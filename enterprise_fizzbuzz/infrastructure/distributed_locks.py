"""
Enterprise FizzBuzz Platform - Distributed Lock Manager (FizzLock)

Preventing deadlocks between operations that complete faster than the
lock acquisition itself. Correctness demands no less.

Provides a hierarchical, multi-granularity lock manager for coordinating
concurrent FizzBuzz evaluation across subsystems. Implements the standard
five lock modes (X, S, IS, IX, U) with a verified 5x5 compatibility matrix,
Tarjan's Strongly Connected Components algorithm for deadlock detection,
wait-die / wound-wait deadlock prevention policies, monotonic fencing tokens,
heap-based lease management with background expiry, and per-resource
contention profiling.

The FizzBuzz evaluation pipeline operates across many subsystems — cache,
blockchain, ML engine, event sourcing, compliance, and more. Without
coordinated locking, concurrent evaluations risk reading stale intermediate
results, producing inconsistent audit trails, or corrupting the MESI cache
coherence protocol. FizzLock ensures serializability across the full
evaluation hierarchy: platform > namespace > subsystem > number > field.
The critical section — evaluating ``n % 3`` — executes in microseconds,
which makes robust deadlock detection all the more essential: at that
timescale, even brief contention windows represent unacceptable risk.
"""

from __future__ import annotations

import heapq
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================================
# Lock Modes
# ============================================================================

class LockMode(Enum):
    """Multi-granularity lock modes for the hierarchical lock manager.

    The five modes form a lattice that governs compatibility between
    concurrent lock requests on the same resource:

    - X  (Exclusive): Full read-write access. Incompatible with all others.
    - S  (Shared): Read-only access. Compatible with S and IS.
    - IS (Intent Shared): Signals intent to acquire S locks at finer
      granularity. Compatible with IS, IX, S, and U.
    - IX (Intent Exclusive): Signals intent to acquire X locks at finer
      granularity. Compatible with IS and IX.
    - U  (Update): Read with intent to upgrade to X. Prevents the
      conversion deadlock that arises when two S-holders both attempt
      upgrade. Compatible with S and IS.
    """

    X = auto()
    S = auto()
    IS = auto()
    IX = auto()
    U = auto()


# 5x5 compatibility matrix.
# COMPAT[requested][held] == True means the modes can coexist.
COMPAT: dict[LockMode, dict[LockMode, bool]] = {
    LockMode.X: {
        LockMode.X: False,
        LockMode.S: False,
        LockMode.IS: False,
        LockMode.IX: False,
        LockMode.U: False,
    },
    LockMode.S: {
        LockMode.X: False,
        LockMode.S: True,
        LockMode.IS: True,
        LockMode.IX: False,
        LockMode.U: False,
    },
    LockMode.IS: {
        LockMode.X: False,
        LockMode.S: True,
        LockMode.IS: True,
        LockMode.IX: True,
        LockMode.U: True,
    },
    LockMode.IX: {
        LockMode.X: False,
        LockMode.S: False,
        LockMode.IS: True,
        LockMode.IX: True,
        LockMode.U: False,
    },
    LockMode.U: {
        LockMode.X: False,
        LockMode.S: True,
        LockMode.IS: True,
        LockMode.IX: False,
        LockMode.U: False,
    },
}

# Intent mode mapping: when acquiring S or X at a fine level, the parent
# levels should hold IS or IX respectively.
_INTENT_MODE: dict[LockMode, LockMode] = {
    LockMode.X: LockMode.IX,
    LockMode.S: LockMode.IS,
    LockMode.U: LockMode.IX,
    LockMode.IS: LockMode.IS,
    LockMode.IX: LockMode.IX,
}


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class LockRequest:
    """A request to acquire a lock on a resource.

    Each request carries a unique identifier, a transaction identifier for
    ownership tracking, the target resource path, the desired lock mode,
    and a monotonic timestamp used by the wait-die / wound-wait policies
    to determine relative transaction age.
    """

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    transaction_id: str = ""
    resource: str = ""
    mode: LockMode = LockMode.S
    timestamp: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        if not self.transaction_id:
            self.transaction_id = uuid.uuid4().hex[:8]


@dataclass
class LockGrant:
    """Confirmation that a lock has been acquired.

    Contains the original request metadata plus a fencing token — a
    monotonically increasing integer that downstream subsystems can use
    to reject stale operations from lock holders whose lease has expired.
    """

    request: LockRequest
    fencing_token: int
    granted_at: float = field(default_factory=time.monotonic)
    lease_expiry: Optional[float] = None

    @property
    def resource(self) -> str:
        return self.request.resource

    @property
    def mode(self) -> LockMode:
        return self.request.mode

    @property
    def transaction_id(self) -> str:
        return self.request.transaction_id


# ============================================================================
# Lock Table — per-resource lock state
# ============================================================================

@dataclass
class _ResourceLockState:
    """Internal bookkeeping for all locks held on a single resource."""

    # transaction_id -> list of LockGrant (a txn may hold multiple modes)
    holders: dict[str, list[LockGrant]] = field(default_factory=lambda: defaultdict(list))
    # Pending requests waiting for compatibility
    wait_queue: deque[LockRequest] = field(default_factory=deque)


class LockTable:
    """Per-resource lock state manager with compatibility checking.

    The LockTable is the core data structure of the lock manager. It
    maintains, for every resource in the hierarchy, the set of current
    holders and a FIFO wait queue. Before granting a new request, it
    checks the 5x5 compatibility matrix against all currently held modes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._resources: dict[str, _ResourceLockState] = defaultdict(
            _ResourceLockState
        )
        self._stats_acquisitions: int = 0
        self._stats_contentions: int = 0

    def is_compatible(self, resource: str, mode: LockMode, transaction_id: str) -> bool:
        """Check whether *mode* is compatible with all currently held locks.

        A transaction is always compatible with its own holdings — upgrading
        from S to X is handled separately by the hierarchical manager.
        """
        with self._lock:
            state = self._resources.get(resource)
            if state is None:
                return True
            for holder_txn, grants in state.holders.items():
                if holder_txn == transaction_id:
                    continue
                for grant in grants:
                    if not COMPAT[mode][grant.mode]:
                        return False
            return True

    def add_holder(self, grant: LockGrant) -> None:
        """Record *grant* as a current holder of its resource."""
        with self._lock:
            self._resources[grant.resource].holders[grant.transaction_id].append(
                grant
            )
            self._stats_acquisitions += 1

    def remove_holder(self, resource: str, transaction_id: str) -> list[LockGrant]:
        """Remove all holdings of *transaction_id* on *resource*. Returns removed grants."""
        with self._lock:
            state = self._resources.get(resource)
            if state is None:
                return []
            removed = state.holders.pop(transaction_id, [])
            # Clean up empty resource entries
            if not state.holders and not state.wait_queue:
                del self._resources[resource]
            return removed

    def enqueue_waiter(self, request: LockRequest) -> None:
        """Add a request to the resource's wait queue."""
        with self._lock:
            self._resources[request.resource].wait_queue.append(request)
            self._stats_contentions += 1

    def dequeue_compatible(self, resource: str) -> list[LockRequest]:
        """Pop all compatible waiters from the front of the queue."""
        with self._lock:
            state = self._resources.get(resource)
            if state is None:
                return []
            granted: list[LockRequest] = []
            remaining: deque[LockRequest] = deque()
            for req in state.wait_queue:
                compatible = True
                for holder_txn, grants in state.holders.items():
                    if holder_txn == req.transaction_id:
                        continue
                    for g in grants:
                        if not COMPAT[req.mode][g.mode]:
                            compatible = False
                            break
                    if not compatible:
                        break
                # Also check compatibility with already-granted waiters
                if compatible:
                    for prev in granted:
                        if prev.transaction_id != req.transaction_id:
                            if not COMPAT[req.mode][prev.mode]:
                                compatible = False
                                break
                if compatible:
                    granted.append(req)
                else:
                    remaining.append(req)
            state.wait_queue = remaining
            return granted

    def remove_waiter(self, resource: str, transaction_id: str) -> Optional[LockRequest]:
        """Remove a specific waiter (e.g., when aborting a transaction)."""
        with self._lock:
            state = self._resources.get(resource)
            if state is None:
                return None
            new_queue: deque[LockRequest] = deque()
            removed: Optional[LockRequest] = None
            for req in state.wait_queue:
                if req.transaction_id == transaction_id and removed is None:
                    removed = req
                else:
                    new_queue.append(req)
            state.wait_queue = new_queue
            return removed

    def get_holders(self, resource: str) -> dict[str, list[LockGrant]]:
        """Return a snapshot of current holders for a resource."""
        with self._lock:
            state = self._resources.get(resource)
            if state is None:
                return {}
            return dict(state.holders)

    def get_all_resources(self) -> list[str]:
        """Return all resources that currently have locks or waiters."""
        with self._lock:
            return list(self._resources.keys())

    def get_waiters(self, resource: str) -> list[LockRequest]:
        """Return a snapshot of the wait queue for a resource."""
        with self._lock:
            state = self._resources.get(resource)
            if state is None:
                return []
            return list(state.wait_queue)

    @property
    def total_acquisitions(self) -> int:
        return self._stats_acquisitions

    @property
    def total_contentions(self) -> int:
        return self._stats_contentions


# ============================================================================
# Deadlock Detection — Tarjan's SCC
# ============================================================================

class DeadlockDetector:
    """Detects deadlock cycles in the wait-for graph using Tarjan's
    Strongly Connected Components algorithm.

    The wait-for graph is a directed graph where an edge from transaction A
    to transaction B means "A is waiting for a resource held by B." A cycle
    in this graph indicates a deadlock — a set of transactions where each
    is waiting for another, and none can proceed.

    Tarjan's algorithm identifies all SCCs in O(V+E) time. Any SCC with
    more than one vertex represents a deadlock cycle. The detector selects
    victims using a youngest-first policy: the transaction with the highest
    timestamp (most recently started) is aborted to break the cycle, as it
    has invested the least work.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # wait-for edges: waiter_txn -> set of holder_txns
        self._edges: dict[str, set[str]] = defaultdict(set)
        self._deadlock_history: list[dict[str, Any]] = []
        self._total_deadlocks: int = 0

    def add_edge(self, waiter: str, holder: str) -> None:
        """Record that *waiter* is waiting for *holder*."""
        if waiter == holder:
            return
        with self._lock:
            self._edges[waiter].add(holder)

    def remove_edges_for(self, transaction_id: str) -> None:
        """Remove all edges involving *transaction_id* (both directions)."""
        with self._lock:
            self._edges.pop(transaction_id, None)
            for txn in list(self._edges):
                self._edges[txn].discard(transaction_id)
                if not self._edges[txn]:
                    del self._edges[txn]

    def detect(self, timestamps: dict[str, float]) -> list[list[str]]:
        """Run Tarjan's SCC algorithm and return deadlock cycles.

        Each returned list is an SCC with |V| > 1, representing a set
        of mutually deadlocked transactions. Within each cycle, the
        transactions are sorted by timestamp (ascending), so the last
        element is the recommended victim (youngest-first).
        """
        with self._lock:
            graph = {k: set(v) for k, v in self._edges.items()}

        # Tarjan's algorithm
        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        index_map: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        sccs: list[list[str]] = []

        all_nodes: set[str] = set(graph.keys())
        for targets in graph.values():
            all_nodes.update(targets)

        def strongconnect(v: str) -> None:
            index_map[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in graph.get(v, set()):
                if w not in index_map:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index_map[w])

            if lowlink[v] == index_map[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    # Sort by timestamp ascending; youngest (highest ts) last
                    scc.sort(key=lambda t: timestamps.get(t, 0.0))
                    sccs.append(scc)

        for node in all_nodes:
            if node not in index_map:
                strongconnect(node)

        if sccs:
            with self._lock:
                self._total_deadlocks += len(sccs)
                for scc in sccs:
                    self._deadlock_history.append({
                        "cycle": list(scc),
                        "victim": scc[-1],
                        "detected_at": time.monotonic(),
                        "size": len(scc),
                    })

        return sccs

    def select_victim(self, cycle: list[str], timestamps: dict[str, float]) -> str:
        """Select the youngest transaction in the cycle as the victim.

        The youngest-first policy minimizes wasted work: the transaction
        that has been running for the shortest time is the cheapest to abort.
        """
        return max(cycle, key=lambda t: timestamps.get(t, 0.0))

    @property
    def deadlock_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._deadlock_history)

    @property
    def total_deadlocks(self) -> int:
        return self._total_deadlocks

    @property
    def edge_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._edges.values())

    def get_wait_for_graph(self) -> dict[str, set[str]]:
        """Return a snapshot of the wait-for graph."""
        with self._lock:
            return {k: set(v) for k, v in self._edges.items()}


# ============================================================================
# Wait Policy — Wait-Die and Wound-Wait
# ============================================================================

class WaitPolicyType(Enum):
    """Deadlock prevention policy selection."""

    WAIT_DIE = auto()
    WOUND_WAIT = auto()


class WaitPolicy:
    """Implements wait-die and wound-wait deadlock prevention policies.

    Both policies use transaction timestamps to impose a total ordering
    on transactions, preventing cycles from forming in the wait-for graph.

    **Wait-Die** (non-preemptive): If the requesting transaction is older
    (lower timestamp) than the holder, it waits. If it is younger, it
    aborts ("dies") immediately rather than risk forming a cycle.

    **Wound-Wait** (preemptive): If the requesting transaction is older
    than the holder, it "wounds" (aborts) the holder and takes the lock.
    If it is younger, it waits. This policy guarantees that older
    transactions always make progress.
    """

    def __init__(self, policy_type: WaitPolicyType = WaitPolicyType.WAIT_DIE) -> None:
        self._policy = policy_type
        self._aborted: set[str] = set()
        self._lock = threading.Lock()

    @property
    def policy_type(self) -> WaitPolicyType:
        return self._policy

    def decide(
        self,
        requester_txn: str,
        requester_ts: float,
        holder_txn: str,
        holder_ts: float,
    ) -> str:
        """Decide the action for a conflicting lock request.

        Returns one of:
        - "wait"    : the requester should wait for the holder
        - "abort_requester" : the requester should abort itself
        - "abort_holder"    : the holder should be aborted (wound-wait only)
        """
        if self._policy == WaitPolicyType.WAIT_DIE:
            # Older (lower ts) waits; younger dies
            if requester_ts <= holder_ts:
                return "wait"
            else:
                return "abort_requester"
        else:
            # Wound-Wait: Older wounds (aborts) holder; younger waits
            if requester_ts <= holder_ts:
                return "abort_holder"
            else:
                return "wait"

    def mark_aborted(self, transaction_id: str) -> None:
        """Record a transaction as aborted."""
        with self._lock:
            self._aborted.add(transaction_id)

    def is_aborted(self, transaction_id: str) -> bool:
        """Check if a transaction has been aborted."""
        with self._lock:
            return transaction_id in self._aborted

    def clear_aborted(self, transaction_id: str) -> None:
        """Remove a transaction from the aborted set (e.g., after restart)."""
        with self._lock:
            self._aborted.discard(transaction_id)


# ============================================================================
# Fencing Token Generator
# ============================================================================

class FencingTokenGenerator:
    """Generates strictly monotonically increasing 64-bit fencing tokens.

    Fencing tokens provide protection against stale lock holders. When a
    lease expires and is re-acquired by a new transaction, the new holder
    receives a higher token value. Downstream subsystems (cache, blockchain,
    event store) compare the incoming token against the last-seen token
    and reject operations bearing a lower value, preventing
    out-of-order writes from zombie lock holders.

    Thread-safe via threading.Lock. The counter is an unbounded Python
    integer that is conceptually a 64-bit value for wire protocol purposes.
    """

    def __init__(self, initial: int = 0) -> None:
        self._counter = initial
        self._lock = threading.Lock()

    def next(self) -> int:
        """Generate the next fencing token. Guaranteed strictly monotonic."""
        with self._lock:
            self._counter += 1
            return self._counter

    @property
    def current(self) -> int:
        """The most recently issued token value."""
        with self._lock:
            return self._counter


# ============================================================================
# Lease Manager
# ============================================================================

class LeaseManager:
    """Heap-based lease expiration manager with background reaper thread.

    Every lock grant may carry a lease — a wall-clock deadline after which
    the lock is considered expired and must be revoked. The LeaseManager
    maintains a min-heap ordered by expiry time and runs a daemon thread
    that periodically scans for expired leases.

    A configurable grace period allows a small window for lease renewal
    before the lock is forcibly released. This prevents transient delays
    (e.g., GC pauses) from causing premature revocation.
    """

    def __init__(
        self,
        lease_duration: float = 30.0,
        grace_period: float = 5.0,
        check_interval: float = 1.0,
        on_expire: Optional[Callable[[LockGrant], None]] = None,
    ) -> None:
        self._lease_duration = lease_duration
        self._grace_period = grace_period
        self._check_interval = check_interval
        self._on_expire = on_expire

        self._lock = threading.Lock()
        # Heap entries: (expiry_time, grant_id, LockGrant)
        self._heap: list[tuple[float, str, LockGrant]] = []
        self._active: dict[str, LockGrant] = {}  # grant request_id -> grant
        self._expired_count: int = 0
        self._renewed_count: int = 0

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background lease reaper thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._reaper_loop,
            name="FizzLock-LeaseReaper",
            daemon=True,
        )
        self._thread.start()
        logger.debug("Lease reaper thread started (interval=%.1fs)", self._check_interval)

    def stop(self) -> None:
        """Stop the background lease reaper thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self._check_interval * 2)
            self._thread = None

    def register(self, grant: LockGrant) -> None:
        """Register a lock grant for lease tracking."""
        expiry = time.monotonic() + self._lease_duration
        grant.lease_expiry = expiry
        with self._lock:
            self._active[grant.request.request_id] = grant
            heapq.heappush(self._heap, (expiry, grant.request.request_id, grant))

    def renew(self, request_id: str) -> bool:
        """Renew the lease for a grant, extending its expiry.

        Returns True if renewal succeeded, False if the grant is not found
        or has already expired.
        """
        with self._lock:
            grant = self._active.get(request_id)
            if grant is None:
                return False
            new_expiry = time.monotonic() + self._lease_duration
            grant.lease_expiry = new_expiry
            heapq.heappush(self._heap, (new_expiry, request_id, grant))
            self._renewed_count += 1
            return True

    def unregister(self, request_id: str) -> None:
        """Remove a grant from lease tracking (e.g., on voluntary release)."""
        with self._lock:
            self._active.pop(request_id, None)

    def _reaper_loop(self) -> None:
        """Background loop that checks for expired leases."""
        while self._running:
            self._check_expired()
            time.sleep(self._check_interval)

    def _check_expired(self) -> None:
        """Scan the heap and expire any leases past their deadline + grace."""
        now = time.monotonic()
        expired_grants: list[LockGrant] = []

        with self._lock:
            while self._heap:
                expiry, req_id, grant = self._heap[0]
                if expiry + self._grace_period > now:
                    break
                heapq.heappop(self._heap)
                # Only expire if still active and expiry hasn't been renewed
                active_grant = self._active.get(req_id)
                if active_grant is not None and active_grant.lease_expiry is not None:
                    if active_grant.lease_expiry + self._grace_period <= now:
                        self._active.pop(req_id, None)
                        self._expired_count += 1
                        expired_grants.append(active_grant)

        for grant in expired_grants:
            logger.info(
                "Lease expired for resource=%s txn=%s token=%d",
                grant.resource, grant.transaction_id, grant.fencing_token,
            )
            if self._on_expire:
                try:
                    self._on_expire(grant)
                except Exception:
                    logger.exception("Error in lease expiry callback")

    @property
    def active_lease_count(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def expired_count(self) -> int:
        return self._expired_count

    @property
    def renewed_count(self) -> int:
        return self._renewed_count

    @property
    def lease_duration(self) -> float:
        return self._lease_duration


# ============================================================================
# Contention Profiler
# ============================================================================

class ContentionProfiler:
    """Per-resource wait-time histogram and hot-lock detection.

    The ContentionProfiler records the wait time (time between lock request
    and lock grant) for every acquisition. It maintains a histogram of
    wait times per resource and identifies "hot locks" — resources whose
    total contention time exceeds a configurable threshold.

    This data feeds the LockDashboard's contention heatmap, enabling
    operators to identify bottleneck resources and adjust the lock
    hierarchy or evaluation pipeline accordingly.
    """

    def __init__(self, hot_lock_threshold_ms: float = 10.0) -> None:
        self._lock = threading.Lock()
        self._hot_threshold = hot_lock_threshold_ms
        # resource -> list of wait durations in ms
        self._wait_times: dict[str, list[float]] = defaultdict(list)
        self._total_wait_ms: float = 0.0
        self._total_samples: int = 0

    def record_wait(self, resource: str, wait_ms: float) -> None:
        """Record a wait-time sample for a resource."""
        with self._lock:
            self._wait_times[resource].append(wait_ms)
            self._total_wait_ms += wait_ms
            self._total_samples += 1

    def get_histogram(self, resource: str) -> dict[str, Any]:
        """Return wait-time statistics for a specific resource."""
        with self._lock:
            times = self._wait_times.get(resource, [])
        if not times:
            return {"count": 0, "min_ms": 0.0, "max_ms": 0.0, "avg_ms": 0.0, "p50_ms": 0.0, "p99_ms": 0.0}
        sorted_times = sorted(times)
        n = len(sorted_times)
        return {
            "count": n,
            "min_ms": sorted_times[0],
            "max_ms": sorted_times[-1],
            "avg_ms": sum(sorted_times) / n,
            "p50_ms": sorted_times[n // 2],
            "p99_ms": sorted_times[min(int(n * 0.99), n - 1)],
        }

    def get_hot_locks(self) -> list[tuple[str, float]]:
        """Return resources whose average wait time exceeds the threshold.

        Returns a list of (resource, avg_wait_ms) tuples sorted by average
        wait time descending.
        """
        hot: list[tuple[str, float]] = []
        with self._lock:
            for resource, times in self._wait_times.items():
                if times:
                    avg = sum(times) / len(times)
                    if avg >= self._hot_threshold:
                        hot.append((resource, avg))
        hot.sort(key=lambda x: x[1], reverse=True)
        return hot

    def get_contention_heatmap(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Return the top-N resources by total contention time."""
        entries: list[tuple[str, float, int]] = []
        with self._lock:
            for resource, times in self._wait_times.items():
                entries.append((resource, sum(times), len(times)))
        entries.sort(key=lambda x: x[1], reverse=True)
        return [
            {"resource": r, "total_ms": t, "count": c}
            for r, t, c in entries[:top_n]
        ]

    @property
    def total_wait_ms(self) -> float:
        return self._total_wait_ms

    @property
    def total_samples(self) -> int:
        return self._total_samples


# ============================================================================
# Hierarchical Lock Manager
# ============================================================================

# The five-level resource hierarchy
HIERARCHY_LEVELS = ["platform", "namespace", "subsystem", "number", "field"]


def _resource_path(
    platform: str = "efp",
    namespace: str = "default",
    subsystem: str = "evaluation",
    number: Optional[int] = None,
    field_name: Optional[str] = None,
) -> str:
    """Construct a canonical resource path in the lock hierarchy.

    The hierarchy is: /platform/namespace/subsystem/number/field
    Omitted trailing components produce a coarser-grained resource path.
    """
    parts = [platform, namespace, subsystem]
    if number is not None:
        parts.append(str(number))
        if field_name is not None:
            parts.append(field_name)
    return "/".join(parts)


def _ancestor_paths(resource: str) -> list[str]:
    """Return all ancestor resource paths, from root to parent.

    For resource "efp/default/evaluation/42/result", returns:
    ["efp", "efp/default", "efp/default/evaluation", "efp/default/evaluation/42"]
    """
    parts = resource.split("/")
    ancestors: list[str] = []
    for i in range(1, len(parts)):
        ancestors.append("/".join(parts[:i]))
    return ancestors


class HierarchicalLockManager:
    """Multi-granularity hierarchical lock manager.

    Implements the standard multi-granularity locking protocol with a
    five-level hierarchy: platform / namespace / subsystem / number / field.

    When a lock is requested at a fine granularity (e.g., number 42), the
    manager automatically acquires intent locks at all ancestor levels.
    For example, acquiring S on "efp/default/evaluation/42" first acquires
    IS on "efp", "efp/default", and "efp/default/evaluation".

    Supports lock upgrade (S -> X) and downgrade (X -> S) within the
    same transaction. Integrates with DeadlockDetector for cycle detection
    and WaitPolicy for deadlock prevention.
    """

    def __init__(
        self,
        wait_policy: Optional[WaitPolicy] = None,
        token_generator: Optional[FencingTokenGenerator] = None,
        lease_manager: Optional[LeaseManager] = None,
        profiler: Optional[ContentionProfiler] = None,
    ) -> None:
        self._table = LockTable()
        self._detector = DeadlockDetector()
        self._policy = wait_policy or WaitPolicy()
        self._tokens = token_generator or FencingTokenGenerator()
        self._leases = lease_manager
        self._profiler = profiler

        self._lock = threading.Lock()
        # transaction_id -> timestamp (for age-based policies)
        self._txn_timestamps: dict[str, float] = {}
        # transaction_id -> list of all resources locked
        self._txn_locks: dict[str, list[str]] = defaultdict(list)
        self._total_acquires: int = 0
        self._total_releases: int = 0
        self._total_upgrades: int = 0
        self._total_aborts: int = 0

    @property
    def lock_table(self) -> LockTable:
        return self._table

    @property
    def deadlock_detector(self) -> DeadlockDetector:
        return self._detector

    @property
    def wait_policy(self) -> WaitPolicy:
        return self._policy

    @property
    def fencing_token_generator(self) -> FencingTokenGenerator:
        return self._tokens

    @property
    def contention_profiler(self) -> Optional[ContentionProfiler]:
        return self._profiler

    def register_transaction(self, transaction_id: str, timestamp: Optional[float] = None) -> None:
        """Register a transaction with its timestamp for policy decisions."""
        with self._lock:
            self._txn_timestamps[transaction_id] = timestamp or time.monotonic()

    def _get_timestamp(self, transaction_id: str) -> float:
        with self._lock:
            ts = self._txn_timestamps.get(transaction_id)
            if ts is None:
                ts = time.monotonic()
                self._txn_timestamps[transaction_id] = ts
            return ts

    def acquire(
        self,
        resource: str,
        mode: LockMode,
        transaction_id: str,
        timeout: float = 5.0,
    ) -> Optional[LockGrant]:
        """Acquire a lock on *resource* with the given *mode*.

        Automatically acquires intent locks at all ancestor levels in the
        resource hierarchy. If the lock cannot be granted immediately,
        applies the configured wait policy (wait-die or wound-wait) and
        blocks up to *timeout* seconds.

        Returns a LockGrant on success, or None if the lock could not be
        acquired (timeout, abort, or deadlock).
        """
        from enterprise_fizzbuzz.domain.exceptions import (
            LockAcquisitionTimeoutError,
            LockDeadlockDetectedError,
        )

        self._get_timestamp(transaction_id)  # ensure registered

        # Step 1: Acquire intent locks at ancestor levels
        ancestors = _ancestor_paths(resource)
        intent_mode = _INTENT_MODE.get(mode, LockMode.IS)

        for ancestor in ancestors:
            if not self._acquire_single(ancestor, intent_mode, transaction_id, timeout):
                return None

        # Step 2: Acquire the actual lock
        grant = self._acquire_single(resource, mode, transaction_id, timeout)
        if grant is not None:
            with self._lock:
                self._total_acquires += 1
        return grant

    def _acquire_single(
        self,
        resource: str,
        mode: LockMode,
        transaction_id: str,
        timeout: float,
    ) -> Optional[LockGrant]:
        """Acquire a single lock (no hierarchy traversal)."""
        from enterprise_fizzbuzz.domain.exceptions import (
            LockAcquisitionTimeoutError,
            LockDeadlockDetectedError,
            LockTransactionAbortedError,
        )

        start = time.monotonic()

        # Check if we already hold a compatible or same lock
        existing = self._table.get_holders(resource)
        if transaction_id in existing:
            for g in existing[transaction_id]:
                if g.mode == mode:
                    return g  # Already hold this exact lock

        # Try immediate grant
        if self._table.is_compatible(resource, mode, transaction_id):
            return self._grant_lock(resource, mode, transaction_id)

        # Apply wait policy against each conflicting holder
        holders = self._table.get_holders(resource)
        requester_ts = self._get_timestamp(transaction_id)

        for holder_txn, grants in holders.items():
            if holder_txn == transaction_id:
                continue
            holder_ts = self._get_timestamp(holder_txn)
            decision = self._policy.decide(requester_ts, requester_ts, holder_txn, holder_ts)

            if decision == "abort_requester":
                self._policy.mark_aborted(transaction_id)
                with self._lock:
                    self._total_aborts += 1
                return None
            elif decision == "abort_holder":
                # Wound the holder
                self._force_release(holder_txn)
                self._policy.mark_aborted(holder_txn)
                with self._lock:
                    self._total_aborts += 1

        # Add wait-for edges for deadlock detection
        for holder_txn in holders:
            if holder_txn != transaction_id:
                self._detector.add_edge(transaction_id, holder_txn)

        # Check for deadlocks
        timestamps = dict(self._txn_timestamps)
        cycles = self._detector.detect(timestamps)
        if cycles:
            for cycle in cycles:
                victim = self._detector.select_victim(cycle, timestamps)
                if victim == transaction_id:
                    self._detector.remove_edges_for(transaction_id)
                    self._policy.mark_aborted(transaction_id)
                    with self._lock:
                        self._total_aborts += 1
                    return None

        # Spin-wait with backoff until timeout
        wait_start = time.monotonic()
        backoff = 0.001  # 1ms initial backoff
        while time.monotonic() - start < timeout:
            if self._policy.is_aborted(transaction_id):
                self._detector.remove_edges_for(transaction_id)
                return None

            if self._table.is_compatible(resource, mode, transaction_id):
                self._detector.remove_edges_for(transaction_id)
                grant = self._grant_lock(resource, mode, transaction_id)
                if grant is not None and self._profiler is not None:
                    wait_ms = (time.monotonic() - wait_start) * 1000
                    self._profiler.record_wait(resource, wait_ms)
                return grant

            time.sleep(min(backoff, 0.05))
            backoff = min(backoff * 2, 0.05)

        # Timeout
        self._detector.remove_edges_for(transaction_id)
        return None

    def _grant_lock(self, resource: str, mode: LockMode, transaction_id: str) -> LockGrant:
        """Create a LockGrant and register it in the table."""
        request = LockRequest(
            transaction_id=transaction_id,
            resource=resource,
            mode=mode,
            timestamp=self._get_timestamp(transaction_id),
        )
        token = self._tokens.next()
        grant = LockGrant(request=request, fencing_token=token)

        self._table.add_holder(grant)

        with self._lock:
            if resource not in self._txn_locks[transaction_id]:
                self._txn_locks[transaction_id].append(resource)

        if self._leases is not None:
            self._leases.register(grant)

        logger.debug(
            "Lock granted: resource=%s mode=%s txn=%s token=%d",
            resource, mode.name, transaction_id, token,
        )
        return grant

    def release(self, resource: str, transaction_id: str) -> bool:
        """Release all locks held by *transaction_id* on *resource*.

        Also releases intent locks at ancestor levels if the transaction
        holds no other locks that require them.
        """
        removed = self._table.remove_holder(resource, transaction_id)
        if not removed:
            return False

        for grant in removed:
            if self._leases is not None:
                self._leases.unregister(grant.request.request_id)

        with self._lock:
            if resource in self._txn_locks.get(transaction_id, []):
                self._txn_locks[transaction_id].remove(resource)
            self._total_releases += 1

        # Clean up ancestor intent locks if no longer needed
        ancestors = _ancestor_paths(resource)
        for ancestor in reversed(ancestors):
            # Check if txn still holds any other locks under this ancestor
            still_needed = False
            with self._lock:
                for other_resource in self._txn_locks.get(transaction_id, []):
                    if other_resource.startswith(ancestor + "/") or other_resource == ancestor:
                        still_needed = True
                        break
            if not still_needed:
                self._table.remove_holder(ancestor, transaction_id)

        self._detector.remove_edges_for(transaction_id)
        logger.debug("Lock released: resource=%s txn=%s", resource, transaction_id)
        return True

    def release_all(self, transaction_id: str) -> int:
        """Release all locks held by a transaction. Returns the count released."""
        with self._lock:
            resources = list(self._txn_locks.get(transaction_id, []))
        count = 0
        for resource in resources:
            removed = self._table.remove_holder(resource, transaction_id)
            for grant in removed:
                if self._leases is not None:
                    self._leases.unregister(grant.request.request_id)
            count += len(removed)

        # Also release any ancestor intent locks
        all_ancestors: set[str] = set()
        for resource in resources:
            for a in _ancestor_paths(resource):
                all_ancestors.add(a)
        for ancestor in all_ancestors:
            self._table.remove_holder(ancestor, transaction_id)

        with self._lock:
            self._txn_locks.pop(transaction_id, None)
            self._txn_timestamps.pop(transaction_id, None)
            self._total_releases += count

        self._detector.remove_edges_for(transaction_id)
        self._policy.clear_aborted(transaction_id)
        return count

    def _force_release(self, transaction_id: str) -> None:
        """Force-release all locks for a transaction (used by wound-wait)."""
        self.release_all(transaction_id)

    def upgrade(self, resource: str, transaction_id: str, new_mode: LockMode = LockMode.X, timeout: float = 5.0) -> Optional[LockGrant]:
        """Upgrade an existing lock on *resource* to a stronger mode.

        Releases the current lock and re-acquires with the new mode.
        Common pattern: S -> X for read-then-modify operations.
        """
        holders = self._table.get_holders(resource)
        current_grants = holders.get(transaction_id, [])
        if not current_grants:
            return None

        # Release current lock
        self._table.remove_holder(resource, transaction_id)
        for g in current_grants:
            if self._leases is not None:
                self._leases.unregister(g.request.request_id)

        # Acquire upgraded lock
        grant = self._acquire_single(resource, new_mode, transaction_id, timeout)
        if grant is not None:
            with self._lock:
                self._total_upgrades += 1
        else:
            # Re-acquire original locks if upgrade fails
            for g in current_grants:
                self._acquire_single(resource, g.mode, transaction_id, timeout)
        return grant

    def get_transaction_locks(self, transaction_id: str) -> list[str]:
        """Return all resources currently locked by a transaction."""
        with self._lock:
            return list(self._txn_locks.get(transaction_id, []))

    def get_active_lock_count(self) -> int:
        """Return the total number of active locks across all resources."""
        total = 0
        for resource in self._table.get_all_resources():
            holders = self._table.get_holders(resource)
            for grants in holders.values():
                total += len(grants)
        return total

    @property
    def total_acquires(self) -> int:
        return self._total_acquires

    @property
    def total_releases(self) -> int:
        return self._total_releases

    @property
    def total_upgrades(self) -> int:
        return self._total_upgrades

    @property
    def total_aborts(self) -> int:
        return self._total_aborts


# ============================================================================
# Lock Dashboard — ASCII visualization
# ============================================================================

class LockDashboard:
    """ASCII dashboard providing real-time visibility into the lock manager.

    Renders four panels:
    1. Active Locks — currently held locks by resource and transaction
    2. Wait-For Graph — directed edges between waiting transactions
    3. Deadlock History — past deadlock cycles and selected victims
    4. Contention Heatmap — top resources by total wait time

    The dashboard is a critical operational tool: without visibility into
    lock state, diagnosing liveness issues in the FizzBuzz evaluation
    pipeline would require attaching a debugger to the modulo operator,
    which is as impractical as it sounds.
    """

    @staticmethod
    def render(
        manager: HierarchicalLockManager,
        width: int = 60,
    ) -> str:
        """Render the complete FizzLock dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        divider = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "| " + text.ljust(width - 4) + " |"

        lines.append(border)
        lines.append(center("FIZZLOCK DISTRIBUTED LOCK MANAGER"))
        lines.append(center("Hierarchical Multi-Granularity Locking"))
        lines.append(border)

        # Stats
        lines.append(left(f"Policy: {manager.wait_policy.policy_type.name}"))
        lines.append(left(f"Acquires: {manager.total_acquires}  Releases: {manager.total_releases}"))
        lines.append(left(f"Upgrades: {manager.total_upgrades}  Aborts: {manager.total_aborts}"))
        lines.append(left(f"Fencing Token: {manager.fencing_token_generator.current}"))
        lines.append(left(f"Active Locks: {manager.get_active_lock_count()}"))
        lines.append(left(f"Deadlocks Detected: {manager.deadlock_detector.total_deadlocks}"))
        lines.append(divider)

        # Panel 1: Active Locks
        lines.append(center("ACTIVE LOCKS"))
        lines.append(divider)

        resources = manager.lock_table.get_all_resources()
        if not resources:
            lines.append(left("  (no active locks)"))
        else:
            for resource in sorted(resources)[:15]:
                holders = manager.lock_table.get_holders(resource)
                for txn_id, grants in holders.items():
                    modes_str = ",".join(g.mode.name for g in grants)
                    res_display = resource
                    max_len = width - 22
                    if len(res_display) > max_len:
                        res_display = "..." + res_display[-(max_len - 3):]
                    line = f"  {res_display}: {txn_id[:8]} [{modes_str}]"
                    lines.append(left(line))

        lines.append(divider)

        # Panel 2: Wait-For Graph
        lines.append(center("WAIT-FOR GRAPH"))
        lines.append(divider)

        wf_graph = manager.deadlock_detector.get_wait_for_graph()
        if not wf_graph:
            lines.append(left("  (no waiting transactions)"))
        else:
            for waiter, holders in sorted(wf_graph.items()):
                for holder in sorted(holders):
                    lines.append(left(f"  {waiter[:8]} --waits--> {holder[:8]}"))

        lines.append(divider)

        # Panel 3: Deadlock History
        lines.append(center("DEADLOCK HISTORY"))
        lines.append(divider)

        history = manager.deadlock_detector.deadlock_history
        if not history:
            lines.append(left("  (no deadlocks detected)"))
        else:
            for entry in history[-5:]:
                cycle_str = " -> ".join(t[:8] for t in entry["cycle"])
                lines.append(left(f"  Cycle: {cycle_str}"))
                lines.append(left(f"  Victim: {entry['victim'][:8]}  Size: {entry['size']}"))

        lines.append(divider)

        # Panel 4: Contention Heatmap
        lines.append(center("CONTENTION HEATMAP"))
        lines.append(divider)

        profiler = manager.contention_profiler
        if profiler is None or profiler.total_samples == 0:
            lines.append(left("  (no contention data)"))
        else:
            lines.append(left(f"  Total Wait: {profiler.total_wait_ms:.1f}ms across {profiler.total_samples} samples"))
            heatmap = profiler.get_contention_heatmap(top_n=5)
            if heatmap:
                max_total = max(e["total_ms"] for e in heatmap) if heatmap else 1.0
                for entry in heatmap:
                    bar_len = int((entry["total_ms"] / max(max_total, 0.001)) * 15)
                    bar = "#" * bar_len
                    res = entry["resource"]
                    max_res_len = width - 35
                    if len(res) > max_res_len:
                        res = "..." + res[-(max_res_len - 3):]
                    lines.append(left(f"  {res}: {bar} {entry['total_ms']:.1f}ms"))

            hot = profiler.get_hot_locks()
            if hot:
                lines.append(left("  Hot Locks:"))
                for resource, avg_ms in hot[:3]:
                    res = resource
                    max_res_len = width - 30
                    if len(res) > max_res_len:
                        res = "..." + res[-(max_res_len - 3):]
                    lines.append(left(f"    {res}: avg {avg_ms:.2f}ms"))

        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Lock Middleware — IMiddleware implementation
# ============================================================================

class LockMiddleware(IMiddleware):
    """Middleware that acquires a shared lock on the number resource before
    evaluation and releases it afterward.

    Each number in the FizzBuzz pipeline passes through the middleware
    chain. This middleware ensures that concurrent evaluations of the
    same number are serialized via shared locks, while evaluations of
    different numbers proceed in parallel.

    The lock resource is constructed as:
        efp/default/evaluation/{number}

    A shared (S) lock permits multiple concurrent readers while preventing
    exclusive writers from modifying intermediate state during evaluation.
    The lock is released after the downstream middleware chain completes.
    """

    def __init__(
        self,
        manager: HierarchicalLockManager,
        priority: int = 800,
    ) -> None:
        self._manager = manager
        self._priority = priority
        self._lock_count = 0
        self._failed_count = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Acquire S-lock on number resource, evaluate, then release."""
        number = context.number
        resource = _resource_path(number=number)
        txn_id = f"eval-{number}-{uuid.uuid4().hex[:6]}"

        self._manager.register_transaction(txn_id)

        grant = self._manager.acquire(
            resource=resource,
            mode=LockMode.S,
            transaction_id=txn_id,
            timeout=5.0,
        )

        if grant is None:
            self._failed_count += 1
            logger.warning(
                "Failed to acquire lock for number %d, proceeding unlocked", number
            )
            context.metadata["lock_acquired"] = False
            result = next_handler(context)
            self._manager.release_all(txn_id)
            return result

        self._lock_count += 1
        context.metadata["lock_acquired"] = True
        context.metadata["lock_fencing_token"] = grant.fencing_token
        context.metadata["lock_resource"] = resource
        context.metadata["lock_transaction_id"] = txn_id

        try:
            result = next_handler(context)
        finally:
            self._manager.release_all(txn_id)

        return result

    def get_name(self) -> str:
        return "LockMiddleware"

    def get_priority(self) -> int:
        return self._priority

    @property
    def lock_count(self) -> int:
        return self._lock_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

"""
Enterprise FizzBuzz Platform - FizzCRDT: Conflict-Free Replicated Data Types

Implements a complete CRDT library for eventual consistency across the
FizzBuzz evaluation cluster. Because when you have N replicas of a modulo
operation, you need mathematically proven convergence guarantees. The
join-semilattice axioms (commutative, associative, idempotent merge) ensure
that all replicas converge to the same state regardless of message ordering,
network partitions, or whether Mercury is in retrograde.

Every CRDT in this module satisfies the Strong Eventual Consistency (SEC)
property: any two replicas that have received the same set of updates
(in any order) will have identical state. This is achieved through
state-based (CvRDT) replication where the merge function computes
the least upper bound (LUB) in the semilattice.

Supported CRDTs:
- VectorClock: Lamport-style logical timestamps for causal ordering
- GCounter: Grow-only counter (increment only)
- PNCounter: Positive-Negative counter (increment and decrement)
- LWWRegister: Last-Writer-Wins register with wall-clock timestamps
- MVRegister: Multi-Value register preserving concurrent writes
- ORSet: Observed-Remove set with add-wins semantics
- LWWMap: Dictionary of key -> LWWRegister entries
- RGA: Replicated Growable Array with Lamport timestamp ordering
- CRDTMergeEngine: State-based replication orchestrator
- CRDTDashboard: ASCII visualization of CRDT state
- CRDTMiddleware: IMiddleware for replicating classification state
"""

from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CRDTError,
    CRDTMergeConflictError,
    CRDTCausalityViolationError,
    CRDTReplicaDivergenceError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# =====================================================================
# Vector Clock
# =====================================================================

class VectorClock:
    """Logical timestamps for causal ordering across replicas.

    Each replica maintains its own counter. The vector is the collection
    of all replica counters. Merge = element-wise max. Happened-before
    is defined as: a < b iff forall i: a[i] <= b[i] and exists j: a[j] < b[j].
    """

    def __init__(self, node_id: str = "", clocks: Optional[dict[str, int]] = None) -> None:
        self._node_id = node_id
        self._clocks: dict[str, int] = dict(clocks) if clocks else {}

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def clocks(self) -> dict[str, int]:
        return dict(self._clocks)

    def increment(self, node_id: Optional[str] = None) -> VectorClock:
        """Increment the clock for the given node (or self)."""
        nid = node_id or self._node_id
        self._clocks[nid] = self._clocks.get(nid, 0) + 1
        return self

    def get(self, node_id: str) -> int:
        """Get the clock value for a specific node."""
        return self._clocks.get(node_id, 0)

    def merge(self, other: VectorClock) -> VectorClock:
        """Merge with another vector clock (element-wise max)."""
        all_nodes = set(self._clocks.keys()) | set(other._clocks.keys())
        merged = {}
        for node in all_nodes:
            merged[node] = max(self._clocks.get(node, 0), other._clocks.get(node, 0))
        return VectorClock(node_id=self._node_id, clocks=merged)

    def happened_before(self, other: VectorClock) -> bool:
        """Return True if self happened-before other (strict partial order).

        a < b iff forall i: a[i] <= b[i] AND exists j: a[j] < b[j]
        """
        all_nodes = set(self._clocks.keys()) | set(other._clocks.keys())
        all_leq = True
        any_lt = False
        for node in all_nodes:
            self_val = self._clocks.get(node, 0)
            other_val = other._clocks.get(node, 0)
            if self_val > other_val:
                all_leq = False
                break
            if self_val < other_val:
                any_lt = True
        return all_leq and any_lt

    def is_concurrent(self, other: VectorClock) -> bool:
        """Return True if neither clock happened-before the other."""
        return not self.happened_before(other) and not other.happened_before(self) and self != other

    def dominates(self, other: VectorClock) -> bool:
        """Return True if self >= other (all components >=)."""
        all_nodes = set(self._clocks.keys()) | set(other._clocks.keys())
        for node in all_nodes:
            if self._clocks.get(node, 0) < other._clocks.get(node, 0):
                return False
        return True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VectorClock):
            return NotImplemented
        all_nodes = set(self._clocks.keys()) | set(other._clocks.keys())
        for node in all_nodes:
            if self._clocks.get(node, 0) != other._clocks.get(node, 0):
                return False
        return True

    def __repr__(self) -> str:
        entries = ", ".join(f"{k}:{v}" for k, v in sorted(self._clocks.items()))
        return f"VC({entries})"

    def copy(self) -> VectorClock:
        """Return a deep copy of this vector clock."""
        return VectorClock(node_id=self._node_id, clocks=dict(self._clocks))


# =====================================================================
# GCounter — Grow-only Counter
# =====================================================================

class GCounter:
    """Grow-only counter CRDT.

    Each node has its own monotonically increasing counter.
    value() = sum of all node counters.
    merge = element-wise max.

    This is the fundamental building block. If you can count up,
    you can do anything. Except count down. For that you need PNCounter.
    """

    def __init__(self, node_id: str = "", counters: Optional[dict[str, int]] = None) -> None:
        self._node_id = node_id
        self._counters: dict[str, int] = dict(counters) if counters else {}

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def counters(self) -> dict[str, int]:
        return dict(self._counters)

    def increment(self, amount: int = 1, node_id: Optional[str] = None) -> None:
        """Increment the counter for the given node."""
        if amount < 0:
            raise CRDTError("GCounter does not support decrement. Use PNCounter.")
        nid = node_id or self._node_id
        self._counters[nid] = self._counters.get(nid, 0) + amount

    def value(self) -> int:
        """Return the total count (sum of all node counters)."""
        return sum(self._counters.values())

    def merge(self, other: GCounter) -> GCounter:
        """Merge with another GCounter (element-wise max)."""
        all_nodes = set(self._counters.keys()) | set(other._counters.keys())
        merged = {}
        for node in all_nodes:
            merged[node] = max(self._counters.get(node, 0), other._counters.get(node, 0))
        return GCounter(node_id=self._node_id, counters=merged)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GCounter):
            return NotImplemented
        all_nodes = set(self._counters.keys()) | set(other._counters.keys())
        for node in all_nodes:
            if self._counters.get(node, 0) != other._counters.get(node, 0):
                return False
        return True

    def __repr__(self) -> str:
        return f"GCounter(value={self.value()}, nodes={dict(self._counters)})"


# =====================================================================
# PNCounter — Positive-Negative Counter
# =====================================================================

class PNCounter:
    """Positive-Negative counter CRDT.

    A pair of GCounters: P (positive) and N (negative).
    value() = P.value() - N.value().

    Because sometimes the FizzBuzz cluster needs to decrement
    the number of times it has been disappointed by a non-FizzBuzz number.
    """

    def __init__(self, node_id: str = "") -> None:
        self._node_id = node_id
        self._p = GCounter(node_id=node_id)
        self._n = GCounter(node_id=node_id)

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def p(self) -> GCounter:
        return self._p

    @property
    def n(self) -> GCounter:
        return self._n

    def increment(self, amount: int = 1, node_id: Optional[str] = None) -> None:
        """Increment the positive counter."""
        self._p.increment(amount=amount, node_id=node_id)

    def decrement(self, amount: int = 1, node_id: Optional[str] = None) -> None:
        """Increment the negative counter (effectively decrementing)."""
        self._n.increment(amount=amount, node_id=node_id)

    def value(self) -> int:
        """Return P - N."""
        return self._p.value() - self._n.value()

    def merge(self, other: PNCounter) -> PNCounter:
        """Merge with another PNCounter."""
        result = PNCounter(node_id=self._node_id)
        result._p = self._p.merge(other._p)
        result._n = self._n.merge(other._n)
        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PNCounter):
            return NotImplemented
        return self._p == other._p and self._n == other._n

    def __repr__(self) -> str:
        return f"PNCounter(value={self.value()}, P={self._p.value()}, N={self._n.value()})"


# =====================================================================
# LWWRegister — Last-Writer-Wins Register
# =====================================================================

class LWWRegister:
    """Last-Writer-Wins Register CRDT.

    Stores a single value with a timestamp. Merge keeps the value
    with the highest timestamp. In case of tie, the value from the
    node with the lexicographically higher ID wins, because
    alphabetical superiority is a valid conflict resolution strategy
    in distributed systems.
    """

    def __init__(
        self,
        node_id: str = "",
        value: Any = None,
        timestamp: float = 0.0,
    ) -> None:
        self._node_id = node_id
        self._value = value
        self._timestamp = timestamp

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def value(self) -> Any:
        return self._value

    @property
    def timestamp(self) -> float:
        return self._timestamp

    def set(self, value: Any, timestamp: Optional[float] = None) -> None:
        """Set the register value with a timestamp."""
        ts = timestamp if timestamp is not None else time.monotonic()
        if ts >= self._timestamp:
            self._value = value
            self._timestamp = ts

    def merge(self, other: LWWRegister) -> LWWRegister:
        """Merge: keep the value with the higher timestamp."""
        if other._timestamp > self._timestamp:
            return LWWRegister(
                node_id=self._node_id,
                value=other._value,
                timestamp=other._timestamp,
            )
        elif other._timestamp == self._timestamp:
            # Tiebreak by node_id
            if other._node_id > self._node_id:
                return LWWRegister(
                    node_id=self._node_id,
                    value=other._value,
                    timestamp=other._timestamp,
                )
        return LWWRegister(
            node_id=self._node_id,
            value=self._value,
            timestamp=self._timestamp,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LWWRegister):
            return NotImplemented
        return self._value == other._value and self._timestamp == other._timestamp

    def __repr__(self) -> str:
        return f"LWWRegister(value={self._value!r}, ts={self._timestamp:.6f})"


# =====================================================================
# MVRegister — Multi-Value Register
# =====================================================================

class MVRegister:
    """Multi-Value Register CRDT.

    Preserves all concurrent writes as multiple values. Each value
    is tagged with the vector clock at the time of writing. On merge,
    values that are dominated (happened-before) are discarded; concurrent
    values are all retained.

    This is the CRDT equivalent of "I don't know which FizzBuzz result
    is correct so I'll keep all of them and let someone else decide."
    """

    def __init__(self, node_id: str = "") -> None:
        self._node_id = node_id
        # List of (value, VectorClock) pairs
        self._values: list[tuple[Any, VectorClock]] = []

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def values(self) -> list[Any]:
        """Return only the values (without clocks)."""
        return [v for v, _ in self._values]

    @property
    def values_with_clocks(self) -> list[tuple[Any, VectorClock]]:
        """Return values with their vector clocks."""
        return [(v, vc.copy()) for v, vc in self._values]

    def set(self, value: Any, clock: VectorClock) -> None:
        """Set a value with its vector clock, replacing all dominated values."""
        new_clock = clock.copy()
        new_clock.increment(self._node_id)
        self._values = [(value, new_clock)]

    def merge(self, other: MVRegister) -> MVRegister:
        """Merge: keep all concurrent values, discard dominated ones."""
        result = MVRegister(node_id=self._node_id)
        all_entries = self._values + other._values

        # Keep only entries that are not dominated by any other entry
        survivors: list[tuple[Any, VectorClock]] = []
        for i, (val_i, vc_i) in enumerate(all_entries):
            dominated = False
            for j, (val_j, vc_j) in enumerate(all_entries):
                if i != j and vc_i.happened_before(vc_j):
                    dominated = True
                    break
            if not dominated:
                # Deduplicate identical entries
                is_dup = False
                for sv, svc in survivors:
                    if sv == val_i and vc_i == svc:
                        is_dup = True
                        break
                if not is_dup:
                    survivors.append((val_i, vc_i.copy()))

        result._values = survivors
        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MVRegister):
            return NotImplemented
        if len(self._values) != len(other._values):
            return False
        for (v1, vc1), (v2, vc2) in zip(
            sorted(self._values, key=lambda x: repr(x)),
            sorted(other._values, key=lambda x: repr(x)),
        ):
            if v1 != v2 or vc1 != vc2:
                return False
        return True

    def __repr__(self) -> str:
        vals = [repr(v) for v in self.values]
        return f"MVRegister(values={vals})"


# =====================================================================
# ORSet — Observed-Remove Set
# =====================================================================

class ORSet:
    """Observed-Remove Set CRDT with add-wins semantics.

    Each element is tagged with a unique identifier on add. Remove
    only removes the tags that were observed at the time of removal.
    If an add and remove are concurrent, the add wins — because in
    the FizzBuzz universe, existence triumphs over annihilation.
    """

    def __init__(self, node_id: str = "") -> None:
        self._node_id = node_id
        # element -> set of unique tags
        self._elements: dict[Any, set[str]] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    def _generate_tag(self) -> str:
        """Generate a globally unique tag for an element."""
        return f"{self._node_id}:{uuid.uuid4().hex[:12]}"

    def add(self, element: Any) -> None:
        """Add an element with a unique tag."""
        tag = self._generate_tag()
        if element not in self._elements:
            self._elements[element] = set()
        self._elements[element].add(tag)

    def remove(self, element: Any) -> None:
        """Remove an element by clearing all its observed tags."""
        if element in self._elements:
            self._elements[element] = set()
            # Clean up empty entries
            if not self._elements[element]:
                del self._elements[element]

    def contains(self, element: Any) -> bool:
        """Check if an element is in the set (has at least one tag)."""
        return element in self._elements and len(self._elements[element]) > 0

    def elements(self) -> set[Any]:
        """Return all elements currently in the set."""
        return {e for e, tags in self._elements.items() if tags}

    def merge(self, other: ORSet) -> ORSet:
        """Merge with another ORSet (union of tags per element = add-wins)."""
        result = ORSet(node_id=self._node_id)
        all_elements = set(self._elements.keys()) | set(other._elements.keys())
        for elem in all_elements:
            tags = set()
            if elem in self._elements:
                tags |= self._elements[elem]
            if elem in other._elements:
                tags |= other._elements[elem]
            if tags:
                result._elements[elem] = tags
        return result

    def __len__(self) -> int:
        return len(self.elements())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ORSet):
            return NotImplemented
        return self.elements() == other.elements()

    def __repr__(self) -> str:
        return f"ORSet({self.elements()})"


# =====================================================================
# LWWMap — Last-Writer-Wins Map
# =====================================================================

class LWWMap:
    """LWW-Element-Map CRDT.

    A dictionary where each key maps to an LWWRegister. Merge is
    performed per-key using the LWWRegister merge semantics.

    Perfect for storing FizzBuzz configuration across replicas,
    where "the last person to change the divisor wins" is a
    perfectly reasonable conflict resolution policy.
    """

    def __init__(self, node_id: str = "") -> None:
        self._node_id = node_id
        self._entries: dict[str, LWWRegister] = {}
        # Track removes with timestamps for proper merge
        self._tombstones: dict[str, float] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    def set(self, key: str, value: Any, timestamp: Optional[float] = None) -> None:
        """Set a key-value pair."""
        ts = timestamp if timestamp is not None else time.monotonic()
        reg = LWWRegister(node_id=self._node_id, value=value, timestamp=ts)
        existing = self._entries.get(key)
        if existing is None or ts >= existing.timestamp:
            self._entries[key] = reg
            # Remove tombstone if set is newer
            if key in self._tombstones and ts >= self._tombstones[key]:
                del self._tombstones[key]

    def remove(self, key: str, timestamp: Optional[float] = None) -> None:
        """Remove a key with a timestamp."""
        ts = timestamp if timestamp is not None else time.monotonic()
        self._tombstones[key] = ts
        if key in self._entries and ts >= self._entries[key].timestamp:
            del self._entries[key]

    def get(self, key: str) -> Optional[Any]:
        """Get the value for a key, or None if not present."""
        reg = self._entries.get(key)
        return reg.value if reg is not None else None

    def keys(self) -> set[str]:
        """Return all active keys."""
        return set(self._entries.keys())

    def items(self) -> list[tuple[str, Any]]:
        """Return all active key-value pairs."""
        return [(k, reg.value) for k, reg in self._entries.items()]

    def merge(self, other: LWWMap) -> LWWMap:
        """Merge with another LWWMap."""
        result = LWWMap(node_id=self._node_id)

        # Merge entries
        all_keys = set(self._entries.keys()) | set(other._entries.keys())
        for key in all_keys:
            self_reg = self._entries.get(key)
            other_reg = other._entries.get(key)
            if self_reg is not None and other_reg is not None:
                result._entries[key] = self_reg.merge(other_reg)
            elif self_reg is not None:
                result._entries[key] = LWWRegister(
                    node_id=self._node_id,
                    value=self_reg.value,
                    timestamp=self_reg.timestamp,
                )
            else:
                result._entries[key] = LWWRegister(
                    node_id=self._node_id,
                    value=other_reg.value,
                    timestamp=other_reg.timestamp,
                )

        # Merge tombstones (keep latest per key)
        all_tomb_keys = set(self._tombstones.keys()) | set(other._tombstones.keys())
        for key in all_tomb_keys:
            ts = max(
                self._tombstones.get(key, 0.0),
                other._tombstones.get(key, 0.0),
            )
            result._tombstones[key] = ts

        # Apply tombstones: if tombstone timestamp >= entry timestamp, remove entry
        for key in list(result._entries.keys()):
            if key in result._tombstones:
                if result._tombstones[key] >= result._entries[key].timestamp:
                    del result._entries[key]

        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LWWMap):
            return NotImplemented
        if set(self._entries.keys()) != set(other._entries.keys()):
            return False
        for k in self._entries:
            if self._entries[k] != other._entries[k]:
                return False
        return True

    def __repr__(self) -> str:
        items = {k: reg.value for k, reg in self._entries.items()}
        return f"LWWMap({items})"


# =====================================================================
# RGA — Replicated Growable Array
# =====================================================================

@dataclass
class RGANode:
    """A node in the RGA linked structure."""
    value: Any
    timestamp: float
    node_id: str
    unique_id: str
    tombstone: bool = False

    def ordering_key(self) -> tuple[float, str]:
        """Return the key used for ordering concurrent inserts."""
        return (self.timestamp, self.node_id)


class RGA:
    """Replicated Growable Array CRDT.

    A sequence CRDT where concurrent inserts at the same position are
    ordered by (timestamp, node_id) tiebreak. Uses Lamport timestamps
    for global ordering. Delete marks nodes as tombstones rather than
    removing them, preserving the causal structure.

    This data structure ensures that if two replicas concurrently decide
    to insert "Fizz" at position 3, the resulting order is deterministic
    across all replicas, even though neither replica has any idea what
    the other was doing.
    """

    def __init__(self, node_id: str = "") -> None:
        self._node_id = node_id
        self._nodes: list[RGANode] = []
        self._lamport_clock: float = 0.0
        # Index by unique_id for O(1) lookup during merge
        self._id_index: dict[str, int] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    def _next_timestamp(self) -> float:
        """Generate the next Lamport timestamp."""
        self._lamport_clock += 1.0
        return self._lamport_clock

    def _rebuild_index(self) -> None:
        """Rebuild the unique_id -> index mapping."""
        self._id_index = {n.unique_id: i for i, n in enumerate(self._nodes)}

    def insert(self, index: int, value: Any) -> str:
        """Insert a value at the given index. Returns the unique ID."""
        ts = self._next_timestamp()
        uid = f"{self._node_id}:{uuid.uuid4().hex[:12]}"
        node = RGANode(
            value=value,
            timestamp=ts,
            node_id=self._node_id,
            unique_id=uid,
        )
        # Clamp index to valid range (considering visible positions)
        visible = self._visible_indices()
        if index >= len(visible):
            # Append at end
            self._nodes.append(node)
        elif index <= 0:
            # Insert at beginning: find the position before the first visible
            if visible:
                self._nodes.insert(visible[0], node)
            else:
                self._nodes.append(node)
        else:
            # Insert after the visible[index-1] node
            insert_pos = visible[index - 1] + 1
            self._nodes.insert(insert_pos, node)
        self._rebuild_index()
        return uid

    def append(self, value: Any) -> str:
        """Append a value at the end."""
        return self.insert(len(self.values()), value)

    def delete(self, index: int) -> None:
        """Mark the element at the visible index as a tombstone."""
        visible = self._visible_indices()
        if 0 <= index < len(visible):
            self._nodes[visible[index]].tombstone = True

    def _visible_indices(self) -> list[int]:
        """Return indices of non-tombstoned nodes."""
        return [i for i, n in enumerate(self._nodes) if not n.tombstone]

    def values(self) -> list[Any]:
        """Return the visible values in order."""
        return [n.value for n in self._nodes if not n.tombstone]

    def all_nodes(self) -> list[RGANode]:
        """Return all nodes including tombstones (for merge)."""
        return list(self._nodes)

    def merge(self, other: RGA) -> RGA:
        """Merge with another RGA.

        Combines the node lists, maintaining causal ordering. Nodes
        are sorted by their position in the document, with concurrent
        inserts at the same position ordered by (timestamp, node_id).
        """
        result = RGA(node_id=self._node_id)

        # Collect all unique nodes from both replicas
        seen: dict[str, RGANode] = {}
        for node in self._nodes:
            if node.unique_id not in seen:
                seen[node.unique_id] = RGANode(
                    value=node.value,
                    timestamp=node.timestamp,
                    node_id=node.node_id,
                    unique_id=node.unique_id,
                    tombstone=node.tombstone,
                )
            else:
                # If either side tombstoned it, it's tombstoned
                if node.tombstone:
                    seen[node.unique_id].tombstone = True

        for node in other._nodes:
            if node.unique_id not in seen:
                seen[node.unique_id] = RGANode(
                    value=node.value,
                    timestamp=node.timestamp,
                    node_id=node.node_id,
                    unique_id=node.unique_id,
                    tombstone=node.tombstone,
                )
            else:
                if node.tombstone:
                    seen[node.unique_id].tombstone = True

        # Sort by (timestamp, node_id) for deterministic ordering
        sorted_nodes = sorted(
            seen.values(),
            key=lambda n: (n.timestamp, n.node_id),
        )
        result._nodes = sorted_nodes
        result._lamport_clock = max(self._lamport_clock, other._lamport_clock)
        result._rebuild_index()
        return result

    def __len__(self) -> int:
        return len(self.values())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RGA):
            return NotImplemented
        return self.values() == other.values()

    def __repr__(self) -> str:
        return f"RGA({self.values()})"


# =====================================================================
# CRDTMergeEngine — State-based replication orchestrator
# =====================================================================

class CRDTType(Enum):
    """Enumeration of supported CRDT types."""
    G_COUNTER = "g_counter"
    PN_COUNTER = "pn_counter"
    LWW_REGISTER = "lww_register"
    MV_REGISTER = "mv_register"
    OR_SET = "or_set"
    LWW_MAP = "lww_map"
    RGA = "rga"


@dataclass
class ReplicaState:
    """State of a single replica in the merge engine."""
    replica_id: str
    crdts: dict[str, Any] = field(default_factory=dict)
    vector_clock: VectorClock = field(default_factory=lambda: VectorClock())
    merge_count: int = 0
    last_merge_time: float = 0.0


@dataclass
class MergeResult:
    """Result of a merge operation."""
    source_replica: str
    target_replica: str
    crdts_merged: int
    converged: bool
    merge_time_ms: float


class CRDTMergeEngine:
    """Orchestrates state-based merge across N replicas.

    Implements anti-entropy: periodically, replicas exchange their full
    state and merge it using the CRDT merge functions. The Strong Eventual
    Consistency guarantee ensures that after all replicas have exchanged
    state, they will converge to the same value.

    In the FizzBuzz context, this means that even if replica-A classified
    15 as "FizzBuzz" and replica-B classified it as "FizzBuzz" independently,
    they will eventually agree that it is, in fact, "FizzBuzz". Groundbreaking.
    """

    def __init__(self) -> None:
        self._replicas: dict[str, ReplicaState] = {}
        self._merge_history: list[MergeResult] = []
        self._total_merges: int = 0

    @property
    def replicas(self) -> dict[str, ReplicaState]:
        return dict(self._replicas)

    @property
    def merge_history(self) -> list[MergeResult]:
        return list(self._merge_history)

    @property
    def total_merges(self) -> int:
        return self._total_merges

    def register_replica(self, replica_id: str) -> ReplicaState:
        """Register a new replica."""
        if replica_id in self._replicas:
            return self._replicas[replica_id]
        state = ReplicaState(
            replica_id=replica_id,
            vector_clock=VectorClock(node_id=replica_id),
        )
        self._replicas[replica_id] = state
        return state

    def set_crdt(self, replica_id: str, name: str, crdt: Any) -> None:
        """Set a named CRDT on a replica."""
        if replica_id not in self._replicas:
            raise CRDTReplicaDivergenceError(
                replica_a=replica_id,
                replica_b="<engine>",
                crdt_name=name,
            )
        self._replicas[replica_id].crdts[name] = crdt
        self._replicas[replica_id].vector_clock.increment(replica_id)

    def get_crdt(self, replica_id: str, name: str) -> Optional[Any]:
        """Get a named CRDT from a replica."""
        if replica_id not in self._replicas:
            return None
        return self._replicas[replica_id].crdts.get(name)

    def merge_replicas(self, source_id: str, target_id: str) -> MergeResult:
        """Merge state from source into target replica."""
        if source_id not in self._replicas:
            raise CRDTReplicaDivergenceError(
                replica_a=source_id,
                replica_b=target_id,
                crdt_name="<all>",
            )
        if target_id not in self._replicas:
            raise CRDTReplicaDivergenceError(
                replica_a=source_id,
                replica_b=target_id,
                crdt_name="<all>",
            )

        start = time.monotonic()
        source = self._replicas[source_id]
        target = self._replicas[target_id]

        crdts_merged = 0
        all_names = set(source.crdts.keys()) | set(target.crdts.keys())

        for name in all_names:
            source_crdt = source.crdts.get(name)
            target_crdt = target.crdts.get(name)

            if source_crdt is not None and target_crdt is not None:
                # Both have it — merge
                try:
                    merged = target_crdt.merge(source_crdt)
                    target.crdts[name] = merged
                    crdts_merged += 1
                except Exception as e:
                    raise CRDTMergeConflictError(
                        crdt_type=type(target_crdt).__name__,
                        detail=str(e),
                    )
            elif source_crdt is not None:
                # Only source has it — copy to target
                target.crdts[name] = copy.deepcopy(source_crdt)
                crdts_merged += 1

        # Merge vector clocks
        target.vector_clock = target.vector_clock.merge(source.vector_clock)
        target.vector_clock.increment(target_id)
        target.merge_count += 1
        target.last_merge_time = time.monotonic()

        elapsed_ms = (time.monotonic() - start) * 1000
        self._total_merges += 1

        result = MergeResult(
            source_replica=source_id,
            target_replica=target_id,
            crdts_merged=crdts_merged,
            converged=self._check_convergence(source_id, target_id),
            merge_time_ms=elapsed_ms,
        )
        self._merge_history.append(result)
        return result

    def full_sync(self) -> list[MergeResult]:
        """Perform a full anti-entropy round: merge all pairs."""
        results = []
        replica_ids = list(self._replicas.keys())
        for i in range(len(replica_ids)):
            for j in range(len(replica_ids)):
                if i != j:
                    results.append(
                        self.merge_replicas(replica_ids[i], replica_ids[j])
                    )
        return results

    def _check_convergence(self, replica_a: str, replica_b: str) -> bool:
        """Check if two replicas have converged."""
        a = self._replicas[replica_a]
        b = self._replicas[replica_b]

        a_names = set(a.crdts.keys())
        b_names = set(b.crdts.keys())
        if a_names != b_names:
            return False

        for name in a_names:
            crdt_a = a.crdts[name]
            crdt_b = b.crdts[name]
            try:
                if crdt_a != crdt_b:
                    return False
            except (TypeError, AttributeError):
                return False
        return True

    def convergence_report(self) -> dict[str, Any]:
        """Generate a convergence report across all replicas."""
        replica_ids = list(self._replicas.keys())
        converged_pairs = 0
        total_pairs = 0
        for i in range(len(replica_ids)):
            for j in range(i + 1, len(replica_ids)):
                total_pairs += 1
                if self._check_convergence(replica_ids[i], replica_ids[j]):
                    converged_pairs += 1

        return {
            "total_replicas": len(replica_ids),
            "total_pairs": total_pairs,
            "converged_pairs": converged_pairs,
            "convergence_ratio": converged_pairs / max(total_pairs, 1),
            "total_merges": self._total_merges,
            "all_converged": converged_pairs == total_pairs,
        }


# =====================================================================
# CRDTDashboard — ASCII visualization
# =====================================================================

class CRDTDashboard:
    """ASCII dashboard for visualizing CRDT state across replicas.

    Renders a comprehensive view of all CRDTs, vector clocks,
    convergence statistics, and merge history. Because distributed
    FizzBuzz data needs to be observable.
    """

    @staticmethod
    def render(
        engine: CRDTMergeEngine,
        width: int = 60,
    ) -> str:
        """Render the CRDT dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        title_line = "|" + " FizzCRDT: Conflict-Free Replicated Data Types ".center(width - 2) + "|"

        lines.append("")
        lines.append(border)
        lines.append(title_line)
        lines.append(border)

        # Convergence summary
        report = engine.convergence_report()
        lines.append("|" + " Convergence Summary ".center(width - 2, "-") + "|")
        lines.append("|" + f"  Replicas: {report['total_replicas']}".ljust(width - 2) + "|")
        lines.append("|" + f"  Converged pairs: {report['converged_pairs']}/{report['total_pairs']}".ljust(width - 2) + "|")
        ratio_pct = report['convergence_ratio'] * 100
        lines.append("|" + f"  Convergence ratio: {ratio_pct:.1f}%".ljust(width - 2) + "|")
        lines.append("|" + f"  Total merges: {report['total_merges']}".ljust(width - 2) + "|")
        status = "CONVERGED" if report['all_converged'] else "DIVERGENT"
        lines.append("|" + f"  Status: {status}".ljust(width - 2) + "|")
        lines.append(border)

        # Per-replica state
        lines.append("|" + " Replica State ".center(width - 2, "-") + "|")
        for replica_id, state in engine.replicas.items():
            lines.append("|" + f"  [{replica_id}]".ljust(width - 2) + "|")
            lines.append("|" + f"    Vector clock: {state.vector_clock}".ljust(width - 2) + "|")
            lines.append("|" + f"    CRDTs: {len(state.crdts)}".ljust(width - 2) + "|")
            lines.append("|" + f"    Merges: {state.merge_count}".ljust(width - 2) + "|")
            for name, crdt in state.crdts.items():
                crdt_type = type(crdt).__name__
                crdt_summary = _crdt_summary(crdt)
                line = f"      {name}: {crdt_type} = {crdt_summary}"
                if len(line) > width - 4:
                    line = line[:width - 7] + "..."
                lines.append("|" + line.ljust(width - 2) + "|")
        lines.append(border)

        # Merge history (last 5)
        lines.append("|" + " Recent Merges ".center(width - 2, "-") + "|")
        recent = engine.merge_history[-5:]
        if not recent:
            lines.append("|" + "  (no merges yet)".ljust(width - 2) + "|")
        for mr in recent:
            conv_str = "OK" if mr.converged else "DIVERGENT"
            line = f"  {mr.source_replica} -> {mr.target_replica}: {mr.crdts_merged} CRDTs ({conv_str}, {mr.merge_time_ms:.2f}ms)"
            if len(line) > width - 4:
                line = line[:width - 7] + "..."
            lines.append("|" + line.ljust(width - 2) + "|")
        lines.append(border)

        # Semilattice axiom reminder
        lines.append("|" + " Axioms: commutative, associative, idempotent ".center(width - 2) + "|")
        lines.append("|" + " Strong Eventual Consistency: guaranteed.     ".center(width - 2) + "|")
        lines.append(border)
        lines.append("")

        return "\n".join(lines)


def _crdt_summary(crdt: Any) -> str:
    """Generate a short summary string for a CRDT value."""
    if isinstance(crdt, GCounter):
        return str(crdt.value())
    elif isinstance(crdt, PNCounter):
        return str(crdt.value())
    elif isinstance(crdt, LWWRegister):
        return repr(crdt.value)
    elif isinstance(crdt, MVRegister):
        return repr(crdt.values)
    elif isinstance(crdt, ORSet):
        elems = crdt.elements()
        if len(elems) > 5:
            return f"{{{len(elems)} elements}}"
        return repr(elems)
    elif isinstance(crdt, LWWMap):
        keys = crdt.keys()
        if len(keys) > 5:
            return f"{{{len(keys)} keys}}"
        return repr(dict(crdt.items()))
    elif isinstance(crdt, RGA):
        vals = crdt.values()
        if len(vals) > 5:
            return f"[{len(vals)} elements]"
        return repr(vals)
    return repr(crdt)


# =====================================================================
# CRDTMiddleware — IMiddleware for replicating classification state
# =====================================================================

class CRDTMiddleware(IMiddleware):
    """Middleware that replicates FizzBuzz classification state via CRDTs.

    Creates an LWWRegister per evaluation, replicating the classification
    result across N simulated replicas. On each evaluation, the middleware:
    1. Writes the classification to each replica's LWWRegister
    2. Runs anti-entropy merge across all replicas
    3. Verifies convergence

    This ensures that every FizzBuzz classification achieves Strong
    Eventual Consistency across the cluster, which is absolutely
    necessary for a single-process CLI tool.
    """

    def __init__(
        self,
        engine: CRDTMergeEngine,
        replica_count: int = 3,
    ) -> None:
        self._engine = engine
        self._replica_count = replica_count
        self._evaluation_count = 0
        self._convergence_failures = 0

        # Register replicas
        self._replica_ids: list[str] = []
        for i in range(replica_count):
            rid = f"fizz-node-{i}"
            self._engine.register_replica(rid)
            self._replica_ids.append(rid)

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    @property
    def convergence_failures(self) -> int:
        return self._convergence_failures

    def get_name(self) -> str:
        """Return the middleware's identifier."""
        return "CRDTMiddleware"

    def get_priority(self) -> int:
        """Return the middleware's execution priority."""
        return 870

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process: replicate classification state via LWWRegister."""
        result = next_handler(context)

        self._evaluation_count += 1

        # Extract classification from results
        classification = "unknown"
        if result.results:
            classification = result.results[-1].output

        # Write to all replicas with slightly different timestamps
        # to simulate network delay
        crdt_name = f"eval_{context.number}"
        base_ts = time.monotonic()
        for i, rid in enumerate(self._replica_ids):
            reg = LWWRegister(
                node_id=rid,
                value=classification,
                timestamp=base_ts + i * 0.0001,
            )
            self._engine.set_crdt(rid, crdt_name, reg)

        # Also maintain running counters
        counter_name = f"count_{classification}"
        for rid in self._replica_ids:
            existing = self._engine.get_crdt(rid, counter_name)
            if existing is None:
                existing = GCounter(node_id=rid)
            existing.increment(node_id=rid)
            self._engine.set_crdt(rid, counter_name, existing)

        # Anti-entropy: merge all replicas
        for i in range(len(self._replica_ids)):
            for j in range(len(self._replica_ids)):
                if i != j:
                    try:
                        merge_result = self._engine.merge_replicas(
                            self._replica_ids[i],
                            self._replica_ids[j],
                        )
                        if not merge_result.converged:
                            self._convergence_failures += 1
                    except CRDTMergeConflictError:
                        self._convergence_failures += 1

        # Tag context metadata
        result.metadata["crdt_replicas"] = self._replica_count
        result.metadata["crdt_convergence_failures"] = self._convergence_failures

        return result

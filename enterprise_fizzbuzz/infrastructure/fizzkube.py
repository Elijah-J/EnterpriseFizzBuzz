"""
Enterprise FizzBuzz Platform - FizzKube Container Orchestration Module

Implements a Kubernetes-inspired container orchestration system for
scheduling FizzBuzz evaluations across simulated worker nodes. Every
evaluation becomes a Pod with a full lifecycle (Pending -> Running ->
Succeeded), worker nodes have resource capacities measured in milliFizz
CPU and FizzBytes memory, a scheduler filters and scores nodes,
ReplicaSets maintain desired pod counts, and a Horizontal Pod
Autoscaler adjusts replica counts based on CPU utilization.

The fact that each pod's workload is a single modulo operation that
completes in microseconds is, of course, completely beside the point.
If Google needs Kubernetes to serve search results, surely we need
container orchestration for n % 3 == 0. The architecture diagrams
are indistinguishable from a production cluster — provided you don't
look at what the pods are actually doing.

Resource Units:
  - milliFizz (mF): 1/1000th of a FizzCore. A standard FizzBuzz pod
    requests 100mF, which is 10% of a FizzCore. Enterprise-grade
    modulo arithmetic demands precision resource accounting.
  - FizzBytes (FB): The fundamental unit of FizzBuzz memory. A standard
    pod requests 128 FB, because even n % 3 needs a generous memory
    allocation. Overcommitting FizzBytes leads to OOMFizzKilled.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    EtcdKeyNotFoundError,
    FizzKubeError,
    HPAScalingError,
    NodeNotReadyError,
    PodSchedulingError,
    ResourceQuotaExceededError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)


# ── Enumerations ──────────────────────────────────────────────────


class PodPhase(Enum):
    """Lifecycle phases for a FizzKube Pod.

    Mirrors the Kubernetes pod lifecycle with the same gravitas, despite
    the fact that each pod's entire existence lasts approximately the
    time it takes for light to cross a conference room. PENDING pods
    wait in the scheduling queue — an ordeal that takes microseconds
    but is logged with millisecond precision. RUNNING pods are actively
    computing n % d, which is the computational equivalent of breathing.
    SUCCEEDED pods have completed their sacred duty. FAILED pods have
    somehow managed to fail at modulo arithmetic, which is impressive
    in its own right.
    """

    PENDING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()


class NodeCondition(Enum):
    """Health conditions for a FizzKube worker node.

    READY: The node is healthy and accepting pods. This is the expected
        state for an in-memory Python object that has no disk, no network,
        and no actual hardware to malfunction.
    NOT_READY: The node has been marked unhealthy. This is entirely
        simulated, because Python dicts do not experience hardware failures.
    DISK_PRESSURE: The node is running low on disk space. There is no
        disk. The pressure is philosophical.
    MEMORY_PRESSURE: The node is running low on memory. The memory in
        question is measured in FizzBytes, which are backed by exactly
        zero actual bytes of RAM reservation.
    PID_PRESSURE: The node has too many processes. The processes are
        pods. The pods are dict entries. The pressure is aspirational.
    """

    READY = auto()
    NOT_READY = auto()
    DISK_PRESSURE = auto()
    MEMORY_PRESSURE = auto()
    PID_PRESSURE = auto()


# ── Data Classes ──────────────────────────────────────────────────


@dataclass
class ResourceUnits:
    """Resource quantities in the FizzKube resource model.

    Attributes:
        cpu_millifizz: CPU allocation in milliFizz (mF). 1000mF = 1 FizzCore.
            A single modulo operation requires approximately 0.001mF of
            actual computation, but we allocate 100mF per pod because
            enterprise resource planning demands generous margins.
        memory_fizzbytes: Memory allocation in FizzBytes (FB). A FizzBuzz
            result is approximately 10 bytes, but we allocate 128 FB per
            pod because memory is cheap (especially imaginary memory).
    """

    cpu_millifizz: int = 0
    memory_fizzbytes: int = 0

    def fits_in(self, capacity: ResourceUnits) -> bool:
        """Check if this resource request fits within the given capacity."""
        return (
            self.cpu_millifizz <= capacity.cpu_millifizz
            and self.memory_fizzbytes <= capacity.memory_fizzbytes
        )

    def __add__(self, other: ResourceUnits) -> ResourceUnits:
        return ResourceUnits(
            cpu_millifizz=self.cpu_millifizz + other.cpu_millifizz,
            memory_fizzbytes=self.memory_fizzbytes + other.memory_fizzbytes,
        )

    def __sub__(self, other: ResourceUnits) -> ResourceUnits:
        return ResourceUnits(
            cpu_millifizz=self.cpu_millifizz - other.cpu_millifizz,
            memory_fizzbytes=self.memory_fizzbytes - other.memory_fizzbytes,
        )


@dataclass
class PodSpec:
    """Specification for a FizzKube Pod.

    The PodSpec defines what a pod needs to run: resource requests,
    resource limits, the namespace it belongs to, and the number it
    will evaluate. In real Kubernetes, a PodSpec might reference
    container images, volumes, environment variables, and init
    containers. Here, it specifies how many imaginary CPU millicores
    to reserve for a modulo operation. Progress.

    Attributes:
        cpu_request: CPU requested in milliFizz.
        cpu_limit: CPU limit in milliFizz.
        memory_request: Memory requested in FizzBytes.
        memory_limit: Memory limit in FizzBytes.
        namespace: The namespace this pod belongs to.
        number: The sacred number to be evaluated.
    """

    cpu_request: int = 100
    cpu_limit: int = 200
    memory_request: int = 128
    memory_limit: int = 256
    namespace: str = "fizzbuzz-production"
    number: int = 0

    @property
    def requests(self) -> ResourceUnits:
        return ResourceUnits(
            cpu_millifizz=self.cpu_request,
            memory_fizzbytes=self.memory_request,
        )

    @property
    def limits(self) -> ResourceUnits:
        return ResourceUnits(
            cpu_millifizz=self.cpu_limit,
            memory_fizzbytes=self.memory_limit,
        )


@dataclass
class Pod:
    """A FizzKube Pod — the atomic unit of FizzBuzz scheduling.

    Each Pod represents a single FizzBuzz evaluation, complete with a
    unique name, a full lifecycle state machine, resource requests, and
    a creation timestamp. The pod name follows the Kubernetes convention
    of <deployment>-<random-suffix>, except the deployment is always
    'fizzbuzz-eval' and the suffix is a UUID fragment, because even
    ephemeral modulo operations deserve globally unique identifiers.

    Attributes:
        name: Unique pod identifier (e.g. 'fizzbuzz-eval-a1b2c3d4').
        phase: Current lifecycle phase (Pending -> Running -> Succeeded/Failed).
        spec: The PodSpec defining resource requirements and target number.
        node_name: The worker node this pod is scheduled to (None if Pending).
        created_at: When the pod was created (UTC).
        started_at: When the pod entered the Running phase.
        finished_at: When the pod entered Succeeded or Failed.
        result: The FizzBuzz evaluation result (populated on success).
        execution_time_ns: How long the evaluation took in nanoseconds.
    """

    name: str = ""
    phase: PodPhase = PodPhase.PENDING
    spec: PodSpec = field(default_factory=PodSpec)
    node_name: Optional[str] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[str] = None
    execution_time_ns: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            suffix = uuid.uuid4().hex[:8]
            self.name = f"fizzbuzz-eval-{suffix}"


@dataclass
class WorkerNode:
    """A FizzKube worker node — a simulated Kubernetes node.

    Each worker node has a fixed resource capacity, a current condition,
    and tracks which pods are running on it. In production Kubernetes,
    nodes are actual machines with CPUs, RAM, and GPUs. Here, they are
    Python objects with integer fields, but we monitor their utilization
    with the same intensity as a hyperscale cloud provider.

    Attributes:
        name: Node identifier (e.g. 'fizzkube-node-0').
        capacity: Total resource capacity of the node.
        allocated: Currently allocated resources (sum of running pod requests).
        condition: Current health condition of the node.
        pods: List of pods running on this node.
        taints: Node taints that repel pods (not yet used, but the field
            exists because Kubernetes has it and we must achieve feature parity).
    """

    name: str = ""
    capacity: ResourceUnits = field(default_factory=lambda: ResourceUnits(4000, 8192))
    allocated: ResourceUnits = field(default_factory=ResourceUnits)
    condition: NodeCondition = NodeCondition.READY
    pods: list[Pod] = field(default_factory=list)
    taints: list[str] = field(default_factory=list)

    @property
    def available(self) -> ResourceUnits:
        """Calculate available resources on this node."""
        return self.capacity - self.allocated

    @property
    def cpu_utilization_pct(self) -> float:
        """CPU utilization as a percentage."""
        if self.capacity.cpu_millifizz == 0:
            return 0.0
        return (self.allocated.cpu_millifizz / self.capacity.cpu_millifizz) * 100.0

    @property
    def memory_utilization_pct(self) -> float:
        """Memory utilization as a percentage."""
        if self.capacity.memory_fizzbytes == 0:
            return 0.0
        return (self.allocated.memory_fizzbytes / self.capacity.memory_fizzbytes) * 100.0

    def can_fit(self, requests: ResourceUnits) -> bool:
        """Check if this node can accommodate the given resource request."""
        avail = self.available
        return (
            requests.cpu_millifizz <= avail.cpu_millifizz
            and requests.memory_fizzbytes <= avail.memory_fizzbytes
        )

    def allocate(self, pod: Pod) -> None:
        """Allocate resources for a pod on this node."""
        self.allocated = self.allocated + pod.spec.requests
        self.pods.append(pod)
        pod.node_name = self.name

    def deallocate(self, pod: Pod) -> None:
        """Release resources when a pod completes or is removed."""
        self.allocated = self.allocated - pod.spec.requests
        # Clamp to zero to prevent negative resource accounting
        if self.allocated.cpu_millifizz < 0:
            self.allocated.cpu_millifizz = 0
        if self.allocated.memory_fizzbytes < 0:
            self.allocated.memory_fizzbytes = 0
        self.pods = [p for p in self.pods if p.name != pod.name]


@dataclass
class Namespace:
    """A FizzKube namespace — logical isolation for FizzBuzz workloads.

    In Kubernetes, namespaces provide scope for names and resource quotas.
    Here, a namespace provides scope for pod names within a dictionary,
    and enforces resource quotas that prevent any single team from
    monopolizing the cluster's imaginary FizzBuzz computing resources.

    Attributes:
        name: Namespace identifier.
        resource_quota: Maximum resources consumable within this namespace.
        used: Currently consumed resources.
    """

    name: str = "fizzbuzz-production"
    resource_quota: Optional[ResourceQuota] = None
    used: ResourceUnits = field(default_factory=ResourceUnits)


@dataclass
class ResourceQuota:
    """Resource quota for a FizzKube namespace.

    Defines the maximum amount of milliFizz CPU and FizzBytes memory
    that can be consumed across all pods in a namespace. Exceeding
    this quota prevents new pods from being scheduled, creating the
    enterprise-familiar experience of waiting for budget approval
    before you can run n % 3.

    Attributes:
        cpu_limit: Maximum CPU in milliFizz.
        memory_limit: Maximum memory in FizzBytes.
    """

    cpu_limit: int = 16000
    memory_limit: int = 32768

    def allows(self, current_used: ResourceUnits, additional: ResourceUnits) -> bool:
        """Check if adding these resources would exceed the quota."""
        new_cpu = current_used.cpu_millifizz + additional.cpu_millifizz
        new_mem = current_used.memory_fizzbytes + additional.memory_fizzbytes
        return new_cpu <= self.cpu_limit and new_mem <= self.memory_limit


# ── EtcdStore ─────────────────────────────────────────────────────


class EtcdStore:
    """An etcd-inspired key-value store for FizzKube cluster state.

    Implements a linearizable (it's a dict), consistent (it's a dict),
    highly available (it's in RAM) key-value store that tracks all
    cluster state including pods, nodes, namespaces, and ReplicaSets.
    Every mutation increments a global revision counter, mimicking
    etcd's MVCC revision system that enables watch notifications
    and consistent reads. The fact that this is just an OrderedDict
    with a counter is the kind of implementation detail that separates
    enterprise architecture from weekend hackathons.

    Attributes:
        _store: The actual key-value store (an OrderedDict, naturally).
        _revision: Monotonically increasing revision counter.
        _history: Record of all mutations for audit purposes.
    """

    def __init__(self) -> None:
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._revision: int = 0
        self._history: list[dict[str, Any]] = []

    @property
    def revision(self) -> int:
        """Current store revision."""
        return self._revision

    @property
    def size(self) -> int:
        """Number of keys in the store."""
        return len(self._store)

    def put(self, key: str, value: Any) -> int:
        """Set a key-value pair, returning the new revision."""
        self._revision += 1
        self._store[key] = value
        self._history.append({
            "revision": self._revision,
            "action": "PUT",
            "key": key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return self._revision

    def get(self, key: str) -> Any:
        """Get a value by key, raising EtcdKeyNotFoundError if absent."""
        if key not in self._store:
            raise EtcdKeyNotFoundError(key)
        return self._store[key]

    def get_or_default(self, key: str, default: Any = None) -> Any:
        """Get a value by key, returning default if not found."""
        return self._store.get(key, default)

    def delete(self, key: str) -> int:
        """Delete a key, returning the new revision."""
        if key in self._store:
            del self._store[key]
            self._revision += 1
            self._history.append({
                "revision": self._revision,
                "action": "DELETE",
                "key": key,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return self._revision

    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys with the given prefix."""
        return [k for k in self._store if k.startswith(prefix)]

    def get_history(self) -> list[dict[str, Any]]:
        """Return the full mutation history."""
        return list(self._history)


# ── FizzKubeScheduler ─────────────────────────────────────────────


class FizzKubeScheduler:
    """Kubernetes-style pod scheduler for FizzBuzz evaluations.

    The scheduler implements a two-phase scheduling algorithm:
    1. **Filter**: Eliminate nodes that cannot run the pod (insufficient
       resources, NotReady condition, namespace quota exceeded).
    2. **Score**: Rank remaining nodes by balanced utilization, preferring
       nodes that spread the workload evenly across the cluster.

    This is the exact same algorithm used by the real Kubernetes
    default scheduler, except it runs in a single thread against a
    list of three Python objects instead of across thousands of nodes
    in a distributed system. The algorithmic complexity is O(n) where
    n is typically 3, making this perhaps the most over-engineered
    linear scan in computing history.
    """

    def __init__(
        self,
        event_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self._event_callback = event_callback
        self._schedule_count: int = 0
        self._filter_log: list[dict[str, Any]] = []
        self._score_log: list[dict[str, Any]] = []

    @property
    def schedule_count(self) -> int:
        """Total number of scheduling decisions made."""
        return self._schedule_count

    @property
    def filter_log(self) -> list[dict[str, Any]]:
        """Log of all filter decisions."""
        return list(self._filter_log)

    @property
    def score_log(self) -> list[dict[str, Any]]:
        """Log of all scoring decisions."""
        return list(self._score_log)

    def schedule(
        self,
        pod: Pod,
        nodes: list[WorkerNode],
        namespace: Optional[Namespace] = None,
    ) -> WorkerNode:
        """Schedule a pod to a worker node.

        Args:
            pod: The pod to schedule.
            nodes: Available worker nodes.
            namespace: Optional namespace with resource quota.

        Returns:
            The selected worker node.

        Raises:
            PodSchedulingError: If no node can accommodate the pod.
        """
        # Check namespace quota first
        if namespace and namespace.resource_quota:
            if not namespace.resource_quota.allows(namespace.used, pod.spec.requests):
                raise ResourceQuotaExceededError(
                    namespace.name,
                    "cpu+memory",
                    namespace.resource_quota.cpu_limit,
                    namespace.used.cpu_millifizz + pod.spec.requests.cpu_millifizz,
                )

        # Phase 1: Filter
        feasible = self._filter(pod, nodes)

        if not feasible:
            raise PodSchedulingError(
                pod.name,
                f"0/{len(nodes)} nodes are available: "
                f"all nodes failed resource or condition predicates",
            )

        # Phase 2: Score
        best_node = self._score(pod, feasible)

        # Record the decision
        self._schedule_count += 1

        self._emit_event(EventType.FIZZKUBE_POD_SCHEDULED, {
            "pod": pod.name,
            "node": best_node.name,
            "feasible_count": len(feasible),
            "total_nodes": len(nodes),
        })

        return best_node

    def _filter(self, pod: Pod, nodes: list[WorkerNode]) -> list[WorkerNode]:
        """Filter phase: eliminate nodes that cannot run the pod."""
        feasible: list[WorkerNode] = []
        filter_entry: dict[str, Any] = {
            "pod": pod.name,
            "results": [],
        }

        for node in nodes:
            # Check node condition
            if node.condition != NodeCondition.READY:
                filter_entry["results"].append({
                    "node": node.name,
                    "passed": False,
                    "reason": f"condition={node.condition.name}",
                })
                continue

            # Check resource capacity
            if not node.can_fit(pod.spec.requests):
                filter_entry["results"].append({
                    "node": node.name,
                    "passed": False,
                    "reason": (
                        f"insufficient resources: "
                        f"available={node.available.cpu_millifizz}mF/"
                        f"{node.available.memory_fizzbytes}FB, "
                        f"requested={pod.spec.requests.cpu_millifizz}mF/"
                        f"{pod.spec.requests.memory_fizzbytes}FB"
                    ),
                })
                continue

            filter_entry["results"].append({
                "node": node.name,
                "passed": True,
                "reason": "all predicates passed",
            })
            feasible.append(node)

        self._filter_log.append(filter_entry)

        self._emit_event(EventType.FIZZKUBE_SCHEDULER_FILTER, {
            "pod": pod.name,
            "feasible": len(feasible),
            "total": len(nodes),
        })

        return feasible

    def _score(self, pod: Pod, nodes: list[WorkerNode]) -> WorkerNode:
        """Score phase: rank feasible nodes by balanced utilization.

        Prefers nodes with lower utilization to spread the load evenly.
        The scoring function computes a weighted combination of CPU and
        memory utilization, then selects the node with the lowest score
        (most available resources). This is the LeastRequestedPriority
        scoring plugin from the real Kubernetes scheduler.
        """
        scored: list[tuple[WorkerNode, float]] = []
        score_entry: dict[str, Any] = {
            "pod": pod.name,
            "scores": [],
        }

        for node in nodes:
            # LeastRequestedPriority: prefer nodes with more available resources
            cpu_score = 1.0 - (node.cpu_utilization_pct / 100.0)
            mem_score = 1.0 - (node.memory_utilization_pct / 100.0)
            # Weighted average: 60% CPU, 40% memory
            score = 0.6 * cpu_score + 0.4 * mem_score

            score_entry["scores"].append({
                "node": node.name,
                "cpu_util_pct": round(node.cpu_utilization_pct, 1),
                "mem_util_pct": round(node.memory_utilization_pct, 1),
                "score": round(score, 4),
            })
            scored.append((node, score))

        self._score_log.append(score_entry)

        # Select highest score (most available resources)
        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0][0]

        self._emit_event(EventType.FIZZKUBE_SCHEDULER_SCORE, {
            "pod": pod.name,
            "winner": best.name,
            "score": round(scored[0][1], 4),
        })

        return best

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event if a callback is configured."""
        if self._event_callback:
            self._event_callback(Event(
                event_type=event_type,
                payload=payload,
                source="FizzKubeScheduler",
            ))


# ── ReplicaSet ────────────────────────────────────────────────────


class ReplicaSet:
    """Kubernetes-style ReplicaSet for maintaining desired pod counts.

    A ReplicaSet ensures that a specified number of pod replicas are
    running at any given time. If a pod fails, the ReplicaSet creates
    a replacement. If there are too many pods, it terminates the excess.
    This is the self-healing mechanism that keeps your FizzBuzz
    infrastructure resilient against the catastrophic failure mode of
    a modulo operation somehow not completing.

    The reconciliation loop runs synchronously because we are in a
    single-threaded Python CLI tool, but we log it as if it were an
    asynchronous distributed control loop because that sounds more
    enterprise.

    Attributes:
        name: ReplicaSet identifier.
        desired: Target number of running pods.
        pods: Current set of managed pods.
        generation: Monotonically increasing generation counter.
        reconciliation_count: Number of reconciliation runs.
    """

    def __init__(
        self,
        name: str = "fizzbuzz-replicaset",
        desired: int = 2,
        event_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self._name = name
        self._desired = desired
        self._pods: list[Pod] = []
        self._generation: int = 0
        self._reconciliation_count: int = 0
        self._event_callback = event_callback
        self._history: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def desired(self) -> int:
        return self._desired

    @desired.setter
    def desired(self, value: int) -> None:
        self._desired = max(0, value)
        self._generation += 1

    @property
    def current(self) -> int:
        """Number of pods in Running or Pending state."""
        return sum(
            1 for p in self._pods
            if p.phase in (PodPhase.PENDING, PodPhase.RUNNING)
        )

    @property
    def ready(self) -> int:
        """Number of pods in Succeeded state."""
        return sum(1 for p in self._pods if p.phase == PodPhase.SUCCEEDED)

    @property
    def failed(self) -> int:
        """Number of pods in Failed state."""
        return sum(1 for p in self._pods if p.phase == PodPhase.FAILED)

    @property
    def pods(self) -> list[Pod]:
        return list(self._pods)

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def reconciliation_count(self) -> int:
        return self._reconciliation_count

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def add_pod(self, pod: Pod) -> None:
        """Add a pod to the ReplicaSet."""
        self._pods.append(pod)

    def reconcile(self, pod_factory: Callable[[], Pod]) -> list[Pod]:
        """Reconcile actual state with desired state.

        If there are fewer running/pending pods than desired, create
        new ones. If there are more, mark excess as Failed (terminated).
        This is the heart of the Kubernetes reconciliation loop, distilled
        to its purest form: a comparison between two integers.

        Args:
            pod_factory: Callable that creates a new Pod.

        Returns:
            List of newly created pods (if any).
        """
        self._reconciliation_count += 1

        # Remove completed (Succeeded/Failed) pods from active tracking
        active = [
            p for p in self._pods
            if p.phase in (PodPhase.PENDING, PodPhase.RUNNING)
        ]

        diff = self._desired - len(active)
        new_pods: list[Pod] = []

        if diff > 0:
            # Scale up: create replacement pods
            for _ in range(diff):
                pod = pod_factory()
                self._pods.append(pod)
                new_pods.append(pod)
                self._history.append({
                    "action": "create",
                    "pod": pod.name,
                    "reason": "reconciliation: under desired count",
                    "generation": self._generation,
                })
        elif diff < 0:
            # Scale down: terminate excess pods
            excess = active[self._desired:]
            for pod in excess:
                pod.phase = PodPhase.FAILED
                pod.finished_at = datetime.now(timezone.utc)
                self._history.append({
                    "action": "terminate",
                    "pod": pod.name,
                    "reason": "reconciliation: over desired count",
                    "generation": self._generation,
                })

        self._emit_event(EventType.FIZZKUBE_REPLICASET_RECONCILE, {
            "replicaset": self._name,
            "desired": self._desired,
            "active": len(active),
            "created": len(new_pods),
            "terminated": max(0, -diff),
            "generation": self._generation,
        })

        return new_pods

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_callback:
            self._event_callback(Event(
                event_type=event_type,
                payload=payload,
                source="FizzKubeReplicaSet",
            ))


# ── HorizontalPodAutoscaler ──────────────────────────────────────


class HorizontalPodAutoscaler:
    """Kubernetes-style Horizontal Pod Autoscaler (HPA).

    Automatically scales the number of pod replicas based on observed
    CPU utilization. When average CPU utilization across all nodes
    exceeds the target (default 70%), the HPA increases the desired
    replica count. When utilization drops, it decreases the count.

    The scaling formula mirrors the real Kubernetes HPA:
        desired = ceil(current * (current_util / target_util))

    Bounded by min_replicas and max_replicas to prevent both
    under-provisioning (can't serve FizzBuzz!) and over-provisioning
    (too much FizzBuzz! — a problem that has never existed in the
    history of computing).

    Attributes:
        target_cpu_utilization: Target average CPU utilization (0-100).
        min_replicas: Floor for replica count.
        max_replicas: Ceiling for replica count.
        scaling_history: Record of all scaling decisions.
    """

    def __init__(
        self,
        target_cpu_utilization: int = 70,
        min_replicas: int = 1,
        max_replicas: int = 10,
        event_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self._target_cpu_utilization = target_cpu_utilization
        self._min_replicas = min_replicas
        self._max_replicas = max_replicas
        self._event_callback = event_callback
        self._scaling_history: list[dict[str, Any]] = []

    @property
    def target_cpu_utilization(self) -> int:
        return self._target_cpu_utilization

    @property
    def min_replicas(self) -> int:
        return self._min_replicas

    @property
    def max_replicas(self) -> int:
        return self._max_replicas

    @property
    def scaling_history(self) -> list[dict[str, Any]]:
        return list(self._scaling_history)

    def evaluate(
        self,
        replica_set: ReplicaSet,
        nodes: list[WorkerNode],
    ) -> Optional[int]:
        """Evaluate whether scaling is needed and apply it.

        Args:
            replica_set: The ReplicaSet to potentially scale.
            nodes: Current cluster nodes for utilization measurement.

        Returns:
            New desired replica count, or None if no change needed.
        """
        if not nodes:
            return None

        # Calculate average CPU utilization across all nodes
        total_util = sum(n.cpu_utilization_pct for n in nodes)
        avg_util = total_util / len(nodes)

        current_replicas = replica_set.desired

        # Calculate desired replicas using the Kubernetes HPA formula
        if self._target_cpu_utilization == 0:
            new_desired = current_replicas
        else:
            ratio = avg_util / self._target_cpu_utilization
            import math
            new_desired = max(1, math.ceil(current_replicas * ratio))

        # Clamp to bounds
        new_desired = max(self._min_replicas, min(self._max_replicas, new_desired))

        decision = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "avg_cpu_utilization": round(avg_util, 2),
            "target_utilization": self._target_cpu_utilization,
            "current_replicas": current_replicas,
            "computed_desired": new_desired,
            "action": "none",
        }

        if new_desired != current_replicas:
            if new_desired > current_replicas:
                decision["action"] = "scale_up"
            else:
                decision["action"] = "scale_down"

            replica_set.desired = new_desired

            self._emit_event(EventType.FIZZKUBE_HPA_SCALE, {
                "replicaset": replica_set.name,
                "from": current_replicas,
                "to": new_desired,
                "avg_cpu_utilization": round(avg_util, 2),
                "action": decision["action"],
            })
        else:
            self._emit_event(EventType.FIZZKUBE_HPA_DECISION, {
                "replicaset": replica_set.name,
                "replicas": current_replicas,
                "avg_cpu_utilization": round(avg_util, 2),
                "action": "no_change",
            })

        self._scaling_history.append(decision)

        return new_desired if new_desired != current_replicas else None

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_callback:
            self._event_callback(Event(
                event_type=event_type,
                payload=payload,
                source="FizzKubeHPA",
            ))


# ── FizzKubeControlPlane ──────────────────────────────────────────


class FizzKubeControlPlane:
    """The FizzKube control plane — orchestrating FizzBuzz at scale.

    Manages the complete lifecycle of FizzBuzz evaluation pods across
    a cluster of simulated worker nodes. The control plane:

    1. Creates worker nodes with configurable resource capacities.
    2. Maintains an etcd-backed cluster state store.
    3. Schedules pods to nodes via the FizzKubeScheduler.
    4. Evaluates FizzBuzz for each number through the pod lifecycle.
    5. Manages ReplicaSets for self-healing pod management.
    6. Runs HPA for automatic horizontal scaling.

    This is the Kubernetes API server, scheduler, controller manager,
    and kubelet all rolled into one, because separating them into
    distinct processes would require actual distributed systems
    engineering, and we're already at peak over-engineering.

    Attributes:
        etcd: The cluster state store.
        scheduler: The pod scheduler.
        replica_set: The ReplicaSet controller.
        hpa: The Horizontal Pod Autoscaler (optional).
        nodes: List of worker nodes.
        namespace: The default namespace.
        all_pods: Complete history of all pods.
    """

    def __init__(
        self,
        num_nodes: int = 3,
        cpu_per_node: int = 4000,
        memory_per_node: int = 8192,
        pod_cpu_request: int = 100,
        pod_memory_request: int = 128,
        pod_cpu_limit: int = 200,
        pod_memory_limit: int = 256,
        desired_replicas: int = 2,
        namespace_name: str = "fizzbuzz-production",
        quota_cpu: int = 16000,
        quota_memory: int = 32768,
        hpa_enabled: bool = True,
        hpa_min_replicas: int = 1,
        hpa_max_replicas: int = 10,
        hpa_target_cpu: int = 70,
        rules: Optional[list] = None,
        event_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self._event_callback = event_callback
        self._rules = rules or [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz"},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz"},
        ]

        # Pod spec defaults
        self._pod_cpu_request = pod_cpu_request
        self._pod_memory_request = pod_memory_request
        self._pod_cpu_limit = pod_cpu_limit
        self._pod_memory_limit = pod_memory_limit

        # Create etcd store
        self.etcd = EtcdStore()

        # Create scheduler
        self.scheduler = FizzKubeScheduler(event_callback=event_callback)

        # Create worker nodes
        self.nodes: list[WorkerNode] = []
        for i in range(num_nodes):
            node = WorkerNode(
                name=f"fizzkube-node-{i}",
                capacity=ResourceUnits(cpu_per_node, memory_per_node),
            )
            self.nodes.append(node)
            self.etcd.put(f"/nodes/{node.name}", {
                "capacity_cpu": cpu_per_node,
                "capacity_mem": memory_per_node,
                "condition": NodeCondition.READY.name,
            })
            self._emit_event(EventType.FIZZKUBE_NODE_ADDED, {
                "node": node.name,
                "cpu": cpu_per_node,
                "memory": memory_per_node,
            })

        # Create namespace with quota
        quota = ResourceQuota(cpu_limit=quota_cpu, memory_limit=quota_memory)
        self.namespace = Namespace(
            name=namespace_name,
            resource_quota=quota,
        )
        self.etcd.put(f"/namespaces/{namespace_name}", {
            "quota_cpu": quota_cpu,
            "quota_mem": quota_memory,
        })

        # Create ReplicaSet
        self.replica_set = ReplicaSet(
            name="fizzbuzz-replicaset",
            desired=desired_replicas,
            event_callback=event_callback,
        )

        # Create HPA
        self.hpa: Optional[HorizontalPodAutoscaler] = None
        if hpa_enabled:
            self.hpa = HorizontalPodAutoscaler(
                target_cpu_utilization=hpa_target_cpu,
                min_replicas=hpa_min_replicas,
                max_replicas=hpa_max_replicas,
                event_callback=event_callback,
            )

        # Pod tracking
        self.all_pods: list[Pod] = []
        self._evaluation_count: int = 0

    @property
    def evaluation_count(self) -> int:
        """Total number of evaluations processed."""
        return self._evaluation_count

    @property
    def total_pods_created(self) -> int:
        """Total number of pods ever created."""
        return len(self.all_pods)

    @property
    def running_pods(self) -> list[Pod]:
        """Pods currently in Running phase."""
        return [p for p in self.all_pods if p.phase == PodPhase.RUNNING]

    @property
    def succeeded_pods(self) -> list[Pod]:
        """Pods that have completed successfully."""
        return [p for p in self.all_pods if p.phase == PodPhase.SUCCEEDED]

    @property
    def failed_pods(self) -> list[Pod]:
        """Pods that have failed."""
        return [p for p in self.all_pods if p.phase == PodPhase.FAILED]

    @property
    def cluster_cpu_utilization(self) -> float:
        """Average CPU utilization across all nodes."""
        if not self.nodes:
            return 0.0
        return sum(n.cpu_utilization_pct for n in self.nodes) / len(self.nodes)

    @property
    def cluster_memory_utilization(self) -> float:
        """Average memory utilization across all nodes."""
        if not self.nodes:
            return 0.0
        return sum(n.memory_utilization_pct for n in self.nodes) / len(self.nodes)

    def _make_pod_spec(self, number: int) -> PodSpec:
        """Create a PodSpec for the given number."""
        return PodSpec(
            cpu_request=self._pod_cpu_request,
            cpu_limit=self._pod_cpu_limit,
            memory_request=self._pod_memory_request,
            memory_limit=self._pod_memory_limit,
            namespace=self.namespace.name,
            number=number,
        )

    def _evaluate_fizzbuzz(self, number: int) -> str:
        """Evaluate FizzBuzz for a number using the configured rules.

        This is the actual workload that each pod runs. It takes
        approximately 0.001ms. The scheduling overhead that precedes
        it takes approximately 1000x longer. Enterprise efficiency.

        Handles both RuleDefinition dataclass objects and raw dicts,
        because enterprise software must be polymorphically compatible
        with every representation of { divisor: int, label: str }.
        """
        def _get_attr(rule: Any, key: str, default: Any = None) -> Any:
            """Extract attribute from either a dataclass or a dict."""
            if isinstance(rule, dict):
                return rule.get(key, default)
            return getattr(rule, key, default)

        labels: list[str] = []
        for rule in sorted(self._rules, key=lambda r: _get_attr(r, "priority", 0)):
            divisor = _get_attr(rule, "divisor", 0)
            if divisor and number % divisor == 0:
                labels.append(_get_attr(rule, "label", ""))
        return "".join(labels) if labels else str(number)

    def evaluate(self, number: int) -> tuple[str, Pod]:
        """Evaluate a number through the full pod lifecycle.

        Creates a Pod, schedules it to a node, runs the evaluation,
        and transitions the pod through Pending -> Running -> Succeeded.
        Also runs HPA evaluation periodically.

        Args:
            number: The number to evaluate.

        Returns:
            Tuple of (result_string, completed_pod).
        """
        self._evaluation_count += 1

        # Create pod
        spec = self._make_pod_spec(number)
        pod = Pod(spec=spec, phase=PodPhase.PENDING)

        self.all_pods.append(pod)
        self.replica_set.add_pod(pod)

        self.etcd.put(f"/pods/{pod.name}", {
            "phase": PodPhase.PENDING.name,
            "number": number,
            "namespace": self.namespace.name,
        })

        self._emit_event(EventType.FIZZKUBE_POD_CREATED, {
            "pod": pod.name,
            "number": number,
            "cpu_request": spec.cpu_request,
            "memory_request": spec.memory_request,
        })

        # Schedule pod to a node
        try:
            node = self.scheduler.schedule(pod, self.nodes, self.namespace)
        except (PodSchedulingError, ResourceQuotaExceededError):
            # If scheduling fails, try to clean up older succeeded pods
            # from nodes to free resources (simulated garbage collection)
            self._gc_completed_pods()
            try:
                node = self.scheduler.schedule(pod, self.nodes, self.namespace)
            except (PodSchedulingError, ResourceQuotaExceededError):
                pod.phase = PodPhase.FAILED
                pod.finished_at = datetime.now(timezone.utc)
                self._emit_event(EventType.FIZZKUBE_POD_FAILED, {
                    "pod": pod.name,
                    "reason": "scheduling_failed",
                })
                return str(number), pod

        # Bind pod to node
        node.allocate(pod)
        self.namespace.used = self.namespace.used + pod.spec.requests

        # Transition to Running
        pod.phase = PodPhase.RUNNING
        pod.started_at = datetime.now(timezone.utc)

        self.etcd.put(f"/pods/{pod.name}", {
            "phase": PodPhase.RUNNING.name,
            "number": number,
            "node": node.name,
        })

        self._emit_event(EventType.FIZZKUBE_POD_RUNNING, {
            "pod": pod.name,
            "node": node.name,
        })

        # Execute the workload (the actual FizzBuzz evaluation)
        start_ns = time.perf_counter_ns()
        result = self._evaluate_fizzbuzz(number)
        elapsed_ns = time.perf_counter_ns() - start_ns

        # Transition to Succeeded
        pod.phase = PodPhase.SUCCEEDED
        pod.finished_at = datetime.now(timezone.utc)
        pod.result = result
        pod.execution_time_ns = elapsed_ns

        # Release resources
        node.deallocate(pod)
        self.namespace.used = self.namespace.used - pod.spec.requests
        # Clamp namespace used to zero
        if self.namespace.used.cpu_millifizz < 0:
            self.namespace.used.cpu_millifizz = 0
        if self.namespace.used.memory_fizzbytes < 0:
            self.namespace.used.memory_fizzbytes = 0

        self.etcd.put(f"/pods/{pod.name}", {
            "phase": PodPhase.SUCCEEDED.name,
            "number": number,
            "node": node.name,
            "result": result,
            "execution_time_ns": elapsed_ns,
        })

        self._emit_event(EventType.FIZZKUBE_POD_SUCCEEDED, {
            "pod": pod.name,
            "node": node.name,
            "result": result,
            "execution_time_ns": elapsed_ns,
        })

        # Run HPA evaluation every 5 evaluations
        if self.hpa and self._evaluation_count % 5 == 0:
            self.hpa.evaluate(self.replica_set, self.nodes)

        return result, pod

    def _gc_completed_pods(self) -> None:
        """Garbage collect completed pods from nodes to free resources.

        In real Kubernetes, completed pods are eventually garbage collected.
        Here, we do it eagerly when scheduling pressure is detected,
        because even imaginary resources deserve tidy management.
        """
        for node in self.nodes:
            completed = [
                p for p in node.pods
                if p.phase in (PodPhase.SUCCEEDED, PodPhase.FAILED)
            ]
            for pod in completed:
                node.deallocate(pod)

    def get_cluster_summary(self) -> dict[str, Any]:
        """Return a summary of cluster state for dashboard rendering."""
        return {
            "nodes": len(self.nodes),
            "total_pods": len(self.all_pods),
            "running_pods": len(self.running_pods),
            "succeeded_pods": len(self.succeeded_pods),
            "failed_pods": len(self.failed_pods),
            "evaluations": self._evaluation_count,
            "etcd_revision": self.etcd.revision,
            "etcd_keys": self.etcd.size,
            "replica_set_desired": self.replica_set.desired,
            "replica_set_reconciliations": self.replica_set.reconciliation_count,
            "cluster_cpu_util": round(self.cluster_cpu_utilization, 2),
            "cluster_mem_util": round(self.cluster_memory_utilization, 2),
            "namespace": self.namespace.name,
            "hpa_enabled": self.hpa is not None,
            "hpa_history_count": len(self.hpa.scaling_history) if self.hpa else 0,
        }

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_callback:
            self._event_callback(Event(
                event_type=event_type,
                payload=payload,
                source="FizzKubeControlPlane",
            ))


# ── FizzKubeDashboard ─────────────────────────────────────────────


class FizzKubeDashboard:
    """ASCII dashboard for FizzKube cluster visualization.

    Renders a comprehensive view of the FizzKube cluster including
    node topology with resource utilization bars, a pod status table,
    HPA scaling history, and ReplicaSet reconciliation statistics.
    All rendered in glorious ASCII art, because kubectl get pods
    deserves a terminal-native experience.
    """

    @staticmethod
    def render(
        control_plane: FizzKubeControlPlane,
        width: int = 60,
    ) -> str:
        """Render the FizzKube dashboard."""
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            truncated = text[: width - 4]
            return "| " + truncated.ljust(width - 4) + " |"

        lines: list[str] = []

        # Header
        lines.append(border)
        lines.append(center(" FIZZKUBE CONTAINER ORCHESTRATION "))
        lines.append(center("Kubernetes-Inspired Pod Scheduling"))
        lines.append(border)

        # Cluster Overview
        summary = control_plane.get_cluster_summary()
        lines.append(center("CLUSTER OVERVIEW"))
        lines.append(thin)
        lines.append(left(f"Namespace:  {summary['namespace']}"))
        lines.append(left(f"Nodes:      {summary['nodes']}"))
        lines.append(left(f"Total Pods: {summary['total_pods']}"))
        lines.append(left(
            f"  Running: {summary['running_pods']}  "
            f"Succeeded: {summary['succeeded_pods']}  "
            f"Failed: {summary['failed_pods']}"
        ))
        lines.append(left(f"Evaluations: {summary['evaluations']}"))
        lines.append(left(f"etcd revision: {summary['etcd_revision']} ({summary['etcd_keys']} keys)"))
        lines.append(left(
            f"Cluster CPU:  {summary['cluster_cpu_util']:.1f}%  "
            f"Memory: {summary['cluster_mem_util']:.1f}%"
        ))

        # Node Topology
        lines.append(thin)
        lines.append(center("NODE TOPOLOGY"))
        lines.append(thin)

        bar_width = max(10, width - 30)

        for node in control_plane.nodes:
            lines.append(left(
                f"{node.name}  [{node.condition.name}]"
            ))

            # CPU bar
            cpu_pct = node.cpu_utilization_pct
            cpu_filled = int(bar_width * cpu_pct / 100)
            cpu_bar = "#" * cpu_filled + "." * (bar_width - cpu_filled)
            lines.append(left(
                f"  CPU: [{cpu_bar}] {cpu_pct:.0f}%"
            ))

            # Memory bar
            mem_pct = node.memory_utilization_pct
            mem_filled = int(bar_width * mem_pct / 100)
            mem_bar = "#" * mem_filled + "." * (bar_width - mem_filled)
            lines.append(left(
                f"  MEM: [{mem_bar}] {mem_pct:.0f}%"
            ))

            lines.append(left(
                f"  Pods: {len(node.pods)}  "
                f"Alloc: {node.allocated.cpu_millifizz}mF / "
                f"{node.allocated.memory_fizzbytes}FB"
            ))

        # Pod Table (last 10 pods)
        lines.append(thin)
        lines.append(center("RECENT PODS (last 10)"))
        lines.append(thin)

        recent_pods = control_plane.all_pods[-10:]
        if recent_pods:
            header = f"{'POD':<25} {'PHASE':<11} {'NODE':<17} {'TIME':>6}"
            lines.append(left(header))
            lines.append(left("-" * (width - 6)))
            for pod in recent_pods:
                node_name = pod.node_name or "(pending)"
                if len(node_name) > 16:
                    node_name = node_name[:16]
                time_str = (
                    f"{pod.execution_time_ns / 1000:.0f}us"
                    if pod.execution_time_ns > 0
                    else "-"
                )
                name_display = pod.name if len(pod.name) <= 24 else pod.name[:24]
                lines.append(left(
                    f"{name_display:<25} {pod.phase.name:<11} "
                    f"{node_name:<17} {time_str:>6}"
                ))
        else:
            lines.append(left("  (no pods created yet)"))

        # ReplicaSet Status
        lines.append(thin)
        lines.append(center("REPLICASET"))
        lines.append(thin)
        rs = control_plane.replica_set
        lines.append(left(
            f"Name: {rs.name}  Desired: {rs.desired}  "
            f"Generation: {rs.generation}"
        ))
        lines.append(left(f"Reconciliations: {rs.reconciliation_count}"))

        # HPA History
        if control_plane.hpa and control_plane.hpa.scaling_history:
            lines.append(thin)
            lines.append(center("HPA SCALING HISTORY"))
            lines.append(thin)

            for entry in control_plane.hpa.scaling_history[-5:]:
                action = entry["action"]
                cpu = entry["avg_cpu_utilization"]
                current = entry["current_replicas"]
                computed = entry["computed_desired"]
                icon = {
                    "scale_up": "^",
                    "scale_down": "v",
                    "none": "=",
                }.get(action, "?")
                lines.append(left(
                    f"  [{icon}] CPU: {cpu:.1f}%  "
                    f"Replicas: {current} -> {computed}  "
                    f"({action})"
                ))
        elif control_plane.hpa:
            lines.append(thin)
            lines.append(center("HPA SCALING HISTORY"))
            lines.append(thin)
            lines.append(left("  (no scaling events yet)"))

        # Footer
        lines.append(border)
        lines.append(center(
            "Auto-scaling modulo operations since 2026."
        ))
        lines.append(border)

        return "\n".join("  " + ln for ln in lines)


# ── FizzKubeMiddleware ────────────────────────────────────────────


class FizzKubeMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through FizzKube.

    Intercepts each number in the processing pipeline and evaluates it
    as a Kubernetes-style pod — complete with pod creation, scheduler
    filtering and scoring, node binding, resource accounting, and
    lifecycle state transitions. The result is identical to what
    StandardRuleEngine would produce, but with approximately 10,000x
    more ceremony and resource-unit bookkeeping.

    Priority -11 ensures this runs very early in the middleware pipeline,
    because container orchestration must have first dibs on every number,
    before the operating system kernel (priority -10) even gets a chance.
    After all, Kubernetes runs above the kernel. Sort of.
    """

    def __init__(
        self,
        control_plane: FizzKubeControlPlane,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._control_plane = control_plane
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Route the evaluation through FizzKube pod orchestration."""
        number = context.number

        # Evaluate through the control plane
        result_str, pod = self._control_plane.evaluate(number)

        # Inject FizzKube metadata into context
        context.metadata["fizzkube_pod"] = pod.name
        context.metadata["fizzkube_node"] = pod.node_name or "(unscheduled)"
        context.metadata["fizzkube_phase"] = pod.phase.name
        context.metadata["fizzkube_execution_ns"] = pod.execution_time_ns

        # If the pod succeeded, attach the result and short-circuit
        if pod.phase == PodPhase.SUCCEEDED and pod.result is not None:
            context.results.append(FizzBuzzResult(
                number=number,
                output=result_str,
                metadata={"strategy": "fizzkube", "pod": pod.name},
            ))
            return context

        # Fallback to downstream pipeline
        return next_handler(context)

    def get_name(self) -> str:
        return "FizzKubeMiddleware"

    def get_priority(self) -> int:
        return -11

"""
Enterprise FizzBuzz Platform - FizzNUMA Topology Manager

Implements a non-uniform memory access topology manager for locality-aware
FizzBuzz evaluation. In NUMA architectures, memory access latency depends
on the physical proximity of the CPU to the memory controller servicing
the request. A naive FizzBuzz implementation that ignores NUMA topology
risks remote memory accesses that can double latency and halve throughput.

The FizzNUMA subsystem models the complete NUMA hierarchy:

    NUMATopology
        ├── NUMANode                (memory + CPUs on a single socket)
        │     ├── MemoryZone        (local memory capacity and allocation)
        │     └── CPUSet            (logical CPUs attached to this node)
        ├── DistanceMatrix          (inter-node latency in abstract units)
        │     ├── Self-distance     (always 10, per ACPI SLIT convention)
        │     └── Cross-distance    (20+ for remote, 40+ for 2-hop)
        ├── PlacementPolicy         (bind, interleave, preferred, default)
        │     ├── BindPolicy        (strict local allocation)
        │     ├── InterleavePolicy  (round-robin across nodes)
        │     └── PreferredPolicy   (soft affinity with fallback)
        ├── AffinityManager         (CPU-to-node binding for vCPUs/threads)
        ├── MigrationEngine         (cross-node page migration with cost)
        └── NUMADashboard           (ASCII topology visualization)

By modeling NUMA topology, the platform can place FizzBuzz evaluation
threads on the optimal node, minimizing remote memory latency and
maximizing throughput per socket.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZNUMA_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 251

MAX_NODES = 64
MAX_CPUS_PER_NODE = 128
DEFAULT_LOCAL_DISTANCE = 10
DEFAULT_REMOTE_DISTANCE = 20
PAGE_SIZE = 4096


# ============================================================================
# Enums
# ============================================================================

class PlacementPolicyType(Enum):
    """Memory placement policies for NUMA-aware allocation."""
    BIND = "bind"
    INTERLEAVE = "interleave"
    PREFERRED = "preferred"
    DEFAULT = "default"


class MigrationStatus(Enum):
    """Status of a cross-node page migration operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class MemoryZone:
    """A memory zone within a NUMA node.

    Each zone tracks total capacity, current allocation, and page-level
    allocation records for fine-grained placement control.
    """
    total_pages: int
    allocated_pages: int = 0
    allocations: dict[str, int] = field(default_factory=dict)

    @property
    def free_pages(self) -> int:
        return self.total_pages - self.allocated_pages

    def allocate(self, tag: str, pages: int) -> bool:
        if pages > self.free_pages:
            return False
        self.allocated_pages += pages
        self.allocations[tag] = self.allocations.get(tag, 0) + pages
        return True

    def free(self, tag: str) -> int:
        pages = self.allocations.pop(tag, 0)
        self.allocated_pages -= pages
        return pages


@dataclass
class MigrationRecord:
    """Record of a cross-node page migration."""
    src_node: int
    dst_node: int
    pages: int
    cost: float
    status: MigrationStatus = MigrationStatus.PENDING
    timestamp: float = 0.0


# ============================================================================
# NUMA Node
# ============================================================================

class NUMANode:
    """A single NUMA node representing a processor socket and local memory.

    Each node contains a set of logical CPUs and a memory zone. Accesses
    from CPUs on this node to local memory have the lowest latency
    (distance = 10). Cross-node accesses incur higher latency proportional
    to the inter-node distance.
    """

    def __init__(self, node_id: int, cpu_ids: list[int], memory_pages: int) -> None:
        self.node_id = node_id
        self.cpu_ids = list(cpu_ids)
        self.memory = MemoryZone(total_pages=memory_pages)
        self._access_count = 0
        self._remote_access_count = 0

    def contains_cpu(self, cpu_id: int) -> bool:
        return cpu_id in self.cpu_ids

    def record_access(self, remote: bool = False) -> None:
        self._access_count += 1
        if remote:
            self._remote_access_count += 1

    @property
    def access_count(self) -> int:
        return self._access_count

    @property
    def remote_access_count(self) -> int:
        return self._remote_access_count

    @property
    def local_ratio(self) -> float:
        if self._access_count == 0:
            return 1.0
        return 1.0 - (self._remote_access_count / self._access_count)


# ============================================================================
# Distance Matrix
# ============================================================================

class DistanceMatrix:
    """Inter-node distance matrix conforming to the ACPI SLIT specification.

    Distances are expressed in abstract units where 10 represents local
    access (same node) and higher values represent increasing latency.
    The matrix must be symmetric and reflexive (d(i,i) = 10 for all i).
    """

    def __init__(self, num_nodes: int) -> None:
        self.num_nodes = num_nodes
        self._matrix: list[list[int]] = [
            [DEFAULT_LOCAL_DISTANCE if i == j else DEFAULT_REMOTE_DISTANCE
             for j in range(num_nodes)]
            for i in range(num_nodes)
        ]

    def set_distance(self, src: int, dst: int, distance: int) -> None:
        """Set the distance between two nodes (symmetric)."""
        self._matrix[src][dst] = distance
        self._matrix[dst][src] = distance

    def get_distance(self, src: int, dst: int) -> int:
        """Get the distance between two nodes."""
        if 0 <= src < self.num_nodes and 0 <= dst < self.num_nodes:
            return self._matrix[src][dst]
        return -1

    def nearest_node(self, src: int, exclude: Optional[set[int]] = None) -> int:
        """Find the nearest node to src, optionally excluding some nodes."""
        exclude = exclude or set()
        best_node = -1
        best_dist = float("inf")
        for j in range(self.num_nodes):
            if j == src or j in exclude:
                continue
            d = self._matrix[src][j]
            if d < best_dist:
                best_dist = d
                best_node = j
        return best_node

    def validate(self) -> list[str]:
        """Validate matrix consistency. Returns list of error messages."""
        errors = []
        for i in range(self.num_nodes):
            if self._matrix[i][i] != DEFAULT_LOCAL_DISTANCE:
                errors.append(f"Node {i} self-distance is {self._matrix[i][i]}, expected {DEFAULT_LOCAL_DISTANCE}")
        for i in range(self.num_nodes):
            for j in range(i + 1, self.num_nodes):
                if self._matrix[i][j] != self._matrix[j][i]:
                    errors.append(f"Asymmetric distance: d({i},{j})={self._matrix[i][j]} != d({j},{i})={self._matrix[j][i]}")
        return errors

    def as_list(self) -> list[list[int]]:
        return [row[:] for row in self._matrix]


# ============================================================================
# Placement Policy
# ============================================================================

class PlacementPolicy:
    """Determines which NUMA node should service a memory allocation.

    Four policies are supported:
    - BIND: strict allocation on a specific node; fails if the node
      has insufficient free memory.
    - INTERLEAVE: round-robin distribution across all nodes for
      bandwidth-sensitive workloads.
    - PREFERRED: attempt allocation on the preferred node, falling
      back to others if unavailable.
    - DEFAULT: allocate on the node local to the requesting CPU.
    """

    def __init__(self, policy_type: PlacementPolicyType, preferred_node: int = 0) -> None:
        self.policy_type = policy_type
        self.preferred_node = preferred_node
        self._interleave_index = 0

    def select_node(self, nodes: list[NUMANode], requesting_cpu: int = 0) -> int:
        """Select the target node for a memory allocation."""
        if self.policy_type == PlacementPolicyType.BIND:
            return self.preferred_node

        if self.policy_type == PlacementPolicyType.INTERLEAVE:
            node_id = self._interleave_index % len(nodes)
            self._interleave_index += 1
            return node_id

        if self.policy_type == PlacementPolicyType.PREFERRED:
            node = nodes[self.preferred_node] if self.preferred_node < len(nodes) else None
            if node is not None and node.memory.free_pages > 0:
                return self.preferred_node
            # Fallback: find any node with free memory
            for n in nodes:
                if n.memory.free_pages > 0:
                    return n.node_id
            return 0

        # DEFAULT: local to requesting CPU
        for n in nodes:
            if n.contains_cpu(requesting_cpu):
                return n.node_id
        return 0


# ============================================================================
# Affinity Manager
# ============================================================================

class AffinityManager:
    """Manages CPU-to-NUMA-node affinity bindings.

    Ensures that FizzBuzz evaluation threads run on CPUs that are
    local to the memory node holding the evaluation data, minimizing
    cross-node memory traffic.
    """

    def __init__(self) -> None:
        self._bindings: dict[int, int] = {}  # cpu_id -> node_id

    def bind(self, cpu_id: int, node_id: int) -> None:
        self._bindings[cpu_id] = node_id

    def unbind(self, cpu_id: int) -> bool:
        return self._bindings.pop(cpu_id, None) is not None

    def get_node(self, cpu_id: int) -> Optional[int]:
        return self._bindings.get(cpu_id)

    def is_bound(self, cpu_id: int) -> bool:
        return cpu_id in self._bindings

    @property
    def binding_count(self) -> int:
        return len(self._bindings)


# ============================================================================
# Migration Engine
# ============================================================================

class MigrationEngine:
    """Handles cross-node page migration with cost estimation.

    When a workload migrates between NUMA nodes, its memory pages
    should follow to maintain locality. The MigrationEngine tracks
    migration costs based on the inter-node distance and page count.
    """

    def __init__(self, distance_matrix: DistanceMatrix) -> None:
        self._distance_matrix = distance_matrix
        self._history: list[MigrationRecord] = []

    def estimate_cost(self, src_node: int, dst_node: int, pages: int) -> float:
        """Estimate the migration cost in abstract units.

        Cost is proportional to the number of pages and the inter-node
        distance, reflecting the actual data transfer overhead.
        """
        distance = self._distance_matrix.get_distance(src_node, dst_node)
        return pages * (distance / DEFAULT_LOCAL_DISTANCE)

    def migrate(self, src_node: int, dst_node: int, pages: int,
                nodes: list[NUMANode]) -> MigrationRecord:
        """Execute a page migration between NUMA nodes.

        Returns a MigrationRecord with the outcome.
        """
        cost = self.estimate_cost(src_node, dst_node, pages)
        record = MigrationRecord(
            src_node=src_node,
            dst_node=dst_node,
            pages=pages,
            cost=cost,
            timestamp=time.time(),
        )

        # Check capacity
        if dst_node < len(nodes) and nodes[dst_node].memory.free_pages >= pages:
            record.status = MigrationStatus.COMPLETED
        else:
            record.status = MigrationStatus.FAILED

        self._history.append(record)
        return record

    @property
    def history(self) -> list[MigrationRecord]:
        return list(self._history)

    @property
    def total_migrations(self) -> int:
        return len(self._history)


# ============================================================================
# NUMA Topology
# ============================================================================

class NUMATopology:
    """Complete NUMA topology representation.

    Aggregates nodes, the distance matrix, placement policy, affinity
    manager, and migration engine into a coherent topology model that
    the middleware uses for locality-aware FizzBuzz evaluation.
    """

    def __init__(self, num_nodes: int = 2, cpus_per_node: int = 4,
                 memory_pages_per_node: int = 1024) -> None:
        self.nodes: list[NUMANode] = []
        cpu_id = 0
        for i in range(num_nodes):
            cpu_ids = list(range(cpu_id, cpu_id + cpus_per_node))
            self.nodes.append(NUMANode(i, cpu_ids, memory_pages_per_node))
            cpu_id += cpus_per_node

        self.distances = DistanceMatrix(num_nodes)
        self.policy = PlacementPolicy(PlacementPolicyType.DEFAULT)
        self.affinity = AffinityManager()
        self.migration = MigrationEngine(self.distances)
        self._evaluations = 0

    def evaluate_fizzbuzz(self, number: int, cpu_id: int = 0) -> str:
        """Evaluate FizzBuzz with NUMA-aware placement.

        Selects the optimal NUMA node based on the current placement
        policy and CPU affinity, performs the evaluation, and records
        access statistics.
        """
        target_node = self.policy.select_node(self.nodes, cpu_id)
        node = self.nodes[target_node] if target_node < len(self.nodes) else self.nodes[0]

        # Determine if this is a local or remote access
        is_local = node.contains_cpu(cpu_id)
        node.record_access(remote=not is_local)

        if number % 15 == 0:
            result = "FizzBuzz"
        elif number % 3 == 0:
            result = "Fizz"
        elif number % 5 == 0:
            result = "Buzz"
        else:
            result = str(number)

        self._evaluations += 1
        return result

    @property
    def total_evaluations(self) -> int:
        return self._evaluations

    @property
    def node_count(self) -> int:
        return len(self.nodes)


# ============================================================================
# Dashboard
# ============================================================================

class NUMADashboard:
    """ASCII dashboard for NUMA topology visualization."""

    @staticmethod
    def render(topology: NUMATopology, width: int = 72) -> str:
        border = "+" + "-" * (width - 2) + "+"
        title = "| FizzNUMA Topology Status".ljust(width - 1) + "|"

        lines = [border, title, border]
        lines.append(f"| {'Version:':<20} {FIZZNUMA_VERSION:<{width-24}} |")
        lines.append(f"| {'Nodes:':<20} {topology.node_count:<{width-24}} |")
        lines.append(f"| {'Evaluations:':<20} {topology.total_evaluations:<{width-24}} |")
        lines.append(f"| {'Policy:':<20} {topology.policy.policy_type.value:<{width-24}} |")
        lines.append(border)

        for node in topology.nodes:
            cpu_str = f"CPUs: {node.cpu_ids}"
            mem_str = f"Mem: {node.memory.allocated_pages}/{node.memory.total_pages}"
            lines.append(f"| Node {node.node_id}: {cpu_str:<30} {mem_str:<{width-42}} |")

        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class NUMAMiddleware(IMiddleware):
    """Pipeline middleware that evaluates FizzBuzz with NUMA awareness."""

    def __init__(self, topology: NUMATopology) -> None:
        self.topology = topology

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        result = self.topology.evaluate_fizzbuzz(number)

        context.metadata["numa_classification"] = result
        context.metadata["numa_node_count"] = self.topology.node_count
        context.metadata["numa_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizznuma"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizznuma_subsystem(
    num_nodes: int = 2,
    cpus_per_node: int = 4,
) -> tuple[NUMATopology, NUMAMiddleware]:
    """Create and configure the complete FizzNUMA subsystem.

    Args:
        num_nodes: Number of NUMA nodes in the topology.
        cpus_per_node: Number of logical CPUs per node.

    Returns:
        Tuple of (NUMATopology, NUMAMiddleware).
    """
    topology = NUMATopology(num_nodes=num_nodes, cpus_per_node=cpus_per_node)
    middleware = NUMAMiddleware(topology)

    logger.info(
        "FizzNUMA subsystem initialized: %d nodes, %d CPUs/node",
        num_nodes, cpus_per_node,
    )

    return topology, middleware

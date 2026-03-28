"""
Enterprise FizzBuzz Platform - FizzInfiniBand Fabric Simulator

Implements an InfiniBand fabric simulator for high-bandwidth, low-latency
FizzBuzz result dissemination. InfiniBand is the interconnect of choice
for high-performance computing clusters, offering sub-microsecond latency
and hundreds of gigabits per second of bandwidth per port.

The FizzInfiniBand subsystem models the full IB fabric management stack:

    IBFabric
        ├── SubnetManager          (fabric discovery, topology management)
        │     ├── SweepEngine      (periodic fabric sweep for topology changes)
        │     └── SMState          (DISCOVERING, STANDBY, MASTER)
        ├── LIDManager             (Local Identifier assignment)
        │     ├── LID range        (1-65535 for unicast)
        │     └── LID recycling    (reuse freed LIDs)
        ├── GIDManager             (Global Identifier assignment)
        │     ├── Subnet prefix    (64-bit)
        │     └── Interface ID     (64-bit, derived from port GUID)
        ├── PathRouter             (source/destination path resolution)
        │     ├── LinearForwarding (LFT-based routing tables)
        │     └── PathRecord       (src_lid, dst_lid, SL, MTU, rate)
        ├── QoSManager             (Service Level enforcement)
        │     ├── SL-to-VL mapping (16 SLs → 8 VLs)
        │     └── Bandwidth limits (per-SL traffic shaping)
        ├── PartitionManager       (P_Key isolation)
        │     ├── Default pkey     (0xFFFF, full membership)
        │     └── Custom pkeys     (limited membership)
        ├── MulticastManager       (multicast group lifecycle)
        │     ├── Create group     (MGID assignment)
        │     ├── Join/Leave       (member management)
        │     └── Routing          (multicast forwarding tables)
        └── IBDashboard            (ASCII fabric status)

Each FizzBuzz classification result can be unicast to a specific endpoint
or multicast to all interested subscribers via the IB fabric.
"""

from __future__ import annotations

import hashlib
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

FIZZINFINIBAND_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 253

MAX_LIDS = 65535
MIN_UNICAST_LID = 1
MAX_UNICAST_LID = 49151
MAX_MULTICAST_LID = 65535
MIN_MULTICAST_LID = 49152
DEFAULT_PKEY = 0xFFFF
MAX_SERVICE_LEVELS = 16
MAX_VIRTUAL_LANES = 8
DEFAULT_MTU = 4096
MAX_PORTS_PER_SWITCH = 36


# ============================================================================
# Enums
# ============================================================================

class SMState(Enum):
    """Subnet Manager operational states."""
    DISCOVERING = "discovering"
    STANDBY = "standby"
    MASTER = "master"


class PortState(Enum):
    """InfiniBand port physical states."""
    DOWN = "down"
    INIT = "init"
    ARMED = "armed"
    ACTIVE = "active"


class NodeType(Enum):
    """InfiniBand node types."""
    CA = "channel_adapter"        # Host Channel Adapter (HCA)
    SWITCH = "switch"
    ROUTER = "router"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class IBPort:
    """An InfiniBand port on a node."""
    port_num: int
    guid: str
    lid: int = 0
    gid: str = ""
    state: PortState = PortState.DOWN
    mtu: int = DEFAULT_MTU
    pkeys: list[int] = field(default_factory=lambda: [DEFAULT_PKEY])


@dataclass
class IBNode:
    """An InfiniBand node (HCA or switch)."""
    node_guid: str
    node_type: NodeType
    name: str
    ports: list[IBPort] = field(default_factory=list)

    def get_port(self, port_num: int) -> Optional[IBPort]:
        for p in self.ports:
            if p.port_num == port_num:
                return p
        return None


@dataclass
class PathRecord:
    """A resolved path between two IB endpoints."""
    src_lid: int
    dst_lid: int
    service_level: int = 0
    mtu: int = DEFAULT_MTU
    rate: int = 200  # Gbps
    hop_count: int = 1


@dataclass
class MulticastGroup:
    """An InfiniBand multicast group."""
    mgid: str
    mlid: int
    members: list[int] = field(default_factory=list)  # member LIDs
    pkey: int = DEFAULT_PKEY
    service_level: int = 0


# ============================================================================
# LID Manager
# ============================================================================

class LIDManager:
    """Manages Local Identifier assignment for the subnet.

    Each port on the fabric must be assigned a unique LID in the
    unicast range (1-49151). The LIDManager tracks assignments and
    recycles freed LIDs for reuse.
    """

    def __init__(self) -> None:
        self._next_lid = MIN_UNICAST_LID
        self._assignments: dict[str, int] = {}  # port_guid -> lid
        self._freed: list[int] = []

    def assign(self, port_guid: str) -> int:
        """Assign a LID to a port. Returns the assigned LID."""
        if port_guid in self._assignments:
            return self._assignments[port_guid]

        if self._freed:
            lid = self._freed.pop(0)
        else:
            lid = self._next_lid
            self._next_lid += 1

        self._assignments[port_guid] = lid
        return lid

    def release(self, port_guid: str) -> bool:
        lid = self._assignments.pop(port_guid, None)
        if lid is not None:
            self._freed.append(lid)
            return True
        return False

    def get_lid(self, port_guid: str) -> Optional[int]:
        return self._assignments.get(port_guid)

    @property
    def assignment_count(self) -> int:
        return len(self._assignments)


# ============================================================================
# GID Manager
# ============================================================================

class GIDManager:
    """Manages Global Identifier assignment.

    A GID is a 128-bit identifier composed of a 64-bit subnet prefix
    and a 64-bit interface ID derived from the port GUID.
    """

    def __init__(self, subnet_prefix: str = "fe80:0000:0000:0000") -> None:
        self.subnet_prefix = subnet_prefix
        self._assignments: dict[str, str] = {}

    def assign(self, port_guid: str) -> str:
        if port_guid in self._assignments:
            return self._assignments[port_guid]

        gid = f"{self.subnet_prefix}:{port_guid}"
        self._assignments[port_guid] = gid
        return gid

    def get_gid(self, port_guid: str) -> Optional[str]:
        return self._assignments.get(port_guid)

    @property
    def assignment_count(self) -> int:
        return len(self._assignments)


# ============================================================================
# Path Router
# ============================================================================

class PathRouter:
    """Resolves paths between InfiniBand endpoints.

    Uses a simple linear forwarding table to route traffic between
    source and destination LIDs. Path records include the service
    level, MTU, and rate for QoS-aware routing.
    """

    def __init__(self) -> None:
        self._forwarding_table: dict[int, dict[int, int]] = {}
        self._path_cache: dict[tuple[int, int], PathRecord] = {}

    def add_route(self, src_lid: int, dst_lid: int, next_hop_port: int = 1) -> None:
        if src_lid not in self._forwarding_table:
            self._forwarding_table[src_lid] = {}
        self._forwarding_table[src_lid][dst_lid] = next_hop_port

    def resolve_path(self, src_lid: int, dst_lid: int, sl: int = 0) -> Optional[PathRecord]:
        cache_key = (src_lid, dst_lid)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        # Check if a route exists
        if src_lid in self._forwarding_table and dst_lid in self._forwarding_table[src_lid]:
            path = PathRecord(src_lid=src_lid, dst_lid=dst_lid, service_level=sl)
            self._path_cache[cache_key] = path
            return path

        # Direct path if LIDs are known
        if src_lid > 0 and dst_lid > 0:
            path = PathRecord(src_lid=src_lid, dst_lid=dst_lid, service_level=sl)
            self._path_cache[cache_key] = path
            return path

        return None

    @property
    def route_count(self) -> int:
        return sum(len(v) for v in self._forwarding_table.values())


# ============================================================================
# QoS Manager
# ============================================================================

class QoSManager:
    """Manages Quality of Service via service level to virtual lane mapping.

    InfiniBand supports 16 Service Levels (SLs) mapped to up to 8
    Virtual Lanes (VLs). Each SL can have a bandwidth limit to
    prevent one traffic class from starving others.
    """

    def __init__(self) -> None:
        # Default: SL 0-7 map to VL 0-7, SL 8-15 map to VL 0-7
        self._sl_to_vl: dict[int, int] = {
            sl: sl % MAX_VIRTUAL_LANES for sl in range(MAX_SERVICE_LEVELS)
        }
        self._bandwidth_limits: dict[int, int] = {}  # SL -> Gbps

    def set_sl_vl_mapping(self, sl: int, vl: int) -> bool:
        if 0 <= sl < MAX_SERVICE_LEVELS and 0 <= vl < MAX_VIRTUAL_LANES:
            self._sl_to_vl[sl] = vl
            return True
        return False

    def get_vl(self, sl: int) -> int:
        return self._sl_to_vl.get(sl, 0)

    def set_bandwidth_limit(self, sl: int, gbps: int) -> None:
        self._bandwidth_limits[sl] = gbps

    def get_bandwidth_limit(self, sl: int) -> Optional[int]:
        return self._bandwidth_limits.get(sl)


# ============================================================================
# Partition Manager
# ============================================================================

class PartitionManager:
    """Manages partition keys (P_Keys) for fabric isolation.

    P_Keys provide logical isolation on the IB fabric, similar to
    VLANs in Ethernet. Only ports that share a common P_Key can
    communicate. The default P_Key (0xFFFF) grants full membership.
    """

    def __init__(self) -> None:
        self._partitions: dict[int, set[str]] = {
            DEFAULT_PKEY: set(),
        }

    def create_partition(self, pkey: int) -> bool:
        if pkey in self._partitions:
            return False
        self._partitions[pkey] = set()
        return True

    def add_member(self, pkey: int, port_guid: str) -> bool:
        partition = self._partitions.get(pkey)
        if partition is None:
            return False
        partition.add(port_guid)
        return True

    def remove_member(self, pkey: int, port_guid: str) -> bool:
        partition = self._partitions.get(pkey)
        if partition is None:
            return False
        partition.discard(port_guid)
        return True

    def can_communicate(self, pkey: int, guid_a: str, guid_b: str) -> bool:
        partition = self._partitions.get(pkey)
        if partition is None:
            return False
        return guid_a in partition and guid_b in partition

    @property
    def partition_count(self) -> int:
        return len(self._partitions)


# ============================================================================
# Multicast Manager
# ============================================================================

class MulticastManager:
    """Manages multicast group lifecycle on the IB fabric.

    Multicast enables a single FizzBuzz classification result to
    be delivered to all interested subscribers simultaneously,
    using the fabric's hardware multicast capability.
    """

    def __init__(self) -> None:
        self._groups: dict[str, MulticastGroup] = {}
        self._next_mlid = MIN_MULTICAST_LID

    def create_group(self, mgid: str, pkey: int = DEFAULT_PKEY, sl: int = 0) -> MulticastGroup:
        if mgid in self._groups:
            return self._groups[mgid]

        group = MulticastGroup(
            mgid=mgid,
            mlid=self._next_mlid,
            pkey=pkey,
            service_level=sl,
        )
        self._next_mlid += 1
        self._groups[mgid] = group
        return group

    def join_group(self, mgid: str, lid: int) -> bool:
        group = self._groups.get(mgid)
        if group is None:
            return False
        if lid not in group.members:
            group.members.append(lid)
        return True

    def leave_group(self, mgid: str, lid: int) -> bool:
        group = self._groups.get(mgid)
        if group is None:
            return False
        if lid in group.members:
            group.members.remove(lid)
            return True
        return False

    def get_group(self, mgid: str) -> Optional[MulticastGroup]:
        return self._groups.get(mgid)

    def delete_group(self, mgid: str) -> bool:
        return self._groups.pop(mgid, None) is not None

    @property
    def group_count(self) -> int:
        return len(self._groups)


# ============================================================================
# Subnet Manager
# ============================================================================

class SubnetManager:
    """InfiniBand Subnet Manager coordinating the entire fabric.

    The SM discovers fabric topology, assigns LIDs and GIDs, computes
    routing tables, and enforces QoS and partition policies. Only one
    SM is MASTER at a time; others are STANDBY.
    """

    def __init__(self) -> None:
        self.state = SMState.DISCOVERING
        self.lid_manager = LIDManager()
        self.gid_manager = GIDManager()
        self.router = PathRouter()
        self.qos = QoSManager()
        self.partitions = PartitionManager()
        self.multicast = MulticastManager()
        self._nodes: dict[str, IBNode] = {}
        self._sweeps = 0
        self._evaluations = 0

    def register_node(self, node: IBNode) -> None:
        """Register a node with the subnet manager."""
        self._nodes[node.node_guid] = node
        for port in node.ports:
            lid = self.lid_manager.assign(port.guid)
            port.lid = lid
            gid = self.gid_manager.assign(port.guid)
            port.gid = gid
            port.state = PortState.ACTIVE
            self.partitions.add_member(DEFAULT_PKEY, port.guid)

    def unregister_node(self, node_guid: str) -> bool:
        node = self._nodes.pop(node_guid, None)
        if node is None:
            return False
        for port in node.ports:
            self.lid_manager.release(port.guid)
            port.state = PortState.DOWN
        return True

    def sweep(self) -> int:
        """Perform a fabric sweep, refreshing topology information."""
        self._sweeps += 1
        active_ports = sum(
            1 for n in self._nodes.values()
            for p in n.ports if p.state == PortState.ACTIVE
        )
        if self.state == SMState.DISCOVERING and active_ports > 0:
            self.state = SMState.MASTER
        return active_ports

    def resolve_path(self, src_guid: str, dst_guid: str, sl: int = 0) -> Optional[PathRecord]:
        src_lid = self.lid_manager.get_lid(src_guid)
        dst_lid = self.lid_manager.get_lid(dst_guid)
        if src_lid is None or dst_lid is None:
            return None
        return self.router.resolve_path(src_lid, dst_lid, sl)

    def evaluate_fizzbuzz(self, number: int) -> str:
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

    def get_node(self, node_guid: str) -> Optional[IBNode]:
        return self._nodes.get(node_guid)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def total_evaluations(self) -> int:
        return self._evaluations

    @property
    def sweep_count(self) -> int:
        return self._sweeps


# ============================================================================
# Dashboard
# ============================================================================

class IBDashboard:
    """ASCII dashboard for InfiniBand fabric status."""

    @staticmethod
    def render(sm: SubnetManager, width: int = 72) -> str:
        border = "+" + "-" * (width - 2) + "+"
        title = "| FizzInfiniBand Fabric Status".ljust(width - 1) + "|"

        lines = [border, title, border]
        lines.append(f"| {'Version:':<20} {FIZZINFINIBAND_VERSION:<{width-24}} |")
        lines.append(f"| {'SM State:':<20} {sm.state.value:<{width-24}} |")
        lines.append(f"| {'Nodes:':<20} {sm.node_count:<{width-24}} |")
        lines.append(f"| {'LIDs Assigned:':<20} {sm.lid_manager.assignment_count:<{width-24}} |")
        lines.append(f"| {'Partitions:':<20} {sm.partitions.partition_count:<{width-24}} |")
        lines.append(f"| {'Multicast Groups:':<20} {sm.multicast.group_count:<{width-24}} |")
        lines.append(f"| {'Sweeps:':<20} {sm.sweep_count:<{width-24}} |")
        lines.append(f"| {'Evaluations:':<20} {sm.total_evaluations:<{width-24}} |")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class InfiniBandMiddleware(IMiddleware):
    """Pipeline middleware that evaluates FizzBuzz via InfiniBand fabric."""

    def __init__(self, sm: SubnetManager) -> None:
        self.sm = sm

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        result = self.sm.evaluate_fizzbuzz(number)

        context.metadata["ib_classification"] = result
        context.metadata["ib_sm_state"] = self.sm.state.value
        context.metadata["ib_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzinfiniband"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzinfiniband_subsystem() -> tuple[SubnetManager, InfiniBandMiddleware]:
    """Create and configure the complete FizzInfiniBand subsystem.

    Returns:
        Tuple of (SubnetManager, InfiniBandMiddleware).
    """
    sm = SubnetManager()
    sm.sweep()
    middleware = InfiniBandMiddleware(sm)

    logger.info("FizzInfiniBand subsystem initialized")

    return sm, middleware

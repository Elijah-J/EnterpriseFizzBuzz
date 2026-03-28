"""
Enterprise FizzBuzz Platform - FizzInfiniBand Fabric Simulator Test Suite

Comprehensive tests for the InfiniBand fabric simulator, covering subnet
manager operations, LID/GID assignment, path routing, QoS service levels,
partition key management, multicast groups, FizzBuzz evaluation via the
IB fabric, dashboard rendering, and middleware integration.

The FizzInfiniBand subsystem enables high-bandwidth FizzBuzz result
dissemination across the fabric. These tests verify correct fabric
management, endpoint addressing, and routing behavior.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzinfiniband import (
    DEFAULT_MTU,
    DEFAULT_PKEY,
    FIZZINFINIBAND_VERSION,
    MAX_SERVICE_LEVELS,
    MAX_VIRTUAL_LANES,
    MIDDLEWARE_PRIORITY,
    GIDManager,
    IBDashboard,
    IBNode,
    IBPort,
    InfiniBandMiddleware,
    LIDManager,
    MulticastGroup,
    MulticastManager,
    NodeType,
    PartitionManager,
    PathRecord,
    PathRouter,
    PortState,
    QoSManager,
    SMState,
    SubnetManager,
    create_fizzinfiniband_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    InfiniBandError,
    IBSubnetManagerError,
    IBLIDAssignmentError,
    IBPathRoutingError,
    IBServiceLevelError,
    IBPartitionKeyError,
    IBMulticastError,
    IBGIDError,
)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify InfiniBand constants match documented specifications."""

    def test_version(self):
        assert FIZZINFINIBAND_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 253

    def test_default_pkey(self):
        assert DEFAULT_PKEY == 0xFFFF

    def test_max_service_levels(self):
        assert MAX_SERVICE_LEVELS == 16

    def test_max_virtual_lanes(self):
        assert MAX_VIRTUAL_LANES == 8


# =========================================================================
# LID Manager
# =========================================================================


class TestLIDManager:
    """Verify Local Identifier assignment and recycling."""

    def test_assign_lid(self):
        lm = LIDManager()
        lid = lm.assign("port_guid_0")
        assert lid >= 1

    def test_assign_same_guid_returns_same_lid(self):
        lm = LIDManager()
        lid1 = lm.assign("port_guid_0")
        lid2 = lm.assign("port_guid_0")
        assert lid1 == lid2

    def test_assign_unique_lids(self):
        lm = LIDManager()
        lid1 = lm.assign("guid_0")
        lid2 = lm.assign("guid_1")
        assert lid1 != lid2

    def test_release_and_reuse(self):
        lm = LIDManager()
        lid = lm.assign("guid_0")
        lm.release("guid_0")
        lid2 = lm.assign("guid_1")
        assert lid2 == lid  # Freed LID reused

    def test_assignment_count(self):
        lm = LIDManager()
        lm.assign("guid_0")
        lm.assign("guid_1")
        assert lm.assignment_count == 2


# =========================================================================
# GID Manager
# =========================================================================


class TestGIDManager:
    """Verify Global Identifier assignment."""

    def test_assign_gid(self):
        gm = GIDManager()
        gid = gm.assign("port_guid_0")
        assert "port_guid_0" in gid

    def test_same_guid_returns_same_gid(self):
        gm = GIDManager()
        gid1 = gm.assign("guid_0")
        gid2 = gm.assign("guid_0")
        assert gid1 == gid2


# =========================================================================
# Path Router
# =========================================================================


class TestPathRouter:
    """Verify path resolution between endpoints."""

    def test_resolve_with_route(self):
        router = PathRouter()
        router.add_route(1, 2, next_hop_port=1)
        path = router.resolve_path(1, 2)
        assert path is not None
        assert path.src_lid == 1
        assert path.dst_lid == 2

    def test_resolve_direct_path(self):
        router = PathRouter()
        path = router.resolve_path(1, 3)
        assert path is not None

    def test_route_count(self):
        router = PathRouter()
        router.add_route(1, 2)
        router.add_route(1, 3)
        assert router.route_count == 2


# =========================================================================
# QoS Manager
# =========================================================================


class TestQoSManager:
    """Verify QoS service level to virtual lane mapping."""

    def test_default_mapping(self):
        qos = QoSManager()
        assert qos.get_vl(0) == 0
        assert qos.get_vl(8) == 0  # 8 % 8 = 0

    def test_set_mapping(self):
        qos = QoSManager()
        assert qos.set_sl_vl_mapping(0, 7) is True
        assert qos.get_vl(0) == 7

    def test_invalid_sl(self):
        qos = QoSManager()
        assert qos.set_sl_vl_mapping(20, 0) is False

    def test_bandwidth_limit(self):
        qos = QoSManager()
        qos.set_bandwidth_limit(0, 100)
        assert qos.get_bandwidth_limit(0) == 100


# =========================================================================
# Partition Manager
# =========================================================================


class TestPartitionManager:
    """Verify partition key management."""

    def test_create_partition(self):
        pm = PartitionManager()
        assert pm.create_partition(0x8001) is True
        assert pm.partition_count == 2  # default + new

    def test_add_member(self):
        pm = PartitionManager()
        pm.create_partition(0x8001)
        assert pm.add_member(0x8001, "guid_0") is True

    def test_can_communicate(self):
        pm = PartitionManager()
        pm.create_partition(0x8001)
        pm.add_member(0x8001, "guid_0")
        pm.add_member(0x8001, "guid_1")
        assert pm.can_communicate(0x8001, "guid_0", "guid_1") is True

    def test_cannot_communicate_different_partitions(self):
        pm = PartitionManager()
        pm.create_partition(0x8001)
        pm.create_partition(0x8002)
        pm.add_member(0x8001, "guid_0")
        pm.add_member(0x8002, "guid_1")
        assert pm.can_communicate(0x8001, "guid_0", "guid_1") is False


# =========================================================================
# Multicast Manager
# =========================================================================


class TestMulticastManager:
    """Verify multicast group lifecycle."""

    def test_create_group(self):
        mm = MulticastManager()
        group = mm.create_group("ff12::1")
        assert group.mgid == "ff12::1"
        assert mm.group_count == 1

    def test_join_and_leave(self):
        mm = MulticastManager()
        mm.create_group("ff12::1")
        assert mm.join_group("ff12::1", 1) is True
        assert mm.join_group("ff12::1", 2) is True
        group = mm.get_group("ff12::1")
        assert len(group.members) == 2
        assert mm.leave_group("ff12::1", 1) is True
        assert len(group.members) == 1

    def test_delete_group(self):
        mm = MulticastManager()
        mm.create_group("ff12::1")
        assert mm.delete_group("ff12::1") is True
        assert mm.group_count == 0


# =========================================================================
# Subnet Manager
# =========================================================================


class TestSubnetManager:
    """Verify subnet manager fabric operations."""

    def test_initial_state(self):
        sm = SubnetManager()
        assert sm.state == SMState.DISCOVERING

    def test_register_node(self):
        sm = SubnetManager()
        port = IBPort(port_num=1, guid="guid_0")
        node = IBNode(node_guid="node_0", node_type=NodeType.CA,
                      name="hca0", ports=[port])
        sm.register_node(node)
        assert sm.node_count == 1
        assert port.lid > 0
        assert port.state == PortState.ACTIVE

    def test_sweep_transitions_to_master(self):
        sm = SubnetManager()
        port = IBPort(port_num=1, guid="guid_0")
        node = IBNode(node_guid="node_0", node_type=NodeType.CA,
                      name="hca0", ports=[port])
        sm.register_node(node)
        sm.sweep()
        assert sm.state == SMState.MASTER

    def test_evaluate_fizzbuzz(self):
        sm = SubnetManager()
        assert sm.evaluate_fizzbuzz(15) == "FizzBuzz"
        assert sm.evaluate_fizzbuzz(7) == "7"


# =========================================================================
# Dashboard
# =========================================================================


class TestIBDashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_produces_output(self):
        sm = SubnetManager()
        output = IBDashboard.render(sm)
        assert "FizzInfiniBand" in output
        assert FIZZINFINIBAND_VERSION in output


# =========================================================================
# Middleware
# =========================================================================


class TestInfiniBandMiddleware:
    """Verify pipeline middleware integration."""

    def test_middleware_sets_metadata(self):
        sm = SubnetManager()
        mw = InfiniBandMiddleware(sm)

        @dataclass
        class Ctx:
            number: int
            session_id: str = "test"
            metadata: dict = None
            def __post_init__(self):
                if self.metadata is None:
                    self.metadata = {}

        ctx = Ctx(number=5)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["ib_classification"] == "Buzz"
        assert result.metadata["ib_enabled"] is True

    def test_middleware_name(self):
        sm = SubnetManager()
        mw = InfiniBandMiddleware(sm)
        assert mw.get_name() == "fizzinfiniband"

    def test_middleware_priority(self):
        sm = SubnetManager()
        mw = InfiniBandMiddleware(sm)
        assert mw.get_priority() == 253


# =========================================================================
# Factory
# =========================================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_subsystem(self):
        sm, mw = create_fizzinfiniband_subsystem()
        assert isinstance(sm, SubnetManager)
        assert isinstance(mw, InfiniBandMiddleware)


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify InfiniBand exception hierarchy."""

    def test_ib_error_base(self):
        err = InfiniBandError("test")
        assert "test" in str(err)

    def test_ib_path_routing_error(self):
        err = IBPathRoutingError(1, 2)
        assert err.src_lid == 1
        assert err.dst_lid == 2

    def test_ib_partition_key_error(self):
        err = IBPartitionKeyError(0x8001, "not found")
        assert err.pkey == 0x8001

    def test_ib_multicast_error(self):
        err = IBMulticastError("ff12::1", "group full")
        assert err.mgid == "ff12::1"

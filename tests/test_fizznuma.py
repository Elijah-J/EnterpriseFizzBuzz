"""
Enterprise FizzBuzz Platform - FizzNUMA Topology Manager Test Suite

Comprehensive tests for the NUMA topology manager, covering node creation,
distance matrix operations, memory placement policies, CPU affinity binding,
cross-node migration, FizzBuzz evaluation with NUMA awareness, dashboard
rendering, and middleware integration.

The FizzNUMA subsystem ensures that FizzBuzz evaluation threads are
scheduled on CPUs local to the memory holding the evaluation data,
minimizing cross-node latency and maximizing throughput per socket.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizznuma import (
    DEFAULT_LOCAL_DISTANCE,
    DEFAULT_REMOTE_DISTANCE,
    FIZZNUMA_VERSION,
    MIDDLEWARE_PRIORITY,
    AffinityManager,
    DistanceMatrix,
    MemoryZone,
    MigrationEngine,
    MigrationRecord,
    MigrationStatus,
    NUMADashboard,
    NUMAMiddleware,
    NUMANode,
    NUMATopology,
    PlacementPolicy,
    PlacementPolicyType,
    create_fizznuma_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    NUMAError,
    NUMANodeError,
    NUMADistanceError,
    NUMAPlacementError,
    NUMAAffinityError,
    NUMAMigrationError,
    NUMATopologyError,
)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify NUMA constants match documented specifications."""

    def test_version(self):
        assert FIZZNUMA_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 251

    def test_local_distance(self):
        assert DEFAULT_LOCAL_DISTANCE == 10

    def test_remote_distance(self):
        assert DEFAULT_REMOTE_DISTANCE == 20


# =========================================================================
# Memory Zone
# =========================================================================


class TestMemoryZone:
    """Verify per-node memory zone allocation."""

    def test_allocate(self):
        zone = MemoryZone(total_pages=100)
        assert zone.allocate("fizzbuzz", 10) is True
        assert zone.allocated_pages == 10

    def test_free_pages(self):
        zone = MemoryZone(total_pages=100)
        zone.allocate("test", 30)
        assert zone.free_pages == 70

    def test_allocate_exceeds_capacity(self):
        zone = MemoryZone(total_pages=10)
        assert zone.allocate("big", 20) is False

    def test_free_returns_pages(self):
        zone = MemoryZone(total_pages=100)
        zone.allocate("test", 10)
        freed = zone.free("test")
        assert freed == 10
        assert zone.free_pages == 100


# =========================================================================
# NUMA Node
# =========================================================================


class TestNUMANode:
    """Verify NUMA node CPU membership and access tracking."""

    def test_contains_cpu(self):
        node = NUMANode(0, [0, 1, 2, 3], 1024)
        assert node.contains_cpu(0) is True
        assert node.contains_cpu(4) is False

    def test_access_tracking(self):
        node = NUMANode(0, [0], 1024)
        node.record_access(remote=False)
        node.record_access(remote=True)
        assert node.access_count == 2
        assert node.remote_access_count == 1

    def test_local_ratio(self):
        node = NUMANode(0, [0], 1024)
        node.record_access(remote=False)
        node.record_access(remote=False)
        node.record_access(remote=True)
        assert abs(node.local_ratio - 2 / 3) < 0.01


# =========================================================================
# Distance Matrix
# =========================================================================


class TestDistanceMatrix:
    """Verify inter-node distance matrix operations."""

    def test_self_distance(self):
        dm = DistanceMatrix(4)
        for i in range(4):
            assert dm.get_distance(i, i) == DEFAULT_LOCAL_DISTANCE

    def test_remote_distance(self):
        dm = DistanceMatrix(4)
        assert dm.get_distance(0, 1) == DEFAULT_REMOTE_DISTANCE

    def test_set_distance_symmetric(self):
        dm = DistanceMatrix(4)
        dm.set_distance(0, 2, 30)
        assert dm.get_distance(0, 2) == 30
        assert dm.get_distance(2, 0) == 30

    def test_nearest_node(self):
        dm = DistanceMatrix(3)
        dm.set_distance(0, 1, 15)
        dm.set_distance(0, 2, 30)
        assert dm.nearest_node(0) == 1

    def test_validate_default(self):
        dm = DistanceMatrix(4)
        assert len(dm.validate()) == 0

    def test_out_of_bounds(self):
        dm = DistanceMatrix(2)
        assert dm.get_distance(0, 5) == -1


# =========================================================================
# Placement Policy
# =========================================================================


class TestPlacementPolicy:
    """Verify NUMA memory placement policies."""

    def test_bind_policy(self):
        nodes = [NUMANode(i, [i], 100) for i in range(4)]
        policy = PlacementPolicy(PlacementPolicyType.BIND, preferred_node=2)
        assert policy.select_node(nodes) == 2

    def test_interleave_policy(self):
        nodes = [NUMANode(i, [i], 100) for i in range(3)]
        policy = PlacementPolicy(PlacementPolicyType.INTERLEAVE)
        results = [policy.select_node(nodes) for _ in range(6)]
        assert results == [0, 1, 2, 0, 1, 2]

    def test_default_policy_uses_cpu_local(self):
        nodes = [NUMANode(0, [0, 1], 100), NUMANode(1, [2, 3], 100)]
        policy = PlacementPolicy(PlacementPolicyType.DEFAULT)
        assert policy.select_node(nodes, requesting_cpu=2) == 1


# =========================================================================
# Affinity Manager
# =========================================================================


class TestAffinityManager:
    """Verify CPU-to-node affinity binding."""

    def test_bind_and_get(self):
        am = AffinityManager()
        am.bind(0, 1)
        assert am.get_node(0) == 1

    def test_unbind(self):
        am = AffinityManager()
        am.bind(0, 1)
        assert am.unbind(0) is True
        assert am.get_node(0) is None

    def test_is_bound(self):
        am = AffinityManager()
        am.bind(0, 1)
        assert am.is_bound(0) is True
        assert am.is_bound(1) is False


# =========================================================================
# Migration Engine
# =========================================================================


class TestMigrationEngine:
    """Verify cross-node page migration."""

    def test_estimate_cost(self):
        dm = DistanceMatrix(2)
        engine = MigrationEngine(dm)
        cost = engine.estimate_cost(0, 1, 100)
        assert cost == 100 * (DEFAULT_REMOTE_DISTANCE / DEFAULT_LOCAL_DISTANCE)

    def test_migrate_success(self):
        dm = DistanceMatrix(2)
        nodes = [NUMANode(0, [0], 1000), NUMANode(1, [1], 1000)]
        engine = MigrationEngine(dm)
        record = engine.migrate(0, 1, 10, nodes)
        assert record.status == MigrationStatus.COMPLETED

    def test_migrate_failure_no_capacity(self):
        dm = DistanceMatrix(2)
        nodes = [NUMANode(0, [0], 1000), NUMANode(1, [1], 5)]
        engine = MigrationEngine(dm)
        record = engine.migrate(0, 1, 10, nodes)
        assert record.status == MigrationStatus.FAILED


# =========================================================================
# NUMA Topology
# =========================================================================


class TestNUMATopology:
    """Verify complete NUMA topology operations."""

    def test_node_count(self):
        topo = NUMATopology(num_nodes=4, cpus_per_node=2)
        assert topo.node_count == 4

    def test_evaluate_fizzbuzz_fizz(self):
        topo = NUMATopology()
        assert topo.evaluate_fizzbuzz(9) == "Fizz"

    def test_evaluate_fizzbuzz_buzz(self):
        topo = NUMATopology()
        assert topo.evaluate_fizzbuzz(10) == "Buzz"

    def test_evaluate_fizzbuzz_fizzbuzz(self):
        topo = NUMATopology()
        assert topo.evaluate_fizzbuzz(30) == "FizzBuzz"

    def test_evaluate_fizzbuzz_number(self):
        topo = NUMATopology()
        assert topo.evaluate_fizzbuzz(7) == "7"


# =========================================================================
# Dashboard
# =========================================================================


class TestNUMADashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_produces_output(self):
        topo = NUMATopology()
        output = NUMADashboard.render(topo)
        assert "FizzNUMA" in output
        assert FIZZNUMA_VERSION in output


# =========================================================================
# Middleware
# =========================================================================


class TestNUMAMiddleware:
    """Verify pipeline middleware integration."""

    def test_middleware_sets_metadata(self):
        topo = NUMATopology()
        mw = NUMAMiddleware(topo)

        @dataclass
        class Ctx:
            number: int
            session_id: str = "test"
            metadata: dict = None
            def __post_init__(self):
                if self.metadata is None:
                    self.metadata = {}

        ctx = Ctx(number=15)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["numa_classification"] == "FizzBuzz"
        assert result.metadata["numa_enabled"] is True

    def test_middleware_name(self):
        topo = NUMATopology()
        mw = NUMAMiddleware(topo)
        assert mw.get_name() == "fizznuma"

    def test_middleware_priority(self):
        topo = NUMATopology()
        mw = NUMAMiddleware(topo)
        assert mw.get_priority() == 251


# =========================================================================
# Factory
# =========================================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_subsystem(self):
        topo, mw = create_fizznuma_subsystem(num_nodes=4, cpus_per_node=2)
        assert isinstance(topo, NUMATopology)
        assert isinstance(mw, NUMAMiddleware)
        assert topo.node_count == 4


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify NUMA exception hierarchy."""

    def test_numa_error_base(self):
        err = NUMAError("test")
        assert "test" in str(err)

    def test_numa_distance_error(self):
        err = NUMADistanceError(0, 1, -5)
        assert err.src_node == 0
        assert err.distance == -5

    def test_numa_placement_error(self):
        err = NUMAPlacementError("bind", "no memory")
        assert err.policy == "bind"

    def test_numa_topology_error(self):
        err = NUMATopologyError("asymmetric distances")
        assert "asymmetric" in str(err)

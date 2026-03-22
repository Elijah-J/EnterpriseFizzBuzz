"""
Tests for the FizzLock Distributed Lock Manager.

Validates the correctness of the hierarchical multi-granularity lock manager,
including the 5x5 compatibility matrix, Tarjan's SCC deadlock detection,
wait-die / wound-wait policies, fencing token generation, lease management,
contention profiling, and lock dashboard rendering.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.distributed_locks import (
    COMPAT,
    HIERARCHY_LEVELS,
    ContentionProfiler,
    DeadlockDetector,
    FencingTokenGenerator,
    HierarchicalLockManager,
    LeaseManager,
    LockDashboard,
    LockGrant,
    LockMiddleware,
    LockMode,
    LockRequest,
    LockTable,
    WaitPolicy,
    WaitPolicyType,
    _ancestor_paths,
    _resource_path,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext
from enterprise_fizzbuzz.domain.exceptions import (
    DistributedLockError,
    LockAcquisitionTimeoutError,
    LockDeadlockDetectedError,
    LockLeaseExpiredError,
    LockTransactionAbortedError,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================================
# LockMode and Compatibility Matrix
# ============================================================================

class TestLockModeCompatibility:
    """Verify the 5x5 compatibility matrix against the standard MGL protocol."""

    def test_x_incompatible_with_all(self):
        """X mode is incompatible with every other mode including itself."""
        for mode in LockMode:
            assert COMPAT[LockMode.X][mode] is False
            assert COMPAT[mode][LockMode.X] is False

    def test_s_compatible_with_s(self):
        """Multiple shared readers can coexist on the same resource."""
        assert COMPAT[LockMode.S][LockMode.S] is True

    def test_s_compatible_with_is(self):
        """Shared lock is compatible with intent shared."""
        assert COMPAT[LockMode.S][LockMode.IS] is True
        assert COMPAT[LockMode.IS][LockMode.S] is True

    def test_s_incompatible_with_ix(self):
        """Shared lock conflicts with intent exclusive."""
        assert COMPAT[LockMode.S][LockMode.IX] is False

    def test_is_compatible_with_is(self):
        """Intent shared is compatible with itself."""
        assert COMPAT[LockMode.IS][LockMode.IS] is True

    def test_is_compatible_with_ix(self):
        """Intent shared is compatible with intent exclusive."""
        assert COMPAT[LockMode.IS][LockMode.IX] is True
        assert COMPAT[LockMode.IX][LockMode.IS] is True

    def test_ix_compatible_with_ix(self):
        """Intent exclusive is compatible with itself."""
        assert COMPAT[LockMode.IX][LockMode.IX] is True

    def test_ix_incompatible_with_s(self):
        """Intent exclusive conflicts with shared."""
        assert COMPAT[LockMode.IX][LockMode.S] is False

    def test_u_compatible_with_s(self):
        """Update lock is compatible with shared (read before upgrade)."""
        assert COMPAT[LockMode.U][LockMode.S] is True

    def test_u_compatible_with_is(self):
        """Update lock is compatible with intent shared."""
        assert COMPAT[LockMode.U][LockMode.IS] is True
        assert COMPAT[LockMode.IS][LockMode.U] is True

    def test_u_incompatible_with_u(self):
        """Only one update lock is permitted per resource."""
        assert COMPAT[LockMode.U][LockMode.U] is False

    def test_u_incompatible_with_ix(self):
        """Update lock conflicts with intent exclusive."""
        assert COMPAT[LockMode.U][LockMode.IX] is False

    def test_u_incompatible_with_x(self):
        """Update lock conflicts with exclusive."""
        assert COMPAT[LockMode.U][LockMode.X] is False

    def test_compatibility_matrix_is_5x5(self):
        """The matrix covers all 25 mode combinations."""
        assert len(COMPAT) == 5
        for mode in LockMode:
            assert len(COMPAT[mode]) == 5


# ============================================================================
# LockRequest and LockGrant
# ============================================================================

class TestLockRequestGrant:
    """Verify lock request and grant data structures."""

    def test_request_default_fields(self):
        req = LockRequest()
        assert req.request_id
        assert req.transaction_id
        assert req.resource == ""
        assert req.mode == LockMode.S
        assert req.timestamp > 0

    def test_request_custom_fields(self):
        req = LockRequest(
            transaction_id="txn-1",
            resource="efp/default/evaluation/42",
            mode=LockMode.X,
        )
        assert req.transaction_id == "txn-1"
        assert req.resource == "efp/default/evaluation/42"
        assert req.mode == LockMode.X

    def test_grant_delegates_properties(self):
        req = LockRequest(
            transaction_id="txn-1",
            resource="efp/default/evaluation/42",
            mode=LockMode.S,
        )
        grant = LockGrant(request=req, fencing_token=1)
        assert grant.resource == "efp/default/evaluation/42"
        assert grant.mode == LockMode.S
        assert grant.transaction_id == "txn-1"
        assert grant.fencing_token == 1

    def test_grant_expiry_initially_none(self):
        req = LockRequest(transaction_id="txn-1")
        grant = LockGrant(request=req, fencing_token=1)
        assert grant.lease_expiry is None


# ============================================================================
# Resource Path Utilities
# ============================================================================

class TestResourcePaths:
    """Verify canonical resource path construction and ancestor decomposition."""

    def test_default_resource_path(self):
        assert _resource_path() == "efp/default/evaluation"

    def test_resource_path_with_number(self):
        assert _resource_path(number=42) == "efp/default/evaluation/42"

    def test_resource_path_with_field(self):
        assert _resource_path(number=42, field_name="result") == "efp/default/evaluation/42/result"

    def test_resource_path_custom_components(self):
        path = _resource_path(platform="prod", namespace="ns1", subsystem="cache", number=7)
        assert path == "prod/ns1/cache/7"

    def test_ancestor_paths(self):
        ancestors = _ancestor_paths("efp/default/evaluation/42/result")
        assert ancestors == [
            "efp",
            "efp/default",
            "efp/default/evaluation",
            "efp/default/evaluation/42",
        ]

    def test_ancestor_paths_root(self):
        ancestors = _ancestor_paths("efp")
        assert ancestors == []

    def test_hierarchy_levels(self):
        assert HIERARCHY_LEVELS == ["platform", "namespace", "subsystem", "number", "field"]


# ============================================================================
# Lock Table
# ============================================================================

class TestLockTable:
    """Verify the per-resource lock state management."""

    def test_empty_table_is_compatible(self):
        table = LockTable()
        assert table.is_compatible("r1", LockMode.X, "txn-1") is True

    def test_add_and_check_holder(self):
        table = LockTable()
        req = LockRequest(transaction_id="txn-1", resource="r1", mode=LockMode.S)
        grant = LockGrant(request=req, fencing_token=1)
        table.add_holder(grant)
        assert table.is_compatible("r1", LockMode.S, "txn-2") is True
        assert table.is_compatible("r1", LockMode.X, "txn-2") is False

    def test_same_transaction_is_always_compatible(self):
        table = LockTable()
        req = LockRequest(transaction_id="txn-1", resource="r1", mode=LockMode.X)
        grant = LockGrant(request=req, fencing_token=1)
        table.add_holder(grant)
        assert table.is_compatible("r1", LockMode.X, "txn-1") is True

    def test_remove_holder(self):
        table = LockTable()
        req = LockRequest(transaction_id="txn-1", resource="r1", mode=LockMode.S)
        grant = LockGrant(request=req, fencing_token=1)
        table.add_holder(grant)
        removed = table.remove_holder("r1", "txn-1")
        assert len(removed) == 1
        assert table.is_compatible("r1", LockMode.X, "txn-2") is True

    def test_remove_nonexistent_holder(self):
        table = LockTable()
        removed = table.remove_holder("r1", "txn-ghost")
        assert removed == []

    def test_get_holders(self):
        table = LockTable()
        req = LockRequest(transaction_id="txn-1", resource="r1", mode=LockMode.S)
        grant = LockGrant(request=req, fencing_token=1)
        table.add_holder(grant)
        holders = table.get_holders("r1")
        assert "txn-1" in holders
        assert len(holders["txn-1"]) == 1

    def test_get_all_resources(self):
        table = LockTable()
        req1 = LockRequest(transaction_id="txn-1", resource="r1", mode=LockMode.S)
        req2 = LockRequest(transaction_id="txn-1", resource="r2", mode=LockMode.X)
        table.add_holder(LockGrant(request=req1, fencing_token=1))
        table.add_holder(LockGrant(request=req2, fencing_token=2))
        resources = table.get_all_resources()
        assert set(resources) == {"r1", "r2"}

    def test_acquisition_counter(self):
        table = LockTable()
        req = LockRequest(transaction_id="txn-1", resource="r1", mode=LockMode.S)
        table.add_holder(LockGrant(request=req, fencing_token=1))
        assert table.total_acquisitions == 1

    def test_waiter_operations(self):
        table = LockTable()
        req = LockRequest(transaction_id="txn-1", resource="r1", mode=LockMode.X)
        table.enqueue_waiter(req)
        waiters = table.get_waiters("r1")
        assert len(waiters) == 1
        removed = table.remove_waiter("r1", "txn-1")
        assert removed is not None
        assert removed.transaction_id == "txn-1"


# ============================================================================
# Fencing Token Generator
# ============================================================================

class TestFencingTokenGenerator:
    """Verify strict monotonicity of fencing tokens."""

    def test_tokens_are_strictly_increasing(self):
        gen = FencingTokenGenerator()
        tokens = [gen.next() for _ in range(100)]
        for i in range(1, len(tokens)):
            assert tokens[i] > tokens[i - 1]

    def test_initial_value(self):
        gen = FencingTokenGenerator(initial=1000)
        assert gen.next() == 1001

    def test_current_property(self):
        gen = FencingTokenGenerator()
        assert gen.current == 0
        gen.next()
        assert gen.current == 1

    def test_thread_safety(self):
        gen = FencingTokenGenerator()
        results: list[int] = []
        lock = threading.Lock()

        def generate_tokens(n: int):
            local_tokens = [gen.next() for _ in range(n)]
            with lock:
                results.extend(local_tokens)

        threads = [threading.Thread(target=generate_tokens, args=(50,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 200
        assert len(set(results)) == 200  # All unique
        assert max(results) == 200


# ============================================================================
# Deadlock Detector — Tarjan's SCC
# ============================================================================

class TestDeadlockDetector:
    """Verify Tarjan's SCC-based deadlock detection."""

    def test_no_deadlock_in_acyclic_graph(self):
        detector = DeadlockDetector()
        detector.add_edge("A", "B")
        detector.add_edge("B", "C")
        cycles = detector.detect({"A": 1.0, "B": 2.0, "C": 3.0})
        assert cycles == []

    def test_simple_deadlock_cycle(self):
        detector = DeadlockDetector()
        detector.add_edge("A", "B")
        detector.add_edge("B", "A")
        cycles = detector.detect({"A": 1.0, "B": 2.0})
        assert len(cycles) == 1
        assert set(cycles[0]) == {"A", "B"}

    def test_three_way_deadlock(self):
        detector = DeadlockDetector()
        detector.add_edge("A", "B")
        detector.add_edge("B", "C")
        detector.add_edge("C", "A")
        cycles = detector.detect({"A": 1.0, "B": 2.0, "C": 3.0})
        assert len(cycles) == 1
        assert set(cycles[0]) == {"A", "B", "C"}

    def test_victim_selection_youngest_first(self):
        detector = DeadlockDetector()
        timestamps = {"A": 1.0, "B": 5.0, "C": 3.0}
        cycle = ["A", "C", "B"]
        victim = detector.select_victim(cycle, timestamps)
        assert victim == "B"  # Highest timestamp = youngest

    def test_remove_edges_clears_both_directions(self):
        detector = DeadlockDetector()
        detector.add_edge("A", "B")
        detector.add_edge("B", "A")
        detector.remove_edges_for("A")
        cycles = detector.detect({"A": 1.0, "B": 2.0})
        assert cycles == []

    def test_self_edge_ignored(self):
        detector = DeadlockDetector()
        detector.add_edge("A", "A")
        assert detector.edge_count == 0

    def test_deadlock_history(self):
        detector = DeadlockDetector()
        detector.add_edge("X", "Y")
        detector.add_edge("Y", "X")
        detector.detect({"X": 1.0, "Y": 2.0})
        assert len(detector.deadlock_history) == 1
        assert detector.total_deadlocks == 1
        assert detector.deadlock_history[0]["victim"] == "Y"

    def test_multiple_independent_cycles(self):
        detector = DeadlockDetector()
        detector.add_edge("A", "B")
        detector.add_edge("B", "A")
        detector.add_edge("C", "D")
        detector.add_edge("D", "C")
        cycles = detector.detect({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0})
        assert len(cycles) == 2

    def test_wait_for_graph_snapshot(self):
        detector = DeadlockDetector()
        detector.add_edge("A", "B")
        graph = detector.get_wait_for_graph()
        assert "A" in graph
        assert "B" in graph["A"]


# ============================================================================
# Wait Policy
# ============================================================================

class TestWaitPolicy:
    """Verify wait-die and wound-wait policy decisions."""

    def test_wait_die_older_waits(self):
        policy = WaitPolicy(WaitPolicyType.WAIT_DIE)
        decision = policy.decide("txn-old", 1.0, "txn-young", 5.0)
        assert decision == "wait"

    def test_wait_die_younger_dies(self):
        policy = WaitPolicy(WaitPolicyType.WAIT_DIE)
        decision = policy.decide("txn-young", 5.0, "txn-old", 1.0)
        assert decision == "abort_requester"

    def test_wait_die_same_age_waits(self):
        policy = WaitPolicy(WaitPolicyType.WAIT_DIE)
        decision = policy.decide("txn-a", 3.0, "txn-b", 3.0)
        assert decision == "wait"

    def test_wound_wait_older_wounds(self):
        policy = WaitPolicy(WaitPolicyType.WOUND_WAIT)
        decision = policy.decide("txn-old", 1.0, "txn-young", 5.0)
        assert decision == "abort_holder"

    def test_wound_wait_younger_waits(self):
        policy = WaitPolicy(WaitPolicyType.WOUND_WAIT)
        decision = policy.decide("txn-young", 5.0, "txn-old", 1.0)
        assert decision == "wait"

    def test_wound_wait_same_age_wounds(self):
        policy = WaitPolicy(WaitPolicyType.WOUND_WAIT)
        decision = policy.decide("txn-a", 3.0, "txn-b", 3.0)
        assert decision == "abort_holder"

    def test_abort_tracking(self):
        policy = WaitPolicy()
        assert policy.is_aborted("txn-1") is False
        policy.mark_aborted("txn-1")
        assert policy.is_aborted("txn-1") is True
        policy.clear_aborted("txn-1")
        assert policy.is_aborted("txn-1") is False

    def test_policy_type_property(self):
        policy = WaitPolicy(WaitPolicyType.WOUND_WAIT)
        assert policy.policy_type == WaitPolicyType.WOUND_WAIT


# ============================================================================
# Lease Manager
# ============================================================================

class TestLeaseManager:
    """Verify heap-based lease expiration and renewal."""

    def test_register_sets_expiry(self):
        lm = LeaseManager(lease_duration=10.0)
        req = LockRequest(transaction_id="txn-1", resource="r1")
        grant = LockGrant(request=req, fencing_token=1)
        lm.register(grant)
        assert grant.lease_expiry is not None
        assert lm.active_lease_count == 1

    def test_unregister_removes_lease(self):
        lm = LeaseManager()
        req = LockRequest(transaction_id="txn-1", resource="r1")
        grant = LockGrant(request=req, fencing_token=1)
        lm.register(grant)
        lm.unregister(req.request_id)
        assert lm.active_lease_count == 0

    def test_renew_extends_expiry(self):
        lm = LeaseManager(lease_duration=10.0)
        req = LockRequest(transaction_id="txn-1", resource="r1")
        grant = LockGrant(request=req, fencing_token=1)
        lm.register(grant)
        old_expiry = grant.lease_expiry
        time.sleep(0.01)
        assert lm.renew(req.request_id) is True
        assert grant.lease_expiry > old_expiry
        assert lm.renewed_count == 1

    def test_renew_nonexistent_fails(self):
        lm = LeaseManager()
        assert lm.renew("ghost-id") is False

    def test_lease_expiry_callback(self):
        expired_grants: list[LockGrant] = []

        def on_expire(grant: LockGrant):
            expired_grants.append(grant)

        lm = LeaseManager(
            lease_duration=0.05,
            grace_period=0.01,
            check_interval=0.02,
            on_expire=on_expire,
        )
        req = LockRequest(transaction_id="txn-1", resource="r1")
        grant = LockGrant(request=req, fencing_token=1)
        lm.register(grant)
        lm.start()
        try:
            time.sleep(0.3)
        finally:
            lm.stop()
        assert len(expired_grants) >= 1
        assert lm.expired_count >= 1

    def test_start_stop_idempotent(self):
        lm = LeaseManager()
        lm.start()
        lm.start()  # Double start should not error
        lm.stop()
        lm.stop()  # Double stop should not error

    def test_lease_duration_property(self):
        lm = LeaseManager(lease_duration=42.0)
        assert lm.lease_duration == 42.0


# ============================================================================
# Contention Profiler
# ============================================================================

class TestContentionProfiler:
    """Verify per-resource contention tracking and hot-lock detection."""

    def test_record_and_histogram(self):
        profiler = ContentionProfiler()
        profiler.record_wait("r1", 5.0)
        profiler.record_wait("r1", 10.0)
        profiler.record_wait("r1", 15.0)
        h = profiler.get_histogram("r1")
        assert h["count"] == 3
        assert h["min_ms"] == 5.0
        assert h["max_ms"] == 15.0
        assert h["avg_ms"] == 10.0

    def test_empty_histogram(self):
        profiler = ContentionProfiler()
        h = profiler.get_histogram("r_nonexistent")
        assert h["count"] == 0

    def test_hot_lock_detection(self):
        profiler = ContentionProfiler(hot_lock_threshold_ms=5.0)
        profiler.record_wait("hot_resource", 10.0)
        profiler.record_wait("hot_resource", 20.0)
        profiler.record_wait("cold_resource", 1.0)
        hot = profiler.get_hot_locks()
        assert len(hot) == 1
        assert hot[0][0] == "hot_resource"

    def test_contention_heatmap(self):
        profiler = ContentionProfiler()
        profiler.record_wait("r1", 10.0)
        profiler.record_wait("r1", 20.0)
        profiler.record_wait("r2", 5.0)
        heatmap = profiler.get_contention_heatmap(top_n=2)
        assert len(heatmap) == 2
        assert heatmap[0]["resource"] == "r1"
        assert heatmap[0]["total_ms"] == 30.0

    def test_total_statistics(self):
        profiler = ContentionProfiler()
        profiler.record_wait("r1", 5.0)
        profiler.record_wait("r2", 10.0)
        assert profiler.total_wait_ms == 15.0
        assert profiler.total_samples == 2


# ============================================================================
# Hierarchical Lock Manager
# ============================================================================

class TestHierarchicalLockManager:
    """Verify the complete hierarchical lock acquisition protocol."""

    def test_acquire_and_release_shared(self):
        mgr = HierarchicalLockManager()
        grant = mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        assert grant is not None
        assert grant.mode == LockMode.S
        assert grant.fencing_token > 0
        assert mgr.release("efp/default/evaluation/42", "txn-1") is True

    def test_acquire_exclusive(self):
        mgr = HierarchicalLockManager()
        grant = mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-1")
        assert grant is not None
        assert grant.mode == LockMode.X

    def test_multiple_shared_readers(self):
        mgr = HierarchicalLockManager()
        g1 = mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        g2 = mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-2")
        assert g1 is not None
        assert g2 is not None

    def test_exclusive_blocks_shared(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-1")
        # txn-2 should fail to acquire S lock (timeout quickly)
        g2 = mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-2", timeout=0.1)
        assert g2 is None

    def test_shared_blocks_exclusive(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        g2 = mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-2", timeout=0.1)
        assert g2 is None

    def test_intent_locks_at_ancestors(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        # Ancestors should have IS locks
        holders_platform = mgr.lock_table.get_holders("efp")
        assert "txn-1" in holders_platform

    def test_release_all(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        mgr.acquire("efp/default/evaluation/43", LockMode.S, "txn-1")
        count = mgr.release_all("txn-1")
        assert count >= 2

    def test_upgrade_s_to_x(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        upgraded = mgr.upgrade("efp/default/evaluation/42", "txn-1", LockMode.X)
        assert upgraded is not None
        assert upgraded.mode == LockMode.X
        assert mgr.total_upgrades == 1

    def test_reacquire_same_lock_returns_existing(self):
        mgr = HierarchicalLockManager()
        g1 = mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        g2 = mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        assert g1 is g2  # Same grant object

    def test_different_numbers_dont_conflict(self):
        mgr = HierarchicalLockManager()
        g1 = mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-1")
        g2 = mgr.acquire("efp/default/evaluation/43", LockMode.X, "txn-2")
        assert g1 is not None
        assert g2 is not None

    def test_get_transaction_locks(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        locks = mgr.get_transaction_locks("txn-1")
        assert "efp/default/evaluation/42" in locks

    def test_total_acquires_counter(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/1", LockMode.S, "txn-1")
        mgr.acquire("efp/default/evaluation/2", LockMode.S, "txn-2")
        assert mgr.total_acquires == 2

    def test_release_nonexistent_returns_false(self):
        mgr = HierarchicalLockManager()
        assert mgr.release("nonexistent", "ghost-txn") is False


# ============================================================================
# Wait Policy Integration
# ============================================================================

class TestWaitPolicyIntegration:
    """Verify wait-die and wound-wait behavior within the lock manager."""

    def test_wait_die_younger_aborted(self):
        policy = WaitPolicy(WaitPolicyType.WAIT_DIE)
        mgr = HierarchicalLockManager(wait_policy=policy)
        # txn-old gets lock first (registered with lower timestamp)
        mgr.register_transaction("txn-old", timestamp=1.0)
        mgr.register_transaction("txn-young", timestamp=100.0)
        mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-old", timeout=1.0)
        # txn-young should be aborted (younger dies)
        result = mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-young", timeout=0.1)
        assert result is None

    def test_wound_wait_older_wounds_holder(self):
        policy = WaitPolicy(WaitPolicyType.WOUND_WAIT)
        mgr = HierarchicalLockManager(wait_policy=policy)
        mgr.register_transaction("txn-young", timestamp=100.0)
        mgr.register_transaction("txn-old", timestamp=1.0)
        mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-young", timeout=1.0)
        # txn-old should wound (abort) txn-young and get the lock
        result = mgr.acquire("efp/default/evaluation/42", LockMode.X, "txn-old", timeout=1.0)
        assert result is not None
        assert result.transaction_id == "txn-old"


# ============================================================================
# Lock Dashboard
# ============================================================================

class TestLockDashboard:
    """Verify ASCII dashboard rendering."""

    def test_empty_dashboard_renders(self):
        mgr = HierarchicalLockManager()
        output = LockDashboard.render(mgr)
        assert "FIZZLOCK DISTRIBUTED LOCK MANAGER" in output
        assert "ACTIVE LOCKS" in output
        assert "WAIT-FOR GRAPH" in output
        assert "DEADLOCK HISTORY" in output
        assert "CONTENTION HEATMAP" in output
        assert "(no active locks)" in output

    def test_dashboard_with_active_locks(self):
        mgr = HierarchicalLockManager()
        mgr.acquire("efp/default/evaluation/42", LockMode.S, "txn-1")
        output = LockDashboard.render(mgr)
        assert "txn-1" in output or "txn-1"[:8] in output

    def test_dashboard_custom_width(self):
        mgr = HierarchicalLockManager()
        output = LockDashboard.render(mgr, width=80)
        lines = output.split("\n")
        for line in lines:
            assert len(line) <= 80

    def test_dashboard_with_contention_data(self):
        profiler = ContentionProfiler()
        profiler.record_wait("efp/default/evaluation/42", 15.0)
        mgr = HierarchicalLockManager(profiler=profiler)
        output = LockDashboard.render(mgr)
        assert "15.0ms" in output or "Total Wait" in output

    def test_dashboard_policy_display(self):
        policy = WaitPolicy(WaitPolicyType.WOUND_WAIT)
        mgr = HierarchicalLockManager(wait_policy=policy)
        output = LockDashboard.render(mgr)
        assert "WOUND_WAIT" in output


# ============================================================================
# Lock Middleware
# ============================================================================

class TestLockMiddleware:
    """Verify middleware integration with the evaluation pipeline."""

    def _make_context(self, number: int = 42) -> ProcessingContext:
        return ProcessingContext(
            number=number,
            session_id="test-session",
        )

    def test_middleware_acquires_and_releases_lock(self):
        mgr = HierarchicalLockManager()
        mw = LockMiddleware(manager=mgr)

        def handler(ctx: ProcessingContext) -> ProcessingContext:
            # While inside the handler, lock should be held
            assert ctx.metadata.get("lock_acquired") is True
            assert ctx.metadata.get("lock_fencing_token", 0) > 0
            return ctx

        ctx = self._make_context()
        result = mw.process(ctx, handler)
        assert result.metadata["lock_acquired"] is True
        assert mw.lock_count == 1
        # After middleware completes, locks should be released
        assert mgr.get_active_lock_count() == 0

    def test_middleware_name_and_priority(self):
        mgr = HierarchicalLockManager()
        mw = LockMiddleware(manager=mgr, priority=900)
        assert mw.get_name() == "LockMiddleware"
        assert mw.get_priority() == 900

    def test_middleware_releases_on_exception(self):
        mgr = HierarchicalLockManager()
        mw = LockMiddleware(manager=mgr)

        def failing_handler(ctx: ProcessingContext) -> ProcessingContext:
            raise ValueError("evaluation exploded")

        ctx = self._make_context()
        with pytest.raises(ValueError):
            mw.process(ctx, failing_handler)
        # Lock should still be released despite exception
        assert mgr.get_active_lock_count() == 0


# ============================================================================
# Exception Hierarchy
# ============================================================================

class TestExceptionHierarchy:
    """Verify the FizzLock exception classes and error codes."""

    def test_base_exception(self):
        err = DistributedLockError("test error")
        assert "EFP-7000" in str(err)

    def test_acquisition_timeout_error(self):
        err = LockAcquisitionTimeoutError("r1", "S", 5000.0, "txn-1")
        assert "EFP-7001" in str(err)
        assert err.resource == "r1"
        assert err.timeout_ms == 5000.0

    def test_deadlock_detected_error(self):
        err = LockDeadlockDetectedError(["A", "B"], "B")
        assert "EFP-7002" in str(err)
        assert err.cycle == ["A", "B"]
        assert err.victim == "B"

    def test_transaction_aborted_error(self):
        err = LockTransactionAbortedError("txn-1", "younger than holder")
        assert "EFP-7003" in str(err)
        assert err.transaction_id == "txn-1"

    def test_lease_expired_error(self):
        err = LockLeaseExpiredError("r1", "txn-1", 42)
        assert "EFP-7004" in str(err)
        assert err.fencing_token == 42

    def test_all_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(DistributedLockError, FizzBuzzError)
        assert issubclass(LockAcquisitionTimeoutError, DistributedLockError)
        assert issubclass(LockDeadlockDetectedError, DistributedLockError)
        assert issubclass(LockTransactionAbortedError, DistributedLockError)
        assert issubclass(LockLeaseExpiredError, DistributedLockError)


# ============================================================================
# EventType Entries
# ============================================================================

class TestEventTypeEntries:
    """Verify that FizzLock event types exist in the domain model."""

    def test_lock_event_types_exist(self):
        assert EventType.LOCK_ACQUIRED is not None
        assert EventType.LOCK_RELEASED is not None
        assert EventType.LOCK_UPGRADE_REQUESTED is not None
        assert EventType.LOCK_UPGRADE_COMPLETED is not None
        assert EventType.LOCK_ACQUISITION_TIMEOUT is not None
        assert EventType.LOCK_DEADLOCK_DETECTED is not None
        assert EventType.LOCK_TRANSACTION_ABORTED is not None
        assert EventType.LOCK_LEASE_EXPIRED is not None
        assert EventType.LOCK_LEASE_RENEWED is not None
        assert EventType.LOCK_CONTENTION_DETECTED is not None
        assert EventType.LOCK_DASHBOARD_RENDERED is not None

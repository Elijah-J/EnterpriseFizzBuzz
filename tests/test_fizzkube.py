"""
Enterprise FizzBuzz Platform - FizzKube Container Orchestration Tests

Tests for the Kubernetes-inspired pod scheduling system including
EtcdStore, FizzKubeScheduler, ReplicaSet, HPA, FizzKubeControlPlane,
FizzKubeDashboard, and FizzKubeMiddleware.

Because if your Kubernetes-inspired container orchestration system
for scheduling modulo arithmetic across simulated worker nodes doesn't
have a comprehensive test suite, can you really call it production-ready?
"""

from __future__ import annotations

import math
import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    EtcdKeyNotFoundError,
    FizzKubeError,
    HPAScalingError,
    NodeNotReadyError,
    PodSchedulingError,
    ResourceQuotaExceededError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzkube import (
    EtcdStore,
    FizzKubeControlPlane,
    FizzKubeDashboard,
    FizzKubeMiddleware,
    FizzKubeScheduler,
    HorizontalPodAutoscaler,
    Namespace,
    NodeCondition,
    Pod,
    PodPhase,
    PodSpec,
    ReplicaSet,
    ResourceQuota,
    ResourceUnits,
    WorkerNode,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def etcd():
    """Create a fresh EtcdStore."""
    return EtcdStore()


@pytest.fixture
def small_node():
    """Create a small worker node (1000mF CPU, 2048 FB memory)."""
    return WorkerNode(
        name="test-node-0",
        capacity=ResourceUnits(1000, 2048),
    )


@pytest.fixture
def three_nodes():
    """Create three worker nodes."""
    return [
        WorkerNode(
            name=f"test-node-{i}",
            capacity=ResourceUnits(4000, 8192),
        )
        for i in range(3)
    ]


@pytest.fixture
def scheduler():
    """Create a FizzKubeScheduler."""
    return FizzKubeScheduler()


@pytest.fixture
def default_pod_spec():
    """Create a default PodSpec."""
    return PodSpec(
        cpu_request=100,
        cpu_limit=200,
        memory_request=128,
        memory_limit=256,
        namespace="test-ns",
        number=15,
    )


@pytest.fixture
def control_plane():
    """Create a FizzKubeControlPlane with default settings."""
    return FizzKubeControlPlane(
        num_nodes=3,
        cpu_per_node=4000,
        memory_per_node=8192,
        pod_cpu_request=100,
        pod_memory_request=128,
    )


# ===========================================================================
# ResourceUnits Tests
# ===========================================================================


class TestResourceUnits:
    """Tests for the ResourceUnits dataclass."""

    def test_default_values(self):
        """ResourceUnits default to zero."""
        ru = ResourceUnits()
        assert ru.cpu_millifizz == 0
        assert ru.memory_fizzbytes == 0

    def test_fits_in_when_smaller(self):
        """Smaller resources fit within larger capacity."""
        request = ResourceUnits(100, 128)
        capacity = ResourceUnits(4000, 8192)
        assert request.fits_in(capacity)

    def test_fits_in_when_equal(self):
        """Equal resources fit exactly."""
        ru = ResourceUnits(100, 128)
        assert ru.fits_in(ru)

    def test_does_not_fit_when_larger(self):
        """Larger resources do not fit."""
        request = ResourceUnits(5000, 128)
        capacity = ResourceUnits(4000, 8192)
        assert not request.fits_in(capacity)

    def test_addition(self):
        """ResourceUnits can be added together."""
        a = ResourceUnits(100, 200)
        b = ResourceUnits(300, 400)
        result = a + b
        assert result.cpu_millifizz == 400
        assert result.memory_fizzbytes == 600

    def test_subtraction(self):
        """ResourceUnits can be subtracted."""
        a = ResourceUnits(500, 1000)
        b = ResourceUnits(200, 300)
        result = a - b
        assert result.cpu_millifizz == 300
        assert result.memory_fizzbytes == 700


# ===========================================================================
# PodSpec Tests
# ===========================================================================


class TestPodSpec:
    """Tests for the PodSpec dataclass."""

    def test_requests_property(self, default_pod_spec):
        """PodSpec.requests returns correct ResourceUnits."""
        req = default_pod_spec.requests
        assert req.cpu_millifizz == 100
        assert req.memory_fizzbytes == 128

    def test_limits_property(self, default_pod_spec):
        """PodSpec.limits returns correct ResourceUnits."""
        lim = default_pod_spec.limits
        assert lim.cpu_millifizz == 200
        assert lim.memory_fizzbytes == 256


# ===========================================================================
# Pod Tests
# ===========================================================================


class TestPod:
    """Tests for the Pod dataclass."""

    def test_auto_generated_name(self):
        """Pod generates a unique name if not provided."""
        pod = Pod()
        assert pod.name.startswith("fizzbuzz-eval-")
        assert len(pod.name) > len("fizzbuzz-eval-")

    def test_unique_names(self):
        """Each pod gets a unique name."""
        pods = [Pod() for _ in range(10)]
        names = [p.name for p in pods]
        assert len(set(names)) == 10

    def test_default_phase_is_pending(self):
        """Pods start in PENDING phase."""
        pod = Pod()
        assert pod.phase == PodPhase.PENDING

    def test_custom_name(self):
        """Custom pod name is preserved."""
        pod = Pod(name="my-custom-pod")
        assert pod.name == "my-custom-pod"


# ===========================================================================
# WorkerNode Tests
# ===========================================================================


class TestWorkerNode:
    """Tests for the WorkerNode dataclass."""

    def test_available_resources(self, small_node):
        """Available = capacity - allocated."""
        avail = small_node.available
        assert avail.cpu_millifizz == 1000
        assert avail.memory_fizzbytes == 2048

    def test_cpu_utilization_empty(self, small_node):
        """Empty node has 0% CPU utilization."""
        assert small_node.cpu_utilization_pct == 0.0

    def test_memory_utilization_empty(self, small_node):
        """Empty node has 0% memory utilization."""
        assert small_node.memory_utilization_pct == 0.0

    def test_can_fit_within_capacity(self, small_node):
        """Node can fit a pod within its capacity."""
        request = ResourceUnits(500, 1024)
        assert small_node.can_fit(request)

    def test_cannot_fit_beyond_capacity(self, small_node):
        """Node cannot fit a pod beyond its capacity."""
        request = ResourceUnits(2000, 1024)
        assert not small_node.can_fit(request)

    def test_allocate_updates_resources(self, small_node):
        """Allocating a pod updates the node's allocated resources."""
        pod = Pod(spec=PodSpec(cpu_request=200, memory_request=256))
        small_node.allocate(pod)
        assert small_node.allocated.cpu_millifizz == 200
        assert small_node.allocated.memory_fizzbytes == 256
        assert pod.node_name == "test-node-0"
        assert len(small_node.pods) == 1

    def test_deallocate_releases_resources(self, small_node):
        """Deallocating a pod releases its resources."""
        pod = Pod(spec=PodSpec(cpu_request=200, memory_request=256))
        small_node.allocate(pod)
        small_node.deallocate(pod)
        assert small_node.allocated.cpu_millifizz == 0
        assert small_node.allocated.memory_fizzbytes == 0
        assert len(small_node.pods) == 0

    def test_utilization_after_allocation(self, small_node):
        """Utilization reflects allocated resources."""
        pod = Pod(spec=PodSpec(cpu_request=500, memory_request=1024))
        small_node.allocate(pod)
        assert small_node.cpu_utilization_pct == 50.0
        assert small_node.memory_utilization_pct == 50.0

    def test_zero_capacity_utilization(self):
        """Zero capacity node reports 0% utilization."""
        node = WorkerNode(
            name="empty-node",
            capacity=ResourceUnits(0, 0),
        )
        assert node.cpu_utilization_pct == 0.0
        assert node.memory_utilization_pct == 0.0


# ===========================================================================
# ResourceQuota Tests
# ===========================================================================


class TestResourceQuota:
    """Tests for the ResourceQuota dataclass."""

    def test_allows_within_limits(self):
        """Quota allows allocation within limits."""
        quota = ResourceQuota(cpu_limit=1000, memory_limit=2048)
        used = ResourceUnits(500, 1024)
        additional = ResourceUnits(200, 512)
        assert quota.allows(used, additional)

    def test_denies_exceeding_limits(self):
        """Quota denies allocation that would exceed limits."""
        quota = ResourceQuota(cpu_limit=1000, memory_limit=2048)
        used = ResourceUnits(900, 1024)
        additional = ResourceUnits(200, 512)
        assert not quota.allows(used, additional)

    def test_allows_exact_limits(self):
        """Quota allows allocation at exact limits."""
        quota = ResourceQuota(cpu_limit=1000, memory_limit=2048)
        used = ResourceUnits(800, 1536)
        additional = ResourceUnits(200, 512)
        assert quota.allows(used, additional)


# ===========================================================================
# EtcdStore Tests
# ===========================================================================


class TestEtcdStore:
    """Tests for the etcd-inspired key-value store."""

    def test_put_and_get(self, etcd):
        """Basic put and get operations."""
        etcd.put("key1", "value1")
        assert etcd.get("key1") == "value1"

    def test_revision_increments_on_put(self, etcd):
        """Revision increases with each put."""
        rev1 = etcd.put("key1", "value1")
        rev2 = etcd.put("key2", "value2")
        assert rev2 > rev1

    def test_get_nonexistent_raises(self, etcd):
        """Getting a nonexistent key raises EtcdKeyNotFoundError."""
        with pytest.raises(EtcdKeyNotFoundError):
            etcd.get("nonexistent")

    def test_get_or_default_returns_value(self, etcd):
        """get_or_default returns the value if the key exists."""
        etcd.put("key1", 42)
        assert etcd.get_or_default("key1", -1) == 42

    def test_get_or_default_returns_default(self, etcd):
        """get_or_default returns default for missing keys."""
        assert etcd.get_or_default("missing", "fallback") == "fallback"

    def test_delete(self, etcd):
        """Delete removes a key."""
        etcd.put("key1", "value1")
        etcd.delete("key1")
        with pytest.raises(EtcdKeyNotFoundError):
            etcd.get("key1")

    def test_delete_nonexistent_is_safe(self, etcd):
        """Deleting a nonexistent key does not raise."""
        etcd.delete("nonexistent")  # Should not raise

    def test_list_keys_with_prefix(self, etcd):
        """list_keys filters by prefix."""
        etcd.put("/pods/pod-1", {})
        etcd.put("/pods/pod-2", {})
        etcd.put("/nodes/node-0", {})
        pod_keys = etcd.list_keys("/pods/")
        assert len(pod_keys) == 2
        assert all(k.startswith("/pods/") for k in pod_keys)

    def test_size(self, etcd):
        """Size reflects number of keys."""
        assert etcd.size == 0
        etcd.put("a", 1)
        etcd.put("b", 2)
        assert etcd.size == 2

    def test_history_tracking(self, etcd):
        """History records all mutations."""
        etcd.put("key1", "value1")
        etcd.put("key2", "value2")
        etcd.delete("key1")
        history = etcd.get_history()
        assert len(history) == 3
        assert history[0]["action"] == "PUT"
        assert history[2]["action"] == "DELETE"

    def test_overwrite_key(self, etcd):
        """Overwriting a key updates its value."""
        etcd.put("key1", "old")
        etcd.put("key1", "new")
        assert etcd.get("key1") == "new"


# ===========================================================================
# FizzKubeScheduler Tests
# ===========================================================================


class TestFizzKubeScheduler:
    """Tests for the FizzKube pod scheduler."""

    def test_schedule_to_empty_node(self, scheduler, three_nodes):
        """Scheduler selects a node for a pod."""
        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        node = scheduler.schedule(pod, three_nodes)
        assert node in three_nodes

    def test_schedule_prefers_least_utilized(self, scheduler, three_nodes):
        """Scheduler prefers the node with the lowest utilization."""
        # Load up node 0 and 1
        heavy_pod_0 = Pod(spec=PodSpec(cpu_request=3000, memory_request=4096))
        three_nodes[0].allocate(heavy_pod_0)

        heavy_pod_1 = Pod(spec=PodSpec(cpu_request=2000, memory_request=3000))
        three_nodes[1].allocate(heavy_pod_1)

        # Node 2 is empty, should be preferred
        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        selected = scheduler.schedule(pod, three_nodes)
        assert selected.name == "test-node-2"

    def test_schedule_fails_when_no_capacity(self, scheduler):
        """Scheduler raises PodSchedulingError when no node fits."""
        tiny_nodes = [
            WorkerNode(name="tiny-0", capacity=ResourceUnits(50, 64)),
        ]
        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        with pytest.raises(PodSchedulingError):
            scheduler.schedule(pod, tiny_nodes)

    def test_schedule_skips_not_ready_nodes(self, scheduler, three_nodes):
        """Scheduler skips nodes that are not in Ready condition."""
        three_nodes[0].condition = NodeCondition.NOT_READY
        three_nodes[1].condition = NodeCondition.DISK_PRESSURE

        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        selected = scheduler.schedule(pod, three_nodes)
        assert selected.name == "test-node-2"

    def test_schedule_all_not_ready_fails(self, scheduler, three_nodes):
        """Scheduler fails when all nodes are not ready."""
        for node in three_nodes:
            node.condition = NodeCondition.NOT_READY

        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        with pytest.raises(PodSchedulingError):
            scheduler.schedule(pod, three_nodes)

    def test_schedule_checks_quota(self, scheduler, three_nodes):
        """Scheduler respects namespace resource quotas."""
        quota = ResourceQuota(cpu_limit=50, memory_limit=64)
        ns = Namespace(name="test-ns", resource_quota=quota)

        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        with pytest.raises(ResourceQuotaExceededError):
            scheduler.schedule(pod, three_nodes, namespace=ns)

    def test_schedule_count_increments(self, scheduler, three_nodes):
        """Schedule count tracks total scheduling decisions."""
        pod1 = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        pod2 = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        scheduler.schedule(pod1, three_nodes)
        scheduler.schedule(pod2, three_nodes)
        assert scheduler.schedule_count == 2

    def test_filter_log_records_decisions(self, scheduler, three_nodes):
        """Filter log captures filter decisions."""
        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        scheduler.schedule(pod, three_nodes)
        assert len(scheduler.filter_log) == 1
        assert len(scheduler.filter_log[0]["results"]) == 3

    def test_score_log_records_scores(self, scheduler, three_nodes):
        """Score log captures scoring decisions."""
        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        scheduler.schedule(pod, three_nodes)
        assert len(scheduler.score_log) == 1


# ===========================================================================
# ReplicaSet Tests
# ===========================================================================


class TestReplicaSet:
    """Tests for the ReplicaSet controller."""

    def test_initial_state(self):
        """ReplicaSet starts with correct defaults."""
        rs = ReplicaSet(name="test-rs", desired=3)
        assert rs.name == "test-rs"
        assert rs.desired == 3
        assert rs.current == 0
        assert rs.generation == 0

    def test_reconcile_creates_pods(self):
        """Reconciliation creates pods to reach desired count."""
        rs = ReplicaSet(desired=3)

        def make_pod():
            return Pod(phase=PodPhase.PENDING)

        new_pods = rs.reconcile(make_pod)
        assert len(new_pods) == 3
        assert rs.reconciliation_count == 1

    def test_reconcile_no_change_when_at_desired(self):
        """Reconciliation does nothing when already at desired count."""
        rs = ReplicaSet(desired=2)

        pod1 = Pod(phase=PodPhase.RUNNING)
        pod2 = Pod(phase=PodPhase.RUNNING)
        rs.add_pod(pod1)
        rs.add_pod(pod2)

        new_pods = rs.reconcile(lambda: Pod())
        assert len(new_pods) == 0

    def test_reconcile_replaces_failed_pods(self):
        """Reconciliation creates replacements for failed pods."""
        rs = ReplicaSet(desired=2)

        pod1 = Pod(phase=PodPhase.RUNNING)
        pod2 = Pod(phase=PodPhase.FAILED)
        rs.add_pod(pod1)
        rs.add_pod(pod2)

        new_pods = rs.reconcile(lambda: Pod(phase=PodPhase.PENDING))
        assert len(new_pods) == 1

    def test_reconcile_terminates_excess(self):
        """Reconciliation terminates excess pods when scaling down."""
        rs = ReplicaSet(desired=1)

        pods = [Pod(phase=PodPhase.RUNNING) for _ in range(3)]
        for p in pods:
            rs.add_pod(p)

        rs.reconcile(lambda: Pod())
        # 2 excess should be Failed
        failed = [p for p in rs.pods if p.phase == PodPhase.FAILED]
        assert len(failed) == 2

    def test_desired_setter_clamps_negative(self):
        """Desired count cannot go below zero."""
        rs = ReplicaSet(desired=5)
        rs.desired = -3
        assert rs.desired == 0

    def test_generation_increments_on_change(self):
        """Generation increments when desired count changes."""
        rs = ReplicaSet(desired=2)
        assert rs.generation == 0
        rs.desired = 4
        assert rs.generation == 1

    def test_history_records_actions(self):
        """ReplicaSet history records create and terminate actions."""
        rs = ReplicaSet(desired=2)
        rs.reconcile(lambda: Pod(phase=PodPhase.PENDING))
        assert len(rs.history) == 2
        assert all(h["action"] == "create" for h in rs.history)


# ===========================================================================
# HorizontalPodAutoscaler Tests
# ===========================================================================


class TestHorizontalPodAutoscaler:
    """Tests for the Horizontal Pod Autoscaler."""

    def test_no_change_at_target(self):
        """HPA does not scale when at target utilization."""
        hpa = HorizontalPodAutoscaler(target_cpu_utilization=50)
        rs = ReplicaSet(desired=2)
        nodes = [
            WorkerNode(name="n0", capacity=ResourceUnits(1000, 1000)),
        ]
        # Set utilization to exactly 50%
        nodes[0].allocated = ResourceUnits(500, 500)

        result = hpa.evaluate(rs, nodes)
        assert result is None  # no change
        assert rs.desired == 2

    def test_scale_up_on_high_utilization(self):
        """HPA scales up when utilization exceeds target."""
        hpa = HorizontalPodAutoscaler(
            target_cpu_utilization=50,
            min_replicas=1,
            max_replicas=10,
        )
        rs = ReplicaSet(desired=2)
        nodes = [
            WorkerNode(name="n0", capacity=ResourceUnits(1000, 1000)),
        ]
        # Set utilization to 90% (well above 50% target)
        nodes[0].allocated = ResourceUnits(900, 500)

        result = hpa.evaluate(rs, nodes)
        assert result is not None
        assert rs.desired > 2  # Should have scaled up

    def test_scale_down_on_low_utilization(self):
        """HPA scales down when utilization is below target."""
        hpa = HorizontalPodAutoscaler(
            target_cpu_utilization=70,
            min_replicas=1,
            max_replicas=10,
        )
        rs = ReplicaSet(desired=5)
        nodes = [
            WorkerNode(name="n0", capacity=ResourceUnits(1000, 1000)),
        ]
        # Set utilization to 10% (well below 70% target)
        nodes[0].allocated = ResourceUnits(100, 100)

        result = hpa.evaluate(rs, nodes)
        assert result is not None
        assert rs.desired < 5  # Should have scaled down

    def test_respects_min_replicas(self):
        """HPA does not scale below min_replicas."""
        hpa = HorizontalPodAutoscaler(
            target_cpu_utilization=70,
            min_replicas=3,
            max_replicas=10,
        )
        rs = ReplicaSet(desired=5)
        nodes = [
            WorkerNode(name="n0", capacity=ResourceUnits(1000, 1000)),
        ]
        # Zero utilization - would want to scale to 1
        nodes[0].allocated = ResourceUnits(0, 0)

        hpa.evaluate(rs, nodes)
        assert rs.desired >= 3

    def test_respects_max_replicas(self):
        """HPA does not scale above max_replicas."""
        hpa = HorizontalPodAutoscaler(
            target_cpu_utilization=10,
            min_replicas=1,
            max_replicas=5,
        )
        rs = ReplicaSet(desired=4)
        nodes = [
            WorkerNode(name="n0", capacity=ResourceUnits(1000, 1000)),
        ]
        # 100% utilization - would want to scale way up
        nodes[0].allocated = ResourceUnits(1000, 1000)

        hpa.evaluate(rs, nodes)
        assert rs.desired <= 5

    def test_scaling_history_recorded(self):
        """HPA records scaling decisions in history."""
        hpa = HorizontalPodAutoscaler(target_cpu_utilization=50)
        rs = ReplicaSet(desired=2)
        nodes = [
            WorkerNode(name="n0", capacity=ResourceUnits(1000, 1000)),
        ]
        nodes[0].allocated = ResourceUnits(500, 500)

        hpa.evaluate(rs, nodes)
        assert len(hpa.scaling_history) == 1

    def test_no_nodes_returns_none(self):
        """HPA returns None when there are no nodes."""
        hpa = HorizontalPodAutoscaler()
        rs = ReplicaSet(desired=2)
        result = hpa.evaluate(rs, [])
        assert result is None


# ===========================================================================
# FizzKubeControlPlane Tests
# ===========================================================================


class TestFizzKubeControlPlane:
    """Tests for the FizzKube control plane."""

    def test_initialization(self, control_plane):
        """Control plane initializes with correct number of nodes."""
        assert len(control_plane.nodes) == 3
        assert control_plane.evaluation_count == 0
        assert control_plane.etcd.size > 0  # nodes + namespace stored

    def test_evaluate_creates_pod(self, control_plane):
        """Evaluation creates a pod."""
        result, pod = control_plane.evaluate(15)
        assert result == "FizzBuzz"
        assert pod.phase == PodPhase.SUCCEEDED
        assert pod.node_name is not None
        assert control_plane.total_pods_created == 1

    def test_evaluate_fizz(self, control_plane):
        """Evaluation correctly identifies Fizz."""
        result, pod = control_plane.evaluate(3)
        assert result == "Fizz"
        assert pod.phase == PodPhase.SUCCEEDED

    def test_evaluate_buzz(self, control_plane):
        """Evaluation correctly identifies Buzz."""
        result, pod = control_plane.evaluate(5)
        assert result == "Buzz"
        assert pod.phase == PodPhase.SUCCEEDED

    def test_evaluate_plain_number(self, control_plane):
        """Evaluation returns the number for non-FizzBuzz values."""
        result, pod = control_plane.evaluate(7)
        assert result == "7"
        assert pod.phase == PodPhase.SUCCEEDED

    def test_evaluate_fizzbuzz(self, control_plane):
        """Evaluation correctly identifies FizzBuzz."""
        result, pod = control_plane.evaluate(30)
        assert result == "FizzBuzz"

    def test_multiple_evaluations(self, control_plane):
        """Multiple evaluations create multiple pods."""
        for n in range(1, 11):
            control_plane.evaluate(n)
        assert control_plane.evaluation_count == 10
        assert control_plane.total_pods_created == 10

    def test_pods_distributed_across_nodes(self, control_plane):
        """Pods are distributed across nodes by the scheduler."""
        # Run enough evaluations to spread across nodes
        for n in range(1, 16):
            control_plane.evaluate(n)

        # All pods should have been assigned to a node
        for pod in control_plane.all_pods:
            assert pod.node_name is not None

    def test_succeeded_pods_tracked(self, control_plane):
        """Succeeded pods are tracked separately."""
        control_plane.evaluate(15)
        assert len(control_plane.succeeded_pods) == 1

    def test_etcd_stores_pod_state(self, control_plane):
        """Pod state is stored in etcd."""
        control_plane.evaluate(15)
        pod = control_plane.all_pods[0]
        stored = control_plane.etcd.get(f"/pods/{pod.name}")
        assert stored["phase"] == "SUCCEEDED"
        assert stored["result"] == "FizzBuzz"

    def test_namespace_exists(self, control_plane):
        """Namespace is created with correct name."""
        assert control_plane.namespace.name == "fizzbuzz-production"

    def test_cluster_utilization_starts_at_zero(self, control_plane):
        """Initial cluster utilization is zero."""
        assert control_plane.cluster_cpu_utilization == 0.0
        assert control_plane.cluster_memory_utilization == 0.0

    def test_get_cluster_summary(self, control_plane):
        """Cluster summary returns expected keys."""
        control_plane.evaluate(15)
        summary = control_plane.get_cluster_summary()
        assert "nodes" in summary
        assert "total_pods" in summary
        assert "evaluations" in summary
        assert summary["evaluations"] == 1

    def test_hpa_integration(self):
        """HPA evaluates periodically during evaluations."""
        cp = FizzKubeControlPlane(
            num_nodes=2,
            cpu_per_node=1000,
            memory_per_node=2048,
            hpa_enabled=True,
        )
        # Run 5 evaluations to trigger HPA
        for n in range(1, 6):
            cp.evaluate(n)
        assert cp.hpa is not None
        assert len(cp.hpa.scaling_history) >= 1

    def test_control_plane_without_hpa(self):
        """Control plane works without HPA."""
        cp = FizzKubeControlPlane(hpa_enabled=False)
        result, pod = cp.evaluate(15)
        assert result == "FizzBuzz"
        assert cp.hpa is None


# ===========================================================================
# FizzKubeDashboard Tests
# ===========================================================================


class TestFizzKubeDashboard:
    """Tests for the FizzKube ASCII dashboard."""

    def test_render_empty_cluster(self, control_plane):
        """Dashboard renders for an empty cluster."""
        output = FizzKubeDashboard.render(control_plane)
        assert "FIZZKUBE CONTAINER ORCHESTRATION" in output
        assert "CLUSTER OVERVIEW" in output
        assert "NODE TOPOLOGY" in output

    def test_render_after_evaluations(self, control_plane):
        """Dashboard renders after evaluations."""
        for n in range(1, 6):
            control_plane.evaluate(n)
        output = FizzKubeDashboard.render(control_plane)
        assert "RECENT PODS" in output
        assert "REPLICASET" in output

    def test_render_includes_node_bars(self, control_plane):
        """Dashboard includes CPU and memory utilization bars."""
        output = FizzKubeDashboard.render(control_plane)
        assert "CPU:" in output
        assert "MEM:" in output

    def test_render_custom_width(self, control_plane):
        """Dashboard respects custom width."""
        output = FizzKubeDashboard.render(control_plane, width=80)
        lines = output.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") or stripped.startswith("+"):
                assert len(stripped) <= 80

    def test_render_with_hpa_history(self):
        """Dashboard shows HPA history when available."""
        cp = FizzKubeControlPlane(num_nodes=2, hpa_enabled=True)
        for n in range(1, 11):
            cp.evaluate(n)
        output = FizzKubeDashboard.render(cp)
        assert "HPA SCALING HISTORY" in output


# ===========================================================================
# FizzKubeMiddleware Tests
# ===========================================================================


class TestFizzKubeMiddleware:
    """Tests for the FizzKube middleware integration."""

    def test_middleware_name(self, control_plane):
        """Middleware reports correct name."""
        mw = FizzKubeMiddleware(control_plane)
        assert mw.get_name() == "FizzKubeMiddleware"

    def test_middleware_priority(self, control_plane):
        """Middleware has priority -11."""
        mw = FizzKubeMiddleware(control_plane)
        assert mw.get_priority() == -11

    def test_middleware_processes_fizzbuzz(self, control_plane):
        """Middleware correctly processes a FizzBuzz number."""
        mw = FizzKubeMiddleware(control_plane)
        ctx = ProcessingContext(number=15, session_id="test-session")

        result = mw.process(ctx, lambda c: c)

        assert len(result.results) == 1
        assert result.results[0].output == "FizzBuzz"
        assert result.results[0].metadata["strategy"] == "fizzkube"

    def test_middleware_processes_fizz(self, control_plane):
        """Middleware correctly processes a Fizz number."""
        mw = FizzKubeMiddleware(control_plane)
        ctx = ProcessingContext(number=9, session_id="test-session")

        result = mw.process(ctx, lambda c: c)

        assert result.results[0].output == "Fizz"

    def test_middleware_processes_buzz(self, control_plane):
        """Middleware correctly processes a Buzz number."""
        mw = FizzKubeMiddleware(control_plane)
        ctx = ProcessingContext(number=10, session_id="test-session")

        result = mw.process(ctx, lambda c: c)

        assert result.results[0].output == "Buzz"

    def test_middleware_processes_plain(self, control_plane):
        """Middleware correctly processes a plain number."""
        mw = FizzKubeMiddleware(control_plane)
        ctx = ProcessingContext(number=7, session_id="test-session")

        result = mw.process(ctx, lambda c: c)

        assert result.results[0].output == "7"

    def test_middleware_injects_metadata(self, control_plane):
        """Middleware injects FizzKube metadata into context."""
        mw = FizzKubeMiddleware(control_plane)
        ctx = ProcessingContext(number=15, session_id="test-session")

        result = mw.process(ctx, lambda c: c)

        assert "fizzkube_pod" in result.metadata
        assert "fizzkube_node" in result.metadata
        assert "fizzkube_phase" in result.metadata
        assert "fizzkube_execution_ns" in result.metadata


# ===========================================================================
# Exception Tests
# ===========================================================================


class TestFizzKubeExceptions:
    """Tests for FizzKube exception hierarchy."""

    def test_fizzkube_error_base(self):
        """FizzKubeError is the base exception."""
        err = FizzKubeError("test error")
        assert "EFP-KB00" in str(err)

    def test_pod_scheduling_error(self):
        """PodSchedulingError has correct error code."""
        err = PodSchedulingError("my-pod", "no nodes available")
        assert "EFP-KB01" in str(err)
        assert err.pod_name == "my-pod"

    def test_node_not_ready_error(self):
        """NodeNotReadyError has correct error code."""
        err = NodeNotReadyError("node-0", "NOT_READY")
        assert "EFP-KB02" in str(err)
        assert err.node_name == "node-0"

    def test_resource_quota_exceeded_error(self):
        """ResourceQuotaExceededError has correct error code."""
        err = ResourceQuotaExceededError("test-ns", "cpu", 1000.0, 1500.0)
        assert "EFP-KB03" in str(err)
        assert err.namespace == "test-ns"

    def test_etcd_key_not_found_error(self):
        """EtcdKeyNotFoundError has correct error code."""
        err = EtcdKeyNotFoundError("/missing/key")
        assert "EFP-KB04" in str(err)
        assert err.key == "/missing/key"

    def test_hpa_scaling_error(self):
        """HPAScalingError has correct error code."""
        err = HPAScalingError("my-rs", "cluster at capacity")
        assert "EFP-KB05" in str(err)
        assert err.replica_set == "my-rs"

    def test_all_exceptions_inherit_from_fizzkube_error(self):
        """All FizzKube exceptions inherit from FizzKubeError."""
        assert issubclass(PodSchedulingError, FizzKubeError)
        assert issubclass(NodeNotReadyError, FizzKubeError)
        assert issubclass(ResourceQuotaExceededError, FizzKubeError)
        assert issubclass(EtcdKeyNotFoundError, FizzKubeError)
        assert issubclass(HPAScalingError, FizzKubeError)


# ===========================================================================
# EventType Tests
# ===========================================================================


class TestFizzKubeEventTypes:
    """Tests for FizzKube-related EventType entries."""

    def test_fizzkube_event_types_exist(self):
        """All FizzKube EventType entries exist."""
        expected = [
            "FIZZKUBE_POD_CREATED",
            "FIZZKUBE_POD_SCHEDULED",
            "FIZZKUBE_POD_RUNNING",
            "FIZZKUBE_POD_SUCCEEDED",
            "FIZZKUBE_POD_FAILED",
            "FIZZKUBE_NODE_ADDED",
            "FIZZKUBE_NODE_CONDITION_CHANGED",
            "FIZZKUBE_SCHEDULER_FILTER",
            "FIZZKUBE_SCHEDULER_SCORE",
            "FIZZKUBE_REPLICASET_RECONCILE",
            "FIZZKUBE_HPA_SCALE",
            "FIZZKUBE_HPA_DECISION",
            "FIZZKUBE_ETCD_PUT",
            "FIZZKUBE_ETCD_GET",
            "FIZZKUBE_DASHBOARD_RENDERED",
        ]
        for name in expected:
            assert hasattr(EventType, name), f"EventType.{name} not found"


# ===========================================================================
# PodPhase / NodeCondition Enum Tests
# ===========================================================================


class TestEnums:
    """Tests for FizzKube enumerations."""

    def test_pod_phases(self):
        """All expected PodPhase values exist."""
        assert PodPhase.PENDING is not None
        assert PodPhase.RUNNING is not None
        assert PodPhase.SUCCEEDED is not None
        assert PodPhase.FAILED is not None

    def test_node_conditions(self):
        """All expected NodeCondition values exist."""
        assert NodeCondition.READY is not None
        assert NodeCondition.NOT_READY is not None
        assert NodeCondition.DISK_PRESSURE is not None
        assert NodeCondition.MEMORY_PRESSURE is not None
        assert NodeCondition.PID_PRESSURE is not None


# ===========================================================================
# Integration / Edge Case Tests
# ===========================================================================


class TestFizzKubeEdgeCases:
    """Integration and edge case tests."""

    def test_evaluate_large_range(self):
        """Control plane handles a large range without errors."""
        cp = FizzKubeControlPlane(num_nodes=3)
        for n in range(1, 51):
            result, pod = cp.evaluate(n)
            assert pod.phase == PodPhase.SUCCEEDED

    def test_single_node_cluster(self):
        """Single-node cluster works correctly."""
        cp = FizzKubeControlPlane(num_nodes=1)
        result, pod = cp.evaluate(15)
        assert result == "FizzBuzz"
        assert pod.node_name == "fizzkube-node-0"

    def test_node_condition_change_blocks_scheduling(self, three_nodes, scheduler):
        """Changing a node to NOT_READY prevents scheduling to it."""
        three_nodes[0].condition = NodeCondition.NOT_READY
        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        selected = scheduler.schedule(pod, three_nodes)
        assert selected.name != "test-node-0"

    def test_pod_execution_time_tracked(self, control_plane):
        """Pod execution time is recorded in nanoseconds."""
        _, pod = control_plane.evaluate(15)
        assert pod.execution_time_ns > 0

    def test_namespace_with_no_quota_works(self, scheduler, three_nodes):
        """Scheduling works in a namespace without a quota."""
        ns = Namespace(name="no-quota-ns")
        pod = Pod(spec=PodSpec(cpu_request=100, memory_request=128))
        selected = scheduler.schedule(pod, three_nodes, namespace=ns)
        assert selected is not None

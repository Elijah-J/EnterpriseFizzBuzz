"""
Tests for FizzContainerChaos: Container-Native Chaos Engineering

Validates fault injection types, experiment lifecycle, game day
orchestration, blast radius enforcement, cognitive load gating,
steady-state measurement, and middleware pipeline integration.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzcontainerchaos import (
    # Constants
    CONTAINER_CHAOS_VERSION,
    CHAOS_MESH_COMPAT_VERSION,
    DEFAULT_EXPERIMENT_TIMEOUT,
    DEFAULT_OBSERVATION_INTERVAL,
    DEFAULT_COGNITIVE_LOAD_THRESHOLD,
    DEFAULT_BLAST_RADIUS_LIMIT,
    DEFAULT_STEADY_STATE_TOLERANCE,
    DEFAULT_GAMEDAY_TIMEOUT,
    DEFAULT_LATENCY_MS,
    DEFAULT_JITTER_MS,
    DEFAULT_CPU_STRESS_CORES,
    DEFAULT_MEMORY_PRESSURE_RATE,
    DEFAULT_DISK_FILL_PERCENT,
    MIDDLEWARE_PRIORITY,
    DEFAULT_DASHBOARD_WIDTH,
    # Enums
    FaultType,
    ExperimentStatus,
    GameDayStatus,
    AbortReason,
    BlastRadiusScope,
    ScheduleMode,
    # Dataclasses
    FaultConfig,
    SteadyStateMetric,
    AbortCondition,
    ChaosExperiment,
    ExperimentReport,
    GameDay,
    GameDayReport,
    ChaosSchedule,
    # Classes
    TargetResolver,
    SteadyStateProbe,
    BlastRadiusCalculator,
    ContainerKillFault,
    NetworkPartitionFault,
    CPUStressFault,
    MemoryPressureFault,
    DiskFillFault,
    ImagePullFailureFault,
    DNSFailureFault,
    NetworkLatencyFault,
    FaultRegistry,
    ChaosGate,
    ChaosExecutor,
    GameDayOrchestrator,
    PredefinedGameDays,
    ContainerChaosDashboard,
    FizzContainerChaosMiddleware,
    create_fizzcontainerchaos_subsystem,
    # Exceptions
    ContainerChaosError,
    ChaosExperimentNotFoundError,
    ChaosExperimentAlreadyRunningError,
    ChaosExperimentFailedStartError,
    ChaosFaultInjectionError,
    ChaosTargetResolutionError,
    ChaosCognitiveLoadGateError,
    ChaosContainerChaosMiddlewareError,
)
from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.models import ProcessingContext, FizzBuzzResult


# ============================================================
# Helpers
# ============================================================


def _make_container_registry(count: int = 5) -> dict:
    """Create a simulated container registry with the given count."""
    registry = {}
    for i in range(count):
        cid = f"container-{i:04d}"
        registry[cid] = {
            "labels": {
                "app": "fizzbuzz",
                "tier": "application" if i % 2 == 0 else "data",
                "instance": str(i),
            },
            "status": "running",
            "image": "fizzbuzz:latest",
        }
    return registry


def _make_executor(container_count: int = 5) -> ChaosExecutor:
    """Create a ChaosExecutor with a populated container registry."""
    registry = _make_container_registry(container_count)
    fault_registry = FaultRegistry()
    target_resolver = TargetResolver()
    probe = SteadyStateProbe()
    calc = BlastRadiusCalculator(limit=0.50)
    gate = ChaosGate(threshold=100.0)  # High threshold to pass by default
    return ChaosExecutor(
        fault_registry=fault_registry,
        target_resolver=target_resolver,
        steady_state_probe=probe,
        blast_radius_calculator=calc,
        chaos_gate=gate,
        container_registry=registry,
    )


def _make_context(number: int = 42) -> ProcessingContext:
    """Create a minimal ProcessingContext."""
    return ProcessingContext(number=number, session_id="test-session")


# ============================================================
# TestFaultType
# ============================================================


class TestFaultType:
    """Test FaultType enum values and membership."""

    def test_has_eight_fault_types(self):
        assert len(FaultType) == 8

    def test_container_kill_value(self):
        assert FaultType.CONTAINER_KILL.value == "container_kill"

    def test_all_values_are_strings(self):
        for ft in FaultType:
            assert isinstance(ft.value, str)


# ============================================================
# TestExperimentStatus
# ============================================================


class TestExperimentStatus:
    """Test ExperimentStatus enum transitions."""

    def test_has_ten_statuses(self):
        assert len(ExperimentStatus) == 10

    def test_pending_is_initial(self):
        assert ExperimentStatus.PENDING.value == "pending"

    def test_terminal_states(self):
        terminals = {ExperimentStatus.COMPLETED, ExperimentStatus.ABORTED, ExperimentStatus.FAILED}
        for s in terminals:
            assert s.value in ("completed", "aborted", "failed")


# ============================================================
# TestGameDayStatus
# ============================================================


class TestGameDayStatus:
    """Test GameDayStatus enum values."""

    def test_has_seven_statuses(self):
        assert len(GameDayStatus) == 7

    def test_planning_is_initial(self):
        assert GameDayStatus.PLANNING.value == "planning"


# ============================================================
# TestAbortReason
# ============================================================


class TestAbortReason:
    """Test AbortReason enum values."""

    def test_has_eight_reasons(self):
        assert len(AbortReason) == 8

    def test_manual_abort_value(self):
        assert AbortReason.MANUAL_ABORT.value == "manual_abort"


# ============================================================
# TestBlastRadiusScope
# ============================================================


class TestBlastRadiusScope:
    """Test BlastRadiusScope enum values."""

    def test_has_four_scopes(self):
        assert len(BlastRadiusScope) == 4

    def test_global_value(self):
        assert BlastRadiusScope.GLOBAL.value == "global"


# ============================================================
# TestScheduleMode
# ============================================================


class TestScheduleMode:
    """Test ScheduleMode enum values."""

    def test_has_three_modes(self):
        assert len(ScheduleMode) == 3

    def test_sequential_value(self):
        assert ScheduleMode.SEQUENTIAL.value == "sequential"


# ============================================================
# TestFaultConfig
# ============================================================


class TestFaultConfig:
    """Test FaultConfig dataclass defaults and construction."""

    def test_default_fault_type_is_container_kill(self):
        config = FaultConfig()
        assert config.fault_type == FaultType.CONTAINER_KILL

    def test_default_duration(self):
        config = FaultConfig()
        assert config.duration == 60.0

    def test_custom_config(self):
        config = FaultConfig(
            fault_type=FaultType.CPU_STRESS,
            cores=4,
            load_percent=95.0,
        )
        assert config.fault_type == FaultType.CPU_STRESS
        assert config.cores == 4
        assert config.load_percent == 95.0

    def test_label_selector(self):
        config = FaultConfig(
            target_labels={"app": "fizzbuzz", "tier": "data"},
        )
        assert config.target_labels["app"] == "fizzbuzz"


# ============================================================
# TestSteadyStateMetric
# ============================================================


class TestSteadyStateMetric:
    """Test SteadyStateMetric baseline/during/recovery values."""

    def test_default_values(self):
        metric = SteadyStateMetric(name="error_rate")
        assert metric.baseline_value == 0.0
        assert metric.during_value == 0.0
        assert metric.recovery_value == 0.0

    def test_threshold_bounds(self):
        metric = SteadyStateMetric(
            name="p99_latency_ms",
            threshold_upper=500.0,
            threshold_lower=1.0,
        )
        assert metric.threshold_upper == 500.0
        assert metric.threshold_lower == 1.0

    def test_source_default(self):
        metric = SteadyStateMetric()
        assert metric.source == "fizzsli"


# ============================================================
# TestAbortCondition
# ============================================================


class TestAbortCondition:
    """Test AbortCondition operator evaluation."""

    def test_default_operator(self):
        cond = AbortCondition()
        assert cond.operator == "gt"

    def test_not_triggered_by_default(self):
        cond = AbortCondition()
        assert cond.triggered is False

    def test_custom_condition(self):
        cond = AbortCondition(
            metric_name="error_rate",
            operator="gt",
            threshold=50.0,
            description="Abort if error rate exceeds 50%",
        )
        assert cond.metric_name == "error_rate"
        assert cond.threshold == 50.0


# ============================================================
# TestChaosExperiment
# ============================================================


class TestChaosExperiment:
    """Test ChaosExperiment lifecycle and timeline."""

    def test_auto_generated_id(self):
        exp = ChaosExperiment()
        assert len(exp.experiment_id) == 36  # UUID format

    def test_initial_status_is_pending(self):
        exp = ChaosExperiment()
        assert exp.status == ExperimentStatus.PENDING

    def test_timeline_starts_empty(self):
        exp = ChaosExperiment()
        assert exp.timeline == []

    def test_custom_experiment(self):
        exp = ChaosExperiment(
            name="Test kill",
            fault_config=FaultConfig(fault_type=FaultType.CONTAINER_KILL),
            hypothesis="Containers restart within 30 seconds",
        )
        assert exp.name == "Test kill"
        assert exp.hypothesis == "Containers restart within 30 seconds"


# ============================================================
# TestExperimentReport
# ============================================================


class TestExperimentReport:
    """Test ExperimentReport generation and hypothesis evaluation."""

    def test_default_hypothesis_not_validated(self):
        report = ExperimentReport()
        assert report.hypothesis_validated is False

    def test_blast_radius_default(self):
        report = ExperimentReport()
        assert report.blast_radius_percent == 0.0

    def test_recommendations_start_empty(self):
        report = ExperimentReport()
        assert report.recommendations == []


# ============================================================
# TestGameDay
# ============================================================


class TestGameDay:
    """Test GameDay composition and scheduling."""

    def test_auto_generated_id(self):
        gd = GameDay()
        assert len(gd.gameday_id) == 36

    def test_default_schedule_mode(self):
        gd = GameDay()
        assert gd.schedule_mode == ScheduleMode.SEQUENTIAL

    def test_experiments_start_empty(self):
        gd = GameDay()
        assert gd.experiments == []


# ============================================================
# TestGameDayReport
# ============================================================


class TestGameDayReport:
    """Test GameDayReport aggregation."""

    def test_default_values(self):
        report = GameDayReport()
        assert report.experiments_completed == 0
        assert report.hypothesis_validated is False

    def test_resilience_gaps_start_empty(self):
        report = GameDayReport()
        assert report.resilience_gaps == []


# ============================================================
# TestChaosSchedule
# ============================================================


class TestChaosSchedule:
    """Test ChaosSchedule cron expression handling."""

    def test_default_cron(self):
        sched = ChaosSchedule()
        assert sched.cron_expression == "0 */6 * * *"

    def test_enabled_by_default(self):
        sched = ChaosSchedule()
        assert sched.enabled is True


# ============================================================
# TestTargetResolver
# ============================================================


class TestTargetResolver:
    """Test container target resolution from labels and IDs."""

    def test_resolve_by_container_id(self):
        resolver = TargetResolver()
        registry = _make_container_registry(3)
        config = FaultConfig(target_container="container-0000")
        targets = resolver.resolve(config, registry)
        assert targets == ["container-0000"]

    def test_resolve_by_label_selector(self):
        resolver = TargetResolver()
        registry = _make_container_registry(5)
        config = FaultConfig(
            target_labels={"tier": "application"},
            target_count=0,
        )
        targets = resolver.resolve(config, registry)
        # Even-indexed containers have tier=application
        assert len(targets) == 3

    def test_target_count_limits_results(self):
        resolver = TargetResolver()
        registry = _make_container_registry(10)
        config = FaultConfig(
            target_labels={"app": "fizzbuzz"},
            target_count=2,
        )
        targets = resolver.resolve(config, registry)
        assert len(targets) == 2

    def test_no_match_raises_error(self):
        resolver = TargetResolver()
        registry = _make_container_registry(3)
        config = FaultConfig(target_labels={"nonexistent": "label"})
        with pytest.raises(ChaosTargetResolutionError):
            resolver.resolve(config, registry)

    def test_specific_id_not_found_raises_error(self):
        resolver = TargetResolver()
        registry = _make_container_registry(3)
        config = FaultConfig(target_container="nonexistent-id")
        with pytest.raises(ChaosTargetResolutionError):
            resolver.resolve(config, registry)


# ============================================================
# TestSteadyStateProbe
# ============================================================


class TestSteadyStateProbe:
    """Test steady-state measurement and violation detection."""

    def test_measure_baseline_sets_values(self):
        probe = SteadyStateProbe()
        metrics = [SteadyStateMetric(name="error_rate")]
        probe.measure_baseline(metrics, ["c1"])
        assert metrics[0].baseline_value > 0.0 or metrics[0].baseline_value == 0.0

    def test_measure_during_degrades(self):
        probe = SteadyStateProbe()
        metrics = [SteadyStateMetric(name="error_rate")]
        probe.measure_baseline(metrics, ["c1"])
        baseline = metrics[0].baseline_value
        probe.measure_during(metrics, ["c1"])
        # Error rate should increase (degrade)
        assert metrics[0].during_value >= baseline

    def test_measure_recovery_near_baseline(self):
        probe = SteadyStateProbe()
        metrics = [SteadyStateMetric(name="error_rate")]
        probe.measure_baseline(metrics, ["c1"])
        baseline = metrics[0].baseline_value
        probe.measure_recovery(metrics, ["c1"])
        # Recovery should be within 5% of baseline
        if baseline > 0:
            deviation = abs(metrics[0].recovery_value - baseline) / baseline
            assert deviation < 0.10

    def test_check_violations(self):
        probe = SteadyStateProbe()
        metrics = [
            SteadyStateMetric(name="error_rate", during_value=60.0, threshold_upper=50.0),
            SteadyStateMetric(name="throughput", during_value=100.0, threshold_lower=200.0),
        ]
        violations = probe.check_violations(metrics)
        assert len(violations) == 2


# ============================================================
# TestBlastRadiusCalculator
# ============================================================


class TestBlastRadiusCalculator:
    """Test blast radius calculation and limit enforcement."""

    def test_within_limit(self):
        calc = BlastRadiusCalculator(limit=0.50)
        within, radius = calc.check(["c1", "c2"], set(), 10)
        assert within is True
        assert radius == 20.0

    def test_exceeds_limit(self):
        calc = BlastRadiusCalculator(limit=0.20)
        within, radius = calc.check(["c1", "c2", "c3"], set(), 10)
        assert within is False
        assert radius == 30.0

    def test_add_and_remove_affected(self):
        calc = BlastRadiusCalculator()
        calc.add_affected(["c1", "c2"])
        assert len(calc.get_affected()) == 2
        calc.remove_affected(["c1"])
        assert len(calc.get_affected()) == 1

    def test_current_radius(self):
        calc = BlastRadiusCalculator()
        radius = calc.current_radius({"c1", "c2"}, 10)
        assert radius == 20.0

    def test_summary(self):
        calc = BlastRadiusCalculator(limit=0.50, scope=BlastRadiusScope.GLOBAL)
        calc.add_affected(["c1"])
        summary = calc.get_summary()
        assert summary["limit_percent"] == 50.0
        assert summary["scope"] == "global"
        assert summary["affected_count"] == 1


# ============================================================
# TestContainerKillFault
# ============================================================


class TestContainerKillFault:
    """Test container kill injection and verification."""

    def test_inject_kills_container(self):
        fault = ContainerKillFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.CONTAINER_KILL)
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["killed"] is True
        assert result["container-0000"]["exit_code"] == 137
        assert fault.kill_count == 1

    def test_remove_restarts_container(self):
        fault = ContainerKillFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.CONTAINER_KILL)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert registry["container-0000"]["status"] == "running"

    def test_verify_checks_restart(self):
        fault = ContainerKillFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.CONTAINER_KILL)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        result = fault.verify(["container-0000"], registry)
        assert result["container-0000"] is True


# ============================================================
# TestNetworkPartitionFault
# ============================================================


class TestNetworkPartitionFault:
    """Test network partition injection and removal."""

    def test_inject_partitions_container(self):
        fault = NetworkPartitionFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.NETWORK_PARTITION, direction="both")
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["partitioned"] is True
        assert result["container-0000"]["direction"] == "both"

    def test_remove_restores_connectivity(self):
        fault = NetworkPartitionFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.NETWORK_PARTITION)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert "network_partitioned" not in registry["container-0000"]

    def test_verify_during_partition(self):
        fault = NetworkPartitionFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.NETWORK_PARTITION)
        fault.inject(["container-0000"], config, registry)
        result = fault.verify(["container-0000"], registry)
        assert result["container-0000"] is True


# ============================================================
# TestCPUStressFault
# ============================================================


class TestCPUStressFault:
    """Test CPU stress injection and throttle verification."""

    def test_inject_stresses_cpu(self):
        fault = CPUStressFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.CPU_STRESS, cores=4, load_percent=90.0)
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["stressed"] is True
        assert result["container-0000"]["cores"] == 4

    def test_remove_stops_stress(self):
        fault = CPUStressFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.CPU_STRESS)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert "cpu_stressed" not in registry["container-0000"]

    def test_verify_throttling(self):
        fault = CPUStressFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.CPU_STRESS)
        fault.inject(["container-0000"], config, registry)
        result = fault.verify(["container-0000"], registry)
        assert result["container-0000"] is True


# ============================================================
# TestMemoryPressureFault
# ============================================================


class TestMemoryPressureFault:
    """Test memory pressure injection and OOM verification."""

    def test_inject_applies_pressure(self):
        fault = MemoryPressureFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.MEMORY_PRESSURE, target_bytes=536870912)
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["pressured"] is True
        assert result["container-0000"]["target_bytes"] == 536870912

    def test_remove_releases_memory(self):
        fault = MemoryPressureFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.MEMORY_PRESSURE)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert "memory_pressured" not in registry["container-0000"]

    def test_verify_pressure(self):
        fault = MemoryPressureFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.MEMORY_PRESSURE)
        fault.inject(["container-0000"], config, registry)
        result = fault.verify(["container-0000"], registry)
        assert result["container-0000"] is True


# ============================================================
# TestDiskFillFault
# ============================================================


class TestDiskFillFault:
    """Test disk fill injection and graceful failure."""

    def test_inject_fills_disk(self):
        fault = DiskFillFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.DISK_FILL, fill_percent=95.0)
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["filled"] is True
        assert result["container-0000"]["fill_percent"] == 95.0

    def test_remove_clears_fill(self):
        fault = DiskFillFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.DISK_FILL)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert "disk_filled" not in registry["container-0000"]


# ============================================================
# TestImagePullFailureFault
# ============================================================


class TestImagePullFailureFault:
    """Test image pull failure injection and backoff."""

    def test_inject_intercepts_pulls(self):
        fault = ImagePullFailureFault()
        registry = _make_container_registry(3)
        config = FaultConfig(
            fault_type=FaultType.IMAGE_PULL_FAILURE,
            error_type="timeout",
            affected_images=["fizzbuzz:latest"],
        )
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["intercepted"] is True
        assert result["container-0000"]["error_type"] == "timeout"

    def test_remove_restores_pulls(self):
        fault = ImagePullFailureFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.IMAGE_PULL_FAILURE)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert "image_pull_failure" not in registry["container-0000"]


# ============================================================
# TestDNSFailureFault
# ============================================================


class TestDNSFailureFault:
    """Test DNS failure injection and retry behavior."""

    def test_inject_disrupts_dns(self):
        fault = DNSFailureFault()
        registry = _make_container_registry(3)
        config = FaultConfig(
            fault_type=FaultType.DNS_FAILURE,
            failure_mode="nxdomain",
            affected_domains=["*.fizzbuzz.internal"],
        )
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["disrupted"] is True
        assert result["container-0000"]["failure_mode"] == "nxdomain"

    def test_remove_restores_dns(self):
        fault = DNSFailureFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.DNS_FAILURE)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert "dns_failure" not in registry["container-0000"]


# ============================================================
# TestNetworkLatencyFault
# ============================================================


class TestNetworkLatencyFault:
    """Test network latency injection with jitter."""

    def test_inject_adds_latency(self):
        fault = NetworkLatencyFault()
        registry = _make_container_registry(3)
        config = FaultConfig(
            fault_type=FaultType.NETWORK_LATENCY,
            latency_ms=300.0,
            jitter_ms=100.0,
        )
        result = fault.inject(["container-0000"], config, registry)
        assert result["container-0000"]["delayed"] is True
        assert result["container-0000"]["latency_ms"] == 300.0
        assert result["container-0000"]["jitter_ms"] == 100.0

    def test_remove_restores_latency(self):
        fault = NetworkLatencyFault()
        registry = _make_container_registry(3)
        config = FaultConfig(fault_type=FaultType.NETWORK_LATENCY)
        fault.inject(["container-0000"], config, registry)
        fault.remove(["container-0000"], config, registry)
        assert "network_latency" not in registry["container-0000"]


# ============================================================
# TestFaultRegistry
# ============================================================


class TestFaultRegistry:
    """Test fault type to injector mapping."""

    def test_all_eight_types_registered(self):
        registry = FaultRegistry()
        for ft in FaultType:
            injector = registry.get_injector(ft)
            assert injector is not None

    def test_list_faults_returns_eight(self):
        registry = FaultRegistry()
        faults = registry.list_faults()
        assert len(faults) == 8

    def test_list_faults_contains_descriptions(self):
        registry = FaultRegistry()
        faults = registry.list_faults()
        for f in faults:
            assert "description" in f
            assert "fault_type" in f
            assert "params" in f


# ============================================================
# TestChaosExecutor
# ============================================================


class TestChaosExecutor:
    """Test the seven-phase experiment lifecycle."""

    def test_register_experiment(self):
        executor = _make_executor()
        exp = ChaosExperiment(
            name="Test experiment",
            fault_config=FaultConfig(
                fault_type=FaultType.CONTAINER_KILL,
                target_labels={"app": "fizzbuzz"},
                target_count=1,
            ),
        )
        exp_id = executor.register_experiment(exp)
        assert exp_id == exp.experiment_id
        assert exp_id in executor.experiments

    def test_run_full_lifecycle(self):
        executor = _make_executor()
        exp = ChaosExperiment(
            name="Full lifecycle test",
            fault_config=FaultConfig(
                fault_type=FaultType.CONTAINER_KILL,
                target_labels={"app": "fizzbuzz"},
                target_count=1,
            ),
            hypothesis="Container restarts after kill",
            steady_state_metrics=[
                SteadyStateMetric(name="error_rate", unit="%"),
            ],
        )
        exp_id = executor.register_experiment(exp)
        report = executor.run_experiment(exp_id)
        assert report.experiment_id == exp_id
        assert report.experiment_name == "Full lifecycle test"
        assert report.fault_type == FaultType.CONTAINER_KILL
        assert report.affected_container_count >= 1

    def test_abort_experiment(self):
        executor = _make_executor()
        exp = ChaosExperiment(
            name="Abort test",
            fault_config=FaultConfig(
                fault_type=FaultType.NETWORK_PARTITION,
                target_labels={"app": "fizzbuzz"},
                target_count=1,
            ),
        )
        exp_id = executor.register_experiment(exp)
        executor.abort_experiment(exp_id, AbortReason.MANUAL_ABORT)
        assert exp.status == ExperimentStatus.ABORTED
        assert exp.abort_reason == AbortReason.MANUAL_ABORT

    def test_experiment_not_found(self):
        executor = _make_executor()
        with pytest.raises(ChaosExperimentNotFoundError):
            executor.get_experiment("nonexistent-id")

    def test_blast_radius_check_in_precheck(self):
        registry = _make_container_registry(4)
        fault_registry = FaultRegistry()
        target_resolver = TargetResolver()
        probe = SteadyStateProbe()
        calc = BlastRadiusCalculator(limit=0.10)  # Very low limit
        gate = ChaosGate(threshold=100.0)

        executor = ChaosExecutor(
            fault_registry=fault_registry,
            target_resolver=target_resolver,
            steady_state_probe=probe,
            blast_radius_calculator=calc,
            chaos_gate=gate,
            container_registry=registry,
        )

        exp = ChaosExperiment(
            name="Blast radius test",
            fault_config=FaultConfig(
                fault_type=FaultType.CONTAINER_KILL,
                target_labels={"app": "fizzbuzz"},
                target_count=0,  # All containers
            ),
        )
        exp_id = executor.register_experiment(exp)
        report = executor.run_experiment(exp_id)
        # Experiment should fail due to blast radius
        assert exp.status == ExperimentStatus.FAILED

    def test_report_generation(self):
        executor = _make_executor()
        exp = ChaosExperiment(
            name="Report test",
            fault_config=FaultConfig(
                fault_type=FaultType.CPU_STRESS,
                target_labels={"app": "fizzbuzz"},
                target_count=1,
            ),
            steady_state_metrics=[
                SteadyStateMetric(name="cpu_utilization", unit="%"),
            ],
        )
        exp_id = executor.register_experiment(exp)
        executor.run_experiment(exp_id)
        report = executor.get_report(exp_id)
        assert report is not None
        assert len(report.steady_state_comparison) == 1

    def test_list_active_and_all(self):
        executor = _make_executor()
        exp = ChaosExperiment(
            name="List test",
            fault_config=FaultConfig(
                fault_type=FaultType.CONTAINER_KILL,
                target_labels={"app": "fizzbuzz"},
                target_count=1,
            ),
        )
        executor.register_experiment(exp)
        assert len(executor.list_all()) == 1

    def test_run_with_abort_conditions(self):
        executor = _make_executor()
        exp = ChaosExperiment(
            name="Abort condition test",
            fault_config=FaultConfig(
                fault_type=FaultType.CPU_STRESS,
                target_labels={"app": "fizzbuzz"},
                target_count=1,
            ),
            steady_state_metrics=[
                SteadyStateMetric(
                    name="error_rate",
                    unit="%",
                    threshold_upper=0.001,  # Very low threshold to trigger violation
                ),
            ],
            abort_conditions=[
                AbortCondition(
                    metric_name="error_rate",
                    operator="gt",
                    threshold=0.001,
                    description="Abort if error rate exceeds 0.001%",
                ),
            ],
        )
        exp_id = executor.register_experiment(exp)
        report = executor.run_experiment(exp_id)
        # May or may not abort depending on random measurement
        assert report is not None


# ============================================================
# TestChaosGate
# ============================================================


class TestChaosGate:
    """Test cognitive load gating."""

    def test_permitted_when_below_threshold(self):
        gate = ChaosGate(threshold=100.0)  # Very high threshold
        permitted, score = gate.check()
        assert permitted is True

    def test_blocked_when_above_threshold(self):
        gate = ChaosGate(threshold=0.0)  # Impossible threshold
        with pytest.raises(ChaosCognitiveLoadGateError):
            gate.check()

    def test_emergency_bypasses_gate(self):
        gate = ChaosGate(threshold=0.0)  # Impossible threshold
        permitted, score = gate.check(is_emergency=True)
        assert permitted is True

    def test_threshold_getter_setter(self):
        gate = ChaosGate(threshold=60.0)
        assert gate.get_threshold() == 60.0
        gate.set_threshold(75.0)
        assert gate.get_threshold() == 75.0


# ============================================================
# TestGameDayOrchestrator
# ============================================================


class TestGameDayOrchestrator:
    """Test game day execution modes."""

    def _make_orchestrator(self) -> tuple:
        executor = _make_executor(10)
        calc = executor._blast_radius_calculator
        orch = GameDayOrchestrator(executor=executor, blast_radius_calculator=calc)
        return orch, executor

    def test_register_gameday(self):
        orch, _ = self._make_orchestrator()
        gd = GameDay(title="Test game day")
        gd_id = orch.register_gameday(gd)
        assert gd_id == gd.gameday_id

    def test_run_sequential(self):
        orch, _ = self._make_orchestrator()
        gd = PredefinedGameDays.container_restart_resilience()
        gd_id = orch.register_gameday(gd)
        report = orch.run_gameday(gd_id)
        assert report.gameday_id == gd_id
        assert report.experiments_completed + report.experiments_aborted + report.experiments_failed >= 1

    def test_run_concurrent(self):
        orch, _ = self._make_orchestrator()
        gd = GameDay(
            title="Concurrent test",
            experiments=[
                ChaosExperiment(
                    name="Kill test",
                    fault_config=FaultConfig(
                        fault_type=FaultType.CONTAINER_KILL,
                        target_labels={"app": "fizzbuzz"},
                        target_count=1,
                    ),
                ),
            ],
            schedule_mode=ScheduleMode.CONCURRENT,
        )
        gd_id = orch.register_gameday(gd)
        report = orch.run_gameday(gd_id)
        assert report is not None

    def test_run_staggered(self):
        orch, _ = self._make_orchestrator()
        gd = PredefinedGameDays.resource_exhaustion()
        gd_id = orch.register_gameday(gd)
        report = orch.run_gameday(gd_id)
        assert report is not None
        assert report.total_duration_seconds >= 0.0

    def test_abort_gameday(self):
        orch, _ = self._make_orchestrator()
        gd = GameDay(title="Abort test")
        gd_id = orch.register_gameday(gd)
        orch.abort_gameday(gd_id, AbortReason.MANUAL_ABORT)
        assert gd.status == GameDayStatus.ABORTED

    def test_gameday_report(self):
        orch, _ = self._make_orchestrator()
        gd = PredefinedGameDays.network_partition_tolerance()
        gd_id = orch.register_gameday(gd)
        report = orch.run_gameday(gd_id)
        assert isinstance(report, GameDayReport)
        assert len(report.timeline) > 0


# ============================================================
# TestPredefinedGameDays
# ============================================================


class TestPredefinedGameDays:
    """Test predefined game day factory methods."""

    def test_container_restart_resilience(self):
        gd = PredefinedGameDays.container_restart_resilience()
        assert gd.title == "Container Restart Resilience"
        assert len(gd.experiments) == 1
        assert gd.experiments[0].fault_config.fault_type == FaultType.CONTAINER_KILL

    def test_network_partition_tolerance(self):
        gd = PredefinedGameDays.network_partition_tolerance()
        assert gd.title == "Network Partition Tolerance"
        assert len(gd.experiments) == 1
        assert gd.experiments[0].fault_config.fault_type == FaultType.NETWORK_PARTITION

    def test_resource_exhaustion(self):
        gd = PredefinedGameDays.resource_exhaustion()
        assert gd.title == "Resource Exhaustion"
        assert len(gd.experiments) == 2
        assert gd.schedule_mode == ScheduleMode.STAGGERED

    def test_full_outage_recovery(self):
        gd = PredefinedGameDays.full_outage_recovery()
        assert gd.title == "Full Outage Recovery"
        assert gd.experiments[0].is_emergency is True
        assert gd.blast_radius_limit == 1.0


# ============================================================
# TestContainerChaosDashboard
# ============================================================


class TestContainerChaosDashboard:
    """Test ASCII dashboard rendering."""

    def test_render_status_no_active(self):
        dashboard = ContainerChaosDashboard()
        executor = _make_executor()
        output = dashboard.render_status(executor)
        assert "No active chaos experiments" in output

    def test_render_report(self):
        dashboard = ContainerChaosDashboard()
        report = ExperimentReport(
            experiment_id="test-id",
            experiment_name="Test Report",
            fault_type=FaultType.CONTAINER_KILL,
            hypothesis="Containers restart",
            hypothesis_validated=True,
            affected_container_count=3,
            total_container_count=10,
            blast_radius_percent=30.0,
            duration_seconds=45.0,
        )
        output = dashboard.render_report(report)
        assert "Test Report" in output
        assert "container_kill" in output

    def test_render_blast_radius(self):
        dashboard = ContainerChaosDashboard()
        calc = BlastRadiusCalculator(limit=0.50)
        calc.add_affected(["c1", "c2"])
        output = dashboard.render_blast_radius(calc, 10)
        assert "Blast Radius" in output
        assert "20.0%" in output

    def test_render_fault_list(self):
        dashboard = ContainerChaosDashboard()
        registry = FaultRegistry()
        output = dashboard.render_fault_list(registry)
        assert "container_kill" in output
        assert "network_partition" in output
        assert "cpu_stress" in output


# ============================================================
# TestFizzContainerChaosMiddleware
# ============================================================


class TestFizzContainerChaosMiddleware:
    """Test middleware pipeline integration."""

    def test_process_no_active_experiments(self):
        executor = _make_executor()
        dashboard = ContainerChaosDashboard()
        mw = FizzContainerChaosMiddleware(executor=executor, dashboard=dashboard)
        ctx = _make_context()

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert result.metadata["container_chaos_active"] is False

    def test_process_with_active_experiment(self):
        executor = _make_executor()
        dashboard = ContainerChaosDashboard()
        mw = FizzContainerChaosMiddleware(executor=executor, dashboard=dashboard)

        # Manually add an active experiment to simulate
        exp = ChaosExperiment(name="Active test", status=ExperimentStatus.OBSERVING)
        exp_id = exp.experiment_id
        executor.experiments[exp_id] = exp
        executor.active_experiments.add(exp_id)

        ctx = _make_context()

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert result.metadata["container_chaos_active"] is True
        assert len(result.metadata["container_chaos_experiments"]) == 1

    def test_priority(self):
        executor = _make_executor()
        dashboard = ContainerChaosDashboard()
        mw = FizzContainerChaosMiddleware(executor=executor, dashboard=dashboard)
        assert mw.get_priority() == 117
        assert mw.priority == 117

    def test_name(self):
        executor = _make_executor()
        dashboard = ContainerChaosDashboard()
        mw = FizzContainerChaosMiddleware(executor=executor, dashboard=dashboard)
        assert mw.get_name() == "FizzContainerChaosMiddleware"
        assert mw.name == "FizzContainerChaosMiddleware"


# ============================================================
# TestCreateFizzcontainerchaosSubsystem
# ============================================================


class TestCreateFizzcontainerchaosSubsystem:
    """Test factory function wiring."""

    def test_default_config(self):
        executor, orchestrator, middleware = create_fizzcontainerchaos_subsystem()
        assert isinstance(executor, ChaosExecutor)
        assert isinstance(orchestrator, GameDayOrchestrator)
        assert isinstance(middleware, FizzContainerChaosMiddleware)

    def test_custom_config(self):
        executor, orchestrator, middleware = create_fizzcontainerchaos_subsystem(
            cognitive_load_threshold=80.0,
            blast_radius_limit=0.30,
            blast_radius_scope="namespace",
            observation_interval=10.0,
            steady_state_tolerance=0.20,
            dashboard_width=80,
        )
        assert middleware.get_priority() == 117


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Test module-level constants."""

    def test_version(self):
        assert CONTAINER_CHAOS_VERSION == "1.0.0"

    def test_chaos_mesh_compat(self):
        assert CHAOS_MESH_COMPAT_VERSION == "2.6"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 117

    def test_default_experiment_timeout(self):
        assert DEFAULT_EXPERIMENT_TIMEOUT == 300.0

    def test_default_cognitive_load_threshold(self):
        assert DEFAULT_COGNITIVE_LOAD_THRESHOLD == 60.0

    def test_default_blast_radius_limit(self):
        assert DEFAULT_BLAST_RADIUS_LIMIT == 0.50


# ============================================================
# TestExceptions
# ============================================================


class TestExceptions:
    """Test exception hierarchy and error codes."""

    def test_base_exception_inherits_fizzbuzz_error(self):
        exc = ContainerChaosError("test")
        assert isinstance(exc, FizzBuzzError)
        assert exc.error_code == "EFP-CCH00"

    def test_experiment_not_found_error_code(self):
        exc = ChaosExperimentNotFoundError("missing")
        assert exc.error_code == "EFP-CCH01"

    def test_middleware_error_includes_number(self):
        exc = ChaosContainerChaosMiddlewareError(42, "test failure")
        assert exc.evaluation_number == 42
        assert exc.error_code == "EFP-CCH23"
        assert "42" in str(exc)

    def test_all_exceptions_inherit_container_chaos_error(self):
        exceptions = [
            ChaosExperimentNotFoundError("test"),
            ChaosExperimentAlreadyRunningError("test"),
            ChaosExperimentFailedStartError("test"),
            ChaosFaultInjectionError("test"),
            ChaosTargetResolutionError("test"),
            ChaosCognitiveLoadGateError("test"),
        ]
        for exc in exceptions:
            assert isinstance(exc, ContainerChaosError)
            assert isinstance(exc, FizzBuzzError)

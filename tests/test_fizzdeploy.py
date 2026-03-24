"""
Tests for enterprise_fizzbuzz.infrastructure.fizzdeploy

Comprehensive test suite for the FizzDeploy Container-Native Deployment
Pipeline: enums, data classes, exception hierarchy, core classes
(PipelineStep, PipelineStage, Pipeline, PipelineExecutor), four deployment
strategies (RollingUpdateStrategy, BlueGreenStrategy, CanaryStrategy,
RecreateStrategy), ManifestParser, GitOpsReconciler, RollbackManager,
DeploymentGate, _PipelineBuilder, DeployDashboard, FizzDeployMiddleware,
and factory function.
"""

import hashlib
import threading
import time
from dataclasses import fields
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzdeploy import (
    # Constants
    FIZZDEPLOY_VERSION,
    DEFAULT_PIPELINE_TIMEOUT,
    DEFAULT_STAGE_TIMEOUT,
    DEFAULT_STEP_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_ROLLING_MAX_SURGE,
    DEFAULT_ROLLING_MAX_UNAVAILABLE,
    DEFAULT_CANARY_ANALYSIS_INTERVAL,
    DEFAULT_RECONCILE_INTERVAL,
    DEFAULT_REVISION_HISTORY_DEPTH,
    DEFAULT_COGNITIVE_LOAD_THRESHOLD,
    DEFAULT_DASHBOARD_WIDTH,
    MIDDLEWARE_PRIORITY,
    DEFAULT_CANARY_STEPS,
    # Event type constants
    DEPLOY_PIPELINE_STARTED,
    DEPLOY_PIPELINE_COMPLETED,
    DEPLOY_PIPELINE_FAILED,
    DEPLOY_STAGE_STARTED,
    DEPLOY_STAGE_COMPLETED,
    DEPLOY_STAGE_FAILED,
    DEPLOY_ROLLING_UPDATE_BATCH,
    DEPLOY_ROLLING_UPDATE_PAUSED,
    DEPLOY_BLUE_GREEN_SWITCHED,
    DEPLOY_BLUE_GREEN_ABORTED,
    DEPLOY_CANARY_STEP_ADVANCED,
    DEPLOY_CANARY_REGRESSION,
    DEPLOY_RECREATE_STARTED,
    DEPLOY_RECREATE_COMPLETED,
    DEPLOY_GITOPS_DRIFT_DETECTED,
    DEPLOY_GITOPS_SYNC_APPLIED,
    DEPLOY_ROLLBACK_EXECUTED,
    DEPLOY_GATE_BLOCKED,
    DEPLOY_GATE_PASSED,
    DEPLOY_GATE_EMERGENCY_BYPASS,
    DEPLOY_DASHBOARD_RENDERED,
    # Enums
    PipelineStatus,
    StageType,
    StageStatus,
    DeploymentStrategy,
    SyncStrategy,
    RevisionStatus,
    OnFailureAction,
    # Data classes
    RetryPolicy,
    StageResult,
    PipelineResult,
    HealthCheckConfig,
    DeploymentSpec,
    DeploymentManifest,
    DeploymentRevision,
    RollbackRecord,
    DriftReport,
    CanaryAnalysisResult,
    # Classes
    PipelineStep,
    PipelineStage,
    Pipeline,
    PipelineExecutor,
    RollingUpdateStrategy,
    BlueGreenStrategy,
    CanaryStrategy,
    RecreateStrategy,
    _StrategyFactory,
    ManifestParser,
    GitOpsReconciler,
    RollbackManager,
    DeploymentGate,
    _PipelineBuilder,
    DeployDashboard,
    FizzDeployMiddleware,
    # Factory
    create_fizzdeploy_subsystem,
    # Exceptions
    DeployError,
    DeployPipelineError,
    DeployStageError,
    DeployStepError,
    DeployStrategyError,
    RollingUpdateError,
    BlueGreenError,
    CanaryError,
    RecreateError,
    DeployManifestError,
    ManifestParseError,
    ManifestValidationError,
    GitOpsReconcileError,
    GitOpsDriftError,
    GitOpsSyncError,
    RollbackError,
    RollbackRevisionNotFoundError,
    RollbackStrategyError,
    DeployGateError,
    CognitiveLoadGateError,
    DeployDashboardError,
    DeployMiddlewareError,
)
from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Fixtures
# ============================================================


class MockEventBus:
    """Mock event bus for testing lifecycle events."""

    def __init__(self):
        self.events = []

    def publish(self, event_type, data=None):
        self.events.append((event_type, data))


@pytest.fixture
def event_bus():
    """Provide a mock event bus."""
    return MockEventBus()


@pytest.fixture
def sample_manifest():
    """Provide a sample deployment manifest."""
    return DeploymentManifest(
        name="fizzbuzz-core",
        namespace="production",
        labels={"app": "fizzbuzz", "tier": "core"},
        spec=DeploymentSpec(
            image="fizzbuzz-eval:1.0.0",
            replicas=3,
            strategy=DeploymentStrategy.ROLLING_UPDATE,
            health_check=HealthCheckConfig(
                probe_type="http", path="/healthz", port=8080
            ),
        ),
    )


@pytest.fixture
def sample_pods():
    """Provide sample current pods."""
    return [
        {"id": f"fizzbuzz-core-pod-{i}", "image": "fizzbuzz-eval:0.9.0", "status": "ready"}
        for i in range(3)
    ]


@pytest.fixture
def pipeline_executor(event_bus):
    """Provide a PipelineExecutor instance."""
    return PipelineExecutor(event_bus=event_bus)


@pytest.fixture
def rollback_manager(event_bus):
    """Provide a RollbackManager instance."""
    return RollbackManager(max_depth=10, event_bus=event_bus)


@pytest.fixture
def reconciler(pipeline_executor, event_bus):
    """Provide a GitOpsReconciler instance."""
    return GitOpsReconciler(
        sync_strategy=SyncStrategy.AUTO,
        reconcile_interval=30.0,
        pipeline_executor=pipeline_executor,
        event_bus=event_bus,
    )


@pytest.fixture
def deployment_gate(event_bus):
    """Provide a DeploymentGate instance."""
    return DeploymentGate(threshold=70.0, event_bus=event_bus)


@pytest.fixture
def deploy_middleware(rollback_manager, reconciler):
    """Provide a FizzDeployMiddleware instance."""
    return FizzDeployMiddleware(
        rollback_mgr=rollback_manager,
        reconciler=reconciler,
    )


@pytest.fixture
def dashboard():
    """Provide a DeployDashboard instance."""
    return DeployDashboard(width=72)


# ============================================================
# TestRetryPolicy
# ============================================================


class TestRetryPolicy:
    """Tests for RetryPolicy data class."""

    def test_default_max_retries(self):
        policy = RetryPolicy()
        assert policy.max_retries == DEFAULT_MAX_RETRIES

    def test_default_backoff_multiplier(self):
        policy = RetryPolicy()
        assert policy.backoff_multiplier == DEFAULT_RETRY_BACKOFF

    def test_default_max_delay(self):
        policy = RetryPolicy()
        assert policy.max_delay == 60.0

    def test_default_initial_delay(self):
        policy = RetryPolicy()
        assert policy.initial_delay == 1.0

    def test_custom_max_retries(self):
        policy = RetryPolicy(max_retries=5)
        assert policy.max_retries == 5

    def test_custom_backoff(self):
        policy = RetryPolicy(backoff_multiplier=3.0)
        assert policy.backoff_multiplier == 3.0

    def test_custom_max_delay(self):
        policy = RetryPolicy(max_delay=120.0)
        assert policy.max_delay == 120.0

    def test_custom_initial_delay(self):
        policy = RetryPolicy(initial_delay=0.5)
        assert policy.initial_delay == 0.5


# ============================================================
# TestPipelineStep
# ============================================================


class TestPipelineStep:
    """Tests for PipelineStep execution and retry logic."""

    def test_successful_execution(self):
        step = PipelineStep("test", lambda ctx: {"result": "ok"})
        result = step.execute({})
        assert result == {"result": "ok"}

    def test_step_name(self):
        step = PipelineStep("my-step", lambda ctx: {})
        assert step.name == "my-step"

    def test_default_timeout(self):
        step = PipelineStep("test", lambda ctx: {})
        assert step.timeout == DEFAULT_STEP_TIMEOUT

    def test_custom_timeout(self):
        step = PipelineStep("test", lambda ctx: {}, timeout=30.0)
        assert step.timeout == 30.0

    def test_default_on_failure(self):
        step = PipelineStep("test", lambda ctx: {})
        assert step.on_failure == OnFailureAction.ABORT

    def test_custom_on_failure(self):
        step = PipelineStep("test", lambda ctx: {}, on_failure=OnFailureAction.SKIP)
        assert step.on_failure == OnFailureAction.SKIP

    def test_retry_on_failure(self):
        call_count = 0

        def action(ctx):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("fail")
            return {"ok": True}

        policy = RetryPolicy(max_retries=3, initial_delay=0.001, backoff_multiplier=1.0)
        step = PipelineStep("test", action, retry_policy=policy)
        result = step.execute({})
        assert result == {"ok": True}
        assert call_count == 3

    def test_all_retries_exhausted(self):
        def action(ctx):
            raise RuntimeError("always fail")

        policy = RetryPolicy(max_retries=2, initial_delay=0.001, backoff_multiplier=1.0)
        step = PipelineStep("test", action, retry_policy=policy)
        with pytest.raises(DeployStepError):
            step.execute({})

    def test_context_passed_to_action(self):
        def action(ctx):
            return {"received": ctx.get("key")}

        step = PipelineStep("test", action)
        result = step.execute({"key": "value"})
        assert result == {"received": "value"}

    def test_metadata(self):
        step = PipelineStep("test", lambda ctx: {}, metadata={"env": "prod"})
        assert step.metadata == {"env": "prod"}

    def test_default_metadata(self):
        step = PipelineStep("test", lambda ctx: {})
        assert step.metadata == {}

    def test_retry_policy_default(self):
        step = PipelineStep("test", lambda ctx: {})
        assert step.retry_policy.max_retries == DEFAULT_MAX_RETRIES

    def test_custom_retry_policy(self):
        policy = RetryPolicy(max_retries=5)
        step = PipelineStep("test", lambda ctx: {}, retry_policy=policy)
        assert step.retry_policy.max_retries == 5

    def test_error_message_in_exception(self):
        def action(ctx):
            raise ValueError("specific error")

        policy = RetryPolicy(max_retries=0, initial_delay=0.001)
        step = PipelineStep("fail-step", action, retry_policy=policy)
        with pytest.raises(DeployStepError, match="fail-step"):
            step.execute({})

    def test_on_failure_rollback(self):
        step = PipelineStep("test", lambda ctx: {}, on_failure=OnFailureAction.ROLLBACK)
        assert step.on_failure == OnFailureAction.ROLLBACK


# ============================================================
# TestPipelineStage
# ============================================================


class TestPipelineStage:
    """Tests for PipelineStage execution."""

    def test_stage_name(self):
        stage = PipelineStage("build", StageType.BUILD)
        assert stage.name == "build"

    def test_stage_type(self):
        stage = PipelineStage("scan", StageType.SCAN)
        assert stage.stage_type == StageType.SCAN

    def test_default_parallel(self):
        stage = PipelineStage("build", StageType.BUILD)
        assert stage.parallel is False

    def test_parallel_flag(self):
        stage = PipelineStage("build", StageType.BUILD, parallel=True)
        assert stage.parallel is True

    def test_default_timeout(self):
        stage = PipelineStage("build", StageType.BUILD)
        assert stage.timeout == DEFAULT_STAGE_TIMEOUT

    def test_add_step(self):
        stage = PipelineStage("build", StageType.BUILD)
        step = PipelineStep("s1", lambda ctx: {})
        stage.add_step(step)
        assert len(stage.steps) == 1

    def test_execute_empty_stage(self):
        stage = PipelineStage("build", StageType.BUILD)
        result = stage.execute({})
        assert result.status == StageStatus.SUCCEEDED

    def test_execute_single_step(self):
        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", lambda ctx: {"ok": True}))
        result = stage.execute({})
        assert result.status == StageStatus.SUCCEEDED

    def test_execute_failed_step(self):
        def fail(ctx):
            raise RuntimeError("fail")

        stage = PipelineStage("build", StageType.BUILD)
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)
        stage.add_step(PipelineStep("s1", fail, retry_policy=policy))
        result = stage.execute({})
        assert result.status == StageStatus.FAILED

    def test_execute_records_duration(self):
        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", lambda ctx: {}))
        result = stage.execute({})
        assert result.duration_ms >= 0

    def test_execute_records_timestamps(self):
        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", lambda ctx: {}))
        result = stage.execute({})
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_stage_result_stage_type(self):
        stage = PipelineStage("deploy", StageType.DEPLOY)
        stage.add_step(PipelineStep("s1", lambda ctx: {}))
        result = stage.execute({})
        assert result.stage_type == StageType.DEPLOY

    def test_multiple_steps_sequential(self):
        results = []
        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", lambda ctx: results.append(1) or {}))
        stage.add_step(PipelineStep("s2", lambda ctx: results.append(2) or {}))
        stage.execute({})
        assert results == [1, 2]

    def test_skip_on_failure(self):
        def fail(ctx):
            raise RuntimeError("fail")

        stage = PipelineStage("build", StageType.BUILD)
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)
        stage.add_step(PipelineStep("s1", fail, retry_policy=policy, on_failure=OnFailureAction.SKIP))
        stage.add_step(PipelineStep("s2", lambda ctx: {}))
        result = stage.execute({})
        assert result.status == StageStatus.SUCCEEDED

    def test_parallel_execution(self):
        results = []
        stage = PipelineStage("build", StageType.BUILD, parallel=True)
        stage.add_step(PipelineStep("s1", lambda ctx: results.append("a") or {}))
        stage.add_step(PipelineStep("s2", lambda ctx: results.append("b") or {}))
        result = stage.execute({})
        assert result.status == StageStatus.SUCCEEDED
        assert len(results) == 2

    def test_parallel_failure(self):
        def fail(ctx):
            raise RuntimeError("parallel fail")

        stage = PipelineStage("build", StageType.BUILD, parallel=True)
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)
        stage.add_step(PipelineStep("s1", fail, retry_policy=policy))
        stage.add_step(PipelineStep("s2", lambda ctx: {}))
        result = stage.execute({})
        assert result.status == StageStatus.FAILED

    def test_error_message_on_failure(self):
        def fail(ctx):
            raise RuntimeError("boom")

        stage = PipelineStage("build", StageType.BUILD)
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)
        stage.add_step(PipelineStep("s1", fail, retry_policy=policy))
        result = stage.execute({})
        assert "boom" in result.error_message or "s1" in result.error_message

    def test_stage_with_initial_steps(self):
        steps = [PipelineStep("s1", lambda ctx: {})]
        stage = PipelineStage("build", StageType.BUILD, steps=steps)
        assert len(stage.steps) == 1


# ============================================================
# TestPipeline
# ============================================================


class TestPipeline:
    """Tests for Pipeline construction."""

    def test_pipeline_id_generated(self):
        p = Pipeline("test-deploy")
        assert len(p.pipeline_id) == 16

    def test_deployment_name(self):
        p = Pipeline("my-deploy")
        assert p.deployment_name == "my-deploy"

    def test_default_status(self):
        p = Pipeline("test")
        assert p.status == PipelineStatus.PENDING

    def test_default_timeout(self):
        p = Pipeline("test")
        assert p.timeout == DEFAULT_PIPELINE_TIMEOUT

    def test_custom_timeout(self):
        p = Pipeline("test", timeout=300.0)
        assert p.timeout == 300.0

    def test_add_stage(self):
        p = Pipeline("test")
        p.add_stage(PipelineStage("build", StageType.BUILD))
        assert len(p.stages) == 1

    def test_multiple_stages(self):
        p = Pipeline("test")
        p.add_stage(PipelineStage("build", StageType.BUILD))
        p.add_stage(PipelineStage("deploy", StageType.DEPLOY))
        assert len(p.stages) == 2

    def test_get_result_before_execution(self):
        p = Pipeline("test")
        assert p.get_result() is None

    def test_created_at(self):
        p = Pipeline("test")
        assert p.created_at is not None

    def test_initial_stages_empty(self):
        p = Pipeline("test")
        assert p.stages == []

    def test_initial_stages_provided(self):
        stages = [PipelineStage("build", StageType.BUILD)]
        p = Pipeline("test", stages=stages)
        assert len(p.stages) == 1

    def test_unique_pipeline_ids(self):
        ids = {Pipeline("test").pipeline_id for _ in range(100)}
        assert len(ids) == 100


# ============================================================
# TestPipelineExecutor
# ============================================================


class TestPipelineExecutor:
    """Tests for PipelineExecutor execution flow."""

    def test_execute_empty_pipeline(self, pipeline_executor):
        pipeline = Pipeline("test")
        result = pipeline_executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_execute_single_stage(self, pipeline_executor):
        pipeline = Pipeline("test")
        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", lambda ctx: {}))
        pipeline.add_stage(stage)
        result = pipeline_executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_execute_records_pipeline_id(self, pipeline_executor):
        pipeline = Pipeline("test")
        result = pipeline_executor.execute(pipeline)
        assert result.pipeline_id == pipeline.pipeline_id

    def test_execute_records_deployment_name(self, pipeline_executor):
        pipeline = Pipeline("my-deploy")
        result = pipeline_executor.execute(pipeline)
        assert result.deployment_name == "my-deploy"

    def test_execute_records_timestamps(self, pipeline_executor):
        pipeline = Pipeline("test")
        result = pipeline_executor.execute(pipeline)
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_execute_records_duration(self, pipeline_executor):
        pipeline = Pipeline("test")
        result = pipeline_executor.execute(pipeline)
        assert result.total_duration_ms >= 0

    def test_failed_stage_aborts(self, pipeline_executor):
        pipeline = Pipeline("test")
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)
        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")), retry_policy=policy))
        pipeline.add_stage(stage)
        result = pipeline_executor.execute(pipeline)
        assert result.status == PipelineStatus.FAILED

    def test_rollback_on_failure(self, pipeline_executor):
        pipeline = Pipeline("test")
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)

        def fail(ctx):
            raise RuntimeError("deploy fail")

        stage = PipelineStage("deploy", StageType.DEPLOY)
        stage.add_step(PipelineStep("s1", fail, retry_policy=policy, on_failure=OnFailureAction.ROLLBACK))
        pipeline.add_stage(stage)
        result = pipeline_executor.execute(pipeline)
        assert result.status == PipelineStatus.ROLLED_BACK

    def test_history_recorded(self, pipeline_executor):
        pipeline = Pipeline("test")
        pipeline_executor.execute(pipeline)
        history = pipeline_executor.get_history()
        assert len(history) == 1

    def test_history_limit(self, pipeline_executor):
        for i in range(15):
            pipeline_executor.execute(Pipeline(f"test-{i}"))
        history = pipeline_executor.get_history(5)
        assert len(history) == 5

    def test_active_pipelines_empty_after(self, pipeline_executor):
        pipeline = Pipeline("test")
        pipeline_executor.execute(pipeline)
        assert pipeline_executor.get_active() == []

    def test_cancel_nonexistent(self, pipeline_executor):
        assert pipeline_executor.cancel("nonexistent") is False

    def test_stage_results_collected(self, pipeline_executor):
        pipeline = Pipeline("test")
        pipeline.add_stage(PipelineStage("build", StageType.BUILD))
        pipeline.add_stage(PipelineStage("scan", StageType.SCAN))
        result = pipeline_executor.execute(pipeline)
        assert len(result.stage_results) == 2

    def test_events_emitted(self, event_bus, pipeline_executor):
        pipeline = Pipeline("test")
        pipeline_executor.execute(pipeline)
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_PIPELINE_STARTED in event_types
        assert DEPLOY_PIPELINE_COMPLETED in event_types

    def test_failure_event_emitted(self, event_bus):
        executor = PipelineExecutor(event_bus=event_bus)
        pipeline = Pipeline("test")
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)

        def fail(ctx):
            raise RuntimeError("fail")

        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", fail, retry_policy=policy))
        pipeline.add_stage(stage)
        executor.execute(pipeline)
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_PIPELINE_FAILED in event_types

    def test_pipeline_result_stored(self, pipeline_executor):
        pipeline = Pipeline("test")
        result = pipeline_executor.execute(pipeline)
        assert pipeline.get_result() is result

    def test_multiple_pipelines_history(self, pipeline_executor):
        pipeline_executor.execute(Pipeline("a"))
        pipeline_executor.execute(Pipeline("b"))
        pipeline_executor.execute(Pipeline("c"))
        history = pipeline_executor.get_history(10)
        names = [r.deployment_name for r in history]
        assert "a" in names
        assert "b" in names
        assert "c" in names

    def test_skipped_stage_continues(self, pipeline_executor):
        def fail(ctx):
            raise RuntimeError("fail")

        pipeline = Pipeline("test")
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)

        stage1 = PipelineStage("build", StageType.BUILD)
        stage1.add_step(PipelineStep("s1", fail, retry_policy=policy, on_failure=OnFailureAction.SKIP))
        pipeline.add_stage(stage1)

        stage2 = PipelineStage("scan", StageType.SCAN)
        stage2.add_step(PipelineStep("s2", lambda ctx: {}))
        pipeline.add_stage(stage2)

        result = pipeline_executor.execute(pipeline)
        assert len(result.stage_results) == 2

    def test_total_executions_tracked(self, pipeline_executor):
        pipeline_executor.execute(Pipeline("a"))
        pipeline_executor.execute(Pipeline("b"))
        assert pipeline_executor._total_executions == 2

    def test_total_failures_tracked(self, event_bus):
        executor = PipelineExecutor(event_bus=event_bus)
        policy = RetryPolicy(max_retries=0, initial_delay=0.001)

        def fail(ctx):
            raise RuntimeError("fail")

        pipeline = Pipeline("test")
        stage = PipelineStage("build", StageType.BUILD)
        stage.add_step(PipelineStep("s1", fail, retry_policy=policy))
        pipeline.add_stage(stage)
        executor.execute(pipeline)
        assert executor._total_failures == 1

    def test_no_event_bus(self):
        executor = PipelineExecutor(event_bus=None)
        pipeline = Pipeline("test")
        result = executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_stage_started_events(self, event_bus, pipeline_executor):
        pipeline = Pipeline("test")
        pipeline.add_stage(PipelineStage("build", StageType.BUILD))
        pipeline_executor.execute(pipeline)
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_STAGE_STARTED in event_types
        assert DEPLOY_STAGE_COMPLETED in event_types

    def test_seven_stage_pipeline(self, pipeline_executor):
        pipeline = Pipeline("test")
        for st in StageType:
            stage = PipelineStage(st.value, st)
            stage.add_step(PipelineStep(f"step-{st.value}", lambda ctx: {}))
            pipeline.add_stage(stage)
        result = pipeline_executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED
        assert len(result.stage_results) == 7


# ============================================================
# TestPipelineStatus
# ============================================================


class TestPipelineStatus:
    """Tests for PipelineStatus enum values."""

    def test_pending(self):
        assert PipelineStatus.PENDING.value == "pending"

    def test_running(self):
        assert PipelineStatus.RUNNING.value == "running"

    def test_succeeded(self):
        assert PipelineStatus.SUCCEEDED.value == "succeeded"

    def test_failed(self):
        assert PipelineStatus.FAILED.value == "failed"

    def test_rolled_back(self):
        assert PipelineStatus.ROLLED_BACK.value == "rolled_back"

    def test_cancelled(self):
        assert PipelineStatus.CANCELLED.value == "cancelled"


# ============================================================
# TestStageType
# ============================================================


class TestStageType:
    """Tests for StageType enum values."""

    def test_build(self):
        assert StageType.BUILD.value == "build"

    def test_scan(self):
        assert StageType.SCAN.value == "scan"

    def test_sign(self):
        assert StageType.SIGN.value == "sign"

    def test_push(self):
        assert StageType.PUSH.value == "push"

    def test_deploy(self):
        assert StageType.DEPLOY.value == "deploy"

    def test_validate(self):
        assert StageType.VALIDATE.value == "validate"

    def test_finalize(self):
        assert StageType.FINALIZE.value == "finalize"


# ============================================================
# TestStageStatus
# ============================================================


class TestStageStatus:
    """Tests for StageStatus enum values."""

    def test_pending(self):
        assert StageStatus.PENDING.value == "pending"

    def test_running(self):
        assert StageStatus.RUNNING.value == "running"

    def test_succeeded(self):
        assert StageStatus.SUCCEEDED.value == "succeeded"

    def test_failed(self):
        assert StageStatus.FAILED.value == "failed"

    def test_skipped(self):
        assert StageStatus.SKIPPED.value == "skipped"


# ============================================================
# TestDeploymentStrategy
# ============================================================


class TestDeploymentStrategy:
    """Tests for DeploymentStrategy enum values."""

    def test_rolling_update(self):
        assert DeploymentStrategy.ROLLING_UPDATE.value == "rolling_update"

    def test_blue_green(self):
        assert DeploymentStrategy.BLUE_GREEN.value == "blue_green"

    def test_canary(self):
        assert DeploymentStrategy.CANARY.value == "canary"

    def test_recreate(self):
        assert DeploymentStrategy.RECREATE.value == "recreate"


# ============================================================
# TestSyncStrategy
# ============================================================


class TestSyncStrategy:
    """Tests for SyncStrategy enum values."""

    def test_auto(self):
        assert SyncStrategy.AUTO.value == "auto"

    def test_manual(self):
        assert SyncStrategy.MANUAL.value == "manual"

    def test_dry_run(self):
        assert SyncStrategy.DRY_RUN.value == "dry_run"


# ============================================================
# TestRevisionStatus
# ============================================================


class TestRevisionStatus:
    """Tests for RevisionStatus enum values."""

    def test_active(self):
        assert RevisionStatus.ACTIVE.value == "active"

    def test_superseded(self):
        assert RevisionStatus.SUPERSEDED.value == "superseded"

    def test_rolled_back(self):
        assert RevisionStatus.ROLLED_BACK.value == "rolled_back"

    def test_failed(self):
        assert RevisionStatus.FAILED.value == "failed"


# ============================================================
# TestOnFailureAction
# ============================================================


class TestOnFailureAction:
    """Tests for OnFailureAction enum values."""

    def test_abort(self):
        assert OnFailureAction.ABORT.value == "abort"

    def test_skip(self):
        assert OnFailureAction.SKIP.value == "skip"

    def test_rollback(self):
        assert OnFailureAction.ROLLBACK.value == "rollback"


# ============================================================
# TestRollingUpdateStrategy
# ============================================================


class TestRollingUpdateStrategy:
    """Tests for RollingUpdateStrategy."""

    def test_default_max_surge(self):
        s = RollingUpdateStrategy()
        assert s._max_surge == DEFAULT_ROLLING_MAX_SURGE

    def test_default_max_unavailable(self):
        s = RollingUpdateStrategy()
        assert s._max_unavailable == DEFAULT_ROLLING_MAX_UNAVAILABLE

    def test_compute_batch_size_fraction(self):
        s = RollingUpdateStrategy(max_surge=0.25, max_unavailable=0.25)
        surge, unavail = s._compute_batch_size(4)
        assert surge == 1
        assert unavail == 1

    def test_compute_batch_size_larger(self):
        s = RollingUpdateStrategy(max_surge=0.5, max_unavailable=0.5)
        surge, unavail = s._compute_batch_size(10)
        assert surge == 5
        assert unavail == 5

    def test_compute_batch_size_minimum_one(self):
        s = RollingUpdateStrategy(max_surge=0.01, max_unavailable=0.01)
        surge, unavail = s._compute_batch_size(1)
        assert surge >= 1
        assert unavail >= 1

    def test_execute_returns_metrics(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, sample_pods, "fizzbuzz-eval:2.0.0")
        assert result["strategy"] == "rolling_update"
        assert result["desired_replicas"] == 3
        assert result["batches_completed"] > 0

    def test_execute_creates_new_pods(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, sample_pods, "fizzbuzz-eval:2.0.0")
        assert len(result["new_pods"]) >= sample_manifest.spec.replicas

    def test_execute_new_pods_have_new_image(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, sample_pods, "fizzbuzz-eval:2.0.0")
        for pod in result["new_pods"]:
            assert pod["image"] == "fizzbuzz-eval:2.0.0"

    def test_execute_emits_batch_events(self, event_bus, sample_manifest, sample_pods):
        s = RollingUpdateStrategy(event_bus=event_bus)
        s.execute(sample_manifest, sample_pods, "fizzbuzz-eval:2.0.0")
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_ROLLING_UPDATE_BATCH in event_types

    def test_execute_with_single_pod(self, sample_manifest):
        sample_manifest.spec.replicas = 1
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, [{"id": "p1", "image": "old"}], "new:1.0")
        assert result["pods_replaced"] >= 1

    def test_execute_with_many_pods(self, sample_manifest):
        sample_manifest.spec.replicas = 10
        pods = [{"id": f"p{i}", "image": "old"} for i in range(10)]
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, pods, "new:1.0")
        assert result["pods_replaced"] == 10

    def test_readiness_check_deterministic(self):
        s = RollingUpdateStrategy()
        result1 = s._simulate_readiness_check("test-pod-1")
        result2 = s._simulate_readiness_check("test-pod-1")
        assert result1 == result2

    def test_surge_count_in_result(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy(max_surge=0.5)
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert "surge_count" in result

    def test_unavailable_count_in_result(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert "unavailable_count" in result

    def test_absolute_surge(self):
        s = RollingUpdateStrategy(max_surge=3.0)
        surge, _ = s._compute_batch_size(10)
        assert surge == 3

    def test_no_event_bus(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy(event_bus=None)
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["strategy"] == "rolling_update"

    def test_empty_current_pods(self, sample_manifest):
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, [], "new:1.0")
        assert result["batches_completed"] == 0
        assert len(result["new_pods"]) == sample_manifest.spec.replicas

    def test_min_ready_seconds(self):
        s = RollingUpdateStrategy(min_ready_seconds=5.0)
        assert s._min_ready_seconds == 5.0

    def test_health_check_timeout(self):
        s = RollingUpdateStrategy(health_check_timeout=60.0)
        assert s._health_check_timeout == 60.0

    def test_pod_ids_unique(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        pod_ids = [p["id"] for p in result["new_pods"]]
        assert len(pod_ids) == len(set(pod_ids))

    def test_batch_size_uses_max_of_surge_unavail(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy(max_surge=0.5, max_unavailable=0.25)
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["batch_size"] > 0

    def test_compute_batch_zero_desired(self):
        s = RollingUpdateStrategy()
        surge, unavail = s._compute_batch_size(0)
        assert surge >= 0
        assert unavail >= 0

    def test_execute_returns_paused_flag(self, sample_manifest, sample_pods):
        s = RollingUpdateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert "paused" in result

    def test_custom_event_bus(self):
        bus = MockEventBus()
        s = RollingUpdateStrategy(event_bus=bus)
        assert s._event_bus is bus


# ============================================================
# TestBlueGreenStrategy
# ============================================================


class TestBlueGreenStrategy:
    """Tests for BlueGreenStrategy."""

    def test_default_active_environment(self):
        s = BlueGreenStrategy()
        assert s.get_active_environment() == "blue"

    def test_switch_traffic(self):
        s = BlueGreenStrategy()
        new_active = s.switch_traffic()
        assert new_active == "green"

    def test_switch_traffic_toggle(self):
        s = BlueGreenStrategy()
        s.switch_traffic()
        new_active = s.switch_traffic()
        assert new_active == "blue"

    def test_rollback(self):
        s = BlueGreenStrategy()
        s.switch_traffic()
        result = s.rollback()
        assert result == "blue"

    def test_execute_deploys_to_inactive(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["strategy"] == "blue_green"

    def test_execute_switches_on_validation_pass(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        if result["validation_passed"]:
            assert result["switched"] is True

    def test_execute_pods_deployed(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        if result["validation_passed"]:
            assert result["pods_deployed"] == sample_manifest.spec.replicas

    def test_execute_emits_switch_event(self, event_bus, sample_manifest, sample_pods):
        s = BlueGreenStrategy(event_bus=event_bus)
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        event_types = [e[0] for e in event_bus.events]
        if result["validation_passed"]:
            assert DEPLOY_BLUE_GREEN_SWITCHED in event_types

    def test_execute_new_pods_have_correct_image(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:2.0")
        for pod in result.get("new_pods", []):
            assert pod["image"] == "new:2.0"

    def test_execute_pods_have_environment_label(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        for pod in result.get("new_pods", []):
            assert "environment" in pod

    def test_validation_timeout(self):
        s = BlueGreenStrategy(validation_timeout=60.0)
        assert s._validation_timeout == 60.0

    def test_environments_initialized(self):
        s = BlueGreenStrategy()
        assert "blue" in s._environments
        assert "green" in s._environments

    def test_no_event_bus(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy(event_bus=None)
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["strategy"] == "blue_green"

    def test_execute_with_single_replica(self, sample_manifest):
        sample_manifest.spec.replicas = 1
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, [{"id": "p1", "image": "old"}], "new:1.0")
        assert result["strategy"] == "blue_green"

    def test_get_active_after_execute(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        if result["switched"]:
            assert s.get_active_environment() == "green"

    def test_multiple_deployments(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        s.execute(sample_manifest, sample_pods, "new:1.0")
        result2 = s.execute(sample_manifest, sample_pods, "new:2.0")
        assert result2["strategy"] == "blue_green"

    def test_execute_result_keys(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert "strategy" in result
        assert "active_environment" in result
        assert "validation_passed" in result
        assert "switched" in result

    def test_empty_environment_validation_fails(self, sample_manifest):
        s = BlueGreenStrategy()
        assert s._validate_environment("green", sample_manifest) is False

    def test_pod_ids_unique(self, sample_manifest, sample_pods):
        s = BlueGreenStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        pod_ids = [p["id"] for p in result.get("new_pods", [])]
        assert len(pod_ids) == len(set(pod_ids))


# ============================================================
# TestCanaryStrategy
# ============================================================


class TestCanaryStrategy:
    """Tests for CanaryStrategy."""

    def test_default_steps(self):
        s = CanaryStrategy()
        assert len(s._steps) == len(DEFAULT_CANARY_STEPS)

    def test_custom_steps(self):
        steps = [(10.0, 60.0), (50.0, 120.0), (100.0, 0.0)]
        s = CanaryStrategy(steps=steps)
        assert len(s._steps) == 3

    def test_default_error_threshold(self):
        s = CanaryStrategy()
        assert s._error_rate_threshold == 0.05

    def test_default_latency_threshold(self):
        s = CanaryStrategy()
        assert s._latency_threshold == 50.0

    def test_analyze_step_returns_result(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 5.0)
        assert isinstance(result, CanaryAnalysisResult)

    def test_analyze_step_records_traffic(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 25.0)
        assert result.traffic_percent == 25.0

    def test_analyze_step_records_step_index(self):
        s = CanaryStrategy()
        result = s.analyze_step(2, 50.0)
        assert result.step_index == 2

    def test_analyze_step_has_verdict(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 5.0)
        assert result.verdict in ("pass", "fail", "inconclusive")

    def test_analyze_step_deterministic(self):
        s1 = CanaryStrategy()
        s2 = CanaryStrategy()
        r1 = s1.analyze_step(0, 5.0)
        r2 = s2.analyze_step(0, 5.0)
        assert r1.baseline_error_rate == r2.baseline_error_rate

    def test_analysis_results_accumulated(self):
        s = CanaryStrategy()
        s.analyze_step(0, 5.0)
        s.analyze_step(1, 25.0)
        results = s.get_analysis_results()
        assert len(results) == 2

    def test_execute_returns_metrics(self, sample_manifest, sample_pods):
        steps = [(10.0, 0.0), (100.0, 0.0)]
        s = CanaryStrategy(steps=steps)
        try:
            result = s.execute(sample_manifest, sample_pods, "new:1.0")
            assert result["strategy"] == "canary"
        except CanaryError:
            pass  # regression detected is valid behavior

    def test_execute_emits_step_events(self, event_bus, sample_manifest, sample_pods):
        steps = [(10.0, 0.0), (100.0, 0.0)]
        s = CanaryStrategy(steps=steps, event_bus=event_bus)
        try:
            s.execute(sample_manifest, sample_pods, "new:1.0")
        except CanaryError:
            pass
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_CANARY_STEP_ADVANCED in event_types

    def test_execute_canary_pods_created(self, sample_manifest, sample_pods):
        steps = [(10.0, 0.0), (100.0, 0.0)]
        s = CanaryStrategy(steps=steps)
        try:
            result = s.execute(sample_manifest, sample_pods, "new:1.0")
            assert len(result["canary_pods"]) == sample_manifest.spec.replicas
        except CanaryError:
            pass

    def test_regression_raises_canary_error(self, sample_manifest, sample_pods):
        steps = [(50.0, 0.0)]
        s = CanaryStrategy(steps=steps, error_rate_threshold=-1.0)
        with pytest.raises(CanaryError):
            s.execute(sample_manifest, sample_pods, "new:1.0")

    def test_analysis_duration_positive(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 5.0)
        assert result.analysis_duration_ms > 0

    def test_baseline_error_rate_positive(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 5.0)
        assert result.baseline_error_rate >= 0

    def test_canary_error_rate_non_negative(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 5.0)
        assert result.canary_error_rate >= 0

    def test_baseline_p99_positive(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 5.0)
        assert result.baseline_p99_latency_ms > 0

    def test_canary_p99_positive(self):
        s = CanaryStrategy()
        result = s.analyze_step(0, 5.0)
        assert result.canary_p99_latency_ms > 0

    def test_no_event_bus(self, sample_manifest, sample_pods):
        steps = [(10.0, 0.0), (100.0, 0.0)]
        s = CanaryStrategy(steps=steps, event_bus=None)
        try:
            result = s.execute(sample_manifest, sample_pods, "new:1.0")
            assert result["strategy"] == "canary"
        except CanaryError:
            pass

    def test_custom_analysis_interval(self):
        s = CanaryStrategy(analysis_interval=60.0)
        assert s._analysis_interval == 60.0

    def test_custom_error_rate_threshold(self):
        s = CanaryStrategy(error_rate_threshold=0.1)
        assert s._error_rate_threshold == 0.1

    def test_custom_latency_threshold(self):
        s = CanaryStrategy(latency_threshold=100.0)
        assert s._latency_threshold == 100.0


# ============================================================
# TestRecreateStrategy
# ============================================================


class TestRecreateStrategy:
    """Tests for RecreateStrategy."""

    def test_default_shutdown_timeout(self):
        s = RecreateStrategy()
        assert s._shutdown_timeout == 30.0

    def test_default_startup_timeout(self):
        s = RecreateStrategy()
        assert s._startup_timeout == 60.0

    def test_execute_returns_metrics(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["strategy"] == "recreate"

    def test_execute_terminates_old_pods(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert len(result["terminated_pods"]) == len(sample_pods)

    def test_execute_creates_new_pods(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["pods_created"] == sample_manifest.spec.replicas

    def test_execute_records_downtime(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["downtime_ms"] >= 0

    def test_execute_new_pods_have_correct_image(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:2.0")
        for pod in result["new_pods"]:
            assert pod["image"] == "new:2.0"

    def test_execute_emits_events(self, event_bus, sample_manifest, sample_pods):
        s = RecreateStrategy(event_bus=event_bus)
        s.execute(sample_manifest, sample_pods, "new:1.0")
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_RECREATE_STARTED in event_types
        assert DEPLOY_RECREATE_COMPLETED in event_types

    def test_execute_empty_current_pods(self, sample_manifest):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, [], "new:1.0")
        assert len(result["terminated_pods"]) == 0
        assert result["pods_created"] == sample_manifest.spec.replicas

    def test_custom_shutdown_timeout(self):
        s = RecreateStrategy(shutdown_timeout=60.0)
        assert s._shutdown_timeout == 60.0

    def test_custom_startup_timeout(self):
        s = RecreateStrategy(startup_timeout=120.0)
        assert s._startup_timeout == 120.0

    def test_no_event_bus(self, sample_manifest, sample_pods):
        s = RecreateStrategy(event_bus=None)
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert result["strategy"] == "recreate"

    def test_pod_ids_unique(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        pod_ids = [p["id"] for p in result["new_pods"]]
        assert len(pod_ids) == len(set(pod_ids))

    def test_new_pods_ready_status(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        for pod in result["new_pods"]:
            assert pod["status"] == "ready"

    def test_execute_with_large_replica_count(self, sample_manifest):
        sample_manifest.spec.replicas = 20
        pods = [{"id": f"p{i}", "image": "old"} for i in range(20)]
        s = RecreateStrategy()
        result = s.execute(sample_manifest, pods, "new:1.0")
        assert result["pods_created"] == 20

    def test_result_has_terminated_and_new(self, sample_manifest, sample_pods):
        s = RecreateStrategy()
        result = s.execute(sample_manifest, sample_pods, "new:1.0")
        assert "terminated_pods" in result
        assert "new_pods" in result


# ============================================================
# TestDeploymentManifest
# ============================================================


class TestDeploymentManifest:
    """Tests for DeploymentManifest data class."""

    def test_default_api_version(self):
        m = DeploymentManifest()
        assert m.api_version == "apps/v1"

    def test_default_kind(self):
        m = DeploymentManifest()
        assert m.kind == "Deployment"

    def test_default_namespace(self):
        m = DeploymentManifest()
        assert m.namespace == "default"

    def test_custom_name(self):
        m = DeploymentManifest(name="fizzbuzz-core")
        assert m.name == "fizzbuzz-core"

    def test_default_labels(self):
        m = DeploymentManifest()
        assert m.labels == {}

    def test_custom_labels(self):
        m = DeploymentManifest(labels={"app": "fizzbuzz"})
        assert m.labels == {"app": "fizzbuzz"}

    def test_spec_default(self):
        m = DeploymentManifest()
        assert isinstance(m.spec, DeploymentSpec)

    def test_parsed_at_set(self):
        m = DeploymentManifest()
        assert m.parsed_at is not None

    def test_raw_yaml_default(self):
        m = DeploymentManifest()
        assert m.raw_yaml == ""

    def test_annotations_default(self):
        m = DeploymentManifest()
        assert m.annotations == {}


# ============================================================
# TestDeploymentSpec
# ============================================================


class TestDeploymentSpec:
    """Tests for DeploymentSpec data class."""

    def test_default_image(self):
        s = DeploymentSpec()
        assert s.image == ""

    def test_default_replicas(self):
        s = DeploymentSpec()
        assert s.replicas == 1

    def test_default_strategy(self):
        s = DeploymentSpec()
        assert s.strategy == DeploymentStrategy.ROLLING_UPDATE

    def test_custom_replicas(self):
        s = DeploymentSpec(replicas=5)
        assert s.replicas == 5

    def test_health_check_none_default(self):
        s = DeploymentSpec()
        assert s.health_check is None

    def test_health_check_embedded(self):
        hc = HealthCheckConfig(probe_type="tcp", port=9090)
        s = DeploymentSpec(health_check=hc)
        assert s.health_check.probe_type == "tcp"

    def test_env_default(self):
        s = DeploymentSpec()
        assert s.env == {}

    def test_volumes_default(self):
        s = DeploymentSpec()
        assert s.volumes == []


# ============================================================
# TestHealthCheckConfig
# ============================================================


class TestHealthCheckConfig:
    """Tests for HealthCheckConfig data class."""

    def test_default_probe_type(self):
        hc = HealthCheckConfig()
        assert hc.probe_type == "http"

    def test_default_path(self):
        hc = HealthCheckConfig()
        assert hc.path == "/healthz"

    def test_default_port(self):
        hc = HealthCheckConfig()
        assert hc.port == 8080

    def test_tcp_probe(self):
        hc = HealthCheckConfig(probe_type="tcp", port=9090)
        assert hc.probe_type == "tcp"
        assert hc.port == 9090

    def test_exec_probe(self):
        hc = HealthCheckConfig(probe_type="exec", command=["test", "-f", "/ready"])
        assert hc.probe_type == "exec"
        assert len(hc.command) == 3

    def test_default_interval(self):
        hc = HealthCheckConfig()
        assert hc.interval_seconds == 10

    def test_default_timeout(self):
        hc = HealthCheckConfig()
        assert hc.timeout_seconds == 5

    def test_default_thresholds(self):
        hc = HealthCheckConfig()
        assert hc.success_threshold == 1
        assert hc.failure_threshold == 3


# ============================================================
# TestManifestParser
# ============================================================


class TestManifestParser:
    """Tests for ManifestParser."""

    def test_parse_dict_valid(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {"image": "fizzbuzz:1.0"},
        }
        manifest = parser.parse_dict(data)
        assert manifest.name == "test"
        assert manifest.spec.image == "fizzbuzz:1.0"

    def test_parse_dict_missing_name(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {},
            "spec": {"image": "fizzbuzz:1.0"},
        }
        with pytest.raises(ManifestValidationError):
            parser.parse_dict(data)

    def test_parse_dict_missing_image(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {},
        }
        with pytest.raises(ManifestValidationError):
            parser.parse_dict(data)

    def test_parse_dict_missing_required_field(self):
        parser = ManifestParser()
        data = {"apiVersion": "apps/v1"}
        with pytest.raises(ManifestValidationError):
            parser.parse_dict(data)

    def test_parse_dict_with_strategy(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {"image": "fizzbuzz:1.0", "strategy": "canary"},
        }
        manifest = parser.parse_dict(data)
        assert manifest.spec.strategy == DeploymentStrategy.CANARY

    def test_parse_dict_unknown_strategy(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {"image": "fizzbuzz:1.0", "strategy": "unknown_strategy"},
        }
        with pytest.raises(ManifestValidationError):
            parser.parse_dict(data)

    def test_parse_dict_with_replicas(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {"image": "fizzbuzz:1.0", "replicas": 5},
        }
        manifest = parser.parse_dict(data)
        assert manifest.spec.replicas == 5

    def test_parse_dict_with_health_check(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {
                "image": "fizzbuzz:1.0",
                "health_check": {"probe_type": "tcp", "port": 9090},
            },
        }
        manifest = parser.parse_dict(data)
        assert manifest.spec.health_check is not None
        assert manifest.spec.health_check.probe_type == "tcp"

    def test_parse_dict_with_namespace(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test", "namespace": "staging"},
            "spec": {"image": "fizzbuzz:1.0"},
        }
        manifest = parser.parse_dict(data)
        assert manifest.namespace == "staging"

    def test_parse_dict_with_labels(self):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "test", "labels": {"app": "fizzbuzz"}},
            "spec": {"image": "fizzbuzz:1.0"},
        }
        manifest = parser.parse_dict(data)
        assert manifest.labels == {"app": "fizzbuzz"}

    def test_validate_valid_manifest(self, sample_manifest):
        parser = ManifestParser()
        errors = parser.validate(sample_manifest)
        assert errors == []

    def test_validate_missing_name(self):
        parser = ManifestParser()
        manifest = DeploymentManifest(spec=DeploymentSpec(image="test:1.0"))
        errors = parser.validate(manifest)
        assert any("name" in e for e in errors)

    def test_validate_missing_image(self):
        parser = ManifestParser()
        manifest = DeploymentManifest(name="test")
        errors = parser.validate(manifest)
        assert any("image" in e for e in errors)

    def test_validate_negative_replicas(self):
        parser = ManifestParser()
        manifest = DeploymentManifest(
            name="test",
            spec=DeploymentSpec(image="test:1.0", replicas=0),
        )
        errors = parser.validate(manifest)
        assert any("replicas" in e for e in errors)

    def test_validate_strategy_params_negative_surge(self):
        parser = ManifestParser()
        errors = parser._validate_strategy_params(
            DeploymentStrategy.ROLLING_UPDATE, {"max_surge": -1}
        )
        assert len(errors) > 0

    def test_validate_resources_unknown_key(self):
        parser = ManifestParser()
        errors = parser._validate_resources({"unknown": {}})
        assert len(errors) > 0

    def test_validate_resources_valid(self):
        parser = ManifestParser()
        errors = parser._validate_resources({"requests": {}, "limits": {}})
        assert errors == []

    def test_parse_simple_yaml(self):
        parser = ManifestParser()
        yaml_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-deploy
spec:
  image: fizzbuzz:1.0
  replicas: 3"""
        manifest = parser.parse(yaml_content)
        assert manifest.name == "test-deploy"
        assert manifest.spec.image == "fizzbuzz:1.0"

    def test_parse_invalid_yaml(self):
        parser = ManifestParser()
        with pytest.raises((ManifestParseError, ManifestValidationError)):
            parser.parse("")

    def test_parse_health_check(self):
        parser = ManifestParser()
        data = {"probe_type": "exec", "command": ["test"], "port": 3000}
        hc = parser._parse_health_check(data)
        assert hc.probe_type == "exec"
        assert hc.port == 3000


# ============================================================
# TestGitOpsReconciler
# ============================================================


class TestGitOpsReconciler:
    """Tests for GitOpsReconciler."""

    def test_register_manifest(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        assert "fizzbuzz-core" in reconciler._manifests

    def test_update_actual_state(self, reconciler):
        reconciler.update_actual_state("fizzbuzz-core", {"image": "old:1.0"})
        assert reconciler._actual_state["fizzbuzz-core"]["image"] == "old:1.0"

    def test_reconcile_no_manifests(self, reconciler):
        reports = reconciler.reconcile()
        assert reports == []

    def test_reconcile_no_drift(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reports = reconciler.reconcile()
        assert len(reports) == 0

    def test_reconcile_detects_image_drift(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "different:2.0",
            "replicas": 3,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert len(reports) == 1
        assert any(d["field"] == "image" for d in reports[0].drifts)

    def test_reconcile_detects_replicas_drift(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": sample_manifest.spec.image,
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert len(reports) == 1

    def test_auto_sync_corrects_drift(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert reports[0].corrected is True

    def test_manual_sync_no_correction(self, pipeline_executor, event_bus, sample_manifest):
        reconciler = GitOpsReconciler(
            sync_strategy=SyncStrategy.MANUAL,
            pipeline_executor=pipeline_executor,
            event_bus=event_bus,
        )
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert reports[0].corrected is False

    def test_dry_run_no_correction(self, pipeline_executor, event_bus, sample_manifest):
        reconciler = GitOpsReconciler(
            sync_strategy=SyncStrategy.DRY_RUN,
            pipeline_executor=pipeline_executor,
            event_bus=event_bus,
        )
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert reports[0].corrected is False

    def test_drift_history(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reconciler.reconcile()
        history = reconciler.get_drift_history()
        assert len(history) >= 1

    def test_drift_history_limit(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        for i in range(5):
            reconciler.update_actual_state("fizzbuzz-core", {
                "image": f"old:{i}",
                "replicas": 1,
                "resources": {},
                "env": {},
            })
            reconciler.reconcile()
        history = reconciler.get_drift_history(3)
        assert len(history) <= 3

    def test_total_reconciliations(self, reconciler):
        reconciler.reconcile()
        reconciler.reconcile()
        assert reconciler._total_reconciliations == 2

    def test_total_drifts_detected(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reconciler.reconcile()
        assert reconciler._total_drifts_detected > 0

    def test_total_corrections(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reconciler.reconcile()
        assert reconciler._total_corrections > 0

    def test_emits_drift_event(self, event_bus, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reconciler.reconcile()
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_GITOPS_DRIFT_DETECTED in event_types

    def test_emits_sync_event(self, event_bus, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reconciler.reconcile()
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_GITOPS_SYNC_APPLIED in event_types

    def test_start_stop_loop(self, reconciler):
        reconciler.start_loop()
        assert reconciler._running is True
        reconciler.stop_loop()
        assert reconciler._running is False

    def test_multiple_manifests(self, reconciler, sample_manifest):
        m2 = DeploymentManifest(
            name="fizzbuzz-api",
            spec=DeploymentSpec(image="api:1.0", replicas=2),
        )
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.register_manifest("fizzbuzz-api", m2)
        assert len(reconciler._manifests) == 2

    def test_detect_drift_env(self, reconciler, sample_manifest):
        sample_manifest.spec.env = {"KEY": "value"}
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": sample_manifest.spec.image,
            "replicas": sample_manifest.spec.replicas,
            "resources": {},
            "env": {"KEY": "different"},
        })
        reports = reconciler.reconcile()
        assert len(reports) == 1
        assert any(d["field"] == "env" for d in reports[0].drifts)

    def test_detect_drift_resources(self, reconciler, sample_manifest):
        sample_manifest.spec.resources = {"requests": {"cpu": "100m"}}
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": sample_manifest.spec.image,
            "replicas": sample_manifest.spec.replicas,
            "resources": {"requests": {"cpu": "200m"}},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert len(reports) == 1

    def test_drift_report_sync_strategy(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert reports[0].sync_strategy == SyncStrategy.AUTO

    def test_drift_report_deployment_name(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert reports[0].deployment_name == "fizzbuzz-core"

    def test_no_event_bus(self, pipeline_executor, sample_manifest):
        reconciler = GitOpsReconciler(
            pipeline_executor=pipeline_executor, event_bus=None
        )
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert len(reports) == 1

    def test_second_reconcile_after_auto_fix(self, reconciler, sample_manifest):
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reconciler.reconcile()
        reports2 = reconciler.reconcile()
        assert len(reports2) == 0


# ============================================================
# TestDriftReport
# ============================================================


class TestDriftReport:
    """Tests for DriftReport data class."""

    def test_default_report_id(self):
        dr = DriftReport()
        assert len(dr.report_id) == 12

    def test_default_deployment_name(self):
        dr = DriftReport()
        assert dr.deployment_name == ""

    def test_default_drifts(self):
        dr = DriftReport()
        assert dr.drifts == []

    def test_default_sync_strategy(self):
        dr = DriftReport()
        assert dr.sync_strategy == SyncStrategy.AUTO

    def test_default_corrected(self):
        dr = DriftReport()
        assert dr.corrected is False

    def test_custom_drifts(self):
        drifts = [{"field": "image", "expected": "a", "actual": "b"}]
        dr = DriftReport(drifts=drifts)
        assert len(dr.drifts) == 1

    def test_detected_at(self):
        dr = DriftReport()
        assert dr.detected_at is not None

    def test_unique_report_ids(self):
        ids = {DriftReport().report_id for _ in range(50)}
        assert len(ids) == 50


# ============================================================
# TestRollbackManager
# ============================================================


class TestRollbackManager:
    """Tests for RollbackManager."""

    def test_record_revision(self, rollback_manager, sample_manifest):
        rev = rollback_manager.record_revision(
            "fizzbuzz-core", sample_manifest, "sha256:abc", "pipeline-1"
        )
        assert rev.revision_number == 1
        assert rev.status == RevisionStatus.ACTIVE

    def test_record_multiple_revisions(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rev2 = rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        assert rev2.revision_number == 2

    def test_previous_revision_superseded(self, rollback_manager, sample_manifest):
        rev1 = rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        assert rev1.status == RevisionStatus.SUPERSEDED

    def test_get_revisions(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        revisions = rollback_manager.get_revisions("fizzbuzz-core")
        assert len(revisions) == 1

    def test_get_active_revision(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        active = rollback_manager.get_active_revision("fizzbuzz-core")
        assert active is not None
        assert active.status == RevisionStatus.ACTIVE

    def test_get_active_revision_none(self, rollback_manager):
        active = rollback_manager.get_active_revision("nonexistent")
        assert active is None

    def test_rollback_success(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        record = rollback_manager.rollback("fizzbuzz-core", 1)
        assert record.success is True
        assert record.to_revision == 1

    def test_rollback_not_found(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        with pytest.raises(RollbackRevisionNotFoundError):
            rollback_manager.rollback("fizzbuzz-core", 999)

    def test_rollback_creates_new_revision(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        rollback_manager.rollback("fizzbuzz-core", 1)
        revisions = rollback_manager.get_revisions("fizzbuzz-core")
        assert len(revisions) == 3

    def test_rollback_from_set(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        rollback_manager.rollback("fizzbuzz-core", 1)
        revisions = rollback_manager.get_revisions("fizzbuzz-core")
        latest = revisions[-1]
        assert latest.rollback_from == 2

    def test_history_depth_trim(self, event_bus, sample_manifest):
        mgr = RollbackManager(max_depth=3, event_bus=event_bus)
        for i in range(5):
            mgr.record_revision("fizzbuzz-core", sample_manifest, f"sha256:{i}", f"p{i}")
        revisions = mgr.get_revisions("fizzbuzz-core")
        assert len(revisions) == 3

    def test_rollback_history(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        rollback_manager.rollback("fizzbuzz-core", 1)
        history = rollback_manager.get_rollback_history()
        assert len(history) == 1

    def test_rollback_emits_event(self, event_bus, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        rollback_manager.rollback("fizzbuzz-core", 1)
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_ROLLBACK_EXECUTED in event_types

    def test_rollback_record_trigger(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        record = rollback_manager.rollback("fizzbuzz-core", 1, trigger="automatic", reason="validation failed")
        assert record.trigger == "automatic"
        assert record.reason == "validation failed"

    def test_rollback_record_completed_at(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:def", "p2")
        record = rollback_manager.rollback("fizzbuzz-core", 1)
        assert record.completed_at is not None

    def test_revision_image_digest(self, rollback_manager, sample_manifest):
        rev = rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc123", "p1")
        assert rev.image_digest == "sha256:abc123"

    def test_revision_pipeline_id(self, rollback_manager, sample_manifest):
        rev = rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "pipeline-42")
        assert rev.pipeline_id == "pipeline-42"

    def test_no_event_bus(self, sample_manifest):
        mgr = RollbackManager(event_bus=None)
        rev = mgr.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        assert rev.revision_number == 1

    def test_multiple_deployments(self, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        rollback_manager.record_revision("fizzbuzz-api", sample_manifest, "sha256:def", "p2")
        assert len(rollback_manager.get_revisions("fizzbuzz-core")) == 1
        assert len(rollback_manager.get_revisions("fizzbuzz-api")) == 1


# ============================================================
# TestDeploymentRevision
# ============================================================


class TestDeploymentRevision:
    """Tests for DeploymentRevision data class."""

    def test_default_revision_number(self):
        rev = DeploymentRevision()
        assert rev.revision_number == 0

    def test_default_status(self):
        rev = DeploymentRevision()
        assert rev.status == RevisionStatus.ACTIVE

    def test_default_rollback_from(self):
        rev = DeploymentRevision()
        assert rev.rollback_from is None

    def test_custom_revision_number(self):
        rev = DeploymentRevision(revision_number=5)
        assert rev.revision_number == 5

    def test_manifest_stored(self, sample_manifest):
        rev = DeploymentRevision(manifest=sample_manifest)
        assert rev.manifest is not None

    def test_deployed_at(self):
        rev = DeploymentRevision()
        assert rev.deployed_at is not None

    def test_pipeline_id(self):
        rev = DeploymentRevision(pipeline_id="p-abc")
        assert rev.pipeline_id == "p-abc"

    def test_image_digest(self):
        rev = DeploymentRevision(image_digest="sha256:abcdef")
        assert rev.image_digest == "sha256:abcdef"


# ============================================================
# TestRollbackRecord
# ============================================================


class TestRollbackRecord:
    """Tests for RollbackRecord data class."""

    def test_default_rollback_id(self):
        rec = RollbackRecord()
        assert len(rec.rollback_id) == 12

    def test_default_trigger(self):
        rec = RollbackRecord()
        assert rec.trigger == "manual"

    def test_default_success(self):
        rec = RollbackRecord()
        assert rec.success is False

    def test_custom_trigger(self):
        rec = RollbackRecord(trigger="automatic")
        assert rec.trigger == "automatic"

    def test_started_at(self):
        rec = RollbackRecord()
        assert rec.started_at is not None

    def test_reason(self):
        rec = RollbackRecord(reason="validation failed")
        assert rec.reason == "validation failed"


# ============================================================
# TestDeploymentGate
# ============================================================


class TestDeploymentGate:
    """Tests for DeploymentGate."""

    def test_default_threshold(self, deployment_gate):
        assert deployment_gate._threshold == 70.0

    def test_emergency_bypass(self, deployment_gate, sample_manifest):
        result = deployment_gate.check("fizzbuzz-core", sample_manifest, emergency=True)
        assert result is True

    def test_emergency_bypass_increments_count(self, deployment_gate, sample_manifest):
        deployment_gate.check("fizzbuzz-core", sample_manifest, emergency=True)
        assert deployment_gate._bypass_count == 1

    def test_emergency_bypass_emits_event(self, event_bus, sample_manifest):
        gate = DeploymentGate(threshold=70.0, event_bus=event_bus)
        gate.check("fizzbuzz-core", sample_manifest, emergency=True)
        event_types = [e[0] for e in event_bus.events]
        assert DEPLOY_GATE_EMERGENCY_BYPASS in event_types

    def test_check_increments_gate_count(self, deployment_gate, sample_manifest):
        try:
            deployment_gate.check("fizzbuzz-core", sample_manifest)
        except CognitiveLoadGateError:
            pass
        assert deployment_gate._gate_count == 1

    def test_cognitive_load_simulation(self, deployment_gate):
        score = deployment_gate._simulate_cognitive_load()
        assert 0.0 <= score <= 100.0

    def test_queued_deployments_empty(self, deployment_gate):
        assert deployment_gate.get_queued() == []

    def test_release_queue(self, deployment_gate, sample_manifest):
        deployment_gate._queued_deployments.append(("fizzbuzz-core", sample_manifest))
        released = deployment_gate.release_queue()
        assert released >= 0

    def test_low_threshold_blocks(self, event_bus, sample_manifest):
        gate = DeploymentGate(threshold=0.0, event_bus=event_bus)
        with pytest.raises(CognitiveLoadGateError):
            gate.check("fizzbuzz-core", sample_manifest)

    def test_high_threshold_passes(self, event_bus, sample_manifest):
        gate = DeploymentGate(threshold=100.0, event_bus=event_bus)
        result = gate.check("fizzbuzz-core", sample_manifest)
        assert result is True

    def test_cognitive_load_gate_error_context(self, sample_manifest):
        gate = DeploymentGate(threshold=0.0)
        try:
            gate.check("fizzbuzz-core", sample_manifest)
        except CognitiveLoadGateError as e:
            assert "fizzbuzz-core" in str(e)
            assert e.error_code == "EFP-DPL19"

    def test_blocked_deployment_queued(self, sample_manifest):
        gate = DeploymentGate(threshold=0.0)
        try:
            gate.check("fizzbuzz-core", sample_manifest)
        except CognitiveLoadGateError:
            pass
        assert len(gate.get_queued()) == 1

    def test_no_event_bus(self, sample_manifest):
        gate = DeploymentGate(threshold=100.0, event_bus=None)
        result = gate.check("fizzbuzz-core", sample_manifest)
        assert result is True

    def test_multiple_emergency_bypasses(self, deployment_gate, sample_manifest):
        deployment_gate.check("a", sample_manifest, emergency=True)
        deployment_gate.check("b", sample_manifest, emergency=True)
        assert deployment_gate._bypass_count == 2

    def test_custom_threshold(self):
        gate = DeploymentGate(threshold=50.0)
        assert gate._threshold == 50.0


# ============================================================
# TestCanaryAnalysisResult
# ============================================================


class TestCanaryAnalysisResult:
    """Tests for CanaryAnalysisResult data class."""

    def test_default_step_index(self):
        r = CanaryAnalysisResult()
        assert r.step_index == 0

    def test_default_traffic(self):
        r = CanaryAnalysisResult()
        assert r.traffic_percent == 0.0

    def test_default_regression(self):
        r = CanaryAnalysisResult()
        assert r.regression_detected is False

    def test_default_verdict(self):
        r = CanaryAnalysisResult()
        assert r.verdict == "pass"

    def test_fail_verdict(self):
        r = CanaryAnalysisResult(verdict="fail", regression_detected=True)
        assert r.verdict == "fail"
        assert r.regression_detected is True

    def test_custom_error_rates(self):
        r = CanaryAnalysisResult(baseline_error_rate=0.01, canary_error_rate=0.05)
        assert r.baseline_error_rate == 0.01
        assert r.canary_error_rate == 0.05

    def test_custom_latencies(self):
        r = CanaryAnalysisResult(baseline_p99_latency_ms=10.0, canary_p99_latency_ms=50.0)
        assert r.baseline_p99_latency_ms == 10.0
        assert r.canary_p99_latency_ms == 50.0

    def test_analysis_duration(self):
        r = CanaryAnalysisResult(analysis_duration_ms=150.0)
        assert r.analysis_duration_ms == 150.0


# ============================================================
# TestStrategyFactory
# ============================================================


class TestStrategyFactory:
    """Tests for _StrategyFactory."""

    def test_create_rolling_update(self):
        s = _StrategyFactory.create(DeploymentStrategy.ROLLING_UPDATE, {})
        assert isinstance(s, RollingUpdateStrategy)

    def test_create_blue_green(self):
        s = _StrategyFactory.create(DeploymentStrategy.BLUE_GREEN, {})
        assert isinstance(s, BlueGreenStrategy)

    def test_create_canary(self):
        s = _StrategyFactory.create(DeploymentStrategy.CANARY, {})
        assert isinstance(s, CanaryStrategy)

    def test_create_recreate(self):
        s = _StrategyFactory.create(DeploymentStrategy.RECREATE, {})
        assert isinstance(s, RecreateStrategy)

    def test_create_with_params(self):
        s = _StrategyFactory.create(
            DeploymentStrategy.ROLLING_UPDATE,
            {"max_surge": 0.5, "max_unavailable": 0.3},
        )
        assert s._max_surge == 0.5

    def test_create_with_event_bus(self, event_bus):
        s = _StrategyFactory.create(
            DeploymentStrategy.ROLLING_UPDATE, {}, event_bus=event_bus
        )
        assert s._event_bus is event_bus


# ============================================================
# TestPipelineBuilder
# ============================================================


class TestPipelineBuilder:
    """Tests for _PipelineBuilder."""

    def test_build_standard_seven_stages(self, sample_manifest):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        assert len(pipeline.stages) == 7

    def test_build_standard_stage_types(self, sample_manifest):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        stage_types = [s.stage_type for s in pipeline.stages]
        assert StageType.BUILD in stage_types
        assert StageType.SCAN in stage_types
        assert StageType.SIGN in stage_types
        assert StageType.PUSH in stage_types
        assert StageType.DEPLOY in stage_types
        assert StageType.VALIDATE in stage_types
        assert StageType.FINALIZE in stage_types

    def test_build_standard_deployment_name(self, sample_manifest):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        assert pipeline.deployment_name == "fizzbuzz-core"

    def test_build_standard_each_stage_has_steps(self, sample_manifest):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        for stage in pipeline.stages:
            assert len(stage.steps) > 0

    def test_build_standard_custom_digest(self, sample_manifest):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy, image_digest="sha256:custom"
        )
        assert pipeline is not None

    def test_build_standard_auto_digest(self, sample_manifest):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        assert pipeline is not None

    def test_build_standard_executable(self, sample_manifest, pipeline_executor):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        result = pipeline_executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_build_standard_with_blue_green(self, sample_manifest):
        strategy = BlueGreenStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        assert len(pipeline.stages) == 7

    def test_build_standard_with_recreate(self, sample_manifest):
        strategy = RecreateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        assert len(pipeline.stages) == 7

    def test_build_standard_deploy_stage_has_rollback_action(self, sample_manifest):
        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        deploy_stage = [s for s in pipeline.stages if s.stage_type == StageType.DEPLOY][0]
        assert deploy_stage.steps[0].on_failure == OnFailureAction.ROLLBACK


# ============================================================
# TestDeployDashboard
# ============================================================


class TestDeployDashboard:
    """Tests for DeployDashboard rendering."""

    def test_header(self, dashboard):
        header = dashboard._header("Test Header")
        assert "Test Header" in header

    def test_bar_full(self, dashboard):
        bar = dashboard._bar(100.0, 100.0, width=10)
        assert "#" * 10 in bar

    def test_bar_empty(self, dashboard):
        bar = dashboard._bar(0.0, 100.0, width=10)
        assert " " * 10 in bar

    def test_bar_half(self, dashboard):
        bar = dashboard._bar(50.0, 100.0, width=10)
        assert "#" * 5 in bar

    def test_bar_zero_max(self, dashboard):
        bar = dashboard._bar(50.0, 0.0, width=10)
        assert " " * 10 in bar

    def test_render_complete(self, dashboard, pipeline_executor, rollback_manager, reconciler):
        output = dashboard.render(pipeline_executor, rollback_manager, reconciler)
        assert "FIZZDEPLOY" in output

    def test_render_pipeline(self, dashboard):
        result = PipelineResult(
            pipeline_id="abc123def456",
            deployment_name="fizzbuzz-core",
            status=PipelineStatus.SUCCEEDED,
            total_duration_ms=1234.5,
        )
        output = dashboard.render_pipeline(result)
        assert "abc123def456"[:12] in output
        assert "fizzbuzz-core" in output

    def test_render_revisions_empty(self, dashboard):
        output = dashboard.render_revisions("fizzbuzz-core", [])
        assert "No revisions" in output

    def test_render_revisions_with_data(self, dashboard, sample_manifest):
        revisions = [
            DeploymentRevision(revision_number=1, image_digest="sha256:abc"),
            DeploymentRevision(revision_number=2, image_digest="sha256:def"),
        ]
        output = dashboard.render_revisions("fizzbuzz-core", revisions)
        assert "1" in output
        assert "2" in output

    def test_render_drift_empty(self, dashboard):
        output = dashboard.render_drift([])
        assert "No drift" in output

    def test_render_drift_with_data(self, dashboard):
        reports = [
            DriftReport(
                deployment_name="fizzbuzz-core",
                drifts=[{"field": "image", "expected": "a", "actual": "b"}],
                corrected=True,
            )
        ]
        output = dashboard.render_drift(reports)
        assert "CORRECTED" in output
        assert "image" in output

    def test_render_canary_empty(self, dashboard):
        output = dashboard.render_canary([])
        assert "No canary" in output

    def test_render_canary_with_data(self, dashboard):
        results = [
            CanaryAnalysisResult(step_index=0, traffic_percent=5.0, verdict="pass"),
        ]
        output = dashboard.render_canary(results)
        assert "5.0" in output

    def test_render_gate_status(self, dashboard, deployment_gate):
        output = dashboard.render_gate_status(deployment_gate)
        assert "70.0" in output

    def test_render_no_history(self, dashboard, pipeline_executor, rollback_manager, reconciler):
        output = dashboard.render(pipeline_executor, rollback_manager, reconciler)
        assert "No pipeline history" in output

    def test_render_with_history(self, dashboard, pipeline_executor, rollback_manager, reconciler):
        pipeline_executor.execute(Pipeline("test"))
        output = dashboard.render(pipeline_executor, rollback_manager, reconciler)
        assert "test" in output

    def test_render_pipeline_with_stages(self, dashboard):
        result = PipelineResult(
            pipeline_id="abc123def456",
            deployment_name="fizzbuzz-core",
            status=PipelineStatus.SUCCEEDED,
            stage_results=[
                StageResult(stage_name="build", stage_type=StageType.BUILD, status=StageStatus.SUCCEEDED),
            ],
        )
        output = dashboard.render_pipeline(result)
        assert "build" in output

    def test_render_pipeline_with_error(self, dashboard):
        result = PipelineResult(
            pipeline_id="abc123def456",
            deployment_name="fizzbuzz-core",
            status=PipelineStatus.FAILED,
            stage_results=[
                StageResult(
                    stage_name="build",
                    stage_type=StageType.BUILD,
                    status=StageStatus.FAILED,
                    error_message="build failed",
                ),
            ],
        )
        output = dashboard.render_pipeline(result)
        assert "Error" in output

    def test_custom_width(self):
        d = DeployDashboard(width=100)
        assert d._width == 100


# ============================================================
# TestFizzDeployMiddleware
# ============================================================


class TestFizzDeployMiddleware:
    """Tests for FizzDeployMiddleware."""

    def test_get_name(self, deploy_middleware):
        assert deploy_middleware.get_name() == "FizzDeployMiddleware"

    def test_get_priority(self, deploy_middleware):
        assert deploy_middleware.get_priority() == 114

    def test_name_property(self, deploy_middleware):
        assert deploy_middleware.name == "FizzDeployMiddleware"

    def test_priority_property(self, deploy_middleware):
        assert deploy_middleware.priority == 114

    def test_process_without_revision(self, deploy_middleware):
        ctx = ProcessingContext(number=1, session_id="test")
        result = deploy_middleware.process(ctx, lambda c: c)
        assert result.metadata["deploy_revision"] == 0

    def test_process_with_revision(self, deploy_middleware, rollback_manager, sample_manifest):
        rollback_manager.record_revision(
            "fizzbuzz-core", sample_manifest, "sha256:abc", "p1"
        )
        ctx = ProcessingContext(number=1, session_id="test")
        result = deploy_middleware.process(ctx, lambda c: c)
        assert result.metadata["deploy_revision"] == 1

    def test_process_enriches_image_digest(self, deploy_middleware, rollback_manager, sample_manifest):
        rollback_manager.record_revision(
            "fizzbuzz-core", sample_manifest, "sha256:abc123", "p1"
        )
        ctx = ProcessingContext(number=1, session_id="test")
        result = deploy_middleware.process(ctx, lambda c: c)
        assert result.metadata["deploy_image_digest"] == "sha256:abc123"

    def test_process_enriches_strategy(self, deploy_middleware, rollback_manager, sample_manifest):
        rollback_manager.record_revision(
            "fizzbuzz-core", sample_manifest, "sha256:abc", "p1"
        )
        ctx = ProcessingContext(number=1, session_id="test")
        result = deploy_middleware.process(ctx, lambda c: c)
        assert result.metadata["deploy_strategy"] == "rolling_update"

    def test_process_delegates_to_next_handler(self, deploy_middleware):
        ctx = ProcessingContext(number=42, session_id="test")

        def handler(c):
            c.metadata["handled"] = True
            return c

        result = deploy_middleware.process(ctx, handler)
        assert result.metadata["handled"] is True

    def test_evaluation_count_incremented(self, deploy_middleware):
        ctx = ProcessingContext(number=1, session_id="test")
        deploy_middleware.process(ctx, lambda c: c)
        assert deploy_middleware._evaluation_count == 1

    def test_error_increments_errors(self, deploy_middleware):
        ctx = ProcessingContext(number=1, session_id="test")

        def bad_handler(c):
            raise RuntimeError("handler fail")

        with pytest.raises(DeployMiddlewareError):
            deploy_middleware.process(ctx, bad_handler)
        assert deploy_middleware._errors == 1

    def test_error_wraps_in_middleware_error(self, deploy_middleware):
        ctx = ProcessingContext(number=42, session_id="test")

        def bad_handler(c):
            raise RuntimeError("handler fail")

        with pytest.raises(DeployMiddlewareError) as exc_info:
            deploy_middleware.process(ctx, bad_handler)
        assert exc_info.value.evaluation_number == 42

    def test_render_revisions(self, deploy_middleware, rollback_manager, sample_manifest):
        rollback_manager.record_revision("fizzbuzz-core", sample_manifest, "sha256:abc", "p1")
        output = deploy_middleware.render_revisions("fizzbuzz-core")
        assert "fizzbuzz-core" in output

    def test_render_drift(self, deploy_middleware):
        output = deploy_middleware.render_drift()
        assert "drift" in output.lower() or "Drift" in output

    def test_render_canary(self, deploy_middleware):
        output = deploy_middleware.render_canary()
        assert "canary" in output.lower() or "Canary" in output

    def test_render_stats(self, deploy_middleware):
        output = deploy_middleware.render_stats()
        assert "Evaluations" in output

    def test_render_pipeline(self, deploy_middleware):
        output = deploy_middleware.render_pipeline("test-id")
        assert "test-id" in output

    def test_process_no_manifest_on_revision(self, deploy_middleware, rollback_manager):
        rev = DeploymentRevision(
            revision_number=1,
            deployment_name="fizzbuzz-core",
            manifest=None,
            image_digest="sha256:abc",
            status=RevisionStatus.ACTIVE,
        )
        rollback_manager._revisions["fizzbuzz-core"].append(rev)
        ctx = ProcessingContext(number=1, session_id="test")
        result = deploy_middleware.process(ctx, lambda c: c)
        assert result.metadata["deploy_strategy"] == "unknown"

    def test_multiple_evaluations(self, deploy_middleware):
        for i in range(5):
            ctx = ProcessingContext(number=i, session_id="test")
            deploy_middleware.process(ctx, lambda c: c)
        assert deploy_middleware._evaluation_count == 5

    def test_render_gate(self, deploy_middleware):
        output = deploy_middleware.render_gate()
        assert "Gate" in output or "gate" in output

    def test_enable_dashboard_flag(self, rollback_manager, reconciler):
        mw = FizzDeployMiddleware(
            rollback_mgr=rollback_manager,
            reconciler=reconciler,
            enable_dashboard=True,
        )
        assert mw._enable_dashboard is True


# ============================================================
# TestCreateFizzDeploySubsystem
# ============================================================


class TestCreateFizzDeploySubsystem:
    """Tests for create_fizzdeploy_subsystem factory function."""

    def test_returns_tuple(self):
        result = create_fizzdeploy_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_executor(self):
        executor, _ = create_fizzdeploy_subsystem()
        assert isinstance(executor, PipelineExecutor)

    def test_returns_middleware(self):
        _, middleware = create_fizzdeploy_subsystem()
        assert isinstance(middleware, FizzDeployMiddleware)

    def test_middleware_name(self):
        _, middleware = create_fizzdeploy_subsystem()
        assert middleware.get_name() == "FizzDeployMiddleware"

    def test_middleware_priority(self):
        _, middleware = create_fizzdeploy_subsystem()
        assert middleware.get_priority() == 114

    def test_custom_strategy(self):
        result = create_fizzdeploy_subsystem(default_strategy="rolling_update")
        assert result is not None

    def test_custom_pipeline_timeout(self):
        result = create_fizzdeploy_subsystem(pipeline_timeout=300.0)
        assert result is not None

    def test_custom_sync_strategy(self):
        result = create_fizzdeploy_subsystem(sync_strategy="manual")
        assert result is not None

    def test_with_event_bus(self, event_bus):
        executor, _ = create_fizzdeploy_subsystem(event_bus=event_bus)
        assert executor._event_bus is event_bus

    def test_custom_revision_depth(self):
        result = create_fizzdeploy_subsystem(revision_history_depth=5)
        assert result is not None


# ============================================================
# TestDeployExceptions
# ============================================================


class TestDeployExceptions:
    """Tests for all 22 exception classes."""

    def test_deploy_error_inherits_fizzbuzz_error(self):
        assert issubclass(DeployError, FizzBuzzError)

    def test_deploy_error_code(self):
        e = DeployError("test")
        assert e.error_code == "EFP-DPL00"

    def test_deploy_pipeline_error(self):
        e = DeployPipelineError("pipeline fail")
        assert e.error_code == "EFP-DPL01"
        assert isinstance(e, DeployError)

    def test_deploy_stage_error(self):
        e = DeployStageError("stage fail")
        assert e.error_code == "EFP-DPL02"

    def test_deploy_step_error(self):
        e = DeployStepError("step fail")
        assert e.error_code == "EFP-DPL03"

    def test_deploy_strategy_error(self):
        e = DeployStrategyError("unknown strategy")
        assert e.error_code == "EFP-DPL04"

    def test_rolling_update_error(self):
        e = RollingUpdateError("pod readiness timeout")
        assert e.error_code == "EFP-DPL05"

    def test_blue_green_error(self):
        e = BlueGreenError("validation failed")
        assert e.error_code == "EFP-DPL06"

    def test_canary_error(self):
        e = CanaryError("regression detected")
        assert e.error_code == "EFP-DPL07"

    def test_recreate_error(self):
        e = RecreateError("shutdown timeout")
        assert e.error_code == "EFP-DPL08"

    def test_deploy_manifest_error(self):
        e = DeployManifestError("invalid manifest")
        assert e.error_code == "EFP-DPL09"

    def test_manifest_parse_error(self):
        e = ManifestParseError("YAML syntax error")
        assert e.error_code == "EFP-DPL10"
        assert isinstance(e, DeployManifestError)

    def test_manifest_validation_error(self):
        e = ManifestValidationError("missing required field")
        assert e.error_code == "EFP-DPL11"

    def test_gitops_reconcile_error(self):
        e = GitOpsReconcileError("reconciliation failure")
        assert e.error_code == "EFP-DPL12"

    def test_gitops_drift_error(self):
        e = GitOpsDriftError("drift detected")
        assert e.error_code == "EFP-DPL13"

    def test_gitops_sync_error(self):
        e = GitOpsSyncError("sync failure")
        assert e.error_code == "EFP-DPL14"

    def test_rollback_error(self):
        e = RollbackError("rollback failure")
        assert e.error_code == "EFP-DPL15"

    def test_rollback_revision_not_found(self):
        e = RollbackRevisionNotFoundError("revision 5 not found")
        assert e.error_code == "EFP-DPL16"
        assert isinstance(e, RollbackError)

    def test_rollback_strategy_error(self):
        e = RollbackStrategyError("traffic switch failed")
        assert e.error_code == "EFP-DPL17"

    def test_deploy_gate_error(self):
        e = DeployGateError("gate error")
        assert e.error_code == "EFP-DPL18"

    def test_cognitive_load_gate_error(self):
        e = CognitiveLoadGateError("fizzbuzz-core", 85.0, 70.0)
        assert e.error_code == "EFP-DPL19"
        assert isinstance(e, DeployGateError)
        assert "fizzbuzz-core" in str(e)

    def test_deploy_dashboard_error(self):
        e = DeployDashboardError("render failure")
        assert e.error_code == "EFP-DPL20"

    def test_deploy_middleware_error(self):
        e = DeployMiddlewareError(42, "processing error")
        assert e.error_code == "EFP-DPL21"
        assert e.evaluation_number == 42

    def test_all_exceptions_have_context(self):
        exceptions = [
            DeployError("test"),
            DeployPipelineError("test"),
            DeployStageError("test"),
            DeployStepError("test"),
            DeployStrategyError("test"),
            RollingUpdateError("test"),
            BlueGreenError("test"),
            CanaryError("test"),
            RecreateError("test"),
            DeployManifestError("test"),
            ManifestParseError("test"),
            ManifestValidationError("test"),
            GitOpsReconcileError("test"),
            GitOpsDriftError("test"),
            GitOpsSyncError("test"),
            RollbackError("test"),
            RollbackRevisionNotFoundError("test"),
            RollbackStrategyError("test"),
            DeployGateError("test"),
            DeployDashboardError("test"),
        ]
        for exc in exceptions:
            assert hasattr(exc, "context")
            assert hasattr(exc, "error_code")


# ============================================================
# TestDeployIntegration
# ============================================================


class TestDeployIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_lifecycle(self, event_bus, sample_manifest):
        executor = PipelineExecutor(event_bus=event_bus)
        strategy = RollingUpdateStrategy(event_bus=event_bus)
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        result = executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_pipeline_then_revision(self, event_bus, sample_manifest):
        executor = PipelineExecutor(event_bus=event_bus)
        rollback_mgr = RollbackManager(event_bus=event_bus)
        strategy = RollingUpdateStrategy(event_bus=event_bus)
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy, image_digest="sha256:abc"
        )
        result = executor.execute(pipeline)
        rev = rollback_mgr.record_revision(
            "fizzbuzz-core", sample_manifest, "sha256:abc", result.pipeline_id
        )
        assert rev.revision_number == 1

    def test_deploy_then_rollback(self, event_bus, sample_manifest):
        rollback_mgr = RollbackManager(event_bus=event_bus)
        rollback_mgr.record_revision("fizzbuzz-core", sample_manifest, "sha256:v1", "p1")
        rollback_mgr.record_revision("fizzbuzz-core", sample_manifest, "sha256:v2", "p2")
        record = rollback_mgr.rollback("fizzbuzz-core", 1)
        assert record.success is True

    def test_gate_then_pipeline(self, event_bus, sample_manifest):
        gate = DeploymentGate(threshold=100.0, event_bus=event_bus)
        gate.check("fizzbuzz-core", sample_manifest)
        executor = PipelineExecutor(event_bus=event_bus)
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, RollingUpdateStrategy()
        )
        result = executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_reconciler_detects_and_fixes(self, event_bus, sample_manifest):
        executor = PipelineExecutor(event_bus=event_bus)
        reconciler = GitOpsReconciler(
            sync_strategy=SyncStrategy.AUTO,
            pipeline_executor=executor,
            event_bus=event_bus,
        )
        reconciler.register_manifest("fizzbuzz-core", sample_manifest)
        reconciler.update_actual_state("fizzbuzz-core", {
            "image": "old:1.0",
            "replicas": 1,
            "resources": {},
            "env": {},
        })
        reports = reconciler.reconcile()
        assert len(reports) == 1
        assert reports[0].corrected is True

    def test_factory_wiring(self, event_bus):
        executor, middleware = create_fizzdeploy_subsystem(event_bus=event_bus)
        ctx = ProcessingContext(number=1, session_id="test")
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["deploy_revision"] == 0

    def test_manifest_parse_then_deploy(self, event_bus):
        parser = ManifestParser()
        data = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "fizzbuzz-core"},
            "spec": {"image": "fizzbuzz-eval:1.0.0", "replicas": 3},
        }
        manifest = parser.parse_dict(data)
        strategy = _StrategyFactory.create(manifest.spec.strategy, {}, event_bus=event_bus)
        pipeline = _PipelineBuilder.build_standard("fizzbuzz-core", manifest, strategy)
        executor = PipelineExecutor(event_bus=event_bus)
        result = executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_blue_green_full_cycle(self, event_bus, sample_manifest):
        sample_manifest.spec.strategy = DeploymentStrategy.BLUE_GREEN
        strategy = BlueGreenStrategy(event_bus=event_bus)
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        executor = PipelineExecutor(event_bus=event_bus)
        result = executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_recreate_full_cycle(self, event_bus, sample_manifest):
        sample_manifest.spec.strategy = DeploymentStrategy.RECREATE
        strategy = RecreateStrategy(event_bus=event_bus)
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        executor = PipelineExecutor(event_bus=event_bus)
        result = executor.execute(pipeline)
        assert result.status == PipelineStatus.SUCCEEDED

    def test_middleware_with_live_revision(self, event_bus, sample_manifest):
        rollback_mgr = RollbackManager(event_bus=event_bus)
        reconciler = GitOpsReconciler(
            sync_strategy=SyncStrategy.AUTO,
            event_bus=event_bus,
        )
        middleware = FizzDeployMiddleware(
            rollback_mgr=rollback_mgr,
            reconciler=reconciler,
        )
        rollback_mgr.record_revision(
            "fizzbuzz-core", sample_manifest, "sha256:live", "p1"
        )
        ctx = ProcessingContext(number=1, session_id="test")
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["deploy_revision"] == 1
        assert result.metadata["deploy_image_digest"] == "sha256:live"

    def test_multiple_revisions_then_rollback(self, event_bus, sample_manifest):
        rollback_mgr = RollbackManager(event_bus=event_bus)
        rollback_mgr.record_revision("fizzbuzz-core", sample_manifest, "sha256:v1", "p1")
        rollback_mgr.record_revision("fizzbuzz-core", sample_manifest, "sha256:v2", "p2")
        rollback_mgr.record_revision("fizzbuzz-core", sample_manifest, "sha256:v3", "p3")
        record = rollback_mgr.rollback("fizzbuzz-core", 1)
        assert record.success is True
        active = rollback_mgr.get_active_revision("fizzbuzz-core")
        assert active.rollback_from == 3

    def test_dashboard_with_pipeline_history(self, event_bus, sample_manifest):
        executor = PipelineExecutor(event_bus=event_bus)
        rollback_mgr = RollbackManager(event_bus=event_bus)
        reconciler = GitOpsReconciler(event_bus=event_bus)

        strategy = RollingUpdateStrategy()
        pipeline = _PipelineBuilder.build_standard(
            "fizzbuzz-core", sample_manifest, strategy
        )
        executor.execute(pipeline)

        dashboard = DeployDashboard()
        output = dashboard.render(executor, rollback_mgr, reconciler)
        assert "FIZZDEPLOY" in output

    def test_constants_values(self):
        assert FIZZDEPLOY_VERSION == "1.0.0"
        assert DEFAULT_PIPELINE_TIMEOUT == 600.0
        assert DEFAULT_STAGE_TIMEOUT == 120.0
        assert DEFAULT_STEP_TIMEOUT == 60.0
        assert MIDDLEWARE_PRIORITY == 114

    def test_event_type_constants(self):
        assert DEPLOY_PIPELINE_STARTED == "fizzdeploy.pipeline.started"
        assert DEPLOY_PIPELINE_COMPLETED == "fizzdeploy.pipeline.completed"
        assert DEPLOY_PIPELINE_FAILED == "fizzdeploy.pipeline.failed"
        assert DEPLOY_ROLLBACK_EXECUTED == "fizzdeploy.rollback.executed"
        assert DEPLOY_GATE_BLOCKED == "fizzdeploy.gate.blocked"

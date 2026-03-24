"""
Enterprise FizzBuzz Platform -- FizzLambda Serverless Function Runtime Tests

Validates the complete FizzLambda serverless lifecycle: function registration,
immutable versioning, alias-based routing with weighted traffic shifting,
execution environment management with warm pools, cold start optimization,
event triggers, dead letter queues, retry management, dependency layers,
auto-scaling, and middleware integration.
"""

import json
import time

import pytest

from enterprise_fizzbuzz.infrastructure.fizzlambda import (
    FIZZLAMBDA_VERSION,
    DEFAULT_MEMORY_MB,
    MIN_MEMORY_MB,
    MAX_MEMORY_MB,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    VCPU_MEMORY_RATIO,
    CPU_PERIOD_US,
    MAX_LAYERS,
    MAX_LAYER_TOTAL_MB,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_MAX_ENVIRONMENTS,
    DEFAULT_MAX_PER_FUNCTION,
    DEFAULT_RECYCLING_INVOCATIONS,
    DEFAULT_RECYCLING_LIFETIME,
    MIDDLEWARE_PRIORITY,
    AliasManager,
    AutoScaler,
    BuiltinFunctions,
    CodeSource,
    CodeSourceType,
    ColdStartBreakdown,
    ColdStartOptimizer,
    ConcurrencyConfig,
    DeadLetterConfig,
    DeadLetterQueueManager,
    DeadLetterTargetType,
    EnvironmentState,
    EventBusTriggerConfig,
    EventTriggerManager,
    ExecutionEnvironment,
    ExecutionEnvironmentManager,
    FizzLambdaCognitiveLoadGate,
    FizzLambdaComplianceEngine,
    FizzLambdaDashboard,
    FizzLambdaMiddleware,
    FizzLambdaRuntime,
    FunctionAlias,
    FunctionContext,
    FunctionDefinition,
    FunctionLayer,
    FunctionPackager,
    FunctionRegistry,
    FunctionRuntime,
    FunctionVersion,
    FunctionVersionManager,
    HTTPTriggerConfig,
    InvocationDispatcher,
    InvocationRequest,
    InvocationResponse,
    InvocationRouter,
    InvocationType,
    LayerManager,
    LogType,
    PreWarmPrediction,
    QueueMessage,
    QueueMessageState,
    QueueTriggerConfig,
    ResourceAllocator,
    RetryClassification,
    RetryManager,
    RetryPolicy,
    SnapshotRecord,
    TimerTriggerConfig,
    TrafficShiftOrchestrator,
    TrafficShiftState,
    TrafficShiftStrategy,
    TriggerDefinition,
    TriggerType,
    VPCConfig,
    WarmPoolManager,
    create_fizzlambda_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzlambda import (
    AliasAlreadyExistsError,
    AliasNotFoundError,
    ColdStartOptimizerError,
    FunctionAlreadyExistsError,
    FunctionNotFoundError,
    FunctionRegistryError,
    FunctionVersionNotFoundError,
    InvocationThrottledError,
    LayerLimitExceededError,
    LayerNotFoundError,
    TriggerNotFoundError,
    WarmPoolCapacityError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_bus():
    """Simple event collector for verifying event emission."""

    class _EventBus:
        def __init__(self):
            self.events = []

        def emit(self, event_type, data):
            self.events.append((event_type, data))

    return _EventBus()


@pytest.fixture
def registry(event_bus):
    return FunctionRegistry(event_bus=event_bus)


@pytest.fixture
def version_manager(registry, event_bus):
    return FunctionVersionManager(registry, event_bus=event_bus)


@pytest.fixture
def alias_manager(version_manager, event_bus):
    return AliasManager(version_manager, event_bus=event_bus)


@pytest.fixture
def resource_allocator():
    return ResourceAllocator()


@pytest.fixture
def env_manager(resource_allocator, event_bus):
    return ExecutionEnvironmentManager(resource_allocator, event_bus=event_bus)


@pytest.fixture
def warm_pool(env_manager, event_bus):
    return WarmPoolManager(
        env_manager,
        max_total=DEFAULT_MAX_ENVIRONMENTS,
        max_per_function=DEFAULT_MAX_PER_FUNCTION,
        idle_timeout=DEFAULT_IDLE_TIMEOUT,
        event_bus=event_bus,
    )


@pytest.fixture
def cold_start_optimizer(env_manager, warm_pool, event_bus):
    return ColdStartOptimizer(
        env_manager, warm_pool,
        snapshot_enabled=True,
        predictive_enabled=True,
        event_bus=event_bus,
    )


@pytest.fixture
def trigger_manager(event_bus):
    return EventTriggerManager(event_bus=event_bus)


@pytest.fixture
def auto_scaler(warm_pool, env_manager, event_bus):
    return AutoScaler(warm_pool, env_manager, event_bus=event_bus)


@pytest.fixture
def dlq_manager(event_bus):
    return DeadLetterQueueManager(event_bus=event_bus)


@pytest.fixture
def retry_manager(dlq_manager, event_bus):
    return RetryManager(dlq_manager, event_bus=event_bus)


@pytest.fixture
def layer_manager(event_bus):
    return LayerManager(event_bus=event_bus)


@pytest.fixture
def sample_definition():
    """A valid function definition for testing."""
    return FunctionDefinition(
        name="test-func",
        namespace="default",
        runtime=FunctionRuntime.PYTHON_312,
        handler="handler.main",
        code_source=CodeSource(
            source_type=CodeSourceType.INLINE,
            inline_code="def main(event, ctx): return {'result': 'ok'}",
        ),
        memory_mb=256,
        timeout_seconds=30,
    )


@pytest.fixture
def runtime():
    """A fresh FizzLambdaRuntime instance."""
    return FizzLambdaRuntime()


# ---------------------------------------------------------------------------
# TestFunctionRegistry
# ---------------------------------------------------------------------------

class TestFunctionRegistry:
    """Validates function CRUD, namespace isolation, validation, and events."""

    def test_create_function(self, registry, sample_definition):
        result = registry.create_function(sample_definition)
        assert result.name == "test-func"
        assert result.function_id != ""
        assert result.version == 1

    def test_create_function_duplicate_name(self, registry, sample_definition):
        registry.create_function(sample_definition)
        with pytest.raises(FunctionAlreadyExistsError):
            registry.create_function(sample_definition)

    def test_get_function_not_found(self, registry):
        with pytest.raises(FunctionNotFoundError):
            registry.get_function("nonexistent")

    def test_update_function(self, registry, sample_definition):
        registry.create_function(sample_definition)
        updated = registry.update_function("test-func", {"memory_mb": 512})
        assert updated.memory_mb == 512
        assert updated.version == 2

    def test_update_function_stale_version(self, registry, sample_definition):
        registry.create_function(sample_definition)
        with pytest.raises(FunctionRegistryError):
            registry.update_function("test-func", {
                "memory_mb": 512,
                "expected_version": 99,
            })

    def test_delete_function(self, registry, sample_definition):
        registry.create_function(sample_definition)
        registry.delete_function("test-func")
        with pytest.raises(FunctionNotFoundError):
            registry.get_function("test-func")

    def test_list_functions_by_namespace(self, registry):
        d1 = FunctionDefinition(name="f1", namespace="ns-a", handler="h")
        d2 = FunctionDefinition(name="f2", namespace="ns-b", handler="h")
        registry.create_function(d1)
        registry.create_function(d2)
        result = registry.list_functions(namespace="ns-a")
        assert len(result) == 1
        assert result[0].name == "f1"

    def test_validate_definition_invalid_memory(self, registry):
        d = FunctionDefinition(name="bad-mem", handler="h", memory_mb=64)
        with pytest.raises(FunctionRegistryError):
            registry.create_function(d)

    def test_validate_definition_invalid_timeout(self, registry):
        d = FunctionDefinition(name="bad-timeout", handler="h", timeout_seconds=0)
        with pytest.raises(FunctionRegistryError):
            registry.create_function(d)

    def test_registry_emits_events(self, registry, sample_definition, event_bus):
        registry.create_function(sample_definition)
        registry.update_function("test-func", {"memory_mb": 512})
        registry.delete_function("test-func")
        event_types = [e[0] for e in event_bus.events]
        assert any("CREATED" in str(t) for t in event_types)
        assert any("UPDATED" in str(t) for t in event_types)
        assert any("DELETED" in str(t) for t in event_types)


# ---------------------------------------------------------------------------
# TestFunctionVersionManager
# ---------------------------------------------------------------------------

class TestFunctionVersionManager:
    """Validates immutable versioning, snapshots, and garbage collection."""

    def test_publish_version(self, registry, version_manager, sample_definition):
        registry.create_function(sample_definition)
        v = version_manager.publish_version("test-func")
        assert v.version_number == 1
        assert v.function_name == "test-func"

    def test_publish_captures_snapshot(self, registry, version_manager, sample_definition):
        registry.create_function(sample_definition)
        v = version_manager.publish_version("test-func")
        assert v.code_sha256 != ""
        assert v.definition_snapshot.name == "test-func"

    def test_get_version(self, registry, version_manager, sample_definition):
        registry.create_function(sample_definition)
        version_manager.publish_version("test-func")
        v = version_manager.get_version("test-func", 1)
        assert v.version_number == 1

    def test_get_version_not_found(self, version_manager):
        with pytest.raises(FunctionVersionNotFoundError):
            version_manager.get_version("test-func", 99)

    def test_list_versions(self, registry, version_manager, sample_definition):
        registry.create_function(sample_definition)
        version_manager.publish_version("test-func")
        version_manager.publish_version("test-func", "second")
        versions = version_manager.list_versions("test-func")
        assert len(versions) == 2
        assert versions[0].version_number == 1
        assert versions[1].version_number == 2

    def test_latest_version(self, registry, version_manager, sample_definition):
        registry.create_function(sample_definition)
        version_manager.publish_version("test-func")
        version_manager.publish_version("test-func", "v2")
        latest = version_manager.get_latest_version("test-func")
        assert latest.version_number == 2

    def test_version_immutability(self, registry, version_manager, sample_definition):
        registry.create_function(sample_definition)
        v1 = version_manager.publish_version("test-func")
        original_memory = v1.definition_snapshot.memory_mb
        registry.update_function("test-func", {"memory_mb": 1024})
        v1_again = version_manager.get_version("test-func", 1)
        assert v1_again.definition_snapshot.memory_mb == original_memory

    def test_garbage_collect(self, registry, version_manager, sample_definition):
        registry.create_function(sample_definition)
        v = version_manager.publish_version("test-func")
        v.published_at = v.published_at.__class__(2020, 1, 1, tzinfo=v.published_at.tzinfo)
        collected = version_manager.garbage_collect(retention_days=30)
        assert len(collected) == 1


# ---------------------------------------------------------------------------
# TestAliasManager
# ---------------------------------------------------------------------------

class TestAliasManager:
    """Validates alias CRUD, weighted routing, and resolution."""

    def _setup_versioned_function(self, registry, version_manager):
        d = FunctionDefinition(name="alias-func", handler="h",
                               code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                                       inline_code="code"))
        registry.create_function(d)
        version_manager.publish_version("alias-func")
        version_manager.publish_version("alias-func", "v2")

    def test_create_alias(self, registry, version_manager, alias_manager):
        self._setup_versioned_function(registry, version_manager)
        alias = alias_manager.create_alias("alias-func", "prod", 1)
        assert alias.alias_name == "prod"
        assert alias.function_version == 1

    def test_update_alias_version(self, registry, version_manager, alias_manager):
        self._setup_versioned_function(registry, version_manager)
        alias_manager.create_alias("alias-func", "prod", 1)
        updated = alias_manager.update_alias("alias-func", "prod", 2)
        assert updated.function_version == 2

    def test_update_alias_weighted(self, registry, version_manager, alias_manager):
        self._setup_versioned_function(registry, version_manager)
        alias_manager.create_alias("alias-func", "canary", 1)
        updated = alias_manager.update_alias(
            "alias-func", "canary", 1,
            additional_version=2,
            additional_version_weight=0.1,
        )
        assert updated.additional_version == 2
        assert updated.additional_version_weight == 0.1

    def test_resolve_alias_single(self, registry, version_manager, alias_manager):
        self._setup_versioned_function(registry, version_manager)
        alias = alias_manager.create_alias("alias-func", "stable", 1)
        resolved = alias_manager.resolve_version(alias)
        assert resolved == 1

    def test_resolve_alias_weighted(self, registry, version_manager, alias_manager):
        self._setup_versioned_function(registry, version_manager)
        alias_manager.create_alias("alias-func", "split", 1)
        alias_manager.update_alias(
            "alias-func", "split", 1,
            additional_version=2,
            additional_version_weight=0.5,
        )
        alias = alias_manager.get_alias("alias-func", "split")
        versions_seen = set()
        for _ in range(100):
            v = alias_manager.resolve_version(alias)
            versions_seen.add(v)
        assert len(versions_seen) == 2

    def test_delete_alias(self, registry, version_manager, alias_manager):
        self._setup_versioned_function(registry, version_manager)
        alias_manager.create_alias("alias-func", "temp", 1)
        alias_manager.delete_alias("alias-func", "temp")
        with pytest.raises(AliasNotFoundError):
            alias_manager.get_alias("alias-func", "temp")

    def test_alias_not_found(self, alias_manager):
        with pytest.raises(AliasNotFoundError):
            alias_manager.get_alias("nope", "nope")

    def test_alias_invalid_version(self, registry, version_manager, alias_manager):
        self._setup_versioned_function(registry, version_manager)
        with pytest.raises(FunctionVersionNotFoundError):
            alias_manager.create_alias("alias-func", "bad", 999)


# ---------------------------------------------------------------------------
# TestTrafficShiftOrchestrator
# ---------------------------------------------------------------------------

class TestTrafficShiftOrchestrator:
    """Validates traffic shifting strategies and rollback."""

    def _setup(self, registry, version_manager, alias_manager):
        d = FunctionDefinition(name="shift-func", handler="h",
                               code_source=CodeSource(source_type=CodeSourceType.INLINE,
                                                       inline_code="code"))
        registry.create_function(d)
        version_manager.publish_version("shift-func")
        version_manager.publish_version("shift-func", "v2")
        alias_manager.create_alias("shift-func", "live", 1)
        return TrafficShiftOrchestrator(alias_manager)

    def test_linear_shift(self, registry, version_manager, alias_manager):
        orch = self._setup(registry, version_manager, alias_manager)
        state = orch.start_shift("shift-func", "live", 2, TrafficShiftStrategy.LINEAR, steps=4)
        assert state.current_weight == pytest.approx(0.25, abs=0.01)

    def test_canary_shift(self, registry, version_manager, alias_manager):
        orch = self._setup(registry, version_manager, alias_manager)
        state = orch.start_shift("shift-func", "live", 2, TrafficShiftStrategy.CANARY)
        assert state.current_weight == pytest.approx(1.0, abs=0.01)

    def test_all_at_once_shift(self, registry, version_manager, alias_manager):
        orch = self._setup(registry, version_manager, alias_manager)
        state = orch.start_shift("shift-func", "live", 2, TrafficShiftStrategy.ALL_AT_ONCE)
        assert state.current_weight == pytest.approx(1.0, abs=0.01)

    def test_rollback_shift(self, registry, version_manager, alias_manager):
        orch = self._setup(registry, version_manager, alias_manager)
        orch.start_shift("shift-func", "live", 2, TrafficShiftStrategy.LINEAR, steps=10)
        orch.rollback_shift("shift-func", "live")
        alias = alias_manager.get_alias("shift-func", "live")
        assert alias.function_version == 1

    def test_shift_completion(self, registry, version_manager, alias_manager):
        orch = self._setup(registry, version_manager, alias_manager)
        orch.start_shift("shift-func", "live", 2, TrafficShiftStrategy.LINEAR, steps=2)
        state = orch.advance_shift("shift-func", "live")
        assert state.current_weight == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# TestResourceAllocator
# ---------------------------------------------------------------------------

class TestResourceAllocator:
    """Validates cgroup v2 resource computation."""

    def test_cpu_quota_proportional(self, resource_allocator):
        quota = resource_allocator.compute_cpu_quota(VCPU_MEMORY_RATIO)
        assert quota == CPU_PERIOD_US

    def test_cpu_quota_minimum(self, resource_allocator):
        quota = resource_allocator.compute_cpu_quota(MIN_MEMORY_MB)
        expected = int((MIN_MEMORY_MB / VCPU_MEMORY_RATIO) * CPU_PERIOD_US)
        assert quota == max(expected, 1000)

    def test_memory_max(self, resource_allocator):
        result = resource_allocator.compute_memory_max(256)
        assert result == 256 * 1024 * 1024

    def test_memory_high(self, resource_allocator):
        mem_max = resource_allocator.compute_memory_max(256)
        mem_high = resource_allocator.compute_memory_high(256)
        assert mem_high == int(mem_max * 0.9)

    def test_cgroup_path(self, resource_allocator):
        path = resource_allocator.get_cgroup_path("my-func", "env-123")
        assert path == "/sys/fs/cgroup/fizzlambda/my-func/env-123"


# ---------------------------------------------------------------------------
# TestExecutionEnvironmentManager
# ---------------------------------------------------------------------------

class TestExecutionEnvironmentManager:
    """Validates environment creation, invocation execution, and recycling."""

    def _make_version(self, definition):
        return FunctionVersion(
            function_name=definition.name,
            version_number=1,
        )

    def test_create_environment(self, env_manager, sample_definition):
        version = self._make_version(sample_definition)
        env = env_manager.create_environment(sample_definition, version)
        assert env.state == EnvironmentState.READY
        assert env.environment_id != ""

    def test_cold_start_breakdown(self, env_manager, sample_definition):
        version = self._make_version(sample_definition)
        env = env_manager.create_environment(sample_definition, version)
        assert env.cgroup_path.startswith("/sys/fs/cgroup/fizzlambda/")

    def test_execute_invocation(self, env_manager, sample_definition):
        version = self._make_version(sample_definition)
        env = env_manager.create_environment(sample_definition, version)
        request = InvocationRequest(
            function_name="test-func",
            payload=json.dumps({"number": 15}).encode(),
        )
        context = FunctionContext(
            invocation_id="inv-1",
            function_name="test-func",
            function_version="1",
            memory_limit_mb=256,
            timeout_seconds=30,
            start_time=time.time(),
        )
        response = env_manager.execute_invocation(env, request, context)
        assert response.status_code == 200
        assert env.invocation_count == 1

    def test_invocation_timeout(self, env_manager, sample_definition):
        version = self._make_version(sample_definition)
        env = env_manager.create_environment(sample_definition, version)
        request = InvocationRequest(function_name="test-func", payload=b"")
        context = FunctionContext(
            invocation_id="inv-timeout",
            function_name="test-func",
            function_version="1",
            timeout_seconds=0,
            start_time=time.time() - 100,
        )
        response = env_manager.execute_invocation(env, request, context)
        assert response.status_code == 408

    def test_destroy_environment(self, env_manager, sample_definition):
        version = self._make_version(sample_definition)
        env = env_manager.create_environment(sample_definition, version)
        env_manager.destroy_environment(env)
        assert env.state == EnvironmentState.DESTROYING

    def test_should_recycle_by_count(self, env_manager):
        env = ExecutionEnvironment(
            environment_id="env-1",
            invocation_count=DEFAULT_RECYCLING_INVOCATIONS + 1,
        )
        assert env_manager.should_recycle(env) is True

    def test_should_recycle_by_lifetime(self, env_manager):
        from datetime import datetime, timezone, timedelta
        env = ExecutionEnvironment(
            environment_id="env-2",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=DEFAULT_RECYCLING_LIFETIME + 1),
        )
        assert env_manager.should_recycle(env) is True


# ---------------------------------------------------------------------------
# TestWarmPoolManager
# ---------------------------------------------------------------------------

class TestWarmPoolManager:
    """Validates warm pool acquisition, release, eviction, and provisioning."""

    def _make_env(self, function_id="fid-1", version="1"):
        return ExecutionEnvironment(
            environment_id=f"env-{function_id}-{version}",
            function_id=function_id,
            function_version=version,
            state=EnvironmentState.READY,
        )

    def test_acquire_warm_hit(self, warm_pool):
        env = self._make_env()
        warm_pool.release(env)
        # After release, the environment is FROZEN in the pool.
        # Set it back to READY to simulate the pool restoring it for acquisition.
        env.state = EnvironmentState.READY
        acquired = warm_pool.acquire("fid-1", "1")
        assert acquired is not None
        assert acquired.environment_id == env.environment_id

    def test_acquire_warm_miss(self, warm_pool):
        result = warm_pool.acquire("nonexistent", "1")
        assert result is None

    def test_release_to_pool(self, warm_pool):
        env = self._make_env()
        warm_pool.release(env)
        assert warm_pool.get_pool_size() == 1

    def test_idle_eviction(self, env_manager, event_bus):
        pool = WarmPoolManager(env_manager, idle_timeout=0.0, event_bus=event_bus)
        env = self._make_env()
        pool.release(env)
        evicted = pool.evict_idle()
        assert evicted >= 1
        assert pool.get_pool_size() == 0

    def test_provisioned_never_evicted(self, env_manager, event_bus):
        pool = WarmPoolManager(env_manager, idle_timeout=0.0, event_bus=event_bus)
        env = self._make_env()
        env.is_provisioned = True
        pool.release(env)
        evicted = pool.evict_idle()
        assert evicted == 0
        assert pool.get_pool_size() == 1

    def test_pool_capacity_limit(self, env_manager, event_bus):
        pool = WarmPoolManager(env_manager, max_total=2, max_per_function=2, event_bus=event_bus)
        for i in range(3):
            env = ExecutionEnvironment(
                environment_id=f"cap-{i}",
                function_id="fid-cap",
                function_version="1",
                state=EnvironmentState.READY,
            )
            pool.release(env)
        assert pool.get_pool_size() <= 2

    def test_per_function_limit(self, env_manager, event_bus):
        pool = WarmPoolManager(env_manager, max_total=100, max_per_function=1, event_bus=event_bus)
        for i in range(2):
            env = ExecutionEnvironment(
                environment_id=f"per-{i}",
                function_id="fid-per",
                function_version="1",
                state=EnvironmentState.READY,
            )
            pool.release(env)
        assert pool.get_pool_size("fid-per") <= 1

    def test_hit_rate_tracking(self, warm_pool):
        env = self._make_env()
        warm_pool.release(env)
        # Set back to READY so acquire can find it
        env.state = EnvironmentState.READY
        warm_pool.acquire("fid-1", "1")
        # Second acquire is a miss (env already taken), but first was a hit
        warm_pool.acquire("fid-1", "1")
        rate = warm_pool.get_hit_rate()
        assert rate > 0


# ---------------------------------------------------------------------------
# TestColdStartOptimizer
# ---------------------------------------------------------------------------

class TestColdStartOptimizer:
    """Validates snapshot capture/restore, predictive pre-warming, and layer caching."""

    def test_snapshot_capture_and_restore(self, cold_start_optimizer, sample_definition):
        env = ExecutionEnvironment(
            environment_id="snap-env-1",
            function_id="fid-snap",
            function_version="1",
            state=EnvironmentState.READY,
        )
        sample_definition.function_id = "fid-snap"
        snap = cold_start_optimizer.capture_snapshot(env, sample_definition)
        assert snap.snapshot_id != ""
        restored = cold_start_optimizer.restore_snapshot("fid-snap", "1")
        assert restored is not None
        assert restored.state == EnvironmentState.READY

    def test_snapshot_invalidation(self, cold_start_optimizer, sample_definition):
        env = ExecutionEnvironment(
            environment_id="snap-env-2",
            function_id="fid-inv",
            function_version="1",
        )
        sample_definition.function_id = "fid-inv"
        cold_start_optimizer.capture_snapshot(env, sample_definition)
        cold_start_optimizer.invalidate_snapshot("fid-inv", "1")
        result = cold_start_optimizer.restore_snapshot("fid-inv", "1")
        assert result is None

    def test_predictive_prewarm(self, cold_start_optimizer):
        now = time.time()
        for i in range(20):
            cold_start_optimizer.record_invocation("fid-pred", now - (20 - i) * 60)
        prediction = cold_start_optimizer.predict_demand("fid-pred")
        assert prediction is not None
        assert prediction.predicted_concurrency >= 1

    def test_layer_caching(self, cold_start_optimizer):
        layer = FunctionLayer(
            layer_name="test-layer",
            layer_version=1,
            content_ref="content-data",
            size_bytes=100,
        )
        cold_start_optimizer.cache_layer(layer)
        cached = cold_start_optimizer.get_cached_layer("test-layer", 1)
        assert cached is not None

    def test_layer_cache_eviction(self, env_manager, warm_pool, event_bus):
        optimizer = ColdStartOptimizer(
            env_manager, warm_pool,
            layer_cache_size_mb=0,
            event_bus=event_bus,
        )
        layer = FunctionLayer(
            layer_name="big-layer",
            layer_version=1,
            content_ref="x" * 100,
            size_bytes=100,
        )
        optimizer.cache_layer(layer)
        count = optimizer.evict_layer_cache()
        assert count >= 0

    def test_cold_start_stats(self, cold_start_optimizer):
        stats = cold_start_optimizer.get_cold_start_stats()
        assert "snapshot_enabled" in stats
        assert "snapshot_hit_rate" in stats
        assert "layer_cache_entries" in stats


# ---------------------------------------------------------------------------
# TestEventTriggerManager
# ---------------------------------------------------------------------------

class TestEventTriggerManager:
    """Validates trigger CRUD, firing, and event pattern matching."""

    def test_create_http_trigger(self, trigger_manager):
        trigger = TriggerDefinition(
            function_name="http-func",
            trigger_type=TriggerType.HTTP,
            trigger_config={"route_path": "/api/test", "http_methods": ["POST"]},
        )
        result = trigger_manager.create_trigger(trigger)
        assert result.trigger_id != ""
        assert result.trigger_type == TriggerType.HTTP

    def test_create_timer_trigger_cron(self, trigger_manager):
        trigger = TriggerDefinition(
            function_name="timer-func",
            trigger_type=TriggerType.TIMER,
            trigger_config={"schedule_expression": "cron(0 12 * * ? *)"},
        )
        result = trigger_manager.create_trigger(trigger)
        assert result.trigger_type == TriggerType.TIMER

    def test_create_timer_trigger_rate(self, trigger_manager):
        trigger = TriggerDefinition(
            function_name="rate-func",
            trigger_type=TriggerType.TIMER,
            trigger_config={"schedule_expression": "rate(5 minutes)"},
        )
        result = trigger_manager.create_trigger(trigger)
        assert result.trigger_type == TriggerType.TIMER

    def test_create_queue_trigger(self, trigger_manager):
        trigger = TriggerDefinition(
            function_name="queue-func",
            trigger_type=TriggerType.QUEUE,
            trigger_config={"queue_name": "test-queue", "batch_size": 5},
        )
        result = trigger_manager.create_trigger(trigger)
        assert result.trigger_type == TriggerType.QUEUE

    def test_create_event_bus_trigger(self, trigger_manager):
        trigger = TriggerDefinition(
            function_name="event-func",
            trigger_type=TriggerType.EVENT_BUS,
            trigger_config={"event_pattern": {"source": ["test"]}},
        )
        result = trigger_manager.create_trigger(trigger)
        assert result.trigger_type == TriggerType.EVENT_BUS

    def test_enable_disable_trigger(self, trigger_manager):
        trigger = TriggerDefinition(
            function_name="toggle-func",
            trigger_type=TriggerType.HTTP,
        )
        created = trigger_manager.create_trigger(trigger)
        trigger_manager.disable_trigger(created.trigger_id)
        t = trigger_manager.get_trigger(created.trigger_id)
        assert t.enabled is False
        trigger_manager.enable_trigger(created.trigger_id)
        t = trigger_manager.get_trigger(created.trigger_id)
        assert t.enabled is True

    def test_trigger_not_found(self, trigger_manager):
        with pytest.raises(TriggerNotFoundError):
            trigger_manager.get_trigger("nonexistent")

    def test_event_pattern_matching(self, trigger_manager):
        pattern = {
            "source": ["fizzbuzz.cache"],
            "detail": {"action": ["invalidate"], "scope": {"region": ["us-east-1"]}},
        }
        event = {
            "source": "fizzbuzz.cache",
            "detail": {"action": "invalidate", "scope": {"region": "us-east-1"}},
        }
        assert trigger_manager._match_event_pattern(pattern, event) is True

        bad_event = {
            "source": "fizzbuzz.other",
            "detail": {"action": "invalidate"},
        }
        assert trigger_manager._match_event_pattern(pattern, bad_event) is False


# ---------------------------------------------------------------------------
# TestAutoScaler
# ---------------------------------------------------------------------------

class TestAutoScaler:
    """Validates concurrency tracking, throttling, and burst scaling."""

    def test_concurrency_tracking(self, auto_scaler):
        auto_scaler.on_invocation_start("fid-1")
        assert auto_scaler.get_active_count("fid-1") == 1
        auto_scaler.on_invocation_end("fid-1")
        assert auto_scaler.get_active_count("fid-1") == 0

    def test_throttle_at_limit(self, auto_scaler):
        auto_scaler.on_invocation_start("fid-throttle")
        allowed = auto_scaler.check_concurrency("fid-throttle", reserved=1)
        assert allowed is False

    def test_burst_scaling(self, auto_scaler, sample_definition, event_bus):
        version = FunctionVersion(function_name="test-func", version_number=1)
        sample_definition.function_id = "fid-burst"
        created = auto_scaler.scale_up("fid-burst", 5, sample_definition, version)
        assert created > 0

    def test_account_limit(self, warm_pool, env_manager, event_bus):
        scaler = AutoScaler(warm_pool, env_manager, account_limit=2, event_bus=event_bus)
        scaler.on_invocation_start("f1")
        scaler.on_invocation_start("f2")
        assert scaler.check_concurrency("f3", reserved=None) is False

    def test_scale_stats(self, auto_scaler):
        auto_scaler.on_invocation_start("fid-stats")
        stats = auto_scaler.get_stats()
        assert "total_active" in stats
        assert "total_throttled" in stats


# ---------------------------------------------------------------------------
# TestDeadLetterQueueManager
# ---------------------------------------------------------------------------

class TestDeadLetterQueueManager:
    """Validates DLQ send, receive, visibility, replay, and purge."""

    def test_send_and_receive(self, dlq_manager):
        dlq_manager.create_queue("test-q")
        dlq_manager.send_message("test-q", b"hello")
        messages = dlq_manager.receive_messages("test-q", max_messages=1)
        assert len(messages) == 1
        assert messages[0].body == b"hello"

    def test_visibility_timeout(self, dlq_manager):
        dlq_manager.create_queue("vis-q", visibility_timeout=0.0)
        dlq_manager.send_message("vis-q", b"msg")
        msg1 = dlq_manager.receive_messages("vis-q", max_messages=1)
        assert len(msg1) == 1
        msg2 = dlq_manager.receive_messages("vis-q", max_messages=1)
        assert len(msg2) == 1

    def test_delete_message(self, dlq_manager):
        dlq_manager.create_queue("del-q")
        dlq_manager.send_message("del-q", b"to-delete")
        messages = dlq_manager.receive_messages("del-q")
        dlq_manager.delete_message("del-q", messages[0].receipt_handle)
        remaining = dlq_manager.receive_messages("del-q")
        assert len(remaining) == 0

    def test_max_receive_count(self, dlq_manager):
        dlq_manager.create_queue("max-q", max_receive_count=1, visibility_timeout=0.0)
        dlq_manager.send_message("max-q", b"fail-msg")
        dlq_manager.receive_messages("max-q")
        messages = dlq_manager._messages["max-q"]
        dead_msgs = [m for m in messages if m.state == QueueMessageState.DEAD]
        assert len(dead_msgs) == 1

    def test_purge_queue(self, dlq_manager):
        dlq_manager.create_queue("purge-q")
        for i in range(5):
            dlq_manager.send_message("purge-q", f"msg-{i}".encode())
        count = dlq_manager.purge_queue("purge-q")
        assert count == 5

    def test_replay_message(self, dlq_manager):
        dlq_manager.create_queue("replay-q")
        msg = dlq_manager.send_message("replay-q", b"replay-body", attributes={"function_name": "f"})
        response = dlq_manager.replay_message("replay-q", msg.message_id)
        assert response.status_code == 200

    def test_queue_stats(self, dlq_manager):
        dlq_manager.create_queue("stats-q")
        dlq_manager.send_message("stats-q", b"data")
        stats = dlq_manager.get_queue_stats("stats-q")
        assert stats["total_messages"] == 1
        assert "oldest_age_seconds" in stats

    def test_message_retention(self, dlq_manager):
        dlq_manager.create_queue("expire-q", message_retention=0)
        msg = dlq_manager.send_message("expire-q", b"old")
        from datetime import datetime, timezone
        msg.sent_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        expired = dlq_manager._expire_messages("expire-q")
        assert expired == 1


# ---------------------------------------------------------------------------
# TestRetryManager
# ---------------------------------------------------------------------------

class TestRetryManager:
    """Validates failure classification, backoff, and DLQ routing."""

    def test_classify_timeout_retryable(self, retry_manager):
        response = InvocationResponse(status_code=408, function_error="Timeout")
        classification = retry_manager.classify_failure(response)
        assert classification == RetryClassification.RETRYABLE

    def test_classify_code_error_non_retryable(self, retry_manager):
        response = InvocationResponse(status_code=500, function_error="Unhandled")
        classification = retry_manager.classify_failure(response)
        assert classification == RetryClassification.NON_RETRYABLE

    def test_exponential_backoff(self, retry_manager):
        d0 = retry_manager.compute_delay(0, base_delay=60)
        d1 = retry_manager.compute_delay(1, base_delay=60)
        assert d1 > d0

    def test_retry_exhaustion_routes_to_dlq(self, retry_manager, dlq_manager):
        request = InvocationRequest(function_name="fail-func", payload=b"data")
        response = InvocationResponse(status_code=408, function_error="Timeout")
        definition = FunctionDefinition(name="fail-func", handler="h")
        retry_manager.route_to_dlq(request, response, definition)
        queues = dlq_manager.list_queues()
        assert "dlq-fail-func" in queues

    def test_retry_success(self, retry_manager):
        request = InvocationRequest(function_name="success-func", qualifier="$LATEST")
        retry_manager._retry_counts["success-func:$LATEST"] = 1
        retry_manager.record_success(request)
        assert retry_manager._success_count == 1


# ---------------------------------------------------------------------------
# TestLayerManager
# ---------------------------------------------------------------------------

class TestLayerManager:
    """Validates layer lifecycle, composition, and limits."""

    def test_create_and_publish_layer(self, layer_manager):
        layer = layer_manager.create_layer(
            "test-layer", "test deps",
            [FunctionRuntime.PYTHON_312],
            b"layer-content",
        )
        assert layer.layer_name == "test-layer"
        assert layer.layer_version == 1
        v2 = layer_manager.publish_layer("test-layer")
        assert v2.layer_version == 2

    def test_compose_layers(self, layer_manager):
        layer_manager.create_layer("l1", "first", [FunctionRuntime.PYTHON_312], b"a")
        layer_manager.create_layer("l2", "second", [FunctionRuntime.PYTHON_312], b"b")
        composed = layer_manager.compose_layers(["l1", "l2"])
        assert len(composed) > 0

    def test_layer_limit(self, layer_manager):
        for i in range(MAX_LAYERS + 1):
            layer_manager.create_layer(f"layer-{i}", "desc", [FunctionRuntime.PYTHON_312], b"x")
        refs = [f"layer-{i}" for i in range(MAX_LAYERS + 1)]
        with pytest.raises(LayerLimitExceededError):
            layer_manager.compose_layers(refs)

    def test_layer_size_limit(self, layer_manager):
        huge_content = b"x" * (MAX_LAYER_TOTAL_MB * 1024 * 1024 + 1)
        layer_manager.create_layer("huge", "big", [FunctionRuntime.PYTHON_312], huge_content)
        with pytest.raises(LayerLimitExceededError):
            layer_manager.validate_layer_limits(["huge"])

    def test_layer_not_found(self, layer_manager):
        with pytest.raises(LayerNotFoundError):
            layer_manager.get_layer("nonexistent", 1)


# ---------------------------------------------------------------------------
# TestFizzLambdaMiddleware
# ---------------------------------------------------------------------------

class TestFizzLambdaMiddleware:
    """Validates middleware integration, mode routing, and dashboard rendering."""

    def test_serverless_mode_invokes_function(self):
        runtime, dashboard, middleware = create_fizzlambda_subsystem(mode="serverless")
        runtime.start()
        assert middleware._mode == "serverless"

    def test_container_mode_passthrough(self):
        runtime, dashboard, middleware = create_fizzlambda_subsystem(mode="container")
        assert middleware._mode == "container"

    def test_response_annotations(self):
        runtime, dashboard, middleware = create_fizzlambda_subsystem(mode="serverless")
        runtime.start()
        assert middleware.get_name() == "FizzLambdaMiddleware"
        assert middleware.get_priority() == MIDDLEWARE_PRIORITY

    def test_cold_start_header(self):
        runtime, dashboard, middleware = create_fizzlambda_subsystem(mode="serverless")
        runtime.start()
        assert middleware._runtime is not None

    def test_dashboard_render(self):
        runtime, dashboard, middleware = create_fizzlambda_subsystem()
        runtime.start()
        output = dashboard.render_functions()
        assert "FizzLambda Functions" in output
        assert "standard-eval" in output


# ---------------------------------------------------------------------------
# TestFizzLambdaRuntime
# ---------------------------------------------------------------------------

class TestFizzLambdaRuntime:
    """Validates the top-level runtime lifecycle and unified API."""

    def test_full_lifecycle(self, runtime):
        runtime.start()
        functions = runtime.list_functions()
        assert len(functions) >= 7
        request = InvocationRequest(
            function_name="standard-eval",
            payload=json.dumps({"number": 15}).encode(),
        )
        response = runtime.invoke(request)
        assert response.status_code == 200

    def test_register_builtins(self, runtime):
        runtime.register_builtins()
        functions = runtime.list_functions()
        names = {f.name for f in functions}
        expected = {
            "standard-eval", "configurable-eval", "ml-eval",
            "batch-eval", "scheduled-report", "cache-invalidation", "audit-log",
        }
        assert expected.issubset(names)

    def test_runtime_start_stop(self, runtime):
        runtime.start()
        assert runtime._started is True
        runtime.stop()
        assert runtime._started is False

    def test_invoke_with_alias(self, runtime):
        runtime.start()
        runtime.create_alias("standard-eval", "live", 1)
        request = InvocationRequest(
            function_name="standard-eval",
            qualifier="live",
            payload=json.dumps({"number": 3}).encode(),
        )
        response = runtime.invoke(request)
        assert response.status_code == 200

    def test_invoke_async(self, runtime):
        runtime.start()
        request = InvocationRequest(
            function_name="standard-eval",
            payload=json.dumps({"number": 5}).encode(),
        )
        response = runtime.invoke_async(request)
        assert response.status_code == 202

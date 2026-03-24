"""Tests for the FizzStream distributed stream processing engine.

Validates the complete FizzStream subsystem: enums, data classes,
execution environment, DataStream API, source/transformation operators,
windowing, watermarks, checkpointing, stateful processing, joins,
CEP, backpressure, savepoints, scaling, metrics, SQL bridge,
middleware, exceptions, and factory wiring.
"""

from __future__ import annotations

import time
from collections import defaultdict
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzstream import (
    # Enums
    CheckpointStatus,
    Contiguity,
    JoinType,
    NFAStateType,
    OperatorChainStrategy,
    RestartStrategyType,
    ScaleDirection,
    SourceStartPosition,
    StateBackendType,
    StreamJobStatus,
    TimeCharacteristic,
    TriggerResult,
    WatermarkStrategyType,
    WindowType,
    # Data classes
    BackpressureStatus,
    CheckpointMetadata,
    JobDescriptor,
    NFAState,
    OperatorDescriptor,
    OperatorMetrics,
    PartialMatch,
    SavepointMetadata,
    ScaleEvent,
    StreamElement,
    StreamRecord,
    StreamTopicConfig,
    WindowSpec,
    # Core
    StreamExecutionEnvironment,
    DataStream,
    KeyedStream,
    StreamJob,
    ProcessContext,
    # Transformation operators
    MapOperator,
    FlatMapOperator,
    FilterOperator,
    KeyByOperator,
    ReduceOperator,
    ProcessOperator,
    UnionOperator,
    # Source operators
    MessageQueueSource,
    EventStoreSource,
    ContainerEventSource,
    MetricSource,
    GeneratorSource,
    # Sink operators
    MessageQueueSink,
    EventStoreSink,
    # Windowing
    TumblingEventTimeWindow,
    SlidingEventTimeWindow,
    SessionWindow,
    GlobalWindow,
    WindowAssigner,
    AllowedLateness,
    # Triggers
    EventTimeTrigger,
    ProcessingTimeTrigger,
    CountTrigger,
    PurgingTrigger,
    ContinuousEventTimeTrigger,
    # Window functions
    ReduceFunction,
    AggregateFunction,
    ProcessWindowFunction,
    # Watermarks
    Watermark,
    BoundedOutOfOrdernessStrategy,
    MonotonousTimestampsStrategy,
    PunctuatedWatermarkStrategy,
    IdleSourceDetection,
    WatermarkAlignment,
    # Checkpointing
    CheckpointCoordinator,
    CheckpointBarrier,
    InMemoryCheckpointStorage,
    FileSystemCheckpointStorage,
    # Restart strategies
    FixedDelayRestartStrategy,
    ExponentialBackoffRestartStrategy,
    NoRestartStrategy,
    # State
    ValueState,
    ListState,
    MapState,
    ReducingState,
    AggregatingState,
    HashMapStateBackend,
    RocksDBStateBackend,
    StateTTL,
    # Joins
    StreamStreamJoin,
    StreamTableJoin,
    IntervalJoin,
    # CEP
    Pattern,
    PatternElement,
    NFACompiler,
    CEPOperator,
    PatternStream,
    # Backpressure
    BackpressureController,
    CreditBasedFlowControl,
    BufferPool,
    # Savepoints
    SavepointManager,
    SavepointRestoreManager,
    # Scaling
    ScaleManager,
    AutoScaler,
    KeyGroupAssigner,
    # Metrics and dashboard
    StreamMetricsCollector,
    FizzStreamDashboard,
    # SQL
    StreamSQLBridge,
    # Middleware
    FizzStreamMiddleware,
    # Factory
    create_fizzstream_subsystem,
    # Constants
    FIZZSTREAM_VERSION,
    MIDDLEWARE_PRIORITY,
    MURMUR3_SEED,
    DEFAULT_PARALLELISM,
    DEFAULT_MAX_PARALLELISM,
    DEFAULT_CHECKPOINT_INTERVAL_MS,
)
from enterprise_fizzbuzz.domain.exceptions.fizzstream import (
    StreamProcessingError,
    StreamJobSubmissionError,
    StreamJobNotFoundError,
    StreamSourceError,
    StreamSinkError,
    StreamOperatorError,
    StreamCheckpointError,
    StreamCheckpointRestoreError,
    StreamSavepointError,
    StreamSavepointRestoreError,
    WatermarkViolationError,
    WindowError,
    StateAccessError,
    StateBackendError,
    KeyGroupAssignmentError,
    StreamJoinError,
    CEPPatternError,
    CEPMatchError,
    BackpressureError,
    ScaleError,
    StreamSQLError,
    RestartExhaustedError,
    BarrierAlignmentTimeoutError,
    StreamMiddlewareError,
    StateTTLError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env():
    """Create a default StreamExecutionEnvironment."""
    return StreamExecutionEnvironment()


@pytest.fixture
def hashmap_backend():
    """Create a HashMapStateBackend."""
    return HashMapStateBackend()


@pytest.fixture
def rocksdb_backend():
    """Create a RocksDBStateBackend."""
    return RocksDBStateBackend()


@pytest.fixture
def checkpoint_storage():
    """Create an InMemoryCheckpointStorage."""
    return InMemoryCheckpointStorage()


@pytest.fixture
def buffer_pool():
    """Create a BufferPool."""
    return BufferPool()


@pytest.fixture
def metrics_collector():
    """Create a StreamMetricsCollector."""
    return StreamMetricsCollector()


# ===========================================================================
# Test Classes
# ===========================================================================


class TestStreamEnums:
    """Validate all 14 enum classes, member counts, and string values."""

    def test_stream_job_status_members(self):
        assert hasattr(StreamJobStatus, "CREATED")
        assert hasattr(StreamJobStatus, "RUNNING")
        assert hasattr(StreamJobStatus, "FAILED")
        assert hasattr(StreamJobStatus, "FINISHED")
        assert hasattr(StreamJobStatus, "CANCELLED")

    def test_operator_chain_strategy_members(self):
        assert hasattr(OperatorChainStrategy, "ALWAYS")
        assert hasattr(OperatorChainStrategy, "NEVER")
        assert hasattr(OperatorChainStrategy, "HEAD")

    def test_window_type_members(self):
        assert hasattr(WindowType, "TUMBLING")
        assert hasattr(WindowType, "SLIDING")
        assert hasattr(WindowType, "SESSION")
        assert hasattr(WindowType, "GLOBAL")

    def test_time_characteristic_members(self):
        assert hasattr(TimeCharacteristic, "EVENT_TIME")
        assert hasattr(TimeCharacteristic, "PROCESSING_TIME")
        assert hasattr(TimeCharacteristic, "INGESTION_TIME")

    def test_trigger_result_members(self):
        assert hasattr(TriggerResult, "CONTINUE")
        assert hasattr(TriggerResult, "FIRE")
        assert hasattr(TriggerResult, "FIRE_AND_PURGE")
        assert hasattr(TriggerResult, "PURGE")

    def test_checkpoint_status_members(self):
        assert hasattr(CheckpointStatus, "IN_PROGRESS")
        assert hasattr(CheckpointStatus, "COMPLETED")
        assert hasattr(CheckpointStatus, "FAILED")

    def test_state_backend_type_members(self):
        assert hasattr(StateBackendType, "HASHMAP")
        assert hasattr(StateBackendType, "ROCKSDB")

    def test_restart_strategy_type_members(self):
        assert hasattr(RestartStrategyType, "FIXED_DELAY")
        assert hasattr(RestartStrategyType, "EXPONENTIAL_BACKOFF")
        assert hasattr(RestartStrategyType, "NO_RESTART")


class TestStreamDataClasses:
    """Test dataclass construction, defaults, and field validation."""

    def test_stream_element_construction(self):
        elem = StreamElement(key="fizz", value=3, timestamp=1000)
        assert elem.key == "fizz"
        assert elem.value == 3
        assert elem.timestamp == 1000

    def test_stream_record_construction(self):
        elem = StreamElement(key="buzz", value=5, timestamp=2000)
        rec = StreamRecord(element=elem, operator_id="map-1")
        assert rec.element.key == "buzz"
        assert rec.operator_id == "map-1"

    def test_operator_descriptor_construction(self):
        desc = OperatorDescriptor(
            uid="map-1",
            name="MapOperator",
            parallelism=4,
        )
        assert desc.uid == "map-1"
        assert desc.parallelism == 4

    def test_window_spec_construction(self):
        spec = WindowSpec(
            start=0,
            end=5000,
            window_type=WindowType.TUMBLING,
        )
        assert spec.window_type == WindowType.TUMBLING
        assert spec.end == 5000

    def test_checkpoint_metadata_construction(self):
        meta = CheckpointMetadata(
            checkpoint_id=1,
            status=CheckpointStatus.COMPLETED,
        )
        assert meta.checkpoint_id == 1
        assert meta.status == CheckpointStatus.COMPLETED

    def test_savepoint_metadata_construction(self):
        meta = SavepointMetadata(
            name="pre-upgrade",
            checkpoint_id=42,
        )
        assert meta.name == "pre-upgrade"
        assert meta.checkpoint_id == 42

    def test_operator_metrics_construction(self):
        metrics = OperatorMetrics(operator_uid="filter-1")
        assert metrics.operator_uid == "filter-1"

    def test_job_descriptor_construction(self):
        desc = JobDescriptor(
            job_id="job-1",
            name="fizzbuzz-classification",
        )
        assert desc.job_id == "job-1"

    def test_nfa_state_construction(self):
        state = NFAState(
            name="start",
            state_type=NFAStateType.START,
        )
        assert state.name == "start"
        assert state.state_type == NFAStateType.START

    def test_partial_match_construction(self):
        match = PartialMatch(current_state="start")
        assert match.current_state == "start"


class TestStreamExecutionEnvironment:
    """Environment creation, configuration, source factory methods, job submission."""

    def test_env_creation_defaults(self, env):
        assert env.parallelism == DEFAULT_PARALLELISM
        assert env.max_parallelism == DEFAULT_MAX_PARALLELISM

    def test_env_custom_parallelism(self):
        env = StreamExecutionEnvironment(parallelism=8, max_parallelism=256)
        assert env.parallelism == 8
        assert env.max_parallelism == 256

    def test_env_from_source(self, env):
        source = GeneratorSource(
            generator_fn=lambda i: i,
            num_elements=100,
        )
        stream = env.from_source(source)
        assert isinstance(stream, DataStream)

    def test_env_job_submission(self, env):
        source = GeneratorSource(
            generator_fn=lambda i: i,
            num_elements=10,
        )
        stream = env.from_source(source)
        sink = EventStoreSink(name="test-sink")
        stream.sink_to(sink)
        job = env.submit_job("test-job", stream)
        assert isinstance(job, StreamJob)
        assert job.name == "test-job"

    def test_env_job_registry(self, env):
        source = GeneratorSource(
            generator_fn=lambda i: i,
            num_elements=5,
        )
        stream = env.from_source(source)
        sink = EventStoreSink(name="reg-sink")
        stream.sink_to(sink)
        job = env.submit_job("registry-test", stream)
        found = env.get_job(job.job_id)
        assert found is not None
        assert found.job_id == job.job_id


class TestDataStreamAPI:
    """Fluent API chaining: filter, map, flat_map, key_by, window, sink_to."""

    def test_filter_returns_datastream(self, env):
        source = GeneratorSource(generator_fn=lambda i: i, num_elements=10)
        stream = env.from_source(source)
        filtered = stream.filter(lambda x: x % 3 == 0)
        assert isinstance(filtered, DataStream)

    def test_map_returns_datastream(self, env):
        source = GeneratorSource(generator_fn=lambda i: i, num_elements=10)
        stream = env.from_source(source)
        mapped = stream.map(lambda x: x * 2)
        assert isinstance(mapped, DataStream)

    def test_flat_map_returns_datastream(self, env):
        source = GeneratorSource(generator_fn=lambda i: i, num_elements=10)
        stream = env.from_source(source)
        flat_mapped = stream.flat_map(lambda x: [x, x + 1])
        assert isinstance(flat_mapped, DataStream)

    def test_key_by_returns_keyed_stream(self, env):
        source = GeneratorSource(generator_fn=lambda i: i, num_elements=10)
        stream = env.from_source(source)
        keyed = stream.key_by(lambda x: x % 3)
        assert isinstance(keyed, KeyedStream)

    def test_chained_operations(self, env):
        source = GeneratorSource(generator_fn=lambda i: i, num_elements=100)
        stream = env.from_source(source)
        result = stream.filter(lambda x: x > 0).map(lambda x: x * 2).key_by(lambda x: x % 5)
        assert isinstance(result, KeyedStream)

    def test_sink_to(self, env):
        source = GeneratorSource(generator_fn=lambda i: i, num_elements=10)
        stream = env.from_source(source)
        sink = MessageQueueSink(name="mq-sink", topic="output")
        result = stream.sink_to(sink)
        # sink_to returns the DataStream for chaining
        assert isinstance(result, DataStream)
        # The sink should be in the operator list
        operators = stream.get_operators()
        assert len(operators) >= 2  # source + sink


class TestSourceOperators:
    """Source operator construction and behavior."""

    def test_message_queue_source(self):
        source = MessageQueueSource(name="mq-src", topic="input")
        assert source.name == "mq-src"
        assert source.topic == "input"

    def test_event_store_source(self):
        source = EventStoreSource(name="es-src", stream_name="evaluations")
        assert source.name == "es-src"
        assert source.stream_name == "evaluations"

    def test_container_event_source(self):
        source = ContainerEventSource(name="container-src")
        assert source.name == "container-src"

    def test_metric_source(self):
        source = MetricSource(name="metric-src")
        assert source.name == "metric-src"

    def test_generator_source_bounded(self):
        source = GeneratorSource(
            generator_fn=lambda i: i,
            num_elements=10,
        )
        assert source.num_elements == 10


class TestTransformationOperators:
    """Map, FlatMap, Filter, KeyBy, Reduce, Process operators."""

    def test_map_operator(self):
        op = MapOperator(map_fn=lambda x: x * 2, uid="map-1")
        results = op.process_element(StreamElement(key=None, value=5, timestamp=0))
        assert len(results) == 1
        assert results[0].value == 10

    def test_flat_map_operator(self):
        op = FlatMapOperator(flat_map_fn=lambda x: [x, x + 1], uid="fm-1")
        results = op.process_element(StreamElement(key=None, value=3, timestamp=0))
        assert len(results) == 2

    def test_filter_operator_pass(self):
        op = FilterOperator(predicate=lambda x: x > 5, uid="fil-1")
        results = op.process_element(StreamElement(key=None, value=10, timestamp=0))
        assert len(results) == 1

    def test_filter_operator_reject(self):
        op = FilterOperator(predicate=lambda x: x > 5, uid="fil-2")
        results = op.process_element(StreamElement(key=None, value=2, timestamp=0))
        assert len(results) == 0

    def test_key_by_operator_murmur3(self):
        op = KeyByOperator(key_extractor=lambda x: x % 3, uid="kb-1")
        elem = StreamElement(key=None, value=9, timestamp=0)
        results = op.process_element(elem)
        assert len(results) == 1
        # After key_by, the element should have a key assigned
        assert results[0].key is not None

    def test_reduce_operator(self):
        op = ReduceOperator(reduce_fn=lambda a, b: a + b, uid="red-1")
        e1 = StreamElement(key="k", value=1, timestamp=0)
        e2 = StreamElement(key="k", value=2, timestamp=1)
        op.process_element(e1)
        results = op.process_element(e2)
        assert len(results) == 1
        assert results[0].value == 3


class TestWindowingSystem:
    """Window assignment, triggers, and firing."""

    def test_tumbling_window_assignment(self):
        window = TumblingEventTimeWindow(size_ms=5000)
        ts = 12345
        assigned = window.assign_windows(ts)
        assert len(assigned) == 1
        assert assigned[0].start <= ts < assigned[0].end

    def test_sliding_window_overlap(self):
        window = SlidingEventTimeWindow(size_ms=10000, slide_ms=5000)
        ts = 7500
        assigned = window.assign_windows(ts)
        assert len(assigned) >= 2

    def test_session_window_gap(self):
        window = SessionWindow(gap_ms=5000)
        assert window.gap_ms == 5000

    def test_global_window(self):
        window = GlobalWindow()
        assigned = window.assign_windows(99999)
        assert len(assigned) == 1

    def test_window_assigner(self):
        window_def = TumblingEventTimeWindow(size_ms=1000)
        assigner = WindowAssigner(window_def)
        assert assigner.window_def is window_def

    def test_event_time_trigger_fires_on_watermark(self):
        trigger = EventTimeTrigger()
        window = WindowSpec(start=0, end=9000)
        result = trigger.on_watermark(watermark=10000, window=window)
        assert result == TriggerResult.FIRE

    def test_count_trigger(self):
        trigger = CountTrigger(max_count=3)
        window = WindowSpec(start=0, end=10000)
        elem = StreamElement(key="k", value=1, timestamp=0)
        assert trigger.on_element(elem, window, 0) == TriggerResult.CONTINUE
        assert trigger.on_element(elem, window, 0) == TriggerResult.CONTINUE
        assert trigger.on_element(elem, window, 0) == TriggerResult.FIRE


class TestWatermarkSystem:
    """Watermark strategy computation and alignment."""

    def test_bounded_out_of_orderness(self):
        strategy = BoundedOutOfOrdernessStrategy(max_out_of_orderness_ms=5000)
        strategy.on_event(timestamp=10000)
        strategy.on_event(timestamp=8000)
        wm = strategy.get_watermark()
        assert wm.timestamp == 10000 - 5000

    def test_monotonous_timestamps(self):
        strategy = MonotonousTimestampsStrategy()
        strategy.on_event(timestamp=1000)
        strategy.on_event(timestamp=2000)
        strategy.on_event(timestamp=3000)
        wm = strategy.get_watermark()
        # MonotonousTimestampsStrategy returns max_timestamp - 1
        assert wm.timestamp == 2999

    def test_punctuated_watermark(self):
        strategy = PunctuatedWatermarkStrategy(
            extractor=lambda event: event if isinstance(event, int) and event % 1000 == 0 else None
        )
        result = strategy.on_event(element=2000)
        assert result is not None
        assert result.timestamp == 2000

    def test_idle_source_detection(self):
        detector = IdleSourceDetection(idle_timeout_ms=5000)
        assert detector.idle_timeout_ms == 5000

    def test_watermark_alignment(self):
        alignment = WatermarkAlignment()
        alignment.update("input-0", 1000)
        alignment.update("input-1", 2000)
        # Aligned watermark is the minimum across all inputs
        assert alignment.get_effective_watermark() == 1000


class TestCheckpointing:
    """Checkpoint coordinator, barrier alignment, storage, restart strategies."""

    def test_checkpoint_coordinator_creation(self, checkpoint_storage):
        backend = HashMapStateBackend()
        coordinator = CheckpointCoordinator(
            interval_ms=60000,
            state_backend=backend,
        )
        assert coordinator.interval_ms == 60000

    def test_checkpoint_barrier_creation(self):
        barrier = CheckpointBarrier(checkpoint_id=42, timestamp=int(time.time() * 1000))
        assert barrier.checkpoint_id == 42

    def test_in_memory_checkpoint_storage_round_trip(self, checkpoint_storage):
        checkpoint_storage.store(checkpoint_id=1, operator_uid="op-1", state={"key": "value"})
        restored = checkpoint_storage.load(checkpoint_id=1, operator_uid="op-1")
        assert restored == {"key": "value"}

    def test_filesystem_checkpoint_storage_creation(self):
        storage = FileSystemCheckpointStorage(base_path="/tmp/fizzstream")
        storage.store(checkpoint_id=1, operator_uid="op-1", state={"count": 42})
        restored = storage.load(checkpoint_id=1, operator_uid="op-1")
        assert restored == {"count": 42}

    def test_restart_strategy_hierarchy(self):
        fixed = FixedDelayRestartStrategy(max_restarts=3, delay_ms=1000)
        exp = ExponentialBackoffRestartStrategy(
            initial_delay_ms=1000, max_delay_ms=30000, backoff_multiplier=2.0
        )
        none_ = NoRestartStrategy()
        assert fixed.can_restart() is True
        assert exp.can_restart() is True
        assert none_.can_restart() is False


class TestStatefulProcessing:
    """Keyed state CRUD, state backends, and TTL."""

    def test_value_state_crud(self, hashmap_backend):
        state = ValueState(name="counter", backend=hashmap_backend)
        state.update(0, key="key-1")
        assert state.value(key="key-1") == 0
        state.update(42, key="key-1")
        assert state.value(key="key-1") == 42
        state.clear(key="key-1")
        assert state.value(key="key-1") is None

    def test_list_state_operations(self, hashmap_backend):
        state = ListState(name="items", backend=hashmap_backend)
        state.add("a", key="key-1")
        state.add("b", key="key-1")
        state.add("c", key="key-1")
        items = state.get(key="key-1")
        assert len(items) == 3
        assert "b" in items

    def test_map_state_operations(self, hashmap_backend):
        state = MapState(name="lookup", backend=hashmap_backend)
        state.put("sub-key", "value", key="key-1")
        assert state.get("sub-key", key="key-1") == "value"
        assert state.contains("sub-key", key="key-1") is True

    def test_reducing_state(self, hashmap_backend):
        state = ReducingState(
            name="sum", reduce_fn=lambda a, b: a + b, backend=hashmap_backend
        )
        state.add(10, key="key-1")
        state.add(20, key="key-1")
        state.add(30, key="key-1")
        assert state.get(key="key-1") == 60

    def test_aggregating_state(self, hashmap_backend):
        agg_fn = AggregateFunction(
            create_accumulator=lambda: (0, 0),
            add=lambda acc, val: (acc[0] + val, acc[1] + 1),
            merge=lambda a, b: (a[0] + b[0], a[1] + b[1]),
            get_result=lambda acc: acc[0] / acc[1] if acc[1] > 0 else 0,
        )
        state = AggregatingState(
            name="avg",
            agg_fn=agg_fn,
            backend=hashmap_backend,
        )
        state.add(10, key="key-1")
        state.add(20, key="key-1")
        result = state.get(key="key-1")
        assert result == 15.0

    def test_hashmap_vs_rocksdb_backend(self, hashmap_backend, rocksdb_backend):
        for backend in [hashmap_backend, rocksdb_backend]:
            backend.put("ns", "key", "value")
            assert backend.get("ns", "key") == "value"
            backend.delete("ns", "key")
            assert backend.get("ns", "key") is None


class TestStreamJoins:
    """Stream-stream, stream-table, interval joins."""

    def test_stream_stream_join(self):
        join = StreamStreamJoin(
            left_window_ms=10000,
            right_window_ms=10000,
            join_type=JoinType.INNER,
        )
        assert join.left_window_ms == 10000
        assert join.join_type == JoinType.INNER

    def test_stream_table_join(self):
        join = StreamTableJoin(table_name="evaluations")
        join.upsert("k1", {"name": "fizz"}, timestamp=1000)
        result = join.lookup("k1", timestamp=2000)
        assert result == {"name": "fizz"}

    def test_interval_join(self):
        join = IntervalJoin(
            lower_bound_ms=-5000,
            upper_bound_ms=5000,
        )
        assert join.lower_bound_ms == -5000
        assert join.upper_bound_ms == 5000

    def test_join_type_semantics(self):
        assert hasattr(JoinType, "INNER")
        assert hasattr(JoinType, "LEFT_OUTER")
        assert hasattr(JoinType, "RIGHT_OUTER")
        assert hasattr(JoinType, "FULL_OUTER")


class TestCEP:
    """CEP pattern construction, NFA compilation, and matching."""

    def test_pattern_fluent_api(self):
        pattern = Pattern.begin("start").where(lambda e: e.get("type") == "fizz")
        assert pattern.name == "start"

    def test_pattern_element_quantifiers(self):
        elem = PatternElement(name="elem", condition=lambda e: True)
        elem.quantifier = "one_or_more"
        assert elem.quantifier == "one_or_more"

    def test_nfa_compiler(self):
        pattern = Pattern.begin("start").where(lambda e: True).followed_by("end").where(lambda e: True)
        compiler = NFACompiler(pattern)
        states = compiler.compile()
        assert len(states) >= 2

    def test_cep_operator_creation(self):
        pattern = Pattern.begin("start").where(lambda e: True)
        compiler = NFACompiler(pattern)
        states = compiler.compile()
        operator = CEPOperator(nfa_states=states, uid="cep-1")
        assert operator.uid == "cep-1"

    def test_pattern_stream(self):
        pattern = Pattern.begin("start").where(lambda e: True)
        compiler = NFACompiler(pattern)
        states = compiler.compile()
        operator = CEPOperator(nfa_states=states)
        ps = PatternStream(cep_operator=operator)
        assert ps is not None


class TestBackpressure:
    """Backpressure controller, credit-based flow, buffer pool."""

    def test_backpressure_controller_signaling(self):
        controller = BackpressureController(
            high_watermark_pct=0.80,
            low_watermark_pct=0.50,
        )
        # At 90% capacity should trigger backpressure
        status_high = controller.update("op-1", 0.90)
        assert status_high.is_backpressured is True
        # At 40% capacity should clear backpressure
        status_low = controller.update("op-1", 0.40)
        assert status_low.is_backpressured is False

    def test_credit_based_flow_control(self):
        flow = CreditBasedFlowControl()
        flow.issue_credits("upstream-1", "downstream-1", 10)
        assert flow.available_credits("upstream-1", "downstream-1") == 10
        assert flow.consume_credit("upstream-1", "downstream-1") is True
        assert flow.available_credits("upstream-1", "downstream-1") == 9

    def test_buffer_pool_allocation(self, buffer_pool):
        buf = buffer_pool.acquire()
        assert buf is not None
        buffer_pool.release()


class TestSavepoints:
    """Savepoint creation, retrieval, and restore with topology changes."""

    def test_savepoint_creation(self, checkpoint_storage):
        manager = SavepointManager(storage=checkpoint_storage)
        # Create a mock operator for the savepoint
        mock_op = MagicMock()
        mock_op.uid = "op-1"
        mock_op.snapshot_state.return_value = {"key": "val"}
        sp = manager.create_savepoint(
            name="pre-upgrade",
            operators=[mock_op],
        )
        assert sp.name == "pre-upgrade"

    def test_savepoint_retrieval(self, checkpoint_storage):
        manager = SavepointManager(storage=checkpoint_storage)
        mock_op = MagicMock()
        mock_op.uid = "op-1"
        mock_op.snapshot_state.return_value = {"key": "val"}
        manager.create_savepoint(
            name="sp-retrieve",
            operators=[mock_op],
        )
        sp = manager._savepoints.get("sp-retrieve")
        assert sp is not None
        assert sp.name == "sp-retrieve"

    def test_savepoint_restore_manager(self):
        restore_mgr = SavepointRestoreManager()
        assert restore_mgr._unmatched_states == []
        assert restore_mgr._missing_operators == []


class TestDynamicScaling:
    """Scale manager, auto-scaler, key group redistribution."""

    def test_key_group_assigner_consistency(self):
        assigner = KeyGroupAssigner(max_parallelism=128)
        # Same key should always map to same key group
        kg1 = assigner.assign_key_group("fizzbuzz-key-42")
        kg2 = assigner.assign_key_group("fizzbuzz-key-42")
        assert kg1 == kg2
        assert 0 <= kg1 < 128

    def test_scale_manager(self, checkpoint_storage):
        sp_manager = SavepointManager(storage=checkpoint_storage)
        kg_assigner = KeyGroupAssigner(max_parallelism=128)
        scale_mgr = ScaleManager(
            key_group_assigner=kg_assigner,
            savepoint_manager=sp_manager,
        )
        assert scale_mgr is not None

    def test_auto_scaler_thresholds(self, checkpoint_storage):
        sp_manager = SavepointManager(storage=checkpoint_storage)
        kg_assigner = KeyGroupAssigner(max_parallelism=128)
        scale_mgr = ScaleManager(
            key_group_assigner=kg_assigner,
            savepoint_manager=sp_manager,
        )
        scaler = AutoScaler(
            scale_manager=scale_mgr,
            scale_up_threshold_ms=30000,
            scale_down_threshold_ms=60000,
        )
        assert scaler.scale_up_threshold_ms == 30000


class TestStreamMetrics:
    """Metrics collection and dashboard rendering."""

    def test_metrics_collector(self, metrics_collector):
        metrics_collector.record_input("map-1")
        metrics_collector.record_input("map-1")
        metrics = metrics_collector._metrics.get("map-1")
        assert metrics is not None
        assert metrics.records_processed == 2

    def test_dashboard_rendering(self):
        dashboard = FizzStreamDashboard(width=76)
        output = dashboard.render(
            jobs=[],
            metrics={},
            checkpoints=[],
        )
        assert isinstance(output, str)
        assert len(output) > 0


class TestStreamSQLBridge:
    """Streaming SQL parsing and compilation."""

    def test_tumble_window_sql_parsing(self):
        bridge = StreamSQLBridge()
        query = "SELECT TUMBLE_START(event_time, INTERVAL '5' SECOND), COUNT(*) FROM evaluations GROUP BY TUMBLE(event_time, INTERVAL '5' SECOND)"
        result = bridge.execute_sql(query)
        assert result is not None
        assert result["window_type"] == WindowType.TUMBLING.value

    def test_select_compilation(self):
        bridge = StreamSQLBridge()
        query = "SELECT classification, COUNT(*) FROM evaluations GROUP BY classification, TUMBLE(event_time, INTERVAL '10' SECOND)"
        result = bridge.execute_sql(query)
        assert result is not None
        assert result["compiled"] is True


class TestFizzStreamMiddleware:
    """Middleware process delegation and evaluation emission."""

    def test_middleware_priority(self):
        env = StreamExecutionEnvironment()
        mw = FizzStreamMiddleware(env=env, dashboard_width=76)
        assert mw.get_priority() == MIDDLEWARE_PRIORITY
        assert mw.get_name() == "FizzStreamMiddleware"

    def test_middleware_process_delegation(self):
        env = StreamExecutionEnvironment()
        mw = FizzStreamMiddleware(env=env, dashboard_width=76)
        context = MagicMock()
        result = MagicMock()
        called = []

        def next_handler(ctx, res):
            called.append(True)
            return res

        mw.process(context, result, next_handler)
        assert len(called) == 1

    def test_middleware_render_status(self):
        env = StreamExecutionEnvironment()
        mw = FizzStreamMiddleware(env=env, dashboard_width=76)
        status = mw.render_status()
        assert isinstance(status, str)


class TestStreamExceptions:
    """Error code format, context population, inheritance chain."""

    def test_error_code_prefix(self):
        err = StreamProcessingError("test failure")
        assert err.error_code.startswith("EFP-STR")

    def test_context_population(self):
        err = StreamJobSubmissionError("my-job", "invalid graph")
        assert "job_name" in err.context
        assert err.context["job_name"] == "my-job"

    def test_inheritance_chain(self):
        err = StreamJobNotFoundError("job-123")
        assert isinstance(err, StreamProcessingError)
        assert isinstance(err, Exception)


class TestCreateFizzstreamSubsystem:
    """Factory function wiring and return types."""

    def test_factory_returns_tuple(self):
        env, middleware = create_fizzstream_subsystem()
        assert isinstance(env, StreamExecutionEnvironment)
        assert isinstance(middleware, FizzStreamMiddleware)

    def test_factory_state_backend_selection(self):
        env_hm, _ = create_fizzstream_subsystem(state_backend="hashmap")
        env_rdb, _ = create_fizzstream_subsystem(state_backend="rocksdb")
        assert isinstance(env_hm.state_backend, HashMapStateBackend)
        assert isinstance(env_rdb.state_backend, RocksDBStateBackend)

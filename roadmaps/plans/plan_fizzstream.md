# Implementation Plan: FizzStream -- Distributed Stream Processing Engine

**Date:** 2026-03-24
**Feature:** Idea 10 from Brainstorm Report (TeraSwarm)
**Target File:** `enterprise_fizzbuzz/infrastructure/fizzstream.py` (~3,500 lines)
**Test File:** `tests/test_fizzstream.py` (~500 lines)
**Re-export Stub:** `fizzstream.py` (root level)

---

## 1. Class Inventory

### Core Classes

| # | Class | Responsibility | Approx. Lines |
|---|-------|---------------|---------------|
| 1 | `StreamExecutionEnvironment` | Entry point for creating and executing stream processing pipelines. Configures global execution parameters (default parallelism, checkpoint interval, state backend, watermark strategy, restart strategy, buffer timeout). Provides factory methods for creating source streams. Compiles logical plans into physical execution graphs and manages active jobs | ~250 |
| 2 | `DataStream` | Fundamental abstraction representing an unbounded sequence of events. Defines a DAG of operators via fluent method chaining (filter, map, flat_map, key_by, window, union, process, sink_to). Does not hold data -- represents a logical plan | ~200 |
| 3 | `KeyedStream` | Specialized DataStream partitioned by a key extractor function. Enables key-scoped stateful processing, windowing, and reduction. Returned by `DataStream.key_by()` | ~80 |
| 4 | `StreamOperator` | Abstract base class for all operators. Defines lifecycle: `open()`, `process_element()`, `process_watermark()`, `snapshot_state()`, `restore_state()`, `close()`. Declares parallelism, chain strategy, and stable UID | ~100 |
| 5 | `MapOperator` | Applies `f: T -> R` to each element. Stateless. Chainable | ~40 |
| 6 | `FlatMapOperator` | Applies `f: T -> Iterable[R]` to each element. Zero or more outputs per input | ~40 |
| 7 | `FilterOperator` | Forwards elements where predicate returns True. Stateless | ~35 |
| 8 | `KeyByOperator` | Partitions stream by key extractor using murmur3 consistent hashing. Returns KeyedStream | ~60 |
| 9 | `ReduceOperator` | Binary reduction maintaining running aggregate per key in keyed state | ~60 |
| 10 | `ProcessOperator` | General-purpose operator with access to keyed state, timers, side outputs, watermark info. Supports `process_element()` and `on_timer()` callbacks | ~120 |
| 11 | `UnionOperator` | Merges two or more streams of the same type without deduplication or ordering | ~40 |
| 12 | `MessageQueueSource` | Reads from message queue topic partitions via ConsumerGroup. Tracks committed offsets per partition. Emits watermarks from message timestamps. Reports offsets during checkpointing | ~120 |
| 13 | `EventStoreSource` | Tails the EventStore journal as a continuous stream. Configurable start position. Emits watermarks from event timestamps. Records last consumed sequence number for checkpointing | ~100 |
| 14 | `ContainerEventSource` | Reads container lifecycle events from FizzContainerd's event service | ~60 |
| 15 | `MetricSource` | Reads metric emissions from OpenTelemetry collector as a continuous stream | ~60 |
| 16 | `GeneratorSource` | Synthetic source generating events from a user-defined function. Supports bounded and unbounded modes | ~60 |
| 17 | `MessageQueueSink` | Writes stream results to message queue topic partitions via Producer. Uses idempotency layer for exactly-once production | ~80 |
| 18 | `EventStoreSink` | Appends computed stream results as domain events via EventStore.append() | ~60 |
| 19 | `TumblingEventTimeWindow` | Fixed-size, non-overlapping windows aligned to event time. Parameters: size_ms, offset_ms | ~50 |
| 20 | `SlidingEventTimeWindow` | Fixed-size overlapping windows with configurable slide interval. Parameters: size_ms, slide_ms | ~60 |
| 21 | `SessionWindow` | Dynamically-sized windows defined by gaps in activity. Keyed. Parameters: gap_ms | ~70 |
| 22 | `GlobalWindow` | Single window containing all elements. Requires custom Trigger | ~30 |
| 23 | `WindowAssigner` | Assigns each element to zero or more windows based on timestamp and window definition | ~60 |
| 24 | `EventTimeTrigger` | Fires when watermark passes window end timestamp | ~35 |
| 25 | `ProcessingTimeTrigger` | Fires at wall-clock time equal to window end | ~35 |
| 26 | `CountTrigger` | Fires when window contains specified number of elements | ~35 |
| 27 | `PurgingTrigger` | Wraps another trigger, clears window contents after firing | ~30 |
| 28 | `ContinuousEventTimeTrigger` | Fires periodically within a window for early results | ~40 |
| 29 | `ReduceFunction` | Incrementally reduces elements as they arrive. Memory-efficient | ~25 |
| 30 | `AggregateFunction` | Generalizes ReduceFunction with accumulator, add, merge, extract phases | ~35 |
| 31 | `ProcessWindowFunction` | Receives all buffered elements when window fires. Access to window metadata | ~40 |
| 32 | `Watermark` | Special stream element declaring event-time completeness threshold | ~25 |
| 33 | `BoundedOutOfOrdernessStrategy` | Watermark = max_timestamp - max_out_of_orderness. Configurable tolerance | ~40 |
| 34 | `MonotonousTimestampsStrategy` | Watermark = max_timestamp - 1. Zero out-of-order tolerance | ~30 |
| 35 | `PunctuatedWatermarkStrategy` | Extracts watermarks from punctuation events in the stream | ~35 |
| 36 | `IdleSourceDetection` | Advances watermark for idle partitions to prevent stalling | ~40 |
| 37 | `WatermarkAlignment` | Computes effective watermark as minimum across multi-input operators | ~40 |
| 38 | `CheckpointCoordinator` | Orchestrates periodic Chandy-Lamport snapshots. Injects barriers, collects acknowledgments, records metadata, coordinates recovery | ~200 |
| 39 | `CheckpointBarrier` | Special stream element for checkpoint synchronization. Supports aligned and unaligned modes | ~30 |
| 40 | `InMemoryCheckpointStorage` | Stores checkpoints in Python dictionary. Fast but not durable | ~40 |
| 41 | `FileSystemCheckpointStorage` | Stores checkpoints to FizzVFS. Durable. Configurable retention | ~60 |
| 42 | `FixedDelayRestartStrategy` | Restarts with fixed delay between attempts. Parameters: max_restarts, delay_ms | ~35 |
| 43 | `ExponentialBackoffRestartStrategy` | Restarts with exponentially increasing delays. Parameters: initial_delay_ms, max_delay_ms, backoff_multiplier, max_restarts | ~45 |
| 44 | `NoRestartStrategy` | Fail immediately without restart | ~15 |
| 45 | `ValueState` | Single value per key. Methods: value(), update(), clear() | ~35 |
| 46 | `ListState` | Ordered list per key. Methods: get(), add(), add_all(), update(), clear() | ~45 |
| 47 | `MapState` | Key-value map per key. Methods: get(), put(), contains(), remove(), keys(), values(), entries(), clear() | ~55 |
| 48 | `ReducingState` | Single value per key with incremental reduce. Methods: get(), add(), clear() | ~35 |
| 49 | `AggregatingState` | Accumulator per key with separate input/accumulator/output types. Methods: get(), add(), clear() | ~40 |
| 50 | `HashMapStateBackend` | In-memory keyed state stored in Python dict. O(1) lookup. Serialized via pickle during checkpointing | ~80 |
| 51 | `RocksDBStateBackend` | LSM-tree keyed state with sorted dict, write-ahead log, level-based compaction, write buffer, and block cache. O(log N) reads. Configurable parameters | ~150 |
| 52 | `StateTTL` | Time-to-live for keyed state entries. Lazy cleanup on access, proactive during compaction. Configurable update_type and cleanup_strategy | ~50 |
| 53 | `StreamStreamJoin` | Joins two keyed streams within time-bounded window. Supports inner, left outer, right outer, full outer. Maintains buffer state for both streams | ~120 |
| 54 | `StreamTableJoin` | Joins stream against slowly-changing lookup table materialized from upsert events. Temporal join at event time | ~100 |
| 55 | `IntervalJoin` | Specialized asymmetric time-bounded join. Efficient targeted scan | ~80 |
| 56 | `Pattern` | Declarative specification of event sequences. Fluent API: begin(), where(), followed_by(), followed_by_any(), not_followed_by(), within() | ~80 |
| 57 | `PatternElement` | Single stage in a pattern with name, condition, and quantifier (times, times_or_more, optional, one_or_more) | ~50 |
| 58 | `NFACompiler` | Compiles Pattern into NFA for efficient matching. Handles quantifiers, contiguity modes, negation | ~100 |
| 59 | `CEPOperator` | Stateful operator running compiled NFA against event stream. Maintains partial match state. Completes/times out matches | ~100 |
| 60 | `PatternStream` | Result of applying Pattern to DataStream. Methods: select(), select_timed_out() | ~40 |
| 61 | `BackpressureController` | Monitors operator input buffer occupancy. Signals upstream on high/low watermarks | ~50 |
| 62 | `CreditBasedFlowControl` | Credit-based flow control between operators. Downstream issues credits, upstream respects limits | ~50 |
| 63 | `BufferPool` | Fixed-size pool of network buffers for inter-operator communication. Lock-free ring buffer | ~50 |
| 64 | `SavepointManager` | Creates named, persistent checkpoints for version upgrades. Stores manifest with operator state locations | ~60 |
| 65 | `SavepointRestoreManager` | Restores pipeline from savepoint. Handles topology changes: new/removed/repartitioned operators. Reports unmatched and missing state | ~70 |
| 66 | `ScaleManager` | Adjusts operator parallelism at runtime via savepoint-based coordination. Redistributes keyed state | ~60 |
| 67 | `AutoScaler` | Monitors throughput and backpressure to auto-adjust parallelism. Configurable thresholds and cooldown | ~60 |
| 68 | `KeyGroupAssigner` | Maps keys to key groups (unit of state redistribution), key groups to operator instances. Two-level consistent hashing | ~50 |
| 69 | `StreamMetricsCollector` | Collects per-operator metrics: input/output rate, latency percentiles, backpressure time, buffer utilization, checkpoint duration, state size, watermark lag | ~80 |
| 70 | `FizzStreamDashboard` | ASCII dashboard: operator topology graph, throughput/latency, watermark positions, checkpoint history, backpressure indicators, active jobs | ~100 |
| 71 | `StreamSQLBridge` | Extends FizzSQLEngine with streaming SQL: TUMBLE/HOP/SESSION window functions, EMIT AFTER WATERMARK, continuous SELECT, streaming joins. Compiles SQL to DataStream operator graphs | ~100 |
| 72 | `FizzStreamMiddleware` | IMiddleware at priority 38. Emits evaluation results to fizzbuzz.stream.evaluations topic. Annotates context with real-time aggregates | ~80 |
| 73 | `StreamJob` | Runtime representation of a submitted job: job_id, name, status, operator graph, metrics, savepoint history, start time | ~50 |
| 74 | `ProcessContext` | Context object passed to ProcessOperator. Methods: get_state(), register_event_time_timer(), register_processing_time_timer(), output(), current_watermark() | ~50 |
| 75 | `AllowedLateness` | Grace period configuration for late elements after window close. Parameters: lateness_ms | ~25 |

---

## 2. Enums

All enums defined within `fizzstream.py`, following the codebase pattern (string values for serialization).

```python
class StreamJobStatus(Enum):
    """Execution status of a stream processing job."""
    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    CHECKPOINTING = "checkpointing"
    FAILING = "failing"
    RESTARTING = "restarting"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FINISHED = "finished"
    FAILED = "failed"
    SUSPENDED = "suspended"


class OperatorChainStrategy(Enum):
    """Strategy for chaining adjacent operators to reduce serialization."""
    ALWAYS = "always"
    NEVER = "never"
    HEAD = "head"
    DEFAULT = "default"


class WindowType(Enum):
    """Type of window for bounded computation."""
    TUMBLING = "tumbling"
    SLIDING = "sliding"
    SESSION = "session"
    GLOBAL = "global"


class TimeCharacteristic(Enum):
    """Time semantics for stream processing."""
    EVENT_TIME = "event_time"
    PROCESSING_TIME = "processing_time"
    INGESTION_TIME = "ingestion_time"


class TriggerResult(Enum):
    """Result of a trigger evaluation."""
    CONTINUE = "continue"
    FIRE = "fire"
    PURGE = "purge"
    FIRE_AND_PURGE = "fire_and_purge"


class CheckpointStatus(Enum):
    """Status of a checkpoint operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class StateBackendType(Enum):
    """Type of state backend for keyed state storage."""
    HASHMAP = "hashmap"
    ROCKSDB = "rocksdb"


class RestartStrategyType(Enum):
    """Type of restart strategy for failure recovery."""
    FIXED_DELAY = "fixed"
    EXPONENTIAL_BACKOFF = "exponential"
    NO_RESTART = "none"


class JoinType(Enum):
    """Type of stream join."""
    INNER = "inner"
    LEFT_OUTER = "left_outer"
    RIGHT_OUTER = "right_outer"
    FULL_OUTER = "full_outer"


class Contiguity(Enum):
    """Contiguity mode for CEP pattern sequences."""
    STRICT = "strict"
    RELAXED = "relaxed"
    NON_DETERMINISTIC_RELAXED = "non_deterministic_relaxed"


class SourceStartPosition(Enum):
    """Start position for source operators."""
    EARLIEST = "earliest"
    LATEST = "latest"
    SPECIFIC = "specific"


class WatermarkStrategyType(Enum):
    """Type of watermark generation strategy."""
    BOUNDED_OUT_OF_ORDERNESS = "bounded_out_of_orderness"
    MONOTONOUS = "monotonous"
    PUNCTUATED = "punctuated"


class NFAStateType(Enum):
    """State type in the NFA for CEP pattern matching."""
    START = "start"
    NORMAL = "normal"
    FINAL = "final"
    STOP = "stop"


class ScaleDirection(Enum):
    """Direction of a scaling operation."""
    UP = "up"
    DOWN = "down"
```

---

## 3. Data Classes

All dataclasses defined within `fizzstream.py`.

```python
@dataclass
class StreamElement:
    """A single element in a data stream.

    Attributes:
        value: The element's payload.
        timestamp: Event time in milliseconds since epoch.
        key: Partition key (set after KeyBy).
    """
    value: Any
    timestamp: int = 0
    key: Optional[Any] = None


@dataclass
class StreamRecord:
    """Internal record wrapping a stream element with processing metadata.

    Attributes:
        element: The stream element.
        operator_id: ID of the operator that produced this record.
        key_group: Key group assignment for state partitioning.
        is_watermark: Whether this record is a watermark event.
        is_barrier: Whether this record is a checkpoint barrier.
        watermark_timestamp: Watermark timestamp if is_watermark.
        barrier_id: Checkpoint ID if is_barrier.
    """
    element: Optional[StreamElement] = None
    operator_id: str = ""
    key_group: int = -1
    is_watermark: bool = False
    is_barrier: bool = False
    watermark_timestamp: int = -1
    barrier_id: int = -1


@dataclass
class OperatorDescriptor:
    """Descriptor for a stream operator in the execution graph.

    Attributes:
        uid: Stable identifier for state recovery across topology changes.
        name: Human-readable operator name.
        operator_type: Class name of the operator.
        parallelism: Number of concurrent instances.
        chain_strategy: Operator chaining strategy.
        input_operators: List of upstream operator UIDs.
        output_operators: List of downstream operator UIDs.
    """
    uid: str
    name: str
    operator_type: str
    parallelism: int = 1
    chain_strategy: OperatorChainStrategy = OperatorChainStrategy.DEFAULT
    input_operators: List[str] = field(default_factory=list)
    output_operators: List[str] = field(default_factory=list)


@dataclass
class WindowSpec:
    """Specification for a window instance.

    Attributes:
        start: Window start timestamp in milliseconds.
        end: Window end timestamp in milliseconds.
        max_timestamp: Last event timestamp that belongs to this window.
        window_type: Type of window.
    """
    start: int
    end: int
    max_timestamp: int = 0
    window_type: WindowType = WindowType.TUMBLING


@dataclass
class CheckpointMetadata:
    """Metadata for a completed checkpoint.

    Attributes:
        checkpoint_id: Unique checkpoint identifier.
        timestamp: When the checkpoint was initiated.
        duration_ms: Time taken to complete the checkpoint.
        operator_states: Map of operator UID to state storage location.
        source_positions: Map of source UID to committed positions.
        state_size_bytes: Total size of checkpointed state.
        status: Checkpoint completion status.
    """
    checkpoint_id: int
    timestamp: float = 0.0
    duration_ms: float = 0.0
    operator_states: Dict[str, str] = field(default_factory=dict)
    source_positions: Dict[str, Any] = field(default_factory=dict)
    state_size_bytes: int = 0
    status: CheckpointStatus = CheckpointStatus.PENDING


@dataclass
class SavepointMetadata:
    """Metadata for a named savepoint.

    Attributes:
        name: User-provided savepoint name.
        checkpoint_id: Underlying checkpoint ID.
        timestamp: When the savepoint was created.
        operator_states: Map of operator UID to state storage location.
        source_positions: Map of source UID to committed positions.
        topology_hash: Hash of the operator topology at savepoint time.
    """
    name: str
    checkpoint_id: int = 0
    timestamp: float = 0.0
    operator_states: Dict[str, str] = field(default_factory=dict)
    source_positions: Dict[str, Any] = field(default_factory=dict)
    topology_hash: str = ""


@dataclass
class OperatorMetrics:
    """Runtime metrics for a single operator instance.

    Attributes:
        operator_uid: Operator identifier.
        input_rate: Events per second ingested.
        output_rate: Events per second emitted.
        latency_p50_ms: 50th percentile processing latency.
        latency_p95_ms: 95th percentile processing latency.
        latency_p99_ms: 99th percentile processing latency.
        backpressure_pct: Percentage of time backpressured.
        buffer_utilization_pct: Input buffer utilization percentage.
        state_size_bytes: Current keyed state size.
        watermark_lag_ms: Difference between processing time and event time.
        records_processed: Total records processed since start.
    """
    operator_uid: str = ""
    input_rate: float = 0.0
    output_rate: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    backpressure_pct: float = 0.0
    buffer_utilization_pct: float = 0.0
    state_size_bytes: int = 0
    watermark_lag_ms: float = 0.0
    records_processed: int = 0


@dataclass
class JobDescriptor:
    """Runtime descriptor for a stream processing job.

    Attributes:
        job_id: Unique job identifier.
        name: User-provided job name.
        status: Current execution status.
        operators: List of operator descriptors in the execution graph.
        start_time: When the job was submitted.
        end_time: When the job finished (if applicable).
        checkpoint_interval_ms: Configured checkpoint interval.
        restart_strategy: Configured restart strategy type.
        state_backend: Configured state backend type.
        parallelism: Default parallelism.
        max_parallelism: Maximum parallelism / key group count.
        metrics: Per-operator metrics.
        checkpoints: List of checkpoint metadata.
        savepoints: List of savepoint metadata.
        restart_count: Number of times the job has been restarted.
    """
    job_id: str = ""
    name: str = ""
    status: StreamJobStatus = StreamJobStatus.CREATED
    operators: List[OperatorDescriptor] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    checkpoint_interval_ms: int = 60000
    restart_strategy: RestartStrategyType = RestartStrategyType.FIXED_DELAY
    state_backend: StateBackendType = StateBackendType.HASHMAP
    parallelism: int = 4
    max_parallelism: int = 128
    metrics: Dict[str, OperatorMetrics] = field(default_factory=dict)
    checkpoints: List[CheckpointMetadata] = field(default_factory=list)
    savepoints: List[SavepointMetadata] = field(default_factory=list)
    restart_count: int = 0


@dataclass
class NFAState:
    """State in the nondeterministic finite automaton for CEP.

    Attributes:
        name: State name (matches pattern element name).
        state_type: Type of NFA state.
        condition: Predicate guarding transitions from this state.
        transitions: Map of target state name to transition conditions.
        self_loop: Whether this state has a self-loop (for quantifiers).
    """
    name: str
    state_type: NFAStateType = NFAStateType.NORMAL
    condition: Optional[Callable] = None
    transitions: Dict[str, Optional[Callable]] = field(default_factory=dict)
    self_loop: bool = False


@dataclass
class PartialMatch:
    """A partial match in the CEP NFA execution.

    Attributes:
        current_state: Current NFA state name.
        matched_events: Map of pattern element name to matched events.
        start_timestamp: Timestamp of the first matched event.
        version: Match version for branching on non-deterministic transitions.
    """
    current_state: str = ""
    matched_events: Dict[str, List[Any]] = field(default_factory=dict)
    start_timestamp: int = 0
    version: int = 0


@dataclass
class BackpressureStatus:
    """Backpressure status for an operator.

    Attributes:
        operator_uid: Operator identifier.
        is_backpressured: Whether the operator is currently backpressured.
        buffer_occupancy_pct: Current input buffer occupancy percentage.
        credits_available: Available credits from downstream.
        time_backpressured_ms: Total time spent backpressured.
    """
    operator_uid: str = ""
    is_backpressured: bool = False
    buffer_occupancy_pct: float = 0.0
    credits_available: int = 0
    time_backpressured_ms: float = 0.0


@dataclass
class ScaleEvent:
    """Record of a scaling operation.

    Attributes:
        operator_uid: Operator that was scaled.
        direction: Scale direction (up or down).
        old_parallelism: Previous parallelism.
        new_parallelism: New parallelism.
        key_groups_migrated: Number of key groups moved.
        duration_ms: Time taken for the scaling operation.
        timestamp: When the scaling occurred.
    """
    operator_uid: str = ""
    direction: ScaleDirection = ScaleDirection.UP
    old_parallelism: int = 0
    new_parallelism: int = 0
    key_groups_migrated: int = 0
    duration_ms: float = 0.0
    timestamp: float = 0.0


@dataclass
class StreamTopicConfig:
    """Configuration for a default streaming topic.

    Attributes:
        name: Topic name.
        partitions: Number of partitions.
        replication_factor: Replication factor.
        retention_ms: Message retention in milliseconds.
        description: Human-readable topic description.
    """
    name: str
    partitions: int = 4
    replication_factor: int = 1
    retention_ms: int = 86400000  # 24 hours
    description: str = ""
```

---

## 4. Constants

```python
FIZZSTREAM_VERSION = "1.0.0"
"""FizzStream engine version."""

DEFAULT_PARALLELISM = 4
"""Default operator parallelism."""

DEFAULT_MAX_PARALLELISM = 128
"""Default maximum parallelism / key group count."""

DEFAULT_CHECKPOINT_INTERVAL_MS = 60000
"""Default checkpoint interval in milliseconds."""

DEFAULT_WATERMARK_INTERVAL_MS = 200
"""Default watermark emission interval in milliseconds."""

DEFAULT_BUFFER_TIMEOUT_MS = 100
"""Default buffer flush timeout in milliseconds."""

DEFAULT_BUFFER_SIZE = 1024
"""Default size of a network buffer in elements."""

DEFAULT_BUFFER_POOL_SIZE = 64
"""Default number of buffers in the buffer pool."""

DEFAULT_HIGH_WATERMARK_PCT = 0.80
"""Default backpressure high watermark threshold."""

DEFAULT_LOW_WATERMARK_PCT = 0.50
"""Default backpressure low watermark threshold."""

DEFAULT_CHECKPOINT_RETENTION = 3
"""Default number of checkpoints to retain."""

DEFAULT_RESTART_ATTEMPTS = 3
"""Default maximum restart attempts for fixed-delay strategy."""

DEFAULT_RESTART_DELAY_MS = 10000
"""Default delay between restart attempts in milliseconds."""

DEFAULT_BACKOFF_INITIAL_MS = 1000
"""Default initial delay for exponential backoff restart."""

DEFAULT_BACKOFF_MAX_MS = 60000
"""Default maximum delay for exponential backoff restart."""

DEFAULT_BACKOFF_MULTIPLIER = 2.0
"""Default backoff multiplier."""

DEFAULT_SCALE_UP_THRESHOLD_MS = 30000
"""Default backpressure duration before auto-scaling up."""

DEFAULT_SCALE_DOWN_THRESHOLD_MS = 60000
"""Default idle duration before auto-scaling down."""

DEFAULT_SCALE_COOLDOWN_MS = 120000
"""Default minimum duration between scaling operations."""

DEFAULT_DASHBOARD_WIDTH = 76
"""Default ASCII dashboard width."""

DEFAULT_DASHBOARD_REFRESH_MS = 5000
"""Default dashboard refresh interval in milliseconds."""

MIDDLEWARE_PRIORITY = 38
"""Middleware pipeline priority for FizzStream (after caching, before MapReduce)."""

MURMUR3_SEED = 0x9747B28C
"""Seed for murmur3 consistent hashing in key partitioning."""

KEY_GROUP_COUNT = 128
"""Default number of key groups for state redistribution."""

STREAM_TOPIC_EVALUATIONS = "fizzbuzz.stream.evaluations"
"""Default topic for real-time evaluation results."""

STREAM_TOPIC_METRICS = "fizzbuzz.stream.metrics"
"""Default topic for continuous metric emissions."""

STREAM_TOPIC_ALERTS = "fizzbuzz.stream.alerts"
"""Default topic for threshold violations and anomalies."""

STREAM_TOPIC_AUDIT = "fizzbuzz.stream.audit"
"""Default topic for compliance-relevant events."""

STREAM_TOPIC_LIFECYCLE = "fizzbuzz.stream.lifecycle"
"""Default topic for container and service lifecycle events."""
```

---

## 5. Exception Classes (~25, EFP-STR prefix)

File: `enterprise_fizzbuzz/domain/exceptions/fizzstream.py`

```python
class StreamProcessingError(FizzBuzzError):
    """Base exception for all FizzStream distributed stream processing errors.

    FizzStream provides continuous computation over unbounded event
    sequences with exactly-once guarantees, event-time semantics,
    windowed aggregation, stateful processing, and fault-tolerant
    checkpointing.  All stream-processing-specific failures inherit
    from this class to enable categorical error handling in the
    middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-STR00"
        self.context = {"reason": reason}


class StreamJobSubmissionError(StreamProcessingError):
    """Raised when a stream processing job cannot be submitted.

    The StreamExecutionEnvironment rejected the job submission.
    Possible causes include an invalid operator graph (cycles,
    disconnected components), conflicting operator UIDs, or
    resource constraints preventing job initialization.
    """

    def __init__(self, job_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to submit stream job '{job_name}': {reason}. "
            f"The job's operator graph could not be compiled into a "
            f"physical execution plan."
        )
        self.error_code = "EFP-STR01"
        self.context = {"job_name": job_name, "reason": reason}


class StreamJobNotFoundError(StreamProcessingError):
    """Raised when a referenced stream job does not exist.

    A management operation (cancel, savepoint, scale, metrics)
    targeted a job ID that is not registered in the execution
    environment.  The job may have been completed, cancelled,
    or never submitted.
    """

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"Stream job '{job_id}' not found in the execution "
            f"environment. The job may have completed, been cancelled, "
            f"or was never submitted."
        )
        self.error_code = "EFP-STR02"
        self.context = {"job_id": job_id}


class StreamSourceError(StreamProcessingError):
    """Raised when a source operator fails to read from its external system.

    The source operator encountered an error while ingesting events
    from the upstream data source.  Possible causes include
    connectivity failures, deserialization errors, or partition
    assignment failures.
    """

    def __init__(self, source_name: str, reason: str) -> None:
        super().__init__(
            f"Source operator '{source_name}' failed: {reason}. "
            f"Event ingestion from the external system has been "
            f"interrupted."
        )
        self.error_code = "EFP-STR03"
        self.context = {"source_name": source_name, "reason": reason}


class StreamSinkError(StreamProcessingError):
    """Raised when a sink operator fails to write to its downstream system.

    The sink operator encountered an error while writing computed
    results to the downstream data store.  Possible causes include
    connectivity failures, serialization errors, or exactly-once
    idempotency violations.
    """

    def __init__(self, sink_name: str, reason: str) -> None:
        super().__init__(
            f"Sink operator '{sink_name}' failed: {reason}. "
            f"Result delivery to the downstream system has been "
            f"interrupted."
        )
        self.error_code = "EFP-STR04"
        self.context = {"sink_name": sink_name, "reason": reason}


class StreamOperatorError(StreamProcessingError):
    """Raised when a transformation operator encounters a processing error.

    A user-defined function (map, filter, flat_map, reduce, process)
    threw an exception during element processing.  The operator's
    state may be inconsistent and the job may require a restart
    from the latest checkpoint.
    """

    def __init__(self, operator_uid: str, reason: str) -> None:
        super().__init__(
            f"Operator '{operator_uid}' failed during element "
            f"processing: {reason}. The operator's state may be "
            f"inconsistent."
        )
        self.error_code = "EFP-STR05"
        self.context = {"operator_uid": operator_uid, "reason": reason}


class CheckpointError(StreamProcessingError):
    """Raised when a checkpoint operation fails.

    The CheckpointCoordinator could not complete a distributed
    snapshot.  Possible causes include operator state serialization
    failures, barrier alignment timeouts, or storage backend errors.
    The job's fault tolerance is degraded until the next successful
    checkpoint.
    """

    def __init__(self, checkpoint_id: int, reason: str) -> None:
        super().__init__(
            f"Checkpoint {checkpoint_id} failed: {reason}. "
            f"The job's fault tolerance is degraded until the next "
            f"successful checkpoint."
        )
        self.error_code = "EFP-STR06"
        self.context = {"checkpoint_id": checkpoint_id, "reason": reason}


class CheckpointRestoreError(StreamProcessingError):
    """Raised when restoring from a checkpoint fails.

    The job could not be restored to a previous checkpoint.
    Possible causes include missing checkpoint data, incompatible
    state serialization formats, or operator topology changes
    that prevent state mapping.
    """

    def __init__(self, checkpoint_id: int, reason: str) -> None:
        super().__init__(
            f"Failed to restore from checkpoint {checkpoint_id}: "
            f"{reason}. The job cannot recover from this failure."
        )
        self.error_code = "EFP-STR07"
        self.context = {"checkpoint_id": checkpoint_id, "reason": reason}


class SavepointError(StreamProcessingError):
    """Raised when a savepoint operation fails.

    The SavepointManager could not create or retrieve a named
    savepoint.  Possible causes include storage failures, concurrent
    savepoint operations, or an invalid job state for snapshotting.
    """

    def __init__(self, savepoint_name: str, reason: str) -> None:
        super().__init__(
            f"Savepoint '{savepoint_name}' failed: {reason}. "
            f"The named snapshot could not be created or retrieved."
        )
        self.error_code = "EFP-STR08"
        self.context = {"savepoint_name": savepoint_name, "reason": reason}


class SavepointRestoreError(StreamProcessingError):
    """Raised when restoring from a savepoint fails.

    The SavepointRestoreManager could not map savepoint state to
    the current pipeline topology.  Possible causes include missing
    operator UIDs, incompatible state schemas, or key group
    redistribution failures.
    """

    def __init__(self, savepoint_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to restore from savepoint '{savepoint_name}': "
            f"{reason}. The pipeline topology may have changed "
            f"incompatibly since the savepoint was created."
        )
        self.error_code = "EFP-STR09"
        self.context = {"savepoint_name": savepoint_name, "reason": reason}


class WatermarkViolationError(StreamProcessingError):
    """Raised when a watermark invariant is violated.

    Watermarks must be monotonically non-decreasing.  A source or
    operator attempted to emit a watermark with a timestamp lower
    than the previously emitted watermark, which would violate
    event-time progress guarantees and corrupt window computations.
    """

    def __init__(self, operator_uid: str, current_wm: int, new_wm: int) -> None:
        super().__init__(
            f"Watermark regression detected in operator "
            f"'{operator_uid}': current watermark {current_wm} > "
            f"new watermark {new_wm}. Watermarks must be "
            f"monotonically non-decreasing."
        )
        self.error_code = "EFP-STR10"
        self.context = {
            "operator_uid": operator_uid,
            "current_watermark": current_wm,
            "new_watermark": new_wm,
        }


class WindowError(StreamProcessingError):
    """Raised when a windowing operation encounters an error.

    The window assigner, trigger, or window function failed during
    window evaluation.  Possible causes include invalid window
    boundaries, trigger state corruption, or window function
    exceptions.
    """

    def __init__(self, window_type: str, reason: str) -> None:
        super().__init__(
            f"Window error in {window_type} window: {reason}. "
            f"The window evaluation could not be completed."
        )
        self.error_code = "EFP-STR11"
        self.context = {"window_type": window_type, "reason": reason}


class StateAccessError(StreamProcessingError):
    """Raised when accessing keyed state fails.

    The state backend could not read or write keyed state for an
    operator.  Possible causes include serialization failures,
    state backend corruption, or accessing state outside of a
    keyed context.
    """

    def __init__(self, state_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to access state '{state_name}': {reason}. "
            f"The state backend could not complete the requested "
            f"operation."
        )
        self.error_code = "EFP-STR12"
        self.context = {"state_name": state_name, "reason": reason}


class StateBackendError(StreamProcessingError):
    """Raised when the state backend encounters an internal error.

    The underlying storage layer (HashMap or RocksDB) failed during
    a state operation.  For RocksDB, possible causes include write
    buffer exhaustion, compaction failures, or WAL corruption.
    """

    def __init__(self, backend_type: str, reason: str) -> None:
        super().__init__(
            f"State backend '{backend_type}' error: {reason}. "
            f"The storage layer could not complete the operation."
        )
        self.error_code = "EFP-STR13"
        self.context = {"backend_type": backend_type, "reason": reason}


class KeyGroupAssignmentError(StreamProcessingError):
    """Raised when key group assignment or redistribution fails.

    The KeyGroupAssigner could not map a key to a key group or
    redistribute key groups during a scaling operation.  Possible
    causes include an invalid max_parallelism configuration or
    hash collision overflow.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Key group assignment failed: {reason}. State "
            f"partitioning cannot proceed without a valid key "
            f"group mapping."
        )
        self.error_code = "EFP-STR14"
        self.context = {"reason": reason}


class StreamJoinError(StreamProcessingError):
    """Raised when a stream join operation fails.

    A stream-stream, stream-table, or interval join encountered
    an error.  Possible causes include mismatched key types,
    buffer exhaustion, or temporal constraint violations.
    """

    def __init__(self, join_type: str, reason: str) -> None:
        super().__init__(
            f"Stream join ({join_type}) failed: {reason}. "
            f"The join operation could not correlate events "
            f"across streams."
        )
        self.error_code = "EFP-STR15"
        self.context = {"join_type": join_type, "reason": reason}


class CEPPatternError(StreamProcessingError):
    """Raised when a CEP pattern definition is invalid.

    The pattern specification contains structural errors that
    prevent NFA compilation.  Possible causes include empty
    patterns, duplicate element names, or contradictory
    contiguity constraints.
    """

    def __init__(self, pattern_name: str, reason: str) -> None:
        super().__init__(
            f"Invalid CEP pattern '{pattern_name}': {reason}. "
            f"The pattern cannot be compiled into an NFA."
        )
        self.error_code = "EFP-STR16"
        self.context = {"pattern_name": pattern_name, "reason": reason}


class CEPMatchError(StreamProcessingError):
    """Raised when the CEP operator encounters a matching error.

    The NFA execution encountered an internal error during
    partial match advancement.  Possible causes include state
    corruption, unexpected NFA transitions, or resource
    exhaustion from excessive partial matches.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"CEP match error: {reason}. The NFA execution "
            f"could not advance partial matches."
        )
        self.error_code = "EFP-STR17"
        self.context = {"reason": reason}


class BackpressureError(StreamProcessingError):
    """Raised when the backpressure system encounters a critical failure.

    The backpressure controller or credit-based flow control
    detected an unrecoverable condition.  Possible causes include
    buffer pool exhaustion with all operators blocked, creating
    a deadlock.
    """

    def __init__(self, operator_uid: str, reason: str) -> None:
        super().__init__(
            f"Backpressure error at operator '{operator_uid}': "
            f"{reason}. Flow control could not regulate the "
            f"pipeline throughput."
        )
        self.error_code = "EFP-STR18"
        self.context = {"operator_uid": operator_uid, "reason": reason}


class ScaleError(StreamProcessingError):
    """Raised when a dynamic scaling operation fails.

    The ScaleManager could not adjust operator parallelism.
    Possible causes include savepoint creation failure during
    the scaling coordination, state redistribution errors, or
    violation of min/max parallelism bounds.
    """

    def __init__(self, operator_uid: str, reason: str) -> None:
        super().__init__(
            f"Failed to scale operator '{operator_uid}': {reason}. "
            f"Parallelism adjustment could not be completed."
        )
        self.error_code = "EFP-STR19"
        self.context = {"operator_uid": operator_uid, "reason": reason}


class StreamSQLError(StreamProcessingError):
    """Raised when a streaming SQL query cannot be compiled or executed.

    The StreamSQLBridge encountered an error while parsing a
    streaming SQL query, compiling it into a DataStream operator
    graph, or executing the compiled graph.  Possible causes
    include unsupported SQL constructs, invalid window function
    parameters, or stream reference resolution failures.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"Streaming SQL error: {reason}. The query could not "
            f"be compiled into a DataStream execution plan."
        )
        self.error_code = "EFP-STR20"
        self.context = {"query": query[:200], "reason": reason}


class RestartExhaustedError(StreamProcessingError):
    """Raised when a job has exhausted all restart attempts.

    The configured restart strategy has reached its maximum
    number of restart attempts.  The job transitions to FAILED
    status and no further automatic recovery will be attempted.
    Manual intervention is required.
    """

    def __init__(self, job_id: str, max_restarts: int) -> None:
        super().__init__(
            f"Job '{job_id}' exhausted all {max_restarts} restart "
            f"attempts. No further automatic recovery will be "
            f"attempted. Manual intervention is required."
        )
        self.error_code = "EFP-STR21"
        self.context = {"job_id": job_id, "max_restarts": max_restarts}


class BarrierAlignmentTimeoutError(StreamProcessingError):
    """Raised when checkpoint barrier alignment times out.

    An operator with multiple inputs did not receive barriers
    from all inputs within the configured timeout.  The checkpoint
    is aborted.  This typically indicates severe backpressure or
    a failed upstream operator.
    """

    def __init__(self, operator_uid: str, timeout_ms: int) -> None:
        super().__init__(
            f"Barrier alignment timeout at operator "
            f"'{operator_uid}' after {timeout_ms}ms. Not all "
            f"inputs delivered their checkpoint barriers within "
            f"the configured timeout."
        )
        self.error_code = "EFP-STR22"
        self.context = {"operator_uid": operator_uid, "timeout_ms": timeout_ms}


class StreamMiddlewareError(StreamProcessingError):
    """Raised when the FizzStream middleware encounters an error during evaluation.

    The middleware attempted to emit evaluation results to the
    stream processing pipeline or query real-time aggregates, but
    the operation failed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzStream middleware error: {reason}. The stream "
            f"processing pipeline could not be reached during "
            f"evaluation."
        )
        self.error_code = "EFP-STR23"
        self.context = {"reason": reason}


class StateTTLError(StreamProcessingError):
    """Raised when state TTL configuration or cleanup encounters an error.

    The StateTTL subsystem could not enforce time-to-live semantics
    on keyed state entries.  Possible causes include invalid TTL
    configuration, cleanup strategy incompatibility with the
    selected state backend, or timestamp resolution failures.
    """

    def __init__(self, state_name: str, reason: str) -> None:
        super().__init__(
            f"State TTL error for '{state_name}': {reason}. "
            f"Time-to-live enforcement could not be applied."
        )
        self.error_code = "EFP-STR24"
        self.context = {"state_name": state_name, "reason": reason}
```

---

## 6. EventType Entries (~25 entries)

File: `enterprise_fizzbuzz/domain/events/fizzstream.py`

```python
"""FizzStream Distributed Stream Processing events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("STREAM_JOB_SUBMITTED")
EventType.register("STREAM_JOB_STARTED")
EventType.register("STREAM_JOB_FINISHED")
EventType.register("STREAM_JOB_FAILED")
EventType.register("STREAM_JOB_CANCELLED")
EventType.register("STREAM_JOB_RESTARTED")
EventType.register("STREAM_CHECKPOINT_STARTED")
EventType.register("STREAM_CHECKPOINT_COMPLETED")
EventType.register("STREAM_CHECKPOINT_FAILED")
EventType.register("STREAM_SAVEPOINT_CREATED")
EventType.register("STREAM_SAVEPOINT_RESTORED")
EventType.register("STREAM_WATERMARK_ADVANCED")
EventType.register("STREAM_WINDOW_FIRED")
EventType.register("STREAM_WINDOW_LATE_ELEMENT")
EventType.register("STREAM_OPERATOR_STARTED")
EventType.register("STREAM_OPERATOR_FAILED")
EventType.register("STREAM_BACKPRESSURE_DETECTED")
EventType.register("STREAM_BACKPRESSURE_CLEARED")
EventType.register("STREAM_SCALE_UP")
EventType.register("STREAM_SCALE_DOWN")
EventType.register("STREAM_CEP_PATTERN_MATCHED")
EventType.register("STREAM_CEP_PATTERN_TIMED_OUT")
EventType.register("STREAM_JOIN_COMPLETED")
EventType.register("STREAM_DASHBOARD_RENDERED")
EventType.register("STREAM_EVALUATION_EMITTED")
```

Register in `enterprise_fizzbuzz/domain/events/__init__.py` by adding:

```python
import enterprise_fizzbuzz.domain.events.fizzstream  # noqa: F401
```

---

## 7. Config Properties (~15)

File: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzstream.py`

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `fizzstream_enabled` | `bool` | `False` | Enable the FizzStream subsystem |
| `fizzstream_parallelism` | `int` | `4` | Default operator parallelism |
| `fizzstream_max_parallelism` | `int` | `128` | Maximum parallelism / key group count |
| `fizzstream_checkpoint_interval_ms` | `int` | `60000` | Checkpoint interval in milliseconds |
| `fizzstream_state_backend` | `str` | `"hashmap"` | State backend type (hashmap or rocksdb) |
| `fizzstream_watermark_interval_ms` | `int` | `200` | Watermark emission interval in milliseconds |
| `fizzstream_buffer_timeout_ms` | `int` | `100` | Buffer flush timeout in milliseconds |
| `fizzstream_restart_strategy` | `str` | `"fixed"` | Restart strategy type (fixed, exponential, none) |
| `fizzstream_restart_max_attempts` | `int` | `3` | Maximum restart attempts |
| `fizzstream_restart_delay_ms` | `int` | `10000` | Delay between restart attempts |
| `fizzstream_checkpoint_retention` | `int` | `3` | Number of checkpoints to retain |
| `fizzstream_backpressure_high_pct` | `float` | `0.80` | Backpressure high watermark threshold |
| `fizzstream_backpressure_low_pct` | `float` | `0.50` | Backpressure low watermark threshold |
| `fizzstream_autoscale_enabled` | `bool` | `False` | Enable auto-scaling |
| `fizzstream_dashboard_width` | `int` | `76` | ASCII dashboard width |

Config mixin class: `FizzstreamConfigMixin` following the pattern from `FizzcomposeConfigMixin`.

---

## 8. YAML Config Section

File: `config.d/fizzstream.yaml`

```yaml
fizzstream:
  enabled: false
  parallelism: 4
  max_parallelism: 128
  checkpoint:
    interval_ms: 60000
    retention: 3
  state_backend: "hashmap"
  watermark:
    interval_ms: 200
  buffer:
    timeout_ms: 100
    size: 1024
    pool_size: 64
  restart:
    strategy: "fixed"
    max_attempts: 3
    delay_ms: 10000
  backpressure:
    high_watermark_pct: 0.80
    low_watermark_pct: 0.50
  autoscale:
    enabled: false
    scale_up_threshold_ms: 30000
    scale_down_threshold_ms: 60000
    cooldown_ms: 120000
    min_parallelism: 1
    max_parallelism: 16
  rocksdb:
    write_buffer_size_mb: 64
    max_write_buffers: 3
    block_cache_size_mb: 128
    compaction_style: "leveled"
  state_ttl:
    default_ttl_ms: 0
    cleanup_strategy: "incremental"
  topics:
    evaluations: "fizzbuzz.stream.evaluations"
    metrics: "fizzbuzz.stream.metrics"
    alerts: "fizzbuzz.stream.alerts"
    audit: "fizzbuzz.stream.audit"
    lifecycle: "fizzbuzz.stream.lifecycle"
  dashboard:
    width: 76
    refresh_ms: 5000
    enabled: false
```

---

## 9. CLI Flags

```python
# FizzStream flags
parser.add_argument("--fizzstream", action="store_true",
                    help="Enable the FizzStream distributed stream processing engine")
parser.add_argument("--fizzstream-job", type=str, default=None, metavar="FILE",
                    help="Submit a stream processing job defined in YAML")
parser.add_argument("--fizzstream-sql", type=str, default=None, metavar="QUERY",
                    help="Execute a streaming SQL query")
parser.add_argument("--fizzstream-list-jobs", action="store_true",
                    help="List all active and completed stream processing jobs")
parser.add_argument("--fizzstream-cancel", type=str, default=None, metavar="JOB_ID",
                    help="Cancel a running stream processing job")
parser.add_argument("--fizzstream-savepoint", nargs=2, default=None, metavar=("JOB_ID", "NAME"),
                    help="Trigger a savepoint for a running job")
parser.add_argument("--fizzstream-restore", nargs=2, default=None, metavar=("JOB_ID", "SAVEPOINT"),
                    help="Restore a job from a savepoint")
parser.add_argument("--fizzstream-scale", nargs=3, default=None, metavar=("JOB_ID", "OPERATOR", "PARALLELISM"),
                    help="Adjust operator parallelism for a running job")
parser.add_argument("--fizzstream-metrics", type=str, default=None, metavar="JOB_ID",
                    help="Display per-operator metrics for a stream processing job")
parser.add_argument("--fizzstream-dashboard", action="store_true",
                    help="Display the real-time ASCII pipeline dashboard")
parser.add_argument("--fizzstream-checkpoint-interval", type=int, default=None, metavar="MS",
                    help="Configure checkpoint interval in milliseconds (default: 60000)")
parser.add_argument("--fizzstream-state-backend", type=str, default=None, choices=["hashmap", "rocksdb"],
                    help="Select state backend (default: hashmap)")
parser.add_argument("--fizzstream-watermark-interval", type=int, default=None, metavar="MS",
                    help="Configure watermark emission interval in milliseconds (default: 200)")
parser.add_argument("--fizzstream-parallelism", type=int, default=None, metavar="N",
                    help="Configure default operator parallelism (default: 4)")
parser.add_argument("--fizzstream-max-parallelism", type=int, default=None, metavar="N",
                    help="Configure maximum parallelism / key group count (default: 128)")
parser.add_argument("--fizzstream-buffer-timeout", type=int, default=None, metavar="MS",
                    help="Configure buffer flush timeout in milliseconds (default: 100)")
parser.add_argument("--fizzstream-restart-strategy", type=str, default=None,
                    choices=["fixed", "exponential", "none"],
                    help="Configure restart strategy (default: fixed)")
```

---

## 10. Feature Descriptor

File: `enterprise_fizzbuzz/infrastructure/features/fizzstream_feature.py`

```python
"""Feature descriptor for FizzStream distributed stream processing."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzStreamFeature(FeatureDescriptor):
    name = "fizzstream"
    description = "Distributed stream processing engine for continuous computation"
    middleware_priority = 38
    cli_flags = [
        ("--fizzstream", {"action": "store_true",
                          "help": "Enable FizzStream distributed stream processing engine"}),
        ("--fizzstream-job", {"type": str, "default": None, "metavar": "FILE",
                              "help": "Submit a stream processing job defined in YAML"}),
        ("--fizzstream-sql", {"type": str, "default": None, "metavar": "QUERY",
                              "help": "Execute a streaming SQL query"}),
        ("--fizzstream-list-jobs", {"action": "store_true",
                                    "help": "List all active and completed jobs"}),
        ("--fizzstream-cancel", {"type": str, "default": None, "metavar": "JOB_ID",
                                  "help": "Cancel a running stream processing job"}),
        ("--fizzstream-savepoint", {"nargs": 2, "default": None,
                                     "metavar": ("JOB_ID", "NAME"),
                                     "help": "Trigger a savepoint for a running job"}),
        ("--fizzstream-restore", {"nargs": 2, "default": None,
                                   "metavar": ("JOB_ID", "SAVEPOINT"),
                                   "help": "Restore a job from a savepoint"}),
        ("--fizzstream-scale", {"nargs": 3, "default": None,
                                 "metavar": ("JOB_ID", "OPERATOR", "PARALLELISM"),
                                 "help": "Adjust operator parallelism"}),
        ("--fizzstream-metrics", {"type": str, "default": None, "metavar": "JOB_ID",
                                   "help": "Display per-operator metrics"}),
        ("--fizzstream-dashboard", {"action": "store_true",
                                     "help": "Display real-time ASCII pipeline dashboard"}),
        ("--fizzstream-checkpoint-interval", {"type": int, "default": None, "metavar": "MS",
                                               "help": "Checkpoint interval (ms)"}),
        ("--fizzstream-state-backend", {"type": str, "default": None,
                                         "choices": ["hashmap", "rocksdb"],
                                         "help": "State backend type"}),
        ("--fizzstream-watermark-interval", {"type": int, "default": None, "metavar": "MS",
                                              "help": "Watermark emission interval (ms)"}),
        ("--fizzstream-parallelism", {"type": int, "default": None, "metavar": "N",
                                       "help": "Default operator parallelism"}),
        ("--fizzstream-max-parallelism", {"type": int, "default": None, "metavar": "N",
                                           "help": "Maximum parallelism / key groups"}),
        ("--fizzstream-buffer-timeout", {"type": int, "default": None, "metavar": "MS",
                                          "help": "Buffer flush timeout (ms)"}),
        ("--fizzstream-restart-strategy", {"type": str, "default": None,
                                            "choices": ["fixed", "exponential", "none"],
                                            "help": "Restart strategy type"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzstream", False),
            getattr(args, "fizzstream_dashboard", False),
            getattr(args, "fizzstream_list_jobs", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzstream import (
            FizzStreamMiddleware,
            create_fizzstream_subsystem,
        )

        env, middleware = create_fizzstream_subsystem(
            parallelism=config.fizzstream_parallelism,
            max_parallelism=config.fizzstream_max_parallelism,
            checkpoint_interval_ms=config.fizzstream_checkpoint_interval_ms,
            state_backend=config.fizzstream_state_backend,
            dashboard_width=config.fizzstream_dashboard_width,
        )

        return env, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzstream_list_jobs", False):
            parts.append(middleware.render_jobs())
        if getattr(args, "fizzstream_dashboard", False):
            parts.append(middleware.render_dashboard())
        if getattr(args, "fizzstream", False) and not parts:
            parts.append(middleware.render_status())
        return "\n".join(parts) if parts else None
```

---

## 11. Middleware

### FizzStreamMiddleware

- **Class:** `FizzStreamMiddleware(IMiddleware)`
- **Priority:** 38 (after caching, before MapReduce)
- **Imports:** `IMiddleware` from `enterprise_fizzbuzz.domain.interfaces`, `FizzBuzzResult`, `ProcessingContext`, `EventType` from `enterprise_fizzbuzz.domain.models`
- **Constructor args:** `env: StreamExecutionEnvironment`, `dashboard_width: int`, `enable_dashboard: bool`
- **Methods:**
  - `get_name() -> str`: returns `"FizzStreamMiddleware"`
  - `get_priority() -> int`: returns `MIDDLEWARE_PRIORITY` (38)
  - `priority` property: returns `MIDDLEWARE_PRIORITY`
  - `name` property: returns `"FizzStreamMiddleware"`
  - `process(context: ProcessingContext, result: FizzBuzzResult, next_handler: Callable) -> FizzBuzzResult`:
    1. Emit the evaluation result as a `StreamElement` to the `fizzbuzz.stream.evaluations` topic
    2. Query active stream jobs for real-time aggregates (current evaluation rate, classification distribution, anomaly status)
    3. Attach stream processing metadata to the result context
    4. Delegate to `next_handler(context, result)`
    5. Track emission count
    6. Return result
  - `render_jobs() -> str`: render active/completed job list as ASCII table
  - `render_dashboard() -> str`: delegate to `FizzStreamDashboard`
  - `render_status() -> str`: render subsystem status summary

---

## 12. Factory Function

```python
def create_fizzstream_subsystem(
    parallelism: int = DEFAULT_PARALLELISM,
    max_parallelism: int = DEFAULT_MAX_PARALLELISM,
    checkpoint_interval_ms: int = DEFAULT_CHECKPOINT_INTERVAL_MS,
    state_backend: str = "hashmap",
    watermark_interval_ms: int = DEFAULT_WATERMARK_INTERVAL_MS,
    buffer_timeout_ms: int = DEFAULT_BUFFER_TIMEOUT_MS,
    restart_strategy: str = "fixed",
    restart_max_attempts: int = DEFAULT_RESTART_ATTEMPTS,
    restart_delay_ms: int = DEFAULT_RESTART_DELAY_MS,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzStream subsystem.

    Factory function that instantiates the StreamExecutionEnvironment
    with all supporting components (checkpoint coordinator, state backend,
    backpressure controller, buffer pool, metrics collector, dashboard),
    configures default streaming topics, and creates the middleware,
    ready for integration into the FizzBuzz evaluation pipeline.

    Args:
        parallelism: Default operator parallelism.
        max_parallelism: Maximum parallelism / key group count.
        checkpoint_interval_ms: Checkpoint interval.
        state_backend: State backend type ("hashmap" or "rocksdb").
        watermark_interval_ms: Watermark emission interval.
        buffer_timeout_ms: Buffer flush timeout.
        restart_strategy: Restart strategy type ("fixed", "exponential", "none").
        restart_max_attempts: Maximum restart attempts.
        restart_delay_ms: Delay between restart attempts.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (StreamExecutionEnvironment, FizzStreamMiddleware).
    """
```

Function body:
1. Select state backend: `HashMapStateBackend` or `RocksDBStateBackend`
2. Select restart strategy: `FixedDelayRestartStrategy`, `ExponentialBackoffRestartStrategy`, or `NoRestartStrategy`
3. Create `BufferPool(DEFAULT_BUFFER_POOL_SIZE, DEFAULT_BUFFER_SIZE)`
4. Create `BackpressureController(high_watermark_pct, low_watermark_pct)`
5. Create `CreditBasedFlowControl()`
6. Create `CheckpointCoordinator(checkpoint_interval_ms, state_backend_instance, checkpoint_storage)`
7. Create `KeyGroupAssigner(max_parallelism)`
8. Create `StreamMetricsCollector()`
9. Create `FizzStreamDashboard(dashboard_width)`
10. Create `SavepointManager(checkpoint_storage)`
11. Create `SavepointRestoreManager()`
12. Create `ScaleManager(key_group_assigner, savepoint_manager)`
13. Create `AutoScaler(scale_manager)`
14. Create `StreamExecutionEnvironment(parallelism, max_parallelism, checkpoint_coordinator, state_backend_instance, restart_strategy_instance, buffer_pool, backpressure_controller, metrics_collector, ...)`
15. Configure default streaming topics
16. Create `FizzStreamMiddleware(env, dashboard_width, enable_dashboard)`
17. Log subsystem creation
18. Return `(env, middleware)`

---

## 13. Test Classes

File: `tests/test_fizzstream.py` (~500 lines, ~65 tests)

| Test Class | Tests | Description |
|-----------|-------|-------------|
| `TestStreamEnums` | 8 | Validate all 14 enum classes, member counts, and string values |
| `TestStreamDataClasses` | 10 | Test dataclass construction, defaults, field validation for StreamElement, StreamRecord, OperatorDescriptor, WindowSpec, CheckpointMetadata, SavepointMetadata, OperatorMetrics, JobDescriptor, NFAState, PartialMatch |
| `TestStreamExecutionEnvironment` | 5 | Environment creation, configuration, source factory methods, job submission, job registry |
| `TestDataStreamAPI` | 6 | Fluent API chaining: filter, map, flat_map, key_by, window, sink_to; operator graph construction |
| `TestSourceOperators` | 5 | MessageQueueSource offset tracking, EventStoreSource journal tailing, ContainerEventSource lifecycle events, MetricSource ingestion, GeneratorSource bounded/unbounded modes |
| `TestTransformationOperators` | 6 | MapOperator, FlatMapOperator, FilterOperator, KeyByOperator with murmur3 hashing, ReduceOperator running aggregate, ProcessOperator with state and timers |
| `TestWindowingSystem` | 7 | TumblingEventTimeWindow assignment, SlidingEventTimeWindow overlap, SessionWindow gap detection and merge, GlobalWindow, WindowAssigner, EventTimeTrigger watermark firing, CountTrigger |
| `TestWatermarkSystem` | 5 | BoundedOutOfOrdernessStrategy watermark computation, MonotonousTimestampsStrategy, PunctuatedWatermarkStrategy, IdleSourceDetection advancement, WatermarkAlignment multi-input minimum |
| `TestCheckpointing` | 5 | CheckpointCoordinator barrier injection, barrier alignment, InMemoryCheckpointStorage round-trip, FileSystemCheckpointStorage persistence, RestartStrategy hierarchy |
| `TestStatefulProcessing` | 6 | ValueState CRUD, ListState operations, MapState operations, ReducingState incremental reduce, AggregatingState accumulator, HashMapStateBackend vs RocksDBStateBackend |
| `TestStreamJoins` | 4 | StreamStreamJoin time-bounded matching, StreamTableJoin materialized view lookup, IntervalJoin asymmetric bounds, join type semantics (inner, left, right, full) |
| `TestCEP` | 5 | Pattern fluent API construction, PatternElement quantifiers, NFACompiler state machine generation, CEPOperator partial match advancement, PatternStream select/timed_out |
| `TestBackpressure` | 3 | BackpressureController high/low watermark signaling, CreditBasedFlowControl credit protocol, BufferPool exhaustion blocking |
| `TestSavepoints` | 3 | SavepointManager creation and retrieval, SavepointRestoreManager topology change handling, upgrade workflow simulation |
| `TestDynamicScaling` | 3 | ScaleManager parallelism adjustment, AutoScaler threshold-based decisions, KeyGroupAssigner consistent redistribution |
| `TestStreamMetrics` | 2 | StreamMetricsCollector per-operator metric collection, FizzStreamDashboard ASCII rendering |
| `TestStreamSQLBridge` | 2 | TUMBLE/HOP/SESSION window SQL parsing, continuous SELECT compilation to DataStream graph |
| `TestFizzStreamMiddleware` | 3 | Middleware process delegation, evaluation emission to stream topic, real-time aggregate annotation |
| `TestStreamExceptions` | 3 | Error code format (EFP-STR prefix), context population, inheritance chain |
| `TestCreateFizzstreamSubsystem` | 2 | Factory function wiring, return types, state backend selection |

**Total:** ~91 tests across 20 test classes

---

## 14. Re-export Stub

File: `fizzstream.py` (root level)

```python
"""Re-export stub for backward compatibility.

This module re-exports the public API from the canonical location
within the enterprise_fizzbuzz.infrastructure package.
"""

from enterprise_fizzbuzz.infrastructure.fizzstream import (  # noqa: F401
    # Constants
    DEFAULT_BACKOFF_INITIAL_MS,
    DEFAULT_BACKOFF_MAX_MS,
    DEFAULT_BACKOFF_MULTIPLIER,
    DEFAULT_BUFFER_POOL_SIZE,
    DEFAULT_BUFFER_SIZE,
    DEFAULT_BUFFER_TIMEOUT_MS,
    DEFAULT_CHECKPOINT_INTERVAL_MS,
    DEFAULT_CHECKPOINT_RETENTION,
    DEFAULT_DASHBOARD_REFRESH_MS,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_HIGH_WATERMARK_PCT,
    DEFAULT_LOW_WATERMARK_PCT,
    DEFAULT_MAX_PARALLELISM,
    DEFAULT_PARALLELISM,
    DEFAULT_RESTART_ATTEMPTS,
    DEFAULT_RESTART_DELAY_MS,
    DEFAULT_SCALE_COOLDOWN_MS,
    DEFAULT_SCALE_DOWN_THRESHOLD_MS,
    DEFAULT_SCALE_UP_THRESHOLD_MS,
    DEFAULT_WATERMARK_INTERVAL_MS,
    FIZZSTREAM_VERSION,
    KEY_GROUP_COUNT,
    MIDDLEWARE_PRIORITY,
    MURMUR3_SEED,
    STREAM_TOPIC_ALERTS,
    STREAM_TOPIC_AUDIT,
    STREAM_TOPIC_EVALUATIONS,
    STREAM_TOPIC_LIFECYCLE,
    STREAM_TOPIC_METRICS,
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
    # Core classes
    StreamExecutionEnvironment,
    DataStream,
    KeyedStream,
    StreamOperator,
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
    # Integration
    StreamSQLBridge,
    # Middleware
    FizzStreamMiddleware,
    # Exceptions
    BackpressureError,
    BarrierAlignmentTimeoutError,
    CEPMatchError,
    CEPPatternError,
    CheckpointError,
    CheckpointRestoreError,
    KeyGroupAssignmentError,
    RestartExhaustedError,
    SavepointError,
    SavepointRestoreError,
    ScaleError,
    StateAccessError,
    StateBackendError,
    StateTTLError,
    StreamJobNotFoundError,
    StreamJobSubmissionError,
    StreamJoinError,
    StreamMiddlewareError,
    StreamOperatorError,
    StreamProcessingError,
    StreamSQLError,
    StreamSinkError,
    StreamSourceError,
    WatermarkViolationError,
    WindowError,
    # Factory
    create_fizzstream_subsystem,
)
```

---

## 15. Integration Points

### Message Queue Integration

`MessageQueueSource` reads from `Topic` partitions via existing `Consumer` and `ConsumerGroup` classes. Offset tracking per partition, watermark extraction from message timestamps. During checkpointing, committed offsets are recorded for exactly-once consumption via offset rollback on failure.

`MessageQueueSink` writes to `Topic` partitions via existing `Producer` class. Uses the producer's idempotency layer for exactly-once production.

Five default streaming topics:
1. `fizzbuzz.stream.evaluations` -- real-time evaluation results
2. `fizzbuzz.stream.metrics` -- continuous metric emissions
3. `fizzbuzz.stream.alerts` -- threshold violations and anomalies
4. `fizzbuzz.stream.audit` -- compliance-relevant events
5. `fizzbuzz.stream.lifecycle` -- container and service lifecycle events

### Event Sourcing Integration

`EventStoreSource` tails the `EventStore` journal. Configurable start position (beginning, specific sequence number, latest). Events deserialized into stream elements. Sequence numbers recorded during checkpointing.

`EventStoreSink` appends computed results as domain events via `EventStore.append()`.

### FizzSQL Integration

`StreamSQLBridge` extends `FizzSQLEngine` with streaming SQL:
- Window functions: `TUMBLE(event_time, INTERVAL '1' MINUTE)`, `HOP(event_time, INTERVAL '10' SECOND, INTERVAL '1' MINUTE)`, `SESSION(event_time, INTERVAL '30' SECOND)`
- Emission control: `EMIT AFTER WATERMARK`, `EMIT WITH DELAY INTERVAL '5' SECOND`
- Streaming joins: `JOIN stream_b ON a.key = b.key AND a.event_time BETWEEN b.event_time - INTERVAL '5' MINUTE AND b.event_time + INTERVAL '5' MINUTE`
- Continuous `SELECT` queries compiled into DataStream operator graphs

---

## Implementation Order

1. **Constants block** (~30 constants)
2. **Enums block** (14 enums)
3. **Data classes block** (~14 data classes)
4. **Watermark system** -- Watermark, WatermarkStrategy hierarchy, WatermarkAlignment, IdleSourceDetection
5. **State descriptors and backends** -- ValueState, ListState, MapState, ReducingState, AggregatingState, HashMapStateBackend, RocksDBStateBackend, StateTTL
6. **Stream operators** -- StreamOperator base, MapOperator, FlatMapOperator, FilterOperator, KeyByOperator, ReduceOperator, ProcessOperator, UnionOperator, ProcessContext
7. **Windowing system** -- Window types, WindowAssigner, Trigger hierarchy, WindowFunction variants, AllowedLateness
8. **DataStream and KeyedStream** -- fluent API, operator graph construction
9. **Source operators** -- MessageQueueSource, EventStoreSource, ContainerEventSource, MetricSource, GeneratorSource
10. **Sink operators** -- MessageQueueSink, EventStoreSink
11. **Checkpointing** -- CheckpointBarrier, CheckpointCoordinator, CheckpointStorage hierarchy, RestartStrategy hierarchy
12. **Stream joins** -- StreamStreamJoin, StreamTableJoin, IntervalJoin
13. **CEP** -- Pattern, PatternElement, NFACompiler, CEPOperator, PatternStream
14. **Backpressure** -- BackpressureController, CreditBasedFlowControl, BufferPool
15. **Savepoints** -- SavepointManager, SavepointRestoreManager
16. **Dynamic scaling** -- KeyGroupAssigner, ScaleManager, AutoScaler
17. **Metrics and dashboard** -- StreamMetricsCollector, FizzStreamDashboard
18. **StreamSQLBridge** -- streaming SQL extensions
19. **StreamExecutionEnvironment** -- job compilation, execution, management
20. **StreamJob** -- runtime job representation
21. **FizzStreamMiddleware** -- IMiddleware implementation
22. **Factory function** -- `create_fizzstream_subsystem()`

### Parallel Work (exceptions + events + config)

- Create `enterprise_fizzbuzz/domain/exceptions/fizzstream.py` (25 exceptions, EFP-STR00 through EFP-STR24)
- Create `enterprise_fizzbuzz/domain/events/fizzstream.py` (25 event types) and register in `__init__.py`
- Create `enterprise_fizzbuzz/infrastructure/config/mixins/fizzstream.py` (15 config properties)
- Create `enterprise_fizzbuzz/infrastructure/features/fizzstream_feature.py` (feature descriptor)
- Create `config.d/fizzstream.yaml` (YAML config)
- Create `fizzstream.py` (root-level re-export stub)

---

## Line Count Estimate

| Component | Lines |
|-----------|-------|
| Module docstring + imports | ~60 |
| Constants | ~80 |
| Enums | ~180 |
| Data classes | ~350 |
| Watermark system | ~250 |
| State descriptors and backends | ~300 |
| Stream operators | ~250 |
| Windowing system | ~400 |
| DataStream + KeyedStream API | ~280 |
| Source operators | ~400 |
| Sink operators | ~140 |
| Checkpointing (Chandy-Lamport) | ~350 |
| Stream joins | ~300 |
| CEP (Pattern + NFA) | ~370 |
| Backpressure | ~150 |
| Savepoints | ~130 |
| Dynamic scaling | ~170 |
| Metrics + dashboard | ~180 |
| StreamSQLBridge | ~100 |
| StreamExecutionEnvironment | ~250 |
| StreamJob | ~50 |
| FizzStreamMiddleware | ~80 |
| Factory function | ~60 |
| **Total (fizzstream.py)** | **~4,330** |
| Exceptions (domain/exceptions/fizzstream.py) | ~350 |
| Event types (domain/events/fizzstream.py) | ~30 |
| Config mixin | ~100 |
| Feature descriptor | ~80 |
| YAML config | ~50 |
| Re-export stub | ~140 |
| Tests | ~500 |
| **Grand Total** | **~5,580** |

"""
Enterprise FizzBuzz Platform - FizzStream Distributed Stream Processing Engine

Implements a complete distributed stream processing framework for continuous
FizzBuzz computation over unbounded event sequences. Modern enterprise
FizzBuzz evaluation generates a continuous, high-throughput stream of
classification events that must be processed in real time with exactly-once
guarantees, event-time semantics, windowed aggregation, stateful processing,
and fault-tolerant checkpointing via the Chandy-Lamport distributed snapshot
algorithm.

FizzStream provides:

    - **DataStream API**: Fluent, composable stream transformation operators
      (map, filter, flat_map, key_by, window, reduce, process, union, join)
    - **Event-Time Processing**: Watermark-based event-time tracking with
      bounded-out-of-orderness, monotonous timestamps, and punctuated
      strategies, plus idle source detection and multi-input alignment
    - **Windowing**: Tumbling, sliding, session, and global windows with
      pluggable triggers (event-time, processing-time, count, purging,
      continuous) and allowed lateness
    - **Stateful Processing**: Per-key state abstractions (ValueState,
      ListState, MapState, ReducingState, AggregatingState) backed by
      HashMap or RocksDB-style LSM-tree state backends with configurable
      TTL and proactive cleanup
    - **Checkpointing**: Chandy-Lamport distributed snapshots with barrier
      alignment, in-memory and filesystem checkpoint storage, configurable
      retention, and automatic recovery via pluggable restart strategies
    - **Savepoints**: Named, persistent checkpoints for version upgrades
      with topology change handling and state redistribution
    - **Dynamic Scaling**: Runtime parallelism adjustment via savepoint-based
      coordination with key group redistribution and auto-scaling based on
      backpressure and throughput metrics
    - **Complex Event Processing (CEP)**: Declarative pattern specification
      with NFA-based matching, quantifiers, contiguity modes, and timeout
      detection
    - **Stream Joins**: Stream-stream joins (inner, left, right, full) with
      time-bounded windows, stream-table temporal joins against materialized
      views, and interval joins with asymmetric bounds
    - **Backpressure**: Credit-based flow control with buffer pools, high/low
      watermark signaling, and per-operator backpressure metrics
    - **Streaming SQL**: TUMBLE/HOP/SESSION window functions, EMIT AFTER
      WATERMARK, continuous SELECT compilation to DataStream operator graphs
    - **Metrics & Dashboard**: Per-operator throughput, latency percentiles,
      backpressure time, buffer utilization, checkpoint duration, state size,
      watermark lag, and ASCII pipeline visualization

The middleware integration emits each FizzBuzz evaluation result to the
``fizzbuzz.stream.evaluations`` topic for continuous downstream consumption
by windowed aggregation pipelines, anomaly detection patterns, and
real-time compliance audit streams.
"""

from __future__ import annotations

import abc
import collections
import hashlib
import logging
import math
import pickle
import struct
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from enterprise_fizzbuzz.domain.exceptions.fizzstream import (
    BackpressureError,
    BarrierAlignmentTimeoutError,
    CEPMatchError,
    CEPPatternError,
    KeyGroupAssignmentError,
    RestartExhaustedError,
    ScaleError,
    StateAccessError,
    StateBackendError,
    StateTTLError,
    StreamCheckpointError,
    StreamCheckpointRestoreError,
    StreamJoinError,
    StreamJobNotFoundError,
    StreamJobSubmissionError,
    StreamMiddlewareError,
    StreamOperatorError,
    StreamProcessingError,
    StreamSQLError,
    StreamSavepointError,
    StreamSavepointRestoreError,
    StreamSinkError,
    StreamSourceError,
    WatermarkViolationError,
    WindowError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import FizzBuzzResult, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

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


# ============================================================
# Enumerations
# ============================================================


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


# ============================================================
# Data Classes
# ============================================================


@dataclass
class StreamElement:
    """A single element in a data stream.

    Attributes:
        value: The element's payload.
        timestamp: Event time in milliseconds since epoch.
        key: Partition key (set after KeyBy).
    """
    value: Any = None
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
    uid: str = ""
    name: str = ""
    operator_type: str = ""
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
    start: int = 0
    end: int = 0
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
    checkpoint_id: int = 0
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
    name: str = ""
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
    name: str = ""
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
    name: str = ""
    partitions: int = 4
    replication_factor: int = 1
    retention_ms: int = 86400000  # 24 hours
    description: str = ""


# ============================================================
# Murmur3 Hash
# ============================================================


def _murmur3_32(key: Any, seed: int = MURMUR3_SEED) -> int:
    """Compute a 32-bit murmur3 hash for consistent key partitioning.

    This is a faithful implementation of the MurmurHash3_x86_32
    algorithm. It is used by the KeyByOperator to deterministically
    assign stream elements to key groups based on their partition key,
    ensuring that elements with the same key always land in the same
    operator instance regardless of cluster topology changes.

    Args:
        key: The key to hash. Will be converted to bytes via pickle
             serialization if not already bytes.
        seed: The hash seed. Defaults to MURMUR3_SEED.

    Returns:
        A 32-bit unsigned integer hash value.
    """
    if isinstance(key, bytes):
        data = key
    elif isinstance(key, str):
        data = key.encode("utf-8")
    elif isinstance(key, int):
        data = struct.pack("<q", key)
    else:
        data = pickle.dumps(key)

    length = len(data)
    nblocks = length // 4
    h1 = seed & 0xFFFFFFFF

    c1 = 0xCC9E2D51
    c2 = 0x1B873593

    # Body
    for block_start in range(0, nblocks * 4, 4):
        k1 = struct.unpack_from("<I", data, block_start)[0]
        k1 = (k1 * c1) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (k1 * c2) & 0xFFFFFFFF

        h1 ^= k1
        h1 = ((h1 << 13) | (h1 >> 19)) & 0xFFFFFFFF
        h1 = ((h1 * 5) + 0xE6546B64) & 0xFFFFFFFF

    # Tail
    tail_index = nblocks * 4
    k1 = 0
    tail_size = length & 3

    if tail_size >= 3:
        k1 ^= data[tail_index + 2] << 16
    if tail_size >= 2:
        k1 ^= data[tail_index + 1] << 8
    if tail_size >= 1:
        k1 ^= data[tail_index]
        k1 = (k1 * c1) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (k1 * c2) & 0xFFFFFFFF
        h1 ^= k1

    # Finalization
    h1 ^= length
    h1 ^= (h1 >> 16)
    h1 = (h1 * 0x85EBCA6B) & 0xFFFFFFFF
    h1 ^= (h1 >> 13)
    h1 = (h1 * 0xC2B2AE35) & 0xFFFFFFFF
    h1 ^= (h1 >> 16)

    return h1


# ============================================================
# Watermark System
# ============================================================


class Watermark:
    """Special stream element declaring event-time completeness threshold.

    A watermark with timestamp T asserts that no future elements will
    arrive with a timestamp less than T. Downstream operators use this
    guarantee to close windows, fire triggers, and advance event-time
    clocks.
    """

    def __init__(self, timestamp: int) -> None:
        self.timestamp = timestamp

    def __repr__(self) -> str:
        return f"Watermark(timestamp={self.timestamp})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Watermark):
            return self.timestamp == other.timestamp
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.timestamp)


class BoundedOutOfOrdernessStrategy:
    """Generates watermarks as max_timestamp - max_out_of_orderness.

    This strategy tolerates events arriving out of order up to a
    configurable bound. The watermark is computed as the maximum
    observed timestamp minus the maximum allowed out-of-orderness,
    ensuring that late events within the tolerance window are still
    processed by downstream windows.

    Args:
        max_out_of_orderness_ms: Maximum tolerated out-of-order arrival
            in milliseconds.
    """

    def __init__(self, max_out_of_orderness_ms: int = 5000) -> None:
        self.max_out_of_orderness_ms = max_out_of_orderness_ms
        self.max_timestamp: int = -1
        self.strategy_type = WatermarkStrategyType.BOUNDED_OUT_OF_ORDERNESS

    def on_event(self, timestamp: int) -> None:
        """Update the maximum observed timestamp."""
        if timestamp > self.max_timestamp:
            self.max_timestamp = timestamp

    def get_watermark(self) -> Watermark:
        """Compute the current watermark."""
        if self.max_timestamp < 0:
            return Watermark(-1)
        return Watermark(self.max_timestamp - self.max_out_of_orderness_ms)


class MonotonousTimestampsStrategy:
    """Generates watermarks as max_timestamp - 1.

    Optimized for sources that guarantee monotonically increasing
    timestamps. The watermark trails the maximum observed timestamp
    by exactly 1 millisecond.
    """

    def __init__(self) -> None:
        self.max_timestamp: int = -1
        self.strategy_type = WatermarkStrategyType.MONOTONOUS

    def on_event(self, timestamp: int) -> None:
        """Update the maximum observed timestamp."""
        if timestamp > self.max_timestamp:
            self.max_timestamp = timestamp

    def get_watermark(self) -> Watermark:
        """Compute the current watermark."""
        if self.max_timestamp < 0:
            return Watermark(-1)
        return Watermark(self.max_timestamp - 1)


class PunctuatedWatermarkStrategy:
    """Extracts watermarks from punctuation events in the stream.

    This strategy relies on special punctuation elements embedded in
    the stream by the source that carry explicit watermark timestamps.
    The extractor function identifies punctuation events and returns
    their watermark value, or None for non-punctuation elements.

    Args:
        extractor: Function that takes an element and returns a
            watermark timestamp (int) or None if not a punctuation.
    """

    def __init__(self, extractor: Callable[[Any], Optional[int]]) -> None:
        self.extractor = extractor
        self.current_watermark: int = -1
        self.strategy_type = WatermarkStrategyType.PUNCTUATED

    def on_event(self, element: Any) -> Optional[Watermark]:
        """Check if the element is a punctuation and extract watermark."""
        ts = self.extractor(element)
        if ts is not None and ts > self.current_watermark:
            self.current_watermark = ts
            return Watermark(ts)
        return None

    def get_watermark(self) -> Watermark:
        """Return the last extracted watermark."""
        return Watermark(self.current_watermark)


class IdleSourceDetection:
    """Advances watermark for idle partitions to prevent stalling.

    When a source partition stops emitting events, its watermark
    remains static, preventing downstream operators from advancing
    their effective watermarks (computed as the minimum across all
    inputs). IdleSourceDetection marks partitions as idle after a
    configurable timeout and excludes them from the minimum
    watermark computation.

    Args:
        idle_timeout_ms: Duration without events before marking idle.
    """

    def __init__(self, idle_timeout_ms: int = 30000) -> None:
        self.idle_timeout_ms = idle_timeout_ms
        self._last_event_time: Dict[str, float] = {}
        self._idle_partitions: Set[str] = set()

    def record_event(self, partition_id: str) -> None:
        """Record that an event was received from a partition."""
        self._last_event_time[partition_id] = time.time() * 1000
        self._idle_partitions.discard(partition_id)

    def check_idle(self) -> Set[str]:
        """Return the set of currently idle partitions."""
        now = time.time() * 1000
        for partition_id, last_time in self._last_event_time.items():
            if now - last_time > self.idle_timeout_ms:
                self._idle_partitions.add(partition_id)
        return set(self._idle_partitions)

    def is_idle(self, partition_id: str) -> bool:
        """Check if a specific partition is idle."""
        return partition_id in self._idle_partitions


class WatermarkAlignment:
    """Computes effective watermark as minimum across multi-input operators.

    When an operator has multiple inputs (e.g., after a union or join),
    its effective watermark is the minimum watermark across all
    non-idle input channels. This ensures that windowing and timer
    decisions are correct even when inputs progress at different rates.
    """

    def __init__(self) -> None:
        self._watermarks: Dict[str, int] = {}
        self._idle: Set[str] = set()

    def update(self, input_id: str, watermark: int) -> None:
        """Update the watermark for an input channel."""
        self._watermarks[input_id] = watermark
        self._idle.discard(input_id)

    def mark_idle(self, input_id: str) -> None:
        """Mark an input channel as idle."""
        self._idle.add(input_id)

    def get_effective_watermark(self) -> int:
        """Compute the effective watermark across all active inputs."""
        active = {
            k: v for k, v in self._watermarks.items()
            if k not in self._idle
        }
        if not active:
            return -1
        return min(active.values())


# ============================================================
# Window System
# ============================================================


class TumblingEventTimeWindow:
    """Fixed-size, non-overlapping windows aligned to event time.

    Each element is assigned to exactly one window. Windows are
    aligned to the epoch with an optional offset.

    Args:
        size_ms: Window size in milliseconds.
        offset_ms: Window alignment offset in milliseconds.
    """

    def __init__(self, size_ms: int, offset_ms: int = 0) -> None:
        self.size_ms = size_ms
        self.offset_ms = offset_ms
        self.window_type = WindowType.TUMBLING

    def assign_windows(self, timestamp: int) -> List[WindowSpec]:
        """Assign the element to its tumbling window."""
        adjusted = timestamp - self.offset_ms
        start = (adjusted // self.size_ms) * self.size_ms + self.offset_ms
        end = start + self.size_ms
        return [WindowSpec(start=start, end=end, max_timestamp=end - 1,
                           window_type=WindowType.TUMBLING)]


class SlidingEventTimeWindow:
    """Fixed-size overlapping windows with configurable slide interval.

    Each element may belong to multiple windows. The number of windows
    an element belongs to is size_ms / slide_ms.

    Args:
        size_ms: Window size in milliseconds.
        slide_ms: Slide interval in milliseconds.
    """

    def __init__(self, size_ms: int, slide_ms: int) -> None:
        self.size_ms = size_ms
        self.slide_ms = slide_ms
        self.window_type = WindowType.SLIDING

    def assign_windows(self, timestamp: int) -> List[WindowSpec]:
        """Assign the element to all overlapping sliding windows."""
        windows = []
        last_start = timestamp - timestamp % self.slide_ms
        first_start = last_start - self.size_ms + self.slide_ms
        start = first_start
        while start <= last_start:
            end = start + self.size_ms
            if start <= timestamp < end:
                windows.append(WindowSpec(
                    start=start, end=end, max_timestamp=end - 1,
                    window_type=WindowType.SLIDING,
                ))
            start += self.slide_ms
        return windows


class SessionWindow:
    """Dynamically-sized windows defined by gaps in activity.

    Events are grouped into sessions separated by inactivity gaps.
    When a new event arrives within gap_ms of the last event in a
    session, the session is extended. Sessions are finalized when
    the watermark advances past the session end + gap.

    Args:
        gap_ms: Maximum gap between events in the same session.
    """

    def __init__(self, gap_ms: int) -> None:
        self.gap_ms = gap_ms
        self.window_type = WindowType.SESSION

    def assign_windows(self, timestamp: int) -> List[WindowSpec]:
        """Assign the element to a session window.

        Initially each element creates its own window. Session windows
        are later merged by the window operator when adjacent sessions
        overlap.
        """
        return [WindowSpec(
            start=timestamp, end=timestamp + self.gap_ms,
            max_timestamp=timestamp + self.gap_ms - 1,
            window_type=WindowType.SESSION,
        )]

    def merge_windows(self, windows: List[WindowSpec]) -> List[WindowSpec]:
        """Merge overlapping session windows."""
        if not windows:
            return []
        sorted_windows = sorted(windows, key=lambda w: w.start)
        merged = [sorted_windows[0]]
        for w in sorted_windows[1:]:
            if w.start <= merged[-1].end:
                merged[-1] = WindowSpec(
                    start=merged[-1].start,
                    end=max(merged[-1].end, w.end),
                    max_timestamp=max(merged[-1].end, w.end) - 1,
                    window_type=WindowType.SESSION,
                )
            else:
                merged.append(w)
        return merged


class GlobalWindow:
    """Single window containing all elements.

    The global window never closes on its own. It requires a custom
    trigger to fire results.
    """

    def __init__(self) -> None:
        self.window_type = WindowType.GLOBAL

    def assign_windows(self, timestamp: int) -> List[WindowSpec]:
        """Assign the element to the global window."""
        return [WindowSpec(
            start=0, end=2**63 - 1, max_timestamp=2**63 - 2,
            window_type=WindowType.GLOBAL,
        )]


class WindowAssigner:
    """Assigns each element to zero or more windows.

    Delegates to the underlying window definition (tumbling, sliding,
    session, global) to determine window assignment based on the
    element's event timestamp.

    Args:
        window_def: The window definition to use for assignment.
    """

    def __init__(self, window_def: Any) -> None:
        self.window_def = window_def

    def assign(self, timestamp: int) -> List[WindowSpec]:
        """Assign element to windows based on its timestamp."""
        return self.window_def.assign_windows(timestamp)


class AllowedLateness:
    """Grace period for late elements after window close.

    Elements arriving after the window's watermark has passed but
    within the allowed lateness will still be processed and may
    trigger re-computation of the window result.

    Args:
        lateness_ms: Maximum lateness in milliseconds.
    """

    def __init__(self, lateness_ms: int = 0) -> None:
        self.lateness_ms = lateness_ms

    def is_late(self, element_timestamp: int, window_end: int, current_watermark: int) -> bool:
        """Check if an element is late beyond the allowed lateness."""
        return current_watermark > window_end + self.lateness_ms


# ============================================================
# Triggers
# ============================================================


class EventTimeTrigger:
    """Fires when watermark passes window end timestamp.

    This is the default trigger for event-time windows. It fires
    exactly once when the watermark advances past the window's
    maximum timestamp.
    """

    def on_element(self, element: StreamElement, window: WindowSpec,
                   current_watermark: int) -> TriggerResult:
        """Process an element arrival."""
        if current_watermark >= window.end:
            return TriggerResult.FIRE
        return TriggerResult.CONTINUE

    def on_watermark(self, watermark: int, window: WindowSpec) -> TriggerResult:
        """Process a watermark advancement."""
        if watermark >= window.end:
            return TriggerResult.FIRE
        return TriggerResult.CONTINUE


class ProcessingTimeTrigger:
    """Fires at wall-clock time equal to window end.

    This trigger is used when processing-time semantics are
    configured. It fires when the system clock reaches the
    window's end timestamp.
    """

    def on_element(self, element: StreamElement, window: WindowSpec,
                   current_watermark: int) -> TriggerResult:
        """Process an element arrival."""
        now_ms = int(time.time() * 1000)
        if now_ms >= window.end:
            return TriggerResult.FIRE
        return TriggerResult.CONTINUE

    def on_watermark(self, watermark: int, window: WindowSpec) -> TriggerResult:
        """Processing time triggers do not respond to watermarks."""
        return TriggerResult.CONTINUE


class CountTrigger:
    """Fires when window contains specified number of elements.

    This trigger maintains a count of elements in the window and
    fires when the count reaches the configured threshold.

    Args:
        max_count: Number of elements to trigger on.
    """

    def __init__(self, max_count: int) -> None:
        self.max_count = max_count
        self._counts: Dict[str, int] = defaultdict(int)

    def on_element(self, element: StreamElement, window: WindowSpec,
                   current_watermark: int) -> TriggerResult:
        """Increment count and check threshold."""
        window_key = f"{window.start}:{window.end}"
        self._counts[window_key] += 1
        if self._counts[window_key] >= self.max_count:
            self._counts[window_key] = 0
            return TriggerResult.FIRE
        return TriggerResult.CONTINUE

    def on_watermark(self, watermark: int, window: WindowSpec) -> TriggerResult:
        """Count triggers do not respond to watermarks."""
        return TriggerResult.CONTINUE


class PurgingTrigger:
    """Wraps another trigger, clears window contents after firing.

    When the inner trigger fires, this wrapper converts the result
    to FIRE_AND_PURGE, causing the window contents to be cleared
    after the window function is invoked.

    Args:
        inner_trigger: The trigger to wrap.
    """

    def __init__(self, inner_trigger: Any) -> None:
        self.inner_trigger = inner_trigger

    def on_element(self, element: StreamElement, window: WindowSpec,
                   current_watermark: int) -> TriggerResult:
        """Delegate to inner trigger and convert FIRE to FIRE_AND_PURGE."""
        result = self.inner_trigger.on_element(element, window, current_watermark)
        if result == TriggerResult.FIRE:
            return TriggerResult.FIRE_AND_PURGE
        return result

    def on_watermark(self, watermark: int, window: WindowSpec) -> TriggerResult:
        """Delegate to inner trigger and convert FIRE to FIRE_AND_PURGE."""
        result = self.inner_trigger.on_watermark(watermark, window)
        if result == TriggerResult.FIRE:
            return TriggerResult.FIRE_AND_PURGE
        return result


class ContinuousEventTimeTrigger:
    """Fires periodically within a window for early results.

    This trigger fires at regular intervals within a window,
    allowing downstream consumers to see partial results before
    the window closes.

    Args:
        interval_ms: Firing interval in milliseconds.
    """

    def __init__(self, interval_ms: int) -> None:
        self.interval_ms = interval_ms
        self._next_fire: Dict[str, int] = {}

    def on_element(self, element: StreamElement, window: WindowSpec,
                   current_watermark: int) -> TriggerResult:
        """Register the next fire time on first element."""
        window_key = f"{window.start}:{window.end}"
        if window_key not in self._next_fire:
            self._next_fire[window_key] = window.start + self.interval_ms
        return TriggerResult.CONTINUE

    def on_watermark(self, watermark: int, window: WindowSpec) -> TriggerResult:
        """Fire if watermark passes the next scheduled fire time."""
        window_key = f"{window.start}:{window.end}"
        next_fire = self._next_fire.get(window_key)
        if next_fire is not None and watermark >= next_fire:
            self._next_fire[window_key] = next_fire + self.interval_ms
            if self._next_fire[window_key] >= window.end:
                return TriggerResult.FIRE
            return TriggerResult.FIRE
        if watermark >= window.end:
            return TriggerResult.FIRE
        return TriggerResult.CONTINUE


# ============================================================
# Window Functions
# ============================================================


class ReduceFunction:
    """Incrementally reduces elements as they arrive.

    The reduce function is called for each new element with the
    current accumulated value and the new element, producing an
    updated accumulated value. This is memory-efficient as only
    the accumulated value is stored.

    Args:
        reduce_fn: Binary function (accumulator, element) -> accumulator.
    """

    def __init__(self, reduce_fn: Callable[[Any, Any], Any]) -> None:
        self.reduce_fn = reduce_fn

    def reduce(self, accumulator: Any, element: Any) -> Any:
        """Apply the reduction."""
        return self.reduce_fn(accumulator, element)


class AggregateFunction:
    """Generalizes ReduceFunction with accumulator, add, merge, extract.

    Supports separate input, accumulator, and output types. The
    lifecycle is: create_accumulator() -> add() for each element ->
    merge() for parallel execution -> get_result() to extract output.

    Args:
        create_accumulator: Factory for new accumulators.
        add: Function (accumulator, element) -> accumulator.
        merge: Function (acc1, acc2) -> merged_accumulator.
        get_result: Function (accumulator) -> output.
    """

    def __init__(
        self,
        create_accumulator: Callable[[], Any],
        add: Callable[[Any, Any], Any],
        merge: Callable[[Any, Any], Any],
        get_result: Callable[[Any], Any],
    ) -> None:
        self.create_accumulator = create_accumulator
        self.add = add
        self.merge = merge
        self.get_result = get_result


class ProcessWindowFunction:
    """Receives all buffered elements when window fires.

    Unlike ReduceFunction and AggregateFunction which process
    elements incrementally, this function receives the complete
    contents of the window, along with window metadata, when
    the trigger fires.

    Args:
        process_fn: Function (key, window, elements) -> Iterable[output].
    """

    def __init__(self, process_fn: Callable[[Any, WindowSpec, List[Any]], Iterable]) -> None:
        self.process_fn = process_fn

    def process(self, key: Any, window: WindowSpec, elements: List[Any]) -> Iterable:
        """Process all elements in the window."""
        return self.process_fn(key, window, elements)


# ============================================================
# Keyed State
# ============================================================


class ValueState:
    """Single value per key.

    Provides get/update/clear semantics for a single keyed value.
    The value is stored in the state backend and is scoped to
    the current key.

    Args:
        name: State descriptor name.
        backend: The state backend providing storage.
    """

    def __init__(self, name: str, backend: Any = None) -> None:
        self.name = name
        self._backend = backend
        self._values: Dict[Any, Any] = {}

    def value(self, key: Any = None) -> Optional[Any]:
        """Get the current value for the key."""
        return self._values.get(key)

    def update(self, value: Any, key: Any = None) -> None:
        """Update the value for the key."""
        self._values[key] = value

    def clear(self, key: Any = None) -> None:
        """Clear the value for the key."""
        self._values.pop(key, None)

    def snapshot(self) -> Dict[Any, Any]:
        """Snapshot the entire state for checkpointing."""
        return dict(self._values)

    def restore(self, state: Dict[Any, Any]) -> None:
        """Restore state from a checkpoint."""
        self._values = dict(state)


class ListState:
    """Ordered list per key.

    Provides append, iteration, and bulk update operations on
    a per-key list stored in the state backend.

    Args:
        name: State descriptor name.
        backend: The state backend providing storage.
    """

    def __init__(self, name: str, backend: Any = None) -> None:
        self.name = name
        self._backend = backend
        self._lists: Dict[Any, List[Any]] = defaultdict(list)

    def get(self, key: Any = None) -> List[Any]:
        """Get the list for the key."""
        return list(self._lists.get(key, []))

    def add(self, value: Any, key: Any = None) -> None:
        """Append a value to the list."""
        self._lists[key].append(value)

    def add_all(self, values: Iterable[Any], key: Any = None) -> None:
        """Append multiple values to the list."""
        self._lists[key].extend(values)

    def update(self, values: List[Any], key: Any = None) -> None:
        """Replace the entire list."""
        self._lists[key] = list(values)

    def clear(self, key: Any = None) -> None:
        """Clear the list for the key."""
        self._lists.pop(key, None)

    def snapshot(self) -> Dict[Any, List[Any]]:
        """Snapshot for checkpointing."""
        return {k: list(v) for k, v in self._lists.items()}

    def restore(self, state: Dict[Any, List[Any]]) -> None:
        """Restore from checkpoint."""
        self._lists = defaultdict(list)
        for k, v in state.items():
            self._lists[k] = list(v)


class MapState:
    """Key-value map per key.

    Provides dict-like operations on a per-key map stored in
    the state backend.

    Args:
        name: State descriptor name.
        backend: The state backend providing storage.
    """

    def __init__(self, name: str, backend: Any = None) -> None:
        self.name = name
        self._backend = backend
        self._maps: Dict[Any, Dict[Any, Any]] = defaultdict(dict)

    def get(self, map_key: Any, key: Any = None) -> Optional[Any]:
        """Get a value from the map."""
        return self._maps.get(key, {}).get(map_key)

    def put(self, map_key: Any, value: Any, key: Any = None) -> None:
        """Put a value into the map."""
        self._maps[key][map_key] = value

    def contains(self, map_key: Any, key: Any = None) -> bool:
        """Check if the map contains a key."""
        return map_key in self._maps.get(key, {})

    def remove(self, map_key: Any, key: Any = None) -> None:
        """Remove a value from the map."""
        self._maps.get(key, {}).pop(map_key, None)

    def keys(self, key: Any = None) -> List[Any]:
        """Get all keys in the map."""
        return list(self._maps.get(key, {}).keys())

    def values(self, key: Any = None) -> List[Any]:
        """Get all values in the map."""
        return list(self._maps.get(key, {}).values())

    def entries(self, key: Any = None) -> List[Tuple[Any, Any]]:
        """Get all entries as (key, value) tuples."""
        return list(self._maps.get(key, {}).items())

    def clear(self, key: Any = None) -> None:
        """Clear the map for the key."""
        self._maps.pop(key, None)

    def snapshot(self) -> Dict[Any, Dict[Any, Any]]:
        """Snapshot for checkpointing."""
        return {k: dict(v) for k, v in self._maps.items()}

    def restore(self, state: Dict[Any, Dict[Any, Any]]) -> None:
        """Restore from checkpoint."""
        self._maps = defaultdict(dict)
        for k, v in state.items():
            self._maps[k] = dict(v)


class ReducingState:
    """Single value per key with incremental reduce.

    Each call to add() applies the reduce function to combine
    the new value with the existing accumulated value.

    Args:
        name: State descriptor name.
        reduce_fn: Binary reduction function.
        backend: The state backend providing storage.
    """

    def __init__(self, name: str, reduce_fn: Callable[[Any, Any], Any],
                 backend: Any = None) -> None:
        self.name = name
        self.reduce_fn = reduce_fn
        self._backend = backend
        self._values: Dict[Any, Any] = {}

    def get(self, key: Any = None) -> Optional[Any]:
        """Get the current reduced value."""
        return self._values.get(key)

    def add(self, value: Any, key: Any = None) -> None:
        """Add a value, reducing with the existing accumulator."""
        if key in self._values:
            self._values[key] = self.reduce_fn(self._values[key], value)
        else:
            self._values[key] = value

    def clear(self, key: Any = None) -> None:
        """Clear the state for the key."""
        self._values.pop(key, None)

    def snapshot(self) -> Dict[Any, Any]:
        """Snapshot for checkpointing."""
        return dict(self._values)

    def restore(self, state: Dict[Any, Any]) -> None:
        """Restore from checkpoint."""
        self._values = dict(state)


class AggregatingState:
    """Accumulator per key with separate input/accumulator/output types.

    Combines the flexibility of AggregateFunction with per-key
    state management.

    Args:
        name: State descriptor name.
        agg_fn: The aggregate function defining the accumulator lifecycle.
        backend: The state backend providing storage.
    """

    def __init__(self, name: str, agg_fn: AggregateFunction,
                 backend: Any = None) -> None:
        self.name = name
        self.agg_fn = agg_fn
        self._backend = backend
        self._accumulators: Dict[Any, Any] = {}

    def get(self, key: Any = None) -> Optional[Any]:
        """Get the current output value."""
        acc = self._accumulators.get(key)
        if acc is None:
            return None
        return self.agg_fn.get_result(acc)

    def add(self, value: Any, key: Any = None) -> None:
        """Add a value to the accumulator."""
        if key not in self._accumulators:
            self._accumulators[key] = self.agg_fn.create_accumulator()
        self._accumulators[key] = self.agg_fn.add(self._accumulators[key], value)

    def clear(self, key: Any = None) -> None:
        """Clear the accumulator for the key."""
        self._accumulators.pop(key, None)

    def snapshot(self) -> Dict[Any, Any]:
        """Snapshot for checkpointing."""
        return dict(self._accumulators)

    def restore(self, state: Dict[Any, Any]) -> None:
        """Restore from checkpoint."""
        self._accumulators = dict(state)


# ============================================================
# State Backends
# ============================================================


class HashMapStateBackend:
    """In-memory keyed state stored in Python dict.

    Provides O(1) lookup for keyed state. State is serialized
    via pickle during checkpointing. Suitable for small to
    medium state sizes where durability is not required.
    """

    def __init__(self) -> None:
        self.backend_type = StateBackendType.HASHMAP
        self._state: Dict[str, Dict[Any, Any]] = defaultdict(dict)

    def get(self, state_name: str, key: Any) -> Optional[Any]:
        """Get a value from the state."""
        return self._state.get(state_name, {}).get(key)

    def put(self, state_name: str, key: Any, value: Any) -> None:
        """Put a value into the state."""
        self._state[state_name][key] = value

    def delete(self, state_name: str, key: Any) -> None:
        """Delete a value from the state."""
        self._state.get(state_name, {}).pop(key, None)

    def snapshot(self) -> bytes:
        """Serialize the entire state for checkpointing."""
        return pickle.dumps(dict(self._state))

    def restore(self, data: bytes) -> None:
        """Restore state from a checkpoint."""
        restored = pickle.loads(data)
        self._state = defaultdict(dict)
        self._state.update(restored)

    def state_size_bytes(self) -> int:
        """Estimate the current state size in bytes."""
        return len(pickle.dumps(dict(self._state)))

    def clear(self) -> None:
        """Clear all state."""
        self._state.clear()


class RocksDBStateBackend:
    """LSM-tree keyed state with sorted dict, write-ahead log, and compaction.

    Implements an LSM-tree-inspired state backend with:
    - Sorted in-memory write buffer (memtable)
    - Write-ahead log for durability
    - Level-based compaction when memtable reaches threshold
    - Block cache for frequently accessed entries
    - Configurable write buffer size, cache size, and compaction style

    This provides O(log N) read performance with efficient sequential
    writes, suitable for large state sizes that exceed available memory.

    Args:
        write_buffer_size: Maximum entries before flushing memtable.
        max_write_buffers: Maximum concurrent immutable memtables.
        block_cache_size: Maximum entries in the block cache.
        compaction_style: Compaction strategy ("leveled" or "universal").
    """

    def __init__(
        self,
        write_buffer_size: int = 1024,
        max_write_buffers: int = 3,
        block_cache_size: int = 512,
        compaction_style: str = "leveled",
    ) -> None:
        self.backend_type = StateBackendType.ROCKSDB
        self.write_buffer_size = write_buffer_size
        self.max_write_buffers = max_write_buffers
        self.block_cache_size = block_cache_size
        self.compaction_style = compaction_style

        # Memtable (active write buffer)
        self._memtable: Dict[str, Dict[Any, Any]] = defaultdict(dict)
        self._memtable_count: int = 0

        # Immutable memtables waiting for compaction
        self._immutable_memtables: List[Dict[str, Dict[Any, Any]]] = []

        # SST levels (sorted string tables)
        self._levels: List[Dict[str, Dict[Any, Any]]] = [defaultdict(dict)]

        # Write-ahead log
        self._wal: List[Tuple[str, str, Any, Any]] = []  # (op, state_name, key, value)

        # Block cache (LRU approximation)
        self._cache: Dict[Tuple[str, Any], Any] = {}
        self._cache_order: List[Tuple[str, Any]] = []

    def get(self, state_name: str, key: Any) -> Optional[Any]:
        """Get a value, checking memtable -> immutable -> levels -> cache."""
        # Check active memtable
        if state_name in self._memtable and key in self._memtable[state_name]:
            value = self._memtable[state_name][key]
            self._cache_put(state_name, key, value)
            return value

        # Check immutable memtables (newest first)
        for immutable in reversed(self._immutable_memtables):
            if state_name in immutable and key in immutable[state_name]:
                value = immutable[state_name][key]
                self._cache_put(state_name, key, value)
                return value

        # Check cache
        cache_key = (state_name, key)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check SST levels
        for level in self._levels:
            if state_name in level and key in level[state_name]:
                value = level[state_name][key]
                self._cache_put(state_name, key, value)
                return value

        return None

    def put(self, state_name: str, key: Any, value: Any) -> None:
        """Write to memtable with WAL entry."""
        self._wal.append(("put", state_name, key, value))
        self._memtable[state_name][key] = value
        self._memtable_count += 1
        self._cache_put(state_name, key, value)

        if self._memtable_count >= self.write_buffer_size:
            self._flush_memtable()

    def delete(self, state_name: str, key: Any) -> None:
        """Delete from memtable (tombstone write)."""
        self._wal.append(("delete", state_name, key, None))
        self._memtable[state_name].pop(key, None)
        self._cache.pop((state_name, key), None)

    def _flush_memtable(self) -> None:
        """Flush active memtable to immutable and trigger compaction."""
        self._immutable_memtables.append(self._memtable)
        self._memtable = defaultdict(dict)
        self._memtable_count = 0
        self._wal.clear()

        if len(self._immutable_memtables) >= self.max_write_buffers:
            self._compact()

    def _compact(self) -> None:
        """Merge immutable memtables into SST levels."""
        for immutable in self._immutable_memtables:
            for state_name, entries in immutable.items():
                for key, value in entries.items():
                    self._levels[0][state_name][key] = value
        self._immutable_memtables.clear()

    def _cache_put(self, state_name: str, key: Any, value: Any) -> None:
        """Update the block cache with LRU eviction."""
        cache_key = (state_name, key)
        self._cache[cache_key] = value
        if cache_key in self._cache_order:
            self._cache_order.remove(cache_key)
        self._cache_order.append(cache_key)
        while len(self._cache_order) > self.block_cache_size:
            evicted = self._cache_order.pop(0)
            self._cache.pop(evicted, None)

    def snapshot(self) -> bytes:
        """Serialize all state for checkpointing."""
        self._flush_memtable()
        self._compact()
        return pickle.dumps(dict(self._levels[0]))

    def restore(self, data: bytes) -> None:
        """Restore state from checkpoint."""
        restored = pickle.loads(data)
        self._memtable = defaultdict(dict)
        self._memtable_count = 0
        self._immutable_memtables.clear()
        self._levels = [defaultdict(dict)]
        self._wal.clear()
        self._cache.clear()
        self._cache_order.clear()
        for state_name, entries in restored.items():
            self._levels[0][state_name] = dict(entries)

    def state_size_bytes(self) -> int:
        """Estimate current state size."""
        total = defaultdict(dict)
        for level in self._levels:
            for state_name, entries in level.items():
                total[state_name].update(entries)
        for state_name, entries in self._memtable.items():
            total[state_name].update(entries)
        return len(pickle.dumps(dict(total)))

    def clear(self) -> None:
        """Clear all state."""
        self._memtable.clear()
        self._memtable_count = 0
        self._immutable_memtables.clear()
        self._levels = [defaultdict(dict)]
        self._wal.clear()
        self._cache.clear()
        self._cache_order.clear()


class StateTTL:
    """Time-to-live for keyed state entries.

    Provides lazy cleanup on access and proactive cleanup during
    compaction. Entries older than the configured TTL are considered
    expired and invisible to reads.

    Args:
        ttl_ms: Time-to-live in milliseconds (0 = disabled).
        update_type: When to refresh TTL ("on_create" or "on_read_and_write").
        cleanup_strategy: How to clean up expired entries
            ("incremental" or "full_snapshot").
    """

    def __init__(
        self,
        ttl_ms: int = 0,
        update_type: str = "on_read_and_write",
        cleanup_strategy: str = "incremental",
    ) -> None:
        self.ttl_ms = ttl_ms
        self.update_type = update_type
        self.cleanup_strategy = cleanup_strategy
        self._timestamps: Dict[Tuple[str, Any], float] = {}

    @property
    def enabled(self) -> bool:
        """Whether TTL is enabled."""
        return self.ttl_ms > 0

    def touch(self, state_name: str, key: Any) -> None:
        """Update the access timestamp for an entry."""
        self._timestamps[(state_name, key)] = time.time() * 1000

    def is_expired(self, state_name: str, key: Any) -> bool:
        """Check if an entry has exceeded its TTL."""
        if not self.enabled:
            return False
        ts = self._timestamps.get((state_name, key))
        if ts is None:
            return True
        return (time.time() * 1000 - ts) > self.ttl_ms

    def cleanup(self) -> List[Tuple[str, Any]]:
        """Return list of expired entries for removal."""
        if not self.enabled:
            return []
        now = time.time() * 1000
        expired = [
            (state_name, key)
            for (state_name, key), ts in self._timestamps.items()
            if (now - ts) > self.ttl_ms
        ]
        for entry in expired:
            self._timestamps.pop(entry, None)
        return expired


# ============================================================
# Stream Operators
# ============================================================


class StreamOperator(abc.ABC):
    """Abstract base class for all stream operators.

    Defines the operator lifecycle: open() -> process_element() /
    process_watermark() -> snapshot_state() / restore_state() -> close().
    """

    def __init__(self, uid: str = "", name: str = "", parallelism: int = 1) -> None:
        self.uid = uid or str(uuid.uuid4())[:8]
        self.name = name or self.__class__.__name__
        self.parallelism = parallelism
        self.chain_strategy = OperatorChainStrategy.DEFAULT
        self._output_collectors: List[Callable] = []
        self._metrics = OperatorMetrics(operator_uid=self.uid)
        self._current_watermark: int = -1

    def open(self) -> None:
        """Initialize the operator. Called once before processing."""
        pass

    @abc.abstractmethod
    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Process a single stream element."""
        ...

    def process_watermark(self, watermark: Watermark) -> Optional[Watermark]:
        """Process an incoming watermark. Default: forward unchanged."""
        self._current_watermark = watermark.timestamp
        return watermark

    def snapshot_state(self) -> Any:
        """Snapshot operator state for checkpointing."""
        return None

    def restore_state(self, state: Any) -> None:
        """Restore operator state from a checkpoint."""
        pass

    def close(self) -> None:
        """Clean up the operator. Called once after processing."""
        pass

    def get_descriptor(self) -> OperatorDescriptor:
        """Get the operator descriptor for the execution graph."""
        return OperatorDescriptor(
            uid=self.uid,
            name=self.name,
            operator_type=self.__class__.__name__,
            parallelism=self.parallelism,
            chain_strategy=self.chain_strategy,
        )


class MapOperator(StreamOperator):
    """Applies f: T -> R to each element. Stateless. Chainable.

    Args:
        map_fn: The mapping function.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, map_fn: Callable, uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "Map")
        self.map_fn = map_fn

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Apply the map function to the element."""
        result = self.map_fn(element.value)
        return [StreamElement(value=result, timestamp=element.timestamp, key=element.key)]


class FlatMapOperator(StreamOperator):
    """Applies f: T -> Iterable[R] to each element. Zero or more outputs.

    Args:
        flat_map_fn: The flat-mapping function.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, flat_map_fn: Callable, uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "FlatMap")
        self.flat_map_fn = flat_map_fn

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Apply the flat map function to the element."""
        results = self.flat_map_fn(element.value)
        return [
            StreamElement(value=r, timestamp=element.timestamp, key=element.key)
            for r in results
        ]


class FilterOperator(StreamOperator):
    """Forwards elements where predicate returns True. Stateless.

    Args:
        predicate: The filter predicate.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, predicate: Callable, uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "Filter")
        self.predicate = predicate

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Forward the element if the predicate is satisfied."""
        if self.predicate(element.value):
            return [element]
        return []


class KeyByOperator(StreamOperator):
    """Partitions stream by key extractor using murmur3 consistent hashing.

    After this operator, each element has its ``key`` field set to
    the extracted key, and its key group assignment is determined
    by murmur3 hashing for consistent partitioning.

    Args:
        key_extractor: Function extracting the partition key from element value.
        max_parallelism: Maximum parallelism for key group computation.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, key_extractor: Callable, max_parallelism: int = DEFAULT_MAX_PARALLELISM,
                 uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "KeyBy")
        self.key_extractor = key_extractor
        self.max_parallelism = max_parallelism

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Extract the key and assign key group."""
        key = self.key_extractor(element.value)
        key_group = _murmur3_32(key) % self.max_parallelism
        return [StreamElement(value=element.value, timestamp=element.timestamp, key=key)]

    def get_key_group(self, key: Any) -> int:
        """Compute the key group for a given key."""
        return _murmur3_32(key) % self.max_parallelism


class ReduceOperator(StreamOperator):
    """Binary reduction maintaining running aggregate per key.

    Applies a reduce function to maintain a running aggregate
    for each key in the keyed stream. The reduce function must
    be associative and commutative.

    Args:
        reduce_fn: Binary reduction function.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, reduce_fn: Callable, uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "Reduce")
        self.reduce_fn = reduce_fn
        self._state: Dict[Any, Any] = {}

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Reduce the element with the running aggregate."""
        key = element.key
        if key in self._state:
            self._state[key] = self.reduce_fn(self._state[key], element.value)
        else:
            self._state[key] = element.value
        return [StreamElement(value=self._state[key], timestamp=element.timestamp, key=key)]

    def snapshot_state(self) -> Any:
        """Snapshot the running aggregates."""
        return dict(self._state)

    def restore_state(self, state: Any) -> None:
        """Restore running aggregates from checkpoint."""
        self._state = dict(state) if state else {}


class ProcessOperator(StreamOperator):
    """General-purpose operator with access to keyed state and timers.

    The ProcessOperator provides the most flexible stream processing
    API, with access to the current key, keyed state descriptors,
    timer registration for event-time and processing-time callbacks,
    side outputs, and watermark information.

    Args:
        process_fn: Function (element, ctx) -> List[output].
        on_timer_fn: Optional timer callback (timestamp, ctx) -> List[output].
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(
        self,
        process_fn: Callable,
        on_timer_fn: Optional[Callable] = None,
        uid: str = "",
        name: str = "",
    ) -> None:
        super().__init__(uid=uid, name=name or "Process")
        self.process_fn = process_fn
        self.on_timer_fn = on_timer_fn
        self._state: Dict[str, Any] = {}
        self._timers: List[Tuple[int, str]] = []  # (timestamp, timer_type)

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Process with access to context."""
        ctx = ProcessContext(
            current_key=element.key,
            current_watermark=self._current_watermark,
            state=self._state,
            timers=self._timers,
        )
        results = self.process_fn(element, ctx)
        if results is None:
            return []
        return [
            StreamElement(value=r, timestamp=element.timestamp, key=element.key)
            for r in results
        ]

    def fire_timers(self, current_time: int) -> List[StreamElement]:
        """Fire all timers that have been triggered."""
        if not self.on_timer_fn:
            return []
        fired = []
        remaining = []
        for ts, timer_type in self._timers:
            if ts <= current_time:
                ctx = ProcessContext(
                    current_key=None,
                    current_watermark=self._current_watermark,
                    state=self._state,
                    timers=remaining,
                )
                results = self.on_timer_fn(ts, ctx)
                if results:
                    fired.extend(
                        StreamElement(value=r, timestamp=ts)
                        for r in results
                    )
            else:
                remaining.append((ts, timer_type))
        self._timers = remaining
        return fired

    def snapshot_state(self) -> Any:
        """Snapshot state and timers."""
        return {"state": dict(self._state), "timers": list(self._timers)}

    def restore_state(self, state: Any) -> None:
        """Restore state and timers."""
        if state:
            self._state = dict(state.get("state", {}))
            self._timers = list(state.get("timers", []))


class UnionOperator(StreamOperator):
    """Merges two or more streams without deduplication or ordering.

    Args:
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "Union")

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Forward the element unchanged."""
        return [element]


# ============================================================
# Process Context
# ============================================================


class ProcessContext:
    """Context object passed to ProcessOperator.

    Provides access to the current key, keyed state, timer
    registration, side output, and watermark information.
    """

    def __init__(
        self,
        current_key: Any = None,
        current_watermark: int = -1,
        state: Optional[Dict[str, Any]] = None,
        timers: Optional[List[Tuple[int, str]]] = None,
    ) -> None:
        self.current_key = current_key
        self._current_watermark = current_watermark
        self._state = state if state is not None else {}
        self._timers = timers if timers is not None else []
        self._side_outputs: Dict[str, List[Any]] = defaultdict(list)

    def get_state(self, name: str) -> Any:
        """Get a keyed state value."""
        return self._state.get(name)

    def update_state(self, name: str, value: Any) -> None:
        """Update a keyed state value."""
        self._state[name] = value

    def register_event_time_timer(self, timestamp: int) -> None:
        """Register a timer to fire when the event-time watermark passes."""
        self._timers.append((timestamp, "event_time"))

    def register_processing_time_timer(self, timestamp: int) -> None:
        """Register a timer to fire at wall-clock time."""
        self._timers.append((timestamp, "processing_time"))

    def output(self, tag: str, value: Any) -> None:
        """Emit a value to a side output."""
        self._side_outputs[tag].append(value)

    def current_watermark(self) -> int:
        """Get the current watermark timestamp."""
        return self._current_watermark


# ============================================================
# Source Operators
# ============================================================


class MessageQueueSource(StreamOperator):
    """Reads from message queue topic partitions.

    Tracks committed offsets per partition, emits watermarks from
    message timestamps, and reports offsets during checkpointing
    for exactly-once source guarantees.

    Args:
        topic: The topic to consume from.
        partitions: Number of partitions to consume.
        start_position: Where to start reading.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(
        self,
        topic: str = STREAM_TOPIC_EVALUATIONS,
        partitions: int = 4,
        start_position: SourceStartPosition = SourceStartPosition.LATEST,
        uid: str = "",
        name: str = "",
    ) -> None:
        super().__init__(uid=uid, name=name or f"MQSource[{topic}]")
        self.topic = topic
        self.partitions = partitions
        self.start_position = start_position
        self._offsets: Dict[int, int] = {p: 0 for p in range(partitions)}
        self._watermark_strategy: Optional[Any] = None

    def set_watermark_strategy(self, strategy: Any) -> None:
        """Configure the watermark generation strategy."""
        self._watermark_strategy = strategy

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Process a message from the queue."""
        if self._watermark_strategy and hasattr(self._watermark_strategy, "on_event"):
            self._watermark_strategy.on_event(element.timestamp)
        return [element]

    def commit_offset(self, partition: int, offset: int) -> None:
        """Commit the consumed offset for a partition."""
        self._offsets[partition] = offset

    def snapshot_state(self) -> Any:
        """Snapshot committed offsets for checkpointing."""
        return dict(self._offsets)

    def restore_state(self, state: Any) -> None:
        """Restore committed offsets from checkpoint."""
        if state:
            self._offsets = dict(state)


class EventStoreSource(StreamOperator):
    """Tails the EventStore journal as a continuous stream.

    Reads domain events from the event sourcing journal, emitting
    each event as a stream element. Tracks the last consumed
    sequence number for exactly-once checkpointing.

    Args:
        stream_name: The event store stream to tail.
        start_position: Where to start reading.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(
        self,
        stream_name: str = "fizzbuzz-events",
        start_position: SourceStartPosition = SourceStartPosition.LATEST,
        uid: str = "",
        name: str = "",
    ) -> None:
        super().__init__(uid=uid, name=name or f"ESSource[{stream_name}]")
        self.stream_name = stream_name
        self.start_position = start_position
        self._last_sequence: int = 0

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Process an event from the journal."""
        self._last_sequence += 1
        return [element]

    def snapshot_state(self) -> Any:
        """Snapshot last consumed sequence number."""
        return {"last_sequence": self._last_sequence}

    def restore_state(self, state: Any) -> None:
        """Restore last consumed sequence number."""
        if state:
            self._last_sequence = state.get("last_sequence", 0)


class ContainerEventSource(StreamOperator):
    """Reads container lifecycle events from FizzContainerd.

    Tails the containerd event service for container create, start,
    stop, and delete events, converting them to stream elements
    for downstream processing.

    Args:
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "ContainerEventSource")
        self._event_count: int = 0

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Process a container lifecycle event."""
        self._event_count += 1
        return [element]


class MetricSource(StreamOperator):
    """Reads metric emissions from OpenTelemetry collector.

    Ingests continuous metric data points from the OpenTelemetry
    collector, converting each metric emission into a stream
    element with the metric name, value, and labels as payload.

    Args:
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or "MetricSource")
        self._metric_count: int = 0

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Process a metric emission."""
        self._metric_count += 1
        return [element]


class GeneratorSource(StreamOperator):
    """Synthetic source generating events from a user-defined function.

    Supports bounded and unbounded modes. In bounded mode, the
    generator produces a fixed number of elements. In unbounded
    mode, it produces elements indefinitely (useful for testing
    and benchmarking).

    Args:
        generator_fn: Function (index) -> element_value.
        num_elements: Number of elements to produce (None = unbounded).
        rate_per_second: Maximum element emission rate.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(
        self,
        generator_fn: Callable[[int], Any],
        num_elements: Optional[int] = None,
        rate_per_second: float = 0,
        uid: str = "",
        name: str = "",
    ) -> None:
        super().__init__(uid=uid, name=name or "GeneratorSource")
        self.generator_fn = generator_fn
        self.num_elements = num_elements
        self.rate_per_second = rate_per_second
        self._generated_count: int = 0

    @property
    def is_bounded(self) -> bool:
        """Whether this is a bounded source."""
        return self.num_elements is not None

    def generate(self) -> Optional[StreamElement]:
        """Generate the next element."""
        if self.num_elements is not None and self._generated_count >= self.num_elements:
            return None
        value = self.generator_fn(self._generated_count)
        self._generated_count += 1
        return StreamElement(value=value, timestamp=int(time.time() * 1000))

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Forward generated elements."""
        return [element]


# ============================================================
# Sink Operators
# ============================================================


class MessageQueueSink(StreamOperator):
    """Writes stream results to message queue topic partitions.

    Uses the message queue's idempotency layer for exactly-once
    production. Elements are serialized and published to the
    configured topic with key-based partitioning.

    Args:
        topic: The target topic.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, topic: str = STREAM_TOPIC_EVALUATIONS,
                 uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or f"MQSink[{topic}]")
        self.topic = topic
        self._produced_count: int = 0
        self._buffer: List[StreamElement] = []

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Buffer element for production."""
        self._buffer.append(element)
        self._produced_count += 1
        return []  # Sinks do not emit downstream

    def flush(self) -> int:
        """Flush buffered elements to the topic."""
        count = len(self._buffer)
        self._buffer.clear()
        return count


class EventStoreSink(StreamOperator):
    """Appends computed stream results as domain events.

    Writes each stream result to the event store as a domain
    event, enabling downstream event sourcing consumers to
    react to stream processing results.

    Args:
        stream_name: The target event store stream.
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(self, stream_name: str = "fizzbuzz-stream-results",
                 uid: str = "", name: str = "") -> None:
        super().__init__(uid=uid, name=name or f"ESSink[{stream_name}]")
        self.stream_name = stream_name
        self._appended_count: int = 0

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Append element to event store."""
        self._appended_count += 1
        return []


# ============================================================
# Checkpointing
# ============================================================


class CheckpointBarrier:
    """Special stream element for checkpoint synchronization.

    Injected by the CheckpointCoordinator at source operators
    and propagated through the operator graph. When all inputs
    of an operator have received barriers for the same checkpoint
    ID, the operator snapshots its state and forwards the barrier.

    Args:
        checkpoint_id: The checkpoint identifier.
        timestamp: When the barrier was injected.
    """

    def __init__(self, checkpoint_id: int, timestamp: float = 0.0) -> None:
        self.checkpoint_id = checkpoint_id
        self.timestamp = timestamp or time.time()

    def __repr__(self) -> str:
        return f"CheckpointBarrier(id={self.checkpoint_id})"


class InMemoryCheckpointStorage:
    """Stores checkpoints in Python dictionary.

    Fast but not durable. Suitable for testing and development
    environments where checkpoint persistence is not required.
    """

    def __init__(self, max_retained: int = DEFAULT_CHECKPOINT_RETENTION) -> None:
        self.max_retained = max_retained
        self._checkpoints: Dict[int, Dict[str, Any]] = {}
        self._metadata: Dict[int, CheckpointMetadata] = {}

    def store(self, checkpoint_id: int, operator_uid: str, state: Any) -> str:
        """Store operator state for a checkpoint."""
        if checkpoint_id not in self._checkpoints:
            self._checkpoints[checkpoint_id] = {}
        location = f"memory://{checkpoint_id}/{operator_uid}"
        self._checkpoints[checkpoint_id][operator_uid] = state
        return location

    def load(self, checkpoint_id: int, operator_uid: str) -> Any:
        """Load operator state from a checkpoint."""
        return self._checkpoints.get(checkpoint_id, {}).get(operator_uid)

    def complete(self, metadata: CheckpointMetadata) -> None:
        """Mark a checkpoint as complete and enforce retention."""
        self._metadata[metadata.checkpoint_id] = metadata
        self._enforce_retention()

    def get_latest(self) -> Optional[CheckpointMetadata]:
        """Get the latest completed checkpoint."""
        completed = [
            m for m in self._metadata.values()
            if m.status == CheckpointStatus.COMPLETED
        ]
        if not completed:
            return None
        return max(completed, key=lambda m: m.checkpoint_id)

    def _enforce_retention(self) -> None:
        """Remove old checkpoints beyond retention limit."""
        completed_ids = sorted(
            cid for cid, m in self._metadata.items()
            if m.status == CheckpointStatus.COMPLETED
        )
        while len(completed_ids) > self.max_retained:
            old_id = completed_ids.pop(0)
            self._checkpoints.pop(old_id, None)
            self._metadata.pop(old_id, None)


class FileSystemCheckpointStorage:
    """Stores checkpoints to the virtual filesystem.

    Durable checkpoint storage that persists state to the FizzVFS.
    Since the virtual filesystem is itself an in-memory simulation,
    this provides the abstraction of durable storage without
    requiring actual disk I/O.

    Args:
        base_path: Base directory for checkpoint files.
        max_retained: Maximum checkpoints to retain.
    """

    def __init__(self, base_path: str = "/checkpoints/fizzstream",
                 max_retained: int = DEFAULT_CHECKPOINT_RETENTION) -> None:
        self.base_path = base_path
        self.max_retained = max_retained
        self._storage: Dict[str, Any] = {}
        self._metadata: Dict[int, CheckpointMetadata] = {}

    def store(self, checkpoint_id: int, operator_uid: str, state: Any) -> str:
        """Store operator state to a virtual file."""
        location = f"{self.base_path}/{checkpoint_id}/{operator_uid}.state"
        self._storage[location] = state
        return location

    def load(self, checkpoint_id: int, operator_uid: str) -> Any:
        """Load operator state from a virtual file."""
        location = f"{self.base_path}/{checkpoint_id}/{operator_uid}.state"
        return self._storage.get(location)

    def complete(self, metadata: CheckpointMetadata) -> None:
        """Mark a checkpoint as complete."""
        self._metadata[metadata.checkpoint_id] = metadata
        self._enforce_retention()

    def get_latest(self) -> Optional[CheckpointMetadata]:
        """Get the latest completed checkpoint."""
        completed = [
            m for m in self._metadata.values()
            if m.status == CheckpointStatus.COMPLETED
        ]
        if not completed:
            return None
        return max(completed, key=lambda m: m.checkpoint_id)

    def _enforce_retention(self) -> None:
        """Remove old checkpoint files beyond retention limit."""
        completed_ids = sorted(
            cid for cid, m in self._metadata.items()
            if m.status == CheckpointStatus.COMPLETED
        )
        while len(completed_ids) > self.max_retained:
            old_id = completed_ids.pop(0)
            prefix = f"{self.base_path}/{old_id}/"
            to_remove = [k for k in self._storage if k.startswith(prefix)]
            for k in to_remove:
                del self._storage[k]
            self._metadata.pop(old_id, None)


class CheckpointCoordinator:
    """Orchestrates periodic Chandy-Lamport distributed snapshots.

    Injects checkpoint barriers into source operators, collects
    state acknowledgments from all operators, records checkpoint
    metadata, and coordinates recovery from the latest successful
    checkpoint on failure.

    Args:
        interval_ms: Checkpoint interval in milliseconds.
        state_backend: The state backend for operator state.
        storage: The checkpoint storage backend.
        retention: Number of checkpoints to retain.
    """

    def __init__(
        self,
        interval_ms: int = DEFAULT_CHECKPOINT_INTERVAL_MS,
        state_backend: Any = None,
        storage: Any = None,
        retention: int = DEFAULT_CHECKPOINT_RETENTION,
    ) -> None:
        self.interval_ms = interval_ms
        self.state_backend = state_backend
        self.storage = storage or InMemoryCheckpointStorage(retention)
        self.retention = retention
        self._next_checkpoint_id: int = 1
        self._pending_barriers: Dict[int, Set[str]] = {}
        self._completed_checkpoints: List[CheckpointMetadata] = []
        self._lock = threading.Lock()

    def trigger_checkpoint(self, operators: List[StreamOperator]) -> CheckpointBarrier:
        """Initiate a new checkpoint by injecting barriers."""
        with self._lock:
            checkpoint_id = self._next_checkpoint_id
            self._next_checkpoint_id += 1

        barrier = CheckpointBarrier(checkpoint_id=checkpoint_id)
        self._pending_barriers[checkpoint_id] = {op.uid for op in operators}

        logger.debug(
            "Checkpoint %d initiated with %d operators",
            checkpoint_id, len(operators),
        )
        return barrier

    def acknowledge(self, checkpoint_id: int, operator: StreamOperator) -> Optional[CheckpointMetadata]:
        """Acknowledge that an operator has completed its snapshot.

        Returns CheckpointMetadata if all operators have acknowledged.
        """
        pending = self._pending_barriers.get(checkpoint_id)
        if pending is None:
            return None

        # Store operator state
        state = operator.snapshot_state()
        location = self.storage.store(checkpoint_id, operator.uid, state)

        pending.discard(operator.uid)

        if not pending:
            # All operators acknowledged - checkpoint complete
            del self._pending_barriers[checkpoint_id]
            metadata = CheckpointMetadata(
                checkpoint_id=checkpoint_id,
                timestamp=time.time(),
                duration_ms=0,
                operator_states={operator.uid: location},
                state_size_bytes=0,
                status=CheckpointStatus.COMPLETED,
            )
            self.storage.complete(metadata)
            self._completed_checkpoints.append(metadata)
            logger.debug("Checkpoint %d completed", checkpoint_id)
            return metadata

        return None

    def get_latest_checkpoint(self) -> Optional[CheckpointMetadata]:
        """Get the latest successful checkpoint."""
        return self.storage.get_latest()

    def restore_from_checkpoint(self, checkpoint_id: int,
                                operators: List[StreamOperator]) -> bool:
        """Restore all operators from a checkpoint."""
        for operator in operators:
            state = self.storage.load(checkpoint_id, operator.uid)
            if state is not None:
                operator.restore_state(state)
        logger.info("Restored %d operators from checkpoint %d",
                     len(operators), checkpoint_id)
        return True


# ============================================================
# Restart Strategies
# ============================================================


class FixedDelayRestartStrategy:
    """Restarts with fixed delay between attempts.

    Args:
        max_restarts: Maximum number of restart attempts.
        delay_ms: Delay between restart attempts in milliseconds.
    """

    def __init__(self, max_restarts: int = DEFAULT_RESTART_ATTEMPTS,
                 delay_ms: int = DEFAULT_RESTART_DELAY_MS) -> None:
        self.max_restarts = max_restarts
        self.delay_ms = delay_ms
        self.strategy_type = RestartStrategyType.FIXED_DELAY
        self._restart_count: int = 0

    def can_restart(self) -> bool:
        """Check if another restart is allowed."""
        return self._restart_count < self.max_restarts

    def get_delay_ms(self) -> int:
        """Get the delay before the next restart."""
        return self.delay_ms

    def record_restart(self) -> None:
        """Record a restart attempt."""
        self._restart_count += 1

    def reset(self) -> None:
        """Reset the restart counter."""
        self._restart_count = 0


class ExponentialBackoffRestartStrategy:
    """Restarts with exponentially increasing delays.

    Args:
        initial_delay_ms: Initial delay before first restart.
        max_delay_ms: Maximum delay cap.
        backoff_multiplier: Delay multiplication factor per attempt.
        max_restarts: Maximum number of restart attempts.
    """

    def __init__(
        self,
        initial_delay_ms: int = DEFAULT_BACKOFF_INITIAL_MS,
        max_delay_ms: int = DEFAULT_BACKOFF_MAX_MS,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        max_restarts: int = DEFAULT_RESTART_ATTEMPTS,
    ) -> None:
        self.initial_delay_ms = initial_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backoff_multiplier = backoff_multiplier
        self.max_restarts = max_restarts
        self.strategy_type = RestartStrategyType.EXPONENTIAL_BACKOFF
        self._restart_count: int = 0

    def can_restart(self) -> bool:
        """Check if another restart is allowed."""
        return self._restart_count < self.max_restarts

    def get_delay_ms(self) -> int:
        """Get the delay with exponential backoff."""
        delay = self.initial_delay_ms * (self.backoff_multiplier ** self._restart_count)
        return int(min(delay, self.max_delay_ms))

    def record_restart(self) -> None:
        """Record a restart attempt."""
        self._restart_count += 1

    def reset(self) -> None:
        """Reset the restart counter."""
        self._restart_count = 0


class NoRestartStrategy:
    """Fail immediately without restart."""

    def __init__(self) -> None:
        self.strategy_type = RestartStrategyType.NO_RESTART

    def can_restart(self) -> bool:
        """No restarts are ever allowed."""
        return False

    def get_delay_ms(self) -> int:
        """No delay (never used)."""
        return 0

    def record_restart(self) -> None:
        """No-op."""
        pass

    def reset(self) -> None:
        """No-op."""
        pass


# ============================================================
# Stream Joins
# ============================================================


class StreamStreamJoin:
    """Joins two keyed streams within a time-bounded window.

    Maintains buffer state for both input streams and produces
    matches when elements from both sides have the same key and
    fall within the specified time window.

    Args:
        left_window_ms: Time window for buffering left-side elements.
        right_window_ms: Time window for buffering right-side elements.
        join_type: Type of join to perform.
    """

    def __init__(
        self,
        left_window_ms: int = 60000,
        right_window_ms: int = 60000,
        join_type: JoinType = JoinType.INNER,
    ) -> None:
        self.left_window_ms = left_window_ms
        self.right_window_ms = right_window_ms
        self.join_type = join_type
        self._left_buffer: Dict[Any, List[Tuple[int, Any]]] = defaultdict(list)
        self._right_buffer: Dict[Any, List[Tuple[int, Any]]] = defaultdict(list)

    def process_left(self, element: StreamElement) -> List[Tuple[Any, Any]]:
        """Process an element from the left stream."""
        key = element.key
        self._left_buffer[key].append((element.timestamp, element.value))
        matches = []

        for ts, right_value in self._right_buffer.get(key, []):
            if abs(element.timestamp - ts) <= self.right_window_ms:
                matches.append((element.value, right_value))

        if not matches and self.join_type in (JoinType.LEFT_OUTER, JoinType.FULL_OUTER):
            matches.append((element.value, None))

        return matches

    def process_right(self, element: StreamElement) -> List[Tuple[Any, Any]]:
        """Process an element from the right stream."""
        key = element.key
        self._right_buffer[key].append((element.timestamp, element.value))
        matches = []

        for ts, left_value in self._left_buffer.get(key, []):
            if abs(element.timestamp - ts) <= self.left_window_ms:
                matches.append((left_value, element.value))

        if not matches and self.join_type in (JoinType.RIGHT_OUTER, JoinType.FULL_OUTER):
            matches.append((None, element.value))

        return matches

    def cleanup(self, current_watermark: int) -> None:
        """Remove expired elements from buffers."""
        for key in list(self._left_buffer.keys()):
            self._left_buffer[key] = [
                (ts, v) for ts, v in self._left_buffer[key]
                if current_watermark - ts <= self.left_window_ms
            ]
            if not self._left_buffer[key]:
                del self._left_buffer[key]
        for key in list(self._right_buffer.keys()):
            self._right_buffer[key] = [
                (ts, v) for ts, v in self._right_buffer[key]
                if current_watermark - ts <= self.right_window_ms
            ]
            if not self._right_buffer[key]:
                del self._right_buffer[key]


class StreamTableJoin:
    """Joins stream against a slowly-changing lookup table.

    The table is materialized from upsert events. The join performs
    a temporal lookup at event time, returning the table row that
    was current when the stream event occurred.

    Args:
        table_name: Name of the materialized table.
    """

    def __init__(self, table_name: str = "lookup") -> None:
        self.table_name = table_name
        self._table: Dict[Any, Tuple[int, Any]] = {}  # key -> (timestamp, value)

    def upsert(self, key: Any, value: Any, timestamp: int) -> None:
        """Update the materialized table."""
        existing = self._table.get(key)
        if existing is None or timestamp >= existing[0]:
            self._table[key] = (timestamp, value)

    def lookup(self, key: Any, timestamp: int) -> Optional[Any]:
        """Look up the table value current at the given timestamp."""
        entry = self._table.get(key)
        if entry is None:
            return None
        if entry[0] <= timestamp:
            return entry[1]
        return None

    def join(self, element: StreamElement) -> Optional[Tuple[Any, Any]]:
        """Join a stream element against the table."""
        table_value = self.lookup(element.key, element.timestamp)
        if table_value is not None:
            return (element.value, table_value)
        return None


class IntervalJoin:
    """Specialized asymmetric time-bounded join.

    Joins elements from two keyed streams where the left element's
    timestamp falls within [right.timestamp + lower_bound,
    right.timestamp + upper_bound].

    Args:
        lower_bound_ms: Lower bound offset in milliseconds (can be negative).
        upper_bound_ms: Upper bound offset in milliseconds.
    """

    def __init__(self, lower_bound_ms: int = -60000,
                 upper_bound_ms: int = 60000) -> None:
        self.lower_bound_ms = lower_bound_ms
        self.upper_bound_ms = upper_bound_ms
        self._left_buffer: Dict[Any, List[Tuple[int, Any]]] = defaultdict(list)
        self._right_buffer: Dict[Any, List[Tuple[int, Any]]] = defaultdict(list)

    def process_left(self, element: StreamElement) -> List[Tuple[Any, Any]]:
        """Process an element from the left stream."""
        key = element.key
        self._left_buffer[key].append((element.timestamp, element.value))
        matches = []
        for ts, right_value in self._right_buffer.get(key, []):
            lower = ts + self.lower_bound_ms
            upper = ts + self.upper_bound_ms
            if lower <= element.timestamp <= upper:
                matches.append((element.value, right_value))
        return matches

    def process_right(self, element: StreamElement) -> List[Tuple[Any, Any]]:
        """Process an element from the right stream."""
        key = element.key
        self._right_buffer[key].append((element.timestamp, element.value))
        matches = []
        for ts, left_value in self._left_buffer.get(key, []):
            lower = element.timestamp + self.lower_bound_ms
            upper = element.timestamp + self.upper_bound_ms
            if lower <= ts <= upper:
                matches.append((left_value, element.value))
        return matches


# ============================================================
# Complex Event Processing (CEP)
# ============================================================


class PatternElement:
    """Single stage in a pattern.

    Represents one condition in a CEP pattern sequence with a name,
    condition predicate, and quantifier controlling how many events
    can match at this stage.

    Args:
        name: Stage name (used in match result mapping).
        condition: Predicate that events must satisfy.
        quantifier: How many events can match ("one", "one_or_more",
            "times", "optional").
        times_value: Exact repetition count for "times" quantifier.
    """

    def __init__(
        self,
        name: str,
        condition: Optional[Callable[[Any], bool]] = None,
        quantifier: str = "one",
        times_value: int = 1,
    ) -> None:
        self.name = name
        self.condition = condition
        self.quantifier = quantifier
        self.times_value = times_value
        self.contiguity = Contiguity.STRICT


class Pattern:
    """Declarative specification of event sequences.

    Provides a fluent API for building complex event patterns:
    begin() -> where() -> followed_by() -> followed_by_any() ->
    not_followed_by() -> within().

    Args:
        name: Pattern name.
    """

    def __init__(self, name: str = "pattern") -> None:
        self.name = name
        self.elements: List[PatternElement] = []
        self.within_ms: Optional[int] = None
        self._current_element: Optional[PatternElement] = None

    @classmethod
    def begin(cls, name: str) -> "Pattern":
        """Start a new pattern with the first element."""
        pattern = cls(name=name)
        element = PatternElement(name=name)
        pattern.elements.append(element)
        pattern._current_element = element
        return pattern

    def where(self, condition: Callable[[Any], bool]) -> "Pattern":
        """Add a condition to the current element."""
        if self._current_element:
            self._current_element.condition = condition
        return self

    def followed_by(self, name: str) -> "Pattern":
        """Add a strict contiguity element."""
        element = PatternElement(name=name)
        element.contiguity = Contiguity.STRICT
        self.elements.append(element)
        self._current_element = element
        return self

    def followed_by_any(self, name: str) -> "Pattern":
        """Add a relaxed contiguity element."""
        element = PatternElement(name=name)
        element.contiguity = Contiguity.RELAXED
        self.elements.append(element)
        self._current_element = element
        return self

    def not_followed_by(self, name: str) -> "Pattern":
        """Add a negation element."""
        element = PatternElement(name=name)
        element.contiguity = Contiguity.STRICT
        element.quantifier = "not"
        self.elements.append(element)
        self._current_element = element
        return self

    def times(self, count: int) -> "Pattern":
        """Set exact repetition for the current element."""
        if self._current_element:
            self._current_element.quantifier = "times"
            self._current_element.times_value = count
        return self

    def times_or_more(self, count: int) -> "Pattern":
        """Set minimum repetition for the current element."""
        if self._current_element:
            self._current_element.quantifier = "times_or_more"
            self._current_element.times_value = count
        return self

    def one_or_more(self) -> "Pattern":
        """Allow one or more matches at the current element."""
        if self._current_element:
            self._current_element.quantifier = "one_or_more"
        return self

    def optional(self) -> "Pattern":
        """Make the current element optional."""
        if self._current_element:
            self._current_element.quantifier = "optional"
        return self

    def within(self, duration_ms: int) -> "Pattern":
        """Set a maximum duration for the entire pattern match."""
        self.within_ms = duration_ms
        return self


class NFACompiler:
    """Compiles a Pattern into an NFA for efficient matching.

    Translates the declarative pattern specification into a
    nondeterministic finite automaton with states, transitions,
    and self-loops for quantifiers.

    Args:
        pattern: The pattern to compile.
    """

    def __init__(self, pattern: Pattern) -> None:
        self.pattern = pattern
        self.states: List[NFAState] = []

    def compile(self) -> List[NFAState]:
        """Compile the pattern into NFA states."""
        if not self.pattern.elements:
            raise CEPPatternError(self.pattern.name, "Pattern has no elements")

        self.states = []

        for i, element in enumerate(self.pattern.elements):
            if i == 0:
                state_type = NFAStateType.START
            else:
                state_type = NFAStateType.NORMAL

            state = NFAState(
                name=element.name,
                state_type=state_type,
                condition=element.condition,
                self_loop=(element.quantifier in ("one_or_more", "times_or_more")),
            )

            # Add transition to next state
            if i + 1 < len(self.pattern.elements):
                next_name = self.pattern.elements[i + 1].name
                state.transitions[next_name] = self.pattern.elements[i + 1].condition

            self.states.append(state)

        # Add final state
        final_state = NFAState(
            name="__final__",
            state_type=NFAStateType.FINAL,
        )
        if self.states:
            self.states[-1].transitions["__final__"] = None
        self.states.append(final_state)

        return self.states


class CEPOperator(StreamOperator):
    """Stateful operator running compiled NFA against event stream.

    Maintains partial match state across events and completes or
    times out matches based on NFA transitions and the pattern's
    within() constraint.

    Args:
        nfa_states: Compiled NFA states from NFACompiler.
        within_ms: Maximum match duration (from pattern.within()).
        uid: Stable operator UID.
        name: Human-readable name.
    """

    def __init__(
        self,
        nfa_states: List[NFAState],
        within_ms: Optional[int] = None,
        uid: str = "",
        name: str = "",
    ) -> None:
        super().__init__(uid=uid, name=name or "CEPOperator")
        self.nfa_states = nfa_states
        self.within_ms = within_ms
        self._partial_matches: List[PartialMatch] = []
        self._completed_matches: List[Dict[str, List[Any]]] = []
        self._timed_out_matches: List[Dict[str, List[Any]]] = []
        self._version_counter: int = 0

    def process_element(self, element: StreamElement) -> List[StreamElement]:
        """Advance partial matches and start new matches."""
        # Start new match at START state
        start_state = next(
            (s for s in self.nfa_states if s.state_type == NFAStateType.START),
            None,
        )
        if start_state and (start_state.condition is None or start_state.condition(element.value)):
            self._version_counter += 1
            pm = PartialMatch(
                current_state=start_state.name,
                matched_events={start_state.name: [element.value]},
                start_timestamp=element.timestamp,
                version=self._version_counter,
            )
            self._partial_matches.append(pm)

        # Advance existing partial matches
        new_partials = []
        for pm in self._partial_matches:
            current_nfa = next(
                (s for s in self.nfa_states if s.name == pm.current_state),
                None,
            )
            if current_nfa is None:
                continue

            # Check transitions
            for target_name, target_cond in current_nfa.transitions.items():
                if target_cond is None or target_cond(element.value):
                    self._version_counter += 1
                    new_pm = PartialMatch(
                        current_state=target_name,
                        matched_events={
                            k: list(v) for k, v in pm.matched_events.items()
                        },
                        start_timestamp=pm.start_timestamp,
                        version=self._version_counter,
                    )
                    if target_name not in new_pm.matched_events:
                        new_pm.matched_events[target_name] = []
                    new_pm.matched_events[target_name].append(element.value)
                    new_partials.append(new_pm)

            # Self-loop
            if current_nfa.self_loop:
                if current_nfa.condition is None or current_nfa.condition(element.value):
                    pm.matched_events.setdefault(pm.current_state, []).append(element.value)
                    new_partials.append(pm)

        # Check for completed and timed-out matches
        active = []
        for pm in new_partials:
            target_state = next(
                (s for s in self.nfa_states if s.name == pm.current_state),
                None,
            )
            if target_state and target_state.state_type == NFAStateType.FINAL:
                self._completed_matches.append(pm.matched_events)
            elif (self.within_ms is not None and
                  element.timestamp - pm.start_timestamp > self.within_ms):
                self._timed_out_matches.append(pm.matched_events)
            else:
                active.append(pm)

        self._partial_matches = active

        # Emit completed matches as stream elements
        results = []
        while self._completed_matches:
            match = self._completed_matches.pop(0)
            results.append(StreamElement(
                value={"match": match, "pattern": "cep_match"},
                timestamp=element.timestamp,
                key=element.key,
            ))
        return results

    def get_timed_out_matches(self) -> List[Dict[str, List[Any]]]:
        """Retrieve and clear timed-out matches."""
        timed_out = list(self._timed_out_matches)
        self._timed_out_matches.clear()
        return timed_out

    def snapshot_state(self) -> Any:
        """Snapshot partial match state."""
        return {
            "partial_matches": [
                {
                    "current_state": pm.current_state,
                    "matched_events": pm.matched_events,
                    "start_timestamp": pm.start_timestamp,
                    "version": pm.version,
                }
                for pm in self._partial_matches
            ],
            "version_counter": self._version_counter,
        }

    def restore_state(self, state: Any) -> None:
        """Restore partial match state."""
        if state:
            self._partial_matches = [
                PartialMatch(**pm_data)
                for pm_data in state.get("partial_matches", [])
            ]
            self._version_counter = state.get("version_counter", 0)


class PatternStream:
    """Result of applying a Pattern to a DataStream.

    Provides methods to extract completed matches and timed-out
    matches from the CEP operator.
    """

    def __init__(self, cep_operator: CEPOperator) -> None:
        self.cep_operator = cep_operator
        self._select_fn: Optional[Callable] = None
        self._timeout_fn: Optional[Callable] = None

    def select(self, fn: Callable[[Dict[str, List[Any]]], Any]) -> "PatternStream":
        """Set the function to apply to completed matches."""
        self._select_fn = fn
        return self

    def select_timed_out(self, fn: Callable[[Dict[str, List[Any]]], Any]) -> "PatternStream":
        """Set the function to apply to timed-out matches."""
        self._timeout_fn = fn
        return self


# ============================================================
# Backpressure
# ============================================================


class BackpressureController:
    """Monitors operator input buffer occupancy.

    Signals upstream operators when buffer occupancy exceeds the
    high watermark threshold, and clears the signal when it drops
    below the low watermark.

    Args:
        high_watermark_pct: Buffer occupancy percentage to trigger backpressure.
        low_watermark_pct: Buffer occupancy percentage to clear backpressure.
    """

    def __init__(
        self,
        high_watermark_pct: float = DEFAULT_HIGH_WATERMARK_PCT,
        low_watermark_pct: float = DEFAULT_LOW_WATERMARK_PCT,
    ) -> None:
        self.high_watermark_pct = high_watermark_pct
        self.low_watermark_pct = low_watermark_pct
        self._statuses: Dict[str, BackpressureStatus] = {}

    def update(self, operator_uid: str, buffer_occupancy_pct: float) -> BackpressureStatus:
        """Update buffer occupancy and compute backpressure status."""
        status = self._statuses.get(operator_uid, BackpressureStatus(operator_uid=operator_uid))

        if buffer_occupancy_pct >= self.high_watermark_pct:
            if not status.is_backpressured:
                status.is_backpressured = True
                logger.debug("Backpressure engaged for operator %s at %.1f%%",
                             operator_uid, buffer_occupancy_pct * 100)
        elif buffer_occupancy_pct <= self.low_watermark_pct:
            if status.is_backpressured:
                status.is_backpressured = False
                logger.debug("Backpressure cleared for operator %s at %.1f%%",
                             operator_uid, buffer_occupancy_pct * 100)

        status.buffer_occupancy_pct = buffer_occupancy_pct
        self._statuses[operator_uid] = status
        return status

    def is_backpressured(self, operator_uid: str) -> bool:
        """Check if an operator is currently backpressured."""
        status = self._statuses.get(operator_uid)
        return status.is_backpressured if status else False

    def get_status(self, operator_uid: str) -> BackpressureStatus:
        """Get the backpressure status for an operator."""
        return self._statuses.get(
            operator_uid,
            BackpressureStatus(operator_uid=operator_uid),
        )


class CreditBasedFlowControl:
    """Credit-based flow control between operators.

    Downstream operators issue credits to upstream, and upstream
    respects credit limits before sending data. This prevents
    buffer overflow and enables fine-grained flow regulation.

    Args:
        initial_credits: Initial credits issued to each upstream.
    """

    def __init__(self, initial_credits: int = DEFAULT_BUFFER_SIZE) -> None:
        self.initial_credits = initial_credits
        self._credits: Dict[Tuple[str, str], int] = {}  # (upstream, downstream) -> credits

    def issue_credits(self, upstream_uid: str, downstream_uid: str, credits: int) -> None:
        """Issue credits from downstream to upstream."""
        key = (upstream_uid, downstream_uid)
        self._credits[key] = self._credits.get(key, 0) + credits

    def consume_credit(self, upstream_uid: str, downstream_uid: str) -> bool:
        """Consume one credit. Returns False if no credits available."""
        key = (upstream_uid, downstream_uid)
        available = self._credits.get(key, 0)
        if available > 0:
            self._credits[key] = available - 1
            return True
        return False

    def available_credits(self, upstream_uid: str, downstream_uid: str) -> int:
        """Get available credits for an upstream-downstream pair."""
        return self._credits.get((upstream_uid, downstream_uid), 0)

    def initialize(self, upstream_uid: str, downstream_uid: str) -> None:
        """Initialize credits for a new connection."""
        self._credits[(upstream_uid, downstream_uid)] = self.initial_credits


class BufferPool:
    """Fixed-size pool of network buffers for inter-operator communication.

    Provides a bounded pool of reusable buffers to prevent unbounded
    memory growth. When the pool is exhausted, requestors block until
    a buffer is returned.

    Args:
        pool_size: Number of buffers in the pool.
        buffer_size: Size of each buffer in elements.
    """

    def __init__(self, pool_size: int = DEFAULT_BUFFER_POOL_SIZE,
                 buffer_size: int = DEFAULT_BUFFER_SIZE) -> None:
        self.pool_size = pool_size
        self.buffer_size = buffer_size
        self._available: int = pool_size
        self._lock = threading.Lock()

    def acquire(self) -> Optional[List]:
        """Acquire a buffer from the pool."""
        with self._lock:
            if self._available > 0:
                self._available -= 1
                return []
            return None

    def release(self) -> None:
        """Return a buffer to the pool."""
        with self._lock:
            if self._available < self.pool_size:
                self._available += 1

    @property
    def available(self) -> int:
        """Number of available buffers."""
        return self._available

    @property
    def utilization_pct(self) -> float:
        """Buffer pool utilization percentage."""
        if self.pool_size == 0:
            return 0.0
        return 1.0 - (self._available / self.pool_size)


# ============================================================
# Savepoints
# ============================================================


class SavepointManager:
    """Creates named, persistent checkpoints for version upgrades.

    Savepoints are named snapshots that persist beyond the normal
    checkpoint retention window, enabling planned upgrades with
    state migration.

    Args:
        storage: The checkpoint storage backend.
    """

    def __init__(self, storage: Any = None) -> None:
        self.storage = storage or InMemoryCheckpointStorage()
        self._savepoints: Dict[str, SavepointMetadata] = {}

    def create_savepoint(
        self,
        name: str,
        operators: List[StreamOperator],
        topology_hash: str = "",
    ) -> SavepointMetadata:
        """Create a named savepoint from current operator state."""
        checkpoint_id = int(time.time() * 1000)
        operator_states = {}

        for operator in operators:
            state = operator.snapshot_state()
            location = self.storage.store(checkpoint_id, operator.uid, state)
            operator_states[operator.uid] = location

        metadata = SavepointMetadata(
            name=name,
            checkpoint_id=checkpoint_id,
            timestamp=time.time(),
            operator_states=operator_states,
            topology_hash=topology_hash,
        )
        self._savepoints[name] = metadata
        logger.info("Savepoint '%s' created with %d operator states",
                     name, len(operator_states))
        return metadata

    def get_savepoint(self, name: str) -> Optional[SavepointMetadata]:
        """Retrieve a savepoint by name."""
        return self._savepoints.get(name)

    def list_savepoints(self) -> List[SavepointMetadata]:
        """List all savepoints."""
        return list(self._savepoints.values())


class SavepointRestoreManager:
    """Restores pipeline from a savepoint.

    Handles topology changes between savepoint creation and
    restoration: new operators, removed operators, and
    repartitioned operators.
    """

    def __init__(self) -> None:
        self._unmatched_states: List[str] = []
        self._missing_operators: List[str] = []

    def restore(
        self,
        savepoint: SavepointMetadata,
        operators: List[StreamOperator],
        storage: Any,
    ) -> bool:
        """Restore operators from a savepoint."""
        self._unmatched_states = []
        self._missing_operators = []

        operator_map = {op.uid: op for op in operators}

        for op_uid, location in savepoint.operator_states.items():
            if op_uid in operator_map:
                state = storage.load(savepoint.checkpoint_id, op_uid)
                if state is not None:
                    operator_map[op_uid].restore_state(state)
            else:
                self._unmatched_states.append(op_uid)

        for op in operators:
            if op.uid not in savepoint.operator_states:
                self._missing_operators.append(op.uid)

        logger.info(
            "Restored from savepoint '%s': %d matched, %d unmatched, %d new",
            savepoint.name,
            len(savepoint.operator_states) - len(self._unmatched_states),
            len(self._unmatched_states),
            len(self._missing_operators),
        )
        return True

    @property
    def unmatched_states(self) -> List[str]:
        """Operator UIDs from savepoint not present in current topology."""
        return self._unmatched_states

    @property
    def missing_operators(self) -> List[str]:
        """Operator UIDs in current topology not present in savepoint."""
        return self._missing_operators


# ============================================================
# Dynamic Scaling
# ============================================================


class KeyGroupAssigner:
    """Maps keys to key groups for state redistribution.

    Uses two-level consistent hashing: keys are first mapped to
    key groups (a fixed-size unit of state), then key groups are
    assigned to operator instances. This enables efficient state
    redistribution during scaling by moving entire key groups.

    Args:
        max_parallelism: Maximum parallelism / number of key groups.
    """

    def __init__(self, max_parallelism: int = DEFAULT_MAX_PARALLELISM) -> None:
        self.max_parallelism = max_parallelism

    def assign_key_group(self, key: Any) -> int:
        """Map a key to a key group."""
        return _murmur3_32(key) % self.max_parallelism

    def assign_to_operator(self, key_group: int, parallelism: int) -> int:
        """Map a key group to an operator instance."""
        if parallelism <= 0:
            raise KeyGroupAssignmentError(
                f"Parallelism must be positive, got {parallelism}"
            )
        return key_group % parallelism

    def compute_key_group_range(self, operator_index: int,
                                parallelism: int) -> Tuple[int, int]:
        """Compute the key group range for an operator instance."""
        groups_per_operator = self.max_parallelism // parallelism
        start = operator_index * groups_per_operator
        end = start + groups_per_operator
        if operator_index == parallelism - 1:
            end = self.max_parallelism
        return (start, end)


class ScaleManager:
    """Adjusts operator parallelism at runtime.

    Coordinates scaling operations by creating a savepoint,
    redistributing keyed state across key groups, and restoring
    with the new parallelism.

    Args:
        key_group_assigner: The key group assigner.
        savepoint_manager: The savepoint manager.
    """

    def __init__(
        self,
        key_group_assigner: KeyGroupAssigner,
        savepoint_manager: SavepointManager,
    ) -> None:
        self.key_group_assigner = key_group_assigner
        self.savepoint_manager = savepoint_manager
        self._scale_history: List[ScaleEvent] = []

    def scale(
        self,
        operator_uid: str,
        new_parallelism: int,
        current_parallelism: int,
    ) -> ScaleEvent:
        """Execute a scaling operation."""
        start = time.time()
        direction = ScaleDirection.UP if new_parallelism > current_parallelism else ScaleDirection.DOWN

        # Compute key groups affected
        old_groups = set()
        new_groups = set()
        for kg in range(self.key_group_assigner.max_parallelism):
            old_op = self.key_group_assigner.assign_to_operator(kg, current_parallelism)
            new_op = self.key_group_assigner.assign_to_operator(kg, new_parallelism)
            if old_op != new_op:
                old_groups.add(kg)
                new_groups.add(kg)

        event = ScaleEvent(
            operator_uid=operator_uid,
            direction=direction,
            old_parallelism=current_parallelism,
            new_parallelism=new_parallelism,
            key_groups_migrated=len(old_groups),
            duration_ms=(time.time() - start) * 1000,
            timestamp=time.time(),
        )
        self._scale_history.append(event)

        logger.info(
            "Scaled operator '%s' from %d to %d (migrated %d key groups in %.1fms)",
            operator_uid, current_parallelism, new_parallelism,
            len(old_groups), event.duration_ms,
        )
        return event


class AutoScaler:
    """Monitors throughput and backpressure to auto-adjust parallelism.

    Triggers scale-up when sustained backpressure exceeds the
    threshold, and scale-down when throughput is consistently
    below capacity.

    Args:
        scale_manager: The scale manager for executing scaling.
        scale_up_threshold_ms: Backpressure duration before scale-up.
        scale_down_threshold_ms: Idle duration before scale-down.
        cooldown_ms: Minimum duration between scaling operations.
        min_parallelism: Minimum allowed parallelism.
        max_parallelism: Maximum allowed parallelism.
    """

    def __init__(
        self,
        scale_manager: ScaleManager,
        scale_up_threshold_ms: int = DEFAULT_SCALE_UP_THRESHOLD_MS,
        scale_down_threshold_ms: int = DEFAULT_SCALE_DOWN_THRESHOLD_MS,
        cooldown_ms: int = DEFAULT_SCALE_COOLDOWN_MS,
        min_parallelism: int = 1,
        max_parallelism: int = 16,
    ) -> None:
        self.scale_manager = scale_manager
        self.scale_up_threshold_ms = scale_up_threshold_ms
        self.scale_down_threshold_ms = scale_down_threshold_ms
        self.cooldown_ms = cooldown_ms
        self.min_parallelism = min_parallelism
        self.max_parallelism = max_parallelism
        self._last_scale_time: float = 0

    def evaluate(
        self,
        operator_uid: str,
        current_parallelism: int,
        backpressure_duration_ms: float,
        idle_duration_ms: float,
    ) -> Optional[ScaleEvent]:
        """Evaluate whether scaling is needed."""
        now = time.time() * 1000
        if now - self._last_scale_time * 1000 < self.cooldown_ms:
            return None

        if (backpressure_duration_ms >= self.scale_up_threshold_ms and
                current_parallelism < self.max_parallelism):
            self._last_scale_time = time.time()
            return self.scale_manager.scale(
                operator_uid, current_parallelism + 1, current_parallelism,
            )

        if (idle_duration_ms >= self.scale_down_threshold_ms and
                current_parallelism > self.min_parallelism):
            self._last_scale_time = time.time()
            return self.scale_manager.scale(
                operator_uid, current_parallelism - 1, current_parallelism,
            )

        return None


# ============================================================
# Metrics & Dashboard
# ============================================================


class StreamMetricsCollector:
    """Collects per-operator runtime metrics.

    Tracks input/output rates, latency percentiles, backpressure
    time, buffer utilization, checkpoint duration, state size,
    and watermark lag for each operator in the execution graph.
    """

    def __init__(self) -> None:
        self._metrics: Dict[str, OperatorMetrics] = {}
        self._latency_samples: Dict[str, List[float]] = defaultdict(list)

    def record_input(self, operator_uid: str) -> None:
        """Record an input event for an operator."""
        metrics = self._get_or_create(operator_uid)
        metrics.records_processed += 1

    def record_latency(self, operator_uid: str, latency_ms: float) -> None:
        """Record a processing latency sample."""
        self._latency_samples[operator_uid].append(latency_ms)
        samples = self._latency_samples[operator_uid]

        # Keep last 1000 samples
        if len(samples) > 1000:
            self._latency_samples[operator_uid] = samples[-1000:]
            samples = self._latency_samples[operator_uid]

        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        metrics = self._get_or_create(operator_uid)
        metrics.latency_p50_ms = sorted_samples[int(n * 0.50)] if n > 0 else 0
        metrics.latency_p95_ms = sorted_samples[min(int(n * 0.95), n - 1)] if n > 0 else 0
        metrics.latency_p99_ms = sorted_samples[min(int(n * 0.99), n - 1)] if n > 0 else 0

    def update_rates(self, operator_uid: str, input_rate: float,
                     output_rate: float) -> None:
        """Update throughput rates."""
        metrics = self._get_or_create(operator_uid)
        metrics.input_rate = input_rate
        metrics.output_rate = output_rate

    def update_backpressure(self, operator_uid: str, pct: float) -> None:
        """Update backpressure percentage."""
        metrics = self._get_or_create(operator_uid)
        metrics.backpressure_pct = pct

    def update_buffer_utilization(self, operator_uid: str, pct: float) -> None:
        """Update buffer utilization."""
        metrics = self._get_or_create(operator_uid)
        metrics.buffer_utilization_pct = pct

    def update_state_size(self, operator_uid: str, size_bytes: int) -> None:
        """Update state size."""
        metrics = self._get_or_create(operator_uid)
        metrics.state_size_bytes = size_bytes

    def update_watermark_lag(self, operator_uid: str, lag_ms: float) -> None:
        """Update watermark lag."""
        metrics = self._get_or_create(operator_uid)
        metrics.watermark_lag_ms = lag_ms

    def get_metrics(self, operator_uid: str) -> OperatorMetrics:
        """Get metrics for an operator."""
        return self._get_or_create(operator_uid)

    def get_all_metrics(self) -> Dict[str, OperatorMetrics]:
        """Get all operator metrics."""
        return dict(self._metrics)

    def _get_or_create(self, operator_uid: str) -> OperatorMetrics:
        """Get or create metrics for an operator."""
        if operator_uid not in self._metrics:
            self._metrics[operator_uid] = OperatorMetrics(operator_uid=operator_uid)
        return self._metrics[operator_uid]


class FizzStreamDashboard:
    """ASCII dashboard for FizzStream pipeline visualization.

    Renders the operator topology graph, per-operator throughput
    and latency, watermark positions, checkpoint history,
    backpressure indicators, and active job status.

    Args:
        width: Dashboard width in characters.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self.width = width

    def render(
        self,
        jobs: List[JobDescriptor],
        metrics: Dict[str, OperatorMetrics],
        checkpoints: List[CheckpointMetadata],
    ) -> str:
        """Render the complete dashboard."""
        lines = []
        border = "+" + "-" * (self.width - 2) + "+"

        # Header
        lines.append(border)
        title = f"FIZZSTREAM DASHBOARD v{FIZZSTREAM_VERSION}"
        lines.append(f"| {title:^{self.width - 4}} |")
        lines.append(border)

        # Jobs section
        lines.append(f"| {'ACTIVE JOBS':^{self.width - 4}} |")
        lines.append(f"| {'-' * (self.width - 4)} |")
        if jobs:
            for job in jobs:
                status_line = f"  {job.job_id[:8]}  {job.name:<20} {job.status.value:<12}"
                lines.append(f"| {status_line:<{self.width - 4}} |")
        else:
            lines.append(f"| {'  No active jobs':<{self.width - 4}} |")
        lines.append(border)

        # Operator metrics section
        lines.append(f"| {'OPERATOR METRICS':^{self.width - 4}} |")
        lines.append(f"| {'-' * (self.width - 4)} |")
        header = f"  {'UID':<10} {'In/s':>8} {'Out/s':>8} {'P50ms':>7} {'P99ms':>7} {'BP%':>5}"
        lines.append(f"| {header:<{self.width - 4}} |")
        for uid, m in metrics.items():
            row = (
                f"  {uid[:10]:<10} {m.input_rate:>8.1f} {m.output_rate:>8.1f} "
                f"{m.latency_p50_ms:>7.1f} {m.latency_p99_ms:>7.1f} "
                f"{m.backpressure_pct * 100:>5.1f}"
            )
            lines.append(f"| {row:<{self.width - 4}} |")
        lines.append(border)

        # Checkpoint section
        lines.append(f"| {'CHECKPOINTS':^{self.width - 4}} |")
        lines.append(f"| {'-' * (self.width - 4)} |")
        recent = checkpoints[-3:] if checkpoints else []
        for cp in recent:
            cp_line = f"  CP-{cp.checkpoint_id:04d}  {cp.status.value:<10} {cp.duration_ms:.1f}ms"
            lines.append(f"| {cp_line:<{self.width - 4}} |")
        if not recent:
            lines.append(f"| {'  No checkpoints':<{self.width - 4}} |")
        lines.append(border)

        return "\n".join(lines)


# ============================================================
# Streaming SQL Bridge
# ============================================================


class StreamSQLBridge:
    """Extends FizzSQLEngine with streaming SQL.

    Supports TUMBLE/HOP/SESSION window functions, EMIT AFTER
    WATERMARK, continuous SELECT, and streaming joins. Compiles
    SQL queries into DataStream operator graphs.
    """

    def __init__(self) -> None:
        self._registered_streams: Dict[str, Any] = {}

    def register_stream(self, name: str, stream: Any) -> None:
        """Register a DataStream as a named SQL table."""
        self._registered_streams[name] = stream

    def execute_sql(self, query: str) -> Dict[str, Any]:
        """Parse and compile a streaming SQL query.

        Recognizes TUMBLE(), HOP(), and SESSION() window functions
        and generates appropriate DataStream operator graphs.

        Returns a descriptor of the compiled query plan.
        """
        query_upper = query.upper().strip()

        # Parse window functions
        window_type = None
        if "TUMBLE(" in query_upper:
            window_type = WindowType.TUMBLING
        elif "HOP(" in query_upper:
            window_type = WindowType.SLIDING
        elif "SESSION(" in query_upper:
            window_type = WindowType.SESSION

        plan = {
            "query": query,
            "window_type": window_type.value if window_type else None,
            "is_continuous": "EMIT" in query_upper or window_type is not None,
            "registered_streams": list(self._registered_streams.keys()),
            "compiled": True,
        }

        logger.debug("Compiled streaming SQL: window=%s, continuous=%s",
                      plan["window_type"], plan["is_continuous"])
        return plan


# ============================================================
# DataStream & KeyedStream
# ============================================================


class DataStream:
    """Fundamental abstraction representing an unbounded sequence of events.

    Defines a DAG of operators via fluent method chaining. Does not
    hold data -- represents a logical plan that is compiled into a
    physical execution graph when the job is submitted.
    """

    def __init__(self, env: "StreamExecutionEnvironment",
                 source: Optional[StreamOperator] = None) -> None:
        self._env = env
        self._operators: List[StreamOperator] = []
        if source:
            self._operators.append(source)

    def filter(self, predicate: Callable) -> "DataStream":
        """Filter elements by predicate."""
        op = FilterOperator(predicate)
        self._operators.append(op)
        return self

    def map(self, fn: Callable) -> "DataStream":
        """Apply a function to each element."""
        op = MapOperator(fn)
        self._operators.append(op)
        return self

    def flat_map(self, fn: Callable) -> "DataStream":
        """Apply a function producing zero or more outputs per element."""
        op = FlatMapOperator(fn)
        self._operators.append(op)
        return self

    def key_by(self, key_extractor: Callable) -> "KeyedStream":
        """Partition the stream by key."""
        op = KeyByOperator(key_extractor, max_parallelism=self._env.max_parallelism)
        self._operators.append(op)
        return KeyedStream(self._env, self._operators)

    def union(self, *others: "DataStream") -> "DataStream":
        """Merge with other streams."""
        op = UnionOperator()
        result = DataStream(self._env)
        result._operators = list(self._operators)
        result._operators.append(op)
        for other in others:
            result._operators.extend(other._operators)
        return result

    def process(self, process_fn: Callable,
                on_timer_fn: Optional[Callable] = None) -> "DataStream":
        """Apply a general-purpose process function."""
        op = ProcessOperator(process_fn, on_timer_fn)
        self._operators.append(op)
        return self

    def sink_to(self, sink: StreamOperator) -> "DataStream":
        """Attach a sink operator."""
        self._operators.append(sink)
        return self

    def get_operators(self) -> List[StreamOperator]:
        """Get the list of operators in the logical plan."""
        return list(self._operators)


class KeyedStream:
    """Specialized DataStream partitioned by a key extractor function.

    Enables key-scoped stateful processing, windowing, and reduction.
    """

    def __init__(self, env: "StreamExecutionEnvironment",
                 operators: List[StreamOperator]) -> None:
        self._env = env
        self._operators = list(operators)

    def window(self, window_def: Any) -> "KeyedStream":
        """Apply a window definition to the keyed stream."""
        self._window_def = window_def
        return self

    def reduce(self, reduce_fn: Callable) -> DataStream:
        """Apply a reduce function to the keyed stream."""
        op = ReduceOperator(reduce_fn)
        self._operators.append(op)
        return DataStream(self._env, source=None)

    def process(self, process_fn: Callable,
                on_timer_fn: Optional[Callable] = None) -> DataStream:
        """Apply a process function to the keyed stream."""
        op = ProcessOperator(process_fn, on_timer_fn)
        self._operators.append(op)
        ds = DataStream(self._env)
        ds._operators = list(self._operators)
        return ds

    def filter(self, predicate: Callable) -> "KeyedStream":
        """Filter elements in the keyed stream."""
        op = FilterOperator(predicate)
        self._operators.append(op)
        return self

    def map(self, fn: Callable) -> DataStream:
        """Apply a map function to the keyed stream."""
        op = MapOperator(fn)
        self._operators.append(op)
        ds = DataStream(self._env)
        ds._operators = list(self._operators)
        return ds

    def get_operators(self) -> List[StreamOperator]:
        """Get the list of operators."""
        return list(self._operators)


# ============================================================
# Stream Job
# ============================================================


class StreamJob:
    """Runtime representation of a submitted stream processing job.

    Manages the job lifecycle: CREATED -> INITIALIZING -> RUNNING ->
    CHECKPOINTING -> FINISHED/FAILED/CANCELLED.

    Args:
        name: User-provided job name.
        operators: List of operators in the execution graph.
        env: The execution environment.
    """

    def __init__(
        self,
        name: str,
        operators: List[StreamOperator],
        env: "StreamExecutionEnvironment",
    ) -> None:
        self.job_id = str(uuid.uuid4())[:12]
        self.name = name
        self.operators = operators
        self.env = env
        self.status = StreamJobStatus.CREATED
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.restart_count: int = 0
        self._metrics: Dict[str, OperatorMetrics] = {}
        self._checkpoints: List[CheckpointMetadata] = []
        self._savepoints: List[SavepointMetadata] = []

    def start(self) -> None:
        """Initialize and start the job."""
        self.status = StreamJobStatus.INITIALIZING
        self.start_time = time.time()

        for operator in self.operators:
            operator.open()

        self.status = StreamJobStatus.RUNNING
        logger.info("Stream job '%s' (%s) started with %d operators",
                     self.name, self.job_id, len(self.operators))

    def cancel(self) -> None:
        """Cancel the running job."""
        self.status = StreamJobStatus.CANCELLING
        for operator in self.operators:
            operator.close()
        self.status = StreamJobStatus.CANCELLED
        self.end_time = time.time()
        logger.info("Stream job '%s' (%s) cancelled", self.name, self.job_id)

    def finish(self) -> None:
        """Mark the job as finished."""
        for operator in self.operators:
            operator.close()
        self.status = StreamJobStatus.FINISHED
        self.end_time = time.time()
        logger.info("Stream job '%s' (%s) finished", self.name, self.job_id)

    def fail(self, reason: str) -> None:
        """Mark the job as failed."""
        self.status = StreamJobStatus.FAILED
        self.end_time = time.time()
        logger.error("Stream job '%s' (%s) failed: %s",
                      self.name, self.job_id, reason)

    def get_descriptor(self) -> JobDescriptor:
        """Get the job descriptor."""
        return JobDescriptor(
            job_id=self.job_id,
            name=self.name,
            status=self.status,
            operators=[op.get_descriptor() for op in self.operators],
            start_time=self.start_time,
            end_time=self.end_time,
            checkpoint_interval_ms=self.env.checkpoint_interval_ms,
            restart_strategy=self.env.restart_strategy.strategy_type,
            state_backend=self.env.state_backend.backend_type,
            parallelism=self.env.parallelism,
            max_parallelism=self.env.max_parallelism,
            metrics=self._metrics,
            checkpoints=self._checkpoints,
            savepoints=self._savepoints,
            restart_count=self.restart_count,
        )


# ============================================================
# Stream Execution Environment
# ============================================================


class StreamExecutionEnvironment:
    """Entry point for creating and executing stream processing pipelines.

    Configures global execution parameters, provides factory methods
    for creating source streams, compiles logical plans into physical
    execution graphs, and manages active jobs.

    Args:
        parallelism: Default operator parallelism.
        max_parallelism: Maximum parallelism / key group count.
        checkpoint_interval_ms: Checkpoint interval.
        checkpoint_coordinator: The checkpoint coordinator.
        state_backend: The state backend.
        restart_strategy: The restart strategy.
        buffer_pool: The buffer pool.
        backpressure_controller: The backpressure controller.
        metrics_collector: The metrics collector.
        watermark_interval_ms: Watermark emission interval.
        buffer_timeout_ms: Buffer flush timeout.
    """

    def __init__(
        self,
        parallelism: int = DEFAULT_PARALLELISM,
        max_parallelism: int = DEFAULT_MAX_PARALLELISM,
        checkpoint_interval_ms: int = DEFAULT_CHECKPOINT_INTERVAL_MS,
        checkpoint_coordinator: Optional[CheckpointCoordinator] = None,
        state_backend: Optional[Any] = None,
        restart_strategy: Optional[Any] = None,
        buffer_pool: Optional[BufferPool] = None,
        backpressure_controller: Optional[BackpressureController] = None,
        metrics_collector: Optional[StreamMetricsCollector] = None,
        watermark_interval_ms: int = DEFAULT_WATERMARK_INTERVAL_MS,
        buffer_timeout_ms: int = DEFAULT_BUFFER_TIMEOUT_MS,
    ) -> None:
        self.parallelism = parallelism
        self.max_parallelism = max_parallelism
        self.checkpoint_interval_ms = checkpoint_interval_ms
        self.state_backend = state_backend or HashMapStateBackend()
        self.restart_strategy = restart_strategy or FixedDelayRestartStrategy()
        self.buffer_pool = buffer_pool or BufferPool()
        self.backpressure_controller = backpressure_controller or BackpressureController()
        self.metrics_collector = metrics_collector or StreamMetricsCollector()
        self.checkpoint_coordinator = checkpoint_coordinator or CheckpointCoordinator(
            interval_ms=checkpoint_interval_ms,
            state_backend=self.state_backend,
        )
        self.watermark_interval_ms = watermark_interval_ms
        self.buffer_timeout_ms = buffer_timeout_ms

        self._jobs: Dict[str, StreamJob] = {}
        self._topics: Dict[str, StreamTopicConfig] = {}

    def from_source(self, source: StreamOperator) -> DataStream:
        """Create a DataStream from a source operator."""
        return DataStream(self, source=source)

    def from_collection(self, elements: List[Any]) -> DataStream:
        """Create a bounded DataStream from a collection."""
        source = GeneratorSource(
            generator_fn=lambda i: elements[i] if i < len(elements) else None,
            num_elements=len(elements),
        )
        return DataStream(self, source=source)

    def submit_job(self, name: str, stream: DataStream) -> StreamJob:
        """Submit a stream processing job."""
        operators = stream.get_operators()
        if not operators:
            raise StreamJobSubmissionError(name, "Empty operator graph")

        job = StreamJob(name=name, operators=operators, env=self)
        self._jobs[job.job_id] = job
        job.start()
        return job

    def cancel_job(self, job_id: str) -> None:
        """Cancel a running job."""
        job = self._jobs.get(job_id)
        if job is None:
            raise StreamJobNotFoundError(job_id)
        job.cancel()

    def get_job(self, job_id: str) -> Optional[StreamJob]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[StreamJob]:
        """List all jobs."""
        return list(self._jobs.values())

    def register_topic(self, config: StreamTopicConfig) -> None:
        """Register a streaming topic."""
        self._topics[config.name] = config

    def get_topic(self, name: str) -> Optional[StreamTopicConfig]:
        """Get a topic configuration."""
        return self._topics.get(name)

    def process_element(self, element: StreamElement,
                        operators: List[StreamOperator]) -> List[StreamElement]:
        """Process an element through a chain of operators."""
        current = [element]
        for operator in operators:
            next_elements = []
            for elem in current:
                self.metrics_collector.record_input(operator.uid)
                start = time.time()
                results = operator.process_element(elem)
                latency = (time.time() - start) * 1000
                self.metrics_collector.record_latency(operator.uid, latency)
                next_elements.extend(results)
            current = next_elements
        return current


# ============================================================
# FizzStream Middleware
# ============================================================


class FizzStreamMiddleware(IMiddleware):
    """Middleware integration for the FizzStream subsystem.

    Emits each FizzBuzz evaluation result as a StreamElement to the
    fizzbuzz.stream.evaluations topic, queries active stream jobs
    for real-time aggregates, and annotates the processing context
    with stream processing metadata.

    Priority: 38 (after caching, before MapReduce).
    """

    def __init__(
        self,
        env: StreamExecutionEnvironment,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        self._env = env
        self._dashboard = FizzStreamDashboard(width=dashboard_width)
        self._enable_dashboard = enable_dashboard
        self._emission_count: int = 0

    def get_name(self) -> str:
        """Return middleware name."""
        return "FizzStreamMiddleware"

    def get_priority(self) -> int:
        """Return middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Middleware name."""
        return "FizzStreamMiddleware"

    def process(self, context: ProcessingContext, result: FizzBuzzResult,
                next_handler: Callable) -> FizzBuzzResult:
        """Emit evaluation result to stream and delegate to next handler."""
        # Emit the evaluation as a stream element
        element = StreamElement(
            value={
                "number": getattr(context, "number", None),
                "result": str(result),
                "classification": getattr(result, "classification", None),
            },
            timestamp=int(time.time() * 1000),
        )
        self._emission_count += 1

        # Annotate context with stream metadata
        if hasattr(context, "metadata") and isinstance(context.metadata, dict):
            context.metadata["fizzstream_emission_count"] = self._emission_count
            context.metadata["fizzstream_active_jobs"] = len(self._env.list_jobs())

        return next_handler(context, result)

    def render_jobs(self) -> str:
        """Render active and completed job list."""
        jobs = self._env.list_jobs()
        if not jobs:
            return "FizzStream: No active stream processing jobs."

        lines = ["FizzStream Active Jobs:"]
        lines.append("-" * 60)
        lines.append(f"  {'Job ID':<14} {'Name':<20} {'Status':<12} {'Operators':>6}")
        lines.append("-" * 60)
        for job in jobs:
            lines.append(
                f"  {job.job_id:<14} {job.name:<20} "
                f"{job.status.value:<12} {len(job.operators):>6}"
            )
        return "\n".join(lines)

    def render_dashboard(self) -> str:
        """Render the pipeline dashboard."""
        jobs = [job.get_descriptor() for job in self._env.list_jobs()]
        metrics = self._env.metrics_collector.get_all_metrics()
        checkpoints = []
        for job in self._env.list_jobs():
            checkpoints.extend(job._checkpoints)
        return self._dashboard.render(jobs, metrics, checkpoints)

    def render_status(self) -> str:
        """Render subsystem status summary."""
        active_jobs = sum(
            1 for j in self._env.list_jobs()
            if j.status == StreamJobStatus.RUNNING
        )
        total_jobs = len(self._env.list_jobs())
        return (
            f"FizzStream v{FIZZSTREAM_VERSION}: "
            f"{active_jobs} active / {total_jobs} total jobs, "
            f"{self._emission_count} evaluations emitted, "
            f"parallelism={self._env.parallelism}, "
            f"state_backend={self._env.state_backend.backend_type.value}"
        )


# ============================================================
# Factory Function
# ============================================================


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
) -> Tuple["StreamExecutionEnvironment", "FizzStreamMiddleware"]:
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
    # Select state backend
    if state_backend == "rocksdb":
        state_backend_instance = RocksDBStateBackend()
    else:
        state_backend_instance = HashMapStateBackend()

    # Select restart strategy
    if restart_strategy == "exponential":
        restart_strategy_instance = ExponentialBackoffRestartStrategy(
            max_restarts=restart_max_attempts,
        )
    elif restart_strategy == "none":
        restart_strategy_instance = NoRestartStrategy()
    else:
        restart_strategy_instance = FixedDelayRestartStrategy(
            max_restarts=restart_max_attempts,
            delay_ms=restart_delay_ms,
        )

    # Create infrastructure components
    buffer_pool = BufferPool(DEFAULT_BUFFER_POOL_SIZE, DEFAULT_BUFFER_SIZE)
    backpressure_controller = BackpressureController()
    credit_flow = CreditBasedFlowControl()
    checkpoint_storage = InMemoryCheckpointStorage()
    checkpoint_coordinator = CheckpointCoordinator(
        interval_ms=checkpoint_interval_ms,
        state_backend=state_backend_instance,
        storage=checkpoint_storage,
    )
    key_group_assigner = KeyGroupAssigner(max_parallelism)
    metrics_collector = StreamMetricsCollector()
    dashboard = FizzStreamDashboard(dashboard_width)
    savepoint_manager = SavepointManager(checkpoint_storage)
    savepoint_restore_manager = SavepointRestoreManager()
    scale_manager = ScaleManager(key_group_assigner, savepoint_manager)
    auto_scaler = AutoScaler(scale_manager)

    # Create execution environment
    env = StreamExecutionEnvironment(
        parallelism=parallelism,
        max_parallelism=max_parallelism,
        checkpoint_interval_ms=checkpoint_interval_ms,
        checkpoint_coordinator=checkpoint_coordinator,
        state_backend=state_backend_instance,
        restart_strategy=restart_strategy_instance,
        buffer_pool=buffer_pool,
        backpressure_controller=backpressure_controller,
        metrics_collector=metrics_collector,
        watermark_interval_ms=watermark_interval_ms,
        buffer_timeout_ms=buffer_timeout_ms,
    )

    # Configure default streaming topics
    default_topics = [
        StreamTopicConfig(
            name=STREAM_TOPIC_EVALUATIONS,
            partitions=parallelism,
            description="Real-time FizzBuzz evaluation results",
        ),
        StreamTopicConfig(
            name=STREAM_TOPIC_METRICS,
            partitions=2,
            description="Continuous metric emissions",
        ),
        StreamTopicConfig(
            name=STREAM_TOPIC_ALERTS,
            partitions=1,
            description="Threshold violations and anomalies",
        ),
        StreamTopicConfig(
            name=STREAM_TOPIC_AUDIT,
            partitions=1,
            description="Compliance-relevant events",
        ),
        StreamTopicConfig(
            name=STREAM_TOPIC_LIFECYCLE,
            partitions=2,
            description="Container and service lifecycle events",
        ),
    ]
    for topic in default_topics:
        env.register_topic(topic)

    # Create middleware
    middleware = FizzStreamMiddleware(
        env=env,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info(
        "FizzStream subsystem initialized: parallelism=%d, max_parallelism=%d, "
        "state_backend=%s, restart_strategy=%s, checkpoint_interval=%dms",
        parallelism, max_parallelism, state_backend,
        restart_strategy, checkpoint_interval_ms,
    )

    return env, middleware

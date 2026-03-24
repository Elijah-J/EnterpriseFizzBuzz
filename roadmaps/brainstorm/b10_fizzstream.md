# FizzStream -- Distributed Stream Processing Engine

## The Problem

The Enterprise FizzBuzz Platform processes data in two modes: batch and request-response. FizzReduce implements MapReduce for batch computation, splitting input ranges into partitions, mapping them through rule engines, shuffling by key, and reducing to aggregate counts. The message queue implements Kafka-style partitioned topics with consumer groups, offset management, and exactly-once delivery semantics. The event sourcing module maintains an append-only journal of every FizzBuzz evaluation decision, materialized through projections into read models. FizzSQL provides relational query capabilities over stored data.

All of these systems share a fundamental assumption: the data is bounded. MapReduce jobs operate on finite input ranges. Message queue consumers read from committed offsets to the latest offset and stop. Event store projections rebuild from the beginning of the journal to the current position. FizzSQL queries scan finite tables. Every processing model in the platform treats data as something that has a beginning and an end.

Real enterprise data does not have an end. FizzBuzz evaluation requests arrive continuously. Rule configuration changes propagate in real time. Cache invalidation events cascade through the MESI coherence protocol without termination. Feature flag toggles, compliance audit events, SLA violations, cognitive load measurements, deployment pipeline transitions, container lifecycle events, network packet arrivals, DNS query resolutions -- these are infinite event streams. They do not start and stop. They flow.

Apache Flink, Kafka Streams, Apache Storm, and Google Cloud Dataflow exist because batch processing cannot handle unbounded data. Batch processes data that has already arrived. Stream processes data as it arrives. The latency difference is the difference between "here is yesterday's report" and "the system is degrading right now." The platform has 116 infrastructure modules generating continuous event streams, a message queue capable of delivering those events, and zero capability to process them in real time.

The MapReduce framework cannot process an infinite input range. It requires an `InputSplit` with a start and end. The message queue can deliver events but cannot transform them -- it is a transport layer, not a processing layer. The event sourcing module can project events into read models, but projections are batch rebuilds, not continuous computations. FizzSQL can query stored data, but it cannot query data that has not yet arrived.

The platform has data in motion and no way to compute over it.

## The Vision

A complete distributed stream processing engine inspired by Apache Flink and Kafka Streams, implementing the DataStream API for continuous computation over unbounded event sequences. FizzStream treats every event source in the platform -- message queue topics, event store journals, container lifecycle events, network packets, metric emissions, rule evaluation results -- as an infinite stream that can be filtered, mapped, joined, windowed, aggregated, and sunk to any downstream system in real time.

The engine implements the full stream processing taxonomy: source operators that read from external systems, transformation operators that apply stateless and stateful functions to individual events, windowing operators that group events by time or count for bounded aggregation, join operators that correlate events across streams, complex event processing operators that detect multi-event patterns, and sink operators that write results to external systems. Time semantics support both event time (when the event occurred) and processing time (when the event is processed), with watermarks tracking event-time completeness and triggering window computation. Exactly-once processing guarantees are maintained through periodic checkpointing of operator state to a persistent state backend, enabling failure recovery without data loss or duplication. Stateful operators maintain keyed state partitioned by a user-defined key extractor, stored in configurable state backends (in-memory hash map for low-latency access, RocksDB-style LSM tree for large state). Backpressure propagation prevents fast sources from overwhelming slow operators. Savepoints capture the complete processing state for planned version upgrades. Dynamic scaling adjusts operator parallelism at runtime without stopping the pipeline.

FizzStream integrates with three existing platform subsystems. The message queue serves as the primary source and sink, with FizzStream consumer groups reading from topic partitions and FizzStream producers writing results to output topics. The event sourcing module serves as both a source (reading the event journal as a stream) and a sink (appending computed results as new domain events). FizzSQL provides SQL-on-streams capability, extending the existing SQL parser with streaming-specific constructs (`TUMBLE`, `HOP`, `SESSION` window functions, `EMIT AFTER WATERMARK`, continuous `SELECT` queries).

## Key Components

- **`fizzstream.py`** (~3,500 lines): FizzStream Distributed Stream Processing Engine

### DataStream API

The core programming interface for defining stream processing pipelines:

- **`DataStream[T]`**: the fundamental abstraction representing an unbounded sequence of events of type `T`. A `DataStream` is a logical plan -- it does not hold data, but defines a directed acyclic graph of operators that will process data when the pipeline is executed. Every transformation on a `DataStream` returns a new `DataStream`, enabling fluent method chaining:

  ```
  stream = env.from_source(message_queue_source("fizzbuzz.evaluations"))
      .filter(lambda e: e.result != "FizzBuzz")
      .map(lambda e: (e.number, e.result, e.timestamp))
      .key_by(lambda e: e[1])
      .window(TumblingEventTimeWindow(duration_ms=60000))
      .aggregate(CountAggregator())
      .sink_to(event_store_sink("stream.classification.counts"))
  ```

- **`StreamExecutionEnvironment`**: the entry point for creating and executing stream processing pipelines. Configures global execution parameters: default parallelism, checkpoint interval, state backend, watermark strategy, restart strategy, and buffer timeout. Provides factory methods for creating source streams (`from_source`, `from_collection`, `from_elements`). The `execute(job_name)` method compiles the logical plan into a physical execution graph, deploys operators across processing threads, and begins execution. The environment maintains a registry of all active jobs with their execution status, metrics, and savepoint history

- **`StreamOperator`**: abstract base class for all stream operators. Defines the operator lifecycle: `open()` (called once when the operator starts, used to initialize state and timers), `process_element(event, context)` (called for each incoming event), `process_watermark(watermark)` (called when a watermark arrives), `snapshot_state(checkpoint_id)` (called during checkpointing to serialize operator state), `restore_state(checkpoint_id, state)` (called during recovery to deserialize operator state), `close()` (called once when the operator stops). Each operator has a declared `parallelism` (number of concurrent instances), `chain_strategy` (whether it can be fused with adjacent operators to reduce serialization overhead), and `uid` (stable identifier for state recovery across topology changes)

### Source Operators

Connectors that ingest events from external systems into the stream processing pipeline:

- **`MessageQueueSource`**: reads events from a message queue topic. Each parallel instance is assigned a subset of topic partitions (using the message queue's `ConsumerGroup` rebalancing protocol). Events are deserialized from the message queue's `Message` format into stream elements. The source tracks committed offsets per partition and reports them during checkpointing, enabling exactly-once consumption through offset rollback on failure recovery. Watermarks are extracted from message timestamps using a configurable `WatermarkStrategy`. The source implements `SourceSplitEnumerator` to dynamically discover new partitions added to the topic at runtime

- **`EventStoreSource`**: reads domain events from the event sourcing module's `EventStore` journal as a continuous stream. The source starts from a configurable position (beginning of journal, specific sequence number, or latest) and tails the journal for new events. Each event is deserialized into a stream element containing the event type, aggregate ID, payload, sequence number, and timestamp. The source emits watermarks based on event timestamps. During checkpointing, the source records the last consumed sequence number for recovery

- **`ContainerEventSource`**: reads container lifecycle events from FizzContainerd's event service (container created, started, stopped, paused, resumed, removed). Enables real-time monitoring and reaction to container state changes across the platform

- **`MetricSource`**: reads metric emissions from the OpenTelemetry collector as a continuous stream. Enables real-time metric computation -- sliding window averages, anomaly detection, threshold alerting -- without waiting for the next scrape interval

- **`GeneratorSource`**: a synthetic source that generates events from a user-defined function at a configurable rate. Used for testing, benchmarking, and simulation. Supports bounded (generate N events and stop) and unbounded (generate indefinitely) modes

### Transformation Operators

Stateless and stateful operations that transform stream elements:

- **`MapOperator`**: applies a function `f: T -> R` to each element, producing one output element per input element. Stateless. Chainable with adjacent operators to avoid serialization overhead

- **`FlatMapOperator`**: applies a function `f: T -> Iterable[R]` to each element, producing zero or more output elements per input element. Used for event explosion (one input generates multiple outputs) and filtering (return empty iterable to drop)

- **`FilterOperator`**: applies a predicate `p: T -> bool` to each element, forwarding only elements where the predicate returns `True`. Stateless. Implemented as a specialized `FlatMapOperator` for optimal chaining

- **`KeyByOperator`**: partitions the stream by a key extractor function `k: T -> K`. All elements with the same key are routed to the same downstream operator instance, enabling key-scoped stateful processing. Returns a `KeyedStream[K, T]` rather than a plain `DataStream[T]`. The partitioning uses consistent hashing (murmur3) over the key space, matching the message queue's partition strategy for end-to-end key affinity

- **`ReduceOperator`**: applies a binary reduction function `r: (T, T) -> T` to a keyed stream, maintaining a running aggregate per key. Stateful -- stores the current aggregate value in the keyed state backend. Emits the updated aggregate after each input element. Used for running totals, min/max tracking, and incremental aggregation

- **`ProcessOperator`**: the most general-purpose operator, providing access to the full operator context including keyed state, timers, side outputs, and watermark information. The `process_element(event, context)` method receives a `ProcessContext` with methods: `get_state(descriptor)` (access keyed state), `register_event_time_timer(timestamp)` (fire callback when watermark passes timestamp), `register_processing_time_timer(timestamp)` (fire callback at wall-clock time), `output(element, tag)` (emit to a side output), `current_watermark()` (current watermark position). The `on_timer(timestamp, context)` method is called when a registered timer fires. This operator enables complex stateful logic like session detection, pattern matching, and custom windowing

- **`UnionOperator`**: merges two or more streams of the same type into a single stream. Does not perform deduplication or ordering -- elements arrive in the order they are processed. Used to combine multiple event sources into a unified stream for downstream processing

### Windowing System

Bounded computation over unbounded streams:

- **`Window`**: abstract base class defining a window's time boundaries (`start`, `end`) and maximum timestamp (the last event timestamp that belongs to this window). Windows are assigned to elements by a `WindowAssigner` and evaluated by a `WindowFunction` when triggered by a `Trigger`

- **`TumblingEventTimeWindow`**: fixed-size, non-overlapping windows aligned to event time. A window of size 60 seconds starting at epoch creates windows [0, 60000), [60000, 120000), [120000, 180000), and so on. Each event belongs to exactly one window. Parameters: `size_ms` (window duration in milliseconds), `offset_ms` (optional offset for alignment to non-epoch boundaries). Tumbling windows are the most efficient window type -- they require no duplication of elements across windows

- **`SlidingEventTimeWindow`**: fixed-size windows that advance by a configurable slide interval, creating overlapping windows. A window of size 60 seconds with a slide of 10 seconds creates windows [0, 60000), [10000, 70000), [20000, 80000), and so on. Each event may belong to `size / slide` windows. Parameters: `size_ms`, `slide_ms`. Sliding windows enable moving averages, rolling counts, and other computations that require overlapping temporal context

- **`SessionWindow`**: dynamically-sized windows defined by gaps in activity. A session window with a gap of 30 seconds groups all consecutive events separated by less than 30 seconds into a single window. If no event arrives within the gap duration after the last event, the session is closed and the window fires. Parameters: `gap_ms`. Session windows are inherently keyed -- each key maintains its own session state. They are used for user session analysis, conversation grouping, and burst detection

- **`GlobalWindow`**: a single window that contains all elements. Never triggers automatically -- requires a custom `Trigger` to determine when to evaluate. Used with `ProcessOperator` for custom windowing logic where the standard window types are insufficient

- **`WindowAssigner`**: assigns each incoming element to zero or more windows based on the element's timestamp and the window definition. The assigner is called for every element and returns a list of windows the element belongs to. For tumbling windows this list always contains exactly one window. For sliding windows it may contain `size / slide` windows. For session windows it returns a new or merged session window

- **`Trigger`**: determines when a window's contents should be processed. Built-in triggers:
  - **`EventTimeTrigger`**: fires when the watermark passes the window's end timestamp. This is the default trigger for event-time windows. Guarantees that all events belonging to the window have arrived (modulo late events)
  - **`ProcessingTimeTrigger`**: fires at a wall-clock time equal to the window's end. Does not wait for late events
  - **`CountTrigger`**: fires when the window contains a specified number of elements
  - **`PurgingTrigger`**: wraps another trigger and clears the window contents after firing, converting an accumulating window into a purging window
  - **`ContinuousEventTimeTrigger`**: fires periodically (every N milliseconds of event time) within a window, emitting intermediate results before the window closes. Used for early results in long windows

- **`WindowFunction`**: computes the result of a window. Three variants:
  - **`ReduceFunction`**: incrementally reduces elements as they arrive, maintaining a single aggregate value. Memory-efficient -- does not buffer elements
  - **`AggregateFunction`**: generalizes `ReduceFunction` with separate accumulator, add, merge, and extract phases. Supports complex aggregates (e.g., average requires sum and count)
  - **`ProcessWindowFunction`**: receives all elements in the window as an iterable when the window fires. Most flexible but requires buffering all elements in state. Has access to window metadata (start time, end time, key)

- **`AllowedLateness`**: configurable grace period after a window's end timestamp during which late elements are still accepted into the window. Late elements trigger the window function again with the updated contents (incremental update, not full recomputation). Elements arriving after the allowed lateness are dropped or routed to a side output for separate handling. Parameters: `lateness_ms`

### Watermark System

Event-time progress tracking for correct out-of-order processing:

- **`Watermark`**: a special stream element that declares "no more events with timestamp <= W will arrive." Watermarks flow through the operator graph alongside regular elements, advancing the notion of event-time completeness at each operator. When a watermark arrives at a windowing operator, all windows with end timestamp <= the watermark value are triggered

- **`WatermarkStrategy`**: determines how watermarks are generated from source events:
  - **`BoundedOutOfOrdernessStrategy`**: assumes events may arrive out of order by at most a configurable duration. The watermark is set to `max_event_timestamp - max_out_of_orderness`. This is the most common strategy and provides a balance between latency (lower bound means faster watermark advancement) and completeness (higher bound means fewer late events). Parameters: `max_out_of_orderness_ms`
  - **`MonotonousTimestampsStrategy`**: assumes events arrive in strictly increasing timestamp order. The watermark is set to `max_event_timestamp - 1`. Zero tolerance for out-of-order events. Used when the source guarantees ordering (e.g., a single partition with timestamp-ordered writes)
  - **`PunctuatedWatermarkStrategy`**: extracts watermarks from special punctuation events in the stream (e.g., a message with a watermark payload). Used when the source explicitly embeds watermark information in the data
  - **`IdleSourceDetection`**: if a source partition produces no events for a configurable duration, its watermark is advanced to the current processing time to prevent it from holding back the global watermark. Prevents idle partitions from stalling window computation across the entire pipeline

- **`WatermarkAlignment`**: at operators with multiple inputs (e.g., union, join), the effective watermark is the minimum of all input watermarks. This ensures that no window is triggered until all inputs have confirmed that no more events for that window's time range will arrive. Alignment prevents incorrect results when input streams have different event-time progress rates

### Exactly-Once Semantics via Checkpointing

Consistent state snapshots for fault-tolerant processing:

- **`CheckpointCoordinator`**: orchestrates periodic distributed snapshots of the entire processing pipeline using the Chandy-Lamport algorithm. At configurable intervals (default: 60 seconds), the coordinator injects a `CheckpointBarrier` into each source operator. As barriers flow through the operator graph, each operator snapshots its state (keyed state, operator state, window contents, timer registrations) to the state backend. When all operators have acknowledged the barrier, the checkpoint is considered complete and the coordinator records the checkpoint metadata (ID, timestamp, operator states, source positions). On failure, the coordinator restores the pipeline to the latest complete checkpoint, rolling back operator state and source positions. In-flight events between the checkpoint position and the failure point are replayed from the source

- **`CheckpointBarrier`**: a special stream element injected by the coordinator that flows through the operator graph. When an operator with multiple inputs receives a barrier from one input, it buffers events from that input until barriers arrive from all inputs (barrier alignment). This ensures that the snapshot captures a consistent cut across all operators. Unaligned checkpoints (an optimization where barriers pass through without alignment, using channel state to reconstruct consistency) are supported for latency-sensitive pipelines

- **`CheckpointStorage`**: persists checkpoint data to a configurable backend:
  - **`InMemoryCheckpointStorage`**: stores checkpoints in a Python dictionary. Fast but not durable -- checkpoints are lost on process restart. Suitable for development and testing
  - **`FileSystemCheckpointStorage`**: stores checkpoints to the platform's `FizzVFS` virtual filesystem. Durable across process restarts. Configurable checkpoint retention (number of checkpoints to keep, default: 3)

- **`RestartStrategy`**: defines how the pipeline recovers from failure:
  - **`FixedDelayRestartStrategy`**: restarts with a fixed delay between attempts. Parameters: `max_restarts` (maximum restart attempts before failing the job), `delay_ms` (delay between restarts)
  - **`ExponentialBackoffRestartStrategy`**: restarts with exponentially increasing delays. Parameters: `initial_delay_ms`, `max_delay_ms`, `backoff_multiplier`, `max_restarts`
  - **`NoRestartStrategy`**: fail immediately without restart. Used for pipelines where data loss is preferable to delayed processing

### Stateful Processing

Keyed state management for operators that maintain per-key state:

- **`StateDescriptor`**: declares a piece of keyed state with a name, type, and default value. State descriptors are registered in the operator's `open()` method and accessed during `process_element()`. Types:
  - **`ValueStateDescriptor[T]`**: a single value per key. Methods: `value() -> T`, `update(value: T)`, `clear()`
  - **`ListStateDescriptor[T]`**: an ordered list of values per key. Methods: `get() -> Iterable[T]`, `add(value: T)`, `add_all(values: Iterable[T])`, `update(values: Iterable[T])`, `clear()`
  - **`MapStateDescriptor[K, V]`**: a key-value map per key. Methods: `get(key: K) -> V`, `put(key: K, value: V)`, `contains(key: K) -> bool`, `remove(key: K)`, `keys() -> Iterable[K]`, `values() -> Iterable[V]`, `entries() -> Iterable[Tuple[K, V]]`, `clear()`
  - **`ReducingStateDescriptor[T]`**: a single value per key that is incrementally reduced. Each `add(value)` call applies the reduce function to merge the new value with the existing state. Methods: `get() -> T`, `add(value: T)`, `clear()`
  - **`AggregatingStateDescriptor[IN, ACC, OUT]`**: a single accumulator per key with separate input, accumulator, and output types. Methods: `get() -> OUT`, `add(value: IN)`, `clear()`

- **`StateBackend`**: the storage layer for keyed state:
  - **`HashMapStateBackend`**: stores all keyed state in a Python dictionary keyed by `(operator_uid, key, state_name)`. All state is held in memory. Fast access (O(1) lookup) but state size is bounded by available heap. State is serialized to the checkpoint storage during checkpointing using `pickle`. Suitable for pipelines with moderate state per key (< 100MB total)
  - **`RocksDBStateBackend`**: stores keyed state in an LSM-tree structure (implemented as a sorted dictionary with write-ahead log and level-based compaction). State is primarily on disk with a configurable in-memory write buffer and block cache. Supports state sizes exceeding available memory by spilling to disk. State is checkpointed by flushing the write-ahead log and copying SST files to checkpoint storage. Read performance degrades with state size (O(log N) lookup due to level traversal) but write performance remains consistent. Configurable parameters: `write_buffer_size_mb` (memtable size before flush), `max_write_buffers` (number of memtables before stall), `block_cache_size_mb` (LRU cache for frequently read blocks), `compaction_style` (leveled or universal)

- **`StateTTL`**: configurable time-to-live for keyed state entries. Expired entries are lazily cleaned up on access and proactively cleaned up during compaction (for RocksDBStateBackend). Parameters: `ttl_ms`, `update_type` (on create only, or on create and read/write), `cleanup_strategy` (full snapshot, incremental, or RocksDB compaction filter). Prevents unbounded state growth for keys that are no longer active

### Stream Joins

Correlating events across multiple streams:

- **`StreamStreamJoin`**: joins two keyed streams on their keys within a time-bounded window. For each element in stream A, the join finds all matching elements in stream B whose timestamps fall within a configurable time range relative to A's timestamp, and vice versa. The join produces an output element for each matching pair. Parameters: `lower_bound_ms` (how far back in time to look in the other stream), `upper_bound_ms` (how far forward in time to look). Both streams must be keyed by the same key type. The join maintains state for both streams, buffering elements until they can no longer participate in a join (determined by watermark advancement). Supports inner join, left outer join, right outer join, and full outer join semantics

- **`StreamTableJoin`**: joins a stream against a slowly-changing lookup table. The table is modeled as a `DataStream` of upsert events (`INSERT`, `UPDATE`, `DELETE`) that maintains a materialized view of the current table state in keyed state. Each element in the stream is enriched by looking up the current table entry for its key. This is a temporal join -- the stream element is joined against the table version that was current at the element's event time, not the latest version. Used for enriching real-time events with reference data (e.g., looking up rule configuration for a FizzBuzz evaluation). Parameters: `join_type` (inner or left outer)

- **`IntervalJoin`**: a specialized stream-stream join where the time bounds are asymmetric. Element `a` from stream A joins with element `b` from stream B if `a.timestamp + lower_bound <= b.timestamp <= a.timestamp + upper_bound`. More efficient than a general window join because it uses a targeted scan rather than buffering entire windows

### Complex Event Processing (CEP)

Pattern detection over event streams:

- **`Pattern`**: a declarative specification of a sequence of events to detect. Patterns are composed using a fluent API:

  ```
  pattern = Pattern.begin("start")
      .where(lambda e: e.result == "Fizz")
      .followed_by("middle")
      .where(lambda e: e.result == "Buzz")
      .followed_by("end")
      .where(lambda e: e.result == "FizzBuzz")
      .within(timedelta(seconds=30))
  ```

- **`PatternElement`**: a single stage in a pattern with a name, a condition (predicate), and a quantifier:
  - **`times(n)`**: match exactly N events satisfying the condition
  - **`times_or_more(n)`**: match N or more events (greedy)
  - **`optional()`**: match zero or one event
  - **`one_or_more()`**: match one or more events (greedy, with optional `.greedy()` or `.reluctant()` modifier)

- **`PatternSequence`**: the chaining operators between pattern elements:
  - **`followed_by(name)`**: strict contiguity -- the next matching event must immediately follow the previous match with no non-matching events in between
  - **`followed_by_any(name)`**: relaxed contiguity -- non-matching events may occur between matches
  - **`not_followed_by(name)`**: negation -- assert that a specific event does NOT occur between the previous and next match

- **`WithinConstraint`**: a temporal bound on the entire pattern. The complete pattern must match within the specified duration from the first event. If the duration expires before the pattern completes, the partial match is discarded

- **`PatternStream`**: the result of applying a `Pattern` to a `DataStream`. Provides methods to extract matched patterns: `select(handler)` where `handler` receives a dictionary mapping pattern element names to matched events. Unmatched events (events that started a match but timed out) can be routed to a side output via `select_timed_out(handler)`

- **`NFACompiler`**: compiles a `Pattern` specification into a nondeterministic finite automaton (NFA) for efficient pattern matching. The NFA represents each pattern element as a state with transitions guarded by the element's condition. The compiler handles quantifiers (one-or-more creates a self-loop), contiguity (strict contiguity requires no intervening non-matching events), and negation (not-followed-by adds a rejection state). The compiled NFA is executed by the `CEPOperator` against the event stream, maintaining partial match state for each active pattern instance

- **`CEPOperator`**: a stateful stream operator that runs the compiled NFA against incoming events. Maintains a set of active partial matches in keyed state. For each incoming event, advances all partial matches whose current state has a transition that accepts the event. Creates new partial matches when the event satisfies the initial state's condition. Completes matches when a partial match reaches the NFA's accepting state. Times out matches whose duration exceeds the `within` constraint. The operator checkpoints its partial match state for fault tolerance

### Backpressure Handling

Flow control to prevent fast operators from overwhelming slow operators:

- **`BackpressureController`**: monitors the buffer occupancy of each operator's input queue. When an operator's input buffer exceeds the high watermark threshold (default: 80% capacity), the controller signals upstream operators to reduce their output rate. When the buffer drops below the low watermark threshold (default: 50% capacity), normal processing resumes. The backpressure signal propagates backward through the operator graph until it reaches the source, which reduces its ingestion rate

- **`CreditBasedFlowControl`**: implements a credit-based flow control protocol between operators. Each downstream operator issues credits to its upstream operator, representing the number of elements it is willing to receive. The upstream operator sends at most `credits` elements before waiting for more credits. This prevents buffer overflow without requiring explicit high/low watermark monitoring. Credits are replenished when the downstream operator processes elements from its input buffer

- **`BufferPool`**: manages a fixed-size pool of network buffers for inter-operator communication. When the pool is exhausted (all buffers are in use by operators), requesting operators block until a buffer is returned, creating natural backpressure. Buffer size and pool size are configurable. The pool uses a lock-free ring buffer for allocation and deallocation to minimize contention

### Savepoints

Planned state snapshots for version upgrades and topology changes:

- **`SavepointManager`**: creates and manages savepoints -- externally triggered, named checkpoints that are retained indefinitely (unlike regular checkpoints which are automatically garbage collected). A savepoint captures the complete processing state: operator state, window contents, timer registrations, and source positions. Savepoints are identified by a user-provided name and stored in the checkpoint storage with a manifest listing all operator states and their storage locations

- **`SavepointRestoreManager`**: restores a pipeline from a savepoint. Maps operator state from the savepoint to the current pipeline topology using operator UIDs. Handles topology changes: new operators start with empty state, removed operators' state is ignored, repartitioned operators' state is redistributed across the new parallelism. Reports warnings for unmatched state (state in the savepoint that has no corresponding operator in the new topology) and missing state (operators in the new topology that have no corresponding state in the savepoint)

- **Upgrade workflow**: to upgrade a pipeline to a new version: (1) trigger a savepoint, (2) cancel the current job, (3) deploy the new job version, (4) restore from the savepoint. This workflow enables zero-downtime upgrades with exactly-once guarantees -- no events are lost or duplicated during the upgrade because the savepoint records the exact source position and operator state at the time of the snapshot

### Dynamic Scaling

Runtime adjustment of operator parallelism:

- **`ScaleManager`**: adjusts the parallelism of individual operators without stopping the pipeline. Scaling up adds new operator instances and redistributes keyed state across the expanded instance set using consistent hashing. Scaling down removes operator instances and migrates their keyed state to remaining instances. The scaling operation is coordinated through a savepoint: the manager triggers a savepoint, stops the affected operators, restarts them with the new parallelism and redistributed state, and resumes processing from the savepoint position

- **`AutoScaler`**: monitors operator throughput and backpressure metrics to automatically adjust parallelism. When an operator's throughput drops below a configurable threshold while backpressure is detected (indicating the operator is the bottleneck), the autoscaler increases its parallelism. When an operator's throughput exceeds its input rate with low utilization, the autoscaler decreases its parallelism to conserve resources. Parameters: `scale_up_threshold` (backpressure duration before scaling up), `scale_down_threshold` (idle duration before scaling down), `min_parallelism`, `max_parallelism`, `cooldown_ms` (minimum duration between scaling operations)

- **`KeyGroupAssigner`**: maps keys to key groups, and key groups to operator instances. Key groups are the unit of state redistribution during scaling. The total number of key groups is fixed at pipeline creation (default: 128, configurable as `max_parallelism`) and must be greater than or equal to any parallelism setting. When parallelism changes, key groups are reassigned to operator instances using consistent hashing, and the corresponding keyed state is migrated. This two-level mapping (key -> key group -> operator instance) ensures that scaling only moves state for the affected key groups, not all keys

### Integration Points

Connections to existing platform subsystems:

- **Message Queue Integration**: `MessageQueueSource` reads from message queue `Topic` partitions via the existing `Consumer` and `ConsumerGroup` classes. `MessageQueueSink` writes to message queue `Topic` partitions via the existing `Producer` class. The source participates in consumer group rebalancing and reports consumed offsets during checkpointing. The sink uses the producer's idempotency layer for exactly-once production. Five default streaming topics are created: `fizzbuzz.stream.evaluations` (real-time evaluation results), `fizzbuzz.stream.metrics` (continuous metric emissions), `fizzbuzz.stream.alerts` (threshold violations and anomalies), `fizzbuzz.stream.audit` (compliance-relevant events), `fizzbuzz.stream.lifecycle` (container and service lifecycle events)

- **Event Sourcing Integration**: `EventStoreSource` tails the `EventStore` journal, reading domain events as a continuous stream. `EventStoreSink` appends computed stream results as new domain events via the `EventStore.append()` method. This enables event-driven architectures where stream processing results are themselves events that can be projected, queried, and replayed. The source uses the event store's sequence numbers for checkpointing and recovery

- **FizzSQL Integration**: `StreamSQLBridge` extends the `FizzSQLEngine` with streaming SQL semantics. Streaming SQL queries are parsed by the existing `SQLParser` with extensions for window functions (`TUMBLE(event_time, INTERVAL '1' MINUTE)`, `HOP(event_time, INTERVAL '10' SECOND, INTERVAL '1' MINUTE)`, `SESSION(event_time, INTERVAL '30' SECOND)`), continuous emission (`EMIT AFTER WATERMARK`, `EMIT WITH DELAY INTERVAL '5' SECOND`), and streaming joins (`JOIN stream_b ON a.key = b.key AND a.event_time BETWEEN b.event_time - INTERVAL '5' MINUTE AND b.event_time + INTERVAL '5' MINUTE`). SQL queries are compiled into `DataStream` operator graphs and executed by the `StreamExecutionEnvironment`

### Metrics and Monitoring

Operational visibility into stream processing pipelines:

- **`StreamMetricsCollector`**: collects per-operator metrics: input rate (events/second), output rate, processing latency (p50, p95, p99), backpressure time (percentage of time the operator was backpressured), buffer utilization, checkpoint duration, state size, and watermark lag (difference between current event time and current processing time). Metrics are exposed via the platform's OpenTelemetry integration and rendered in the `FizzStreamDashboard`

- **`FizzStreamDashboard`**: an ASCII dashboard displaying real-time pipeline status: operator topology (directed graph rendered as ASCII art), per-operator throughput and latency, watermark positions, checkpoint history (last successful, last failed, average duration), backpressure indicators, and active jobs with their execution state. The dashboard updates at configurable intervals (default: 5 seconds) and can be displayed via the `--fizzstream-dashboard` CLI flag

### FizzStream Middleware

- **`FizzStreamMiddleware`**: integrates with the middleware pipeline at priority 38 (after caching, before MapReduce). For each FizzBuzz evaluation, the middleware emits the evaluation result as an event to the `fizzbuzz.stream.evaluations` topic, feeding the stream processing pipeline. The middleware also queries active stream processing jobs to annotate the evaluation context with real-time aggregates (current evaluation rate, classification distribution in the last window, anomaly detection status)

### CLI Flags

- `--fizzstream`: enable the FizzStream subsystem
- `--fizzstream-job <job_definition.yaml>`: submit a stream processing job defined in YAML
- `--fizzstream-sql <query>`: execute a streaming SQL query
- `--fizzstream-list-jobs`: list all active and completed jobs with status
- `--fizzstream-cancel <job_id>`: cancel a running job
- `--fizzstream-savepoint <job_id> <name>`: trigger a savepoint for a running job
- `--fizzstream-restore <job_id> <savepoint>`: restore a job from a savepoint
- `--fizzstream-scale <job_id> <operator> <parallelism>`: adjust operator parallelism
- `--fizzstream-metrics <job_id>`: display per-operator metrics for a job
- `--fizzstream-dashboard`: display the real-time ASCII pipeline dashboard
- `--fizzstream-checkpoint-interval <ms>`: configure checkpoint interval (default: 60000)
- `--fizzstream-state-backend <hashmap|rocksdb>`: select state backend (default: hashmap)
- `--fizzstream-watermark-interval <ms>`: configure watermark emission interval (default: 200)
- `--fizzstream-parallelism <n>`: configure default operator parallelism (default: 4)
- `--fizzstream-max-parallelism <n>`: configure maximum parallelism / key group count (default: 128)
- `--fizzstream-buffer-timeout <ms>`: configure buffer flush timeout (default: 100)
- `--fizzstream-restart-strategy <fixed|exponential|none>`: configure restart strategy (default: fixed)

## Why This Is Necessary

Because the Enterprise FizzBuzz Platform generates continuous event streams from 116 infrastructure modules and has no mechanism to process them in real time. The message queue can transport events. MapReduce can process bounded datasets. The event store can record and replay events. FizzSQL can query stored data. None of these systems can perform continuous, stateful computation over unbounded event sequences with exactly-once guarantees, event-time semantics, and windowed aggregation.

Consider the operational requirements: monitoring the platform's health requires computing sliding-window averages over metric streams. Detecting anomalous FizzBuzz evaluation patterns requires stateful pattern matching over the evaluation event stream. Enriching evaluation results with real-time rule configuration requires stream-table joins between the evaluation stream and the rule configuration changelog. Computing per-second classification distributions for the SLA monitoring system requires tumbling window aggregation over the evaluation stream. Correlating container lifecycle events with evaluation latency spikes requires temporal joins between the container event stream and the metrics stream. Detecting compliance-relevant event sequences (three consecutive failed evaluations followed by a configuration change within 60 seconds) requires complex event processing with temporal constraints.

MapReduce computes these answers eventually. FizzStream computes them continuously. The difference between batch and stream is the difference between an autopsy and a vital signs monitor. Both provide information. Only one provides it while the patient is still alive.

## Estimated Scale

~3,500 lines of stream processing engine, ~350 lines of DataStream API and execution environment (DataStream, StreamExecutionEnvironment, StreamOperator lifecycle, operator chaining, job compilation), ~300 lines of source operators (MessageQueueSource with partition tracking and offset checkpointing, EventStoreSource with journal tailing, ContainerEventSource, MetricSource, GeneratorSource), ~250 lines of transformation operators (Map, FlatMap, Filter, KeyBy with consistent hashing, Reduce, Process with timers and state access, Union), ~400 lines of windowing system (TumblingEventTimeWindow, SlidingEventTimeWindow, SessionWindow, GlobalWindow, WindowAssigner, Trigger hierarchy, WindowFunction variants, AllowedLateness, late element side output), ~250 lines of watermark system (Watermark propagation, BoundedOutOfOrdernessStrategy, MonotonousTimestampsStrategy, PunctuatedWatermarkStrategy, IdleSourceDetection, WatermarkAlignment across multi-input operators), ~350 lines of checkpointing (CheckpointCoordinator with Chandy-Lamport, CheckpointBarrier with alignment, InMemoryCheckpointStorage, FileSystemCheckpointStorage, RestartStrategy hierarchy), ~300 lines of stateful processing (ValueState, ListState, MapState, ReducingState, AggregatingState, HashMapStateBackend, RocksDBStateBackend with LSM tree, StateTTL), ~200 lines of stream joins (StreamStreamJoin with time-bounded buffer, StreamTableJoin with materialized view, IntervalJoin), ~250 lines of CEP (Pattern fluent API, PatternElement quantifiers, PatternSequence contiguity, NFACompiler, CEPOperator with partial match state), ~100 lines of backpressure (BackpressureController, CreditBasedFlowControl, BufferPool), ~100 lines of savepoints (SavepointManager, SavepointRestoreManager, topology change handling), ~100 lines of dynamic scaling (ScaleManager, AutoScaler, KeyGroupAssigner with consistent hashing), ~150 lines of integration (MessageQueueSink, EventStoreSink, StreamSQLBridge with window SQL extensions), ~150 lines of metrics and dashboard (StreamMetricsCollector, FizzStreamDashboard ASCII rendering), ~150 lines of middleware and CLI integration, ~500 tests. Total: ~5,400 lines.

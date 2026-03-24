"""
Enterprise FizzBuzz Platform - FizzStream Stream Processing Exceptions (EFP-STR00 through EFP-STR24)
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


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


class StreamCheckpointError(StreamProcessingError):
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


class StreamCheckpointRestoreError(StreamProcessingError):
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


class StreamSavepointError(StreamProcessingError):
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


class StreamSavepointRestoreError(StreamProcessingError):
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

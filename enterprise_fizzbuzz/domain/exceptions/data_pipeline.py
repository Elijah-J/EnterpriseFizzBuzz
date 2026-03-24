"""
Enterprise FizzBuzz Platform - Data Pipeline & ETL Framework Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DataPipelineError(FizzBuzzError):
    """Base exception for all Data Pipeline & ETL Framework errors.

    When your data pipeline for routing integers through modulo
    arithmetic encounters a failure, you've achieved a level of
    data engineering theatre that would make even the most seasoned
    Apache Spark administrator raise an eyebrow. These exceptions
    cover everything from source connector failures to DAG
    resolution deadlocks to the existential crisis of a backfill
    engine that realizes it's re-enriching data that was already
    perfectly fine.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DP00"),
            context=kwargs.pop("context", {}),
        )


class SourceConnectorError(DataPipelineError):
    """Raised when a source connector fails to produce records.

    The source connector — which wraps Python's built-in range()
    function behind three layers of abstraction — has encountered
    an error. Perhaps the range was empty, perhaps the integers
    refused to be extracted, or perhaps range() itself has finally
    given up after years of faithful service.
    """

    def __init__(self, connector_name: str, reason: str) -> None:
        super().__init__(
            f"Source connector '{connector_name}' failed: {reason}. "
            f"The integers could not be coaxed out of their source.",
            error_code="EFP-DP01",
            context={"connector_name": connector_name, "reason": reason},
        )


class SinkConnectorError(DataPipelineError):
    """Raised when a sink connector fails to consume records.

    The sink connector — whose sole job is to print numbers or
    discard them entirely — has somehow failed at this Herculean
    task. If a DevNullSink fails, the laws of computer science
    have been violated at a fundamental level.
    """

    def __init__(self, connector_name: str, reason: str) -> None:
        super().__init__(
            f"Sink connector '{connector_name}' failed: {reason}. "
            f"The data had nowhere to go and nowhere to be.",
            error_code="EFP-DP02",
            context={"connector_name": connector_name, "reason": reason},
        )


class ValidationStageError(DataPipelineError):
    """Raised when a record fails pipeline validation.

    The validation stage has determined that a number is not
    emotionally ready for FizzBuzz evaluation. This is less about
    type-checking and more about ensuring that every integer has
    the psychological fortitude to endure being divided by 3 and 5.
    """

    def __init__(self, record_id: str, reason: str) -> None:
        super().__init__(
            f"Record '{record_id}' failed validation: {reason}. "
            f"The number was not emotionally prepared for the pipeline.",
            error_code="EFP-DP03",
            context={"record_id": record_id, "reason": reason},
        )


class TransformStageError(DataPipelineError):
    """Raised when the transform stage fails to evaluate FizzBuzz.

    The transform stage — which wraps the StandardRuleEngine that
    wraps modulo arithmetic — has encountered an error during
    FizzBuzz evaluation. This is the pipeline equivalent of a
    factory assembly line grinding to a halt because a bolt
    refuses to be bolted.
    """

    def __init__(self, record_id: str, number: int, reason: str) -> None:
        super().__init__(
            f"Transform failed for record '{record_id}' (number={number}): "
            f"{reason}. The modulo operator has declined to cooperate.",
            error_code="EFP-DP04",
            context={"record_id": record_id, "number": number, "reason": reason},
        )


class EnrichStageError(DataPipelineError):
    """Raised when the enrichment stage fails to decorate a record.

    The enrichment engine attempted to add Fibonacci membership,
    primality analysis, Roman numeral conversion, and emotional
    valence to a humble integer. One of these enrichments failed,
    leaving the record in a state of incomplete decoration — the
    data engineering equivalent of leaving the house with only
    one earring.
    """

    def __init__(self, record_id: str, enrichment: str, reason: str) -> None:
        super().__init__(
            f"Enrichment '{enrichment}' failed for record '{record_id}': "
            f"{reason}. The record will proceed with diminished metadata.",
            error_code="EFP-DP05",
            context={"record_id": record_id, "enrichment": enrichment, "reason": reason},
        )


class LoadStageError(DataPipelineError):
    """Raised when the load stage fails to deliver a record to its sink.

    The final stage of the pipeline — the part that actually outputs
    the FizzBuzz result — has failed. The entire five-stage pipeline
    executed flawlessly, only for the result to be lost at the very
    end. This is the data pipeline equivalent of running a marathon
    and tripping at the finish line.
    """

    def __init__(self, record_id: str, sink_name: str, reason: str) -> None:
        super().__init__(
            f"Load to sink '{sink_name}' failed for record '{record_id}': "
            f"{reason}. The data completed its journey but had nowhere to land.",
            error_code="EFP-DP06",
            context={"record_id": record_id, "sink_name": sink_name, "reason": reason},
        )


class DAGResolutionError(DataPipelineError):
    """Raised when the pipeline DAG cannot be topologically sorted.

    Kahn's algorithm has encountered a cycle in what should be a
    perfectly linear five-stage pipeline. Finding a cycle in a
    linear chain is mathematically impossible, which makes this
    error either a sign of cosmic interference or a very creative
    misconfiguration. Either way, the topological sort has failed
    and the pipeline refuses to execute out of principle.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"DAG resolution failed: {reason}. Kahn's algorithm is "
            f"disappointed in your graph construction choices.",
            error_code="EFP-DP07",
            context={"reason": reason},
        )


class CheckpointError(DataPipelineError):
    """Raised when a pipeline checkpoint operation fails.

    The checkpoint system — which saves pipeline state to RAM for
    recovery purposes — has encountered a failure. Since the
    checkpoints are stored in the same memory that would be lost
    in a crash, the recovery guarantees are approximately as
    reliable as a chocolate teapot.
    """

    def __init__(self, stage_name: str, reason: str) -> None:
        super().__init__(
            f"Checkpoint failed at stage '{stage_name}': {reason}. "
            f"Pipeline state has not been saved. Recovery is now "
            f"even more theoretical than it already was.",
            error_code="EFP-DP08",
            context={"stage_name": stage_name, "reason": reason},
        )


class BackfillError(DataPipelineError):
    """Raised when the retroactive backfill engine encounters an error.

    The backfill engine attempted to retroactively enrich records
    that had already been processed, because apparently the initial
    enrichment wasn't enriching enough. This second pass through
    the enrichment stage has failed, leaving records in a state
    of partial re-enrichment — enrichment purgatory, if you will.
    """

    def __init__(self, record_id: str, reason: str) -> None:
        super().__init__(
            f"Backfill failed for record '{record_id}': {reason}. "
            f"The retroactive enrichment has been retro-actively abandoned.",
            error_code="EFP-DP09",
            context={"record_id": record_id, "reason": reason},
        )


class LineageTrackingError(DataPipelineError):
    """Raised when the data lineage tracker loses track of provenance.

    The provenance chain for a data record has been broken. The
    lineage tracker can no longer determine where this number came
    from, what transformations it underwent, or how it arrived at
    its current enriched state. This is the data governance
    equivalent of losing the chain of custody for evidence — except
    the evidence is that 15 is divisible by both 3 and 5.
    """

    def __init__(self, record_id: str, reason: str) -> None:
        super().__init__(
            f"Lineage tracking failed for record '{record_id}': {reason}. "
            f"The provenance chain has been severed. Data governance "
            f"officers have been notified (they haven't).",
            error_code="EFP-DP10",
            context={"record_id": record_id, "reason": reason},
        )


class PipelineStageRetryExhaustedError(DataPipelineError):
    """Raised when a pipeline stage has exhausted all retry attempts.

    The stage tried its best. It retried the configured number of
    times with exponential backoff. It gave the operation every
    chance to succeed. But sometimes, modulo arithmetic just
    doesn't want to cooperate, and you have to accept that some
    numbers were never meant to be FizzBuzzed.
    """

    def __init__(self, stage_name: str, attempts: int, last_error: str) -> None:
        super().__init__(
            f"Stage '{stage_name}' exhausted all {attempts} retry attempts. "
            f"Last error: {last_error}. The pipeline has given up on this "
            f"record with the quiet dignity of a failed unit test.",
            error_code="EFP-DP11",
            context={"stage_name": stage_name, "attempts": attempts, "last_error": last_error},
        )


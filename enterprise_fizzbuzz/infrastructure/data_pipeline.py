"""
Enterprise FizzBuzz Platform - Data Pipeline & ETL Framework Module

Implements a fully enterprise-grade Extract-Transform-Load pipeline for
FizzBuzz evaluation, because routing integers through five abstraction
layers is exactly what the data engineering community has been asking for.

The pipeline consists of five stages arranged in a Directed Acyclic Graph
(DAG) that happens to be a linear chain -- making the topological sort
maximally pointless but architecturally impressive. Each number is wrapped
in a DataRecord with full provenance tracking, enriched with Fibonacci
membership, primality analysis, Roman numeral conversion, and emotional
valence, then loaded into a sink that either prints the result or
discards it entirely.

Key architectural decisions:
- The Extract stage wraps Python's range() behind a SourceConnector interface,
  because calling range() directly would be insufficiently enterprise.
- The Transform stage uses the REAL StandardRuleEngine for FizzBuzz evaluation,
  proving that somewhere beneath all this ceremony, actual modulo arithmetic
  still occurs.
- The Enrich stage assigns emotional valence to numbers based on n % 100,
  because data without feelings is just noise.
- The DAG is resolved using Kahn's algorithm for topological sorting, which
  is absolutely necessary for a five-node linear chain with no branches,
  no fan-out, and no conceivable reason to use topological sort.
- The DevNullSink provides "full pipeline, zero output" -- the enterprise
  equivalent of running a marathon and choosing not to cross the finish line.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BackfillError,
    CheckpointError,
    DAGResolutionError,
    DataPipelineError,
    EnrichStageError,
    LineageTrackingError,
    LoadStageError,
    PipelineDashboardRenderError,
    PipelineStageRetryExhaustedError,
    SinkConnectorError,
    SourceConnectorError,
    TransformStageError,
    ValidationStageError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================

class PipelineStageType(Enum):
    """The five sacred stages of the FizzBuzz ETL pipeline.

    Every number must traverse this gauntlet in order, because
    enterprise data processing demands ceremony above all else.
    """
    EXTRACT = auto()
    VALIDATE = auto()
    TRANSFORM = auto()
    ENRICH = auto()
    LOAD = auto()


class RecordStatus(Enum):
    """Lifecycle status of a DataRecord as it flows through the pipeline.

    PENDING:    The record has been created but not yet processed.
    EXTRACTED:  The record has been pulled from the source connector.
    VALIDATED:  The record has been deemed emotionally and typologically ready.
    TRANSFORMED: The record has undergone FizzBuzz evaluation.
    ENRICHED:   The record has been decorated with supplementary metadata.
    LOADED:     The record has been delivered to the sink connector.
    FAILED:     The record encountered an error and was abandoned by the pipeline.
    """
    PENDING = auto()
    EXTRACTED = auto()
    VALIDATED = auto()
    TRANSFORMED = auto()
    ENRICHED = auto()
    LOADED = auto()
    FAILED = auto()


class EmotionalValence(Enum):
    """Emotional classification of a number based on vibes and modulo.

    Because every number has feelings, and ignoring those feelings
    is a data governance violation of the highest order.
    """
    ECSTATIC = "ecstatic"
    JOYFUL = "joyful"
    CONTENT = "content"
    NEUTRAL = "neutral"
    MELANCHOLY = "melancholy"
    ANXIOUS = "anxious"
    DESPONDENT = "despondent"


# ============================================================
# Data Records & Lineage
# ============================================================

@dataclass
class LineageEntry:
    """A single entry in the data provenance chain.

    Every transformation, enrichment, and stage transition is
    recorded here with nanosecond precision, because the auditors
    need to know exactly when the number 15 was classified as
    'FizzBuzz' and by whom (the StandardRuleEngine, always).

    Attributes:
        stage: Which pipeline stage produced this entry.
        operation: A description of the operation performed.
        timestamp: When the operation occurred (UTC).
        duration_ns: How long the operation took in nanoseconds.
        details: Additional metadata about the operation.
    """
    stage: str
    operation: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ns: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataRecord:
    """A record carrying a number through the ETL pipeline.

    This is the fundamental unit of data flow in the Enterprise
    FizzBuzz Data Pipeline. Each number is wrapped in a DataRecord
    with a unique ID, full metadata dictionary, lineage chain, and
    lifecycle status tracking. Because passing an integer to a
    function would be insufficiently traceable.

    Attributes:
        record_id: Unique identifier for this record instance.
        number: The actual integer being processed (the only field that matters).
        metadata: Arbitrary key-value metadata accumulated during pipeline stages.
        lineage: Ordered list of provenance entries tracking the record's journey.
        status: Current lifecycle status of the record.
        fizzbuzz_result: The FizzBuzz evaluation result (populated during TRANSFORM).
        enrichments: Additional enrichment data (populated during ENRICH).
        created_at: When this record was created (UTC).
        error: Error message if the record failed processing.
        batch_id: Identifier for the batch this record belongs to.
    """
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    lineage: list[LineageEntry] = field(default_factory=list)
    status: RecordStatus = RecordStatus.PENDING
    fizzbuzz_result: Optional[FizzBuzzResult] = None
    enrichments: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None
    batch_id: Optional[str] = None

    def add_lineage(
        self,
        stage: str,
        operation: str,
        duration_ns: int = 0,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append a lineage entry to this record's provenance chain."""
        self.lineage.append(LineageEntry(
            stage=stage,
            operation=operation,
            duration_ns=duration_ns,
            details=details or {},
        ))


# ============================================================
# Source Connectors
# ============================================================

class SourceConnector:
    """Abstract base for pipeline source connectors.

    A source connector extracts records from an external system
    (in our case, Python's range() function) and feeds them into
    the pipeline as DataRecords. The abstraction exists so that
    we can, in theory, swap out range() for a database cursor,
    a Kafka consumer, or a random number generator without
    changing the pipeline code. In practice, we will never do this.
    """

    def extract(self, start: int, end: int) -> list[DataRecord]:
        """Extract records from the source."""
        raise NotImplementedError

    def get_name(self) -> str:
        """Return the connector's display name."""
        raise NotImplementedError


class RangeSource(SourceConnector):
    """Source connector that wraps Python's range() function.

    This connector provides enterprise-grade access to sequential
    integers by invoking range(start, end + 1) and wrapping each
    integer in a DataRecord with full metadata and a unique UUID.
    The overhead-to-value ratio is approximately infinity.
    """

    def extract(self, start: int, end: int) -> list[DataRecord]:
        """Extract integers from the range and wrap them in DataRecords."""
        records = []
        batch_id = str(uuid.uuid4())
        for n in range(start, end + 1):
            record = DataRecord(
                number=n,
                batch_id=batch_id,
                metadata={
                    "source": "range",
                    "source_range": f"[{start}, {end}]",
                    "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            record.status = RecordStatus.EXTRACTED
            record.add_lineage(
                stage="Extract",
                operation=f"Extracted integer {n} from range({start}, {end + 1})",
                details={"source_type": "range", "batch_id": batch_id},
            )
            records.append(record)
        return records

    def get_name(self) -> str:
        return "RangeSource"


class DevNullSource(SourceConnector):
    """Source connector that produces nothing.

    The source equivalent of /dev/null. Extracts zero records,
    resulting in a pipeline that processes exactly nothing.
    Useful for testing pipeline infrastructure without the
    burden of actual data, or for those days when you just
    can't deal with integers.
    """

    def extract(self, start: int, end: int) -> list[DataRecord]:
        """Return an empty list. The void gives nothing."""
        return []

    def get_name(self) -> str:
        return "DevNullSource"


# ============================================================
# Sink Connectors
# ============================================================

class SinkConnector:
    """Abstract base for pipeline sink connectors.

    A sink connector receives processed DataRecords at the end
    of the pipeline and delivers them to their final destination.
    In enterprise data engineering, sinks write to databases,
    data lakes, or message queues. Here, they print to stdout
    or discard the data entirely.
    """

    def load(self, record: DataRecord) -> bool:
        """Load a record into the sink. Returns True on success."""
        raise NotImplementedError

    def get_name(self) -> str:
        """Return the connector's display name."""
        raise NotImplementedError

    def flush(self) -> None:
        """Flush any buffered records."""
        pass

    def get_loaded_records(self) -> list[DataRecord]:
        """Return all successfully loaded records."""
        return []


class StdoutSink(SinkConnector):
    """Sink connector that outputs records to stdout.

    The pipeline's grand finale: after five stages of extraction,
    validation, transformation, enrichment, and loading ceremony,
    the result is printed to the terminal. Just like a simple
    print() statement would have done, but with 800 more lines
    of supporting infrastructure.
    """

    def __init__(self) -> None:
        self._loaded: list[DataRecord] = []

    def load(self, record: DataRecord) -> bool:
        """Print the FizzBuzz result to stdout."""
        if record.fizzbuzz_result is not None:
            # We don't actually print here -- the middleware handles output
            self._loaded.append(record)
            return True
        return False

    def get_name(self) -> str:
        return "StdoutSink"

    def get_loaded_records(self) -> list[DataRecord]:
        return list(self._loaded)


class DevNullSink(SinkConnector):
    """Sink connector that discards all records.

    Full pipeline, zero output. Every number is extracted, validated,
    transformed, enriched, and then... discarded. The entire five-stage
    ETL process executes with perfect fidelity, only for the results
    to be silently swallowed by the void. This is the enterprise data
    pipeline equivalent of running a dishwasher with no dishes inside.

    But the lineage was tracked. The checkpoints were saved. The DAG
    was resolved. And that's what really matters.
    """

    def __init__(self) -> None:
        self._loaded: list[DataRecord] = []

    def load(self, record: DataRecord) -> bool:
        """Accept the record into the void. Always succeeds."""
        self._loaded.append(record)
        return True

    def get_name(self) -> str:
        return "DevNullSink"

    def get_loaded_records(self) -> list[DataRecord]:
        return list(self._loaded)


# ============================================================
# Pipeline Stages
# ============================================================

class PipelineStage:
    """Base class for pipeline stages.

    Each stage receives a list of DataRecords, processes them,
    and returns the (possibly modified) records for the next stage.
    Stages are composable and can be arranged in any DAG topology,
    though our DAG is always a linear chain because five-way fan-out
    for FizzBuzz would be insane even by our standards.
    """

    def __init__(self, stage_type: PipelineStageType) -> None:
        self._stage_type = stage_type
        self._records_processed = 0
        self._total_duration_ns = 0
        self._errors: list[str] = []

    @property
    def stage_type(self) -> PipelineStageType:
        return self._stage_type

    @property
    def name(self) -> str:
        return self._stage_type.name.capitalize()

    @property
    def records_processed(self) -> int:
        return self._records_processed

    @property
    def total_duration_ns(self) -> int:
        return self._total_duration_ns

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def process(self, records: list[DataRecord]) -> list[DataRecord]:
        """Process records through this stage."""
        raise NotImplementedError

    def get_statistics(self) -> dict[str, Any]:
        """Return stage processing statistics."""
        avg_ns = self._total_duration_ns / max(1, self._records_processed)
        return {
            "stage": self.name,
            "records_processed": self._records_processed,
            "total_duration_ns": self._total_duration_ns,
            "total_duration_ms": self._total_duration_ns / 1_000_000,
            "avg_duration_ns": avg_ns,
            "avg_duration_ms": avg_ns / 1_000_000,
            "errors": len(self._errors),
        }


class ExtractStage(PipelineStage):
    """Extract stage: pulls numbers from a SourceConnector.

    The first stage of the pipeline. Takes a range of numbers and
    converts them into DataRecords using the configured source
    connector. For RangeSource, this is equivalent to calling
    range() and wrapping each integer in a dataclass. For
    DevNullSource, this does nothing. Both are valid enterprise
    data extraction strategies.
    """

    def __init__(self, source: SourceConnector) -> None:
        super().__init__(PipelineStageType.EXTRACT)
        self._source = source

    def process(self, records: list[DataRecord]) -> list[DataRecord]:
        """Extract records from the source connector.

        Note: For the Extract stage, the input records list contains
        placeholder records with just the numbers set. The source
        connector creates proper DataRecords.
        """
        start_ns = time.perf_counter_ns()
        # records passed in already have numbers; just mark them as extracted
        for record in records:
            record.status = RecordStatus.EXTRACTED
            record.add_lineage(
                stage=self.name,
                operation=f"Extracted number {record.number}",
                details={"source": self._source.get_name()},
            )
            self._records_processed += 1
        elapsed = time.perf_counter_ns() - start_ns
        self._total_duration_ns += elapsed
        return records


class ValidateStage(PipelineStage):
    """Validate stage: ensures records are pipeline-worthy.

    Validates that each record contains an integer and that the
    number is "emotionally ready" for FizzBuzz evaluation. The
    emotional readiness check always returns True, because every
    integer is emotionally ready -- they just don't know it yet.
    """

    def __init__(self) -> None:
        super().__init__(PipelineStageType.VALIDATE)

    def _is_emotionally_ready(self, number: int) -> bool:
        """Check if a number is emotionally ready for FizzBuzz.

        All numbers are emotionally ready. They were born ready.
        This check exists purely to demonstrate that our validation
        stage does more than just isinstance(n, int).
        """
        return True

    def process(self, records: list[DataRecord]) -> list[DataRecord]:
        """Validate each record for type safety and emotional readiness."""
        start_ns = time.perf_counter_ns()
        valid_records = []
        for record in records:
            if record.status == RecordStatus.FAILED:
                valid_records.append(record)
                continue

            # Type check
            if not isinstance(record.number, int):
                record.status = RecordStatus.FAILED
                record.error = f"Expected int, got {type(record.number).__name__}"
                record.add_lineage(
                    stage=self.name,
                    operation=f"FAILED: type check ({record.error})",
                )
                self._errors.append(record.error)
                valid_records.append(record)
                continue

            # Emotional readiness check
            emotionally_ready = self._is_emotionally_ready(record.number)
            record.metadata["emotionally_ready"] = emotionally_ready
            record.status = RecordStatus.VALIDATED
            record.add_lineage(
                stage=self.name,
                operation=f"Validated number {record.number} (emotionally ready: {emotionally_ready})",
                details={"type_check": "passed", "emotional_readiness": emotionally_ready},
            )
            self._records_processed += 1
            valid_records.append(record)

        elapsed = time.perf_counter_ns() - start_ns
        self._total_duration_ns += elapsed
        return valid_records


class TransformStage(PipelineStage):
    """Transform stage: applies FizzBuzz evaluation via the REAL rules engine.

    This is where the actual FizzBuzz computation happens. The
    Transform stage wraps the StandardRuleEngine and feeds each
    number through the rule evaluation pipeline. After four stages
    of ceremony, abstraction, and enterprise theatre, the modulo
    operator finally gets to do its job.
    """

    def __init__(self, rules: Optional[list[RuleDefinition]] = None) -> None:
        super().__init__(PipelineStageType.TRANSFORM)
        self._engine = StandardRuleEngine()
        if rules is None:
            rules = [
                RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
                RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
            ]
        self._rules = [ConcreteRule(r) for r in rules]

    def process(self, records: list[DataRecord]) -> list[DataRecord]:
        """Apply FizzBuzz transformation to each validated record."""
        start_ns = time.perf_counter_ns()
        for record in records:
            if record.status == RecordStatus.FAILED:
                continue
            if record.status != RecordStatus.VALIDATED:
                continue

            eval_start = time.perf_counter_ns()
            try:
                result = self._engine.evaluate(record.number, self._rules)
                record.fizzbuzz_result = result
                record.status = RecordStatus.TRANSFORMED
                record.metadata["fizzbuzz_output"] = result.output
                record.metadata["matched_rules"] = [
                    m.rule.name for m in result.matched_rules
                ]
                eval_elapsed = time.perf_counter_ns() - eval_start
                record.add_lineage(
                    stage=self.name,
                    operation=f"Transformed {record.number} -> '{result.output}'",
                    duration_ns=eval_elapsed,
                    details={
                        "output": result.output,
                        "matched_rules": len(result.matched_rules),
                        "strategy": "StandardRuleEngine",
                    },
                )
                self._records_processed += 1
            except Exception as e:
                record.status = RecordStatus.FAILED
                record.error = str(e)
                record.add_lineage(
                    stage=self.name,
                    operation=f"FAILED: transform error ({e})",
                )
                self._errors.append(str(e))

        elapsed = time.perf_counter_ns() - start_ns
        self._total_duration_ns += elapsed
        return records


class EnrichStage(PipelineStage):
    """Enrich stage: decorates records with supplementary metadata.

    Because a FizzBuzz result by itself is too austere. Each record
    is enriched with:
    - Fibonacci membership (is this number in the Fibonacci sequence?)
    - Primality analysis (is this number prime?)
    - Roman numeral conversion (because ancient Rome deserves representation)
    - Emotional valence (how does this number FEEL about being FizzBuzzed?)

    None of this information is useful. All of it is computed.
    """

    # Pre-computed Fibonacci numbers up to a reasonable limit
    _FIBONACCI_CACHE: set[int] = set()
    _FIBONACCI_COMPUTED = False

    # Emotional valence mapping based on number % 100
    _VALENCE_RANGES: list[tuple[int, int, EmotionalValence]] = [
        (0, 14, EmotionalValence.ECSTATIC),
        (15, 29, EmotionalValence.JOYFUL),
        (30, 44, EmotionalValence.CONTENT),
        (45, 55, EmotionalValence.NEUTRAL),
        (56, 69, EmotionalValence.MELANCHOLY),
        (70, 84, EmotionalValence.ANXIOUS),
        (85, 99, EmotionalValence.DESPONDENT),
    ]

    def __init__(
        self,
        enable_fibonacci: bool = True,
        enable_primality: bool = True,
        enable_roman: bool = True,
        enable_emotional: bool = True,
    ) -> None:
        super().__init__(PipelineStageType.ENRICH)
        self._enable_fibonacci = enable_fibonacci
        self._enable_primality = enable_primality
        self._enable_roman = enable_roman
        self._enable_emotional = enable_emotional
        self._ensure_fibonacci_cache()

    @classmethod
    def _ensure_fibonacci_cache(cls) -> None:
        """Pre-compute Fibonacci numbers up to 10,000."""
        if cls._FIBONACCI_COMPUTED:
            return
        a, b = 0, 1
        while a <= 10000:
            cls._FIBONACCI_CACHE.add(a)
            a, b = b, a + b
        cls._FIBONACCI_COMPUTED = True

    @staticmethod
    def is_fibonacci(n: int) -> bool:
        """Check if n is a Fibonacci number.

        Uses the pre-computed cache for efficiency, because computing
        Fibonacci membership for each integer in real-time would be
        wasteful -- unlike everything else in this pipeline.
        """
        if n < 0:
            return False
        if n <= 10000:
            return n in EnrichStage._FIBONACCI_CACHE
        # For large numbers, use the mathematical test
        # n is Fibonacci if 5n^2 + 4 or 5n^2 - 4 is a perfect square
        def is_perfect_square(x: int) -> bool:
            if x < 0:
                return False
            s = int(math.isqrt(x))
            return s * s == x
        return is_perfect_square(5 * n * n + 4) or is_perfect_square(5 * n * n - 4)

    @staticmethod
    def is_prime(n: int) -> bool:
        """Check if n is prime.

        Uses trial division because we are enterprise engineers,
        not competitive programmers. O(sqrt(n)) is good enough
        for FizzBuzz enrichment.
        """
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True

    @staticmethod
    def to_roman(n: int) -> str:
        """Convert a positive integer to Roman numeral representation.

        Supports numbers from 1 to 3999. Numbers outside this range
        receive the designation 'N/A' because the Romans never had
        to deal with FizzBuzz at scale.
        """
        if n <= 0 or n > 3999:
            return "N/A"
        values = [
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        ]
        result = ""
        for value, numeral in values:
            while n >= value:
                result += numeral
                n -= value
        return result

    @classmethod
    def get_emotional_valence(cls, n: int) -> EmotionalValence:
        """Assign emotional valence to a number based on n % 100.

        Because every number has feelings, and data enrichment
        without emotional analysis is just cold, heartless
        computation. The valence is determined by the number's
        position in the modulo-100 spectrum, which is exactly
        as scientific as it sounds.
        """
        bucket = abs(n) % 100
        for low, high, valence in cls._VALENCE_RANGES:
            if low <= bucket <= high:
                return valence
        return EmotionalValence.NEUTRAL

    def process(self, records: list[DataRecord]) -> list[DataRecord]:
        """Enrich each transformed record with supplementary metadata."""
        start_ns = time.perf_counter_ns()
        for record in records:
            if record.status == RecordStatus.FAILED:
                continue
            if record.status != RecordStatus.TRANSFORMED:
                continue

            enrich_start = time.perf_counter_ns()
            enrichments: dict[str, Any] = {}

            if self._enable_fibonacci:
                enrichments["is_fibonacci"] = self.is_fibonacci(record.number)

            if self._enable_primality:
                enrichments["is_prime"] = self.is_prime(record.number)

            if self._enable_roman:
                enrichments["roman_numeral"] = self.to_roman(record.number)

            if self._enable_emotional:
                valence = self.get_emotional_valence(record.number)
                enrichments["emotional_valence"] = valence.value

            record.enrichments = enrichments
            record.metadata.update(enrichments)
            record.status = RecordStatus.ENRICHED
            enrich_elapsed = time.perf_counter_ns() - enrich_start
            record.add_lineage(
                stage=self.name,
                operation=f"Enriched number {record.number} with {len(enrichments)} attributes",
                duration_ns=enrich_elapsed,
                details=enrichments,
            )
            self._records_processed += 1

        elapsed = time.perf_counter_ns() - start_ns
        self._total_duration_ns += elapsed
        return records


class LoadStage(PipelineStage):
    """Load stage: delivers records to the configured SinkConnector.

    The final stage of the pipeline. After all that extraction,
    validation, transformation, and enrichment, the record is
    finally delivered to its destination -- which is either stdout
    (for those who want to see their FizzBuzz results) or /dev/null
    (for those who have transcended the need for output).
    """

    def __init__(self, sink: SinkConnector) -> None:
        super().__init__(PipelineStageType.LOAD)
        self._sink = sink

    def process(self, records: list[DataRecord]) -> list[DataRecord]:
        """Load each enriched record into the sink connector."""
        start_ns = time.perf_counter_ns()
        for record in records:
            if record.status == RecordStatus.FAILED:
                continue
            if record.status != RecordStatus.ENRICHED:
                continue

            load_start = time.perf_counter_ns()
            success = self._sink.load(record)
            load_elapsed = time.perf_counter_ns() - load_start

            if success:
                record.status = RecordStatus.LOADED
                record.add_lineage(
                    stage=self.name,
                    operation=f"Loaded record to {self._sink.get_name()}",
                    duration_ns=load_elapsed,
                    details={"sink": self._sink.get_name(), "success": True},
                )
                self._records_processed += 1
            else:
                record.status = RecordStatus.FAILED
                record.error = f"Sink '{self._sink.get_name()}' rejected the record"
                record.add_lineage(
                    stage=self.name,
                    operation=f"FAILED: {record.error}",
                    duration_ns=load_elapsed,
                )
                self._errors.append(record.error)

        elapsed = time.perf_counter_ns() - start_ns
        self._total_duration_ns += elapsed
        return records


# ============================================================
# Data Lineage Tracker
# ============================================================

class DataLineageTracker:
    """Tracks the full provenance chain for every record in the pipeline.

    Every DataRecord accumulates lineage entries as it flows through
    the pipeline stages. The DataLineageTracker provides a centralized
    view of all record lineages, enabling auditors to trace the exact
    journey of every integer from extraction through loading.

    This is the data governance equivalent of attaching a GPS tracker
    to every number. Was it really necessary? No. But can we produce
    a 47-page audit report about it? Absolutely.
    """

    def __init__(self) -> None:
        self._lineages: dict[str, list[LineageEntry]] = {}

    def track(self, record: DataRecord) -> None:
        """Snapshot the current lineage of a record."""
        self._lineages[record.record_id] = list(record.lineage)

    def get_lineage(self, record_id: str) -> list[LineageEntry]:
        """Retrieve the full provenance chain for a record."""
        return self._lineages.get(record_id, [])

    def get_all_lineages(self) -> dict[str, list[LineageEntry]]:
        """Return all tracked lineages."""
        return dict(self._lineages)

    @property
    def tracked_count(self) -> int:
        return len(self._lineages)

    def render_lineage(self, record_id: str, width: int = 60) -> str:
        """Render the lineage of a single record as ASCII art."""
        entries = self.get_lineage(record_id)
        if not entries:
            return f"  No lineage found for record {record_id[:8]}..."

        lines = []
        short_id = record_id[:8]
        lines.append(f"  +{'-' * (width - 2)}+")
        lines.append(f"  | DATA LINEAGE: Record {short_id}...{' ' * max(0, width - 31 - len(short_id))}|")
        lines.append(f"  +{'-' * (width - 2)}+")

        for i, entry in enumerate(entries):
            connector = "|" if i < len(entries) - 1 else "`"
            duration_str = ""
            if entry.duration_ns > 0:
                duration_str = f" ({entry.duration_ns / 1000:.1f}us)"
            line = f"  {connector}-- [{entry.stage}] {entry.operation}{duration_str}"
            if len(line) > width + 2:
                line = line[:width - 1] + "..."
            lines.append(line)

        lines.append(f"  +{'-' * (width - 2)}+")
        return "\n".join(lines)


# ============================================================
# Pipeline DAG (Directed Acyclic Graph)
# ============================================================

@dataclass
class DAGNode:
    """A node in the pipeline DAG representing a single stage.

    Each node wraps a PipelineStage and tracks its dependencies
    (upstream stages) and dependents (downstream stages). For our
    five-stage linear pipeline, each node has exactly one upstream
    and one downstream dependency, making the DAG a glorified
    linked list. But it's a topologically sorted linked list,
    and that makes all the difference.
    """
    stage: PipelineStage
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)


class PipelineDAG:
    """Directed Acyclic Graph for pipeline stage ordering.

    Implements topological sorting via Kahn's algorithm to determine
    the correct execution order of pipeline stages. For our five-stage
    linear chain (Extract -> Validate -> Transform -> Enrich -> Load),
    the topological sort will produce exactly the same order as
    simply listing the stages in sequence. But we use Kahn's algorithm
    anyway, because enterprise data pipelines demand formal graph
    resolution even when the graph is a straight line.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, DAGNode] = {}

    def add_stage(self, stage: PipelineStage, dependencies: Optional[list[str]] = None) -> None:
        """Add a stage to the DAG with optional dependencies."""
        node = DAGNode(
            stage=stage,
            dependencies=list(dependencies or []),
        )
        self._nodes[stage.name] = node

        # Update dependent lists
        for dep_name in node.dependencies:
            if dep_name in self._nodes:
                self._nodes[dep_name].dependents.append(stage.name)

    def topological_sort(self) -> list[PipelineStage]:
        """Resolve stage execution order using Kahn's algorithm.

        Kahn's algorithm performs a topological sort by repeatedly
        removing nodes with no incoming edges. For a linear chain,
        this is equivalent to reading the stages from left to right.
        But the algorithm doesn't know that, and its O(V + E) time
        complexity ensures maximum theoretical overhead for our
        five-node, four-edge graph.
        """
        if not self._nodes:
            return []

        # Compute in-degrees
        in_degree: dict[str, int] = {name: 0 for name in self._nodes}
        for name, node in self._nodes.items():
            for dep in node.dependencies:
                if dep in self._nodes:
                    in_degree[name] = in_degree.get(name, 0)
                    # dep -> name edge means name has an incoming edge
                    pass
            in_degree[name] = len([d for d in node.dependencies if d in self._nodes])

        # Initialize queue with nodes that have no dependencies
        queue: deque[str] = deque()
        for name, degree in in_degree.items():
            if degree == 0:
                queue.append(name)

        sorted_stages: list[PipelineStage] = []
        visited = 0

        while queue:
            current_name = queue.popleft()
            current_node = self._nodes[current_name]
            sorted_stages.append(current_node.stage)
            visited += 1

            # Reduce in-degree for all dependents
            for dependent_name in current_node.dependents:
                if dependent_name in in_degree:
                    in_degree[dependent_name] -= 1
                    if in_degree[dependent_name] == 0:
                        queue.append(dependent_name)

        if visited != len(self._nodes):
            raise DAGResolutionError(
                f"Cycle detected in pipeline DAG. Only {visited}/{len(self._nodes)} "
                f"stages could be resolved. This should be impossible for a "
                f"linear chain, yet here we are."
            )

        return sorted_stages

    def get_node(self, name: str) -> Optional[DAGNode]:
        """Retrieve a DAG node by stage name."""
        return self._nodes.get(name)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(n.dependents) for n in self._nodes.values())

    def render(self, width: int = 60) -> str:
        """Render the DAG as ASCII art.

        Visualizes the pipeline DAG as a flowchart with boxes for
        each stage and arrows showing the dependencies. For our
        linear chain, this produces a straightforward left-to-right
        (well, top-to-bottom) diagram. But we render it as a DAG
        because that's what it is, technically.
        """
        try:
            sorted_stages = self.topological_sort()
        except DAGResolutionError:
            return "  [DAG RESOLUTION FAILED -- Cannot render]"

        lines = []
        lines.append(f"  +{'-' * (width - 2)}+")
        lines.append(f"  | PIPELINE DAG (Topological Order){' ' * max(0, width - 36)}|")
        lines.append(f"  +{'-' * (width - 2)}+")
        lines.append(f"  | Nodes: {self.node_count}  Edges: {self.edge_count}"
                      f"{' ' * max(0, width - 22 - len(str(self.node_count)) - len(str(self.edge_count)))}|")
        lines.append(f"  +{'-' * (width - 2)}+")

        for i, stage in enumerate(sorted_stages):
            node = self._nodes.get(stage.name)
            deps = ", ".join(node.dependencies) if node and node.dependencies else "(none)"
            box_label = f"[{stage.name}]"
            dep_label = f"deps: {deps}"
            lines.append(f"  |  {box_label:<20} {dep_label:<{width - 26}}|")
            if i < len(sorted_stages) - 1:
                lines.append(f"  |       |{' ' * (width - 11)}|")
                lines.append(f"  |       v{' ' * (width - 11)}|")

        lines.append(f"  +{'-' * (width - 2)}+")
        return "\n".join(lines)


# ============================================================
# DAG Executor
# ============================================================

@dataclass
class StageCheckpoint:
    """A checkpoint capturing pipeline state after a stage completes.

    Checkpoints are saved to RAM after each stage, providing
    'recovery' capabilities that are exactly as durable as the
    process that created them. If the process crashes, all
    checkpoints are lost, along with any illusion of fault
    tolerance. But the checkpointing ceremony was performed,
    and that's what compliance cares about.
    """
    stage_name: str
    records_snapshot: list[DataRecord]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class DAGExecutor:
    """Executes pipeline stages in topological order with retry and checkpointing.

    The DAGExecutor drives the pipeline by resolving the DAG's
    topological order and executing each stage in sequence. If a
    stage fails, the executor retries with exponential backoff,
    because transient failures in modulo arithmetic are a well-known
    phenomenon in enterprise computing (they aren't, but the retry
    logic exists anyway).

    Checkpoints are saved after each successful stage, allowing
    theoretical recovery from any point in the pipeline. In practice,
    recovery from an in-memory checkpoint requires that the process
    hasn't crashed, which defeats the entire purpose of checkpointing.
    """

    def __init__(
        self,
        dag: PipelineDAG,
        max_retries: int = 3,
        retry_backoff_ms: int = 100,
        enable_checkpoints: bool = True,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._dag = dag
        self._max_retries = max_retries
        self._retry_backoff_ms = retry_backoff_ms
        self._enable_checkpoints = enable_checkpoints
        self._event_bus = event_bus
        self._checkpoints: list[StageCheckpoint] = []
        self._execution_log: list[dict[str, Any]] = []

    @property
    def checkpoints(self) -> list[StageCheckpoint]:
        return list(self._checkpoints)

    @property
    def execution_log(self) -> list[dict[str, Any]]:
        return list(self._execution_log)

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event via the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(Event(
                    event_type=event_type,
                    payload=payload,
                    source="DataPipeline",
                ))
            except Exception:
                pass

    def execute(self, records: list[DataRecord]) -> list[DataRecord]:
        """Execute the full pipeline DAG on the given records.

        Resolves the topological order, then executes each stage
        in sequence. Stages that fail are retried up to max_retries
        times with exponential backoff. Checkpoints are saved after
        each successful stage.
        """
        # Resolve execution order
        sorted_stages = self._dag.topological_sort()

        self._emit(EventType.PIPELINE_STARTED, {
            "stages": [s.name for s in sorted_stages],
            "record_count": len(records),
        })
        self._emit(EventType.PIPELINE_DAG_RESOLVED, {
            "order": [s.name for s in sorted_stages],
            "nodes": self._dag.node_count,
            "edges": self._dag.edge_count,
        })

        pipeline_start = time.perf_counter_ns()
        current_records = records

        for stage in sorted_stages:
            stage_start = time.perf_counter_ns()

            self._emit(EventType.PIPELINE_STAGE_ENTERED, {
                "stage": stage.name,
                "record_count": len(current_records),
            })

            # Execute with retry
            attempt = 0
            last_error: Optional[str] = None
            success = False

            while attempt <= self._max_retries:
                try:
                    current_records = stage.process(current_records)
                    success = True
                    break
                except Exception as e:
                    last_error = str(e)
                    attempt += 1
                    if attempt <= self._max_retries:
                        # Exponential backoff (simulated -- we don't actually sleep)
                        backoff_ms = self._retry_backoff_ms * (2 ** (attempt - 1))
                        logger.warning(
                            "Stage '%s' failed (attempt %d/%d), backoff %dms: %s",
                            stage.name, attempt, self._max_retries, backoff_ms, last_error,
                        )

            if not success and last_error is not None:
                logger.error(
                    "Stage '%s' exhausted all %d retries. Last error: %s",
                    stage.name, self._max_retries, last_error,
                )

            stage_elapsed = time.perf_counter_ns() - stage_start

            self._emit(EventType.PIPELINE_STAGE_COMPLETED, {
                "stage": stage.name,
                "duration_ns": stage_elapsed,
                "records_processed": stage.records_processed,
                "success": success,
            })

            # Log execution
            self._execution_log.append({
                "stage": stage.name,
                "duration_ns": stage_elapsed,
                "duration_ms": stage_elapsed / 1_000_000,
                "records_in": len(records),
                "records_processed": stage.records_processed,
                "errors": len(stage.errors),
                "success": success,
            })

            # Checkpoint
            if self._enable_checkpoints:
                checkpoint = StageCheckpoint(
                    stage_name=stage.name,
                    records_snapshot=list(current_records),
                )
                self._checkpoints.append(checkpoint)
                self._emit(EventType.PIPELINE_CHECKPOINT_SAVED, {
                    "stage": stage.name,
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "records": len(checkpoint.records_snapshot),
                })

        pipeline_elapsed = time.perf_counter_ns() - pipeline_start

        self._emit(EventType.PIPELINE_COMPLETED, {
            "total_duration_ns": pipeline_elapsed,
            "total_duration_ms": pipeline_elapsed / 1_000_000,
            "stages_executed": len(sorted_stages),
            "records_loaded": sum(
                1 for r in current_records if r.status == RecordStatus.LOADED
            ),
            "records_failed": sum(
                1 for r in current_records if r.status == RecordStatus.FAILED
            ),
        })

        return current_records

    def get_statistics(self) -> dict[str, Any]:
        """Return execution statistics for the pipeline run."""
        return {
            "execution_log": self._execution_log,
            "checkpoints": len(self._checkpoints),
            "total_duration_ms": sum(
                entry.get("duration_ms", 0) for entry in self._execution_log
            ),
        }


# ============================================================
# Backfill Engine
# ============================================================

class BackfillEngine:
    """Retroactive enrichment engine for previously processed records.

    The BackfillEngine re-processes records through the enrichment
    stage with updated or additional enrichment configurations.
    This is the data pipeline equivalent of going back to edit your
    vacation photos after you've already posted them -- the original
    experience was fine, but apparently it needs more filters.
    """

    def __init__(self, enrich_stage: EnrichStage, event_bus: Optional[Any] = None) -> None:
        self._enrich_stage = enrich_stage
        self._event_bus = event_bus
        self._backfill_count = 0

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(Event(
                    event_type=event_type,
                    payload=payload,
                    source="BackfillEngine",
                ))
            except Exception:
                pass

    def backfill(self, records: list[DataRecord]) -> list[DataRecord]:
        """Re-enrich previously processed records.

        Takes records that have already been through the pipeline
        and runs them through the enrichment stage again. Records
        must be in LOADED status (fully processed) to be eligible
        for backfill. Records in any other state are skipped.
        """
        self._emit(EventType.PIPELINE_BACKFILL_STARTED, {
            "record_count": len(records),
        })

        eligible = []
        for record in records:
            if record.status == RecordStatus.LOADED:
                # Temporarily set status back to TRANSFORMED for re-enrichment
                record.status = RecordStatus.TRANSFORMED
                record.add_lineage(
                    stage="Backfill",
                    operation=f"Backfill initiated for record {record.record_id[:8]}",
                )
                eligible.append(record)

        if eligible:
            enriched = self._enrich_stage.process(eligible)
            # Mark as loaded again
            for record in enriched:
                if record.status == RecordStatus.ENRICHED:
                    record.status = RecordStatus.LOADED
                    record.add_lineage(
                        stage="Backfill",
                        operation="Backfill completed -- record re-loaded",
                    )
                    self._backfill_count += 1

        self._emit(EventType.PIPELINE_BACKFILL_COMPLETED, {
            "backfilled": self._backfill_count,
        })

        return records

    @property
    def backfill_count(self) -> int:
        return self._backfill_count


# ============================================================
# Pipeline Dashboard
# ============================================================

class PipelineDashboard:
    """ASCII dashboard for the Data Pipeline & ETL Framework.

    Renders a comprehensive overview of pipeline execution including
    stage statistics, DAG visualization, data lineage, and backfill
    status. The dashboard is rendered in enterprise-grade ASCII art
    that would make any terminal emulator proud.
    """

    @staticmethod
    def render(
        executor: DAGExecutor,
        dag: PipelineDAG,
        records: list[DataRecord],
        lineage_tracker: Optional[DataLineageTracker] = None,
        backfill_engine: Optional[BackfillEngine] = None,
        width: int = 60,
    ) -> str:
        """Render the full pipeline dashboard."""
        lines = []
        inner = width - 4

        lines.append(f"  +{'=' * (width - 2)}+")
        lines.append(f"  | {'DATA PIPELINE & ETL FRAMEWORK DASHBOARD':^{inner}} |")
        lines.append(f"  +{'=' * (width - 2)}+")

        # Pipeline statistics
        stats = executor.get_statistics()
        loaded = sum(1 for r in records if r.status == RecordStatus.LOADED)
        failed = sum(1 for r in records if r.status == RecordStatus.FAILED)
        total = len(records)

        lines.append(f"  | {'PIPELINE SUMMARY':^{inner}} |")
        lines.append(f"  +{'-' * (width - 2)}+")
        lines.append(f"  | Total Records:    {total:<{inner - 20}} |")
        lines.append(f"  | Loaded:           {loaded:<{inner - 20}} |")
        lines.append(f"  | Failed:           {failed:<{inner - 20}} |")
        lines.append(f"  | Checkpoints:      {stats.get('checkpoints', 0):<{inner - 20}} |")
        dur_ms = stats.get('total_duration_ms', 0)
        dur_str = f"{dur_ms:.3f}ms"
        lines.append(f"  | Total Duration:   {dur_str:<{inner - 20}} |")
        lines.append(f"  +{'-' * (width - 2)}+")

        # Stage breakdown
        lines.append(f"  | {'STAGE EXECUTION LOG':^{inner}} |")
        lines.append(f"  +{'-' * (width - 2)}+")
        for entry in stats.get("execution_log", []):
            stage_name = entry.get("stage", "?")
            duration = entry.get("duration_ms", 0)
            processed = entry.get("records_processed", 0)
            errors = entry.get("errors", 0)
            status = "OK" if entry.get("success", False) else "FAIL"
            line = f"  | {stage_name:<12} {duration:>8.3f}ms  {processed:>4} rec  {errors:>2} err  [{status}]"
            padding = max(0, width - len(line))
            lines.append(f"{line}{' ' * (padding - 1)}|")

        lines.append(f"  +{'-' * (width - 2)}+")

        # Lineage tracker stats
        if lineage_tracker is not None:
            lines.append(f"  | {'DATA LINEAGE':^{inner}} |")
            lines.append(f"  +{'-' * (width - 2)}+")
            lines.append(f"  | Records tracked:  {lineage_tracker.tracked_count:<{inner - 20}} |")
            lines.append(f"  +{'-' * (width - 2)}+")

        # Backfill stats
        if backfill_engine is not None:
            lines.append(f"  | {'BACKFILL ENGINE':^{inner}} |")
            lines.append(f"  +{'-' * (width - 2)}+")
            lines.append(f"  | Records backfilled: {backfill_engine.backfill_count:<{inner - 22}} |")
            lines.append(f"  +{'-' * (width - 2)}+")

        # DAG visualization
        lines.append("")
        lines.append(dag.render(width))

        lines.append(f"\n  +{'=' * (width - 2)}+")
        return "\n".join(lines)

    @staticmethod
    def render_dag(dag: PipelineDAG, width: int = 60) -> str:
        """Render just the DAG visualization."""
        return dag.render(width)

    @staticmethod
    def render_lineage(
        lineage_tracker: DataLineageTracker,
        records: list[DataRecord],
        width: int = 60,
    ) -> str:
        """Render lineage for all tracked records."""
        lines = []
        lines.append(f"  +{'=' * (width - 2)}+")
        lines.append(f"  | {'DATA LINEAGE REPORT':<{width - 4}} |")
        lines.append(f"  +{'=' * (width - 2)}+")

        for record in records[:20]:  # Limit to 20 records
            lines.append(lineage_tracker.render_lineage(record.record_id, width))
            lines.append("")

        if len(records) > 20:
            lines.append(f"  ... and {len(records) - 20} more records")

        return "\n".join(lines)


# ============================================================
# Source / Sink Connector Factories
# ============================================================

class SourceConnectorFactory:
    """Factory for creating source connectors by name."""

    _connectors: dict[str, type[SourceConnector]] = {
        "range": RangeSource,
        "devnull": DevNullSource,
    }

    @classmethod
    def create(cls, name: str) -> SourceConnector:
        connector_class = cls._connectors.get(name)
        if connector_class is None:
            raise SourceConnectorError(name, f"Unknown source connector: '{name}'")
        return connector_class()


class SinkConnectorFactory:
    """Factory for creating sink connectors by name."""

    _connectors: dict[str, type[SinkConnector]] = {
        "stdout": StdoutSink,
        "devnull": DevNullSink,
    }

    @classmethod
    def create(cls, name: str) -> SinkConnector:
        connector_class = cls._connectors.get(name)
        if connector_class is None:
            raise SinkConnectorError(name, f"Unknown sink connector: '{name}'")
        return connector_class()


# ============================================================
# Pipeline Builder
# ============================================================

class PipelineBuilder:
    """Fluent builder for constructing a complete ETL pipeline.

    Because even pipelines need a builder pattern. The PipelineBuilder
    assembles all pipeline components -- source, sink, stages, DAG,
    executor, lineage tracker, and backfill engine -- into a coherent
    whole that can process FizzBuzz evaluations with maximum ceremony.
    """

    def __init__(self) -> None:
        self._source: Optional[SourceConnector] = None
        self._sink: Optional[SinkConnector] = None
        self._rules: Optional[list[RuleDefinition]] = None
        self._enrichments: dict[str, bool] = {
            "fibonacci": True,
            "primality": True,
            "roman_numerals": True,
            "emotional_valence": True,
        }
        self._max_retries: int = 3
        self._retry_backoff_ms: int = 100
        self._enable_checkpoints: bool = True
        self._enable_lineage: bool = True
        self._enable_backfill: bool = False
        self._event_bus: Optional[Any] = None

    def with_source(self, source: SourceConnector) -> PipelineBuilder:
        self._source = source
        return self

    def with_sink(self, sink: SinkConnector) -> PipelineBuilder:
        self._sink = sink
        return self

    def with_rules(self, rules: list[RuleDefinition]) -> PipelineBuilder:
        self._rules = rules
        return self

    def with_enrichments(self, enrichments: dict[str, bool]) -> PipelineBuilder:
        self._enrichments = enrichments
        return self

    def with_max_retries(self, max_retries: int) -> PipelineBuilder:
        self._max_retries = max_retries
        return self

    def with_retry_backoff_ms(self, backoff_ms: int) -> PipelineBuilder:
        self._retry_backoff_ms = backoff_ms
        return self

    def with_checkpoints(self, enabled: bool) -> PipelineBuilder:
        self._enable_checkpoints = enabled
        return self

    def with_lineage(self, enabled: bool) -> PipelineBuilder:
        self._enable_lineage = enabled
        return self

    def with_backfill(self, enabled: bool) -> PipelineBuilder:
        self._enable_backfill = enabled
        return self

    def with_event_bus(self, event_bus: Any) -> PipelineBuilder:
        self._event_bus = event_bus
        return self

    def build(self) -> Pipeline:
        """Assemble the pipeline from configured components."""
        source = self._source or RangeSource()
        sink = self._sink or StdoutSink()

        # Create stages
        extract = ExtractStage(source)
        validate = ValidateStage()
        transform = TransformStage(self._rules)
        enrich = EnrichStage(
            enable_fibonacci=self._enrichments.get("fibonacci", True),
            enable_primality=self._enrichments.get("primality", True),
            enable_roman=self._enrichments.get("roman_numerals", True),
            enable_emotional=self._enrichments.get("emotional_valence", True),
        )
        load = LoadStage(sink)

        # Build DAG (linear chain)
        dag = PipelineDAG()
        dag.add_stage(extract)
        dag.add_stage(validate, dependencies=["Extract"])
        dag.add_stage(transform, dependencies=["Validate"])
        dag.add_stage(enrich, dependencies=["Transform"])
        dag.add_stage(load, dependencies=["Enrich"])

        # Create executor
        executor = DAGExecutor(
            dag=dag,
            max_retries=self._max_retries,
            retry_backoff_ms=self._retry_backoff_ms,
            enable_checkpoints=self._enable_checkpoints,
            event_bus=self._event_bus,
        )

        # Create lineage tracker
        lineage_tracker = DataLineageTracker() if self._enable_lineage else None

        # Create backfill engine
        backfill_engine = BackfillEngine(
            enrich_stage=enrich,
            event_bus=self._event_bus,
        ) if self._enable_backfill else None

        return Pipeline(
            source=source,
            sink=sink,
            dag=dag,
            executor=executor,
            lineage_tracker=lineage_tracker,
            backfill_engine=backfill_engine,
            event_bus=self._event_bus,
        )


# ============================================================
# Pipeline
# ============================================================

class Pipeline:
    """The complete ETL pipeline for FizzBuzz evaluation.

    Orchestrates the full Extract-Validate-Transform-Enrich-Load
    process for a range of numbers. Each number flows through five
    stages as a DataRecord, accumulating metadata, lineage entries,
    and enrichment data along the way. The end result is either
    printed to stdout or swallowed by /dev/null, depending on
    how you feel about output today.
    """

    def __init__(
        self,
        source: SourceConnector,
        sink: SinkConnector,
        dag: PipelineDAG,
        executor: DAGExecutor,
        lineage_tracker: Optional[DataLineageTracker] = None,
        backfill_engine: Optional[BackfillEngine] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._source = source
        self._sink = sink
        self._dag = dag
        self._executor = executor
        self._lineage_tracker = lineage_tracker
        self._backfill_engine = backfill_engine
        self._event_bus = event_bus
        self._last_results: list[DataRecord] = []

    @property
    def dag(self) -> PipelineDAG:
        return self._dag

    @property
    def executor(self) -> DAGExecutor:
        return self._executor

    @property
    def lineage_tracker(self) -> Optional[DataLineageTracker]:
        return self._lineage_tracker

    @property
    def backfill_engine(self) -> Optional[BackfillEngine]:
        return self._backfill_engine

    @property
    def last_results(self) -> list[DataRecord]:
        return list(self._last_results)

    @property
    def source(self) -> SourceConnector:
        return self._source

    @property
    def sink(self) -> SinkConnector:
        return self._sink

    def run(self, start: int, end: int) -> list[DataRecord]:
        """Execute the full pipeline for the given range.

        Extracts records from the source, runs them through the DAG,
        tracks lineage, and optionally performs backfill. Returns the
        processed DataRecords.
        """
        # Extract records from source
        records = self._source.extract(start, end)

        # Execute the DAG
        processed = self._executor.execute(records)

        # Track lineage
        if self._lineage_tracker is not None:
            for record in processed:
                self._lineage_tracker.track(record)

        # Backfill if enabled
        if self._backfill_engine is not None:
            processed = self._backfill_engine.backfill(processed)

        self._last_results = processed
        return processed


# ============================================================
# Pipeline Middleware (IMiddleware)
# ============================================================

class PipelineMiddleware(IMiddleware):
    """Middleware that intercepts FizzBuzz processing and routes it through the ETL pipeline.

    Priority 11 ensures this runs after most other middleware but
    before the translation layer. When active, each number processed
    through the middleware pipeline also gets tracked by the data
    pipeline's lineage system, because one pipeline inside another
    pipeline is the Russian nesting doll of enterprise architecture.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._pipeline = pipeline
        self._event_bus = event_bus
        self._records_tracked: int = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process context through the middleware chain, tracking in the pipeline."""
        # Let the normal processing happen first
        result = next_handler(context)

        # Track this number in the pipeline's lineage tracker
        if self._pipeline.lineage_tracker is not None and result.results:
            latest = result.results[-1]
            record = DataRecord(
                number=context.number,
                status=RecordStatus.LOADED,
                fizzbuzz_result=latest,
                metadata={
                    "middleware_tracked": True,
                    "session_id": context.session_id,
                    "output": latest.output,
                },
            )
            record.add_lineage(
                stage="PipelineMiddleware",
                operation=f"Tracked via middleware: {context.number} -> '{latest.output}'",
            )
            self._pipeline.lineage_tracker.track(record)
            self._records_tracked += 1

        return result

    def get_name(self) -> str:
        return "PipelineMiddleware"

    def get_priority(self) -> int:
        return 11

    @property
    def records_tracked(self) -> int:
        return self._records_tracked

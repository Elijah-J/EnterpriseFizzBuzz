"""
Enterprise FizzBuzz Platform - Data Pipeline & ETL Framework Tests

Comprehensive test suite for the Data Pipeline & ETL Framework,
ensuring that every number's journey through five stages of
enterprise ceremony is executed with mathematical precision
and theatrical flair.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

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
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext, RuleDefinition
from enterprise_fizzbuzz.infrastructure.data_pipeline import (
    BackfillEngine,
    DAGExecutor,
    DAGNode,
    DataLineageTracker,
    DataRecord,
    DevNullSink,
    DevNullSource,
    EmotionalValence,
    EnrichStage,
    ExtractStage,
    LineageEntry,
    LoadStage,
    Pipeline,
    PipelineBuilder,
    PipelineDashboard,
    PipelineDAG,
    PipelineMiddleware,
    PipelineStageType,
    RangeSource,
    RecordStatus,
    SinkConnector,
    SinkConnectorFactory,
    SourceConnector,
    SourceConnectorFactory,
    StageCheckpoint,
    StdoutSink,
    TransformStage,
    ValidateStage,
)


# ============================================================
# DataRecord Tests
# ============================================================


class TestDataRecord(unittest.TestCase):
    """Tests for the DataRecord data carrier."""

    def test_default_creation(self):
        record = DataRecord()
        self.assertEqual(record.number, 0)
        self.assertEqual(record.status, RecordStatus.PENDING)
        self.assertIsNone(record.fizzbuzz_result)
        self.assertIsNotNone(record.record_id)
        self.assertEqual(len(record.lineage), 0)
        self.assertEqual(len(record.metadata), 0)

    def test_creation_with_number(self):
        record = DataRecord(number=42)
        self.assertEqual(record.number, 42)

    def test_add_lineage(self):
        record = DataRecord(number=15)
        record.add_lineage("Extract", "Extracted number 15", duration_ns=100)
        self.assertEqual(len(record.lineage), 1)
        self.assertEqual(record.lineage[0].stage, "Extract")
        self.assertEqual(record.lineage[0].operation, "Extracted number 15")
        self.assertEqual(record.lineage[0].duration_ns, 100)

    def test_add_multiple_lineage_entries(self):
        record = DataRecord(number=3)
        record.add_lineage("Extract", "op1")
        record.add_lineage("Validate", "op2")
        record.add_lineage("Transform", "op3")
        self.assertEqual(len(record.lineage), 3)

    def test_lineage_with_details(self):
        record = DataRecord(number=5)
        record.add_lineage("Enrich", "enriched", details={"is_prime": True})
        self.assertTrue(record.lineage[0].details["is_prime"])

    def test_batch_id(self):
        record = DataRecord(number=7, batch_id="batch-001")
        self.assertEqual(record.batch_id, "batch-001")

    def test_error_field(self):
        record = DataRecord(number=0)
        record.error = "Something went wrong"
        record.status = RecordStatus.FAILED
        self.assertEqual(record.error, "Something went wrong")
        self.assertEqual(record.status, RecordStatus.FAILED)


# ============================================================
# Source Connector Tests
# ============================================================


class TestRangeSource(unittest.TestCase):
    """Tests for the RangeSource connector."""

    def test_extract_single(self):
        source = RangeSource()
        records = source.extract(1, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].number, 1)
        self.assertEqual(records[0].status, RecordStatus.EXTRACTED)

    def test_extract_range(self):
        source = RangeSource()
        records = source.extract(1, 5)
        self.assertEqual(len(records), 5)
        self.assertEqual([r.number for r in records], [1, 2, 3, 4, 5])

    def test_extract_adds_lineage(self):
        source = RangeSource()
        records = source.extract(1, 3)
        for record in records:
            self.assertGreaterEqual(len(record.lineage), 1)
            self.assertIn("Extract", record.lineage[0].operation)

    def test_extract_sets_metadata(self):
        source = RangeSource()
        records = source.extract(10, 10)
        self.assertEqual(records[0].metadata["source"], "range")

    def test_extract_batch_id(self):
        source = RangeSource()
        records = source.extract(1, 3)
        batch_ids = {r.batch_id for r in records}
        self.assertEqual(len(batch_ids), 1)  # All same batch

    def test_get_name(self):
        self.assertEqual(RangeSource().get_name(), "RangeSource")


class TestDevNullSource(unittest.TestCase):
    """Tests for the DevNullSource connector."""

    def test_extract_returns_empty(self):
        source = DevNullSource()
        records = source.extract(1, 100)
        self.assertEqual(len(records), 0)

    def test_get_name(self):
        self.assertEqual(DevNullSource().get_name(), "DevNullSource")


# ============================================================
# Sink Connector Tests
# ============================================================


class TestStdoutSink(unittest.TestCase):
    """Tests for the StdoutSink connector."""

    def test_load_with_result(self):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        sink = StdoutSink()
        record = DataRecord(number=15)
        record.fizzbuzz_result = FizzBuzzResult(number=15, output="FizzBuzz")
        self.assertTrue(sink.load(record))
        self.assertEqual(len(sink.get_loaded_records()), 1)

    def test_load_without_result(self):
        sink = StdoutSink()
        record = DataRecord(number=7)
        self.assertFalse(sink.load(record))
        self.assertEqual(len(sink.get_loaded_records()), 0)

    def test_get_name(self):
        self.assertEqual(StdoutSink().get_name(), "StdoutSink")


class TestDevNullSink(unittest.TestCase):
    """Tests for the DevNullSink connector -- full pipeline, zero output."""

    def test_load_always_succeeds(self):
        sink = DevNullSink()
        record = DataRecord(number=42)
        self.assertTrue(sink.load(record))

    def test_tracks_loaded_records(self):
        sink = DevNullSink()
        for i in range(5):
            sink.load(DataRecord(number=i))
        self.assertEqual(len(sink.get_loaded_records()), 5)

    def test_get_name(self):
        self.assertEqual(DevNullSink().get_name(), "DevNullSink")


# ============================================================
# Connector Factory Tests
# ============================================================


class TestSourceConnectorFactory(unittest.TestCase):
    """Tests for the SourceConnectorFactory."""

    def test_create_range(self):
        source = SourceConnectorFactory.create("range")
        self.assertIsInstance(source, RangeSource)

    def test_create_devnull(self):
        source = SourceConnectorFactory.create("devnull")
        self.assertIsInstance(source, DevNullSource)

    def test_create_unknown_raises(self):
        with self.assertRaises(SourceConnectorError):
            SourceConnectorFactory.create("kafka")


class TestSinkConnectorFactory(unittest.TestCase):
    """Tests for the SinkConnectorFactory."""

    def test_create_stdout(self):
        sink = SinkConnectorFactory.create("stdout")
        self.assertIsInstance(sink, StdoutSink)

    def test_create_devnull(self):
        sink = SinkConnectorFactory.create("devnull")
        self.assertIsInstance(sink, DevNullSink)

    def test_create_unknown_raises(self):
        with self.assertRaises(SinkConnectorError):
            SinkConnectorFactory.create("s3")


# ============================================================
# Pipeline Stage Tests
# ============================================================


class TestExtractStage(unittest.TestCase):
    """Tests for the Extract pipeline stage."""

    def test_process_marks_extracted(self):
        source = RangeSource()
        stage = ExtractStage(source)
        records = [DataRecord(number=n) for n in range(1, 4)]
        result = stage.process(records)
        for r in result:
            self.assertEqual(r.status, RecordStatus.EXTRACTED)

    def test_statistics(self):
        source = RangeSource()
        stage = ExtractStage(source)
        records = [DataRecord(number=n) for n in range(1, 6)]
        stage.process(records)
        stats = stage.get_statistics()
        self.assertEqual(stats["records_processed"], 5)
        self.assertEqual(stats["stage"], "Extract")

    def test_name(self):
        stage = ExtractStage(RangeSource())
        self.assertEqual(stage.name, "Extract")


class TestValidateStage(unittest.TestCase):
    """Tests for the Validate pipeline stage."""

    def test_valid_integer(self):
        stage = ValidateStage()
        record = DataRecord(number=42, status=RecordStatus.EXTRACTED)
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.VALIDATED)
        self.assertTrue(result[0].metadata["emotionally_ready"])

    def test_skips_failed_records(self):
        stage = ValidateStage()
        record = DataRecord(number=0, status=RecordStatus.FAILED)
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.FAILED)

    def test_emotional_readiness_always_true(self):
        stage = ValidateStage()
        self.assertTrue(stage._is_emotionally_ready(0))
        self.assertTrue(stage._is_emotionally_ready(-1))
        self.assertTrue(stage._is_emotionally_ready(999999))


class TestTransformStage(unittest.TestCase):
    """Tests for the Transform pipeline stage (real FizzBuzz evaluation!)."""

    def test_fizz(self):
        stage = TransformStage()
        record = DataRecord(number=3, status=RecordStatus.VALIDATED)
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.TRANSFORMED)
        self.assertEqual(result[0].fizzbuzz_result.output, "Fizz")

    def test_buzz(self):
        stage = TransformStage()
        record = DataRecord(number=5, status=RecordStatus.VALIDATED)
        result = stage.process([record])
        self.assertEqual(result[0].fizzbuzz_result.output, "Buzz")

    def test_fizzbuzz(self):
        stage = TransformStage()
        record = DataRecord(number=15, status=RecordStatus.VALIDATED)
        result = stage.process([record])
        self.assertEqual(result[0].fizzbuzz_result.output, "FizzBuzz")

    def test_plain_number(self):
        stage = TransformStage()
        record = DataRecord(number=7, status=RecordStatus.VALIDATED)
        result = stage.process([record])
        self.assertEqual(result[0].fizzbuzz_result.output, "7")

    def test_skips_non_validated(self):
        stage = TransformStage()
        record = DataRecord(number=3, status=RecordStatus.EXTRACTED)
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.EXTRACTED)

    def test_custom_rules(self):
        rules = [
            RuleDefinition(name="WazzRule", divisor=7, label="Wazz", priority=1),
        ]
        stage = TransformStage(rules=rules)
        record = DataRecord(number=7, status=RecordStatus.VALIDATED)
        result = stage.process([record])
        self.assertEqual(result[0].fizzbuzz_result.output, "Wazz")

    def test_metadata_set(self):
        stage = TransformStage()
        record = DataRecord(number=3, status=RecordStatus.VALIDATED)
        result = stage.process([record])
        self.assertEqual(result[0].metadata["fizzbuzz_output"], "Fizz")


class TestEnrichStage(unittest.TestCase):
    """Tests for the Enrich pipeline stage."""

    def test_fibonacci_detection(self):
        self.assertTrue(EnrichStage.is_fibonacci(0))
        self.assertTrue(EnrichStage.is_fibonacci(1))
        self.assertTrue(EnrichStage.is_fibonacci(2))
        self.assertTrue(EnrichStage.is_fibonacci(3))
        self.assertTrue(EnrichStage.is_fibonacci(5))
        self.assertTrue(EnrichStage.is_fibonacci(8))
        self.assertTrue(EnrichStage.is_fibonacci(13))
        self.assertFalse(EnrichStage.is_fibonacci(4))
        self.assertFalse(EnrichStage.is_fibonacci(6))
        self.assertFalse(EnrichStage.is_fibonacci(7))
        self.assertFalse(EnrichStage.is_fibonacci(-1))

    def test_primality(self):
        self.assertFalse(EnrichStage.is_prime(0))
        self.assertFalse(EnrichStage.is_prime(1))
        self.assertTrue(EnrichStage.is_prime(2))
        self.assertTrue(EnrichStage.is_prime(3))
        self.assertFalse(EnrichStage.is_prime(4))
        self.assertTrue(EnrichStage.is_prime(5))
        self.assertTrue(EnrichStage.is_prime(7))
        self.assertFalse(EnrichStage.is_prime(9))
        self.assertTrue(EnrichStage.is_prime(97))

    def test_roman_numerals(self):
        self.assertEqual(EnrichStage.to_roman(1), "I")
        self.assertEqual(EnrichStage.to_roman(4), "IV")
        self.assertEqual(EnrichStage.to_roman(9), "IX")
        self.assertEqual(EnrichStage.to_roman(14), "XIV")
        self.assertEqual(EnrichStage.to_roman(42), "XLII")
        self.assertEqual(EnrichStage.to_roman(99), "XCIX")
        self.assertEqual(EnrichStage.to_roman(3999), "MMMCMXCIX")
        self.assertEqual(EnrichStage.to_roman(0), "N/A")
        self.assertEqual(EnrichStage.to_roman(-1), "N/A")
        self.assertEqual(EnrichStage.to_roman(4000), "N/A")

    def test_emotional_valence(self):
        # 0-14 = ecstatic
        self.assertEqual(EnrichStage.get_emotional_valence(0), EmotionalValence.ECSTATIC)
        self.assertEqual(EnrichStage.get_emotional_valence(14), EmotionalValence.ECSTATIC)
        # 15-29 = joyful
        self.assertEqual(EnrichStage.get_emotional_valence(15), EmotionalValence.JOYFUL)
        # 45-55 = neutral
        self.assertEqual(EnrichStage.get_emotional_valence(50), EmotionalValence.NEUTRAL)
        # 85-99 = despondent
        self.assertEqual(EnrichStage.get_emotional_valence(99), EmotionalValence.DESPONDENT)

    def test_enrich_stage_process(self):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        stage = EnrichStage()
        record = DataRecord(number=5, status=RecordStatus.TRANSFORMED)
        record.fizzbuzz_result = FizzBuzzResult(number=5, output="Buzz")
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.ENRICHED)
        self.assertTrue(result[0].enrichments["is_prime"])
        self.assertTrue(result[0].enrichments["is_fibonacci"])
        self.assertEqual(result[0].enrichments["roman_numeral"], "V")
        self.assertIn("emotional_valence", result[0].enrichments)

    def test_enrich_disabled_enrichments(self):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        stage = EnrichStage(
            enable_fibonacci=False,
            enable_primality=False,
            enable_roman=False,
            enable_emotional=False,
        )
        record = DataRecord(number=5, status=RecordStatus.TRANSFORMED)
        record.fizzbuzz_result = FizzBuzzResult(number=5, output="Buzz")
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.ENRICHED)
        self.assertEqual(len(result[0].enrichments), 0)

    def test_skips_non_transformed(self):
        stage = EnrichStage()
        record = DataRecord(number=5, status=RecordStatus.VALIDATED)
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.VALIDATED)


class TestLoadStage(unittest.TestCase):
    """Tests for the Load pipeline stage."""

    def test_load_to_devnull(self):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        sink = DevNullSink()
        stage = LoadStage(sink)
        record = DataRecord(number=3, status=RecordStatus.ENRICHED)
        record.fizzbuzz_result = FizzBuzzResult(number=3, output="Fizz")
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.LOADED)
        self.assertEqual(len(sink.get_loaded_records()), 1)

    def test_skips_non_enriched(self):
        sink = DevNullSink()
        stage = LoadStage(sink)
        record = DataRecord(number=3, status=RecordStatus.TRANSFORMED)
        result = stage.process([record])
        self.assertEqual(result[0].status, RecordStatus.TRANSFORMED)

    def test_statistics(self):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        sink = DevNullSink()
        stage = LoadStage(sink)
        records = []
        for n in [3, 5, 15]:
            r = DataRecord(number=n, status=RecordStatus.ENRICHED)
            r.fizzbuzz_result = FizzBuzzResult(number=n, output=str(n))
            records.append(r)
        stage.process(records)
        stats = stage.get_statistics()
        self.assertEqual(stats["records_processed"], 3)


# ============================================================
# Pipeline DAG Tests
# ============================================================


class TestPipelineDAG(unittest.TestCase):
    """Tests for the pipeline DAG and topological sort."""

    def test_empty_dag(self):
        dag = PipelineDAG()
        result = dag.topological_sort()
        self.assertEqual(len(result), 0)

    def test_single_stage(self):
        dag = PipelineDAG()
        dag.add_stage(ExtractStage(RangeSource()))
        result = dag.topological_sort()
        self.assertEqual(len(result), 1)

    def test_linear_chain(self):
        dag = PipelineDAG()
        extract = ExtractStage(RangeSource())
        validate = ValidateStage()
        dag.add_stage(extract)
        dag.add_stage(validate, dependencies=["Extract"])
        result = dag.topological_sort()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Extract")
        self.assertEqual(result[1].name, "Validate")

    def test_full_pipeline_dag(self):
        dag = PipelineDAG()
        dag.add_stage(ExtractStage(RangeSource()))
        dag.add_stage(ValidateStage(), dependencies=["Extract"])
        dag.add_stage(TransformStage(), dependencies=["Validate"])
        dag.add_stage(EnrichStage(), dependencies=["Transform"])
        dag.add_stage(LoadStage(DevNullSink()), dependencies=["Enrich"])
        result = dag.topological_sort()
        self.assertEqual(len(result), 5)
        names = [s.name for s in result]
        self.assertEqual(names, ["Extract", "Validate", "Transform", "Enrich", "Load"])

    def test_node_count(self):
        dag = PipelineDAG()
        dag.add_stage(ExtractStage(RangeSource()))
        dag.add_stage(ValidateStage(), dependencies=["Extract"])
        self.assertEqual(dag.node_count, 2)

    def test_edge_count(self):
        dag = PipelineDAG()
        dag.add_stage(ExtractStage(RangeSource()))
        dag.add_stage(ValidateStage(), dependencies=["Extract"])
        self.assertEqual(dag.edge_count, 1)

    def test_render_dag(self):
        dag = PipelineDAG()
        dag.add_stage(ExtractStage(RangeSource()))
        dag.add_stage(ValidateStage(), dependencies=["Extract"])
        rendered = dag.render(width=60)
        self.assertIn("PIPELINE DAG", rendered)
        self.assertIn("Extract", rendered)
        self.assertIn("Validate", rendered)

    def test_get_node(self):
        dag = PipelineDAG()
        dag.add_stage(ExtractStage(RangeSource()))
        node = dag.get_node("Extract")
        self.assertIsNotNone(node)
        self.assertEqual(node.stage.name, "Extract")

    def test_get_nonexistent_node(self):
        dag = PipelineDAG()
        self.assertIsNone(dag.get_node("Nonexistent"))


# ============================================================
# DAG Executor Tests
# ============================================================


class TestDAGExecutor(unittest.TestCase):
    """Tests for the DAG executor with retry and checkpointing."""

    def _build_simple_dag(self):
        dag = PipelineDAG()
        dag.add_stage(ExtractStage(RangeSource()))
        dag.add_stage(ValidateStage(), dependencies=["Extract"])
        dag.add_stage(TransformStage(), dependencies=["Validate"])
        dag.add_stage(EnrichStage(), dependencies=["Transform"])
        dag.add_stage(LoadStage(DevNullSink()), dependencies=["Enrich"])
        return dag

    def test_full_execution(self):
        dag = self._build_simple_dag()
        executor = DAGExecutor(dag, enable_checkpoints=True)
        records = [DataRecord(number=n) for n in range(1, 6)]
        results = executor.execute(records)
        loaded = [r for r in results if r.status == RecordStatus.LOADED]
        self.assertEqual(len(loaded), 5)

    def test_checkpoints_created(self):
        dag = self._build_simple_dag()
        executor = DAGExecutor(dag, enable_checkpoints=True)
        records = [DataRecord(number=n) for n in range(1, 4)]
        executor.execute(records)
        self.assertEqual(len(executor.checkpoints), 5)  # One per stage

    def test_no_checkpoints_when_disabled(self):
        dag = self._build_simple_dag()
        executor = DAGExecutor(dag, enable_checkpoints=False)
        records = [DataRecord(number=1)]
        executor.execute(records)
        self.assertEqual(len(executor.checkpoints), 0)

    def test_execution_log(self):
        dag = self._build_simple_dag()
        executor = DAGExecutor(dag)
        records = [DataRecord(number=15)]
        executor.execute(records)
        log = executor.execution_log
        self.assertEqual(len(log), 5)
        self.assertTrue(all(entry["success"] for entry in log))

    def test_statistics(self):
        dag = self._build_simple_dag()
        executor = DAGExecutor(dag)
        records = [DataRecord(number=1)]
        executor.execute(records)
        stats = executor.get_statistics()
        self.assertEqual(stats["checkpoints"], 5)
        self.assertGreater(stats["total_duration_ms"], 0)

    def test_event_bus_integration(self):
        dag = self._build_simple_dag()
        mock_bus = MagicMock()
        executor = DAGExecutor(dag, event_bus=mock_bus)
        records = [DataRecord(number=1)]
        executor.execute(records)
        self.assertTrue(mock_bus.publish.called)


# ============================================================
# Data Lineage Tracker Tests
# ============================================================


class TestDataLineageTracker(unittest.TestCase):
    """Tests for the data lineage provenance tracker."""

    def test_track_record(self):
        tracker = DataLineageTracker()
        record = DataRecord(number=42)
        record.add_lineage("Extract", "Extracted 42")
        tracker.track(record)
        self.assertEqual(tracker.tracked_count, 1)

    def test_get_lineage(self):
        tracker = DataLineageTracker()
        record = DataRecord(number=42)
        record.add_lineage("Extract", "op1")
        record.add_lineage("Validate", "op2")
        tracker.track(record)
        lineage = tracker.get_lineage(record.record_id)
        self.assertEqual(len(lineage), 2)

    def test_get_nonexistent_lineage(self):
        tracker = DataLineageTracker()
        lineage = tracker.get_lineage("nonexistent-id")
        self.assertEqual(len(lineage), 0)

    def test_get_all_lineages(self):
        tracker = DataLineageTracker()
        for n in range(3):
            record = DataRecord(number=n)
            record.add_lineage("Extract", f"op{n}")
            tracker.track(record)
        self.assertEqual(len(tracker.get_all_lineages()), 3)

    def test_render_lineage(self):
        tracker = DataLineageTracker()
        record = DataRecord(number=15)
        record.add_lineage("Extract", "Extracted 15")
        record.add_lineage("Transform", "Transformed to FizzBuzz")
        tracker.track(record)
        rendered = tracker.render_lineage(record.record_id)
        self.assertIn("DATA LINEAGE", rendered)
        self.assertIn("Extract", rendered)

    def test_render_nonexistent(self):
        tracker = DataLineageTracker()
        rendered = tracker.render_lineage("nope")
        self.assertIn("No lineage found", rendered)


# ============================================================
# Backfill Engine Tests
# ============================================================


class TestBackfillEngine(unittest.TestCase):
    """Tests for the retroactive backfill enrichment engine."""

    def test_backfill_loaded_records(self):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        enrich = EnrichStage()
        engine = BackfillEngine(enrich)

        record = DataRecord(number=5, status=RecordStatus.LOADED)
        record.fizzbuzz_result = FizzBuzzResult(number=5, output="Buzz")
        result = engine.backfill([record])
        self.assertEqual(result[0].status, RecordStatus.LOADED)
        self.assertEqual(engine.backfill_count, 1)

    def test_skips_non_loaded(self):
        enrich = EnrichStage()
        engine = BackfillEngine(enrich)
        record = DataRecord(number=5, status=RecordStatus.TRANSFORMED)
        engine.backfill([record])
        self.assertEqual(engine.backfill_count, 0)

    def test_backfill_with_event_bus(self):
        enrich = EnrichStage()
        mock_bus = MagicMock()
        engine = BackfillEngine(enrich, event_bus=mock_bus)
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        record = DataRecord(number=3, status=RecordStatus.LOADED)
        record.fizzbuzz_result = FizzBuzzResult(number=3, output="Fizz")
        engine.backfill([record])
        self.assertTrue(mock_bus.publish.called)


# ============================================================
# Pipeline Builder Tests
# ============================================================


class TestPipelineBuilder(unittest.TestCase):
    """Tests for the pipeline builder."""

    def test_default_build(self):
        pipeline = PipelineBuilder().build()
        self.assertIsNotNone(pipeline)
        self.assertIsInstance(pipeline.source, RangeSource)
        self.assertIsInstance(pipeline.sink, StdoutSink)

    def test_custom_source_and_sink(self):
        pipeline = (
            PipelineBuilder()
            .with_source(DevNullSource())
            .with_sink(DevNullSink())
            .build()
        )
        self.assertIsInstance(pipeline.source, DevNullSource)
        self.assertIsInstance(pipeline.sink, DevNullSink)

    def test_with_lineage_disabled(self):
        pipeline = PipelineBuilder().with_lineage(False).build()
        self.assertIsNone(pipeline.lineage_tracker)

    def test_with_backfill_enabled(self):
        pipeline = PipelineBuilder().with_backfill(True).build()
        self.assertIsNotNone(pipeline.backfill_engine)

    def test_with_backfill_disabled(self):
        pipeline = PipelineBuilder().with_backfill(False).build()
        self.assertIsNone(pipeline.backfill_engine)

    def test_with_custom_rules(self):
        rules = [RuleDefinition(name="WazzRule", divisor=7, label="Wazz", priority=1)]
        pipeline = PipelineBuilder().with_rules(rules).with_sink(DevNullSink()).build()
        records = pipeline.run(7, 7)
        self.assertEqual(records[0].fizzbuzz_result.output, "Wazz")


# ============================================================
# Pipeline Integration Tests
# ============================================================


class TestPipelineIntegration(unittest.TestCase):
    """End-to-end tests for the full ETL pipeline."""

    def test_full_pipeline_range_1_to_15(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        records = pipeline.run(1, 15)
        loaded = [r for r in records if r.status == RecordStatus.LOADED]
        self.assertEqual(len(loaded), 15)

    def test_fizzbuzz_correctness(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        records = pipeline.run(1, 15)
        outputs = {r.number: r.fizzbuzz_result.output for r in records if r.fizzbuzz_result}
        self.assertEqual(outputs[3], "Fizz")
        self.assertEqual(outputs[5], "Buzz")
        self.assertEqual(outputs[15], "FizzBuzz")
        self.assertEqual(outputs[7], "7")

    def test_enrichments_present(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        records = pipeline.run(5, 5)
        record = records[0]
        self.assertIn("is_fibonacci", record.enrichments)
        self.assertIn("is_prime", record.enrichments)
        self.assertIn("roman_numeral", record.enrichments)
        self.assertIn("emotional_valence", record.enrichments)

    def test_lineage_tracked(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        records = pipeline.run(1, 3)
        self.assertIsNotNone(pipeline.lineage_tracker)
        self.assertEqual(pipeline.lineage_tracker.tracked_count, 3)

    def test_devnull_source_pipeline(self):
        pipeline = (
            PipelineBuilder()
            .with_source(DevNullSource())
            .with_sink(DevNullSink())
            .build()
        )
        records = pipeline.run(1, 100)
        self.assertEqual(len(records), 0)

    def test_pipeline_with_backfill(self):
        pipeline = (
            PipelineBuilder()
            .with_sink(DevNullSink())
            .with_backfill(True)
            .build()
        )
        records = pipeline.run(1, 5)
        self.assertIsNotNone(pipeline.backfill_engine)
        self.assertGreater(pipeline.backfill_engine.backfill_count, 0)

    def test_last_results(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        pipeline.run(1, 3)
        self.assertEqual(len(pipeline.last_results), 3)


# ============================================================
# Pipeline Dashboard Tests
# ============================================================


class TestPipelineDashboard(unittest.TestCase):
    """Tests for the pipeline ASCII dashboard."""

    def test_render_dashboard(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        records = pipeline.run(1, 5)
        rendered = PipelineDashboard.render(
            executor=pipeline.executor,
            dag=pipeline.dag,
            records=records,
            lineage_tracker=pipeline.lineage_tracker,
        )
        self.assertIn("DATA PIPELINE", rendered)
        self.assertIn("PIPELINE SUMMARY", rendered)
        self.assertIn("STAGE EXECUTION LOG", rendered)

    def test_render_dag(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        rendered = PipelineDashboard.render_dag(pipeline.dag)
        self.assertIn("PIPELINE DAG", rendered)

    def test_render_lineage(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        records = pipeline.run(1, 3)
        rendered = PipelineDashboard.render_lineage(
            lineage_tracker=pipeline.lineage_tracker,
            records=records,
        )
        self.assertIn("DATA LINEAGE", rendered)


# ============================================================
# Pipeline Middleware Tests
# ============================================================


class TestPipelineMiddleware(unittest.TestCase):
    """Tests for the PipelineMiddleware IMiddleware implementation."""

    def test_get_name(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        mw = PipelineMiddleware(pipeline)
        self.assertEqual(mw.get_name(), "PipelineMiddleware")

    def test_get_priority(self):
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        mw = PipelineMiddleware(pipeline)
        self.assertEqual(mw.get_priority(), 11)

    def test_middleware_tracks_records(self):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        pipeline = PipelineBuilder().with_sink(DevNullSink()).build()
        mw = PipelineMiddleware(pipeline)

        context = ProcessingContext(number=15, session_id="test-session")
        result_record = FizzBuzzResult(number=15, output="FizzBuzz")
        context.results = [result_record]

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        self.assertEqual(mw.records_tracked, 1)
        self.assertIsNotNone(pipeline.lineage_tracker)
        self.assertEqual(pipeline.lineage_tracker.tracked_count, 1)


# ============================================================
# Exception Tests
# ============================================================


class TestDataPipelineExceptions(unittest.TestCase):
    """Tests for data pipeline exception hierarchy."""

    def test_base_exception(self):
        ex = DataPipelineError("test error")
        self.assertIn("EFP-DP00", str(ex))

    def test_source_connector_error(self):
        ex = SourceConnectorError("RangeSource", "range was empty")
        self.assertIn("EFP-DP01", str(ex))
        self.assertIn("RangeSource", str(ex))

    def test_sink_connector_error(self):
        ex = SinkConnectorError("StdoutSink", "stdout closed")
        self.assertIn("EFP-DP02", str(ex))

    def test_validation_stage_error(self):
        ex = ValidationStageError("rec-001", "not an integer")
        self.assertIn("EFP-DP03", str(ex))

    def test_transform_stage_error(self):
        ex = TransformStageError("rec-001", 15, "modulo failed")
        self.assertIn("EFP-DP04", str(ex))

    def test_enrich_stage_error(self):
        ex = EnrichStageError("rec-001", "fibonacci", "overflow")
        self.assertIn("EFP-DP05", str(ex))

    def test_load_stage_error(self):
        ex = LoadStageError("rec-001", "StdoutSink", "pipe broken")
        self.assertIn("EFP-DP06", str(ex))

    def test_dag_resolution_error(self):
        ex = DAGResolutionError("cycle detected")
        self.assertIn("EFP-DP07", str(ex))

    def test_checkpoint_error(self):
        ex = CheckpointError("Transform", "memory full")
        self.assertIn("EFP-DP08", str(ex))

    def test_backfill_error(self):
        ex = BackfillError("rec-001", "re-enrichment failed")
        self.assertIn("EFP-DP09", str(ex))

    def test_lineage_tracking_error(self):
        ex = LineageTrackingError("rec-001", "chain broken")
        self.assertIn("EFP-DP10", str(ex))

    def test_retry_exhausted_error(self):
        ex = PipelineStageRetryExhaustedError("Transform", 3, "modulo refused")
        self.assertIn("EFP-DP11", str(ex))

    def test_dashboard_render_error(self):
        ex = PipelineDashboardRenderError("width too narrow")
        self.assertIn("EFP-DP12", str(ex))

    def test_all_inherit_from_base(self):
        exceptions = [
            SourceConnectorError("x", "y"),
            SinkConnectorError("x", "y"),
            ValidationStageError("x", "y"),
            TransformStageError("x", 1, "y"),
            EnrichStageError("x", "y", "z"),
            LoadStageError("x", "y", "z"),
            DAGResolutionError("x"),
            CheckpointError("x", "y"),
            BackfillError("x", "y"),
            LineageTrackingError("x", "y"),
            PipelineStageRetryExhaustedError("x", 1, "y"),
            PipelineDashboardRenderError("x"),
        ]
        for ex in exceptions:
            self.assertIsInstance(ex, DataPipelineError)


# ============================================================
# EventType Tests
# ============================================================


class TestPipelineEventTypes(unittest.TestCase):
    """Tests for pipeline event types in the EventType enum."""

    def test_pipeline_started(self):
        self.assertIsNotNone(EventType.PIPELINE_STARTED)

    def test_pipeline_completed(self):
        self.assertIsNotNone(EventType.PIPELINE_COMPLETED)

    def test_pipeline_stage_entered(self):
        self.assertIsNotNone(EventType.PIPELINE_STAGE_ENTERED)

    def test_pipeline_stage_completed(self):
        self.assertIsNotNone(EventType.PIPELINE_STAGE_COMPLETED)

    def test_pipeline_record_extracted(self):
        self.assertIsNotNone(EventType.PIPELINE_RECORD_EXTRACTED)

    def test_pipeline_record_validated(self):
        self.assertIsNotNone(EventType.PIPELINE_RECORD_VALIDATED)

    def test_pipeline_record_transformed(self):
        self.assertIsNotNone(EventType.PIPELINE_RECORD_TRANSFORMED)

    def test_pipeline_record_enriched(self):
        self.assertIsNotNone(EventType.PIPELINE_RECORD_ENRICHED)

    def test_pipeline_record_loaded(self):
        self.assertIsNotNone(EventType.PIPELINE_RECORD_LOADED)

    def test_pipeline_dag_resolved(self):
        self.assertIsNotNone(EventType.PIPELINE_DAG_RESOLVED)

    def test_pipeline_checkpoint_saved(self):
        self.assertIsNotNone(EventType.PIPELINE_CHECKPOINT_SAVED)

    def test_pipeline_backfill_started(self):
        self.assertIsNotNone(EventType.PIPELINE_BACKFILL_STARTED)

    def test_pipeline_backfill_completed(self):
        self.assertIsNotNone(EventType.PIPELINE_BACKFILL_COMPLETED)

    def test_pipeline_dashboard_rendered(self):
        self.assertIsNotNone(EventType.PIPELINE_DASHBOARD_RENDERED)


# ============================================================
# Enum Tests
# ============================================================


class TestPipelineEnums(unittest.TestCase):
    """Tests for pipeline-specific enumerations."""

    def test_pipeline_stage_types(self):
        self.assertEqual(len(PipelineStageType), 5)
        self.assertIn(PipelineStageType.EXTRACT, PipelineStageType)
        self.assertIn(PipelineStageType.VALIDATE, PipelineStageType)
        self.assertIn(PipelineStageType.TRANSFORM, PipelineStageType)
        self.assertIn(PipelineStageType.ENRICH, PipelineStageType)
        self.assertIn(PipelineStageType.LOAD, PipelineStageType)

    def test_record_status(self):
        self.assertEqual(len(RecordStatus), 7)

    def test_emotional_valence(self):
        self.assertEqual(len(EmotionalValence), 7)
        self.assertEqual(EmotionalValence.ECSTATIC.value, "ecstatic")
        self.assertEqual(EmotionalValence.DESPONDENT.value, "despondent")


if __name__ == "__main__":
    unittest.main()

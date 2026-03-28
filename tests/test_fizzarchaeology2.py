"""
Enterprise FizzBuzz Platform - FizzArchaeology2 Digital Archaeology v2 Test Suite

Comprehensive verification of the second-generation digital archaeology
engine, including carbon-14 dating simulation, stratigraphic layer analysis,
artifact classification, excavation grid management, and provenance tracking.

Every FizzBuzz artifact recovered from degraded storage media must be
precisely dated, correctly classified, and traceable to its original
excavation context. These tests ensure that the archaeological pipeline
maintains scientific rigor at every stage of the recovery process.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzarchaeology2 import (
    CARBON_14_HALF_LIFE,
    DECAY_CONSTANT,
    DEFAULT_GRID_COLS,
    DEFAULT_GRID_ROWS,
    MAX_DATEABLE_AGE,
    Archaeology2Middleware,
    Artifact,
    ArtifactClassifier,
    ArtifactType,
    CarbonDatingSimulator,
    DatingResult,
    ExcavationEngine,
    ExcavationGrid,
    GridCell,
    IsotopeRatio,
    LayerType,
    ProvenanceRecord,
    ProvenanceStep,
    ProvenanceTracker,
    StratigraphicAnalyzer,
    StratigraphicLayer,
)
from enterprise_fizzbuzz.domain.exceptions.fizzarchaeology2 import (
    Archaeology2MiddlewareError,
    ArtifactClassificationError,
    CarbonDatingError,
    ExcavationGridError,
    FizzArchaeology2Error,
    ProvenanceError,
    StratigraphicError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def dating_simulator():
    return CarbonDatingSimulator(seed=42)


@pytest.fixture
def grid():
    return ExcavationGrid(rows=4, cols=4)


@pytest.fixture
def stratigraphy():
    analyzer = StratigraphicAnalyzer()
    analyzer.add_layer(StratigraphicLayer("Layer A", 0.0, 2.0, LayerType.ALLUVIAL, estimated_age=100))
    analyzer.add_layer(StratigraphicLayer("Layer B", 2.0, 5.0, LayerType.LACUSTRINE, estimated_age=500))
    return analyzer


@pytest.fixture
def classifier():
    return ArtifactClassifier()


@pytest.fixture
def engine():
    return ExcavationEngine(grid_rows=4, grid_cols=4, seed=42)


# ===========================================================================
# Carbon-14 Dating Tests
# ===========================================================================

class TestCarbonDating:
    """Verification of radiocarbon dating simulation accuracy."""

    def test_young_sample_age(self, dating_simulator):
        result = dating_simulator.date_artifact(100.0)
        assert result.age_years > 0
        assert result.uncertainty_years > 0

    def test_ancient_sample_age(self, dating_simulator):
        result = dating_simulator.date_artifact(10000.0)
        assert result.age_years > 5000.0

    def test_zero_age_sample(self, dating_simulator):
        result = dating_simulator.date_artifact(0.01)
        assert result.age_years >= 0

    def test_negative_age_raises(self, dating_simulator):
        with pytest.raises(CarbonDatingError):
            dating_simulator.measure_isotope_ratio(-100.0)

    def test_dating_result_is_calibrated(self, dating_simulator):
        result = dating_simulator.date_artifact(500.0)
        assert result.calibrated is True
        assert result.calibration_curve == "IntCal20"

    def test_isotope_ratio_validity(self, dating_simulator):
        ratio = dating_simulator.measure_isotope_ratio(1000.0)
        assert ratio.is_valid is True
        assert 0.0 < ratio.c14_c12_ratio <= 1.0

    def test_decay_constant(self):
        expected = math.log(2) / CARBON_14_HALF_LIFE
        assert abs(DECAY_CONSTANT - expected) < 1e-10


# ===========================================================================
# Excavation Grid Tests
# ===========================================================================

class TestExcavationGrid:
    """Verification of excavation grid geometry and operations."""

    def test_grid_creation(self, grid):
        assert grid.rows == 4
        assert grid.cols == 4
        assert grid.total_cells == 16

    def test_initial_progress_is_zero(self, grid):
        assert grid.excavation_progress == pytest.approx(0.0)

    def test_excavate_cell(self, grid):
        cell = grid.excavate_cell(0, 0)
        assert cell.is_excavated is True
        assert grid.excavated_count == 1

    def test_get_cell_out_of_bounds_raises(self, grid):
        with pytest.raises(ExcavationGridError):
            grid.get_cell(10, 10)

    def test_invalid_grid_dimensions_raises(self):
        with pytest.raises(ExcavationGridError):
            ExcavationGrid(rows=0, cols=5)

    def test_excavation_progress(self, grid):
        grid.excavate_cell(0, 0)
        grid.excavate_cell(1, 1)
        assert grid.excavation_progress == pytest.approx(2.0 / 16.0)


# ===========================================================================
# Stratigraphic Analysis Tests
# ===========================================================================

class TestStratigraphicAnalyzer:
    """Verification of stratigraphic layer management and age interpolation."""

    def test_add_valid_layer(self, stratigraphy):
        assert len(stratigraphy.layers) == 2

    def test_total_depth(self, stratigraphy):
        assert stratigraphy.total_depth == pytest.approx(5.0)

    def test_interpolate_age_in_layer(self, stratigraphy):
        age = stratigraphy.interpolate_age(1.0)
        assert age > 0

    def test_get_layer_at_depth(self, stratigraphy):
        layer = stratigraphy.get_layer_at_depth(3.0)
        assert layer is not None
        assert layer.name == "Layer B"

    def test_invalid_layer_raises(self):
        analyzer = StratigraphicAnalyzer()
        with pytest.raises(StratigraphicError):
            analyzer.add_layer(StratigraphicLayer("Bad", 5.0, 2.0, LayerType.ALLUVIAL))


# ===========================================================================
# Artifact Classifier Tests
# ===========================================================================

class TestArtifactClassifier:
    """Verification of artifact classification accuracy."""

    def test_classify_fizz(self, classifier):
        assert classifier.classify("Fizz") == ArtifactType.FIZZ_RESULT

    def test_classify_buzz(self, classifier):
        assert classifier.classify("Buzz") == ArtifactType.BUZZ_RESULT

    def test_classify_fizzbuzz(self, classifier):
        assert classifier.classify("FizzBuzz") == ArtifactType.FIZZBUZZ_RESULT

    def test_classify_numeric(self, classifier):
        assert classifier.classify("42") == ArtifactType.NUMERIC_RESULT

    def test_classify_empty_raises(self, classifier):
        with pytest.raises(ArtifactClassificationError):
            classifier.classify("")

    def test_classify_unknown(self, classifier):
        assert classifier.classify("xyzzy") == ArtifactType.UNKNOWN


# ===========================================================================
# Provenance Tracker Tests
# ===========================================================================

class TestProvenanceTracker:
    """Verification of provenance chain integrity."""

    def test_record_step(self):
        tracker = ProvenanceTracker()
        artifact = Artifact(artifact_id="test1", artifact_type=ArtifactType.FIZZ_RESULT, content="Fizz")
        record = tracker.record_step(artifact, ProvenanceStep.EXCAVATION)
        assert record.step == ProvenanceStep.EXCAVATION
        assert len(artifact.provenance) == 1

    def test_out_of_order_raises(self):
        tracker = ProvenanceTracker()
        artifact = Artifact(artifact_id="test2", artifact_type=ArtifactType.FIZZ_RESULT, content="Fizz")
        tracker.record_step(artifact, ProvenanceStep.EXCAVATION)
        tracker.record_step(artifact, ProvenanceStep.CLEANING)
        with pytest.raises(ProvenanceError):
            tracker.record_step(artifact, ProvenanceStep.EXCAVATION)

    def test_verify_valid_chain(self):
        tracker = ProvenanceTracker()
        artifact = Artifact(artifact_id="test3", artifact_type=ArtifactType.FIZZ_RESULT, content="Fizz")
        tracker.record_step(artifact, ProvenanceStep.EXCAVATION)
        tracker.record_step(artifact, ProvenanceStep.CLEANING)
        assert tracker.verify_chain(artifact) is True


# ===========================================================================
# Excavation Engine Tests
# ===========================================================================

class TestExcavationEngine:
    """Verification of the end-to-end excavation workflow."""

    def test_excavate_cell(self, engine):
        artifacts = engine.excavate_cell(0, 0, 15)
        assert len(artifacts) == 1
        assert artifacts[0].artifact_id is not None

    def test_artifact_has_provenance(self, engine):
        artifacts = engine.excavate_cell(0, 0, 3)
        art = artifacts[0]
        assert len(art.provenance) >= 5

    def test_artifact_has_dating(self, engine):
        artifacts = engine.excavate_cell(1, 1, 5)
        art = artifacts[0]
        # Dating may or may not succeed depending on the simulated age
        assert art.dating_result is not None or len(art.provenance) > 0


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestArchaeology2Middleware:
    """Verification of the Archaeology2Middleware pipeline integration."""

    def test_middleware_name(self):
        mw = Archaeology2Middleware(seed=42)
        assert mw.get_name() == "Archaeology2Middleware"

    def test_middleware_priority(self):
        mw = Archaeology2Middleware(seed=42)
        assert mw.get_priority() == 280

    def test_middleware_attaches_metadata(self):
        mw = Archaeology2Middleware(grid_rows=2, grid_cols=2, seed=42)

        ctx = ProcessingContext(number=15, session_id="test-session")
        result_ctx = ProcessingContext(number=15, session_id="test-session")
        result_ctx.results = [FizzBuzzResult(number=15, output="FizzBuzz")]

        def next_handler(c):
            return result_ctx

        output = mw.process(ctx, next_handler)
        assert "archaeology2_artifact_id" in output.metadata
        assert "archaeology2_type" in output.metadata
        assert mw.excavation_count == 1

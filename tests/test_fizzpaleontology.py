"""
Enterprise FizzBuzz Platform - FizzPaleontology Fossil Record Analyzer Test Suite

Comprehensive verification of the paleontological analysis pipeline,
including taxonomic classification, extinction event detection,
phylogenetic inference, and morphometric analysis. An incorrect
taxonomic assignment could place a "Fizz" specimen in a "Buzz" clade,
fundamentally misrepresenting the evolutionary history of the
FizzBuzz fauna.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzpaleontology import (
    BACKGROUND_EXTINCTION_RATE,
    EXTINCTION_THRESHOLD,
    GEOLOGICAL_PERIODS,
    MIN_SAMPLE_SIZE,
    TAXONOMIC_RANKS,
    ExtinctionDetector,
    ExtinctionEvent,
    FossilSpecimen,
    MorphometricAnalyzer,
    PaleontologyEngine,
    PaleontologyMiddleware,
    ParsimonyInference,
    PhylogeneticNode,
    Taxon,
    TaxonomicClassifier,
    TaxonomicRank,
    create_specimen,
    number_to_measurements,
)
from enterprise_fizzbuzz.domain.exceptions.fizzpaleontology import (
    BiostratigraphyError,
    ExtinctionEventError,
    FizzPaleontologyError,
    MorphometricError,
    PaleontologyMiddlewareError,
    PhylogeneticError,
    StratigraphicAgeError,
    TaxonomicError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(number: int, output: str = "", is_fizz: bool = False, is_buzz: bool = False):
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


# ===========================================================================
# Taxonomic Classifier Tests
# ===========================================================================

class TestTaxonomicClassifier:
    """Verification of the Linnaean taxonomic classification engine."""

    def test_classify_returns_taxon(self):
        tc = TaxonomicClassifier()
        taxon = tc.classify(42)
        assert isinstance(taxon, Taxon)
        assert taxon.rank == TaxonomicRank.SPECIES

    def test_deterministic_classification(self):
        tc = TaxonomicClassifier()
        t1 = tc.classify(42)
        tc2 = TaxonomicClassifier()
        t2 = tc2.classify(42)
        assert t1.name == t2.name

    def test_taxa_count_increments(self):
        tc = TaxonomicClassifier()
        tc.classify(1)
        tc.classify(2)
        assert tc.taxa_count == 2

    def test_first_appearance_set(self):
        tc = TaxonomicClassifier()
        taxon = tc.classify(7)
        assert taxon.first_appearance == 7


# ===========================================================================
# Extinction Detector Tests
# ===========================================================================

class TestExtinctionDetector:
    """Verification of extinction event detection."""

    def test_no_event_on_stable_diversity(self):
        ed = ExtinctionDetector()
        ed.record_diversity(1, 100)
        event = ed.record_diversity(2, 98)
        assert event is None

    def test_mass_extinction_detected(self):
        ed = ExtinctionDetector()
        ed.record_diversity(1, 100)
        event = ed.record_diversity(2, 50)
        assert event is not None
        assert event.severity == "mass"

    def test_moderate_extinction_detected(self):
        ed = ExtinctionDetector()
        ed.record_diversity(1, 100)
        event = ed.record_diversity(2, 75)
        assert event is not None
        assert event.severity == "moderate"

    def test_total_events_accumulate(self):
        ed = ExtinctionDetector()
        ed.record_diversity(1, 100)
        ed.record_diversity(2, 50)
        ed.record_diversity(3, 100)
        ed.record_diversity(4, 40)
        assert ed.total_events == 2


# ===========================================================================
# Phylogenetic Inference Tests
# ===========================================================================

class TestParsimonyInference:
    """Verification of maximum parsimony phylogenetic inference."""

    def test_two_taxa_produces_tree(self):
        pi = ParsimonyInference()
        pi.add_taxon("A", [1, 0, 1, 0])
        pi.add_taxon("B", [0, 1, 0, 1])
        tree = pi.infer_tree()
        assert tree is not None
        assert tree.count_leaves() == 2

    def test_single_taxon_returns_none(self):
        pi = ParsimonyInference()
        pi.add_taxon("A", [1, 0])
        tree = pi.infer_tree()
        assert tree is None

    def test_three_taxa_tree_structure(self):
        pi = ParsimonyInference()
        pi.add_taxon("A", [1, 0, 0])
        pi.add_taxon("B", [1, 1, 0])
        pi.add_taxon("C", [0, 0, 1])
        tree = pi.infer_tree()
        assert tree is not None
        assert tree.count_leaves() == 3

    def test_tree_length_computed(self):
        pi = ParsimonyInference()
        pi.add_taxon("A", [1, 0])
        pi.add_taxon("B", [0, 1])
        tree = pi.infer_tree()
        length = pi.tree_length(tree)
        assert length >= 0


# ===========================================================================
# Morphometric Analyzer Tests
# ===========================================================================

class TestMorphometricAnalyzer:
    """Verification of morphometric analysis."""

    def test_disparity_zero_with_few_samples(self):
        ma = MorphometricAnalyzer()
        ma.add_specimen("S1", [1.0, 2.0])
        assert ma.compute_disparity() == 0.0

    def test_disparity_positive_with_enough_samples(self):
        ma = MorphometricAnalyzer()
        ma.add_specimen("S1", [1.0, 2.0])
        ma.add_specimen("S2", [3.0, 4.0])
        ma.add_specimen("S3", [5.0, 6.0])
        assert ma.compute_disparity() > 0.0

    def test_covariance_matrix_dimensions(self):
        ma = MorphometricAnalyzer()
        ma.add_specimen("S1", [1.0, 2.0, 3.0])
        ma.add_specimen("S2", [4.0, 5.0, 6.0])
        cov = ma.compute_covariance_matrix()
        assert len(cov) == 3
        assert len(cov[0]) == 3


# ===========================================================================
# Specimen Factory Tests
# ===========================================================================

class TestSpecimenFactory:
    """Verification of specimen creation from numbers."""

    def test_measurements_have_five_dimensions(self):
        m = number_to_measurements(42)
        assert len(m) == 5

    def test_fizzbuzz_lowers_quality(self):
        tc = TaxonomicClassifier()
        taxon = tc.classify(15)
        specimen = create_specimen(15, taxon, is_fizz=True, is_buzz=True)
        assert specimen.preservation_quality < 1.0

    def test_plain_number_full_quality(self):
        tc = TaxonomicClassifier()
        taxon = tc.classify(7)
        specimen = create_specimen(7, taxon, is_fizz=False, is_buzz=False)
        assert specimen.preservation_quality == 1.0


# ===========================================================================
# Paleontology Engine Tests
# ===========================================================================

class TestPaleontologyEngine:
    """Verification of the integrated paleontology engine."""

    def test_process_returns_diagnostics(self):
        engine = PaleontologyEngine()
        diag = engine.process_number(1, False, False)
        assert "taxon_name" in diag
        assert "living_taxa" in diag
        assert "disparity" in diag

    def test_fizzbuzz_triggers_mass_extinction(self):
        engine = PaleontologyEngine()
        # Add enough taxa first
        for i in range(1, 15):
            engine.process_number(i, False, False)
        diag = engine.process_number(15, True, True)
        # After mass extinction, living taxa should decrease
        assert diag["living_taxa"] < 15

    def test_step_count_increments(self):
        engine = PaleontologyEngine()
        engine.process_number(1, False, False)
        engine.process_number(2, False, False)
        assert engine.step_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestPaleontologyMiddleware:
    """Verification of the FizzPaleontology middleware integration."""

    def test_middleware_name(self):
        mw = PaleontologyMiddleware()
        assert mw.get_name() == "PaleontologyMiddleware"

    def test_middleware_priority(self):
        mw = PaleontologyMiddleware()
        assert mw.get_priority() == 288

    def test_middleware_attaches_metadata(self):
        mw = PaleontologyMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "paleo_taxon" in result.metadata

    def test_middleware_increments_evaluations(self):
        mw = PaleontologyMiddleware()
        ctx = _make_context(1, "1")
        mw.process(ctx, lambda c: c)
        assert mw.evaluations == 1

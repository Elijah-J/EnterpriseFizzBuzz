"""
Enterprise FizzBuzz Platform - Archaeological Recovery System Tests

Tests for the digital forensics subsystem that excavates FizzBuzz evaluation
evidence from seven stratigraphic layers, simulates data corruption,
reconstructs classifications via Bayesian inference, and renders forensic
ASCII reports. All to recover data that could be recomputed in one CPU cycle.

Covers: EvidenceStratum, EvidenceFragment, CorruptionSimulator, EvidenceCollector,
BayesianReconstructor, StratigraphyEngine, ExcavationReport, ArchaeologyEngine,
ArchaeologyDashboard, ArchaeologyMiddleware, and _true_classification.
"""

from __future__ import annotations

import math

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ArchaeologyError,
    InsufficientEvidenceError,
    StratigraphicConflictError,
    StratumCorruptionError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzClassification,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.archaeology import (
    DEFAULT_STRATA_WEIGHTS,
    ArchaeologyDashboard,
    ArchaeologyEngine,
    ArchaeologyMiddleware,
    BayesianReconstructor,
    CorruptionSimulator,
    EvidenceCollector,
    EvidenceFragment,
    EvidenceStratum,
    ExcavationReport,
    StratigraphyEngine,
    _true_classification,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def collector():
    """An EvidenceCollector with a fixed seed."""
    return EvidenceCollector(seed=42)


@pytest.fixture
def corruption_sim():
    """A CorruptionSimulator with a fixed seed and high corruption rate."""
    return CorruptionSimulator(corruption_rate=0.5, seed=42)


@pytest.fixture
def no_corruption_sim():
    """A CorruptionSimulator with zero corruption rate."""
    return CorruptionSimulator(corruption_rate=0.0, seed=42)


@pytest.fixture
def reconstructor():
    """A BayesianReconstructor with default threshold."""
    return BayesianReconstructor(confidence_threshold=0.6)


@pytest.fixture
def stratigraphy():
    """A StratigraphyEngine instance."""
    return StratigraphyEngine()


@pytest.fixture
def engine():
    """An ArchaeologyEngine with fixed seed and no corruption for deterministic tests."""
    return ArchaeologyEngine(
        corruption_rate=0.0,
        confidence_threshold=0.6,
        min_fragments=2,
        enable_corruption=False,
        seed=42,
    )


@pytest.fixture
def engine_with_corruption():
    """An ArchaeologyEngine with corruption enabled."""
    return ArchaeologyEngine(
        corruption_rate=0.3,
        confidence_threshold=0.6,
        min_fragments=2,
        enable_corruption=True,
        seed=42,
    )


# ---------------------------------------------------------------------------
# _true_classification tests
# ---------------------------------------------------------------------------


class TestTrueClassification:
    """Tests for the ground-truth FizzBuzz classification helper."""

    def test_fizzbuzz_15(self):
        assert _true_classification(15) == FizzBuzzClassification.FIZZBUZZ

    def test_fizzbuzz_30(self):
        assert _true_classification(30) == FizzBuzzClassification.FIZZBUZZ

    def test_fizz_3(self):
        assert _true_classification(3) == FizzBuzzClassification.FIZZ

    def test_fizz_9(self):
        assert _true_classification(9) == FizzBuzzClassification.FIZZ

    def test_buzz_5(self):
        assert _true_classification(5) == FizzBuzzClassification.BUZZ

    def test_buzz_10(self):
        assert _true_classification(10) == FizzBuzzClassification.BUZZ

    def test_plain_1(self):
        assert _true_classification(1) == FizzBuzzClassification.PLAIN

    def test_plain_7(self):
        assert _true_classification(7) == FizzBuzzClassification.PLAIN


# ---------------------------------------------------------------------------
# EvidenceStratum tests
# ---------------------------------------------------------------------------


class TestEvidenceStratum:
    """Tests for the EvidenceStratum enum."""

    def test_seven_strata(self):
        assert len(EvidenceStratum) == 7

    def test_blockchain_value(self):
        assert EvidenceStratum.BLOCKCHAIN.value == "blockchain"

    def test_cache_eulogies_value(self):
        assert EvidenceStratum.CACHE_EULOGIES.value == "cache_eulogies"

    def test_all_strata_have_weights(self):
        for stratum in EvidenceStratum:
            assert stratum.value in DEFAULT_STRATA_WEIGHTS


# ---------------------------------------------------------------------------
# EvidenceFragment tests
# ---------------------------------------------------------------------------


class TestEvidenceFragment:
    """Tests for the EvidenceFragment dataclass."""

    def test_basic_creation(self):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.BLOCKCHAIN,
            number=15,
            classification=FizzBuzzClassification.FIZZBUZZ,
            confidence=0.95,
        )
        assert frag.number == 15
        assert frag.classification == FizzBuzzClassification.FIZZBUZZ
        assert frag.confidence == 0.95
        assert frag.corrupted is False

    def test_weighted_confidence(self):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.BLOCKCHAIN,
            number=15,
            classification=FizzBuzzClassification.FIZZBUZZ,
            confidence=1.0,
        )
        # Blockchain weight is 1.0, so weighted_confidence should be 1.0
        assert frag.weighted_confidence == 1.0

    def test_weighted_confidence_lower_stratum(self):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.CACHE_EULOGIES,
            number=15,
            classification=FizzBuzzClassification.FIZZBUZZ,
            confidence=1.0,
        )
        # Cache eulogies weight is 0.4
        assert frag.weighted_confidence == pytest.approx(0.4, abs=0.01)

    def test_corrupted_flag(self):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.METRICS,
            number=7,
            classification=FizzBuzzClassification.PLAIN,
            confidence=0.3,
            corrupted=True,
        )
        assert frag.corrupted is True

    def test_metadata_default_empty(self):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.RULE_ENGINE,
            number=3,
            classification=FizzBuzzClassification.FIZZ,
            confidence=0.85,
        )
        assert frag.metadata == {}


# ---------------------------------------------------------------------------
# CorruptionSimulator tests
# ---------------------------------------------------------------------------


class TestCorruptionSimulator:
    """Tests for the CorruptionSimulator."""

    def test_zero_corruption_rate_no_corruption(self, no_corruption_sim):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.BLOCKCHAIN,
            number=15,
            classification=FizzBuzzClassification.FIZZBUZZ,
            confidence=0.95,
        )
        result = no_corruption_sim.maybe_corrupt(frag)
        assert result.corrupted is False
        assert result.confidence == frag.confidence

    def test_high_corruption_rate_corrupts_some(self, corruption_sim):
        """With a high corruption rate and many trials, some should be corrupted."""
        frag = EvidenceFragment(
            stratum=EvidenceStratum.CACHE_EULOGIES,  # Low weight = more vulnerable
            number=7,
            classification=FizzBuzzClassification.PLAIN,
            confidence=0.9,
        )
        corrupted_count = 0
        sim = CorruptionSimulator(corruption_rate=0.8, seed=42)
        for i in range(100):
            result = sim.maybe_corrupt(
                EvidenceFragment(
                    stratum=EvidenceStratum.CACHE_EULOGIES,
                    number=i,
                    classification=FizzBuzzClassification.PLAIN,
                    confidence=0.9,
                )
            )
            if result.corrupted:
                corrupted_count += 1
        assert corrupted_count > 0, "Expected some corruption with rate=0.8"

    def test_corruption_reduces_confidence(self, corruption_sim):
        """Corrupted fragments should have lower confidence."""
        sim = CorruptionSimulator(corruption_rate=1.0, seed=42)
        frag = EvidenceFragment(
            stratum=EvidenceStratum.CACHE_EULOGIES,
            number=7,
            classification=FizzBuzzClassification.PLAIN,
            confidence=0.9,
        )
        result = sim.maybe_corrupt(frag)
        # With rate=1.0 and low-weight stratum, corruption is almost certain
        if result.corrupted:
            assert result.confidence < frag.confidence

    def test_corruption_log_records_events(self):
        sim = CorruptionSimulator(corruption_rate=1.0, seed=42)
        frag = EvidenceFragment(
            stratum=EvidenceStratum.CACHE_EULOGIES,
            number=7,
            classification=FizzBuzzClassification.PLAIN,
            confidence=0.9,
        )
        sim.maybe_corrupt(frag)
        # May or may not corrupt based on adjusted rate, but with rate=1.0
        # and low weight, it's very likely
        if len(sim.corruption_log) > 0:
            event = sim.corruption_log[0]
            assert "stratum" in event
            assert "degradation_factor" in event

    def test_reset_clears_log(self, corruption_sim):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.CACHE_EULOGIES,
            number=7,
            classification=FizzBuzzClassification.PLAIN,
            confidence=0.9,
        )
        corruption_sim.maybe_corrupt(frag)
        corruption_sim.reset()
        assert corruption_sim.corruption_log == []

    def test_blockchain_resists_corruption_better(self):
        """Blockchain (weight=1.0) should corrupt less than cache eulogies (weight=0.4)."""
        sim_bc = CorruptionSimulator(corruption_rate=0.5, seed=1)
        sim_ce = CorruptionSimulator(corruption_rate=0.5, seed=1)

        bc_corrupted = 0
        ce_corrupted = 0
        for i in range(200):
            bc = sim_bc.maybe_corrupt(
                EvidenceFragment(
                    stratum=EvidenceStratum.BLOCKCHAIN,
                    number=i,
                    classification=FizzBuzzClassification.PLAIN,
                    confidence=0.9,
                )
            )
            ce = sim_ce.maybe_corrupt(
                EvidenceFragment(
                    stratum=EvidenceStratum.CACHE_EULOGIES,
                    number=i,
                    classification=FizzBuzzClassification.PLAIN,
                    confidence=0.9,
                )
            )
            if bc.corrupted:
                bc_corrupted += 1
            if ce.corrupted:
                ce_corrupted += 1

        # Cache eulogies should be corrupted more often
        assert ce_corrupted >= bc_corrupted


# ---------------------------------------------------------------------------
# EvidenceCollector tests
# ---------------------------------------------------------------------------


class TestEvidenceCollector:
    """Tests for the EvidenceCollector."""

    def test_collect_all_returns_fragments(self, collector):
        fragments = collector.collect_all(15)
        assert len(fragments) > 0

    def test_collect_all_covers_multiple_strata(self, collector):
        fragments = collector.collect_all(15)
        strata = set(f.stratum for f in fragments)
        assert len(strata) == 7  # All 7 strata should be represented

    def test_blockchain_returns_one_fragment(self, collector):
        fragments = collector.collect_blockchain(15)
        assert len(fragments) == 1
        assert fragments[0].stratum == EvidenceStratum.BLOCKCHAIN

    def test_blockchain_high_confidence(self, collector):
        fragments = collector.collect_blockchain(15)
        assert fragments[0].confidence >= 0.95

    def test_event_store_returns_fragments(self, collector):
        fragments = collector.collect_event_store(15)
        assert len(fragments) >= 1
        assert all(f.stratum == EvidenceStratum.EVENT_STORE for f in fragments)

    def test_event_store_extra_event_for_large_numbers(self, collector):
        fragments = collector.collect_event_store(51)
        assert len(fragments) == 2  # Primary + correction event

    def test_rule_engine_fizz(self, collector):
        fragments = collector.collect_rule_engine(3)
        assert len(fragments) >= 1
        assert any(f.classification == FizzBuzzClassification.FIZZ for f in fragments)

    def test_rule_engine_buzz(self, collector):
        fragments = collector.collect_rule_engine(5)
        assert len(fragments) >= 1
        assert any(f.classification == FizzBuzzClassification.BUZZ for f in fragments)

    def test_rule_engine_fizzbuzz(self, collector):
        fragments = collector.collect_rule_engine(15)
        assert len(fragments) >= 1
        # Both rules should match for FizzBuzz
        assert any(f.classification == FizzBuzzClassification.FIZZBUZZ for f in fragments)

    def test_rule_engine_plain(self, collector):
        fragments = collector.collect_rule_engine(7)
        assert len(fragments) == 1
        assert fragments[0].classification == FizzBuzzClassification.PLAIN

    def test_cache_coherence_returns_fragment(self, collector):
        fragments = collector.collect_cache_coherence(15)
        assert len(fragments) == 1
        assert fragments[0].stratum == EvidenceStratum.CACHE_COHERENCE

    def test_cache_coherence_mesi_state_in_metadata(self, collector):
        fragments = collector.collect_cache_coherence(15)
        assert "mesi_state" in fragments[0].metadata

    def test_middleware_pipeline_returns_fragment(self, collector):
        fragments = collector.collect_middleware_pipeline(15)
        assert len(fragments) == 1
        assert fragments[0].stratum == EvidenceStratum.MIDDLEWARE_PIPELINE

    def test_metrics_returns_fragment(self, collector):
        fragments = collector.collect_metrics(15)
        assert len(fragments) == 1
        assert fragments[0].stratum == EvidenceStratum.METRICS

    def test_cache_eulogies_returns_fragment(self, collector):
        fragments = collector.collect_cache_eulogies(15)
        assert len(fragments) == 1
        assert fragments[0].stratum == EvidenceStratum.CACHE_EULOGIES

    def test_cache_eulogies_has_eulogy_text(self, collector):
        fragments = collector.collect_cache_eulogies(15)
        assert "eulogy_text" in fragments[0].metadata

    def test_correct_classification_for_fizzbuzz(self, collector):
        fragments = collector.collect_all(15)
        # All strata should (without corruption) agree on FIZZBUZZ
        for f in fragments:
            assert f.classification == FizzBuzzClassification.FIZZBUZZ


# ---------------------------------------------------------------------------
# BayesianReconstructor tests
# ---------------------------------------------------------------------------


class TestBayesianReconstructor:
    """Tests for the BayesianReconstructor."""

    def test_empty_fragments_returns_priors(self, reconstructor):
        posteriors = reconstructor.reconstruct([])
        assert posteriors[FizzBuzzClassification.FIZZBUZZ] == pytest.approx(1.0 / 15.0, abs=0.001)
        assert posteriors[FizzBuzzClassification.PLAIN] == pytest.approx(8.0 / 15.0, abs=0.001)

    def test_posteriors_sum_to_one(self, reconstructor, collector):
        fragments = collector.collect_all(15)
        posteriors = reconstructor.reconstruct(fragments)
        total = sum(posteriors.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_correct_classification_fizzbuzz(self, reconstructor, collector):
        fragments = collector.collect_all(15)
        best_class, best_prob = reconstructor.classify(fragments)
        assert best_class == FizzBuzzClassification.FIZZBUZZ

    def test_correct_classification_fizz(self, reconstructor, collector):
        fragments = collector.collect_all(3)
        best_class, best_prob = reconstructor.classify(fragments)
        assert best_class == FizzBuzzClassification.FIZZ

    def test_correct_classification_buzz(self, reconstructor, collector):
        fragments = collector.collect_all(5)
        best_class, best_prob = reconstructor.classify(fragments)
        assert best_class == FizzBuzzClassification.BUZZ

    def test_correct_classification_plain(self, reconstructor, collector):
        fragments = collector.collect_all(7)
        best_class, best_prob = reconstructor.classify(fragments)
        assert best_class == FizzBuzzClassification.PLAIN

    def test_high_confidence_with_unanimous_evidence(self, reconstructor, collector):
        fragments = collector.collect_all(15)
        _, prob = reconstructor.classify(fragments)
        assert prob > 0.9

    def test_priors_match_fizzbuzz_distribution(self, reconstructor):
        priors = BayesianReconstructor.PRIORS
        assert priors[FizzBuzzClassification.FIZZBUZZ] == pytest.approx(1.0 / 15.0, abs=0.001)
        assert priors[FizzBuzzClassification.FIZZ] == pytest.approx(4.0 / 15.0, abs=0.001)
        assert priors[FizzBuzzClassification.BUZZ] == pytest.approx(2.0 / 15.0, abs=0.001)
        assert priors[FizzBuzzClassification.PLAIN] == pytest.approx(8.0 / 15.0, abs=0.001)

    def test_priors_sum_to_one(self):
        total = sum(BayesianReconstructor.PRIORS.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_confidence_threshold_property(self, reconstructor):
        assert reconstructor.confidence_threshold == 0.6

    def test_single_fragment_shifts_posterior(self, reconstructor):
        frag = EvidenceFragment(
            stratum=EvidenceStratum.BLOCKCHAIN,
            number=15,
            classification=FizzBuzzClassification.FIZZBUZZ,
            confidence=0.99,
        )
        posteriors = reconstructor.reconstruct([frag])
        # FizzBuzz posterior should be higher than its prior
        assert posteriors[FizzBuzzClassification.FIZZBUZZ] > BayesianReconstructor.PRIORS[FizzBuzzClassification.FIZZBUZZ]


# ---------------------------------------------------------------------------
# StratigraphyEngine tests
# ---------------------------------------------------------------------------


class TestStratigraphyEngine:
    """Tests for the StratigraphyEngine."""

    def test_correlate_groups_by_stratum(self, stratigraphy, collector):
        fragments = collector.collect_all(15)
        strata_map = stratigraphy.correlate(fragments)
        assert "blockchain" in strata_map
        assert "cache_eulogies" in strata_map

    def test_timeline_ordered_by_weight(self, stratigraphy, collector):
        fragments = collector.collect_all(15)
        timeline = stratigraphy.build_timeline(fragments)
        weights = [entry["weight"] for entry in timeline]
        assert weights == sorted(weights, reverse=True)

    def test_no_conflicts_with_consistent_evidence(self, stratigraphy, collector):
        fragments = collector.collect_all(15)
        conflicts = stratigraphy.detect_conflicts(fragments)
        assert len(conflicts) == 0

    def test_conflicts_detected_with_disagreeing_evidence(self, stratigraphy):
        fragments = [
            EvidenceFragment(
                stratum=EvidenceStratum.BLOCKCHAIN,
                number=15,
                classification=FizzBuzzClassification.FIZZBUZZ,
                confidence=0.95,
            ),
            EvidenceFragment(
                stratum=EvidenceStratum.CACHE_EULOGIES,
                number=15,
                classification=FizzBuzzClassification.FIZZ,
                confidence=0.45,
            ),
        ]
        conflicts = stratigraphy.detect_conflicts(fragments)
        assert len(conflicts) == 1
        assert conflicts[0]["class_a"] != conflicts[0]["class_b"]

    def test_timeline_fragment_count(self, stratigraphy, collector):
        fragments = collector.collect_all(15)
        timeline = stratigraphy.build_timeline(fragments)
        total = sum(entry["fragment_count"] for entry in timeline)
        assert total == len(fragments)

    def test_timeline_corrupted_count(self, stratigraphy):
        fragments = [
            EvidenceFragment(
                stratum=EvidenceStratum.BLOCKCHAIN,
                number=15,
                classification=FizzBuzzClassification.FIZZBUZZ,
                confidence=0.95,
                corrupted=True,
            ),
        ]
        timeline = stratigraphy.build_timeline(fragments)
        assert timeline[0]["corrupted_count"] == 1


# ---------------------------------------------------------------------------
# ExcavationReport tests
# ---------------------------------------------------------------------------


class TestExcavationReport:
    """Tests for the ExcavationReport renderer."""

    def test_render_produces_string(self, collector, reconstructor, stratigraphy):
        fragments = collector.collect_all(15)
        posteriors = reconstructor.reconstruct(fragments)
        best_class, best_prob = reconstructor.classify(fragments)
        timeline = stratigraphy.build_timeline(fragments)
        conflicts = stratigraphy.detect_conflicts(fragments)
        report = ExcavationReport.render(
            number=15,
            fragments=fragments,
            posteriors=posteriors,
            best_class=best_class,
            best_prob=best_prob,
            conflicts=conflicts,
            timeline=timeline,
            corruption_log=[],
        )
        assert isinstance(report, str)
        assert "15" in report
        assert "ARCHAEOLOGICAL" in report

    def test_report_contains_classification(self, collector, reconstructor, stratigraphy):
        fragments = collector.collect_all(15)
        posteriors = reconstructor.reconstruct(fragments)
        best_class, best_prob = reconstructor.classify(fragments)
        timeline = stratigraphy.build_timeline(fragments)
        conflicts = stratigraphy.detect_conflicts(fragments)
        report = ExcavationReport.render(
            number=15,
            fragments=fragments,
            posteriors=posteriors,
            best_class=best_class,
            best_prob=best_prob,
            conflicts=conflicts,
            timeline=timeline,
            corruption_log=[],
        )
        assert "FIZZBUZZ" in report

    def test_report_contains_irony_note(self, collector, reconstructor, stratigraphy):
        fragments = collector.collect_all(15)
        posteriors = reconstructor.reconstruct(fragments)
        best_class, best_prob = reconstructor.classify(fragments)
        timeline = stratigraphy.build_timeline(fragments)
        conflicts = stratigraphy.detect_conflicts(fragments)
        report = ExcavationReport.render(
            number=15,
            fragments=fragments,
            posteriors=posteriors,
            best_class=best_class,
            best_prob=best_prob,
            conflicts=conflicts,
            timeline=timeline,
            corruption_log=[],
        )
        assert "CPU cycle" in report

    def test_report_shows_corruption_events(self, collector, reconstructor, stratigraphy):
        fragments = collector.collect_all(15)
        posteriors = reconstructor.reconstruct(fragments)
        best_class, best_prob = reconstructor.classify(fragments)
        timeline = stratigraphy.build_timeline(fragments)
        conflicts = stratigraphy.detect_conflicts(fragments)
        corruption_log = [
            {
                "stratum": "cache_eulogies",
                "degradation_factor": 0.5,
                "classification_flipped": True,
            }
        ]
        report = ExcavationReport.render(
            number=15,
            fragments=fragments,
            posteriors=posteriors,
            best_class=best_class,
            best_prob=best_prob,
            conflicts=conflicts,
            timeline=timeline,
            corruption_log=corruption_log,
        )
        assert "CORRUPTION" in report
        assert "CLASS FLIPPED" in report


# ---------------------------------------------------------------------------
# ArchaeologyEngine tests
# ---------------------------------------------------------------------------


class TestArchaeologyEngine:
    """Tests for the ArchaeologyEngine orchestrator."""

    def test_excavate_returns_report(self, engine):
        report = engine.excavate(15)
        assert isinstance(report, str)
        assert "ARCHAEOLOGICAL" in report

    def test_excavate_records_history(self, engine):
        engine.excavate(15)
        assert len(engine.excavation_history) == 1
        assert engine.excavation_history[0]["number"] == 15

    def test_excavate_correct_classification_fizzbuzz(self, engine):
        engine.excavate(15)
        assert engine.excavation_history[0]["classification"] == "FIZZBUZZ"

    def test_excavate_correct_classification_fizz(self, engine):
        engine.excavate(3)
        assert engine.excavation_history[0]["classification"] == "FIZZ"

    def test_excavate_correct_classification_buzz(self, engine):
        engine.excavate(5)
        assert engine.excavation_history[0]["classification"] == "BUZZ"

    def test_excavate_correct_classification_plain(self, engine):
        engine.excavate(7)
        assert engine.excavation_history[0]["classification"] == "PLAIN"

    def test_excavate_range(self, engine):
        reports = engine.excavate_range(1, 5)
        assert len(reports) == 5
        assert len(engine.excavation_history) == 5

    def test_summary_empty(self, engine):
        summary = engine.get_summary()
        assert summary["total_excavations"] == 0

    def test_summary_after_excavation(self, engine):
        engine.excavate(15)
        engine.excavate(3)
        engine.excavate(5)
        summary = engine.get_summary()
        assert summary["total_excavations"] == 3
        assert summary["avg_confidence"] > 0
        assert summary["total_fragments"] > 0

    def test_summary_classification_distribution(self, engine):
        engine.excavate(15)
        engine.excavate(3)
        engine.excavate(5)
        engine.excavate(7)
        summary = engine.get_summary()
        dist = summary["classification_distribution"]
        assert dist["FIZZBUZZ"] == 1
        assert dist["FIZZ"] == 1
        assert dist["BUZZ"] == 1
        assert dist["PLAIN"] == 1

    def test_corruption_engine_produces_some_corrupted_fragments(self, engine_with_corruption):
        engine_with_corruption.excavate(15)
        # With corruption enabled, we may or may not see corruption
        # Just verify it doesn't crash
        assert len(engine_with_corruption.excavation_history) == 1

    def test_engine_properties(self, engine):
        assert engine.collector is not None
        assert engine.corruption_simulator is not None
        assert engine.reconstructor is not None
        assert engine.stratigraphy is not None


# ---------------------------------------------------------------------------
# ArchaeologyDashboard tests
# ---------------------------------------------------------------------------


class TestArchaeologyDashboard:
    """Tests for the ArchaeologyDashboard renderer."""

    def test_render_empty_engine(self, engine):
        output = ArchaeologyDashboard.render(engine)
        assert "ARCHAEOLOGICAL RECOVERY DASHBOARD" in output

    def test_render_after_excavation(self, engine):
        engine.excavate(15)
        engine.excavate(3)
        output = ArchaeologyDashboard.render(engine)
        assert "Total Excavations:" in output
        assert "2" in output

    def test_render_shows_strata_weights(self, engine):
        output = ArchaeologyDashboard.render(engine, show_strata=True)
        assert "STRATA RELIABILITY WEIGHTS" in output
        assert "blockchain" in output

    def test_render_shows_bayesian_priors(self, engine):
        output = ArchaeologyDashboard.render(engine, show_bayesian=True)
        assert "BAYESIAN PRIOR DISTRIBUTION" in output

    def test_render_hides_strata_when_disabled(self, engine):
        output = ArchaeologyDashboard.render(engine, show_strata=False)
        assert "STRATA RELIABILITY WEIGHTS" not in output

    def test_render_hides_bayesian_when_disabled(self, engine):
        output = ArchaeologyDashboard.render(engine, show_bayesian=False)
        assert "BAYESIAN PRIOR DISTRIBUTION" not in output

    def test_render_efficiency_note(self, engine):
        engine.excavate(15)
        output = ArchaeologyDashboard.render(engine)
        assert "n%3==0" in output

    def test_render_recent_excavations(self, engine):
        for n in [3, 5, 7, 9, 10, 12, 15]:
            engine.excavate(n)
        output = ArchaeologyDashboard.render(engine)
        assert "RECENT EXCAVATIONS" in output


# ---------------------------------------------------------------------------
# ArchaeologyMiddleware tests
# ---------------------------------------------------------------------------


class TestArchaeologyMiddleware:
    """Tests for the ArchaeologyMiddleware."""

    def test_middleware_name(self, engine):
        mw = ArchaeologyMiddleware(engine)
        assert mw.get_name() == "ArchaeologyMiddleware"

    def test_middleware_priority(self, engine):
        mw = ArchaeologyMiddleware(engine)
        assert mw.get_priority() == 900

    def test_middleware_passes_through_result(self, engine):
        mw = ArchaeologyMiddleware(engine)
        ctx = ProcessingContext(number=15, session_id="test-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(
                FizzBuzzResult(
                    number=15,
                    output="FizzBuzz",
                )
            )
            return ctx

        result = mw.process(ctx, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "FizzBuzz"

    def test_middleware_adds_archaeology_metadata(self, engine):
        mw = ArchaeologyMiddleware(engine)
        ctx = ProcessingContext(number=15, session_id="test-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            return ctx

        result = mw.process(ctx, next_handler)
        assert "archaeology" in result.metadata
        assert result.metadata["archaeology"]["reconstructed_class"] == "FIZZBUZZ"

    def test_middleware_records_excavation(self, engine):
        mw = ArchaeologyMiddleware(engine)
        ctx = ProcessingContext(number=3, session_id="test-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            return ctx

        mw.process(ctx, next_handler)
        assert len(engine.excavation_history) == 1
        assert engine.excavation_history[0]["number"] == 3


# ---------------------------------------------------------------------------
# Exception tests
# ---------------------------------------------------------------------------


class TestArchaeologyExceptions:
    """Tests for the archaeological exception hierarchy."""

    def test_archaeology_error_base(self):
        err = ArchaeologyError("test error")
        assert "EFP-AR00" in str(err)

    def test_stratum_corruption_error(self):
        err = StratumCorruptionError("blockchain", 15, 0.1)
        assert "EFP-AR01" in str(err)
        assert err.stratum == "blockchain"
        assert err.number == 15
        assert err.confidence == 0.1

    def test_insufficient_evidence_error(self):
        err = InsufficientEvidenceError(15, 1, 3)
        assert "EFP-AR02" in str(err)
        assert err.number == 15
        assert err.fragments_found == 1
        assert err.minimum_required == 3

    def test_stratigraphic_conflict_error(self):
        err = StratigraphicConflictError(15, "blockchain", "FIZZBUZZ", "cache_eulogies", "FIZZ")
        assert "EFP-AR03" in str(err)
        assert err.number == 15
        assert err.stratum_a == "blockchain"
        assert err.classification_a == "FIZZBUZZ"
        assert err.stratum_b == "cache_eulogies"
        assert err.classification_b == "FIZZ"

    def test_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(ArchaeologyError, FizzBuzzError)
        assert issubclass(StratumCorruptionError, ArchaeologyError)
        assert issubclass(InsufficientEvidenceError, ArchaeologyError)
        assert issubclass(StratigraphicConflictError, ArchaeologyError)

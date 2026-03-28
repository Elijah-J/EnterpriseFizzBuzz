"""
Tests for FizzBloom -- Probabilistic Data Structures subsystem.

Validates space-efficient membership testing via Bloom filters, cardinality
estimation via HyperLogLog, and frequency counting via Count-Min Sketch.
Probabilistic data structures are critical infrastructure for any enterprise
platform operating at scale, enabling sub-linear memory usage for set
membership queries, distinct-count analytics, and frequency estimation
across the FizzBuzz processing pipeline.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzbloom import (
    FIZZBLOOM_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzBloomConfig,
    BloomFilter,
    HyperLogLog,
    CountMinSketch,
    ProbabilisticRegistry,
    FizzBloomDashboard,
    FizzBloomMiddleware,
    create_fizzbloom_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzbloom import (
    FizzBloomError,
    FizzBloomNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def bloom():
    return BloomFilter(capacity=1000, false_positive_rate=0.01)


@pytest.fixture
def hll():
    return HyperLogLog(precision=14)


@pytest.fixture
def cms():
    return CountMinSketch(width=1000, depth=5)


@pytest.fixture
def registry():
    return ProbabilisticRegistry()


# ============================================================================
# Constants
# ============================================================================

class TestConstants:
    """Verify module-level constants required for subsystem registration."""

    def test_version_string(self):
        assert FIZZBLOOM_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 214


# ============================================================================
# FizzBloomConfig
# ============================================================================

class TestFizzBloomConfig:
    """Validate the FizzBloom configuration data structure."""

    def test_config_dashboard_width(self):
        config = FizzBloomConfig(dashboard_width=120)
        assert config.dashboard_width == 120


# ============================================================================
# BloomFilter -- insertion and membership
# ============================================================================

class TestBloomFilterBasic:
    """Validate core Bloom filter operations for membership testing."""

    def test_add_single_item(self, bloom):
        """Adding an item must not raise and must be reflected in count."""
        bloom.add("fizz")
        assert bloom.count == 1

    def test_contains_returns_true_for_added_item(self, bloom):
        """A Bloom filter must report membership for every item that was added."""
        bloom.add("buzz")
        assert bloom.contains("buzz") is True

    def test_contains_returns_false_for_absent_item(self, bloom):
        """An empty Bloom filter must not report membership for arbitrary items."""
        assert bloom.contains("nonexistent") is False

    def test_no_false_negatives(self, bloom):
        """The fundamental Bloom filter invariant: zero false negatives.

        Every item that has been inserted must be reported as present.
        False positives are acceptable; false negatives are not.
        """
        items = [f"item_{i}" for i in range(200)]
        for item in items:
            bloom.add(item)
        for item in items:
            assert bloom.contains(item) is True, (
                f"False negative detected for '{item}' -- "
                "this violates the Bloom filter contract"
            )

    def test_count_tracks_insertions(self, bloom):
        """The count property must accurately track the number of add operations."""
        for i in range(50):
            bloom.add(f"entry_{i}")
        assert bloom.count == 50

    def test_false_positive_rate_property(self, bloom):
        """The configured false positive rate must be retrievable."""
        assert bloom.false_positive_rate == pytest.approx(0.01)

    def test_custom_capacity_and_fpr(self):
        """Custom capacity and false positive rate must be honored."""
        bf = BloomFilter(capacity=500, false_positive_rate=0.05)
        assert bf.false_positive_rate == pytest.approx(0.05)

    def test_empty_bloom_count_is_zero(self, bloom):
        """A freshly constructed Bloom filter must have a count of zero."""
        assert bloom.count == 0

    def test_add_multiple_distinct_items(self, bloom):
        """Adding multiple distinct items must increment count correctly."""
        bloom.add("alpha")
        bloom.add("beta")
        bloom.add("gamma")
        assert bloom.count == 3


# ============================================================================
# HyperLogLog -- cardinality estimation
# ============================================================================

class TestHyperLogLogBasic:
    """Validate HyperLogLog cardinality estimation accuracy."""

    def test_add_single_item(self, hll):
        """Adding an item must not raise."""
        hll.add("fizz")
        assert hll.estimate() >= 1.0

    def test_estimate_empty_is_zero_or_near_zero(self, hll):
        """An empty HyperLogLog must estimate cardinality at or near zero."""
        assert hll.estimate() < 1.0

    def test_estimate_accuracy_within_twenty_percent(self):
        """HyperLogLog with precision=14 must estimate within 20% of true cardinality.

        This is a standard accuracy bound for HLL with 2^14 registers.
        The relative error for precision p is approximately 1.04 / sqrt(2^p).
        """
        hll = HyperLogLog(precision=14)
        true_cardinality = 5000
        for i in range(true_cardinality):
            hll.add(f"item_{i}")
        estimate = hll.estimate()
        lower = true_cardinality * 0.80
        upper = true_cardinality * 1.20
        assert lower <= estimate <= upper, (
            f"HLL estimate {estimate} is outside 20% tolerance of "
            f"true cardinality {true_cardinality}"
        )

    def test_estimate_small_cardinality(self):
        """HyperLogLog must produce reasonable estimates for small cardinalities."""
        hll = HyperLogLog(precision=14)
        for i in range(10):
            hll.add(f"small_{i}")
        estimate = hll.estimate()
        assert 5 <= estimate <= 20, (
            f"HLL estimate {estimate} is unreasonable for 10 distinct items"
        )

    def test_duplicate_items_do_not_inflate_estimate(self):
        """Inserting the same item repeatedly must not significantly inflate the estimate."""
        hll = HyperLogLog(precision=14)
        for _ in range(1000):
            hll.add("duplicate")
        estimate = hll.estimate()
        assert estimate < 5.0, (
            f"HLL estimate {estimate} should be ~1 for a single distinct item"
        )


# ============================================================================
# HyperLogLog -- merge
# ============================================================================

class TestHyperLogLogMerge:
    """Validate HyperLogLog merge operation for distributed cardinality estimation."""

    def test_merge_returns_new_hll(self):
        """Merging two HLLs must return a new HyperLogLog instance."""
        hll_a = HyperLogLog(precision=14)
        hll_b = HyperLogLog(precision=14)
        hll_a.add("a")
        hll_b.add("b")
        merged = hll_a.merge(hll_b)
        assert isinstance(merged, HyperLogLog)

    def test_merge_combines_cardinalities(self):
        """The merged HLL must reflect the union cardinality of both inputs."""
        hll_a = HyperLogLog(precision=14)
        hll_b = HyperLogLog(precision=14)
        for i in range(500):
            hll_a.add(f"a_{i}")
        for i in range(500):
            hll_b.add(f"b_{i}")
        merged = hll_a.merge(hll_b)
        estimate = merged.estimate()
        assert 800 <= estimate <= 1200, (
            f"Merged HLL estimate {estimate} should be ~1000 for 1000 distinct items"
        )

    def test_merge_with_overlapping_items(self):
        """Merging HLLs with overlapping items must not double-count."""
        hll_a = HyperLogLog(precision=14)
        hll_b = HyperLogLog(precision=14)
        for i in range(500):
            hll_a.add(f"shared_{i}")
            hll_b.add(f"shared_{i}")
        merged = hll_a.merge(hll_b)
        estimate = merged.estimate()
        assert 400 <= estimate <= 600, (
            f"Merged HLL estimate {estimate} should be ~500 for fully overlapping sets"
        )


# ============================================================================
# CountMinSketch -- frequency estimation
# ============================================================================

class TestCountMinSketchBasic:
    """Validate Count-Min Sketch frequency estimation correctness."""

    def test_add_and_estimate(self, cms):
        """Adding an item and estimating its frequency must return at least 1."""
        cms.add("fizz")
        assert cms.estimate("fizz") >= 1

    def test_estimate_absent_item_is_zero(self, cms):
        """An item never added must have an estimated frequency of zero."""
        assert cms.estimate("ghost") == 0

    def test_never_underestimates(self):
        """The Count-Min Sketch invariant: estimated frequency is never less than true frequency.

        Over-estimation is acceptable due to hash collisions; under-estimation
        violates the data structure's mathematical guarantee.
        """
        cms = CountMinSketch(width=1000, depth=5)
        items = {f"item_{i}": (i + 1) * 3 for i in range(50)}
        for item, count in items.items():
            cms.add(item, count)
        for item, true_count in items.items():
            estimated = cms.estimate(item)
            assert estimated >= true_count, (
                f"CMS underestimated '{item}': estimated={estimated}, "
                f"true={true_count} -- this violates the CMS contract"
            )

    def test_add_with_custom_count(self, cms):
        """Adding an item with a custom count must increase the estimate by at least that amount."""
        cms.add("bulk", count=100)
        assert cms.estimate("bulk") >= 100

    def test_multiple_adds_accumulate(self, cms):
        """Multiple add operations for the same item must accumulate correctly."""
        cms.add("repeated", count=10)
        cms.add("repeated", count=20)
        assert cms.estimate("repeated") >= 30


# ============================================================================
# ProbabilisticRegistry -- CRUD
# ============================================================================

class TestRegistryCRUD:
    """Validate lifecycle operations on the ProbabilisticRegistry."""

    def test_create_bloom_filter(self, registry):
        bf = registry.create_bloom_filter("membership_test")
        assert isinstance(bf, BloomFilter)

    def test_create_hyperloglog(self, registry):
        hll = registry.create_hyperloglog("cardinality_counter")
        assert isinstance(hll, HyperLogLog)

    def test_create_count_min_sketch(self, registry):
        cms = registry.create_count_min_sketch("freq_tracker")
        assert isinstance(cms, CountMinSketch)

    def test_get_returns_created_structure(self, registry):
        registry.create_bloom_filter("my_bloom")
        retrieved = registry.get("my_bloom")
        assert isinstance(retrieved, BloomFilter)

    def test_get_not_found_raises(self, registry):
        with pytest.raises(FizzBloomNotFoundError):
            registry.get("nonexistent")

    def test_list_structures_returns_all(self, registry):
        registry.create_bloom_filter("bf1")
        registry.create_hyperloglog("hll1")
        registry.create_count_min_sketch("cms1")
        structures = registry.list_structures()
        assert len(structures) == 3

    def test_list_structures_contains_name_and_type(self, registry):
        """Each entry in the structure listing must include name and type metadata."""
        registry.create_bloom_filter("bloom_alpha")
        listing = registry.list_structures()
        assert len(listing) == 1
        entry = listing[0]
        assert "name" in entry
        assert "type" in entry
        assert entry["name"] == "bloom_alpha"


# ============================================================================
# Exceptions
# ============================================================================

class TestExceptions:
    """Validate exception hierarchy for the FizzBloom subsystem."""

    def test_not_found_is_subclass_of_base(self):
        assert issubclass(FizzBloomNotFoundError, FizzBloomError)

    def test_base_is_subclass_of_exception(self):
        assert issubclass(FizzBloomError, Exception)


# ============================================================================
# FizzBloomDashboard
# ============================================================================

class TestDashboard:
    """Validate dashboard rendering for operational visibility into probabilistic structures."""

    def test_render_returns_string(self):
        registry = ProbabilisticRegistry()
        dashboard = FizzBloomDashboard(registry)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_structure_name(self):
        registry = ProbabilisticRegistry()
        registry.create_bloom_filter("visible_bloom")
        dashboard = FizzBloomDashboard(registry)
        output = dashboard.render()
        assert "visible_bloom" in output


# ============================================================================
# FizzBloomMiddleware
# ============================================================================

class TestMiddleware:
    """Validate FizzBloom middleware integration with the processing pipeline."""

    def test_get_name(self):
        middleware = FizzBloomMiddleware()
        assert middleware.get_name() == "fizzbloom"

    def test_get_priority(self):
        middleware = FizzBloomMiddleware()
        assert middleware.get_priority() == 214

    def test_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        middleware = FizzBloomMiddleware()
        ctx = ProcessingContext(number=42, session_id="test")
        called = {"value": False}

        def fake_next(c):
            called["value"] = True
            return c

        middleware.process(ctx, fake_next)
        assert called["value"] is True, "Middleware must call the next handler"


# ============================================================================
# Factory function
# ============================================================================

class TestCreateSubsystem:
    """Validate the factory function that wires the FizzBloom subsystem."""

    def test_returns_tuple_of_three(self):
        result = create_fizzbloom_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        registry, dashboard, middleware = create_fizzbloom_subsystem()
        assert isinstance(registry, ProbabilisticRegistry)
        assert isinstance(dashboard, FizzBloomDashboard)
        assert isinstance(middleware, FizzBloomMiddleware)

    def test_subsystem_components_are_wired(self):
        """The registry and dashboard must be connected for operational visibility."""
        registry, dashboard, middleware = create_fizzbloom_subsystem()
        registry.create_bloom_filter("wired_test")
        output = dashboard.render()
        assert isinstance(output, str)

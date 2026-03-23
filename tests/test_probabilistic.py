"""
Enterprise FizzBuzz Platform - Probabilistic Data Structures Tests

Comprehensive test coverage for FizzBloom, the probabilistic analytics
subsystem that provides approximate membership testing (Bloom filter),
frequency estimation (Count-Min Sketch), cardinality estimation
(HyperLogLog), and streaming quantile approximation (T-Digest) for
FizzBuzz evaluation streams.

Tests verify mathematical correctness of all four data structures,
the middleware integration, and the ASCII dashboard renderer.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    BloomFilterCapacityError,
    CountMinSketchOverflowError,
    HyperLogLogPrecisionError,
    ProbabilisticError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.probabilistic import (
    BloomFilter,
    CountMinSketch,
    HyperLogLog,
    ProbabilisticDashboard,
    ProbabilisticMiddleware,
    TDigest,
    _Centroid,
    _hash_with_seed,
    _md5_hash_with_seed,
    create_probabilistic_subsystem,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def bloom() -> BloomFilter:
    """A Bloom filter sized for 100 elements with 1% FPR."""
    return BloomFilter(expected_elements=100, false_positive_rate=0.01)


@pytest.fixture
def cms() -> CountMinSketch:
    """A Count-Min Sketch with default parameters."""
    return CountMinSketch(width=1024, depth=5)


@pytest.fixture
def hll() -> HyperLogLog:
    """A HyperLogLog estimator with precision 10."""
    return HyperLogLog(precision=10)


@pytest.fixture
def tdigest() -> TDigest:
    """A T-Digest with default compression."""
    return TDigest(compression=100)


@pytest.fixture
def middleware(bloom, cms, hll, tdigest) -> ProbabilisticMiddleware:
    """A fully wired ProbabilisticMiddleware with all four structures."""
    return ProbabilisticMiddleware(
        bloom=bloom,
        cms=cms,
        hll=hll,
        tdigest=tdigest,
    )


def _make_context(number: int, label: str) -> ProcessingContext:
    """Create a minimal ProcessingContext for testing."""
    ctx = ProcessingContext(number=number, session_id="test-session")
    ctx.results.append(FizzBuzzResult(number=number, output=label))
    return ctx


# ============================================================
# Hash Utility Tests
# ============================================================

class TestHashUtilities:
    """Tests for the hash utility functions."""

    def test_hash_with_seed_deterministic(self):
        """Same input and seed produce the same hash."""
        h1 = _hash_with_seed("Fizz", 42)
        h2 = _hash_with_seed("Fizz", 42)
        assert h1 == h2

    def test_hash_with_seed_different_seeds(self):
        """Different seeds produce different hashes."""
        h1 = _hash_with_seed("Fizz", 0)
        h2 = _hash_with_seed("Fizz", 1)
        assert h1 != h2

    def test_hash_with_seed_different_items(self):
        """Different items produce different hashes."""
        h1 = _hash_with_seed("Fizz", 42)
        h2 = _hash_with_seed("Buzz", 42)
        assert h1 != h2

    def test_md5_hash_with_seed_deterministic(self):
        """MD5 hash is deterministic."""
        h1 = _md5_hash_with_seed("FizzBuzz", 7)
        h2 = _md5_hash_with_seed("FizzBuzz", 7)
        assert h1 == h2

    def test_md5_hash_differs_from_sha256(self):
        """MD5 and SHA-256 hash families are independent."""
        h_sha = _hash_with_seed("Fizz", 0)
        h_md5 = _md5_hash_with_seed("Fizz", 0)
        assert h_sha != h_md5

    def test_hash_returns_positive_integer(self):
        """Hash values are non-negative 64-bit integers."""
        h = _hash_with_seed("test", 0)
        assert isinstance(h, int)
        assert h >= 0


# ============================================================
# Bloom Filter Tests
# ============================================================

class TestBloomFilter:
    """Tests for the Bloom filter implementation."""

    def test_empty_filter_contains_nothing(self, bloom):
        """An empty Bloom filter reports no membership."""
        assert not bloom.might_contain("Fizz")
        assert not bloom.might_contain("Buzz")
        assert not bloom.might_contain("FizzBuzz")

    def test_add_and_query(self, bloom):
        """Added elements are always found (no false negatives)."""
        bloom.add("Fizz")
        assert bloom.might_contain("Fizz")

    def test_no_false_negatives(self, bloom):
        """Every inserted element must be found."""
        labels = ["Fizz", "Buzz", "FizzBuzz", "1", "2", "4", "7"]
        for label in labels:
            bloom.add(label)
        for label in labels:
            assert bloom.might_contain(label), f"False negative for {label}"

    def test_element_count(self, bloom):
        """Element count tracks insertions."""
        assert bloom.element_count == 0
        bloom.add("Fizz")
        assert bloom.element_count == 1
        bloom.add("Buzz")
        assert bloom.element_count == 2

    def test_optimal_parameters(self):
        """Optimal m and k are computed correctly."""
        bf = BloomFilter(expected_elements=1000, false_positive_rate=0.01)
        # m = -n * ln(p) / (ln(2))^2
        expected_m = int(math.ceil(
            -1000 * math.log(0.01) / (math.log(2) ** 2)
        ))
        assert bf.bit_count == expected_m
        # k = (m/n) * ln(2)
        expected_k = int(round((expected_m / 1000) * math.log(2)))
        assert bf.hash_count == expected_k

    def test_false_positive_rate_empty(self, bloom):
        """Empty filter has zero FPR."""
        assert bloom.false_positive_rate() == 0.0

    def test_false_positive_rate_increases_with_insertions(self, bloom):
        """FPR increases as more elements are added."""
        bloom.add("Fizz")
        fpr1 = bloom.false_positive_rate()
        for i in range(50):
            bloom.add(f"element_{i}")
        fpr2 = bloom.false_positive_rate()
        assert fpr2 > fpr1

    def test_bit_density_increases(self, bloom):
        """Bit density increases with insertions."""
        d0 = bloom.bit_density()
        bloom.add("Fizz")
        d1 = bloom.bit_density()
        assert d1 > d0

    def test_clear_resets_filter(self, bloom):
        """Clear returns the filter to empty state."""
        bloom.add("Fizz")
        bloom.add("Buzz")
        bloom.clear()
        assert bloom.element_count == 0
        assert bloom.bit_density() == 0.0
        assert not bloom.might_contain("Fizz")

    def test_invalid_expected_elements(self):
        """Zero or negative expected elements raises error."""
        with pytest.raises(ProbabilisticError):
            BloomFilter(expected_elements=0)

    def test_invalid_false_positive_rate(self):
        """FPR outside (0, 1) raises error."""
        with pytest.raises(ProbabilisticError):
            BloomFilter(expected_elements=100, false_positive_rate=0.0)
        with pytest.raises(ProbabilisticError):
            BloomFilter(expected_elements=100, false_positive_rate=1.0)

    def test_check_capacity_no_error_under_limit(self, bloom):
        """No error when under capacity."""
        for i in range(10):
            bloom.add(f"item_{i}")
        bloom.check_capacity()  # Should not raise

    def test_check_capacity_error_over_limit(self):
        """Error raised when significantly over capacity with high FPR."""
        bf = BloomFilter(expected_elements=5, false_positive_rate=0.01)
        for i in range(100):
            bf.add(f"item_{i}")
        with pytest.raises(BloomFilterCapacityError):
            bf.check_capacity()

    def test_properties_accessible(self, bloom):
        """All properties return expected types."""
        assert isinstance(bloom.bit_count, int)
        assert isinstance(bloom.hash_count, int)
        assert isinstance(bloom.expected_elements, int)
        assert isinstance(bloom.target_fpr, float)

    def test_duplicate_insert_idempotent_for_bits(self, bloom):
        """Inserting the same element twice does not change membership."""
        bloom.add("Fizz")
        density1 = bloom.bit_density()
        bloom.add("Fizz")
        density2 = bloom.bit_density()
        assert density1 == density2
        assert bloom.element_count == 2  # Count increments, but bits unchanged


# ============================================================
# Count-Min Sketch Tests
# ============================================================

class TestCountMinSketch:
    """Tests for the Count-Min Sketch implementation."""

    def test_empty_sketch_estimates_zero(self, cms):
        """Empty sketch returns zero for any item."""
        assert cms.estimate("Fizz") == 0
        assert cms.estimate("anything") == 0

    def test_increment_and_estimate(self, cms):
        """Single increment produces estimate of at least 1."""
        cms.increment("Fizz")
        assert cms.estimate("Fizz") >= 1

    def test_multiple_increments(self, cms):
        """Multiple increments produce proportional estimates."""
        for _ in range(100):
            cms.increment("Fizz")
        assert cms.estimate("Fizz") >= 100

    def test_estimate_is_upper_bound(self, cms):
        """Estimate is never less than true count."""
        true_count = 50
        for _ in range(true_count):
            cms.increment("Buzz")
        assert cms.estimate("Buzz") >= true_count

    def test_total_count(self, cms):
        """Total count tracks all increments."""
        cms.increment("Fizz", 10)
        cms.increment("Buzz", 20)
        assert cms.total_count == 30

    def test_increment_with_count(self, cms):
        """Increment with count > 1 works correctly."""
        cms.increment("FizzBuzz", count=42)
        assert cms.estimate("FizzBuzz") >= 42

    def test_top_k(self, cms):
        """Top-k returns items sorted by estimated frequency."""
        cms.increment("Fizz", 100)
        cms.increment("Buzz", 50)
        cms.increment("FizzBuzz", 25)
        result = cms.top_k(["Fizz", "Buzz", "FizzBuzz"], k=2)
        assert len(result) == 2
        assert result[0][0] == "Fizz"
        assert result[1][0] == "Buzz"

    def test_top_k_empty_candidates(self, cms):
        """Top-k with empty candidate list returns empty."""
        assert cms.top_k([], k=5) == []

    def test_merge(self):
        """Merging two sketches combines their counts."""
        cms1 = CountMinSketch(width=512, depth=3)
        cms2 = CountMinSketch(width=512, depth=3)
        cms1.increment("Fizz", 10)
        cms2.increment("Fizz", 20)
        cms1.merge(cms2)
        assert cms1.estimate("Fizz") >= 30
        assert cms1.total_count == 30

    def test_merge_dimension_mismatch(self):
        """Merging sketches with different dimensions raises error."""
        cms1 = CountMinSketch(width=512, depth=3)
        cms2 = CountMinSketch(width=256, depth=3)
        with pytest.raises(ProbabilisticError):
            cms1.merge(cms2)

    def test_clear(self, cms):
        """Clear resets all counters."""
        cms.increment("Fizz", 100)
        cms.clear()
        assert cms.estimate("Fizz") == 0
        assert cms.total_count == 0

    def test_invalid_width(self):
        """Zero width raises error."""
        with pytest.raises(ProbabilisticError):
            CountMinSketch(width=0)

    def test_invalid_depth(self):
        """Zero depth raises error."""
        with pytest.raises(ProbabilisticError):
            CountMinSketch(depth=0)

    def test_properties(self, cms):
        """Properties return expected values."""
        assert cms.width == 1024
        assert cms.depth == 5


# ============================================================
# HyperLogLog Tests
# ============================================================

class TestHyperLogLog:
    """Tests for the HyperLogLog cardinality estimator."""

    def test_empty_cardinality(self, hll):
        """Empty estimator reports zero cardinality."""
        assert hll.cardinality() == 0.0

    def test_single_element(self, hll):
        """Single element gives cardinality estimate around 1."""
        hll.add("Fizz")
        c = hll.cardinality()
        assert 0.5 <= c <= 3.0

    def test_cardinality_increases_with_distinct(self, hll):
        """Cardinality estimate increases with more distinct elements."""
        for i in range(10):
            hll.add(f"item_{i}")
        c10 = hll.cardinality()
        for i in range(10, 50):
            hll.add(f"item_{i}")
        c50 = hll.cardinality()
        assert c50 > c10

    def test_duplicates_do_not_increase_cardinality(self, hll):
        """Adding the same element multiple times does not inflate cardinality."""
        for _ in range(100):
            hll.add("Fizz")
        c = hll.cardinality()
        assert c < 5.0  # Should be approximately 1

    def test_cardinality_accuracy(self):
        """Estimate is within 3 standard errors of true cardinality."""
        hll = HyperLogLog(precision=14)
        n = 1000
        for i in range(n):
            hll.add(f"element_{i}")
        c = hll.cardinality()
        error_bound = 3 * hll.standard_error * n
        assert abs(c - n) < error_bound

    def test_merge(self):
        """Merged estimator captures union cardinality."""
        hll1 = HyperLogLog(precision=10)
        hll2 = HyperLogLog(precision=10)
        for i in range(50):
            hll1.add(f"item_{i}")
        for i in range(25, 75):
            hll2.add(f"item_{i}")
        hll1.merge(hll2)
        c = hll1.cardinality()
        # True cardinality of union is 75
        assert 40 < c < 120

    def test_merge_precision_mismatch(self):
        """Merging estimators with different precision raises error."""
        hll1 = HyperLogLog(precision=10)
        hll2 = HyperLogLog(precision=12)
        with pytest.raises(ProbabilisticError):
            hll1.merge(hll2)

    def test_invalid_precision_low(self):
        """Precision below 4 raises HyperLogLogPrecisionError."""
        with pytest.raises(HyperLogLogPrecisionError):
            HyperLogLog(precision=3)

    def test_invalid_precision_high(self):
        """Precision above 18 raises HyperLogLogPrecisionError."""
        with pytest.raises(HyperLogLogPrecisionError):
            HyperLogLog(precision=19)

    def test_precision_boundaries(self):
        """Precision 4 and 18 are both valid."""
        hll4 = HyperLogLog(precision=4)
        assert hll4.register_count == 16
        hll18 = HyperLogLog(precision=18)
        assert hll18.register_count == 262144

    def test_standard_error(self, hll):
        """Standard error is computed correctly."""
        expected = 1.04 / math.sqrt(1024)
        assert abs(hll.standard_error - expected) < 1e-10

    def test_clear(self, hll):
        """Clear resets all registers."""
        hll.add("Fizz")
        hll.clear()
        assert hll.cardinality() == 0.0
        assert hll.element_count == 0

    def test_element_count(self, hll):
        """Element count tracks additions."""
        hll.add("Fizz")
        hll.add("Buzz")
        assert hll.element_count == 2

    def test_properties(self, hll):
        """Properties return expected values."""
        assert hll.precision == 10
        assert hll.register_count == 1024

    def test_count_leading_zeros(self):
        """Leading zero count is correct for known values."""
        # Binary: 1000... -> 1 leading zero (rank 1)
        assert HyperLogLog._count_leading_zeros(0b10000000, 8) == 1
        # Binary: 0001... -> 3 leading zeros (rank 4)
        assert HyperLogLog._count_leading_zeros(0b00010000, 8) == 4
        # All zeros -> max_bits + 1
        assert HyperLogLog._count_leading_zeros(0, 8) == 9


# ============================================================
# T-Digest Tests
# ============================================================

class TestTDigest:
    """Tests for the T-Digest quantile estimator."""

    def test_single_value(self, tdigest):
        """Single value returns itself for any quantile."""
        tdigest.add(42.0)
        assert tdigest.quantile(0.5) == 42.0

    def test_two_values(self, tdigest):
        """Two values return interpolated results."""
        tdigest.add(10.0)
        tdigest.add(20.0)
        q50 = tdigest.quantile(0.5)
        assert 10.0 <= q50 <= 20.0

    def test_median_accuracy(self, tdigest):
        """Median of uniform data is approximately the midpoint."""
        for i in range(1, 101):
            tdigest.add(float(i))
        median = tdigest.quantile(0.5)
        assert 40 <= median <= 60

    def test_quantile_monotonicity(self, tdigest):
        """Higher quantiles yield higher or equal values."""
        for i in range(1, 101):
            tdigest.add(float(i))
        q25 = tdigest.quantile(0.25)
        q50 = tdigest.quantile(0.50)
        q75 = tdigest.quantile(0.75)
        q99 = tdigest.quantile(0.99)
        assert q25 <= q50 <= q75 <= q99

    def test_extreme_quantiles(self, tdigest):
        """Quantile 0 returns min, quantile 1 returns max."""
        for i in [5.0, 10.0, 15.0, 20.0]:
            tdigest.add(i)
        assert tdigest.quantile(0.0) == 5.0
        assert tdigest.quantile(1.0) == 20.0

    def test_min_max_tracking(self, tdigest):
        """Min and max are tracked correctly."""
        tdigest.add(50.0)
        tdigest.add(10.0)
        tdigest.add(90.0)
        assert tdigest.min == 10.0
        assert tdigest.max == 90.0

    def test_total_weight(self, tdigest):
        """Total weight tracks all additions."""
        tdigest.add(1.0)
        tdigest.add(2.0)
        tdigest.add(3.0, weight=5)
        assert tdigest.total_weight == 7

    def test_cdf_below_min(self, tdigest):
        """CDF below minimum value returns 0."""
        tdigest.add(10.0)
        tdigest.add(20.0)
        assert tdigest.cdf(5.0) == 0.0

    def test_cdf_above_max(self, tdigest):
        """CDF above maximum value returns 1."""
        tdigest.add(10.0)
        tdigest.add(20.0)
        assert tdigest.cdf(25.0) == 1.0

    def test_cdf_monotonicity(self, tdigest):
        """CDF is monotonically non-decreasing."""
        for i in range(1, 101):
            tdigest.add(float(i))
        prev = 0.0
        for x in range(0, 105, 5):
            c = tdigest.cdf(float(x))
            assert c >= prev
            prev = c

    def test_merge(self):
        """Merged T-Digests combine their data."""
        td1 = TDigest(compression=50)
        td2 = TDigest(compression=50)
        for i in range(1, 51):
            td1.add(float(i))
        for i in range(51, 101):
            td2.add(float(i))
        td1.merge(td2)
        assert td1.total_weight == 100
        assert td1.min == 1.0
        assert td1.max == 100.0
        median = td1.quantile(0.5)
        assert 35 <= median <= 65

    def test_clear(self, tdigest):
        """Clear resets the digest."""
        tdigest.add(42.0)
        tdigest.clear()
        assert tdigest.total_weight == 0
        assert tdigest.min is None
        assert tdigest.max is None

    def test_invalid_compression(self):
        """Zero compression raises error."""
        with pytest.raises(ProbabilisticError):
            TDigest(compression=0)

    def test_invalid_quantile(self, tdigest):
        """Quantile outside [0, 1] raises error."""
        tdigest.add(1.0)
        with pytest.raises(ProbabilisticError):
            tdigest.quantile(-0.1)
        with pytest.raises(ProbabilisticError):
            tdigest.quantile(1.1)

    def test_quantile_empty_raises(self, tdigest):
        """Quantile on empty digest raises error."""
        with pytest.raises(ProbabilisticError):
            tdigest.quantile(0.5)

    def test_centroid_count_bounded(self):
        """Centroid count stays bounded by compression parameter."""
        td = TDigest(compression=20)
        for i in range(1000):
            td.add(float(i))
        # Centroid count should be roughly proportional to compression
        assert td.centroid_count <= 20 * 10  # generous upper bound


# ============================================================
# Centroid Tests
# ============================================================

class TestCentroid:
    """Tests for the internal _Centroid class."""

    def test_creation(self):
        """Centroid initializes with mean and count."""
        c = _Centroid(mean=5.0, count=3)
        assert c.mean == 5.0
        assert c.count == 3

    def test_add_updates_weighted_mean(self):
        """Adding a value updates the weighted mean."""
        c = _Centroid(mean=10.0, count=2)
        c.add(20.0, weight=1)
        assert c.count == 3
        expected_mean = (10.0 * 2 + 20.0 * 1) / 3
        assert abs(c.mean - expected_mean) < 1e-10

    def test_repr(self):
        """Repr includes mean and count."""
        c = _Centroid(mean=3.14, count=7)
        r = repr(c)
        assert "3.14" in r
        assert "7" in r


# ============================================================
# Middleware Tests
# ============================================================

class TestProbabilisticMiddleware:
    """Tests for the ProbabilisticMiddleware integration."""

    def test_process_feeds_all_structures(self, middleware):
        """Processing a context feeds data to all four structures."""
        ctx = _make_context(15, "FizzBuzz")

        def next_handler(c):
            return c

        result = middleware.process(ctx, next_handler)

        assert middleware.bloom.might_contain("FizzBuzz")
        assert middleware.cms.estimate("FizzBuzz") >= 1
        assert middleware.hll.element_count == 1
        assert middleware.tdigest.total_weight == 1
        assert middleware.evaluations_processed == 1
        assert "FizzBuzz" in middleware.labels_seen

    def test_process_multiple_evaluations(self, middleware):
        """Multiple evaluations accumulate correctly."""
        labels = [("3", "Fizz"), ("5", "Buzz"), ("15", "FizzBuzz"), ("7", "7")]

        def next_handler(c):
            return c

        for num_str, label in labels:
            ctx = _make_context(int(num_str), label)
            middleware.process(ctx, next_handler)

        assert middleware.evaluations_processed == 4
        assert len(middleware.labels_seen) == 4
        for _, label in labels:
            assert middleware.bloom.might_contain(label)

    def test_middleware_name(self, middleware):
        """Middleware reports its name."""
        assert middleware.get_name() == "ProbabilisticMiddleware"

    def test_middleware_priority(self, middleware):
        """Middleware has priority 850."""
        assert middleware.get_priority() == 850

    def test_middleware_with_event_bus(self, bloom, cms, hll, tdigest):
        """Middleware emits events when event bus is provided."""
        bus = MagicMock()
        mw = ProbabilisticMiddleware(
            bloom=bloom, cms=cms, hll=hll, tdigest=tdigest,
            event_bus=bus,
        )
        ctx = _make_context(3, "Fizz")
        mw.process(ctx, lambda c: c)
        assert bus.publish.call_count == 4  # One per structure

    def test_middleware_tolerates_event_bus_failure(self, bloom, cms, hll, tdigest):
        """Middleware continues even if event bus raises."""
        bus = MagicMock()
        bus.publish.side_effect = RuntimeError("bus down")
        mw = ProbabilisticMiddleware(
            bloom=bloom, cms=cms, hll=hll, tdigest=tdigest,
            event_bus=bus,
        )
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, lambda c: c)
        assert result.number == 3

    def test_context_passed_through(self, middleware):
        """Middleware passes context to next handler."""
        ctx = _make_context(42, "Fizz")
        called = []

        def next_handler(c):
            called.append(c.number)
            return c

        middleware.process(ctx, next_handler)
        assert called == [42]


# ============================================================
# Dashboard Tests
# ============================================================

class TestProbabilisticDashboard:
    """Tests for the ProbabilisticDashboard renderer."""

    def test_render_with_data(self, middleware):
        """Dashboard renders without error when data is present."""
        for i in range(1, 16):
            label = "FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else str(i)
            ctx = _make_context(i, label)
            middleware.process(ctx, lambda c: c)

        output = ProbabilisticDashboard.render(middleware=middleware, width=60)
        assert "FIZZBLOOM" in output
        assert "BLOOM FILTER" in output
        assert "COUNT-MIN SKETCH" in output
        assert "HYPERLOGLOG" in output
        assert "T-DIGEST" in output

    def test_render_empty(self, middleware):
        """Dashboard renders without error when no data is present."""
        output = ProbabilisticDashboard.render(middleware=middleware, width=60)
        assert "FIZZBLOOM" in output
        assert "Evaluations processed: 0" in output

    def test_render_contains_density_bar(self, middleware):
        """Dashboard includes a density visualization."""
        middleware.bloom.add("Fizz")
        output = ProbabilisticDashboard.render(middleware=middleware)
        assert "[" in output
        assert "]" in output

    def test_render_contains_quantiles(self, middleware):
        """Dashboard shows quantile estimates when data exists."""
        for i in range(1, 101):
            label = "Fizz" if i % 3 == 0 else str(i)
            ctx = _make_context(i, label)
            middleware.process(ctx, lambda c: c)

        output = ProbabilisticDashboard.render(middleware=middleware)
        assert "p50" in output
        assert "p95" in output

    def test_render_custom_width(self, middleware):
        """Dashboard respects custom width parameter."""
        output_narrow = ProbabilisticDashboard.render(middleware=middleware, width=50)
        output_wide = ProbabilisticDashboard.render(middleware=middleware, width=80)
        narrow_lines = output_narrow.split("\n")
        wide_lines = output_wide.split("\n")
        # Wide dashboard lines should be wider
        if narrow_lines and wide_lines:
            assert max(len(l) for l in wide_lines) > max(len(l) for l in narrow_lines)


# ============================================================
# Factory Tests
# ============================================================

class TestCreateProbabilisticSubsystem:
    """Tests for the create_probabilistic_subsystem factory."""

    def test_creates_all_components(self):
        """Factory returns middleware and all four structures."""
        mw, bloom, cms, hll, td = create_probabilistic_subsystem()
        assert isinstance(mw, ProbabilisticMiddleware)
        assert isinstance(bloom, BloomFilter)
        assert isinstance(cms, CountMinSketch)
        assert isinstance(hll, HyperLogLog)
        assert isinstance(td, TDigest)

    def test_custom_parameters(self):
        """Factory respects custom parameters."""
        mw, bloom, cms, hll, td = create_probabilistic_subsystem(
            bloom_expected=500,
            bloom_fpr=0.05,
            cms_width=256,
            cms_depth=3,
            hll_precision=8,
            tdigest_compression=50,
        )
        assert bloom.expected_elements == 500
        assert cms.width == 256
        assert cms.depth == 3
        assert hll.precision == 8
        assert td.compression == 50

    def test_middleware_wired_to_structures(self):
        """Middleware references the same structure instances."""
        mw, bloom, cms, hll, td = create_probabilistic_subsystem()
        assert mw.bloom is bloom
        assert mw.cms is cms
        assert mw.hll is hll
        assert mw.tdigest is td

    def test_event_bus_passed_through(self):
        """Event bus is forwarded to middleware."""
        bus = MagicMock()
        mw, _, _, _, _ = create_probabilistic_subsystem(event_bus=bus)
        ctx = _make_context(3, "Fizz")
        mw.process(ctx, lambda c: c)
        assert bus.publish.called

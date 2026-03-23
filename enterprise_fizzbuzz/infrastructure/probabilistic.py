"""
Enterprise FizzBuzz Platform - Probabilistic Data Structures Module (FizzBloom)

Implements four probabilistic data structures for approximate analytics over
the FizzBuzz evaluation stream:

- **BloomFilter**: Space-efficient probabilistic set membership testing with
  configurable false positive rate. Answers "possibly in set" or "definitely
  not in set" for FizzBuzz evaluation results.

- **CountMinSketch**: Sub-linear space frequency estimation using multiple
  hash functions and the minimum-across-rows estimator. Provides approximate
  frequency counts for each evaluation label.

- **HyperLogLog**: Cardinality estimation using the Flajolet-Martin approach
  with stochastic averaging and bias correction. Estimates the number of
  distinct evaluation results observed in the stream.

- **TDigest**: Streaming quantile approximation using a sorted centroid
  representation with compression. Enables percentile queries over the
  numeric evaluation stream (e.g., p50, p95, p99 of input values).

These structures are fed by ProbabilisticMiddleware (priority 850) which
intercepts every evaluation in the middleware pipeline and routes data to
all four structures simultaneously. The ProbabilisticDashboard renders a
unified ASCII view of all four structures' state.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BloomFilterCapacityError,
    CountMinSketchOverflowError,
    HyperLogLogPrecisionError,
    ProbabilisticError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger(__name__)

# Maximum 64-bit signed integer, used as overflow guard for CMS counters
_MAX_COUNTER = (2**63) - 1


# ============================================================
# Hash Utilities
# ============================================================

def _hash_with_seed(item: str, seed: int) -> int:
    """Produce a deterministic hash of *item* mixed with *seed*.

    Uses SHA-256 with a 4-byte big-endian seed prefix. The full
    256-bit digest is truncated to 64 bits, which provides more
    than enough entropy for the index computations required by
    Bloom filters, Count-Min Sketches, and HyperLogLog registers.
    """
    data = struct.pack(">I", seed & 0xFFFFFFFF) + item.encode("utf-8")
    digest = hashlib.sha256(data).digest()
    return struct.unpack(">Q", digest[:8])[0]


def _md5_hash_with_seed(item: str, seed: int) -> int:
    """Produce a deterministic MD5-based hash mixed with *seed*.

    MD5 is used as a secondary hash family to ensure independence
    between the SHA-256 and MD5 hash families when both are needed
    within the same structure.
    """
    data = struct.pack(">I", seed & 0xFFFFFFFF) + item.encode("utf-8")
    digest = hashlib.md5(data).digest()
    return struct.unpack(">Q", digest[:8])[0]


# ============================================================
# Bloom Filter
# ============================================================

class BloomFilter:
    """Space-efficient probabilistic set membership structure.

    A Bloom filter uses a bit array of m bits and k independent hash
    functions. To add an element, it sets the k bit positions computed
    by the hash functions. To query membership, it checks whether all
    k positions are set. False positives are possible (the filter may
    report membership for an element that was never added), but false
    negatives are not.

    Optimal parameters are computed from the expected number of
    elements n and the desired false positive probability p:

        m = -n * ln(p) / (ln(2))^2
        k = (m / n) * ln(2)
    """

    def __init__(
        self,
        expected_elements: int = 1000,
        false_positive_rate: float = 0.01,
    ) -> None:
        if expected_elements <= 0:
            raise ProbabilisticError(
                f"Expected elements must be positive, got {expected_elements}"
            )
        if not (0.0 < false_positive_rate < 1.0):
            raise ProbabilisticError(
                f"False positive rate must be in (0, 1), got {false_positive_rate}"
            )

        self._expected_elements = expected_elements
        self._target_fpr = false_positive_rate

        # Optimal bit array size: m = -n * ln(p) / (ln(2))^2
        ln2_sq = math.log(2) ** 2
        self._m = max(1, int(math.ceil(
            -expected_elements * math.log(false_positive_rate) / ln2_sq
        )))

        # Optimal number of hash functions: k = (m/n) * ln(2)
        self._k = max(1, int(round(
            (self._m / expected_elements) * math.log(2)
        )))

        # Bit array stored as a bytearray for memory efficiency
        self._bits = bytearray((self._m + 7) // 8)
        self._count = 0

        logger.debug(
            "BloomFilter initialized: m=%d bits, k=%d hashes, "
            "target FPR=%.6f for n=%d elements",
            self._m, self._k, false_positive_rate, expected_elements,
        )

    @property
    def bit_count(self) -> int:
        """Total number of bits in the filter."""
        return self._m

    @property
    def hash_count(self) -> int:
        """Number of hash functions used."""
        return self._k

    @property
    def element_count(self) -> int:
        """Number of elements that have been added."""
        return self._count

    @property
    def expected_elements(self) -> int:
        """Designed capacity of the filter."""
        return self._expected_elements

    @property
    def target_fpr(self) -> float:
        """Design-time false positive rate."""
        return self._target_fpr

    def _get_bit(self, index: int) -> bool:
        """Read a single bit from the bit array."""
        byte_index = index >> 3
        bit_offset = index & 7
        return bool(self._bits[byte_index] & (1 << bit_offset))

    def _set_bit(self, index: int) -> None:
        """Set a single bit in the bit array."""
        byte_index = index >> 3
        bit_offset = index & 7
        self._bits[byte_index] |= (1 << bit_offset)

    def _hash_positions(self, item: str) -> list[int]:
        """Compute the k bit positions for *item*."""
        positions = []
        for seed in range(self._k):
            h = _hash_with_seed(item, seed)
            positions.append(h % self._m)
        return positions

    def add(self, item: str) -> None:
        """Insert an element into the Bloom filter.

        Sets the k bit positions corresponding to the element's
        hash values. Duplicate insertions are idempotent with
        respect to the bit array but increment the element counter.
        """
        for pos in self._hash_positions(item):
            self._set_bit(pos)
        self._count += 1

    def might_contain(self, item: str) -> bool:
        """Query whether an element might be in the set.

        Returns True if the element is possibly present (with a
        probability of false positive bounded by the design FPR),
        or False if the element is definitely not in the set.
        """
        return all(self._get_bit(pos) for pos in self._hash_positions(item))

    def false_positive_rate(self) -> float:
        """Estimate the current false positive rate.

        Uses the theoretical formula:
            FPR = (1 - e^(-k*n/m))^k

        where n is the number of inserted elements.
        """
        if self._count == 0:
            return 0.0
        exponent = -self._k * self._count / self._m
        return (1.0 - math.exp(exponent)) ** self._k

    def bit_density(self) -> float:
        """Fraction of bits that are set to 1."""
        set_bits = 0
        for byte_val in self._bits:
            set_bits += bin(byte_val).count("1")
        return set_bits / self._m if self._m > 0 else 0.0

    def clear(self) -> None:
        """Reset the filter to its initial empty state."""
        self._bits = bytearray((self._m + 7) // 8)
        self._count = 0

    def check_capacity(self) -> None:
        """Raise BloomFilterCapacityError if the filter is over capacity."""
        if self._count > self._expected_elements:
            fpr = self.false_positive_rate()
            if fpr > self._target_fpr * 2:
                raise BloomFilterCapacityError(
                    self._count, self._expected_elements, fpr
                )


# ============================================================
# Count-Min Sketch
# ============================================================

class CountMinSketch:
    """Sub-linear space frequency estimation structure.

    A Count-Min Sketch maintains a 2D array of d rows and w columns.
    Each row uses an independent hash function. To increment the count
    for an item, the item is hashed once per row and the corresponding
    counter is incremented. To estimate the count, the minimum value
    across all d rows is returned -- this provides an upper bound on
    the true count with controlled overestimation.

    The error guarantee is: with probability at least 1 - delta,
    the estimate is at most (epsilon * N) larger than the true count,
    where N is the total number of increments, epsilon = e / w,
    and delta = 1 / e^d.
    """

    def __init__(self, width: int = 2048, depth: int = 5) -> None:
        if width <= 0:
            raise ProbabilisticError(
                f"Count-Min Sketch width must be positive, got {width}"
            )
        if depth <= 0:
            raise ProbabilisticError(
                f"Count-Min Sketch depth must be positive, got {depth}"
            )

        self._width = width
        self._depth = depth
        self._table: list[list[int]] = [
            [0] * width for _ in range(depth)
        ]
        self._total_count = 0

        logger.debug(
            "CountMinSketch initialized: width=%d, depth=%d, "
            "epsilon=%.6f, delta=%.6f",
            width, depth, math.e / width, 1.0 / math.exp(depth),
        )

    @property
    def width(self) -> int:
        """Number of counters per row."""
        return self._width

    @property
    def depth(self) -> int:
        """Number of rows (hash functions)."""
        return self._depth

    @property
    def total_count(self) -> int:
        """Total number of increments across all items."""
        return self._total_count

    def _hash_indices(self, item: str) -> list[int]:
        """Compute the column index for each row."""
        indices = []
        for row in range(self._depth):
            h = _md5_hash_with_seed(item, row + 1000)
            indices.append(h % self._width)
        return indices

    def increment(self, item: str, count: int = 1) -> None:
        """Increment the frequency counter for *item*.

        Raises CountMinSketchOverflowError if any counter would
        exceed the 64-bit signed integer range.
        """
        indices = self._hash_indices(item)
        for row, col in enumerate(indices):
            new_val = self._table[row][col] + count
            if new_val > _MAX_COUNTER:
                raise CountMinSketchOverflowError(row, col, new_val)
            self._table[row][col] = new_val
        self._total_count += count

    def estimate(self, item: str) -> int:
        """Estimate the frequency of *item*.

        Returns the minimum counter value across all d rows for
        the given item. This is guaranteed to be >= the true count
        and at most epsilon * N above it with high probability.
        """
        indices = self._hash_indices(item)
        return min(
            self._table[row][col]
            for row, col in enumerate(indices)
        )

    def merge(self, other: CountMinSketch) -> CountMinSketch:
        """Merge another Count-Min Sketch into this one.

        Both sketches must have identical width and depth parameters.
        Returns self for fluent chaining.
        """
        if self._width != other._width or self._depth != other._depth:
            raise ProbabilisticError(
                f"Cannot merge CMS with dimensions ({other._width}, {other._depth}) "
                f"into CMS with dimensions ({self._width}, {self._depth})"
            )
        for row in range(self._depth):
            for col in range(self._width):
                self._table[row][col] += other._table[row][col]
        self._total_count += other._total_count
        return self

    def top_k(self, candidates: list[str], k: int = 5) -> list[tuple[str, int]]:
        """Return the top-k items by estimated frequency from a candidate list.

        The Count-Min Sketch does not track keys, so a candidate list
        must be provided. Items are ranked by their estimated count.
        """
        estimates = [(item, self.estimate(item)) for item in candidates]
        estimates.sort(key=lambda x: x[1], reverse=True)
        return estimates[:k]

    def clear(self) -> None:
        """Reset all counters to zero."""
        for row in range(self._depth):
            for col in range(self._width):
                self._table[row][col] = 0
        self._total_count = 0


# ============================================================
# HyperLogLog
# ============================================================

class HyperLogLog:
    """Cardinality estimation using stochastic averaging.

    HyperLogLog divides hash values into 2^p registers using the
    first p bits as the register index. For each element, the
    remaining bits are examined for the position of the first 1-bit
    (the "rank"). Each register stores the maximum rank observed.

    The cardinality estimate uses the harmonic mean of 2^(-register)
    values, multiplied by a bias-correction constant alpha_m:

        E = alpha_m * m^2 / sum(2^(-M[j]))

    For small cardinalities, linear counting is used as a correction;
    for large cardinalities, the raw estimate is adjusted to account
    for hash collisions.
    """

    # Bias correction constants for small register counts
    _ALPHA = {
        4: 0.532,
        5: 0.625,
        6: 0.673,
    }

    def __init__(self, precision: int = 14) -> None:
        if not (4 <= precision <= 18):
            raise HyperLogLogPrecisionError(precision)

        self._p = precision
        self._m = 1 << precision  # Number of registers = 2^p
        self._registers = bytearray(self._m)
        self._count = 0

        # alpha_m constant for bias correction
        if precision in self._ALPHA:
            self._alpha = self._ALPHA[precision]
        else:
            self._alpha = 0.7213 / (1.0 + 1.079 / self._m)

        logger.debug(
            "HyperLogLog initialized: precision=%d, registers=%d, "
            "alpha=%.4f, standard_error=%.4f",
            precision, self._m, self._alpha,
            1.04 / math.sqrt(self._m),
        )

    @property
    def precision(self) -> int:
        """Precision parameter p."""
        return self._p

    @property
    def register_count(self) -> int:
        """Number of registers (2^p)."""
        return self._m

    @property
    def element_count(self) -> int:
        """Number of elements that have been added."""
        return self._count

    @property
    def standard_error(self) -> float:
        """Theoretical standard error of the estimator: 1.04 / sqrt(m)."""
        return 1.04 / math.sqrt(self._m)

    @staticmethod
    def _count_leading_zeros(value: int, max_bits: int) -> int:
        """Count leading zeros in the binary representation.

        Examines at most *max_bits* positions. Returns the 1-based
        position of the first 1-bit (i.e., rank = leading_zeros + 1).
        If no 1-bit is found, returns max_bits + 1.
        """
        for i in range(max_bits):
            if value & (1 << (max_bits - 1 - i)):
                return i + 1
        return max_bits + 1

    def add(self, item: str) -> None:
        """Add an element to the HyperLogLog estimator.

        Computes a 64-bit hash, uses the first p bits as the register
        index, and stores the maximum rank (leading zeros + 1) of the
        remaining bits.
        """
        h = _hash_with_seed(item, 0x484C4C)  # Seed: "HLL" in hex
        # First p bits determine the register index
        register_idx = h >> (64 - self._p)
        # Remaining bits determine the rank
        remaining_bits = 64 - self._p
        w = h & ((1 << remaining_bits) - 1)
        rank = self._count_leading_zeros(w, remaining_bits)
        self._registers[register_idx] = max(
            self._registers[register_idx], rank
        )
        self._count += 1

    def cardinality(self) -> float:
        """Estimate the number of distinct elements.

        Applies the HyperLogLog algorithm with small-range and
        large-range corrections:

        1. Raw estimate: E = alpha_m * m^2 / sum(2^(-M[j]))
        2. Small range correction (E < 5/2 * m): linear counting
           using the number of zero-valued registers
        3. Large range correction (E > 2^32 / 30): hash collision
           adjustment
        """
        # Compute the harmonic mean indicator
        indicator = 0.0
        for reg in self._registers:
            indicator += 2.0 ** (-reg)

        raw_estimate = self._alpha * (self._m ** 2) / indicator

        # Small range correction: linear counting
        if raw_estimate <= 2.5 * self._m:
            zero_registers = self._registers.count(0)
            if zero_registers > 0:
                return self._m * math.log(self._m / zero_registers)
            return raw_estimate

        # Large range correction
        two_32 = 2.0 ** 32
        if raw_estimate > two_32 / 30.0:
            return -two_32 * math.log(1.0 - raw_estimate / two_32)

        return raw_estimate

    def merge(self, other: HyperLogLog) -> HyperLogLog:
        """Merge another HyperLogLog estimator into this one.

        Takes the element-wise maximum of the register arrays.
        Both estimators must have the same precision.
        """
        if self._p != other._p:
            raise ProbabilisticError(
                f"Cannot merge HyperLogLog with precision {other._p} "
                f"into HyperLogLog with precision {self._p}"
            )
        for i in range(self._m):
            self._registers[i] = max(self._registers[i], other._registers[i])
        self._count += other._count
        return self

    def clear(self) -> None:
        """Reset all registers to zero."""
        self._registers = bytearray(self._m)
        self._count = 0


# ============================================================
# T-Digest
# ============================================================

class _Centroid:
    """A weighted centroid in the T-Digest data structure.

    Each centroid represents a cluster of nearby values. The mean
    is the weighted average of all values in the cluster, and the
    weight (count) is the number of values.
    """

    __slots__ = ("mean", "count")

    def __init__(self, mean: float, count: int = 1) -> None:
        self.mean = mean
        self.count = count

    def add(self, value: float, weight: int = 1) -> None:
        """Merge a value into this centroid using weighted averaging."""
        new_count = self.count + weight
        self.mean = (self.mean * self.count + value * weight) / new_count
        self.count = new_count

    def __repr__(self) -> str:
        return f"_Centroid(mean={self.mean:.4f}, count={self.count})"


class TDigest:
    """Streaming quantile estimator using sorted centroids.

    The T-Digest maintains an ordered list of centroids, each
    representing a cluster of values. The compression parameter
    (delta) controls the tradeoff between accuracy and memory:
    higher values allow more centroids and improve accuracy at
    extreme quantiles (near 0 or 1).

    The key insight is that centroids near the tails are kept
    small (few values) for precision, while centroids near the
    median can be larger. This size constraint is enforced during
    compression using the scale function:

        k(q) = (delta / 2) * arcsin(2q - 1) / pi

    The maximum weight of a centroid at quantile q is bounded by:
        max_weight = 4 * N * q * (1 - q) / delta
    """

    def __init__(self, compression: int = 100) -> None:
        if compression <= 0:
            raise ProbabilisticError(
                f"T-Digest compression must be positive, got {compression}"
            )

        self._compression = compression
        self._centroids: list[_Centroid] = []
        self._total_weight = 0
        self._min_val: Optional[float] = None
        self._max_val: Optional[float] = None
        self._unmerged_count = 0
        self._buffer: list[tuple[float, int]] = []
        self._buffer_limit = max(10, compression)

        logger.debug(
            "TDigest initialized: compression=%d, max_centroids~%d",
            compression, compression * 5,
        )

    @property
    def compression(self) -> int:
        """Compression parameter delta."""
        return self._compression

    @property
    def total_weight(self) -> int:
        """Total number of values added."""
        return self._total_weight

    @property
    def centroid_count(self) -> int:
        """Current number of centroids."""
        return len(self._centroids)

    @property
    def min(self) -> Optional[float]:
        """Minimum value observed."""
        return self._min_val

    @property
    def max(self) -> Optional[float]:
        """Maximum value observed."""
        return self._max_val

    def _max_weight_at_quantile(self, q: float, n: int) -> float:
        """Maximum centroid weight allowed at quantile q."""
        return max(1.0, 4.0 * n * q * (1.0 - q) / self._compression)

    def add(self, value: float, weight: int = 1) -> None:
        """Add a value with optional weight to the digest.

        Values are buffered and periodically compressed into the
        sorted centroid list.
        """
        if self._min_val is None or value < self._min_val:
            self._min_val = value
        if self._max_val is None or value > self._max_val:
            self._max_val = value

        self._buffer.append((value, weight))
        self._total_weight += weight
        self._unmerged_count += 1

        if self._unmerged_count >= self._buffer_limit:
            self._compress()

    def _compress(self) -> None:
        """Merge buffered values into the sorted centroid list."""
        if not self._buffer:
            return

        # Combine buffer values with existing centroids
        all_values: list[tuple[float, int]] = [
            (c.mean, c.count) for c in self._centroids
        ]
        all_values.extend(self._buffer)
        all_values.sort(key=lambda x: x[0])
        self._buffer.clear()
        self._unmerged_count = 0

        # Rebuild centroids with size constraints
        new_centroids: list[_Centroid] = []
        if not all_values:
            self._centroids = new_centroids
            return

        current = _Centroid(all_values[0][0], all_values[0][1])
        cumulative_weight = 0.0

        for mean, count in all_values[1:]:
            proposed_weight = current.count + count
            # Quantile of the current centroid
            q = (cumulative_weight + current.count / 2.0) / self._total_weight
            max_w = self._max_weight_at_quantile(q, self._total_weight)

            if proposed_weight <= max_w:
                current.add(mean, count)
            else:
                new_centroids.append(current)
                cumulative_weight += current.count
                current = _Centroid(mean, count)

        new_centroids.append(current)
        self._centroids = new_centroids

    def quantile(self, q: float) -> float:
        """Estimate the value at quantile q (0 <= q <= 1).

        Interpolates between centroids to estimate the value at
        the requested quantile. Extreme quantiles (near 0 or 1)
        use the tracked min/max values for improved accuracy.
        """
        if not (0.0 <= q <= 1.0):
            raise ProbabilisticError(
                f"Quantile must be in [0, 1], got {q}"
            )

        self._compress()

        if not self._centroids:
            raise ProbabilisticError("Cannot compute quantile of empty T-Digest")

        if len(self._centroids) == 1:
            return self._centroids[0].mean

        # Edge cases
        if q == 0.0:
            return self._min_val if self._min_val is not None else self._centroids[0].mean
        if q == 1.0:
            return self._max_val if self._max_val is not None else self._centroids[-1].mean

        target_weight = q * self._total_weight
        cumulative = 0.0

        for i, centroid in enumerate(self._centroids):
            upper = cumulative + centroid.count
            if target_weight < upper:
                # Interpolate within this centroid's range
                if i == 0:
                    # First centroid: interpolate between min and centroid mean
                    if self._min_val is not None and cumulative < target_weight:
                        inner_q = (target_weight - cumulative) / centroid.count
                        return self._min_val + inner_q * (centroid.mean - self._min_val)
                    return centroid.mean

                # Interpolate between previous and current centroid
                prev = self._centroids[i - 1]
                prev_upper = cumulative
                prev_mid = prev_upper - prev.count / 2.0
                curr_mid = cumulative + centroid.count / 2.0

                if curr_mid == prev_mid:
                    return centroid.mean

                fraction = (target_weight - prev_mid) / (curr_mid - prev_mid)
                fraction = max(0.0, min(1.0, fraction))
                return prev.mean + fraction * (centroid.mean - prev.mean)

            cumulative = upper

        # Past the last centroid
        return self._max_val if self._max_val is not None else self._centroids[-1].mean

    def cdf(self, value: float) -> float:
        """Estimate the cumulative distribution function at *value*.

        Returns the estimated fraction of values less than or equal
        to *value*, in the range [0, 1].
        """
        self._compress()

        if not self._centroids:
            return 0.0

        if self._min_val is not None and value <= self._min_val:
            return 0.0
        if self._max_val is not None and value >= self._max_val:
            return 1.0

        cumulative = 0.0
        for i, centroid in enumerate(self._centroids):
            if value < centroid.mean:
                if i == 0:
                    if self._min_val is not None:
                        fraction = (value - self._min_val) / (centroid.mean - self._min_val)
                        return fraction * (centroid.count / 2.0) / self._total_weight
                    return 0.0
                prev = self._centroids[i - 1]
                prev_cumulative = cumulative - prev.count / 2.0
                span = centroid.mean - prev.mean
                if span == 0:
                    return cumulative / self._total_weight
                fraction = (value - prev.mean) / span
                interpolated = prev_cumulative + prev.count / 2.0 + fraction * (
                    (prev.count + centroid.count) / 2.0
                )
                return min(1.0, interpolated / self._total_weight)
            cumulative += centroid.count

        return 1.0

    def merge(self, other: TDigest) -> TDigest:
        """Merge another T-Digest into this one.

        Combines the centroid lists and recompresses to maintain
        the size constraint.
        """
        if other._min_val is not None:
            if self._min_val is None or other._min_val < self._min_val:
                self._min_val = other._min_val
        if other._max_val is not None:
            if self._max_val is None or other._max_val > self._max_val:
                self._max_val = other._max_val

        for centroid in other._centroids:
            self._buffer.append((centroid.mean, centroid.count))
        for value, weight in other._buffer:
            self._buffer.append((value, weight))

        self._total_weight += other._total_weight
        self._unmerged_count += len(self._buffer)
        self._compress()
        return self

    def clear(self) -> None:
        """Reset the digest to its initial empty state."""
        self._centroids.clear()
        self._buffer.clear()
        self._total_weight = 0
        self._min_val = None
        self._max_val = None
        self._unmerged_count = 0


# ============================================================
# Probabilistic Middleware
# ============================================================

class ProbabilisticMiddleware(IMiddleware):
    """Middleware that feeds FizzBuzz evaluations into all four
    probabilistic data structures.

    Intercepts each evaluation in the middleware pipeline and:
    1. Adds the result label to the Bloom filter
    2. Increments the label count in the Count-Min Sketch
    3. Adds the label to the HyperLogLog estimator
    4. Adds the input number to the T-Digest

    Priority 850 places this middleware after the core evaluation
    logic but before most observability middleware, ensuring that
    probabilistic structures receive clean, validated results.
    """

    def __init__(
        self,
        bloom: BloomFilter,
        cms: CountMinSketch,
        hll: HyperLogLog,
        tdigest: TDigest,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._bloom = bloom
        self._cms = cms
        self._hll = hll
        self._tdigest = tdigest
        self._event_bus = event_bus
        self._evaluations_processed = 0
        self._labels_seen: set[str] = set()

    @property
    def bloom(self) -> BloomFilter:
        """The Bloom filter instance."""
        return self._bloom

    @property
    def cms(self) -> CountMinSketch:
        """The Count-Min Sketch instance."""
        return self._cms

    @property
    def hll(self) -> HyperLogLog:
        """The HyperLogLog instance."""
        return self._hll

    @property
    def tdigest(self) -> TDigest:
        """The T-Digest instance."""
        return self._tdigest

    @property
    def evaluations_processed(self) -> int:
        """Total evaluations routed through the probabilistic pipeline."""
        return self._evaluations_processed

    @property
    def labels_seen(self) -> set[str]:
        """Set of distinct labels observed (exact, for top-k candidate list)."""
        return self._labels_seen

    def _emit(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Emit an event if an event bus is available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                logger.debug("Failed to emit probabilistic event %s", event_type)

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Intercept evaluation and feed into all four structures."""
        result = next_handler(context)

        # Determine the label from the latest evaluation result
        number = context.number
        label = str(number)
        if context.results:
            latest = context.results[-1]
            label = latest.output or str(latest.number)

        # Feed Bloom filter
        self._bloom.add(label)
        self._emit(EventType.PROBABILISTIC_BLOOM_ADD, {
            "label": label,
            "number": number,
            "bit_density": self._bloom.bit_density(),
        })

        # Feed Count-Min Sketch
        self._cms.increment(label)
        self._emit(EventType.PROBABILISTIC_CMS_INCREMENT, {
            "label": label,
            "estimated_count": self._cms.estimate(label),
        })

        # Feed HyperLogLog
        self._hll.add(label)
        self._emit(EventType.PROBABILISTIC_HLL_ADD, {
            "label": label,
            "estimated_cardinality": self._hll.cardinality(),
        })

        # Feed T-Digest with the numeric input
        self._tdigest.add(float(number))
        self._emit(EventType.PROBABILISTIC_TDIGEST_ADD, {
            "number": number,
            "total_weight": self._tdigest.total_weight,
        })

        self._labels_seen.add(label)
        self._evaluations_processed += 1

        return result

    def get_name(self) -> str:
        return "ProbabilisticMiddleware"

    def get_priority(self) -> int:
        return 850


# ============================================================
# Probabilistic Dashboard
# ============================================================

class ProbabilisticDashboard:
    """ASCII dashboard renderer for the FizzBloom probabilistic analytics suite.

    Displays a unified view of all four data structures:
    - Bloom filter: bit density bar, element count, FPR
    - Count-Min Sketch: top-k labels by estimated frequency
    - HyperLogLog: cardinality estimate with error bounds
    - T-Digest: quantile estimates (p25, p50, p75, p90, p95, p99)
    """

    @staticmethod
    def render(
        middleware: ProbabilisticMiddleware,
        width: int = 60,
    ) -> str:
        """Render the complete FizzBloom dashboard."""
        lines: list[str] = []
        inner = width - 4  # Account for "| " and " |" borders

        def border() -> str:
            return "  +" + "-" * (width - 2) + "+"

        def title_line(text: str) -> str:
            return "  | " + text.center(inner) + " |"

        def data_line(text: str) -> str:
            return "  | " + text.ljust(inner) + " |"

        def empty_line() -> str:
            return "  | " + " " * inner + " |"

        bloom = middleware.bloom
        cms = middleware.cms
        hll = middleware.hll
        tdigest = middleware.tdigest

        # Header
        lines.append(border())
        lines.append(title_line("FIZZBLOOM: PROBABILISTIC DATA STRUCTURES"))
        lines.append(title_line("Approximate Analytics Dashboard"))
        lines.append(border())

        # Summary
        lines.append(data_line(
            f"Evaluations processed: {middleware.evaluations_processed}"
        ))
        lines.append(data_line(
            f"Distinct labels (exact): {len(middleware.labels_seen)}"
        ))
        lines.append(border())

        # Bloom Filter Section
        lines.append(title_line("BLOOM FILTER"))
        lines.append(border())
        density = bloom.bit_density()
        fpr = bloom.false_positive_rate()
        lines.append(data_line(
            f"Bits: {bloom.bit_count}  Hashes: {bloom.hash_count}  "
            f"Elements: {bloom.element_count}/{bloom.expected_elements}"
        ))
        lines.append(data_line(f"Bit density: {density:.4f}  FPR: {fpr:.6f}"))

        # Density bar
        bar_width = min(inner - 12, 40)
        filled = int(density * bar_width)
        bar = "[" + "#" * filled + "." * (bar_width - filled) + "]"
        lines.append(data_line(f"Density:  {bar} {density*100:.1f}%"))
        lines.append(border())

        # Count-Min Sketch Section
        lines.append(title_line("COUNT-MIN SKETCH"))
        lines.append(border())
        lines.append(data_line(
            f"Width: {cms.width}  Depth: {cms.depth}  "
            f"Total increments: {cms.total_count}"
        ))

        # Top-k labels
        candidates = list(middleware.labels_seen)
        if candidates:
            top_items = cms.top_k(candidates, k=min(10, len(candidates)))
            lines.append(data_line("Top labels by estimated frequency:"))
            for rank, (label, count) in enumerate(top_items, 1):
                display_label = label if len(label) <= 20 else label[:17] + "..."
                lines.append(data_line(
                    f"  {rank:>2}. {display_label:<22} ~{count}"
                ))
        else:
            lines.append(data_line("No data recorded yet."))
        lines.append(border())

        # HyperLogLog Section
        lines.append(title_line("HYPERLOGLOG CARDINALITY ESTIMATOR"))
        lines.append(border())
        cardinality = hll.cardinality()
        lines.append(data_line(
            f"Precision: {hll.precision}  Registers: {hll.register_count}"
        ))
        lines.append(data_line(
            f"Elements added: {hll.element_count}  "
            f"Standard error: {hll.standard_error:.4f}"
        ))
        lines.append(data_line(
            f"Estimated distinct cardinality: {cardinality:.1f}"
        ))
        # Confidence interval (approximate)
        error_margin = cardinality * hll.standard_error
        lower = max(0, cardinality - 2 * error_margin)
        upper = cardinality + 2 * error_margin
        lines.append(data_line(
            f"95% confidence interval: [{lower:.1f}, {upper:.1f}]"
        ))
        lines.append(border())

        # T-Digest Section
        lines.append(title_line("T-DIGEST QUANTILE ESTIMATOR"))
        lines.append(border())
        lines.append(data_line(
            f"Compression: {tdigest.compression}  "
            f"Centroids: {tdigest.centroid_count}  "
            f"Total weight: {tdigest.total_weight}"
        ))

        if tdigest.total_weight > 0:
            lines.append(data_line(
                f"Range: [{tdigest.min:.1f}, {tdigest.max:.1f}]"
            ))
            quantiles = [0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
            lines.append(data_line("Quantile estimates:"))
            for q in quantiles:
                try:
                    val = tdigest.quantile(q)
                    lines.append(data_line(f"  p{int(q*100):>2}: {val:.2f}"))
                except ProbabilisticError:
                    lines.append(data_line(f"  p{int(q*100):>2}: N/A"))
        else:
            lines.append(data_line("No data recorded yet."))
        lines.append(border())

        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================

def create_probabilistic_subsystem(
    *,
    bloom_expected: int = 1000,
    bloom_fpr: float = 0.01,
    cms_width: int = 2048,
    cms_depth: int = 5,
    hll_precision: int = 14,
    tdigest_compression: int = 100,
    event_bus: Optional[Any] = None,
) -> tuple[ProbabilisticMiddleware, BloomFilter, CountMinSketch, HyperLogLog, TDigest]:
    """Create and wire all FizzBloom probabilistic data structures.

    Returns a tuple of (middleware, bloom, cms, hll, tdigest) for
    external access to individual structures (e.g., for dashboard
    rendering or post-hoc queries).
    """
    bloom = BloomFilter(
        expected_elements=bloom_expected,
        false_positive_rate=bloom_fpr,
    )
    cms = CountMinSketch(width=cms_width, depth=cms_depth)
    hll = HyperLogLog(precision=hll_precision)
    tdigest = TDigest(compression=tdigest_compression)

    middleware = ProbabilisticMiddleware(
        bloom=bloom,
        cms=cms,
        hll=hll,
        tdigest=tdigest,
        event_bus=event_bus,
    )

    logger.info(
        "FizzBloom probabilistic subsystem initialized: "
        "Bloom(m=%d, k=%d), CMS(%dx%d), HLL(p=%d), TDigest(delta=%d)",
        bloom.bit_count, bloom.hash_count,
        cms.width, cms.depth,
        hll.precision,
        tdigest.compression,
    )

    return middleware, bloom, cms, hll, tdigest

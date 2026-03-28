"""Enterprise FizzBuzz Platform - FizzBloom: Probabilistic Data Structures"""
from __future__ import annotations
import hashlib, logging, math, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzbloom import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzbloom")
EVENT_BLOOM = EventType.register("FIZZBLOOM_QUERY")
FIZZBLOOM_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 214


@dataclass
class FizzBloomConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class BloomFilter:
    """A space-efficient probabilistic data structure for membership testing.

    Guarantees no false negatives: if contains() returns False, the item was
    definitely not added. May produce false positives at the configured rate."""

    def __init__(self, capacity: int = 1000, false_positive_rate: float = 0.01) -> None:
        self._capacity = capacity
        self._fpr = false_positive_rate
        # Optimal bit array size: m = -n*ln(p) / (ln(2))^2
        self._size = max(1, int(-capacity * math.log(false_positive_rate) / (math.log(2) ** 2)))
        # Optimal number of hash functions: k = (m/n) * ln(2)
        self._num_hashes = max(1, int((self._size / capacity) * math.log(2)))
        self._bit_array = [False] * self._size
        self._count = 0

    def _hashes(self, item: str) -> List[int]:
        """Generate k hash positions using double hashing with MD5 and SHA1."""
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha1(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self._size for i in range(self._num_hashes)]

    def add(self, item: str) -> None:
        """Add an item to the Bloom filter."""
        for pos in self._hashes(item):
            self._bit_array[pos] = True
        self._count += 1

    def contains(self, item: str) -> bool:
        """Test membership. Returns True if the item may be in the set,
        False if it is definitely not in the set."""
        return all(self._bit_array[pos] for pos in self._hashes(item))

    @property
    def count(self) -> int:
        """Number of items added to the filter."""
        return self._count

    @property
    def false_positive_rate(self) -> float:
        """Configured false positive rate."""
        return self._fpr

    @property
    def size(self) -> int:
        """Size of the underlying bit array."""
        return self._size


class HyperLogLog:
    """Probabilistic cardinality estimator using the HyperLogLog algorithm.

    Estimates the number of distinct elements in a multiset using O(m) space
    where m = 2^precision, achieving a standard error of ~1.04/sqrt(m)."""

    def __init__(self, precision: int = 14) -> None:
        self._precision = min(max(precision, 4), 18)
        self._m = 1 << self._precision
        self._registers = [0] * self._m
        self._alpha = self._compute_alpha(self._m)

    @staticmethod
    def _compute_alpha(m: int) -> float:
        """Compute the bias correction constant alpha_m."""
        if m == 16:
            return 0.673
        elif m == 32:
            return 0.697
        elif m == 64:
            return 0.709
        else:
            return 0.7213 / (1 + 1.079 / m)

    def _hash(self, item: str) -> int:
        """Hash an item to a 64-bit integer."""
        return int(hashlib.sha256(item.encode()).hexdigest()[:16], 16)

    def add(self, item: str) -> None:
        """Add an item to the HyperLogLog."""
        h = self._hash(item)
        idx = h & (self._m - 1)  # First p bits as register index
        remaining = h >> self._precision
        # Count leading zeros + 1 in the remaining bits
        rho = 1
        for bit in range(64 - self._precision):
            if remaining & (1 << bit):
                break
            rho += 1
        self._registers[idx] = max(self._registers[idx], rho)

    def estimate(self) -> float:
        """Estimate the cardinality of the multiset."""
        # Raw HLL estimate
        indicator = sum(2.0 ** (-r) for r in self._registers)
        estimate = self._alpha * self._m * self._m / indicator

        # Small range correction
        if estimate <= 2.5 * self._m:
            zeros = self._registers.count(0)
            if zeros > 0:
                estimate = self._m * math.log(self._m / zeros)

        return estimate

    def merge(self, other: "HyperLogLog") -> "HyperLogLog":
        """Merge two HyperLogLog instances by taking element-wise max of registers."""
        if self._precision != other._precision:
            raise FizzBloomError(
                f"Cannot merge HLLs with different precisions: {self._precision} vs {other._precision}"
            )
        result = HyperLogLog(self._precision)
        result._registers = [max(a, b) for a, b in zip(self._registers, other._registers)]
        return result

    @property
    def precision(self) -> int:
        return self._precision


class CountMinSketch:
    """Frequency estimation data structure that never underestimates.

    Uses multiple hash functions and a 2D array of counters to provide
    approximate frequency counts with one-sided error (may overestimate)."""

    def __init__(self, width: int = 1000, depth: int = 5) -> None:
        self._width = width
        self._depth = depth
        self._table = [[0] * width for _ in range(depth)]
        self._total = 0

    def _hashes(self, item: str) -> List[int]:
        """Generate depth hash positions."""
        positions = []
        for i in range(self._depth):
            h = hashlib.sha256(f"{i}:{item}".encode()).hexdigest()
            positions.append(int(h, 16) % self._width)
        return positions

    def add(self, item: str, count: int = 1) -> None:
        """Add an item with the given count."""
        for row, col in enumerate(self._hashes(item)):
            self._table[row][col] += count
        self._total += count

    def estimate(self, item: str) -> int:
        """Estimate the frequency of an item. Never underestimates."""
        return min(
            self._table[row][col]
            for row, col in enumerate(self._hashes(item))
        )

    @property
    def total(self) -> int:
        """Total number of items added."""
        return self._total


class ProbabilisticRegistry:
    """Registry for managing named probabilistic data structures."""

    def __init__(self) -> None:
        self._structures: OrderedDict[str, Any] = OrderedDict()
        self._types: Dict[str, str] = {}

    def create_bloom_filter(self, name: str, capacity: int = 1000,
                            fpr: float = 0.01) -> BloomFilter:
        bf = BloomFilter(capacity, fpr)
        self._structures[name] = bf
        self._types[name] = "bloom_filter"
        return bf

    def create_hyperloglog(self, name: str, precision: int = 14) -> HyperLogLog:
        hll = HyperLogLog(precision)
        self._structures[name] = hll
        self._types[name] = "hyperloglog"
        return hll

    def create_count_min_sketch(self, name: str, width: int = 1000,
                                depth: int = 5) -> CountMinSketch:
        cms = CountMinSketch(width, depth)
        self._structures[name] = cms
        self._types[name] = "count_min_sketch"
        return cms

    def get(self, name: str) -> Any:
        s = self._structures.get(name)
        if s is None:
            raise FizzBloomNotFoundError(name)
        return s

    def list_structures(self) -> List[dict]:
        result = []
        for name, structure in self._structures.items():
            info = {"name": name, "type": self._types[name]}
            if isinstance(structure, BloomFilter):
                info["count"] = structure.count
                info["size"] = structure.size
            elif isinstance(structure, HyperLogLog):
                info["precision"] = structure.precision
                info["estimate"] = structure.estimate()
            elif isinstance(structure, CountMinSketch):
                info["total"] = structure.total
            result.append(info)
        return result


class FizzBloomDashboard:
    def __init__(self, registry: Optional[ProbabilisticRegistry] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._registry = registry
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzBloom Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZBLOOM_VERSION}"]
        if self._registry:
            structures = self._registry.list_structures()
            lines.append(f"  Structures: {len(structures)}")
            lines.append("-" * self._width)
            for s in structures[:15]:
                lines.append(f"  {s['name']:<25} [{s['type']}]")
        return "\n".join(lines)


class FizzBloomMiddleware(IMiddleware):
    def __init__(self, registry: Optional[ProbabilisticRegistry] = None,
                 dashboard: Optional[FizzBloomDashboard] = None) -> None:
        self._registry = registry
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzbloom"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzbloom_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[ProbabilisticRegistry, FizzBloomDashboard, FizzBloomMiddleware]:
    """Factory function that creates and wires the FizzBloom subsystem."""
    registry = ProbabilisticRegistry()
    # Create default structures for the FizzBuzz pipeline
    registry.create_bloom_filter("processed_numbers", capacity=10000, fpr=0.001)
    registry.create_hyperloglog("unique_classifications", precision=14)
    registry.create_count_min_sketch("classification_frequency", width=2000, depth=7)

    dashboard = FizzBloomDashboard(registry, dashboard_width)
    middleware = FizzBloomMiddleware(registry, dashboard)
    logger.info("FizzBloom initialized: %d structures", len(registry.list_structures()))
    return registry, dashboard, middleware

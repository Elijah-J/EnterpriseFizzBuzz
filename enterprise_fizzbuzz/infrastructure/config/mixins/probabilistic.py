"""FizzBloom Probabilistic Data Structures Properties"""

from __future__ import annotations

from typing import Any


class ProbabilisticConfigMixin:
    """Configuration properties for the probabilistic subsystem."""

    # ----------------------------------------------------------------
    # FizzBloom Probabilistic Data Structures Properties
    # ----------------------------------------------------------------

    @property
    def probabilistic_enabled(self) -> bool:
        """Whether the FizzBloom probabilistic analytics subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("enabled", False)

    @property
    def probabilistic_bloom_expected_elements(self) -> int:
        """Expected number of distinct elements for the Bloom filter."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("bloom", {}).get("expected_elements", 1000)

    @property
    def probabilistic_bloom_false_positive_rate(self) -> float:
        """Target false positive rate for the Bloom filter."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("bloom", {}).get("false_positive_rate", 0.01)

    @property
    def probabilistic_cms_width(self) -> int:
        """Number of counters per row in the Count-Min Sketch."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("count_min_sketch", {}).get("width", 2048)

    @property
    def probabilistic_cms_depth(self) -> int:
        """Number of hash function rows in the Count-Min Sketch."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("count_min_sketch", {}).get("depth", 5)

    @property
    def probabilistic_hll_precision(self) -> int:
        """HyperLogLog precision parameter p (register count = 2^p)."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("hyperloglog", {}).get("precision", 14)

    @property
    def probabilistic_tdigest_compression(self) -> int:
        """T-Digest compression parameter controlling centroid count."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("tdigest", {}).get("compression", 100)

    @property
    def probabilistic_dashboard_width(self) -> int:
        """Width of the FizzBloom ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("probabilistic", {}).get("dashboard", {}).get("width", 60)


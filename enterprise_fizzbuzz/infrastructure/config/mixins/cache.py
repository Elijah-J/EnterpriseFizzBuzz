"""Cache configuration properties"""

from __future__ import annotations

from typing import Any


class CacheConfigMixin:
    """Configuration properties for the cache subsystem."""

    # ----------------------------------------------------------------
    # Cache configuration properties
    # ----------------------------------------------------------------

    @property
    def cache_enabled(self) -> bool:
        """Whether the in-memory caching layer is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("enabled", False)

    @property
    def cache_max_size(self) -> int:
        """Maximum number of entries in the FizzBuzz result cache."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("max_size", 1024)

    @property
    def cache_ttl_seconds(self) -> float:
        """Time-to-live for cache entries in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("ttl_seconds", 3600.0)

    @property
    def cache_eviction_policy(self) -> str:
        """Eviction policy name: lru, lfu, fifo, or dramatic_random."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("eviction_policy", "lru")

    @property
    def cache_enable_coherence_protocol(self) -> bool:
        """Whether to enable MESI cache coherence state tracking."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("enable_coherence_protocol", True)

    @property
    def cache_enable_eulogies(self) -> bool:
        """Whether to generate commemorative eulogies for evicted cache entries."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("enable_eulogies", True)

    @property
    def cache_warming_enabled(self) -> bool:
        """Whether to pre-populate the cache on startup (defeats the purpose)."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("warming", {}).get("enabled", False)

    @property
    def cache_warming_range_start(self) -> int:
        """Start of the range to pre-populate in the cache."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("warming", {}).get("range_start", 1)

    @property
    def cache_warming_range_end(self) -> int:
        """End of the range to pre-populate in the cache."""
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("warming", {}).get("range_end", 100)


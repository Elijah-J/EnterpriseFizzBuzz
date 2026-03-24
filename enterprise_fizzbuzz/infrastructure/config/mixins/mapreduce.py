"""Mapreduce configuration properties."""

from __future__ import annotations

from typing import Any


class MapreduceConfigMixin:
    """Configuration properties for the mapreduce subsystem."""

    # ----------------------------------------------------------------
    # FizzReduce — MapReduce Framework
    # ----------------------------------------------------------------

    @property
    def mapreduce_enabled(self) -> bool:
        """Whether the FizzReduce MapReduce framework is active."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("enabled", False)

    @property
    def mapreduce_num_mappers(self) -> int:
        """Number of parallel mapper tasks for FizzReduce jobs."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("num_mappers", 4)

    @property
    def mapreduce_num_reducers(self) -> int:
        """Number of reducer partitions for FizzReduce jobs."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("num_reducers", 2)

    @property
    def mapreduce_speculative_threshold(self) -> float:
        """Speculative execution threshold multiplier (task_time > threshold * avg)."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("speculative_threshold", 1.5)

    @property
    def mapreduce_dashboard_width(self) -> int:
        """Dashboard width for the FizzReduce dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("mapreduce", {}).get("dashboard", {}).get("width", 60)


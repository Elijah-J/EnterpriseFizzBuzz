"""Fizzstream configuration properties."""

from __future__ import annotations

from typing import Any


class FizzstreamConfigMixin:
    """Configuration properties for the FizzStream subsystem."""

    # ----------------------------------------------------------------
    # FizzStream -- Distributed Stream Processing Engine
    # ----------------------------------------------------------------

    @property
    def fizzstream_enabled(self) -> bool:
        """Whether the FizzStream distributed stream processing engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("enabled", False)

    @property
    def fizzstream_parallelism(self) -> int:
        """Default operator parallelism for FizzStream pipelines."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("parallelism", 4)

    @property
    def fizzstream_max_parallelism(self) -> int:
        """Maximum parallelism / key group count for state redistribution."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("max_parallelism", 128)

    @property
    def fizzstream_checkpoint_interval_ms(self) -> int:
        """Checkpoint interval in milliseconds for Chandy-Lamport snapshots."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("checkpoint", {}).get("interval_ms", 60000)

    @property
    def fizzstream_state_backend(self) -> str:
        """State backend type (hashmap or rocksdb)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("state_backend", "hashmap")

    @property
    def fizzstream_watermark_interval_ms(self) -> int:
        """Watermark emission interval in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("watermark", {}).get("interval_ms", 200)

    @property
    def fizzstream_buffer_timeout_ms(self) -> int:
        """Buffer flush timeout in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("buffer", {}).get("timeout_ms", 100)

    @property
    def fizzstream_restart_strategy(self) -> str:
        """Restart strategy type (fixed, exponential, none)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("restart", {}).get("strategy", "fixed")

    @property
    def fizzstream_restart_max_attempts(self) -> int:
        """Maximum restart attempts before job failure."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("restart", {}).get("max_attempts", 3)

    @property
    def fizzstream_restart_delay_ms(self) -> int:
        """Delay between restart attempts in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("restart", {}).get("delay_ms", 10000)

    @property
    def fizzstream_checkpoint_retention(self) -> int:
        """Number of completed checkpoints to retain."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("checkpoint", {}).get("retention", 3)

    @property
    def fizzstream_backpressure_high_pct(self) -> float:
        """Backpressure high watermark threshold percentage."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzstream", {}).get("backpressure", {}).get("high_watermark_pct", 0.80))

    @property
    def fizzstream_backpressure_low_pct(self) -> float:
        """Backpressure low watermark threshold percentage."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzstream", {}).get("backpressure", {}).get("low_watermark_pct", 0.50))

    @property
    def fizzstream_autoscale_enabled(self) -> bool:
        """Whether auto-scaling is enabled for stream operators."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("autoscale", {}).get("enabled", False)

    @property
    def fizzstream_dashboard_width(self) -> int:
        """ASCII dashboard width for FizzStream pipeline visualization."""
        self._ensure_loaded()
        return self._raw_config.get("fizzstream", {}).get("dashboard", {}).get("width", 76)

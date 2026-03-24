"""Chaos configuration properties."""

from __future__ import annotations

from typing import Any


class ChaosConfigMixin:
    """Configuration properties for the chaos subsystem."""

    @property
    def chaos_enabled(self) -> bool:
        """Whether the Chaos Engineering subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("enabled", False)

    @property
    def chaos_level(self) -> int:
        """Chaos severity level (1-5). 1 = gentle breeze, 5 = category 5 hurricane."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("level", 1)

    @property
    def chaos_fault_types(self) -> list[str]:
        """List of armed fault type names."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("fault_types", [
            "RESULT_CORRUPTION",
            "LATENCY_INJECTION",
            "EXCEPTION_INJECTION",
            "RULE_ENGINE_FAILURE",
            "CONFIDENCE_MANIPULATION",
        ])

    @property
    def chaos_latency_min_ms(self) -> int:
        """Minimum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("latency", {}).get("min_ms", 10)

    @property
    def chaos_latency_max_ms(self) -> int:
        """Maximum injected latency in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("latency", {}).get("max_ms", 500)

    @property
    def chaos_seed(self) -> int | None:
        """Random seed for reproducible chaos. None = true entropy."""
        self._ensure_loaded()
        return self._raw_config.get("chaos", {}).get("seed", None)


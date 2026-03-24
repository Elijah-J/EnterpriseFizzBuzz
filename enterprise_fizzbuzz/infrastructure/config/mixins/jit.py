"""FizzJIT — Runtime Code Generation properties"""

from __future__ import annotations

from typing import Any


class JitConfigMixin:
    """Configuration properties for the jit subsystem."""

    # ------------------------------------------------------------------
    # FizzJIT — Runtime Code Generation properties
    # ------------------------------------------------------------------

    @property
    def jit_enabled(self) -> bool:
        """Whether the FizzJIT trace-based compiler is active."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enabled", False)

    @property
    def jit_threshold(self) -> int:
        """Number of range evaluations before JIT compilation triggers."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("threshold", 3)

    @property
    def jit_cache_size(self) -> int:
        """Maximum number of compiled traces in the LRU cache."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("cache_size", 64)

    @property
    def jit_enable_constant_folding(self) -> bool:
        """Whether constant folding optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_constant_folding", True)

    @property
    def jit_enable_dce(self) -> bool:
        """Whether dead code elimination optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_dce", True)

    @property
    def jit_enable_guard_hoisting(self) -> bool:
        """Whether guard hoisting optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_guard_hoisting", True)

    @property
    def jit_enable_type_specialization(self) -> bool:
        """Whether type specialization optimization pass is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("enable_type_specialization", True)

    @property
    def jit_dashboard_width(self) -> int:
        """Dashboard width for the JIT compiler dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("jit", {}).get("dashboard", {}).get("width", 60)


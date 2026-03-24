"""Dependent Type System & Curry-Howard Proof Engine properties"""

from __future__ import annotations

from typing import Any


class DependentTypesConfigMixin:
    """Configuration properties for the dependent types subsystem."""

    # ------------------------------------------------------------------
    # Dependent Type System & Curry-Howard Proof Engine properties
    # ------------------------------------------------------------------

    @property
    def dependent_types_enabled(self) -> bool:
        """Whether the Dependent Type System is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("enabled", False)

    @property
    def dependent_types_max_beta_reductions(self) -> int:
        """Safety limit for beta-normalization steps."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("max_beta_reductions", 1000)

    @property
    def dependent_types_max_unification_depth(self) -> int:
        """Maximum depth for first-order unification."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("max_unification_depth", 100)

    @property
    def dependent_types_enable_proof_cache(self) -> bool:
        """Whether to cache proof terms."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("enable_proof_cache", True)

    @property
    def dependent_types_proof_cache_size(self) -> int:
        """Maximum entries in the proof cache."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("proof_cache_size", 4096)

    @property
    def dependent_types_enable_type_inference(self) -> bool:
        """Whether bidirectional type inference is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("enable_type_inference", True)

    @property
    def dependent_types_strict_mode(self) -> bool:
        """Whether strict mode (no auto tactic) is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("strict_mode", False)

    @property
    def dependent_types_dashboard_width(self) -> int:
        """Dashboard width for the type system dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("width", 60)

    @property
    def dependent_types_dashboard_show_curry_howard(self) -> bool:
        """Whether to show the Curry-Howard correspondence table."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("show_curry_howard", True)

    @property
    def dependent_types_dashboard_show_proof_tree(self) -> bool:
        """Whether to show proof tree structure."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("show_proof_tree", True)

    @property
    def dependent_types_dashboard_show_complexity_index(self) -> bool:
        """Whether to show the Proof Complexity Index."""
        self._ensure_loaded()
        return self._raw_config.get("dependent_types", {}).get("dashboard", {}).get("show_complexity_index", True)


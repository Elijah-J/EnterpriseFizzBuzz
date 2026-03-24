"""Feature Flags configuration properties."""

from __future__ import annotations

from typing import Any


class FeatureFlagsConfigMixin:
    """Configuration properties for the feature flags subsystem."""

    @property
    def feature_flags_enabled(self) -> bool:
        """Whether the Feature Flags subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("enabled", False)

    @property
    def feature_flags_default_lifecycle(self) -> str:
        """Default lifecycle state for newly created flags."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("default_lifecycle", "ACTIVE")

    @property
    def feature_flags_log_evaluations(self) -> bool:
        """Whether to log every flag evaluation for audit compliance."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("log_evaluations", True)

    @property
    def feature_flags_strict_dependencies(self) -> bool:
        """Whether to enforce dependency graph constraints."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("strict_dependencies", True)

    @property
    def feature_flags_predefined(self) -> dict[str, Any]:
        """Predefined feature flag definitions from config."""
        self._ensure_loaded()
        return self._raw_config.get("feature_flags", {}).get("predefined_flags", {})


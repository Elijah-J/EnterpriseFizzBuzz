"""Fizzdeploy configuration properties."""

from __future__ import annotations

from typing import Any


class FizzdeployConfigMixin:
    """Configuration properties for the fizzdeploy subsystem."""

    @property
    def fizzdeploy_enabled(self) -> bool:
        """Whether the FizzDeploy deployment pipeline is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdeploy", {}).get("enabled", False)

    @property
    def fizzdeploy_default_strategy(self) -> str:
        """Default deployment strategy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdeploy", {}).get("default_strategy", "rolling_update")

    @property
    def fizzdeploy_pipeline_timeout(self) -> float:
        """Pipeline execution timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("pipeline_timeout", 600.0))

    @property
    def fizzdeploy_reconcile_interval(self) -> float:
        """GitOps reconciliation loop interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("reconcile_interval", 30.0))

    @property
    def fizzdeploy_sync_strategy(self) -> str:
        """Default GitOps sync strategy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdeploy", {}).get("sync_strategy", "auto")

    @property
    def fizzdeploy_revision_history_depth(self) -> int:
        """Maximum deployment revisions retained per deployment."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdeploy", {}).get("revision_history_depth", 10))

    @property
    def fizzdeploy_cognitive_load_threshold(self) -> float:
        """NASA-TLX cognitive load threshold for deployment gating."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("cognitive_load_threshold", 70.0))

    @property
    def fizzdeploy_max_surge(self) -> float:
        """Default max surge for rolling update strategy (fraction 0.0-1.0)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("rolling_update", {}).get("max_surge", 0.25))

    @property
    def fizzdeploy_max_unavailable(self) -> float:
        """Default max unavailable for rolling update strategy (fraction 0.0-1.0)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzdeploy", {}).get("rolling_update", {}).get("max_unavailable", 0.25))

    @property
    def fizzdeploy_dashboard_width(self) -> int:
        """Width of the FizzDeploy ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdeploy", {}).get("dashboard", {}).get("width", 72))


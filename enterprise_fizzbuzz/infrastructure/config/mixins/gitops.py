"""GitOps Configuration-as-Code Simulator properties"""

from __future__ import annotations

from typing import Any


class GitopsConfigMixin:
    """Configuration properties for the gitops subsystem."""

    # ----------------------------------------------------------------
    # GitOps Configuration-as-Code Simulator properties
    # ----------------------------------------------------------------

    @property
    def gitops_enabled(self) -> bool:
        """Whether the GitOps Configuration-as-Code Simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("enabled", False)

    @property
    def gitops_default_branch(self) -> str:
        """The default (trunk) branch name."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("default_branch", "main")

    @property
    def gitops_auto_commit_on_load(self) -> bool:
        """Whether to create an initial commit when configuration is loaded."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("auto_commit_on_load", True)

    @property
    def gitops_policy_enforcement(self) -> bool:
        """Whether policy rules are enforced on configuration changes."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("policy_enforcement", True)

    @property
    def gitops_dry_run_range_start(self) -> int:
        """Start of FizzBuzz range for dry-run simulation."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("dry_run_range_start", 1)

    @property
    def gitops_dry_run_range_end(self) -> int:
        """End of FizzBuzz range for dry-run simulation."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("dry_run_range_end", 30)

    @property
    def gitops_reconciliation_on_drift(self) -> bool:
        """Whether to auto-reconcile when drift is detected."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("reconciliation_on_drift", True)

    @property
    def gitops_max_commit_history(self) -> int:
        """Maximum commits to retain in the log."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("max_commit_history", 100)

    @property
    def gitops_approval_mode(self) -> str:
        """Approval mode: 'single_operator' or 'committee'."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("approval_mode", "single_operator")

    @property
    def gitops_blast_radius_subsystems(self) -> list[str]:
        """Subsystems tracked for blast radius estimation."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("blast_radius_subsystems", [
            "rules", "engine", "output", "range", "middleware",
            "circuit_breaker", "cache", "feature_flags", "chaos",
        ])

    @property
    def gitops_dashboard_width(self) -> int:
        """ASCII dashboard width for GitOps dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("gitops", {}).get("dashboard", {}).get("width", 60)


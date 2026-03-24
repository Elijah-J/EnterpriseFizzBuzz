"""Approval configuration properties."""

from __future__ import annotations

from typing import Any


class ApprovalConfigMixin:
    """Configuration properties for the approval subsystem."""

    @property
    def approval_enabled(self) -> bool:
        """Whether the FizzApproval workflow engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_approval", {}).get("enabled", False)

    @property
    def approval_default_change_type(self) -> str:
        """Default ITIL change type for approval requests."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_approval", {}).get("default_change_type", "NORMAL")

    @property
    def approval_default_timeout(self) -> float:
        """Default approval request timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_approval", {}).get("default_timeout", 300.0))

    @property
    def approval_required_eyes(self) -> int:
        """Number of independent reviewers for four-eyes principle."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_approval", {}).get("required_eyes", 2))

    @property
    def approval_max_delegation_depth(self) -> int:
        """Maximum delegation chain depth."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_approval", {}).get("max_delegation_depth", 10))

    @property
    def approval_quorum_size(self) -> int:
        """Minimum CAB members for quorum."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_approval", {}).get("quorum_size", 1))

    @property
    def approval_dashboard_width(self) -> int:
        """Width of the FizzApproval ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_approval", {}).get("dashboard", {}).get("width", 72))


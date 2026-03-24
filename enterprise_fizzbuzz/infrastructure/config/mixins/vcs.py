"""Vcs configuration properties."""

from __future__ import annotations

from typing import Any


class VcsConfigMixin:
    """Configuration properties for the vcs subsystem."""

    @property
    def vcs_enabled(self) -> bool:
        """Whether the FizzGit version control system is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("vcs", {}).get("enabled", False)

    @property
    def vcs_auto_commit(self) -> bool:
        """Whether VCS auto-commit is enabled for evaluation batches."""
        self._ensure_loaded()
        return self._raw_config.get("vcs", {}).get("auto_commit", True)

    @property
    def vcs_author(self) -> str:
        """Default author for VCS commits."""
        self._ensure_loaded()
        return self._raw_config.get("vcs", {}).get("author", "FizzGitBot")

    @property
    def vcs_dashboard_width(self) -> int:
        """Width of the FizzGit ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("vcs", {}).get("dashboard", {}).get("width", 60)


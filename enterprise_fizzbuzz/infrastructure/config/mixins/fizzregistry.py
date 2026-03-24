"""Fizzregistry configuration properties."""

from __future__ import annotations

from typing import Any


class FizzregistryConfigMixin:
    """Configuration properties for the fizzregistry subsystem."""

    @property
    def fizzregistry_enabled(self) -> bool:
        """Whether the FizzRegistry image registry is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzregistry", {}).get("enabled", False)

    @property
    def fizzregistry_max_blobs(self) -> int:
        """Maximum blobs in the content-addressable store."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzregistry", {}).get("max_blobs", 4096))

    @property
    def fizzregistry_max_repos(self) -> int:
        """Maximum repositories in the registry."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzregistry", {}).get("max_repos", 256))

    @property
    def fizzregistry_max_tags(self) -> int:
        """Maximum tags per repository."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzregistry", {}).get("max_tags", 1024))

    @property
    def fizzregistry_gc_grace_period(self) -> float:
        """GC grace period in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzregistry", {}).get("gc_grace_period", 86400.0))

    @property
    def fizzregistry_dashboard_width(self) -> int:
        """Width of the FizzRegistry ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzregistry", {}).get("dashboard", {}).get("width", 72))

    # ── FizzOverlay: Copy-on-Write Union Filesystem ──────────


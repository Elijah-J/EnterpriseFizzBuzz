"""Org configuration properties."""

from __future__ import annotations

from typing import Any


class OrgConfigMixin:
    """Configuration properties for the org subsystem."""

    @property
    def org_enabled(self) -> bool:
        """Whether the FizzOrg organizational hierarchy engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_org", {}).get("enabled", False)

    @property
    def org_operator(self) -> str:
        """The sole operator occupying every position in the org chart."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_org", {}).get("operator", "Bob McFizzington")

    @property
    def org_target_headcount(self) -> int:
        """Target organizational headcount."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_org", {}).get("target_headcount", 42))

    @property
    def org_dashboard_width(self) -> int:
        """Width of the FizzOrg ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_org", {}).get("dashboard", {}).get("width", 72))

    # ── FizzNS: Linux Namespace Isolation ───────────────────────


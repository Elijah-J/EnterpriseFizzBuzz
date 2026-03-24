"""Fizzpm configuration properties."""

from __future__ import annotations

from typing import Any


class FizzpmConfigMixin:
    """Configuration properties for the fizzpm subsystem."""

    # ----------------------------------------------------------------
    # FizzPM Package Manager
    # ----------------------------------------------------------------

    @property
    def fizzpm_enabled(self) -> bool:
        """Whether the FizzPM Package Manager is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("enabled", False)

    @property
    def fizzpm_audit_on_install(self) -> bool:
        """Whether to automatically run vulnerability scan after install."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("audit_on_install", True)

    @property
    def fizzpm_default_packages(self) -> list[str]:
        """Packages auto-installed when FizzPM is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("default_packages", ["fizzbuzz-core"])

    @property
    def fizzpm_lockfile_path(self) -> str:
        """Path to the deterministic lockfile."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("lockfile_path", "fizzpm.lock")

    @property
    def fizzpm_registry_mirror(self) -> str:
        """The fictional FizzPM registry URL."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("registry_mirror", "https://registry.fizzpm.io")

    @property
    def fizzpm_dashboard_width(self) -> int:
        """Dashboard width for the FizzPM dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpm", {}).get("dashboard", {}).get("width", 60)


"""FizzSystemd configuration properties."""

from __future__ import annotations

from typing import Any


class FizzsystemdConfigMixin:
    """Configuration properties for the FizzSystemd service manager subsystem."""

    @property
    def fizzsystemd_enabled(self) -> bool:
        """Whether the FizzSystemd service manager is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("enabled", False)

    @property
    def fizzsystemd_unit_dir(self) -> str:
        """Unit file directory."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("unit_dir", "/etc/fizzsystemd/")

    @property
    def fizzsystemd_default_target(self) -> str:
        """Default boot target."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("default_target", "fizzbuzz.target")

    @property
    def fizzsystemd_log_level(self) -> str:
        """Journal minimum priority level."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("log_level", "info")

    @property
    def fizzsystemd_log_target(self) -> str:
        """Log destination."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("log_target", "journal")

    @property
    def fizzsystemd_watchdog_sec(self) -> float:
        """Default watchdog timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsystemd", {}).get("watchdog_sec", 0.0))

    @property
    def fizzsystemd_default_restart_policy(self) -> str:
        """Default restart policy for services."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("default_restart_policy", "no")

    @property
    def fizzsystemd_crash_shell(self) -> bool:
        """Drop to emergency target on failure."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("crash_shell", False)

    @property
    def fizzsystemd_confirm_spawn(self) -> bool:
        """Prompt before starting each service."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("confirm_spawn", False)

    @property
    def fizzsystemd_show_status(self) -> bool:
        """Display startup progress."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("show_status", False)

    @property
    def fizzsystemd_dump_core(self) -> bool:
        """Enable core dump collection."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("dump_core", False)

    @property
    def fizzsystemd_journal_max_size(self) -> int:
        """Maximum journal size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsystemd", {}).get("journal", {}).get("max_size", 134217728))

    @property
    def fizzsystemd_journal_max_retention(self) -> float:
        """Maximum journal retention in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsystemd", {}).get("journal", {}).get("max_retention_sec", 2592000.0))

    @property
    def fizzsystemd_journal_seal(self) -> bool:
        """Enable forward-secure sealing."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsystemd", {}).get("journal", {}).get("seal", False)

    @property
    def fizzsystemd_inhibit_delay(self) -> float:
        """Maximum inhibitor lock delay in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsystemd", {}).get("inhibit_delay_max_sec", 5.0))

    @property
    def fizzsystemd_dashboard_width(self) -> int:
        """Width of the FizzSystemd ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsystemd", {}).get("dashboard", {}).get("width", 76))

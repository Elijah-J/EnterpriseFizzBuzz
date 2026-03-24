"""Hot-Reload Configuration Properties"""

from __future__ import annotations

from typing import Any


class HotReloadConfigMixin:
    """Configuration properties for the hot reload subsystem."""

    # ----------------------------------------------------------------
    # Hot-Reload Configuration Properties
    # ----------------------------------------------------------------

    @property
    def hot_reload_enabled(self) -> bool:
        """Whether the configuration hot-reload subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("enabled", False)

    @property
    def hot_reload_poll_interval_seconds(self) -> float:
        """Polling interval for config file change detection."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("poll_interval_seconds", 2.0)

    @property
    def hot_reload_raft_heartbeat_interval_ms(self) -> int:
        """Raft heartbeat interval in milliseconds (to 0 followers)."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("raft_heartbeat_interval_ms", 150)

    @property
    def hot_reload_raft_election_timeout_ms(self) -> int:
        """Raft election timeout in milliseconds (always wins immediately)."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("raft_election_timeout_ms", 300)

    @property
    def hot_reload_max_rollback_history(self) -> int:
        """Number of previous configs to retain for rollback."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("max_rollback_history", 10)

    @property
    def hot_reload_validate_before_apply(self) -> bool:
        """Whether to validate config changes before applying them."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("validate_before_apply", True)

    @property
    def hot_reload_log_diffs(self) -> bool:
        """Whether to log configuration diffs on reload."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("log_diffs", True)

    @property
    def hot_reload_subsystem_reload_timeout_ms(self) -> int:
        """Timeout for each subsystem to accept new config."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("subsystem_reload_timeout_ms", 5000)

    @property
    def hot_reload_dashboard_width(self) -> int:
        """ASCII dashboard width for hot-reload status display."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("dashboard", {}).get("width", 60)

    @property
    def hot_reload_dashboard_show_raft_details(self) -> bool:
        """Whether to show Raft consensus details in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("hot_reload", {}).get("dashboard", {}).get("show_raft_details", True)


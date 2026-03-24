"""Replication configuration properties."""

from __future__ import annotations

from typing import Any


class ReplicationConfigMixin:
    """Configuration properties for the replication subsystem."""

    @property
    def replication_enabled(self) -> bool:
        """Whether database replication is enabled via configuration."""
        self._ensure_loaded()
        return self._raw_config.get("replication", {}).get("enabled", False)

    @property
    def replication_mode(self) -> str:
        """Replication mode: sync, async, or quorum."""
        self._ensure_loaded()
        return self._raw_config.get("replication", {}).get("mode", "async")

    @property
    def replication_replica_count(self) -> int:
        """Number of replica nodes in the replica set."""
        self._ensure_loaded()
        return self._raw_config.get("replication", {}).get("replica_count", 2)

    @property
    def replication_heartbeat_timeout(self) -> float:
        """Heartbeat timeout in seconds for failover detection."""
        self._ensure_loaded()
        return self._raw_config.get("replication", {}).get("heartbeat_timeout_s", 5.0)

    @property
    def replication_lag_threshold(self) -> int:
        """Replication lag alert threshold in WAL records."""
        self._ensure_loaded()
        return self._raw_config.get("replication", {}).get("lag_threshold", 10)

    @property
    def replication_dashboard_width(self) -> int:
        """Width of the replication ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("replication", {}).get("dashboard", {}).get("width", 72)


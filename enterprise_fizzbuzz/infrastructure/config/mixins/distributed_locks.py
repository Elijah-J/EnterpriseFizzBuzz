"""Distributed Lock Manager (FizzLock) configuration properties"""

from __future__ import annotations

from typing import Any


class DistributedLocksConfigMixin:
    """Configuration properties for the distributed locks subsystem."""

    # ----------------------------------------------------------------
    # Distributed Lock Manager (FizzLock) configuration properties
    # ----------------------------------------------------------------

    @property
    def distributed_locks_enabled(self) -> bool:
        """Whether the Distributed Lock Manager is active."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("enabled", False)

    @property
    def distributed_locks_policy(self) -> str:
        """Deadlock prevention policy: 'wait-die' or 'wound-wait'."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("policy", "wait-die")

    @property
    def distributed_locks_lease_duration(self) -> float:
        """Lock lease time-to-live in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("lease_duration_s", 30.0)

    @property
    def distributed_locks_grace_period(self) -> float:
        """Grace period before forced lease revocation in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("grace_period_s", 5.0)

    @property
    def distributed_locks_check_interval(self) -> float:
        """Lease reaper background check interval in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("check_interval_s", 1.0)

    @property
    def distributed_locks_acquisition_timeout(self) -> float:
        """Maximum time to wait for a lock acquisition in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("acquisition_timeout_s", 5.0)

    @property
    def distributed_locks_hot_lock_threshold_ms(self) -> float:
        """Contention threshold in milliseconds for hot-lock detection."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("hot_lock_threshold_ms", 10.0)

    @property
    def distributed_locks_dashboard_width(self) -> int:
        """Dashboard width for the FizzLock dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("distributed_locks", {}).get("dashboard", {}).get("width", 60)


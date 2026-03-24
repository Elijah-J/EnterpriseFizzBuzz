"""Disaster Recovery & Backup/Restore properties"""

from __future__ import annotations

from typing import Any


class DrConfigMixin:
    """Configuration properties for the dr subsystem."""

    # ----------------------------------------------------------------
    # Disaster Recovery & Backup/Restore properties
    # ----------------------------------------------------------------

    @property
    def dr_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("enabled", False)

    @property
    def dr_wal_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("enabled", True)

    @property
    def dr_wal_checksum_algorithm(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("checksum_algorithm", "sha256")

    @property
    def dr_wal_max_entries(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("max_entries", 10000)

    @property
    def dr_wal_verify_on_read(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("wal", {}).get("verify_on_read", True)

    @property
    def dr_backup_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("backup", {}).get("enabled", True)

    @property
    def dr_backup_max_snapshots(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("backup", {}).get("max_snapshots", 50)

    @property
    def dr_backup_auto_snapshot_interval(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("backup", {}).get("auto_snapshot_interval", 10)

    @property
    def dr_pitr_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("pitr", {}).get("enabled", True)

    @property
    def dr_pitr_granularity_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("pitr", {}).get("granularity_ms", 1)

    @property
    def dr_pitr_max_recovery_window_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("pitr", {}).get("max_recovery_window_ms", 5000)

    @property
    def dr_retention_hourly(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("hourly", 24)

    @property
    def dr_retention_daily(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("daily", 7)

    @property
    def dr_retention_weekly(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("weekly", 4)

    @property
    def dr_retention_monthly(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("retention", {}).get("monthly", 12)

    @property
    def dr_drill_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("enabled", True)

    @property
    def dr_drill_auto_drill(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("auto_drill", False)

    @property
    def dr_drill_rto_target_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("rto_target_ms", 100.0)

    @property
    def dr_drill_rpo_target_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("drill", {}).get("rpo_target_ms", 50.0)

    @property
    def dr_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("disaster_recovery", {}).get("dashboard", {}).get("width", 60)


"""Feature descriptor for the Disaster Recovery & Backup/Restore subsystem."""

from __future__ import annotations

import copy
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class DisasterRecoveryFeature(FeatureDescriptor):
    name = "disaster_recovery"
    description = "Write-ahead log, snapshots, point-in-time recovery, and DR drills (all in RAM)"
    middleware_priority = 82
    cli_flags = [
        ("--dr", {"action": "store_true", "default": False,
                  "help": "Enable Disaster Recovery with WAL, snapshots, and PITR (all in RAM, naturally)"}),
        ("--backup", {"action": "store_true", "default": False,
                      "help": "Create a manual backup of the current state after execution"}),
        ("--backup-list", {"action": "store_true", "default": False,
                           "help": "Display all backups in the in-memory vault after execution"}),
        ("--restore", {"action": "store_true", "default": False,
                       "help": "Restore the latest backup before execution (proves recovery works)"}),
        ("--dr-drill", {"action": "store_true", "default": False,
                        "help": "Run a DR drill: destroy state, recover, measure RTO/RPO (all in RAM)"}),
        ("--dr-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the Disaster Recovery ASCII dashboard after execution"}),
        ("--retention-status", {"action": "store_true", "default": False,
                                "help": "Display the backup retention policy status (24h/7d/4w/12m for a <1s process)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "dr", False),
            getattr(args, "backup", False),
            getattr(args, "backup_list", False),
            getattr(args, "restore", False),
            getattr(args, "dr_drill", False),
            getattr(args, "dr_dashboard", False),
            getattr(args, "retention_status", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.disaster_recovery import DRSystem

        dr_system = DRSystem(
            wal_max_entries=config.dr_wal_max_entries,
            wal_verify_on_read=config.dr_wal_verify_on_read,
            backup_max_snapshots=config.dr_backup_max_snapshots,
            auto_snapshot_interval=config.dr_backup_auto_snapshot_interval,
            retention_hourly=config.dr_retention_hourly,
            retention_daily=config.dr_retention_daily,
            retention_weekly=config.dr_retention_weekly,
            retention_monthly=config.dr_retention_monthly,
            rto_target_ms=config.dr_drill_rto_target_ms,
            rpo_target_ms=config.dr_drill_rpo_target_ms,
            dashboard_width=config.dr_dashboard_width,
            event_bus=event_bus,
        )
        dr_middleware = dr_system.create_middleware()

        return dr_system, dr_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        from enterprise_fizzbuzz.infrastructure.disaster_recovery import RecoveryDashboard

        parts = []

        if getattr(args, "backup", False) and middleware is not None:
            middleware.create_backup()

        if getattr(args, "restore", False) and hasattr(middleware, "_dr_system"):
            dr_system = middleware._dr_system
            restored = dr_system.restore_latest()
            if restored:
                parts.append(
                    f"\n  Restored {len(restored)} entries from latest backup."
                    f"\n  (This data was already in RAM. You're welcome.)\n"
                )
            else:
                parts.append("\n  No backups available to restore. The void is empty.\n")

        if getattr(args, "dr_drill", False):
            drill_state = copy.deepcopy(middleware.state) if middleware.state else {"dummy": "data"}
            dr_system = middleware._dr_system if hasattr(middleware, "_dr_system") else None
            if dr_system is not None:
                from enterprise_fizzbuzz.infrastructure.disaster_recovery import RecoveryDashboard as RD
                drill_result = dr_system.run_drill(drill_state)
                parts.append(RD.render_drill_report(drill_result, width=60))

        if getattr(args, "backup_list", False) and hasattr(middleware, "_dr_system"):
            parts.append(middleware._dr_system.render_backup_list())

        if getattr(args, "dr_dashboard", False) and hasattr(middleware, "_dr_system"):
            parts.append(middleware._dr_system.render_dashboard())

        if getattr(args, "retention_status", False) and hasattr(middleware, "_dr_system"):
            parts.append(middleware._dr_system.render_retention_status())

        return "\n".join(parts) if parts else None

"""Feature descriptor for the FizzBackup disaster recovery system."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzBackupFeature(FeatureDescriptor):
    name = "fizzbackup"
    description = "Disaster recovery with full/incremental/differential backups, PITR, and GFS retention"
    middleware_priority = 138
    cli_flags = [
        ("--fizzbackup", {"action": "store_true", "default": False, "help": "Enable FizzBackup"}),
        ("--fizzbackup-create", {"type": str, "default": None, "help": "Create backup (full/incremental/differential)"}),
        ("--fizzbackup-restore", {"type": str, "default": None, "help": "Restore from backup ID"}),
        ("--fizzbackup-list", {"action": "store_true", "default": False, "help": "List backups"}),
        ("--fizzbackup-verify", {"type": str, "default": None, "help": "Verify backup integrity"}),
        ("--fizzbackup-retention", {"action": "store_true", "default": False, "help": "Show retention policy"}),
        ("--fizzbackup-pitr", {"type": str, "default": None, "help": "Point-in-time recovery (ISO timestamp)"}),
        ("--fizzbackup-stats", {"action": "store_true", "default": False, "help": "Display backup statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzbackup", False), getattr(args, "fizzbackup_list", False),
                    getattr(args, "fizzbackup_stats", False), getattr(args, "fizzbackup_create", None)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzbackup import FizzBackupMiddleware, create_fizzbackup_subsystem
        engine, dashboard, mw = create_fizzbackup_subsystem(
            retention_days=config.fizzbackup_retention_days,
            encryption=config.fizzbackup_encryption,
            dashboard_width=config.fizzbackup_dashboard_width,
        )
        return engine, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzbackup_list", False): parts.append(middleware.render_list())
        if getattr(args, "fizzbackup_stats", False): parts.append(middleware.render_stats())
        if getattr(args, "fizzbackup", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

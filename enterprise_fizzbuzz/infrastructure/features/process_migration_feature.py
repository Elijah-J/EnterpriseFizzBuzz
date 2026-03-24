"""Feature descriptor for FizzMigrate live process migration."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ProcessMigrationFeature(FeatureDescriptor):
    name = "process_migration"
    description = "Live process migration with checkpoint/restore for the evaluation pipeline"
    middleware_priority = 133
    cli_flags = [
        ("--live-migrate", {"action": "store_true", "default": False,
                            "help": "Enable live process migration with checkpoint/restore for the evaluation pipeline"}),
        ("--live-migrate-strategy", {"choices": ["pre-copy", "post-copy", "stop-and-copy"],
                                     "default": "pre-copy",
                                     "help": "Migration strategy: pre-copy (iterative dirty page transfer), "
                                             "post-copy (demand-fault), or stop-and-copy (default: pre-copy)"}),
        ("--live-migrate-checkpoint", {"type": str, "metavar": "FILE", "default": None,
                                       "help": "Path to save/load the migration checkpoint image (JSON with SHA-256 integrity)"}),
        ("--live-migrate-dashboard", {"action": "store_true", "default": False,
                                      "help": "Display the FizzMigrate ASCII dashboard with transfer progress, dirty pages, and downtime"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "live_migrate", False),
            getattr(args, "live_migrate_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.process_migration import (
            MigrationStrategy,
            create_migration_subsystem,
        )

        strategy = MigrationStrategy(getattr(args, "live_migrate_strategy", "pre-copy"))

        orchestrator, middleware = create_migration_subsystem(
            strategy=strategy,
            checkpoint_file=getattr(args, "live_migrate_checkpoint", None),
            checkpoint_interval=config.get_raw("migration.checkpoint_interval", 10) or 10,
            enable_dashboard=getattr(args, "live_migrate_dashboard", False),
        )

        return orchestrator, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        from enterprise_fizzbuzz.infrastructure.process_migration import MigrationStrategy
        strategy = MigrationStrategy(getattr(args, "live_migrate_strategy", "pre-copy"))
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZMIGRATE: LIVE PROCESS MIGRATION ENABLED             |\n"
            f"  |   Strategy: {strategy.value.upper():<45s}|\n"
            "  |   Checkpoint/Restore with SHA-256 integrity.            |\n"
            "  |   Pre-copy iterative dirty page convergence.            |\n"
            "  |   Migration time exceeds computation time by design.    |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        from enterprise_fizzbuzz.infrastructure.process_migration import (
            MigrationDashboard as ProcessMigrationDashboard,
        )

        parts = []

        # The orchestrator is stored as the service (first element of create tuple)
        # but render receives the middleware. We need the orchestrator for dashboard.
        # The middleware tracks eval_count and checkpoints_taken.
        if getattr(args, "live_migrate", False):
            eval_count = getattr(middleware, "eval_count", 0)
            checkpoints = getattr(middleware, "checkpoints_taken", 0)
            parts.append(
                f"  FizzMigrate: {eval_count} evaluations, "
                f"{checkpoints} checkpoints captured"
            )

        if getattr(args, "live_migrate_dashboard", False):
            last_metrics = getattr(middleware, "last_metrics", None)
            if last_metrics is not None:
                parts.append(ProcessMigrationDashboard.render(last_metrics))
            else:
                parts.append("  FizzMigrate: No migration metrics available.")

        return "\n".join(parts) if parts else None

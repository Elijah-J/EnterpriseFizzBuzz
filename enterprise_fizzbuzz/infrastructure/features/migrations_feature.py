"""Feature descriptor for the Database Migration Framework subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class MigrationsFeature(FeatureDescriptor):
    name = "migrations"
    description = "Database migration framework with ephemeral in-memory schema, seed data, and rollback"
    middleware_priority = 0
    cli_flags = [
        ("--migrate", {"action": "store_true", "default": False,
                       "help": "Apply all pending database migrations to the in-memory schema (it won't persist)"}),
        ("--migrate-status", {"action": "store_true", "default": False,
                              "help": "Display the migration status dashboard for the ephemeral database"}),
        ("--migrate-rollback", {"type": int, "nargs": "?", "const": 1, "default": None,
                                "metavar": "N",
                                "help": "Roll back the last N migrations (default: 1)"}),
        ("--migrate-seed", {"action": "store_true", "default": False,
                            "help": "Generate FizzBuzz seed data using the FizzBuzz engine (the ouroboros)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "migrate", False),
            getattr(args, "migrate_status", False),
            getattr(args, "migrate_rollback", None) is not None,
            getattr(args, "migrate_seed", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return self.is_enabled(args)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.migrations import (
            MigrationDashboard,
            MigrationRegistry,
            MigrationRunner,
            SchemaManager,
            SchemaVisualizer,
            SeedDataGenerator,
            _register_builtin_migrations,
        )

        MigrationRegistry.reset()
        _register_builtin_migrations()

        migration_schema = SchemaManager(log_fake_sql=config.migrations_log_fake_sql)
        migration_runner = MigrationRunner(migration_schema)

        if args.migrate:
            print(
                "  +---------------------------------------------------------+\n"
                "  | DATABASE MIGRATION FRAMEWORK: Applying Migrations       |\n"
                "  | All schema changes apply to in-memory dicts that will   |\n"
                "  | be destroyed when this process exits. You're welcome.   |\n"
                "  +---------------------------------------------------------+"
            )
            print()

            applied = migration_runner.apply_all()
            for record in applied:
                print(f"  [+] Applied: {record.migration_id} ({record.duration_ms:.2f}ms)")

            if not applied:
                print("  No pending migrations. The ephemeral schema is up to date.")

            print()

            if config.migrations_visualize_schema:
                print(SchemaVisualizer.render(migration_schema))

        if args.migrate_seed:
            if not migration_schema.table_exists("fizzbuzz_results"):
                migration_runner.apply_all()

            seeder = SeedDataGenerator(migration_schema)
            seed_start = config.migrations_seed_range_start
            seed_end = config.migrations_seed_range_end
            count = seeder.generate(seed_start, seed_end)
            print(
                f"  Seeded {count} rows using FizzBuzz to populate the FizzBuzz database.\n"
                f"  The ouroboros is complete. The snake has eaten its own tail.\n"
            )

        if args.migrate_rollback is not None:
            rolled_back = migration_runner.rollback(args.migrate_rollback)
            for record in rolled_back:
                print(f"  [-] Rolled back: {record.migration_id}")
            if not rolled_back:
                print("  No migrations to roll back.")
            print()

        if args.migrate_status:
            print(MigrationDashboard.render(migration_runner))

        if config.migrations_log_fake_sql and migration_schema.sql_log:
            print("  +-- FAKE SQL LOG (for enterprise cosplay) --+")
            for sql in migration_schema.sql_log:
                print(f"  |  {sql}")
            print("  +--------------------------------------------+")
            print()

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None

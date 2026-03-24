"""Feature descriptor for the FizzSQL relational query engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSQLFeature(FeatureDescriptor):
    name = "fizzsql"
    description = "Relational query engine with lexer, parser, volcano executor, and virtual tables over platform state"
    middleware_priority = 90
    cli_flags = [
        ("--fizzsql", {"type": str, "metavar": "QUERY", "default": None,
                       "help": 'Execute a FizzSQL query against platform internals (e.g. --fizzsql "SELECT * FROM evaluations")'}),
        ("--fizzsql-tables", {"action": "store_true", "default": False,
                              "help": "List all FizzSQL virtual tables and their schemas"}),
        ("--fizzsql-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzSQL Relational Query Engine ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzsql", None) is not None,
            getattr(args, "fizzsql_tables", False),
            getattr(args, "fizzsql_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsql import (
            FizzSQLEngine,
            PlatformState,
        )

        state = PlatformState(
            evaluations=None,
            cache_store=None,
            blockchain=None,
            sla_monitor=None,
            event_bus=event_bus,
        )

        engine = FizzSQLEngine(
            state=state,
            max_result_rows=config.fizzsql_max_result_rows,
            enable_history=config.fizzsql_enable_query_history,
            history_size=config.fizzsql_query_history_size,
            slow_query_threshold_ms=config.fizzsql_slow_query_threshold_ms,
        )

        if getattr(args, "fizzsql_tables", False):
            tables = engine.list_tables()
            print("\n  Available FizzSQL Virtual Tables:")
            print("  " + "=" * 57)
            for t in tables:
                print(f"\n  {t['name']}")
                print(f"    Columns: {t['columns']}")
                print(f"    {t['description']}")
            print("\n  " + "=" * 57)
            print()

        if getattr(args, "fizzsql", None):
            try:
                output = engine.execute(args.fizzsql)
                print(f"\n  fizzsql> {args.fizzsql}")
                print(output)
                print()
            except Exception as e:
                print(f"\n  FizzSQL Error: {e}\n")

        return engine, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "fizzsql_dashboard", False):
            return None
        engine = middleware
        if engine is None:
            return None
        from enterprise_fizzbuzz.infrastructure.fizzsql import FizzSQLDashboard
        return FizzSQLDashboard.render(
            engine,
            width=60,
        )

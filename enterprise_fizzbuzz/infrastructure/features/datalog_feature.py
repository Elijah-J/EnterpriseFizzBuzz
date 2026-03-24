"""Feature descriptor for the FizzLog Datalog query engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class DatalogFeature(FeatureDescriptor):
    name = "datalog"
    description = "Datalog query engine with stratified negation for declarative FizzBuzz reasoning"
    middleware_priority = 58
    cli_flags = [
        ("--datalog", {"action": "store_true", "default": False,
                       "help": "Enable FizzLog: Datalog query engine with stratified negation for declarative FizzBuzz reasoning"}),
        ("--datalog-query", {"type": str, "metavar": "QUERY", "default": None,
                             "help": 'Execute a Datalog query against the FizzBuzz knowledge base (e.g. --datalog-query "fizzbuzz(X)")'}),
        ("--datalog-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzLog ASCII dashboard with fact counts, stratification, and evaluation metrics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "datalog", False),
            getattr(args, "datalog_query", None) is not None,
            getattr(args, "datalog_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.datalog import (
            DatalogMiddleware,
            FizzBuzzDatalogProgram,
        )

        session = FizzBuzzDatalogProgram.create_session(
            config.range_start, config.range_end,
        )
        session.evaluate()
        middleware = DatalogMiddleware(session)

        return session, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []

        if getattr(args, "datalog_query", None) is not None:
            session = middleware._session if hasattr(middleware, "_session") else None
            if session is not None:
                try:
                    query_results = session.query_text(args.datalog_query)
                    lines = [f"\n  Datalog Query: {args.datalog_query}",
                             f"  Results: {len(query_results)} bindings"]
                    for i, bindings in enumerate(query_results[:50]):
                        binding_str = ", ".join(f"{k}={v}" for k, v in sorted(bindings.items()))
                        lines.append(f"    [{i + 1}] {binding_str}")
                    if len(query_results) > 50:
                        lines.append(f"    ... and {len(query_results) - 50} more")
                    lines.append("")
                    parts.append("\n".join(lines))
                except Exception as e:
                    parts.append(f"\n  Datalog query error: {e}\n")

        if getattr(args, "datalog_dashboard", False):
            from enterprise_fizzbuzz.infrastructure.datalog import DatalogDashboard
            session = middleware._session if hasattr(middleware, "_session") else None
            if session is not None:
                parts.append(DatalogDashboard.render(session=session, width=60))

        return "\n".join(parts) if parts else None

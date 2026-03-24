"""Feature descriptor for the FizzSheet spreadsheet engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SpreadsheetFeature(FeatureDescriptor):
    name = "spreadsheet"
    description = "Spreadsheet engine with formula parser, dependency graph, and Kahn topological recalculation"
    middleware_priority = 137
    cli_flags = [
        ("--sheet", {"action": "store_true", "default": False,
                     "help": "Enable the FizzSheet spreadsheet engine to capture evaluation results in a tabular grid"}),
        ("--sheet-formula", {"type": str, "default": None, "metavar": "FORMULA",
                             "help": "Evaluate a standalone spreadsheet formula (e.g. --sheet-formula '=FIZZBUZZ(15)')"}),
        ("--sheet-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzSheet ASCII dashboard with cell statistics and dependency graph metrics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "sheet", False),
            getattr(args, "sheet_dashboard", False),
            getattr(args, "sheet_formula", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.spreadsheet import (
            SpreadsheetMiddleware,
        )

        sheet_middleware = SpreadsheetMiddleware(
            enable_dashboard=getattr(args, "sheet_dashboard", False),
            event_bus=event_bus,
        )

        return sheet_middleware, sheet_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZSHEET: SPREADSHEET ENGINE ENABLED                   |\n"
            "  |   Cell addressing: A1 notation (A-Z, 1-999)            |\n"
            "  |   Formula parser: Recursive descent w/ precedence      |\n"
            "  |   Recalculation: Kahn's topological sort               |\n"
            "  |   Built-in functions: 20 (incl. FIZZBUZZ, COST, TAX)   |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "sheet_dashboard", False):
                return "  FizzSheet not enabled. Use --sheet to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.spreadsheet import (
            SpreadsheetDashboard,
            SpreadsheetRenderer,
        )

        parts = []

        if getattr(args, "sheet_dashboard", False):
            sheet = middleware.spreadsheet
            renderer = SpreadsheetRenderer()
            parts.append(renderer.render(sheet))
            parts.append(SpreadsheetDashboard.render(sheet))

        return "\n".join(parts) if parts else None

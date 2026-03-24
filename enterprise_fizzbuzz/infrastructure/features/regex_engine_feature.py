"""Feature descriptor for the FizzRegex regular expression engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class RegexEngineFeature(FeatureDescriptor):
    name = "regex_engine"
    description = "DFA-based regex engine with Thompson NFA construction and Hopcroft minimization"
    middleware_priority = 136
    cli_flags = [
        ("--regex", {"action": "store_true", "default": False,
                     "help": "Enable the FizzRegex engine for DFA-based classification validation (Thompson NFA + Rabin-Scott DFA)"}),
        ("--regex-match", {"nargs": 2, "type": str, "metavar": ("PATTERN", "INPUT"), "default": None,
                           "help": "Compile PATTERN via Thompson/Rabin-Scott pipeline and test against INPUT (e.g. --regex-match 'a|b' 'a')"}),
        ("--regex-benchmark", {"action": "store_true", "default": False,
                               "help": "Run the pathological pattern benchmark: (a?)^n(a)^n -- FizzRegex O(n) vs Python re O(2^n)"}),
        ("--regex-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzRegex ASCII dashboard with NFA/DFA state counts and minimization statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "regex", False),
            getattr(args, "regex_dashboard", False),
            getattr(args, "regex_match", None) is not None,
            getattr(args, "regex_benchmark", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.regex_engine import (
            RegexMiddleware,
        )

        regex_middleware = RegexMiddleware(
            event_bus=event_bus,
            enable_dashboard=getattr(args, "regex_dashboard", False),
        )

        return regex_middleware, regex_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZREGEX: REGULAR EXPRESSION ENGINE ENABLED            |\n"
            "  |   Construction: Thompson NFA (1968)                     |\n"
            "  |   Compilation: Rabin-Scott subset construction          |\n"
            "  |   Minimization: Hopcroft partition refinement           |\n"
            "  |   Matching: O(n) DFA simulation (no backtracking)       |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "regex_dashboard", False):
                return "  FizzRegex not enabled. Use --regex to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.regex_engine import (
            RegexDashboard,
        )

        parts = []

        if getattr(args, "regex_dashboard", False):
            all_stats = middleware.patterns.get_stats()
            parts.append(RegexDashboard.render(
                all_stats,
                benchmark_results=None,
                width=80,
            ))
            parts.append(
                f"  Validations: {middleware.match_count} passed, "
                f"{middleware.fail_count} failed"
            )
            parts.append(
                f"  Total match time: {middleware.total_match_time_us:.1f}us"
            )

        return "\n".join(parts) if parts else None

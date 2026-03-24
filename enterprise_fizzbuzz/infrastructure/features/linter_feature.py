"""Feature descriptor for the FizzLint static analysis engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class LinterFeature(FeatureDescriptor):
    name = "linter"
    description = "Static analysis engine for FizzBuzz rule definitions with auto-fix support"
    middleware_priority = 10
    cli_flags = [
        ("--lint", {"action": "store_true", "default": False,
                    "help": "Run FizzLint static analysis on the configured rule definitions and display the report"}),
        ("--lint-fix", {"action": "store_true", "default": False,
                        "help": "Run FizzLint and automatically apply safe fixes for auto-fixable violations"}),
        ("--lint-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzLint ASCII dashboard with violation distribution and rule status grid"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "lint", False),
            getattr(args, "lint_fix", False),
            getattr(args, "lint_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return self.is_enabled(args)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.linter import (
            AutoFixer,
            LintDashboard,
            LintEngine,
        )

        engine = LintEngine()
        report = engine.analyze(config.rules)

        if getattr(args, "lint_fix", False):
            fixer = AutoFixer()
            fixed_rules, applied = fixer.fix(config.rules, report.violations)
            if applied:
                print("FizzLint Auto-Fix Applied:")
                for desc in applied:
                    print(f"  {desc}")
                print()
                report = engine.analyze(fixed_rules)

        print(report.render())

        if getattr(args, "lint_dashboard", False):
            print()
            dashboard = LintDashboard()
            print(dashboard.render(report, config.rules))

        return 1 if report.has_errors else 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

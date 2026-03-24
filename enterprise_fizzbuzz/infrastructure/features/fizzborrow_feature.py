"""Feature descriptor for the FizzBorrow Ownership & Borrow Checker."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzBorrowFeature(FeatureDescriptor):
    name = "fizzborrow"
    description = "Ownership and borrow checker with NLL region inference, MIR-based analysis, and Rust-style diagnostics"
    middleware_priority = 60
    cli_flags = [
        ("--fizzborrow", {"action": "store_true",
                          "help": "Enable the FizzBorrow ownership and borrow checker for FizzLang programs"}),
        ("--no-fizzborrow-nll", {"action": "store_true", "default": False,
                                  "help": "Disable non-lexical lifetimes (use lexical lifetime analysis)"}),
        ("--fizzborrow-dump-mir", {"action": "store_true",
                                    "help": "Dump MIR representation before borrow analysis"}),
        ("--fizzborrow-dump-regions", {"action": "store_true",
                                        "help": "Dump solved lifetime regions after NLL inference"}),
        ("--fizzborrow-dump-borrows", {"action": "store_true",
                                        "help": "Dump active borrow set at each MIR statement"}),
        ("--fizzborrow-dump-drops", {"action": "store_true",
                                      "help": "Dump computed drop order for each scope"}),
        ("--fizzborrow-variance", {"action": "store_true",
                                    "help": "Display the variance table for all types"}),
        ("--fizzborrow-elision-verbose", {"action": "store_true",
                                           "help": "Show lifetimes inserted by the elision engine"}),
        ("--no-fizzborrow-two-phase", {"action": "store_true", "default": False,
                                        "help": "Disable two-phase borrows (strict borrowing)"}),
        ("--fizzborrow-strict", {"action": "store_true",
                                  "help": "Require all lifetimes to be explicitly annotated (no elision)"}),
        ("--fizzborrow-dashboard", {"action": "store_true",
                                     "help": "Display the FizzBorrow borrow checker ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzborrow", False),
            getattr(args, "fizzborrow_dump_mir", False),
            getattr(args, "fizzborrow_dump_regions", False),
            getattr(args, "fizzborrow_dump_borrows", False),
            getattr(args, "fizzborrow_dump_drops", False),
            getattr(args, "fizzborrow_variance", False),
            getattr(args, "fizzborrow_elision_verbose", False),
            getattr(args, "fizzborrow_strict", False),
            getattr(args, "fizzborrow_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzborrow import (
            FizzBorrowEngine,
            FizzBorrowMiddleware,
        )

        nll_enabled = config.fizzborrow_nll_enabled and not getattr(args, "no_fizzborrow_nll", False)
        two_phase_enabled = config.fizzborrow_two_phase_enabled and not getattr(args, "no_fizzborrow_two_phase", False)
        strict_mode = config.fizzborrow_strict_mode or getattr(args, "fizzborrow_strict", False)

        engine = FizzBorrowEngine(
            nll_enabled=nll_enabled,
            two_phase_enabled=two_phase_enabled,
            strict_mode=strict_mode,
            max_inference_iterations=config.fizzborrow_max_inference_iterations,
            max_liveness_iterations=config.fizzborrow_max_liveness_iterations,
            max_mir_temporaries=config.fizzborrow_max_mir_temporaries,
            max_borrow_depth=config.fizzborrow_max_borrow_depth,
            dump_mir=config.fizzborrow_dump_mir or getattr(args, "fizzborrow_dump_mir", False),
            dump_regions=config.fizzborrow_dump_regions or getattr(args, "fizzborrow_dump_regions", False),
            dump_borrows=config.fizzborrow_dump_borrows or getattr(args, "fizzborrow_dump_borrows", False),
            dump_drops=config.fizzborrow_dump_drops or getattr(args, "fizzborrow_dump_drops", False),
            show_variance=config.fizzborrow_show_variance or getattr(args, "fizzborrow_variance", False),
            event_bus=event_bus,
        )

        middleware = FizzBorrowMiddleware(
            engine=engine,
            dashboard_width=config.fizzborrow_dashboard_width,
            enable_dashboard=getattr(args, "fizzborrow_dashboard", False),
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "fizzborrow_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.fizzborrow import BorrowDashboard
        return BorrowDashboard.render(
            middleware,
            width=72,
        )

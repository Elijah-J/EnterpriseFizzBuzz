"""Feature descriptor for the PostgreSQL-style cost-based query optimizer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class QueryOptimizerFeature(FeatureDescriptor):
    name = "query_optimizer"
    description = "Cost-based query planner for FizzBuzz evaluation with EXPLAIN and plan caching"
    middleware_priority = 40
    cli_flags = [
        ("--optimize", {"action": "store_true", "default": False,
                        "help": "Enable the cost-based Query Optimizer for FizzBuzz evaluation (because modulo deserves a query planner)"}),
        ("--explain", {"type": int, "metavar": "N", "default": None,
                       "help": "Display the PostgreSQL-style EXPLAIN plan for evaluating number N (without executing)"}),
        ("--explain-analyze", {"type": int, "metavar": "N", "default": None,
                               "help": "Display EXPLAIN ANALYZE for number N (execute and compare estimated vs actual costs)"}),
        ("--optimizer-hints", {"type": str, "metavar": "HINTS", "default": None,
                               "help": "Comma-separated optimizer hints: FORCE_ML, PREFER_CACHE, NO_BLOCKCHAIN, NO_ML"}),
        ("--optimizer-dashboard", {"action": "store_true", "default": False,
                                   "help": "Display the Query Optimizer ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "optimize", False),
            getattr(args, "explain", None) is not None,
            getattr(args, "explain_analyze", None) is not None,
            getattr(args, "optimizer_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return (getattr(args, "explain", None) is not None or
                getattr(args, "explain_analyze", None) is not None)

    def run_early_exit(self, args: Any, config: Any) -> int:
        import time
        from enterprise_fizzbuzz.infrastructure.query_optimizer import (
            DivisibilityProfile,
            ExplainOutput,
            create_optimizer_from_config,
        )

        optimizer = create_optimizer_from_config(config)
        hints_str = getattr(args, "optimizer_hints", None)
        if hints_str:
            from enterprise_fizzbuzz.infrastructure.query_optimizer import parse_optimizer_hints
            hints = parse_optimizer_hints(hints_str)
        else:
            hints = frozenset()

        if args.explain is not None:
            profile = DivisibilityProfile(
                divisors=tuple(r.divisor for r in config.rules),
                labels=tuple(r.label for r in config.rules),
                range_size=max(1, args.explain),
            )
            plan = optimizer.optimize(profile, hints)
            print()
            print("  QUERY PLAN (estimated)")
            print("  " + "-" * 56)
            print(ExplainOutput.render(plan, analyze=False, indent=1))
            print("  " + "-" * 56)
            print(f"  Total estimated cost: {plan.total_cost():.2f} FCU")
            print()
            return 0

        if args.explain_analyze is not None:
            profile = DivisibilityProfile(
                divisors=tuple(r.divisor for r in config.rules),
                labels=tuple(r.label for r in config.rules),
                range_size=max(1, args.explain_analyze),
            )
            plan = optimizer.optimize(profile, hints)

            exec_start = time.perf_counter_ns()
            n = args.explain_analyze
            _result = "FizzBuzz" if n % 15 == 0 else "Fizz" if n % 3 == 0 else "Buzz" if n % 5 == 0 else str(n)
            exec_elapsed_ms = (time.perf_counter_ns() - exec_start) / 1_000_000

            def _mark_executed(node, depth=0):
                node.mark_executed(
                    actual_rows=node.estimated_rows,
                    actual_time_ms=exec_elapsed_ms / max(1, node.depth()),
                    actual_cost=node.estimated_cost * 1.05,
                )
                for child in node.children:
                    _mark_executed(child, depth + 1)
            _mark_executed(plan)

            print()
            print("  QUERY PLAN (with ANALYZE)")
            print("  " + "-" * 56)
            print(ExplainOutput.render(plan, analyze=True, indent=1))
            print("  " + "-" * 56)
            print(f"  Estimated cost: {plan.total_cost():.2f} FCU")
            print(f"  Actual cost:    {plan.total_actual_cost():.2f} FCU")
            print(f"  Execution time: {exec_elapsed_ms:.4f}ms")
            print(f"  Result:         {_result}")
            print()
            return 0

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.query_optimizer import (
            OptimizerMiddleware,
            create_optimizer_from_config,
            parse_optimizer_hints,
        )

        optimizer = create_optimizer_from_config(config)
        hints_str = getattr(args, "optimizer_hints", None)
        hints = parse_optimizer_hints(hints_str) if hints_str else frozenset()

        return optimizer, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "optimizer_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.query_optimizer import OptimizerDashboard
        return OptimizerDashboard.render(
            middleware, width=60,
        )

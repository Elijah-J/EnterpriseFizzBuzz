"""Feature descriptor for the FizzSpec Z notation formal specification subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ZSpecificationFeature(FeatureDescriptor):
    name = "z_specification"
    description = "Z notation formal specification with schema calculus and refinement checking"
    middleware_priority = 59
    cli_flags = [
        ("--zspec", {"action": "store_true", "default": False,
                     "help": "Enable FizzSpec: formal Z notation specification with schema calculus and refinement checking"}),
        ("--zspec-check", {"action": "store_true", "default": False,
                           "help": "Run refinement checking to verify FizzBuzz implementation against the Z specification"}),
        ("--zspec-render", {"action": "store_true", "default": False,
                            "help": "Render Z specification schemas as Unicode box-drawing art"}),
        ("--zspec-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzSpec ASCII dashboard with schema inventory and refinement results"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "zspec", False),
            getattr(args, "zspec_check", False),
            getattr(args, "zspec_render", False),
            getattr(args, "zspec_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.z_specification import (
            FizzBuzzSpec,
            SpecMiddleware,
        )

        spec = FizzBuzzSpec()
        middleware = SpecMiddleware(spec)

        return spec, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        from enterprise_fizzbuzz.infrastructure.z_specification import (
            RefinementChecker,
            SpecDashboard,
            ZRenderer,
        )

        parts = []
        spec = middleware._spec if hasattr(middleware, "_spec") else None
        if spec is None:
            return None

        if getattr(args, "zspec_check", False):
            def _fizzbuzz_impl(n: int) -> str:
                d3 = (n % 3 == 0)
                d5 = (n % 5 == 0)
                if d3 and d5:
                    return "FizzBuzz"
                if d3:
                    return "Fizz"
                if d5:
                    return "Buzz"
                return str(n)

            range_val = getattr(args, "range", None)
            start = range_val[0] if range_val else 1
            end = range_val[1] if range_val else 100

            checker = RefinementChecker(
                spec=spec.state_schema,
                impl_fn=_fizzbuzz_impl,
                test_range=range(start, end + 1),
            )
            refinement_results = []
            for op in spec.all_operations():
                result = checker.check_operation_refinement(
                    spec_operation=op,
                    postcondition_checker=spec.verify_classification,
                )
                refinement_results.append(result)

            all_valid = all(r.is_valid for r in refinement_results)
            total_checks = sum(r.checks_performed for r in refinement_results)
            total_passed = sum(r.checks_passed for r in refinement_results)
            status = "PASS" if all_valid else "FAIL"
            lines = [f"\n  FizzSpec Refinement: {status}  ({total_passed}/{total_checks} checks)"]
            for r in refinement_results:
                marker = "[+]" if r.is_valid else "[X]"
                lines.append(f"    {marker} {r.spec_name}: {r.checks_passed}/{r.checks_performed}")
            lines.append("")
            parts.append("\n".join(lines))
        else:
            refinement_results = None

        if getattr(args, "zspec_render", False):
            render_parts = [""]
            for schema in spec.all_schemas():
                render_parts.append(ZRenderer.render_schema(schema, width=56))
                render_parts.append("")
            for op in spec.all_operations():
                render_parts.append(ZRenderer.render_operation(op, width=56))
                render_parts.append("")
            parts.append("\n".join(render_parts))

        if getattr(args, "zspec_dashboard", False):
            parts.append(SpecDashboard.render(
                spec=spec,
                refinement_results=refinement_results,
                width=60,
            ))

        return "\n".join(parts) if parts else None

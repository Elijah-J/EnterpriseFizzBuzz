"""Feature descriptor for FizzOrg organizational hierarchy engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzOrgFeature(FeatureDescriptor):
    name = "fizzorg"
    description = "Organizational hierarchy engine with departments, positions, RACI matrix, headcount planning, and governance committees"
    middleware_priority = 105
    cli_flags = [
        ("--org", {"action": "store_true",
                   "help": "Enable FizzOrg: organizational hierarchy engine with departments, positions, RACI matrix, headcount planning, and governance committees"}),
        ("--org-chart", {"action": "store_true",
                         "help": "Display the FizzOrg ASCII organizational chart after execution"}),
        ("--org-raci-matrix", {"action": "store_true",
                               "help": "Display the FizzOrg RACI matrix summary after execution"}),
        ("--org-headcount-report", {"action": "store_true",
                                    "help": "Display the FizzOrg headcount report and hiring plan after execution"}),
        ("--org-department", {"type": str, "default": None,
                              "help": "Display positions for a specific department (e.g., Engineering, Operations)"}),
        ("--org-committees", {"action": "store_true",
                              "help": "Display the FizzOrg governance committee status report after execution"}),
        ("--org-reporting-chain", {"type": str, "default": None,
                                   "help": "Trace the reporting chain from a position to the root (e.g., 'On-Call Engineer')"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "org", False),
            getattr(args, "org_chart", False),
            getattr(args, "org_raci_matrix", False),
            getattr(args, "org_headcount_report", False),
            getattr(args, "org_department", None) is not None,
            getattr(args, "org_committees", False),
            getattr(args, "org_reporting_chain", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzorg import (
            create_org_subsystem,
        )

        engine, middleware = create_org_subsystem(
            operator=config.org_operator,
            target_headcount=config.org_target_headcount,
            enable_dashboard=getattr(args, "org_chart", False),
            event_bus=event_bus,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "org_chart", False):
            parts.append(middleware.render_org_chart())
        if getattr(args, "org_raci_matrix", False):
            parts.append(middleware.render_raci_summary())
        if getattr(args, "org_headcount_report", False):
            parts.append(middleware.render_headcount_report())
        if getattr(args, "org_department", None) is not None:
            from enterprise_fizzbuzz.infrastructure.fizzorg import DepartmentRegistry, DepartmentType
            dept = None
            for dt in DepartmentType:
                name = DepartmentRegistry.DEPARTMENT_NAMES.get(dt, "")
                if name.lower() == args.org_department.lower() or dt.value == args.org_department.lower():
                    dept = dt
                    break
            if dept:
                parts.append(middleware.engine.chart_renderer.render_department_view(dept))
            else:
                parts.append(f"\n  Department not found: {args.org_department}\n")
        if getattr(args, "org_committees", False):
            parts.append(middleware.render_committees_report())
        if getattr(args, "org_reporting_chain", None) is not None:
            parts.append(middleware.render_reporting_chain(args.org_reporting_chain))
        return "\n".join(parts) if parts else None

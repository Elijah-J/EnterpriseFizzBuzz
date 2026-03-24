"""Feature descriptor for the FizzApproval multi-party approval workflow engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ApprovalFeature(FeatureDescriptor):
    name = "approval"
    description = "ITIL v4 change management approval workflow with CAB review and four-eyes principle"
    middleware_priority = 102
    cli_flags = [
        ("--approval", {"action": "store_true",
                        "help": "Enable FizzApproval: route every evaluation through ITIL v4 change management approval workflow with CAB review, four-eyes principle, and SOE handling"}),
        ("--approval-dashboard", {"action": "store_true",
                                  "help": "Display the FizzApproval workflow dashboard after execution"}),
        ("--approval-policy", {"type": str, "default": None, "metavar": "TYPE",
                               "help": "Default approval policy type: STANDARD, NORMAL, or EMERGENCY (default: from config, typically NORMAL)"}),
        ("--approval-change-type", {"type": str, "default": None, "metavar": "TYPE",
                                    "help": "Default ITIL change type for evaluations: STANDARD, NORMAL, or EMERGENCY (default: from config, typically NORMAL)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "approval", False),
            getattr(args, "approval_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.approval import (
            ApprovalMiddleware,
            create_approval_subsystem,
        )

        engine, dashboard, middleware = create_approval_subsystem(
            default_policy=getattr(args, "approval_policy", None) or config.approval_default_policy,
            default_change_type=getattr(args, "approval_change_type", None) or config.approval_default_change_type,
            dashboard_width=config.approval_dashboard_width,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "approval_dashboard", False):
            return None
        if middleware is None:
            return None
        return middleware.render_dashboard()

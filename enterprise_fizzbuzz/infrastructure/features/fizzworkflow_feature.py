"""Feature descriptor for FizzWorkflow."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzWorkflowFeature(FeatureDescriptor):
    name = "fizzworkflow"
    description = "Workflow orchestration with saga patterns and compensation"
    middleware_priority = 154
    cli_flags = [
        ("--fizzworkflow", {"action": "store_true", "default": False, "help": "Enable FizzWorkflow"}),
        ("--fizzworkflow-start", {"type": str, "default": None, "help": "Start workflow"}),
        ("--fizzworkflow-list", {"action": "store_true", "default": False, "help": "List workflows"}),
        ("--fizzworkflow-status", {"type": str, "default": None, "help": "Get instance status"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzworkflow", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzworkflow import FizzWorkflowMiddleware, create_fizzworkflow_subsystem
        e, d, m = create_fizzworkflow_subsystem(dashboard_width=config.fizzworkflow_dashboard_width)
        return e, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()

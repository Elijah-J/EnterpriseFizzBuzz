"""Feature descriptor for FizzCron."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzCronFeature(FeatureDescriptor):
    name = "fizzcron"
    description = "Distributed job scheduler with cron expressions, locks, and history"
    middleware_priority = 138
    cli_flags = [
        ("--fizzcron", {"action": "store_true", "default": False, "help": "Enable FizzCron"}),
        ("--fizzcron-list", {"action": "store_true", "default": False, "help": "List jobs"}),
        ("--fizzcron-run", {"type": str, "default": None, "help": "Execute a job by ID"}),
        ("--fizzcron-history", {"action": "store_true", "default": False, "help": "Show job history"}),
        ("--fizzcron-add", {"type": str, "default": None, "help": "Add job (name:schedule:command)"}),
        ("--fizzcron-remove", {"type": str, "default": None, "help": "Remove job by ID"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzcron", False), getattr(args, "fizzcron_list", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcron import FizzCronMiddleware, create_fizzcron_subsystem
        s, d, m = create_fizzcron_subsystem(dashboard_width=config.fizzcron_dashboard_width)
        return s, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzcron_list", False): parts.append(middleware.render_list())
        if getattr(args, "fizzcron_history", False): parts.append(middleware.render_history())
        if getattr(args, "fizzcron", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

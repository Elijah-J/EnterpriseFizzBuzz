"""Feature descriptor for FizzConfig2."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzConfig2Feature(FeatureDescriptor):
    name = "fizzconfig2"
    description = "Distributed configuration with versioning, rollback, validation, and watchers"
    middleware_priority = 150
    cli_flags = [
        ("--fizzconfig2", {"action": "store_true", "default": False, "help": "Enable FizzConfig2"}),
        ("--fizzconfig2-get", {"type": str, "default": None, "help": "Get config (ns/key)"}),
        ("--fizzconfig2-set", {"type": str, "default": None, "help": "Set config (ns/key=value)"}),
        ("--fizzconfig2-list", {"action": "store_true", "default": False, "help": "List config"}),
        ("--fizzconfig2-history", {"type": str, "default": None, "help": "Show config history"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzconfig2", False), getattr(args, "fizzconfig2_list", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzconfig2 import FizzConfig2Middleware, create_fizzconfig2_subsystem
        s, d, m = create_fizzconfig2_subsystem(dashboard_width=config.fizzconfig2_dashboard_width)
        return s, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzconfig2_list", False): parts.append(middleware.render_list())
        if getattr(args, "fizzconfig2", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

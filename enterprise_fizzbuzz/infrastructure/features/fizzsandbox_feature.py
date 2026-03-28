"""Feature descriptor for FizzSandbox."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzSandboxFeature(FeatureDescriptor):
    name = "fizzsandbox"
    description = "Code sandbox with isolation, resource limits, and security validation"
    middleware_priority = 144
    cli_flags = [
        ("--fizzsandbox", {"action": "store_true", "default": False, "help": "Enable FizzSandbox"}),
        ("--fizzsandbox-run", {"type": str, "default": None, "help": "Execute code in sandbox"}),
        ("--fizzsandbox-validate", {"type": str, "default": None, "help": "Validate code safety"}),
        ("--fizzsandbox-list", {"action": "store_true", "default": False, "help": "List sandboxes"}),
        ("--fizzsandbox-timeout", {"type": float, "default": 30.0, "help": "Execution timeout"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzsandbox", False), getattr(args, "fizzsandbox_run", None)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsandbox import FizzSandboxMiddleware, create_fizzsandbox_subsystem
        m, d, mw = create_fizzsandbox_subsystem(timeout=config.fizzsandbox_timeout,
                                                  dashboard_width=config.fizzsandbox_dashboard_width)
        return m, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzsandbox_list", False): parts.append(middleware.render_list())
        if getattr(args, "fizzsandbox", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

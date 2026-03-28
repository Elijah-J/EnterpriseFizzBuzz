"""Feature descriptor for FizzAudit."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzAuditFeature(FeatureDescriptor):
    name = "fizzaudit"
    description = "Tamper-evident audit trail with SHA-256 hash chain and retention policies"
    middleware_priority = 142
    cli_flags = [
        ("--fizzaudit", {"action": "store_true", "default": False, "help": "Enable FizzAudit"}),
        ("--fizzaudit-search", {"type": str, "default": None, "help": "Search audit log"}),
        ("--fizzaudit-verify", {"action": "store_true", "default": False, "help": "Verify chain integrity"}),
        ("--fizzaudit-export", {"action": "store_true", "default": False, "help": "Export audit log"}),
        ("--fizzaudit-stats", {"action": "store_true", "default": False, "help": "Show audit statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzaudit", False), getattr(args, "fizzaudit_verify", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzaudit import FizzAuditMiddleware, create_fizzaudit_subsystem
        log, d, m = create_fizzaudit_subsystem(retention_days=config.fizzaudit_retention_days,
                                                dashboard_width=config.fizzaudit_dashboard_width)
        return log, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzaudit_verify", False): parts.append(middleware.render_verify())
        if getattr(args, "fizzaudit_stats", False): parts.append(middleware.render_stats())
        if getattr(args, "fizzaudit", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

"""Feature descriptor for FizzSecurityScanner."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzSecurityScannerFeature(FeatureDescriptor):
    name = "fizzsecurityscanner"
    description = "SAST/DAST security scanner with secret detection and dependency audit"
    middleware_priority = 170
    cli_flags = [("--fizzsecurityscanner", {"action": "store_true", "default": False, "help": "Enable FizzSecurityScanner"}),
                 ("--fizzsecurityscanner-scan", {"type": str, "default": None, "help": "Scan code"})]
    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzsecurityscanner", False)])
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsecurityscanner import FizzSecurityScannerMiddleware, create_fizzsecurityscanner_subsystem
        s, d, m = create_fizzsecurityscanner_subsystem(dashboard_width=config.fizzsecurityscanner_dashboard_width)
        return s, m
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()

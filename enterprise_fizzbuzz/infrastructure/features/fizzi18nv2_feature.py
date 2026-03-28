"""Feature descriptor for FizzI18nV2."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzI18nV2Feature(FeatureDescriptor):
    name = "fizzi18nv2"
    description = "Localization management with ICU message format, plural rules, and translation store"
    middleware_priority = 148
    cli_flags = [
        ("--fizzi18nv2", {"action": "store_true", "default": False, "help": "Enable FizzI18nV2"}),
        ("--fizzi18nv2-locale", {"type": str, "default": "en", "help": "Set locale"}),
        ("--fizzi18nv2-locales", {"action": "store_true", "default": False, "help": "List locales"}),
        ("--fizzi18nv2-completion", {"action": "store_true", "default": False, "help": "Show completion"}),
        ("--fizzi18nv2-export", {"type": str, "default": None, "help": "Export locale"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzi18nv2", False), getattr(args, "fizzi18nv2_locales", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzi18nv2 import FizzI18nV2Middleware, create_fizzi18nv2_subsystem
        s, l, d, m = create_fizzi18nv2_subsystem(default_locale=config.fizzi18nv2_default_locale,
                                                   dashboard_width=config.fizzi18nv2_dashboard_width)
        return s, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzi18nv2_locales", False): parts.append(middleware.render_locales())
        if getattr(args, "fizzi18nv2", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

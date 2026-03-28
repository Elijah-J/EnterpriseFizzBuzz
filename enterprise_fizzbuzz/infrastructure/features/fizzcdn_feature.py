"""Feature descriptor for the FizzCDN content delivery network."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzCDNFeature(FeatureDescriptor):
    name = "fizzcdn"
    description = "CDN with edge caching, geographic routing, purge, preload, and edge compute"
    middleware_priority = 130
    cli_flags = [
        ("--fizzcdn", {"action": "store_true", "default": False, "help": "Enable FizzCDN"}),
        ("--fizzcdn-pops", {"type": int, "default": 5, "help": "Number of PoP nodes"}),
        ("--fizzcdn-create-pop", {"type": str, "default": None, "help": "Create a PoP (name:region:lat:lon)"}),
        ("--fizzcdn-purge", {"type": str, "default": None, "help": "Purge a single URL from cache"}),
        ("--fizzcdn-purge-prefix", {"type": str, "default": None, "help": "Purge by URL prefix"}),
        ("--fizzcdn-purge-tag", {"type": str, "default": None, "help": "Purge by cache tag"}),
        ("--fizzcdn-preload", {"type": str, "default": None, "help": "Preload a URL into all PoPs"}),
        ("--fizzcdn-analytics", {"action": "store_true", "default": False, "help": "Display CDN analytics"}),
        ("--fizzcdn-edge-compute", {"action": "store_true", "default": True, "help": "Enable edge compute"}),
        ("--fizzcdn-origin", {"type": str, "default": "origin.fizzbuzz.local", "help": "Origin server address"}),
        ("--fizzcdn-ttl", {"type": int, "default": 3600, "help": "Default cache TTL in seconds"}),
        ("--fizzcdn-stale-while-revalidate", {"type": int, "default": 60, "help": "Stale-while-revalidate window"}),
        ("--fizzcdn-stale-if-error", {"type": int, "default": 300, "help": "Stale-if-error window"}),
        ("--fizzcdn-cache-stats", {"action": "store_true", "default": False, "help": "Display cache statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzcdn", False), getattr(args, "fizzcdn_analytics", False),
                    getattr(args, "fizzcdn_cache_stats", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcdn import FizzCDNMiddleware, create_fizzcdn_subsystem
        cdn, dashboard, mw = create_fizzcdn_subsystem(
            num_pops=config.fizzcdn_pops, ttl=config.fizzcdn_ttl,
            origin=config.fizzcdn_origin, enable_edge_compute=config.fizzcdn_edge_compute,
            dashboard_width=config.fizzcdn_dashboard_width,
        )
        return cdn, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzcdn_analytics", False): parts.append(middleware.render_analytics())
        if getattr(args, "fizzcdn_cache_stats", False): parts.append(middleware.render_cache_stats())
        if getattr(args, "fizzcdn", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

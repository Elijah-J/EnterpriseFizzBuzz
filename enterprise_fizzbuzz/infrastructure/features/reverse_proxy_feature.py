"""Feature descriptor for the FizzProxy reverse proxy and load balancer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ReverseProxyFeature(FeatureDescriptor):
    name = "reverse_proxy"
    description = "Reverse proxy with load-balanced FizzBuzz evaluation across multiple backend engines"
    middleware_priority = 56
    cli_flags = [
        ("--proxy", {"action": "store_true", "default": False,
                     "help": "Enable the FizzProxy reverse proxy for load-balanced FizzBuzz evaluation across multiple backend engines"}),
        ("--proxy-backends", {"type": int, "default": None, "metavar": "N",
                              "help": "Number of backend engine instances in the proxy pool (default: from config)"}),
        ("--proxy-algorithm", {"type": str,
                               "choices": ["round_robin", "least_connections", "weighted_random", "ip_hash"],
                               "default": None, "metavar": "ALG",
                               "help": "Load balancing algorithm (default: from config)"}),
        ("--proxy-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzProxy ASCII dashboard with backend pool status and traffic distribution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "proxy", False) or getattr(args, "proxy_dashboard", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.reverse_proxy import (
            LoadBalanceAlgorithm,
            ProxyMiddleware,
            create_proxy_subsystem,
        )

        algorithm_name = getattr(args, "proxy_algorithm", None) or config.proxy_algorithm
        algorithm_map = {
            "round_robin": LoadBalanceAlgorithm.ROUND_ROBIN,
            "least_connections": LoadBalanceAlgorithm.LEAST_CONNECTIONS,
            "weighted_random": LoadBalanceAlgorithm.WEIGHTED_RANDOM,
            "ip_hash": LoadBalanceAlgorithm.IP_HASH,
        }
        proxy_algorithm = algorithm_map.get(algorithm_name, LoadBalanceAlgorithm.ROUND_ROBIN)
        proxy_num_backends = getattr(args, "proxy_backends", None) or config.proxy_num_backends

        proxy_instance, proxy_pool = create_proxy_subsystem(
            num_backends=proxy_num_backends,
            algorithm=proxy_algorithm,
            rules=list(config.rules),
            enable_sticky=config.proxy_enable_sticky_sessions,
            enable_health_check=config.proxy_enable_health_check,
            dashboard_width=config.proxy_dashboard_width,
        )

        middleware = ProxyMiddleware(
            proxy=proxy_instance,
            event_bus=event_bus,
        )

        return proxy_instance, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "proxy_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.reverse_proxy import ProxyDashboard
        proxy = middleware._proxy if hasattr(middleware, "_proxy") else None
        if proxy is None:
            return None
        return ProxyDashboard.render(
            proxy=proxy,
            width=60,
        )

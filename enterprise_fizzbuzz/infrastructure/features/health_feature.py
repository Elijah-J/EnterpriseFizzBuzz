"""Feature descriptor for the Kubernetes-style Health Check Probes subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class HealthFeature(FeatureDescriptor):
    name = "health"
    description = "Kubernetes-style liveness, readiness, and startup probes with self-healing"
    middleware_priority = 0
    cli_flags = [
        ("--health", {"action": "store_true", "default": False,
                      "help": "Enable Kubernetes-style health check probes for the FizzBuzz platform"}),
        ("--liveness", {"action": "store_true", "default": False,
                        "help": "Run a liveness probe (canary evaluation of 15 must equal FizzBuzz)"}),
        ("--readiness", {"action": "store_true", "default": False,
                         "help": "Run a readiness probe (aggregate subsystem health assessment)"}),
        ("--startup-probe", {"action": "store_true", "default": False,
                             "help": "Display the startup probe status (boot milestone tracking)"}),
        ("--health-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the comprehensive health check dashboard after execution"}),
        ("--self-heal", {"action": "store_true", "default": False,
                         "help": "Enable self-healing: automatically attempt recovery of failing subsystems"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "health", False),
            getattr(args, "liveness", False),
            getattr(args, "readiness", False),
            getattr(args, "startup_probe", False),
            getattr(args, "health_dashboard", False),
            getattr(args, "self_heal", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.health import (
            CacheCoherenceHealthCheck,
            CircuitBreakerHealthCheck,
            ConfigHealthCheck,
            HealthCheckRegistry,
            LivenessProbe,
            MLEngineHealthCheck,
            ReadinessProbe,
            SelfHealingManager,
            SLABudgetHealthCheck,
            StartupProbe,
        )

        HealthCheckRegistry.reset()
        health_registry = HealthCheckRegistry.get_instance()

        health_registry.register(ConfigHealthCheck(config))
        health_registry.register(CircuitBreakerHealthCheck(registry=None))
        health_registry.register(CacheCoherenceHealthCheck(cache_store=None))
        health_registry.register(SLABudgetHealthCheck(sla_monitor=None))
        health_registry.register(MLEngineHealthCheck())

        liveness_probe = LivenessProbe(
            evaluate_fn=lambda n: "",
            canary_number=config.health_check_canary_number,
            canary_expected=config.health_check_canary_expected,
            event_bus=event_bus,
        )

        readiness_probe = ReadinessProbe(
            registry=health_registry,
            degraded_is_ready=config.health_check_degraded_is_ready,
            event_bus=event_bus,
        )

        startup_probe = StartupProbe(
            milestones=config.health_check_startup_milestones,
            timeout_seconds=config.health_check_startup_timeout,
            event_bus=event_bus,
        )

        self_healing_mgr = None
        if getattr(args, "self_heal", False):
            self_healing_mgr = SelfHealingManager(
                registry=health_registry,
                max_retries=config.health_check_self_healing_max_retries,
                backoff_base_ms=config.health_check_self_healing_backoff_ms,
                event_bus=event_bus,
            )

        service = {
            "registry": health_registry,
            "liveness": liveness_probe,
            "readiness": readiness_probe,
            "startup": startup_probe,
            "self_healing": self_healing_mgr,
        }

        return service, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None and not isinstance(middleware, dict):
            # Health feature stores service in the middleware slot via create()
            pass
        return None

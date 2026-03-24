"""Feature descriptor for the Digital Twin simulation subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class DigitalTwinFeature(FeatureDescriptor):
    name = "digital_twin"
    description = "Real-time simulation mirror with Monte Carlo analysis, drift monitoring, and what-if scenarios"
    middleware_priority = 57
    cli_flags = [
        ("--twin", {"action": "store_true",
                    "help": "Enable the Digital Twin: a real-time simulation of the platform itself (a simulation of a simulation of n%%3)"}),
        ("--twin-scenario", {"type": str, "metavar": "SCENARIO", "default": None,
                             "help": 'Run a what-if scenario against the twin (e.g. --twin-scenario "blockchain.latency_ms=1.0;cache.failure_prob=0.5")'}),
        ("--twin-dashboard", {"action": "store_true",
                              "help": "Display the Digital Twin ASCII dashboard with Monte Carlo histogram and drift gauge"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "twin", False),
            getattr(args, "twin_dashboard", False),
            getattr(args, "twin_scenario", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.digital_twin import (
            MonteCarloEngine,
            PredictiveAnomalyDetector,
            StateSync,
            TwinDriftMonitor,
            TwinMiddleware,
            TwinModel,
            WhatIfSimulator,
        )

        active_flags: dict[str, bool] = {
            "cache": getattr(args, "cache", False),
            "circuit_breaker": getattr(args, "circuit_breaker", False),
            "blockchain": getattr(args, "blockchain", False),
            "tracing": getattr(args, "otel", False),
            "sla_monitor": getattr(args, "sla", False),
            "compliance": getattr(args, "compliance", False),
            "service_mesh": getattr(args, "service_mesh", False),
            "chaos_monkey": getattr(args, "chaos", False),
            "finops": getattr(args, "finops", False),
            "event_sourcing": getattr(args, "event_sourcing", False),
            "feature_flags": getattr(args, "feature_flags", False),
        }

        twin_model = TwinModel(
            active_flags=active_flags,
            jitter_stddev=config.digital_twin_jitter_stddev,
            failure_jitter=config.digital_twin_failure_jitter,
        )

        drift_monitor = TwinDriftMonitor(
            threshold_fdu=config.digital_twin_drift_threshold_fdu,
        )

        anomaly_detector = PredictiveAnomalyDetector(
            anomaly_sigma=config.digital_twin_anomaly_sigma,
        )

        state_sync = StateSync(twin_model)
        if event_bus is not None:
            event_bus.subscribe(state_sync)

        mc_engine = MonteCarloEngine(twin_model)
        mc_result = mc_engine.run(n=config.digital_twin_monte_carlo_runs)

        middleware = TwinMiddleware(
            model=twin_model,
            anomaly_detector=anomaly_detector,
            drift_monitor=drift_monitor,
            event_bus=event_bus,
        )

        what_if_result = None
        if getattr(args, "twin_scenario", None):
            simulator = WhatIfSimulator(twin_model)
            what_if_result = simulator.simulate_scenario(
                args.twin_scenario,
                monte_carlo_runs=min(500, config.digital_twin_monte_carlo_runs),
            )

        middleware._twin_model = twin_model
        middleware._mc_result = mc_result
        middleware._drift_monitor = drift_monitor
        middleware._anomaly_detector = anomaly_detector
        middleware._what_if_result = what_if_result

        return twin_model, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "twin_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.digital_twin import TwinDashboard
        return TwinDashboard.render(
            model=middleware._twin_model,
            mc_result=getattr(middleware, "_mc_result", None),
            drift_monitor=getattr(middleware, "_drift_monitor", None),
            anomaly_detector=getattr(middleware, "_anomaly_detector", None),
            what_if_result=getattr(middleware, "_what_if_result", None),
            width=60,
            show_histogram=True,
            show_drift_gauge=True,
            histogram_buckets=20,
        )

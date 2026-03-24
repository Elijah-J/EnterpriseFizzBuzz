"""Feature descriptor for the Prometheus-style metrics collection subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class MetricsFeature(FeatureDescriptor):
    name = "metrics"
    description = "Prometheus-style metrics collection with counters, gauges, histograms, and summaries"
    middleware_priority = 40
    cli_flags = [
        ("--metrics", {"action": "store_true",
                       "help": "Enable Prometheus-style metrics collection for FizzBuzz evaluation"}),
        ("--metrics-export", {"action": "store_true",
                              "help": "Export all metrics in Prometheus text exposition format after execution"}),
        ("--metrics-dashboard", {"action": "store_true",
                                 "help": "Display the ASCII Grafana metrics dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "metrics", False),
            getattr(args, "metrics_export", False),
            getattr(args, "metrics_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.metrics import (
            MetricRegistry,
            create_metrics_subsystem,
        )

        MetricRegistry.reset()
        registry, collector, middleware, cardinality = create_metrics_subsystem(
            event_bus=event_bus,
            bob_initial_stress=config.metrics_bob_stress_level,
            cardinality_threshold=config.metrics_cardinality_threshold,
            default_buckets=config.metrics_default_buckets,
        )

        return (registry, collector, cardinality), middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | PROMETHEUS METRICS: Collection ENABLED                  |\n"
            "  | Counters, gauges, histograms, and summaries are now     |\n"
            "  | tracking every aspect of your FizzBuzz evaluations.     |\n"
            "  | Bob McFizzington's stress level: monitored.             |\n"
            "  | is_tuesday label: mandatory.                            |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.metrics import (
            MetricsDashboard,
            PrometheusTextExporter,
        )
        parts = []
        if getattr(args, "metrics_export", False):
            parts.append(PrometheusTextExporter.export())
        if getattr(args, "metrics_dashboard", False):
            parts.append(MetricsDashboard.render())
        return "\n".join(parts) if parts else None

"""Feature descriptor for the Unified Audit Dashboard and event streaming."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class AuditDashboardFeature(FeatureDescriptor):
    name = "audit_dashboard"
    description = "Six-pane ASCII telemetry dashboard with anomaly detection, correlation, and NDJSON event streaming"
    middleware_priority = 128
    cli_flags = [
        ("--audit-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the Unified Audit Dashboard: six-pane ASCII telemetry for FizzBuzz observability-of-observability"}),
        ("--audit-stream", {"action": "store_true", "default": False,
                            "help": "Stream all events as NDJSON to stdout (structured logging for the structurally inclined)"}),
        ("--audit-anomalies", {"action": "store_true", "default": False,
                               "help": "Display the anomaly detection report after execution (z-score analysis of FizzBuzz event rates)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "audit_dashboard", False),
            getattr(args, "audit_stream", False),
            getattr(args, "audit_anomalies", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import (
            UnifiedAuditDashboard,
        )

        audit_dashboard = UnifiedAuditDashboard(
            buffer_size=config.audit_dashboard_buffer_size,
            anomaly_window_seconds=config.audit_dashboard_anomaly_window_seconds,
            z_score_threshold=config.audit_dashboard_z_score_threshold,
            anomaly_min_samples=config.audit_dashboard_anomaly_min_samples,
            correlation_window_seconds=config.audit_dashboard_correlation_window_seconds,
            correlation_min_events=config.audit_dashboard_correlation_min_events,
            stream_include_payload=config.audit_dashboard_stream_include_payload,
            enable_anomaly_detection=config.audit_dashboard_anomaly_enabled,
            enable_correlation=config.audit_dashboard_correlation_enabled,
        )

        if event_bus is not None:
            event_bus.subscribe(audit_dashboard.aggregator)

        # UnifiedAuditDashboard is not a pipeline middleware — it subscribes
        # to the event bus directly. Return it as the service with no middleware.
        self._dashboard_instance = audit_dashboard
        return audit_dashboard, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        dashboard = getattr(self, "_dashboard_instance", None)
        if dashboard is None:
            return None

        parts = []

        if getattr(args, "audit_dashboard", False):
            parts.append(dashboard.render_dashboard(width=80))

        if getattr(args, "audit_stream", False):
            stream_output = dashboard.render_stream()
            if stream_output:
                parts.append(stream_output)

        if getattr(args, "audit_anomalies", False):
            parts.append(dashboard.render_anomalies())

        return "\n".join(parts) if parts else None

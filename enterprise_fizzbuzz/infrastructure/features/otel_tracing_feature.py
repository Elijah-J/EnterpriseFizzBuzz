"""Feature descriptor for the FizzOTel OpenTelemetry-compatible distributed tracing subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class OTelTracingFeature(FeatureDescriptor):
    name = "otel_tracing"
    description = "OpenTelemetry-compatible distributed tracing with W3C TraceContext, OTLP/Zipkin export, and probabilistic sampling"
    middleware_priority = 5
    cli_flags = [
        ("--otel", {"action": "store_true", "default": False,
                    "help": "Enable FizzOTel distributed tracing: W3C TraceContext, OTLP/Zipkin export, probabilistic sampling"}),
        ("--otel-export", {"type": str, "choices": ["otlp", "zipkin", "console"],
                           "default": None,
                           "help": "OTel trace export format: otlp (JSON), zipkin (v2 JSON), console (ASCII waterfall). Default: from config"}),
        ("--otel-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzOTel ASCII dashboard with trace stats, sampling decisions, export metrics, and duration histogram"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "otel", False),
            getattr(args, "otel_dashboard", False),
            getattr(args, "trace", False),
            getattr(args, "trace_json", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.otel_tracing import (
            create_otel_subsystem,
            set_active_provider,
        )

        tracing_enabled = getattr(args, "trace", False) or getattr(args, "trace_json", False)

        if getattr(args, "otel_export", None):
            otel_export_fmt = args.otel_export
        elif getattr(args, "trace_json", False):
            otel_export_fmt = "otlp"
        elif getattr(args, "trace", False):
            otel_export_fmt = "console"
        else:
            otel_export_fmt = config.otel_export_format

        provider, exporter, middleware = create_otel_subsystem(
            sampling_rate=config.otel_sampling_rate,
            export_format=otel_export_fmt,
            batch_mode=config.otel_batch_mode,
            max_queue_size=config.otel_max_queue_size,
            max_batch_size=config.otel_max_batch_size,
            console_width=config.otel_dashboard_width,
        )

        set_active_provider(provider)

        # Attach provider/exporter to middleware for post-execution rendering
        middleware._otel_provider = provider
        middleware._otel_exporter = exporter

        service = {"provider": provider, "exporter": exporter}
        return service, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.otel_tracing import (
            ConsoleExporter as OTelConsoleExporter,
            OTelDashboard,
        )
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()

        provider = getattr(middleware, "_otel_provider", None)
        exporter = getattr(middleware, "_otel_exporter", None)
        if provider is None or exporter is None:
            return None

        provider.shutdown()

        parts = []
        parts.append(
            "\n  +---------------------------------------------------------+\n"
            "  | FizzOTel Distributed Tracing                            |\n"
            "  | OpenTelemetry-Compatible W3C TraceContext Propagation   |\n"
            "  | Because single-node tracing was never enough.           |\n"
            "  +---------------------------------------------------------+"
        )

        parts.append(f"\n  Traces:    {provider.trace_count}")
        parts.append(f"  Spans:     {provider.span_count}")
        parts.append(f"  Sampled:   {provider.sampler.sampled_count}")
        parts.append(f"  Dropped:   {provider.sampler.dropped_count}")
        parts.append(f"  Exported:  {exporter.exported_count}")
        parts.append(f"  Avg dur:   {provider.metrics_bridge.avg_duration_ms:.3f}ms")
        parts.append("")

        if isinstance(exporter, OTelConsoleExporter):
            parts.append(exporter.render())
            parts.append("")

        if getattr(args, "otel_dashboard", False):
            dashboard = OTelDashboard(
                provider=provider,
                exporter=exporter,
                width=config.otel_dashboard_width,
            )
            parts.append(dashboard.render())

        return "\n".join(parts) if parts else None

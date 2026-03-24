"""Feature descriptor for the FizzCDC Change Data Capture subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CDCFeature(FeatureDescriptor):
    name = "cdc"
    description = "Change Data Capture with transactional outbox, schema registry, and pluggable sink connectors"
    middleware_priority = 131
    cli_flags = [
        ("--cdc", {"action": "store_true", "default": False,
                   "help": "Enable FizzCDC Change Data Capture: stream platform state changes through an outbox relay to pluggable sinks"}),
        ("--cdc-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzCDC ASCII dashboard with capture rates, outbox depth, relay lag, and sink status"}),
        ("--cdc-sinks", {"type": str, "default": None, "metavar": "SINKS",
                         "help": "Comma-separated list of CDC sink connectors (log,metrics,message_queue). Default: from config"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "cdc", False),
            getattr(args, "cdc_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.cdc import (
            CDCMiddleware,
            create_cdc_subsystem,
        )

        sinks_cfg = (
            [s.strip() for s in args.cdc_sinks.split(",")]
            if getattr(args, "cdc_sinks", None)
            else config.cdc_sinks
        )
        pipeline, agents, sinks_list, _registry = create_cdc_subsystem(
            sinks_config=sinks_cfg,
            compatibility=config.cdc_schema_compatibility,
            relay_interval_s=config.cdc_relay_interval_s,
            outbox_capacity=config.cdc_outbox_capacity,
        )

        middleware = CDCMiddleware(pipeline=pipeline)
        pipeline.outbox_relay.start()

        return (pipeline, agents, sinks_list), middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZCDC — CHANGE DATA CAPTURE                           |\n"
            "  | Transactional Outbox | Schema Registry | Sink Relay     |\n"
            f"  | Relay Interval: {config.cdc_relay_interval_s:.2f}s  Capacity: {config.cdc_outbox_capacity:<14}|\n"
            "  | Capture: cache | blockchain | SLA | compliance          |\n"
            '  | "Every state change deserves a paper trail."            |\n'
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "cdc_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.cdc import CDCDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        pipeline = middleware.pipeline
        pipeline.outbox_relay.stop()
        return CDCDashboard.render(
            pipeline=pipeline,
            agents=[],
            sinks=[],
            width=config.cdc_dashboard_width,
        )

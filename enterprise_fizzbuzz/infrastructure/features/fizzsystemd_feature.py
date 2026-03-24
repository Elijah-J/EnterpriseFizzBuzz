"""Feature descriptor for the FizzSystemd service manager."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSystemdFeature(FeatureDescriptor):
    name = "fizzsystemd"
    description = "systemd-style service manager with init system, journal, socket activation, and watchdog"
    middleware_priority = 104
    cli_flags = [
        ("--fizzsystemd", {"action": "store_true",
                           "help": "Enable FizzSystemd: service manager and init system"}),
        ("--fizzsystemd-status", {"action": "store_true",
                                  "help": "Display service tree with unit status"}),
        ("--fizzctl", {"nargs": "*", "default": None, "metavar": "ARGS",
                       "help": "Invoke fizzctl administrative subcommands"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzsystemd", False),
            getattr(args, "fizzsystemd_status", False),
            getattr(args, "fizzctl", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsystemd import (
            FizzSystemdMiddleware,
            create_fizzsystemd_subsystem,
        )

        manager, middleware = create_fizzsystemd_subsystem(
            unit_dir=config.fizzsystemd_unit_dir,
            default_target=config.fizzsystemd_default_target,
            log_level=config.fizzsystemd_log_level,
            watchdog_sec=config.fizzsystemd_watchdog_sec,
            journal_max_size=config.fizzsystemd_journal_max_size,
            journal_seal=config.fizzsystemd_journal_seal,
            dashboard_width=config.fizzsystemd_dashboard_width,
            event_bus=event_bus,
        )

        return manager, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzsystemd_status", False):
            parts.append(middleware.render_service_tree())
        if getattr(args, "fizzctl", None) is not None:
            parts.append(middleware.render_fizzctl_output(args.fizzctl))
        if getattr(args, "fizzsystemd", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

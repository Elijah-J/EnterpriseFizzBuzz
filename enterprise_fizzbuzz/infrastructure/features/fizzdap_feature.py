"""Feature descriptor for the FizzDAP Debug Adapter Protocol server."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzDAPFeature(FeatureDescriptor):
    name = "fizzdap"
    description = "Debug Adapter Protocol server for stepping through FizzBuzz evaluations with breakpoints and stack frames"
    middleware_priority = 91
    cli_flags = [
        ("--dap", {"action": "store_true", "default": False,
                   "help": "Enable the FizzDAP Debug Adapter Protocol Server: step through FizzBuzz one modulo at a time"}),
        ("--dap-port", {"type": int, "default": None, "metavar": "N",
                        "help": "DAP server port (simulated, no actual socket -- default: from config)"}),
        ("--dap-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzDAP ASCII dashboard with breakpoints, stack trace, variables, and Debug Complexity Index"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "dap", False) or getattr(args, "dap_dashboard", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzdap import FizzDAPServer

        dap_port = getattr(args, "dap_port", None) or config.fizzdap_port

        server = FizzDAPServer(
            port=dap_port,
            auto_stop_on_entry=config.fizzdap_auto_stop_on_entry,
            max_breakpoints=config.fizzdap_max_breakpoints,
            step_granularity=config.fizzdap_step_granularity,
            max_frames=config.fizzdap_max_frames,
            include_source_location=config.fizzdap_include_source_location,
            include_cache=config.fizzdap_include_cache_state,
            include_circuit_breaker=config.fizzdap_include_circuit_breaker,
            include_quantum=config.fizzdap_include_quantum_state,
            include_timings=config.fizzdap_include_middleware_timings,
            max_string_length=config.fizzdap_max_string_length,
        )

        server.initialize()

        return server, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "dap_dashboard", False):
            return None
        server = middleware
        if server is None:
            return None

        # Terminate session if still active
        if hasattr(server, "session") and server.session.is_active:
            server.terminate()

        from enterprise_fizzbuzz.infrastructure.fizzdap import FizzDAPDashboard
        return FizzDAPDashboard.render(
            server,
            width=60,
            show_breakpoints=True,
            show_stack_trace=True,
            show_variables=True,
            show_complexity_index=True,
        )

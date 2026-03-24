"""Fizzdap configuration properties."""

from __future__ import annotations

from typing import Any


class FizzdapConfigMixin:
    """Configuration properties for the fizzdap subsystem."""

    # ----------------------------------------------------------------
    # FizzDAP Debug Adapter Protocol
    # ----------------------------------------------------------------

    @property
    def fizzdap_enabled(self) -> bool:
        """Whether the FizzDAP Debug Adapter Protocol server is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("enabled", False)

    @property
    def fizzdap_port(self) -> int:
        """The DAP server port (simulated)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("port", 4711)

    @property
    def fizzdap_auto_stop_on_entry(self) -> bool:
        """Whether to automatically break on first evaluation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("auto_stop_on_entry", True)

    @property
    def fizzdap_max_breakpoints(self) -> int:
        """Maximum concurrent breakpoints."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("max_breakpoints", 256)

    @property
    def fizzdap_step_granularity(self) -> str:
        """Step granularity: middleware | instruction | evaluation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("step_granularity", "middleware")

    @property
    def fizzdap_include_cache_state(self) -> bool:
        """Whether to expose cache MESI states as debugger variables."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_cache_state", True)

    @property
    def fizzdap_include_circuit_breaker(self) -> bool:
        """Whether to expose circuit breaker state as variables."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_circuit_breaker", True)

    @property
    def fizzdap_include_quantum_state(self) -> bool:
        """Whether to expose quantum register amplitudes as variables."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_quantum_state", True)

    @property
    def fizzdap_include_middleware_timings(self) -> bool:
        """Whether to expose per-middleware timing data."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("include_middleware_timings", True)

    @property
    def fizzdap_max_string_length(self) -> int:
        """Maximum string length for variable inspection."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("variable_inspection", {}).get("max_string_length", 1024)

    @property
    def fizzdap_include_source_location(self) -> bool:
        """Whether to synthesize source locations for middleware stack frames."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("stack_frame", {}).get("include_source_location", True)

    @property
    def fizzdap_max_frames(self) -> int:
        """Maximum stack frame depth."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("stack_frame", {}).get("max_frames", 64)

    @property
    def fizzdap_dashboard_width(self) -> int:
        """Dashboard width for the FizzDAP dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("width", 60)

    @property
    def fizzdap_dashboard_show_breakpoints(self) -> bool:
        """Whether to show breakpoint table in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_breakpoints", True)

    @property
    def fizzdap_dashboard_show_stack_trace(self) -> bool:
        """Whether to show synthetic stack trace in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_stack_trace", True)

    @property
    def fizzdap_dashboard_show_variables(self) -> bool:
        """Whether to show variable inspector in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_variables", True)

    @property
    def fizzdap_dashboard_show_complexity_index(self) -> bool:
        """Whether to show Debug Complexity Index in dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdap", {}).get("dashboard", {}).get("show_complexity_index", True)


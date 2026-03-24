"""FizzLSP configuration properties."""

from __future__ import annotations

from typing import Any


class FizzlspConfigMixin:
    """Configuration properties for the fizzlsp subsystem."""

    # ----------------------------------------------------------------
    # FizzLSP Language Server Protocol
    # ----------------------------------------------------------------

    @property
    def fizzlsp_enabled(self) -> bool:
        """Whether the FizzLSP Language Server Protocol server is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("enabled", False)

    @property
    def fizzlsp_transport(self) -> str:
        """Transport type: 'stdio' or 'tcp'."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("transport", "stdio")

    @property
    def fizzlsp_tcp_port(self) -> int:
        """TCP port for the TCP transport (simulated)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("tcp_port", 5007)

    @property
    def fizzlsp_diagnostic_debounce_ms(self) -> int:
        """Debounce interval for diagnostic publication in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("diagnostic_debounce_ms", 150)

    @property
    def fizzlsp_max_completion_items(self) -> int:
        """Maximum number of completion items returned per request."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("max_completion_items", 50)

    @property
    def fizzlsp_semantic_tokens_enabled(self) -> bool:
        """Whether to compute semantic tokens for syntax highlighting."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("semantic_tokens_enabled", True)

    @property
    def fizzlsp_dependent_type_diagnostics(self) -> bool:
        """Whether to include dependent type observations in diagnostics."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dependent_type_diagnostics", True)

    @property
    def fizzlsp_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("width", 60)

    @property
    def fizzlsp_dashboard_show_documents(self) -> bool:
        """Whether to show active documents in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_documents", True)

    @property
    def fizzlsp_dashboard_show_diagnostics(self) -> bool:
        """Whether to show diagnostic breakdown in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_diagnostics", True)

    @property
    def fizzlsp_dashboard_show_protocol_stats(self) -> bool:
        """Whether to show protocol statistics in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_protocol_stats", True)

    @property
    def fizzlsp_dashboard_show_complexity_index(self) -> bool:
        """Whether to show the LSP Complexity Index in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_complexity_index", True)

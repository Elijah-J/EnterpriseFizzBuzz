"""API Gateway properties"""

from __future__ import annotations

from typing import Any


class ApiGatewayConfigMixin:
    """Configuration properties for the api gateway subsystem."""

    # ----------------------------------------------------------------
    # API Gateway properties
    # ----------------------------------------------------------------

    @property
    def api_gateway_enabled(self) -> bool:
        """Whether the API Gateway subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("enabled", False)

    @property
    def api_gateway_versions(self) -> dict[str, Any]:
        """Version configuration for the API Gateway."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("versions", {})

    @property
    def api_gateway_default_version(self) -> str:
        """Default API version when none is specified."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("default_version", "v2")

    @property
    def api_gateway_routes(self) -> list[dict[str, Any]]:
        """Route definitions for the API Gateway."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("routes", [])

    @property
    def api_gateway_api_keys_default_quota(self) -> int:
        """Default request quota per API key."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("api_keys", {}).get("default_quota", 1000)

    @property
    def api_gateway_api_keys_prefix(self) -> str:
        """Prefix for generated API keys."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("api_keys", {}).get("key_prefix", "efp_")

    @property
    def api_gateway_api_keys_length(self) -> int:
        """Length of generated API keys (after prefix)."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("api_keys", {}).get("key_length", 32)

    @property
    def api_gateway_transformers(self) -> dict[str, Any]:
        """Transformer configuration for request/response pipelines."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("transformers", {})

    @property
    def api_gateway_replay_journal_enabled(self) -> bool:
        """Whether the request replay journal is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("replay_journal", {}).get("enabled", True)

    @property
    def api_gateway_replay_journal_max_entries(self) -> int:
        """Maximum entries in the request replay journal."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("replay_journal", {}).get("max_entries", 10000)

    @property
    def api_gateway_dashboard_width(self) -> int:
        """ASCII dashboard width for the API Gateway dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("api_gateway", {}).get("dashboard", {}).get("width", 60)


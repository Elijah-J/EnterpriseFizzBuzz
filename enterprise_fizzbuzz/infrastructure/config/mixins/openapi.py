"""OpenAPI Specification Generator properties"""

from __future__ import annotations

from typing import Any


class OpenapiConfigMixin:
    """Configuration properties for the openapi subsystem."""

    # ----------------------------------------------------------------
    # OpenAPI Specification Generator properties
    # ----------------------------------------------------------------

    @property
    def openapi_enabled(self) -> bool:
        """Whether the OpenAPI spec generator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("enabled", False)

    @property
    def openapi_spec_version(self) -> str:
        """OpenAPI specification version."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("spec_version", "3.1.0")

    @property
    def openapi_server_url(self) -> str:
        """The server URL. Always http://localhost:0. Always does not exist."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("server_url", "http://localhost:0")

    @property
    def openapi_server_description(self) -> str:
        """Server description."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("server_description", "This server does not exist")

    @property
    def openapi_swagger_ui_width(self) -> int:
        """ASCII Swagger UI width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("swagger_ui_width", 80)

    @property
    def openapi_dashboard_width(self) -> int:
        """ASCII dashboard width for the OpenAPI dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("dashboard_width", 70)

    @property
    def openapi_include_deprecated(self) -> bool:
        """Whether to include deprecated endpoints in output."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("include_deprecated", True)

    @property
    def openapi_contact_name(self) -> str:
        """API contact person name."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("contact_name", "Bob McFizzington")

    @property
    def openapi_contact_email(self) -> str:
        """API contact email."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("contact_email", "bob.mcfizzington@enterprise.example.com")

    @property
    def openapi_license_name(self) -> str:
        """API license name."""
        self._ensure_loaded()
        return self._raw_config.get("openapi", {}).get("license_name", "Enterprise FizzBuzz Public License v1.0")


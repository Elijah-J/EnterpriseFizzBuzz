"""FizzCap — Capability-Based Security properties"""

from __future__ import annotations

from typing import Any


class CapabilitySecurityConfigMixin:
    """Configuration properties for the capability security subsystem."""

    # ------------------------------------------------------------------
    # FizzCap — Capability-Based Security properties
    # ------------------------------------------------------------------

    @property
    def capability_security_enabled(self) -> bool:
        """Whether the FizzCap capability-based security model is active."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("enabled", False)

    @property
    def capability_security_mode(self) -> str:
        """Capability enforcement mode: native, bridge, or audit-only."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("mode", "native")

    @property
    def capability_security_secret_key(self) -> str:
        """HMAC-SHA256 secret key for capability signing."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("secret_key", "fizzcap-default-key")

    @property
    def capability_security_default_resource(self) -> str:
        """Default resource identifier for capability middleware."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("default_resource", "fizzbuzz:evaluation")

    @property
    def capability_security_dashboard_width(self) -> int:
        """Dashboard width for the FizzCap dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("capability_security", {}).get("dashboard", {}).get("width", 60)


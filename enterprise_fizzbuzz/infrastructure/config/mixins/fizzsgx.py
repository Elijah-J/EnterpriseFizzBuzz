"""FizzSGX — Intel SGX Enclave Simulator properties"""

from __future__ import annotations


class FizzsgxConfigMixin:
    """Configuration properties for the FizzSGX subsystem."""

    @property
    def fizzsgx_enabled(self) -> bool:
        """Whether the FizzSGX enclave simulator is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsgx", {}).get("enabled", False)

    @property
    def fizzsgx_enclave_size(self) -> int:
        """Maximum enclave memory size in bytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsgx", {}).get("enclave_size", 67108864)

    @property
    def fizzsgx_max_enclaves(self) -> int:
        """Maximum number of concurrent enclaves."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsgx", {}).get("max_enclaves", 8)

    @property
    def fizzsgx_dashboard_width(self) -> int:
        """Dashboard width for the FizzSGX ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsgx", {}).get("dashboard", {}).get("width", 72)

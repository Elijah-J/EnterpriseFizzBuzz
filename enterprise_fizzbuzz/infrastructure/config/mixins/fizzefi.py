"""FizzEFI — UEFI Firmware Interface properties"""

from __future__ import annotations


class FizzefiConfigMixin:
    """Configuration properties for the FizzEFI subsystem."""

    @property
    def fizzefi_enabled(self) -> bool:
        """Whether the FizzEFI UEFI firmware interface is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzefi", {}).get("enabled", False)

    @property
    def fizzefi_secure_boot(self) -> bool:
        """Whether UEFI Secure Boot verification is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzefi", {}).get("secure_boot", True)

    @property
    def fizzefi_variable_store_size(self) -> int:
        """Maximum number of UEFI variables in the variable store."""
        self._ensure_loaded()
        return self._raw_config.get("fizzefi", {}).get("variable_store_size", 256)

    @property
    def fizzefi_dashboard_width(self) -> int:
        """Dashboard width for the FizzEFI ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzefi", {}).get("dashboard", {}).get("width", 72)

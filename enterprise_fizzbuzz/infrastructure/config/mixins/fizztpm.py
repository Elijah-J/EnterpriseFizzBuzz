"""FizzTPM — Trusted Platform Module 2.0 properties"""

from __future__ import annotations


class FizztpmConfigMixin:
    """Configuration properties for the FizzTPM subsystem."""

    @property
    def fizztpm_enabled(self) -> bool:
        """Whether the FizzTPM trusted platform module is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizztpm", {}).get("enabled", False)

    @property
    def fizztpm_algorithm(self) -> str:
        """Hash algorithm for the PCR bank (sha256, sha384, sha512)."""
        self._ensure_loaded()
        return self._raw_config.get("fizztpm", {}).get("algorithm", "sha256")

    @property
    def fizztpm_measurement_pcr(self) -> int:
        """PCR index used for FizzBuzz classification measurements."""
        self._ensure_loaded()
        return self._raw_config.get("fizztpm", {}).get("measurement_pcr", 17)

    @property
    def fizztpm_dashboard_width(self) -> int:
        """Dashboard width for the FizzTPM ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizztpm", {}).get("dashboard", {}).get("width", 72)

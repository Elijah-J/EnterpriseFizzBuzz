"""IP Office Configuration Properties"""

from __future__ import annotations

from typing import Any


class IpOfficeConfigMixin:
    """Configuration properties for the ip office subsystem."""

    # ----------------------------------------------------------------
    # IP Office Configuration Properties
    # ----------------------------------------------------------------

    @property
    def ip_office_enabled(self) -> bool:
        """Whether the FizzBuzz Intellectual Property Office is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("enabled", False)

    @property
    def ip_office_trademark_similarity_threshold(self) -> float:
        """Phonetic similarity threshold for trademark conflict detection."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("trademark_similarity_threshold", 0.7)

    @property
    def ip_office_patent_novelty_threshold(self) -> float:
        """Prior art similarity threshold for patent novelty examination."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("patent_novelty_threshold", 0.5)

    @property
    def ip_office_copyright_originality_threshold(self) -> float:
        """Levenshtein distance threshold for copyright originality scoring."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("copyright_originality_threshold", 0.3)

    @property
    def ip_office_default_license(self) -> str:
        """Default license type for new IP registrations."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("default_license", "FBPL")

    @property
    def ip_office_trademark_renewal_days(self) -> int:
        """Number of days before trademark registration expires."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("trademark_renewal_days", 365)

    @property
    def ip_office_dashboard_width(self) -> int:
        """Dashboard width for the IP Office dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("ip_office", {}).get("dashboard", {}).get("width", 60)


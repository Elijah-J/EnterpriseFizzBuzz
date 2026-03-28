"""FizzIOMMU — I/O Memory Management Unit properties"""

from __future__ import annotations


class FizziommuConfigMixin:
    """Configuration properties for the FizzIOMMU subsystem."""

    @property
    def fizziommu_enabled(self) -> bool:
        """Whether the FizzIOMMU I/O memory management unit is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizziommu", {}).get("enabled", False)

    @property
    def fizziommu_page_size(self) -> int:
        """Page size in bytes for IOMMU translation tables."""
        self._ensure_loaded()
        return self._raw_config.get("fizziommu", {}).get("page_size", 4096)

    @property
    def fizziommu_max_devices(self) -> int:
        """Maximum number of devices the IOMMU can manage."""
        self._ensure_loaded()
        return self._raw_config.get("fizziommu", {}).get("max_devices", 256)

    @property
    def fizziommu_dashboard_width(self) -> int:
        """Dashboard width for the FizzIOMMU ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizziommu", {}).get("dashboard", {}).get("width", 72)

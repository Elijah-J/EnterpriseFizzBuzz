"""FizzSmartNIC — Smart NIC Offload Engine properties"""

from __future__ import annotations


class FizzsmartnicConfigMixin:
    """Configuration properties for the FizzSmartNIC subsystem."""

    @property
    def fizzsmartnic_enabled(self) -> bool:
        """Whether the FizzSmartNIC offload engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsmartnic", {}).get("enabled", False)

    @property
    def fizzsmartnic_num_queues(self) -> int:
        """Number of TX/RX queue pairs on the Smart NIC."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsmartnic", {}).get("num_queues", 4)

    @property
    def fizzsmartnic_max_flow_rules(self) -> int:
        """Maximum number of hardware flow rules."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsmartnic", {}).get("max_flow_rules", 8192)

    @property
    def fizzsmartnic_dashboard_width(self) -> int:
        """Dashboard width for the FizzSmartNIC ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsmartnic", {}).get("dashboard", {}).get("width", 72)

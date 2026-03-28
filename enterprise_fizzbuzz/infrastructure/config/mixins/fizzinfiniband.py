"""FizzInfiniBand — InfiniBand Fabric Simulator properties"""

from __future__ import annotations


class FizzinfinibandConfigMixin:
    """Configuration properties for the FizzInfiniBand subsystem."""

    @property
    def fizzinfiniband_enabled(self) -> bool:
        """Whether the FizzInfiniBand fabric simulator is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzinfiniband", {}).get("enabled", False)

    @property
    def fizzinfiniband_max_nodes(self) -> int:
        """Maximum number of nodes in the IB fabric."""
        self._ensure_loaded()
        return self._raw_config.get("fizzinfiniband", {}).get("max_nodes", 64)

    @property
    def fizzinfiniband_default_mtu(self) -> int:
        """Default MTU for InfiniBand ports."""
        self._ensure_loaded()
        return self._raw_config.get("fizzinfiniband", {}).get("default_mtu", 4096)

    @property
    def fizzinfiniband_dashboard_width(self) -> int:
        """Dashboard width for the FizzInfiniBand ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzinfiniband", {}).get("dashboard", {}).get("width", 72)

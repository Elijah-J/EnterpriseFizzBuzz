"""FizzLoadBalancerV2 configuration."""
from __future__ import annotations
class Fizzloadbalancerv2ConfigMixin:
    @property
    def fizzloadbalancerv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzloadbalancerv2", {}).get("enabled", False)
    @property
    def fizzloadbalancerv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzloadbalancerv2", {}).get("dashboard_width", 72))

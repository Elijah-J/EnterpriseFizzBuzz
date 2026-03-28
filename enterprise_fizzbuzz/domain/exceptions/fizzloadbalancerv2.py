"""Enterprise FizzBuzz Platform - FizzLoadBalancerV2 Errors (EFP-LBV2-00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzLoadBalancerV2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzLoadBalancerV2: {r}", error_code="EFP-LBV2-00", context={"reason": r})
class FizzLoadBalancerV2BackendError(FizzLoadBalancerV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Backend: {r}"); self.error_code="EFP-LBV2-01"
class FizzLoadBalancerV2CircuitError(FizzLoadBalancerV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Circuit: {r}"); self.error_code="EFP-LBV2-02"
class FizzLoadBalancerV2CanaryError(FizzLoadBalancerV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Canary: {r}"); self.error_code="EFP-LBV2-03"
class FizzLoadBalancerV2RoutingError(FizzLoadBalancerV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Routing: {r}"); self.error_code="EFP-LBV2-04"
class FizzLoadBalancerV2ConfigError(FizzLoadBalancerV2Error):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-LBV2-05"

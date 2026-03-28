"""Enterprise FizzBuzz Platform - FizzNetworkPolicy Errors (EFP-NP00..04)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzNetworkPolicyError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzNetworkPolicy: {r}", error_code="EFP-NP00", context={"reason": r})
class FizzNetworkPolicyRuleError(FizzNetworkPolicyError):
    def __init__(self, r: str) -> None: super().__init__(f"Rule: {r}"); self.error_code="EFP-NP01"
class FizzNetworkPolicyDNSError(FizzNetworkPolicyError):
    def __init__(self, r: str) -> None: super().__init__(f"DNS: {r}"); self.error_code="EFP-NP02"
class FizzNetworkPolicyPolicySetError(FizzNetworkPolicyError):
    def __init__(self, r: str) -> None: super().__init__(f"PolicySet: {r}"); self.error_code="EFP-NP03"
class FizzNetworkPolicyConfigError(FizzNetworkPolicyError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-NP04"

"""Enterprise FizzBuzz Platform - FizzComplianceV2 Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzComplianceV2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzComplianceV2: {r}", error_code="EFP-COMP2-00", context={"reason": r})
class FizzComplianceV2ControlError(FizzComplianceV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Control: {r}"); self.error_code="EFP-COMP2-01"
class FizzComplianceV2ConfigError(FizzComplianceV2Error):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-COMP2-02"

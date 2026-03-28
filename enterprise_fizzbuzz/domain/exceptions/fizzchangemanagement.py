"""Enterprise FizzBuzz Platform - FizzChangeManagement Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzChangeManagementError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzChangeManagement: {r}", error_code="EFP-CHM00", context={"reason": r})
class FizzChangeManagementNotFoundError(FizzChangeManagementError):
    def __init__(self, i: str) -> None: super().__init__(f"Not found: {i}"); self.error_code="EFP-CHM01"
class FizzChangeManagementStateError(FizzChangeManagementError):
    def __init__(self, r: str) -> None: super().__init__(f"State: {r}"); self.error_code="EFP-CHM02"
class FizzChangeManagementConfigError(FizzChangeManagementError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-CHM03"

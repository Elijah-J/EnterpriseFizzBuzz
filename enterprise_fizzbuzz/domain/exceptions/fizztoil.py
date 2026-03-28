"""Enterprise FizzBuzz Platform - FizzToil Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzToilError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzToil: {r}", error_code="EFP-TOIL00", context={"reason": r})
class FizzToilNotFoundError(FizzToilError):
    def __init__(self, t: str) -> None: super().__init__(f"Task not found: {t}"); self.error_code="EFP-TOIL01"
class FizzToilConfigError(FizzToilError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-TOIL02"

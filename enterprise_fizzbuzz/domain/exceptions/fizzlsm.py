"""Enterprise FizzBuzz Platform - FizzLSM Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzLSMError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzLSM: {r}", error_code="EFP-LSM00", context={"reason": r})
class FizzLSMNotFoundError(FizzLSMError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-LSM01"

"""Enterprise FizzBuzz Platform - FizzOPA Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzOPAError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzOPA: {r}", error_code="EFP-OPA00", context={"reason": r})
class FizzOPANotFoundError(FizzOPAError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-OPA01"

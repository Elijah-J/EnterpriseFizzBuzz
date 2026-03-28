"""Enterprise FizzBuzz Platform - FizzSMT Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzSMTError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzSMT: {r}", error_code="EFP-SMT00", context={"reason": r})
class FizzSMTNotFoundError(FizzSMTError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-SMT01"

"""Enterprise FizzBuzz Platform - FizzWAF Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzWAFError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzWAF: {r}", error_code="EFP-WAF00", context={"reason": r})
class FizzWAFNotFoundError(FizzWAFError):
    def __init__(self, s: str) -> None: super().__init__(f"Rule not found: {s}"); self.error_code="EFP-WAF01"

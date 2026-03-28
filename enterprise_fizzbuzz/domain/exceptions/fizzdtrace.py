"""Enterprise FizzBuzz Platform - FizzDTrace Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzDTraceError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzDTrace: {r}", error_code="EFP-DTR00", context={"reason": r})
class FizzDTraceNotFoundError(FizzDTraceError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-DTR01"

"""Enterprise FizzBuzz Platform - FizzWASI Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzWASIError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzWASI: {r}", error_code="EFP-WASI00", context={"reason": r})
class FizzWASINotFoundError(FizzWASIError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-WASI01"

"""Enterprise FizzBuzz Platform - FizzFFI Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzFFIError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzFFI: {r}", error_code="EFP-FFI00", context={"reason": r})
class FizzFFINotFoundError(FizzFFIError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-FFI01"
class FizzFFITypeError(FizzFFIError):
    def __init__(self, r: str) -> None: super().__init__(f"Type error: {r}"); self.error_code="EFP-FFI02"

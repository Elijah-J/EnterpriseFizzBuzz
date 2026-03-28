"""Enterprise FizzBuzz Platform - FizzIDL Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzIDLError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzIDL: {r}", error_code="EFP-IDL00", context={"reason": r})
class FizzIDLNotFoundError(FizzIDLError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-IDL01"
class FizzIDLConfigError(FizzIDLError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-IDL02"

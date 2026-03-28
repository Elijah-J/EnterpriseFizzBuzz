"""Enterprise FizzBuzz Platform - FizzPGWire Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzPGWireError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzPGWire: {r}", error_code="EFP-PGW00", context={"reason": r})
class FizzPGWireNotFoundError(FizzPGWireError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-PGW01"
class FizzPGWireAuthError(FizzPGWireError):
    def __init__(self, r: str) -> None: super().__init__(f"Auth failed: {r}"); self.error_code="EFP-PGW02"

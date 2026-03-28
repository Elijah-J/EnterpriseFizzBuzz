"""Enterprise FizzBuzz Platform - FizzBloom Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzBloomError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzBloom: {r}", error_code="EFP-BLOM00", context={"reason": r})
class FizzBloomNotFoundError(FizzBloomError):
    def __init__(self, s: str) -> None: super().__init__(f"Structure not found: {s}"); self.error_code="EFP-BLOM01"
class FizzBloomConfigError(FizzBloomError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-BLOM02"

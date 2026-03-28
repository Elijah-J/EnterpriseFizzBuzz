"""Enterprise FizzBuzz Platform - FizzDrift Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzDriftError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzDrift: {r}", error_code="EFP-DFT00", context={"reason": r})
class FizzDriftNotFoundError(FizzDriftError):
    def __init__(self, d: str) -> None: super().__init__(f"Drift not found: {d}"); self.error_code="EFP-DFT01"
class FizzDriftConfigError(FizzDriftError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-DFT02"

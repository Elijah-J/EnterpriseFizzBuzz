"""Enterprise FizzBuzz Platform - FizzHealthAggregator Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzHealthAggregatorError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzHealthAggregator: {r}", error_code="EFP-HLAG00", context={"reason": r})
class FizzHealthAggregatorNotFoundError(FizzHealthAggregatorError):
    def __init__(self, s: str) -> None: super().__init__(f"Subsystem not found: {s}"); self.error_code="EFP-HLAG01"
class FizzHealthAggregatorConfigError(FizzHealthAggregatorError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-HLAG02"

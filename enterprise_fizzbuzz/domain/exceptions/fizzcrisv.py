"""Enterprise FizzBuzz Platform - FizzRISCV Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzRISCVError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzRISCV: {r}", error_code="EFP-RSCV00", context={"reason": r})
class FizzRISCVNotFoundError(FizzRISCVError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-RSCV01"

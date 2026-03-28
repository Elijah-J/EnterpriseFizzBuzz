"""Enterprise FizzBuzz Platform - FizzBPF Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzBPFError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzBPF: {r}", error_code="EFP-BPF00", context={"reason": r})
class FizzBPFNotFoundError(FizzBPFError):
    def __init__(self, s: str) -> None: super().__init__(f"Probe not found: {s}"); self.error_code="EFP-BPF01"

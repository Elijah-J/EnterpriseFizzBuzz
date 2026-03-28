"""Enterprise FizzBuzz Platform - FizzMPSC Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzMPSCError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzMPSC: {r}", error_code="EFP-MPSC00", context={"reason": r})
class FizzMPSCNotFoundError(FizzMPSCError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-MPSC01"
class FizzMPSCClosedError(FizzMPSCError):
    def __init__(self, c: str) -> None: super().__init__(f"Channel closed: {c}"); self.error_code="EFP-MPSC02"

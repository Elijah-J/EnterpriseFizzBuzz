"""Enterprise FizzBuzz Platform - FizzZFS Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzZFSError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzZFS: {r}", error_code="EFP-ZFS00", context={"reason": r})
class FizzZFSNotFoundError(FizzZFSError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-ZFS01"

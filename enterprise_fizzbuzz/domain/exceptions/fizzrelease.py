"""Enterprise FizzBuzz Platform - FizzRelease Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzReleaseError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzRelease: {r}", error_code="EFP-RELS00", context={"reason": r})
class FizzReleaseNotFoundError(FizzReleaseError):
    def __init__(self, s: str) -> None: super().__init__(f"Release not found: {s}"); self.error_code="EFP-RELS01"
class FizzReleaseStateError(FizzReleaseError):
    def __init__(self, r: str) -> None: super().__init__(f"Invalid state: {r}"); self.error_code="EFP-RELS02"
class FizzReleaseConfigError(FizzReleaseError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-RELS03"

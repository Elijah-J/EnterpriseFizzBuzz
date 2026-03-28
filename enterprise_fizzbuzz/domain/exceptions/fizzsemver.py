"""Enterprise FizzBuzz Platform - FizzSemVer Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzSemVerError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzSemVer: {r}", error_code="EFP-SEMV00", context={"reason": r})
class FizzSemVerParseError(FizzSemVerError):
    def __init__(self, v: str) -> None: super().__init__(f"Cannot parse version: {v}"); self.error_code="EFP-SEMV01"
class FizzSemVerConfigError(FizzSemVerError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-SEMV02"

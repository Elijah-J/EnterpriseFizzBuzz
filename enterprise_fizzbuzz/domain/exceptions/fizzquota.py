"""Enterprise FizzBuzz Platform - FizzQuota Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzQuotaError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzQuota: {r}", error_code="EFP-QUOT00", context={"reason": r})
class FizzQuotaNotFoundError(FizzQuotaError):
    def __init__(self, s: str) -> None: super().__init__(f"Quota not found: {s}"); self.error_code="EFP-QUOT01"
class FizzQuotaExceededError(FizzQuotaError):
    def __init__(self, s: str, u: float, l: float) -> None: super().__init__(f"Quota exceeded for {s}: {u}/{l}"); self.error_code="EFP-QUOT02"
class FizzQuotaConfigError(FizzQuotaError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-QUOT03"

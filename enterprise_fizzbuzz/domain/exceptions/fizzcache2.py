"""Enterprise FizzBuzz Platform - FizzCache2 Errors (EFP-CA2-00..04)"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzCache2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzCache2: {r}", error_code="EFP-CA2-00", context={"reason": r})
class FizzCache2KeyError(FizzCache2Error):
    def __init__(self, k: str) -> None: super().__init__(f"Key: {k}"); self.error_code="EFP-CA2-01"
class FizzCache2PubSubError(FizzCache2Error):
    def __init__(self, r: str) -> None: super().__init__(f"PubSub: {r}"); self.error_code="EFP-CA2-02"
class FizzCache2CapacityError(FizzCache2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Capacity: {r}"); self.error_code="EFP-CA2-03"
class FizzCache2ConfigError(FizzCache2Error):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-CA2-04"

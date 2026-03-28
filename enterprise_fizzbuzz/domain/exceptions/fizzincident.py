"""Enterprise FizzBuzz Platform - FizzIncident Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzIncidentError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzIncident: {r}", error_code="EFP-INC00", context={"reason": r})
class FizzIncidentNotFoundError(FizzIncidentError):
    def __init__(self, i: str) -> None: super().__init__(f"Not found: {i}"); self.error_code="EFP-INC01"
class FizzIncidentStateError(FizzIncidentError):
    def __init__(self, r: str) -> None: super().__init__(f"State: {r}"); self.error_code="EFP-INC02"
class FizzIncidentConfigError(FizzIncidentError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-INC03"

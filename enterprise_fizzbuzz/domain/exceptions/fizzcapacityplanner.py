"""Enterprise FizzBuzz Platform - FizzCapacityPlanner Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzCapacityPlannerError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzCapacityPlanner: {r}", error_code="EFP-CAP00", context={"reason": r})
class FizzCapacityPlannerForecastError(FizzCapacityPlannerError):
    def __init__(self, r: str) -> None: super().__init__(f"Forecast: {r}"); self.error_code="EFP-CAP01"
class FizzCapacityPlannerConfigError(FizzCapacityPlannerError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-CAP02"

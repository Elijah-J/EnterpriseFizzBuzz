"""Enterprise FizzBuzz Platform - FizzCostOptimizer Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzCostOptimizerError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzCostOptimizer: {r}", error_code="EFP-COST00", context={"reason": r})
class FizzCostOptimizerBudgetError(FizzCostOptimizerError):
    def __init__(self, r: str) -> None: super().__init__(f"Budget: {r}"); self.error_code="EFP-COST01"
class FizzCostOptimizerConfigError(FizzCostOptimizerError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-COST02"

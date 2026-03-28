"""Enterprise FizzBuzz Platform - FizzFeatureFlagV2 Errors (EFP-FFV2-00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzFeatureFlagV2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzFeatureFlagV2: {r}", error_code="EFP-FFV2-00", context={"reason": r})
class FizzFeatureFlagV2NotFoundError(FizzFeatureFlagV2Error):
    def __init__(self, name: str) -> None:
        super().__init__(f"Flag not found: {name}"); self.error_code = "EFP-FFV2-01"
class FizzFeatureFlagV2EvaluationError(FizzFeatureFlagV2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"Evaluation: {r}"); self.error_code = "EFP-FFV2-02"
class FizzFeatureFlagV2TargetingError(FizzFeatureFlagV2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"Targeting: {r}"); self.error_code = "EFP-FFV2-03"
class FizzFeatureFlagV2ABTestError(FizzFeatureFlagV2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"ABTest: {r}"); self.error_code = "EFP-FFV2-04"
class FizzFeatureFlagV2ConfigError(FizzFeatureFlagV2Error):
    def __init__(self, p: str, r: str) -> None:
        super().__init__(f"Config {p}: {r}"); self.error_code = "EFP-FFV2-05"

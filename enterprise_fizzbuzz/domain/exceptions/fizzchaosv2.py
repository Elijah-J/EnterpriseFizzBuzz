"""Enterprise FizzBuzz Platform - FizzChaosV2 Errors (EFP-CHV2-00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzChaosV2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzChaosV2: {r}", error_code="EFP-CHV2-00", context={"reason": r})
class FizzChaosV2ExperimentError(FizzChaosV2Error):
    def __init__(self, exp_id: str, r: str) -> None:
        super().__init__(f"Experiment {exp_id}: {r}"); self.error_code = "EFP-CHV2-01"
class FizzChaosV2SteadyStateError(FizzChaosV2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"SteadyState: {r}"); self.error_code = "EFP-CHV2-02"
class FizzChaosV2GameDayError(FizzChaosV2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"GameDay: {r}"); self.error_code = "EFP-CHV2-03"
class FizzChaosV2AbortError(FizzChaosV2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"Abort: {r}"); self.error_code = "EFP-CHV2-04"
class FizzChaosV2ConfigError(FizzChaosV2Error):
    def __init__(self, p: str, r: str) -> None:
        super().__init__(f"Config {p}: {r}"); self.error_code = "EFP-CHV2-05"

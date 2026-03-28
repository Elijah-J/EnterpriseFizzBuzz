"""Enterprise FizzBuzz Platform - FizzAPM Errors (EFP-APM00..04)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzAPMError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzAPM: {r}", error_code="EFP-APM00", context={"reason": r})
class FizzAPMSpanError(FizzAPMError):
    def __init__(self, r: str) -> None: super().__init__(f"Span: {r}"); self.error_code="EFP-APM01"
class FizzAPMTraceError(FizzAPMError):
    def __init__(self, r: str) -> None: super().__init__(f"Trace: {r}"); self.error_code="EFP-APM02"
class FizzAPMAnomalyError(FizzAPMError):
    def __init__(self, r: str) -> None: super().__init__(f"Anomaly: {r}"); self.error_code="EFP-APM03"
class FizzAPMConfigError(FizzAPMError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-APM04"

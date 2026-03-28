"""Enterprise FizzBuzz Platform - FizzMetricsV2 Errors (EFP-MET2-00..04)"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzMetricsV2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzMetricsV2: {r}", error_code="EFP-MET2-00", context={"reason": r})
class FizzMetricsV2QueryError(FizzMetricsV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Query: {r}"); self.error_code="EFP-MET2-01"
class FizzMetricsV2AlertError(FizzMetricsV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Alert: {r}"); self.error_code="EFP-MET2-02"
class FizzMetricsV2RetentionError(FizzMetricsV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Retention: {r}"); self.error_code="EFP-MET2-03"
class FizzMetricsV2ConfigError(FizzMetricsV2Error):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-MET2-04"

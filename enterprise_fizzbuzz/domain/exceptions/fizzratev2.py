"""Enterprise FizzBuzz Platform - FizzRateV2 Errors (EFP-RTV2-00 .. EFP-RTV2-04)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzRateV2Error(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzRateV2 error: {reason}", error_code="EFP-RTV2-00", context={"reason": reason})
class FizzRateV2LimitExceededError(FizzRateV2Error):
    def __init__(self, key: str) -> None:
        super().__init__(f"Rate limit exceeded: {key}"); self.error_code = "EFP-RTV2-01"
class FizzRateV2AlgorithmError(FizzRateV2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Algorithm: {reason}"); self.error_code = "EFP-RTV2-02"
class FizzRateV2BucketError(FizzRateV2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Bucket: {reason}"); self.error_code = "EFP-RTV2-03"
class FizzRateV2ConfigError(FizzRateV2Error):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-RTV2-04"

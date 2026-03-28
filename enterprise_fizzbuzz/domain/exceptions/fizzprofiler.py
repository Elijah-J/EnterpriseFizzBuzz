"""Enterprise FizzBuzz Platform - FizzProfiler Errors (EFP-PRF00 .. EFP-PRF10)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzProfilerError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzProfiler error: {reason}", error_code="EFP-PRF00", context={"reason": reason})

class FizzProfilerSessionError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Session: {reason}"); self.error_code = "EFP-PRF01"

class FizzProfilerSampleError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Sample: {reason}"); self.error_code = "EFP-PRF02"

class FizzProfilerCallGraphError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Call graph: {reason}"); self.error_code = "EFP-PRF03"

class FizzProfilerMemoryError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Memory: {reason}"); self.error_code = "EFP-PRF04"

class FizzProfilerHotspotError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Hotspot: {reason}"); self.error_code = "EFP-PRF05"

class FizzProfilerRegressionError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Regression: {reason}"); self.error_code = "EFP-PRF06"

class FizzProfilerExportError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Export: {reason}"); self.error_code = "EFP-PRF07"

class FizzProfilerContinuousError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Continuous: {reason}"); self.error_code = "EFP-PRF08"

class FizzProfilerTraceError(FizzProfilerError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Trace: {reason}"); self.error_code = "EFP-PRF09"

class FizzProfilerConfigError(FizzProfilerError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-PRF10"

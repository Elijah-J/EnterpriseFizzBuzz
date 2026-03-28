"""Enterprise FizzBuzz Platform - FizzTelemetry Errors (EFP-TEL00 .. EFP-TEL06)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzTelemetryError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzTelemetry error: {reason}", error_code="EFP-TEL00", context={"reason": reason})
class FizzTelemetryEventError(FizzTelemetryError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Event: {reason}"); self.error_code = "EFP-TEL01"
class FizzTelemetryErrorReportError(FizzTelemetryError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Error report: {reason}"); self.error_code = "EFP-TEL02"
class FizzTelemetrySessionError(FizzTelemetryError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Session: {reason}"); self.error_code = "EFP-TEL03"
class FizzTelemetryPerformanceError(FizzTelemetryError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Performance: {reason}"); self.error_code = "EFP-TEL04"
class FizzTelemetryExportError(FizzTelemetryError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Export: {reason}"); self.error_code = "EFP-TEL05"
class FizzTelemetryConfigError(FizzTelemetryError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-TEL06"

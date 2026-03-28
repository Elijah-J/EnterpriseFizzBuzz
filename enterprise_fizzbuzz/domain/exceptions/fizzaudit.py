"""Enterprise FizzBuzz Platform - FizzAudit Errors (EFP-AUD00 .. EFP-AUD08)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzAuditError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzAudit error: {reason}", error_code="EFP-AUD00", context={"reason": reason})
class FizzAuditChainError(FizzAuditError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Chain: {reason}"); self.error_code = "EFP-AUD01"
class FizzAuditEntryNotFoundError(FizzAuditError):
    def __init__(self, entry_id: str) -> None:
        super().__init__(f"Entry not found: {entry_id}"); self.error_code = "EFP-AUD02"
class FizzAuditRetentionError(FizzAuditError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Retention: {reason}"); self.error_code = "EFP-AUD03"
class FizzAuditQueryError(FizzAuditError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Query: {reason}"); self.error_code = "EFP-AUD04"
class FizzAuditExportError(FizzAuditError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Export: {reason}"); self.error_code = "EFP-AUD05"
class FizzAuditTamperError(FizzAuditError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Tamper detected: {reason}"); self.error_code = "EFP-AUD06"
class FizzAuditConfigError(FizzAuditError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-AUD07"

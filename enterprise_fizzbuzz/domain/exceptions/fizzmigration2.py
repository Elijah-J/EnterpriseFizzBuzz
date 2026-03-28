"""Enterprise FizzBuzz Platform - FizzMigration2 Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzMigration2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzMigration2: {r}", error_code="EFP-MIG2-00", context={"reason": r})
class FizzMigration2ApplyError(FizzMigration2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Apply: {r}"); self.error_code="EFP-MIG2-01"
class FizzMigration2RollbackError(FizzMigration2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Rollback: {r}"); self.error_code="EFP-MIG2-02"
class FizzMigration2ConfigError(FizzMigration2Error):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-MIG2-03"

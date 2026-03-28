"""Enterprise FizzBuzz Platform - FizzBackup Errors (EFP-BKP00 .. EFP-BKP14)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzBackupError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzBackup error: {reason}", error_code="EFP-BKP00", context={"reason": reason})

class FizzBackupCreateError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Create: {reason}"); self.error_code = "EFP-BKP01"

class FizzBackupRestoreError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Restore: {reason}"); self.error_code = "EFP-BKP02"

class FizzBackupNotFoundError(FizzBackupError):
    def __init__(self, backup_id: str) -> None:
        super().__init__(f"Backup not found: {backup_id}"); self.error_code = "EFP-BKP03"

class FizzBackupVerifyError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Verify: {reason}"); self.error_code = "EFP-BKP04"

class FizzBackupRetentionError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Retention: {reason}"); self.error_code = "EFP-BKP05"

class FizzBackupEncryptionError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Encryption: {reason}"); self.error_code = "EFP-BKP06"

class FizzBackupScheduleError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Schedule: {reason}"); self.error_code = "EFP-BKP07"

class FizzBackupIncrementalError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Incremental: {reason}"); self.error_code = "EFP-BKP08"

class FizzBackupWALError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"WAL replay: {reason}"); self.error_code = "EFP-BKP09"

class FizzBackupStorageError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Storage: {reason}"); self.error_code = "EFP-BKP10"

class FizzBackupDRError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Disaster recovery: {reason}"); self.error_code = "EFP-BKP11"

class FizzBackupRPOError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"RPO violation: {reason}"); self.error_code = "EFP-BKP12"

class FizzBackupRTOError(FizzBackupError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"RTO violation: {reason}"); self.error_code = "EFP-BKP13"

class FizzBackupConfigError(FizzBackupError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-BKP14"

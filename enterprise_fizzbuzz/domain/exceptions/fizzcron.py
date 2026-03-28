"""Enterprise FizzBuzz Platform - FizzCron Errors (EFP-CRON00 .. EFP-CRON10)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzCronError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzCron error: {reason}", error_code="EFP-CRON00", context={"reason": reason})
class FizzCronJobNotFoundError(FizzCronError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job not found: {job_id}"); self.error_code = "EFP-CRON01"
class FizzCronScheduleError(FizzCronError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Schedule: {reason}"); self.error_code = "EFP-CRON02"
class FizzCronExecutionError(FizzCronError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Execution: {reason}"); self.error_code = "EFP-CRON03"
class FizzCronLockError(FizzCronError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Lock: {reason}"); self.error_code = "EFP-CRON04"
class FizzCronTimeoutError(FizzCronError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Timeout: {job_id}"); self.error_code = "EFP-CRON05"
class FizzCronRetryError(FizzCronError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Retry: {reason}"); self.error_code = "EFP-CRON06"
class FizzCronHistoryError(FizzCronError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"History: {reason}"); self.error_code = "EFP-CRON07"
class FizzCronConfigError(FizzCronError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-CRON08"

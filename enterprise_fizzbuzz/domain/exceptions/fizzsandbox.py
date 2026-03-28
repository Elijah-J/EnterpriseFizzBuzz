"""Enterprise FizzBuzz Platform - FizzSandbox Errors (EFP-SBX00 .. EFP-SBX08)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzSandboxError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzSandbox error: {reason}", error_code="EFP-SBX00", context={"reason": reason})
class FizzSandboxNotFoundError(FizzSandboxError):
    def __init__(self, sandbox_id: str) -> None:
        super().__init__(f"Sandbox not found: {sandbox_id}"); self.error_code = "EFP-SBX01"
class FizzSandboxExecutionError(FizzSandboxError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Execution: {reason}"); self.error_code = "EFP-SBX02"
class FizzSandboxTimeoutError(FizzSandboxError):
    def __init__(self, sandbox_id: str) -> None:
        super().__init__(f"Timeout: {sandbox_id}"); self.error_code = "EFP-SBX03"
class FizzSandboxResourceError(FizzSandboxError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Resource: {reason}"); self.error_code = "EFP-SBX04"
class FizzSandboxValidationError(FizzSandboxError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Validation: {reason}"); self.error_code = "EFP-SBX05"
class FizzSandboxSecurityError(FizzSandboxError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Security: {reason}"); self.error_code = "EFP-SBX06"
class FizzSandboxKilledError(FizzSandboxError):
    def __init__(self, sandbox_id: str) -> None:
        super().__init__(f"Killed: {sandbox_id}"); self.error_code = "EFP-SBX07"
class FizzSandboxConfigError(FizzSandboxError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-SBX08"

"""Enterprise FizzBuzz Platform - FizzSecurityScanner Errors (EFP-SEC00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzSecurityScannerError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzSecurityScanner: {r}", error_code="EFP-SEC00", context={"reason": r})
class FizzSecurityScannerSASTError(FizzSecurityScannerError):
    def __init__(self, r: str) -> None: super().__init__(f"SAST: {r}"); self.error_code="EFP-SEC01"
class FizzSecurityScannerDASTError(FizzSecurityScannerError):
    def __init__(self, r: str) -> None: super().__init__(f"DAST: {r}"); self.error_code="EFP-SEC02"
class FizzSecurityScannerDependencyError(FizzSecurityScannerError):
    def __init__(self, r: str) -> None: super().__init__(f"Dependency: {r}"); self.error_code="EFP-SEC03"
class FizzSecurityScannerSecretError(FizzSecurityScannerError):
    def __init__(self, r: str) -> None: super().__init__(f"Secret: {r}"); self.error_code="EFP-SEC04"
class FizzSecurityScannerConfigError(FizzSecurityScannerError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-SEC05"

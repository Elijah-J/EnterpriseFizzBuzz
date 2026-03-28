"""Enterprise FizzBuzz Platform - FizzConfig2 Errors (EFP-CFG2-00 .. EFP-CFG2-06)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzConfig2Error(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzConfig2 error: {reason}", error_code="EFP-CFG2-00", context={"reason": reason})
class FizzConfig2KeyNotFoundError(FizzConfig2Error):
    def __init__(self, ns: str, key: str) -> None:
        super().__init__(f"Key not found: {ns}/{key}"); self.error_code = "EFP-CFG2-01"
class FizzConfig2NamespaceError(FizzConfig2Error):
    def __init__(self, ns: str, reason: str) -> None:
        super().__init__(f"Namespace {ns}: {reason}"); self.error_code = "EFP-CFG2-02"
class FizzConfig2ValidationError(FizzConfig2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Validation: {reason}"); self.error_code = "EFP-CFG2-03"
class FizzConfig2VersionError(FizzConfig2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Version: {reason}"); self.error_code = "EFP-CFG2-04"
class FizzConfig2WatchError(FizzConfig2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Watch: {reason}"); self.error_code = "EFP-CFG2-05"
class FizzConfig2ConfigError(FizzConfig2Error):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-CFG2-06"

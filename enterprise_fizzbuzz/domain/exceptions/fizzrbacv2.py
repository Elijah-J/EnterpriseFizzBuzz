"""Enterprise FizzBuzz Platform - FizzRBACV2 Errors (EFP-RBAC2-00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzRBACV2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzRBACV2: {r}", error_code="EFP-RBAC2-00", context={"reason": r})
class FizzRBACV2RoleNotFoundError(FizzRBACV2Error):
    def __init__(self, n: str) -> None: super().__init__(f"Role not found: {n}"); self.error_code="EFP-RBAC2-01"
class FizzRBACV2PolicyError(FizzRBACV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Policy: {r}"); self.error_code="EFP-RBAC2-02"
class FizzRBACV2ScopeError(FizzRBACV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Scope: {r}"); self.error_code="EFP-RBAC2-03"
class FizzRBACV2InheritanceError(FizzRBACV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Inheritance: {r}"); self.error_code="EFP-RBAC2-04"
class FizzRBACV2ConfigError(FizzRBACV2Error):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-RBAC2-05"

"""Enterprise FizzBuzz Platform - FizzDILifecycle Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzDILifecycleError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzDILifecycle: {r}", error_code="EFP-DIL00", context={"reason": r})
class FizzDILifecycleResolutionError(FizzDILifecycleError):
    def __init__(self, n: str) -> None: super().__init__(f"Cannot resolve: {n}"); self.error_code="EFP-DIL01"
class FizzDILifecycleCycleError(FizzDILifecycleError):
    def __init__(self, r: str) -> None: super().__init__(f"Cycle: {r}"); self.error_code="EFP-DIL02"
class FizzDILifecycleDisposedError(FizzDILifecycleError):
    def __init__(self, r: str) -> None: super().__init__(f"Disposed: {r}"); self.error_code="EFP-DIL03"
class FizzDILifecycleConfigError(FizzDILifecycleError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-DIL04"

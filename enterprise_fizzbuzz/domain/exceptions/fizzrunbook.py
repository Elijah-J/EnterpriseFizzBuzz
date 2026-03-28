"""Enterprise FizzBuzz Platform - FizzRunbook Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzRunbookError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzRunbook: {r}", error_code="EFP-RNBK00", context={"reason": r})
class FizzRunbookNotFoundError(FizzRunbookError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-RNBK01"
class FizzRunbookExecutionError(FizzRunbookError):
    def __init__(self, r: str) -> None: super().__init__(f"Execution error: {r}"); self.error_code="EFP-RNBK02"
class FizzRunbookStateError(FizzRunbookError):
    def __init__(self, r: str) -> None: super().__init__(f"Invalid state: {r}"); self.error_code="EFP-RNBK03"
class FizzRunbookConfigError(FizzRunbookError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-RNBK04"

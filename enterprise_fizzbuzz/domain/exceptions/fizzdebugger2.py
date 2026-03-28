"""Enterprise FizzBuzz Platform - FizzDebugger2 Errors (EFP-DBG2-00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzDebugger2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzDebugger2: {r}", error_code="EFP-DBG2-00", context={"reason": r})
class FizzDebugger2BreakpointError(FizzDebugger2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"Breakpoint: {r}"); self.error_code = "EFP-DBG2-01"
class FizzDebugger2WatchError(FizzDebugger2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"Watch: {r}"); self.error_code = "EFP-DBG2-02"
class FizzDebugger2TimelineError(FizzDebugger2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"Timeline: {r}"); self.error_code = "EFP-DBG2-03"
class FizzDebugger2SessionError(FizzDebugger2Error):
    def __init__(self, r: str) -> None:
        super().__init__(f"Session: {r}"); self.error_code = "EFP-DBG2-04"
class FizzDebugger2ConfigError(FizzDebugger2Error):
    def __init__(self, p: str, r: str) -> None:
        super().__init__(f"Config {p}: {r}"); self.error_code = "EFP-DBG2-05"

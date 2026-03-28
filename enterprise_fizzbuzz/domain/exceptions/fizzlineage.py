"""Enterprise FizzBuzz Platform - FizzLineage Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzLineageError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzLineage: {r}", error_code="EFP-LIN00", context={"reason": r})
class FizzLineageNodeNotFoundError(FizzLineageError):
    def __init__(self, n: str) -> None: super().__init__(f"Node not found: {n}"); self.error_code="EFP-LIN01"
class FizzLineageConfigError(FizzLineageError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-LIN02"

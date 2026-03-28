"""Enterprise FizzBuzz Platform - FizzLLVM Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzLLVMError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzLLVM: {r}", error_code="EFP-LLVM00", context={"reason": r})
class FizzLLVMNotFoundError(FizzLLVMError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-LLVM01"

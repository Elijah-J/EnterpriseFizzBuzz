"""Enterprise FizzBuzz Platform - FizzGRPC Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzGRPCError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzGRPC: {r}", error_code="EFP-GRPC00", context={"reason": r})
class FizzGRPCNotFoundError(FizzGRPCError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-GRPC01"

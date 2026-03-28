"""Enterprise FizzBuzz Platform - FizzEtcd Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzEtcdError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzEtcd: {r}", error_code="EFP-ETCD00", context={"reason": r})
class FizzEtcdNotFoundError(FizzEtcdError):
    def __init__(self, k: str) -> None: super().__init__(f"Key not found: {k}"); self.error_code="EFP-ETCD01"
class FizzEtcdLeaseError(FizzEtcdError):
    def __init__(self, r: str) -> None: super().__init__(f"Lease error: {r}"); self.error_code="EFP-ETCD02"

"""Enterprise FizzBuzz Platform - FizzEventMesh Errors (EFP-EM00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzEventMeshError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzEventMesh: {r}", error_code="EFP-EM00", context={"reason": r})
class FizzEventMeshTopicError(FizzEventMeshError):
    def __init__(self, t: str, r: str) -> None: super().__init__(f"Topic {t}: {r}"); self.error_code="EFP-EM01"
class FizzEventMeshPublishError(FizzEventMeshError):
    def __init__(self, r: str) -> None: super().__init__(f"Publish: {r}"); self.error_code="EFP-EM02"
class FizzEventMeshSubscribeError(FizzEventMeshError):
    def __init__(self, r: str) -> None: super().__init__(f"Subscribe: {r}"); self.error_code="EFP-EM03"
class FizzEventMeshDeadLetterError(FizzEventMeshError):
    def __init__(self, r: str) -> None: super().__init__(f"DeadLetter: {r}"); self.error_code="EFP-EM04"
class FizzEventMeshConfigError(FizzEventMeshError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-EM05"

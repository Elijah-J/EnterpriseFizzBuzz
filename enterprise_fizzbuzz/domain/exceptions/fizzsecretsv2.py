"""Enterprise FizzBuzz Platform - FizzSecretsV2 Errors (EFP-SCV2-00..05)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzSecretsV2Error(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzSecretsV2: {r}", error_code="EFP-SCV2-00", context={"reason": r})
class FizzSecretsV2NotFoundError(FizzSecretsV2Error):
    def __init__(self, n: str) -> None: super().__init__(f"Not found: {n}"); self.error_code="EFP-SCV2-01"
class FizzSecretsV2RotationError(FizzSecretsV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Rotation: {r}"); self.error_code="EFP-SCV2-02"
class FizzSecretsV2LeaseError(FizzSecretsV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Lease: {r}"); self.error_code="EFP-SCV2-03"
class FizzSecretsV2GeneratorError(FizzSecretsV2Error):
    def __init__(self, r: str) -> None: super().__init__(f"Generator: {r}"); self.error_code="EFP-SCV2-04"
class FizzSecretsV2ConfigError(FizzSecretsV2Error):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-SCV2-05"

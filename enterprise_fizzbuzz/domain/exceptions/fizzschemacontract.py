"""Enterprise FizzBuzz Platform - FizzSchemaContract Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzSchemaContractError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzSchemaContract: {r}", error_code="EFP-SCHC00", context={"reason": r})
class FizzSchemaContractNotFoundError(FizzSchemaContractError):
    def __init__(self, s: str) -> None: super().__init__(f"Schema not found: {s}"); self.error_code="EFP-SCHC01"
class FizzSchemaContractConfigError(FizzSchemaContractError):
    def __init__(self, p: str, r: str) -> None: super().__init__(f"Config {p}: {r}"); self.error_code="EFP-SCHC02"
class FizzSchemaContractIncompatibleError(FizzSchemaContractError):
    def __init__(self, p: str, c: str) -> None: super().__init__(f"Incompatible: producer={p} consumer={c}"); self.error_code="EFP-SCHC03"

"""Enterprise FizzBuzz Platform - FizzDataLake Errors (EFP-DL00..06)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzDataLakeError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzDataLake: {reason}", error_code="EFP-DL00", context={"reason": reason})
class FizzDataLakeObjectNotFoundError(FizzDataLakeError):
    def __init__(self, obj_id: str) -> None:
        super().__init__(f"Object not found: {obj_id}"); self.error_code = "EFP-DL01"
class FizzDataLakeIngestError(FizzDataLakeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Ingest: {reason}"); self.error_code = "EFP-DL02"
class FizzDataLakeQueryError(FizzDataLakeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Query: {reason}"); self.error_code = "EFP-DL03"
class FizzDataLakeSchemaError(FizzDataLakeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Schema: {reason}"); self.error_code = "EFP-DL04"
class FizzDataLakePartitionError(FizzDataLakeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Partition: {reason}"); self.error_code = "EFP-DL05"
class FizzDataLakeConfigError(FizzDataLakeError):
    def __init__(self, p: str, r: str) -> None:
        super().__init__(f"Config {p}: {r}"); self.error_code = "EFP-DL06"

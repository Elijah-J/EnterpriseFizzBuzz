"""Enterprise FizzBuzz Platform - FizzNotebook Errors (EFP-NB00 .. EFP-NB14)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzNotebookError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzNotebook error: {reason}", error_code="EFP-NB00", context={"reason": reason})

class FizzNotebookKernelError(FizzNotebookError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Kernel: {reason}"); self.error_code = "EFP-NB01"

class FizzNotebookCellError(FizzNotebookError):
    def __init__(self, cell_id: str, reason: str) -> None:
        super().__init__(f"Cell {cell_id}: {reason}"); self.error_code = "EFP-NB02"

class FizzNotebookExecutionError(FizzNotebookError):
    def __init__(self, cell_id: str, reason: str) -> None:
        super().__init__(f"Execution {cell_id}: {reason}"); self.error_code = "EFP-NB03"

class FizzNotebookNotFoundError(FizzNotebookError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Notebook not found: {name}"); self.error_code = "EFP-NB04"

class FizzNotebookExistsError(FizzNotebookError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Notebook exists: {name}"); self.error_code = "EFP-NB05"

class FizzNotebookFormatError(FizzNotebookError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Format: {reason}"); self.error_code = "EFP-NB06"

class FizzNotebookExportError(FizzNotebookError):
    def __init__(self, fmt: str, reason: str) -> None:
        super().__init__(f"Export {fmt}: {reason}"); self.error_code = "EFP-NB07"

class FizzNotebookWidgetError(FizzNotebookError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Widget: {reason}"); self.error_code = "EFP-NB08"

class FizzNotebookSessionError(FizzNotebookError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Session: {reason}"); self.error_code = "EFP-NB09"

class FizzNotebookCheckpointError(FizzNotebookError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Checkpoint: {reason}"); self.error_code = "EFP-NB10"

class FizzNotebookDiffError(FizzNotebookError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Diff: {reason}"); self.error_code = "EFP-NB11"

class FizzNotebookVariableError(FizzNotebookError):
    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"Variable {name}: {reason}"); self.error_code = "EFP-NB12"

class FizzNotebookMagicError(FizzNotebookError):
    def __init__(self, magic: str, reason: str) -> None:
        super().__init__(f"Magic {magic}: {reason}"); self.error_code = "EFP-NB13"

class FizzNotebookConfigError(FizzNotebookError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-NB14"

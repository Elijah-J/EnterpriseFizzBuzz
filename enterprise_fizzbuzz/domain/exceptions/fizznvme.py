"""
Enterprise FizzBuzz Platform - FizzNVMe Storage Protocol Exceptions (EFP-NVM00 .. EFP-NVM14)

The FizzNVMe subsystem implements the NVM Express protocol for high-performance
block storage access within the Enterprise FizzBuzz Platform.  When a namespace
cannot be created, a command queue overflows, an I/O command targets an invalid
LBA range, or a controller reset fails, these exceptions provide the diagnostic
precision required to resolve storage protocol issues at the transport layer.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzNVMeError(FizzBuzzError):
    """Base exception for all FizzNVMe storage protocol errors.

    When the FizzNVMe controller encounters an invalid command, a
    namespace that cannot be located, or a queue depth violation,
    this exception (or one of its children) is raised.  The storage
    administrator has been paged.  The controller is in a safe state.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NVM00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzNVMeNamespaceError(FizzNVMeError):
    """Raised when a namespace operation fails."""

    def __init__(self, message: str, *, ns_id: Optional[str] = None) -> None:
        super().__init__(
            message,
            error_code="EFP-NVM01",
            context={"ns_id": ns_id},
        )
        self.ns_id = ns_id


class FizzNVMeNamespaceNotFoundError(FizzNVMeError):
    """Raised when a referenced namespace does not exist."""

    def __init__(self, ns_id: str) -> None:
        super().__init__(
            f"Namespace '{ns_id}' does not exist",
            error_code="EFP-NVM02",
            context={"ns_id": ns_id},
        )
        self.ns_id = ns_id


class FizzNVMeQueueError(FizzNVMeError):
    """Raised when a command queue operation fails."""

    def __init__(self, message: str, *, queue_id: Optional[str] = None) -> None:
        super().__init__(
            message,
            error_code="EFP-NVM03",
            context={"queue_id": queue_id},
        )
        self.queue_id = queue_id


class FizzNVMeQueueNotFoundError(FizzNVMeError):
    """Raised when a referenced command queue does not exist."""

    def __init__(self, queue_id: str) -> None:
        super().__init__(
            f"Command queue '{queue_id}' does not exist",
            error_code="EFP-NVM04",
            context={"queue_id": queue_id},
        )
        self.queue_id = queue_id


class FizzNVMeQueueFullError(FizzNVMeError):
    """Raised when a command queue has reached its depth limit."""

    def __init__(self, queue_id: str, depth: int) -> None:
        super().__init__(
            f"Command queue '{queue_id}' is full (depth={depth})",
            error_code="EFP-NVM05",
            context={"queue_id": queue_id, "depth": depth},
        )
        self.queue_id = queue_id
        self.depth = depth


class FizzNVMeCommandError(FizzNVMeError):
    """Raised when an I/O command cannot be processed."""

    def __init__(self, message: str, *, cmd_id: Optional[str] = None) -> None:
        super().__init__(
            message,
            error_code="EFP-NVM06",
            context={"cmd_id": cmd_id},
        )
        self.cmd_id = cmd_id


class FizzNVMeInvalidLBAError(FizzNVMeError):
    """Raised when an I/O command references an LBA outside the namespace range."""

    def __init__(self, ns_id: str, lba: int, num_blocks: int, max_lba: int) -> None:
        super().__init__(
            f"LBA range [{lba}..{lba + num_blocks - 1}] exceeds namespace "
            f"'{ns_id}' capacity ({max_lba} blocks)",
            error_code="EFP-NVM07",
            context={"ns_id": ns_id, "lba": lba, "num_blocks": num_blocks, "max_lba": max_lba},
        )
        self.ns_id = ns_id
        self.lba = lba


class FizzNVMeDataSizeMismatchError(FizzNVMeError):
    """Raised when write data size does not match the requested block count."""

    def __init__(self, expected_bytes: int, actual_bytes: int) -> None:
        super().__init__(
            f"Write data size mismatch: expected {expected_bytes} bytes, got {actual_bytes}",
            error_code="EFP-NVM08",
            context={"expected_bytes": expected_bytes, "actual_bytes": actual_bytes},
        )


class FizzNVMeControllerError(FizzNVMeError):
    """Raised when the NVMe controller encounters an internal error."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-NVM09",
        )


class FizzNVMeReadUnwrittenError(FizzNVMeError):
    """Raised when reading from an LBA range that has not been written."""

    def __init__(self, ns_id: str, lba: int, num_blocks: int) -> None:
        super().__init__(
            f"Read of unwritten LBA range [{lba}..{lba + num_blocks - 1}] in namespace '{ns_id}'",
            error_code="EFP-NVM10",
            context={"ns_id": ns_id, "lba": lba, "num_blocks": num_blocks},
        )
        self.ns_id = ns_id


class FizzNVMeDuplicateNamespaceError(FizzNVMeError):
    """Raised when attempting to create a namespace with a duplicate name."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Namespace with name '{name}' already exists",
            error_code="EFP-NVM11",
            context={"name": name},
        )
        self.name = name


class FizzNVMeDuplicateQueueError(FizzNVMeError):
    """Raised when attempting to create a queue with a duplicate name."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Command queue with name '{name}' already exists",
            error_code="EFP-NVM12",
            context={"name": name},
        )
        self.name = name


class FizzNVMeMiddlewareError(FizzNVMeError):
    """Raised when the FizzNVMe middleware encounters an internal error."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-NVM13",
        )


class FizzNVMeDashboardError(FizzNVMeError):
    """Raised when the FizzNVMe dashboard rendering fails."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-NVM14",
        )

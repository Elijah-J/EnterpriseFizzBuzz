"""
Enterprise FizzBuzz Platform - FizzFS — Virtual File System Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FileSystemError(FizzBuzzError):
    """Base exception for all FizzFS virtual file system operations.

    The FizzFS subsystem provides a POSIX-like virtual file system for
    navigating platform state. When file operations fail — open, read,
    write, stat, readdir — the appropriate subclass of this exception
    is raised with diagnostic context sufficient for post-mortem analysis.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-FS00"),
            context=kwargs.pop("context", {}),
        )


class FileNotFoundError_(FileSystemError):
    """Raised when a path does not resolve to any inode in the file system.

    The virtual file system walked the directory tree from root to the
    requested path component-by-component and failed to locate a matching
    directory entry. This is the VFS equivalent of ENOENT. The trailing
    underscore avoids shadowing the built-in FileNotFoundError, which
    applies to the host OS — a fundamentally less important file system.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"No such file or directory: '{path}'",
            error_code="EFP-FS01",
            context={"path": path},
        )


class PermissionDeniedError(FileSystemError):
    """Raised when an operation is denied by the inode permission bits.

    The requested operation (read, write, or execute) requires a
    permission bit that is not set on the target inode. In a real
    POSIX system this would trigger EACCES. Here, it means someone
    tried to write to /dev/null's parent directory without the
    appropriate access flags, which is a governance concern.
    """

    def __init__(self, path: str, operation: str) -> None:
        self.path = path
        self.operation = operation
        super().__init__(
            f"Permission denied: '{operation}' on '{path}'",
            error_code="EFP-FS02",
            context={"path": path, "operation": operation},
        )


class NotADirectoryError_(FileSystemError):
    """Raised when a path component is not a directory during traversal.

    While resolving a multi-component path, the VFS encountered a
    non-directory inode where a directory was expected. This is the
    ENOTDIR errno. The trailing underscore avoids shadowing the
    built-in NotADirectoryError.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"Not a directory: '{path}'",
            error_code="EFP-FS03",
            context={"path": path},
        )


class IsADirectoryError_(FileSystemError):
    """Raised when a file operation is attempted on a directory inode.

    The caller attempted to open, read, or write a path that resolves
    to a directory. Directories are not regular files and cannot be
    treated as byte streams. This is EISDIR.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"Is a directory: '{path}'",
            error_code="EFP-FS04",
            context={"path": path},
        )


class FileDescriptorError(FileSystemError):
    """Raised when an operation references an invalid file descriptor.

    The file descriptor number provided does not correspond to any
    open file in the fd table. Either the fd was never opened, or
    it was previously closed. This is EBADF.
    """

    def __init__(self, fd: int) -> None:
        self.fd = fd
        super().__init__(
            f"Bad file descriptor: {fd}",
            error_code="EFP-FS05",
            context={"fd": fd},
        )


class FileDescriptorLimitError(FileSystemError):
    """Raised when the process has exhausted its file descriptor quota.

    The enterprise fd limit (1024) has been reached. No additional
    files may be opened until existing descriptors are closed. This
    mirrors EMFILE. In production deployments, this limit ensures
    that no single FizzBuzz evaluation monopolizes the VFS fd table,
    preserving fair access for all concurrent evaluations.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(
            f"Too many open files: limit is {limit}",
            error_code="EFP-FS06",
            context={"limit": limit},
        )


class MountError(FileSystemError):
    """Raised when a mount or unmount operation fails.

    The VFS was unable to attach or detach a file system provider
    at the specified mount point. Common causes include mounting
    over an existing mount point, attempting to unmount a path
    that is not a mount boundary, or providing an invalid path.
    """

    def __init__(self, mount_point: str, reason: str) -> None:
        self.mount_point = mount_point
        super().__init__(
            f"Mount error at '{mount_point}': {reason}",
            error_code="EFP-FS07",
            context={"mount_point": mount_point, "reason": reason},
        )


class FileExistsError_(FileSystemError):
    """Raised when creating a file or directory that already exists.

    The target path already contains an inode. To overwrite, the
    caller must first remove the existing entry. This is EEXIST.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"File exists: '{path}'",
            error_code="EFP-FS08",
            context={"path": path},
        )


class ReadOnlyFileSystemError(FileSystemError):
    """Raised when a write operation targets a read-only mount.

    The target path resides on a mount point backed by a provider
    that does not support write operations. Virtual providers
    (proc, cache, dev) are read-only by design: platform state
    flows outward through the VFS, not inward.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"Read-only file system: '{path}'",
            error_code="EFP-FS09",
            context={"path": path},
        )


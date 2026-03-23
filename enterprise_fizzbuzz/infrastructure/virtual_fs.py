"""
Enterprise FizzBuzz Platform - FizzFS Virtual File System Module

Implements a POSIX-like in-memory virtual file system with mount points
for exposing platform state as a hierarchical namespace. Because the
Unix philosophy of "everything is a file" was always meant to apply to
FizzBuzz evaluation engines.

Features:
    - Inode-based file system with support for regular files, directories,
      symlinks, and character devices
    - File descriptor table with configurable limit (enterprise default: 1024)
    - Mount table with pluggable FizzFSProvider backends
    - Five built-in providers: /proc, /cache, /sys, /dev, /audit
    - POSIX-like operations: open, read, write, close, stat, readdir, mkdir
    - Interactive shell (FizzShell) with cd, ls, cat, echo, stat, mount,
      pwd, tree, and exit commands
    - ASCII dashboard with mount table, inode statistics, and directory tree
    - FSMiddleware for optional pipeline integration

The file system faithfully models real VFS semantics applied to a problem
domain where all "persistent" state exists for the duration of a single
CLI invocation. The inode table, fd table, and mount table are allocated
in-process memory and reclaimed on exit — much like tmpfs, but with
significantly more enterprise overhead per byte stored.
"""

from __future__ import annotations

import logging
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FileDescriptorError,
    FileDescriptorLimitError,
    FileExistsError_,
    FileNotFoundError_,
    FileSystemError,
    IsADirectoryError_,
    MountError,
    NotADirectoryError_,
    PermissionDeniedError,
    ReadOnlyFileSystemError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ── File Type Enum ──────────────────────────────────────────────────


class FileType(Enum):
    """Classification of inode types in the FizzFS virtual file system.

    REGULAR files store arbitrary byte content. DIRECTORY inodes contain
    child directory entries. SYMLINK inodes contain a target path string.
    CHARDEV inodes represent character devices with custom read/write
    handlers — used for /dev/null, /dev/random, /dev/fizz, and /dev/buzz.
    """

    REGULAR = auto()
    DIRECTORY = auto()
    SYMLINK = auto()
    CHARDEV = auto()


# ── Open Mode Flags ─────────────────────────────────────────────────


class OpenMode(Enum):
    """File open mode flags mirroring POSIX O_RDONLY, O_WRONLY, O_RDWR."""

    READ = "r"
    WRITE = "w"
    READ_WRITE = "rw"
    APPEND = "a"


# ── Inode ───────────────────────────────────────────────────────────


@dataclass
class Inode:
    """Metadata and data storage for a single file system object.

    Every file, directory, symlink, and device in FizzFS is backed by
    an inode. The inode stores the file type, permission bits (octal),
    size, timestamps, and — for regular files — the raw byte content.
    Directory inodes store their children as a dict of name-to-inode-number
    mappings. Character device inodes delegate reads and writes to
    registered handler callables.
    """

    ino: int
    file_type: FileType
    permissions: int = 0o644
    uid: int = 0
    gid: int = 0
    size: int = 0
    created: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: bytes = b""
    # Directory children: name -> inode number
    children: dict[str, int] = field(default_factory=dict)
    # Symlink target path
    link_target: str = ""
    # Character device handlers
    dev_read: Optional[Callable[[int], bytes]] = field(default=None, repr=False)
    dev_write: Optional[Callable[[bytes], int]] = field(default=None, repr=False)
    nlinks: int = 1

    def update_size(self) -> None:
        """Recalculate the size field from the data content."""
        if self.file_type == FileType.REGULAR:
            self.size = len(self.data)
        elif self.file_type == FileType.DIRECTORY:
            self.size = len(self.children) * 64  # Estimated dirent size


# ── Directory Entry ─────────────────────────────────────────────────


@dataclass
class DirectoryEntry:
    """A single entry in a directory listing.

    Maps a human-readable name to an inode number. This is the VFS
    equivalent of a struct dirent — the fundamental unit of directory
    traversal.
    """

    name: str
    ino: int
    file_type: FileType


# ── File Descriptor ─────────────────────────────────────────────────


@dataclass
class FileDescriptor:
    """An open file handle referencing an inode with a current offset.

    File descriptors are created by open() and destroyed by close().
    Each descriptor tracks the inode it references, the mode in which
    it was opened, and the current byte offset for sequential reads
    and writes.
    """

    fd: int
    ino: int
    mode: OpenMode
    offset: int = 0
    path: str = ""


# ── Stat Result ─────────────────────────────────────────────────────


@dataclass
class StatResult:
    """Result of a stat() system call on a path or file descriptor.

    Contains all metadata fields exposed by the inode, formatted for
    consumption by user-space tools (ls, stat, the dashboard).
    """

    ino: int
    file_type: FileType
    permissions: int
    nlinks: int
    uid: int
    gid: int
    size: int
    created: datetime
    modified: datetime
    accessed: datetime


# ── FizzFSProvider ABC ──────────────────────────────────────────────


class FizzFSProvider(ABC):
    """Abstract base class for virtual file system mount providers.

    Each provider supplies a virtual directory tree that is mounted at
    a specific path in the FizzFS namespace. Providers implement three
    operations: readdir (list directory contents), read_file (return
    file content as a string), and stat_file (return metadata).

    Providers are read-only by default. The SysProvider overrides this
    convention to allow runtime configuration writes.
    """

    @abstractmethod
    def readdir(self, relative_path: str) -> list[str]:
        """List entries in the directory at the given relative path.

        The relative_path is relative to the mount point root. An empty
        string or "/" denotes the mount root itself.
        """
        ...

    @abstractmethod
    def read_file(self, relative_path: str) -> str:
        """Read the content of a virtual file at the given relative path.

        Returns the file content as a UTF-8 string. Raises FileNotFoundError_
        if the path does not correspond to a readable file.
        """
        ...

    @abstractmethod
    def stat_file(self, relative_path: str) -> dict[str, Any]:
        """Return metadata for a virtual file or directory.

        The returned dict should contain at minimum: 'type' (FileType),
        'size' (int), and 'permissions' (int, octal).
        """
        ...

    def is_writable(self) -> bool:
        """Return True if this provider supports write operations."""
        return False

    def write_file(self, relative_path: str, content: str) -> None:
        """Write content to a virtual file. Default raises ReadOnlyFileSystemError."""
        raise ReadOnlyFileSystemError(relative_path)


# ── ProcProvider ────────────────────────────────────────────────────


class ProcProvider(FizzFSProvider):
    """Virtual /proc file system exposing FizzBuzz process information.

    Mirrors the Linux /proc filesystem in spirit: provides read-only
    virtual files that report platform runtime state. Files are generated
    on each read, reflecting the current state of the evaluation engine.
    """

    def __init__(
        self,
        *,
        version: str = "1.0.0",
        middleware_count: int = 0,
        start_time: Optional[float] = None,
    ) -> None:
        self._version = version
        self._middleware_count = middleware_count
        self._start_time = start_time or time.monotonic()
        self._files: dict[str, Callable[[], str]] = {
            "uptime": self._read_uptime,
            "version": self._read_version,
            "middleware_count": self._read_middleware_count,
            "status": self._read_status,
            "cmdline": self._read_cmdline,
            "meminfo": self._read_meminfo,
        }

    def _read_uptime(self) -> str:
        elapsed = time.monotonic() - self._start_time
        return f"{elapsed:.2f}\n"

    def _read_version(self) -> str:
        return f"Enterprise FizzBuzz Platform v{self._version}\n"

    def _read_middleware_count(self) -> str:
        return f"{self._middleware_count}\n"

    def _read_status(self) -> str:
        return "running\n"

    def _read_cmdline(self) -> str:
        import sys
        return " ".join(sys.argv) + "\n"

    def _read_meminfo(self) -> str:
        import sys
        # Report approximate memory usage of the Python process
        obj_count = len(list(range(100)))  # Placeholder
        return (
            f"Python objects (sampled): {obj_count}\n"
            f"sys.getsizeof(int): {sys.getsizeof(0)} bytes\n"
            f"sys.getsizeof(str): {sys.getsizeof('')} bytes\n"
            f"sys.getsizeof(list): {sys.getsizeof([])} bytes\n"
        )

    def set_middleware_count(self, count: int) -> None:
        """Update the middleware count reported by /proc/middleware_count."""
        self._middleware_count = count

    def readdir(self, relative_path: str) -> list[str]:
        path = relative_path.strip("/")
        if path == "":
            return sorted(self._files.keys())
        raise FileNotFoundError_(f"/proc/{relative_path}")

    def read_file(self, relative_path: str) -> str:
        path = relative_path.strip("/")
        if path in self._files:
            return self._files[path]()
        raise FileNotFoundError_(f"/proc/{relative_path}")

    def stat_file(self, relative_path: str) -> dict[str, Any]:
        path = relative_path.strip("/")
        if path == "":
            return {"type": FileType.DIRECTORY, "size": 0, "permissions": 0o555}
        if path in self._files:
            content = self._files[path]()
            return {
                "type": FileType.REGULAR,
                "size": len(content.encode("utf-8")),
                "permissions": 0o444,
            }
        raise FileNotFoundError_(f"/proc/{relative_path}")


# ── CacheProvider ───────────────────────────────────────────────────


class CacheProvider(FizzFSProvider):
    """Virtual /cache file system exposing MESI cache coherence statistics.

    Reads cache state from the platform's CacheStore (if available) and
    presents it as flat files: hits, misses, evictions, hit_rate, state.
    When no cache subsystem is configured, all files return "0" or "N/A".
    """

    def __init__(self, *, cache_store: Any = None) -> None:
        self._cache = cache_store
        self._files = ["hits", "misses", "evictions", "hit_rate", "state", "size"]

    def _get_stats(self) -> dict[str, str]:
        if self._cache is None:
            return {
                "hits": "0\n",
                "misses": "0\n",
                "evictions": "0\n",
                "hit_rate": "0.00%\n",
                "state": "not configured\n",
                "size": "0\n",
            }
        stats = getattr(self._cache, "get_stats", lambda: {})()
        return {
            "hits": f"{stats.get('hits', 0)}\n",
            "misses": f"{stats.get('misses', 0)}\n",
            "evictions": f"{stats.get('evictions', 0)}\n",
            "hit_rate": f"{stats.get('hit_rate', 0.0):.2f}%\n",
            "state": f"{stats.get('state', 'unknown')}\n",
            "size": f"{stats.get('size', 0)}\n",
        }

    def readdir(self, relative_path: str) -> list[str]:
        path = relative_path.strip("/")
        if path == "":
            return sorted(self._files)
        raise FileNotFoundError_(f"/cache/{relative_path}")

    def read_file(self, relative_path: str) -> str:
        path = relative_path.strip("/")
        stats = self._get_stats()
        if path in stats:
            return stats[path]
        raise FileNotFoundError_(f"/cache/{relative_path}")

    def stat_file(self, relative_path: str) -> dict[str, Any]:
        path = relative_path.strip("/")
        if path == "":
            return {"type": FileType.DIRECTORY, "size": 0, "permissions": 0o555}
        if path in self._files:
            content = self.read_file(relative_path)
            return {
                "type": FileType.REGULAR,
                "size": len(content.encode("utf-8")),
                "permissions": 0o444,
            }
        raise FileNotFoundError_(f"/cache/{relative_path}")


# ── SysProvider ─────────────────────────────────────────────────────


class SysProvider(FizzFSProvider):
    """Virtual /sys file system exposing the configuration tree.

    Mirrors the Linux sysfs concept: each configuration key is exposed
    as a file whose content is the configuration value. Nested keys
    are represented as subdirectories. Unlike other providers, /sys
    supports write operations for runtime configuration adjustment.
    """

    def __init__(self, *, config_tree: Optional[dict[str, Any]] = None) -> None:
        self._tree = config_tree or {}

    def _resolve(self, relative_path: str) -> Any:
        """Walk the config tree to the given path."""
        path = relative_path.strip("/")
        if path == "":
            return self._tree
        parts = path.split("/")
        node = self._tree
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                raise FileNotFoundError_(f"/sys/{relative_path}")
        return node

    def readdir(self, relative_path: str) -> list[str]:
        node = self._resolve(relative_path)
        if isinstance(node, dict):
            return sorted(node.keys())
        raise NotADirectoryError_(f"/sys/{relative_path}")

    def read_file(self, relative_path: str) -> str:
        node = self._resolve(relative_path)
        if isinstance(node, dict):
            raise IsADirectoryError_(f"/sys/{relative_path}")
        return f"{node}\n"

    def stat_file(self, relative_path: str) -> dict[str, Any]:
        node = self._resolve(relative_path)
        if isinstance(node, dict):
            return {"type": FileType.DIRECTORY, "size": 0, "permissions": 0o755}
        content = f"{node}\n"
        return {
            "type": FileType.REGULAR,
            "size": len(content.encode("utf-8")),
            "permissions": 0o644,
        }

    def is_writable(self) -> bool:
        return True

    def write_file(self, relative_path: str, content: str) -> None:
        """Write a value to a configuration key in the /sys tree."""
        path = relative_path.strip("/")
        if path == "":
            raise PermissionDeniedError("/sys", "write")
        parts = path.split("/")
        node = self._tree
        for part in parts[:-1]:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                raise FileNotFoundError_(f"/sys/{relative_path}")
        key = parts[-1]
        if not isinstance(node, dict):
            raise NotADirectoryError_(f"/sys/{'/'.join(parts[:-1])}")
        # Attempt type coercion to preserve existing types
        old_val = node.get(key)
        val = content.strip()
        if isinstance(old_val, bool):
            node[key] = val.lower() in ("true", "1", "yes")
        elif isinstance(old_val, int):
            try:
                node[key] = int(val)
            except ValueError:
                node[key] = val
        elif isinstance(old_val, float):
            try:
                node[key] = float(val)
            except ValueError:
                node[key] = val
        else:
            node[key] = val
        logger.info("SysProvider: wrote '%s' to /sys/%s", val, path)


# ── DevProvider ─────────────────────────────────────────────────────


class DevProvider(FizzFSProvider):
    """Virtual /dev file system providing character device files.

    Implements four canonical device files:
    - /dev/null: reads empty, writes are silently discarded
    - /dev/random: reads pseudo-random bytes as hex
    - /dev/fizz: always reads "Fizz\\n"
    - /dev/buzz: always reads "Buzz\\n"

    These devices follow the Unix tradition of exposing hardware (or in
    this case, evaluation primitives) as file-like interfaces.
    """

    DEVICES = ["null", "random", "fizz", "buzz", "zero", "fizzbuzz"]

    def readdir(self, relative_path: str) -> list[str]:
        path = relative_path.strip("/")
        if path == "":
            return sorted(self.DEVICES)
        raise FileNotFoundError_(f"/dev/{relative_path}")

    def read_file(self, relative_path: str) -> str:
        path = relative_path.strip("/")
        if path == "null":
            return ""
        if path == "random":
            return "".join(f"{random.randint(0, 255):02x}" for _ in range(32)) + "\n"
        if path == "fizz":
            return "Fizz\n"
        if path == "buzz":
            return "Buzz\n"
        if path == "zero":
            return "\x00" * 64 + "\n"
        if path == "fizzbuzz":
            return "FizzBuzz\n"
        raise FileNotFoundError_(f"/dev/{relative_path}")

    def stat_file(self, relative_path: str) -> dict[str, Any]:
        path = relative_path.strip("/")
        if path == "":
            return {"type": FileType.DIRECTORY, "size": 0, "permissions": 0o755}
        if path in self.DEVICES:
            return {"type": FileType.CHARDEV, "size": 0, "permissions": 0o666}
        raise FileNotFoundError_(f"/dev/{relative_path}")


# ── AuditProvider ───────────────────────────────────────────────────


class AuditProvider(FizzFSProvider):
    """Virtual /audit file system exposing the event audit log.

    Presents event log entries as numbered files (0, 1, 2, ...) within
    the /audit directory. Each file contains the serialized event data.
    A special 'count' file reports the total number of audit entries.
    """

    def __init__(self) -> None:
        self._entries: list[str] = []

    def append(self, entry: str) -> None:
        """Add an audit log entry."""
        ts = datetime.now(timezone.utc).isoformat()
        self._entries.append(f"[{ts}] {entry}")

    @property
    def entries(self) -> list[str]:
        """Return a copy of all audit entries."""
        return list(self._entries)

    def readdir(self, relative_path: str) -> list[str]:
        path = relative_path.strip("/")
        if path == "":
            files = [str(i) for i in range(len(self._entries))]
            files.append("count")
            return files
        raise FileNotFoundError_(f"/audit/{relative_path}")

    def read_file(self, relative_path: str) -> str:
        path = relative_path.strip("/")
        if path == "count":
            return f"{len(self._entries)}\n"
        try:
            idx = int(path)
            if 0 <= idx < len(self._entries):
                return self._entries[idx] + "\n"
        except ValueError:
            pass
        raise FileNotFoundError_(f"/audit/{relative_path}")

    def stat_file(self, relative_path: str) -> dict[str, Any]:
        path = relative_path.strip("/")
        if path == "":
            return {"type": FileType.DIRECTORY, "size": 0, "permissions": 0o555}
        if path == "count":
            return {
                "type": FileType.REGULAR,
                "size": len(f"{len(self._entries)}\n"),
                "permissions": 0o444,
            }
        try:
            idx = int(path)
            if 0 <= idx < len(self._entries):
                content = self._entries[idx] + "\n"
                return {
                    "type": FileType.REGULAR,
                    "size": len(content.encode("utf-8")),
                    "permissions": 0o444,
                }
        except ValueError:
            pass
        raise FileNotFoundError_(f"/audit/{relative_path}")


# ── FizzFS ──────────────────────────────────────────────────────────


class FizzFS:
    """In-memory virtual file system with POSIX-like semantics.

    FizzFS manages an inode table, a file descriptor table, and a mount
    table. Regular file system operations (open, read, write, close, stat,
    readdir, mkdir) operate on inodes in the inode table. When a path
    crosses a mount boundary, the operation is delegated to the mounted
    FizzFSProvider.

    The maximum number of simultaneous file descriptors is capped at
    1024, in compliance with enterprise resource governance policies.
    """

    MAX_FDS: int = 1024
    ROOT_INO: int = 1

    def __init__(self) -> None:
        self._next_ino: int = 2
        self._next_fd: int = 3  # Reserve 0, 1, 2 for stdin/stdout/stderr
        self._inodes: dict[int, Inode] = {}
        self._fd_table: dict[int, FileDescriptor] = {}
        self._mount_table: dict[str, FizzFSProvider] = {}
        self._boot_time: float = time.monotonic()

        # Create root inode
        root = Inode(
            ino=self.ROOT_INO,
            file_type=FileType.DIRECTORY,
            permissions=0o755,
            nlinks=2,
        )
        root.children = {".": self.ROOT_INO, "..": self.ROOT_INO}
        self._inodes[self.ROOT_INO] = root

    # ── Inode allocation ────────────────────────────────────────────

    def _alloc_ino(self) -> int:
        """Allocate and return a new inode number."""
        ino = self._next_ino
        self._next_ino += 1
        return ino

    def _alloc_fd(self) -> int:
        """Allocate and return a new file descriptor number."""
        if len(self._fd_table) >= self.MAX_FDS:
            raise FileDescriptorLimitError(self.MAX_FDS)
        fd = self._next_fd
        self._next_fd += 1
        return fd

    # ── Mount operations ────────────────────────────────────────────

    def mount(self, path: str, provider: FizzFSProvider) -> None:
        """Mount a FizzFSProvider at the given absolute path.

        Creates any necessary intermediate directory inodes and registers
        the provider in the mount table. The mount point path must be
        absolute (start with /).
        """
        norm = self._normalize_path(path)
        if norm in self._mount_table:
            raise MountError(norm, "mount point already occupied")

        # Ensure mount point directory exists
        self._mkdir_parents(norm)
        self._mount_table[norm] = provider
        logger.info("FizzFS: mounted provider at %s", norm)

    def unmount(self, path: str) -> None:
        """Unmount the provider at the given path."""
        norm = self._normalize_path(path)
        if norm not in self._mount_table:
            raise MountError(norm, "not a mount point")
        del self._mount_table[norm]
        logger.info("FizzFS: unmounted %s", norm)

    def get_mount_table(self) -> dict[str, FizzFSProvider]:
        """Return a copy of the current mount table."""
        return dict(self._mount_table)

    # ── Path utilities ──────────────────────────────────────────────

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize a path: ensure leading /, collapse multiple /, remove trailing /."""
        if not path or path == "/":
            return "/"
        # Normalize separators
        path = path.replace("\\", "/")
        parts = path.split("/")
        resolved: list[str] = []
        for p in parts:
            if p == "" or p == ".":
                continue
            if p == "..":
                if resolved:
                    resolved.pop()
            else:
                resolved.append(p)
        return "/" + "/".join(resolved)

    def _find_mount(self, path: str) -> Optional[tuple[str, FizzFSProvider, str]]:
        """Find the deepest mount point that is a prefix of path.

        Returns (mount_point, provider, relative_path) or None.
        """
        norm = self._normalize_path(path)
        best_mount: Optional[str] = None
        for mp in self._mount_table:
            if norm == mp or norm.startswith(mp.rstrip("/") + "/"):
                if best_mount is None or len(mp) > len(best_mount):
                    best_mount = mp
        if best_mount is not None:
            provider = self._mount_table[best_mount]
            rel = norm[len(best_mount.rstrip("/")):]
            if not rel:
                rel = "/"
            return (best_mount, provider, rel)
        return None

    def _resolve_path(self, path: str) -> int:
        """Resolve a path to an inode number, walking the directory tree.

        Does not cross mount boundaries — use _find_mount first.
        """
        norm = self._normalize_path(path)
        if norm == "/":
            return self.ROOT_INO
        parts = norm.strip("/").split("/")
        current_ino = self.ROOT_INO
        for i, part in enumerate(parts):
            inode = self._inodes.get(current_ino)
            if inode is None:
                raise FileNotFoundError_(norm)
            if inode.file_type != FileType.DIRECTORY:
                raise NotADirectoryError_("/" + "/".join(parts[: i + 1]))
            if part not in inode.children:
                raise FileNotFoundError_(norm)
            current_ino = inode.children[part]
        return current_ino

    def _mkdir_parents(self, path: str) -> None:
        """Ensure all directory components of path exist, creating as needed."""
        norm = self._normalize_path(path)
        if norm == "/":
            return
        parts = norm.strip("/").split("/")
        current_ino = self.ROOT_INO
        for part in parts:
            inode = self._inodes[current_ino]
            if part in inode.children:
                current_ino = inode.children[part]
                next_inode = self._inodes.get(current_ino)
                if next_inode and next_inode.file_type != FileType.DIRECTORY:
                    raise NotADirectoryError_(part)
            else:
                new_ino = self._alloc_ino()
                new_dir = Inode(
                    ino=new_ino,
                    file_type=FileType.DIRECTORY,
                    permissions=0o755,
                    nlinks=2,
                )
                new_dir.children = {".": new_ino, "..": current_ino}
                self._inodes[new_ino] = new_dir
                inode.children[part] = new_ino
                inode.nlinks += 1
                current_ino = new_ino

    # ── POSIX operations ────────────────────────────────────────────

    def open(self, path: str, mode: OpenMode = OpenMode.READ) -> int:
        """Open a file and return a file descriptor.

        If the path falls within a mounted provider, a synthetic fd is
        created that delegates reads to the provider. If the path is in
        the inode tree, a standard fd is created referencing the inode.
        """
        norm = self._normalize_path(path)
        mount_info = self._find_mount(norm)

        if mount_info is not None:
            mp, provider, rel = mount_info
            # Verify the file exists on the provider
            try:
                stat_info = provider.stat_file(rel)
            except (FileNotFoundError_, FileSystemError):
                raise FileNotFoundError_(norm)
            if stat_info.get("type") == FileType.DIRECTORY:
                raise IsADirectoryError_(norm)
            if mode in (OpenMode.WRITE, OpenMode.APPEND, OpenMode.READ_WRITE):
                if not provider.is_writable():
                    raise ReadOnlyFileSystemError(norm)
            fd_num = self._alloc_fd()
            # Use a sentinel inode number (negative) to indicate provider-backed fd
            self._fd_table[fd_num] = FileDescriptor(
                fd=fd_num, ino=-1, mode=mode, offset=0, path=norm
            )
            return fd_num

        # Resolve in the inode tree
        try:
            ino = self._resolve_path(norm)
        except FileNotFoundError_:
            if mode in (OpenMode.WRITE, OpenMode.APPEND, OpenMode.READ_WRITE):
                # Create the file
                ino = self._create_file(norm)
            else:
                raise

        inode = self._inodes[ino]
        if inode.file_type == FileType.DIRECTORY:
            raise IsADirectoryError_(norm)

        # Check permissions
        if mode == OpenMode.READ and not (inode.permissions & 0o444):
            raise PermissionDeniedError(norm, "read")
        if mode in (OpenMode.WRITE, OpenMode.APPEND) and not (inode.permissions & 0o222):
            raise PermissionDeniedError(norm, "write")

        fd_num = self._alloc_fd()
        offset = len(inode.data) if mode == OpenMode.APPEND else 0
        if mode == OpenMode.WRITE:
            inode.data = b""
            inode.update_size()
            inode.modified = datetime.now(timezone.utc)
        self._fd_table[fd_num] = FileDescriptor(
            fd=fd_num, ino=ino, mode=mode, offset=offset, path=norm
        )
        inode.accessed = datetime.now(timezone.utc)
        return fd_num

    def read(self, fd: int, size: int = -1) -> bytes:
        """Read bytes from an open file descriptor.

        If the fd is backed by a provider, the entire file content is
        returned (providers do not support partial reads). For inode-backed
        fds, reads up to 'size' bytes from the current offset.
        """
        descriptor = self._get_fd(fd)
        if descriptor.mode == OpenMode.WRITE:
            raise PermissionDeniedError(descriptor.path, "read")

        # Provider-backed fd
        if descriptor.ino == -1:
            mount_info = self._find_mount(descriptor.path)
            if mount_info is None:
                raise FileNotFoundError_(descriptor.path)
            _, provider, rel = mount_info
            content = provider.read_file(rel)
            return content.encode("utf-8")

        inode = self._inodes.get(descriptor.ino)
        if inode is None:
            raise FileDescriptorError(fd)

        if inode.file_type == FileType.CHARDEV:
            if inode.dev_read is not None:
                return inode.dev_read(size if size > 0 else 4096)
            return b""

        data = inode.data
        if size < 0:
            result = data[descriptor.offset:]
            descriptor.offset = len(data)
        else:
            result = data[descriptor.offset:descriptor.offset + size]
            descriptor.offset += len(result)
        inode.accessed = datetime.now(timezone.utc)
        return result

    def write(self, fd: int, data: bytes) -> int:
        """Write bytes to an open file descriptor.

        For provider-backed fds, delegates to the provider's write_file.
        For inode-backed fds, writes data at the current offset and
        advances the offset.
        """
        descriptor = self._get_fd(fd)
        if descriptor.mode == OpenMode.READ:
            raise PermissionDeniedError(descriptor.path, "write")

        # Provider-backed fd
        if descriptor.ino == -1:
            mount_info = self._find_mount(descriptor.path)
            if mount_info is None:
                raise FileNotFoundError_(descriptor.path)
            _, provider, rel = mount_info
            if not provider.is_writable():
                raise ReadOnlyFileSystemError(descriptor.path)
            provider.write_file(rel, data.decode("utf-8", errors="replace"))
            return len(data)

        inode = self._inodes.get(descriptor.ino)
        if inode is None:
            raise FileDescriptorError(fd)

        if inode.file_type == FileType.CHARDEV:
            if inode.dev_write is not None:
                return inode.dev_write(data)
            return len(data)  # /dev/null behavior: silently consume

        # Write at offset
        current = bytearray(inode.data)
        offset = descriptor.offset
        end = offset + len(data)
        if end > len(current):
            current.extend(b"\x00" * (end - len(current)))
        current[offset:end] = data
        inode.data = bytes(current)
        descriptor.offset = end
        inode.update_size()
        inode.modified = datetime.now(timezone.utc)
        return len(data)

    def close(self, fd: int) -> None:
        """Close an open file descriptor, releasing it from the fd table."""
        if fd not in self._fd_table:
            raise FileDescriptorError(fd)
        del self._fd_table[fd]

    def stat(self, path: str) -> StatResult:
        """Return metadata for the file or directory at path."""
        norm = self._normalize_path(path)
        mount_info = self._find_mount(norm)

        if mount_info is not None:
            _, provider, rel = mount_info
            try:
                info = provider.stat_file(rel)
            except (FileNotFoundError_, FileSystemError):
                raise FileNotFoundError_(norm)
            now = datetime.now(timezone.utc)
            return StatResult(
                ino=0,
                file_type=info.get("type", FileType.REGULAR),
                permissions=info.get("permissions", 0o444),
                nlinks=1,
                uid=0,
                gid=0,
                size=info.get("size", 0),
                created=now,
                modified=now,
                accessed=now,
            )

        ino = self._resolve_path(norm)
        inode = self._inodes[ino]
        return StatResult(
            ino=inode.ino,
            file_type=inode.file_type,
            permissions=inode.permissions,
            nlinks=inode.nlinks,
            uid=inode.uid,
            gid=inode.gid,
            size=inode.size,
            created=inode.created,
            modified=inode.modified,
            accessed=inode.accessed,
        )

    def readdir(self, path: str) -> list[DirectoryEntry]:
        """List the contents of a directory.

        If the path is a mount point root, delegates to the provider's
        readdir. For inode-backed directories, returns DirectoryEntry
        objects for each child.
        """
        norm = self._normalize_path(path)
        mount_info = self._find_mount(norm)

        if mount_info is not None:
            _, provider, rel = mount_info
            try:
                names = provider.readdir(rel)
            except (FileNotFoundError_, FileSystemError):
                raise FileNotFoundError_(norm)
            entries = []
            for name in names:
                child_rel = rel.rstrip("/") + "/" + name
                try:
                    info = provider.stat_file(child_rel)
                    ft = info.get("type", FileType.REGULAR)
                except Exception:
                    ft = FileType.REGULAR
                entries.append(DirectoryEntry(name=name, ino=0, file_type=ft))
            return entries

        ino = self._resolve_path(norm)
        inode = self._inodes[ino]
        if inode.file_type != FileType.DIRECTORY:
            raise NotADirectoryError_(norm)

        entries: list[DirectoryEntry] = []
        for name, child_ino in sorted(inode.children.items()):
            if name in (".", ".."):
                continue
            child_inode = self._inodes.get(child_ino)
            ft = child_inode.file_type if child_inode else FileType.REGULAR
            entries.append(DirectoryEntry(name=name, ino=child_ino, file_type=ft))

        # Also include mount points that are direct children
        for mp in self._mount_table:
            mp_stripped = mp.rstrip("/")
            parent = self._normalize_path(norm).rstrip("/")
            if "/" in mp_stripped:
                mp_parent = mp_stripped.rsplit("/", 1)[0]
                mp_name = mp_stripped.rsplit("/", 1)[1]
            else:
                mp_parent = ""
                mp_name = mp_stripped
            if mp_parent == parent and not any(e.name == mp_name for e in entries):
                entries.append(DirectoryEntry(name=mp_name, ino=0, file_type=FileType.DIRECTORY))

        return sorted(entries, key=lambda e: e.name)

    def mkdir(self, path: str, permissions: int = 0o755) -> None:
        """Create a new directory at the given path.

        The parent directory must already exist. Raises FileExistsError_
        if the path already has an inode.
        """
        norm = self._normalize_path(path)
        if norm == "/":
            raise FileExistsError_("/")

        parent_path = norm.rsplit("/", 1)[0] or "/"
        name = norm.rsplit("/", 1)[1]

        parent_ino = self._resolve_path(parent_path)
        parent_inode = self._inodes[parent_ino]
        if parent_inode.file_type != FileType.DIRECTORY:
            raise NotADirectoryError_(parent_path)
        if name in parent_inode.children:
            raise FileExistsError_(norm)

        new_ino = self._alloc_ino()
        new_dir = Inode(
            ino=new_ino,
            file_type=FileType.DIRECTORY,
            permissions=permissions,
            nlinks=2,
        )
        new_dir.children = {".": new_ino, "..": parent_ino}
        self._inodes[new_ino] = new_dir
        parent_inode.children[name] = new_ino
        parent_inode.nlinks += 1
        parent_inode.modified = datetime.now(timezone.utc)

    def _create_file(self, path: str) -> int:
        """Create a new regular file at path, returning its inode number."""
        norm = self._normalize_path(path)
        parent_path = norm.rsplit("/", 1)[0] or "/"
        name = norm.rsplit("/", 1)[1]

        try:
            parent_ino = self._resolve_path(parent_path)
        except FileNotFoundError_:
            # Auto-create parent directories
            self._mkdir_parents(parent_path)
            parent_ino = self._resolve_path(parent_path)

        parent_inode = self._inodes[parent_ino]
        if parent_inode.file_type != FileType.DIRECTORY:
            raise NotADirectoryError_(parent_path)

        new_ino = self._alloc_ino()
        new_file = Inode(
            ino=new_ino,
            file_type=FileType.REGULAR,
            permissions=0o644,
        )
        self._inodes[new_ino] = new_file
        parent_inode.children[name] = new_ino
        parent_inode.modified = datetime.now(timezone.utc)
        return new_ino

    def _get_fd(self, fd: int) -> FileDescriptor:
        """Retrieve a file descriptor from the fd table."""
        if fd not in self._fd_table:
            raise FileDescriptorError(fd)
        return self._fd_table[fd]

    def create_symlink(self, path: str, target: str) -> None:
        """Create a symbolic link at path pointing to target."""
        norm = self._normalize_path(path)
        parent_path = norm.rsplit("/", 1)[0] or "/"
        name = norm.rsplit("/", 1)[1]

        parent_ino = self._resolve_path(parent_path)
        parent_inode = self._inodes[parent_ino]
        if parent_inode.file_type != FileType.DIRECTORY:
            raise NotADirectoryError_(parent_path)
        if name in parent_inode.children:
            raise FileExistsError_(norm)

        new_ino = self._alloc_ino()
        link_inode = Inode(
            ino=new_ino,
            file_type=FileType.SYMLINK,
            permissions=0o777,
            link_target=target,
        )
        link_inode.data = target.encode("utf-8")
        link_inode.update_size()
        self._inodes[new_ino] = link_inode
        parent_inode.children[name] = new_ino

    def unlink(self, path: str) -> None:
        """Remove a file (not a directory) from the file system."""
        norm = self._normalize_path(path)
        parent_path = norm.rsplit("/", 1)[0] or "/"
        name = norm.rsplit("/", 1)[1]

        parent_ino = self._resolve_path(parent_path)
        parent_inode = self._inodes[parent_ino]
        if name not in parent_inode.children:
            raise FileNotFoundError_(norm)
        child_ino = parent_inode.children[name]
        child_inode = self._inodes.get(child_ino)
        if child_inode and child_inode.file_type == FileType.DIRECTORY:
            raise IsADirectoryError_(norm)
        del parent_inode.children[name]
        if child_ino in self._inodes:
            self._inodes[child_ino].nlinks -= 1
            if self._inodes[child_ino].nlinks <= 0:
                del self._inodes[child_ino]

    # ── Convenience methods ─────────────────────────────────────────

    def read_file(self, path: str) -> str:
        """Read the entire content of a file as a UTF-8 string."""
        fd = self.open(path, OpenMode.READ)
        try:
            data = self.read(fd)
            return data.decode("utf-8", errors="replace")
        finally:
            self.close(fd)

    def write_file(self, path: str, content: str) -> None:
        """Write a UTF-8 string to a file, creating it if necessary."""
        fd = self.open(path, OpenMode.WRITE)
        try:
            self.write(fd, content.encode("utf-8"))
        finally:
            self.close(fd)

    def exists(self, path: str) -> bool:
        """Return True if the path exists in the file system."""
        try:
            self.stat(path)
            return True
        except (FileNotFoundError_, FileSystemError):
            return False

    @property
    def inode_count(self) -> int:
        """Return the total number of allocated inodes."""
        return len(self._inodes)

    @property
    def open_fd_count(self) -> int:
        """Return the number of currently open file descriptors."""
        return len(self._fd_table)

    @property
    def mount_count(self) -> int:
        """Return the number of active mount points."""
        return len(self._mount_table)

    @property
    def uptime(self) -> float:
        """Return seconds since boot."""
        return time.monotonic() - self._boot_time


# ── FizzShell ───────────────────────────────────────────────────────


class FizzShell:
    """Interactive REPL for navigating the FizzFS virtual file system.

    Provides a shell experience with familiar commands: cd, ls, cat,
    echo, stat, mount, pwd, tree, and exit. The prompt displays the
    current working directory, because situational awareness is critical
    when navigating in-memory FizzBuzz state.
    """

    def __init__(self, fs: FizzFS) -> None:
        self._fs = fs
        self._cwd = "/"
        self._running = False

    @property
    def cwd(self) -> str:
        """Return the current working directory."""
        return self._cwd

    def _resolve(self, path: str) -> str:
        """Resolve a path relative to cwd."""
        if path.startswith("/"):
            return self._fs._normalize_path(path)
        return self._fs._normalize_path(self._cwd.rstrip("/") + "/" + path)

    def execute(self, line: str) -> str:
        """Execute a single shell command and return output."""
        line = line.strip()
        if not line:
            return ""
        parts = line.split()
        cmd = parts[0]
        args = parts[1:]

        dispatch = {
            "cd": self._cmd_cd,
            "ls": self._cmd_ls,
            "cat": self._cmd_cat,
            "echo": self._cmd_echo,
            "stat": self._cmd_stat,
            "mount": self._cmd_mount,
            "pwd": self._cmd_pwd,
            "tree": self._cmd_tree,
            "mkdir": self._cmd_mkdir,
            "rm": self._cmd_rm,
            "touch": self._cmd_touch,
            "help": self._cmd_help,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
        }

        handler = dispatch.get(cmd)
        if handler is None:
            return f"fizzsh: command not found: {cmd}"
        try:
            return handler(args)
        except FileSystemError as e:
            return f"fizzsh: {e}"

    def _cmd_cd(self, args: list[str]) -> str:
        target = args[0] if args else "/"
        path = self._resolve(target)
        try:
            info = self._fs.stat(path)
            if info.file_type != FileType.DIRECTORY:
                return f"fizzsh: cd: not a directory: {path}"
            self._cwd = path
            return ""
        except FileSystemError as e:
            return f"fizzsh: cd: {e}"

    def _cmd_ls(self, args: list[str]) -> str:
        target = args[0] if args else self._cwd
        path = self._resolve(target)
        entries = self._fs.readdir(path)
        if not entries:
            return ""
        lines = []
        for entry in entries:
            prefix = "d" if entry.file_type == FileType.DIRECTORY else \
                     "l" if entry.file_type == FileType.SYMLINK else \
                     "c" if entry.file_type == FileType.CHARDEV else "-"
            lines.append(f"{prefix} {entry.name}")
        return "\n".join(lines)

    def _cmd_cat(self, args: list[str]) -> str:
        if not args:
            return "fizzsh: cat: missing operand"
        path = self._resolve(args[0])
        content = self._fs.read_file(path)
        return content.rstrip("\n")

    def _cmd_echo(self, args: list[str]) -> str:
        # Handle echo text > file
        if ">" in args:
            idx = args.index(">")
            text = " ".join(args[:idx])
            if idx + 1 < len(args):
                path = self._resolve(args[idx + 1])
                self._fs.write_file(path, text + "\n")
                return ""
            return "fizzsh: echo: missing file operand after >"
        return " ".join(args)

    def _cmd_stat(self, args: list[str]) -> str:
        if not args:
            return "fizzsh: stat: missing operand"
        path = self._resolve(args[0])
        info = self._fs.stat(path)
        lines = [
            f"  File: {path}",
            f"  Size: {info.size}\tInode: {info.ino}\tLinks: {info.nlinks}",
            f"  Type: {info.file_type.name}",
            f"  Mode: {oct(info.permissions)}",
            f"  Uid:  {info.uid}\tGid:  {info.gid}",
            f"  Created:  {info.created.isoformat()}",
            f"  Modified: {info.modified.isoformat()}",
            f"  Accessed: {info.accessed.isoformat()}",
        ]
        return "\n".join(lines)

    def _cmd_mount(self, args: list[str]) -> str:
        table = self._fs.get_mount_table()
        if not table:
            return "  No mount points configured."
        lines = []
        for mp, provider in sorted(table.items()):
            ptype = type(provider).__name__
            lines.append(f"  {ptype} on {mp} type fizzfs (ro)")
        return "\n".join(lines)

    def _cmd_pwd(self, args: list[str]) -> str:
        return self._cwd

    def _cmd_tree(self, args: list[str]) -> str:
        target = args[0] if args else self._cwd
        path = self._resolve(target)
        lines: list[str] = [path]
        self._tree_recursive(path, lines, "")
        return "\n".join(lines)

    def _tree_recursive(self, path: str, lines: list[str], prefix: str, depth: int = 0) -> None:
        if depth > 8:
            lines.append(f"{prefix}...")
            return
        try:
            entries = self._fs.readdir(path)
        except FileSystemError:
            return
        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.file_type == FileType.DIRECTORY:
                extension = "    " if is_last else "│   "
                child_path = path.rstrip("/") + "/" + entry.name
                self._tree_recursive(child_path, lines, prefix + extension, depth + 1)

    def _cmd_mkdir(self, args: list[str]) -> str:
        if not args:
            return "fizzsh: mkdir: missing operand"
        path = self._resolve(args[0])
        self._fs.mkdir(path)
        return ""

    def _cmd_rm(self, args: list[str]) -> str:
        if not args:
            return "fizzsh: rm: missing operand"
        path = self._resolve(args[0])
        self._fs.unlink(path)
        return ""

    def _cmd_touch(self, args: list[str]) -> str:
        if not args:
            return "fizzsh: touch: missing operand"
        path = self._resolve(args[0])
        if not self._fs.exists(path):
            self._fs.write_file(path, "")
        return ""

    def _cmd_help(self, args: list[str]) -> str:
        return (
            "FizzShell — Enterprise FizzBuzz Virtual File System Shell\n"
            "\n"
            "Commands:\n"
            "  cd [DIR]        Change working directory\n"
            "  ls [DIR]        List directory contents\n"
            "  cat FILE        Display file contents\n"
            "  echo TEXT > F   Write text to file\n"
            "  stat PATH       Display inode metadata\n"
            "  mount           List mount points\n"
            "  pwd             Print working directory\n"
            "  tree [DIR]      Display directory tree\n"
            "  mkdir DIR       Create directory\n"
            "  rm FILE         Remove file\n"
            "  touch FILE      Create empty file\n"
            "  help            Display this help\n"
            "  exit            Exit shell"
        )

    def _cmd_exit(self, args: list[str]) -> str:
        self._running = False
        return ""

    def run(self) -> None:
        """Start the interactive REPL loop."""
        print("FizzShell v1.0.0 — Enterprise FizzBuzz Virtual File System")
        print("Type 'help' for available commands, 'exit' to quit.\n")
        self._running = True
        while self._running:
            try:
                prompt = f"fizzfs:{self._cwd}$ "
                line = input(prompt)
                output = self.execute(line)
                if output:
                    print(output)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue


# ── FSDashboard ─────────────────────────────────────────────────────


class FSDashboard:
    """ASCII dashboard for the FizzFS virtual file system.

    Renders a comprehensive overview of the file system state including
    the mount table, inode statistics, open file descriptors, and a
    top-level directory tree.
    """

    @staticmethod
    def render(fs: FizzFS, *, width: int = 60) -> str:
        """Render the FizzFS dashboard as an ASCII string."""
        border = "+" + "-" * (width - 2) + "+"
        lines: list[str] = []

        # Header
        lines.append(border)
        lines.append(f"|{'FizzFS — Virtual File System Dashboard':^{width - 2}}|")
        lines.append(f"|{'Everything is a file. Especially FizzBuzz.':^{width - 2}}|")
        lines.append(border)

        # Statistics
        lines.append(f"|  {'Uptime:':<20}{fs.uptime:.2f}s{' ' * (width - 32)}|")
        lines.append(f"|  {'Inodes allocated:':<20}{fs.inode_count:<{width - 24}}|")
        lines.append(f"|  {'Open FDs:':<20}{fs.open_fd_count}/{fs.MAX_FDS:<{width - 25}}|")
        lines.append(f"|  {'Mount points:':<20}{fs.mount_count:<{width - 24}}|")
        lines.append(border)

        # Mount table
        lines.append(f"|{'Mount Table':^{width - 2}}|")
        lines.append(border)
        mount_table = fs.get_mount_table()
        if mount_table:
            for mp, provider in sorted(mount_table.items()):
                ptype = type(provider).__name__
                rw = "rw" if provider.is_writable() else "ro"
                entry = f"  {mp:<20} {ptype:<25} [{rw}]"
                lines.append(f"|{entry:<{width - 2}}|")
        else:
            lines.append(f"|  {'(no mount points)':^{width - 4}}|")
        lines.append(border)

        # Root directory listing
        lines.append(f"|{'Root Directory (/)':^{width - 2}}|")
        lines.append(border)
        try:
            entries = fs.readdir("/")
            for entry in entries:
                prefix = "d" if entry.file_type == FileType.DIRECTORY else "-"
                line = f"  {prefix} {entry.name}"
                lines.append(f"|{line:<{width - 2}}|")
        except FileSystemError:
            lines.append(f"|  {'(empty)':^{width - 4}}|")
        lines.append(border)

        return "\n".join(lines)


# ── FSMiddleware ────────────────────────────────────────────────────


class FSMiddleware(IMiddleware):
    """Middleware that writes evaluation results to the FizzFS /eval directory.

    For each number processed through the middleware pipeline, FSMiddleware
    creates a file at /eval/<number> containing the evaluation result.
    This provides a file-system-addressable view of all evaluations
    performed during the session — because every FizzBuzz result deserves
    its own inode.
    """

    PRIORITY: int = 930

    def __init__(self, fs: FizzFS) -> None:
        self._fs = fs
        self._eval_count = 0
        # Ensure /eval directory exists
        if not self._fs.exists("/eval"):
            self._fs.mkdir("/eval")

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)
        # Write the evaluation result to /eval/<number>
        try:
            number = context.number
            if result.results:
                output = result.results[-1].output if result.results else str(number)
            else:
                output = str(number)
            path = f"/eval/{number}"
            self._fs.write_file(path, f"{output}\n")
            self._eval_count += 1
        except Exception:
            logger.debug("FSMiddleware: failed to write eval file for %s", context.number)
        return result

    def get_name(self) -> str:
        return "FSMiddleware"

    def get_priority(self) -> int:
        return self.PRIORITY

    @property
    def eval_count(self) -> int:
        """Return the number of evaluation files written."""
        return self._eval_count


# ── Factory function ────────────────────────────────────────────────


def create_fizzfs(
    *,
    config_tree: Optional[dict[str, Any]] = None,
    cache_store: Any = None,
    version: str = "1.0.0",
    middleware_count: int = 0,
) -> tuple[FizzFS, AuditProvider]:
    """Create a fully configured FizzFS instance with all standard mount points.

    Returns a tuple of (FizzFS, AuditProvider) — the AuditProvider is
    returned separately so that callers can append entries to the audit
    log during execution.
    """
    fs = FizzFS()

    # Mount /proc
    proc_provider = ProcProvider(
        version=version,
        middleware_count=middleware_count,
    )
    fs.mount("/proc", proc_provider)

    # Mount /cache
    cache_provider = CacheProvider(cache_store=cache_store)
    fs.mount("/cache", cache_provider)

    # Mount /sys
    sys_provider = SysProvider(config_tree=config_tree or {})
    fs.mount("/sys", sys_provider)

    # Mount /dev
    dev_provider = DevProvider()
    fs.mount("/dev", dev_provider)

    # Mount /audit
    audit_provider = AuditProvider()
    fs.mount("/audit", audit_provider)

    # Create standard directories
    fs.mkdir("/tmp")
    fs.mkdir("/eval")
    fs.mkdir("/home")

    return fs, audit_provider

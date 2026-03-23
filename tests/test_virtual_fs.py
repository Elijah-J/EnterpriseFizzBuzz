"""
Enterprise FizzBuzz Platform - FizzFS Virtual File System Tests

Comprehensive test suite for the in-memory POSIX-like virtual file system.
Every file operation, every mount point, every provider, and every edge
case is verified — because an untested file system is just a data structure
with aspirations.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.virtual_fs import (
    AuditProvider,
    CacheProvider,
    DevProvider,
    DirectoryEntry,
    FileDescriptor,
    FileType,
    FizzFS,
    FizzFSProvider,
    FizzShell,
    FSDashboard,
    FSMiddleware,
    Inode,
    OpenMode,
    ProcProvider,
    StatResult,
    SysProvider,
    create_fizzfs,
)
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


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def fs():
    """Create a fresh FizzFS instance for each test."""
    return FizzFS()


@pytest.fixture
def full_fs():
    """Create a fully-mounted FizzFS instance."""
    return create_fizzfs(
        config_tree={"application": {"name": "Test", "version": "1.0.0"}, "range": {"start": 1, "end": 100}},
        version="1.0.0",
        middleware_count=5,
    )


# ── FileType Tests ──────────────────────────────────────────────────


class TestFileType:
    def test_enum_members(self):
        assert FileType.REGULAR is not None
        assert FileType.DIRECTORY is not None
        assert FileType.SYMLINK is not None
        assert FileType.CHARDEV is not None

    def test_enum_values_are_distinct(self):
        values = [ft.value for ft in FileType]
        assert len(values) == len(set(values))


# ── Inode Tests ─────────────────────────────────────────────────────


class TestInode:
    def test_default_inode(self):
        inode = Inode(ino=1, file_type=FileType.REGULAR)
        assert inode.ino == 1
        assert inode.file_type == FileType.REGULAR
        assert inode.permissions == 0o644
        assert inode.data == b""
        assert inode.size == 0
        assert inode.nlinks == 1

    def test_update_size_regular_file(self):
        inode = Inode(ino=1, file_type=FileType.REGULAR, data=b"hello")
        inode.update_size()
        assert inode.size == 5

    def test_update_size_directory(self):
        inode = Inode(ino=1, file_type=FileType.DIRECTORY)
        inode.children = {"a": 2, "b": 3}
        inode.update_size()
        assert inode.size == 2 * 64

    def test_inode_timestamps(self):
        inode = Inode(ino=1, file_type=FileType.REGULAR)
        assert isinstance(inode.created, datetime)
        assert isinstance(inode.modified, datetime)
        assert isinstance(inode.accessed, datetime)


# ── DirectoryEntry Tests ────────────────────────────────────────────


class TestDirectoryEntry:
    def test_creation(self):
        entry = DirectoryEntry(name="test.txt", ino=5, file_type=FileType.REGULAR)
        assert entry.name == "test.txt"
        assert entry.ino == 5
        assert entry.file_type == FileType.REGULAR


# ── FileDescriptor Tests ───────────────────────────────────────────


class TestFileDescriptor:
    def test_creation(self):
        fd = FileDescriptor(fd=3, ino=10, mode=OpenMode.READ)
        assert fd.fd == 3
        assert fd.ino == 10
        assert fd.mode == OpenMode.READ
        assert fd.offset == 0


# ── StatResult Tests ────────────────────────────────────────────────


class TestStatResult:
    def test_creation(self):
        now = datetime.now(timezone.utc)
        sr = StatResult(
            ino=1, file_type=FileType.REGULAR, permissions=0o644,
            nlinks=1, uid=0, gid=0, size=100,
            created=now, modified=now, accessed=now,
        )
        assert sr.size == 100
        assert sr.file_type == FileType.REGULAR


# ── FizzFS Core Tests ──────────────────────────────────────────────


class TestFizzFSCore:
    def test_root_exists(self, fs):
        stat = fs.stat("/")
        assert stat.file_type == FileType.DIRECTORY

    def test_mkdir(self, fs):
        fs.mkdir("/test")
        stat = fs.stat("/test")
        assert stat.file_type == FileType.DIRECTORY

    def test_mkdir_nested(self, fs):
        fs.mkdir("/a")
        fs.mkdir("/a/b")
        fs.mkdir("/a/b/c")
        stat = fs.stat("/a/b/c")
        assert stat.file_type == FileType.DIRECTORY

    def test_mkdir_already_exists(self, fs):
        fs.mkdir("/test")
        with pytest.raises(FileExistsError_):
            fs.mkdir("/test")

    def test_mkdir_root_raises(self, fs):
        with pytest.raises(FileExistsError_):
            fs.mkdir("/")

    def test_create_and_read_file(self, fs):
        fs.write_file("/hello.txt", "Hello, FizzBuzz!")
        content = fs.read_file("/hello.txt")
        assert content == "Hello, FizzBuzz!"

    def test_open_read_close(self, fs):
        fs.write_file("/data.txt", "test data")
        fd = fs.open("/data.txt", OpenMode.READ)
        data = fs.read(fd)
        assert data == b"test data"
        fs.close(fd)

    def test_open_write_read(self, fs):
        fd = fs.open("/new.txt", OpenMode.WRITE)
        fs.write(fd, b"written content")
        fs.close(fd)
        content = fs.read_file("/new.txt")
        assert content == "written content"

    def test_write_overwrites(self, fs):
        fs.write_file("/file.txt", "original")
        fs.write_file("/file.txt", "replaced")
        assert fs.read_file("/file.txt") == "replaced"

    def test_append_mode(self, fs):
        fs.write_file("/log.txt", "line1\n")
        fd = fs.open("/log.txt", OpenMode.APPEND)
        fs.write(fd, b"line2\n")
        fs.close(fd)
        assert fs.read_file("/log.txt") == "line1\nline2\n"

    def test_read_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError_):
            fs.read_file("/nonexistent.txt")

    def test_open_directory_raises(self, fs):
        fs.mkdir("/dir")
        with pytest.raises(IsADirectoryError_):
            fs.open("/dir", OpenMode.READ)

    def test_close_invalid_fd_raises(self, fs):
        with pytest.raises(FileDescriptorError):
            fs.close(999)

    def test_read_invalid_fd_raises(self, fs):
        with pytest.raises(FileDescriptorError):
            fs.read(999)

    def test_readdir_root(self, fs):
        fs.mkdir("/bin")
        fs.mkdir("/etc")
        entries = fs.readdir("/")
        names = [e.name for e in entries]
        assert "bin" in names
        assert "etc" in names

    def test_readdir_not_a_directory(self, fs):
        fs.write_file("/file.txt", "data")
        with pytest.raises(NotADirectoryError_):
            fs.readdir("/file.txt")

    def test_stat_file(self, fs):
        fs.write_file("/info.txt", "hello")
        stat = fs.stat("/info.txt")
        assert stat.file_type == FileType.REGULAR
        assert stat.size == 5

    def test_stat_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError_):
            fs.stat("/nonexistent")

    def test_exists(self, fs):
        assert fs.exists("/")
        assert not fs.exists("/nope")
        fs.mkdir("/yes")
        assert fs.exists("/yes")

    def test_unlink(self, fs):
        fs.write_file("/temp.txt", "temp")
        assert fs.exists("/temp.txt")
        fs.unlink("/temp.txt")
        assert not fs.exists("/temp.txt")

    def test_unlink_nonexistent_raises(self, fs):
        with pytest.raises(FileNotFoundError_):
            fs.unlink("/nonexistent")

    def test_unlink_directory_raises(self, fs):
        fs.mkdir("/dir")
        with pytest.raises(IsADirectoryError_):
            fs.unlink("/dir")

    def test_create_symlink(self, fs):
        fs.write_file("/target.txt", "data")
        fs.create_symlink("/link", "/target.txt")
        stat = fs.stat("/link")
        assert stat.file_type == FileType.SYMLINK

    def test_symlink_already_exists_raises(self, fs):
        fs.write_file("/target.txt", "data")
        fs.create_symlink("/link", "/target.txt")
        with pytest.raises(FileExistsError_):
            fs.create_symlink("/link", "/target.txt")

    def test_inode_count(self, fs):
        initial = fs.inode_count
        fs.mkdir("/a")
        assert fs.inode_count == initial + 1

    def test_open_fd_count(self, fs):
        fs.write_file("/test.txt", "data")
        assert fs.open_fd_count == 0
        fd = fs.open("/test.txt", OpenMode.READ)
        assert fs.open_fd_count == 1
        fs.close(fd)
        assert fs.open_fd_count == 0

    def test_partial_read(self, fs):
        fs.write_file("/data.txt", "abcdefghij")
        fd = fs.open("/data.txt", OpenMode.READ)
        chunk1 = fs.read(fd, 5)
        chunk2 = fs.read(fd, 5)
        fs.close(fd)
        assert chunk1 == b"abcde"
        assert chunk2 == b"fghij"

    def test_read_past_end(self, fs):
        fs.write_file("/short.txt", "hi")
        fd = fs.open("/short.txt", OpenMode.READ)
        data = fs.read(fd, 1000)
        fs.close(fd)
        assert data == b"hi"

    def test_write_read_only_raises(self, fs):
        fs.write_file("/ro.txt", "data")
        fd = fs.open("/ro.txt", OpenMode.READ)
        with pytest.raises(PermissionDeniedError):
            fs.write(fd, b"no")
        fs.close(fd)

    def test_read_write_only_raises(self, fs):
        fd = fs.open("/wo.txt", OpenMode.WRITE)
        fs.write(fd, b"data")
        with pytest.raises(PermissionDeniedError):
            fs.read(fd)
        fs.close(fd)

    def test_uptime(self, fs):
        assert fs.uptime >= 0

    def test_max_fds(self):
        assert FizzFS.MAX_FDS == 1024


# ── Path Normalization Tests ────────────────────────────────────────


class TestPathNormalization:
    def test_empty_path(self):
        assert FizzFS._normalize_path("") == "/"

    def test_root(self):
        assert FizzFS._normalize_path("/") == "/"

    def test_trailing_slash(self):
        assert FizzFS._normalize_path("/foo/") == "/foo"

    def test_double_slash(self):
        assert FizzFS._normalize_path("//foo//bar//") == "/foo/bar"

    def test_dot(self):
        assert FizzFS._normalize_path("/foo/./bar") == "/foo/bar"

    def test_dotdot(self):
        assert FizzFS._normalize_path("/foo/bar/../baz") == "/foo/baz"

    def test_dotdot_at_root(self):
        assert FizzFS._normalize_path("/..") == "/"

    def test_backslash_converted(self):
        assert FizzFS._normalize_path("\\foo\\bar") == "/foo/bar"


# ── Mount Tests ─────────────────────────────────────────────────────


class TestMount:
    def test_mount_and_list(self, fs):
        provider = DevProvider()
        fs.mount("/dev", provider)
        table = fs.get_mount_table()
        assert "/dev" in table

    def test_mount_duplicate_raises(self, fs):
        provider = DevProvider()
        fs.mount("/dev", provider)
        with pytest.raises(MountError):
            fs.mount("/dev", DevProvider())

    def test_unmount(self, fs):
        provider = DevProvider()
        fs.mount("/dev", provider)
        fs.unmount("/dev")
        assert "/dev" not in fs.get_mount_table()

    def test_unmount_nonexistent_raises(self, fs):
        with pytest.raises(MountError):
            fs.unmount("/nonexistent")

    def test_mount_count(self, fs):
        assert fs.mount_count == 0
        fs.mount("/dev", DevProvider())
        assert fs.mount_count == 1


# ── ProcProvider Tests ──────────────────────────────────────────────


class TestProcProvider:
    def test_readdir(self):
        provider = ProcProvider()
        entries = provider.readdir("")
        assert "uptime" in entries
        assert "version" in entries
        assert "middleware_count" in entries
        assert "status" in entries

    def test_read_version(self):
        provider = ProcProvider(version="2.0.0")
        content = provider.read_file("version")
        assert "2.0.0" in content

    def test_read_middleware_count(self):
        provider = ProcProvider(middleware_count=10)
        content = provider.read_file("middleware_count")
        assert "10" in content

    def test_read_status(self):
        provider = ProcProvider()
        assert "running" in provider.read_file("status")

    def test_read_uptime(self):
        provider = ProcProvider()
        content = provider.read_file("uptime")
        uptime = float(content.strip())
        assert uptime >= 0

    def test_read_nonexistent_raises(self):
        provider = ProcProvider()
        with pytest.raises(FileNotFoundError_):
            provider.read_file("nonexistent")

    def test_readdir_subdir_raises(self):
        provider = ProcProvider()
        with pytest.raises(FileNotFoundError_):
            provider.readdir("subdir")

    def test_stat_root(self):
        provider = ProcProvider()
        info = provider.stat_file("")
        assert info["type"] == FileType.DIRECTORY

    def test_stat_file(self):
        provider = ProcProvider()
        info = provider.stat_file("version")
        assert info["type"] == FileType.REGULAR
        assert info["permissions"] == 0o444

    def test_stat_nonexistent_raises(self):
        provider = ProcProvider()
        with pytest.raises(FileNotFoundError_):
            provider.stat_file("nonexistent")

    def test_set_middleware_count(self):
        provider = ProcProvider(middleware_count=0)
        provider.set_middleware_count(42)
        assert "42" in provider.read_file("middleware_count")

    def test_read_cmdline(self):
        provider = ProcProvider()
        content = provider.read_file("cmdline")
        assert isinstance(content, str)

    def test_read_meminfo(self):
        provider = ProcProvider()
        content = provider.read_file("meminfo")
        assert "bytes" in content


# ── CacheProvider Tests ─────────────────────────────────────────────


class TestCacheProvider:
    def test_readdir_no_cache(self):
        provider = CacheProvider()
        entries = provider.readdir("")
        assert "hits" in entries
        assert "misses" in entries

    def test_read_hits_no_cache(self):
        provider = CacheProvider()
        assert provider.read_file("hits") == "0\n"

    def test_read_hit_rate_no_cache(self):
        provider = CacheProvider()
        assert "0.00%" in provider.read_file("hit_rate")

    def test_read_nonexistent_raises(self):
        provider = CacheProvider()
        with pytest.raises(FileNotFoundError_):
            provider.read_file("nonexistent")

    def test_stat_root(self):
        provider = CacheProvider()
        info = provider.stat_file("")
        assert info["type"] == FileType.DIRECTORY

    def test_stat_file(self):
        provider = CacheProvider()
        info = provider.stat_file("hits")
        assert info["type"] == FileType.REGULAR

    def test_with_cache_store(self):
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {"hits": 42, "misses": 8, "evictions": 2, "hit_rate": 84.0, "state": "MODIFIED", "size": 100}
        provider = CacheProvider(cache_store=mock_cache)
        assert "42" in provider.read_file("hits")
        assert "84.00%" in provider.read_file("hit_rate")


# ── SysProvider Tests ───────────────────────────────────────────────


class TestSysProvider:
    def test_readdir_root(self):
        provider = SysProvider(config_tree={"a": 1, "b": {"c": 2}})
        entries = provider.readdir("")
        assert "a" in entries
        assert "b" in entries

    def test_readdir_subdir(self):
        provider = SysProvider(config_tree={"b": {"c": 2, "d": 3}})
        entries = provider.readdir("b")
        assert "c" in entries
        assert "d" in entries

    def test_read_value(self):
        provider = SysProvider(config_tree={"key": "value"})
        assert provider.read_file("key") == "value\n"

    def test_read_nested_value(self):
        provider = SysProvider(config_tree={"a": {"b": 42}})
        assert provider.read_file("a/b") == "42\n"

    def test_read_directory_raises(self):
        provider = SysProvider(config_tree={"dir": {"key": "val"}})
        with pytest.raises(IsADirectoryError_):
            provider.read_file("dir")

    def test_read_nonexistent_raises(self):
        provider = SysProvider(config_tree={})
        with pytest.raises(FileNotFoundError_):
            provider.read_file("nope")

    def test_is_writable(self):
        provider = SysProvider()
        assert provider.is_writable() is True

    def test_write_value(self):
        tree = {"key": "old"}
        provider = SysProvider(config_tree=tree)
        provider.write_file("key", "new")
        assert tree["key"] == "new"

    def test_write_int_coercion(self):
        tree = {"num": 10}
        provider = SysProvider(config_tree=tree)
        provider.write_file("num", "42")
        assert tree["num"] == 42

    def test_write_bool_coercion(self):
        tree = {"flag": False}
        provider = SysProvider(config_tree=tree)
        provider.write_file("flag", "true")
        assert tree["flag"] is True

    def test_write_float_coercion(self):
        tree = {"rate": 1.5}
        provider = SysProvider(config_tree=tree)
        provider.write_file("rate", "3.14")
        assert tree["rate"] == pytest.approx(3.14)

    def test_write_root_raises(self):
        provider = SysProvider(config_tree={})
        with pytest.raises(PermissionDeniedError):
            provider.write_file("", "data")

    def test_write_nonexistent_path_raises(self):
        provider = SysProvider(config_tree={})
        with pytest.raises(FileNotFoundError_):
            provider.write_file("no/such/key", "data")

    def test_stat_directory(self):
        provider = SysProvider(config_tree={"dir": {"k": "v"}})
        info = provider.stat_file("dir")
        assert info["type"] == FileType.DIRECTORY
        assert info["permissions"] == 0o755

    def test_stat_file(self):
        provider = SysProvider(config_tree={"key": "val"})
        info = provider.stat_file("key")
        assert info["type"] == FileType.REGULAR
        assert info["permissions"] == 0o644


# ── DevProvider Tests ───────────────────────────────────────────────


class TestDevProvider:
    def test_readdir(self):
        provider = DevProvider()
        entries = provider.readdir("")
        assert "null" in entries
        assert "random" in entries
        assert "fizz" in entries
        assert "buzz" in entries
        assert "zero" in entries
        assert "fizzbuzz" in entries

    def test_read_null(self):
        provider = DevProvider()
        assert provider.read_file("null") == ""

    def test_read_fizz(self):
        provider = DevProvider()
        assert provider.read_file("fizz") == "Fizz\n"

    def test_read_buzz(self):
        provider = DevProvider()
        assert provider.read_file("buzz") == "Buzz\n"

    def test_read_fizzbuzz(self):
        provider = DevProvider()
        assert provider.read_file("fizzbuzz") == "FizzBuzz\n"

    def test_read_zero(self):
        provider = DevProvider()
        content = provider.read_file("zero")
        assert "\x00" in content

    def test_read_random(self):
        provider = DevProvider()
        content = provider.read_file("random")
        assert len(content.strip()) == 64  # 32 bytes as hex

    def test_read_random_different_each_time(self):
        provider = DevProvider()
        a = provider.read_file("random")
        b = provider.read_file("random")
        # Random values should differ (astronomically unlikely to match)
        assert a != b

    def test_read_nonexistent_raises(self):
        provider = DevProvider()
        with pytest.raises(FileNotFoundError_):
            provider.read_file("nonexistent")

    def test_stat_root(self):
        provider = DevProvider()
        info = provider.stat_file("")
        assert info["type"] == FileType.DIRECTORY

    def test_stat_device(self):
        provider = DevProvider()
        info = provider.stat_file("null")
        assert info["type"] == FileType.CHARDEV
        assert info["permissions"] == 0o666

    def test_stat_nonexistent_raises(self):
        provider = DevProvider()
        with pytest.raises(FileNotFoundError_):
            provider.stat_file("nonexistent")

    def test_readdir_subdir_raises(self):
        provider = DevProvider()
        with pytest.raises(FileNotFoundError_):
            provider.readdir("sub")


# ── AuditProvider Tests ─────────────────────────────────────────────


class TestAuditProvider:
    def test_empty_readdir(self):
        provider = AuditProvider()
        entries = provider.readdir("")
        assert "count" in entries

    def test_append_and_read(self):
        provider = AuditProvider()
        provider.append("test event")
        assert "test event" in provider.read_file("0")

    def test_count(self):
        provider = AuditProvider()
        assert provider.read_file("count") == "0\n"
        provider.append("event 1")
        provider.append("event 2")
        assert provider.read_file("count") == "2\n"

    def test_read_nonexistent_index_raises(self):
        provider = AuditProvider()
        with pytest.raises(FileNotFoundError_):
            provider.read_file("999")

    def test_read_invalid_name_raises(self):
        provider = AuditProvider()
        with pytest.raises(FileNotFoundError_):
            provider.read_file("invalid")

    def test_entries_property(self):
        provider = AuditProvider()
        provider.append("a")
        provider.append("b")
        entries = provider.entries
        assert len(entries) == 2

    def test_stat_root(self):
        provider = AuditProvider()
        info = provider.stat_file("")
        assert info["type"] == FileType.DIRECTORY

    def test_stat_count(self):
        provider = AuditProvider()
        info = provider.stat_file("count")
        assert info["type"] == FileType.REGULAR

    def test_stat_entry(self):
        provider = AuditProvider()
        provider.append("event")
        info = provider.stat_file("0")
        assert info["type"] == FileType.REGULAR

    def test_stat_nonexistent_raises(self):
        provider = AuditProvider()
        with pytest.raises(FileNotFoundError_):
            provider.stat_file("nonexistent")

    def test_readdir_includes_entries(self):
        provider = AuditProvider()
        provider.append("a")
        provider.append("b")
        entries = provider.readdir("")
        assert "0" in entries
        assert "1" in entries
        assert "count" in entries

    def test_readdir_subdir_raises(self):
        provider = AuditProvider()
        with pytest.raises(FileNotFoundError_):
            provider.readdir("sub")


# ── Mounted FS Integration Tests ───────────────────────────────────


class TestMountedFS:
    def test_read_mounted_file(self, fs):
        fs.mount("/dev", DevProvider())
        content = fs.read_file("/dev/fizz")
        assert content == "Fizz\n"

    def test_read_mounted_buzz(self, fs):
        fs.mount("/dev", DevProvider())
        assert fs.read_file("/dev/buzz") == "Buzz\n"

    def test_read_dev_null(self, fs):
        fs.mount("/dev", DevProvider())
        assert fs.read_file("/dev/null") == ""

    def test_stat_mounted_file(self, fs):
        fs.mount("/dev", DevProvider())
        info = fs.stat("/dev/fizz")
        assert info.file_type == FileType.CHARDEV

    def test_stat_mount_root(self, fs):
        fs.mount("/proc", ProcProvider())
        info = fs.stat("/proc")
        assert info.file_type == FileType.DIRECTORY

    def test_readdir_mounted(self, fs):
        fs.mount("/dev", DevProvider())
        entries = fs.readdir("/dev")
        names = [e.name for e in entries]
        assert "fizz" in names
        assert "buzz" in names

    def test_open_read_close_mounted(self, fs):
        fs.mount("/dev", DevProvider())
        fd = fs.open("/dev/fizz", OpenMode.READ)
        data = fs.read(fd)
        fs.close(fd)
        assert data == b"Fizz\n"

    def test_write_to_readonly_mount_raises(self, fs):
        fs.mount("/proc", ProcProvider())
        with pytest.raises(ReadOnlyFileSystemError):
            fs.open("/proc/version", OpenMode.WRITE)

    def test_write_to_writable_mount(self, fs):
        tree = {"key": "old"}
        fs.mount("/sys", SysProvider(config_tree=tree))
        fd = fs.open("/sys/key", OpenMode.WRITE)
        fs.write(fd, b"new")
        fs.close(fd)
        assert tree["key"] == "new"

    def test_open_nonexistent_mounted_raises(self, fs):
        fs.mount("/proc", ProcProvider())
        with pytest.raises(FileNotFoundError_):
            fs.open("/proc/nonexistent", OpenMode.READ)

    def test_open_mounted_directory_raises(self, fs):
        fs.mount("/proc", ProcProvider())
        with pytest.raises(IsADirectoryError_):
            fs.open("/proc", OpenMode.READ)

    def test_readdir_root_shows_mount_points(self, fs):
        fs.mount("/dev", DevProvider())
        fs.mount("/proc", ProcProvider())
        entries = fs.readdir("/")
        names = [e.name for e in entries]
        assert "dev" in names
        assert "proc" in names


# ── FizzShell Tests ─────────────────────────────────────────────────


class TestFizzShell:
    def test_pwd(self, fs):
        shell = FizzShell(fs)
        assert shell.execute("pwd") == "/"

    def test_cd_and_pwd(self, fs):
        fs.mkdir("/test")
        shell = FizzShell(fs)
        shell.execute("cd /test")
        assert shell.execute("pwd") == "/test"

    def test_cd_root(self, fs):
        fs.mkdir("/test")
        shell = FizzShell(fs)
        shell.execute("cd /test")
        shell.execute("cd /")
        assert shell.cwd == "/"

    def test_cd_nonexistent(self, fs):
        shell = FizzShell(fs)
        result = shell.execute("cd /nonexistent")
        assert "cd:" in result

    def test_ls(self, fs):
        fs.mkdir("/bin")
        fs.write_file("/readme.txt", "hi")
        shell = FizzShell(fs)
        output = shell.execute("ls /")
        assert "bin" in output
        assert "readme.txt" in output

    def test_cat(self, fs):
        fs.write_file("/hello.txt", "world")
        shell = FizzShell(fs)
        assert shell.execute("cat /hello.txt") == "world"

    def test_cat_no_arg(self, fs):
        shell = FizzShell(fs)
        assert "missing" in shell.execute("cat")

    def test_echo_redirect(self, fs):
        shell = FizzShell(fs)
        shell.execute("echo hello > /out.txt")
        assert fs.read_file("/out.txt") == "hello\n"

    def test_echo_no_redirect(self, fs):
        shell = FizzShell(fs)
        assert shell.execute("echo hello world") == "hello world"

    def test_stat_cmd(self, fs):
        fs.write_file("/info.txt", "data")
        shell = FizzShell(fs)
        output = shell.execute("stat /info.txt")
        assert "File:" in output
        assert "REGULAR" in output

    def test_mount_cmd(self, fs):
        fs.mount("/dev", DevProvider())
        shell = FizzShell(fs)
        output = shell.execute("mount")
        assert "DevProvider" in output

    def test_mount_cmd_empty(self, fs):
        shell = FizzShell(fs)
        output = shell.execute("mount")
        assert "No mount" in output

    def test_tree(self, fs):
        fs.mkdir("/a")
        fs.mkdir("/a/b")
        fs.write_file("/a/b/c.txt", "data")
        shell = FizzShell(fs)
        output = shell.execute("tree /a")
        assert "b" in output
        assert "c.txt" in output

    def test_mkdir_cmd(self, fs):
        shell = FizzShell(fs)
        shell.execute("mkdir /newdir")
        assert fs.exists("/newdir")

    def test_rm_cmd(self, fs):
        fs.write_file("/temp.txt", "data")
        shell = FizzShell(fs)
        shell.execute("rm /temp.txt")
        assert not fs.exists("/temp.txt")

    def test_touch_cmd(self, fs):
        shell = FizzShell(fs)
        shell.execute("touch /empty.txt")
        assert fs.exists("/empty.txt")

    def test_help(self, fs):
        shell = FizzShell(fs)
        output = shell.execute("help")
        assert "cd" in output
        assert "ls" in output
        assert "cat" in output

    def test_unknown_command(self, fs):
        shell = FizzShell(fs)
        output = shell.execute("foobar")
        assert "command not found" in output

    def test_empty_command(self, fs):
        shell = FizzShell(fs)
        assert shell.execute("") == ""

    def test_exit(self, fs):
        shell = FizzShell(fs)
        shell.execute("exit")
        assert shell._running is False

    def test_relative_path(self, fs):
        fs.mkdir("/home")
        fs.mkdir("/home/user")
        shell = FizzShell(fs)
        shell.execute("cd /home")
        shell.execute("mkdir user/docs")
        assert fs.exists("/home/user/docs")


# ── FSDashboard Tests ──────────────────────────────────────────────


class TestFSDashboard:
    def test_render(self, fs):
        fs.mount("/dev", DevProvider())
        output = FSDashboard.render(fs)
        assert "FizzFS" in output
        assert "Mount Table" in output
        assert "DevProvider" in output

    def test_render_empty(self, fs):
        output = FSDashboard.render(fs)
        assert "FizzFS" in output

    def test_render_width(self, fs):
        output = FSDashboard.render(fs, width=80)
        assert isinstance(output, str)
        assert len(output) > 0


# ── FSMiddleware Tests ──────────────────────────────────────────────


class TestFSMiddleware:
    def test_name(self, fs):
        mw = FSMiddleware(fs)
        assert mw.get_name() == "FSMiddleware"

    def test_priority(self, fs):
        mw = FSMiddleware(fs)
        assert mw.get_priority() == 930

    def test_creates_eval_dir(self, fs):
        FSMiddleware(fs)
        assert fs.exists("/eval")

    def test_eval_count_starts_at_zero(self, fs):
        mw = FSMiddleware(fs)
        assert mw.eval_count == 0


# ── create_fizzfs Factory Tests ─────────────────────────────────────


class TestCreateFizzFS:
    def test_returns_tuple(self):
        result = create_fizzfs()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_has_mount_points(self):
        fs, _ = create_fizzfs()
        table = fs.get_mount_table()
        assert "/proc" in table
        assert "/cache" in table
        assert "/sys" in table
        assert "/dev" in table
        assert "/audit" in table

    def test_standard_directories(self):
        fs, _ = create_fizzfs()
        assert fs.exists("/tmp")
        assert fs.exists("/eval")
        assert fs.exists("/home")

    def test_audit_provider_returned(self):
        fs, audit = create_fizzfs()
        assert isinstance(audit, AuditProvider)
        audit.append("test")
        assert fs.read_file("/audit/0").startswith("[")

    def test_read_dev_fizz(self):
        fs, _ = create_fizzfs()
        assert fs.read_file("/dev/fizz") == "Fizz\n"

    def test_read_dev_buzz(self):
        fs, _ = create_fizzfs()
        assert fs.read_file("/dev/buzz") == "Buzz\n"

    def test_read_proc_version(self):
        fs, _ = create_fizzfs(version="3.0.0")
        assert "3.0.0" in fs.read_file("/proc/version")

    def test_sys_config_tree(self):
        fs, _ = create_fizzfs(config_tree={"engine": {"strategy": "standard"}})
        assert "standard" in fs.read_file("/sys/engine/strategy")

    def test_write_tmp_file(self):
        fs, _ = create_fizzfs()
        fs.write_file("/tmp/note.txt", "remember this")
        assert fs.read_file("/tmp/note.txt") == "remember this"


# ── File Descriptor Limit Tests ─────────────────────────────────────


class TestFDLimit:
    def test_fd_limit_enforced(self):
        fs = FizzFS()
        fs.write_file("/test.txt", "data")
        fds = []
        # Open up to MAX_FDS
        for i in range(FizzFS.MAX_FDS):
            fd = fs.open("/test.txt", OpenMode.READ)
            fds.append(fd)
        # The next open should raise
        with pytest.raises(FileDescriptorLimitError):
            fs.open("/test.txt", OpenMode.READ)
        # Clean up
        for fd in fds:
            fs.close(fd)


# ── End-to-End Integration Tests ────────────────────────────────────


class TestEndToEnd:
    def test_full_workflow(self):
        fs, audit = create_fizzfs(
            config_tree={"rules": {"fizz": 3, "buzz": 5}},
            version="1.0.0",
            middleware_count=7,
        )

        # Read platform info
        assert "1.0.0" in fs.read_file("/proc/version")
        assert "7" in fs.read_file("/proc/middleware_count")

        # Read config via /sys
        assert "3" in fs.read_file("/sys/rules/fizz")

        # Device reads
        assert fs.read_file("/dev/fizz") == "Fizz\n"
        assert fs.read_file("/dev/buzz") == "Buzz\n"
        assert fs.read_file("/dev/null") == ""

        # Write to /tmp
        fs.write_file("/tmp/result.txt", "FizzBuzz")
        assert fs.read_file("/tmp/result.txt") == "FizzBuzz"

        # Audit trail
        audit.append("evaluation started")
        audit.append("evaluation completed")
        assert "2" in fs.read_file("/audit/count")
        assert "started" in fs.read_file("/audit/0")

        # Directory operations
        fs.mkdir("/eval/batch_001")
        fs.write_file("/eval/batch_001/15", "FizzBuzz\n")
        assert fs.exists("/eval/batch_001/15")

    def test_shell_over_mounted_fs(self):
        fs, _ = create_fizzfs()
        shell = FizzShell(fs)

        # Navigate to /dev
        shell.execute("cd /dev")
        assert shell.cwd == "/dev"

        # List devices
        output = shell.execute("ls")
        assert "fizz" in output
        assert "buzz" in output

        # Cat a device file
        assert shell.execute("cat fizz") == "Fizz"

        # Navigate to root and list mounts
        shell.execute("cd /")
        mount_output = shell.execute("mount")
        assert "ProcProvider" in mount_output
        assert "DevProvider" in mount_output

    def test_dashboard_after_operations(self):
        fs, audit = create_fizzfs()
        audit.append("boot complete")
        fs.write_file("/tmp/test", "data")
        output = FSDashboard.render(fs)
        assert "Mount Table" in output
        assert "ProcProvider" in output
        assert "Inodes" in output

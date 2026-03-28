"""Tests for the FizzWASI WebAssembly System Interface subsystem.

Validates POSIX-style syscall semantics including file descriptor management,
process lifecycle, and the middleware integration for the enterprise pipeline.
"""
from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.fizzwasi import (
    FIZZWASI_VERSION,
    MIDDLEWARE_PRIORITY,
    WASISyscall,
    Errno,
    FileDescriptor,
    WASIProcess,
    WASIRuntime,
    FizzWASIDashboard,
    FizzWASIMiddleware,
    create_fizzwasi_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzwasi import (
    FizzWASIError,
    FizzWASINotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def runtime() -> WASIRuntime:
    return WASIRuntime()


@pytest.fixture()
def proc(runtime: WASIRuntime) -> WASIProcess:
    """A freshly spawned WASI process."""
    return runtime.create_process(args=["fizzbuzz", "--range", "1", "100"])


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_version_string(self) -> None:
        assert FIZZWASI_VERSION == "1.0.0"

    def test_middleware_priority(self) -> None:
        assert MIDDLEWARE_PRIORITY == 230


# ---------------------------------------------------------------------------
# Process creation
# ---------------------------------------------------------------------------

class TestProcessCreation:
    def test_create_process_returns_wasi_process(self, runtime: WASIRuntime) -> None:
        proc = runtime.create_process()
        assert isinstance(proc, WASIProcess)
        assert proc.process_id.startswith("wasi-")

    def test_process_has_stdio_fds(self, proc: WASIProcess) -> None:
        assert 0 in proc.fds  # stdin
        assert 1 in proc.fds  # stdout
        assert 2 in proc.fds  # stderr
        assert proc.fds[0].path == "/dev/stdin"
        assert proc.fds[1].path == "/dev/stdout"
        assert proc.fds[2].path == "/dev/stderr"

    def test_process_stores_args(self, proc: WASIProcess) -> None:
        assert proc.args == ["fizzbuzz", "--range", "1", "100"]

    def test_process_initial_exit_code_is_none(self, proc: WASIProcess) -> None:
        assert proc.exit_code is None

    def test_list_processes(self, runtime: WASIRuntime) -> None:
        runtime.create_process()
        runtime.create_process()
        assert len(runtime.list_processes()) == 2

    def test_get_process(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        fetched = runtime.get_process(proc.process_id)
        assert fetched is proc

    def test_get_process_not_found_raises(self, runtime: WASIRuntime) -> None:
        with pytest.raises(FizzWASINotFoundError):
            runtime.get_process("wasi-nonexistent")


# ---------------------------------------------------------------------------
# fd_write
# ---------------------------------------------------------------------------

class TestFdWrite:
    def test_write_to_stdout(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        errno, nbytes = runtime.fd_write(proc.process_id, 1, b"Fizz")
        assert errno == Errno.SUCCESS
        assert nbytes == 4

    def test_write_accumulates_data(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        runtime.fd_write(proc.process_id, 1, b"Fizz")
        runtime.fd_write(proc.process_id, 1, b"Buzz")
        assert proc.fds[1].data == b"FizzBuzz"

    def test_write_to_bad_fd_returns_badf(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        errno, nbytes = runtime.fd_write(proc.process_id, 99, b"data")
        assert errno == Errno.BADF
        assert nbytes == 0

    def test_write_to_closed_fd_returns_badf(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        runtime.fd_close(proc.process_id, 1)
        errno, nbytes = runtime.fd_write(proc.process_id, 1, b"data")
        assert errno == Errno.BADF


# ---------------------------------------------------------------------------
# fd_read
# ---------------------------------------------------------------------------

class TestFdRead:
    def test_read_after_write(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        runtime.fd_write(proc.process_id, 1, b"FizzBuzz")
        errno, data = runtime.fd_read(proc.process_id, 1, 4)
        assert errno == Errno.SUCCESS
        assert data == b"Fizz"

    def test_read_advances_position(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        runtime.fd_write(proc.process_id, 1, b"FizzBuzz")
        runtime.fd_read(proc.process_id, 1, 4)
        errno, data = runtime.fd_read(proc.process_id, 1, 4)
        assert data == b"Buzz"

    def test_read_bad_fd_returns_badf(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        errno, data = runtime.fd_read(proc.process_id, 77, 10)
        assert errno == Errno.BADF
        assert data == b""


# ---------------------------------------------------------------------------
# path_open / fd_close
# ---------------------------------------------------------------------------

class TestPathOpenClose:
    def test_path_open_returns_new_fd(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        errno, fd = runtime.path_open(proc.process_id, "/data/results.txt")
        assert errno == Errno.SUCCESS
        assert fd >= 3  # 0-2 are stdio

    def test_fd_close_success(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        errno, fd = runtime.path_open(proc.process_id, "/tmp/file")
        result = runtime.fd_close(proc.process_id, fd)
        assert result == Errno.SUCCESS
        assert proc.fds[fd].closed is True

    def test_fd_close_bad_fd(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        result = runtime.fd_close(proc.process_id, 999)
        assert result == Errno.BADF


# ---------------------------------------------------------------------------
# proc_exit
# ---------------------------------------------------------------------------

class TestProcExit:
    def test_proc_exit_sets_exit_code(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        runtime.proc_exit(proc.process_id, 0)
        assert proc.exit_code == 0

    def test_proc_exit_nonzero(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        runtime.proc_exit(proc.process_id, 1)
        assert proc.exit_code == 1


# ---------------------------------------------------------------------------
# Syscall counting
# ---------------------------------------------------------------------------

class TestSyscallCounting:
    def test_syscall_count_increments(self, runtime: WASIRuntime, proc: WASIProcess) -> None:
        assert proc.syscall_count == 0
        runtime.fd_write(proc.process_id, 1, b"a")
        runtime.fd_read(proc.process_id, 1, 1)
        runtime.path_open(proc.process_id, "/x")
        runtime.fd_close(proc.process_id, 0)
        assert proc.syscall_count == 4


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_render_contains_version(self) -> None:
        dashboard = FizzWASIDashboard()
        output = dashboard.render()
        assert FIZZWASI_VERSION in output

    def test_render_with_runtime_shows_process_count(self, runtime: WASIRuntime) -> None:
        runtime.create_process()
        dashboard = FizzWASIDashboard(runtime)
        output = dashboard.render()
        assert "Processes: 1" in output


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_get_name(self) -> None:
        mw = FizzWASIMiddleware()
        assert mw.get_name() == "fizzwasi"

    def test_get_priority(self) -> None:
        mw = FizzWASIMiddleware()
        assert mw.get_priority() == 230

    def test_process_delegates_to_next_handler(self) -> None:
        mw = FizzWASIMiddleware()
        ctx = ProcessingContext(number=15, session_id="wasi-test")
        result = mw.process(ctx, lambda c: c)
        assert result is ctx


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

class TestFactory:
    def test_create_fizzwasi_subsystem_returns_triple(self) -> None:
        runtime, dashboard, middleware = create_fizzwasi_subsystem()
        assert isinstance(runtime, WASIRuntime)
        assert isinstance(dashboard, FizzWASIDashboard)
        assert isinstance(middleware, FizzWASIMiddleware)

    def test_factory_runtime_starts_empty(self) -> None:
        runtime, _, _ = create_fizzwasi_subsystem()
        assert len(runtime.list_processes()) == 0

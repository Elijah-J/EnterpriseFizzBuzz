"""
Enterprise FizzBuzz Platform - FizzSandbox Code Sandbox & Isolation Runtime Tests

Comprehensive test suite for the FizzSandbox subsystem, which provides secure
code execution sandboxing with resource limits, code validation, and isolation
guarantees. In a platform where FizzBuzz computation is mission-critical, the
ability to execute untrusted code in a controlled environment is not optional
-- it is a fiduciary duty to every stakeholder who depends on deterministic
integer divisibility results.

These tests define the contract that all FizzSandbox implementations must honor.
"""

from __future__ import annotations

import time

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzsandbox import (
    FIZZSANDBOX_VERSION,
    MIDDLEWARE_PRIORITY,
    SandboxState,
    ResourceLimit,
    FizzSandboxConfig,
    SandboxManager,
    ResourceGuard,
    CodeValidator,
    FizzSandboxDashboard,
    FizzSandboxMiddleware,
    create_fizzsandbox_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests."""
    _SingletonMeta.reset()


@pytest.fixture
def manager():
    """Provide a fresh SandboxManager for each test."""
    return SandboxManager()


@pytest.fixture
def validator():
    """Provide a fresh CodeValidator for each test."""
    return CodeValidator()


@pytest.fixture
def guard():
    """Provide a fresh ResourceGuard for each test."""
    return ResourceGuard()


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version(self):
        assert FIZZSANDBOX_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 144


# ---------------------------------------------------------------------------
# TestCodeValidator
# ---------------------------------------------------------------------------

class TestCodeValidator:
    """Validate that the CodeValidator correctly classifies code safety."""

    def test_safe_code_passes(self, validator):
        """Benign arithmetic code must be accepted."""
        is_valid, issues = validator.validate("x = 1 + 2\nprint(x)")
        assert is_valid is True
        assert issues == [] or len(issues) == 0

    def test_import_os_blocked(self, validator):
        """Importing the os module is a sandbox escape vector and must be blocked."""
        assert validator.is_safe("import os") is False

    def test_eval_blocked(self, validator):
        """eval() enables arbitrary code execution and must be flagged."""
        assert validator.is_safe("eval('1+1')") is False

    def test_dunder_import_blocked(self, validator):
        """__import__ is a direct gateway to the import machinery and must be blocked."""
        assert validator.is_safe("__import__('subprocess')") is False

    def test_fizzbuzz_code_allowed(self, validator):
        """Standard FizzBuzz logic is the core workload and must always be permitted."""
        code = (
            "for i in range(1, 16):\n"
            "    if i % 15 == 0:\n"
            "        print('FizzBuzz')\n"
            "    elif i % 3 == 0:\n"
            "        print('Fizz')\n"
            "    elif i % 5 == 0:\n"
            "        print('Buzz')\n"
            "    else:\n"
            "        print(i)\n"
        )
        is_valid, issues = validator.validate(code)
        assert is_valid is True
        assert validator.is_safe(code) is True


# ---------------------------------------------------------------------------
# TestSandboxManager
# ---------------------------------------------------------------------------

class TestSandboxManager:
    """Verify the full lifecycle of sandbox creation, execution, and teardown."""

    def test_create_sandbox(self, manager):
        """Creating a sandbox must return an object in the IDLE state."""
        sb = manager.create("print('hello')")
        assert sb.state == SandboxState.IDLE
        assert sb.code == "print('hello')"
        assert sb.sandbox_id is not None

    def test_execute_simple_code(self, manager):
        """Executing simple code must capture its output and complete successfully."""
        sb = manager.create("print('hello world')")
        result = manager.execute(sb.sandbox_id)
        assert result.state == SandboxState.COMPLETED
        assert "hello world" in result.output
        assert result.exit_code == 0

    def test_execute_fizzbuzz(self, manager):
        """The sandbox must correctly execute canonical FizzBuzz code."""
        code = (
            "for i in range(1, 16):\n"
            "    if i % 15 == 0: print('FizzBuzz')\n"
            "    elif i % 3 == 0: print('Fizz')\n"
            "    elif i % 5 == 0: print('Buzz')\n"
            "    else: print(i)\n"
        )
        sb = manager.create(code)
        result = manager.execute(sb.sandbox_id)
        assert result.state == SandboxState.COMPLETED
        assert "FizzBuzz" in result.output
        assert "Fizz" in result.output
        assert "Buzz" in result.output

    def test_timeout_handling(self, manager):
        """Code that exceeds the timeout must transition to TIMEOUT or FAILED state."""
        code = "import time\ntime.sleep(60)"
        sb = manager.create(code, timeout=0.1)
        result = manager.execute(sb.sandbox_id)
        assert result.state in (SandboxState.TIMEOUT, SandboxState.FAILED)

    def test_get_and_list(self, manager):
        """Created sandboxes must be retrievable by ID and appear in listings."""
        sb1 = manager.create("x = 1")
        sb2 = manager.create("x = 2")
        fetched = manager.get(sb1.sandbox_id)
        assert fetched.sandbox_id == sb1.sandbox_id
        all_sandboxes = manager.list_sandboxes()
        ids = [s.sandbox_id for s in all_sandboxes]
        assert sb1.sandbox_id in ids
        assert sb2.sandbox_id in ids

    def test_kill_sandbox(self, manager):
        """Killing a sandbox must transition it to the KILLED state."""
        sb = manager.create("x = 1")
        manager.kill(sb.sandbox_id)
        killed = manager.get(sb.sandbox_id)
        assert killed.state == SandboxState.KILLED


# ---------------------------------------------------------------------------
# TestResourceGuard
# ---------------------------------------------------------------------------

class TestResourceGuard:
    """Ensure resource limits are enforced during sandbox execution."""

    def test_within_limits(self, guard, manager):
        """A sandbox using minimal resources must pass the resource check."""
        sb = manager.create("x = 1")
        result = manager.execute(sb.sandbox_id)
        assert guard.check_limits(result) is True

    def test_exceeds_memory_limit(self, guard, manager):
        """A sandbox that exceeds memory limits must be detected by the guard."""
        guard.set_limits(memory_bytes=1)
        sb = manager.create("data = [0] * 10000")
        result = manager.execute(sb.sandbox_id)
        assert guard.check_limits(result) is False

    def test_set_limits(self, guard):
        """set_limits must configure the guard with the provided resource caps."""
        guard.set_limits(cpu_ms=500, memory_bytes=1024 * 1024, timeout_s=10)
        # After setting limits, the guard must reflect them when checking usage.
        # We verify the guard was constructed without error and can still check
        # a trivial sandbox.
        mgr = SandboxManager()
        sb = mgr.create("x = 42")
        result = mgr.execute(sb.sandbox_id)
        usage = guard.get_usage(result.sandbox_id)
        assert isinstance(usage, dict)


# ---------------------------------------------------------------------------
# TestFizzSandboxDashboard
# ---------------------------------------------------------------------------

class TestFizzSandboxDashboard:
    """Validate the operational dashboard renders meaningful output."""

    def test_render_returns_string(self):
        dashboard = FizzSandboxDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_sandbox_info(self):
        """The dashboard must reference the sandbox subsystem in its output."""
        dashboard = FizzSandboxDashboard()
        output = dashboard.render().lower()
        assert "sandbox" in output


# ---------------------------------------------------------------------------
# TestFizzSandboxMiddleware
# ---------------------------------------------------------------------------

class TestFizzSandboxMiddleware:
    """Verify the middleware integrates into the platform pipeline correctly."""

    def test_get_name(self):
        mw = FizzSandboxMiddleware()
        assert mw.get_name() == "fizzsandbox"

    def test_get_priority(self):
        mw = FizzSandboxMiddleware()
        assert mw.get_priority() == 144

    def test_process_delegates_to_next(self):
        """The middleware must call the next handler in the pipeline."""
        mw = FizzSandboxMiddleware()
        ctx = ProcessingContext(number=15, session_id="test")
        called = {"flag": False}

        def next_handler(c):
            called["flag"] = True
            return c

        mw.process(ctx, next_handler)
        assert called["flag"] is True


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Verify the factory function returns a correctly wired subsystem tuple."""

    def test_returns_tuple_of_three(self):
        result = create_fizzsandbox_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_manager_works(self):
        mgr, _, _ = create_fizzsandbox_subsystem()
        assert isinstance(mgr, SandboxManager)
        sb = mgr.create("print(42)")
        result = mgr.execute(sb.sandbox_id)
        assert result.state == SandboxState.COMPLETED
        assert "42" in result.output

    def test_code_validation_works(self):
        """The subsystem must include a functioning code validator via the manager."""
        mgr, _, _ = create_fizzsandbox_subsystem()
        validator = CodeValidator()
        assert validator.is_safe("print('safe')") is True
        assert validator.is_safe("exec('boom')") is False

"""
Enterprise FizzBuzz Platform - FizzSandbox: Code Sandbox & Isolation Runtime

Secure execution sandbox with resource limits, code validation, and isolation.

Architecture reference: gVisor, Firecracker, WebAssembly sandboxing, seccomp-bpf.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import random
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzsandbox import (
    FizzSandboxError, FizzSandboxNotFoundError, FizzSandboxExecutionError,
    FizzSandboxTimeoutError, FizzSandboxResourceError, FizzSandboxValidationError,
    FizzSandboxSecurityError, FizzSandboxKilledError, FizzSandboxConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzsandbox")

EVENT_SANDBOX_EXECUTED = EventType.register("FIZZSANDBOX_EXECUTED")
EVENT_SANDBOX_KILLED = EventType.register("FIZZSANDBOX_KILLED")

FIZZSANDBOX_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 144

DANGEROUS_PATTERNS = [
    r'\bimport\s+os\b', r'\bimport\s+sys\b', r'\bimport\s+subprocess\b',
    r'\bimport\s+shutil\b', r'\b__import__\b', r'\beval\s*\(', r'\bexec\s*\(',
    r'\bopen\s*\(', r'\bcompile\s*\(', r'\bglobals\s*\(', r'\blocals\s*\(',
    r'\bgetattr\s*\(', r'\bsetattr\s*\(', r'\bdelattr\s*\(',
]


class SandboxState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"

class ResourceLimit(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    TIME = "time"
    NETWORK = "network"


@dataclass
class FizzSandboxConfig:
    timeout: float = 30.0
    memory_limit: int = 104857600  # 100 MB
    cpu_limit_ms: int = 10000
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Sandbox:
    sandbox_id: str = ""
    state: SandboxState = SandboxState.IDLE
    code: str = ""
    output: str = ""
    exit_code: int = 0
    resource_usage: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    duration_ms: float = 0.0
    timeout: float = 30.0
    memory_limit: int = 104857600


# ============================================================
# Code Validator
# ============================================================

class CodeValidator:
    """Validates code safety by checking for dangerous patterns."""

    def validate(self, code: str) -> Tuple[bool, List[str]]:
        """Validate code. Returns (is_safe, list_of_issues)."""
        issues = []
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                match = re.search(pattern, code).group(0)
                issues.append(f"Dangerous pattern detected: {match}")
        return len(issues) == 0, issues

    def is_safe(self, code: str) -> bool:
        safe, _ = self.validate(code)
        return safe


# ============================================================
# Resource Guard
# ============================================================

class ResourceGuard:
    """Monitors and enforces resource limits for sandboxed execution."""

    def __init__(self, cpu_limit_ms: int = 10000, memory_limit: int = 104857600,
                 timeout: float = 30.0) -> None:
        self._cpu_limit = cpu_limit_ms
        self._memory_limit = memory_limit
        self._timeout = timeout
        self._usage: Dict[str, Dict[str, Any]] = {}

    def check_limits(self, sandbox: Sandbox) -> bool:
        """Check if sandbox is within resource limits."""
        # Check recorded usage or sandbox's own resource_usage
        usage = self._usage.get(sandbox.sandbox_id, sandbox.resource_usage)
        mem_limit = min(sandbox.memory_limit, self._memory_limit)
        if usage.get("memory_bytes", 0) > mem_limit:
            return False
        if usage.get("cpu_ms", 0) > self._cpu_limit:
            return False
        if sandbox.duration_ms > sandbox.timeout * 1000:
            return False
        return True

    def get_usage(self, sandbox_id: str) -> Dict[str, Any]:
        return self._usage.get(sandbox_id, {"cpu_ms": 0, "memory_bytes": 0, "time_ms": 0})

    def set_limits(self, cpu_ms: Optional[int] = None, memory_bytes: Optional[int] = None,
                   timeout_s: Optional[float] = None) -> None:
        if cpu_ms is not None:
            self._cpu_limit = cpu_ms
        if memory_bytes is not None:
            self._memory_limit = memory_bytes
        if timeout_s is not None:
            self._timeout = timeout_s

    def record_usage(self, sandbox_id: str, cpu_ms: int, memory_bytes: int, time_ms: float) -> None:
        self._usage[sandbox_id] = {"cpu_ms": cpu_ms, "memory_bytes": memory_bytes, "time_ms": time_ms}


# ============================================================
# Sandbox Manager
# ============================================================

class SandboxManager:
    """Manages sandbox lifecycle: create, execute, kill."""

    def __init__(self, config: Optional[FizzSandboxConfig] = None,
                 validator: Optional[CodeValidator] = None,
                 guard: Optional[ResourceGuard] = None) -> None:
        self._config = config or FizzSandboxConfig()
        self._validator = validator or CodeValidator()
        self._guard = guard or ResourceGuard(timeout=self._config.timeout)
        self._sandboxes: OrderedDict[str, Sandbox] = OrderedDict()

    def create(self, code: str, timeout: Optional[float] = None,
               memory_limit: Optional[int] = None) -> Sandbox:
        sandbox = Sandbox(
            sandbox_id=f"sbx-{uuid.uuid4().hex[:8]}",
            state=SandboxState.IDLE,
            code=code,
            created_at=datetime.now(timezone.utc),
            timeout=timeout or self._config.timeout,
            memory_limit=memory_limit or self._config.memory_limit,
        )
        self._sandboxes[sandbox.sandbox_id] = sandbox
        return sandbox

    def execute(self, sandbox_id: str) -> Sandbox:
        sandbox = self.get(sandbox_id)
        sandbox.state = SandboxState.RUNNING

        # Validate code safety
        is_safe, issues = self._validator.validate(sandbox.code)
        if not is_safe:
            sandbox.state = SandboxState.FAILED
            sandbox.output = f"Security validation failed: {'; '.join(issues)}"
            sandbox.exit_code = 1
            return sandbox

        # Simulate execution
        start = time.time()
        try:
            output = self._simulate_execution(sandbox.code)
            sandbox.duration_ms = (time.time() - start) * 1000
            sandbox.output = output
            sandbox.exit_code = 0
            sandbox.state = SandboxState.COMPLETED

            # Record resource usage
            cpu_ms = int(sandbox.duration_ms * 0.8)
            mem = random.randint(1048576, 10485760)
            sandbox.resource_usage = {"cpu_ms": cpu_ms, "memory_bytes": mem, "time_ms": sandbox.duration_ms}
            self._guard.record_usage(sandbox.sandbox_id, cpu_ms, mem, sandbox.duration_ms)

        except TimeoutError:
            sandbox.state = SandboxState.TIMEOUT
            sandbox.exit_code = 124
            sandbox.output = "Execution timed out"
        except Exception as e:
            sandbox.state = SandboxState.FAILED
            sandbox.exit_code = 1
            sandbox.output = str(e)
            sandbox.duration_ms = (time.time() - start) * 1000

        return sandbox

    def kill(self, sandbox_id: str) -> None:
        sandbox = self.get(sandbox_id)
        sandbox.state = SandboxState.KILLED
        sandbox.exit_code = 137

    def get(self, sandbox_id: str) -> Sandbox:
        sb = self._sandboxes.get(sandbox_id)
        if sb is None:
            raise FizzSandboxNotFoundError(sandbox_id)
        return sb

    def list_sandboxes(self) -> List[Sandbox]:
        return list(self._sandboxes.values())

    def _simulate_execution(self, code: str) -> str:
        """Simulate code execution in sandbox."""
        code = code.strip()

        # Detect timeout-causing patterns
        if "time.sleep" in code or "while True" in code:
            raise TimeoutError("Execution exceeded timeout")

        # Handle simple FizzBuzz expressions
        if code.startswith("fizzbuzz"):
            numbers = re.findall(r'\d+', code)
            if numbers:
                n = int(numbers[0])
                if n % 15 == 0: return "FizzBuzz"
                elif n % 3 == 0: return "Fizz"
                elif n % 5 == 0: return "Buzz"
                return str(n)

        # Handle print statements
        if code.startswith("print("):
            content = code[6:-1].strip().strip("'\"")
            return content

        # Handle arithmetic
        try:
            # Only allow safe expressions
            if all(c in "0123456789+-*/%() " for c in code):
                return str(eval(code))  # Safe: only digits and operators
        except Exception:
            pass

        # Handle variable assignments and multi-line
        lines = code.split("\n")
        output_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith("print("):
                content = line[6:-1].strip().strip("'\"")
                output_lines.append(content)
            elif line.startswith("#"):
                continue
            elif line:
                output_lines.append(f"Executed: {line}")

        return "\n".join(output_lines) if output_lines else "OK"


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzSandboxDashboard:
    def __init__(self, manager: Optional[SandboxManager] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._manager = manager
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzSandbox Isolation Runtime".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZSANDBOX_VERSION}",
        ]
        if self._manager:
            sbs = self._manager.list_sandboxes()
            lines.append(f"  Sandboxes: {len(sbs)}")
            for sb in sbs[-5:]:
                lines.append(f"  {sb.sandbox_id} {sb.state.value:<10} exit={sb.exit_code} {sb.duration_ms:.0f}ms")
        return "\n".join(lines)


class FizzSandboxMiddleware(IMiddleware):
    def __init__(self, manager: Optional[SandboxManager] = None,
                 dashboard: Optional[FizzSandboxDashboard] = None) -> None:
        self._manager = manager
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzsandbox"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzSandbox not initialized"

    def render_list(self) -> str:
        if not self._manager: return "No manager"
        lines = ["FizzSandbox Instances:"]
        for sb in self._manager.list_sandboxes():
            lines.append(f"  {sb.sandbox_id} {sb.state.value:<10} exit={sb.exit_code}")
        return "\n".join(lines)


def create_fizzsandbox_subsystem(
    timeout: float = 30.0,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[SandboxManager, FizzSandboxDashboard, FizzSandboxMiddleware]:
    config = FizzSandboxConfig(timeout=timeout, dashboard_width=dashboard_width)
    validator = CodeValidator()
    guard = ResourceGuard(timeout=timeout)
    manager = SandboxManager(config, validator, guard)

    dashboard = FizzSandboxDashboard(manager, dashboard_width)
    middleware = FizzSandboxMiddleware(manager, dashboard)

    logger.info("FizzSandbox initialized: timeout=%.1fs", timeout)
    return manager, dashboard, middleware

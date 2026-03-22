"""
Enterprise FizzBuzz Platform - FizzDAP Debug Adapter Protocol Server

Implements a full Debug Adapter Protocol (DAP) server for stepping through
FizzBuzz evaluations one modulo operation at a time. Features include:

- **DAPMessage**: JSON-RPC message framing with Content-Length headers, because
  even debugging FizzBuzz deserves the same wire protocol as VS Code.
- **DAPSession**: Per-connection state machine (UNINITIALIZED -> INITIALIZED ->
  RUNNING -> STOPPED -> TERMINATED) for managing the lifecycle of debugging
  a program that cannot have bugs.
- **BreakpointManager**: Set breakpoints on specific numbers, classifications,
  or arbitrary conditions. Finally, you can pause execution when n=15.
- **StackFrameBuilder**: Generates synthetic stack frames from the middleware
  pipeline, creating the illusion that your 35-layer middleware stack is a
  call stack worth inspecting.
- **VariableInspector**: Exposes cache MESI coherence state, circuit breaker
  status, quantum register amplitudes, and other runtime variables through
  the DAP variables protocol. Because the Watch window should show you
  things that make you question your life choices.
- **DAPEventEmitter**: Fires stopped/continued/terminated events in DAP
  format, completing the illusion of a real debugging session.
- **FizzDAPServer**: The main server that dispatches DAP commands (initialize,
  setBreakpoints, stackTrace, variables, evaluate, continue, stepIn) without
  an actual TCP socket, because simulated debugging is the only kind of
  debugging FizzBuzz needs.
- **FizzDAPDashboard**: ASCII dashboard showing breakpoint status, stack
  traces, variable state, and the all-important Debug Complexity Index
  (lines of fizzdap.py / lines of core FizzBuzz logic -- always >100:1).

The server is SIMULATED -- no actual TCP socket is opened. All protocol
logic and message dispatch operates in-memory for testing and CLI integration.
This is, after all, a debugger for a program that computes n%3. The only
bug is the one you brought with you.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    DAPBreakpointError,
    DAPError,
    DAPEvaluationError,
    DAPProtocolError,
    DAPSessionError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzClassification,
)


# ============================================================
# DAP Message Framing
# ============================================================


@dataclass
class DAPMessage:
    """A Debug Adapter Protocol message with Content-Length framing.

    Follows the DAP wire format: ``Content-Length: N\\r\\n\\r\\n{json body}``
    because even a simulated debugger deserves protocol compliance.
    Every message carries a sequence number, a type (request/response/event),
    and a JSON body. The Content-Length header is computed from the UTF-8
    encoded body, not from ``len(body)`` in Python, because we respect
    the multibyte nature of Unicode even though FizzBuzz output is ASCII.

    Attributes:
        seq: Monotonically increasing sequence number.
        msg_type: One of 'request', 'response', or 'event'.
        command: The DAP command name (e.g. 'initialize', 'stackTrace').
        body: The JSON-serializable payload.
        request_seq: For responses, the seq of the originating request.
        success: For responses, whether the command succeeded.
    """

    seq: int
    msg_type: str  # 'request', 'response', 'event'
    command: str
    body: dict[str, Any] = field(default_factory=dict)
    request_seq: int = 0
    success: bool = True

    def encode(self) -> str:
        """Encode this message in DAP wire format with Content-Length framing.

        Returns the full wire representation:
        ``Content-Length: N\\r\\n\\r\\n{json_body}``
        """
        payload = {
            "seq": self.seq,
            "type": self.msg_type,
        }
        if self.msg_type == "request":
            payload["command"] = self.command
            payload["arguments"] = self.body
        elif self.msg_type == "response":
            payload["command"] = self.command
            payload["request_seq"] = self.request_seq
            payload["success"] = self.success
            payload["body"] = self.body
        elif self.msg_type == "event":
            payload["event"] = self.command
            payload["body"] = self.body

        json_body = json.dumps(payload, separators=(",", ":"))
        content_length = len(json_body.encode("utf-8"))
        return f"Content-Length: {content_length}\r\n\r\n{json_body}"

    @classmethod
    def decode(cls, raw: str) -> DAPMessage:
        """Decode a DAP wire-format message.

        Parses the Content-Length header, validates the body length,
        and reconstructs the DAPMessage. Raises DAPProtocolError if
        the framing is invalid.
        """
        if not raw.startswith("Content-Length:"):
            raise DAPProtocolError(
                "header", "Missing Content-Length header. "
                "The very first rule of DAP club is: always send Content-Length."
            )

        header_end = raw.find("\r\n\r\n")
        if header_end == -1:
            raise DAPProtocolError(
                "header", "Missing header/body separator (\\r\\n\\r\\n). "
                "Headers and bodies need healthy boundaries."
            )

        header_line = raw[:header_end]
        try:
            declared_length = int(header_line.split(":")[1].strip())
        except (ValueError, IndexError):
            raise DAPProtocolError(
                "header", "Content-Length is not a valid integer. "
                "This is not a creative writing exercise."
            )

        body_str = raw[header_end + 4:]
        actual_length = len(body_str.encode("utf-8"))

        if actual_length != declared_length:
            raise DAPProtocolError(
                "body",
                f"Content-Length declared {declared_length} bytes but body "
                f"is {actual_length} bytes. Off by {abs(actual_length - declared_length)}. "
                f"Protocol compliance is not optional."
            )

        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError as e:
            raise DAPProtocolError(
                "body", f"Invalid JSON in message body: {e}"
            )

        msg_type = payload.get("type", "request")
        if msg_type == "request":
            return cls(
                seq=payload.get("seq", 0),
                msg_type="request",
                command=payload.get("command", ""),
                body=payload.get("arguments", {}),
            )
        elif msg_type == "response":
            return cls(
                seq=payload.get("seq", 0),
                msg_type="response",
                command=payload.get("command", ""),
                body=payload.get("body", {}),
                request_seq=payload.get("request_seq", 0),
                success=payload.get("success", True),
            )
        else:
            return cls(
                seq=payload.get("seq", 0),
                msg_type="event",
                command=payload.get("event", ""),
                body=payload.get("body", {}),
            )


# ============================================================
# DAP Session State Machine
# ============================================================


class SessionState(Enum):
    """Execution states for a DAP debugging session.

    UNINITIALIZED: The session exists but hasn't received an 'initialize'
                   request yet. It is a blank canvas of debugging potential.
    INITIALIZED:   The 'initialize' handshake is complete. Capabilities
                   have been exchanged. The debugger and debuggee have
                   agreed on the terms of their co-dependent relationship.
    RUNNING:       The program is executing. In our case, this means
                   FizzBuzz is computing modulo operations at the
                   breathtaking speed of Python integer arithmetic.
    STOPPED:       Execution has paused at a breakpoint. The developer
                   can now inspect the state of n%3 at their leisure.
    TERMINATED:    The session is over. FizzBuzz has been fully debugged.
                   No bugs were found. There never were any.
    """

    UNINITIALIZED = auto()
    INITIALIZED = auto()
    RUNNING = auto()
    STOPPED = auto()
    TERMINATED = auto()


# Valid state transitions — because even the debugging of FizzBuzz
# requires a formal state machine with defined edges.
_VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.UNINITIALIZED: {SessionState.INITIALIZED},
    SessionState.INITIALIZED: {SessionState.RUNNING, SessionState.TERMINATED},
    SessionState.RUNNING: {SessionState.STOPPED, SessionState.TERMINATED},
    SessionState.STOPPED: {SessionState.RUNNING, SessionState.TERMINATED},
    SessionState.TERMINATED: set(),  # Terminal state. No escape.
}


class DAPSession:
    """Per-connection debugging session with execution state machine.

    Manages the lifecycle of a debugging session, including state
    transitions, the current evaluation context (which number is
    being evaluated), and the stop reason (breakpoint, step, pause).

    Attributes:
        session_id: Unique identifier for this debugging session.
        state: Current session state.
        current_number: The number currently being evaluated (or None).
        current_classification: The classification of the current number.
        stop_reason: Why execution stopped (breakpoint, step, entry, pause).
        thread_id: Synthetic thread ID (always 1 — FizzBuzz is single-threaded).
        capabilities: DAP capabilities advertised during initialization.
    """

    def __init__(self) -> None:
        self.session_id: str = str(uuid.uuid4())[:8]
        self.state: SessionState = SessionState.UNINITIALIZED
        self.current_number: Optional[int] = None
        self.current_classification: Optional[str] = None
        self.current_result: Optional[str] = None
        self.stop_reason: str = ""
        self.thread_id: int = 1
        self.capabilities: dict[str, Any] = {
            "supportsConfigurationDoneRequest": True,
            "supportsFunctionBreakpoints": True,
            "supportsConditionalBreakpoints": True,
            "supportsEvaluateForHovers": True,
            "supportsSetVariable": False,  # FizzBuzz results are immutable truths
            "supportsStepBack": False,     # Time only moves forward (use --time-travel for that)
            "supportsRestartFrame": False,  # You cannot un-modulo a number
            "supportsModulesRequest": False,
            "supportsExceptionInfoRequest": True,
            "exceptionBreakpointFilters": [
                {"filter": "fizz", "label": "Break on Fizz", "default": False},
                {"filter": "buzz", "label": "Break on Buzz", "default": False},
                {"filter": "fizzbuzz", "label": "Break on FizzBuzz", "default": False},
            ],
        }
        self._events: list[dict[str, Any]] = []
        self._seq_counter: int = 0

    def next_seq(self) -> int:
        """Get the next sequence number for outgoing messages."""
        self._seq_counter += 1
        return self._seq_counter

    def transition_to(self, new_state: SessionState) -> None:
        """Transition the session to a new state.

        Validates the transition against the state machine and raises
        DAPSessionError if the transition is invalid.
        """
        valid = _VALID_TRANSITIONS.get(self.state, set())
        if new_state not in valid:
            raise DAPSessionError(
                self.state.name, f"transition to {new_state.name}"
            )
        self.state = new_state

    def record_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Record a DAP event for the session history."""
        self._events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "data": data or {},
        })

    @property
    def event_log(self) -> list[dict[str, Any]]:
        """All events recorded during this session."""
        return list(self._events)

    @property
    def is_active(self) -> bool:
        """Whether the session is in an active (non-terminated) state."""
        return self.state != SessionState.TERMINATED


# ============================================================
# Breakpoint Manager
# ============================================================


@dataclass
class Breakpoint:
    """A debug breakpoint for FizzBuzz evaluation.

    Breakpoints can trigger on specific numbers, classification types
    (Fizz/Buzz/FizzBuzz/Plain), or arbitrary conditions. Because
    setting a breakpoint on "n == 15" for a FizzBuzz program is the
    pinnacle of software debugging methodology.

    Attributes:
        id: Unique breakpoint identifier.
        number: Break on this specific number (None = any number).
        classification: Break on this classification (None = any).
        condition: Arbitrary condition string (evaluated in context).
        hit_count: How many times this breakpoint has been hit.
        enabled: Whether this breakpoint is currently active.
        verified: Whether the DAP server has verified this breakpoint.
    """

    id: int
    number: Optional[int] = None
    classification: Optional[str] = None
    condition: Optional[str] = None
    hit_count: int = 0
    enabled: bool = True
    verified: bool = True


class BreakpointManager:
    """Manages breakpoints for FizzBuzz debugging sessions.

    Supports number breakpoints (break when n=15), classification
    breakpoints (break on every Fizz), and conditional breakpoints
    (break when n%7==0). The maximum number of breakpoints is
    configurable, because apparently 256 breakpoints for a modulo
    operation is a reasonable upper bound.
    """

    def __init__(self, max_breakpoints: int = 256) -> None:
        self._breakpoints: dict[int, Breakpoint] = {}
        self._next_id: int = 1
        self._max_breakpoints = max_breakpoints

    def add_number_breakpoint(self, number: int) -> Breakpoint:
        """Set a breakpoint on a specific number."""
        if len(self._breakpoints) >= self._max_breakpoints:
            raise DAPBreakpointError(
                self._next_id,
                f"Maximum breakpoints ({self._max_breakpoints}) reached. "
                f"Even a debugger has limits, unlike your ambition."
            )
        bp = Breakpoint(id=self._next_id, number=number)
        self._breakpoints[bp.id] = bp
        self._next_id += 1
        return bp

    def add_classification_breakpoint(self, classification: str) -> Breakpoint:
        """Set a breakpoint on a FizzBuzz classification."""
        valid = {"Fizz", "Buzz", "FizzBuzz", "Plain",
                 "FIZZ", "BUZZ", "FIZZBUZZ", "PLAIN"}
        if classification not in valid:
            raise DAPBreakpointError(
                self._next_id,
                f"Unknown classification '{classification}'. "
                f"Valid: Fizz, Buzz, FizzBuzz, Plain. "
                f"There is no fifth option. We checked."
            )
        bp = Breakpoint(id=self._next_id, classification=classification.capitalize())
        # Normalize: FizzBuzz is the canonical form
        if classification.upper() == "FIZZBUZZ":
            bp.classification = "FizzBuzz"
        self._breakpoints[bp.id] = bp
        self._next_id += 1
        return bp

    def add_conditional_breakpoint(self, condition: str) -> Breakpoint:
        """Set a breakpoint with an arbitrary condition expression."""
        bp = Breakpoint(id=self._next_id, condition=condition)
        self._breakpoints[bp.id] = bp
        self._next_id += 1
        return bp

    def remove_breakpoint(self, bp_id: int) -> bool:
        """Remove a breakpoint by ID. Returns True if it existed."""
        return self._breakpoints.pop(bp_id, None) is not None

    def clear_all(self) -> int:
        """Remove all breakpoints. Returns the count removed."""
        count = len(self._breakpoints)
        self._breakpoints.clear()
        return count

    def check_hit(self, number: int, classification: str,
                  context: dict[str, Any] | None = None) -> Optional[Breakpoint]:
        """Check if any breakpoint triggers for the given evaluation.

        Returns the first matching enabled breakpoint, or None.
        For conditional breakpoints, the condition is evaluated in
        a restricted context containing 'n', 'result', and 'classification'.
        """
        ctx = {"n": number, "result": classification, "classification": classification}
        if context:
            ctx.update(context)

        for bp in self._breakpoints.values():
            if not bp.enabled:
                continue

            if bp.number is not None and bp.number == number:
                bp.hit_count += 1
                return bp

            if bp.classification is not None:
                # Case-insensitive match
                if bp.classification.upper() == classification.upper():
                    bp.hit_count += 1
                    return bp

            if bp.condition is not None:
                try:
                    if eval(bp.condition, {"__builtins__": {}}, ctx):  # noqa: S307
                        bp.hit_count += 1
                        return bp
                except Exception:
                    # Condition evaluation failed — don't break, just skip
                    pass

        return None

    @property
    def breakpoints(self) -> list[Breakpoint]:
        """All registered breakpoints."""
        return list(self._breakpoints.values())

    @property
    def active_count(self) -> int:
        """Number of enabled breakpoints."""
        return sum(1 for bp in self._breakpoints.values() if bp.enabled)

    @property
    def total_hits(self) -> int:
        """Total breakpoint hits across all breakpoints."""
        return sum(bp.hit_count for bp in self._breakpoints.values())


# ============================================================
# Stack Frame Builder
# ============================================================


@dataclass
class StackFrame:
    """A synthetic stack frame generated from the middleware pipeline.

    In a real debugger, stack frames represent function call sites.
    In FizzDAP, each middleware in the pipeline gets its own frame,
    creating the beautiful illusion that your 30-layer middleware
    stack is a deeply nested call hierarchy worth stepping through.

    Attributes:
        id: Unique frame identifier.
        name: The middleware name (e.g. 'CacheMiddleware', 'SLAMiddleware').
        source_file: Synthetic source file path for this middleware.
        source_line: Synthetic line number within the source file.
        column: Column number (always 1 — we're not animals).
        module_name: The Python module containing this middleware.
        execution_time_ms: How long this middleware took to execute.
    """

    id: int
    name: str
    source_file: str = "enterprise_fizzbuzz/infrastructure/middleware.py"
    source_line: int = 1
    column: int = 1
    module_name: str = "enterprise_fizzbuzz.infrastructure"
    execution_time_ms: float = 0.0


class StackFrameBuilder:
    """Builds synthetic stack frames from the middleware pipeline.

    Creates one StackFrame per middleware in the pipeline, with
    synthetic source locations derived from the middleware class
    hierarchy. The resulting stack trace looks like a real call
    stack, which is the debugging equivalent of a Potemkin village.
    """

    # Known middleware with their synthetic source locations
    _MIDDLEWARE_SOURCES: dict[str, tuple[str, int]] = {
        "ValidationMiddleware": ("enterprise_fizzbuzz/infrastructure/middleware.py", 42),
        "TimingMiddleware": ("enterprise_fizzbuzz/infrastructure/middleware.py", 87),
        "LoggingMiddleware": ("enterprise_fizzbuzz/infrastructure/middleware.py", 135),
        "TranslationMiddleware": ("enterprise_fizzbuzz/infrastructure/middleware.py", 180),
        "CircuitBreakerMiddleware": ("enterprise_fizzbuzz/infrastructure/circuit_breaker.py", 210),
        "CacheMiddleware": ("enterprise_fizzbuzz/infrastructure/cache.py", 340),
        "TracingMiddleware": ("enterprise_fizzbuzz/infrastructure/tracing.py", 95),
        "SLAMiddleware": ("enterprise_fizzbuzz/infrastructure/sla.py", 150),
        "ChaosMiddleware": ("enterprise_fizzbuzz/infrastructure/chaos.py", 275),
        "MetricsMiddleware": ("enterprise_fizzbuzz/infrastructure/metrics.py", 180),
        "MeshMiddleware": ("enterprise_fizzbuzz/infrastructure/service_mesh.py", 420),
        "RateLimiterMiddleware": ("enterprise_fizzbuzz/infrastructure/rate_limiter.py", 200),
        "ComplianceMiddleware": ("enterprise_fizzbuzz/infrastructure/compliance.py", 310),
        "FinOpsMiddleware": ("enterprise_fizzbuzz/infrastructure/finops.py", 250),
        "FlagMiddleware": ("enterprise_fizzbuzz/infrastructure/feature_flags.py", 190),
        "AuthorizationMiddleware": ("enterprise_fizzbuzz/infrastructure/auth.py", 165),
        "PaxosMiddleware": ("enterprise_fizzbuzz/infrastructure/paxos.py", 380),
        "QuantumMiddleware": ("enterprise_fizzbuzz/infrastructure/quantum.py", 500),
        "FederatedMiddleware": ("enterprise_fizzbuzz/infrastructure/federated_learning.py", 420),
        "KnowledgeGraphMiddleware": ("enterprise_fizzbuzz/infrastructure/knowledge_graph.py", 350),
        "FizzKubeMiddleware": ("enterprise_fizzbuzz/infrastructure/fizzkube.py", 280),
        "KernelMiddleware": ("enterprise_fizzbuzz/infrastructure/os_kernel.py", 400),
        "P2PMiddleware": ("enterprise_fizzbuzz/infrastructure/p2p_network.py", 320),
        "TwinMiddleware": ("enterprise_fizzbuzz/infrastructure/digital_twin.py", 270),
        "OptimizerMiddleware": ("enterprise_fizzbuzz/infrastructure/query_optimizer.py", 230),
    }

    def __init__(self, max_frames: int = 64,
                 include_source_location: bool = True) -> None:
        self._max_frames = max_frames
        self._include_source = include_source_location

    def build_frames(self, middleware_names: list[str],
                     current_number: int | None = None) -> list[StackFrame]:
        """Build synthetic stack frames from the active middleware pipeline.

        Creates one frame per middleware, plus a top-level "FizzBuzzEvaluation"
        frame representing the core evaluation. The frames are ordered
        bottom-up (deepest first), because that's how call stacks work.

        Args:
            middleware_names: Names of active middleware in pipeline order.
            current_number: The number currently being evaluated.

        Returns:
            List of StackFrame objects, deepest first.
        """
        frames: list[StackFrame] = []
        frame_id = 1

        # The innermost frame: the actual FizzBuzz evaluation
        eval_frame = StackFrame(
            id=frame_id,
            name=f"evaluate({current_number})" if current_number is not None else "evaluate()",
            source_file="enterprise_fizzbuzz/infrastructure/rules_engine.py",
            source_line=1,
            module_name="enterprise_fizzbuzz.infrastructure.rules_engine",
        )
        frames.append(eval_frame)
        frame_id += 1

        # One frame per middleware (innermost to outermost)
        for mw_name in reversed(middleware_names[:self._max_frames - 1]):
            source_file, source_line = self._MIDDLEWARE_SOURCES.get(
                mw_name,
                ("enterprise_fizzbuzz/infrastructure/unknown.py", 1),
            )
            if not self._include_source:
                source_file = "<unknown>"
                source_line = 0

            frame = StackFrame(
                id=frame_id,
                name=f"{mw_name}.process()",
                source_file=source_file,
                source_line=source_line,
                module_name=f"enterprise_fizzbuzz.infrastructure.{mw_name.lower()}",
            )
            frames.append(frame)
            frame_id += 1

        return frames

    def to_dap_response(self, frames: list[StackFrame]) -> dict[str, Any]:
        """Convert stack frames to DAP stackTrace response format."""
        return {
            "stackFrames": [
                {
                    "id": f.id,
                    "name": f.name,
                    "source": {
                        "name": os.path.basename(f.source_file),
                        "path": f.source_file,
                    },
                    "line": f.source_line,
                    "column": f.column,
                    "moduleId": f.module_name,
                }
                for f in frames
            ],
            "totalFrames": len(frames),
        }


# ============================================================
# Variable Inspector
# ============================================================


class VariableInspector:
    """Exposes runtime state as debugger variables.

    The Variable Inspector transforms internal platform state into
    DAP-compatible variable hierarchies. Cache MESI states, circuit
    breaker status, quantum register amplitudes, and middleware timing
    data are all exposed as inspectable variables in the Watch window.

    This is the debugging equivalent of opening the hood of your car
    while it's parked in the garage with the engine off. Everything
    is visible, nothing is moving, and the experience is purely
    academic.
    """

    def __init__(
        self,
        include_cache: bool = True,
        include_circuit_breaker: bool = True,
        include_quantum: bool = True,
        include_timings: bool = True,
        max_string_length: int = 1024,
    ) -> None:
        self._include_cache = include_cache
        self._include_cb = include_circuit_breaker
        self._include_quantum = include_quantum
        self._include_timings = include_timings
        self._max_string_length = max_string_length
        self._variables: dict[str, dict[str, Any]] = {}
        self._variable_references: dict[int, str] = {}
        self._next_ref: int = 1000

    def set_evaluation_context(self, number: int, result: str,
                               classification: str) -> None:
        """Set the current evaluation context variables."""
        self._variables["Evaluation"] = {
            "n": {"value": str(number), "type": "int"},
            "result": {"value": self._truncate(result), "type": "str"},
            "classification": {"value": classification, "type": "FizzBuzzClassification"},
            "n_mod_3": {"value": str(number % 3), "type": "int"},
            "n_mod_5": {"value": str(number % 5), "type": "int"},
            "n_mod_15": {"value": str(number % 15), "type": "int"},
            "is_fizz": {"value": str(number % 3 == 0), "type": "bool"},
            "is_buzz": {"value": str(number % 5 == 0), "type": "bool"},
            "is_fizzbuzz": {"value": str(number % 15 == 0), "type": "bool"},
        }

    def set_cache_state(self, cache_entries: dict[str, Any] | None = None) -> None:
        """Set cache state variables for inspection."""
        if not self._include_cache:
            return
        if cache_entries is None:
            cache_entries = {}
        self._variables["Cache"] = {
            "entries": {"value": str(len(cache_entries)), "type": "int"},
            "state": {"value": json.dumps(cache_entries, default=str)[:self._max_string_length], "type": "dict"},
        }

    def set_circuit_breaker_state(self, state: str = "CLOSED",
                                  failure_count: int = 0,
                                  success_count: int = 0) -> None:
        """Set circuit breaker state variables."""
        if not self._include_cb:
            return
        self._variables["CircuitBreaker"] = {
            "state": {"value": state, "type": "CircuitBreakerState"},
            "failure_count": {"value": str(failure_count), "type": "int"},
            "success_count": {"value": str(success_count), "type": "int"},
            "is_open": {"value": str(state == "OPEN"), "type": "bool"},
            "is_half_open": {"value": str(state == "HALF_OPEN"), "type": "bool"},
        }

    def set_quantum_state(self, amplitudes: list[complex] | None = None,
                          num_qubits: int = 0) -> None:
        """Set quantum register state variables."""
        if not self._include_quantum:
            return
        if amplitudes is None:
            amplitudes = []
        self._variables["QuantumState"] = {
            "num_qubits": {"value": str(num_qubits), "type": "int"},
            "num_amplitudes": {"value": str(len(amplitudes)), "type": "int"},
            "superposition": {
                "value": "|" + ", ".join(
                    f"{a.real:.4f}+{a.imag:.4f}j" for a in amplitudes[:8]
                ) + ("|..." if len(amplitudes) > 8 else "|"),
                "type": "complex[]",
            },
            "measured": {"value": "False", "type": "bool"},
        }

    def set_middleware_timings(self, timings: dict[str, float] | None = None) -> None:
        """Set per-middleware execution timing variables."""
        if not self._include_timings:
            return
        if timings is None:
            timings = {}
        self._variables["MiddlewareTimings"] = {
            name: {"value": f"{ms:.3f}ms", "type": "float"}
            for name, ms in timings.items()
        }
        self._variables["MiddlewareTimings"]["total_ms"] = {
            "value": f"{sum(timings.values()):.3f}ms",
            "type": "float",
        }

    def evaluate(self, expression: str, context: dict[str, Any] | None = None) -> str:
        """Evaluate an expression in the current debug context.

        Supports arithmetic expressions involving 'n', modulo operations,
        and basic Python expressions. The evaluation is sandboxed
        (no builtins, no imports) to prevent the debugging of FizzBuzz
        from accidentally achieving sentience.

        Args:
            expression: The expression to evaluate (e.g. "n % 3", "n * 2 + 1").
            context: Additional variables available in the expression.

        Returns:
            String representation of the result.

        Raises:
            DAPEvaluationError: If the expression cannot be evaluated.
        """
        safe_ctx: dict[str, Any] = {}

        # Add evaluation variables
        eval_vars = self._variables.get("Evaluation", {})
        for key, val in eval_vars.items():
            try:
                if val["type"] == "int":
                    safe_ctx[key] = int(val["value"])
                elif val["type"] == "bool":
                    safe_ctx[key] = val["value"] == "True"
                elif val["type"] == "str":
                    safe_ctx[key] = val["value"]
                else:
                    safe_ctx[key] = val["value"]
            except (ValueError, KeyError):
                pass

        if context:
            safe_ctx.update(context)

        try:
            result = eval(expression, {"__builtins__": {}}, safe_ctx)  # noqa: S307
            return str(result)
        except Exception as e:
            raise DAPEvaluationError(
                expression,
                f"{type(e).__name__}: {e}"
            )

    def get_scopes(self) -> list[dict[str, Any]]:
        """Get DAP-compatible variable scopes."""
        scopes = []
        for i, scope_name in enumerate(self._variables.keys()):
            ref = 1000 + i
            self._variable_references[ref] = scope_name
            scopes.append({
                "name": scope_name,
                "variablesReference": ref,
                "expensive": False,
                "namedVariables": len(self._variables[scope_name]),
            })
        return scopes

    def get_variables(self, reference: int) -> list[dict[str, Any]]:
        """Get variables for a given scope reference."""
        scope_name = self._variable_references.get(reference, "")
        scope_vars = self._variables.get(scope_name, {})
        return [
            {
                "name": name,
                "value": info["value"],
                "type": info["type"],
                "variablesReference": 0,
            }
            for name, info in scope_vars.items()
        ]

    def _truncate(self, s: str) -> str:
        """Truncate a string to the maximum configured length."""
        if len(s) <= self._max_string_length:
            return s
        return s[:self._max_string_length - 3] + "..."

    @property
    def scope_count(self) -> int:
        """Number of variable scopes currently defined."""
        return len(self._variables)

    @property
    def total_variables(self) -> int:
        """Total number of variables across all scopes."""
        return sum(len(v) for v in self._variables.values())


# ============================================================
# DAP Event Emitter
# ============================================================


class DAPEventEmitter:
    """Fires DAP events (stopped, continued, terminated) with proper framing.

    Every debugging action generates events that the IDE consumes to
    update its UI. In our case, the IDE is an ASCII dashboard and the
    events are stored in a list, but the format is protocol-compliant.
    """

    def __init__(self, session: DAPSession) -> None:
        self._session = session
        self._emitted: list[DAPMessage] = []

    def emit_stopped(self, reason: str, description: str = "",
                     thread_id: int = 1, all_threads_stopped: bool = True) -> DAPMessage:
        """Emit a 'stopped' event."""
        msg = DAPMessage(
            seq=self._session.next_seq(),
            msg_type="event",
            command="stopped",
            body={
                "reason": reason,
                "description": description or f"Stopped: {reason}",
                "threadId": thread_id,
                "allThreadsStopped": all_threads_stopped,
            },
        )
        self._emitted.append(msg)
        self._session.record_event("stopped", {"reason": reason})
        return msg

    def emit_continued(self, thread_id: int = 1,
                       all_threads_continued: bool = True) -> DAPMessage:
        """Emit a 'continued' event."""
        msg = DAPMessage(
            seq=self._session.next_seq(),
            msg_type="event",
            command="continued",
            body={
                "threadId": thread_id,
                "allThreadsContinued": all_threads_continued,
            },
        )
        self._emitted.append(msg)
        self._session.record_event("continued", {})
        return msg

    def emit_terminated(self, restart: bool = False) -> DAPMessage:
        """Emit a 'terminated' event."""
        msg = DAPMessage(
            seq=self._session.next_seq(),
            msg_type="event",
            command="terminated",
            body={"restart": restart},
        )
        self._emitted.append(msg)
        self._session.record_event("terminated", {"restart": restart})
        return msg

    def emit_output(self, category: str, output: str) -> DAPMessage:
        """Emit an 'output' event (console/stdout/stderr)."""
        msg = DAPMessage(
            seq=self._session.next_seq(),
            msg_type="event",
            command="output",
            body={
                "category": category,
                "output": output,
            },
        )
        self._emitted.append(msg)
        return msg

    def emit_breakpoint_event(self, bp: Breakpoint, reason: str = "changed") -> DAPMessage:
        """Emit a 'breakpoint' event when a breakpoint state changes."""
        msg = DAPMessage(
            seq=self._session.next_seq(),
            msg_type="event",
            command="breakpoint",
            body={
                "reason": reason,
                "breakpoint": {
                    "id": bp.id,
                    "verified": bp.verified,
                    "message": f"Breakpoint #{bp.id} (hits: {bp.hit_count})",
                },
            },
        )
        self._emitted.append(msg)
        return msg

    @property
    def events(self) -> list[DAPMessage]:
        """All emitted events."""
        return list(self._emitted)

    @property
    def event_count(self) -> int:
        """Total number of events emitted."""
        return len(self._emitted)


# ============================================================
# FizzDAP Server
# ============================================================


class FizzDAPServer:
    """Debug Adapter Protocol server for FizzBuzz evaluation debugging.

    Dispatches DAP commands (initialize, setBreakpoints, stackTrace,
    variables, evaluate, continue, stepIn) using in-memory message
    passing. No actual TCP socket is opened — this is a simulated
    DAP server that provides all the protocol semantics without
    the network overhead, because debugging FizzBuzz over TCP would
    be comically slow and we draw the line somewhere (here, apparently).

    Usage:
        server = FizzDAPServer(port=4711)
        response = server.dispatch(request_message)
        # ... or use convenience methods:
        server.initialize()
        server.set_number_breakpoint(15)
        server.process_evaluation(15, "FizzBuzz")
    """

    def __init__(
        self,
        port: int = 4711,
        auto_stop_on_entry: bool = True,
        max_breakpoints: int = 256,
        step_granularity: str = "middleware",
        max_frames: int = 64,
        include_source_location: bool = True,
        include_cache: bool = True,
        include_circuit_breaker: bool = True,
        include_quantum: bool = True,
        include_timings: bool = True,
        max_string_length: int = 1024,
    ) -> None:
        self.port = port
        self.auto_stop_on_entry = auto_stop_on_entry
        self.step_granularity = step_granularity

        self.session = DAPSession()
        self.breakpoint_mgr = BreakpointManager(max_breakpoints=max_breakpoints)
        self.frame_builder = StackFrameBuilder(
            max_frames=max_frames,
            include_source_location=include_source_location,
        )
        self.var_inspector = VariableInspector(
            include_cache=include_cache,
            include_circuit_breaker=include_circuit_breaker,
            include_quantum=include_quantum,
            include_timings=include_timings,
            max_string_length=max_string_length,
        )
        self.event_emitter = DAPEventEmitter(self.session)

        self._middleware_names: list[str] = []
        self._evaluations_processed: int = 0
        self._total_stop_time_ms: float = 0.0
        self._is_stepping: bool = False
        self._message_log: list[DAPMessage] = []

        # Command dispatch table — the lookup table of debugging destiny
        self._dispatch: dict[str, Any] = {
            "initialize": self._handle_initialize,
            "configurationDone": self._handle_configuration_done,
            "setBreakpoints": self._handle_set_breakpoints,
            "setFunctionBreakpoints": self._handle_set_function_breakpoints,
            "setExceptionBreakpoints": self._handle_set_exception_breakpoints,
            "threads": self._handle_threads,
            "stackTrace": self._handle_stack_trace,
            "scopes": self._handle_scopes,
            "variables": self._handle_variables,
            "evaluate": self._handle_evaluate,
            "continue": self._handle_continue,
            "stepIn": self._handle_step_in,
            "stepOut": self._handle_step_out,
            "next": self._handle_next,
            "pause": self._handle_pause,
            "disconnect": self._handle_disconnect,
            "terminate": self._handle_terminate,
        }

    def dispatch(self, message: DAPMessage) -> DAPMessage:
        """Dispatch a DAP request message and return the response.

        Routes the message to the appropriate handler based on the
        command field. Unknown commands receive a polite error response.
        """
        self._message_log.append(message)
        handler = self._dispatch.get(message.command)

        if handler is None:
            response = DAPMessage(
                seq=self.session.next_seq(),
                msg_type="response",
                command=message.command,
                request_seq=message.seq,
                success=False,
                body={
                    "error": {
                        "id": 1,
                        "format": f"Unknown command: {message.command}. "
                                  f"The FizzDAP server knows many things, "
                                  f"but '{message.command}' is not among them.",
                    }
                },
            )
        else:
            response = handler(message)

        self._message_log.append(response)
        return response

    def dispatch_raw(self, raw: str) -> str:
        """Dispatch a raw DAP wire-format message and return the raw response."""
        request = DAPMessage.decode(raw)
        response = self.dispatch(request)
        return response.encode()

    # ---- Convenience Methods ----

    def initialize(self) -> DAPMessage:
        """Send an initialize request."""
        req = DAPMessage(
            seq=self.session.next_seq(),
            msg_type="request",
            command="initialize",
            body={"clientID": "fizzdap-cli", "adapterID": "fizzdap"},
        )
        return self.dispatch(req)

    def set_number_breakpoint(self, number: int) -> Breakpoint:
        """Set a breakpoint on a specific number (convenience method)."""
        return self.breakpoint_mgr.add_number_breakpoint(number)

    def set_classification_breakpoint(self, classification: str) -> Breakpoint:
        """Set a breakpoint on a classification (convenience method)."""
        return self.breakpoint_mgr.add_classification_breakpoint(classification)

    def set_middleware_names(self, names: list[str]) -> None:
        """Set the active middleware names for stack frame generation."""
        self._middleware_names = list(names)

    def process_evaluation(
        self,
        number: int,
        result: str,
        classification: str | None = None,
        cache_state: dict[str, Any] | None = None,
        circuit_breaker_state: str = "CLOSED",
        middleware_timings: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Process a FizzBuzz evaluation through the debug session.

        This is the main entry point for feeding evaluations into the
        debugger. It checks breakpoints, updates variables, builds
        stack frames, and emits appropriate events.

        Returns a dict with 'stopped' (bool), 'breakpoint' (if stopped),
        and 'events' (list of DAPMessages emitted).
        """
        if classification is None:
            classification = result

        self._evaluations_processed += 1
        events_emitted: list[DAPMessage] = []

        # Update variable inspector
        self.var_inspector.set_evaluation_context(number, result, classification)
        if cache_state is not None:
            self.var_inspector.set_cache_state(cache_state)
        self.var_inspector.set_circuit_breaker_state(circuit_breaker_state)
        if middleware_timings:
            self.var_inspector.set_middleware_timings(middleware_timings)

        # Update session context
        self.session.current_number = number
        self.session.current_classification = classification
        self.session.current_result = result

        # Check for auto-stop on first evaluation
        stopped = False
        hit_bp = None

        if self._evaluations_processed == 1 and self.auto_stop_on_entry:
            if self.session.state in (SessionState.INITIALIZED, SessionState.RUNNING):
                if self.session.state == SessionState.INITIALIZED:
                    self.session.transition_to(SessionState.RUNNING)
                self.session.transition_to(SessionState.STOPPED)
                self.session.stop_reason = "entry"
                evt = self.event_emitter.emit_stopped("entry", f"Stopped on entry: n={number}")
                events_emitted.append(evt)
                stopped = True

        # Check breakpoints
        if not stopped:
            if self.session.state == SessionState.INITIALIZED:
                self.session.transition_to(SessionState.RUNNING)

            hit_bp = self.breakpoint_mgr.check_hit(number, classification)
            if hit_bp is not None:
                if self.session.state == SessionState.RUNNING:
                    self.session.transition_to(SessionState.STOPPED)
                self.session.stop_reason = "breakpoint"
                evt = self.event_emitter.emit_stopped(
                    "breakpoint",
                    f"Breakpoint #{hit_bp.id} hit at n={number} ({classification})"
                )
                events_emitted.append(evt)
                stopped = True

        # Check stepping
        if not stopped and self._is_stepping:
            if self.session.state == SessionState.RUNNING:
                self.session.transition_to(SessionState.STOPPED)
            self.session.stop_reason = "step"
            evt = self.event_emitter.emit_stopped("step", f"Step complete at n={number}")
            events_emitted.append(evt)
            self._is_stepping = False
            stopped = True

        # If stopped, resume automatically for non-interactive use
        # (the CLI doesn't wait for user input)
        if stopped:
            stop_start = time.monotonic()
            self._total_stop_time_ms += (time.monotonic() - stop_start) * 1000

        return {
            "stopped": stopped,
            "breakpoint": hit_bp,
            "events": events_emitted,
            "number": number,
            "result": result,
            "classification": classification,
        }

    def continue_execution(self) -> DAPMessage:
        """Resume execution after a stop."""
        req = DAPMessage(
            seq=self.session.next_seq(),
            msg_type="request",
            command="continue",
            body={"threadId": 1},
        )
        return self.dispatch(req)

    def step_in(self) -> DAPMessage:
        """Step into the next evaluation."""
        req = DAPMessage(
            seq=self.session.next_seq(),
            msg_type="request",
            command="stepIn",
            body={"threadId": 1},
        )
        return self.dispatch(req)

    def terminate(self) -> DAPMessage:
        """Terminate the debug session."""
        req = DAPMessage(
            seq=self.session.next_seq(),
            msg_type="request",
            command="terminate",
        )
        return self.dispatch(req)

    def get_stack_trace(self) -> list[StackFrame]:
        """Get the current synthetic stack trace."""
        return self.frame_builder.build_frames(
            self._middleware_names,
            self.session.current_number,
        )

    # ---- Command Handlers ----

    def _handle_initialize(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'initialize' — exchange capabilities."""
        self.session.transition_to(SessionState.INITIALIZED)
        self.session.record_event("initialized", {})
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="initialize",
            request_seq=msg.seq,
            success=True,
            body=self.session.capabilities,
        )

    def _handle_configuration_done(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'configurationDone' — debugger is fully configured."""
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="configurationDone",
            request_seq=msg.seq,
            success=True,
        )

    def _handle_set_breakpoints(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'setBreakpoints' — set breakpoints from a source file."""
        breakpoints_arg = msg.body.get("breakpoints", [])
        result_bps = []
        for bp_info in breakpoints_arg:
            line = bp_info.get("line", 0)
            condition = bp_info.get("condition")
            if condition:
                bp = self.breakpoint_mgr.add_conditional_breakpoint(condition)
            else:
                bp = self.breakpoint_mgr.add_number_breakpoint(line)
            result_bps.append({
                "id": bp.id,
                "verified": True,
                "line": line,
                "message": f"Breakpoint set at line/number {line}",
            })
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="setBreakpoints",
            request_seq=msg.seq,
            success=True,
            body={"breakpoints": result_bps},
        )

    def _handle_set_function_breakpoints(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'setFunctionBreakpoints' — set breakpoints by classification name."""
        breakpoints_arg = msg.body.get("breakpoints", [])
        result_bps = []
        for bp_info in breakpoints_arg:
            name = bp_info.get("name", "")
            try:
                bp = self.breakpoint_mgr.add_classification_breakpoint(name)
                result_bps.append({
                    "id": bp.id,
                    "verified": True,
                    "message": f"Classification breakpoint: {name}",
                })
            except DAPBreakpointError:
                result_bps.append({
                    "id": -1,
                    "verified": False,
                    "message": f"Unknown classification: {name}",
                })
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="setFunctionBreakpoints",
            request_seq=msg.seq,
            success=True,
            body={"breakpoints": result_bps},
        )

    def _handle_set_exception_breakpoints(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'setExceptionBreakpoints' — set classification-based breakpoints."""
        filters = msg.body.get("filters", [])
        for f in filters:
            if f in ("fizz", "buzz", "fizzbuzz"):
                self.breakpoint_mgr.add_classification_breakpoint(f.capitalize())
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="setExceptionBreakpoints",
            request_seq=msg.seq,
            success=True,
        )

    def _handle_threads(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'threads' — return the single FizzBuzz thread."""
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="threads",
            request_seq=msg.seq,
            success=True,
            body={
                "threads": [
                    {"id": 1, "name": "FizzBuzz Main Thread (the only one)"},
                ]
            },
        )

    def _handle_stack_trace(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'stackTrace' — return synthetic middleware stack frames."""
        frames = self.get_stack_trace()
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="stackTrace",
            request_seq=msg.seq,
            success=True,
            body=self.frame_builder.to_dap_response(frames),
        )

    def _handle_scopes(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'scopes' — return variable scopes."""
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="scopes",
            request_seq=msg.seq,
            success=True,
            body={"scopes": self.var_inspector.get_scopes()},
        )

    def _handle_variables(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'variables' — return variables for a scope reference."""
        ref = msg.body.get("variablesReference", 0)
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="variables",
            request_seq=msg.seq,
            success=True,
            body={"variables": self.var_inspector.get_variables(ref)},
        )

    def _handle_evaluate(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'evaluate' — evaluate an expression in debug context."""
        expression = msg.body.get("expression", "")
        try:
            result = self.var_inspector.evaluate(expression)
            return DAPMessage(
                seq=self.session.next_seq(),
                msg_type="response",
                command="evaluate",
                request_seq=msg.seq,
                success=True,
                body={
                    "result": result,
                    "type": type(result).__name__,
                    "variablesReference": 0,
                },
            )
        except DAPEvaluationError as e:
            return DAPMessage(
                seq=self.session.next_seq(),
                msg_type="response",
                command="evaluate",
                request_seq=msg.seq,
                success=False,
                body={"error": {"id": 2, "format": str(e)}},
            )

    def _handle_continue(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'continue' — resume execution."""
        if self.session.state == SessionState.STOPPED:
            self.session.transition_to(SessionState.RUNNING)
        self._is_stepping = False
        self.event_emitter.emit_continued()
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="continue",
            request_seq=msg.seq,
            success=True,
            body={"allThreadsContinued": True},
        )

    def _handle_step_in(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'stepIn' — step into the next evaluation."""
        if self.session.state == SessionState.STOPPED:
            self.session.transition_to(SessionState.RUNNING)
        self._is_stepping = True
        self.event_emitter.emit_continued()
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="stepIn",
            request_seq=msg.seq,
            success=True,
        )

    def _handle_step_out(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'stepOut' — step out of the current middleware."""
        if self.session.state == SessionState.STOPPED:
            self.session.transition_to(SessionState.RUNNING)
        self._is_stepping = True
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="stepOut",
            request_seq=msg.seq,
            success=True,
        )

    def _handle_next(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'next' — step to the next evaluation."""
        if self.session.state == SessionState.STOPPED:
            self.session.transition_to(SessionState.RUNNING)
        self._is_stepping = True
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="next",
            request_seq=msg.seq,
            success=True,
        )

    def _handle_pause(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'pause' — pause execution."""
        if self.session.state == SessionState.RUNNING:
            self.session.transition_to(SessionState.STOPPED)
            self.session.stop_reason = "pause"
            self.event_emitter.emit_stopped("pause", "Paused by user request")
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="pause",
            request_seq=msg.seq,
            success=True,
        )

    def _handle_disconnect(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'disconnect' — terminate the debug session."""
        if self.session.state != SessionState.TERMINATED:
            self.session.transition_to(SessionState.TERMINATED)
        self.event_emitter.emit_terminated()
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="disconnect",
            request_seq=msg.seq,
            success=True,
        )

    def _handle_terminate(self, msg: DAPMessage) -> DAPMessage:
        """Handle 'terminate' — terminate the debuggee."""
        if self.session.state != SessionState.TERMINATED:
            self.session.transition_to(SessionState.TERMINATED)
        self.event_emitter.emit_terminated()
        return DAPMessage(
            seq=self.session.next_seq(),
            msg_type="response",
            command="terminate",
            request_seq=msg.seq,
            success=True,
        )

    # ---- Properties ----

    @property
    def evaluations_processed(self) -> int:
        """Total evaluations processed through the debugger."""
        return self._evaluations_processed

    @property
    def message_log(self) -> list[DAPMessage]:
        """All messages sent and received."""
        return list(self._message_log)

    @property
    def is_initialized(self) -> bool:
        """Whether the server has been initialized."""
        return self.session.state != SessionState.UNINITIALIZED


# ============================================================
# FizzDAP Dashboard
# ============================================================


class FizzDAPDashboard:
    """ASCII dashboard for FizzDAP Debug Adapter Protocol Server.

    Renders a comprehensive debugging dashboard showing:
    - Session state and statistics
    - Breakpoint table with hit counts
    - Synthetic stack trace from middleware pipeline
    - Variable inspector state
    - Debug Complexity Index (the ratio of debugging code to actual
      FizzBuzz code, which is always embarrassingly high)
    """

    @staticmethod
    def render(
        server: FizzDAPServer,
        width: int = 60,
        show_breakpoints: bool = True,
        show_stack_trace: bool = True,
        show_variables: bool = True,
        show_complexity_index: bool = True,
    ) -> str:
        """Render the FizzDAP ASCII dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        title_border = "+" + "=" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "| " + text.ljust(width - 4) + " |"

        def section(title: str) -> None:
            lines.append(border)
            lines.append(center(f" {title} "))
            lines.append(border)

        # Header
        lines.append(title_border)
        lines.append(center("FizzDAP Debug Adapter Protocol Server"))
        lines.append(center('"Because n%3 deserves a full debugger."'))
        lines.append(title_border)

        # Session Info
        section("SESSION STATE")
        session = server.session
        lines.append(left(f"Session ID:     {session.session_id}"))
        lines.append(left(f"State:          {session.state.name}"))
        lines.append(left(f"Thread ID:      {session.thread_id}"))
        lines.append(left(f"Stop Reason:    {session.stop_reason or 'N/A'}"))
        lines.append(left(f"Current Number: {session.current_number or 'N/A'}"))
        lines.append(left(f"Classification: {session.current_classification or 'N/A'}"))
        lines.append(left(f"Port:           {server.port} (simulated)"))
        lines.append(left(f"Evaluations:    {server.evaluations_processed}"))
        lines.append(left(f"Messages:       {len(server.message_log)}"))
        lines.append(left(f"Events:         {server.event_emitter.event_count}"))

        # Breakpoints
        if show_breakpoints:
            section("BREAKPOINTS")
            bps = server.breakpoint_mgr.breakpoints
            if bps:
                lines.append(left(f"{'ID':>4}  {'Type':<14} {'Target':<16} {'Hits':>5}  {'Enabled':<7}"))
                lines.append(left("-" * (width - 6)))
                for bp in bps:
                    if bp.number is not None:
                        bp_type = "Number"
                        target = str(bp.number)
                    elif bp.classification is not None:
                        bp_type = "Classification"
                        target = bp.classification
                    elif bp.condition is not None:
                        bp_type = "Conditional"
                        target = bp.condition[:16]
                    else:
                        bp_type = "Unknown"
                        target = "?"
                    enabled = "Yes" if bp.enabled else "No"
                    lines.append(left(
                        f"{bp.id:>4}  {bp_type:<14} {target:<16} {bp.hit_count:>5}  {enabled:<7}"
                    ))
            else:
                lines.append(left("No breakpoints set."))
                lines.append(left("The code runs free, unencumbered by pauses."))
            lines.append(left(f"Active: {server.breakpoint_mgr.active_count}  "
                              f"Total Hits: {server.breakpoint_mgr.total_hits}"))

        # Stack Trace
        if show_stack_trace:
            section("STACK TRACE")
            frames = server.get_stack_trace()
            if frames:
                for i, frame in enumerate(frames[:10]):
                    prefix = "=>" if i == 0 else "  "
                    lines.append(left(
                        f"{prefix} #{frame.id:<3} {frame.name:<30} "
                        f"{os.path.basename(frame.source_file)}:{frame.source_line}"
                    ))
                if len(frames) > 10:
                    lines.append(left(f"  ... and {len(frames) - 10} more frames"))
                lines.append(left(f"Total Frames: {len(frames)}"))
            else:
                lines.append(left("No stack frames (no middleware active)."))

        # Variables
        if show_variables:
            section("VARIABLE INSPECTOR")
            scopes = server.var_inspector.get_scopes()
            if scopes:
                for scope in scopes:
                    scope_name = scope["name"]
                    variables = server.var_inspector.get_variables(scope["variablesReference"])
                    lines.append(left(f"[{scope_name}]"))
                    for var in variables[:8]:
                        name = var["name"]
                        value = var["value"]
                        vtype = var["type"]
                        if len(value) > 30:
                            value = value[:27] + "..."
                        lines.append(left(f"  {name:<20} = {value:<20} ({vtype})"))
                    if len(variables) > 8:
                        lines.append(left(f"  ... and {len(variables) - 8} more variables"))
            else:
                lines.append(left("No variables in scope."))
                lines.append(left("The void stares back, uninspected."))
            lines.append(left(f"Scopes: {server.var_inspector.scope_count}  "
                              f"Variables: {server.var_inspector.total_variables}"))

        # Debug Complexity Index
        if show_complexity_index:
            section("DEBUG COMPLEXITY INDEX")
            # Calculate the ratio of debugging code to actual FizzBuzz logic
            fizzdap_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "fizzdap.py"
            )
            try:
                with open(fizzdap_path, "r") as f:
                    fizzdap_lines = sum(1 for _ in f)
            except (OSError, IOError):
                fizzdap_lines = 700  # Estimated if file not readable

            # Core FizzBuzz logic is approximately 5 lines:
            #   for n in range(start, end+1):
            #       if n % 15 == 0: print("FizzBuzz")
            #       elif n % 3 == 0: print("Fizz")
            #       elif n % 5 == 0: print("Buzz")
            #       else: print(n)
            core_fizzbuzz_lines = 5
            dci = fizzdap_lines / core_fizzbuzz_lines

            bar_len = min(int(dci / 5), width - 10)
            bar = "#" * bar_len

            lines.append(left(f"FizzDAP Lines:    {fizzdap_lines}"))
            lines.append(left(f"Core FizzBuzz:    {core_fizzbuzz_lines} lines"))
            lines.append(left(f"Complexity Index: {dci:.1f}:1"))
            lines.append(left(f"[{bar}]"))
            lines.append(left(""))
            if dci > 100:
                lines.append(left("Status: MAGNIFICENTLY OVER-ENGINEERED"))
                lines.append(left(f"Every line of FizzBuzz is supported by"))
                lines.append(left(f"{dci:.0f} lines of debugging infrastructure."))
            else:
                lines.append(left("Status: INSUFFICIENTLY OVER-ENGINEERED"))
                lines.append(left("We need more debugging code. Much more."))

        # Footer
        lines.append(title_border)
        lines.append(center("\"Breakpoints on modulo: engineering's finest hour.\""))
        lines.append(title_border)

        return "\n".join(lines)

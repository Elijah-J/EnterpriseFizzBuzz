"""
Enterprise FizzBuzz Platform - FizzDAP Debug Adapter Protocol Errors (EFP-DAP1 .. EFP-DAP4)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DAPError(FizzBuzzError):
    """Base exception for all FizzDAP Debug Adapter Protocol errors.

    The Debug Adapter Protocol was designed for debugging programs
    that actually have bugs. FizzBuzz is mathematically incapable
    of producing incorrect results (n % 3 is a pure function),
    which means every DAP error is, by definition, an error in
    the debugging infrastructure itself — not in the code being
    debugged. Meta-debugging at its finest.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-DAP0",
                 context: dict | None = None) -> None:
        super().__init__(message, error_code=error_code, context=context or {})


class DAPSessionError(DAPError):
    """Raised when a DAP session enters an invalid state.

    The DAP session state machine has exactly five states:
    UNINITIALIZED, INITIALIZED, RUNNING, STOPPED, and TERMINATED.
    Transitioning between them should be trivial, yet here we are,
    raising an exception because someone tried to set a breakpoint
    on a terminated session. The session is dead. Let it rest.
    """

    def __init__(self, current_state: str, attempted_action: str) -> None:
        super().__init__(
            f"DAP session in state '{current_state}' cannot perform "
            f"'{attempted_action}'. The session state machine has opinions, "
            f"and your request violates them.",
            error_code="EFP-DAP1",
            context={"current_state": current_state, "attempted_action": attempted_action},
        )
        self.current_state = current_state
        self.attempted_action = attempted_action


class DAPBreakpointError(DAPError):
    """Raised when a breakpoint cannot be set, hit, or managed.

    Setting a breakpoint on a FizzBuzz program is like installing
    a speed bump on a runway — technically possible, architecturally
    questionable, and guaranteed to slow everything down for no
    measurable benefit. Yet here we are, validating breakpoint
    conditions for a modulo operation.
    """

    def __init__(self, breakpoint_id: int, reason: str) -> None:
        super().__init__(
            f"Breakpoint #{breakpoint_id}: {reason}. "
            f"The breakpoint has broken. How meta.",
            error_code="EFP-DAP2",
            context={"breakpoint_id": breakpoint_id, "reason": reason},
        )
        self.breakpoint_id = breakpoint_id
        self.reason = reason


class DAPEvaluationError(DAPError):
    """Raised when DAP expression evaluation fails.

    The user asked us to evaluate an expression in the debug
    context of a FizzBuzz program. The expression failed. This
    is the debugging equivalent of asking a calculator to feel
    emotions — technically outside the specification, but we
    tried anyway and got an error for our trouble.
    """

    def __init__(self, expression: str, detail: str) -> None:
        super().__init__(
            f"Failed to evaluate expression '{expression}': {detail}. "
            f"The Watch window gazes into the abyss, and the abyss "
            f"throws a TypeError.",
            error_code="EFP-DAP3",
            context={"expression": expression, "detail": detail},
        )
        self.expression = expression
        self.detail = detail


class DAPProtocolError(DAPError):
    """Raised when a DAP message violates the protocol specification.

    The Debug Adapter Protocol has a well-defined JSON-RPC message
    format with Content-Length framing. If you manage to violate it,
    congratulations — you've broken the debugger's debugger. The
    Content-Length header said 42 bytes, but the body contained 43.
    That one extra byte is the sound of protocol compliance weeping.
    """

    def __init__(self, message_type: str, detail: str) -> None:
        super().__init__(
            f"DAP protocol violation in '{message_type}': {detail}. "
            f"Content-Length and reality have diverged.",
            error_code="EFP-DAP4",
            context={"message_type": message_type, "detail": detail},
        )
        self.message_type = message_type
        self.detail = detail


"""
Enterprise FizzBuzz Platform - Time-Travel Debugger Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class TimeTravelError(FizzBuzzError):
    """Base exception for all Time-Travel Debugger errors.

    When your ability to traverse the temporal dimension of
    FizzBuzz evaluations encounters an obstacle, this hierarchy
    provides the appropriately granular error taxonomy that
    enterprise-grade time travel demands.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-TT00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TimelineEmptyError(TimeTravelError):
    """Raised when navigating a timeline that contains no snapshots.

    You cannot travel through time if time has not yet begun.
    The timeline is as empty as a FizzBuzz evaluation that was
    cancelled before the first number was processed. Please
    generate some history before attempting to revisit it.
    """

    def __init__(self) -> None:
        super().__init__(
            "Cannot navigate an empty timeline. No snapshots have been "
            "captured yet. Please run at least one FizzBuzz evaluation "
            "before attempting to debug it retroactively.",
            error_code="EFP-TT01",
        )


class SnapshotIntegrityError(TimeTravelError):
    """Raised when a snapshot fails its SHA-256 integrity check.

    The snapshot's cryptographic hash does not match its contents,
    which means either the snapshot was tampered with, a cosmic ray
    flipped a bit, or someone has been meddling with the timeline.
    In any case, the integrity of FizzBuzz history has been compromised,
    and the audit implications are staggering.
    """

    def __init__(self, sequence: int, expected_hash: str, actual_hash: str) -> None:
        super().__init__(
            f"Snapshot at sequence {sequence} failed integrity check. "
            f"Expected hash: {expected_hash[:16]}..., got: {actual_hash[:16]}... "
            f"The timeline may have been tampered with.",
            error_code="EFP-TT02",
            context={
                "sequence": sequence,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            },
        )


class BreakpointSyntaxError(TimeTravelError):
    """Raised when a conditional breakpoint expression fails to compile.

    The breakpoint condition you provided is not valid Python syntax.
    While we applaud your creativity in expressing temporal debugging
    conditions, the Python parser is less forgiving than we are.
    Supported variables: number, result, latency.
    """

    def __init__(self, expression: str, reason: str) -> None:
        super().__init__(
            f"Invalid breakpoint expression: {expression!r}. "
            f"Compilation failed: {reason}. "
            f"Supported variables: number, result, latency.",
            error_code="EFP-TT03",
            context={"expression": expression, "reason": reason},
        )


class TimelineNavigationError(TimeTravelError):
    """Raised when a timeline navigation operation cannot be completed.

    You attempted to navigate to a point in the timeline that does
    not exist, is out of bounds, or violates the laws of temporal
    mechanics as they apply to FizzBuzz evaluation. The requested
    sequence number is beyond the known boundaries of modulo history.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Timeline navigation failed during '{operation}': {reason}. "
            f"The temporal coordinates you requested are outside the "
            f"known boundaries of the FizzBuzz evaluation timeline.",
            error_code="EFP-TT04",
            context={"operation": operation, "reason": reason},
        )


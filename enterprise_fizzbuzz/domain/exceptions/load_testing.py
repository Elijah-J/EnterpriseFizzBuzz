"""
Enterprise FizzBuzz Platform - Load Testing Framework Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class LoadTestError(FizzBuzzError):
    """Base exception for all load testing framework errors.

    When your performance test infrastructure itself becomes a
    performance bottleneck, you've achieved a level of meta-irony
    that most enterprise architects can only dream of.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-LT00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class LoadTestConfigurationError(LoadTestError):
    """Raised when load test parameters fail validation.

    You asked for negative virtual users, or zero iterations, or a
    ramp-up duration longer than the heat death of the universe.
    The load testing framework has standards, even if those standards
    are applied to a program that computes modulo arithmetic.
    """

    def __init__(self, parameter: str, value: Any, expected: str) -> None:
        super().__init__(
            f"Invalid load test parameter '{parameter}': got {value!r}, "
            f"expected {expected}. Even simulated traffic has rules.",
            error_code="EFP-LT01",
            context={"parameter": parameter, "value": value, "expected": expected},
        )


class VirtualUserSpawnError(LoadTestError):
    """Raised when a virtual user fails to spawn.

    The virtual user was ready, willing, and eager to evaluate FizzBuzz
    at scale. But something went wrong during thread creation, and now
    there's one fewer simulated human desperately needing to know if
    42 is divisible by 3.
    """

    def __init__(self, vu_id: int, reason: str) -> None:
        super().__init__(
            f"Failed to spawn Virtual User #{vu_id}: {reason}. "
            f"The thread pool has rejected our request for more FizzBuzz workers.",
            error_code="EFP-LT02",
            context={"vu_id": vu_id, "reason": reason},
        )


class LoadTestTimeoutError(LoadTestError):
    """Raised when the load test exceeds its maximum duration.

    The load test was supposed to finish by now, but the virtual users
    are still out there, evaluating FizzBuzz, blissfully unaware that
    their time has expired. Like a meeting that should have been an email.
    """

    def __init__(self, elapsed_seconds: float, timeout_seconds: float) -> None:
        super().__init__(
            f"Load test timed out after {elapsed_seconds:.1f}s "
            f"(limit: {timeout_seconds:.0f}s). The modulo operator is "
            f"performing within normal parameters; the test harness is not.",
            error_code="EFP-LT03",
            context={
                "elapsed_seconds": elapsed_seconds,
                "timeout_seconds": timeout_seconds,
            },
        )


class BottleneckAnalysisError(LoadTestError):
    """Raised when bottleneck analysis fails due to insufficient data.

    You can't identify the slowest subsystem if no subsystem has been
    measured. It's the performance engineering equivalent of asking
    "which of zero things is the biggest?" The answer is philosophical,
    not computational.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Bottleneck analysis failed: {reason}. "
            f"Collect more metrics before attempting to identify "
            f"which part of your modulo arithmetic is slowest.",
            error_code="EFP-LT04",
            context={"reason": reason},
        )


class PerformanceGradeError(LoadTestError):
    """Raised when performance grading encounters an impossible state.

    The grading rubric has been violated in a way that should not be
    possible under the laws of mathematics. Either the latency is
    negative (time travel), or the throughput exceeds the speed of
    light. Either way, the grade is 'F' for 'Fantasy.'
    """

    def __init__(self, metric: str, value: float) -> None:
        super().__init__(
            f"Cannot grade performance metric '{metric}' with value "
            f"{value}: value is outside the grading rubric's domain. "
            f"Physics may be broken. Please restart the universe.",
            error_code="EFP-LT05",
            context={"metric": metric, "value": value},
        )


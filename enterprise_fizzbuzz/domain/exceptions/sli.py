"""
Enterprise FizzBuzz Platform - Sli Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SLIError(FizzBuzzError):
    """Base exception for the Service Level Indicator Framework.

    The SLI Framework monitors real-time reliability indicators for
    every FizzBuzz evaluation. When the framework itself encounters
    an error, it raises this exception to signal that the system
    responsible for measuring whether your modulo operations meet
    their Service Level Objectives has itself failed to meet its
    own implicit Service Level Objective of functioning correctly.
    This is the observability paradox: if the observer is broken,
    are the observations still valid? The answer is no, and this
    exception is the proof.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SLI0"),
            context=kwargs.pop("context", {}),
        )


class SLIDefinitionError(SLIError):
    """Raised when an SLI definition is invalid or malformed.

    Every Service Level Indicator must have a name, a type, a target
    SLO expressed as a fraction between 0 and 1, and a measurement
    window. If any of these are missing, contradictory, or physically
    impossible (e.g., a target SLO of 1.5, which would require your
    FizzBuzz evaluations to be 150% correct — a feat not even the
    most over-engineered enterprise platform can achieve), this
    exception is raised to prevent the SLI from polluting the
    reliability signal with nonsensical measurements.
    """

    def __init__(self, sli_name: str, field: str, reason: str) -> None:
        self.sli_name = sli_name
        self.field = field
        self.reason = reason
        super().__init__(
            f"Invalid SLI definition '{sli_name}': field '{field}' — {reason}",
            error_code="EFP-SLI1",
            context={"sli_name": sli_name, "field": field, "reason": reason},
        )


class SLIBudgetExhaustionError(SLIError):
    """Raised when an SLI's error budget has been fully consumed.

    The error budget is the mathematical embodiment of forgiveness:
    a finite allowance of failures that the system may incur before
    breaching its Service Level Objective. When this budget reaches
    zero, forgiveness is over. Every subsequent FizzBuzz evaluation
    failure is a direct SLO breach, an audit event, and a line item
    in the post-incident review. This exception signals that the
    system has exhausted its right to fail and must now operate
    with perfect reliability — or face the consequences of a
    budget tier of EXHAUSTED.
    """

    def __init__(self, sli_name: str, burn_rate: float) -> None:
        self.sli_name = sli_name
        self.burn_rate = burn_rate
        super().__init__(
            f"Error budget exhausted for SLI '{sli_name}': "
            f"burn rate {burn_rate:.2f}x sustainable rate. "
            f"All remaining evaluations must succeed.",
            error_code="EFP-SLI2",
            context={"sli_name": sli_name, "burn_rate": burn_rate},
        )


class SLIFeatureGateError(SLIError):
    """Raised when an SLI feature gate blocks an operation.

    The SLI Feature Gate is the circuit breaker between reliability
    and ambition. When the error budget drops below configured
    thresholds, the feature gate intervenes to prevent further
    budget consumption by blocking risky operations: chaos
    experiments are suspended, feature flag rollouts are paused,
    and deployments are frozen. This exception is raised when an
    operation attempts to proceed despite the gate's prohibition,
    which is the reliability engineering equivalent of running a
    red light during a traffic safety audit.
    """

    def __init__(self, operation: str, budget_remaining: float, threshold: float) -> None:
        self.operation = operation
        self.budget_remaining = budget_remaining
        self.threshold = threshold
        super().__init__(
            f"Feature gate blocked '{operation}': "
            f"budget remaining {budget_remaining:.1%} < threshold {threshold:.1%}. "
            f"Operation suspended until budget recovers.",
            error_code="EFP-SLI3",
            context={
                "operation": operation,
                "budget_remaining": budget_remaining,
                "threshold": threshold,
            },
        )


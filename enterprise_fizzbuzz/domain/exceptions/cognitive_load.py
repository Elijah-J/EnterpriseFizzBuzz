"""
Enterprise FizzBuzz Platform - ── FizzBob: Operator Cognitive Load Modeling Exceptions ─────────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class BobError(FizzBuzzError):
    """Base exception for all FizzBob operator cognitive load errors.

    The FizzBob subsystem models the cognitive state of the human
    operator monitoring the Enterprise FizzBuzz Platform.  Errors in
    this domain indicate failures in the cognitive modeling pipeline,
    not failures in the operator themselves (although the latter are
    also modeled, through burnout and fatigue scores).
    """

    def __init__(self, message: str, *, error_code: str = "EFP-BOB0", **kwargs: Any) -> None:
        super().__init__(message, error_code=error_code, context=kwargs)


class BobCalibrationError(BobError):
    """Raised when the cognitive model cannot be calibrated.

    Calibration requires valid baseline measurements for all six
    NASA-TLX subscales, a circadian phase reference, and an initial
    burnout assessment.  If any of these are missing or inconsistent,
    the model cannot produce reliable predictions.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(
            f"Calibration failed for parameter '{parameter}': {reason}",
            error_code="EFP-BOB1",
            parameter=parameter,
            reason=reason,
        )
        self.parameter = parameter


class BobCircadianError(BobError):
    """Raised when the two-process circadian model encounters invalid state.

    The Borbely two-process model requires positive time constants and
    valid phase parameters.  This exception indicates that the circadian
    computation cannot proceed with the given inputs.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(
            f"Circadian model error for '{parameter}': {reason}",
            error_code="EFP-BOB2",
            parameter=parameter,
            reason=reason,
        )
        self.parameter = parameter


class BobAlertFatigueError(BobError):
    """Raised when the alert fatigue tracker cannot process an event.

    Alert fatigue computation depends on valid half-life parameters
    and monotonically increasing timestamps.  This exception covers
    configuration errors and temporal inconsistencies.
    """

    def __init__(self, alert_count: int, reason: str) -> None:
        super().__init__(
            f"Alert fatigue error (alerts={alert_count}): {reason}",
            error_code="EFP-BOB3",
            alert_count=alert_count,
            reason=reason,
        )
        self.alert_count = alert_count


class BobBurnoutError(BobError):
    """Raised when a Maslach Burnout Inventory assessment is invalid.

    Each MBI subscale has a defined range: EE (0-54), DP (0-30),
    PA (0-48).  Scores outside these ranges indicate instrument
    malfunction or data entry error, not extraordinary burnout levels.
    """

    def __init__(self, subscale: str, reason: str) -> None:
        super().__init__(
            f"Burnout assessment error for '{subscale}': {reason}",
            error_code="EFP-BOB4",
            subscale=subscale,
            reason=reason,
        )
        self.subscale = subscale


class BobOverloadError(BobError):
    """Raised when the overload mode controller enters an invalid state.

    Overload Mode transitions must follow the defined state machine:
    activation requires threshold crossing, and deactivation requires
    clearing both the TLX and alertness hysteresis bands.
    """

    def __init__(self, current_state: str, reason: str) -> None:
        super().__init__(
            f"Overload controller error (state={current_state}): {reason}",
            error_code="EFP-BOB5",
            current_state=current_state,
            reason=reason,
        )
        self.current_state = current_state


class BobDashboardError(BobError):
    """Raised when the cognitive load dashboard cannot be rendered.

    Dashboard rendering requires a valid orchestrator with at least
    one TLX snapshot and one circadian state computation.  This
    exception covers rendering failures due to missing or corrupt data.
    """

    def __init__(self, panel: str, reason: str) -> None:
        super().__init__(
            f"Dashboard rendering error in panel '{panel}': {reason}",
            error_code="EFP-BOB6",
            panel=panel,
            reason=reason,
        )
        self.panel = panel


class BobMiddlewareError(BobError):
    """Raised when the BobMiddleware fails to process an evaluation.

    The middleware intercepts each evaluation to update the cognitive
    model.  This exception covers failures in the interception and
    metadata injection path.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Middleware error at evaluation {evaluation_number}: {reason}",
            error_code="EFP-BOB7",
            evaluation_number=evaluation_number,
            reason=reason,
        )
        self.evaluation_number = evaluation_number


class BobTLXError(BobError):
    """Raised when a NASA-TLX assessment encounters invalid data.

    TLX subscale scores must be in the range [0, 100].  Paired-comparison
    weights must sum to 15.  Missing subscales prevent a complete
    assessment.  This exception covers all TLX-specific validation failures.
    """

    def __init__(self, subscale: str, reason: str) -> None:
        super().__init__(
            f"TLX error for subscale '{subscale}': {reason}",
            error_code="EFP-BOB8",
            subscale=subscale,
            reason=reason,
        )
        self.subscale = subscale


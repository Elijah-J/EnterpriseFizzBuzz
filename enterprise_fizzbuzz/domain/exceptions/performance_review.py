"""
Enterprise FizzBuzz Platform - ── FizzPerf: Operator Performance Review & 360-Degree Feedback ─────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class PerfError(FizzBuzzError):
    """Base exception for all FizzPerf performance review errors.

    The FizzPerf engine manages the complete performance review lifecycle
    including OKR tracking, 360-degree feedback, calibration, and
    compensation benchmarking.  This base exception is raised when a
    general performance review error occurs that does not fit a more
    specific exception category.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Performance review error: {reason}",
            error_code="EFP-PRF0",
            context={"reason": reason},
        )


class PerfGoalError(PerfError):
    """Raised when OKR goal tracking encounters an error.

    The OKR framework manages objectives and key results for the
    review period.  This exception covers failures in objective
    creation, key result tracking, and completion calculation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF1"


class PerfSelfAssessmentError(PerfError):
    """Raised when the self-assessment module encounters an error.

    The self-assessment generates pre-populated competency ratings
    and narrative reflections.  This exception covers failures in
    rating generation, narrative construction, and assessment
    serialization.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF2"


class PerfFeedbackError(PerfError):
    """Raised when the 360-degree feedback engine encounters an error.

    The feedback engine collects and aggregates multi-rater feedback
    from manager, peer, direct report, and stakeholder perspectives.
    This exception covers failures in feedback collection, aggregation,
    and inter-rater reliability computation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF3"


class PerfCalibrationError(PerfError):
    """Raised when the calibration engine encounters an error.

    The calibration engine manages the committee review process
    including forced distribution evaluation and PIP determination.
    This exception covers failures in calibration execution, vote
    collection, and outcome recording.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF4"


class PerfCompensationError(PerfError):
    """Raised when the compensation benchmarker encounters an error.

    The benchmarker computes role-level market rates, the composite
    market rate, and the McFizzington Equity Index.  This exception
    covers failures in benchmark calculation, alert classification,
    and recommendation generation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF5"


class PerfReviewCycleError(PerfError):
    """Raised when the review cycle orchestrator encounters an error.

    The orchestrator manages the 8-phase state machine driving the
    review cycle.  This exception covers failures in phase transitions,
    cycle completion, and snapshot generation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF6"


class PerfReportError(PerfError):
    """Raised when the performance report generator fails.

    The report generator aggregates data from all performance review
    components into executive-ready reports.  This exception covers
    failures in data aggregation and formatting.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF7"


class PerfDashboardError(PerfError):
    """Raised when the performance dashboard rendering fails.

    The dashboard renders OKR progress, competency radar, calibration
    status, and compensation benchmarks in ASCII format.  This
    exception covers failures in data retrieval and rendering.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-PRF8"


class PerfMiddlewareError(PerfError):
    """Raised when the PerfMiddleware fails to process an evaluation.

    The middleware intercepts each evaluation to inject performance
    review metadata.  This exception covers failures in metadata
    computation and context injection.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Performance middleware error at evaluation {evaluation_number}: {reason}",
        )
        self.error_code = "EFP-PRF9"
        self.evaluation_number = evaluation_number


# ═══════════════════════════════════════════════════════════════════
# FizzOrg: Organizational Hierarchy & Reporting Structure Errors
# ═══════════════════════════════════════════════════════════════════


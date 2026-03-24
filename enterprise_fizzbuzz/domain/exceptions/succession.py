"""
Enterprise FizzBuzz Platform - ── FizzSuccession: Operator Succession Planning ────────────────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SuccessionError(FizzBuzzError):
    """Base exception for all FizzSuccession operator succession planning errors.

    The FizzSuccession framework monitors organizational continuity risk
    by tracking the bus factor, skills coverage, cross-training depth,
    and hiring pipeline status.  This base exception is raised when
    a general succession planning error occurs that does not fit a
    more specific exception category.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Succession planning error: {reason}",
            error_code="EFP-SUC0",
            context={"reason": reason},
        )


class SuccessionBusFactorError(SuccessionError):
    """Raised when bus factor calculation encounters an error.

    The bus factor calculator analyzes operator coverage across
    infrastructure modules.  This exception is raised when the
    calculation cannot be completed, typically due to an empty
    operator roster or invalid module ownership data.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SUC1"


class SuccessionSkillsMatrixError(SuccessionError):
    """Raised when the skills matrix encounters an initialization or query error.

    The skills matrix catalogs all infrastructure modules as operational
    skills and maps each to an operator, proficiency level, and
    dependency score.  This exception covers failures in matrix
    construction, entry lookup, and aggregation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SUC2"


class SuccessionPCRSError(SuccessionError):
    """Raised when the Platform Continuity Readiness Score calculation fails.

    The PCRS is a composite metric quantifying organizational preparedness
    for operator succession.  This exception is raised when the input
    parameters are invalid (e.g., bus factor < 1) or the formula
    produces an out-of-range result.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SUC3"


class SuccessionKnowledgeGapError(SuccessionError):
    """Raised when the knowledge gap analysis encounters an error.

    The gap analysis identifies modules with zero cross-trained
    operators.  This exception covers failures in gap detection,
    criticality weighting, and remediation estimation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SUC4"


class SuccessionHiringPlanError(SuccessionError):
    """Raised when the hiring plan generator encounters an error.

    The hiring plan produces recommendations based on knowledge gaps
    and organizational priorities.  This exception covers failures
    in recommendation generation, budget estimation, and approval
    workflow integration.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SUC5"


class SuccessionKnowledgeTransferError(SuccessionError):
    """Raised when the knowledge transfer tracker encounters an error.

    The transfer tracker manages the scheduling and completion of
    knowledge transfer sessions.  This exception covers failures
    in session creation, status updates, and completion tracking.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SUC6"


class SuccessionReportError(SuccessionError):
    """Raised when the succession report generator fails.

    The report generator aggregates data from all succession planning
    components into a comprehensive readiness report.  This exception
    covers failures in data aggregation, formatting, and serialization.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SUC7"


class SuccessionMiddlewareError(SuccessionError):
    """Raised when the SuccessionMiddleware fails to process an evaluation.

    The middleware intercepts each evaluation to inject succession
    planning metadata.  This exception covers failures in metadata
    computation and context injection.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Succession middleware error at evaluation {evaluation_number}: {reason}",
        )
        self.error_code = "EFP-SUC8"
        self.evaluation_number = evaluation_number


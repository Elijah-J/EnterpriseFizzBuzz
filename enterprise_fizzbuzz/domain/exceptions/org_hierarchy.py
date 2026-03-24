"""
Enterprise FizzBuzz Platform - Org Hierarchy Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class OrgError(FizzBuzzError):
    """Base exception for all FizzOrg organizational hierarchy errors.

    The FizzOrg engine models the organizational structure of the
    Enterprise FizzBuzz Platform, including departments, positions,
    reporting relationships, RACI matrix, headcount planning, and
    governance committees.  This base exception is raised when a
    general organizational error occurs that does not fit a more
    specific exception category.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Organizational hierarchy error: {reason}",
            error_code="EFP-ORG0",
            context={"reason": reason},
        )


class OrgDepartmentError(OrgError):
    """Raised when a department operation encounters an error.

    The department registry manages 10 organizational departments,
    each with a mission statement, headcount target, and department
    head.  This exception covers failures in department registration,
    lookup, and validation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG1"


class OrgPositionError(OrgError):
    """Raised when a position operation encounters an error.

    The position hierarchy manages 14 formal positions organized
    in a 4-level tree, each with a title, department assignment,
    grade level, and incumbent.  This exception covers failures in
    position registration, lookup, and hierarchy traversal.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG2"


class OrgHierarchyError(OrgError):
    """Raised when the organizational hierarchy encounters an error.

    The hierarchy engine maintains the reporting tree structure,
    validates parent-child relationships, and traces reporting
    chains from any position to the root.  This exception covers
    failures in tree construction, traversal, and validation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG3"


class OrgRACIError(OrgError):
    """Raised when the RACI matrix encounters an error.

    The RACI matrix assigns Responsible, Accountable, Consulted,
    and Informed designations across 106 subsystems and 14 roles.
    This exception covers failures in matrix construction, conflict
    detection, and coverage validation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG4"


class OrgHeadcountError(OrgError):
    """Raised when the headcount planner encounters an error.

    The headcount planner tracks staffing levels across departments,
    computes utilization ratios, and generates hiring plans.  This
    exception covers failures in headcount computation, staffing
    analysis, and hiring plan generation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG5"


class OrgCommitteeError(OrgError):
    """Raised when the committee manager encounters an error.

    The committee manager maintains 6 governance committees, each
    with membership rosters, quorum requirements, and meeting
    schedules.  This exception covers failures in committee
    operations, quorum validation, and schedule computation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG6"


class OrgChartError(OrgError):
    """Raised when the org chart renderer encounters an error.

    The org chart renderer produces ASCII tree visualizations of
    the organizational hierarchy, with position titles, incumbents,
    and department annotations.  This exception covers failures in
    tree layout computation and rendering.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG7"


class OrgDashboardError(OrgError):
    """Raised when the organizational dashboard rendering fails.

    The dashboard renders department summaries, headcount metrics,
    RACI coverage, committee status, and organizational statistics
    in ASCII format.  This exception covers failures in data
    retrieval and rendering.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-ORG8"


class OrgMiddlewareError(OrgError):
    """Raised when the OrgMiddleware fails to process an evaluation.

    The middleware intercepts each evaluation to inject organizational
    hierarchy metadata into the processing context.  This exception
    covers failures in metadata computation and context injection.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Org middleware error at evaluation {evaluation_number}: {reason}",
        )
        self.error_code = "EFP-ORG9"
        self.evaluation_number = evaluation_number


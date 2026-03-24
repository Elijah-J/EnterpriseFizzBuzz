"""
Enterprise FizzBuzz Platform - Typesetting Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class TypesettingError(FizzBuzzError):
    """Raised when the FizzPrint typesetting engine encounters a failure.

    Publication-quality FizzBuzz reports demand flawless typographic
    output. Any failure in the line breaking, pagination, or rendering
    pipeline indicates a fundamental breakdown in the platform's ability
    to present divisibility results with the visual precision that
    enterprise stakeholders expect.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-TS00",
            context={"subsystem": "typesetter"},
        )


class LineBreakingError(TypesettingError):
    """Raised when the Knuth-Plass algorithm fails to find feasible breakpoints.

    If the optimizer cannot identify any sequence of breakpoints with
    finite demerits, the paragraph is considered untypesettable at the
    current line width. This typically indicates that a word exceeds
    the available column width, or that penalty constraints are
    overconstrained.
    """

    def __init__(self, paragraph_text: str, line_width: float) -> None:
        super().__init__(
            f"No feasible breakpoint sequence for paragraph at line width "
            f"{line_width:.1f}pt: {paragraph_text[:80]!r}..."
        )
        self.error_code = "EFP-TS01"


class PaginationError(TypesettingError):
    """Raised when the page layout engine fails to distribute lines across pages.

    Widow/orphan constraints may conflict with available page capacity,
    creating an unsolvable pagination problem. In extreme cases, a
    single paragraph may exceed the total capacity of a page, which
    suggests that the FizzBuzz range was set unreasonably large or that
    page margins were configured by someone who has never seen paper.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-TS02"


class PostScriptRenderError(TypesettingError):
    """Raised when PostScript generation fails.

    PostScript is a Turing-complete page description language, so in
    theory any rendering problem is solvable. In practice, malformed
    string literals, invalid font references, or coordinate overflow
    can produce output that no RIP can interpret.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-TS03"


"""
Enterprise FizzBuzz Platform - Intellectual Property Office Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class IPOfficeError(FizzBuzzError):
    """Base exception for all Intellectual Property Office errors.

    The FizzBuzz IP Office maintains a comprehensive registry of
    trademarks, patents, and copyrights covering every conceivable
    aspect of divisibility-based string substitution. When you
    attempt to use the label "Fizz" without proper trademark
    clearance, or implement a modulo-3 rule without licensing the
    patent, this exception hierarchy is what stands between you
    and IP anarchy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-IP00"),
            context=kwargs.get("context", {}),
        )


class TrademarkViolationError(IPOfficeError):
    """Raised when a label infringes on a registered FizzBuzz trademark.

    The FizzBuzz Trademark Registry contains marks that have been
    registered through a rigorous application process involving
    phonetic similarity analysis (Soundex + Metaphone), visual
    inspection, and a mandatory 30-day opposition period during
    which no one objects because this is a FizzBuzz program.
    Attempting to use a confusingly similar label — say, "Fhyzz"
    when "Fizz" is already registered — triggers this exception
    and a sternly worded cease-and-desist from the Tribunal.
    """

    def __init__(self, mark: str, conflicting_mark: str, similarity: float) -> None:
        super().__init__(
            f"Trademark violation: '{mark}' is confusingly similar to "
            f"registered mark '{conflicting_mark}' (similarity: {similarity:.2%}). "
            f"Cease and desist immediately.",
            error_code="EFP-IP01",
            context={"mark": mark, "conflicting_mark": conflicting_mark, "similarity": similarity},
        )
        self.mark = mark
        self.conflicting_mark = conflicting_mark
        self.similarity = similarity


class PatentInfringementError(IPOfficeError):
    """Raised when a rule infringes on a granted FizzBuzz patent.

    The FizzBuzz Patent Office examines each rule for novelty (is it
    truly new?), non-obviousness (would a person having ordinary
    skill in the art of modulo arithmetic find it obvious?), and
    utility (does it actually produce output for at least one
    integer?). If your rule fails any of these tests, it is either
    rejected or, worse, found to infringe on an existing patent.
    The prior art database is extensive: {3: "Fizz"} was patented
    in the Before Times.
    """

    def __init__(self, rule_description: str, patent_id: str, reason: str) -> None:
        super().__init__(
            f"Patent infringement: rule '{rule_description}' infringes on "
            f"patent {patent_id}: {reason}. "
            f"The patent holder's attorneys have been notified.",
            error_code="EFP-IP02",
            context={"rule_description": rule_description, "patent_id": patent_id, "reason": reason},
        )
        self.rule_description = rule_description
        self.patent_id = patent_id
        self.reason = reason


class CopyrightInfringementError(IPOfficeError):
    """Raised when a work infringes on a registered FizzBuzz copyright.

    Every FizzBuzz output sequence is a copyrightable work of
    applied mathematics. The Copyright Registry maintains records
    of all registered works, their originality scores (computed via
    Levenshtein distance from existing works), and their licensing
    terms. Copying someone else's "1, 2, Fizz, 4, Buzz" sequence
    without attribution is not just bad form — it's a violation of
    the FizzBuzz Intellectual Property Act of 2026.
    """

    def __init__(self, work_title: str, original_work_id: str, similarity: float) -> None:
        super().__init__(
            f"Copyright infringement: work '{work_title}' is {similarity:.0%} similar to "
            f"registered work {original_work_id}. "
            f"The DMCA takedown notice is being prepared.",
            error_code="EFP-IP03",
            context={"work_title": work_title, "original_work_id": original_work_id, "similarity": similarity},
        )
        self.work_title = work_title
        self.original_work_id = original_work_id
        self.similarity = similarity


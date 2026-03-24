"""
Enterprise FizzBuzz Platform - Archaeological Recovery System Exceptions (EFP-AR00 .. EFP-AR03)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ArchaeologyError(FizzBuzzError):
    """Base exception for all Archaeological Recovery System errors.

    When the enterprise-grade digital forensics subsystem that painstakingly
    excavates FizzBuzz evaluation evidence from seven stratigraphic layers
    encounters a failure, it raises one of these. The irony that recovering
    data which could be recomputed in a single CPU cycle requires its own
    exception hierarchy is not lost on the architects — it is, in fact,
    the entire point.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-AR00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class StratumCorruptionError(ArchaeologyError):
    """Raised when evidence recovered from a stratigraphic layer is too degraded.

    The corruption simulator has determined that the evidence fragment has
    suffered catastrophic data degradation — bit rot, cosmic ray flips, or
    the slow thermodynamic march toward entropy that afflicts all information
    systems. The fragment's confidence has fallen below the recoverable
    threshold, rendering the evidence forensically inadmissible. This is
    the archaeological equivalent of finding a cuneiform tablet that has
    been through a blender.
    """

    def __init__(self, stratum: str, number: int, confidence: float) -> None:
        super().__init__(
            f"Evidence from stratum '{stratum}' for number {number} is "
            f"catastrophically corrupted (confidence: {confidence:.4f}). "
            f"The fragment has suffered irreversible data degradation. "
            f"Consider excavating adjacent strata for corroborating evidence.",
            error_code="EFP-AR01",
            context={
                "stratum": stratum,
                "number": number,
                "confidence": confidence,
            },
        )
        self.stratum = stratum
        self.number = number
        self.confidence = confidence


class InsufficientEvidenceError(ArchaeologyError):
    """Raised when too few strata yield usable evidence for Bayesian reconstruction.

    The excavation has returned fewer evidence fragments than the minimum
    required for statistically meaningful Bayesian inference. Without
    sufficient cross-layer corroboration, the posterior distribution is
    dominated by the prior, rendering the reconstruction no better than
    simply computing n % 3 and n % 5 directly, which would bypass the
    archaeological recovery pipeline entirely.
    """

    def __init__(self, number: int, fragments_found: int, minimum_required: int) -> None:
        super().__init__(
            f"Insufficient evidence for number {number}: only {fragments_found} "
            f"fragments recovered (minimum {minimum_required} required). "
            f"The Bayesian reconstructor cannot produce a credible posterior "
            f"distribution from this meager corpus. The archaeological record "
            f"is, frankly, embarrassing.",
            error_code="EFP-AR02",
            context={
                "number": number,
                "fragments_found": fragments_found,
                "minimum_required": minimum_required,
            },
        )
        self.number = number
        self.fragments_found = fragments_found
        self.minimum_required = minimum_required


class StratigraphicConflictError(ArchaeologyError):
    """Raised when evidence from different strata produces contradictory classifications.

    Two or more stratigraphic layers have yielded evidence that disagrees
    on the fundamental nature of a number. One stratum insists the number
    is Fizz; another is equally certain it is Buzz. This temporal paradox
    suggests either data corruption or conflicting classification
    metadata across temporal layers that must be resolved through
    manual reconciliation.
    """

    def __init__(
        self, number: int, stratum_a: str, class_a: str, stratum_b: str, class_b: str
    ) -> None:
        super().__init__(
            f"Stratigraphic conflict for number {number}: stratum '{stratum_a}' "
            f"yields '{class_a}' but stratum '{stratum_b}' yields '{class_b}'. "
            f"Cross-layer evidence is irreconcilable. A temporal paradox in "
            f"the FizzBuzz archaeological record has been detected.",
            error_code="EFP-AR03",
            context={
                "number": number,
                "stratum_a": stratum_a,
                "classification_a": class_a,
                "stratum_b": stratum_b,
                "classification_b": class_b,
            },
        )
        self.number = number
        self.stratum_a = stratum_a
        self.classification_a = class_a
        self.stratum_b = stratum_b
        self.classification_b = class_b


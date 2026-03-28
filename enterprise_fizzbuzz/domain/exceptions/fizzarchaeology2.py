"""
Enterprise FizzBuzz Platform - FizzArchaeology2 Exceptions (EFP-AR200 through EFP-AR209)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzArchaeology2Error(FizzBuzzError):
    """Base exception for the FizzArchaeology2 digital archaeology v2 subsystem.

    The second-generation digital archaeology engine extends the original
    recovery system with carbon-14 dating simulation, stratigraphic layer
    analysis, and excavation grid management. These capabilities enable
    temporal ordering of recovered FizzBuzz artifacts with radiometric
    precision, providing a scientifically rigorous provenance chain for
    every evaluation result extracted from degraded storage media.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-AR200",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class CarbonDatingError(FizzArchaeology2Error):
    """Raised when carbon-14 dating yields a non-physical age estimate.

    The radioactive decay of carbon-14 follows first-order kinetics with
    a half-life of 5,730 years. An age estimate outside the valid range
    (0 to ~50,000 years) indicates either sample contamination or a
    measurement error in the isotope ratio detector. Digital artifacts
    older than the platform's deployment date are chronologically
    impossible and must be flagged for manual review.
    """

    def __init__(self, estimated_age: float, reason: str) -> None:
        super().__init__(
            f"Carbon-14 dating error: estimated age {estimated_age:.1f} years "
            f"is non-physical: {reason}",
            error_code="EFP-AR201",
            context={"estimated_age": estimated_age, "reason": reason},
        )


class StratigraphicError(FizzArchaeology2Error):
    """Raised when stratigraphic layer analysis detects an inversion.

    The law of superposition requires that deeper layers are older than
    shallower layers in undisturbed deposits. A stratigraphic inversion
    indicates either bioturbation, post-depositional disturbance, or
    a data corruption event that reordered the storage media sectors.
    """

    def __init__(self, layer_above: str, layer_below: str, reason: str) -> None:
        super().__init__(
            f"Stratigraphic inversion between layer '{layer_above}' and "
            f"'{layer_below}': {reason}",
            error_code="EFP-AR202",
            context={
                "layer_above": layer_above,
                "layer_below": layer_below,
                "reason": reason,
            },
        )


class ArtifactClassificationError(FizzArchaeology2Error):
    """Raised when an excavated artifact cannot be classified.

    Each artifact recovered from the digital stratigraphic record must
    be assignable to a known typological category. Unclassifiable artifacts
    may represent previously unknown FizzBuzz evaluation patterns or
    corrupted data that does not conform to any recognized schema.
    """

    def __init__(self, artifact_id: str, reason: str) -> None:
        super().__init__(
            f"Cannot classify artifact '{artifact_id}': {reason}",
            error_code="EFP-AR203",
            context={"artifact_id": artifact_id, "reason": reason},
        )


class ExcavationGridError(FizzArchaeology2Error):
    """Raised when the excavation grid configuration is invalid.

    The excavation grid partitions the data recovery space into discrete
    sectors for systematic sampling. Grid dimensions must be positive
    integers and the total sector count must not exceed available memory.
    """

    def __init__(self, rows: int, cols: int, reason: str) -> None:
        super().__init__(
            f"Excavation grid {rows}x{cols} is invalid: {reason}",
            error_code="EFP-AR204",
            context={"rows": rows, "cols": cols, "reason": reason},
        )


class ProvenanceError(FizzArchaeology2Error):
    """Raised when provenance chain validation fails.

    Every recovered artifact must have a complete provenance chain from
    excavation through classification to final archival. A broken chain
    renders the artifact inadmissible as evidence of historical FizzBuzz
    evaluation activity.
    """

    def __init__(self, artifact_id: str, missing_step: str) -> None:
        super().__init__(
            f"Provenance chain broken for artifact '{artifact_id}': "
            f"missing step '{missing_step}'",
            error_code="EFP-AR205",
            context={"artifact_id": artifact_id, "missing_step": missing_step},
        )


class Archaeology2MiddlewareError(FizzArchaeology2Error):
    """Raised when the FizzArchaeology2 middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzArchaeology2 middleware error: {reason}",
            error_code="EFP-AR206",
            context={"reason": reason},
        )

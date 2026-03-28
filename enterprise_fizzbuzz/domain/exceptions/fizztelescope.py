"""
Enterprise FizzBuzz Platform - FizzTelescope Exceptions (EFP-TEL00 through EFP-TEL09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzTelescopeError(FizzBuzzError):
    """Base exception for all FizzTelescope control system errors.

    The FizzTelescope engine provides computerized telescope control for
    observing the celestial coordinates associated with each FizzBuzz
    evaluation. Mount tracking, field rotation compensation, autoguiding,
    and plate solving are all essential for maintaining pointing accuracy
    during extended evaluation sessions.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-TEL00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class MountTrackingError(FizzTelescopeError):
    """Raised when the telescope mount fails to maintain sidereal tracking.

    Sidereal tracking requires a rotation rate of 15.041 arcseconds per
    second to compensate for Earth's rotation. Tracking errors exceeding
    the acceptable threshold degrade image quality and compromise the
    positional accuracy of FizzBuzz celestial associations.
    """

    def __init__(self, tracking_error_arcsec: float, max_allowed: float) -> None:
        super().__init__(
            f"Mount tracking error {tracking_error_arcsec:.3f} arcsec exceeds "
            f"tolerance of {max_allowed:.3f} arcsec",
            error_code="EFP-TEL01",
            context={
                "tracking_error_arcsec": tracking_error_arcsec,
                "max_allowed": max_allowed,
            },
        )


class FieldRotationError(FizzTelescopeError):
    """Raised when field rotation compensation fails.

    Alt-azimuth mounts experience field rotation as they track objects
    across the sky. The rotation rate depends on the object's hour
    angle and declination. Failure to compensate produces trailed
    star images at the field edges.
    """

    def __init__(self, rotation_rate_deg_hr: float, reason: str) -> None:
        super().__init__(
            f"Field rotation error at {rotation_rate_deg_hr:.4f} deg/hr: {reason}",
            error_code="EFP-TEL02",
            context={"rotation_rate_deg_hr": rotation_rate_deg_hr, "reason": reason},
        )


class AutoguidingError(FizzTelescopeError):
    """Raised when the autoguiding system loses lock on the guide star.

    Autoguiding requires a guide star of sufficient brightness within
    the guide camera field of view. Loss of guide star lock results
    in uncorrected tracking errors that accumulate over time.
    """

    def __init__(self, guide_star_magnitude: float, reason: str) -> None:
        super().__init__(
            f"Autoguiding failure (guide star mag {guide_star_magnitude:.1f}): {reason}",
            error_code="EFP-TEL03",
            context={"guide_star_magnitude": guide_star_magnitude, "reason": reason},
        )


class PlateSolveError(FizzTelescopeError):
    """Raised when astrometric plate solving fails to determine pointing.

    Plate solving matches detected star patterns against a reference
    catalog to determine the precise sky coordinates of the telescope's
    field of view. Insufficient detected stars or excessive field
    distortion can prevent a solution.
    """

    def __init__(self, detected_stars: int, min_required: int) -> None:
        super().__init__(
            f"Plate solve failed: detected {detected_stars} stars, "
            f"minimum {min_required} required for solution",
            error_code="EFP-TEL04",
            context={"detected_stars": detected_stars, "min_required": min_required},
        )


class CatalogLookupError(FizzTelescopeError):
    """Raised when a celestial object catalog lookup fails.

    The telescope control system maintains catalogs of stars, deep-sky
    objects, and solar system bodies. A lookup failure indicates that
    the requested designation does not match any known catalog entry.
    """

    def __init__(self, designation: str, catalog: str) -> None:
        super().__init__(
            f"Object '{designation}' not found in catalog '{catalog}'",
            error_code="EFP-TEL05",
            context={"designation": designation, "catalog": catalog},
        )


class CoordinateError(FizzTelescopeError):
    """Raised when celestial coordinates are out of range.

    Right ascension must be in [0, 24) hours and declination in
    [-90, +90] degrees. Coordinates outside these ranges do not
    correspond to valid positions on the celestial sphere.
    """

    def __init__(self, ra_hours: float, dec_degrees: float) -> None:
        super().__init__(
            f"Invalid celestial coordinates: RA={ra_hours:.4f}h, Dec={dec_degrees:.4f}deg",
            error_code="EFP-TEL06",
            context={"ra_hours": ra_hours, "dec_degrees": dec_degrees},
        )


class TelescopeMiddlewareError(FizzTelescopeError):
    """Raised when the FizzTelescope middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzTelescope middleware error: {reason}",
            error_code="EFP-TEL07",
            context={"reason": reason},
        )

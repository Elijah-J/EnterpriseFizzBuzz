"""
Enterprise FizzBuzz Platform - FizzOptics Exceptions (EFP-OP00 through EFP-OP07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzOpticsError(FizzBuzzError):
    """Base exception for the FizzOptics optical system designer subsystem.

    Optical system design for FizzBuzz evaluation requires ray tracing
    through multi-element lens systems, computing modulation transfer
    functions, and analyzing aberration coefficients. Each calculation
    depends on precise refractive index data and surface geometry
    that may be incorrectly specified.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-OP00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SnellLawError(FizzOpticsError):
    """Raised when Snell's law computation encounters total internal reflection.

    When the angle of incidence exceeds the critical angle at an
    interface between a denser and rarer medium, total internal
    reflection occurs. The refracted ray does not exist, and the
    optical path through subsequent elements is undefined.
    """

    def __init__(self, n1: float, n2: float, angle_deg: float) -> None:
        super().__init__(
            f"Total internal reflection at interface (n1={n1:.4f}, n2={n2:.4f}, "
            f"angle={angle_deg:.2f} deg)",
            error_code="EFP-OP01",
            context={"n1": n1, "n2": n2, "angle_deg": angle_deg},
        )
        self.n1 = n1
        self.n2 = n2
        self.angle_deg = angle_deg


class ThinLensError(FizzOpticsError):
    """Raised when the thin lens equation produces non-physical results.

    The thin lens equation 1/f = 1/do + 1/di requires that the object
    distance is not equal to the focal length (which would place the
    image at infinity). Virtual images require careful sign-convention
    handling.
    """

    def __init__(self, focal_length: float, object_distance: float) -> None:
        super().__init__(
            f"Thin lens equation failure: f={focal_length:.4f}, "
            f"do={object_distance:.4f}",
            error_code="EFP-OP02",
            context={
                "focal_length": focal_length,
                "object_distance": object_distance,
            },
        )
        self.focal_length = focal_length
        self.object_distance = object_distance


class AberrationError(FizzOpticsError):
    """Raised when aberration coefficients exceed acceptable limits.

    Seidel aberrations (spherical, coma, astigmatism, field curvature,
    distortion) must remain within the design tolerance for the optical
    system to achieve its specified resolution. Excessive aberration
    indicates a fundamentally flawed lens prescription.
    """

    def __init__(self, aberration_type: str, coefficient: float, limit: float) -> None:
        super().__init__(
            f"Aberration '{aberration_type}' coefficient {coefficient:.6f} "
            f"exceeds limit {limit:.6f}",
            error_code="EFP-OP03",
            context={
                "aberration_type": aberration_type,
                "coefficient": coefficient,
                "limit": limit,
            },
        )
        self.aberration_type = aberration_type
        self.coefficient = coefficient


class MTFError(FizzOpticsError):
    """Raised when MTF computation yields invalid values.

    The modulation transfer function must be monotonically decreasing
    from 1.0 at zero spatial frequency to 0.0 at the cutoff frequency.
    Values outside [0, 1] or non-monotonic behavior indicate a
    computation error in the optical transfer function pipeline.
    """

    def __init__(self, frequency: float, mtf_value: float) -> None:
        super().__init__(
            f"Invalid MTF value {mtf_value:.4f} at frequency {frequency:.2f} lp/mm",
            error_code="EFP-OP04",
            context={"frequency": frequency, "mtf_value": mtf_value},
        )
        self.frequency = frequency
        self.mtf_value = mtf_value


class OpticalPathError(FizzOpticsError):
    """Raised when optical path difference computation fails.

    Optical path differences must be computed along well-defined rays.
    If a ray is vignetted (blocked by an aperture) or undergoes total
    internal reflection, the OPD is undefined.
    """

    def __init__(self, surface_index: int, reason: str) -> None:
        super().__init__(
            f"Optical path difference error at surface {surface_index}: {reason}",
            error_code="EFP-OP05",
            context={"surface_index": surface_index, "reason": reason},
        )
        self.surface_index = surface_index


class RayTraceError(FizzOpticsError):
    """Raised when ray tracing through the optical system fails.

    A ray may fail to intersect a surface (miss), or the iterative
    surface intersection algorithm may fail to converge for aspheric
    surfaces with high-order polynomial terms.
    """

    def __init__(self, ray_id: int, surface_index: int, reason: str) -> None:
        super().__init__(
            f"Ray {ray_id} failed at surface {surface_index}: {reason}",
            error_code="EFP-OP06",
            context={
                "ray_id": ray_id,
                "surface_index": surface_index,
                "reason": reason,
            },
        )
        self.ray_id = ray_id
        self.surface_index = surface_index


class OpticsMiddlewareError(FizzOpticsError):
    """Raised when the FizzOptics middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzOptics middleware error: {reason}",
            error_code="EFP-OP07",
            context={"reason": reason},
        )

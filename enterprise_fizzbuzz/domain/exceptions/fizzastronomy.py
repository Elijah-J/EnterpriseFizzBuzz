"""
Enterprise FizzBuzz Platform - FizzAstronomy Exceptions (EFP-AST00 through EFP-AST09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzAstronomyError(FizzBuzzError):
    """Base exception for all FizzAstronomy celestial mechanics errors.

    The FizzAstronomy engine computes orbital mechanics, n-body simulations,
    and ephemeris data to determine the gravitational context in which a
    FizzBuzz evaluation occurs. Celestial position directly influences the
    tidal classification weight applied to divisibility checks.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-AST00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidOrbitalElementsError(FizzAstronomyError):
    """Raised when Keplerian orbital elements are physically impossible.

    A valid Keplerian orbit requires eccentricity in [0, 1) for bound
    orbits, positive semi-major axis, and inclination in [0, pi]. Violating
    these constraints would produce a trajectory that does not close,
    rendering periodic FizzBuzz evaluations along the orbit undefined.
    """

    def __init__(self, element_name: str, value: float, reason: str) -> None:
        super().__init__(
            f"Invalid orbital element '{element_name}' = {value}: {reason}",
            error_code="EFP-AST01",
            context={"element_name": element_name, "value": value, "reason": reason},
        )


class EphemerisComputationError(FizzAstronomyError):
    """Raised when an ephemeris calculation fails to converge.

    Ephemeris computation relies on iterative solution of Kepler's
    equation via Newton-Raphson. If the iteration does not converge
    within the allowed number of steps, the position of the celestial
    body remains indeterminate and cannot be used for gravitational
    weighting of FizzBuzz results.
    """

    def __init__(self, body_name: str, epoch: float, iterations: int) -> None:
        super().__init__(
            f"Ephemeris computation for '{body_name}' at epoch {epoch:.6f} "
            f"failed to converge after {iterations} iterations",
            error_code="EFP-AST02",
            context={"body_name": body_name, "epoch": epoch, "iterations": iterations},
        )


class NBodyIntegrationError(FizzAstronomyError):
    """Raised when the n-body integrator encounters a numerical instability.

    The Verlet integrator used for n-body simulation requires that
    inter-body distances remain above a softening threshold. When two
    bodies approach too closely, the gravitational force diverges and
    the integration becomes numerically unstable, potentially ejecting
    bodies at superluminal velocities.
    """

    def __init__(self, body_a: str, body_b: str, distance: float) -> None:
        super().__init__(
            f"N-body integration instability: bodies '{body_a}' and '{body_b}' "
            f"approached within {distance:.6e} AU, below the softening threshold",
            error_code="EFP-AST03",
            context={"body_a": body_a, "body_b": body_b, "distance": distance},
        )


class CoordinateTransformError(FizzAstronomyError):
    """Raised when a coordinate system transformation fails.

    Transformations between ecliptic, equatorial, and galactic reference
    frames require valid obliquity angles and proper rotation matrices.
    A failed transform means the FizzBuzz evaluation cannot be
    localized to the correct celestial reference frame.
    """

    def __init__(self, source_frame: str, target_frame: str, reason: str) -> None:
        super().__init__(
            f"Coordinate transform from '{source_frame}' to '{target_frame}' "
            f"failed: {reason}",
            error_code="EFP-AST04",
            context={"source_frame": source_frame, "target_frame": target_frame},
        )


class KeplerEquationError(FizzAstronomyError):
    """Raised when Kepler's equation solver encounters a degenerate case.

    For high eccentricities near 1.0, the Newton-Raphson solver for
    Kepler's equation M = E - e*sin(E) can oscillate or converge
    extremely slowly. This prevents determination of the true anomaly,
    which is required to place the FizzBuzz evaluator at the correct
    orbital position.
    """

    def __init__(self, mean_anomaly: float, eccentricity: float) -> None:
        super().__init__(
            f"Kepler's equation solver failed for M={mean_anomaly:.6f}, "
            f"e={eccentricity:.8f}. The eccentric anomaly is indeterminate.",
            error_code="EFP-AST05",
            context={"mean_anomaly": mean_anomaly, "eccentricity": eccentricity},
        )


class CelestialBodyNotFoundError(FizzAstronomyError):
    """Raised when a referenced celestial body is not in the catalog.

    The FizzAstronomy engine maintains an ephemeris catalog of known
    bodies. Referencing an unregistered body prevents gravitational
    force computation and orbital propagation.
    """

    def __init__(self, body_name: str) -> None:
        super().__init__(
            f"Celestial body '{body_name}' not found in the ephemeris catalog",
            error_code="EFP-AST06",
            context={"body_name": body_name},
        )


class AstronomyMiddlewareError(FizzAstronomyError):
    """Raised when the FizzAstronomy middleware pipeline encounters a fault.

    The middleware layer applies celestial mechanics data to the
    FizzBuzz processing context. A middleware fault means gravitational
    context cannot be injected into the evaluation pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzAstronomy middleware error: {reason}",
            error_code="EFP-AST07",
            context={"reason": reason},
        )

"""
Enterprise FizzBuzz Platform - FizzTribology Exceptions (EFP-TRB00 through EFP-TRB09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzTribologyError(FizzBuzzError):
    """Base exception for all FizzTribology friction and wear errors.

    The FizzTribology engine models contact mechanics, friction, and wear
    processes that occur at the interface between FizzBuzz evaluations and
    the computational substrate. Coulomb friction coefficients, Hertzian
    contact pressures, and lubrication film thickness all affect the
    efficiency of number-to-classification mapping.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-TRB00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class CoulombFrictionError(FizzTribologyError):
    """Raised when Coulomb friction parameters are non-physical.

    The coefficient of kinetic friction must be positive and typically
    less than the coefficient of static friction. Negative friction
    would imply that surfaces accelerate each other upon contact,
    violating the second law of thermodynamics.
    """

    def __init__(self, mu_static: float, mu_kinetic: float) -> None:
        super().__init__(
            f"Invalid Coulomb friction: mu_s={mu_static:.4f}, mu_k={mu_kinetic:.4f} — "
            f"coefficients must be positive with mu_k <= mu_s",
            error_code="EFP-TRB01",
            context={"mu_static": mu_static, "mu_kinetic": mu_kinetic},
        )


class HertzianContactError(FizzTribologyError):
    """Raised when Hertzian contact mechanics computation fails.

    Hertzian contact theory requires positive elastic moduli, positive
    Poisson ratios less than 0.5 (for stable materials), and positive
    contact radii. A negative reduced elastic modulus would imply that
    the material expands under compressive load.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Hertzian contact computation error: {reason}",
            error_code="EFP-TRB02",
            context={"reason": reason},
        )


class WearModelError(FizzTribologyError):
    """Raised when the Archard wear model produces invalid results.

    The Archard wear equation V = K * F * s / H requires positive
    hardness H, non-negative normal force F, and a wear coefficient K
    in the range [0, 1]. Negative wear volume would correspond to
    spontaneous material deposition, which is not a wear mechanism.
    """

    def __init__(self, wear_volume: float, reason: str) -> None:
        super().__init__(
            f"Archard wear model error: volume={wear_volume:.6e} — {reason}",
            error_code="EFP-TRB03",
            context={"wear_volume": wear_volume, "reason": reason},
        )


class LubricationRegimeError(FizzTribologyError):
    """Raised when the lubrication regime cannot be determined.

    The Stribeck curve maps the dimensionless Hersey number
    (eta * N / P) to the friction coefficient across three regimes:
    boundary, mixed, and hydrodynamic. Invalid viscosity, speed,
    or pressure prevents regime classification.
    """

    def __init__(self, hersey_number: float, reason: str) -> None:
        super().__init__(
            f"Lubrication regime error at Hersey number {hersey_number:.6e}: {reason}",
            error_code="EFP-TRB04",
            context={"hersey_number": hersey_number, "reason": reason},
        )


class SurfaceRoughnessError(FizzTribologyError):
    """Raised when surface roughness parameters are non-physical.

    Surface roughness (Ra, Rq) must be non-negative. The ratio of
    real contact area to apparent contact area must be in (0, 1].
    A negative roughness average has no physical meaning in surface
    metrology.
    """

    def __init__(self, ra_um: float, reason: str) -> None:
        super().__init__(
            f"Surface roughness error: Ra={ra_um:.4f} um — {reason}",
            error_code="EFP-TRB05",
            context={"ra_um": ra_um, "reason": reason},
        )


class TribologyMiddlewareError(FizzTribologyError):
    """Raised when the FizzTribology middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzTribology middleware error: {reason}",
            error_code="EFP-TRB06",
            context={"reason": reason},
        )

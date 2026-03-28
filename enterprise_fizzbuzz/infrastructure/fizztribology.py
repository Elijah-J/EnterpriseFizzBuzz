"""
Enterprise FizzBuzz Platform - FizzTribology Friction and Wear Engine

Models tribological phenomena at the interface between FizzBuzz evaluations
and the computational substrate. Contact mechanics, friction, lubrication,
and wear processes govern the efficiency and longevity of number-to-
classification mapping operations.

Coulomb friction: F_f = mu * F_N
Hertzian contact: a = (3*F*R / (4*E*)) ^ (1/3), p_max = (6*F*E*^2 / (pi^3*R^2))^(1/3)
Archard wear: V = K * F_N * s / H
Stribeck curve: mu = f(eta * N / P) mapping Hersey number to friction regimes

The reduced elastic modulus E* combines the two contacting bodies:
    1/E* = (1-v1^2)/E1 + (1-v2^2)/E2

The Stribeck curve identifies three lubrication regimes:
- Boundary: asperity contact dominates (low speed, high load)
- Mixed: partial hydrodynamic film support
- Hydrodynamic: full film separation (high speed, low load)

All tribology is implemented in pure Python using only the standard
library (math). No external tribology libraries are required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizztribology import (
    CoulombFrictionError,
    HertzianContactError,
    LubricationRegimeError,
    SurfaceRoughnessError,
    TribologyMiddlewareError,
    WearModelError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enums
# ============================================================


class LubricationRegime(Enum):
    """Lubrication regimes on the Stribeck curve."""

    BOUNDARY = auto()
    MIXED = auto()
    HYDRODYNAMIC = auto()


class WearMechanism(Enum):
    """Classification of wear mechanisms."""

    ADHESIVE = auto()
    ABRASIVE = auto()
    FATIGUE = auto()
    CORROSIVE = auto()


# ============================================================
# Surface Properties
# ============================================================


@dataclass
class SurfaceProperties:
    """Mechanical and topographical properties of a contacting surface."""

    elastic_modulus_gpa: float = 200.0  # Steel: ~200 GPa
    poisson_ratio: float = 0.30
    hardness_gpa: float = 2.0           # Vickers hardness
    roughness_ra_um: float = 0.8        # Arithmetic mean roughness (um)
    roughness_rq_um: float = 1.0        # Root mean square roughness (um)

    def validate(self) -> None:
        """Validate surface properties."""
        if self.elastic_modulus_gpa <= 0:
            raise HertzianContactError(
                f"Elastic modulus must be positive: {self.elastic_modulus_gpa} GPa"
            )
        if self.poisson_ratio < 0 or self.poisson_ratio >= 0.5:
            raise HertzianContactError(
                f"Poisson ratio must be in [0, 0.5): {self.poisson_ratio}"
            )
        if self.hardness_gpa <= 0:
            raise HertzianContactError(
                f"Hardness must be positive: {self.hardness_gpa} GPa"
            )
        if self.roughness_ra_um < 0:
            raise SurfaceRoughnessError(
                self.roughness_ra_um, "Roughness Ra must be non-negative"
            )


# ============================================================
# Coulomb Friction
# ============================================================


class CoulombFriction:
    """Implements the Coulomb friction model.

    The friction force F_f = mu * F_N where mu is the coefficient
    of friction (static or kinetic) and F_N is the normal force.
    The kinetic coefficient must not exceed the static coefficient.
    """

    def __init__(self, mu_static: float, mu_kinetic: float) -> None:
        if mu_static <= 0 or mu_kinetic <= 0:
            raise CoulombFrictionError(mu_static, mu_kinetic)
        if mu_kinetic > mu_static:
            raise CoulombFrictionError(mu_static, mu_kinetic)
        self._mu_s = mu_static
        self._mu_k = mu_kinetic

    @property
    def mu_static(self) -> float:
        return self._mu_s

    @property
    def mu_kinetic(self) -> float:
        return self._mu_k

    def static_friction_force(self, normal_force_n: float) -> float:
        """Maximum static friction force in Newtons."""
        return self._mu_s * abs(normal_force_n)

    def kinetic_friction_force(self, normal_force_n: float) -> float:
        """Kinetic friction force in Newtons."""
        return self._mu_k * abs(normal_force_n)

    def is_sliding(self, applied_force_n: float, normal_force_n: float) -> bool:
        """Determine if sliding occurs under the applied tangential force."""
        return abs(applied_force_n) > self.static_friction_force(normal_force_n)


# ============================================================
# Hertzian Contact Mechanics
# ============================================================


class HertzianContact:
    """Computes Hertzian contact parameters for sphere-on-flat geometry.

    The reduced radius R and reduced elastic modulus E* combine the
    properties of both bodies to yield contact radius, maximum pressure,
    and contact area.
    """

    @staticmethod
    def reduced_modulus(
        e1_gpa: float, v1: float, e2_gpa: float, v2: float
    ) -> float:
        """Compute the reduced elastic modulus E* in GPa."""
        if e1_gpa <= 0 or e2_gpa <= 0:
            raise HertzianContactError("Elastic moduli must be positive")
        inv = (1.0 - v1 * v1) / e1_gpa + (1.0 - v2 * v2) / e2_gpa
        if inv <= 0:
            raise HertzianContactError("Reduced modulus computation yielded non-positive value")
        return 1.0 / inv

    @staticmethod
    def contact_radius(
        force_n: float, radius_m: float, e_star_pa: float
    ) -> float:
        """Compute the Hertzian contact radius a in meters.

        a = (3 * F * R / (4 * E*))^(1/3)
        """
        if force_n < 0 or radius_m <= 0 or e_star_pa <= 0:
            raise HertzianContactError(
                f"Invalid inputs: F={force_n} N, R={radius_m} m, E*={e_star_pa} Pa"
            )
        return (3.0 * force_n * radius_m / (4.0 * e_star_pa)) ** (1.0 / 3.0)

    @staticmethod
    def max_contact_pressure(
        force_n: float, contact_radius_m: float
    ) -> float:
        """Compute maximum Hertzian contact pressure p0 in Pa.

        p0 = 3F / (2 * pi * a^2)
        """
        if contact_radius_m <= 0:
            raise HertzianContactError("Contact radius must be positive")
        return 3.0 * force_n / (2.0 * math.pi * contact_radius_m * contact_radius_m)

    @staticmethod
    def contact_area(contact_radius_m: float) -> float:
        """Compute the circular contact area in m^2."""
        return math.pi * contact_radius_m * contact_radius_m


# ============================================================
# Archard Wear Model
# ============================================================


class ArchardWear:
    """Implements the Archard wear equation.

    V = K * F_N * s / H

    where V is wear volume (m^3), K is the dimensionless wear
    coefficient, F_N is normal force (N), s is sliding distance (m),
    and H is hardness of the softer material (Pa).
    """

    def __init__(self, wear_coefficient: float = 1e-4) -> None:
        if wear_coefficient < 0 or wear_coefficient > 1:
            raise WearModelError(
                0.0,
                f"Wear coefficient K={wear_coefficient} must be in [0, 1]",
            )
        self._k = wear_coefficient

    @property
    def wear_coefficient(self) -> float:
        return self._k

    def wear_volume(
        self, normal_force_n: float, sliding_distance_m: float, hardness_pa: float
    ) -> float:
        """Compute wear volume in cubic meters."""
        if hardness_pa <= 0:
            raise WearModelError(0.0, "Hardness must be positive")
        if normal_force_n < 0:
            raise WearModelError(0.0, "Normal force must be non-negative")
        v = self._k * normal_force_n * sliding_distance_m / hardness_pa
        if v < 0:
            raise WearModelError(v, "Negative wear volume computed")
        return v

    def wear_depth(
        self, normal_force_n: float, sliding_distance_m: float,
        hardness_pa: float, contact_area_m2: float,
    ) -> float:
        """Compute wear depth in meters."""
        v = self.wear_volume(normal_force_n, sliding_distance_m, hardness_pa)
        if contact_area_m2 <= 0:
            raise WearModelError(v, "Contact area must be positive")
        return v / contact_area_m2


# ============================================================
# Stribeck Curve
# ============================================================


class StribeckCurve:
    """Models the Stribeck curve mapping Hersey number to friction coefficient.

    The Hersey number H = eta * N / P where eta is dynamic viscosity
    (Pa*s), N is rotational speed (rev/s), and P is contact pressure (Pa).
    """

    def __init__(
        self,
        mu_boundary: float = 0.15,
        mu_min: float = 0.005,
        transition_hersey: float = 1e-6,
    ) -> None:
        self._mu_b = mu_boundary
        self._mu_min = mu_min
        self._h_trans = transition_hersey

    def hersey_number(
        self, viscosity_pa_s: float, speed_rev_s: float, pressure_pa: float
    ) -> float:
        """Compute the Hersey number."""
        if viscosity_pa_s <= 0 or speed_rev_s < 0 or pressure_pa <= 0:
            raise LubricationRegimeError(
                0.0, "Viscosity and pressure must be positive; speed non-negative"
            )
        return viscosity_pa_s * speed_rev_s / pressure_pa

    def regime(self, hersey: float) -> LubricationRegime:
        """Classify the lubrication regime from the Hersey number."""
        if hersey < 0:
            raise LubricationRegimeError(hersey, "Hersey number must be non-negative")
        if hersey < self._h_trans * 0.1:
            return LubricationRegime.BOUNDARY
        elif hersey < self._h_trans * 10.0:
            return LubricationRegime.MIXED
        else:
            return LubricationRegime.HYDRODYNAMIC

    def friction_coefficient(self, hersey: float) -> float:
        """Compute friction coefficient from the Stribeck curve."""
        regime = self.regime(hersey)
        if regime == LubricationRegime.BOUNDARY:
            return self._mu_b
        elif regime == LubricationRegime.HYDRODYNAMIC:
            # Linear increase with Hersey number in hydrodynamic regime
            return self._mu_min + hersey * 1e3
        else:
            # Mixed regime: interpolation
            t = math.log10(max(hersey, 1e-20)) - math.log10(self._h_trans * 0.1)
            t /= math.log10(10.0 / 0.1)
            t = max(0.0, min(1.0, t))
            return self._mu_b + (self._mu_min - self._mu_b) * t


# ============================================================
# Surface Roughness Analyzer
# ============================================================


class SurfaceRoughnessAnalyzer:
    """Analyzes surface roughness and real contact area.

    The ratio of real contact area to apparent contact area determines
    the effective friction and wear behavior. For rough surfaces,
    A_real / A_apparent << 1.
    """

    @staticmethod
    def real_contact_area_ratio(
        roughness_rq_um: float, normal_pressure_mpa: float, hardness_gpa: float
    ) -> float:
        """Estimate the real contact area ratio."""
        if roughness_rq_um < 0:
            raise SurfaceRoughnessError(roughness_rq_um, "Rq must be non-negative")
        if hardness_gpa <= 0:
            raise SurfaceRoughnessError(
                roughness_rq_um, f"Hardness must be positive: {hardness_gpa} GPa"
            )
        # Simplified Greenwood-Williamson: A_real/A_app ~ P / H
        ratio = (normal_pressure_mpa * 1e-3) / hardness_gpa
        return min(1.0, max(0.0, ratio))

    @staticmethod
    def composite_roughness(rq1_um: float, rq2_um: float) -> float:
        """Compute composite RMS roughness of two contacting surfaces."""
        if rq1_um < 0 or rq2_um < 0:
            raise SurfaceRoughnessError(
                min(rq1_um, rq2_um), "Roughness values must be non-negative"
            )
        return math.sqrt(rq1_um ** 2 + rq2_um ** 2)


# ============================================================
# FizzTribology Middleware
# ============================================================


class TribologyMiddleware(IMiddleware):
    """Injects tribological analysis into the FizzBuzz pipeline.

    For each number evaluated, the middleware computes friction
    coefficients, contact mechanics parameters, and wear estimates
    for the evaluation interface.
    """

    def __init__(
        self,
        surface1: SurfaceProperties | None = None,
        surface2: SurfaceProperties | None = None,
    ) -> None:
        self._s1 = surface1 or SurfaceProperties()
        self._s2 = surface2 or SurfaceProperties(
            elastic_modulus_gpa=70.0, poisson_ratio=0.33,
            hardness_gpa=1.0, roughness_ra_um=1.6,
        )
        self._friction = CoulombFriction(mu_static=0.4, mu_kinetic=0.3)
        self._wear = ArchardWear(wear_coefficient=1e-4)

    @property
    def friction_model(self) -> CoulombFriction:
        return self._friction

    def get_name(self) -> str:
        return "fizztribology"

    def get_priority(self) -> int:
        return 302

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Compute tribological parameters and inject into context."""
        try:
            n = context.number
            # Map number to contact conditions
            normal_force = 10.0 + (n % 50) * 2.0
            sliding_distance = 0.001 * n

            e_star = HertzianContact.reduced_modulus(
                self._s1.elastic_modulus_gpa, self._s1.poisson_ratio,
                self._s2.elastic_modulus_gpa, self._s2.poisson_ratio,
            )

            contact_radius = HertzianContact.contact_radius(
                normal_force, 0.01, e_star * 1e9,
            )
            max_pressure = HertzianContact.max_contact_pressure(
                normal_force, contact_radius,
            )

            friction_force = self._friction.kinetic_friction_force(normal_force)

            wear_vol = self._wear.wear_volume(
                normal_force, sliding_distance,
                min(self._s1.hardness_gpa, self._s2.hardness_gpa) * 1e9,
            )

            context.metadata["tribo_friction_force_n"] = round(friction_force, 4)
            context.metadata["tribo_contact_radius_m"] = contact_radius
            context.metadata["tribo_max_pressure_pa"] = max_pressure
            context.metadata["tribo_wear_volume_m3"] = wear_vol

            logger.debug(
                "FizzTribology: number=%d F_f=%.2fN a=%.2e m p0=%.2e Pa wear=%.2e m^3",
                n, friction_force, contact_radius, max_pressure, wear_vol,
            )
        except Exception as exc:
            logger.error("FizzTribology middleware error: %s", exc)
            context.metadata["tribo_error"] = str(exc)

        return next_handler(context)

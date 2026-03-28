"""
Enterprise FizzBuzz Platform - FizzOptics: Optical System Designer

Implements ray tracing through multi-element lens systems, Snell's law
refraction, thin lens imaging, Seidel aberration analysis, modulation
transfer function computation, and optical path difference calculation
for FizzBuzz evaluation sequences.

Each FizzBuzz number passes through an optical system before reaching
the output formatter. The number enters as a collimated beam of
information, and the lens system focuses it onto the classification
focal plane. Numbers divisible by 3 are refracted toward the Fizz
detector, numbers divisible by 5 toward the Buzz detector, and numbers
divisible by 15 undergo chromatic splitting where both detectors are
illuminated simultaneously.

The image quality at each detector directly determines classification
accuracy. A poorly corrected optical system would introduce aberrations
that blur the distinction between Fizz and non-Fizz numbers, leading
to misclassification. The MTF analysis quantifies the contrast transfer
at each spatial frequency, ensuring that the finest details of the
number's divisibility structure are resolved.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPEED_OF_LIGHT = 2.998e8  # m/s
DEFAULT_WAVELENGTH_NM = 550.0  # Green light (peak sensitivity)
N_AIR = 1.0003  # Refractive index of air at STP
N_GLASS_BK7 = 1.5168  # Schott BK7 crown glass
N_GLASS_SF11 = 1.7847  # Schott SF11 flint glass

# Abbe numbers for dispersion
ABBE_BK7 = 64.17
ABBE_SF11 = 25.76

# Aberration tolerance (waves at 550nm)
DEFAULT_ABERRATION_LIMIT = 0.25  # Rayleigh criterion


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SurfaceType(Enum):
    """Optical surface types."""
    SPHERICAL = auto()
    PLANAR = auto()
    ASPHERIC = auto()
    STOP = auto()


class AberrationType(Enum):
    """Seidel aberration types."""
    SPHERICAL = auto()
    COMA = auto()
    ASTIGMATISM = auto()
    FIELD_CURVATURE = auto()
    DISTORTION = auto()
    CHROMATIC = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Ray:
    """A geometric ray with position and direction."""
    y: float = 0.0  # Height above optical axis (m)
    u: float = 0.0  # Angle with optical axis (radians)
    wavelength_nm: float = DEFAULT_WAVELENGTH_NM
    intensity: float = 1.0
    ray_id: int = 0
    optical_path_length: float = 0.0

    @property
    def is_paraxial(self) -> bool:
        return abs(self.u) < 0.1  # Small angle approximation valid


@dataclass
class OpticalSurface:
    """A single refractive surface in the optical system."""
    surface_type: SurfaceType = SurfaceType.SPHERICAL
    radius_of_curvature: float = float("inf")  # m (positive = center to right)
    thickness_after: float = 0.01  # m (to next surface)
    n_before: float = N_AIR
    n_after: float = N_GLASS_BK7
    aperture_radius: float = 0.025  # m
    surface_index: int = 0

    @property
    def power(self) -> float:
        """Optical power (diopters) = (n2 - n1) / R."""
        if abs(self.radius_of_curvature) < 1e-15:
            return 0.0
        return (self.n_after - self.n_before) / self.radius_of_curvature


@dataclass
class LensElement:
    """A single lens element (two surfaces + glass)."""
    front: OpticalSurface = field(default_factory=OpticalSurface)
    back: OpticalSurface = field(default_factory=OpticalSurface)
    glass_type: str = "BK7"

    @property
    def focal_length(self) -> float:
        """Thin lens focal length from lensmaker's equation."""
        n = self.front.n_after
        r1 = self.front.radius_of_curvature
        r2 = self.back.radius_of_curvature
        if abs(r1) < 1e-15 or abs(r2) < 1e-15:
            return float("inf")
        power = (n - 1.0) * (1.0 / r1 - 1.0 / r2)
        return 1.0 / power if abs(power) > 1e-15 else float("inf")


@dataclass
class AberrationCoefficient:
    """A single Seidel aberration coefficient."""
    aberration_type: AberrationType = AberrationType.SPHERICAL
    coefficient: float = 0.0
    waves: float = 0.0  # In units of wavelength


@dataclass
class MTFPoint:
    """A single point on the MTF curve."""
    spatial_frequency: float = 0.0  # lp/mm
    modulation: float = 1.0  # [0, 1]


@dataclass
class OpticalAnalysis:
    """Complete optical analysis result."""
    focal_length: float = 0.0
    image_distance: float = 0.0
    magnification: float = 0.0
    aberrations: list[AberrationCoefficient] = field(default_factory=list)
    mtf_curve: list[MTFPoint] = field(default_factory=list)
    optical_path_difference: float = 0.0
    total_transmittance: float = 1.0
    diffraction_limit_lp_mm: float = 0.0
    strehl_ratio: float = 1.0


# ---------------------------------------------------------------------------
# Snell's Law Engine
# ---------------------------------------------------------------------------


class SnellEngine:
    """Applies Snell's law at optical interfaces.

    n1 * sin(theta1) = n2 * sin(theta2)

    Handles total internal reflection by raising SnellLawError when
    the angle of incidence exceeds the critical angle.
    """

    def refract(self, n1: float, n2: float, angle_rad: float) -> float:
        """Compute the refracted angle using Snell's law."""
        sin_theta2 = n1 * math.sin(angle_rad) / n2

        if abs(sin_theta2) > 1.0:
            from enterprise_fizzbuzz.domain.exceptions.fizzoptics import SnellLawError
            raise SnellLawError(n1, n2, math.degrees(angle_rad))

        return math.asin(sin_theta2)

    def critical_angle(self, n1: float, n2: float) -> float:
        """Compute the critical angle for total internal reflection."""
        if n2 >= n1:
            return math.pi / 2.0  # No TIR possible
        return math.asin(n2 / n1)

    def fresnel_reflectance(self, n1: float, n2: float, angle_rad: float) -> float:
        """Compute Fresnel reflectance at normal incidence (approximate)."""
        r = ((n1 - n2) / (n1 + n2)) ** 2
        return r


# ---------------------------------------------------------------------------
# Thin Lens Calculator
# ---------------------------------------------------------------------------


class ThinLensCalculator:
    """Applies the thin lens equation: 1/f = 1/do + 1/di."""

    def compute_image(
        self, focal_length: float, object_distance: float
    ) -> tuple[float, float]:
        """Compute image distance and magnification.

        Returns (image_distance, magnification).
        """
        if abs(object_distance - focal_length) < 1e-12:
            from enterprise_fizzbuzz.domain.exceptions.fizzoptics import ThinLensError
            raise ThinLensError(focal_length, object_distance)

        if abs(focal_length) < 1e-15:
            from enterprise_fizzbuzz.domain.exceptions.fizzoptics import ThinLensError
            raise ThinLensError(focal_length, object_distance)

        di = 1.0 / (1.0 / focal_length - 1.0 / object_distance)
        magnification = -di / object_distance if abs(object_distance) > 1e-15 else 0.0

        return di, magnification


# ---------------------------------------------------------------------------
# Ray Tracer
# ---------------------------------------------------------------------------


class SequentialRayTracer:
    """Traces rays through a sequential optical system.

    Uses the paraxial ray trace algorithm (ynu trace) for speed and
    accuracy in the small-angle regime. Each ray is characterized by
    its height (y) and angle (u) at each surface.
    """

    def trace(
        self, ray: Ray, surfaces: list[OpticalSurface]
    ) -> list[Ray]:
        """Trace a ray through all surfaces, returning the ray at each surface."""
        trace_history: list[Ray] = [Ray(
            y=ray.y, u=ray.u, wavelength_nm=ray.wavelength_nm,
            ray_id=ray.ray_id, optical_path_length=0.0,
        )]

        y = ray.y
        u = ray.u
        opl = 0.0

        for surface in surfaces:
            # Refraction at surface
            n1 = surface.n_before
            n2 = surface.n_after
            c = 1.0 / surface.radius_of_curvature if abs(surface.radius_of_curvature) > 1e-15 else 0.0

            # Check aperture
            if abs(y) > surface.aperture_radius:
                from enterprise_fizzbuzz.domain.exceptions.fizzoptics import RayTraceError
                raise RayTraceError(
                    ray.ray_id, surface.surface_index, "ray vignetted by aperture"
                )

            # Paraxial refraction: n2*u2 = n1*u1 - y*(n2-n1)*c
            u_new = (n1 * u - y * (n2 - n1) * c) / n2

            opl += n1 * surface.thickness_after

            # Transfer to next surface: y2 = y1 + u2*t
            y_new = y + u_new * surface.thickness_after

            y = y_new
            u = u_new

            trace_history.append(Ray(
                y=y, u=u, wavelength_nm=ray.wavelength_nm,
                ray_id=ray.ray_id, optical_path_length=opl,
            ))

        return trace_history


# ---------------------------------------------------------------------------
# Aberration Analyzer
# ---------------------------------------------------------------------------


class AberrationAnalyzer:
    """Computes Seidel aberration coefficients.

    The five primary (third-order) aberrations are computed from the
    paraxial ray trace data using the Seidel sum formulas.
    """

    def analyze(
        self,
        focal_length: float,
        f_number: float,
        field_angle_deg: float = 0.0,
    ) -> list[AberrationCoefficient]:
        """Compute Seidel aberrations for the given system parameters."""
        wavelength_m = DEFAULT_WAVELENGTH_NM * 1e-9

        # Simplified Seidel coefficient estimation
        aperture = focal_length / (2.0 * f_number) if f_number > 0 else 0.01
        h = aperture  # Marginal ray height
        field_rad = math.radians(field_angle_deg)

        # Spherical aberration ~ h^4 / f^3
        s1 = h ** 4 / (8.0 * focal_length ** 3) if focal_length != 0 else 0.0

        # Coma ~ h^3 * field / f^2
        s2 = h ** 3 * field_rad / (2.0 * focal_length ** 2) if focal_length != 0 else 0.0

        # Astigmatism ~ h^2 * field^2 / f
        s3 = h ** 2 * field_rad ** 2 / (2.0 * focal_length) if focal_length != 0 else 0.0

        # Field curvature ~ h^2 * field^2 / f
        s4 = s3 * 0.5

        # Distortion ~ h * field^3
        s5 = h * field_rad ** 3 / (2.0 * focal_length) if focal_length != 0 else 0.0

        coefficients = [
            AberrationCoefficient(
                AberrationType.SPHERICAL, s1,
                s1 / wavelength_m if wavelength_m > 0 else 0.0,
            ),
            AberrationCoefficient(
                AberrationType.COMA, s2,
                s2 / wavelength_m if wavelength_m > 0 else 0.0,
            ),
            AberrationCoefficient(
                AberrationType.ASTIGMATISM, s3,
                s3 / wavelength_m if wavelength_m > 0 else 0.0,
            ),
            AberrationCoefficient(
                AberrationType.FIELD_CURVATURE, s4,
                s4 / wavelength_m if wavelength_m > 0 else 0.0,
            ),
            AberrationCoefficient(
                AberrationType.DISTORTION, s5,
                s5 / wavelength_m if wavelength_m > 0 else 0.0,
            ),
        ]

        return coefficients


# ---------------------------------------------------------------------------
# MTF Calculator
# ---------------------------------------------------------------------------


class MTFCalculator:
    """Computes the Modulation Transfer Function.

    The MTF describes the contrast transfer as a function of spatial
    frequency. For a diffraction-limited system, the MTF is the
    autocorrelation of the exit pupil. Aberrations reduce the MTF
    below the diffraction limit.
    """

    def compute(
        self,
        focal_length: float,
        f_number: float,
        rms_wavefront_error: float = 0.0,
        num_points: int = 25,
    ) -> tuple[list[MTFPoint], float]:
        """Compute the MTF curve and diffraction-limited cutoff frequency.

        Returns (mtf_curve, cutoff_frequency_lp_mm).
        """
        wavelength_mm = DEFAULT_WAVELENGTH_NM * 1e-6  # mm
        cutoff = 1.0 / (wavelength_mm * f_number) if f_number > 0 else 1000.0

        # Strehl ratio from Marechal approximation
        strehl = math.exp(-(2.0 * math.pi * rms_wavefront_error) ** 2) if rms_wavefront_error < 0.3 else 0.01

        points: list[MTFPoint] = []
        for i in range(num_points):
            freq = cutoff * i / (num_points - 1)
            nu = freq / cutoff if cutoff > 0 else 0.0

            # Diffraction-limited MTF for circular aperture
            if nu <= 1.0:
                mtf_diff = (2.0 / math.pi) * (
                    math.acos(nu) - nu * math.sqrt(1.0 - nu ** 2)
                )
            else:
                mtf_diff = 0.0

            # Apply aberration reduction
            mtf = mtf_diff * strehl

            points.append(MTFPoint(spatial_frequency=freq, modulation=max(0.0, mtf)))

        return points, cutoff


# ---------------------------------------------------------------------------
# Optical System Engine
# ---------------------------------------------------------------------------


class OpticalSystemEngine:
    """Integrates all optical analysis components.

    Designs and analyzes an optical system tailored to each FizzBuzz
    number. The focal length is derived from the number magnitude,
    the f-number from the classification type, and the field angle
    from the number's position in the sequence.
    """

    def __init__(self) -> None:
        self.snell = SnellEngine()
        self.thin_lens = ThinLensCalculator()
        self.ray_tracer = SequentialRayTracer()
        self.aberration_analyzer = AberrationAnalyzer()
        self.mtf_calculator = MTFCalculator()
        self._analysis_count = 0

    def analyze_number(
        self, number: int, is_fizz: bool, is_buzz: bool
    ) -> OpticalAnalysis:
        """Perform complete optical analysis for a FizzBuzz number."""
        self._analysis_count += 1

        # System parameters derived from number
        focal_length = 0.05 + 0.001 * (abs(number) % 100)  # 50-150mm
        f_number = self._classify_f_number(is_fizz, is_buzz)
        object_distance = focal_length * (2.0 + (abs(number) % 10) * 0.5)
        field_angle = (abs(number) % 20) * 0.5

        # Thin lens imaging
        image_distance, magnification = self.thin_lens.compute_image(
            focal_length, object_distance
        )

        # Aberration analysis
        aberrations = self.aberration_analyzer.analyze(
            focal_length, f_number, field_angle
        )

        # RMS wavefront error from aberrations
        rms_wfe = math.sqrt(sum(a.coefficient ** 2 for a in aberrations))
        rms_wfe_waves = rms_wfe / (DEFAULT_WAVELENGTH_NM * 1e-9) if rms_wfe > 0 else 0.0

        # MTF
        mtf_curve, cutoff = self.mtf_calculator.compute(
            focal_length, f_number, rms_wfe_waves
        )

        # OPD
        opd = self._compute_opd(focal_length, f_number, aberrations)

        # Transmittance (Fresnel losses at each surface, 4 surfaces typical)
        r_per_surface = self.snell.fresnel_reflectance(N_AIR, N_GLASS_BK7, 0.0)
        transmittance = (1.0 - r_per_surface) ** 4

        # Strehl ratio
        strehl = math.exp(-(2.0 * math.pi * rms_wfe_waves) ** 2) if rms_wfe_waves < 0.3 else 0.01

        return OpticalAnalysis(
            focal_length=focal_length,
            image_distance=image_distance,
            magnification=magnification,
            aberrations=aberrations,
            mtf_curve=mtf_curve,
            optical_path_difference=opd,
            total_transmittance=transmittance,
            diffraction_limit_lp_mm=cutoff,
            strehl_ratio=strehl,
        )

    def _classify_f_number(self, is_fizz: bool, is_buzz: bool) -> float:
        """Assign f-number based on FizzBuzz classification."""
        if is_fizz and is_buzz:
            return 2.8  # Fast lens for maximum light gathering
        elif is_fizz:
            return 4.0
        elif is_buzz:
            return 5.6
        else:
            return 8.0

    def _compute_opd(
        self,
        focal_length: float,
        f_number: float,
        aberrations: list[AberrationCoefficient],
    ) -> float:
        """Compute peak-to-valley optical path difference."""
        opd = sum(abs(a.coefficient) for a in aberrations)
        return opd

    @property
    def analysis_count(self) -> int:
        return self._analysis_count


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class OpticsMiddleware(IMiddleware):
    """Middleware that performs optical system analysis for each evaluation.

    Each number is imaged through a lens system optimized for its
    classification type. The image quality metrics (MTF, Strehl ratio,
    aberrations) are attached to the processing context.

    Priority 294 positions this in the physical sciences tier.
    """

    def __init__(self) -> None:
        self._engine = OpticalSystemEngine()
        self._evaluations = 0

    def get_name(self) -> str:
        return "fizzoptics"

    def get_priority(self) -> int:
        return 294

    @property
    def engine(self) -> OpticalSystemEngine:
        return self._engine

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        try:
            analysis = self._engine.analyze_number(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["optics"] = {
                "focal_length_mm": round(analysis.focal_length * 1000, 2),
                "image_distance_mm": round(analysis.image_distance * 1000, 2),
                "magnification": round(analysis.magnification, 4),
                "strehl_ratio": round(analysis.strehl_ratio, 4),
                "transmittance": round(analysis.total_transmittance, 4),
                "diffraction_limit_lp_mm": round(analysis.diffraction_limit_lp_mm, 2),
                "opd_m": round(analysis.optical_path_difference, 10),
                "aberration_count": len(analysis.aberrations),
                "mtf_points": len(analysis.mtf_curve),
            }

            logger.debug(
                "FizzOptics: number=%d f=%.1fmm Strehl=%.4f",
                number,
                analysis.focal_length * 1000,
                analysis.strehl_ratio,
            )

        except Exception:
            logger.exception(
                "FizzOptics: analysis failed for number %d", number
            )

        return result

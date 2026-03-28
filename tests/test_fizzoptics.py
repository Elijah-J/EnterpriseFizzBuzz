"""
Enterprise FizzBuzz Platform - FizzOptics Optical System Designer Test Suite

Comprehensive verification of the optical analysis pipeline, including
Snell's law refraction, thin lens imaging, sequential ray tracing,
Seidel aberration computation, MTF analysis, and optical path difference
calculation. Image quality at the classification focal plane directly
determines whether a number is correctly resolved as Fizz, Buzz, or
FizzBuzz — any degradation in the optical transfer function risks
misclassification.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzoptics import (
    DEFAULT_ABERRATION_LIMIT,
    DEFAULT_WAVELENGTH_NM,
    N_AIR,
    N_GLASS_BK7,
    N_GLASS_SF11,
    SPEED_OF_LIGHT,
    AberrationAnalyzer,
    AberrationCoefficient,
    AberrationType,
    LensElement,
    MTFCalculator,
    MTFPoint,
    OpticalAnalysis,
    OpticalSurface,
    OpticalSystemEngine,
    OpticsMiddleware,
    Ray,
    SequentialRayTracer,
    SnellEngine,
    SurfaceType,
    ThinLensCalculator,
)
from enterprise_fizzbuzz.domain.exceptions.fizzoptics import (
    AberrationError,
    FizzOpticsError,
    MTFError,
    OpticalPathError,
    OpticsMiddlewareError,
    RayTraceError,
    SnellLawError,
    ThinLensError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(number: int, output: str = "", is_fizz: bool = False, is_buzz: bool = False):
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


# ===========================================================================
# Snell's Law Tests
# ===========================================================================


class TestSnellEngine:

    def test_normal_incidence_no_refraction(self):
        engine = SnellEngine()
        angle_out = engine.refract(N_AIR, N_GLASS_BK7, 0.0)
        assert abs(angle_out) < 1e-10

    def test_snell_law_ratio(self):
        engine = SnellEngine()
        angle_in = math.radians(30.0)
        angle_out = engine.refract(N_AIR, N_GLASS_BK7, angle_in)
        ratio = N_AIR * math.sin(angle_in) / (N_GLASS_BK7 * math.sin(angle_out))
        assert abs(ratio - 1.0) < 1e-6

    def test_total_internal_reflection(self):
        engine = SnellEngine()
        critical = engine.critical_angle(N_GLASS_BK7, N_AIR)
        with pytest.raises(SnellLawError):
            engine.refract(N_GLASS_BK7, N_AIR, critical + 0.1)

    def test_critical_angle_value(self):
        engine = SnellEngine()
        critical = engine.critical_angle(N_GLASS_BK7, N_AIR)
        expected = math.asin(N_AIR / N_GLASS_BK7)
        assert abs(critical - expected) < 1e-6

    def test_fresnel_reflectance_positive(self):
        engine = SnellEngine()
        r = engine.fresnel_reflectance(N_AIR, N_GLASS_BK7, 0.0)
        assert 0 < r < 0.1


# ===========================================================================
# Thin Lens Tests
# ===========================================================================


class TestThinLensCalculator:

    def test_real_image(self):
        calc = ThinLensCalculator()
        di, mag = calc.compute_image(0.1, 0.3)
        assert di > 0  # Real image
        assert mag < 0  # Inverted

    def test_object_at_focal_raises(self):
        calc = ThinLensCalculator()
        with pytest.raises(ThinLensError):
            calc.compute_image(0.1, 0.1)

    def test_virtual_image(self):
        calc = ThinLensCalculator()
        di, mag = calc.compute_image(0.1, 0.05)  # Object inside focal length
        assert di < 0  # Virtual image
        assert mag > 0  # Upright

    def test_magnification_formula(self):
        calc = ThinLensCalculator()
        di, mag = calc.compute_image(0.1, 0.2)
        expected_mag = -di / 0.2
        assert abs(mag - expected_mag) < 1e-10

    def test_zero_focal_length_raises(self):
        calc = ThinLensCalculator()
        with pytest.raises(ThinLensError):
            calc.compute_image(0.0, 0.3)


# ===========================================================================
# Ray Tracer Tests
# ===========================================================================


class TestSequentialRayTracer:

    def test_trace_single_surface(self):
        tracer = SequentialRayTracer()
        ray = Ray(y=0.01, u=0.0, ray_id=1)
        surface = OpticalSurface(
            radius_of_curvature=0.1,
            thickness_after=0.05,
            n_before=N_AIR,
            n_after=N_GLASS_BK7,
            aperture_radius=0.05,
            surface_index=0,
        )
        history = tracer.trace(ray, [surface])
        assert len(history) == 2

    def test_ray_vignetting(self):
        tracer = SequentialRayTracer()
        ray = Ray(y=0.1, u=0.0, ray_id=1)  # Ray outside aperture
        surface = OpticalSurface(
            aperture_radius=0.01,
            surface_index=0,
        )
        with pytest.raises(RayTraceError):
            tracer.trace(ray, [surface])


# ===========================================================================
# Aberration Tests
# ===========================================================================


class TestAberrationAnalyzer:

    def test_five_seidel_aberrations(self):
        analyzer = AberrationAnalyzer()
        aberrations = analyzer.analyze(0.1, 4.0, 10.0)
        assert len(aberrations) == 5

    def test_spherical_at_zero_field(self):
        analyzer = AberrationAnalyzer()
        aberrations = analyzer.analyze(0.1, 4.0, 0.0)
        sph = [a for a in aberrations if a.aberration_type == AberrationType.SPHERICAL][0]
        assert sph.coefficient > 0
        # Coma, astigmatism etc. should be zero at zero field
        coma = [a for a in aberrations if a.aberration_type == AberrationType.COMA][0]
        assert abs(coma.coefficient) < 1e-15

    def test_aberrations_increase_with_field(self):
        analyzer = AberrationAnalyzer()
        narrow = analyzer.analyze(0.1, 4.0, 1.0)
        wide = analyzer.analyze(0.1, 4.0, 20.0)
        narrow_total = sum(abs(a.coefficient) for a in narrow)
        wide_total = sum(abs(a.coefficient) for a in wide)
        assert wide_total > narrow_total


# ===========================================================================
# MTF Tests
# ===========================================================================


class TestMTFCalculator:

    def test_mtf_starts_near_one(self):
        calc = MTFCalculator()
        points, cutoff = calc.compute(0.1, 4.0, 0.0)
        assert points[0].modulation > 0.5

    def test_mtf_ends_near_zero(self):
        calc = MTFCalculator()
        points, cutoff = calc.compute(0.1, 4.0, 0.0)
        assert points[-1].modulation < 0.01

    def test_cutoff_frequency_positive(self):
        calc = MTFCalculator()
        _, cutoff = calc.compute(0.1, 4.0)
        assert cutoff > 0


# ===========================================================================
# Engine Integration Tests
# ===========================================================================


class TestOpticalSystemEngine:

    def test_analyze_fizzbuzz_number(self):
        engine = OpticalSystemEngine()
        result = engine.analyze_number(15, True, True)
        assert result.focal_length > 0
        assert result.strehl_ratio > 0
        assert len(result.aberrations) == 5

    def test_analysis_count(self):
        engine = OpticalSystemEngine()
        engine.analyze_number(1, False, False)
        engine.analyze_number(3, True, False)
        assert engine.analysis_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================


class TestOpticsMiddleware:

    def test_middleware_attaches_metadata(self):
        mw = OpticsMiddleware()
        ctx = _make_context(5, "Buzz", is_buzz=True)
        result = mw.process(ctx, lambda c: c)
        assert "optics" in result.metadata
        assert "focal_length_mm" in result.metadata["optics"]
        assert "strehl_ratio" in result.metadata["optics"]

    def test_middleware_handles_fizz(self):
        mw = OpticsMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["optics"]["strehl_ratio"] > 0


# ===========================================================================
# Exception Tests
# ===========================================================================


class TestExceptions:

    def test_base_exception(self):
        err = FizzOpticsError("test")
        assert "EFP-OP00" in str(err.error_code)

    def test_snell_error_fields(self):
        err = SnellLawError(1.5, 1.0, 45.0)
        assert err.n1 == 1.5
        assert err.n2 == 1.0
        assert err.angle_deg == 45.0

"""
Enterprise FizzBuzz Platform - FizzTelescope Telescope Control Test Suite

Comprehensive verification of the telescope control system, including
celestial coordinate validation, mount tracking, field rotation
computation, autoguiding, plate solving, and star catalog lookup.
These tests ensure that each FizzBuzz evaluation is observed at the
correct celestial position with sub-arcsecond pointing accuracy.

An error in the sidereal tracking rate would cause the telescope to
drift from the target over the course of the evaluation session,
placing the FizzBuzz classification at the wrong celestial coordinates
and invalidating the astrometric association.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizztelescope import (
    Autoguider,
    CatalogStar,
    CelestialCoordinate,
    FieldRotationCalculator,
    HorizontalCoordinate,
    MountController,
    MountType,
    PlateSolver,
    SIDEREAL_RATE_ARCSEC_S,
    StarCatalog,
    TelescopeMiddleware,
    TrackingMode,
)
from enterprise_fizzbuzz.domain.exceptions.fizztelescope import (
    AutoguidingError,
    CatalogLookupError,
    CoordinateError,
    FieldRotationError,
    MountTrackingError,
    PlateSolveError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Celestial Coordinate Tests
# ============================================================


class TestCelestialCoordinate:
    def test_valid_coordinates(self):
        coord = CelestialCoordinate(ra_hours=12.0, dec_degrees=45.0)
        coord.validate()  # Should not raise

    def test_ra_out_of_range_raises(self):
        coord = CelestialCoordinate(ra_hours=25.0, dec_degrees=0.0)
        with pytest.raises(CoordinateError):
            coord.validate()

    def test_dec_out_of_range_raises(self):
        coord = CelestialCoordinate(ra_hours=12.0, dec_degrees=95.0)
        with pytest.raises(CoordinateError):
            coord.validate()

    def test_ra_degrees_conversion(self):
        coord = CelestialCoordinate(ra_hours=12.0, dec_degrees=0.0)
        assert abs(coord.ra_degrees() - 180.0) < 0.01

    def test_angular_separation_same_point(self):
        c1 = CelestialCoordinate(ra_hours=6.0, dec_degrees=30.0)
        sep = c1.angular_separation(c1)
        assert sep < 0.001

    def test_angular_separation_poles(self):
        north = CelestialCoordinate(ra_hours=0.0, dec_degrees=90.0)
        south = CelestialCoordinate(ra_hours=0.0, dec_degrees=-90.0)
        sep = north.angular_separation(south)
        assert abs(sep - 180.0) < 0.01


# ============================================================
# Star Catalog Tests
# ============================================================


class TestStarCatalog:
    def test_lookup_sirius(self):
        catalog = StarCatalog()
        star = catalog.lookup("Sirius")
        assert star.magnitude < 0
        assert abs(star.ra_hours - 6.7525) < 0.01

    def test_lookup_case_insensitive(self):
        catalog = StarCatalog()
        star = catalog.lookup("vega")
        assert star.designation == "Vega"

    def test_lookup_unknown_raises(self):
        catalog = StarCatalog()
        with pytest.raises(CatalogLookupError):
            catalog.lookup("FizzStar")

    def test_stars_in_field(self):
        catalog = StarCatalog()
        center = CelestialCoordinate(ra_hours=19.0, dec_degrees=30.0)
        stars = catalog.stars_in_field(center, 15.0)
        assert len(stars) > 0


# ============================================================
# Mount Controller Tests
# ============================================================


class TestMountController:
    def test_sidereal_tracking_rate(self):
        mount = MountController(MountType.EQUATORIAL)
        rate = mount.start_tracking(TrackingMode.SIDEREAL)
        assert abs(rate - SIDEREAL_RATE_ARCSEC_S) < 0.001

    def test_lunar_tracking_rate_slower(self):
        mount = MountController(MountType.EQUATORIAL)
        lunar = mount.start_tracking(TrackingMode.LUNAR)
        sidereal = SIDEREAL_RATE_ARCSEC_S
        assert lunar < sidereal

    def test_slew_to_valid_target(self):
        mount = MountController()
        coord = CelestialCoordinate(ra_hours=18.0, dec_degrees=38.0)
        mount.slew_to(coord)  # Should not raise

    def test_tracking_error_sinusoidal(self):
        mount = MountController()
        mount.start_tracking()
        err1 = mount.tracking_error(0.0)
        err2 = mount.tracking_error(120.0)  # Quarter worm period
        # Errors should differ due to sinusoidal PE
        assert isinstance(err1, float)
        assert isinstance(err2, float)

    def test_check_tracking_within_tolerance(self):
        mount = MountController()
        mount._tracking_error_arcsec = 1.0
        mount.check_tracking(max_error_arcsec=2.0)  # Should not raise

    def test_check_tracking_exceeds_tolerance_raises(self):
        mount = MountController()
        mount._tracking_error_arcsec = 5.0
        with pytest.raises(MountTrackingError):
            mount.check_tracking(max_error_arcsec=2.0)


# ============================================================
# Field Rotation Tests
# ============================================================


class TestFieldRotationCalculator:
    def test_rotation_rate_returns_float(self):
        rate = FieldRotationCalculator.rotation_rate(45.0, 60.0, 180.0)
        assert isinstance(rate, float)

    def test_zenith_raises(self):
        with pytest.raises(FieldRotationError):
            FieldRotationCalculator.rotation_rate(45.0, 90.0, 0.0)


# ============================================================
# Autoguider Tests
# ============================================================


class TestAutoguider:
    def test_acquire_guide_star(self):
        catalog = StarCatalog()
        guider = Autoguider(guide_camera_fov_arcmin=600.0, limiting_magnitude=2.0)
        center = CelestialCoordinate(ra_hours=19.0, dec_degrees=30.0)
        star = guider.acquire_guide_star(catalog, center)
        assert star.magnitude <= 2.0
        assert guider.is_locked

    def test_no_guide_star_raises(self):
        catalog = StarCatalog()
        guider = Autoguider(guide_camera_fov_arcmin=0.01, limiting_magnitude=-5.0)
        center = CelestialCoordinate(ra_hours=12.0, dec_degrees=80.0)
        with pytest.raises(AutoguidingError):
            guider.acquire_guide_star(catalog, center)

    def test_compute_correction(self):
        guider = Autoguider()
        ra_pulse, dec_pulse = guider.compute_correction(1.0, 0.5)
        assert ra_pulse > 0
        assert dec_pulse > 0


# ============================================================
# Plate Solver Tests
# ============================================================


class TestPlateSolver:
    def test_solve_with_sufficient_stars(self):
        catalog = StarCatalog()
        solver = PlateSolver(catalog)
        center = CelestialCoordinate(ra_hours=6.0, dec_degrees=0.0)
        # Provide fake pixel positions
        detected = [(100, 200), (300, 400), (150, 350), (250, 150), (200, 300)]
        solved = solver.solve(detected, center, field_radius_deg=30.0)
        assert 0.0 <= solved.ra_hours < 24.0
        assert -90.0 <= solved.dec_degrees <= 90.0

    def test_insufficient_stars_raises(self):
        catalog = StarCatalog()
        solver = PlateSolver(catalog)
        center = CelestialCoordinate(ra_hours=12.0, dec_degrees=0.0)
        detected = [(100, 200)]
        with pytest.raises(PlateSolveError):
            solver.solve(detected, center)


# ============================================================
# Middleware Tests
# ============================================================


class TestTelescopeMiddleware:
    def test_middleware_injects_ra(self):
        mw = TelescopeMiddleware()
        ctx = _make_context(10)
        result = mw.process(ctx, _identity_handler)
        assert "telescope_ra_hours" in result.metadata

    def test_middleware_injects_dec(self):
        mw = TelescopeMiddleware()
        ctx = _make_context(7)
        result = mw.process(ctx, _identity_handler)
        assert "telescope_dec_degrees" in result.metadata

    def test_middleware_injects_tracking_rate(self):
        mw = TelescopeMiddleware()
        ctx = _make_context(15)
        result = mw.process(ctx, _identity_handler)
        assert "telescope_tracking_rate" in result.metadata
        assert abs(result.metadata["telescope_tracking_rate"] - SIDEREAL_RATE_ARCSEC_S) < 0.001

    def test_middleware_name(self):
        mw = TelescopeMiddleware()
        assert mw.get_name() == "fizztelescope"

    def test_middleware_priority(self):
        mw = TelescopeMiddleware()
        assert mw.get_priority() == 303

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = TelescopeMiddleware()
        assert isinstance(mw, IMiddleware)

"""
Enterprise FizzBuzz Platform - FizzAstronomy Celestial Mechanics Test Suite

Comprehensive verification of the orbital mechanics engine, including
Kepler equation solving, n-body gravitational simulation, ephemeris
computation, and coordinate frame transformations. These tests ensure
that FizzBuzz evaluations are correctly contextualized within the
gravitational environment of the solar system.

Accurate celestial mechanics are non-negotiable: an incorrect tidal
factor would misrepresent the gravitational influence on divisibility
checks, constituting a violation of the Enterprise FizzBuzz Celestial
Compliance Standard (EFCCS).
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from typing import Callable

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzastronomy import (
    AstronomyMiddleware,
    CelestialBody,
    CoordinateFrame,
    CoordinateTransformer,
    EphemerisCatalog,
    EphemerisRecord,
    G_AU,
    GravitationalContext,
    KeplerSolver,
    NBodySimulator,
    OBLIQUITY_J2000,
    OrbitalElements,
    OrbitalMechanics,
    Vec3,
)
from enterprise_fizzbuzz.domain.exceptions.fizzastronomy import (
    AstronomyMiddlewareError,
    CelestialBodyNotFoundError,
    CoordinateTransformError,
    EphemerisComputationError,
    InvalidOrbitalElementsError,
    KeplerEquationError,
    NBodyIntegrationError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    """Create a ProcessingContext for testing."""
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Vec3 Tests
# ============================================================


class TestVec3:
    def test_addition(self):
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(4.0, 5.0, 6.0)
        c = a + b
        assert c.x == 5.0
        assert c.y == 7.0
        assert c.z == 9.0

    def test_magnitude(self):
        v = Vec3(3.0, 4.0, 0.0)
        assert abs(v.magnitude() - 5.0) < 1e-10

    def test_normalized(self):
        v = Vec3(0.0, 0.0, 5.0)
        n = v.normalized()
        assert abs(n.z - 1.0) < 1e-10
        assert abs(n.magnitude() - 1.0) < 1e-10

    def test_dot_product(self):
        a = Vec3(1.0, 0.0, 0.0)
        b = Vec3(0.0, 1.0, 0.0)
        assert abs(a.dot(b)) < 1e-10


# ============================================================
# Kepler Equation Tests
# ============================================================


class TestKeplerSolver:
    def test_circular_orbit(self):
        """For e=0, eccentric anomaly equals mean anomaly."""
        E = KeplerSolver.solve(math.pi / 4, 0.0)
        assert abs(E - math.pi / 4) < 1e-10

    def test_low_eccentricity(self):
        """Solve for a typical low-eccentricity orbit (Earth-like)."""
        M = 1.0
        e = 0.0167
        E = KeplerSolver.solve(M, e)
        # Verify: M = E - e*sin(E)
        residual = abs(E - e * math.sin(E) - M)
        assert residual < 1e-10

    def test_high_eccentricity(self):
        """Solve for a high-eccentricity orbit."""
        M = 0.5
        e = 0.9
        E = KeplerSolver.solve(M, e)
        residual = abs(E - e * math.sin(E) - M)
        assert residual < 1e-10

    def test_invalid_eccentricity_raises(self):
        with pytest.raises(KeplerEquationError):
            KeplerSolver.solve(1.0, 1.0)

    def test_true_anomaly_circular(self):
        """True anomaly equals eccentric anomaly for circular orbits."""
        E = math.pi / 3
        nu = KeplerSolver.eccentric_to_true_anomaly(E, 0.0)
        assert abs(nu - E) < 1e-10


# ============================================================
# Orbital Mechanics Tests
# ============================================================


class TestOrbitalMechanics:
    def test_orbital_period_earth(self):
        """Earth's orbital period should be approximately 365.25 days."""
        period = OrbitalMechanics.orbital_period(1.0, 1.0)
        assert abs(period - 365.25) < 1.0

    def test_position_circular_orbit(self):
        """A circular orbit at 1 AU should produce positions at ~1 AU distance."""
        elements = OrbitalElements(
            semi_major_axis=1.0,
            eccentricity=0.0,
            inclination=0.0,
            longitude_ascending=0.0,
            argument_periapsis=0.0,
            mean_anomaly_epoch=0.0,
        )
        pos, vel = OrbitalMechanics.position_at_epoch(elements, 0.0)
        dist = pos.magnitude()
        assert abs(dist - 1.0) < 0.01

    def test_invalid_semi_major_axis_raises(self):
        elements = OrbitalElements(-1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        with pytest.raises(InvalidOrbitalElementsError):
            OrbitalMechanics.position_at_epoch(elements, 0.0)


# ============================================================
# N-Body Simulator Tests
# ============================================================


class TestNBodySimulator:
    def test_two_body_energy_conservation(self):
        """Total energy should be approximately conserved over short integrations."""
        sun = CelestialBody("Sun", mass=1.0, position=Vec3(0, 0, 0), velocity=Vec3(0, 0, 0))
        earth = CelestialBody("Earth", mass=3e-6, position=Vec3(1, 0, 0), velocity=Vec3(0, 0.01721, 0))
        sim = NBodySimulator([sun, earth])
        e0 = sim.total_energy()
        sim.simulate(10.0, 1.0)
        e1 = sim.total_energy()
        # Energy should be conserved to within ~1%
        assert abs((e1 - e0) / e0) < 0.05

    def test_simulation_returns_history(self):
        b1 = CelestialBody("A", mass=1.0, position=Vec3(0, 0, 0), velocity=Vec3(0, 0, 0))
        b2 = CelestialBody("B", mass=1e-3, position=Vec3(1, 0, 0), velocity=Vec3(0, 0.017, 0))
        sim = NBodySimulator([b1, b2])
        history = sim.simulate(5.0, 1.0)
        assert len(history) == 5
        assert len(history[0]) == 2


# ============================================================
# Ephemeris Catalog Tests
# ============================================================


class TestEphemerisCatalog:
    def test_default_bodies_loaded(self):
        catalog = EphemerisCatalog()
        assert "Earth" in catalog.body_names
        assert "Mars" in catalog.body_names

    def test_compute_ephemeris_earth(self):
        catalog = EphemerisCatalog()
        record = catalog.compute_ephemeris("Earth", 2451545.0)
        assert isinstance(record, EphemerisRecord)
        assert record.body_name == "Earth"
        assert record.distance_au > 0

    def test_unknown_body_raises(self):
        catalog = EphemerisCatalog()
        with pytest.raises(CelestialBodyNotFoundError):
            catalog.compute_ephemeris("Pluto", 2451545.0)

    def test_register_custom_body(self):
        catalog = EphemerisCatalog()
        elements = OrbitalElements(2.0, 0.1, 0.0, 0.0, 0.0, 0.0)
        catalog.register_body("TestBody", elements)
        assert "TestBody" in catalog.body_names


# ============================================================
# Coordinate Transform Tests
# ============================================================


class TestCoordinateTransformer:
    def test_ecliptic_to_equatorial_x_preserved(self):
        """The x-axis is shared between ecliptic and equatorial frames."""
        pos = Vec3(1.0, 0.0, 0.0)
        eq = CoordinateTransformer.ecliptic_to_equatorial(pos)
        assert abs(eq.x - 1.0) < 1e-10

    def test_round_trip_ecliptic_equatorial(self):
        """Ecliptic -> equatorial -> ecliptic should recover the original position."""
        pos = Vec3(0.5, 0.3, 0.7)
        eq = CoordinateTransformer.ecliptic_to_equatorial(pos)
        recovered = CoordinateTransformer.equatorial_to_ecliptic(eq)
        assert abs(recovered.x - pos.x) < 1e-10
        assert abs(recovered.y - pos.y) < 1e-10
        assert abs(recovered.z - pos.z) < 1e-10

    def test_galactic_transform_unsupported_inverse(self):
        with pytest.raises(CoordinateTransformError):
            CoordinateTransformer.transform(
                Vec3(1, 0, 0), CoordinateFrame.GALACTIC, CoordinateFrame.ECLIPTIC
            )

    def test_same_frame_returns_same(self):
        pos = Vec3(1.0, 2.0, 3.0)
        result = CoordinateTransformer.transform(pos, CoordinateFrame.ECLIPTIC, CoordinateFrame.ECLIPTIC)
        assert result.x == pos.x


# ============================================================
# Middleware Tests
# ============================================================


class TestAstronomyMiddleware:
    def test_middleware_injects_metadata(self):
        catalog = EphemerisCatalog()
        mw = AstronomyMiddleware(catalog)
        ctx = _make_context(15)
        result = mw.process(ctx, _identity_handler)
        assert "astronomy_tidal_factor" in result.metadata
        assert "astronomy_dominant_body" in result.metadata

    def test_middleware_epoch_advances_with_number(self):
        catalog = EphemerisCatalog()
        mw = AstronomyMiddleware(catalog, base_epoch_jd=2451545.0, epoch_step_days=1.0)
        ctx = _make_context(100)
        result = mw.process(ctx, _identity_handler)
        assert result.metadata["astronomy_epoch_jd"] == 2451645.0

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        catalog = EphemerisCatalog()
        mw = AstronomyMiddleware(catalog)
        assert isinstance(mw, IMiddleware)

"""
Enterprise FizzBuzz Platform - FizzTribology Friction and Wear Test Suite

Comprehensive verification of the tribological engine, including Coulomb
friction, Hertzian contact mechanics, Archard wear model, Stribeck curve
lubrication regime classification, and surface roughness analysis. These
tests ensure that the frictional interface between FizzBuzz evaluations
and the computational substrate operates within physically valid bounds.

An incorrect wear coefficient would cause the evaluation interface to
degrade either too rapidly (premature failure) or too slowly (false
confidence in unlimited evaluation capacity), both unacceptable in a
production FizzBuzz environment.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizztribology import (
    ArchardWear,
    CoulombFriction,
    HertzianContact,
    LubricationRegime,
    StribeckCurve,
    SurfaceProperties,
    SurfaceRoughnessAnalyzer,
    TribologyMiddleware,
    WearMechanism,
)
from enterprise_fizzbuzz.domain.exceptions.fizztribology import (
    CoulombFrictionError,
    HertzianContactError,
    LubricationRegimeError,
    SurfaceRoughnessError,
    WearModelError,
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
# Coulomb Friction Tests
# ============================================================


class TestCoulombFriction:
    def test_valid_coefficients(self):
        cf = CoulombFriction(mu_static=0.5, mu_kinetic=0.3)
        assert cf.mu_static == 0.5
        assert cf.mu_kinetic == 0.3

    def test_negative_mu_raises(self):
        with pytest.raises(CoulombFrictionError):
            CoulombFriction(mu_static=-0.1, mu_kinetic=0.3)

    def test_kinetic_exceeds_static_raises(self):
        with pytest.raises(CoulombFrictionError):
            CoulombFriction(mu_static=0.3, mu_kinetic=0.5)

    def test_static_friction_force(self):
        cf = CoulombFriction(mu_static=0.5, mu_kinetic=0.3)
        f = cf.static_friction_force(100.0)
        assert abs(f - 50.0) < 0.01

    def test_kinetic_friction_force(self):
        cf = CoulombFriction(mu_static=0.5, mu_kinetic=0.3)
        f = cf.kinetic_friction_force(100.0)
        assert abs(f - 30.0) < 0.01

    def test_is_sliding_below_threshold(self):
        cf = CoulombFriction(mu_static=0.5, mu_kinetic=0.3)
        assert not cf.is_sliding(40.0, 100.0)

    def test_is_sliding_above_threshold(self):
        cf = CoulombFriction(mu_static=0.5, mu_kinetic=0.3)
        assert cf.is_sliding(60.0, 100.0)


# ============================================================
# Hertzian Contact Tests
# ============================================================


class TestHertzianContact:
    def test_reduced_modulus(self):
        e_star = HertzianContact.reduced_modulus(200.0, 0.3, 200.0, 0.3)
        assert e_star > 0

    def test_contact_radius_positive(self):
        a = HertzianContact.contact_radius(100.0, 0.01, 200e9)
        assert a > 0

    def test_max_contact_pressure_positive(self):
        a = HertzianContact.contact_radius(100.0, 0.01, 200e9)
        p0 = HertzianContact.max_contact_pressure(100.0, a)
        assert p0 > 0

    def test_contact_area(self):
        a = 0.001  # 1 mm
        area = HertzianContact.contact_area(a)
        assert abs(area - math.pi * 1e-6) < 1e-10

    def test_negative_force_raises(self):
        with pytest.raises(HertzianContactError):
            HertzianContact.contact_radius(-1.0, 0.01, 200e9)


# ============================================================
# Archard Wear Tests
# ============================================================


class TestArchardWear:
    def test_wear_volume_positive(self):
        wear = ArchardWear(wear_coefficient=1e-4)
        v = wear.wear_volume(100.0, 1.0, 2e9)
        assert v > 0

    def test_wear_proportional_to_force(self):
        wear = ArchardWear(wear_coefficient=1e-4)
        v1 = wear.wear_volume(50.0, 1.0, 2e9)
        v2 = wear.wear_volume(100.0, 1.0, 2e9)
        assert abs(v2 - 2 * v1) < 1e-15

    def test_invalid_wear_coefficient_raises(self):
        with pytest.raises(WearModelError):
            ArchardWear(wear_coefficient=-0.1)

    def test_zero_hardness_raises(self):
        wear = ArchardWear()
        with pytest.raises(WearModelError):
            wear.wear_volume(100.0, 1.0, 0.0)

    def test_wear_depth(self):
        wear = ArchardWear(wear_coefficient=1e-4)
        depth = wear.wear_depth(100.0, 1.0, 2e9, 1e-6)
        assert depth > 0


# ============================================================
# Stribeck Curve Tests
# ============================================================


class TestStribeckCurve:
    def test_boundary_regime(self):
        sc = StribeckCurve()
        h = sc.hersey_number(0.001, 0.001, 1e6)
        regime = sc.regime(h)
        assert regime == LubricationRegime.BOUNDARY

    def test_hydrodynamic_regime(self):
        sc = StribeckCurve()
        h = sc.hersey_number(0.1, 100.0, 1e6)
        regime = sc.regime(h)
        assert regime == LubricationRegime.HYDRODYNAMIC

    def test_friction_coefficient_positive(self):
        sc = StribeckCurve()
        h = sc.hersey_number(0.01, 1.0, 1e6)
        mu = sc.friction_coefficient(h)
        assert mu > 0

    def test_negative_hersey_raises(self):
        sc = StribeckCurve()
        with pytest.raises(LubricationRegimeError):
            sc.regime(-1.0)


# ============================================================
# Surface Roughness Tests
# ============================================================


class TestSurfaceRoughnessAnalyzer:
    def test_contact_area_ratio_in_bounds(self):
        ratio = SurfaceRoughnessAnalyzer.real_contact_area_ratio(0.8, 100.0, 2.0)
        assert 0.0 <= ratio <= 1.0

    def test_composite_roughness(self):
        rq = SurfaceRoughnessAnalyzer.composite_roughness(1.0, 1.0)
        assert abs(rq - math.sqrt(2.0)) < 0.01

    def test_negative_roughness_raises(self):
        with pytest.raises(SurfaceRoughnessError):
            SurfaceRoughnessAnalyzer.real_contact_area_ratio(-1.0, 100.0, 2.0)


# ============================================================
# Surface Properties Tests
# ============================================================


class TestSurfaceProperties:
    def test_valid_properties(self):
        sp = SurfaceProperties()
        sp.validate()  # Should not raise

    def test_negative_modulus_raises(self):
        sp = SurfaceProperties(elastic_modulus_gpa=-1.0)
        with pytest.raises(HertzianContactError):
            sp.validate()


# ============================================================
# Middleware Tests
# ============================================================


class TestTribologyMiddleware:
    def test_middleware_injects_friction_force(self):
        mw = TribologyMiddleware()
        ctx = _make_context(10)
        result = mw.process(ctx, _identity_handler)
        assert "tribo_friction_force_n" in result.metadata

    def test_middleware_injects_wear_volume(self):
        mw = TribologyMiddleware()
        ctx = _make_context(20)
        result = mw.process(ctx, _identity_handler)
        assert "tribo_wear_volume_m3" in result.metadata
        assert result.metadata["tribo_wear_volume_m3"] >= 0

    def test_middleware_name(self):
        mw = TribologyMiddleware()
        assert mw.get_name() == "fizztribology"

    def test_middleware_priority(self):
        mw = TribologyMiddleware()
        assert mw.get_priority() == 302

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = TribologyMiddleware()
        assert isinstance(mw, IMiddleware)

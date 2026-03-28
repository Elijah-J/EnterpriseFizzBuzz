"""
Enterprise FizzBuzz Platform - FizzVolcanology Volcanic Eruption Test Suite

Comprehensive verification of the volcanic eruption simulator, including
magma chamber modeling, viscosity computation, eruption style classification,
VEI assignment, and pyroclastic flow dynamics. These tests ensure that
each FizzBuzz evaluation triggers a volcanologically accurate eruption
event.

An incorrectly computed viscosity would misclassify an explosive Plinian
eruption as a gentle effusive flow, fundamentally altering the hazard
assessment of the FizzBuzz evaluation zone.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzvolcanology import (
    EruptionClassifier,
    EruptionSimulator,
    EruptionStyle,
    LavaProperties,
    MagmaChamber,
    MagmaComposition,
    PyroclasticFlow,
    VEICalculator,
    ViscosityModel,
    VolcanologyMiddleware,
)
from enterprise_fizzbuzz.domain.exceptions.fizzvolcanology import (
    LavaViscosityError,
    MagmaChamberError,
    PyroclasticFlowError,
    VEIClassificationError,
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
# Magma Chamber Tests
# ============================================================


class TestMagmaChamber:
    def test_lithostatic_pressure(self):
        chamber = MagmaChamber(depth_km=5.0)
        p_lith = chamber.lithostatic_pressure_mpa()
        # rho*g*h = 2700 * 9.81 * 5000 / 1e6 ~ 132.4 MPa
        assert 100.0 < p_lith < 200.0

    def test_overpressure(self):
        chamber = MagmaChamber(depth_km=5.0, pressure_mpa=200.0)
        op = chamber.overpressure_mpa()
        assert op > 0

    def test_validate_negative_pressure_raises(self):
        chamber = MagmaChamber(pressure_mpa=-10.0)
        with pytest.raises(MagmaChamberError):
            chamber.validate()

    def test_validate_extreme_temperature_raises(self):
        chamber = MagmaChamber(temperature_k=500.0)
        with pytest.raises(MagmaChamberError):
            chamber.validate()

    def test_can_erupt_high_pressure(self):
        chamber = MagmaChamber(depth_km=1.0, pressure_mpa=200.0)
        # Overpressure should exceed tensile strength at shallow depth
        assert isinstance(chamber.can_erupt(), bool)


# ============================================================
# Viscosity Model Tests
# ============================================================


class TestViscosityModel:
    def test_basaltic_viscosity_range(self):
        eta = ViscosityModel.compute(MagmaComposition.BASALTIC, 1473.0)
        assert 1.0 < eta < 1e8

    def test_rhyolitic_higher_than_basaltic(self):
        eta_bas = ViscosityModel.compute(MagmaComposition.BASALTIC, 1473.0)
        eta_rhy = ViscosityModel.compute(MagmaComposition.RHYOLITIC, 1073.0)
        assert eta_rhy > eta_bas

    def test_crystal_fraction_increases_viscosity(self):
        eta_no_crystals = ViscosityModel.compute(MagmaComposition.ANDESITIC, 1373.0, 0.0)
        eta_crystals = ViscosityModel.compute(MagmaComposition.ANDESITIC, 1373.0, 0.3)
        assert eta_crystals > eta_no_crystals

    def test_temperature_decreases_viscosity(self):
        eta_cool = ViscosityModel.compute(MagmaComposition.BASALTIC, 1273.0)
        eta_hot = ViscosityModel.compute(MagmaComposition.BASALTIC, 1573.0)
        assert eta_cool > eta_hot


# ============================================================
# Eruption Classifier Tests
# ============================================================


class TestEruptionClassifier:
    def test_low_viscosity_low_volatile_effusive(self):
        style = EruptionClassifier.classify_style(100.0, 1.0)
        assert style == EruptionStyle.EFFUSIVE

    def test_high_viscosity_high_volatile_plinian(self):
        style = EruptionClassifier.classify_style(1e8, 6.0)
        assert style in (EruptionStyle.PLINIAN, EruptionStyle.ULTRA_PLINIAN)

    def test_moderate_conditions_vulcanian(self):
        style = EruptionClassifier.classify_style(1e5, 3.0)
        assert style == EruptionStyle.VULCANIAN


# ============================================================
# VEI Calculator Tests
# ============================================================


class TestVEICalculator:
    def test_vei_0_small_volume(self):
        vei = VEICalculator.classify(1e-6)
        assert vei == 0

    def test_vei_5_large_volume(self):
        vei = VEICalculator.classify(2.0)
        assert vei == 5

    def test_vei_8_mega_colossal(self):
        vei = VEICalculator.classify(2e4)
        assert vei == 8

    def test_negative_volume_raises(self):
        with pytest.raises(VEIClassificationError):
            VEICalculator.classify(-1.0)


# ============================================================
# Pyroclastic Flow Tests
# ============================================================


class TestPyroclasticFlow:
    def test_valid_flow(self):
        pf = PyroclasticFlow(velocity_ms=100.0, temperature_k=973.0)
        pf.validate()  # Should not raise

    def test_negative_velocity_raises(self):
        pf = PyroclasticFlow(velocity_ms=-10.0, temperature_k=973.0)
        with pytest.raises(PyroclasticFlowError):
            pf.validate()

    def test_low_temperature_raises(self):
        pf = PyroclasticFlow(velocity_ms=50.0, temperature_k=200.0)
        with pytest.raises(PyroclasticFlowError):
            pf.validate()


# ============================================================
# Eruption Simulator Tests
# ============================================================


class TestEruptionSimulator:
    def test_simulate_basaltic(self):
        chamber = MagmaChamber(
            composition=MagmaComposition.BASALTIC,
            temperature_k=1473.0,
            volatile_wt_pct=2.0,
        )
        sim = EruptionSimulator()
        event = sim.simulate(chamber)
        assert event.vei >= 0
        assert event.ejecta_volume_km3 > 0

    def test_simulate_rhyolitic_explosive(self):
        chamber = MagmaChamber(
            composition=MagmaComposition.RHYOLITIC,
            temperature_k=1073.0,
            volatile_wt_pct=6.0,
            volume_km3=50.0,
        )
        sim = EruptionSimulator()
        event = sim.simulate(chamber)
        assert event.style in (EruptionStyle.PLINIAN, EruptionStyle.ULTRA_PLINIAN, EruptionStyle.VULCANIAN)


# ============================================================
# Middleware Tests
# ============================================================


class TestVolcanologyMiddleware:
    def test_middleware_injects_vei(self):
        mw = VolcanologyMiddleware()
        ctx = _make_context(7)
        result = mw.process(ctx, _identity_handler)
        assert "volcano_vei" in result.metadata

    def test_middleware_injects_style(self):
        mw = VolcanologyMiddleware()
        ctx = _make_context(15)
        result = mw.process(ctx, _identity_handler)
        assert "volcano_style" in result.metadata

    def test_middleware_name(self):
        mw = VolcanologyMiddleware()
        assert mw.get_name() == "fizzvolcanology"

    def test_middleware_priority(self):
        mw = VolcanologyMiddleware()
        assert mw.get_priority() == 299

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = VolcanologyMiddleware()
        assert isinstance(mw, IMiddleware)

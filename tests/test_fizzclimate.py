"""
Enterprise FizzBuzz Platform - FizzClimate Climate Model Test Suite

Comprehensive verification of the climate modeling pipeline, including
radiative forcing computation, greenhouse gas concentration tracking,
carbon cycle simulation, temperature projection, ice sheet dynamics,
and climate feedback analysis. Every FizzBuzz evaluation contributes
to atmospheric CO2 accumulation; an error in the radiative forcing
calculation would underestimate the platform's climate liability,
potentially exposing the organization to ESG compliance violations.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzclimate import (
    BERN_FRACTIONS,
    BERN_TIMESCALES,
    CO2_CURRENT,
    CO2_PER_EVAL,
    CO2_PREINDUSTRIAL,
    CLIMATE_SENSITIVITY,
    GREENLAND_VOLUME_KM3,
    MELT_THRESHOLD_K,
    RF_2XCO2,
    CarbonCycleModel,
    CarbonFlux,
    CarbonReservoir,
    ClimateAnalysis,
    ClimateEngine,
    ClimateMiddleware,
    FeedbackCalculator,
    FeedbackType,
    GasType,
    GHGConcentration,
    IceSheet,
    IceSheetModel,
    IceSheetState,
    RadiativeForcing,
    RadiativeForcingCalculator,
    TemperatureModel,
    TemperatureState,
)
from enterprise_fizzbuzz.domain.exceptions.fizzclimate import (
    CarbonCycleError,
    ClimateMiddlewareError,
    FeedbackLoopError,
    FizzClimateError,
    GreenhouseGasError,
    IceSheetError,
    RadiativeForcingError,
    TemperatureProjectionError,
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
# Radiative Forcing Tests
# ===========================================================================


class TestRadiativeForcingCalculator:

    def test_preindustrial_zero_forcing(self):
        calc = RadiativeForcingCalculator()
        rf = calc.compute_co2_forcing(CO2_PREINDUSTRIAL)
        assert abs(rf.forcing_wm2) < 1e-10

    def test_doubled_co2_forcing(self):
        calc = RadiativeForcingCalculator()
        rf = calc.compute_co2_forcing(2 * CO2_PREINDUSTRIAL)
        assert abs(rf.forcing_wm2 - 5.35 * math.log(2.0)) < 0.01

    def test_current_co2_positive_forcing(self):
        calc = RadiativeForcingCalculator()
        rf = calc.compute_co2_forcing(CO2_CURRENT)
        assert rf.forcing_wm2 > 0

    def test_zero_co2_raises(self):
        calc = RadiativeForcingCalculator()
        with pytest.raises(GreenhouseGasError):
            calc.compute_co2_forcing(0.0)

    def test_ch4_forcing_positive(self):
        calc = RadiativeForcingCalculator()
        rf = calc.compute_ch4_forcing(1900.0)
        assert rf.forcing_wm2 > 0

    def test_total_forcing_sums(self):
        calc = RadiativeForcingCalculator()
        f1 = RadiativeForcing("CO2", 2.0)
        f2 = RadiativeForcing("CH4", 0.5)
        total = calc.compute_total([f1, f2])
        assert abs(total - 2.5) < 1e-10


# ===========================================================================
# Carbon Cycle Tests
# ===========================================================================


class TestCarbonCycleModel:

    def test_airborne_fraction_at_zero(self):
        model = CarbonCycleModel()
        fraction = model.compute_airborne_fraction(0.0)
        assert abs(fraction - 1.0) < 1e-6  # All fractions sum to 1

    def test_airborne_fraction_decays(self):
        model = CarbonCycleModel()
        f0 = model.compute_airborne_fraction(0.0)
        f100 = model.compute_airborne_fraction(100.0)
        assert f100 < f0

    def test_emit_increases_cumulative(self):
        model = CarbonCycleModel()
        model.emit(1.0)
        assert model.cumulative_emissions == 1.0

    def test_emit_returns_positive_ppm(self):
        model = CarbonCycleModel()
        delta = model.emit(1.0)
        assert delta > 0

    def test_carbon_fluxes_positive(self):
        model = CarbonCycleModel()
        fluxes = model.compute_fluxes(CO2_CURRENT)
        assert all(f.flux_gtc_per_year > 0 for f in fluxes)


# ===========================================================================
# Temperature Model Tests
# ===========================================================================


class TestTemperatureModel:

    def test_projection_length(self):
        model = TemperatureModel()
        traj = model.project(2.0, years=50)
        assert len(traj) == 50

    def test_warming_with_positive_forcing(self):
        model = TemperatureModel()
        traj = model.project(4.0, years=100, initial_anomaly_k=0.0)
        assert traj[-1].surface_anomaly_k > 0

    def test_year_increments(self):
        model = TemperatureModel()
        traj = model.project(2.0, years=10)
        assert traj[0].year == 2024
        assert traj[-1].year == 2033


# ===========================================================================
# Ice Sheet Tests
# ===========================================================================


class TestIceSheetModel:

    def test_no_melt_below_threshold(self):
        model = IceSheetModel()
        state = model.compute_state(IceSheet.GREENLAND, 1.0)
        assert state.mass_loss_rate_gt_yr == 0.0

    def test_melt_above_threshold(self):
        model = IceSheetModel()
        state = model.compute_state(IceSheet.GREENLAND, 3.0)
        assert state.mass_loss_rate_gt_yr > 0

    def test_sea_level_contribution_positive(self):
        model = IceSheetModel()
        state = model.compute_state(IceSheet.GREENLAND, 3.0)
        assert state.sea_level_contribution_mm > 0

    def test_antarctic_less_sensitive(self):
        model = IceSheetModel()
        greenland = model.compute_state(IceSheet.GREENLAND, 3.0)
        antarctic = model.compute_state(IceSheet.ANTARCTIC, 3.0)
        assert greenland.mass_loss_rate_gt_yr > antarctic.mass_loss_rate_gt_yr


# ===========================================================================
# Feedback Calculator Tests
# ===========================================================================


class TestFeedbackCalculator:

    def test_feedback_factor_less_than_one(self):
        calc = FeedbackCalculator()
        f = calc.compute_total_feedback()
        assert f < 1.0

    def test_stability_check_passes(self):
        calc = FeedbackCalculator()
        assert calc.validate_stability()


# ===========================================================================
# Engine Integration Tests
# ===========================================================================


class TestClimateEngine:

    def test_analyze_plain_number(self):
        engine = ClimateEngine()
        result = engine.analyze_number(7, False, False)
        assert result.co2_concentration.concentration_ppm >= CO2_CURRENT
        assert result.total_forcing_wm2 > 0

    def test_fizzbuzz_emits_more(self):
        engine1 = ClimateEngine()
        engine2 = ClimateEngine()
        r1 = engine1.analyze_number(7, False, False)
        r2 = engine2.analyze_number(15, True, True)
        assert r2.cumulative_emissions_gtc > r1.cumulative_emissions_gtc

    def test_analysis_count(self):
        engine = ClimateEngine()
        engine.analyze_number(1, False, False)
        engine.analyze_number(2, False, False)
        assert engine.analysis_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================


class TestClimateMiddleware:

    def test_middleware_attaches_metadata(self):
        mw = ClimateMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "climate" in result.metadata
        assert "co2_ppm" in result.metadata["climate"]

    def test_middleware_cumulative_tracking(self):
        mw = ClimateMiddleware()
        ctx1 = _make_context(3, "Fizz", is_fizz=True)
        mw.process(ctx1, lambda c: c)
        ctx2 = _make_context(5, "Buzz", is_buzz=True)
        result = mw.process(ctx2, lambda c: c)
        assert result.metadata["climate"]["cumulative_emissions_gtc"] > 0


# ===========================================================================
# Exception Tests
# ===========================================================================


class TestExceptions:

    def test_base_exception(self):
        err = FizzClimateError("test")
        assert "EFP-CL00" in str(err.error_code)

    def test_greenhouse_gas_error_fields(self):
        err = GreenhouseGasError("CO2", -10.0, "negative concentration")
        assert err.gas == "CO2"
        assert err.concentration_ppm == -10.0

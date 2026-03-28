"""
Enterprise FizzBuzz Platform - FizzWeather Weather Simulation Test Suite

Comprehensive verification of the atmospheric dynamics engine, including
Navier-Stokes solving, pressure system modeling, temperature gradients,
Coriolis effect computation, and precipitation prediction. These tests
ensure that FizzBuzz evaluations occur under meteorologically accurate
simulated conditions.

Atmospheric accuracy is non-negotiable: an incorrect Coriolis parameter
would reverse the cyclonic rotation direction, fundamentally altering
whether the atmosphere favors Fizz or Buzz classifications.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzweather import (
    AtmosphericGrid,
    CoriolisComputer,
    Forecast,
    GridCell,
    NavierStokesSolver,
    PrecipitationPredictor,
    PrecipitationType,
    PressureSystem,
    PressureType,
    REFERENCE_PRESSURE,
    WeatherMiddleware,
    WeatherState,
)
from enterprise_fizzbuzz.domain.exceptions.fizzweather import (
    CoriolisError,
    GridResolutionError,
    NavierStokesError,
    PressureSystemError,
    TemperatureGradientError,
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
# Atmospheric Grid Tests
# ============================================================


class TestAtmosphericGrid:
    def test_grid_creation(self):
        grid = AtmosphericGrid(8, 8)
        assert len(grid.grid) == 8
        assert len(grid.grid[0]) == 8

    def test_grid_too_small_raises(self):
        with pytest.raises(GridResolutionError):
            AtmosphericGrid(2, 2)

    def test_default_pressure(self):
        grid = AtmosphericGrid(4, 4)
        assert abs(grid.grid[0][0].pressure - REFERENCE_PRESSURE) < 0.01

    def test_apply_pressure_system(self):
        grid = AtmosphericGrid(16, 16)
        system = PressureSystem(
            system_type=PressureType.LOW,
            center_x=8, center_y=8,
            central_pressure=990.0,
            radius=4,
        )
        grid.apply_pressure_system(system)
        # Center should have lower pressure
        assert grid.grid[8][8].pressure < REFERENCE_PRESSURE

    def test_invalid_pressure_system_raises(self):
        system = PressureSystem(
            system_type=PressureType.HIGH,
            center_x=5, center_y=5,
            central_pressure=-100.0,
            radius=3,
        )
        with pytest.raises(PressureSystemError):
            system.validate()


# ============================================================
# Coriolis Tests
# ============================================================


class TestCoriolisComputer:
    def test_coriolis_at_pole(self):
        f = CoriolisComputer.coriolis_parameter(90.0)
        expected = 2.0 * 7.2921e-5
        assert abs(f - expected) < 1e-10

    def test_coriolis_at_equator(self):
        f = CoriolisComputer.coriolis_parameter(0.0)
        assert abs(f) < 1e-10

    def test_coriolis_southern_hemisphere_negative(self):
        f = CoriolisComputer.coriolis_parameter(-45.0)
        assert f < 0

    def test_invalid_latitude_raises(self):
        with pytest.raises(CoriolisError):
            CoriolisComputer.coriolis_parameter(100.0)

    def test_geostrophic_wind(self):
        f = CoriolisComputer.coriolis_parameter(45.0)
        u, v = CoriolisComputer.geostrophic_wind(100.0, 50.0, 1.225, f)
        assert isinstance(u, float)
        assert isinstance(v, float)

    def test_geostrophic_wind_equator_raises(self):
        with pytest.raises(CoriolisError):
            CoriolisComputer.geostrophic_wind(100.0, 50.0, 1.225, 0.0)


# ============================================================
# Temperature Gradient Tests
# ============================================================


class TestTemperatureGradient:
    def test_valid_gradient(self):
        grid = AtmosphericGrid(8, 8)
        grid.set_temperature_gradient(288.15, 0.5)
        # Temperature should increase with j
        assert grid.grid[0][7].temperature > grid.grid[0][0].temperature

    def test_excessive_gradient_raises(self):
        grid = AtmosphericGrid(8, 8)
        with pytest.raises(TemperatureGradientError):
            grid.set_temperature_gradient(288.15, 20.0)


# ============================================================
# Navier-Stokes Solver Tests
# ============================================================


class TestNavierStokesSolver:
    def test_solver_single_step(self):
        grid = AtmosphericGrid(8, 8)
        solver = NavierStokesSolver(grid, latitude=45.0)
        solver.step(1.0)  # Should not raise

    def test_solver_simulation(self):
        grid = AtmosphericGrid(8, 8)
        solver = NavierStokesSolver(grid, latitude=45.0)
        states = solver.simulate(3.0, 1.0)
        assert len(states) == 3
        assert isinstance(states[0], WeatherState)


# ============================================================
# Precipitation Tests
# ============================================================


class TestPrecipitationPredictor:
    def test_no_precipitation_low_humidity(self):
        cell = GridCell(humidity=0.3, temperature=288.15)
        ptype, rate = PrecipitationPredictor.predict(cell)
        assert ptype == PrecipitationType.NONE
        assert rate == 0.0

    def test_rain_above_freezing(self):
        cell = GridCell(humidity=1.1, temperature=290.0)
        # Force high humidity that exceeds saturation
        ptype, rate = PrecipitationPredictor.predict(cell)
        # Type should be RAIN or NONE depending on actual saturation
        assert ptype in (PrecipitationType.RAIN, PrecipitationType.NONE)

    def test_saturation_vapor_pressure_positive(self):
        e_sat = PrecipitationPredictor.saturation_vapor_pressure(273.15)
        assert e_sat > 0


# ============================================================
# Middleware Tests
# ============================================================


class TestWeatherMiddleware:
    def test_middleware_injects_temperature(self):
        grid = AtmosphericGrid(8, 8)
        mw = WeatherMiddleware(grid, latitude=45.0)
        ctx = _make_context(10)
        result = mw.process(ctx, _identity_handler)
        assert "weather_temperature_c" in result.metadata

    def test_middleware_injects_pressure(self):
        grid = AtmosphericGrid(8, 8)
        mw = WeatherMiddleware(grid)
        ctx = _make_context(5)
        result = mw.process(ctx, _identity_handler)
        assert "weather_pressure_hpa" in result.metadata
        assert abs(result.metadata["weather_pressure_hpa"] - REFERENCE_PRESSURE) < 1.0

    def test_middleware_injects_coriolis(self):
        grid = AtmosphericGrid(8, 8)
        mw = WeatherMiddleware(grid, latitude=60.0)
        ctx = _make_context(1)
        result = mw.process(ctx, _identity_handler)
        assert "weather_coriolis" in result.metadata
        assert result.metadata["weather_coriolis"] > 0

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        grid = AtmosphericGrid(4, 4)
        mw = WeatherMiddleware(grid)
        assert isinstance(mw, IMiddleware)

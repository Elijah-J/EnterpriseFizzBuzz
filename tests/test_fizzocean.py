"""
Enterprise FizzBuzz Platform - FizzOcean Ocean Current Simulator Test Suite

Comprehensive verification of the ocean circulation model, from individual
cell thermodynamics through the complete thermohaline-ENSO coupled system.
Incorrect ocean state could misattribute a Fizz trade wind event to a
Buzz freshwater event, producing an oceanographic classification discrepancy
that would propagate through all downstream geophysical diagnostics.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzocean import (
    AIR_DENSITY,
    DEFAULT_DT,
    DEFAULT_NX,
    DEFAULT_NY,
    DEFAULT_NZ,
    DRAG_COEFFICIENT,
    EARTH_ROTATION_RATE,
    EKMAN_DEPTH_SCALE,
    ENSO_COUPLING,
    ENSO_DAMPING,
    ENSO_DELAY_STEPS,
    ENSO_MAX_ANOMALY,
    GRAVITY,
    HALINE_CONTRACTION,
    MAX_PHYSICAL_SALINITY,
    MAX_PHYSICAL_VELOCITY,
    MIN_PHYSICAL_SALINITY,
    THERMAL_EXPANSION,
    WATER_DENSITY_REF,
    CurrentType,
    ENSOOscillator,
    ENSOState,
    OceanCell,
    OceanGrid,
    OceanMiddleware,
    OceanSimulator,
    ThermohalineSolver,
    UpwellingDetector,
    WindForcing,
    buoyancy_frequency,
    classify_current,
    compute_wind_stress,
    coriolis_parameter,
    density_from_ts,
    ekman_transport,
)
from enterprise_fizzbuzz.domain.exceptions.fizzocean import (
    CurrentVelocityError,
    EkmanTransportError,
    ENSOError,
    FizzOceanError,
    OceanMiddlewareError,
    SalinityError,
    ThermohalineError,
    UpwellingError,
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
    rules = []
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=rules)
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


# ===========================================================================
# OceanCell Tests
# ===========================================================================

class TestOceanCell:
    """Verification of ocean cell thermodynamic properties."""

    def test_default_density(self):
        cell = OceanCell()
        assert cell.density == pytest.approx(WATER_DENSITY_REF, rel=1e-3)

    def test_warm_water_less_dense(self):
        warm = OceanCell(temperature=25.0, salinity=35.0)
        cold = OceanCell(temperature=5.0, salinity=35.0)
        assert warm.density < cold.density

    def test_salty_water_more_dense(self):
        salty = OceanCell(temperature=15.0, salinity=38.0)
        fresh = OceanCell(temperature=15.0, salinity=32.0)
        assert salty.density > fresh.density

    def test_speed_zero_at_rest(self):
        cell = OceanCell()
        assert cell.speed == pytest.approx(0.0)

    def test_speed_nonzero(self):
        cell = OceanCell(u=0.3, v=0.4)
        assert cell.speed == pytest.approx(0.5)


# ===========================================================================
# Coriolis and Ekman Tests
# ===========================================================================

class TestCoriolisAndEkman:
    """Verification of Coriolis parameter and Ekman transport."""

    def test_coriolis_at_pole(self):
        f = coriolis_parameter(90.0)
        assert f == pytest.approx(2.0 * EARTH_ROTATION_RATE, rel=1e-6)

    def test_coriolis_at_equator(self):
        f = coriolis_parameter(0.0)
        assert abs(f) < 1e-12

    def test_coriolis_southern_hemisphere_negative(self):
        f = coriolis_parameter(-45.0)
        assert f < 0.0

    def test_ekman_transport_equatorial_singularity(self):
        wind = WindForcing(tau_x=0.1, tau_y=0.0)
        with pytest.raises(EkmanTransportError):
            ekman_transport(wind, 0.0)

    def test_ekman_transport_midlatitude(self):
        wind = WindForcing(tau_x=0.1, tau_y=0.0)
        mx, my = ekman_transport(wind, 45.0)
        assert isinstance(mx, float)
        assert isinstance(my, float)

    def test_wind_stress_magnitude(self):
        stress = compute_wind_stress(10.0, 0.0)
        expected = AIR_DENSITY * DRAG_COEFFICIENT * 10.0 * 10.0
        assert stress.tau_x == pytest.approx(expected, rel=1e-6)


# ===========================================================================
# Ocean Grid Tests
# ===========================================================================

class TestOceanGrid:
    """Verification of the discretized ocean basin."""

    def test_grid_dimensions(self):
        grid = OceanGrid(nx=10, ny=5, nz=3)
        assert grid.total_cells() == 150

    def test_latitude_range(self):
        grid = OceanGrid(ny=10)
        assert grid.latitude_at(0) == pytest.approx(-45.0)
        assert grid.latitude_at(9) == pytest.approx(45.0)

    def test_mean_sst_positive(self):
        grid = OceanGrid()
        sst = grid.mean_surface_temperature()
        assert sst > 0.0

    def test_surface_cell_retrieval(self):
        grid = OceanGrid()
        cell = grid.get_surface_cell(0, 0)
        assert isinstance(cell, OceanCell)


# ===========================================================================
# ENSO Oscillator Tests
# ===========================================================================

class TestENSOOscillator:
    """Verification of the ENSO delayed oscillator."""

    def test_initial_state_neutral(self):
        enso = ENSOOscillator()
        assert enso.state.phase == "neutral"
        assert enso.state.thermocline_anomaly == 0.0

    def test_positive_forcing_increases_anomaly(self):
        enso = ENSOOscillator()
        enso.step(external_forcing=10.0)
        assert enso.state.thermocline_anomaly > 0.0

    def test_el_nino_phase_detection(self):
        enso = ENSOOscillator(coupling=0.01, damping=0.001)
        for _ in range(5):
            enso.step(external_forcing=10.0)
        assert enso.state.phase == "el_nino"

    def test_step_counter_increments(self):
        enso = ENSOOscillator()
        enso.step()
        enso.step()
        assert enso.state.step == 2


# ===========================================================================
# Thermohaline Solver Tests
# ===========================================================================

class TestThermohalineSolver:
    """Verification of the iterative thermohaline solver."""

    def test_solver_converges_on_small_grid(self):
        grid = OceanGrid(nx=5, ny=5, nz=2)
        solver = ThermohalineSolver(max_iterations=50, tolerance=1.0)
        iterations = solver.solve(grid, dt=100.0)
        assert iterations <= 50

    def test_solver_raises_on_non_convergence(self):
        grid = OceanGrid(nx=5, ny=5, nz=2)
        solver = ThermohalineSolver(max_iterations=1, tolerance=1e-30)
        with pytest.raises(ThermohalineError):
            solver.solve(grid, dt=0.001)


# ===========================================================================
# Ocean Simulator Tests
# ===========================================================================

class TestOceanSimulator:
    """Verification of the integrated ocean simulator."""

    def test_step_returns_diagnostics(self):
        sim = OceanSimulator(nx=5, ny=5, nz=2)
        diag = sim.step(3, is_fizz=True, is_buzz=False)
        assert "mean_sst" in diag
        assert "enso_phase" in diag

    def test_fizz_forcing_applied(self):
        sim = OceanSimulator(nx=5, ny=5, nz=2)
        sim.step(3, is_fizz=True, is_buzz=False)
        assert sim._total_fizz_forcing == 1

    def test_buzz_forcing_applied(self):
        sim = OceanSimulator(nx=5, ny=5, nz=2)
        sim.step(5, is_fizz=False, is_buzz=True)
        assert sim._total_buzz_forcing == 1

    def test_fizzbuzz_forcing_applied(self):
        sim = OceanSimulator(nx=5, ny=5, nz=2)
        sim.step(15, is_fizz=True, is_buzz=True)
        assert sim._total_fizzbuzz_forcing == 1

    def test_step_count_increments(self):
        sim = OceanSimulator(nx=5, ny=5, nz=2)
        sim.step(1, False, False)
        sim.step(2, False, False)
        assert sim.step_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestOceanMiddleware:
    """Verification of the FizzOcean middleware integration."""

    def test_middleware_name(self):
        mw = OceanMiddleware(nx=5, ny=5, nz=2)
        assert mw.get_name() == "OceanMiddleware"

    def test_middleware_priority(self):
        mw = OceanMiddleware()
        assert mw.get_priority() == 286

    def test_middleware_attaches_metadata(self):
        mw = OceanMiddleware(nx=5, ny=5, nz=2)
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "ocean_sst" in result.metadata

    def test_middleware_increments_evaluations(self):
        mw = OceanMiddleware(nx=5, ny=5, nz=2)
        ctx = _make_context(1, "1")
        mw.process(ctx, lambda c: c)
        assert mw.evaluations == 1


# ===========================================================================
# Utility Tests
# ===========================================================================

class TestUtilities:
    """Verification of ocean physics utility functions."""

    def test_density_from_ts_reference(self):
        rho = density_from_ts(15.0, 35.0)
        assert rho == pytest.approx(WATER_DENSITY_REF, rel=1e-6)

    def test_buoyancy_frequency_stable(self):
        n = buoyancy_frequency(1025.0, 1027.0, 100.0)
        assert n > 0.0

    def test_buoyancy_frequency_unstable(self):
        n = buoyancy_frequency(1027.0, 1025.0, 100.0)
        assert n == 0.0

    def test_classify_current_deep(self):
        cell = OceanCell(depth=500.0)
        ct = classify_current(cell, 30.0, 10, 20)
        assert ct == CurrentType.DEEP

    def test_classify_current_equatorial(self):
        cell = OceanCell(depth=10.0)
        ct = classify_current(cell, 2.0, 10, 20)
        assert ct == CurrentType.EQUATORIAL

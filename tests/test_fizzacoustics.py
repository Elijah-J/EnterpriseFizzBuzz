"""
Enterprise FizzBuzz Platform - FizzAcoustics Acoustic Propagation Test Suite

Comprehensive verification of the acoustic propagation engine, including
sound speed computation, impedance matching, room acoustics, Sabine
reverberation, standing wave analysis, and Helmholtz resonance. These
tests ensure that the acoustic environment of each FizzBuzz evaluation
is physically accurate.

An incorrect Sabine constant would produce reverberation times that
are inconsistent with the room dimensions and absorption, causing
FizzBuzz evaluations to echo for impossibly long or short durations.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzacoustics import (
    AcousticImpedance,
    AcousticsMiddleware,
    HelmholtzResonator,
    RoomGeometry,
    SabineReverb,
    SoundSpeed,
    SPLCalculator,
    StandingWaveCalculator,
    SurfaceMaterial,
)
from enterprise_fizzbuzz.domain.exceptions.fizzacoustics import (
    HelmholtzResonanceError,
    ImpedanceMismatchError,
    RoomAcousticsError,
    SoundPropagationError,
    StandingWaveError,
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
# Sound Speed Tests
# ============================================================


class TestSoundSpeed:
    def test_speed_at_0c(self):
        c = SoundSpeed.in_air(0.0)
        assert abs(c - 331.3) < 0.1

    def test_speed_at_20c(self):
        c = SoundSpeed.in_air(20.0)
        # ~343 m/s at 20C
        assert 340.0 < c < 346.0

    def test_speed_increases_with_temperature(self):
        c_cold = SoundSpeed.in_air(0.0)
        c_warm = SoundSpeed.in_air(30.0)
        assert c_warm > c_cold

    def test_wavelength_computation(self):
        c = SoundSpeed.in_air(20.0)
        lam = SoundSpeed.wavelength(440.0, c)
        assert abs(lam - c / 440.0) < 0.001

    def test_negative_frequency_raises(self):
        with pytest.raises(SoundPropagationError):
            SoundSpeed.wavelength(-100.0, 343.0)


# ============================================================
# Acoustic Impedance Tests
# ============================================================


class TestAcousticImpedance:
    def test_air_impedance(self):
        z = AcousticImpedance.compute(1.225, 343.0)
        assert 400.0 < z < 450.0

    def test_reflection_at_equal_impedance(self):
        r = AcousticImpedance.reflection_coefficient(413.0, 413.0)
        assert abs(r) < 0.001

    def test_total_reflection_at_zero_impedance_raises(self):
        with pytest.raises(ImpedanceMismatchError):
            AcousticImpedance.reflection_coefficient(0.0, 413.0)

    def test_transmission_coefficient(self):
        t = AcousticImpedance.transmission_coefficient(413.0, 413.0)
        assert abs(t - 1.0) < 0.001

    def test_transmitted_intensity_at_matched_impedance(self):
        ratio = AcousticImpedance.transmitted_intensity_ratio(413.0, 413.0)
        assert abs(ratio - 1.0) < 0.001


# ============================================================
# Room Geometry Tests
# ============================================================


class TestRoomGeometry:
    def test_room_volume(self):
        room = RoomGeometry(length=10.0, width=8.0, height=3.0)
        assert abs(room.volume() - 240.0) < 0.01

    def test_total_surface_area(self):
        room = RoomGeometry(length=10.0, width=8.0, height=3.0)
        expected = 2 * 3 * (10 + 8) + 2 * 10 * 8
        assert abs(room.total_surface_area() - expected) < 0.01

    def test_total_absorption_positive(self):
        room = RoomGeometry()
        assert room.total_absorption() > 0

    def test_invalid_dimensions_raises(self):
        room = RoomGeometry(length=-1.0)
        with pytest.raises(RoomAcousticsError):
            room.validate()


# ============================================================
# Sabine Reverberation Tests
# ============================================================


class TestSabineReverb:
    def test_rt60_positive(self):
        room = RoomGeometry()
        rt60 = SabineReverb.rt60(room)
        assert rt60 > 0

    def test_more_absorption_shorter_rt60(self):
        room_hard = RoomGeometry(
            wall_material=SurfaceMaterial.CONCRETE,
            floor_material=SurfaceMaterial.CONCRETE,
            ceiling_material=SurfaceMaterial.CONCRETE,
        )
        room_soft = RoomGeometry(
            wall_material=SurfaceMaterial.CURTAIN,
            floor_material=SurfaceMaterial.CARPET,
            ceiling_material=SurfaceMaterial.ACOUSTIC_TILE,
        )
        assert SabineReverb.rt60(room_soft) < SabineReverb.rt60(room_hard)

    def test_critical_distance_positive(self):
        room = RoomGeometry()
        dc = SabineReverb.critical_distance(room)
        assert dc > 0


# ============================================================
# Standing Wave Tests
# ============================================================


class TestStandingWaveCalculator:
    def test_fundamental_mode(self):
        f = StandingWaveCalculator.closed_closed(1, 1.0, 343.0)
        assert abs(f - 171.5) < 0.1

    def test_second_harmonic(self):
        f1 = StandingWaveCalculator.closed_closed(1, 1.0, 343.0)
        f2 = StandingWaveCalculator.closed_closed(2, 1.0, 343.0)
        assert abs(f2 - 2 * f1) < 0.1

    def test_invalid_mode_raises(self):
        with pytest.raises(StandingWaveError):
            StandingWaveCalculator.closed_closed(0, 1.0, 343.0)

    def test_zero_length_raises(self):
        with pytest.raises(StandingWaveError):
            StandingWaveCalculator.closed_closed(1, 0.0, 343.0)

    def test_room_modes_non_empty(self):
        room = RoomGeometry()
        modes = StandingWaveCalculator.room_modes(room, 343.0)
        assert len(modes) > 0


# ============================================================
# Helmholtz Resonator Tests
# ============================================================


class TestHelmholtzResonator:
    def test_resonance_frequency_positive(self):
        f = HelmholtzResonator.resonance_frequency(0.001, 0.0001, 0.01, 343.0)
        assert f > 0

    def test_larger_volume_lower_frequency(self):
        f_small = HelmholtzResonator.resonance_frequency(0.001, 0.0001, 0.01, 343.0)
        f_large = HelmholtzResonator.resonance_frequency(0.01, 0.0001, 0.01, 343.0)
        assert f_large < f_small

    def test_zero_volume_raises(self):
        with pytest.raises(HelmholtzResonanceError):
            HelmholtzResonator.resonance_frequency(0.0, 0.0001, 0.01, 343.0)


# ============================================================
# SPL Calculator Tests
# ============================================================


class TestSPLCalculator:
    def test_spl_at_threshold(self):
        spl = SPLCalculator.from_pressure(2e-5)
        assert abs(spl - 0.0) < 0.01

    def test_inverse_square_law(self):
        spl_1m = 90.0
        spl_2m = SPLCalculator.inverse_square_law(spl_1m, 1.0, 2.0)
        assert abs(spl_2m - (90.0 - 6.02)) < 0.1


# ============================================================
# Middleware Tests
# ============================================================


class TestAcousticsMiddleware:
    def test_middleware_injects_rt60(self):
        mw = AcousticsMiddleware()
        ctx = _make_context(10)
        result = mw.process(ctx, _identity_handler)
        assert "acoustic_rt60_s" in result.metadata
        assert result.metadata["acoustic_rt60_s"] > 0

    def test_middleware_injects_speed(self):
        mw = AcousticsMiddleware(temperature_celsius=25.0)
        ctx = _make_context(5)
        result = mw.process(ctx, _identity_handler)
        assert "acoustic_speed_ms" in result.metadata

    def test_middleware_name(self):
        mw = AcousticsMiddleware()
        assert mw.get_name() == "fizzacoustics"

    def test_middleware_priority(self):
        mw = AcousticsMiddleware()
        assert mw.get_priority() == 301

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = AcousticsMiddleware()
        assert isinstance(mw, IMiddleware)

"""
Enterprise FizzBuzz Platform - FizzSeismology Seismic Wave Propagator Test Suite

Comprehensive verification of seismic wave propagation, ray tracing,
magnitude computation, and focal mechanism determination. A miscalculated
P-wave travel time could delay the delivery of a FizzBuzz classification
to a remote station, violating the platform's seismic latency SLA.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzseismology import (
    EARTH_RADIUS,
    MAX_MAGNITUDE,
    MIN_MAGNITUDE,
    MOMENT_CONSTANT,
    P_WAVE_SURFACE,
    RICHTER_LOG_A0,
    S_WAVE_SURFACE,
    VP_VS_RATIO,
    FocalMechanism,
    MagnitudeScale,
    RaySegment,
    SeismicEvent,
    SeismicEventGenerator,
    SeismicRayTracer,
    SeismologyMiddleware,
    TravelTimeEntry,
    TravelTimeTable,
    VelocityLayer,
    WaveType,
    build_iasp91_model,
    generate_focal_mechanism,
    moment_magnitude,
    richter_magnitude,
)
from enterprise_fizzbuzz.domain.exceptions.fizzseismology import (
    FizzSeismologyError,
    FocalMechanismError,
    MagnitudeError,
    RayTracingError,
    SeismologyMiddlewareError,
    TravelTimeError,
    VelocityModelError,
    WaveformError,
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
# Velocity Model Tests
# ===========================================================================

class TestVelocityModel:
    """Verification of the IASP91 velocity model."""

    def test_iasp91_has_eight_layers(self):
        model = build_iasp91_model()
        assert len(model) == 8

    def test_all_layers_valid(self):
        model = build_iasp91_model()
        for layer in model:
            assert layer.validate()

    def test_velocity_increases_with_depth(self):
        model = build_iasp91_model()
        # P-wave velocity generally increases from crust to lower mantle
        assert model[0].vp < model[5].vp

    def test_invalid_layer_raises(self):
        bad_layer = VelocityLayer(0.0, -1.0, 3.0, 2.7, "Bad")
        assert not bad_layer.validate()


# ===========================================================================
# Ray Tracing Tests
# ===========================================================================

class TestSeismicRayTracer:
    """Verification of seismic ray tracing through the velocity model."""

    def test_ray_tracer_produces_segments(self):
        tracer = SeismicRayTracer()
        segments = tracer.trace_ray(10.0, math.radians(30.0))
        assert len(segments) > 0

    def test_all_segments_have_positive_travel_time(self):
        tracer = SeismicRayTracer()
        segments = tracer.trace_ray(10.0, math.radians(45.0))
        for seg in segments:
            assert seg.travel_time > 0.0

    def test_ray_tracer_rejects_bad_model(self):
        bad_model = [VelocityLayer(0.0, 0.0, 0.0, 0.0, "Zero")]
        with pytest.raises(VelocityModelError):
            SeismicRayTracer(bad_model)

    def test_ray_type_preserved(self):
        tracer = SeismicRayTracer()
        segments = tracer.trace_ray(10.0, math.radians(30.0), WaveType.S_WAVE)
        for seg in segments:
            assert seg.wave_type == WaveType.S_WAVE


# ===========================================================================
# Travel Time Table Tests
# ===========================================================================

class TestTravelTimeTable:
    """Verification of pre-computed travel time tables."""

    def test_table_has_entries(self):
        table = TravelTimeTable()
        table.compute_table(source_depth=10.0, max_distance=30.0, step=10.0)
        assert "P" in table.phases
        assert "S" in table.phases

    def test_lookup_returns_entry(self):
        table = TravelTimeTable()
        table.compute_table(source_depth=10.0, max_distance=30.0, step=10.0)
        entry = table.lookup("P", 10.0)
        # May be None if no ray reached that distance, but the method should not crash
        assert entry is None or isinstance(entry, TravelTimeEntry)


# ===========================================================================
# Magnitude Tests
# ===========================================================================

class TestMagnitude:
    """Verification of earthquake magnitude computation."""

    def test_richter_positive_amplitude(self):
        ml = richter_magnitude(10.0, 100.0)
        assert MIN_MAGNITUDE <= ml <= MAX_MAGNITUDE

    def test_richter_zero_amplitude_raises(self):
        with pytest.raises(MagnitudeError):
            richter_magnitude(0.0, 100.0)

    def test_moment_magnitude_positive(self):
        mw = moment_magnitude(1.0e18)
        assert isinstance(mw, float)
        assert MIN_MAGNITUDE <= mw <= MAX_MAGNITUDE

    def test_moment_magnitude_zero_raises(self):
        with pytest.raises(MagnitudeError):
            moment_magnitude(0.0)

    def test_larger_moment_gives_larger_magnitude(self):
        mw_small = moment_magnitude(1.0e15)
        mw_large = moment_magnitude(1.0e20)
        assert mw_large > mw_small


# ===========================================================================
# Focal Mechanism Tests
# ===========================================================================

class TestFocalMechanism:
    """Verification of focal mechanism determination."""

    def test_fizzbuzz_produces_strike_slip(self):
        fm = generate_focal_mechanism(15, is_fizz=True, is_buzz=True)
        assert fm.mechanism_type == "strike-slip"

    def test_fizz_produces_normal(self):
        fm = generate_focal_mechanism(3, is_fizz=True, is_buzz=False)
        assert fm.mechanism_type == "normal"

    def test_buzz_produces_reverse(self):
        fm = generate_focal_mechanism(5, is_fizz=False, is_buzz=True)
        assert fm.mechanism_type == "reverse"

    def test_dip_within_range(self):
        fm = generate_focal_mechanism(42, is_fizz=False, is_buzz=False)
        assert 0.0 <= fm.dip <= 90.0


# ===========================================================================
# Event Generator Tests
# ===========================================================================

class TestSeismicEventGenerator:
    """Verification of the seismic event generation pipeline."""

    def test_event_has_magnitude(self):
        gen = SeismicEventGenerator()
        event = gen.generate_event(3, is_fizz=True, is_buzz=False)
        assert event.magnitude_ml > 0.0

    def test_fizzbuzz_generates_large_magnitude(self):
        gen = SeismicEventGenerator()
        event = gen.generate_event(15, is_fizz=True, is_buzz=True)
        assert event.magnitude_ml >= 6.0

    def test_catalog_accumulates(self):
        gen = SeismicEventGenerator()
        gen.generate_event(1, False, False)
        gen.generate_event(3, True, False)
        assert gen.total_events == 2

    def test_max_magnitude_correct(self):
        gen = SeismicEventGenerator()
        gen.generate_event(15, True, True)
        gen.generate_event(1, False, False)
        assert gen.max_magnitude() >= 6.0


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestSeismologyMiddleware:
    """Verification of the FizzSeismology middleware integration."""

    def test_middleware_name(self):
        mw = SeismologyMiddleware()
        assert mw.get_name() == "SeismologyMiddleware"

    def test_middleware_priority(self):
        mw = SeismologyMiddleware()
        assert mw.get_priority() == 287

    def test_middleware_attaches_metadata(self):
        mw = SeismologyMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "seismo_magnitude_ml" in result.metadata

    def test_middleware_increments_evaluations(self):
        mw = SeismologyMiddleware()
        ctx = _make_context(1, "1")
        mw.process(ctx, lambda c: c)
        assert mw.evaluations == 1

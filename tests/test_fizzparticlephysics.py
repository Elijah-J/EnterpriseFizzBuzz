"""
Enterprise FizzBuzz Platform - FizzParticlePhysics Simulator Test Suite

Comprehensive verification of the particle physics analysis pipeline,
including Standard Model particle identification, decay channel
calculation, Breit-Wigner cross-section computation, Feynman diagram
construction, and invariant mass reconstruction. Misidentification
of the Fizzon or Buzzon particle species would assign incorrect
quantum numbers to the FizzBuzz output, causing the classification
to violate conservation laws.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzparticlephysics import (
    ALPHA_EM,
    ALPHA_S,
    C,
    ELECTRON_MASS,
    GEV2_TO_PB,
    HIGGS_MASS,
    PROTON_MASS,
    W_MASS,
    Z_MASS,
    CrossSectionCalculator,
    CrossSectionResult,
    DecayChannel,
    DecayChannelCalculator,
    FeynmanDiagram,
    FeynmanDiagramBuilder,
    FeynmanVertex,
    InteractionType,
    InvariantMassReconstructor,
    Particle,
    ParticleIdentifier,
    ParticlePhysicsEngine,
    ParticlePhysicsMiddleware,
    ParticleType,
)
from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
    ConservationViolationError,
    CrossSectionError,
    DecayChannelError,
    FeynmanDiagramError,
    FizzParticlePhysicsError,
    InvariantMassError,
    ParticleNotFoundError,
    ParticlePhysicsMiddlewareError,
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
# Particle Identifier Tests
# ===========================================================================


class TestParticleIdentifier:

    def test_fizz_is_fizzon(self):
        ident = ParticleIdentifier()
        assert ident.identify(3, True, False) == ParticleType.FIZZON

    def test_buzz_is_buzzon(self):
        ident = ParticleIdentifier()
        assert ident.identify(5, False, True) == ParticleType.BUZZON

    def test_fizzbuzz_is_fizzbuzzon(self):
        ident = ParticleIdentifier()
        assert ident.identify(15, True, True) == ParticleType.FIZZBUZZON

    def test_plain_number_uses_modular_map(self):
        ident = ParticleIdentifier()
        p = ident.identify(1, False, False)
        assert p == ParticleType.UP

    def test_mass_positive_for_massive_particles(self):
        ident = ParticleIdentifier()
        mass = ident.get_mass(ParticleType.HIGGS)
        assert mass == HIGGS_MASS


# ===========================================================================
# Decay Channel Tests
# ===========================================================================


class TestDecayChannelCalculator:

    def test_fizzbuzzon_decays(self):
        calc = DecayChannelCalculator()
        channels = calc.compute_channels(ParticleType.FIZZBUZZON)
        assert len(channels) > 0
        total_br = sum(c.branching_ratio for c in channels)
        assert abs(total_br - 1.0) < 1e-6

    def test_fizzon_decays(self):
        calc = DecayChannelCalculator()
        channels = calc.compute_channels(ParticleType.FIZZON)
        assert len(channels) > 0

    def test_decay_kinematically_allowed(self):
        calc = DecayChannelCalculator()
        channels = calc.compute_channels(ParticleType.FIZZBUZZON)
        for ch in channels:
            assert ch.is_kinematically_allowed

    def test_no_decay_for_unknown_particle(self):
        calc = DecayChannelCalculator()
        channels = calc.compute_channels(ParticleType.ELECTRON)
        assert len(channels) == 0


# ===========================================================================
# Cross Section Tests
# ===========================================================================


class TestCrossSectionCalculator:

    def test_resonance_peak(self):
        calc = CrossSectionCalculator()
        on_peak = calc.compute("test", 91.188, 91.188, 2.5)
        off_peak = calc.compute("test", 200.0, 91.188, 2.5)
        assert on_peak.cross_section_pb > off_peak.cross_section_pb

    def test_cross_section_positive(self):
        calc = CrossSectionCalculator()
        result = calc.compute("fizzbuzz", 100.0, 15.0, 1.0)
        assert result.cross_section_pb > 0

    def test_zero_energy_raises(self):
        calc = CrossSectionCalculator()
        with pytest.raises(CrossSectionError):
            calc.compute("test", 0.0, 91.188)

    def test_statistical_error(self):
        calc = CrossSectionCalculator()
        result = calc.compute("test", 50.0, 15.0)
        assert result.statistical_error_pb > 0


# ===========================================================================
# Feynman Diagram Tests
# ===========================================================================


class TestFeynmanDiagramBuilder:

    def test_s_channel_diagram(self):
        builder = FeynmanDiagramBuilder()
        diagram = builder.build_s_channel(
            [ParticleType.FIZZON, ParticleType.BUZZON],
            ParticleType.FIZZBUZZON,
            [ParticleType.UP, ParticleType.DOWN],
        )
        assert len(diagram.vertices) == 2
        assert diagram.order == 2

    def test_amplitude_nonzero(self):
        builder = FeynmanDiagramBuilder()
        diagram = builder.build_s_channel(
            [ParticleType.ELECTRON],
            ParticleType.PHOTON,
            [ParticleType.ELECTRON],
        )
        assert diagram.amplitude != 0


# ===========================================================================
# Invariant Mass Tests
# ===========================================================================


class TestInvariantMassReconstructor:

    def test_single_particle(self):
        recon = InvariantMassReconstructor()
        p = Particle(ParticleType.ELECTRON, energy_gev=1.0, px=0.0, py=0.0, pz=math.sqrt(1.0 - ELECTRON_MASS**2))
        mass = recon.reconstruct([p])
        assert abs(mass - ELECTRON_MASS) < 0.01

    def test_negative_mass_squared_raises(self):
        recon = InvariantMassReconstructor()
        # Spacelike: |p| > E
        p = Particle(ParticleType.PHOTON, energy_gev=1.0, px=2.0, py=0.0, pz=0.0)
        with pytest.raises(InvariantMassError):
            recon.reconstruct([p])

    def test_conservation_check_passes(self):
        recon = InvariantMassReconstructor()
        initial = [Particle(ParticleType.FIZZBUZZON, energy_gev=15.0, px=0.0, py=0.0, pz=0.0)]
        final = [
            Particle(ParticleType.FIZZON, energy_gev=7.5, px=1.0, py=0.0, pz=0.0),
            Particle(ParticleType.BUZZON, energy_gev=7.5, px=-1.0, py=0.0, pz=0.0),
        ]
        assert recon.check_conservation(initial, final)

    def test_conservation_violation_raises(self):
        recon = InvariantMassReconstructor()
        initial = [Particle(ParticleType.FIZZBUZZON, energy_gev=15.0, px=0.0, py=0.0, pz=0.0)]
        final = [Particle(ParticleType.FIZZON, energy_gev=5.0, px=0.0, py=0.0, pz=0.0)]
        with pytest.raises(ConservationViolationError):
            recon.check_conservation(initial, final)


# ===========================================================================
# Engine Integration Tests
# ===========================================================================


class TestParticlePhysicsEngine:

    def test_analyze_fizz(self):
        engine = ParticlePhysicsEngine()
        result = engine.analyze_number(3, True, False)
        assert result.identified_particle == ParticleType.FIZZON
        assert result.fizz_charge == 1
        assert result.buzz_charge == 0

    def test_analyze_buzz(self):
        engine = ParticlePhysicsEngine()
        result = engine.analyze_number(5, False, True)
        assert result.identified_particle == ParticleType.BUZZON
        assert result.buzz_charge == 1

    def test_analysis_count(self):
        engine = ParticlePhysicsEngine()
        engine.analyze_number(1, False, False)
        engine.analyze_number(2, False, False)
        assert engine.analysis_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================


class TestParticlePhysicsMiddleware:

    def test_middleware_attaches_metadata(self):
        mw = ParticlePhysicsMiddleware()
        ctx = _make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        result = mw.process(ctx, lambda c: c)
        assert "particle_physics" in result.metadata
        assert "particle" in result.metadata["particle_physics"]
        assert "invariant_mass_gev" in result.metadata["particle_physics"]

    def test_middleware_handles_plain(self):
        mw = ParticlePhysicsMiddleware()
        ctx = _make_context(7, "7")
        result = mw.process(ctx, lambda c: c)
        assert "particle_physics" in result.metadata


# ===========================================================================
# Exception Tests
# ===========================================================================


class TestExceptions:

    def test_base_exception(self):
        err = FizzParticlePhysicsError("test")
        assert "EFP-PP00" in str(err.error_code)

    def test_decay_channel_error_fields(self):
        err = DecayChannelError("Higgs", ["b", "bbar"], "mass exceeds parent")
        assert err.parent == "Higgs"
        assert err.daughters == ["b", "bbar"]

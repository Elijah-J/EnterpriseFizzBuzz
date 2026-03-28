"""
Enterprise FizzBuzz Platform - FizzParticlePhysics: Particle Physics Simulator

Implements Standard Model particle identification, decay channel
computation, scattering cross-section calculation, Feynman diagram
topology analysis, and invariant mass reconstruction for FizzBuzz
evaluation sequences.

The fundamental particles of the FizzBuzz Standard Model are the Fizzon
(a boson mediating the Fizz interaction), the Buzzon (mediating the Buzz
interaction), and the FizzBuzzon (a composite state arising from
Fizzon-Buzzon fusion). Each integer maps to a particle species based on
its quantum numbers: the Fizz charge (divisibility by 3) and Buzz charge
(divisibility by 5) determine the interaction vertices.

Cross-section calculations are essential for predicting the probability
that a given number will be classified correctly in a high-luminosity
evaluation environment. The Feynman diagram formalism provides a
systematic way to compute these probabilities to arbitrary precision
in perturbation theory. Without this analysis, the platform cannot
provide cross-section-weighted classification confidence intervals.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Speed of light (m/s)
C = 2.998e8

# Planck constant (eV*s)
H_BAR = 6.582119569e-16

# Fine structure constant
ALPHA_EM = 1.0 / 137.036

# Strong coupling constant at M_Z
ALPHA_S = 0.1179

# Fermi constant (GeV^-2)
G_FERMI = 1.1663787e-5

# Conversion factor: GeV^-2 to pb
GEV2_TO_PB = 3.8938e8

# Particle masses (GeV/c^2)
ELECTRON_MASS = 0.000511
MUON_MASS = 0.10566
TAU_MASS = 1.777
UP_MASS = 0.0022
DOWN_MASS = 0.0047
CHARM_MASS = 1.275
STRANGE_MASS = 0.095
TOP_MASS = 173.0
BOTTOM_MASS = 4.18
W_MASS = 80.379
Z_MASS = 91.188
HIGGS_MASS = 125.1
PROTON_MASS = 0.938


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ParticleType(Enum):
    """Standard Model particle types."""
    # Quarks
    UP = auto()
    DOWN = auto()
    CHARM = auto()
    STRANGE = auto()
    TOP = auto()
    BOTTOM = auto()
    # Leptons
    ELECTRON = auto()
    MUON = auto()
    TAU = auto()
    ELECTRON_NEUTRINO = auto()
    MUON_NEUTRINO = auto()
    TAU_NEUTRINO = auto()
    # Gauge bosons
    PHOTON = auto()
    GLUON = auto()
    W_PLUS = auto()
    W_MINUS = auto()
    Z_BOSON = auto()
    # Scalar boson
    HIGGS = auto()
    # FizzBuzz-specific
    FIZZON = auto()
    BUZZON = auto()
    FIZZBUZZON = auto()


class InteractionType(Enum):
    """Fundamental interaction types."""
    ELECTROMAGNETIC = auto()
    STRONG = auto()
    WEAK = auto()
    FIZZ = auto()
    BUZZ = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


_PARTICLE_MASSES: dict[ParticleType, float] = {
    ParticleType.UP: UP_MASS,
    ParticleType.DOWN: DOWN_MASS,
    ParticleType.CHARM: CHARM_MASS,
    ParticleType.STRANGE: STRANGE_MASS,
    ParticleType.TOP: TOP_MASS,
    ParticleType.BOTTOM: BOTTOM_MASS,
    ParticleType.ELECTRON: ELECTRON_MASS,
    ParticleType.MUON: MUON_MASS,
    ParticleType.TAU: TAU_MASS,
    ParticleType.ELECTRON_NEUTRINO: 0.0,
    ParticleType.MUON_NEUTRINO: 0.0,
    ParticleType.TAU_NEUTRINO: 0.0,
    ParticleType.PHOTON: 0.0,
    ParticleType.GLUON: 0.0,
    ParticleType.W_PLUS: W_MASS,
    ParticleType.W_MINUS: W_MASS,
    ParticleType.Z_BOSON: Z_MASS,
    ParticleType.HIGGS: HIGGS_MASS,
    ParticleType.FIZZON: 3.0,
    ParticleType.BUZZON: 5.0,
    ParticleType.FIZZBUZZON: 15.0,
}

_PARTICLE_CHARGES: dict[ParticleType, float] = {
    ParticleType.UP: 2.0 / 3.0,
    ParticleType.DOWN: -1.0 / 3.0,
    ParticleType.CHARM: 2.0 / 3.0,
    ParticleType.STRANGE: -1.0 / 3.0,
    ParticleType.TOP: 2.0 / 3.0,
    ParticleType.BOTTOM: -1.0 / 3.0,
    ParticleType.ELECTRON: -1.0,
    ParticleType.MUON: -1.0,
    ParticleType.TAU: -1.0,
    ParticleType.ELECTRON_NEUTRINO: 0.0,
    ParticleType.MUON_NEUTRINO: 0.0,
    ParticleType.TAU_NEUTRINO: 0.0,
    ParticleType.PHOTON: 0.0,
    ParticleType.GLUON: 0.0,
    ParticleType.W_PLUS: 1.0,
    ParticleType.W_MINUS: -1.0,
    ParticleType.Z_BOSON: 0.0,
    ParticleType.HIGGS: 0.0,
    ParticleType.FIZZON: 0.0,
    ParticleType.BUZZON: 0.0,
    ParticleType.FIZZBUZZON: 0.0,
}


@dataclass
class Particle:
    """A particle with four-momentum."""
    particle_type: ParticleType = ParticleType.ELECTRON
    energy_gev: float = 0.0
    px: float = 0.0
    py: float = 0.0
    pz: float = 0.0

    @property
    def mass_gev(self) -> float:
        return _PARTICLE_MASSES.get(self.particle_type, 0.0)

    @property
    def charge(self) -> float:
        return _PARTICLE_CHARGES.get(self.particle_type, 0.0)

    @property
    def invariant_mass_squared(self) -> float:
        return self.energy_gev ** 2 - self.px ** 2 - self.py ** 2 - self.pz ** 2

    @property
    def invariant_mass(self) -> float:
        m2 = self.invariant_mass_squared
        return math.sqrt(m2) if m2 >= 0 else -math.sqrt(-m2)

    @property
    def momentum_magnitude(self) -> float:
        return math.sqrt(self.px ** 2 + self.py ** 2 + self.pz ** 2)


@dataclass
class DecayChannel:
    """A particle decay channel."""
    parent: ParticleType = ParticleType.HIGGS
    daughters: list[ParticleType] = field(default_factory=list)
    branching_ratio: float = 0.0
    is_kinematically_allowed: bool = True

    def validate(self) -> bool:
        """Check that the decay is kinematically allowed."""
        parent_mass = _PARTICLE_MASSES.get(self.parent, 0.0)
        daughters_mass = sum(
            _PARTICLE_MASSES.get(d, 0.0) for d in self.daughters
        )
        return parent_mass >= daughters_mass


@dataclass
class CrossSectionResult:
    """Scattering cross-section result."""
    process: str = ""
    energy_gev: float = 0.0
    cross_section_pb: float = 0.0
    statistical_error_pb: float = 0.0


@dataclass
class FeynmanVertex:
    """A vertex in a Feynman diagram."""
    vertex_id: int = 0
    incoming: list[ParticleType] = field(default_factory=list)
    outgoing: list[ParticleType] = field(default_factory=list)
    coupling: float = 0.0


@dataclass
class FeynmanDiagram:
    """A Feynman diagram as a collection of vertices and propagators."""
    diagram_id: str = ""
    vertices: list[FeynmanVertex] = field(default_factory=list)
    order: int = 0  # Perturbative order
    amplitude: float = 0.0


@dataclass
class ParticlePhysicsAnalysis:
    """Complete particle physics analysis result."""
    identified_particle: ParticleType = ParticleType.ELECTRON
    decay_channels: list[DecayChannel] = field(default_factory=list)
    cross_section: CrossSectionResult = field(default_factory=CrossSectionResult)
    invariant_mass_gev: float = 0.0
    diagram: FeynmanDiagram = field(default_factory=FeynmanDiagram)
    fizz_charge: int = 0
    buzz_charge: int = 0


# ---------------------------------------------------------------------------
# Particle Identifier
# ---------------------------------------------------------------------------


class ParticleIdentifier:
    """Maps FizzBuzz numbers to Standard Model particles.

    The mapping is based on the number's modular arithmetic properties:
    - n mod 12 determines the fermion generation and type
    - Fizz numbers are bosonic (integer spin)
    - Buzz numbers carry color charge
    - FizzBuzz numbers are the heavy composite state
    """

    _MODULAR_MAP: dict[int, ParticleType] = {
        0: ParticleType.FIZZBUZZON,
        1: ParticleType.UP,
        2: ParticleType.DOWN,
        3: ParticleType.FIZZON,
        4: ParticleType.CHARM,
        5: ParticleType.BUZZON,
        6: ParticleType.FIZZON,
        7: ParticleType.STRANGE,
        8: ParticleType.TOP,
        9: ParticleType.FIZZON,
        10: ParticleType.BUZZON,
        11: ParticleType.BOTTOM,
    }

    def identify(self, number: int, is_fizz: bool, is_buzz: bool) -> ParticleType:
        """Identify the particle species for a given number."""
        if is_fizz and is_buzz:
            return ParticleType.FIZZBUZZON
        elif is_fizz:
            return ParticleType.FIZZON
        elif is_buzz:
            return ParticleType.BUZZON
        else:
            key = abs(number) % 12
            return self._MODULAR_MAP.get(key, ParticleType.ELECTRON)

    def get_mass(self, particle: ParticleType) -> float:
        """Return the mass of a particle in GeV/c^2."""
        mass = _PARTICLE_MASSES.get(particle)
        if mass is None:
            from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
                ParticleNotFoundError,
            )
            raise ParticleNotFoundError(particle.name)
        return mass


# ---------------------------------------------------------------------------
# Decay Channel Calculator
# ---------------------------------------------------------------------------


class DecayChannelCalculator:
    """Computes allowed decay channels for FizzBuzz particles."""

    # Pre-defined decay channels for FizzBuzz particles
    _CHANNELS: dict[ParticleType, list[tuple[list[ParticleType], float]]] = {
        ParticleType.FIZZBUZZON: [
            ([ParticleType.FIZZON, ParticleType.BUZZON], 0.60),
            ([ParticleType.FIZZON, ParticleType.FIZZON, ParticleType.FIZZON], 0.15),
            ([ParticleType.BUZZON, ParticleType.BUZZON, ParticleType.BUZZON], 0.10),
            ([ParticleType.UP, ParticleType.DOWN], 0.15),
        ],
        ParticleType.FIZZON: [
            ([ParticleType.UP, ParticleType.DOWN], 0.40),
            ([ParticleType.ELECTRON, ParticleType.ELECTRON_NEUTRINO], 0.30),
            ([ParticleType.MUON, ParticleType.MUON_NEUTRINO], 0.30),
        ],
        ParticleType.BUZZON: [
            ([ParticleType.CHARM, ParticleType.STRANGE], 0.50),
            ([ParticleType.UP, ParticleType.DOWN], 0.30),
            ([ParticleType.TAU, ParticleType.TAU_NEUTRINO], 0.20),
        ],
    }

    def compute_channels(self, particle: ParticleType) -> list[DecayChannel]:
        """Compute allowed decay channels."""
        raw = self._CHANNELS.get(particle, [])
        channels: list[DecayChannel] = []

        for daughters, br in raw:
            channel = DecayChannel(
                parent=particle,
                daughters=daughters,
                branching_ratio=br,
            )
            channel.is_kinematically_allowed = channel.validate()

            if not channel.is_kinematically_allowed:
                from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
                    DecayChannelError,
                )
                raise DecayChannelError(
                    particle.name,
                    [d.name for d in daughters],
                    "daughter mass exceeds parent mass",
                )

            channels.append(channel)

        return channels


# ---------------------------------------------------------------------------
# Cross Section Calculator
# ---------------------------------------------------------------------------


class CrossSectionCalculator:
    """Computes scattering cross-sections for FizzBuzz processes.

    Uses the Breit-Wigner resonance formula for s-channel processes
    and the Rutherford formula for t-channel exchanges.
    """

    def compute(
        self,
        process: str,
        sqrt_s_gev: float,
        resonance_mass_gev: float,
        resonance_width_gev: float = 1.0,
    ) -> CrossSectionResult:
        """Compute the scattering cross-section in picobarns."""
        if sqrt_s_gev <= 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
                CrossSectionError,
            )
            raise CrossSectionError(process, sqrt_s_gev, 0.0)

        s = sqrt_s_gev ** 2
        m2 = resonance_mass_gev ** 2
        gamma2 = resonance_width_gev ** 2

        # Breit-Wigner cross-section
        denom = (s - m2) ** 2 + m2 * gamma2
        if denom < 1e-30:
            denom = 1e-30

        sigma = (12.0 * math.pi / m2) * (s * gamma2 / denom)
        sigma_pb = sigma * GEV2_TO_PB / s if s > 0 else 0.0

        if sigma_pb < 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
                CrossSectionError,
            )
            raise CrossSectionError(process, sqrt_s_gev, sigma_pb)

        return CrossSectionResult(
            process=process,
            energy_gev=sqrt_s_gev,
            cross_section_pb=sigma_pb,
            statistical_error_pb=sigma_pb * 0.05,
        )


# ---------------------------------------------------------------------------
# Feynman Diagram Builder
# ---------------------------------------------------------------------------


class FeynmanDiagramBuilder:
    """Constructs Feynman diagrams for FizzBuzz interactions."""

    def build_s_channel(
        self,
        incoming: list[ParticleType],
        mediator: ParticleType,
        outgoing: list[ParticleType],
    ) -> FeynmanDiagram:
        """Build an s-channel Feynman diagram."""
        diagram_id = f"s_{mediator.name}"

        v1 = FeynmanVertex(
            vertex_id=0,
            incoming=incoming,
            outgoing=[mediator],
            coupling=self._coupling_constant(incoming, mediator),
        )

        v2 = FeynmanVertex(
            vertex_id=1,
            incoming=[mediator],
            outgoing=outgoing,
            coupling=self._coupling_constant([mediator], outgoing[0] if outgoing else mediator),
        )

        amplitude = v1.coupling * v2.coupling

        return FeynmanDiagram(
            diagram_id=diagram_id,
            vertices=[v1, v2],
            order=2,
            amplitude=amplitude,
        )

    def _coupling_constant(
        self, particles_in: list[ParticleType], vertex_particle: ParticleType
    ) -> float:
        """Determine the coupling constant at a vertex."""
        if vertex_particle == ParticleType.PHOTON:
            return math.sqrt(ALPHA_EM)
        elif vertex_particle == ParticleType.GLUON:
            return math.sqrt(ALPHA_S)
        elif vertex_particle in (ParticleType.W_PLUS, ParticleType.W_MINUS, ParticleType.Z_BOSON):
            return math.sqrt(G_FERMI * W_MASS ** 2 * 4.0 * math.sqrt(2.0))
        elif vertex_particle == ParticleType.FIZZON:
            return 1.0 / 3.0
        elif vertex_particle == ParticleType.BUZZON:
            return 1.0 / 5.0
        elif vertex_particle == ParticleType.FIZZBUZZON:
            return 1.0 / 15.0
        else:
            return ALPHA_EM


# ---------------------------------------------------------------------------
# Invariant Mass Reconstructor
# ---------------------------------------------------------------------------


class InvariantMassReconstructor:
    """Reconstructs invariant mass from particle four-momenta.

    The invariant mass of a system is M^2 = (sum E)^2 - (sum p)^2.
    This is a Lorentz invariant quantity that identifies the parent
    particle in a decay.
    """

    def reconstruct(self, particles: list[Particle]) -> float:
        """Reconstruct the invariant mass of the particle system."""
        total_e = sum(p.energy_gev for p in particles)
        total_px = sum(p.px for p in particles)
        total_py = sum(p.py for p in particles)
        total_pz = sum(p.pz for p in particles)

        m_squared = total_e ** 2 - total_px ** 2 - total_py ** 2 - total_pz ** 2

        if m_squared < -1e-6:
            from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
                InvariantMassError,
            )
            raise InvariantMassError(
                [p.particle_type.name for p in particles], m_squared
            )

        return math.sqrt(max(0.0, m_squared))

    def check_conservation(
        self, initial: list[Particle], final: list[Particle]
    ) -> bool:
        """Verify energy-momentum conservation."""
        e_in = sum(p.energy_gev for p in initial)
        e_out = sum(p.energy_gev for p in final)

        if abs(e_in - e_out) > 1e-4:
            from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
                ConservationViolationError,
            )
            raise ConservationViolationError("energy", e_in, e_out)

        q_in = sum(p.charge for p in initial)
        q_out = sum(p.charge for p in final)

        if abs(q_in - q_out) > 1e-6:
            from enterprise_fizzbuzz.domain.exceptions.fizzparticlephysics import (
                ConservationViolationError,
            )
            raise ConservationViolationError("charge", q_in, q_out)

        return True


# ---------------------------------------------------------------------------
# Particle Physics Engine
# ---------------------------------------------------------------------------


class ParticlePhysicsEngine:
    """Integrates all particle physics analysis components.

    Performs particle identification, decay channel computation,
    cross-section calculation, and invariant mass reconstruction
    for each FizzBuzz evaluation number.
    """

    def __init__(self) -> None:
        self.identifier = ParticleIdentifier()
        self.decay_calc = DecayChannelCalculator()
        self.xs_calc = CrossSectionCalculator()
        self.diagram_builder = FeynmanDiagramBuilder()
        self.mass_reconstructor = InvariantMassReconstructor()
        self._analysis_count = 0

    def analyze_number(
        self, number: int, is_fizz: bool, is_buzz: bool
    ) -> ParticlePhysicsAnalysis:
        """Perform complete particle physics analysis."""
        self._analysis_count += 1

        particle = self.identifier.identify(number, is_fizz, is_buzz)
        mass = self.identifier.get_mass(particle)

        channels = self.decay_calc.compute_channels(particle)

        sqrt_s = float(abs(number)) + mass
        xs = self.xs_calc.compute(
            f"fizzbuzz -> {particle.name}",
            sqrt_s,
            mass,
            resonance_width_gev=max(0.1, mass * 0.1),
        )

        diagram = self.diagram_builder.build_s_channel(
            [ParticleType.FIZZON, ParticleType.BUZZON],
            particle,
            channels[0].daughters if channels else [ParticleType.ELECTRON],
        )

        fizz_charge = 1 if number % 3 == 0 else 0
        buzz_charge = 1 if number % 5 == 0 else 0

        return ParticlePhysicsAnalysis(
            identified_particle=particle,
            decay_channels=channels,
            cross_section=xs,
            invariant_mass_gev=mass,
            diagram=diagram,
            fizz_charge=fizz_charge,
            buzz_charge=buzz_charge,
        )

    @property
    def analysis_count(self) -> int:
        return self._analysis_count


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class ParticlePhysicsMiddleware(IMiddleware):
    """Middleware that performs particle physics analysis for each evaluation.

    Each number is identified as a fundamental particle, its decay
    channels are computed, and the scattering cross-section at the
    evaluation energy is calculated.

    Priority 295 positions this in the physical sciences tier.
    """

    def __init__(self) -> None:
        self._engine = ParticlePhysicsEngine()
        self._evaluations = 0

    def get_name(self) -> str:
        return "fizzparticlephysics"

    def get_priority(self) -> int:
        return 295

    @property
    def engine(self) -> ParticlePhysicsEngine:
        return self._engine

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        try:
            analysis = self._engine.analyze_number(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["particle_physics"] = {
                "particle": analysis.identified_particle.name,
                "invariant_mass_gev": round(analysis.invariant_mass_gev, 4),
                "fizz_charge": analysis.fizz_charge,
                "buzz_charge": analysis.buzz_charge,
                "cross_section_pb": round(analysis.cross_section.cross_section_pb, 6),
                "decay_channels": len(analysis.decay_channels),
                "diagram_order": analysis.diagram.order,
                "diagram_amplitude": round(analysis.diagram.amplitude, 8),
            }

            logger.debug(
                "FizzParticlePhysics: number=%d particle=%s m=%.4f GeV",
                number,
                analysis.identified_particle.name,
                analysis.invariant_mass_gev,
            )

        except Exception:
            logger.exception(
                "FizzParticlePhysics: analysis failed for number %d", number
            )

        return result

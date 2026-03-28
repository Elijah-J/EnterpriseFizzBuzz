"""
Enterprise FizzBuzz Platform - FizzParticlePhysics Exceptions (EFP-PP00 through EFP-PP07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzParticlePhysicsError(FizzBuzzError):
    """Base exception for the FizzParticlePhysics simulator subsystem.

    Particle physics simulation for FizzBuzz evaluation involves
    Standard Model particle identification, decay channel computation,
    cross-section calculation, and invariant mass reconstruction. Each
    step has conservation law requirements that must be strictly
    satisfied.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PP00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ParticleNotFoundError(FizzParticlePhysicsError):
    """Raised when a referenced particle is not in the Standard Model catalog.

    The Standard Model catalog contains all known fundamental particles:
    six quarks, six leptons, four gauge bosons, and the Higgs boson.
    Referencing a particle not in this catalog indicates either a typo
    or a request for beyond-Standard-Model physics, which is not yet
    supported.
    """

    def __init__(self, particle_name: str) -> None:
        super().__init__(
            f"Particle '{particle_name}' not found in the Standard Model catalog",
            error_code="EFP-PP01",
            context={"particle_name": particle_name},
        )
        self.particle_name = particle_name


class DecayChannelError(FizzParticlePhysicsError):
    """Raised when a decay channel violates conservation laws.

    Every decay must conserve energy, momentum, charge, baryon number,
    and lepton number. A decay channel where the sum of daughter-particle
    masses exceeds the parent mass is kinematically forbidden.
    """

    def __init__(self, parent: str, daughters: list[str], reason: str) -> None:
        super().__init__(
            f"Decay channel {parent} -> {', '.join(daughters)} is invalid: {reason}",
            error_code="EFP-PP02",
            context={"parent": parent, "daughters": daughters, "reason": reason},
        )
        self.parent = parent
        self.daughters = daughters


class CrossSectionError(FizzParticlePhysicsError):
    """Raised when cross-section calculation yields non-physical results.

    Scattering cross-sections must be non-negative (unitarity) and
    satisfy the optical theorem. Negative values indicate a sign error
    in the matrix element computation.
    """

    def __init__(self, process: str, energy_gev: float, value_pb: float) -> None:
        super().__init__(
            f"Non-physical cross-section for '{process}' at sqrt(s)="
            f"{energy_gev:.2f} GeV: {value_pb:.6e} pb",
            error_code="EFP-PP03",
            context={
                "process": process,
                "energy_gev": energy_gev,
                "value_pb": value_pb,
            },
        )
        self.process = process
        self.energy_gev = energy_gev


class FeynmanDiagramError(FizzParticlePhysicsError):
    """Raised when Feynman diagram topology is invalid.

    A valid Feynman diagram must have an even number of external legs
    at each vertex, and each vertex must conserve all quantum numbers.
    Disconnected diagrams must be factored before amplitude computation.
    """

    def __init__(self, diagram_id: str, reason: str) -> None:
        super().__init__(
            f"Feynman diagram '{diagram_id}' is invalid: {reason}",
            error_code="EFP-PP04",
            context={"diagram_id": diagram_id, "reason": reason},
        )
        self.diagram_id = diagram_id


class InvariantMassError(FizzParticlePhysicsError):
    """Raised when invariant mass reconstruction yields unphysical results.

    The invariant mass of a system of particles must be non-negative
    (timelike four-momentum). Negative invariant mass squared indicates
    a spacelike four-momentum, which is non-physical for on-shell
    particles.
    """

    def __init__(self, particles: list[str], mass_squared_gev2: float) -> None:
        super().__init__(
            f"Invariant mass reconstruction failed for "
            f"{', '.join(particles)}: m^2 = {mass_squared_gev2:.4f} GeV^2",
            error_code="EFP-PP05",
            context={
                "particles": particles,
                "mass_squared_gev2": mass_squared_gev2,
            },
        )
        self.particles = particles
        self.mass_squared_gev2 = mass_squared_gev2


class ConservationViolationError(FizzParticlePhysicsError):
    """Raised when a conservation law is violated in a particle interaction.

    Conservation of energy-momentum, charge, baryon number, and lepton
    flavor must hold at every vertex. Any discrepancy indicates a
    fundamental error in the interaction topology.
    """

    def __init__(self, quantity: str, expected: float, actual: float) -> None:
        super().__init__(
            f"Conservation of {quantity} violated: expected {expected:.6f}, "
            f"got {actual:.6f}",
            error_code="EFP-PP06",
            context={"quantity": quantity, "expected": expected, "actual": actual},
        )
        self.quantity = quantity


class ParticlePhysicsMiddlewareError(FizzParticlePhysicsError):
    """Raised when the FizzParticlePhysics middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzParticlePhysics middleware error: {reason}",
            error_code="EFP-PP07",
            context={"reason": reason},
        )

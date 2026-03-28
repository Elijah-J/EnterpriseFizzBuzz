"""
Enterprise FizzBuzz Platform - FizzSwarm Swarm Intelligence Exceptions

The FizzSwarm subsystem applies collective intelligence algorithms to the
FizzBuzz classification problem. Ant colony optimization discovers optimal
classification paths via pheromone-guided search; particle swarm optimization
evolves candidate solutions through velocity-position updates; the bee algorithm
allocates forager agents to promising regions of the solution space.

Each algorithm has characteristic failure modes: pheromone evaporation can
drive the colony to stagnation, particle velocities can diverge, and forager
allocation can deadlock if all scouts return empty.

Error codes: EFP-SW00 through EFP-SW06.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzSwarmError(FizzBuzzError):
    """Base exception for all swarm intelligence subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SW00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class PheromoneEvaporationError(FizzSwarmError):
    """Raised when pheromone levels decay below the functional threshold.

    Pheromone evaporation is essential for preventing premature convergence,
    but excessive evaporation causes the colony to lose all trail information.
    When the maximum pheromone level across all edges drops below the minimum
    detectable concentration, ants revert to random exploration and the
    algorithm degenerates to brute-force search.
    """

    def __init__(self, max_pheromone: float, threshold: float) -> None:
        super().__init__(
            f"Maximum pheromone level {max_pheromone:.6f} is below the "
            f"functional threshold of {threshold:.6f}. The colony has lost "
            f"all trail information.",
            error_code="EFP-SW01",
            context={"max_pheromone": max_pheromone, "threshold": threshold},
        )


class ParticleVelocityDivergenceError(FizzSwarmError):
    """Raised when a particle's velocity exceeds the maximum allowed magnitude.

    In particle swarm optimization, each particle's velocity is updated based
    on cognitive (personal best) and social (global best) components. Without
    velocity clamping, particles can escape the search space. This exception
    is raised when the velocity magnitude exceeds V_max, indicating that the
    inertia weight or acceleration coefficients are misconfigured.
    """

    def __init__(self, particle_id: int, velocity: float, v_max: float) -> None:
        super().__init__(
            f"Particle {particle_id} velocity magnitude {velocity:.4f} exceeds "
            f"V_max={v_max:.4f}. Reduce inertia weight or acceleration coefficients.",
            error_code="EFP-SW02",
            context={"particle_id": particle_id, "velocity": velocity, "v_max": v_max},
        )


class SwarmConvergenceError(FizzSwarmError):
    """Raised when the swarm fails to converge within the allowed iterations.

    Convergence is measured by the variance of the swarm's fitness values.
    If the variance remains above the convergence threshold after the maximum
    number of iterations, the swarm has not reached consensus on the optimal
    FizzBuzz classification.
    """

    def __init__(self, iterations: int, variance: float, threshold: float) -> None:
        super().__init__(
            f"Swarm did not converge after {iterations} iterations. "
            f"Fitness variance {variance:.6f} exceeds threshold {threshold:.6f}.",
            error_code="EFP-SW03",
            context={"iterations": iterations, "variance": variance, "threshold": threshold},
        )


class StigmergyError(FizzSwarmError):
    """Raised when the stigmergic environment becomes inconsistent.

    Stigmergy is the mechanism by which agents communicate indirectly through
    modifications to a shared environment. If the environment state becomes
    inconsistent (e.g., negative pheromone, corrupted trail map), the
    collective behavior of the swarm is no longer well-defined.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Stigmergic environment inconsistency: {reason}.",
            error_code="EFP-SW04",
            context={"reason": reason},
        )


class ForagerAllocationError(FizzSwarmError):
    """Raised when the bee algorithm cannot allocate foragers to food sources.

    The bee algorithm partitions the colony into employed bees, onlooker bees,
    and scouts. If all food sources are exhausted and all scouts fail to discover
    new sources within the abandonment limit, the colony cannot make progress.
    """

    def __init__(self, num_sources: int, abandonment_limit: int) -> None:
        super().__init__(
            f"All {num_sources} food sources exhausted after {abandonment_limit} "
            f"scouting attempts. No viable solutions remain.",
            error_code="EFP-SW05",
            context={"num_sources": num_sources, "abandonment_limit": abandonment_limit},
        )


class SwarmMiddlewareError(FizzSwarmError):
    """Raised when the swarm intelligence middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Swarm intelligence middleware failed for number {number}: {reason}.",
            error_code="EFP-SW06",
            context={"number": number, "reason": reason},
        )

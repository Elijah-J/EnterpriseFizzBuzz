"""
Enterprise FizzBuzz Platform - FizzSwarm: Swarm Intelligence Engine

Applies collective intelligence algorithms to discover optimal FizzBuzz
classifications through emergent behavior of simple autonomous agents.

Three complementary algorithms are implemented:

1. **Ant Colony Optimization (ACO)** — Ants traverse a graph whose edges
   connect input integers to candidate FizzBuzz labels. Pheromone deposits
   reinforce edges that lead to correct classifications. Over successive
   iterations, the colony converges to the globally optimal label for each
   number. The pheromone update follows the Ant System (AS) variant with
   configurable evaporation rate rho.

2. **Particle Swarm Optimization (PSO)** — Each particle occupies a position
   in a 4-dimensional classification space (one axis per FizzBuzz class).
   The velocity update combines cognitive (personal best), social (global
   best), and inertia components. The argmax of the particle's position
   vector determines the predicted label.

3. **Bee Algorithm (BA)** — The colony partitions into employed bees
   (exploiting known food sources), onlooker bees (probabilistically
   selecting sources based on quality), and scout bees (exploring new
   regions after source abandonment). Each food source maps to a
   candidate FizzBuzz classification.

Stigmergy — indirect communication via environmental modification — is
the unifying principle. All three algorithms modify a shared fitness
landscape that encodes the FizzBuzz rules.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIZZBUZZ_CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]
NUM_CLASSES = len(FIZZBUZZ_CLASSES)

# ACO defaults
DEFAULT_NUM_ANTS = 20
DEFAULT_ACO_ITERATIONS = 50
DEFAULT_PHEROMONE_INIT = 1.0
DEFAULT_EVAPORATION_RATE = 0.1
DEFAULT_PHEROMONE_DEPOSIT = 1.0
DEFAULT_ALPHA = 1.0  # Pheromone influence
DEFAULT_BETA = 2.0   # Heuristic influence
DEFAULT_MIN_PHEROMONE = 0.001

# PSO defaults
DEFAULT_NUM_PARTICLES = 15
DEFAULT_PSO_ITERATIONS = 40
DEFAULT_INERTIA = 0.7
DEFAULT_COGNITIVE = 1.5
DEFAULT_SOCIAL = 1.5
DEFAULT_V_MAX = 2.0

# Bee algorithm defaults
DEFAULT_NUM_EMPLOYED = 10
DEFAULT_NUM_ONLOOKER = 10
DEFAULT_NUM_SCOUT = 5
DEFAULT_ABANDONMENT_LIMIT = 10
DEFAULT_BEE_ITERATIONS = 30


# ---------------------------------------------------------------------------
# Pheromone Trail Map (Stigmergy)
# ---------------------------------------------------------------------------

@dataclass
class PheromoneTrail:
    """Pheromone levels on edges from input number to FizzBuzz class.

    In a full ACO graph, each (number, class) pair has an associated
    pheromone level that encodes the colony's accumulated experience.
    """
    levels: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.levels:
            for cls in FIZZBUZZ_CLASSES:
                self.levels[cls] = DEFAULT_PHEROMONE_INIT

    def max_level(self) -> float:
        return max(self.levels.values()) if self.levels else 0.0

    def best_class(self) -> str:
        return max(self.levels, key=lambda k: self.levels[k])


# ---------------------------------------------------------------------------
# Ant Colony Optimization
# ---------------------------------------------------------------------------

@dataclass
class AntSolution:
    """A single ant's solution: a chosen FizzBuzz class and its fitness."""
    label: str = "Plain"
    fitness: float = 0.0


class AntColonyOptimizer:
    """Ant Colony Optimization for FizzBuzz classification.

    Each ant probabilistically selects a FizzBuzz class based on the
    pheromone levels and a heuristic function derived from the divisibility
    properties of the input number. After all ants have made their selection,
    pheromone is deposited on the edges chosen by ants with high fitness,
    and evaporation reduces all pheromone levels.
    """

    def __init__(
        self,
        num_ants: int = DEFAULT_NUM_ANTS,
        iterations: int = DEFAULT_ACO_ITERATIONS,
        evaporation_rate: float = DEFAULT_EVAPORATION_RATE,
        alpha: float = DEFAULT_ALPHA,
        beta: float = DEFAULT_BETA,
        min_pheromone: float = DEFAULT_MIN_PHEROMONE,
        seed: Optional[int] = None,
    ) -> None:
        self._num_ants = num_ants
        self._iterations = iterations
        self._evaporation_rate = evaporation_rate
        self._alpha = alpha
        self._beta = beta
        self._min_pheromone = min_pheromone
        self._rng = random.Random(seed)

    def optimize(self, number: int) -> Tuple[str, PheromoneTrail]:
        """Run ACO to find the optimal FizzBuzz class for the given number.

        Returns:
            Tuple of (best class label, final pheromone trail).
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzswarm import PheromoneEvaporationError

        trail = PheromoneTrail()
        heuristic = self._compute_heuristic(number)
        rng = random.Random(number)

        for iteration in range(self._iterations):
            solutions: List[AntSolution] = []

            for ant in range(self._num_ants):
                # Probabilistic class selection
                label = self._select_class(trail, heuristic, rng)
                fitness = self._evaluate_fitness(number, label)
                solutions.append(AntSolution(label=label, fitness=fitness))

            # Pheromone update
            self._evaporate(trail)
            self._deposit(trail, solutions)

            # Check for pheromone collapse
            if trail.max_level() < self._min_pheromone:
                raise PheromoneEvaporationError(trail.max_level(), self._min_pheromone)

        return trail.best_class(), trail

    def _compute_heuristic(self, number: int) -> Dict[str, float]:
        """Compute heuristic desirability for each class."""
        div3 = number % 3 == 0
        div5 = number % 5 == 0
        h = {
            "Plain": 0.1,
            "Fizz": 0.1,
            "Buzz": 0.1,
            "FizzBuzz": 0.1,
        }
        if div3 and div5:
            h["FizzBuzz"] = 10.0
        elif div3:
            h["Fizz"] = 10.0
        elif div5:
            h["Buzz"] = 10.0
        else:
            h["Plain"] = 10.0
        return h

    def _select_class(
        self, trail: PheromoneTrail, heuristic: Dict[str, float], rng: random.Random
    ) -> str:
        """Probabilistically select a class using pheromone and heuristic."""
        weights = {}
        for cls in FIZZBUZZ_CLASSES:
            tau = trail.levels.get(cls, DEFAULT_PHEROMONE_INIT)
            eta = heuristic.get(cls, 0.1)
            weights[cls] = (tau ** self._alpha) * (eta ** self._beta)

        total = sum(weights.values())
        if total < 1e-12:
            return rng.choice(FIZZBUZZ_CLASSES)

        r = rng.random() * total
        cumulative = 0.0
        for cls in FIZZBUZZ_CLASSES:
            cumulative += weights[cls]
            if r <= cumulative:
                return cls
        return FIZZBUZZ_CLASSES[-1]

    def _evaluate_fitness(self, number: int, label: str) -> float:
        """Evaluate the fitness of a classification."""
        correct = self._correct_label(number)
        return 1.0 if label == correct else 0.0

    def _correct_label(self, number: int) -> str:
        if number % 15 == 0:
            return "FizzBuzz"
        elif number % 3 == 0:
            return "Fizz"
        elif number % 5 == 0:
            return "Buzz"
        return "Plain"

    def _evaporate(self, trail: PheromoneTrail) -> None:
        for cls in FIZZBUZZ_CLASSES:
            trail.levels[cls] *= (1.0 - self._evaporation_rate)

    def _deposit(self, trail: PheromoneTrail, solutions: List[AntSolution]) -> None:
        for sol in solutions:
            if sol.fitness > 0:
                trail.levels[sol.label] += DEFAULT_PHEROMONE_DEPOSIT * sol.fitness


# ---------------------------------------------------------------------------
# Particle Swarm Optimization
# ---------------------------------------------------------------------------

@dataclass
class Particle:
    """A single particle in the swarm.

    Attributes:
        position: Current position in N-dimensional classification space.
        velocity: Current velocity vector.
        personal_best: Best position found by this particle.
        personal_best_fitness: Fitness at the personal best.
    """
    position: List[float] = field(default_factory=lambda: [0.0] * NUM_CLASSES)
    velocity: List[float] = field(default_factory=lambda: [0.0] * NUM_CLASSES)
    personal_best: List[float] = field(default_factory=lambda: [0.0] * NUM_CLASSES)
    personal_best_fitness: float = float("-inf")

    @property
    def predicted_class_index(self) -> int:
        return self.position.index(max(self.position))

    @property
    def predicted_label(self) -> str:
        return FIZZBUZZ_CLASSES[self.predicted_class_index]


class ParticleSwarmOptimizer:
    """Particle Swarm Optimization for FizzBuzz classification."""

    def __init__(
        self,
        num_particles: int = DEFAULT_NUM_PARTICLES,
        iterations: int = DEFAULT_PSO_ITERATIONS,
        inertia: float = DEFAULT_INERTIA,
        cognitive: float = DEFAULT_COGNITIVE,
        social: float = DEFAULT_SOCIAL,
        v_max: float = DEFAULT_V_MAX,
        seed: Optional[int] = None,
    ) -> None:
        self._num_particles = num_particles
        self._iterations = iterations
        self._inertia = inertia
        self._cognitive = cognitive
        self._social = social
        self._v_max = v_max
        self._rng = random.Random(seed)

    def optimize(self, number: int) -> Tuple[str, List[Particle]]:
        """Run PSO to classify the given number.

        Returns:
            Tuple of (best label, final particle list).
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzswarm import ParticleVelocityDivergenceError

        rng = random.Random(number)
        particles = self._initialize_particles(rng)
        global_best = [0.0] * NUM_CLASSES
        global_best_fitness = float("-inf")

        for iteration in range(self._iterations):
            for i, p in enumerate(particles):
                # Evaluate fitness
                fitness = self._evaluate(number, p.position)
                if fitness > p.personal_best_fitness:
                    p.personal_best = list(p.position)
                    p.personal_best_fitness = fitness
                if fitness > global_best_fitness:
                    global_best = list(p.position)
                    global_best_fitness = fitness

            # Update velocities and positions
            for i, p in enumerate(particles):
                for d in range(NUM_CLASSES):
                    r1 = rng.random()
                    r2 = rng.random()
                    cognitive_comp = self._cognitive * r1 * (p.personal_best[d] - p.position[d])
                    social_comp = self._social * r2 * (global_best[d] - p.position[d])
                    p.velocity[d] = self._inertia * p.velocity[d] + cognitive_comp + social_comp

                # Velocity clamping
                v_mag = math.sqrt(sum(v * v for v in p.velocity))
                if v_mag > self._v_max * 10:
                    raise ParticleVelocityDivergenceError(i, v_mag, self._v_max)
                if v_mag > self._v_max:
                    scale = self._v_max / v_mag
                    p.velocity = [v * scale for v in p.velocity]

                # Position update
                for d in range(NUM_CLASSES):
                    p.position[d] += p.velocity[d]

        best_idx = global_best.index(max(global_best))
        return FIZZBUZZ_CLASSES[best_idx], particles

    def _initialize_particles(self, rng: random.Random) -> List[Particle]:
        particles = []
        for _ in range(self._num_particles):
            pos = [rng.uniform(-1, 1) for _ in range(NUM_CLASSES)]
            vel = [rng.uniform(-0.5, 0.5) for _ in range(NUM_CLASSES)]
            particles.append(Particle(
                position=pos,
                velocity=vel,
                personal_best=list(pos),
                personal_best_fitness=float("-inf"),
            ))
        return particles

    def _evaluate(self, number: int, position: List[float]) -> float:
        """Evaluate fitness: reward the correct class dimension."""
        if number % 15 == 0:
            target = 3
        elif number % 3 == 0:
            target = 1
        elif number % 5 == 0:
            target = 2
        else:
            target = 0
        return position[target] - max(
            position[j] for j in range(NUM_CLASSES) if j != target
        )


# ---------------------------------------------------------------------------
# Bee Algorithm
# ---------------------------------------------------------------------------

@dataclass
class FoodSource:
    """A food source in the bee algorithm representing a candidate solution.

    Attributes:
        label: The FizzBuzz class this source represents.
        fitness: Quality of this food source.
        trials: Number of consecutive unsuccessful improvement attempts.
    """
    label: str = "Plain"
    fitness: float = 0.0
    trials: int = 0


class BeeAlgorithm:
    """Artificial Bee Colony algorithm for FizzBuzz classification."""

    def __init__(
        self,
        num_employed: int = DEFAULT_NUM_EMPLOYED,
        num_onlooker: int = DEFAULT_NUM_ONLOOKER,
        abandonment_limit: int = DEFAULT_ABANDONMENT_LIMIT,
        iterations: int = DEFAULT_BEE_ITERATIONS,
        seed: Optional[int] = None,
    ) -> None:
        self._num_employed = num_employed
        self._num_onlooker = num_onlooker
        self._abandonment_limit = abandonment_limit
        self._iterations = iterations
        self._rng = random.Random(seed)

    def optimize(self, number: int) -> Tuple[str, List[FoodSource]]:
        """Run the bee algorithm to classify the given number.

        Returns:
            Tuple of (best label, final food sources).
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzswarm import ForagerAllocationError

        rng = random.Random(number)
        sources = self._initialize_sources(number, rng)

        for iteration in range(self._iterations):
            # Employed bee phase
            for source in sources:
                neighbor_label = rng.choice(FIZZBUZZ_CLASSES)
                neighbor_fitness = self._evaluate(number, neighbor_label)
                if neighbor_fitness > source.fitness:
                    source.label = neighbor_label
                    source.fitness = neighbor_fitness
                    source.trials = 0
                else:
                    source.trials += 1

            # Onlooker bee phase (roulette wheel selection)
            total_fitness = sum(max(s.fitness, 0.01) for s in sources)
            for _ in range(self._num_onlooker):
                r = rng.random() * total_fitness
                cumulative = 0.0
                for source in sources:
                    cumulative += max(source.fitness, 0.01)
                    if r <= cumulative:
                        neighbor_label = rng.choice(FIZZBUZZ_CLASSES)
                        neighbor_fitness = self._evaluate(number, neighbor_label)
                        if neighbor_fitness > source.fitness:
                            source.label = neighbor_label
                            source.fitness = neighbor_fitness
                            source.trials = 0
                        break

            # Scout bee phase
            for source in sources:
                if source.trials >= self._abandonment_limit:
                    new_label = rng.choice(FIZZBUZZ_CLASSES)
                    source.label = new_label
                    source.fitness = self._evaluate(number, new_label)
                    source.trials = 0

        best = max(sources, key=lambda s: s.fitness)
        return best.label, sources

    def _initialize_sources(self, number: int, rng: random.Random) -> List[FoodSource]:
        sources = []
        for _ in range(self._num_employed):
            label = rng.choice(FIZZBUZZ_CLASSES)
            fitness = self._evaluate(number, label)
            sources.append(FoodSource(label=label, fitness=fitness, trials=0))
        return sources

    def _evaluate(self, number: int, label: str) -> float:
        """Evaluate fitness of a classification."""
        correct = self._correct_label(number)
        return 1.0 if label == correct else 0.0

    def _correct_label(self, number: int) -> str:
        if number % 15 == 0:
            return "FizzBuzz"
        elif number % 3 == 0:
            return "Fizz"
        elif number % 5 == 0:
            return "Buzz"
        return "Plain"


# ---------------------------------------------------------------------------
# Unified Swarm Classifier
# ---------------------------------------------------------------------------

@dataclass
class SwarmResult:
    """Aggregated result from all swarm algorithms."""
    label: str = "Plain"
    aco_label: str = "Plain"
    pso_label: str = "Plain"
    bee_label: str = "Plain"
    consensus: bool = False
    pheromone_trail: Optional[PheromoneTrail] = None


class SwarmClassifier:
    """Ensemble classifier that combines ACO, PSO, and Bee Algorithm results."""

    def __init__(
        self,
        aco: Optional[AntColonyOptimizer] = None,
        pso: Optional[ParticleSwarmOptimizer] = None,
        bee: Optional[BeeAlgorithm] = None,
    ) -> None:
        self._aco = aco or AntColonyOptimizer()
        self._pso = pso or ParticleSwarmOptimizer()
        self._bee = bee or BeeAlgorithm()

    def classify(self, number: int) -> SwarmResult:
        """Classify a number using all three swarm algorithms and majority vote."""
        aco_label, trail = self._aco.optimize(number)
        pso_label, _ = self._pso.optimize(number)
        bee_label, _ = self._bee.optimize(number)

        # Majority vote
        votes: Dict[str, int] = {}
        for label in [aco_label, pso_label, bee_label]:
            votes[label] = votes.get(label, 0) + 1
        consensus_label = max(votes, key=lambda k: votes[k])

        return SwarmResult(
            label=consensus_label,
            aco_label=aco_label,
            pso_label=pso_label,
            bee_label=bee_label,
            consensus=votes[consensus_label] >= 2,
            pheromone_trail=trail,
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class SwarmDashboard:
    """Renders an ASCII dashboard of the swarm intelligence pipeline."""

    @staticmethod
    def render(result: SwarmResult, width: int = 60) -> str:
        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(f"| {'FIZZSWARM: SWARM INTELLIGENCE DASHBOARD':^{width - 4}} |")
        lines.append(border)
        lines.append(f"|  ACO result : {result.aco_label:<12}                             |")
        lines.append(f"|  PSO result : {result.pso_label:<12}                             |")
        lines.append(f"|  Bee result : {result.bee_label:<12}                             |")
        lines.append(f"|  Consensus  : {result.label:<12}  (unanimous: {result.consensus})    |")
        if result.pheromone_trail:
            for cls, level in result.pheromone_trail.levels.items():
                bar_len = min(int(level * 3), width - 25)
                bar = "#" * max(bar_len, 0)
                lines.append(f"|    {cls:<10}: {bar:<{width - 20}}|")
        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SwarmMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz via swarm intelligence."""

    def __init__(
        self,
        classifier: Optional[SwarmClassifier] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._classifier = classifier or SwarmClassifier()
        self._enable_dashboard = enable_dashboard
        self._last_result: Optional[SwarmResult] = None

    @property
    def classifier(self) -> SwarmClassifier:
        return self._classifier

    @property
    def last_result(self) -> Optional[SwarmResult]:
        return self._last_result

    def get_name(self) -> str:
        return "SwarmMiddleware"

    def get_priority(self) -> int:
        return 269

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzswarm import SwarmMiddlewareError

        context = next_handler(context)

        try:
            result = self._classifier.classify(context.number)
            self._last_result = result
            context.metadata["swarm_label"] = result.label
            context.metadata["swarm_consensus"] = result.consensus
            context.metadata["swarm_aco"] = result.aco_label
            context.metadata["swarm_pso"] = result.pso_label
            context.metadata["swarm_bee"] = result.bee_label
        except SwarmMiddlewareError:
            raise
        except Exception as exc:
            raise SwarmMiddlewareError(context.number, str(exc)) from exc

        return context

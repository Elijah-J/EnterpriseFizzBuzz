"""
Enterprise FizzBuzz Platform - FizzLife Integration Layer

Provides the middleware, evolutionary discovery, orchestration, and
visualization components that integrate the FizzLife continuous cellular
automaton engine with the Enterprise FizzBuzz Platform pipeline.

The core simulation engine (LeniaGrid, FFTConvolver, SpeciesCatalog, etc.)
resides in fizzlife.py. This module builds on that foundation to provide:

1. **FizzLifeMiddleware**: An IMiddleware implementation that seeds a Lenia
   simulation from each input number, runs it to convergence, and maps the
   emergent species classification to a FizzBuzz output. This replaces naive
   modulo arithmetic with biologically plausible pattern formation.

2. **FizzLifeEvolver**: A genetic algorithm wrapper that discovers novel
   Lenia species by evolving kernel and growth parameters. Each chromosome
   encodes a complete Lenia parameter set; fitness is evaluated by running
   a simulation and measuring stability, diversity, and classification
   accuracy. The evolver integrates with the existing GA infrastructure
   patterns but implements its own selection and mutation loop tailored to
   continuous parameter optimization.

3. **FizzLifeSimulator**: A high-level orchestrator that coordinates a
   complete simulation run, including grid initialization, generation
   stepping, equilibrium detection, species classification, and event
   emission. Provides both a batch run() method and an incremental step()
   method for integration with different pipeline modes.

4. **FizzLifeDashboard**: An enhanced ASCII visualization that renders the
   current grid state with density-mapped characters, box-drawing borders,
   species identification, and statistical summaries. Supports ANSI color
   output for terminals that accept it.

5. **create_fizzlife_subsystem**: Factory function that wires all components
   together with consistent configuration and event routing.

Key Components:
    - FizzLifeMiddleware: IMiddleware for pipeline integration
    - FizzLifeEvolver: GA-based Lenia species discovery
    - FizzLifeSimulator: high-level simulation orchestrator
    - FizzLifeDashboard: enhanced ASCII grid visualization
    - create_fizzlife_subsystem: factory wiring function
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FizzLifeConvergenceError,
    FizzLifeError,
    FizzLifeGridInitializationError,
    FizzLifeSpeciesClassificationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzClassification,
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.fizzlife import (
    DEFAULT_DT,
    DEFAULT_GENERATIONS,
    DEFAULT_GRID_SIZE,
    DEFAULT_KERNEL_RADIUS,
    DEFAULT_MU,
    DEFAULT_SIGMA,
    DENSITY_CHARS,
    EQUILIBRIUM_MASS_DELTA,
    EXTINCTION_MASS_THRESHOLD,
    FIZZLIFE_VERSION,
    POPULATION_THRESHOLD,
    FFTConvolver,
    FlowField,
    GrowthConfig,
    GrowthFunction,
    GrowthType,
    GenerationReport,
    KernelConfig,
    KernelType,
    LeniaGrid,
    LeniaKernel,
    PatternAnalyzer,
    SimulationConfig,
    SimulationResult,
    SimulationState,
    SpeciesCatalog,
    SpeciesFingerprint,
)

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

MIDDLEWARE_PRIORITY = 125
"""FizzLife middleware priority in the processing pipeline."""

EVOLVER_POPULATION_SIZE = 30
"""Default population size for the evolutionary species discovery loop."""

EVOLVER_TOURNAMENT_SIZE = 5
"""Tournament selection size for the FizzLifeEvolver."""

EVOLVER_MUTATION_RATE = 0.15
"""Probability of mutating each gene in a chromosome."""

EVOLVER_CROSSOVER_RATE = 0.7
"""Probability of performing crossover between two parents."""

EVOLVER_ELITISM_COUNT = 2
"""Number of elite individuals preserved across generations."""

DASHBOARD_GRID_HEIGHT = 20
"""Maximum grid rows rendered in the dashboard visualization."""


# ============================================================
# Data Structures
# ============================================================


@dataclass
class EvolverChromosome:
    """Encodes a complete Lenia parameter set as an evolvable chromosome.

    Each chromosome represents a point in the continuous Lenia parameter
    space. The genetic algorithm explores this space by mutating and
    recombining chromosomes, evaluating their fitness through simulation,
    and selecting the fittest for reproduction.

    The parameter encoding uses direct real-valued representation rather
    than binary encoding, as the Lenia parameter space is inherently
    continuous and benefits from Gaussian mutation operators.

    Attributes:
        mu: Growth function center parameter.
        sigma: Growth function width parameter.
        kernel_radius: Convolution kernel radius in grid cells.
        kernel_type: Index into KernelType enum (0=EXP, 1=POLY, 2=RECT).
        beta_vector: Weights for multi-ring kernel shells.
        chromosome_id: Unique identifier for lineage tracking.
        generation: The evolutionary generation of origin.
        fitness: Most recently evaluated fitness score.
        parent_ids: Identifiers of parent chromosomes.
    """

    mu: float = DEFAULT_MU
    sigma: float = DEFAULT_SIGMA
    kernel_radius: int = DEFAULT_KERNEL_RADIUS
    kernel_type: int = 0
    beta_vector: list[float] = field(default_factory=lambda: [1.0])
    chromosome_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    generation: int = 0
    fitness: float = 0.0
    parent_ids: list[str] = field(default_factory=list)

    def clone(self) -> EvolverChromosome:
        """Create a deep copy with a new chromosome ID."""
        return EvolverChromosome(
            mu=self.mu,
            sigma=self.sigma,
            kernel_radius=self.kernel_radius,
            kernel_type=self.kernel_type,
            beta_vector=list(self.beta_vector),
            chromosome_id=str(uuid.uuid4())[:8],
            generation=self.generation,
            fitness=0.0,
            parent_ids=[self.chromosome_id],
        )

    def to_simulation_config(self) -> SimulationConfig:
        """Convert this chromosome to a SimulationConfig for evaluation.

        Maps the encoded parameters back to the concrete configuration
        objects used by the Lenia simulation engine.

        Returns:
            A SimulationConfig parameterized by this chromosome.
        """
        kernel_types = [KernelType.EXPONENTIAL, KernelType.POLYNOMIAL,
                        KernelType.RECTANGULAR]
        kt = kernel_types[self.kernel_type % len(kernel_types)]

        return SimulationConfig(
            grid_size=DEFAULT_GRID_SIZE,
            generations=min(DEFAULT_GENERATIONS, 100),
            dt=DEFAULT_DT,
            kernel=KernelConfig(
                kernel_type=kt,
                radius=self.kernel_radius,
                rank=len(self.beta_vector),
                beta=list(self.beta_vector),
            ),
            growth=GrowthConfig(
                growth_type=GrowthType.GAUSSIAN,
                mu=self.mu,
                sigma=self.sigma,
            ),
        )

    def fingerprint(self) -> str:
        """Generate a canonical fingerprint for deduplication.

        The fingerprint is derived from the parameter values, enabling
        detection of convergent evolution where different lineages arrive
        at the same parameter configuration.

        Returns:
            A 12-character hexadecimal fingerprint string.
        """
        data = f"{self.mu:.6f}:{self.sigma:.6f}:{self.kernel_radius}:" \
               f"{self.kernel_type}:{self.beta_vector}"
        return hashlib.md5(data.encode()).hexdigest()[:12]

    def __repr__(self) -> str:
        return (
            f"EvolverChromosome({self.chromosome_id} "
            f"mu={self.mu:.4f} sigma={self.sigma:.4f} "
            f"R={self.kernel_radius} fit={self.fitness:.4f})"
        )


@dataclass
class EvolverReport:
    """Summary report for one generation of evolutionary species discovery.

    Attributes:
        generation: The evolutionary generation number.
        best_fitness: Fitness of the top individual.
        mean_fitness: Average fitness across the population.
        worst_fitness: Fitness of the weakest individual.
        diversity: Population diversity metric (unique fingerprints).
        best_chromosome: The fittest chromosome this generation.
        species_discovered: Names of species matched by top individuals.
        elapsed_seconds: Wall-clock time for this generation.
    """

    generation: int
    best_fitness: float
    mean_fitness: float
    worst_fitness: float
    diversity: float
    best_chromosome: Optional[EvolverChromosome] = None
    species_discovered: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ============================================================
# FizzLifeMiddleware
# ============================================================


class FizzLifeMiddleware(IMiddleware):
    """IMiddleware implementation for FizzLife continuous cellular automaton evaluation.

    Integrates the FizzLife simulation engine into the Enterprise FizzBuzz
    Platform middleware pipeline. For each input number, the middleware:

    1. Seeds the Lenia grid deterministically from the input number.
    2. Runs the simulation for the configured number of generations.
    3. Classifies the emergent pattern via the SpeciesCatalog.
    4. Maps the species to a FizzBuzz classification.
    5. Emits a FIZZLIFE_PATTERN_CLASSIFIED event for downstream observers.

    This ensures that every FizzBuzz evaluation is grounded in the emergent
    dynamics of a continuous cellular automaton, rather than relying on the
    computationally trivial (and therefore insufficiently enterprise-grade)
    modulo operator.

    The middleware is non-blocking with respect to the pipeline: it enriches
    the processing context with FizzLife metadata but delegates final output
    determination to downstream middleware via next_handler.
    """

    MIDDLEWARE_PRIORITY = MIDDLEWARE_PRIORITY

    def __init__(
        self,
        simulator: FizzLifeSimulator,
        config: SimulationConfig,
        event_callback: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self._simulator = simulator
        self._config = config
        self._event_callback = event_callback
        self._invocation_count = 0
        self._total_simulation_time = 0.0

        logger.info(
            "FizzLifeMiddleware initialized: grid=%d, gens=%d, priority=%d",
            config.grid_size, config.generations, self.MIDDLEWARE_PRIORITY,
        )

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the FizzLife simulation pipeline.

        Seeds a Lenia simulation from context.number, runs it to convergence
        or extinction, classifies the result, and attaches the classification
        as metadata on the processing context before delegating to the next
        handler.

        Args:
            context: The current processing context with the input number.
            next_handler: The next middleware in the pipeline chain.

        Returns:
            The enriched processing context after downstream processing.
        """
        number = context.number
        self._invocation_count += 1

        start = time.monotonic()

        # Run simulation seeded from the input number
        result = self._simulator.run(seed_number=number)

        elapsed = time.monotonic() - start
        self._total_simulation_time += elapsed

        # Attach FizzLife metadata to context
        context.metadata["fizzlife_classification"] = result.classification
        context.metadata["fizzlife_species"] = (
            result.species_history[-1] if result.species_history else "Unknown"
        )
        context.metadata["fizzlife_generations_run"] = result.generations_run
        context.metadata["fizzlife_final_mass"] = result.final_mass
        context.metadata["fizzlife_final_population"] = result.final_population
        context.metadata["fizzlife_elapsed_ms"] = elapsed * 1000

        # Emit classification event
        self._emit_event(EventType.RULE_EVALUATED, {
            "number": number,
            "classification": result.classification,
            "species": context.metadata["fizzlife_species"],
            "generations_run": result.generations_run,
            "elapsed_ms": elapsed * 1000,
        })

        logger.debug(
            "FizzLifeMiddleware processed n=%d: classification=%r, "
            "species=%s, gens=%d, elapsed=%.3fms",
            number, result.classification,
            context.metadata["fizzlife_species"],
            result.generations_run, elapsed * 1000,
        )

        return next_handler(context)

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event through the configured callback, if present."""
        if self._event_callback is not None:
            event = Event(
                event_type=event_type,
                payload=payload,
                source="FizzLifeMiddleware",
            )
            self._event_callback(event)

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "FizzLifeMiddleware"

    def get_priority(self) -> int:
        """Return the middleware pipeline priority."""
        return self.MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority (125)."""
        return self.MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "FizzLifeMiddleware"

    @property
    def invocation_count(self) -> int:
        """Return the total number of middleware invocations."""
        return self._invocation_count

    @property
    def total_simulation_time(self) -> float:
        """Return cumulative simulation time in seconds."""
        return self._total_simulation_time

    @property
    def average_simulation_time_ms(self) -> float:
        """Return average per-number simulation time in milliseconds."""
        if self._invocation_count == 0:
            return 0.0
        return (self._total_simulation_time / self._invocation_count) * 1000


# ============================================================
# FizzLifeEvolver
# ============================================================


class FizzLifeEvolver:
    """Evolutionary discovery of novel Lenia species via genetic algorithm.

    The evolver searches the continuous Lenia parameter space for parameter
    configurations that produce stable, classifiable patterns. Each individual
    in the population encodes a complete set of Lenia parameters (mu, sigma,
    kernel_radius, kernel_type, beta_vector) as a real-valued chromosome.

    Fitness evaluation runs a full Lenia simulation for each chromosome and
    scores the result on three axes:

    - **Stability** (weight 0.4): Did the simulation converge to equilibrium
      rather than going extinct? Stable patterns indicate a viable region of
      parameter space.

    - **Diversity** (weight 0.3): How different is this chromosome from others
      in the population? Diversity pressure prevents premature convergence to
      a single species.

    - **Classification accuracy** (weight 0.3): Does the emergent pattern
      match a known species in the SpeciesCatalog? Matching a known species
      validates that the parameters produce biologically meaningful dynamics.

    The evolutionary operators are:

    - **Tournament selection**: Select parents via k-tournament (k=5 default).
    - **Gaussian mutation**: Add N(0, sigma) noise to continuous parameters.
    - **Uniform crossover**: Swap parameter values between parents with 50%
      probability per parameter.
    - **Elitism**: Preserve the top-N individuals unchanged across generations.

    Usage:
        evolver = FizzLifeEvolver()
        reports = evolver.evolve(generations=50)
        best = evolver.best_chromosome
    """

    def __init__(
        self,
        population_size: int = EVOLVER_POPULATION_SIZE,
        tournament_size: int = EVOLVER_TOURNAMENT_SIZE,
        mutation_rate: float = EVOLVER_MUTATION_RATE,
        crossover_rate: float = EVOLVER_CROSSOVER_RATE,
        elitism_count: int = EVOLVER_ELITISM_COUNT,
        seed: Optional[int] = None,
        event_callback: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self._population_size = population_size
        self._tournament_size = min(tournament_size, population_size)
        self._mutation_rate = mutation_rate
        self._crossover_rate = crossover_rate
        self._elitism_count = min(elitism_count, population_size)
        self._rng = random.Random(seed)
        self._event_callback = event_callback
        self._catalog = SpeciesCatalog()
        self._analyzer = PatternAnalyzer(self._catalog)

        self._population: list[EvolverChromosome] = []
        self._generation = 0
        self._best_chromosome: Optional[EvolverChromosome] = None
        self._hall_of_fame: list[EvolverChromosome] = []
        self._reports: list[EvolverReport] = []

        logger.info(
            "FizzLifeEvolver initialized: pop=%d, tournament=%d, "
            "mutation=%.2f, crossover=%.2f, elitism=%d",
            population_size, self._tournament_size,
            mutation_rate, crossover_rate, self._elitism_count,
        )

    @property
    def population(self) -> list[EvolverChromosome]:
        """Return the current population."""
        return list(self._population)

    @property
    def generation(self) -> int:
        """Return the current evolutionary generation."""
        return self._generation

    @property
    def best_chromosome(self) -> Optional[EvolverChromosome]:
        """Return the all-time best chromosome."""
        return self._best_chromosome

    @property
    def hall_of_fame(self) -> list[EvolverChromosome]:
        """Return the hall of fame (top individuals across all generations)."""
        return list(self._hall_of_fame)

    @property
    def reports(self) -> list[EvolverReport]:
        """Return all evolutionary generation reports."""
        return list(self._reports)

    def initialize_population(self) -> None:
        """Seed the initial population with random parameter configurations.

        Generates chromosomes by sampling uniformly across the viable region
        of Lenia parameter space. The viable region is defined by empirical
        observation: mu in [0.05, 0.30], sigma in [0.005, 0.05], radius in
        [8, 20], with 1-3 kernel rings.
        """
        self._population = []
        for _ in range(self._population_size):
            num_rings = self._rng.randint(1, 3)
            beta = [self._rng.uniform(0.3, 1.0) for _ in range(num_rings)]

            chromosome = EvolverChromosome(
                mu=self._rng.uniform(0.05, 0.30),
                sigma=self._rng.uniform(0.005, 0.05),
                kernel_radius=self._rng.randint(8, 20),
                kernel_type=self._rng.randint(0, 2),
                beta_vector=beta,
                generation=0,
            )
            self._population.append(chromosome)

        logger.debug(
            "Initialized population of %d chromosomes", len(self._population)
        )

    def evaluate_fitness(self, chromosome: EvolverChromosome) -> float:
        """Evaluate the fitness of a single chromosome by simulation.

        Runs a Lenia simulation with the chromosome's parameters and scores
        the result on stability, diversity, and classification accuracy.

        Args:
            chromosome: The chromosome to evaluate.

        Returns:
            The composite fitness score in [0, 1].
        """
        config = chromosome.to_simulation_config()

        # Run simulation with reduced generation count for speed
        grid = LeniaGrid(config)
        reports: list[GenerationReport] = []

        for _ in range(config.generations):
            report = grid.step()
            reports.append(report)
            if report.state == SimulationState.EXTINCT:
                break

        # Stability score: did the simulation survive?
        if not reports:
            stability = 0.0
        elif reports[-1].state == SimulationState.EXTINCT:
            # Partial credit for surviving longer before extinction
            stability = len(reports) / config.generations * 0.3
        else:
            # Check for equilibrium convergence
            if self._analyzer.detect_equilibrium(reports):
                stability = 1.0
            else:
                # Still running at max generations: moderate stability
                stability = 0.6

        # Classification score: does it match a known species?
        species = self._catalog.classify(config)
        classification = 0.0
        if species is not None:
            classification = 1.0
        elif stability > 0.5:
            # Unknown but stable pattern: partial credit
            classification = 0.3

        # Diversity score: computed relative to population during selection
        # For individual evaluation, use parameter distance from defaults
        default_mu = DEFAULT_MU
        default_sigma = DEFAULT_SIGMA
        mu_dist = abs(chromosome.mu - default_mu)
        sigma_dist = abs(chromosome.sigma - default_sigma)
        diversity = min(1.0, (mu_dist + sigma_dist) * 10.0)

        # Composite fitness
        fitness = (
            0.4 * stability
            + 0.3 * classification
            + 0.3 * diversity
        )

        chromosome.fitness = fitness
        return fitness

    def _tournament_select(self) -> EvolverChromosome:
        """Select a parent via tournament selection.

        Randomly samples tournament_size individuals from the population
        and returns the one with the highest fitness.

        Returns:
            The tournament winner.
        """
        candidates = self._rng.sample(
            self._population,
            min(self._tournament_size, len(self._population)),
        )
        return max(candidates, key=lambda c: c.fitness)

    def _crossover(
        self, parent_a: EvolverChromosome, parent_b: EvolverChromosome
    ) -> EvolverChromosome:
        """Perform uniform crossover between two parent chromosomes.

        Each parameter is independently inherited from one parent with
        50% probability. The beta vector is inherited from whichever
        parent is selected for the kernel_type parameter, maintaining
        kernel configuration coherence.

        Args:
            parent_a: First parent chromosome.
            parent_b: Second parent chromosome.

        Returns:
            A new offspring chromosome.
        """
        child = EvolverChromosome(
            mu=parent_a.mu if self._rng.random() < 0.5 else parent_b.mu,
            sigma=parent_a.sigma if self._rng.random() < 0.5 else parent_b.sigma,
            kernel_radius=(
                parent_a.kernel_radius
                if self._rng.random() < 0.5
                else parent_b.kernel_radius
            ),
            generation=self._generation + 1,
            parent_ids=[parent_a.chromosome_id, parent_b.chromosome_id],
        )

        # Kernel type and beta vector are inherited together
        if self._rng.random() < 0.5:
            child.kernel_type = parent_a.kernel_type
            child.beta_vector = list(parent_a.beta_vector)
        else:
            child.kernel_type = parent_b.kernel_type
            child.beta_vector = list(parent_b.beta_vector)

        return child

    def _mutate(self, chromosome: EvolverChromosome) -> EvolverChromosome:
        """Apply Gaussian mutation to a chromosome's continuous parameters.

        Each parameter is independently mutated with probability equal to
        the configured mutation rate. Continuous parameters receive additive
        Gaussian noise; discrete parameters (kernel_type, radius) receive
        uniform perturbation.

        Mutation magnitudes are calibrated to the scale of each parameter:
        small for sigma (order 0.001), moderate for mu (order 0.01), and
        integer-valued for radius and kernel_type.

        Args:
            chromosome: The chromosome to mutate (modified in place).

        Returns:
            The mutated chromosome (same object).
        """
        if self._rng.random() < self._mutation_rate:
            chromosome.mu += self._rng.gauss(0, 0.02)
            chromosome.mu = max(0.01, min(0.50, chromosome.mu))

        if self._rng.random() < self._mutation_rate:
            chromosome.sigma += self._rng.gauss(0, 0.005)
            chromosome.sigma = max(0.001, min(0.10, chromosome.sigma))

        if self._rng.random() < self._mutation_rate:
            chromosome.kernel_radius += self._rng.choice([-2, -1, 1, 2])
            chromosome.kernel_radius = max(5, min(25, chromosome.kernel_radius))

        if self._rng.random() < self._mutation_rate:
            chromosome.kernel_type = self._rng.randint(0, 2)

        if self._rng.random() < self._mutation_rate:
            # Mutate a random beta value or add/remove a ring
            if len(chromosome.beta_vector) > 1 and self._rng.random() < 0.2:
                chromosome.beta_vector.pop()
            elif len(chromosome.beta_vector) < 4 and self._rng.random() < 0.2:
                chromosome.beta_vector.append(self._rng.uniform(0.1, 1.0))
            else:
                idx = self._rng.randint(0, len(chromosome.beta_vector) - 1)
                chromosome.beta_vector[idx] += self._rng.gauss(0, 0.1)
                chromosome.beta_vector[idx] = max(
                    0.05, min(2.0, chromosome.beta_vector[idx])
                )

        return chromosome

    def _compute_population_diversity(self) -> float:
        """Compute population diversity as fraction of unique fingerprints.

        Returns:
            Diversity score in [0, 1] where 1 means all individuals are unique.
        """
        if not self._population:
            return 0.0
        fingerprints = set(c.fingerprint() for c in self._population)
        return len(fingerprints) / len(self._population)

    def _update_hall_of_fame(self, max_size: int = 10) -> None:
        """Update the hall of fame with the current generation's best.

        Maintains a sorted list of the top-N all-time individuals,
        deduplicated by fingerprint.
        """
        existing_fps = set(c.fingerprint() for c in self._hall_of_fame)

        for chromosome in self._population:
            fp = chromosome.fingerprint()
            if fp not in existing_fps:
                self._hall_of_fame.append(chromosome)
                existing_fps.add(fp)

        self._hall_of_fame.sort(key=lambda c: c.fitness, reverse=True)
        self._hall_of_fame = self._hall_of_fame[:max_size]

    def evolve(self, generations: int = 20) -> list[EvolverReport]:
        """Run the evolutionary loop for the specified number of generations.

        Initializes the population if not already done, then iterates
        through selection, crossover, mutation, and evaluation for each
        generation.

        Args:
            generations: Number of evolutionary generations to run.

        Returns:
            List of EvolverReport objects, one per generation.
        """
        if not self._population:
            self.initialize_population()

        reports: list[EvolverReport] = []

        for gen in range(generations):
            gen_start = time.monotonic()
            self._generation += 1

            # Evaluate fitness for all individuals
            for chromosome in self._population:
                self.evaluate_fitness(chromosome)

            # Sort by fitness (descending)
            self._population.sort(key=lambda c: c.fitness, reverse=True)

            # Update best and hall of fame
            if self._population:
                gen_best = self._population[0]
                if (
                    self._best_chromosome is None
                    or gen_best.fitness > self._best_chromosome.fitness
                ):
                    self._best_chromosome = gen_best

            self._update_hall_of_fame()

            # Compute generation statistics
            fitnesses = [c.fitness for c in self._population]
            diversity = self._compute_population_diversity()

            # Identify species matches
            species_found: list[str] = []
            for chrom in self._population[:5]:
                species = self._catalog.classify(chrom.to_simulation_config())
                if species and species.name not in species_found:
                    species_found.append(species.name)

            gen_elapsed = time.monotonic() - gen_start

            report = EvolverReport(
                generation=self._generation,
                best_fitness=fitnesses[0] if fitnesses else 0.0,
                mean_fitness=sum(fitnesses) / len(fitnesses) if fitnesses else 0.0,
                worst_fitness=fitnesses[-1] if fitnesses else 0.0,
                diversity=diversity,
                best_chromosome=self._population[0] if self._population else None,
                species_discovered=species_found,
                elapsed_seconds=gen_elapsed,
            )
            reports.append(report)
            self._reports.append(report)

            # Emit generation event
            self._emit_event(EventType.RULE_EVALUATED, {
                "evolver_generation": self._generation,
                "best_fitness": report.best_fitness,
                "mean_fitness": report.mean_fitness,
                "diversity": diversity,
                "species_discovered": species_found,
            })

            logger.debug(
                "Evolver gen %d: best=%.4f, mean=%.4f, diversity=%.2f, "
                "species=%s, elapsed=%.3fs",
                self._generation, report.best_fitness, report.mean_fitness,
                diversity, species_found, gen_elapsed,
            )

            # Produce next generation
            next_population: list[EvolverChromosome] = []

            # Elitism: preserve top individuals
            for i in range(min(self._elitism_count, len(self._population))):
                elite = self._population[i].clone()
                elite.fitness = self._population[i].fitness
                elite.generation = self._generation + 1
                next_population.append(elite)

            # Fill remaining slots with offspring
            while len(next_population) < self._population_size:
                parent_a = self._tournament_select()
                parent_b = self._tournament_select()

                if self._rng.random() < self._crossover_rate:
                    offspring = self._crossover(parent_a, parent_b)
                else:
                    offspring = parent_a.clone()
                    offspring.generation = self._generation + 1

                self._mutate(offspring)
                next_population.append(offspring)

            self._population = next_population

        return reports

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event through the configured callback."""
        if self._event_callback is not None:
            event = Event(
                event_type=event_type,
                payload=payload,
                source="FizzLifeEvolver",
            )
            self._event_callback(event)


# ============================================================
# FizzLife Dashboard (Enhanced)
# ============================================================


class FizzLifeIntegrationDashboard:
    """Enhanced ASCII visualization of FizzLife simulation state.

    Renders a terminal-friendly dashboard with box-drawing borders,
    density-mapped grid state, statistical panels, and species
    identification. Supports ANSI color output for terminals that
    accept escape sequences.

    The density mapping uses a graduated character set that maps
    continuous cell states in [0, 1] to increasing visual density:
    space (empty), dots (trace), colons (low), equals (medium),
    plus (moderate), asterisk (high), hash (dense), percent (very
    dense), at-sign (maximum).

    Grid Layout:
        +------------------------------------------+
        | FIZZLIFE SIMULATION DASHBOARD            |
        +------------------------------------------+
        | Generation: 142/200  State: CONVERGED    |
        | Population: 47       Mass: 12.3456       |
        | Species: Orbium unicaudatus (Fizz)       |
        +------------------------------------------+
        | Grid (64x64):                            |
        |  ..::-==+**##%%@@...                     |
        |  ..::--==+**##%%@@..                     |
        |  ...                                     |
        +------------------------------------------+

    Usage:
        dashboard = FizzLifeIntegrationDashboard()
        output = dashboard.render(grid, report, species_info)
        print(output)
    """

    DENSITY_CHARS = DENSITY_CHARS

    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        self._config = config or SimulationConfig()
        self._width = 72
        self._use_ansi = True

    @property
    def width(self) -> int:
        """Return the dashboard rendering width."""
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        """Set the dashboard rendering width."""
        self._width = max(40, value)

    def render(
        self,
        grid: list[list[float]],
        report: Optional[GenerationReport] = None,
        species_info: Optional[SpeciesFingerprint] = None,
    ) -> str:
        """Render a complete dashboard frame for the current simulation state.

        Composes the header, statistics panel, grid visualization, and
        species identification into a single multi-line string suitable
        for terminal display.

        Args:
            grid: The current Lenia grid state (2D float array in [0,1]).
            report: The most recent GenerationReport, if available.
            species_info: The identified species, if classified.

        Returns:
            Multi-line string containing the rendered dashboard.
        """
        w = self._width
        lines: list[str] = []

        # Box-drawing characters
        h_line = "\u2500"
        v_line = "\u2502"
        tl_corner = "\u250c"
        tr_corner = "\u2510"
        bl_corner = "\u2514"
        br_corner = "\u2518"
        t_junction = "\u252c"
        b_junction = "\u2534"
        l_junction = "\u251c"
        r_junction = "\u2524"

        def top_border() -> str:
            return tl_corner + h_line * (w - 2) + tr_corner

        def bottom_border() -> str:
            return bl_corner + h_line * (w - 2) + br_corner

        def mid_border() -> str:
            return l_junction + h_line * (w - 2) + r_junction

        def row(text: str) -> str:
            content = text[:w - 4]
            return f"{v_line} {content:<{w - 4}} {v_line}"

        def center_row(text: str) -> str:
            content = text[:w - 4]
            return f"{v_line} {content:^{w - 4}} {v_line}"

        # Header
        lines.append(top_border())
        lines.append(center_row(
            f"FIZZLIFE CONTINUOUS CELLULAR AUTOMATON v{FIZZLIFE_VERSION}"
        ))
        lines.append(mid_border())

        # Statistics panel
        if report is not None:
            max_gens = self._config.generations
            lines.append(row(
                f"Generation:   {report.generation}/{max_gens}    "
                f"State: {report.state.name}"
            ))
            lines.append(row(
                f"Population:   {report.population:<12}  "
                f"Total Mass: {report.total_mass:.4f}"
            ))
            lines.append(row(
                f"Mass Delta:   {report.mass_delta:+.8f}"
            ))
        else:
            lines.append(row("(awaiting simulation data)"))

        # Species identification
        if species_info is not None:
            classification = self._catalog_classification(species_info.name)
            lines.append(mid_border())
            lines.append(row(
                f"Species:      {species_info.name}"
            ))
            lines.append(row(
                f"Family:       {species_info.family}"
            ))
            if classification:
                lines.append(row(
                    f"Maps to:      {classification}"
                ))
        elif report is not None and report.species_detected:
            lines.append(mid_border())
            lines.append(row(
                f"Species:      {report.species_detected}"
            ))

        # Grid visualization
        lines.append(mid_border())
        grid_size = len(grid)
        lines.append(center_row(f"GRID STATE ({grid_size}x{grid_size})"))
        lines.append(mid_border())

        grid_width = w - 4
        grid_lines = self._render_grid(grid, grid_width, DASHBOARD_GRID_HEIGHT)
        for grid_line in grid_lines:
            lines.append(row(grid_line))

        # Mass summary
        total_mass = sum(sum(row_data) for row_data in grid)
        population = sum(
            1 for row_data in grid for val in row_data
            if val > POPULATION_THRESHOLD
        )
        lines.append(mid_border())
        lines.append(row(
            f"Grid cells: {grid_size * grid_size}    "
            f"Occupied: {population}    "
            f"Mass: {total_mass:.2f}"
        ))

        lines.append(bottom_border())
        return "\n".join(lines)

    def _render_grid(
        self,
        grid: list[list[float]],
        target_width: int,
        max_height: int,
    ) -> list[str]:
        """Render the grid as density-mapped ASCII characters.

        Maps each cell's continuous state value to a character from the
        DENSITY_CHARS palette. The grid is downsampled if necessary to
        fit within the target dimensions.

        Args:
            grid: The 2D grid of float values in [0, 1].
            target_width: Maximum characters per line.
            max_height: Maximum number of lines.

        Returns:
            List of strings, one per rendered row.
        """
        if not grid or not grid[0]:
            return ["(empty grid)"]

        size = len(grid)
        chars = self.DENSITY_CHARS
        max_idx = len(chars) - 1

        # Compute downsampling factors
        x_scale = max(1, math.ceil(size / target_width))
        y_scale = max(1, math.ceil(size / max_height))

        lines: list[str] = []
        for y in range(0, size, y_scale):
            line_chars: list[str] = []
            for x in range(0, size, x_scale):
                if x < size and y < size:
                    val = grid[y][x]
                    idx = int(val * max_idx)
                    idx = max(0, min(max_idx, idx))
                    line_chars.append(chars[idx])
            lines.append("".join(line_chars))

            if len(lines) >= max_height:
                break

        return lines

    def _catalog_classification(self, species_name: str) -> Optional[str]:
        """Look up the FizzBuzz classification for a species name."""
        catalog = SpeciesCatalog()
        return catalog.get_classification(species_name)


# ============================================================
# FizzLife Simulator (Orchestrator)
# ============================================================


class FizzLifeSimulator:
    """Orchestrates a complete FizzLife simulation run.

    The simulator provides a higher-level interface than the raw LeniaGrid
    and FizzLifeEngine, coordinating initialization, stepping, equilibrium
    detection, species classification, and event emission in a single
    coherent API. It serves as the primary entry point for middleware and
    other platform subsystems that need to run FizzLife simulations.

    The simulator supports two usage modes:

    1. **Batch mode** (run): Execute a complete simulation from seed to
       classification in a single call. Suitable for middleware integration
       where the full result is needed synchronously.

    2. **Incremental mode** (step): Advance the simulation one generation
       at a time, returning a GenerationReport after each step. Suitable
       for interactive visualization and dashboard integration.

    Usage:
        simulator = FizzLifeSimulator(config)
        result = simulator.run(seed_number=42)
        print(result.classification)  # "Fizz", "Buzz", "FizzBuzz", or ""
    """

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        event_callback: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self._config = config or SimulationConfig()
        self._event_callback = event_callback
        self._catalog = SpeciesCatalog()
        self._analyzer = PatternAnalyzer(self._catalog)
        self._grid: Optional[LeniaGrid] = None
        self._reports: list[GenerationReport] = []
        self._species_history: list[str] = []
        self._run_id = str(uuid.uuid4())[:12]
        self._start_time: Optional[float] = None
        self._converged = False

        logger.info(
            "FizzLifeSimulator created: run_id=%s, grid=%d, gens=%d",
            self._run_id, self._config.grid_size, self._config.generations,
        )

    @property
    def config(self) -> SimulationConfig:
        """Return the simulation configuration."""
        return self._config

    @property
    def grid(self) -> Optional[LeniaGrid]:
        """Return the simulation grid, if initialized."""
        return self._grid

    @property
    def reports(self) -> list[GenerationReport]:
        """Return all generation reports collected so far."""
        return list(self._reports)

    @property
    def run_id(self) -> str:
        """Return the unique run identifier."""
        return self._run_id

    @property
    def is_running(self) -> bool:
        """Return whether the simulation is currently in progress."""
        return (
            self._grid is not None
            and self._grid.state == SimulationState.RUNNING
        )

    @property
    def is_complete(self) -> bool:
        """Return whether the simulation has terminated."""
        if self._grid is None:
            return False
        return self._grid.state in (
            SimulationState.CONVERGED,
            SimulationState.EXTINCT,
            SimulationState.FAILED,
        )

    def _initialize(self, seed_number: Optional[int] = None) -> None:
        """Initialize the simulation grid.

        Creates a new LeniaGrid with the configured parameters. If a seed
        number is provided, it overrides the config seed for deterministic
        initialization tied to the input number.

        Args:
            seed_number: Optional seed for deterministic grid initialization.
        """
        config = self._config
        if seed_number is not None:
            config = SimulationConfig(
                grid_size=config.grid_size,
                generations=config.generations,
                dt=config.dt,
                kernel=config.kernel,
                growth=config.growth,
                channels=config.channels,
                mass_conservation=config.mass_conservation,
                initial_density=config.initial_density,
                seed=seed_number,
            )

        self._grid = LeniaGrid(config)
        self._reports = []
        self._species_history = []
        self._converged = False
        self._start_time = time.monotonic()
        self._run_id = str(uuid.uuid4())[:12]

        self._emit_event(EventType.SESSION_STARTED, {
            "run_id": self._run_id,
            "grid_size": config.grid_size,
            "generations": config.generations,
            "seed": seed_number,
        })

        logger.debug(
            "FizzLifeSimulator initialized: run_id=%s, seed=%s, mass=%.4f",
            self._run_id, seed_number, self._grid.total_mass(),
        )

    def step(self) -> GenerationReport:
        """Advance the simulation by one generation.

        If the simulation has not been initialized, it is initialized with
        the default configuration (no seed override).

        Returns:
            The GenerationReport for the completed generation.

        Raises:
            FizzLifeConvergenceError: If the simulation has already terminated.
        """
        if self._grid is None:
            self._initialize()

        assert self._grid is not None

        if self._grid.state in (SimulationState.CONVERGED,
                                SimulationState.EXTINCT,
                                SimulationState.FAILED):
            raise FizzLifeConvergenceError(
                generation=len(self._reports),
                mass_history=[r.total_mass for r in self._reports[-10:]],
                reason="Simulation has already terminated",
            )

        report = self._grid.step()
        self._reports.append(report)

        # Check for equilibrium
        if self._analyzer.detect_equilibrium(self._reports):
            self._converged = True
            self._grid.state = SimulationState.CONVERGED
            species = self._analyzer.classify_species(self._config)
            if species:
                report.species_detected = species.name
                if species.name not in self._species_history:
                    self._species_history.append(species.name)

        return report

    def run(self, seed_number: Optional[int] = None) -> SimulationResult:
        """Execute a complete simulation and return the result.

        Initializes the grid (optionally seeded from the input number),
        runs all generations until convergence, extinction, or the maximum
        generation count, then classifies the result and returns a
        SimulationResult.

        Args:
            seed_number: Optional seed for deterministic initialization.

        Returns:
            The complete SimulationResult with classification.
        """
        self._initialize(seed_number)
        assert self._grid is not None

        for gen in range(self._config.generations):
            report = self._grid.step()
            self._reports.append(report)

            # Check for extinction
            if report.state == SimulationState.EXTINCT:
                self._emit_event(EventType.SESSION_ENDED, {
                    "run_id": self._run_id,
                    "reason": "extinction",
                    "generation": gen + 1,
                })
                break

            # Check for equilibrium
            if self._analyzer.detect_equilibrium(self._reports):
                self._converged = True
                self._grid.state = SimulationState.CONVERGED
                species = self._analyzer.classify_species(self._config)
                if species:
                    report.species_detected = species.name
                    if species.name not in self._species_history:
                        self._species_history.append(species.name)

                self._emit_event(EventType.SESSION_ENDED, {
                    "run_id": self._run_id,
                    "reason": "convergence",
                    "generation": gen + 1,
                    "species": species.name if species else None,
                })
                break

        # Compute classification
        classification = self._classify()

        elapsed = time.monotonic() - (self._start_time or time.monotonic())

        result = SimulationResult(
            config=self._config,
            generations_run=len(self._reports),
            final_population=self._reports[-1].population if self._reports else 0,
            final_mass=self._reports[-1].total_mass if self._reports else 0.0,
            species_history=list(self._species_history),
            classification=classification,
            reports=self._reports,
        )

        logger.info(
            "FizzLifeSimulator run complete: run_id=%s, gens=%d, "
            "classification=%r, elapsed=%.3fs",
            self._run_id, len(self._reports), classification, elapsed,
        )

        return result

    def _classify(self) -> str:
        """Determine FizzBuzz classification from simulation outcome.

        Returns:
            "Fizz", "Buzz", "FizzBuzz", or "" (plain number).
        """
        if not self._reports:
            return ""

        final_report = self._reports[-1]

        if final_report.state == SimulationState.EXTINCT:
            return ""

        # Use species classification if available
        for species_name in self._species_history:
            classification = self._catalog.get_classification(species_name)
            if classification:
                return classification

        # Fallback heuristic based on convergence characteristics
        if self._converged and final_report.population > 0:
            density = final_report.total_mass / final_report.population
            if density > 0.7:
                return "Buzz"
            elif density > 0.4:
                return "Fizz"
            else:
                return "FizzBuzz"

        return ""

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event through the configured callback."""
        if self._event_callback is not None:
            event = Event(
                event_type=event_type,
                payload={**payload, "run_id": self._run_id},
                source="FizzLifeSimulator",
            )
            self._event_callback(event)

    def get_current_grid(self) -> Optional[list[list[float]]]:
        """Return the current grid state for visualization.

        Returns:
            The 2D grid array, or None if not initialized.
        """
        if self._grid is None:
            return None
        return self._grid.grid


# ============================================================
# Factory Function
# ============================================================


def create_fizzlife_subsystem(
    config: Optional[SimulationConfig] = None,
    event_callback: Optional[Callable[[Event], None]] = None,
) -> tuple[FizzLifeSimulator, FizzLifeMiddleware, FizzLifeIntegrationDashboard]:
    """Factory function for FizzLife subsystem components.

    Creates and wires together the simulator, middleware, and dashboard
    components with consistent configuration and event routing. This is
    the recommended entry point for subsystem initialization from the
    composition root.

    Args:
        config: Simulation configuration. Uses defaults if None.
        event_callback: Optional callback for event emission to the
            platform event bus.

    Returns:
        Tuple of (simulator, middleware, dashboard), fully wired and
        ready for integration into the middleware pipeline.
    """
    if config is None:
        config = SimulationConfig()

    simulator = FizzLifeSimulator(config, event_callback)
    middleware = FizzLifeMiddleware(simulator, config, event_callback)
    dashboard = FizzLifeIntegrationDashboard(config)

    logger.info(
        "FizzLife subsystem created: grid=%d, gens=%d, middleware_priority=%d",
        config.grid_size, config.generations, MIDDLEWARE_PRIORITY,
    )

    return simulator, middleware, dashboard

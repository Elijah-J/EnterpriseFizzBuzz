"""
Enterprise FizzBuzz Platform - FizzSwarm Swarm Intelligence Test Suite

Comprehensive verification of the three swarm intelligence algorithms (ACO,
PSO, Bee Algorithm) and their ensemble classifier. These tests ensure that
pheromone dynamics converge, particle velocities remain bounded, food sources
are correctly evaluated, and the majority vote produces correct classifications.

Swarm convergence is critical: a divergent particle or collapsed pheromone
trail can lead to incorrect FizzBuzz labels, undermining the collective
intelligence of the platform.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzswarm import (
    DEFAULT_ABANDONMENT_LIMIT,
    DEFAULT_ACO_ITERATIONS,
    DEFAULT_EVAPORATION_RATE,
    DEFAULT_NUM_ANTS,
    DEFAULT_NUM_PARTICLES,
    DEFAULT_PHEROMONE_INIT,
    DEFAULT_V_MAX,
    FIZZBUZZ_CLASSES,
    NUM_CLASSES,
    AntColonyOptimizer,
    AntSolution,
    BeeAlgorithm,
    FoodSource,
    Particle,
    ParticleSwarmOptimizer,
    PheromoneTrail,
    SwarmClassifier,
    SwarmDashboard,
    SwarmMiddleware,
    SwarmResult,
)
from enterprise_fizzbuzz.domain.exceptions.fizzswarm import (
    FizzSwarmError,
    ForagerAllocationError,
    ParticleVelocityDivergenceError,
    PheromoneEvaporationError,
    StigmergyError,
    SwarmConvergenceError,
    SwarmMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def aco():
    return AntColonyOptimizer(num_ants=10, iterations=20, seed=42)


@pytest.fixture
def pso():
    return ParticleSwarmOptimizer(num_particles=10, iterations=20, seed=42)


@pytest.fixture
def bee():
    return BeeAlgorithm(num_employed=5, iterations=20, seed=42)


@pytest.fixture
def make_context():
    def _make(number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-swarm")
    return _make


# ===========================================================================
# Pheromone Trail Tests
# ===========================================================================

class TestPheromoneTrail:
    """Verification of pheromone trail initialization and queries."""

    def test_default_initialization(self):
        trail = PheromoneTrail()
        for cls in FIZZBUZZ_CLASSES:
            assert trail.levels[cls] == DEFAULT_PHEROMONE_INIT

    def test_max_level(self):
        trail = PheromoneTrail()
        trail.levels["Fizz"] = 5.0
        assert trail.max_level() == 5.0

    def test_best_class(self):
        trail = PheromoneTrail()
        trail.levels["FizzBuzz"] = 10.0
        assert trail.best_class() == "FizzBuzz"


# ===========================================================================
# Ant Colony Optimization Tests
# ===========================================================================

class TestAntColonyOptimizer:
    """Verification of the ACO algorithm."""

    def test_classifies_plain_number(self, aco):
        label, trail = aco.optimize(7)
        assert label == "Plain"

    def test_classifies_fizz_number(self, aco):
        label, trail = aco.optimize(9)
        assert label == "Fizz"

    def test_classifies_buzz_number(self, aco):
        label, trail = aco.optimize(10)
        assert label == "Buzz"

    def test_classifies_fizzbuzz_number(self, aco):
        label, trail = aco.optimize(15)
        assert label == "FizzBuzz"

    def test_returns_pheromone_trail(self, aco):
        _, trail = aco.optimize(7)
        assert isinstance(trail, PheromoneTrail)
        assert trail.max_level() > 0


# ===========================================================================
# Particle Swarm Optimization Tests
# ===========================================================================

class TestParticleSwarmOptimizer:
    """Verification of the PSO algorithm."""

    def test_classifies_plain_number(self, pso):
        label, particles = pso.optimize(7)
        assert label == "Plain"

    def test_classifies_fizz_number(self, pso):
        label, particles = pso.optimize(9)
        assert label == "Fizz"

    def test_returns_particles(self, pso):
        _, particles = pso.optimize(7)
        assert len(particles) == 10

    def test_particle_has_correct_dimensions(self, pso):
        _, particles = pso.optimize(7)
        for p in particles:
            assert len(p.position) == NUM_CLASSES
            assert len(p.velocity) == NUM_CLASSES


# ===========================================================================
# Bee Algorithm Tests
# ===========================================================================

class TestBeeAlgorithm:
    """Verification of the Artificial Bee Colony algorithm."""

    def test_classifies_plain_number(self, bee):
        label, sources = bee.optimize(7)
        assert label == "Plain"

    def test_classifies_fizzbuzz_number(self, bee):
        label, sources = bee.optimize(30)
        assert label == "FizzBuzz"

    def test_returns_food_sources(self, bee):
        _, sources = bee.optimize(7)
        assert len(sources) > 0
        for source in sources:
            assert isinstance(source, FoodSource)


# ===========================================================================
# Swarm Classifier Tests
# ===========================================================================

class TestSwarmClassifier:
    """Verification of the ensemble swarm classifier."""

    def test_majority_vote_plain(self):
        classifier = SwarmClassifier()
        result = classifier.classify(7)
        assert result.label == "Plain"

    def test_majority_vote_fizz(self):
        classifier = SwarmClassifier()
        result = classifier.classify(9)
        assert result.label == "Fizz"

    def test_consensus_flag(self):
        classifier = SwarmClassifier()
        result = classifier.classify(15)
        assert result.consensus is True

    def test_all_algorithm_labels_present(self):
        classifier = SwarmClassifier()
        result = classifier.classify(10)
        assert result.aco_label in FIZZBUZZ_CLASSES
        assert result.pso_label in FIZZBUZZ_CLASSES
        assert result.bee_label in FIZZBUZZ_CLASSES


# ===========================================================================
# Dashboard Tests
# ===========================================================================

class TestSwarmDashboard:
    """Verification of the ASCII dashboard rendering."""

    def test_render_produces_output(self):
        result = SwarmResult(
            label="Fizz", aco_label="Fizz", pso_label="Fizz", bee_label="Plain",
            consensus=True, pheromone_trail=PheromoneTrail(),
        )
        output = SwarmDashboard.render(result)
        assert "FIZZSWARM" in output
        assert "Fizz" in output


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestSwarmMiddleware:
    """Verification of the swarm middleware integration."""

    def test_implements_imiddleware(self):
        middleware = SwarmMiddleware()
        assert isinstance(middleware, IMiddleware)

    def test_get_name(self):
        assert SwarmMiddleware().get_name() == "SwarmMiddleware"

    def test_get_priority(self):
        assert SwarmMiddleware().get_priority() == 269

    def test_process_sets_metadata(self, make_context):
        middleware = SwarmMiddleware()
        ctx = make_context(7)
        result = middleware.process(ctx, lambda c: c)
        assert "swarm_label" in result.metadata
        assert "swarm_consensus" in result.metadata

    def test_process_wraps_exceptions(self, make_context):
        middleware = SwarmMiddleware()
        middleware._classifier = MagicMock()
        middleware._classifier.classify.side_effect = RuntimeError("boom")
        with pytest.raises(SwarmMiddlewareError):
            middleware.process(make_context(1), lambda c: c)


# ===========================================================================
# Exception Tests
# ===========================================================================

class TestExceptions:
    """Verification of the FizzSwarm exception hierarchy."""

    def test_pheromone_evaporation_error(self):
        err = PheromoneEvaporationError(0.0001, 0.001)
        assert "0.000100" in str(err)

    def test_velocity_divergence_error(self):
        err = ParticleVelocityDivergenceError(3, 100.0, 2.0)
        assert "Particle 3" in str(err)

    def test_swarm_convergence_error(self):
        err = SwarmConvergenceError(100, 0.5, 0.01)
        assert "100" in str(err)

    def test_stigmergy_error(self):
        err = StigmergyError("negative pheromone detected")
        assert "negative pheromone" in str(err)

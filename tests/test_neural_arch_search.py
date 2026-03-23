"""
Enterprise FizzBuzz Platform - Neural Architecture Search Test Suite

Validates the FizzNAS subsystem: genome encoding/decoding, search space
sampling, fitness evaluation, search strategies, Pareto front analysis,
NAS engine orchestration, and dashboard rendering.

Test budgets are kept deliberately low (5-10 evaluations) to ensure
the test suite completes in under a second while still exercising
all code paths.
"""

from __future__ import annotations

import math
import random

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    NASFitnessEvaluationError,
    InvalidGenomeError,
    NeuralArchitectureSearchError,
    SearchSpaceExhaustedError,
)
from enterprise_fizzbuzz.infrastructure.neural_arch_search import (
    ACTIVATION_FUNCTIONS,
    ArchitectureGenome,
    ConfigurableMLP,
    ConfigurableNeuronLayer,
    DARTSStrategy,
    EvolutionarySearchStrategy,
    FitnessEvaluator,
    FitnessResult,
    NASDashboard,
    NASEngine,
    ParetoFrontAnalyzer,
    RandomSearchStrategy,
    SearchSpace,
    _relu,
    _relu_derivative,
    _tanh,
    _tanh_derivative,
)


# ============================================================
# Activation Function Tests
# ============================================================


class TestActivationFunctions:
    """Verify the mathematical correctness of activation functions."""

    def test_tanh_at_zero(self):
        assert abs(_tanh(0.0)) < 1e-10

    def test_tanh_positive(self):
        result = _tanh(2.0)
        expected = (math.exp(2.0) - math.exp(-2.0)) / (math.exp(2.0) + math.exp(-2.0))
        assert abs(result - expected) < 1e-10

    def test_tanh_negative(self):
        result = _tanh(-3.0)
        assert result < 0.0

    def test_tanh_bounded(self):
        assert -1.0 < _tanh(100.0) <= 1.0
        assert -1.0 <= _tanh(-100.0) < 1.0

    def test_tanh_derivative_at_zero(self):
        output = _tanh(0.0)
        deriv = _tanh_derivative(output)
        assert abs(deriv - 1.0) < 1e-10

    def test_relu_positive(self):
        assert _relu(5.0) == 5.0

    def test_relu_negative(self):
        assert _relu(-3.0) == 0.0

    def test_relu_zero(self):
        assert _relu(0.0) == 0.0

    def test_relu_derivative_positive(self):
        assert _relu_derivative(5.0) == 1.0

    def test_relu_derivative_zero(self):
        assert _relu_derivative(0.0) == 0.0

    def test_activation_registry(self):
        assert "sigmoid" in ACTIVATION_FUNCTIONS
        assert "tanh" in ACTIVATION_FUNCTIONS
        assert "relu" in ACTIVATION_FUNCTIONS

    def test_each_activation_callable(self):
        for name, (fn, deriv_fn) in ACTIVATION_FUNCTIONS.items():
            output = fn(1.0)
            deriv = deriv_fn(output)
            assert isinstance(output, float), f"{name} forward failed"
            assert isinstance(deriv, float), f"{name} derivative failed"


# ============================================================
# ConfigurableNeuronLayer Tests
# ============================================================


class TestConfigurableNeuronLayer:
    """Verify configurable layers with different activations."""

    def test_sigmoid_layer_forward(self):
        rng = random.Random(42)
        layer = ConfigurableNeuronLayer(2, 4, "sigmoid", rng)
        output = layer.forward([0.5, -0.5])
        assert len(output) == 4
        for val in output:
            assert 0.0 < val < 1.0  # sigmoid range

    def test_tanh_layer_forward(self):
        rng = random.Random(42)
        layer = ConfigurableNeuronLayer(2, 4, "tanh", rng)
        output = layer.forward([0.5, -0.5])
        assert len(output) == 4
        for val in output:
            assert -1.0 <= val <= 1.0  # tanh range

    def test_relu_layer_forward(self):
        rng = random.Random(42)
        layer = ConfigurableNeuronLayer(2, 8, "relu", rng)
        output = layer.forward([1.0, 1.0])
        assert len(output) == 8
        for val in output:
            assert val >= 0.0  # relu range

    def test_parameter_count(self):
        rng = random.Random(42)
        layer = ConfigurableNeuronLayer(2, 16, "sigmoid", rng)
        assert layer.parameter_count == 2 * 16 + 16  # weights + biases

    def test_backward_returns_gradients(self):
        rng = random.Random(42)
        layer = ConfigurableNeuronLayer(2, 4, "sigmoid", rng)
        layer.forward([0.5, -0.5])
        grads = layer.backward([1.0, 1.0, 1.0, 1.0], 0.1)
        assert len(grads) == 2

    def test_invalid_activation_raises(self):
        rng = random.Random(42)
        with pytest.raises(InvalidGenomeError):
            ConfigurableNeuronLayer(2, 4, "swish", rng)


# ============================================================
# Architecture Genome Tests
# ============================================================


class TestArchitectureGenome:
    """Verify genome encoding, decoding, and validation."""

    def test_genome_string_roundtrip(self):
        genome = ArchitectureGenome(
            layers=[(16, "sigmoid"), (8, "tanh")],
            learning_rate=0.5,
        )
        genome_str = genome.genome_string
        restored = ArchitectureGenome.from_string(genome_str)
        assert restored.layers == genome.layers
        assert abs(restored.learning_rate - genome.learning_rate) < 1e-3

    def test_genome_string_format(self):
        genome = ArchitectureGenome(
            layers=[(16, "sigmoid")], learning_rate=0.3
        )
        assert "16:sigmoid" in genome.genome_string
        assert "lr=0.3000" in genome.genome_string

    def test_from_string_single_layer(self):
        genome = ArchitectureGenome.from_string("32:relu|lr=1.0000")
        assert genome.layers == [(32, "relu")]
        assert genome.learning_rate == 1.0

    def test_from_string_multi_layer(self):
        genome = ArchitectureGenome.from_string("16:sigmoid|8:tanh|4:relu|lr=0.5000")
        assert len(genome.layers) == 3
        assert genome.depth == 3

    def test_from_string_invalid_width(self):
        with pytest.raises(InvalidGenomeError):
            ArchitectureGenome.from_string("abc:sigmoid|lr=0.5000")

    def test_from_string_invalid_activation(self):
        with pytest.raises(InvalidGenomeError):
            ArchitectureGenome.from_string("16:leaky_relu|lr=0.5000")

    def test_from_string_empty(self):
        with pytest.raises(InvalidGenomeError):
            ArchitectureGenome.from_string("lr=0.5000")

    def test_from_string_malformed(self):
        with pytest.raises(InvalidGenomeError):
            ArchitectureGenome.from_string("16sigmoid|lr=0.5000")

    def test_depth_property(self):
        genome = ArchitectureGenome(layers=[(8, "relu"), (4, "tanh")])
        assert genome.depth == 2

    def test_genome_equality(self):
        a = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        b = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        assert a == b

    def test_genome_hash(self):
        a = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        b = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        assert hash(a) == hash(b)


# ============================================================
# Search Space Tests
# ============================================================


class TestSearchSpace:
    """Verify search space configuration and sampling."""

    def test_default_search_space(self):
        space = SearchSpace()
        assert 4 in space.hidden_sizes
        assert 64 in space.hidden_sizes
        assert "sigmoid" in space.activations
        assert "tanh" in space.activations
        assert "relu" in space.activations
        assert 1 in space.depths
        assert 3 in space.depths

    def test_total_configurations(self):
        space = SearchSpace()
        total = space.total_configurations
        assert total > 0
        # 5 widths * 3 activations = 15 per layer, 4 LRs
        # depth 1: 15^1 * 4 = 60
        # depth 2: 15^2 * 4 = 900
        # depth 3: 15^3 * 4 = 13500
        assert total == 60 + 900 + 13500

    def test_sample_random(self):
        space = SearchSpace()
        rng = random.Random(42)
        genome = space.sample_random(rng)
        assert isinstance(genome, ArchitectureGenome)
        assert genome.depth in space.depths
        for width, act in genome.layers:
            assert width in space.hidden_sizes
            assert act in space.activations
        assert genome.learning_rate in space.learning_rates

    def test_sample_random_diversity(self):
        space = SearchSpace()
        rng = random.Random(42)
        genomes = {space.sample_random(rng).genome_string for _ in range(20)}
        assert len(genomes) > 5  # Should produce diverse architectures

    def test_validate_genome_valid(self):
        space = SearchSpace()
        genome = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        assert space.validate_genome(genome)

    def test_validate_genome_invalid_width(self):
        space = SearchSpace()
        genome = ArchitectureGenome(layers=[(7, "sigmoid")], learning_rate=0.5)
        assert not space.validate_genome(genome)

    def test_validate_genome_invalid_activation(self):
        space = SearchSpace()
        genome = ArchitectureGenome(layers=[(16, "swish")], learning_rate=0.5)
        assert not space.validate_genome(genome)


# ============================================================
# ConfigurableMLP Tests
# ============================================================


class TestConfigurableMLP:
    """Verify MLP construction from genomes and training."""

    def test_build_from_genome(self):
        genome = ArchitectureGenome(layers=[(8, "sigmoid")], learning_rate=0.5)
        rng = random.Random(42)
        mlp = ConfigurableMLP(genome, rng)
        assert mlp.parameter_count > 0

    def test_forward_produces_probability(self):
        genome = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        rng = random.Random(42)
        mlp = ConfigurableMLP(genome, rng)
        output = mlp.forward([0.5, 0.5])
        assert 0.0 <= output <= 1.0

    def test_train_step_reduces_loss(self):
        genome = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        rng = random.Random(42)
        mlp = ConfigurableMLP(genome, rng)

        losses = []
        for _ in range(50):
            loss = mlp.train_step([1.0, 0.0], 1.0, 0.5)
            losses.append(loss)

        # Loss should decrease over training
        assert losses[-1] < losses[0]

    def test_multi_layer_forward(self):
        genome = ArchitectureGenome(
            layers=[(8, "relu"), (4, "tanh")], learning_rate=0.3
        )
        rng = random.Random(42)
        mlp = ConfigurableMLP(genome, rng)
        output = mlp.forward([0.0, 1.0])
        assert 0.0 <= output <= 1.0

    def test_parameter_count_scales_with_depth(self):
        rng = random.Random(42)
        genome_1 = ArchitectureGenome(layers=[(8, "sigmoid")], learning_rate=0.5)
        genome_2 = ArchitectureGenome(
            layers=[(8, "sigmoid"), (8, "sigmoid")], learning_rate=0.5
        )
        mlp_1 = ConfigurableMLP(genome_1, random.Random(42))
        mlp_2 = ConfigurableMLP(genome_2, random.Random(42))
        assert mlp_2.parameter_count > mlp_1.parameter_count


# ============================================================
# Fitness Evaluator Tests
# ============================================================


class TestFitnessEvaluator:
    """Verify fitness evaluation of candidate architectures."""

    def test_evaluate_returns_fitness_result(self):
        evaluator = FitnessEvaluator(divisor=3, train_epochs=10, train_samples=30)
        genome = ArchitectureGenome(layers=[(8, "sigmoid")], learning_rate=0.5)
        result = evaluator.evaluate(genome)
        assert isinstance(result, FitnessResult)
        assert 0.0 <= result.accuracy <= 100.0
        assert result.parameter_count > 0
        assert result.latency_us > 0

    def test_evaluate_baseline_high_accuracy(self):
        evaluator = FitnessEvaluator(divisor=3, train_epochs=100, train_samples=60)
        genome = ArchitectureGenome(layers=[(16, "sigmoid")], learning_rate=0.5)
        result = evaluator.evaluate(genome)
        # The hand-tuned baseline should achieve high accuracy
        assert result.accuracy >= 80.0

    def test_evaluate_different_seeds(self):
        evaluator = FitnessEvaluator(divisor=3, train_epochs=10, train_samples=30)
        genome = ArchitectureGenome(layers=[(8, "sigmoid")], learning_rate=0.5)
        r1 = evaluator.evaluate(genome, eval_index=0)
        r2 = evaluator.evaluate(genome, eval_index=1)
        # Different seeds may produce slightly different results
        assert isinstance(r1, FitnessResult)
        assert isinstance(r2, FitnessResult)

    def test_evaluate_records_training_time(self):
        evaluator = FitnessEvaluator(divisor=3, train_epochs=5, train_samples=20)
        genome = ArchitectureGenome(layers=[(4, "relu")], learning_rate=0.3)
        result = evaluator.evaluate(genome)
        assert result.training_time_ms > 0

    def test_fitness_result_genome_string(self):
        evaluator = FitnessEvaluator(divisor=3, train_epochs=5, train_samples=20)
        genome = ArchitectureGenome(layers=[(8, "tanh")], learning_rate=0.1)
        result = evaluator.evaluate(genome)
        assert result.genome_string == genome.genome_string


# ============================================================
# Random Search Strategy Tests
# ============================================================


class TestRandomSearchStrategy:
    """Verify random search produces the requested number of results."""

    def test_random_search_budget(self):
        space = SearchSpace()
        evaluator = FitnessEvaluator(divisor=3, train_epochs=5, train_samples=20)
        strategy = RandomSearchStrategy(space, evaluator, budget=5, seed=42)
        results = strategy.search()
        assert len(results) == 5

    def test_random_search_diversity(self):
        space = SearchSpace()
        evaluator = FitnessEvaluator(divisor=3, train_epochs=5, train_samples=20)
        strategy = RandomSearchStrategy(space, evaluator, budget=8, seed=42)
        results = strategy.search()
        genome_strings = {r.genome_string for r in results}
        assert len(genome_strings) > 1  # Not all identical


# ============================================================
# Evolutionary Search Strategy Tests
# ============================================================


class TestEvolutionarySearchStrategy:
    """Verify evolutionary search with mutation and crossover."""

    def test_evolutionary_search_budget(self):
        space = SearchSpace()
        evaluator = FitnessEvaluator(divisor=3, train_epochs=5, train_samples=20)
        strategy = EvolutionarySearchStrategy(
            space, evaluator, budget=8, population_size=5,
            tournament_size=3, seed=42,
        )
        results = strategy.search()
        assert len(results) == 8

    def test_evolutionary_search_produces_results(self):
        space = SearchSpace()
        evaluator = FitnessEvaluator(divisor=3, train_epochs=5, train_samples=20)
        strategy = EvolutionarySearchStrategy(
            space, evaluator, budget=6, population_size=4,
            tournament_size=2, seed=42,
        )
        results = strategy.search()
        assert all(isinstance(r, FitnessResult) for r in results)
        assert all(r.accuracy >= 0 for r in results)


# ============================================================
# DARTS Strategy Tests
# ============================================================


class TestDARTSStrategy:
    """Verify DARTS continuous relaxation and discretization."""

    def test_darts_search_produces_results(self):
        space = SearchSpace()
        evaluator = FitnessEvaluator(divisor=3, train_epochs=5, train_samples=20)
        strategy = DARTSStrategy(
            space, evaluator, budget=5, supernet_epochs=3, seed=42,
        )
        results = strategy.search()
        assert len(results) == 5
        assert all(isinstance(r, FitnessResult) for r in results)

    def test_darts_softmax(self):
        probs = DARTSStrategy._softmax([1.0, 2.0, 3.0])
        assert abs(sum(probs) - 1.0) < 1e-10
        assert probs[2] > probs[1] > probs[0]

    def test_darts_softmax_uniform(self):
        probs = DARTSStrategy._softmax([0.0, 0.0, 0.0])
        assert abs(probs[0] - 1.0 / 3) < 1e-10
        assert abs(probs[1] - 1.0 / 3) < 1e-10
        assert abs(probs[2] - 1.0 / 3) < 1e-10


# ============================================================
# Pareto Front Analyzer Tests
# ============================================================


class TestParetoFrontAnalyzer:
    """Verify dominance relations and Pareto front extraction."""

    def _make_result(self, accuracy, params, latency):
        genome = ArchitectureGenome(
            layers=[(params // 3, "sigmoid")],  # approximate
            learning_rate=0.5,
        )
        return FitnessResult(
            genome=genome,
            accuracy=accuracy,
            parameter_count=params,
            latency_us=latency,
            training_epochs=10,
            training_time_ms=1.0,
            converged=True,
        )

    def test_dominates_better_on_all(self):
        a = self._make_result(100.0, 10, 1.0)
        b = self._make_result(90.0, 20, 2.0)
        assert ParetoFrontAnalyzer.dominates(a, b)
        assert not ParetoFrontAnalyzer.dominates(b, a)

    def test_dominates_equal_not_dominated(self):
        a = self._make_result(100.0, 10, 1.0)
        b = self._make_result(100.0, 10, 1.0)
        assert not ParetoFrontAnalyzer.dominates(a, b)
        assert not ParetoFrontAnalyzer.dominates(b, a)

    def test_dominates_trade_off(self):
        a = self._make_result(100.0, 20, 1.0)  # better accuracy, worse params
        b = self._make_result(90.0, 10, 1.0)   # worse accuracy, better params
        assert not ParetoFrontAnalyzer.dominates(a, b)
        assert not ParetoFrontAnalyzer.dominates(b, a)

    def test_extract_pareto_front(self):
        results = [
            self._make_result(100.0, 10, 1.0),   # Pareto optimal
            self._make_result(90.0, 5, 0.5),      # Pareto optimal (fewer params, lower latency)
            self._make_result(80.0, 20, 2.0),      # Dominated by first
        ]
        front = ParetoFrontAnalyzer.extract_pareto_front(results)
        assert len(front) == 2
        assert results[0] in front
        assert results[1] in front

    def test_extract_pareto_front_empty(self):
        front = ParetoFrontAnalyzer.extract_pareto_front([])
        assert front == []

    def test_pareto_ranks(self):
        results = [
            self._make_result(100.0, 10, 1.0),   # Rank 0
            self._make_result(90.0, 20, 2.0),     # Rank 1 (dominated by first)
            self._make_result(80.0, 30, 3.0),     # Rank 2
        ]
        ranks = ParetoFrontAnalyzer.compute_pareto_ranks(results)
        assert ranks[results[0].genome_string] == 0
        assert ranks[results[1].genome_string] == 1
        assert ranks[results[2].genome_string] == 2

    def test_scalarized_rank(self):
        good = self._make_result(100.0, 10, 1.0)
        bad = self._make_result(50.0, 500, 500.0)
        score_good = ParetoFrontAnalyzer.scalarized_rank(good)
        score_bad = ParetoFrontAnalyzer.scalarized_rank(bad)
        assert score_good > score_bad


# ============================================================
# NAS Engine Tests
# ============================================================


class TestNASEngine:
    """Verify the NAS orchestrator end-to-end."""

    def test_engine_random_strategy(self):
        engine = NASEngine(strategy="random", budget=5, seed=42)
        winner = engine.run()
        assert isinstance(winner, FitnessResult)
        assert winner.accuracy >= 0
        assert len(engine.results) == 5
        assert len(engine.pareto_front) > 0
        assert engine.baseline_result is not None

    def test_engine_evolutionary_strategy(self):
        engine = NASEngine(strategy="evolutionary", budget=6, seed=42)
        winner = engine.run()
        assert isinstance(winner, FitnessResult)
        assert len(engine.results) == 6

    def test_engine_darts_strategy(self):
        engine = NASEngine(strategy="darts", budget=5, seed=42)
        winner = engine.run()
        assert isinstance(winner, FitnessResult)
        assert len(engine.results) == 5

    def test_engine_invalid_strategy(self):
        engine = NASEngine(strategy="quantum_annealing", budget=5, seed=42)
        with pytest.raises(InvalidGenomeError):
            engine.run()

    def test_engine_has_baseline(self):
        engine = NASEngine(strategy="random", budget=5, seed=42)
        engine.run()
        assert engine.baseline_result is not None
        assert engine.baseline_result.genome_string == "16:sigmoid|lr=0.5000"

    def test_engine_search_time_recorded(self):
        engine = NASEngine(strategy="random", budget=5, seed=42)
        engine.run()
        assert engine.search_time_ms > 0


# ============================================================
# NAS Dashboard Tests
# ============================================================


class TestNASDashboard:
    """Verify dashboard rendering produces valid ASCII output."""

    def test_dashboard_renders(self):
        engine = NASEngine(strategy="random", budget=5, seed=42)
        engine.run()
        output = NASDashboard.render(engine, width=60)
        assert "FizzNAS" in output
        assert "SEARCH SUMMARY" in output
        assert "TOP ARCHITECTURES" in output
        assert "PARETO FRONT" in output
        assert "NAS WINNER vs BASELINE" in output

    def test_dashboard_contains_winner(self):
        engine = NASEngine(strategy="random", budget=5, seed=42)
        engine.run()
        output = NASDashboard.render(engine, width=60)
        assert "Winner genome:" in output
        assert "Baseline genome:" in output

    def test_dashboard_width(self):
        engine = NASEngine(strategy="random", budget=5, seed=42)
        engine.run()
        output = NASDashboard.render(engine, width=60)
        assert isinstance(output, str)
        assert len(output) > 100  # Non-trivial output


# ============================================================
# Exception Tests
# ============================================================


class TestNASExceptions:
    """Verify NAS exception hierarchy and error codes."""

    def test_nas_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = NeuralArchitectureSearchError("test")
        assert isinstance(err, FizzBuzzError)

    def test_invalid_genome_error(self):
        err = InvalidGenomeError("bad_genome", "too many layers")
        assert "bad_genome" in str(err)
        assert "too many layers" in str(err)
        assert err.error_code == "EFP-NAS01"

    def test_search_space_exhausted_error(self):
        err = SearchSpaceExhaustedError(100, 100)
        assert err.budget == 100
        assert err.evaluated == 100
        assert err.error_code == "EFP-NAS02"

    def test_fitness_evaluation_error(self):
        err = NASFitnessEvaluationError("16:sigmoid", "NaN loss")
        assert err.genome_str == "16:sigmoid"
        assert err.error_code == "EFP-NAS03"

    def test_exception_hierarchy(self):
        assert issubclass(InvalidGenomeError, NeuralArchitectureSearchError)
        assert issubclass(SearchSpaceExhaustedError, NeuralArchitectureSearchError)
        assert issubclass(NASFitnessEvaluationError, NeuralArchitectureSearchError)

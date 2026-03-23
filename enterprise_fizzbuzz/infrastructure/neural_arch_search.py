"""
Enterprise FizzBuzz Platform - Neural Architecture Search (FizzNAS)

Implements automated topology optimization for the mission-critical
MLP-based integer divisibility classification pipeline. Rather than
relying on human intuition to select layer widths and activation
functions — a process fraught with cognitive bias and insufficient
rigor — FizzNAS systematically explores the space of possible network
architectures to discover Pareto-optimal configurations.

Three search strategies are provided:

1. **Random Search** — The humble baseline. Samples architectures
   uniformly at random from the search space. Surprisingly competitive,
   as shown by Li & Talwalkar (2019), because the search space itself
   encodes strong priors about what constitutes a reasonable network
   for checking whether numbers are divisible by 3.

2. **Evolutionary Search** — Tournament selection with mutation and
   crossover, inspired by AmoebaNet's aging evolution. Genomes encoding
   network topologies are bred across generations, with the fittest
   architectures surviving to propagate their layer widths and activation
   genes to the next generation. Natural selection, applied to the
   problem of integer modulo arithmetic.

3. **DARTS** — Differentiable Architecture Search with continuous
   relaxation. Activation function selection is relaxed from a discrete
   choice to a softmax-weighted mixture, enabling gradient-based
   optimization of architecture parameters via bilevel optimization.
   The inner loop trains network weights; the outer loop optimizes
   architecture alphas. After convergence, the continuous relaxation
   is discretized via argmax to produce the final architecture.

All strategies produce candidates that are evaluated on three objectives:
classification accuracy, parameter count, and inference latency. The
Pareto front of non-dominated architectures is extracted and ranked
to select the winning topology.

Dependencies: None (pure stdlib implementation, zero external packages)
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional

from enterprise_fizzbuzz.domain.exceptions import (
    InvalidGenomeError,
    NASFitnessEvaluationError,
)
from enterprise_fizzbuzz.infrastructure.ml_engine import (
    NeuronLayer,
    TrainingDataGenerator,
    _binary_cross_entropy,
    _sigmoid,
)

logger = logging.getLogger(__name__)


# ============================================================
# Activation Functions
# ============================================================


def _tanh(x: float) -> float:
    """Hyperbolic tangent activation function.

    Maps inputs to (-1, 1), providing zero-centered outputs that
    can accelerate convergence in networks trained to determine
    whether integers are divisible by small primes.
    """
    x = max(-500.0, min(500.0, x))
    ex = math.exp(x)
    emx = math.exp(-x)
    return (ex - emx) / (ex + emx)


def _tanh_derivative(output: float) -> float:
    """Derivative of tanh given the tanh output."""
    return 1.0 - output * output


def _relu(x: float) -> float:
    """Rectified Linear Unit activation function.

    The workhorse of modern deep learning, applied here to the
    equally demanding task of learning n % 3 == 0. Returns the
    input if positive, zero otherwise — a piecewise linearity
    that has powered everything from ImageNet classifiers to
    FizzBuzz predictors.
    """
    return max(0.0, x)


def _relu_derivative(output: float) -> float:
    """Derivative of ReLU given the ReLU output."""
    return 1.0 if output > 0.0 else 0.0


ACTIVATION_FUNCTIONS = {
    "sigmoid": (_sigmoid, lambda o: o * (1.0 - o)),
    "tanh": (_tanh, _tanh_derivative),
    "relu": (_relu, _relu_derivative),
}


# ============================================================
# Configurable Neuron Layer
# ============================================================


class ConfigurableNeuronLayer:
    """A fully-connected layer with configurable activation function.

    Extends the base NeuronLayer concept to support sigmoid, tanh,
    and relu activations, enabling the architecture search to explore
    the impact of activation function choice on divisibility
    classification performance.
    """

    def __init__(
        self,
        input_size: int,
        output_size: int,
        activation: str,
        rng: random.Random,
    ) -> None:
        self._input_size = input_size
        self._output_size = output_size
        self._activation_name = activation

        if activation not in ACTIVATION_FUNCTIONS:
            raise InvalidGenomeError(
                f"act={activation}",
                f"Unknown activation function '{activation}'. "
                f"Valid options: {list(ACTIVATION_FUNCTIONS.keys())}",
            )

        self._activate, self._activate_deriv = ACTIVATION_FUNCTIONS[activation]

        # Xavier/Glorot initialization
        scale = math.sqrt(2.0 / (input_size + output_size))
        self.weights: list[list[float]] = [
            [rng.gauss(0.0, scale) for _ in range(input_size)]
            for _ in range(output_size)
        ]
        self.biases: list[float] = [0.0] * output_size

        self._last_input: list[float] = []
        self._last_output: list[float] = []

    @property
    def parameter_count(self) -> int:
        """Total trainable parameters in this layer."""
        return self._output_size * self._input_size + self._output_size

    def forward(self, inputs: list[float]) -> list[float]:
        """Forward pass with configurable activation."""
        self._last_input = inputs
        outputs: list[float] = []
        for j in range(self._output_size):
            z = self.biases[j]
            for i in range(self._input_size):
                z += self.weights[j][i] * inputs[i]
            outputs.append(self._activate(z))
        self._last_output = outputs
        return outputs

    def backward(
        self,
        output_gradients: list[float],
        learning_rate: float,
    ) -> list[float]:
        """Backward pass with activation-specific derivatives."""
        input_gradients: list[float] = [0.0] * self._input_size

        for j in range(self._output_size):
            d_act = self._activate_deriv(self._last_output[j])
            delta = output_gradients[j] * d_act

            for i in range(self._input_size):
                input_gradients[i] += self.weights[j][i] * delta
                self.weights[j][i] -= learning_rate * delta * self._last_input[i]

            self.biases[j] -= learning_rate * delta

        return input_gradients


# ============================================================
# Architecture Genome
# ============================================================


@dataclass
class ArchitectureGenome:
    """Encodes a neural network topology as a genome string.

    The genome format is a pipe-delimited sequence of layer
    specifications, where each layer is encoded as width:activation.
    For example, "16:sigmoid|8:tanh" encodes a two-layer network
    with a 16-neuron sigmoid hidden layer followed by an 8-neuron
    tanh hidden layer (the output layer is always 1:sigmoid and
    is implicit).

    This encoding enables genetic operators — mutation, crossover,
    and random sampling — to manipulate network architectures as
    string-valued chromosomes, bringing the power of evolutionary
    computation to bear on the problem of deciding how many neurons
    should participate in checking divisibility.
    """

    layers: list[tuple[int, str]]  # [(width, activation), ...]
    learning_rate: float = 0.5

    @property
    def genome_string(self) -> str:
        """Serialize the genome to its canonical string representation."""
        layer_strs = [f"{w}:{a}" for w, a in self.layers]
        return "|".join(layer_strs) + f"|lr={self.learning_rate:.4f}"

    @staticmethod
    def from_string(genome_str: str) -> "ArchitectureGenome":
        """Deserialize a genome from its string representation."""
        parts = genome_str.split("|")
        layers: list[tuple[int, str]] = []
        lr = 0.5

        for part in parts:
            if part.startswith("lr="):
                lr = float(part[3:])
            else:
                tokens = part.split(":")
                if len(tokens) != 2:
                    raise InvalidGenomeError(
                        genome_str,
                        f"Malformed layer specification '{part}': expected 'width:activation'",
                    )
                try:
                    width = int(tokens[0])
                except ValueError:
                    raise InvalidGenomeError(
                        genome_str,
                        f"Non-integer layer width '{tokens[0]}'",
                    )
                activation = tokens[1]
                if activation not in ACTIVATION_FUNCTIONS:
                    raise InvalidGenomeError(
                        genome_str,
                        f"Unknown activation '{activation}'",
                    )
                layers.append((width, activation))

        if not layers:
            raise InvalidGenomeError(genome_str, "Genome encodes zero layers")

        return ArchitectureGenome(layers=layers, learning_rate=lr)

    @property
    def depth(self) -> int:
        """Number of hidden layers."""
        return len(self.layers)

    def __hash__(self) -> int:
        return hash(self.genome_string)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ArchitectureGenome):
            return NotImplemented
        return self.genome_string == other.genome_string


# ============================================================
# Search Space
# ============================================================


@dataclass
class SearchSpace:
    """Defines the boundaries of the architecture search space.

    The search space constrains which topologies are considered
    during NAS. Each dimension — layer width, activation function,
    network depth, and learning rate — is bounded to ensure that
    only architecturally sound candidates are evaluated.

    The default configuration explores networks with 1-3 hidden
    layers, widths of 4-64 neurons, three activation functions,
    and four learning rate options. This yields a combinatorial
    space of tens of thousands of possible architectures, all
    dedicated to the singular purpose of classifying integers
    by their remainder when divided by small numbers.
    """

    hidden_sizes: list[int] = field(
        default_factory=lambda: [4, 8, 16, 32, 64]
    )
    activations: list[str] = field(
        default_factory=lambda: ["sigmoid", "tanh", "relu"]
    )
    depths: list[int] = field(default_factory=lambda: [1, 2, 3])
    learning_rates: list[float] = field(
        default_factory=lambda: [0.1, 0.3, 0.5, 1.0]
    )

    @property
    def total_configurations(self) -> int:
        """Total number of distinct architectures in the search space."""
        total = 0
        for depth in self.depths:
            combos_per_layer = len(self.hidden_sizes) * len(self.activations)
            total += (combos_per_layer ** depth) * len(self.learning_rates)
        return total

    def sample_random(self, rng: random.Random) -> ArchitectureGenome:
        """Sample a random architecture uniformly from the search space."""
        depth = rng.choice(self.depths)
        layers: list[tuple[int, str]] = []
        for _ in range(depth):
            width = rng.choice(self.hidden_sizes)
            activation = rng.choice(self.activations)
            layers.append((width, activation))
        lr = rng.choice(self.learning_rates)
        return ArchitectureGenome(layers=layers, learning_rate=lr)

    def validate_genome(self, genome: ArchitectureGenome) -> bool:
        """Check whether a genome falls within the search space bounds."""
        if genome.depth not in self.depths and genome.depth > 0:
            return False
        for width, activation in genome.layers:
            if width not in self.hidden_sizes:
                return False
            if activation not in self.activations:
                return False
        if genome.learning_rate not in self.learning_rates:
            return False
        return True


# ============================================================
# Configurable MLP (built from genome)
# ============================================================


class ConfigurableMLP:
    """A Multi-Layer Perceptron constructed from an ArchitectureGenome.

    Unlike the hand-tuned FizzBuzzNeuralNetwork with its artisanally
    selected 16-neuron sigmoid hidden layer, the ConfigurableMLP
    accepts any topology specified by the genome — variable depth,
    variable width per layer, and per-layer activation function
    selection. This flexibility is essential for NAS to explore
    the full architecture space and determine whether 16 sigmoid
    neurons really is optimal, or whether perhaps 17 would have
    been even better.
    """

    def __init__(self, genome: ArchitectureGenome, rng: random.Random) -> None:
        self._genome = genome
        self._layers: list[ConfigurableNeuronLayer] = []

        # Build hidden layers from genome
        prev_size = 2  # Input: sin and cos features
        for width, activation in genome.layers:
            layer = ConfigurableNeuronLayer(prev_size, width, activation, rng)
            self._layers.append(layer)
            prev_size = width

        # Output layer: always 1 neuron with sigmoid for binary classification
        self._output_layer = ConfigurableNeuronLayer(prev_size, 1, "sigmoid", rng)

    @property
    def parameter_count(self) -> int:
        """Total trainable parameters across all layers."""
        total = self._output_layer.parameter_count
        for layer in self._layers:
            total += layer.parameter_count
        return total

    def forward(self, features: list[float]) -> float:
        """Forward pass through all layers."""
        x = features
        for layer in self._layers:
            x = layer.forward(x)
        out = self._output_layer.forward(x)
        return out[0]

    def train_step(
        self,
        features: list[float],
        target: float,
        learning_rate: float,
    ) -> float:
        """One training step: forward + backward."""
        prediction = self.forward(features)
        loss = _binary_cross_entropy(prediction, target)

        p = max(1e-15, min(1.0 - 1e-15, prediction))
        d_loss = -(target / p) + (1.0 - target) / (1.0 - p)

        grad = self._output_layer.backward([d_loss], learning_rate)
        for layer in reversed(self._layers):
            grad = layer.backward(grad, learning_rate)

        return loss


# ============================================================
# Fitness Evaluator
# ============================================================


@dataclass
class FitnessResult:
    """The measured fitness of a candidate architecture.

    Three objectives are recorded:
    - accuracy: Classification accuracy on the divisibility task (0-100%)
    - parameter_count: Total trainable parameters in the network
    - latency_us: Average inference time per evaluation in microseconds

    These objectives form a three-dimensional fitness landscape over
    which the Pareto front is computed, enabling multi-objective
    architecture selection.
    """

    genome: ArchitectureGenome
    accuracy: float
    parameter_count: int
    latency_us: float
    training_epochs: int
    training_time_ms: float
    converged: bool

    @property
    def genome_string(self) -> str:
        return self.genome.genome_string


class FitnessEvaluator:
    """Evaluates the fitness of a candidate architecture.

    Instantiates a ConfigurableMLP from the genome specification,
    trains it on the divisibility dataset for a divisor of 3 (the
    canonical FizzBuzz modulus), and measures accuracy, parameter
    count, and inference latency. The training budget is kept
    intentionally modest — 100 epochs with 100 samples — to enable
    rapid fitness evaluation during the search loop.

    Each evaluation is a complete train-from-scratch cycle because
    weight sharing across architectures would introduce correlations
    between fitness measurements that could mislead the search
    algorithm. The computational cost of this approach is justified
    by the criticality of finding the optimal FizzBuzz topology.
    """

    def __init__(
        self,
        divisor: int = 3,
        train_epochs: int = 100,
        train_samples: int = 100,
        seed: int = 42,
    ) -> None:
        self._divisor = divisor
        self._train_epochs = train_epochs
        self._train_samples = train_samples
        self._base_seed = seed

    def evaluate(self, genome: ArchitectureGenome, eval_index: int = 0) -> FitnessResult:
        """Evaluate a single architecture genome.

        Builds the network, trains it, and measures all three fitness
        objectives. The eval_index is used to vary the RNG seed across
        evaluations while maintaining reproducibility within each.
        """
        rng = random.Random(self._base_seed + eval_index)

        try:
            network = ConfigurableMLP(genome, rng)
        except Exception as e:
            raise NASFitnessEvaluationError(
                genome.genome_string,
                f"Failed to instantiate network: {e}",
            )

        features, labels = TrainingDataGenerator.generate(
            self._divisor, self._train_samples
        )

        # Train
        lr = genome.learning_rate
        lr_decay = 0.998
        converged = False
        train_start = time.perf_counter_ns()
        epochs_run = 0

        indices = list(range(len(features)))
        for epoch in range(1, self._train_epochs + 1):
            rng.shuffle(indices)
            epoch_loss = 0.0
            for idx in indices:
                loss = network.train_step(features[idx], labels[idx], lr)
                epoch_loss += loss
            avg_loss = epoch_loss / len(features)
            lr *= lr_decay
            epochs_run = epoch

            if avg_loss < 0.01:
                converged = True
                break

        train_time_ms = (time.perf_counter_ns() - train_start) / 1_000_000

        # Measure accuracy
        correct = 0
        for i in range(len(features)):
            pred = network.forward(features[i])
            if (pred > 0.5) == (labels[i] > 0.5):
                correct += 1
        accuracy = correct / len(features) * 100.0

        # Measure inference latency
        latency_start = time.perf_counter_ns()
        n_infer = min(50, len(features))
        for i in range(n_infer):
            network.forward(features[i])
        latency_ns = (time.perf_counter_ns() - latency_start)
        latency_us = latency_ns / 1000.0 / n_infer

        return FitnessResult(
            genome=genome,
            accuracy=accuracy,
            parameter_count=network.parameter_count,
            latency_us=latency_us,
            training_epochs=epochs_run,
            training_time_ms=train_time_ms,
            converged=converged,
        )


# ============================================================
# Search Strategies
# ============================================================


class RandomSearchStrategy:
    """Random architecture sampling — the NAS baseline.

    Samples N random architectures uniformly from the search space,
    evaluates all of them, and returns the complete set of fitness
    results. Li & Talwalkar (2019) demonstrated that this simple
    approach is surprisingly competitive with sophisticated NAS
    methods, especially when the search space is well-designed.

    For FizzBuzz, the search space is extremely well-designed (by
    virtue of the problem being trivial), so random search serves
    as a sanity check: if evolutionary or DARTS strategies cannot
    outperform random sampling, the additional complexity is not
    justified.
    """

    def __init__(
        self,
        search_space: SearchSpace,
        evaluator: FitnessEvaluator,
        budget: int,
        seed: int = 42,
    ) -> None:
        self._space = search_space
        self._evaluator = evaluator
        self._budget = budget
        self._rng = random.Random(seed)

    def search(self) -> list[FitnessResult]:
        """Execute random search across the architecture space."""
        logger.info("  [NAS/Random] Sampling %d random architectures...", self._budget)
        results: list[FitnessResult] = []

        for i in range(self._budget):
            genome = self._space.sample_random(self._rng)
            result = self._evaluator.evaluate(genome, eval_index=i)
            results.append(result)
            logger.info(
                "  [NAS/Random] %d/%d | %s | acc=%.1f%% params=%d lat=%.1fus",
                i + 1,
                self._budget,
                genome.genome_string,
                result.accuracy,
                result.parameter_count,
                result.latency_us,
            )

        return results


class EvolutionarySearchStrategy:
    """Evolutionary NAS with tournament selection and aging.

    Implements an evolution strategy inspired by AmoebaNet's aging
    evolution algorithm. A population of architecture genomes is
    maintained and evolved through:

    1. **Tournament selection**: Sample a tournament of S individuals,
       select the fittest as a parent.
    2. **Mutation**: Apply one of three mutation operators —
       width mutation (change layer width), activation mutation
       (change layer activation), or depth mutation (add/remove layer).
    3. **Crossover**: With probability p_crossover, combine two
       parents by swapping layer segments.
    4. **Aging**: Remove the oldest individual from the population
       each generation, regardless of fitness, to prevent stagnation.

    The evolutionary pressure drives the population toward high-fitness
    regions of the architecture space, while aging ensures continued
    exploration. After the budget is exhausted, all evaluated
    architectures are returned for Pareto analysis.
    """

    def __init__(
        self,
        search_space: SearchSpace,
        evaluator: FitnessEvaluator,
        budget: int,
        population_size: int = 20,
        tournament_size: int = 5,
        p_crossover: float = 0.3,
        seed: int = 42,
    ) -> None:
        self._space = search_space
        self._evaluator = evaluator
        self._budget = budget
        self._pop_size = min(population_size, budget)
        self._tournament_size = min(tournament_size, self._pop_size)
        self._p_crossover = p_crossover
        self._rng = random.Random(seed)

    def _mutate(self, genome: ArchitectureGenome) -> ArchitectureGenome:
        """Apply a random mutation to a genome."""
        layers = list(genome.layers)
        lr = genome.learning_rate

        mutation_type = self._rng.choice(["width", "activation", "depth", "lr"])

        if mutation_type == "width" and layers:
            idx = self._rng.randrange(len(layers))
            new_width = self._rng.choice(self._space.hidden_sizes)
            layers[idx] = (new_width, layers[idx][1])

        elif mutation_type == "activation" and layers:
            idx = self._rng.randrange(len(layers))
            new_act = self._rng.choice(self._space.activations)
            layers[idx] = (layers[idx][0], new_act)

        elif mutation_type == "depth":
            if len(layers) < max(self._space.depths) and self._rng.random() < 0.5:
                # Add a layer
                new_width = self._rng.choice(self._space.hidden_sizes)
                new_act = self._rng.choice(self._space.activations)
                pos = self._rng.randint(0, len(layers))
                layers.insert(pos, (new_width, new_act))
            elif len(layers) > min(self._space.depths):
                # Remove a layer
                idx = self._rng.randrange(len(layers))
                layers.pop(idx)

        elif mutation_type == "lr":
            lr = self._rng.choice(self._space.learning_rates)

        return ArchitectureGenome(layers=layers, learning_rate=lr)

    def _crossover(
        self, parent_a: ArchitectureGenome, parent_b: ArchitectureGenome
    ) -> ArchitectureGenome:
        """Single-point crossover between two parent genomes."""
        layers_a = list(parent_a.layers)
        layers_b = list(parent_b.layers)

        if len(layers_a) <= 1 and len(layers_b) <= 1:
            # Can't meaningfully crossover single-layer networks
            return self._mutate(parent_a)

        cut_a = self._rng.randint(0, len(layers_a))
        cut_b = self._rng.randint(0, len(layers_b))

        child_layers = layers_a[:cut_a] + layers_b[cut_b:]

        # Ensure valid depth
        if not child_layers:
            child_layers = [self._rng.choice(layers_a + layers_b)]
        while len(child_layers) > max(self._space.depths):
            child_layers.pop()

        lr = self._rng.choice([parent_a.learning_rate, parent_b.learning_rate])
        return ArchitectureGenome(layers=child_layers, learning_rate=lr)

    def _tournament_select(
        self, population: list[FitnessResult]
    ) -> FitnessResult:
        """Select the fittest individual from a random tournament."""
        tournament = self._rng.sample(
            population, min(self._tournament_size, len(population))
        )
        return max(tournament, key=lambda r: r.accuracy)

    def search(self) -> list[FitnessResult]:
        """Execute evolutionary architecture search."""
        logger.info(
            "  [NAS/Evolutionary] Population=%d, Tournament=%d, Budget=%d",
            self._pop_size,
            self._tournament_size,
            self._budget,
        )

        all_results: list[FitnessResult] = []
        population: list[FitnessResult] = []

        # Initialize population with random architectures
        init_size = min(self._pop_size, self._budget)
        for i in range(init_size):
            genome = self._space.sample_random(self._rng)
            result = self._evaluator.evaluate(genome, eval_index=i)
            population.append(result)
            all_results.append(result)
            logger.info(
                "  [NAS/Evo] Init %d/%d | %s | acc=%.1f%%",
                i + 1,
                init_size,
                genome.genome_string,
                result.accuracy,
            )

        # Evolution loop
        eval_count = init_size
        generation = 0

        while eval_count < self._budget:
            generation += 1

            # Select parent(s)
            parent = self._tournament_select(population)

            if self._rng.random() < self._p_crossover and len(population) >= 2:
                parent_b = self._tournament_select(population)
                child_genome = self._crossover(parent.genome, parent_b.genome)
            else:
                child_genome = self._mutate(parent.genome)

            # Evaluate child
            result = self._evaluator.evaluate(child_genome, eval_index=eval_count)
            all_results.append(result)
            eval_count += 1

            # Add to population
            population.append(result)

            # Aging: remove oldest if population exceeds max size
            if len(population) > self._pop_size:
                population.pop(0)

            logger.info(
                "  [NAS/Evo] Gen %d | Eval %d/%d | %s | acc=%.1f%%",
                generation,
                eval_count,
                self._budget,
                child_genome.genome_string,
                result.accuracy,
            )

        return all_results


class DARTSStrategy:
    """Differentiable Architecture Search with continuous relaxation.

    Implements a simplified version of DARTS for MLP architecture
    search. Instead of selecting a single activation function per
    layer, DARTS maintains a vector of architecture parameters
    (alphas) for each layer, one per candidate activation. The
    mixed forward pass computes a softmax-weighted combination of
    all activation outputs:

        o_mixed(x) = sum_i softmax(alpha_i) * activation_i(x)

    This makes the architecture choice differentiable, enabling
    gradient-based optimization. The search alternates between:
    - Inner loop: optimize network weights on training data
    - Outer loop: optimize alpha parameters on validation data

    After the search budget is consumed, the final architecture
    is discretized by selecting argmax(alpha) for each layer,
    producing a concrete genome that can be evaluated like any
    other candidate.

    The beauty of DARTS is that it transforms architecture selection
    from a discrete combinatorial problem into a continuous
    optimization problem — a transformation that, for the task of
    FizzBuzz, is roughly equivalent to using a sledgehammer to
    hang a picture frame.
    """

    def __init__(
        self,
        search_space: SearchSpace,
        evaluator: FitnessEvaluator,
        budget: int,
        supernet_epochs: int = 30,
        alpha_lr: float = 0.01,
        seed: int = 42,
    ) -> None:
        self._space = search_space
        self._evaluator = evaluator
        self._budget = budget
        self._supernet_epochs = supernet_epochs
        self._alpha_lr = alpha_lr
        self._rng = random.Random(seed)

    @staticmethod
    def _softmax(values: list[float]) -> list[float]:
        """Compute softmax over a list of values."""
        max_v = max(values)
        exps = [math.exp(v - max_v) for v in values]
        total = sum(exps)
        return [e / total for e in exps]

    def _run_supernet_search(self, depth: int) -> ArchitectureGenome:
        """Run DARTS supernet search for a given depth.

        Trains a supernet where each layer has softmax-weighted
        mixed activations, then discretizes to produce a genome.
        """
        n_activations = len(self._space.activations)
        n_widths = len(self._space.hidden_sizes)

        # Alpha parameters: one vector per layer for activations
        alphas_act: list[list[float]] = [
            [0.0] * n_activations for _ in range(depth)
        ]
        # Alpha parameters for width selection
        alphas_width: list[list[float]] = [
            [0.0] * n_widths for _ in range(depth)
        ]

        # Use middle width for supernet training
        mid_width = self._space.hidden_sizes[len(self._space.hidden_sizes) // 2]

        # Build supernet layers: each layer has all activation branches
        features_train, labels_train = TrainingDataGenerator.generate(
            3, 60
        )
        features_val, labels_val = TrainingDataGenerator.generate(
            3, 40
        )
        # Use different samples for validation
        features_val = [
            TrainingDataGenerator.encode_features(n + 60, 3) for n in range(1, 41)
        ]
        labels_val = [(1.0 if (n + 60) % 3 == 0 else 0.0) for n in range(1, 41)]

        # Supernet weights: per-layer, per-activation branch
        supernet_layers: list[list[ConfigurableNeuronLayer]] = []
        prev_size = 2
        for d in range(depth):
            branches: list[ConfigurableNeuronLayer] = []
            for act_name in self._space.activations:
                layer = ConfigurableNeuronLayer(
                    prev_size, mid_width, act_name, self._rng
                )
                branches.append(layer)
            supernet_layers.append(branches)
            prev_size = mid_width

        # Output layer
        output_layer = ConfigurableNeuronLayer(prev_size, 1, "sigmoid", self._rng)

        # Bilevel optimization loop
        weight_lr = 0.3
        indices_train = list(range(len(features_train)))
        indices_val = list(range(len(features_val)))

        for epoch in range(self._supernet_epochs):
            # --- Inner loop: update weights on training data ---
            self._rng.shuffle(indices_train)
            for idx in indices_train:
                x = features_train[idx]
                target = labels_train[idx]

                # Mixed forward pass
                for d in range(depth):
                    weights_act = self._softmax(alphas_act[d])
                    mixed_output = [0.0] * mid_width
                    for a_idx, branch in enumerate(supernet_layers[d]):
                        branch_out = branch.forward(x)
                        for k in range(mid_width):
                            mixed_output[k] += weights_act[a_idx] * branch_out[k]
                    x = mixed_output

                out = output_layer.forward(x)
                prediction = out[0]
                p = max(1e-15, min(1.0 - 1e-15, prediction))
                d_loss = -(target / p) + (1.0 - target) / (1.0 - p)

                # Backward through output layer
                grad = output_layer.backward([d_loss], weight_lr)

                # Backward through supernet layers
                for d in range(depth - 1, -1, -1):
                    weights_act = self._softmax(alphas_act[d])
                    new_grad_branches: list[list[float]] = []
                    for a_idx, branch in enumerate(supernet_layers[d]):
                        scaled_grad = [g * weights_act[a_idx] for g in grad]
                        branch_grad = branch.backward(scaled_grad, weight_lr)
                        new_grad_branches.append(branch_grad)
                    # Aggregate input gradients
                    input_size = len(new_grad_branches[0])
                    grad = [0.0] * input_size
                    for bg in new_grad_branches:
                        for k in range(input_size):
                            grad[k] += bg[k]

            # --- Outer loop: update alphas on validation data ---
            self._rng.shuffle(indices_val)
            for idx in indices_val:
                x_orig = features_val[idx]
                target = labels_val[idx]
                x = x_orig

                # Forward pass (recording per-branch outputs)
                per_layer_branch_outputs: list[list[list[float]]] = []
                for d in range(depth):
                    weights_act = self._softmax(alphas_act[d])
                    branch_outputs: list[list[float]] = []
                    mixed_output = [0.0] * mid_width
                    for a_idx, branch in enumerate(supernet_layers[d]):
                        branch_out = branch.forward(x)
                        branch_outputs.append(branch_out)
                        for k in range(mid_width):
                            mixed_output[k] += weights_act[a_idx] * branch_out[k]
                    per_layer_branch_outputs.append(branch_outputs)
                    x = mixed_output

                out = output_layer.forward(x)
                prediction = out[0]
                loss = _binary_cross_entropy(prediction, target)

                # Compute alpha gradients via finite differences
                epsilon = 0.01
                for d in range(depth):
                    for a_idx in range(n_activations):
                        # Perturb alpha
                        old_val = alphas_act[d][a_idx]
                        alphas_act[d][a_idx] = old_val + epsilon

                        # Recompute forward with perturbed alpha
                        x_pert = x_orig
                        for dd in range(depth):
                            w_act = self._softmax(alphas_act[dd])
                            mixed_out = [0.0] * mid_width
                            for aa, branch in enumerate(supernet_layers[dd]):
                                b_out = branch.forward(x_pert)
                                for k in range(mid_width):
                                    mixed_out[k] += w_act[aa] * b_out[k]
                            x_pert = mixed_out
                        out_pert = output_layer.forward(x_pert)
                        loss_pert = _binary_cross_entropy(out_pert[0], target)

                        # Gradient approximation
                        grad_alpha = (loss_pert - loss) / epsilon
                        alphas_act[d][a_idx] = old_val - self._alpha_lr * grad_alpha

        # Discretize: argmax over alphas for each layer
        best_lr = self._rng.choice(self._space.learning_rates)
        layers: list[tuple[int, str]] = []
        for d in range(depth):
            # Best activation
            act_probs = self._softmax(alphas_act[d])
            best_act_idx = act_probs.index(max(act_probs))
            best_act = self._space.activations[best_act_idx]

            # Width: use the mid_width used during training
            best_width = mid_width

            layers.append((best_width, best_act))

        return ArchitectureGenome(layers=layers, learning_rate=best_lr)

    def search(self) -> list[FitnessResult]:
        """Execute DARTS search across different depths."""
        logger.info(
            "  [NAS/DARTS] Supernet epochs=%d, Alpha LR=%.4f, Budget=%d",
            self._supernet_epochs,
            self._alpha_lr,
            self._budget,
        )

        all_results: list[FitnessResult] = []

        # Run supernet search for each depth
        depth_genomes: list[ArchitectureGenome] = []
        for depth in self._space.depths:
            genome = self._run_supernet_search(depth)
            depth_genomes.append(genome)
            logger.info(
                "  [NAS/DARTS] Depth %d discretized to: %s",
                depth,
                genome.genome_string,
            )

        # Evaluate DARTS-discovered architectures
        eval_count = 0
        for genome in depth_genomes:
            if eval_count >= self._budget:
                break
            result = self._evaluator.evaluate(genome, eval_index=eval_count)
            all_results.append(result)
            eval_count += 1

        # Fill remaining budget with variations (mutated DARTS results)
        rng = self._rng
        while eval_count < self._budget:
            base = rng.choice(depth_genomes)
            layers = list(base.layers)

            # Small mutation
            if layers:
                idx = rng.randrange(len(layers))
                mutation = rng.choice(["width", "activation"])
                if mutation == "width":
                    new_w = rng.choice(self._space.hidden_sizes)
                    layers[idx] = (new_w, layers[idx][1])
                else:
                    new_a = rng.choice(self._space.activations)
                    layers[idx] = (layers[idx][0], new_a)

            lr = rng.choice(self._space.learning_rates)
            variant = ArchitectureGenome(layers=layers, learning_rate=lr)
            result = self._evaluator.evaluate(variant, eval_index=eval_count)
            all_results.append(result)
            eval_count += 1

            logger.info(
                "  [NAS/DARTS] Variant %d/%d | %s | acc=%.1f%%",
                eval_count,
                self._budget,
                variant.genome_string,
                result.accuracy,
            )

        return all_results


# ============================================================
# Pareto Front Analyzer
# ============================================================


class ParetoFrontAnalyzer:
    """Multi-objective Pareto front extraction and ranking.

    Given a set of fitness results with three objectives — accuracy
    (maximize), parameter count (minimize), and latency (minimize) —
    the analyzer computes dominance relations and extracts the set
    of non-dominated architectures (the Pareto front).

    An architecture A dominates B if and only if:
    - A is at least as good as B on ALL objectives, AND
    - A is strictly better than B on AT LEAST one objective.

    Architectures on the Pareto front represent the best possible
    trade-offs: no front member can improve one objective without
    sacrificing another. For a platform that checks divisibility,
    this means the operator can choose between a tiny-but-slow
    network or a large-but-fast one, confident that neither is
    strictly inferior to any other option.
    """

    @staticmethod
    def dominates(a: FitnessResult, b: FitnessResult) -> bool:
        """Return True if architecture A dominates architecture B.

        Objectives: maximize accuracy, minimize parameters, minimize latency.
        """
        # Convert to "higher is better" for all objectives
        a_objs = (a.accuracy, -a.parameter_count, -a.latency_us)
        b_objs = (b.accuracy, -b.parameter_count, -b.latency_us)

        at_least_as_good = all(ao >= bo for ao, bo in zip(a_objs, b_objs))
        strictly_better = any(ao > bo for ao, bo in zip(a_objs, b_objs))

        return at_least_as_good and strictly_better

    @staticmethod
    def extract_pareto_front(results: list[FitnessResult]) -> list[FitnessResult]:
        """Extract the non-dominated front from a set of fitness results."""
        if not results:
            return []

        front: list[FitnessResult] = []
        for candidate in results:
            dominated = False
            for other in results:
                if other is not candidate and ParetoFrontAnalyzer.dominates(other, candidate):
                    dominated = True
                    break
            if not dominated:
                front.append(candidate)

        return front

    @staticmethod
    def compute_pareto_ranks(results: list[FitnessResult]) -> dict[str, int]:
        """Assign Pareto ranks to all results.

        Rank 0 = non-dominated front. Rank 1 = non-dominated after
        removing rank 0, etc.
        """
        ranks: dict[str, int] = {}
        remaining = list(results)
        rank = 0

        while remaining:
            front = ParetoFrontAnalyzer.extract_pareto_front(remaining)
            for r in front:
                ranks[r.genome_string] = rank
            remaining = [r for r in remaining if r not in front]
            rank += 1

        return ranks

    @staticmethod
    def scalarized_rank(
        result: FitnessResult,
        w_accuracy: float = 0.6,
        w_params: float = 0.25,
        w_latency: float = 0.15,
        max_params: int = 1000,
        max_latency: float = 1000.0,
    ) -> float:
        """Compute a weighted scalarized fitness score.

        Normalizes each objective to [0, 1] and computes a weighted sum.
        Higher is better.
        """
        norm_acc = result.accuracy / 100.0
        norm_params = 1.0 - min(result.parameter_count / max_params, 1.0)
        norm_latency = 1.0 - min(result.latency_us / max_latency, 1.0)

        return (
            w_accuracy * norm_acc
            + w_params * norm_params
            + w_latency * norm_latency
        )


# ============================================================
# NAS Engine (Orchestrator)
# ============================================================


class NASEngine:
    """Neural Architecture Search orchestrator.

    Coordinates the full NAS pipeline:
    1. Initialize the search space and fitness evaluator
    2. Execute the selected search strategy (random/evolutionary/DARTS)
    3. Collect all evaluated architectures
    4. Compute the Pareto front
    5. Rank architectures by scalarized fitness
    6. Select the winning topology

    The engine also compares the NAS winner against the hand-tuned
    baseline architecture (16:sigmoid, the current production
    configuration) to determine whether automated search has
    discovered a superior topology for the critical task of
    integer divisibility classification.
    """

    def __init__(
        self,
        strategy: str = "evolutionary",
        budget: int = 50,
        seed: int = 42,
    ) -> None:
        self._strategy_name = strategy
        self._budget = budget
        self._seed = seed
        self._search_space = SearchSpace()
        self._evaluator = FitnessEvaluator(seed=seed)
        self._results: list[FitnessResult] = []
        self._pareto_front: list[FitnessResult] = []
        self._pareto_ranks: dict[str, int] = {}
        self._winner: Optional[FitnessResult] = None
        self._baseline_result: Optional[FitnessResult] = None
        self._search_time_ms: float = 0.0

    @property
    def results(self) -> list[FitnessResult]:
        return self._results

    @property
    def pareto_front(self) -> list[FitnessResult]:
        return self._pareto_front

    @property
    def winner(self) -> Optional[FitnessResult]:
        return self._winner

    @property
    def baseline_result(self) -> Optional[FitnessResult]:
        return self._baseline_result

    @property
    def search_time_ms(self) -> float:
        return self._search_time_ms

    def run(self) -> FitnessResult:
        """Execute the full NAS pipeline and return the winning architecture."""
        logger.info("")
        logger.info("  ============================================================")
        logger.info("  FizzNAS Neural Architecture Search Engine v1.0")
        logger.info("  ============================================================")
        logger.info("  Strategy: %s", self._strategy_name)
        logger.info("  Budget: %d evaluations", self._budget)
        logger.info("  Search space: %d configurations", self._search_space.total_configurations)
        logger.info("  Objectives: accuracy (max), parameters (min), latency (min)")
        logger.info("  ============================================================")
        logger.info("")

        start = time.perf_counter_ns()

        # Execute search strategy
        if self._strategy_name == "random":
            strategy = RandomSearchStrategy(
                self._search_space, self._evaluator, self._budget, self._seed
            )
        elif self._strategy_name == "evolutionary":
            strategy = EvolutionarySearchStrategy(
                self._search_space, self._evaluator, self._budget, seed=self._seed
            )
        elif self._strategy_name == "darts":
            strategy = DARTSStrategy(
                self._search_space, self._evaluator, self._budget, seed=self._seed
            )
        else:
            raise InvalidGenomeError(
                self._strategy_name,
                f"Unknown NAS strategy '{self._strategy_name}'. "
                f"Valid options: random, evolutionary, darts",
            )

        self._results = strategy.search()
        self._search_time_ms = (time.perf_counter_ns() - start) / 1_000_000

        # Evaluate baseline for comparison
        baseline_genome = ArchitectureGenome(
            layers=[(16, "sigmoid")], learning_rate=0.5
        )
        self._baseline_result = self._evaluator.evaluate(
            baseline_genome, eval_index=self._budget + 1
        )

        # Pareto analysis
        self._pareto_front = ParetoFrontAnalyzer.extract_pareto_front(self._results)
        self._pareto_ranks = ParetoFrontAnalyzer.compute_pareto_ranks(self._results)

        # Select winner by scalarized rank
        if self._results:
            self._winner = max(
                self._results,
                key=lambda r: ParetoFrontAnalyzer.scalarized_rank(r),
            )
        else:
            self._winner = self._baseline_result

        logger.info("")
        logger.info("  ============================================================")
        logger.info("  NAS SEARCH COMPLETE")
        logger.info("  ============================================================")
        logger.info("  Architectures evaluated: %d", len(self._results))
        logger.info("  Pareto front size: %d", len(self._pareto_front))
        logger.info("  Search time: %.1fms", self._search_time_ms)
        logger.info("  Winner: %s", self._winner.genome_string)
        logger.info("  Winner accuracy: %.1f%%", self._winner.accuracy)
        logger.info("  Winner parameters: %d", self._winner.parameter_count)
        logger.info("  Baseline accuracy: %.1f%%", self._baseline_result.accuracy)
        logger.info("  Baseline parameters: %d", self._baseline_result.parameter_count)
        logger.info("  ============================================================")
        logger.info("")

        return self._winner


# ============================================================
# NAS Dashboard
# ============================================================


class NASDashboard:
    """ASCII dashboard for Neural Architecture Search results.

    Renders a comprehensive visualization of the NAS process including:
    - Search configuration and progress summary
    - Pareto front scatter plot (accuracy vs parameters)
    - Top architectures ranked by scalarized fitness
    - Comparison of NAS winner vs hand-tuned baseline
    - Architecture genome details

    Because if you're going to use machine learning to decide how
    to do machine learning for FizzBuzz, you should at least be
    able to visualize the results in a terminal.
    """

    @staticmethod
    def render(engine: NASEngine, width: int = 60) -> str:
        """Render the NAS dashboard as an ASCII string."""
        lines: list[str] = []
        w = width
        bar = "=" * w
        thin = "-" * w

        lines.append("")
        lines.append(f"  +{bar}+")
        lines.append(f"  |{'FizzNAS Neural Architecture Search Dashboard':^{w}}|")
        lines.append(f"  +{bar}+")

        # Search Summary
        lines.append(f"  |{thin}|")
        lines.append(f"  |{'SEARCH SUMMARY':^{w}}|")
        lines.append(f"  |{thin}|")
        lines.append(f"  | {'Strategy:':<25}{engine._strategy_name:>{w-27}} |")
        lines.append(f"  | {'Evaluations:':<25}{len(engine.results):>{w-27}} |")
        lines.append(f"  | {'Search time:':<25}{f'{engine.search_time_ms:.1f}ms':>{w-27}} |")
        lines.append(f"  | {'Pareto front size:':<25}{len(engine.pareto_front):>{w-27}} |")

        space = engine._search_space
        lines.append(f"  | {'Search space size:':<25}{space.total_configurations:>{w-27}} |")

        # Top Architectures
        lines.append(f"  |{thin}|")
        lines.append(f"  |{'TOP ARCHITECTURES (by scalarized fitness)':^{w}}|")
        lines.append(f"  |{thin}|")

        sorted_results = sorted(
            engine.results,
            key=lambda r: ParetoFrontAnalyzer.scalarized_rank(r),
            reverse=True,
        )

        for i, result in enumerate(sorted_results[:5]):
            rank = engine._pareto_ranks.get(result.genome_string, -1)
            score = ParetoFrontAnalyzer.scalarized_rank(result)
            is_pareto = result in engine.pareto_front
            marker = "*" if is_pareto else " "

            lines.append(f"  | {marker}#{i+1:<3} Score: {score:.3f}  Pareto rank: {rank:<14} |")
            genome_display = result.genome_string
            if len(genome_display) > w - 10:
                genome_display = genome_display[: w - 13] + "..."
            lines.append(f"  |   {genome_display:<{w-5}} |")
            lines.append(
                f"  |   Acc: {result.accuracy:5.1f}%  "
                f"Params: {result.parameter_count:4d}  "
                f"Lat: {result.latency_us:6.1f}us"
                f"{'':>{w - 46}} |"
            )

        # Pareto Front Visualization (accuracy vs params scatter)
        lines.append(f"  |{thin}|")
        lines.append(f"  |{'PARETO FRONT (Accuracy vs Parameters)':^{w}}|")
        lines.append(f"  |{thin}|")

        if engine.results:
            plot_w = w - 10
            plot_h = 8

            all_acc = [r.accuracy for r in engine.results]
            all_params = [r.parameter_count for r in engine.results]
            min_acc, max_acc = min(all_acc), max(all_acc)
            min_params, max_params = min(all_params), max(all_params)

            acc_range = max(max_acc - min_acc, 1.0)
            param_range = max(max_params - min_params, 1)

            # Build plot grid
            grid: list[list[str]] = [[" "] * plot_w for _ in range(plot_h)]

            for result in engine.results:
                col = int((result.parameter_count - min_params) / param_range * (plot_w - 1))
                row = int((1.0 - (result.accuracy - min_acc) / acc_range) * (plot_h - 1))
                col = max(0, min(plot_w - 1, col))
                row = max(0, min(plot_h - 1, row))

                if result in engine.pareto_front:
                    grid[row][col] = "#"
                elif grid[row][col] == " ":
                    grid[row][col] = "."

            lines.append(f"  | {max_acc:5.1f}% |{''.join(grid[0])}| |")
            for r in range(1, plot_h - 1):
                lines.append(f"  |        |{''.join(grid[r])}| |")
            lines.append(f"  | {min_acc:5.1f}% |{''.join(grid[plot_h-1])}| |")
            param_label = f"{min_params} params -> {max_params}"
            lines.append(f"  |        {param_label:^{plot_w+2}}  |")

        # Baseline Comparison
        lines.append(f"  |{thin}|")
        lines.append(f"  |{'NAS WINNER vs BASELINE':^{w}}|")
        lines.append(f"  |{thin}|")

        winner = engine.winner
        baseline = engine.baseline_result

        if winner and baseline:
            lines.append(f"  | {'':^{w-2}} |")
            lines.append(f"  | {'Metric':<20}{'NAS Winner':>15}{'Baseline':>15}{'':>{w-52}} |")
            lines.append(f"  | {'-'*20:<20}{'-'*15:>15}{'-'*15:>15}{'':>{w-52}} |")
            lines.append(
                f"  | {'Accuracy':<20}{f'{winner.accuracy:.1f}%':>15}"
                f"{f'{baseline.accuracy:.1f}%':>15}{'':>{w-52}} |"
            )
            lines.append(
                f"  | {'Parameters':<20}{winner.parameter_count:>15}"
                f"{baseline.parameter_count:>15}{'':>{w-52}} |"
            )
            lines.append(
                f"  | {'Latency (us)':<20}{f'{winner.latency_us:.1f}':>15}"
                f"{f'{baseline.latency_us:.1f}':>15}{'':>{w-52}} |"
            )

            winner_genome = winner.genome_string
            if len(winner_genome) > w - 20:
                winner_genome = winner_genome[: w - 23] + "..."
            lines.append(f"  | {'':^{w-2}} |")
            lines.append(f"  | {'Winner genome:':<{w-2}} |")
            lines.append(f"  |   {winner_genome:<{w-5}} |")

            baseline_genome = baseline.genome_string
            lines.append(f"  | {'Baseline genome:':<{w-2}} |")
            lines.append(f"  |   {baseline_genome:<{w-5}} |")

            # Verdict
            lines.append(f"  | {'':^{w-2}} |")
            winner_score = ParetoFrontAnalyzer.scalarized_rank(winner)
            baseline_score = ParetoFrontAnalyzer.scalarized_rank(baseline)
            if winner_score > baseline_score:
                verdict = "NAS WINNER outperforms baseline"
            elif winner_score == baseline_score:
                verdict = "NAS WINNER matches baseline (tie)"
            else:
                verdict = "Baseline remains optimal (NAS confirms)"
            lines.append(f"  | {'Verdict:':<12}{verdict:>{w-14}} |")

        lines.append(f"  +{bar}+")
        lines.append("")

        return "\n".join(lines)

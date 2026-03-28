"""
Enterprise FizzBuzz Platform - FizzReservoir: Reservoir Computing Engine

Implements echo state networks (ESNs) for time-series classification of
FizzBuzz sequences. The reservoir is a sparsely connected recurrent neural
network with fixed random weights. Only the output (readout) layer is
trained, using ridge regression on collected reservoir states.

The key insight of reservoir computing is that a sufficiently large, randomly
connected dynamical system — when driven by input signals — creates a rich,
high-dimensional representation of the input history. By training only a
linear readout, the computational cost of learning is reduced from O(N^3)
(full RNN training) to O(N * K^2) where N is the number of time steps and
K is the reservoir dimension.

The echo state property requires that the spectral radius (largest absolute
eigenvalue) of the reservoir weight matrix be strictly less than 1.0. This
ensures that the reservoir state is a contracting map — past inputs are
gradually forgotten, giving the network a finite memory horizon.

For the FizzBuzz classification task, the ESN processes a sequence of integers
and produces a 4-class prediction at each time step: {Plain, Fizz, Buzz,
FizzBuzz}. The periodic structure of FizzBuzz modular arithmetic creates
characteristic patterns in the reservoir state space that the readout layer
exploits for classification.
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

DEFAULT_RESERVOIR_SIZE = 100
DEFAULT_INPUT_DIM = 8
DEFAULT_OUTPUT_DIM = 4  # {Plain, Fizz, Buzz, FizzBuzz}
DEFAULT_SPECTRAL_RADIUS = 0.9
DEFAULT_SPARSITY = 0.1  # 10% connectivity
DEFAULT_INPUT_SCALING = 0.5
DEFAULT_LEAK_RATE = 0.3  # Leaky integration constant
DEFAULT_RIDGE_ALPHA = 1e-6  # Ridge regression regularization
DEFAULT_WASHOUT = 10  # Initial steps discarded before collecting states

CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]


# ---------------------------------------------------------------------------
# Linear algebra helpers
# ---------------------------------------------------------------------------

def _mat_vec_mul(matrix: List[List[float]], vector: List[float]) -> List[float]:
    """Multiply a matrix by a vector."""
    result = []
    for row in matrix:
        val = sum(row[j] * vector[j] for j in range(len(vector)))
        result.append(val)
    return result


def _vec_add(a: List[float], b: List[float]) -> List[float]:
    return [a[i] + b[i] for i in range(len(a))]


def _vec_scale(v: List[float], s: float) -> List[float]:
    return [x * s for x in v]


def _tanh_vec(v: List[float]) -> List[float]:
    return [math.tanh(x) for x in v]


def _dot(a: List[float], b: List[float]) -> float:
    return sum(a[i] * b[i] for i in range(len(a)))


def _mat_transpose(m: List[List[float]]) -> List[List[float]]:
    if not m:
        return []
    rows, cols = len(m), len(m[0])
    return [[m[r][c] for r in range(rows)] for c in range(cols)]


def _mat_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    """Multiply two matrices."""
    rows_a, cols_a = len(a), len(a[0])
    cols_b = len(b[0])
    result = [[0.0] * cols_b for _ in range(rows_a)]
    for i in range(rows_a):
        for j in range(cols_b):
            for k in range(cols_a):
                result[i][j] += a[i][k] * b[k][j]
    return result


def _identity(n: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _mat_add(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def _mat_scale(m: List[List[float]], s: float) -> List[List[float]]:
    return [[m[i][j] * s for j in range(len(m[0]))] for i in range(len(m))]


def _spectral_radius_estimate(matrix: List[List[float]], iterations: int = 50) -> float:
    """Estimate the spectral radius using power iteration."""
    n = len(matrix)
    if n == 0:
        return 0.0

    # Start with random vector
    v = [random.gauss(0, 1) for _ in range(n)]
    norm = math.sqrt(sum(x * x for x in v))
    v = [x / max(norm, 1e-12) for x in v]

    eigenvalue = 0.0
    for _ in range(iterations):
        w = _mat_vec_mul(matrix, v)
        eigenvalue = math.sqrt(sum(x * x for x in w))
        if eigenvalue < 1e-12:
            return 0.0
        v = [x / eigenvalue for x in w]

    return eigenvalue


# ---------------------------------------------------------------------------
# Reservoir
# ---------------------------------------------------------------------------

@dataclass
class Reservoir:
    """A random recurrent neural network serving as the dynamical reservoir.

    The weight matrix W is sparse and scaled to have the desired spectral
    radius. The input weight matrix W_in maps input features to reservoir
    neurons. The state is updated via leaky integration:

        x(t) = (1 - alpha) * x(t-1) + alpha * tanh(W_in * u(t) + W * x(t-1))

    where alpha is the leak rate.
    """

    size: int = DEFAULT_RESERVOIR_SIZE
    input_dim: int = DEFAULT_INPUT_DIM
    spectral_radius: float = DEFAULT_SPECTRAL_RADIUS
    sparsity: float = DEFAULT_SPARSITY
    input_scaling: float = DEFAULT_INPUT_SCALING
    leak_rate: float = DEFAULT_LEAK_RATE
    W: List[List[float]] = field(default_factory=list)
    W_in: List[List[float]] = field(default_factory=list)
    state: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzreservoir import (
            ReservoirDimensionError,
            SpectralRadiusError,
        )

        if self.size <= 0:
            raise ReservoirDimensionError(self.size, "Reservoir size must be positive")
        if self.input_dim <= 0:
            raise ReservoirDimensionError(self.input_dim, "Input dimension must be positive")

        if not self.W:
            self._initialize_weights()
        if not self.W_in:
            self._initialize_input_weights()
        if not self.state:
            self.state = [0.0] * self.size

    def _initialize_weights(self) -> None:
        """Generate sparse random reservoir weight matrix and scale spectral radius."""
        self.W = [[0.0] * self.size for _ in range(self.size)]
        for i in range(self.size):
            for j in range(self.size):
                if random.random() < self.sparsity:
                    self.W[i][j] = random.uniform(-1.0, 1.0)

        # Scale to desired spectral radius
        sr = _spectral_radius_estimate(self.W)
        if sr > 1e-10:
            scale = self.spectral_radius / sr
            for i in range(self.size):
                for j in range(self.size):
                    self.W[i][j] *= scale

    def _initialize_input_weights(self) -> None:
        """Generate random input weight matrix."""
        self.W_in = []
        for i in range(self.size):
            row = []
            for j in range(self.input_dim):
                row.append(random.uniform(-self.input_scaling, self.input_scaling))
            self.W_in.append(row)

    def update(self, input_vec: List[float]) -> List[float]:
        """Drive the reservoir with an input vector and return the new state.

        Uses leaky-integrator ESN dynamics.
        """
        # W_in * u
        input_contribution = _mat_vec_mul(self.W_in, input_vec)
        # W * x
        recurrent_contribution = _mat_vec_mul(self.W, self.state)
        # Pre-activation
        pre_activation = _vec_add(input_contribution, recurrent_contribution)
        # tanh nonlinearity
        activated = _tanh_vec(pre_activation)
        # Leaky integration
        new_state = []
        for i in range(self.size):
            new_state.append(
                (1.0 - self.leak_rate) * self.state[i]
                + self.leak_rate * activated[i]
            )
        self.state = new_state
        return list(self.state)

    def reset(self) -> None:
        """Reset the reservoir state to zero."""
        self.state = [0.0] * self.size

    def get_spectral_radius(self) -> float:
        """Estimate the current spectral radius of the weight matrix."""
        return _spectral_radius_estimate(self.W)


# ---------------------------------------------------------------------------
# Readout layer
# ---------------------------------------------------------------------------

@dataclass
class ReadoutLayer:
    """Linear readout layer trained with ridge regression.

    Maps reservoir state vectors to output class predictions.
    """

    reservoir_size: int = DEFAULT_RESERVOIR_SIZE
    output_dim: int = DEFAULT_OUTPUT_DIM
    ridge_alpha: float = DEFAULT_RIDGE_ALPHA
    weights: List[List[float]] = field(default_factory=list)
    _trained: bool = False

    def train(self, states: List[List[float]], targets: List[List[float]]) -> None:
        """Train the readout using ridge regression.

        Computes W_out = Y * X^T * (X * X^T + alpha * I)^(-1)
        using the normal equations.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzreservoir import ReadoutTrainingError

        n_samples = len(states)
        if n_samples == 0:
            raise ReadoutTrainingError(0.0, "No training samples provided")

        n_features = len(states[0])

        # Compute X^T * X + alpha * I
        XtX = [[0.0] * n_features for _ in range(n_features)]
        for s in states:
            for i in range(n_features):
                for j in range(n_features):
                    XtX[i][j] += s[i] * s[j]

        for i in range(n_features):
            XtX[i][i] += self.ridge_alpha

        # Compute X^T * Y
        XtY = [[0.0] * self.output_dim for _ in range(n_features)]
        for k in range(n_samples):
            for i in range(n_features):
                for j in range(self.output_dim):
                    XtY[i][j] += states[k][i] * targets[k][j]

        # Solve using simple Gaussian elimination for small systems
        self.weights = self._solve_linear(XtX, XtY)
        self._trained = True

        logger.info("Readout layer trained on %d samples", n_samples)

    def _solve_linear(
        self, A: List[List[float]], B: List[List[float]]
    ) -> List[List[float]]:
        """Solve AX = B using Gaussian elimination with partial pivoting."""
        n = len(A)
        m = len(B[0]) if B else 0

        # Augmented matrix [A | B]
        aug = [A[i][:] + B[i][:] for i in range(n)]

        # Forward elimination
        for col in range(n):
            # Partial pivoting
            max_row = col
            for row in range(col + 1, n):
                if abs(aug[row][col]) > abs(aug[max_row][col]):
                    max_row = row
            aug[col], aug[max_row] = aug[max_row], aug[col]

            pivot = aug[col][col]
            if abs(pivot) < 1e-12:
                continue

            for row in range(col + 1, n):
                factor = aug[row][col] / pivot
                for j in range(col, n + m):
                    aug[row][j] -= factor * aug[col][j]

        # Back substitution
        X = [[0.0] * m for _ in range(n)]
        for col in range(n - 1, -1, -1):
            pivot = aug[col][col]
            if abs(pivot) < 1e-12:
                continue
            for j in range(m):
                val = aug[col][n + j]
                for k in range(col + 1, n):
                    val -= aug[col][k] * X[k][j]
                X[col][j] = val / pivot

        return X

    def predict(self, state: List[float]) -> Tuple[str, List[float]]:
        """Predict the FizzBuzz class from a reservoir state vector."""
        if not self._trained or not self.weights:
            return "Plain", [0.0] * self.output_dim

        # Linear output: y = W^T * x
        outputs = []
        for j in range(self.output_dim):
            val = sum(self.weights[i][j] * state[i]
                      for i in range(min(len(state), len(self.weights))))
            outputs.append(val)

        # Softmax-like normalization
        max_val = max(outputs)
        exp_vals = [math.exp(min(v - max_val, 50)) for v in outputs]
        total = sum(exp_vals)
        probs = [e / max(total, 1e-12) for e in exp_vals]

        best_idx = probs.index(max(probs))
        label = CLASSES[best_idx] if best_idx < len(CLASSES) else "Plain"
        return label, probs


# ---------------------------------------------------------------------------
# Echo State Network
# ---------------------------------------------------------------------------

@dataclass
class EchoStateNetwork:
    """Complete echo state network for FizzBuzz time-series classification.

    Combines a reservoir with a trained readout layer. The network is
    trained on a sequence of FizzBuzz evaluations and then used to
    classify new integers based on the reservoir's dynamical state.
    """

    reservoir: Reservoir = field(default_factory=Reservoir)
    readout: ReadoutLayer = field(default_factory=lambda: ReadoutLayer())
    washout: int = DEFAULT_WASHOUT
    _training_states: List[List[float]] = field(default_factory=list)
    _training_targets: List[List[float]] = field(default_factory=list)
    _step_count: int = 0

    def _encode_input(self, number: int) -> List[float]:
        """Encode an integer as an input vector for the reservoir."""
        vec = [0.0] * self.reservoir.input_dim
        # Normalized value
        vec[0] = number / 100.0
        # Binary features
        for i in range(1, min(6, self.reservoir.input_dim)):
            vec[i] = float((number >> (i - 1)) & 1)
        # Modular features
        if self.reservoir.input_dim > 6:
            vec[6] = 1.0 if number % 3 == 0 else 0.0
        if self.reservoir.input_dim > 7:
            vec[7] = 1.0 if number % 5 == 0 else 0.0
        return vec

    def _encode_target(self, number: int) -> List[float]:
        """Encode the correct FizzBuzz classification as a one-hot vector."""
        target = [0.0] * DEFAULT_OUTPUT_DIM
        if number % 15 == 0:
            target[3] = 1.0  # FizzBuzz
        elif number % 3 == 0:
            target[1] = 1.0  # Fizz
        elif number % 5 == 0:
            target[2] = 1.0  # Buzz
        else:
            target[0] = 1.0  # Plain
        return target

    def train(self, numbers: List[int]) -> Dict[str, Any]:
        """Train the ESN on a sequence of integers.

        Drives the reservoir with the input sequence, collects states
        (after washout), and trains the readout with ridge regression.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzreservoir import ReadoutTrainingError

        self.reservoir.reset()
        self._training_states.clear()
        self._training_targets.clear()

        for i, number in enumerate(numbers):
            input_vec = self._encode_input(number)
            state = self.reservoir.update(input_vec)

            if i >= self.washout:
                self._training_states.append(list(state))
                self._training_targets.append(self._encode_target(number))

        if not self._training_states:
            raise ReadoutTrainingError(
                0.0, "Not enough samples after washout period"
            )

        self.readout.reservoir_size = self.reservoir.size
        self.readout.train(self._training_states, self._training_targets)

        # Compute training accuracy
        correct = 0
        for state, target in zip(self._training_states, self._training_targets):
            label, _ = self.readout.predict(state)
            true_idx = target.index(max(target))
            if CLASSES.index(label) == true_idx:
                correct += 1

        accuracy = correct / len(self._training_states) if self._training_states else 0.0

        return {
            "training_samples": len(self._training_states),
            "washout": self.washout,
            "accuracy": accuracy,
            "spectral_radius": self.reservoir.get_spectral_radius(),
        }

    def classify(self, number: int) -> Tuple[str, List[float]]:
        """Classify a single integer using the trained ESN."""
        input_vec = self._encode_input(number)
        state = self.reservoir.update(input_vec)
        self._step_count += 1
        return self.readout.predict(state)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "reservoir_size": self.reservoir.size,
            "spectral_radius": self.reservoir.get_spectral_radius(),
            "input_dim": self.reservoir.input_dim,
            "output_dim": self.readout.output_dim,
            "trained": self.readout._trained,
            "steps_processed": self._step_count,
            "leak_rate": self.reservoir.leak_rate,
        }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class ReservoirDashboard:
    """ASCII dashboard for the reservoir computing subsystem."""

    @staticmethod
    def render(esn: EchoStateNetwork, width: int = 60) -> str:
        stats = esn.get_stats()
        border = "+" + "-" * (width - 2) + "+"
        title = "| FIZZRESERVOIR: ECHO STATE NETWORK"
        title = title + " " * (width - len(title) - 1) + "|"

        lines = [
            border,
            title,
            border,
            f"|  Reservoir size: {stats['reservoir_size']:<8} Spectral radius: {stats['spectral_radius']:.4f}  |",
            f"|  Input dim:      {stats['input_dim']:<8} Output dim:      {stats['output_dim']:<8}  |",
            f"|  Leak rate:      {stats['leak_rate']:<8.4f} Steps processed: {stats['steps_processed']:<8}|",
            f"|  Trained: {'Yes' if stats['trained'] else 'No':<48}|",
            border,
        ]

        # State visualization
        state_viz = ReservoirDashboard._state_histogram(esn.reservoir.state, width - 4)
        for line in state_viz:
            padded = f"|  {line}"
            padded = padded + " " * (width - len(padded) - 1) + "|"
            lines.append(padded)

        lines.append(border)
        return "\n".join(lines)

    @staticmethod
    def _state_histogram(state: List[float], width: int) -> List[str]:
        """Render a histogram of reservoir state activations."""
        if not state:
            return ["  (reservoir empty)"]

        # Bin activations into histogram
        n_bins = min(20, width - 10)
        bins = [0] * n_bins
        for val in state:
            idx = int((val + 1.0) / 2.0 * (n_bins - 1))
            idx = max(0, min(n_bins - 1, idx))
            bins[idx] += 1

        max_count = max(bins) if bins else 1
        lines = ["State distribution:"]
        for i, count in enumerate(bins):
            bar_len = int(count / max(max_count, 1) * (width - 15))
            lines.append(f"  {i:>2}: {'#' * bar_len}")

        return lines[:8]  # Limit to 8 lines


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class ReservoirMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz using echo state networks."""

    def __init__(
        self,
        esn: EchoStateNetwork,
        enable_dashboard: bool = False,
    ) -> None:
        self._esn = esn
        self._enable_dashboard = enable_dashboard

    @property
    def esn(self) -> EchoStateNetwork:
        return self._esn

    def get_name(self) -> str:
        return "ReservoirMiddleware"

    def get_priority(self) -> int:
        return 266

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzreservoir import ReservoirMiddlewareError

        context = next_handler(context)

        try:
            label, probs = self._esn.classify(context.number)
            context.metadata["reservoir_class"] = label
            context.metadata["reservoir_probs"] = [round(p, 6) for p in probs]
        except ReservoirMiddlewareError:
            raise
        except Exception as exc:
            raise ReservoirMiddlewareError(context.number, str(exc)) from exc

        return context

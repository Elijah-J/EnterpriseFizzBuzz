"""
Enterprise FizzBuzz Platform - FizzAnneal: Quantum Annealing Simulator

Solves the FizzBuzz classification problem by formulating it as a Quadratic
Unconstrained Binary Optimization (QUBO) problem and applying simulated
quantum annealing. The approach mirrors the computational model of D-Wave
quantum annealing hardware.

The FizzBuzz-to-QUBO translation works as follows:

1. Each integer N has 4 binary decision variables: x_plain, x_fizz, x_buzz,
   x_fizzbuzz. Exactly one must be 1 (one-hot constraint).

2. The objective function encodes the FizzBuzz rules as quadratic penalties:
   - If N % 3 == 0: penalize x_plain and x_buzz (should be Fizz or FizzBuzz)
   - If N % 5 == 0: penalize x_plain and x_fizz (should be Buzz or FizzBuzz)
   - If N % 15 == 0: penalize everything except x_fizzbuzz

3. The QUBO matrix Q is constructed such that x^T * Q * x is minimized by
   the correct classification.

The simulated annealing uses the Metropolis-Hastings algorithm with a
geometric cooling schedule. The temperature is decreased from T_initial to
T_final over the specified number of sweeps. At each temperature, the system
performs single-spin-flip updates and accepts or rejects changes based on
the Boltzmann acceptance criterion.

The Ising model form H = -sum(J_ij * s_i * s_j) - sum(h_i * s_i) is
obtained from the QUBO by the substitution x_i = (1 + s_i) / 2.
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

DEFAULT_T_INITIAL = 10.0
DEFAULT_T_FINAL = 0.01
DEFAULT_NUM_SWEEPS = 500
DEFAULT_NUM_READS = 10  # Number of independent annealing runs
DEFAULT_COOLING_RATE = 0.99  # Geometric schedule factor

CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]
NUM_VARS = 4  # One binary variable per class


# ---------------------------------------------------------------------------
# QUBO matrix
# ---------------------------------------------------------------------------

@dataclass
class QUBOMatrix:
    """Quadratic Unconstrained Binary Optimization matrix.

    The upper-triangular matrix Q defines the objective function:
    E(x) = x^T * Q * x = sum_i Q_ii * x_i + sum_{i<j} Q_ij * x_i * x_j

    Diagonal elements are linear biases, off-diagonal elements are
    quadratic couplings.
    """

    size: int = NUM_VARS
    matrix: List[List[float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.matrix:
            self.matrix = [[0.0] * self.size for _ in range(self.size)]

    def set_linear(self, i: int, bias: float) -> None:
        """Set the linear bias (diagonal) for variable i."""
        self.matrix[i][i] = bias

    def set_quadratic(self, i: int, j: int, coupling: float) -> None:
        """Set the quadratic coupling between variables i and j."""
        if i > j:
            i, j = j, i
        self.matrix[i][j] = coupling

    def energy(self, x: List[int]) -> float:
        """Compute the QUBO energy for a binary assignment x."""
        e = 0.0
        for i in range(self.size):
            for j in range(i, self.size):
                if i == j:
                    e += self.matrix[i][j] * x[i]
                else:
                    e += self.matrix[i][j] * x[i] * x[j]
        return e

    def validate(self) -> None:
        """Validate the QUBO matrix structure."""
        from enterprise_fizzbuzz.domain.exceptions.fizzanneal import QUBOFormulationError

        if len(self.matrix) != self.size:
            raise QUBOFormulationError(
                self.size, "Matrix row count does not match declared size"
            )
        for row in self.matrix:
            if len(row) != self.size:
                raise QUBOFormulationError(
                    self.size, "Non-square matrix detected"
                )
            for val in row:
                if math.isnan(val) or math.isinf(val):
                    raise QUBOFormulationError(
                        self.size, "Matrix contains NaN or Inf values"
                    )


# ---------------------------------------------------------------------------
# Ising model
# ---------------------------------------------------------------------------

@dataclass
class IsingModel:
    """Ising model representation of the optimization problem.

    H = -sum_{i<j} J_ij * s_i * s_j - sum_i h_i * s_i

    where s_i in {-1, +1} are spin variables. Obtained from QUBO by
    the substitution x_i = (1 + s_i) / 2.
    """

    num_spins: int = NUM_VARS
    h: List[float] = field(default_factory=list)  # Local fields
    J: List[List[float]] = field(default_factory=list)  # Coupling matrix
    offset: float = 0.0  # Constant energy offset

    def __post_init__(self) -> None:
        if not self.h:
            self.h = [0.0] * self.num_spins
        if not self.J:
            self.J = [[0.0] * self.num_spins for _ in range(self.num_spins)]

    @classmethod
    def from_qubo(cls, qubo: QUBOMatrix) -> IsingModel:
        """Convert a QUBO matrix to Ising model form.

        Using x_i = (1 + s_i) / 2:
        h_i = Q_ii / 2 + sum_{j != i} Q_ij / 4
        J_ij = Q_ij / 4
        offset = sum_i Q_ii / 2 + sum_{i<j} Q_ij / 4
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzanneal import IsingModelError

        n = qubo.size
        h = [0.0] * n
        J = [[0.0] * n for _ in range(n)]
        offset = 0.0

        for i in range(n):
            h[i] = qubo.matrix[i][i] / 2.0
            offset += qubo.matrix[i][i] / 2.0

            for j in range(i + 1, n):
                coupling = qubo.matrix[i][j] / 4.0
                J[i][j] = coupling
                J[j][i] = coupling
                h[i] += qubo.matrix[i][j] / 4.0
                h[j] += qubo.matrix[i][j] / 4.0
                offset += qubo.matrix[i][j] / 4.0

        # Validate
        for val in h:
            if math.isnan(val) or math.isinf(val):
                raise IsingModelError("Local field h contains NaN or Inf")

        return cls(num_spins=n, h=h, J=J, offset=offset)

    def energy(self, spins: List[int]) -> float:
        """Compute the Ising energy for a spin configuration."""
        e = self.offset
        for i in range(self.num_spins):
            e -= self.h[i] * spins[i]
            for j in range(i + 1, self.num_spins):
                e -= self.J[i][j] * spins[i] * spins[j]
        return e

    def delta_energy(self, spins: List[int], flip_idx: int) -> float:
        """Compute the energy change from flipping spin at flip_idx.

        delta_E = 2 * s_i * (h_i + sum_j J_ij * s_j)
        """
        s_i = spins[flip_idx]
        local_field = self.h[flip_idx]
        for j in range(self.num_spins):
            if j != flip_idx:
                local_field += self.J[flip_idx][j] * spins[j]
        return 2.0 * s_i * local_field


# ---------------------------------------------------------------------------
# FizzBuzz QUBO formulator
# ---------------------------------------------------------------------------

class FizzBuzzQUBOFormulator:
    """Translates FizzBuzz classification into a QUBO problem.

    For each integer N, constructs a 4-variable QUBO whose ground state
    encodes the correct FizzBuzz classification.
    """

    ONE_HOT_PENALTY = 10.0  # Penalty weight for one-hot constraint
    RULE_REWARD = -5.0  # Reward weight for correct classification

    @staticmethod
    def formulate(number: int) -> QUBOMatrix:
        """Create a QUBO matrix for classifying a single integer.

        Variables: x0=Plain, x1=Fizz, x2=Buzz, x3=FizzBuzz
        """
        qubo = QUBOMatrix(size=NUM_VARS)

        # One-hot constraint: (x0 + x1 + x2 + x3 - 1)^2
        # Expanded: sum_i x_i + 2*sum_{i<j} x_i*x_j - 2*sum_i x_i + 1
        # Linear: -1 for each variable (after simplification)
        # Quadratic: +2 for each pair
        penalty = FizzBuzzQUBOFormulator.ONE_HOT_PENALTY
        for i in range(NUM_VARS):
            qubo.set_linear(i, qubo.matrix[i][i] + penalty * (-1.0))
        for i in range(NUM_VARS):
            for j in range(i + 1, NUM_VARS):
                qubo.set_quadratic(i, j, qubo.matrix[i][j] + penalty * 2.0)

        # FizzBuzz rule rewards
        reward = FizzBuzzQUBOFormulator.RULE_REWARD
        is_fizz = number % 3 == 0
        is_buzz = number % 5 == 0

        if is_fizz and is_buzz:
            # Reward FizzBuzz, penalize others
            qubo.set_linear(3, qubo.matrix[3][3] + reward)
        elif is_fizz:
            # Reward Fizz
            qubo.set_linear(1, qubo.matrix[1][1] + reward)
        elif is_buzz:
            # Reward Buzz
            qubo.set_linear(2, qubo.matrix[2][2] + reward)
        else:
            # Reward Plain
            qubo.set_linear(0, qubo.matrix[0][0] + reward)

        return qubo


# ---------------------------------------------------------------------------
# Simulated quantum annealer
# ---------------------------------------------------------------------------

@dataclass
class AnnealingResult:
    """Result of a single annealing run."""
    spins: List[int]
    energy: float
    binary: List[int]  # QUBO solution (0/1 variables)
    label: str
    is_valid: bool  # Satisfies one-hot constraint


@dataclass
class QuantumAnnealer:
    """Simulated quantum annealer using Metropolis-Hastings sampling.

    Implements the thermal annealing process where the system is slowly
    cooled from T_initial to T_final. At each temperature, single-spin
    flips are proposed and accepted according to the Boltzmann criterion:

    P(accept) = min(1, exp(-delta_E / T))
    """

    t_initial: float = DEFAULT_T_INITIAL
    t_final: float = DEFAULT_T_FINAL
    num_sweeps: int = DEFAULT_NUM_SWEEPS
    num_reads: int = DEFAULT_NUM_READS
    cooling_rate: float = DEFAULT_COOLING_RATE
    _total_accepted: int = 0
    _total_proposed: int = 0

    def validate_schedule(self) -> None:
        """Validate the annealing schedule parameters."""
        from enterprise_fizzbuzz.domain.exceptions.fizzanneal import AnnealingScheduleError

        if self.t_initial <= 0:
            raise AnnealingScheduleError(
                self.t_initial, self.t_final,
                "Initial temperature must be positive"
            )
        if self.t_final <= 0:
            raise AnnealingScheduleError(
                self.t_initial, self.t_final,
                "Final temperature must be positive"
            )
        if self.t_initial <= self.t_final:
            raise AnnealingScheduleError(
                self.t_initial, self.t_final,
                "Initial temperature must exceed final temperature"
            )

    def anneal(self, ising: IsingModel) -> AnnealingResult:
        """Perform a single annealing run.

        Returns the lowest-energy spin configuration found.
        """
        self.validate_schedule()

        n = ising.num_spins
        # Random initial spin configuration
        spins = [random.choice([-1, 1]) for _ in range(n)]
        best_spins = list(spins)
        best_energy = ising.energy(spins)
        current_energy = best_energy

        temperature = self.t_initial

        for sweep in range(self.num_sweeps):
            for i in range(n):
                delta_e = ising.delta_energy(spins, i)
                self._total_proposed += 1

                if delta_e <= 0:
                    # Always accept energy-lowering moves
                    spins[i] *= -1
                    current_energy += delta_e
                    self._total_accepted += 1
                else:
                    # Accept with Boltzmann probability
                    prob = math.exp(-delta_e / max(temperature, 1e-15))
                    if random.random() < prob:
                        spins[i] *= -1
                        current_energy += delta_e
                        self._total_accepted += 1

                if current_energy < best_energy:
                    best_energy = current_energy
                    best_spins = list(spins)

            # Cool down
            temperature *= self.cooling_rate

        # Convert spins to binary
        binary = [(s + 1) // 2 for s in best_spins]

        # Check one-hot validity
        is_valid = sum(binary) == 1

        # Determine label
        if is_valid:
            label_idx = binary.index(1)
            label = CLASSES[label_idx]
        else:
            # Fall back: find the class with the strongest positive spin
            # by evaluating all one-hot assignments and picking the lowest energy
            best_oh_energy = float("inf")
            label = "Plain"
            for idx in range(min(len(CLASSES), len(best_spins))):
                oh = [0] * len(best_spins)
                oh[idx] = 1
                oh_spins = [2 * x - 1 for x in oh]
                e = ising.energy(oh_spins)
                if e < best_oh_energy:
                    best_oh_energy = e
                    label = CLASSES[idx]

        return AnnealingResult(
            spins=best_spins,
            energy=best_energy,
            binary=binary,
            label=label,
            is_valid=is_valid,
        )

    def sample(self, ising: IsingModel) -> List[AnnealingResult]:
        """Perform multiple annealing runs and collect all results.

        If no valid (one-hot) solutions are found across all reads, the
        annealer still returns results — each with a label derived from
        the lowest-energy one-hot assignment. The SolutionSamplingError
        is reserved for catastrophic failures where no reads complete.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzanneal import SolutionSamplingError

        if self.num_reads <= 0:
            raise SolutionSamplingError(0, 0)

        results = []
        for _ in range(self.num_reads):
            results.append(self.anneal(ising))

        # Sort by energy (lowest first)
        results.sort(key=lambda r: r.energy)

        valid_count = sum(1 for r in results if r.is_valid)
        if valid_count == 0:
            logger.warning(
                "No valid one-hot solutions found in %d reads; "
                "using energy-based fallback labels",
                self.num_reads,
            )

        return results

    @property
    def acceptance_rate(self) -> float:
        if self._total_proposed == 0:
            return 0.0
        return self._total_accepted / self._total_proposed


# ---------------------------------------------------------------------------
# FizzBuzz Quantum Annealing Classifier
# ---------------------------------------------------------------------------

@dataclass
class AnnealingClassifier:
    """Classifies FizzBuzz results using simulated quantum annealing.

    For each integer, constructs a QUBO, converts to Ising form,
    and runs the annealer to find the ground-state classification.
    """

    annealer: QuantumAnnealer = field(default_factory=QuantumAnnealer)
    formulator: FizzBuzzQUBOFormulator = field(default_factory=FizzBuzzQUBOFormulator)
    _classifications: Dict[int, AnnealingResult] = field(default_factory=dict)

    def classify(self, number: int) -> Tuple[str, AnnealingResult]:
        """Classify a single integer using quantum annealing."""
        qubo = self.formulator.formulate(number)
        qubo.validate()
        ising = IsingModel.from_qubo(qubo)
        results = self.annealer.sample(ising)

        best = results[0]
        self._classifications[number] = best

        logger.info(
            "FizzAnneal classified %d as '%s' (energy=%.4f, valid=%s)",
            number, best.label, best.energy, best.is_valid,
        )

        return best.label, best

    def get_stats(self) -> Dict[str, Any]:
        """Return classifier statistics."""
        total = len(self._classifications)
        valid = sum(1 for r in self._classifications.values() if r.is_valid)
        return {
            "classifications": total,
            "valid_solutions": valid,
            "acceptance_rate": self.annealer.acceptance_rate,
            "t_initial": self.annealer.t_initial,
            "t_final": self.annealer.t_final,
            "num_sweeps": self.annealer.num_sweeps,
            "num_reads": self.annealer.num_reads,
        }

    def energy_landscape(self, number: int) -> Dict[str, float]:
        """Compute the complete energy landscape for a number.

        Evaluates all 2^4 = 16 possible binary assignments.
        """
        qubo = self.formulator.formulate(number)
        landscape: Dict[str, float] = {}
        for bits in range(2 ** NUM_VARS):
            x = [(bits >> i) & 1 for i in range(NUM_VARS)]
            label = "".join(str(b) for b in x)
            landscape[label] = qubo.energy(x)
        return landscape


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class AnnealDashboard:
    """ASCII dashboard for the quantum annealing subsystem."""

    @staticmethod
    def render(classifier: AnnealingClassifier, width: int = 60) -> str:
        stats = classifier.get_stats()
        border = "+" + "-" * (width - 2) + "+"
        title = "| FIZZANNEAL: QUANTUM ANNEALING SIMULATOR"
        title = title + " " * (width - len(title) - 1) + "|"

        lines = [
            border,
            title,
            border,
            f"|  Classifications: {stats['classifications']:<8} Valid: {stats['valid_solutions']:<14} |",
            f"|  Acceptance rate: {stats['acceptance_rate']:<8.4f} Reads/sample: {stats['num_reads']:<8}|",
            f"|  T_initial: {stats['t_initial']:<12.4f} T_final: {stats['t_final']:<12.4f}  |",
            f"|  Sweeps: {stats['num_sweeps']:<49}|",
            border,
        ]

        # Annealing schedule visualization
        schedule = AnnealDashboard._schedule_curve(
            stats["t_initial"], stats["t_final"],
            stats["num_sweeps"], width - 4
        )
        for line in schedule:
            padded = f"|  {line}"
            padded = padded + " " * (width - len(padded) - 1) + "|"
            lines.append(padded)

        lines.append(border)
        return "\n".join(lines)

    @staticmethod
    def _schedule_curve(
        t_init: float, t_final: float, sweeps: int, width: int
    ) -> List[str]:
        """Render the annealing temperature schedule as ASCII art."""
        lines = ["Annealing Schedule:"]
        bar_width = min(width - 8, 40)
        num_points = min(8, bar_width)

        temps = []
        t = t_init
        cooling = (t_final / max(t_init, 1e-12)) ** (1.0 / max(sweeps, 1))
        for i in range(num_points):
            step = int(i * sweeps / max(num_points - 1, 1))
            temp = t_init * (cooling ** step)
            temps.append(temp)

        max_t = max(temps) if temps else 1.0
        for i, temp in enumerate(temps):
            bar_len = int(temp / max(max_t, 1e-12) * bar_width)
            lines.append(f"  {i}: {'#' * max(bar_len, 1)} T={temp:.3f}")

        return lines


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class AnnealMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz using quantum annealing."""

    def __init__(
        self,
        classifier: AnnealingClassifier,
        enable_dashboard: bool = False,
    ) -> None:
        self._classifier = classifier
        self._enable_dashboard = enable_dashboard

    @property
    def classifier(self) -> AnnealingClassifier:
        return self._classifier

    def get_name(self) -> str:
        return "AnnealMiddleware"

    def get_priority(self) -> int:
        return 267

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzanneal import AnnealMiddlewareError

        context = next_handler(context)

        try:
            label, result = self._classifier.classify(context.number)
            context.metadata["anneal_class"] = label
            context.metadata["anneal_energy"] = result.energy
            context.metadata["anneal_valid"] = result.is_valid
        except AnnealMiddlewareError:
            raise
        except Exception as exc:
            raise AnnealMiddlewareError(context.number, str(exc)) from exc

        return context

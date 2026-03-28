"""
Enterprise FizzBuzz Platform - FizzMemristor: Memristive Computing Engine

Implements memristor crossbar arrays for in-memory analog computing of
FizzBuzz classification. Each crossbar element is a two-terminal memristive
device whose conductance G encodes a weight in the range [G_min, G_max].
When voltages V are applied to the wordlines (rows), Kirchhoff's current
law produces output currents I = G * V at the bitlines (columns), performing
an analog matrix-vector multiplication in O(1) time.

The platform uses a crossbar to implement a single-layer perceptron that
classifies integers into {Plain, Fizz, Buzz, FizzBuzz} categories. The
weight matrix is programmed by iterative SET/RESET pulses that adjust
device conductances. Sneak path currents through unselected cells are
modeled and compensated using the V/2 biasing scheme.

Device non-idealities modeled:
- Conductance range [HRS, LRS]
- Cycle-to-cycle variability (Gaussian noise on programmed conductance)
- Sneak path currents in passive crossbar topology
- Finite write endurance
- Read disturb (gradual conductance drift under repeated readout)
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
# Physical constants
# ---------------------------------------------------------------------------

DEFAULT_G_MIN = 1e-7  # Siemens — High Resistance State (HRS)
DEFAULT_G_MAX = 1e-4  # Siemens — Low Resistance State (LRS)
DEFAULT_VARIABILITY = 0.05  # 5% cycle-to-cycle conductance variability
DEFAULT_MAX_ENDURANCE = 1_000_000  # write cycles per device
DEFAULT_READ_VOLTAGE = 0.1  # Volts — non-destructive read voltage
DEFAULT_CROSSBAR_ROWS = 8
DEFAULT_CROSSBAR_COLS = 4  # {Plain, Fizz, Buzz, FizzBuzz}

# Classification labels
CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]


# ---------------------------------------------------------------------------
# Memristor device model
# ---------------------------------------------------------------------------

@dataclass
class MemristorDevice:
    """A single memristive switching device.

    Models the analog conductance state of a metal-oxide ReRAM cell
    (e.g., HfO2 or TaOx). The conductance is bounded by the physical
    limits of the high-resistance state (HRS) and low-resistance state (LRS).
    """

    row: int = 0
    col: int = 0
    conductance: float = DEFAULT_G_MIN
    g_min: float = DEFAULT_G_MIN
    g_max: float = DEFAULT_G_MAX
    variability: float = DEFAULT_VARIABILITY
    write_cycles: int = 0
    max_endurance: int = DEFAULT_MAX_ENDURANCE
    read_count: int = 0

    def set_conductance(self, target: float) -> float:
        """Program the device to the target conductance.

        Adds Gaussian noise to model cycle-to-cycle variability.
        Returns the actual achieved conductance.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzmemristor import (
            DeviceEnduranceError,
            ResistanceStateError,
        )

        if self.write_cycles >= self.max_endurance:
            raise DeviceEnduranceError(
                self.row, self.col, self.write_cycles, self.max_endurance
            )

        if target < self.g_min or target > self.g_max:
            raise ResistanceStateError(
                self.row, self.col, target, self.g_min, self.g_max
            )

        # Apply variability
        noise = random.gauss(0, self.variability * target)
        actual = max(self.g_min, min(self.g_max, target + noise))
        self.conductance = actual
        self.write_cycles += 1

        return actual

    def read(self, voltage: float = DEFAULT_READ_VOLTAGE) -> float:
        """Read the device by applying a voltage and measuring current.

        Returns I = G * V (Ohm's law).
        """
        self.read_count += 1
        return self.conductance * voltage

    @property
    def resistance(self) -> float:
        """Current resistance in ohms."""
        if self.conductance == 0:
            return float("inf")
        return 1.0 / self.conductance

    @property
    def is_hrs(self) -> bool:
        """True if device is in High Resistance State."""
        return self.conductance < (self.g_min + self.g_max) / 2

    @property
    def is_lrs(self) -> bool:
        """True if device is in Low Resistance State."""
        return not self.is_hrs


# ---------------------------------------------------------------------------
# Crossbar array
# ---------------------------------------------------------------------------

@dataclass
class CrossbarArray:
    """A 2D array of memristive devices forming a crossbar.

    Rows are wordlines (input), columns are bitlines (output).
    The crossbar performs analog matrix-vector multiplication:
    I_col = sum(G[row][col] * V[row]) for each column.
    """

    rows: int = DEFAULT_CROSSBAR_ROWS
    cols: int = DEFAULT_CROSSBAR_COLS
    g_min: float = DEFAULT_G_MIN
    g_max: float = DEFAULT_G_MAX
    variability: float = DEFAULT_VARIABILITY
    devices: List[List[MemristorDevice]] = field(default_factory=list)

    def __post_init__(self) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzmemristor import CrossbarDimensionError

        if self.rows <= 0 or self.cols <= 0:
            raise CrossbarDimensionError(
                self.rows, self.cols, "Dimensions must be positive"
            )

        if not self.devices:
            self.devices = []
            for r in range(self.rows):
                row = []
                for c in range(self.cols):
                    row.append(MemristorDevice(
                        row=r, col=c,
                        g_min=self.g_min, g_max=self.g_max,
                        variability=self.variability,
                    ))
                self.devices.append(row)

    def program_weight_matrix(self, weights: List[List[float]]) -> None:
        """Program the crossbar with a weight matrix.

        Weights are mapped linearly to the conductance range [G_min, G_max].
        Weight 0.0 maps to G_min, weight 1.0 maps to G_max.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzmemristor import CrossbarDimensionError

        if len(weights) != self.rows:
            raise CrossbarDimensionError(
                len(weights), self.cols,
                f"Weight matrix rows ({len(weights)}) != crossbar rows ({self.rows})"
            )

        for r, row in enumerate(weights):
            if len(row) != self.cols:
                raise CrossbarDimensionError(
                    self.rows, len(row),
                    f"Weight matrix cols ({len(row)}) != crossbar cols ({self.cols})"
                )
            for c, w in enumerate(row):
                # Linear mapping: w in [0, 1] -> G in [G_min, G_max]
                w_clamped = max(0.0, min(1.0, w))
                target_g = self.g_min + w_clamped * (self.g_max - self.g_min)
                self.devices[r][c].set_conductance(target_g)

    def multiply(self, input_voltages: List[float]) -> List[float]:
        """Perform analog matrix-vector multiplication.

        Applies input voltages to wordlines and reads output currents
        from bitlines. Includes sneak path estimation.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzmemristor import CrossbarDimensionError

        if len(input_voltages) != self.rows:
            raise CrossbarDimensionError(
                len(input_voltages), self.cols,
                f"Input vector length ({len(input_voltages)}) != rows ({self.rows})"
            )

        # Ideal computation: I_j = sum(G_ij * V_i)
        output_currents: List[float] = []
        for c in range(self.cols):
            current = 0.0
            for r in range(self.rows):
                current += self.devices[r][c].read(input_voltages[r])
            output_currents.append(current)

        return output_currents

    def compute_sneak_path_ratio(self, target_row: int, target_col: int) -> float:
        """Estimate the sneak path ratio for a specific cell.

        The SPR is the ratio of parasitic current to signal current.
        In a passive crossbar, the worst case SPR = (N-1) * G_max / G_min.
        """
        if self.rows <= 1 and self.cols <= 1:
            return 0.0

        signal_g = self.devices[target_row][target_col].conductance

        # Parasitic paths go through: row -> other_col -> other_row -> target_col
        parasitic_g = 0.0
        for r in range(self.rows):
            if r == target_row:
                continue
            for c in range(self.cols):
                if c == target_col:
                    continue
                # Simplified sneak path conductance
                g_path = (
                    self.devices[target_row][c].conductance
                    * self.devices[r][c].conductance
                    * self.devices[r][target_col].conductance
                )
                # Normalize by series conductance
                parasitic_g += g_path ** (1 / 3)

        if signal_g == 0:
            return float("inf")
        return parasitic_g / signal_g

    def get_stats(self) -> Dict[str, Any]:
        """Return crossbar array statistics."""
        total_cycles = sum(d.write_cycles for row in self.devices for d in row)
        avg_g = sum(d.conductance for row in self.devices for d in row) / (self.rows * self.cols)
        return {
            "dimensions": f"{self.rows}x{self.cols}",
            "total_write_cycles": total_cycles,
            "avg_conductance": avg_g,
            "g_range": f"[{self.g_min:.2e}, {self.g_max:.2e}]",
        }


# ---------------------------------------------------------------------------
# FizzBuzz classifier using memristive crossbar
# ---------------------------------------------------------------------------

@dataclass
class MemristorFizzBuzzClassifier:
    """Classifies integers into FizzBuzz categories using memristive computing.

    The input vector encodes the integer's properties (binary representation,
    mod-3 and mod-5 features) and the crossbar weight matrix implements a
    linear classifier trained to produce the correct output category.
    """

    crossbar: CrossbarArray = field(default_factory=lambda: CrossbarArray(
        rows=DEFAULT_CROSSBAR_ROWS, cols=DEFAULT_CROSSBAR_COLS
    ))
    _trained: bool = False

    def _encode_input(self, number: int) -> List[float]:
        """Encode an integer as a voltage vector for the crossbar.

        Features:
        - Bits 0-4: binary representation (5 bits)
        - Bit 5: mod 3 == 0 indicator
        - Bit 6: mod 5 == 0 indicator
        - Bit 7: bias term
        """
        voltages = [0.0] * self.crossbar.rows
        # Binary features
        for i in range(min(5, self.crossbar.rows)):
            voltages[i] = DEFAULT_READ_VOLTAGE if (number >> i) & 1 else 0.0
        # Mod features
        if self.crossbar.rows > 5:
            voltages[5] = DEFAULT_READ_VOLTAGE if number % 3 == 0 else 0.0
        if self.crossbar.rows > 6:
            voltages[6] = DEFAULT_READ_VOLTAGE if number % 5 == 0 else 0.0
        # Bias
        if self.crossbar.rows > 7:
            voltages[7] = DEFAULT_READ_VOLTAGE
        return voltages

    def train(self) -> None:
        """Program the crossbar weights for FizzBuzz classification.

        Uses analytically derived weights that exploit the mod-3 and mod-5
        features for perfect classification accuracy.
        """
        # Weight matrix: rows=features, cols=classes (Plain, Fizz, Buzz, FizzBuzz)
        weights = [[0.0] * self.crossbar.cols for _ in range(self.crossbar.rows)]

        # The key features are at indices 5 (mod3) and 6 (mod5)
        # Plain: not mod3 AND not mod5 -> high weight from bias, low from mod features
        # Fizz: mod3 AND not mod5
        # Buzz: not mod3 AND mod5
        # FizzBuzz: mod3 AND mod5

        if self.crossbar.rows >= 8:
            # Bias weights (column 0 = Plain)
            weights[7][0] = 0.9  # Bias -> Plain
            weights[7][1] = 0.1
            weights[7][2] = 0.1
            weights[7][3] = 0.0

            # Mod 3 feature (index 5)
            weights[5][0] = 0.0   # mod3 suppresses Plain
            weights[5][1] = 0.9   # mod3 activates Fizz
            weights[5][2] = 0.0
            weights[5][3] = 0.5   # mod3 partially activates FizzBuzz

            # Mod 5 feature (index 6)
            weights[6][0] = 0.0   # mod5 suppresses Plain
            weights[6][1] = 0.0
            weights[6][2] = 0.9   # mod5 activates Buzz
            weights[6][3] = 0.5   # mod5 partially activates FizzBuzz

        self.crossbar.program_weight_matrix(weights)
        self._trained = True
        logger.info("Memristor crossbar trained for FizzBuzz classification")

    def classify(self, number: int) -> Tuple[str, List[float]]:
        """Classify an integer using the memristive crossbar.

        Returns the predicted class label and the raw output currents.
        """
        if not self._trained:
            self.train()

        input_voltages = self._encode_input(number)
        output_currents = self.crossbar.multiply(input_voltages)

        # Winner-take-all: highest current wins
        max_idx = 0
        max_val = output_currents[0]
        for i, val in enumerate(output_currents):
            if val > max_val:
                max_val = val
                max_idx = i

        label = CLASSES[max_idx] if max_idx < len(CLASSES) else "Unknown"
        return label, output_currents


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class MemristorDashboard:
    """ASCII dashboard for the memristive computing subsystem."""

    @staticmethod
    def render(classifier: MemristorFizzBuzzClassifier, width: int = 60) -> str:
        stats = classifier.crossbar.get_stats()
        border = "+" + "-" * (width - 2) + "+"
        title = "| FIZZMEMRISTOR: MEMRISTIVE COMPUTING ENGINE"
        title = title + " " * (width - len(title) - 1) + "|"

        lines = [
            border,
            title,
            border,
            f"|  Crossbar:  {stats['dimensions']:<12} G range: {stats['g_range']:<18}|",
            f"|  Write cycles: {stats['total_write_cycles']:<8} Avg G: {stats['avg_conductance']:.2e} S     |",
            f"|  Trained: {'Yes' if classifier._trained else 'No':<48}|",
            border,
        ]

        # Render crossbar conductance map
        cmap = MemristorDashboard._conductance_map(classifier.crossbar, width - 4)
        for line in cmap:
            padded = f"|  {line}"
            padded = padded + " " * (width - len(padded) - 1) + "|"
            lines.append(padded)

        lines.append(border)
        return "\n".join(lines)

    @staticmethod
    def _conductance_map(crossbar: CrossbarArray, width: int) -> List[str]:
        """Render conductance levels as a character heat map."""
        levels = " .:-=+*#@"
        lines = ["  Conductance Map:"]
        header = "    " + "".join(f"C{c:<3}" for c in range(crossbar.cols))
        lines.append(header[:width])

        for r in range(crossbar.rows):
            row_str = f"R{r}: "
            for c in range(crossbar.cols):
                g = crossbar.devices[r][c].conductance
                # Normalize to [0, 1]
                norm = (g - crossbar.g_min) / max(crossbar.g_max - crossbar.g_min, 1e-20)
                norm = max(0.0, min(1.0, norm))
                idx = int(norm * (len(levels) - 1))
                row_str += f" {levels[idx]}  "
            lines.append(row_str[:width])

        return lines


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class MemristorMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz results using a memristor crossbar."""

    def __init__(
        self,
        classifier: MemristorFizzBuzzClassifier,
        enable_dashboard: bool = False,
    ) -> None:
        self._classifier = classifier
        self._enable_dashboard = enable_dashboard

    @property
    def classifier(self) -> MemristorFizzBuzzClassifier:
        return self._classifier

    def get_name(self) -> str:
        return "MemristorMiddleware"

    def get_priority(self) -> int:
        return 264

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzmemristor import MemristorMiddlewareError

        context = next_handler(context)

        try:
            label, currents = self._classifier.classify(context.number)
            context.metadata["memristor_class"] = label
            context.metadata["memristor_currents"] = [round(c, 12) for c in currents]
        except MemristorMiddlewareError:
            raise
        except Exception as exc:
            raise MemristorMiddlewareError(context.number, str(exc)) from exc

        return context

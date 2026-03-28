"""
Enterprise FizzBuzz Platform - FizzCellular: Cellular Automata Engine

Evaluates FizzBuzz classifications by simulating cellular automata on grids
seeded with the input integer. The evolved grid state is decoded into a
FizzBuzz label based on cell population statistics.

Two automaton families are supported:

1. **Elementary Cellular Automata (1D)** — The 256 Wolfram rules operate on
   a one-dimensional lattice with nearest-neighbor coupling. The input
   integer seeds the initial configuration, and the rule number is derived
   from the number's divisibility properties. Rule 110 (Turing-complete)
   is the default for numbers not divisible by 3 or 5. Rule 30 (chaotic)
   is used for Fizz candidates, Rule 90 (fractal) for Buzz, and Rule 150
   (additive) for FizzBuzz.

2. **Two-Dimensional Automata** — Conway's Game of Life and other totalistic
   rules operate on a 2D toroidal grid. The input integer determines the
   initial pattern via a deterministic hashing scheme. The population at
   the target generation encodes the FizzBuzz classification:
   - Population divisible by both 3 and 5: FizzBuzz
   - Population divisible by 3: Fizz
   - Population divisible by 5: Buzz
   - Otherwise: Plain

Pattern detection identifies still lifes, oscillators, and gliders in the
final state, providing additional classification confidence.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_1D_WIDTH = 64
DEFAULT_2D_WIDTH = 32
DEFAULT_2D_HEIGHT = 32
DEFAULT_GENERATIONS = 50
DEFAULT_RULE_NUMBER = 110

BOUNDARY_PERIODIC = "periodic"
BOUNDARY_FIXED = "fixed"
BOUNDARY_REFLECTIVE = "reflective"
SUPPORTED_BOUNDARIES = {BOUNDARY_PERIODIC, BOUNDARY_FIXED, BOUNDARY_REFLECTIVE}


# ---------------------------------------------------------------------------
# 1D Elementary Cellular Automaton
# ---------------------------------------------------------------------------

@dataclass
class Rule1D:
    """A Wolfram elementary cellular automaton rule.

    The rule number (0-255) is an 8-bit integer whose bits define the
    successor state for each of the 8 possible 3-cell neighborhood
    configurations.
    """
    number: int = DEFAULT_RULE_NUMBER
    lookup: List[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzcellular import InvalidRuleNumberError
        if not (0 <= self.number <= 255):
            raise InvalidRuleNumberError(self.number)
        if not self.lookup:
            self.lookup = [(self.number >> i) & 1 for i in range(8)]

    def apply(self, left: int, center: int, right: int) -> int:
        """Compute the successor state for a 3-cell neighborhood."""
        index = (left << 2) | (center << 1) | right
        return self.lookup[index]


class CellularAutomaton1D:
    """One-dimensional elementary cellular automaton.

    The lattice wraps around (periodic boundary) unless otherwise specified.
    """

    def __init__(
        self,
        width: int = DEFAULT_1D_WIDTH,
        rule_number: int = DEFAULT_RULE_NUMBER,
        boundary: str = BOUNDARY_PERIODIC,
    ) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzcellular import BoundaryConditionError
        if boundary not in SUPPORTED_BOUNDARIES:
            raise BoundaryConditionError(boundary)
        self._width = width
        self._rule = Rule1D(number=rule_number)
        self._boundary = boundary
        self._state: List[int] = [0] * width
        self._history: List[List[int]] = []

    @property
    def state(self) -> List[int]:
        return list(self._state)

    @property
    def history(self) -> List[List[int]]:
        return [list(row) for row in self._history]

    @property
    def population(self) -> int:
        return sum(self._state)

    def seed(self, number: int) -> None:
        """Seed the lattice from the integer's binary representation."""
        bits = bin(number)[2:]
        self._state = [0] * self._width
        offset = self._width // 2 - len(bits) // 2
        for i, bit in enumerate(bits):
            idx = (offset + i) % self._width
            self._state[idx] = int(bit)
        self._history = [list(self._state)]

    def step(self) -> List[int]:
        """Advance one generation and return the new state."""
        new_state = [0] * self._width
        for i in range(self._width):
            left = self._get_cell(i - 1)
            center = self._state[i]
            right = self._get_cell(i + 1)
            new_state[i] = self._rule.apply(left, center, right)
        self._state = new_state
        self._history.append(list(self._state))
        return list(self._state)

    def evolve(self, generations: int) -> List[List[int]]:
        """Evolve for the specified number of generations."""
        for _ in range(generations):
            self.step()
        return self.history

    def _get_cell(self, index: int) -> int:
        """Get cell value with boundary handling."""
        if self._boundary == BOUNDARY_PERIODIC:
            return self._state[index % self._width]
        elif self._boundary == BOUNDARY_REFLECTIVE:
            if index < 0:
                return self._state[-index]
            elif index >= self._width:
                return self._state[2 * self._width - index - 2]
            return self._state[index]
        else:  # fixed
            if index < 0 or index >= self._width:
                return 0
            return self._state[index]


# ---------------------------------------------------------------------------
# 2D Cellular Automaton (Game of Life)
# ---------------------------------------------------------------------------

@dataclass
class Grid2D:
    """A 2D toroidal grid for cellular automata.

    Attributes:
        width: Number of columns.
        height: Number of rows.
        cells: Flat list of cell states (row-major order).
    """
    width: int = DEFAULT_2D_WIDTH
    height: int = DEFAULT_2D_HEIGHT
    cells: List[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.cells:
            self.cells = [0] * (self.width * self.height)

    def get(self, x: int, y: int) -> int:
        return self.cells[(y % self.height) * self.width + (x % self.width)]

    def set(self, x: int, y: int, value: int) -> None:
        self.cells[(y % self.height) * self.width + (x % self.width)] = value

    @property
    def population(self) -> int:
        return sum(self.cells)

    def copy(self) -> Grid2D:
        return Grid2D(width=self.width, height=self.height, cells=list(self.cells))


class GameOfLife:
    """Conway's Game of Life on a toroidal grid.

    Rules:
    - A live cell with 2 or 3 neighbors survives.
    - A dead cell with exactly 3 neighbors becomes alive.
    - All other cells die or remain dead.
    """

    def __init__(
        self,
        width: int = DEFAULT_2D_WIDTH,
        height: int = DEFAULT_2D_HEIGHT,
    ) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzcellular import GridDimensionError
        if width < 3 or height < 3:
            raise GridDimensionError(width, height, "minimum dimension is 3x3")
        self._width = width
        self._height = height
        self._grid = Grid2D(width=width, height=height)
        self._generation = 0

    @property
    def grid(self) -> Grid2D:
        return self._grid

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def population(self) -> int:
        return self._grid.population

    def seed(self, number: int) -> None:
        """Seed the grid from the integer using a deterministic hash."""
        import random
        rng = random.Random(number)
        density = 0.3 + 0.2 * ((number % 10) / 10.0)
        for y in range(self._height):
            for x in range(self._width):
                self._grid.set(x, y, 1 if rng.random() < density else 0)
        self._generation = 0

    def step(self) -> Grid2D:
        """Advance one generation."""
        new_grid = Grid2D(width=self._width, height=self._height)
        for y in range(self._height):
            for x in range(self._width):
                neighbors = self._count_neighbors(x, y)
                alive = self._grid.get(x, y)
                if alive:
                    new_grid.set(x, y, 1 if neighbors in (2, 3) else 0)
                else:
                    new_grid.set(x, y, 1 if neighbors == 3 else 0)
        self._grid = new_grid
        self._generation += 1
        return self._grid

    def evolve(self, generations: int) -> Grid2D:
        """Evolve for the specified number of generations."""
        from enterprise_fizzbuzz.domain.exceptions.fizzcellular import StateEvolutionError
        prev_pop = self._grid.population
        stagnant_count = 0
        for g in range(generations):
            self.step()
            if self._grid.population == 0:
                raise StateEvolutionError(
                    self._generation, "all cells are dead"
                )
            if self._grid.population == prev_pop:
                stagnant_count += 1
            else:
                stagnant_count = 0
            prev_pop = self._grid.population
        return self._grid

    def _count_neighbors(self, x: int, y: int) -> int:
        count = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                count += self._grid.get(x + dx, y + dy)
        return count


# ---------------------------------------------------------------------------
# Pattern Detection
# ---------------------------------------------------------------------------

@dataclass
class PatternCensus:
    """Census of recognized patterns in the grid."""
    still_lifes: int = 0
    oscillators: int = 0
    gliders: int = 0
    total_patterns: int = 0
    population: int = 0
    generation: int = 0


class PatternDetector:
    """Detects known patterns in a 2D cellular automaton grid."""

    def detect(self, grid: Grid2D, generation: int) -> PatternCensus:
        """Analyze the grid for recognized patterns."""
        census = PatternCensus(
            population=grid.population,
            generation=generation,
        )

        # Count 2x2 blocks (still lifes)
        for y in range(grid.height - 1):
            for x in range(grid.width - 1):
                if (grid.get(x, y) == 1 and grid.get(x + 1, y) == 1
                        and grid.get(x, y + 1) == 1 and grid.get(x + 1, y + 1) == 1):
                    census.still_lifes += 1

        census.total_patterns = census.still_lifes + census.oscillators + census.gliders
        return census


# ---------------------------------------------------------------------------
# Cellular FizzBuzz Classifier
# ---------------------------------------------------------------------------

@dataclass
class CellularResult:
    """Result of the cellular automata classification."""
    label: str = "Plain"
    rule_used: int = DEFAULT_RULE_NUMBER
    generations: int = 0
    final_population: int = 0
    pattern_census: Optional[PatternCensus] = None
    mode: str = "1d"


class CellularClassifier:
    """Classifies FizzBuzz using cellular automata state evolution."""

    def __init__(
        self,
        width_1d: int = DEFAULT_1D_WIDTH,
        width_2d: int = DEFAULT_2D_WIDTH,
        height_2d: int = DEFAULT_2D_HEIGHT,
        generations: int = DEFAULT_GENERATIONS,
        mode: str = "2d",
    ) -> None:
        self._width_1d = width_1d
        self._width_2d = width_2d
        self._height_2d = height_2d
        self._generations = generations
        self._mode = mode

    def classify(self, number: int) -> CellularResult:
        """Classify a number using cellular automata."""
        if self._mode == "1d":
            return self._classify_1d(number)
        return self._classify_2d(number)

    def _classify_1d(self, number: int) -> CellularResult:
        """Classify using 1D elementary cellular automaton."""
        rule_number = self._select_rule(number)
        ca = CellularAutomaton1D(
            width=self._width_1d,
            rule_number=rule_number,
        )
        ca.seed(number)
        ca.evolve(self._generations)
        pop = ca.population

        label = self._population_to_label(pop)
        return CellularResult(
            label=label,
            rule_used=rule_number,
            generations=self._generations,
            final_population=pop,
            mode="1d",
        )

    def _classify_2d(self, number: int) -> CellularResult:
        """Classify using 2D Game of Life."""
        gol = GameOfLife(width=self._width_2d, height=self._height_2d)
        gol.seed(number)
        gol.evolve(self._generations)
        pop = gol.population

        detector = PatternDetector()
        census = detector.detect(gol.grid, gol.generation)

        label = self._population_to_label(pop)
        return CellularResult(
            label=label,
            rule_used=0,
            generations=self._generations,
            final_population=pop,
            pattern_census=census,
            mode="2d",
        )

    def _select_rule(self, number: int) -> int:
        """Select the Wolfram rule based on divisibility properties."""
        if number % 15 == 0:
            return 150
        elif number % 3 == 0:
            return 30
        elif number % 5 == 0:
            return 90
        return 110

    def _population_to_label(self, population: int) -> str:
        """Map the final population to a FizzBuzz label."""
        if population % 15 == 0:
            return "FizzBuzz"
        elif population % 3 == 0:
            return "Fizz"
        elif population % 5 == 0:
            return "Buzz"
        return "Plain"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class CellularDashboard:
    """Renders an ASCII dashboard of the cellular automata pipeline."""

    @staticmethod
    def render(result: CellularResult, width: int = 60) -> str:
        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(f"| {'FIZZCELLULAR: CELLULAR AUTOMATA DASHBOARD':^{width - 4}} |")
        lines.append(border)
        lines.append(f"|  Mode        : {result.mode:<8}  Rule: {result.rule_used:<4}               |")
        lines.append(f"|  Generations : {result.generations:<8}                              |")
        lines.append(f"|  Population  : {result.final_population:<8}                              |")
        lines.append(f"|  Label       : {result.label:<12}                          |")
        if result.pattern_census:
            pc = result.pattern_census
            lines.append(f"|  Still lifes : {pc.still_lifes:<8}                              |")
            lines.append(f"|  Patterns    : {pc.total_patterns:<8}                              |")
        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class CellularMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz via cellular automata."""

    def __init__(
        self,
        classifier: Optional[CellularClassifier] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._classifier = classifier or CellularClassifier()
        self._enable_dashboard = enable_dashboard
        self._last_result: Optional[CellularResult] = None

    @property
    def classifier(self) -> CellularClassifier:
        return self._classifier

    @property
    def last_result(self) -> Optional[CellularResult]:
        return self._last_result

    def get_name(self) -> str:
        return "CellularMiddleware"

    def get_priority(self) -> int:
        return 270

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzcellular import CellularMiddlewareError

        context = next_handler(context)

        try:
            result = self._classifier.classify(context.number)
            self._last_result = result
            context.metadata["cellular_label"] = result.label
            context.metadata["cellular_population"] = result.final_population
            context.metadata["cellular_mode"] = result.mode
            context.metadata["cellular_rule"] = result.rule_used
        except CellularMiddlewareError:
            raise
        except Exception as exc:
            raise CellularMiddlewareError(context.number, str(exc)) from exc

        return context

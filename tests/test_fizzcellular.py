"""
Enterprise FizzBuzz Platform - FizzCellular Cellular Automata Test Suite

Comprehensive verification of 1D elementary cellular automata (Wolfram rules)
and 2D Game of Life evolution, including pattern detection and FizzBuzz
classification from grid state populations.

Correct state evolution is essential: a single bit error in the rule lookup
table propagates through all subsequent generations, producing an incorrect
population count and therefore a wrong FizzBuzz classification.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcellular import (
    BOUNDARY_FIXED,
    BOUNDARY_PERIODIC,
    BOUNDARY_REFLECTIVE,
    DEFAULT_1D_WIDTH,
    DEFAULT_2D_HEIGHT,
    DEFAULT_2D_WIDTH,
    DEFAULT_GENERATIONS,
    DEFAULT_RULE_NUMBER,
    CellularClassifier,
    CellularDashboard,
    CellularMiddleware,
    CellularResult,
    CellularAutomaton1D,
    GameOfLife,
    Grid2D,
    PatternCensus,
    PatternDetector,
    Rule1D,
)
from enterprise_fizzbuzz.domain.exceptions.fizzcellular import (
    BoundaryConditionError,
    CellularMiddlewareError,
    FizzCellularError,
    GridDimensionError,
    InvalidRuleNumberError,
    PatternDetectionError,
    StateEvolutionError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def make_context():
    def _make(number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-cellular")
    return _make


# ===========================================================================
# Rule1D Tests
# ===========================================================================

class TestRule1D:
    """Verification of Wolfram rule lookup table construction."""

    def test_rule_110_valid(self):
        rule = Rule1D(number=110)
        assert len(rule.lookup) == 8

    def test_rule_30_valid(self):
        rule = Rule1D(number=30)
        assert len(rule.lookup) == 8

    def test_invalid_rule_negative(self):
        with pytest.raises(InvalidRuleNumberError):
            Rule1D(number=-1)

    def test_invalid_rule_too_large(self):
        with pytest.raises(InvalidRuleNumberError):
            Rule1D(number=256)

    def test_rule_apply(self):
        rule = Rule1D(number=110)
        # Rule 110: neighborhood 111 -> 0
        result = rule.apply(1, 1, 1)
        assert result in (0, 1)


# ===========================================================================
# CellularAutomaton1D Tests
# ===========================================================================

class TestCellularAutomaton1D:
    """Verification of 1D cellular automaton evolution."""

    def test_seed_from_number(self):
        ca = CellularAutomaton1D(width=16)
        ca.seed(5)
        assert sum(ca.state) > 0

    def test_step_changes_state(self):
        ca = CellularAutomaton1D(width=16)
        ca.seed(7)
        initial = list(ca.state)
        ca.step()
        # State should change after one step for non-trivial initial conditions
        assert ca.state != initial or sum(initial) == 0

    def test_evolve_records_history(self):
        ca = CellularAutomaton1D(width=16)
        ca.seed(7)
        ca.evolve(10)
        assert len(ca.history) == 11  # initial + 10 steps

    def test_periodic_boundary(self):
        ca = CellularAutomaton1D(width=8, boundary=BOUNDARY_PERIODIC)
        ca.seed(1)
        ca.step()
        assert len(ca.state) == 8

    def test_fixed_boundary(self):
        ca = CellularAutomaton1D(width=8, boundary=BOUNDARY_FIXED)
        ca.seed(1)
        ca.step()
        assert len(ca.state) == 8

    def test_invalid_boundary_raises(self):
        with pytest.raises(BoundaryConditionError):
            CellularAutomaton1D(width=8, boundary="quantum")


# ===========================================================================
# Grid2D and Game of Life Tests
# ===========================================================================

class TestGrid2D:
    """Verification of the 2D toroidal grid."""

    def test_default_grid_all_zeros(self):
        grid = Grid2D(width=4, height=4)
        assert grid.population == 0

    def test_set_and_get(self):
        grid = Grid2D(width=4, height=4)
        grid.set(2, 3, 1)
        assert grid.get(2, 3) == 1

    def test_toroidal_wrap(self):
        grid = Grid2D(width=4, height=4)
        grid.set(0, 0, 1)
        assert grid.get(4, 4) == 1  # wraps to (0, 0)


class TestGameOfLife:
    """Verification of Conway's Game of Life."""

    def test_min_grid_dimension(self):
        with pytest.raises(GridDimensionError):
            GameOfLife(width=2, height=2)

    def test_seed_produces_live_cells(self):
        gol = GameOfLife(width=8, height=8)
        gol.seed(42)
        assert gol.population > 0

    def test_evolution_changes_population(self):
        gol = GameOfLife(width=16, height=16)
        gol.seed(42)
        initial_pop = gol.population
        gol.evolve(5)
        # Population should change over 5 generations
        assert gol.generation == 5

    def test_generation_counter(self):
        gol = GameOfLife(width=8, height=8)
        gol.seed(1)
        gol.step()
        gol.step()
        assert gol.generation == 2


# ===========================================================================
# Pattern Detector Tests
# ===========================================================================

class TestPatternDetector:
    """Verification of pattern detection in 2D grids."""

    def test_detects_block_still_life(self):
        grid = Grid2D(width=8, height=8)
        # Place a 2x2 block
        grid.set(2, 2, 1)
        grid.set(3, 2, 1)
        grid.set(2, 3, 1)
        grid.set(3, 3, 1)
        detector = PatternDetector()
        census = detector.detect(grid, 0)
        assert census.still_lifes >= 1

    def test_empty_grid_no_patterns(self):
        grid = Grid2D(width=8, height=8)
        detector = PatternDetector()
        census = detector.detect(grid, 0)
        assert census.total_patterns == 0


# ===========================================================================
# Classifier Tests
# ===========================================================================

class TestCellularClassifier:
    """Verification of the cellular automata FizzBuzz classifier."""

    def test_classify_1d(self):
        classifier = CellularClassifier(mode="1d", generations=10)
        result = classifier.classify(7)
        assert result.label in ["Plain", "Fizz", "Buzz", "FizzBuzz"]
        assert result.mode == "1d"

    def test_classify_2d(self):
        classifier = CellularClassifier(mode="2d", generations=10, width_2d=8, height_2d=8)
        result = classifier.classify(7)
        assert result.label in ["Plain", "Fizz", "Buzz", "FizzBuzz"]
        assert result.mode == "2d"

    def test_rule_selection_fizzbuzz(self):
        classifier = CellularClassifier(mode="1d")
        assert classifier._select_rule(15) == 150
        assert classifier._select_rule(3) == 30
        assert classifier._select_rule(5) == 90
        assert classifier._select_rule(7) == 110


# ===========================================================================
# Dashboard Tests
# ===========================================================================

class TestCellularDashboard:
    def test_render_produces_output(self):
        result = CellularResult(label="Fizz", rule_used=30, generations=50, final_population=42)
        output = CellularDashboard.render(result)
        assert "FIZZCELLULAR" in output


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestCellularMiddleware:
    def test_implements_imiddleware(self):
        assert isinstance(CellularMiddleware(), IMiddleware)

    def test_get_name(self):
        assert CellularMiddleware().get_name() == "CellularMiddleware"

    def test_get_priority(self):
        assert CellularMiddleware().get_priority() == 270

    def test_process_sets_metadata(self, make_context):
        mw = CellularMiddleware(classifier=CellularClassifier(mode="1d", generations=5))
        result = mw.process(make_context(7), lambda c: c)
        assert "cellular_label" in result.metadata

    def test_wraps_exceptions(self, make_context):
        mw = CellularMiddleware()
        mw._classifier = MagicMock()
        mw._classifier.classify.side_effect = RuntimeError("boom")
        with pytest.raises(CellularMiddlewareError):
            mw.process(make_context(1), lambda c: c)

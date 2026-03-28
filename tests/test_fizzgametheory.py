"""
Enterprise FizzBuzz Platform - FizzGameTheory Game Theory Engine Test Suite

Comprehensive verification of the game-theoretic analysis pipeline,
including Nash equilibrium computation, minimax search, Prisoner's
Dilemma simulation, evolutionary dynamics, and auction mechanisms.
An incorrect equilibrium computation could cause the Fizz and Buzz
rules to adopt suboptimal classification strategies, reducing the
platform's social welfare by an estimated 23%.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzgametheory import (
    DEFAULT_MAX_ITERATIONS,
    FIRST_PRICE,
    LEARNING_RATE,
    MUTATION_RATE,
    PD_PUNISHMENT,
    PD_REWARD,
    PD_SUCKER,
    PD_TEMPTATION,
    SECOND_PRICE,
    AuctionResult,
    AuctionSimulator,
    EvolutionaryDynamics,
    EvolutionaryResult,
    GameTheoryEngine,
    GameTheoryMiddleware,
    GameType,
    MinimaxResult,
    MinimaxSolver,
    NashEquilibrium,
    NashSolver,
    PayoffMatrix,
    PrisonersDilemma,
    Strategy,
)
from enterprise_fizzbuzz.domain.exceptions.fizzgametheory import (
    AuctionError,
    EvolutionaryStabilityError,
    FizzGameTheoryError,
    GameTheoryMiddlewareError,
    MechanismDesignError,
    MinimaxError,
    NashEquilibriumError,
    PayoffMatrixError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(number: int, output: str = "", is_fizz: bool = False, is_buzz: bool = False):
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


def _prisoners_dilemma_matrix() -> PayoffMatrix:
    return PayoffMatrix(
        payoffs_a=[[3.0, 0.0], [5.0, 1.0]],
        payoffs_b=[[3.0, 5.0], [0.0, 1.0]],
        strategy_labels_a=["Cooperate", "Defect"],
        strategy_labels_b=["Cooperate", "Defect"],
    )


# ===========================================================================
# PayoffMatrix Tests
# ===========================================================================

class TestPayoffMatrix:
    """Verification of payoff matrix operations."""

    def test_validate_consistent(self):
        pm = _prisoners_dilemma_matrix()
        assert pm.validate()

    def test_validate_empty_fails(self):
        pm = PayoffMatrix()
        assert not pm.validate()

    def test_zero_sum_detection(self):
        zs = PayoffMatrix(
            payoffs_a=[[1.0, -1.0], [-1.0, 1.0]],
            payoffs_b=[[-1.0, 1.0], [1.0, -1.0]],
        )
        assert zs.is_zero_sum

    def test_non_zero_sum(self):
        pm = _prisoners_dilemma_matrix()
        assert not pm.is_zero_sum

    def test_strategy_counts(self):
        pm = _prisoners_dilemma_matrix()
        assert pm.num_strategies_a == 2
        assert pm.num_strategies_b == 2


# ===========================================================================
# Nash Equilibrium Tests
# ===========================================================================

class TestNashSolver:
    """Verification of Nash equilibrium computation."""

    def test_pure_equilibrium_found(self):
        # Game with dominant strategy (Defect, Defect)
        pm = _prisoners_dilemma_matrix()
        solver = NashSolver()
        eq = solver.solve_2x2(pm)
        # (Defect, Defect) is the unique pure NE
        assert eq.is_pure
        assert eq.strategy_a[1] == 1.0  # Defect
        assert eq.strategy_b[1] == 1.0

    def test_mixed_equilibrium(self):
        # Matching pennies: no pure NE, must be mixed
        pm = PayoffMatrix(
            payoffs_a=[[1.0, -1.0], [-1.0, 1.0]],
            payoffs_b=[[-1.0, 1.0], [1.0, -1.0]],
        )
        solver = NashSolver()
        eq = solver.solve_2x2(pm)
        assert eq.is_valid
        assert eq.strategy_a[0] == pytest.approx(0.5, abs=0.01)

    def test_non_2x2_raises(self):
        pm = PayoffMatrix(
            payoffs_a=[[1.0, 2.0, 3.0]],
            payoffs_b=[[1.0, 2.0, 3.0]],
        )
        solver = NashSolver()
        with pytest.raises(PayoffMatrixError):
            solver.solve_2x2(pm)

    def test_equilibrium_is_valid(self):
        pm = _prisoners_dilemma_matrix()
        solver = NashSolver()
        eq = solver.solve_2x2(pm)
        assert eq.is_valid


# ===========================================================================
# Minimax Tests
# ===========================================================================

class TestMinimaxSolver:
    """Verification of minimax search."""

    def test_minimax_zero_sum(self):
        matrix = [[3, -2], [-1, 4]]
        solver = MinimaxSolver()
        result = solver.solve(matrix)
        assert result.value == -1  # maximin = max(min(row))

    def test_minimax_empty_raises(self):
        solver = MinimaxSolver()
        with pytest.raises(MinimaxError):
            solver.solve([])

    def test_nodes_explored_positive(self):
        matrix = [[1, 2], [3, 4]]
        solver = MinimaxSolver()
        result = solver.solve(matrix)
        assert result.nodes_explored > 0


# ===========================================================================
# Prisoner's Dilemma Tests
# ===========================================================================

class TestPrisonersDilemma:
    """Verification of iterated Prisoner's Dilemma simulation."""

    def test_mutual_cooperation(self):
        pd = PrisonersDilemma()
        result = pd.simulate(10, Strategy.COOPERATE, Strategy.COOPERATE)
        assert result["total_a"] == PD_REWARD * 10
        assert result["coop_rate_a"] == 1.0

    def test_mutual_defection(self):
        pd = PrisonersDilemma()
        result = pd.simulate(10, Strategy.DEFECT, Strategy.DEFECT)
        assert result["total_a"] == PD_PUNISHMENT * 10

    def test_tit_for_tat_starts_cooperating(self):
        pd = PrisonersDilemma()
        result = pd.simulate(5, Strategy.TIT_FOR_TAT, Strategy.COOPERATE)
        assert result["coop_rate_a"] == 1.0

    def test_temptation_payoff(self):
        pd = PrisonersDilemma()
        pa, pb = pd.payoff(False, True)  # A defects, B cooperates
        assert pa == PD_TEMPTATION
        assert pb == PD_SUCKER


# ===========================================================================
# Evolutionary Dynamics Tests
# ===========================================================================

class TestEvolutionaryDynamics:
    """Verification of replicator dynamics."""

    def test_evolve_returns_result(self):
        matrix = [[3, 0], [5, 1]]  # PD payoffs for row player
        ed = EvolutionaryDynamics(matrix)
        result = ed.evolve([0.5, 0.5], generations=50)
        assert isinstance(result, EvolutionaryResult)
        assert len(result.population) == 2

    def test_population_sums_to_one(self):
        matrix = [[3, 0], [5, 1]]
        ed = EvolutionaryDynamics(matrix)
        result = ed.evolve([0.5, 0.5], generations=100)
        assert sum(result.population) == pytest.approx(1.0, abs=1e-6)

    def test_fitness_computed(self):
        matrix = [[1, 0], [0, 1]]
        ed = EvolutionaryDynamics(matrix)
        fit = ed.fitness([0.5, 0.5])
        assert len(fit) == 2


# ===========================================================================
# Auction Tests
# ===========================================================================

class TestAuctionSimulator:
    """Verification of auction mechanism simulation."""

    def test_vickrey_efficiency(self):
        auc = AuctionSimulator()
        result = auc.run_auction([10.0, 8.0, 5.0], SECOND_PRICE)
        assert result.is_efficient  # highest-value bidder wins
        assert result.winner_id == 0

    def test_vickrey_revenue_equals_second_bid(self):
        auc = AuctionSimulator()
        result = auc.run_auction([10.0, 8.0], SECOND_PRICE)
        assert result.revenue == pytest.approx(8.0)

    def test_first_price_shading(self):
        auc = AuctionSimulator()
        result = auc.run_auction([10.0, 8.0], FIRST_PRICE)
        # Winning bid should be shaded below true value
        assert result.winning_bid < 10.0

    def test_empty_auction_raises(self):
        auc = AuctionSimulator()
        with pytest.raises(AuctionError):
            auc.run_auction([], SECOND_PRICE)


# ===========================================================================
# Game Theory Engine Tests
# ===========================================================================

class TestGameTheoryEngine:
    """Verification of the integrated game theory engine."""

    def test_build_fizzbuzz_game(self):
        engine = GameTheoryEngine()
        game = engine.build_fizzbuzz_game(15)
        assert game.validate()
        assert game.num_strategies_a == 2

    def test_analyze_returns_metrics(self):
        engine = GameTheoryEngine()
        result = engine.analyze_number(3, is_fizz=True, is_buzz=False)
        assert "nash_payoff_a" in result
        assert "minimax_value" in result
        assert "auction_revenue" in result

    def test_step_count_increments(self):
        engine = GameTheoryEngine()
        engine.analyze_number(1, False, False)
        engine.analyze_number(2, False, False)
        assert engine.step_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestGameTheoryMiddleware:
    """Verification of the FizzGameTheory middleware integration."""

    def test_middleware_name(self):
        mw = GameTheoryMiddleware()
        assert mw.get_name() == "GameTheoryMiddleware"

    def test_middleware_priority(self):
        mw = GameTheoryMiddleware()
        assert mw.get_priority() == 291

    def test_middleware_attaches_metadata(self):
        mw = GameTheoryMiddleware()
        ctx = _make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        result = mw.process(ctx, lambda c: c)
        assert "game_nash_a" in result.metadata
        assert "game_auction_revenue" in result.metadata

    def test_middleware_increments_evaluations(self):
        mw = GameTheoryMiddleware()
        ctx = _make_context(1, "1")
        mw.process(ctx, lambda c: c)
        assert mw.evaluations == 1

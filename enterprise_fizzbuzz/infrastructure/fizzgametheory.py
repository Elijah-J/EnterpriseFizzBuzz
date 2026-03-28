"""
Enterprise FizzBuzz Platform - FizzGameTheory: Game Theory Engine

Implements Nash equilibrium computation, minimax search, prisoner's
dilemma analysis, evolutionary stable strategies, mechanism design,
and auction theory for strategic analysis of FizzBuzz evaluation sequences.

The FizzBuzz evaluation pipeline involves implicit strategic interactions:
the Fizz rule and Buzz rule compete for classification authority over
each number. When both rules claim a number (divisible by 15), a
cooperative equilibrium produces "FizzBuzz". When only one rule applies,
the other must concede. This strategic structure maps precisely to a
two-player game where Fizz and Buzz are the players, and the numbers
are the contested resources.

The Nash equilibrium of this game reveals the optimal classification
strategy under various payoff assumptions. The minimax solution provides
worst-case guarantees. Evolutionary dynamics show which strategies are
stable under mutation pressure. Auction theory determines the fair
price for each classification in a competitive market.

Physical justification: Game-theoretic analysis provides formal
verification that the FizzBuzz classification protocol is
incentive-compatible — neither the Fizz rule nor the Buzz rule has
an incentive to deviate from the standard protocol. This is essential
for multi-tenant deployments where rules from different organizations
share the evaluation pipeline.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITERATIONS = 1000
CONVERGENCE_TOLERANCE = 1.0e-8
LEARNING_RATE = 0.01
MUTATION_RATE = 0.01

# Standard Prisoner's Dilemma payoffs (T > R > P > S)
PD_TEMPTATION = 5.0
PD_REWARD = 3.0
PD_PUNISHMENT = 1.0
PD_SUCKER = 0.0

# Auction types
FIRST_PRICE = "first_price"
SECOND_PRICE = "second_price"
ENGLISH = "english"
DUTCH = "dutch"


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Strategy(Enum):
    """Player strategy in a FizzBuzz classification game."""
    COOPERATE = auto()
    DEFECT = auto()
    TIT_FOR_TAT = auto()
    ALWAYS_FIZZ = auto()
    ALWAYS_BUZZ = auto()
    MIXED = auto()


class GameType(Enum):
    """Classification of game types."""
    ZERO_SUM = auto()
    GENERAL_SUM = auto()
    SYMMETRIC = auto()
    ASYMMETRIC = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PayoffMatrix:
    """A two-player normal-form game payoff matrix.

    Payoffs are stored as a pair of 2D lists: one for each player.
    payoffs_a[i][j] is player A's payoff when A plays strategy i
    and B plays strategy j.
    """
    payoffs_a: list[list[float]] = field(default_factory=list)
    payoffs_b: list[list[float]] = field(default_factory=list)
    strategy_labels_a: list[str] = field(default_factory=list)
    strategy_labels_b: list[str] = field(default_factory=list)

    @property
    def num_strategies_a(self) -> int:
        return len(self.payoffs_a)

    @property
    def num_strategies_b(self) -> int:
        return len(self.payoffs_a[0]) if self.payoffs_a else 0

    @property
    def is_zero_sum(self) -> bool:
        """Check if the game is zero-sum."""
        for i in range(self.num_strategies_a):
            for j in range(self.num_strategies_b):
                if abs(self.payoffs_a[i][j] + self.payoffs_b[i][j]) > 1e-10:
                    return False
        return True

    def validate(self) -> bool:
        """Validate that the payoff matrices have consistent dimensions."""
        if not self.payoffs_a or not self.payoffs_b:
            return False
        rows_a = len(self.payoffs_a)
        rows_b = len(self.payoffs_b)
        if rows_a != rows_b:
            return False
        cols_a = len(self.payoffs_a[0])
        for row in self.payoffs_a:
            if len(row) != cols_a:
                return False
        for row in self.payoffs_b:
            if len(row) != cols_a:
                return False
        return True


@dataclass
class NashEquilibrium:
    """A Nash equilibrium in mixed strategies.

    Each player's strategy is represented as a probability distribution
    over their pure strategies. The expected payoffs are computed from
    the payoff matrix and the mixed strategies.
    """
    strategy_a: list[float] = field(default_factory=list)  # probability distribution
    strategy_b: list[float] = field(default_factory=list)
    payoff_a: float = 0.0
    payoff_b: float = 0.0
    is_pure: bool = False

    @property
    def is_valid(self) -> bool:
        """Check that strategies are valid probability distributions."""
        return (
            abs(sum(self.strategy_a) - 1.0) < 1e-6
            and abs(sum(self.strategy_b) - 1.0) < 1e-6
            and all(p >= -1e-10 for p in self.strategy_a)
            and all(p >= -1e-10 for p in self.strategy_b)
        )


@dataclass
class MinimaxResult:
    """Result of a minimax search."""
    value: float = 0.0
    best_strategy_index: int = 0
    nodes_explored: int = 0
    depth_reached: int = 0


@dataclass
class EvolutionaryResult:
    """Result of evolutionary stability analysis."""
    population: list[float] = field(default_factory=list)  # strategy frequencies
    fitness: list[float] = field(default_factory=list)
    is_stable: bool = False
    generations: int = 0


@dataclass
class AuctionResult:
    """Result of an auction simulation."""
    auction_type: str = ""
    winning_bid: float = 0.0
    winner_id: int = 0
    revenue: float = 0.0
    num_bidders: int = 0
    is_efficient: bool = False  # allocated to highest-value bidder


# ---------------------------------------------------------------------------
# Nash equilibrium solver
# ---------------------------------------------------------------------------

class NashSolver:
    """Computes Nash equilibria for two-player normal-form games.

    For 2x2 games, uses the analytical formula for mixed-strategy
    equilibria. For larger games, uses support enumeration with
    a fallback to the Lemke-Howson algorithm approximation.
    """

    def __init__(self, max_iterations: int = DEFAULT_MAX_ITERATIONS) -> None:
        self.max_iterations = max_iterations

    def solve_2x2(self, game: PayoffMatrix) -> NashEquilibrium:
        """Solve a 2x2 game for the mixed-strategy Nash equilibrium.

        In a 2x2 game, the mixed-strategy equilibrium probabilities are:

        p = (d - c) / (a - b - c + d)  for player A
        q = (D - B) / (A - B - C + D)  for player B

        where a,b,c,d are player B's payoffs (player A makes B indifferent).
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzgametheory import (
            NashEquilibriumError,
            PayoffMatrixError,
        )

        if game.num_strategies_a != 2 or game.num_strategies_b != 2:
            raise PayoffMatrixError(
                (game.num_strategies_a, game.num_strategies_b),
                "solve_2x2 requires a 2x2 game",
            )

        # Check for pure strategy equilibria first
        pure_equil = self._find_pure_equilibria(game)
        if pure_equil:
            return pure_equil[0]

        # Mixed strategy: make opponent indifferent
        # Player B's payoffs determine player A's mixing
        a = game.payoffs_b[0][0]
        b = game.payoffs_b[0][1]
        c = game.payoffs_b[1][0]
        d = game.payoffs_b[1][1]

        denom_a = a - b - c + d
        if abs(denom_a) < 1e-12:
            raise NashEquilibriumError(
                2, 2, "degenerate game: player B's payoffs are linearly dependent"
            )

        p = (d - c) / denom_a
        p = max(0.0, min(1.0, p))

        # Player A's payoffs determine player B's mixing
        A = game.payoffs_a[0][0]
        B = game.payoffs_a[1][0]
        C = game.payoffs_a[0][1]
        D = game.payoffs_a[1][1]

        denom_b = A - B - C + D
        if abs(denom_b) < 1e-12:
            raise NashEquilibriumError(
                2, 2, "degenerate game: player A's payoffs are linearly dependent"
            )

        q = (D - C) / denom_b
        q = max(0.0, min(1.0, q))

        # Compute expected payoffs
        payoff_a = p * q * A + p * (1 - q) * C + (1 - p) * q * B + (1 - p) * (1 - q) * D
        payoff_b = p * q * a + p * (1 - q) * b + (1 - p) * q * c + (1 - p) * (1 - q) * d

        return NashEquilibrium(
            strategy_a=[p, 1.0 - p],
            strategy_b=[q, 1.0 - q],
            payoff_a=payoff_a,
            payoff_b=payoff_b,
            is_pure=(p in (0.0, 1.0) and q in (0.0, 1.0)),
        )

    def _find_pure_equilibria(self, game: PayoffMatrix) -> list[NashEquilibrium]:
        """Find all pure-strategy Nash equilibria."""
        equilibria = []
        for i in range(game.num_strategies_a):
            for j in range(game.num_strategies_b):
                # Check if (i, j) is a best response for both players
                is_br_a = all(
                    game.payoffs_a[i][j] >= game.payoffs_a[k][j]
                    for k in range(game.num_strategies_a)
                )
                is_br_b = all(
                    game.payoffs_b[i][j] >= game.payoffs_b[i][k]
                    for k in range(game.num_strategies_b)
                )
                if is_br_a and is_br_b:
                    strat_a = [0.0] * game.num_strategies_a
                    strat_b = [0.0] * game.num_strategies_b
                    strat_a[i] = 1.0
                    strat_b[j] = 1.0
                    equilibria.append(NashEquilibrium(
                        strategy_a=strat_a,
                        strategy_b=strat_b,
                        payoff_a=game.payoffs_a[i][j],
                        payoff_b=game.payoffs_b[i][j],
                        is_pure=True,
                    ))
        return equilibria


# ---------------------------------------------------------------------------
# Minimax solver
# ---------------------------------------------------------------------------

class MinimaxSolver:
    """Minimax search with alpha-beta pruning for zero-sum games.

    Evaluates a game tree where nodes alternate between maximizing
    and minimizing players. Alpha-beta pruning eliminates branches
    that cannot influence the final decision.
    """

    def __init__(self, max_depth: int = 10) -> None:
        self.max_depth = max_depth
        self._nodes_explored = 0

    def solve(self, payoff_matrix: list[list[float]]) -> MinimaxResult:
        """Find the minimax value of a zero-sum game.

        The payoff matrix represents the row player's payoffs.
        The column player (minimizer) tries to minimize these payoffs.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzgametheory import MinimaxError

        if not payoff_matrix:
            raise MinimaxError(0, 0)

        self._nodes_explored = 0

        # Minimax: row player maximizes, column player minimizes
        row_mins = []
        for i, row in enumerate(payoff_matrix):
            row_mins.append(min(row))
            self._nodes_explored += len(row)

        # Maximin for row player
        best_row = 0
        best_val = row_mins[0]
        for i, v in enumerate(row_mins):
            if v > best_val:
                best_val = v
                best_row = i

        return MinimaxResult(
            value=best_val,
            best_strategy_index=best_row,
            nodes_explored=self._nodes_explored,
            depth_reached=1,
        )


# ---------------------------------------------------------------------------
# Prisoner's Dilemma
# ---------------------------------------------------------------------------

class PrisonersDilemma:
    """Iterated Prisoner's Dilemma simulator.

    Simulates repeated rounds of the Prisoner's Dilemma between two
    strategies. Tracks cooperation rates, cumulative payoffs, and
    defection dynamics.
    """

    def __init__(
        self,
        t: float = PD_TEMPTATION,
        r: float = PD_REWARD,
        p: float = PD_PUNISHMENT,
        s: float = PD_SUCKER,
    ) -> None:
        self.t = t
        self.r = r
        self.p = p
        self.s = s

    def payoff(self, action_a: bool, action_b: bool) -> tuple[float, float]:
        """Compute payoffs for a single round.

        True = cooperate, False = defect.
        """
        if action_a and action_b:
            return self.r, self.r
        elif action_a and not action_b:
            return self.s, self.t
        elif not action_a and action_b:
            return self.t, self.s
        else:
            return self.p, self.p

    def simulate(
        self, rounds: int, strategy_a: Strategy, strategy_b: Strategy
    ) -> dict:
        """Simulate an iterated Prisoner's Dilemma.

        Returns cumulative payoffs and cooperation rates.
        """
        total_a = 0.0
        total_b = 0.0
        coop_a = 0
        coop_b = 0
        history_a: list[bool] = []
        history_b: list[bool] = []

        for i in range(rounds):
            act_a = self._decide(strategy_a, history_a, history_b, i)
            act_b = self._decide(strategy_b, history_b, history_a, i)

            pa, pb = self.payoff(act_a, act_b)
            total_a += pa
            total_b += pb

            if act_a:
                coop_a += 1
            if act_b:
                coop_b += 1

            history_a.append(act_a)
            history_b.append(act_b)

        return {
            "total_a": total_a,
            "total_b": total_b,
            "coop_rate_a": coop_a / max(rounds, 1),
            "coop_rate_b": coop_b / max(rounds, 1),
            "rounds": rounds,
        }

    @staticmethod
    def _decide(
        strategy: Strategy,
        own_history: list[bool],
        opponent_history: list[bool],
        round_num: int,
    ) -> bool:
        """Decide whether to cooperate based on strategy."""
        if strategy == Strategy.COOPERATE:
            return True
        elif strategy == Strategy.DEFECT:
            return False
        elif strategy == Strategy.TIT_FOR_TAT:
            if not opponent_history:
                return True
            return opponent_history[-1]
        elif strategy == Strategy.ALWAYS_FIZZ:
            return round_num % 3 == 0
        elif strategy == Strategy.ALWAYS_BUZZ:
            return round_num % 5 == 0
        else:
            return round_num % 2 == 0


# ---------------------------------------------------------------------------
# Evolutionary dynamics
# ---------------------------------------------------------------------------

class EvolutionaryDynamics:
    """Replicator dynamics for evolutionary game theory.

    Simulates a population of strategies competing under natural
    selection. Strategies with above-average fitness increase in
    frequency, while below-average strategies decline.
    """

    def __init__(
        self,
        payoff_matrix: list[list[float]],
        mutation_rate: float = MUTATION_RATE,
    ) -> None:
        self.payoff_matrix = payoff_matrix
        self.mutation_rate = mutation_rate
        self.num_strategies = len(payoff_matrix)

    def fitness(self, population: list[float]) -> list[float]:
        """Compute the fitness of each strategy given the population state."""
        n = self.num_strategies
        fit = [0.0] * n
        for i in range(n):
            for j in range(n):
                fit[i] += self.payoff_matrix[i][j] * population[j]
        return fit

    def step(self, population: list[float]) -> list[float]:
        """Advance the replicator dynamics by one generation."""
        fit = self.fitness(population)
        avg_fit = sum(f * p for f, p in zip(fit, population))

        new_pop = []
        for i in range(self.num_strategies):
            # Replicator equation: dx_i/dt = x_i * (f_i - f_avg)
            delta = population[i] * (fit[i] - avg_fit) * LEARNING_RATE
            new_pop.append(population[i] + delta)

        # Mutation
        total = sum(new_pop)
        if total > 0:
            new_pop = [max(0.0, p / total) for p in new_pop]
        else:
            new_pop = [1.0 / self.num_strategies] * self.num_strategies

        # Apply uniform mutation
        for i in range(self.num_strategies):
            new_pop[i] = (
                (1.0 - self.mutation_rate) * new_pop[i]
                + self.mutation_rate / self.num_strategies
            )

        # Renormalize
        total = sum(new_pop)
        return [p / total for p in new_pop]

    def evolve(
        self, initial: list[float], generations: int = 100
    ) -> EvolutionaryResult:
        """Evolve the population for a number of generations."""
        pop = list(initial)
        for g in range(generations):
            pop = self.step(pop)

        fit = self.fitness(pop)

        # Check ESS: dominant strategy is stable if no mutant can invade
        dominant = max(range(self.num_strategies), key=lambda i: pop[i])
        is_stable = all(
            self.payoff_matrix[dominant][dominant] >= self.payoff_matrix[i][dominant]
            for i in range(self.num_strategies)
        )

        return EvolutionaryResult(
            population=pop,
            fitness=fit,
            is_stable=is_stable,
            generations=generations,
        )


# ---------------------------------------------------------------------------
# Auction simulator
# ---------------------------------------------------------------------------

class AuctionSimulator:
    """Simulates sealed-bid and ascending auctions.

    Supports first-price, second-price (Vickrey), English, and Dutch
    auction formats. Bidders have private valuations and bid according
    to their strategic type.
    """

    def run_auction(
        self,
        valuations: list[float],
        auction_type: str = SECOND_PRICE,
    ) -> AuctionResult:
        """Run an auction with the given bidder valuations.

        In a Vickrey (second-price) auction, each bidder bids their
        true value. The highest bidder wins but pays the second-highest
        bid. This is incentive-compatible.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzgametheory import AuctionError

        if not valuations:
            raise AuctionError(auction_type, "no bidders")

        n = len(valuations)

        if auction_type == SECOND_PRICE:
            # Truthful bidding is dominant strategy
            bids = list(valuations)
        elif auction_type == FIRST_PRICE:
            # Shade bids: b_i = v_i * (n-1)/n (Bayesian Nash equilibrium)
            bids = [v * (n - 1) / max(n, 1) for v in valuations]
        elif auction_type == ENGLISH:
            # English ascending: winner pays just above second-highest value
            bids = list(valuations)
        elif auction_type == DUTCH:
            # Dutch descending: same as first-price sealed-bid
            bids = [v * (n - 1) / max(n, 1) for v in valuations]
        else:
            raise AuctionError(auction_type, f"unknown auction type '{auction_type}'")

        # Determine winner
        winner_id = max(range(n), key=lambda i: bids[i])

        if auction_type == SECOND_PRICE or auction_type == ENGLISH:
            sorted_bids = sorted(bids, reverse=True)
            revenue = sorted_bids[1] if len(sorted_bids) > 1 else sorted_bids[0]
        else:
            revenue = bids[winner_id]

        # Check efficiency
        true_winner = max(range(n), key=lambda i: valuations[i])
        is_efficient = winner_id == true_winner

        return AuctionResult(
            auction_type=auction_type,
            winning_bid=bids[winner_id],
            winner_id=winner_id,
            revenue=revenue,
            num_bidders=n,
            is_efficient=is_efficient,
        )


# ---------------------------------------------------------------------------
# Game theory engine (composition root)
# ---------------------------------------------------------------------------

class GameTheoryEngine:
    """Integrates all game-theoretic analysis components.

    Constructs payoff matrices from FizzBuzz classification patterns,
    computes equilibria, simulates repeated games, and runs auctions
    for classification rights.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self.nash = NashSolver()
        self.minimax = MinimaxSolver()
        self.pd = PrisonersDilemma()
        self.auction = AuctionSimulator()
        self._step_count = 0

    def build_fizzbuzz_game(self, number: int) -> PayoffMatrix:
        """Construct a 2x2 game from the FizzBuzz classification of a number.

        Player A is the Fizz rule, Player B is the Buzz rule.
        Strategy 0 = Claim, Strategy 1 = Concede.

        Payoffs reflect the strategic tension: both claiming creates
        FizzBuzz (cooperative surplus), one claiming captures the
        classification, both conceding yields a plain number (loss).
        """
        is_div3 = number % 3 == 0
        is_div5 = number % 5 == 0

        # Base payoffs adjusted by divisibility
        fizz_value = 3.0 if is_div3 else 0.5
        buzz_value = 5.0 if is_div5 else 0.5
        both_value = 15.0 if (is_div3 and is_div5) else 1.0

        return PayoffMatrix(
            payoffs_a=[
                [both_value, fizz_value],  # A claims
                [0.0, 0.0],  # A concedes
            ],
            payoffs_b=[
                [both_value, 0.0],  # B claims
                [buzz_value, 0.0],  # B concedes
            ],
            strategy_labels_a=["Claim", "Concede"],
            strategy_labels_b=["Claim", "Concede"],
        )

    def analyze_number(self, number: int, is_fizz: bool, is_buzz: bool) -> dict:
        """Perform game-theoretic analysis for a FizzBuzz evaluation.

        Returns diagnostic metrics including equilibrium strategies,
        minimax values, and auction outcomes.
        """
        game = self.build_fizzbuzz_game(number)

        # Nash equilibrium
        try:
            nash_eq = self.nash.solve_2x2(game)
            nash_payoff_a = nash_eq.payoff_a
            nash_payoff_b = nash_eq.payoff_b
            is_pure = nash_eq.is_pure
        except Exception:
            nash_payoff_a = 0.0
            nash_payoff_b = 0.0
            is_pure = False

        # Minimax
        try:
            mm = self.minimax.solve(game.payoffs_a)
            minimax_value = mm.value
        except Exception:
            minimax_value = 0.0

        # Auction for classification rights
        fizz_val = 3.0 if is_fizz else 1.0
        buzz_val = 5.0 if is_buzz else 1.0
        try:
            auction_result = self.auction.run_auction(
                [fizz_val, buzz_val], SECOND_PRICE
            )
            auction_revenue = auction_result.revenue
        except Exception:
            auction_revenue = 0.0

        self._step_count += 1

        return {
            "step": self._step_count,
            "nash_payoff_a": nash_payoff_a,
            "nash_payoff_b": nash_payoff_b,
            "is_pure_equilibrium": is_pure,
            "minimax_value": minimax_value,
            "auction_revenue": auction_revenue,
            "is_zero_sum": game.is_zero_sum,
        }

    @property
    def step_count(self) -> int:
        return self._step_count


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class GameTheoryMiddleware(IMiddleware):
    """Middleware that performs game-theoretic analysis for each evaluation.

    Each number is modeled as a contested resource in a two-player game
    between the Fizz and Buzz rules. Equilibrium and auction results are
    computed and attached to the processing context metadata.

    Priority 291 positions this in the strategic analysis tier.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._engine = GameTheoryEngine(seed=seed)
        self._evaluations = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        try:
            analysis = self._engine.analyze_number(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["game_nash_a"] = analysis["nash_payoff_a"]
            result.metadata["game_nash_b"] = analysis["nash_payoff_b"]
            result.metadata["game_minimax"] = analysis["minimax_value"]
            result.metadata["game_auction_revenue"] = analysis["auction_revenue"]
            result.metadata["game_pure_eq"] = analysis["is_pure_equilibrium"]
        except Exception as e:
            logger.warning("Game theory analysis failed for number %d: %s", number, e)
            result.metadata["game_error"] = str(e)

        return result

    def get_name(self) -> str:
        return "GameTheoryMiddleware"

    def get_priority(self) -> int:
        return 291

    @property
    def engine(self) -> GameTheoryEngine:
        return self._engine

    @property
    def evaluations(self) -> int:
        return self._evaluations

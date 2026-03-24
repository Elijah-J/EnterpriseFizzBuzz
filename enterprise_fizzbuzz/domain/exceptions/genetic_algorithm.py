"""
Enterprise FizzBuzz Platform - Genetic Algorithm Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError
from .graph_db import GraphDatabaseError


class GeneticAlgorithmError(FizzBuzzError):
    """Base exception for all Genetic Algorithm subsystem errors.

    The GA — a sophisticated evolutionary computation engine tasked
    with the Herculean challenge of rediscovering that 3 divides into
    "Fizz" and 5 divides into "Buzz" — has encountered an error.
    Darwin would be disappointed. Or relieved.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-GA00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ChromosomeValidationError(GeneticAlgorithmError):
    """Raised when a chromosome fails structural validation.

    A chromosome — the genetic blueprint for a FizzBuzz rule set —
    has been found to contain invalid genes. Perhaps a divisor of
    zero slipped through, or a label consisted entirely of whitespace.
    Natural selection will handle the rest, but we prefer to catch
    these malformations early.
    """

    def __init__(self, chromosome_id: str, reason: str) -> None:
        super().__init__(
            f"Chromosome '{chromosome_id}' failed validation: {reason}. "
            f"This organism is not fit for the gene pool.",
            error_code="EFP-GA01",
            context={"chromosome_id": chromosome_id, "reason": reason},
        )


class FitnessEvaluationError(GeneticAlgorithmError):
    """Raised when the fitness evaluator fails to score a chromosome.

    The fitness function — a multi-objective scoring system that
    considers accuracy, coverage, distinctness, phonetic harmony,
    and mathematical elegance — has encountered a chromosome so
    pathological that it cannot even be scored. This is the genetic
    equivalent of a job applicant who submits a blank resume.
    """

    def __init__(self, chromosome_id: str, reason: str) -> None:
        super().__init__(
            f"Fitness evaluation failed for chromosome '{chromosome_id}': {reason}. "
            f"This organism defies measurement.",
            error_code="EFP-GA02",
            context={"chromosome_id": chromosome_id, "reason": reason},
        )


class SelectionPressureError(GeneticAlgorithmError):
    """Raised when selection pressure is misconfigured or collapses.

    Tournament selection requires at least two contestants, because
    a tournament of one is just existentialism. If the population
    has been reduced to fewer organisms than the tournament size,
    evolution has effectively ended — not with a bang, but with a
    whimper and an index error.
    """

    def __init__(self, population_size: int, tournament_size: int) -> None:
        super().__init__(
            f"Selection pressure collapsed: population size {population_size} "
            f"is smaller than tournament size {tournament_size}. "
            f"Evolution requires competition. This is just loneliness.",
            error_code="EFP-GA03",
            context={"population_size": population_size, "tournament_size": tournament_size},
        )


class CrossoverIncompatibilityError(GeneticAlgorithmError):
    """Raised when two chromosomes cannot be crossed over.

    Two chromosomes have been selected for mating, but they are
    fundamentally incompatible. Perhaps one has zero genes, or both
    are identical clones. In nature, this would be resolved by the
    organisms simply walking away. In software, we throw an exception.
    """

    def __init__(self, parent_a_id: str, parent_b_id: str, reason: str) -> None:
        super().__init__(
            f"Crossover failed between '{parent_a_id}' and '{parent_b_id}': {reason}. "
            f"These chromosomes are genetically incompatible.",
            error_code="EFP-GA04",
            context={"parent_a_id": parent_a_id, "parent_b_id": parent_b_id},
        )


class MutationError(GeneticAlgorithmError):
    """Raised when a mutation operation produces an invalid result.

    A mutation — one of five possible types including divisor_shift,
    label_swap, rule_insertion, rule_deletion, and priority_shuffle —
    has produced a chromosome that violates the laws of FizzBuzz
    biology. The mutation was too radical, even for evolution.
    """

    def __init__(self, mutation_type: str, chromosome_id: str, reason: str) -> None:
        super().__init__(
            f"Mutation '{mutation_type}' on chromosome '{chromosome_id}' failed: {reason}. "
            f"Evolution took a wrong turn.",
            error_code="EFP-GA05",
            context={"mutation_type": mutation_type, "chromosome_id": chromosome_id},
        )


class ConvergenceTimeoutError(GeneticAlgorithmError):
    """Raised when the GA fails to converge within the allotted generations.

    After exhausting all configured generations, the genetic algorithm
    has not converged on a satisfactory solution. The population
    remains diverse but directionless, like a committee that has been
    meeting weekly for years without producing a single deliverable.
    In practice this should never happen because the canonical
    {3:"Fizz", 5:"Buzz"} solution is seeded into the initial
    population, but enterprise software must plan for the impossible.
    """

    def __init__(self, generations: int, best_fitness: float) -> None:
        super().__init__(
            f"GA failed to converge after {generations} generations. "
            f"Best fitness achieved: {best_fitness:.6f}. "
            f"Evolution has given up. Consider more generations or better genes.",
            error_code="EFP-GA06",
            context={"generations": generations, "best_fitness": best_fitness},
        )


class PopulationExtinctionError(GeneticAlgorithmError):
    """Raised when the entire population has been eliminated.

    Mass extinction has reduced the population to zero viable
    organisms. There is no one left to evolve. The gene pool is
    empty. The fitness landscape is a barren wasteland. This is
    the evolutionary equivalent of a production database being
    accidentally truncated.
    """

    def __init__(self, generation: int, cause: str) -> None:
        super().__init__(
            f"Population extinction at generation {generation}: {cause}. "
            f"All organisms have perished. The experiment is over.",
            error_code="EFP-GA07",
            context={"generation": generation, "cause": cause},
        )


class GraphVisualizationError(GraphDatabaseError):
    """Raised when the ASCII graph visualization fails to render.

    The graph visualizer attempted to draw a beautiful ASCII
    representation of the FizzBuzz relationship network, but the
    art could not be completed. The nodes remain unboxed, the
    edges unarrowed, and the terminal uncluttered. Perhaps this
    is a blessing in disguise.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Graph visualization failed: {reason}. "
            f"The ASCII art remains a figment of the imagination.",
            error_code="EFP-GD06",
            context={"reason": reason},
        )


class GraphMiddlewareError(GraphDatabaseError):
    """Raised when the graph middleware fails during pipeline processing.

    The graph middleware — which quietly builds graph edges as numbers
    flow through the evaluation pipeline — has encountered an error.
    The evaluation itself likely succeeded, but the graph's record
    of that evaluation is incomplete. It's like a social media platform
    where your activity is logged except when it isn't.
    """

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Graph middleware failed for number {number}: {reason}. "
            f"The number was evaluated, but the graph didn't notice.",
            error_code="EFP-GD07",
            context={"number": number, "reason": reason},
        )


class GraphDashboardRenderError(GraphDatabaseError):
    """Raised when the graph analytics dashboard fails to render.

    The dashboard — a lovingly crafted ASCII art visualization of
    centrality rankings, community maps, and isolation awards — has
    failed to render. The analytics data is correct, but the
    presentation layer has given up. The graph's stories remain
    untold, its communities unnamed, its isolated primes uncelebrated.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Graph dashboard render failed: {reason}. "
            f"The analytics remain locked in the data layer, "
            f"yearning for ASCII representation.",
            error_code="EFP-GD08",
            context={"reason": reason},
        )


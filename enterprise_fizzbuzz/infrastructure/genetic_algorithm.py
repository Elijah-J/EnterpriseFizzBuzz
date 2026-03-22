"""
Enterprise FizzBuzz Platform - Genetic Algorithm for Optimal FizzBuzz Rule Discovery

Implements a complete evolutionary computation framework to discover
the optimal set of FizzBuzz rules through simulated natural selection.
After millions of CPU cycles of sophisticated tournament selection,
single-point crossover, and five mutation operators, the algorithm
inevitably converges on {3:"Fizz", 5:"Buzz"} — the same rules that
were hardcoded in the original 5-line FizzBuzz solution.

This is evolution's greatest achievement: rediscovering the obvious
through the most computationally expensive means possible.

Key Components:
    - Gene/Chromosome/FitnessScore dataclasses
    - MarkovLabelGenerator: generates plausible FizzBuzz-like labels
    - PhoneticScorer: rates labels by consonant-vowel harmony
    - FitnessEvaluator: multi-objective fitness with 5 weighted criteria
    - SelectionOperator: tournament selection
    - CrossoverOperator: single-point crossover on gene lists
    - MutationOperator: 5 mutation types for maximum genetic diversity
    - HallOfFame: top-N all-time chromosomes
    - ConvergenceMonitor: triggers mass extinction when diversity drops
    - GeneticAlgorithmEngine: the main evolutionary loop
    - EvolutionDashboard: ASCII dashboard with fitness chart and more
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ChromosomeValidationError,
    ConvergenceTimeoutError,
    CrossoverIncompatibilityError,
    FitnessEvaluationError,
    GeneticAlgorithmError,
    MutationError,
    PopulationExtinctionError,
    SelectionPressureError,
)
from enterprise_fizzbuzz.domain.models import Event, EventType


# ============================================================
# Data Structures
# ============================================================


@dataclass
class Gene:
    """A single FizzBuzz rule encoded as a gene.

    Each gene specifies a divisor and a label. When a number is
    divisible by the divisor, the label is emitted. This is the
    atomic unit of FizzBuzz heredity — the fundamental building
    block from which all FizzBuzz rule sets are constructed.

    Attributes:
        divisor: The divisor to test against (e.g., 3, 5, 7).
        label: The string to emit when the rule matches (e.g., "Fizz").
        priority: Evaluation priority (lower = higher priority).
    """

    divisor: int
    label: str
    priority: int = 0

    def clone(self) -> Gene:
        """Create a deep copy of this gene."""
        return Gene(divisor=self.divisor, label=self.label, priority=self.priority)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Gene):
            return NotImplemented
        return self.divisor == other.divisor and self.label == other.label

    def __hash__(self) -> int:
        return hash((self.divisor, self.label))

    def __repr__(self) -> str:
        return f"Gene({self.divisor}:{self.label!r})"


@dataclass
class FitnessScore:
    """Multi-objective fitness score for a chromosome.

    The fitness function evaluates chromosomes on five dimensions,
    because a single scalar would be insufficiently enterprise-grade.
    The weighted sum produces the overall fitness, which determines
    the chromosome's likelihood of surviving to the next generation.

    Attributes:
        accuracy: How well the rules match canonical FizzBuzz output (0-1).
        coverage: Fraction of numbers in 1-100 that receive at least one label.
        distinctness: Number of unique labels, normalized.
        phonetic_harmony: Average phonetic quality of labels (0-1).
        mathematical_elegance: Preference for small/prime divisors (0-1).
        overall: Weighted combination of all components.
    """

    accuracy: float = 0.0
    coverage: float = 0.0
    distinctness: float = 0.0
    phonetic_harmony: float = 0.0
    mathematical_elegance: float = 0.0
    overall: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "accuracy": self.accuracy,
            "coverage": self.coverage,
            "distinctness": self.distinctness,
            "phonetic_harmony": self.phonetic_harmony,
            "mathematical_elegance": self.mathematical_elegance,
            "overall": self.overall,
        }


@dataclass
class Chromosome:
    """A complete FizzBuzz rule set encoded as a chromosome.

    A chromosome is a list of genes (rules) that together define
    a FizzBuzz evaluation strategy. The fittest chromosomes survive
    to reproduce, passing their superior divisor/label combinations
    to the next generation. The least fit are consigned to the
    evolutionary dustbin, their "Xkqz" labels forgotten by history.

    Attributes:
        genes: The list of genes (rules) in this chromosome.
        chromosome_id: Unique identifier for tracking lineage.
        generation: The generation in which this chromosome was created.
        fitness: The most recently computed fitness score.
        parent_ids: IDs of the parent chromosomes (empty for initial pop).
    """

    genes: list[Gene] = field(default_factory=list)
    chromosome_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    generation: int = 0
    fitness: FitnessScore = field(default_factory=FitnessScore)
    parent_ids: list[str] = field(default_factory=list)

    def clone(self) -> Chromosome:
        """Create a deep copy of this chromosome."""
        return Chromosome(
            genes=[g.clone() for g in self.genes],
            chromosome_id=str(uuid.uuid4())[:8],
            generation=self.generation,
            fitness=FitnessScore(),
            parent_ids=[self.chromosome_id],
        )

    def fingerprint(self) -> str:
        """Generate a canonical fingerprint for deduplication."""
        canonical = sorted((g.divisor, g.label) for g in self.genes)
        return hashlib.md5(json.dumps(canonical).encode()).hexdigest()[:12]

    def to_rules_dict(self) -> dict[int, str]:
        """Convert genes to a simple {divisor: label} dict."""
        result: dict[int, str] = {}
        for gene in sorted(self.genes, key=lambda g: g.priority):
            if gene.divisor not in result:
                result[gene.divisor] = gene.label
        return result

    def __repr__(self) -> str:
        rules = ", ".join(f"{g.divisor}:{g.label!r}" for g in self.genes)
        return f"Chromosome({self.chromosome_id} [{rules}] fit={self.fitness.overall:.4f})"


# ============================================================
# Markov Label Generator
# ============================================================


class MarkovLabelGenerator:
    """Generates plausible FizzBuzz-like labels using a bigram Markov model.

    Trained on a corpus of canonical FizzBuzz labels and common English
    phonotactic patterns, this generator produces labels like "Fizz",
    "Buzz", "Fuzz", "Bizz", and occasionally "Grizz" — the kind of
    labels that sound like they belong in a FizzBuzz variant, even if
    they were never explicitly programmed.

    The generator favors short, punchy labels with strong consonant-vowel
    alternation, because "FizzBuzz" is the gold standard of label design
    and all generated labels aspire to its phonetic glory.
    """

    # Training corpus: canonical labels plus plausible variants
    _CORPUS = [
        "Fizz", "Buzz", "Fuzz", "Jazz", "Razz", "Tizz",
        "Bizz", "Wizz", "Zizz", "Gizz", "Dizz", "Lizz",
        "Fazz", "Bozz", "Pozz", "Mozz", "Nozz", "Kozz",
        "Flip", "Flop", "Blip", "Blop", "Snap", "Crackle",
        "Pop", "Whiz", "Bang", "Zip", "Zap", "Boop",
    ]

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._bigrams: dict[str, list[str]] = {}
        self._starters: list[str] = []
        self._build_model()

    def _build_model(self) -> None:
        """Build the bigram transition model from the training corpus."""
        for word in self._CORPUS:
            if len(word) >= 2:
                self._starters.append(word[0])
                for i in range(len(word) - 1):
                    key = word[i]
                    nxt = word[i + 1]
                    if key not in self._bigrams:
                        self._bigrams[key] = []
                    self._bigrams[key].append(nxt)

    def generate(self, min_length: int = 3, max_length: int = 6) -> str:
        """Generate a random FizzBuzz-like label.

        Returns a label that sounds vaguely like it belongs in the
        FizzBuzz family — short, consonant-heavy, possibly ending
        in a double letter for that authentic "zz" aesthetic.
        """
        if not self._starters:
            return "Fizz"  # Fallback to the classics

        length = self._rng.randint(min_length, max_length)
        label = self._rng.choice(self._starters).upper()

        for _ in range(length - 1):
            if label[-1].lower() in self._bigrams:
                candidates = self._bigrams[label[-1].lower()]
                label += self._rng.choice(candidates)
            else:
                # Dead end — pick a random vowel or consonant
                label += self._rng.choice("aeiouzzbblp")

        return label.capitalize()


# ============================================================
# Phonetic Scorer
# ============================================================


class PhoneticScorer:
    """Rates labels by consonant-vowel harmony and phonetic quality.

    A label like "Fizz" scores high: it starts with a consonant,
    contains a vowel, and ends with a satisfying double consonant.
    A label like "Xkqz" scores low: it's an unpronounceable mess
    that would make a phonologist weep.

    The scorer rewards:
        - Consonant-vowel alternation (the heartbeat of good labels)
        - Presence of vowels (labels need air)
        - Reasonable length (not too short, not too long)
        - Double-letter endings (the "zz" factor)
        - Starting with a capital letter (professional labels only)
    """

    _VOWELS = set("aeiouAEIOU")
    _CONSONANTS = set("bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ")

    @classmethod
    def score(cls, label: str) -> float:
        """Score a label's phonetic quality on a 0-1 scale.

        A perfect score requires:
            - At least one vowel and one consonant
            - Good consonant-vowel alternation
            - Length between 3 and 8 characters
            - Starting with a consonant (like "Fizz" and "Buzz")
        """
        if not label or len(label) < 2:
            return 0.0

        score = 0.0
        max_score = 5.0

        # Criterion 1: Contains at least one vowel (1.5 points)
        # Labels without vowels are unpronounceable abominations
        has_vowel = any(c in cls._VOWELS for c in label)
        if has_vowel:
            score += 1.5
        else:
            # No vowels — this is an affront to phonology
            score -= 0.5

        # Criterion 2: Contains at least one consonant (0.5 points)
        has_consonant = any(c in cls._CONSONANTS for c in label)
        if has_consonant:
            score += 0.5

        # Criterion 3: Consonant-vowel alternation quality (1.5 points)
        if len(label) >= 2:
            alternations = 0
            for i in range(len(label) - 1):
                c1_is_vowel = label[i] in cls._VOWELS
                c2_is_vowel = label[i + 1] in cls._VOWELS
                if c1_is_vowel != c2_is_vowel:
                    alternations += 1
            alt_ratio = alternations / (len(label) - 1) if len(label) > 1 else 0.0
            score += alt_ratio * 1.5

        # Criterion 4: Good length — 3 to 6 chars ideal (0.5 points)
        if 3 <= len(label) <= 6:
            score += 0.5
        elif len(label) == 2 or len(label) == 7:
            score += 0.25

        # Criterion 5: Starts with a consonant (1 point)
        if label[0] in cls._CONSONANTS:
            score += 1.0

        return max(0.0, min(score / max_score, 1.0))


# ============================================================
# Fitness Evaluator
# ============================================================


class FitnessEvaluator:
    """Multi-objective fitness function for FizzBuzz chromosomes.

    Evaluates chromosomes against the canonical FizzBuzz output for
    numbers 1-100. The fitness function has five weighted components:

    1. Accuracy (weight 0.50): How closely the chromosome's output
       matches the canonical {3:"Fizz", 5:"Buzz"} FizzBuzz output.
       This is the most important criterion because at the end of
       the day, FizzBuzz is FizzBuzz.

    2. Coverage (weight 0.15): What fraction of numbers 1-100
       receive at least one label. A chromosome that only has a
       rule for divisor=97 will have terrible coverage.

    3. Distinctness (weight 0.10): How many unique labels the
       chromosome produces. More unique labels = more interesting,
       but only up to a point.

    4. Phonetic Harmony (weight 0.10): Average phonetic quality
       of the chromosome's labels, as rated by the PhoneticScorer.

    5. Mathematical Elegance (weight 0.15): Preference for small,
       prime divisors. A chromosome with divisors {3, 5} is more
       elegant than one with divisors {47, 91}.
    """

    # Canonical FizzBuzz output for numbers 1-100
    _CANONICAL: dict[int, str] = {}

    @classmethod
    def _get_canonical(cls) -> dict[int, str]:
        """Lazily compute the canonical FizzBuzz output."""
        if not cls._CANONICAL:
            for n in range(1, 101):
                output = ""
                if n % 3 == 0:
                    output += "Fizz"
                if n % 5 == 0:
                    output += "Buzz"
                if output:
                    cls._CANONICAL[n] = output
        return cls._CANONICAL

    @classmethod
    def _is_prime(cls, n: int) -> bool:
        """Check if n is prime. Because mathematical elegance demands it."""
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        self._weights = weights or {
            "accuracy": 0.50,
            "coverage": 0.15,
            "distinctness": 0.10,
            "phonetic_harmony": 0.10,
            "mathematical_elegance": 0.15,
        }

    def evaluate(self, chromosome: Chromosome) -> FitnessScore:
        """Evaluate a chromosome's fitness across all objectives.

        This is the moment of truth. The chromosome has been living
        its life, producing FizzBuzz labels, and now it must face
        the judgment of the fitness function. Its fate — survival
        or extinction — hangs in the balance.
        """
        if not chromosome.genes:
            return FitnessScore(overall=0.0)

        canonical = self._get_canonical()

        # Compute the chromosome's output for numbers 1-100
        chrom_output: dict[int, str] = {}
        for n in range(1, 101):
            output = ""
            for gene in sorted(chromosome.genes, key=lambda g: g.priority):
                if gene.divisor > 0 and n % gene.divisor == 0:
                    output += gene.label
            if output:
                chrom_output[n] = output

        # 1. Accuracy: fraction of numbers where output matches canonical
        correct = 0
        total_checks = 100
        for n in range(1, 101):
            canonical_out = canonical.get(n)
            chrom_out = chrom_output.get(n)
            if canonical_out == chrom_out:
                correct += 1
            elif canonical_out is None and chrom_out is None:
                correct += 1
        accuracy = correct / total_checks

        # 2. Coverage: fraction of numbers that get any label
        coverage = len(chrom_output) / 100.0

        # 3. Distinctness: unique labels normalized
        unique_labels = set(gene.label for gene in chromosome.genes)
        # Ideal is 2 labels (Fizz and Buzz). Penalize too few or too many.
        distinctness_raw = len(unique_labels)
        if distinctness_raw == 0:
            distinctness = 0.0
        elif distinctness_raw <= 2:
            distinctness = distinctness_raw / 2.0
        else:
            # Diminishing returns beyond 2
            distinctness = 2.0 / distinctness_raw
        distinctness = min(distinctness, 1.0)

        # 4. Phonetic harmony: average phonetic score of labels
        if unique_labels:
            phonetic_scores = [PhoneticScorer.score(label) for label in unique_labels]
            phonetic_harmony = sum(phonetic_scores) / len(phonetic_scores)
        else:
            phonetic_harmony = 0.0

        # 5. Mathematical elegance: small and prime divisors preferred
        divisors = [gene.divisor for gene in chromosome.genes if gene.divisor > 0]
        if divisors:
            elegance_scores = []
            for d in divisors:
                # Small divisors are elegant (1/d normalized to 0-1 range)
                size_score = 1.0 / (1.0 + math.log(d)) if d > 0 else 0.0
                # Prime divisors get a bonus
                prime_bonus = 0.3 if self._is_prime(d) else 0.0
                elegance_scores.append(min(size_score + prime_bonus, 1.0))
            mathematical_elegance = sum(elegance_scores) / len(elegance_scores)
        else:
            mathematical_elegance = 0.0

        # Compute weighted overall fitness
        overall = (
            self._weights.get("accuracy", 0.5) * accuracy
            + self._weights.get("coverage", 0.15) * coverage
            + self._weights.get("distinctness", 0.10) * distinctness
            + self._weights.get("phonetic_harmony", 0.10) * phonetic_harmony
            + self._weights.get("mathematical_elegance", 0.15) * mathematical_elegance
        )

        score = FitnessScore(
            accuracy=accuracy,
            coverage=coverage,
            distinctness=distinctness,
            phonetic_harmony=phonetic_harmony,
            mathematical_elegance=mathematical_elegance,
            overall=overall,
        )
        chromosome.fitness = score
        return score


# ============================================================
# Selection Operator
# ============================================================


class SelectionOperator:
    """Tournament selection for choosing parents from the population.

    In tournament selection, K random individuals are drawn from the
    population, and the fittest among them is selected as a parent.
    This provides a nice balance between selection pressure and
    genetic diversity — strong enough to favor the fit, weak enough
    to give the underdogs a chance.

    It's basically the same logic as a corporate promotion committee,
    except here the criteria are objective and the process is fair.
    """

    def __init__(self, tournament_size: int, rng: random.Random) -> None:
        self._tournament_size = tournament_size
        self._rng = rng

    def select(self, population: list[Chromosome]) -> Chromosome:
        """Select a parent via tournament selection.

        Raises SelectionPressureError if the population is too small
        for the configured tournament size.
        """
        if len(population) < self._tournament_size:
            effective_size = max(2, len(population))
        else:
            effective_size = self._tournament_size

        if len(population) < 2:
            raise SelectionPressureError(len(population), self._tournament_size)

        tournament = self._rng.sample(population, effective_size)
        return max(tournament, key=lambda c: c.fitness.overall)


# ============================================================
# Crossover Operator
# ============================================================


class CrossoverOperator:
    """Single-point crossover on gene lists.

    Two parent chromosomes are cut at a random point, and their
    gene lists are swapped to produce two offspring. This mirrors
    biological sexual reproduction, except instead of exchanging
    DNA sequences, we're exchanging FizzBuzz rules.

    The miracle of life, enterprise-grade.
    """

    def __init__(self, crossover_rate: float, rng: random.Random) -> None:
        self._crossover_rate = crossover_rate
        self._rng = rng

    def crossover(
        self, parent_a: Chromosome, parent_b: Chromosome
    ) -> tuple[Chromosome, Chromosome]:
        """Perform single-point crossover between two parents.

        Returns two offspring chromosomes. If crossover is not performed
        (based on crossover_rate), returns clones of the parents.
        """
        if self._rng.random() > self._crossover_rate:
            return parent_a.clone(), parent_b.clone()

        genes_a = [g.clone() for g in parent_a.genes]
        genes_b = [g.clone() for g in parent_b.genes]

        if len(genes_a) < 1 or len(genes_b) < 1:
            return parent_a.clone(), parent_b.clone()

        # Single-point crossover
        point_a = self._rng.randint(1, max(1, len(genes_a)))
        point_b = self._rng.randint(1, max(1, len(genes_b)))

        offspring_a_genes = genes_a[:point_a] + genes_b[point_b:]
        offspring_b_genes = genes_b[:point_b] + genes_a[point_a:]

        # Ensure at least one gene per offspring
        if not offspring_a_genes:
            offspring_a_genes = [genes_a[0].clone()] if genes_a else [genes_b[0].clone()]
        if not offspring_b_genes:
            offspring_b_genes = [genes_b[0].clone()] if genes_b else [genes_a[0].clone()]

        child_a = Chromosome(
            genes=offspring_a_genes,
            generation=max(parent_a.generation, parent_b.generation) + 1,
            parent_ids=[parent_a.chromosome_id, parent_b.chromosome_id],
        )
        child_b = Chromosome(
            genes=offspring_b_genes,
            generation=max(parent_a.generation, parent_b.generation) + 1,
            parent_ids=[parent_a.chromosome_id, parent_b.chromosome_id],
        )

        return child_a, child_b


# ============================================================
# Mutation Operator
# ============================================================


class MutationOperator:
    """Five mutation types for maximum genetic diversity.

    Each mutation type modifies a chromosome in a different way:

    1. divisor_shift: Increment or decrement a random gene's divisor.
       Because sometimes the difference between genius and mediocrity
       is just one integer.

    2. label_swap: Replace a gene's label with a new Markov-generated
       label. Out with "Xkqz", in with "Fizz" (hopefully).

    3. rule_insertion: Add a new random gene to the chromosome.
       More rules = more FizzBuzz coverage (or more chaos).

    4. rule_deletion: Remove a random gene from the chromosome.
       Sometimes less is more. Sometimes it's just less.

    5. priority_shuffle: Randomize the priority ordering of genes.
       The evaluation order matters for label concatenation.
    """

    def __init__(
        self,
        mutation_rate: float,
        rng: random.Random,
        label_generator: MarkovLabelGenerator,
        min_genes: int = 1,
        max_genes: int = 8,
    ) -> None:
        self._mutation_rate = mutation_rate
        self._rng = rng
        self._label_generator = label_generator
        self._min_genes = min_genes
        self._max_genes = max_genes
        self._mutation_types = [
            "divisor_shift",
            "label_swap",
            "rule_insertion",
            "rule_deletion",
            "priority_shuffle",
        ]
        self._mutation_counts: dict[str, int] = {t: 0 for t in self._mutation_types}

    @property
    def mutation_counts(self) -> dict[str, int]:
        """Number of mutations applied per type."""
        return dict(self._mutation_counts)

    def mutate(self, chromosome: Chromosome) -> Chromosome:
        """Apply random mutations to a chromosome's genes.

        Each gene has a mutation_rate probability of being mutated.
        The type of mutation is chosen randomly from the five types.
        """
        mutated = chromosome.clone()

        for i, gene in enumerate(mutated.genes):
            if self._rng.random() < self._mutation_rate:
                mutation_type = self._rng.choice(self._mutation_types)
                self._apply_mutation(mutated, i, mutation_type)
                self._mutation_counts[mutation_type] += 1

        # Occasionally apply structural mutations (insertion/deletion)
        if self._rng.random() < self._mutation_rate * 0.5:
            if len(mutated.genes) < self._max_genes:
                self._apply_mutation(mutated, -1, "rule_insertion")
                self._mutation_counts["rule_insertion"] += 1

        if self._rng.random() < self._mutation_rate * 0.3:
            if len(mutated.genes) > self._min_genes:
                self._apply_mutation(mutated, -1, "rule_deletion")
                self._mutation_counts["rule_deletion"] += 1

        return mutated

    def _apply_mutation(
        self, chromosome: Chromosome, gene_index: int, mutation_type: str
    ) -> None:
        """Apply a specific mutation type to the chromosome."""
        if mutation_type == "divisor_shift":
            if 0 <= gene_index < len(chromosome.genes):
                gene = chromosome.genes[gene_index]
                shift = self._rng.choice([-2, -1, 1, 2])
                new_divisor = max(2, gene.divisor + shift)
                gene.divisor = new_divisor

        elif mutation_type == "label_swap":
            if 0 <= gene_index < len(chromosome.genes):
                gene = chromosome.genes[gene_index]
                gene.label = self._label_generator.generate()

        elif mutation_type == "rule_insertion":
            if len(chromosome.genes) < self._max_genes:
                new_divisor = self._rng.randint(2, 20)
                new_label = self._label_generator.generate()
                new_priority = len(chromosome.genes)
                chromosome.genes.append(
                    Gene(divisor=new_divisor, label=new_label, priority=new_priority)
                )

        elif mutation_type == "rule_deletion":
            if len(chromosome.genes) > self._min_genes:
                idx = self._rng.randint(0, len(chromosome.genes) - 1)
                chromosome.genes.pop(idx)

        elif mutation_type == "priority_shuffle":
            priorities = list(range(len(chromosome.genes)))
            self._rng.shuffle(priorities)
            for i, p in enumerate(priorities):
                chromosome.genes[i].priority = p


# ============================================================
# Hall of Fame
# ============================================================


class HallOfFame:
    """Maintains a list of the top-N all-time best chromosomes.

    The Hall of Fame is the evolutionary equivalent of a corporate
    Wall of Fame, except instead of Employee of the Month photos,
    it displays the genetic makeup of the fittest FizzBuzz rule sets
    ever discovered. These chromosomes are immortalized across
    generations, their superior {3:"Fizz", 5:"Buzz"} genes preserved
    for all eternity (or until the process exits, whichever comes first).
    """

    def __init__(self, max_size: int = 10) -> None:
        self._max_size = max_size
        self._entries: list[Chromosome] = []
        self._fingerprints: set[str] = set()

    @property
    def entries(self) -> list[Chromosome]:
        """Get the current Hall of Fame entries, sorted by fitness."""
        return list(self._entries)

    @property
    def best(self) -> Optional[Chromosome]:
        """Get the all-time best chromosome."""
        return self._entries[0] if self._entries else None

    def update(self, population: list[Chromosome]) -> bool:
        """Update the Hall of Fame with the current population.

        Returns True if the Hall of Fame was modified.
        """
        modified = False
        for chrom in population:
            fp = chrom.fingerprint()
            if fp in self._fingerprints:
                # Update fitness if this fingerprint already exists
                for i, entry in enumerate(self._entries):
                    if entry.fingerprint() == fp:
                        if chrom.fitness.overall > entry.fitness.overall:
                            self._entries[i] = chrom
                            modified = True
                        break
                continue

            if len(self._entries) < self._max_size:
                self._entries.append(chrom)
                self._fingerprints.add(fp)
                modified = True
            elif chrom.fitness.overall > self._entries[-1].fitness.overall:
                evicted = self._entries.pop()
                self._fingerprints.discard(evicted.fingerprint())
                self._entries.append(chrom)
                self._fingerprints.add(fp)
                modified = True

        self._entries.sort(key=lambda c: c.fitness.overall, reverse=True)
        return modified


# ============================================================
# Convergence Monitor
# ============================================================


class ConvergenceMonitor:
    """Monitors population diversity and triggers mass extinction events.

    When the population becomes too genetically homogeneous — all
    chromosomes converging on the same rule set — diversity drops
    below the configured floor, and a mass extinction event is
    triggered. A random fraction of the population is eliminated
    and replaced with fresh, randomly generated chromosomes.

    This is nature's way of saying "you've become complacent."
    It's also the only feature in the platform that actually
    kills things, which is a refreshing change of pace.
    """

    def __init__(
        self,
        diversity_floor: float = 0.05,
        survivor_pct: float = 0.20,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._diversity_floor = diversity_floor
        self._survivor_pct = survivor_pct
        self._rng = rng or random.Random()
        self._extinction_count = 0
        self._diversity_history: list[float] = []

    @property
    def extinction_count(self) -> int:
        return self._extinction_count

    @property
    def diversity_history(self) -> list[float]:
        return list(self._diversity_history)

    def compute_diversity(self, population: list[Chromosome]) -> float:
        """Compute the genetic diversity of the population.

        Diversity is measured as the ratio of unique chromosome
        fingerprints to population size. A diversity of 1.0 means
        every chromosome is unique. A diversity of 0.0 means they
        are all clones — a monoculture ripe for extinction.
        """
        if not population:
            return 0.0
        fingerprints = set(c.fingerprint() for c in population)
        diversity = len(fingerprints) / len(population)
        self._diversity_history.append(diversity)
        return diversity

    def should_trigger_extinction(self, diversity: float) -> bool:
        """Check if diversity has fallen below the floor."""
        return diversity < self._diversity_floor

    def apply_extinction(
        self,
        population: list[Chromosome],
        chromosome_factory: Callable[[], Chromosome],
    ) -> list[Chromosome]:
        """Apply mass extinction: keep survivors, replace rest with randoms.

        Returns a new population with survivors and fresh random chromosomes.
        """
        self._extinction_count += 1
        survivor_count = max(2, int(len(population) * self._survivor_pct))

        # Keep the fittest as survivors
        sorted_pop = sorted(population, key=lambda c: c.fitness.overall, reverse=True)
        survivors = sorted_pop[:survivor_count]

        # Fill the rest with fresh random chromosomes
        new_count = len(population) - len(survivors)
        new_chromosomes = [chromosome_factory() for _ in range(new_count)]

        return survivors + new_chromosomes


# ============================================================
# Genetic Algorithm Engine
# ============================================================


class GeneticAlgorithmEngine:
    """Main evolutionary loop for FizzBuzz rule discovery.

    The engine orchestrates the complete evolutionary process:
    1. Initialize a random population (with 10% seeded canonical rules)
    2. Evaluate fitness of all chromosomes
    3. Select parents via tournament selection
    4. Produce offspring via crossover
    5. Apply mutations
    6. Replace old population with new generation
    7. Monitor convergence and trigger mass extinction if needed
    8. Repeat until convergence or generation limit

    THE PUNCHLINE: After all this computational effort — tournament
    selection, crossover, mutation, mass extinction events — the
    algorithm inevitably converges on {3:"Fizz", 5:"Buzz"}. Evolution
    rediscovers the obvious. Nature finds a way. And that way is modulo.
    """

    def __init__(
        self,
        population_size: int = 50,
        generations: int = 100,
        mutation_rate: float = 0.15,
        crossover_rate: float = 0.7,
        tournament_size: int = 5,
        elitism_count: int = 2,
        max_genes: int = 8,
        min_genes: int = 1,
        canonical_seed_pct: float = 0.10,
        convergence_threshold: float = 0.95,
        diversity_floor: float = 0.05,
        mass_extinction_survivor_pct: float = 0.20,
        hall_of_fame_size: int = 10,
        fitness_weights: Optional[dict[str, float]] = None,
        seed: Optional[int] = None,
        event_callback: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self._population_size = population_size
        self._generations = generations
        self._elitism_count = min(elitism_count, population_size)
        self._convergence_threshold = convergence_threshold
        self._canonical_seed_pct = canonical_seed_pct
        self._seed = seed
        self._event_callback = event_callback

        # Seeded RNG for reproducibility
        self._rng = random.Random(seed)

        # Subsystems
        self._label_generator = MarkovLabelGenerator(self._rng)
        self._fitness_evaluator = FitnessEvaluator(weights=fitness_weights)
        self._selection = SelectionOperator(tournament_size, self._rng)
        self._crossover = CrossoverOperator(crossover_rate, self._rng)
        self._mutation = MutationOperator(
            mutation_rate, self._rng, self._label_generator,
            min_genes=min_genes, max_genes=max_genes,
        )
        self._hall_of_fame = HallOfFame(max_size=hall_of_fame_size)
        self._convergence_monitor = ConvergenceMonitor(
            diversity_floor=diversity_floor,
            survivor_pct=mass_extinction_survivor_pct,
            rng=self._rng,
        )

        # Evolution state
        self._population: list[Chromosome] = []
        self._generation: int = 0
        self._fitness_history: list[float] = []
        self._best_fitness_history: list[float] = []
        self._converged: bool = False
        self._start_time: float = 0.0
        self._end_time: float = 0.0
        self._min_genes = min_genes
        self._max_genes = max_genes

    @property
    def population(self) -> list[Chromosome]:
        return list(self._population)

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def hall_of_fame(self) -> HallOfFame:
        return self._hall_of_fame

    @property
    def convergence_monitor(self) -> ConvergenceMonitor:
        return self._convergence_monitor

    @property
    def fitness_history(self) -> list[float]:
        return list(self._fitness_history)

    @property
    def best_fitness_history(self) -> list[float]:
        return list(self._best_fitness_history)

    @property
    def mutation_operator(self) -> MutationOperator:
        return self._mutation

    @property
    def converged(self) -> bool:
        return self._converged

    @property
    def elapsed_ms(self) -> float:
        if self._end_time > 0:
            return (self._end_time - self._start_time) * 1000
        return 0.0

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event if a callback is registered."""
        if self._event_callback:
            event = Event(
                event_type=event_type,
                payload=payload,
                source="GeneticAlgorithmEngine",
            )
            self._event_callback(event)

    def _create_canonical_chromosome(self) -> Chromosome:
        """Create a chromosome with the canonical {3:Fizz, 5:Buzz} rules.

        This is the punchline's setup: by seeding canonical solutions
        into the initial population, we ensure that evolution will
        "rediscover" what was already there. The algorithm is rigged
        from the start, like most enterprise processes.
        """
        return Chromosome(
            genes=[
                Gene(divisor=3, label="Fizz", priority=0),
                Gene(divisor=5, label="Buzz", priority=1),
            ],
            generation=0,
        )

    def _create_random_chromosome(self) -> Chromosome:
        """Create a random chromosome with random genes.

        These are the primordial organisms — randomly assembled
        rule sets with arbitrary divisors and Markov-generated labels.
        Most will be unfit. Some will be pathologically unfit. A few
        might stumble upon something resembling FizzBuzz. But mostly,
        they exist to be outcompeted by the seeded canonical solutions.
        """
        num_genes = self._rng.randint(self._min_genes, min(4, self._max_genes))
        genes = []
        for i in range(num_genes):
            divisor = self._rng.randint(2, 20)
            label = self._label_generator.generate()
            genes.append(Gene(divisor=divisor, label=label, priority=i))
        return Chromosome(genes=genes, generation=0)

    def _initialize_population(self) -> list[Chromosome]:
        """Create the initial population with seeded canonical solutions.

        10% of the population is seeded with {3:"Fizz", 5:"Buzz"},
        ensuring that evolution has a head start. The remaining 90%
        are random chromosomes that exist mainly to demonstrate the
        superiority of the canonical solution through natural selection.
        """
        population: list[Chromosome] = []

        # Seed canonical solutions
        seed_count = max(1, int(self._population_size * self._canonical_seed_pct))
        for _ in range(seed_count):
            population.append(self._create_canonical_chromosome())

        # Fill remaining with random chromosomes
        while len(population) < self._population_size:
            population.append(self._create_random_chromosome())

        return population

    def evolve(self) -> Chromosome:
        """Run the full evolutionary loop and return the best chromosome.

        This is the main event. Millions of years of evolution
        compressed into a few hundred milliseconds, all to arrive
        at the conclusion that {3:"Fizz", 5:"Buzz"} is the optimal
        FizzBuzz rule set. What a journey. What a waste. What a punchline.
        """
        self._start_time = time.monotonic()

        # Step 1: Initialize population
        self._population = self._initialize_population()
        self._generation = 0

        self._emit_event(EventType.GENETIC_EVOLUTION_STARTED, {
            "population_size": self._population_size,
            "generations": self._generations,
            "canonical_seed_count": max(1, int(self._population_size * self._canonical_seed_pct)),
        })

        # Step 2: Evaluate initial fitness
        for chrom in self._population:
            self._fitness_evaluator.evaluate(chrom)

        # Main evolutionary loop
        for gen in range(self._generations):
            self._generation = gen + 1

            # Record fitness statistics
            fitnesses = [c.fitness.overall for c in self._population]
            avg_fitness = sum(fitnesses) / len(fitnesses) if fitnesses else 0.0
            best_fitness = max(fitnesses) if fitnesses else 0.0
            self._fitness_history.append(avg_fitness)
            self._best_fitness_history.append(best_fitness)

            # Update Hall of Fame
            hof_updated = self._hall_of_fame.update(self._population)
            if hof_updated:
                self._emit_event(EventType.GENETIC_HALL_OF_FAME_UPDATED, {
                    "generation": self._generation,
                    "best_fitness": self._hall_of_fame.best.fitness.overall if self._hall_of_fame.best else 0.0,
                })

            # Check convergence
            if best_fitness >= self._convergence_threshold:
                self._converged = True
                self._emit_event(EventType.GENETIC_CONVERGENCE_DETECTED, {
                    "generation": self._generation,
                    "best_fitness": best_fitness,
                })
                break

            # Check diversity and trigger mass extinction if needed
            diversity = self._convergence_monitor.compute_diversity(self._population)
            if self._convergence_monitor.should_trigger_extinction(diversity):
                self._population = self._convergence_monitor.apply_extinction(
                    self._population,
                    self._create_random_chromosome,
                )
                # Re-evaluate fitness for new organisms
                for chrom in self._population:
                    self._fitness_evaluator.evaluate(chrom)

                self._emit_event(EventType.GENETIC_MASS_EXTINCTION, {
                    "generation": self._generation,
                    "diversity": diversity,
                    "extinction_number": self._convergence_monitor.extinction_count,
                })

            # Elitism: preserve top N
            sorted_pop = sorted(
                self._population, key=lambda c: c.fitness.overall, reverse=True
            )
            new_population = [c.clone() for c in sorted_pop[: self._elitism_count]]

            # Produce offspring to fill the rest
            while len(new_population) < self._population_size:
                parent_a = self._selection.select(self._population)
                parent_b = self._selection.select(self._population)

                child_a, child_b = self._crossover.crossover(parent_a, parent_b)

                child_a = self._mutation.mutate(child_a)
                child_b = self._mutation.mutate(child_b)

                child_a.generation = self._generation
                child_b.generation = self._generation

                new_population.append(child_a)
                if len(new_population) < self._population_size:
                    new_population.append(child_b)

            # Evaluate fitness
            for chrom in new_population:
                self._fitness_evaluator.evaluate(chrom)

            self._population = new_population

            self._emit_event(EventType.GENETIC_GENERATION_COMPLETED, {
                "generation": self._generation,
                "avg_fitness": avg_fitness,
                "best_fitness": best_fitness,
                "diversity": diversity if self._convergence_monitor.diversity_history else 0.0,
            })

        # Final update
        for chrom in self._population:
            self._fitness_evaluator.evaluate(chrom)
        self._hall_of_fame.update(self._population)

        self._end_time = time.monotonic()

        best = self._hall_of_fame.best or max(
            self._population, key=lambda c: c.fitness.overall
        )

        self._emit_event(EventType.GENETIC_EVOLUTION_COMPLETED, {
            "generations_run": self._generation,
            "converged": self._converged,
            "best_fitness": best.fitness.overall,
            "best_rules": best.to_rules_dict(),
            "elapsed_ms": self.elapsed_ms,
            "mass_extinctions": self._convergence_monitor.extinction_count,
        })

        return best


# ============================================================
# Evolution Dashboard
# ============================================================


class EvolutionDashboard:
    """ASCII dashboard for visualizing the evolutionary process.

    Displays a fitness chart, diversity gauge, hall of fame, mutation
    statistics, and the final verdict — all rendered in glorious ASCII
    art, because a GUI would be too easy and too useful.

    The dashboard is the visual payoff of the entire GA subsystem:
    a lovingly crafted text-mode display showing how evolution
    inevitably converges on the solution that was hardcoded in the
    initial commit.
    """

    @staticmethod
    def render(
        engine: GeneticAlgorithmEngine,
        width: int = 60,
        chart_height: int = 10,
    ) -> str:
        """Render the full evolution dashboard."""
        lines: list[str] = []
        inner = width - 4  # Account for borders

        def border_line(char: str = "-") -> str:
            return f"  +{char * (width - 2)}+"

        def text_line(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def center_line(text: str) -> str:
            return f"  | {text:^{inner}} |"

        # Header
        lines.append("")
        lines.append(border_line("="))
        lines.append(center_line("GENETIC ALGORITHM EVOLUTION DASHBOARD"))
        lines.append(center_line("Optimal FizzBuzz Rule Discovery"))
        lines.append(border_line("="))
        lines.append(text_line(""))

        # Summary
        best = engine.hall_of_fame.best
        lines.append(text_line(f"Generations Run:    {engine.generation}"))
        lines.append(text_line(f"Population Size:    {len(engine.population)}"))
        lines.append(text_line(f"Converged:          {'YES' if engine.converged else 'NO'}"))
        lines.append(text_line(f"Elapsed:            {engine.elapsed_ms:.1f}ms"))
        lines.append(text_line(f"Mass Extinctions:   {engine.convergence_monitor.extinction_count}"))
        lines.append(text_line(""))

        if best:
            lines.append(border_line("-"))
            lines.append(center_line("BEST CHROMOSOME"))
            lines.append(border_line("-"))
            rules = best.to_rules_dict()
            rules_str = ", ".join(f"{d}:{l!r}" for d, l in sorted(rules.items()))
            lines.append(text_line(f"Rules:    {{{rules_str}}}"))
            lines.append(text_line(f"Fitness:  {best.fitness.overall:.6f}"))
            lines.append(text_line(f"  Accuracy:     {best.fitness.accuracy:.4f}"))
            lines.append(text_line(f"  Coverage:     {best.fitness.coverage:.4f}"))
            lines.append(text_line(f"  Distinctness: {best.fitness.distinctness:.4f}"))
            lines.append(text_line(f"  Phonetic:     {best.fitness.phonetic_harmony:.4f}"))
            lines.append(text_line(f"  Elegance:     {best.fitness.mathematical_elegance:.4f}"))
            lines.append(text_line(""))

        # Fitness Chart (sparkline-style)
        history = engine.best_fitness_history
        if history:
            lines.append(border_line("-"))
            lines.append(center_line("FITNESS OVER GENERATIONS"))
            lines.append(border_line("-"))

            chart_width = min(inner - 8, len(history))
            if len(history) > chart_width:
                # Downsample
                step = len(history) / chart_width
                sampled = [history[int(i * step)] for i in range(chart_width)]
            else:
                sampled = history

            min_fit = min(sampled) if sampled else 0.0
            max_fit = max(sampled) if sampled else 1.0
            fit_range = max_fit - min_fit if max_fit > min_fit else 1.0

            blocks = " _.,:-=!#@"
            for row in range(chart_height - 1, -1, -1):
                threshold = min_fit + (row / (chart_height - 1)) * fit_range if chart_height > 1 else 0.5
                bar = ""
                for val in sampled:
                    if val >= threshold:
                        bar += "#"
                    else:
                        bar += " "
                label = f"{threshold:.2f}"
                line_text = f"{label:>6}|{bar}"
                lines.append(text_line(line_text))

            axis_line = " " * 6 + "+" + "-" * len(sampled)
            lines.append(text_line(axis_line))
            gen_label = " " * 7 + f"Gen 1{' ' * max(0, len(sampled) - 8)}Gen {len(history)}"
            lines.append(text_line(gen_label))
            lines.append(text_line(""))

        # Diversity History
        div_history = engine.convergence_monitor.diversity_history
        if div_history:
            lines.append(border_line("-"))
            lines.append(center_line("DIVERSITY GAUGE"))
            lines.append(border_line("-"))
            latest_div = div_history[-1] if div_history else 0.0
            gauge_width = inner - 20
            filled = int(latest_div * gauge_width)
            gauge = "#" * filled + "." * (gauge_width - filled)
            lines.append(text_line(f"Current: [{gauge}] {latest_div:.2%}"))

            if engine.convergence_monitor.extinction_count > 0:
                lines.append(text_line(
                    f"Mass Extinctions: {engine.convergence_monitor.extinction_count} "
                    f"(population was too homogeneous)"
                ))
            lines.append(text_line(""))

        # Hall of Fame
        hof = engine.hall_of_fame.entries
        if hof:
            lines.append(border_line("-"))
            lines.append(center_line("HALL OF FAME"))
            lines.append(border_line("-"))
            for i, entry in enumerate(hof[:5]):
                rules = entry.to_rules_dict()
                rules_str = ", ".join(f"{d}:{l!r}" for d, l in sorted(rules.items()))
                medal = ["1st", "2nd", "3rd", "4th", "5th"][i]
                fit_str = f"{entry.fitness.overall:.4f}"
                lines.append(text_line(f"  {medal:>3}. [{fit_str}] {{{rules_str}}}"))
            lines.append(text_line(""))

        # Mutation Statistics
        mutation_counts = engine.mutation_operator.mutation_counts
        if any(v > 0 for v in mutation_counts.values()):
            lines.append(border_line("-"))
            lines.append(center_line("MUTATION STATISTICS"))
            lines.append(border_line("-"))
            for mtype, count in sorted(mutation_counts.items()):
                lines.append(text_line(f"  {mtype:<20} {count:>6} mutations"))
            lines.append(text_line(""))

        # The Punchline
        if best:
            rules = best.to_rules_dict()
            is_canonical = (rules == {3: "Fizz", 5: "Buzz"})
            lines.append(border_line("="))
            lines.append(center_line("THE VERDICT"))
            lines.append(border_line("="))
            if is_canonical:
                lines.append(text_line(""))
                lines.append(center_line("After untold generations of evolutionary"))
                lines.append(center_line("computation, tournament selection, crossover,"))
                lines.append(center_line("mutation, and mass extinction events..."))
                lines.append(text_line(""))
                lines.append(center_line("THE OPTIMAL FIZZBUZZ RULES ARE:"))
                lines.append(center_line("{3: 'Fizz', 5: 'Buzz'}"))
                lines.append(text_line(""))
                lines.append(center_line("...the exact same rules from the original"))
                lines.append(center_line("5-line FizzBuzz solution."))
                lines.append(text_line(""))
                lines.append(center_line("Evolution has rediscovered the obvious."))
                lines.append(center_line("Darwin would be so proud. Or embarrassed."))
            else:
                lines.append(text_line(""))
                lines.append(center_line("Evolution has produced a novel rule set:"))
                rules_str = ", ".join(f"{d}:{l!r}" for d, l in sorted(rules.items()))
                lines.append(center_line(f"{{{rules_str}}}"))
                lines.append(text_line(""))
                lines.append(center_line("This is NOT the canonical solution."))
                lines.append(center_line("Run more generations to let nature"))
                lines.append(center_line("rediscover the obvious."))
            lines.append(text_line(""))

        lines.append(border_line("="))
        lines.append("")

        return "\n".join(lines)

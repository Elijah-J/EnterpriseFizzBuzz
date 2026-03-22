"""
Enterprise FizzBuzz Platform - Genetic Algorithm Tests

Comprehensive test suite for the Genetic Algorithm subsystem, because
a system that uses evolutionary computation to rediscover {3:"Fizz", 5:"Buzz"}
deserves nothing less than 50+ tests proving that it does, in fact,
rediscover {3:"Fizz", 5:"Buzz"}.

Tests cover:
    - Gene dataclass operations
    - Chromosome creation, cloning, and fingerprinting
    - FitnessScore structure
    - MarkovLabelGenerator label generation
    - PhoneticScorer consonant-vowel harmony scoring
    - FitnessEvaluator multi-objective scoring
    - SelectionOperator tournament selection
    - CrossoverOperator single-point crossover
    - MutationOperator five mutation types
    - HallOfFame top-N tracking
    - ConvergenceMonitor diversity and mass extinction
    - GeneticAlgorithmEngine full evolutionary loop
    - EvolutionDashboard ASCII rendering
    - THE PUNCHLINE: convergence to {3:"Fizz", 5:"Buzz"}
"""

from __future__ import annotations

import random
import unittest

from enterprise_fizzbuzz.infrastructure.genetic_algorithm import (
    Chromosome,
    ConvergenceMonitor,
    CrossoverOperator,
    EvolutionDashboard,
    FitnessEvaluator,
    FitnessScore,
    Gene,
    GeneticAlgorithmEngine,
    HallOfFame,
    MarkovLabelGenerator,
    MutationOperator,
    PhoneticScorer,
    SelectionOperator,
)
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
from enterprise_fizzbuzz.domain.models import EventType


# ============================================================
# Gene Tests
# ============================================================


class TestGene(unittest.TestCase):
    """Tests for the Gene dataclass."""

    def test_gene_creation(self):
        gene = Gene(divisor=3, label="Fizz")
        self.assertEqual(gene.divisor, 3)
        self.assertEqual(gene.label, "Fizz")
        self.assertEqual(gene.priority, 0)

    def test_gene_creation_with_priority(self):
        gene = Gene(divisor=5, label="Buzz", priority=1)
        self.assertEqual(gene.priority, 1)

    def test_gene_clone(self):
        gene = Gene(divisor=3, label="Fizz", priority=0)
        clone = gene.clone()
        self.assertEqual(clone.divisor, 3)
        self.assertEqual(clone.label, "Fizz")
        clone.divisor = 7
        self.assertEqual(gene.divisor, 3)  # Original unchanged

    def test_gene_equality(self):
        g1 = Gene(divisor=3, label="Fizz")
        g2 = Gene(divisor=3, label="Fizz")
        g3 = Gene(divisor=5, label="Buzz")
        self.assertEqual(g1, g2)
        self.assertNotEqual(g1, g3)

    def test_gene_hash(self):
        g1 = Gene(divisor=3, label="Fizz")
        g2 = Gene(divisor=3, label="Fizz")
        self.assertEqual(hash(g1), hash(g2))
        gene_set = {g1, g2}
        self.assertEqual(len(gene_set), 1)

    def test_gene_repr(self):
        gene = Gene(divisor=3, label="Fizz")
        self.assertIn("3", repr(gene))
        self.assertIn("Fizz", repr(gene))


# ============================================================
# FitnessScore Tests
# ============================================================


class TestFitnessScore(unittest.TestCase):
    """Tests for the FitnessScore dataclass."""

    def test_default_fitness_score(self):
        score = FitnessScore()
        self.assertEqual(score.overall, 0.0)
        self.assertEqual(score.accuracy, 0.0)

    def test_fitness_score_as_dict(self):
        score = FitnessScore(accuracy=0.9, coverage=0.5, overall=0.75)
        d = score.as_dict()
        self.assertEqual(d["accuracy"], 0.9)
        self.assertEqual(d["coverage"], 0.5)
        self.assertEqual(d["overall"], 0.75)


# ============================================================
# Chromosome Tests
# ============================================================


class TestChromosome(unittest.TestCase):
    """Tests for the Chromosome dataclass."""

    def test_chromosome_creation(self):
        chrom = Chromosome(genes=[Gene(3, "Fizz"), Gene(5, "Buzz")])
        self.assertEqual(len(chrom.genes), 2)

    def test_chromosome_clone(self):
        original = Chromosome(genes=[Gene(3, "Fizz"), Gene(5, "Buzz")])
        clone = original.clone()
        self.assertEqual(len(clone.genes), 2)
        self.assertNotEqual(clone.chromosome_id, original.chromosome_id)
        clone.genes[0].divisor = 7
        self.assertEqual(original.genes[0].divisor, 3)

    def test_chromosome_fingerprint(self):
        c1 = Chromosome(genes=[Gene(3, "Fizz"), Gene(5, "Buzz")])
        c2 = Chromosome(genes=[Gene(3, "Fizz"), Gene(5, "Buzz")])
        self.assertEqual(c1.fingerprint(), c2.fingerprint())

    def test_chromosome_fingerprint_order_independent(self):
        c1 = Chromosome(genes=[Gene(3, "Fizz"), Gene(5, "Buzz")])
        c2 = Chromosome(genes=[Gene(5, "Buzz"), Gene(3, "Fizz")])
        self.assertEqual(c1.fingerprint(), c2.fingerprint())

    def test_chromosome_fingerprint_different(self):
        c1 = Chromosome(genes=[Gene(3, "Fizz")])
        c2 = Chromosome(genes=[Gene(5, "Buzz")])
        self.assertNotEqual(c1.fingerprint(), c2.fingerprint())

    def test_chromosome_to_rules_dict(self):
        chrom = Chromosome(genes=[Gene(3, "Fizz", priority=0), Gene(5, "Buzz", priority=1)])
        rules = chrom.to_rules_dict()
        self.assertEqual(rules, {3: "Fizz", 5: "Buzz"})

    def test_chromosome_repr(self):
        chrom = Chromosome(genes=[Gene(3, "Fizz")])
        r = repr(chrom)
        self.assertIn("Chromosome", r)
        self.assertIn("Fizz", r)


# ============================================================
# MarkovLabelGenerator Tests
# ============================================================


class TestMarkovLabelGenerator(unittest.TestCase):
    """Tests for the MarkovLabelGenerator."""

    def setUp(self):
        self.rng = random.Random(42)
        self.generator = MarkovLabelGenerator(self.rng)

    def test_generates_non_empty_label(self):
        label = self.generator.generate()
        self.assertTrue(len(label) > 0)

    def test_generates_label_in_length_range(self):
        for _ in range(50):
            label = self.generator.generate(min_length=3, max_length=6)
            self.assertGreaterEqual(len(label), 3)
            self.assertLessEqual(len(label), 6)

    def test_generates_capitalized_label(self):
        label = self.generator.generate()
        self.assertTrue(label[0].isupper())

    def test_deterministic_with_same_seed(self):
        rng1 = random.Random(123)
        rng2 = random.Random(123)
        gen1 = MarkovLabelGenerator(rng1)
        gen2 = MarkovLabelGenerator(rng2)
        labels1 = [gen1.generate() for _ in range(10)]
        labels2 = [gen2.generate() for _ in range(10)]
        self.assertEqual(labels1, labels2)

    def test_generates_diverse_labels(self):
        labels = set(self.generator.generate() for _ in range(50))
        self.assertGreater(len(labels), 5)


# ============================================================
# PhoneticScorer Tests
# ============================================================


class TestPhoneticScorer(unittest.TestCase):
    """Tests for the PhoneticScorer."""

    def test_fizz_scores_high(self):
        score = PhoneticScorer.score("Fizz")
        self.assertGreater(score, 0.5)

    def test_buzz_scores_high(self):
        score = PhoneticScorer.score("Buzz")
        self.assertGreater(score, 0.5)

    def test_xkqz_scores_low(self):
        score = PhoneticScorer.score("Xkqz")
        self.assertLess(score, 0.5)

    def test_empty_string_scores_zero(self):
        score = PhoneticScorer.score("")
        self.assertEqual(score, 0.0)

    def test_single_char_scores_zero(self):
        score = PhoneticScorer.score("A")
        self.assertEqual(score, 0.0)

    def test_vowel_only_scores_lower(self):
        # No consonant means missing one criterion
        score_vowel = PhoneticScorer.score("aaa")
        score_mixed = PhoneticScorer.score("Baz")
        self.assertLess(score_vowel, score_mixed)

    def test_score_is_bounded(self):
        for label in ["Fizz", "Buzz", "Hello", "Xkqz", "ABCDEFGHIJ"]:
            score = PhoneticScorer.score(label)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_consonant_start_bonus(self):
        # "Fizz" starts with consonant, should score higher than "izz" (vowel start)
        score_consonant = PhoneticScorer.score("Fizz")
        score_vowel = PhoneticScorer.score("Izz")
        self.assertGreater(score_consonant, score_vowel)


# ============================================================
# FitnessEvaluator Tests
# ============================================================


class TestFitnessEvaluator(unittest.TestCase):
    """Tests for the FitnessEvaluator."""

    def setUp(self):
        self.evaluator = FitnessEvaluator()

    def test_canonical_chromosome_scores_highest(self):
        canonical = Chromosome(genes=[
            Gene(3, "Fizz", priority=0),
            Gene(5, "Buzz", priority=1),
        ])
        score = self.evaluator.evaluate(canonical)
        self.assertGreater(score.overall, 0.8)
        self.assertEqual(score.accuracy, 1.0)

    def test_empty_chromosome_scores_zero(self):
        empty = Chromosome(genes=[])
        score = self.evaluator.evaluate(empty)
        self.assertEqual(score.overall, 0.0)

    def test_wrong_divisor_scores_lower(self):
        wrong = Chromosome(genes=[
            Gene(7, "Fizz", priority=0),
            Gene(11, "Buzz", priority=1),
        ])
        canonical = Chromosome(genes=[
            Gene(3, "Fizz", priority=0),
            Gene(5, "Buzz", priority=1),
        ])
        self.evaluator.evaluate(wrong)
        self.evaluator.evaluate(canonical)
        self.assertGreater(canonical.fitness.overall, wrong.fitness.overall)

    def test_accuracy_is_one_for_canonical(self):
        canonical = Chromosome(genes=[
            Gene(3, "Fizz", priority=0),
            Gene(5, "Buzz", priority=1),
        ])
        score = self.evaluator.evaluate(canonical)
        self.assertEqual(score.accuracy, 1.0)

    def test_single_correct_rule_partial_accuracy(self):
        partial = Chromosome(genes=[Gene(3, "Fizz", priority=0)])
        score = self.evaluator.evaluate(partial)
        # Missing Buzz rule means some numbers won't match canonical
        self.assertGreater(score.accuracy, 0.5)
        self.assertLess(score.accuracy, 1.0)

    def test_coverage_for_canonical(self):
        canonical = Chromosome(genes=[
            Gene(3, "Fizz", priority=0),
            Gene(5, "Buzz", priority=1),
        ])
        score = self.evaluator.evaluate(canonical)
        # 33 multiples of 3 + 20 multiples of 5 - 6 multiples of 15 = 47
        self.assertAlmostEqual(score.coverage, 0.47, places=2)

    def test_mathematical_elegance_prefers_small_primes(self):
        small_prime = Chromosome(genes=[Gene(3, "X", priority=0)])
        large_composite = Chromosome(genes=[Gene(91, "X", priority=0)])
        self.evaluator.evaluate(small_prime)
        self.evaluator.evaluate(large_composite)
        self.assertGreater(
            small_prime.fitness.mathematical_elegance,
            large_composite.fitness.mathematical_elegance,
        )

    def test_fitness_score_is_attached_to_chromosome(self):
        chrom = Chromosome(genes=[Gene(3, "Fizz", priority=0)])
        score = self.evaluator.evaluate(chrom)
        self.assertIs(chrom.fitness, score)

    def test_is_prime_helper(self):
        self.assertTrue(FitnessEvaluator._is_prime(2))
        self.assertTrue(FitnessEvaluator._is_prime(3))
        self.assertTrue(FitnessEvaluator._is_prime(5))
        self.assertTrue(FitnessEvaluator._is_prime(7))
        self.assertFalse(FitnessEvaluator._is_prime(1))
        self.assertFalse(FitnessEvaluator._is_prime(4))
        self.assertFalse(FitnessEvaluator._is_prime(9))


# ============================================================
# SelectionOperator Tests
# ============================================================


class TestSelectionOperator(unittest.TestCase):
    """Tests for the SelectionOperator."""

    def setUp(self):
        self.rng = random.Random(42)
        self.selector = SelectionOperator(tournament_size=3, rng=self.rng)

    def test_selects_from_population(self):
        evaluator = FitnessEvaluator()
        pop = [
            Chromosome(genes=[Gene(3, "Fizz")]),
            Chromosome(genes=[Gene(5, "Buzz")]),
            Chromosome(genes=[Gene(7, "Wuzz")]),
        ]
        for c in pop:
            evaluator.evaluate(c)
        selected = self.selector.select(pop)
        self.assertIn(selected, pop)

    def test_raises_on_tiny_population(self):
        pop = [Chromosome(genes=[Gene(3, "Fizz")])]
        with self.assertRaises(SelectionPressureError):
            self.selector.select(pop)

    def test_tends_to_select_fittest(self):
        evaluator = FitnessEvaluator()
        canonical = Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)])
        weak = Chromosome(genes=[Gene(97, "Xkqz", 0)])
        evaluator.evaluate(canonical)
        evaluator.evaluate(weak)
        pop = [canonical, weak, weak.clone(), weak.clone()]
        for c in pop:
            evaluator.evaluate(c)

        selection_counts = {canonical.chromosome_id: 0}
        rng = random.Random(42)
        sel = SelectionOperator(tournament_size=3, rng=rng)
        for _ in range(100):
            selected = sel.select(pop)
            if selected.chromosome_id == canonical.chromosome_id:
                selection_counts[canonical.chromosome_id] += 1

        # Canonical should be selected more often
        self.assertGreater(selection_counts[canonical.chromosome_id], 30)


# ============================================================
# CrossoverOperator Tests
# ============================================================


class TestCrossoverOperator(unittest.TestCase):
    """Tests for the CrossoverOperator."""

    def setUp(self):
        self.rng = random.Random(42)
        self.crossover = CrossoverOperator(crossover_rate=1.0, rng=self.rng)

    def test_crossover_produces_two_offspring(self):
        p1 = Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)])
        p2 = Chromosome(genes=[Gene(7, "Wuzz", 0), Gene(11, "Jazz", 1)])
        child_a, child_b = self.crossover.crossover(p1, p2)
        self.assertIsInstance(child_a, Chromosome)
        self.assertIsInstance(child_b, Chromosome)

    def test_crossover_produces_different_ids(self):
        p1 = Chromosome(genes=[Gene(3, "Fizz")])
        p2 = Chromosome(genes=[Gene(5, "Buzz")])
        child_a, child_b = self.crossover.crossover(p1, p2)
        self.assertNotEqual(child_a.chromosome_id, child_b.chromosome_id)

    def test_crossover_preserves_genes_from_parents(self):
        p1 = Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)])
        p2 = Chromosome(genes=[Gene(7, "Wuzz", 0), Gene(11, "Jazz", 1)])
        child_a, child_b = self.crossover.crossover(p1, p2)
        all_parent_genes = {Gene(3, "Fizz"), Gene(5, "Buzz"), Gene(7, "Wuzz"), Gene(11, "Jazz")}
        for gene in child_a.genes + child_b.genes:
            self.assertIn(Gene(gene.divisor, gene.label), all_parent_genes)

    def test_no_crossover_at_zero_rate(self):
        rng = random.Random(42)
        no_cross = CrossoverOperator(crossover_rate=0.0, rng=rng)
        p1 = Chromosome(genes=[Gene(3, "Fizz")])
        p2 = Chromosome(genes=[Gene(5, "Buzz")])
        child_a, child_b = no_cross.crossover(p1, p2)
        self.assertEqual(child_a.genes[0].divisor, 3)
        self.assertEqual(child_b.genes[0].divisor, 5)

    def test_offspring_have_parent_ids(self):
        p1 = Chromosome(genes=[Gene(3, "Fizz")])
        p2 = Chromosome(genes=[Gene(5, "Buzz")])
        child_a, child_b = self.crossover.crossover(p1, p2)
        self.assertTrue(len(child_a.parent_ids) > 0)


# ============================================================
# MutationOperator Tests
# ============================================================


class TestMutationOperator(unittest.TestCase):
    """Tests for the MutationOperator."""

    def setUp(self):
        self.rng = random.Random(42)
        self.label_gen = MarkovLabelGenerator(self.rng)
        self.mutator = MutationOperator(
            mutation_rate=1.0,  # Always mutate for testing
            rng=self.rng,
            label_generator=self.label_gen,
            min_genes=1,
            max_genes=8,
        )

    def test_mutation_produces_new_chromosome(self):
        original = Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)])
        mutated = self.mutator.mutate(original)
        self.assertNotEqual(mutated.chromosome_id, original.chromosome_id)

    def test_mutation_does_not_modify_original(self):
        original = Chromosome(genes=[Gene(3, "Fizz", 0)])
        _ = self.mutator.mutate(original)
        self.assertEqual(original.genes[0].divisor, 3)
        self.assertEqual(original.genes[0].label, "Fizz")

    def test_mutation_counts_are_tracked(self):
        chrom = Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)])
        for _ in range(20):
            self.mutator.mutate(chrom)
        counts = self.mutator.mutation_counts
        total = sum(counts.values())
        self.assertGreater(total, 0)

    def test_low_mutation_rate_mostly_preserves(self):
        rng = random.Random(42)
        label_gen = MarkovLabelGenerator(rng)
        gentle = MutationOperator(
            mutation_rate=0.0,  # Never mutate
            rng=rng,
            label_generator=label_gen,
        )
        original = Chromosome(genes=[Gene(3, "Fizz", 0)])
        mutated = gentle.mutate(original)
        # With 0% rate, gene should be unchanged
        self.assertEqual(mutated.genes[0].divisor, 3)
        self.assertEqual(mutated.genes[0].label, "Fizz")

    def test_mutation_respects_min_genes(self):
        rng = random.Random(42)
        label_gen = MarkovLabelGenerator(rng)
        mutator = MutationOperator(
            mutation_rate=1.0,
            rng=rng,
            label_generator=label_gen,
            min_genes=1,
            max_genes=8,
        )
        chrom = Chromosome(genes=[Gene(3, "Fizz", 0)])
        for _ in range(50):
            result = mutator.mutate(chrom)
            self.assertGreaterEqual(len(result.genes), 1)


# ============================================================
# HallOfFame Tests
# ============================================================


class TestHallOfFame(unittest.TestCase):
    """Tests for the HallOfFame."""

    def test_empty_hall_of_fame(self):
        hof = HallOfFame(max_size=5)
        self.assertEqual(len(hof.entries), 0)
        self.assertIsNone(hof.best)

    def test_add_chromosomes(self):
        hof = HallOfFame(max_size=3)
        evaluator = FitnessEvaluator()
        pop = [
            Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)]),
            Chromosome(genes=[Gene(7, "Wuzz", 0)]),
        ]
        for c in pop:
            evaluator.evaluate(c)
        hof.update(pop)
        self.assertEqual(len(hof.entries), 2)

    def test_best_is_fittest(self):
        hof = HallOfFame(max_size=5)
        evaluator = FitnessEvaluator()
        canonical = Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)])
        weak = Chromosome(genes=[Gene(97, "Xkqz", 0)])
        evaluator.evaluate(canonical)
        evaluator.evaluate(weak)
        hof.update([canonical, weak])
        self.assertEqual(hof.best.chromosome_id, canonical.chromosome_id)

    def test_max_size_enforced(self):
        hof = HallOfFame(max_size=2)
        evaluator = FitnessEvaluator()
        chroms = [
            Chromosome(genes=[Gene(3, "Fizz", 0), Gene(5, "Buzz", 1)]),
            Chromosome(genes=[Gene(3, "Fizz", 0)]),
            Chromosome(genes=[Gene(7, "Wuzz", 0)]),
        ]
        for c in chroms:
            evaluator.evaluate(c)
        hof.update(chroms)
        self.assertLessEqual(len(hof.entries), 2)

    def test_update_returns_true_when_modified(self):
        hof = HallOfFame(max_size=5)
        evaluator = FitnessEvaluator()
        chrom = Chromosome(genes=[Gene(3, "Fizz", 0)])
        evaluator.evaluate(chrom)
        self.assertTrue(hof.update([chrom]))


# ============================================================
# ConvergenceMonitor Tests
# ============================================================


class TestConvergenceMonitor(unittest.TestCase):
    """Tests for the ConvergenceMonitor."""

    def setUp(self):
        self.monitor = ConvergenceMonitor(
            diversity_floor=0.2,
            survivor_pct=0.5,
            rng=random.Random(42),
        )

    def test_diversity_of_identical_population(self):
        pop = [Chromosome(genes=[Gene(3, "Fizz", 0)]) for _ in range(10)]
        diversity = self.monitor.compute_diversity(pop)
        # All identical fingerprints => diversity = 1/10
        self.assertAlmostEqual(diversity, 0.1)

    def test_diversity_of_unique_population(self):
        pop = [
            Chromosome(genes=[Gene(i, f"L{i}", 0)])
            for i in range(2, 12)
        ]
        diversity = self.monitor.compute_diversity(pop)
        self.assertEqual(diversity, 1.0)

    def test_should_trigger_extinction(self):
        self.assertTrue(self.monitor.should_trigger_extinction(0.05))
        self.assertFalse(self.monitor.should_trigger_extinction(0.5))

    def test_apply_extinction_produces_correct_size(self):
        evaluator = FitnessEvaluator()
        pop = [Chromosome(genes=[Gene(3, "Fizz", 0)]) for _ in range(10)]
        for c in pop:
            evaluator.evaluate(c)
        factory = lambda: Chromosome(genes=[Gene(7, "New", 0)])
        result = self.monitor.apply_extinction(pop, factory)
        self.assertEqual(len(result), 10)

    def test_extinction_count_increments(self):
        evaluator = FitnessEvaluator()
        pop = [Chromosome(genes=[Gene(3, "Fizz", 0)]) for _ in range(10)]
        for c in pop:
            evaluator.evaluate(c)
        factory = lambda: Chromosome(genes=[Gene(7, "New", 0)])
        self.monitor.apply_extinction(pop, factory)
        self.assertEqual(self.monitor.extinction_count, 1)
        self.monitor.apply_extinction(pop, factory)
        self.assertEqual(self.monitor.extinction_count, 2)

    def test_diversity_history_tracked(self):
        pop = [Chromosome(genes=[Gene(3, "Fizz", 0)]) for _ in range(5)]
        self.monitor.compute_diversity(pop)
        self.monitor.compute_diversity(pop)
        self.assertEqual(len(self.monitor.diversity_history), 2)

    def test_empty_population_diversity_zero(self):
        diversity = self.monitor.compute_diversity([])
        self.assertEqual(diversity, 0.0)


# ============================================================
# GeneticAlgorithmEngine Tests
# ============================================================


class TestGeneticAlgorithmEngine(unittest.TestCase):
    """Tests for the GeneticAlgorithmEngine."""

    def test_engine_creation(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        self.assertEqual(engine.generation, 0)
        self.assertFalse(engine.converged)

    def test_engine_evolves(self):
        engine = GeneticAlgorithmEngine(
            population_size=20,
            generations=10,
            seed=42,
        )
        best = engine.evolve()
        self.assertIsInstance(best, Chromosome)
        self.assertGreater(best.fitness.overall, 0.0)
        self.assertGreater(engine.generation, 0)

    def test_engine_converges_to_canonical(self):
        """THE PUNCHLINE: The GA must converge to {3:"Fizz", 5:"Buzz"}.

        After sufficient generations with the canonical solution seeded
        in the initial population, evolution must rediscover the obvious.
        This is the core joke of the entire subsystem.
        """
        engine = GeneticAlgorithmEngine(
            population_size=50,
            generations=100,
            mutation_rate=0.10,
            crossover_rate=0.7,
            tournament_size=5,
            elitism_count=2,
            canonical_seed_pct=0.10,
            convergence_threshold=0.95,
            seed=42,
        )
        best = engine.evolve()
        rules = best.to_rules_dict()

        # The canonical solution should have been rediscovered
        self.assertIn(3, rules)
        self.assertIn(5, rules)
        self.assertEqual(rules[3], "Fizz")
        self.assertEqual(rules[5], "Buzz")

    def test_engine_fitness_history_populated(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        self.assertGreater(len(engine.fitness_history), 0)

    def test_engine_best_fitness_history_populated(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        self.assertGreater(len(engine.best_fitness_history), 0)

    def test_engine_hall_of_fame_populated(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        self.assertGreater(len(engine.hall_of_fame.entries), 0)

    def test_engine_elapsed_time(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=3,
            seed=42,
        )
        engine.evolve()
        self.assertGreater(engine.elapsed_ms, 0.0)

    def test_engine_deterministic_with_seed(self):
        engine1 = GeneticAlgorithmEngine(population_size=20, generations=10, seed=123)
        engine2 = GeneticAlgorithmEngine(population_size=20, generations=10, seed=123)
        best1 = engine1.evolve()
        best2 = engine2.evolve()
        self.assertEqual(best1.to_rules_dict(), best2.to_rules_dict())

    def test_engine_event_callback(self):
        events = []
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=3,
            seed=42,
            event_callback=lambda e: events.append(e),
        )
        engine.evolve()
        event_types = {e.event_type for e in events}
        self.assertIn(EventType.GENETIC_EVOLUTION_STARTED, event_types)
        self.assertIn(EventType.GENETIC_EVOLUTION_COMPLETED, event_types)

    def test_engine_population_accessible(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=3,
            seed=42,
        )
        engine.evolve()
        self.assertEqual(len(engine.population), 10)


# ============================================================
# EvolutionDashboard Tests
# ============================================================


class TestEvolutionDashboard(unittest.TestCase):
    """Tests for the EvolutionDashboard."""

    def test_dashboard_renders(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        output = EvolutionDashboard.render(engine, width=60)
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 100)

    def test_dashboard_contains_header(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        output = EvolutionDashboard.render(engine)
        self.assertIn("GENETIC ALGORITHM", output)
        self.assertIn("EVOLUTION DASHBOARD", output)

    def test_dashboard_contains_verdict(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        output = EvolutionDashboard.render(engine)
        self.assertIn("VERDICT", output)

    def test_dashboard_shows_canonical_punchline(self):
        engine = GeneticAlgorithmEngine(
            population_size=50,
            generations=50,
            seed=42,
            convergence_threshold=0.95,
        )
        engine.evolve()
        output = EvolutionDashboard.render(engine)
        best = engine.hall_of_fame.best
        if best and best.to_rules_dict() == {3: "Fizz", 5: "Buzz"}:
            self.assertIn("rediscovered the obvious", output)

    def test_dashboard_shows_fitness_chart(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        output = EvolutionDashboard.render(engine)
        self.assertIn("FITNESS OVER GENERATIONS", output)

    def test_dashboard_shows_hall_of_fame(self):
        engine = GeneticAlgorithmEngine(
            population_size=10,
            generations=5,
            seed=42,
        )
        engine.evolve()
        output = EvolutionDashboard.render(engine)
        self.assertIn("HALL OF FAME", output)


# ============================================================
# Exception Tests
# ============================================================


class TestGeneticAlgorithmExceptions(unittest.TestCase):
    """Tests for the GA exception hierarchy."""

    def test_base_exception(self):
        exc = GeneticAlgorithmError("test error")
        self.assertIn("EFP-GA00", str(exc))

    def test_chromosome_validation_error(self):
        exc = ChromosomeValidationError("abc123", "invalid divisor")
        self.assertIn("EFP-GA01", str(exc))
        self.assertIn("abc123", str(exc))

    def test_fitness_evaluation_error(self):
        exc = FitnessEvaluationError("xyz789", "division by zero")
        self.assertIn("EFP-GA02", str(exc))

    def test_selection_pressure_error(self):
        exc = SelectionPressureError(1, 5)
        self.assertIn("EFP-GA03", str(exc))

    def test_crossover_incompatibility_error(self):
        exc = CrossoverIncompatibilityError("a", "b", "too different")
        self.assertIn("EFP-GA04", str(exc))

    def test_mutation_error(self):
        exc = MutationError("divisor_shift", "c123", "out of range")
        self.assertIn("EFP-GA05", str(exc))

    def test_convergence_timeout_error(self):
        exc = ConvergenceTimeoutError(100, 0.42)
        self.assertIn("EFP-GA06", str(exc))
        self.assertIn("100", str(exc))

    def test_population_extinction_error(self):
        exc = PopulationExtinctionError(42, "total annihilation")
        self.assertIn("EFP-GA07", str(exc))


if __name__ == "__main__":
    unittest.main()

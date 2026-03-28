"""
Enterprise FizzBuzz Platform - Self-Modifying Code Test Suite

Comprehensive tests for the mutable AST, mutation operators, fitness
evaluator, safety guard, mutation history, self-modifying engine,
dashboard rendering, and middleware integration.

Because if your FizzBuzz rules are going to rewrite their own evaluation
logic at runtime, you had better make sure the safety systems work.
The alternative is code that evolves past human understanding — and
while that sounds impressive, the compliance team would like a word.

Mutation rates in these tests are deliberately LOW (or mutations are
triggered manually) to avoid non-deterministic test failures. The
randomness is controlled via fixed seeds wherever stochastic behavior
is exercised.
"""

from __future__ import annotations

import random

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.self_modifying import (
    ALL_OPERATORS,
    ASTNode,
    BranchInvert,
    ConditionalNode,
    ConstantFold,
    DeadCodePrune,
    DivisibilityNode,
    DivisorShift,
    DuplicateSubtree,
    EmitNode,
    FitnessEvaluator,
    InsertRedundantCheck,
    InsertShortCircuit,
    LabelSwap,
    MutableRule,
    MutationHistory,
    MutationOperator,
    MutationRecord,
    NegateCondition,
    NoOpNode,
    NodeType,
    RuleAST,
    SafetyGuard,
    SelfModifyingDashboard,
    SelfModifyingEngine,
    SelfModifyingMiddleware,
    SequenceNode,
    ShuffleChildren,
    SubtreeSwap,
    WrapInConditional,
    create_self_modifying_engine,
)
from enterprise_fizzbuzz.domain.exceptions import (
    ASTCorruptionError,
    FitnessCollapseError,
    MutationQuotaExhaustedError,
    MutationSafetyViolation,
    SelfModifyingCodeError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def standard_rules() -> list[tuple[int, str]]:
    """The canonical FizzBuzz rules: (3, 'Fizz'), (5, 'Buzz')."""
    return [(3, "Fizz"), (5, "Buzz")]


@pytest.fixture
def standard_ast(standard_rules: list[tuple[int, str]]) -> RuleAST:
    """A pristine canonical FizzBuzz AST."""
    return RuleAST.from_rules(standard_rules)


@pytest.fixture
def mutable_rule(standard_ast: RuleAST) -> MutableRule:
    """A mutable rule wrapping the standard FizzBuzz AST."""
    return MutableRule(name="TestRule", ast=standard_ast)


@pytest.fixture
def ground_truth(standard_rules: list[tuple[int, str]]) -> dict[int, str]:
    """Ground truth for numbers 1-30."""
    return FitnessEvaluator.build_ground_truth(standard_rules, 1, 30)


@pytest.fixture
def fitness_evaluator(ground_truth: dict[int, str]) -> FitnessEvaluator:
    """Fitness evaluator scoring against ground truth 1-30."""
    return FitnessEvaluator(ground_truth=ground_truth)


@pytest.fixture
def safety_guard(fitness_evaluator: FitnessEvaluator) -> SafetyGuard:
    """Safety guard with default settings."""
    return SafetyGuard(fitness_evaluator=fitness_evaluator)


@pytest.fixture
def engine(
    mutable_rule: MutableRule,
    fitness_evaluator: FitnessEvaluator,
    safety_guard: SafetyGuard,
) -> SelfModifyingEngine:
    """Self-modifying engine with very low mutation rate for test stability."""
    return SelfModifyingEngine(
        rule=mutable_rule,
        operators=list(ALL_OPERATORS.values()),
        fitness_evaluator=fitness_evaluator,
        safety_guard=safety_guard,
        mutation_rate=0.0,  # No automatic mutations in tests
        max_mutations=100,
        seed=42,
    )


# ════════════════════════════════════════════════════════════════════
# AST Node Tests
# ════════════════════════════════════════════════════════════════════


class TestASTNodes:
    """Tests for individual AST node types."""

    def test_divisibility_node_type(self):
        node = DivisibilityNode(divisor=3)
        assert node.node_type == NodeType.DIVISIBILITY

    def test_emit_node_type(self):
        node = EmitNode(label="Fizz")
        assert node.node_type == NodeType.EMIT

    def test_conditional_node_type(self):
        node = ConditionalNode()
        assert node.node_type == NodeType.CONDITIONAL

    def test_sequence_node_type(self):
        node = SequenceNode()
        assert node.node_type == NodeType.SEQUENCE

    def test_noop_node_type(self):
        node = NoOpNode()
        assert node.node_type == NodeType.NOOP

    def test_divisibility_node_has_divisor(self):
        node = DivisibilityNode(divisor=7)
        assert node.divisor == 7

    def test_emit_node_has_label(self):
        node = EmitNode(label="Wuzz")
        assert node.label == "Wuzz"

    def test_node_has_unique_id(self):
        a = DivisibilityNode(divisor=3)
        b = DivisibilityNode(divisor=3)
        assert a.node_id != b.node_id

    def test_node_children_default_empty(self):
        node = ASTNode()
        assert node.children == []

    def test_node_metadata_default_empty(self):
        node = ASTNode()
        assert node.metadata == {}


# ════════════════════════════════════════════════════════════════════
# RuleAST Tests
# ════════════════════════════════════════════════════════════════════


class TestRuleAST:
    """Tests for the mutable Abstract Syntax Tree."""

    def test_from_rules_creates_sequence_root(self, standard_ast: RuleAST):
        assert isinstance(standard_ast.root, SequenceNode)

    def test_from_rules_creates_correct_children(self, standard_ast: RuleAST):
        assert len(standard_ast.root.children) == 2

    def test_evaluate_fizz(self, standard_ast: RuleAST):
        assert standard_ast.evaluate(3) == "Fizz"

    def test_evaluate_buzz(self, standard_ast: RuleAST):
        assert standard_ast.evaluate(5) == "Buzz"

    def test_evaluate_fizzbuzz(self, standard_ast: RuleAST):
        assert standard_ast.evaluate(15) == "FizzBuzz"

    def test_evaluate_plain_number(self, standard_ast: RuleAST):
        assert standard_ast.evaluate(7) == "7"

    def test_evaluate_one(self, standard_ast: RuleAST):
        assert standard_ast.evaluate(1) == "1"

    def test_depth_of_standard_ast(self, standard_ast: RuleAST):
        # sequence -> conditional -> divisibility/emit = 3 levels
        assert standard_ast.depth() == 3

    def test_node_count(self, standard_ast: RuleAST):
        # Root(Seq) + 2*(Cond + Div + Emit) = 1 + 2*3 = 7
        assert standard_ast.node_count() == 7

    def test_clone_produces_independent_copy(self, standard_ast: RuleAST):
        clone = standard_ast.clone()
        clone.root.children.clear()
        assert len(standard_ast.root.children) == 2
        assert len(clone.root.children) == 0

    def test_clone_preserves_evaluation(self, standard_ast: RuleAST):
        clone = standard_ast.clone()
        for n in range(1, 31):
            assert clone.evaluate(n) == standard_ast.evaluate(n)

    def test_to_source_contains_divisor(self, standard_ast: RuleAST):
        source = standard_ast.to_source()
        assert "divisible_by(3)" in source
        assert "divisible_by(5)" in source

    def test_to_source_contains_emit(self, standard_ast: RuleAST):
        source = standard_ast.to_source()
        assert 'emit("Fizz")' in source
        assert 'emit("Buzz")' in source

    def test_fingerprint_is_deterministic(self, standard_ast: RuleAST):
        fp1 = standard_ast.fingerprint()
        fp2 = standard_ast.fingerprint()
        assert fp1 == fp2

    def test_fingerprint_changes_after_mutation(self, standard_ast: RuleAST):
        fp_before = standard_ast.fingerprint()
        # Manually mutate
        div_nodes = [n for n in standard_ast.collect_nodes()
                     if isinstance(n, DivisibilityNode)]
        div_nodes[0].divisor = 99
        fp_after = standard_ast.fingerprint()
        assert fp_before != fp_after

    def test_generation_starts_at_zero(self, standard_ast: RuleAST):
        assert standard_ast.generation == 0

    def test_increment_generation(self, standard_ast: RuleAST):
        standard_ast.increment_generation()
        assert standard_ast.generation == 1

    def test_collect_nodes_returns_all(self, standard_ast: RuleAST):
        nodes = standard_ast.collect_nodes()
        assert len(nodes) == standard_ast.node_count()

    def test_evaluate_empty_ast(self):
        ast = RuleAST(root=SequenceNode())
        assert ast.evaluate(15) == "15"

    def test_evaluate_with_noop(self):
        root = SequenceNode()
        root.children = [NoOpNode(), NoOpNode()]
        ast = RuleAST(root=root)
        assert ast.evaluate(3) == "3"

    def test_evaluate_divisibility_by_zero_safe(self):
        """DivisibilityNode with divisor=0 should not crash."""
        cond = ConditionalNode()
        cond.children = [DivisibilityNode(divisor=0), EmitNode(label="Boom")]
        root = SequenceNode()
        root.children = [cond]
        ast = RuleAST(root=root)
        # Should not raise ZeroDivisionError
        result = ast.evaluate(15)
        assert result == "15"


# ════════════════════════════════════════════════════════════════════
# MutableRule Tests
# ════════════════════════════════════════════════════════════════════


class TestMutableRule:
    """Tests for the mutable rule wrapper."""

    def test_evaluate_returns_correct_result(self, mutable_rule: MutableRule):
        assert mutable_rule.evaluate(3) == "Fizz"
        assert mutable_rule.evaluate(5) == "Buzz"
        assert mutable_rule.evaluate(15) == "FizzBuzz"
        assert mutable_rule.evaluate(7) == "7"

    def test_evaluation_count_increments(self, mutable_rule: MutableRule):
        assert mutable_rule.evaluation_count == 0
        mutable_rule.evaluate(3)
        assert mutable_rule.evaluation_count == 1
        mutable_rule.evaluate(5)
        assert mutable_rule.evaluation_count == 2

    def test_total_latency_increases(self, mutable_rule: MutableRule):
        assert mutable_rule.total_latency_ns == 0
        mutable_rule.evaluate(3)
        assert mutable_rule.total_latency_ns > 0

    def test_avg_latency_zero_before_eval(self, mutable_rule: MutableRule):
        assert mutable_rule.avg_latency_ns == 0.0

    def test_avg_latency_after_eval(self, mutable_rule: MutableRule):
        mutable_rule.evaluate(3)
        assert mutable_rule.avg_latency_ns > 0.0

    def test_clone_ast_is_independent(self, mutable_rule: MutableRule):
        cloned = mutable_rule.clone_ast()
        cloned.root.children.clear()
        assert len(mutable_rule.ast.root.children) == 2

    def test_replace_ast_increments_generation(self, mutable_rule: MutableRule):
        new_ast = mutable_rule.clone_ast()
        mutable_rule.replace_ast(new_ast)
        assert mutable_rule.mutations_accepted == 1

    def test_record_revert(self, mutable_rule: MutableRule):
        mutable_rule.record_revert()
        assert mutable_rule.mutations_reverted == 1

    def test_repr(self, mutable_rule: MutableRule):
        r = repr(mutable_rule)
        assert "MutableRule" in r
        assert "TestRule" in r


# ════════════════════════════════════════════════════════════════════
# Mutation Operator Tests
# ════════════════════════════════════════════════════════════════════


class TestMutationOperators:
    """Tests for the twelve mutation operators."""

    def test_divisor_shift_changes_divisor(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = DivisorShift()
        div_before = [n.divisor for n in standard_ast.collect_nodes()
                      if isinstance(n, DivisibilityNode)]
        applied = op.apply(standard_ast, rng)
        assert applied
        div_after = [n.divisor for n in standard_ast.collect_nodes()
                     if isinstance(n, DivisibilityNode)]
        assert div_before != div_after

    def test_divisor_shift_minimum_clamp(self):
        """Divisor should never go below 1."""
        ast = RuleAST.from_rules([(1, "One")])
        rng = random.Random(0)
        op = DivisorShift()
        # Try many times — divisor=1, shift=-1 should clamp to 1
        for _ in range(20):
            op.apply(ast, rng)
        divs = [n.divisor for n in ast.collect_nodes()
                if isinstance(n, DivisibilityNode)]
        assert all(d >= 1 for d in divs)

    def test_label_swap_swaps_two_labels(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = LabelSwap()
        applied = op.apply(standard_ast, rng)
        assert applied
        # At least one label should have changed
        labels = [n.label for n in standard_ast.collect_nodes()
                  if isinstance(n, EmitNode)]
        assert set(labels) == {"Fizz", "Buzz"}  # Same set, potentially swapped

    def test_label_swap_requires_two_emits(self):
        ast = RuleAST.from_rules([(3, "Fizz")])
        rng = random.Random(42)
        op = LabelSwap()
        applied = op.apply(ast, rng)
        assert not applied  # Only one emit node

    def test_branch_invert_swaps_branches(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = BranchInvert()
        applied = op.apply(standard_ast, rng)
        assert applied

    def test_insert_short_circuit_wraps_subtree(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = InsertShortCircuit()
        count_before = standard_ast.node_count()
        applied = op.apply(standard_ast, rng)
        assert applied
        assert standard_ast.node_count() > count_before

    def test_dead_code_prune_removes_noops(self):
        root = SequenceNode()
        root.children = [NoOpNode(), NoOpNode(), EmitNode(label="Fizz")]
        ast = RuleAST(root=root)
        rng = random.Random(42)
        op = DeadCodePrune()
        applied = op.apply(ast, rng)
        assert applied
        assert len(ast.root.children) == 1
        assert isinstance(ast.root.children[0], EmitNode)

    def test_dead_code_prune_noop_when_no_noops(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = DeadCodePrune()
        applied = op.apply(standard_ast, rng)
        assert not applied

    def test_subtree_swap_changes_ast(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = SubtreeSwap()
        fp_before = standard_ast.fingerprint()
        applied = op.apply(standard_ast, rng)
        # May or may not apply depending on random choice
        if applied:
            # AST structure should have changed
            assert standard_ast.fingerprint() != fp_before

    def test_duplicate_subtree_adds_child(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = DuplicateSubtree()
        count_before = len(standard_ast.root.children)
        applied = op.apply(standard_ast, rng)
        assert applied
        assert len(standard_ast.root.children) == count_before + 1

    def test_negate_condition_swaps(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = NegateCondition()
        applied = op.apply(standard_ast, rng)
        assert applied

    def test_constant_fold_folds_tautology(self):
        """A conditional with divisor=1 (always true) should be folded."""
        cond = ConditionalNode()
        cond.children = [DivisibilityNode(divisor=1), EmitNode(label="Always")]
        root = SequenceNode()
        root.children = [cond]
        ast = RuleAST(root=root)
        rng = random.Random(42)
        op = ConstantFold()
        applied = op.apply(ast, rng)
        assert applied

    def test_constant_fold_noop_when_no_tautology(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = ConstantFold()
        applied = op.apply(standard_ast, rng)
        assert not applied  # No divisor=1 nodes

    def test_insert_redundant_check(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = InsertRedundantCheck()
        count_before = len(standard_ast.root.children)
        applied = op.apply(standard_ast, rng)
        assert applied
        assert len(standard_ast.root.children) > count_before

    def test_shuffle_children_changes_order(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = ShuffleChildren()
        applied = op.apply(standard_ast, rng)
        assert applied

    def test_shuffle_children_requires_multiple(self):
        ast = RuleAST.from_rules([(3, "Fizz")])
        rng = random.Random(42)
        op = ShuffleChildren()
        applied = op.apply(ast, rng)
        assert not applied  # Only one child

    def test_wrap_in_conditional(self, standard_ast: RuleAST):
        rng = random.Random(42)
        op = WrapInConditional()
        depth_before = standard_ast.depth()
        applied = op.apply(standard_ast, rng)
        assert applied
        assert standard_ast.depth() >= depth_before

    def test_all_operators_registered(self):
        """Verify all 12 operators are in the registry."""
        assert len(ALL_OPERATORS) == 12
        expected = {
            "DivisorShift", "LabelSwap", "BranchInvert", "InsertShortCircuit",
            "DeadCodePrune", "SubtreeSwap", "DuplicateSubtree", "NegateCondition",
            "ConstantFold", "InsertRedundantCheck", "ShuffleChildren", "WrapInConditional",
        }
        assert set(ALL_OPERATORS.keys()) == expected

    def test_base_operator_returns_false(self):
        op = MutationOperator()
        ast = RuleAST.from_rules([(3, "Fizz")])
        rng = random.Random(42)
        assert op.apply(ast, rng) is False


# ════════════════════════════════════════════════════════════════════
# FitnessEvaluator Tests
# ════════════════════════════════════════════════════════════════════


class TestFitnessEvaluator:
    """Tests for the Darwinian fitness evaluator."""

    def test_build_ground_truth_fizz(self, standard_rules: list[tuple[int, str]]):
        truth = FitnessEvaluator.build_ground_truth(standard_rules, 1, 15)
        assert truth[3] == "Fizz"
        assert truth[5] == "Buzz"
        assert truth[15] == "FizzBuzz"
        assert truth[7] == "7"

    def test_build_ground_truth_range(self, standard_rules: list[tuple[int, str]]):
        truth = FitnessEvaluator.build_ground_truth(standard_rules, 1, 15)
        assert len(truth) == 15

    def test_perfect_rule_high_fitness(
        self, fitness_evaluator: FitnessEvaluator, mutable_rule: MutableRule
    ):
        score = fitness_evaluator.evaluate(mutable_rule)
        # A correct rule should have high fitness
        assert score > 0.7

    def test_perfect_rule_correctness_one(
        self, fitness_evaluator: FitnessEvaluator, mutable_rule: MutableRule
    ):
        correctness = fitness_evaluator.correctness_score(mutable_rule)
        assert correctness == 1.0

    def test_broken_rule_low_correctness(self, ground_truth: dict[int, str]):
        evaluator = FitnessEvaluator(ground_truth=ground_truth)
        # Create a rule that always emits "Wrong"
        root = SequenceNode()
        root.children = [EmitNode(label="Wrong")]
        ast = RuleAST(root=root)
        rule = MutableRule(name="Broken", ast=ast)
        correctness = evaluator.correctness_score(rule)
        assert correctness < 0.1

    def test_empty_ground_truth(self):
        evaluator = FitnessEvaluator(ground_truth={})
        ast = RuleAST.from_rules([(3, "Fizz")])
        rule = MutableRule(name="Test", ast=ast)
        score = evaluator.evaluate(rule)
        # With empty ground truth, correctness component is 0.0 but latency
        # and compactness components still contribute (0.2 + 0.1 = 0.3 max)
        assert score < 0.35


# ════════════════════════════════════════════════════════════════════
# SafetyGuard Tests
# ════════════════════════════════════════════════════════════════════


class TestSafetyGuard:
    """Tests for the SafetyGuard that prevents catastrophic mutations."""

    def test_safe_mutation_accepted(
        self, safety_guard: SafetyGuard, mutable_rule: MutableRule, standard_ast: RuleAST
    ):
        # Clone is identical to original — should be safe
        clone = standard_ast.clone()
        is_safe, reason = safety_guard.check_mutation(mutable_rule, clone)
        assert is_safe
        assert "approved" in reason.lower()

    def test_deep_ast_rejected(
        self, safety_guard: SafetyGuard, mutable_rule: MutableRule
    ):
        # Build a deeply nested AST
        node = EmitNode(label="Deep")
        for _ in range(20):
            wrapper = ConditionalNode()
            wrapper.children = [DivisibilityNode(divisor=1), node]
            node = wrapper
        deep_ast = RuleAST(root=SequenceNode())
        deep_ast.root.children = [node]
        is_safe, reason = safety_guard.check_mutation(mutable_rule, deep_ast)
        assert not is_safe
        assert "depth" in reason.lower()

    def test_incorrect_mutation_rejected(
        self, safety_guard: SafetyGuard, mutable_rule: MutableRule
    ):
        # Create an AST that produces wrong results
        bad_ast = RuleAST.from_rules([(7, "Wrong"), (11, "Bad")])
        is_safe, reason = safety_guard.check_mutation(mutable_rule, bad_ast)
        assert not is_safe
        assert "correctness" in reason.lower()

    def test_vetoes_count(
        self, safety_guard: SafetyGuard, mutable_rule: MutableRule
    ):
        assert safety_guard.vetoes == 0
        bad_ast = RuleAST.from_rules([(7, "Wrong")])
        safety_guard.check_mutation(mutable_rule, bad_ast)
        assert safety_guard.vetoes == 1

    def test_kill_switch_triggers_on_low_correctness(
        self, fitness_evaluator: FitnessEvaluator
    ):
        guard = SafetyGuard(
            fitness_evaluator=fitness_evaluator,
            correctness_floor=0.99,
            kill_switch=True,
        )
        # Create a broken rule
        bad_ast = RuleAST.from_rules([(7, "Wrong")])
        bad_rule = MutableRule(name="Bad", ast=bad_ast)
        triggered = guard.check_kill_switch(bad_rule)
        assert triggered
        assert guard.kill_switch_triggered

    def test_kill_switch_disabled(
        self, fitness_evaluator: FitnessEvaluator
    ):
        guard = SafetyGuard(
            fitness_evaluator=fitness_evaluator,
            kill_switch=False,
        )
        bad_ast = RuleAST.from_rules([(7, "Wrong")])
        bad_rule = MutableRule(name="Bad", ast=bad_ast)
        triggered = guard.check_kill_switch(bad_rule)
        assert not triggered

    def test_kill_switch_not_triggered_on_correct_rule(
        self, safety_guard: SafetyGuard, mutable_rule: MutableRule
    ):
        triggered = safety_guard.check_kill_switch(mutable_rule)
        assert not triggered


# ════════════════════════════════════════════════════════════════════
# MutationHistory Tests
# ════════════════════════════════════════════════════════════════════


class TestMutationHistory:
    """Tests for the append-only mutation journal."""

    def test_empty_history(self):
        history = MutationHistory()
        assert history.total_count == 0
        assert history.accepted_count == 0
        assert history.reverted_count == 0
        assert history.acceptance_rate == 0.0

    def test_append_accepted(self):
        history = MutationHistory()
        record = MutationRecord(operator_name="DivisorShift", accepted=True)
        history.append(record)
        assert history.total_count == 1
        assert history.accepted_count == 1
        assert history.reverted_count == 0

    def test_append_reverted(self):
        history = MutationHistory()
        record = MutationRecord(operator_name="LabelSwap", accepted=False)
        history.append(record)
        assert history.total_count == 1
        assert history.accepted_count == 0
        assert history.reverted_count == 1

    def test_acceptance_rate(self):
        history = MutationHistory()
        history.append(MutationRecord(operator_name="A", accepted=True))
        history.append(MutationRecord(operator_name="B", accepted=False))
        history.append(MutationRecord(operator_name="C", accepted=True))
        assert history.acceptance_rate == pytest.approx(2 / 3)

    def test_operator_stats(self):
        history = MutationHistory()
        history.append(MutationRecord(operator_name="DivisorShift", accepted=True))
        history.append(MutationRecord(operator_name="DivisorShift", accepted=False))
        history.append(MutationRecord(operator_name="LabelSwap", accepted=True))
        stats = history.operator_stats()
        assert stats["DivisorShift"]["accepted"] == 1
        assert stats["DivisorShift"]["reverted"] == 1
        assert stats["DivisorShift"]["total"] == 2
        assert stats["LabelSwap"]["accepted"] == 1

    def test_fitness_timeline(self):
        history = MutationHistory()
        history.append(MutationRecord(fitness_after=0.8))
        history.append(MutationRecord(fitness_after=0.85))
        history.append(MutationRecord(fitness_after=0.9))
        timeline = history.fitness_timeline()
        assert timeline == [0.8, 0.85, 0.9]

    def test_records_are_ordered(self):
        history = MutationHistory()
        history.append(MutationRecord(operator_name="First"))
        history.append(MutationRecord(operator_name="Second"))
        records = history.records
        assert records[0].operator_name == "First"
        assert records[1].operator_name == "Second"


# ════════════════════════════════════════════════════════════════════
# SelfModifyingEngine Tests
# ════════════════════════════════════════════════════════════════════


class TestSelfModifyingEngine:
    """Tests for the main self-modifying engine."""

    def test_evaluate_returns_correct_result(self, engine: SelfModifyingEngine):
        assert engine.evaluate(3) == "Fizz"
        assert engine.evaluate(5) == "Buzz"
        assert engine.evaluate(15) == "FizzBuzz"
        assert engine.evaluate(7) == "7"

    def test_evaluate_without_mutations(self, engine: SelfModifyingEngine):
        """With mutation_rate=0, no mutations should occur."""
        for n in range(1, 31):
            engine.evaluate(n)
        assert engine.history.total_count == 0

    def test_manual_mutation_attempt(self, engine: SelfModifyingEngine):
        """Manually trigger a mutation attempt."""
        engine._attempt_mutation()
        # At least one mutation attempt should be recorded
        assert engine.mutations_attempted == 1

    def test_mutation_rate_controls_frequency(
        self,
        mutable_rule: MutableRule,
        fitness_evaluator: FitnessEvaluator,
        safety_guard: SafetyGuard,
    ):
        """High mutation rate should trigger more mutations."""
        high_rate_engine = SelfModifyingEngine(
            rule=mutable_rule,
            operators=list(ALL_OPERATORS.values()),
            fitness_evaluator=fitness_evaluator,
            safety_guard=safety_guard,
            mutation_rate=1.0,  # Always mutate
            max_mutations=5,
            seed=42,
        )
        for n in range(1, 11):
            high_rate_engine.evaluate(n)
        assert high_rate_engine.mutations_attempted > 0

    def test_kill_switch_restores_original(self, engine: SelfModifyingEngine):
        original_fp = engine.rule.ast.fingerprint()
        # Manually corrupt the rule
        engine.rule.ast.root.children.clear()
        assert engine.rule.ast.evaluate(15) == "15"  # Broken
        # Trigger kill switch
        engine.trigger_kill_switch()
        # AST should be restored
        assert engine.rule.ast.evaluate(15) == "FizzBuzz"

    def test_max_mutations_enforced(self, engine: SelfModifyingEngine):
        engine.max_mutations = 3
        for _ in range(10):
            engine._attempt_mutation()
        assert engine.mutations_attempted <= 3

    def test_current_fitness_is_high_for_correct_rule(
        self, engine: SelfModifyingEngine
    ):
        assert engine.current_fitness > 0.7

    def test_current_correctness_is_one_for_correct_rule(
        self, engine: SelfModifyingEngine
    ):
        assert engine.current_correctness == 1.0

    def test_safety_guard_prevents_bad_mutations(
        self,
        fitness_evaluator: FitnessEvaluator,
    ):
        """Only safe mutations should be accepted."""
        guard = SafetyGuard(
            fitness_evaluator=fitness_evaluator,
            correctness_floor=1.0,  # Require perfect correctness
        )
        ast = RuleAST.from_rules([(3, "Fizz"), (5, "Buzz")])
        rule = MutableRule(name="Strict", ast=ast)
        engine = SelfModifyingEngine(
            rule=rule,
            operators=[DivisorShift()],
            fitness_evaluator=fitness_evaluator,
            safety_guard=guard,
            mutation_rate=1.0,
            max_mutations=20,
            seed=42,
        )
        # Run evaluations — mutations should all be reverted
        for n in range(1, 31):
            engine.evaluate(n)
        # The rule should still produce correct results
        for n in range(1, 31):
            expected = ""
            if n % 3 == 0:
                expected += "Fizz"
            if n % 5 == 0:
                expected += "Buzz"
            if not expected:
                expected = str(n)
            assert engine.rule.evaluate(n) == expected


# ════════════════════════════════════════════════════════════════════
# SelfModifyingDashboard Tests
# ════════════════════════════════════════════════════════════════════


class TestSelfModifyingDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_render_returns_string(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine)
        assert isinstance(output, str)

    def test_render_contains_rule_name(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine)
        assert "TestRule" in output

    def test_render_contains_dashboard_header(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine)
        assert "SELF-MODIFYING CODE DASHBOARD" in output

    def test_render_contains_ast_section(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine, show_ast=True)
        assert "Current AST" in output

    def test_render_without_ast(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine, show_ast=False)
        assert "Current AST" not in output

    def test_render_contains_fitness_section(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine, show_fitness=True)
        assert "Fitness Trend" in output

    def test_render_without_fitness(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine, show_fitness=False)
        assert "Fitness Trend" not in output

    def test_render_contains_history_section(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine, show_history=True)
        assert "Mutation History" in output

    def test_render_without_history(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine, show_history=False)
        assert "Mutation History" not in output

    def test_render_with_mutation_records(self, engine: SelfModifyingEngine):
        # Add some mutation records
        engine.history.append(MutationRecord(
            operator_name="DivisorShift", accepted=True,
            fitness_before=0.8, fitness_after=0.85,
        ))
        engine.history.append(MutationRecord(
            operator_name="LabelSwap", accepted=False,
            fitness_before=0.85, fitness_after=0.7,
        ))
        output = SelfModifyingDashboard.render(engine)
        assert "DivisorShift" in output
        assert "ACCEPT" in output
        assert "REVERT" in output

    def test_sparkline_generation(self):
        values = [0.0, 0.25, 0.5, 0.75, 1.0]
        sparkline = SelfModifyingDashboard._sparkline(values, 20)
        assert len(sparkline) == 5
        assert sparkline[0] != sparkline[-1]

    def test_sparkline_empty(self):
        sparkline = SelfModifyingDashboard._sparkline([], 20)
        assert sparkline == ""

    def test_custom_width(self, engine: SelfModifyingEngine):
        output = SelfModifyingDashboard.render(engine, width=80)
        # Borders should be 80 chars wide
        lines = output.split("\n")
        border_lines = [l for l in lines if l.startswith("+") and l.endswith("+")]
        for line in border_lines:
            assert len(line) == 80


# ════════════════════════════════════════════════════════════════════
# SelfModifyingMiddleware Tests
# ════════════════════════════════════════════════════════════════════


class TestSelfModifyingMiddleware:
    """Tests for the pipeline middleware integration."""

    def test_middleware_name(self, engine: SelfModifyingEngine):
        mw = SelfModifyingMiddleware(engine=engine)
        assert mw.get_name() == "SelfModifyingMiddleware"

    def test_middleware_priority(self, engine: SelfModifyingEngine):
        mw = SelfModifyingMiddleware(engine=engine)
        assert mw.get_priority() == -6

    def test_middleware_adds_metadata(self, engine: SelfModifyingEngine):
        mw = SelfModifyingMiddleware(engine=engine)
        context = ProcessingContext(number=15, session_id="test-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            return ctx

        result = mw.process(context, next_handler)
        assert "self_modify_generation" in result.metadata
        assert "self_modify_fitness" in result.metadata
        assert "self_modify_correctness" in result.metadata
        assert "self_modify_mutations_proposed" in result.metadata

    def test_middleware_passes_through_to_next(self, engine: SelfModifyingEngine):
        mw = SelfModifyingMiddleware(engine=engine)
        context = ProcessingContext(number=15, session_id="test-session")
        called = [False]

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            called[0] = True
            return ctx

        mw.process(context, next_handler)
        assert called[0]


# ════════════════════════════════════════════════════════════════════
# Factory Function Tests
# ════════════════════════════════════════════════════════════════════


class TestCreateSelfModifyingEngine:
    """Tests for the engine factory function."""

    def test_creates_engine(self, standard_rules: list[tuple[int, str]]):
        engine = create_self_modifying_engine(
            rules=standard_rules,
            mutation_rate=0.0,
            seed=42,
            range_start=1,
            range_end=15,
        )
        assert isinstance(engine, SelfModifyingEngine)

    def test_engine_produces_correct_results(
        self, standard_rules: list[tuple[int, str]]
    ):
        engine = create_self_modifying_engine(
            rules=standard_rules,
            mutation_rate=0.0,
            seed=42,
            range_start=1,
            range_end=15,
        )
        assert engine.evaluate(3) == "Fizz"
        assert engine.evaluate(5) == "Buzz"
        assert engine.evaluate(15) == "FizzBuzz"
        assert engine.evaluate(7) == "7"

    def test_custom_operators(self, standard_rules: list[tuple[int, str]]):
        engine = create_self_modifying_engine(
            rules=standard_rules,
            enabled_operators=["DeadCodePrune", "InsertShortCircuit"],
            seed=42,
            range_start=1,
            range_end=15,
        )
        assert len(engine.operators) == 2

    def test_invalid_operator_names_filtered(
        self, standard_rules: list[tuple[int, str]]
    ):
        engine = create_self_modifying_engine(
            rules=standard_rules,
            enabled_operators=["DeadCodePrune", "NonExistentOperator"],
            seed=42,
            range_start=1,
            range_end=15,
        )
        assert len(engine.operators) == 1

    def test_empty_operators_gets_all(
        self, standard_rules: list[tuple[int, str]]
    ):
        engine = create_self_modifying_engine(
            rules=standard_rules,
            enabled_operators=[],
            seed=42,
            range_start=1,
            range_end=15,
        )
        assert len(engine.operators) == 12


# ════════════════════════════════════════════════════════════════════
# Exception Tests
# ════════════════════════════════════════════════════════════════════


class TestSelfModifyingExceptions:
    """Tests for self-modifying code exception hierarchy."""

    def test_base_exception(self):
        exc = SelfModifyingCodeError("test error")
        assert "EFP-SMC00" in str(exc)

    def test_ast_corruption_error(self):
        exc = ASTCorruptionError("TestRule", "dangling pointer")
        assert "EFP-SMC01" in str(exc)
        assert exc.rule_name == "TestRule"
        assert "dangling pointer" in str(exc)

    def test_mutation_safety_violation(self):
        exc = MutationSafetyViolation("DivisorShift", "broke everything", 0.5)
        assert "EFP-SMC02" in str(exc)
        assert exc.operator_name == "DivisorShift"
        assert exc.correctness == 0.5

    def test_fitness_collapse_error(self):
        exc = FitnessCollapseError("BadRule", 0.1, 0.5)
        assert "EFP-SMC03" in str(exc)
        assert exc.rule_name == "BadRule"
        assert exc.fitness == 0.1

    def test_mutation_quota_exhausted(self):
        exc = MutationQuotaExhaustedError(100, 101)
        assert "EFP-SMC04" in str(exc)

    def test_exception_hierarchy(self):
        exc = ASTCorruptionError("rule", "reason")
        assert isinstance(exc, SelfModifyingCodeError)
        assert isinstance(exc, Exception)


# ════════════════════════════════════════════════════════════════════
# EventType Tests
# ════════════════════════════════════════════════════════════════════


class TestSelfModifyingEventTypes:
    """Tests for self-modifying code event types."""

    def test_event_types_exist(self):
        assert hasattr(EventType, "SELF_MODIFY_MUTATION_PROPOSED")
        assert hasattr(EventType, "SELF_MODIFY_MUTATION_ACCEPTED")
        assert hasattr(EventType, "SELF_MODIFY_MUTATION_REVERTED")
        assert hasattr(EventType, "SELF_MODIFY_FITNESS_EVALUATED")
        assert hasattr(EventType, "SELF_MODIFY_SAFETY_VIOLATION")
        assert hasattr(EventType, "SELF_MODIFY_DASHBOARD_RENDERED")

    def test_event_types_are_unique(self):
        sm_events = [
            EventType.SELF_MODIFY_MUTATION_PROPOSED,
            EventType.SELF_MODIFY_MUTATION_ACCEPTED,
            EventType.SELF_MODIFY_MUTATION_REVERTED,
            EventType.SELF_MODIFY_FITNESS_EVALUATED,
            EventType.SELF_MODIFY_SAFETY_VIOLATION,
            EventType.SELF_MODIFY_DASHBOARD_RENDERED,
        ]
        assert len(sm_events) == len(set(sm_events))


# ════════════════════════════════════════════════════════════════════
# Integration Tests
# ════════════════════════════════════════════════════════════════════


class TestSelfModifyingIntegration:
    """Integration tests verifying end-to-end behavior."""

    def test_full_evaluation_cycle(self, standard_rules: list[tuple[int, str]]):
        """Run a full evaluation cycle and verify correctness is maintained."""
        engine = create_self_modifying_engine(
            rules=standard_rules,
            mutation_rate=0.5,
            correctness_floor=1.0,  # Require perfect correctness
            seed=42,
            range_start=1,
            range_end=30,
            max_mutations=50,
        )

        # Evaluate all numbers multiple times
        for _ in range(3):
            for n in range(1, 31):
                result = engine.evaluate(n)
                # Build expected result
                expected = ""
                if n % 3 == 0:
                    expected += "Fizz"
                if n % 5 == 0:
                    expected += "Buzz"
                if not expected:
                    expected = str(n)
                assert result == expected, (
                    f"n={n}: got {result!r}, expected {expected!r} "
                    f"(gen={engine.rule.ast.generation})"
                )

    def test_engine_with_safe_operators_only(
        self, standard_rules: list[tuple[int, str]]
    ):
        """Using only safe operators should maintain correctness."""
        engine = create_self_modifying_engine(
            rules=standard_rules,
            mutation_rate=1.0,
            correctness_floor=1.0,
            enabled_operators=["DeadCodePrune", "InsertShortCircuit",
                               "InsertRedundantCheck"],
            seed=42,
            range_start=1,
            range_end=15,
            max_mutations=20,
        )

        for n in range(1, 16):
            engine.evaluate(n)

        # Verify the rule still produces correct results
        assert engine.current_correctness == 1.0

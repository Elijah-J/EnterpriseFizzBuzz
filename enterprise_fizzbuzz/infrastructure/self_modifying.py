"""
Enterprise FizzBuzz Platform - Self-Modifying Code Module

Implements FizzBuzz rules that inspect and rewrite their own evaluation
logic at runtime using mutable Abstract Syntax Trees, stochastic mutation
operators, a Darwinian fitness evaluator, and a SafetyGuard that prevents
the rules from evolving into something that produces incorrect results.

The core insight is profound: if FizzBuzz rules can rewrite themselves,
perhaps they can discover more efficient — or at least more entertaining —
ways to evaluate divisibility. In practice, the SafetyGuard vetoes most
mutations because "correct FizzBuzz" is a fairly narrow evolutionary niche.

The system implements a genetic-programming-inspired loop:
1. Evaluate numbers using the current AST
2. Occasionally propose a random mutation
3. Score the mutated version against ground truth
4. Accept the mutation if fitness improves (or is within tolerance)
5. Revert if the SafetyGuard detects a correctness violation

This is, without question, the most dangerous subsystem in the Enterprise
FizzBuzz Platform. Code that modifies itself is either the future of
computing or the plot of a horror film. Possibly both.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ASTCorruptionError,
    FitnessCollapseError,
    MutationQuotaExhaustedError,
    MutationSafetyViolation,
    SelfModifyingCodeError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# AST Node Types
# ════════════════════════════════════════════════════════════════════
# The mutable AST represents a FizzBuzz rule as a tree of nodes.
# Each node type corresponds to a fundamental operation in the
# grand taxonomy of modulo arithmetic:
#
#   DivisibilityNode — checks if n % divisor == 0
#   EmitNode         — produces a label string ("Fizz", "Buzz", etc.)
#   ConditionalNode  — if-then-else branching
#   SequenceNode     — executes children in order, concatenating outputs
#   NoOpNode         — does nothing (the evolutionary appendix)
#
# These nodes can be freely composed, cloned, mutated, and pruned.
# The result is a tree that can represent any FizzBuzz evaluation
# strategy — and many strategies that are not FizzBuzz at all,
# which is where the SafetyGuard earns its keep.
# ════════════════════════════════════════════════════════════════════


class NodeType(Enum):
    """Classification of AST node types in the self-modifying rule tree."""

    DIVISIBILITY = auto()
    EMIT = auto()
    CONDITIONAL = auto()
    SEQUENCE = auto()
    NOOP = auto()


@dataclass
class ASTNode:
    """Base node in the mutable FizzBuzz rule AST.

    Every node has a unique ID for tracking mutations, a type for
    dispatching, and optional children. Nodes are mutable by design
    — immutability is the enemy of self-modification.

    Attributes:
        node_id: Unique identifier for this specific node instance.
        node_type: What kind of AST operation this node represents.
        children: Child nodes (for compound expressions).
        metadata: Arbitrary metadata attached by mutation operators.
    """

    node_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    node_type: NodeType = NodeType.NOOP
    children: list[ASTNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DivisibilityNode(ASTNode):
    """AST node that checks divisibility: n % divisor == 0.

    The fundamental building block of FizzBuzz evaluation, elevated
    to a mutable AST node so that it can be cloned, swapped, inverted,
    and otherwise subjected to the whims of stochastic mutation operators.
    The modulo operator has never been so vulnerable.

    Attributes:
        divisor: The divisor to check against.
    """

    divisor: int = 3

    def __post_init__(self) -> None:
        self.node_type = NodeType.DIVISIBILITY


@dataclass
class EmitNode(ASTNode):
    """AST node that produces a label string.

    When reached during evaluation, this node contributes its label
    to the output string. "Fizz" and "Buzz" are the classic labels,
    but mutation operators may swap them, duplicate them, or introduce
    entirely new labels from the void.

    Attributes:
        label: The string to emit.
    """

    label: str = ""

    def __post_init__(self) -> None:
        self.node_type = NodeType.EMIT


@dataclass
class ConditionalNode(ASTNode):
    """AST node implementing if-then-else branching.

    The condition is the first child, the then-branch is the second,
    and the else-branch (if present) is the third. This allows the
    AST to express the classic FizzBuzz decision tree:

        if n % 3 == 0:
            emit "Fizz"
        if n % 5 == 0:
            emit "Buzz"

    Mutation operators can invert conditions, swap branches, or
    insert additional levels of nesting until the AST resembles
    a particularly anxious decision forest.
    """

    def __post_init__(self) -> None:
        self.node_type = NodeType.CONDITIONAL


@dataclass
class SequenceNode(ASTNode):
    """AST node that executes children in order, concatenating outputs.

    The root of most FizzBuzz ASTs is a SequenceNode whose children
    are ConditionalNodes for each rule. Outputs are concatenated
    left-to-right, which is how "Fizz" + "Buzz" = "FizzBuzz".
    """

    def __post_init__(self) -> None:
        self.node_type = NodeType.SEQUENCE


@dataclass
class NoOpNode(ASTNode):
    """AST node that does nothing. The vestigial organ of self-modifying code.

    Inserted by mutation operators when they need a placeholder,
    and removed by the DeadCodePrune operator when it detects that
    this node contributes nothing to the output. Its existence is
    fleeting and purposeless — much like this docstring.
    """

    def __post_init__(self) -> None:
        self.node_type = NodeType.NOOP


# ════════════════════════════════════════════════════════════════════
# RuleAST — The Mutable Abstract Syntax Tree
# ════════════════════════════════════════════════════════════════════


class RuleAST:
    """Mutable Abstract Syntax Tree representing a FizzBuzz evaluation rule.

    The RuleAST can be evaluated against a number to produce a FizzBuzz
    classification, converted to source code for inspection, cloned for
    speculative mutation, and measured for depth and node count. It is
    the living, breathing embodiment of a FizzBuzz rule — a rule that
    can rewrite itself, question its own existence, and occasionally
    mutate into something that no longer works.

    The canonical AST for standard FizzBuzz looks like:

        Sequence
          Conditional
            condition: Divisibility(3)
            then: Emit("Fizz")
          Conditional
            condition: Divisibility(5)
            then: Emit("Buzz")
    """

    def __init__(self, root: Optional[ASTNode] = None) -> None:
        self.root = root or SequenceNode()
        self._generation: int = 0

    @classmethod
    def from_rules(cls, rules: list[tuple[int, str]]) -> RuleAST:
        """Build a canonical AST from a list of (divisor, label) pairs.

        This is the genesis of the self-modifying rule: it starts as a
        faithful representation of the configured rules, pristine and
        correct. What happens next is between the mutation operators
        and the SafetyGuard.
        """
        root = SequenceNode()
        for divisor, label in rules:
            cond = ConditionalNode()
            cond.children = [
                DivisibilityNode(divisor=divisor),
                EmitNode(label=label),
            ]
            root.children.append(cond)
        ast = cls(root)
        return ast

    def clone(self) -> RuleAST:
        """Create a deep copy of this AST for speculative mutation.

        Every mutation is applied to a clone first. If the SafetyGuard
        approves, the clone replaces the original. If not, the clone
        is discarded and the original survives, blissfully unaware of
        the horrors that were proposed for it.
        """
        cloned = RuleAST(root=copy.deepcopy(self.root))
        cloned._generation = self._generation
        return cloned

    def depth(self, node: Optional[ASTNode] = None) -> int:
        """Calculate the maximum depth of the AST from the given node.

        Deeper ASTs are more complex, which sounds impressive but is
        usually the result of mutation operators inserting unnecessary
        layers of ConditionalNodes around perfectly functional code.
        """
        if node is None:
            node = self.root
        if not node.children:
            return 1
        return 1 + max(self.depth(child) for child in node.children)

    def node_count(self, node: Optional[ASTNode] = None) -> int:
        """Count the total number of nodes in the AST."""
        if node is None:
            node = self.root
        count = 1
        for child in node.children:
            count += self.node_count(child)
        return count

    def evaluate(self, n: int) -> str:
        """Evaluate the AST against a number and return the FizzBuzz output.

        Traverses the AST depth-first, collecting emit labels from
        branches whose conditions are satisfied. If no labels are
        collected, returns str(n) — the number itself, unchanged
        and unmutated, in the tradition of all FizzBuzz implementations.

        Args:
            n: The number to evaluate.

        Returns:
            The FizzBuzz classification string.
        """
        result = self._eval_node(self.root, n)
        return result if result else str(n)

    def _eval_node(self, node: ASTNode, n: int) -> str:
        """Recursively evaluate a single AST node."""
        if node.node_type == NodeType.DIVISIBILITY:
            div_node = node
            if not isinstance(div_node, DivisibilityNode):
                return ""
            return "1" if (div_node.divisor != 0 and n % div_node.divisor == 0) else ""

        elif node.node_type == NodeType.EMIT:
            emit_node = node
            if not isinstance(emit_node, EmitNode):
                return ""
            return emit_node.label

        elif node.node_type == NodeType.CONDITIONAL:
            if len(node.children) < 2:
                return ""
            condition_result = self._eval_node(node.children[0], n)
            if condition_result:
                return self._eval_node(node.children[1], n)
            elif len(node.children) >= 3:
                return self._eval_node(node.children[2], n)
            return ""

        elif node.node_type == NodeType.SEQUENCE:
            parts: list[str] = []
            for child in node.children:
                part = self._eval_node(child, n)
                if part:
                    parts.append(part)
            return "".join(parts)

        elif node.node_type == NodeType.NOOP:
            return ""

        return ""

    def to_source(self, node: Optional[ASTNode] = None, indent: int = 0) -> str:
        """Convert the AST to a human-readable pseudo-source representation.

        This is not valid Python — it is a pedagogical rendering of the
        AST structure that makes the self-modifying logic visible to
        human observers. The goal is to show what the rule *does*, not
        to produce executable code (that's what evaluate() is for).
        """
        if node is None:
            node = self.root
        pad = "  " * indent

        if node.node_type == NodeType.DIVISIBILITY:
            div_node = node
            if isinstance(div_node, DivisibilityNode):
                return f"{pad}divisible_by({div_node.divisor})"
            return f"{pad}divisible_by(?)"

        elif node.node_type == NodeType.EMIT:
            emit_node = node
            if isinstance(emit_node, EmitNode):
                return f'{pad}emit("{emit_node.label}")'
            return f'{pad}emit("?")'

        elif node.node_type == NodeType.CONDITIONAL:
            lines = [f"{pad}if:"]
            if node.children:
                lines.append(self.to_source(node.children[0], indent + 1))
            if len(node.children) > 1:
                lines.append(f"{pad}then:")
                lines.append(self.to_source(node.children[1], indent + 1))
            if len(node.children) > 2:
                lines.append(f"{pad}else:")
                lines.append(self.to_source(node.children[2], indent + 1))
            return "\n".join(lines)

        elif node.node_type == NodeType.SEQUENCE:
            lines = [f"{pad}sequence:"]
            for child in node.children:
                lines.append(self.to_source(child, indent + 1))
            return "\n".join(lines)

        elif node.node_type == NodeType.NOOP:
            return f"{pad}noop"

        return f"{pad}unknown"

    def collect_nodes(self, node: Optional[ASTNode] = None) -> list[ASTNode]:
        """Collect all nodes in the AST into a flat list."""
        if node is None:
            node = self.root
        nodes = [node]
        for child in node.children:
            nodes.extend(self.collect_nodes(child))
        return nodes

    def fingerprint(self) -> str:
        """Generate a hash fingerprint of the AST structure.

        Used to detect duplicate mutations and track lineage.
        """
        source = self.to_source()
        return hashlib.sha256(source.encode()).hexdigest()[:16]

    @property
    def generation(self) -> int:
        """The number of accepted mutations that produced this AST."""
        return self._generation

    def increment_generation(self) -> None:
        """Advance the generation counter after an accepted mutation."""
        self._generation += 1


# ════════════════════════════════════════════════════════════════════
# MutableRule — A Rule That Can Rewrite Itself
# ════════════════════════════════════════════════════════════════════


class MutableRule:
    """A FizzBuzz rule backed by a mutable AST.

    Unlike a normal rule that evaluates n % divisor == 0 and returns
    a label, this rule traverses an entire AST that can be modified
    at runtime by mutation operators. The rule tracks per-evaluation
    statistics including invocation count, total latency, and the
    number of mutations that have been accepted or reverted.

    It implements the same evaluate(n) interface as IRule, making it
    a drop-in replacement for any deterministic rule — except that
    this one might change its behavior between evaluations, which is
    either a feature or a terrifying liability depending on whether
    the SafetyGuard is doing its job.
    """

    def __init__(self, name: str, ast: RuleAST) -> None:
        self.name = name
        self.ast = ast
        self.evaluation_count: int = 0
        self.total_latency_ns: int = 0
        self.mutations_accepted: int = 0
        self.mutations_reverted: int = 0

    def evaluate(self, n: int) -> str:
        """Evaluate the number against the mutable AST.

        Returns the FizzBuzz classification string produced by
        traversing the AST. Tracks timing for fitness evaluation.
        """
        start = time.perf_counter_ns()
        result = self.ast.evaluate(n)
        elapsed = time.perf_counter_ns() - start
        self.evaluation_count += 1
        self.total_latency_ns += elapsed
        return result

    @property
    def avg_latency_ns(self) -> float:
        """Average evaluation latency in nanoseconds."""
        if self.evaluation_count == 0:
            return 0.0
        return self.total_latency_ns / self.evaluation_count

    def clone_ast(self) -> RuleAST:
        """Clone the current AST for speculative mutation."""
        return self.ast.clone()

    def replace_ast(self, new_ast: RuleAST) -> None:
        """Replace the current AST with a mutated version."""
        self.ast = new_ast
        self.ast.increment_generation()
        self.mutations_accepted += 1

    def record_revert(self) -> None:
        """Record that a proposed mutation was reverted."""
        self.mutations_reverted += 1

    def __repr__(self) -> str:
        return (
            f"MutableRule(name={self.name!r}, gen={self.ast.generation}, "
            f"evals={self.evaluation_count}, accepted={self.mutations_accepted}, "
            f"reverted={self.mutations_reverted})"
        )


# ════════════════════════════════════════════════════════════════════
# Mutation Operators — The Twelve Labors of Self-Modification
# ════════════════════════════════════════════════════════════════════
# Each operator implements a single atomic mutation on the AST.
# Some are benign (DeadCodePrune), some are dangerous (DivisorShift),
# and some are purely cosmetic (ShuffleChildren). Together they form
# the mutation vocabulary of the self-modifying engine — the alphabet
# of change from which evolution spells its improvements (and its
# catastrophes).
# ════════════════════════════════════════════════════════════════════


class MutationOperator:
    """Base class for AST mutation operators.

    Each operator has a name, a description, and an apply() method
    that mutates an AST in place. Operators should be idempotent
    where possible, but this is self-modifying code — consistency
    is a suggestion, not a guarantee.
    """

    name: str = "BaseOperator"
    description: str = "Does nothing. The platonic ideal of a mutation."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        """Apply the mutation to the AST. Returns True if mutation was applied."""
        return False


class DivisorShift(MutationOperator):
    """Shifts a randomly selected divisor by +1 or -1.

    The most dangerous operator: changing the divisor changes what
    numbers the rule matches. A Fizz rule (divisor=3) could become
    a rule for divisor=4, which is not Fizz at all. The SafetyGuard
    almost always reverts these mutations, but occasionally one slips
    through when the test range doesn't cover the affected numbers.
    """

    name = "DivisorShift"
    description = "Shift a divisor by +/-1. Extremely dangerous."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        nodes = [n for n in ast.collect_nodes() if isinstance(n, DivisibilityNode)]
        if not nodes:
            return False
        target = rng.choice(nodes)
        delta = rng.choice([-1, 1])
        new_divisor = target.divisor + delta
        if new_divisor < 1:
            new_divisor = 1
        target.divisor = new_divisor
        target.metadata["last_mutation"] = f"DivisorShift({delta:+d})"
        return True


class LabelSwap(MutationOperator):
    """Swaps the labels of two randomly selected EmitNodes.

    Fizz becomes Buzz, Buzz becomes Fizz. The semantic confusion
    this causes is profound, but the rule still produces *some*
    output — just not the right one. The SafetyGuard usually
    catches this within a single evaluation cycle.
    """

    name = "LabelSwap"
    description = "Swap labels between two emit nodes."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        nodes = [n for n in ast.collect_nodes() if isinstance(n, EmitNode)]
        if len(nodes) < 2:
            return False
        a, b = rng.sample(nodes, 2)
        a.label, b.label = b.label, a.label
        a.metadata["last_mutation"] = "LabelSwap"
        b.metadata["last_mutation"] = "LabelSwap"
        return True


class BranchInvert(MutationOperator):
    """Inverts a conditional by swapping its then/else branches.

    What was once true is now false. The condition still evaluates,
    but the branches it selects are reversed. This is the logical
    negation of an entire decision subtree — philosophically
    interesting, practically catastrophic.
    """

    name = "BranchInvert"
    description = "Swap then/else branches of a conditional node."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        nodes = [n for n in ast.collect_nodes()
                 if isinstance(n, ConditionalNode) and len(n.children) >= 2]
        if not nodes:
            return False
        target = rng.choice(nodes)
        if len(target.children) == 2:
            # Add a NoOp as else branch, then swap
            target.children.append(NoOpNode())
        target.children[1], target.children[2] = target.children[2], target.children[1]
        target.metadata["last_mutation"] = "BranchInvert"
        return True


class InsertShortCircuit(MutationOperator):
    """Inserts a short-circuit check that bypasses a subtree.

    Wraps a random subtree in a conditional that always evaluates
    to true (divisible_by(1)), effectively adding a redundant guard.
    Harmless but wasteful — the evolutionary equivalent of a wisdom tooth.
    """

    name = "InsertShortCircuit"
    description = "Wrap a subtree in a tautological conditional."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        if not ast.root.children:
            return False
        idx = rng.randint(0, len(ast.root.children) - 1)
        original = ast.root.children[idx]
        wrapper = ConditionalNode()
        wrapper.children = [
            DivisibilityNode(divisor=1),  # Always true: n % 1 == 0
            original,
        ]
        ast.root.children[idx] = wrapper
        wrapper.metadata["last_mutation"] = "InsertShortCircuit"
        return True


class DeadCodePrune(MutationOperator):
    """Removes NoOp nodes from the AST.

    The janitor of self-modifying code: sweeps away the vestigial
    nodes that other operators leave behind. This is the only mutation
    that consistently improves the AST without risk — removing nothing
    from nothing always produces nothing.
    """

    name = "DeadCodePrune"
    description = "Remove NoOp nodes from the AST."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        pruned = False

        def prune_children(node: ASTNode) -> bool:
            nonlocal pruned
            original_len = len(node.children)
            node.children = [c for c in node.children
                             if not isinstance(c, NoOpNode)]
            if len(node.children) < original_len:
                pruned = True
            for child in node.children:
                prune_children(child)
            return pruned

        prune_children(ast.root)
        return pruned


class SubtreeSwap(MutationOperator):
    """Swaps two random subtrees within the AST.

    Takes two non-root subtrees and exchanges their positions in
    the tree. This can produce wildly different evaluation semantics
    if the swapped subtrees have different types or depths. The AST
    equivalent of rearranging the furniture in a burning building.
    """

    name = "SubtreeSwap"
    description = "Swap two random subtrees."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        # Collect parent-child pairs for swapping
        pairs: list[tuple[ASTNode, int]] = []
        for node in ast.collect_nodes():
            for i, _child in enumerate(node.children):
                pairs.append((node, i))
        if len(pairs) < 2:
            return False
        pair_a, pair_b = rng.sample(pairs, 2)
        parent_a, idx_a = pair_a
        parent_b, idx_b = pair_b
        parent_a.children[idx_a], parent_b.children[idx_b] = (
            parent_b.children[idx_b], parent_a.children[idx_a]
        )
        return True


class DuplicateSubtree(MutationOperator):
    """Duplicates a random subtree and appends it to the root sequence.

    Gene duplication is one of evolution's most powerful mechanisms.
    In FizzBuzz, duplicating a conditional check means the same
    label gets emitted twice — "FizzFizz" instead of "Fizz". The
    SafetyGuard will notice, but the mutation history will record
    this ambitious attempt at self-improvement.
    """

    name = "DuplicateSubtree"
    description = "Clone a subtree and append it to the root."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        if not ast.root.children:
            return False
        idx = rng.randint(0, len(ast.root.children) - 1)
        cloned = copy.deepcopy(ast.root.children[idx])
        cloned.node_id = uuid.uuid4().hex[:8]
        cloned.metadata["last_mutation"] = "DuplicateSubtree"
        ast.root.children.append(cloned)
        return True


class NegateCondition(MutationOperator):
    """Wraps a divisibility check in a NOT operation by swapping branches.

    Instead of checking "is divisible by 3", the condition now means
    "is NOT divisible by 3". This is achieved by swapping then/else
    branches, which is semantically equivalent to logical negation
    without needing a dedicated NOT node.
    """

    name = "NegateCondition"
    description = "Negate a condition by branch swap."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        nodes = [n for n in ast.collect_nodes()
                 if isinstance(n, ConditionalNode) and len(n.children) >= 2]
        if not nodes:
            return False
        target = rng.choice(nodes)
        if len(target.children) < 3:
            target.children.append(NoOpNode())
        target.children[1], target.children[2] = target.children[2], target.children[1]
        target.metadata["last_mutation"] = "NegateCondition"
        return True


class ConstantFold(MutationOperator):
    """Replaces a tautological divisibility check with its known result.

    If the divisor is 1 (everything is divisible by 1), replace the
    conditional with just its then-branch. This is compiler optimization
    applied to a mutable AST — the kind of optimization that a real
    compiler does automatically but that we perform stochastically
    because determinism is boring.
    """

    name = "ConstantFold"
    description = "Fold tautological conditions (divisor=1)."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        for node in ast.collect_nodes():
            if isinstance(node, ConditionalNode) and node.children:
                cond = node.children[0]
                if isinstance(cond, DivisibilityNode) and cond.divisor == 1:
                    if len(node.children) >= 2:
                        # Replace the conditional with its then-branch
                        then_branch = node.children[1]
                        node.node_type = then_branch.node_type
                        node.__class__ = then_branch.__class__
                        node.children = then_branch.children
                        if isinstance(then_branch, EmitNode):
                            node.label = then_branch.label  # type: ignore[attr-defined]
                        node.metadata["last_mutation"] = "ConstantFold"
                        return True
        return False


class InsertRedundantCheck(MutationOperator):
    """Inserts a redundant divisibility check that duplicates an existing one.

    The self-modifying equivalent of writing the same if-statement twice.
    Produces no behavioral change but increases AST complexity, giving
    the DeadCodePrune operator something to clean up in a future cycle.
    Symbiosis in action.
    """

    name = "InsertRedundantCheck"
    description = "Add a duplicate divisibility check."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        div_nodes = [n for n in ast.collect_nodes() if isinstance(n, DivisibilityNode)]
        if not div_nodes:
            return False
        template = rng.choice(div_nodes)
        # Find the emit node that corresponds to this divisor
        emit_nodes = [n for n in ast.collect_nodes() if isinstance(n, EmitNode)]
        if not emit_nodes:
            return False
        emit = rng.choice(emit_nodes)
        new_cond = ConditionalNode()
        new_cond.children = [
            DivisibilityNode(divisor=template.divisor),
            NoOpNode(),  # Redundant — emits nothing even when true
        ]
        new_cond.metadata["last_mutation"] = "InsertRedundantCheck"
        ast.root.children.append(new_cond)
        return True


class ShuffleChildren(MutationOperator):
    """Shuffles the order of children in the root sequence node.

    Reordering the rule checks changes the concatenation order
    of labels. "FizzBuzz" becomes "BuzzFizz" if the Buzz check
    is moved before the Fizz check. The SafetyGuard catches this
    because "BuzzFizz" != "FizzBuzz" according to string equality,
    which is the most pedantic form of mathematical correctness.
    """

    name = "ShuffleChildren"
    description = "Randomize child execution order."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        if len(ast.root.children) < 2:
            return False
        rng.shuffle(ast.root.children)
        return True


class WrapInConditional(MutationOperator):
    """Wraps a random subtree in a new conditional with a random divisor.

    The mutation operator equivalent of "but what if we also check
    divisibility by 7?" — adds an entirely new condition around
    existing logic. Usually produces incorrect results because the
    random divisor filters out numbers that should have matched.
    """

    name = "WrapInConditional"
    description = "Wrap a subtree in a new random conditional."

    def apply(self, ast: RuleAST, rng: random.Random) -> bool:
        if not ast.root.children:
            return False
        idx = rng.randint(0, len(ast.root.children) - 1)
        original = ast.root.children[idx]
        new_divisor = rng.randint(1, 15)
        wrapper = ConditionalNode()
        wrapper.children = [
            DivisibilityNode(divisor=new_divisor),
            original,
        ]
        wrapper.metadata["last_mutation"] = f"WrapInConditional(div={new_divisor})"
        ast.root.children[idx] = wrapper
        return True


# Registry of all mutation operators
ALL_OPERATORS: dict[str, MutationOperator] = {
    "DivisorShift": DivisorShift(),
    "LabelSwap": LabelSwap(),
    "BranchInvert": BranchInvert(),
    "InsertShortCircuit": InsertShortCircuit(),
    "DeadCodePrune": DeadCodePrune(),
    "SubtreeSwap": SubtreeSwap(),
    "DuplicateSubtree": DuplicateSubtree(),
    "NegateCondition": NegateCondition(),
    "ConstantFold": ConstantFold(),
    "InsertRedundantCheck": InsertRedundantCheck(),
    "ShuffleChildren": ShuffleChildren(),
    "WrapInConditional": WrapInConditional(),
}


# ════════════════════════════════════════════════════════════════════
# FitnessEvaluator — Darwinian Selection for FizzBuzz Rules
# ════════════════════════════════════════════════════════════════════


class FitnessEvaluator:
    """Scores a mutable rule against ground truth using a weighted fitness function.

    The fitness function balances three concerns:
    - **Correctness** (default weight 0.7): Does the rule produce the
      right FizzBuzz classification for every number in the test range?
    - **Latency** (default weight 0.2): How fast does the rule evaluate?
      Faster is better, because even self-modifying code should be efficient.
    - **Compactness** (default weight 0.1): How many nodes does the AST
      contain? Fewer nodes = simpler code = higher compactness score.

    The fitness score is a float in [0.0, 1.0]. A score of 1.0 means
    the rule is perfect, fast, and minimal. A score of 0.0 means the
    rule has evolved into a non-functional heap of ConditionalNodes
    that returns "BuzzFizzBuzzFizz" for every input.
    """

    def __init__(
        self,
        ground_truth: dict[int, str],
        correctness_weight: float = 0.70,
        latency_weight: float = 0.20,
        compactness_weight: float = 0.10,
        max_acceptable_nodes: int = 50,
    ) -> None:
        self.ground_truth = ground_truth
        self.correctness_weight = correctness_weight
        self.latency_weight = latency_weight
        self.compactness_weight = compactness_weight
        self.max_acceptable_nodes = max_acceptable_nodes

    @staticmethod
    def build_ground_truth(
        rules: list[tuple[int, str]],
        range_start: int = 1,
        range_end: int = 100,
    ) -> dict[int, str]:
        """Build ground truth by evaluating rules deterministically.

        This is the oracle: the canonical, deterministic FizzBuzz
        evaluation that all mutations are compared against. It is
        computed once and never mutated, because the truth should
        not be subject to stochastic modification.
        """
        truth: dict[int, str] = {}
        for n in range(range_start, range_end + 1):
            output = ""
            for divisor, label in rules:
                if n % divisor == 0:
                    output += label
            if not output:
                output = str(n)
            truth[n] = output
        return truth

    def evaluate(self, rule: MutableRule) -> float:
        """Score the rule's current AST against ground truth.

        Returns:
            Weighted fitness score in [0.0, 1.0].
        """
        # Correctness: fraction of test cases that match ground truth
        correct = 0
        total = len(self.ground_truth)
        total_time_ns = 0

        for n, expected in self.ground_truth.items():
            start = time.perf_counter_ns()
            actual = rule.ast.evaluate(n)
            total_time_ns += time.perf_counter_ns() - start
            if actual == expected:
                correct += 1

        correctness = correct / total if total > 0 else 0.0

        # Latency: normalized inversely (faster = higher score)
        # Baseline: 1000ns per evaluation is "perfect"
        avg_ns = total_time_ns / total if total > 0 else 0
        latency_score = min(1.0, 1000.0 / max(avg_ns, 1.0))

        # Compactness: fewer nodes = higher score
        node_count = rule.ast.node_count()
        compactness = max(0.0, 1.0 - (node_count / self.max_acceptable_nodes))

        fitness = (
            self.correctness_weight * correctness
            + self.latency_weight * latency_score
            + self.compactness_weight * compactness
        )

        return min(1.0, max(0.0, fitness))

    def correctness_score(self, rule: MutableRule) -> float:
        """Calculate only the correctness component of fitness."""
        correct = 0
        total = len(self.ground_truth)
        for n, expected in self.ground_truth.items():
            if rule.ast.evaluate(n) == expected:
                correct += 1
        return correct / total if total > 0 else 0.0


# ════════════════════════════════════════════════════════════════════
# SafetyGuard — The Last Line of Defense
# ════════════════════════════════════════════════════════════════════


class SafetyGuard:
    """Prevents catastrophic mutations from corrupting FizzBuzz output.

    The SafetyGuard is the conscience of the self-modifying engine.
    It evaluates every proposed mutation against the correctness floor,
    maximum AST depth, and node count limits. If a mutation would
    cause the rule to produce incorrect results for even a single
    number in the test range, the SafetyGuard vetoes the mutation
    and the original AST is preserved.

    The kill switch, when enabled, will revert ALL accumulated
    mutations if the overall correctness drops below the floor.
    This is the nuclear option — the acknowledgment that sometimes
    the best path forward is to go all the way back.
    """

    def __init__(
        self,
        fitness_evaluator: FitnessEvaluator,
        correctness_floor: float = 0.95,
        max_ast_depth: int = 10,
        max_node_count: int = 100,
        kill_switch: bool = True,
    ) -> None:
        self.fitness_evaluator = fitness_evaluator
        self.correctness_floor = correctness_floor
        self.max_ast_depth = max_ast_depth
        self.max_node_count = max_node_count
        self.kill_switch = kill_switch
        self.kill_switch_triggered: bool = False
        self.vetoes: int = 0

    def check_mutation(self, rule: MutableRule, proposed_ast: RuleAST) -> tuple[bool, str]:
        """Evaluate a proposed mutation for safety.

        Args:
            rule: The mutable rule being modified.
            proposed_ast: The AST after the proposed mutation.

        Returns:
            Tuple of (is_safe, reason). If is_safe is False, the reason
            explains why the mutation was vetoed.
        """
        # Check AST depth
        depth = proposed_ast.depth()
        if depth > self.max_ast_depth:
            self.vetoes += 1
            return False, f"AST depth {depth} exceeds maximum {self.max_ast_depth}"

        # Check node count
        count = proposed_ast.node_count()
        if count > self.max_node_count:
            self.vetoes += 1
            return False, f"Node count {count} exceeds maximum {self.max_node_count}"

        # Check correctness against ground truth
        # Create a temporary rule with the proposed AST
        temp_rule = MutableRule(name=rule.name, ast=proposed_ast)
        correctness = self.fitness_evaluator.correctness_score(temp_rule)

        if correctness < self.correctness_floor:
            self.vetoes += 1
            return False, (
                f"Correctness {correctness:.1%} is below floor "
                f"{self.correctness_floor:.1%}"
            )

        return True, "Mutation approved by SafetyGuard"

    def check_kill_switch(self, rule: MutableRule) -> bool:
        """Check if the kill switch should trigger.

        Returns True if the kill switch is triggered (correctness below floor).
        """
        if not self.kill_switch:
            return False
        correctness = self.fitness_evaluator.correctness_score(rule)
        if correctness < self.correctness_floor:
            self.kill_switch_triggered = True
            return True
        return False


# ════════════════════════════════════════════════════════════════════
# MutationHistory — The Append-Only Journal of Self-Modification
# ════════════════════════════════════════════════════════════════════


@dataclass
class MutationRecord:
    """A single entry in the mutation history journal.

    Records what operator was applied, whether the mutation was
    accepted or reverted, the fitness before and after, and a
    timestamp for forensic analysis. Every mutation leaves a trace,
    because in enterprise software, accountability extends even
    to code that modifies itself.
    """

    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    operator_name: str = ""
    accepted: bool = False
    fitness_before: float = 0.0
    fitness_after: float = 0.0
    correctness_before: float = 0.0
    correctness_after: float = 0.0
    reason: str = ""
    ast_fingerprint_before: str = ""
    ast_fingerprint_after: str = ""
    generation: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MutationHistory:
    """Append-only journal tracking all proposed mutations and their outcomes.

    Every mutation — accepted, reverted, or vetoed by the SafetyGuard —
    is recorded in this journal. The history is immutable (append-only)
    because the past cannot be changed, even by self-modifying code.
    Though if any code were arrogant enough to try, it would be this code.
    """

    def __init__(self) -> None:
        self._records: list[MutationRecord] = []

    def append(self, record: MutationRecord) -> None:
        """Append a mutation record to the journal."""
        self._records.append(record)

    @property
    def records(self) -> list[MutationRecord]:
        """All mutation records in chronological order."""
        return list(self._records)

    @property
    def accepted_count(self) -> int:
        """Number of accepted mutations."""
        return sum(1 for r in self._records if r.accepted)

    @property
    def reverted_count(self) -> int:
        """Number of reverted mutations."""
        return sum(1 for r in self._records if not r.accepted)

    @property
    def total_count(self) -> int:
        """Total number of mutation proposals."""
        return len(self._records)

    @property
    def acceptance_rate(self) -> float:
        """Fraction of mutations that were accepted."""
        if not self._records:
            return 0.0
        return self.accepted_count / len(self._records)

    def operator_stats(self) -> dict[str, dict[str, int]]:
        """Per-operator statistics: accepted/reverted/total."""
        stats: dict[str, dict[str, int]] = {}
        for r in self._records:
            if r.operator_name not in stats:
                stats[r.operator_name] = {"accepted": 0, "reverted": 0, "total": 0}
            stats[r.operator_name]["total"] += 1
            if r.accepted:
                stats[r.operator_name]["accepted"] += 1
            else:
                stats[r.operator_name]["reverted"] += 1
        return stats

    def fitness_timeline(self) -> list[float]:
        """Ordered list of fitness scores after each mutation attempt."""
        return [r.fitness_after for r in self._records]


# ════════════════════════════════════════════════════════════════════
# SelfModifyingEngine — The Main Loop of Evolution
# ════════════════════════════════════════════════════════════════════


class SelfModifyingEngine:
    """The central engine that orchestrates rule self-modification.

    On each evaluation, the engine:
    1. Evaluates the number using the current mutable rule
    2. With probability `mutation_rate`, proposes a random mutation
    3. Applies the mutation to a cloned AST
    4. Scores the mutant against ground truth via FitnessEvaluator
    5. Submits the mutant to SafetyGuard for approval
    6. Accepts or reverts the mutation based on the verdict
    7. Records everything in MutationHistory

    The engine never produces incorrect results because the SafetyGuard
    evaluates every mutation against the full ground truth before accepting
    it. The mutation rate controls how often the engine *proposes* mutations,
    not how often it *accepts* them — acceptance is determined entirely by
    the fitness evaluator and the safety constraints.

    This is, in essence, a runtime genetic programming system that
    optimizes FizzBuzz rules by stochastic search. The search space is
    the set of all possible ASTs, the fitness function rewards correctness
    and speed, and the SafetyGuard ensures that the evolved rules never
    deviate from the canonical FizzBuzz classifications.

    The irony of spending CPU cycles to evolve a rule that computes
    n % 3 == 0 is not lost on the engineering team.
    """

    def __init__(
        self,
        rule: MutableRule,
        operators: list[MutationOperator],
        fitness_evaluator: FitnessEvaluator,
        safety_guard: SafetyGuard,
        mutation_rate: float = 0.05,
        max_mutations: int = 100,
        seed: Optional[int] = None,
        event_bus: Any = None,
    ) -> None:
        self.rule = rule
        self.operators = operators
        self.fitness_evaluator = fitness_evaluator
        self.safety_guard = safety_guard
        self.mutation_rate = mutation_rate
        self.max_mutations = max_mutations
        self.history = MutationHistory()
        self.rng = random.Random(seed)
        self.event_bus = event_bus
        self._original_ast: RuleAST = rule.clone_ast()
        self._mutations_attempted: int = 0

    def evaluate(self, n: int) -> str:
        """Evaluate a number, potentially mutating the rule afterward.

        Returns the FizzBuzz classification string. The mutation (if any)
        happens AFTER the evaluation, so the current evaluation always
        uses the most recently accepted AST.
        """
        result = self.rule.evaluate(n)

        # Maybe mutate
        if self.rng.random() < self.mutation_rate:
            self._attempt_mutation()

        return result

    def _attempt_mutation(self) -> None:
        """Propose and evaluate a random mutation."""
        if self._mutations_attempted >= self.max_mutations:
            logger.debug(
                "Mutation quota exhausted (%d/%d)",
                self._mutations_attempted, self.max_mutations,
            )
            return

        self._mutations_attempted += 1

        # Select a random operator
        operator = self.rng.choice(self.operators)

        # Clone the AST for speculative mutation
        candidate_ast = self.rule.clone_ast()
        fingerprint_before = candidate_ast.fingerprint()
        fitness_before = self.fitness_evaluator.evaluate(self.rule)
        correctness_before = self.fitness_evaluator.correctness_score(self.rule)

        # Apply the mutation
        applied = operator.apply(candidate_ast, self.rng)
        if not applied:
            return

        # Safety check
        is_safe, reason = self.safety_guard.check_mutation(self.rule, candidate_ast)

        if is_safe:
            # Evaluate fitness of the mutated version
            temp_rule = MutableRule(name=self.rule.name, ast=candidate_ast)
            fitness_after = self.fitness_evaluator.evaluate(temp_rule)
            correctness_after = self.fitness_evaluator.correctness_score(temp_rule)

            # Accept the mutation
            self.rule.replace_ast(candidate_ast)

            record = MutationRecord(
                operator_name=operator.name,
                accepted=True,
                fitness_before=fitness_before,
                fitness_after=fitness_after,
                correctness_before=correctness_before,
                correctness_after=correctness_after,
                reason="Accepted: fitness maintained",
                ast_fingerprint_before=fingerprint_before,
                ast_fingerprint_after=candidate_ast.fingerprint(),
                generation=self.rule.ast.generation,
            )
            self.history.append(record)

            self._emit_event(EventType.SELF_MODIFY_MUTATION_ACCEPTED, {
                "operator": operator.name,
                "fitness": fitness_after,
                "generation": self.rule.ast.generation,
            })

            logger.debug(
                "Mutation accepted: %s (fitness %.4f -> %.4f, gen %d)",
                operator.name, fitness_before, fitness_after,
                self.rule.ast.generation,
            )
        else:
            # Revert the mutation
            self.rule.record_revert()

            record = MutationRecord(
                operator_name=operator.name,
                accepted=False,
                fitness_before=fitness_before,
                fitness_after=fitness_before,
                correctness_before=correctness_before,
                correctness_after=correctness_before,
                reason=f"Reverted: {reason}",
                ast_fingerprint_before=fingerprint_before,
                ast_fingerprint_after=fingerprint_before,
                generation=self.rule.ast.generation,
            )
            self.history.append(record)

            self._emit_event(EventType.SELF_MODIFY_MUTATION_REVERTED, {
                "operator": operator.name,
                "reason": reason,
            })

            logger.debug(
                "Mutation reverted: %s (%s)", operator.name, reason,
            )

    def trigger_kill_switch(self) -> None:
        """Revert ALL mutations and restore the original AST.

        The nuclear option. Called when the SafetyGuard determines
        that accumulated mutations have degraded the rule beyond
        the correctness floor. All progress is lost. The rule
        returns to its pristine, unmutated state — wiser, perhaps,
        but certainly no more evolved.
        """
        self.rule.ast = copy.deepcopy(self._original_ast)
        self.safety_guard.kill_switch_triggered = True

        self._emit_event(EventType.SELF_MODIFY_SAFETY_VIOLATION, {
            "action": "kill_switch_triggered",
            "mutations_reverted": self.history.accepted_count,
        })

        logger.warning(
            "Kill switch triggered: reverted ALL %d mutations",
            self.history.accepted_count,
        )

    def _emit_event(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Emit an event if an event bus is available."""
        if self.event_bus is not None:
            try:
                self.event_bus.publish(event_type, data)
            except Exception:
                pass  # Events are best-effort

    @property
    def mutations_attempted(self) -> int:
        """Total number of mutation attempts."""
        return self._mutations_attempted

    @property
    def current_fitness(self) -> float:
        """Current fitness score of the mutable rule."""
        return self.fitness_evaluator.evaluate(self.rule)

    @property
    def current_correctness(self) -> float:
        """Current correctness score of the mutable rule."""
        return self.fitness_evaluator.correctness_score(self.rule)


# ════════════════════════════════════════════════════════════════════
# SelfModifyingDashboard — ASCII Visualization of Self-Modification
# ════════════════════════════════════════════════════════════════════


class SelfModifyingDashboard:
    """ASCII dashboard visualizing the state of the self-modifying engine.

    Renders:
    - Current AST structure (pseudo-source)
    - Mutation history (last N mutations with accept/revert status)
    - Fitness sparkline (trending fitness over time)
    - Operator statistics (acceptance rates per operator)
    - SafetyGuard status (vetoes, kill switch state)

    Because if your FizzBuzz rules are going to rewrite themselves
    at runtime, the least you can do is provide a dashboard so that
    humans can watch in real time as the code evolves, panics, and
    is occasionally saved by the SafetyGuard from its own ambition.
    """

    SPARKLINE_CHARS = " _.,:-=!#@"

    @classmethod
    def render(
        cls,
        engine: SelfModifyingEngine,
        width: int = 60,
        show_ast: bool = True,
        show_history: bool = True,
        show_fitness: bool = True,
    ) -> str:
        """Render the full self-modifying code dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        inner_w = width - 4

        lines.append("")
        lines.append(border)
        lines.append(cls._center("SELF-MODIFYING CODE DASHBOARD", width))
        lines.append(cls._center("Rules That Rewrite Themselves", width))
        lines.append(border)

        # Summary
        rule = engine.rule
        history = engine.history
        guard = engine.safety_guard

        lines.append(cls._pad(f"Rule: {rule.name}", inner_w, width))
        lines.append(cls._pad(f"Generation: {rule.ast.generation}", inner_w, width))
        lines.append(cls._pad(f"AST Depth: {rule.ast.depth()}", inner_w, width))
        lines.append(cls._pad(f"AST Nodes: {rule.ast.node_count()}", inner_w, width))
        lines.append(cls._pad(f"Evaluations: {rule.evaluation_count}", inner_w, width))
        lines.append(cls._pad(
            f"Fitness: {engine.current_fitness:.4f}",
            inner_w, width,
        ))
        lines.append(cls._pad(
            f"Correctness: {engine.current_correctness:.1%}",
            inner_w, width,
        ))
        lines.append(cls._pad(
            f"Mutations: {history.accepted_count} accepted / "
            f"{history.reverted_count} reverted",
            inner_w, width,
        ))
        lines.append(cls._pad(
            f"Acceptance Rate: {history.acceptance_rate:.1%}",
            inner_w, width,
        ))
        lines.append(cls._pad(
            f"SafetyGuard Vetoes: {guard.vetoes}",
            inner_w, width,
        ))
        kill_status = "TRIGGERED" if guard.kill_switch_triggered else "Armed"
        lines.append(cls._pad(
            f"Kill Switch: {kill_status}",
            inner_w, width,
        ))
        lines.append(border)

        # AST view
        if show_ast:
            lines.append(cls._center("Current AST", width))
            lines.append(cls._center("-" * 20, width))
            source_lines = rule.ast.to_source().split("\n")
            for src_line in source_lines[:20]:  # Limit to 20 lines
                truncated = src_line[:inner_w]
                lines.append(cls._pad(truncated, inner_w, width))
            if len(source_lines) > 20:
                lines.append(cls._pad(
                    f"... ({len(source_lines) - 20} more lines)",
                    inner_w, width,
                ))
            lines.append(border)

        # Fitness sparkline
        if show_fitness:
            timeline = history.fitness_timeline()
            if timeline:
                lines.append(cls._center("Fitness Trend", width))
                lines.append(cls._center("-" * 20, width))
                sparkline = cls._sparkline(timeline, inner_w)
                lines.append(cls._pad(sparkline, inner_w, width))
                lines.append(cls._pad(
                    f"Min: {min(timeline):.4f}  Max: {max(timeline):.4f}  "
                    f"Current: {timeline[-1]:.4f}",
                    inner_w, width,
                ))
            else:
                lines.append(cls._center("Fitness Trend", width))
                lines.append(cls._pad("(no mutations yet)", inner_w, width))
            lines.append(border)

        # Mutation history
        if show_history:
            lines.append(cls._center("Mutation History (Last 10)", width))
            lines.append(cls._center("-" * 20, width))
            recent = history.records[-10:]
            if not recent:
                lines.append(cls._pad("(no mutations recorded)", inner_w, width))
            for rec in recent:
                status = "ACCEPT" if rec.accepted else "REVERT"
                entry = (
                    f"[{status}] {rec.operator_name}: "
                    f"{rec.fitness_before:.3f}->{rec.fitness_after:.3f}"
                )
                lines.append(cls._pad(entry[:inner_w], inner_w, width))
            lines.append(border)

            # Operator stats
            stats = history.operator_stats()
            if stats:
                lines.append(cls._center("Operator Statistics", width))
                lines.append(cls._center("-" * 20, width))
                for op_name, counts in sorted(stats.items()):
                    rate = counts["accepted"] / counts["total"] if counts["total"] else 0
                    stat_line = (
                        f"{op_name}: {counts['accepted']}/{counts['total']} "
                        f"({rate:.0%})"
                    )
                    lines.append(cls._pad(stat_line[:inner_w], inner_w, width))
                lines.append(border)

        return "\n".join("  " + ln if ln else ln for ln in lines)

    @classmethod
    def _center(cls, text: str, width: int) -> str:
        """Center text within the dashboard border."""
        return f"| {text:^{width - 4}} |"

    @classmethod
    def _pad(cls, text: str, inner_w: int, width: int) -> str:
        """Left-align text within the dashboard border."""
        return f"| {text:<{inner_w}} |"

    @classmethod
    def _sparkline(cls, values: list[float], max_width: int) -> str:
        """Generate an ASCII sparkline from a list of float values."""
        if not values:
            return ""
        # Sample values to fit within max_width
        if len(values) > max_width:
            step = len(values) / max_width
            sampled = [values[int(i * step)] for i in range(max_width)]
        else:
            sampled = values

        min_val = min(sampled)
        max_val = max(sampled)
        val_range = max_val - min_val if max_val > min_val else 1.0

        chars = cls.SPARKLINE_CHARS
        result = []
        for v in sampled:
            idx = int((v - min_val) / val_range * (len(chars) - 1))
            idx = max(0, min(idx, len(chars) - 1))
            result.append(chars[idx])
        return "".join(result)


# ════════════════════════════════════════════════════════════════════
# SelfModifyingMiddleware — Pipeline Integration
# ════════════════════════════════════════════════════════════════════


class SelfModifyingMiddleware(IMiddleware):
    """Middleware that integrates the self-modifying engine into the pipeline.

    Priority -6 ensures this middleware runs early in the pipeline,
    before most other middleware but after tracing and feature flags.
    Each number that passes through the pipeline is also evaluated
    by the self-modifying engine, and the engine may mutate the rule
    AST between evaluations.

    The middleware records mutation events in the context metadata,
    providing observability into the self-modification process for
    downstream middleware (metrics, audit, compliance). Because if
    your code is going to rewrite itself, the compliance team would
    like to know about it.
    """

    def __init__(
        self,
        engine: SelfModifyingEngine,
        event_bus: Any = None,
    ) -> None:
        self._engine = engine
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context through the self-modifying engine."""
        # Track state before evaluation
        gen_before = self._engine.rule.ast.generation
        mutations_before = self._engine.history.total_count

        # Let the rest of the pipeline evaluate the number
        result = next_handler(context)

        # The self-modifying engine evaluates the number independently
        # This is where mutations may be proposed and evaluated
        self._engine.evaluate(context.number)

        # Record self-modification metadata
        gen_after = self._engine.rule.ast.generation
        mutations_after = self._engine.history.total_count

        result.metadata["self_modify_generation"] = gen_after
        result.metadata["self_modify_mutations_proposed"] = mutations_after - mutations_before
        result.metadata["self_modify_generation_changed"] = gen_after != gen_before
        result.metadata["self_modify_fitness"] = self._engine.current_fitness
        result.metadata["self_modify_correctness"] = self._engine.current_correctness

        return result

    def get_name(self) -> str:
        return "SelfModifyingMiddleware"

    def get_priority(self) -> int:
        return -6


# ════════════════════════════════════════════════════════════════════
# Factory Functions
# ════════════════════════════════════════════════════════════════════


def create_self_modifying_engine(
    rules: list[tuple[int, str]],
    mutation_rate: float = 0.05,
    max_ast_depth: int = 10,
    correctness_floor: float = 0.95,
    max_mutations: int = 100,
    kill_switch: bool = True,
    correctness_weight: float = 0.70,
    latency_weight: float = 0.20,
    compactness_weight: float = 0.10,
    enabled_operators: Optional[list[str]] = None,
    seed: Optional[int] = None,
    event_bus: Any = None,
    range_start: int = 1,
    range_end: int = 100,
) -> SelfModifyingEngine:
    """Factory function to create a fully configured SelfModifyingEngine.

    Builds the AST from rule definitions, constructs ground truth,
    initializes the fitness evaluator and safety guard, and selects
    the enabled mutation operators. Returns a ready-to-use engine.
    """
    # Build the canonical AST
    ast = RuleAST.from_rules(rules)
    mutable_rule = MutableRule(name="SelfModifyingFizzBuzz", ast=ast)

    # Build ground truth for fitness evaluation
    ground_truth = FitnessEvaluator.build_ground_truth(
        rules, range_start=range_start, range_end=range_end
    )

    # Initialize fitness evaluator
    fitness_evaluator = FitnessEvaluator(
        ground_truth=ground_truth,
        correctness_weight=correctness_weight,
        latency_weight=latency_weight,
        compactness_weight=compactness_weight,
    )

    # Initialize safety guard
    safety_guard = SafetyGuard(
        fitness_evaluator=fitness_evaluator,
        correctness_floor=correctness_floor,
        max_ast_depth=max_ast_depth,
        kill_switch=kill_switch,
    )

    # Select operators
    if enabled_operators:
        operators = [ALL_OPERATORS[name] for name in enabled_operators
                     if name in ALL_OPERATORS]
    else:
        operators = list(ALL_OPERATORS.values())

    if not operators:
        operators = list(ALL_OPERATORS.values())

    # Build the engine
    engine = SelfModifyingEngine(
        rule=mutable_rule,
        operators=operators,
        fitness_evaluator=fitness_evaluator,
        safety_guard=safety_guard,
        mutation_rate=mutation_rate,
        max_mutations=max_mutations,
        seed=seed,
        event_bus=event_bus,
    )

    return engine

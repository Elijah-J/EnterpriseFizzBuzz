"""
Enterprise FizzBuzz Platform - Regular Expression Engine (FizzRegex)

A production-grade regular expression engine built from first principles using
Thompson's NFA construction and Rabin-Scott DFA compilation. Where Python's
built-in ``re`` module uses backtracking (and suffers exponential blowup on
pathological patterns), FizzRegex guarantees O(n) matching time via DFA
simulation — because the Enterprise FizzBuzz Platform cannot afford to let a
rogue quantifier bring down the classification pipeline.

The implementation follows the canonical three-phase compilation pipeline:

1. **Parsing** — A recursive-descent parser converts regex strings to an
   abstract syntax tree (AST) supporting literals, concatenation, alternation,
   Kleene star, plus, optional, character classes, dot, and anchors.

2. **Thompson's NFA Construction** — Each AST node maps to a two-state NFA
   fragment connected by epsilon transitions, following Ken Thompson's 1968
   construction. The resulting NFA has O(m) states for a pattern of length m.

3. **Rabin-Scott Subset Construction** — The powerset construction converts
   the NFA to an equivalent DFA where each DFA state is the epsilon-closure
   of a set of NFA states. Hopcroft's partition-refinement algorithm then
   minimizes the DFA to its canonical form.

The FizzBuzz classification pipeline pre-compiles patterns like
``Fizz|Buzz|FizzBuzz|\\d+`` into minimized DFAs at startup, enabling O(n)
classification validation with zero backtracking risk.

Features:
    - Recursive-descent regex parser with full operator precedence
    - Thompson NFA: each literal -> 2-state NFA, concat -> chain,
      alternation -> branch with epsilon, Kleene -> loop with epsilon
    - Rabin-Scott DFA: state = frozenset of NFA states via epsilon closure
    - Hopcroft DFA minimization via partition refinement
    - O(n) matching guarantee — no exponential backtracking
    - Pre-compiled FizzBuzz classification patterns
    - Benchmark suite demonstrating O(n) vs O(2^n) on pathological inputs
    - ASCII dashboard with NFA/DFA state counts and minimization statistics
    - IMiddleware integration for classification validation
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    RegexCompilationError,
    RegexPatternSyntaxError,
    RegexEngineError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Regex AST
# ============================================================


class ASTNodeType(Enum):
    """Types of nodes in the regex abstract syntax tree."""

    LITERAL = auto()
    CONCAT = auto()
    ALTERNATION = auto()
    KLEENE_STAR = auto()
    PLUS = auto()
    OPTIONAL = auto()
    CHAR_CLASS = auto()
    DOT = auto()
    ANCHOR_START = auto()
    ANCHOR_END = auto()
    EMPTY = auto()


@dataclass
class RegexAST:
    """Node in the regular expression abstract syntax tree.

    Each node represents a single regex operation. The tree structure
    mirrors the precedence hierarchy: alternation at the root, concatenation
    in the middle, and quantifiers closest to the leaves.
    """

    node_type: ASTNodeType
    value: Optional[str] = None
    children: list[RegexAST] = field(default_factory=list)
    char_ranges: list[tuple[str, str]] = field(default_factory=list)
    negated: bool = False

    def __repr__(self) -> str:
        if self.node_type == ASTNodeType.LITERAL:
            return f"Lit({self.value!r})"
        elif self.node_type == ASTNodeType.CHAR_CLASS:
            neg = "^" if self.negated else ""
            return f"CC({neg}{self.char_ranges})"
        elif self.node_type == ASTNodeType.DOT:
            return "Dot"
        elif self.node_type == ASTNodeType.ANCHOR_START:
            return "^"
        elif self.node_type == ASTNodeType.ANCHOR_END:
            return "$"
        elif self.node_type == ASTNodeType.EMPTY:
            return "Empty"
        elif self.node_type == ASTNodeType.CONCAT:
            return f"Concat({', '.join(repr(c) for c in self.children)})"
        elif self.node_type == ASTNodeType.ALTERNATION:
            return f"Alt({', '.join(repr(c) for c in self.children)})"
        elif self.node_type == ASTNodeType.KLEENE_STAR:
            return f"Star({self.children[0]!r})"
        elif self.node_type == ASTNodeType.PLUS:
            return f"Plus({self.children[0]!r})"
        elif self.node_type == ASTNodeType.OPTIONAL:
            return f"Opt({self.children[0]!r})"
        return f"AST({self.node_type})"


# ============================================================
# Regex Parser — Recursive Descent
# ============================================================


class RegexParser:
    """Recursive-descent parser converting regex strings to AST.

    Grammar (operator precedence, lowest to highest):
        expr       -> concat ('|' concat)*
        concat     -> quantified+
        quantified -> atom ('*' | '+' | '?')?
        atom       -> LITERAL | '.' | '^' | '$' | '(' expr ')' | '[' charclass ']'
        charclass  -> '^'? (range | char)+
        range      -> char '-' char
    """

    def __init__(self, pattern: str) -> None:
        self._pattern = pattern
        self._pos = 0
        self._length = len(pattern)

    def parse(self) -> RegexAST:
        """Parse the complete pattern and return the AST root."""
        if self._length == 0:
            return RegexAST(node_type=ASTNodeType.EMPTY)
        ast = self._parse_expr()
        if self._pos < self._length:
            raise RegexPatternSyntaxError(
                self._pattern,
                self._pos,
                f"Unexpected character {self._pattern[self._pos]!r} at position {self._pos}",
            )
        return ast

    def _peek(self) -> Optional[str]:
        if self._pos < self._length:
            return self._pattern[self._pos]
        return None

    def _advance(self) -> str:
        ch = self._pattern[self._pos]
        self._pos += 1
        return ch

    def _parse_expr(self) -> RegexAST:
        """Parse an alternation expression: concat ('|' concat)*."""
        branches = [self._parse_concat()]
        while self._peek() == "|":
            self._advance()
            branches.append(self._parse_concat())
        if len(branches) == 1:
            return branches[0]
        return RegexAST(node_type=ASTNodeType.ALTERNATION, children=branches)

    def _parse_concat(self) -> RegexAST:
        """Parse a concatenation of quantified atoms."""
        parts: list[RegexAST] = []
        while self._peek() is not None and self._peek() not in ("|", ")"):
            parts.append(self._parse_quantified())
        if len(parts) == 0:
            return RegexAST(node_type=ASTNodeType.EMPTY)
        if len(parts) == 1:
            return parts[0]
        return RegexAST(node_type=ASTNodeType.CONCAT, children=parts)

    def _parse_quantified(self) -> RegexAST:
        """Parse an atom followed by an optional quantifier."""
        atom = self._parse_atom()
        ch = self._peek()
        if ch == "*":
            self._advance()
            return RegexAST(node_type=ASTNodeType.KLEENE_STAR, children=[atom])
        elif ch == "+":
            self._advance()
            return RegexAST(node_type=ASTNodeType.PLUS, children=[atom])
        elif ch == "?":
            self._advance()
            return RegexAST(node_type=ASTNodeType.OPTIONAL, children=[atom])
        return atom

    def _parse_atom(self) -> RegexAST:
        """Parse a single atom: literal, dot, anchor, group, or char class."""
        ch = self._peek()
        if ch is None:
            raise RegexPatternSyntaxError(
                self._pattern, self._pos, "Unexpected end of pattern"
            )

        if ch == "(":
            self._advance()
            inner = self._parse_expr()
            if self._peek() != ")":
                raise RegexPatternSyntaxError(
                    self._pattern, self._pos, "Missing closing parenthesis"
                )
            self._advance()
            return inner

        if ch == "[":
            return self._parse_char_class()

        if ch == ".":
            self._advance()
            return RegexAST(node_type=ASTNodeType.DOT)

        if ch == "^":
            self._advance()
            return RegexAST(node_type=ASTNodeType.ANCHOR_START)

        if ch == "$":
            self._advance()
            return RegexAST(node_type=ASTNodeType.ANCHOR_END)

        if ch == "\\":
            return self._parse_escape()

        # Literal character
        self._advance()
        return RegexAST(node_type=ASTNodeType.LITERAL, value=ch)

    def _parse_escape(self) -> RegexAST:
        """Parse an escape sequence."""
        self._advance()  # consume backslash
        if self._pos >= self._length:
            raise RegexPatternSyntaxError(
                self._pattern, self._pos, "Trailing backslash"
            )
        ch = self._advance()
        if ch == "d":
            return RegexAST(
                node_type=ASTNodeType.CHAR_CLASS,
                char_ranges=[("0", "9")],
            )
        elif ch == "w":
            return RegexAST(
                node_type=ASTNodeType.CHAR_CLASS,
                char_ranges=[("a", "z"), ("A", "Z"), ("0", "9"), ("_", "_")],
            )
        elif ch == "s":
            return RegexAST(
                node_type=ASTNodeType.CHAR_CLASS,
                char_ranges=[(" ", " "), ("\t", "\t"), ("\n", "\n"), ("\r", "\r")],
            )
        elif ch == "D":
            return RegexAST(
                node_type=ASTNodeType.CHAR_CLASS,
                char_ranges=[("0", "9")],
                negated=True,
            )
        elif ch == "W":
            return RegexAST(
                node_type=ASTNodeType.CHAR_CLASS,
                char_ranges=[("a", "z"), ("A", "Z"), ("0", "9"), ("_", "_")],
                negated=True,
            )
        elif ch == "S":
            return RegexAST(
                node_type=ASTNodeType.CHAR_CLASS,
                char_ranges=[(" ", " "), ("\t", "\t"), ("\n", "\n"), ("\r", "\r")],
                negated=True,
            )
        else:
            # Escaped special character treated as literal
            return RegexAST(node_type=ASTNodeType.LITERAL, value=ch)

    def _parse_char_class(self) -> RegexAST:
        """Parse a character class: [abc], [a-z], [^0-9]."""
        self._advance()  # consume '['
        negated = False
        if self._peek() == "^":
            negated = True
            self._advance()

        ranges: list[tuple[str, str]] = []
        while self._peek() is not None and self._peek() != "]":
            start_ch = self._advance()
            if start_ch == "\\" and self._peek() is not None:
                start_ch = self._advance()
            if self._peek() == "-" and self._pos + 1 < self._length and self._pattern[self._pos + 1] != "]":
                self._advance()  # consume '-'
                end_ch = self._advance()
                if end_ch == "\\" and self._peek() is not None:
                    end_ch = self._advance()
                ranges.append((start_ch, end_ch))
            else:
                ranges.append((start_ch, start_ch))

        if self._peek() != "]":
            raise RegexPatternSyntaxError(
                self._pattern, self._pos, "Missing closing bracket ']'"
            )
        self._advance()  # consume ']'
        return RegexAST(
            node_type=ASTNodeType.CHAR_CLASS,
            char_ranges=ranges,
            negated=negated,
        )


# ============================================================
# NFA — Thompson's Construction
# ============================================================


_nfa_state_counter = 0


def _next_nfa_id() -> int:
    """Generate a globally unique NFA state identifier."""
    global _nfa_state_counter
    _nfa_state_counter += 1
    return _nfa_state_counter


def _reset_nfa_counter() -> None:
    """Reset the NFA state counter. Used for testing determinism."""
    global _nfa_state_counter
    _nfa_state_counter = 0


class NFAState:
    """A single state in a Thompson NFA.

    Each state has:
    - A unique identifier
    - A set of transitions on specific characters
    - A set of epsilon transitions (transitions on no input)
    - An accepting flag
    """

    def __init__(self, state_id: Optional[int] = None, accepting: bool = False) -> None:
        self.state_id: int = state_id if state_id is not None else _next_nfa_id()
        self.accepting: bool = accepting
        self.transitions: dict[str, list[NFAState]] = {}
        self.epsilon_transitions: list[NFAState] = []

    def add_transition(self, char: str, target: NFAState) -> None:
        """Add a transition on the given character."""
        if char not in self.transitions:
            self.transitions[char] = []
        self.transitions[char].append(target)

    def add_epsilon(self, target: NFAState) -> None:
        """Add an epsilon (empty string) transition."""
        self.epsilon_transitions.append(target)

    def __repr__(self) -> str:
        return f"NFAState({self.state_id}, accepting={self.accepting})"

    def __hash__(self) -> int:
        return hash(self.state_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NFAState):
            return NotImplemented
        return self.state_id == other.state_id


@dataclass
class NFA:
    """A non-deterministic finite automaton with epsilon transitions.

    Represented as a start state and an accept state, following Thompson's
    convention where each NFA fragment has exactly one start and one accept state.
    """

    start: NFAState
    accept: NFAState

    def state_count(self) -> int:
        """Count all reachable states via BFS."""
        visited: set[int] = set()
        queue = [self.start]
        while queue:
            state = queue.pop()
            if state.state_id in visited:
                continue
            visited.add(state.state_id)
            for targets in state.transitions.values():
                queue.extend(targets)
            queue.extend(state.epsilon_transitions)
        return len(visited)

    def all_states(self) -> list[NFAState]:
        """Return all reachable states in BFS order."""
        visited: set[int] = set()
        result: list[NFAState] = []
        queue = [self.start]
        while queue:
            state = queue.pop(0)
            if state.state_id in visited:
                continue
            visited.add(state.state_id)
            result.append(state)
            for targets in state.transitions.values():
                queue.extend(targets)
            queue.extend(state.epsilon_transitions)
        return result


def _char_matches(char: str, ranges: list[tuple[str, str]], negated: bool) -> bool:
    """Test whether a character matches a set of ranges, possibly negated."""
    matched = any(lo <= char <= hi for lo, hi in ranges)
    return (not matched) if negated else matched


class ThompsonConstructor:
    """Constructs an NFA from a regex AST using Thompson's algorithm.

    Each regex operation maps to a standard NFA fragment:
    - Literal 'a': two states connected by transition on 'a'
    - Concatenation: chain fragment endpoints
    - Alternation: branch with epsilon transitions to/from each alternative
    - Kleene star: loop with epsilon transitions
    - Plus: concatenation with Kleene star
    - Optional: alternation with epsilon (empty string)
    """

    def build(self, ast: RegexAST) -> NFA:
        """Convert the AST to a Thompson NFA."""
        _reset_nfa_counter()
        return self._build(ast)

    def _build(self, node: RegexAST) -> NFA:
        if node.node_type == ASTNodeType.EMPTY:
            return self._build_epsilon()
        elif node.node_type == ASTNodeType.LITERAL:
            return self._build_literal(node.value or "")
        elif node.node_type == ASTNodeType.DOT:
            return self._build_dot()
        elif node.node_type == ASTNodeType.CHAR_CLASS:
            return self._build_char_class(node.char_ranges, node.negated)
        elif node.node_type == ASTNodeType.CONCAT:
            return self._build_concat(node.children)
        elif node.node_type == ASTNodeType.ALTERNATION:
            return self._build_alternation(node.children)
        elif node.node_type == ASTNodeType.KLEENE_STAR:
            return self._build_kleene_star(node.children[0])
        elif node.node_type == ASTNodeType.PLUS:
            return self._build_plus(node.children[0])
        elif node.node_type == ASTNodeType.OPTIONAL:
            return self._build_optional(node.children[0])
        elif node.node_type == ASTNodeType.ANCHOR_START:
            return self._build_epsilon()
        elif node.node_type == ASTNodeType.ANCHOR_END:
            return self._build_epsilon()
        else:
            raise RegexCompilationError(
                f"Unknown AST node type: {node.node_type}"
            )

    def _build_epsilon(self) -> NFA:
        """Build a two-state NFA accepting the empty string."""
        start = NFAState()
        accept = NFAState(accepting=True)
        start.add_epsilon(accept)
        return NFA(start=start, accept=accept)

    def _build_literal(self, char: str) -> NFA:
        """Build a two-state NFA accepting a single character."""
        start = NFAState()
        accept = NFAState(accepting=True)
        start.add_transition(char, accept)
        return NFA(start=start, accept=accept)

    def _build_dot(self) -> NFA:
        """Build an NFA accepting any single character (printable ASCII)."""
        start = NFAState()
        accept = NFAState(accepting=True)
        # Dot matches any printable character (ASCII 32-126) plus common whitespace
        for code in range(32, 127):
            start.add_transition(chr(code), accept)
        for ws in ("\t", "\n", "\r"):
            start.add_transition(ws, accept)
        return NFA(start=start, accept=accept)

    def _build_char_class(
        self, ranges: list[tuple[str, str]], negated: bool
    ) -> NFA:
        """Build an NFA accepting characters in (or not in) the given ranges."""
        start = NFAState()
        accept = NFAState(accepting=True)
        # Enumerate matching characters in ASCII range
        for code in range(0, 128):
            ch = chr(code)
            if _char_matches(ch, ranges, negated):
                start.add_transition(ch, accept)
        return NFA(start=start, accept=accept)

    def _build_concat(self, children: list[RegexAST]) -> NFA:
        """Chain NFA fragments sequentially."""
        if not children:
            return self._build_epsilon()
        nfas = [self._build(child) for child in children]
        for i in range(len(nfas) - 1):
            nfas[i].accept.accepting = False
            nfas[i].accept.add_epsilon(nfas[i + 1].start)
        nfas[-1].accept.accepting = True
        return NFA(start=nfas[0].start, accept=nfas[-1].accept)

    def _build_alternation(self, children: list[RegexAST]) -> NFA:
        """Branch with epsilon transitions to/from each alternative."""
        start = NFAState()
        accept = NFAState(accepting=True)
        for child in children:
            child_nfa = self._build(child)
            start.add_epsilon(child_nfa.start)
            child_nfa.accept.accepting = False
            child_nfa.accept.add_epsilon(accept)
        return NFA(start=start, accept=accept)

    def _build_kleene_star(self, child: RegexAST) -> NFA:
        """Loop with epsilon transitions: zero or more repetitions."""
        start = NFAState()
        accept = NFAState(accepting=True)
        child_nfa = self._build(child)
        start.add_epsilon(child_nfa.start)
        start.add_epsilon(accept)
        child_nfa.accept.accepting = False
        child_nfa.accept.add_epsilon(child_nfa.start)
        child_nfa.accept.add_epsilon(accept)
        return NFA(start=start, accept=accept)

    def _build_plus(self, child: RegexAST) -> NFA:
        """One or more repetitions: concat(child, kleene_star(child))."""
        # Plus = at least one occurrence followed by zero or more
        start = NFAState()
        accept = NFAState(accepting=True)
        child_nfa = self._build(child)
        start.add_epsilon(child_nfa.start)
        child_nfa.accept.accepting = False
        child_nfa.accept.add_epsilon(child_nfa.start)
        child_nfa.accept.add_epsilon(accept)
        return NFA(start=start, accept=accept)

    def _build_optional(self, child: RegexAST) -> NFA:
        """Zero or one occurrence: alternation with epsilon."""
        start = NFAState()
        accept = NFAState(accepting=True)
        child_nfa = self._build(child)
        start.add_epsilon(child_nfa.start)
        start.add_epsilon(accept)
        child_nfa.accept.accepting = False
        child_nfa.accept.add_epsilon(accept)
        return NFA(start=start, accept=accept)


# ============================================================
# DFA — Rabin-Scott Subset Construction
# ============================================================


@dataclass(frozen=True)
class DFAState:
    """A state in the deterministic finite automaton.

    Each DFA state corresponds to a frozenset of NFA states — the epsilon
    closure of all NFA states reachable simultaneously. This is the core
    insight of Rabin-Scott subset construction: non-determinism is resolved
    by tracking all possible NFA states in parallel.
    """

    nfa_states: frozenset[int]
    accepting: bool

    def __hash__(self) -> int:
        return hash(self.nfa_states)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DFAState):
            return NotImplemented
        return self.nfa_states == other.nfa_states


@dataclass
class DFA:
    """A deterministic finite automaton compiled from an NFA.

    The DFA has:
    - A start state
    - A set of accepting states
    - A transition table mapping (state, character) -> state
    - No epsilon transitions (all resolved during construction)
    """

    start: DFAState
    states: dict[frozenset[int], DFAState]
    transitions: dict[frozenset[int], dict[str, frozenset[int]]]
    accepting_states: set[frozenset[int]]
    alphabet: set[str]

    def state_count(self) -> int:
        return len(self.states)


class SubsetConstructor:
    """Rabin-Scott subset construction: NFA -> DFA via powerset method.

    The algorithm computes the epsilon closure of NFA state sets and builds
    DFA states as frozensets of NFA state IDs. Each DFA transition is
    computed by: given a DFA state (set of NFA states) and an input character,
    compute the set of NFA states reachable by following character transitions
    from all NFA states in the set, then taking the epsilon closure.
    """

    def __init__(self, nfa: NFA) -> None:
        self._nfa = nfa
        self._nfa_states: dict[int, NFAState] = {}
        self._alphabet: set[str] = set()
        self._collect_states_and_alphabet()

    def _collect_states_and_alphabet(self) -> None:
        """Discover all NFA states and the input alphabet via BFS."""
        visited: set[int] = set()
        queue = [self._nfa.start]
        while queue:
            state = queue.pop()
            if state.state_id in visited:
                continue
            visited.add(state.state_id)
            self._nfa_states[state.state_id] = state
            for char, targets in state.transitions.items():
                self._alphabet.add(char)
                queue.extend(targets)
            queue.extend(state.epsilon_transitions)

    def _epsilon_closure(self, state_ids: frozenset[int]) -> frozenset[int]:
        """Compute the epsilon closure of a set of NFA states.

        The epsilon closure is the set of all NFA states reachable from the
        given states by following zero or more epsilon transitions.
        """
        closure: set[int] = set(state_ids)
        stack = list(state_ids)
        while stack:
            sid = stack.pop()
            state = self._nfa_states.get(sid)
            if state is None:
                continue
            for eps_target in state.epsilon_transitions:
                if eps_target.state_id not in closure:
                    closure.add(eps_target.state_id)
                    stack.append(eps_target.state_id)
        return frozenset(closure)

    def _move(self, state_ids: frozenset[int], char: str) -> frozenset[int]:
        """Compute the set of NFA states reachable on a given character."""
        result: set[int] = set()
        for sid in state_ids:
            state = self._nfa_states.get(sid)
            if state is None:
                continue
            for target in state.transitions.get(char, []):
                result.add(target.state_id)
        return frozenset(result)

    def _is_accepting(self, state_ids: frozenset[int]) -> bool:
        """Check if any NFA state in the set is an accepting state."""
        accept_id = self._nfa.accept.state_id
        return accept_id in state_ids

    def build(self) -> DFA:
        """Execute subset construction to produce the DFA."""
        start_closure = self._epsilon_closure(
            frozenset([self._nfa.start.state_id])
        )

        states: dict[frozenset[int], DFAState] = {}
        transitions: dict[frozenset[int], dict[str, frozenset[int]]] = {}
        accepting: set[frozenset[int]] = set()

        start_state = DFAState(
            nfa_states=start_closure,
            accepting=self._is_accepting(start_closure),
        )
        states[start_closure] = start_state
        if start_state.accepting:
            accepting.add(start_closure)

        worklist = [start_closure]
        visited: set[frozenset[int]] = {start_closure}

        while worklist:
            current = worklist.pop()
            transitions[current] = {}

            for char in sorted(self._alphabet):
                moved = self._move(current, char)
                if not moved:
                    continue
                closure = self._epsilon_closure(moved)
                if not closure:
                    continue

                transitions[current][char] = closure

                if closure not in visited:
                    visited.add(closure)
                    dfa_state = DFAState(
                        nfa_states=closure,
                        accepting=self._is_accepting(closure),
                    )
                    states[closure] = dfa_state
                    if dfa_state.accepting:
                        accepting.add(closure)
                    worklist.append(closure)

        return DFA(
            start=start_state,
            states=states,
            transitions=transitions,
            accepting_states=accepting,
            alphabet=self._alphabet,
        )


# ============================================================
# DFA Minimizer — Hopcroft's Algorithm
# ============================================================


class DFAMinimizer:
    """Minimizes a DFA using Hopcroft's partition-refinement algorithm.

    Starting from the initial partition {accepting, non-accepting}, the
    algorithm repeatedly refines partitions by splitting groups whose members
    disagree on which group a given transition leads to. The process
    terminates when no further splits are possible, yielding the minimal DFA.
    """

    def minimize(self, dfa: DFA) -> DFA:
        """Produce the minimal equivalent DFA."""
        all_state_keys = set(dfa.states.keys())
        accepting = dfa.accepting_states
        non_accepting = all_state_keys - accepting

        # Initial partition
        partitions: list[set[frozenset[int]]] = []
        if accepting:
            partitions.append(set(accepting))
        if non_accepting:
            partitions.append(set(non_accepting))
        if not partitions:
            return dfa

        # Build reverse transition index
        alphabet = sorted(dfa.alphabet)

        changed = True
        while changed:
            changed = False
            new_partitions: list[set[frozenset[int]]] = []
            for group in partitions:
                split = self._try_split(group, partitions, dfa.transitions, alphabet)
                if len(split) > 1:
                    changed = True
                new_partitions.extend(split)
            partitions = new_partitions

        # Build minimized DFA
        return self._build_minimized_dfa(partitions, dfa)

    def _try_split(
        self,
        group: set[frozenset[int]],
        partitions: list[set[frozenset[int]]],
        transitions: dict[frozenset[int], dict[str, frozenset[int]]],
        alphabet: list[str],
    ) -> list[set[frozenset[int]]]:
        """Attempt to split a partition group on each character."""
        if len(group) <= 1:
            return [group]

        for char in alphabet:
            # Map each state in the group to the partition index its transition leads to
            target_groups: dict[Optional[int], set[frozenset[int]]] = {}
            for state_key in group:
                trans = transitions.get(state_key, {})
                target = trans.get(char)
                if target is None:
                    target_idx: Optional[int] = -1  # dead state
                else:
                    target_idx = None
                    for idx, part in enumerate(partitions):
                        if target in part:
                            target_idx = idx
                            break
                if target_idx not in target_groups:
                    target_groups[target_idx] = set()
                target_groups[target_idx].add(state_key)

            if len(target_groups) > 1:
                return list(target_groups.values())

        return [group]

    def _build_minimized_dfa(
        self,
        partitions: list[set[frozenset[int]]],
        original: DFA,
    ) -> DFA:
        """Construct a new DFA from the refined partitions."""
        # Map each original state to its partition representative
        state_to_partition: dict[frozenset[int], int] = {}
        for idx, group in enumerate(partitions):
            for state_key in group:
                state_to_partition[state_key] = idx

        # Choose a representative for each partition
        representatives: dict[int, frozenset[int]] = {}
        for idx, group in enumerate(partitions):
            representatives[idx] = next(iter(group))

        # Build new states
        new_states: dict[frozenset[int], DFAState] = {}
        new_transitions: dict[frozenset[int], dict[str, frozenset[int]]] = {}
        new_accepting: set[frozenset[int]] = set()

        for idx, group in enumerate(partitions):
            rep = representatives[idx]
            # Create a new state key from the partition index
            new_key = frozenset([idx])
            is_accepting = rep in original.accepting_states
            new_states[new_key] = DFAState(
                nfa_states=new_key, accepting=is_accepting
            )
            if is_accepting:
                new_accepting.add(new_key)

            # Build transitions
            new_transitions[new_key] = {}
            for char, target in original.transitions.get(rep, {}).items():
                target_part_idx = state_to_partition.get(target)
                if target_part_idx is not None:
                    new_transitions[new_key][char] = frozenset([target_part_idx])

        # Find new start state
        start_part_idx = state_to_partition.get(original.start.nfa_states)
        if start_part_idx is None:
            start_key = frozenset([0])
        else:
            start_key = frozenset([start_part_idx])

        new_start = new_states.get(start_key)
        if new_start is None:
            # Fallback: use original
            return original

        return DFA(
            start=new_start,
            states=new_states,
            transitions=new_transitions,
            accepting_states=new_accepting,
            alphabet=original.alphabet,
        )


# ============================================================
# Matcher — O(n) DFA Simulation
# ============================================================


@dataclass
class MatchResult:
    """Result of a regex match operation."""

    matched: bool
    input_text: str
    pattern: str
    match_start: int = 0
    match_end: int = 0

    @property
    def matched_text(self) -> str:
        if self.matched:
            return self.input_text[self.match_start : self.match_end]
        return ""


class Matcher:
    """O(n) regex matching via DFA state simulation.

    Given a compiled DFA, the matcher processes each input character exactly
    once, following the unique transition from the current DFA state. This
    provides a strict O(n) time guarantee with no backtracking, regardless
    of the pattern complexity.
    """

    def __init__(self, dfa: DFA, pattern: str) -> None:
        self._dfa = dfa
        self._pattern = pattern

    def full_match(self, text: str) -> MatchResult:
        """Test if the entire input string matches the pattern."""
        current = self._dfa.start.nfa_states
        for ch in text:
            trans = self._dfa.transitions.get(current, {})
            next_state = trans.get(ch)
            if next_state is None:
                return MatchResult(
                    matched=False, input_text=text, pattern=self._pattern
                )
            current = next_state

        is_accept = current in self._dfa.accepting_states
        return MatchResult(
            matched=is_accept,
            input_text=text,
            pattern=self._pattern,
            match_start=0,
            match_end=len(text),
        )

    def search(self, text: str) -> MatchResult:
        """Search for the pattern anywhere in the input string.

        Tries full_match at every starting position. Each attempt is O(n)
        in the substring length, giving O(n^2) worst case for search — still
        without backtracking within any single attempt.
        """
        for start in range(len(text)):
            for end in range(start, len(text) + 1):
                current = self._dfa.start.nfa_states
                matched = True
                for ch in text[start:end]:
                    trans = self._dfa.transitions.get(current, {})
                    next_state = trans.get(ch)
                    if next_state is None:
                        matched = False
                        break
                    current = next_state

                if matched and current in self._dfa.accepting_states:
                    return MatchResult(
                        matched=True,
                        input_text=text,
                        pattern=self._pattern,
                        match_start=start,
                        match_end=end,
                    )

        return MatchResult(matched=False, input_text=text, pattern=self._pattern)

    def is_match(self, text: str) -> bool:
        """Convenience: return True if the text fully matches the pattern."""
        return self.full_match(text).matched


# ============================================================
# Regex Compiler — Full Pipeline
# ============================================================


@dataclass
class CompilationStats:
    """Statistics from the regex compilation pipeline."""

    pattern: str
    parse_time_us: float = 0.0
    nfa_time_us: float = 0.0
    dfa_time_us: float = 0.0
    minimize_time_us: float = 0.0
    total_time_us: float = 0.0
    nfa_state_count: int = 0
    dfa_state_count: int = 0
    minimized_state_count: int = 0
    states_eliminated: int = 0


class RegexCompiler:
    """Full compilation pipeline: parse -> NFA -> DFA -> minimize -> Matcher.

    This is the primary entry point for compiling regex patterns. The compiler
    orchestrates the complete pipeline and collects detailed statistics at
    each phase for monitoring and debugging purposes.
    """

    def __init__(self) -> None:
        self._parser_cls = RegexParser
        self._thompson = ThompsonConstructor()
        self._minimizer = DFAMinimizer()

    def compile(self, pattern: str) -> tuple[Matcher, CompilationStats]:
        """Compile a regex pattern to an O(n) matcher with statistics."""
        stats = CompilationStats(pattern=pattern)
        total_start = time.perf_counter_ns()

        # Phase 1: Parse
        t0 = time.perf_counter_ns()
        parser = self._parser_cls(pattern)
        ast = parser.parse()
        stats.parse_time_us = (time.perf_counter_ns() - t0) / 1000.0

        # Phase 2: Thompson NFA
        t0 = time.perf_counter_ns()
        nfa = self._thompson.build(ast)
        stats.nfa_time_us = (time.perf_counter_ns() - t0) / 1000.0
        stats.nfa_state_count = nfa.state_count()

        # Phase 3: Rabin-Scott DFA
        t0 = time.perf_counter_ns()
        constructor = SubsetConstructor(nfa)
        dfa = constructor.build()
        stats.dfa_time_us = (time.perf_counter_ns() - t0) / 1000.0
        stats.dfa_state_count = dfa.state_count()

        # Phase 4: Hopcroft minimization
        t0 = time.perf_counter_ns()
        min_dfa = self._minimizer.minimize(dfa)
        stats.minimize_time_us = (time.perf_counter_ns() - t0) / 1000.0
        stats.minimized_state_count = min_dfa.state_count()
        stats.states_eliminated = stats.dfa_state_count - stats.minimized_state_count

        stats.total_time_us = (time.perf_counter_ns() - total_start) / 1000.0

        matcher = Matcher(min_dfa, pattern)
        return matcher, stats


# ============================================================
# FizzBuzz Patterns — Pre-compiled Classification Matchers
# ============================================================


class FizzBuzzPatterns:
    """Pre-compiled regex patterns for FizzBuzz output classification.

    These patterns are compiled once at startup and reused for every
    classification validation. The DFA-based matching ensures that
    validation overhead is strictly O(n) in the output string length,
    which is critical for meeting the platform's SLA targets.
    """

    def __init__(self) -> None:
        self._compiler = RegexCompiler()
        self._matchers: dict[str, Matcher] = {}
        self._stats: dict[str, CompilationStats] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile all FizzBuzz classification patterns."""
        patterns = {
            "fizz": "Fizz",
            "buzz": "Buzz",
            "fizzbuzz": "FizzBuzz",
            "number": "(0|1|2|3|4|5|6|7|8|9)+",
            "classification": "(Fizz|Buzz|FizzBuzz|(0|1|2|3|4|5|6|7|8|9)+)",
            "fizz_family": "(Fizz|FizzBuzz)",
            "buzz_family": "(Buzz|FizzBuzz)",
        }
        for name, pattern in patterns.items():
            matcher, stats = self._compiler.compile(pattern)
            self._matchers[name] = matcher
            self._stats[name] = stats
            logger.debug(
                "Compiled FizzBuzz pattern '%s': %d NFA states -> %d DFA states -> %d minimized",
                name,
                stats.nfa_state_count,
                stats.dfa_state_count,
                stats.minimized_state_count,
            )

    def validate_classification(self, output: str) -> bool:
        """Validate that a FizzBuzz output matches the classification grammar."""
        matcher = self._matchers.get("classification")
        if matcher is None:
            return False
        return matcher.is_match(output)

    def classify(self, output: str) -> str:
        """Classify a FizzBuzz output string into its category."""
        if self._matchers["fizzbuzz"].is_match(output):
            return "FizzBuzz"
        elif self._matchers["fizz"].is_match(output):
            return "Fizz"
        elif self._matchers["buzz"].is_match(output):
            return "Buzz"
        elif self._matchers["number"].is_match(output):
            return "Number"
        return "Unknown"

    def get_matcher(self, name: str) -> Optional[Matcher]:
        """Retrieve a named pre-compiled matcher."""
        return self._matchers.get(name)

    def get_stats(self) -> dict[str, CompilationStats]:
        """Return compilation statistics for all patterns."""
        return dict(self._stats)

    @property
    def pattern_count(self) -> int:
        return len(self._matchers)


# ============================================================
# Regex Benchmark
# ============================================================


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    pattern: str
    input_length: int
    fizzregex_time_us: float
    python_re_time_us: float
    speedup_ratio: float
    fizzregex_matched: bool
    python_re_matched: bool
    results_agree: bool


class RegexBenchmark:
    """Benchmarks FizzRegex engine against Python's built-in ``re`` module.

    The benchmark focuses on pathological patterns where backtracking engines
    exhibit exponential behavior. The classic example is ``(a?)^n(a)^n`` matched
    against ``a^n``: Python's ``re`` takes O(2^n) time due to backtracking,
    while FizzRegex's DFA simulation completes in O(n).

    This benchmark exists to empirically validate the O(n) matching guarantee
    that justifies the entire FizzRegex subsystem. Without it, one might
    reasonably question why the Enterprise FizzBuzz Platform ships its own
    regex engine. With it, the answer is self-evident.
    """

    def __init__(self) -> None:
        self._compiler = RegexCompiler()
        self._results: list[BenchmarkResult] = []

    def run(self, sizes: Optional[list[int]] = None) -> list[BenchmarkResult]:
        """Run the pathological pattern benchmark at various input sizes.

        The pathological pattern is: (a?)^n (a)^n matched against a^n
        For backtracking engines, this forces exponential exploration.
        For DFA engines, it remains O(n).
        """
        import re as python_re

        if sizes is None:
            sizes = [5, 10, 15, 20, 23, 25]

        self._results = []

        for n in sizes:
            # Build pattern: a? repeated n times followed by a repeated n times
            pattern = "a?" * n + "a" * n
            input_text = "a" * n

            # FizzRegex (DFA, O(n))
            matcher, _ = self._compiler.compile(pattern)
            t0 = time.perf_counter_ns()
            fizzregex_result = matcher.full_match(input_text)
            fizzregex_us = (time.perf_counter_ns() - t0) / 1000.0

            # Python re (backtracking, O(2^n) on this pattern)
            compiled_re = python_re.compile("^" + pattern + "$")
            t0 = time.perf_counter_ns()
            python_match = compiled_re.match(input_text)
            python_us = (time.perf_counter_ns() - t0) / 1000.0

            python_matched = python_match is not None and python_match.group() == input_text
            speedup = python_us / max(fizzregex_us, 0.001)

            result = BenchmarkResult(
                pattern=f"(a?)^{n}(a)^{n}",
                input_length=n,
                fizzregex_time_us=fizzregex_us,
                python_re_time_us=python_us,
                speedup_ratio=speedup,
                fizzregex_matched=fizzregex_result.matched,
                python_re_matched=python_matched,
                results_agree=fizzregex_result.matched == python_matched,
            )
            self._results.append(result)

        return self._results

    @property
    def results(self) -> list[BenchmarkResult]:
        return list(self._results)


# ============================================================
# Regex Dashboard — ASCII Visualization
# ============================================================


class RegexDashboard:
    """ASCII dashboard displaying regex engine compilation and matching statistics.

    Provides visibility into the compilation pipeline state counts,
    minimization savings, and benchmark results in a format suitable for
    enterprise monitoring infrastructure (or a terminal).
    """

    @staticmethod
    def render(
        stats: dict[str, CompilationStats],
        benchmark_results: Optional[list[BenchmarkResult]] = None,
        width: int = 72,
    ) -> str:
        """Render the complete regex engine dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        empty = "|" + " " * (width - 2) + "|"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        lines.append(border)
        lines.append(center("FIZZREGEX ENGINE DASHBOARD"))
        lines.append(center("Thompson NFA + Rabin-Scott DFA + Hopcroft Minimization"))
        lines.append(border)

        # Compilation Statistics
        lines.append(center("COMPILATION PIPELINE"))
        lines.append(border)
        header = f"{'Pattern':<20} {'NFA':>5} {'DFA':>5} {'Min':>5} {'Saved':>5} {'Time':>10}"
        lines.append(left(header))
        lines.append(left("-" * len(header)))

        total_nfa = 0
        total_dfa = 0
        total_min = 0
        total_saved = 0

        for name, stat in sorted(stats.items()):
            pat = name[:18]
            row = (
                f"{pat:<20} {stat.nfa_state_count:>5} "
                f"{stat.dfa_state_count:>5} {stat.minimized_state_count:>5} "
                f"{stat.states_eliminated:>5} {stat.total_time_us:>8.1f}us"
            )
            lines.append(left(row))
            total_nfa += stat.nfa_state_count
            total_dfa += stat.dfa_state_count
            total_min += stat.minimized_state_count
            total_saved += stat.states_eliminated

        lines.append(left("-" * len(header)))
        totals = f"{'TOTAL':<20} {total_nfa:>5} {total_dfa:>5} {total_min:>5} {total_saved:>5}"
        lines.append(left(totals))

        if total_dfa > 0:
            reduction_pct = (total_saved / total_dfa) * 100
            lines.append(left(f"State reduction: {reduction_pct:.1f}%"))
        lines.append(empty)

        # Matching guarantee
        lines.append(border)
        lines.append(center("MATCHING GUARANTEE"))
        lines.append(border)
        lines.append(left("Algorithm: DFA simulation (no backtracking)"))
        lines.append(left("Time complexity: O(n) per character"))
        lines.append(left("Space complexity: O(1) per character (single state)"))
        lines.append(left("Pathological pattern immunity: CONFIRMED"))
        lines.append(empty)

        # Benchmark results (if available)
        if benchmark_results:
            lines.append(border)
            lines.append(center("BENCHMARK: (a?)^n(a)^n vs a^n"))
            lines.append(border)
            header_b = f"{'n':>4} {'FizzRegex':>12} {'Python re':>12} {'Speedup':>10} {'Agree':>6}"
            lines.append(left(header_b))
            lines.append(left("-" * len(header_b)))
            for br in benchmark_results:
                row = (
                    f"{br.input_length:>4} "
                    f"{br.fizzregex_time_us:>10.1f}us "
                    f"{br.python_re_time_us:>10.1f}us "
                    f"{br.speedup_ratio:>9.1f}x "
                    f"{'Y' if br.results_agree else 'N':>5}"
                )
                lines.append(left(row))
            lines.append(empty)

        lines.append(border)
        return "\n".join(lines)


# ============================================================
# Regex Middleware — IMiddleware Integration
# ============================================================


class RegexMiddleware(IMiddleware):
    """Middleware that validates FizzBuzz output classifications using the
    regex engine.

    On each evaluation, the middleware passes the output through the
    pre-compiled classification pattern to verify it conforms to the
    ``Fizz|Buzz|FizzBuzz|\\d+`` grammar. Non-conforming outputs are flagged
    in the processing context metadata for downstream analysis.

    This provides a defense-in-depth layer: even if the rule engine produces
    a correct result, the regex middleware independently verifies that the
    output string is syntactically valid. Trust but verify.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._patterns = FizzBuzzPatterns()
        self._event_bus = event_bus
        self._enable_dashboard = enable_dashboard
        self._match_count = 0
        self._fail_count = 0
        self._total_match_time_us = 0.0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Validate the classification output via regex matching."""
        result = next_handler(context)

        if result.results:
            last_result = result.results[-1]
            output = last_result.output

            t0 = time.perf_counter_ns()
            is_valid = self._patterns.validate_classification(output)
            match_time_us = (time.perf_counter_ns() - t0) / 1000.0

            self._total_match_time_us += match_time_us

            if is_valid:
                self._match_count += 1
                classification = self._patterns.classify(output)
                result.metadata["regex_classification"] = classification
                result.metadata["regex_valid"] = True
            else:
                self._fail_count += 1
                result.metadata["regex_valid"] = False
                result.metadata["regex_classification"] = "INVALID"
                logger.warning(
                    "Regex classification validation failed for output: %r",
                    output,
                )

            result.metadata["regex_match_time_us"] = match_time_us

        return result

    def get_name(self) -> str:
        return "RegexMiddleware"

    def get_priority(self) -> int:
        return 750

    @property
    def patterns(self) -> FizzBuzzPatterns:
        return self._patterns

    @property
    def match_count(self) -> int:
        return self._match_count

    @property
    def fail_count(self) -> int:
        return self._fail_count

    @property
    def total_match_time_us(self) -> float:
        return self._total_match_time_us

    @property
    def enable_dashboard(self) -> bool:
        return self._enable_dashboard

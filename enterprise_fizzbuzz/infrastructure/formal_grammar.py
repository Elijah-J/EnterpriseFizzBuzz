"""
Enterprise FizzBuzz Platform -- FizzGrammar: Formal Grammar & Parser Generator

Provides BNF/EBNF grammar specification, FIRST/FOLLOW set computation,
LL(1) classification, left-recursion detection, ambiguity analysis,
and a parser generator that compiles grammars to recursive-descent
parsers producing typed AST nodes.

Noam Chomsky formalized the theory of formal grammars in 1956.  Seventy
years later, the Enterprise FizzBuzz Platform finally applies it --
because a parser without a grammar is a function without a specification,
and the FizzBuzz evaluation pipeline deserves nothing less than
grammar-driven correctness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    GrammarConflictError,
    GrammarError,
    GrammarParseError,
    GrammarSyntaxError,
)

# ============================================================
# Sentinel constants
# ============================================================

EPSILON = "ε"
EOF = "$"


# ============================================================
# Symbol types
# ============================================================


class SymbolKind(Enum):
    """Classification of grammar symbols."""

    TERMINAL = auto()
    NON_TERMINAL = auto()
    EPSILON = auto()


@dataclass(frozen=True)
class Symbol:
    """A grammar symbol -- terminal or non-terminal."""

    name: str
    kind: SymbolKind

    def __repr__(self) -> str:
        return self.name

    @property
    def is_terminal(self) -> bool:
        return self.kind == SymbolKind.TERMINAL

    @property
    def is_non_terminal(self) -> bool:
        return self.kind == SymbolKind.NON_TERMINAL

    @property
    def is_epsilon(self) -> bool:
        return self.kind == SymbolKind.EPSILON


def terminal(name: str) -> Symbol:
    """Create a terminal symbol."""
    return Symbol(name, SymbolKind.TERMINAL)


def non_terminal(name: str) -> Symbol:
    """Create a non-terminal symbol."""
    return Symbol(name, SymbolKind.NON_TERMINAL)


def epsilon() -> Symbol:
    """Create the epsilon (empty string) symbol."""
    return Symbol(EPSILON, SymbolKind.EPSILON)


# ============================================================
# Production rules
# ============================================================


@dataclass
class Production:
    """A single production rule: lhs -> rhs (sequence of symbols).

    Each production represents one alternative for a non-terminal.
    Multiple productions with the same LHS represent alternatives
    (i.e., ``A ::= alpha | beta`` becomes two Production objects).
    """

    lhs: Symbol
    rhs: list[Symbol]
    label: str = ""

    def __repr__(self) -> str:
        rhs_str = " ".join(repr(s) for s in self.rhs) if self.rhs else EPSILON
        tag = f"  [{self.label}]" if self.label else ""
        return f"{self.lhs} ::= {rhs_str}{tag}"

    @property
    def is_epsilon(self) -> bool:
        """True if this production derives the empty string."""
        return len(self.rhs) == 0 or (
            len(self.rhs) == 1 and self.rhs[0].is_epsilon
        )


# ============================================================
# Grammar
# ============================================================


@dataclass
class Grammar:
    """A context-free grammar: a set of productions with a start symbol.

    The Grammar object is the central data structure of FizzGrammar.
    It holds all productions, indexes them by LHS non-terminal, and
    identifies the terminal and non-terminal vocabularies.
    """

    name: str
    productions: list[Production] = field(default_factory=list)
    start_symbol: Optional[Symbol] = None

    def __post_init__(self) -> None:
        self._index: dict[str, list[Production]] = {}
        for p in self.productions:
            self._index.setdefault(p.lhs.name, []).append(p)

    def add_production(self, prod: Production) -> None:
        """Add a production rule to the grammar."""
        self.productions.append(prod)
        self._index.setdefault(prod.lhs.name, []).append(prod)

    def productions_for(self, name: str) -> list[Production]:
        """Get all productions for a given non-terminal name."""
        return self._index.get(name, [])

    @property
    def non_terminals(self) -> set[str]:
        """All non-terminal names appearing as LHS of some production."""
        return {p.lhs.name for p in self.productions}

    @property
    def terminals(self) -> set[str]:
        """All terminal names referenced in production RHS."""
        terms: set[str] = set()
        for p in self.productions:
            for s in p.rhs:
                if s.is_terminal:
                    terms.add(s.name)
        return terms

    @property
    def all_symbols(self) -> set[str]:
        """All symbol names (terminals + non-terminals)."""
        return self.terminals | self.non_terminals

    def statistics(self) -> dict[str, Any]:
        """Compute grammar statistics."""
        return {
            "name": self.name,
            "terminals": len(self.terminals),
            "non_terminals": len(self.non_terminals),
            "productions": len(self.productions),
            "start_symbol": self.start_symbol.name if self.start_symbol else None,
        }


# ============================================================
# BNF / EBNF Parser  (parses grammar specifications)
# ============================================================


class GrammarParser:
    """Parses a BNF/EBNF grammar specification string into a Grammar.

    Supported syntax:
        non_terminal ::= sym1 sym2 | sym3 sym4 ;
    Terminals are quoted strings (``"KEYWORD"``) or ALL-CAPS identifiers.
    Non-terminals are lowercase identifiers.
    EBNF extensions: ``{ ... }`` (zero-or-more), ``[ ... ]`` (optional).
    """

    # Token patterns for the meta-grammar
    _TOKEN_PATTERNS = [
        ("DERIVES", r"::="),
        ("SEMICOLON", r";"),
        ("PIPE", r"\|"),
        ("LBRACE", r"\{"),
        ("RBRACE", r"\}"),
        ("LBRACKET", r"\["),
        ("RBRACKET", r"\]"),
        ("LPAREN", r"\("),
        ("RPAREN", r"\)"),
        ("STRING", r'"[^"]*"'),
        ("IDENT", r"[A-Za-z_][A-Za-z_0-9]*"),
        ("SKIP", r"[ \t]+"),
        ("NEWLINE", r"\n"),
        ("COMMENT", r"#[^\n]*"),
    ]

    _META_RE = re.compile(
        "|".join(f"(?P<{name}>{pat})" for name, pat in _TOKEN_PATTERNS)
    )

    def __init__(self) -> None:
        self._tokens: list[tuple[str, str, int, int]] = []
        self._pos: int = 0

    def parse(self, text: str, name: str = "grammar") -> Grammar:
        """Parse a BNF/EBNF specification into a Grammar object."""
        self._tokenize(text)
        self._pos = 0
        grammar = Grammar(name=name)
        while self._pos < len(self._tokens):
            prod_list = self._parse_rule()
            for prod in prod_list:
                grammar.add_production(prod)
        if grammar.productions and grammar.start_symbol is None:
            grammar.start_symbol = grammar.productions[0].lhs
        return grammar

    def _tokenize(self, text: str) -> None:
        self._tokens = []
        line = 1
        col = 1
        for m in self._META_RE.finditer(text):
            kind = m.lastgroup
            value = m.group()
            if kind == "NEWLINE":
                line += 1
                col = 1
                continue
            if kind in ("SKIP", "COMMENT"):
                col += len(value)
                continue
            self._tokens.append((kind, value, line, col))  # type: ignore[arg-type]
            col += len(value)

    def _peek(self) -> Optional[tuple[str, str, int, int]]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self, expected_kind: Optional[str] = None) -> tuple[str, str, int, int]:
        tok = self._peek()
        if tok is None:
            raise GrammarSyntaxError(0, 0, "unexpected end of grammar specification")
        if expected_kind and tok[0] != expected_kind:
            raise GrammarSyntaxError(
                tok[2], tok[3],
                f"expected {expected_kind}, got {tok[0]} ('{tok[1]}')",
            )
        self._pos += 1
        return tok

    def _parse_rule(self) -> list[Production]:
        """Parse one rule: ``non_terminal ::= alternatives ;``."""
        name_tok = self._consume("IDENT")
        lhs = non_terminal(name_tok[1])
        self._consume("DERIVES")
        alternatives = self._parse_alternatives()
        self._consume("SEMICOLON")
        productions: list[Production] = []
        for alt in alternatives:
            productions.append(Production(lhs=lhs, rhs=alt))
        return productions

    def _parse_alternatives(self) -> list[list[Symbol]]:
        """Parse ``alt1 | alt2 | ...``."""
        alts: list[list[Symbol]] = [self._parse_sequence()]
        while self._peek() and self._peek()[0] == "PIPE":  # type: ignore[index]
            self._consume("PIPE")
            alts.append(self._parse_sequence())
        return alts

    def _parse_sequence(self) -> list[Symbol]:
        """Parse a sequence of symbols (one alternative)."""
        seq: list[Symbol] = []
        while True:
            tok = self._peek()
            if tok is None:
                break
            kind = tok[0]
            if kind in ("SEMICOLON", "PIPE", "RBRACE", "RBRACKET", "RPAREN"):
                break
            if kind == "LBRACE":
                # EBNF zero-or-more: desugar { X } into a fresh non-terminal
                self._consume("LBRACE")
                inner = self._parse_sequence()
                self._consume("RBRACE")
                # Represent as a special terminal marker for analysis
                rep_name = f"_repeat_{'_'.join(s.name for s in inner)}"
                seq.append(non_terminal(rep_name))
            elif kind == "LBRACKET":
                # EBNF optional: desugar [ X ] into a fresh non-terminal
                self._consume("LBRACKET")
                inner = self._parse_sequence()
                self._consume("RBRACKET")
                opt_name = f"_opt_{'_'.join(s.name for s in inner)}"
                seq.append(non_terminal(opt_name))
            elif kind == "LPAREN":
                self._consume("LPAREN")
                group_alts = self._parse_alternatives()
                self._consume("RPAREN")
                # For simplicity, flatten single-alternative groups
                if len(group_alts) == 1:
                    seq.extend(group_alts[0])
                else:
                    grp_name = f"_group_{self._pos}"
                    seq.append(non_terminal(grp_name))
            elif kind == "STRING":
                val = self._consume("STRING")[1]
                # Strip quotes
                seq.append(terminal(val[1:-1]))
            elif kind == "IDENT":
                val = self._consume("IDENT")[1]
                if val.isupper():
                    seq.append(terminal(val))
                else:
                    seq.append(non_terminal(val))
            else:
                raise GrammarSyntaxError(
                    tok[2], tok[3],
                    f"unexpected token: {kind} ('{tok[1]}')",
                )
        return seq


# ============================================================
# FIRST / FOLLOW set computation
# ============================================================


class FirstFollowComputer:
    """Computes FIRST and FOLLOW sets for all non-terminals in a grammar.

    Uses the standard fixed-point iteration algorithm from every
    compiler textbook published since 1986.  The algorithm handles
    nullable productions (epsilon) correctly and terminates when
    no set changes between iterations -- a property guaranteed by
    the monotonicity of set union over a finite universe of terminals.
    """

    def __init__(self, grammar: Grammar) -> None:
        self.grammar = grammar
        self.first: dict[str, set[str]] = {}
        self.follow: dict[str, set[str]] = {}
        self.nullable: set[str] = set()
        self._compute()

    def _compute(self) -> None:
        """Run the fixed-point iteration."""
        # Initialize
        for nt in self.grammar.non_terminals:
            self.first[nt] = set()
            self.follow[nt] = set()

        # Compute nullable non-terminals
        self._compute_nullable()

        # Compute FIRST sets
        self._compute_first()

        # Compute FOLLOW sets
        self._compute_follow()

    def _compute_nullable(self) -> None:
        """Determine which non-terminals can derive epsilon."""
        changed = True
        while changed:
            changed = False
            for prod in self.grammar.productions:
                if prod.lhs.name in self.nullable:
                    continue
                if prod.is_epsilon:
                    self.nullable.add(prod.lhs.name)
                    changed = True
                elif all(
                    s.is_non_terminal and s.name in self.nullable
                    for s in prod.rhs
                ):
                    self.nullable.add(prod.lhs.name)
                    changed = True

    def _compute_first(self) -> None:
        """Fixed-point iteration for FIRST sets."""
        changed = True
        while changed:
            changed = False
            for prod in self.grammar.productions:
                lhs_name = prod.lhs.name
                before = len(self.first[lhs_name])
                first_of_rhs = self._first_of_sequence(prod.rhs)
                self.first[lhs_name] |= first_of_rhs
                if len(self.first[lhs_name]) > before:
                    changed = True

    def _first_of_sequence(self, symbols: list[Symbol]) -> set[str]:
        """Compute FIRST of a sequence of symbols."""
        result: set[str] = set()
        for sym in symbols:
            if sym.is_terminal:
                result.add(sym.name)
                return result
            if sym.is_epsilon:
                continue
            # Non-terminal
            result |= self.first.get(sym.name, set()) - {EPSILON}
            if sym.name not in self.nullable:
                return result
        # All symbols are nullable
        result.add(EPSILON)
        return result

    def _compute_follow(self) -> None:
        """Fixed-point iteration for FOLLOW sets."""
        # Start symbol gets EOF
        if self.grammar.start_symbol:
            self.follow.setdefault(
                self.grammar.start_symbol.name, set()
            ).add(EOF)

        changed = True
        while changed:
            changed = False
            for prod in self.grammar.productions:
                for i, sym in enumerate(prod.rhs):
                    if not sym.is_non_terminal:
                        continue
                    rest = prod.rhs[i + 1:]
                    first_rest = self._first_of_sequence(rest)
                    before = len(self.follow.get(sym.name, set()))

                    self.follow.setdefault(sym.name, set())
                    self.follow[sym.name] |= first_rest - {EPSILON}

                    # If rest can derive epsilon, add FOLLOW(lhs)
                    if EPSILON in first_rest or not rest:
                        self.follow[sym.name] |= self.follow.get(
                            prod.lhs.name, set()
                        )

                    if len(self.follow[sym.name]) > before:
                        changed = True

    def first_of(self, symbol_name: str) -> set[str]:
        """Return the FIRST set for a given symbol."""
        if symbol_name in self.first:
            return self.first[symbol_name]
        # Terminal: FIRST is itself
        return {symbol_name}

    def follow_of(self, symbol_name: str) -> set[str]:
        """Return the FOLLOW set for a given non-terminal."""
        return self.follow.get(symbol_name, set())


# ============================================================
# LL(1) Classifier
# ============================================================


class LL1Classifier:
    """Determines whether a grammar is LL(1).

    A grammar is LL(1) if and only if, for every non-terminal A with
    alternatives A -> alpha | beta:
      1. FIRST(alpha) and FIRST(beta) are disjoint.
      2. If epsilon is in FIRST(alpha), then FIRST(beta) and FOLLOW(A)
         are disjoint (and vice versa).

    When conflicts exist, the classifier reports them with enough
    detail to guide grammar refactoring -- or to accept that the
    grammar is simply not LL(1) and move on with one's life.
    """

    def __init__(self, grammar: Grammar, ff: FirstFollowComputer) -> None:
        self.grammar = grammar
        self.ff = ff
        self.conflicts: list[dict[str, Any]] = []
        self.is_ll1 = self._classify()

    def _classify(self) -> bool:
        """Check all non-terminals for LL(1) conflicts."""
        is_clean = True
        for nt_name in self.grammar.non_terminals:
            prods = self.grammar.productions_for(nt_name)
            if len(prods) < 2:
                continue
            # Compute FIRST for each alternative
            alt_firsts: list[tuple[Production, set[str]]] = []
            for prod in prods:
                first = self.ff._first_of_sequence(prod.rhs)
                alt_firsts.append((prod, first))

            # Pairwise disjointness check
            for i in range(len(alt_firsts)):
                for j in range(i + 1, len(alt_firsts)):
                    prod_i, first_i = alt_firsts[i]
                    prod_j, first_j = alt_firsts[j]
                    overlap = (first_i - {EPSILON}) & (first_j - {EPSILON})
                    if overlap:
                        self.conflicts.append({
                            "non_terminal": nt_name,
                            "type": "FIRST/FIRST",
                            "productions": [repr(prod_i), repr(prod_j)],
                            "overlap": overlap,
                        })
                        is_clean = False

            # Nullable alternative vs FOLLOW check
            for prod, first in alt_firsts:
                if EPSILON in first:
                    follow_set = self.ff.follow_of(nt_name)
                    for other_prod, other_first in alt_firsts:
                        if other_prod is prod:
                            continue
                        overlap = other_first & follow_set
                        if overlap:
                            self.conflicts.append({
                                "non_terminal": nt_name,
                                "type": "FIRST/FOLLOW",
                                "productions": [repr(prod), repr(other_prod)],
                                "overlap": overlap,
                            })
                            is_clean = False

        return is_clean


# ============================================================
# Left Recursion Detector
# ============================================================


class LeftRecursionDetector:
    """Detects direct and indirect left recursion in a grammar.

    Left recursion prevents top-down (LL) parsing because the parser
    enters an infinite loop trying to expand A -> A alpha.  This
    detector uses DFS to find cycles in the ``left-corner`` relation:
    A left-derives B if some production A -> B beta exists (or
    A -> C beta where C left-derives B, transitively).
    """

    def __init__(self, grammar: Grammar) -> None:
        self.grammar = grammar
        self.cycles: list[list[str]] = []
        self._detect()

    def _detect(self) -> None:
        """Find all left-recursive cycles via DFS."""
        for nt_name in self.grammar.non_terminals:
            visited: set[str] = set()
            path: list[str] = []
            self._dfs(nt_name, nt_name, visited, path)

    def _dfs(
        self,
        start: str,
        current: str,
        visited: set[str],
        path: list[str],
    ) -> None:
        if current in visited:
            return
        visited.add(current)
        path.append(current)
        for prod in self.grammar.productions_for(current):
            if not prod.rhs:
                continue
            first_sym = prod.rhs[0]
            if first_sym.is_non_terminal:
                if first_sym.name == start and len(path) >= 1:
                    cycle = path + [start]
                    # Avoid duplicate cycles
                    if cycle not in self.cycles:
                        self.cycles.append(cycle)
                else:
                    self._dfs(start, first_sym.name, visited, path)
        path.pop()
        visited.discard(current)

    @property
    def has_left_recursion(self) -> bool:
        return len(self.cycles) > 0


# ============================================================
# Ambiguity Analyzer
# ============================================================


class AmbiguityAnalyzer:
    """Bounded-search ambiguity detection for context-free grammars.

    Ambiguity detection is undecidable in general (Rice's theorem
    strikes again), but a bounded breadth-first expansion of
    derivations can catch many practical ambiguities.  The analyzer
    expands all non-terminals up to a configurable depth and checks
    whether any terminal string can be derived in two distinct ways.
    """

    def __init__(self, grammar: Grammar, max_depth: int = 6) -> None:
        self.grammar = grammar
        self.max_depth = max_depth
        self.ambiguities: list[dict[str, Any]] = []
        self._analyze()

    def _analyze(self) -> None:
        """Perform bounded derivation search for ambiguities."""
        for nt_name in self.grammar.non_terminals:
            prods = self.grammar.productions_for(nt_name)
            if len(prods) < 2:
                continue
            # Derive terminal strings from each alternative (bounded)
            for i in range(len(prods)):
                for j in range(i + 1, len(prods)):
                    strings_i = self._derive(prods[i].rhs, self.max_depth)
                    strings_j = self._derive(prods[j].rhs, self.max_depth)
                    overlap = strings_i & strings_j
                    if overlap:
                        example = next(iter(overlap))
                        self.ambiguities.append({
                            "non_terminal": nt_name,
                            "production_a": repr(prods[i]),
                            "production_b": repr(prods[j]),
                            "ambiguous_string": example,
                        })

    def _derive(self, symbols: list[Symbol], depth: int) -> set[str]:
        """Derive all terminal strings reachable within depth steps."""
        if depth <= 0:
            return set()
        if not symbols:
            return {""}
        first = symbols[0]
        rest = symbols[1:]
        if first.is_terminal:
            rest_strings = self._derive(rest, depth)
            return {first.name + r for r in rest_strings}
        if first.is_epsilon:
            return self._derive(rest, depth)
        # Non-terminal: expand each production
        result: set[str] = set()
        for prod in self.grammar.productions_for(first.name):
            expanded = prod.rhs + rest
            # Limit expansion length to prevent combinatorial explosion
            if len(expanded) <= self.max_depth * 2:
                result |= self._derive(expanded, depth - 1)
        return result

    @property
    def is_ambiguous(self) -> bool:
        return len(self.ambiguities) > 0


# ============================================================
# Unreachable Symbol Detector
# ============================================================


class UnreachableSymbolDetector:
    """Finds non-terminals that cannot be reached from the start symbol.

    An unreachable non-terminal is dead grammar -- production rules
    that exist but can never participate in any derivation from the
    start symbol.  This is the grammatical equivalent of dead code,
    and it deserves the same diagnosis.
    """

    def __init__(self, grammar: Grammar) -> None:
        self.grammar = grammar
        self.unreachable: set[str] = set()
        self._detect()

    def _detect(self) -> None:
        if not self.grammar.start_symbol:
            self.unreachable = self.grammar.non_terminals
            return
        reachable: set[str] = set()
        queue = [self.grammar.start_symbol.name]
        while queue:
            current = queue.pop()
            if current in reachable:
                continue
            reachable.add(current)
            for prod in self.grammar.productions_for(current):
                for sym in prod.rhs:
                    if sym.is_non_terminal and sym.name not in reachable:
                        queue.append(sym.name)
        self.unreachable = self.grammar.non_terminals - reachable


# ============================================================
# AST Node
# ============================================================


@dataclass
class ASTNode:
    """A generic Abstract Syntax Tree node.

    Every node has a type (matching a non-terminal or token type),
    optional children (for interior nodes), and optional token data
    (for leaf nodes).  Line and column track source positions for
    error reporting.
    """

    node_type: str
    children: list["ASTNode"] = field(default_factory=list)
    token: Optional[str] = None
    line: int = 0
    column: int = 0

    def is_leaf(self) -> bool:
        return self.token is not None

    def pretty(self, indent: int = 0) -> str:
        """Render the AST as an indented text tree."""
        prefix = "  " * indent
        if self.is_leaf():
            return f"{prefix}{self.node_type}: {self.token!r}"
        lines = [f"{prefix}{self.node_type}"]
        for child in self.children:
            lines.append(child.pretty(indent + 1))
        return "\n".join(lines)

    def __repr__(self) -> str:
        if self.is_leaf():
            return f"ASTNode({self.node_type!r}, token={self.token!r})"
        return f"ASTNode({self.node_type!r}, children={len(self.children)})"


# ============================================================
# Generated Parser (base class + generator)
# ============================================================


@dataclass
class Token:
    """A lexical token produced by the tokenizer."""

    kind: str
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r})"


class GeneratedParser:
    """Base class for parsers generated from a Grammar.

    The ParserGenerator populates ``_parse_table`` and ``_token_rules``
    on subclasses.  The base class provides the tokenizer, lookahead
    management, error reporting, and error recovery logic.
    """

    # Populated by ParserGenerator
    _grammar: Optional[Grammar] = None
    _first_sets: Optional[dict[str, set[str]]] = None
    _follow_sets: Optional[dict[str, set[str]]] = None
    _token_patterns: list[tuple[str, str]] = []
    _sync_tokens: set[str] = {";", ")"}

    def __init__(self) -> None:
        self._tokens: list[Token] = []
        self._pos: int = 0
        self._errors: list[dict[str, Any]] = []

    def parse(self, text: str) -> ASTNode:
        """Tokenize and parse the input, returning an AST."""
        self._tokenize(text)
        self._pos = 0
        self._errors = []
        if self._grammar is None or self._grammar.start_symbol is None:
            raise GrammarError("No grammar or start symbol configured")
        node = self._parse_non_terminal(self._grammar.start_symbol.name)
        return node

    def _tokenize(self, text: str) -> None:
        """Convert input text into a token stream."""
        self._tokens = []
        line = 1
        col = 1
        i = 0
        while i < len(text):
            if text[i] == "\n":
                line += 1
                col = 1
                i += 1
                continue
            if text[i] in (" ", "\t", "\r"):
                col += 1
                i += 1
                continue
            matched = False
            # Try keyword/literal patterns first, then regex patterns
            for kind, pattern in self._token_patterns:
                if pattern.startswith("__re__"):
                    regex = pattern[6:]
                    m = re.match(regex, text[i:])
                    if m:
                        val = m.group()
                        self._tokens.append(Token(kind, val, line, col))
                        col += len(val)
                        i += len(val)
                        matched = True
                        break
                else:
                    if text[i:i + len(pattern)] == pattern:
                        # Keyword: ensure not part of a larger identifier
                        end = i + len(pattern)
                        if pattern.isalpha() and end < len(text) and (
                            text[end].isalnum() or text[end] == "_"
                        ):
                            continue
                        self._tokens.append(Token(kind, pattern, line, col))
                        col += len(pattern)
                        i += len(pattern)
                        matched = True
                        break
            if not matched:
                self._errors.append({
                    "line": line,
                    "column": col,
                    "message": f"unexpected character: {text[i]!r}",
                })
                col += 1
                i += 1
        # Append EOF token
        self._tokens.append(Token(EOF, "", line, col))

    def _peek(self) -> Token:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return Token(EOF, "", 0, 0)

    def _consume(self, expected_kind: Optional[str] = None) -> Token:
        tok = self._peek()
        if expected_kind and tok.kind != expected_kind:
            self._report_error(tok, [expected_kind])
            self._recover()
            return tok
        self._pos += 1
        return tok

    def _report_error(self, tok: Token, expected: list[str]) -> None:
        error_info = {
            "line": tok.line,
            "column": tok.column,
            "found": tok.kind,
            "expected": expected,
        }
        self._errors.append(error_info)

    def _recover(self) -> None:
        """Skip tokens until a synchronization token is found."""
        while self._peek().kind != EOF:
            if self._peek().value in self._sync_tokens or self._peek().kind in self._sync_tokens:
                return
            self._pos += 1

    def _parse_non_terminal(self, nt_name: str) -> ASTNode:
        """Parse a non-terminal by trying its alternatives."""
        if self._grammar is None:
            raise GrammarError("No grammar configured")

        prods = self._grammar.productions_for(nt_name)
        if not prods:
            raise GrammarError(f"No productions for non-terminal '{nt_name}'")

        lookahead = self._peek()

        # Try to select alternative via FIRST sets (LL(1))
        for prod in prods:
            if self._can_start(prod, lookahead):
                return self._parse_production(prod)

        # Check if any alternative is nullable
        for prod in prods:
            if self._is_nullable_production(prod):
                return ASTNode(node_type=nt_name, line=lookahead.line, column=lookahead.column)

        # No match: report error
        expected = self._expected_tokens(nt_name)
        self._report_error(lookahead, expected)
        self._recover()
        return ASTNode(node_type=nt_name, line=lookahead.line, column=lookahead.column)

    def _can_start(self, prod: Production, lookahead: Token) -> bool:
        """Check if a production can start with the given lookahead."""
        if self._first_sets is None:
            return True  # No analysis available; try everything
        first = self._first_of_production(prod)
        return lookahead.kind in first or lookahead.value in first

    def _first_of_production(self, prod: Production) -> set[str]:
        """Compute FIRST set for a production's RHS."""
        result: set[str] = set()
        for sym in prod.rhs:
            if sym.is_terminal:
                result.add(sym.name)
                return result
            if sym.is_epsilon:
                continue
            if self._first_sets and sym.name in self._first_sets:
                result |= self._first_sets[sym.name] - {EPSILON}
                if EPSILON not in self._first_sets.get(sym.name, set()):
                    return result
            else:
                return result
        result.add(EPSILON)
        return result

    def _is_nullable_production(self, prod: Production) -> bool:
        """Check if a production can derive epsilon."""
        if prod.is_epsilon:
            return True
        return EPSILON in self._first_of_production(prod)

    def _expected_tokens(self, nt_name: str) -> list[str]:
        """Compute the expected token set for a non-terminal."""
        expected: set[str] = set()
        if self._first_sets and nt_name in self._first_sets:
            expected |= self._first_sets[nt_name] - {EPSILON}
        if self._follow_sets and nt_name in self._follow_sets:
            expected |= self._follow_sets[nt_name]
        return sorted(expected) if expected else ["<unknown>"]

    def _parse_production(self, prod: Production) -> ASTNode:
        """Parse a single production, building an AST node."""
        node = ASTNode(
            node_type=prod.lhs.name,
            line=self._peek().line,
            column=self._peek().column,
        )
        for sym in prod.rhs:
            if sym.is_epsilon:
                continue
            if sym.is_terminal:
                tok = self._peek()
                if tok.kind == sym.name or tok.value == sym.name:
                    self._pos += 1
                    node.children.append(ASTNode(
                        node_type=sym.name,
                        token=tok.value,
                        line=tok.line,
                        column=tok.column,
                    ))
                else:
                    self._report_error(tok, [sym.name])
                    self._recover()
            elif sym.is_non_terminal:
                child = self._parse_non_terminal(sym.name)
                node.children.append(child)
        return node


# ============================================================
# Parser Generator
# ============================================================


class ParserGenerator:
    """Compiles a Grammar into a GeneratedParser subclass.

    The generator analyzes the grammar (FIRST/FOLLOW, LL(1) classification),
    configures a GeneratedParser subclass with the computed parse tables,
    and returns an instance ready to parse input strings.

    The generated parser is a genuine recursive-descent parser that uses
    FIRST sets for predictive lookahead selection.  For non-LL(1) grammars,
    it falls back to ordered-choice (PEG-style first-match) selection.
    """

    def __init__(self, grammar: Grammar) -> None:
        self.grammar = grammar
        self.ff = FirstFollowComputer(grammar)
        self.classifier = LL1Classifier(grammar, self.ff)

    def generate(self) -> GeneratedParser:
        """Generate and return a parser for the grammar."""
        # Build token patterns from grammar terminals
        token_patterns: list[tuple[str, str]] = []
        keyword_terminals: set[str] = set()
        regex_terminals: set[str] = set()

        for t in sorted(self.grammar.terminals, key=len, reverse=True):
            if t.isupper():
                # Token class like NUMBER, IDENTIFIER, STRING
                if t == "NUMBER":
                    token_patterns.append((t, "__re__[0-9]+"))
                elif t == "IDENTIFIER":
                    token_patterns.append((t, "__re__[A-Za-z_][A-Za-z_0-9]*"))
                elif t == "STRING":
                    token_patterns.append((t, '__re__"[^"]*"'))
                else:
                    token_patterns.append((t, f"__re__[A-Za-z_][A-Za-z_0-9]*"))
                regex_terminals.add(t)
            else:
                # Literal keyword or operator
                keyword_terminals.add(t)

        # Keywords before regex patterns (longest match)
        ordered_patterns: list[tuple[str, str]] = []
        for t in sorted(keyword_terminals, key=len, reverse=True):
            ordered_patterns.append((t, t))
        ordered_patterns.extend(
            (k, v) for k, v in token_patterns if k in regex_terminals
        )

        # Create parser instance
        parser = GeneratedParser()
        parser._grammar = self.grammar
        parser._first_sets = dict(self.ff.first)
        parser._follow_sets = dict(self.ff.follow)
        parser._token_patterns = ordered_patterns

        return parser


# ============================================================
# Grammar Analysis Report
# ============================================================


class GrammarAnalyzer:
    """Runs all grammar analyses and produces a structured report.

    This is the single entry point for comprehensive grammar analysis:
    FIRST/FOLLOW sets, LL(1) classification, left recursion detection,
    ambiguity analysis, and unreachable symbol detection.
    """

    def __init__(self, grammar: Grammar, max_ambiguity_depth: int = 6) -> None:
        self.grammar = grammar
        self.ff = FirstFollowComputer(grammar)
        self.classifier = LL1Classifier(grammar, self.ff)
        self.left_recursion = LeftRecursionDetector(grammar)
        self.ambiguity = AmbiguityAnalyzer(grammar, max_depth=max_ambiguity_depth)
        self.unreachable = UnreachableSymbolDetector(grammar)

    def report(self) -> dict[str, Any]:
        """Produce a comprehensive analysis report."""
        stats = self.grammar.statistics()
        diagnostics_total = 3  # left recursion, ambiguity, unreachable
        diagnostics_passing = sum([
            0 if self.left_recursion.has_left_recursion else 1,
            0 if self.ambiguity.is_ambiguous else 1,
            1 if not self.unreachable.unreachable else 0,
        ])
        health_index = (
            diagnostics_passing / diagnostics_total * 100
            if diagnostics_total > 0
            else 100.0
        )
        return {
            "statistics": stats,
            "first_sets": {k: sorted(v) for k, v in self.ff.first.items()},
            "follow_sets": {k: sorted(v) for k, v in self.ff.follow.items()},
            "nullable": sorted(self.ff.nullable),
            "is_ll1": self.classifier.is_ll1,
            "ll1_conflicts": self.classifier.conflicts,
            "left_recursion": {
                "detected": self.left_recursion.has_left_recursion,
                "cycles": self.left_recursion.cycles,
            },
            "ambiguity": {
                "detected": self.ambiguity.is_ambiguous,
                "instances": self.ambiguity.ambiguities,
            },
            "unreachable_symbols": sorted(self.unreachable.unreachable),
            "grammar_class": "LL(1)" if self.classifier.is_ll1 else "not LL(1)",
            "health_index": round(health_index, 1),
        }

    def render_text_report(self) -> str:
        """Render the analysis report as human-readable text."""
        r = self.report()
        lines: list[str] = []
        lines.append(f"  Grammar: {r['statistics']['name']}")
        lines.append(f"  Terminals: {r['statistics']['terminals']}")
        lines.append(f"  Non-terminals: {r['statistics']['non_terminals']}")
        lines.append(f"  Productions: {r['statistics']['productions']}")
        lines.append(f"  Grammar class: {r['grammar_class']}")
        lines.append(f"  Health index: {r['health_index']}%")
        lines.append("")

        lines.append("  FIRST sets:")
        for nt, first in sorted(r["first_sets"].items()):
            lines.append(f"    {nt}: {{ {', '.join(first)} }}")
        lines.append("")

        lines.append("  FOLLOW sets:")
        for nt, follow in sorted(r["follow_sets"].items()):
            lines.append(f"    {nt}: {{ {', '.join(follow)} }}")
        lines.append("")

        if r["nullable"]:
            lines.append(f"  Nullable: {', '.join(r['nullable'])}")
            lines.append("")

        if r["ll1_conflicts"]:
            lines.append(f"  LL(1) conflicts ({len(r['ll1_conflicts'])}):")
            for c in r["ll1_conflicts"]:
                lines.append(f"    {c['non_terminal']}: {c['type']} overlap on {c['overlap']}")
            lines.append("")

        if r["left_recursion"]["detected"]:
            lines.append("  Left recursion detected:")
            for cycle in r["left_recursion"]["cycles"]:
                lines.append(f"    Cycle: {' -> '.join(cycle)}")
            lines.append("")
        else:
            lines.append("  Left recursion: none detected")
            lines.append("")

        if r["ambiguity"]["detected"]:
            lines.append(f"  Ambiguities ({len(r['ambiguity']['instances'])}):")
            for a in r["ambiguity"]["instances"]:
                lines.append(f"    {a['non_terminal']}: {a['ambiguous_string']!r}")
            lines.append("")
        else:
            lines.append("  Ambiguity: none detected (bounded search)")
            lines.append("")

        if r["unreachable_symbols"]:
            lines.append(f"  Unreachable: {', '.join(r['unreachable_symbols'])}")
        else:
            lines.append("  Unreachable symbols: none")

        return "\n".join(lines)


# ============================================================
# Built-in FizzBuzz Classification Grammar
# ============================================================

FIZZBUZZ_GRAMMAR_BNF = """\
program       ::= statement ;
statement     ::= rule_def | query | assignment ;
rule_def      ::= "RULE" IDENTIFIER ":" condition "->" label ";" ;
condition     ::= primary_cond ;
primary_cond  ::= "divisible_by" "(" NUMBER ")" ;
label         ::= STRING ;
query         ::= "EVALUATE" expression ;
expression    ::= NUMBER | IDENTIFIER ;
assignment    ::= "LET" IDENTIFIER "=" expression ";" ;
"""


def load_builtin_grammar() -> Grammar:
    """Parse and return the built-in FizzBuzz Classification grammar."""
    parser = GrammarParser()
    return parser.parse(FIZZBUZZ_GRAMMAR_BNF, name="FizzBuzz Classification")


# ============================================================
# Dashboard
# ============================================================


class GrammarDashboard:
    """ASCII dashboard for grammar analysis results.

    Renders a box-drawing dashboard showing grammar inventory,
    FIRST/FOLLOW set summaries, diagnostics, and a Grammar Health
    Index.  Because every compiler textbook has tables, but only
    the Enterprise FizzBuzz Platform has a dashboard.
    """

    @staticmethod
    def render(grammar: Grammar, analyzer: Optional[GrammarAnalyzer] = None, width: int = 60) -> str:
        """Render the dashboard as an ASCII string."""
        if analyzer is None:
            analyzer = GrammarAnalyzer(grammar)

        report = analyzer.report()
        inner = width - 4  # account for "| " and " |"

        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(_center("FizzGrammar: Formal Grammar & Parser Generator", width))
        lines.append(_center("Chomsky hierarchy compliance since 1956", width))
        lines.append(border)

        # Grammar inventory
        lines.append(_center("GRAMMAR INVENTORY", width))
        lines.append(border)
        stats = report["statistics"]
        lines.append(_row("Grammar", stats["name"], inner, width))
        lines.append(_row("Terminals", str(stats["terminals"]), inner, width))
        lines.append(_row("Non-terminals", str(stats["non_terminals"]), inner, width))
        lines.append(_row("Productions", str(stats["productions"]), inner, width))
        lines.append(_row("Grammar class", report["grammar_class"], inner, width))
        lines.append(border)

        # FIRST sets (abbreviated)
        lines.append(_center("FIRST SETS", width))
        lines.append(border)
        for nt, first in sorted(report["first_sets"].items()):
            first_str = ", ".join(first)
            if len(first_str) > inner - len(nt) - 6:
                first_str = first_str[:inner - len(nt) - 9] + "..."
            lines.append(_row(nt, "{ " + first_str + " }", inner, width))
        lines.append(border)

        # FOLLOW sets (abbreviated)
        lines.append(_center("FOLLOW SETS", width))
        lines.append(border)
        for nt, follow in sorted(report["follow_sets"].items()):
            follow_str = ", ".join(follow)
            if len(follow_str) > inner - len(nt) - 6:
                follow_str = follow_str[:inner - len(nt) - 9] + "..."
            lines.append(_row(nt, "{ " + follow_str + " }", inner, width))
        lines.append(border)

        # Diagnostics
        lines.append(_center("DIAGNOSTICS", width))
        lines.append(border)
        lr_status = "DETECTED" if report["left_recursion"]["detected"] else "CLEAN"
        amb_status = "DETECTED" if report["ambiguity"]["detected"] else "CLEAN"
        unreach = ", ".join(report["unreachable_symbols"]) if report["unreachable_symbols"] else "none"
        ll1_status = "YES" if report["is_ll1"] else f"NO ({len(report['ll1_conflicts'])} conflicts)"
        lines.append(_row("LL(1)", ll1_status, inner, width))
        lines.append(_row("Left recursion", lr_status, inner, width))
        lines.append(_row("Ambiguity", amb_status, inner, width))
        lines.append(_row("Unreachable", unreach, inner, width))
        lines.append(border)

        # Health Index
        lines.append(_center("GRAMMAR HEALTH INDEX", width))
        lines.append(border)
        health = report["health_index"]
        bar_width = inner - 10
        filled = int(health / 100 * bar_width)
        bar = "#" * filled + "-" * (bar_width - filled)
        lines.append(_row("Health", f"{health}% [{bar}]", inner, width))
        lines.append(border)

        return "\n".join(lines)


def _center(text: str, width: int) -> str:
    """Center text in a dashboard row."""
    padded = text.center(width - 4)
    return f"| {padded} |"


def _row(label: str, value: str, inner: int, width: int) -> str:
    """Format a label-value row."""
    content = f"  {label}: {value}"
    if len(content) > inner:
        content = content[:inner - 3] + "..."
    content = content.ljust(inner)
    return f"| {content} |"

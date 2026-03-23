"""
Enterprise FizzBuzz Platform - FizzSheet Spreadsheet Engine

Provides a full-featured spreadsheet engine for FizzBuzz analytics, including
A1-style cell addressing, a recursive-descent formula parser with operator
precedence, a directed dependency graph with Kahn's topological sort for
recalculation ordering, circular reference detection, and 20 built-in
functions including three FizzBuzz-specific functions for classification,
cost analysis, and tax computation.

Modern enterprise platforms require tabular data analysis capabilities.
Exporting FizzBuzz results to a third-party spreadsheet application
introduces unacceptable latency and compliance risk. By embedding a
spreadsheet engine directly into the platform, analysts can perform
real-time FizzBuzz analytics without leaving the evaluation pipeline.

Key components:
- CellRef: A1-style cell reference (columns A-Z, rows 1-999)
- CellValue: Typed cell values (Number, String, Boolean, Error, Empty)
- Formula AST: NumberNode, StringNode, CellRefNode, RangeNode,
  FunctionCallNode, BinaryOpNode, UnaryOpNode
- FormulaParser: Recursive-descent parser with operator precedence
- FormulaEvaluator: AST walker that evaluates formulas against the grid
- DependencyGraph: Directed graph with Kahn's topological sort
- CircularReferenceDetector: DFS-based cycle detection
- Spreadsheet: The grid itself, with get/set/recalculate/insert/delete
- SpreadsheetRenderer: ASCII table output with auto-width columns
- SpreadsheetDashboard: ASCII dashboard with cell statistics
- SpreadsheetMiddleware: IMiddleware implementation for pipeline integration
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, Union

from enterprise_fizzbuzz.domain.exceptions import (
    SpreadsheetError,
    SpreadsheetCellReferenceError,
    SpreadsheetFormulaParseError,
    SpreadsheetCircularReferenceError,
    SpreadsheetFunctionError,
    SpreadsheetRangeError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_COLUMNS = 26  # A through Z
MAX_ROWS = 999
COLUMN_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ---------------------------------------------------------------------------
# Cell Reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellRef:
    """A1-style cell reference.

    Columns are identified by a single uppercase letter (A-Z), and rows
    by an integer (1-999). This gives a maximum grid of 26 columns by
    999 rows, which is more than sufficient for any conceivable FizzBuzz
    analytics workload.
    """

    col: str
    row: int

    def __post_init__(self) -> None:
        if len(self.col) != 1 or self.col not in COLUMN_LETTERS:
            raise SpreadsheetCellReferenceError(
                f"Invalid column: {self.col!r}. Must be A-Z."
            )
        if not (1 <= self.row <= MAX_ROWS):
            raise SpreadsheetCellReferenceError(
                f"Invalid row: {self.row}. Must be 1-{MAX_ROWS}."
            )

    @staticmethod
    def from_string(ref: str) -> CellRef:
        """Parse a cell reference string like 'A1' or 'Z999'."""
        ref = ref.strip().upper()
        match = re.fullmatch(r"([A-Z])(\d{1,3})", ref)
        if not match:
            raise SpreadsheetCellReferenceError(
                f"Cannot parse cell reference: {ref!r}"
            )
        col = match.group(1)
        row = int(match.group(2))
        return CellRef(col=col, row=row)

    @property
    def col_index(self) -> int:
        """Zero-based column index."""
        return ord(self.col) - ord("A")

    def __str__(self) -> str:
        return f"{self.col}{self.row}"

    def __repr__(self) -> str:
        return f"CellRef({self.col!r}, {self.row})"


# ---------------------------------------------------------------------------
# Cell Value Types
# ---------------------------------------------------------------------------


class CellValueType(Enum):
    """The type of a cell's computed value."""
    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    ERROR = auto()
    EMPTY = auto()


@dataclass
class CellValue:
    """A typed cell value.

    Wraps raw Python values with an explicit type tag, enabling the
    formula evaluator to distinguish between numeric zero and empty
    cells, or between the string "TRUE" and the boolean True.
    """

    value_type: CellValueType
    raw: Any = None

    @staticmethod
    def number(v: float) -> CellValue:
        return CellValue(CellValueType.NUMBER, float(v))

    @staticmethod
    def string(v: str) -> CellValue:
        return CellValue(CellValueType.STRING, str(v))

    @staticmethod
    def boolean(v: bool) -> CellValue:
        return CellValue(CellValueType.BOOLEAN, bool(v))

    @staticmethod
    def error(msg: str) -> CellValue:
        return CellValue(CellValueType.ERROR, msg)

    @staticmethod
    def empty() -> CellValue:
        return CellValue(CellValueType.EMPTY, None)

    @property
    def is_number(self) -> bool:
        return self.value_type == CellValueType.NUMBER

    @property
    def is_string(self) -> bool:
        return self.value_type == CellValueType.STRING

    @property
    def is_boolean(self) -> bool:
        return self.value_type == CellValueType.BOOLEAN

    @property
    def is_error(self) -> bool:
        return self.value_type == CellValueType.ERROR

    @property
    def is_empty(self) -> bool:
        return self.value_type == CellValueType.EMPTY

    def to_number(self) -> float:
        """Coerce to a number, or raise on incompatible types."""
        if self.is_number:
            return self.raw
        if self.is_boolean:
            return 1.0 if self.raw else 0.0
        if self.is_empty:
            return 0.0
        if self.is_string:
            try:
                return float(self.raw)
            except (ValueError, TypeError):
                pass
        raise SpreadsheetFunctionError(
            f"Cannot convert {self.value_type.name} to number"
        )

    def to_string(self) -> str:
        """Coerce to a display string."""
        if self.is_empty:
            return ""
        if self.is_error:
            return str(self.raw)
        if self.is_boolean:
            return "TRUE" if self.raw else "FALSE"
        if self.is_number:
            if self.raw == int(self.raw):
                return str(int(self.raw))
            return f"{self.raw:.6g}"
        return str(self.raw)

    def __repr__(self) -> str:
        return f"CellValue({self.value_type.name}, {self.raw!r})"


# ---------------------------------------------------------------------------
# Formula AST Nodes
# ---------------------------------------------------------------------------


class FormulaNodeType(Enum):
    """AST node types for parsed formulas."""
    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    CELL_REF = auto()
    RANGE = auto()
    FUNCTION_CALL = auto()
    BINARY_OP = auto()
    UNARY_OP = auto()


@dataclass
class FormulaNode:
    """A node in the formula abstract syntax tree."""
    node_type: FormulaNodeType


@dataclass
class NumberNode(FormulaNode):
    """A numeric literal."""
    value: float

    def __init__(self, value: float) -> None:
        super().__init__(FormulaNodeType.NUMBER)
        self.value = value


@dataclass
class StringNode(FormulaNode):
    """A string literal (enclosed in double quotes)."""
    value: str

    def __init__(self, value: str) -> None:
        super().__init__(FormulaNodeType.STRING)
        self.value = value


@dataclass
class BooleanNode(FormulaNode):
    """A boolean literal (TRUE or FALSE)."""
    value: bool

    def __init__(self, value: bool) -> None:
        super().__init__(FormulaNodeType.BOOLEAN)
        self.value = value


@dataclass
class CellRefNode(FormulaNode):
    """A cell reference (e.g., A1, B2)."""
    ref: CellRef

    def __init__(self, ref: CellRef) -> None:
        super().__init__(FormulaNodeType.CELL_REF)
        self.ref = ref


@dataclass
class RangeNode(FormulaNode):
    """A cell range (e.g., A1:A10)."""
    start: CellRef
    end: CellRef

    def __init__(self, start: CellRef, end: CellRef) -> None:
        super().__init__(FormulaNodeType.RANGE)
        self.start = start
        self.end = end


@dataclass
class FunctionCallNode(FormulaNode):
    """A function call (e.g., SUM(A1:A10))."""
    name: str
    args: list[FormulaNode]

    def __init__(self, name: str, args: list[FormulaNode]) -> None:
        super().__init__(FormulaNodeType.FUNCTION_CALL)
        self.name = name
        self.args = args


@dataclass
class BinaryOpNode(FormulaNode):
    """A binary operation (e.g., A1 + B1)."""
    op: str
    left: FormulaNode
    right: FormulaNode

    def __init__(self, op: str, left: FormulaNode, right: FormulaNode) -> None:
        super().__init__(FormulaNodeType.BINARY_OP)
        self.op = op
        self.left = left
        self.right = right


@dataclass
class UnaryOpNode(FormulaNode):
    """A unary operation (e.g., -A1)."""
    op: str
    operand: FormulaNode

    def __init__(self, op: str, operand: FormulaNode) -> None:
        super().__init__(FormulaNodeType.UNARY_OP)
        self.op = op
        self.operand = operand


# ---------------------------------------------------------------------------
# Token Types for the Lexer
# ---------------------------------------------------------------------------


class TokenType(Enum):
    """Lexer token types for the formula parser."""
    NUMBER = auto()
    STRING = auto()
    CELL_REF = auto()
    IDENT = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    COLON = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    CARET = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    EOF = auto()


@dataclass
class Token:
    """A lexer token."""
    token_type: TokenType
    value: Any
    position: int


# ---------------------------------------------------------------------------
# Formula Lexer
# ---------------------------------------------------------------------------


class FormulaLexer:
    """Tokenizer for spreadsheet formulas.

    Converts a raw formula string into a stream of typed tokens.
    Handles numeric literals, string literals, cell references,
    function names, operators, and punctuation.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0

    def tokenize(self) -> list[Token]:
        """Tokenize the entire formula string."""
        tokens: list[Token] = []
        while self._pos < len(self._text):
            ch = self._text[self._pos]

            # Skip whitespace
            if ch.isspace():
                self._pos += 1
                continue

            # String literal
            if ch == '"':
                tokens.append(self._read_string())
                continue

            # Number
            if ch.isdigit() or (ch == '.' and self._pos + 1 < len(self._text)
                                and self._text[self._pos + 1].isdigit()):
                tokens.append(self._read_number())
                continue

            # Identifier or cell reference
            if ch.isalpha() or ch == '_':
                tokens.append(self._read_identifier())
                continue

            # Two-character operators
            if ch in ('<', '>', '!') and self._pos + 1 < len(self._text):
                next_ch = self._text[self._pos + 1]
                if ch == '<' and next_ch == '=':
                    tokens.append(Token(TokenType.LTE, "<=", self._pos))
                    self._pos += 2
                    continue
                if ch == '>' and next_ch == '=':
                    tokens.append(Token(TokenType.GTE, ">=", self._pos))
                    self._pos += 2
                    continue
                if ch == '<' and next_ch == '>':
                    tokens.append(Token(TokenType.NEQ, "<>", self._pos))
                    self._pos += 2
                    continue
                if ch == '!' and next_ch == '=':
                    tokens.append(Token(TokenType.NEQ, "!=", self._pos))
                    self._pos += 2
                    continue

            # Single-character operators and punctuation
            single_map = {
                '(': TokenType.LPAREN,
                ')': TokenType.RPAREN,
                ',': TokenType.COMMA,
                ':': TokenType.COLON,
                '+': TokenType.PLUS,
                '-': TokenType.MINUS,
                '*': TokenType.STAR,
                '/': TokenType.SLASH,
                '^': TokenType.CARET,
                '=': TokenType.EQ,
                '<': TokenType.LT,
                '>': TokenType.GT,
            }
            if ch in single_map:
                tokens.append(Token(single_map[ch], ch, self._pos))
                self._pos += 1
                continue

            raise SpreadsheetFormulaParseError(
                f"Unexpected character: {ch!r}",
                position=self._pos,
            )

        tokens.append(Token(TokenType.EOF, None, self._pos))
        return tokens

    def _read_string(self) -> Token:
        """Read a string literal enclosed in double quotes."""
        start = self._pos
        self._pos += 1  # skip opening quote
        chars: list[str] = []
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch == '"':
                self._pos += 1
                return Token(TokenType.STRING, "".join(chars), start)
            chars.append(ch)
            self._pos += 1
        raise SpreadsheetFormulaParseError(
            "Unterminated string literal",
            position=start,
        )

    def _read_number(self) -> Token:
        """Read a numeric literal (integer or decimal)."""
        start = self._pos
        has_dot = False
        chars: list[str] = []
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch.isdigit():
                chars.append(ch)
                self._pos += 1
            elif ch == '.' and not has_dot:
                has_dot = True
                chars.append(ch)
                self._pos += 1
            else:
                break
        return Token(TokenType.NUMBER, float("".join(chars)), start)

    def _read_identifier(self) -> Token:
        """Read an identifier or cell reference."""
        start = self._pos
        chars: list[str] = []
        while self._pos < len(self._text) and (
            self._text[self._pos].isalnum() or self._text[self._pos] == '_'
        ):
            chars.append(self._text[self._pos])
            self._pos += 1
        text = "".join(chars)
        upper = text.upper()

        # Check if it's a cell reference (single letter + digits)
        if re.fullmatch(r"[A-Z]\d{1,3}", upper):
            row = int(upper[1:])
            if 1 <= row <= MAX_ROWS:
                return Token(TokenType.CELL_REF, upper, start)

        return Token(TokenType.IDENT, upper, start)


# ---------------------------------------------------------------------------
# Formula Parser
# ---------------------------------------------------------------------------


class FormulaParser:
    """Recursive-descent parser for spreadsheet formulas.

    Implements standard operator precedence:
    1. Unary (-, +)  — highest
    2. Power (^)
    3. Multiplication, Division (*, /)
    4. Addition, Subtraction (+, -)
    5. Comparison (=, <>, <, >, <=, >=) — lowest

    Supports function calls with variable argument lists, cell references,
    cell ranges (A1:B5), string literals, numeric literals, and boolean
    constants (TRUE, FALSE).
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._tokens: list[Token] = []
        self._pos = 0

    def parse(self) -> FormulaNode:
        """Parse the formula text and return an AST root node."""
        # Strip leading '=' if present
        text = self._text.strip()
        if text.startswith("="):
            text = text[1:]

        lexer = FormulaLexer(text)
        self._tokens = lexer.tokenize()
        self._pos = 0

        node = self._parse_comparison()

        if self._current().token_type != TokenType.EOF:
            raise SpreadsheetFormulaParseError(
                f"Unexpected token: {self._current().value!r}",
                position=self._current().position,
            )
        return node

    def _current(self) -> Token:
        """Return the current token."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return Token(TokenType.EOF, None, len(self._text))

    def _advance(self) -> Token:
        """Consume and return the current token."""
        tok = self._current()
        self._pos += 1
        return tok

    def _expect(self, tt: TokenType) -> Token:
        """Consume the current token, asserting its type."""
        tok = self._current()
        if tok.token_type != tt:
            raise SpreadsheetFormulaParseError(
                f"Expected {tt.name}, got {tok.token_type.name}",
                position=tok.position,
            )
        return self._advance()

    def _parse_comparison(self) -> FormulaNode:
        """Parse comparison operators (lowest precedence)."""
        left = self._parse_addition()
        comp_ops = {
            TokenType.EQ: "=",
            TokenType.NEQ: "<>",
            TokenType.LT: "<",
            TokenType.GT: ">",
            TokenType.LTE: "<=",
            TokenType.GTE: ">=",
        }
        while self._current().token_type in comp_ops:
            op = comp_ops[self._current().token_type]
            self._advance()
            right = self._parse_addition()
            left = BinaryOpNode(op, left, right)
        return left

    def _parse_addition(self) -> FormulaNode:
        """Parse addition and subtraction."""
        left = self._parse_multiplication()
        while self._current().token_type in (TokenType.PLUS, TokenType.MINUS):
            op = "+" if self._current().token_type == TokenType.PLUS else "-"
            self._advance()
            right = self._parse_multiplication()
            left = BinaryOpNode(op, left, right)
        return left

    def _parse_multiplication(self) -> FormulaNode:
        """Parse multiplication and division."""
        left = self._parse_power()
        while self._current().token_type in (TokenType.STAR, TokenType.SLASH):
            op = "*" if self._current().token_type == TokenType.STAR else "/"
            self._advance()
            right = self._parse_power()
            left = BinaryOpNode(op, left, right)
        return left

    def _parse_power(self) -> FormulaNode:
        """Parse exponentiation (right-associative)."""
        base = self._parse_unary()
        if self._current().token_type == TokenType.CARET:
            self._advance()
            exp = self._parse_power()  # Right-associative
            return BinaryOpNode("^", base, exp)
        return base

    def _parse_unary(self) -> FormulaNode:
        """Parse unary plus and minus (highest precedence)."""
        if self._current().token_type == TokenType.MINUS:
            self._advance()
            operand = self._parse_unary()
            return UnaryOpNode("-", operand)
        if self._current().token_type == TokenType.PLUS:
            self._advance()
            return self._parse_unary()
        return self._parse_primary()

    def _parse_primary(self) -> FormulaNode:
        """Parse primary expressions: literals, cell refs, functions, parens."""
        tok = self._current()

        # Numeric literal
        if tok.token_type == TokenType.NUMBER:
            self._advance()
            return NumberNode(tok.value)

        # String literal
        if tok.token_type == TokenType.STRING:
            self._advance()
            return StringNode(tok.value)

        # Boolean or function call or identifier
        if tok.token_type == TokenType.IDENT:
            name = tok.value
            self._advance()

            # Boolean constants
            if name == "TRUE":
                return BooleanNode(True)
            if name == "FALSE":
                return BooleanNode(False)

            # Function call
            if self._current().token_type == TokenType.LPAREN:
                self._advance()  # consume '('
                args: list[FormulaNode] = []
                if self._current().token_type != TokenType.RPAREN:
                    args.append(self._parse_comparison())
                    while self._current().token_type == TokenType.COMMA:
                        self._advance()
                        args.append(self._parse_comparison())
                self._expect(TokenType.RPAREN)
                return FunctionCallNode(name, args)

            # Bare identifier — treat as error
            raise SpreadsheetFormulaParseError(
                f"Unknown identifier: {name!r}",
                position=tok.position,
            )

        # Cell reference, possibly a range
        if tok.token_type == TokenType.CELL_REF:
            self._advance()
            ref = CellRef.from_string(tok.value)

            # Check for range operator ':'
            if self._current().token_type == TokenType.COLON:
                self._advance()
                end_tok = self._expect(TokenType.CELL_REF)
                end_ref = CellRef.from_string(end_tok.value)
                return RangeNode(ref, end_ref)

            return CellRefNode(ref)

        # Parenthesized expression
        if tok.token_type == TokenType.LPAREN:
            self._advance()
            node = self._parse_comparison()
            self._expect(TokenType.RPAREN)
            return node

        raise SpreadsheetFormulaParseError(
            f"Unexpected token: {tok.value!r}",
            position=tok.position,
        )


# ---------------------------------------------------------------------------
# Dependency Graph
# ---------------------------------------------------------------------------


class DependencyGraph:
    """Directed graph tracking cell dependencies for recalculation ordering.

    An edge from cell X to cell Y means "Y depends on X" — when X changes,
    Y must be recalculated. Kahn's algorithm produces a topological ordering
    of cells that need recalculation, ensuring that every cell is evaluated
    only after all its dependencies have been updated.
    """

    def __init__(self) -> None:
        # edges[X] = set of cells that depend on X
        self._dependents: dict[str, set[str]] = defaultdict(set)
        # reverse: dependencies[Y] = set of cells that Y depends on
        self._dependencies: dict[str, set[str]] = defaultdict(set)

    def add_dependency(self, cell: str, depends_on: str) -> None:
        """Record that `cell` depends on `depends_on`."""
        self._dependents[depends_on].add(cell)
        self._dependencies[cell].add(depends_on)

    def remove_cell(self, cell: str) -> None:
        """Remove all edges involving `cell`."""
        # Remove from dependents lists
        for dep in self._dependencies.get(cell, set()).copy():
            self._dependents[dep].discard(cell)
        self._dependencies.pop(cell, None)

        # Remove as a dependency source
        for dependent in self._dependents.get(cell, set()).copy():
            self._dependencies[dependent].discard(cell)
        self._dependents.pop(cell, None)

    def remove_own_dependencies(self, cell: str) -> None:
        """Remove only the edges representing what `cell` depends on.

        Preserves edges from other cells that depend on `cell`. This is
        used when a cell's formula changes: the old dependency edges are
        removed before the new ones are added, but downstream dependents
        must remain intact to ensure proper recalculation cascading.
        """
        for dep in self._dependencies.get(cell, set()).copy():
            self._dependents[dep].discard(cell)
        self._dependencies.pop(cell, None)

    def get_dependents(self, cell: str) -> set[str]:
        """Return the set of cells that directly depend on `cell`."""
        return set(self._dependents.get(cell, set()))

    def get_dependencies(self, cell: str) -> set[str]:
        """Return the set of cells that `cell` directly depends on."""
        return set(self._dependencies.get(cell, set()))

    def topological_order(self, dirty_cells: Optional[set[str]] = None) -> list[str]:
        """Compute a topological recalculation order using Kahn's algorithm.

        If `dirty_cells` is provided, only return the subset of cells that
        are reachable from the dirty set. Otherwise, return all cells.

        Returns:
            A list of cell keys in topological order.

        Raises:
            SpreadsheetCircularReferenceError: If a cycle is detected.
        """
        # Collect all cells in the subgraph
        if dirty_cells is not None:
            relevant = self._collect_downstream(dirty_cells)
        else:
            relevant = set(self._dependencies.keys()) | set(self._dependents.keys())

        if not relevant:
            return []

        # Build in-degree map restricted to relevant cells
        in_degree: dict[str, int] = {c: 0 for c in relevant}
        for cell in relevant:
            for dep in self._dependencies.get(cell, set()):
                if dep in relevant:
                    in_degree[cell] = in_degree.get(cell, 0) + 1

        # Kahn's algorithm
        queue: deque[str] = deque()
        for cell, degree in in_degree.items():
            if degree == 0:
                queue.append(cell)

        result: list[str] = []
        while queue:
            cell = queue.popleft()
            result.append(cell)
            for dependent in self._dependents.get(cell, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if len(result) != len(relevant):
            # Cycle detected — identify the cells involved
            remaining = relevant - set(result)
            raise SpreadsheetCircularReferenceError(
                sorted(remaining)
            )

        return result

    def _collect_downstream(self, seeds: set[str]) -> set[str]:
        """BFS to collect all cells reachable downstream from seeds."""
        visited: set[str] = set()
        queue: deque[str] = deque(seeds)
        while queue:
            cell = queue.popleft()
            if cell in visited:
                continue
            visited.add(cell)
            for dep in self._dependents.get(cell, set()):
                if dep not in visited:
                    queue.append(dep)
        return visited

    @property
    def all_edges(self) -> list[tuple[str, str]]:
        """Return all edges as (dependency, dependent) tuples."""
        edges = []
        for source, targets in self._dependents.items():
            for target in sorted(targets):
                edges.append((source, target))
        return sorted(edges)

    @property
    def cell_count(self) -> int:
        """Return the number of unique cells in the graph."""
        cells = set(self._dependents.keys()) | set(self._dependencies.keys())
        return len(cells)


# ---------------------------------------------------------------------------
# Circular Reference Detector
# ---------------------------------------------------------------------------


class CircularReferenceDetector:
    """DFS-based cycle detection for the cell dependency graph.

    Uses a three-color DFS marking scheme:
    - WHITE: not yet visited
    - GRAY: currently on the DFS stack (part of current path)
    - BLACK: fully processed

    If a GRAY node is encountered during DFS, a cycle exists.
    """

    WHITE = 0
    GRAY = 1
    BLACK = 2

    def __init__(self, graph: DependencyGraph) -> None:
        self._graph = graph

    def has_cycle(self) -> bool:
        """Return True if the dependency graph contains a cycle."""
        return len(self.find_cycle()) > 0

    def find_cycle(self) -> list[str]:
        """Find and return cells participating in a cycle, or empty list."""
        all_cells = set()
        for source, targets in self._graph._dependents.items():
            all_cells.add(source)
            all_cells.update(targets)
        for cell, deps in self._graph._dependencies.items():
            all_cells.add(cell)
            all_cells.update(deps)

        color: dict[str, int] = {c: self.WHITE for c in all_cells}
        parent: dict[str, Optional[str]] = {c: None for c in all_cells}

        for cell in sorted(all_cells):
            if color[cell] == self.WHITE:
                cycle = self._dfs(cell, color, parent)
                if cycle:
                    return cycle
        return []

    def _dfs(
        self,
        cell: str,
        color: dict[str, int],
        parent: dict[str, Optional[str]],
    ) -> list[str]:
        """DFS visit. Returns cycle path if found, else empty list."""
        color[cell] = self.GRAY

        for dependent in sorted(self._graph.get_dependents(cell)):
            if color.get(dependent) == self.GRAY:
                # Cycle found — reconstruct path
                return [cell, dependent]
            if color.get(dependent, self.WHITE) == self.WHITE:
                parent[dependent] = cell
                cycle = self._dfs(dependent, color, parent)
                if cycle:
                    return cycle

        color[cell] = self.BLACK
        return []


# ---------------------------------------------------------------------------
# Formula Evaluator
# ---------------------------------------------------------------------------


class FormulaEvaluator:
    """Evaluates a formula AST against a spreadsheet grid.

    Walks the AST recursively, resolving cell references, expanding ranges,
    calling built-in functions, and performing arithmetic operations. All
    errors are caught and returned as CellValue.error() rather than
    propagated, matching standard spreadsheet error semantics.
    """

    def __init__(self, get_cell: Callable[[CellRef], CellValue]) -> None:
        self._get_cell = get_cell
        self._functions = self._build_function_table()

    def evaluate(self, node: FormulaNode) -> CellValue:
        """Evaluate a formula AST node and return the result."""
        try:
            return self._eval(node)
        except SpreadsheetError as exc:
            return CellValue.error(f"#ERROR! {exc}")
        except ZeroDivisionError:
            return CellValue.error("#DIV/0!")
        except Exception as exc:
            return CellValue.error(f"#ERROR! {exc}")

    def _eval(self, node: FormulaNode) -> CellValue:
        """Internal recursive evaluator."""
        if isinstance(node, NumberNode):
            return CellValue.number(node.value)

        if isinstance(node, StringNode):
            return CellValue.string(node.value)

        if isinstance(node, BooleanNode):
            return CellValue.boolean(node.value)

        if isinstance(node, CellRefNode):
            val = self._get_cell(node.ref)
            if val.is_error:
                return val
            return val

        if isinstance(node, RangeNode):
            # Ranges are expanded in function calls, not standalone
            return CellValue.error("#VALUE! Range must be inside a function")

        if isinstance(node, FunctionCallNode):
            return self._eval_function(node)

        if isinstance(node, BinaryOpNode):
            return self._eval_binary(node)

        if isinstance(node, UnaryOpNode):
            return self._eval_unary(node)

        return CellValue.error("#ERROR! Unknown node type")

    def _eval_binary(self, node: BinaryOpNode) -> CellValue:
        """Evaluate a binary operation."""
        left = self._eval(node.left)
        right = self._eval(node.right)

        if left.is_error:
            return left
        if right.is_error:
            return right

        # String concatenation with &
        if node.op == "&":
            return CellValue.string(left.to_string() + right.to_string())

        # Comparison operators work on numbers and strings
        if node.op in ("=", "<>", "<", ">", "<=", ">="):
            return self._eval_comparison(node.op, left, right)

        # Arithmetic operators require numbers
        lv = left.to_number()
        rv = right.to_number()

        if node.op == "+":
            return CellValue.number(lv + rv)
        if node.op == "-":
            return CellValue.number(lv - rv)
        if node.op == "*":
            return CellValue.number(lv * rv)
        if node.op == "/":
            if rv == 0.0:
                return CellValue.error("#DIV/0!")
            return CellValue.number(lv / rv)
        if node.op == "^":
            return CellValue.number(lv ** rv)

        return CellValue.error(f"#ERROR! Unknown operator: {node.op}")

    def _eval_comparison(self, op: str, left: CellValue, right: CellValue) -> CellValue:
        """Evaluate a comparison operator."""
        # Compare numbers if both are numeric
        if left.is_number and right.is_number:
            lv, rv = left.raw, right.raw
        elif left.is_string and right.is_string:
            lv, rv = left.raw, right.raw
        else:
            # Mixed types: coerce to numbers
            try:
                lv = left.to_number()
                rv = right.to_number()
            except SpreadsheetFunctionError:
                lv = left.to_string()
                rv = right.to_string()

        if op == "=":
            return CellValue.boolean(lv == rv)
        if op == "<>":
            return CellValue.boolean(lv != rv)
        if op == "<":
            return CellValue.boolean(lv < rv)
        if op == ">":
            return CellValue.boolean(lv > rv)
        if op == "<=":
            return CellValue.boolean(lv <= rv)
        if op == ">=":
            return CellValue.boolean(lv >= rv)

        return CellValue.error(f"#ERROR! Unknown comparison: {op}")

    def _eval_unary(self, node: UnaryOpNode) -> CellValue:
        """Evaluate a unary operation."""
        operand = self._eval(node.operand)
        if operand.is_error:
            return operand
        if node.op == "-":
            return CellValue.number(-operand.to_number())
        if node.op == "+":
            return CellValue.number(operand.to_number())
        return CellValue.error(f"#ERROR! Unknown unary op: {node.op}")

    def _expand_range(self, node: FormulaNode) -> list[CellValue]:
        """Expand a range or single cell into a list of CellValues."""
        if isinstance(node, RangeNode):
            values = []
            start_col = node.start.col_index
            end_col = node.end.col_index
            start_row = node.start.row
            end_row = node.end.row
            for row in range(min(start_row, end_row), max(start_row, end_row) + 1):
                for col_idx in range(min(start_col, end_col), max(start_col, end_col) + 1):
                    col_letter = COLUMN_LETTERS[col_idx]
                    ref = CellRef(col_letter, row)
                    values.append(self._get_cell(ref))
            return values
        # Single value
        val = self._eval(node)
        return [val]

    def _collect_numeric(self, args: list[FormulaNode]) -> list[float]:
        """Expand all arguments (including ranges) and collect numeric values."""
        numbers: list[float] = []
        for arg in args:
            for val in self._expand_range(arg):
                if val.is_number:
                    numbers.append(val.raw)
                elif val.is_boolean:
                    numbers.append(1.0 if val.raw else 0.0)
                # Skip empty and string values (standard spreadsheet behavior)
        return numbers

    def _eval_function(self, node: FunctionCallNode) -> CellValue:
        """Evaluate a function call node."""
        func = self._functions.get(node.name)
        if func is None:
            return CellValue.error(f"#NAME? Unknown function: {node.name}")
        return func(node.args)

    # ------------------------------------------------------------------
    # Built-in Function Table
    # ------------------------------------------------------------------

    def _build_function_table(
        self,
    ) -> dict[str, Callable[[list[FormulaNode]], CellValue]]:
        """Construct the built-in function dispatch table."""
        return {
            "SUM": self._fn_sum,
            "AVERAGE": self._fn_average,
            "COUNT": self._fn_count,
            "MAX": self._fn_max,
            "MIN": self._fn_min,
            "IF": self._fn_if,
            "AND": self._fn_and,
            "OR": self._fn_or,
            "NOT": self._fn_not,
            "CONCATENATE": self._fn_concatenate,
            "LEN": self._fn_len,
            "ABS": self._fn_abs,
            "MOD": self._fn_mod,
            "POWER": self._fn_power,
            "ROUND": self._fn_round,
            "UPPER": self._fn_upper,
            "LOWER": self._fn_lower,
            "FIZZBUZZ": self._fn_fizzbuzz,
            "FIZZBUZZ_COST": self._fn_fizzbuzz_cost,
            "FIZZBUZZ_TAX": self._fn_fizzbuzz_tax,
        }

    def _fn_sum(self, args: list[FormulaNode]) -> CellValue:
        """SUM: sum of all numeric values in the arguments."""
        numbers = self._collect_numeric(args)
        return CellValue.number(sum(numbers))

    def _fn_average(self, args: list[FormulaNode]) -> CellValue:
        """AVERAGE: arithmetic mean of all numeric values."""
        numbers = self._collect_numeric(args)
        if not numbers:
            return CellValue.error("#DIV/0!")
        return CellValue.number(sum(numbers) / len(numbers))

    def _fn_count(self, args: list[FormulaNode]) -> CellValue:
        """COUNT: count of numeric values in the arguments."""
        numbers = self._collect_numeric(args)
        return CellValue.number(float(len(numbers)))

    def _fn_max(self, args: list[FormulaNode]) -> CellValue:
        """MAX: maximum numeric value."""
        numbers = self._collect_numeric(args)
        if not numbers:
            return CellValue.number(0.0)
        return CellValue.number(max(numbers))

    def _fn_min(self, args: list[FormulaNode]) -> CellValue:
        """MIN: minimum numeric value."""
        numbers = self._collect_numeric(args)
        if not numbers:
            return CellValue.number(0.0)
        return CellValue.number(min(numbers))

    def _fn_if(self, args: list[FormulaNode]) -> CellValue:
        """IF(condition, value_if_true, value_if_false)."""
        if len(args) < 2 or len(args) > 3:
            return CellValue.error("#ERROR! IF requires 2-3 arguments")
        cond = self._eval(args[0])
        if cond.is_error:
            return cond
        # Truthiness: non-zero numbers, TRUE, non-empty strings
        is_true = False
        if cond.is_boolean:
            is_true = cond.raw
        elif cond.is_number:
            is_true = cond.raw != 0.0
        elif cond.is_string:
            is_true = len(cond.raw) > 0
        if is_true:
            return self._eval(args[1])
        if len(args) == 3:
            return self._eval(args[2])
        return CellValue.boolean(False)

    def _fn_and(self, args: list[FormulaNode]) -> CellValue:
        """AND: logical AND of all arguments."""
        for arg in args:
            val = self._eval(arg)
            if val.is_error:
                return val
            if val.is_boolean and not val.raw:
                return CellValue.boolean(False)
            if val.is_number and val.raw == 0.0:
                return CellValue.boolean(False)
        return CellValue.boolean(True)

    def _fn_or(self, args: list[FormulaNode]) -> CellValue:
        """OR: logical OR of all arguments."""
        for arg in args:
            val = self._eval(arg)
            if val.is_error:
                return val
            if val.is_boolean and val.raw:
                return CellValue.boolean(True)
            if val.is_number and val.raw != 0.0:
                return CellValue.boolean(True)
        return CellValue.boolean(False)

    def _fn_not(self, args: list[FormulaNode]) -> CellValue:
        """NOT: logical negation."""
        if len(args) != 1:
            return CellValue.error("#ERROR! NOT requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        if val.is_boolean:
            return CellValue.boolean(not val.raw)
        if val.is_number:
            return CellValue.boolean(val.raw == 0.0)
        return CellValue.error("#VALUE! NOT requires boolean or number")

    def _fn_concatenate(self, args: list[FormulaNode]) -> CellValue:
        """CONCATENATE: join all arguments as strings."""
        parts: list[str] = []
        for arg in args:
            val = self._eval(arg)
            if val.is_error:
                return val
            parts.append(val.to_string())
        return CellValue.string("".join(parts))

    def _fn_len(self, args: list[FormulaNode]) -> CellValue:
        """LEN: length of the string representation."""
        if len(args) != 1:
            return CellValue.error("#ERROR! LEN requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        return CellValue.number(float(len(val.to_string())))

    def _fn_abs(self, args: list[FormulaNode]) -> CellValue:
        """ABS: absolute value."""
        if len(args) != 1:
            return CellValue.error("#ERROR! ABS requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        return CellValue.number(abs(val.to_number()))

    def _fn_mod(self, args: list[FormulaNode]) -> CellValue:
        """MOD(number, divisor): modulo operation."""
        if len(args) != 2:
            return CellValue.error("#ERROR! MOD requires 2 arguments")
        num = self._eval(args[0])
        div = self._eval(args[1])
        if num.is_error:
            return num
        if div.is_error:
            return div
        divisor = div.to_number()
        if divisor == 0.0:
            return CellValue.error("#DIV/0!")
        return CellValue.number(math.fmod(num.to_number(), divisor))

    def _fn_power(self, args: list[FormulaNode]) -> CellValue:
        """POWER(base, exponent): exponentiation."""
        if len(args) != 2:
            return CellValue.error("#ERROR! POWER requires 2 arguments")
        base = self._eval(args[0])
        exp = self._eval(args[1])
        if base.is_error:
            return base
        if exp.is_error:
            return exp
        return CellValue.number(base.to_number() ** exp.to_number())

    def _fn_round(self, args: list[FormulaNode]) -> CellValue:
        """ROUND(number, digits): round to n decimal places."""
        if len(args) != 2:
            return CellValue.error("#ERROR! ROUND requires 2 arguments")
        num = self._eval(args[0])
        digits = self._eval(args[1])
        if num.is_error:
            return num
        if digits.is_error:
            return digits
        return CellValue.number(round(num.to_number(), int(digits.to_number())))

    def _fn_upper(self, args: list[FormulaNode]) -> CellValue:
        """UPPER: convert to uppercase."""
        if len(args) != 1:
            return CellValue.error("#ERROR! UPPER requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        return CellValue.string(val.to_string().upper())

    def _fn_lower(self, args: list[FormulaNode]) -> CellValue:
        """LOWER: convert to lowercase."""
        if len(args) != 1:
            return CellValue.error("#ERROR! LOWER requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        return CellValue.string(val.to_string().lower())

    def _fn_fizzbuzz(self, args: list[FormulaNode]) -> CellValue:
        """FIZZBUZZ(n): evaluate n through the FizzBuzz classification rules.

        Returns:
            "FizzBuzz" if n divisible by both 3 and 5.
            "Fizz" if n divisible by 3 only.
            "Buzz" if n divisible by 5 only.
            The number itself otherwise.
        """
        if len(args) != 1:
            return CellValue.error("#ERROR! FIZZBUZZ requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        n = int(val.to_number())
        if n % 15 == 0:
            return CellValue.string("FizzBuzz")
        if n % 3 == 0:
            return CellValue.string("Fizz")
        if n % 5 == 0:
            return CellValue.string("Buzz")
        return CellValue.number(float(n))

    def _fn_fizzbuzz_cost(self, args: list[FormulaNode]) -> CellValue:
        """FIZZBUZZ_COST(n): compute the FinOps evaluation cost in FizzBucks.

        The cost model mirrors the FizzBuzz Tax Authority's fee schedule:
        - FizzBuzz: 0.15 FB$ (premium classification, premium price)
        - Fizz:     0.03 FB$ (base divisibility surcharge)
        - Buzz:     0.05 FB$ (secondary divisibility surcharge)
        - Plain:    0.01 FB$ (existence fee — even non-matches have a cost)
        """
        if len(args) != 1:
            return CellValue.error("#ERROR! FIZZBUZZ_COST requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        n = int(val.to_number())
        if n % 15 == 0:
            return CellValue.number(0.15)
        if n % 3 == 0:
            return CellValue.number(0.03)
        if n % 5 == 0:
            return CellValue.number(0.05)
        return CellValue.number(0.01)

    def _fn_fizzbuzz_tax(self, args: list[FormulaNode]) -> CellValue:
        """FIZZBUZZ_TAX(n): return the FizzBuzz tax rate for n.

        Tax rates are set by the FizzBuzz Tax Authority and correspond
        directly to the divisibility properties of the number:
        - FizzBuzz: 15% (divisible by 15, taxed at 15%)
        - Fizz:     3%  (divisible by 3, taxed at 3%)
        - Buzz:     5%  (divisible by 5, taxed at 5%)
        - Plain:    0%  (no divisibility, no taxation)
        """
        if len(args) != 1:
            return CellValue.error("#ERROR! FIZZBUZZ_TAX requires 1 argument")
        val = self._eval(args[0])
        if val.is_error:
            return val
        n = int(val.to_number())
        if n % 15 == 0:
            return CellValue.number(0.15)
        if n % 3 == 0:
            return CellValue.number(0.03)
        if n % 5 == 0:
            return CellValue.number(0.05)
        return CellValue.number(0.0)


# ---------------------------------------------------------------------------
# Cell Storage
# ---------------------------------------------------------------------------


@dataclass
class Cell:
    """A single cell in the spreadsheet.

    Stores the raw input (either a literal value or a formula string),
    the parsed formula AST (if applicable), and the computed value.
    """

    raw_input: str = ""
    formula: Optional[FormulaNode] = None
    value: CellValue = field(default_factory=CellValue.empty)
    is_formula: bool = False


# ---------------------------------------------------------------------------
# Spreadsheet
# ---------------------------------------------------------------------------


class Spreadsheet:
    """A grid-based spreadsheet with formula evaluation and dependency tracking.

    Supports A1-style cell addressing, automatic recalculation on cell changes,
    topological recalculation ordering via Kahn's algorithm, circular reference
    detection, and insert/delete operations for rows and columns.

    The spreadsheet maintains internal consistency: every set operation triggers
    dependency graph updates and incremental recalculation of all affected cells.
    """

    def __init__(self) -> None:
        self._cells: dict[str, Cell] = {}
        self._graph = DependencyGraph()
        self._parser_cache: dict[str, FormulaNode] = {}
        self._function_usage: dict[str, int] = defaultdict(int)
        self._eval_count: int = 0
        self._recalc_count: int = 0

    @property
    def dependency_graph(self) -> DependencyGraph:
        """Expose the dependency graph for inspection."""
        return self._graph

    @property
    def function_usage(self) -> dict[str, int]:
        """Return function call counts."""
        return dict(self._function_usage)

    @property
    def eval_count(self) -> int:
        """Total number of cell evaluations performed."""
        return self._eval_count

    @property
    def recalc_count(self) -> int:
        """Total number of recalculation passes performed."""
        return self._recalc_count

    def set_cell(self, ref: Union[str, CellRef], value: str) -> None:
        """Set a cell's value or formula.

        If the value starts with '=', it is treated as a formula and parsed
        into an AST. Otherwise, it is stored as a literal. After setting,
        the cell and all its dependents are recalculated.

        Args:
            ref: Cell reference (string like "A1" or CellRef object).
            value: The raw input string.
        """
        if isinstance(ref, str):
            ref = CellRef.from_string(ref)

        key = str(ref)
        cell = Cell(raw_input=value)

        # Remove old dependencies (but keep dependents intact for cascading)
        self._graph.remove_own_dependencies(key)

        if value.startswith("="):
            # Parse formula
            parser = FormulaParser(value)
            try:
                ast = parser.parse()
            except SpreadsheetError as exc:
                cell.value = CellValue.error(f"#PARSE! {exc}")
                self._cells[key] = cell
                return

            cell.formula = ast
            cell.is_formula = True

            # Track function usage
            self._track_functions(ast)

            # Extract dependencies
            deps = self._extract_references(ast)
            for dep_key in deps:
                self._graph.add_dependency(key, dep_key)

            # Check for circular references
            detector = CircularReferenceDetector(self._graph)
            if detector.has_cycle():
                cell.value = CellValue.error("#CIRCULAR!")
                cell.formula = None
                cell.is_formula = False
                self._graph.remove_cell(key)
                self._cells[key] = cell
                return

        else:
            # Literal value
            cell.value = self._parse_literal(value)

        self._cells[key] = cell

        # Recalculate this cell and all dependents
        self._recalculate(key)

    def get_cell(self, ref: Union[str, CellRef]) -> CellValue:
        """Get the computed value of a cell.

        Args:
            ref: Cell reference (string like "A1" or CellRef object).

        Returns:
            The cell's computed value, or CellValue.empty() if the cell
            has not been set.
        """
        if isinstance(ref, str):
            ref = CellRef.from_string(ref)
        key = str(ref)
        cell = self._cells.get(key)
        if cell is None:
            return CellValue.empty()
        return cell.value

    def get_raw(self, ref: Union[str, CellRef]) -> str:
        """Get the raw input string of a cell."""
        if isinstance(ref, str):
            ref = CellRef.from_string(ref)
        key = str(ref)
        cell = self._cells.get(key)
        if cell is None:
            return ""
        return cell.raw_input

    def get_all_cells(self) -> dict[str, Cell]:
        """Return a copy of all cells."""
        return dict(self._cells)

    def clear_cell(self, ref: Union[str, CellRef]) -> None:
        """Clear a cell, removing its value and dependencies."""
        if isinstance(ref, str):
            ref = CellRef.from_string(ref)
        key = str(ref)
        dependents = self._graph.get_dependents(key)
        self._graph.remove_cell(key)
        self._cells.pop(key, None)
        # Recalculate dependents
        for dep_key in dependents:
            self._recalculate(dep_key)

    def insert_row(self, before_row: int) -> None:
        """Insert a new empty row, shifting existing rows down.

        All cell references and formulas are updated to reflect the new
        row positions. This is the spreadsheet equivalent of an online
        schema migration — except the stakes are even higher, because
        a misplaced FizzBuzz result could cascade through the entire
        analytics pipeline.
        """
        if not (1 <= before_row <= MAX_ROWS):
            raise SpreadsheetRangeError(
                f"Cannot insert row at position {before_row}"
            )
        self._shift_rows(before_row, delta=1)

    def delete_row(self, row: int) -> None:
        """Delete a row, shifting rows above it up."""
        if not (1 <= row <= MAX_ROWS):
            raise SpreadsheetRangeError(f"Cannot delete row {row}")
        # Remove cells in the target row
        to_remove = [
            key for key, cell in self._cells.items()
            if CellRef.from_string(key).row == row
        ]
        for key in to_remove:
            self.clear_cell(key)
        self._shift_rows(row + 1, delta=-1)

    def insert_column(self, before_col: str) -> None:
        """Insert a new empty column, shifting existing columns right."""
        before_col = before_col.upper()
        if before_col not in COLUMN_LETTERS:
            raise SpreadsheetRangeError(
                f"Cannot insert column at position {before_col!r}"
            )
        col_idx = COLUMN_LETTERS.index(before_col)
        self._shift_columns(col_idx, delta=1)

    def delete_column(self, col: str) -> None:
        """Delete a column, shifting columns to the right left."""
        col = col.upper()
        if col not in COLUMN_LETTERS:
            raise SpreadsheetRangeError(f"Cannot delete column {col!r}")
        col_idx = COLUMN_LETTERS.index(col)
        # Remove cells in the target column
        to_remove = [
            key for key, cell in self._cells.items()
            if CellRef.from_string(key).col == col
        ]
        for key in to_remove:
            self.clear_cell(key)
        self._shift_columns(col_idx + 1, delta=-1)

    def recalculate_all(self) -> None:
        """Force a full recalculation of all formula cells."""
        formula_keys = [
            key for key, cell in self._cells.items() if cell.is_formula
        ]
        if not formula_keys:
            return

        try:
            order = self._graph.topological_order(set(formula_keys))
        except SpreadsheetCircularReferenceError:
            for key in formula_keys:
                self._cells[key].value = CellValue.error("#CIRCULAR!")
            return

        for key in order:
            cell = self._cells.get(key)
            if cell and cell.is_formula and cell.formula:
                evaluator = FormulaEvaluator(self._cell_getter)
                cell.value = evaluator.evaluate(cell.formula)
                self._eval_count += 1

        self._recalc_count += 1

    def get_used_range(self) -> tuple[CellRef, CellRef]:
        """Return the bounding box of all non-empty cells.

        Returns:
            A tuple of (top_left, bottom_right) CellRefs.
        """
        if not self._cells:
            return CellRef("A", 1), CellRef("A", 1)

        min_col = MAX_COLUMNS
        max_col = 0
        min_row = MAX_ROWS + 1
        max_row = 0

        for key in self._cells:
            ref = CellRef.from_string(key)
            col_idx = ref.col_index
            min_col = min(min_col, col_idx)
            max_col = max(max_col, col_idx)
            min_row = min(min_row, ref.row)
            max_row = max(max_row, ref.row)

        return (
            CellRef(COLUMN_LETTERS[min_col], min_row),
            CellRef(COLUMN_LETTERS[max_col], max_row),
        )

    # ------------------------------------------------------------------
    # Internal Methods
    # ------------------------------------------------------------------

    def _cell_getter(self, ref: CellRef) -> CellValue:
        """Callback for the formula evaluator to read cell values."""
        return self.get_cell(ref)

    def _recalculate(self, key: str) -> None:
        """Recalculate a cell and all downstream dependents."""
        try:
            order = self._graph.topological_order({key})
        except SpreadsheetCircularReferenceError:
            cell = self._cells.get(key)
            if cell:
                cell.value = CellValue.error("#CIRCULAR!")
            return

        for cell_key in order:
            cell = self._cells.get(cell_key)
            if cell is None:
                continue
            if cell.is_formula and cell.formula:
                evaluator = FormulaEvaluator(self._cell_getter)
                cell.value = evaluator.evaluate(cell.formula)
                self._eval_count += 1
            # Literal cells don't need re-evaluation

        self._recalc_count += 1

    def _parse_literal(self, text: str) -> CellValue:
        """Parse a literal cell value string."""
        if not text:
            return CellValue.empty()
        upper = text.strip().upper()
        if upper == "TRUE":
            return CellValue.boolean(True)
        if upper == "FALSE":
            return CellValue.boolean(False)
        try:
            return CellValue.number(float(text))
        except ValueError:
            return CellValue.string(text)

    def _extract_references(self, node: FormulaNode) -> set[str]:
        """Extract all cell references from a formula AST."""
        refs: set[str] = set()
        self._walk_refs(node, refs)
        return refs

    def _walk_refs(self, node: FormulaNode, refs: set[str]) -> None:
        """Recursively collect cell references from the AST."""
        if isinstance(node, CellRefNode):
            refs.add(str(node.ref))
        elif isinstance(node, RangeNode):
            start_col = node.start.col_index
            end_col = node.end.col_index
            start_row = node.start.row
            end_row = node.end.row
            for row in range(min(start_row, end_row), max(start_row, end_row) + 1):
                for col_idx in range(min(start_col, end_col), max(start_col, end_col) + 1):
                    refs.add(f"{COLUMN_LETTERS[col_idx]}{row}")
        elif isinstance(node, FunctionCallNode):
            for arg in node.args:
                self._walk_refs(arg, refs)
        elif isinstance(node, BinaryOpNode):
            self._walk_refs(node.left, refs)
            self._walk_refs(node.right, refs)
        elif isinstance(node, UnaryOpNode):
            self._walk_refs(node.operand, refs)

    def _track_functions(self, node: FormulaNode) -> None:
        """Track function usage statistics."""
        if isinstance(node, FunctionCallNode):
            self._function_usage[node.name] += 1
            for arg in node.args:
                self._track_functions(arg)
        elif isinstance(node, BinaryOpNode):
            self._track_functions(node.left)
            self._track_functions(node.right)
        elif isinstance(node, UnaryOpNode):
            self._track_functions(node.operand)

    def _shift_rows(self, from_row: int, delta: int) -> None:
        """Shift all cells at or below `from_row` by `delta` rows."""
        # Collect cells to move
        to_move: list[tuple[str, Cell]] = []
        to_remove: list[str] = []
        for key, cell in list(self._cells.items()):
            ref = CellRef.from_string(key)
            if ref.row >= from_row:
                to_remove.append(key)
                new_row = ref.row + delta
                if 1 <= new_row <= MAX_ROWS:
                    to_move.append((f"{ref.col}{new_row}", cell))

        for key in to_remove:
            self._graph.remove_cell(key)
            del self._cells[key]

        for key, cell in to_move:
            self._cells[key] = cell

        # Re-parse all formulas to update references
        self._rebuild_all_formulas()

    def _shift_columns(self, from_col_idx: int, delta: int) -> None:
        """Shift all cells at or right of `from_col_idx` by `delta` columns."""
        to_move: list[tuple[str, Cell]] = []
        to_remove: list[str] = []
        for key, cell in list(self._cells.items()):
            ref = CellRef.from_string(key)
            if ref.col_index >= from_col_idx:
                to_remove.append(key)
                new_col_idx = ref.col_index + delta
                if 0 <= new_col_idx < MAX_COLUMNS:
                    new_key = f"{COLUMN_LETTERS[new_col_idx]}{ref.row}"
                    to_move.append((new_key, cell))

        for key in to_remove:
            self._graph.remove_cell(key)
            del self._cells[key]

        for key, cell in to_move:
            self._cells[key] = cell

        self._rebuild_all_formulas()

    def _rebuild_all_formulas(self) -> None:
        """Re-parse and re-evaluate all formula cells.

        Called after structural changes (insert/delete rows/columns) to
        ensure all cell references in formulas point to the correct cells.
        Note: This re-parses the original raw_input, so formulas use their
        original references. For a production system, references would be
        rewritten. Here, we simply re-evaluate in place.
        """
        # Rebuild dependency graph
        self._graph = DependencyGraph()
        formula_cells: list[str] = []
        for key, cell in self._cells.items():
            if cell.is_formula:
                formula_cells.append(key)
                if cell.formula:
                    deps = self._extract_references(cell.formula)
                    for dep_key in deps:
                        self._graph.add_dependency(key, dep_key)

        # Recalculate all
        self.recalculate_all()


# ---------------------------------------------------------------------------
# Spreadsheet Renderer
# ---------------------------------------------------------------------------


class SpreadsheetRenderer:
    """ASCII table renderer for spreadsheet grids.

    Produces formatted output with auto-width columns, aligned headers,
    and properly padded cell values. Suitable for terminal display of
    FizzBuzz analytics data.
    """

    def __init__(self, min_col_width: int = 8, max_col_width: int = 20) -> None:
        self._min_width = min_col_width
        self._max_width = max_col_width

    def render(self, sheet: Spreadsheet) -> str:
        """Render the spreadsheet's used range as an ASCII table."""
        top_left, bottom_right = sheet.get_used_range()
        if not sheet.get_all_cells():
            return "  (empty spreadsheet)"

        start_col = top_left.col_index
        end_col = bottom_right.col_index
        start_row = top_left.row
        end_row = bottom_right.row

        # Compute column widths
        col_widths: dict[int, int] = {}
        for col_idx in range(start_col, end_col + 1):
            col_letter = COLUMN_LETTERS[col_idx]
            max_w = max(len(col_letter), self._min_width)
            for row in range(start_row, end_row + 1):
                ref = CellRef(col_letter, row)
                val = sheet.get_cell(ref)
                display = val.to_string()
                max_w = max(max_w, len(display))
            col_widths[col_idx] = min(max_w, self._max_width)

        # Row number width
        row_num_width = max(3, len(str(end_row)))

        lines: list[str] = []

        # Header row
        header_parts = [" " * row_num_width]
        for col_idx in range(start_col, end_col + 1):
            col_letter = COLUMN_LETTERS[col_idx]
            width = col_widths[col_idx]
            header_parts.append(col_letter.center(width))
        lines.append("  " + " | ".join(header_parts))

        # Separator
        sep_parts = ["-" * row_num_width]
        for col_idx in range(start_col, end_col + 1):
            sep_parts.append("-" * col_widths[col_idx])
        lines.append("  " + "-+-".join(sep_parts))

        # Data rows
        for row in range(start_row, end_row + 1):
            row_parts = [str(row).rjust(row_num_width)]
            for col_idx in range(start_col, end_col + 1):
                col_letter = COLUMN_LETTERS[col_idx]
                ref = CellRef(col_letter, row)
                val = sheet.get_cell(ref)
                display = val.to_string()
                if len(display) > self._max_width:
                    display = display[: self._max_width - 1] + "~"
                width = col_widths[col_idx]
                # Right-align numbers, left-align everything else
                if val.is_number:
                    row_parts.append(display.rjust(width))
                else:
                    row_parts.append(display.ljust(width))
            lines.append("  " + " | ".join(row_parts))

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Spreadsheet Dashboard
# ---------------------------------------------------------------------------


class SpreadsheetDashboard:
    """ASCII dashboard displaying spreadsheet analytics.

    Provides at-a-glance metrics about the spreadsheet, including cell
    counts by type, function usage frequency, dependency graph statistics,
    and evaluation performance counters.
    """

    @staticmethod
    def render(sheet: Spreadsheet, width: int = 60) -> str:
        """Render the FizzSheet dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        title_line = "|" + " FIZZSHEET: SPREADSHEET ENGINE DASHBOARD ".center(width - 2) + "|"

        lines.append(border)
        lines.append(title_line)
        lines.append(border)

        # Cell statistics
        all_cells = sheet.get_all_cells()
        total = len(all_cells)
        formulas = sum(1 for c in all_cells.values() if c.is_formula)
        literals = total - formulas
        errors = sum(1 for c in all_cells.values() if c.value.is_error)
        numbers = sum(1 for c in all_cells.values() if c.value.is_number)
        strings = sum(1 for c in all_cells.values() if c.value.is_string)
        booleans = sum(1 for c in all_cells.values() if c.value.is_boolean)

        lines.append("|" + " Cell Statistics".ljust(width - 2) + "|")
        lines.append("|" + ("-" * (width - 2)) + "|")
        stats = [
            ("Total cells", str(total)),
            ("Formula cells", str(formulas)),
            ("Literal cells", str(literals)),
            ("Numeric values", str(numbers)),
            ("String values", str(strings)),
            ("Boolean values", str(booleans)),
            ("Error values", str(errors)),
        ]
        for label, value in stats:
            content = f"  {label}: {value}"
            lines.append("|" + content.ljust(width - 2) + "|")

        # Function usage
        usage = sheet.function_usage
        if usage:
            lines.append("|" + " " * (width - 2) + "|")
            lines.append("|" + " Function Usage".ljust(width - 2) + "|")
            lines.append("|" + ("-" * (width - 2)) + "|")
            for func_name in sorted(usage.keys()):
                count = usage[func_name]
                content = f"  {func_name}: {count} call{'s' if count != 1 else ''}"
                lines.append("|" + content.ljust(width - 2) + "|")

        # Dependency graph stats
        graph = sheet.dependency_graph
        lines.append("|" + " " * (width - 2) + "|")
        lines.append("|" + " Dependency Graph".ljust(width - 2) + "|")
        lines.append("|" + ("-" * (width - 2)) + "|")
        edges = graph.all_edges
        dep_stats = [
            ("Nodes", str(graph.cell_count)),
            ("Edges", str(len(edges))),
        ]
        for label, value in dep_stats:
            content = f"  {label}: {value}"
            lines.append("|" + content.ljust(width - 2) + "|")

        # Edge list (up to 10)
        if edges:
            shown = edges[:10]
            for src, dst in shown:
                content = f"    {src} -> {dst}"
                lines.append("|" + content.ljust(width - 2) + "|")
            if len(edges) > 10:
                content = f"    ... and {len(edges) - 10} more"
                lines.append("|" + content.ljust(width - 2) + "|")

        # Performance
        lines.append("|" + " " * (width - 2) + "|")
        lines.append("|" + " Performance".ljust(width - 2) + "|")
        lines.append("|" + ("-" * (width - 2)) + "|")
        perf_stats = [
            ("Cell evaluations", str(sheet.eval_count)),
            ("Recalculation passes", str(sheet.recalc_count)),
        ]
        for label, value in perf_stats:
            content = f"  {label}: {value}"
            lines.append("|" + content.ljust(width - 2) + "|")

        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Spreadsheet Middleware
# ---------------------------------------------------------------------------


class SpreadsheetMiddleware(IMiddleware):
    """Middleware that populates a spreadsheet with FizzBuzz evaluation results.

    Intercepts each evaluation in the middleware pipeline and records the
    result into the spreadsheet grid. Each number gets its own row, with
    columns for the input number, the FizzBuzz output, the classification
    cost, and the tax rate.

    Column layout:
    - A: Input number
    - B: FizzBuzz classification (formula: =FIZZBUZZ(A{row}))
    - C: Evaluation cost in FizzBucks (formula: =FIZZBUZZ_COST(A{row}))
    - D: Tax rate (formula: =FIZZBUZZ_TAX(A{row}))
    """

    def __init__(
        self,
        spreadsheet: Optional[Spreadsheet] = None,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._sheet = spreadsheet or Spreadsheet()
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus
        self._row_counter = 1
        self._initialized = False

    @property
    def spreadsheet(self) -> Spreadsheet:
        """Access the underlying spreadsheet instance."""
        return self._sheet

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the evaluation context and record results in the spreadsheet."""
        # Initialize header row on first call
        if not self._initialized:
            self._sheet.set_cell("A1", "Number")
            self._sheet.set_cell("B1", "Classification")
            self._sheet.set_cell("C1", "Cost (FB$)")
            self._sheet.set_cell("D1", "Tax Rate")
            self._row_counter = 2
            self._initialized = True

        # Call the next handler first
        context = next_handler(context)

        # Record the evaluation
        row = self._row_counter
        if row <= MAX_ROWS:
            self._sheet.set_cell(f"A{row}", str(context.number))
            self._sheet.set_cell(f"B{row}", f"=FIZZBUZZ(A{row})")
            self._sheet.set_cell(f"C{row}", f"=FIZZBUZZ_COST(A{row})")
            self._sheet.set_cell(f"D{row}", f"=FIZZBUZZ_TAX(A{row})")
            self._row_counter += 1

        return context

    def get_name(self) -> str:
        return "SpreadsheetMiddleware"

    def get_priority(self) -> int:
        return 8


# ---------------------------------------------------------------------------
# Standalone Formula Evaluation (for --sheet-formula)
# ---------------------------------------------------------------------------


def evaluate_formula(formula: str) -> CellValue:
    """Evaluate a standalone formula without a spreadsheet context.

    Creates a temporary empty spreadsheet and evaluates the formula
    in a reserved evaluation cell (Z999) that is unlikely to conflict
    with cell references in the formula itself.
    """
    sheet = Spreadsheet()
    eval_cell = "Z999"
    sheet.set_cell(eval_cell, formula)
    return sheet.get_cell(eval_cell)

"""
Enterprise FizzBuzz Platform - FizzSQL Relational Query Engine

Implements a fully relational SQL engine for querying FizzBuzz
platform internals, because accessing Python attributes directly
is the kind of unstructured data access that gives database
administrators nightmares.

FizzSQL provides:
  - A lexer that tokenizes SQL queries with the gravitas of Oracle
  - A recursive descent parser that produces an AST
  - A logical planner that builds operator trees
  - A physical planner that maps logical to physical operators
  - A Volcano-model executor (open/next/close iterator protocol)
  - 5 virtual tables over platform internals
  - EXPLAIN ANALYZE with cost estimates and actual row counts
  - ASCII result formatting with auto-width columns
  - A dashboard with query history and slow query log

Supported SQL subset:
  SELECT [columns | * | aggregates] FROM table
  [WHERE condition] [GROUP BY columns] [ORDER BY columns [ASC|DESC]]
  [LIMIT n] [OFFSET n]
  EXPLAIN ANALYZE SELECT ...
  SHOW TABLES

All data lives in memory. There is no persistence layer. The
query optimizer has a cost model derived from nothing. The
estimated costs are fictional. This is enterprise-grade.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Iterator, Optional, Sequence

from enterprise_fizzbuzz.domain.exceptions import (
    FizzSQLError,
    FizzSQLExecutionError,
    FizzSQLSyntaxError,
    FizzSQLTableNotFoundError,
)

logger = logging.getLogger(__name__)


# ============================================================
# Token Types & Lexer
# ============================================================


class TokenType(Enum):
    """SQL token types recognized by the FizzSQL lexer.

    Every keyword, operator, and literal gets its own enum variant
    because stringly-typed parsing is how SQL injection happens.
    (We are parsing our own SQL. The injection would be from ourselves.)
    """

    # Keywords
    SELECT = auto()
    FROM = auto()
    WHERE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    ORDER = auto()
    BY = auto()
    ASC = auto()
    DESC = auto()
    LIMIT = auto()
    OFFSET = auto()
    GROUP = auto()
    HAVING = auto()
    AS = auto()
    EXPLAIN = auto()
    ANALYZE = auto()
    SHOW = auto()
    TABLES = auto()
    NULL = auto()
    IS = auto()
    IN = auto()
    LIKE = auto()
    BETWEEN = auto()
    COUNT = auto()
    SUM = auto()
    AVG = auto()
    MIN = auto()
    MAX = auto()
    DISTINCT = auto()

    # Literals & identifiers
    IDENTIFIER = auto()
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()

    # Operators & punctuation
    STAR = auto()         # *
    COMMA = auto()        # ,
    DOT = auto()          # .
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    EQ = auto()           # =
    NEQ = auto()          # != or <>
    LT = auto()           # <
    GT = auto()           # >
    LTE = auto()          # <=
    GTE = auto()          # >=
    PLUS = auto()         # +
    MINUS = auto()        # -
    SLASH = auto()        # /
    PERCENT = auto()      # %

    # Special
    EOF = auto()


@dataclass(frozen=True)
class Token:
    """A lexical token produced by the FizzSQL lexer.

    Carries its type, raw value, and position in the source query
    so that error messages can point at the exact character where
    the parser lost the will to continue.
    """

    token_type: TokenType
    value: str
    position: int


# Keyword lookup table
_KEYWORDS: dict[str, TokenType] = {
    "SELECT": TokenType.SELECT,
    "FROM": TokenType.FROM,
    "WHERE": TokenType.WHERE,
    "AND": TokenType.AND,
    "OR": TokenType.OR,
    "NOT": TokenType.NOT,
    "ORDER": TokenType.ORDER,
    "BY": TokenType.BY,
    "ASC": TokenType.ASC,
    "DESC": TokenType.DESC,
    "LIMIT": TokenType.LIMIT,
    "OFFSET": TokenType.OFFSET,
    "GROUP": TokenType.GROUP,
    "HAVING": TokenType.HAVING,
    "AS": TokenType.AS,
    "EXPLAIN": TokenType.EXPLAIN,
    "ANALYZE": TokenType.ANALYZE,
    "SHOW": TokenType.SHOW,
    "TABLES": TokenType.TABLES,
    "NULL": TokenType.NULL,
    "IS": TokenType.IS,
    "IN": TokenType.IN,
    "LIKE": TokenType.LIKE,
    "BETWEEN": TokenType.BETWEEN,
    "COUNT": TokenType.COUNT,
    "SUM": TokenType.SUM,
    "AVG": TokenType.AVG,
    "MIN": TokenType.MIN,
    "MAX": TokenType.MAX,
    "DISTINCT": TokenType.DISTINCT,
}


class SQLLexer:
    """Tokenizer for the FizzSQL query language.

    Scans the input string character by character, producing a
    stream of Token objects. Handles identifiers, keywords,
    strings (single-quoted), integers, floats, and all standard
    SQL comparison operators including the dreaded <> syntax
    that nobody likes but everyone supports.
    """

    def __init__(self, query: str) -> None:
        self._query = query
        self._pos = 0
        self._tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Scan the entire query and return a list of tokens."""
        self._tokens = []
        self._pos = 0

        while self._pos < len(self._query):
            ch = self._query[self._pos]

            # Skip whitespace
            if ch.isspace():
                self._pos += 1
                continue

            # Single-quoted string literal
            if ch == "'":
                self._read_string()
                continue

            # Number (integer or float)
            if ch.isdigit():
                self._read_number()
                continue

            # Identifier or keyword
            if ch.isalpha() or ch == "_":
                self._read_identifier()
                continue

            # Two-character operators
            if self._pos + 1 < len(self._query):
                two = self._query[self._pos : self._pos + 2]
                if two == "!=":
                    self._emit(TokenType.NEQ, two, 2)
                    continue
                if two == "<>":
                    self._emit(TokenType.NEQ, two, 2)
                    continue
                if two == "<=":
                    self._emit(TokenType.LTE, two, 2)
                    continue
                if two == ">=":
                    self._emit(TokenType.GTE, two, 2)
                    continue

            # Single-character operators
            singles: dict[str, TokenType] = {
                "*": TokenType.STAR,
                ",": TokenType.COMMA,
                ".": TokenType.DOT,
                "(": TokenType.LPAREN,
                ")": TokenType.RPAREN,
                "=": TokenType.EQ,
                "<": TokenType.LT,
                ">": TokenType.GT,
                "+": TokenType.PLUS,
                "-": TokenType.MINUS,
                "/": TokenType.SLASH,
                "%": TokenType.PERCENT,
            }

            if ch in singles:
                self._emit(singles[ch], ch, 1)
                continue

            raise FizzSQLSyntaxError(
                self._query, self._pos,
                f"Unexpected character: '{ch}'"
            )

        self._tokens.append(Token(TokenType.EOF, "", self._pos))
        return self._tokens

    def _emit(self, token_type: TokenType, value: str, length: int) -> None:
        """Emit a token and advance the position."""
        self._tokens.append(Token(token_type, value, self._pos))
        self._pos += length

    def _read_string(self) -> None:
        """Read a single-quoted string literal."""
        start = self._pos
        self._pos += 1  # skip opening quote
        chars: list[str] = []

        while self._pos < len(self._query):
            ch = self._query[self._pos]
            if ch == "'":
                # Check for escaped quote ('')
                if (self._pos + 1 < len(self._query)
                        and self._query[self._pos + 1] == "'"):
                    chars.append("'")
                    self._pos += 2
                else:
                    self._pos += 1  # skip closing quote
                    self._tokens.append(
                        Token(TokenType.STRING, "".join(chars), start)
                    )
                    return
            else:
                chars.append(ch)
                self._pos += 1

        raise FizzSQLSyntaxError(
            self._query, start, "Unterminated string literal"
        )

    def _read_number(self) -> None:
        """Read an integer or float literal."""
        start = self._pos
        has_dot = False

        while self._pos < len(self._query):
            ch = self._query[self._pos]
            if ch.isdigit():
                self._pos += 1
            elif ch == "." and not has_dot:
                has_dot = True
                self._pos += 1
            else:
                break

        value = self._query[start : self._pos]
        token_type = TokenType.FLOAT if has_dot else TokenType.INTEGER
        self._tokens.append(Token(token_type, value, start))

    def _read_identifier(self) -> None:
        """Read an identifier or keyword."""
        start = self._pos

        while self._pos < len(self._query):
            ch = self._query[self._pos]
            if ch.isalnum() or ch == "_":
                self._pos += 1
            else:
                break

        value = self._query[start : self._pos]
        upper = value.upper()

        token_type = _KEYWORDS.get(upper, TokenType.IDENTIFIER)
        self._tokens.append(Token(token_type, value, start))


# ============================================================
# AST Nodes
# ============================================================


@dataclass
class ColumnRef:
    """A reference to a column, possibly with a table qualifier."""

    name: str
    table: Optional[str] = None
    alias: Optional[str] = None


@dataclass
class AggregateExpr:
    """An aggregate function call (COUNT, SUM, AVG, MIN, MAX)."""

    function: str  # COUNT, SUM, AVG, MIN, MAX
    column: str    # column name or *
    alias: Optional[str] = None
    distinct: bool = False


@dataclass
class LiteralExpr:
    """A literal value (string, integer, float, NULL)."""

    value: Any
    data_type: str  # 'string', 'integer', 'float', 'null'


@dataclass
class ComparisonExpr:
    """A comparison expression (column op value)."""

    left: str  # column name
    operator: str  # =, !=, <, >, <=, >=, LIKE, IS
    right: Any  # literal value


@dataclass
class BooleanExpr:
    """A boolean combination of expressions (AND, OR, NOT)."""

    operator: str  # AND, OR, NOT
    left: Any  # ComparisonExpr or BooleanExpr
    right: Any = None  # None for NOT


@dataclass
class OrderByClause:
    """An ORDER BY specification."""

    column: str
    direction: str = "ASC"


@dataclass
class SelectStatement:
    """The AST node for a SELECT statement.

    Contains everything the planner needs to construct a query
    execution plan: columns to project, source table, filter
    predicate, grouping, ordering, and pagination. This is the
    parse tree that the recursive descent parser fought so hard
    to construct from your humble SQL string.
    """

    columns: list[ColumnRef | AggregateExpr]  # columns or aggregates
    table: str = ""
    where: Optional[ComparisonExpr | BooleanExpr] = None
    group_by: list[str] = field(default_factory=list)
    having: Optional[ComparisonExpr | BooleanExpr] = None
    order_by: list[OrderByClause] = field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None
    is_star: bool = False
    is_explain: bool = False
    is_show_tables: bool = False


# ============================================================
# Recursive Descent Parser
# ============================================================


class SQLParser:
    """Recursive descent parser for FizzSQL queries.

    Implements the following grammar (simplified):

        query       -> EXPLAIN ANALYZE? select | SHOW TABLES | select
        select      -> SELECT columns FROM table [where] [group_by]
                       [order_by] [limit] [offset]
        columns     -> STAR | column_list
        column_list -> column (COMMA column)*
        column      -> aggregate | IDENTIFIER [AS IDENTIFIER]
        aggregate   -> (COUNT|SUM|AVG|MIN|MAX) LPAREN [DISTINCT] (STAR|IDENTIFIER) RPAREN [AS IDENTIFIER]
        where       -> WHERE condition
        condition   -> comparison ((AND|OR) comparison)*
        comparison  -> IDENTIFIER op value | NOT comparison
        op          -> EQ | NEQ | LT | GT | LTE | GTE | LIKE | IS
        value       -> STRING | INTEGER | FLOAT | NULL
        group_by    -> GROUP BY identifier_list
        order_by    -> ORDER BY order_list
        order_list  -> order_item (COMMA order_item)*
        order_item  -> IDENTIFIER [ASC|DESC]
        limit       -> LIMIT INTEGER
        offset      -> OFFSET INTEGER

    Error messages attempt to be helpful. They are not always
    successful in this endeavor.
    """

    def __init__(self, tokens: list[Token], query: str) -> None:
        self._tokens = tokens
        self._query = query
        self._pos = 0

    def parse(self) -> SelectStatement:
        """Parse the token stream into a SelectStatement AST."""
        # SHOW TABLES
        if self._check(TokenType.SHOW):
            self._advance()
            self._expect(TokenType.TABLES, "Expected TABLES after SHOW")
            return SelectStatement(columns=[], is_show_tables=True)

        # EXPLAIN [ANALYZE]
        is_explain = False
        if self._check(TokenType.EXPLAIN):
            self._advance()
            is_explain = True
            if self._check(TokenType.ANALYZE):
                self._advance()

        stmt = self._parse_select()
        stmt.is_explain = is_explain

        if not self._check(TokenType.EOF):
            raise FizzSQLSyntaxError(
                self._query,
                self._current().position,
                f"Unexpected token: '{self._current().value}'"
            )

        return stmt

    def _parse_select(self) -> SelectStatement:
        """Parse a SELECT statement."""
        self._expect(TokenType.SELECT, "Expected SELECT")

        # Parse columns
        columns: list[ColumnRef | AggregateExpr] = []
        is_star = False

        if self._check(TokenType.STAR):
            is_star = True
            self._advance()
        else:
            columns = self._parse_column_list()

        # FROM
        self._expect(TokenType.FROM, "Expected FROM")
        table_token = self._expect(TokenType.IDENTIFIER, "Expected table name")
        table = table_token.value

        # Optional clauses
        where = None
        group_by: list[str] = []
        having = None
        order_by: list[OrderByClause] = []
        limit = None
        offset = None

        if self._check(TokenType.WHERE):
            self._advance()
            where = self._parse_condition()

        if self._check(TokenType.GROUP):
            self._advance()
            self._expect(TokenType.BY, "Expected BY after GROUP")
            group_by = self._parse_identifier_list()

        if self._check(TokenType.HAVING):
            self._advance()
            having = self._parse_condition()

        if self._check(TokenType.ORDER):
            self._advance()
            self._expect(TokenType.BY, "Expected BY after ORDER")
            order_by = self._parse_order_list()

        if self._check(TokenType.LIMIT):
            self._advance()
            limit_token = self._expect(TokenType.INTEGER, "Expected integer after LIMIT")
            limit = int(limit_token.value)

        if self._check(TokenType.OFFSET):
            self._advance()
            offset_token = self._expect(TokenType.INTEGER, "Expected integer after OFFSET")
            offset = int(offset_token.value)

        return SelectStatement(
            columns=columns,
            table=table,
            where=where,
            group_by=group_by,
            having=having,
            order_by=order_by,
            limit=limit,
            offset=offset,
            is_star=is_star,
        )

    def _parse_column_list(self) -> list[ColumnRef | AggregateExpr]:
        """Parse a comma-separated list of columns or aggregates."""
        cols: list[ColumnRef | AggregateExpr] = []
        cols.append(self._parse_column())

        while self._check(TokenType.COMMA):
            self._advance()
            cols.append(self._parse_column())

        return cols

    def _parse_column(self) -> ColumnRef | AggregateExpr:
        """Parse a single column reference or aggregate function."""
        # Check for aggregate functions
        agg_types = {
            TokenType.COUNT, TokenType.SUM, TokenType.AVG,
            TokenType.MIN, TokenType.MAX,
        }

        if self._current().token_type in agg_types:
            func_name = self._current().value.upper()
            self._advance()
            self._expect(TokenType.LPAREN, f"Expected ( after {func_name}")

            distinct = False
            if self._check(TokenType.DISTINCT):
                distinct = True
                self._advance()

            if self._check(TokenType.STAR):
                col_name = "*"
                self._advance()
            else:
                col_token = self._expect(
                    TokenType.IDENTIFIER,
                    f"Expected column name in {func_name}()"
                )
                col_name = col_token.value

            self._expect(TokenType.RPAREN, f"Expected ) after {func_name}({col_name})")

            alias = None
            if self._check(TokenType.AS):
                self._advance()
                alias_token = self._expect(
                    TokenType.IDENTIFIER, "Expected alias after AS"
                )
                alias = alias_token.value

            return AggregateExpr(
                function=func_name,
                column=col_name,
                alias=alias,
                distinct=distinct,
            )

        # Regular column
        col_token = self._expect(TokenType.IDENTIFIER, "Expected column name")
        name = col_token.value
        table = None

        # table.column syntax
        if self._check(TokenType.DOT):
            self._advance()
            inner = self._expect(TokenType.IDENTIFIER, "Expected column name after '.'")
            table = name
            name = inner.value

        alias = None
        if self._check(TokenType.AS):
            self._advance()
            alias_token = self._expect(
                TokenType.IDENTIFIER, "Expected alias after AS"
            )
            alias = alias_token.value

        return ColumnRef(name=name, table=table, alias=alias)

    def _parse_condition(self) -> ComparisonExpr | BooleanExpr:
        """Parse a WHERE or HAVING condition (supports AND/OR/NOT)."""
        left = self._parse_comparison()

        while self._check(TokenType.AND) or self._check(TokenType.OR):
            op = self._current().value.upper()
            self._advance()
            right = self._parse_comparison()
            left = BooleanExpr(operator=op, left=left, right=right)

        return left

    def _parse_comparison(self) -> ComparisonExpr | BooleanExpr:
        """Parse a single comparison (column op value) or NOT expression."""
        if self._check(TokenType.NOT):
            self._advance()
            inner = self._parse_comparison()
            return BooleanExpr(operator="NOT", left=inner)

        # Handle aggregate functions in HAVING (e.g., COUNT(*) > 1)
        agg_types = {
            TokenType.COUNT, TokenType.SUM, TokenType.AVG,
            TokenType.MIN, TokenType.MAX,
        }
        if self._current().token_type in agg_types:
            func_name = self._current().value.upper()
            self._advance()
            self._expect(TokenType.LPAREN, f"Expected ( after {func_name}")
            if self._check(TokenType.STAR):
                inner_col = "*"
                self._advance()
            else:
                inner_tok = self._expect(
                    TokenType.IDENTIFIER,
                    f"Expected column name in {func_name}()"
                )
                inner_col = inner_tok.value
            self._expect(TokenType.RPAREN, f"Expected ) after {func_name}({inner_col})")
            col_name = f"{func_name}({inner_col})"
        else:
            col_token = self._expect(TokenType.IDENTIFIER, "Expected column name in condition")
            col_name = col_token.value

        # IS [NOT] NULL
        if self._check(TokenType.IS):
            self._advance()
            if self._check(TokenType.NOT):
                self._advance()
                self._expect(TokenType.NULL, "Expected NULL after IS NOT")
                return ComparisonExpr(left=col_name, operator="IS NOT", right=None)
            self._expect(TokenType.NULL, "Expected NULL after IS")
            return ComparisonExpr(left=col_name, operator="IS", right=None)

        # LIKE
        if self._check(TokenType.LIKE):
            self._advance()
            val = self._parse_value()
            return ComparisonExpr(left=col_name, operator="LIKE", right=val)

        # IN (val, val, ...)
        if self._check(TokenType.IN):
            self._advance()
            self._expect(TokenType.LPAREN, "Expected ( after IN")
            values: list[Any] = []
            values.append(self._parse_value())
            while self._check(TokenType.COMMA):
                self._advance()
                values.append(self._parse_value())
            self._expect(TokenType.RPAREN, "Expected ) after IN list")
            return ComparisonExpr(left=col_name, operator="IN", right=values)

        # BETWEEN val AND val
        if self._check(TokenType.BETWEEN):
            self._advance()
            low = self._parse_value()
            self._expect(TokenType.AND, "Expected AND in BETWEEN expression")
            high = self._parse_value()
            return ComparisonExpr(
                left=col_name, operator="BETWEEN", right=(low, high)
            )

        # Standard comparison operators
        op_map = {
            TokenType.EQ: "=",
            TokenType.NEQ: "!=",
            TokenType.LT: "<",
            TokenType.GT: ">",
            TokenType.LTE: "<=",
            TokenType.GTE: ">=",
        }

        if self._current().token_type in op_map:
            op = op_map[self._current().token_type]
            self._advance()
            val = self._parse_value()
            return ComparisonExpr(left=col_name, operator=op, right=val)

        raise FizzSQLSyntaxError(
            self._query,
            self._current().position,
            f"Expected comparison operator, got '{self._current().value}'"
        )

    def _parse_value(self) -> Any:
        """Parse a literal value."""
        tok = self._current()

        if tok.token_type == TokenType.STRING:
            self._advance()
            return tok.value
        if tok.token_type == TokenType.INTEGER:
            self._advance()
            return int(tok.value)
        if tok.token_type == TokenType.FLOAT:
            self._advance()
            return float(tok.value)
        if tok.token_type == TokenType.NULL:
            self._advance()
            return None

        raise FizzSQLSyntaxError(
            self._query,
            tok.position,
            f"Expected value, got '{tok.value}'"
        )

    def _parse_identifier_list(self) -> list[str]:
        """Parse a comma-separated list of identifiers."""
        ids: list[str] = []
        tok = self._expect(TokenType.IDENTIFIER, "Expected column name")
        ids.append(tok.value)

        while self._check(TokenType.COMMA):
            self._advance()
            tok = self._expect(TokenType.IDENTIFIER, "Expected column name")
            ids.append(tok.value)

        return ids

    def _parse_order_list(self) -> list[OrderByClause]:
        """Parse ORDER BY column list."""
        items: list[OrderByClause] = []

        tok = self._expect(TokenType.IDENTIFIER, "Expected column name in ORDER BY")
        direction = "ASC"
        if self._check(TokenType.ASC):
            self._advance()
        elif self._check(TokenType.DESC):
            direction = "DESC"
            self._advance()
        items.append(OrderByClause(column=tok.value, direction=direction))

        while self._check(TokenType.COMMA):
            self._advance()
            tok = self._expect(TokenType.IDENTIFIER, "Expected column name")
            direction = "ASC"
            if self._check(TokenType.ASC):
                self._advance()
            elif self._check(TokenType.DESC):
                direction = "DESC"
                self._advance()
            items.append(OrderByClause(column=tok.value, direction=direction))

        return items

    # ---- Token stream helpers ----

    def _current(self) -> Token:
        """Return the current token."""
        if self._pos >= len(self._tokens):
            return Token(TokenType.EOF, "", len(self._query))
        return self._tokens[self._pos]

    def _check(self, token_type: TokenType) -> bool:
        """Check if the current token matches a type without consuming."""
        return self._current().token_type == token_type

    def _advance(self) -> Token:
        """Consume and return the current token."""
        tok = self._current()
        self._pos += 1
        return tok

    def _expect(self, token_type: TokenType, message: str) -> Token:
        """Consume and return the current token, or raise on mismatch."""
        tok = self._current()
        if tok.token_type != token_type:
            raise FizzSQLSyntaxError(
                self._query,
                tok.position,
                f"{message}, got '{tok.value}' ({tok.token_type.name})"
            )
        self._pos += 1
        return tok


# ============================================================
# Platform State & Virtual Tables
# ============================================================

# Type alias for a row: dict mapping column name to value
Row = dict[str, Any]


@dataclass
class TableSchema:
    """Schema definition for a FizzSQL virtual table.

    Each virtual table has a name, a list of column names, their
    types (for display and validation), and a populate function
    that materializes rows from the live platform state. The
    populate function is called at query time — no caching, no
    materialized views, just raw in-memory data every time.
    Maximum freshness. Zero efficiency.
    """

    name: str
    columns: list[str]
    column_types: dict[str, str]  # column -> type hint string
    description: str
    populate: Callable[[PlatformState], list[Row]]


@dataclass
class PlatformState:
    """A snapshot of FizzBuzz platform internals.

    Passed to virtual table populate functions to extract rows.
    Any field may be None if the corresponding subsystem is not
    enabled — virtual tables gracefully return empty result sets
    rather than crashing, because NULL is a valid state of being
    (both existentially and relationally).
    """

    evaluations: Optional[list[Any]] = None
    cache_store: Optional[Any] = None
    blockchain: Optional[Any] = None
    sla_monitor: Optional[Any] = None
    event_bus: Optional[Any] = None


def _populate_evaluations(state: PlatformState) -> list[Row]:
    """Populate the evaluations virtual table.

    Maps FizzBuzzResult or EvaluationResult objects into relational
    rows. Each row represents a single FizzBuzz evaluation with its
    number, classification, output, and strategy. This is the crown
    jewel of FizzSQL — the ability to SELECT * FROM evaluations WHERE
    classification = 'FizzBuzz', a query that could have been
    accomplished with a list comprehension in one line.

    Supports two result types:
      - FizzBuzzResult: has .number, .output, .is_fizz/.is_buzz/.is_fizzbuzz
      - EvaluationResult: has .number, .classification (enum), .strategy_name
    """
    if state.evaluations is None:
        return []

    rows: list[Row] = []
    for i, result in enumerate(state.evaluations):
        number = getattr(result, "number", 0)

        # Determine classification from the result object
        if hasattr(result, "classification"):
            # EvaluationResult path — has a classification enum
            cls_val = result.classification
            classification = cls_val.name if hasattr(cls_val, "name") else str(cls_val)
        elif hasattr(result, "is_fizzbuzz"):
            # FizzBuzzResult path — derive classification from properties
            if result.is_fizzbuzz:
                classification = "FizzBuzz"
            elif result.is_fizz:
                classification = "Fizz"
            elif result.is_buzz:
                classification = "Buzz"
            else:
                classification = "Plain"
        else:
            classification = "Unknown"

        # Get the output string
        output = getattr(result, "output", str(number))

        # Get strategy
        if hasattr(result, "strategy_name"):
            strategy = result.strategy_name
        elif hasattr(result, "metadata") and isinstance(result.metadata, dict):
            strategy = result.metadata.get("strategy", "standard")
        else:
            strategy = "standard"

        rows.append({
            "id": i + 1,
            "number": number,
            "classification": classification,
            "output": output,
            "strategy": strategy,
        })

    return rows


def _populate_cache_entries(state: PlatformState) -> list[Row]:
    """Populate the cache_entries virtual table."""
    if state.cache_store is None:
        return []

    rows: list[Row] = []
    cache = state.cache_store

    entries: dict[Any, Any] = {}
    if hasattr(cache, "_store"):
        entries = cache._store
    elif hasattr(cache, "store"):
        entries = cache.store

    for i, (key, entry) in enumerate(entries.items()):
        state_name = "UNKNOWN"
        value = ""
        if hasattr(entry, "state"):
            state_name = entry.state.name if hasattr(entry.state, "name") else str(entry.state)
        if hasattr(entry, "value"):
            value = str(entry.value)

        rows.append({
            "id": i + 1,
            "cache_key": str(key),
            "value": value,
            "state": state_name,
        })

    return rows


def _populate_blockchain_blocks(state: PlatformState) -> list[Row]:
    """Populate the blockchain_blocks virtual table."""
    if state.blockchain is None:
        return []

    rows: list[Row] = []
    chain: list[Any] = []
    if hasattr(state.blockchain, "chain"):
        chain = state.blockchain.chain
    elif hasattr(state.blockchain, "_chain"):
        chain = state.blockchain._chain

    for block in chain:
        block_hash = ""
        prev_hash = ""
        timestamp_str = ""
        nonce = 0
        data_str = ""

        if hasattr(block, "hash"):
            block_hash = str(block.hash)[:16]
        if hasattr(block, "previous_hash"):
            prev_hash = str(block.previous_hash)[:16]
        if hasattr(block, "timestamp"):
            timestamp_str = str(block.timestamp)
        if hasattr(block, "nonce"):
            nonce = block.nonce
        if hasattr(block, "data"):
            data_str = str(block.data)[:64]

        rows.append({
            "block_index": block.index if hasattr(block, "index") else 0,
            "hash": block_hash,
            "previous_hash": prev_hash,
            "timestamp": timestamp_str,
            "nonce": nonce,
            "data": data_str,
        })

    return rows


def _populate_sla_metrics(state: PlatformState) -> list[Row]:
    """Populate the sla_metrics virtual table."""
    if state.sla_monitor is None:
        return []

    rows: list[Row] = []
    monitor = state.sla_monitor

    # Extract SLO metrics
    slos: list[Any] = []
    if hasattr(monitor, "_slos"):
        slos = monitor._slos
    elif hasattr(monitor, "slos"):
        slos = monitor.slos if isinstance(monitor.slos, list) else list(monitor.slos.values())

    for i, slo in enumerate(slos):
        slo_name = ""
        target = 0.0
        current = 0.0
        slo_type = "unknown"

        if hasattr(slo, "name"):
            slo_name = slo.name
        if hasattr(slo, "target"):
            target = slo.target
        if hasattr(slo, "slo_type"):
            slo_type = slo.slo_type.name if hasattr(slo.slo_type, "name") else str(slo.slo_type)

        # Try to get current value from monitor
        if hasattr(monitor, "get_current_value"):
            try:
                current = monitor.get_current_value(slo_name)
            except Exception:
                current = 0.0
        elif hasattr(monitor, "_current_values"):
            current = monitor._current_values.get(slo_name, 0.0)

        met = "YES" if current >= target else "NO"

        rows.append({
            "id": i + 1,
            "slo_name": slo_name,
            "slo_type": slo_type,
            "target": target,
            "current": current,
            "met": met,
        })

    return rows


def _populate_events(state: PlatformState) -> list[Row]:
    """Populate the events virtual table."""
    if state.event_bus is None:
        return []

    rows: list[Row] = []
    bus = state.event_bus

    # Try to access event history
    history: list[Any] = []
    if hasattr(bus, "_history"):
        history = list(bus._history)
    elif hasattr(bus, "history"):
        history = list(bus.history)
    elif hasattr(bus, "_event_log"):
        history = list(bus._event_log)

    for i, event in enumerate(history):
        event_type = "UNKNOWN"
        source = ""
        timestamp_str = ""

        if hasattr(event, "event_type"):
            event_type = event.event_type.name if hasattr(event.event_type, "name") else str(event.event_type)
        if hasattr(event, "source"):
            source = str(event.source)
        if hasattr(event, "timestamp"):
            timestamp_str = str(event.timestamp)

        payload_str = ""
        if hasattr(event, "payload") and event.payload:
            payload_str = str(event.payload)[:64]

        rows.append({
            "id": i + 1,
            "event_type": event_type,
            "source": source,
            "timestamp": timestamp_str,
            "payload": payload_str,
        })

    return rows


# Virtual table registry — the information_schema of FizzSQL
VIRTUAL_TABLES: dict[str, TableSchema] = {
    "evaluations": TableSchema(
        name="evaluations",
        columns=["id", "number", "classification", "output", "strategy"],
        column_types={
            "id": "INTEGER", "number": "INTEGER",
            "classification": "VARCHAR(10)", "output": "VARCHAR(20)",
            "strategy": "VARCHAR(30)",
        },
        description="FizzBuzz evaluation results — the raison d'etre of this entire platform",
        populate=_populate_evaluations,
    ),
    "cache_entries": TableSchema(
        name="cache_entries",
        columns=["id", "cache_key", "value", "state"],
        column_types={
            "id": "INTEGER", "cache_key": "VARCHAR(50)",
            "value": "VARCHAR(50)", "state": "VARCHAR(20)",
        },
        description="MESI cache coherence entries — cached modulo arithmetic results",
        populate=_populate_cache_entries,
    ),
    "blockchain_blocks": TableSchema(
        name="blockchain_blocks",
        columns=["block_index", "hash", "previous_hash", "timestamp", "nonce", "data"],
        column_types={
            "block_index": "INTEGER", "hash": "VARCHAR(16)",
            "previous_hash": "VARCHAR(16)", "timestamp": "VARCHAR(30)",
            "nonce": "INTEGER", "data": "VARCHAR(64)",
        },
        description="FizzBuzz blockchain audit ledger — immutable proof of modulo operations",
        populate=_populate_blockchain_blocks,
    ),
    "sla_metrics": TableSchema(
        name="sla_metrics",
        columns=["id", "slo_name", "slo_type", "target", "current", "met"],
        column_types={
            "id": "INTEGER", "slo_name": "VARCHAR(30)",
            "slo_type": "VARCHAR(20)", "target": "FLOAT",
            "current": "FLOAT", "met": "VARCHAR(3)",
        },
        description="SLA/SLO compliance metrics — service level agreements for modulo arithmetic",
        populate=_populate_sla_metrics,
    ),
    "events": TableSchema(
        name="events",
        columns=["id", "event_type", "source", "timestamp", "payload"],
        column_types={
            "id": "INTEGER", "event_type": "VARCHAR(30)",
            "source": "VARCHAR(30)", "timestamp": "VARCHAR(30)",
            "payload": "VARCHAR(64)",
        },
        description="Event bus history — a chronicle of every FizzBuzz life event",
        populate=_populate_events,
    ),
}


# ============================================================
# Logical Plan Nodes
# ============================================================


class LogicalNode:
    """Base class for logical plan nodes.

    Each logical node represents a relational algebra operator:
    Scan, Filter, Project, Sort, Limit, or Aggregate. The logical
    plan is strategy-agnostic — it describes WHAT to compute, not
    HOW. That distinction belongs to the physical planner, which
    is responsible for the "how" and is equally over-engineered.
    """

    def __init__(self) -> None:
        self.children: list[LogicalNode] = []
        self.estimated_rows: int = 0
        self.estimated_cost: float = 0.0


class ScanNode(LogicalNode):
    """Full table scan — the only access path we have."""

    def __init__(self, table: str) -> None:
        super().__init__()
        self.table = table


class FilterNode(LogicalNode):
    """Predicate filter (WHERE clause)."""

    def __init__(self, predicate: ComparisonExpr | BooleanExpr) -> None:
        super().__init__()
        self.predicate = predicate


class ProjectNode(LogicalNode):
    """Column projection (SELECT list)."""

    def __init__(self, columns: list[ColumnRef | AggregateExpr], is_star: bool = False) -> None:
        super().__init__()
        self.columns = columns
        self.is_star = is_star


class SortNode(LogicalNode):
    """Sort operator (ORDER BY)."""

    def __init__(self, order_by: list[OrderByClause]) -> None:
        super().__init__()
        self.order_by = order_by


class LimitNode(LogicalNode):
    """Limit/Offset operator."""

    def __init__(self, limit: Optional[int], offset: Optional[int] = None) -> None:
        super().__init__()
        self.limit = limit
        self.offset = offset


class AggregateNode(LogicalNode):
    """Aggregate operator (GROUP BY + aggregate functions)."""

    def __init__(
        self,
        group_by: list[str],
        aggregates: list[AggregateExpr],
        having: Optional[ComparisonExpr | BooleanExpr] = None,
    ) -> None:
        super().__init__()
        self.group_by = group_by
        self.aggregates = aggregates
        self.having = having


# ============================================================
# Logical Planner
# ============================================================


class LogicalPlanner:
    """Builds a logical plan tree from a SelectStatement AST.

    The logical planner translates the declarative SQL AST into
    a tree of relational algebra operators. The tree is built
    bottom-up: Scan at the root (leaf?), then Filter, then
    Aggregate (if GROUP BY), then Sort, then Limit, then Project.

    The order matters. Getting it wrong produces incorrect results.
    This is why database engineers are paid well. We are not
    database engineers. We wrote this for FizzBuzz.
    """

    def build(self, stmt: SelectStatement) -> LogicalNode:
        """Build a logical plan from a parsed SELECT statement."""
        # Start with a table scan
        plan: LogicalNode = ScanNode(stmt.table)

        # Filter (WHERE)
        if stmt.where is not None:
            filter_node = FilterNode(stmt.where)
            filter_node.children = [plan]
            plan = filter_node

        # Check for aggregates
        has_aggregates = any(
            isinstance(c, AggregateExpr) for c in stmt.columns
        )

        # Aggregate (GROUP BY and/or aggregate functions)
        if has_aggregates or stmt.group_by:
            aggregates = [c for c in stmt.columns if isinstance(c, AggregateExpr)]
            agg_node = AggregateNode(
                group_by=stmt.group_by,
                aggregates=aggregates,
                having=stmt.having,
            )
            agg_node.children = [plan]
            plan = agg_node

        # Sort (ORDER BY)
        if stmt.order_by:
            sort_node = SortNode(stmt.order_by)
            sort_node.children = [plan]
            plan = sort_node

        # Limit/Offset
        if stmt.limit is not None or stmt.offset is not None:
            limit_node = LimitNode(stmt.limit, stmt.offset)
            limit_node.children = [plan]
            plan = limit_node

        # Project (SELECT columns)
        project_node = ProjectNode(stmt.columns, is_star=stmt.is_star)
        project_node.children = [plan]
        plan = project_node

        return plan


# ============================================================
# Physical Operators (Volcano Model)
# ============================================================


class PhysicalOperator:
    """Base class for Volcano-model physical operators.

    Every physical operator implements the open()/next()/close()
    iterator protocol. open() initializes state, next() returns
    the next row (or None when exhausted), and close() releases
    resources. This is the Volcano execution model, invented by
    Goetz Graefe, who certainly never imagined it would be used
    to query FizzBuzz evaluation results.

    Each operator pulls from its child operator(s) one row at a
    time — the classic "pull-based" iterator model that powers
    every serious RDBMS. And now, FizzBuzz.
    """

    def __init__(self) -> None:
        self.rows_produced: int = 0

    def open(self) -> None:
        """Initialize the operator."""
        pass

    def next(self) -> Optional[Row]:
        """Return the next row, or None if exhausted."""
        return None

    def close(self) -> None:
        """Release resources."""
        pass

    def explain_name(self) -> str:
        """Return the operator name for EXPLAIN output."""
        return self.__class__.__name__


class SeqScanOperator(PhysicalOperator):
    """Sequential scan — reads all rows from a virtual table.

    The only access path available in FizzSQL, because building
    a B-tree index over an in-memory list of modulo arithmetic
    results would be... actually, that's a great idea for the
    next feature. But for now: sequential scan. O(n). Deal with it.
    """

    def __init__(self, table_schema: TableSchema, state: PlatformState) -> None:
        super().__init__()
        self._schema = table_schema
        self._state = state
        self._rows: list[Row] = []
        self._index: int = 0

    def open(self) -> None:
        self._rows = self._schema.populate(self._state)
        self._index = 0

    def next(self) -> Optional[Row]:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        self.rows_produced += 1
        return row

    def close(self) -> None:
        self._rows = []
        self._index = 0

    def explain_name(self) -> str:
        return f"SeqScan on {self._schema.name}"


class FilterOperator(PhysicalOperator):
    """Filter operator — evaluates predicates and discards non-matching rows.

    Pulls rows from its child and applies the WHERE predicate.
    Rows that don't match the predicate are silently discarded,
    like interns who fail the FizzBuzz interview.
    """

    def __init__(
        self,
        child: PhysicalOperator,
        predicate: ComparisonExpr | BooleanExpr,
    ) -> None:
        super().__init__()
        self._child = child
        self._predicate = predicate

    def open(self) -> None:
        self._child.open()

    def next(self) -> Optional[Row]:
        while True:
            row = self._child.next()
            if row is None:
                return None
            if _evaluate_predicate(self._predicate, row):
                self.rows_produced += 1
                return row

    def close(self) -> None:
        self._child.close()

    def explain_name(self) -> str:
        return f"Filter ({_predicate_to_string(self._predicate)})"


class ProjectOperator(PhysicalOperator):
    """Projection operator — selects specific columns from rows.

    Strips away columns you didn't ask for, because returning
    all columns when you only need two is a waste of precious
    in-memory dictionary space.
    """

    def __init__(
        self,
        child: PhysicalOperator,
        columns: list[ColumnRef | AggregateExpr],
        is_star: bool = False,
    ) -> None:
        super().__init__()
        self._child = child
        self._columns = columns
        self._is_star = is_star

    def open(self) -> None:
        self._child.open()

    def next(self) -> Optional[Row]:
        row = self._child.next()
        if row is None:
            return None

        if self._is_star:
            self.rows_produced += 1
            return row

        projected: Row = {}
        for col in self._columns:
            if isinstance(col, ColumnRef):
                key = col.alias or col.name
                projected[key] = row.get(col.name, None)
            elif isinstance(col, AggregateExpr):
                # Aggregates are already computed by the aggregate operator
                key = col.alias or f"{col.function}({col.column})"
                projected[key] = row.get(key, row.get(col.column, None))

        self.rows_produced += 1
        return projected

    def close(self) -> None:
        self._child.close()

    def explain_name(self) -> str:
        if self._is_star:
            return "Project (*)"
        col_names = []
        for c in self._columns:
            if isinstance(c, ColumnRef):
                col_names.append(c.alias or c.name)
            elif isinstance(c, AggregateExpr):
                col_names.append(c.alias or f"{c.function}({c.column})")
        return f"Project ({', '.join(col_names)})"


class SortOperator(PhysicalOperator):
    """Sort operator — materializes all input rows and sorts them.

    This is a blocking operator: it must consume all input before
    producing any output. In a real database this would spill to
    disk for large sorts. Here, everything fits in memory because
    we're sorting FizzBuzz results. The largest sort in FizzSQL
    history is 100 rows. We'll survive.
    """

    def __init__(
        self,
        child: PhysicalOperator,
        order_by: list[OrderByClause],
    ) -> None:
        super().__init__()
        self._child = child
        self._order_by = order_by
        self._sorted: list[Row] = []
        self._index: int = 0

    def open(self) -> None:
        self._child.open()

        # Materialize all input rows
        rows: list[Row] = []
        while True:
            row = self._child.next()
            if row is None:
                break
            rows.append(row)

        # Sort by each ORDER BY column
        def sort_key(row: Row) -> tuple[Any, ...]:
            key_parts: list[Any] = []
            for ob in self._order_by:
                val = row.get(ob.column, "")
                if val is None:
                    val = ""
                # Normalize for comparison
                if isinstance(val, str):
                    sort_val: Any = val.lower()
                else:
                    sort_val = val

                if ob.direction == "DESC":
                    # For descending, negate numbers; reverse strings
                    if isinstance(sort_val, (int, float)):
                        sort_val = -sort_val
                    else:
                        # Use a wrapper for reverse string sort
                        sort_val = _ReverseStr(str(sort_val))
                key_parts.append(sort_val)
            return tuple(key_parts)

        self._sorted = sorted(rows, key=sort_key)
        self._index = 0

    def next(self) -> Optional[Row]:
        if self._index >= len(self._sorted):
            return None
        row = self._sorted[self._index]
        self._index += 1
        self.rows_produced += 1
        return row

    def close(self) -> None:
        self._child.close()
        self._sorted = []
        self._index = 0

    def explain_name(self) -> str:
        cols = ", ".join(
            f"{ob.column} {ob.direction}" for ob in self._order_by
        )
        return f"Sort ({cols})"


class _ReverseStr:
    """Helper for descending string sort."""

    def __init__(self, s: str) -> None:
        self.s = s

    def __lt__(self, other: _ReverseStr) -> bool:
        return self.s > other.s

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _ReverseStr):
            return NotImplemented
        return self.s == other.s

    def __le__(self, other: _ReverseStr) -> bool:
        return self.s >= other.s

    def __gt__(self, other: _ReverseStr) -> bool:
        return self.s < other.s

    def __ge__(self, other: _ReverseStr) -> bool:
        return self.s <= other.s


class LimitOperator(PhysicalOperator):
    """Limit/Offset operator — restricts output row count.

    Implements SQL LIMIT and OFFSET by counting rows from
    the child operator. The first `offset` rows are skipped,
    and at most `limit` rows are returned. Simple in theory,
    but somehow Oracle didn't have native LIMIT until 12c.
    We got it right on the first try. Take that, Larry.
    """

    def __init__(
        self,
        child: PhysicalOperator,
        limit: Optional[int],
        offset: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._child = child
        self._limit = limit
        self._offset = offset or 0
        self._skipped: int = 0
        self._returned: int = 0

    def open(self) -> None:
        self._child.open()
        self._skipped = 0
        self._returned = 0

    def next(self) -> Optional[Row]:
        # Skip offset rows
        while self._skipped < self._offset:
            row = self._child.next()
            if row is None:
                return None
            self._skipped += 1

        # Check limit
        if self._limit is not None and self._returned >= self._limit:
            return None

        row = self._child.next()
        if row is None:
            return None

        self._returned += 1
        self.rows_produced += 1
        return row

    def close(self) -> None:
        self._child.close()

    def explain_name(self) -> str:
        parts = []
        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")
        if self._offset:
            parts.append(f"OFFSET {self._offset}")
        return f"Limit ({', '.join(parts)})"


class AggregateOperator(PhysicalOperator):
    """Aggregate operator — GROUP BY with aggregate functions.

    Materializes all input, groups by the specified columns, and
    computes aggregate values (COUNT, SUM, AVG, MIN, MAX) for
    each group. The HAVING clause is applied post-aggregation.

    This is a blocking operator for the same reasons as Sort:
    you can't compute COUNT(*) without reading all the rows.
    """

    def __init__(
        self,
        child: PhysicalOperator,
        group_by: list[str],
        aggregates: list[AggregateExpr],
        having: Optional[ComparisonExpr | BooleanExpr] = None,
    ) -> None:
        super().__init__()
        self._child = child
        self._group_by = group_by
        self._aggregates = aggregates
        self._having = having
        self._result_rows: list[Row] = []
        self._index: int = 0

    def open(self) -> None:
        self._child.open()

        # Materialize all input rows
        all_rows: list[Row] = []
        while True:
            row = self._child.next()
            if row is None:
                break
            all_rows.append(row)

        # Group rows
        groups: dict[tuple[Any, ...], list[Row]] = {}
        for row in all_rows:
            key = tuple(row.get(col, None) for col in self._group_by)
            groups.setdefault(key, []).append(row)

        # If no GROUP BY and no rows, we still produce one row for aggregates
        if not self._group_by and not groups:
            groups[()]  = []

        # Compute aggregates for each group
        self._result_rows = []
        for key, group_rows in groups.items():
            result_row: Row = {}

            # Add group-by columns
            for i, col in enumerate(self._group_by):
                result_row[col] = key[i]

            # Compute each aggregate
            for agg in self._aggregates:
                agg_key = agg.alias or f"{agg.function}({agg.column})"
                result_row[agg_key] = _compute_aggregate(
                    agg.function, agg.column, group_rows, agg.distinct
                )

            self._result_rows.append(result_row)

        # Apply HAVING filter
        if self._having is not None:
            self._result_rows = [
                row for row in self._result_rows
                if _evaluate_predicate(self._having, row)
            ]

        self._index = 0

    def next(self) -> Optional[Row]:
        if self._index >= len(self._result_rows):
            return None
        row = self._result_rows[self._index]
        self._index += 1
        self.rows_produced += 1
        return row

    def close(self) -> None:
        self._child.close()
        self._result_rows = []
        self._index = 0

    def explain_name(self) -> str:
        parts = []
        if self._group_by:
            parts.append(f"GROUP BY {', '.join(self._group_by)}")
        agg_names = [f"{a.function}({a.column})" for a in self._aggregates]
        if agg_names:
            parts.append(f"aggregates: {', '.join(agg_names)}")
        return f"Aggregate ({'; '.join(parts)})"


# ============================================================
# Predicate Evaluation Helpers
# ============================================================


def _evaluate_predicate(pred: ComparisonExpr | BooleanExpr, row: Row) -> bool:
    """Evaluate a predicate against a single row."""
    if isinstance(pred, BooleanExpr):
        if pred.operator == "AND":
            return (
                _evaluate_predicate(pred.left, row)
                and _evaluate_predicate(pred.right, row)
            )
        if pred.operator == "OR":
            return (
                _evaluate_predicate(pred.left, row)
                or _evaluate_predicate(pred.right, row)
            )
        if pred.operator == "NOT":
            return not _evaluate_predicate(pred.left, row)
        return False

    if isinstance(pred, ComparisonExpr):
        left_val = row.get(pred.left, None)
        right_val = pred.right

        if pred.operator == "IS":
            return left_val is None
        if pred.operator == "IS NOT":
            return left_val is not None

        if pred.operator == "IN":
            if isinstance(right_val, list):
                return _coerce_compare(left_val) in [_coerce_compare(v) for v in right_val]
            return False

        if pred.operator == "BETWEEN":
            if isinstance(right_val, tuple) and len(right_val) == 2:
                low, high = right_val
                cv = _coerce_compare(left_val)
                return _coerce_compare(low) <= cv <= _coerce_compare(high)
            return False

        if pred.operator == "LIKE":
            return _like_match(str(left_val) if left_val is not None else "", str(right_val))

        # Standard comparison
        left_c = _coerce_compare(left_val)
        right_c = _coerce_compare(right_val)

        if pred.operator == "=":
            return left_c == right_c
        if pred.operator == "!=":
            return left_c != right_c
        if pred.operator == "<":
            return left_c < right_c
        if pred.operator == ">":
            return left_c > right_c
        if pred.operator == "<=":
            return left_c <= right_c
        if pred.operator == ">=":
            return left_c >= right_c

    return False


def _coerce_compare(val: Any) -> Any:
    """Coerce a value for comparison — strings are case-insensitive."""
    if val is None:
        return ""
    if isinstance(val, str):
        # Try to convert string to number for numeric comparisons
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
        return val.upper()
    return val


def _like_match(value: str, pattern: str) -> bool:
    """Simple SQL LIKE pattern matching (% and _ wildcards)."""
    # Convert SQL LIKE pattern to a simple matcher
    import re as _re
    regex_pattern = "^"
    for ch in pattern:
        if ch == "%":
            regex_pattern += ".*"
        elif ch == "_":
            regex_pattern += "."
        else:
            regex_pattern += _re.escape(ch)
    regex_pattern += "$"
    return bool(_re.match(regex_pattern, value, _re.IGNORECASE))


def _compute_aggregate(
    func: str,
    column: str,
    rows: list[Row],
    distinct: bool = False,
) -> Any:
    """Compute an aggregate function over a group of rows."""
    if func == "COUNT":
        if column == "*":
            return len(rows)
        values = [row.get(column) for row in rows if row.get(column) is not None]
        if distinct:
            values = list(set(values))
        return len(values)

    # Extract numeric values
    values: list[Any] = []
    for row in rows:
        val = row.get(column)
        if val is not None:
            if isinstance(val, (int, float)):
                values.append(val)
            else:
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    pass

    if distinct:
        values = list(set(values))

    if not values:
        return None

    if func == "SUM":
        return sum(values)
    if func == "AVG":
        return sum(values) / len(values) if values else None
    if func == "MIN":
        return min(values)
    if func == "MAX":
        return max(values)

    return None


def _predicate_to_string(pred: ComparisonExpr | BooleanExpr) -> str:
    """Convert a predicate to a human-readable string."""
    if isinstance(pred, BooleanExpr):
        if pred.operator == "NOT":
            return f"NOT ({_predicate_to_string(pred.left)})"
        left_str = _predicate_to_string(pred.left)
        right_str = _predicate_to_string(pred.right)
        return f"{left_str} {pred.operator} {right_str}"

    if isinstance(pred, ComparisonExpr):
        right_repr = repr(pred.right) if isinstance(pred.right, str) else str(pred.right)
        return f"{pred.left} {pred.operator} {right_repr}"

    return "???"


# ============================================================
# Physical Planner
# ============================================================


class PhysicalPlanner:
    """Maps a logical plan tree to physical operators.

    This is where the logical algebra meets physical reality.
    ScanNode becomes SeqScanOperator, FilterNode becomes
    FilterOperator, and so on. In a real database, this is
    where you'd choose between nested-loop joins, hash joins,
    merge joins, index scans, and bitmap heap scans. We have
    exactly one choice per operator. The optimizer is trivial.
    The cost model is a work of fiction. Enjoy.
    """

    def __init__(self, state: PlatformState) -> None:
        self._state = state

    def plan(self, logical: LogicalNode) -> PhysicalOperator:
        """Convert a logical plan tree to a physical operator tree."""
        return self._build(logical)

    def _build(self, node: LogicalNode) -> PhysicalOperator:
        """Recursively build physical operators."""
        if isinstance(node, ScanNode):
            if node.table not in VIRTUAL_TABLES:
                raise FizzSQLTableNotFoundError(
                    node.table, list(VIRTUAL_TABLES.keys())
                )
            return SeqScanOperator(VIRTUAL_TABLES[node.table], self._state)

        # Build child operator first
        child_op: Optional[PhysicalOperator] = None
        if node.children:
            child_op = self._build(node.children[0])

        if isinstance(node, FilterNode):
            assert child_op is not None
            return FilterOperator(child_op, node.predicate)

        if isinstance(node, ProjectNode):
            assert child_op is not None
            return ProjectOperator(child_op, node.columns, node.is_star)

        if isinstance(node, SortNode):
            assert child_op is not None
            return SortOperator(child_op, node.order_by)

        if isinstance(node, LimitNode):
            assert child_op is not None
            return LimitOperator(child_op, node.limit, node.offset)

        if isinstance(node, AggregateNode):
            assert child_op is not None
            return AggregateOperator(
                child_op, node.group_by, node.aggregates, node.having
            )

        raise FizzSQLExecutionError(
            "(internal)", f"Unknown logical node type: {type(node).__name__}"
        )


# ============================================================
# Cost Estimator
# ============================================================


class CostEstimator:
    """Estimates query execution costs.

    The cost model is inspired by PostgreSQL's cost model and is
    equally as opaque, but with the added benefit of being entirely
    made up. Costs are expressed in "Fizz Cost Units" (FCU), a
    currency that has no exchange rate with any real-world metric.
    The startup cost represents the time to begin producing rows.
    The total cost represents... vibes.
    """

    # Cost constants — these are completely fictional
    SEQ_SCAN_COST_PER_ROW = 1.0
    FILTER_COST_PER_ROW = 0.5
    SORT_COST_FACTOR = 2.0  # n * log(n) approximated as 2n
    AGGREGATE_COST_PER_ROW = 1.5
    PROJECT_COST_PER_ROW = 0.1
    LIMIT_COST = 0.01

    @staticmethod
    def estimate(logical: LogicalNode, table_row_count: int) -> tuple[float, float]:
        """Estimate (startup_cost, total_cost) for a logical plan.

        Returns a tuple of (startup_cost, total_cost) in Fizz Cost
        Units (FCU). The startup cost is the cost before the first
        row can be returned. The total cost is the cost to process
        all rows. Both numbers are fictional.
        """
        rows = table_row_count
        startup = 0.0
        total = 0.0

        if isinstance(logical, ScanNode):
            total = rows * CostEstimator.SEQ_SCAN_COST_PER_ROW
            return (0.0, total)

        if isinstance(logical, FilterNode):
            child_startup, child_total = CostEstimator.estimate(
                logical.children[0], rows
            )
            filter_cost = rows * CostEstimator.FILTER_COST_PER_ROW
            # Assume 33% selectivity (because we have no statistics)
            estimated_output = max(1, rows // 3)
            logical.estimated_rows = estimated_output
            return (child_startup, child_total + filter_cost)

        if isinstance(logical, SortNode):
            child_startup, child_total = CostEstimator.estimate(
                logical.children[0], rows
            )
            import math
            sort_cost = rows * math.log2(max(rows, 2)) * CostEstimator.SORT_COST_FACTOR
            # Sort is blocking: startup includes materializing all input
            return (child_total + sort_cost, child_total + sort_cost)

        if isinstance(logical, AggregateNode):
            child_startup, child_total = CostEstimator.estimate(
                logical.children[0], rows
            )
            agg_cost = rows * CostEstimator.AGGREGATE_COST_PER_ROW
            return (child_total + agg_cost, child_total + agg_cost)

        if isinstance(logical, LimitNode):
            child_startup, child_total = CostEstimator.estimate(
                logical.children[0], rows
            )
            return (child_startup, child_startup + CostEstimator.LIMIT_COST)

        if isinstance(logical, ProjectNode):
            child_startup, child_total = CostEstimator.estimate(
                logical.children[0], rows
            )
            proj_cost = rows * CostEstimator.PROJECT_COST_PER_ROW
            return (child_startup, child_total + proj_cost)

        return (0.0, 0.0)


# ============================================================
# EXPLAIN ANALYZE
# ============================================================


class ExplainAnalyze:
    """Produces EXPLAIN ANALYZE output with an ASCII plan tree.

    Like PostgreSQL's EXPLAIN ANALYZE, but for queries over
    FizzBuzz evaluation results. Displays the physical operator
    tree with estimated and actual row counts, startup and total
    costs, and execution time. The output format is designed to
    look impressive in terminal screenshots on social media.
    """

    @staticmethod
    def render(
        root: PhysicalOperator,
        execution_time_ms: float,
        table_row_count: int,
        logical_root: LogicalNode,
    ) -> str:
        """Render an EXPLAIN ANALYZE plan tree."""
        startup_cost, total_cost = CostEstimator.estimate(
            logical_root, table_row_count
        )

        lines: list[str] = []
        lines.append("  QUERY PLAN")
        lines.append("  " + "-" * 60)
        ExplainAnalyze._render_operator(root, lines, indent=0)
        lines.append("  " + "-" * 60)
        lines.append(
            f"  Planning time: 0.001 ms (it's a Python dict, not Oracle)"
        )
        lines.append(f"  Execution time: {execution_time_ms:.3f} ms")
        lines.append(
            f"  Total cost: {total_cost:.2f} FCU (Fizz Cost Units)"
        )
        lines.append(f"  Startup cost: {startup_cost:.2f} FCU")
        lines.append(
            f"  Rows: {root.rows_produced} actual"
        )

        return "\n".join(lines)

    @staticmethod
    def _render_operator(
        op: PhysicalOperator,
        lines: list[str],
        indent: int,
    ) -> None:
        """Recursively render operators in the plan tree."""
        prefix = "  " + "  " * indent + ("-> " if indent > 0 else "")
        lines.append(
            f"{prefix}{op.explain_name()} "
            f"(rows={op.rows_produced})"
        )

        # Render children
        child_ops: list[PhysicalOperator] = []
        if isinstance(op, FilterOperator):
            child_ops = [op._child]
        elif isinstance(op, ProjectOperator):
            child_ops = [op._child]
        elif isinstance(op, SortOperator):
            child_ops = [op._child]
        elif isinstance(op, LimitOperator):
            child_ops = [op._child]
        elif isinstance(op, AggregateOperator):
            child_ops = [op._child]

        for child in child_ops:
            ExplainAnalyze._render_operator(child, lines, indent + 1)


# ============================================================
# Result Formatter
# ============================================================


class ResultFormatter:
    """Formats query results as ASCII tables with auto-width columns.

    Produces beautiful(ish) ASCII tables with +---+---+ borders,
    automatically sized columns, and a row count footer. Like
    the mysql command-line client, but for FizzBuzz. The tables
    are guaranteed to look acceptable in a monospace font and
    completely unacceptable in a proportional font.
    """

    @staticmethod
    def format(rows: list[Row], columns: Optional[list[str]] = None) -> str:
        """Format rows as an ASCII table."""
        if not rows:
            return "  (0 rows)\n"

        # Determine columns
        if columns is None:
            columns = list(rows[0].keys())

        # Compute column widths (min width = header length)
        widths: dict[str, int] = {}
        for col in columns:
            widths[col] = len(col)

        for row in rows:
            for col in columns:
                val = str(row.get(col, "NULL"))
                widths[col] = max(widths[col], len(val))

        # Build format string
        def separator() -> str:
            return "  +" + "+".join(
                "-" * (widths[col] + 2) for col in columns
            ) + "+"

        def format_row(values: dict[str, Any]) -> str:
            cells = []
            for col in columns:  # type: ignore[union-attr]
                val = str(values.get(col, "NULL"))
                # Right-align numbers, left-align strings
                raw = values.get(col, None)
                if isinstance(raw, (int, float)):
                    cells.append(f" {val:>{widths[col]}} ")
                else:
                    cells.append(f" {val:<{widths[col]}} ")
            return "  |" + "|".join(cells) + "|"

        lines: list[str] = []
        lines.append(separator())

        # Header
        header_vals = {col: col for col in columns}
        lines.append(format_row(header_vals))
        lines.append(separator())

        # Data rows
        for row in rows:
            lines.append(format_row(row))

        lines.append(separator())
        lines.append(f"  ({len(rows)} row{'s' if len(rows) != 1 else ''})")

        return "\n".join(lines)


# ============================================================
# Query History & Dashboard
# ============================================================


@dataclass
class QueryRecord:
    """A record of a single FizzSQL query execution."""

    query: str
    execution_time_ms: float
    rows_returned: int
    timestamp: float
    success: bool
    error: Optional[str] = None


class FizzSQLDashboard:
    """Renders an ASCII dashboard for the FizzSQL query engine.

    Displays query history, slow query log, table catalog, and
    engine statistics. Because every database needs a monitoring
    dashboard, even one that exists entirely in RAM and queries
    data structures that vanish when the process exits.
    """

    @staticmethod
    def render(
        engine: FizzSQLEngine,
        width: int = 60,
    ) -> str:
        """Render the FizzSQL dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        lines.append("")
        lines.append("  " + border)
        lines.append("  |" + " FIZZSQL RELATIONAL QUERY ENGINE DASHBOARD".ljust(width - 3) + "|")
        lines.append("  |" + ' "SELECT * FROM overkill"'.ljust(width - 3) + "|")
        lines.append("  " + border)

        # Engine Statistics
        lines.append("  |" + " ENGINE STATISTICS".ljust(width - 3) + "|")
        lines.append("  |" + ("-" * (width - 4)).ljust(width - 3) + "|")
        total_queries = len(engine.query_history)
        successful = sum(1 for q in engine.query_history if q.success)
        failed = total_queries - successful

        stats = [
            f"Total queries executed: {total_queries}",
            f"Successful: {successful} | Failed: {failed}",
        ]

        if engine.query_history:
            avg_time = sum(
                q.execution_time_ms for q in engine.query_history
            ) / len(engine.query_history)
            total_rows = sum(
                q.rows_returned for q in engine.query_history
            )
            stats.append(f"Avg execution time: {avg_time:.3f} ms")
            stats.append(f"Total rows returned: {total_rows}")

        for stat in stats:
            lines.append("  |  " + stat.ljust(width - 5) + "|")

        lines.append("  " + border)

        # Table Catalog
        lines.append("  |" + " TABLE CATALOG".ljust(width - 3) + "|")
        lines.append("  |" + ("-" * (width - 4)).ljust(width - 3) + "|")

        for name, schema in VIRTUAL_TABLES.items():
            cols_str = ", ".join(schema.columns)
            table_line = f"{name}: [{cols_str}]"
            # Truncate if needed
            max_len = width - 6
            if len(table_line) > max_len:
                table_line = table_line[: max_len - 3] + "..."
            lines.append("  |  " + table_line.ljust(width - 5) + "|")

        lines.append("  " + border)

        # Recent Queries
        if engine.query_history:
            lines.append("  |" + " RECENT QUERIES".ljust(width - 3) + "|")
            lines.append("  |" + ("-" * (width - 4)).ljust(width - 3) + "|")

            recent = list(engine.query_history)[-5:]
            for qr in recent:
                status = "OK" if qr.success else "ERR"
                q_display = qr.query[:width - 25]
                entry = f"[{status}] {q_display} ({qr.execution_time_ms:.1f}ms)"
                lines.append("  |  " + entry.ljust(width - 5) + "|")

            lines.append("  " + border)

        # Slow Query Log
        slow_queries = [
            q for q in engine.query_history
            if q.execution_time_ms > engine.slow_query_threshold_ms
        ]
        if slow_queries:
            lines.append("  |" + " SLOW QUERY LOG".ljust(width - 3) + "|")
            lines.append("  |" + ("-" * (width - 4)).ljust(width - 3) + "|")

            for sq in slow_queries[-3:]:
                entry = f"{sq.query[:width - 20]} ({sq.execution_time_ms:.1f}ms)"
                lines.append("  |  " + entry.ljust(width - 5) + "|")

            lines.append("  " + border)

        lines.append("")
        return "\n".join(lines)


# ============================================================
# FizzSQL Engine — the orchestrator
# ============================================================


class FizzSQLEngine:
    """The FizzSQL Relational Query Engine orchestrator.

    Wires together the lexer, parser, logical planner, physical
    planner, cost estimator, and Volcano executor into a single
    execute() call that takes a SQL string and returns formatted
    results. This is the entry point for all FizzSQL operations.

    Usage:
        engine = FizzSQLEngine(state=platform_state)
        output = engine.execute("SELECT * FROM evaluations")

    The engine maintains a query history and slow query log,
    because observability into your FizzBuzz query engine is
    non-negotiable at this level of enterprise architecture.
    """

    def __init__(
        self,
        state: Optional[PlatformState] = None,
        max_result_rows: int = 10000,
        enable_history: bool = True,
        history_size: int = 100,
        slow_query_threshold_ms: float = 50.0,
    ) -> None:
        self._state = state or PlatformState()
        self._max_result_rows = max_result_rows
        self._enable_history = enable_history
        self._history_size = history_size
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.query_history: deque[QueryRecord] = deque(maxlen=history_size)

    @property
    def state(self) -> PlatformState:
        """The platform state snapshot."""
        return self._state

    @state.setter
    def state(self, value: PlatformState) -> None:
        """Update the platform state."""
        self._state = value

    def execute(self, query: str) -> str:
        """Execute a FizzSQL query and return formatted output.

        This is the main entry point. It:
        1. Lexes the query into tokens
        2. Parses tokens into an AST
        3. Builds a logical plan
        4. Builds a physical plan
        5. Executes via the Volcano model
        6. Formats results as an ASCII table

        All of this to query a Python list. Enterprise.
        """
        start_time = time.perf_counter()

        try:
            result = self._execute_inner(query)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Count rows (rough heuristic from output)
            row_count = result.count("\n|") - 1  # subtract header
            if row_count < 0:
                row_count = 0

            if self._enable_history:
                self.query_history.append(QueryRecord(
                    query=query.strip(),
                    execution_time_ms=elapsed_ms,
                    rows_returned=row_count,
                    timestamp=time.time(),
                    success=True,
                ))

            if elapsed_ms > self.slow_query_threshold_ms:
                logger.warning(
                    "FizzSQL slow query (%.3f ms): %s",
                    elapsed_ms, query.strip()
                )

            return result

        except (FizzSQLError, FizzSQLSyntaxError, FizzSQLTableNotFoundError,
                FizzSQLExecutionError) as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            if self._enable_history:
                self.query_history.append(QueryRecord(
                    query=query.strip(),
                    execution_time_ms=elapsed_ms,
                    rows_returned=0,
                    timestamp=time.time(),
                    success=False,
                    error=str(e),
                ))
            raise

    def _execute_inner(self, query: str) -> str:
        """Inner execution logic."""
        query = query.strip()
        if not query:
            raise FizzSQLSyntaxError(query, 0, "Empty query")

        # Lex
        lexer = SQLLexer(query)
        tokens = lexer.tokenize()

        # Parse
        parser = SQLParser(tokens, query)
        stmt = parser.parse()

        # SHOW TABLES
        if stmt.is_show_tables:
            return self._show_tables()

        # Build logical plan
        planner = LogicalPlanner()
        logical_root = planner.build(stmt)

        # Build physical plan
        physical_planner = PhysicalPlanner(self._state)
        physical_root = physical_planner.plan(logical_root)

        # Execute
        start_exec = time.perf_counter()
        physical_root.open()

        rows: list[Row] = []
        while True:
            row = physical_root.next()
            if row is None:
                break
            rows.append(row)
            if len(rows) >= self._max_result_rows:
                break

        physical_root.close()
        exec_time_ms = (time.perf_counter() - start_exec) * 1000

        # EXPLAIN ANALYZE
        if stmt.is_explain:
            # Re-estimate table row count
            table_row_count = 0
            if stmt.table in VIRTUAL_TABLES:
                table_row_count = len(
                    VIRTUAL_TABLES[stmt.table].populate(self._state)
                )
            return ExplainAnalyze.render(
                physical_root, exec_time_ms, table_row_count, logical_root
            )

        # Format result
        return ResultFormatter.format(rows)

    def _show_tables(self) -> str:
        """Handle SHOW TABLES query."""
        rows: list[Row] = []
        for name, schema in VIRTUAL_TABLES.items():
            cols_str = ", ".join(schema.columns)
            rows.append({
                "table_name": name,
                "columns": cols_str,
                "description": schema.description[:50],
            })
        return ResultFormatter.format(rows)

    def list_tables(self) -> list[dict[str, str]]:
        """Return a list of available virtual tables and their schemas.

        Useful for CLI --fizzsql-tables output without executing
        a full SQL query. Because sometimes you just want to know
        what tables exist without the overhead of a recursive
        descent parser.
        """
        tables: list[dict[str, str]] = []
        for name, schema in VIRTUAL_TABLES.items():
            cols_str = ", ".join(
                f"{col} {schema.column_types.get(col, 'ANY')}"
                for col in schema.columns
            )
            tables.append({
                "name": name,
                "columns": cols_str,
                "description": schema.description,
            })
        return tables

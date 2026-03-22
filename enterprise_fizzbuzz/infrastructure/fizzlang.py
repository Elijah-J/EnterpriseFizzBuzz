"""
Enterprise FizzBuzz Platform - FizzLang Domain-Specific Language

A complete, purpose-built, Turing-INCOMPLETE programming language for
expressing FizzBuzz rules. Features a hand-written lexer, recursive-descent
parser, AST-based type checker, tree-walking interpreter, a 3-function
standard library, an interactive REPL, and an ASCII dashboard — all to
evaluate ``n % 3``.

FizzLang intentionally lacks loops, recursion, and user-defined functions.
These omissions are not bugs — they are architectural decisions that ensure
FizzLang remains forever incapable of computing anything beyond FizzBuzz.
The Turing-incompleteness is a feature, not a limitation. Any language
that CAN'T solve the halting problem is enterprise-ready by definition.

Syntax overview::

    # Comments start with hash
    let x = 42
    rule fizz when n % 3 == 0 emit "Fizz" priority 1
    rule buzz when n % 5 == 0 emit "Buzz" priority 2
    evaluate 1 to 100

The ``fizzbuzz()`` stdlib function implements FizzBuzz in one line,
creating a recursive irony: a FizzBuzz DSL that contains a built-in
function that does FizzBuzz, used inside a FizzBuzz platform. It's
FizzBuzz all the way down.
"""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional


from enterprise_fizzbuzz.domain.exceptions import (
    FizzLangError,
    FizzLangLexerError,
    FizzLangParseError,
    FizzLangRuntimeError,
    FizzLangTypeError,
)


# ======================================================================
# Token Types
# ======================================================================

class TokenType(Enum):
    """Token types for the FizzLang lexer.

    Every programming language begins with a set of token types.
    FizzLang's vocabulary is intentionally spartan: just enough to
    express divisibility rules and string emissions, not enough to
    compute anything interesting. This is by design.
    """

    # Literals
    INTEGER = auto()
    STRING = auto()
    IDENTIFIER = auto()

    # Keywords (case-insensitive, because shouting is optional)
    RULE = auto()
    WHEN = auto()
    EMIT = auto()
    EVALUATE = auto()
    TO = auto()
    LET = auto()
    PRIORITY = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    TRUE = auto()
    FALSE = auto()

    # Operators
    PLUS = auto()          # +
    MINUS = auto()         # -
    STAR = auto()          # *
    SLASH = auto()         # /
    PERCENT = auto()       # %
    EQUALS = auto()        # ==
    NOT_EQUALS = auto()    # !=
    LESS_THAN = auto()     # <
    GREATER_THAN = auto()  # >
    LESS_EQUAL = auto()    # <=
    GREATER_EQUAL = auto() # >=
    ASSIGN = auto()        # =

    # Delimiters
    LPAREN = auto()        # (
    RPAREN = auto()        # )
    COMMA = auto()         # ,

    # Special
    N_VAR = auto()         # the sacred variable 'n'
    EOF = auto()
    NEWLINE = auto()


@dataclass(frozen=True)
class Token:
    """A single token produced by the FizzLang lexer.

    Each token carries its type, literal value, and source location,
    because even in a language this simple, debugging requires knowing
    where things went wrong.
    """

    type: TokenType
    value: Any
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:{self.col})"


# ======================================================================
# Lexer
# ======================================================================

# Keyword map (case-insensitive)
_KEYWORDS: dict[str, TokenType] = {
    "rule": TokenType.RULE,
    "when": TokenType.WHEN,
    "emit": TokenType.EMIT,
    "evaluate": TokenType.EVALUATE,
    "to": TokenType.TO,
    "let": TokenType.LET,
    "priority": TokenType.PRIORITY,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}


class Lexer:
    """Hand-written character scanner for the FizzLang DSL.

    Transforms raw source text into a stream of tokens, one character
    at a time, like a very slow assembly line for modulo arithmetic
    instructions. Keywords are case-insensitive because the language
    doesn't care about your shift key preferences.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []

    def _peek(self) -> str:
        if self.pos >= len(self.source):
            return "\0"
        return self.source[self.pos]

    def _advance(self) -> str:
        ch = self._peek()
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self.pos < len(self.source) and self.source[self.pos] == expected:
            self._advance()
            return True
        return False

    def _add_token(self, token_type: TokenType, value: Any = None) -> None:
        self.tokens.append(Token(token_type, value, self.line, self.col))

    def tokenize(self) -> list[Token]:
        """Scan the entire source and return a list of tokens."""
        while self.pos < len(self.source):
            ch = self._peek()

            # Skip whitespace (except newlines)
            if ch in (" ", "\t", "\r"):
                self._advance()
                continue

            # Newlines are significant for statement separation
            if ch == "\n":
                start_col = self.col
                self._advance()
                self.tokens.append(Token(TokenType.NEWLINE, "\\n", self.line - 1, start_col))
                continue

            # Comments: skip to end of line
            if ch == "#":
                while self.pos < len(self.source) and self._peek() != "\n":
                    self._advance()
                continue

            # String literals
            if ch == '"':
                self._scan_string()
                continue

            # Numbers
            if ch.isdigit():
                self._scan_number()
                continue

            # Identifiers and keywords
            if ch.isalpha() or ch == "_":
                self._scan_identifier()
                continue

            # Two-character operators
            start_line, start_col = self.line, self.col
            if ch == "=" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "=":
                self._advance()
                self._advance()
                self.tokens.append(Token(TokenType.EQUALS, "==", start_line, start_col))
                continue

            if ch == "!" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "=":
                self._advance()
                self._advance()
                self.tokens.append(Token(TokenType.NOT_EQUALS, "!=", start_line, start_col))
                continue

            if ch == "<" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "=":
                self._advance()
                self._advance()
                self.tokens.append(Token(TokenType.LESS_EQUAL, "<=", start_line, start_col))
                continue

            if ch == ">" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "=":
                self._advance()
                self._advance()
                self.tokens.append(Token(TokenType.GREATER_EQUAL, ">=", start_line, start_col))
                continue

            # Single-character operators and delimiters
            start_line, start_col = self.line, self.col
            self._advance()

            single_char_map: dict[str, TokenType] = {
                "+": TokenType.PLUS,
                "-": TokenType.MINUS,
                "*": TokenType.STAR,
                "/": TokenType.SLASH,
                "%": TokenType.PERCENT,
                "=": TokenType.ASSIGN,
                "<": TokenType.LESS_THAN,
                ">": TokenType.GREATER_THAN,
                "(": TokenType.LPAREN,
                ")": TokenType.RPAREN,
                ",": TokenType.COMMA,
            }

            if ch in single_char_map:
                self.tokens.append(Token(single_char_map[ch], ch, start_line, start_col))
                continue

            raise FizzLangLexerError(ch, start_line, start_col)

        # Sentinel
        self.tokens.append(Token(TokenType.EOF, None, self.line, self.col))
        return self.tokens

    def _scan_string(self) -> None:
        """Scan a double-quoted string literal."""
        start_line, start_col = self.line, self.col
        self._advance()  # consume opening "
        value = []
        while self.pos < len(self.source) and self._peek() != '"':
            ch = self._advance()
            if ch == "\\":
                next_ch = self._advance()
                escape_map = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}
                value.append(escape_map.get(next_ch, next_ch))
            else:
                value.append(ch)
        if self.pos >= len(self.source):
            raise FizzLangLexerError("EOF", start_line, start_col)
        self._advance()  # consume closing "
        self.tokens.append(Token(TokenType.STRING, "".join(value), start_line, start_col))

    def _scan_number(self) -> None:
        """Scan an integer literal."""
        start_line, start_col = self.line, self.col
        digits = []
        while self.pos < len(self.source) and self._peek().isdigit():
            digits.append(self._advance())
        self.tokens.append(Token(TokenType.INTEGER, int("".join(digits)), start_line, start_col))

    def _scan_identifier(self) -> None:
        """Scan an identifier or keyword."""
        start_line, start_col = self.line, self.col
        chars = []
        while self.pos < len(self.source) and (self._peek().isalnum() or self._peek() == "_"):
            chars.append(self._advance())
        word = "".join(chars)
        lower = word.lower()

        # The sacred variable 'n'
        if lower == "n" and len(word) == 1:
            self.tokens.append(Token(TokenType.N_VAR, "n", start_line, start_col))
            return

        # Keywords
        if lower in _KEYWORDS:
            self.tokens.append(Token(_KEYWORDS[lower], lower, start_line, start_col))
            return

        # Regular identifier
        self.tokens.append(Token(TokenType.IDENTIFIER, word, start_line, start_col))


# ======================================================================
# AST Nodes
# ======================================================================

@dataclass
class ASTNode:
    """Base class for all AST nodes in the FizzLang syntax tree."""
    line: int = 0


@dataclass
class LiteralNode(ASTNode):
    """An integer, string, or boolean literal."""
    value: Any = None


@dataclass
class NVarNode(ASTNode):
    """Reference to the sacred variable 'n' — the number being evaluated."""
    pass


@dataclass
class IdentifierNode(ASTNode):
    """Reference to a let-bound variable."""
    name: str = ""


@dataclass
class BinaryOpNode(ASTNode):
    """A binary operation: left op right."""
    op: str = ""
    left: Optional[ASTNode] = None
    right: Optional[ASTNode] = None


@dataclass
class UnaryOpNode(ASTNode):
    """A unary operation: op operand (currently just NOT and unary minus)."""
    op: str = ""
    operand: Optional[ASTNode] = None


@dataclass
class FunctionCallNode(ASTNode):
    """A stdlib function call: name(args...)."""
    name: str = ""
    args: list[ASTNode] = field(default_factory=list)


@dataclass
class RuleNode(ASTNode):
    """A rule definition: rule NAME when CONDITION emit EXPR [priority N]."""
    name: str = ""
    condition: Optional[ASTNode] = None
    emit_expr: Optional[ASTNode] = None
    priority: int = 0


@dataclass
class LetNode(ASTNode):
    """A let binding: let NAME = EXPR."""
    name: str = ""
    value: Optional[ASTNode] = None


@dataclass
class EvaluateNode(ASTNode):
    """An evaluate statement: evaluate START to END."""
    start: Optional[ASTNode] = None
    end: Optional[ASTNode] = None


@dataclass
class ProgramNode(ASTNode):
    """The root node: a sequence of statements."""
    statements: list[ASTNode] = field(default_factory=list)


# ======================================================================
# Parser
# ======================================================================

class Parser:
    """Recursive-descent parser for the FizzLang DSL.

    Consumes a token stream and produces an Abstract Syntax Tree.
    The grammar is deliberately minimal — no loops, no function
    definitions, no recursion — ensuring the language remains
    forever Turing-incomplete. This parser handles:

    - ``rule NAME when CONDITION emit EXPR [priority N]``
    - ``let NAME = EXPR``
    - ``evaluate START to END``
    - Arithmetic and comparison expressions
    - Boolean operators (and, or, not)
    - Stdlib function calls
    """

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _current(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # EOF

    def _peek_type(self) -> TokenType:
        return self._current().type

    def _advance(self) -> Token:
        tok = self._current()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _expect(self, token_type: TokenType, label: str = "") -> Token:
        tok = self._current()
        if tok.type != token_type:
            expected = label or token_type.name
            raise FizzLangParseError(expected, repr(tok.value), tok.line)
        return self._advance()

    def _skip_newlines(self) -> None:
        while self._peek_type() == TokenType.NEWLINE:
            self._advance()

    def parse(self) -> ProgramNode:
        """Parse the token stream into a ProgramNode AST."""
        program = ProgramNode(line=1)
        self._skip_newlines()

        while self._peek_type() != TokenType.EOF:
            stmt = self._parse_statement()
            if stmt is not None:
                program.statements.append(stmt)
            self._skip_newlines()

        return program

    def _parse_statement(self) -> Optional[ASTNode]:
        """Parse a single top-level statement."""
        tt = self._peek_type()

        if tt == TokenType.RULE:
            return self._parse_rule()
        elif tt == TokenType.LET:
            return self._parse_let()
        elif tt == TokenType.EVALUATE:
            return self._parse_evaluate()
        elif tt == TokenType.NEWLINE:
            self._advance()
            return None
        else:
            raise FizzLangParseError(
                "statement (rule, let, or evaluate)",
                repr(self._current().value),
                self._current().line,
            )

    def _parse_rule(self) -> RuleNode:
        """Parse: rule NAME when CONDITION emit EXPR [priority N]."""
        tok = self._expect(TokenType.RULE, "rule")
        line = tok.line

        name_tok = self._expect(TokenType.IDENTIFIER, "rule name")
        name = name_tok.value

        self._expect(TokenType.WHEN, "when")
        condition = self._parse_expression()

        self._expect(TokenType.EMIT, "emit")
        emit_expr = self._parse_expression()

        priority = 0
        if self._peek_type() == TokenType.PRIORITY:
            self._advance()
            # Handle optional negative sign for priority
            negate = False
            if self._peek_type() == TokenType.MINUS:
                negate = True
                self._advance()
            priority_tok = self._expect(TokenType.INTEGER, "priority number")
            priority = -priority_tok.value if negate else priority_tok.value

        return RuleNode(line=line, name=name, condition=condition, emit_expr=emit_expr, priority=priority)

    def _parse_let(self) -> LetNode:
        """Parse: let NAME = EXPR."""
        tok = self._expect(TokenType.LET, "let")
        line = tok.line

        name_tok = self._expect(TokenType.IDENTIFIER, "variable name")
        name = name_tok.value

        self._expect(TokenType.ASSIGN, "=")
        value = self._parse_expression()

        return LetNode(line=line, name=name, value=value)

    def _parse_evaluate(self) -> EvaluateNode:
        """Parse: evaluate START to END."""
        tok = self._expect(TokenType.EVALUATE, "evaluate")
        line = tok.line

        start = self._parse_expression()
        self._expect(TokenType.TO, "to")
        end = self._parse_expression()

        return EvaluateNode(line=line, start=start, end=end)

    # ---- Expression parsing (precedence climbing) ----

    def _parse_expression(self) -> ASTNode:
        """Parse a full expression (lowest precedence: OR)."""
        return self._parse_or()

    def _parse_or(self) -> ASTNode:
        left = self._parse_and()
        while self._peek_type() == TokenType.OR:
            op_tok = self._advance()
            right = self._parse_and()
            left = BinaryOpNode(line=op_tok.line, op="or", left=left, right=right)
        return left

    def _parse_and(self) -> ASTNode:
        left = self._parse_not()
        while self._peek_type() == TokenType.AND:
            op_tok = self._advance()
            right = self._parse_not()
            left = BinaryOpNode(line=op_tok.line, op="and", left=left, right=right)
        return left

    def _parse_not(self) -> ASTNode:
        if self._peek_type() == TokenType.NOT:
            op_tok = self._advance()
            operand = self._parse_not()
            return UnaryOpNode(line=op_tok.line, op="not", operand=operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> ASTNode:
        left = self._parse_additive()
        comp_ops = {
            TokenType.EQUALS, TokenType.NOT_EQUALS,
            TokenType.LESS_THAN, TokenType.GREATER_THAN,
            TokenType.LESS_EQUAL, TokenType.GREATER_EQUAL,
        }
        if self._peek_type() in comp_ops:
            op_tok = self._advance()
            right = self._parse_additive()
            return BinaryOpNode(line=op_tok.line, op=op_tok.value, left=left, right=right)
        return left

    def _parse_additive(self) -> ASTNode:
        left = self._parse_multiplicative()
        while self._peek_type() in (TokenType.PLUS, TokenType.MINUS):
            op_tok = self._advance()
            right = self._parse_multiplicative()
            left = BinaryOpNode(line=op_tok.line, op=op_tok.value, left=left, right=right)
        return left

    def _parse_multiplicative(self) -> ASTNode:
        left = self._parse_unary()
        while self._peek_type() in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op_tok = self._advance()
            right = self._parse_unary()
            left = BinaryOpNode(line=op_tok.line, op=op_tok.value, left=left, right=right)
        return left

    def _parse_unary(self) -> ASTNode:
        if self._peek_type() == TokenType.MINUS:
            op_tok = self._advance()
            operand = self._parse_unary()
            return UnaryOpNode(line=op_tok.line, op="-", operand=operand)
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        tok = self._current()

        if tok.type == TokenType.INTEGER:
            self._advance()
            return LiteralNode(line=tok.line, value=tok.value)

        if tok.type == TokenType.STRING:
            self._advance()
            return LiteralNode(line=tok.line, value=tok.value)

        if tok.type == TokenType.TRUE:
            self._advance()
            return LiteralNode(line=tok.line, value=True)

        if tok.type == TokenType.FALSE:
            self._advance()
            return LiteralNode(line=tok.line, value=False)

        if tok.type == TokenType.N_VAR:
            self._advance()
            return NVarNode(line=tok.line)

        if tok.type == TokenType.IDENTIFIER:
            name = tok.value
            self._advance()
            # Check for function call
            if self._peek_type() == TokenType.LPAREN:
                return self._parse_function_call(name, tok.line)
            return IdentifierNode(line=tok.line, name=name)

        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, ")")
            return expr

        raise FizzLangParseError(
            "expression",
            repr(tok.value),
            tok.line,
        )

    def _parse_function_call(self, name: str, line: int) -> FunctionCallNode:
        """Parse a function call: name(arg1, arg2, ...)."""
        self._expect(TokenType.LPAREN, "(")
        args: list[ASTNode] = []
        if self._peek_type() != TokenType.RPAREN:
            args.append(self._parse_expression())
            while self._peek_type() == TokenType.COMMA:
                self._advance()
                args.append(self._parse_expression())
        self._expect(TokenType.RPAREN, ")")
        return FunctionCallNode(line=line, name=name, args=args)


# ======================================================================
# Type Checker
# ======================================================================

class TypeChecker:
    """AST-level semantic validator for FizzLang programs.

    Enforces constraints that the parser cannot:
    - Rule names must be unique (no two rules may share a name)
    - At least one rule or evaluate must exist (empty programs are nihilistic)
    - Variable references must resolve to let-bindings defined earlier
    - Function calls must reference stdlib functions with correct arity
    - Priorities must be non-negative

    The type checker is the enterprise equivalent of a disapproving
    code reviewer: technically correct, pedantically thorough, and
    occasionally infuriating.
    """

    STDLIB_FUNCTIONS: dict[str, int] = {
        "is_prime": 1,
        "fizzbuzz": 1,
        "range": 2,
    }

    def __init__(self, strict: bool = True) -> None:
        self.strict = strict

    def check(self, program: ProgramNode) -> list[str]:
        """Validate the AST. Returns a list of warnings (errors are raised)."""
        warnings: list[str] = []
        rule_names: set[str] = set()
        let_names: set[str] = set()
        has_rule = False
        has_evaluate = False

        for stmt in program.statements:
            if isinstance(stmt, RuleNode):
                has_rule = True
                if stmt.name in rule_names:
                    raise FizzLangTypeError(
                        f"Duplicate rule name '{stmt.name}'",
                        node_type="RuleNode",
                    )
                rule_names.add(stmt.name)

                if stmt.priority < 0:
                    raise FizzLangTypeError(
                        f"Rule '{stmt.name}' has negative priority {stmt.priority}. "
                        f"Negative priorities are reserved for rules that actively avoid matching.",
                        node_type="RuleNode",
                    )

                self._check_expr(stmt.condition, let_names)
                self._check_expr(stmt.emit_expr, let_names)

            elif isinstance(stmt, LetNode):
                if stmt.name in let_names and self.strict:
                    raise FizzLangTypeError(
                        f"Duplicate let binding '{stmt.name}'",
                        node_type="LetNode",
                    )
                let_names.add(stmt.name)
                self._check_expr(stmt.value, let_names)

            elif isinstance(stmt, EvaluateNode):
                has_evaluate = True
                self._check_expr(stmt.start, let_names)
                self._check_expr(stmt.end, let_names)

        if not has_rule and not has_evaluate:
            warnings.append(
                "Program contains no rules and no evaluate statements. "
                "This is technically valid but existentially questionable."
            )

        return warnings

    def _check_expr(self, node: Optional[ASTNode], let_names: set[str]) -> None:
        """Recursively validate an expression subtree."""
        if node is None:
            return

        if isinstance(node, LiteralNode):
            return

        if isinstance(node, NVarNode):
            return

        if isinstance(node, IdentifierNode):
            if node.name not in let_names:
                raise FizzLangTypeError(
                    f"Undefined variable '{node.name}'. Did you forget a let binding?",
                    node_type="IdentifierNode",
                )

        elif isinstance(node, BinaryOpNode):
            self._check_expr(node.left, let_names)
            self._check_expr(node.right, let_names)

        elif isinstance(node, UnaryOpNode):
            self._check_expr(node.operand, let_names)

        elif isinstance(node, FunctionCallNode):
            if node.name not in self.STDLIB_FUNCTIONS:
                raise FizzLangTypeError(
                    f"Unknown function '{node.name}'. FizzLang's standard library "
                    f"contains exactly 3 functions: is_prime(), fizzbuzz(), range(). "
                    f"User-defined functions are intentionally unsupported because "
                    f"abstraction is the enemy of enterprise simplicity.",
                    node_type="FunctionCallNode",
                )
            expected_arity = self.STDLIB_FUNCTIONS[node.name]
            if len(node.args) != expected_arity:
                raise FizzLangTypeError(
                    f"Function '{node.name}' expects {expected_arity} argument(s), "
                    f"got {len(node.args)}",
                    node_type="FunctionCallNode",
                )
            for arg in node.args:
                self._check_expr(arg, let_names)


# ======================================================================
# Standard Library
# ======================================================================

class StdLib:
    """The FizzLang Standard Library: three functions of immeasurable importance.

    - ``is_prime(n)``: Determine primality via trial division. Because
      FizzBuzz rules might need to know if a number is prime, even though
      no standard FizzBuzz rule has ever required this.

    - ``fizzbuzz(n)``: Evaluate standard FizzBuzz for a single number.
      The recursive irony of a FizzBuzz DSL that contains a built-in
      FizzBuzz function, running inside a FizzBuzz platform, is not
      lost on us. It is, in fact, the entire point.

    - ``range(a, b)``: Return a list of integers from a to b inclusive.
      Provided so that evaluate statements can use computed ranges.
    """

    @staticmethod
    def is_prime(n: int) -> bool:
        """Trial-division primality test. O(sqrt(n)) because we're not barbarians."""
        if not isinstance(n, (int, float)):
            raise FizzLangRuntimeError(f"is_prime() expects an integer, got {type(n).__name__}")
        n = int(n)
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

    @staticmethod
    def fizzbuzz(n: int) -> str:
        """The recursive irony: FizzBuzz implemented inside a FizzBuzz DSL.

        This function implements standard FizzBuzz in one line, because
        the most enterprise way to solve FizzBuzz is to build a DSL that
        contains a built-in function that solves FizzBuzz.
        """
        if not isinstance(n, (int, float)):
            raise FizzLangRuntimeError(f"fizzbuzz() expects an integer, got {type(n).__name__}")
        n = int(n)
        return "FizzBuzz" if n % 15 == 0 else "Fizz" if n % 3 == 0 else "Buzz" if n % 5 == 0 else str(n)

    @staticmethod
    def range_inclusive(a: int, b: int) -> list[int]:
        """Return integers from a to b inclusive. Revolutionary."""
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            raise FizzLangRuntimeError("range() expects two integers")
        return list(range(int(a), int(b) + 1))


# ======================================================================
# Interpreter
# ======================================================================

@dataclass
class EvalResult:
    """Result of evaluating a single number through FizzLang rules."""
    number: int
    output: str
    matched_rules: list[str] = field(default_factory=list)


class Interpreter:
    """Tree-walking interpreter for FizzLang ASTs.

    Walks the AST node by node, evaluating expressions and applying
    rules to numbers. The interpreter maintains a simple environment
    for let-bindings and supports the 3-function standard library.

    The interpretation process is intentionally single-threaded and
    sequential, because parallel FizzBuzz evaluation is handled by
    17 other subsystems in this platform.
    """

    def __init__(self, stdlib_enabled: bool = True) -> None:
        self.stdlib_enabled = stdlib_enabled
        self.stdlib = StdLib()
        self.env: dict[str, Any] = {}
        self.rules: list[RuleNode] = []
        self.eval_results: list[EvalResult] = []
        self._current_n: Optional[int] = None

    def interpret(self, program: ProgramNode) -> list[EvalResult]:
        """Interpret a FizzLang program, returning evaluation results."""
        self.env = {}
        self.rules = []
        self.eval_results = []
        self._current_n = None

        # First pass: collect let-bindings and rules
        for stmt in program.statements:
            if isinstance(stmt, LetNode):
                self.env[stmt.name] = self._eval_expr(stmt.value)
            elif isinstance(stmt, RuleNode):
                self.rules.append(stmt)

        # Sort rules by priority (lower number = higher priority)
        self.rules.sort(key=lambda r: r.priority)

        # Second pass: process evaluate statements
        for stmt in program.statements:
            if isinstance(stmt, EvaluateNode):
                start = self._eval_expr(stmt.start)
                end = self._eval_expr(stmt.end)
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                    raise FizzLangRuntimeError("evaluate range must be integers")
                for n in range(int(start), int(end) + 1):
                    result = self._evaluate_number(n)
                    self.eval_results.append(result)

        return self.eval_results

    def _evaluate_number(self, n: int) -> EvalResult:
        """Evaluate all rules against a single number."""
        self._current_n = n
        matched_labels: list[str] = []
        matched_names: list[str] = []

        for rule in self.rules:
            try:
                condition_result = self._eval_expr(rule.condition)
                if condition_result:
                    emit_value = self._eval_expr(rule.emit_expr)
                    matched_labels.append(str(emit_value))
                    matched_names.append(rule.name)
            except Exception as e:
                raise FizzLangRuntimeError(
                    f"Error evaluating rule '{rule.name}' for n={n}: {e}",
                    number=n,
                )

        self._current_n = None

        if matched_labels:
            output = "".join(matched_labels)
        else:
            output = str(n)

        return EvalResult(number=n, output=output, matched_rules=matched_names)

    def _eval_expr(self, node: Optional[ASTNode]) -> Any:
        """Evaluate an expression node and return its value."""
        if node is None:
            raise FizzLangRuntimeError("Attempted to evaluate a None expression")

        if isinstance(node, LiteralNode):
            return node.value

        if isinstance(node, NVarNode):
            if self._current_n is None:
                raise FizzLangRuntimeError(
                    "'n' can only be used inside rule conditions and emit expressions"
                )
            return self._current_n

        if isinstance(node, IdentifierNode):
            if node.name not in self.env:
                raise FizzLangRuntimeError(f"Undefined variable '{node.name}'")
            return self.env[node.name]

        if isinstance(node, UnaryOpNode):
            operand = self._eval_expr(node.operand)
            if node.op == "-":
                return -operand
            if node.op == "not":
                return not operand
            raise FizzLangRuntimeError(f"Unknown unary operator '{node.op}'")

        if isinstance(node, BinaryOpNode):
            return self._eval_binary(node)

        if isinstance(node, FunctionCallNode):
            return self._eval_function(node)

        raise FizzLangRuntimeError(f"Unknown AST node type: {type(node).__name__}")

    def _eval_binary(self, node: BinaryOpNode) -> Any:
        """Evaluate a binary operation."""
        # Short-circuit for boolean operators
        if node.op == "and":
            left = self._eval_expr(node.left)
            if not left:
                return False
            return bool(self._eval_expr(node.right))

        if node.op == "or":
            left = self._eval_expr(node.left)
            if left:
                return True
            return bool(self._eval_expr(node.right))

        left = self._eval_expr(node.left)
        right = self._eval_expr(node.right)

        ops: dict[str, Callable[[Any, Any], Any]] = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: self._safe_div(a, b),
            "%": lambda a, b: self._safe_mod(a, b),
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
        }

        if node.op not in ops:
            raise FizzLangRuntimeError(f"Unknown binary operator '{node.op}'")

        try:
            return ops[node.op](left, right)
        except Exception as e:
            raise FizzLangRuntimeError(f"Error evaluating {left} {node.op} {right}: {e}")

    def _safe_div(self, a: Any, b: Any) -> Any:
        if b == 0:
            raise FizzLangRuntimeError("Division by zero. Even FizzLang respects mathematical laws.")
        if isinstance(a, int) and isinstance(b, int):
            return a // b
        return a / b

    def _safe_mod(self, a: Any, b: Any) -> Any:
        if b == 0:
            raise FizzLangRuntimeError("Modulo by zero. The modulus operator has boundaries, both literal and figurative.")
        return a % b

    def _eval_function(self, node: FunctionCallNode) -> Any:
        """Evaluate a stdlib function call."""
        if not self.stdlib_enabled:
            raise FizzLangRuntimeError(
                f"Standard library disabled. Function '{node.name}' is unavailable. "
                f"The 3-function stdlib was deemed too powerful."
            )

        args = [self._eval_expr(arg) for arg in node.args]

        if node.name == "is_prime":
            return self.stdlib.is_prime(args[0])
        elif node.name == "fizzbuzz":
            return self.stdlib.fizzbuzz(args[0])
        elif node.name == "range":
            return self.stdlib.range_inclusive(args[0], args[1])
        else:
            raise FizzLangRuntimeError(f"Unknown function '{node.name}'")


# ======================================================================
# Pipeline: Compile & Run
# ======================================================================

@dataclass
class CompilationUnit:
    """The result of compiling a FizzLang source program.

    Contains everything from source text to final AST, along with
    compilation metadata that no one asked for but everyone deserves.
    """

    source: str
    tokens: list[Token]
    ast: ProgramNode
    warnings: list[str]
    compile_time_ms: float


def compile_program(
    source: str,
    strict_type_checking: bool = True,
    max_program_length: int = 10000,
) -> CompilationUnit:
    """Compile a FizzLang source string into a CompilationUnit.

    Runs the full compilation pipeline: lex -> parse -> type-check.
    Does NOT interpret — that's a separate step, because separation
    of concerns is the foundation of enterprise architecture, even
    when the concerns are trivially small.
    """
    start = time.monotonic()

    if len(source) > max_program_length:
        raise FizzLangError(
            f"Program exceeds maximum length of {max_program_length} characters. "
            f"FizzLang programs should be concise — it's a DSL for modulo arithmetic, "
            f"not War and Peace.",
            error_code="EFP-FL10",
        )

    # Lex
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    # Parse
    parser = Parser(tokens)
    ast = parser.parse()

    # Type check
    checker = TypeChecker(strict=strict_type_checking)
    warnings = checker.check(ast)

    elapsed = (time.monotonic() - start) * 1000

    return CompilationUnit(
        source=source,
        tokens=tokens,
        ast=ast,
        warnings=warnings,
        compile_time_ms=elapsed,
    )


def run_program(
    source: str,
    strict_type_checking: bool = True,
    stdlib_enabled: bool = True,
    max_program_length: int = 10000,
) -> list[EvalResult]:
    """Compile and interpret a FizzLang program in one step.

    The convenience function for when you want results without
    caring about the compilation pipeline. Which is always,
    because this is FizzBuzz.
    """
    unit = compile_program(source, strict_type_checking, max_program_length)
    interpreter = Interpreter(stdlib_enabled=stdlib_enabled)
    return interpreter.interpret(unit.ast)


# ======================================================================
# REPL
# ======================================================================

class FizzLangREPL:
    """Interactive Read-Eval-Print Loop for FizzLang.

    Supports REPL commands:
    - ``:help``  — Show available commands
    - ``:tokens`` — Toggle token display
    - ``:ast``   — Toggle AST display
    - ``:quit``  — Exit the REPL

    The REPL maintains state across inputs, so let-bindings persist
    between prompts. Rules and evaluate statements are executed
    immediately.
    """

    HELP_TEXT = """
  FizzLang REPL Commands:
    :help       Show this help message
    :tokens     Toggle token stream display
    :ast        Toggle AST display
    :quit       Exit the REPL (also: :exit, :q, Ctrl+C)

  Language Quick Reference:
    rule NAME when CONDITION emit EXPR [priority N]
    let NAME = EXPR
    evaluate START to END

  StdLib Functions:
    is_prime(n)    Trial-division primality test
    fizzbuzz(n)    The recursive irony: FizzBuzz inside FizzBuzz
    range(a, b)    Inclusive integer range [a, b]

  Example:
    rule fizz when n % 3 == 0 emit "Fizz"
    rule buzz when n % 5 == 0 emit "Buzz"
    evaluate 1 to 20
"""

    def __init__(
        self,
        prompt: str = "fizz> ",
        show_tokens: bool = False,
        show_ast: bool = False,
        stdlib_enabled: bool = True,
        output_stream: Any = None,
        input_fn: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.prompt = prompt
        self.show_tokens = show_tokens
        self.show_ast = show_ast
        self.stdlib_enabled = stdlib_enabled
        self.history: list[str] = []
        self.env: dict[str, Any] = {}
        self.rules: list[RuleNode] = []
        self._out = output_stream or sys.stdout
        self._input_fn = input_fn or input

    def _write(self, text: str) -> None:
        self._out.write(text)
        if hasattr(self._out, "flush"):
            self._out.flush()

    def run(self) -> None:
        """Start the REPL loop."""
        self._write("\n  FizzLang REPL v1.0.0 — The Turing-Incomplete Experience\n")
        self._write("  Type :help for commands, :quit to exit.\n\n")

        while True:
            try:
                line = self._input_fn(self.prompt)
            except (EOFError, KeyboardInterrupt):
                self._write("\n  Goodbye. May your modulo operations be forever remainder-free.\n\n")
                break

            line = line.strip()
            if not line:
                continue

            # REPL commands
            if line.startswith(":"):
                cmd = line.lower()
                if cmd in (":quit", ":exit", ":q"):
                    self._write("  Goodbye. May your modulo operations be forever remainder-free.\n\n")
                    break
                elif cmd == ":help":
                    self._write(self.HELP_TEXT)
                    continue
                elif cmd == ":tokens":
                    self.show_tokens = not self.show_tokens
                    state = "ON" if self.show_tokens else "OFF"
                    self._write(f"  Token display: {state}\n")
                    continue
                elif cmd == ":ast":
                    self.show_ast = not self.show_ast
                    state = "ON" if self.show_ast else "OFF"
                    self._write(f"  AST display: {state}\n")
                    continue
                else:
                    self._write(f"  Unknown command: {line}\n")
                    continue

            self.history.append(line)

            try:
                # Lex
                lexer = Lexer(line)
                tokens = lexer.tokenize()

                if self.show_tokens:
                    self._write("  Tokens:\n")
                    for t in tokens:
                        if t.type != TokenType.EOF:
                            self._write(f"    {t}\n")

                # Parse
                parser = Parser(tokens)
                ast = parser.parse()

                if self.show_ast:
                    self._write("  AST:\n")
                    self._write(f"    {ast}\n")

                # Interpret inline
                for stmt in ast.statements:
                    if isinstance(stmt, LetNode):
                        interp = Interpreter(stdlib_enabled=self.stdlib_enabled)
                        interp.env = dict(self.env)
                        val = interp._eval_expr(stmt.value)
                        self.env[stmt.name] = val
                        self._write(f"  {stmt.name} = {val!r}\n")

                    elif isinstance(stmt, RuleNode):
                        self.rules.append(stmt)
                        self._write(f"  Rule '{stmt.name}' registered (priority {stmt.priority})\n")

                    elif isinstance(stmt, EvaluateNode):
                        interp = Interpreter(stdlib_enabled=self.stdlib_enabled)
                        interp.env = dict(self.env)
                        interp.rules = sorted(list(self.rules), key=lambda r: r.priority)
                        start_val = interp._eval_expr(stmt.start)
                        end_val = interp._eval_expr(stmt.end)
                        for n in range(int(start_val), int(end_val) + 1):
                            result = interp._evaluate_number(n)
                            self._write(f"  {result.output}\n")

            except (FizzLangLexerError, FizzLangParseError,
                    FizzLangTypeError, FizzLangRuntimeError) as e:
                self._write(f"  Error: {e}\n")
            except Exception as e:
                self._write(f"  Internal error: {e}\n")


# ======================================================================
# AST Pretty-Printer (for :ast and dashboard)
# ======================================================================

def format_ast(node: ASTNode, indent: int = 0) -> str:
    """Render an AST node as a human-readable indented string."""
    prefix = "  " * indent
    lines: list[str] = []

    if isinstance(node, ProgramNode):
        lines.append(f"{prefix}Program:")
        for stmt in node.statements:
            lines.append(format_ast(stmt, indent + 1))

    elif isinstance(node, RuleNode):
        lines.append(f"{prefix}Rule '{node.name}' (priority={node.priority}):")
        lines.append(f"{prefix}  when: {format_ast(node.condition, 0).strip()}")
        lines.append(f"{prefix}  emit: {format_ast(node.emit_expr, 0).strip()}")

    elif isinstance(node, LetNode):
        lines.append(f"{prefix}Let {node.name} = {format_ast(node.value, 0).strip()}")

    elif isinstance(node, EvaluateNode):
        lines.append(f"{prefix}Evaluate {format_ast(node.start, 0).strip()} to {format_ast(node.end, 0).strip()}")

    elif isinstance(node, LiteralNode):
        lines.append(f"{prefix}{node.value!r}")

    elif isinstance(node, NVarNode):
        lines.append(f"{prefix}n")

    elif isinstance(node, IdentifierNode):
        lines.append(f"{prefix}{node.name}")

    elif isinstance(node, BinaryOpNode):
        left = format_ast(node.left, 0).strip() if node.left else "?"
        right = format_ast(node.right, 0).strip() if node.right else "?"
        lines.append(f"{prefix}({left} {node.op} {right})")

    elif isinstance(node, UnaryOpNode):
        operand = format_ast(node.operand, 0).strip() if node.operand else "?"
        lines.append(f"{prefix}({node.op} {operand})")

    elif isinstance(node, FunctionCallNode):
        args_str = ", ".join(
            format_ast(a, 0).strip() for a in node.args
        )
        lines.append(f"{prefix}{node.name}({args_str})")

    else:
        lines.append(f"{prefix}<unknown node: {type(node).__name__}>")

    return "\n".join(lines)


# ======================================================================
# Dashboard
# ======================================================================

class FizzLangDashboard:
    """ASCII dashboard for FizzLang source analysis.

    Renders source statistics, token distribution, AST summary,
    and the all-important Language Complexity Index — which is
    carefully calibrated to always score below Brainfuck, because
    a language designed for modulo arithmetic should not be more
    complex than a language with 8 instructions.
    """

    @staticmethod
    def render(
        source: str,
        unit: Optional[CompilationUnit] = None,
        results: Optional[list[EvalResult]] = None,
        width: int = 60,
        show_source_stats: bool = True,
        show_complexity_index: bool = True,
    ) -> str:
        """Render the FizzLang dashboard."""
        if unit is None:
            try:
                unit = compile_program(source)
            except FizzLangError:
                return _box("FizzLang Dashboard", ["  [Compilation failed]"], width)

        lines: list[str] = []

        if show_source_stats:
            lines.extend(_source_stats(source, unit))

        if show_complexity_index:
            lines.append("")
            lines.extend(_complexity_index(source, unit))

        if results:
            lines.append("")
            lines.extend(_evaluation_stats(results))

        if unit.warnings:
            lines.append("")
            lines.append("  Warnings:")
            for w in unit.warnings:
                lines.append(f"    - {w}")

        return _box("FizzLang Dashboard", lines, width)


def _source_stats(source: str, unit: CompilationUnit) -> list[str]:
    """Generate source code statistics."""
    source_lines = source.strip().split("\n")
    non_empty = [l for l in source_lines if l.strip() and not l.strip().startswith("#")]
    comment_lines = [l for l in source_lines if l.strip().startswith("#")]

    num_rules = sum(1 for s in unit.ast.statements if isinstance(s, RuleNode))
    num_lets = sum(1 for s in unit.ast.statements if isinstance(s, LetNode))
    num_evals = sum(1 for s in unit.ast.statements if isinstance(s, EvaluateNode))

    # Token distribution
    token_counts: dict[str, int] = {}
    for t in unit.tokens:
        if t.type != TokenType.EOF and t.type != TokenType.NEWLINE:
            name = t.type.name
            token_counts[name] = token_counts.get(name, 0) + 1

    lines = [
        "  Source Statistics:",
        f"    Total lines:      {len(source_lines)}",
        f"    Code lines:       {len(non_empty)}",
        f"    Comment lines:    {len(comment_lines)}",
        f"    Characters:       {len(source)}",
        f"    Tokens:           {len(unit.tokens) - 1}",  # exclude EOF
        f"    Compile time:     {unit.compile_time_ms:.3f}ms",
        "",
        "  Program Structure:",
        f"    Rules:            {num_rules}",
        f"    Let bindings:     {num_lets}",
        f"    Evaluate stmts:   {num_evals}",
        f"    Total statements: {len(unit.ast.statements)}",
    ]

    if token_counts:
        lines.append("")
        lines.append("  Token Distribution:")
        sorted_counts = sorted(token_counts.items(), key=lambda x: -x[1])
        for name, count in sorted_counts[:8]:
            bar = "#" * min(count, 20)
            lines.append(f"    {name:<18s} {count:>3d} {bar}")

    return lines


def _complexity_index(source: str, unit: CompilationUnit) -> list[str]:
    """Calculate the Language Complexity Index.

    The LCI is a completely fabricated metric that measures how
    "complex" a FizzLang program is relative to other languages.
    It is carefully calibrated to ALWAYS score below Brainfuck (1.0),
    because any language designed for modulo arithmetic that scores
    higher than a language with 8 instructions has failed at its
    primary mission of being simple.

    Formula: LCI = (unique_tokens * statement_count) / (chars * pi)
    Capped at 0.95 to ensure the Brainfuck invariant holds.
    """
    num_tokens = len(set(t.type for t in unit.tokens if t.type not in (TokenType.EOF, TokenType.NEWLINE)))
    num_stmts = len(unit.ast.statements)
    num_chars = max(len(source), 1)

    raw_lci = (num_tokens * num_stmts) / (num_chars * math.pi)
    lci = min(raw_lci, 0.95)  # MUST be below Brainfuck (1.0)

    brainfuck_score = 1.0
    cobol_score = 7.3
    java_score = 8.1
    enterprise_fizzbuzz_score = 42.0

    lines = [
        "  Language Complexity Index (LCI):",
        f"    FizzLang program:     {lci:.4f}",
        f"    Brainfuck:            {brainfuck_score:.4f}  {'<-- still more complex' if lci < brainfuck_score else ''}",
        f"    COBOL:                {cobol_score:.4f}",
        f"    Java:                 {java_score:.4f}",
        f"    Enterprise FizzBuzz:  {enterprise_fizzbuzz_score:.4f}  (the platform, not the language)",
        "",
    ]

    if lci < brainfuck_score:
        lines.append("    Status: BELOW BRAINFUCK -- mission accomplished")
    else:
        lines.append("    Status: ABOVE BRAINFUCK -- this should never happen")

    return lines


def _evaluation_stats(results: list[EvalResult]) -> list[str]:
    """Generate evaluation result statistics."""
    if not results:
        return ["  No evaluation results."]

    total = len(results)
    matched = sum(1 for r in results if r.matched_rules)
    unmatched = total - matched

    # Count unique outputs
    output_counts: dict[str, int] = {}
    for r in results:
        output_counts[r.output] = output_counts.get(r.output, 0) + 1

    lines = [
        "  Evaluation Results:",
        f"    Numbers evaluated:  {total}",
        f"    Rules matched:      {matched}",
        f"    Plain numbers:      {unmatched}",
        f"    Unique outputs:     {len(output_counts)}",
    ]

    # Top outputs
    if output_counts:
        lines.append("")
        lines.append("  Output Distribution (top 5):")
        sorted_outputs = sorted(output_counts.items(), key=lambda x: -x[1])
        for output, count in sorted_outputs[:5]:
            display = output if len(output) <= 15 else output[:12] + "..."
            pct = (count / total) * 100
            lines.append(f"    {display:<15s} {count:>4d} ({pct:.1f}%)")

    return lines


def _box(title: str, content_lines: list[str], width: int) -> str:
    """Render content inside an ASCII box."""
    lines: list[str] = []
    lines.append(f"+{'=' * (width - 2)}+")
    lines.append(f"|{title:^{width - 2}}|")
    lines.append(f"+{'-' * (width - 2)}+")
    for line in content_lines:
        # Truncate or pad to fit
        if len(line) > width - 4:
            line = line[:width - 7] + "..."
        lines.append(f"| {line:<{width - 4}} |")
    lines.append(f"+{'=' * (width - 2)}+")
    return "\n".join(lines)

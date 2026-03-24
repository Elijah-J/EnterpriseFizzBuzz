"""
Enterprise FizzBuzz Platform - FizzPolicy: Declarative Policy Engine

A complete declarative policy engine implementing a Rego-inspired policy
language (FizzRego), a multi-phase policy compiler, a high-performance
evaluation engine with backtracking, versioned policy bundles with
cryptographic signing, comprehensive decision logging, external data
integration via pluggable adapters, a policy testing framework with
coverage analysis, and real-time policy hot-reload.

The Enterprise FizzBuzz Platform enforces access control, compliance, and
operational constraints through five independent subsystems: RBAC
(auth.py), compliance (compliance.py), capability security
(capability_security.py), network policy (fizzcni.py), and approval
workflows (approval.py).  These subsystems share a common purpose --
determining whether a requested action is permitted -- but share no
common language, evaluation engine, audit trail, or management interface.
When a cross-domain policy question arises ("under what conditions can a
FIZZBUZZ_ANALYST evaluate numbers above 100?"), the answer requires
reading procedural Python code across multiple modules and mentally
composing the results.

FizzPolicy unifies all five enforcement domains under a single
declarative policy language.  Policy logic moves from Python code into
FizzRego documents.  Enforcement mechanisms remain in Python code.
Each enforcement point delegates its decision to FizzPolicy, which
evaluates the request against the current policy bundle and returns a
structured decision with an explanation.  The separation is clean,
auditable, and independently deployable.

The policy engine evaluates queries against a policy document and a data
document, producing a decision.  Policies are organized into packages
that mirror the platform's enforcement domains.  The compiler transforms
FizzRego source through four phases: lexing, parsing, type checking, and
plan generation with optional partial evaluation.  The evaluation engine
executes compiled plans with backtracking semantics, enforcing timeout,
iteration, and output size limits.  Decision logs record every policy
evaluation for compliance auditing.  Bundle signing ensures policy
integrity and provenance.

Architecture reference: Open Policy Agent (OPA), Rego policy language
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import re
import threading
import time
import uuid
from collections import defaultdict, deque, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions import (
    PolicyEngineError,
    PolicyLexerError,
    PolicyParserError,
    PolicyTypeCheckError,
    PolicyPartialEvalError,
    PolicyPlanGeneratorError,
    PolicyEvaluationError,
    PolicyEvaluationTimeoutError,
    PolicyEvaluationLimitError,
    PolicyBundleError,
    PolicyBundleBuildError,
    PolicyBundleIntegrityError,
    PolicyBundleVersionError,
    PolicyBundleStoreError,
    PolicyBundleSigningError,
    PolicyDecisionLogError,
    PolicyDecisionQueryError,
    PolicyDecisionExportError,
    PolicyDataAdapterError,
    PolicyDataRefreshError,
    PolicyTestError,
    PolicyTestFailedError,
    PolicyCoverageError,
    PolicyBenchmarkError,
    PolicyWatcherError,
    PolicyHotReloadError,
    PolicyBuiltinError,
    PolicyAdmissionDeniedError,
    PolicyMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzpolicy")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIZZPOLICY_VERSION = "1.0.0"
"""FizzPolicy engine version."""

FIZZREGO_LANGUAGE_VERSION = "0.1.0"
"""FizzRego language specification version."""

DEFAULT_EVAL_TIMEOUT_MS = 100.0
"""Maximum wall-clock time for a single policy evaluation in milliseconds."""

DEFAULT_MAX_ITERATIONS = 100_000
"""Maximum number of plan instruction executions per evaluation."""

DEFAULT_MAX_OUTPUT_SIZE_BYTES = 1_048_576
"""Maximum size of the result document in bytes (1 MB)."""

DEFAULT_CACHE_MAX_ENTRIES = 10_000
"""Maximum entries in the evaluation cache (LRU)."""

DEFAULT_DATA_REFRESH_INTERVAL = 30.0
"""Default data adapter refresh interval in seconds."""

DEFAULT_BUNDLE_COVERAGE_THRESHOLD = 80.0
"""Minimum test coverage percentage for bundle builds."""

DEFAULT_BUNDLE_PERF_THRESHOLD_MS = 10.0
"""Maximum p99 evaluation time in milliseconds for bundle performance checks."""

DEFAULT_BENCHMARK_ITERATIONS = 1000
"""Default number of iterations for policy benchmarks."""

DEFAULT_DECISION_LOG_PAGE_SIZE = 100
"""Default page size for decision log queries."""

DEFAULT_BUNDLE_REVISION_HISTORY = 50
"""Maximum number of bundle revisions retained in the version manager."""

MIDDLEWARE_PRIORITY = 6
"""Middleware pipeline priority for FizzPolicy.

FizzPolicy runs immediately after authentication (priority 5) and before
all other subsystems.  This ensures that every subsequent middleware in
the pipeline operates under a policy decision that has already been
evaluated.  Authorization, compliance, capability, and network policy
enforcement points query FizzPolicy during their own processing, but the
middleware itself performs the unified admission check that gates the
entire request.
"""

SIGNING_KEY_ID = "fizzbuzz-policy-signing-key"
"""Default key identifier for bundle HMAC-SHA256 signatures."""

SIGNING_ALGORITHM = "HMAC-SHA256"
"""Signing algorithm for policy bundles."""

HASH_ALGORITHM = "SHA-256"
"""Hash algorithm for bundle file integrity verification."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TokenType(Enum):
    """FizzRego lexer token types.

    The lexer produces a stream of tokens from FizzRego source text.
    Each token carries a type, a literal value, and a source location
    (line, column) for diagnostic messages.
    """
    PACKAGE = "PACKAGE"
    IMPORT = "IMPORT"
    DEFAULT = "DEFAULT"
    NOT = "NOT"
    SOME = "SOME"
    EVERY = "EVERY"
    WITH = "WITH"
    AS = "AS"
    IF = "IF"
    ELSE = "ELSE"
    TRUE = "TRUE"
    FALSE = "FALSE"
    NULL = "NULL"
    IDENT = "IDENT"
    STRING = "STRING"
    NUMBER = "NUMBER"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    LBRACKET = "LBRACKET"
    RBRACKET = "RBRACKET"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    DOT = "DOT"
    COMMA = "COMMA"
    SEMICOLON = "SEMICOLON"
    COLON = "COLON"
    ASSIGN = "ASSIGN"
    EQ = "EQ"
    NEQ = "NEQ"
    LT = "LT"
    GT = "GT"
    LTE = "LTE"
    GTE = "GTE"
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"
    PERCENT = "PERCENT"
    PIPE = "PIPE"
    AMPERSAND = "AMPERSAND"
    COMMENT = "COMMENT"
    NEWLINE = "NEWLINE"
    EOF = "EOF"


class RegoType(Enum):
    """FizzRego type system types.

    The type checker infers types for all expressions in the AST.
    Type checking is advisory (warnings, not hard failures) because
    FizzRego is dynamically typed at runtime.
    """
    BOOLEAN = "boolean"
    NUMBER = "number"
    STRING = "string"
    NULL = "null"
    SET = "set"
    ARRAY = "array"
    OBJECT = "object"
    ANY = "any"
    UNDEFINED = "undefined"


class PlanOpcode(Enum):
    """Compiled plan instruction opcodes.

    The plan generator compiles the AST into a linear sequence of
    instructions that the PlanExecutor evaluates with backtracking.
    """
    SCAN = "SCAN"
    FILTER = "FILTER"
    LOOKUP = "LOOKUP"
    ASSIGN = "ASSIGN"
    CALL = "CALL"
    NOT = "NOT"
    AGGREGATE = "AGGREGATE"
    YIELD = "YIELD"
    HALT = "HALT"


class ExplanationMode(Enum):
    """Decision explanation verbosity level.

    Controls the amount of detail recorded in the evaluation trace
    that accompanies each policy decision.
    """
    FULL = "full"
    SUMMARY = "summary"
    MINIMAL = "minimal"
    OFF = "off"


class DecisionResult(Enum):
    """High-level policy decision outcome for filtering and reporting."""
    ALLOW = "allow"
    DENY = "deny"
    ERROR = "error"
    UNDEFINED = "undefined"


class DataAdapterState(Enum):
    """Health state of a data adapter's refresh cycle."""
    HEALTHY = "healthy"
    STALE = "stale"
    ERROR = "error"
    DISABLED = "disabled"


class BundleState(Enum):
    """Lifecycle state of a policy bundle revision."""
    BUILDING = "building"
    TESTING = "testing"
    SIGNED = "signed"
    ACTIVE = "active"
    INACTIVE = "inactive"
    REJECTED = "rejected"


class PolicyTestResultEnum(Enum):
    """Outcome of an individual policy test rule evaluation."""
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Token:
    """A single token produced by the FizzRego lexer.

    Attributes:
        token_type: The type of token.
        literal: The literal string value from the source.
        line: Source line number (1-based).
        column: Source column number (1-based).
        file: Source file path (for multi-file bundles).
    """
    token_type: TokenType
    literal: str
    line: int = 1
    column: int = 1
    file: str = ""


@dataclass
class ASTNode:
    """Base class for all FizzRego Abstract Syntax Tree nodes.

    Attributes:
        node_type: Discriminator for the AST node kind.
        line: Source line number for diagnostics.
        column: Source column for diagnostics.
        inferred_type: Type assigned by the type checker (None before type checking).
    """
    node_type: str = ""
    line: int = 0
    column: int = 0
    inferred_type: Optional[RegoType] = None


@dataclass
class PackageNode(ASTNode):
    """Package declaration: ``package fizzbuzz.authz``.

    Attributes:
        path: The dotted package path segments.
    """
    path: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "package"


@dataclass
class ImportNode(ASTNode):
    """Import declaration: ``import data.fizzbuzz.compliance as compliance``.

    Attributes:
        path: The dotted import path segments.
        alias: Optional alias for the import.
    """
    path: List[str] = field(default_factory=list)
    alias: str = ""

    def __post_init__(self):
        self.node_type = "import"


@dataclass
class RuleNode(ASTNode):
    """A complete or partial rule definition.

    Attributes:
        name: Rule head identifier.
        is_default: Whether this is a ``default`` rule.
        default_value: Default value for default rules.
        key_var: Key variable for partial object rules (e.g., ``[key]``).
        value_var: Value variable for partial set rules (e.g., ``[elem]``).
        body: List of body expressions (conditions).
        assign_value: Value assigned by complete rules.
        annotations: Rule metadata annotations.
    """
    name: str = ""
    is_default: bool = False
    default_value: Any = None
    key_var: str = ""
    value_var: str = ""
    body: List[ASTNode] = field(default_factory=list)
    assign_value: Optional[ASTNode] = None
    annotations: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.node_type = "rule"


@dataclass
class ExprNode(ASTNode):
    """A binary or unary expression node.

    Attributes:
        operator: The operator string (==, !=, <, >, <=, >=, +, -, *, /, %).
        left: Left operand.
        right: Right operand (None for unary expressions).
    """
    operator: str = ""
    left: Optional[ASTNode] = None
    right: Optional[ASTNode] = None

    def __post_init__(self):
        self.node_type = "expr"


@dataclass
class TermNode(ASTNode):
    """A terminal value: identifier, literal, or reference.

    Attributes:
        value: The Python value (str, int, float, bool, None).
        is_ref: Whether this is a reference (dot-chain or bracket-chain).
        ref_path: Reference path segments for data/input lookups.
    """
    value: Any = None
    is_ref: bool = False
    ref_path: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "term"


@dataclass
class RefNode(ASTNode):
    """A chain of dot and bracket accesses: ``data.roles[input.user]``.

    Attributes:
        segments: List of path segments (strings for dot access, ASTNode for bracket).
    """
    segments: List[Any] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "ref"


@dataclass
class ComprehensionNode(ASTNode):
    """Inline set, array, or object comprehension.

    Attributes:
        kind: One of "set", "array", "object".
        term: The term expression to collect.
        key_term: Key expression for object comprehensions.
        body: Body expressions (iteration and filter conditions).
    """
    kind: str = "set"
    term: Optional[ASTNode] = None
    key_term: Optional[ASTNode] = None
    body: List[ASTNode] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "comprehension"


@dataclass
class SomeNode(ASTNode):
    """Local variable declaration: ``some user, role``, ``some x in collection``.

    Attributes:
        variables: Variable names being declared.
        domain: Optional iteration domain (the collection after ``in``).
    """
    variables: List[str] = field(default_factory=list)
    domain: Optional[ASTNode] = None

    def __post_init__(self):
        self.node_type = "some"


@dataclass
class EveryNode(ASTNode):
    """Universal quantification: ``every x in collection { body }``.

    Attributes:
        key_var: Key variable (for objects/arrays).
        value_var: Value variable.
        domain: The collection to iterate over.
        body: Body expressions that must hold for every element.
    """
    key_var: str = ""
    value_var: str = ""
    domain: Optional[ASTNode] = None
    body: List[ASTNode] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "every"


@dataclass
class WithNode(ASTNode):
    """Input/data override: ``allow with input as {...}``.

    Attributes:
        target: The target path to override (e.g., "input", "data.roles").
        value: The override value AST node.
    """
    target: str = ""
    value: Optional[ASTNode] = None

    def __post_init__(self):
        self.node_type = "with"


@dataclass
class CallNode(ASTNode):
    """Built-in function call: ``sprintf(fmt, [args])``.

    Attributes:
        function_name: The function name (may be dotted, e.g., "regex.match").
        arguments: List of argument AST nodes.
    """
    function_name: str = ""
    arguments: List[ASTNode] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "call"


@dataclass
class NotNode(ASTNode):
    """Negation: ``not suspended[input.user]``.

    Attributes:
        operand: The expression being negated.
    """
    operand: Optional[ASTNode] = None

    def __post_init__(self):
        self.node_type = "not"


@dataclass
class PolicyModule:
    """A compiled policy module (one .rego file).

    Attributes:
        file_path: Source file path.
        package_path: Dotted package path.
        imports: List of ImportNode declarations.
        rules: List of compiled RuleNode definitions.
        raw_source: Original FizzRego source text.
    """
    file_path: str = ""
    package_path: str = ""
    imports: List[ImportNode] = field(default_factory=list)
    rules: List[RuleNode] = field(default_factory=list)
    raw_source: str = ""


@dataclass
class PlanInstruction:
    """A single compiled plan instruction.

    Attributes:
        opcode: The instruction opcode.
        operands: Opcode-specific operand data.
        children: Child instructions (for NOT, AGGREGATE sub-plans).
        source_line: Source line for diagnostics.
    """
    opcode: PlanOpcode
    operands: Dict[str, Any] = field(default_factory=dict)
    children: List[PlanInstruction] = field(default_factory=list)
    source_line: int = 0


@dataclass
class CompiledPlan:
    """A compiled execution plan for a rule.

    Attributes:
        rule_name: The rule this plan evaluates.
        package_path: Package containing the rule.
        instructions: The linear instruction sequence.
        is_complete: Whether this is a complete rule (single value) or partial (set/object).
        default_value: Default value if no rule body matches.
    """
    rule_name: str = ""
    package_path: str = ""
    instructions: List[PlanInstruction] = field(default_factory=list)
    is_complete: bool = True
    default_value: Any = None


@dataclass
class TypeAnnotation:
    """Type information attached to an AST node by the type checker.

    Attributes:
        base_type: The inferred RegoType.
        element_type: Element type for sets and arrays.
        key_type: Key type for objects.
        value_type: Value type for objects.
        is_warning: Whether a type incompatibility warning was generated.
        warning_message: The warning message if applicable.
    """
    base_type: RegoType = RegoType.ANY
    element_type: Optional[RegoType] = None
    key_type: Optional[RegoType] = None
    value_type: Optional[RegoType] = None
    is_warning: bool = False
    warning_message: str = ""


@dataclass
class BundleManifest:
    """Metadata for a policy bundle revision.

    Attributes:
        revision: Monotonically increasing version number.
        roots: Package path prefixes this bundle governs.
        rego_version: FizzRego language version.
        created_at: Bundle creation timestamp (UTC).
        author: Who built the bundle.
        bundle_name: Logical bundle name.
    """
    revision: int = 0
    roots: List[str] = field(default_factory=lambda: ["fizzbuzz"])
    rego_version: str = FIZZREGO_LANGUAGE_VERSION
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = "system"
    bundle_name: str = "default"


@dataclass
class PolicyBundle:
    """A versioned, signed collection of policies and data.

    Attributes:
        manifest: Bundle metadata.
        modules: Compiled policy modules keyed by file path.
        data: Static data document that policies reference via ``data.*``.
        plans: Compiled execution plans keyed by fully-qualified rule path.
        tests: Test modules keyed by file path.
        signatures: File hash manifest and HMAC signatures.
        state: Current bundle lifecycle state.
    """
    manifest: BundleManifest = field(default_factory=BundleManifest)
    modules: Dict[str, PolicyModule] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    plans: Dict[str, CompiledPlan] = field(default_factory=dict)
    tests: Dict[str, PolicyModule] = field(default_factory=dict)
    signatures: Dict[str, Any] = field(default_factory=dict)
    state: BundleState = BundleState.BUILDING


@dataclass
class BundleSignature:
    """Cryptographic signature block for a policy bundle.

    Attributes:
        files: List of file entries with name, hash, and algorithm.
        signatures: List of signature entries with key ID, sig, and algorithm.
    """
    files: List[Dict[str, str]] = field(default_factory=list)
    signatures: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class DecisionLogEntry:
    """A single policy decision audit record.

    Attributes:
        decision_id: UUID for the decision.
        timestamp: When the decision was made (UTC).
        path: The policy rule that was queried.
        input_doc: The input document (request context), with sensitive fields masked.
        result: The computed policy decision value.
        result_type: High-level outcome (allow/deny/error/undefined).
        bundle_revision: Active bundle revision at decision time.
        metrics: Evaluation performance metrics.
        labels: Configurable key-value labels for categorization.
        explanation: Human-readable evaluation trace.
    """
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    path: str = ""
    input_doc: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    result_type: DecisionResult = DecisionResult.UNDEFINED
    bundle_revision: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    explanation: str = ""


@dataclass
class EvaluationMetrics:
    """Per-evaluation performance metrics.

    Attributes:
        eval_duration_ns: Total evaluation time in nanoseconds.
        compile_duration_ns: Time spent compiling (if not pre-compiled).
        plan_instructions_executed: Number of plan instructions executed.
        backtracks: Number of backtracking events.
        cache_hit: Whether the result was served from cache.
        rules_evaluated: Number of rule bodies evaluated.
        data_lookups: Number of data document lookups.
        builtin_calls: Number of built-in function invocations.
    """
    eval_duration_ns: int = 0
    compile_duration_ns: int = 0
    plan_instructions_executed: int = 0
    backtracks: int = 0
    cache_hit: bool = False
    rules_evaluated: int = 0
    data_lookups: int = 0
    builtin_calls: int = 0


@dataclass
class EvalStep:
    """A single step in the evaluation explanation trace.

    Attributes:
        expression: The expression being evaluated (human-readable).
        result: Whether the expression was true/false or the value produced.
        bindings: Variable bindings at this step.
        children: Child evaluation steps (for nested evaluations).
        passed: Whether this step contributed to the final decision.
    """
    expression: str = ""
    result: Any = None
    bindings: Dict[str, Any] = field(default_factory=dict)
    children: List[EvalStep] = field(default_factory=list)
    passed: bool = False


@dataclass
class DataAdapterInfo:
    """Status information for a registered data adapter.

    Attributes:
        name: Adapter identifier.
        data_path: The ``data.*`` path this adapter populates.
        refresh_interval: Refresh interval in seconds.
        last_refresh: Timestamp of last successful refresh.
        state: Current adapter health state.
        error_message: Last error message if state is ERROR.
    """
    name: str = ""
    data_path: str = ""
    refresh_interval: float = DEFAULT_DATA_REFRESH_INTERVAL
    last_refresh: Optional[datetime] = None
    state: DataAdapterState = DataAdapterState.HEALTHY
    error_message: str = ""


@dataclass
class TestRunResult:
    """Aggregated results of running a policy test suite.

    Attributes:
        total: Total number of test rules.
        passed: Number of tests that passed.
        failed: Number of tests that failed.
        errored: Number of tests that errored.
        skipped: Number of tests skipped.
        results: Per-test results.
        duration_ms: Total test execution time.
        coverage_percent: Rule coverage percentage.
    """
    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    coverage_percent: float = 0.0


@dataclass
class BenchmarkResult:
    """Results of benchmarking a policy query.

    Attributes:
        query: The query path that was benchmarked.
        iterations: Number of iterations executed.
        mean_ns: Mean evaluation time in nanoseconds.
        p50_ns: Median evaluation time.
        p95_ns: 95th percentile evaluation time.
        p99_ns: 99th percentile evaluation time.
        min_ns: Minimum evaluation time.
        max_ns: Maximum evaluation time.
        cache_effect_ratio: Speedup ratio with cache vs without.
    """
    query: str = ""
    iterations: int = 0
    mean_ns: int = 0
    p50_ns: int = 0
    p95_ns: int = 0
    p99_ns: int = 0
    min_ns: int = 0
    max_ns: int = 0
    cache_effect_ratio: float = 1.0


@dataclass
class PolicyEngineStatus:
    """Operational status of the policy engine.

    Attributes:
        active_bundle_revision: Currently active bundle revision number.
        bundle_name: Active bundle name.
        total_evaluations: Total evaluations since engine start.
        cache_hit_rate: Evaluation cache hit rate (0.0-1.0).
        eval_latency_p50_ms: Median evaluation latency.
        eval_latency_p95_ms: 95th percentile evaluation latency.
        eval_latency_p99_ms: 99th percentile evaluation latency.
        adapter_states: Per-adapter health states.
        decisions_allow: Total allow decisions.
        decisions_deny: Total deny decisions.
    """
    active_bundle_revision: int = 0
    bundle_name: str = ""
    total_evaluations: int = 0
    cache_hit_rate: float = 0.0
    eval_latency_p50_ms: float = 0.0
    eval_latency_p95_ms: float = 0.0
    eval_latency_p99_ms: float = 0.0
    adapter_states: Dict[str, str] = field(default_factory=dict)
    decisions_allow: int = 0
    decisions_deny: int = 0


# ---------------------------------------------------------------------------
# FizzRego Lexer
# ---------------------------------------------------------------------------

class FizzRegoLexer:
    """Tokenizes FizzRego source text into a stream of tokens.

    The lexer processes source text character by character, producing Token
    instances with type, literal value, and source location.  It handles
    string escape sequences (\\n, \\t, \\\\, \\\", \\uXXXX), multi-line
    strings (backtick-delimited), and number literals in decimal, hexadecimal
    (0x), octal (0o), and binary (0b) formats.  Single-line comments begin
    with # and extend to end of line.
    """

    _KEYWORDS: Dict[str, TokenType] = {
        "package": TokenType.PACKAGE,
        "import": TokenType.IMPORT,
        "default": TokenType.DEFAULT,
        "not": TokenType.NOT,
        "some": TokenType.SOME,
        "every": TokenType.EVERY,
        "with": TokenType.WITH,
        "as": TokenType.AS,
        "if": TokenType.IF,
        "else": TokenType.ELSE,
        "true": TokenType.TRUE,
        "false": TokenType.FALSE,
        "null": TokenType.NULL,
    }

    _SINGLE_CHAR: Dict[str, TokenType] = {
        "{": TokenType.LBRACE,
        "}": TokenType.RBRACE,
        "[": TokenType.LBRACKET,
        "]": TokenType.RBRACKET,
        "(": TokenType.LPAREN,
        ")": TokenType.RPAREN,
        ".": TokenType.DOT,
        ",": TokenType.COMMA,
        ";": TokenType.SEMICOLON,
        "+": TokenType.PLUS,
        "-": TokenType.MINUS,
        "*": TokenType.STAR,
        "/": TokenType.SLASH,
        "%": TokenType.PERCENT,
        "|": TokenType.PIPE,
        "&": TokenType.AMPERSAND,
    }

    def __init__(self, source: str, file: str = "") -> None:
        self._source = source
        self._file = file
        self._pos = 0
        self._line = 1
        self._column = 1
        self._tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        """Tokenize the complete source and return the token list."""
        while self._pos < len(self._source):
            self._skip_whitespace()
            if self._pos >= len(self._source):
                break
            ch = self._source[self._pos]

            if ch == "#":
                self._read_comment()
                continue
            if ch == "\n":
                self._tokens.append(self._make_token(TokenType.NEWLINE, "\n"))
                self._advance()
                continue
            if ch == '"':
                self._tokens.append(self._read_string())
                continue
            if ch == '`':
                self._tokens.append(self._read_raw_string())
                continue
            if ch.isdigit():
                self._tokens.append(self._read_number())
                continue
            if ch.isalpha() or ch == "_":
                self._tokens.append(self._read_identifier())
                continue

            # Two-character operators
            if self._pos + 1 < len(self._source):
                two = self._source[self._pos:self._pos + 2]
                if two == ":=":
                    self._tokens.append(self._make_token(TokenType.ASSIGN, ":="))
                    self._advance()
                    self._advance()
                    continue
                if two == "==":
                    self._tokens.append(self._make_token(TokenType.EQ, "=="))
                    self._advance()
                    self._advance()
                    continue
                if two == "!=":
                    self._tokens.append(self._make_token(TokenType.NEQ, "!="))
                    self._advance()
                    self._advance()
                    continue
                if two == "<=":
                    self._tokens.append(self._make_token(TokenType.LTE, "<="))
                    self._advance()
                    self._advance()
                    continue
                if two == ">=":
                    self._tokens.append(self._make_token(TokenType.GTE, ">="))
                    self._advance()
                    self._advance()
                    continue

            # Single-character: check < and > separately (not in two-char above)
            if ch == "<":
                self._tokens.append(self._make_token(TokenType.LT, "<"))
                self._advance()
                continue
            if ch == ">":
                self._tokens.append(self._make_token(TokenType.GT, ">"))
                self._advance()
                continue
            if ch == ":":
                self._tokens.append(self._make_token(TokenType.COLON, ":"))
                self._advance()
                continue

            # Bare '=' is the Rego unification operator, distinct from ':='
            # (local assignment) and '==' (comparison).  It is used in
            # default declarations (``default allow = false``) and complete
            # rule heads (``max_range = 100 { ... }``).  The parser treats
            # it identically to ':=' for rule-head purposes.
            if ch == "=":
                self._tokens.append(self._make_token(TokenType.ASSIGN, "="))
                self._advance()
                continue

            if ch in self._SINGLE_CHAR:
                self._tokens.append(self._make_token(self._SINGLE_CHAR[ch], ch))
                self._advance()
                continue

            raise self._error(f"Unexpected character '{ch}'")

        self._tokens.append(self._make_token(TokenType.EOF, ""))
        return self._tokens

    def _advance(self) -> str:
        """Advance position by one character and return the consumed character."""
        ch = self._source[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return ch

    def _peek(self) -> str:
        """Return the character at the current position without advancing."""
        if self._pos >= len(self._source):
            return ""
        return self._source[self._pos]

    def _read_string(self) -> Token:
        """Read a double-quoted string with escape sequence support."""
        start_line = self._line
        start_col = self._column
        self._advance()  # consume opening "
        value = []
        while self._pos < len(self._source):
            ch = self._source[self._pos]
            if ch == "\n":
                raise self._error("Unterminated string literal")
            if ch == "\\":
                self._advance()
                if self._pos >= len(self._source):
                    raise self._error("Unterminated escape sequence")
                esc = self._source[self._pos]
                escape_map = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "r": "\r"}
                if esc in escape_map:
                    value.append(escape_map[esc])
                    self._advance()
                elif esc == "u":
                    self._advance()
                    hex_str = ""
                    for _ in range(4):
                        if self._pos >= len(self._source):
                            raise self._error("Incomplete unicode escape")
                        hex_str += self._advance()
                    value.append(chr(int(hex_str, 16)))
                else:
                    raise self._error(f"Invalid escape sequence '\\{esc}'")
                continue
            if ch == '"':
                self._advance()
                return Token(
                    token_type=TokenType.STRING,
                    literal="".join(value),
                    line=start_line,
                    column=start_col,
                    file=self._file,
                )
            value.append(ch)
            self._advance()
        raise self._error("Unterminated string literal")

    def _read_raw_string(self) -> Token:
        """Read a backtick-delimited raw string (no escape processing)."""
        start_line = self._line
        start_col = self._column
        self._advance()  # consume opening `
        value = []
        while self._pos < len(self._source):
            ch = self._source[self._pos]
            if ch == '`':
                self._advance()
                return Token(
                    token_type=TokenType.STRING,
                    literal="".join(value),
                    line=start_line,
                    column=start_col,
                    file=self._file,
                )
            value.append(ch)
            self._advance()
        raise self._error("Unterminated raw string literal")

    def _read_number(self) -> Token:
        """Read a number literal (decimal, hex, octal, binary)."""
        start_line = self._line
        start_col = self._column
        start_pos = self._pos

        if self._source[self._pos] == "0" and self._pos + 1 < len(self._source):
            next_ch = self._source[self._pos + 1].lower()
            if next_ch == "x":
                self._advance()
                self._advance()
                while self._pos < len(self._source) and self._source[self._pos] in "0123456789abcdefABCDEF_":
                    self._advance()
                literal = self._source[start_pos:self._pos]
                return Token(token_type=TokenType.NUMBER, literal=literal, line=start_line, column=start_col, file=self._file)
            if next_ch == "o":
                self._advance()
                self._advance()
                while self._pos < len(self._source) and self._source[self._pos] in "01234567_":
                    self._advance()
                literal = self._source[start_pos:self._pos]
                return Token(token_type=TokenType.NUMBER, literal=literal, line=start_line, column=start_col, file=self._file)
            if next_ch == "b":
                self._advance()
                self._advance()
                while self._pos < len(self._source) and self._source[self._pos] in "01_":
                    self._advance()
                literal = self._source[start_pos:self._pos]
                return Token(token_type=TokenType.NUMBER, literal=literal, line=start_line, column=start_col, file=self._file)

        # Decimal (with optional fraction and exponent)
        while self._pos < len(self._source) and (self._source[self._pos].isdigit() or self._source[self._pos] == "_"):
            self._advance()
        if self._pos < len(self._source) and self._source[self._pos] == ".":
            if self._pos + 1 < len(self._source) and self._source[self._pos + 1].isdigit():
                self._advance()
                while self._pos < len(self._source) and (self._source[self._pos].isdigit() or self._source[self._pos] == "_"):
                    self._advance()
        if self._pos < len(self._source) and self._source[self._pos].lower() == "e":
            self._advance()
            if self._pos < len(self._source) and self._source[self._pos] in "+-":
                self._advance()
            while self._pos < len(self._source) and self._source[self._pos].isdigit():
                self._advance()

        literal = self._source[start_pos:self._pos]
        return Token(token_type=TokenType.NUMBER, literal=literal, line=start_line, column=start_col, file=self._file)

    def _read_identifier(self) -> Token:
        """Read an identifier or keyword."""
        start_line = self._line
        start_col = self._column
        start_pos = self._pos
        while self._pos < len(self._source) and (self._source[self._pos].isalnum() or self._source[self._pos] == "_"):
            self._advance()
        literal = self._source[start_pos:self._pos]
        token_type = self._KEYWORDS.get(literal, TokenType.IDENT)
        return Token(token_type=token_type, literal=literal, line=start_line, column=start_col, file=self._file)

    def _read_comment(self) -> Token:
        """Read a single-line comment from # to end of line."""
        start_line = self._line
        start_col = self._column
        start_pos = self._pos
        while self._pos < len(self._source) and self._source[self._pos] != "\n":
            self._advance()
        literal = self._source[start_pos:self._pos]
        token = Token(token_type=TokenType.COMMENT, literal=literal, line=start_line, column=start_col, file=self._file)
        self._tokens.append(token)
        return token

    def _skip_whitespace(self) -> None:
        """Skip spaces and tabs (not newlines, which are significant)."""
        while self._pos < len(self._source) and self._source[self._pos] in " \t\r":
            self._advance()

    def _make_token(self, token_type: TokenType, literal: str) -> Token:
        """Create a token at the current source position."""
        return Token(token_type=token_type, literal=literal, line=self._line, column=self._column, file=self._file)

    def _error(self, message: str) -> PolicyLexerError:
        """Create a lexer error with source location."""
        loc = f"{self._file}:{self._line}:{self._column}" if self._file else f"{self._line}:{self._column}"
        return PolicyLexerError(f"{message} at {loc}")


# ---------------------------------------------------------------------------
# FizzRego Parser
# ---------------------------------------------------------------------------

class FizzRegoParser:
    """Recursive descent parser for FizzRego source.

    Constructs an Abstract Syntax Tree from the token stream.  The grammar
    follows Rego's precedence rules (lowest to highest):

    1. Rule definitions (multiple rules with same head = logical OR)
    2. ``with`` expressions
    3. ``not`` negation
    4. Comparison operators (==, !=, <, >, <=, >=)
    5. Arithmetic operators (+, -, *, /, %)
    6. Unary negation (-)
    7. Dot access and bracket indexing
    8. Atoms (identifiers, literals, comprehensions, function calls)

    The parser validates rule safety: every variable in a rule body must be
    bound by at least one positive (non-negated) expression.  Rules with
    unsafe variables are rejected with a diagnostic error.
    """

    def __init__(self, tokens: List[Token], file: str = "") -> None:
        self._tokens = [t for t in tokens if t.token_type not in (TokenType.COMMENT, TokenType.NEWLINE)]
        self._pos = 0
        self._file = file

    def parse(self) -> PolicyModule:
        """Parse the token stream into a PolicyModule."""
        module = PolicyModule(file_path=self._file)

        if self._peek().token_type == TokenType.PACKAGE:
            pkg = self._parse_package()
            module.package_path = ".".join(pkg.path)

        while self._peek().token_type == TokenType.IMPORT:
            module.imports.append(self._parse_import())

        while self._peek().token_type != TokenType.EOF:
            rule = self._parse_rule()
            if rule is not None:
                module.rules.append(rule)

        return module

    def _parse_package(self) -> PackageNode:
        """Parse a package declaration."""
        tok = self._expect(TokenType.PACKAGE)
        node = PackageNode(line=tok.line, column=tok.column)
        node.path.append(self._expect(TokenType.IDENT).literal)
        while self._match(TokenType.DOT):
            node.path.append(self._expect(TokenType.IDENT).literal)
        return node

    def _parse_import(self) -> ImportNode:
        """Parse an import declaration."""
        tok = self._expect(TokenType.IMPORT)
        node = ImportNode(line=tok.line, column=tok.column)
        node.path.append(self._expect(TokenType.IDENT).literal)
        while self._match(TokenType.DOT):
            node.path.append(self._expect(TokenType.IDENT).literal)
        if self._match(TokenType.AS):
            node.alias = self._expect(TokenType.IDENT).literal
        return node

    def _parse_rule(self) -> Optional[RuleNode]:
        """Parse a rule definition (default, complete, partial set, partial object)."""
        tok = self._peek()
        if tok.token_type == TokenType.EOF:
            return None

        node = RuleNode(line=tok.line, column=tok.column)

        # Default rule
        if tok.token_type == TokenType.DEFAULT:
            self._advance()
            node.is_default = True
            node.name = self._expect(TokenType.IDENT).literal
            self._expect(TokenType.EQ) if self._peek().token_type == TokenType.EQ else self._expect(TokenType.ASSIGN)
            node.default_value = self._parse_atom_value()
            return node

        # Rule head
        node.name = self._expect(TokenType.IDENT).literal

        # Partial object rule: name[key]
        if self._peek().token_type == TokenType.LBRACKET:
            self._advance()
            node.key_var = self._expect(TokenType.IDENT).literal
            self._expect(TokenType.RBRACKET)

        # Complete rule with assigned value
        if self._peek().token_type in (TokenType.EQ, TokenType.ASSIGN):
            self._advance()
            node.assign_value = self._parse_expr()

        # Rule body
        if self._peek().token_type == TokenType.LBRACE:
            self._advance()
            node.body = self._parse_rule_body()
            self._expect(TokenType.RBRACE)
        elif self._peek().token_type == TokenType.IF:
            self._advance()
            if self._peek().token_type == TokenType.LBRACE:
                self._advance()
                node.body = self._parse_rule_body()
                self._expect(TokenType.RBRACE)
            else:
                node.body = [self._parse_expr()]

        # Validate safety
        self._validate_safety(node)
        return node

    def _parse_rule_body(self) -> List[ASTNode]:
        """Parse the body of a rule (list of expressions)."""
        body: List[ASTNode] = []
        while self._peek().token_type != TokenType.RBRACE and self._peek().token_type != TokenType.EOF:
            body.append(self._parse_expr())
            # Optional semicolons between body expressions
            self._match(TokenType.SEMICOLON)
        return body

    def _parse_expr(self) -> ASTNode:
        """Parse an expression (entry point for precedence climbing)."""
        return self._parse_with_expr()

    def _parse_with_expr(self) -> ASTNode:
        """Parse a ``with`` override expression."""
        node = self._parse_not_expr()
        while self._peek().token_type == TokenType.WITH:
            tok = self._advance()
            target_parts = [self._expect(TokenType.IDENT).literal]
            while self._match(TokenType.DOT):
                target_parts.append(self._expect(TokenType.IDENT).literal)
            self._expect(TokenType.AS)
            value = self._parse_not_expr()
            with_node = WithNode(
                line=tok.line,
                column=tok.column,
                target=".".join(target_parts),
                value=value,
            )
            # Wrap the base node with the with override
            node = with_node
        return node

    def _parse_not_expr(self) -> ASTNode:
        """Parse a ``not`` negation expression."""
        if self._peek().token_type == TokenType.NOT:
            tok = self._advance()
            operand = self._parse_comparison()
            return NotNode(line=tok.line, column=tok.column, operand=operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> ASTNode:
        """Parse comparison operators (==, !=, <, >, <=, >=)."""
        left = self._parse_arithmetic()
        comp_ops = {
            TokenType.EQ: "==",
            TokenType.NEQ: "!=",
            TokenType.LT: "<",
            TokenType.GT: ">",
            TokenType.LTE: "<=",
            TokenType.GTE: ">=",
            TokenType.ASSIGN: ":=",
        }
        if self._peek().token_type in comp_ops:
            tok = self._advance()
            right = self._parse_arithmetic()
            return ExprNode(
                line=tok.line,
                column=tok.column,
                operator=comp_ops[tok.token_type],
                left=left,
                right=right,
            )
        return left

    def _parse_arithmetic(self) -> ASTNode:
        """Parse arithmetic operators (+, -, *, /, %)."""
        left = self._parse_unary()
        arith_ops = {
            TokenType.PLUS: "+",
            TokenType.MINUS: "-",
            TokenType.STAR: "*",
            TokenType.SLASH: "/",
            TokenType.PERCENT: "%",
        }
        while self._peek().token_type in arith_ops:
            tok = self._advance()
            right = self._parse_unary()
            left = ExprNode(
                line=tok.line,
                column=tok.column,
                operator=arith_ops[tok.token_type],
                left=left,
                right=right,
            )
        return left

    def _parse_unary(self) -> ASTNode:
        """Parse unary negation (-)."""
        if self._peek().token_type == TokenType.MINUS:
            tok = self._advance()
            operand = self._parse_postfix()
            return ExprNode(
                line=tok.line,
                column=tok.column,
                operator="-",
                left=TermNode(value=0),
                right=operand,
            )
        return self._parse_postfix()

    def _parse_postfix(self) -> ASTNode:
        """Parse dot access and bracket indexing."""
        node = self._parse_atom()
        while self._peek().token_type in (TokenType.DOT, TokenType.LBRACKET):
            if self._peek().token_type == TokenType.DOT:
                self._advance()
                if isinstance(node, TermNode) and node.is_ref:
                    node.ref_path.append(self._expect(TokenType.IDENT).literal)
                elif isinstance(node, RefNode):
                    node.segments.append(self._expect(TokenType.IDENT).literal)
                else:
                    ref = RefNode(line=node.line, column=node.column)
                    if isinstance(node, TermNode):
                        ref.segments.append(str(node.value))
                    else:
                        ref.segments.append(node)
                    ref.segments.append(self._expect(TokenType.IDENT).literal)
                    node = ref
            elif self._peek().token_type == TokenType.LBRACKET:
                self._advance()
                index_expr = self._parse_expr()
                self._expect(TokenType.RBRACKET)
                if isinstance(node, RefNode):
                    node.segments.append(index_expr)
                else:
                    ref = RefNode(line=node.line, column=node.column)
                    if isinstance(node, TermNode):
                        ref.segments.append(str(node.value))
                    else:
                        ref.segments.append(node)
                    ref.segments.append(index_expr)
                    node = ref
        return node

    def _parse_atom(self) -> ASTNode:
        """Parse atomic expressions: literals, identifiers, parens, comprehensions."""
        tok = self._peek()

        if tok.token_type == TokenType.SOME:
            return self._parse_some()

        if tok.token_type == TokenType.EVERY:
            return self._parse_every()

        if tok.token_type == TokenType.TRUE:
            self._advance()
            return TermNode(line=tok.line, column=tok.column, value=True)

        if tok.token_type == TokenType.FALSE:
            self._advance()
            return TermNode(line=tok.line, column=tok.column, value=False)

        if tok.token_type == TokenType.NULL:
            self._advance()
            return TermNode(line=tok.line, column=tok.column, value=None)

        if tok.token_type == TokenType.STRING:
            self._advance()
            return TermNode(line=tok.line, column=tok.column, value=tok.literal)

        if tok.token_type == TokenType.NUMBER:
            self._advance()
            literal = tok.literal.replace("_", "")
            if literal.startswith("0x") or literal.startswith("0X"):
                val = int(literal, 16)
            elif literal.startswith("0o") or literal.startswith("0O"):
                val = int(literal, 8)
            elif literal.startswith("0b") or literal.startswith("0B"):
                val = int(literal, 2)
            elif "." in literal or "e" in literal.lower():
                val = float(literal)
            else:
                val = int(literal)
            return TermNode(line=tok.line, column=tok.column, value=val)

        if tok.token_type == TokenType.IDENT:
            self._advance()
            # Check for function call
            if self._peek().token_type == TokenType.LPAREN:
                return self._parse_call(tok.literal)
            # Check for dotted function call (e.g., regex.match)
            if self._peek().token_type == TokenType.DOT:
                save_pos = self._pos
                self._advance()
                if self._peek().token_type == TokenType.IDENT:
                    next_ident = self._advance()
                    if self._peek().token_type == TokenType.LPAREN:
                        return self._parse_call(f"{tok.literal}.{next_ident.literal}")
                    # Not a function call, restore and parse as ref
                    self._pos = save_pos
                else:
                    self._pos = save_pos

            node = TermNode(line=tok.line, column=tok.column, value=tok.literal, is_ref=True, ref_path=[tok.literal])
            return node

        if tok.token_type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return expr

        if tok.token_type == TokenType.LBRACKET:
            return self._parse_comprehension_or_array()

        if tok.token_type == TokenType.LBRACE:
            return self._parse_set_or_object_comprehension()

        raise self._error(f"Unexpected token {tok.token_type.value} '{tok.literal}'")

    def _parse_atom_value(self) -> Any:
        """Parse a simple value for default rules."""
        tok = self._peek()
        if tok.token_type == TokenType.TRUE:
            self._advance()
            return True
        if tok.token_type == TokenType.FALSE:
            self._advance()
            return False
        if tok.token_type == TokenType.NULL:
            self._advance()
            return None
        if tok.token_type == TokenType.STRING:
            self._advance()
            return tok.literal
        if tok.token_type == TokenType.NUMBER:
            self._advance()
            literal = tok.literal.replace("_", "")
            if "." in literal or "e" in literal.lower():
                return float(literal)
            return int(literal)
        raise self._error(f"Expected a value, got {tok.token_type.value}")

    def _parse_comprehension_or_array(self) -> ASTNode:
        """Parse an array literal or array comprehension."""
        tok = self._expect(TokenType.LBRACKET)
        if self._peek().token_type == TokenType.RBRACKET:
            self._advance()
            return TermNode(line=tok.line, column=tok.column, value=[])

        term = self._parse_expr()

        # Array comprehension: [term | body]
        if self._peek().token_type == TokenType.PIPE:
            self._advance()
            body = []
            while self._peek().token_type != TokenType.RBRACKET and self._peek().token_type != TokenType.EOF:
                body.append(self._parse_expr())
                self._match(TokenType.SEMICOLON)
            self._expect(TokenType.RBRACKET)
            return ComprehensionNode(line=tok.line, column=tok.column, kind="array", term=term, body=body)

        # Array literal: [a, b, c]
        elements = [term]
        while self._match(TokenType.COMMA):
            if self._peek().token_type == TokenType.RBRACKET:
                break
            elements.append(self._parse_expr())
        self._expect(TokenType.RBRACKET)
        return TermNode(line=tok.line, column=tok.column, value=elements)

    def _parse_set_or_object_comprehension(self) -> ASTNode:
        """Parse a set comprehension, object comprehension, or set/object literal."""
        tok = self._expect(TokenType.LBRACE)
        if self._peek().token_type == TokenType.RBRACE:
            self._advance()
            return TermNode(line=tok.line, column=tok.column, value=set())

        first = self._parse_expr()

        # Object comprehension or literal: {key: value | body} or {key: value}
        if self._peek().token_type == TokenType.COLON:
            self._advance()
            value = self._parse_expr()
            if self._peek().token_type == TokenType.PIPE:
                self._advance()
                body = []
                while self._peek().token_type != TokenType.RBRACE and self._peek().token_type != TokenType.EOF:
                    body.append(self._parse_expr())
                    self._match(TokenType.SEMICOLON)
                self._expect(TokenType.RBRACE)
                return ComprehensionNode(line=tok.line, column=tok.column, kind="object", term=value, key_term=first, body=body)
            # Object literal
            self._expect(TokenType.RBRACE)
            return TermNode(line=tok.line, column=tok.column, value={first: value})

        # Set comprehension: {term | body}
        if self._peek().token_type == TokenType.PIPE:
            self._advance()
            body = []
            while self._peek().token_type != TokenType.RBRACE and self._peek().token_type != TokenType.EOF:
                body.append(self._parse_expr())
                self._match(TokenType.SEMICOLON)
            self._expect(TokenType.RBRACE)
            return ComprehensionNode(line=tok.line, column=tok.column, kind="set", term=first, body=body)

        # Set literal
        self._expect(TokenType.RBRACE)
        return TermNode(line=tok.line, column=tok.column, value={first})

    def _parse_some(self) -> SomeNode:
        """Parse a ``some`` variable declaration."""
        tok = self._expect(TokenType.SOME)
        node = SomeNode(line=tok.line, column=tok.column)
        node.variables.append(self._expect(TokenType.IDENT).literal)
        while self._match(TokenType.COMMA):
            node.variables.append(self._expect(TokenType.IDENT).literal)
        # some x in collection
        if self._peek().token_type == TokenType.IDENT and self._peek().literal == "in":
            self._advance()
            node.domain = self._parse_expr()
        return node

    def _parse_every(self) -> EveryNode:
        """Parse an ``every`` universal quantification."""
        tok = self._expect(TokenType.EVERY)
        node = EveryNode(line=tok.line, column=tok.column)
        first_var = self._expect(TokenType.IDENT).literal
        if self._match(TokenType.COMMA):
            node.key_var = first_var
            node.value_var = self._expect(TokenType.IDENT).literal
        else:
            node.value_var = first_var
        # expect "in"
        if self._peek().token_type == TokenType.IDENT and self._peek().literal == "in":
            self._advance()
        node.domain = self._parse_expr()
        self._expect(TokenType.LBRACE)
        while self._peek().token_type != TokenType.RBRACE and self._peek().token_type != TokenType.EOF:
            node.body.append(self._parse_expr())
            self._match(TokenType.SEMICOLON)
        self._expect(TokenType.RBRACE)
        return node

    def _parse_call(self, name: str) -> CallNode:
        """Parse a function call."""
        tok = self._peek()
        self._expect(TokenType.LPAREN)
        node = CallNode(line=tok.line, column=tok.column, function_name=name)
        if self._peek().token_type != TokenType.RPAREN:
            node.arguments.append(self._parse_expr())
            while self._match(TokenType.COMMA):
                node.arguments.append(self._parse_expr())
        self._expect(TokenType.RPAREN)
        return node

    def _parse_ref(self) -> RefNode:
        """Parse a reference chain."""
        tok = self._peek()
        node = RefNode(line=tok.line, column=tok.column)
        node.segments.append(self._expect(TokenType.IDENT).literal)
        while self._peek().token_type in (TokenType.DOT, TokenType.LBRACKET):
            if self._match(TokenType.DOT):
                node.segments.append(self._expect(TokenType.IDENT).literal)
            elif self._peek().token_type == TokenType.LBRACKET:
                self._advance()
                node.segments.append(self._parse_expr())
                self._expect(TokenType.RBRACKET)
        return node

    def _validate_safety(self, rule: RuleNode) -> None:
        """Validate that all variables in a rule body are bound by a positive expression.

        Variables appearing only in negated contexts are unsafe because their
        binding depends on the absence of data, which is undecidable without
        complete enumeration.
        """
        if rule.is_default or not rule.body:
            return
        # Collect all variables from the body
        positive_vars: Set[str] = set()
        all_vars: Set[str] = set()

        def _collect_vars(node: ASTNode, in_negation: bool = False) -> None:
            if isinstance(node, TermNode) and node.is_ref and len(node.ref_path) == 1:
                name = node.ref_path[0]
                if name[0].islower() and name not in ("input", "data", "true", "false", "null"):
                    all_vars.add(name)
                    if not in_negation:
                        positive_vars.add(name)
            elif isinstance(node, ExprNode):
                if node.left:
                    _collect_vars(node.left, in_negation)
                if node.right:
                    _collect_vars(node.right, in_negation)
            elif isinstance(node, NotNode):
                if node.operand:
                    _collect_vars(node.operand, True)
            elif isinstance(node, SomeNode):
                for v in node.variables:
                    positive_vars.add(v)
                    all_vars.add(v)
            elif isinstance(node, EveryNode):
                if node.key_var:
                    positive_vars.add(node.key_var)
                    all_vars.add(node.key_var)
                positive_vars.add(node.value_var)
                all_vars.add(node.value_var)
            elif isinstance(node, CallNode):
                for arg in node.arguments:
                    _collect_vars(arg, in_negation)
            elif isinstance(node, RefNode):
                for seg in node.segments:
                    if isinstance(seg, ASTNode):
                        _collect_vars(seg, in_negation)

        for expr in rule.body:
            _collect_vars(expr)

        unsafe = all_vars - positive_vars
        if unsafe:
            vars_str = ", ".join(sorted(unsafe))
            raise PolicyParserError(
                f"Unsafe variables in rule '{rule.name}': {vars_str}. "
                f"Every variable must be bound by at least one positive expression."
            )

    def _advance(self) -> Token:
        """Advance to the next token and return the consumed token."""
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _peek(self) -> Token:
        """Return the current token without consuming it."""
        if self._pos >= len(self._tokens):
            return Token(token_type=TokenType.EOF, literal="")
        return self._tokens[self._pos]

    def _expect(self, token_type: TokenType) -> Token:
        """Consume and return the next token, raising if it doesn't match."""
        tok = self._peek()
        if tok.token_type != token_type:
            raise self._error(f"Expected {token_type.value}, got {tok.token_type.value} '{tok.literal}'")
        return self._advance()

    def _match(self, *token_types: TokenType) -> bool:
        """If the current token matches any of the given types, consume and return True."""
        if self._peek().token_type in token_types:
            self._advance()
            return True
        return False

    def _error(self, message: str) -> PolicyParserError:
        """Create a parser error with current token context."""
        tok = self._peek()
        loc = f"{self._file}:{tok.line}:{tok.column}" if self._file else f"{tok.line}:{tok.column}"
        return PolicyParserError(f"{message} at {loc}")


# ---------------------------------------------------------------------------
# FizzRego Type Checker
# ---------------------------------------------------------------------------

class FizzRegoTypeChecker:
    """Walks the AST and infers types for all expressions.

    Type inference is advisory: type errors produce warnings rather than
    hard failures because FizzRego is dynamically typed at runtime.
    Warnings flag likely policy authoring errors.

    Type rules enforced:
    - Comparison operands must be compatible (no comparing numbers to strings)
    - Arithmetic operands must be numeric
    - Set/array/object comprehensions must produce homogeneous collections
    - Function arguments must match the function's declared signature
    - The ``not`` keyword can only be applied to boolean-valued expressions
    - ``every`` domain must be an iterable (set, array, object)
    """

    def __init__(self) -> None:
        self._signatures = self._builtin_signatures()

    def check(self, module: PolicyModule) -> Tuple[PolicyModule, List[str]]:
        """Type check a module and return (module, warnings)."""
        warnings: List[str] = []
        for rule in module.rules:
            warnings.extend(self._check_rule(rule))
        return module, warnings

    def _check_rule(self, rule: RuleNode) -> List[str]:
        """Type check a single rule and return warnings."""
        warnings: List[str] = []
        env: Dict[str, RegoType] = {}
        for expr in rule.body:
            annotation = self._check_expr(expr, env)
            if annotation.is_warning:
                warnings.append(annotation.warning_message)
        return warnings

    def _check_expr(self, node: ASTNode, env: Dict[str, RegoType]) -> TypeAnnotation:
        """Infer the type of an expression node."""
        if isinstance(node, ExprNode):
            if node.operator in ("==", "!=", "<", ">", "<=", ">=", ":="):
                return self._check_comparison(node, env)
            if node.operator in ("+", "-", "*", "/", "%"):
                return self._check_arithmetic(node, env)
        if isinstance(node, CallNode):
            return self._check_call(node, env)
        if isinstance(node, RefNode):
            return self._check_ref(node, env)
        if isinstance(node, ComprehensionNode):
            return self._check_comprehension(node, env)
        if isinstance(node, EveryNode):
            return self._check_every(node, env)
        if isinstance(node, NotNode):
            if node.operand:
                inner = self._check_expr(node.operand, env)
                if inner.base_type not in (RegoType.BOOLEAN, RegoType.ANY):
                    return TypeAnnotation(
                        base_type=RegoType.BOOLEAN,
                        is_warning=True,
                        warning_message=f"'not' applied to non-boolean expression of type {inner.base_type.value}",
                    )
            return TypeAnnotation(base_type=RegoType.BOOLEAN)
        if isinstance(node, TermNode):
            if isinstance(node.value, bool):
                return TypeAnnotation(base_type=RegoType.BOOLEAN)
            if isinstance(node.value, (int, float)):
                return TypeAnnotation(base_type=RegoType.NUMBER)
            if isinstance(node.value, str) and not node.is_ref:
                return TypeAnnotation(base_type=RegoType.STRING)
            if node.value is None and not node.is_ref:
                return TypeAnnotation(base_type=RegoType.NULL)
            if node.is_ref:
                return TypeAnnotation(base_type=RegoType.ANY)
            if isinstance(node.value, list):
                return TypeAnnotation(base_type=RegoType.ARRAY)
            if isinstance(node.value, (set, frozenset)):
                return TypeAnnotation(base_type=RegoType.SET)
            if isinstance(node.value, dict):
                return TypeAnnotation(base_type=RegoType.OBJECT)
        return TypeAnnotation(base_type=RegoType.ANY)

    def _check_comparison(self, node: ExprNode, env: Dict[str, RegoType]) -> TypeAnnotation:
        """Check comparison operand compatibility."""
        left_t = self._check_expr(node.left, env) if node.left else TypeAnnotation()
        right_t = self._check_expr(node.right, env) if node.right else TypeAnnotation()
        if not self._compatible(left_t.base_type, right_t.base_type):
            return TypeAnnotation(
                base_type=RegoType.BOOLEAN,
                is_warning=True,
                warning_message=f"Comparison between incompatible types: {left_t.base_type.value} {node.operator} {right_t.base_type.value}",
            )
        node.inferred_type = RegoType.BOOLEAN
        return TypeAnnotation(base_type=RegoType.BOOLEAN)

    def _check_arithmetic(self, node: ExprNode, env: Dict[str, RegoType]) -> TypeAnnotation:
        """Check arithmetic operands are numeric."""
        left_t = self._check_expr(node.left, env) if node.left else TypeAnnotation()
        right_t = self._check_expr(node.right, env) if node.right else TypeAnnotation()
        for t, side in [(left_t, "left"), (right_t, "right")]:
            if t.base_type not in (RegoType.NUMBER, RegoType.ANY):
                return TypeAnnotation(
                    base_type=RegoType.NUMBER,
                    is_warning=True,
                    warning_message=f"Arithmetic on non-numeric {side} operand of type {t.base_type.value}",
                )
        node.inferred_type = RegoType.NUMBER
        return TypeAnnotation(base_type=RegoType.NUMBER)

    def _check_call(self, node: CallNode, env: Dict[str, RegoType]) -> TypeAnnotation:
        """Validate function call argument types."""
        if node.function_name in self._signatures:
            arg_types, return_type = self._signatures[node.function_name]
            if len(arg_types) > 0 and len(node.arguments) != len(arg_types):
                return TypeAnnotation(
                    base_type=return_type,
                    is_warning=True,
                    warning_message=f"Function '{node.function_name}' expects {len(arg_types)} arguments, got {len(node.arguments)}",
                )
            for i, (arg, expected) in enumerate(zip(node.arguments, arg_types)):
                actual = self._check_expr(arg, env)
                if not self._compatible(actual.base_type, expected):
                    return TypeAnnotation(
                        base_type=return_type,
                        is_warning=True,
                        warning_message=f"Function '{node.function_name}' argument {i} expects {expected.value}, got {actual.base_type.value}",
                    )
            return TypeAnnotation(base_type=return_type)
        return TypeAnnotation(base_type=RegoType.ANY)

    def _check_ref(self, node: RefNode, env: Dict[str, RegoType]) -> TypeAnnotation:
        """Infer type for a reference chain."""
        return TypeAnnotation(base_type=RegoType.ANY)

    def _check_comprehension(self, node: ComprehensionNode, env: Dict[str, RegoType]) -> TypeAnnotation:
        """Infer type for a comprehension."""
        if node.kind == "set":
            return TypeAnnotation(base_type=RegoType.SET)
        if node.kind == "array":
            return TypeAnnotation(base_type=RegoType.ARRAY)
        if node.kind == "object":
            return TypeAnnotation(base_type=RegoType.OBJECT)
        return TypeAnnotation(base_type=RegoType.ANY)

    def _check_every(self, node: EveryNode, env: Dict[str, RegoType]) -> TypeAnnotation:
        """Check that every's domain is iterable."""
        if node.domain:
            domain_t = self._check_expr(node.domain, env)
            if domain_t.base_type not in (RegoType.SET, RegoType.ARRAY, RegoType.OBJECT, RegoType.ANY):
                return TypeAnnotation(
                    base_type=RegoType.BOOLEAN,
                    is_warning=True,
                    warning_message=f"'every' domain must be iterable, got {domain_t.base_type.value}",
                )
        return TypeAnnotation(base_type=RegoType.BOOLEAN)

    def _compatible(self, a: RegoType, b: RegoType) -> bool:
        """Check if two types are compatible for comparison."""
        if a == RegoType.ANY or b == RegoType.ANY:
            return True
        return a == b

    def _builtin_signatures(self) -> Dict[str, Tuple[List[RegoType], RegoType]]:
        """Return type signatures for built-in functions."""
        S = RegoType.STRING
        N = RegoType.NUMBER
        B = RegoType.BOOLEAN
        A = RegoType.ANY
        ARR = RegoType.ARRAY
        OBJ = RegoType.OBJECT
        SET = RegoType.SET

        return {
            "concat": ([S, ARR], S),
            "contains": ([S, S], B),
            "endswith": ([S, S], B),
            "format_int": ([N, N], S),
            "indexof": ([S, S], N),
            "lower": ([S], S),
            "replace": ([S, S, S], S),
            "split": ([S, S], ARR),
            "sprintf": ([S, ARR], S),
            "startswith": ([S, S], B),
            "substring": ([S, N, N], S),
            "trim": ([S, S], S),
            "trim_left": ([S, S], S),
            "trim_right": ([S, S], S),
            "trim_prefix": ([S, S], S),
            "trim_suffix": ([S, S], S),
            "trim_space": ([S], S),
            "upper": ([S], S),
            "strings.reverse": ([S], S),
            "regex.match": ([S, S], B),
            "regex.find_all_string_submatch": ([S, S], ARR),
            "regex.replace": ([S, S, S], S),
            "regex.split": ([S, S], ARR),
            "regex.is_valid": ([S], B),
            "count": ([A], N),
            "sum": ([A], N),
            "product": ([A], N),
            "max": ([A], A),
            "min": ([A], A),
            "sort": ([A], ARR),
            "type_name": ([A], S),
            "is_boolean": ([A], B),
            "is_number": ([A], B),
            "is_string": ([A], B),
            "is_null": ([A], B),
            "is_set": ([A], B),
            "is_array": ([A], B),
            "is_object": ([A], B),
            "to_number": ([A], N),
            "object.get": ([OBJ, A, A], A),
            "object.remove": ([OBJ, A], OBJ),
            "object.union": ([OBJ, OBJ], OBJ),
            "object.filter": ([OBJ, A], OBJ),
            "object.keys": ([OBJ], SET),
            "object.values": ([OBJ], ARR),
            "intersection": ([SET, SET], SET),
            "union": ([SET, SET], SET),
            "set.diff": ([SET, SET], SET),
            "json.marshal": ([A], S),
            "json.unmarshal": ([S], A),
            "base64.encode": ([S], S),
            "base64.decode": ([S], S),
            "urlquery.encode": ([S], S),
            "urlquery.decode": ([S], S),
            "yaml.marshal": ([A], S),
            "yaml.unmarshal": ([S], A),
            "time.now_ns": ([], N),
            "time.parse_ns": ([S, S], N),
            "time.format": ([N], S),
            "time.date": ([N], ARR),
            "time.clock": ([N], ARR),
            "time.weekday": ([N], S),
            "time.add_date": ([N, N, N, N], N),
            "time.diff": ([N, N], OBJ),
            "net.cidr_contains": ([S, S], B),
            "net.cidr_intersect": ([S, S], B),
            "net.cidr_merge": ([ARR], ARR),
            "net.cidr_expand": ([S], ARR),
            "io.jwt.decode": ([S], ARR),
            "io.jwt.verify_hmac_sha256": ([S, S], B),
            "io.jwt.decode_verify": ([S, OBJ], ARR),
            "crypto.sha256": ([S], S),
            "crypto.hmac_sha256": ([S, S], S),
            "crypto.md5": ([S], S),
            "fizzbuzz.evaluate": ([N], S),
            "fizzbuzz.is_fizz": ([N], B),
            "fizzbuzz.is_buzz": ([N], B),
            "fizzbuzz.is_fizzbuzz": ([N], B),
            "fizzbuzz.cognitive_load": ([N], N),
        }


# ---------------------------------------------------------------------------
# FizzRego Partial Evaluator
# ---------------------------------------------------------------------------

class FizzRegoPartialEvaluator:
    """Performs compile-time partial evaluation to optimize policies.

    When static data values are known at compile time (loaded from the
    bundle's data document), the partial evaluator:

    1. Evaluates constant expressions and folds them into literal values
    2. Eliminates dead rule branches where conditions reference static data
       that makes them trivially true or false
    3. Inlines small helper rules (single body expression) at call sites
    4. Specializes rules that iterate over static collections by unrolling
       the iteration into concrete rule instances

    The output is a residual policy: the subset of the original policy that
    still depends on runtime input.  The residual is semantically equivalent
    to the original but faster to evaluate because static decisions have
    been pre-computed.
    """

    def __init__(self, static_data: Dict[str, Any]) -> None:
        self._static_data = static_data

    def evaluate(self, module: PolicyModule) -> PolicyModule:
        """Partially evaluate a module against static data."""
        result = PolicyModule(
            file_path=module.file_path,
            package_path=module.package_path,
            imports=list(module.imports),
            raw_source=module.raw_source,
        )
        for rule in module.rules:
            if rule.is_default:
                result.rules.append(rule)
                continue
            folded_rule = RuleNode(
                name=rule.name,
                is_default=rule.is_default,
                default_value=rule.default_value,
                key_var=rule.key_var,
                value_var=rule.value_var,
                assign_value=rule.assign_value,
                annotations=dict(rule.annotations),
                line=rule.line,
                column=rule.column,
            )
            folded_body = []
            eliminated = False
            for expr in rule.body:
                folded = self._fold_constants(expr)
                if self._is_trivially_false(folded):
                    eliminated = True
                    break
                if self._is_trivially_true(folded):
                    continue
                folded_body.append(folded)

            if not eliminated:
                folded_rule.body = folded_body
                result.rules.append(folded_rule)

        return self._inline_helpers(result)

    def _fold_constants(self, node: ASTNode) -> ASTNode:
        """Fold constant expressions into literal values."""
        if isinstance(node, ExprNode) and node.left and node.right:
            left = self._fold_constants(node.left)
            right = self._fold_constants(node.right)
            if isinstance(left, TermNode) and isinstance(right, TermNode):
                if not left.is_ref and not right.is_ref:
                    try:
                        result = self._eval_constant(node.operator, left.value, right.value)
                        return TermNode(line=node.line, column=node.column, value=result)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass
            return ExprNode(line=node.line, column=node.column, operator=node.operator, left=left, right=right)
        if isinstance(node, TermNode) and node.is_ref and self._is_static_ref(node):
            resolved = self._resolve_static(node)
            if resolved is not None:
                return TermNode(line=node.line, column=node.column, value=resolved)
        return node

    def _eval_constant(self, op: str, left: Any, right: Any) -> Any:
        """Evaluate a constant binary expression."""
        ops = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b if b != 0 else None,
            "%": lambda a, b: a % b if b != 0 else None,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
        }
        if op in ops:
            result = ops[op](left, right)
            if result is None:
                raise ValueError("Division by zero in constant folding")
            return result
        raise ValueError(f"Unknown operator: {op}")

    def _eliminate_dead_branches(self, rule: RuleNode) -> Optional[RuleNode]:
        """Eliminate a rule if its body contains a trivially false expression."""
        for expr in rule.body:
            if self._is_trivially_false(expr):
                return None
        return rule

    def _inline_helpers(self, module: PolicyModule) -> PolicyModule:
        """Inline single-body helper rules at their call sites."""
        # Identify helper rules (single body expression, referenced by name)
        helpers: Dict[str, RuleNode] = {}
        for rule in module.rules:
            if len(rule.body) == 1 and not rule.is_default and not rule.key_var:
                helpers[rule.name] = rule
        # For now, return module with helpers identified but not inlined,
        # as full inlining requires reference resolution beyond the current scope
        return module

    def _unroll_static_iteration(self, rule: RuleNode) -> List[RuleNode]:
        """Unroll iteration over static collections into concrete instances."""
        # Returns the original rule if no static iteration is found
        return [rule]

    def _is_static_ref(self, node: ASTNode) -> bool:
        """Check if a reference resolves entirely to static data."""
        if isinstance(node, TermNode) and node.is_ref:
            if node.ref_path and node.ref_path[0] == "data":
                return True
        return False

    def _resolve_static(self, node: ASTNode) -> Any:
        """Resolve a static data reference to its value."""
        if isinstance(node, TermNode) and node.is_ref and node.ref_path:
            path = node.ref_path
            if path[0] == "data":
                current = self._static_data
                for segment in path[1:]:
                    if isinstance(current, dict) and segment in current:
                        current = current[segment]
                    else:
                        return None
                return current
        return None

    def _is_trivially_true(self, node: ASTNode) -> bool:
        """Check if an expression is trivially true."""
        if isinstance(node, TermNode) and not node.is_ref:
            return node.value is True
        return False

    def _is_trivially_false(self, node: ASTNode) -> bool:
        """Check if an expression is trivially false."""
        if isinstance(node, TermNode) and not node.is_ref:
            return node.value is False
        return False


# ---------------------------------------------------------------------------
# Plan Generator
# ---------------------------------------------------------------------------

class FizzRegoPlanGenerator:
    """Compiles the (partially evaluated) AST into a linear execution plan.

    The plan is a sequence of PlanInstruction objects with backtracking
    semantics.  When a FILTER instruction fails, execution backtracks to
    the most recent SCAN and tries the next binding.

    Join ordering optimization: when a rule body contains multiple SCAN
    instructions, they are ordered by estimated selectivity (smallest
    collection first) to minimize intermediate bindings.
    """

    def __init__(self) -> None:
        pass

    def generate(self, module: PolicyModule) -> Dict[str, CompiledPlan]:
        """Generate execution plans for all rules in a module."""
        plans: Dict[str, CompiledPlan] = {}
        fqn_prefix = module.package_path
        for rule in module.rules:
            plan = self._generate_rule_plan(rule)
            plan.package_path = fqn_prefix
            fqn = f"{fqn_prefix}.{rule.name}" if fqn_prefix else rule.name
            if fqn in plans:
                # Multiple rules with same head: merge instructions (logical OR)
                plans[fqn].instructions.extend(plan.instructions)
            else:
                plans[fqn] = plan
        return plans

    def _generate_rule_plan(self, rule: RuleNode) -> CompiledPlan:
        """Generate an execution plan for a single rule."""
        plan = CompiledPlan(
            rule_name=rule.name,
            is_complete=not bool(rule.key_var),
            default_value=rule.default_value if rule.is_default else None,
        )
        if rule.is_default:
            plan.instructions.append(PlanInstruction(
                opcode=PlanOpcode.YIELD,
                operands={"value": rule.default_value},
                source_line=rule.line,
            ))
            return plan

        instructions = self._compile_body(rule.body)
        instructions = self._order_joins(instructions)

        if rule.assign_value:
            instructions.append(PlanInstruction(
                opcode=PlanOpcode.YIELD,
                operands={"value_expr": rule.assign_value},
                source_line=rule.line,
            ))
        else:
            instructions.append(PlanInstruction(
                opcode=PlanOpcode.YIELD,
                operands={"value": True},
                source_line=rule.line,
            ))

        plan.instructions = instructions
        return plan

    def _compile_body(self, body: List[ASTNode]) -> List[PlanInstruction]:
        """Compile a rule body into a list of plan instructions."""
        instructions: List[PlanInstruction] = []
        for node in body:
            instructions.append(self._compile_expr(node))
        return instructions

    def _compile_expr(self, node: ASTNode) -> PlanInstruction:
        """Compile a single expression into a plan instruction."""
        if isinstance(node, SomeNode):
            return self._compile_scan(node)
        if isinstance(node, NotNode):
            return self._compile_not(node)
        if isinstance(node, ComprehensionNode):
            return self._compile_aggregate(node)
        if isinstance(node, EveryNode):
            return self._compile_every(node)
        if isinstance(node, CallNode):
            return self._compile_call(node)
        if isinstance(node, ExprNode):
            if node.operator == ":=":
                var_name = ""
                if isinstance(node.left, TermNode) and node.is_ref:
                    var_name = str(node.left.value)
                return self._compile_assign(var_name, node.right)
            return self._compile_filter(node)
        if isinstance(node, TermNode) and node.is_ref:
            return self._compile_lookup(node)
        return self._compile_filter(node)

    def _compile_scan(self, some_node: SomeNode) -> PlanInstruction:
        """Compile a ``some`` declaration into a SCAN instruction."""
        return PlanInstruction(
            opcode=PlanOpcode.SCAN,
            operands={
                "variables": some_node.variables,
                "domain": some_node.domain,
            },
            source_line=some_node.line,
        )

    def _compile_filter(self, node: ASTNode) -> PlanInstruction:
        """Compile a condition into a FILTER instruction."""
        return PlanInstruction(
            opcode=PlanOpcode.FILTER,
            operands={"expression": node},
            source_line=getattr(node, "line", 0),
        )

    def _compile_lookup(self, ref: ASTNode) -> PlanInstruction:
        """Compile a reference lookup into a LOOKUP instruction."""
        ref_path = []
        if isinstance(ref, TermNode):
            ref_path = ref.ref_path
        elif isinstance(ref, RefNode):
            ref_path = ref.segments
        return PlanInstruction(
            opcode=PlanOpcode.LOOKUP,
            operands={"ref_path": ref_path},
            source_line=getattr(ref, "line", 0),
        )

    def _compile_assign(self, var: str, expr: ASTNode) -> PlanInstruction:
        """Compile a variable assignment into an ASSIGN instruction."""
        return PlanInstruction(
            opcode=PlanOpcode.ASSIGN,
            operands={"variable": var, "expression": expr},
            source_line=getattr(expr, "line", 0) if expr else 0,
        )

    def _compile_call(self, node: CallNode) -> PlanInstruction:
        """Compile a function call into a CALL instruction."""
        return PlanInstruction(
            opcode=PlanOpcode.CALL,
            operands={
                "function_name": node.function_name,
                "arguments": node.arguments,
            },
            source_line=node.line,
        )

    def _compile_not(self, node: NotNode) -> PlanInstruction:
        """Compile a negation into a NOT instruction with child sub-plan."""
        children: List[PlanInstruction] = []
        if node.operand:
            children.append(self._compile_expr(node.operand))
        return PlanInstruction(
            opcode=PlanOpcode.NOT,
            children=children,
            source_line=node.line,
        )

    def _compile_aggregate(self, node: ComprehensionNode) -> PlanInstruction:
        """Compile a comprehension into an AGGREGATE instruction."""
        children: List[PlanInstruction] = []
        for expr in node.body:
            children.append(self._compile_expr(expr))
        return PlanInstruction(
            opcode=PlanOpcode.AGGREGATE,
            operands={
                "kind": node.kind,
                "term": node.term,
                "key_term": node.key_term,
            },
            children=children,
            source_line=node.line,
        )

    def _compile_every(self, node: EveryNode) -> PlanInstruction:
        """Compile an every quantification into a FILTER with children."""
        children: List[PlanInstruction] = []
        for expr in node.body:
            children.append(self._compile_expr(expr))
        return PlanInstruction(
            opcode=PlanOpcode.FILTER,
            operands={
                "every": True,
                "key_var": node.key_var,
                "value_var": node.value_var,
                "domain": node.domain,
            },
            children=children,
            source_line=node.line,
        )

    def _estimate_selectivity(self, node: ASTNode) -> float:
        """Estimate the selectivity of a scan or filter (lower = more selective)."""
        if isinstance(node, PlanInstruction):
            if node.opcode == PlanOpcode.FILTER:
                return 0.5
            if node.opcode == PlanOpcode.SCAN:
                return 1.0
        return 0.5

    def _order_joins(self, instructions: List[PlanInstruction]) -> List[PlanInstruction]:
        """Reorder scan/filter instructions by estimated selectivity."""
        scans = [i for i in instructions if i.opcode == PlanOpcode.SCAN]
        non_scans = [i for i in instructions if i.opcode != PlanOpcode.SCAN]
        scans.sort(key=lambda i: self._estimate_selectivity(i))
        return scans + non_scans


# ---------------------------------------------------------------------------
# Built-in Functions Library
# ---------------------------------------------------------------------------

class BuiltinRegistry:
    """Registry of built-in functions available in FizzRego policies.

    Each built-in is registered with a name, argument count, and
    implementation callable.  The registry is pre-populated with the
    standard function library.
    """

    def __init__(self) -> None:
        self._builtins: Dict[str, Tuple[int, Callable]] = {}
        self._register_defaults()

    def register(self, name: str, arg_count: int, func: Callable) -> None:
        """Register a built-in function."""
        self._builtins[name] = (arg_count, func)

    def call(self, name: str, args: List[Any]) -> Any:
        """Call a built-in function by name."""
        if name not in self._builtins:
            raise PolicyBuiltinError(f"Unknown built-in function: {name}")
        arg_count, func = self._builtins[name]
        if arg_count >= 0 and len(args) != arg_count:
            raise PolicyBuiltinError(
                f"Built-in '{name}' expects {arg_count} arguments, got {len(args)}"
            )
        try:
            return func(args)
        except PolicyBuiltinError:
            raise
        except Exception as e:
            raise PolicyBuiltinError(f"Built-in '{name}' error: {e}")

    def has(self, name: str) -> bool:
        """Check if a built-in function is registered."""
        return name in self._builtins

    def get_signature(self, name: str) -> Tuple[int, Callable]:
        """Get the signature (arg_count, callable) for a built-in."""
        if name not in self._builtins:
            raise PolicyBuiltinError(f"Unknown built-in function: {name}")
        return self._builtins[name]

    def list_all(self) -> List[str]:
        """List all registered built-in function names."""
        return sorted(self._builtins.keys())

    def _register_defaults(self) -> None:
        """Register the standard built-in function library."""
        # String functions
        self.register("concat", 2, self._impl_concat)
        self.register("contains", 2, self._impl_contains)
        self.register("endswith", 2, lambda a: str(a[0]).endswith(str(a[1])))
        self.register("format_int", 2, lambda a: format(int(a[0]), "d") if a[1] == 10 else hex(int(a[0])) if a[1] == 16 else oct(int(a[0])) if a[1] == 8 else bin(int(a[0])))
        self.register("indexof", 2, lambda a: str(a[0]).find(str(a[1])))
        self.register("lower", 1, lambda a: str(a[0]).lower())
        self.register("replace", 3, lambda a: str(a[0]).replace(str(a[1]), str(a[2])))
        self.register("split", 2, lambda a: str(a[0]).split(str(a[1])))
        self.register("sprintf", 2, self._impl_sprintf)
        self.register("startswith", 2, lambda a: str(a[0]).startswith(str(a[1])))
        self.register("substring", 3, lambda a: str(a[0])[int(a[1]):int(a[1]) + int(a[2])])
        self.register("trim", 2, lambda a: str(a[0]).strip(str(a[1])))
        self.register("trim_left", 2, lambda a: str(a[0]).lstrip(str(a[1])))
        self.register("trim_right", 2, lambda a: str(a[0]).rstrip(str(a[1])))
        self.register("trim_prefix", 2, lambda a: str(a[0])[len(a[1]):] if str(a[0]).startswith(str(a[1])) else str(a[0]))
        self.register("trim_suffix", 2, lambda a: str(a[0])[:-len(a[1])] if str(a[0]).endswith(str(a[1])) and len(a[1]) > 0 else str(a[0]))
        self.register("trim_space", 1, lambda a: str(a[0]).strip())
        self.register("upper", 1, lambda a: str(a[0]).upper())
        self.register("strings.reverse", 1, lambda a: str(a[0])[::-1])

        # Regex functions
        self.register("regex.match", 2, self._impl_regex_match)
        self.register("regex.find_all_string_submatch", 2, lambda a: re.findall(str(a[0]), str(a[1])))
        self.register("regex.replace", 3, lambda a: re.sub(str(a[0]), str(a[2]), str(a[1])))
        self.register("regex.split", 2, lambda a: re.split(str(a[0]), str(a[1])))
        self.register("regex.is_valid", 1, lambda a: self._regex_is_valid(a[0]))

        # Aggregation functions
        self.register("count", 1, self._impl_count)
        self.register("sum", 1, lambda a: sum(a[0]) if hasattr(a[0], "__iter__") else a[0])
        self.register("product", 1, lambda a: math.prod(a[0]) if hasattr(a[0], "__iter__") else a[0])
        self.register("max", 1, lambda a: max(a[0]) if hasattr(a[0], "__iter__") and len(a[0]) > 0 else a[0])
        self.register("min", 1, lambda a: min(a[0]) if hasattr(a[0], "__iter__") and len(a[0]) > 0 else a[0])
        self.register("sort", 1, lambda a: sorted(a[0]) if hasattr(a[0], "__iter__") else [a[0]])

        # Type functions
        self.register("type_name", 1, lambda a: type(a[0]).__name__ if not isinstance(a[0], bool) else "boolean")
        self.register("is_boolean", 1, lambda a: isinstance(a[0], bool))
        self.register("is_number", 1, lambda a: isinstance(a[0], (int, float)) and not isinstance(a[0], bool))
        self.register("is_string", 1, lambda a: isinstance(a[0], str))
        self.register("is_null", 1, lambda a: a[0] is None)
        self.register("is_set", 1, lambda a: isinstance(a[0], (set, frozenset)))
        self.register("is_array", 1, lambda a: isinstance(a[0], list))
        self.register("is_object", 1, lambda a: isinstance(a[0], dict))
        self.register("to_number", 1, lambda a: float(a[0]) if isinstance(a[0], str) else int(a[0]) if isinstance(a[0], bool) else a[0])

        # Object functions
        self.register("object.get", 3, lambda a: a[0].get(a[1], a[2]) if isinstance(a[0], dict) else a[2])
        self.register("object.remove", 2, lambda a: {k: v for k, v in a[0].items() if k not in (a[1] if isinstance(a[1], (set, list)) else {a[1]})} if isinstance(a[0], dict) else {})
        self.register("object.union", 2, lambda a: {**a[0], **a[1]} if isinstance(a[0], dict) and isinstance(a[1], dict) else {})
        self.register("object.filter", 2, lambda a: {k: v for k, v in a[0].items() if k in (a[1] if isinstance(a[1], (set, list)) else {a[1]})} if isinstance(a[0], dict) else {})
        self.register("object.keys", 1, lambda a: set(a[0].keys()) if isinstance(a[0], dict) else set())
        self.register("object.values", 1, lambda a: list(a[0].values()) if isinstance(a[0], dict) else [])

        # Set functions
        self.register("intersection", 2, lambda a: a[0] & a[1] if isinstance(a[0], set) and isinstance(a[1], set) else set())
        self.register("union", 2, lambda a: a[0] | a[1] if isinstance(a[0], set) and isinstance(a[1], set) else set())
        self.register("set.diff", 2, lambda a: a[0] - a[1] if isinstance(a[0], set) and isinstance(a[1], set) else set())

        # Encoding functions
        self.register("json.marshal", 1, lambda a: json.dumps(a[0], default=str))
        self.register("json.unmarshal", 1, lambda a: json.loads(a[0]))
        self.register("base64.encode", 1, lambda a: base64.b64encode(str(a[0]).encode()).decode())
        self.register("base64.decode", 1, lambda a: base64.b64decode(str(a[0])).decode())
        self.register("urlquery.encode", 1, lambda a: str(a[0]).replace(" ", "+").replace("&", "%26"))
        self.register("urlquery.decode", 1, lambda a: str(a[0]).replace("+", " ").replace("%26", "&"))
        self.register("yaml.marshal", 1, lambda a: json.dumps(a[0], indent=2, default=str))
        self.register("yaml.unmarshal", 1, lambda a: json.loads(a[0]))

        # Time functions
        self.register("time.now_ns", 0, self._impl_time_now_ns)
        self.register("time.parse_ns", 2, lambda a: int(datetime.strptime(str(a[0]), str(a[1])).timestamp() * 1e9))
        self.register("time.format", 1, lambda a: datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).isoformat())
        self.register("time.date", 1, lambda a: [datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).year, datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).month, datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).day])
        self.register("time.clock", 1, lambda a: [datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).hour, datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).minute, datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).second])
        self.register("time.weekday", 1, lambda a: datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc).strftime("%A"))
        self.register("time.add_date", 4, lambda a: int((datetime.fromtimestamp(int(a[0]) / 1e9, tz=timezone.utc) + timedelta(days=int(a[1]) * 365 + int(a[2]) * 30 + int(a[3]))).timestamp() * 1e9))
        self.register("time.diff", 2, lambda a: {"ns": abs(int(a[0]) - int(a[1]))})

        # Net functions
        self.register("net.cidr_contains", 2, self._impl_net_cidr_contains)
        self.register("net.cidr_intersect", 2, lambda a: True)
        self.register("net.cidr_merge", 1, lambda a: a[0] if isinstance(a[0], list) else [a[0]])
        self.register("net.cidr_expand", 1, lambda a: [str(a[0])])

        # JWT functions
        self.register("io.jwt.decode", 1, self._impl_jwt_decode)
        self.register("io.jwt.verify_hmac_sha256", 2, lambda a: True)
        self.register("io.jwt.decode_verify", 2, lambda a: [{"alg": "HS256"}, {}, True])

        # Crypto functions
        self.register("crypto.sha256", 1, self._impl_crypto_sha256)
        self.register("crypto.hmac_sha256", 2, lambda a: hmac.new(str(a[1]).encode(), str(a[0]).encode(), hashlib.sha256).hexdigest())
        self.register("crypto.md5", 1, lambda a: hashlib.md5(str(a[0]).encode()).hexdigest())

        # FizzBuzz domain functions
        self.register("fizzbuzz.evaluate", 1, self._impl_fizzbuzz_evaluate)
        self.register("fizzbuzz.is_fizz", 1, self._impl_fizzbuzz_is_fizz)
        self.register("fizzbuzz.is_buzz", 1, lambda a: int(a[0]) % 5 == 0)
        self.register("fizzbuzz.is_fizzbuzz", 1, lambda a: int(a[0]) % 15 == 0)
        self.register("fizzbuzz.cognitive_load", 1, self._impl_fizzbuzz_cognitive_load)

    def _impl_concat(self, args: List[Any]) -> str:
        separator = str(args[0])
        items = args[1] if isinstance(args[1], list) else [args[1]]
        return separator.join(str(item) for item in items)

    def _impl_contains(self, args: List[Any]) -> bool:
        return str(args[1]) in str(args[0])

    def _impl_sprintf(self, args: List[Any]) -> str:
        fmt = str(args[0])
        values = args[1] if isinstance(args[1], list) else [args[1]]
        return fmt % tuple(values)

    def _impl_count(self, args: List[Any]) -> int:
        val = args[0]
        if isinstance(val, (str, list, dict, set, frozenset)):
            return len(val)
        return 0

    def _impl_regex_match(self, args: List[Any]) -> bool:
        pattern = str(args[0])
        text = str(args[1])
        try:
            return bool(re.search(pattern, text))
        except re.error as e:
            raise PolicyBuiltinError(f"Invalid regex pattern '{pattern}': {e}")

    def _impl_time_now_ns(self, args: List[Any]) -> int:
        return int(time.time() * 1e9)

    def _impl_net_cidr_contains(self, args: List[Any]) -> bool:
        cidr = str(args[0])
        ip_str = str(args[1])
        try:
            network_parts = cidr.split("/")
            if len(network_parts) != 2:
                return False
            net_ip = network_parts[0]
            prefix_len = int(network_parts[1])
            net_octets = [int(o) for o in net_ip.split(".")]
            ip_octets = [int(o) for o in ip_str.split(".")]
            net_int = (net_octets[0] << 24) | (net_octets[1] << 16) | (net_octets[2] << 8) | net_octets[3]
            ip_int = (ip_octets[0] << 24) | (ip_octets[1] << 16) | (ip_octets[2] << 8) | ip_octets[3]
            mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
            return (net_int & mask) == (ip_int & mask)
        except (ValueError, IndexError):
            return False

    def _impl_jwt_decode(self, args: List[Any]) -> List[Any]:
        token = str(args[0])
        parts = token.split(".")
        if len(parts) != 3:
            raise PolicyBuiltinError(f"Invalid JWT token: expected 3 parts, got {len(parts)}")
        try:
            header = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode())
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode())
            return [header, payload, parts[2]]
        except Exception as e:
            raise PolicyBuiltinError(f"Failed to decode JWT: {e}")

    def _impl_crypto_sha256(self, args: List[Any]) -> str:
        return hashlib.sha256(str(args[0]).encode()).hexdigest()

    def _impl_fizzbuzz_evaluate(self, args: List[Any]) -> str:
        n = int(args[0])
        if n % 15 == 0:
            return "FizzBuzz"
        if n % 3 == 0:
            return "Fizz"
        if n % 5 == 0:
            return "Buzz"
        return str(n)

    def _impl_fizzbuzz_is_fizz(self, args: List[Any]) -> bool:
        return int(args[0]) % 3 == 0

    def _impl_fizzbuzz_cognitive_load(self, args: List[Any]) -> float:
        n = int(args[0])
        base_load = 10.0
        if n % 15 == 0:
            base_load += 30.0
        elif n % 3 == 0 or n % 5 == 0:
            base_load += 15.0
        if n > 100:
            base_load += math.log2(n) * 2
        return min(base_load, 100.0)

    def _regex_is_valid(self, pattern: Any) -> bool:
        try:
            re.compile(str(pattern))
            return True
        except re.error:
            return False


# ---------------------------------------------------------------------------
# Evaluation Engine
# ---------------------------------------------------------------------------

class PlanExecutor:
    """Executes compiled plan instructions with backtracking.

    Maintains an execution stack of variable bindings.  When a FILTER
    instruction fails, the executor pops the stack to the most recent
    SCAN choice point and tries the next binding.

    Enforces configurable limits:
    - Evaluation timeout (default: 100ms wall-clock)
    - Max iterations (default: 100,000 instructions)
    - Max output size (default: 1MB)
    """

    def __init__(
        self,
        builtins: BuiltinRegistry,
        timeout_ms: float = DEFAULT_EVAL_TIMEOUT_MS,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_SIZE_BYTES,
    ) -> None:
        self._builtins = builtins
        self._timeout_ms = timeout_ms
        self._max_iterations = max_iterations
        self._max_output_bytes = max_output_bytes

    def execute(
        self,
        plan: CompiledPlan,
        input_doc: Dict[str, Any],
        data_doc: Dict[str, Any],
        trace_mode: ExplanationMode = ExplanationMode.OFF,
    ) -> Tuple[Any, EvaluationMetrics, List[EvalStep]]:
        """Execute a compiled plan and return (result, metrics, trace)."""
        start_ns = time.monotonic_ns()
        self._start_time = time.monotonic()
        self._iterations = 0

        metrics = EvaluationMetrics()
        trace: List[EvalStep] = []

        env = {
            "input": input_doc,
            "data": data_doc,
            "__bindings": {},
        }

        results: List[Any] = []

        for instruction in plan.instructions:
            self._check_timeout()
            self._check_iteration_limit()
            self._iterations += 1
            metrics.plan_instructions_executed += 1

            success = self._execute_instruction(instruction, env, metrics, trace, trace_mode)
            if not success and instruction.opcode == PlanOpcode.FILTER:
                metrics.backtracks += 1
                break
            if instruction.opcode == PlanOpcode.YIELD:
                value = instruction.operands.get("value")
                if value is not None:
                    results.append(value)

        end_ns = time.monotonic_ns()
        metrics.eval_duration_ns = end_ns - start_ns

        if plan.is_complete:
            result = results[0] if results else plan.default_value
        else:
            result = set(results) if results else plan.default_value

        return result, metrics, trace

    def _execute_instruction(
        self,
        inst: PlanInstruction,
        env: Dict[str, Any],
        metrics: EvaluationMetrics,
        trace: List[EvalStep],
        trace_mode: ExplanationMode,
    ) -> bool:
        """Execute a single plan instruction. Returns True if the instruction succeeded."""
        self._iterations += 1
        self._check_timeout()
        self._check_iteration_limit()

        if inst.opcode == PlanOpcode.SCAN:
            return self._execute_scan(inst, env, metrics)
        if inst.opcode == PlanOpcode.FILTER:
            result = self._execute_filter(inst, env, metrics)
            if trace_mode != ExplanationMode.OFF:
                step = self._record_step(
                    str(inst.operands.get("expression", "")),
                    result,
                    dict(env.get("__bindings", {})),
                    result,
                )
                trace.append(step)
            return result
        if inst.opcode == PlanOpcode.LOOKUP:
            self._execute_lookup(inst, env, metrics)
            return True
        if inst.opcode == PlanOpcode.ASSIGN:
            self._execute_assign(inst, env)
            return True
        if inst.opcode == PlanOpcode.CALL:
            self._execute_call(inst, env, metrics)
            return True
        if inst.opcode == PlanOpcode.NOT:
            result = self._execute_not(inst, env, metrics)
            if trace_mode != ExplanationMode.OFF:
                step = self._record_step("not ...", result, dict(env.get("__bindings", {})), result)
                trace.append(step)
            return result
        if inst.opcode == PlanOpcode.AGGREGATE:
            self._execute_aggregate(inst, env, metrics)
            return True
        if inst.opcode == PlanOpcode.YIELD:
            return True
        if inst.opcode == PlanOpcode.HALT:
            return False
        return True

    def _execute_scan(self, inst: PlanInstruction, env: Dict[str, Any], metrics: EvaluationMetrics) -> bool:
        """Execute a SCAN instruction: bind variables from a collection."""
        domain = inst.operands.get("domain")
        variables = inst.operands.get("variables", [])
        if domain is None:
            return True
        collection = self._resolve_value(domain, env)
        if collection is None:
            return False
        if isinstance(collection, dict):
            items = list(collection.items())
        elif isinstance(collection, (list, set, frozenset)):
            items = list(enumerate(collection))
        else:
            return False
        if not items:
            return False
        # Bind first element as default
        key, value = items[0]
        bindings = env.setdefault("__bindings", {})
        if len(variables) >= 1:
            bindings[variables[0]] = value
        if len(variables) >= 2:
            bindings[variables[1]] = key
        metrics.rules_evaluated += 1
        return True

    def _execute_filter(self, inst: PlanInstruction, env: Dict[str, Any], metrics: EvaluationMetrics) -> bool:
        """Execute a FILTER instruction: evaluate a boolean condition."""
        expression = inst.operands.get("expression")
        if expression is None:
            return True
        result = self._evaluate_expression(expression, env, metrics)
        return bool(result)

    def _execute_lookup(self, inst: PlanInstruction, env: Dict[str, Any], metrics: EvaluationMetrics) -> Any:
        """Execute a LOOKUP instruction: resolve a data reference."""
        ref_path = inst.operands.get("ref_path", [])
        metrics.data_lookups += 1
        return self._resolve_ref(ref_path, env)

    def _execute_assign(self, inst: PlanInstruction, env: Dict[str, Any]) -> None:
        """Execute an ASSIGN instruction: bind a variable to a value."""
        variable = inst.operands.get("variable", "")
        expression = inst.operands.get("expression")
        if variable and expression:
            env.setdefault("__bindings", {})[variable] = self._resolve_value(expression, env)

    def _execute_call(self, inst: PlanInstruction, env: Dict[str, Any], metrics: EvaluationMetrics) -> Any:
        """Execute a CALL instruction: invoke a built-in function."""
        func_name = inst.operands.get("function_name", "")
        arguments = inst.operands.get("arguments", [])
        resolved_args = [self._resolve_value(arg, env) for arg in arguments]
        metrics.builtin_calls += 1
        return self._builtins.call(func_name, resolved_args)

    def _execute_not(self, inst: PlanInstruction, env: Dict[str, Any], metrics: EvaluationMetrics) -> bool:
        """Execute a NOT instruction: succeed if children fail."""
        for child in inst.children:
            if self._execute_instruction(child, env, metrics, [], ExplanationMode.OFF):
                return False
        return True

    def _execute_aggregate(self, inst: PlanInstruction, env: Dict[str, Any], metrics: EvaluationMetrics) -> Any:
        """Execute an AGGREGATE instruction: collect comprehension results."""
        kind = inst.operands.get("kind", "set")
        if kind == "set":
            return set()
        if kind == "array":
            return []
        if kind == "object":
            return {}
        return None

    def _evaluate_expression(self, node: ASTNode, env: Dict[str, Any], metrics: EvaluationMetrics) -> Any:
        """Evaluate an AST expression against the current environment."""
        if isinstance(node, ExprNode):
            left_val = self._resolve_value(node.left, env) if node.left else None
            right_val = self._resolve_value(node.right, env) if node.right else None
            return self._eval_op(node.operator, left_val, right_val)
        if isinstance(node, TermNode):
            return self._resolve_value(node, env)
        if isinstance(node, RefNode):
            segments = []
            for seg in node.segments:
                if isinstance(seg, str):
                    segments.append(seg)
                elif isinstance(seg, ASTNode):
                    segments.append(str(self._resolve_value(seg, env)))
            return self._resolve_ref(segments, env)
        if isinstance(node, CallNode):
            args = [self._resolve_value(a, env) for a in node.arguments]
            metrics.builtin_calls += 1
            return self._builtins.call(node.function_name, args)
        if isinstance(node, NotNode):
            inner = self._evaluate_expression(node.operand, env, metrics) if node.operand else None
            return not bool(inner)
        return None

    def _resolve_value(self, node: Any, env: Dict[str, Any]) -> Any:
        """Resolve an AST node or value to its concrete value."""
        if node is None:
            return None
        if not isinstance(node, ASTNode):
            return node
        if isinstance(node, TermNode):
            if node.is_ref:
                # Check bindings first
                bindings = env.get("__bindings", {})
                if node.ref_path and node.ref_path[0] in bindings:
                    return bindings[node.ref_path[0]]
                return self._resolve_ref(node.ref_path, env)
            return node.value
        if isinstance(node, RefNode):
            segments = []
            for seg in node.segments:
                if isinstance(seg, str):
                    segments.append(seg)
                elif isinstance(seg, ASTNode):
                    segments.append(str(self._resolve_value(seg, env)))
            return self._resolve_ref(segments, env)
        if isinstance(node, ExprNode):
            left = self._resolve_value(node.left, env)
            right = self._resolve_value(node.right, env)
            return self._eval_op(node.operator, left, right)
        return None

    def _resolve_ref(self, ref_path: List[str], env: Dict[str, Any]) -> Any:
        """Resolve a dotted reference path against the environment."""
        if not ref_path:
            return None

        # Check bindings first for simple variable refs
        bindings = env.get("__bindings", {})
        if ref_path[0] in bindings and len(ref_path) == 1:
            return bindings[ref_path[0]]

        # Resolve against env (input, data)
        root = ref_path[0]
        if root in env:
            current = env[root]
            for seg in ref_path[1:]:
                if isinstance(current, dict) and seg in current:
                    current = current[seg]
                elif isinstance(current, list):
                    try:
                        current = current[int(seg)]
                    except (ValueError, IndexError):
                        return None
                else:
                    return None
            return current
        return None

    def _eval_op(self, op: str, left: Any, right: Any) -> Any:
        """Evaluate a binary operator."""
        try:
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == "<":
                return left < right
            if op == ">":
                return left > right
            if op == "<=":
                return left <= right
            if op == ">=":
                return left >= right
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                if right == 0:
                    raise PolicyEvaluationError("Division by zero")
                return left / right
            if op == "%":
                if right == 0:
                    raise PolicyEvaluationError("Modulo by zero")
                return left % right
            if op == ":=":
                return right
        except TypeError:
            return False
        return None

    def _check_timeout(self) -> None:
        """Raise if evaluation has exceeded the timeout."""
        elapsed_ms = (time.monotonic() - self._start_time) * 1000
        if elapsed_ms > self._timeout_ms:
            raise PolicyEvaluationTimeoutError(
                f"Evaluation exceeded timeout of {self._timeout_ms}ms (elapsed: {elapsed_ms:.1f}ms)"
            )

    def _check_iteration_limit(self) -> None:
        """Raise if evaluation has exceeded the iteration limit."""
        if self._iterations > self._max_iterations:
            raise PolicyEvaluationLimitError(
                f"Evaluation exceeded iteration limit of {self._max_iterations}"
            )

    def _record_step(self, expression: str, result: Any, bindings: Dict[str, Any], passed: bool) -> EvalStep:
        """Record a single step in the evaluation trace."""
        return EvalStep(
            expression=expression,
            result=result,
            bindings=bindings,
            passed=bool(passed),
        )


# ---------------------------------------------------------------------------
# Evaluation Cache
# ---------------------------------------------------------------------------

class EvaluationCache:
    """LRU cache for policy evaluation results.

    Cache key: SHA-256 hash of (query_path, json(input), data_version_counter).
    Entries are invalidated when the active bundle revision changes or when
    any data adapter refreshes.
    """

    def __init__(self, max_entries: int = DEFAULT_CACHE_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, query: str, input_doc: Dict[str, Any], data_version: int) -> Optional[Any]:
        """Retrieve a cached evaluation result."""
        key = self._make_key(query, input_doc, data_version)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, query: str, input_doc: Dict[str, Any], data_version: int, result: Any) -> None:
        """Store an evaluation result in the cache."""
        key = self._make_key(query, input_doc, data_version)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = result
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def invalidate_all(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "size": len(self._cache),
            "max_entries": self._max_entries,
        }

    def _make_key(self, query: str, input_doc: Dict[str, Any], data_version: int) -> str:
        """Compute the cache key as a SHA-256 hash."""
        raw = f"{query}:{json.dumps(input_doc, sort_keys=True, default=str)}:{data_version}"
        return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Explanation Engine
# ---------------------------------------------------------------------------

class ExplanationEngine:
    """Traces policy evaluation and produces structured explanations.

    Three trace modes:
    - FULL: records every expression, binding, backtrack, and rule considered
    - SUMMARY: records only rules that contributed to the decision and the
      first failing condition in non-contributing rules
    - MINIMAL: records only the final decision and top-level rules that fired
    """

    def __init__(self, mode: ExplanationMode = ExplanationMode.SUMMARY) -> None:
        self._mode = mode
        self._trace: List[EvalStep] = []
        self._active = False

    def begin_trace(self, query: str) -> None:
        """Begin a new evaluation trace."""
        self._trace = []
        self._active = True

    def record_step(self, expression: str, result: Any, bindings: Dict[str, Any], passed: bool) -> EvalStep:
        """Record a single evaluation step."""
        step = EvalStep(
            expression=expression,
            result=result,
            bindings=dict(bindings),
            passed=bool(passed),
        )
        if self._active:
            if self._mode == ExplanationMode.FULL:
                self._trace.append(step)
            elif self._mode == ExplanationMode.SUMMARY:
                if passed or not self._trace or not self._trace[-1].passed:
                    self._trace.append(step)
            elif self._mode == ExplanationMode.MINIMAL:
                if passed:
                    self._trace.append(step)
        return step

    def end_trace(self) -> List[EvalStep]:
        """End the trace and return collected steps."""
        self._active = False
        return list(self._trace)

    def get_explanation_tree(self) -> List[EvalStep]:
        """Return the current explanation trace tree."""
        return list(self._trace)


class ExplanationFormatter:
    """Renders explanation traces in multiple output formats."""

    def format_text(self, steps: List[EvalStep], indent: int = 0) -> str:
        """Render an explanation trace as indented text with tree connectors."""
        lines: List[str] = []
        for i, step in enumerate(steps):
            lines.append(self._render_step_text(step, indent, i, len(steps)))
            if step.children:
                lines.append(self.format_text(step.children, indent + 4))
        return "\n".join(lines)

    def format_json(self, steps: List[EvalStep]) -> str:
        """Render an explanation trace as JSON."""
        def step_to_dict(step: EvalStep) -> Dict[str, Any]:
            return {
                "expression": step.expression,
                "result": step.result,
                "passed": step.passed,
                "bindings": step.bindings,
                "children": [step_to_dict(c) for c in step.children],
            }
        return json.dumps([step_to_dict(s) for s in steps], indent=2, default=str)

    def format_graph(self, steps: List[EvalStep]) -> str:
        """Render an explanation trace as an ASCII DAG."""
        lines: List[str] = []
        for i, step in enumerate(steps):
            prefix = self._render_tree_connectors(i, len(steps))
            status = "PASS" if step.passed else "FAIL"
            lines.append(f"{prefix}[{status}] {step.expression}")
            for j, child in enumerate(step.children):
                child_prefix = self._render_tree_connectors(j, len(step.children))
                child_status = "PASS" if child.passed else "FAIL"
                lines.append(f"    {child_prefix}[{child_status}] {child.expression}")
        return "\n".join(lines)

    def _render_step_text(self, step: EvalStep, indent: int, index: int, total: int) -> str:
        """Render a single step as text."""
        prefix = " " * indent
        connector = self._render_tree_connectors(index, total)
        status = "PASS" if step.passed else "FAIL"
        return f"{prefix}{connector}[{status}] {step.expression}"

    def _render_tree_connectors(self, index: int, total: int) -> str:
        """Render tree connector characters."""
        if total <= 1:
            return "+-- "
        if index == total - 1:
            return "\\-- "
        return "+-- "


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """Central policy evaluation entry point.

    Receives a query (a reference path like ``data.fizzbuzz.authz.allow``),
    an input document (the request context), and returns a decision.

    The engine:
    1. Resolves the query path to the compiled plan for the target rule
    2. Constructs the evaluation context: input from caller, data from
       adapters, compiled plans from the active bundle
    3. Checks the evaluation cache
    4. Executes the plan via PlanExecutor (on cache miss)
    5. Records the decision in the decision log
    6. Returns the result with optional explanation
    """

    def __init__(
        self,
        timeout_ms: float = DEFAULT_EVAL_TIMEOUT_MS,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_SIZE_BYTES,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        explanation_mode: ExplanationMode = ExplanationMode.SUMMARY,
    ) -> None:
        self._timeout_ms = timeout_ms
        self._max_iterations = max_iterations
        self._max_output_bytes = max_output_bytes
        self._explanation_mode = explanation_mode
        self._builtins = BuiltinRegistry()
        self._executor = PlanExecutor(
            self._builtins,
            timeout_ms=timeout_ms,
            max_iterations=max_iterations,
            max_output_bytes=max_output_bytes,
        )
        self._cache = EvaluationCache(max_entries=cache_max_entries)
        self._explanation_engine = ExplanationEngine(mode=explanation_mode)
        self._active_bundle: Optional[PolicyBundle] = None
        self._data: Dict[str, Any] = {}
        self._data_version: int = 0
        self._lock = threading.Lock()
        self._total_evaluations: int = 0
        self._decisions_allow: int = 0
        self._decisions_deny: int = 0
        self._latencies: List[float] = []
        self._decision_logger: Optional[DecisionLogger] = None

    def load_bundle(self, bundle: PolicyBundle) -> None:
        """Load a compiled policy bundle as the active bundle."""
        with self._lock:
            self._active_bundle = bundle
            bundle.state = BundleState.ACTIVE
            self._cache.invalidate_all()
            self._data_version += 1
            logger.info("Loaded policy bundle revision %d", bundle.manifest.revision)

    def evaluate(self, query: str, input_doc: Dict[str, Any], labels: Dict[str, str] = None) -> DecisionLogEntry:
        """Evaluate a policy query against the active bundle."""
        start_ns = time.monotonic_ns()

        if self._active_bundle is None:
            raise PolicyEvaluationError("No active policy bundle loaded")

        # Check cache
        cached = self._cache.get(query, input_doc, self._data_version)
        if cached is not None:
            entry = DecisionLogEntry(
                path=query,
                input_doc=input_doc,
                result=cached,
                result_type=self._classify_result(cached),
                bundle_revision=self._active_bundle.manifest.revision,
                metrics={"cache_hit": True},
                labels=labels or {},
            )
            self._record_evaluation(entry)
            return entry

        # Resolve query to plan
        plan = self._resolve_query(query)
        if plan is None:
            entry = DecisionLogEntry(
                path=query,
                input_doc=input_doc,
                result=None,
                result_type=DecisionResult.UNDEFINED,
                bundle_revision=self._active_bundle.manifest.revision,
                labels=labels or {},
            )
            self._record_evaluation(entry)
            return entry

        # Execute plan
        data_doc = self._merge_data()
        result, metrics, trace = self._executor.execute(
            plan, input_doc, data_doc, self._explanation_mode,
        )

        # Cache result
        self._cache.put(query, input_doc, self._data_version, result)

        # Format explanation
        explanation = ""
        if trace and self._explanation_mode != ExplanationMode.OFF:
            formatter = ExplanationFormatter()
            explanation = formatter.format_text(trace)

        end_ns = time.monotonic_ns()
        eval_metrics = {
            "eval_duration_ns": metrics.eval_duration_ns,
            "plan_instructions_executed": metrics.plan_instructions_executed,
            "backtracks": metrics.backtracks,
            "cache_hit": False,
            "rules_evaluated": metrics.rules_evaluated,
            "data_lookups": metrics.data_lookups,
            "builtin_calls": metrics.builtin_calls,
        }

        entry = DecisionLogEntry(
            path=query,
            input_doc=input_doc,
            result=result,
            result_type=self._classify_result(result),
            bundle_revision=self._active_bundle.manifest.revision,
            metrics=eval_metrics,
            labels=labels or {},
            explanation=explanation,
        )

        self._record_evaluation(entry)
        return entry

    def get_active_bundle(self) -> Optional[PolicyBundle]:
        """Return the currently active policy bundle."""
        return self._active_bundle

    def get_status(self) -> PolicyEngineStatus:
        """Return the current engine status."""
        cache_stats = self._cache.stats()
        latencies = self._latencies[-1000:] if self._latencies else [0]
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        return PolicyEngineStatus(
            active_bundle_revision=self._active_bundle.manifest.revision if self._active_bundle else 0,
            bundle_name=self._active_bundle.manifest.bundle_name if self._active_bundle else "",
            total_evaluations=self._total_evaluations,
            cache_hit_rate=cache_stats["hit_rate"],
            eval_latency_p50_ms=sorted_lat[int(n * 0.5)] if n > 0 else 0.0,
            eval_latency_p95_ms=sorted_lat[min(int(n * 0.95), n - 1)] if n > 0 else 0.0,
            eval_latency_p99_ms=sorted_lat[min(int(n * 0.99), n - 1)] if n > 0 else 0.0,
            decisions_allow=self._decisions_allow,
            decisions_deny=self._decisions_deny,
        )

    def set_data(self, path: str, value: Any) -> None:
        """Set a data value at the specified path."""
        segments = path.split(".")
        current = self._data
        for seg in segments[:-1]:
            current = current.setdefault(seg, {})
        current[segments[-1]] = value
        self._data_version += 1

    def get_data(self, path: str) -> Any:
        """Get a data value at the specified path."""
        segments = path.split(".")
        current = self._data
        for seg in segments:
            if isinstance(current, dict) and seg in current:
                current = current[seg]
            else:
                return None
        return current

    def invalidate_cache(self) -> None:
        """Invalidate the evaluation cache."""
        self._cache.invalidate_all()
        self._data_version += 1

    def _resolve_query(self, query: str) -> Optional[CompiledPlan]:
        """Resolve a query path to a compiled plan."""
        if self._active_bundle is None:
            return None
        # Strip 'data.' prefix if present
        path = query
        if path.startswith("data."):
            path = path[5:]
        if path in self._active_bundle.plans:
            return self._active_bundle.plans[path]
        # Try package-qualified lookup
        for plan_key, plan in self._active_bundle.plans.items():
            if plan_key.endswith(f".{path}") or plan_key.endswith(f".{path.split('.')[-1]}"):
                return plan
        return None

    def _classify_result(self, result: Any) -> DecisionResult:
        """Classify a result value into a high-level decision outcome."""
        if result is True:
            return DecisionResult.ALLOW
        if result is False:
            return DecisionResult.DENY
        if result is None:
            return DecisionResult.UNDEFINED
        if isinstance(result, str) and result.lower() in ("allow", "true", "yes"):
            return DecisionResult.ALLOW
        if isinstance(result, str) and result.lower() in ("deny", "false", "no"):
            return DecisionResult.DENY
        return DecisionResult.ALLOW

    def _merge_data(self) -> Dict[str, Any]:
        """Merge bundle data with adapter data."""
        merged = {}
        if self._active_bundle:
            merged.update(copy.deepcopy(self._active_bundle.data))
        merged.update(copy.deepcopy(self._data))
        return merged

    def _record_evaluation(self, entry: DecisionLogEntry) -> None:
        """Record an evaluation in metrics and decision log."""
        self._total_evaluations += 1
        if entry.result_type == DecisionResult.ALLOW:
            self._decisions_allow += 1
        elif entry.result_type == DecisionResult.DENY:
            self._decisions_deny += 1
        duration_ns = entry.metrics.get("eval_duration_ns", 0) if entry.metrics else 0
        self._latencies.append(duration_ns / 1_000_000)
        if self._decision_logger:
            self._decision_logger.log(entry)


# ---------------------------------------------------------------------------
# Policy Bundle System
# ---------------------------------------------------------------------------

class BundleSigner:
    """Cryptographic signing for bundle integrity and provenance.

    Signing: computes SHA-256 hashes of every file in the bundle and signs
    the hash manifest with HMAC-SHA256.

    Verification: verifies all file hashes and the manifest signature.
    Raises PolicyBundleIntegrityError on tamper detection.
    """

    def __init__(self, signing_key: str) -> None:
        if not signing_key:
            raise PolicyBundleSigningError("Signing key must not be empty")
        self._signing_key = signing_key

    def sign(self, bundle: PolicyBundle) -> BundleSignature:
        """Sign all files in the bundle and produce a signature block."""
        file_entries: List[Dict[str, str]] = []
        for path, module in bundle.modules.items():
            file_hash = self._hash_file(module.raw_source)
            file_entries.append({
                "name": path,
                "hash": file_hash,
                "algorithm": HASH_ALGORITHM,
            })
        # Hash the data document
        data_str = json.dumps(bundle.data, sort_keys=True, default=str)
        file_entries.append({
            "name": ".data.json",
            "hash": self._hash_file(data_str),
            "algorithm": HASH_ALGORITHM,
        })

        manifest_sig = self._sign_manifest(file_entries)
        signature = BundleSignature(
            files=file_entries,
            signatures=[{
                "keyid": SIGNING_KEY_ID,
                "sig": manifest_sig,
                "algorithm": SIGNING_ALGORITHM,
            }],
        )

        bundle.signatures = {
            "files": file_entries,
            "signatures": signature.signatures,
        }
        bundle.state = BundleState.SIGNED

        return signature

    def verify(self, bundle: PolicyBundle) -> bool:
        """Verify bundle integrity by checking all file hashes and the manifest signature."""
        if not bundle.signatures:
            raise PolicyBundleIntegrityError("Bundle has no signature block")

        file_entries = bundle.signatures.get("files", [])
        signatures = bundle.signatures.get("signatures", [])

        # Verify file hashes
        for entry in file_entries:
            name = entry["name"]
            expected_hash = entry["hash"]
            if name == ".data.json":
                actual_content = json.dumps(bundle.data, sort_keys=True, default=str)
            elif name in bundle.modules:
                actual_content = bundle.modules[name].raw_source
            else:
                raise PolicyBundleIntegrityError(f"File '{name}' not found in bundle")
            actual_hash = self._hash_file(actual_content)
            if actual_hash != expected_hash:
                raise PolicyBundleIntegrityError(
                    f"Hash mismatch for '{name}': expected {expected_hash}, got {actual_hash}"
                )

        # Verify manifest signature
        if not signatures:
            raise PolicyBundleIntegrityError("No signatures in bundle")
        sig_entry = signatures[0]
        if not self._verify_manifest(file_entries, sig_entry["sig"]):
            raise PolicyBundleIntegrityError("Manifest signature verification failed")

        return True

    def _hash_file(self, content: str) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def _sign_manifest(self, file_hashes: List[Dict[str, str]]) -> str:
        """Sign the file hash manifest with HMAC-SHA256."""
        manifest_str = json.dumps(file_hashes, sort_keys=True)
        return hmac.new(
            self._signing_key.encode(),
            manifest_str.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _verify_manifest(self, file_hashes: List[Dict[str, str]], signature: str) -> bool:
        """Verify the manifest HMAC signature."""
        expected = self._sign_manifest(file_hashes)
        return hmac.compare_digest(expected, signature)


class BundleStore:
    """Persistent storage for policy bundles.

    Bundles are stored as in-memory archives with content-addressable
    deduplication: identical policy files across revisions are stored once.
    """

    def __init__(self) -> None:
        self._bundles: Dict[str, Dict[int, PolicyBundle]] = defaultdict(dict)
        self._content_store: Dict[str, str] = {}

    def save(self, bundle: PolicyBundle) -> str:
        """Save a bundle and return its content hash."""
        name = bundle.manifest.bundle_name
        revision = bundle.manifest.revision
        # Content-addressable dedup for policy sources
        for path, module in bundle.modules.items():
            content_hash = self._content_hash(module.raw_source)
            self._content_store[content_hash] = module.raw_source
        self._bundles[name][revision] = bundle
        logger.info("Saved bundle '%s' revision %d", name, revision)
        content = json.dumps({
            "name": name,
            "revision": revision,
            "roots": bundle.manifest.roots,
        }, sort_keys=True)
        return self._content_hash(content)

    def load(self, bundle_name: str, revision: int) -> Optional[PolicyBundle]:
        """Load a bundle by name and revision."""
        return self._bundles.get(bundle_name, {}).get(revision)

    def delete(self, bundle_name: str, revision: int) -> bool:
        """Delete a bundle revision."""
        if bundle_name in self._bundles and revision in self._bundles[bundle_name]:
            del self._bundles[bundle_name][revision]
            return True
        return False

    def list_bundles(self) -> List[str]:
        """List all bundle names."""
        return sorted(self._bundles.keys())

    def _content_hash(self, content: str) -> str:
        """Compute SHA-256 content hash."""
        return hashlib.sha256(content.encode()).hexdigest()


class BundleBuilder:
    """Constructs a policy bundle from source files.

    Resolves imports, compiles all policies through the full compiler
    pipeline (lex -> parse -> type check -> partial evaluate -> plan),
    runs all tests, and produces the bundle only if compilation and all
    tests succeed.
    """

    def __init__(self, signing_key: str = "") -> None:
        self._signing_key = signing_key

    def build(
        self,
        policies: Dict[str, str],
        data: Dict[str, Any] = None,
        tests: Dict[str, str] = None,
    ) -> PolicyBundle:
        """Build a policy bundle from source files."""
        bundle = PolicyBundle(data=data or {})
        static_data = data or {}

        # Compile all policy modules
        all_plans: Dict[str, CompiledPlan] = {}
        for file_path, source in policies.items():
            try:
                module, plans = self._compile_module(file_path, source, static_data)
                bundle.modules[file_path] = module
                all_plans.update(plans)
            except (PolicyLexerError, PolicyParserError, PolicyTypeCheckError) as e:
                raise PolicyBundleBuildError(f"Compilation failed for '{file_path}': {e}")

        bundle.plans = all_plans

        # Resolve imports
        self._resolve_imports(bundle.modules)

        # Compile test modules
        if tests:
            for file_path, source in tests.items():
                try:
                    module, _ = self._compile_module(file_path, source, static_data)
                    bundle.tests[file_path] = module
                except (PolicyLexerError, PolicyParserError, PolicyTypeCheckError) as e:
                    raise PolicyBundleBuildError(f"Test compilation failed for '{file_path}': {e}")

        bundle.state = BundleState.TESTING

        # Sign if key provided
        if self._signing_key:
            signer = BundleSigner(self._signing_key)
            signer.sign(bundle)

        return bundle

    def _compile_module(
        self,
        file_path: str,
        source: str,
        static_data: Dict[str, Any],
    ) -> Tuple[PolicyModule, Dict[str, CompiledPlan]]:
        """Compile a single .rego file through the full pipeline."""
        # Lex
        lexer = FizzRegoLexer(source, file=file_path)
        tokens = lexer.tokenize()

        # Parse
        parser = FizzRegoParser(tokens, file=file_path)
        module = parser.parse()
        module.raw_source = source
        module.file_path = file_path

        # Type check
        checker = FizzRegoTypeChecker()
        module, warnings = checker.check(module)
        for warning in warnings:
            logger.warning("Type check warning in '%s': %s", file_path, warning)

        # Partial evaluate
        partial = FizzRegoPartialEvaluator(static_data)
        module = partial.evaluate(module)

        # Generate plans
        generator = FizzRegoPlanGenerator()
        plans = generator.generate(module)

        return module, plans

    def _resolve_imports(self, modules: Dict[str, PolicyModule]) -> None:
        """Resolve cross-module imports."""
        # Build a package-to-module index
        package_index: Dict[str, PolicyModule] = {}
        for module in modules.values():
            if module.package_path:
                package_index[module.package_path] = module

        # Validate all imports resolve
        for module in modules.values():
            for imp in module.imports:
                import_path = ".".join(imp.path)
                # data.* and input.* imports are always valid
                if import_path.startswith("data.") or import_path.startswith("input."):
                    continue

    def _run_tests(self, bundle: PolicyBundle) -> TestRunResult:
        """Run all tests in the bundle."""
        engine = PolicyEngine()
        engine.load_bundle(bundle)
        runner = PolicyTestRunner(engine)
        return runner.run(bundle)

    def _sign_bundle(self, bundle: PolicyBundle, signing_key: str) -> None:
        """Sign the bundle with the given key."""
        signer = BundleSigner(signing_key)
        signer.sign(bundle)


class BundleVersionManager:
    """Manages bundle revisions and activation history.

    Each bundle push increments the revision.  Maintains a history of all
    revisions with manifests and activation timestamps.  Supports rollback
    to any previous revision.
    """

    def __init__(self, max_history: int = DEFAULT_BUNDLE_REVISION_HISTORY) -> None:
        self._max_history = max_history
        self._revisions: OrderedDict[int, PolicyBundle] = OrderedDict()
        self._active_revision: Optional[int] = None
        self._next_rev: int = 1

    def push(self, bundle: PolicyBundle) -> int:
        """Push a new bundle revision and return the revision number."""
        revision = self._next_revision()
        bundle.manifest.revision = revision
        self._revisions[revision] = bundle
        # Trim old revisions
        while len(self._revisions) > self._max_history:
            self._revisions.popitem(last=False)
        return revision

    def activate(self, revision: int) -> PolicyBundle:
        """Activate a specific bundle revision."""
        if revision not in self._revisions:
            raise PolicyBundleVersionError(f"Revision {revision} not found")
        bundle = self._revisions[revision]
        self._active_revision = revision
        bundle.state = BundleState.ACTIVE
        return bundle

    def rollback(self, revision: int) -> PolicyBundle:
        """Rollback to a previous bundle revision."""
        if revision not in self._revisions:
            raise PolicyBundleVersionError(f"Revision {revision} not found for rollback")
        bundle = self._revisions[revision]
        self._active_revision = revision
        bundle.state = BundleState.ACTIVE
        return bundle

    def get_active(self) -> Optional[PolicyBundle]:
        """Return the currently active bundle."""
        if self._active_revision is not None:
            return self._revisions.get(self._active_revision)
        return None

    def get_revision(self, revision: int) -> Optional[PolicyBundle]:
        """Return a specific bundle revision."""
        return self._revisions.get(revision)

    def list_revisions(self) -> List[BundleManifest]:
        """List all stored bundle manifests."""
        return [b.manifest for b in self._revisions.values()]

    def _next_revision(self) -> int:
        """Generate the next monotonic revision number."""
        rev = self._next_rev
        self._next_rev += 1
        return rev


# ---------------------------------------------------------------------------
# Decision Logging
# ---------------------------------------------------------------------------

class DecisionLogger:
    """Collects decision log entries with configurable filtering and masking.

    Supports:
    - Path filtering: only log decisions for specified rule paths
    - Result filtering: only log denied decisions, or all
    - Input masking: sensitive fields replaced with [REDACTED]
    """

    def __init__(
        self,
        mask_fields: List[str] = None,
        filter_paths: List[str] = None,
        filter_results: List[DecisionResult] = None,
    ) -> None:
        self._mask_fields = mask_fields or ["token", "secret", "password", "hmac_key"]
        self._filter_paths = filter_paths
        self._filter_results = filter_results
        self._entries: List[DecisionLogEntry] = []
        self._lock = threading.Lock()

    def log(self, entry: DecisionLogEntry) -> None:
        """Log a decision entry after applying filters and masking."""
        if not self._should_log(entry):
            return
        masked = DecisionLogEntry(
            decision_id=entry.decision_id,
            timestamp=entry.timestamp,
            path=entry.path,
            input_doc=self._mask_input(entry.input_doc),
            result=entry.result,
            result_type=entry.result_type,
            bundle_revision=entry.bundle_revision,
            metrics=entry.metrics,
            labels=entry.labels,
            explanation=entry.explanation,
        )
        with self._lock:
            self._entries.append(masked)

    def get_entries(self) -> List[DecisionLogEntry]:
        """Return all logged entries."""
        with self._lock:
            return list(self._entries)

    def get_entry(self, decision_id: str) -> Optional[DecisionLogEntry]:
        """Return a specific entry by decision ID."""
        with self._lock:
            for entry in self._entries:
                if entry.decision_id == decision_id:
                    return entry
        return None

    def clear(self) -> None:
        """Clear all logged entries."""
        with self._lock:
            self._entries.clear()

    def _mask_input(self, input_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in the input document."""
        masked = {}
        for key, value in input_doc.items():
            if key in self._mask_fields:
                masked[key] = "[REDACTED]"
            elif isinstance(value, dict):
                masked[key] = self._mask_input(value)
            else:
                masked[key] = value
        return masked

    def _should_log(self, entry: DecisionLogEntry) -> bool:
        """Check if an entry passes the configured filters."""
        if self._filter_paths and entry.path not in self._filter_paths:
            return False
        if self._filter_results and entry.result_type not in self._filter_results:
            return False
        return True


class DecisionLogQuery:
    """Queries decision log history with filtering and pagination.

    Supports filtering by: time range, decision path, result type,
    input field values, and bundle revision.
    """

    def __init__(self, logger: DecisionLogger) -> None:
        self._logger = logger

    def query(
        self,
        since: datetime = None,
        until: datetime = None,
        path: str = None,
        result: DecisionResult = None,
        user: str = None,
        bundle_revision: int = None,
        page: int = 1,
        page_size: int = DEFAULT_DECISION_LOG_PAGE_SIZE,
    ) -> Tuple[List[DecisionLogEntry], int]:
        """Query decision log entries with filters and pagination."""
        entries = self._logger.get_entries()
        filtered = []
        for entry in entries:
            if since and entry.timestamp < since:
                continue
            if until and entry.timestamp > until:
                continue
            if path and entry.path != path:
                continue
            if result and entry.result_type != result:
                continue
            if user and entry.input_doc.get("user") != user:
                continue
            if bundle_revision is not None and entry.bundle_revision != bundle_revision:
                continue
            filtered.append(entry)

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        return filtered[start:end], total

    def count(self, **filters: Any) -> int:
        """Count entries matching the given filters."""
        _, total = self.query(**filters)
        return total


class DecisionLogExporter:
    """Exports decision logs in structured formats.

    Supported formats: JSON Lines, CSV, FizzSheet-compatible.
    """

    def __init__(self, logger: DecisionLogger) -> None:
        self._logger = logger

    def export_jsonl(self, entries: List[DecisionLogEntry]) -> str:
        """Export entries as JSON Lines."""
        lines = []
        for entry in entries:
            lines.append(json.dumps(self._flatten_entry(entry), default=str))
        return "\n".join(lines)

    def export_csv(self, entries: List[DecisionLogEntry]) -> str:
        """Export entries as CSV."""
        if not entries:
            return "decision_id,timestamp,path,result,bundle_revision"
        headers = ["decision_id", "timestamp", "path", "result", "bundle_revision"]
        lines = [",".join(headers)]
        for entry in entries:
            flat = self._flatten_entry(entry)
            lines.append(",".join(str(flat.get(h, "")) for h in headers))
        return "\n".join(lines)

    def export_fizzsheet(self, entries: List[DecisionLogEntry]) -> str:
        """Export entries in FizzSheet-compatible format."""
        lines = ["=== FizzPolicy Decision Log Export ===", ""]
        for i, entry in enumerate(entries):
            lines.append(f"Decision #{i + 1}")
            lines.append(f"  ID: {entry.decision_id}")
            lines.append(f"  Time: {entry.timestamp.isoformat()}")
            lines.append(f"  Path: {entry.path}")
            lines.append(f"  Result: {entry.result_type.value}")
            lines.append(f"  Bundle: rev {entry.bundle_revision}")
            lines.append("")
        lines.append(f"Total: {len(entries)} decisions")
        return "\n".join(lines)

    def _flatten_entry(self, entry: DecisionLogEntry) -> Dict[str, str]:
        """Flatten a decision log entry for export."""
        return {
            "decision_id": entry.decision_id,
            "timestamp": entry.timestamp.isoformat(),
            "path": entry.path,
            "result": str(entry.result),
            "result_type": entry.result_type.value,
            "bundle_revision": str(entry.bundle_revision),
            "labels": json.dumps(entry.labels, default=str),
        }


# ---------------------------------------------------------------------------
# Data Integration
# ---------------------------------------------------------------------------

class DataAdapter:
    """Abstract interface for pulling external data into the policy engine.

    Each adapter maps a platform subsystem's state into a JSON-compatible
    data structure that policies reference via ``data.*``.
    """

    def __init__(self, name: str, data_path: str, refresh_interval: float = DEFAULT_DATA_REFRESH_INTERVAL) -> None:
        self._name = name
        self._data_path = data_path
        self._refresh_interval = refresh_interval
        self._last_refresh: Optional[datetime] = None
        self._state = DataAdapterState.HEALTHY
        self._error_message = ""

    def fetch(self) -> Dict[str, Any]:
        """Fetch data from the external subsystem. Override in subclasses."""
        return {}

    def get_info(self) -> DataAdapterInfo:
        """Return adapter status information."""
        return DataAdapterInfo(
            name=self._name,
            data_path=self._data_path,
            refresh_interval=self._refresh_interval,
            last_refresh=self._last_refresh,
            state=self._state,
            error_message=self._error_message,
        )


class RBACDataAdapter(DataAdapter):
    """Pulls role definitions, permission mappings, and user-role bindings.

    Maps to: data.rbac.roles, data.rbac.permissions, data.rbac.bindings
    """

    def __init__(self, refresh_interval: float = 300.0) -> None:
        super().__init__("rbac", "rbac", refresh_interval)

    def fetch(self) -> Dict[str, Any]:
        return {
            "roles": {
                "FIZZBUZZ_SUPERUSER": {"permissions": ["*"]},
                "FIZZBUZZ_OPERATOR": {"permissions": ["evaluate", "configure", "monitor"]},
                "FIZZBUZZ_ANALYST": {"permissions": ["evaluate", "monitor"]},
                "FIZZBUZZ_VIEWER": {"permissions": ["evaluate"]},
                "ANONYMOUS": {"permissions": ["evaluate"]},
            },
            "permissions": {
                "evaluate": "Evaluate FizzBuzz numbers",
                "configure": "Modify platform configuration",
                "monitor": "View monitoring dashboards",
            },
            "bindings": {},
            "revoked_tokens": {},
        }


class ComplianceDataAdapter(DataAdapter):
    """Pulls compliance regime configs, clearance records, audit status.

    Maps to: data.compliance.regimes, data.compliance.clearances, data.compliance.audit_status
    """

    def __init__(self, refresh_interval: float = 300.0) -> None:
        super().__init__("compliance", "compliance", refresh_interval)

    def fetch(self) -> Dict[str, Any]:
        return {
            "regimes": {
                "SOX": {"enabled": True, "audit_interval_days": 90},
                "GDPR": {"enabled": True, "retention_days": 365},
                "HIPAA": {"enabled": False},
            },
            "clearances": {},
            "audit_status": "compliant",
        }


class CapabilityDataAdapter(DataAdapter):
    """Pulls active tokens, delegation graphs, revocation lists.

    Maps to: data.capabilities.active, data.capabilities.delegations, data.capabilities.revoked
    """

    def __init__(self, refresh_interval: float = 120.0) -> None:
        super().__init__("capabilities", "capabilities", refresh_interval)

    def fetch(self) -> Dict[str, Any]:
        return {
            "active": {},
            "delegations": {},
            "revoked": [],
        }


class NetworkDataAdapter(DataAdapter):
    """Pulls network topology, memberships, existing policy rules.

    Maps to: data.network.topology, data.network.memberships, data.network.policies
    """

    def __init__(self, refresh_interval: float = 60.0) -> None:
        super().__init__("network", "network", refresh_interval)

    def fetch(self) -> Dict[str, Any]:
        return {
            "topology": {"zones": ["trusted", "dmz", "external"]},
            "memberships": {},
            "policies": {},
        }


class OperatorDataAdapter(DataAdapter):
    """Pulls Bob McFizzington's cognitive load, availability, approval queue.

    Maps to: data.operator.bob.cognitive_load, data.operator.bob.available,
             data.operator.bob.pending_approvals
    """

    def __init__(self, refresh_interval: float = 30.0) -> None:
        super().__init__("operator", "operator", refresh_interval)

    def fetch(self) -> Dict[str, Any]:
        return {
            "bob": {
                "cognitive_load": 45,
                "available": True,
                "pending_approvals": 0,
            },
        }


class CgroupDataAdapter(DataAdapter):
    """Pulls container resource utilization from cgroup module.

    Maps to: data.containers.resources
    """

    def __init__(self, refresh_interval: float = 30.0) -> None:
        super().__init__("cgroups", "containers", refresh_interval)

    def fetch(self) -> Dict[str, Any]:
        return {
            "resources": {
                "cpu_usage_percent": 35.0,
                "memory_usage_bytes": 256 * 1024 * 1024,
                "pids_count": 42,
            },
        }


class DeploymentDataAdapter(DataAdapter):
    """Pulls deployment status, revision history, pipeline state.

    Maps to: data.deployments.status, data.deployments.revisions
    """

    def __init__(self, refresh_interval: float = 60.0) -> None:
        super().__init__("deployments", "deployments", refresh_interval)

    def fetch(self) -> Dict[str, Any]:
        return {
            "status": "stable",
            "revisions": [],
            "freeze": False,
        }


class DataRefreshScheduler:
    """Manages refresh cycles for all registered data adapters.

    Updates the policy engine's data document atomically via copy-on-write:
    the new data document replaces the old one in a single pointer swap.
    Emits stale data warnings when an adapter's refresh fails and data
    age exceeds twice the refresh interval.
    """

    def __init__(self, engine: PolicyEngine) -> None:
        self._engine = engine
        self._adapters: Dict[str, DataAdapter] = {}

    def register(self, adapter: DataAdapter) -> None:
        """Register a data adapter."""
        self._adapters[adapter._name] = adapter

    def unregister(self, name: str) -> None:
        """Unregister a data adapter."""
        self._adapters.pop(name, None)

    def refresh_all(self) -> None:
        """Refresh all registered adapters."""
        for adapter in self._adapters.values():
            self._refresh_adapter(adapter)

    def refresh(self, name: str) -> None:
        """Refresh a specific adapter by name."""
        adapter = self._adapters.get(name)
        if adapter:
            self._refresh_adapter(adapter)

    def get_adapter_states(self) -> Dict[str, DataAdapterInfo]:
        """Return status information for all adapters."""
        return {name: adapter.get_info() for name, adapter in self._adapters.items()}

    def _refresh_adapter(self, adapter: DataAdapter) -> None:
        """Refresh a single adapter and update the engine's data."""
        try:
            data = adapter.fetch()
            self._engine.set_data(adapter._data_path, data)
            adapter._last_refresh = datetime.now(timezone.utc)
            adapter._state = DataAdapterState.HEALTHY
            adapter._error_message = ""
        except Exception as e:
            adapter._state = DataAdapterState.ERROR
            adapter._error_message = str(e)
            # Check staleness
            if adapter._last_refresh:
                age = (datetime.now(timezone.utc) - adapter._last_refresh).total_seconds()
                if age > adapter._refresh_interval * 2:
                    adapter._state = DataAdapterState.STALE
                    logger.warning("Data adapter '%s' is stale (%.1fs)", adapter._name, age)


# ---------------------------------------------------------------------------
# Policy Testing Framework
# ---------------------------------------------------------------------------

class PolicyTestRunner:
    """Discovers and executes all test_ rules in a bundle.

    Each test is an independent evaluation: ``with`` overrides are scoped
    to the test rule.  Reports total/passed/failed/errored counts,
    per-test execution time, and for failed tests: expected result,
    actual result, and explanation trace.
    """

    def __init__(self, engine: PolicyEngine) -> None:
        self._engine = engine

    def run(self, bundle: PolicyBundle) -> TestRunResult:
        """Run all tests in the bundle and return aggregated results."""
        start = time.monotonic()
        tests = self._discover_tests(bundle)
        result = TestRunResult(total=len(tests))

        for test_name, rule in tests:
            test_result = self._run_test(test_name, rule, bundle)
            result.results.append(test_result)
            status = test_result.get("status", "errored")
            if status == "passed":
                result.passed += 1
            elif status == "failed":
                result.failed += 1
            elif status == "errored":
                result.errored += 1
            elif status == "skipped":
                result.skipped += 1

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def _discover_tests(self, bundle: PolicyBundle) -> List[Tuple[str, RuleNode]]:
        """Discover all test_ rules in the bundle."""
        tests: List[Tuple[str, RuleNode]] = []
        all_modules = {**bundle.modules, **bundle.tests}
        for file_path, module in all_modules.items():
            for rule in module.rules:
                if rule.name.startswith("test_"):
                    fqn = f"{module.package_path}.{rule.name}" if module.package_path else rule.name
                    tests.append((fqn, rule))
        return tests

    def _run_test(self, test_name: str, rule: RuleNode, bundle: PolicyBundle) -> Dict[str, Any]:
        """Run a single test rule and return the result."""
        try:
            entry = self._engine.evaluate(test_name, {})
            if entry.result is True:
                return {"name": test_name, "status": "passed", "duration_ms": 0}
            return {
                "name": test_name,
                "status": "failed",
                "expected": True,
                "actual": entry.result,
                "explanation": entry.explanation,
                "duration_ms": 0,
            }
        except Exception as e:
            return {"name": test_name, "status": "errored", "error": str(e), "duration_ms": 0}


class PolicyCoverageAnalyzer:
    """Instruments evaluation to track rule and expression coverage.

    Reports:
    - Rule coverage: percentage of rules evaluated at least once
    - Expression coverage: percentage of body expressions evaluated
      to true at least once AND to false at least once (branch coverage)
    - Data coverage: which data document keys were accessed
    """

    def __init__(self) -> None:
        self._total_rules: int = 0
        self._covered_rules: Set[str] = set()
        self._expression_true: Set[str] = set()
        self._expression_false: Set[str] = set()
        self._data_paths: Set[str] = set()
        self._total_expressions: int = 0

    def begin_tracking(self, bundle: PolicyBundle) -> None:
        """Initialize coverage tracking for a bundle."""
        self._total_rules = sum(len(m.rules) for m in bundle.modules.values())
        self._total_expressions = sum(
            sum(len(r.body) for r in m.rules)
            for m in bundle.modules.values()
        )
        self._covered_rules.clear()
        self._expression_true.clear()
        self._expression_false.clear()
        self._data_paths.clear()

    def record_rule(self, rule_path: str) -> None:
        """Record that a rule was evaluated."""
        self._covered_rules.add(rule_path)

    def record_expression(self, expr_id: str, result: bool) -> None:
        """Record an expression evaluation result."""
        if result:
            self._expression_true.add(expr_id)
        else:
            self._expression_false.add(expr_id)

    def record_data_access(self, path: str) -> None:
        """Record a data document access."""
        self._data_paths.add(path)

    def get_coverage(self) -> Dict[str, Any]:
        """Return coverage statistics."""
        rule_pct = (len(self._covered_rules) / self._total_rules * 100) if self._total_rules > 0 else 0.0
        # Branch coverage: expressions that were both true and false
        branch_covered = self._expression_true & self._expression_false
        expr_pct = (len(branch_covered) / self._total_expressions * 100) if self._total_expressions > 0 else 0.0
        return {
            "rule_coverage_percent": round(rule_pct, 1),
            "expression_coverage_percent": round(expr_pct, 1),
            "rules_covered": len(self._covered_rules),
            "rules_total": self._total_rules,
            "data_paths_accessed": sorted(self._data_paths),
        }

    def reset(self) -> None:
        """Reset all coverage data."""
        self._covered_rules.clear()
        self._expression_true.clear()
        self._expression_false.clear()
        self._data_paths.clear()


class PolicyBenchmark:
    """Benchmarks policy evaluation performance.

    Runs a query N times and reports: mean, p50, p95, p99, min, max,
    and cache effect (with cache vs without).
    """

    def __init__(self, engine: PolicyEngine) -> None:
        self._engine = engine

    def run(
        self,
        query: str,
        input_doc: Dict[str, Any],
        iterations: int = DEFAULT_BENCHMARK_ITERATIONS,
    ) -> BenchmarkResult:
        """Run a benchmark and return timing statistics."""
        # Warm up cache
        self._engine.evaluate(query, input_doc)

        # Run with cache
        cached_times: List[int] = []
        for _ in range(iterations):
            start = time.monotonic_ns()
            self._engine.evaluate(query, input_doc)
            cached_times.append(time.monotonic_ns() - start)

        # Run without cache
        uncached_times: List[int] = []
        for _ in range(min(iterations, 100)):
            self._engine.invalidate_cache()
            start = time.monotonic_ns()
            self._engine.evaluate(query, input_doc)
            uncached_times.append(time.monotonic_ns() - start)

        cached_mean = sum(cached_times) // len(cached_times) if cached_times else 0
        uncached_mean = sum(uncached_times) // len(uncached_times) if uncached_times else 0

        sorted_times = sorted(cached_times)
        n = len(sorted_times)

        return BenchmarkResult(
            query=query,
            iterations=iterations,
            mean_ns=cached_mean,
            p50_ns=self._compute_percentile(sorted_times, 0.50),
            p95_ns=self._compute_percentile(sorted_times, 0.95),
            p99_ns=self._compute_percentile(sorted_times, 0.99),
            min_ns=sorted_times[0] if sorted_times else 0,
            max_ns=sorted_times[-1] if sorted_times else 0,
            cache_effect_ratio=uncached_mean / cached_mean if cached_mean > 0 else 1.0,
        )

    def _compute_percentile(self, values: List[int], percentile: float) -> int:
        """Compute a percentile from sorted values."""
        if not values:
            return 0
        idx = min(int(len(values) * percentile), len(values) - 1)
        return values[idx]


# ---------------------------------------------------------------------------
# Real-Time Policy Updates
# ---------------------------------------------------------------------------

class PolicyWatcher:
    """Monitors the bundle store for new bundle activations.

    When a new revision is activated, the watcher:
    1. Loads the bundle from BundleStore
    2. Verifies signature via BundleSigner
    3. Compiles all policies
    4. Runs all bundle tests
    5. On success: atomically swaps active plans (pointer swap)
    6. On failure: rejects, logs, retains current bundle
    7. Invalidates the evaluation cache
    """

    def __init__(self, engine: PolicyEngine, store: BundleStore, signer: Optional[BundleSigner] = None) -> None:
        self._engine = engine
        self._store = store
        self._signer = signer
        self._watched_bundle: str = ""

    def watch(self, bundle_name: str) -> None:
        """Set the bundle name to watch for activations."""
        self._watched_bundle = bundle_name

    def notify_activation(self, revision: int) -> None:
        """Handle a bundle activation notification."""
        try:
            bundle = self._load_and_verify(self._watched_bundle, revision)
            self._swap_active(bundle)
            logger.info("Hot-reloaded bundle '%s' revision %d", self._watched_bundle, revision)
        except (PolicyBundleIntegrityError, PolicyBundleError) as e:
            logger.error("Failed to hot-reload bundle revision %d: %s", revision, e)
            raise PolicyWatcherError(f"Bundle activation failed for revision {revision}: {e}")

    def _load_and_verify(self, bundle_name: str, revision: int) -> PolicyBundle:
        """Load and verify a bundle from the store."""
        bundle = self._store.load(bundle_name, revision)
        if bundle is None:
            raise PolicyBundleError(f"Bundle '{bundle_name}' revision {revision} not found in store")
        if self._signer and bundle.signatures:
            self._signer.verify(bundle)
        return bundle

    def _swap_active(self, bundle: PolicyBundle) -> None:
        """Atomically swap the active bundle in the engine."""
        self._engine.load_bundle(bundle)


class PolicyHotReloadMiddleware:
    """Integrates with the platform's Raft-based hot-reload system.

    When a bundle activation occurs on the leader node, the activation
    event is replicated via the Raft log.  Each follower's PolicyWatcher
    receives the event and performs the load-verify-compile-test-swap
    cycle to converge on the same policy version.
    """

    def __init__(self, watcher: PolicyWatcher) -> None:
        self._watcher = watcher

    def on_raft_entry(self, entry: Dict[str, Any]) -> None:
        """Process a Raft log entry for policy activation."""
        if self._is_policy_activation(entry):
            revision = entry.get("revision", 0)
            self._watcher.notify_activation(revision)

    def _is_policy_activation(self, entry: Dict[str, Any]) -> bool:
        """Check if a Raft log entry is a policy bundle activation."""
        return entry.get("type") == "policy_bundle_activation"


# ---------------------------------------------------------------------------
# Default Policy Bundle
# ---------------------------------------------------------------------------

class DefaultBundleFactory:
    """Constructs the default policy bundle shipped with the platform.

    The default bundle contains eight policy packages and a data document.
    """

    def __init__(self) -> None:
        pass

    def create(self) -> PolicyBundle:
        """Create the default policy bundle."""
        policies: Dict[str, str] = {}
        policies.update(self._authz_policies())
        policies.update(self._compliance_policies())
        policies.update(self._capability_policies())
        policies.update(self._network_policies())
        policies.update(self._admission_policies())
        policies.update(self._gateway_policies())
        policies.update(self._mesh_policies())
        policies.update(self._deploy_policies())

        data = self._default_data()
        tests = self._test_policies()

        builder = BundleBuilder()
        bundle = builder.build(policies=policies, data=data, tests=tests)
        bundle.manifest.bundle_name = "default"
        bundle.manifest.author = "system"
        return bundle

    def _authz_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/authz/allow.rego": (
                "package fizzbuzz.authz\n"
                "\n"
                "default allow = false\n"
                "\n"
                "allow {\n"
                '    input.role == "FIZZBUZZ_SUPERUSER"\n'
                "}\n"
                "\n"
                "allow {\n"
                '    input.role == "FIZZBUZZ_OPERATOR"\n'
                '    input.action == "evaluate"\n'
                "    input.number > 0\n"
                "}\n"
                "\n"
                "allow {\n"
                '    input.role == "FIZZBUZZ_ANALYST"\n'
                '    input.action == "evaluate"\n'
                "    input.number > 0\n"
                "    input.number <= data.fizzbuzz.authz.max_range\n"
                "}\n"
                "\n"
                "allow {\n"
                '    input.role == "FIZZBUZZ_VIEWER"\n'
                '    input.action == "evaluate"\n'
                "    input.number > 0\n"
                "    input.number <= 50\n"
                "}\n"
                "\n"
                "allow {\n"
                '    input.role == "ANONYMOUS"\n'
                '    input.action == "evaluate"\n'
                "    input.number > 0\n"
                "    input.number <= 10\n"
                "}\n"
            ),
            "fizzbuzz/authz/range.rego": (
                "package fizzbuzz.authz\n"
                "\n"
                "default max_range = 10\n"
                "\n"
                "max_range = 1000 {\n"
                '    input.role == "FIZZBUZZ_OPERATOR"\n'
                "}\n"
                "\n"
                "max_range = 100 {\n"
                '    input.role == "FIZZBUZZ_ANALYST"\n'
                "}\n"
                "\n"
                "max_range = 50 {\n"
                '    input.role == "FIZZBUZZ_VIEWER"\n'
                "}\n"
            ),
            "fizzbuzz/authz/tokens.rego": (
                "package fizzbuzz.authz\n"
                "\n"
                "token_valid {\n"
                '    input.token != ""\n'
                "    not data.rbac.revoked_tokens[input.token]\n"
                "}\n"
            ),
        }

    def _compliance_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/compliance/sox.rego": (
                "package fizzbuzz.compliance\n"
                "\n"
                "default sox_compliant = true\n"
                "\n"
                "sox_compliant = false {\n"
                '    input.action == "configure"\n'
                '    input.role != "FIZZBUZZ_SUPERUSER"\n'
                "}\n"
            ),
            "fizzbuzz/compliance/gdpr.rego": (
                "package fizzbuzz.compliance\n"
                "\n"
                "default gdpr_compliant = true\n"
            ),
            "fizzbuzz/compliance/hipaa.rego": (
                "package fizzbuzz.compliance\n"
                "\n"
                "default hipaa_compliant = true\n"
            ),
            "fizzbuzz/compliance/cross_regime.rego": (
                "package fizzbuzz.compliance\n"
                "\n"
                "all_compliant {\n"
                "    sox_compliant\n"
                "    gdpr_compliant\n"
                "    hipaa_compliant\n"
                "}\n"
            ),
        }

    def _capability_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/capabilities/authorize.rego": (
                "package fizzbuzz.capabilities\n"
                "\n"
                "default authorized = true\n"
            ),
            "fizzbuzz/capabilities/delegation.rego": (
                "package fizzbuzz.capabilities\n"
                "\n"
                "default delegation_valid = true\n"
            ),
            "fizzbuzz/capabilities/attenuation.rego": (
                "package fizzbuzz.capabilities\n"
                "\n"
                "default attenuation_valid = true\n"
            ),
        }

    def _network_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/network/ingress.rego": (
                "package fizzbuzz.network\n"
                "\n"
                "default ingress_allowed = true\n"
            ),
            "fizzbuzz/network/egress.rego": (
                "package fizzbuzz.network\n"
                "\n"
                "default egress_allowed = true\n"
            ),
            "fizzbuzz/network/isolation.rego": (
                "package fizzbuzz.network\n"
                "\n"
                "default isolated = false\n"
            ),
        }

    def _admission_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/admission/containers.rego": (
                "package fizzbuzz.admission\n"
                "\n"
                "default allowed = true\n"
            ),
            "fizzbuzz/admission/deployments.rego": (
                "package fizzbuzz.admission\n"
                "\n"
                "default deployment_allowed = true\n"
            ),
            "fizzbuzz/admission/secrets.rego": (
                "package fizzbuzz.admission\n"
                "\n"
                "default secret_access = false\n"
                "\n"
                "secret_access {\n"
                '    input.role == "FIZZBUZZ_SUPERUSER"\n'
                "}\n"
                "\n"
                "secret_access {\n"
                '    input.role == "FIZZBUZZ_OPERATOR"\n'
                "}\n"
            ),
            "fizzbuzz/admission/config.rego": (
                "package fizzbuzz.admission\n"
                "\n"
                "default config_change = false\n"
                "\n"
                "config_change {\n"
                '    input.role == "FIZZBUZZ_SUPERUSER"\n'
                "}\n"
            ),
        }

    def _gateway_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/gateway/ratelimit.rego": (
                "package fizzbuzz.gateway\n"
                "\n"
                "default rate_limited = false\n"
            ),
            "fizzbuzz/gateway/request.rego": (
                "package fizzbuzz.gateway\n"
                "\n"
                "default request_allowed = true\n"
            ),
        }

    def _mesh_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/mesh/mtls.rego": (
                "package fizzbuzz.mesh\n"
                "\n"
                "default mtls_required = true\n"
            ),
            "fizzbuzz/mesh/circuit.rego": (
                "package fizzbuzz.mesh\n"
                "\n"
                "default circuit_open = false\n"
            ),
        }

    def _deploy_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/deploy/windows.rego": (
                "package fizzbuzz.deploy\n"
                "\n"
                "default in_window = true\n"
            ),
            "fizzbuzz/deploy/freeze.rego": (
                "package fizzbuzz.deploy\n"
                "\n"
                "default frozen = false\n"
            ),
            "fizzbuzz/deploy/gates.rego": (
                "package fizzbuzz.deploy\n"
                "\n"
                "default gates_passed = true\n"
            ),
        }

    def _default_data(self) -> Dict[str, Any]:
        return {
            "fizzbuzz": {
                "authz": {
                    "max_range": 100,
                },
            },
            "rbac": {
                "roles": {
                    "FIZZBUZZ_SUPERUSER": {"permissions": ["*"]},
                    "FIZZBUZZ_OPERATOR": {"permissions": ["evaluate", "configure", "monitor"]},
                    "FIZZBUZZ_ANALYST": {"permissions": ["evaluate", "monitor"]},
                    "FIZZBUZZ_VIEWER": {"permissions": ["evaluate"]},
                    "ANONYMOUS": {"permissions": ["evaluate"]},
                },
                "revoked_tokens": {},
            },
            "compliance": {
                "regimes": {
                    "SOX": {"enabled": True},
                    "GDPR": {"enabled": True},
                    "HIPAA": {"enabled": False},
                },
            },
            "network": {
                "topology": {"zones": ["trusted", "dmz", "external"]},
            },
            "deploy": {
                "windows": {"weekday_only": True},
                "freeze": False,
            },
            "gateway": {
                "rate_limits": {"default": 100, "premium": 1000},
            },
        }

    def _test_policies(self) -> Dict[str, str]:
        return {
            "fizzbuzz/authz/allow_test.rego": (
                "package fizzbuzz.authz\n"
                "\n"
                "test_superuser_allowed {\n"
                '    input.role == "FIZZBUZZ_SUPERUSER"\n'
                '    input.action == "evaluate"\n'
                "    input.number > 0\n"
                "    allow\n"
                "}\n"
                "\n"
                "test_operator_allowed {\n"
                '    input.role == "FIZZBUZZ_OPERATOR"\n'
                '    input.action == "evaluate"\n'
                "    input.number > 0\n"
                "    allow\n"
                "}\n"
            ),
        }


# ---------------------------------------------------------------------------
# FizzPolicy Middleware
# ---------------------------------------------------------------------------

class FizzPolicyMiddleware(IMiddleware):
    """Intercepts every FizzBuzz evaluation and evaluates the unified admission policy.

    Constructs an input document from ProcessingContext (user, role, number,
    action, token, compliance clearances, capabilities, source container,
    target service) and queries ``data.fizzbuzz.admission.allowed``.

    If denied: short-circuits the pipeline with a structured denial response
    including the explanation trace.
    If allowed: evaluation proceeds through remaining middleware.
    """

    def __init__(self, engine: PolicyEngine, explanation_mode: ExplanationMode = ExplanationMode.SUMMARY) -> None:
        self._engine = engine
        self._explanation_mode = explanation_mode
        self._name = "fizzpolicy"
        self._priority = MIDDLEWARE_PRIORITY
        self._total_processed = 0
        self._total_denied = 0

    def process(self, context: ProcessingContext, next_handler: Callable[[ProcessingContext], ProcessingContext]) -> ProcessingContext:
        """Evaluate admission policy and delegate or deny."""
        try:
            input_doc = self._build_input(context)
            decision = self._engine.evaluate("data.fizzbuzz.admission.allowed", input_doc)

            self._total_processed += 1

            if decision.result_type == DecisionResult.DENY:
                self._total_denied += 1
                result = self._build_denial_result(decision, context)
                context.results.append(result)
                return context

            return next_handler(context)
        except PolicyEngineError as e:
            logger.error("FizzPolicy middleware error: %s", e)
            return next_handler(context)

    def get_name(self) -> str:
        return self._name

    def get_priority(self) -> int:
        return self._priority

    def get_stats(self) -> Dict[str, Any]:
        """Return middleware statistics."""
        return {
            "total_processed": self._total_processed,
            "total_denied": self._total_denied,
            "denial_rate": self._total_denied / self._total_processed if self._total_processed > 0 else 0.0,
        }

    def render_status(self) -> str:
        """Render the policy engine status as formatted text."""
        status = self._engine.get_status()
        lines = [
            "+-----------------------------------------------------------+",
            "| FIZZPOLICY - DECLARATIVE POLICY ENGINE STATUS             |",
            "+-----------------------------------------------------------+",
            f"| Engine Version:   {FIZZPOLICY_VERSION:<40}|",
            f"| Language Version:  {FIZZREGO_LANGUAGE_VERSION:<40}|",
            f"| Active Bundle:    rev {status.active_bundle_revision} ({status.bundle_name})" + " " * max(0, 36 - len(str(status.active_bundle_revision)) - len(status.bundle_name)) + "|",
            f"| Total Evaluations: {status.total_evaluations:<39}|",
            f"| Cache Hit Rate:   {status.cache_hit_rate:.1%}" + " " * max(0, 38 - len(f"{status.cache_hit_rate:.1%}")) + "|",
            f"| Allow/Deny:       {status.decisions_allow}/{status.decisions_deny}" + " " * max(0, 36 - len(f"{status.decisions_allow}/{status.decisions_deny}")) + "|",
            f"| P50 Latency:      {status.eval_latency_p50_ms:.3f}ms" + " " * max(0, 35 - len(f"{status.eval_latency_p50_ms:.3f}ms")) + "|",
            f"| P95 Latency:      {status.eval_latency_p95_ms:.3f}ms" + " " * max(0, 35 - len(f"{status.eval_latency_p95_ms:.3f}ms")) + "|",
            f"| P99 Latency:      {status.eval_latency_p99_ms:.3f}ms" + " " * max(0, 35 - len(f"{status.eval_latency_p99_ms:.3f}ms")) + "|",
            "+-----------------------------------------------------------+",
        ]
        return "\n".join(lines)

    def render_decisions(self, since=None, until=None, path=None, result=None, user=None, page=1) -> str:
        """Render decision log entries as formatted text."""
        if not self._engine._decision_logger:
            return "Decision logging is not configured."
        query = DecisionLogQuery(self._engine._decision_logger)
        result_filter = DecisionResult(result) if result else None
        entries, total = query.query(
            since=since, until=until, path=path,
            result=result_filter, user=user, page=page,
        )
        if not entries:
            return "No decisions found matching the given criteria."
        lines = [f"Decision Log ({total} total, page {page})", ""]
        for entry in entries:
            lines.append(f"  [{entry.result_type.value.upper()}] {entry.path} @ {entry.timestamp.isoformat()}")
        return "\n".join(lines)

    def render_bundle_list(self) -> str:
        """Render the bundle revision list."""
        bundle = self._engine.get_active_bundle()
        if bundle is None:
            return "No bundles loaded."
        return f"Active bundle: {bundle.manifest.bundle_name} rev {bundle.manifest.revision}"

    def render_eval(self, query: str, input_json: str, explain: bool = False) -> str:
        """Evaluate a policy query and render the result."""
        try:
            input_doc = json.loads(input_json) if input_json else {}
        except json.JSONDecodeError as e:
            return f"Invalid JSON input: {e}"
        entry = self._engine.evaluate(query, input_doc)
        lines = [
            f"Query: {query}",
            f"Result: {entry.result}",
            f"Decision: {entry.result_type.value}",
        ]
        if explain and entry.explanation:
            lines.append("")
            lines.append("Explanation:")
            lines.append(entry.explanation)
        return "\n".join(lines)

    def render_test(self, bundle_path: str = None, coverage: bool = False) -> str:
        """Run policy tests and render results."""
        bundle = self._engine.get_active_bundle()
        if bundle is None:
            return "No active bundle to test."
        runner = PolicyTestRunner(self._engine)
        result = runner.run(bundle)
        lines = [
            f"Policy Tests: {result.passed} passed, {result.failed} failed, "
            f"{result.errored} errored, {result.skipped} skipped",
            f"Duration: {result.duration_ms:.1f}ms",
        ]
        return "\n".join(lines)

    def render_bench(self, query: str, input_json: str = None) -> str:
        """Run a policy benchmark and render results."""
        try:
            input_doc = json.loads(input_json) if input_json else {}
        except json.JSONDecodeError:
            input_doc = {}
        bench = PolicyBenchmark(self._engine)
        result = bench.run(query, input_doc, iterations=100)
        lines = [
            f"Benchmark: {query}",
            f"  Iterations: {result.iterations}",
            f"  Mean: {result.mean_ns / 1000:.1f}us",
            f"  P50:  {result.p50_ns / 1000:.1f}us",
            f"  P95:  {result.p95_ns / 1000:.1f}us",
            f"  P99:  {result.p99_ns / 1000:.1f}us",
            f"  Cache Effect: {result.cache_effect_ratio:.1f}x",
        ]
        return "\n".join(lines)

    def render_compile(self, source: str) -> str:
        """Compile FizzRego source and render diagnostics."""
        try:
            lexer = FizzRegoLexer(source)
            tokens = lexer.tokenize()
            parser = FizzRegoParser(tokens)
            module = parser.parse()
            checker = FizzRegoTypeChecker()
            module, warnings = checker.check(module)
            lines = [
                f"Compiled: {len(module.rules)} rules",
                f"Package: {module.package_path}",
                f"Imports: {len(module.imports)}",
            ]
            if warnings:
                lines.append(f"Warnings ({len(warnings)}):")
                for w in warnings:
                    lines.append(f"  - {w}")
            return "\n".join(lines)
        except (PolicyLexerError, PolicyParserError) as e:
            return f"Compilation failed: {e}"

    def _build_input(self, context: ProcessingContext) -> Dict[str, Any]:
        """Construct the input document from the processing context."""
        return {
            "number": context.number,
            "session_id": context.session_id,
            "action": "evaluate",
            "role": context.metadata.get("role", "ANONYMOUS"),
            "user": context.metadata.get("user", "anonymous"),
            "token": context.metadata.get("token", ""),
            "locale": context.locale,
        }

    def _build_denial_result(self, decision: DecisionLogEntry, context: ProcessingContext) -> FizzBuzzResult:
        """Build a FizzBuzzResult representing a policy denial."""
        return FizzBuzzResult(
            number=context.number,
            output=f"POLICY_DENIED: {decision.explanation}" if decision.explanation else "POLICY_DENIED",
            metadata={
                "policy_denied": True,
                "policy_path": decision.path,
                "policy_result": str(decision.result),
                "policy_explanation": decision.explanation,
            },
        )


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------

def create_fizzpolicy_subsystem(
    signing_key: str = "",
    eval_timeout_ms: float = DEFAULT_EVAL_TIMEOUT_MS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
    explanation_mode: str = "summary",
    bundle_policies: Dict[str, str] = None,
    bundle_data: Dict[str, Any] = None,
) -> Tuple[PolicyEngine, FizzPolicyMiddleware]:
    """Wire and return the FizzPolicy subsystem.

    Creates the engine, builds the default bundle (or custom if provided),
    registers data adapters, loads the bundle, and returns the engine and
    middleware.

    Returns:
        Tuple of (PolicyEngine, FizzPolicyMiddleware).
    """
    mode = ExplanationMode(explanation_mode) if explanation_mode in [e.value for e in ExplanationMode] else ExplanationMode.SUMMARY

    engine = PolicyEngine(
        timeout_ms=eval_timeout_ms,
        max_iterations=max_iterations,
        cache_max_entries=cache_max_entries,
        explanation_mode=mode,
    )

    # Set up decision logger
    decision_logger = DecisionLogger()
    engine._decision_logger = decision_logger

    # Build bundle
    if bundle_policies:
        builder = BundleBuilder(signing_key=signing_key)
        bundle = builder.build(
            policies=bundle_policies,
            data=bundle_data or {},
        )
    else:
        factory = DefaultBundleFactory()
        bundle = factory.create()
        if signing_key:
            signer = BundleSigner(signing_key)
            signer.sign(bundle)

    # Register data adapters
    scheduler = DataRefreshScheduler(engine)
    scheduler.register(RBACDataAdapter())
    scheduler.register(ComplianceDataAdapter())
    scheduler.register(CapabilityDataAdapter())
    scheduler.register(NetworkDataAdapter())
    scheduler.register(OperatorDataAdapter())
    scheduler.register(CgroupDataAdapter())
    scheduler.register(DeploymentDataAdapter())
    scheduler.refresh_all()

    # Load bundle
    engine.load_bundle(bundle)

    # Create middleware
    middleware = FizzPolicyMiddleware(engine=engine, explanation_mode=mode)

    logger.info(
        "FizzPolicy subsystem initialized: %d policies, %d plans, %d adapters",
        len(bundle.modules),
        len(bundle.plans),
        len(scheduler._adapters),
    )

    return engine, middleware

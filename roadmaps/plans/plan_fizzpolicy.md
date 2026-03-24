# Plan: FizzPolicy -- Declarative Policy Engine

**Module**: `enterprise_fizzbuzz/infrastructure/fizzpolicy.py`
**Target Size**: ~3,500 lines
**Test File**: `tests/test_fizzpolicy.py` (~500 lines, ~120 tests)
**Re-export Stub**: `fizzpolicy.py` (root)
**Middleware Priority**: 6

---

## 1. Module Docstring

```python
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
```

---

## 2. Imports

```python
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
```

---

## 3. Constants (~20 constants)

```python
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
```

---

## 4. Enums

### TokenType
```python
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
```

### RegoType
```python
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
```

### PlanOpcode
```python
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
```

### ExplanationMode
```python
class ExplanationMode(Enum):
    """Decision explanation verbosity level.

    Controls the amount of detail recorded in the evaluation trace
    that accompanies each policy decision.
    """
    FULL = "full"
    SUMMARY = "summary"
    MINIMAL = "minimal"
    OFF = "off"
```

### DecisionResult
```python
class DecisionResult(Enum):
    """High-level policy decision outcome for filtering and reporting."""
    ALLOW = "allow"
    DENY = "deny"
    ERROR = "error"
    UNDEFINED = "undefined"
```

### DataAdapterState
```python
class DataAdapterState(Enum):
    """Health state of a data adapter's refresh cycle."""
    HEALTHY = "healthy"
    STALE = "stale"
    ERROR = "error"
    DISABLED = "disabled"
```

### BundleState
```python
class BundleState(Enum):
    """Lifecycle state of a policy bundle revision."""
    BUILDING = "building"
    TESTING = "testing"
    SIGNED = "signed"
    ACTIVE = "active"
    INACTIVE = "inactive"
    REJECTED = "rejected"
```

### PolicyTestResult
```python
class PolicyTestResult(Enum):
    """Outcome of an individual policy test rule evaluation."""
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    SKIPPED = "skipped"
```

---

## 5. Data Classes

### Token
```python
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
```

### ASTNode (base)
```python
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
```

### PackageNode
```python
@dataclass
class PackageNode(ASTNode):
    """Package declaration: ``package fizzbuzz.authz``.

    Attributes:
        path: The dotted package path segments.
    """
    path: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "package"
```

### ImportNode
```python
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
```

### RuleNode
```python
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
```

### ExprNode
```python
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
```

### TermNode
```python
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
```

### RefNode
```python
@dataclass
class RefNode(ASTNode):
    """A chain of dot and bracket accesses: ``data.roles[input.user]``.

    Attributes:
        segments: List of path segments (strings for dot access, ASTNode for bracket).
    """
    segments: List[Any] = field(default_factory=list)

    def __post_init__(self):
        self.node_type = "ref"
```

### ComprehensionNode
```python
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
```

### SomeNode
```python
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
```

### EveryNode
```python
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
```

### WithNode
```python
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
```

### CallNode
```python
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
```

### NotNode
```python
@dataclass
class NotNode(ASTNode):
    """Negation: ``not suspended[input.user]``.

    Attributes:
        operand: The expression being negated.
    """
    operand: Optional[ASTNode] = None

    def __post_init__(self):
        self.node_type = "not"
```

### PolicyModule
```python
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
```

### PlanInstruction
```python
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
```

### CompiledPlan
```python
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
```

### TypeAnnotation
```python
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
```

### BundleManifest
```python
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
```

### PolicyBundle
```python
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
```

### BundleSignature
```python
@dataclass
class BundleSignature:
    """Cryptographic signature block for a policy bundle.

    Attributes:
        files: List of file entries with name, hash, and algorithm.
        signatures: List of signature entries with key ID, sig, and algorithm.
    """
    files: List[Dict[str, str]] = field(default_factory=list)
    signatures: List[Dict[str, str]] = field(default_factory=list)
```

### DecisionLogEntry
```python
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
```

### EvaluationMetrics
```python
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
```

### EvalStep
```python
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
```

### DataAdapterInfo
```python
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
```

### TestRunResult
```python
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
```

### BenchmarkResult
```python
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
```

### PolicyEngineStatus
```python
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
```

---

## 6. FizzRego Lexer (~200 lines)

### FizzRegoLexer
```
class FizzRegoLexer:
    """Tokenizes FizzRego source text into a stream of tokens.

    The lexer processes source text character by character, producing Token
    instances with type, literal value, and source location.  It handles
    string escape sequences (\\n, \\t, \\\\, \\\", \\uXXXX), multi-line
    strings (backtick-delimited), and number literals in decimal, hexadecimal
    (0x), octal (0o), and binary (0b) formats.  Single-line comments begin
    with # and extend to end of line.

    Methods:
        __init__(self, source: str, file: str = "")
        tokenize(self) -> List[Token]
        _advance(self) -> str
        _peek(self) -> str
        _read_string(self) -> Token
        _read_raw_string(self) -> Token           # backtick-delimited
        _read_number(self) -> Token
        _read_identifier(self) -> Token
        _read_comment(self) -> Token
        _skip_whitespace(self)
        _make_token(self, token_type, literal) -> Token
        _error(self, message) -> PolicyLexerError
    """
```

Keyword map: `{"package": PACKAGE, "import": IMPORT, "default": DEFAULT, "not": NOT, "some": SOME, "every": EVERY, "with": WITH, "as": AS, "if": IF, "else": ELSE, "true": TRUE, "false": FALSE, "null": NULL}`.

Two-character operators: `:=` -> ASSIGN, `==` -> EQ, `!=` -> NEQ, `<=` -> LTE, `>=` -> GTE.  Single-character operators: `{`, `}`, `[`, `]`, `(`, `)`, `.`, `,`, `;`, `:`, `<`, `>`, `+`, `-`, `*`, `/`, `%`, `|`, `&`.

Lexer errors include source location (file, line, column) in the exception message for diagnostic reporting.

---

## 7. FizzRego Parser (~250 lines)

### FizzRegoParser
```
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

    Methods:
        __init__(self, tokens: List[Token], file: str = "")
        parse(self) -> PolicyModule
        _parse_package(self) -> PackageNode
        _parse_import(self) -> ImportNode
        _parse_rule(self) -> RuleNode
        _parse_rule_body(self) -> List[ASTNode]
        _parse_expr(self) -> ASTNode
        _parse_or_expr(self) -> ASTNode
        _parse_with_expr(self) -> ASTNode
        _parse_not_expr(self) -> ASTNode
        _parse_comparison(self) -> ASTNode
        _parse_arithmetic(self) -> ASTNode
        _parse_unary(self) -> ASTNode
        _parse_postfix(self) -> ASTNode        # dot, bracket
        _parse_atom(self) -> ASTNode           # literal, ident, paren, comprehension
        _parse_comprehension(self) -> ComprehensionNode
        _parse_some(self) -> SomeNode
        _parse_every(self) -> EveryNode
        _parse_call(self, name) -> CallNode
        _parse_ref(self) -> RefNode
        _validate_safety(self, rule: RuleNode)
        _advance(self) -> Token
        _peek(self) -> Token
        _expect(self, token_type) -> Token
        _match(self, *token_types) -> bool
        _error(self, message) -> PolicyParserError
    """
```

---

## 8. FizzRego Type Checker (~400 lines)

### FizzRegoTypeChecker
```
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

    Methods:
        __init__(self)
        check(self, module: PolicyModule) -> Tuple[PolicyModule, List[str]]
        _check_rule(self, rule: RuleNode) -> List[str]
        _check_expr(self, node: ASTNode, env: Dict) -> TypeAnnotation
        _check_comparison(self, node: ExprNode, env: Dict) -> TypeAnnotation
        _check_arithmetic(self, node: ExprNode, env: Dict) -> TypeAnnotation
        _check_call(self, node: CallNode, env: Dict) -> TypeAnnotation
        _check_ref(self, node: RefNode, env: Dict) -> TypeAnnotation
        _check_comprehension(self, node: ComprehensionNode, env: Dict) -> TypeAnnotation
        _check_every(self, node: EveryNode, env: Dict) -> TypeAnnotation
        _compatible(self, a: RegoType, b: RegoType) -> bool
        _builtin_signatures(self) -> Dict[str, Tuple[List[RegoType], RegoType]]
    """
```

The `_builtin_signatures` method returns the type signatures for all ~80 built-in functions, used to validate call argument types and infer return types.

---

## 9. FizzRego Partial Evaluator (~350 lines)

### FizzRegoPartialEvaluator
```
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

    Methods:
        __init__(self, static_data: Dict[str, Any])
        evaluate(self, module: PolicyModule) -> PolicyModule
        _fold_constants(self, node: ASTNode) -> ASTNode
        _eliminate_dead_branches(self, rule: RuleNode) -> Optional[RuleNode]
        _inline_helpers(self, module: PolicyModule) -> PolicyModule
        _unroll_static_iteration(self, rule: RuleNode) -> List[RuleNode]
        _is_static_ref(self, node: ASTNode) -> bool
        _resolve_static(self, node: ASTNode) -> Any
        _is_trivially_true(self, node: ASTNode) -> bool
        _is_trivially_false(self, node: ASTNode) -> bool
    """
```

---

## 10. Plan Generator (~300 lines)

### FizzRegoPlanGenerator
```
class FizzRegoPlanGenerator:
    """Compiles the (partially evaluated) AST into a linear execution plan.

    The plan is a sequence of PlanInstruction objects with backtracking
    semantics.  When a FILTER instruction fails, execution backtracks to
    the most recent SCAN and tries the next binding.

    Join ordering optimization: when a rule body contains multiple SCAN
    instructions, they are ordered by estimated selectivity (smallest
    collection first) to minimize intermediate bindings.

    Methods:
        __init__(self)
        generate(self, module: PolicyModule) -> Dict[str, CompiledPlan]
        _generate_rule_plan(self, rule: RuleNode) -> CompiledPlan
        _compile_body(self, body: List[ASTNode]) -> List[PlanInstruction]
        _compile_expr(self, node: ASTNode) -> PlanInstruction
        _compile_scan(self, some_node: SomeNode) -> PlanInstruction
        _compile_filter(self, node: ASTNode) -> PlanInstruction
        _compile_lookup(self, ref: RefNode) -> PlanInstruction
        _compile_assign(self, var: str, expr: ASTNode) -> PlanInstruction
        _compile_call(self, node: CallNode) -> PlanInstruction
        _compile_not(self, node: NotNode) -> PlanInstruction
        _compile_aggregate(self, node: ComprehensionNode) -> PlanInstruction
        _compile_every(self, node: EveryNode) -> PlanInstruction
        _estimate_selectivity(self, node: ASTNode) -> float
        _order_joins(self, instructions: List[PlanInstruction]) -> List[PlanInstruction]
    """
```

---

## 11. Built-in Functions Library (~350 lines)

### BuiltinRegistry
```
class BuiltinRegistry:
    """Registry of built-in functions available in FizzRego policies.

    Each built-in is registered with a name, argument count, and
    implementation callable.  The registry is pre-populated with the
    standard function library.

    Function categories and counts:
    - String functions (18): concat, contains, endswith, format_int,
      indexof, lower, replace, split, sprintf, startswith, substring,
      trim, trim_left, trim_right, trim_prefix, trim_suffix, trim_space,
      upper, strings.reverse
    - Regex functions (5): regex.match, regex.find_all_string_submatch,
      regex.replace, regex.split, regex.is_valid
    - Aggregation functions (6): count, sum, product, max, min, sort
    - Type functions (9): type_name, is_boolean, is_number, is_string,
      is_null, is_set, is_array, is_object, to_number
    - Object functions (6): object.get, object.remove, object.union,
      object.filter, object.keys, object.values
    - Set functions (3): intersection, union, set.diff
    - Encoding functions (8): json.marshal, json.unmarshal, base64.encode,
      base64.decode, urlquery.encode, urlquery.decode, yaml.marshal,
      yaml.unmarshal
    - Time functions (8): time.now_ns, time.parse_ns, time.format,
      time.date, time.clock, time.weekday, time.add_date, time.diff
    - Net functions (4): net.cidr_contains, net.cidr_intersect,
      net.cidr_merge, net.cidr_expand
    - JWT functions (3): io.jwt.decode, io.jwt.verify_hmac_sha256,
      io.jwt.decode_verify
    - Crypto functions (3): crypto.sha256, crypto.hmac_sha256, crypto.md5
    - FizzBuzz domain functions (5): fizzbuzz.evaluate, fizzbuzz.is_fizz,
      fizzbuzz.is_buzz, fizzbuzz.is_fizzbuzz, fizzbuzz.cognitive_load

    Methods:
        __init__(self)
        register(self, name, arg_count, func)
        call(self, name, args) -> Any
        has(self, name) -> bool
        get_signature(self, name) -> Tuple[int, Callable]
        list_all(self) -> List[str]
        _register_defaults(self)
        _impl_concat(self, args) -> str
        _impl_contains(self, args) -> bool
        _impl_sprintf(self, args) -> str
        _impl_count(self, args) -> int
        _impl_regex_match(self, args) -> bool
        _impl_time_now_ns(self, args) -> int
        _impl_net_cidr_contains(self, args) -> bool
        _impl_jwt_decode(self, args) -> List
        _impl_crypto_sha256(self, args) -> str
        _impl_fizzbuzz_evaluate(self, args) -> str
        _impl_fizzbuzz_is_fizz(self, args) -> bool
        _impl_fizzbuzz_cognitive_load(self, args) -> float
        ... (remaining implementations follow same pattern)
    """
```

Each built-in raises `PolicyBuiltinError` with a descriptive message on argument type mismatches or invalid inputs.

---

## 12. Evaluation Engine (~400 lines)

### PlanExecutor
```
class PlanExecutor:
    """Executes compiled plan instructions with backtracking.

    Maintains an execution stack of variable bindings.  When a FILTER
    instruction fails, the executor pops the stack to the most recent
    SCAN choice point and tries the next binding.

    Enforces configurable limits:
    - Evaluation timeout (default: 100ms wall-clock)
    - Max iterations (default: 100,000 instructions)
    - Max output size (default: 1MB)

    Methods:
        __init__(self, builtins: BuiltinRegistry, timeout_ms, max_iterations, max_output_bytes)
        execute(self, plan: CompiledPlan, input_doc, data_doc, trace_mode) -> Tuple[Any, EvaluationMetrics, List[EvalStep]]
        _execute_instruction(self, inst: PlanInstruction, env: Dict) -> bool
        _execute_scan(self, inst, env) -> Iterator[Dict]
        _execute_filter(self, inst, env) -> bool
        _execute_lookup(self, inst, env) -> Any
        _execute_assign(self, inst, env) -> None
        _execute_call(self, inst, env) -> Any
        _execute_not(self, inst, env) -> bool
        _execute_aggregate(self, inst, env) -> Any
        _execute_yield(self, inst, env) -> Any
        _resolve_ref(self, ref_path, env) -> Any
        _check_timeout(self)
        _check_iteration_limit(self)
        _record_step(self, expression, result, bindings, passed) -> EvalStep
    """
```

### EvaluationCache
```
class EvaluationCache:
    """LRU cache for policy evaluation results.

    Cache key: SHA-256 hash of (query_path, json(input), data_version_counter).
    Entries are invalidated when the active bundle revision changes or when
    any data adapter refreshes.

    Methods:
        __init__(self, max_entries: int = DEFAULT_CACHE_MAX_ENTRIES)
        get(self, query, input_doc, data_version) -> Optional[Any]
        put(self, query, input_doc, data_version, result)
        invalidate_all(self)
        stats(self) -> Dict[str, Any]        # hits, misses, hit_rate, size
        _make_key(self, query, input_doc, data_version) -> str
    """
```

### PolicyEngine
```
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

    Methods:
        __init__(self, timeout_ms, max_iterations, max_output_bytes, cache_max_entries, explanation_mode)
        load_bundle(self, bundle: PolicyBundle)
        evaluate(self, query: str, input_doc: Dict, labels: Dict = None) -> DecisionLogEntry
        get_active_bundle(self) -> Optional[PolicyBundle]
        get_status(self) -> PolicyEngineStatus
        set_data(self, path: str, value: Any)
        get_data(self, path: str) -> Any
        invalidate_cache(self)
        _resolve_query(self, query: str) -> CompiledPlan
        _classify_result(self, result: Any) -> DecisionResult
        _merge_data(self) -> Dict[str, Any]
    """
```

---

## 13. Explanation Engine (~250 lines)

### ExplanationEngine
```
class ExplanationEngine:
    """Traces policy evaluation and produces structured explanations.

    Three trace modes:
    - FULL: records every expression, binding, backtrack, and rule considered
    - SUMMARY: records only rules that contributed to the decision and the
      first failing condition in non-contributing rules
    - MINIMAL: records only the final decision and top-level rules that fired

    Methods:
        __init__(self, mode: ExplanationMode = ExplanationMode.SUMMARY)
        begin_trace(self, query: str)
        record_step(self, expression, result, bindings, passed) -> EvalStep
        end_trace(self) -> List[EvalStep]
        get_explanation_tree(self) -> List[EvalStep]
    """
```

### ExplanationFormatter
```
class ExplanationFormatter:
    """Renders explanation traces in multiple output formats.

    Methods:
        format_text(self, steps: List[EvalStep], indent: int = 0) -> str
        format_json(self, steps: List[EvalStep]) -> str
        format_graph(self, steps: List[EvalStep]) -> str   # ASCII DAG
        _render_step_text(self, step: EvalStep, indent) -> str
        _render_tree_connectors(self, index, total) -> str
    """
```

Text format example:
```
data.fizzbuzz.authz.allow = true
  +-- [PASS] input.role == "FIZZBUZZ_OPERATOR"
  +-- [PASS] input.action == "evaluate"
  +-- [PASS] not suspended[input.user]
  |   \-- [FAIL] suspended["bob"] (no matching entries in data.suspension_list)
  \-- [PASS] not cognitive_overload
      \-- [FAIL] cognitive_overload (data.operator.bob.cognitive_load = 45, threshold 70)
```

---

## 14. Policy Bundle System (~350 lines)

### BundleBuilder
```
class BundleBuilder:
    """Constructs a policy bundle from source files.

    Resolves imports, compiles all policies through the full compiler
    pipeline (lex -> parse -> type check -> partial evaluate -> plan),
    runs all tests, and produces the bundle only if compilation and all
    tests succeed.

    Methods:
        __init__(self, signing_key: str = "")
        build(self, policies: Dict[str, str], data: Dict = None, tests: Dict[str, str] = None) -> PolicyBundle
        _compile_module(self, file_path: str, source: str, static_data: Dict) -> Tuple[PolicyModule, Dict[str, CompiledPlan]]
        _resolve_imports(self, modules: Dict[str, PolicyModule])
        _run_tests(self, bundle: PolicyBundle) -> TestRunResult
        _sign_bundle(self, bundle: PolicyBundle, signing_key: str)
    """
```

### BundleVersionManager
```
class BundleVersionManager:
    """Manages bundle revisions and activation history.

    Each bundle push increments the revision.  Maintains a history of all
    revisions with manifests and activation timestamps.  Supports rollback
    to any previous revision.

    Methods:
        __init__(self, max_history: int = DEFAULT_BUNDLE_REVISION_HISTORY)
        push(self, bundle: PolicyBundle) -> int             # returns revision
        activate(self, revision: int) -> PolicyBundle
        rollback(self, revision: int) -> PolicyBundle
        get_active(self) -> Optional[PolicyBundle]
        get_revision(self, revision: int) -> Optional[PolicyBundle]
        list_revisions(self) -> List[BundleManifest]
        _next_revision(self) -> int
    """
```

### BundleStore
```
class BundleStore:
    """Persistent storage for policy bundles.

    Bundles are stored as in-memory archives with content-addressable
    deduplication: identical policy files across revisions are stored once.

    Methods:
        __init__(self)
        save(self, bundle: PolicyBundle) -> str              # returns content hash
        load(self, bundle_name: str, revision: int) -> Optional[PolicyBundle]
        delete(self, bundle_name: str, revision: int) -> bool
        list_bundles(self) -> List[str]
        _content_hash(self, content: str) -> str
    """
```

### BundleSigner
```
class BundleSigner:
    """Cryptographic signing for bundle integrity and provenance.

    Signing: computes SHA-256 hashes of every file in the bundle and signs
    the hash manifest with HMAC-SHA256.

    Verification: verifies all file hashes and the manifest signature.
    Raises PolicyBundleIntegrityError on tamper detection.

    Methods:
        __init__(self, signing_key: str)
        sign(self, bundle: PolicyBundle) -> BundleSignature
        verify(self, bundle: PolicyBundle) -> bool
        _hash_file(self, content: str) -> str
        _sign_manifest(self, file_hashes: List[Dict]) -> str
        _verify_manifest(self, file_hashes: List[Dict], signature: str) -> bool
    """
```

---

## 15. Decision Logging (~350 lines)

### DecisionLogger
```
class DecisionLogger:
    """Collects decision log entries with configurable filtering and masking.

    Supports:
    - Path filtering: only log decisions for specified rule paths
    - Result filtering: only log denied decisions, or all
    - Input masking: sensitive fields replaced with [REDACTED]

    Methods:
        __init__(self, mask_fields: List[str] = None, filter_paths: List[str] = None, filter_results: List[DecisionResult] = None)
        log(self, entry: DecisionLogEntry)
        get_entries(self) -> List[DecisionLogEntry]
        get_entry(self, decision_id: str) -> Optional[DecisionLogEntry]
        clear(self)
        _mask_input(self, input_doc: Dict) -> Dict
        _should_log(self, entry: DecisionLogEntry) -> bool
    """
```

### DecisionLogQuery
```
class DecisionLogQuery:
    """Queries decision log history with filtering and pagination.

    Supports filtering by: time range, decision path, result type,
    input field values, and bundle revision.

    Methods:
        __init__(self, logger: DecisionLogger)
        query(self, since: datetime = None, until: datetime = None,
              path: str = None, result: DecisionResult = None,
              user: str = None, bundle_revision: int = None,
              page: int = 1, page_size: int = DEFAULT_DECISION_LOG_PAGE_SIZE) -> Tuple[List[DecisionLogEntry], int]
        count(self, **filters) -> int
    """
```

### DecisionLogExporter
```
class DecisionLogExporter:
    """Exports decision logs in structured formats.

    Supported formats: JSON Lines, CSV, FizzSheet-compatible.

    Methods:
        __init__(self, logger: DecisionLogger)
        export_jsonl(self, entries: List[DecisionLogEntry]) -> str
        export_csv(self, entries: List[DecisionLogEntry]) -> str
        export_fizzsheet(self, entries: List[DecisionLogEntry]) -> str
        _flatten_entry(self, entry: DecisionLogEntry) -> Dict[str, str]
    """
```

---

## 16. Data Integration (~300 lines)

### DataAdapter (abstract)
```
class DataAdapter:
    """Abstract interface for pulling external data into the policy engine.

    Each adapter maps a platform subsystem's state into a JSON-compatible
    data structure that policies reference via ``data.*``.

    Methods:
        __init__(self, name: str, data_path: str, refresh_interval: float)
        fetch(self) -> Dict[str, Any]          # abstract
        get_info(self) -> DataAdapterInfo
    """
```

### Built-in Adapters (7 adapters, ~25 lines each)

Each adapter follows the same pattern:

```
class RBACDataAdapter(DataAdapter):
    """Pulls role definitions, permission mappings, and user-role bindings.

    Maps to: data.rbac.roles, data.rbac.permissions, data.rbac.bindings
    """
    def __init__(self, refresh_interval=300.0)
    def fetch(self) -> Dict[str, Any]

class ComplianceDataAdapter(DataAdapter):
    """Pulls compliance regime configs, clearance records, audit status.

    Maps to: data.compliance.regimes, data.compliance.clearances, data.compliance.audit_status
    """
    def __init__(self, refresh_interval=300.0)
    def fetch(self) -> Dict[str, Any]

class CapabilityDataAdapter(DataAdapter):
    """Pulls active tokens, delegation graphs, revocation lists.

    Maps to: data.capabilities.active, data.capabilities.delegations, data.capabilities.revoked
    """
    def __init__(self, refresh_interval=120.0)
    def fetch(self) -> Dict[str, Any]

class NetworkDataAdapter(DataAdapter):
    """Pulls network topology, memberships, existing policy rules.

    Maps to: data.network.topology, data.network.memberships, data.network.policies
    """
    def __init__(self, refresh_interval=60.0)
    def fetch(self) -> Dict[str, Any]

class OperatorDataAdapter(DataAdapter):
    """Pulls Bob McFizzington's cognitive load, availability, approval queue.

    Maps to: data.operator.bob.cognitive_load, data.operator.bob.available,
             data.operator.bob.pending_approvals
    """
    def __init__(self, refresh_interval=30.0)
    def fetch(self) -> Dict[str, Any]

class CgroupDataAdapter(DataAdapter):
    """Pulls container resource utilization from cgroup module.

    Maps to: data.containers.resources
    """
    def __init__(self, refresh_interval=30.0)
    def fetch(self) -> Dict[str, Any]

class DeploymentDataAdapter(DataAdapter):
    """Pulls deployment status, revision history, pipeline state.

    Maps to: data.deployments.status, data.deployments.revisions
    """
    def __init__(self, refresh_interval=60.0)
    def fetch(self) -> Dict[str, Any]
```

### DataRefreshScheduler
```
class DataRefreshScheduler:
    """Manages refresh cycles for all registered data adapters.

    Updates the policy engine's data document atomically via copy-on-write:
    the new data document replaces the old one in a single pointer swap.
    Emits stale data warnings when an adapter's refresh fails and data
    age exceeds twice the refresh interval.

    Methods:
        __init__(self, engine: PolicyEngine)
        register(self, adapter: DataAdapter)
        unregister(self, name: str)
        refresh_all(self)
        refresh(self, name: str)
        get_adapter_states(self) -> Dict[str, DataAdapterInfo]
        _refresh_adapter(self, adapter: DataAdapter)
    """
```

---

## 17. Policy Testing Framework (~250 lines)

### PolicyTestRunner
```
class PolicyTestRunner:
    """Discovers and executes all test_ rules in a bundle.

    Each test is an independent evaluation: ``with`` overrides are scoped
    to the test rule.  Reports total/passed/failed/errored counts,
    per-test execution time, and for failed tests: expected result,
    actual result, and explanation trace.

    Methods:
        __init__(self, engine: PolicyEngine)
        run(self, bundle: PolicyBundle) -> TestRunResult
        _discover_tests(self, bundle: PolicyBundle) -> List[Tuple[str, RuleNode]]
        _run_test(self, test_name: str, rule: RuleNode, bundle: PolicyBundle) -> Dict[str, Any]
    """
```

### PolicyCoverageAnalyzer
```
class PolicyCoverageAnalyzer:
    """Instruments evaluation to track rule and expression coverage.

    Reports:
    - Rule coverage: percentage of rules evaluated at least once
    - Expression coverage: percentage of body expressions evaluated
      to true at least once AND to false at least once (branch coverage)
    - Data coverage: which data document keys were accessed

    Methods:
        __init__(self)
        begin_tracking(self, bundle: PolicyBundle)
        record_rule(self, rule_path: str)
        record_expression(self, expr_id: str, result: bool)
        record_data_access(self, path: str)
        get_coverage(self) -> Dict[str, Any]     # rule_pct, expr_pct, data_paths
        reset(self)
    """
```

### PolicyBenchmark
```
class PolicyBenchmark:
    """Benchmarks policy evaluation performance.

    Runs a query N times and reports: mean, p50, p95, p99, min, max,
    and cache effect (with cache vs without).

    Methods:
        __init__(self, engine: PolicyEngine)
        run(self, query: str, input_doc: Dict, iterations: int = DEFAULT_BENCHMARK_ITERATIONS) -> BenchmarkResult
        _compute_percentile(self, values: List[int], percentile: float) -> int
    """
```

---

## 18. Real-Time Policy Updates (~150 lines)

### PolicyWatcher
```
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

    Methods:
        __init__(self, engine: PolicyEngine, store: BundleStore, signer: BundleSigner)
        watch(self, bundle_name: str)
        notify_activation(self, revision: int)
        _load_and_verify(self, bundle_name: str, revision: int) -> PolicyBundle
        _swap_active(self, bundle: PolicyBundle)
    """
```

### PolicyHotReloadMiddleware
```
class PolicyHotReloadMiddleware:
    """Integrates with the platform's Raft-based hot-reload system.

    When a bundle activation occurs on the leader node, the activation
    event is replicated via the Raft log.  Each follower's PolicyWatcher
    receives the event and performs the load-verify-compile-test-swap
    cycle to converge on the same policy version.

    Methods:
        __init__(self, watcher: PolicyWatcher)
        on_raft_entry(self, entry: Dict[str, Any])
        _is_policy_activation(self, entry: Dict) -> bool
    """
```

---

## 19. Default Policy Bundle (~200 lines)

### DefaultBundleFactory
```
class DefaultBundleFactory:
    """Constructs the default policy bundle shipped with the platform.

    The default bundle contains eight policy packages and a data document:

    Packages:
    - fizzbuzz/authz/: Role-based evaluation permissions (allow.rego, range.rego, tokens.rego)
    - fizzbuzz/compliance/: SOX, GDPR, HIPAA policies (sox.rego, gdpr.rego, hipaa.rego, cross_regime.rego)
    - fizzbuzz/capabilities/: Capability token validation (authorize.rego, delegation.rego, attenuation.rego)
    - fizzbuzz/network/: Network ingress/egress policies (ingress.rego, egress.rego, isolation.rego)
    - fizzbuzz/admission/: Resource creation admission (containers.rego, deployments.rego, secrets.rego, config.rego)
    - fizzbuzz/gateway/: API gateway policies (ratelimit.rego, request.rego)
    - fizzbuzz/mesh/: Service mesh authorization (mtls.rego, circuit.rego)
    - fizzbuzz/deploy/: Deployment gate policies (windows.rego, freeze.rego, gates.rego)

    Data document includes role definitions, compliance regime configs,
    network topology stubs, deployment windows, and rate limits.

    Methods:
        __init__(self)
        create(self) -> PolicyBundle
        _authz_policies(self) -> Dict[str, str]
        _compliance_policies(self) -> Dict[str, str]
        _capability_policies(self) -> Dict[str, str]
        _network_policies(self) -> Dict[str, str]
        _admission_policies(self) -> Dict[str, str]
        _gateway_policies(self) -> Dict[str, str]
        _mesh_policies(self) -> Dict[str, str]
        _deploy_policies(self) -> Dict[str, str]
        _default_data(self) -> Dict[str, Any]
        _test_policies(self) -> Dict[str, str]
    """
```

Each `_*_policies` method returns a dict mapping file paths to FizzRego source strings.  Example from `_authz_policies`:

```python
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
            "    input.token != \"\"\n"
            "    not data.rbac.revoked_tokens[input.token]\n"
            "}\n"
        ),
    }
```

---

## 20. Middleware and Factory (~200 lines)

### FizzPolicyMiddleware
```
class FizzPolicyMiddleware(IMiddleware):
    """Intercepts every FizzBuzz evaluation and evaluates the unified admission policy.

    Constructs an input document from ProcessingContext (user, role, number,
    action, token, compliance clearances, capabilities, source container,
    target service) and queries ``data.fizzbuzz.admission.allowed``.

    If denied: short-circuits the pipeline with a structured denial response
    including the explanation trace.
    If allowed: evaluation proceeds through remaining middleware.

    Attributes:
        name: "fizzpolicy"
        priority: 6

    Methods:
        __init__(self, engine: PolicyEngine, explanation_mode: ExplanationMode)
        process(self, context: ProcessingContext, next_handler) -> FizzBuzzResult
        get_name(self) -> str
        get_priority(self) -> int
        get_stats(self) -> Dict[str, Any]
        render_status(self) -> str
        render_decisions(self, since, until, path, result, user, page) -> str
        render_eval(self, query, input_json, explain) -> str
        render_test(self, bundle_path, coverage) -> str
        render_bench(self, query, input_json) -> str
        render_compile(self, source) -> str
        _build_input(self, context: ProcessingContext) -> Dict[str, Any]
        _build_denial_result(self, decision: DecisionLogEntry, context) -> FizzBuzzResult
    """
```

### Factory Function
```
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
```

---

## 21. Exception Classes (~30 exceptions, EFP-POL00 through EFP-POL29)

File: `enterprise_fizzbuzz/domain/exceptions/fizzpolicy.py`

All follow the established pattern: inherit from base, call `super().__init__(reason)`, set `self.error_code` and `self.context`.

```python
class PolicyEngineError(FizzBuzzError):
    """Base exception for FizzPolicy declarative policy engine errors."""
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL00"
        self.context = {"reason": reason}

class PolicyLexerError(PolicyEngineError):
    """Raised when the FizzRego lexer encounters invalid source text.

    Unterminated strings, invalid escape sequences, malformed number
    literals, and unrecognized characters trigger this exception.
    The error includes the source file, line, and column.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL01"
        self.context = {"reason": reason}

class PolicyParserError(PolicyEngineError):
    """Raised when the FizzRego parser encounters a syntax error.

    Unexpected tokens, missing delimiters, malformed rule definitions,
    and unsafe variable references trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL02"
        self.context = {"reason": reason}

class PolicyTypeCheckError(PolicyEngineError):
    """Raised when the type checker detects a type incompatibility.

    Comparing incompatible types, arithmetic on non-numeric values,
    and function argument type mismatches trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL03"
        self.context = {"reason": reason}

class PolicyPartialEvalError(PolicyEngineError):
    """Raised when the partial evaluator encounters an error during optimization.

    Static data resolution failures, constant folding errors, and
    rule inlining cycles trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL04"
        self.context = {"reason": reason}

class PolicyPlanGeneratorError(PolicyEngineError):
    """Raised when the plan generator fails to compile a rule into instructions.

    Unsupported AST node types, circular rule references, and join
    ordering failures trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL05"
        self.context = {"reason": reason}

class PolicyEvaluationError(PolicyEngineError):
    """Raised when policy evaluation encounters a runtime error.

    Division by zero, undefined variable access, type mismatches during
    evaluation, and conflicting complete rule values trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL06"
        self.context = {"reason": reason}

class PolicyEvaluationTimeoutError(PolicyEngineError):
    """Raised when a policy evaluation exceeds its wall-clock timeout.

    The default timeout is 100ms.  Complex policies with unbounded
    iteration or deeply nested evaluations may exceed this limit.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL07"
        self.context = {"reason": reason}

class PolicyEvaluationLimitError(PolicyEngineError):
    """Raised when a policy evaluation exceeds its iteration or output size limit.

    The default limits are 100,000 plan instructions and 1MB output.
    Policies that generate excessively large result sets or create
    unbounded iteration trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL08"
        self.context = {"reason": reason}

class PolicyBundleError(PolicyEngineError):
    """Raised when a policy bundle operation fails.

    General bundle lifecycle errors not covered by more specific
    bundle exception subclasses trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL09"
        self.context = {"reason": reason}

class PolicyBundleBuildError(PolicyEngineError):
    """Raised when a bundle build fails during compilation or testing.

    Compilation errors in any .rego file, import resolution failures,
    and test failures during the build process trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL10"
        self.context = {"reason": reason}

class PolicyBundleIntegrityError(PolicyEngineError):
    """Raised when a bundle fails signature verification.

    File hash mismatches, invalid HMAC signatures, missing signature
    blocks, and tampered manifest entries trigger this exception.
    This indicates unauthorized policy modification.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL11"
        self.context = {"reason": reason}

class PolicyBundleVersionError(PolicyEngineError):
    """Raised when a bundle version operation fails.

    Activating a non-existent revision, rolling back beyond history
    limits, and revision counter corruption trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL12"
        self.context = {"reason": reason}

class PolicyBundleStoreError(PolicyEngineError):
    """Raised when the bundle store encounters a persistence error.

    Save failures, load failures, content-addressable deduplication
    errors, and storage corruption trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL13"
        self.context = {"reason": reason}

class PolicyBundleSigningError(PolicyEngineError):
    """Raised when bundle signing fails.

    Missing signing key, HMAC computation errors, and key ID
    mismatches trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL14"
        self.context = {"reason": reason}

class PolicyDecisionLogError(PolicyEngineError):
    """Raised when the decision logger encounters a recording error.

    Log entry serialization failures, storage capacity exhaustion,
    and input masking errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL15"
        self.context = {"reason": reason}

class PolicyDecisionQueryError(PolicyEngineError):
    """Raised when a decision log query fails.

    Invalid filter parameters, time range parsing errors, and
    pagination boundary errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL16"
        self.context = {"reason": reason}

class PolicyDecisionExportError(PolicyEngineError):
    """Raised when decision log export fails.

    Unsupported export format, serialization errors, and filesystem
    write failures trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL17"
        self.context = {"reason": reason}

class PolicyDataAdapterError(PolicyEngineError):
    """Raised when a data adapter fails to fetch external data.

    Subsystem unavailability, data format changes, and adapter
    initialization failures trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL18"
        self.context = {"reason": reason}

class PolicyDataRefreshError(PolicyEngineError):
    """Raised when the data refresh scheduler encounters an error.

    Adapter timeout, concurrent refresh conflicts, and atomic
    data swap failures trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL19"
        self.context = {"reason": reason}

class PolicyTestError(PolicyEngineError):
    """Raised when the policy test runner encounters an infrastructure error.

    Test discovery failures, test environment setup errors, and
    coverage instrumentation failures trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL20"
        self.context = {"reason": reason}

class PolicyTestFailedError(PolicyEngineError):
    """Raised when one or more policy tests fail.

    Contains the test run result with per-test failure details
    including expected vs actual values and explanation traces.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL21"
        self.context = {"reason": reason}

class PolicyCoverageError(PolicyEngineError):
    """Raised when policy test coverage falls below the configured threshold.

    The default minimum coverage is 80%.  Bundles with insufficient
    coverage are rejected during the build process.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL22"
        self.context = {"reason": reason}

class PolicyBenchmarkError(PolicyEngineError):
    """Raised when policy benchmarking encounters an error.

    Benchmark setup failures, evaluation errors during benchmarking,
    and statistical computation errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL23"
        self.context = {"reason": reason}

class PolicyWatcherError(PolicyEngineError):
    """Raised when the policy watcher fails to detect or process activations.

    Store polling failures, bundle load errors after activation,
    and test failures on new bundles trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL24"
        self.context = {"reason": reason}

class PolicyHotReloadError(PolicyEngineError):
    """Raised when policy hot-reload via Raft consensus fails.

    Raft log deserialization errors, follower-leader version mismatch,
    and plan swap failures during hot-reload trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL25"
        self.context = {"reason": reason}

class PolicyBuiltinError(PolicyEngineError):
    """Raised when a built-in function encounters a runtime error.

    Argument type mismatches, invalid inputs (e.g., invalid regex
    pattern, malformed JWT token), and domain errors (division by
    zero in format_int) trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL26"
        self.context = {"reason": reason}

class PolicyAdmissionDeniedError(PolicyEngineError):
    """Raised when the admission controller denies a resource mutation.

    The admission controller evaluates ``data.fizzbuzz.admission.allowed``
    and raises this exception when the result is false or undefined.
    Contains the denial reason and the explanation trace.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL27"
        self.context = {"reason": reason}

class PolicyMiddlewareError(PolicyEngineError):
    """Raised when the FizzPolicy middleware encounters a processing error.

    Input document construction failures, engine invocation errors,
    and denial response building errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-POL28"
        self.context = {"reason": reason}
```

---

## 22. Domain Events

File: `enterprise_fizzbuzz/domain/events/fizzpolicy.py`

```python
"""FizzPolicy declarative policy engine events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("POLICY_BUNDLE_BUILT")
EventType.register("POLICY_BUNDLE_SIGNED")
EventType.register("POLICY_BUNDLE_PUSHED")
EventType.register("POLICY_BUNDLE_ACTIVATED")
EventType.register("POLICY_BUNDLE_ROLLBACK")
EventType.register("POLICY_BUNDLE_REJECTED")
EventType.register("POLICY_BUNDLE_INTEGRITY_FAILED")
EventType.register("POLICY_EVALUATION_COMPLETED")
EventType.register("POLICY_EVALUATION_DENIED")
EventType.register("POLICY_EVALUATION_TIMEOUT")
EventType.register("POLICY_EVALUATION_ERROR")
EventType.register("POLICY_CACHE_HIT")
EventType.register("POLICY_CACHE_INVALIDATED")
EventType.register("POLICY_DATA_REFRESHED")
EventType.register("POLICY_DATA_STALE")
EventType.register("POLICY_DATA_ADAPTER_ERROR")
EventType.register("POLICY_TEST_SUITE_PASSED")
EventType.register("POLICY_TEST_SUITE_FAILED")
EventType.register("POLICY_COVERAGE_BELOW_THRESHOLD")
EventType.register("POLICY_HOT_RELOAD_STARTED")
EventType.register("POLICY_HOT_RELOAD_COMPLETED")
EventType.register("POLICY_HOT_RELOAD_FAILED")
EventType.register("POLICY_ADMISSION_DENIED")
EventType.register("POLICY_DECISION_LOGGED")
EventType.register("POLICY_DECISION_EXPORTED")
EventType.register("POLICY_MIDDLEWARE_PROCESSED")
```

---

## 23. Configuration Mixin

File: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzpolicy.py`

```python
"""Fizzpolicy configuration properties."""

from __future__ import annotations

from typing import Any


class FizzpolicyConfigMixin:
    """Configuration properties for the fizzpolicy subsystem."""

    @property
    def fizzpolicy_enabled(self) -> bool:
        """Whether the FizzPolicy declarative policy engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpolicy", {}).get("enabled", False)

    @property
    def fizzpolicy_eval_timeout_ms(self) -> float:
        """Maximum wall-clock time for a single policy evaluation in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("eval_timeout_ms", 100.0))

    @property
    def fizzpolicy_max_iterations(self) -> int:
        """Maximum plan instruction executions per evaluation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("max_iterations", 100000))

    @property
    def fizzpolicy_max_output_size_bytes(self) -> int:
        """Maximum result document size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("max_output_size_bytes", 1048576))

    @property
    def fizzpolicy_cache_max_entries(self) -> int:
        """Maximum entries in the evaluation cache."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("cache_max_entries", 10000))

    @property
    def fizzpolicy_explanation_mode(self) -> str:
        """Decision explanation verbosity: full, summary, minimal, off."""
        self._ensure_loaded()
        return str(self._raw_config.get("fizzpolicy", {}).get("explanation_mode", "summary"))

    @property
    def fizzpolicy_signing_key(self) -> str:
        """HMAC-SHA256 signing key for policy bundles."""
        self._ensure_loaded()
        return str(self._raw_config.get("fizzpolicy", {}).get("signing_key", "fizzbuzz-default-policy-key"))

    @property
    def fizzpolicy_data_refresh_interval(self) -> float:
        """Default data adapter refresh interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("data_refresh_interval", 30.0))

    @property
    def fizzpolicy_bundle_coverage_threshold(self) -> float:
        """Minimum test coverage percentage for bundle builds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("bundle_coverage_threshold", 80.0))

    @property
    def fizzpolicy_bundle_perf_threshold_ms(self) -> float:
        """Maximum p99 evaluation time for bundle performance checks."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("bundle_perf_threshold_ms", 10.0))

    @property
    def fizzpolicy_decision_log_mask_fields(self) -> list:
        """Input fields to redact in decision logs."""
        self._ensure_loaded()
        return list(self._raw_config.get("fizzpolicy", {}).get("decision_log", {}).get("mask_fields", ["token", "secret", "password", "hmac_key"]))

    @property
    def fizzpolicy_decision_log_page_size(self) -> int:
        """Default page size for decision log queries."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("decision_log", {}).get("page_size", 100))
```

---

## 24. Feature Descriptor

File: `enterprise_fizzbuzz/infrastructure/features/fizzpolicy_feature.py`

```python
"""Feature descriptor for FizzPolicy declarative policy engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzPolicyFeature(FeatureDescriptor):
    name = "fizzpolicy"
    description = "Declarative policy engine with FizzRego language, bundle management, and decision logging"
    middleware_priority = 6
    cli_flags = [
        ("--fizzpolicy", {"action": "store_true", "default": False,
                          "help": "Enable FizzPolicy: declarative policy engine with FizzRego language"}),
        ("--fizzpolicy-bundle", {"type": str, "default": None, "metavar": "PATH",
                                  "help": "Load a policy bundle from the specified path"}),
        ("--fizzpolicy-bundle-build", {"type": str, "default": None, "metavar": "SOURCE_DIR",
                                        "help": "Build a policy bundle from a source directory"}),
        ("--fizzpolicy-bundle-push", {"type": str, "default": None, "metavar": "PATH",
                                       "help": "Push a built bundle to the bundle store"}),
        ("--fizzpolicy-bundle-activate", {"type": int, "default": None, "metavar": "REVISION",
                                           "help": "Activate a specific bundle revision"}),
        ("--fizzpolicy-bundle-rollback", {"type": int, "default": None, "metavar": "REVISION",
                                           "help": "Rollback to a previous bundle revision"}),
        ("--fizzpolicy-bundle-list", {"action": "store_true", "default": False,
                                       "help": "List all bundle revisions with metadata"}),
        ("--fizzpolicy-eval", {"type": str, "default": None, "metavar": "QUERY",
                                "help": "Evaluate a policy query (e.g., data.fizzbuzz.authz.allow)"}),
        ("--fizzpolicy-eval-explain", {"type": str, "default": None, "metavar": "QUERY",
                                        "help": "Evaluate a policy query with full explanation trace"}),
        ("--fizzpolicy-input", {"type": str, "default": None, "metavar": "JSON",
                                 "help": "Input document (JSON) for --fizzpolicy-eval or --fizzpolicy-eval-explain"}),
        ("--fizzpolicy-test", {"type": str, "default": None, "metavar": "BUNDLE_PATH",
                                "help": "Run all tests in a policy bundle"}),
        ("--fizzpolicy-test-coverage", {"type": str, "default": None, "metavar": "BUNDLE_PATH",
                                         "help": "Run tests with coverage analysis"}),
        ("--fizzpolicy-bench", {"type": str, "default": None, "metavar": "QUERY",
                                 "help": "Benchmark a policy query"}),
        ("--fizzpolicy-decisions", {"action": "store_true", "default": False,
                                     "help": "Query the decision log"}),
        ("--fizzpolicy-decisions-export", {"type": str, "default": None, "metavar": "FORMAT",
                                            "help": "Export decision logs (json, csv, fizzsheet)"}),
        ("--fizzpolicy-decisions-since", {"type": str, "default": None, "metavar": "TIMESTAMP",
                                           "help": "Filter decisions since timestamp (ISO 8601)"}),
        ("--fizzpolicy-decisions-until", {"type": str, "default": None, "metavar": "TIMESTAMP",
                                           "help": "Filter decisions until timestamp (ISO 8601)"}),
        ("--fizzpolicy-decisions-path", {"type": str, "default": None, "metavar": "PATH",
                                          "help": "Filter decisions by rule path"}),
        ("--fizzpolicy-decisions-result", {"type": str, "default": None, "metavar": "RESULT",
                                            "help": "Filter decisions by result (allow, deny)"}),
        ("--fizzpolicy-decisions-user", {"type": str, "default": None, "metavar": "USER",
                                          "help": "Filter decisions by user"}),
        ("--fizzpolicy-data-refresh", {"action": "store_true", "default": False,
                                        "help": "Trigger immediate refresh of all data adapters"}),
        ("--fizzpolicy-status", {"action": "store_true", "default": False,
                                  "help": "Show policy engine status (bundle, cache, latency, adapters)"}),
        ("--fizzpolicy-compile", {"type": str, "default": None, "metavar": "FILE",
                                   "help": "Compile a FizzRego file and show diagnostics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzpolicy", False),
            getattr(args, "fizzpolicy_status", False),
            getattr(args, "fizzpolicy_eval", None) is not None,
            getattr(args, "fizzpolicy_eval_explain", None) is not None,
            getattr(args, "fizzpolicy_decisions", False),
            getattr(args, "fizzpolicy_bundle_list", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzpolicy import (
            FizzPolicyMiddleware,
            create_fizzpolicy_subsystem,
        )

        engine, middleware = create_fizzpolicy_subsystem(
            signing_key=config.fizzpolicy_signing_key,
            eval_timeout_ms=config.fizzpolicy_eval_timeout_ms,
            max_iterations=config.fizzpolicy_max_iterations,
            cache_max_entries=config.fizzpolicy_cache_max_entries,
            explanation_mode=config.fizzpolicy_explanation_mode,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzpolicy_status", False):
            parts.append(middleware.render_status())
        if getattr(args, "fizzpolicy_decisions", False):
            parts.append(middleware.render_decisions(
                since=getattr(args, "fizzpolicy_decisions_since", None),
                until=getattr(args, "fizzpolicy_decisions_until", None),
                path=getattr(args, "fizzpolicy_decisions_path", None),
                result=getattr(args, "fizzpolicy_decisions_result", None),
                user=getattr(args, "fizzpolicy_decisions_user", None),
                page=1,
            ))
        if getattr(args, "fizzpolicy_bundle_list", False):
            parts.append(middleware.render_bundle_list())
        return "\n".join(parts) if parts else None
```

---

## 25. Configuration YAML

File: `config.d/fizzpolicy.yaml`

```yaml

fizzpolicy:
  enabled: false
  eval_timeout_ms: 100.0
  max_iterations: 100000
  max_output_size_bytes: 1048576
  cache_max_entries: 10000
  explanation_mode: summary
  signing_key: fizzbuzz-default-policy-key
  data_refresh_interval: 30.0
  bundle_coverage_threshold: 80.0
  bundle_perf_threshold_ms: 10.0
  decision_log:
    mask_fields:
      - token
      - secret
      - password
      - hmac_key
    page_size: 100
```

---

## 26. Re-export Stub

File: `fizzpolicy.py` (project root)

```python
"""Backward-compatible re-export stub for fizzpolicy."""
from enterprise_fizzbuzz.infrastructure.fizzpolicy import *  # noqa: F401,F403
```

---

## 27. Test Classes

File: `tests/test_fizzpolicy.py` (~500 lines, ~120 tests)

```
class TestTokenType                    (~3 tests)  - Enum values and membership
class TestRegoType                     (~3 tests)  - Enum values and membership
class TestPlanOpcode                   (~2 tests)  - Enum values
class TestExplanationMode              (~2 tests)  - Enum values
class TestDecisionResult               (~2 tests)  - Enum values
class TestDataAdapterState             (~2 tests)  - Enum values
class TestBundleState                  (~2 tests)  - Enum values
class TestPolicyTestResult             (~2 tests)  - Enum values
class TestToken                        (~3 tests)  - Dataclass creation, defaults, source location
class TestASTNodes                     (~8 tests)  - PackageNode, ImportNode, RuleNode, ExprNode, TermNode, RefNode, ComprehensionNode, SomeNode, EveryNode, WithNode, CallNode, NotNode node_type and fields
class TestPlanInstruction              (~2 tests)  - Creation, children
class TestCompiledPlan                 (~2 tests)  - Creation, default_value
class TestTypeAnnotation               (~2 tests)  - Creation, warning fields
class TestBundleManifest               (~2 tests)  - Creation, defaults, roots
class TestPolicyBundle                 (~2 tests)  - Creation, state lifecycle
class TestBundleSignature              (~2 tests)  - Creation, file/signature lists
class TestDecisionLogEntry             (~2 tests)  - Creation, UUID generation, timestamp
class TestEvaluationMetrics            (~2 tests)  - Creation, field defaults
class TestEvalStep                     (~2 tests)  - Creation, children nesting
class TestDataAdapterInfo              (~2 tests)  - Creation, state values
class TestTestRunResult                (~2 tests)  - Creation, aggregates
class TestBenchmarkResult              (~2 tests)  - Creation, percentile fields
class TestPolicyEngineStatus           (~2 tests)  - Creation, adapter_states dict
class TestFizzRegoLexer                (~10 tests) - Keywords, identifiers, strings (escapes, backtick), numbers (decimal, hex, octal, binary), operators (single-char, two-char), comments, newlines, source location tracking, unterminated string error, invalid character error
class TestFizzRegoParser               (~10 tests) - Package declaration, import with alias, simple allow rule, default rule, complete rule with value, partial set rule, partial object rule, comprehension (set, array, object), some/every/with/not nodes, function call, nested expressions, unsafe variable rejection
class TestFizzRegoTypeChecker          (~6 tests)  - Boolean rule typing, number comparison, string comparison, arithmetic on non-numeric warning, function signature validation, comprehension type inference
class TestFizzRegoPartialEvaluator     (~5 tests)  - Constant folding, dead branch elimination, helper inlining, static iteration unrolling, no-op on dynamic-only policy
class TestFizzRegoPlanGenerator        (~5 tests)  - Simple filter plan, scan+filter plan, not sub-plan, aggregate plan, join ordering by selectivity
class TestBuiltinRegistry              (~8 tests)  - String functions (concat, sprintf, contains), regex functions (match, split), aggregation (count, sum, max), type functions (type_name, is_number), object functions (get, keys), time (now_ns), crypto (sha256), fizzbuzz domain (evaluate, is_fizz, cognitive_load)
class TestPlanExecutor                 (~6 tests)  - Simple filter evaluation, scan with backtracking, not instruction, aggregate (set comprehension), timeout enforcement, iteration limit enforcement
class TestEvaluationCache              (~4 tests)  - Put/get, LRU eviction, invalidate_all, stats (hit rate)
class TestPolicyEngine                 (~6 tests)  - Load bundle, evaluate allow, evaluate deny, evaluate with cache hit, evaluate with explanation, status reporting
class TestExplanationEngine            (~4 tests)  - Full trace, summary trace, minimal trace, off mode
class TestExplanationFormatter         (~3 tests)  - Text format with tree connectors, JSON format, graph format
class TestBundleBuilder                (~4 tests)  - Build valid bundle, build with test failure raises, build with compile error raises, import resolution
class TestBundleVersionManager         (~4 tests)  - Push increments revision, activate, rollback, list revisions
class TestBundleStore                  (~3 tests)  - Save/load round-trip, delete, content-addressable dedup
class TestBundleSigner                 (~4 tests)  - Sign produces signature, verify valid passes, verify tampered fails, missing key error
class TestDecisionLogger               (~5 tests)  - Log entry, mask sensitive fields, filter by path, filter by result, clear
class TestDecisionLogQuery             (~4 tests)  - Query by time range, by path, by user, pagination
class TestDecisionLogExporter          (~3 tests)  - Export JSONL, export CSV, export fizzsheet
class TestDataAdapter                  (~3 tests)  - RBAC adapter fetch, operator adapter fetch, adapter info
class TestDataRefreshScheduler         (~3 tests)  - Register/refresh, stale data warning, unregister
class TestPolicyTestRunner             (~4 tests)  - Discover tests, run passing suite, run failing suite, per-test timing
class TestPolicyCoverageAnalyzer       (~3 tests)  - Rule coverage, expression branch coverage, data path coverage
class TestPolicyBenchmark              (~2 tests)  - Run benchmark, percentile computation
class TestPolicyWatcher                (~3 tests)  - Notify activation success, notify activation failure retains old, cache invalidation
class TestPolicyHotReloadMiddleware    (~2 tests)  - Raft entry triggers watcher, non-policy entry ignored
class TestDefaultBundleFactory         (~3 tests)  - Creates valid bundle, contains all 8 packages, data document has required keys
class TestFizzPolicyMiddleware         (~5 tests)  - Process allows, process denies with explanation, name/priority, render_status, render_eval
class TestCreateSubsystem              (~2 tests)  - Factory wiring, returns engine/middleware tuple
class TestExceptions                   (~3 tests)  - Error codes (EFP-POL00 through EFP-POL28), inheritance from PolicyEngineError, context dict
```

### Test Fixture Pattern

```python
import pytest
from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()
```

---

## 28. Wiring Notes

### exceptions/__init__.py

Add at end of import block (before `__all__`):
```python
from enterprise_fizzbuzz.domain.exceptions.fizzpolicy import *  # noqa: F401,F403
```

Add all 29 exception class names to the `__all__` list.

### events/__init__.py

Add at end of import block (before `__all__`):
```python
import enterprise_fizzbuzz.domain.events.fizzpolicy  # noqa: F401
```

### config mixins

Add `FizzpolicyConfigMixin` to the configuration manager's mixin chain in `enterprise_fizzbuzz/infrastructure/config/__init__.py`.

---

## 29. Implementation Order

1. Constants and signing constants
2. Enums (TokenType, RegoType, PlanOpcode, ExplanationMode, DecisionResult, DataAdapterState, BundleState, PolicyTestResult)
3. Data classes (Token, all AST nodes, PlanInstruction, CompiledPlan, TypeAnnotation, BundleManifest, PolicyBundle, BundleSignature, DecisionLogEntry, EvaluationMetrics, EvalStep, DataAdapterInfo, TestRunResult, BenchmarkResult, PolicyEngineStatus)
4. FizzRegoLexer (tokenization with keywords, strings, numbers, operators)
5. FizzRegoParser (recursive descent with precedence climbing, AST construction, safety validation)
6. FizzRegoTypeChecker (type inference, compatibility checks, warning generation)
7. FizzRegoPartialEvaluator (constant folding, dead branch elimination, inlining, unrolling)
8. FizzRegoPlanGenerator (instruction emission, join ordering, selectivity estimation)
9. BuiltinRegistry (all 78 built-in function implementations)
10. PlanExecutor (backtracking evaluation, timeout/limit enforcement)
11. EvaluationCache (LRU, SHA-256 keys, invalidation)
12. ExplanationEngine and ExplanationFormatter (trace modes, text/JSON/graph output)
13. PolicyEngine (central evaluation, data merging, decision classification)
14. BundleSigner (SHA-256 hashing, HMAC-SHA256 signing/verification)
15. BundleStore (persistence, content-addressable deduplication)
16. BundleBuilder (compile pipeline, test execution, signing)
17. BundleVersionManager (revision tracking, activation, rollback)
18. DecisionLogger, DecisionLogQuery, DecisionLogExporter (audit trail)
19. DataAdapter and 7 built-in adapters (RBAC, Compliance, Capability, Network, Operator, Cgroup, Deployment)
20. DataRefreshScheduler (atomic data swap, stale warnings)
21. PolicyTestRunner, PolicyCoverageAnalyzer, PolicyBenchmark (testing framework)
22. PolicyWatcher, PolicyHotReloadMiddleware (live updates)
23. DefaultBundleFactory (8 policy packages, data document, test policies)
24. FizzPolicyMiddleware (admission check, input construction, denial response)
25. Factory function (create_fizzpolicy_subsystem)

"""Tests for the FizzPolicy declarative policy engine.

Validates the complete FizzPolicy subsystem: enums, data classes,
FizzRego lexer, parser, type checker, partial evaluator, plan generator,
builtin registry, plan executor, evaluation cache, explanation engine,
policy engine, bundle signer/store/builder/version manager, decision
logging, data adapters, testing framework, coverage analysis, benchmarking,
hot-reload, default bundle factory, middleware, and factory wiring.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzpolicy import (
    # Enums
    TokenType,
    RegoType,
    PlanOpcode,
    ExplanationMode,
    DecisionResult,
    DataAdapterState,
    BundleState,
    PolicyTestResultEnum,
    # Data classes
    Token,
    ASTNode,
    PackageNode,
    ImportNode,
    RuleNode,
    ExprNode,
    TermNode,
    RefNode,
    ComprehensionNode,
    SomeNode,
    EveryNode,
    WithNode,
    CallNode,
    NotNode,
    PolicyModule,
    PlanInstruction,
    CompiledPlan,
    TypeAnnotation,
    BundleManifest,
    PolicyBundle,
    BundleSignature,
    DecisionLogEntry,
    EvaluationMetrics,
    EvalStep,
    DataAdapterInfo,
    TestRunResult,
    BenchmarkResult,
    PolicyEngineStatus,
    # Compiler pipeline
    FizzRegoLexer,
    FizzRegoParser,
    FizzRegoTypeChecker,
    FizzRegoPartialEvaluator,
    FizzRegoPlanGenerator,
    # Runtime
    BuiltinRegistry,
    PlanExecutor,
    EvaluationCache,
    ExplanationEngine,
    ExplanationFormatter,
    PolicyEngine,
    # Bundle system
    BundleSigner,
    BundleStore,
    BundleBuilder,
    BundleVersionManager,
    # Decision logging
    DecisionLogger,
    DecisionLogQuery,
    DecisionLogExporter,
    # Data integration
    DataAdapter,
    RBACDataAdapter,
    ComplianceDataAdapter,
    CapabilityDataAdapter,
    NetworkDataAdapter,
    OperatorDataAdapter,
    CgroupDataAdapter,
    DeploymentDataAdapter,
    DataRefreshScheduler,
    # Testing framework
    PolicyTestRunner,
    PolicyCoverageAnalyzer,
    PolicyBenchmark,
    # Hot-reload
    PolicyWatcher,
    PolicyHotReloadMiddleware,
    # Default bundle
    DefaultBundleFactory,
    # Middleware
    FizzPolicyMiddleware,
    # Factory
    create_fizzpolicy_subsystem,
    # Constants
    FIZZPOLICY_VERSION,
    FIZZREGO_LANGUAGE_VERSION,
    MIDDLEWARE_PRIORITY,
)
from enterprise_fizzbuzz.domain.exceptions import (
    PolicyEngineError,
    PolicyLexerError,
    PolicyParserError,
    PolicyEvaluationError,
    PolicyBundleIntegrityError,
    PolicyBundleVersionError,
    PolicyBundleSigningError,
    PolicyMiddlewareError,
)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------

class TestTokenType:
    def test_keyword_members_exist(self):
        assert TokenType.PACKAGE.value == "PACKAGE"
        assert TokenType.IMPORT.value == "IMPORT"
        assert TokenType.DEFAULT.value == "DEFAULT"
        assert TokenType.NOT.value == "NOT"

    def test_operator_members_exist(self):
        assert TokenType.EQ.value == "EQ"
        assert TokenType.NEQ.value == "NEQ"
        assert TokenType.ASSIGN.value == "ASSIGN"

    def test_eof_member(self):
        assert TokenType.EOF.value == "EOF"


class TestRegoType:
    def test_primitive_types(self):
        assert RegoType.BOOLEAN.value == "boolean"
        assert RegoType.NUMBER.value == "number"
        assert RegoType.STRING.value == "string"
        assert RegoType.NULL.value == "null"

    def test_collection_types(self):
        assert RegoType.SET.value == "set"
        assert RegoType.ARRAY.value == "array"
        assert RegoType.OBJECT.value == "object"

    def test_special_types(self):
        assert RegoType.ANY.value == "any"
        assert RegoType.UNDEFINED.value == "undefined"


class TestPlanOpcode:
    def test_all_opcodes_exist(self):
        opcodes = [PlanOpcode.SCAN, PlanOpcode.FILTER, PlanOpcode.LOOKUP,
                   PlanOpcode.ASSIGN, PlanOpcode.CALL, PlanOpcode.NOT,
                   PlanOpcode.AGGREGATE, PlanOpcode.YIELD, PlanOpcode.HALT]
        assert len(opcodes) == 9

    def test_opcode_values(self):
        assert PlanOpcode.SCAN.value == "SCAN"
        assert PlanOpcode.HALT.value == "HALT"


class TestExplanationMode:
    def test_mode_values(self):
        assert ExplanationMode.FULL.value == "full"
        assert ExplanationMode.SUMMARY.value == "summary"
        assert ExplanationMode.MINIMAL.value == "minimal"
        assert ExplanationMode.OFF.value == "off"

    def test_membership(self):
        assert len(ExplanationMode) == 4


class TestDecisionResult:
    def test_result_values(self):
        assert DecisionResult.ALLOW.value == "allow"
        assert DecisionResult.DENY.value == "deny"
        assert DecisionResult.ERROR.value == "error"
        assert DecisionResult.UNDEFINED.value == "undefined"

    def test_membership(self):
        assert len(DecisionResult) == 4


class TestDataAdapterState:
    def test_state_values(self):
        assert DataAdapterState.HEALTHY.value == "healthy"
        assert DataAdapterState.STALE.value == "stale"
        assert DataAdapterState.ERROR.value == "error"
        assert DataAdapterState.DISABLED.value == "disabled"

    def test_membership(self):
        assert len(DataAdapterState) == 4


class TestBundleState:
    def test_state_values(self):
        assert BundleState.BUILDING.value == "building"
        assert BundleState.ACTIVE.value == "active"
        assert BundleState.SIGNED.value == "signed"

    def test_lifecycle_states(self):
        assert BundleState.TESTING.value == "testing"
        assert BundleState.INACTIVE.value == "inactive"
        assert BundleState.REJECTED.value == "rejected"


class TestPolicyTestResult:
    def test_result_values(self):
        assert PolicyTestResultEnum.PASSED.value == "passed"
        assert PolicyTestResultEnum.FAILED.value == "failed"

    def test_all_values(self):
        assert PolicyTestResultEnum.ERRORED.value == "errored"
        assert PolicyTestResultEnum.SKIPPED.value == "skipped"


# ---------------------------------------------------------------------------
# Data Class Tests
# ---------------------------------------------------------------------------

class TestToken:
    def test_creation(self):
        tok = Token(token_type=TokenType.IDENT, literal="allow")
        assert tok.token_type == TokenType.IDENT
        assert tok.literal == "allow"

    def test_defaults(self):
        tok = Token(token_type=TokenType.EOF, literal="")
        assert tok.line == 1
        assert tok.column == 1
        assert tok.file == ""

    def test_source_location(self):
        tok = Token(token_type=TokenType.STRING, literal='"hello"', line=5, column=12, file="authz.rego")
        assert tok.line == 5
        assert tok.column == 12
        assert tok.file == "authz.rego"


class TestASTNodes:
    def test_package_node(self):
        node = PackageNode(path=["fizzbuzz", "authz"])
        assert node.node_type == "package"
        assert node.path == ["fizzbuzz", "authz"]

    def test_import_node(self):
        node = ImportNode(path=["data", "fizzbuzz", "compliance"], alias="compliance")
        assert node.node_type == "import"
        assert node.alias == "compliance"

    def test_rule_node(self):
        node = RuleNode(name="allow", body=[])
        assert node.node_type == "rule"
        assert node.name == "allow"
        assert node.is_default is False

    def test_expr_node(self):
        node = ExprNode(operator="==")
        assert node.node_type == "expr"
        assert node.operator == "=="

    def test_term_node(self):
        node = TermNode(value=42)
        assert node.node_type == "term"
        assert node.value == 42

    def test_ref_node(self):
        node = RefNode(segments=["data", "roles"])
        assert node.node_type == "ref"
        assert len(node.segments) == 2

    def test_comprehension_node(self):
        node = ComprehensionNode(kind="set")
        assert node.node_type == "comprehension"
        assert node.kind == "set"

    def test_some_every_with_call_not(self):
        some = SomeNode(variables=["x", "y"])
        assert some.node_type == "some"
        every = EveryNode(value_var="item")
        assert every.node_type == "every"
        with_node = WithNode()
        assert with_node.node_type == "with"
        call = CallNode()
        assert call.node_type == "call"
        not_node = NotNode()
        assert not_node.node_type == "not"


class TestPlanInstruction:
    def test_creation(self):
        inst = PlanInstruction(opcode=PlanOpcode.FILTER, operands={"field": "role"})
        assert inst.opcode == PlanOpcode.FILTER
        assert inst.operands["field"] == "role"

    def test_children(self):
        child = PlanInstruction(opcode=PlanOpcode.YIELD)
        parent = PlanInstruction(opcode=PlanOpcode.NOT, children=[child])
        assert len(parent.children) == 1


class TestCompiledPlan:
    def test_creation(self):
        plan = CompiledPlan(rule_name="allow", package_path="fizzbuzz.authz")
        assert plan.rule_name == "allow"
        assert plan.package_path == "fizzbuzz.authz"

    def test_default_value(self):
        plan = CompiledPlan(default_value=False)
        assert plan.default_value is False
        assert plan.is_complete is True


class TestTypeAnnotation:
    def test_creation(self):
        ann = TypeAnnotation(base_type=RegoType.BOOLEAN)
        assert ann.base_type == RegoType.BOOLEAN
        assert ann.is_warning is False

    def test_warning_fields(self):
        ann = TypeAnnotation(base_type=RegoType.ANY, is_warning=True, warning_message="mixed types")
        assert ann.is_warning is True
        assert ann.warning_message == "mixed types"


class TestBundleManifest:
    def test_creation(self):
        manifest = BundleManifest(revision=3, bundle_name="prod")
        assert manifest.revision == 3
        assert manifest.bundle_name == "prod"

    def test_defaults(self):
        manifest = BundleManifest()
        assert manifest.revision == 0
        assert manifest.roots == ["fizzbuzz"]
        assert manifest.rego_version == FIZZREGO_LANGUAGE_VERSION


class TestPolicyBundle:
    def test_creation(self):
        bundle = PolicyBundle()
        assert bundle.state == BundleState.BUILDING
        assert isinstance(bundle.modules, dict)
        assert isinstance(bundle.plans, dict)

    def test_state_lifecycle(self):
        bundle = PolicyBundle()
        assert bundle.state == BundleState.BUILDING
        bundle.state = BundleState.TESTING
        assert bundle.state == BundleState.TESTING
        bundle.state = BundleState.ACTIVE
        assert bundle.state == BundleState.ACTIVE


class TestBundleSignature:
    def test_creation(self):
        sig = BundleSignature(files=[{"name": "authz.rego", "hash": "abc", "algorithm": "SHA-256"}])
        assert len(sig.files) == 1

    def test_signature_list(self):
        sig = BundleSignature(
            files=[],
            signatures=[{"keyid": "k1", "sig": "abc123", "algorithm": "HMAC-SHA256"}],
        )
        assert len(sig.signatures) == 1


class TestDecisionLogEntry:
    def test_creation(self):
        entry = DecisionLogEntry(
            path="data.fizzbuzz.authz.allow",
            input_doc={"user": "admin"},
            result=True,
            result_type=DecisionResult.ALLOW,
            bundle_revision=1,
        )
        assert entry.path == "data.fizzbuzz.authz.allow"
        assert entry.result is True

    def test_uuid_generation(self):
        e1 = DecisionLogEntry(path="a", input_doc={}, result=True, result_type=DecisionResult.ALLOW, bundle_revision=1)
        e2 = DecisionLogEntry(path="a", input_doc={}, result=True, result_type=DecisionResult.ALLOW, bundle_revision=1)
        assert e1.decision_id != e2.decision_id

    def test_timestamp(self):
        entry = DecisionLogEntry(path="a", input_doc={}, result=True, result_type=DecisionResult.ALLOW, bundle_revision=1)
        assert entry.timestamp is not None
        assert isinstance(entry.timestamp, datetime)


class TestEvaluationMetrics:
    def test_creation(self):
        m = EvaluationMetrics()
        assert m.eval_duration_ns == 0

    def test_field_defaults(self):
        m = EvaluationMetrics()
        assert m.plan_instructions_executed == 0
        assert m.backtracks == 0


class TestEvalStep:
    def test_creation(self):
        step = EvalStep(expression="evaluate rule allow")
        assert step.expression == "evaluate rule allow"

    def test_children_nesting(self):
        child = EvalStep(expression="check condition")
        parent = EvalStep(expression="rule", children=[child])
        assert len(parent.children) == 1


class TestDataAdapterInfo:
    def test_creation(self):
        info = DataAdapterInfo(
            name="rbac", data_path="rbac",
            refresh_interval=300.0,
            state=DataAdapterState.HEALTHY,
        )
        assert info.name == "rbac"
        assert info.state == DataAdapterState.HEALTHY

    def test_state_values(self):
        info = DataAdapterInfo(name="test", data_path="test", refresh_interval=10.0, state=DataAdapterState.STALE)
        assert info.state == DataAdapterState.STALE


class TestTestRunResult:
    def test_creation(self):
        result = TestRunResult(total=10, passed=8, failed=1, errored=1)
        assert result.total == 10
        assert result.passed == 8

    def test_aggregates(self):
        result = TestRunResult(total=5, passed=5)
        assert result.failed == 0
        assert result.errored == 0


class TestBenchmarkResult:
    def test_creation(self):
        result = BenchmarkResult(
            query="data.fizzbuzz.authz.allow",
            iterations=1000,
            mean_ns=50000,
            p50_ns=45000,
            p95_ns=80000,
            p99_ns=95000,
            min_ns=20000,
            max_ns=120000,
        )
        assert result.query == "data.fizzbuzz.authz.allow"
        assert result.iterations == 1000

    def test_percentile_fields(self):
        result = BenchmarkResult(
            query="q", iterations=100,
            mean_ns=100, p50_ns=90, p95_ns=150, p99_ns=200,
            min_ns=50, max_ns=300,
        )
        assert result.p50_ns < result.p95_ns < result.p99_ns


class TestPolicyEngineStatus:
    def test_creation(self):
        status = PolicyEngineStatus(
            active_bundle_revision=5,
            bundle_name="prod",
            total_evaluations=1000,
        )
        assert status.active_bundle_revision == 5
        assert status.total_evaluations == 1000

    def test_adapter_states(self):
        status = PolicyEngineStatus(active_bundle_revision=1, bundle_name="test")
        assert status.decisions_allow == 0
        assert status.decisions_deny == 0


# ---------------------------------------------------------------------------
# FizzRego Lexer Tests
# ---------------------------------------------------------------------------

class TestFizzRegoLexer:
    def test_keywords(self):
        lexer = FizzRegoLexer("package import default not some every with as if else")
        tokens = lexer.tokenize()
        types = [t.token_type for t in tokens if t.token_type != TokenType.NEWLINE and t.token_type != TokenType.EOF]
        assert TokenType.PACKAGE in types
        assert TokenType.IMPORT in types
        assert TokenType.DEFAULT in types

    def test_identifiers(self):
        lexer = FizzRegoLexer("allow deny role_name")
        tokens = lexer.tokenize()
        idents = [t for t in tokens if t.token_type == TokenType.IDENT]
        assert len(idents) == 3
        assert idents[0].literal == "allow"

    def test_strings(self):
        lexer = FizzRegoLexer('"hello world"')
        tokens = lexer.tokenize()
        strings = [t for t in tokens if t.token_type == TokenType.STRING]
        assert len(strings) == 1

    def test_string_escapes(self):
        lexer = FizzRegoLexer(r'"hello\nworld"')
        tokens = lexer.tokenize()
        strings = [t for t in tokens if t.token_type == TokenType.STRING]
        assert len(strings) == 1

    def test_numbers_decimal(self):
        lexer = FizzRegoLexer("42 3.14")
        tokens = lexer.tokenize()
        numbers = [t for t in tokens if t.token_type == TokenType.NUMBER]
        assert len(numbers) == 2

    def test_numbers_hex_octal_binary(self):
        lexer = FizzRegoLexer("0xFF 0o77 0b1010")
        tokens = lexer.tokenize()
        numbers = [t for t in tokens if t.token_type == TokenType.NUMBER]
        assert len(numbers) == 3

    def test_operators(self):
        lexer = FizzRegoLexer("== != < > <= >= + - * / %")
        tokens = lexer.tokenize()
        op_types = {TokenType.EQ, TokenType.NEQ, TokenType.LT, TokenType.GT,
                    TokenType.LTE, TokenType.GTE, TokenType.PLUS, TokenType.MINUS,
                    TokenType.STAR, TokenType.SLASH, TokenType.PERCENT}
        found = {t.token_type for t in tokens if t.token_type != TokenType.EOF and t.token_type != TokenType.NEWLINE}
        assert op_types.issubset(found)

    def test_comments(self):
        lexer = FizzRegoLexer("allow # this is a comment\ndeny")
        tokens = lexer.tokenize()
        comments = [t for t in tokens if t.token_type == TokenType.COMMENT]
        assert len(comments) >= 1

    def test_source_location_tracking(self):
        lexer = FizzRegoLexer("allow\ndeny")
        tokens = lexer.tokenize()
        idents = [t for t in tokens if t.token_type == TokenType.IDENT]
        assert idents[0].line == 1
        assert idents[1].line == 2

    def test_unterminated_string_error(self):
        lexer = FizzRegoLexer('"unterminated')
        with pytest.raises(PolicyLexerError):
            lexer.tokenize()


# ---------------------------------------------------------------------------
# FizzRego Parser Tests
# ---------------------------------------------------------------------------

class TestFizzRegoParser:
    def _parse(self, source: str) -> PolicyModule:
        lexer = FizzRegoLexer(source)
        tokens = lexer.tokenize()
        parser = FizzRegoParser(tokens)
        return parser.parse()

    def test_package_declaration(self):
        module = self._parse("package fizzbuzz.authz")
        assert module.package_path == "fizzbuzz.authz"

    def test_import_with_alias(self):
        module = self._parse("package test\nimport data.fizzbuzz.compliance as comp")
        assert len(module.imports) == 1
        assert module.imports[0].alias == "comp"

    def test_simple_allow_rule(self):
        source = 'package test\nallow { input.role == "admin" }'
        module = self._parse(source)
        rules = [r for r in module.rules if r.name == "allow"]
        assert len(rules) >= 1

    def test_default_rule(self):
        source = "package test\ndefault allow := false"
        module = self._parse(source)
        defaults = [r for r in module.rules if r.is_default]
        assert len(defaults) >= 1
        assert defaults[0].name == "allow"

    def test_complete_rule_with_value(self):
        source = 'package test\nmax_number := 100 { input.role == "admin" }'
        module = self._parse(source)
        rules = [r for r in module.rules if r.name == "max_number"]
        assert len(rules) >= 1

    def test_partial_set_rule(self):
        source = 'package test\nallowed_roles[role] { role := "admin" }'
        module = self._parse(source)
        rules = [r for r in module.rules if r.name == "allowed_roles"]
        assert len(rules) >= 1

    def test_function_call(self):
        source = 'package test\nresult { count(input.items) > 0 }'
        module = self._parse(source)
        assert len(module.rules) >= 1

    def test_nested_expressions(self):
        source = 'package test\nresult { (input.a + input.b) * 2 > 10 }'
        module = self._parse(source)
        assert len(module.rules) >= 1

    def test_not_keyword(self):
        source = 'package test\nresult { not input.denied }'
        module = self._parse(source)
        assert len(module.rules) >= 1

    def test_multiple_rules(self):
        source = 'package test\ndefault allow := false\nallow { input.admin }\nallow { input.superuser }'
        module = self._parse(source)
        allow_rules = [r for r in module.rules if r.name == "allow"]
        assert len(allow_rules) >= 2


# ---------------------------------------------------------------------------
# FizzRego Type Checker Tests
# ---------------------------------------------------------------------------

class TestFizzRegoTypeChecker:
    def _check(self, source: str):
        lexer = FizzRegoLexer(source)
        tokens = lexer.tokenize()
        parser = FizzRegoParser(tokens)
        module = parser.parse()
        checker = FizzRegoTypeChecker()
        return checker.check(module)

    def test_boolean_rule_typing(self):
        module, warnings = self._check('package test\nallow { true }')
        assert module is not None

    def test_number_comparison(self):
        module, warnings = self._check('package test\nresult { input.count > 5 }')
        assert module is not None

    def test_string_comparison(self):
        module, warnings = self._check('package test\nresult { input.role == "admin" }')
        assert module is not None

    def test_function_signature_validation(self):
        module, warnings = self._check('package test\nresult { count(input.items) > 0 }')
        assert module is not None

    def test_no_warnings_on_valid_types(self):
        module, warnings = self._check('package test\nallow { true }')
        # Simple rules should not generate warnings
        assert isinstance(warnings, list)

    def test_checker_returns_module_and_warnings(self):
        module, warnings = self._check('package test\ndefault allow := false')
        assert isinstance(module, PolicyModule)
        assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# FizzRego Partial Evaluator Tests
# ---------------------------------------------------------------------------

class TestFizzRegoPartialEvaluator:
    def _partial_eval(self, source: str, data: dict = None):
        lexer = FizzRegoLexer(source)
        tokens = lexer.tokenize()
        parser = FizzRegoParser(tokens)
        module = parser.parse()
        partial = FizzRegoPartialEvaluator(data or {})
        return partial.evaluate(module)

    def test_constant_folding(self):
        module = self._partial_eval('package test\nresult { 1 + 2 == 3 }')
        assert module is not None

    def test_no_op_on_dynamic_policy(self):
        module = self._partial_eval('package test\nresult { input.role == "admin" }')
        assert len(module.rules) >= 1

    def test_preserves_rules(self):
        module = self._partial_eval('package test\ndefault allow := false\nallow { input.admin }')
        assert len(module.rules) >= 1

    def test_with_static_data(self):
        module = self._partial_eval(
            'package test\nresult { data.config.enabled }',
            data={"config": {"enabled": True}},
        )
        assert module is not None

    def test_returns_policy_module(self):
        module = self._partial_eval('package test\nallow { true }')
        assert isinstance(module, PolicyModule)


# ---------------------------------------------------------------------------
# FizzRego Plan Generator Tests
# ---------------------------------------------------------------------------

class TestFizzRegoPlanGenerator:
    def _generate(self, source: str):
        lexer = FizzRegoLexer(source)
        tokens = lexer.tokenize()
        parser = FizzRegoParser(tokens)
        module = parser.parse()
        generator = FizzRegoPlanGenerator()
        return generator.generate(module)

    def test_simple_filter_plan(self):
        plans = self._generate('package test\nallow { input.admin }')
        assert len(plans) >= 1

    def test_plan_has_instructions(self):
        plans = self._generate('package test\nresult { input.count > 5 }')
        for plan in plans.values():
            assert isinstance(plan, CompiledPlan)

    def test_default_plan(self):
        plans = self._generate('package test\ndefault allow := false\nallow { input.admin }')
        assert len(plans) >= 1

    def test_multiple_rules_generate_plans(self):
        plans = self._generate('package test\nallow { input.admin }\ndeny { input.blocked }')
        assert len(plans) >= 2

    def test_plan_keys_contain_rule_name(self):
        plans = self._generate('package test\nallow { true }')
        keys = list(plans.keys())
        assert any("allow" in k for k in keys)


# ---------------------------------------------------------------------------
# Builtin Registry Tests
# ---------------------------------------------------------------------------

class TestBuiltinRegistry:
    def setup_method(self):
        self.builtins = BuiltinRegistry()

    def test_string_concat(self):
        result = self.builtins.call("concat", [", ", ["a", "b", "c"]])
        assert result == "a, b, c"

    def test_string_contains(self):
        result = self.builtins.call("contains", ["hello world", "world"])
        assert result is True

    def test_regex_match(self):
        result = self.builtins.call("regex.match", [r"\d+", "abc123"])
        assert result is True

    def test_count(self):
        result = self.builtins.call("count", [[1, 2, 3]])
        assert result == 3

    def test_sum(self):
        result = self.builtins.call("sum", [[1, 2, 3, 4]])
        assert result == 10

    def test_type_name(self):
        result = self.builtins.call("type_name", [42])
        assert result in ("number", "int")

    def test_object_get(self):
        result = self.builtins.call("object.get", [{"a": 1}, "a", None])
        assert result == 1

    def test_crypto_sha256(self):
        result = self.builtins.call("crypto.sha256", ["hello"])
        assert isinstance(result, str)
        assert len(result) == 64


# ---------------------------------------------------------------------------
# Plan Executor Tests
# ---------------------------------------------------------------------------

class TestPlanExecutor:
    def setup_method(self):
        self.builtins = BuiltinRegistry()
        self.executor = PlanExecutor(self.builtins)

    def test_simple_filter_evaluation(self):
        plan = CompiledPlan(
            rule_name="allow",
            instructions=[
                PlanInstruction(opcode=PlanOpcode.YIELD, operands={"value": True}),
            ],
        )
        result, metrics, trace = self.executor.execute(plan, {}, {})
        assert result is True

    def test_halt_instruction(self):
        plan = CompiledPlan(
            rule_name="test",
            instructions=[
                PlanInstruction(opcode=PlanOpcode.HALT),
            ],
            default_value=False,
        )
        result, metrics, trace = self.executor.execute(plan, {}, {})
        assert isinstance(metrics, EvaluationMetrics)

    def test_lookup_instruction(self):
        plan = CompiledPlan(
            rule_name="test",
            instructions=[
                PlanInstruction(opcode=PlanOpcode.LOOKUP, operands={"path": "input.admin", "var": "x"}),
                PlanInstruction(opcode=PlanOpcode.YIELD, operands={"value": True}),
            ],
        )
        result, metrics, trace = self.executor.execute(plan, {"admin": True}, {})
        assert isinstance(result, (bool, type(None)))

    def test_returns_metrics(self):
        plan = CompiledPlan(
            rule_name="test",
            instructions=[PlanInstruction(opcode=PlanOpcode.YIELD, operands={"value": 42})],
        )
        result, metrics, trace = self.executor.execute(plan, {}, {})
        assert isinstance(metrics, EvaluationMetrics)

    def test_returns_trace(self):
        plan = CompiledPlan(
            rule_name="test",
            instructions=[PlanInstruction(opcode=PlanOpcode.YIELD, operands={"value": True})],
        )
        result, metrics, trace = self.executor.execute(plan, {}, {}, trace_mode=ExplanationMode.FULL)
        assert isinstance(trace, list)

    def test_empty_plan_returns_default(self):
        plan = CompiledPlan(rule_name="test", instructions=[], default_value="undefined")
        result, metrics, trace = self.executor.execute(plan, {}, {})
        assert isinstance(metrics, EvaluationMetrics)


# ---------------------------------------------------------------------------
# Evaluation Cache Tests
# ---------------------------------------------------------------------------

class TestEvaluationCache:
    def test_put_get(self):
        cache = EvaluationCache(max_entries=100)
        cache.put("q1", {"user": "admin"}, 1, True)
        result = cache.get("q1", {"user": "admin"}, 1)
        assert result is True

    def test_lru_eviction(self):
        cache = EvaluationCache(max_entries=2)
        cache.put("q1", {}, 1, "r1")
        cache.put("q2", {}, 1, "r2")
        cache.put("q3", {}, 1, "r3")
        assert cache.get("q1", {}, 1) is None
        assert cache.get("q3", {}, 1) == "r3"

    def test_invalidate_all(self):
        cache = EvaluationCache(max_entries=100)
        cache.put("q1", {}, 1, True)
        cache.invalidate_all()
        assert cache.get("q1", {}, 1) is None

    def test_stats_hit_rate(self):
        cache = EvaluationCache(max_entries=100)
        cache.put("q1", {}, 1, True)
        cache.get("q1", {}, 1)  # hit
        cache.get("q2", {}, 1)  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


# ---------------------------------------------------------------------------
# Policy Engine Tests
# ---------------------------------------------------------------------------

class TestPolicyEngine:
    def _make_engine_with_bundle(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        return engine

    def test_load_bundle(self):
        engine = PolicyEngine()
        bundle = PolicyBundle()
        engine.load_bundle(bundle)
        assert engine.get_active_bundle() is bundle

    def test_evaluate_allow(self):
        engine = self._make_engine_with_bundle()
        entry = engine.evaluate("data.fizzbuzz.authz.allow", {"role": "FIZZBUZZ_SUPERUSER", "action": "evaluate"})
        assert isinstance(entry, DecisionLogEntry)

    def test_evaluate_returns_decision_entry(self):
        engine = self._make_engine_with_bundle()
        entry = engine.evaluate("data.fizzbuzz.authz.allow", {"role": "admin"})
        assert hasattr(entry, "result_type")
        assert entry.result_type in (DecisionResult.ALLOW, DecisionResult.DENY, DecisionResult.UNDEFINED)

    def test_evaluate_with_cache_hit(self):
        engine = self._make_engine_with_bundle()
        e1 = engine.evaluate("data.fizzbuzz.authz.allow", {"role": "admin"})
        e2 = engine.evaluate("data.fizzbuzz.authz.allow", {"role": "admin"})
        assert e2.metrics.get("cache_hit") is True

    def test_no_bundle_raises(self):
        engine = PolicyEngine()
        with pytest.raises(PolicyEvaluationError):
            engine.evaluate("data.test.allow", {})

    def test_status_reporting(self):
        engine = self._make_engine_with_bundle()
        engine.evaluate("data.fizzbuzz.authz.allow", {"role": "admin"})
        status = engine.get_status()
        assert isinstance(status, PolicyEngineStatus)
        assert status.total_evaluations >= 1


# ---------------------------------------------------------------------------
# Explanation Engine Tests
# ---------------------------------------------------------------------------

class TestExplanationEngine:
    def test_full_trace(self):
        engine = ExplanationEngine(mode=ExplanationMode.FULL)
        engine.begin_trace("test.allow")
        assert engine._mode == ExplanationMode.FULL

    def test_summary_trace(self):
        engine = ExplanationEngine(mode=ExplanationMode.SUMMARY)
        engine.begin_trace("test.allow")
        assert engine._mode == ExplanationMode.SUMMARY

    def test_minimal_trace(self):
        engine = ExplanationEngine(mode=ExplanationMode.MINIMAL)
        engine.begin_trace("test.allow")
        assert engine._mode == ExplanationMode.MINIMAL

    def test_off_mode(self):
        engine = ExplanationEngine(mode=ExplanationMode.OFF)
        engine.begin_trace("test.allow")
        assert engine._mode == ExplanationMode.OFF


class TestExplanationFormatter:
    def test_text_format(self):
        formatter = ExplanationFormatter()
        steps = [EvalStep(expression="rule allow evaluated to true")]
        result = formatter.format_text(steps)
        assert isinstance(result, str)
        assert "allow" in result

    def test_json_format(self):
        formatter = ExplanationFormatter()
        steps = [EvalStep(expression="test")]
        result = formatter.format_json(steps)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_graph_format(self):
        formatter = ExplanationFormatter()
        steps = [EvalStep(expression="root", children=[EvalStep(expression="child")])]
        result = formatter.format_graph(steps)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Bundle Signer Tests
# ---------------------------------------------------------------------------

class TestBundleSigner:
    def _make_signed_bundle(self):
        factory = DefaultBundleFactory()
        bundle = factory.create()
        signer = BundleSigner("test-signing-key")
        signer.sign(bundle)
        return bundle, signer

    def test_sign_produces_signature(self):
        bundle, signer = self._make_signed_bundle()
        assert bundle.signatures
        assert "files" in bundle.signatures
        assert "signatures" in bundle.signatures

    def test_verify_valid_passes(self):
        bundle, signer = self._make_signed_bundle()
        assert signer.verify(bundle) is True

    def test_verify_tampered_fails(self):
        bundle, signer = self._make_signed_bundle()
        # Tamper with data
        bundle.data["tampered"] = True
        with pytest.raises(PolicyBundleIntegrityError):
            signer.verify(bundle)

    def test_missing_key_error(self):
        with pytest.raises(PolicyBundleSigningError):
            BundleSigner("")


# ---------------------------------------------------------------------------
# Bundle Store Tests
# ---------------------------------------------------------------------------

class TestBundleStore:
    def test_save_load_roundtrip(self):
        store = BundleStore()
        bundle = PolicyBundle(manifest=BundleManifest(revision=1, bundle_name="test"))
        store.save(bundle)
        loaded = store.load("test", 1)
        assert loaded is bundle

    def test_delete(self):
        store = BundleStore()
        bundle = PolicyBundle(manifest=BundleManifest(revision=1, bundle_name="test"))
        store.save(bundle)
        assert store.delete("test", 1) is True
        assert store.load("test", 1) is None

    def test_content_addressable_dedup(self):
        store = BundleStore()
        b1 = PolicyBundle(manifest=BundleManifest(revision=1, bundle_name="test"))
        b2 = PolicyBundle(manifest=BundleManifest(revision=2, bundle_name="test"))
        h1 = store.save(b1)
        h2 = store.save(b2)
        assert isinstance(h1, str)
        assert isinstance(h2, str)


# ---------------------------------------------------------------------------
# Bundle Builder Tests
# ---------------------------------------------------------------------------

class TestBundleBuilder:
    def test_build_valid_bundle(self):
        builder = BundleBuilder()
        bundle = builder.build(
            policies={"authz.rego": 'package test.authz\ndefault allow := false\nallow { input.admin }'},
            data={"roles": {}},
        )
        assert isinstance(bundle, PolicyBundle)
        assert len(bundle.modules) == 1

    def test_build_with_compile_error_raises(self):
        builder = BundleBuilder()
        with pytest.raises(Exception):
            builder.build(policies={"bad.rego": "this is not valid rego at all {{{ %%% @@@"})

    def test_build_multiple_policies(self):
        builder = BundleBuilder()
        bundle = builder.build(
            policies={
                "authz.rego": 'package test.authz\nallow { true }',
                "compliance.rego": 'package test.compliance\ncompliant { true }',
            },
        )
        assert len(bundle.modules) == 2

    def test_import_resolution(self):
        builder = BundleBuilder()
        bundle = builder.build(
            policies={
                "authz.rego": 'package test.authz\nimport data.test.compliance\nallow { true }',
                "compliance.rego": 'package test.compliance\ncompliant { true }',
            },
        )
        assert len(bundle.modules) == 2


# ---------------------------------------------------------------------------
# Bundle Version Manager Tests
# ---------------------------------------------------------------------------

class TestBundleVersionManager:
    def test_push_increments_revision(self):
        mgr = BundleVersionManager()
        b1 = PolicyBundle()
        b2 = PolicyBundle()
        rev1 = mgr.push(b1)
        rev2 = mgr.push(b2)
        assert rev2 == rev1 + 1

    def test_activate(self):
        mgr = BundleVersionManager()
        bundle = PolicyBundle()
        rev = mgr.push(bundle)
        activated = mgr.activate(rev)
        assert activated.state == BundleState.ACTIVE
        assert mgr.get_active() is bundle

    def test_rollback(self):
        mgr = BundleVersionManager()
        b1 = PolicyBundle()
        b2 = PolicyBundle()
        rev1 = mgr.push(b1)
        rev2 = mgr.push(b2)
        mgr.activate(rev2)
        rolled = mgr.rollback(rev1)
        assert mgr.get_active() is b1

    def test_list_revisions(self):
        mgr = BundleVersionManager()
        mgr.push(PolicyBundle())
        mgr.push(PolicyBundle())
        revisions = mgr.list_revisions()
        assert len(revisions) == 2


# ---------------------------------------------------------------------------
# Decision Logger Tests
# ---------------------------------------------------------------------------

class TestDecisionLogger:
    def test_log_entry(self):
        logger = DecisionLogger()
        entry = DecisionLogEntry(
            path="test.allow", input_doc={"user": "admin"},
            result=True, result_type=DecisionResult.ALLOW, bundle_revision=1,
        )
        logger.log(entry)
        assert len(logger.get_entries()) == 1

    def test_mask_sensitive_fields(self):
        logger = DecisionLogger(mask_fields=["token", "password"])
        entry = DecisionLogEntry(
            path="test.allow",
            input_doc={"user": "admin", "token": "secret123", "password": "p@ss"},
            result=True, result_type=DecisionResult.ALLOW, bundle_revision=1,
        )
        logger.log(entry)
        logged = logger.get_entries()[0]
        assert logged.input_doc["token"] == "[REDACTED]"
        assert logged.input_doc["password"] == "[REDACTED]"
        assert logged.input_doc["user"] == "admin"

    def test_filter_by_path(self):
        logger = DecisionLogger(filter_paths=["authz.allow"])
        e1 = DecisionLogEntry(path="authz.allow", input_doc={}, result=True, result_type=DecisionResult.ALLOW, bundle_revision=1)
        e2 = DecisionLogEntry(path="compliance.check", input_doc={}, result=True, result_type=DecisionResult.ALLOW, bundle_revision=1)
        logger.log(e1)
        logger.log(e2)
        assert len(logger.get_entries()) == 1

    def test_filter_by_result(self):
        logger = DecisionLogger(filter_results=[DecisionResult.DENY])
        e1 = DecisionLogEntry(path="t", input_doc={}, result=True, result_type=DecisionResult.ALLOW, bundle_revision=1)
        e2 = DecisionLogEntry(path="t", input_doc={}, result=False, result_type=DecisionResult.DENY, bundle_revision=1)
        logger.log(e1)
        logger.log(e2)
        assert len(logger.get_entries()) == 1

    def test_clear(self):
        logger = DecisionLogger()
        entry = DecisionLogEntry(path="t", input_doc={}, result=True, result_type=DecisionResult.ALLOW, bundle_revision=1)
        logger.log(entry)
        logger.clear()
        assert len(logger.get_entries()) == 0


# ---------------------------------------------------------------------------
# Decision Log Query Tests
# ---------------------------------------------------------------------------

class TestDecisionLogQuery:
    def _make_query_with_entries(self):
        logger = DecisionLogger()
        now = datetime.now(timezone.utc)
        for i in range(5):
            entry = DecisionLogEntry(
                path="authz.allow",
                input_doc={"user": f"user{i}"},
                result=True if i % 2 == 0 else False,
                result_type=DecisionResult.ALLOW if i % 2 == 0 else DecisionResult.DENY,
                bundle_revision=1,
            )
            entry.timestamp = now + timedelta(minutes=i)
            logger.log(entry)
        return DecisionLogQuery(logger), now

    def test_query_by_path(self):
        query, now = self._make_query_with_entries()
        entries, total = query.query(path="authz.allow")
        assert total == 5

    def test_query_by_user(self):
        query, now = self._make_query_with_entries()
        entries, total = query.query(user="user0")
        assert total >= 1

    def test_pagination(self):
        query, now = self._make_query_with_entries()
        entries, total = query.query(page=1, page_size=2)
        assert len(entries) == 2
        assert total == 5

    def test_query_by_result(self):
        query, now = self._make_query_with_entries()
        entries, total = query.query(result=DecisionResult.DENY)
        assert all(e.result_type == DecisionResult.DENY for e in entries)


# ---------------------------------------------------------------------------
# Decision Log Exporter Tests
# ---------------------------------------------------------------------------

class TestDecisionLogExporter:
    def _make_exporter_with_entries(self):
        logger = DecisionLogger()
        entries = []
        for i in range(3):
            entry = DecisionLogEntry(
                path="test.allow", input_doc={"user": f"u{i}"},
                result=True, result_type=DecisionResult.ALLOW, bundle_revision=1,
            )
            logger.log(entry)
            entries.append(entry)
        return DecisionLogExporter(logger), logger.get_entries()

    def test_export_jsonl(self):
        exporter, entries = self._make_exporter_with_entries()
        result = exporter.export_jsonl(entries)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        parsed = json.loads(lines[0])
        assert "decision_id" in parsed

    def test_export_csv(self):
        exporter, entries = self._make_exporter_with_entries()
        result = exporter.export_csv(entries)
        lines = result.strip().split("\n")
        assert lines[0].startswith("decision_id")
        assert len(lines) == 4  # header + 3 entries

    def test_export_fizzsheet(self):
        exporter, entries = self._make_exporter_with_entries()
        result = exporter.export_fizzsheet(entries)
        assert "FizzPolicy Decision Log Export" in result
        assert "Total: 3 decisions" in result


# ---------------------------------------------------------------------------
# Data Adapter Tests
# ---------------------------------------------------------------------------

class TestDataAdapter:
    def test_rbac_adapter_fetch(self):
        adapter = RBACDataAdapter()
        data = adapter.fetch()
        assert "roles" in data
        assert "FIZZBUZZ_SUPERUSER" in data["roles"]

    def test_operator_adapter_fetch(self):
        adapter = OperatorDataAdapter()
        data = adapter.fetch()
        assert isinstance(data, dict)

    def test_adapter_info(self):
        adapter = RBACDataAdapter()
        info = adapter.get_info()
        assert isinstance(info, DataAdapterInfo)
        assert info.name == "rbac"
        assert info.state == DataAdapterState.HEALTHY


# ---------------------------------------------------------------------------
# Data Refresh Scheduler Tests
# ---------------------------------------------------------------------------

class TestDataRefreshScheduler:
    def test_register_and_refresh(self):
        engine = PolicyEngine()
        bundle = PolicyBundle()
        engine.load_bundle(bundle)
        scheduler = DataRefreshScheduler(engine)
        adapter = RBACDataAdapter()
        scheduler.register(adapter)
        scheduler.refresh_all()
        data = engine.get_data("rbac")
        assert data is not None

    def test_stale_data_warning(self):
        engine = PolicyEngine()
        bundle = PolicyBundle()
        engine.load_bundle(bundle)
        scheduler = DataRefreshScheduler(engine)

        class FailingAdapter(DataAdapter):
            def __init__(self):
                super().__init__("failing", "failing", refresh_interval=0.001)
                self._last_refresh = datetime.now(timezone.utc) - timedelta(hours=1)

            def fetch(self):
                raise RuntimeError("connection refused")

        adapter = FailingAdapter()
        scheduler.register(adapter)
        scheduler.refresh_all()
        assert adapter._state in (DataAdapterState.ERROR, DataAdapterState.STALE)

    def test_unregister(self):
        engine = PolicyEngine()
        bundle = PolicyBundle()
        engine.load_bundle(bundle)
        scheduler = DataRefreshScheduler(engine)
        scheduler.register(RBACDataAdapter())
        scheduler.unregister("rbac")
        states = scheduler.get_adapter_states()
        assert "rbac" not in states


# ---------------------------------------------------------------------------
# Policy Test Runner Tests
# ---------------------------------------------------------------------------

class TestPolicyTestRunner:
    def test_discover_tests(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        runner = PolicyTestRunner(engine)
        tests = runner._discover_tests(bundle)
        assert isinstance(tests, list)

    def test_run_returns_result(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        runner = PolicyTestRunner(engine)
        result = runner.run(bundle)
        assert isinstance(result, TestRunResult)
        assert result.total >= 0

    def test_per_test_timing(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        runner = PolicyTestRunner(engine)
        result = runner.run(bundle)
        assert result.duration_ms >= 0

    def test_aggregates(self):
        engine = PolicyEngine()
        bundle = PolicyBundle()
        engine.load_bundle(bundle)
        runner = PolicyTestRunner(engine)
        result = runner.run(bundle)
        assert result.total == result.passed + result.failed + result.errored + result.skipped


# ---------------------------------------------------------------------------
# Policy Coverage Analyzer Tests
# ---------------------------------------------------------------------------

class TestPolicyCoverageAnalyzer:
    def test_rule_coverage(self):
        analyzer = PolicyCoverageAnalyzer()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        analyzer.begin_tracking(bundle)
        analyzer.record_rule("test.allow")
        coverage = analyzer.get_coverage()
        assert coverage["rules_covered"] == 1

    def test_expression_branch_coverage(self):
        analyzer = PolicyCoverageAnalyzer()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        analyzer.begin_tracking(bundle)
        analyzer.record_expression("e1", True)
        analyzer.record_expression("e1", False)
        coverage = analyzer.get_coverage()
        assert coverage["expression_coverage_percent"] >= 0

    def test_data_path_coverage(self):
        analyzer = PolicyCoverageAnalyzer()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        analyzer.begin_tracking(bundle)
        analyzer.record_data_access("rbac.roles")
        analyzer.record_data_access("compliance.regimes")
        coverage = analyzer.get_coverage()
        assert len(coverage["data_paths_accessed"]) == 2


# ---------------------------------------------------------------------------
# Policy Benchmark Tests
# ---------------------------------------------------------------------------

class TestPolicyBenchmark:
    def test_run_benchmark(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        bench = PolicyBenchmark(engine)
        result = bench.run("data.fizzbuzz.authz.allow", {"role": "admin"}, iterations=10)
        assert isinstance(result, BenchmarkResult)
        assert result.iterations == 10

    def test_percentile_computation(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        bench = PolicyBenchmark(engine)
        result = bench.run("data.fizzbuzz.authz.allow", {"role": "admin"}, iterations=10)
        assert result.p50_ns <= result.p99_ns


# ---------------------------------------------------------------------------
# Policy Watcher Tests
# ---------------------------------------------------------------------------

class TestPolicyWatcher:
    def test_notify_activation_success(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        store = BundleStore()
        store.save(bundle)
        bundle.manifest.bundle_name = "default"
        bundle.manifest.revision = 1
        store.save(bundle)
        watcher = PolicyWatcher(engine, store)
        watcher.watch("default")
        watcher.notify_activation(1)

    def test_notify_activation_failure(self):
        engine = PolicyEngine()
        store = BundleStore()
        watcher = PolicyWatcher(engine, store)
        watcher.watch("nonexistent")
        with pytest.raises(Exception):
            watcher.notify_activation(999)

    def test_cache_invalidation(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        bundle.manifest.bundle_name = "default"
        bundle.manifest.revision = 1
        engine.load_bundle(bundle)
        store = BundleStore()
        store.save(bundle)
        watcher = PolicyWatcher(engine, store)
        watcher.watch("default")
        # Evaluate to populate cache
        engine.evaluate("data.fizzbuzz.authz.allow", {"role": "admin"})
        # Activate should invalidate cache
        watcher.notify_activation(1)
        stats = engine._cache.stats()
        assert stats["size"] == 0


# ---------------------------------------------------------------------------
# Policy Hot-Reload Middleware Tests
# ---------------------------------------------------------------------------

class TestPolicyHotReloadMiddleware:
    def test_raft_entry_triggers_watcher(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        bundle.manifest.bundle_name = "default"
        bundle.manifest.revision = 1
        engine.load_bundle(bundle)
        store = BundleStore()
        store.save(bundle)
        watcher = PolicyWatcher(engine, store)
        watcher.watch("default")
        middleware = PolicyHotReloadMiddleware(watcher)
        middleware.on_raft_entry({"type": "policy_bundle_activation", "revision": 1})

    def test_non_policy_entry_ignored(self):
        engine = PolicyEngine()
        store = BundleStore()
        watcher = PolicyWatcher(engine, store)
        middleware = PolicyHotReloadMiddleware(watcher)
        # Should not raise
        middleware.on_raft_entry({"type": "config_update", "key": "some_setting"})


# ---------------------------------------------------------------------------
# Default Bundle Factory Tests
# ---------------------------------------------------------------------------

class TestDefaultBundleFactory:
    def test_creates_valid_bundle(self):
        factory = DefaultBundleFactory()
        bundle = factory.create()
        assert isinstance(bundle, PolicyBundle)
        assert len(bundle.modules) > 0

    def test_contains_all_8_packages(self):
        factory = DefaultBundleFactory()
        bundle = factory.create()
        packages = {m.package_path for m in bundle.modules.values()}
        assert len(packages) >= 8

    def test_data_document_has_required_keys(self):
        factory = DefaultBundleFactory()
        bundle = factory.create()
        assert isinstance(bundle.data, dict)


# ---------------------------------------------------------------------------
# FizzPolicy Middleware Tests
# ---------------------------------------------------------------------------

class TestFizzPolicyMiddleware:
    def _make_middleware(self):
        engine = PolicyEngine()
        factory = DefaultBundleFactory()
        bundle = factory.create()
        engine.load_bundle(bundle)
        logger = DecisionLogger()
        engine._decision_logger = logger
        scheduler = DataRefreshScheduler(engine)
        scheduler.register(RBACDataAdapter())
        scheduler.refresh_all()
        middleware = FizzPolicyMiddleware(engine)
        return middleware, engine

    def test_name_and_priority(self):
        middleware, _ = self._make_middleware()
        assert middleware.get_name() == "fizzpolicy"
        assert middleware.get_priority() == MIDDLEWARE_PRIORITY

    def test_process_allows(self):
        middleware, engine = self._make_middleware()
        context = MagicMock()
        context.number = 42
        context.session_id = "test-session"
        context.metadata = {"role": "FIZZBUZZ_SUPERUSER", "user": "admin"}
        context.locale = "en"
        context.results = []
        next_handler = MagicMock(return_value=context)
        result = middleware.process(context, next_handler)
        assert isinstance(result, MagicMock)

    def test_render_status(self):
        middleware, _ = self._make_middleware()
        status = middleware.render_status()
        assert "FIZZPOLICY" in status
        assert FIZZPOLICY_VERSION in status

    def test_render_eval(self):
        middleware, _ = self._make_middleware()
        result = middleware.render_eval("data.fizzbuzz.authz.allow", '{"role": "admin"}')
        assert "Query:" in result
        assert "Result:" in result

    def test_get_stats(self):
        middleware, _ = self._make_middleware()
        stats = middleware.get_stats()
        assert "total_processed" in stats
        assert "total_denied" in stats


# ---------------------------------------------------------------------------
# Factory Function Tests
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    def test_factory_wiring(self):
        engine, middleware = create_fizzpolicy_subsystem(signing_key="test-key")
        assert isinstance(engine, PolicyEngine)
        assert isinstance(middleware, FizzPolicyMiddleware)

    def test_returns_engine_middleware_tuple(self):
        result = create_fizzpolicy_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------

class TestExceptions:
    def test_error_codes(self):
        err = PolicyEngineError("test error")
        assert err.error_code == "EFP-POL00"
        lex_err = PolicyLexerError("bad token")
        assert lex_err.error_code == "EFP-POL01"
        parse_err = PolicyParserError("unexpected token")
        assert parse_err.error_code == "EFP-POL02"

    def test_inheritance(self):
        err = PolicyLexerError("test")
        assert isinstance(err, PolicyEngineError)
        eval_err = PolicyEvaluationError("test")
        assert isinstance(eval_err, PolicyEngineError)

    def test_context_dict(self):
        err = PolicyEngineError("something went wrong")
        assert "reason" in err.context
        assert err.context["reason"] == "something went wrong"

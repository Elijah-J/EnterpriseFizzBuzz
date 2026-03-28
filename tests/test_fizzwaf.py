"""
Enterprise FizzBuzz Platform - FizzWAF Tests

Comprehensive test suite for the FizzWAF Web Application Firewall subsystem.
Validates request inspection, threat detection across all major attack vectors,
rule lifecycle management, action enforcement, statistics tracking, middleware
integration, dashboard rendering, and factory wiring.

Tests cover:
- WAFRule creation and field defaults
- WAFEngine rule CRUD (add, remove, enable, disable, get, list)
- SQL injection pattern detection
- Cross-site scripting (XSS) pattern detection
- Command injection pattern detection
- Path traversal pattern detection
- Custom threat category support
- RuleAction.ALLOW vs BLOCK vs LOG behavior on inspection results
- Disabled rules excluded from inspection
- Inspection statistics tracking (total, blocked, allowed)
- InspectionResult field correctness
- FizzWAFMiddleware name, priority, and pipeline integration
- FizzWAFDashboard rendering
- create_fizzwaf_subsystem factory
- Module-level exports (FIZZWAF_VERSION, MIDDLEWARE_PRIORITY)
- Exception hierarchy (FizzWAFError, FizzWAFNotFoundError)
"""

from __future__ import annotations

import unittest

from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.fizzwaf import (
    FIZZWAF_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzWAFDashboard,
    FizzWAFMiddleware,
    InspectionResult,
    RuleAction,
    ThreatCategory,
    WAFEngine,
    WAFRule,
    create_fizzwaf_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzwaf import (
    FizzWAFError,
    FizzWAFNotFoundError,
)


# ---------------------------------------------------------------------------
# Test: Module-level exports
# ---------------------------------------------------------------------------

class TestModuleExports(unittest.TestCase):
    """Verify module-level constants are correctly exported."""

    def test_version_string(self):
        """FIZZWAF_VERSION should be a semantic version string."""
        self.assertEqual(FIZZWAF_VERSION, "1.0.0")

    def test_middleware_priority(self):
        """MIDDLEWARE_PRIORITY should be 219."""
        self.assertEqual(MIDDLEWARE_PRIORITY, 219)


# ---------------------------------------------------------------------------
# Test: RuleAction enum
# ---------------------------------------------------------------------------

class TestRuleAction(unittest.TestCase):
    """Verify the RuleAction enum members."""

    def test_has_allow(self):
        self.assertIsNotNone(RuleAction.ALLOW)

    def test_has_block(self):
        self.assertIsNotNone(RuleAction.BLOCK)

    def test_has_log(self):
        self.assertIsNotNone(RuleAction.LOG)


# ---------------------------------------------------------------------------
# Test: ThreatCategory enum
# ---------------------------------------------------------------------------

class TestThreatCategory(unittest.TestCase):
    """Verify the ThreatCategory enum members."""

    def test_all_categories_present(self):
        expected = {"SQL_INJECTION", "XSS", "COMMAND_INJECTION", "PATH_TRAVERSAL", "CUSTOM"}
        actual = {member.name for member in ThreatCategory}
        self.assertTrue(expected.issubset(actual))


# ---------------------------------------------------------------------------
# Test: WAFRule dataclass
# ---------------------------------------------------------------------------

class TestWAFRule(unittest.TestCase):
    """Verify WAFRule field defaults and structure."""

    def test_enabled_defaults_to_true(self):
        """Rules should be enabled by default upon creation."""
        rule = WAFRule(
            rule_id="r1",
            name="test",
            pattern=".*",
            category=ThreatCategory.CUSTOM,
            action=RuleAction.BLOCK,
        )
        self.assertTrue(rule.enabled)

    def test_fields_stored_correctly(self):
        """All fields should be stored as provided."""
        rule = WAFRule(
            rule_id="r2",
            name="Block XSS",
            pattern="<script>",
            category=ThreatCategory.XSS,
            action=RuleAction.BLOCK,
            enabled=False,
        )
        self.assertEqual(rule.rule_id, "r2")
        self.assertEqual(rule.name, "Block XSS")
        self.assertEqual(rule.pattern, "<script>")
        self.assertEqual(rule.category, ThreatCategory.XSS)
        self.assertEqual(rule.action, RuleAction.BLOCK)
        self.assertFalse(rule.enabled)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Rule CRUD
# ---------------------------------------------------------------------------

class TestWAFEngineRuleCRUD(unittest.TestCase):
    """Verify rule lifecycle operations on the WAF engine."""

    def setUp(self):
        self.engine = WAFEngine()

    def test_add_rule_returns_waf_rule(self):
        """add_rule should return a WAFRule with a generated rule_id."""
        rule = self.engine.add_rule(
            "Block SQLi", r"(?i)(union\s+select|drop\s+table)",
            ThreatCategory.SQL_INJECTION,
        )
        self.assertIsInstance(rule, WAFRule)
        self.assertTrue(len(rule.rule_id) > 0)
        self.assertEqual(rule.name, "Block SQLi")
        self.assertEqual(rule.action, RuleAction.BLOCK)

    def test_add_rule_with_custom_action(self):
        """add_rule should respect a non-default action parameter."""
        rule = self.engine.add_rule(
            "Log traversal", r"\.\./", ThreatCategory.PATH_TRAVERSAL,
            action=RuleAction.LOG,
        )
        self.assertEqual(rule.action, RuleAction.LOG)

    def test_get_rule_by_id(self):
        """get_rule should retrieve the rule matching the given ID."""
        added = self.engine.add_rule("test", r"x", ThreatCategory.CUSTOM)
        fetched = self.engine.get_rule(added.rule_id)
        self.assertEqual(fetched.rule_id, added.rule_id)

    def test_get_rule_nonexistent_raises(self):
        """get_rule for an unknown ID should raise FizzWAFNotFoundError."""
        with self.assertRaises(FizzWAFNotFoundError):
            self.engine.get_rule("nonexistent-id")

    def test_remove_rule(self):
        """remove_rule should delete the rule so it no longer appears in list_rules."""
        rule = self.engine.add_rule("temp", r"x", ThreatCategory.CUSTOM)
        self.engine.remove_rule(rule.rule_id)
        ids = [r.rule_id for r in self.engine.list_rules()]
        self.assertNotIn(rule.rule_id, ids)

    def test_remove_nonexistent_raises(self):
        """remove_rule for an unknown ID should raise FizzWAFNotFoundError."""
        with self.assertRaises(FizzWAFNotFoundError):
            self.engine.remove_rule("nonexistent-id")

    def test_disable_rule(self):
        """disable_rule should set enabled=False on the rule."""
        rule = self.engine.add_rule("r", r"x", ThreatCategory.CUSTOM)
        updated = self.engine.disable_rule(rule.rule_id)
        self.assertFalse(updated.enabled)

    def test_enable_rule(self):
        """enable_rule should set enabled=True on a previously disabled rule."""
        rule = self.engine.add_rule("r", r"x", ThreatCategory.CUSTOM)
        self.engine.disable_rule(rule.rule_id)
        updated = self.engine.enable_rule(rule.rule_id)
        self.assertTrue(updated.enabled)

    def test_list_rules_returns_all(self):
        """list_rules should return every registered rule."""
        self.engine.add_rule("a", r"x", ThreatCategory.CUSTOM)
        self.engine.add_rule("b", r"y", ThreatCategory.CUSTOM)
        self.assertEqual(len(self.engine.list_rules()), 2)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Inspection: SQL Injection
# ---------------------------------------------------------------------------

class TestInspectionSQLInjection(unittest.TestCase):
    """Verify that SQL injection patterns are correctly detected."""

    def setUp(self):
        self.engine = WAFEngine()
        self.engine.add_rule(
            "SQLi", r"(?i)(union\s+select|drop\s+table|;\s*delete\s+from)",
            ThreatCategory.SQL_INJECTION,
        )

    def test_blocks_union_select_in_path(self):
        result = self.engine.inspect("/search?q=1 UNION SELECT * FROM users")
        self.assertFalse(result.allowed)
        self.assertEqual(result.threat_category, ThreatCategory.SQL_INJECTION)

    def test_blocks_drop_table_in_body(self):
        result = self.engine.inspect("/api/data", request_body="DROP TABLE accounts")
        self.assertFalse(result.allowed)

    def test_allows_clean_request(self):
        result = self.engine.inspect("/api/fizzbuzz/15")
        self.assertTrue(result.allowed)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Inspection: XSS
# ---------------------------------------------------------------------------

class TestInspectionXSS(unittest.TestCase):
    """Verify that cross-site scripting patterns are correctly detected."""

    def setUp(self):
        self.engine = WAFEngine()
        self.engine.add_rule(
            "XSS", r"(?i)(<script|javascript:|on\w+=)",
            ThreatCategory.XSS,
        )

    def test_blocks_script_tag_in_body(self):
        result = self.engine.inspect("/post", request_body='<script>alert(1)</script>')
        self.assertFalse(result.allowed)
        self.assertEqual(result.threat_category, ThreatCategory.XSS)

    def test_blocks_javascript_uri_in_path(self):
        result = self.engine.inspect("/redirect?url=javascript:alert(1)")
        self.assertFalse(result.allowed)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Inspection: Command Injection
# ---------------------------------------------------------------------------

class TestInspectionCommandInjection(unittest.TestCase):
    """Verify that command injection patterns are correctly detected."""

    def setUp(self):
        self.engine = WAFEngine()
        self.engine.add_rule(
            "CmdInject", r"(?i)(;\s*(ls|cat|rm|wget|curl)\b|\|.*sh\b)",
            ThreatCategory.COMMAND_INJECTION,
        )

    def test_blocks_semicolon_command(self):
        result = self.engine.inspect("/api", request_body="; cat /etc/passwd")
        self.assertFalse(result.allowed)
        self.assertEqual(result.threat_category, ThreatCategory.COMMAND_INJECTION)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Inspection: Path Traversal
# ---------------------------------------------------------------------------

class TestInspectionPathTraversal(unittest.TestCase):
    """Verify that path traversal patterns are correctly detected."""

    def setUp(self):
        self.engine = WAFEngine()
        self.engine.add_rule(
            "PathTraversal", r"\.\./",
            ThreatCategory.PATH_TRAVERSAL,
        )

    def test_blocks_dot_dot_slash(self):
        result = self.engine.inspect("/files/../../../etc/passwd")
        self.assertFalse(result.allowed)
        self.assertEqual(result.threat_category, ThreatCategory.PATH_TRAVERSAL)

    def test_allows_normal_path(self):
        result = self.engine.inspect("/files/report.pdf")
        self.assertTrue(result.allowed)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Action Semantics
# ---------------------------------------------------------------------------

class TestRuleActions(unittest.TestCase):
    """Verify that ALLOW, BLOCK, and LOG actions produce correct inspection outcomes."""

    def setUp(self):
        self.engine = WAFEngine()

    def test_block_action_denies_request(self):
        """A matching BLOCK rule should set allowed=False."""
        self.engine.add_rule("block-test", r"malicious", ThreatCategory.CUSTOM, action=RuleAction.BLOCK)
        result = self.engine.inspect("/malicious")
        self.assertFalse(result.allowed)

    def test_allow_action_permits_request(self):
        """A matching ALLOW rule should not block the request."""
        self.engine.add_rule("allow-test", r"trusted", ThreatCategory.CUSTOM, action=RuleAction.ALLOW)
        result = self.engine.inspect("/trusted/endpoint")
        self.assertTrue(result.allowed)

    def test_log_action_permits_request(self):
        """A matching LOG rule should record the match but still allow the request."""
        rule = self.engine.add_rule("log-test", r"monitored", ThreatCategory.CUSTOM, action=RuleAction.LOG)
        result = self.engine.inspect("/monitored/path")
        self.assertTrue(result.allowed)
        self.assertIn(rule.rule_id, result.matched_rules)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Disabled Rules
# ---------------------------------------------------------------------------

class TestDisabledRulesSkipped(unittest.TestCase):
    """Verify that disabled rules are excluded from inspection."""

    def test_disabled_rule_does_not_block(self):
        engine = WAFEngine()
        rule = engine.add_rule("sqli", r"(?i)drop\s+table", ThreatCategory.SQL_INJECTION)
        engine.disable_rule(rule.rule_id)
        result = engine.inspect("/api", request_body="DROP TABLE users")
        self.assertTrue(result.allowed)
        self.assertEqual(len(result.matched_rules), 0)


# ---------------------------------------------------------------------------
# Test: WAFEngine - Statistics
# ---------------------------------------------------------------------------

class TestWAFEngineStats(unittest.TestCase):
    """Verify inspection statistics tracking."""

    def setUp(self):
        self.engine = WAFEngine()
        self.engine.add_rule("block-bad", r"bad", ThreatCategory.CUSTOM, action=RuleAction.BLOCK)

    def test_stats_initial_zero(self):
        stats = self.engine.get_stats()
        self.assertEqual(stats["total_inspections"], 0)
        self.assertEqual(stats["blocked_count"], 0)
        self.assertEqual(stats["allowed_count"], 0)

    def test_stats_after_mixed_traffic(self):
        """Stats should accurately reflect inspections across allowed and blocked requests."""
        self.engine.inspect("/clean/path")
        self.engine.inspect("/bad/path")
        self.engine.inspect("/also/clean")
        stats = self.engine.get_stats()
        self.assertEqual(stats["total_inspections"], 3)
        self.assertEqual(stats["blocked_count"], 1)
        self.assertEqual(stats["allowed_count"], 2)


# ---------------------------------------------------------------------------
# Test: InspectionResult
# ---------------------------------------------------------------------------

class TestInspectionResult(unittest.TestCase):
    """Verify InspectionResult dataclass fields."""

    def test_fields_present(self):
        result = InspectionResult(
            request_id="req-001",
            allowed=True,
            matched_rules=[],
            threat_category=None,
        )
        self.assertEqual(result.request_id, "req-001")
        self.assertTrue(result.allowed)
        self.assertEqual(result.matched_rules, [])
        self.assertIsNone(result.threat_category)

    def test_blocked_result_carries_threat_category(self):
        result = InspectionResult(
            request_id="req-002",
            allowed=False,
            matched_rules=["r1"],
            threat_category=ThreatCategory.XSS,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.threat_category, ThreatCategory.XSS)
        self.assertEqual(result.matched_rules, ["r1"])


# ---------------------------------------------------------------------------
# Test: FizzWAFMiddleware
# ---------------------------------------------------------------------------

class TestFizzWAFMiddleware(unittest.TestCase):
    """Verify FizzWAFMiddleware conforms to the IMiddleware contract."""

    def setUp(self):
        self.middleware = FizzWAFMiddleware()

    def test_get_name(self):
        self.assertEqual(self.middleware.get_name(), "fizzwaf")

    def test_get_priority(self):
        self.assertEqual(self.middleware.get_priority(), 219)

    def test_process_passes_context_through(self):
        """The middleware should invoke the next handler and return a ProcessingContext."""
        ctx = ProcessingContext(number=42, session_id="waf-test")

        def next_handler(c):
            c.metadata["pipeline_continued"] = True
            return c

        result = self.middleware.process(ctx, next_handler)
        self.assertIsInstance(result, ProcessingContext)
        self.assertTrue(result.metadata.get("pipeline_continued"))


# ---------------------------------------------------------------------------
# Test: FizzWAFDashboard
# ---------------------------------------------------------------------------

class TestFizzWAFDashboard(unittest.TestCase):
    """Verify dashboard rendering produces non-empty output."""

    def test_render_returns_string(self):
        dashboard = FizzWAFDashboard()
        output = dashboard.render()
        self.assertIsInstance(output, str)
        self.assertTrue(len(output) > 0)


# ---------------------------------------------------------------------------
# Test: Factory
# ---------------------------------------------------------------------------

class TestCreateFizzWAFSubsystem(unittest.TestCase):
    """Verify the factory function returns the expected subsystem components."""

    def test_returns_engine_dashboard_middleware(self):
        engine, dashboard, middleware = create_fizzwaf_subsystem()
        self.assertIsInstance(engine, WAFEngine)
        self.assertIsInstance(dashboard, FizzWAFDashboard)
        self.assertIsInstance(middleware, FizzWAFMiddleware)


# ---------------------------------------------------------------------------
# Test: Exception Hierarchy
# ---------------------------------------------------------------------------

class TestExceptionHierarchy(unittest.TestCase):
    """Verify FizzWAF exceptions follow the platform exception hierarchy."""

    def test_fizzwaf_error_is_base(self):
        self.assertTrue(issubclass(FizzWAFNotFoundError, FizzWAFError))

    def test_fizzwaf_error_is_catchable(self):
        with self.assertRaises(FizzWAFError):
            raise FizzWAFNotFoundError("rule not found")


if __name__ == "__main__":
    unittest.main()

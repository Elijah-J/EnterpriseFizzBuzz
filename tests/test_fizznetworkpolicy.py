"""
Tests for the FizzNetworkPolicy subsystem.

The Network Policy Engine provides microsegmentation, egress/ingress rule
evaluation, and DNS-based filtering for the Enterprise FizzBuzz platform.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from enterprise_fizzbuzz.infrastructure.fizznetworkpolicy import (
    FIZZNETWORKPOLICY_VERSION,
    MIDDLEWARE_PRIORITY,
    RuleAction,
    Direction,
    Protocol,
    FizzNetworkPolicyConfig,
    NetworkRule,
    PolicySet,
    NetworkPolicyEngine,
    DNSFilter,
    FizzNetworkPolicyDashboard,
    FizzNetworkPolicyMiddleware,
    create_fizznetworkpolicy_subsystem,
)


class TestConstants:
    """Verify module-level constants are correctly exported."""

    def test_version(self):
        assert FIZZNETWORKPOLICY_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 188


class TestNetworkPolicyEngine:
    """Tests for the core network policy evaluation engine."""

    def _make_engine(self):
        config = FizzNetworkPolicyConfig()
        return NetworkPolicyEngine(config)

    def _make_rule(self, **overrides):
        defaults = dict(
            rule_id="rule-1",
            name="test-rule",
            direction=Direction.INGRESS,
            action=RuleAction.ALLOW,
            source="10.0.0.0/24",
            destination="192.168.1.0/24",
            port=443,
            protocol=Protocol.TCP,
            priority=100,
        )
        defaults.update(overrides)
        return NetworkRule(**defaults)

    def test_add_rule(self):
        engine = self._make_engine()
        rule = self._make_rule()
        result = engine.add_rule(rule)
        assert result.rule_id == "rule-1"
        assert result.name == "test-rule"

    def test_evaluate_allow(self):
        engine = self._make_engine()
        rule = self._make_rule(
            action=RuleAction.ALLOW,
            source="10.0.0.1",
            destination="192.168.1.1",
            port=443,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
        )
        engine.add_rule(rule)
        result = engine.evaluate(
            source="10.0.0.1",
            destination="192.168.1.1",
            port=443,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
        )
        assert result == RuleAction.ALLOW

    def test_evaluate_deny(self):
        engine = self._make_engine()
        rule = self._make_rule(
            rule_id="deny-rule",
            action=RuleAction.DENY,
            source="10.0.0.1",
            destination="192.168.1.1",
            port=80,
            protocol=Protocol.TCP,
            direction=Direction.EGRESS,
        )
        engine.add_rule(rule)
        result = engine.evaluate(
            source="10.0.0.1",
            destination="192.168.1.1",
            port=80,
            protocol=Protocol.TCP,
            direction=Direction.EGRESS,
        )
        assert result == RuleAction.DENY

    def test_priority_ordering_higher_priority_wins(self):
        """When multiple rules match, the one with the highest priority value wins."""
        engine = self._make_engine()
        low_priority = self._make_rule(
            rule_id="low",
            action=RuleAction.ALLOW,
            source="10.0.0.1",
            destination="192.168.1.1",
            port=443,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
            priority=10,
        )
        high_priority = self._make_rule(
            rule_id="high",
            action=RuleAction.DENY,
            source="10.0.0.1",
            destination="192.168.1.1",
            port=443,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
            priority=999,
        )
        engine.add_rule(low_priority)
        engine.add_rule(high_priority)
        result = engine.evaluate(
            source="10.0.0.1",
            destination="192.168.1.1",
            port=443,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
        )
        # The higher priority (999) rule should win, which is DENY
        assert result == RuleAction.DENY

    def test_list_rules_by_direction(self):
        engine = self._make_engine()
        ingress_rule = self._make_rule(rule_id="in-1", direction=Direction.INGRESS)
        egress_rule = self._make_rule(rule_id="eg-1", direction=Direction.EGRESS)
        engine.add_rule(ingress_rule)
        engine.add_rule(egress_rule)
        ingress_rules = engine.list_rules(Direction.INGRESS)
        egress_rules = engine.list_rules(Direction.EGRESS)
        ingress_ids = [r.rule_id for r in ingress_rules]
        egress_ids = [r.rule_id for r in egress_rules]
        assert "in-1" in ingress_ids
        assert "eg-1" not in ingress_ids
        assert "eg-1" in egress_ids
        assert "in-1" not in egress_ids

    def test_create_and_get_policy_set(self):
        engine = self._make_engine()
        rule = self._make_rule()
        ps = engine.create_policy_set("web-tier", [rule], RuleAction.DENY)
        assert isinstance(ps, PolicySet)
        assert ps.name == "web-tier"
        retrieved = engine.get_policy_set("web-tier")
        assert retrieved.name == "web-tier"
        assert len(retrieved.rules) == 1
        assert retrieved.default_action == RuleAction.DENY

    def test_simulate_returns_matched_rule(self):
        engine = self._make_engine()
        rule = self._make_rule(
            rule_id="sim-rule",
            action=RuleAction.ALLOW,
            source="10.0.0.1",
            destination="192.168.1.1",
            port=8080,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
        )
        engine.add_rule(rule)
        result = engine.simulate(
            source="10.0.0.1",
            dest="192.168.1.1",
            port=8080,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
        )
        assert isinstance(result, dict)
        assert result["action"] == RuleAction.ALLOW
        assert result["matched_rule"] is not None
        assert result["matched_rule"].rule_id == "sim-rule"

    def test_default_action_when_no_rule_matches(self):
        """When no rule matches a given packet, evaluate returns the engine default action."""
        engine = self._make_engine()
        # Add a rule that will NOT match the query
        rule = self._make_rule(
            source="10.0.0.1",
            destination="192.168.1.1",
            port=443,
            protocol=Protocol.TCP,
            direction=Direction.INGRESS,
        )
        engine.add_rule(rule)
        # Query with completely different parameters so nothing matches
        result = engine.evaluate(
            source="172.16.0.99",
            destination="8.8.8.8",
            port=9999,
            protocol=Protocol.UDP,
            direction=Direction.EGRESS,
        )
        # Default action should be DENY (deny-by-default is standard network policy)
        assert result in (RuleAction.DENY, RuleAction.LOG)


class TestDNSFilter:
    """Tests for DNS-based domain filtering."""

    def _make_filter(self):
        return DNSFilter()

    def test_add_blocked_domain(self):
        dns = self._make_filter()
        dns.add_blocked_domain("malware.example.com")
        blocked = dns.list_blocked()
        assert "malware.example.com" in blocked

    def test_is_blocked_returns_true(self):
        dns = self._make_filter()
        dns.add_blocked_domain("evil.corp")
        assert dns.is_blocked("evil.corp") is True

    def test_not_blocked_returns_false(self):
        dns = self._make_filter()
        assert dns.is_blocked("safe.example.com") is False


class TestFizzNetworkPolicyDashboard:
    """Tests for the network policy dashboard renderer."""

    def _make_dashboard(self):
        config = FizzNetworkPolicyConfig()
        engine = NetworkPolicyEngine(config)
        return FizzNetworkPolicyDashboard(engine)

    def test_render_returns_string(self):
        dashboard = self._make_dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_network_info(self):
        dashboard = self._make_dashboard()
        output = dashboard.render()
        # Dashboard should contain recognizable network policy terminology
        output_lower = output.lower()
        assert any(
            term in output_lower
            for term in ["network", "policy", "rule", "fizznetworkpolicy"]
        )


class TestFizzNetworkPolicyMiddleware:
    """Tests for the middleware integration."""

    def _make_middleware(self):
        config = FizzNetworkPolicyConfig()
        engine = NetworkPolicyEngine(config)
        return FizzNetworkPolicyMiddleware(engine)

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "fizznetworkpolicy"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 188

    def test_process_calls_next(self):
        mw = self._make_middleware()
        ctx = MagicMock()
        next_handler = MagicMock()
        mw.process(ctx, next_handler)
        next_handler.assert_called_once()


class TestCreateSubsystem:
    """Tests for the factory function that wires the subsystem together."""

    def test_returns_tuple(self):
        result = create_fizznetworkpolicy_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_engine_works(self):
        engine, dashboard, middleware = create_fizznetworkpolicy_subsystem()
        assert isinstance(engine, NetworkPolicyEngine)
        rule = NetworkRule(
            rule_id="factory-test",
            name="factory-test-rule",
            direction=Direction.INGRESS,
            action=RuleAction.ALLOW,
            source="10.0.0.1",
            destination="10.0.0.2",
            port=80,
            protocol=Protocol.TCP,
            priority=50,
        )
        added = engine.add_rule(rule)
        assert added.rule_id == "factory-test"

    def test_has_default_rules(self):
        """The factory should produce an engine pre-loaded with baseline rules."""
        engine, _, _ = create_fizznetworkpolicy_subsystem()
        # Check that at least some default rules exist across directions
        ingress = engine.list_rules(Direction.INGRESS)
        egress = engine.list_rules(Direction.EGRESS)
        total = len(ingress) + len(egress)
        assert total > 0, "Factory should seed the engine with default network rules"

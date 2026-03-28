"""Enterprise FizzBuzz Platform - FizzWAF: Web Application Firewall"""
from __future__ import annotations
import logging, re, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzwaf import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzwaf")
EVENT_WAF = EventType.register("FIZZWAF_INSPECTION")
FIZZWAF_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 219


class RuleAction(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    LOG = "log"


class ThreatCategory(Enum):
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    CUSTOM = "custom"


@dataclass
class WAFRule:
    """A WAF rule matching a regex pattern to a threat category."""
    rule_id: str = ""
    name: str = ""
    pattern: str = ""
    category: ThreatCategory = ThreatCategory.CUSTOM
    action: RuleAction = RuleAction.BLOCK
    enabled: bool = True


@dataclass
class InspectionResult:
    """Result of inspecting a request against WAF rules."""
    request_id: str = ""
    allowed: bool = True
    matched_rules: List[str] = field(default_factory=list)
    threat_category: Optional[ThreatCategory] = None


@dataclass
class FizzWAFConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class WAFEngine:
    """Inspects incoming requests against configurable rule sets to detect
    and block common web application attacks."""

    def __init__(self) -> None:
        self._rules: OrderedDict[str, WAFRule] = OrderedDict()
        self._total_inspections = 0
        self._blocked_count = 0
        self._allowed_count = 0

    def add_rule(self, name: str, pattern: str, category: ThreatCategory,
                 action: RuleAction = RuleAction.BLOCK) -> WAFRule:
        """Add a WAF rule with a regex pattern."""
        rule_id = f"waf-{uuid.uuid4().hex[:8]}"
        rule = WAFRule(
            rule_id=rule_id,
            name=name,
            pattern=pattern,
            category=category,
            action=action,
        )
        self._rules[rule_id] = rule
        logger.debug("Added WAF rule %s: %s (%s)", rule_id, name, category.value)
        return rule

    def remove_rule(self, rule_id: str) -> None:
        """Remove a WAF rule."""
        if rule_id not in self._rules:
            raise FizzWAFNotFoundError(rule_id)
        del self._rules[rule_id]

    def enable_rule(self, rule_id: str) -> WAFRule:
        rule = self.get_rule(rule_id)
        rule.enabled = True
        return rule

    def disable_rule(self, rule_id: str) -> WAFRule:
        rule = self.get_rule(rule_id)
        rule.enabled = False
        return rule

    def get_rule(self, rule_id: str) -> WAFRule:
        rule = self._rules.get(rule_id)
        if rule is None:
            raise FizzWAFNotFoundError(rule_id)
        return rule

    def list_rules(self) -> List[WAFRule]:
        return list(self._rules.values())

    def inspect(self, request_path: str, request_body: str = "") -> InspectionResult:
        """Inspect a request against all enabled rules."""
        self._total_inspections += 1
        combined = request_path + " " + request_body
        matched = []
        blocked = False
        threat = None

        for rule in self._rules.values():
            if not rule.enabled:
                continue
            try:
                if re.search(rule.pattern, combined, re.IGNORECASE):
                    matched.append(rule.rule_id)
                    if rule.action == RuleAction.BLOCK:
                        blocked = True
                        threat = rule.category
                    elif rule.action == RuleAction.LOG:
                        if threat is None:
                            threat = rule.category
            except re.error:
                logger.warning("Invalid regex in rule %s: %s", rule.rule_id, rule.pattern)

        if blocked:
            self._blocked_count += 1
        else:
            self._allowed_count += 1

        return InspectionResult(
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            allowed=not blocked,
            matched_rules=matched,
            threat_category=threat if matched else None,
        )

    def get_stats(self) -> dict:
        return {
            "total_inspections": self._total_inspections,
            "blocked_count": self._blocked_count,
            "allowed_count": self._allowed_count,
        }


class FizzWAFDashboard:
    def __init__(self, engine: Optional[WAFEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzWAF Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZWAF_VERSION}"]
        if self._engine:
            stats = self._engine.get_stats()
            rules = self._engine.list_rules()
            lines.append(f"  Rules: {len(rules)}")
            lines.append(f"  Inspections: {stats['total_inspections']}")
            lines.append(f"  Blocked: {stats['blocked_count']}")
            lines.append(f"  Allowed: {stats['allowed_count']}")
            lines.append("-" * self._width)
            for r in rules[:10]:
                status = "ON" if r.enabled else "OFF"
                lines.append(f"  {r.name:<25} [{r.category.value}] {r.action.value} {status}")
        return "\n".join(lines)


class FizzWAFMiddleware(IMiddleware):
    def __init__(self, engine: Optional[WAFEngine] = None,
                 dashboard: Optional[FizzWAFDashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzwaf"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzwaf_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[WAFEngine, FizzWAFDashboard, FizzWAFMiddleware]:
    """Factory function that creates and wires the FizzWAF subsystem."""
    engine = WAFEngine()
    # OWASP Top 10 rule set for the FizzBuzz API
    engine.add_rule("SQL Injection", r"(?:union\s+select|;\s*drop\s|'\s*or\s+'1'\s*=\s*'1|--\s*$)",
                     ThreatCategory.SQL_INJECTION)
    engine.add_rule("XSS Script Tag", r"<\s*script[^>]*>",
                     ThreatCategory.XSS)
    engine.add_rule("XSS Event Handler", r"on(?:load|error|click|mouseover)\s*=",
                     ThreatCategory.XSS)
    engine.add_rule("Command Injection", r"(?:;\s*(?:ls|cat|rm|wget|curl)\b|\|\s*(?:sh|bash)\b|`[^`]+`)",
                     ThreatCategory.COMMAND_INJECTION)
    engine.add_rule("Path Traversal", r"(?:\.\./|\.\.\\|%2e%2e[/\\])",
                     ThreatCategory.PATH_TRAVERSAL)

    dashboard = FizzWAFDashboard(engine, dashboard_width)
    middleware = FizzWAFMiddleware(engine, dashboard)
    logger.info("FizzWAF initialized: %d rules", len(engine.list_rules()))
    return engine, dashboard, middleware

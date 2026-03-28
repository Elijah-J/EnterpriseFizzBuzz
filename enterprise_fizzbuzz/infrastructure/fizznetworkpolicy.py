"""
Enterprise FizzBuzz Platform - FizzNetworkPolicy: Network Policy Engine

Microsegmentation with ingress/egress rules, priority-based evaluation,
DNS-based filtering, policy sets, and simulation.

Architecture reference: Kubernetes NetworkPolicy, Calico, Cilium, AWS Security Groups.
"""

from __future__ import annotations

import fnmatch
import logging
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizznetworkpolicy import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizznetworkpolicy")
EVENT_NP_EVALUATED = EventType.register("FIZZNETWORKPOLICY_EVALUATED")

FIZZNETWORKPOLICY_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 188


class RuleAction(Enum):
    ALLOW = "allow"
    DENY = "deny"
    LOG = "log"

class Direction(Enum):
    INGRESS = "ingress"
    EGRESS = "egress"

class Protocol(Enum):
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    ANY = "any"


@dataclass
class FizzNetworkPolicyConfig:
    default_action: RuleAction = RuleAction.DENY
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class NetworkRule:
    rule_id: str = ""
    name: str = ""
    direction: Direction = Direction.INGRESS
    action: RuleAction = RuleAction.ALLOW
    source: str = "*"
    destination: str = "*"
    port: int = 0
    protocol: Protocol = Protocol.ANY
    priority: int = 100

@dataclass
class PolicySet:
    name: str = ""
    rules: List[NetworkRule] = field(default_factory=list)
    default_action: RuleAction = RuleAction.DENY


class NetworkPolicyEngine:
    """Network policy evaluation with priority-based rule matching."""

    def __init__(self, config_or_action: Any = None) -> None:
        self._rules: List[NetworkRule] = []
        self._policy_sets: Dict[str, PolicySet] = {}
        if isinstance(config_or_action, FizzNetworkPolicyConfig):
            self._default_action = config_or_action.default_action
        elif isinstance(config_or_action, RuleAction):
            self._default_action = config_or_action
        else:
            self._default_action = RuleAction.DENY

    def add_rule(self, rule: NetworkRule) -> NetworkRule:
        if not rule.rule_id:
            rule.rule_id = f"nr-{uuid.uuid4().hex[:8]}"
        self._rules.append(rule)
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    def evaluate(self, source: str, destination: str, port: int,
                 protocol: Protocol = Protocol.TCP,
                 direction: Direction = Direction.INGRESS) -> RuleAction:
        """Evaluate rules by priority (highest priority number wins)."""
        matching = []
        for rule in self._rules:
            if rule.direction != direction:
                continue
            if not self._matches(rule.source, source):
                continue
            if not self._matches(rule.destination, destination):
                continue
            if rule.port != 0 and rule.port != port:
                continue
            if rule.protocol != Protocol.ANY and rule.protocol != protocol:
                continue
            matching.append(rule)

        if not matching:
            return self._default_action

        # Highest priority wins
        best = max(matching, key=lambda r: r.priority)
        return best.action

    def list_rules(self, direction: Optional[Direction] = None) -> List[NetworkRule]:
        if direction is None:
            return list(self._rules)
        return [r for r in self._rules if r.direction == direction]

    def create_policy_set(self, name: str, rules: List[NetworkRule],
                          default_action: RuleAction = RuleAction.DENY) -> PolicySet:
        ps = PolicySet(name=name, rules=list(rules), default_action=default_action)
        self._policy_sets[name] = ps
        return ps

    def get_policy_set(self, name: str) -> Optional[PolicySet]:
        return self._policy_sets.get(name)

    def simulate(self, source: str, destination: str = "", port: int = 0,
                 protocol: Protocol = Protocol.TCP,
                 direction: Direction = Direction.INGRESS,
                 dest: str = "") -> Dict[str, Any]:
        destination = destination or dest
        """Simulate evaluation and return details about the matched rule."""
        matching = []
        for rule in self._rules:
            if rule.direction != direction:
                continue
            if not self._matches(rule.source, source):
                continue
            if not self._matches(rule.destination, destination):
                continue
            if rule.port != 0 and rule.port != port:
                continue
            if rule.protocol != Protocol.ANY and rule.protocol != protocol:
                continue
            matching.append(rule)

        if not matching:
            return {"action": self._default_action, "matched_rule": None, "reason": "default"}

        best = max(matching, key=lambda r: r.priority)
        return {
            "action": best.action,
            "matched_rule": best,
            "rule_name": best.name,
            "priority": best.priority,
            "reason": "matched",
        }

    def _matches(self, pattern: str, value: str) -> bool:
        if pattern == "*":
            return True
        return fnmatch.fnmatch(value, pattern)


class DNSFilter:
    """DNS-based domain filtering."""

    def __init__(self) -> None:
        self._blocked: set = set()

    def add_blocked_domain(self, domain: str) -> None:
        self._blocked.add(domain.lower())

    def is_blocked(self, domain: str) -> bool:
        domain = domain.lower()
        # Check exact match and parent domain match
        if domain in self._blocked:
            return True
        parts = domain.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[i:])
            if parent in self._blocked:
                return True
        return False

    def list_blocked(self) -> List[str]:
        return sorted(self._blocked)


class FizzNetworkPolicyDashboard:
    def __init__(self, engine: Optional[NetworkPolicyEngine] = None,
                 dns: Optional[DNSFilter] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._dns = dns
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width,
                 "FizzNetworkPolicy Dashboard".center(self._width),
                 "=" * self._width,
                 f"  Version: {FIZZNETWORKPOLICY_VERSION}"]
        if self._engine:
            rules = self._engine.list_rules()
            lines.append(f"  Rules:    {len(rules)}")
            for r in rules[:5]:
                lines.append(f"  {r.rule_id} {r.direction.value:<8} {r.action.value:<5} {r.source}->{r.destination}:{r.port}")
        if self._dns:
            lines.append(f"  Blocked:  {len(self._dns.list_blocked())} domains")
        return "\n".join(lines)


class FizzNetworkPolicyMiddleware(IMiddleware):
    def __init__(self, engine: Optional[NetworkPolicyEngine] = None,
                 dashboard: Optional[FizzNetworkPolicyDashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizznetworkpolicy"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizznetworkpolicy_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[NetworkPolicyEngine, FizzNetworkPolicyDashboard, FizzNetworkPolicyMiddleware]:
    engine = NetworkPolicyEngine()
    dns = DNSFilter()

    # Default rules
    engine.add_rule(NetworkRule(name="allow-fizzbuzz-ingress", direction=Direction.INGRESS,
                                action=RuleAction.ALLOW, source="10.0.0.0/8",
                                destination="fizzbuzz-service", port=8080, priority=100))
    engine.add_rule(NetworkRule(name="allow-dns-egress", direction=Direction.EGRESS,
                                action=RuleAction.ALLOW, destination="*", port=53, priority=100))
    engine.add_rule(NetworkRule(name="deny-external-ingress", direction=Direction.INGRESS,
                                action=RuleAction.DENY, source="*", destination="*", priority=1))

    # Default DNS blocks
    dns.add_blocked_domain("malware.example.com")
    dns.add_blocked_domain("phishing.example.net")

    dashboard = FizzNetworkPolicyDashboard(engine, dns, dashboard_width)
    middleware = FizzNetworkPolicyMiddleware(engine, dashboard)

    logger.info("FizzNetworkPolicy initialized: %d rules, %d blocked domains",
                len(engine.list_rules()), len(dns.list_blocked()))
    return engine, dashboard, middleware

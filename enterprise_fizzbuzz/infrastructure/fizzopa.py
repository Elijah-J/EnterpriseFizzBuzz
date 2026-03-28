"""Enterprise FizzBuzz Platform - FizzOPA: Open Policy Agent"""
from __future__ import annotations
import logging, re, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzopa import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzopa")
EVENT_OPA = EventType.register("FIZZOPA_EVALUATED")
FIZZOPA_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 227


class PolicyResult(Enum):
    ALLOW = "allow"; DENY = "deny"; UNDECIDED = "undecided"


@dataclass
class Policy:
    policy_id: str = ""; name: str = ""
    rules: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class EvaluationResult:
    policy_id: str = ""; result: PolicyResult = PolicyResult.UNDECIDED
    matched_rules: List[str] = field(default_factory=list)
    input_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FizzOPAConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class PolicyEngine:
    """Evaluates Rego-style policies against input data for access control
    and FizzBuzz operational policy enforcement."""

    def __init__(self) -> None:
        self._policies: OrderedDict[str, Policy] = OrderedDict()

    def add_policy(self, name: str, rules: List[str]) -> Policy:
        policy = Policy(policy_id=f"pol-{uuid.uuid4().hex[:8]}", name=name, rules=list(rules))
        self._policies[policy.policy_id] = policy
        return policy

    def remove_policy(self, policy_id: str) -> None:
        if policy_id not in self._policies:
            raise FizzOPANotFoundError(policy_id)
        del self._policies[policy_id]

    def enable_policy(self, policy_id: str) -> Policy:
        p = self.get_policy(policy_id); p.enabled = True; return p

    def disable_policy(self, policy_id: str) -> Policy:
        p = self.get_policy(policy_id); p.enabled = False; return p

    def get_policy(self, policy_id: str) -> Policy:
        p = self._policies.get(policy_id)
        if p is None: raise FizzOPANotFoundError(policy_id)
        return p

    def list_policies(self) -> List[Policy]:
        return list(self._policies.values())

    def evaluate(self, input_data: dict) -> List[EvaluationResult]:
        results = []
        for policy in self._policies.values():
            if not policy.enabled:
                continue
            matched = []
            for rule in policy.rules:
                if self._evaluate_rule(rule, input_data):
                    matched.append(rule)
            result = PolicyResult.ALLOW if matched else PolicyResult.UNDECIDED
            results.append(EvaluationResult(
                policy_id=policy.policy_id, result=result,
                matched_rules=matched, input_data=input_data,
            ))
        return results

    def decide(self, input_data: dict) -> PolicyResult:
        results = self.evaluate(input_data)
        for r in results:
            if r.result == PolicyResult.ALLOW:
                return PolicyResult.ALLOW
        for r in results:
            if r.result == PolicyResult.DENY:
                return PolicyResult.DENY
        return PolicyResult.UNDECIDED

    def _evaluate_rule(self, rule: str, input_data: dict) -> bool:
        """Evaluate a simple Rego-style rule expression."""
        expr = rule
        for key, value in input_data.items():
            pattern = f"input.{key}"
            if isinstance(value, str):
                expr = expr.replace(pattern, repr(value))
            else:
                expr = expr.replace(pattern, str(value))
        try:
            return bool(eval(expr))  # noqa: S307
        except Exception:
            return False


class FizzOPADashboard:
    def __init__(self, engine: Optional[PolicyEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzOPA Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZOPA_VERSION}"]
        if self._engine:
            policies = self._engine.list_policies()
            lines.append(f"  Policies: {len(policies)}")
            active = sum(1 for p in policies if p.enabled)
            lines.append(f"  Active: {active}")
        return "\n".join(lines)


class FizzOPAMiddleware(IMiddleware):
    def __init__(self, engine: Optional[PolicyEngine] = None,
                 dashboard: Optional[FizzOPADashboard] = None) -> None:
        self._engine = engine; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzopa"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzopa_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[PolicyEngine, FizzOPADashboard, FizzOPAMiddleware]:
    engine = PolicyEngine()
    engine.add_policy("fizzbuzz_access", ["input.role == 'admin'", "input.role == 'operator'"])
    engine.add_policy("divisibility_check", ["input.number % 3 == 0", "input.number % 5 == 0"])
    dashboard = FizzOPADashboard(engine, dashboard_width)
    middleware = FizzOPAMiddleware(engine, dashboard)
    logger.info("FizzOPA initialized: %d policies", len(engine.list_policies()))
    return engine, dashboard, middleware

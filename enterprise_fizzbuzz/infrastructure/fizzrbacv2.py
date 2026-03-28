"""
Enterprise FizzBuzz Platform - FizzRBACV2: Role-Based Access Control V2

Attribute-based policies, OAuth scope enforcement, permission inheritance.

Architecture reference: AWS IAM, OPA, Casbin, Keycloak Authorization.
"""

from __future__ import annotations

import fnmatch
import logging
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzrbacv2 import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzrbacv2")
EVENT_RBAC_EVALUATED = EventType.register("FIZZRBACV2_EVALUATED")

FIZZRBACV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 184


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"

class PolicyEffect(Enum):
    PERMIT = "permit"
    DENY_EFFECT = "deny"


@dataclass
class FizzRBACV2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Role:
    role_id: str = ""
    name: str = ""
    permissions: Set[str] = field(default_factory=set)
    parent_role: Optional[str] = None

@dataclass
class Policy:
    policy_id: str = ""
    name: str = ""
    effect: PolicyEffect = PolicyEffect.PERMIT
    resource: str = ""
    actions: List[str] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AccessRequest:
    subject: str = ""
    resource: str = ""
    action: str = ""
    context: Dict[str, Any] = field(default_factory=dict)


class RoleManager:
    """Role management with permission inheritance through parent chain."""

    def __init__(self) -> None:
        self._roles: OrderedDict[str, Role] = OrderedDict()
        self._assignments: Dict[str, List[str]] = defaultdict(list)  # subject -> [role_name]

    def create_role(self, name: str, permissions: Optional[Set[str]] = None,
                    parent_role: Optional[str] = None) -> Role:
        role = Role(
            role_id=f"role-{uuid.uuid4().hex[:8]}",
            name=name,
            permissions=set(permissions) if permissions else set(),
            parent_role=parent_role,
        )
        self._roles[name] = role
        return role

    def get_role(self, name: str) -> Role:
        role = self._roles.get(name)
        if role is None:
            raise FizzRBACV2RoleNotFoundError(name)
        return role

    def list_roles(self) -> List[Role]:
        return list(self._roles.values())

    def get_effective_permissions(self, role_name: str) -> Set[str]:
        """Get all permissions including inherited from parent chain."""
        permissions = set()
        current = role_name
        visited = set()
        while current and current not in visited:
            visited.add(current)
            role = self._roles.get(current)
            if role is None:
                break
            permissions |= role.permissions
            current = role.parent_role
        return permissions

    def assign_role(self, subject: str, role_name: str) -> None:
        self.get_role(role_name)  # Validate exists
        if role_name not in self._assignments[subject]:
            self._assignments[subject].append(role_name)

    def get_subject_roles(self, subject: str) -> List[Role]:
        role_names = self._assignments.get(subject, [])
        return [self._roles[n] for n in role_names if n in self._roles]


class PolicyEngine:
    """Policy evaluation engine with condition-based matching."""

    def __init__(self) -> None:
        self._policies: List[Policy] = []

    def add_policy(self, policy: Policy) -> Policy:
        self._policies.append(policy)
        return policy

    def evaluate(self, request: AccessRequest) -> Decision:
        """Evaluate an access request against all policies.
        DENY takes precedence over PERMIT. Default is DENY."""
        matched_permit = False

        for policy in self._policies:
            # Check resource match
            if not self._resource_matches(policy.resource, request.resource):
                continue
            # Check action match
            if request.action not in policy.actions:
                continue
            # Check conditions
            if policy.conditions:
                if not all(request.context.get(k) == v for k, v in policy.conditions.items()):
                    continue

            # Policy matched
            if policy.effect == PolicyEffect.DENY_EFFECT:
                return Decision.DENY
            elif policy.effect == PolicyEffect.PERMIT:
                matched_permit = True

        return Decision.ALLOW if matched_permit else Decision.DENY

    def list_policies(self) -> List[Policy]:
        return list(self._policies)

    def _resource_matches(self, pattern: str, resource: str) -> bool:
        return fnmatch.fnmatch(resource, pattern)


class ScopeValidator:
    """OAuth scope validation."""

    def validate_scopes(self, required_scopes: Set[str], granted_scopes: Set[str]) -> bool:
        if "*" in granted_scopes:
            return True
        return required_scopes.issubset(granted_scopes)


class FizzRBACV2Dashboard:
    def __init__(self, role_mgr: Optional[RoleManager] = None,
                 policy_eng: Optional[PolicyEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._roles = role_mgr
        self._policies = policy_eng
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width,
                 "FizzRBACV2 Access Control Dashboard".center(self._width),
                 "=" * self._width,
                 f"  Version: {FIZZRBACV2_VERSION}"]
        if self._roles:
            lines.append(f"  Roles: {len(self._roles.list_roles())}")
            for r in self._roles.list_roles():
                parent = f" (inherits: {r.parent_role})" if r.parent_role else ""
                lines.append(f"  {r.name:<20} perms={len(r.permissions)}{parent}")
        if self._policies:
            lines.append(f"  Policies: {len(self._policies.list_policies())}")
        return "\n".join(lines)


class FizzRBACV2Middleware(IMiddleware):
    def __init__(self, role_mgr: Optional[RoleManager] = None,
                 policy_eng: Optional[PolicyEngine] = None,
                 dashboard: Optional[FizzRBACV2Dashboard] = None) -> None:
        self._roles = role_mgr
        self._policies = policy_eng
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzrbacv2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzrbacv2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[RoleManager, PolicyEngine, FizzRBACV2Dashboard, FizzRBACV2Middleware]:
    role_mgr = RoleManager()
    policy_eng = PolicyEngine()

    # Default roles with inheritance
    role_mgr.create_role("viewer", {"fizzbuzz:read", "metrics:read"})
    role_mgr.create_role("operator", {"fizzbuzz:write", "config:read"}, parent_role="viewer")
    role_mgr.create_role("admin", {"admin:all", "config:write"}, parent_role="operator")

    # Default policies
    policy_eng.add_policy(Policy(policy_id="pol-read", name="allow-read",
                                  effect=PolicyEffect.PERMIT, resource="fizzbuzz:*",
                                  actions=["read"]))
    policy_eng.add_policy(Policy(policy_id="pol-admin", name="allow-admin",
                                  effect=PolicyEffect.PERMIT, resource="*",
                                  actions=["read", "write", "delete", "admin"],
                                  conditions={"role": "admin"}))

    # Default assignments
    role_mgr.assign_role("bob.mcfizzington", "admin")

    dashboard = FizzRBACV2Dashboard(role_mgr, policy_eng, dashboard_width)
    middleware = FizzRBACV2Middleware(role_mgr, policy_eng, dashboard)

    logger.info("FizzRBACV2 initialized: %d roles, %d policies",
                len(role_mgr.list_roles()), len(policy_eng.list_policies()))
    return role_mgr, policy_eng, dashboard, middleware

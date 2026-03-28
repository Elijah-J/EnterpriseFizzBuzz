"""Enterprise FizzBuzz Platform - FizzSemVer: Semantic Versioning Constraint Solver"""
from __future__ import annotations
import logging, re
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzsemver import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzsemver")
EVENT_SEMVER = EventType.register("FIZZSEMVER_RESOLVED")
FIZZSEMVER_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 217

SEMVER_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?(?:\+([a-zA-Z0-9.]+))?$"
)


@dataclass
class SemanticVersion:
    """A semantic version following SemVer 2.0.0 specification."""
    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    build: str = ""

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base += f"-{self.prerelease}"
        if self.build:
            base += f"+{self.build}"
        return base

    def _tuple(self) -> tuple:
        """Version tuple for comparison. Pre-release versions have lower
        precedence than release versions."""
        pre = (0, self.prerelease) if self.prerelease else (1, "")
        return (self.major, self.minor, self.patch, pre)

    def __lt__(self, other: SemanticVersion) -> bool:
        return self._tuple() < other._tuple()

    def __le__(self, other: SemanticVersion) -> bool:
        return self._tuple() <= other._tuple()

    def __gt__(self, other: SemanticVersion) -> bool:
        return self._tuple() > other._tuple()

    def __ge__(self, other: SemanticVersion) -> bool:
        return self._tuple() >= other._tuple()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._tuple() == other._tuple()

    def __hash__(self) -> int:
        return hash(self._tuple())


@dataclass
class VersionConstraint:
    """A version constraint with an operator and target version."""
    operator: str = "="
    version: SemanticVersion = field(default_factory=SemanticVersion)


@dataclass
class FizzSemVerConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class VersionResolver:
    """Resolves semantic version constraints, detects conflicts, and finds
    the highest satisfying version from a set of available versions."""

    def parse(self, version_string: str) -> SemanticVersion:
        """Parse a version string into a SemanticVersion."""
        match = SEMVER_RE.match(version_string.strip())
        if not match:
            raise FizzSemVerParseError(version_string)
        return SemanticVersion(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
            build=match.group(5) or "",
        )

    def satisfies(self, version: SemanticVersion,
                  constraint: VersionConstraint) -> bool:
        """Check if a version satisfies a constraint.

        Operators:
          =   exact match
          >=  greater than or equal
          <=  less than or equal
          >   greater than
          <   less than
          ^   caret (compatible: same major, minor+patch can increase)
          ~>  tilde (pessimistic: same major.minor, patch can increase)
        """
        cv = constraint.version
        op = constraint.operator
        if op == "=":
            return version == cv
        elif op == ">=":
            return version >= cv
        elif op == "<=":
            return version <= cv
        elif op == ">":
            return version > cv
        elif op == "<":
            return version < cv
        elif op == "^":
            # Same major version, at least the constraint version
            if cv.major == 0:
                return version.major == cv.major and version.minor == cv.minor and version.patch >= cv.patch
            return version.major == cv.major and version >= cv
        elif op == "~>":
            # Same major.minor, patch can be >= constraint patch
            return (version.major == cv.major and
                    version.minor == cv.minor and
                    version.patch >= cv.patch)
        else:
            raise FizzSemVerError(f"Unknown operator: {op}")

    def resolve(self, constraints: List[VersionConstraint],
                available: List[SemanticVersion]) -> Optional[SemanticVersion]:
        """Find the highest version from available that satisfies all constraints."""
        candidates = [
            v for v in available
            if all(self.satisfies(v, c) for c in constraints)
        ]
        if not candidates:
            return None
        return max(candidates)

    def check_conflicts(self, constraints: List[VersionConstraint]) -> List[str]:
        """Check for obvious conflicts between constraints."""
        conflicts = []
        for i, c1 in enumerate(constraints):
            for c2 in constraints[i + 1:]:
                # Check for direct contradictions
                if c1.operator == "=" and c2.operator == "=":
                    if c1.version != c2.version:
                        conflicts.append(
                            f"Conflict: ={c1.version} vs ={c2.version}"
                        )
                elif c1.operator == ">" and c2.operator == "<":
                    if c1.version >= c2.version:
                        conflicts.append(
                            f"Conflict: >{c1.version} vs <{c2.version}"
                        )
                elif c1.operator == "<" and c2.operator == ">":
                    if c2.version >= c1.version:
                        conflicts.append(
                            f"Conflict: <{c1.version} vs >{c2.version}"
                        )
        return conflicts


class FizzSemVerDashboard:
    def __init__(self, resolver: Optional[VersionResolver] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._resolver = resolver
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzSemVer Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZSEMVER_VERSION}"]
        if self._resolver:
            lines.append("  Resolver: Active")
            lines.append("  Supported Operators: =, >=, <=, >, <, ^, ~>")
        return "\n".join(lines)


class FizzSemVerMiddleware(IMiddleware):
    def __init__(self, resolver: Optional[VersionResolver] = None,
                 dashboard: Optional[FizzSemVerDashboard] = None) -> None:
        self._resolver = resolver
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzsemver"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzsemver_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[VersionResolver, FizzSemVerDashboard, FizzSemVerMiddleware]:
    """Factory function that creates and wires the FizzSemVer subsystem."""
    resolver = VersionResolver()
    dashboard = FizzSemVerDashboard(resolver, dashboard_width)
    middleware = FizzSemVerMiddleware(resolver, dashboard)
    logger.info("FizzSemVer initialized")
    return resolver, dashboard, middleware

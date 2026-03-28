"""Enterprise FizzBuzz Platform - FizzRelease: Release Management"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzrelease import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzrelease")
EVENT_RELEASE = EventType.register("FIZZRELEASE_PROMOTED")
FIZZRELEASE_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 213


class ReleaseState(Enum):
    DRAFT = "draft"
    CANDIDATE = "candidate"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class ReleaseChange:
    """A single change included in a release."""
    change_id: str = ""
    description: str = ""
    subsystem: str = ""


@dataclass
class Release:
    """A versioned group of changes promoted through environments."""
    release_id: str = ""
    version: str = ""
    name: str = ""
    state: ReleaseState = ReleaseState.DRAFT
    changes: List[ReleaseChange] = field(default_factory=list)
    current_environment: Optional[Environment] = None
    created_at: Optional[str] = None
    promoted_at: Optional[str] = None
    health_score: float = 1.0


@dataclass
class FizzReleaseConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class ReleaseManager:
    """Manages coordinated multi-subsystem releases with environment promotion,
    gate checks, and post-deployment health tracking."""

    PROMOTION_ORDER = [Environment.DEVELOPMENT, Environment.STAGING, Environment.PRODUCTION]

    def __init__(self) -> None:
        self._releases: OrderedDict[str, Release] = OrderedDict()

    def create_release(self, version: str, name: str = "") -> Release:
        """Create a new release in DRAFT state."""
        release_id = f"release-{uuid.uuid4().hex[:8]}"
        release = Release(
            release_id=release_id,
            version=version,
            name=name or f"Release {version}",
            state=ReleaseState.DRAFT,
            created_at=datetime.utcnow().isoformat(),
        )
        self._releases[release_id] = release
        logger.debug("Created release %s: %s", release_id, version)
        return release

    def add_change(self, release_id: str, description: str,
                   subsystem: str = "") -> ReleaseChange:
        """Add a change to a DRAFT release."""
        release = self.get_release(release_id)
        if release.state != ReleaseState.DRAFT:
            raise FizzReleaseStateError(
                f"Cannot add changes to {release.state.value} release {release_id}"
            )
        change = ReleaseChange(
            change_id=f"change-{uuid.uuid4().hex[:8]}",
            description=description,
            subsystem=subsystem,
        )
        release.changes.append(change)
        return change

    def finalize(self, release_id: str) -> Release:
        """Move a DRAFT release to CANDIDATE state, ready for promotion."""
        release = self.get_release(release_id)
        if release.state != ReleaseState.DRAFT:
            raise FizzReleaseStateError(
                f"Only DRAFT releases can be finalized, current: {release.state.value}"
            )
        release.state = ReleaseState.CANDIDATE
        return release

    def promote(self, release_id: str) -> Release:
        """Promote a release to the next environment in the pipeline.

        CANDIDATE -> DEVELOPMENT -> STAGING -> PRODUCTION.
        Sets state to DEPLOYING during promotion, then DEPLOYED."""
        release = self.get_release(release_id)
        if release.state not in (ReleaseState.CANDIDATE, ReleaseState.DEPLOYED):
            raise FizzReleaseStateError(
                f"Cannot promote release in {release.state.value} state"
            )

        if release.current_environment is None:
            next_env = Environment.DEVELOPMENT
        else:
            idx = self.PROMOTION_ORDER.index(release.current_environment)
            if idx >= len(self.PROMOTION_ORDER) - 1:
                raise FizzReleaseStateError(
                    f"Release already at {release.current_environment.value}, cannot promote further"
                )
            next_env = self.PROMOTION_ORDER[idx + 1]

        release.state = ReleaseState.DEPLOYED
        release.current_environment = next_env
        release.promoted_at = datetime.utcnow().isoformat()
        logger.info("Promoted release %s to %s", release_id, next_env.value)
        return release

    def rollback(self, release_id: str) -> Release:
        """Roll back a deployed release."""
        release = self.get_release(release_id)
        if release.state != ReleaseState.DEPLOYED:
            raise FizzReleaseStateError(
                f"Only DEPLOYED releases can be rolled back, current: {release.state.value}"
            )
        release.state = ReleaseState.ROLLED_BACK
        logger.info("Rolled back release %s from %s", release_id,
                      release.current_environment.value if release.current_environment else "unknown")
        return release

    def update_health(self, release_id: str, health_score: float) -> Release:
        """Update the health score of a deployed release."""
        release = self.get_release(release_id)
        release.health_score = max(0.0, min(1.0, health_score))
        return release

    def get_release(self, release_id: str) -> Release:
        """Retrieve a release by ID."""
        release = self._releases.get(release_id)
        if release is None:
            raise FizzReleaseNotFoundError(release_id)
        return release

    def list_releases(self) -> List[Release]:
        """Return all releases."""
        return list(self._releases.values())

    def get_releases_by_state(self, state: ReleaseState) -> List[Release]:
        """Return all releases in the given state."""
        return [r for r in self._releases.values() if r.state == state]

    def get_releases_in_environment(self, env: Environment) -> List[Release]:
        """Return all deployed releases in a specific environment."""
        return [r for r in self._releases.values()
                if r.current_environment == env and r.state == ReleaseState.DEPLOYED]


class FizzReleaseDashboard:
    def __init__(self, manager: Optional[ReleaseManager] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._manager = manager
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzRelease Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZRELEASE_VERSION}"]
        if self._manager:
            releases = self._manager.list_releases()
            lines.append(f"  Releases: {len(releases)}")
            lines.append("-" * self._width)
            for r in releases[:10]:
                env = r.current_environment.value if r.current_environment else "none"
                lines.append(
                    f"  {r.version:<12} {r.name:<20} [{r.state.value}] "
                    f"env={env} health={r.health_score:.0%}"
                )
        return "\n".join(lines)


class FizzReleaseMiddleware(IMiddleware):
    def __init__(self, manager: Optional[ReleaseManager] = None,
                 dashboard: Optional[FizzReleaseDashboard] = None) -> None:
        self._manager = manager
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzrelease"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzrelease_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[ReleaseManager, FizzReleaseDashboard, FizzReleaseMiddleware]:
    """Factory function that creates and wires the FizzRelease subsystem."""
    manager = ReleaseManager()
    # Create a sample release for the current platform version
    rel = manager.create_release("27.0.0", "Platform Maturity Release")
    manager.add_change(rel.release_id, "Add dependency injection lifecycle management", "fizzdilifecycle")
    manager.add_change(rel.release_id, "Add platform health aggregation", "fizzhealthaggregator")
    manager.add_change(rel.release_id, "Add schema contract testing", "fizzschemacontract")
    manager.finalize(rel.release_id)
    manager.promote(rel.release_id)  # -> development

    dashboard = FizzReleaseDashboard(manager, dashboard_width)
    middleware = FizzReleaseMiddleware(manager, dashboard)
    logger.info("FizzRelease initialized: %d releases", len(manager.list_releases()))
    return manager, dashboard, middleware

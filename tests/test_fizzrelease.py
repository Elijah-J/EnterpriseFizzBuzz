"""
Tests for enterprise_fizzbuzz.infrastructure.fizzrelease

Release Management subsystem that groups changes into versioned releases
and promotes them through deployment environments (development, staging,
production) with full lifecycle governance.
"""

import pytest

from enterprise_fizzbuzz.infrastructure.fizzrelease import (
    FIZZRELEASE_VERSION,
    MIDDLEWARE_PRIORITY,
    ReleaseState,
    Environment,
    ReleaseChange,
    Release,
    FizzReleaseConfig,
    ReleaseManager,
    FizzReleaseDashboard,
    FizzReleaseMiddleware,
    create_fizzrelease_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzrelease import (
    FizzReleaseError,
    FizzReleaseNotFoundError,
    FizzReleaseStateError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    return ReleaseManager()


@pytest.fixture
def draft_release(manager):
    return manager.create_release("1.0.0", name="Initial Release")


@pytest.fixture
def candidate_release(manager, draft_release):
    manager.add_change(draft_release.release_id, "Add caching layer", subsystem="cache")
    return manager.finalize(draft_release.release_id)


@pytest.fixture
def deployed_dev_release(manager, candidate_release):
    """A release promoted to the DEVELOPMENT environment."""
    return manager.promote(candidate_release.release_id)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_version(self):
        """Module version string must match the documented release."""
        assert FIZZRELEASE_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority is assigned a deterministic slot in the pipeline."""
        assert MIDDLEWARE_PRIORITY == 213


# ---------------------------------------------------------------------------
# TestReleaseState
# ---------------------------------------------------------------------------

class TestReleaseState:
    def test_all_states_present(self):
        """The ReleaseState enum must expose all lifecycle phases."""
        expected = {"DRAFT", "CANDIDATE", "DEPLOYING", "DEPLOYED", "ROLLED_BACK"}
        actual = {s.name for s in ReleaseState}
        assert expected.issubset(actual)

    def test_all_environments_present(self):
        """The Environment enum must expose all target deployment tiers."""
        expected = {"DEVELOPMENT", "STAGING", "PRODUCTION"}
        actual = {e.name for e in Environment}
        assert expected.issubset(actual)


# ---------------------------------------------------------------------------
# TestReleaseCreation
# ---------------------------------------------------------------------------

class TestReleaseCreation:
    def test_create_returns_release(self, manager):
        """Creating a release must return a Release dataclass instance."""
        release = manager.create_release("2.0.0", name="Major Overhaul")
        assert isinstance(release, Release)

    def test_create_sets_draft_state(self, manager):
        """Newly created releases enter the DRAFT state."""
        release = manager.create_release("2.0.0")
        assert release.state == ReleaseState.DRAFT

    def test_create_stores_version_and_name(self, manager):
        """The version string and release name must be preserved verbatim."""
        release = manager.create_release("3.1.4", name="Pi Release")
        assert release.version == "3.1.4"
        assert release.name == "Pi Release"

    def test_create_defaults(self, manager):
        """A new release starts with no changes, no environment, and full health."""
        release = manager.create_release("1.0.0")
        assert release.changes == []
        assert release.current_environment is None
        assert release.health_score == 1.0


# ---------------------------------------------------------------------------
# TestAddChange
# ---------------------------------------------------------------------------

class TestAddChange:
    def test_add_change_returns_change(self, manager, draft_release):
        """Adding a change must return a ReleaseChange instance."""
        change = manager.add_change(
            draft_release.release_id, "Upgrade auth module", subsystem="auth"
        )
        assert isinstance(change, ReleaseChange)

    def test_add_change_stores_fields(self, manager, draft_release):
        """The change description and subsystem must be stored as provided."""
        change = manager.add_change(
            draft_release.release_id, "Fix cache invalidation", subsystem="cache"
        )
        assert change.description == "Fix cache invalidation"
        assert change.subsystem == "cache"

    def test_add_change_appears_in_release(self, manager, draft_release):
        """Changes added to a release must be retrievable from the release."""
        manager.add_change(draft_release.release_id, "First change")
        manager.add_change(draft_release.release_id, "Second change")
        release = manager.get_release(draft_release.release_id)
        assert len(release.changes) == 2

    def test_add_change_to_non_draft_raises(self, manager, candidate_release):
        """Changes may only be added to releases in DRAFT state."""
        with pytest.raises((FizzReleaseStateError, FizzReleaseError)):
            manager.add_change(
                candidate_release.release_id, "Late addition", subsystem="core"
            )


# ---------------------------------------------------------------------------
# TestFinalize
# ---------------------------------------------------------------------------

class TestFinalize:
    def test_finalize_transitions_to_candidate(self, manager, draft_release):
        """Finalizing a draft release promotes it to CANDIDATE state."""
        manager.add_change(draft_release.release_id, "Required change")
        release = manager.finalize(draft_release.release_id)
        assert release.state == ReleaseState.CANDIDATE

    def test_finalize_returns_release(self, manager, draft_release):
        """Finalize must return the updated Release object."""
        manager.add_change(draft_release.release_id, "Some change")
        release = manager.finalize(draft_release.release_id)
        assert isinstance(release, Release)


# ---------------------------------------------------------------------------
# TestPromote
# ---------------------------------------------------------------------------

class TestPromote:
    def test_promote_candidate_to_development(self, manager, candidate_release):
        """First promotion targets the DEVELOPMENT environment."""
        release = manager.promote(candidate_release.release_id)
        assert release.current_environment == Environment.DEVELOPMENT

    def test_promote_development_to_staging(self, manager, deployed_dev_release):
        """Promoting from development advances to STAGING."""
        release = manager.promote(deployed_dev_release.release_id)
        assert release.current_environment == Environment.STAGING

    def test_promote_staging_to_production(self, manager, deployed_dev_release):
        """Promoting from staging advances to PRODUCTION."""
        staging = manager.promote(deployed_dev_release.release_id)
        production = manager.promote(staging.release_id)
        assert production.current_environment == Environment.PRODUCTION

    def test_promote_sets_deployed_state(self, manager, candidate_release):
        """Promoted releases enter the DEPLOYED state."""
        release = manager.promote(candidate_release.release_id)
        assert release.state == ReleaseState.DEPLOYED

    def test_cannot_promote_past_production(self, manager, deployed_dev_release):
        """A release already in production cannot be promoted further."""
        staging = manager.promote(deployed_dev_release.release_id)
        production = manager.promote(staging.release_id)
        with pytest.raises((FizzReleaseStateError, FizzReleaseError)):
            manager.promote(production.release_id)


# ---------------------------------------------------------------------------
# TestRollback
# ---------------------------------------------------------------------------

class TestRollback:
    def test_rollback_sets_rolled_back_state(self, manager, deployed_dev_release):
        """Rolling back a deployed release transitions to ROLLED_BACK."""
        release = manager.rollback(deployed_dev_release.release_id)
        assert release.state == ReleaseState.ROLLED_BACK

    def test_rollback_returns_release(self, manager, deployed_dev_release):
        """Rollback must return the updated Release object."""
        release = manager.rollback(deployed_dev_release.release_id)
        assert isinstance(release, Release)


# ---------------------------------------------------------------------------
# TestHealthScore
# ---------------------------------------------------------------------------

class TestHealthScore:
    def test_update_health(self, manager, draft_release):
        """Health score can be set to an arbitrary value in [0.0, 1.0]."""
        release = manager.update_health(draft_release.release_id, 0.75)
        assert release.health_score == 0.75

    def test_health_clamps_above_one(self, manager, draft_release):
        """Health scores above 1.0 are clamped to 1.0."""
        release = manager.update_health(draft_release.release_id, 2.5)
        assert release.health_score == 1.0

    def test_health_clamps_below_zero(self, manager, draft_release):
        """Health scores below 0.0 are clamped to 0.0."""
        release = manager.update_health(draft_release.release_id, -0.5)
        assert release.health_score == 0.0


# ---------------------------------------------------------------------------
# TestQueryMethods
# ---------------------------------------------------------------------------

class TestQueryMethods:
    def test_get_release(self, manager, draft_release):
        """Retrieving a release by ID returns the correct record."""
        fetched = manager.get_release(draft_release.release_id)
        assert fetched.release_id == draft_release.release_id

    def test_get_release_not_found(self, manager):
        """Requesting a non-existent release raises a not-found error."""
        with pytest.raises((FizzReleaseNotFoundError, FizzReleaseError)):
            manager.get_release("nonexistent-release-id")

    def test_list_releases(self, manager):
        """list_releases returns all managed releases."""
        manager.create_release("1.0.0")
        manager.create_release("2.0.0")
        releases = manager.list_releases()
        assert len(releases) >= 2

    def test_get_releases_by_state(self, manager):
        """Filtering by state returns only releases in that state."""
        r1 = manager.create_release("1.0.0")
        r2 = manager.create_release("2.0.0")
        manager.add_change(r2.release_id, "change")
        manager.finalize(r2.release_id)
        drafts = manager.get_releases_by_state(ReleaseState.DRAFT)
        candidates = manager.get_releases_by_state(ReleaseState.CANDIDATE)
        assert all(r.state == ReleaseState.DRAFT for r in drafts)
        assert all(r.state == ReleaseState.CANDIDATE for r in candidates)
        assert len(drafts) >= 1
        assert len(candidates) >= 1

    def test_get_releases_in_environment(self, manager, deployed_dev_release):
        """Filtering by environment returns only releases deployed there."""
        dev_releases = manager.get_releases_in_environment(Environment.DEVELOPMENT)
        assert len(dev_releases) >= 1
        assert all(
            r.current_environment == Environment.DEVELOPMENT for r in dev_releases
        )


# ---------------------------------------------------------------------------
# TestDashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_render_returns_string(self):
        """The dashboard must produce a string representation."""
        mgr = ReleaseManager()
        dashboard = FizzReleaseDashboard(mgr)
        output = dashboard.render()
        assert isinstance(output, str)

    def test_render_includes_release_info(self):
        """Rendered output should reference managed releases."""
        mgr = ReleaseManager()
        mgr.create_release("1.0.0", name="Visible Release")
        dashboard = FizzReleaseDashboard(mgr)
        output = dashboard.render()
        assert "Visible Release" in output or "1.0.0" in output or "DRAFT" in output


# ---------------------------------------------------------------------------
# TestMiddleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_get_name(self):
        """Middleware name must match the subsystem identifier."""
        middleware = FizzReleaseMiddleware()
        assert middleware.get_name() == "fizzrelease"

    def test_get_priority(self):
        """Middleware priority must match the module constant."""
        middleware = FizzReleaseMiddleware()
        assert middleware.get_priority() == 213

    def test_process_calls_next(self):
        """Middleware must delegate to the next handler in the pipeline."""
        middleware = FizzReleaseMiddleware()
        called = {"flag": False}
        sentinel = object()

        def fake_next(ctx):
            called["flag"] = True
            return sentinel

        result = middleware.process({}, fake_next)
        assert called["flag"], "Middleware must invoke the next handler in the pipeline"
        assert result is sentinel


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    def test_returns_three_components(self):
        """The factory function must return a 3-tuple."""
        result = create_fizzrelease_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_component_types(self):
        """Factory must produce (ReleaseManager, Dashboard, Middleware)."""
        mgr, dashboard, middleware = create_fizzrelease_subsystem()
        assert isinstance(mgr, ReleaseManager)
        assert isinstance(dashboard, FizzReleaseDashboard)
        assert isinstance(middleware, FizzReleaseMiddleware)

    def test_subsystem_manager_is_functional(self):
        """The factory-produced manager must support full lifecycle operations."""
        mgr, _, _ = create_fizzrelease_subsystem()
        release = mgr.create_release("1.0.0", name="Smoke Test")
        assert release.state == ReleaseState.DRAFT
        fetched = mgr.get_release(release.release_id)
        assert fetched.release_id == release.release_id

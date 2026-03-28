"""
Tests for the FizzSemVer Semantic Versioning Constraint Solver.

Validates parsing, comparison, constraint satisfaction, conflict detection,
resolution strategy, dashboard rendering, middleware integration, and the
factory function — because dependency resolution is a critical concern
when determining whether integers are divisible by three.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzsemver import (
    FIZZSEMVER_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzSemVerDashboard,
    FizzSemVerMiddleware,
    SemanticVersion,
    VersionConstraint,
    VersionResolver,
    create_fizzsemver_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzsemver import (
    FizzSemVerError,
    FizzSemVerParseError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def resolver():
    return VersionResolver()


@pytest.fixture
def ctx():
    return ProcessingContext(number=42, session_id="semver-test-session")


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Verify module metadata exports."""

    def test_version_string(self):
        assert FIZZSEMVER_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 217


# ---------------------------------------------------------------------------
# SemanticVersion dataclass
# ---------------------------------------------------------------------------


class TestSemanticVersion:
    """SemanticVersion representation and ordering tests."""

    def test_str_without_prerelease(self):
        v = SemanticVersion(major=2, minor=7, patch=1)
        assert str(v) == "2.7.1"

    def test_str_with_prerelease(self):
        v = SemanticVersion(major=1, minor=0, patch=0, prerelease="alpha.3")
        assert str(v) == "1.0.0-alpha.3"

    def test_str_with_empty_prerelease(self):
        v = SemanticVersion(major=0, minor=9, patch=14, prerelease="")
        assert str(v) == "0.9.14"

    def test_equality(self):
        a = SemanticVersion(1, 2, 3)
        b = SemanticVersion(1, 2, 3)
        assert a == b

    def test_inequality_patch(self):
        a = SemanticVersion(1, 2, 3)
        b = SemanticVersion(1, 2, 4)
        assert a != b

    def test_less_than_major(self):
        assert SemanticVersion(1, 0, 0) < SemanticVersion(2, 0, 0)

    def test_less_than_minor(self):
        assert SemanticVersion(1, 2, 0) < SemanticVersion(1, 3, 0)

    def test_less_than_patch(self):
        assert SemanticVersion(1, 2, 3) < SemanticVersion(1, 2, 4)

    def test_greater_than(self):
        assert SemanticVersion(3, 0, 0) > SemanticVersion(2, 99, 99)

    def test_less_than_or_equal_when_equal(self):
        v = SemanticVersion(1, 1, 1)
        assert v <= SemanticVersion(1, 1, 1)

    def test_greater_than_or_equal_when_greater(self):
        assert SemanticVersion(2, 0, 0) >= SemanticVersion(1, 9, 9)

    def test_default_build_metadata(self):
        v = SemanticVersion(1, 0, 0)
        assert v.build == ""


# ---------------------------------------------------------------------------
# VersionResolver.parse
# ---------------------------------------------------------------------------


class TestVersionResolverParse:
    """Version string parsing tests."""

    def test_parse_simple(self, resolver):
        v = resolver.parse("1.2.3")
        assert v == SemanticVersion(1, 2, 3)

    def test_parse_with_prerelease(self, resolver):
        v = resolver.parse("4.5.6-beta")
        assert v == SemanticVersion(4, 5, 6, prerelease="beta")

    def test_parse_zeroes(self, resolver):
        v = resolver.parse("0.0.0")
        assert v == SemanticVersion(0, 0, 0)

    def test_parse_invalid_raises(self, resolver):
        with pytest.raises(FizzSemVerParseError):
            resolver.parse("not.a.version")

    def test_parse_incomplete_raises(self, resolver):
        with pytest.raises(FizzSemVerParseError):
            resolver.parse("1.2")


# ---------------------------------------------------------------------------
# VersionResolver.satisfies
# ---------------------------------------------------------------------------


class TestVersionResolverSatisfies:
    """Constraint satisfaction for all supported operators."""

    def test_exact_match_true(self, resolver):
        v = SemanticVersion(1, 0, 0)
        c = VersionConstraint(operator="=", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is True

    def test_exact_match_false(self, resolver):
        v = SemanticVersion(1, 0, 1)
        c = VersionConstraint(operator="=", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is False

    def test_gte_true(self, resolver):
        v = SemanticVersion(2, 0, 0)
        c = VersionConstraint(operator=">=", version=SemanticVersion(1, 5, 0))
        assert resolver.satisfies(v, c) is True

    def test_gte_boundary(self, resolver):
        v = SemanticVersion(1, 5, 0)
        c = VersionConstraint(operator=">=", version=SemanticVersion(1, 5, 0))
        assert resolver.satisfies(v, c) is True

    def test_lt_true(self, resolver):
        v = SemanticVersion(0, 9, 9)
        c = VersionConstraint(operator="<", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is True

    def test_lt_false_when_equal(self, resolver):
        v = SemanticVersion(1, 0, 0)
        c = VersionConstraint(operator="<", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is False

    def test_lte_boundary(self, resolver):
        v = SemanticVersion(1, 0, 0)
        c = VersionConstraint(operator="<=", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is True

    def test_gt_true(self, resolver):
        v = SemanticVersion(2, 0, 0)
        c = VersionConstraint(operator=">", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is True

    def test_caret_same_major_higher_minor(self, resolver):
        """Caret (^) allows minor and patch increases within the same major."""
        v = SemanticVersion(1, 5, 3)
        c = VersionConstraint(operator="^", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is True

    def test_caret_different_major_rejected(self, resolver):
        v = SemanticVersion(2, 0, 0)
        c = VersionConstraint(operator="^", version=SemanticVersion(1, 0, 0))
        assert resolver.satisfies(v, c) is False

    def test_caret_below_floor_rejected(self, resolver):
        v = SemanticVersion(1, 0, 0)
        c = VersionConstraint(operator="^", version=SemanticVersion(1, 2, 0))
        assert resolver.satisfies(v, c) is False

    def test_tilde_pessimistic_same_minor(self, resolver):
        """Pessimistic (~>) allows patch increases within the same minor."""
        v = SemanticVersion(1, 2, 9)
        c = VersionConstraint(operator="~>", version=SemanticVersion(1, 2, 0))
        assert resolver.satisfies(v, c) is True

    def test_tilde_pessimistic_different_minor_rejected(self, resolver):
        v = SemanticVersion(1, 3, 0)
        c = VersionConstraint(operator="~>", version=SemanticVersion(1, 2, 0))
        assert resolver.satisfies(v, c) is False


# ---------------------------------------------------------------------------
# VersionResolver.resolve
# ---------------------------------------------------------------------------


class TestVersionResolverResolve:
    """Resolution picks the highest version satisfying all constraints."""

    def test_resolve_returns_highest(self, resolver):
        constraints = [
            VersionConstraint(operator=">=", version=SemanticVersion(1, 0, 0)),
            VersionConstraint(operator="<", version=SemanticVersion(2, 0, 0)),
        ]
        available = [
            SemanticVersion(0, 9, 0),
            SemanticVersion(1, 0, 0),
            SemanticVersion(1, 5, 0),
            SemanticVersion(1, 9, 9),
            SemanticVersion(2, 0, 0),
        ]
        result = resolver.resolve(constraints, available)
        assert result == SemanticVersion(1, 9, 9)

    def test_resolve_no_match_returns_none(self, resolver):
        constraints = [
            VersionConstraint(operator=">", version=SemanticVersion(10, 0, 0)),
        ]
        available = [SemanticVersion(1, 0, 0), SemanticVersion(2, 0, 0)]
        assert resolver.resolve(constraints, available) is None

    def test_resolve_empty_available(self, resolver):
        constraints = [
            VersionConstraint(operator=">=", version=SemanticVersion(1, 0, 0)),
        ]
        assert resolver.resolve(constraints, []) is None

    def test_resolve_single_exact_constraint(self, resolver):
        constraints = [
            VersionConstraint(operator="=", version=SemanticVersion(1, 2, 3)),
        ]
        available = [
            SemanticVersion(1, 2, 2),
            SemanticVersion(1, 2, 3),
            SemanticVersion(1, 2, 4),
        ]
        assert resolver.resolve(constraints, available) == SemanticVersion(1, 2, 3)


# ---------------------------------------------------------------------------
# VersionResolver.check_conflicts
# ---------------------------------------------------------------------------


class TestVersionResolverCheckConflicts:
    """Conflict detection identifies unsatisfiable constraint sets."""

    def test_no_conflicts_for_compatible(self, resolver):
        constraints = [
            VersionConstraint(operator=">=", version=SemanticVersion(1, 0, 0)),
            VersionConstraint(operator="<", version=SemanticVersion(2, 0, 0)),
        ]
        assert resolver.check_conflicts(constraints) == []

    def test_conflict_detected_for_impossible(self, resolver):
        constraints = [
            VersionConstraint(operator=">", version=SemanticVersion(2, 0, 0)),
            VersionConstraint(operator="<", version=SemanticVersion(1, 0, 0)),
        ]
        conflicts = resolver.check_conflicts(constraints)
        assert len(conflicts) > 0
        assert isinstance(conflicts[0], str)


# ---------------------------------------------------------------------------
# FizzSemVerDashboard
# ---------------------------------------------------------------------------


class TestFizzSemVerDashboard:
    """Dashboard renders human-readable subsystem status."""

    def test_render_returns_string(self):
        dashboard = FizzSemVerDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_version(self):
        dashboard = FizzSemVerDashboard()
        output = dashboard.render()
        assert "1.0.0" in output or "FizzSemVer" in output


# ---------------------------------------------------------------------------
# FizzSemVerMiddleware
# ---------------------------------------------------------------------------


class TestFizzSemVerMiddleware:
    """Middleware integration with the processing pipeline."""

    def test_get_name(self):
        mw = FizzSemVerMiddleware()
        assert mw.get_name() == "fizzsemver"

    def test_get_priority(self):
        mw = FizzSemVerMiddleware()
        assert mw.get_priority() == 217

    def test_process_delegates_to_next(self, ctx):
        mw = FizzSemVerMiddleware()
        next_handler = MagicMock(side_effect=lambda c: c)
        result = mw.process(ctx, next_handler)
        next_handler.assert_called_once()
        assert result.number == 42


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestCreateFizzSemVerSubsystem:
    """Factory wiring returns the expected component triple."""

    def test_returns_tuple_of_three(self):
        result = create_fizzsemver_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_first_element_is_resolver(self):
        resolver, _, _ = create_fizzsemver_subsystem()
        assert isinstance(resolver, VersionResolver)

    def test_second_element_is_dashboard(self):
        _, dashboard, _ = create_fizzsemver_subsystem()
        assert isinstance(dashboard, FizzSemVerDashboard)

    def test_third_element_is_middleware(self):
        _, _, middleware = create_fizzsemver_subsystem()
        assert isinstance(middleware, FizzSemVerMiddleware)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptions:
    """FizzSemVer exception classes conform to the platform error contract."""

    def test_base_error_is_catchable(self):
        with pytest.raises(FizzSemVerError):
            raise FizzSemVerError("test failure")

    def test_parse_error_inherits_base(self):
        err = FizzSemVerParseError("abc")
        assert isinstance(err, FizzSemVerError)

    def test_parse_error_contains_version_string(self):
        err = FizzSemVerParseError("xyz")
        assert "xyz" in str(err)

"""
Tests for FizzDILifecycle -- Dependency Injection Lifecycle Manager.

Validates container registration, resolution across lifetime scopes,
cycle detection, dashboard rendering, and middleware integration.
"""

import pytest

from enterprise_fizzbuzz.infrastructure.fizzdilifecycle import (
    FIZZDILIFECYCLE_VERSION,
    MIDDLEWARE_PRIORITY,
    Lifetime,
    ResolutionState,
    FizzDILifecycleConfig,
    Registration,
    Container,
    CycleDetector,
    FizzDILifecycleDashboard,
    FizzDILifecycleMiddleware,
    create_fizzdilifecycle_subsystem,
)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_version_string(self):
        assert FIZZDILIFECYCLE_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 208


# ---------------------------------------------------------------------------
# TestContainer
# ---------------------------------------------------------------------------

class TestContainer:
    def test_register_returns_registration(self):
        container = Container()
        reg = container.register("svc", lambda c: object(), Lifetime.TRANSIENT)
        assert isinstance(reg, Registration)
        assert reg.name == "svc"
        assert reg.lifetime == Lifetime.TRANSIENT

    def test_singleton_returns_same_instance(self):
        container = Container()
        container.register("single", lambda c: object(), Lifetime.SINGLETON)
        first = container.resolve("single")
        second = container.resolve("single")
        assert first is second

    def test_transient_returns_new_instance_each_time(self):
        container = Container()
        container.register("trans", lambda c: object(), Lifetime.TRANSIENT)
        first = container.resolve("trans")
        second = container.resolve("trans")
        assert first is not second

    def test_scoped_shares_within_scope(self):
        container = Container()
        container.register("scoped_svc", lambda c: object(), Lifetime.SCOPED)
        scope = container.create_scope()
        first = scope.resolve("scoped_svc")
        second = scope.resolve("scoped_svc")
        assert first is second

    def test_scoped_differs_across_scopes(self):
        container = Container()
        container.register("scoped_svc", lambda c: object(), Lifetime.SCOPED)
        scope_a = container.create_scope()
        scope_b = container.create_scope()
        instance_a = scope_a.resolve("scoped_svc")
        instance_b = scope_b.resolve("scoped_svc")
        assert instance_a is not instance_b

    def test_has_returns_true_for_registered(self):
        container = Container()
        container.register("exists", lambda c: 42, Lifetime.TRANSIENT)
        assert container.has("exists") is True

    def test_has_returns_false_for_unregistered(self):
        container = Container()
        assert container.has("ghost") is False

    def test_list_registrations(self):
        container = Container()
        container.register("alpha", lambda c: 1, Lifetime.SINGLETON)
        container.register("beta", lambda c: 2, Lifetime.TRANSIENT)
        regs = container.list_registrations()
        names = [r.name for r in regs]
        assert "alpha" in names
        assert "beta" in names
        assert len(regs) >= 2

    def test_dispose_marks_disposed(self):
        container = Container()
        container.register("svc", lambda c: object(), Lifetime.SINGLETON)
        container.resolve("svc")
        container.dispose()
        regs = container.list_registrations()
        for reg in regs:
            assert reg.state == ResolutionState.DISPOSED

    def test_resolve_unregistered_raises(self):
        container = Container()
        with pytest.raises(Exception):
            container.resolve("nonexistent")

    def test_factory_receives_container(self):
        """The factory callable must receive the container so it can resolve dependencies."""
        container = Container()
        received = {}

        def factory(c):
            received["container"] = c
            return "result"

        container.register("svc", factory, Lifetime.TRANSIENT)
        container.resolve("svc")
        assert received["container"] is container


# ---------------------------------------------------------------------------
# TestCycleDetector
# ---------------------------------------------------------------------------

class TestCycleDetector:
    def test_no_cycles_in_clean_container(self):
        container = Container()
        container.register("a", lambda c: 1, Lifetime.TRANSIENT)
        container.register("b", lambda c: 2, Lifetime.TRANSIENT)
        detector = CycleDetector()
        cycles = detector.check(container)
        assert cycles == []

    def test_detects_cycle(self):
        """Register services whose factories resolve each other, creating a cycle."""
        container = Container()
        container.register("x", lambda c: c.resolve("y"), Lifetime.TRANSIENT)
        container.register("y", lambda c: c.resolve("x"), Lifetime.TRANSIENT)
        detector = CycleDetector()
        cycles = detector.check(container)
        assert len(cycles) > 0
        flat = [name for cycle in cycles for name in cycle]
        assert "x" in flat
        assert "y" in flat


# ---------------------------------------------------------------------------
# TestDashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_render_returns_string(self):
        dashboard = FizzDILifecycleDashboard()
        result = dashboard.render()
        assert isinstance(result, str)

    def test_render_contains_lifecycle_info(self):
        dashboard = FizzDILifecycleDashboard()
        result = dashboard.render()
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TestMiddleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_get_name(self):
        mw = FizzDILifecycleMiddleware()
        assert mw.get_name() == "fizzdilifecycle"

    def test_get_priority(self):
        mw = FizzDILifecycleMiddleware()
        assert mw.get_priority() == 208

    def test_process_calls_next(self):
        mw = FizzDILifecycleMiddleware()
        called = {"next": False}

        class FakeContext:
            pass

        def fake_next(ctx):
            called["next"] = True
            return ctx

        ctx = FakeContext()
        mw.process(ctx, fake_next)
        assert called["next"] is True


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    def test_returns_tuple_of_three(self):
        result = create_fizzdilifecycle_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        container, dashboard, middleware = create_fizzdilifecycle_subsystem()
        assert isinstance(container, Container)
        assert isinstance(dashboard, FizzDILifecycleDashboard)
        assert isinstance(middleware, FizzDILifecycleMiddleware)

    def test_container_is_functional(self):
        container, _, _ = create_fizzdilifecycle_subsystem()
        container.register("test_svc", lambda c: "hello", Lifetime.SINGLETON)
        assert container.resolve("test_svc") == "hello"

"""
Enterprise FizzBuzz Platform - Dependency Injection Container Tests

Comprehensive test suite for the IoC container, covering registration,
resolution, lifetime management, cycle detection, named bindings,
factory registration, Optional parameter handling, scoped lifetimes,
reset behavior, and fluent API chaining.

Because a 400-line dependency injection container for a FizzBuzz
application deserves at least 300 lines of tests to validate that
it correctly wires together components that could have been
instantiated with a single constructor call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    CircularDependencyError,
    DuplicateBindingError,
    MissingBindingError,
    ScopeError,
)
from enterprise_fizzbuzz.infrastructure.container import (
    Container,
    Lifetime,
    Registration,
    ScopeContext,
)


# ----------------------------------------------------------------
# Test fixtures and dummy classes
# ----------------------------------------------------------------


class IGreeter(ABC):
    """A greeting interface, because even test doubles deserve abstraction."""

    @abstractmethod
    def greet(self) -> str:
        ...


class SimpleGreeter(IGreeter):
    """A greeter that greets simply."""

    def greet(self) -> str:
        return "Hello, Enterprise FizzBuzz!"


class FancyGreeter(IGreeter):
    """A greeter with more gravitas."""

    def greet(self) -> str:
        return "Greetings, esteemed stakeholder of the FizzBuzz Platform!"


class ILogger(ABC):
    @abstractmethod
    def log(self, message: str) -> None:
        ...


class FakeLogger(ILogger):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def log(self, message: str) -> None:
        self.messages.append(message)


class ServiceWithDependency:
    """A service that depends on IGreeter via constructor injection."""

    def __init__(self, greeter: IGreeter) -> None:
        self.greeter = greeter


class ServiceWithOptional:
    """A service with an optional dependency."""

    def __init__(self, greeter: IGreeter, logger: Optional[ILogger] = None) -> None:
        self.greeter = greeter
        self.logger = logger


class ServiceWithMultipleDeps:
    """A service with multiple dependencies for recursive resolution."""

    def __init__(self, greeter: IGreeter, logger: ILogger) -> None:
        self.greeter = greeter
        self.logger = logger


class ServiceWithDefaults:
    """A service with default parameter values."""

    def __init__(self, greeter: IGreeter, name: str = "default") -> None:
        self.greeter = greeter
        self.name = name


class IndependentService:
    """A service with no dependencies at all."""

    def __init__(self) -> None:
        self.created = True


# Cycle detection test classes — defined at module scope so that
# typing.get_type_hints() can resolve the forward references.
# Locally-defined classes + from __future__ import annotations
# = unresolvable string annotations = sadness.


class ICycleA(ABC):
    """First half of a codependent relationship."""

    @abstractmethod
    def a(self) -> None:
        ...


class ICycleB(ABC):
    """Second half of a codependent relationship."""

    @abstractmethod
    def b(self) -> None:
        ...


class CycleA(ICycleA):
    def __init__(self, b: ICycleB) -> None:
        self.b = b

    def a(self) -> None:
        pass


class CycleB(ICycleB):
    def __init__(self, a: ICycleA) -> None:
        self.a = a

    def b(self) -> None:
        pass


# ----------------------------------------------------------------
# Tests
# ----------------------------------------------------------------


class TestBasicResolution:
    """Test basic registration and resolution."""

    def test_resolve_simple_class(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        result = container.resolve(IGreeter)
        assert isinstance(result, SimpleGreeter)
        assert result.greet() == "Hello, Enterprise FizzBuzz!"

    def test_resolve_returns_new_instance_for_transient(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.TRANSIENT)
        a = container.resolve(IGreeter)
        b = container.resolve(IGreeter)
        assert a is not b

    def test_resolve_independent_service(self) -> None:
        container = Container()
        container.register(IndependentService, IndependentService)
        result = container.resolve(IndependentService)
        assert isinstance(result, IndependentService)
        assert result.created is True


class TestLifetimeManagement:
    """Test singleton, eternal, transient, and scoped lifetimes."""

    def test_singleton_returns_same_instance(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.SINGLETON)
        a = container.resolve(IGreeter)
        b = container.resolve(IGreeter)
        assert a is b

    def test_eternal_returns_same_instance(self) -> None:
        """ETERNAL is comedically identical to SINGLETON."""
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.ETERNAL)
        a = container.resolve(IGreeter)
        b = container.resolve(IGreeter)
        assert a is b

    def test_singleton_and_eternal_behave_identically(self) -> None:
        """Prove that ETERNAL is just SINGLETON wearing a monocle."""
        singleton_container = Container()
        singleton_container.register(IGreeter, SimpleGreeter, Lifetime.SINGLETON)

        eternal_container = Container()
        eternal_container.register(IGreeter, SimpleGreeter, Lifetime.ETERNAL)

        s1 = singleton_container.resolve(IGreeter)
        s2 = singleton_container.resolve(IGreeter)
        e1 = eternal_container.resolve(IGreeter)
        e2 = eternal_container.resolve(IGreeter)

        assert s1 is s2
        assert e1 is e2

    def test_scoped_returns_same_instance_within_scope(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.SCOPED)

        with container.create_scope() as scope:
            a = scope.resolve(IGreeter)
            b = scope.resolve(IGreeter)
            assert a is b

    def test_scoped_returns_different_instances_across_scopes(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.SCOPED)

        with container.create_scope() as scope1:
            a = scope1.resolve(IGreeter)

        with container.create_scope() as scope2:
            b = scope2.resolve(IGreeter)

        assert a is not b

    def test_scoped_raises_without_scope(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.SCOPED)
        with pytest.raises(ScopeError):
            container.resolve(IGreeter)


class TestNamedBindings:
    """Test named binding registration and resolution."""

    def test_named_bindings_resolve_separately(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, name="simple")
        container.register(IGreeter, FancyGreeter, name="fancy")

        simple = container.resolve(IGreeter, name="simple")
        fancy = container.resolve(IGreeter, name="fancy")

        assert isinstance(simple, SimpleGreeter)
        assert isinstance(fancy, FancyGreeter)

    def test_named_and_unnamed_coexist(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        container.register(IGreeter, FancyGreeter, name="fancy")

        default = container.resolve(IGreeter)
        fancy = container.resolve(IGreeter, name="fancy")

        assert isinstance(default, SimpleGreeter)
        assert isinstance(fancy, FancyGreeter)


class TestMissingBinding:
    """Test that missing bindings raise appropriate errors."""

    def test_missing_binding_raises_error(self) -> None:
        container = Container()
        with pytest.raises(MissingBindingError):
            container.resolve(IGreeter)

    def test_missing_named_binding_raises_error(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, name="exists")
        with pytest.raises(MissingBindingError):
            container.resolve(IGreeter, name="does_not_exist")


class TestDuplicateBinding:
    """Test that duplicate bindings raise errors."""

    def test_duplicate_binding_raises_error(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        with pytest.raises(DuplicateBindingError):
            container.register(IGreeter, FancyGreeter)

    def test_duplicate_named_binding_raises_error(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, name="x")
        with pytest.raises(DuplicateBindingError):
            container.register(IGreeter, FancyGreeter, name="x")


class TestRecursiveResolution:
    """Test that the container resolves dependencies recursively."""

    def test_resolve_with_dependency(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.SINGLETON)
        container.register(ServiceWithDependency, ServiceWithDependency)

        result = container.resolve(ServiceWithDependency)
        assert isinstance(result, ServiceWithDependency)
        assert isinstance(result.greeter, SimpleGreeter)

    def test_resolve_with_multiple_dependencies(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.SINGLETON)
        container.register(ILogger, FakeLogger, Lifetime.SINGLETON)
        container.register(ServiceWithMultipleDeps, ServiceWithMultipleDeps)

        result = container.resolve(ServiceWithMultipleDeps)
        assert isinstance(result.greeter, SimpleGreeter)
        assert isinstance(result.logger, FakeLogger)


class TestOptionalParameters:
    """Test Optional[X] parameter handling."""

    def test_optional_resolved_when_registered(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        container.register(ILogger, FakeLogger)
        container.register(ServiceWithOptional, ServiceWithOptional)

        result = container.resolve(ServiceWithOptional)
        assert result.logger is not None
        assert isinstance(result.logger, FakeLogger)

    def test_optional_is_none_when_not_registered(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        container.register(ServiceWithOptional, ServiceWithOptional)

        result = container.resolve(ServiceWithOptional)
        assert result.greeter is not None
        assert result.logger is None


class TestFactoryRegistration:
    """Test factory-based registration."""

    def test_factory_registration(self) -> None:
        container = Container()
        container.register(
            IGreeter,
            factory=lambda: SimpleGreeter(),
            lifetime=Lifetime.SINGLETON,
        )

        result = container.resolve(IGreeter)
        assert isinstance(result, SimpleGreeter)

    def test_factory_singleton_returns_same_instance(self) -> None:
        container = Container()
        container.register(
            IGreeter,
            factory=lambda: SimpleGreeter(),
            lifetime=Lifetime.SINGLETON,
        )

        a = container.resolve(IGreeter)
        b = container.resolve(IGreeter)
        assert a is b

    def test_factory_transient_returns_new_instances(self) -> None:
        container = Container()
        container.register(
            IGreeter,
            factory=lambda: SimpleGreeter(),
            lifetime=Lifetime.TRANSIENT,
        )

        a = container.resolve(IGreeter)
        b = container.resolve(IGreeter)
        assert a is not b


class TestCircularDependencyDetection:
    """Test Kahn's algorithm cycle detection."""

    def test_circular_dependency_detected(self) -> None:
        """Two services that depend on each other should be caught."""
        container = Container()
        container.register(ICycleA, CycleA)
        with pytest.raises(CircularDependencyError):
            container.register(ICycleB, CycleB)


class TestReset:
    """Test container reset functionality."""

    def test_reset_clears_all_bindings(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        assert container.get_registration_count() == 1

        container.reset()
        assert container.get_registration_count() == 0

    def test_reset_clears_singleton_cache(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, Lifetime.SINGLETON)
        a = container.resolve(IGreeter)

        container.reset()
        container.register(IGreeter, SimpleGreeter, Lifetime.SINGLETON)
        b = container.resolve(IGreeter)

        assert a is not b


class TestFluentAPI:
    """Test fluent method chaining."""

    def test_register_returns_self(self) -> None:
        container = Container()
        result = container.register(IGreeter, SimpleGreeter)
        assert result is container

    def test_fluent_chaining(self) -> None:
        container = Container()
        result = (
            container
            .register(IGreeter, SimpleGreeter, Lifetime.SINGLETON)
            .register(ILogger, FakeLogger, Lifetime.TRANSIENT)
        )
        assert result is container
        assert container.get_registration_count() == 2


class TestIsRegistered:
    """Test registration introspection."""

    def test_is_registered_returns_true(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        assert container.is_registered(IGreeter) is True

    def test_is_registered_returns_false(self) -> None:
        container = Container()
        assert container.is_registered(IGreeter) is False

    def test_is_registered_with_name(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter, name="simple")
        assert container.is_registered(IGreeter, name="simple") is True
        assert container.is_registered(IGreeter) is False


class TestDefaultParameters:
    """Test that non-injectable parameters with defaults are handled."""

    def test_default_params_preserved(self) -> None:
        container = Container()
        container.register(IGreeter, SimpleGreeter)
        container.register(ServiceWithDefaults, ServiceWithDefaults)

        result = container.resolve(ServiceWithDefaults)
        assert result.name == "default"
        assert isinstance(result.greeter, SimpleGreeter)


class TestRegistrationValidation:
    """Test that invalid registrations are caught."""

    def test_no_impl_or_factory_raises(self) -> None:
        container = Container()
        with pytest.raises(ValueError):
            container.register(IGreeter)


class TestLifetimeEnum:
    """Test that all lifetime values exist and are distinct."""

    def test_all_lifetimes_exist(self) -> None:
        assert Lifetime.TRANSIENT.value == "transient"
        assert Lifetime.SCOPED.value == "scoped"
        assert Lifetime.SINGLETON.value == "singleton"
        assert Lifetime.ETERNAL.value == "eternal"

    def test_lifetime_count(self) -> None:
        assert len(Lifetime) == 4

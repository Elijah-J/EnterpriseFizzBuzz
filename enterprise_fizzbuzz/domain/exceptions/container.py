"""
Enterprise FizzBuzz Platform - Dependency Injection Container Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DependencyInjectionError(FizzBuzzError):
    """Base exception for all Dependency Injection Container errors.

    When the IoC container — responsible for wiring together all
    FizzBuzz platform components — itself encounters an error, a
    critical infrastructure failure has occurred at the dependency
    resolution layer. The container manages construction and lifecycle
    of all services, making failures at this level particularly
    consequential as they prevent normal component initialization.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DI00"),
            context=kwargs.pop("context", {}),
        )


class CircularDependencyError(DependencyInjectionError):
    """Raised when the dependency graph contains a cycle.

    Service A depends on Service B which depends on Service C which
    depends on Service A. Congratulations, you've created an infinite
    loop of constructor injection that would make even the most
    forgiving IoC container give up and go home. Kahn's algorithm
    has detected your circular shame and refuses to participate.
    """

    def __init__(self, cycle: list[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Circular dependency detected in the IoC container: {cycle_str}. "
            f"The dependency graph is not a DAG. Topological sort has failed. "
            f"Consider refactoring or embracing the chaos.",
            error_code="EFP-DI01",
            context={"cycle": cycle},
        )
        self.cycle = cycle


class MissingBindingError(DependencyInjectionError):
    """Raised when a requested service has no registered binding.

    You asked the container to resolve a service it has never heard of.
    The container searched its registry, checked behind the couch
    cushions, and even looked in the singleton cache. It's simply not
    there. Perhaps you forgot to register it, or perhaps you're asking
    the wrong container — a mistake that in enterprise Java would
    result in a 47-slide PowerPoint about proper bean configuration.
    """

    def __init__(self, interface_name: str) -> None:
        super().__init__(
            f"No binding registered for '{interface_name}'. "
            f"The container cannot conjure services from thin air, "
            f"despite what the Spring documentation implies.",
            error_code="EFP-DI02",
            context={"interface_name": interface_name},
        )
        self.interface_name = interface_name


class DuplicateBindingError(DependencyInjectionError):
    """Raised when attempting to register a binding that already exists.

    This interface already has a registered implementation. The container
    does not support overwriting bindings because that would introduce
    non-determinism into the dependency graph, and non-determinism in
    an IoC container is the architectural equivalent of a land mine in
    a library. Use named bindings if you need multiple implementations.
    """

    def __init__(self, interface_name: str) -> None:
        super().__init__(
            f"Binding for '{interface_name}' already exists. "
            f"The container refuses to overwrite it. Use a named binding "
            f"or call reset() if you enjoy living dangerously.",
            error_code="EFP-DI03",
            context={"interface_name": interface_name},
        )
        self.interface_name = interface_name


class ScopeError(DependencyInjectionError):
    """Raised when a scoped service is resolved outside of an active scope.

    Scoped services have a lifecycle tied to a specific scope context.
    Attempting to resolve one without an active scope is like trying
    to withdraw money from a bank account that doesn't exist — the
    operation is technically well-formed but semantically meaningless.
    The container needs a ScopeContext to manage the scoped instance's
    lifecycle, and you haven't provided one.
    """

    def __init__(self, interface_name: str) -> None:
        super().__init__(
            f"Cannot resolve scoped service '{interface_name}' outside "
            f"of an active scope. Use container.create_scope() to create "
            f"a scope context, or change the lifetime to SINGLETON if you "
            f"want the instance to live forever (or ETERNAL, if you want "
            f"it to live forever with more dignity).",
            error_code="EFP-DI04",
            context={"interface_name": interface_name},
        )
        self.interface_name = interface_name


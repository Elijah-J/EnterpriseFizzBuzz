"""
Enterprise FizzBuzz Platform - Dependency Injection Container

Implements a fully-featured IoC (Inversion of Control) container with
constructor introspection, lifetime management, topological cycle detection,
named bindings, and factory registration. Because manually calling
``EventBus()`` was far too simple, and what the Enterprise FizzBuzz Platform
truly needed was a 400-line abstraction layer that uses ``inspect.signature``,
``typing.get_type_hints``, and Kahn's algorithm to wire together objects
that could have been instantiated in three lines of code.

Features:
    - **Lifetime management**: Transient, Scoped, Singleton, and the
      comedically identical Eternal — because "Singleton" sounds too
      pedestrian for enterprise software.
    - **Auto-wiring**: Constructor parameters are introspected via
      ``typing.get_type_hints()`` and resolved recursively. If your
      constructor takes an ``IEventBus``, the container will find one
      for you, assuming you remembered to register it.
    - **Cycle detection**: Uses Kahn's topological sort to detect
      circular dependencies at registration time, before they can
      cause an infinite recursion that stack-overflows your production
      FizzBuzz evaluation pipeline.
    - **Named bindings**: Multiple implementations of the same interface
      can coexist peacefully via named registrations.
    - **Factory registration**: For objects with exotic construction
      requirements (looking at you, ``_SingletonMeta``).
    - **Fluent API**: ``container.register(...).register(...).register(...)``
      because method chaining makes everything feel more modern.

This container is ADDITIVE. It does not replace the existing
``FizzBuzzServiceBuilder`` wiring in ``__main__.py``. It merely
provides an additional layer of abstraction on top of the existing
layers of abstraction, like a parfait of unnecessary indirection.
"""

from __future__ import annotations

import inspect
import logging
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Generator,
    Optional,
    Union,
    get_type_hints,
)

from enterprise_fizzbuzz.domain.exceptions import (
    CircularDependencyError,
    DuplicateBindingError,
    MissingBindingError,
    ScopeError,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Lifetime Enum
# ----------------------------------------------------------------

class Lifetime(Enum):
    """Defines how long a resolved instance survives.

    In enterprise software, the lifespan of an object is a decision
    of profound philosophical weight. Will it be born and discarded
    for every request? Will it persist for the duration of a scope?
    Or will it live forever, a singleton in the sky, watching over
    all subsequent resolve() calls with quiet, immutable dignity?

    Members:
        TRANSIENT: A new instance is created every time. Stateless,
            ephemeral, and refreshingly commitment-free.
        SCOPED: One instance per scope context. Perfect for things
            that need to share state within a request but not across
            requests — assuming your FizzBuzz platform processes
            concurrent requests, which it absolutely does not.
        SINGLETON: One instance for the entire container lifetime.
            The classic. The original. The pattern that launched a
            thousand blog posts about why it's an anti-pattern.
        ETERNAL: Functionally identical to SINGLETON, but with a
            name that conveys the gravitas befitting an enterprise
            FizzBuzz component. Singletons are temporary. Eternal
            instances transcend the mortal plane of garbage collection.
    """

    TRANSIENT = "transient"
    SCOPED = "scoped"
    SINGLETON = "singleton"
    ETERNAL = "eternal"  # Same as Singleton, but more dignified


# ----------------------------------------------------------------
# Registration Dataclass
# ----------------------------------------------------------------

@dataclass
class Registration:
    """A binding between an interface and its implementation.

    This dataclass records everything the container needs to know to
    resolve a service: what interface it satisfies, what class implements
    it, how long the instance should live, and optionally a factory
    callable for objects that resist conventional construction.

    Attributes:
        interface: The abstract type or protocol being registered.
        implementation: The concrete class to instantiate.
        lifetime: How long the resolved instance should survive.
        name: Optional named binding for disambiguation.
        factory: Optional callable that produces the instance.
        _singleton_instance: Cached instance for SINGLETON/ETERNAL lifetimes.
    """

    interface: type
    implementation: Optional[type] = None
    lifetime: Lifetime = Lifetime.TRANSIENT
    name: Optional[str] = None
    factory: Optional[Callable[..., Any]] = None
    _singleton_instance: Optional[Any] = field(default=None, repr=False)

    def _binding_key(self) -> tuple[type, Optional[str]]:
        """Return the unique key for this registration."""
        return (self.interface, self.name)


# ----------------------------------------------------------------
# Scope Context
# ----------------------------------------------------------------

class ScopeContext:
    """A scoped lifetime context for the DI container.

    Scoped services live as long as the scope context is active. When
    the scope exits, all scoped instances are discarded — a ceremonial
    purge of short-lived objects that never quite achieved singleton
    status but were too important to be merely transient.

    Usage::

        with container.create_scope() as scope:
            service = scope.resolve(ISomeService)
            # Same instance within this scope
            same_service = scope.resolve(ISomeService)
        # scope exits, all scoped instances are gone
    """

    def __init__(self, container: Container) -> None:
        self._container = container
        self._scoped_instances: dict[tuple[type, Optional[str]], Any] = {}

    def resolve(self, interface: type, *, name: Optional[str] = None) -> Any:
        """Resolve a service within this scope context.

        Scoped services are cached per-scope. Transient services are
        created fresh. Singletons and Eternals delegate to the parent
        container's cache, because they transcend scope boundaries.
        """
        return self._container._resolve_internal(interface, name=name, scope=self)

    def _get_or_create_scoped(
        self, key: tuple[type, Optional[str]], factory: Callable[[], Any]
    ) -> Any:
        """Return cached scoped instance or create a new one."""
        if key not in self._scoped_instances:
            self._scoped_instances[key] = factory()
        return self._scoped_instances[key]

    def __enter__(self) -> ScopeContext:
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        logger.debug(
            "Scope context exiting. Discarding %d scoped instances. "
            "They served their purpose with distinction.",
            len(self._scoped_instances),
        )
        self._scoped_instances.clear()


# ----------------------------------------------------------------
# Container
# ----------------------------------------------------------------

class Container:
    """Enterprise-Grade Dependency Injection Container.

    A fully-featured IoC container that would make any Java enterprise
    architect feel right at home. Supports constructor auto-wiring,
    four distinct lifetime strategies, named bindings, factory
    registration, cycle detection via topological sort, and a fluent
    API that lets you chain registrations until your line exceeds
    PEP 8's column limit.

    The container resolves dependencies by introspecting constructor
    signatures using ``typing.get_type_hints()`` and recursively
    resolving each parameter. If a parameter is ``Optional[X]``, the
    container will attempt to resolve ``X`` and gracefully pass
    ``None`` if no binding exists — because even a DI container
    should know when to give up.

    Example::

        container = Container()
        container.register(IEventBus, EventBus, Lifetime.SINGLETON)
        container.register(IObserver, ConsoleObserver, Lifetime.TRANSIENT)

        event_bus = container.resolve(IEventBus)
        # Returns the same EventBus instance every time (singleton)

    The container is ADDITIVE — it does not replace the existing
    ``FizzBuzzServiceBuilder`` in ``__main__.py``. It provides a
    parallel universe of object construction that exists alongside
    the builder, like two parallel parking lots for the same mall.
    """

    def __init__(self) -> None:
        self._registrations: dict[tuple[type, Optional[str]], Registration] = {}
        self._resolution_stack: list[str] = []
        logger.debug(
            "IoC Container initialized. The era of manual constructor "
            "calls is over. Welcome to enterprise-grade wiring."
        )

    # ----------------------------------------------------------------
    # Registration
    # ----------------------------------------------------------------

    def register(
        self,
        interface: type,
        implementation: Optional[type] = None,
        lifetime: Lifetime = Lifetime.TRANSIENT,
        *,
        name: Optional[str] = None,
        factory: Optional[Callable[..., Any]] = None,
    ) -> Container:
        """Register a binding between an interface and its implementation.

        Supports both class-based registration (where the container
        introspects the constructor) and factory-based registration
        (where you provide a callable that handles construction).

        Args:
            interface: The abstract type or protocol to register.
            implementation: The concrete class. Optional if a factory is provided.
            lifetime: How long resolved instances should live.
            name: Optional name for disambiguating multiple registrations
                of the same interface.
            factory: Optional callable that returns the instance. Takes
                precedence over implementation if both are provided.

        Returns:
            self, for fluent chaining. Because ``container.register(...).register(...)``
            reads better than two separate statements, and readability
            counts (PEP 20, #7).

        Raises:
            DuplicateBindingError: If a binding for this interface+name
                already exists.
            ValueError: If neither implementation nor factory is provided.
        """
        key = (interface, name)

        if key in self._registrations:
            display_name = interface.__name__
            if name:
                display_name = f"{display_name}[{name}]"
            raise DuplicateBindingError(display_name)

        if implementation is None and factory is None:
            raise ValueError(
                f"Registration for '{interface.__name__}' requires either "
                f"an implementation class or a factory callable. The container "
                f"is powerful, but it cannot instantiate the abstract concept "
                f"of nothingness."
            )

        registration = Registration(
            interface=interface,
            implementation=implementation,
            lifetime=lifetime,
            name=name,
            factory=factory,
        )

        self._registrations[key] = registration

        # Validate no cycles after each registration
        self._validate_no_cycles()

        lifetime_label = lifetime.value
        impl_label = (
            implementation.__name__
            if implementation
            else f"factory<{factory.__name__ if factory and hasattr(factory, '__name__') else '?'}>"
        )
        logger.debug(
            "Registered %s -> %s [%s]%s",
            interface.__name__,
            impl_label,
            lifetime_label,
            f" (name={name})" if name else "",
        )

        return self

    # ----------------------------------------------------------------
    # Resolution
    # ----------------------------------------------------------------

    def resolve(self, interface: type, *, name: Optional[str] = None) -> Any:
        """Resolve a service by its interface type.

        This is the primary method consumers should call. It looks up
        the registration, introspects the constructor, recursively
        resolves dependencies, manages lifetime caching, and returns
        a fully-constructed instance — all so you don't have to type
        ``EventBus()`` yourself.

        Args:
            interface: The abstract type to resolve.
            name: Optional named binding to resolve.

        Returns:
            An instance of the registered implementation.

        Raises:
            MissingBindingError: If no binding exists for this interface.
            ScopeError: If a scoped service is resolved without a scope.
        """
        return self._resolve_internal(interface, name=name, scope=None)

    def _resolve_internal(
        self,
        interface: type,
        *,
        name: Optional[str] = None,
        scope: Optional[ScopeContext] = None,
    ) -> Any:
        """Internal resolution logic with scope support."""
        key = (interface, name)

        if key not in self._registrations:
            display_name = interface.__name__
            if name:
                display_name = f"{display_name}[{name}]"
            raise MissingBindingError(display_name)

        registration = self._registrations[key]

        # Lifetime dispatch
        if registration.lifetime in (Lifetime.SINGLETON, Lifetime.ETERNAL):
            if registration._singleton_instance is not None:
                return registration._singleton_instance
            instance = self._construct(registration, scope=scope)
            registration._singleton_instance = instance
            return instance

        if registration.lifetime == Lifetime.SCOPED:
            if scope is None:
                raise ScopeError(interface.__name__)
            return scope._get_or_create_scoped(
                key, lambda: self._construct(registration, scope=scope)
            )

        # TRANSIENT — always fresh
        return self._construct(registration, scope=scope)

    # ----------------------------------------------------------------
    # Construction
    # ----------------------------------------------------------------

    def _construct(
        self,
        registration: Registration,
        *,
        scope: Optional[ScopeContext] = None,
    ) -> Any:
        """Construct an instance for a registration.

        If a factory is provided, it is called directly. Otherwise,
        the constructor is introspected via ``typing.get_type_hints()``
        and each parameter is resolved recursively from the container.
        """
        if registration.factory is not None:
            return registration.factory()

        impl = registration.implementation
        if impl is None:
            raise ValueError(
                f"Registration for '{registration.interface.__name__}' has "
                f"no implementation and no factory. This should have been "
                f"caught at registration time. Something has gone deeply wrong."
            )

        # Track resolution stack for debugging
        impl_name = impl.__name__
        self._resolution_stack.append(impl_name)

        try:
            # Introspect constructor parameters
            try:
                hints = get_type_hints(impl.__init__)
            except Exception:
                # If get_type_hints fails (e.g., forward references that
                # can't be resolved), fall back to no-arg construction
                hints = {}

            sig = inspect.signature(impl.__init__)
            kwargs: dict[str, Any] = {}

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                param_type = hints.get(param_name)
                if param_type is None:
                    # No type annotation — skip (will use default or fail)
                    if param.default is not inspect.Parameter.empty:
                        continue
                    continue

                # Handle Optional[X] — extract X from Optional
                origin = getattr(param_type, "__origin__", None)
                args = getattr(param_type, "__args__", None)

                is_optional = False
                inner_type = param_type

                if origin is Union and args is not None:
                    # Optional[X] is Union[X, None]
                    non_none_args = [a for a in args if a is not type(None)]
                    if len(non_none_args) == 1 and type(None) in args:
                        is_optional = True
                        inner_type = non_none_args[0]

                # Try to resolve the type
                key = (inner_type, None)
                if key in self._registrations:
                    kwargs[param_name] = self._resolve_internal(
                        inner_type, scope=scope
                    )
                elif is_optional:
                    kwargs[param_name] = None
                elif param.default is not inspect.Parameter.empty:
                    # Has a default — let it use it
                    continue
                else:
                    # Not registered, not optional, no default — skip
                    # (the constructor will raise its own error if needed)
                    continue

            return impl(**kwargs)
        finally:
            self._resolution_stack.pop()

    # ----------------------------------------------------------------
    # Cycle Detection (Kahn's Algorithm)
    # ----------------------------------------------------------------

    def _validate_no_cycles(self) -> None:
        """Validate that the dependency graph contains no cycles.

        Uses Kahn's algorithm for topological sorting. If the sort
        cannot process all nodes, a cycle exists and we raise a
        ``CircularDependencyError`` with the offending cycle path.

        This runs at registration time because catching cycles early
        is infinitely preferable to catching them at resolve time
        via a ``RecursionError`` that crashes the production FizzBuzz
        evaluation pipeline at 3 AM.
        """
        # Build adjacency list from registrations
        # Each registration's implementation depends on the types in its constructor
        graph: dict[type, set[type]] = defaultdict(set)
        all_types: set[type] = set()

        for key, reg in self._registrations.items():
            interface = reg.interface
            all_types.add(interface)

            impl = reg.implementation
            if impl is None:
                # Factory registration — no introspectable dependencies
                continue

            try:
                hints = get_type_hints(impl.__init__)
            except Exception:
                continue

            sig = inspect.signature(impl.__init__)
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                param_type = hints.get(param_name)
                if param_type is None:
                    continue

                # Unwrap Optional
                origin = getattr(param_type, "__origin__", None)
                args = getattr(param_type, "__args__", None)
                if origin is Union and args is not None:
                    non_none = [a for a in args if a is not type(None)]
                    if len(non_none) == 1:
                        param_type = non_none[0]

                dep_key = (param_type, None)
                if dep_key in self._registrations:
                    graph[interface].add(param_type)
                    all_types.add(param_type)

        # Kahn's algorithm
        in_degree: dict[type, int] = {t: 0 for t in all_types}
        for node, deps in graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] = in_degree.get(dep, 0) + 1

        queue: deque[type] = deque(
            node for node, degree in in_degree.items() if degree == 0
        )
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for dep in graph.get(node, set()):
                if dep in in_degree:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)

        if visited_count < len(all_types):
            # Cycle detected — find the cycle for the error message
            cycle_members = [
                t.__name__ for t, deg in in_degree.items() if deg > 0
            ]
            # Construct a cycle path for display
            cycle_path = cycle_members + [cycle_members[0]] if cycle_members else []
            raise CircularDependencyError(cycle_path)

    # ----------------------------------------------------------------
    # Scope Management
    # ----------------------------------------------------------------

    @contextmanager
    def create_scope(self) -> Generator[ScopeContext, None, None]:
        """Create a new scope context for resolving scoped services.

        Usage::

            with container.create_scope() as scope:
                service = scope.resolve(IScopedService)
        """
        scope = ScopeContext(self)
        logger.debug(
            "New scope context created. Scoped services will be cached "
            "within this context and discarded upon exit."
        )
        try:
            yield scope
        finally:
            scope.__exit__(None, None, None)

    # ----------------------------------------------------------------
    # Reset
    # ----------------------------------------------------------------

    def reset(self) -> None:
        """Clear all registrations and cached instances.

        The nuclear option. Every binding, every cached singleton,
        every eternal instance — all gone, reduced to atoms. Use
        this for testing or when you want to experience the primal
        thrill of starting from a completely blank container.
        """
        self._registrations.clear()
        self._resolution_stack.clear()
        logger.debug(
            "Container reset. All bindings and cached instances have been "
            "purged. The container is a blank canvas once more."
        )

    # ----------------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------------

    def is_registered(self, interface: type, *, name: Optional[str] = None) -> bool:
        """Check whether a binding exists for the given interface."""
        return (interface, name) in self._registrations

    def get_registration_count(self) -> int:
        """Return the total number of registered bindings."""
        return len(self._registrations)

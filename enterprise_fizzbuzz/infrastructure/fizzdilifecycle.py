"""Enterprise FizzBuzz Platform - FizzDILifecycle: Dependency Injection Lifecycle Manager"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzdilifecycle import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzdilifecycle")
EVENT_DI = EventType.register("FIZZDILIFECYCLE_RESOLVED")
FIZZDILIFECYCLE_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 208

class Lifetime(Enum):
    SINGLETON = "singleton"; TRANSIENT = "transient"; SCOPED = "scoped"
class ResolutionState(Enum):
    UNRESOLVED = "unresolved"; RESOLVING = "resolving"; RESOLVED = "resolved"; DISPOSED = "disposed"

@dataclass
class FizzDILifecycleConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Registration:
    name: str = ""; factory: Optional[Callable] = None
    lifetime: Lifetime = Lifetime.TRANSIENT; state: ResolutionState = ResolutionState.UNRESOLVED

class Container:
    def __init__(self, parent: Optional["Container"] = None) -> None:
        self._registrations: OrderedDict[str, Registration] = OrderedDict()
        self._singletons: Dict[str, Any] = {}
        self._scoped: Dict[str, Any] = {}
        self._parent = parent
        self._disposed = False
    def register(self, name: str, factory: Callable, lifetime: Lifetime = Lifetime.TRANSIENT) -> Registration:
        reg = Registration(name=name, factory=factory, lifetime=lifetime)
        self._registrations[name] = reg; return reg
    def resolve(self, name: str) -> Any:
        if self._disposed:
            raise FizzDILifecycleDisposedError(f"Container disposed, cannot resolve {name}")
        reg = self._registrations.get(name)
        if reg is None:
            if self._parent: return self._parent.resolve(name)
            raise FizzDILifecycleResolutionError(name)
        if reg.lifetime == Lifetime.SINGLETON:
            if name not in self._singletons:
                reg.state = ResolutionState.RESOLVING
                self._singletons[name] = reg.factory(self)
                reg.state = ResolutionState.RESOLVED
            return self._singletons[name]
        elif reg.lifetime == Lifetime.SCOPED:
            if name not in self._scoped:
                reg.state = ResolutionState.RESOLVING
                self._scoped[name] = reg.factory(self)
                reg.state = ResolutionState.RESOLVED
            return self._scoped[name]
        else:  # TRANSIENT
            reg.state = ResolutionState.RESOLVING
            instance = reg.factory(self)
            reg.state = ResolutionState.RESOLVED
            return instance
    def create_scope(self) -> "Container":
        child = Container(parent=self)
        # Copy registrations but not instances
        for name, reg in self._registrations.items():
            child._registrations[name] = Registration(name=reg.name, factory=reg.factory, lifetime=reg.lifetime)
        return child
    def dispose(self) -> None:
        self._disposed = True
        for reg in self._registrations.values():
            reg.state = ResolutionState.DISPOSED
        self._singletons.clear(); self._scoped.clear()
    def list_registrations(self) -> List[Registration]:
        return list(self._registrations.values())
    def has(self, name: str) -> bool:
        if name in self._registrations: return True
        if self._parent: return self._parent.has(name)
        return False

class CycleDetector:
    def check(self, container: Container) -> List[List[str]]:
        """Detect dependency cycles by trial-resolving each registration with a
        tracing container that monitors resolution chains."""
        cycles: List[List[str]] = []
        seen_cycles: set = set()
        for name in container._registrations:
            chain: List[str] = []
            try:
                self._probe(name, container, chain, set())
            except _CycleFound as cf:
                cycle = cf.cycle
                key = tuple(sorted(cycle))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(cycle)
        return cycles

    def _probe(self, name: str, container: Container, chain: List[str], visiting: set) -> None:
        if name in visiting:
            start = chain.index(name) if name in chain else 0
            raise _CycleFound(chain[start:] + [name])
        reg = container._registrations.get(name)
        if reg is None:
            return
        visiting_copy = visiting | {name}
        chain_copy = chain + [name]
        probe_container = _ProbeContainer(container, self, chain_copy, visiting_copy)
        try:
            reg.factory(probe_container)
        except _CycleFound:
            raise
        except Exception:
            pass  # Factory may fail for non-cycle reasons during probing

class _CycleFound(Exception):
    def __init__(self, cycle: List[str]) -> None:
        self.cycle = cycle

class _ProbeContainer:
    """A lightweight container stand-in used during cycle probing that intercepts
    resolve calls to track the dependency chain."""
    def __init__(self, real: Container, detector: CycleDetector, chain: List[str], visiting: set) -> None:
        self._real = real; self._detector = detector; self._chain = chain; self._visiting = visiting
    def resolve(self, name: str) -> Any:
        self._detector._probe(name, self._real, self._chain, self._visiting)
        return None  # We don't need real values during probing

class FizzDILifecycleDashboard:
    def __init__(self, container: Optional[Container] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._container = container; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzDILifecycle Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZDILIFECYCLE_VERSION}"]
        if self._container:
            regs = self._container.list_registrations()
            lines.append(f"  Registrations: {len(regs)}")
            for r in regs[:10]:
                lines.append(f"  {r.name:<25} {r.lifetime.value:<10} {r.state.value}")
        return "\n".join(lines)

class FizzDILifecycleMiddleware(IMiddleware):
    def __init__(self, container: Optional[Container] = None, dashboard: Optional[FizzDILifecycleDashboard] = None) -> None:
        self._container = container; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzdilifecycle"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzdilifecycle_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[Container, FizzDILifecycleDashboard, FizzDILifecycleMiddleware]:
    container = Container()
    container.register("fizzbuzz_service", lambda c: {"name": "FizzBuzzService", "version": "1.0"}, Lifetime.SINGLETON)
    container.register("cache", lambda c: {"name": "Cache", "hits": 0}, Lifetime.SCOPED)
    container.register("request_context", lambda c: {"id": uuid.uuid4().hex[:8]}, Lifetime.TRANSIENT)
    dashboard = FizzDILifecycleDashboard(container, dashboard_width)
    middleware = FizzDILifecycleMiddleware(container, dashboard)
    logger.info("FizzDILifecycle initialized: %d registrations", len(container.list_registrations()))
    return container, dashboard, middleware

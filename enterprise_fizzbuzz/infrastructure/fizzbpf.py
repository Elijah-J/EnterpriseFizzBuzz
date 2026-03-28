"""Enterprise FizzBuzz Platform - FizzBPF: eBPF-Style Programmable Observability"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzbpf import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzbpf")
EVENT_BPF = EventType.register("FIZZBPF_PROBE_FIRED")
FIZZBPF_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 218


class ProbeType(Enum):
    KPROBE = "kprobe"
    KRETPROBE = "kretprobe"
    TRACEPOINT = "tracepoint"
    UPROBE = "uprobe"


class ProbeState(Enum):
    ATTACHED = "attached"
    DETACHED = "detached"
    ERROR = "error"


@dataclass
class ProbeProgram:
    """A user-defined probe program attached to an internal subsystem event."""
    probe_id: str = ""
    name: str = ""
    probe_type: ProbeType = ProbeType.KPROBE
    target: str = ""
    state: ProbeState = ProbeState.ATTACHED
    handler: Optional[Callable] = None
    hit_count: int = 0


@dataclass
class ProbeEvent:
    """A single event captured by a probe."""
    event_id: str = ""
    probe_id: str = ""
    timestamp: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FizzBPFConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class ProbeEngine:
    """Manages eBPF-style probes that attach to internal subsystem events,
    capturing observability data without modifying the instrumented code."""

    def __init__(self) -> None:
        self._probes: OrderedDict[str, ProbeProgram] = OrderedDict()
        self._events: List[ProbeEvent] = []

    def attach(self, name: str, probe_type: ProbeType, target: str,
               handler: Optional[Callable] = None) -> ProbeProgram:
        """Attach a probe program to a target event point."""
        probe_id = f"probe-{uuid.uuid4().hex[:8]}"
        probe = ProbeProgram(
            probe_id=probe_id,
            name=name,
            probe_type=probe_type,
            target=target,
            state=ProbeState.ATTACHED,
            handler=handler,
        )
        self._probes[probe_id] = probe
        logger.debug("Attached probe %s (%s) to %s", name, probe_type.value, target)
        return probe

    def detach(self, probe_id: str) -> ProbeProgram:
        """Detach a probe, stopping event capture."""
        probe = self.get_probe(probe_id)
        probe.state = ProbeState.DETACHED
        logger.debug("Detached probe %s", probe_id)
        return probe

    def get_probe(self, probe_id: str) -> ProbeProgram:
        probe = self._probes.get(probe_id)
        if probe is None:
            raise FizzBPFNotFoundError(probe_id)
        return probe

    def list_probes(self) -> List[ProbeProgram]:
        return list(self._probes.values())

    def fire(self, probe_id: str, data: Optional[Dict[str, Any]] = None) -> ProbeEvent:
        """Simulate firing a probe event. Increments hit count, records event,
        and invokes the handler if one is attached."""
        probe = self.get_probe(probe_id)
        if probe.state != ProbeState.ATTACHED:
            raise FizzBPFError(f"Probe {probe_id} is {probe.state.value}, cannot fire")
        probe.hit_count += 1
        event = ProbeEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            probe_id=probe_id,
            timestamp=datetime.utcnow().isoformat(),
            data=data or {},
        )
        self._events.append(event)
        if probe.handler:
            try:
                probe.handler(event)
            except Exception as e:
                logger.warning("Probe handler error for %s: %s", probe_id, e)
        return event

    def get_events(self, probe_id: Optional[str] = None) -> List[ProbeEvent]:
        """Get events, optionally filtered by probe ID."""
        if probe_id:
            return [e for e in self._events if e.probe_id == probe_id]
        return list(self._events)

    def get_stats(self) -> dict:
        """Get aggregate probe statistics."""
        active = sum(1 for p in self._probes.values() if p.state == ProbeState.ATTACHED)
        return {
            "total_probes": len(self._probes),
            "active_probes": active,
            "total_events": len(self._events),
        }


class FizzBPFDashboard:
    def __init__(self, engine: Optional[ProbeEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzBPF Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZBPF_VERSION}"]
        if self._engine:
            stats = self._engine.get_stats()
            lines.append(f"  Probes: {stats['total_probes']} ({stats['active_probes']} active)")
            lines.append(f"  Events: {stats['total_events']}")
            lines.append("-" * self._width)
            for p in self._engine.list_probes()[:10]:
                lines.append(f"  {p.name:<20} [{p.probe_type.value}] {p.target} hits={p.hit_count}")
        return "\n".join(lines)


class FizzBPFMiddleware(IMiddleware):
    def __init__(self, engine: Optional[ProbeEngine] = None,
                 dashboard: Optional[FizzBPFDashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzbpf"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzbpf_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[ProbeEngine, FizzBPFDashboard, FizzBPFMiddleware]:
    """Factory function that creates and wires the FizzBPF subsystem."""
    engine = ProbeEngine()
    engine.attach("classify_entry", ProbeType.KPROBE, "fizzbuzz.classify")
    engine.attach("classify_return", ProbeType.KRETPROBE, "fizzbuzz.classify")
    engine.attach("cache_hit", ProbeType.TRACEPOINT, "cache:hit")

    dashboard = FizzBPFDashboard(engine, dashboard_width)
    middleware = FizzBPFMiddleware(engine, dashboard)
    logger.info("FizzBPF initialized: %d probes", len(engine.list_probes()))
    return engine, dashboard, middleware

"""Enterprise FizzBuzz Platform - FizzMPSC: Lock-Free MPSC Channels"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzmpsc import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzmpsc")
EVENT_MPSC = EventType.register("FIZZMPSC_MESSAGE")
FIZZMPSC_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 231

@dataclass
class ChannelStats:
    sent: int = 0; received: int = 0; pending: int = 0; capacity: int = 0

@dataclass
class FizzMPSCConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

class Channel:
    """A multi-producer single-consumer message channel."""
    def __init__(self, name: str, capacity: int = 0) -> None:
        self.channel_id = f"ch-{uuid.uuid4().hex[:8]}"
        self.name = name
        self._capacity = capacity  # 0 = unbounded
        self._queue: deque = deque()
        self._closed = False
        self._sent = 0; self._received = 0

    def send(self, message: Any) -> bool:
        if self._closed: raise FizzMPSCClosedError(self.name)
        if self._capacity > 0 and len(self._queue) >= self._capacity:
            return False
        self._queue.append(message); self._sent += 1; return True

    def recv(self) -> Optional[Any]:
        if not self._queue:
            if self._closed: return None
            return None
        msg = self._queue.popleft(); self._received += 1; return msg

    def close(self) -> None:
        self._closed = True

    @property
    def is_closed(self) -> bool: return self._closed
    @property
    def pending(self) -> int: return len(self._queue)
    def stats(self) -> ChannelStats:
        return ChannelStats(sent=self._sent, received=self._received,
                            pending=len(self._queue), capacity=self._capacity)

class ChannelRegistry:
    def __init__(self) -> None:
        self._channels: OrderedDict[str, Channel] = OrderedDict()

    def create_channel(self, name: str, capacity: int = 0) -> Channel:
        ch = Channel(name, capacity)
        self._channels[ch.channel_id] = ch; return ch

    def get_channel(self, channel_id: str) -> Channel:
        ch = self._channels.get(channel_id)
        if ch is None: raise FizzMPSCNotFoundError(channel_id)
        return ch

    def list_channels(self) -> List[Channel]:
        return list(self._channels.values())

    def close_all(self) -> None:
        for ch in self._channels.values(): ch.close()

class FizzMPSCDashboard:
    def __init__(self, registry: Optional[ChannelRegistry] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._registry = registry; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzMPSC Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZMPSC_VERSION}"]
        if self._registry:
            channels = self._registry.list_channels()
            lines.append(f"  Channels: {len(channels)}")
            for ch in channels[:10]:
                s = ch.stats()
                lines.append(f"  {ch.name:<20} sent={s.sent} recv={s.received} pending={s.pending}")
        return "\n".join(lines)

class FizzMPSCMiddleware(IMiddleware):
    def __init__(self, registry: Optional[ChannelRegistry] = None, dashboard: Optional[FizzMPSCDashboard] = None) -> None:
        self._registry = registry; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzmpsc"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzmpsc_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[ChannelRegistry, FizzMPSCDashboard, FizzMPSCMiddleware]:
    registry = ChannelRegistry()
    registry.create_channel("fizzbuzz_results", capacity=1000)
    registry.create_channel("metrics_events", capacity=5000)
    dashboard = FizzMPSCDashboard(registry, dashboard_width)
    middleware = FizzMPSCMiddleware(registry, dashboard)
    logger.info("FizzMPSC initialized: %d channels", len(registry.list_channels()))
    return registry, dashboard, middleware

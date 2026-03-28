"""
Enterprise FizzBuzz Platform - FizzDebugger2: Enhanced Debugger

Time-travel debugging, conditional breakpoints, watch expressions, call stack.

Architecture reference: rr, UndoDB, VS Code Debugger, GDB.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzdebugger2 import (
    FizzDebugger2Error, FizzDebugger2BreakpointError,
    FizzDebugger2WatchError, FizzDebugger2TimelineError,
    FizzDebugger2SessionError, FizzDebugger2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzdebugger2")

EVENT_DBG_PAUSED = EventType.register("FIZZDEBUGGER2_PAUSED")
EVENT_DBG_REWIND = EventType.register("FIZZDEBUGGER2_REWIND")

FIZZDEBUGGER2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 178


class DebugState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"
    RECORDING = "recording"

class BreakpointType(Enum):
    LINE = "line"
    CONDITIONAL = "conditional"
    EXCEPTION = "exception"


@dataclass
class FizzDebugger2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
    max_timeline_frames: int = 10000

@dataclass
class Breakpoint:
    bp_id: str = ""
    bp_type: BreakpointType = BreakpointType.LINE
    location: str = ""
    condition: str = ""
    hit_count: int = 0
    enabled: bool = True

@dataclass
class WatchExpression:
    watch_id: str = ""
    expression: str = ""
    current_value: Any = None

@dataclass
class ExecutionFrame:
    frame_id: int = 0
    function_name: str = ""
    file_name: str = ""
    line_number: int = 0
    locals: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class DebugSession:
    """Debug session with time-travel, breakpoints, and watches."""

    def __init__(self, config: Optional[FizzDebugger2Config] = None) -> None:
        self._config = config or FizzDebugger2Config()
        self._state = DebugState.IDLE
        self._breakpoints: OrderedDict[str, Breakpoint] = OrderedDict()
        self._watches: OrderedDict[str, WatchExpression] = OrderedDict()
        self._call_stack: List[ExecutionFrame] = []
        self._timeline: List[ExecutionFrame] = []
        self._current_frame_idx = -1
        self._frame_counter = 0

    def start(self) -> None:
        self._state = DebugState.RUNNING

    def pause(self) -> None:
        self._state = DebugState.PAUSED

    def resume(self) -> None:
        self._state = DebugState.RUNNING

    def step_over(self) -> None:
        self._state = DebugState.STEPPING

    def step_into(self) -> None:
        self._state = DebugState.STEPPING

    def step_out(self) -> None:
        self._state = DebugState.STEPPING

    def add_breakpoint(self, location: str, bp_type: BreakpointType = BreakpointType.LINE,
                       condition: str = "") -> Breakpoint:
        bp = Breakpoint(
            bp_id=f"bp-{uuid.uuid4().hex[:8]}",
            bp_type=bp_type,
            location=location,
            condition=condition,
        )
        self._breakpoints[bp.bp_id] = bp
        return bp

    def remove_breakpoint(self, bp_id: str) -> bool:
        return self._breakpoints.pop(bp_id, None) is not None

    def list_breakpoints(self) -> List[Breakpoint]:
        return list(self._breakpoints.values())

    def add_watch(self, expression: str) -> WatchExpression:
        watch = WatchExpression(
            watch_id=f"watch-{uuid.uuid4().hex[:8]}",
            expression=expression,
        )
        self._watches[watch.watch_id] = watch
        return watch

    def evaluate_watch(self, watch_id: str) -> Any:
        watch = self._watches.get(watch_id)
        if watch is None:
            raise FizzDebugger2WatchError(f"Watch not found: {watch_id}")
        # Simulate evaluation
        expr = watch.expression
        try:
            # Safe eval for simple expressions
            if all(c in "0123456789+-*/%() " for c in expr):
                watch.current_value = eval(expr)
            elif expr.startswith("n "):
                # Variable reference
                watch.current_value = f"<{expr}>"
            else:
                watch.current_value = f"<{expr}>"
        except Exception:
            watch.current_value = "<error>"
        return watch.current_value

    def get_call_stack(self) -> List[ExecutionFrame]:
        return list(self._call_stack)

    def get_state(self) -> DebugState:
        return self._state

    def record_frame(self, frame: ExecutionFrame) -> None:
        """Record a frame in the execution timeline for time-travel."""
        if not frame.frame_id:
            self._frame_counter += 1
            frame.frame_id = self._frame_counter
        if not frame.timestamp:
            frame.timestamp = time.time()
        self._timeline.append(copy.deepcopy(frame))
        self._call_stack = [frame]
        self._current_frame_idx = len(self._timeline) - 1

        # Trim if exceeds max
        if len(self._timeline) > self._config.max_timeline_frames:
            self._timeline = self._timeline[-self._config.max_timeline_frames:]

    def get_timeline(self) -> List[ExecutionFrame]:
        """Return the full execution timeline."""
        return list(self._timeline)

    def rewind(self, frame_id: int) -> ExecutionFrame:
        """Rewind to a specific frame in the timeline."""
        for i, frame in enumerate(self._timeline):
            if frame.frame_id == frame_id:
                self._current_frame_idx = i
                self._call_stack = [frame]
                self._state = DebugState.PAUSED
                return frame
        raise FizzDebugger2TimelineError(f"Frame {frame_id} not found in timeline")


class FizzDebugger2Dashboard:
    def __init__(self, session: Optional[DebugSession] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._session = session
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width,
                 "FizzDebugger2 Dashboard".center(self._width),
                 "=" * self._width,
                 f"  Version: {FIZZDEBUGGER2_VERSION}"]
        if self._session:
            lines.append(f"  State:        {self._session.get_state().value}")
            lines.append(f"  Breakpoints:  {len(self._session.list_breakpoints())}")
            lines.append(f"  Timeline:     {len(self._session.get_timeline())} frames")
            for bp in self._session.list_breakpoints()[:5]:
                lines.append(f"  BP: {bp.bp_id} {bp.location} [{bp.bp_type.value}]")
        return "\n".join(lines)


class FizzDebugger2Middleware(IMiddleware):
    def __init__(self, session: Optional[DebugSession] = None,
                 dashboard: Optional[FizzDebugger2Dashboard] = None) -> None:
        self._session = session
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzdebugger2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzdebugger2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[DebugSession, FizzDebugger2Dashboard, FizzDebugger2Middleware]:
    config = FizzDebugger2Config(dashboard_width=dashboard_width)
    session = DebugSession(config)

    # Record initial frames
    session.record_frame(ExecutionFrame(
        function_name="main", file_name="__main__.py", line_number=1,
        locals={"args": ["--range", "1", "100"]},
    ))
    session.record_frame(ExecutionFrame(
        function_name="FizzBuzzService.run", file_name="service.py", line_number=42,
        locals={"start": 1, "end": 100},
    ))

    dashboard = FizzDebugger2Dashboard(session, dashboard_width)
    middleware = FizzDebugger2Middleware(session, dashboard)

    logger.info("FizzDebugger2 initialized: %d timeline frames", len(session.get_timeline()))
    return session, dashboard, middleware

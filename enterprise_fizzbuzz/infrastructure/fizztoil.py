"""Enterprise FizzBuzz Platform - FizzToil: SRE Toil Measurement and Automation"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizztoil import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizztoil")
EVENT_TOIL = EventType.register("FIZZTOIL_RECORDED")
FIZZTOIL_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 204

class ToilCategory(Enum):
    MANUAL = "manual"; REPETITIVE = "repetitive"; AUTOMATABLE = "automatable"; TACTICAL = "tactical"
class AutomationState(Enum):
    MANUAL = "manual"; PARTIALLY_AUTOMATED = "partially_automated"; FULLY_AUTOMATED = "fully_automated"

@dataclass
class FizzToilConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
@dataclass
class ToilTask:
    task_id: str = ""; name: str = ""; category: ToilCategory = ToilCategory.MANUAL
    time_spent_minutes: float = 0.0; frequency_per_week: float = 1.0
    automation_state: AutomationState = AutomationState.MANUAL; assignee: str = ""

class ToilTracker:
    def __init__(self, config: Optional[Any] = None) -> None:
        self._tasks: OrderedDict[str, ToilTask] = OrderedDict()
    def add_task(self, name: str, category: ToilCategory,
                 time_spent_minutes: float = 0.0, frequency_per_week: float = 1.0,
                 assignee: str = "", time: float = 0.0, frequency: float = 0.0) -> ToilTask:
        actual_time = time_spent_minutes or time
        actual_freq = frequency_per_week or frequency or 1.0
        task = ToilTask(task_id=f"toil-{uuid.uuid4().hex[:8]}", name=name, category=category,
                        time_spent_minutes=actual_time, frequency_per_week=actual_freq,
                        automation_state=AutomationState.MANUAL, assignee=assignee)
        self._tasks[task.task_id] = task; return task
    def get_task(self, task_id: str) -> ToilTask:
        t = self._tasks.get(task_id)
        if t is None: raise FizzToilNotFoundError(task_id)
        return t
    def list_tasks(self) -> List[ToilTask]:
        return list(self._tasks.values())
    def get_toil_budget(self) -> Dict[str, float]:
        total = sum(t.time_spent_minutes * t.frequency_per_week / 60 for t in self._tasks.values())
        manual = sum(t.time_spent_minutes * t.frequency_per_week / 60
                     for t in self._tasks.values() if t.category == ToilCategory.MANUAL)
        automatable = sum(t.time_spent_minutes * t.frequency_per_week / 60
                          for t in self._tasks.values() if t.category == ToilCategory.AUTOMATABLE)
        return {"total_hours": total, "manual_hours": manual, "automatable_hours": automatable}
    def automate(self, task_id: str) -> ToilTask:
        task = self.get_task(task_id)
        task.automation_state = AutomationState.FULLY_AUTOMATED; return task
    def get_automation_rate(self) -> float:
        if not self._tasks: return 0.0
        automated = sum(1 for t in self._tasks.values() if t.automation_state != AutomationState.MANUAL)
        return automated / len(self._tasks)

class FizzToilDashboard:
    def __init__(self, tracker: Optional[ToilTracker] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._tracker = tracker; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzToil Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZTOIL_VERSION}"]
        if self._tracker:
            tasks = self._tracker.list_tasks()
            budget = self._tracker.get_toil_budget()
            lines.append(f"  Tasks: {len(tasks)}")
            lines.append(f"  Total: {budget['total_hours']:.1f}h/week")
            lines.append(f"  Manual: {budget['manual_hours']:.1f}h/week")
            lines.append(f"  Automation: {self._tracker.get_automation_rate():.0%}")
            for t in tasks: lines.append(f"  {t.task_id} {t.name} [{t.category.value}] {t.time_spent_minutes}min x{t.frequency_per_week}/wk")
        return "\n".join(lines)

class FizzToilMiddleware(IMiddleware):
    def __init__(self, tracker: Optional[ToilTracker] = None, dashboard: Optional[FizzToilDashboard] = None) -> None:
        self._tracker = tracker; self._dashboard = dashboard
    def get_name(self) -> str: return "fizztoil"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizztoil_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[ToilTracker, FizzToilDashboard, FizzToilMiddleware]:
    tracker = ToilTracker()
    tracker.add_task("Certificate renewal", ToilCategory.AUTOMATABLE, 30, 1, "bob")
    tracker.add_task("Log rotation", ToilCategory.REPETITIVE, 15, 7, "bob")
    tracker.add_task("Capacity review", ToilCategory.MANUAL, 60, 0.25, "bob")
    dashboard = FizzToilDashboard(tracker, dashboard_width)
    middleware = FizzToilMiddleware(tracker, dashboard)
    logger.info("FizzToil initialized: %d tasks", len(tracker.list_tasks()))
    return tracker, dashboard, middleware

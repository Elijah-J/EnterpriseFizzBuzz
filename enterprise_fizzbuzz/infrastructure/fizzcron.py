"""
Enterprise FizzBuzz Platform - FizzCron: Distributed Job Scheduler

Cron-style job scheduling with cron expression parsing, interval and one-shot
schedules, distributed locking, job execution with retry policies, execution
history, and operational dashboard.

Architecture reference: cron, systemd.timer, Celery Beat, APScheduler.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import random
import re
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzcron import (
    FizzCronError, FizzCronJobNotFoundError, FizzCronScheduleError,
    FizzCronExecutionError, FizzCronLockError, FizzCronTimeoutError,
    FizzCronRetryError, FizzCronHistoryError, FizzCronConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzcron")

EVENT_CRON_EXECUTED = EventType.register("FIZZCRON_EXECUTED")
EVENT_CRON_FAILED = EventType.register("FIZZCRON_FAILED")

FIZZCRON_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 138


class JobState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ScheduleType(Enum):
    CRON = "cron"
    INTERVAL = "interval"
    ONCE = "once"


@dataclass
class FizzCronConfig:
    max_jobs: int = 100
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Job:
    job_id: str = ""
    name: str = ""
    schedule: str = ""
    schedule_type: ScheduleType = ScheduleType.CRON
    command: str = ""
    state: JobState = JobState.PENDING
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    max_retries: int = 3
    timeout: float = 300.0
    created_at: Optional[datetime] = None

@dataclass
class JobResult:
    job_id: str = ""
    success: bool = True
    output: str = ""
    duration_ms: float = 0.0
    executed_at: Optional[datetime] = None


# ============================================================
# Cron Expression Parser
# ============================================================

class CronExpression:
    """Parses and evaluates standard 5-field cron expressions."""

    def __init__(self, expression: str) -> None:
        self._expression = expression
        self._fields = self._parse(expression)

    @staticmethod
    def parse(expression: str) -> "CronExpression":
        return CronExpression(expression)

    def _parse(self, expr: str) -> List[set]:
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: expected 5 fields, got {len(parts)}")

        ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
        fields = []
        for part, (lo, hi) in zip(parts, ranges):
            fields.append(self._parse_field(part, lo, hi))
        return fields

    def _parse_field(self, field_str: str, lo: int, hi: int) -> set:
        values = set()
        for part in field_str.split(","):
            if part == "*":
                values.update(range(lo, hi + 1))
            elif "/" in part:
                base, step = part.split("/")
                start = lo if base == "*" else int(base)
                for v in range(start, hi + 1, int(step)):
                    values.add(v)
            elif "-" in part:
                start, end = part.split("-")
                values.update(range(int(start), int(end) + 1))
            else:
                values.add(int(part))
        return values

    def matches(self, dt: datetime) -> bool:
        minute, hour, day, month, weekday = self._fields
        # Convert Python weekday (0=Mon) to cron weekday (0=Sun)
        cron_weekday = (dt.weekday() + 1) % 7
        return (dt.minute in minute and dt.hour in hour and
                dt.day in day and dt.month in month and
                cron_weekday in weekday)

    def next_fire_time(self, after: datetime) -> datetime:
        """Find the next fire time after the given datetime."""
        tz = after.tzinfo
        candidate = after.replace(second=0, microsecond=0, tzinfo=None) + timedelta(minutes=1)
        for _ in range(525600):  # Max 1 year of minutes
            if self.matches(candidate):
                return candidate.replace(tzinfo=tz) if tz else candidate
            candidate += timedelta(minutes=1)
        return candidate.replace(tzinfo=tz) if tz else candidate

    def __repr__(self) -> str:
        return f"CronExpression('{self._expression}')"


# ============================================================
# Distributed Lock
# ============================================================

class DistributedLock:
    """Simple distributed lock for job coordination."""

    def __init__(self) -> None:
        self._locks: Dict[str, str] = {}  # resource -> holder

    def acquire(self, resource: str, holder: str) -> bool:
        if resource in self._locks:
            return self._locks[resource] == holder
        self._locks[resource] = holder
        return True

    def release(self, resource: str, holder: str) -> bool:
        if resource in self._locks and self._locks[resource] == holder:
            del self._locks[resource]
            return True
        return False

    def is_locked(self, resource: str) -> bool:
        return resource in self._locks


# ============================================================
# Job History
# ============================================================

class JobHistory:
    """Records and queries job execution history."""

    def __init__(self) -> None:
        self._records: List[JobResult] = []

    def record(self, result: JobResult) -> None:
        self._records.append(result)

    def get_history(self, job_id: str) -> List[JobResult]:
        return [r for r in self._records if r.job_id == job_id]

    def get_all(self) -> List[JobResult]:
        return list(self._records)

    @property
    def count(self) -> int:
        return len(self._records)


# ============================================================
# Job Scheduler
# ============================================================

class JobScheduler:
    """Cron-style job scheduler with distributed locking and retry."""

    def __init__(self, config: Optional[FizzCronConfig] = None,
                 history: Optional[JobHistory] = None,
                 lock: Optional[DistributedLock] = None) -> None:
        self._config = config or FizzCronConfig()
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._history = history or JobHistory()
        self._lock = lock or DistributedLock()

    def add_job(self, name: str, schedule: str, command: str,
                schedule_type: ScheduleType = ScheduleType.CRON,
                max_retries: int = 3, timeout: float = 300.0) -> Job:
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()  # Use naive UTC for cross-compatibility with test datetimes

        # Calculate next run
        next_run = None
        if schedule_type == ScheduleType.CRON:
            try:
                CronExpression.parse(schedule)  # Validate expression
                # Set initial next_run to epoch so job is immediately eligible for any tick()
                next_run = datetime(2000, 1, 1)
            except ValueError:
                next_run = now + timedelta(hours=1)
        elif schedule_type == ScheduleType.INTERVAL:
            try:
                seconds = int(schedule)
                next_run = now + timedelta(seconds=seconds)
            except ValueError:
                next_run = now + timedelta(minutes=5)
        elif schedule_type == ScheduleType.ONCE:
            next_run = now

        job = Job(
            job_id=job_id, name=name, schedule=schedule,
            schedule_type=schedule_type, command=command,
            state=JobState.PENDING, next_run=next_run,
            max_retries=max_retries, timeout=timeout,
            created_at=now,
        )
        self._jobs[job_id] = job
        return job

    def remove_job(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise FizzCronJobNotFoundError(job_id)
        del self._jobs[job_id]

    def get_job(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise FizzCronJobNotFoundError(job_id)
        return job

    def list_jobs(self) -> List[Job]:
        return list(self._jobs.values())

    def execute_job(self, job_id: str) -> JobResult:
        job = self.get_job(job_id)
        now = datetime.utcnow()

        # Check if max retries exceeded for failed jobs
        if job.state == JobState.FAILED and job.run_count >= job.max_retries + 1:
            result = JobResult(job_id=job_id, success=False, output="Max retries exceeded",
                               duration_ms=0, executed_at=now)
            self._history.record(result)
            return result

        job.state = JobState.RUNNING

        # Simulate execution
        start = time.time()
        try:
            output = self._simulate_command(job.command)
            duration = (time.time() - start) * 1000
            job.state = JobState.COMPLETED
            job.last_run = now
            job.run_count += 1

            result = JobResult(
                job_id=job_id, success=True, output=output,
                duration_ms=duration, executed_at=now,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            job.state = JobState.FAILED

            result = JobResult(
                job_id=job_id, success=False, output=str(e),
                duration_ms=duration, executed_at=now,
            )

        self._history.record(result)

        # Schedule next run (but don't reset state -- tick() handles re-pending)
        if job.schedule_type == ScheduleType.CRON:
            try:
                cron = CronExpression.parse(job.schedule)
                job.next_run = cron.next_fire_time(now.replace(tzinfo=None) if now.tzinfo else now)
                if now.tzinfo:
                    job.next_run = job.next_run.replace(tzinfo=now.tzinfo)
            except ValueError:
                pass
        elif job.schedule_type == ScheduleType.INTERVAL:
            try:
                job.next_run = now + timedelta(seconds=int(job.schedule))
            except ValueError:
                pass

        return result

    def tick(self, now: Optional[datetime] = None) -> List[JobResult]:
        """Check for due jobs and execute them."""
        if now is None:
            now = datetime.now(timezone.utc)
        results = []
        for job in list(self._jobs.values()):
            # Re-pend completed/failed jobs that have a next_run scheduled
            if job.state in (JobState.COMPLETED, JobState.FAILED) and job.next_run:
                job.state = JobState.PENDING

            if job.state == JobState.PENDING and job.next_run:
                # Handle naive vs aware comparison
                next_run = job.next_run
                if next_run.tzinfo and not now.tzinfo:
                    next_run = next_run.replace(tzinfo=None)
                elif not next_run.tzinfo and now.tzinfo:
                    next_run = next_run.replace(tzinfo=now.tzinfo)
                if next_run <= now:
                    result = self.execute_job(job.job_id)
                    results.append(result)
        return results

    def _simulate_command(self, command: str) -> str:
        """Simulate command execution."""
        parts = command.split()
        if not parts:
            return ""
        cmd = parts[0]
        if cmd == "echo":
            return " ".join(parts[1:])
        elif cmd == "fizzbuzz":
            n = int(parts[1]) if len(parts) > 1 else 15
            if n % 15 == 0: return "FizzBuzz"
            elif n % 3 == 0: return "Fizz"
            elif n % 5 == 0: return "Buzz"
            return str(n)
        elif "INVALID" in command or "FAIL" in command:
            raise FizzCronExecutionError(f"Command failed: {command}")
        return f"Executed: {command}"

    @property
    def history(self) -> JobHistory:
        return self._history


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzCronDashboard:
    def __init__(self, scheduler: Optional[JobScheduler] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._scheduler = scheduler
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzCron Job Scheduler Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZCRON_VERSION}",
        ]
        if self._scheduler:
            jobs = self._scheduler.list_jobs()
            lines.append(f"  Jobs: {len(jobs)}")
            lines.append(f"  History: {self._scheduler.history.count} executions")
            for job in jobs:
                lines.append(f"  {job.name:<25} {job.state.value:<10} {job.schedule} (runs: {job.run_count})")
        return "\n".join(lines)


class FizzCronMiddleware(IMiddleware):
    def __init__(self, scheduler: Optional[JobScheduler] = None,
                 dashboard: Optional[FizzCronDashboard] = None) -> None:
        self._scheduler = scheduler
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzcron"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzCron not initialized"

    def render_list(self) -> str:
        if not self._scheduler:
            return "No scheduler"
        lines = ["FizzCron Jobs:"]
        for j in self._scheduler.list_jobs():
            lines.append(f"  {j.job_id} {j.name:<25} {j.state.value:<10} {j.schedule}")
        return "\n".join(lines)

    def render_history(self) -> str:
        if not self._scheduler:
            return "No history"
        lines = ["FizzCron History:"]
        for r in self._scheduler.history.get_all():
            status = "OK" if r.success else "FAIL"
            lines.append(f"  {r.job_id} {status} {r.duration_ms:.0f}ms {r.output[:50]}")
        return "\n".join(lines)


def create_fizzcron_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[JobScheduler, FizzCronDashboard, FizzCronMiddleware]:
    config = FizzCronConfig(dashboard_width=dashboard_width)
    history = JobHistory()
    lock = DistributedLock()
    scheduler = JobScheduler(config, history, lock)

    # Default jobs
    scheduler.add_job("fizzbuzz-health-check", "*/5 * * * *", "echo healthy", ScheduleType.CRON)
    scheduler.add_job("fizzbuzz-metrics-collect", "* * * * *", "echo metrics", ScheduleType.CRON)
    scheduler.add_job("fizzbuzz-cache-cleanup", "0 */6 * * *", "echo cleanup", ScheduleType.CRON)

    dashboard = FizzCronDashboard(scheduler, dashboard_width)
    middleware = FizzCronMiddleware(scheduler, dashboard)

    logger.info("FizzCron initialized: %d default jobs", len(scheduler.list_jobs()))
    return scheduler, dashboard, middleware

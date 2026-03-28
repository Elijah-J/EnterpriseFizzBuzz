"""
Enterprise FizzBuzz Platform - FizzCron Distributed Job Scheduler Test Suite

Tests for the FizzCron subsystem, which provides enterprise-grade distributed
job scheduling for the FizzBuzz platform. Supports cron expressions, interval
scheduling, one-shot jobs, distributed locking, job history tracking, and a
real-time dashboard for operational visibility.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Callable

import pytest

from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.fizzcron import (
    FIZZCRON_VERSION,
    MIDDLEWARE_PRIORITY,
    CronExpression,
    DistributedLock,
    FizzCronConfig,
    FizzCronDashboard,
    FizzCronMiddleware,
    Job,
    JobHistory,
    JobResult,
    JobScheduler,
    JobState,
    ScheduleType,
    create_fizzcron_subsystem,
)


# ============================================================
# Fixture Helpers
# ============================================================


def _make_scheduler(**kwargs) -> JobScheduler:
    """Create a JobScheduler with sensible defaults."""
    return JobScheduler(**kwargs)


def _make_context(number: int = 42, session_id: str = "test-session") -> ProcessingContext:
    """Create a minimal ProcessingContext for middleware tests."""
    return ProcessingContext(number=number, session_id=session_id)


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Verify module-level constants are correctly exported."""

    def test_version_string(self):
        assert FIZZCRON_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 138


# ============================================================
# TestCronExpression
# ============================================================


class TestCronExpression:
    """Tests for the cron expression parser and matcher."""

    def test_every_minute(self):
        expr = CronExpression.parse("* * * * *")
        dt = datetime(2026, 3, 27, 14, 30, 0)
        assert expr.matches(dt) is True

    def test_specific_time(self):
        expr = CronExpression.parse("30 14 * * *")
        matching = datetime(2026, 3, 27, 14, 30, 0)
        non_matching = datetime(2026, 3, 27, 14, 31, 0)
        assert expr.matches(matching) is True
        assert expr.matches(non_matching) is False

    def test_wildcards_with_specific_day_and_month(self):
        expr = CronExpression.parse("0 0 25 12 *")
        christmas = datetime(2026, 12, 25, 0, 0, 0)
        not_christmas = datetime(2026, 12, 26, 0, 0, 0)
        assert expr.matches(christmas) is True
        assert expr.matches(not_christmas) is False

    def test_day_of_week(self):
        # 1 = Monday in standard cron (0=Sun, 1=Mon, ..., 6=Sat)
        expr = CronExpression.parse("0 9 * * 1")
        # 2026-03-30 is a Monday
        monday_9am = datetime(2026, 3, 30, 9, 0, 0)
        tuesday_9am = datetime(2026, 3, 31, 9, 0, 0)
        assert expr.matches(monday_9am) is True
        assert expr.matches(tuesday_9am) is False

    def test_invalid_expression_raises(self):
        with pytest.raises(ValueError):
            CronExpression.parse("not a cron expression")


# ============================================================
# TestJobScheduler
# ============================================================


class TestJobScheduler:
    """Tests for job lifecycle management and execution."""

    def test_add_job_returns_job(self):
        scheduler = _make_scheduler()
        job = scheduler.add_job(
            name="test_job",
            schedule="* * * * *",
            command="echo fizz",
            schedule_type=ScheduleType.CRON,
        )
        assert isinstance(job, Job)
        assert job.name == "test_job"
        assert job.state == JobState.PENDING
        assert job.run_count == 0

    def test_remove_job(self):
        scheduler = _make_scheduler()
        job = scheduler.add_job(
            name="removable",
            schedule="* * * * *",
            command="echo buzz",
            schedule_type=ScheduleType.CRON,
        )
        scheduler.remove_job(job.job_id)
        with pytest.raises(Exception):
            scheduler.get_job(job.job_id)

    def test_get_job(self):
        scheduler = _make_scheduler()
        job = scheduler.add_job(
            name="findable",
            schedule="*/5 * * * *",
            command="echo fizzbuzz",
            schedule_type=ScheduleType.CRON,
        )
        retrieved = scheduler.get_job(job.job_id)
        assert retrieved.job_id == job.job_id
        assert retrieved.name == "findable"

    def test_list_jobs(self):
        scheduler = _make_scheduler()
        scheduler.add_job("job_a", "* * * * *", "echo a", ScheduleType.CRON)
        scheduler.add_job("job_b", "* * * * *", "echo b", ScheduleType.CRON)
        jobs = scheduler.list_jobs()
        names = [j.name for j in jobs]
        assert "job_a" in names
        assert "job_b" in names
        assert len(jobs) >= 2

    def test_execute_job_returns_result(self):
        scheduler = _make_scheduler()
        job = scheduler.add_job(
            name="executable",
            schedule="* * * * *",
            command="echo hello",
            schedule_type=ScheduleType.CRON,
        )
        result = scheduler.execute_job(job.job_id)
        assert isinstance(result, JobResult)
        assert result.job_id == job.job_id
        assert isinstance(result.success, bool)
        assert isinstance(result.duration_ms, (int, float))
        assert result.duration_ms >= 0

    def test_tick_finds_due_jobs(self):
        scheduler = _make_scheduler()
        scheduler.add_job(
            name="every_minute",
            schedule="* * * * *",
            command="echo tick",
            schedule_type=ScheduleType.CRON,
        )
        now = datetime(2026, 3, 27, 12, 0, 0)
        ran = scheduler.tick(now)
        assert isinstance(ran, list)
        assert len(ran) >= 1

    def test_job_state_transitions_on_execute(self):
        scheduler = _make_scheduler()
        job = scheduler.add_job(
            name="stateful",
            schedule="* * * * *",
            command="echo state",
            schedule_type=ScheduleType.CRON,
        )
        assert job.state == JobState.PENDING
        result = scheduler.execute_job(job.job_id)
        updated = scheduler.get_job(job.job_id)
        assert updated.state in (JobState.COMPLETED, JobState.FAILED)
        assert updated.run_count >= 1

    def test_max_retries_respected(self):
        scheduler = _make_scheduler()
        job = scheduler.add_job(
            name="flaky",
            schedule="* * * * *",
            command="INVALID_COMMAND_THAT_SHOULD_FAIL",
            schedule_type=ScheduleType.CRON,
        )
        # Execute multiple times to trigger retries
        for _ in range(5):
            try:
                scheduler.execute_job(job.job_id)
            except Exception:
                pass
        updated = scheduler.get_job(job.job_id)
        assert updated.run_count <= (updated.max_retries + 1) or updated.state == JobState.FAILED


# ============================================================
# TestDistributedLock
# ============================================================


class TestDistributedLock:
    """Tests for the distributed locking mechanism."""

    def test_acquire_lock(self):
        lock = DistributedLock()
        assert lock.acquire("resource_a", "holder_1") is True

    def test_release_lock(self):
        lock = DistributedLock()
        lock.acquire("resource_b", "holder_1")
        assert lock.release("resource_b", "holder_1") is True
        # After release, another holder can acquire
        assert lock.acquire("resource_b", "holder_2") is True

    def test_double_acquire_fails(self):
        lock = DistributedLock()
        lock.acquire("resource_c", "holder_1")
        assert lock.acquire("resource_c", "holder_2") is False

    def test_is_locked(self):
        lock = DistributedLock()
        assert lock.is_locked("resource_d") is False
        lock.acquire("resource_d", "holder_1")
        assert lock.is_locked("resource_d") is True
        lock.release("resource_d", "holder_1")
        assert lock.is_locked("resource_d") is False


# ============================================================
# TestJobHistory
# ============================================================


class TestJobHistory:
    """Tests for job execution history tracking."""

    def test_record_and_retrieve(self):
        history = JobHistory()
        result = JobResult(
            job_id="job-001",
            success=True,
            output="done",
            duration_ms=42.0,
            executed_at=datetime(2026, 3, 27, 12, 0, 0),
        )
        history.record(result)
        records = history.get_history("job-001")
        assert len(records) == 1
        assert records[0].job_id == "job-001"
        assert records[0].success is True

    def test_filter_by_job_id(self):
        history = JobHistory()
        r1 = JobResult(
            job_id="job-A",
            success=True,
            output="a",
            duration_ms=10.0,
            executed_at=datetime(2026, 3, 27, 12, 0, 0),
        )
        r2 = JobResult(
            job_id="job-B",
            success=False,
            output="b",
            duration_ms=20.0,
            executed_at=datetime(2026, 3, 27, 12, 1, 0),
        )
        r3 = JobResult(
            job_id="job-A",
            success=True,
            output="a2",
            duration_ms=15.0,
            executed_at=datetime(2026, 3, 27, 12, 2, 0),
        )
        history.record(r1)
        history.record(r2)
        history.record(r3)
        a_records = history.get_history("job-A")
        all_records = history.get_all()
        assert len(a_records) == 2
        assert all(r.job_id == "job-A" for r in a_records)
        assert len(all_records) == 3

    def test_empty_history(self):
        history = JobHistory()
        assert history.get_history("nonexistent") == []
        assert history.get_all() == []


# ============================================================
# TestFizzCronDashboard
# ============================================================


class TestFizzCronDashboard:
    """Tests for the operational dashboard renderer."""

    def test_render_returns_string(self):
        scheduler = _make_scheduler()
        dashboard = FizzCronDashboard(scheduler=scheduler)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_job_info(self):
        scheduler = _make_scheduler()
        scheduler.add_job(
            name="dashboard_job",
            schedule="0 * * * *",
            command="echo dash",
            schedule_type=ScheduleType.CRON,
        )
        dashboard = FizzCronDashboard(scheduler=scheduler)
        output = dashboard.render()
        assert "dashboard_job" in output


# ============================================================
# TestFizzCronMiddleware
# ============================================================


class TestFizzCronMiddleware:
    """Tests for the middleware pipeline integration."""

    def test_middleware_name(self):
        mw = FizzCronMiddleware()
        assert mw.get_name() == "fizzcron"

    def test_middleware_priority(self):
        mw = FizzCronMiddleware()
        assert mw.get_priority() == 138

    def test_process_delegates_to_next(self):
        mw = FizzCronMiddleware()
        ctx = _make_context(number=15)
        delegate_called = False

        def mock_next(context: ProcessingContext) -> ProcessingContext:
            nonlocal delegate_called
            delegate_called = True
            return context

        result = mw.process(ctx, mock_next)
        assert delegate_called is True
        assert isinstance(result, ProcessingContext)
        assert result.number == 15


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Tests for the factory function that wires up the full subsystem."""

    def test_returns_tuple(self):
        result = create_fizzcron_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        scheduler, dashboard, middleware = result
        assert isinstance(scheduler, JobScheduler)
        assert isinstance(dashboard, FizzCronDashboard)
        assert isinstance(middleware, FizzCronMiddleware)

    def test_scheduler_operational(self):
        scheduler, _, _ = create_fizzcron_subsystem()
        job = scheduler.add_job(
            name="subsystem_test",
            schedule="* * * * *",
            command="echo subsystem",
            schedule_type=ScheduleType.CRON,
        )
        assert isinstance(job, Job)
        assert job.name == "subsystem_test"

    def test_can_execute_via_subsystem(self):
        scheduler, _, _ = create_fizzcron_subsystem()
        job = scheduler.add_job(
            name="exec_test",
            schedule="* * * * *",
            command="echo run",
            schedule_type=ScheduleType.CRON,
        )
        result = scheduler.execute_job(job.job_id)
        assert isinstance(result, JobResult)
        assert result.job_id == job.job_id


# ============================================================
# TestJobResult
# ============================================================


class TestJobResult:
    """Tests for the JobResult data class."""

    def test_success_result(self):
        result = JobResult(
            job_id="jr-001",
            success=True,
            output="completed successfully",
            duration_ms=100.5,
            executed_at=datetime(2026, 3, 27, 12, 0, 0),
        )
        assert result.success is True
        assert result.output == "completed successfully"
        assert result.duration_ms == 100.5
        assert result.job_id == "jr-001"
        assert result.executed_at == datetime(2026, 3, 27, 12, 0, 0)

    def test_failure_result(self):
        result = JobResult(
            job_id="jr-002",
            success=False,
            output="command not found",
            duration_ms=5.0,
            executed_at=datetime(2026, 3, 27, 12, 1, 0),
        )
        assert result.success is False
        assert result.output == "command not found"
        assert result.duration_ms == 5.0

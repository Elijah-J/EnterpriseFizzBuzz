"""
Enterprise FizzBuzz Platform - FizzSMTP2 SMTP Relay Test Suite

Comprehensive tests for the SMTP Relay with queuing, bounce processing,
and deliverability analytics. Validates message lifecycle from enqueue
through delivery tracking, bounce classification, and statistical
reporting across the entire relay pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzsmtp2 import (
    FIZZSMTP2_VERSION,
    MIDDLEWARE_PRIORITY,
    DeliveryStatus,
    BounceType,
    FizzSMTP2Config,
    EmailMessage,
    DeliveryRecord,
    RelayQueue,
    BounceProcessor,
    DeliverabilityAnalytics,
    FizzSMTP2Dashboard,
    FizzSMTP2Middleware,
    create_fizzsmtp2_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.domain.models import ProcessingContext, FizzBuzzResult


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def queue():
    """Create a fresh RelayQueue for each test."""
    return RelayQueue()


@pytest.fixture
def bounce_processor():
    """Create a fresh BounceProcessor for each test."""
    return BounceProcessor()


@pytest.fixture
def analytics():
    """Create a fresh DeliverabilityAnalytics for each test."""
    return DeliverabilityAnalytics()


@pytest.fixture
def sample_message():
    """Create a sample EmailMessage for testing."""
    return EmailMessage(
        message_id="msg-001",
        from_addr="fizz@enterprise.local",
        to_addr="buzz@enterprise.local",
        subject="FizzBuzz Report Q4",
        body="Attached: quarterly divisibility analysis.",
        headers={"X-Priority": "1", "X-FizzBuzz-Version": "enterprise"},
    )


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify exported constants match the documented protocol specification."""

    def test_version(self):
        assert FIZZSMTP2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 162


# ---------------------------------------------------------------------------
# TestEmailMessage
# ---------------------------------------------------------------------------

class TestEmailMessage:
    """Validate EmailMessage dataclass field integrity."""

    def test_dataclass_fields(self, sample_message):
        assert sample_message.from_addr == "fizz@enterprise.local"
        assert sample_message.to_addr == "buzz@enterprise.local"
        assert sample_message.subject == "FizzBuzz Report Q4"
        assert sample_message.body == "Attached: quarterly divisibility analysis."
        assert sample_message.headers == {
            "X-Priority": "1",
            "X-FizzBuzz-Version": "enterprise",
        }

    def test_message_id_present(self, sample_message):
        assert sample_message.message_id == "msg-001"
        assert isinstance(sample_message.message_id, str)
        assert len(sample_message.message_id) > 0


# ---------------------------------------------------------------------------
# TestRelayQueue
# ---------------------------------------------------------------------------

class TestRelayQueue:
    """Validate SMTP relay queue operations: FIFO ordering, size tracking,
    and non-destructive peek semantics."""

    def test_enqueue_and_dequeue(self, queue, sample_message):
        msg_id = queue.enqueue(sample_message)
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0
        dequeued = queue.dequeue()
        assert dequeued is not None
        assert dequeued.to_addr == "buzz@enterprise.local"

    def test_size_tracks_enqueued_messages(self, queue, sample_message):
        assert queue.size() == 0
        queue.enqueue(sample_message)
        assert queue.size() == 1
        second = EmailMessage(
            message_id="msg-002",
            from_addr="a@b.com",
            to_addr="c@d.com",
            subject="Test",
            body="Body",
            headers={},
        )
        queue.enqueue(second)
        assert queue.size() == 2
        queue.dequeue()
        assert queue.size() == 1

    def test_peek_does_not_remove(self, queue, sample_message):
        queue.enqueue(sample_message)
        peeked = queue.peek()
        assert peeked is not None
        assert peeked.to_addr == sample_message.to_addr
        assert queue.size() == 1

    def test_dequeue_empty_returns_none(self, queue):
        assert queue.dequeue() is None
        assert queue.peek() is None


# ---------------------------------------------------------------------------
# TestBounceProcessor
# ---------------------------------------------------------------------------

class TestBounceProcessor:
    """Validate bounce classification, tracking, and hard-bounce suppression."""

    def test_process_hard_bounce(self, bounce_processor):
        record = bounce_processor.process_bounce(
            "msg-100", BounceType.HARD, "550 User unknown"
        )
        assert isinstance(record, DeliveryRecord)
        assert record.message_id == "msg-100"
        assert record.bounce_type == BounceType.HARD
        assert record.status == DeliveryStatus.BOUNCED
        assert "550" in record.error or "unknown" in record.error.lower()

    def test_process_soft_bounce(self, bounce_processor):
        record = bounce_processor.process_bounce(
            "msg-101", BounceType.SOFT, "452 Mailbox full"
        )
        assert isinstance(record, DeliveryRecord)
        assert record.bounce_type == BounceType.SOFT

    def test_get_bounces_returns_all(self, bounce_processor):
        bounce_processor.process_bounce("msg-200", BounceType.HARD, "550 No such user")
        bounce_processor.process_bounce("msg-201", BounceType.SOFT, "452 Try later")
        bounce_processor.process_bounce("msg-202", BounceType.UNDETERMINED, "Unknown")
        bounces = bounce_processor.get_bounces()
        assert len(bounces) == 3
        bounce_ids = [b.message_id for b in bounces]
        assert "msg-200" in bounce_ids
        assert "msg-201" in bounce_ids
        assert "msg-202" in bounce_ids

    def test_hard_bounced_address_blocked(self, bounce_processor):
        record = bounce_processor.process_bounce(
            "msg-300", BounceType.HARD, "550 User unknown"
        )
        to_addr = record.to_addr
        assert bounce_processor.is_hard_bounced(to_addr) is True

    def test_non_bounced_address_allowed(self, bounce_processor):
        assert bounce_processor.is_hard_bounced("clean@enterprise.local") is False


# ---------------------------------------------------------------------------
# TestDeliverabilityAnalytics
# ---------------------------------------------------------------------------

class TestDeliverabilityAnalytics:
    """Validate delivery rate calculations, bounce rate tracking, and
    statistical summary generation."""

    def _make_record(self, msg_id, status, bounce_type=None):
        return DeliveryRecord(
            message_id=msg_id,
            status=status,
            to_addr=f"{msg_id}@enterprise.local",
            attempts=1,
            last_attempt_at=None,
            bounce_type=bounce_type,
            error="",
        )

    def test_delivery_rate(self, analytics):
        analytics.record_delivery(self._make_record("m1", DeliveryStatus.DELIVERED))
        analytics.record_delivery(self._make_record("m2", DeliveryStatus.DELIVERED))
        analytics.record_delivery(self._make_record("m3", DeliveryStatus.BOUNCED, BounceType.HARD))
        rate = analytics.get_delivery_rate()
        assert isinstance(rate, float)
        assert abs(rate - 2.0 / 3.0) < 0.01

    def test_bounce_rate(self, analytics):
        analytics.record_delivery(self._make_record("m1", DeliveryStatus.DELIVERED))
        analytics.record_delivery(self._make_record("m2", DeliveryStatus.BOUNCED, BounceType.SOFT))
        rate = analytics.get_bounce_rate()
        assert isinstance(rate, float)
        assert abs(rate - 0.5) < 0.01

    def test_stats_dict_structure(self, analytics):
        analytics.record_delivery(self._make_record("m1", DeliveryStatus.DELIVERED))
        analytics.record_delivery(self._make_record("m2", DeliveryStatus.BOUNCED, BounceType.HARD))
        stats = analytics.get_stats()
        assert isinstance(stats, dict)
        assert "delivery_rate" in stats or "delivered" in stats or "total" in stats

    def test_zero_division_safe(self, analytics):
        rate = analytics.get_delivery_rate()
        assert isinstance(rate, float)
        assert rate == 0.0 or rate >= 0.0
        bounce_rate = analytics.get_bounce_rate()
        assert isinstance(bounce_rate, float)
        assert bounce_rate >= 0.0


# ---------------------------------------------------------------------------
# TestFizzSMTP2Dashboard
# ---------------------------------------------------------------------------

class TestFizzSMTP2Dashboard:
    """Validate dashboard rendering produces meaningful relay status output."""

    def test_render_returns_string(self):
        dashboard = FizzSMTP2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_smtp_info(self):
        dashboard = FizzSMTP2Dashboard()
        output = dashboard.render().lower()
        assert "smtp" in output or "relay" in output or "mail" in output or "queue" in output


# ---------------------------------------------------------------------------
# TestFizzSMTP2Middleware
# ---------------------------------------------------------------------------

class TestFizzSMTP2Middleware:
    """Validate middleware integration contract for the SMTP relay pipeline."""

    def test_name(self):
        mw = FizzSMTP2Middleware()
        assert mw.get_name() == "fizzsmtp2"

    def test_priority(self):
        mw = FizzSMTP2Middleware()
        assert mw.get_priority() == 162

    def test_process_calls_next(self):
        mw = FizzSMTP2Middleware()
        ctx = ProcessingContext(number=15, session_id="test")
        next_fn = MagicMock()
        mw.process(ctx, next_fn)
        next_fn.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Validate the subsystem factory returns correctly wired components."""

    def test_returns_tuple(self):
        result = create_fizzsmtp2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_queue_component_is_functional(self):
        queue, dashboard, middleware = create_fizzsmtp2_subsystem()
        assert isinstance(queue, RelayQueue)
        msg = EmailMessage(
            message_id="factory-msg-001",
            from_addr="factory@test.local",
            to_addr="dest@test.local",
            subject="Factory Test",
            body="Wiring validation.",
            headers={},
        )
        msg_id = queue.enqueue(msg)
        assert isinstance(msg_id, str)
        assert queue.size() >= 1

    def test_component_types(self):
        queue, dashboard, middleware = create_fizzsmtp2_subsystem()
        assert isinstance(queue, RelayQueue)
        assert isinstance(dashboard, FizzSMTP2Dashboard)
        assert isinstance(middleware, FizzSMTP2Middleware)

"""
Enterprise FizzBuzz Platform - FizzSMTP2: SMTP Relay

SMTP relay with persistent queuing, bounce classification (hard/soft),
deliverability analytics, and operational dashboard.

Architecture reference: Postfix, Amazon SES, SendGrid, Mailgun.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzsmtp2 import (
    FizzSMTP2Error, FizzSMTP2QueueError, FizzSMTP2DeliveryError,
    FizzSMTP2BounceError, FizzSMTP2RelayError, FizzSMTP2AnalyticsError,
    FizzSMTP2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzsmtp2")

EVENT_SMTP2_QUEUED = EventType.register("FIZZSMTP2_QUEUED")
EVENT_SMTP2_DELIVERED = EventType.register("FIZZSMTP2_DELIVERED")
EVENT_SMTP2_BOUNCED = EventType.register("FIZZSMTP2_BOUNCED")

FIZZSMTP2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 162


class DeliveryStatus(Enum):
    QUEUED = "queued"
    SENDING = "sending"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    DEFERRED = "deferred"
    FAILED = "failed"


class BounceType(Enum):
    HARD = "hard"
    SOFT = "soft"
    UNDETERMINED = "undetermined"


@dataclass
class FizzSMTP2Config:
    max_queue_size: int = 10000
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


@dataclass
class EmailMessage:
    message_id: str = ""
    from_addr: str = ""
    to_addr: str = ""
    subject: str = ""
    body: str = ""
    headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"msg-{uuid.uuid4().hex[:12]}"


@dataclass
class DeliveryRecord:
    message_id: str = ""
    status: DeliveryStatus = DeliveryStatus.QUEUED
    to_addr: str = ""
    attempts: int = 0
    last_attempt_at: Optional[datetime] = None
    bounce_type: Optional[BounceType] = None
    error: str = ""


# ============================================================
# Relay Queue
# ============================================================


class RelayQueue:
    """Persistent message queue for SMTP relay."""

    def __init__(self, config: Optional[FizzSMTP2Config] = None) -> None:
        self._config = config or FizzSMTP2Config()
        self._queue: deque[EmailMessage] = deque()

    def enqueue(self, message: EmailMessage) -> str:
        """Add a message to the relay queue. Returns message_id."""
        if not message.message_id:
            message.message_id = f"msg-{uuid.uuid4().hex[:12]}"
        self._queue.append(message)
        return message.message_id

    def dequeue(self) -> Optional[EmailMessage]:
        """Remove and return the next message, or None if empty."""
        if self._queue:
            return self._queue.popleft()
        return None

    def size(self) -> int:
        """Return the number of queued messages."""
        return len(self._queue)

    def peek(self) -> Optional[EmailMessage]:
        """Return the next message without removing it."""
        if self._queue:
            return self._queue[0]
        return None


# ============================================================
# Bounce Processor
# ============================================================


class BounceProcessor:
    """Classifies and tracks email bounces."""

    def __init__(self) -> None:
        self._bounces: List[DeliveryRecord] = []
        self._hard_bounced_addrs: set = set()

    def process_bounce(self, message_id: str, bounce_type: BounceType,
                       error: str = "") -> DeliveryRecord:
        """Record a bounce for a message."""
        record = DeliveryRecord(
            message_id=message_id,
            status=DeliveryStatus.BOUNCED,
            bounce_type=bounce_type,
            error=error,
            attempts=1,
            last_attempt_at=datetime.now(timezone.utc),
        )
        self._bounces.append(record)
        if bounce_type == BounceType.HARD:
            self._hard_bounced_addrs.add(record.to_addr)
        return record

    def get_bounces(self) -> List[DeliveryRecord]:
        """Return all bounce records."""
        return list(self._bounces)

    def get_hard_bounces(self) -> List[DeliveryRecord]:
        """Return only hard bounce records."""
        return [b for b in self._bounces if b.bounce_type == BounceType.HARD]

    def is_hard_bounced(self, to_addr: str) -> bool:
        """Check if an address has hard-bounced."""
        return to_addr in self._hard_bounced_addrs

    def mark_hard_bounced(self, to_addr: str) -> None:
        """Explicitly mark an address as hard-bounced."""
        self._hard_bounced_addrs.add(to_addr)


# ============================================================
# Deliverability Analytics
# ============================================================


class DeliverabilityAnalytics:
    """Tracks delivery rates and bounce rates."""

    def __init__(self) -> None:
        self._delivered = 0
        self._bounced = 0
        self._total = 0

    def record_delivery(self, record: DeliveryRecord) -> None:
        """Record a delivery outcome."""
        self._total += 1
        if record.status == DeliveryStatus.DELIVERED:
            self._delivered += 1
        elif record.status == DeliveryStatus.BOUNCED:
            self._bounced += 1

    def get_delivery_rate(self) -> float:
        """Return delivery rate as a fraction (0.0-1.0)."""
        if self._total == 0:
            return 0.0
        return self._delivered / self._total

    def get_bounce_rate(self) -> float:
        """Return bounce rate as a fraction (0.0-1.0)."""
        if self._total == 0:
            return 0.0
        return self._bounced / self._total

    def get_stats(self) -> Dict[str, Any]:
        """Return comprehensive delivery statistics."""
        return {
            "total": self._total,
            "delivered": self._delivered,
            "bounced": self._bounced,
            "delivery_rate": self.get_delivery_rate(),
            "bounce_rate": self.get_bounce_rate(),
        }


# ============================================================
# Dashboard & Middleware
# ============================================================


class FizzSMTP2Dashboard:
    """ASCII dashboard for the SMTP relay."""

    def __init__(self, queue: Optional[RelayQueue] = None,
                 bounce_processor: Optional[BounceProcessor] = None,
                 analytics: Optional[DeliverabilityAnalytics] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._queue = queue
        self._bounces = bounce_processor
        self._analytics = analytics
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzSMTP2 SMTP Relay Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZSMTP2_VERSION}",
        ]
        if self._queue:
            lines.append(f"  Queue:      {self._queue.size()} messages")
        if self._bounces:
            lines.append(f"  Bounces:    {len(self._bounces.get_bounces())}")
            lines.append(f"  Hard:       {len(self._bounces.get_hard_bounces())}")
        if self._analytics:
            stats = self._analytics.get_stats()
            lines.append(f"  Delivery:   {stats['delivery_rate']:.1f}%")
            lines.append(f"  Bounce:     {stats['bounce_rate']:.1f}%")
        return "\n".join(lines)


class FizzSMTP2Middleware(IMiddleware):
    """Middleware integration for FizzSMTP2."""

    def __init__(self, queue: Optional[RelayQueue] = None,
                 dashboard: Optional[FizzSMTP2Dashboard] = None) -> None:
        self._queue = queue
        self._dashboard = dashboard

    def get_name(self) -> str:
        return "fizzsmtp2"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzSMTP2 not initialized"


# ============================================================
# Factory
# ============================================================


def create_fizzsmtp2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[RelayQueue, FizzSMTP2Dashboard, FizzSMTP2Middleware]:
    """Create the FizzSMTP2 subsystem."""
    config = FizzSMTP2Config(dashboard_width=dashboard_width)
    queue = RelayQueue(config)
    bounce_processor = BounceProcessor()
    analytics = DeliverabilityAnalytics()

    # Seed with sample delivery records
    for status in [DeliveryStatus.DELIVERED] * 8 + [DeliveryStatus.BOUNCED] * 2:
        analytics.record_delivery(DeliveryRecord(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            status=status,
        ))

    dashboard = FizzSMTP2Dashboard(queue, bounce_processor, analytics, dashboard_width)
    middleware = FizzSMTP2Middleware(queue, dashboard)

    logger.info("FizzSMTP2 initialized: queue=%d, analytics=%s",
                queue.size(), analytics.get_stats())
    return queue, dashboard, middleware

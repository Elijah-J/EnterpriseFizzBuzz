"""
Enterprise FizzBuzz Platform - FizzEventMesh: Event Mesh

Topic hierarchy, dead-letter routing, delivery guarantees, pub/sub.

Architecture reference: Apache Kafka, AWS EventBridge, Solace, NATS.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzeventmesh import (
    FizzEventMeshError, FizzEventMeshTopicError, FizzEventMeshPublishError,
    FizzEventMeshSubscribeError, FizzEventMeshDeadLetterError,
    FizzEventMeshConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzeventmesh")

EVENT_EM_PUBLISHED = EventType.register("FIZZEVENTMESH_PUBLISHED")
EVENT_EM_DEAD_LETTER = EventType.register("FIZZEVENTMESH_DEAD_LETTER")

FIZZEVENTMESH_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 168


class DeliveryGuarantee(Enum):
    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"

class TopicType(Enum):
    STANDARD = "standard"
    FIFO = "fifo"
    DEAD_LETTER = "dead_letter"


@dataclass
class FizzEventMeshConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Event:
    event_id: str = ""
    topic: str = ""
    payload: Any = None
    timestamp: float = 0.0
    headers: Dict[str, str] = field(default_factory=dict)
    delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_LEAST_ONCE

@dataclass
class Topic:
    name: str = ""
    topic_type: TopicType = TopicType.STANDARD
    subscribers: List[str] = field(default_factory=list)
    dead_letter_topic: str = ""
    message_count: int = 0


class EventMesh:
    """Event mesh with topic management, pub/sub, and dead-letter routing."""

    def __init__(self) -> None:
        self._topics: Dict[str, Topic] = {}
        self._handlers: Dict[str, Dict[str, Callable]] = defaultdict(dict)
        self._dead_letters: Dict[str, List[Event]] = defaultdict(list)
        self._dedup_set: Set[str] = set()
        self._total_published = 0
        self._total_dead_lettered = 0

    def create_topic(self, name: str, topic_type: TopicType = TopicType.STANDARD,
                     dead_letter_topic: str = "") -> Topic:
        topic = Topic(name=name, topic_type=topic_type, dead_letter_topic=dead_letter_topic)
        self._topics[name] = topic
        return topic

    def publish(self, topic_name: str, payload: Any,
                guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_LEAST_ONCE,
                headers: Optional[Dict[str, str]] = None) -> Event:
        event = Event(
            event_id=uuid.uuid4().hex[:16],
            topic=topic_name,
            payload=payload,
            timestamp=time.time(),
            headers=headers or {},
            delivery_guarantee=guarantee,
        )

        # Exactly-once dedup
        if guarantee == DeliveryGuarantee.EXACTLY_ONCE:
            dedup_key = f"{topic_name}:{hash(str(payload))}"
            if dedup_key in self._dedup_set:
                return event  # Skip duplicate
            self._dedup_set.add(dedup_key)

        topic = self._topics.get(topic_name)
        if topic:
            topic.message_count += 1

        # Deliver to subscribers
        for handle, handler in list(self._handlers.get(topic_name, {}).items()):
            try:
                handler(event)
            except Exception as e:
                # Route to dead letter topic
                dlq = (topic.dead_letter_topic if topic else "") or (topic_name + ".dlq")
                self._dead_letters[dlq].append(event)
                self._total_dead_lettered += 1
                # Deliver to DLQ subscribers
                for dh in list(self._handlers.get(dlq, {}).values()):
                    try:
                        dh(event)
                    except Exception:
                        pass

        self._total_published += 1
        return event

    def subscribe(self, topic_name: str, handler: Callable) -> str:
        handle = f"sub-{uuid.uuid4().hex[:8]}"
        self._handlers[topic_name][handle] = handler
        topic = self._topics.get(topic_name)
        if topic:
            topic.subscribers.append(handle)
        return handle

    def unsubscribe(self, handle: str) -> None:
        for topic_handlers in self._handlers.values():
            topic_handlers.pop(handle, None)

    def get_topic(self, name: str) -> Optional[Topic]:
        return self._topics.get(name)

    def list_topics(self) -> List[Topic]:
        return list(self._topics.values())

    def get_dead_letters(self, topic: str) -> List[Event]:
        return list(self._dead_letters.get(topic, []))

    def get_stats(self) -> Dict[str, Any]:
        return {
            "topics": len(self._topics),
            "total_published": self._total_published,
            "total_dead_lettered": self._total_dead_lettered,
            "subscribers": sum(len(h) for h in self._handlers.values()),
        }


class FizzEventMeshDashboard:
    def __init__(self, mesh: Optional[EventMesh] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._mesh = mesh
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzEventMesh Dashboard".center(self._width), "=" * self._width,
                 f"  Version: {FIZZEVENTMESH_VERSION}"]
        if self._mesh:
            stats = self._mesh.get_stats()
            lines.append(f"  Topics:     {stats['topics']}")
            lines.append(f"  Published:  {stats['total_published']}")
            lines.append(f"  Dead Letter: {stats['total_dead_lettered']}")
        return "\n".join(lines)


class FizzEventMeshMiddleware(IMiddleware):
    def __init__(self, mesh: Optional[EventMesh] = None, dashboard: Optional[FizzEventMeshDashboard] = None) -> None:
        self._mesh = mesh; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzeventmesh"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(context)
        return context
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzeventmesh_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[EventMesh, FizzEventMeshDashboard, FizzEventMeshMiddleware]:
    mesh = EventMesh()
    mesh.create_topic("fizzbuzz.evaluations", TopicType.STANDARD, dead_letter_topic="fizzbuzz.evaluations.dlq")
    mesh.create_topic("fizzbuzz.evaluations.dlq", TopicType.DEAD_LETTER)
    mesh.create_topic("fizzbuzz.notifications", TopicType.STANDARD)
    mesh.create_topic("fizzbuzz.audit", TopicType.FIFO)
    dashboard = FizzEventMeshDashboard(mesh, dashboard_width)
    middleware = FizzEventMeshMiddleware(mesh, dashboard)
    logger.info("FizzEventMesh initialized: %d topics", len(mesh.list_topics()))
    return mesh, dashboard, middleware

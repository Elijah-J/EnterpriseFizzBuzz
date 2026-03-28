"""Tests for enterprise_fizzbuzz.infrastructure.fizzeventmesh"""
from __future__ import annotations
from unittest.mock import MagicMock, AsyncMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzeventmesh import (
    FIZZEVENTMESH_VERSION, MIDDLEWARE_PRIORITY, DeliveryGuarantee, TopicType,
    FizzEventMeshConfig, Event, Topic, EventMesh, FizzEventMeshDashboard,
    FizzEventMeshMiddleware, create_fizzeventmesh_subsystem,
)


@pytest.fixture
def mesh():
    m, _, _ = create_fizzeventmesh_subsystem()
    return m


@pytest.fixture
def subsystem():
    return create_fizzeventmesh_subsystem()


class TestConstants:
    def test_version(self):
        assert FIZZEVENTMESH_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 168


class TestEventMesh:
    def test_create_topic(self, mesh):
        topic = mesh.create_topic("orders.placed", TopicType.STANDARD)
        assert topic.name == "orders.placed"
        assert topic.topic_type == TopicType.STANDARD
        assert topic.message_count == 0

    def test_publish_delivers_to_subscribers(self, mesh):
        mesh.create_topic("fizz.events", TopicType.STANDARD)
        received = []
        mesh.subscribe("fizz.events", lambda evt: received.append(evt))
        event = mesh.publish("fizz.events", {"value": 3}, DeliveryGuarantee.AT_LEAST_ONCE)
        assert isinstance(event, Event)
        assert event.topic == "fizz.events"
        assert event.payload == {"value": 3}
        assert len(received) == 1
        assert received[0].payload == {"value": 3}

    def test_subscribe_returns_handle(self, mesh):
        mesh.create_topic("test.topic", TopicType.STANDARD)
        handle = mesh.subscribe("test.topic", lambda e: None)
        assert isinstance(handle, str)
        assert len(handle) > 0

    def test_unsubscribe(self, mesh):
        mesh.create_topic("test.topic", TopicType.STANDARD)
        received = []
        handle = mesh.subscribe("test.topic", lambda e: received.append(e))
        mesh.unsubscribe(handle)
        mesh.publish("test.topic", {"value": 1}, DeliveryGuarantee.AT_MOST_ONCE)
        assert len(received) == 0

    def test_dead_letter_routing_on_handler_error(self, mesh):
        """When a subscriber handler raises an exception, the event must be
        routed to the dead-letter topic associated with the source topic."""
        dlq_name = "fizz.events.dlq"
        mesh.create_topic(dlq_name, TopicType.DEAD_LETTER)
        mesh.create_topic("fizz.events", TopicType.STANDARD, dead_letter_topic=dlq_name)

        dead_received = []
        mesh.subscribe(dlq_name, lambda e: dead_received.append(e))

        def failing_handler(evt):
            raise RuntimeError("handler crashed")

        mesh.subscribe("fizz.events", failing_handler)
        mesh.publish("fizz.events", {"bad": True}, DeliveryGuarantee.AT_LEAST_ONCE)

        assert len(dead_received) >= 1, "Failed event must appear in dead-letter topic"
        assert dead_received[0].payload == {"bad": True}

    def test_get_topic(self, mesh):
        mesh.create_topic("lookup.topic", TopicType.STANDARD)
        topic = mesh.get_topic("lookup.topic")
        assert topic is not None
        assert topic.name == "lookup.topic"

    def test_list_topics(self, mesh):
        mesh.create_topic("alpha", TopicType.STANDARD)
        mesh.create_topic("beta", TopicType.FIFO)
        topics = mesh.list_topics()
        names = [t.name for t in topics]
        assert "alpha" in names
        assert "beta" in names

    def test_exactly_once_dedup(self, mesh):
        """Publishing the same event_id twice with EXACTLY_ONCE guarantee
        must deliver to subscribers only once."""
        mesh.create_topic("dedup.topic", TopicType.STANDARD)
        received = []
        mesh.subscribe("dedup.topic", lambda e: received.append(e))
        evt1 = mesh.publish("dedup.topic", {"n": 1}, DeliveryGuarantee.EXACTLY_ONCE,
                            headers={"idempotency-key": "unique-42"})
        evt2 = mesh.publish("dedup.topic", {"n": 1}, DeliveryGuarantee.EXACTLY_ONCE,
                            headers={"idempotency-key": "unique-42"})
        assert len(received) == 1, "Exactly-once must deduplicate by idempotency key"

    def test_get_dead_letters(self, mesh):
        dlq_name = "orders.dlq"
        mesh.create_topic(dlq_name, TopicType.DEAD_LETTER)
        mesh.create_topic("orders", TopicType.STANDARD, dead_letter_topic=dlq_name)
        mesh.subscribe("orders", lambda e: (_ for _ in ()).throw(ValueError("boom")))
        mesh.publish("orders", {"order": 99}, DeliveryGuarantee.AT_LEAST_ONCE)
        dead = mesh.get_dead_letters(dlq_name)
        assert len(dead) >= 1
        assert dead[0].payload == {"order": 99}

    def test_stats(self, mesh):
        mesh.create_topic("stats.topic", TopicType.STANDARD)
        mesh.publish("stats.topic", {"x": 1}, DeliveryGuarantee.AT_MOST_ONCE)
        stats = mesh.get_stats()
        assert isinstance(stats, dict)
        assert "topics" in stats or "topic_count" in stats or len(stats) > 0

    def test_fifo_ordering(self, mesh):
        """FIFO topics must deliver events in the order they were published."""
        mesh.create_topic("fifo.topic", TopicType.FIFO)
        received = []
        mesh.subscribe("fifo.topic", lambda e: received.append(e.payload))
        for i in range(10):
            mesh.publish("fifo.topic", {"seq": i}, DeliveryGuarantee.AT_LEAST_ONCE)
        assert [r["seq"] for r in received] == list(range(10))


class TestFizzEventMeshDashboard:
    def test_render_returns_string(self):
        _, dashboard, _ = create_fizzeventmesh_subsystem()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_mesh_info(self):
        _, dashboard, _ = create_fizzeventmesh_subsystem()
        output = dashboard.render()
        lower = output.lower()
        assert "mesh" in lower or "event" in lower or "topic" in lower


class TestFizzEventMeshMiddleware:
    def test_name(self):
        _, _, mw = create_fizzeventmesh_subsystem()
        assert mw.get_name() == "fizzeventmesh"

    def test_priority(self):
        _, _, mw = create_fizzeventmesh_subsystem()
        assert mw.get_priority() == 168

    def test_process(self):
        _, _, mw = create_fizzeventmesh_subsystem()
        ctx = MagicMock()
        next_handler = MagicMock()
        result = mw.process(ctx, next_handler)
        next_handler.assert_called_once()


class TestCreateSubsystem:
    def test_returns_tuple_of_three(self):
        result = create_fizzeventmesh_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_mesh_is_functional(self):
        mesh, _, _ = create_fizzeventmesh_subsystem()
        assert isinstance(mesh, EventMesh)
        topic = mesh.create_topic("sub.test", TopicType.STANDARD)
        assert topic.name == "sub.test"

    def test_has_default_topics(self):
        mesh, _, _ = create_fizzeventmesh_subsystem()
        topics = mesh.list_topics()
        assert isinstance(topics, list)

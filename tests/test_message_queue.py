"""
Enterprise FizzBuzz Platform - Message Queue & Event Bus Test Suite

Tests for the Kafka-style message queue backed by Python lists.
Every test in this file validates that a list.append() and
list.__getitem__() work correctly under the guise of distributed
messaging infrastructure. The tests are thorough, the assertions
are precise, and the underlying data structure is a list.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    BrokerError,
    ConsumerError,
    ConsumerGroupError,
    DuplicateMessageError,
    MessageQueueError,
    OffsetOutOfRangeError,
    PartitionOutOfRangeError,
    ProducerError,
    SchemaValidationError,
    TopicAlreadyExistsError,
    TopicNotFoundError,
    MessageSerializationError,
    RebalanceError,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.message_queue import (
    Consumer,
    ConsumerGroup,
    ConsumerState,
    IdempotencyLayer,
    MQDashboard,
    MQMiddleware,
    Message,
    MessageBroker,
    MessageQueueBridge,
    OffsetManager,
    Partition,
    PartitionStrategy,
    Partitioner,
    Producer,
    SchemaRegistry,
    Topic,
    create_message_queue_subsystem,
)
from enterprise_fizzbuzz.infrastructure.observers import EventBus


# ============================================================
# Helpers
# ============================================================


def _make_event_bus() -> EventBus:
    return EventBus()


def _make_broker(**kwargs) -> MessageBroker:
    return MessageBroker(**kwargs)


def _make_producer(**kwargs) -> Producer:
    return Producer(**kwargs)


# ============================================================
# Message Tests
# ============================================================


class TestMessage:
    """Tests for the Message frozen dataclass."""

    def test_message_creation(self):
        msg = Message(topic="test", payload={"key": "value"})
        assert msg.topic == "test"
        assert msg.payload == {"key": "value"}
        assert msg.partition == -1
        assert msg.offset == -1

    def test_message_is_frozen(self):
        msg = Message(topic="test")
        with pytest.raises(AttributeError):
            msg.topic = "modified"

    def test_idempotency_key_computation(self):
        payload = {"number": 15, "result": "FizzBuzz"}
        key1 = Message.compute_idempotency_key(payload)
        key2 = Message.compute_idempotency_key(payload)
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex digest

    def test_idempotency_key_different_payloads(self):
        key1 = Message.compute_idempotency_key({"a": 1})
        key2 = Message.compute_idempotency_key({"a": 2})
        assert key1 != key2

    def test_idempotency_key_order_independent(self):
        key1 = Message.compute_idempotency_key({"a": 1, "b": 2})
        key2 = Message.compute_idempotency_key({"b": 2, "a": 1})
        assert key1 == key2  # sort_keys=True ensures order independence


# ============================================================
# Partition Tests (THE JOKE)
# ============================================================


class TestPartition:
    """Tests for the Partition class (a.k.a. Python list in disguise)."""

    def test_partition_creation(self):
        p = Partition(0, "test-topic")
        assert p.partition_id == 0
        assert p.topic_name == "test-topic"
        assert p.message_count == 0
        assert p.high_watermark == 0

    def test_append_message(self):
        p = Partition(0, "test")
        msg = Message(topic="test", payload={"x": 1})
        offset = p.append(msg)
        assert offset == 0
        assert p.message_count == 1
        assert p.high_watermark == 1

    def test_append_multiple_messages(self):
        p = Partition(0, "test")
        for i in range(5):
            offset = p.append(Message(topic="test", payload={"i": i}))
            assert offset == i
        assert p.message_count == 5

    def test_read_message(self):
        p = Partition(0, "test")
        p.append(Message(topic="test", payload={"hello": "world"}))
        msg = p.read(0)
        assert msg.payload == {"hello": "world"}
        assert msg.offset == 0
        assert msg.partition == 0

    def test_read_out_of_range(self):
        p = Partition(0, "test")
        with pytest.raises(OffsetOutOfRangeError):
            p.read(0)

    def test_read_negative_offset(self):
        p = Partition(0, "test")
        p.append(Message(topic="test", payload={}))
        with pytest.raises(OffsetOutOfRangeError):
            p.read(-1)

    def test_read_batch(self):
        p = Partition(0, "test")
        for i in range(10):
            p.append(Message(topic="test", payload={"i": i}))
        batch = p.read_batch(3, 4)
        assert len(batch) == 4
        assert batch[0].payload["i"] == 3
        assert batch[3].payload["i"] == 6

    def test_read_batch_partial(self):
        p = Partition(0, "test")
        for i in range(3):
            p.append(Message(topic="test", payload={"i": i}))
        batch = p.read_batch(1, 10)  # Request more than available
        assert len(batch) == 2

    def test_statistics(self):
        p = Partition(0, "test")
        p.append(Message(topic="test", payload={"x": 1}))
        stats = p.get_statistics()
        assert stats["partition_id"] == 0
        assert stats["message_count"] == 1
        assert stats["implementation"] == "Python list"
        assert stats["replication_factor"] == 1


# ============================================================
# Topic Tests
# ============================================================


class TestTopic:
    """Tests for the Topic class."""

    def test_topic_creation(self):
        t = Topic("my-topic", num_partitions=3)
        assert t.name == "my-topic"
        assert t.num_partitions == 3

    def test_topic_zero_partitions_raises(self):
        with pytest.raises(BrokerError):
            Topic("bad-topic", num_partitions=0)

    def test_get_partition(self):
        t = Topic("test", num_partitions=3)
        p = t.get_partition(1)
        assert p.partition_id == 1

    def test_get_partition_out_of_range(self):
        t = Topic("test", num_partitions=2)
        with pytest.raises(PartitionOutOfRangeError):
            t.get_partition(5)

    def test_total_messages(self):
        t = Topic("test", num_partitions=2)
        t.get_partition(0).append(Message(topic="test", payload={"a": 1}))
        t.get_partition(1).append(Message(topic="test", payload={"b": 2}))
        assert t.get_total_messages() == 2

    def test_subscriber_count(self):
        t = Topic("test", num_partitions=1)
        assert t.subscriber_count == 0
        t.increment_subscribers()
        assert t.subscriber_count == 1
        t.decrement_subscribers()
        assert t.subscriber_count == 0
        t.decrement_subscribers()  # Should not go below 0
        assert t.subscriber_count == 0


# ============================================================
# Partitioner Tests
# ============================================================


class TestPartitioner:
    """Tests for the Partitioner class."""

    def test_hash_partitioner_deterministic(self):
        p = Partitioner(PartitionStrategy.HASH)
        result1 = p.assign_partition("key1", 3)
        result2 = p.assign_partition("key1", 3)
        assert result1 == result2

    def test_hash_partitioner_range(self):
        p = Partitioner(PartitionStrategy.HASH)
        for i in range(100):
            result = p.assign_partition(f"key{i}", 3)
            assert 0 <= result < 3

    def test_hash_partitioner_none_key_falls_back(self):
        p = Partitioner(PartitionStrategy.HASH)
        result = p.assign_partition(None, 3)
        assert 0 <= result < 3

    def test_round_robin_partitioner(self):
        p = Partitioner(PartitionStrategy.ROUND_ROBIN)
        results = [p.assign_partition(None, 3) for _ in range(6)]
        assert results == [0, 1, 2, 0, 1, 2]

    def test_sticky_partitioner(self):
        p = Partitioner(PartitionStrategy.STICKY)
        results = [p.assign_partition(None, 3) for _ in range(5)]
        assert all(r == 0 for r in results)  # Always partition 0

    def test_sticky_partitioner_reset(self):
        p = Partitioner(PartitionStrategy.STICKY)
        assert p.assign_partition(None, 3) == 0
        p.reset_sticky(2)
        assert p.assign_partition(None, 3) == 2

    def test_zero_partitions_raises(self):
        p = Partitioner(PartitionStrategy.HASH)
        with pytest.raises(BrokerError):
            p.assign_partition("key", 0)


# ============================================================
# Schema Registry Tests
# ============================================================


class TestSchemaRegistry:
    """Tests for the SchemaRegistry class."""

    def test_register_and_validate(self):
        sr = SchemaRegistry()
        sr.register_schema("test-topic", ["name", "age"])
        assert sr.validate("test-topic", {"name": "Alice", "age": 30})

    def test_validation_fails_missing_fields(self):
        sr = SchemaRegistry()
        sr.register_schema("test-topic", ["name", "age"])
        with pytest.raises(SchemaValidationError):
            sr.validate("test-topic", {"name": "Alice"})

    def test_validation_no_schema_passes(self):
        sr = SchemaRegistry()
        assert sr.validate("unregistered", {"anything": "goes"})

    def test_get_schema(self):
        sr = SchemaRegistry()
        sr.register_schema("test", ["a", "b"])
        schema = sr.get_schema("test")
        assert schema is not None
        assert "a" in schema["required_fields"]

    def test_get_nonexistent_schema(self):
        sr = SchemaRegistry()
        assert sr.get_schema("nope") is None

    def test_get_all_schemas(self):
        sr = SchemaRegistry()
        sr.register_schema("t1", ["a"])
        sr.register_schema("t2", ["b"])
        schemas = sr.get_all_schemas()
        assert "t1" in schemas
        assert "t2" in schemas


# ============================================================
# Idempotency Layer Tests
# ============================================================


class TestIdempotencyLayer:
    """Tests for the IdempotencyLayer (a Python set with extra steps)."""

    def test_new_message_accepted(self):
        il = IdempotencyLayer()
        assert il.check_and_record("key1") is True
        assert il.total_unique_messages == 1

    def test_duplicate_rejected(self):
        il = IdempotencyLayer()
        il.check_and_record("key1")
        assert il.check_and_record("key1") is False
        assert il.duplicates_detected == 1

    def test_different_keys_accepted(self):
        il = IdempotencyLayer()
        assert il.check_and_record("key1") is True
        assert il.check_and_record("key2") is True
        assert il.total_unique_messages == 2

    def test_reset(self):
        il = IdempotencyLayer()
        il.check_and_record("key1")
        il.reset()
        assert il.total_unique_messages == 0
        assert il.check_and_record("key1") is True  # Accepted again

    def test_statistics(self):
        il = IdempotencyLayer()
        il.check_and_record("a")
        il.check_and_record("b")
        il.check_and_record("a")  # Duplicate
        stats = il.get_statistics()
        assert stats["unique_messages"] == 2
        assert stats["duplicates_detected"] == 1
        assert "SHA-256" in stats["implementation"]


# ============================================================
# Offset Manager Tests
# ============================================================


class TestOffsetManager:
    """Tests for the OffsetManager class."""

    def test_commit_and_retrieve(self):
        om = OffsetManager()
        om.commit("group1", "topic1", 0, 42)
        assert om.get_committed_offset("group1", "topic1", 0) == 42

    def test_default_offset_is_zero(self):
        om = OffsetManager()
        assert om.get_committed_offset("nonexistent", "topic", 0) == 0

    def test_multiple_groups(self):
        om = OffsetManager()
        om.commit("g1", "t1", 0, 10)
        om.commit("g2", "t1", 0, 20)
        assert om.get_committed_offset("g1", "t1", 0) == 10
        assert om.get_committed_offset("g2", "t1", 0) == 20

    def test_total_commits(self):
        om = OffsetManager()
        om.commit("g1", "t1", 0, 1)
        om.commit("g1", "t1", 0, 2)
        assert om.total_commits == 2

    def test_get_all_offsets(self):
        om = OffsetManager()
        om.commit("g1", "t1", 0, 5)
        om.commit("g1", "t2", 1, 10)
        offsets = om.get_all_offsets("g1")
        assert "t1" in offsets
        assert "t2" in offsets


# ============================================================
# Consumer Tests
# ============================================================


class TestConsumer:
    """Tests for the Consumer class."""

    def test_consumer_creation(self):
        c = Consumer("c1", "group1")
        assert c.consumer_id == "c1"
        assert c.group_id == "group1"
        assert c.state == ConsumerState.UNASSIGNED

    def test_assign_partitions(self):
        c = Consumer("c1", "group1")
        c.assign_partitions("topic1", [0, 1])
        assert c.state == ConsumerState.ASSIGNED
        assignments = c.get_assigned_partitions()
        assert "topic1" in assignments
        assert assignments["topic1"] == [0, 1]

    def test_revoke_all(self):
        c = Consumer("c1", "group1")
        c.assign_partitions("topic1", [0, 1])
        prev = c.revoke_all()
        assert "topic1" in prev
        assert c.state == ConsumerState.UNASSIGNED

    def test_poll(self):
        topic = Topic("test", num_partitions=2)
        topic.get_partition(0).append(Message(topic="test", payload={"a": 1}))
        topic.get_partition(0).append(Message(topic="test", payload={"b": 2}))

        c = Consumer("c1", "g1")
        c.assign_partitions("test", [0])
        messages = c.poll({"test": topic})
        assert len(messages) == 2
        assert c.messages_consumed == 2

    def test_poll_closed_consumer_raises(self):
        c = Consumer("c1", "g1")
        c.close()
        with pytest.raises(ConsumerError):
            c.poll({})

    def test_close(self):
        c = Consumer("c1", "g1")
        c.assign_partitions("t", [0])
        c.close()
        assert c.state == ConsumerState.CLOSED


# ============================================================
# Consumer Group Tests
# ============================================================


class TestConsumerGroup:
    """Tests for the ConsumerGroup class."""

    def test_group_creation(self):
        g = ConsumerGroup("g1", ["topic1"])
        assert g.group_id == "g1"
        assert g.consumer_count == 0
        assert g.subscribed_topics == ["topic1"]

    def test_add_consumer(self):
        g = ConsumerGroup("g1", ["topic1"])
        c = Consumer("c1", "g1")
        g.add_consumer(c)
        assert g.consumer_count == 1

    def test_remove_consumer(self):
        g = ConsumerGroup("g1", ["topic1"])
        c = Consumer("c1", "g1")
        g.add_consumer(c)
        removed = g.remove_consumer("c1")
        assert removed is not None
        assert g.consumer_count == 0

    def test_remove_nonexistent_consumer(self):
        g = ConsumerGroup("g1", [])
        removed = g.remove_consumer("nonexistent")
        assert removed is None

    def test_rebalance(self):
        topic = Topic("t1", num_partitions=3)
        g = ConsumerGroup("g1", ["t1"])
        c1 = Consumer("c1", "g1")
        c2 = Consumer("c2", "g1")
        g.add_consumer(c1)
        g.add_consumer(c2)

        report = g.rebalance({"t1": topic})
        assert report.group_id == "g1"
        assert g.generation_id == 1
        assert g.rebalance_count == 1

        # Both consumers should have partitions assigned
        a1 = c1.get_assigned_partitions()
        a2 = c2.get_assigned_partitions()
        assert "t1" in a1 or "t1" in a2

    def test_rebalance_single_consumer_gets_all(self):
        topic = Topic("t1", num_partitions=3)
        g = ConsumerGroup("g1", ["t1"])
        c = Consumer("c1", "g1")
        g.add_consumer(c)

        g.rebalance({"t1": topic})
        assignments = c.get_assigned_partitions()
        assert len(assignments.get("t1", [])) == 3

    def test_rebalance_no_consumers(self):
        topic = Topic("t1", num_partitions=3)
        g = ConsumerGroup("g1", ["t1"])
        report = g.rebalance({"t1": topic})
        assert report.group_id == "g1"

    def test_rebalance_history(self):
        topic = Topic("t1", num_partitions=2)
        g = ConsumerGroup("g1", ["t1"])
        c = Consumer("c1", "g1")
        g.add_consumer(c)
        g.rebalance({"t1": topic})
        g.rebalance({"t1": topic})
        history = g.get_rebalance_history()
        assert len(history) == 2


# ============================================================
# Producer Tests
# ============================================================


class TestProducer:
    """Tests for the Producer class."""

    def test_send_message(self):
        topic = Topic("test", num_partitions=3)
        p = Producer(enable_idempotency=False, enable_schema_validation=False)
        msg = p.send(topic, {"hello": "world"}, key="k1")
        assert msg.topic == "test"
        assert msg.offset >= 0
        assert msg.partition >= 0
        assert p.messages_sent == 1

    def test_send_with_schema_validation(self):
        sr = SchemaRegistry()
        sr.register_schema("test", ["name"])
        topic = Topic("test", num_partitions=1)
        p = Producer(schema_registry=sr, enable_idempotency=False)
        msg = p.send(topic, {"name": "Alice"})
        assert msg.offset == 0

    def test_send_schema_validation_failure(self):
        sr = SchemaRegistry()
        sr.register_schema("test", ["name"])
        topic = Topic("test", num_partitions=1)
        p = Producer(schema_registry=sr, enable_idempotency=False)
        with pytest.raises(SchemaValidationError):
            p.send(topic, {"wrong": "field"})

    def test_send_duplicate_detected(self):
        topic = Topic("test", num_partitions=1)
        p = Producer(enable_schema_validation=False)
        p.send(topic, {"x": 1}, key="k1")
        with pytest.raises(DuplicateMessageError):
            p.send(topic, {"x": 1}, key="k1")  # Same payload

    def test_send_idempotency_disabled_allows_duplicates(self):
        topic = Topic("test", num_partitions=1)
        p = Producer(enable_idempotency=False, enable_schema_validation=False)
        p.send(topic, {"x": 1})
        p.send(topic, {"x": 1})  # Should not raise
        assert p.messages_sent == 2

    def test_send_with_event_bus(self):
        eb = _make_event_bus()
        topic = Topic("test", num_partitions=1)
        p = Producer(
            event_bus=eb,
            enable_idempotency=False,
            enable_schema_validation=False,
        )
        p.send(topic, {"data": "value"})
        history = eb.get_event_history()
        mq_events = [e for e in history if e.event_type == EventType.MQ_MESSAGE_PUBLISHED]
        assert len(mq_events) == 1


# ============================================================
# Message Broker Tests
# ============================================================


class TestMessageBroker:
    """Tests for the MessageBroker class."""

    def test_broker_creation(self):
        broker = _make_broker()
        assert len(broker.list_topics()) == 5
        assert "evaluations.requested" in broker.list_topics()
        assert "fizzbuzz.feelings" in broker.list_topics()

    def test_default_topics_exist(self):
        broker = _make_broker()
        expected = [
            "evaluations.requested",
            "evaluations.completed",
            "audit.events",
            "alerts.critical",
            "fizzbuzz.feelings",
        ]
        for name in expected:
            topic = broker.get_topic(name)
            assert topic.name == name

    def test_create_topic(self):
        broker = _make_broker()
        topic = broker.create_topic("new-topic", num_partitions=2)
        assert topic.name == "new-topic"
        assert topic.num_partitions == 2

    def test_create_duplicate_topic_raises(self):
        broker = _make_broker()
        with pytest.raises(TopicAlreadyExistsError):
            broker.create_topic("evaluations.requested")

    def test_get_nonexistent_topic_raises(self):
        broker = _make_broker()
        with pytest.raises(TopicNotFoundError):
            broker.get_topic("does-not-exist")

    def test_default_consumer_groups(self):
        broker = _make_broker()
        groups = broker.list_consumer_groups()
        assert "fizzbuzz-evaluators" in groups
        assert "audit-loggers" in groups
        assert "feelings-listener" in groups

    def test_feelings_topic_zero_subscribers(self):
        """THE FEELINGS TOPIC: nobody subscribes. Nobody cares."""
        broker = _make_broker()
        feelings = broker.get_feelings_topic_stats()
        assert feelings["exists"] is True
        assert feelings["subscribers"] == 0
        assert feelings["loneliness_index"] == "MAXIMUM"
        assert feelings["existential_purpose"] == "none"

    def test_topic_lag_calculation(self):
        broker = _make_broker()
        topic = broker.get_topic("evaluations.requested")
        # Append some messages
        topic.get_partition(0).append(
            Message(topic="evaluations.requested", payload={"n": 1})
        )
        topic.get_partition(0).append(
            Message(topic="evaluations.requested", payload={"n": 2})
        )
        lag = broker.get_topic_lag("fizzbuzz-evaluators", "evaluations.requested")
        assert lag[0] == 2  # 2 messages behind

    def test_total_lag(self):
        broker = _make_broker()
        topic = broker.get_topic("evaluations.requested")
        for i in range(5):
            topic.get_partition(0).append(
                Message(topic="evaluations.requested", payload={"n": i})
            )
        total = broker.get_total_lag("fizzbuzz-evaluators")
        assert total == 5

    def test_broker_statistics(self):
        broker = _make_broker()
        stats = broker.get_statistics()
        assert stats["cluster_size"] == 1
        assert stats["total_topics"] == 5
        assert "feelings_topic" in stats


# ============================================================
# MessageQueueBridge Tests
# ============================================================


class TestMessageQueueBridge:
    """Tests for the MessageQueueBridge (EventBus -> MQ)."""

    def test_bridge_forwards_events(self):
        broker = _make_broker()
        producer = _make_producer(enable_idempotency=False, enable_schema_validation=False)
        bridge = MessageQueueBridge(broker, producer)

        event = Event(
            event_type=EventType.NUMBER_PROCESSED,
            payload={"number": 15, "result": "FizzBuzz"},
            source="test",
        )
        bridge.on_event(event)
        assert bridge.messages_bridged == 1

    def test_bridge_routes_to_feelings_for_unknown_events(self):
        broker = _make_broker()
        producer = _make_producer(enable_idempotency=False, enable_schema_validation=False)
        bridge = MessageQueueBridge(broker, producer)

        event = Event(
            event_type=EventType.CACHE_HIT,
            payload={"key": "15"},
            source="test",
        )
        bridge.on_event(event)
        assert bridge.feelings_messages == 1

    def test_bridge_ignores_mq_events(self):
        """MQ events should not be bridged (prevents infinite loops)."""
        broker = _make_broker()
        producer = _make_producer(enable_idempotency=False, enable_schema_validation=False)
        bridge = MessageQueueBridge(broker, producer)

        event = Event(
            event_type=EventType.MQ_MESSAGE_PUBLISHED,
            payload={},
            source="test",
        )
        bridge.on_event(event)
        assert bridge.messages_bridged == 0

    def test_bridge_name(self):
        broker = _make_broker()
        producer = _make_producer()
        bridge = MessageQueueBridge(broker, producer)
        assert bridge.get_name() == "MessageQueueBridge"


# ============================================================
# MQMiddleware Tests
# ============================================================


class TestMQMiddleware:
    """Tests for the MQMiddleware class."""

    def test_middleware_name_and_priority(self):
        broker = _make_broker()
        producer = _make_producer(enable_idempotency=False, enable_schema_validation=False)
        mw = MQMiddleware(broker, producer)
        assert mw.get_name() == "MQMiddleware"
        assert mw.get_priority() == 45

    def test_middleware_publishes_events(self):
        broker = _make_broker()
        producer = _make_producer(enable_idempotency=False, enable_schema_validation=False)
        mw = MQMiddleware(broker, producer)

        ctx = ProcessingContext(number=15, session_id="test-session")

        def handler(c: ProcessingContext) -> ProcessingContext:
            from enterprise_fizzbuzz.domain.models import FizzBuzzResult
            c.results.append(FizzBuzzResult(number=15, output="FizzBuzz"))
            return c

        result = mw.process(ctx, handler)
        assert result.results[0].output == "FizzBuzz"
        assert mw.evaluations_published >= 1


# ============================================================
# MQDashboard Tests
# ============================================================


class TestMQDashboard:
    """Tests for the MQDashboard ASCII rendering."""

    def test_render_dashboard(self):
        broker = _make_broker()
        output = MQDashboard.render(broker, width=60)
        assert "MESSAGE QUEUE DASHBOARD" in output
        assert "evaluations.requested" in output
        assert "fizzbuzz.feelings" in output
        assert "FEELINGS REPORT" in output

    def test_render_topics(self):
        broker = _make_broker()
        output = MQDashboard.render_topics(broker, width=60)
        assert "TOPIC LISTING" in output
        assert "nobody subscribes" in output

    def test_render_lag(self):
        broker = _make_broker()
        output = MQDashboard.render_lag(broker, width=60)
        assert "CONSUMER LAG REPORT" in output


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateMessageQueueSubsystem:
    """Tests for the create_message_queue_subsystem factory."""

    def test_creates_all_components(self):
        broker, producer, middleware, bridge = create_message_queue_subsystem()
        assert isinstance(broker, MessageBroker)
        assert isinstance(producer, Producer)
        assert isinstance(middleware, MQMiddleware)
        assert isinstance(bridge, MessageQueueBridge)

    def test_default_schemas_registered(self):
        broker, producer, middleware, bridge = create_message_queue_subsystem()
        # Should not raise for valid payloads
        topic = broker.get_topic("evaluations.requested")
        producer.send(
            topic,
            {"number": 1, "session_id": "s1", "action": "requested"},
            key="1",
        )

    def test_custom_partitioner_strategy(self):
        broker, producer, mw, bridge = create_message_queue_subsystem(
            partitioner_strategy="round_robin",
        )
        assert producer._partitioner.strategy == PartitionStrategy.ROUND_ROBIN


# ============================================================
# Exception Tests
# ============================================================


class TestMessageQueueExceptions:
    """Tests for all MQ exception types."""

    def test_topic_not_found_error(self):
        err = TopicNotFoundError("missing-topic")
        assert "missing-topic" in str(err)
        assert err.error_code == "EFP-MQ01"

    def test_partition_out_of_range_error(self):
        err = PartitionOutOfRangeError("topic1", 5, 3)
        assert "5" in str(err)
        assert err.error_code == "EFP-MQ02"

    def test_consumer_group_error(self):
        err = ConsumerGroupError("group1", "test reason")
        assert err.error_code == "EFP-MQ03"

    def test_offset_out_of_range_error(self):
        err = OffsetOutOfRangeError("topic1", 0, 100, 50)
        assert err.error_code == "EFP-MQ04"

    def test_schema_validation_error(self):
        err = SchemaValidationError("topic1", "missing fields")
        assert err.error_code == "EFP-MQ05"

    def test_duplicate_message_error(self):
        err = DuplicateMessageError("abc123", "topic1")
        assert err.error_code == "EFP-MQ06"

    def test_producer_error(self):
        err = ProducerError("topic1", "list.append() failed")
        assert err.error_code == "EFP-MQ07"

    def test_consumer_error(self):
        err = ConsumerError("c1", "lost in the list")
        assert err.error_code == "EFP-MQ08"

    def test_rebalance_error(self):
        err = RebalanceError("g1", "could not reach consensus")
        assert err.error_code == "EFP-MQ09"

    def test_broker_error(self):
        err = BrokerError("something went wrong")
        assert err.error_code == "EFP-MQ10"

    def test_topic_already_exists_error(self):
        err = TopicAlreadyExistsError("existing-topic")
        assert err.error_code == "EFP-MQ11"

    def test_message_serialization_error(self):
        err = MessageSerializationError("bad payload")
        assert err.error_code == "EFP-MQ12"

    def test_all_inherit_from_message_queue_error(self):
        """All MQ exceptions must inherit from MessageQueueError."""
        exceptions = [
            TopicNotFoundError("t"),
            PartitionOutOfRangeError("t", 0, 1),
            ConsumerGroupError("g", "r"),
            OffsetOutOfRangeError("t", 0, 0, 0),
            SchemaValidationError("t", "r"),
            DuplicateMessageError("k", "t"),
            ProducerError("t", "r"),
            ConsumerError("c", "r"),
            RebalanceError("g", "r"),
            BrokerError("r"),
            TopicAlreadyExistsError("t"),
            MessageSerializationError("r"),
        ]
        for exc in exceptions:
            assert isinstance(exc, MessageQueueError)


# ============================================================
# Integration Tests
# ============================================================


class TestMessageQueueIntegration:
    """Integration tests for the complete message queue subsystem."""

    def test_end_to_end_publish_consume(self):
        """Publish messages, create a consumer, and consume them."""
        broker, producer, mw, bridge = create_message_queue_subsystem(
            enable_idempotency=False,
        )

        # Publish messages
        topic = broker.get_topic("evaluations.completed")
        for i in range(5):
            producer.send(
                topic,
                {
                    "number": i,
                    "session_id": "s1",
                    "output": str(i),
                    "action": "evaluation_completed",
                },
                key=str(i),
            )

        # Create consumer and consume
        group = broker.create_consumer_group(
            "test-group", ["evaluations.completed"]
        )
        consumer = Consumer("c1", "test-group")
        group.add_consumer(consumer)
        group.rebalance(broker.get_all_topics())

        messages = consumer.poll(broker.get_all_topics())
        assert len(messages) == 5

    def test_bridge_with_event_bus(self):
        """Test that the bridge properly forwards EventBus events to MQ."""
        eb = _make_event_bus()
        broker, producer, mw, bridge = create_message_queue_subsystem(
            event_bus=eb,
            enable_idempotency=False,
            enable_schema_validation=False,
        )
        eb.subscribe(bridge)

        # Publish an event through the EventBus
        eb.publish(Event(
            event_type=EventType.NUMBER_PROCESSED,
            payload={"number": 15},
            source="test",
        ))

        assert bridge.messages_bridged >= 1

    def test_feelings_topic_gets_unrouted_events(self):
        """Events without explicit routing go to fizzbuzz.feelings."""
        broker, producer, mw, bridge = create_message_queue_subsystem(
            enable_idempotency=False,
            enable_schema_validation=False,
        )

        # Send an event that has no explicit routing
        event = Event(
            event_type=EventType.CACHE_EVICTION,
            payload={"key": "42"},
            source="test",
        )
        bridge.on_event(event)

        feelings = broker.get_topic("fizzbuzz.feelings")
        assert feelings.get_total_messages() >= 1

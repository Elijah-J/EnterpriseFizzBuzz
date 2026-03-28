"""Tests for enterprise_fizzbuzz.infrastructure.fizzqueue"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzqueue import (
    FIZZQUEUE_VERSION, MIDDLEWARE_PRIORITY, ExchangeType, DeliveryMode,
    FizzQueueConfig, Message, Exchange, Binding, Queue,
    ExchangeRouter, MessageBroker, FizzQueueDashboard,
    FizzQueueMiddleware, create_fizzqueue_subsystem,
)

@pytest.fixture
def broker():
    b, _, _ = create_fizzqueue_subsystem()
    return b

@pytest.fixture
def subsystem():
    return create_fizzqueue_subsystem()


class TestExchangeRouter:
    def test_direct(self):
        r = ExchangeRouter()
        ex = Exchange(name="ex", exchange_type=ExchangeType.DIRECT)
        bindings = [Binding(exchange="ex", queue="q1", routing_key="key1")]
        assert r.route(ex, "key1", {}, bindings) == ["q1"]
        assert r.route(ex, "key2", {}, bindings) == []

    def test_fanout(self):
        r = ExchangeRouter()
        ex = Exchange(name="ex", exchange_type=ExchangeType.FANOUT)
        bindings = [Binding(exchange="ex", queue="q1"), Binding(exchange="ex", queue="q2")]
        assert len(r.route(ex, "any", {}, bindings)) == 2

    def test_topic_exact(self):
        r = ExchangeRouter()
        ex = Exchange(name="ex", exchange_type=ExchangeType.TOPIC)
        bindings = [Binding(exchange="ex", queue="q1", routing_key="fizz.buzz")]
        assert r.route(ex, "fizz.buzz", {}, bindings) == ["q1"]

    def test_topic_star(self):
        r = ExchangeRouter()
        ex = Exchange(name="ex", exchange_type=ExchangeType.TOPIC)
        bindings = [Binding(exchange="ex", queue="q1", routing_key="fizz.*")]
        assert r.route(ex, "fizz.buzz", {}, bindings) == ["q1"]
        assert r.route(ex, "fizz.buzz.extra", {}, bindings) == []

    def test_topic_hash(self):
        r = ExchangeRouter()
        ex = Exchange(name="ex", exchange_type=ExchangeType.TOPIC)
        bindings = [Binding(exchange="ex", queue="q1", routing_key="fizz.#")]
        assert r.route(ex, "fizz.buzz", {}, bindings) == ["q1"]
        assert r.route(ex, "fizz.buzz.extra", {}, bindings) == ["q1"]
        assert r.route(ex, "fizz", {}, bindings) == ["q1"]

    def test_headers_all(self):
        r = ExchangeRouter()
        ex = Exchange(name="ex", exchange_type=ExchangeType.HEADERS)
        bindings = [Binding(exchange="ex", queue="q1", arguments={"x-match": "all", "type": "fizz"})]
        assert r.route(ex, "", {"type": "fizz"}, bindings) == ["q1"]
        assert r.route(ex, "", {"type": "buzz"}, bindings) == []

    def test_headers_any(self):
        r = ExchangeRouter()
        ex = Exchange(name="ex", exchange_type=ExchangeType.HEADERS)
        bindings = [Binding(exchange="ex", queue="q1", arguments={"x-match": "any", "a": "1", "b": "2"})]
        assert r.route(ex, "", {"a": "1"}, bindings) == ["q1"]


class TestMessageBroker:
    def test_declare_exchange(self, broker):
        ex = broker.declare_exchange("test.ex", ExchangeType.TOPIC)
        assert ex.name == "test.ex"

    def test_declare_exchange_idempotent(self, broker):
        broker.declare_exchange("test.ex")
        ex2 = broker.declare_exchange("test.ex")
        assert ex2.name == "test.ex"

    def test_delete_exchange(self, broker):
        broker.declare_exchange("temp.ex")
        broker.delete_exchange("temp.ex")
        assert broker.get_exchange("temp.ex") is None

    def test_declare_queue(self, broker):
        q = broker.declare_queue("test.q")
        assert q.name == "test.q"

    def test_delete_queue(self, broker):
        broker.declare_queue("temp.q")
        broker.delete_queue("temp.q")
        assert broker.get_queue("temp.q") is None

    def test_bind_and_publish(self, broker):
        broker.declare_exchange("test.ex", ExchangeType.DIRECT)
        broker.declare_queue("test.q")
        broker.bind("test.ex", "test.q", "test.key")
        count = broker.publish("test.ex", "test.key", b"hello")
        assert count == 1
        q = broker.get_queue("test.q")
        assert q.depth == 1

    def test_publish_fanout(self, broker):
        broker.declare_exchange("fan.ex", ExchangeType.FANOUT)
        broker.declare_queue("fan.q1")
        broker.declare_queue("fan.q2")
        broker.bind("fan.ex", "fan.q1")
        broker.bind("fan.ex", "fan.q2")
        count = broker.publish("fan.ex", "", b"broadcast")
        assert count == 2

    def test_default_exchange(self, broker):
        broker.declare_queue("direct.q")
        count = broker.publish("", "direct.q", b"direct")
        assert count == 1

    def test_basic_consume_and_get(self, broker):
        broker.declare_queue("cons.q")
        broker.publish("", "cons.q", b"msg1")
        tag = broker.basic_consume("cons.q")
        msg = broker.basic_get("cons.q", tag)
        assert msg is not None
        assert msg.body == b"msg1"

    def test_basic_ack(self, broker):
        broker.declare_queue("ack.q")
        broker.publish("", "ack.q", b"msg")
        tag = broker.basic_consume("ack.q")
        msg = broker.basic_get("ack.q", tag)
        broker.basic_ack(tag, msg.delivery_tag)
        m = broker.get_metrics()
        assert m.messages_acknowledged >= 1

    def test_basic_reject_requeue(self, broker):
        broker.declare_queue("rej.q")
        broker.publish("", "rej.q", b"msg")
        tag = broker.basic_consume("rej.q")
        msg = broker.basic_get("rej.q", tag)
        broker.basic_reject(tag, msg.delivery_tag, requeue=True)
        q = broker.get_queue("rej.q")
        assert q.depth == 1  # Requeued

    def test_dead_letter(self, broker):
        broker.declare_exchange("test.dlx", ExchangeType.DIRECT)
        broker.declare_queue("test.dlq")
        broker.bind("test.dlx", "test.dlq", "dlq.key")
        broker.declare_queue("limited.q", dead_letter_exchange="test.dlx",
                             dead_letter_routing_key="dlq.key", max_length=1)
        broker.publish("", "limited.q", b"msg1")
        broker.publish("", "limited.q", b"msg2")  # Should DL msg1
        dlq = broker.get_queue("test.dlq")
        assert dlq.depth >= 1

    def test_prefetch_limit(self, broker):
        broker.declare_queue("pf.q")
        for i in range(5):
            broker.publish("", "pf.q", b"msg")
        tag = broker.basic_consume("pf.q", prefetch=2)
        broker.basic_get("pf.q", tag)
        broker.basic_get("pf.q", tag)
        # Third get should be blocked by prefetch
        assert broker.basic_get("pf.q", tag) is None

    def test_basic_cancel(self, broker):
        broker.declare_queue("cancel.q")
        broker.publish("", "cancel.q", b"msg")
        tag = broker.basic_consume("cancel.q")
        broker.basic_get("cancel.q", tag)
        broker.basic_cancel(tag)
        # Unacked messages should be requeued
        q = broker.get_queue("cancel.q")
        assert q.depth == 1

    def test_purge_queue(self, broker):
        broker.declare_queue("purge.q")
        broker.publish("", "purge.q", b"a")
        broker.publish("", "purge.q", b"b")
        count = broker.purge_queue("purge.q")
        assert count == 2
        assert broker.get_queue("purge.q").depth == 0

    def test_unbind(self, broker):
        broker.declare_exchange("ub.ex", ExchangeType.DIRECT)
        broker.declare_queue("ub.q")
        broker.bind("ub.ex", "ub.q", "key")
        assert broker.unbind("ub.ex", "ub.q", "key")

    def test_metrics(self, broker):
        m = broker.get_metrics()
        assert m.messages_published >= 3  # Seeded messages

    def test_uptime(self, broker):
        assert broker.uptime > 0
        assert broker.is_running

    def test_default_queues_exist(self, broker):
        assert broker.get_queue("fizzbuzz.evaluations") is not None
        assert broker.get_queue("fizzbuzz.audit") is not None

    def test_seeded_messages(self, broker):
        q = broker.get_queue("fizzbuzz.evaluations")
        assert q.depth >= 3


class TestFizzQueueMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzqueue"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock(); ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzqueue_version"] == FIZZQUEUE_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzQueue" in mw.render_dashboard()

    def test_render_exchanges(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_exchanges()
        assert "fizzbuzz.events" in output

    def test_render_queues(self, subsystem):
        _, _, mw = subsystem
        assert "fizzbuzz.evaluations" in mw.render_queues()


class TestCreateSubsystem:
    def test_returns_tuple(self):
        assert len(create_fizzqueue_subsystem()) == 3

    def test_default_exchanges(self):
        b, _, _ = create_fizzqueue_subsystem()
        names = [e.name for e in b.list_exchanges()]
        assert "amq.direct" in names
        assert "amq.fanout" in names
        assert "fizzbuzz.events" in names


class TestConstants:
    def test_version(self):
        assert FIZZQUEUE_VERSION == "1.0.0"
    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 134

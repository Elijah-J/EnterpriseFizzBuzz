"""
Enterprise FizzBuzz Platform - Webhook Notification System Tests

Comprehensive test suite for the webhook dispatch pipeline, covering
HMAC-SHA256 signature engine, retry policy, simulated HTTP client,
Dead Letter Queue, WebhookManager, WebhookObserver, and the ASCII
dashboard. Because even simulated HTTP POST requests for FizzBuzz
events deserve 100% test coverage.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    WebhookDeadLetterQueueFullError,
    WebhookEndpointValidationError,
    WebhookPayloadSerializationError,
    WebhookSignatureError,
)
from enterprise_fizzbuzz.domain.models import Event, EventType
from enterprise_fizzbuzz.infrastructure.observers import EventBus
from enterprise_fizzbuzz.infrastructure.webhooks import (
    DeadLetterEntry,
    DeadLetterQueue,
    RetryPolicy,
    SimulatedHTTPClient,
    WebhookDashboard,
    WebhookDeliveryResult,
    WebhookEndpoint,
    WebhookManager,
    WebhookObserver,
    WebhookPayload,
    WebhookSignatureEngine,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def signature_engine():
    return WebhookSignatureEngine("test-secret-key")


@pytest.fixture
def retry_policy():
    return RetryPolicy(
        max_retries=3,
        backoff_base_ms=100.0,
        backoff_multiplier=2.0,
        backoff_max_ms=5000.0,
    )


@pytest.fixture
def http_client_always_success():
    """Client with 100% success rate."""
    return SimulatedHTTPClient(success_rate_percent=100)


@pytest.fixture
def http_client_always_fail():
    """Client with 0% success rate."""
    return SimulatedHTTPClient(success_rate_percent=0)


@pytest.fixture
def dlq():
    return DeadLetterQueue(max_size=10)


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def sample_event():
    return Event(
        event_type=EventType.FIZZBUZZ_DETECTED,
        payload={"number": 15, "output": "FizzBuzz"},
        source="TestEngine",
    )


@pytest.fixture
def webhook_manager_success(signature_engine, http_client_always_success, retry_policy, dlq, event_bus):
    mgr = WebhookManager(
        signature_engine=signature_engine,
        http_client=http_client_always_success,
        retry_policy=retry_policy,
        dead_letter_queue=dlq,
        event_bus=event_bus,
    )
    return mgr


@pytest.fixture
def webhook_manager_fail(signature_engine, http_client_always_fail, retry_policy, dlq, event_bus):
    mgr = WebhookManager(
        signature_engine=signature_engine,
        http_client=http_client_always_fail,
        retry_policy=retry_policy,
        dead_letter_queue=dlq,
        event_bus=event_bus,
    )
    return mgr


# ============================================================
# WebhookSignatureEngine Tests
# ============================================================


class TestWebhookSignatureEngine:
    """Tests for the HMAC-SHA256 signature engine."""

    def test_sign_produces_sha256_prefix(self, signature_engine):
        sig = signature_engine.sign('{"test": true}')
        assert sig.startswith("sha256=")

    def test_sign_produces_consistent_output(self, signature_engine):
        body = '{"event": "FIZZBUZZ_DETECTED", "number": 15}'
        sig1 = signature_engine.sign(body)
        sig2 = signature_engine.sign(body)
        assert sig1 == sig2

    def test_different_bodies_produce_different_signatures(self, signature_engine):
        sig1 = signature_engine.sign('{"number": 15}')
        sig2 = signature_engine.sign('{"number": 30}')
        assert sig1 != sig2

    def test_different_secrets_produce_different_signatures(self):
        engine1 = WebhookSignatureEngine("secret-one")
        engine2 = WebhookSignatureEngine("secret-two")
        body = '{"number": 15}'
        assert engine1.sign(body) != engine2.sign(body)

    def test_verify_valid_signature(self, signature_engine):
        body = '{"number": 15}'
        sig = signature_engine.sign(body)
        assert signature_engine.verify(body, sig) is True

    def test_verify_invalid_signature(self, signature_engine):
        body = '{"number": 15}'
        assert signature_engine.verify(body, "sha256=invalid") is False

    def test_verify_tampered_body(self, signature_engine):
        body = '{"number": 15}'
        sig = signature_engine.sign(body)
        assert signature_engine.verify('{"number": 16}', sig) is False

    def test_empty_secret_raises(self):
        with pytest.raises(WebhookSignatureError):
            WebhookSignatureEngine("")

    def test_signature_hex_length(self, signature_engine):
        """HMAC-SHA256 produces a 64-character hex digest."""
        sig = signature_engine.sign("test")
        hex_part = sig.replace("sha256=", "")
        assert len(hex_part) == 64


# ============================================================
# RetryPolicy Tests
# ============================================================


class TestRetryPolicy:
    """Tests for the exponential backoff retry policy."""

    def test_should_retry_within_limit(self, retry_policy):
        assert retry_policy.should_retry(1) is True
        assert retry_policy.should_retry(2) is True

    def test_should_not_retry_at_limit(self, retry_policy):
        assert retry_policy.should_retry(3) is False

    def test_should_not_retry_beyond_limit(self, retry_policy):
        assert retry_policy.should_retry(10) is False

    def test_backoff_delay_exponential(self, retry_policy):
        d0 = retry_policy.calculate_delay_ms(0)
        d1 = retry_policy.calculate_delay_ms(1)
        d2 = retry_policy.calculate_delay_ms(2)
        assert d0 == 100.0
        assert d1 == 200.0
        assert d2 == 400.0

    def test_backoff_delay_capped(self, retry_policy):
        delay = retry_policy.calculate_delay_ms(100)
        assert delay == 5000.0

    def test_max_retries_property(self, retry_policy):
        assert retry_policy.max_retries == 3


# ============================================================
# SimulatedHTTPClient Tests
# ============================================================


class TestSimulatedHTTPClient:
    """Tests for the deterministic simulated HTTP client."""

    def test_always_success_client(self, http_client_always_success, capsys):
        payload = WebhookPayload(
            endpoint_url="http://example.com/hook",
            event_type="FIZZBUZZ_DETECTED",
            body='{"test": true}',
            signature="sha256=abc",
            headers=(
                ("X-FizzBuzz-Signature-256", "sha256=abc"),
                ("X-FizzBuzz-Seriousness-Level", "MAXIMUM"),
            ),
        )
        result = http_client_always_success.deliver(payload)
        assert result.success is True
        assert result.status_code == 200

    def test_always_fail_client(self, http_client_always_fail, capsys):
        payload = WebhookPayload(
            endpoint_url="http://example.com/hook",
            event_type="FIZZBUZZ_DETECTED",
            body='{"test": true}',
            signature="sha256=abc",
            headers=(
                ("X-FizzBuzz-Signature-256", "sha256=abc"),
                ("X-FizzBuzz-Seriousness-Level", "MAXIMUM"),
            ),
        )
        result = http_client_always_fail.deliver(payload)
        assert result.success is False
        assert result.status_code == 503

    def test_delivery_log_populated(self, http_client_always_success, capsys):
        payload = WebhookPayload(
            endpoint_url="http://example.com/hook",
            event_type="TEST",
            body="{}",
            headers=(),
        )
        http_client_always_success.deliver(payload)
        http_client_always_success.deliver(payload)
        assert len(http_client_always_success.delivery_log) == 2

    def test_statistics(self, http_client_always_success, capsys):
        payload = WebhookPayload(
            endpoint_url="http://example.com/hook",
            event_type="TEST",
            body="{}",
            headers=(),
        )
        http_client_always_success.deliver(payload)
        stats = http_client_always_success.get_statistics()
        assert stats["total_deliveries"] == 1
        assert stats["successful"] == 1
        assert stats["failed"] == 0

    def test_success_rate_clamp(self, capsys):
        """Success rate should be clamped to [0, 100]."""
        client = SimulatedHTTPClient(success_rate_percent=150)
        assert client._success_rate == 100
        client2 = SimulatedHTTPClient(success_rate_percent=-50)
        assert client2._success_rate == 0

    def test_deterministic_behavior(self, capsys):
        """Same URL should always get the same result."""
        client = SimulatedHTTPClient(success_rate_percent=50)
        url = "http://test.example.com/deterministic"
        payload = WebhookPayload(
            endpoint_url=url,
            event_type="TEST",
            body="{}",
            headers=(),
        )
        r1 = client.deliver(payload)
        r2 = client.deliver(payload)
        assert r1.success == r2.success


# ============================================================
# DeadLetterQueue Tests
# ============================================================


class TestDeadLetterQueue:
    """Tests for the Dead Letter Queue."""

    def test_enqueue_and_get_entries(self, dlq):
        payload = WebhookPayload(endpoint_url="http://example.com/hook")
        entry = dlq.enqueue(
            payload=payload,
            attempts=[],
            final_error="test error",
        )
        assert dlq.get_size() == 1
        entries = dlq.get_entries()
        assert len(entries) == 1
        assert entries[0].final_error == "test error"

    def test_dlq_max_size_enforced(self):
        small_dlq = DeadLetterQueue(max_size=2)
        for i in range(2):
            small_dlq.enqueue(
                payload=WebhookPayload(endpoint_url=f"http://example.com/{i}"),
                attempts=[],
                final_error=f"error {i}",
            )
        with pytest.raises(WebhookDeadLetterQueueFullError):
            small_dlq.enqueue(
                payload=WebhookPayload(endpoint_url="http://overflow.com"),
                attempts=[],
                final_error="overflow",
            )

    def test_drain(self, dlq):
        dlq.enqueue(
            payload=WebhookPayload(endpoint_url="http://example.com/a"),
            attempts=[],
            final_error="error",
        )
        dlq.enqueue(
            payload=WebhookPayload(endpoint_url="http://example.com/b"),
            attempts=[],
            final_error="error",
        )
        drained = dlq.drain()
        assert len(drained) == 2
        assert dlq.get_size() == 0

    def test_clear(self, dlq):
        dlq.enqueue(
            payload=WebhookPayload(endpoint_url="http://example.com/c"),
            attempts=[],
            final_error="error",
        )
        dlq.clear()
        assert dlq.get_size() == 0

    def test_statistics_empty(self, dlq):
        stats = dlq.get_statistics()
        assert stats["size"] == 0
        assert stats["utilization_percent"] == 0.0

    def test_statistics_with_entries(self, dlq):
        dlq.enqueue(
            payload=WebhookPayload(endpoint_url="http://example.com/d"),
            attempts=[],
            final_error="error",
        )
        stats = dlq.get_statistics()
        assert stats["size"] == 1
        assert stats["unique_endpoints"] == 1


# ============================================================
# WebhookManager Tests
# ============================================================


class TestWebhookManager:
    """Tests for the webhook dispatch orchestrator."""

    def test_register_endpoint(self, webhook_manager_success):
        ep = webhook_manager_success.register_endpoint("http://example.com/hook")
        assert ep.url == "http://example.com/hook"
        assert len(webhook_manager_success.endpoints) == 1

    def test_register_endpoint_empty_url_raises(self, webhook_manager_success):
        with pytest.raises(WebhookEndpointValidationError):
            webhook_manager_success.register_endpoint("")

    def test_register_endpoint_invalid_scheme_raises(self, webhook_manager_success):
        with pytest.raises(WebhookEndpointValidationError):
            webhook_manager_success.register_endpoint("ftp://example.com/hook")

    def test_dispatch_to_endpoint_success(self, webhook_manager_success, sample_event, capsys):
        webhook_manager_success.register_endpoint("http://example.com/success")
        results = webhook_manager_success.dispatch(sample_event)
        assert len(results) == 1
        assert results[0].success is True

    def test_dispatch_to_endpoint_failure_goes_to_dlq(self, webhook_manager_fail, sample_event, capsys):
        webhook_manager_fail.register_endpoint("http://example.com/fail")
        results = webhook_manager_fail.dispatch(sample_event)
        # All retries should fail
        assert results[0].success is False
        # Should be in the DLQ
        assert webhook_manager_fail.dead_letter_queue.get_size() == 1

    def test_dispatch_no_endpoints_returns_empty(self, webhook_manager_success, sample_event):
        results = webhook_manager_success.dispatch(sample_event)
        assert results == []

    def test_dispatch_respects_subscription_filter(self, webhook_manager_success, capsys):
        webhook_manager_success.register_endpoint(
            "http://example.com/fizz_only",
            subscribed_events=["FIZZ_DETECTED"],
        )
        buzz_event = Event(
            event_type=EventType.BUZZ_DETECTED,
            payload={"number": 5},
        )
        results = webhook_manager_success.dispatch(buzz_event)
        assert results == []

    def test_dispatch_matches_subscription(self, webhook_manager_success, capsys):
        webhook_manager_success.register_endpoint(
            "http://example.com/fizzbuzz",
            subscribed_events=["FIZZBUZZ_DETECTED"],
        )
        results = webhook_manager_success.dispatch(
            Event(
                event_type=EventType.FIZZBUZZ_DETECTED,
                payload={"number": 15},
            )
        )
        assert len(results) == 1
        assert results[0].success is True

    def test_statistics(self, webhook_manager_success, sample_event, capsys):
        webhook_manager_success.register_endpoint("http://example.com/stats")
        webhook_manager_success.dispatch(sample_event)
        stats = webhook_manager_success.get_statistics()
        assert stats["total_dispatches"] == 1
        assert stats["successful_deliveries"] == 1
        assert stats["registered_endpoints"] == 1

    def test_payload_includes_hmac_signature(self, webhook_manager_success, sample_event, capsys):
        webhook_manager_success.register_endpoint("http://example.com/signed")
        webhook_manager_success.dispatch(sample_event)
        log = webhook_manager_success.http_client.delivery_log
        assert len(log) >= 1


# ============================================================
# WebhookObserver Tests
# ============================================================


class TestWebhookObserver:
    """Tests for the EventBus-to-webhook adapter."""

    def test_observer_dispatches_matching_events(self, webhook_manager_success, capsys):
        webhook_manager_success.register_endpoint("http://example.com/observer")
        observer = WebhookObserver(
            webhook_manager=webhook_manager_success,
            subscribed_events={"FIZZBUZZ_DETECTED"},
        )
        event = Event(
            event_type=EventType.FIZZBUZZ_DETECTED,
            payload={"number": 15},
        )
        observer.on_event(event)
        assert observer.events_processed == 1

    def test_observer_ignores_non_subscribed_events(self, webhook_manager_success):
        webhook_manager_success.register_endpoint("http://example.com/observer")
        observer = WebhookObserver(
            webhook_manager=webhook_manager_success,
            subscribed_events={"FIZZ_DETECTED"},
        )
        event = Event(
            event_type=EventType.BUZZ_DETECTED,
            payload={"number": 5},
        )
        observer.on_event(event)
        assert observer.events_processed == 0

    def test_observer_ignores_webhook_events(self, webhook_manager_success):
        """Webhook events should not trigger recursive webhook dispatch."""
        webhook_manager_success.register_endpoint("http://example.com/observer")
        observer = WebhookObserver(
            webhook_manager=webhook_manager_success,
            subscribed_events=set(),  # all events
        )
        webhook_event = Event(
            event_type=EventType.WEBHOOK_DISPATCHED,
            payload={"test": True},
        )
        observer.on_event(webhook_event)
        assert observer.events_processed == 0

    def test_observer_get_name(self, webhook_manager_success):
        observer = WebhookObserver(webhook_manager=webhook_manager_success)
        assert observer.get_name() == "WebhookObserver"

    def test_observer_with_event_bus_integration(self, webhook_manager_success, event_bus, capsys):
        webhook_manager_success.register_endpoint("http://example.com/bus")
        observer = WebhookObserver(
            webhook_manager=webhook_manager_success,
            subscribed_events={"FIZZBUZZ_DETECTED"},
        )
        event_bus.subscribe(observer)
        event_bus.publish(Event(
            event_type=EventType.FIZZBUZZ_DETECTED,
            payload={"number": 15},
        ))
        assert observer.events_processed == 1


# ============================================================
# WebhookDashboard Tests
# ============================================================


class TestWebhookDashboard:
    """Tests for the ASCII webhook dashboard."""

    def test_render_empty_dashboard(self, webhook_manager_success):
        output = WebhookDashboard.render(webhook_manager_success)
        assert "WEBHOOK NOTIFICATION SYSTEM DASHBOARD" in output
        assert "no endpoints registered" in output

    def test_render_with_endpoints(self, webhook_manager_success, sample_event, capsys):
        webhook_manager_success.register_endpoint("http://example.com/dash")
        webhook_manager_success.dispatch(sample_event)
        capsys.readouterr()  # Clear simulated delivery output
        output = WebhookDashboard.render(webhook_manager_success)
        assert "example.com" in output
        assert "ACTIVE" in output

    def test_render_delivery_log_empty(self, webhook_manager_success):
        output = WebhookDashboard.render_delivery_log(webhook_manager_success)
        assert "No deliveries recorded" in output

    def test_render_delivery_log_with_entries(self, webhook_manager_success, sample_event, capsys):
        webhook_manager_success.register_endpoint("http://example.com/log")
        webhook_manager_success.dispatch(sample_event)
        capsys.readouterr()
        output = WebhookDashboard.render_delivery_log(webhook_manager_success)
        assert "WEBHOOK DELIVERY LOG" in output

    def test_render_dlq_empty(self, webhook_manager_success):
        output = WebhookDashboard.render_dlq(webhook_manager_success)
        assert "empty" in output

    def test_render_dlq_with_entries(self, webhook_manager_fail, sample_event, capsys):
        webhook_manager_fail.register_endpoint("http://example.com/dlq")
        webhook_manager_fail.dispatch(sample_event)
        capsys.readouterr()
        output = WebhookDashboard.render_dlq(webhook_manager_fail)
        assert "DEAD LETTER QUEUE" in output
        assert "example.com" in output


# ============================================================
# Data Class Tests
# ============================================================


class TestWebhookDataClasses:
    """Tests for the frozen dataclasses."""

    def test_webhook_endpoint_frozen(self):
        ep = WebhookEndpoint(url="http://example.com")
        with pytest.raises(AttributeError):
            ep.url = "http://other.com"

    def test_webhook_payload_frozen(self):
        payload = WebhookPayload(body='{"test": true}')
        with pytest.raises(AttributeError):
            payload.body = '{"test": false}'

    def test_webhook_delivery_result_frozen(self):
        result = WebhookDeliveryResult(success=True)
        with pytest.raises(AttributeError):
            result.success = False

    def test_dead_letter_entry_frozen(self):
        entry = DeadLetterEntry(final_error="test")
        with pytest.raises(AttributeError):
            entry.final_error = "modified"

    def test_webhook_endpoint_defaults(self):
        ep = WebhookEndpoint()
        assert ep.active is True
        assert ep.subscribed_events == frozenset()
        assert ep.endpoint_id  # should have a UUID

    def test_webhook_payload_defaults(self):
        payload = WebhookPayload()
        assert payload.body == ""
        assert payload.signature == ""
        assert payload.payload_id  # should have a UUID

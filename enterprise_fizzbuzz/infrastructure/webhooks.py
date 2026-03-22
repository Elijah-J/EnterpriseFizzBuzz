"""
Enterprise FizzBuzz Platform - Webhook Notification System

Implements a production-grade webhook dispatch system for notifying
external services about FizzBuzz evaluation events. Because when
someone computes 15 % 3 and gets "FizzBuzz", every downstream
microservice in the constellation must be immediately informed via
a cryptographically signed HTTP POST request.

The deliveries are, of course, entirely simulated. No actual HTTP
requests leave this process. But the HMAC-SHA256 signatures are real,
the exponential backoff delays are calculated (if not actually waited
for), and the Dead Letter Queue faithfully stores every permanently
failed delivery for future regret and post-incident review.

Design Patterns Employed:
    - Observer (GoF) — WebhookObserver bridges EventBus to webhook dispatch
    - Strategy (GoF) — RetryPolicy encapsulates backoff strategy
    - Chain of Responsibility — delivery pipeline with retry escalation
    - Dead Letter Queue (enterprise messaging)
    - HMAC-SHA256 Message Authentication (RFC 2104)
    - Simulated HTTP Client (because real HTTP is for deployed services)

Compliance:
    - RFC 2104: HMAC message authentication
    - RFC 7231: HTTP POST semantics (aspirationally)
    - ISO 27001: Information security through payload signing
    - SOC 2 Type II: Audit trail via delivery logging
    - X-FizzBuzz-Seriousness-Level: MAXIMUM (mandatory header)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    WebhookDeadLetterQueueFullError,
    WebhookDeliveryError,
    WebhookEndpointValidationError,
    WebhookPayloadSerializationError,
    WebhookRetryExhaustedError,
    WebhookSignatureError,
)
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IObserver
from enterprise_fizzbuzz.domain.models import Event, EventType

logger = logging.getLogger(__name__)


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class WebhookEndpoint:
    """An immutable webhook endpoint registration.

    Represents a URL that has volunteered (or been volunteered) to
    receive POST requests about FizzBuzz evaluation events. Each
    endpoint has a unique ID for tracking purposes, because even
    URLs deserve identity and individuality in an enterprise system.

    Attributes:
        endpoint_id: Unique identifier for this endpoint registration.
        url: The destination URL for webhook delivery (simulated).
        active: Whether this endpoint is currently accepting deliveries.
        subscribed_events: Event types this endpoint cares about.
            An empty set means "all events," because some endpoints
            are gluttons for FizzBuzz telemetry.
        created_at: When this endpoint was registered (UTC).
    """

    endpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: str = ""
    active: bool = True
    subscribed_events: frozenset[str] = field(default_factory=frozenset)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class WebhookPayload:
    """An immutable webhook payload ready for delivery.

    Contains the serialized event data, HMAC-SHA256 signature, and
    all the headers that a discerning webhook consumer would expect.
    Frozen because payloads, once constructed, are historical facts
    that must not be tampered with — especially not after signing.

    Attributes:
        payload_id: Unique identifier for this payload instance.
        endpoint_url: Where this payload is destined (simulated).
        event_type: The type of event that triggered this webhook.
        body: The JSON-serialized event data.
        signature: HMAC-SHA256 signature of the body.
        headers: HTTP headers to include with the delivery.
        timestamp: When this payload was constructed (UTC).
    """

    payload_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    endpoint_url: str = ""
    event_type: str = ""
    body: str = ""
    signature: str = ""
    headers: tuple[tuple[str, str], ...] = ()
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """The outcome of a single webhook delivery attempt.

    Records whether the simulated HTTP POST succeeded, the status
    code (also simulated), and timing data. Frozen because delivery
    results are immutable records in the grand audit trail of
    enterprise webhook operations.

    Attributes:
        payload_id: The payload that was delivered (or attempted).
        endpoint_url: The destination URL.
        success: Whether the delivery was accepted.
        status_code: Simulated HTTP status code.
        attempt_number: Which retry attempt this was (1-based).
        duration_ms: Simulated response time in milliseconds.
        error_message: Error details if delivery failed.
        timestamp: When this attempt occurred (UTC).
    """

    payload_id: str = ""
    endpoint_url: str = ""
    success: bool = False
    status_code: int = 0
    attempt_number: int = 1
    duration_ms: float = 0.0
    error_message: str = ""
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class DeadLetterEntry:
    """A permanently failed webhook delivery preserved in the Dead Letter Queue.

    When a webhook payload has exhausted all retry attempts and still
    cannot be delivered, it is interred in the Dead Letter Queue —
    the final resting place for undeliverable FizzBuzz notifications.
    Each entry preserves the full payload, all delivery attempts,
    and the original error, so that future archaeologists of the
    webhook subsystem can piece together what went wrong.

    Attributes:
        entry_id: Unique identifier for this DLQ entry.
        payload: The webhook payload that could not be delivered.
        attempts: All delivery results from every retry attempt.
        final_error: The error message from the last attempt.
        dead_lettered_at: When this entry was consigned to the DLQ (UTC).
        reason: Why the payload was dead-lettered.
    """

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    payload: WebhookPayload = field(default_factory=WebhookPayload)
    attempts: tuple[WebhookDeliveryResult, ...] = ()
    final_error: str = ""
    dead_lettered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    reason: str = "max_retries_exhausted"


# ============================================================
# Webhook Signature Engine
# ============================================================


class WebhookSignatureEngine:
    """HMAC-SHA256 signature engine for webhook payload authentication.

    Implements RFC 2104 HMAC message authentication to ensure that
    webhook payloads have not been tampered with in transit. In a
    real system, the receiving endpoint would verify this signature
    against a shared secret. In our system, the receiving endpoint
    is a hash function that doesn't care about signatures, but we
    compute them anyway because cryptographic hygiene is non-negotiable.

    The signature is computed over the raw JSON body using the
    configured secret key, producing a hex-encoded HMAC-SHA256 digest
    that is included in the X-FizzBuzz-Signature-256 header.
    """

    def __init__(self, secret: str) -> None:
        if not secret:
            raise WebhookSignatureError("Secret key cannot be empty")
        self._secret = secret.encode("utf-8")

    def sign(self, payload_body: str) -> str:
        """Generate an HMAC-SHA256 signature for the given payload body.

        Args:
            payload_body: The raw JSON string to sign.

        Returns:
            Hex-encoded HMAC-SHA256 digest prefixed with 'sha256='.
        """
        try:
            digest = hmac.new(
                self._secret,
                payload_body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            return f"sha256={digest}"
        except Exception as e:
            raise WebhookSignatureError(f"Signature generation failed: {e}") from e

    def verify(self, payload_body: str, signature: str) -> bool:
        """Verify an HMAC-SHA256 signature against the payload body.

        Args:
            payload_body: The raw JSON string to verify.
            signature: The signature to verify (prefixed with 'sha256=').

        Returns:
            True if the signature is valid, False otherwise.
        """
        expected = self.sign(payload_body)
        return hmac.compare_digest(expected, signature)


# ============================================================
# Retry Policy
# ============================================================


class RetryPolicy:
    """Exponential backoff retry policy for webhook delivery.

    Calculates progressively increasing delays between retry attempts,
    giving the simulated endpoint more time to recover from its
    deterministic failure pattern. The delays are logged but never
    actually awaited, because sleeping in a FizzBuzz CLI would be
    an unconscionable waste of the user's time.

    The formula: delay = min(base_ms * (multiplier ^ attempt), max_ms)
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base_ms: float = 1000.0,
        backoff_multiplier: float = 2.0,
        backoff_max_ms: float = 30000.0,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base_ms = backoff_base_ms
        self._backoff_multiplier = backoff_multiplier
        self._backoff_max_ms = backoff_max_ms

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def calculate_delay_ms(self, attempt: int) -> float:
        """Calculate the backoff delay for the given attempt number.

        Args:
            attempt: Zero-based attempt counter (0 = first retry).

        Returns:
            Delay in milliseconds, capped at backoff_max_ms.
        """
        delay = self._backoff_base_ms * (self._backoff_multiplier ** attempt)
        return min(delay, self._backoff_max_ms)

    def should_retry(self, attempt: int) -> bool:
        """Determine if another retry attempt should be made.

        Args:
            attempt: The current attempt number (1-based).

        Returns:
            True if the attempt is within the retry limit.
        """
        return attempt < self._max_retries


# ============================================================
# Simulated HTTP Client
# ============================================================


class SimulatedHTTPClient:
    """Deterministic simulated HTTP client for webhook delivery.

    Instead of making real HTTP requests (which would be absurd for
    a CLI FizzBuzz platform), this client determines success or failure
    based on the hash of the destination URL. This ensures that the
    same URL always produces the same result within a session, making
    the webhook system's behavior fully deterministic and testable.

    The success criterion is: hash(url) % 100 < success_rate_percent.
    URLs whose hash modulo 100 falls below the threshold succeed;
    all others fail with a simulated 503 Service Unavailable. Because
    in the enterprise FizzBuzz universe, even simulated HTTP responses
    have proper status codes.

    Every delivery — successful or not — is logged with a beautifully
    formatted block showing the simulated request and response details.
    """

    def __init__(self, success_rate_percent: int = 80) -> None:
        self._success_rate = max(0, min(100, success_rate_percent))
        self._delivery_log: list[WebhookDeliveryResult] = []
        self._lock = threading.Lock()

    @property
    def delivery_log(self) -> list[WebhookDeliveryResult]:
        """Return a copy of the delivery log."""
        with self._lock:
            return list(self._delivery_log)

    def _will_succeed(self, url: str) -> bool:
        """Determine if a delivery to this URL will succeed.

        Uses hash(url) % 100 for deterministic success/failure.
        """
        url_hash = hash(url)
        return (url_hash % 100) < self._success_rate

    def deliver(
        self,
        payload: WebhookPayload,
        attempt_number: int = 1,
    ) -> WebhookDeliveryResult:
        """Simulate delivering a webhook payload via HTTP POST.

        Logs a formatted block showing the simulated request and response,
        then returns a WebhookDeliveryResult indicating success or failure.

        Args:
            payload: The webhook payload to deliver.
            attempt_number: Which attempt this is (for logging).

        Returns:
            A WebhookDeliveryResult recording the outcome.
        """
        url = payload.endpoint_url
        success = self._will_succeed(url)
        status_code = 200 if success else 503
        error_msg = "" if success else "Simulated 503 Service Unavailable"
        simulated_duration = 42.0 if success else 1337.0

        result = WebhookDeliveryResult(
            payload_id=payload.payload_id,
            endpoint_url=url,
            success=success,
            status_code=status_code,
            attempt_number=attempt_number,
            duration_ms=simulated_duration,
            error_message=error_msg,
        )

        with self._lock:
            self._delivery_log.append(result)

        # Log the simulated delivery with enterprise-grade formatting
        status_text = "200 OK" if success else "503 Service Unavailable"
        outcome = "DELIVERED" if success else "FAILED"
        headers_dict = dict(payload.headers)

        log_lines = [
            "",
            "  +--- SIMULATED WEBHOOK DELIVERY ----------------------------+",
            f"  |  Outcome      : {outcome:<42}|",
            f"  |  Endpoint     : {url[:42]:<42}|",
            f"  |  Event        : {payload.event_type:<42}|",
            f"  |  Attempt      : {attempt_number:<42}|",
            f"  |  Status Code  : {status_text:<42}|",
            f"  |  Duration     : {simulated_duration:<38.1f} ms |",
            f"  |  Payload ID   : {payload.payload_id[:42]:<42}|",
            f"  |  Signature    : {headers_dict.get('X-FizzBuzz-Signature-256', 'N/A')[:42]:<42}|",
            f"  |  Seriousness  : {headers_dict.get('X-FizzBuzz-Seriousness-Level', 'MAXIMUM'):<42}|",
            "  +------------------------------------------------------------+",
            "",
        ]
        log_block = "\n".join(log_lines)
        if success:
            logger.info("Webhook delivered to %s: %s", url, status_text)
        else:
            logger.warning("Webhook delivery failed to %s: %s", url, status_text)

        print(log_block)

        return result

    def get_statistics(self) -> dict[str, Any]:
        """Return delivery statistics."""
        with self._lock:
            total = len(self._delivery_log)
            successes = sum(1 for r in self._delivery_log if r.success)
            failures = total - successes
            return {
                "total_deliveries": total,
                "successful": successes,
                "failed": failures,
                "success_rate": (successes / total * 100) if total > 0 else 0.0,
            }


# ============================================================
# Dead Letter Queue
# ============================================================


class DeadLetterQueue:
    """In-memory queue for permanently failed webhook deliveries.

    When a webhook payload has exhausted all retry attempts and still
    cannot be delivered, it is committed to the Dead Letter Queue —
    a solemn repository of unreachable endpoints and undelivered
    notifications. The DLQ preserves the full payload, all delivery
    attempts, and the final error for post-mortem analysis.

    In a real enterprise system, the DLQ would trigger alerts, feed
    monitoring dashboards, and generate incident tickets. Here, it
    generates ASCII art and existential questions about why we
    simulated webhook failures for a FizzBuzz platform.
    """

    def __init__(self, max_size: int = 100) -> None:
        self._max_size = max_size
        self._entries: list[DeadLetterEntry] = []
        self._lock = threading.Lock()

    @property
    def max_size(self) -> int:
        return self._max_size

    def enqueue(
        self,
        payload: WebhookPayload,
        attempts: list[WebhookDeliveryResult],
        final_error: str,
        reason: str = "max_retries_exhausted",
    ) -> DeadLetterEntry:
        """Add a permanently failed delivery to the Dead Letter Queue.

        Args:
            payload: The webhook payload that could not be delivered.
            attempts: All delivery attempt results.
            final_error: The error from the last attempt.
            reason: Why the delivery was dead-lettered.

        Returns:
            The DeadLetterEntry that was created.

        Raises:
            WebhookDeadLetterQueueFullError: If the DLQ is at capacity.
        """
        with self._lock:
            if len(self._entries) >= self._max_size:
                raise WebhookDeadLetterQueueFullError(self._max_size)

            entry = DeadLetterEntry(
                payload=payload,
                attempts=tuple(attempts),
                final_error=final_error,
                reason=reason,
            )
            self._entries.append(entry)

            logger.warning(
                "Webhook payload %s dead-lettered: %s (DLQ size: %d/%d)",
                payload.payload_id,
                reason,
                len(self._entries),
                self._max_size,
            )

            return entry

    def get_entries(self) -> list[DeadLetterEntry]:
        """Return a copy of all DLQ entries."""
        with self._lock:
            return list(self._entries)

    def get_size(self) -> int:
        """Return the current number of entries in the DLQ."""
        with self._lock:
            return len(self._entries)

    def drain(self) -> list[DeadLetterEntry]:
        """Remove and return all entries from the DLQ.

        Returns:
            All entries that were in the DLQ.
        """
        with self._lock:
            entries = list(self._entries)
            self._entries.clear()
            logger.info("Dead Letter Queue drained: %d entries removed", len(entries))
            return entries

    def clear(self) -> None:
        """Clear all entries from the DLQ without returning them."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            logger.info("Dead Letter Queue cleared: %d entries discarded", count)

    def get_statistics(self) -> dict[str, Any]:
        """Return DLQ statistics for dashboard rendering."""
        with self._lock:
            entries = list(self._entries)

        if not entries:
            return {
                "size": 0,
                "max_size": self._max_size,
                "utilization_percent": 0.0,
                "unique_endpoints": 0,
                "oldest_entry_age_seconds": 0.0,
            }

        unique_endpoints = len(set(e.payload.endpoint_url for e in entries))
        oldest = min(e.dead_lettered_at for e in entries)
        age = (datetime.now(timezone.utc) - oldest).total_seconds()

        return {
            "size": len(entries),
            "max_size": self._max_size,
            "utilization_percent": (len(entries) / self._max_size * 100),
            "unique_endpoints": unique_endpoints,
            "oldest_entry_age_seconds": age,
        }


# ============================================================
# Webhook Manager
# ============================================================


class WebhookManager:
    """Orchestrates webhook dispatch, retry, and Dead Letter Queue routing.

    The WebhookManager is the central coordinator of the webhook
    notification system. It receives events, constructs signed payloads,
    dispatches them via the simulated HTTP client, handles retries with
    exponential backoff (logged, not awaited), and routes permanently
    failed deliveries to the Dead Letter Queue.

    Think of it as the FizzBuzz postal service: it picks up the mail
    (events), stamps it (HMAC signature), attempts delivery (simulated
    POST), and when all else fails, sends it to the dead letter office
    (DLQ). The mail never actually leaves the building, but the tracking
    system is impeccable.
    """

    def __init__(
        self,
        signature_engine: WebhookSignatureEngine,
        http_client: SimulatedHTTPClient,
        retry_policy: RetryPolicy,
        dead_letter_queue: DeadLetterQueue,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._signature_engine = signature_engine
        self._http_client = http_client
        self._retry_policy = retry_policy
        self._dlq = dead_letter_queue
        self._event_bus = event_bus
        self._endpoints: list[WebhookEndpoint] = []
        self._dispatch_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._lock = threading.Lock()

        logger.info(
            "WebhookManager initialized: retry_max=%d, "
            "simulated_client_success_rate=%d%%",
            retry_policy.max_retries,
            http_client._success_rate,
        )

    @property
    def endpoints(self) -> list[WebhookEndpoint]:
        """Return registered endpoints."""
        with self._lock:
            return list(self._endpoints)

    @property
    def dead_letter_queue(self) -> DeadLetterQueue:
        return self._dlq

    @property
    def http_client(self) -> SimulatedHTTPClient:
        return self._http_client

    def register_endpoint(
        self,
        url: str,
        subscribed_events: Optional[list[str]] = None,
    ) -> WebhookEndpoint:
        """Register a new webhook endpoint.

        Args:
            url: The URL to receive webhook deliveries.
            subscribed_events: Event types this endpoint wants. None = all.

        Returns:
            The registered WebhookEndpoint.

        Raises:
            WebhookEndpointValidationError: If the URL is invalid.
        """
        if not url:
            raise WebhookEndpointValidationError(url, "URL cannot be empty")
        if not url.startswith(("http://", "https://")):
            raise WebhookEndpointValidationError(
                url, "URL must start with http:// or https://"
            )

        endpoint = WebhookEndpoint(
            url=url,
            subscribed_events=frozenset(subscribed_events) if subscribed_events else frozenset(),
        )

        with self._lock:
            self._endpoints.append(endpoint)

        logger.info(
            "Webhook endpoint registered: %s (subscriptions: %s)",
            url,
            subscribed_events or "ALL",
        )
        return endpoint

    def _build_payload(
        self,
        endpoint: WebhookEndpoint,
        event: Event,
    ) -> WebhookPayload:
        """Construct a signed webhook payload for the given event.

        Serializes the event data to JSON, computes the HMAC-SHA256
        signature, and assembles the payload with all required headers
        including the mandatory X-FizzBuzz-Seriousness-Level: MAXIMUM.
        """
        try:
            body_dict = {
                "event_type": event.event_type.name,
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
                "payload": {
                    k: str(v) if not isinstance(v, (str, int, float, bool, type(None)))
                    else v
                    for k, v in event.payload.items()
                },
            }
            body = json.dumps(body_dict, sort_keys=True, indent=None)
        except (TypeError, ValueError) as e:
            raise WebhookPayloadSerializationError(
                event.event_type.name, str(e)
            ) from e

        signature = self._signature_engine.sign(body)

        headers = (
            ("Content-Type", "application/json"),
            ("X-FizzBuzz-Event", event.event_type.name),
            ("X-FizzBuzz-Delivery-ID", str(uuid.uuid4())),
            ("X-FizzBuzz-Signature-256", signature),
            ("X-FizzBuzz-Seriousness-Level", "MAXIMUM"),
            ("User-Agent", "EnterpriseFizzBuzzPlatform/1.0 WebhookDispatcher"),
        )

        return WebhookPayload(
            endpoint_url=endpoint.url,
            event_type=event.event_type.name,
            body=body,
            signature=signature,
            headers=headers,
        )

    def dispatch(self, event: Event) -> list[WebhookDeliveryResult]:
        """Dispatch a webhook for the given event to all matching endpoints.

        For each registered endpoint that is subscribed to this event type,
        constructs a signed payload and attempts delivery with retries.
        Failed deliveries are routed to the Dead Letter Queue.

        Args:
            event: The event to dispatch as webhooks.

        Returns:
            List of final delivery results for all endpoints.
        """
        with self._lock:
            endpoints = [
                ep for ep in self._endpoints
                if ep.active and (
                    not ep.subscribed_events
                    or event.event_type.name in ep.subscribed_events
                )
            ]

        if not endpoints:
            return []

        results: list[WebhookDeliveryResult] = []

        for endpoint in endpoints:
            payload = self._build_payload(endpoint, event)

            self._publish_event(EventType.WEBHOOK_DISPATCHED, {
                "endpoint_url": endpoint.url,
                "event_type": event.event_type.name,
                "payload_id": payload.payload_id,
            })

            self._publish_event(EventType.WEBHOOK_SIGNATURE_GENERATED, {
                "payload_id": payload.payload_id,
                "signature": payload.signature,
            })

            delivery_result = self._deliver_with_retry(payload)
            results.append(delivery_result)

            with self._lock:
                self._dispatch_count += 1
                if delivery_result.success:
                    self._success_count += 1
                else:
                    self._failure_count += 1

        return results

    def _deliver_with_retry(
        self,
        payload: WebhookPayload,
    ) -> WebhookDeliveryResult:
        """Attempt delivery with exponential backoff retry.

        Tries to deliver the payload, and if it fails, retries up to
        max_retries times with exponentially increasing delays (logged
        but not actually awaited). If all attempts fail, the payload
        is routed to the Dead Letter Queue.

        Args:
            payload: The webhook payload to deliver.

        Returns:
            The final WebhookDeliveryResult.
        """
        attempts: list[WebhookDeliveryResult] = []

        for attempt in range(1, self._retry_policy.max_retries + 1):
            result = self._http_client.deliver(payload, attempt_number=attempt)
            attempts.append(result)

            if result.success:
                self._publish_event(EventType.WEBHOOK_DELIVERY_SUCCESS, {
                    "endpoint_url": payload.endpoint_url,
                    "payload_id": payload.payload_id,
                    "attempt": attempt,
                    "status_code": result.status_code,
                })
                return result

            self._publish_event(EventType.WEBHOOK_DELIVERY_FAILED, {
                "endpoint_url": payload.endpoint_url,
                "payload_id": payload.payload_id,
                "attempt": attempt,
                "status_code": result.status_code,
                "error": result.error_message,
            })

            # Check if we should retry
            if self._retry_policy.should_retry(attempt):
                delay_ms = self._retry_policy.calculate_delay_ms(attempt - 1)
                self._publish_event(EventType.WEBHOOK_RETRY_SCHEDULED, {
                    "endpoint_url": payload.endpoint_url,
                    "payload_id": payload.payload_id,
                    "retry_attempt": attempt + 1,
                    "delay_ms": delay_ms,
                })
                logger.info(
                    "Webhook retry scheduled for %s: attempt %d, "
                    "backoff %.0fms (not actually waiting — this is FizzBuzz, "
                    "not a distributed system)",
                    payload.endpoint_url,
                    attempt + 1,
                    delay_ms,
                )

        # All retries exhausted — route to Dead Letter Queue
        final_error = attempts[-1].error_message if attempts else "Unknown error"
        try:
            self._dlq.enqueue(
                payload=payload,
                attempts=attempts,
                final_error=final_error,
            )
        except WebhookDeadLetterQueueFullError:
            logger.error(
                "Dead Letter Queue is full. Payload %s discarded permanently. "
                "This FizzBuzz notification will never reach its destination.",
                payload.payload_id,
            )

        self._publish_event(EventType.WEBHOOK_DEAD_LETTERED, {
            "endpoint_url": payload.endpoint_url,
            "payload_id": payload.payload_id,
            "total_attempts": len(attempts),
            "final_error": final_error,
        })

        return attempts[-1] if attempts else WebhookDeliveryResult(
            payload_id=payload.payload_id,
            endpoint_url=payload.endpoint_url,
            error_message="No delivery attempts made",
        )

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Publish an event to the event bus, if available."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="WebhookManager",
            ))

    def get_statistics(self) -> dict[str, Any]:
        """Return webhook manager statistics for dashboard rendering."""
        with self._lock:
            return {
                "registered_endpoints": len(self._endpoints),
                "total_dispatches": self._dispatch_count,
                "successful_deliveries": self._success_count,
                "failed_deliveries": self._failure_count,
                "delivery_success_rate": (
                    (self._success_count / self._dispatch_count * 100)
                    if self._dispatch_count > 0
                    else 0.0
                ),
                "dlq_size": self._dlq.get_size(),
                "dlq_max_size": self._dlq.max_size,
            }


# ============================================================
# Webhook Observer
# ============================================================


class WebhookObserver(IObserver):
    """Observer that translates EventBus events to webhook dispatches.

    Bridges the Observer pattern's event bus with the webhook
    dispatch system. When a subscribed event is published on the
    event bus, this observer intercepts it and routes it to the
    WebhookManager for dispatch to all registered endpoints.

    This is a classic Adapter pattern: it adapts the IObserver
    interface (which receives Events) to the WebhookManager
    interface (which dispatches webhooks). The fact that we need
    an adapter between two systems that both deal with events
    is the kind of layered abstraction that enterprise architects
    dream about.
    """

    def __init__(
        self,
        webhook_manager: WebhookManager,
        subscribed_events: Optional[set[str]] = None,
    ) -> None:
        self._manager = webhook_manager
        self._subscribed_events = subscribed_events or set()
        self._events_processed = 0
        self._lock = threading.Lock()

    def on_event(self, event: Event) -> None:
        """Handle an incoming event by dispatching it as a webhook.

        Only dispatches events that match the subscription filter.
        If no filter is set, all events are dispatched — because
        some observers believe every FizzBuzz event deserves a
        webhook notification.
        """
        if self._subscribed_events and event.event_type.name not in self._subscribed_events:
            return

        # Avoid recursive webhook events (don't webhook about webhooks)
        if event.event_type.name.startswith("WEBHOOK_"):
            return

        self._manager.dispatch(event)

        with self._lock:
            self._events_processed += 1

    def get_name(self) -> str:
        return "WebhookObserver"

    @property
    def events_processed(self) -> int:
        with self._lock:
            return self._events_processed


# ============================================================
# Webhook Dashboard
# ============================================================


class WebhookDashboard:
    """ASCII dashboard for webhook notification system status.

    Renders a beautiful, enterprise-grade terminal dashboard showing
    webhook delivery statistics, endpoint status, retry metrics, and
    Dead Letter Queue contents. Because what good is a webhook system
    if you can't admire its performance in monospace font?
    """

    @staticmethod
    def render(
        manager: WebhookManager,
        width: int = 60,
    ) -> str:
        """Render the webhook notification system dashboard.

        Args:
            manager: The WebhookManager to render statistics for.
            width: Dashboard width in characters.

        Returns:
            ASCII dashboard string.
        """
        stats = manager.get_statistics()
        client_stats = manager.http_client.get_statistics()
        dlq_stats = manager.dead_letter_queue.get_statistics()
        endpoints = manager.endpoints

        inner = width - 4

        lines = [
            "",
            f"  +{'=' * inner}+",
            f"  |{'WEBHOOK NOTIFICATION SYSTEM DASHBOARD':^{inner}}|",
            f"  +{'=' * inner}+",
            f"  |  {'Registered Endpoints':<22}: {stats['registered_endpoints']:<{inner - 26}}|",
            f"  |  {'Total Dispatches':<22}: {stats['total_dispatches']:<{inner - 26}}|",
            f"  |  {'Successful Deliveries':<22}: {stats['successful_deliveries']:<{inner - 26}}|",
            f"  |  {'Failed Deliveries':<22}: {stats['failed_deliveries']:<{inner - 26}}|",
            f"  |  {'Success Rate':<22}: {stats['delivery_success_rate']:<{inner - 30}.1f}%   |",
            f"  +{'-' * inner}+",
        ]

        # Endpoint list
        lines.append(f"  |{'REGISTERED ENDPOINTS':^{inner}}|")
        lines.append(f"  +{'-' * inner}+")

        if endpoints:
            for ep in endpoints:
                status = "ACTIVE" if ep.active else "INACTIVE"
                url_display = ep.url[:inner - 14]
                lines.append(
                    f"  |  [{status:<8}] {url_display:<{inner - 16}}|"
                )
                if ep.subscribed_events:
                    events_str = ", ".join(sorted(ep.subscribed_events))
                    events_display = events_str[:inner - 8]
                    lines.append(
                        f"  |    Events: {events_display:<{inner - 14}}|"
                    )
        else:
            lines.append(
                f"  |  {'(no endpoints registered)':<{inner - 4}}|"
            )

        lines.append(f"  +{'-' * inner}+")

        # HTTP Client stats
        lines.append(f"  |{'SIMULATED HTTP CLIENT':^{inner}}|")
        lines.append(f"  +{'-' * inner}+")
        lines.append(
            f"  |  {'Total Requests':<22}: {client_stats['total_deliveries']:<{inner - 26}}|"
        )
        lines.append(
            f"  |  {'Successful':<22}: {client_stats['successful']:<{inner - 26}}|"
        )
        lines.append(
            f"  |  {'Failed':<22}: {client_stats['failed']:<{inner - 26}}|"
        )

        lines.append(f"  +{'-' * inner}+")

        # Dead Letter Queue
        lines.append(f"  |{'DEAD LETTER QUEUE':^{inner}}|")
        lines.append(f"  +{'-' * inner}+")
        lines.append(
            f"  |  {'Entries':<22}: {dlq_stats['size']}/{dlq_stats['max_size']:<{inner - 27}}|"
        )
        lines.append(
            f"  |  {'Utilization':<22}: {dlq_stats['utilization_percent']:<{inner - 30}.1f}%   |"
        )
        lines.append(
            f"  |  {'Unique Endpoints':<22}: {dlq_stats['unique_endpoints']:<{inner - 26}}|"
        )

        # DLQ entries detail
        dlq_entries = manager.dead_letter_queue.get_entries()
        if dlq_entries:
            lines.append(f"  +{'-' * inner}+")
            lines.append(f"  |{'DLQ ENTRIES (most recent)':^{inner}}|")
            lines.append(f"  +{'-' * inner}+")
            for entry in dlq_entries[-5:]:  # Show last 5 entries
                url_short = entry.payload.endpoint_url[:inner - 12]
                lines.append(
                    f"  |  -> {url_short:<{inner - 8}}|"
                )
                lines.append(
                    f"  |     Error: {entry.final_error[:inner - 15]:<{inner - 15}}|"
                )
                lines.append(
                    f"  |     Attempts: {len(entry.attempts):<{inner - 19}}|"
                )

        lines.append(f"  +{'=' * inner}+")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_delivery_log(
        manager: WebhookManager,
        limit: int = 20,
    ) -> str:
        """Render the webhook delivery log.

        Args:
            manager: The WebhookManager whose delivery log to render.
            limit: Maximum number of entries to display.

        Returns:
            Formatted delivery log string.
        """
        log = manager.http_client.delivery_log
        if not log:
            return (
                "\n  +-- WEBHOOK DELIVERY LOG --+\n"
                "  |  No deliveries recorded.  |\n"
                "  +---------------------------+\n"
            )

        lines = [
            "",
            "  +-- WEBHOOK DELIVERY LOG -----------------------------------------+",
            "  |  #   | Status | Code | Endpoint                                 |",
            "  +------+--------+------+------------------------------------------+",
        ]

        for i, result in enumerate(log[-limit:], 1):
            status = "  OK  " if result.success else " FAIL "
            url = result.endpoint_url[:40]
            lines.append(
                f"  | {i:>3} |{status}| {result.status_code:>4} | {url:<40} |"
            )

        lines.append(
            "  +------+--------+------+------------------------------------------+"
        )
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_dlq(manager: WebhookManager) -> str:
        """Render the Dead Letter Queue contents.

        Args:
            manager: The WebhookManager whose DLQ to render.

        Returns:
            Formatted DLQ contents string.
        """
        entries = manager.dead_letter_queue.get_entries()
        dlq_stats = manager.dead_letter_queue.get_statistics()

        if not entries:
            return (
                "\n  +-- DEAD LETTER QUEUE --+\n"
                "  |  (empty)              |\n"
                "  |  All webhooks have    |\n"
                "  |  reached their        |\n"
                "  |  destinations.        |\n"
                "  +-----------------------+\n"
            )

        lines = [
            "",
            "  +===========================================================+",
            "  |                  DEAD LETTER QUEUE                         |",
            "  +===========================================================+",
            f"  |  Entries: {dlq_stats['size']}/{dlq_stats['max_size']}"
            f" ({dlq_stats['utilization_percent']:.1f}% full)"
            + " " * max(0, 37 - len(f"{dlq_stats['size']}/{dlq_stats['max_size']}"
                                     f" ({dlq_stats['utilization_percent']:.1f}% full)"))
            + "|",
            "  |-----------------------------------------------------------|",
        ]

        for i, entry in enumerate(entries, 1):
            lines.extend([
                f"  |  Entry #{i}:",
                f"  |    Payload ID : {entry.payload.payload_id[:40]}",
                f"  |    Endpoint   : {entry.payload.endpoint_url[:40]}",
                f"  |    Event Type : {entry.payload.event_type}",
                f"  |    Attempts   : {len(entry.attempts)}",
                f"  |    Error      : {entry.final_error[:40]}",
                f"  |    Reason     : {entry.reason}",
                "  |-----------------------------------------------------------|",
            ])

        lines.append(
            "  +===========================================================+"
        )
        lines.append("")

        return "\n".join(lines)

"""
Enterprise FizzBuzz Platform - Webhook Notification System Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class WebhookError(FizzBuzzError):
    """Base exception for all Webhook Notification System errors.

    When your webhook system for notifying external services about
    FizzBuzz evaluation events encounters an error, you must ask
    yourself: if a webhook fires in the forest and nobody receives
    the POST request, did the FizzBuzz evaluation really happen?
    The answer, philosophically and architecturally, is yes — but
    the audit trail will forever bear the scar of a failed delivery.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-WH00"),
            context=kwargs.pop("context", {}),
        )


class WebhookEndpointValidationError(WebhookError):
    """Raised when a webhook endpoint URL fails validation.

    The URL you provided is not a valid webhook endpoint. Perhaps
    it's missing the scheme, perhaps it points to localhost (which,
    in a simulated HTTP client, doesn't matter anyway), or perhaps
    it's just a random string you typed to see what would happen.
    Enterprise webhook systems demand well-formed URLs, even when
    they don't actually make HTTP requests.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"Invalid webhook endpoint URL '{url}': {reason}. "
            f"The webhook dispatcher refuses to even pretend to "
            f"deliver to this address.",
            error_code="EFP-WH01",
            context={"url": url, "reason": reason},
        )
        self.url = url


class WebhookSignatureError(WebhookError):
    """Raised when HMAC-SHA256 signature generation or verification fails.

    The cryptographic signature for this webhook payload could not
    be generated or verified. This is the webhook equivalent of
    sealing an envelope and then realizing you've forgotten the wax
    seal. Without a valid HMAC-SHA256 signature, the receiving
    endpoint (which is simulated) cannot verify the payload's
    authenticity (which is fictional).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Webhook signature error: {reason}. The HMAC-SHA256 "
            f"signature engine has encountered a cryptographic crisis "
            f"of confidence.",
            error_code="EFP-WH02",
            context={"reason": reason},
        )


class WebhookDeliveryError(WebhookError):
    """Raised when a webhook delivery attempt fails.

    The simulated HTTP client attempted to deliver the webhook payload
    and failed. In a real system, this could mean the endpoint is down,
    the network is unreachable, or the receiving server returned an
    error status code. In our simulated system, it means the deterministic
    hash function decided this particular URL should fail, which is
    somehow even more existentially troubling than a real network error.
    """

    def __init__(self, url: str, attempt: int, reason: str) -> None:
        super().__init__(
            f"Webhook delivery to '{url}' failed on attempt {attempt}: "
            f"{reason}. The simulated HTTP client has simulated a failure, "
            f"which is the most enterprise thing that has ever happened.",
            error_code="EFP-WH03",
            context={"url": url, "attempt": attempt, "reason": reason},
        )
        self.url = url
        self.attempt = attempt


class WebhookRetryExhaustedError(WebhookError):
    """Raised when all retry attempts for a webhook delivery have been exhausted.

    The webhook system has tried and tried again, each time with
    exponentially increasing delays (that it logged but didn't actually
    wait for), and each time the simulated HTTP client has deterministically
    refused to cooperate. The payload has been routed to the
    Dead Letter Queue, where it will be retained alongside
    other permanently failed deliveries for later analysis.
    """

    def __init__(self, url: str, max_retries: int) -> None:
        super().__init__(
            f"Webhook delivery to '{url}' exhausted all {max_retries} "
            f"retry attempts. Payload routed to Dead Letter Queue. "
            f"Consider updating your endpoint or accepting that some "
            f"FizzBuzz events are destined to remain undelivered.",
            error_code="EFP-WH04",
            context={"url": url, "max_retries": max_retries},
        )
        self.url = url


class WebhookPayloadSerializationError(WebhookError):
    """Raised when a webhook payload cannot be serialized to JSON.

    The event data could not be converted to JSON for webhook delivery.
    Perhaps it contains a datetime that refuses to be serialized, a
    circular reference that creates an infinite loop, or a custom object
    that has no idea how to represent itself as a string. Whatever the
    cause, the payload remains stubbornly un-JSON-ifiable.
    """

    def __init__(self, event_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to serialize webhook payload for event "
            f"'{event_type}': {reason}. The payload's contents are "
            f"too complex, too circular, or too proud to become JSON.",
            error_code="EFP-WH05",
            context={"event_type": event_type, "reason": reason},
        )


class WebhookDeadLetterQueueFullError(WebhookError):
    """Raised when the Dead Letter Queue has reached its maximum capacity.

    The DLQ is full. Every slot is occupied by a permanently failed
    webhook delivery that will never reach its destination. This is
    the webhook equivalent of a post office whose return-to-sender
    shelf has collapsed under the weight of undeliverable mail.
    At this point, you should either drain the DLQ, increase its
    capacity, or accept that your webhook endpoints are fundamentally
    unreachable.
    """

    def __init__(self, max_size: int) -> None:
        super().__init__(
            f"Dead Letter Queue is full ({max_size} entries). "
            f"No more failed deliveries can be stored. The DLQ has "
            f"reached its carrying capacity for disappointment.",
            error_code="EFP-WH06",
            context={"max_size": max_size},
        )


"""Webhook Notification System configuration properties"""

from __future__ import annotations

from typing import Any


class WebhooksConfigMixin:
    """Configuration properties for the webhooks subsystem."""

    # ----------------------------------------------------------------
    # Webhook Notification System configuration properties
    # ----------------------------------------------------------------

    @property
    def webhooks_enabled(self) -> bool:
        """Whether the Webhook Notification System is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("enabled", False)

    @property
    def webhooks_endpoints(self) -> list[str]:
        """List of webhook endpoint URLs to receive notifications."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("endpoints", [])

    @property
    def webhooks_secret(self) -> str:
        """HMAC-SHA256 secret for signing webhook payloads."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get(
            "secret", "enterprise-fizzbuzz-webhook-secret-do-not-share"
        )

    @property
    def webhooks_subscribed_events(self) -> list[str]:
        """List of event type names that trigger webhook dispatch."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("subscribed_events", [
            "FIZZ_DETECTED",
            "BUZZ_DETECTED",
            "FIZZBUZZ_DETECTED",
            "SESSION_STARTED",
            "SESSION_ENDED",
            "ERROR_OCCURRED",
        ])

    @property
    def webhooks_retry_max_retries(self) -> int:
        """Maximum number of delivery retry attempts before DLQ routing."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("max_retries", 3)

    @property
    def webhooks_retry_backoff_base_ms(self) -> float:
        """Base delay in milliseconds for exponential retry backoff."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("backoff_base_ms", 1000)

    @property
    def webhooks_retry_backoff_multiplier(self) -> float:
        """Multiplier for exponential retry backoff."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("backoff_multiplier", 2.0)

    @property
    def webhooks_retry_backoff_max_ms(self) -> float:
        """Maximum backoff delay in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("retry", {}).get("backoff_max_ms", 30000)

    @property
    def webhooks_dlq_max_size(self) -> int:
        """Maximum number of entries in the Dead Letter Queue."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("dead_letter_queue", {}).get("max_size", 100)

    @property
    def webhooks_simulated_success_rate(self) -> int:
        """Deterministic success rate for the simulated HTTP client (0-100)."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("simulated_client", {}).get("success_rate_percent", 80)

    @property
    def webhooks_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("webhooks", {}).get("dashboard", {}).get("width", 60)


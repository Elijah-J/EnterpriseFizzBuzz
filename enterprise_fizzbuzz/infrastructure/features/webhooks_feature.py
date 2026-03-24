"""Feature descriptor for the Webhook Notification System."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class WebhooksFeature(FeatureDescriptor):
    name = "webhooks"
    description = "Webhook notification system with HMAC-SHA256 signatures and dead letter queue"
    middleware_priority = 50
    cli_flags = [
        ("--webhooks", {"action": "store_true",
                        "help": "Enable the Webhook Notification System for event-driven FizzBuzz telemetry"}),
        ("--webhook-url", {"action": "append", "metavar": "URL", "default": [],
                           "help": "Register a webhook endpoint URL (can be specified multiple times)"}),
        ("--webhook-events", {"type": str, "metavar": "EVENTS", "default": None,
                              "help": "Comma-separated list of event types to subscribe to (default: from config)"}),
        ("--webhook-secret", {"type": str, "metavar": "SECRET", "default": None,
                              "help": "HMAC-SHA256 secret for signing webhook payloads (default: from config)"}),
        ("--webhook-test", {"action": "store_true",
                            "help": "Send a test webhook to all registered endpoints and exit"}),
        ("--webhook-log", {"action": "store_true",
                           "help": "Display the webhook delivery log after execution"}),
        ("--webhook-dlq", {"action": "store_true",
                           "help": "Display the Dead Letter Queue contents after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "webhooks", False),
            bool(getattr(args, "webhook_url", [])),
            getattr(args, "webhook_test", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.webhooks import (
            DeadLetterQueue,
            RetryPolicy,
            SimulatedHTTPClient,
            WebhookManager,
            WebhookObserver,
            WebhookSignatureEngine,
        )

        webhook_secret = args.webhook_secret or config.webhooks_secret
        sig_engine = WebhookSignatureEngine(webhook_secret)
        http_client = SimulatedHTTPClient(
            success_rate_percent=config.webhooks_simulated_success_rate,
        )
        retry_policy = RetryPolicy(
            max_retries=config.webhooks_retry_max_retries,
            backoff_base_ms=config.webhooks_retry_backoff_base_ms,
            backoff_multiplier=config.webhooks_retry_backoff_multiplier,
            backoff_max_ms=config.webhooks_retry_backoff_max_ms,
        )
        dlq = DeadLetterQueue(max_size=config.webhooks_dlq_max_size)
        webhook_manager = WebhookManager(
            signature_engine=sig_engine,
            http_client=http_client,
            retry_policy=retry_policy,
            dead_letter_queue=dlq,
            event_bus=event_bus,
        )

        for url in args.webhook_url:
            webhook_manager.register_endpoint(url)
        for url in config.webhooks_endpoints:
            webhook_manager.register_endpoint(url)

        if args.webhook_events:
            subscribed = set(args.webhook_events.split(","))
        else:
            subscribed = set(config.webhooks_subscribed_events)

        webhook_observer = WebhookObserver(
            webhook_manager=webhook_manager,
            subscribed_events=subscribed,
        )
        if event_bus is not None:
            event_bus.subscribe(webhook_observer)

        return webhook_manager, None

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | WEBHOOKS: Notification System ENABLED                   |\n"
            "  | All matching events will be dispatched to registered    |\n"
            "  | endpoints via simulated HTTP POST with HMAC-SHA256      |\n"
            "  | signatures. No actual HTTP requests will be made.       |\n"
            "  | X-FizzBuzz-Seriousness-Level: MAXIMUM                   |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.webhooks import WebhookDashboard
        # middleware is actually webhook_manager (service) since we return None for middleware
        return None

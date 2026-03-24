"""Message Queue & Event Bus properties"""

from __future__ import annotations

from typing import Any


class MqConfigMixin:
    """Configuration properties for the mq subsystem."""

    # ----------------------------------------------------------------
    # Message Queue & Event Bus properties
    # ----------------------------------------------------------------

    @property
    def mq_enabled(self) -> bool:
        """Whether the Message Queue subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("enabled", False)

    @property
    def mq_default_partitions(self) -> int:
        """Default number of partitions per topic (Python lists per topic)."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("default_partitions", 3)

    @property
    def mq_partitioner_strategy(self) -> str:
        """Partitioner strategy: hash, round_robin, or sticky."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("partitioner_strategy", "hash")

    @property
    def mq_enable_schema_validation(self) -> bool:
        """Whether to validate message payloads against the Schema Registry."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("enable_schema_validation", True)

    @property
    def mq_enable_idempotency(self) -> bool:
        """Whether to enforce exactly-once delivery via SHA-256 dedup."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("enable_idempotency", True)

    @property
    def mq_max_poll_records(self) -> int:
        """Maximum messages per consumer poll."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("max_poll_records", 10)

    @property
    def mq_consumer_session_timeout_ms(self) -> int:
        """Consumer session timeout in milliseconds (aspirational)."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("consumer_session_timeout_ms", 30000)

    @property
    def mq_topics(self) -> dict[str, Any]:
        """Topic definitions from configuration."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("topics", {})

    @property
    def mq_consumer_groups(self) -> dict[str, Any]:
        """Consumer group definitions from configuration."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("consumer_groups", {})

    @property
    def mq_dashboard_width(self) -> int:
        """ASCII dashboard width for message queue display."""
        self._ensure_loaded()
        return self._raw_config.get("message_queue", {}).get("dashboard", {}).get("width", 60)


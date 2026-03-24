"""FizzLambda serverless function runtime configuration properties."""

from __future__ import annotations

from typing import Any, Optional


class FizzLambdaConfigMixin:
    """Configuration properties for the FizzLambda serverless function runtime."""

    # ----------------------------------------------------------------
    # FizzLambda Serverless Function Runtime properties
    # ----------------------------------------------------------------

    @property
    def fizzlambda_enabled(self) -> bool:
        """Whether the FizzLambda serverless function runtime is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlambda", {}).get("enabled", False)

    @property
    def fizzlambda_mode(self) -> str:
        """Evaluation routing mode: container, serverless, or hybrid."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlambda", {}).get("mode", "container")

    @property
    def fizzlambda_max_total_environments(self) -> int:
        """Global warm pool capacity across all functions."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("max_total_environments", 1000))

    @property
    def fizzlambda_max_environments_per_function(self) -> int:
        """Per-function warm pool capacity limit."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("max_environments_per_function", 100))

    @property
    def fizzlambda_idle_timeout(self) -> float:
        """Idle eviction timeout in seconds for warm pool environments."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlambda", {}).get("idle_timeout", 300.0))

    @property
    def fizzlambda_max_burst_concurrency(self) -> int:
        """Maximum simultaneous cold starts during burst scaling."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("max_burst_concurrency", 500))

    @property
    def fizzlambda_account_concurrency_limit(self) -> int:
        """Account-wide concurrent execution cap."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("account_concurrency_limit", 1000))

    @property
    def fizzlambda_default_memory_mb(self) -> int:
        """Default function memory allocation in megabytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("default_memory_mb", 256))

    @property
    def fizzlambda_default_timeout(self) -> int:
        """Default function timeout in seconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("default_timeout", 30))

    @property
    def fizzlambda_default_ephemeral_storage_mb(self) -> int:
        """Default /tmp overlay capacity in megabytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("default_ephemeral_storage_mb", 512))

    @property
    def fizzlambda_max_retry_attempts(self) -> int:
        """Default retry count for failed invocations."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("max_retry_attempts", 2))

    @property
    def fizzlambda_retry_delay_seconds(self) -> int:
        """Base retry delay in seconds for exponential backoff."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("retry_delay_seconds", 60))

    @property
    def fizzlambda_snapshot_enabled(self) -> bool:
        """Whether snapshot-and-restore cold start optimization is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlambda", {}).get("snapshot_enabled", True)

    @property
    def fizzlambda_predictive_prewarming(self) -> bool:
        """Whether time-series predictive pre-warming is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlambda", {}).get("predictive_prewarming", True)

    @property
    def fizzlambda_layer_cache_size_mb(self) -> int:
        """Extracted layer cache capacity in megabytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("layer_cache_size_mb", 10240))

    @property
    def fizzlambda_max_recycling_invocations(self) -> int:
        """Maximum invocations before recycling an execution environment."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("max_recycling_invocations", 10000))

    @property
    def fizzlambda_max_recycling_lifetime(self) -> float:
        """Maximum lifetime in seconds before recycling an execution environment."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlambda", {}).get("max_recycling_lifetime", 14400.0))

    @property
    def fizzlambda_queue_depth_limit(self) -> int:
        """Async invocation queue depth limit per function."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("queue_depth_limit", 100000))

    @property
    def fizzlambda_queue_age_limit(self) -> float:
        """Maximum age in seconds for queued events before discard."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlambda", {}).get("queue_age_limit", 21600.0))

    @property
    def fizzlambda_dlq_alert_threshold(self) -> int:
        """Alert when DLQ message count exceeds this threshold."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("dlq_alert_threshold", 100))

    @property
    def fizzlambda_dlq_age_alert_seconds(self) -> int:
        """Alert when oldest DLQ message exceeds this age in seconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("dlq_age_alert_seconds", 86400))

    @property
    def fizzlambda_version_retention_days(self) -> int:
        """Garbage collect unreferenced versions older than this many days."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlambda", {}).get("version_retention_days", 30))

    @property
    def fizzlambda_dashboard_width(self) -> int:
        """Width of the FizzLambda ASCII dashboard."""
        self._ensure_loaded()
        return int(
            self._raw_config.get("fizzlambda", {}).get("dashboard", {}).get("width", 72)
        )

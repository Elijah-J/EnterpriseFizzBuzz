"""FizzCI configuration properties."""

from __future__ import annotations

from typing import Any


class FizzciConfigMixin:
    """Configuration properties for the FizzCI continuous integration pipeline engine."""

    @property
    def fizzci_enabled(self) -> bool:
        """Whether the FizzCI pipeline engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzci", {}).get("enabled", False)

    @property
    def fizzci_max_parallel_jobs(self) -> int:
        """Maximum parallel jobs per stage."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzci", {}).get("max_parallel_jobs", 8))

    @property
    def fizzci_job_timeout(self) -> float:
        """Default job timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzci", {}).get("job_timeout", 3600.0))

    @property
    def fizzci_step_timeout(self) -> float:
        """Default step timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzci", {}).get("step_timeout", 600.0))

    @property
    def fizzci_max_retries(self) -> int:
        """Default maximum retry attempts for failed jobs."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzci", {}).get("max_retries", 3))

    @property
    def fizzci_artifact_max_size(self) -> int:
        """Maximum artifact size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzci", {}).get("artifact_max_size", 104857600))

    @property
    def fizzci_cache_max_size(self) -> int:
        """Maximum build cache size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzci", {}).get("cache_max_size", 1073741824))

    @property
    def fizzci_cache_ttl(self) -> float:
        """Build cache entry TTL in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzci", {}).get("cache_ttl", 86400.0))

    @property
    def fizzci_log_buffer_size(self) -> int:
        """Log buffer size per job in lines."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzci", {}).get("log_buffer_size", 10000))

    @property
    def fizzci_history_max_runs(self) -> int:
        """Maximum pipeline runs to retain in history."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzci", {}).get("history_max_runs", 100))

    @property
    def fizzci_webhook_secret(self) -> str:
        """Webhook trigger HMAC secret."""
        self._ensure_loaded()
        return self._raw_config.get("fizzci", {}).get("webhook_secret", "")

    @property
    def fizzci_default_image(self) -> str:
        """Default container image for job isolation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzci", {}).get("default_image", "fizzbuzz/ci-runner:latest")

    @property
    def fizzci_pipelines_dir(self) -> str:
        """Directory containing pipeline YAML definitions."""
        self._ensure_loaded()
        return self._raw_config.get("fizzci", {}).get("pipelines_dir", ".fizzci/")

    @property
    def fizzci_dashboard_width(self) -> int:
        """Dashboard rendering width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzci", {}).get("dashboard_width", 72))

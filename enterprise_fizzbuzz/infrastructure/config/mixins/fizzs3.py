"""FizzS3 configuration properties."""

from __future__ import annotations

from typing import Any


class FizzS3ConfigMixin:
    """Configuration properties for the FizzS3 object storage subsystem."""

    @property
    def fizzs3_enabled(self) -> bool:
        """Whether the FizzS3 object storage subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzs3", {}).get("enabled", False)

    @property
    def fizzs3_default_region(self) -> str:
        """Default region for new buckets."""
        self._ensure_loaded()
        return self._raw_config.get("fizzs3", {}).get("default_region", "fizz-east-1")

    @property
    def fizzs3_max_buckets(self) -> int:
        """Maximum buckets per owner."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("max_buckets", 100))

    @property
    def fizzs3_default_encryption(self) -> str:
        """Default server-side encryption mode."""
        self._ensure_loaded()
        return self._raw_config.get("fizzs3", {}).get("default_encryption", "sse-s3")

    @property
    def fizzs3_chunk_size(self) -> int:
        """Content-addressable chunk size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("chunk_size", 4 * 1024 * 1024))

    @property
    def fizzs3_gc_interval(self) -> float:
        """Garbage collection interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("gc_interval", 21600.0))

    @property
    def fizzs3_gc_safety_delay(self) -> float:
        """GC safety delay in seconds before collecting unreferenced chunks."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("gc_safety_delay", 86400.0))

    @property
    def fizzs3_lifecycle_interval(self) -> float:
        """Lifecycle evaluation interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("lifecycle_interval", 86400.0))

    @property
    def fizzs3_compaction_threshold(self) -> float:
        """Segment fragmentation ratio that triggers compaction."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzs3", {}).get("compaction_threshold", 0.5))

    @property
    def fizzs3_segment_max_size(self) -> int:
        """Maximum segment size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("segment_max_size", 256 * 1024 * 1024))

    @property
    def fizzs3_replication_retry_max(self) -> int:
        """Maximum replication retry attempts."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("replication_retry_max", 24))

    @property
    def fizzs3_presign_default_expiry(self) -> int:
        """Default presigned URL expiry in seconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("presign_default_expiry", 3600))

    @property
    def fizzs3_key_rotation_days(self) -> int:
        """SSE-S3 master key rotation interval in days."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("key_rotation_days", 90))

    @property
    def fizzs3_dashboard_width(self) -> int:
        """Width of the FizzS3 ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzs3", {}).get("dashboard", {}).get("width", 72))

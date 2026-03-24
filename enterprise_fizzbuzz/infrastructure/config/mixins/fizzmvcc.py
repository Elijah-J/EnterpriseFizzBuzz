"""FizzMVCC configuration properties."""

from __future__ import annotations

from typing import Any


class FizzmvccConfigMixin:
    """Configuration properties for the FizzMVCC MVCC transaction engine."""

    @property
    def fizzmvcc_enabled(self) -> bool:
        """Whether the MVCC transaction engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("enabled", False)

    @property
    def fizzmvcc_isolation_level(self) -> str:
        """Default transaction isolation level."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("isolation_level", "read_committed")

    @property
    def fizzmvcc_cc_mode(self) -> str:
        """Concurrency control mode (mvcc, 2pl, occ)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("cc_mode", "mvcc")

    @property
    def fizzmvcc_deadlock_timeout_ms(self) -> int:
        """Deadlock detection timeout in milliseconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("deadlock_timeout_ms", 1000))

    @property
    def fizzmvcc_deadlock_interval_ms(self) -> int:
        """Deadlock detection cycle interval in milliseconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("deadlock_interval_ms", 100))

    @property
    def fizzmvcc_gc_strategy(self) -> str:
        """Garbage collection strategy (eager, lazy, cooperative)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("gc_strategy", "lazy")

    @property
    def fizzmvcc_gc_interval_ms(self) -> int:
        """Lazy GC cycle interval in milliseconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("gc_interval_ms", 5000))

    @property
    def fizzmvcc_gc_warning_threshold_s(self) -> int:
        """Seconds before warning about long-running transactions blocking GC."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("gc_warning_threshold_s", 60))

    @property
    def fizzmvcc_gc_force_abort_threshold_s(self) -> int:
        """Seconds before forcibly aborting long-running transactions blocking GC."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("gc_force_abort_threshold_s", 300))

    @property
    def fizzmvcc_lock_escalation_threshold(self) -> int:
        """Row-level locks per table before attempting table lock escalation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("lock_escalation_threshold", 5000))

    @property
    def fizzmvcc_plan_cache_size(self) -> int:
        """Maximum prepared statement plans in cache."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("plan_cache_size", 1000))

    @property
    def fizzmvcc_pool_min(self) -> int:
        """Minimum connection pool size."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("pool_min", 5))

    @property
    def fizzmvcc_pool_max(self) -> int:
        """Maximum connection pool size."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("pool_max", 20))

    @property
    def fizzmvcc_pool_timeout_s(self) -> float:
        """Connection checkout timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmvcc", {}).get("pool_timeout_s", 30.0))

    @property
    def fizzmvcc_pool_max_lifetime_s(self) -> float:
        """Maximum connection lifetime in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmvcc", {}).get("pool_max_lifetime_s", 1800.0))

    @property
    def fizzmvcc_auto_analyze_threshold(self) -> int:
        """Minimum modified tuples before auto-analyze triggers."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("auto_analyze_threshold", 50))

    @property
    def fizzmvcc_auto_analyze_scale_factor(self) -> float:
        """Fraction of table size added to threshold for auto-analyze."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmvcc", {}).get("auto_analyze_scale_factor", 0.1))

    @property
    def fizzmvcc_statistics_target(self) -> int:
        """Number of pages sampled per analyze pass."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("statistics_target", 100))

    @property
    def fizzmvcc_explain_analyze(self) -> bool:
        """Whether EXPLAIN ANALYZE runtime statistics collection is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("explain_analyze", False)

    @property
    def fizzmvcc_explain_buffers(self) -> bool:
        """Whether to include buffer statistics in EXPLAIN ANALYZE output."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("explain_buffers", False)

    @property
    def fizzmvcc_occ_threshold(self) -> int:
        """Read-to-write ratio above which OCC is recommended."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("occ_threshold", 10))

    @property
    def fizzmvcc_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("dashboard", {}).get("width", 72))

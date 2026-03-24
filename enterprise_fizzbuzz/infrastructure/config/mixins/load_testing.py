"""Load Testing Framework Properties"""

from __future__ import annotations

from typing import Any


class LoadTestingConfigMixin:
    """Configuration properties for the load testing subsystem."""

    # ----------------------------------------------------------------
    # Load Testing Framework Properties
    # ----------------------------------------------------------------

    @property
    def load_testing_enabled(self) -> bool:
        """Whether the load testing framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("enabled", False)

    @property
    def load_testing_default_profile(self) -> str:
        """Default workload profile for load tests."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("default_profile", "smoke")

    @property
    def load_testing_default_vus(self) -> int:
        """Default number of virtual users."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("default_vus", 10)

    @property
    def load_testing_default_duration_seconds(self) -> int:
        """Default test duration in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("default_duration_seconds", 30)

    @property
    def load_testing_ramp_up_seconds(self) -> int:
        """Ramp-up time in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("ramp_up_seconds", 5)

    @property
    def load_testing_ramp_down_seconds(self) -> int:
        """Ramp-down time in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("ramp_down_seconds", 3)

    @property
    def load_testing_numbers_per_vu(self) -> int:
        """Number of FizzBuzz evaluations per virtual user."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("numbers_per_vu", 100)

    @property
    def load_testing_think_time_ms(self) -> int:
        """Simulated think time between requests in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("think_time_ms", 0)

    @property
    def load_testing_timeout_seconds(self) -> int:
        """Maximum load test duration before forced stop."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("timeout_seconds", 300)

    @property
    def load_testing_dashboard_width(self) -> int:
        """ASCII dashboard width for load testing output."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("dashboard", {}).get("width", 60)

    @property
    def load_testing_histogram_buckets(self) -> int:
        """Number of histogram bars in latency distribution chart."""
        self._ensure_loaded()
        return self._raw_config.get("load_testing", {}).get("dashboard", {}).get("histogram_buckets", 10)


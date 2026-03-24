"""Health Check Probe configuration properties"""

from __future__ import annotations

from typing import Any


class HealthCheckConfigMixin:
    """Configuration properties for the health check subsystem."""

    # ----------------------------------------------------------------
    # Health Check Probe configuration properties
    # ----------------------------------------------------------------

    @property
    def health_check_enabled(self) -> bool:
        """Whether Kubernetes-style health check probes are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("enabled", False)

    @property
    def health_check_canary_number(self) -> int:
        """The number to evaluate as a liveness canary."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("liveness", {}).get("canary_number", 15)

    @property
    def health_check_canary_expected(self) -> str:
        """The expected result from the canary evaluation."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("liveness", {}).get("canary_expected", "FizzBuzz")

    @property
    def health_check_liveness_interval(self) -> int:
        """How often to run liveness checks in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("liveness", {}).get("interval_seconds", 30)

    @property
    def health_check_required_subsystems(self) -> list[str]:
        """Subsystems that must be UP for readiness."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("readiness", {}).get(
            "required_subsystems",
            ["config", "circuit_breaker", "cache", "sla", "ml_engine"],
        )

    @property
    def health_check_degraded_is_ready(self) -> bool:
        """Whether DEGRADED subsystems count as ready."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("readiness", {}).get("degraded_is_ready", True)

    @property
    def health_check_startup_milestones(self) -> list[str]:
        """Boot sequence milestones to track."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("startup", {}).get(
            "milestones",
            ["config_loaded", "rules_initialized", "engine_created", "middleware_assembled", "service_built"],
        )

    @property
    def health_check_startup_timeout(self) -> int:
        """Max time in seconds for startup sequence."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("startup", {}).get("timeout_seconds", 60)

    @property
    def health_check_self_healing_enabled(self) -> bool:
        """Whether automatic recovery on failures is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("self_healing", {}).get("enabled", True)

    @property
    def health_check_self_healing_max_retries(self) -> int:
        """Maximum recovery attempts per subsystem."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("self_healing", {}).get("max_retries", 3)

    @property
    def health_check_self_healing_backoff_ms(self) -> int:
        """Base delay between recovery attempts in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("self_healing", {}).get("backoff_base_ms", 500)

    @property
    def health_check_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("dashboard", {}).get("width", 60)

    @property
    def health_check_dashboard_show_details(self) -> bool:
        """Whether to show diagnostic details in the dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("health_check", {}).get("dashboard", {}).get("show_details", True)


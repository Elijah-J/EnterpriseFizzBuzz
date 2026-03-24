"""SLA Monitoring configuration properties"""

from __future__ import annotations

from typing import Any


class SlaConfigMixin:
    """Configuration properties for the sla subsystem."""

    # ----------------------------------------------------------------
    # SLA Monitoring configuration properties
    # ----------------------------------------------------------------

    @property
    def sla_enabled(self) -> bool:
        """Whether SLA Monitoring is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("enabled", False)

    @property
    def sla_latency_target(self) -> float:
        """SLO target for latency compliance (fraction, e.g. 0.999)."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("latency", {}).get("target", 0.999)

    @property
    def sla_latency_threshold_ms(self) -> float:
        """Maximum acceptable latency per evaluation in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("latency", {}).get("threshold_ms", 100.0)

    @property
    def sla_accuracy_target(self) -> float:
        """SLO target for accuracy compliance (fraction, e.g. 0.99999)."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("accuracy", {}).get("target", 0.99999)

    @property
    def sla_availability_target(self) -> float:
        """SLO target for availability compliance (fraction, e.g. 0.9999)."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("slos", {}).get("availability", {}).get("target", 0.9999)

    @property
    def sla_error_budget_window_days(self) -> int:
        """Rolling window in days for error budget calculation."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("error_budget", {}).get("window_days", 30)

    @property
    def sla_error_budget_burn_rate_threshold(self) -> float:
        """Alert when error budget is burning N times faster than planned."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("error_budget", {}).get("burn_rate_threshold", 2.0)

    @property
    def sla_alerting_cooldown_seconds(self) -> int:
        """Minimum seconds between alerts of the same type."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("alerting", {}).get("cooldown_seconds", 60)

    @property
    def sla_alerting_escalation_timeout_seconds(self) -> int:
        """Seconds before escalating an alert to the next level."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("alerting", {}).get("escalation_timeout_seconds", 300)

    @property
    def sla_on_call_team_name(self) -> str:
        """Name of the on-call team."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("on_call", {}).get(
            "team_name", "FizzBuzz Reliability Engineering"
        )

    @property
    def sla_on_call_rotation_interval_hours(self) -> int:
        """Hours between on-call rotation shifts."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("on_call", {}).get("rotation_interval_hours", 168)

    @property
    def sla_on_call_engineers(self) -> list[dict[str, str]]:
        """List of on-call engineer dicts with name, email, phone, title."""
        self._ensure_loaded()
        return self._raw_config.get("sla", {}).get("on_call", {}).get("engineers", [
            {
                "name": "Bob McFizzington",
                "email": "bob.mcfizzington@enterprise.example.com",
                "phone": "+1-555-FIZZBUZZ",
                "title": "Senior Principal Staff FizzBuzz Reliability Engineer II",
            },
        ])


"""FizzAdmit configuration properties."""

from __future__ import annotations

from typing import Any


class FizzadmitConfigMixin:
    """Configuration properties for the FizzAdmit subsystem."""

    @property
    def fizzadmit_enabled(self) -> bool:
        """Whether the FizzAdmit admission controller framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzadmit", {}).get("enabled", False)

    @property
    def fizzadmit_admission_timeout(self) -> float:
        """Default admission controller timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("admission_timeout", 10.0))

    @property
    def fizzadmit_finalizer_timeout(self) -> float:
        """Seconds before a finalizer is considered stuck."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("finalizer_timeout", 300.0))

    @property
    def fizzadmit_reconcile_max_concurrent(self) -> int:
        """Maximum concurrent reconciliations per operator."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("reconcile_max_concurrent", 1))

    @property
    def fizzadmit_reconcile_backoff_base(self) -> float:
        """Base reconcile retry backoff in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("reconcile_backoff_base", 5.0))

    @property
    def fizzadmit_reconcile_backoff_cap(self) -> float:
        """Maximum reconcile backoff in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("reconcile_backoff_cap", 300.0))

    @property
    def fizzadmit_leader_election_lease(self) -> float:
        """Leader election lease duration in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzadmit", {}).get("leader_election_lease", 15.0))

    @property
    def fizzadmit_enable_default_image_rules(self) -> bool:
        """Whether to register default image policy rules on startup."""
        self._ensure_loaded()
        return self._raw_config.get("fizzadmit", {}).get("enable_default_image_rules", True)

    @property
    def fizzadmit_default_security_profile(self) -> str:
        """Default pod security profile for namespaces without explicit policy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzadmit", {}).get("default_security_profile", "BASELINE")

    @property
    def fizzadmit_dashboard_width(self) -> int:
        """Width of the FizzAdmit ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("dashboard_width", 80))

    @property
    def fizzadmit_max_audit_records(self) -> int:
        """Maximum admission audit records retained in memory."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("max_audit_records", 10000))

    @property
    def fizzadmit_work_queue_max_depth(self) -> int:
        """Maximum operator work queue depth before backpressure."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzadmit", {}).get("work_queue_max_depth", 1000))

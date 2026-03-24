"""Fizzpolicy configuration properties."""

from __future__ import annotations

from typing import Any


class FizzpolicyConfigMixin:
    """Configuration properties for the fizzpolicy subsystem."""

    @property
    def fizzpolicy_enabled(self) -> bool:
        """Whether the FizzPolicy declarative policy engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpolicy", {}).get("enabled", False)

    @property
    def fizzpolicy_eval_timeout_ms(self) -> float:
        """Maximum wall-clock time for a single policy evaluation in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("eval_timeout_ms", 100.0))

    @property
    def fizzpolicy_max_iterations(self) -> int:
        """Maximum plan instruction executions per evaluation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("max_iterations", 100000))

    @property
    def fizzpolicy_max_output_size_bytes(self) -> int:
        """Maximum result document size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("max_output_size_bytes", 1048576))

    @property
    def fizzpolicy_cache_max_entries(self) -> int:
        """Maximum entries in the evaluation cache."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("cache_max_entries", 10000))

    @property
    def fizzpolicy_explanation_mode(self) -> str:
        """Decision explanation verbosity: full, summary, minimal, off."""
        self._ensure_loaded()
        return str(self._raw_config.get("fizzpolicy", {}).get("explanation_mode", "summary"))

    @property
    def fizzpolicy_signing_key(self) -> str:
        """HMAC-SHA256 signing key for policy bundles."""
        self._ensure_loaded()
        return str(self._raw_config.get("fizzpolicy", {}).get("signing_key", "fizzbuzz-default-policy-key"))

    @property
    def fizzpolicy_data_refresh_interval(self) -> float:
        """Default data adapter refresh interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("data_refresh_interval", 30.0))

    @property
    def fizzpolicy_bundle_coverage_threshold(self) -> float:
        """Minimum test coverage percentage for bundle builds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("bundle_coverage_threshold", 80.0))

    @property
    def fizzpolicy_bundle_perf_threshold_ms(self) -> float:
        """Maximum p99 evaluation time for bundle performance checks."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpolicy", {}).get("bundle_perf_threshold_ms", 10.0))

    @property
    def fizzpolicy_decision_log_mask_fields(self) -> list:
        """Input fields to redact in decision logs."""
        self._ensure_loaded()
        return list(self._raw_config.get("fizzpolicy", {}).get("decision_log", {}).get("mask_fields", ["token", "secret", "password", "hmac_key"]))

    @property
    def fizzpolicy_decision_log_page_size(self) -> int:
        """Default page size for decision log queries."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpolicy", {}).get("decision_log", {}).get("page_size", 100))

"""FinOps Cost Tracking & Chargeback Engine properties"""

from __future__ import annotations

from typing import Any


class FinopsConfigMixin:
    """Configuration properties for the finops subsystem."""

    # ----------------------------------------------------------------
    # FinOps Cost Tracking & Chargeback Engine properties
    # ----------------------------------------------------------------

    @property
    def finops_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("enabled", False)

    @property
    def finops_currency(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("currency", "FB$")

    @property
    def finops_exchange_rate_base(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("exchange_rate_base", 0.0001)

    @property
    def finops_tax_rate_fizz(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("fizz", 0.03)

    @property
    def finops_tax_rate_buzz(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("buzz", 0.05)

    @property
    def finops_tax_rate_fizzbuzz(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("fizzbuzz", 0.15)

    @property
    def finops_tax_rate_plain(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("tax_rates", {}).get("plain", 0.00)

    @property
    def finops_friday_premium_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("friday_premium_pct", 50.0)

    @property
    def finops_budget_monthly_limit(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("budget", {}).get("monthly_limit", 10.0)

    @property
    def finops_budget_warning_threshold_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("budget", {}).get("warning_threshold_pct", 80.0)

    @property
    def finops_savings_one_year_discount_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("savings_plans", {}).get("one_year_discount_pct", 30.0)

    @property
    def finops_savings_three_year_discount_pct(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("savings_plans", {}).get("three_year_discount_pct", 55.0)

    @property
    def finops_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("finops", {}).get("dashboard", {}).get("width", 60)


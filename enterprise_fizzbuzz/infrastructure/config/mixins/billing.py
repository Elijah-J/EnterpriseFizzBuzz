"""FizzBill Billing & Revenue Recognition properties"""

from __future__ import annotations

from typing import Any


class BillingConfigMixin:
    """Configuration properties for the billing subsystem."""

    # ----------------------------------------------------------------
    # FizzBill Billing & Revenue Recognition properties
    # ----------------------------------------------------------------

    @property
    def billing_enabled(self) -> bool:
        """Whether the FizzBill billing subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("enabled", False)

    @property
    def billing_default_tier(self) -> str:
        """Default subscription tier for new tenants."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("default_tier", "free")

    @property
    def billing_default_tenant_id(self) -> str:
        """Default tenant identifier."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("default_tenant_id", "tenant-default")

    @property
    def billing_spending_cap(self) -> Optional[float]:
        """Optional monthly spending cap in FizzBucks."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("spending_cap", None)

    @property
    def billing_dashboard_width(self) -> int:
        """Dashboard width for the billing dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("billing", {}).get("dashboard", {}).get("width", 60)



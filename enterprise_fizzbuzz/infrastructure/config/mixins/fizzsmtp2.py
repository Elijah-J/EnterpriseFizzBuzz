"""FizzSMTP2 configuration properties."""

from __future__ import annotations


class Fizzsmtp2ConfigMixin:
    """Configuration properties for the FizzSMTP2 SMTP relay."""

    @property
    def fizzsmtp2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzsmtp2", {}).get("enabled", False)

    @property
    def fizzsmtp2_max_queue_size(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsmtp2", {}).get("max_queue_size", 10000))

    @property
    def fizzsmtp2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsmtp2", {}).get("dashboard_width", 72))

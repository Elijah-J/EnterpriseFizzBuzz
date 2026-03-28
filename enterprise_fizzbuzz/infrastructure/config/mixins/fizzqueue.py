"""FizzQueue configuration properties."""
from __future__ import annotations

class FizzqueueConfigMixin:
    @property
    def fizzqueue_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzqueue", {}).get("enabled", False)
    @property
    def fizzqueue_max_queues(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzqueue", {}).get("max_queues", 1000))
    @property
    def fizzqueue_max_message_size(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzqueue", {}).get("max_message_size", 1048576))
    @property
    def fizzqueue_default_ttl(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzqueue", {}).get("default_ttl", 0))
    @property
    def fizzqueue_prefetch(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzqueue", {}).get("prefetch", 10))
    @property
    def fizzqueue_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzqueue", {}).get("dashboard_width", 72))

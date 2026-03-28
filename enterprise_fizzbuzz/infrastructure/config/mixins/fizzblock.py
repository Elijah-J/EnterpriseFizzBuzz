"""FizzBlock configuration properties."""

from __future__ import annotations


class FizzblockConfigMixin:
    """Configuration properties for the FizzBlock block storage & volume manager."""

    @property
    def fizzblock_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzblock", {}).get("enabled", False)

    @property
    def fizzblock_sector_size(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzblock", {}).get("sector_size", 4096))

    @property
    def fizzblock_default_raid(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzblock", {}).get("default_raid", "none")

    @property
    def fizzblock_encryption(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzblock", {}).get("encryption", False)

    @property
    def fizzblock_dedup(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzblock", {}).get("dedup", False)

    @property
    def fizzblock_compression(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzblock", {}).get("compression", "none")

    @property
    def fizzblock_scheduler(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzblock", {}).get("scheduler", "deadline")

    @property
    def fizzblock_iops_limit(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzblock", {}).get("iops_limit", 0))

    @property
    def fizzblock_bandwidth_limit(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzblock", {}).get("bandwidth_limit", 0))

    @property
    def fizzblock_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzblock", {}).get("dashboard_width", 72))

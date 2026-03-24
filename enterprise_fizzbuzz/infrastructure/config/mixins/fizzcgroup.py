"""Fizzcgroup configuration properties."""

from __future__ import annotations

from typing import Any


class FizzcgroupConfigMixin:
    """Configuration properties for the fizzcgroup subsystem."""

    @property
    def fizzcgroup_enabled(self) -> bool:
        """Whether the FizzCgroup resource accounting engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcgroup", {}).get("enabled", False)

    @property
    def fizzcgroup_oom_policy(self) -> str:
        """OOM killer victim selection policy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcgroup", {}).get("oom_policy", "kill_largest")

    @property
    def fizzcgroup_default_cpu_weight(self) -> int:
        """Default CPU weight for new cgroups."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcgroup", {}).get("default_cpu_weight", 100))

    @property
    def fizzcgroup_default_memory_max(self) -> int:
        """Default memory.max in bytes for new cgroups."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcgroup", {}).get("default_memory_max", -1))

    @property
    def fizzcgroup_default_pids_max(self) -> int:
        """Default pids.max for new cgroups."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcgroup", {}).get("default_pids_max", -1))

    @property
    def fizzcgroup_default_io_weight(self) -> int:
        """Default I/O weight for new cgroups."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcgroup", {}).get("default_io_weight", 100))

    @property
    def fizzcgroup_dashboard_width(self) -> int:
        """Width of the FizzCgroup ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcgroup", {}).get("dashboard", {}).get("width", 72))

    # ── FizzBob: Operator Cognitive Load ────────────────────────


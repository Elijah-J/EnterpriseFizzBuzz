"""Elf configuration properties."""

from __future__ import annotations

from typing import Any


class ElfConfigMixin:
    """Configuration properties for the elf subsystem."""

    @property
    def elf_enabled(self) -> bool:
        """Whether ELF binary generation is enabled via configuration."""
        self._ensure_loaded()
        return self._raw_config.get("elf", {}).get("enabled", False)

    @property
    def elf_output_path(self) -> Optional[str]:
        """Default output path for generated ELF binaries."""
        self._ensure_loaded()
        return self._raw_config.get("elf", {}).get("output_path", None)

    @property
    def elf_dashboard_width(self) -> int:
        """Width of the FizzELF ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("elf", {}).get("dashboard", {}).get("width", 72)


"""FizzForensics Digital Forensics Engine properties."""

from __future__ import annotations

from typing import Any


class FizzforensicsConfigMixin:
    """Configuration properties for the FizzForensics subsystem."""

    @property
    def fizzforensics_enabled(self) -> bool:
        """Whether the FizzForensics digital forensics engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzforensics", {}).get("enabled", False)

    @property
    def fizzforensics_sector_count(self) -> int:
        """Number of sectors in the virtual disk image."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzforensics", {}).get("sector_count", 1024))

    @property
    def fizzforensics_hash_algorithm(self) -> str:
        """Cryptographic hash algorithm for evidence verification."""
        self._ensure_loaded()
        return self._raw_config.get("fizzforensics", {}).get("hash_algorithm", "sha256")

    @property
    def fizzforensics_seed(self) -> int:
        """Random seed for forensic simulation reproducibility."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzforensics", {}).get("seed", 42))

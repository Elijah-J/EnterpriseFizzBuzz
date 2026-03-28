"""FizzZKP Zero-Knowledge Proof System Configuration Properties"""

from __future__ import annotations

from typing import Any


class FizzzkpConfigMixin:
    """Configuration properties for the zero-knowledge proof system."""

    @property
    def fizzzkp_enabled(self) -> bool:
        """Whether the zero-knowledge proof system is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzzkp", {}).get("enabled", False)

    @property
    def fizzzkp_protocol(self) -> str:
        """Default proof protocol (schnorr, chaum_pedersen, sigma_or)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzzkp", {}).get("protocol", "schnorr")

    @property
    def fizzzkp_security_bits(self) -> int:
        """Security parameter in bits."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzzkp", {}).get("security_bits", 128))

    @property
    def fizzzkp_audit_trail(self) -> bool:
        """Whether to maintain a full proof audit trail."""
        self._ensure_loaded()
        return self._raw_config.get("fizzzkp", {}).get("audit_trail", True)

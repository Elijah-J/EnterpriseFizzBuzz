"""FizzHomomorphic Encryption Configuration Properties"""

from __future__ import annotations

from typing import Any


class FizzhomomorphicConfigMixin:
    """Configuration properties for the homomorphic encryption engine."""

    @property
    def fizzhomomorphic_enabled(self) -> bool:
        """Whether the homomorphic encryption engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzhomomorphic", {}).get("enabled", False)

    @property
    def fizzhomomorphic_poly_degree(self) -> int:
        """Polynomial modulus degree (must be power of 2)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzhomomorphic", {}).get("poly_degree", 64))

    @property
    def fizzhomomorphic_coeff_modulus(self) -> int:
        """Coefficient modulus for the BFV scheme."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzhomomorphic", {}).get("coeff_modulus", 65537))

    @property
    def fizzhomomorphic_plain_modulus(self) -> int:
        """Plaintext modulus for the BFV scheme."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzhomomorphic", {}).get("plain_modulus", 257))

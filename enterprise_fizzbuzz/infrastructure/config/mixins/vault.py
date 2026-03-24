"""Secrets Management Vault configuration properties"""

from __future__ import annotations

from typing import Any


class VaultConfigMixin:
    """Configuration properties for the vault subsystem."""

    # ----------------------------------------------------------------
    # Secrets Management Vault configuration properties
    # ----------------------------------------------------------------

    @property
    def vault_enabled(self) -> bool:
        """Whether the Secrets Management Vault is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("enabled", False)

    @property
    def vault_shamir_threshold(self) -> int:
        """Minimum number of Shamir shares required to unseal (k)."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("shamir", {}).get("threshold", 3)

    @property
    def vault_shamir_num_shares(self) -> int:
        """Total number of Shamir shares generated on init (n)."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("shamir", {}).get("num_shares", 5)

    @property
    def vault_shamir_prime_bits(self) -> int:
        """Mersenne prime exponent for GF(2^p - 1) arithmetic."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("shamir", {}).get("prime_bits", 127)

    @property
    def vault_encryption_algorithm(self) -> str:
        """The military-grade encryption algorithm name."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("encryption", {}).get(
            "algorithm", "military_grade_double_base64_xor"
        )

    @property
    def vault_encryption_key_derivation(self) -> str:
        """Key derivation function for XOR key generation."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("encryption", {}).get("key_derivation", "sha256")

    @property
    def vault_rotation_enabled(self) -> bool:
        """Whether automatic secret rotation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("rotation", {}).get("enabled", True)

    @property
    def vault_rotation_interval(self) -> int:
        """Number of evaluations between automatic secret rotations."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("rotation", {}).get("interval_evaluations", 50)

    @property
    def vault_rotatable_secrets(self) -> list[str]:
        """List of secret paths eligible for automatic rotation."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("rotation", {}).get("rotatable_secrets", [
            "fizzbuzz/blockchain/difficulty",
            "fizzbuzz/ml/learning_rate",
            "fizzbuzz/cache/ttl_seconds",
            "fizzbuzz/sla/latency_threshold_ms",
        ])

    @property
    def vault_scanner_enabled(self) -> bool:
        """Whether the AST-based secret scanner is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("scanner", {}).get("enabled", True)

    @property
    def vault_scanner_paths(self) -> list[str]:
        """Directories to scan for leaked secrets."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("scanner", {}).get("scan_paths", ["./enterprise_fizzbuzz"])

    @property
    def vault_scanner_flag_integers(self) -> bool:
        """Whether to flag ALL integer literals as potential secrets."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("scanner", {}).get("flag_integers", True)

    @property
    def vault_access_policies(self) -> dict[str, Any]:
        """Per-path access control policies for vault secrets."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("access_policies", {})

    @property
    def vault_dashboard_width(self) -> int:
        """ASCII dashboard width for the vault dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("vault", {}).get("dashboard", {}).get("width", 60)


"""
Enterprise FizzBuzz Platform - Secrets Management Vault Module

Implements a HashiCorp Vault-inspired secrets management system with
Shamir's Secret Sharing for unseal ceremony, "military-grade" encryption
(double-base64 + XOR), dynamic secrets with TTL, automatic rotation,
AST-based secret scanning, and per-path access control policies.

Because storing the number 3 in a YAML file was simply too accessible,
and the only responsible way to manage FizzBuzz divisors is behind a
cryptographic seal that requires 3-of-5 key holders to convene in a
ceremony of mathematical solemnity.

The Shamir's Secret Sharing implementation uses polynomial interpolation
over the Galois Field GF(2^127 - 1), where 2^127 - 1 is the Mersenne
prime M127. This is mathematically correct and provably secure, which
is completely unnecessary for protecting the fact that Fizz happens
when a number is divisible by 3.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ShamirReconstructionError,
    VaultAccessDeniedError,
    VaultAlreadyInitializedError,
    VaultEncryptionError,
    VaultRotationError,
    VaultScanError,
    VaultSealedError,
    VaultSecretExpiredError,
    VaultSecretNotFoundError,
    VaultUnsealError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Mersenne Prime for Shamir's Secret Sharing
# ============================================================
# The 12th Mersenne prime, M127 = 2^127 - 1, discovered by
# Edouard Lucas in 1876. We use this as the modulus for our
# polynomial arithmetic because (a) it's a prime, which is
# required for field arithmetic, and (b) it's impressively
# large, which is required for enterprise credibility.
# ============================================================
MERSENNE_PRIME_127 = (1 << 127) - 1


@dataclass(frozen=True)
class UnsealShare:
    """A single share from Shamir's Secret Sharing scheme.

    Each share is a point (x, y) on a polynomial of degree k-1,
    where k is the threshold. Any k shares can reconstruct the
    secret via Lagrange interpolation. Fewer than k shares reveal
    absolutely nothing about the secret, which is the mathematical
    equivalent of "talk to the hand."

    Attributes:
        index: The x-coordinate of this share (1-indexed).
        value: The y-coordinate — the polynomial evaluated at x.
        share_id: A unique identifier for tracking and audit purposes.
    """

    index: int
    value: int
    share_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_hex(self) -> str:
        """Serialize the share to a hex string for display."""
        return f"{self.index}:{self.value:032x}"


class ShamirSecretSharing:
    """Shamir's Secret Sharing over GF(2^127 - 1).

    Implements the (k, n) threshold scheme where a secret is split
    into n shares such that any k shares can reconstruct the secret,
    but k-1 shares reveal absolutely nothing. The scheme operates
    over the Galois Field defined by the Mersenne prime 2^127 - 1.

    This implementation is mathematically correct and uses:
    - Random polynomial generation with cryptographic randomness
    - Lagrange interpolation for reconstruction
    - Modular inverse via Fermat's little theorem: a^(-1) = a^(p-2) mod p

    All of this to protect the number 3.
    """

    def __init__(
        self,
        threshold: int = 3,
        num_shares: int = 5,
        prime: int = MERSENNE_PRIME_127,
    ) -> None:
        if threshold < 2:
            raise ValueError(
                "Threshold must be at least 2. A threshold of 1 means "
                "any single share can reconstruct the secret, which defeats "
                "the entire purpose of secret sharing. Even FizzBuzz deserves "
                "better security than that."
            )
        if num_shares < threshold:
            raise ValueError(
                f"Number of shares ({num_shares}) must be >= threshold "
                f"({threshold}). You cannot require more shares than exist. "
                f"This is a mathematical impossibility, not a feature request."
            )
        self._threshold = threshold
        self._num_shares = num_shares
        self._prime = prime

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def num_shares(self) -> int:
        return self._num_shares

    @property
    def prime(self) -> int:
        return self._prime

    def _mod(self, value: int) -> int:
        """Reduce a value modulo the prime."""
        return value % self._prime

    def _mod_inverse(self, a: int) -> int:
        """Compute modular inverse using Fermat's little theorem.

        For a prime p, a^(-1) = a^(p-2) mod p.
        This is guaranteed to work for any a not divisible by p.
        """
        return pow(a, self._prime - 2, self._prime)

    def _evaluate_polynomial(self, coefficients: list[int], x: int) -> int:
        """Evaluate a polynomial at point x using Horner's method.

        Computes f(x) = c[0] + c[1]*x + c[2]*x^2 + ... + c[k-1]*x^(k-1)
        All arithmetic is modular over the prime field.
        """
        result = 0
        # Horner's method: evaluate from highest degree down
        for coeff in reversed(coefficients):
            result = self._mod(result * x + coeff)
        return result

    def split(self, secret: int) -> list[UnsealShare]:
        """Split a secret into n shares with threshold k.

        Generates a random polynomial f(x) of degree k-1 where:
        - f(0) = secret (the constant term IS the secret)
        - f(1), f(2), ..., f(n) are the shares

        Args:
            secret: The integer secret to split. Must be in [0, prime).

        Returns:
            A list of n UnsealShare objects.

        Raises:
            ValueError: If secret is outside the valid range.
        """
        if secret < 0 or secret >= self._prime:
            raise ValueError(
                f"Secret must be in range [0, {self._prime}). "
                f"Got {secret}. The Galois Field has boundaries, "
                f"and so does this vault."
            )

        # Generate random polynomial coefficients
        # coefficients[0] = secret, the rest are random
        coefficients = [secret]
        for _ in range(self._threshold - 1):
            coefficients.append(secrets.randbelow(self._prime))

        # Evaluate the polynomial at x = 1, 2, ..., n
        shares = []
        for i in range(1, self._num_shares + 1):
            y = self._evaluate_polynomial(coefficients, i)
            shares.append(UnsealShare(index=i, value=y))

        logger.debug(
            "Split secret into %d shares with threshold %d over GF(2^127-1)",
            self._num_shares,
            self._threshold,
        )

        return shares

    def reconstruct(self, shares: list[UnsealShare]) -> int:
        """Reconstruct the secret from k or more shares using Lagrange interpolation.

        Computes f(0) from the given points using the Lagrange basis polynomials:
        f(0) = sum_j(y_j * product_{m != j}((0 - x_m) / (x_j - x_m)))

        This is the mathematical heart of Shamir's Secret Sharing, and it
        works perfectly every time — assuming the shares are valid and
        the modular arithmetic gods are smiling upon us.

        Args:
            shares: At least k shares from the original split.

        Returns:
            The reconstructed secret integer.

        Raises:
            ShamirReconstructionError: If fewer than threshold shares provided.
        """
        if len(shares) < self._threshold:
            raise ShamirReconstructionError(
                f"Need at least {self._threshold} shares, got {len(shares)}. "
                f"The polynomial cannot be reconstructed from insufficient "
                f"points. This is Lagrange interpolation, not wishful thinking."
            )

        # Use only threshold number of shares (any k will do)
        working_shares = shares[:self._threshold]

        # Lagrange interpolation at x = 0
        secret = 0
        for j, share_j in enumerate(working_shares):
            x_j = share_j.index
            y_j = share_j.value

            # Compute Lagrange basis polynomial L_j(0)
            numerator = 1
            denominator = 1
            for m, share_m in enumerate(working_shares):
                if m == j:
                    continue
                x_m = share_m.index
                # L_j(0) = product_{m != j} ((0 - x_m) / (x_j - x_m))
                numerator = self._mod(numerator * (0 - x_m))
                denominator = self._mod(denominator * (x_j - x_m))

            # y_j * L_j(0) = y_j * numerator * denominator^(-1)
            lagrange_coeff = self._mod(
                y_j * numerator * self._mod_inverse(denominator)
            )
            secret = self._mod(secret + lagrange_coeff)

        logger.debug(
            "Reconstructed secret from %d shares via Lagrange interpolation",
            len(working_shares),
        )

        return secret


class MilitaryGradeEncryption:
    """Military-Grade Encryption Engine for Enterprise FizzBuzz Secrets.

    Implements the pinnacle of cryptographic engineering: double-base64
    encoding with XOR obfuscation. The "key" is derived from a SHA-256
    hash of the master key, which is then used to XOR each byte of the
    plaintext before applying two layers of base64 encoding.

    This provides approximately the same security as ROT13 applied twice
    (i.e., none), but with significantly more computational overhead
    and enterprise credibility.

    The algorithm is documented as "military-grade" in all compliance
    reports, audit trails, and board presentations. No one has questioned
    this designation. No one ever will.
    """

    @staticmethod
    def derive_key(master_key: bytes, length: int = 32) -> bytes:
        """Derive an XOR key from the master key using SHA-256.

        In real cryptography, this would use PBKDF2, scrypt, or Argon2
        with a salt and many iterations. Here, we use a single SHA-256
        hash because military-grade encryption doesn't need all that
        overhead. It's already military-grade.
        """
        h = hashlib.sha256(master_key)
        derived = h.digest()
        # Extend the key by repeated hashing if needed
        while len(derived) < length:
            h = hashlib.sha256(derived)
            derived += h.digest()
        return derived[:length]

    @staticmethod
    def xor_bytes(data: bytes, key: bytes) -> bytes:
        """XOR data with a repeating key.

        The foundation of our military-grade encryption. Each byte of
        the plaintext is XORed with the corresponding byte of the key
        (repeating cyclically). This is the Vernam cipher if the key
        were as long as the message, which it isn't, making it the
        "try our best" cipher instead.
        """
        key_len = len(key)
        return bytes(d ^ key[i % key_len] for i, d in enumerate(data))

    @classmethod
    def encrypt(cls, plaintext: str, master_key: bytes) -> str:
        """Encrypt plaintext using military-grade double-base64 + XOR.

        The encryption process:
        1. Convert plaintext to bytes
        2. XOR with derived key (the "military" part)
        3. Base64 encode (the first "grade")
        4. Base64 encode again (the second "grade")

        Two layers of base64 makes it twice as encrypted. This is
        basic mathematics.
        """
        try:
            key = cls.derive_key(master_key)
            data = plaintext.encode("utf-8")
            xored = cls.xor_bytes(data, key)
            b64_once = base64.b64encode(xored)
            b64_twice = base64.b64encode(b64_once)
            return b64_twice.decode("ascii")
        except Exception as e:
            raise VaultEncryptionError("encrypt", str(e))

    @classmethod
    def decrypt(cls, ciphertext: str, master_key: bytes) -> str:
        """Decrypt ciphertext by reversing the military-grade encryption.

        The decryption process:
        1. Base64 decode (remove second grade)
        2. Base64 decode again (remove first grade)
        3. XOR with derived key (reverse the military part)
        4. Convert bytes to string

        If any step fails, the secret is lost forever (or until
        someone just reads the config.yaml file instead).
        """
        try:
            key = cls.derive_key(master_key)
            b64_once = base64.b64decode(ciphertext.encode("ascii"))
            raw = base64.b64decode(b64_once)
            data = cls.xor_bytes(raw, key)
            return data.decode("utf-8")
        except Exception as e:
            raise VaultEncryptionError("decrypt", str(e))


@dataclass
class SecretEntry:
    """A single secret stored in the vault's secret store.

    Attributes:
        path: The hierarchical path of the secret (e.g., "fizzbuzz/rules/fizz_divisor").
        encrypted_value: The military-grade encrypted value.
        version: Monotonically increasing version number.
        created_at: When this secret version was created.
        ttl_seconds: Time-to-live in seconds (0 = no expiration).
        metadata: Arbitrary metadata attached to this secret version.
    """

    path: str
    encrypted_value: str
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if this secret has exceeded its TTL."""
        if self.ttl_seconds <= 0:
            return False
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return age > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Age of this secret in seconds."""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()


class SecretStore:
    """Key-value store for encrypted secrets.

    Stores secrets indexed by hierarchical paths (e.g., "fizzbuzz/rules/fizz_divisor").
    All values are "encrypted" using the military-grade double-base64 + XOR algorithm
    before storage. Multiple versions of each secret are retained because enterprise
    compliance demands a full audit trail of every time someone changed the number 3.
    """

    def __init__(self, master_key: bytes) -> None:
        self._master_key = master_key
        self._secrets: dict[str, SecretEntry] = {}
        self._version_history: dict[str, list[SecretEntry]] = {}

    def put(
        self,
        path: str,
        value: str,
        ttl_seconds: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SecretEntry:
        """Store a secret at the given path with military-grade encryption.

        Args:
            path: Hierarchical path for the secret.
            value: The plaintext value to encrypt and store.
            ttl_seconds: Time-to-live (0 = permanent).
            metadata: Optional metadata to attach.

        Returns:
            The created SecretEntry.
        """
        existing = self._secrets.get(path)
        version = (existing.version + 1) if existing else 1

        encrypted = MilitaryGradeEncryption.encrypt(value, self._master_key)

        entry = SecretEntry(
            path=path,
            encrypted_value=encrypted,
            version=version,
            ttl_seconds=ttl_seconds,
            metadata=metadata or {},
        )

        self._secrets[path] = entry

        if path not in self._version_history:
            self._version_history[path] = []
        self._version_history[path].append(entry)

        logger.debug("Stored secret at '%s' (version %d)", path, version)
        return entry

    def get(self, path: str) -> str:
        """Retrieve and decrypt a secret from the store.

        Args:
            path: The path of the secret to retrieve.

        Returns:
            The decrypted plaintext value.

        Raises:
            VaultSecretNotFoundError: If the path does not exist.
            VaultSecretExpiredError: If the secret has exceeded its TTL.
        """
        entry = self._secrets.get(path)
        if entry is None:
            raise VaultSecretNotFoundError(path)

        if entry.is_expired:
            raise VaultSecretExpiredError(
                path, entry.ttl_seconds, entry.age_seconds
            )

        return MilitaryGradeEncryption.decrypt(
            entry.encrypted_value, self._master_key
        )

    def delete(self, path: str) -> bool:
        """Delete a secret from the store.

        Returns True if the secret existed and was deleted.
        """
        if path in self._secrets:
            del self._secrets[path]
            return True
        return False

    def list_paths(self, prefix: str = "") -> list[str]:
        """List all secret paths, optionally filtered by prefix."""
        return [
            path for path in sorted(self._secrets.keys())
            if path.startswith(prefix)
        ]

    def get_entry(self, path: str) -> Optional[SecretEntry]:
        """Get the raw SecretEntry without decryption."""
        return self._secrets.get(path)

    def get_version_count(self, path: str) -> int:
        """Get the number of versions for a secret."""
        return len(self._version_history.get(path, []))

    @property
    def total_secrets(self) -> int:
        """Total number of secrets currently stored."""
        return len(self._secrets)

    @property
    def total_versions(self) -> int:
        """Total number of secret versions across all paths."""
        return sum(len(v) for v in self._version_history.values())


class VaultSealManager:
    """Manages the seal/unseal lifecycle of the vault.

    The vault starts in a SEALED state. To unseal it, a quorum of
    Shamir's Secret Sharing key holders must submit their shares.
    Once the threshold is met, the master key is reconstructed via
    Lagrange interpolation and the vault transitions to UNSEALED.

    Sealing the vault zeroes out the master key from memory, ensuring
    that even if an attacker gains access to the process's address
    space, they cannot read the FizzBuzz divisors. Which is clearly
    the most important security property of any application.
    """

    def __init__(
        self,
        shamir: ShamirSecretSharing,
        event_bus: Any = None,
    ) -> None:
        self._shamir = shamir
        self._event_bus = event_bus
        self._sealed = True
        self._master_key: Optional[int] = None
        self._submitted_shares: list[UnsealShare] = []
        self._all_shares: list[UnsealShare] = []
        self._initialized = False
        self._unseal_count = 0
        self._seal_count = 0

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def shares_submitted(self) -> int:
        return len(self._submitted_shares)

    @property
    def shares_required(self) -> int:
        return self._shamir.threshold

    @property
    def shares_remaining(self) -> int:
        return max(0, self._shamir.threshold - len(self._submitted_shares))

    def initialize(self) -> list[UnsealShare]:
        """Initialize the vault by generating a master key and splitting it.

        Generates a cryptographically random master key, splits it using
        Shamir's Secret Sharing, and returns the shares to the caller.
        The vault starts sealed; shares must be submitted to unseal.

        Returns:
            List of UnsealShare objects (one per key holder).

        Raises:
            VaultAlreadyInitializedError: If the vault was already initialized.
        """
        if self._initialized:
            raise VaultAlreadyInitializedError()

        # Generate a random master key
        self._master_key = secrets.randbelow(self._shamir.prime - 1) + 1

        # Split the master key into shares
        self._all_shares = self._shamir.split(self._master_key)
        self._initialized = True

        # Immediately seal (zero out master key in memory)
        master_key_backup = self._master_key
        self._master_key = None
        self._sealed = True

        self._emit_event(EventType.VAULT_INITIALIZED, {
            "num_shares": self._shamir.num_shares,
            "threshold": self._shamir.threshold,
            "prime_bits": 127,
        })

        logger.info(
            "Vault initialized: %d shares generated, %d required to unseal",
            self._shamir.num_shares,
            self._shamir.threshold,
        )

        return list(self._all_shares)

    def submit_unseal_share(self, share: UnsealShare) -> bool:
        """Submit an unseal share toward the quorum.

        If this share brings the total to the threshold, the vault
        is automatically unsealed via Lagrange interpolation.

        Args:
            share: An UnsealShare from the initialization ceremony.

        Returns:
            True if the vault is now unsealed, False if more shares needed.

        Raises:
            VaultUnsealError: If the share is invalid or already submitted.
        """
        if not self._sealed:
            raise VaultUnsealError("Vault is already unsealed.")

        # Check for duplicate submission
        if any(s.index == share.index for s in self._submitted_shares):
            raise VaultUnsealError(
                f"Share with index {share.index} has already been submitted. "
                f"Duplicate shares do not count toward the quorum."
            )

        self._submitted_shares.append(share)

        self._emit_event(EventType.VAULT_UNSEAL_SHARE_SUBMITTED, {
            "share_index": share.index,
            "shares_submitted": len(self._submitted_shares),
            "shares_required": self._shamir.threshold,
        })

        logger.info(
            "Unseal share %d submitted (%d/%d)",
            share.index,
            len(self._submitted_shares),
            self._shamir.threshold,
        )

        if len(self._submitted_shares) >= self._shamir.threshold:
            return self._unseal()

        return False

    def _unseal(self) -> bool:
        """Reconstruct the master key and unseal the vault."""
        try:
            self._master_key = self._shamir.reconstruct(self._submitted_shares)
            self._sealed = False
            self._unseal_count += 1

            self._emit_event(EventType.VAULT_UNSEALED, {
                "unseal_count": self._unseal_count,
                "shares_used": len(self._submitted_shares),
            })

            logger.info("Vault UNSEALED successfully (unseal #%d)", self._unseal_count)
            return True

        except ShamirReconstructionError:
            self._submitted_shares.clear()
            raise VaultUnsealError(
                "Lagrange interpolation failed. The submitted shares may be "
                "corrupted or from different initialization ceremonies. "
                "All submitted shares have been cleared."
            )

    def seal(self) -> None:
        """Seal the vault, zeroing out the master key.

        Once sealed, no secret operations are possible until a new
        quorum of unseal shares is submitted. The master key is
        overwritten with None, which Python's garbage collector will
        eventually reclaim — but we feel better about it.
        """
        self._master_key = None
        self._sealed = True
        self._submitted_shares.clear()
        self._seal_count += 1

        self._emit_event(EventType.VAULT_SEALED, {
            "seal_count": self._seal_count,
        })

        logger.info("Vault SEALED (seal #%d)", self._seal_count)

    def get_master_key_bytes(self) -> bytes:
        """Get the master key as bytes for encryption operations.

        Raises:
            VaultSealedError: If the vault is sealed.
        """
        if self._sealed or self._master_key is None:
            raise VaultSealedError()
        # Convert the integer master key to bytes
        byte_length = (self._master_key.bit_length() + 7) // 8
        return self._master_key.to_bytes(max(byte_length, 1), byteorder="big")

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event if an event bus is available."""
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="VaultSealManager",
            ))


class DynamicSecretEngine:
    """Engine for generating ephemeral secrets with automatic expiration.

    In real vault systems, dynamic secrets are generated on-demand with
    a TTL, providing short-lived credentials that automatically expire.
    Here, we generate short-lived FizzBuzz configuration values that
    automatically expire, which is equally important in the enterprise
    FizzBuzz threat model.
    """

    def __init__(self, secret_store: SecretStore) -> None:
        self._store = secret_store
        self._generated_count = 0

    def generate(
        self,
        path: str,
        generator: Callable[[], str],
        ttl_seconds: float = 60.0,
    ) -> str:
        """Generate a dynamic secret with a TTL.

        Args:
            path: The path to store the secret under.
            generator: A callable that produces the secret value.
            ttl_seconds: How long the secret is valid.

        Returns:
            The generated secret value.
        """
        value = generator()
        self._store.put(path, value, ttl_seconds=ttl_seconds, metadata={
            "dynamic": True,
            "generator": generator.__name__ if hasattr(generator, "__name__") else "anonymous",
        })
        self._generated_count += 1

        logger.debug(
            "Generated dynamic secret at '%s' with TTL=%ds",
            path, ttl_seconds,
        )

        return value

    @property
    def generated_count(self) -> int:
        return self._generated_count


class SecretRotationScheduler:
    """Scheduler for automatic secret rotation.

    Automatically rotates configured secrets at specified intervals,
    because the FizzBuzz blockchain mining difficulty of 2 must be
    periodically changed to... a different value of 2. Security through
    rotation: because if you change your secrets often enough, nobody
    can remember what they were in the first place.
    """

    def __init__(
        self,
        secret_store: SecretStore,
        rotatable_paths: list[str],
        interval_evaluations: int = 50,
        event_bus: Any = None,
    ) -> None:
        self._store = secret_store
        self._rotatable_paths = rotatable_paths
        self._interval = interval_evaluations
        self._event_bus = event_bus
        self._evaluation_count = 0
        self._rotation_count = 0
        self._rotation_generators: dict[str, Callable[[], str]] = {}

    def register_generator(self, path: str, generator: Callable[[], str]) -> None:
        """Register a rotation generator for a secret path."""
        self._rotation_generators[path] = generator

    def tick(self) -> list[str]:
        """Called after each evaluation. Rotates secrets if interval is reached.

        Returns:
            List of paths that were rotated.
        """
        self._evaluation_count += 1

        if self._evaluation_count % self._interval != 0:
            return []

        rotated = []
        for path in self._rotatable_paths:
            generator = self._rotation_generators.get(path)
            if generator is None:
                continue

            try:
                new_value = generator()
                self._store.put(path, new_value, metadata={
                    "rotated": True,
                    "rotation_number": self._rotation_count + 1,
                })
                rotated.append(path)

                if self._event_bus is not None:
                    from enterprise_fizzbuzz.domain.models import Event
                    self._event_bus.publish(Event(
                        event_type=EventType.VAULT_SECRET_ROTATED,
                        payload={
                            "path": path,
                            "rotation_number": self._rotation_count + 1,
                        },
                        source="SecretRotationScheduler",
                    ))

            except Exception as e:
                logger.warning("Secret rotation failed for '%s': %s", path, e)

        if rotated:
            self._rotation_count += 1
            logger.info(
                "Rotation #%d: rotated %d secrets",
                self._rotation_count, len(rotated),
            )

        return rotated

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    @property
    def rotation_count(self) -> int:
        return self._rotation_count


@dataclass
class VaultAuditEntry:
    """A single entry in the vault's append-only audit log.

    Every secret access, modification, and policy decision is recorded
    here for compliance purposes. The audit log is append-only because
    tampering with vault audit logs is the information security
    equivalent of a war crime.

    Attributes:
        timestamp: When the event occurred (UTC).
        operation: The operation performed (read, write, delete, etc.).
        path: The secret path accessed.
        component: The component that performed the operation.
        success: Whether the operation succeeded.
        details: Additional details about the operation.
        entry_id: Unique identifier for this audit entry.
    """

    timestamp: datetime
    operation: str
    path: str
    component: str
    success: bool
    details: str = ""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])


class VaultAuditLog:
    """Append-only audit log for all vault operations.

    Records every access attempt — successful or not — to the vault's
    secrets. The log is truly append-only: entries cannot be modified
    or deleted, because if the vault's audit log itself were mutable,
    the entire security model would collapse like a house of cards
    in a hurricane of FizzBuzz evaluations.
    """

    def __init__(self) -> None:
        self._entries: list[VaultAuditEntry] = []

    def record(
        self,
        operation: str,
        path: str,
        component: str,
        success: bool,
        details: str = "",
    ) -> VaultAuditEntry:
        """Record an audit entry. This is append-only — no deletions allowed."""
        entry = VaultAuditEntry(
            timestamp=datetime.now(timezone.utc),
            operation=operation,
            path=path,
            component=component,
            success=success,
            details=details,
        )
        self._entries.append(entry)
        return entry

    def get_entries(
        self,
        path: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> list[VaultAuditEntry]:
        """Query audit entries with optional filters."""
        filtered = self._entries
        if path is not None:
            filtered = [e for e in filtered if e.path == path]
        if operation is not None:
            filtered = [e for e in filtered if e.operation == operation]
        return filtered[-limit:]

    @property
    def total_entries(self) -> int:
        return len(self._entries)

    @property
    def denied_count(self) -> int:
        return sum(1 for e in self._entries if not e.success)

    @property
    def granted_count(self) -> int:
        return sum(1 for e in self._entries if e.success)


class VaultAccessPolicy:
    """Per-path access control policy for vault secrets.

    Determines which components are allowed to access which secrets
    and what operations they can perform. Because in enterprise
    FizzBuzz, the rule engine should not be able to read the
    blockchain's mining difficulty, and the ML engine should not
    be able to modify the cache TTL. Separation of concerns,
    taken to its logical extreme.
    """

    def __init__(self, policies: dict[str, Any]) -> None:
        self._policies = policies

    def check_access(
        self,
        path: str,
        component: str,
        operation: str = "read",
    ) -> bool:
        """Check if a component is allowed to perform an operation on a path.

        Uses glob-style matching on paths: "fizzbuzz/rules/*" matches
        "fizzbuzz/rules/fizz_divisor" and "fizzbuzz/rules/buzz_divisor".

        Returns True if access is allowed, False otherwise.
        """
        for pattern, policy in self._policies.items():
            if self._path_matches(path, pattern):
                allowed_components = policy.get("allowed_components", [])
                allowed_operations = policy.get("operations", ["read"])

                if component in allowed_components and operation in allowed_operations:
                    return True
                # If a matching policy denies access, don't check further
                if component not in allowed_components:
                    return False

        # Default: allow if no policy matches (permissive fallback)
        return True

    @staticmethod
    def _path_matches(path: str, pattern: str) -> bool:
        """Simple glob-style path matching.

        Supports:
        - Exact match: "fizzbuzz/rules/fizz" matches "fizzbuzz/rules/fizz"
        - Wildcard suffix: "fizzbuzz/rules/*" matches "fizzbuzz/rules/anything"
        """
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return path == prefix or path.startswith(prefix + "/")
        return path == pattern


@dataclass
class SecretScanFinding:
    """A single finding from the AST-based secret scanner.

    Represents a potential secret that was found lurking in source code,
    masquerading as an innocent integer literal. Every integer is suspect.
    Every number is a potential configuration value that should have been
    stored in the vault instead of hardcoded in source.

    Attributes:
        file_path: The file containing the potential secret.
        line_number: The line number where the secret was found.
        column: The column number.
        value: The suspicious value.
        context: The surrounding code context.
        severity: How suspicious this finding is (always HIGH for integers).
    """

    file_path: str
    line_number: int
    column: int
    value: Any
    context: str = ""
    severity: str = "HIGH"


class SecretScanner:
    """AST-based secret scanner that flags ALL integer literals as potential secrets.

    Uses Python's Abstract Syntax Tree (AST) parser to walk source files
    and identify integer literals that could potentially be secrets that
    should be stored in the vault instead of hardcoded in source code.

    Applies a conservative detection policy where all integer literals
    are flagged as potential hardcoded secrets requiring review. This
    zero-tolerance approach ensures that no configuration value escapes
    the vault, enforcing the security principle that sensitive values
    should always be externalized into secure storage.
    """

    def __init__(
        self,
        flag_integers: bool = True,
        flag_strings: bool = False,
        min_integer_suspicion: int = 0,
    ) -> None:
        self._flag_integers = flag_integers
        self._flag_strings = flag_strings
        self._min_integer_suspicion = min_integer_suspicion

    def scan_file(self, file_path: str) -> list[SecretScanFinding]:
        """Scan a single Python file for potential secrets.

        Args:
            file_path: Path to the Python file to scan.

        Returns:
            List of SecretScanFinding objects.

        Raises:
            VaultScanError: If the file cannot be parsed.
        """
        findings: list[SecretScanFinding] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (IOError, OSError) as e:
            raise VaultScanError(file_path, str(e))

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            raise VaultScanError(file_path, f"Syntax error: {e}")

        for node in ast.walk(tree):
            if self._flag_integers and isinstance(node, ast.Constant):
                if isinstance(node.value, int) and not isinstance(node.value, bool):
                    if abs(node.value) >= self._min_integer_suspicion:
                        # Extract surrounding line for context
                        lines = source.split("\n")
                        line_idx = getattr(node, "lineno", 1) - 1
                        context_line = lines[line_idx].strip() if line_idx < len(lines) else ""

                        findings.append(SecretScanFinding(
                            file_path=file_path,
                            line_number=getattr(node, "lineno", 0),
                            column=getattr(node, "col_offset", 0),
                            value=node.value,
                            context=context_line,
                            severity=self._classify_severity(node.value),
                        ))

        return findings

    def scan_directory(self, directory: str) -> list[SecretScanFinding]:
        """Scan all Python files in a directory for potential secrets.

        Returns:
            Aggregated list of findings across all files.
        """
        all_findings: list[SecretScanFinding] = []
        dir_path = Path(directory)

        if not dir_path.exists():
            return all_findings

        for py_file in sorted(dir_path.rglob("*.py")):
            try:
                file_findings = self.scan_file(str(py_file))
                all_findings.extend(file_findings)
            except VaultScanError:
                # Skip files that can't be parsed
                continue

        return all_findings

    @staticmethod
    def _classify_severity(value: int) -> str:
        """Classify the severity of a suspicious integer literal.

        All integers are suspicious, but some are more suspicious than
        others. The numbers 3, 5, and 15 are CRITICAL because they
        are the holy trinity of FizzBuzz divisors. Other numbers are
        merely HIGH priority, because they might be divisors in
        someone else's FizzBuzz implementation.
        """
        if value in (3, 5, 15):
            return "CRITICAL"
        if value in (0, 1, 2):
            return "MEDIUM"
        return "HIGH"


class VaultDashboard:
    """ASCII dashboard renderer for the Secrets Management Vault.

    Renders a comprehensive dashboard showing vault status, seal state,
    secret inventory, rotation history, audit log statistics, and
    scanner findings — all in beautiful ASCII art that would make any
    terminal-based UI engineer weep with pride.
    """

    @staticmethod
    def render(
        seal_manager: VaultSealManager,
        secret_store: Optional[SecretStore] = None,
        audit_log: Optional[VaultAuditLog] = None,
        rotation_scheduler: Optional[SecretRotationScheduler] = None,
        scan_findings: Optional[list[SecretScanFinding]] = None,
        width: int = 60,
    ) -> str:
        """Render the complete vault dashboard."""
        lines: list[str] = []
        inner = width - 4

        # Header
        lines.append(f"  +{'=' * (inner + 2)}+")
        lines.append(f"  |{'SECRETS MANAGEMENT VAULT':^{inner + 2}}|")
        shamir_label = "with Shamir's Secret Sharing"
        lines.append(f"  |{shamir_label:^{inner + 2}}|")
        lines.append(f"  +{'=' * (inner + 2)}+")

        # Seal status
        seal_status = "SEALED" if seal_manager.is_sealed else "UNSEALED"
        seal_icon = "[X]" if seal_manager.is_sealed else "[O]"
        init_status = "YES" if seal_manager.is_initialized else "NO"

        lines.append(f"  | {'Vault Status:':<{inner // 2}}{seal_icon + ' ' + seal_status:>{inner // 2 + 2}}|")
        lines.append(f"  | {'Initialized:':<{inner // 2}}{init_status:>{inner // 2 + 2}}|")
        lines.append(f"  | {'Shares Required:':<{inner // 2}}{seal_manager.shares_required:>{inner // 2 + 2}}|")
        lines.append(f"  | {'Shares Submitted:':<{inner // 2}}{seal_manager.shares_submitted:>{inner // 2 + 2}}|")
        lines.append(f"  | {'Shares Remaining:':<{inner // 2}}{seal_manager.shares_remaining:>{inner // 2 + 2}}|")
        lines.append(f"  +{'-' * (inner + 2)}+")

        # Secret store stats
        if secret_store is not None and not seal_manager.is_sealed:
            lines.append(f"  | {'SECRET STORE':^{inner + 2}}|")
            lines.append(f"  +{'-' * (inner + 2)}+")
            lines.append(f"  | {'Total Secrets:':<{inner // 2}}{secret_store.total_secrets:>{inner // 2 + 2}}|")
            lines.append(f"  | {'Total Versions:':<{inner // 2}}{secret_store.total_versions:>{inner // 2 + 2}}|")

            paths = secret_store.list_paths()
            if paths:
                lines.append(f"  +{'-' * (inner + 2)}+")
                lines.append(f"  | {'Stored Secrets:':<{inner + 2}}|")
                for path in paths[:10]:
                    entry = secret_store.get_entry(path)
                    ver = f"v{entry.version}" if entry else "v?"
                    display = f"  {path} ({ver})"
                    lines.append(f"  | {display:<{inner + 2}}|")
                if len(paths) > 10:
                    lines.append(f"  | {'  ... and ' + str(len(paths) - 10) + ' more':<{inner + 2}}|")

            lines.append(f"  +{'-' * (inner + 2)}+")

        # Audit log stats
        if audit_log is not None:
            lines.append(f"  | {'AUDIT LOG':^{inner + 2}}|")
            lines.append(f"  +{'-' * (inner + 2)}+")
            lines.append(f"  | {'Total Entries:':<{inner // 2}}{audit_log.total_entries:>{inner // 2 + 2}}|")
            lines.append(f"  | {'Access Granted:':<{inner // 2}}{audit_log.granted_count:>{inner // 2 + 2}}|")
            lines.append(f"  | {'Access Denied:':<{inner // 2}}{audit_log.denied_count:>{inner // 2 + 2}}|")
            lines.append(f"  +{'-' * (inner + 2)}+")

        # Rotation stats
        if rotation_scheduler is not None:
            lines.append(f"  | {'SECRET ROTATION':^{inner + 2}}|")
            lines.append(f"  +{'-' * (inner + 2)}+")
            lines.append(f"  | {'Evaluations:':<{inner // 2}}{rotation_scheduler.evaluation_count:>{inner // 2 + 2}}|")
            lines.append(f"  | {'Rotations:':<{inner // 2}}{rotation_scheduler.rotation_count:>{inner // 2 + 2}}|")
            lines.append(f"  +{'-' * (inner + 2)}+")

        # Scan findings summary
        if scan_findings is not None:
            critical = sum(1 for f in scan_findings if f.severity == "CRITICAL")
            high = sum(1 for f in scan_findings if f.severity == "HIGH")
            medium = sum(1 for f in scan_findings if f.severity == "MEDIUM")

            lines.append(f"  | {'SECRET SCAN FINDINGS':^{inner + 2}}|")
            lines.append(f"  +{'-' * (inner + 2)}+")
            lines.append(f"  | {'Total Findings:':<{inner // 2}}{len(scan_findings):>{inner // 2 + 2}}|")
            lines.append(f"  | {'CRITICAL:':<{inner // 2}}{critical:>{inner // 2 + 2}}|")
            lines.append(f"  | {'HIGH:':<{inner // 2}}{high:>{inner // 2 + 2}}|")
            lines.append(f"  | {'MEDIUM:':<{inner // 2}}{medium:>{inner // 2 + 2}}|")

            if scan_findings:
                lines.append(f"  +{'-' * (inner + 2)}+")
                lines.append(f"  | {'Top Findings:':<{inner + 2}}|")
                for finding in scan_findings[:5]:
                    short_path = Path(finding.file_path).name
                    detail = f"  [{finding.severity}] {short_path}:{finding.line_number} = {finding.value}"
                    if len(detail) > inner + 2:
                        detail = detail[:inner - 1] + "..."
                    lines.append(f"  | {detail:<{inner + 2}}|")
                if len(scan_findings) > 5:
                    lines.append(f"  | {'  ... and ' + str(len(scan_findings) - 5) + ' more leaked integers':<{inner + 2}}|")

            lines.append(f"  +{'-' * (inner + 2)}+")

        # Encryption notice
        lines.append(f"  | {'Encryption: Military-Grade Double-Base64 + XOR':^{inner + 2}}|")
        lines.append(f"  | {'Actual Security: Approximately Zero':^{inner + 2}}|")
        lines.append(f"  +{'=' * (inner + 2)}+")

        return "\n".join(lines)

    @staticmethod
    def render_scan_report(
        findings: list[SecretScanFinding],
        width: int = 60,
    ) -> str:
        """Render a detailed scan report."""
        lines: list[str] = []
        inner = width - 4

        lines.append(f"  +{'=' * (inner + 2)}+")
        lines.append(f"  |{'SECRET SCANNER REPORT':^{inner + 2}}|")
        lines.append(f"  |{'Every Integer is a Potential Secret':^{inner + 2}}|")
        lines.append(f"  +{'=' * (inner + 2)}+")

        if not findings:
            lines.append(f"  | {'No integer literals found. The code is pure.':^{inner + 2}}|")
            lines.append(f"  | {'(This is suspicious in itself.)':^{inner + 2}}|")
        else:
            lines.append(f"  | {'Total potential secrets found:':<{inner // 2}}{len(findings):>{inner // 2 + 2}}|")
            lines.append(f"  +{'-' * (inner + 2)}+")

            # Group by file
            by_file: dict[str, list[SecretScanFinding]] = {}
            for f in findings:
                fname = Path(f.file_path).name
                by_file.setdefault(fname, []).append(f)

            for fname, file_findings in list(by_file.items())[:10]:
                lines.append(f"  | {fname + ':':^{inner + 2}}|")
                for ff in file_findings[:3]:
                    detail = f"    L{ff.line_number}: {ff.value} [{ff.severity}]"
                    if len(detail) > inner + 2:
                        detail = detail[:inner - 1] + "..."
                    lines.append(f"  | {detail:<{inner + 2}}|")
                if len(file_findings) > 3:
                    lines.append(f"  | {'    ... and ' + str(len(file_findings) - 3) + ' more':<{inner + 2}}|")

        lines.append(f"  +{'=' * (inner + 2)}+")
        return "\n".join(lines)


class VaultMiddleware(IMiddleware):
    """Middleware that integrates the Secrets Management Vault into the pipeline.

    Intercepts each FizzBuzz evaluation to:
    1. Check that the vault is unsealed (warn if sealed)
    2. Record vault access in the audit log
    3. Tick the rotation scheduler
    4. Attach vault metadata to the processing context

    Priority 10 ensures this runs after validation but before
    most other middleware, because security should come early
    in the pipeline (right after we've verified the number is
    actually a number).
    """

    def __init__(
        self,
        seal_manager: VaultSealManager,
        secret_store: Optional[SecretStore] = None,
        audit_log: Optional[VaultAuditLog] = None,
        rotation_scheduler: Optional[SecretRotationScheduler] = None,
        event_bus: Any = None,
    ) -> None:
        self._seal_manager = seal_manager
        self._secret_store = secret_store
        self._audit_log = audit_log
        self._rotation_scheduler = rotation_scheduler
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context through the vault middleware."""
        # Record the access attempt
        if self._audit_log is not None:
            self._audit_log.record(
                operation="evaluate",
                path=f"fizzbuzz/evaluation/{context.number}",
                component="middleware_pipeline",
                success=not self._seal_manager.is_sealed,
                details=f"Number {context.number} evaluation",
            )

        # Tick the rotation scheduler
        if self._rotation_scheduler is not None and not self._seal_manager.is_sealed:
            rotated = self._rotation_scheduler.tick()
            if rotated:
                context.metadata["vault_rotated_secrets"] = rotated

        # Add vault metadata
        context.metadata["vault_sealed"] = self._seal_manager.is_sealed
        context.metadata["vault_initialized"] = self._seal_manager.is_initialized

        return next_handler(context)

    def get_name(self) -> str:
        return "VaultMiddleware"

    def get_priority(self) -> int:
        return 10

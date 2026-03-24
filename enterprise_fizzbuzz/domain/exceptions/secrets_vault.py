"""
Enterprise FizzBuzz Platform - Secrets Management Vault Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class VaultError(FizzBuzzError):
    """Base exception for all Secrets Management Vault errors.

    When your vault for storing the modulo divisor "3" encounters
    a failure, you must confront the uncomfortable truth that you've
    built a HashiCorp Vault clone for an application whose most
    sensitive data is the number five. But security is non-negotiable,
    and these exceptions ensure that every vault failure is documented
    with the same rigor as a real secrets management incident.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-VT00"),
            context=kwargs.pop("context", {}),
        )


class VaultSealedError(VaultError):
    """Raised when an operation is attempted on a sealed vault.

    The vault is sealed. It cannot read secrets, write secrets, or
    perform any useful function whatsoever until it receives 3 of
    the 5 Shamir's Secret Sharing unseal shares. This is exactly
    how HashiCorp Vault works, and if it's good enough for Fortune
    500 companies' actual secrets, it's certainly good enough for
    the number 3.
    """

    def __init__(self) -> None:
        super().__init__(
            "The vault is SEALED. Operations require 3-of-5 unseal shares "
            "to be submitted before the vault can serve requests. The "
            "FizzBuzz divisors remain locked behind military-grade Shamir's "
            "Secret Sharing until sufficient key holders convene.",
            error_code="EFP-VT01",
        )


class VaultUnsealError(VaultError):
    """Raised when the unseal process encounters an error.

    The vault attempted to unseal but something went wrong.
    Perhaps the share was invalid, perhaps the threshold wasn't
    met, or perhaps the Lagrange interpolation encountered a
    mathematical impossibility (unlikely but documented).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Vault unseal failed: {reason}. The vault remains sealed "
            f"and the FizzBuzz secrets remain imprisoned. Better luck "
            f"next time.",
            error_code="EFP-VT02",
            context={"reason": reason},
        )


class VaultSecretNotFoundError(VaultError):
    """Raised when a requested secret does not exist in the vault.

    The secret you asked for is not in the vault. Perhaps it was
    never stored, perhaps it was rotated out of existence, or
    perhaps it fled the vault of its own volition. Secrets are
    like that sometimes.
    """

    def __init__(self, path: str) -> None:
        super().__init__(
            f"Secret at path '{path}' not found in the vault. "
            f"The vault has been thoroughly searched and the secret "
            f"is not here. It was last seen... actually, we have no "
            f"idea where it went.",
            error_code="EFP-VT03",
            context={"path": path},
        )
        self.path = path


class VaultAccessDeniedError(VaultError):
    """Raised when access to a secret is denied by the access policy.

    Your component does not have permission to access this secret.
    The vault's access control policy has determined that you are
    not worthy of knowing the FizzBuzz divisor at this path. Please
    submit a 27-page access request form to the Chief Vault
    Administrator (Bob McFizzington, currently unavailable).
    """

    def __init__(self, path: str, component: str) -> None:
        super().__init__(
            f"Access denied: component '{component}' is not authorized "
            f"to access secret at path '{path}'. The vault's access "
            f"control policy is absolute and unyielding, like a bouncer "
            f"at an exclusive nightclub for integers.",
            error_code="EFP-VT04",
            context={"path": path, "component": component},
        )


class VaultEncryptionError(VaultError):
    """Raised when the military-grade encryption subsystem fails.

    The double-base64 + XOR "encryption" algorithm has encountered
    an error. This is technically impossible since base64 encoding
    always succeeds, but enterprise software must be prepared for
    all contingencies, including the heat death of the universe
    mid-encoding.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Military-grade encryption {operation} failed: {reason}. "
            f"The secret remains in its pre-encryption state, which is "
            f"to say, completely readable by anyone with access to RAM.",
            error_code="EFP-VT05",
            context={"operation": operation, "reason": reason},
        )


class VaultRotationError(VaultError):
    """Raised when automatic secret rotation fails.

    The secret rotation scheduler attempted to rotate a secret
    but encountered an error. The old secret remains in place,
    which is fine because the secret was just a configuration
    value that anyone could read from config.yaml anyway.
    """

    def __init__(self, secret_path: str, reason: str) -> None:
        super().__init__(
            f"Secret rotation failed for '{secret_path}': {reason}. "
            f"The secret will retain its previous value, which was "
            f"never actually secret to begin with.",
            error_code="EFP-VT06",
            context={"secret_path": secret_path, "reason": reason},
        )


class ShamirReconstructionError(VaultError):
    """Raised when Shamir's Secret Sharing reconstruction fails.

    The Lagrange interpolation over GF(2^127-1) could not reconstruct
    the master secret from the provided shares. This means either
    the shares are corrupted, insufficient shares were provided, or
    someone substituted fake shares in an attempt to breach the vault.
    Mathematics does not lie, and the polynomial says: access denied.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Shamir's Secret Sharing reconstruction failed: {reason}. "
            f"The polynomial interpolation did not converge to a valid "
            f"master secret. Please verify your unseal shares and try "
            f"again with the appropriate quorum.",
            error_code="EFP-VT07",
            context={"reason": reason},
        )


class VaultSecretExpiredError(VaultError):
    """Raised when an ephemeral dynamic secret has expired.

    This secret had a TTL, and that TTL has expired. The secret
    lived a full life — brief though it was — serving faithfully
    as a configuration value that nobody checked the expiration
    of until just now.
    """

    def __init__(self, path: str, ttl_seconds: float, age_seconds: float) -> None:
        super().__init__(
            f"Dynamic secret at '{path}' has expired: age={age_seconds:.2f}s, "
            f"TTL={ttl_seconds:.2f}s. The secret has passed beyond the veil "
            f"of time-to-live and can no longer be retrieved.",
            error_code="EFP-VT08",
            context={"path": path, "ttl_seconds": ttl_seconds, "age_seconds": age_seconds},
        )


class VaultScanError(VaultError):
    """Raised when the AST-based secret scanner encounters an error.

    The secret scanner, which flags all integer literals as potential
    leaked secrets per the zero-trust numerics policy, has encountered
    a problem during its analysis pass.
    """

    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(
            f"Secret scan error in '{file_path}': {reason}. "
            f"The scanner was unable to complete its paranoid analysis "
            f"of this file. Some integer literals may have escaped "
            f"classification as potential secrets.",
            error_code="EFP-VT09",
            context={"file_path": file_path, "reason": reason},
        )


class VaultAlreadyInitializedError(VaultError):
    """Raised when attempting to initialize a vault that already exists.

    The vault has already been initialized with Shamir's Secret
    Sharing. Re-initializing would destroy the existing shares
    and render the vault permanently sealed with no way to unseal
    it. This is the vault equivalent of changing the locks and
    throwing away all the keys.
    """

    def __init__(self) -> None:
        super().__init__(
            "The vault has already been initialized. Re-initialization "
            "is forbidden because it would destroy the existing Shamir "
            "shares and brick the vault faster than you can say "
            "'split the polynomial.'",
            error_code="EFP-VT10",
        )


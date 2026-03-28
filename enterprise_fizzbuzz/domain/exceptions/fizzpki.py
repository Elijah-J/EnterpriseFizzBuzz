"""Enterprise FizzBuzz Platform - FizzPKI Errors (EFP-PKI00 .. EFP-PKI18)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzPKIError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzPKI error: {reason}", error_code="EFP-PKI00", context={"reason": reason})

class FizzPKIKeyGenerationError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Key generation: {reason}"); self.error_code = "EFP-PKI01"

class FizzPKICSRInvalidError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"CSR invalid: {reason}"); self.error_code = "EFP-PKI02"

class FizzPKICertificateError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Certificate: {reason}"); self.error_code = "EFP-PKI03"

class FizzPKICertificateExpiredError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Certificate expired: {reason}"); self.error_code = "EFP-PKI04"

class FizzPKICertificateRevokedError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Certificate revoked: {reason}"); self.error_code = "EFP-PKI05"

class FizzPKICertificateNotFoundError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Certificate not found: {reason}"); self.error_code = "EFP-PKI06"

class FizzPKICANotInitializedError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"CA not initialized: {reason}"); self.error_code = "EFP-PKI07"

class FizzPKICAChainError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"CA chain: {reason}"); self.error_code = "EFP-PKI08"

class FizzPKICRLError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"CRL: {reason}"); self.error_code = "EFP-PKI09"

class FizzPKIOCSPError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"OCSP: {reason}"); self.error_code = "EFP-PKI10"

class FizzPKIACMEError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"ACME: {reason}"); self.error_code = "EFP-PKI11"

class FizzPKIACMEChallengeError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"ACME challenge: {reason}"); self.error_code = "EFP-PKI12"

class FizzPKIACMEOrderError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"ACME order: {reason}"); self.error_code = "EFP-PKI13"

class FizzPKITransparencyError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Transparency: {reason}"); self.error_code = "EFP-PKI14"

class FizzPKIRenewalError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Renewal: {reason}"); self.error_code = "EFP-PKI15"

class FizzPKIInventoryError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Inventory: {reason}"); self.error_code = "EFP-PKI16"

class FizzPKIVaultIntegrationError(FizzPKIError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Vault integration: {reason}"); self.error_code = "EFP-PKI17"

class FizzPKIConfigError(FizzPKIError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-PKI18"

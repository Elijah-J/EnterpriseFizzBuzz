"""Enterprise FizzBuzz Platform - FizzTLS Errors"""
from __future__ import annotations
from ._base import FizzBuzzError
class FizzTLSError(FizzBuzzError):
    def __init__(self, r: str) -> None:
        super().__init__(f"FizzTLS: {r}", error_code="EFP-TLS00", context={"reason": r})
class FizzTLSNotFoundError(FizzTLSError):
    def __init__(self, s: str) -> None: super().__init__(f"Not found: {s}"); self.error_code="EFP-TLS01"
class FizzTLSHandshakeError(FizzTLSError):
    def __init__(self, r: str) -> None: super().__init__(f"Handshake failed: {r}"); self.error_code="EFP-TLS02"
class FizzTLSCertificateError(FizzTLSError):
    def __init__(self, r: str) -> None: super().__init__(f"Certificate error: {r}"); self.error_code="EFP-TLS03"

"""Enterprise FizzBuzz Platform - FizzAuth2 OAuth 2.0/OIDC Errors (EFP-AUTH2-00 .. EFP-AUTH2-20)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzAuth2Error(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzAuth2 error: {reason}", error_code="EFP-AUTH2-00", context={"reason": reason})

class FizzAuth2InvalidClientError(FizzAuth2Error):
    def __init__(self, client_id: str) -> None:
        super().__init__(f"Invalid client: {client_id}"); self.error_code = "EFP-AUTH2-01"

class FizzAuth2UnauthorizedClientError(FizzAuth2Error):
    def __init__(self, client_id: str, grant: str) -> None:
        super().__init__(f"Client {client_id} not authorized for grant {grant}"); self.error_code = "EFP-AUTH2-02"

class FizzAuth2InvalidGrantError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid grant: {reason}"); self.error_code = "EFP-AUTH2-03"

class FizzAuth2InvalidScopeError(FizzAuth2Error):
    def __init__(self, scope: str) -> None:
        super().__init__(f"Invalid scope: {scope}"); self.error_code = "EFP-AUTH2-04"

class FizzAuth2InvalidRedirectError(FizzAuth2Error):
    def __init__(self, uri: str) -> None:
        super().__init__(f"Invalid redirect URI: {uri}"); self.error_code = "EFP-AUTH2-05"

class FizzAuth2AuthCodeExpiredError(FizzAuth2Error):
    def __init__(self, code: str) -> None:
        super().__init__(f"Authorization code expired: {code}"); self.error_code = "EFP-AUTH2-06"

class FizzAuth2AuthCodeUsedError(FizzAuth2Error):
    def __init__(self, code: str) -> None:
        super().__init__(f"Authorization code already used: {code}"); self.error_code = "EFP-AUTH2-07"

class FizzAuth2PKCEError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"PKCE verification failed: {reason}"); self.error_code = "EFP-AUTH2-08"

class FizzAuth2TokenExpiredError(FizzAuth2Error):
    def __init__(self, token_type: str) -> None:
        super().__init__(f"{token_type} token expired"); self.error_code = "EFP-AUTH2-09"

class FizzAuth2TokenRevokedError(FizzAuth2Error):
    def __init__(self, token_id: str) -> None:
        super().__init__(f"Token revoked: {token_id}"); self.error_code = "EFP-AUTH2-10"

class FizzAuth2TokenInvalidError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Invalid token: {reason}"); self.error_code = "EFP-AUTH2-11"

class FizzAuth2JWTError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"JWT error: {reason}"); self.error_code = "EFP-AUTH2-12"

class FizzAuth2JWKSError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"JWKS error: {reason}"); self.error_code = "EFP-AUTH2-13"

class FizzAuth2OIDCError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"OIDC error: {reason}"); self.error_code = "EFP-AUTH2-14"

class FizzAuth2ConsentError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Consent: {reason}"); self.error_code = "EFP-AUTH2-15"

class FizzAuth2SessionError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Session: {reason}"); self.error_code = "EFP-AUTH2-16"

class FizzAuth2DeviceAuthError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Device auth: {reason}"); self.error_code = "EFP-AUTH2-17"

class FizzAuth2DeviceCodeExpiredError(FizzAuth2Error):
    def __init__(self, device_code: str) -> None:
        super().__init__(f"Device code expired: {device_code}"); self.error_code = "EFP-AUTH2-18"

class FizzAuth2RegistrationError(FizzAuth2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Client registration: {reason}"); self.error_code = "EFP-AUTH2-19"

class FizzAuth2ConfigError(FizzAuth2Error):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-AUTH2-20"

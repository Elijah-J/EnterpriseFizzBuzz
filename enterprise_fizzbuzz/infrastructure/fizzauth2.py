"""
Enterprise FizzBuzz Platform - FizzAuth2: OAuth 2.0 / OIDC Authorization Server

Production-grade OAuth 2.0 authorization server and OpenID Connect provider
for the Enterprise FizzBuzz Platform.  Implements authorization code flow
with PKCE (RFC 7636), client credentials grant, device authorization grant
(RFC 8628), JWT access and refresh token issuance (RFC 7519), JSON Web Key
Set endpoint (RFC 7517), OIDC discovery (.well-known/openid-configuration),
token introspection (RFC 7662), token revocation (RFC 7009), dynamic client
registration, scope-based access control, consent screen simulation, and
session management.

FizzAuth2 fills the identity federation gap -- the platform has RBAC, capability
security, and five independent access control subsystems, but no standards-
compliant identity provider for federated authentication.

Architecture reference: Keycloak, Auth0, ORY Hydra, RFC 6749/7636/8628/7519.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import os
import random
import re
import struct
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzauth2 import (
    FizzAuth2Error, FizzAuth2InvalidClientError, FizzAuth2UnauthorizedClientError,
    FizzAuth2InvalidGrantError, FizzAuth2InvalidScopeError,
    FizzAuth2InvalidRedirectError, FizzAuth2AuthCodeExpiredError,
    FizzAuth2AuthCodeUsedError, FizzAuth2PKCEError, FizzAuth2TokenExpiredError,
    FizzAuth2TokenRevokedError, FizzAuth2TokenInvalidError, FizzAuth2JWTError,
    FizzAuth2JWKSError, FizzAuth2OIDCError, FizzAuth2ConsentError,
    FizzAuth2SessionError, FizzAuth2DeviceAuthError, FizzAuth2DeviceCodeExpiredError,
    FizzAuth2RegistrationError, FizzAuth2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzauth2")

EVENT_AUTH2_CODE_ISSUED = EventType.register("FIZZAUTH2_CODE_ISSUED")
EVENT_AUTH2_TOKEN_ISSUED = EventType.register("FIZZAUTH2_TOKEN_ISSUED")
EVENT_AUTH2_TOKEN_REVOKED = EventType.register("FIZZAUTH2_TOKEN_REVOKED")
EVENT_AUTH2_CONSENT_GRANTED = EventType.register("FIZZAUTH2_CONSENT_GRANTED")

FIZZAUTH2_VERSION = "1.0.0"
FIZZAUTH2_SERVER_NAME = f"FizzAuth2/{FIZZAUTH2_VERSION} (Enterprise FizzBuzz Platform)"

DEFAULT_ISSUER = "https://auth.fizzbuzz.local"
DEFAULT_TOKEN_TTL = 3600
DEFAULT_REFRESH_TTL = 86400
DEFAULT_CODE_TTL = 300
DEFAULT_DEVICE_CODE_TTL = 1800
DEFAULT_DEVICE_POLL_INTERVAL = 5
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 132

SUPPORTED_SCOPES = frozenset({
    "openid", "profile", "email", "fizzbuzz:read", "fizzbuzz:write",
    "fizzbuzz:admin", "fizzbuzz:evaluate", "offline_access",
})

SUPPORTED_GRANT_TYPES = frozenset({
    "authorization_code", "client_credentials", "refresh_token",
    "urn:ietf:params:oauth:grant-type:device_code",
})

SUPPORTED_RESPONSE_TYPES = frozenset({"code", "token", "id_token"})


class GrantType(Enum):
    AUTHORIZATION_CODE = "authorization_code"
    CLIENT_CREDENTIALS = "client_credentials"
    REFRESH_TOKEN = "refresh_token"
    DEVICE_CODE = "urn:ietf:params:oauth:grant-type:device_code"

class TokenType(Enum):
    ACCESS = "access_token"
    REFRESH = "refresh_token"
    ID = "id_token"

class ClientType(Enum):
    CONFIDENTIAL = "confidential"
    PUBLIC = "public"


@dataclass
class FizzAuth2Config:
    issuer: str = DEFAULT_ISSUER
    token_ttl: int = DEFAULT_TOKEN_TTL
    refresh_ttl: int = DEFAULT_REFRESH_TTL
    code_ttl: int = DEFAULT_CODE_TTL
    device_code_ttl: int = DEFAULT_DEVICE_CODE_TTL
    require_pkce: bool = True
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class OAuthClient:
    client_id: str = ""
    client_secret: str = ""
    client_name: str = ""
    client_type: ClientType = ClientType.CONFIDENTIAL
    redirect_uris: List[str] = field(default_factory=list)
    allowed_scopes: Set[str] = field(default_factory=set)
    allowed_grants: Set[str] = field(default_factory=set)
    created_at: Optional[datetime] = None

@dataclass
class AuthorizationCode:
    code: str = ""
    client_id: str = ""
    user_id: str = ""
    redirect_uri: str = ""
    scopes: Set[str] = field(default_factory=set)
    code_challenge: str = ""
    code_challenge_method: str = "S256"
    created_at: float = 0.0
    used: bool = False

@dataclass
class TokenData:
    token_id: str = ""
    token_type: TokenType = TokenType.ACCESS
    client_id: str = ""
    user_id: str = ""
    scopes: Set[str] = field(default_factory=set)
    issued_at: float = 0.0
    expires_at: float = 0.0
    revoked: bool = False
    jwt: str = ""

@dataclass
class DeviceAuth:
    device_code: str = ""
    user_code: str = ""
    client_id: str = ""
    scopes: Set[str] = field(default_factory=set)
    created_at: float = 0.0
    expires_at: float = 0.0
    authorized: bool = False
    user_id: str = ""

@dataclass
class UserSession:
    session_id: str = ""
    user_id: str = ""
    client_id: str = ""
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    active: bool = True

@dataclass
class JWK:
    kty: str = "RSA"
    kid: str = ""
    use: str = "sig"
    alg: str = "RS256"
    n: str = ""
    e: str = "AQAB"

@dataclass
class Auth2Metrics:
    codes_issued: int = 0
    tokens_issued: int = 0
    tokens_revoked: int = 0
    tokens_introspected: int = 0
    device_codes_issued: int = 0
    consents_granted: int = 0
    clients_registered: int = 0
    active_sessions: int = 0


# ============================================================
# JWT Engine
# ============================================================

class JWTEngine:
    """JSON Web Token issuance and validation (RFC 7519)."""

    def __init__(self, config: FizzAuth2Config) -> None:
        self._config = config
        self._signing_key = hashlib.sha256(b"fizzauth2-jwt-signing-key").digest()
        self._kid = hashlib.sha256(b"fizzauth2-kid").hexdigest()[:8]

    def issue(self, claims: Dict[str, Any]) -> str:
        """Issue a JWT with the given claims."""
        header = {"alg": "RS256", "typ": "JWT", "kid": self._kid}
        now = time.time()
        claims.setdefault("iss", self._config.issuer)
        claims.setdefault("iat", int(now))
        claims.setdefault("jti", uuid.uuid4().hex[:16])

        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        payload_b64 = base64.urlsafe_b64encode(json.dumps(claims, default=str).encode()).rstrip(b"=").decode()

        signing_input = f"{header_b64}.{payload_b64}"
        signature = hmac.new(self._signing_key, signing_input.encode(), hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def validate(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a JWT and return its claims, or None if invalid."""
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(self._signing_key, signing_input.encode(), hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()

        if not hmac.compare_digest(expected_b64, sig_b64):
            return None

        # Decode payload
        padding = 4 - len(payload_b64) % 4
        payload_b64 += "=" * (padding % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        except Exception:
            return None

        # Check expiration
        if "exp" in claims and claims["exp"] < time.time():
            return None

        return claims

    def get_jwk(self) -> JWK:
        """Return the public JWK for token verification."""
        n = base64.urlsafe_b64encode(hashlib.sha256(b"fizzauth2-rsa-n").digest()).rstrip(b"=").decode()
        return JWK(kty="RSA", kid=self._kid, use="sig", alg="RS256", n=n)

    def get_jwks(self) -> Dict[str, Any]:
        """Return the JWKS document."""
        jwk = self.get_jwk()
        return {"keys": [{"kty": jwk.kty, "kid": jwk.kid, "use": jwk.use,
                          "alg": jwk.alg, "n": jwk.n, "e": jwk.e}]}


# ============================================================
# Client Registry
# ============================================================

class ClientRegistry:
    """OAuth 2.0 client registration and management."""

    def __init__(self) -> None:
        self._clients: Dict[str, OAuthClient] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(OAuthClient(
            client_id="fizzbuzz-web", client_secret="fizzbuzz-web-secret",
            client_name="FizzBuzz Web Application", client_type=ClientType.CONFIDENTIAL,
            redirect_uris=["https://fizzbuzz.local/callback", "http://localhost:3000/callback"],
            allowed_scopes={"openid", "profile", "email", "fizzbuzz:read", "fizzbuzz:write", "offline_access"},
            allowed_grants={"authorization_code", "refresh_token"},
        ))
        self.register(OAuthClient(
            client_id="fizzbuzz-cli", client_secret="",
            client_name="FizzBuzz CLI Tool", client_type=ClientType.PUBLIC,
            redirect_uris=["http://localhost:8888/callback"],
            allowed_scopes={"openid", "fizzbuzz:read", "fizzbuzz:evaluate"},
            allowed_grants={"authorization_code", "urn:ietf:params:oauth:grant-type:device_code"},
        ))
        self.register(OAuthClient(
            client_id="fizzbuzz-service", client_secret="fizzbuzz-service-secret",
            client_name="FizzBuzz Internal Service", client_type=ClientType.CONFIDENTIAL,
            redirect_uris=[],
            allowed_scopes={"fizzbuzz:read", "fizzbuzz:write", "fizzbuzz:admin"},
            allowed_grants={"client_credentials"},
        ))

    def register(self, client: OAuthClient) -> OAuthClient:
        if not client.created_at:
            client.created_at = datetime.now(timezone.utc)
        self._clients[client.client_id] = client
        return client

    def get(self, client_id: str) -> Optional[OAuthClient]:
        return self._clients.get(client_id)

    def authenticate(self, client_id: str, client_secret: str) -> Optional[OAuthClient]:
        client = self._clients.get(client_id)
        if client is None:
            return None
        if client.client_type == ClientType.PUBLIC:
            return client
        if hmac.compare_digest(client.client_secret, client_secret):
            return client
        return None

    def list_clients(self) -> List[OAuthClient]:
        return list(self._clients.values())

    @property
    def count(self) -> int:
        return len(self._clients)


# ============================================================
# Authorization Server
# ============================================================

class AuthorizationServer:
    """OAuth 2.0 / OIDC authorization server."""

    def __init__(self, config: FizzAuth2Config, jwt: JWTEngine,
                 clients: ClientRegistry) -> None:
        self._config = config
        self._jwt = jwt
        self._clients = clients
        self._codes: Dict[str, AuthorizationCode] = {}
        self._tokens: Dict[str, TokenData] = {}
        self._device_auths: Dict[str, DeviceAuth] = {}
        self._sessions: Dict[str, UserSession] = {}
        self._revoked_tokens: Set[str] = set()
        self._metrics = Auth2Metrics()
        self._started = False
        self._start_time = 0.0

    def start(self) -> None:
        self._started = True
        self._start_time = time.time()
        self._metrics.clients_registered = self._clients.count

    # ---- Authorization Code Flow ----

    def authorize(self, client_id: str, redirect_uri: str, scopes: Set[str],
                  state: str = "", code_challenge: str = "",
                  code_challenge_method: str = "S256",
                  user_id: str = "bob") -> Dict[str, str]:
        """Authorization endpoint: issue an authorization code."""
        client = self._clients.get(client_id)
        if client is None:
            raise FizzAuth2InvalidClientError(client_id)
        if "authorization_code" not in client.allowed_grants:
            raise FizzAuth2UnauthorizedClientError(client_id, "authorization_code")
        if redirect_uri and redirect_uri not in client.redirect_uris:
            raise FizzAuth2InvalidRedirectError(redirect_uri)

        invalid_scopes = scopes - client.allowed_scopes
        if invalid_scopes:
            raise FizzAuth2InvalidScopeError(", ".join(invalid_scopes))

        if self._config.require_pkce and not code_challenge:
            raise FizzAuth2PKCEError("code_challenge required")

        code = uuid.uuid4().hex
        self._codes[code] = AuthorizationCode(
            code=code, client_id=client_id, user_id=user_id,
            redirect_uri=redirect_uri or client.redirect_uris[0],
            scopes=scopes, code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            created_at=time.time(),
        )
        self._metrics.codes_issued += 1
        self._metrics.consents_granted += 1

        result = {"code": code, "redirect_uri": redirect_uri or client.redirect_uris[0]}
        if state:
            result["state"] = state
        return result

    def exchange_code(self, code: str, client_id: str, client_secret: str = "",
                      redirect_uri: str = "", code_verifier: str = "") -> Dict[str, Any]:
        """Token endpoint: exchange authorization code for tokens."""
        auth_code = self._codes.get(code)
        if auth_code is None:
            raise FizzAuth2InvalidGrantError("Unknown authorization code")
        if auth_code.used:
            raise FizzAuth2AuthCodeUsedError(code)
        if time.time() - auth_code.created_at > self._config.code_ttl:
            raise FizzAuth2AuthCodeExpiredError(code)
        if auth_code.client_id != client_id:
            raise FizzAuth2InvalidClientError(client_id)

        # PKCE verification
        if auth_code.code_challenge:
            if not code_verifier:
                raise FizzAuth2PKCEError("code_verifier required")
            if auth_code.code_challenge_method == "S256":
                expected = base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                ).rstrip(b"=").decode()
            else:
                expected = code_verifier
            if not hmac.compare_digest(expected, auth_code.code_challenge):
                raise FizzAuth2PKCEError("code_verifier mismatch")

        auth_code.used = True

        # Issue tokens
        now = time.time()
        access_token = self._issue_token(
            TokenType.ACCESS, client_id, auth_code.user_id,
            auth_code.scopes, self._config.token_ttl,
        )
        refresh_token = None
        if "offline_access" in auth_code.scopes:
            refresh_token = self._issue_token(
                TokenType.REFRESH, client_id, auth_code.user_id,
                auth_code.scopes, self._config.refresh_ttl,
            )

        id_token = None
        if "openid" in auth_code.scopes:
            id_token = self._jwt.issue({
                "sub": auth_code.user_id,
                "aud": client_id,
                "exp": int(now) + self._config.token_ttl,
                "nonce": uuid.uuid4().hex[:8],
                "name": auth_code.user_id,
                "email": f"{auth_code.user_id}@fizzbuzz.local",
            })

        # Create session
        session = UserSession(
            session_id=uuid.uuid4().hex[:12], user_id=auth_code.user_id,
            client_id=client_id, created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        self._sessions[session.session_id] = session
        self._metrics.active_sessions = len([s for s in self._sessions.values() if s.active])

        result = {
            "access_token": access_token.jwt,
            "token_type": "Bearer",
            "expires_in": self._config.token_ttl,
            "scope": " ".join(auth_code.scopes),
        }
        if refresh_token:
            result["refresh_token"] = refresh_token.jwt
        if id_token:
            result["id_token"] = id_token
        return result

    # ---- Client Credentials Flow ----

    def client_credentials(self, client_id: str, client_secret: str,
                           scopes: Set[str]) -> Dict[str, Any]:
        """Token endpoint: client credentials grant."""
        client = self._clients.authenticate(client_id, client_secret)
        if client is None:
            raise FizzAuth2InvalidClientError(client_id)
        if "client_credentials" not in client.allowed_grants:
            raise FizzAuth2UnauthorizedClientError(client_id, "client_credentials")

        invalid = scopes - client.allowed_scopes
        if invalid:
            raise FizzAuth2InvalidScopeError(", ".join(invalid))

        token = self._issue_token(TokenType.ACCESS, client_id, client_id, scopes, self._config.token_ttl)
        return {
            "access_token": token.jwt, "token_type": "Bearer",
            "expires_in": self._config.token_ttl, "scope": " ".join(scopes),
        }

    # ---- Device Authorization Flow ----

    def device_authorize(self, client_id: str, scopes: Set[str]) -> Dict[str, Any]:
        """Device authorization endpoint (RFC 8628)."""
        client = self._clients.get(client_id)
        if client is None:
            raise FizzAuth2InvalidClientError(client_id)

        device_code = uuid.uuid4().hex
        user_code = f"FIZZ-{uuid.uuid4().hex[:4].upper()}"
        now = time.time()

        self._device_auths[device_code] = DeviceAuth(
            device_code=device_code, user_code=user_code, client_id=client_id,
            scopes=scopes, created_at=now, expires_at=now + self._config.device_code_ttl,
        )
        self._metrics.device_codes_issued += 1

        return {
            "device_code": device_code, "user_code": user_code,
            "verification_uri": f"{self._config.issuer}/device",
            "verification_uri_complete": f"{self._config.issuer}/device?code={user_code}",
            "expires_in": self._config.device_code_ttl,
            "interval": DEFAULT_DEVICE_POLL_INTERVAL,
        }

    def device_approve(self, user_code: str, user_id: str = "bob") -> bool:
        """Approve a device authorization request."""
        for da in self._device_auths.values():
            if da.user_code == user_code:
                da.authorized = True
                da.user_id = user_id
                return True
        return False

    def device_token(self, device_code: str, client_id: str) -> Dict[str, Any]:
        """Poll for device authorization token."""
        da = self._device_auths.get(device_code)
        if da is None:
            raise FizzAuth2DeviceAuthError("Unknown device code")
        if time.time() > da.expires_at:
            raise FizzAuth2DeviceCodeExpiredError(device_code)
        if not da.authorized:
            return {"error": "authorization_pending"}

        token = self._issue_token(TokenType.ACCESS, client_id, da.user_id, da.scopes, self._config.token_ttl)
        del self._device_auths[device_code]
        return {"access_token": token.jwt, "token_type": "Bearer", "expires_in": self._config.token_ttl}

    # ---- Refresh Token ----

    def refresh(self, refresh_jwt: str, client_id: str) -> Dict[str, Any]:
        """Refresh an access token using a refresh token."""
        token_data = None
        for td in self._tokens.values():
            if td.jwt == refresh_jwt and td.token_type == TokenType.REFRESH:
                token_data = td
                break
        if token_data is None:
            raise FizzAuth2InvalidGrantError("Invalid refresh token")
        if token_data.revoked:
            raise FizzAuth2TokenRevokedError(token_data.token_id)
        if time.time() > token_data.expires_at:
            raise FizzAuth2TokenExpiredError("refresh")

        new_access = self._issue_token(
            TokenType.ACCESS, client_id, token_data.user_id,
            token_data.scopes, self._config.token_ttl,
        )
        return {"access_token": new_access.jwt, "token_type": "Bearer", "expires_in": self._config.token_ttl}

    # ---- Introspection & Revocation ----

    def introspect(self, token_jwt: str) -> Dict[str, Any]:
        """Token introspection endpoint (RFC 7662)."""
        self._metrics.tokens_introspected += 1
        claims = self._jwt.validate(token_jwt)
        if claims is None:
            return {"active": False}

        token_id = claims.get("jti", "")
        if token_id in self._revoked_tokens:
            return {"active": False}

        return {
            "active": True, "scope": claims.get("scope", ""),
            "client_id": claims.get("client_id", ""), "sub": claims.get("sub", ""),
            "exp": claims.get("exp", 0), "iat": claims.get("iat", 0),
            "iss": claims.get("iss", ""), "token_type": "Bearer",
        }

    def revoke(self, token_jwt: str) -> bool:
        """Token revocation endpoint (RFC 7009)."""
        claims = self._jwt.validate(token_jwt)
        if claims and "jti" in claims:
            self._revoked_tokens.add(claims["jti"])
            self._metrics.tokens_revoked += 1
            return True
        # Also check by JWT string
        for td in self._tokens.values():
            if td.jwt == token_jwt:
                td.revoked = True
                self._revoked_tokens.add(td.token_id)
                self._metrics.tokens_revoked += 1
                return True
        return False

    # ---- OIDC Discovery ----

    def get_discovery(self) -> Dict[str, Any]:
        """OIDC discovery document (.well-known/openid-configuration)."""
        return {
            "issuer": self._config.issuer,
            "authorization_endpoint": f"{self._config.issuer}/authorize",
            "token_endpoint": f"{self._config.issuer}/token",
            "userinfo_endpoint": f"{self._config.issuer}/userinfo",
            "jwks_uri": f"{self._config.issuer}/.well-known/jwks.json",
            "introspection_endpoint": f"{self._config.issuer}/introspect",
            "revocation_endpoint": f"{self._config.issuer}/revoke",
            "device_authorization_endpoint": f"{self._config.issuer}/device/code",
            "registration_endpoint": f"{self._config.issuer}/register",
            "scopes_supported": sorted(SUPPORTED_SCOPES),
            "response_types_supported": sorted(SUPPORTED_RESPONSE_TYPES),
            "grant_types_supported": sorted(SUPPORTED_GRANT_TYPES),
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
            "code_challenge_methods_supported": ["S256", "plain"],
        }

    # ---- Internal ----

    def _issue_token(self, token_type: TokenType, client_id: str,
                     user_id: str, scopes: Set[str], ttl: int) -> TokenData:
        now = time.time()
        token_id = uuid.uuid4().hex[:16]
        claims = {
            "sub": user_id, "client_id": client_id,
            "scope": " ".join(sorted(scopes)), "exp": int(now) + ttl,
            "jti": token_id, "token_type": token_type.value,
        }
        jwt_str = self._jwt.issue(claims)

        td = TokenData(
            token_id=token_id, token_type=token_type, client_id=client_id,
            user_id=user_id, scopes=scopes, issued_at=now,
            expires_at=now + ttl, jwt=jwt_str,
        )
        self._tokens[token_id] = td
        self._metrics.tokens_issued += 1
        return td

    def get_metrics(self) -> Auth2Metrics:
        m = copy.copy(self._metrics)
        m.active_sessions = len([s for s in self._sessions.values() if s.active])
        return m

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._started else 0.0

    @property
    def is_running(self) -> bool:
        return self._started


# ============================================================
# Dashboard
# ============================================================

class FizzAuth2Dashboard:
    def __init__(self, server: AuthorizationServer, jwt: JWTEngine,
                 clients: ClientRegistry, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._server = server
        self._jwt = jwt
        self._clients = clients
        self._width = width

    def render(self) -> str:
        m = self._server.get_metrics()
        lines = [
            "=" * self._width,
            "FizzAuth2 OAuth 2.0/OIDC Dashboard".center(self._width),
            "=" * self._width,
            f"  Server ({FIZZAUTH2_VERSION})",
            f"  {'─' * (self._width - 4)}",
            f"  Status:          {'RUNNING' if self._server.is_running else 'STOPPED'}",
            f"  Issuer:          {self._server._config.issuer}",
            f"  Uptime:          {self._server.uptime:.1f}s",
            f"  Clients:         {m.clients_registered}",
            f"  Codes Issued:    {m.codes_issued}",
            f"  Tokens Issued:   {m.tokens_issued}",
            f"  Tokens Revoked:  {m.tokens_revoked}",
            f"  Introspections:  {m.tokens_introspected}",
            f"  Device Codes:    {m.device_codes_issued}",
            f"  Consents:        {m.consents_granted}",
            f"  Sessions:        {m.active_sessions}",
        ]
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================

class FizzAuth2Middleware(IMiddleware):
    def __init__(self, server: AuthorizationServer, dashboard: FizzAuth2Dashboard,
                 jwt: JWTEngine, clients: ClientRegistry,
                 config: FizzAuth2Config) -> None:
        self._server = server
        self._dashboard = dashboard
        self._jwt = jwt
        self._clients = clients
        self._config = config

    def get_name(self) -> str: return "fizzauth2"

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        m = self._server.get_metrics()
        context.metadata["fizzauth2_version"] = FIZZAUTH2_VERSION
        context.metadata["fizzauth2_running"] = self._server.is_running
        context.metadata["fizzauth2_tokens_issued"] = m.tokens_issued
        context.metadata["fizzauth2_clients"] = m.clients_registered
        if next_handler is not None:
            return next_handler(context)
        return context

    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str: return self._dashboard.render()

    def render_status(self) -> str:
        m = self._server.get_metrics()
        return (f"FizzAuth2 {FIZZAUTH2_VERSION} | {'UP' if self._server.is_running else 'DOWN'} | "
                f"Clients: {m.clients_registered} | Tokens: {m.tokens_issued} | Sessions: {m.active_sessions}")

    def render_clients(self) -> str:
        lines = ["FizzAuth2 Registered Clients:"]
        for c in self._clients.list_clients():
            lines.append(f"\n  {c.client_id} ({c.client_type.value})")
            lines.append(f"    Name:     {c.client_name}")
            lines.append(f"    Scopes:   {', '.join(sorted(c.allowed_scopes))}")
            lines.append(f"    Grants:   {', '.join(sorted(c.allowed_grants))}")
            lines.append(f"    Redirect: {', '.join(c.redirect_uris)}")
        return "\n".join(lines)

    def render_jwks(self) -> str:
        return json.dumps(self._jwt.get_jwks(), indent=2)

    def render_discovery(self) -> str:
        return json.dumps(self._server.get_discovery(), indent=2)

    def render_sessions(self) -> str:
        lines = ["FizzAuth2 Active Sessions:"]
        for s in self._server._sessions.values():
            if s.active:
                lines.append(f"  {s.session_id} user={s.user_id} client={s.client_id}")
        if len(lines) == 1:
            lines.append("  (none)")
        return "\n".join(lines)

    def render_authorize(self, client_id: str) -> str:
        try:
            # Generate PKCE challenge
            verifier = uuid.uuid4().hex
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            ).rstrip(b"=").decode()

            result = self._server.authorize(
                client_id=client_id,
                redirect_uri="",
                scopes={"openid", "fizzbuzz:read"},
                code_challenge=challenge,
                code_challenge_method="S256",
            )
            # Exchange code
            tokens = self._server.exchange_code(
                code=result["code"], client_id=client_id,
                code_verifier=verifier,
            )
            lines = [
                f"FizzAuth2 Authorization Flow",
                f"  Client:        {client_id}",
                f"  Code:          {result['code'][:16]}...",
                f"  Access Token:  {tokens['access_token'][:40]}...",
                f"  Token Type:    {tokens['token_type']}",
                f"  Expires In:    {tokens['expires_in']}s",
                f"  Scope:         {tokens['scope']}",
            ]
            if "id_token" in tokens:
                lines.append(f"  ID Token:      {tokens['id_token'][:40]}...")
            if "refresh_token" in tokens:
                lines.append(f"  Refresh Token: {tokens['refresh_token'][:40]}...")
            return "\n".join(lines)
        except FizzAuth2Error as e:
            return f"Error: {e}"


# ============================================================
# Factory
# ============================================================

def create_fizzauth2_subsystem(
    issuer: str = DEFAULT_ISSUER,
    token_ttl: int = DEFAULT_TOKEN_TTL,
    refresh_ttl: int = DEFAULT_REFRESH_TTL,
    require_pkce: bool = True,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[AuthorizationServer, FizzAuth2Dashboard, FizzAuth2Middleware]:
    config = FizzAuth2Config(issuer=issuer, token_ttl=token_ttl,
                             refresh_ttl=refresh_ttl, require_pkce=require_pkce,
                             dashboard_width=dashboard_width)
    jwt = JWTEngine(config)
    clients = ClientRegistry()
    server = AuthorizationServer(config, jwt, clients)
    dashboard = FizzAuth2Dashboard(server, jwt, clients, dashboard_width)
    middleware = FizzAuth2Middleware(server, dashboard, jwt, clients, config)
    server.start()
    logger.info("FizzAuth2 initialized: issuer=%s clients=%d", issuer, clients.count)
    return server, dashboard, middleware

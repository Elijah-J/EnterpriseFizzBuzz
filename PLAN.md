# PLAN.md — FizzAuth2: OAuth 2.0 / OIDC Authorization Server

## Motivation

The Enterprise FizzBuzz Platform currently authenticates operators via HMAC-SHA256
tokens issued by the RBAC subsystem (`auth.py`).  While effective for single-tenant
deployments, this mechanism does not support federated identity, third-party client
delegation, or standards-based token exchange.  Any organization operating the
platform at scale — multiple services consuming FizzBuzz evaluations, partner
integrations, or CI/CD pipelines requesting automated divisibility checks — requires
an OAuth 2.0 authorization server compliant with the modern security BCP (RFC 6749,
RFC 7636, RFC 8628, RFC 9126).

FizzAuth2 implements a complete OAuth 2.0 and OpenID Connect authorization server
embedded directly in the platform runtime.  It issues JWT access tokens and refresh
tokens, exposes a JWKS endpoint for distributed verification, supports three grant
types (authorization code with PKCE, client credentials, device authorization), and
provides token introspection and revocation endpoints.  The module integrates with
the existing RBAC role hierarchy so that OAuth scopes map deterministically to
FizzBuzz permissions.

## Deliverables Summary

| Artifact | Path |
|----------|------|
| Main module | `enterprise_fizzbuzz/infrastructure/fizzauth2.py` |
| Exception file | `enterprise_fizzbuzz/domain/exceptions/fizzauth2.py` |
| Config mixin | `enterprise_fizzbuzz/infrastructure/config/mixins/fizzauth2.py` |
| Feature descriptor | `enterprise_fizzbuzz/infrastructure/features/fizzauth2_feature.py` |
| Root stub | `fizzauth2.py` |
| Test file | `tests/test_fizzauth2.py` |

Estimated scope: ~2,000 lines implementation, ~100 tests, 12 CLI flags, 21 exception classes.

---

## Phase 1: Core Token Infrastructure

**Goal:** JWT issuance, JWK key management, and token lifecycle primitives.

### 1.1 Exception Hierarchy (`enterprise_fizzbuzz/domain/exceptions/fizzauth2.py`)

Define 21 exception classes under `FizzAuth2Error(FizzBuzzError)` with error codes
EFP-AUTH2-001 through EFP-AUTH2-021:

| Code | Class | Scenario |
|------|-------|----------|
| EFP-AUTH2-001 | `FizzAuth2Error` | Base exception for all OAuth 2.0 failures |
| EFP-AUTH2-002 | `JWKGenerationError` | RSA/EC key pair generation failure |
| EFP-AUTH2-003 | `JWKRotationError` | Key rotation violated minimum lifetime |
| EFP-AUTH2-004 | `JWTSigningError` | Token signing operation failed |
| EFP-AUTH2-005 | `JWTVerificationError` | Signature verification failed |
| EFP-AUTH2-006 | `TokenExpiredError` | Access or refresh token past `exp` claim |
| EFP-AUTH2-007 | `InvalidGrantError` | Grant type not recognized or not enabled |
| EFP-AUTH2-008 | `InvalidClientError` | Client authentication failed |
| EFP-AUTH2-009 | `InvalidScopeError` | Requested scope exceeds client allowance |
| EFP-AUTH2-010 | `AuthorizationCodeExpiredError` | Code used after TTL elapsed |
| EFP-AUTH2-011 | `AuthorizationCodeReplayError` | Code presented more than once (replay) |
| EFP-AUTH2-012 | `PKCEVerificationError` | code_verifier does not match code_challenge |
| EFP-AUTH2-013 | `ClientRegistrationError` | Dynamic client registration failed |
| EFP-AUTH2-014 | `ConsentRequiredError` | User has not granted consent for scope set |
| EFP-AUTH2-015 | `DeviceCodeExpiredError` | Device code exceeded polling window |
| EFP-AUTH2-016 | `DeviceCodePendingError` | User has not yet completed device auth |
| EFP-AUTH2-017 | `DeviceCodeDeniedError` | User explicitly denied device authorization |
| EFP-AUTH2-018 | `TokenRevocationError` | Revocation endpoint processing failure |
| EFP-AUTH2-019 | `TokenIntrospectionError` | Introspection request malformed or forbidden |
| EFP-AUTH2-020 | `SessionExpiredError` | Authorization session exceeded idle timeout |
| EFP-AUTH2-021 | `ScopeEscalationError` | Refresh token request attempted scope widening |

Each exception follows the existing pattern: `__init__(self, reason: str)` calling
`super().__init__(f"FizzAuth2 error [EFP-AUTH2-NNN]: {reason}")`.

### 1.2 JWK Key Store

Core classes for RSA-2048 key pair generation, JWK serialization (RFC 7517), key
rotation with configurable lifetime, and a JWKS document builder:

- `JWKKeyPair` — dataclass holding `kid`, `private_key`, `public_key`, `created_at`, `algorithm`.
- `JWKSKeyStore` — manages active/retired keys, generates new RSA-2048 pairs using
  Python `rsa` arithmetic (no external deps), serializes public keys to JWK format,
  supports key rotation with minimum rotation interval.
- `jwks_document()` method returns `{"keys": [...]}` per RFC 7517 Section 5.

### 1.3 JWT Token Engine

- `JWTHeader` — `{"alg": "RS256", "typ": "JWT", "kid": "..."}`.
- `JWTClaims` — standard claims: `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`,
  plus custom claims: `scope`, `client_id`, `fizzbuzz_role`.
- `JWTCodec` — base64url encoding/decoding, PKCS#1 v1.5 RSA-SHA256 signing and
  verification, token serialization (`header.payload.signature`).
- `AccessToken` and `RefreshToken` dataclasses wrapping encoded JWT strings with
  metadata (expiry, scope set, client ID).

### 1.4 Token Lifecycle Manager

- `TokenManager` — issues access/refresh token pairs, validates tokens against the
  JWKS key store, checks expiry and scope, maintains an in-memory revocation list
  (token `jti` → revocation timestamp), supports token introspection returning
  RFC 7662 response format.

**Phase 1 output:** ~500 lines in the main module, full exception file (~200 lines).

---

## Phase 2: Grant Types and Authorization Flows

**Goal:** Implement the three OAuth 2.0 grant types and supporting infrastructure.

### 2.1 Client Registry

- `OAuthClient` — dataclass: `client_id`, `client_secret_hash`, `client_name`,
  `redirect_uris`, `allowed_scopes`, `allowed_grant_types`, `created_at`,
  `is_confidential`, `device_auth_enabled`.
- `ClientRegistry` — in-memory store of registered clients, client authentication
  (constant-time secret comparison), dynamic client registration (RFC 7591 subset),
  client CRUD operations.
- Default bootstrap client `fizzbuzz-cli` registered on initialization with
  `authorization_code` and `device_authorization` grants enabled.

### 2.2 Scope Model

Define a canonical scope vocabulary mapping to existing RBAC permissions:

| Scope | RBAC Permission | Description |
|-------|----------------|-------------|
| `fizzbuzz:read` | `EVALUATE_SINGLE` | Evaluate a single integer |
| `fizzbuzz:batch` | `EVALUATE_RANGE` | Evaluate a range of integers |
| `fizzbuzz:admin` | `CONFIGURE_RULES` | Modify rule configuration |
| `fizzbuzz:export` | `EXPORT_RESULTS` | Export evaluation results |
| `fizzbuzz:metrics` | `VIEW_METRICS` | Access platform metrics |
| `openid` | — | OIDC identity token |
| `profile` | — | User profile claims |
| `offline_access` | — | Refresh token issuance |

- `ScopeRegistry` — validates scope strings, resolves scopes to RBAC permissions,
  computes effective scope intersection (requested ∩ client-allowed ∩ user-consented).

### 2.3 Authorization Code Grant with PKCE (RFC 7636)

Full authorization code flow:

1. **Authorization request** — `AuthorizationEndpoint.authorize()` accepts
   `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`,
   `code_challenge`, `code_challenge_method` (S256 only, plain rejected per BCP).
2. **Consent simulation** — `ConsentManager` checks whether the user has previously
   consented to the requested scopes for this client.  If not, generates a
   `ConsentScreen` object with scope descriptions and approval/deny action.
   Simulates user approval after a configurable delay (default: immediate).
3. **Code issuance** — generates a cryptographically random authorization code
   (32 bytes, base64url), stores it with associated `client_id`, `redirect_uri`,
   `scope`, `code_challenge`, `user_id`, `created_at`, `ttl` (default 60s).
   Returns redirect URI with `code` and `state` parameters.
4. **Token exchange** — `TokenEndpoint.exchange()` accepts `grant_type=authorization_code`,
   `code`, `redirect_uri`, `client_id`, `code_verifier`.  Validates the code exists,
   has not expired, has not been previously used (replay detection), redirect_uri
   matches, and PKCE verifier matches challenge via `SHA256(code_verifier) == code_challenge`.
   On success, issues access token + refresh token.  On any failure, invalidates
   the code permanently (one-time use per RFC 6749 Section 4.1.2).

### 2.4 Client Credentials Grant

- `TokenEndpoint.client_credentials()` — accepts `grant_type=client_credentials`,
  `client_id`, `client_secret`, `scope`.  Authenticates client, validates requested
  scope subset of client-allowed scopes, issues access token only (no refresh token
  per RFC 6749 Section 4.4.3).

### 2.5 Device Authorization Grant (RFC 8628)

- `DeviceAuthorizationEndpoint.initiate()` — generates `device_code` (32 bytes),
  `user_code` (8-character alphanumeric, formatted XXXX-XXXX), `verification_uri`,
  `expires_in` (default 300s), `interval` (default 5s).
- `DeviceCodeStore` — in-memory store tracking device codes with states:
  `PENDING`, `APPROVED`, `DENIED`, `EXPIRED`.
- `DeviceAuthorizationEndpoint.verify()` — simulates user verification: accepts
  `user_code`, transitions device code to `APPROVED` with associated user identity.
- `TokenEndpoint.device_token()` — polls by `device_code`, returns
  `authorization_pending` / `slow_down` / `access_denied` / token response
  per RFC 8628 Section 3.5.

### 2.6 Session Management

- `AuthSession` — dataclass: `session_id`, `user_id`, `created_at`, `last_active`,
  `idle_timeout`, `absolute_timeout`, `consented_scopes_by_client`.
- `SessionStore` — in-memory session management with idle/absolute timeout,
  session lookup by ID, session invalidation, consent persistence per session.

**Phase 2 output:** ~800 lines added to the main module.

---

## Phase 3: Discovery, Introspection, Revocation, and RBAC Integration

**Goal:** Standards-compliant metadata endpoints and integration with auth.py.

### 3.1 OIDC Discovery Endpoint

`DiscoveryEndpoint.openid_configuration()` returns a dict conforming to
OpenID Connect Discovery 1.0 Section 3:

```python
{
    "issuer": "https://fizzbuzz.enterprise.local",
    "authorization_endpoint": "/authorize",
    "token_endpoint": "/token",
    "device_authorization_endpoint": "/device/authorize",
    "jwks_uri": "/jwks",
    "introspection_endpoint": "/introspect",
    "revocation_endpoint": "/revoke",
    "registration_endpoint": "/register",
    "scopes_supported": ["openid", "profile", "fizzbuzz:read", ...],
    "response_types_supported": ["code"],
    "grant_types_supported": [
        "authorization_code",
        "client_credentials",
        "urn:ietf:params:oauth:grant-type:device_code"
    ],
    "token_endpoint_auth_methods_supported": [
        "client_secret_basic",
        "client_secret_post"
    ],
    "code_challenge_methods_supported": ["S256"],
    "subject_types_supported": ["public"],
    "id_token_signing_alg_values_supported": ["RS256"],
}
```

### 3.2 Token Introspection (RFC 7662)

- `IntrospectionEndpoint.introspect()` — accepts `token` and `token_type_hint`,
  authenticates requesting client, returns `{"active": true/false, ...}` with
  claims `scope`, `client_id`, `sub`, `exp`, `iat`, `token_type`, `iss`.

### 3.3 Token Revocation (RFC 7009)

- `RevocationEndpoint.revoke()` — accepts `token` and `token_type_hint`,
  authenticates requesting client, adds token `jti` to revocation set.
  Returns 200 OK regardless of whether the token existed (per RFC 7009 Section 2.1).

### 3.4 RBAC Bridge

- `RBACBridge` — translates between OAuth scopes and existing `FizzBuzzRole` /
  permission model from `auth.py`.  Given a validated access token, constructs
  an `AuthContext` compatible with the existing `AuthorizationMiddleware`.
- `OAuth2AuthorizationMiddleware` — middleware component that intercepts requests,
  extracts Bearer tokens from the `Authorization` header analog, validates via
  `TokenManager`, constructs `AuthContext` via `RBACBridge`, and delegates to the
  existing RBAC pipeline.  Sits at middleware priority 4 (one above the existing
  auth middleware at priority 5).

### 3.5 Refresh Token Rotation

- `TokenEndpoint.refresh()` — accepts `grant_type=refresh_token`, `refresh_token`,
  `scope` (optional, must be subset of original scope).  Validates the refresh token,
  revokes it, issues a new access/refresh token pair (rotation per OAuth 2.0 Security
  BCP).  Detects scope escalation attempts and raises `ScopeEscalationError`.

**Phase 3 output:** ~400 lines added to the main module.

---

## Phase 4: Configuration, CLI, Feature Descriptor, Tests

**Goal:** Platform integration and comprehensive test coverage.

### 4.1 Config Mixin (`enterprise_fizzbuzz/infrastructure/config/mixins/fizzauth2.py`)

Properties with `oauth2_` prefix, reading from `config.yaml` under `oauth2:` key:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `oauth2_enabled` | `bool` | `False` | Master enable for FizzAuth2 |
| `oauth2_issuer` | `str` | `"https://fizzbuzz.enterprise.local"` | Token issuer URI |
| `oauth2_access_token_ttl` | `int` | `3600` | Access token lifetime (seconds) |
| `oauth2_refresh_token_ttl` | `int` | `86400` | Refresh token lifetime (seconds) |
| `oauth2_authorization_code_ttl` | `int` | `60` | Auth code lifetime (seconds) |
| `oauth2_device_code_ttl` | `int` | `300` | Device code lifetime (seconds) |
| `oauth2_device_poll_interval` | `int` | `5` | Device code polling interval |
| `oauth2_jwk_rotation_interval` | `int` | `86400` | JWK rotation interval (seconds) |
| `oauth2_require_pkce` | `bool` | `True` | Reject auth code requests without PKCE |
| `oauth2_consent_auto_approve` | `bool` | `True` | Auto-approve consent in non-interactive mode |
| `oauth2_session_idle_timeout` | `int` | `1800` | Session idle timeout (seconds) |
| `oauth2_session_absolute_timeout` | `int` | `28800` | Session absolute timeout (seconds) |

### 4.2 CLI Flags (12 flags)

Added to `build_argument_parser()` in `__main__.py`:

| Flag | Type | Default | Maps to |
|------|------|---------|---------|
| `--oauth2` | `store_true` | `False` | `oauth2_enabled` |
| `--oauth2-issuer` | `str` | config | `oauth2_issuer` |
| `--oauth2-access-token-ttl` | `int` | config | `oauth2_access_token_ttl` |
| `--oauth2-refresh-token-ttl` | `int` | config | `oauth2_refresh_token_ttl` |
| `--oauth2-auth-code-ttl` | `int` | config | `oauth2_authorization_code_ttl` |
| `--oauth2-device-code-ttl` | `int` | config | `oauth2_device_code_ttl` |
| `--oauth2-device-poll-interval` | `int` | config | `oauth2_device_poll_interval` |
| `--oauth2-jwk-rotation-interval` | `int` | config | `oauth2_jwk_rotation_interval` |
| `--oauth2-require-pkce` | `store_true` | `True` | `oauth2_require_pkce` |
| `--no-oauth2-require-pkce` | `store_false` | — | `oauth2_require_pkce` (negation) |
| `--oauth2-auto-consent` | `store_true` | config | `oauth2_consent_auto_approve` |
| `--oauth2-session-timeout` | `int` | config | `oauth2_session_idle_timeout` |

### 4.3 Feature Descriptor (`enterprise_fizzbuzz/infrastructure/features/fizzauth2_feature.py`)

Standard `FeatureDescriptor` subclass:

- `name = "fizzauth2"`
- `description = "OAuth 2.0 / OIDC authorization server with PKCE, device flow, and JWKS"`
- `middleware_priority = 4`
- `cli_flags = [<the 12 flags above>]`
- `is_enabled()` checks `args.oauth2` or `config.oauth2_enabled`
- `create()` instantiates `FizzAuth2Server`, `OAuth2AuthorizationMiddleware`,
  wires `RBACBridge` to existing auth context.

### 4.4 Root Stub (`fizzauth2.py`)

```python
"""Backward-compatible re-export stub for fizzauth2."""
from enterprise_fizzbuzz.infrastructure.fizzauth2 import *  # noqa: F401,F403
```

### 4.5 Test Suite (`tests/test_fizzauth2.py`)

~100 tests organized by functional area:

**JWK Key Store (10 tests)**
- Key pair generation produces valid RSA-2048 keys
- JWK serialization includes required fields (`kty`, `n`, `e`, `kid`, `use`, `alg`)
- JWKS document contains all active public keys
- Key rotation creates new key and retires previous
- Rotation respects minimum rotation interval
- Key store initializes with at least one key pair
- Retired keys remain in JWKS for verification overlap
- Key IDs are unique across generations
- JWK `n` and `e` are base64url-encoded without padding
- Empty key store raises `JWKGenerationError`

**JWT Token Engine (12 tests)**
- Access token contains required claims (`iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `scope`)
- Token signature validates against issuing key
- Expired token fails verification with `TokenExpiredError`
- Token with tampered payload fails signature check
- Refresh token includes `offline_access` scope indicator
- Token `jti` is unique across issuances
- Base64url encoding omits padding characters
- Header `kid` matches the signing key ID
- Claims roundtrip through encode/decode without loss
- Token with `nbf` in the future fails validation
- Algorithm field locked to RS256
- Malformed token string raises `JWTVerificationError`

**Client Registry (8 tests)**
- Client registration returns `client_id` and `client_secret`
- Client authentication succeeds with correct secret
- Client authentication fails with wrong secret (raises `InvalidClientError`)
- Confidential vs public client distinction
- Redirect URI validation (exact match, no fragments)
- Bootstrap client `fizzbuzz-cli` exists after initialization
- Dynamic registration rejects duplicate client names
- Client allowed scopes restrict token issuance

**Authorization Code + PKCE (15 tests)**
- Authorization request returns code and state
- Code exchange produces access and refresh tokens
- PKCE S256 challenge/verifier validation succeeds
- PKCE verification fails with wrong verifier (raises `PKCEVerificationError`)
- Authorization code expires after TTL (raises `AuthorizationCodeExpiredError`)
- Authorization code is single-use (raises `AuthorizationCodeReplayError`)
- Redirect URI mismatch on exchange rejects request
- Missing `code_challenge` rejected when PKCE required
- `code_challenge_method=plain` rejected (S256 only)
- State parameter echoed unmodified
- Scope downscoping on token exchange
- Code bound to specific client ID
- Invalid client on exchange raises `InvalidClientError`
- Authorization with unknown client raises `InvalidClientError`
- Code invalidated on any exchange failure

**Client Credentials Grant (8 tests)**
- Client credentials returns access token only (no refresh token)
- Scope limited to client-allowed scopes
- Public client rejected for client credentials grant
- Invalid secret raises `InvalidClientError`
- Empty scope defaults to client full allowance
- Unsupported grant type for client raises `InvalidGrantError`
- Token `sub` is the client ID (not a user)
- Token includes `client_credentials` grant type in claims

**Device Authorization Grant (12 tests)**
- Device initiation returns `device_code`, `user_code`, `verification_uri`
- User code format is XXXX-XXXX (8 alphanumeric characters)
- Polling before user approval returns `authorization_pending`
- Polling after user approval returns tokens
- Polling after user denial raises `DeviceCodeDeniedError`
- Device code expires after TTL (raises `DeviceCodeExpiredError`)
- Polling faster than interval returns `slow_down`
- User verification with invalid code rejected
- Device code is single-use after approval
- Multiple device codes can be active simultaneously
- Device grant disabled for clients without `device_authorization` grant type
- Approved device code carries correct user identity into tokens

**Token Introspection (8 tests)**
- Active token introspection returns `{"active": true}` with claims
- Expired token returns `{"active": false}`
- Revoked token returns `{"active": false}`
- Unknown token returns `{"active": false}`
- Introspection requires authenticated client
- Response includes `scope`, `client_id`, `sub`, `exp`, `token_type`
- `token_type_hint` accepted but not required
- Introspection of refresh token works correctly

**Token Revocation (7 tests)**
- Revoked access token fails subsequent validation
- Revoked refresh token cannot be used for refresh
- Revoking unknown token returns success (no error per RFC 7009)
- Revocation requires authenticated client
- Revoked token appears inactive in introspection
- Double revocation is idempotent
- `token_type_hint` accepted for routing

**Refresh Token (8 tests)**
- Refresh produces new access/refresh token pair
- Old refresh token revoked after rotation
- Scope subset on refresh accepted
- Scope escalation on refresh raises `ScopeEscalationError`
- Expired refresh token raises `TokenExpiredError`
- Revoked refresh token raises `TokenRevocationError`
- Refresh preserves original `sub` claim
- Refresh with invalid token raises `JWTVerificationError`

**OIDC Discovery (5 tests)**
- Discovery document contains all required fields
- Issuer matches configured value
- Supported grant types include all three grants
- `code_challenge_methods_supported` contains `S256`
- JWKS URI points to `/jwks`

**Session Management (5 tests)**
- Session created on successful authorization
- Idle timeout expires session (raises `SessionExpiredError`)
- Activity resets idle timer
- Absolute timeout cannot be extended
- Consent stored per client within session

**RBAC Integration (5 tests)**
- OAuth scope `fizzbuzz:read` maps to `EVALUATE_SINGLE` permission
- `RBACBridge` constructs valid `AuthContext` from access token
- `OAuth2AuthorizationMiddleware` accepts valid Bearer token
- Middleware rejects expired token
- Middleware delegates to existing RBAC pipeline with mapped role

**Exception Hierarchy (2 tests)**
- All 21 exceptions inherit from `FizzAuth2Error`
- All error codes follow EFP-AUTH2-NNN format

---

## Implementation Notes

1. **No external dependencies.** RSA key generation uses Python's built-in `int`
   arithmetic with Miller-Rabin primality testing, consistent with the platform's
   existing cryptographic implementations in `auth.py` and `blockchain.py`.

2. **In-memory storage only.** Authorization codes, device codes, sessions, client
   registrations, and revocation lists are held in dictionaries.  Persistence is
   out of scope — the platform's existing persistence backends (SQLite, filesystem)
   can be integrated in a future cycle.

3. **No HTTP server.** FizzAuth2 exposes endpoint classes with method calls, not
   actual HTTP listeners.  The FizzWeb module can route to these endpoints in a
   future integration.  This is an authorization server engine, not a web
   application.

4. **Deterministic time.** All timestamp operations use `time.time()` with injectable
   clock functions for testability.  Tests use a mock clock to control token expiry,
   session timeouts, and device code windows without real-time delays.

5. **RBAC bridge is additive.** The `OAuth2AuthorizationMiddleware` does not replace
   the existing `AuthorizationMiddleware` — it sits upstream at priority 4 and
   constructs an `AuthContext` that the existing middleware can validate.  Operators
   can use either HMAC tokens or OAuth 2.0 Bearer tokens.

6. **Singleton reset.** `FizzAuth2Server` follows the `_SingletonMeta` pattern if
   applicable, with `reset()` support for test isolation.  If a singleton is not
   warranted, standard instance creation with builder injection is used instead.

# RBAC & Security Reference

Enterprise FizzBuzz Platform v1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [Role Hierarchy](#role-hierarchy)
3. [Permission Model](#permission-model)
4. [Token Authentication](#token-authentication)
5. [Trust-Mode Authentication](#trust-mode-authentication)
6. [Authorization Middleware](#authorization-middleware)
7. [Access Denied Response Specification](#access-denied-response-specification)
8. [Configuration](#configuration)
9. [Compliance](#compliance)

---

## Overview

The Enterprise FizzBuzz Platform implements a comprehensive Role-Based Access Control
(RBAC) system to govern access to FizzBuzz evaluation operations. The ability to
compute `n % 3` is a privilege, not a right, and the authorization framework enforces
this principle at every layer of the middleware pipeline.

The system is implemented in
`enterprise_fizzbuzz/infrastructure/auth.py` and relies on domain models defined in
`enterprise_fizzbuzz/domain/models.py`. It provides:

- A five-tier role hierarchy with permission inheritance
- Granular permission strings scoped to numeric ranges and actions
- HMAC-SHA256 token-based authentication
- A trust-mode bypass for development and testing
- A 47-field access denied response body (the field count is asserted at runtime)
- Middleware-based authorization enforcement at pipeline priority -10

The RBAC module references four custom exceptions from `enterprise_fizzbuzz/domain/exceptions.py`:

| Exception | Purpose |
|-----------|---------|
| `AuthenticationError` | Raised when authentication fails at the transport layer |
| `TokenValidationError` | Raised when a token is malformed, expired, or tampered with |
| `InsufficientFizzPrivilegesError` | Raised when an authenticated user lacks the required permission |
| `NumberClassificationLevelExceededError` | Raised when a number exceeds the user's classification clearance |

---

## Role Hierarchy

The platform defines five roles in the `FizzBuzzRole` enum
(`enterprise_fizzbuzz/domain/models.py`). Each role inherits all permissions from its
parent in the hierarchy, which is maintained by the `RoleRegistry` class
(`enterprise_fizzbuzz/infrastructure/auth.py`).

### Hierarchy Diagram

```
ANONYMOUS
  └── FIZZ_READER
        ├── BUZZ_ADMIN
        │     └── FIZZBUZZ_SUPERUSER
        └── NUMBER_AUDITOR
```

### Inheritance Chain

The `RoleRegistry._HIERARCHY` dict maps each role to its parent:

| Role | Parent | Description |
|------|--------|-------------|
| `ANONYMOUS` | *(none)* | The default role. Can read the number 1. |
| `FIZZ_READER` | `ANONYMOUS` | Can read multiples of 3 and evaluate numbers 1-50. |
| `BUZZ_ADMIN` | `FIZZ_READER` | Can read and configure multiples of 5 and evaluate numbers 1-100. |
| `FIZZBUZZ_SUPERUSER` | `BUZZ_ADMIN` | Unrestricted access to all numbers, all actions. |
| `NUMBER_AUDITOR` | `FIZZ_READER` | Can audit and read all numbers but cannot evaluate or configure. |

### Direct Permissions by Role

These are the permissions granted directly to each role, *not* including inherited
permissions. Defined in `RoleRegistry._DIRECT_PERMISSIONS`.

**ANONYMOUS**
- `numbers:1:read`

**FIZZ_READER**
- `numbers:fizz:read`
- `numbers:1-50:evaluate`

**BUZZ_ADMIN**
- `numbers:buzz:read`
- `numbers:buzz:configure`
- `numbers:1-100:evaluate`

**FIZZBUZZ_SUPERUSER**
- `numbers:*:evaluate`
- `numbers:*:read`
- `numbers:*:configure`

**NUMBER_AUDITOR**
- `numbers:*:audit`
- `numbers:*:read`

### Effective Permissions (Including Inherited)

The `RoleRegistry.get_effective_permissions()` method walks up the hierarchy collecting
all permissions from each ancestor. The effective permission set for each role:

| Role | Effective Permissions |
|------|---------------------|
| `ANONYMOUS` | `numbers:1:read` |
| `FIZZ_READER` | `numbers:fizz:read`, `numbers:1-50:evaluate`, `numbers:1:read` |
| `BUZZ_ADMIN` | `numbers:buzz:read`, `numbers:buzz:configure`, `numbers:1-100:evaluate`, `numbers:fizz:read`, `numbers:1-50:evaluate`, `numbers:1:read` |
| `FIZZBUZZ_SUPERUSER` | `numbers:*:evaluate`, `numbers:*:read`, `numbers:*:configure`, `numbers:buzz:read`, `numbers:buzz:configure`, `numbers:1-100:evaluate`, `numbers:fizz:read`, `numbers:1-50:evaluate`, `numbers:1:read` |
| `NUMBER_AUDITOR` | `numbers:*:audit`, `numbers:*:read`, `numbers:fizz:read`, `numbers:1-50:evaluate`, `numbers:1:read` |

### Suggested Upgrade Path

When access is denied, the `RoleRegistry.get_suggested_upgrade_path()` method recommends
the next role in the hierarchy. Every denial is also a sales opportunity.

| Current Role | Suggested Upgrade |
|-------------|-------------------|
| `ANONYMOUS` | `FIZZ_READER` |
| `FIZZ_READER` | `BUZZ_ADMIN` |
| `BUZZ_ADMIN` | `FIZZBUZZ_SUPERUSER` |
| `NUMBER_AUDITOR` | `FIZZBUZZ_SUPERUSER` |
| `FIZZBUZZ_SUPERUSER` | `FIZZBUZZ_SUPERUSER` |

---

## Permission Model

### Permission String Format

All permissions follow the format `resource:range_spec:action`, parsed by the
`PermissionParser` class.

| Segment | Description | Examples |
|---------|-------------|----------|
| `resource` | The resource category being accessed. Currently always `numbers`. | `numbers` |
| `range_spec` | Which subset of the resource the permission applies to. | `*`, `1-50`, `fizz`, `buzz`, `fizzbuzz`, `42` |
| `action` | The operation being performed on the resource. | `evaluate`, `read`, `configure`, `audit` |

### Range Specifications

The `range_spec` segment supports the following formats, resolved by
`PermissionParser._range_contains_number()`:

| Spec | Syntax | Covers |
|------|--------|--------|
| Wildcard | `*` | All numbers. The ultimate privilege. |
| Numeric range | `start-end` | All integers from `start` to `end`, inclusive. Example: `1-50` covers 1 through 50. |
| Named class: fizz | `fizz` | All multiples of 3. |
| Named class: buzz | `buzz` | All multiples of 5. |
| Named class: fizzbuzz | `fizzbuzz` | All multiples of both 3 and 5 (i.e., multiples of 15). Checked before `fizz` and `buzz` to avoid false positives. |
| Single number | `N` | Exactly the integer N. Example: `42` covers only 42. |

### Permission Matching

The `PermissionParser.matches()` method determines whether a granted permission covers
a required permission. The rules:

1. **Resource must match exactly.** A `numbers` grant does not cover a hypothetical `strings` requirement.
2. **Action must match exactly.** An `evaluate` grant does not satisfy a `read` requirement.
3. **Range matching follows containment logic:**
   - A wildcard `*` grant covers any required range.
   - If the required range is `*`, only a wildcard grant can satisfy it.
   - If the required range resolves to a single number, the grant is checked using `_range_contains_number()`.
   - For non-numeric required ranges, only an exact match satisfies the requirement.

### Actions

The following actions are used in the current permission model:

| Action | Description |
|--------|-------------|
| `evaluate` | Perform a FizzBuzz evaluation on a number. This is the action checked by `AuthorizationMiddleware`. |
| `read` | Read a number or its properties. |
| `configure` | Modify evaluation rules or parameters for a number range. |
| `audit` | Access audit trails and evaluation history for a number range. |

---

## Token Authentication

### Token Format

Enterprise FizzBuzz Platform tokens use the format:

```
EFP.<base64url_payload>.<hmac_sha256_hex>
```

This is, as the source code notes, "suspiciously similar to JWT but legally distinct
enough to avoid licensing fees."

| Segment | Encoding | Description |
|---------|----------|-------------|
| `EFP` | Plain text | The fixed prefix. Identifies this as an Enterprise FizzBuzz Platform token, not a JWT, a grocery receipt, or a cry for help. |
| `payload` | Base64url (no padding) | A JSON object containing the nine payload fields, serialized with compact separators and sorted keys. |
| `signature` | Hex-encoded HMAC-SHA256 | The HMAC-SHA256 digest of the base64url payload, keyed with the platform's signing secret. |

### Payload Fields

The token payload contains exactly nine fields, defined in `FizzBuzzTokenEngine.generate_token()`:

| Field | Type | Description |
|-------|------|-------------|
| `sub` | `string` | Subject. The username of the authenticated user. |
| `role` | `string` | The `FizzBuzzRole` enum member name (e.g., `"BUZZ_ADMIN"`). |
| `iat` | `float` | Issued-at timestamp. Unix epoch seconds at time of token generation. |
| `exp` | `float` | Expiration timestamp. Unix epoch seconds. Defaults to `iat + 3600` (one hour). |
| `jti` | `string` | Token ID. A UUID v4 generated at signing time. Used for audit trails. |
| `iss` | `string` | Issuer. Defaults to `"enterprise-fizzbuzz-platform"`. |
| `fizz_clearance_level` | `int` | Clearance level for Fizz operations (0-5). Determined by role. |
| `buzz_clearance_level` | `int` | Clearance level for Buzz operations (0-5). Determined by role. |
| `favorite_prime` | `int` | The user's favorite prime number, randomly selected from a curated list. |

### Clearance Levels by Role

The `FizzBuzzTokenEngine._CLEARANCE_LEVELS` dict maps each role to a
`(fizz_clearance, buzz_clearance)` tuple:

| Role | Fizz Clearance | Buzz Clearance |
|------|---------------|----------------|
| `ANONYMOUS` | 0 | 0 |
| `FIZZ_READER` | 2 | 0 |
| `BUZZ_ADMIN` | 2 | 4 |
| `FIZZBUZZ_SUPERUSER` | 5 | 5 |
| `NUMBER_AUDITOR` | 3 | 3 |

### Favorite Prime Selection

The `favorite_prime` field is populated from the following curated list:

```
2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47
```

Selection is random. The platform makes no representations about the suitability of
any particular prime for any particular user. The inclusion of 47 in this list is,
of course, not a coincidence.

### Token Generation

To generate a token programmatically:

```python
from enterprise_fizzbuzz.infrastructure.auth import FizzBuzzTokenEngine
from enterprise_fizzbuzz.domain.models import FizzBuzzRole

token = FizzBuzzTokenEngine.generate_token(
    user="alice",
    role=FizzBuzzRole.BUZZ_ADMIN,
    secret="your-signing-secret",
    ttl_seconds=3600,              # optional, defaults to 3600
    issuer="enterprise-fizzbuzz-platform",  # optional
)
```

The payload JSON is serialized with `separators=(",", ":")` and `sort_keys=True` to
ensure deterministic output. The base64url encoding strips trailing `=` padding.

### Token Validation

`FizzBuzzTokenEngine.validate_token()` performs validation in the following order:

1. **Format check.** The token must contain exactly three dot-separated segments, and the first segment must be `"EFP"`.
2. **Signature verification.** The HMAC-SHA256 of the base64url payload is computed and compared against the provided signature using `hmac.compare_digest()` (constant-time comparison to prevent timing attacks).
3. **Payload decoding.** The base64url segment is padded and decoded. The resulting bytes are parsed as JSON.
4. **Required fields check.** The fields `sub`, `role`, `iat`, `exp`, `jti`, and `iss` must be present. (Note: `fizz_clearance_level`, `buzz_clearance_level`, and `favorite_prime` are not checked at validation time.)
5. **Expiration check.** The `exp` field must be greater than or equal to the current Unix timestamp.
6. **Role resolution.** The `role` field must correspond to a valid `FizzBuzzRole` enum member.

On success, `validate_token()` returns an `AuthContext` with `trust_mode=False` and
the role's effective permissions resolved via `RoleRegistry.get_effective_permissions()`.

On failure at any step, a `TokenValidationError` is raised with a diagnostic message
that is informative, specific, and slightly judgmental.

---

## Trust-Mode Authentication

Trust-mode authentication bypasses token verification entirely. It is activated by
the `--user` CLI flag and is, as the source code describes it, "the 'just trust me'
protocol, which is exactly as secure as it sounds."

### CLI Flags

| Flag | Type | Description |
|------|------|-------------|
| `--user USERNAME` | `string` | Authenticate as the specified user without a token. Activates trust mode. |
| `--role ROLE` | `string` | Assign the specified RBAC role. Choices: `ANONYMOUS`, `FIZZ_READER`, `BUZZ_ADMIN`, `FIZZBUZZ_SUPERUSER`, `NUMBER_AUDITOR`. If omitted, defaults to the `rbac_default_role` from configuration. Requires `--user` or `--token`. |
| `--token TOKEN` | `string` | Authenticate using a signed EFP token. Mutually exclusive with `--user` in practice: if `--token` is provided, it takes precedence. |

### Authentication Precedence

The authentication logic in `enterprise_fizzbuzz/__main__.py` follows this precedence:

1. **`--token` is present:** Token-based authentication. The token is validated via `FizzBuzzTokenEngine.validate_token()`. If validation fails, the process exits with return code 1.
2. **`--user` is present (no `--token`):** Trust-mode authentication. An `AuthContext` is constructed directly with `trust_mode=True`. The role is taken from `--role` if provided, otherwise from the config default.
3. **Neither `--token` nor `--user`, but RBAC is enabled in config:** The user is set to `"anonymous"` with the default role. `trust_mode` is `False`.
4. **RBAC is not enabled and no auth flags are provided:** No `AuthContext` is created. The `AuthorizationMiddleware` is not added to the pipeline.

### Trust-Mode Warning

When trust-mode authentication is activated, the platform emits a warning to standard
output:

```
+---------------------------------------------------------+
| WARNING: Trust-mode authentication enabled.             |
| The user's identity has not been cryptographically      |
| verified. This is the security equivalent of writing    |
| your password on a Post-It note and sticking it to     |
| your monitor. Proceed with existential dread.          |
+---------------------------------------------------------+
```

This warning is not suppressible. The existential dread is mandatory.

---

## Authorization Middleware

### Class: `AuthorizationMiddleware`

**Module:** `enterprise_fizzbuzz/infrastructure/auth.py`
**Interface:** `IMiddleware` (from `enterprise_fizzbuzz/domain/interfaces`)
**Priority:** `-10`

The `AuthorizationMiddleware` runs before all other middleware in the pipeline. Its
priority of -10 ensures that unauthorized requests are rejected before any downstream
processing occurs — there is no point in breaking a circuit if the user does not have
permission to close it in the first place.

### Behavior

For each number processed through the pipeline, the middleware:

1. **Constructs the required permission.** The required permission is always `numbers:<N>:evaluate`, where `<N>` is the number being processed.

2. **Checks all effective permissions.** Iterates over the `AuthContext.effective_permissions` tuple and calls `PermissionParser.matches()` for each granted permission against the required permission.

3. **On success:**
   - Publishes an `AUTHORIZATION_GRANTED` event to the event bus (if available).
   - Stamps `context.metadata["auth_user"]` and `context.metadata["auth_role"]` on the processing context.
   - Passes the context to the next handler in the chain.

4. **On failure:**
   - Builds the 47-field access denied response via `AccessDeniedResponseBuilder.build()`.
   - Publishes an `AUTHORIZATION_DENIED` event to the event bus (if available).
   - Raises `InsufficientFizzPrivilegesError` with the denial body attached. The exception message includes a motivational quote selected from the denial response.

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `auth_context` | `AuthContext` | *(required)* | The authenticated user's context. |
| `contact_email` | `str` | `fizzbuzz-security@enterprise.example.com` | HR/security contact included in denial responses. |
| `next_training_session` | `str` | `2026-04-01T09:00:00Z` | Next available RBAC training session date. |
| `event_bus` | `Any \| None` | `None` | Optional event bus for publishing authorization events. |

---

## Access Denied Response Specification

When a user is denied access to a FizzBuzz evaluation, the `AccessDeniedResponseBuilder.build()`
method constructs a response body containing exactly 47 fields. This count is enforced
by a runtime assertion. It was established by the FizzBuzz Security Council in a meeting
that ran 47 minutes over schedule, and the irony was not lost on anyone.

### Field Reference

The following table lists all 47 fields in their construction order, grouped by category.

#### Fields 1-5: Core Denial Information

| # | Field | Type | Source |
|---|-------|------|--------|
| 1 | `denied` | `bool` | Always `True`. |
| 2 | `denial_reason` | `str` | Constructed from user, role, required permission, and number. |
| 3 | `denial_code` | `str` | Always `"EFP-A001"`. |
| 4 | `denial_timestamp` | `str` | ISO 8601 UTC timestamp at time of denial. |
| 5 | `denial_id` | `str` | The `request_id` parameter, or a generated UUID v4. |

#### Fields 6-10: User Information

| # | Field | Type | Source |
|---|-------|------|--------|
| 6 | `user` | `str` | The denied user's identifier. |
| 7 | `user_role` | `str` | The `FizzBuzzRole` enum name (e.g., `"FIZZ_READER"`). |
| 8 | `user_role_display_name` | `str` | Title-cased role name with underscores replaced by spaces (e.g., `"Fizz Reader"`). |
| 9 | `user_trust_score` | `float` | Computed as `(granted_permissions_count / max(len(FizzBuzzRole), 1)) * 42.0 + (0.1 if number is prime else 0.0)`, rounded to 4 decimal places. Completely meaningless. |
| 10 | `user_permissions_count` | `int` | Number of effective permissions the user holds. |

#### Fields 11-15: Permission Details

| # | Field | Type | Source |
|---|-------|------|--------|
| 11 | `required_permission` | `str` | The permission string that was required (e.g., `"numbers:15:evaluate"`). |
| 12 | `granted_permissions` | `list[str]` | All permissions the user currently holds, as formatted strings. |
| 13 | `permission_gap` | `str` | A `"Missing: ..."` string identifying the specific permission deficit. |
| 14 | `permission_model_version` | `str` | Always `"3.1.4"`. The digits of pi, because the permission model is irrational. |
| 15 | `rbac_policy_revision` | `str` | Always `"rev-2026-03-15"`. |

#### Fields 16-20: Number Analysis

| # | Field | Type | Source |
|---|-------|------|--------|
| 16 | `requested_number` | `int` | The number the user attempted to evaluate. |
| 17 | `number_is_prime` | `bool` | Whether the requested number is prime, computed by `_is_prime()`. |
| 18 | `number_is_even` | `bool` | Whether the requested number is even (`n % 2 == 0`). |
| 19 | `number_would_be_fizz` | `bool` | Whether the number is divisible by 3. |
| 20 | `number_would_be_buzz` | `bool` | Whether the number is divisible by 5. |

#### Fields 21-25: Number Analysis (Continued)

| # | Field | Type | Source |
|---|-------|------|--------|
| 21 | `number_would_be_fizzbuzz` | `bool` | Whether the number is divisible by both 3 and 5. |
| 22 | `number_binary` | `str` | Binary representation of the number (`bin(n)`). |
| 23 | `number_hexadecimal` | `str` | Hexadecimal representation of the number (`hex(n)`). |
| 24 | `number_roman_numeral_available` | `bool` | Whether the number falls in the range 1-3999, where Roman numeral conversion is defined. |
| 25 | `number_factors_count` | `int` | Total number of factors of the requested number. Computed by trial division. Returns 0 if the number is 0. |

#### Fields 26-30: Remediation Guidance

| # | Field | Type | Source |
|---|-------|------|--------|
| 26 | `suggested_role_upgrade_path` | `str` | The next role in the upgrade path, from `RoleRegistry.get_suggested_upgrade_path()`. |
| 27 | `hr_contact_email` | `str` | The `contact_email` parameter. Defaults to `fizzbuzz-security@enterprise.example.com`. |
| 28 | `next_available_training_session` | `str` | The `next_training_session` parameter. Defaults to `2026-04-01T09:00:00Z`. |
| 29 | `escalation_procedure` | `str` | A four-step procedure: file ServiceNow ticket, obtain manager approval, complete RBAC training, wait 3-5 business days. |
| 30 | `self_service_portal_url` | `str` | Always `https://fizzbuzz-iam.enterprise.example.com/request-access`. |

#### Fields 31-35: Incident Management

| # | Field | Type | Source |
|---|-------|------|--------|
| 31 | `incident_auto_filed` | `bool` | Always `True`. Every denial automatically files an incident. |
| 32 | `incident_id` | `str` | Format: `INC-<first 8 chars of request_id, uppercased>`. |
| 33 | `incident_severity` | `str` | Always `"P4 - Cosmetic"`. Access denials are, officially, a cosmetic issue. |
| 34 | `incident_assigned_to` | `str` | Always `"FizzBuzz Security Team"`. |
| 35 | `sla_response_time_hours` | `int` | Always `72`. Three business days to respond to a FizzBuzz access denial. |

#### Fields 36-40: Compliance and Audit

| # | Field | Type | Source |
|---|-------|------|--------|
| 36 | `compliance_frameworks` | `list[str]` | Always `["SOC2", "ISO27001", "FizzBuzz-RBAC-v2"]`. |
| 37 | `audit_trail_enabled` | `bool` | Always `True`. |
| 38 | `data_classification` | `str` | Always `"FIZZBUZZ-INTERNAL"`. |
| 39 | `legal_disclaimer` | `str` | A disclaimer noting that the access denial is provided "as-is" without warranty, and that the platform assumes no liability for emotional distress caused by insufficient privileges. |
| 40 | `retention_period_days` | `int` | Always `365`. Denial records are retained for one year. |

#### Fields 41-45: Metadata and Miscellaneous

| # | Field | Type | Source |
|---|-------|------|--------|
| 41 | `platform_version` | `str` | Always `"1.0.0"`. |
| 42 | `rbac_engine_version` | `str` | Always `"1.0.0"`. |
| 43 | `motivational_quote` | `str` | Randomly selected from a list of seven quotes. Examples include "Every 'Access Denied' is just a 'Not Yet' in disguise" and "Access is not given. Access is earned. Through a ServiceNow ticket." |
| 44 | `support_ticket_url` | `str` | Format: `https://support.enterprise.example.com/tickets/<request_id>`. |
| 45 | `denial_appeal_deadline_utc` | `str` | Computed as the current day + 30, capped at the 28th. An approximate deadline that avoids calendar edge cases by ignoring them. |

#### Fields 46-47: API Response Metadata

| # | Field | Type | Source |
|---|-------|------|--------|
| 46 | `response_content_type` | `str` | Always `"application/fizzbuzz-denial+json"`. A proprietary MIME type for FizzBuzz denial payloads. |
| 47 | `cache_control` | `str` | Always `"no-store, no-cache, must-revalidate, fizzbuzz-private"`. Access denials must never be cached. The `fizzbuzz-private` directive is not an RFC-standard cache directive, but the platform is not an RFC-standard platform. |

### Field Count Enforcement

The `AccessDeniedResponseBuilder.build()` method includes a runtime assertion:

```python
assert len(body) == 47, (
    f"Access denied response body has {len(body)} fields, "
    f"but exactly 47 are required. The FizzBuzz Security Council "
    f"will not be pleased."
)
```

Adding or removing a field without maintaining the count of 47 will result in an
`AssertionError`. The FizzBuzz Security Council will not be pleased.

---

## Configuration

The RBAC system is configured through the following surfaces. See
[docs/configuration.md](configuration.md) for complete configuration reference.

| Config Key | CLI Flag | Default | Description |
|-----------|----------|---------|-------------|
| `auth.enabled` | *(none)* | `true` | Whether RBAC enforcement is active when no auth flags are provided. |
| `auth.default_role` | *(none)* | `ANONYMOUS` | The role assigned when RBAC is enabled but no `--user` or `--token` is provided. |
| `auth.token_secret` | *(none)* | *(configured)* | The HMAC-SHA256 signing secret for token generation and validation. |

---

## Compliance

The RBAC module declares compliance with the following frameworks, as documented in
the module docstring and the access denied response:

| Framework | Scope |
|-----------|-------|
| SOC 2 Type II | Access controls for FizzBuzz operations |
| GDPR | Right to be forgotten (but not right to be FizzBuzzed) |
| ISO 27001 | Information security for modulo arithmetic |
| PCI DSS | Payment Card Industry standards (FizzBuzz is priceless) |
| FizzBuzz-RBAC-v2 | The platform's own RBAC policy framework |

These compliance claims have not been independently audited. The platform's legal
counsel has advised that compliance with FizzBuzz-RBAC-v2 is self-certifying, on the
grounds that no external auditor has agreed to review it.

---

## Container Security

The containerization layer implements defense-in-depth security controls at every tier
of the container stack. These controls ensure that the isolation, integrity, and
auditability guarantees of the platform extend from the application layer down through
the container runtime to the kernel resource boundaries.

### Image Vulnerability Scanning

FizzImage (`enterprise_fizzbuzz/infrastructure/fizzimage.py`) scans every container
image against a simulated CVE database before the image enters the FizzRegistry. The
scanning pipeline:

1. **Dependency extraction**: AST-based analysis identifies all Python imports in the
   image's module tree, building a complete dependency graph.
2. **CVE matching**: Each dependency is checked against known vulnerabilities in the
   simulated CVE database. Matches produce a severity-scored finding (CRITICAL, HIGH,
   MEDIUM, LOW).
3. **Policy enforcement**: Images with CRITICAL vulnerabilities are rejected from the
   registry. HIGH vulnerabilities generate a warning but permit publication. MEDIUM
   and LOW findings are logged for audit.
4. **Continuous re-scanning**: The FizzImage catalog periodically re-scans published
   images when the CVE database is updated, flagging newly discovered vulnerabilities
   in previously clean images.

FizzDeploy (`enterprise_fizzbuzz/infrastructure/fizzdeploy.py`) enforces a mandatory
scan gate in its deployment pipeline. The SCAN stage must pass before the SIGN stage
can proceed. Deployments referencing unscanned images are rejected.

### Non-Root Containers

FizzOCI (`enterprise_fizzbuzz/infrastructure/fizzoci.py`) enforces non-root execution
by default. During container creation:

1. The OCI runtime configuration (`config.json`) specifies the container's UID and GID.
   The platform default maps the container process to a non-privileged user.
2. FizzNS (`enterprise_fizzbuzz/infrastructure/fizzns.py`) configures USER namespace
   mappings so that UID 0 inside the container maps to an unprivileged UID on the host.
   This provides root-like behavior within the container's isolated view while
   preventing privilege escalation to the host.
3. FizzOverlay (`enterprise_fizzbuzz/infrastructure/fizzoverlay.py`) sets the upper
   (writable) layer permissions to the mapped non-root UID, preventing unauthorized
   writes to the container filesystem from other processes.

### Seccomp Profiles

FizzOCI applies seccomp (secure computing mode) syscall filtering during container
creation. The seccomp profile:

1. Operates in whitelist mode: only explicitly permitted system calls are allowed.
   All others return `EPERM`.
2. The default profile permits the minimal set of syscalls required for Python process
   execution, including `read`, `write`, `open`, `close`, `mmap`, `brk`, `futex`,
   and `clock_gettime`.
3. Dangerous syscalls are blocked: `mount`, `umount`, `ptrace`, `reboot`,
   `init_module`, `delete_module`, `sethostname`, and `pivot_root` are denied by
   default.
4. Custom seccomp profiles can be specified per container in the OCI runtime
   configuration for subsystems with specialized syscall requirements.

### Network Policies

FizzCNI (`enterprise_fizzbuzz/infrastructure/fizzcni.py`) implements network policy
enforcement via label-based microsegmentation:

1. **Default deny**: Containers without an explicit network policy receive no inbound
   connectivity from other containers. Outbound traffic to the compose network is
   permitted by default.
2. **Label selectors**: Network policies match containers by labels (e.g.,
   `group=security`, `tier=data`). A policy specifying `allow: { from: { group: core } }`
   permits inbound traffic only from containers labeled `group=core`.
3. **Port-level rules**: Policies can restrict allowed ports. A container exposing
   port 8080 can have a policy that only permits inbound connections on that port from
   specific label groups.
4. **Policy evaluation order**: Policies are evaluated in specificity order. A
   container-specific policy overrides a namespace-wide policy. Conflicting policies
   result in the most restrictive rule being applied.

### Capability-Based Security Integration

FizzOCI integrates with the platform's capability security system (`fizzcap.py`) to
enforce the principle of least privilege at the Linux capability level:

1. During container creation, FizzOCI drops all Linux capabilities except those
   explicitly required by the container's workload.
2. The default capability set retains only `CAP_NET_BIND_SERVICE` (for containers
   that bind to privileged ports) and `CAP_SETUID`/`CAP_SETGID` (for user namespace
   setup). All other capabilities, including `CAP_SYS_ADMIN`, `CAP_NET_RAW`, and
   `CAP_SYS_PTRACE`, are dropped.
3. Containers requesting elevated capabilities must declare them in the OCI runtime
   configuration. FizzDeploy's security review stage flags any deployment manifest
   that requests capabilities beyond the default set.

### Container Security Audit Trail

Every security-relevant container operation is recorded in the audit trail:

| Operation | Audit Record |
|-----------|-------------|
| Image scan result | Image name, scan timestamp, CVE findings with severity |
| Container creation | Container ID, image digest, seccomp profile, capability set, UID/GID mapping |
| Network policy evaluation | Container ID, source/destination, policy match result, allowed/denied |
| Capability request | Container ID, requested capabilities, granted/denied |
| Deployment security gate | Deployment ID, scan result, signature verification, policy compliance |

The audit trail is accessible through FizzContainerOps' structured log aggregation
system, supporting both real-time monitoring and post-incident forensic analysis.

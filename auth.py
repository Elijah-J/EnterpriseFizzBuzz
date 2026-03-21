"""
Enterprise FizzBuzz Platform - Role-Based Access Control (RBAC) Module

Implements a comprehensive, enterprise-grade authorization framework
for controlling access to FizzBuzz evaluation operations. Because the
ability to compute n % 3 is a privilege, not a right.

Features:
    - Five-tier role hierarchy (ANONYMOUS through FIZZBUZZ_SUPERUSER)
    - Permission-based access control with range specifications
    - HMAC-SHA256 token authentication (JWT-adjacent, but more enterprise)
    - 47-field access denied response body (the number is sacred)
    - Middleware integration for the processing pipeline

Design Patterns Employed:
    - Role-Based Access Control (NIST RBAC)
    - Chain of Responsibility (permission inheritance)
    - Builder (access denied response construction)
    - Middleware Pipeline (authorization checks)
    - Token-based Authentication (homegrown, as is tradition)

Compliance:
    - SOC 2 Type II: Access controls for FizzBuzz operations
    - GDPR: Right to be forgotten (but not right to be FizzBuzzed)
    - ISO 27001: Information security for modulo arithmetic
    - PCI DSS: Payment Card Industry standards (FizzBuzz is priceless)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from exceptions import (
    AuthenticationError,
    InsufficientFizzPrivilegesError,
    NumberClassificationLevelExceededError,
    TokenValidationError,
)
from interfaces import IMiddleware
from models import (
    AuthContext,
    Event,
    EventType,
    FizzBuzzRole,
    Permission,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Permission Parser
# ============================================================


class PermissionParser:
    """Parses and matches FizzBuzz permission strings.

    Permission strings follow the format: resource:range_spec:action

    Examples:
        "numbers:1-50:evaluate"   - Evaluate numbers 1 through 50
        "numbers:fizz:read"       - Read multiples of 3
        "numbers:buzz:configure"  - Configure multiples of 5
        "numbers:*:evaluate"      - Evaluate any number (the dream)

    Range specifications:
        "*"         - All numbers (the wildcard of power)
        "1-50"      - Inclusive numeric range
        "fizz"      - Multiples of 3 (the chosen ones)
        "buzz"      - Multiples of 5 (the other chosen ones)
        "fizzbuzz"  - Multiples of both 3 and 5 (the elite)
        "42"        - A single number (the answer)
    """

    @staticmethod
    def parse(permission_str: str) -> Permission:
        """Parse a permission string into a Permission object.

        Args:
            permission_str: A colon-separated permission string
                           (e.g., "numbers:1-50:evaluate").

        Returns:
            A Permission object with resource, range_spec, and action.

        Raises:
            ValueError: If the permission string is malformed.
        """
        parts = permission_str.strip().split(":")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid permission format: {permission_str!r}. "
                f"Expected 'resource:range_spec:action'. "
                f"This is not a freestyle permission — structure matters."
            )
        return Permission(resource=parts[0], range_spec=parts[1], action=parts[2])

    @staticmethod
    def matches(granted: Permission, required: Permission) -> bool:
        """Check if a granted permission covers a required permission.

        A granted permission "covers" a required permission when:
        1. The resources match exactly
        2. The granted range includes the required range
        3. The actions match exactly

        Args:
            granted: The permission the user actually has.
            required: The permission the user needs.

        Returns:
            True if the granted permission satisfies the requirement.
        """
        # Resources must match
        if granted.resource != required.resource:
            return False

        # Actions must match
        if granted.action != required.action:
            return False

        # Range matching
        return PermissionParser._range_covers(granted.range_spec, required.range_spec)

    @staticmethod
    def _range_covers(granted_range: str, required_range: str) -> bool:
        """Check if the granted range specification covers the required range.

        The wildcard '*' covers everything. Named classes (fizz, buzz,
        fizzbuzz) cover specific multiples. Numeric ranges cover their
        inclusive span.
        """
        # Wildcard covers everything — the ultimate privilege
        if granted_range == "*":
            return True

        # If required is wildcard, only wildcard can satisfy it
        if required_range == "*":
            return False

        # Try to interpret required_range as a single number for matching
        required_number = PermissionParser._try_parse_single_number(required_range)

        if required_number is not None:
            return PermissionParser._range_contains_number(granted_range, required_number)

        # If required range is a named class or range, check for exact match
        # or containment
        if granted_range == required_range:
            return True

        return False

    @staticmethod
    def _try_parse_single_number(range_spec: str) -> Optional[int]:
        """Try to parse a range spec as a single number."""
        try:
            return int(range_spec)
        except ValueError:
            return None

    @staticmethod
    def _range_contains_number(range_spec: str, number: int) -> bool:
        """Check if a range specification contains a specific number.

        Supports:
            "*"         -> contains everything
            "1-50"      -> contains numbers 1 through 50 inclusive
            "fizz"      -> contains multiples of 3
            "buzz"      -> contains multiples of 5
            "fizzbuzz"  -> contains multiples of both 3 and 5
            "42"        -> contains only 42
        """
        if range_spec == "*":
            return True

        # Named class: fizzbuzz (must check before fizz/buzz)
        if range_spec == "fizzbuzz":
            return number % 3 == 0 and number % 5 == 0

        # Named class: fizz
        if range_spec == "fizz":
            return number % 3 == 0

        # Named class: buzz
        if range_spec == "buzz":
            return number % 5 == 0

        # Numeric range: "start-end"
        if "-" in range_spec:
            parts = range_spec.split("-", 1)
            try:
                start = int(parts[0])
                end = int(parts[1])
                return start <= number <= end
            except (ValueError, IndexError):
                return False

        # Single number
        try:
            return int(range_spec) == number
        except ValueError:
            return False


# ============================================================
# Role Registry
# ============================================================


class RoleRegistry:
    """Registry of FizzBuzz roles, their permissions, and hierarchy.

    Implements a role hierarchy where each role inherits all permissions
    from its parent roles. The hierarchy is carefully designed to ensure
    that only the most trusted individuals can evaluate FizzBuzz across
    the full numeric range.

    Role Hierarchy:
        ANONYMOUS
          └── FIZZ_READER
                ├── BUZZ_ADMIN
                │     └── FIZZBUZZ_SUPERUSER
                └── NUMBER_AUDITOR
    """

    # Role hierarchy: child -> parent
    _HIERARCHY: dict[FizzBuzzRole, Optional[FizzBuzzRole]] = {
        FizzBuzzRole.ANONYMOUS: None,
        FizzBuzzRole.FIZZ_READER: FizzBuzzRole.ANONYMOUS,
        FizzBuzzRole.BUZZ_ADMIN: FizzBuzzRole.FIZZ_READER,
        FizzBuzzRole.FIZZBUZZ_SUPERUSER: FizzBuzzRole.BUZZ_ADMIN,
        FizzBuzzRole.NUMBER_AUDITOR: FizzBuzzRole.FIZZ_READER,
    }

    # Direct permissions for each role (not including inherited)
    _DIRECT_PERMISSIONS: dict[FizzBuzzRole, list[str]] = {
        FizzBuzzRole.ANONYMOUS: [
            "numbers:1:read",
        ],
        FizzBuzzRole.FIZZ_READER: [
            "numbers:fizz:read",
            "numbers:1-50:evaluate",
        ],
        FizzBuzzRole.BUZZ_ADMIN: [
            "numbers:buzz:read",
            "numbers:buzz:configure",
            "numbers:1-100:evaluate",
        ],
        FizzBuzzRole.FIZZBUZZ_SUPERUSER: [
            "numbers:*:evaluate",
            "numbers:*:read",
            "numbers:*:configure",
        ],
        FizzBuzzRole.NUMBER_AUDITOR: [
            "numbers:*:audit",
            "numbers:*:read",
        ],
    }

    # Suggested upgrade path for each role
    _UPGRADE_PATH: dict[FizzBuzzRole, FizzBuzzRole] = {
        FizzBuzzRole.ANONYMOUS: FizzBuzzRole.FIZZ_READER,
        FizzBuzzRole.FIZZ_READER: FizzBuzzRole.BUZZ_ADMIN,
        FizzBuzzRole.BUZZ_ADMIN: FizzBuzzRole.FIZZBUZZ_SUPERUSER,
        FizzBuzzRole.NUMBER_AUDITOR: FizzBuzzRole.FIZZBUZZ_SUPERUSER,
        FizzBuzzRole.FIZZBUZZ_SUPERUSER: FizzBuzzRole.FIZZBUZZ_SUPERUSER,
    }

    @classmethod
    def get_effective_permissions(cls, role: FizzBuzzRole) -> list[Permission]:
        """Get all effective permissions for a role, including inherited.

        Walks up the role hierarchy collecting permissions from each
        ancestor role, because in enterprise RBAC, privilege is inherited
        like a family fortune — except it's modulo arithmetic instead of money.

        Args:
            role: The FizzBuzz role to resolve permissions for.

        Returns:
            A deduplicated list of all effective Permission objects.
        """
        seen: set[str] = set()
        permissions: list[Permission] = []

        current: Optional[FizzBuzzRole] = role
        while current is not None:
            for perm_str in cls._DIRECT_PERMISSIONS.get(current, []):
                if perm_str not in seen:
                    seen.add(perm_str)
                    permissions.append(PermissionParser.parse(perm_str))
            current = cls._HIERARCHY.get(current)

        return permissions

    @classmethod
    def get_suggested_upgrade_path(cls, role: FizzBuzzRole) -> FizzBuzzRole:
        """Suggest the next role upgrade for a user.

        When a user is denied access, we helpfully suggest which role
        they should request from their FizzBuzz administrator. Because
        in enterprise software, every denial is also a sales opportunity.

        Args:
            role: The user's current role.

        Returns:
            The recommended next role in the hierarchy.
        """
        return cls._UPGRADE_PATH.get(role, FizzBuzzRole.FIZZBUZZ_SUPERUSER)


# ============================================================
# Token Engine
# ============================================================


class FizzBuzzTokenEngine:
    """Enterprise FizzBuzz Platform token engine.

    Generates and validates authentication tokens using HMAC-SHA256.
    The token format is EFP.<base64url_payload>.<hmac_sha256_hex>,
    which is suspiciously similar to JWT but legally distinct enough
    to avoid licensing fees.

    Token Payload Fields:
        sub:                    Subject (username)
        role:                   FizzBuzz role name
        iat:                    Issued at (Unix timestamp)
        exp:                    Expiration (Unix timestamp)
        jti:                    Token ID (UUID)
        iss:                    Issuer
        fizz_clearance_level:   Clearance for Fizz operations (1-5)
        buzz_clearance_level:   Clearance for Buzz operations (1-5)
        favorite_prime:         The user's favorite prime number
    """

    # Clearance levels by role (because security needs layers)
    _CLEARANCE_LEVELS: dict[FizzBuzzRole, tuple[int, int]] = {
        FizzBuzzRole.ANONYMOUS: (0, 0),
        FizzBuzzRole.FIZZ_READER: (2, 0),
        FizzBuzzRole.BUZZ_ADMIN: (2, 4),
        FizzBuzzRole.FIZZBUZZ_SUPERUSER: (5, 5),
        FizzBuzzRole.NUMBER_AUDITOR: (3, 3),
    }

    # A curated selection of primes for the favorite_prime field
    _FAVORITE_PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]

    @classmethod
    def generate_token(
        cls,
        user: str,
        role: FizzBuzzRole,
        secret: str,
        ttl_seconds: int = 3600,
        issuer: str = "enterprise-fizzbuzz-platform",
    ) -> str:
        """Generate a new authentication token.

        Creates a cryptographically signed token that encodes the user's
        identity and role. The token is valid for ttl_seconds, after which
        it expires and the user must re-authenticate — because even
        FizzBuzz privileges should be ephemeral.

        Args:
            user: The username to encode in the token.
            role: The FizzBuzz role to assign.
            secret: The HMAC signing secret.
            ttl_seconds: Token time-to-live in seconds.
            issuer: The token issuer identifier.

        Returns:
            A signed token string in EFP format.
        """
        now = time.time()
        fizz_cl, buzz_cl = cls._CLEARANCE_LEVELS.get(role, (0, 0))

        payload = {
            "sub": user,
            "role": role.name,
            "iat": now,
            "exp": now + ttl_seconds,
            "jti": str(uuid.uuid4()),
            "iss": issuer,
            "fizz_clearance_level": fizz_cl,
            "buzz_clearance_level": buzz_cl,
            "favorite_prime": random.choice(cls._FAVORITE_PRIMES),
        }

        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

        signature = hmac.new(
            secret.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()

        return f"EFP.{payload_b64}.{signature}"

    @classmethod
    def validate_token(cls, token: str, secret: str) -> AuthContext:
        """Validate a token and extract the authentication context.

        Performs the following validation checks:
        1. Token format (must be EFP.<payload>.<signature>)
        2. HMAC signature verification (tamper detection)
        3. Expiration check (time waits for no FizzBuzz)
        4. Required fields (all payload fields must be present)

        Args:
            token: The token string to validate.
            secret: The HMAC signing secret.

        Returns:
            An AuthContext with the authenticated user's information.

        Raises:
            TokenValidationError: If the token is invalid for any reason.
        """
        # Step 1: Format check
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "EFP":
            raise TokenValidationError(
                "Invalid token format. Expected 'EFP.<payload>.<signature>'. "
                "This is not a FizzBuzz token — it might be a JWT, a grocery "
                "receipt, or a cry for help."
            )

        _, payload_b64, provided_signature = parts

        # Step 2: Signature verification
        expected_signature = hmac.new(
            secret.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(provided_signature, expected_signature):
            raise TokenValidationError(
                "Token signature mismatch. The token has been tampered with, "
                "or the signing secret has changed. Either way, trust is broken."
            )

        # Step 3: Decode payload
        try:
            # Add back padding
            padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(padded).decode()
            payload = json.loads(payload_json)
        except (ValueError, json.JSONDecodeError) as e:
            raise TokenValidationError(
                f"Failed to decode token payload: {e}. The base64 is broken, "
                f"which is impressive given how simple base64 is."
            )

        # Step 4: Required fields
        required_fields = ["sub", "role", "iat", "exp", "jti", "iss"]
        missing = [f for f in required_fields if f not in payload]
        if missing:
            raise TokenValidationError(
                f"Token payload missing required fields: {missing}. "
                f"A proper FizzBuzz token requires all fields. No shortcuts."
            )

        # Step 5: Expiration check
        if payload["exp"] < time.time():
            raise TokenValidationError(
                "Token has expired. Your FizzBuzz privileges have lapsed. "
                "Please re-authenticate or contact your FizzBuzz administrator "
                "for a fresh token."
            )

        # Step 6: Role resolution
        try:
            role = FizzBuzzRole[payload["role"]]
        except KeyError:
            raise TokenValidationError(
                f"Unknown role in token: {payload['role']!r}. "
                f"Valid roles are: {[r.name for r in FizzBuzzRole]}."
            )

        # Build auth context
        effective_permissions = RoleRegistry.get_effective_permissions(role)

        return AuthContext(
            user=payload["sub"],
            role=role,
            token_id=payload.get("jti"),
            effective_permissions=tuple(effective_permissions),
            trust_mode=False,
        )


# ============================================================
# Access Denied Response Builder
# ============================================================


def _is_prime(n: int) -> bool:
    """Check if a number is prime.

    A helper function that determines primality, because when denying
    access to a FizzBuzz evaluation, we must also inform the user
    whether the number they were trying to evaluate was prime. This
    information is critical for the 47-field access denied response.

    Args:
        n: The number to check for primality.

    Returns:
        True if n is prime, False otherwise.
    """
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


class AccessDeniedResponseBuilder:
    """Builds the sacred 47-field access denied response body.

    When a user is denied access to a FizzBuzz evaluation, they deserve
    a comprehensive, informative, and slightly passive-aggressive response
    that includes every conceivable piece of information about their
    denial — plus some that are entirely inconceivable.

    The 47-field requirement is non-negotiable. It was established by
    the FizzBuzz Security Council in a meeting that ran 47 minutes
    over schedule, and the irony was not lost on anyone.
    """

    # Motivational quotes for denied users
    _MOTIVATIONAL_QUOTES = [
        "Every 'Access Denied' is just a 'Not Yet' in disguise.",
        "The journey of a thousand FizzBuzzes begins with a single permission grant.",
        "Today's ANONYMOUS is tomorrow's FIZZBUZZ_SUPERUSER.",
        "They told me I couldn't FizzBuzz. I'm still proving them right.",
        "Access is not given. Access is earned. Through a ServiceNow ticket.",
        "In a world of access denials, be a permission grant.",
        "Fall seven times, get denied eight.",
    ]

    # Legal disclaimers
    _LEGAL_DISCLAIMER = (
        "This access denial is provided 'as-is' without warranty of any kind, "
        "express or implied. The Enterprise FizzBuzz Platform assumes no liability "
        "for emotional distress caused by insufficient privileges. Any resemblance "
        "to actual access control systems, living or dead, is purely coincidental."
    )

    @classmethod
    def build(
        cls,
        number: int,
        user: str,
        role: FizzBuzzRole,
        required_permission: Permission,
        granted_permissions: list[Permission],
        contact_email: str = "fizzbuzz-security@enterprise.example.com",
        next_training_session: str = "2026-04-01T09:00:00Z",
        request_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build the sacred 47-field access denied response body.

        Every field in this response serves a critical enterprise purpose,
        from the denial timestamp to the user's trust score to whether
        the forbidden number is prime. All 47 fields. No more, no less.

        Args:
            number: The number the user was trying to evaluate.
            user: The denied user's identifier.
            role: The user's current role.
            required_permission: The permission that was required.
            granted_permissions: The permissions the user actually has.
            contact_email: HR/security contact email.
            next_training_session: Next available RBAC training session.
            request_id: Optional request identifier for correlation.

        Returns:
            A dict with exactly 47 fields. This is tested. Don't mess it up.
        """
        now = datetime.now(timezone.utc)
        req_id = request_id or str(uuid.uuid4())
        suggested_upgrade = RoleRegistry.get_suggested_upgrade_path(role)

        # Calculate a completely meaningless trust score
        trust_score = round(
            (len(granted_permissions) / max(len(FizzBuzzRole), 1)) * 42.0
            + (0.1 if _is_prime(number) else 0.0),
            4,
        )

        # Build the sacred 47-field response
        body: dict[str, Any] = {
            # Field 1-5: Core denial information
            "denied": True,
            "denial_reason": (
                f"User '{user}' with role '{role.name}' lacks permission "
                f"'{required_permission.resource}:{required_permission.range_spec}:"
                f"{required_permission.action}' for number {number}."
            ),
            "denial_code": "EFP-A001",
            "denial_timestamp": now.isoformat(),
            "denial_id": req_id,

            # Field 6-10: User information
            "user": user,
            "user_role": role.name,
            "user_role_display_name": role.name.replace("_", " ").title(),
            "user_trust_score": trust_score,
            "user_permissions_count": len(granted_permissions),

            # Field 11-15: Permission details
            "required_permission": (
                f"{required_permission.resource}:{required_permission.range_spec}:"
                f"{required_permission.action}"
            ),
            "granted_permissions": [
                f"{p.resource}:{p.range_spec}:{p.action}" for p in granted_permissions
            ],
            "permission_gap": (
                f"Missing: {required_permission.resource}:{required_permission.range_spec}:"
                f"{required_permission.action}"
            ),
            "permission_model_version": "3.1.4",
            "rbac_policy_revision": "rev-2026-03-15",

            # Field 16-20: Number analysis
            "requested_number": number,
            "number_is_prime": _is_prime(number),
            "number_is_even": number % 2 == 0,
            "number_would_be_fizz": number % 3 == 0,
            "number_would_be_buzz": number % 5 == 0,

            # Field 21-25: Number analysis continued
            "number_would_be_fizzbuzz": number % 3 == 0 and number % 5 == 0,
            "number_binary": bin(number),
            "number_hexadecimal": hex(number),
            "number_roman_numeral_available": 0 < number < 4000,
            "number_factors_count": sum(1 for i in range(1, abs(number) + 1) if number % i == 0) if number != 0 else 0,

            # Field 26-30: Remediation guidance
            "suggested_role_upgrade_path": suggested_upgrade.name,
            "hr_contact_email": contact_email,
            "next_available_training_session": next_training_session,
            "escalation_procedure": (
                "1. File a ServiceNow ticket (CAT: FizzBuzz Access). "
                "2. Obtain manager approval. "
                "3. Complete RBAC training. "
                "4. Wait 3-5 business days."
            ),
            "self_service_portal_url": "https://fizzbuzz-iam.enterprise.example.com/request-access",

            # Field 31-35: Incident management
            "incident_auto_filed": True,
            "incident_id": f"INC-{req_id[:8].upper()}",
            "incident_severity": "P4 - Cosmetic",
            "incident_assigned_to": "FizzBuzz Security Team",
            "sla_response_time_hours": 72,

            # Field 36-40: Compliance and audit
            "compliance_frameworks": ["SOC2", "ISO27001", "FizzBuzz-RBAC-v2"],
            "audit_trail_enabled": True,
            "data_classification": "FIZZBUZZ-INTERNAL",
            "legal_disclaimer": cls._LEGAL_DISCLAIMER,
            "retention_period_days": 365,

            # Field 41-45: Metadata and miscellaneous
            "platform_version": "1.0.0",
            "rbac_engine_version": "1.0.0",
            "motivational_quote": random.choice(cls._MOTIVATIONAL_QUOTES),
            "support_ticket_url": f"https://support.enterprise.example.com/tickets/{req_id}",
            "denial_appeal_deadline_utc": (
                f"{now.year}-{now.month:02d}-{min(now.day + 30, 28):02d}T23:59:59Z"
            ),

            # Field 46-47: API response metadata
            "response_content_type": "application/fizzbuzz-denial+json",
            "cache_control": "no-store, no-cache, must-revalidate, fizzbuzz-private",
        }

        # Sanity check — the 47-field requirement is sacred
        assert len(body) == 47, (
            f"Access denied response body has {len(body)} fields, "
            f"but exactly 47 are required. The FizzBuzz Security Council "
            f"will not be pleased."
        )

        return body


# ============================================================
# Authorization Middleware
# ============================================================


class AuthorizationMiddleware(IMiddleware):
    """Middleware that enforces RBAC on every FizzBuzz evaluation.

    Intercepts processing requests in the middleware pipeline and
    verifies that the authenticated user has sufficient privileges
    to evaluate the requested number. Because in the Enterprise
    FizzBuzz Platform, not everyone gets to know what 15 % 3 is.

    Priority: -10 (runs before everything else, even circuit breakers,
    because there's no point in breaking a circuit if the user doesn't
    have permission to close it in the first place).
    """

    def __init__(
        self,
        auth_context: AuthContext,
        contact_email: str = "fizzbuzz-security@enterprise.example.com",
        next_training_session: str = "2026-04-01T09:00:00Z",
        event_bus: Optional[Any] = None,
    ) -> None:
        self._auth_context = auth_context
        self._contact_email = contact_email
        self._next_training_session = next_training_session
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Check authorization before allowing FizzBuzz evaluation.

        Constructs the required permission for the current number and
        checks it against the user's effective permissions. If the check
        fails, builds the sacred 47-field denial response and raises
        an InsufficientFizzPrivilegesError.

        Args:
            context: The processing context containing the number.
            next_handler: The next handler in the middleware chain.

        Returns:
            The processing context from the next handler, if authorized.

        Raises:
            InsufficientFizzPrivilegesError: If the user lacks permission.
        """
        number = context.number
        required = Permission(
            resource="numbers",
            range_spec=str(number),
            action="evaluate",
        )

        # Check all effective permissions
        granted_list = list(self._auth_context.effective_permissions)
        authorized = any(
            PermissionParser.matches(granted, required) for granted in granted_list
        )

        if authorized:
            # Publish authorization granted event
            self._publish_event(EventType.AUTHORIZATION_GRANTED, {
                "user": self._auth_context.user,
                "role": self._auth_context.role.name,
                "number": number,
                "permission": f"{required.resource}:{required.range_spec}:{required.action}",
            })
            context.metadata["auth_user"] = self._auth_context.user
            context.metadata["auth_role"] = self._auth_context.role.name
            return next_handler(context)

        # Access denied — build the sacred 47-field response
        denial_body = AccessDeniedResponseBuilder.build(
            number=number,
            user=self._auth_context.user,
            role=self._auth_context.role,
            required_permission=required,
            granted_permissions=granted_list,
            contact_email=self._contact_email,
            next_training_session=self._next_training_session,
        )

        # Publish authorization denied event
        self._publish_event(EventType.AUTHORIZATION_DENIED, {
            "user": self._auth_context.user,
            "role": self._auth_context.role.name,
            "number": number,
            "required_permission": f"{required.resource}:{required.range_spec}:{required.action}",
            "denial_id": denial_body.get("denial_id", "unknown"),
        })

        raise InsufficientFizzPrivilegesError(
            f"Access denied: user '{self._auth_context.user}' "
            f"(role: {self._auth_context.role.name}) cannot evaluate "
            f"number {number}. {denial_body.get('motivational_quote', '')}",
            denial_body=denial_body,
        )

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Publish an event to the event bus, if available."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="AuthorizationMiddleware",
            ))

    def get_name(self) -> str:
        return "AuthorizationMiddleware"

    def get_priority(self) -> int:
        return -10

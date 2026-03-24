"""Feature descriptor for the Role-Based Access Control (RBAC) subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class AuthFeature(FeatureDescriptor):
    name = "auth"
    description = "RBAC with trust-mode authentication, token validation, and authorization middleware"
    middleware_priority = 5
    cli_flags = [
        ("--user", {"type": str, "metavar": "USERNAME", "default": None,
                     "help": "Authenticate as the specified user (trust-mode, no token required)"}),
        ("--role", {"type": str, "default": None,
                    "help": "Assign the specified RBAC role (requires --user or --token)"}),
        ("--token", {"type": str, "metavar": "TOKEN", "default": None,
                     "help": "Authenticate using an Enterprise FizzBuzz Platform token"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            bool(getattr(args, "user", None)),
            bool(getattr(args, "token", None)),
            bool(getattr(args, "role", None)),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            FizzBuzzTokenEngine,
            RoleRegistry,
        )
        from enterprise_fizzbuzz.domain.models import AuthContext, FizzBuzzRole

        auth_context = None

        if args.token:
            auth_context = FizzBuzzTokenEngine.validate_token(
                args.token, config.rbac_token_secret
            )
        elif args.user:
            role = FizzBuzzRole[args.role] if args.role else FizzBuzzRole[config.rbac_default_role]
            effective_permissions = RoleRegistry.get_effective_permissions(role)
            auth_context = AuthContext(
                user=args.user,
                role=role,
                token_id=None,
                effective_permissions=tuple(effective_permissions),
                trust_mode=True,
            )
        elif config.rbac_enabled:
            role = FizzBuzzRole[config.rbac_default_role]
            effective_permissions = RoleRegistry.get_effective_permissions(role)
            auth_context = AuthContext(
                user="anonymous",
                role=role,
                token_id=None,
                effective_permissions=tuple(effective_permissions),
                trust_mode=False,
            )

        if auth_context is None:
            return None, None

        middleware = AuthorizationMiddleware(
            auth_context=auth_context,
            contact_email=config.rbac_access_denied_contact_email,
            next_training_session=config.rbac_next_training_session,
            event_bus=event_bus,
        )

        return auth_context, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None

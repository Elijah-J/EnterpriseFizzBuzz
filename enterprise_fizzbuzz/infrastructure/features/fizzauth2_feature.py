"""Feature descriptor for the FizzAuth2 OAuth 2.0/OIDC authorization server."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzAuth2Feature(FeatureDescriptor):
    name = "fizzauth2"
    description = "OAuth 2.0/OIDC authorization server with PKCE, JWT, JWKS, and device authorization"
    middleware_priority = 132
    cli_flags = [
        ("--fizzauth2", {"action": "store_true", "default": False, "help": "Enable FizzAuth2 OAuth 2.0/OIDC server"}),
        ("--fizzauth2-issuer", {"type": str, "default": "https://auth.fizzbuzz.local", "help": "Issuer URL"}),
        ("--fizzauth2-token-ttl", {"type": int, "default": 3600, "help": "Access token TTL in seconds"}),
        ("--fizzauth2-refresh-ttl", {"type": int, "default": 86400, "help": "Refresh token TTL in seconds"}),
        ("--fizzauth2-require-pkce", {"action": "store_true", "default": True, "help": "Require PKCE for auth code flow"}),
        ("--fizzauth2-clients", {"action": "store_true", "default": False, "help": "List registered OAuth clients"}),
        ("--fizzauth2-jwks", {"action": "store_true", "default": False, "help": "Display JWKS public keys"}),
        ("--fizzauth2-discovery", {"action": "store_true", "default": False, "help": "Display OIDC discovery document"}),
        ("--fizzauth2-sessions", {"action": "store_true", "default": False, "help": "List active sessions"}),
        ("--fizzauth2-authorize", {"type": str, "default": None, "help": "Simulate auth code flow (client_id)"}),
        ("--fizzauth2-token", {"type": str, "default": None, "help": "Exchange auth code for tokens"}),
        ("--fizzauth2-introspect", {"type": str, "default": None, "help": "Introspect a token"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzauth2", False), getattr(args, "fizzauth2_clients", False),
                    getattr(args, "fizzauth2_jwks", False), getattr(args, "fizzauth2_discovery", False),
                    getattr(args, "fizzauth2_authorize", None), getattr(args, "fizzauth2_token", None)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzauth2 import FizzAuth2Middleware, create_fizzauth2_subsystem
        server, dashboard, mw = create_fizzauth2_subsystem(
            issuer=config.fizzauth2_issuer, token_ttl=config.fizzauth2_token_ttl,
            refresh_ttl=config.fizzauth2_refresh_ttl, require_pkce=config.fizzauth2_require_pkce,
            dashboard_width=config.fizzauth2_dashboard_width,
        )
        return server, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzauth2_clients", False): parts.append(middleware.render_clients())
        if getattr(args, "fizzauth2_jwks", False): parts.append(middleware.render_jwks())
        if getattr(args, "fizzauth2_discovery", False): parts.append(middleware.render_discovery())
        if getattr(args, "fizzauth2_sessions", False): parts.append(middleware.render_sessions())
        if getattr(args, "fizzauth2_authorize", None): parts.append(middleware.render_authorize(args.fizzauth2_authorize))
        if getattr(args, "fizzauth2", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

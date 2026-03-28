"""
Enterprise FizzBuzz Platform - FizzAPIGateway2 Errors (EFP-GW2-00 .. EFP-GW2-08)

Exception hierarchy for the FizzAPIGateway2 full API gateway subsystem.
Covers route matching, request transformation, version management,
OpenAPI generation, and gateway engine failures.
"""

from __future__ import annotations

from ._base import FizzBuzzError


class FizzAPIGateway2Error(FizzBuzzError):
    """Base exception for all FizzAPIGateway2 errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzAPIGateway2 error: {reason}",
            error_code="EFP-GW2-00",
            context={"reason": reason},
        )


class FizzAPIGateway2RouteError(FizzAPIGateway2Error):
    """Raised when a route operation fails."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Route {path}: {reason}")
        self.error_code = "EFP-GW2-01"


class FizzAPIGateway2RouteNotFoundError(FizzAPIGateway2Error):
    """Raised when no route matches a request."""

    def __init__(self, method: str, path: str) -> None:
        super().__init__(f"No route: {method} {path}")
        self.error_code = "EFP-GW2-02"


class FizzAPIGateway2TransformError(FizzAPIGateway2Error):
    """Raised when request or response transformation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Transform: {reason}")
        self.error_code = "EFP-GW2-03"


class FizzAPIGateway2VersionError(FizzAPIGateway2Error):
    """Raised when API version management fails."""

    def __init__(self, version: str, reason: str) -> None:
        super().__init__(f"Version {version}: {reason}")
        self.error_code = "EFP-GW2-04"


class FizzAPIGateway2AuthError(FizzAPIGateway2Error):
    """Raised when authentication fails at the gateway."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Auth: {reason}")
        self.error_code = "EFP-GW2-05"


class FizzAPIGateway2RateLimitError(FizzAPIGateway2Error):
    """Raised when a request is rate-limited at the gateway."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Rate limited: {path}")
        self.error_code = "EFP-GW2-06"


class FizzAPIGateway2OpenAPIError(FizzAPIGateway2Error):
    """Raised when OpenAPI spec generation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"OpenAPI: {reason}")
        self.error_code = "EFP-GW2-07"


class FizzAPIGateway2ConfigError(FizzAPIGateway2Error):
    """Raised on configuration errors."""

    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}")
        self.error_code = "EFP-GW2-08"

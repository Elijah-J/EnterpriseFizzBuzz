"""
Enterprise FizzBuzz Platform - API Gateway with Routing, Versioning & Request Transformation

Implements a full-featured API Gateway for a CLI application that has no
HTTP server, no network stack, and no clients. The gateway provides:

- Path-based routing with version-aware route resolution
- Semantic API versioning (v1=DEPRECATED, v2=ACTIVE, v3=ACTIVE)
- Request transformation pipeline (normalizer, enricher, validator, deprecation injector)
- Response transformation pipeline (compressor, pagination wrapper, HATEOAS enricher)
- API key generation, validation, and quota management
- Append-only request replay journal
- GatewayMiddleware for integration with the middleware pipeline
- ASCII dashboard for gateway observability

The gateway faithfully implements every feature a real API gateway would
need, despite the inconvenient fact that all "requests" originate from
the same process that handles them. The request IDs are 340 characters
long because UUID v4's 36 characters were deemed insufficiently unique
for enterprise FizzBuzz operations.

All of this runs in a single process. In RAM. For modulo arithmetic.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import logging
import math
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    APIKeyInvalidError,
    APIKeyQuotaExceededError,
    GatewayDashboardRenderError,
    GatewayError,
    RequestReplayError,
    RequestTransformationError,
    ResponseTransformationError,
    RouteNotFoundError,
    VersionDeprecatedError,
    VersionNotSupportedError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The request ID must be exactly 340 characters, because UUID v4 was
# simply not enterprise enough. We achieve this by concatenating multiple
# UUIDs, a timestamp hash, a process ID hash, and padding with the
# SHA-256 of the word "enterprise" until we hit the target length.
_REQUEST_ID_TARGET_LENGTH = 340

# Deprecation warning messages that escalate in urgency for v1 users
_V1_DEPRECATION_WARNINGS = [
    "NOTICE: API v1 is deprecated. Please migrate to v2 or v3.",
    "WARNING: API v1 is deprecated. Migration is strongly recommended.",
    "URGENT: API v1 is deprecated. Your continued use has been noted in the audit log.",
    "CRITICAL: API v1 is DEPRECATED. The sunset date has PASSED. Please migrate IMMEDIATELY.",
    "EMERGENCY: API v1 is DEPRECATED and WILL BE REMOVED. This is not a drill. "
    "Bob McFizzington has been notified. Your manager has been CC'd. "
    "A calendar invite for a 'migration planning session' has been sent.",
]

# The lunar phases, because every enterprise request deserves to know
# what phase the moon is in when it was processed
_LUNAR_PHASES = [
    "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
    "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
]

# HATEOAS link relations that every self-respecting FizzBuzz API must include
_HATEOAS_RELATIONS = [
    ("self", "/api/{version}/fizzbuzz/{number}", "The current resource"),
    ("next", "/api/{version}/fizzbuzz/{next_number}", "The next number in sequence"),
    ("prev", "/api/{version}/fizzbuzz/{prev_number}", "The previous number in sequence"),
    ("collection", "/api/{version}/fizzbuzz/range", "Batch evaluation endpoint"),
    ("feelings", "/api/{version}/fizzbuzz/feelings", "How does the FizzBuzz engine feel?"),
    ("health", "/api/{version}/health", "Gateway health check"),
    ("metrics", "/api/{version}/metrics", "Prometheus-style metrics"),
    ("documentation", "/api/{version}/docs", "API documentation (does not exist)"),
    ("deprecation-policy", "/api/{version}/deprecation-policy", "Version deprecation policy"),
    ("support", "/api/{version}/support", "Enterprise support portal (also does not exist)"),
]


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class APIRequest:
    """Represents an incoming API request to the gateway.

    In a real API gateway, this would be parsed from an HTTP request.
    Here, it is lovingly constructed from CLI arguments and passed
    through a transformation pipeline that adds 27 metadata fields,
    normalizes the input, and calculates the lunar phase — because
    every FizzBuzz evaluation deserves contextual awareness of celestial
    mechanics.

    Attributes:
        request_id: A 340-character request identifier, because UUID v4
            was simply not unique enough for enterprise operations.
        path: The API path (e.g., "/api/v2/fizzbuzz/15").
        method: The HTTP method (always GET in a CLI application).
        version: The API version extracted from the path.
        headers: Request headers (simulated, but with real data types).
        query_params: Query parameters (simulated).
        body: Request body (for POST requests, also simulated).
        metadata: Metadata added by the transformation pipeline.
        timestamp: When the request was created (UTC).
        api_key: The API key used for authentication, if any.
        warnings: Deprecation and other warnings accumulated during processing.
    """

    request_id: str = ""
    path: str = ""
    method: str = "GET"
    version: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    api_key: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = generate_enterprise_request_id()


@dataclass
class APIResponse:
    """Represents the gateway's response to an API request.

    The response goes through its own transformation pipeline that
    compresses the data (making it larger), wraps it in pagination
    metadata (page 1 of 1), and enriches it with HATEOAS links
    to endpoints that do not exist.

    Attributes:
        request_id: The request ID this response corresponds to.
        status_code: HTTP status code (simulated but accurate).
        headers: Response headers including Sunset and deprecation warnings.
        body: The response body (before transformation).
        transformed_body: The response body after all transformations.
        metadata: Response metadata added by transformers.
        processing_time_ms: Time spent processing this request.
    """

    request_id: str = ""
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    transformed_body: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# Request ID Generator
# ---------------------------------------------------------------------------

def generate_enterprise_request_id() -> str:
    """Generate a 340-character enterprise-grade request identifier.

    Concatenates multiple UUIDs, timestamp hashes, process IDs, and
    the SHA-256 of strategic enterprise keywords until we achieve
    exactly 340 characters. Because in enterprise software, the length
    of your identifiers is directly proportional to the seriousness
    of your platform.
    """
    parts = [
        str(uuid.uuid4()),  # 36 chars
        str(uuid.uuid4()),  # 36 chars
        str(uuid.uuid4()),  # 36 chars
        str(uuid.uuid4()),  # 36 chars
        hashlib.sha256(str(time.time_ns()).encode()).hexdigest(),  # 64 chars
        hashlib.md5(str(os.getpid()).encode()).hexdigest(),  # 32 chars
    ]
    raw = "-".join(parts)

    # Pad with the SHA-256 hash of "enterprise" repeated until we reach target
    enterprise_hash = hashlib.sha256(b"enterprise-fizzbuzz-gateway").hexdigest()
    while len(raw) < _REQUEST_ID_TARGET_LENGTH:
        raw += enterprise_hash

    return raw[:_REQUEST_ID_TARGET_LENGTH]


# ---------------------------------------------------------------------------
# Route / RouteTable
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Route:
    """A single route definition in the gateway's routing table.

    Each route maps a path pattern to a handler function, with version
    filtering so that deprecated versions can have a reduced set of
    available endpoints. Because not every API version deserves access
    to the /feelings endpoint.

    Attributes:
        path_pattern: The URL pattern with {version} and {number} placeholders.
        method: The HTTP method this route responds to.
        handler_name: The name of the handler function.
        versions: Which API versions this route is available in.
        description: Human-readable description of the route.
    """

    path_pattern: str
    method: str
    handler_name: str
    versions: tuple[str, ...] = ()
    description: str = ""

    def matches(self, path: str, method: str, version: str) -> Optional[dict[str, str]]:
        """Check if this route matches the given path, method, and version.

        Returns a dict of captured path parameters if matched, None otherwise.
        The matching is performed by converting the path pattern into a regex,
        because string splitting was too straightforward for enterprise software.
        """
        if self.method.upper() != method.upper():
            return None

        if version and version not in self.versions:
            return None

        # Convert path pattern to regex
        # {version} -> (?P<version>[^/]+)
        # {number} -> (?P<number>[^/]+)
        regex_pattern = self.path_pattern
        param_names: list[str] = []
        for match in re.finditer(r"\{(\w+)\}", self.path_pattern):
            param_name = match.group(1)
            param_names.append(param_name)
            regex_pattern = regex_pattern.replace(
                f"{{{param_name}}}", f"(?P<{param_name}>[^/]+)"
            )

        regex_pattern = f"^{regex_pattern}$"
        m = re.match(regex_pattern, path)
        if m:
            return m.groupdict()
        return None


class RouteTable:
    """The gateway's routing table, holding all registered routes.

    Routes are matched in registration order, with the first match winning.
    This is the enterprise equivalent of a giant if-elif chain, but with
    significantly more ceremony, data structures, and docstrings.
    """

    def __init__(self) -> None:
        self._routes: list[Route] = []
        self._match_count: int = 0
        self._miss_count: int = 0

    def register(self, route: Route) -> None:
        """Register a new route in the routing table."""
        self._routes.append(route)
        logger.debug(
            "Registered route: %s %s (versions: %s)",
            route.method, route.path_pattern, ", ".join(route.versions),
        )

    def resolve(self, path: str, method: str, version: str) -> tuple[Route, dict[str, str]]:
        """Resolve a path and method to a route and extracted parameters.

        Raises:
            RouteNotFoundError: If no route matches the given path and method.
        """
        for route in self._routes:
            params = route.matches(path, method, version)
            if params is not None:
                self._match_count += 1
                return route, params

        self._miss_count += 1
        raise RouteNotFoundError(path, method)

    @property
    def routes(self) -> list[Route]:
        """Return all registered routes."""
        return list(self._routes)

    @property
    def total_matches(self) -> int:
        return self._match_count

    @property
    def total_misses(self) -> int:
        return self._miss_count

    def get_routes_for_version(self, version: str) -> list[Route]:
        """Return all routes available in the specified API version."""
        return [r for r in self._routes if version in r.versions]


# ---------------------------------------------------------------------------
# VersionRouter
# ---------------------------------------------------------------------------

class VersionRouter:
    """Manages API version resolution, deprecation warnings, and Sunset headers.

    Supports three API versions:
    - v1: DEPRECATED. Past its sunset date. Generates escalating warnings.
    - v2: ACTIVE. The recommended stable version.
    - v3: ACTIVE. The bleeding edge.

    When a request arrives for v1, the VersionRouter dutifully processes it
    while generating increasingly frantic deprecation warnings, adding Sunset
    headers, and incrementing an internal panic counter that serves no
    functional purpose but provides emotional catharsis for the engineering team.
    """

    def __init__(self, version_config: dict[str, Any], default_version: str = "v2") -> None:
        self._versions: dict[str, dict[str, Any]] = version_config
        self._default_version = default_version
        self._v1_request_count: int = 0
        self._version_request_counts: dict[str, int] = {}

    @property
    def supported_versions(self) -> list[str]:
        """Return all configured version identifiers."""
        return list(self._versions.keys())

    @property
    def active_versions(self) -> list[str]:
        """Return only ACTIVE versions."""
        return [
            v for v, cfg in self._versions.items()
            if cfg.get("status") == "ACTIVE"
        ]

    @property
    def deprecated_versions(self) -> list[str]:
        """Return only DEPRECATED versions."""
        return [
            v for v, cfg in self._versions.items()
            if cfg.get("status") == "DEPRECATED"
        ]

    @property
    def default_version(self) -> str:
        return self._default_version

    @property
    def version_request_counts(self) -> dict[str, int]:
        return dict(self._version_request_counts)

    def resolve_version(self, requested_version: Optional[str]) -> str:
        """Resolve the API version from the request.

        If no version is specified, returns the default version.
        If the version is not in the supported list, raises VersionNotSupportedError.
        """
        version = requested_version or self._default_version

        if version not in self._versions:
            raise VersionNotSupportedError(version, self.supported_versions)

        self._version_request_counts[version] = (
            self._version_request_counts.get(version, 0) + 1
        )

        return version

    def get_deprecation_warnings(self, version: str) -> list[str]:
        """Generate deprecation warnings for the given version.

        For v1, warnings escalate in urgency with each successive request,
        because gentle nudges clearly weren't working.
        """
        cfg = self._versions.get(version, {})
        if cfg.get("status") != "DEPRECATED":
            return []

        self._v1_request_count += 1

        # Escalate warnings based on request count
        idx = min(self._v1_request_count - 1, len(_V1_DEPRECATION_WARNINGS) - 1)
        warnings = [_V1_DEPRECATION_WARNINGS[idx]]

        # Add extra warnings at higher counts
        if self._v1_request_count >= 3:
            warnings.append(
                f"You have made {self._v1_request_count} requests to deprecated v1. "
                f"Each request is logged and forwarded to the API Governance Committee."
            )

        if self._v1_request_count >= 5:
            warnings.append(
                "FINAL WARNING: The next v1 request will generate a calendar invite "
                "for a mandatory API migration workshop. You have been warned."
            )

        return warnings

    def get_sunset_header(self, version: str) -> Optional[str]:
        """Return the Sunset header value for the given version, if applicable."""
        cfg = self._versions.get(version, {})
        sunset = cfg.get("sunset_date")
        if sunset:
            return f"Sunset: {sunset}"
        return None

    def get_version_status(self, version: str) -> str:
        """Return the status of the given version."""
        return self._versions.get(version, {}).get("status", "UNKNOWN")

    def is_deprecated(self, version: str) -> bool:
        """Check if the given version is deprecated."""
        return self.get_version_status(version) == "DEPRECATED"


# ---------------------------------------------------------------------------
# Request Transformers
# ---------------------------------------------------------------------------

class RequestNormalizer:
    """Normalizes incoming API requests.

    Takes the absolute value of numeric inputs, because negative numbers
    are a sign of negativity that has no place in an enterprise-positive
    FizzBuzz evaluation pipeline. Also strips whitespace from strings
    and lowercases headers, because consistency is the hobgoblin of
    enterprise middleware.
    """

    name = "RequestNormalizer"

    def transform(self, request: APIRequest) -> APIRequest:
        """Normalize the request, converting negative numbers to positive.

        Because if the user asks for FizzBuzz of -15, they clearly meant 15.
        Negativity is not a FizzBuzz-compatible emotion.
        """
        # Normalize number parameter if present
        if "number" in request.query_params:
            try:
                num = int(request.query_params["number"])
                request.query_params["number"] = str(abs(num))
                if num < 0:
                    request.metadata["original_number"] = num
                    request.metadata["normalized"] = True
                    request.warnings.append(
                        f"Input {num} was normalized to {abs(num)}. "
                        f"Negativity has no place in enterprise FizzBuzz."
                    )
            except ValueError:
                pass

        # Normalize headers to lowercase keys
        request.headers = {k.lower(): v for k, v in request.headers.items()}

        request.metadata["transformer_normalizer_applied"] = True
        return request


class RequestEnricher:
    """Enriches API requests with 27 metadata fields.

    Every request deserves to be adorned with contextual information
    including the lunar phase, day of week, whether it's a leap year,
    the golden ratio, Euler's number, and other critical business
    intelligence that no FizzBuzz evaluation should be without.
    """

    name = "RequestEnricher"

    def transform(self, request: APIRequest) -> APIRequest:
        """Enrich the request with 27 metadata fields.

        These fields provide the deep contextual awareness that
        separates enterprise FizzBuzz from artisanal FizzBuzz.
        """
        now = request.timestamp
        day_of_year = now.timetuple().tm_yday

        # Calculate approximate lunar phase (good enough for FizzBuzz)
        # Based on the synodic month of ~29.53 days
        known_new_moon = datetime(2024, 1, 11, tzinfo=timezone.utc)
        days_since = (now - known_new_moon).total_seconds() / 86400
        lunar_cycle = days_since % 29.53
        lunar_phase_idx = int(lunar_cycle / (29.53 / 8)) % 8
        lunar_phase = _LUNAR_PHASES[lunar_phase_idx]

        enrichments: dict[str, Any] = {
            "enriched_at": now.isoformat(),
            "lunar_phase": lunar_phase,
            "day_of_week": now.strftime("%A"),
            "day_of_year": day_of_year,
            "is_weekend": now.weekday() >= 5,
            "is_leap_year": (now.year % 4 == 0 and (now.year % 100 != 0 or now.year % 400 == 0)),
            "iso_week_number": now.isocalendar()[1],
            "unix_timestamp": int(now.timestamp()),
            "golden_ratio": 1.6180339887,
            "eulers_number": 2.7182818284,
            "pi_approximation": 3.1415926535,
            "request_id_length": len(request.request_id),
            "request_id_entropy_bits": len(request.request_id) * 4.7,  # ~4.7 bits per hex char
            "gateway_mood": _calculate_gateway_mood(now),
            "fizzbuzz_confidence": 1.0,  # We are always confident about modulo
            "platform_uptime_ms": time.monotonic() * 1000,
            "process_id": os.getpid(),
            "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
            "api_version_requested": request.version,
            "correlation_id": str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "span_id": str(uuid.uuid4())[:16],
            "request_priority": "ENTERPRISE_CRITICAL",
            "sla_class": "PLATINUM_FIZZBUZZ",
            "data_classification": "TOP_SECRET_FIZZBUZZ",
            "compliance_regime": "SOX_GDPR_HIPAA_FIZZBUZZ",
            "cost_center": "CC-FIZZBUZZ-001",
        }

        request.metadata.update(enrichments)
        request.metadata["transformer_enricher_applied"] = True
        request.metadata["enrichment_field_count"] = len(enrichments)
        return request


class RequestValidator:
    """Validates API request structure and parameters.

    Ensures that requests meet the exacting standards of the Enterprise
    FizzBuzz Platform before they are allowed anywhere near the sacred
    modulo operator.
    """

    name = "RequestValidator"

    def transform(self, request: APIRequest) -> APIRequest:
        """Validate the request structure.

        Checks that the request has a valid path, method, and version.
        Raises RequestTransformationError if validation fails.
        """
        if not request.path:
            raise RequestTransformationError(
                self.name,
                "Request path is empty. Even fictional API requests "
                "need a destination.",
            )

        if not request.method:
            raise RequestTransformationError(
                self.name,
                "Request method is empty. GET, POST, PUT, DELETE — "
                "pick one. Any one. We're not picky.",
            )

        if not request.request_id:
            raise RequestTransformationError(
                self.name,
                "Request ID is missing. Every request deserves a "
                "340-character identity.",
            )

        if len(request.request_id) != _REQUEST_ID_TARGET_LENGTH:
            request.warnings.append(
                f"Request ID is {len(request.request_id)} characters instead of "
                f"the required {_REQUEST_ID_TARGET_LENGTH}. This is a standards "
                f"violation but will be tolerated this time."
            )

        request.metadata["transformer_validator_applied"] = True
        request.metadata["validation_passed"] = True
        return request


class DeprecationInjector:
    """Injects deprecation warnings into requests for deprecated API versions.

    Works in concert with the VersionRouter to ensure that users of deprecated
    API versions are made aware of their transgression at every possible
    opportunity. The warnings are added to the request metadata, the response
    headers, and the engineering team's collective conscience.
    """

    name = "DeprecationInjector"

    def __init__(self, version_router: VersionRouter) -> None:
        self._version_router = version_router

    def transform(self, request: APIRequest) -> APIRequest:
        """Inject deprecation warnings if the version is deprecated."""
        if self._version_router.is_deprecated(request.version):
            warnings = self._version_router.get_deprecation_warnings(request.version)
            request.warnings.extend(warnings)

            sunset = self._version_router.get_sunset_header(request.version)
            if sunset:
                request.headers["sunset"] = sunset

            request.metadata["deprecated_version"] = True
            request.metadata["deprecation_warning_count"] = len(warnings)

        request.metadata["transformer_deprecation_injector_applied"] = True
        return request


class RequestTransformerChain:
    """Chains multiple request transformers together in sequence.

    Each transformer in the chain receives the output of the previous one,
    forming a pipeline of progressive request enrichment that transforms
    a simple "evaluate FizzBuzz for 15" into a metadata-laden enterprise
    artifact adorned with lunar phases, golden ratios, and deprecation
    warnings.
    """

    def __init__(self) -> None:
        self._transformers: list[Any] = []

    def add(self, transformer: Any) -> RequestTransformerChain:
        """Add a transformer to the chain. Returns self for fluent API."""
        self._transformers.append(transformer)
        return self

    def transform(self, request: APIRequest) -> APIRequest:
        """Run the request through all transformers in sequence."""
        for transformer in self._transformers:
            try:
                request = transformer.transform(request)
            except (RequestTransformationError, GatewayError):
                raise
            except Exception as e:
                raise RequestTransformationError(
                    getattr(transformer, "name", type(transformer).__name__),
                    str(e),
                ) from e
        return request

    @property
    def transformer_names(self) -> list[str]:
        return [getattr(t, "name", type(t).__name__) for t in self._transformers]


# ---------------------------------------------------------------------------
# Response Transformers
# ---------------------------------------------------------------------------

class ResponseCompressor:
    """Compresses API responses using gzip + base64 encoding.

    In a stunning feat of engineering, this compressor takes a small
    response like "Fizz" (4 bytes) and transforms it into a gzip-compressed,
    base64-encoded string that is approximately 9.47x larger than the original.
    This achieves a space savings of approximately -847%, which is to say,
    it makes the response significantly larger.

    The compression ratio is proudly displayed in the response metadata,
    because transparency about negative optimization is an enterprise value.
    """

    name = "ResponseCompressor"

    def transform(self, response: APIResponse) -> APIResponse:
        """Compress the response body using gzip + base64.

        The resulting string is always larger than the input, because
        gzip headers and base64 overhead dominate for small payloads.
        This is a feature, not a bug.
        """
        if response.body is None:
            return response

        # Serialize to string
        body_str = str(response.body)
        original_size = len(body_str.encode("utf-8"))

        # Gzip compress
        compressed = gzip.compress(body_str.encode("utf-8"))

        # Base64 encode (because binary is scary)
        encoded = base64.b64encode(compressed).decode("ascii")
        compressed_size = len(encoded)

        # Calculate the glorious space "savings"
        if original_size > 0:
            savings_pct = ((original_size - compressed_size) / original_size) * 100
        else:
            savings_pct = 0.0

        response.metadata["compression"] = {
            "algorithm": "gzip+base64",
            "original_size_bytes": original_size,
            "compressed_size_bytes": compressed_size,
            "savings_percent": round(savings_pct, 1),
            "savings_description": (
                f"Saved {savings_pct:.1f}% space "
                f"({'reduced' if savings_pct > 0 else 'increased'} "
                f"from {original_size} to {compressed_size} bytes)"
            ),
            "enterprise_grade": True,
        }

        response.headers["content-encoding"] = "gzip+base64"
        response.headers["x-original-size"] = str(original_size)
        response.headers["x-compressed-size"] = str(compressed_size)
        response.headers["x-compression-savings"] = f"{savings_pct:.1f}%"

        if response.transformed_body is None:
            response.transformed_body = {}

        response.transformed_body["compressed_data"] = encoded
        response.metadata["transformer_compressor_applied"] = True
        return response


class PaginationWrapper:
    """Wraps API responses in pagination metadata.

    Every response is page 1 of 1, with 1 result per page and a
    total of 1 page. The next_cursor is always null because there
    is never a next page. Despite this, the pagination wrapper
    faithfully includes all the pagination fields that a proper
    REST API would need, including prev_cursor (also null),
    total_results (1), and has_more (false).

    The pagination exists because enterprise APIs must be paginated,
    even when there is only one result. It's in the style guide.
    """

    name = "PaginationWrapper"

    def transform(self, response: APIResponse) -> APIResponse:
        """Wrap the response in pagination metadata."""
        if response.transformed_body is None:
            response.transformed_body = {}

        response.transformed_body["pagination"] = {
            "page": 1,
            "per_page": 1,
            "total_pages": 1,
            "total_results": 1,
            "has_more": False,
            "next_cursor": None,
            "prev_cursor": None,
            "first_page": 1,
            "last_page": 1,
        }

        response.headers["x-page"] = "1"
        response.headers["x-per-page"] = "1"
        response.headers["x-total-pages"] = "1"
        response.headers["x-total-results"] = "1"
        response.headers["x-has-more"] = "false"

        response.metadata["transformer_pagination_applied"] = True
        return response


class HATEOASEnricher:
    """Enriches API responses with HATEOAS hypermedia links.

    Every response includes _links containing hyperlinks to related
    resources, including a /feelings endpoint that reveals the
    existential state of the FizzBuzz evaluation engine. All links
    point to endpoints that do not exist on any server, because the
    server itself does not exist.

    REST purists will be pleased. Everyone else will wonder why a
    FizzBuzz CLI has hypermedia links.
    """

    name = "HATEOASEnricher"

    def transform(self, response: APIResponse, version: str = "v2",
                  number: int = 0) -> APIResponse:
        """Add HATEOAS _links to the response."""
        if response.transformed_body is None:
            response.transformed_body = {}

        links: dict[str, dict[str, str]] = {}
        for rel, href_template, title in _HATEOAS_RELATIONS:
            href = href_template.format(
                version=version,
                number=number,
                next_number=number + 1,
                prev_number=max(0, number - 1),
            )
            links[rel] = {
                "href": href,
                "method": "GET",
                "title": title,
            }

        response.transformed_body["_links"] = links
        response.headers["x-hateoas-enriched"] = "true"
        response.metadata["transformer_hateoas_applied"] = True
        response.metadata["hateoas_link_count"] = len(links)
        return response


class ResponseTransformerChain:
    """Chains multiple response transformers together.

    Each transformer modifies the response in sequence, progressively
    compressing, paginating, and enriching it until the original
    4-character "Fizz" response has become a 2KB JSON document with
    hypermedia links, pagination metadata, and base64-encoded gzip data.
    """

    def __init__(self) -> None:
        self._transformers: list[Any] = []

    def add(self, transformer: Any) -> ResponseTransformerChain:
        """Add a transformer to the chain. Returns self for fluent API."""
        self._transformers.append(transformer)
        return self

    def transform(self, response: APIResponse, **kwargs: Any) -> APIResponse:
        """Run the response through all transformers in sequence."""
        for transformer in self._transformers:
            try:
                # HATEOASEnricher takes extra kwargs
                if isinstance(transformer, HATEOASEnricher):
                    response = transformer.transform(
                        response,
                        version=kwargs.get("version", "v2"),
                        number=kwargs.get("number", 0),
                    )
                else:
                    response = transformer.transform(response)
            except (ResponseTransformationError, GatewayError):
                raise
            except Exception as e:
                raise ResponseTransformationError(
                    getattr(transformer, "name", type(transformer).__name__),
                    str(e),
                ) from e
        return response

    @property
    def transformer_names(self) -> list[str]:
        return [getattr(t, "name", type(t).__name__) for t in self._transformers]


# ---------------------------------------------------------------------------
# API Key Manager
# ---------------------------------------------------------------------------

class APIKeyManager:
    """Manages API key generation, validation, revocation, and quota tracking.

    Every API key is prefixed with 'efp_' (Enterprise FizzBuzz Platform)
    and consists of 32 random characters, because authentication for
    modulo arithmetic is a serious business. Keys have quotas, and
    exceeding your quota means you've evaluated too many numbers through
    the FizzBuzz pipeline — a transgression that the API Governance
    Committee takes very seriously.
    """

    def __init__(
        self,
        default_quota: int = 1000,
        key_prefix: str = "efp_",
        key_length: int = 32,
    ) -> None:
        self._default_quota = default_quota
        self._key_prefix = key_prefix
        self._key_length = key_length
        self._keys: dict[str, dict[str, Any]] = {}
        self._revoked_keys: set[str] = set()

    def generate_key(self, owner: str = "anonymous", quota: Optional[int] = None) -> str:
        """Generate a new API key with the specified quota.

        Returns the full API key string. Store it securely — in a
        Post-It note on your monitor, like all enterprise secrets.
        """
        key_body = secrets.token_hex(self._key_length // 2)
        full_key = f"{self._key_prefix}{key_body}"

        self._keys[full_key] = {
            "owner": owner,
            "quota_limit": quota or self._default_quota,
            "quota_used": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": None,
            "revoked": False,
        }

        logger.debug("Generated API key for '%s': %s...", owner, full_key[:12])
        return full_key

    def validate_key(self, key: str) -> dict[str, Any]:
        """Validate an API key and return its metadata.

        Raises:
            APIKeyInvalidError: If the key is invalid or revoked.
            APIKeyQuotaExceededError: If the key has exceeded its quota.
        """
        if key in self._revoked_keys:
            raise APIKeyInvalidError(
                key[:12], "This key has been revoked. It is dead to us."
            )

        if key not in self._keys:
            raise APIKeyInvalidError(
                key[:12], "Key not found in the registry. It may never have existed."
            )

        key_data = self._keys[key]

        if key_data["revoked"]:
            raise APIKeyInvalidError(
                key[:12], "This key has been revoked. Please generate a new one."
            )

        if key_data["quota_used"] >= key_data["quota_limit"]:
            raise APIKeyQuotaExceededError(
                key[:12], key_data["quota_limit"], key_data["quota_used"]
            )

        # Consume one quota unit
        key_data["quota_used"] += 1
        key_data["last_used_at"] = datetime.now(timezone.utc).isoformat()

        return key_data

    def revoke_key(self, key: str) -> bool:
        """Revoke an API key, permanently preventing further use.

        Returns True if the key was found and revoked, False if not found.
        Revoked keys can never be un-revoked. Like trust, once broken,
        an API key cannot be repaired.
        """
        if key in self._keys:
            self._keys[key]["revoked"] = True
            self._revoked_keys.add(key)
            return True
        return False

    def get_key_info(self, key: str) -> Optional[dict[str, Any]]:
        """Return metadata for the given key, or None if not found."""
        return self._keys.get(key)

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    @property
    def active_keys(self) -> int:
        return sum(1 for k in self._keys.values() if not k["revoked"])

    @property
    def revoked_key_count(self) -> int:
        return len(self._revoked_keys)

    @property
    def total_quota_consumed(self) -> int:
        return sum(k["quota_used"] for k in self._keys.values())


# ---------------------------------------------------------------------------
# Request Replay Journal
# ---------------------------------------------------------------------------

class RequestReplayJournal:
    """Append-only journal of all API requests processed by the gateway.

    Every request that passes through the gateway is faithfully recorded
    in this journal, creating an immutable (in-RAM) audit trail of every
    FizzBuzz evaluation request ever made. The journal supports replay,
    allowing you to re-execute historical requests — though since all
    results are computed from pure functions (modulo arithmetic), the
    replayed results will be identical to the originals, making the
    entire replay capability technically useless but architecturally
    satisfying.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: list[dict[str, Any]] = []
        self._max_entries = max_entries
        self._replay_count: int = 0

    def append(self, request: APIRequest, response: APIResponse) -> None:
        """Append a request/response pair to the journal."""
        if len(self._entries) >= self._max_entries:
            # Journal is full — in a real system we'd rotate. Here, we
            # just sadly refuse to record more history.
            logger.warning(
                "Request replay journal is full (%d entries). "
                "History beyond this point will be lost to the void.",
                self._max_entries,
            )
            return

        self._entries.append({
            "request_id": request.request_id,
            "path": request.path,
            "method": request.method,
            "version": request.version,
            "timestamp": request.timestamp.isoformat(),
            "query_params": dict(request.query_params),
            "status_code": response.status_code,
            "processing_time_ms": response.processing_time_ms,
            "warnings": list(request.warnings),
        })

    def get_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent journal entries."""
        return list(self._entries[-limit:])

    def replay(self, handler: Callable[[APIRequest], APIResponse]) -> list[APIResponse]:
        """Replay all journal entries through the given handler.

        Returns a list of responses from the replayed requests.

        Raises:
            RequestReplayError: If replay encounters an error.
        """
        responses: list[APIResponse] = []
        try:
            for entry in self._entries:
                req = APIRequest(
                    path=entry["path"],
                    method=entry["method"],
                    version=entry["version"],
                    query_params=entry.get("query_params", {}),
                )
                resp = handler(req)
                responses.append(resp)
                self._replay_count += 1
        except Exception as e:
            raise RequestReplayError(str(e)) from e

        return responses

    @property
    def total_entries(self) -> int:
        return len(self._entries)

    @property
    def replay_count(self) -> int:
        return self._replay_count

    @property
    def is_full(self) -> bool:
        return len(self._entries) >= self._max_entries


# ---------------------------------------------------------------------------
# Gateway Core
# ---------------------------------------------------------------------------

class APIGateway:
    """The central API Gateway orchestrator.

    Coordinates routing, versioning, request/response transformation,
    API key validation, and request journaling. This is the nerve center
    of the Enterprise FizzBuzz Platform's non-existent REST API, routing
    fictional HTTP requests through a real transformation pipeline to
    produce results that could have been computed with a single modulo
    operation.

    The gateway processes requests in this order:
    1. Resolve API version
    2. Validate API key (if provided)
    3. Run request transformer chain
    4. Resolve route
    5. Execute handler
    6. Run response transformer chain
    7. Record in replay journal
    """

    def __init__(
        self,
        route_table: RouteTable,
        version_router: VersionRouter,
        request_chain: RequestTransformerChain,
        response_chain: ResponseTransformerChain,
        key_manager: APIKeyManager,
        journal: RequestReplayJournal,
        event_bus: Any = None,
    ) -> None:
        self._route_table = route_table
        self._version_router = version_router
        self._request_chain = request_chain
        self._response_chain = response_chain
        self._key_manager = key_manager
        self._journal = journal
        self._event_bus = event_bus
        self._total_requests: int = 0
        self._total_errors: int = 0

    def process_request(
        self,
        request: APIRequest,
        handler_registry: Optional[dict[str, Callable[..., Any]]] = None,
    ) -> APIResponse:
        """Process a request through the full gateway pipeline.

        Returns an APIResponse with all transformations applied.
        """
        start_time = time.perf_counter()
        self._total_requests += 1

        self._emit_event(EventType.GATEWAY_REQUEST_RECEIVED, {
            "request_id": request.request_id[:36],
            "path": request.path,
            "method": request.method,
        })

        try:
            # 1. Resolve version
            version = self._version_router.resolve_version(request.version or None)
            request.version = version

            self._emit_event(EventType.GATEWAY_VERSION_RESOLVED, {
                "version": version,
                "status": self._version_router.get_version_status(version),
            })

            # 2. Validate API key
            if request.api_key:
                key_data = self._key_manager.validate_key(request.api_key)
                request.metadata["api_key_owner"] = key_data["owner"]
                self._emit_event(EventType.GATEWAY_API_KEY_VALIDATED, {
                    "key_prefix": request.api_key[:12],
                })

            # 3. Request transformation
            request = self._request_chain.transform(request)
            self._emit_event(EventType.GATEWAY_REQUEST_TRANSFORMED, {
                "transformer_count": len(self._request_chain.transformer_names),
            })

            # 4. Resolve route
            route, params = self._route_table.resolve(request.path, request.method, version)
            request.metadata["matched_route"] = route.path_pattern
            request.metadata["route_params"] = params

            self._emit_event(EventType.GATEWAY_REQUEST_ROUTED, {
                "route": route.path_pattern,
                "handler": route.handler_name,
            })

            # 5. Execute handler
            result = None
            if handler_registry and route.handler_name in handler_registry:
                handler_fn = handler_registry[route.handler_name]
                result = handler_fn(request, params)

            # 6. Build response
            response = APIResponse(
                request_id=request.request_id,
                status_code=200,
                body=result,
                headers={},
            )

            # Add deprecation headers
            sunset = self._version_router.get_sunset_header(version)
            if sunset:
                response.headers["sunset"] = sunset
            if self._version_router.is_deprecated(version):
                response.headers["x-deprecated"] = "true"
                self._emit_event(EventType.GATEWAY_DEPRECATION_WARNING, {
                    "version": version,
                    "warning_count": len(request.warnings),
                })

            # Add warnings to response
            if request.warnings:
                response.headers["x-warnings"] = str(len(request.warnings))
                response.metadata["warnings"] = request.warnings

            # Extract number for HATEOAS links
            number = 0
            if "number" in params:
                try:
                    number = int(params["number"])
                except (ValueError, TypeError):
                    pass

            # 7. Response transformation
            response = self._response_chain.transform(
                response, version=version, number=number
            )
            self._emit_event(EventType.GATEWAY_RESPONSE_TRANSFORMED, {
                "transformer_count": len(self._response_chain.transformer_names),
            })

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            response.processing_time_ms = elapsed_ms

            # 8. Record in journal
            self._journal.append(request, response)

            return response

        except GatewayError:
            self._total_errors += 1
            raise
        except Exception as e:
            self._total_errors += 1
            raise GatewayError(f"Unexpected gateway error: {e}") from e

    @property
    def route_table(self) -> RouteTable:
        return self._route_table

    @property
    def version_router(self) -> VersionRouter:
        return self._version_router

    @property
    def key_manager(self) -> APIKeyManager:
        return self._key_manager

    @property
    def journal(self) -> RequestReplayJournal:
        return self._journal

    @property
    def total_requests(self) -> int:
        return self._total_requests

    @property
    def total_errors(self) -> int:
        return self._total_errors

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event if the event bus is available."""
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.notify(Event(
                event_type=event_type,
                payload=payload,
                source="APIGateway",
            ))


# ---------------------------------------------------------------------------
# Gateway Middleware
# ---------------------------------------------------------------------------

class GatewayMiddleware(IMiddleware):
    """Middleware that integrates the API Gateway into the FizzBuzz pipeline.

    When the gateway is enabled, every FizzBuzz evaluation is wrapped in
    an API request, routed through the gateway, transformed, compressed,
    paginated, and enriched with HATEOAS links — before the actual modulo
    arithmetic even begins. The gateway middleware runs at priority 12,
    ensuring it executes after basic validation but before most other
    enterprise middleware layers.

    Priority 12 was chosen because it is the product of 3 and 4, and
    3 is the most important number in FizzBuzz. The choice was ratified
    by the Architecture Review Board in a 3-hour meeting.
    """

    def __init__(self, gateway: APIGateway, version: str = "v2") -> None:
        self._gateway = gateway
        self._version = version

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Wrap the FizzBuzz evaluation in a gateway request/response cycle."""
        # Create an API request for this number
        request = APIRequest(
            path=f"/api/{self._version}/fizzbuzz/{context.number}",
            method="GET",
            version=self._version,
            query_params={"number": str(context.number)},
        )

        try:
            # Process through the gateway (routing + transformation only)
            response = self._gateway.process_request(request)

            # Add gateway metadata to context
            context.metadata["gateway_request_id"] = request.request_id[:36] + "..."
            context.metadata["gateway_version"] = self._version
            context.metadata["gateway_warnings"] = request.warnings
            context.metadata["gateway_processing_time_ms"] = response.processing_time_ms

            if response.metadata.get("compression"):
                context.metadata["gateway_compression"] = response.metadata["compression"]

        except GatewayError as e:
            context.metadata["gateway_error"] = str(e)

        # Continue with the actual FizzBuzz evaluation
        return next_handler(context)

    def get_name(self) -> str:
        return "GatewayMiddleware"

    def get_priority(self) -> int:
        return 12


# ---------------------------------------------------------------------------
# Gateway Dashboard
# ---------------------------------------------------------------------------

class GatewayDashboard:
    """Renders an ASCII dashboard for the API Gateway.

    Displays routing tables, version status, request statistics,
    API key utilization, compression metrics, and the gateway's
    current emotional state — all in lovingly crafted ASCII art
    that would make a 1990s BBS sysop proud.
    """

    @staticmethod
    def render(gateway: APIGateway, width: int = 60) -> str:
        """Render the complete API Gateway dashboard."""
        try:
            lines: list[str] = []
            inner = width - 4  # Account for "  | " and " |"

            def border() -> str:
                return "  +" + "-" * (width - 2) + "+"

            def title(text: str) -> str:
                return f"  | {text:<{inner}}|"

            def row(text: str) -> str:
                return f"  | {text:<{inner}}|"

            # Header
            lines.append(border())
            lines.append(title("API GATEWAY DASHBOARD"))
            lines.append(title("Enterprise FizzBuzz Platform"))
            lines.append(border())

            # Request Statistics
            lines.append(title("REQUEST STATISTICS"))
            lines.append(row(f"  Total Requests:  {gateway.total_requests}"))
            lines.append(row(f"  Total Errors:    {gateway.total_errors}"))
            lines.append(row(f"  Route Matches:   {gateway.route_table.total_matches}"))
            lines.append(row(f"  Route Misses:    {gateway.route_table.total_misses}"))
            lines.append(border())

            # Version Status
            lines.append(title("API VERSIONS"))
            vr = gateway.version_router
            for v in vr.supported_versions:
                status = vr.get_version_status(v)
                count = vr.version_request_counts.get(v, 0)
                marker = "X" if status == "DEPRECATED" else "+"
                lines.append(row(f"  [{marker}] {v}: {status} ({count} requests)"))

            sunset_versions = vr.deprecated_versions
            for sv in sunset_versions:
                sunset = vr.get_sunset_header(sv)
                if sunset:
                    lines.append(row(f"      {sunset}"))
            lines.append(border())

            # Routes
            lines.append(title("REGISTERED ROUTES"))
            for r in gateway.route_table.routes:
                vers_str = ",".join(r.versions)
                line = f"  {r.method:<6} {r.path_pattern}"
                if len(line) > inner - 2:
                    line = line[:inner - 5] + "..."
                lines.append(row(line))
                lines.append(row(f"         versions: [{vers_str}]"))
            lines.append(border())

            # API Keys
            km = gateway.key_manager
            lines.append(title("API KEY MANAGEMENT"))
            lines.append(row(f"  Total Keys:      {km.total_keys}"))
            lines.append(row(f"  Active Keys:     {km.active_keys}"))
            lines.append(row(f"  Revoked Keys:    {km.revoked_key_count}"))
            lines.append(row(f"  Quota Consumed:  {km.total_quota_consumed}"))
            lines.append(border())

            # Journal
            j = gateway.journal
            lines.append(title("REQUEST REPLAY JOURNAL"))
            lines.append(row(f"  Total Entries:   {j.total_entries}"))
            lines.append(row(f"  Replay Count:    {j.replay_count}"))
            lines.append(row(f"  Journal Full:    {'YES' if j.is_full else 'NO'}"))
            lines.append(border())

            # Gateway Mood
            mood = _calculate_gateway_mood(datetime.now(timezone.utc))
            lines.append(title("GATEWAY STATUS"))
            lines.append(row(f"  Current Mood:    {mood}"))
            lines.append(row(f"  Uptime:          Unmeasurable (it's a CLI)"))
            lines.append(row(f"  Server:          Does not exist"))
            lines.append(row(f"  HTTP Port:       0 (bound to the void)"))
            lines.append(border())

            return "\n".join(lines) + "\n"

        except Exception as e:
            raise GatewayDashboardRenderError(str(e)) from e


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _calculate_gateway_mood(now: datetime) -> str:
    """Calculate the gateway's current emotional state.

    The mood is determined by the hour of the day, because even
    API gateways experience circadian rhythms. Gateways are grumpiest
    at 3 AM and most optimistic at 10 AM, which mirrors the emotional
    arc of the average software engineer's day.
    """
    hour = now.hour
    moods = {
        range(0, 4): "Existential Dread",
        range(4, 7): "Reluctant Awareness",
        range(7, 10): "Cautious Optimism",
        range(10, 12): "Peak Enterprise Enthusiasm",
        range(12, 14): "Post-Lunch Lethargy",
        range(14, 17): "Productive Resignation",
        range(17, 20): "Gradual Disengagement",
        range(20, 24): "Philosophical Contemplation",
    }
    for hours, mood in moods.items():
        if hour in hours:
            return mood
    return "Unknown Emotional State"


def create_api_gateway(
    config: Any,
    event_bus: Any = None,
) -> tuple[APIGateway, GatewayMiddleware]:
    """Factory function to create a fully configured API Gateway.

    Returns a tuple of (APIGateway, GatewayMiddleware) ready for
    integration into the FizzBuzz processing pipeline.
    """
    # Build version router
    version_config = config.api_gateway_versions
    default_version = config.api_gateway_default_version
    version_router = VersionRouter(version_config, default_version)

    # Build route table
    route_table = RouteTable()
    for route_cfg in config.api_gateway_routes:
        route = Route(
            path_pattern=route_cfg["path"],
            method=route_cfg["method"],
            handler_name=route_cfg["handler"],
            versions=tuple(route_cfg.get("versions", [])),
            description=route_cfg.get("description", ""),
        )
        route_table.register(route)

    # Build request transformer chain
    req_transformers = config.api_gateway_transformers.get("request", {})
    request_chain = RequestTransformerChain()
    if req_transformers.get("normalizer", True):
        request_chain.add(RequestNormalizer())
    if req_transformers.get("enricher", True):
        request_chain.add(RequestEnricher())
    if req_transformers.get("validator", True):
        request_chain.add(RequestValidator())
    if req_transformers.get("deprecation_injector", True):
        request_chain.add(DeprecationInjector(version_router))

    # Build response transformer chain
    resp_transformers = config.api_gateway_transformers.get("response", {})
    response_chain = ResponseTransformerChain()
    if resp_transformers.get("compressor", True):
        response_chain.add(ResponseCompressor())
    if resp_transformers.get("pagination_wrapper", True):
        response_chain.add(PaginationWrapper())
    if resp_transformers.get("hateoas_enricher", True):
        response_chain.add(HATEOASEnricher())

    # Build API key manager
    key_manager = APIKeyManager(
        default_quota=config.api_gateway_api_keys_default_quota,
        key_prefix=config.api_gateway_api_keys_prefix,
        key_length=config.api_gateway_api_keys_length,
    )

    # Build replay journal
    journal = RequestReplayJournal(
        max_entries=config.api_gateway_replay_journal_max_entries,
    )

    # Assemble the gateway
    gateway = APIGateway(
        route_table=route_table,
        version_router=version_router,
        request_chain=request_chain,
        response_chain=response_chain,
        key_manager=key_manager,
        journal=journal,
        event_bus=event_bus,
    )

    # Build middleware
    middleware = GatewayMiddleware(
        gateway=gateway,
        version=default_version,
    )

    return gateway, middleware

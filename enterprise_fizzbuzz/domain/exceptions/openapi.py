"""
Enterprise FizzBuzz Platform - OpenAPI Specification Generator Exceptions (EFP-OA00 through EFP-OA11)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class OpenAPIError(FizzBuzzError):
    """Base exception for all OpenAPI Specification Generator errors.

    When your system for documenting an API that does not exist
    encounters a failure, you have achieved a level of meta-documentation
    failure that most enterprises can only dream of. The spec was
    supposed to describe what could be; instead, it describes what
    went wrong while trying to describe what could be.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-OA00"),
            context=kwargs.pop("context", {}),
        )


class SchemaIntrospectionError(OpenAPIError):
    """Raised when the schema generator fails to introspect a domain model.

    The SchemaGenerator attempted to convert a dataclass or enum to
    JSON Schema using reflection, type hints, and a healthy dose of
    optimism. Something went wrong. Perhaps the type annotations are
    too creative, the dataclass fields are too recursive, or Python's
    typing module has finally given up trying to understand generics.
    """

    def __init__(self, class_name: str, reason: str) -> None:
        super().__init__(
            f"Schema introspection failed for '{class_name}': {reason}. "
            f"The JSON Schema generator cannot convert this class to a "
            f"schema. The type annotations have defeated reflection.",
            error_code="EFP-OA01",
            context={"class_name": class_name, "reason": reason},
        )
        self.class_name = class_name


class EndpointRegistrationError(OpenAPIError):
    """Raised when an endpoint fails to register in the EndpointRegistry.

    The fictional endpoint you tried to register has been rejected by
    the registry. Perhaps the path is malformed, the operation_id is
    already taken, or the endpoint is simply too fictional even for
    our standards (which is saying something).
    """

    def __init__(self, path: str, method: str, reason: str) -> None:
        super().__init__(
            f"Endpoint registration failed for {method} {path}: {reason}. "
            f"The fictional endpoint could not be added to the fictional registry "
            f"of the fictional API. This is a real error about a fake API.",
            error_code="EFP-OA02",
            context={"path": path, "method": method, "reason": reason},
        )
        self.path = path
        self.method = method


class ExceptionMappingError(OpenAPIError):
    """Raised when an exception cannot be mapped to an HTTP status code.

    The ExceptionToHTTPMapper examined the exception class, walked its
    MRO, checked the explicit mappings, and still couldn't determine
    an appropriate HTTP status code. This exception has fallen through
    every crack in the mapping table and now exists in HTTP status limbo.
    """

    def __init__(self, exception_name: str, reason: str) -> None:
        super().__init__(
            f"Cannot map exception '{exception_name}' to HTTP status code: "
            f"{reason}. The exception will default to 500 Internal Server "
            f"Error, which is the HTTP equivalent of shrugging.",
            error_code="EFP-OA03",
            context={"exception_name": exception_name, "reason": reason},
        )
        self.exception_name = exception_name


class OpenAPISpecGenerationError(OpenAPIError):
    """Raised when the OpenAPI specification cannot be assembled.

    The OpenAPIGenerator attempted to assemble the complete specification
    from endpoints, schemas, security schemes, and server definitions,
    but something went wrong during assembly. The spec is incomplete,
    which means the documentation for the non-existent API is itself
    non-existent. The recursion is complete.
    """

    def __init__(self, section: str, reason: str) -> None:
        super().__init__(
            f"OpenAPI specification generation failed in section '{section}': "
            f"{reason}. The spec for the server that does not exist has itself "
            f"failed to exist. The irony is not lost on us.",
            error_code="EFP-OA04",
            context={"section": section, "reason": reason},
        )
        self.section = section


class SwaggerUIRenderError(OpenAPIError):
    """Raised when the ASCII Swagger UI fails to render.

    The ASCII art rendering engine — which converts OpenAPI endpoints
    into box-drawing characters and [Try It] buttons — has encountered
    a rendering error. The Swagger UI cannot be displayed, which means
    the terminal-based documentation for the non-existent API will
    remain invisible. Some might argue this is an improvement.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"ASCII Swagger UI render failed: {reason}. "
            f"The box-drawing characters have refused to draw boxes. "
            f"The [Try It] buttons cannot be tried. The swagger has left the UI.",
            error_code="EFP-OA05",
            context={"reason": reason},
        )


class OpenAPIDashboardRenderError(OpenAPIError):
    """Raised when the OpenAPI dashboard fails to render.

    The statistics dashboard — a compact summary of endpoints, schemas,
    and exception mappings — has failed to render. The meta-dashboard
    about the meta-specification has experienced a meta-failure. We are
    now three levels deep in the meta-stack and the box-drawing characters
    are getting dizzy.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"OpenAPI dashboard render failed: {reason}. "
            f"The dashboard summarizing the spec describing the API that "
            f"doesn't exist has itself failed to appear. Peak enterprise.",
            error_code="EFP-OA06",
            context={"reason": reason},
        )


class OpenAPISerializationError(OpenAPIError):
    """Raised when the OpenAPI spec cannot be serialized to JSON or YAML.

    The specification was generated successfully in memory but could not
    be serialized to a string format. Perhaps a value is not JSON-serializable,
    or the YAML formatter encountered a type it cannot represent. Either way,
    the documentation exists only in RAM, which is appropriate for a platform
    whose entire state exists only in RAM.
    """

    def __init__(self, format_name: str, reason: str) -> None:
        super().__init__(
            f"OpenAPI spec serialization to {format_name} failed: {reason}. "
            f"The specification cannot be exported. It will remain an "
            f"in-memory representation of a non-existent API.",
            error_code="EFP-OA07",
            context={"format_name": format_name, "reason": reason},
        )
        self.format_name = format_name


class InvalidEndpointPathError(OpenAPIError):
    """Raised when an endpoint path does not conform to OpenAPI path syntax.

    OpenAPI paths must start with '/' and use '{paramName}' for path
    parameters. Your path either forgot the leading slash (barbaric),
    used angle brackets instead of curly braces (XML contamination),
    or contained characters that no URL should ever contain.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"Invalid OpenAPI endpoint path '{path}': {reason}. "
            f"Paths must start with '/' and use curly braces for parameters. "
            f"This is not negotiable. RFC 3986 has opinions.",
            error_code="EFP-OA08",
            context={"path": path, "reason": reason},
        )
        self.path = path


class DuplicateOperationIdError(OpenAPIError):
    """Raised when two endpoints share the same operationId.

    Every endpoint must have a unique operationId, because the OpenAPI
    spec says so and we are nothing if not compliant with specifications
    — even when documenting an API that violates the most fundamental
    specification of all: having a server.
    """

    def __init__(self, operation_id: str, path_a: str, path_b: str) -> None:
        super().__init__(
            f"Duplicate operationId '{operation_id}' found in '{path_a}' "
            f"and '{path_b}'. Operation IDs must be unique across the entire "
            f"spec. Even fictional APIs have standards.",
            error_code="EFP-OA09",
            context={
                "operation_id": operation_id,
                "path_a": path_a,
                "path_b": path_b,
            },
        )
        self.operation_id = operation_id


class SecuritySchemeNotFoundError(OpenAPIError):
    """Raised when a referenced security scheme does not exist.

    The endpoint references a security scheme that has not been defined
    in the components/securitySchemes section. This is the OpenAPI
    equivalent of citing a source that doesn't exist in an academic paper.
    The peer reviewers (validators) will not be pleased.
    """

    def __init__(self, scheme_name: str) -> None:
        super().__init__(
            f"Security scheme '{scheme_name}' not found in components. "
            f"The endpoint references a security mechanism that has not "
            f"been defined. Authentication is hard enough without phantom "
            f"security schemes.",
            error_code="EFP-OA10",
            context={"scheme_name": scheme_name},
        )
        self.scheme_name = scheme_name


class TagNotFoundError(OpenAPIError):
    """Raised when an endpoint references a tag that has no description.

    Every tag used by endpoints should have a corresponding entry in the
    tags section with a description. An undescribed tag is like an
    unlabeled filing cabinet: technically functional, but deeply
    unsatisfying to anyone who values organizational hygiene.
    """

    def __init__(self, tag_name: str) -> None:
        super().__init__(
            f"Tag '{tag_name}' used by endpoint but not defined in tags section. "
            f"Every tag deserves a description. Even in a spec for an API that "
            f"doesn't exist, we maintain documentation standards.",
            error_code="EFP-OA11",
            context={"tag_name": tag_name},
        )
        self.tag_name = tag_name


class GatewayError(FizzBuzzError):
    """Base exception for all API Gateway errors.

    When your API Gateway for a CLI application that has no HTTP server
    encounters an error, you've achieved a level of architectural ambition
    that most enterprise architects can only dream of. These exceptions
    cover everything from route resolution failures to version deprecation
    tantrums to request transformation meltdowns — all for an API that
    exists entirely in the imagination of the YAML configuration file.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-GW00"),
            context=kwargs.pop("context", {}),
        )


class RouteNotFoundError(GatewayError):
    """Raised when no route matches the incoming API request path.

    The request arrived at the gateway's door, knocked politely, and
    was turned away because no route existed to handle it. Perhaps the
    path was misspelled, perhaps it never existed, or perhaps the
    routing table was last updated during the previous fiscal quarter.
    """

    def __init__(self, path: str, method: str) -> None:
        super().__init__(
            f"No route found for {method} {path}. The gateway searched "
            f"every routing table, consulted the map, and found only wilderness.",
            error_code="EFP-GW01",
            context={"path": path, "method": method},
        )
        self.path = path
        self.method = method


class VersionNotSupportedError(GatewayError):
    """Raised when the requested API version is not supported.

    The client requested an API version that either never existed,
    has been deprecated into oblivion, or belongs to a future release
    that exists only in the product roadmap. Time travel is not yet
    supported by the Enterprise FizzBuzz Platform gateway.
    """

    def __init__(self, version: str, supported_versions: list[str]) -> None:
        super().__init__(
            f"API version '{version}' is not supported. "
            f"Supported versions: {', '.join(supported_versions)}. "
            f"The gateway recommends upgrading to a version that exists.",
            error_code="EFP-GW02",
            context={"version": version, "supported_versions": supported_versions},
        )
        self.version = version
        self.supported_versions = supported_versions


class VersionDeprecatedError(GatewayError):
    """Raised when the requested API version is deprecated.

    The client is clinging to an API version that has been formally
    deprecated. Like a software archaeologist unearthing ancient
    endpoints, you are accessing routes that time forgot. The Sunset
    header has been set. The countdown has begun. Please migrate
    before the version is removed entirely and your requests fall
    into the void.
    """

    def __init__(self, version: str, sunset_date: str) -> None:
        super().__init__(
            f"API version '{version}' is DEPRECATED. Sunset date: {sunset_date}. "
            f"Your requests are living on borrowed time. Please migrate "
            f"to a supported version before it's too late.",
            error_code="EFP-GW03",
            context={"version": version, "sunset_date": sunset_date},
        )
        self.version = version
        self.sunset_date = sunset_date


class RequestTransformationError(GatewayError):
    """Raised when a request transformer fails to process the request.

    The request entered the transformation pipeline full of hope and
    left as a mangled data structure that no downstream handler could
    parse. The transformer chain is supposed to enrich, normalize,
    and validate — not destroy. Something went very wrong in the
    metadata enrichment phase, probably the lunar phase calculator.
    """

    def __init__(self, transformer_name: str, reason: str) -> None:
        super().__init__(
            f"Request transformer '{transformer_name}' failed: {reason}. "
            f"The request has been irrevocably transformed into something "
            f"no downstream handler can recognize.",
            error_code="EFP-GW04",
            context={"transformer_name": transformer_name, "reason": reason},
        )
        self.transformer_name = transformer_name


class ResponseTransformationError(GatewayError):
    """Raised when a response transformer fails to process the response.

    The response was perfectly fine until the transformation pipeline
    got its hands on it. Now it's been gzipped, base64-encoded,
    wrapped in pagination metadata, and adorned with HATEOAS links
    to related endpoints — and something in that process
    went sideways.
    """

    def __init__(self, transformer_name: str, reason: str) -> None:
        super().__init__(
            f"Response transformer '{transformer_name}' failed: {reason}. "
            f"The response has been lost in the transformation pipeline. "
            f"The original data is irretrievable. Thoughts and prayers.",
            error_code="EFP-GW05",
            context={"transformer_name": transformer_name, "reason": reason},
        )
        self.transformer_name = transformer_name


class APIKeyInvalidError(GatewayError):
    """Raised when the provided API key is invalid or revoked.

    The API key you presented has been examined by the gateway's
    key validation service and found to be either invalid, revoked,
    expired, or simply not a real Enterprise FizzBuzz Platform API key.
    Perhaps you generated it at a different FizzBuzz platform. Perhaps
    you made it up. Either way, access is denied with extreme prejudice.
    """

    def __init__(self, key_prefix: str, reason: str) -> None:
        super().__init__(
            f"API key '{key_prefix}...' is invalid: {reason}. "
            f"Please generate a new key using --api-key-generate.",
            error_code="EFP-GW06",
            context={"key_prefix": key_prefix, "reason": reason},
        )


class APIKeyQuotaExceededError(GatewayError):
    """Raised when an API key has exhausted its request quota.

    Your API key has been used so many times that it has worn out.
    Like a subway pass that's been swiped too many times, it simply
    refuses to grant passage. The quota exists to protect the platform
    from being overwhelmed by excessive FizzBuzz requests, which is
    a real and present danger in today's fast-paced modulo economy.
    """

    def __init__(self, key_prefix: str, quota_limit: int, quota_used: int) -> None:
        super().__init__(
            f"API key '{key_prefix}...' has exceeded its quota: "
            f"{quota_used}/{quota_limit} requests consumed. "
            f"Consider purchasing the Enterprise FizzBuzz Unlimited plan.",
            error_code="EFP-GW07",
            context={"key_prefix": key_prefix, "quota_limit": quota_limit, "quota_used": quota_used},
        )


class RequestReplayError(GatewayError):
    """Raised when request replay from the journal fails.

    The append-only request journal faithfully recorded every request
    that passed through the gateway. When you asked to replay them,
    something went wrong — perhaps the journal was corrupted, perhaps
    the requests reference routes that no longer exist, or perhaps
    replaying modulo arithmetic requests is simply not as straightforward
    as the architecture diagrams suggested.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Request replay failed: {reason}. The journal entries are "
            f"intact but the replay engine has lost confidence in its "
            f"ability to re-execute them faithfully.",
            error_code="EFP-GW08",
            context={"reason": reason},
        )


class GatewayDashboardRenderError(GatewayError):
    """Raised when the gateway ASCII dashboard fails to render.

    The dashboard — a lovingly crafted ASCII art visualization of
    your API Gateway's routing tables, version status, and request
    statistics — has failed to render. The gateway itself continues
    to function perfectly; it is only the observation of the gateway
    that has failed. Schrodinger's dashboard: simultaneously rendered
    and unrendered until you look at it.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Gateway dashboard render failed: {reason}. "
            f"The ASCII art remains undrawn. The statistics unvisualized. "
            f"The gateway, however, continues to route — unobserved.",
            error_code="EFP-GW09",
            context={"reason": reason},
        )


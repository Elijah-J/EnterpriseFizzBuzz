"""OpenAPI Specification Generator events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("OPENAPI_SPEC_GENERATED")
EventType.register("OPENAPI_SCHEMA_INTROSPECTED")
EventType.register("OPENAPI_EXCEPTION_MAPPED")
EventType.register("OPENAPI_SWAGGER_UI_RENDERED")
EventType.register("OPENAPI_DASHBOARD_RENDERED")
EventType.register("OPENAPI_YAML_EXPORTED")

"""
Enterprise FizzBuzz Platform - OpenAPI Specification Generator Tests

Comprehensive test suite for the OpenAPI Specification Generator & ASCII
Swagger UI, ensuring that the documentation for the API that does not
exist is itself thoroughly tested. Because untested documentation for
a non-existent API is the only thing worse than tested documentation
for a non-existent API.

Tests cover:
- EndpointDefinition and ParameterDefinition dataclasses
- EndpointRegistry with all 30 fictional endpoints
- SchemaGenerator introspection of domain models
- ExceptionToHTTPMapper with ALL exception classes
- OpenAPIGenerator spec assembly and serialization
- ASCIISwaggerUI terminal rendering
- OpenAPIDashboard statistics rendering
- OpenAPI-specific exception hierarchy (EFP-OA00 through EFP-OA11)
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import unittest

from enterprise_fizzbuzz.domain import exceptions as exceptions_module
from enterprise_fizzbuzz.domain import models as models_module
from enterprise_fizzbuzz.domain.exceptions import (
    DuplicateOperationIdError,
    EndpointRegistrationError,
    ExceptionMappingError,
    FizzBuzzError,
    InvalidEndpointPathError,
    OpenAPIDashboardRenderError,
    OpenAPIError,
    OpenAPISerializationError,
    OpenAPISpecGenerationError,
    SchemaIntrospectionError,
    SecuritySchemeNotFoundError,
    SwaggerUIRenderError,
    TagNotFoundError,
)
from enterprise_fizzbuzz.domain.models import EventType
from enterprise_fizzbuzz.infrastructure.openapi import (
    ASCIISwaggerUI,
    EndpointDefinition,
    EndpointRegistry,
    ExceptionToHTTPMapper,
    OpenAPIDashboard,
    OpenAPIGenerator,
    ParameterDefinition,
    SchemaGenerator,
)


class TestParameterDefinition(unittest.TestCase):
    """Tests for the ParameterDefinition frozen dataclass."""

    def test_create_required_path_parameter(self):
        """A path parameter should be required by default."""
        param = ParameterDefinition(
            name="number",
            location="path",
            param_type="integer",
            description="The number to evaluate.",
        )
        self.assertEqual(param.name, "number")
        self.assertEqual(param.location, "path")
        self.assertEqual(param.param_type, "integer")
        self.assertTrue(param.required)

    def test_create_optional_query_parameter(self):
        """Query parameters can be optional with defaults."""
        param = ParameterDefinition(
            name="strategy",
            location="query",
            param_type="string",
            description="Evaluation strategy.",
            required=False,
            default="standard",
            enum_values=("standard", "machine_learning"),
        )
        self.assertFalse(param.required)
        self.assertEqual(param.default, "standard")
        self.assertIn("machine_learning", param.enum_values)

    def test_frozen_dataclass(self):
        """ParameterDefinition should be immutable (frozen)."""
        param = ParameterDefinition(
            name="x", location="query", param_type="string", description="test"
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            param.name = "y"  # type: ignore[misc]

    def test_parameter_with_example(self):
        """Parameters can have example values for documentation."""
        param = ParameterDefinition(
            name="number",
            location="path",
            param_type="integer",
            description="A number.",
            example=15,
        )
        self.assertEqual(param.example, 15)


class TestEndpointDefinition(unittest.TestCase):
    """Tests for the EndpointDefinition frozen dataclass."""

    def test_create_simple_endpoint(self):
        """An endpoint should have path, method, tag, and operation_id."""
        ep = EndpointDefinition(
            path="/api/v1/test",
            method="GET",
            tag="Meta",
            summary="Test endpoint",
            description="A test.",
            operation_id="testOp",
        )
        self.assertEqual(ep.path, "/api/v1/test")
        self.assertEqual(ep.method, "GET")
        self.assertFalse(ep.deprecated)

    def test_deprecated_endpoint(self):
        """Deprecated endpoints should be marked accordingly."""
        ep = EndpointDefinition(
            path="/api/v1/old",
            method="GET",
            tag="Meta",
            summary="Old",
            description="Deprecated.",
            operation_id="oldOp",
            deprecated=True,
        )
        self.assertTrue(ep.deprecated)

    def test_endpoint_with_parameters(self):
        """Endpoints can have parameter definitions."""
        param = ParameterDefinition(
            name="id", location="path", param_type="integer", description="ID"
        )
        ep = EndpointDefinition(
            path="/api/v1/thing/{id}",
            method="GET",
            tag="Meta",
            summary="Get thing",
            description="Gets a thing.",
            operation_id="getThing",
            parameters=(param,),
        )
        self.assertEqual(len(ep.parameters), 1)
        self.assertEqual(ep.parameters[0].name, "id")

    def test_endpoint_with_request_body(self):
        """Endpoints can specify a request body schema."""
        ep = EndpointDefinition(
            path="/api/v1/batch",
            method="POST",
            tag="Evaluation",
            summary="Batch eval",
            description="Batch.",
            operation_id="batch",
            request_body_schema="BatchEvaluationRequest",
        )
        self.assertEqual(ep.request_body_schema, "BatchEvaluationRequest")


class TestEndpointRegistry(unittest.TestCase):
    """Tests for the EndpointRegistry containing 30 fictional endpoints."""

    def test_total_endpoint_count(self):
        """The registry should contain exactly 30 endpoints."""
        endpoints = EndpointRegistry.get_all_endpoints()
        self.assertEqual(len(endpoints), 30)

    def test_all_seven_tag_groups_present(self):
        """All 7 tag groups should be represented."""
        endpoints = EndpointRegistry.get_all_endpoints()
        tags = {ep.tag for ep in endpoints}
        expected_tags = {
            "Evaluation", "Audit", "ML", "Compliance",
            "Operations", "Pipeline", "Meta",
        }
        self.assertEqual(tags, expected_tags)

    def test_tag_descriptions_match_tags(self):
        """Every tag used by endpoints should have a description."""
        endpoints = EndpointRegistry.get_all_endpoints()
        used_tags = {ep.tag for ep in endpoints}
        described_tags = set(EndpointRegistry.get_tag_descriptions().keys())
        self.assertEqual(used_tags, described_tags)

    def test_unique_operation_ids(self):
        """Every endpoint must have a unique operationId."""
        endpoints = EndpointRegistry.get_all_endpoints()
        operation_ids = [ep.operation_id for ep in endpoints]
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_all_paths_start_with_slash(self):
        """All endpoint paths must start with '/'."""
        for ep in EndpointRegistry.get_all_endpoints():
            self.assertTrue(
                ep.path.startswith("/"),
                f"Path '{ep.path}' does not start with '/'",
            )

    def test_valid_http_methods(self):
        """All endpoints must use valid HTTP methods."""
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH"}
        for ep in EndpointRegistry.get_all_endpoints():
            self.assertIn(
                ep.method.upper(), valid_methods,
                f"Invalid method '{ep.method}' for {ep.path}",
            )

    def test_evaluation_tag_has_endpoints(self):
        """The Evaluation tag should have multiple endpoints."""
        endpoints = EndpointRegistry.get_all_endpoints()
        eval_eps = [ep for ep in endpoints if ep.tag == "Evaluation"]
        self.assertGreaterEqual(len(eval_eps), 4)

    def test_at_least_one_deprecated_endpoint(self):
        """There should be at least one deprecated endpoint."""
        endpoints = EndpointRegistry.get_all_endpoints()
        deprecated = [ep for ep in endpoints if ep.deprecated]
        self.assertGreaterEqual(len(deprecated), 1)

    def test_at_least_one_post_endpoint(self):
        """There should be at least one POST endpoint."""
        endpoints = EndpointRegistry.get_all_endpoints()
        posts = [ep for ep in endpoints if ep.method == "POST"]
        self.assertGreaterEqual(len(posts), 3)

    def test_at_least_one_delete_endpoint(self):
        """There should be at least one DELETE endpoint."""
        endpoints = EndpointRegistry.get_all_endpoints()
        deletes = [ep for ep in endpoints if ep.method == "DELETE"]
        self.assertGreaterEqual(len(deletes), 1)


class TestSchemaGenerator(unittest.TestCase):
    """Tests for the SchemaGenerator that introspects domain models."""

    def test_generate_all_schemas_returns_dict(self):
        """generate_all_schemas should return a non-empty dict."""
        schemas = SchemaGenerator.generate_all_schemas()
        self.assertIsInstance(schemas, dict)
        self.assertGreater(len(schemas), 0)

    def test_fizzbuzz_result_schema_has_properties(self):
        """FizzBuzzResult should have 'number' and 'output' properties."""
        schemas = SchemaGenerator.generate_all_schemas()
        self.assertIn("FizzBuzzResult", schemas)
        fb_schema = schemas["FizzBuzzResult"]
        self.assertEqual(fb_schema["type"], "object")
        self.assertIn("number", fb_schema["properties"])
        self.assertIn("output", fb_schema["properties"])

    def test_enum_schema_has_enum_values(self):
        """Enum classes should be converted to string enums."""
        schemas = SchemaGenerator.generate_all_schemas()
        self.assertIn("FizzBuzzClassification", schemas)
        cls_schema = schemas["FizzBuzzClassification"]
        self.assertEqual(cls_schema["type"], "string")
        self.assertIn("FIZZ", cls_schema["enum"])
        self.assertIn("BUZZ", cls_schema["enum"])
        self.assertIn("FIZZBUZZ", cls_schema["enum"])
        self.assertIn("PLAIN", cls_schema["enum"])

    def test_evaluation_strategy_enum(self):
        """EvaluationStrategy should be an enum schema."""
        schemas = SchemaGenerator.generate_all_schemas()
        self.assertIn("EvaluationStrategy", schemas)
        self.assertIn("STANDARD", schemas["EvaluationStrategy"]["enum"])
        self.assertIn("MACHINE_LEARNING", schemas["EvaluationStrategy"]["enum"])

    def test_synthetic_schemas_included(self):
        """Synthetic schemas like BatchEvaluationRequest should be present."""
        schemas = SchemaGenerator.generate_all_schemas()
        self.assertIn("BatchEvaluationRequest", schemas)
        self.assertIn("BatchEvaluationResponse", schemas)
        self.assertIn("RangeEvaluationRequest", schemas)
        self.assertIn("ErrorResponse", schemas)

    def test_error_response_has_required_fields(self):
        """ErrorResponse should require error_code and message."""
        schemas = SchemaGenerator.generate_all_schemas()
        error_schema = schemas["ErrorResponse"]
        self.assertIn("error_code", error_schema["required"])
        self.assertIn("message", error_schema["required"])

    def test_dataclass_required_fields(self):
        """Dataclass fields without defaults should be marked as required."""
        schemas = SchemaGenerator.generate_all_schemas()
        fb_schema = schemas["FizzBuzzResult"]
        self.assertIn("number", fb_schema.get("required", []))
        self.assertIn("output", fb_schema.get("required", []))

    def test_health_status_enum(self):
        """HealthStatus should include EXISTENTIAL_CRISIS."""
        schemas = SchemaGenerator.generate_all_schemas()
        self.assertIn("HealthStatus", schemas)
        self.assertIn("EXISTENTIAL_CRISIS", schemas["HealthStatus"]["enum"])

    def test_all_dataclasses_have_schemas(self):
        """Every dataclass in models should have a generated schema."""
        schemas = SchemaGenerator.generate_all_schemas()
        for name, obj in inspect.getmembers(models_module):
            if (
                inspect.isclass(obj)
                and dataclasses.is_dataclass(obj)
                and obj.__module__ == models_module.__name__
            ):
                self.assertIn(name, schemas, f"Missing schema for dataclass {name}")

    def test_all_enums_have_schemas(self):
        """Every Enum in models should have a generated schema."""
        from enum import Enum
        schemas = SchemaGenerator.generate_all_schemas()
        for name, obj in inspect.getmembers(models_module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, Enum)
                and obj.__module__ == models_module.__name__
            ):
                self.assertIn(name, schemas, f"Missing schema for enum {name}")


class TestExceptionToHTTPMapper(unittest.TestCase):
    """Tests for the ExceptionToHTTPMapper that maps ALL exceptions."""

    def test_all_exceptions_are_mapped(self):
        """Every exception in the exceptions module should have a mapping."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        for name, obj in inspect.getmembers(exceptions_module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, FizzBuzzError)
                and obj.__module__ == exceptions_module.__name__
            ):
                self.assertIn(
                    name, mappings,
                    f"Exception {name} is not mapped to an HTTP status code",
                )

    def test_budget_exceeded_is_402(self):
        """BudgetExceededError must map to 402 Payment Required."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        self.assertEqual(mappings["BudgetExceededError"], 402)

    def test_gdpr_erasure_paradox_is_451(self):
        """GDPRErasureParadoxError must map to 451 Unavailable For Legal Reasons."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        self.assertEqual(mappings["GDPRErasureParadoxError"], 451)

    def test_rate_limit_exceeded_is_429(self):
        """RateLimitExceededError must map to 429 Too Many Requests."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        self.assertEqual(mappings["RateLimitExceededError"], 429)

    def test_circuit_open_is_503(self):
        """CircuitOpenError must map to 503 Service Unavailable."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        self.assertEqual(mappings["CircuitOpenError"], 503)

    def test_insufficient_privileges_is_403(self):
        """InsufficientFizzPrivilegesError must map to 403 Forbidden."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        self.assertEqual(mappings["InsufficientFizzPrivilegesError"], 403)

    def test_token_validation_is_401(self):
        """TokenValidationError must map to 401 Unauthorized."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        self.assertEqual(mappings["TokenValidationError"], 401)

    def test_all_mappings_have_valid_status_codes(self):
        """All mapped status codes should be valid HTTP status codes."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        for name, code in mappings.items():
            self.assertGreaterEqual(code, 400, f"{name} has invalid code {code}")
            self.assertLessEqual(code, 599, f"{name} has invalid code {code}")

    def test_get_status_description(self):
        """Status descriptions should be correct."""
        self.assertEqual(
            ExceptionToHTTPMapper.get_status_description(402),
            "Payment Required",
        )
        self.assertEqual(
            ExceptionToHTTPMapper.get_status_description(451),
            "Unavailable For Legal Reasons",
        )
        self.assertEqual(
            ExceptionToHTTPMapper.get_status_description(429),
            "Too Many Requests",
        )

    def test_unique_status_codes_sorted(self):
        """get_unique_status_codes should return a sorted list."""
        codes = ExceptionToHTTPMapper.get_unique_status_codes()
        self.assertEqual(codes, sorted(codes))
        self.assertGreater(len(codes), 5)

    def test_get_exceptions_for_status(self):
        """Should return exception names for a given status code."""
        exceptions_403 = ExceptionToHTTPMapper.get_exceptions_for_status(403)
        self.assertIn("InsufficientFizzPrivilegesError", exceptions_403)

    def test_openapi_exceptions_mapped(self):
        """OpenAPI-specific exceptions should be mapped."""
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        self.assertIn("OpenAPIError", mappings)
        self.assertIn("SchemaIntrospectionError", mappings)
        self.assertIn("SwaggerUIRenderError", mappings)


class TestOpenAPIGenerator(unittest.TestCase):
    """Tests for the OpenAPIGenerator that builds the full spec."""

    def test_generate_returns_valid_structure(self):
        """The generated spec should have all required top-level keys."""
        spec = OpenAPIGenerator.generate()
        self.assertIn("openapi", spec)
        self.assertIn("info", spec)
        self.assertIn("servers", spec)
        self.assertIn("paths", spec)
        self.assertIn("components", spec)
        self.assertIn("tags", spec)

    def test_openapi_version_is_3_1(self):
        """The spec should declare OpenAPI 3.1.0."""
        spec = OpenAPIGenerator.generate()
        self.assertEqual(spec["openapi"], "3.1.0")

    def test_server_url_is_localhost_0(self):
        """The server URL MUST be http://localhost:0."""
        spec = OpenAPIGenerator.generate()
        self.assertEqual(spec["servers"][0]["url"], "http://localhost:0")

    def test_server_description_says_does_not_exist(self):
        """The server description should acknowledge non-existence."""
        spec = OpenAPIGenerator.generate()
        desc = spec["servers"][0]["description"]
        self.assertIn("does not exist", desc.lower())

    def test_info_contains_title(self):
        """The info section should have a title."""
        spec = OpenAPIGenerator.generate()
        self.assertIn("title", spec["info"])
        self.assertIn("FizzBuzz", spec["info"]["title"])

    def test_info_contains_contact(self):
        """The info section should have contact information."""
        spec = OpenAPIGenerator.generate()
        self.assertIn("contact", spec["info"])
        self.assertIn("Bob McFizzington", spec["info"]["contact"]["name"])

    def test_paths_not_empty(self):
        """The spec should contain path definitions."""
        spec = OpenAPIGenerator.generate()
        self.assertGreater(len(spec["paths"]), 0)

    def test_components_has_schemas(self):
        """Components should include schemas."""
        spec = OpenAPIGenerator.generate()
        self.assertIn("schemas", spec["components"])
        self.assertGreater(len(spec["components"]["schemas"]), 0)

    def test_components_has_security_schemes(self):
        """Components should include security schemes."""
        spec = OpenAPIGenerator.generate()
        self.assertIn("securitySchemes", spec["components"])
        self.assertIn("FizzBuzzApiKey", spec["components"]["securitySchemes"])
        self.assertIn("BearerAuth", spec["components"]["securitySchemes"])

    def test_to_json_returns_valid_json(self):
        """to_json() should return valid parseable JSON."""
        json_str = OpenAPIGenerator.to_json()
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed["openapi"], "3.1.0")

    def test_to_json_uses_indent_2(self):
        """to_json() should use indent=2 for pretty printing."""
        json_str = OpenAPIGenerator.to_json()
        # With indent=2, opening brace is on first line, next key indented
        self.assertIn('  "openapi"', json_str)

    def test_to_yaml_returns_string(self):
        """to_yaml() should return a non-empty string."""
        yaml_str = OpenAPIGenerator.to_yaml()
        self.assertIsInstance(yaml_str, str)
        self.assertGreater(len(yaml_str), 100)
        self.assertIn("openapi", yaml_str)

    def test_to_yaml_contains_header_comments(self):
        """to_yaml() should include header comments."""
        yaml_str = OpenAPIGenerator.to_yaml()
        self.assertIn("# Enterprise FizzBuzz Platform", yaml_str)
        self.assertIn("localhost:0", yaml_str)

    def test_security_section_present(self):
        """The top-level security section should be present."""
        spec = OpenAPIGenerator.generate()
        self.assertIn("security", spec)
        self.assertIsInstance(spec["security"], list)

    def test_bob_stress_level_in_info(self):
        """Bob's stress level should be in the info extensions."""
        spec = OpenAPIGenerator.generate()
        self.assertEqual(spec["info"]["x-bob-stress-level"], 94.7)


class TestASCIISwaggerUI(unittest.TestCase):
    """Tests for the ASCII Swagger UI terminal renderer."""

    def test_render_returns_string(self):
        """render() should return a non-empty string."""
        output = ASCIISwaggerUI.render()
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 100)

    def test_render_contains_swagger_ui_header(self):
        """The output should contain the Swagger UI title."""
        output = ASCIISwaggerUI.render()
        self.assertIn("SWAGGER UI", output)

    def test_render_contains_server_info(self):
        """The output should show the server URL."""
        output = ASCIISwaggerUI.render()
        self.assertIn("http://localhost:0", output)
        self.assertIn("does not exist", output)

    def test_render_contains_try_it_buttons(self):
        """The output should contain [Try It] buttons."""
        output = ASCIISwaggerUI.render()
        self.assertIn("[Try It]", output)

    def test_try_it_acknowledges_no_server(self):
        """[Try It] buttons should acknowledge there is no server."""
        output = ASCIISwaggerUI.render()
        self.assertIn("server does not exist", output)

    def test_render_contains_all_tag_groups(self):
        """The output should contain all 7 tag groups."""
        output = ASCIISwaggerUI.render()
        for tag in ["Evaluation", "Audit", "ML", "Compliance",
                     "Operations", "Pipeline", "Meta"]:
            self.assertIn(f"[{tag}]", output)

    def test_render_contains_box_drawing(self):
        """The output should use box-drawing characters."""
        output = ASCIISwaggerUI.render()
        self.assertIn("+", output)
        self.assertIn("|", output)
        self.assertIn("=", output)

    def test_render_with_custom_width(self):
        """render() should accept a custom width parameter."""
        output = ASCIISwaggerUI.render(width=100)
        self.assertIsInstance(output, str)
        # Check that wider output has longer lines
        lines = output.split("\n")
        box_lines = [l for l in lines if l.strip().startswith("+")]
        if box_lines:
            self.assertGreaterEqual(len(box_lines[0]), 95)

    def test_render_contains_statistics(self):
        """The output should show specification statistics."""
        output = ASCIISwaggerUI.render()
        self.assertIn("Endpoints:", output)
        self.assertIn("Schemas:", output)
        self.assertIn("Server Exists:", output)
        self.assertIn("No", output)

    def test_render_shows_method_badges(self):
        """The output should show HTTP method badges."""
        output = ASCIISwaggerUI.render()
        self.assertIn("GET", output)
        self.assertIn("POST", output)
        self.assertIn("DELETE", output)


class TestOpenAPIDashboard(unittest.TestCase):
    """Tests for the OpenAPI statistics dashboard."""

    def test_render_returns_string(self):
        """render() should return a non-empty string."""
        output = OpenAPIDashboard.render()
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 100)

    def test_render_contains_title(self):
        """The dashboard should have a title."""
        output = OpenAPIDashboard.render()
        self.assertIn("OPENAPI SPECIFICATION DASHBOARD", output)

    def test_render_shows_server_status(self):
        """The dashboard should show server status."""
        output = OpenAPIDashboard.render()
        self.assertIn("DOES NOT EXIST", output)
        self.assertIn("http://localhost:0", output)

    def test_render_shows_endpoint_counts(self):
        """The dashboard should show endpoint counts by tag."""
        output = OpenAPIDashboard.render()
        self.assertIn("ENDPOINTS BY TAG GROUP", output)

    def test_render_shows_schema_inventory(self):
        """The dashboard should show schema inventory."""
        output = OpenAPIDashboard.render()
        self.assertIn("SCHEMA INVENTORY", output)

    def test_render_shows_exception_mapping(self):
        """The dashboard should show exception mapping stats."""
        output = OpenAPIDashboard.render()
        self.assertIn("EXCEPTION -> HTTP STATUS MAPPING", output)

    def test_render_shows_security_schemes(self):
        """The dashboard should show security schemes."""
        output = OpenAPIDashboard.render()
        self.assertIn("SECURITY SCHEMES", output)
        self.assertIn("Bob McFizzington", output)
        self.assertIn("unavailable", output)

    def test_render_with_custom_width(self):
        """render() should accept a custom width parameter."""
        output = OpenAPIDashboard.render(width=90)
        self.assertIsInstance(output, str)


class TestOpenAPIExceptions(unittest.TestCase):
    """Tests for the OpenAPI-specific exception hierarchy."""

    def test_openapi_error_is_fizzbuzz_error(self):
        """OpenAPIError should inherit from FizzBuzzError."""
        err = OpenAPIError("test")
        self.assertIsInstance(err, FizzBuzzError)
        self.assertEqual(err.error_code, "EFP-OA00")

    def test_schema_introspection_error(self):
        """SchemaIntrospectionError should have EFP-OA01."""
        err = SchemaIntrospectionError("MyClass", "bad types")
        self.assertEqual(err.error_code, "EFP-OA01")
        self.assertIn("MyClass", str(err))
        self.assertEqual(err.class_name, "MyClass")

    def test_endpoint_registration_error(self):
        """EndpointRegistrationError should have EFP-OA02."""
        err = EndpointRegistrationError("/api/test", "GET", "already exists")
        self.assertEqual(err.error_code, "EFP-OA02")
        self.assertEqual(err.path, "/api/test")
        self.assertEqual(err.method, "GET")

    def test_exception_mapping_error(self):
        """ExceptionMappingError should have EFP-OA03."""
        err = ExceptionMappingError("WeirdError", "not found")
        self.assertEqual(err.error_code, "EFP-OA03")
        self.assertEqual(err.exception_name, "WeirdError")

    def test_spec_generation_error(self):
        """OpenAPISpecGenerationError should have EFP-OA04."""
        err = OpenAPISpecGenerationError("paths", "explosion")
        self.assertEqual(err.error_code, "EFP-OA04")
        self.assertEqual(err.section, "paths")

    def test_swagger_ui_render_error(self):
        """SwaggerUIRenderError should have EFP-OA05."""
        err = SwaggerUIRenderError("box drawing failed")
        self.assertEqual(err.error_code, "EFP-OA05")
        self.assertIn("swagger", str(err).lower())

    def test_dashboard_render_error(self):
        """OpenAPIDashboardRenderError should have EFP-OA06."""
        err = OpenAPIDashboardRenderError("width too narrow")
        self.assertEqual(err.error_code, "EFP-OA06")

    def test_serialization_error(self):
        """OpenAPISerializationError should have EFP-OA07."""
        err = OpenAPISerializationError("JSON", "circular ref")
        self.assertEqual(err.error_code, "EFP-OA07")
        self.assertEqual(err.format_name, "JSON")

    def test_invalid_endpoint_path_error(self):
        """InvalidEndpointPathError should have EFP-OA08."""
        err = InvalidEndpointPathError("no-slash", "must start with /")
        self.assertEqual(err.error_code, "EFP-OA08")
        self.assertEqual(err.path, "no-slash")

    def test_duplicate_operation_id_error(self):
        """DuplicateOperationIdError should have EFP-OA09."""
        err = DuplicateOperationIdError("getStuff", "/a", "/b")
        self.assertEqual(err.error_code, "EFP-OA09")
        self.assertEqual(err.operation_id, "getStuff")

    def test_security_scheme_not_found_error(self):
        """SecuritySchemeNotFoundError should have EFP-OA10."""
        err = SecuritySchemeNotFoundError("OAuth2")
        self.assertEqual(err.error_code, "EFP-OA10")
        self.assertEqual(err.scheme_name, "OAuth2")

    def test_tag_not_found_error(self):
        """TagNotFoundError should have EFP-REG09."""
        err = TagNotFoundError("test-repo", "Undefined")
        self.assertEqual(err.error_code, "EFP-REG09")
        self.assertEqual(err.context["tag"], "Undefined")


class TestOpenAPIEventTypes(unittest.TestCase):
    """Tests for the OpenAPI-related EventType enum entries."""

    def test_openapi_spec_generated_event(self):
        """OPENAPI_SPEC_GENERATED should exist in EventType."""
        self.assertIsNotNone(EventType.OPENAPI_SPEC_GENERATED)

    def test_openapi_schema_introspected_event(self):
        """OPENAPI_SCHEMA_INTROSPECTED should exist in EventType."""
        self.assertIsNotNone(EventType.OPENAPI_SCHEMA_INTROSPECTED)

    def test_openapi_exception_mapped_event(self):
        """OPENAPI_EXCEPTION_MAPPED should exist in EventType."""
        self.assertIsNotNone(EventType.OPENAPI_EXCEPTION_MAPPED)

    def test_openapi_swagger_ui_rendered_event(self):
        """OPENAPI_SWAGGER_UI_RENDERED should exist in EventType."""
        self.assertIsNotNone(EventType.OPENAPI_SWAGGER_UI_RENDERED)

    def test_openapi_dashboard_rendered_event(self):
        """OPENAPI_DASHBOARD_RENDERED should exist in EventType."""
        self.assertIsNotNone(EventType.OPENAPI_DASHBOARD_RENDERED)

    def test_openapi_yaml_exported_event(self):
        """OPENAPI_YAML_EXPORTED should exist in EventType."""
        self.assertIsNotNone(EventType.OPENAPI_YAML_EXPORTED)


class TestSpecIntegrity(unittest.TestCase):
    """Integration tests verifying the spec's internal consistency."""

    def test_all_response_schemas_exist_in_components(self):
        """Every schema referenced by endpoints should exist in components."""
        spec = OpenAPIGenerator.generate()
        schema_names = set(spec["components"]["schemas"].keys())

        for path, methods in spec["paths"].items():
            for method, operation in methods.items():
                # Check request body refs
                if "requestBody" in operation:
                    content = operation["requestBody"].get("content", {})
                    for media_type, media_def in content.items():
                        ref = media_def.get("schema", {}).get("$ref", "")
                        if ref:
                            schema_name = ref.split("/")[-1]
                            self.assertIn(
                                schema_name, schema_names,
                                f"Missing schema {schema_name} referenced by {method.upper()} {path}",
                            )

    def test_spec_is_json_serializable(self):
        """The entire spec should be JSON-serializable."""
        spec = OpenAPIGenerator.generate()
        json_str = json.dumps(spec, default=str)
        self.assertIsInstance(json_str, str)
        self.assertGreater(len(json_str), 100)

    def test_paths_match_endpoint_registry(self):
        """Paths in spec should match endpoints from the registry."""
        spec = OpenAPIGenerator.generate()
        registry_paths = {ep.path for ep in EndpointRegistry.get_all_endpoints()}
        spec_paths = set(spec["paths"].keys())
        self.assertEqual(registry_paths, spec_paths)


if __name__ == "__main__":
    unittest.main()

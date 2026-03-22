"""
Enterprise FizzBuzz Platform - OpenAPI Specification Generator & ASCII Swagger UI

Generates a complete OpenAPI 3.1 specification for the Enterprise FizzBuzz
Platform's fictional REST API, then renders it as an ASCII Swagger UI in
the terminal. Because the only thing better than an API that doesn't exist
is comprehensive documentation for that non-existent API.

The server URL is http://localhost:0, which is both a valid URL and a
profound statement about the platform's relationship with HTTP. Port 0
means "let the OS choose a port," but since we never bind a socket,
the OS never chooses, and the server remains forever theoretical.

The ASCII Swagger UI includes [Try It] buttons that acknowledge there
is no server to try anything against. This is not a limitation — it is
a philosophical position on the nature of API documentation.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, get_type_hints

from enterprise_fizzbuzz.domain import exceptions as exceptions_module
from enterprise_fizzbuzz.domain import models as models_module
from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.models import EventType


# ============================================================
# Data Classes for Endpoint & Parameter Definitions
# ============================================================


@dataclass(frozen=True)
class ParameterDefinition:
    """Defines a single parameter for a fictional API endpoint.

    Each parameter has a name, location (path, query, header, cookie),
    a type, and a description that probably contains more satire than
    useful information. The 'required' field is always True for path
    parameters, because that's how OpenAPI works, and we respect the
    specification even when we don't respect the concept of having
    an API server.

    Attributes:
        name: The parameter name as it would appear in the URL or headers.
        location: Where the parameter lives (path, query, header, cookie).
        param_type: The JSON Schema type (string, integer, boolean, number, array).
        description: A satirical description of what this parameter controls.
        required: Whether the parameter is mandatory.
        default: Default value, if any.
        enum_values: Allowed values for enum-style parameters.
        example: An example value for documentation purposes.
    """

    name: str
    location: str  # path | query | header | cookie
    param_type: str  # string | integer | boolean | number | array
    description: str
    required: bool = True
    default: Any = None
    enum_values: Optional[tuple[str, ...]] = None
    example: Any = None


@dataclass(frozen=True)
class EndpointDefinition:
    """Defines a single fictional API endpoint in the OpenAPI specification.

    Each endpoint has a path, HTTP method, tag group, summary, description,
    and zero or more parameters. The responses are auto-generated based on
    the exception-to-HTTP-status mapping, because every endpoint can fail
    in every possible way — that's the enterprise guarantee.

    Attributes:
        path: The URL path (e.g., "/api/v1/fizzbuzz/evaluate/{number}").
        method: The HTTP method (GET, POST, PUT, DELETE, PATCH).
        tag: The tag group this endpoint belongs to.
        summary: A one-line summary of what this endpoint pretends to do.
        description: A longer description with satirical commentary.
        operation_id: A unique identifier for this operation.
        parameters: Parameter definitions for this endpoint.
        request_body_schema: Optional schema name for the request body.
        response_schema: Optional schema name for the 200 response body.
        deprecated: Whether this endpoint is deprecated (some are, for comedy).
    """

    path: str
    method: str
    tag: str
    summary: str
    description: str
    operation_id: str
    parameters: tuple[ParameterDefinition, ...] = ()
    request_body_schema: Optional[str] = None
    response_schema: Optional[str] = None
    deprecated: bool = False


# ============================================================
# Endpoint Registry — 30 Fictional Endpoints
# ============================================================


class EndpointRegistry:
    """Registry of all fictional REST API endpoints for the Enterprise
    FizzBuzz Platform.

    Contains 30 endpoints organized across 7 tag groups, each more
    unnecessary than the last. These endpoints do not exist, have never
    existed, and will never exist — but they are documented with the
    same care and attention as if they served millions of requests
    per second. Which they don't. Because there is no server.

    Tag Groups:
        - Evaluation:  Core FizzBuzz evaluation operations
        - Audit:       Blockchain and compliance audit trail
        - ML:          Machine Learning model management
        - Compliance:  SOX, GDPR, HIPAA regulatory endpoints
        - Operations:  Health, metrics, circuit breakers
        - Pipeline:    Data pipeline and ETL management
        - Meta:        OpenAPI meta-endpoints (the spec about the spec)
    """

    _TAG_DESCRIPTIONS: dict[str, str] = {
        "Evaluation": (
            "Core FizzBuzz evaluation endpoints. These endpoints accept numbers "
            "and return their FizzBuzz classification through a pipeline of "
            "middleware, feature flags, rate limiting, and existential dread."
        ),
        "Audit": (
            "Blockchain-based immutable audit trail endpoints. Every FizzBuzz "
            "evaluation is recorded on an in-memory blockchain with proof-of-work "
            "mining, because accountability for modulo arithmetic is non-negotiable."
        ),
        "ML": (
            "Machine Learning model management endpoints. Train, evaluate, and "
            "interrogate the neural network that has been tasked with learning "
            "modulo arithmetic from scratch. Spoiler: it achieves ~95% accuracy "
            "on a problem that has a deterministic O(1) solution."
        ),
        "Compliance": (
            "Regulatory compliance endpoints spanning SOX segregation of duties, "
            "GDPR right-to-erasure (which triggers THE COMPLIANCE PARADOX), and "
            "HIPAA minimum necessary access controls. Bob McFizzington's stress "
            "level is exposed as a metric on every response."
        ),
        "Operations": (
            "Operational endpoints for health checks, Prometheus metrics, circuit "
            "breaker management, and SLA monitoring. These endpoints would be "
            "scraped by Prometheus if we had an HTTP server, which we do not."
        ),
        "Pipeline": (
            "Data Pipeline & ETL management endpoints for the five-stage "
            "Extract-Validate-Transform-Enrich-Load pipeline. Manage DAG "
            "execution, data lineage, and retroactive backfill operations "
            "for numbers that deserve a second enrichment pass."
        ),
        "Meta": (
            "Meta-endpoints about the API itself. The OpenAPI specification "
            "documenting the OpenAPI specification. The Swagger UI rendering "
            "the Swagger UI. It's turtles all the way down, and every turtle "
            "has a JSON Schema."
        ),
    }

    @classmethod
    def get_tag_descriptions(cls) -> dict[str, str]:
        """Return tag group descriptions for the OpenAPI spec."""
        return dict(cls._TAG_DESCRIPTIONS)

    @classmethod
    def get_all_endpoints(cls) -> list[EndpointDefinition]:
        """Return all 30 fictional endpoint definitions."""
        endpoints: list[EndpointDefinition] = []

        # ---- Evaluation (6 endpoints) ----
        endpoints.append(EndpointDefinition(
            path="/api/v1/fizzbuzz/evaluate/{number}",
            method="GET",
            tag="Evaluation",
            summary="Evaluate a single number through the FizzBuzz pipeline",
            description=(
                "Accepts a number and routes it through the full enterprise "
                "middleware stack: validation, rate limiting, feature flags, "
                "circuit breakers, distributed tracing, compliance checks, "
                "and finally — the modulo operator. Returns the canonical "
                "FizzBuzz classification along with approximately 4KB of "
                "metadata that nobody asked for."
            ),
            operation_id="evaluateNumber",
            parameters=(
                ParameterDefinition(
                    name="number",
                    location="path",
                    param_type="integer",
                    description="The number to evaluate. Must be a positive integer.",
                    example=15,
                ),
                ParameterDefinition(
                    name="strategy",
                    location="query",
                    param_type="string",
                    description="Evaluation strategy override.",
                    required=False,
                    enum_values=("standard", "chain_of_responsibility", "machine_learning"),
                    default="standard",
                ),
                ParameterDefinition(
                    name="X-FizzBuzz-Trace-Id",
                    location="header",
                    param_type="string",
                    description="Distributed trace identifier for cross-service correlation.",
                    required=False,
                ),
            ),
            response_schema="FizzBuzzResult",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/fizzbuzz/evaluate/batch",
            method="POST",
            tag="Evaluation",
            summary="Evaluate a batch of numbers through the FizzBuzz pipeline",
            description=(
                "Accepts an array of numbers and evaluates each one through "
                "the full enterprise pipeline. Results are returned in order, "
                "unless chaos engineering is enabled, in which case they are "
                "returned in whatever order the Chaos Monkey deems appropriate."
            ),
            operation_id="evaluateBatch",
            request_body_schema="BatchEvaluationRequest",
            response_schema="BatchEvaluationResponse",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/fizzbuzz/evaluate/range",
            method="POST",
            tag="Evaluation",
            summary="Evaluate a range of numbers",
            description=(
                "Evaluates all numbers in the specified range [start, end]. "
                "This is the enterprise equivalent of a for loop, but with "
                "significantly more YAML configuration and approximately "
                "47 more layers of abstraction."
            ),
            operation_id="evaluateRange",
            request_body_schema="RangeEvaluationRequest",
            response_schema="BatchEvaluationResponse",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/fizzbuzz/classify/{number}",
            method="GET",
            tag="Evaluation",
            summary="Get the canonical classification for a number",
            description=(
                "Returns the FizzBuzzClassification enum value without the "
                "full result metadata. For when you just need to know if "
                "it's Fizz, Buzz, FizzBuzz, or Plain — and you need to know "
                "it through 14 middleware layers."
            ),
            operation_id="classifyNumber",
            parameters=(
                ParameterDefinition(
                    name="number",
                    location="path",
                    param_type="integer",
                    description="The number to classify.",
                    example=42,
                ),
            ),
            response_schema="EvaluationResult",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/fizzbuzz/rules",
            method="GET",
            tag="Evaluation",
            summary="List all active FizzBuzz evaluation rules",
            description=(
                "Returns the currently configured FizzBuzz rules, including "
                "divisors, labels, and priorities. Spoiler: it's divisor 3 "
                "for Fizz and divisor 5 for Buzz. It has always been this. "
                "It will always be this."
            ),
            operation_id="listRules",
            response_schema="RuleDefinition",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/fizzbuzz/session/{session_id}/summary",
            method="GET",
            tag="Evaluation",
            summary="Get the summary for a completed evaluation session",
            description=(
                "Returns aggregate statistics for a completed FizzBuzz session: "
                "total numbers, Fizz count, Buzz count, FizzBuzz count, plain "
                "count, and the throughput in numbers-per-second — a metric "
                "that is simultaneously impressive and meaningless."
            ),
            operation_id="getSessionSummary",
            parameters=(
                ParameterDefinition(
                    name="session_id",
                    location="path",
                    param_type="string",
                    description="The UUID of the evaluation session.",
                    example="550e8400-e29b-41d4-a716-446655440000",
                ),
            ),
            response_schema="FizzBuzzSessionSummary",
        ))

        # ---- Audit (4 endpoints) ----
        endpoints.append(EndpointDefinition(
            path="/api/v1/audit/blockchain",
            method="GET",
            tag="Audit",
            summary="Retrieve the full blockchain audit ledger",
            description=(
                "Returns the complete immutable blockchain containing every "
                "FizzBuzz evaluation ever performed. Each block is cryptographically "
                "linked to the previous one with SHA-256 hashes and proof-of-work "
                "mining, because FizzBuzz results deserve the same level of "
                "tamper-proofing as Bitcoin transactions."
            ),
            operation_id="getBlockchain",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/audit/blockchain/block/{index}",
            method="GET",
            tag="Audit",
            summary="Retrieve a specific block from the blockchain",
            description=(
                "Returns a single block by index, including its hash, previous "
                "hash, timestamp, nonce, and the FizzBuzz evaluation data it "
                "immutably preserves for all eternity (or until the process exits)."
            ),
            operation_id="getBlock",
            parameters=(
                ParameterDefinition(
                    name="index",
                    location="path",
                    param_type="integer",
                    description="The block index in the blockchain.",
                    example=0,
                ),
            ),
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/audit/blockchain/verify",
            method="POST",
            tag="Audit",
            summary="Verify the integrity of the entire blockchain",
            description=(
                "Walks the blockchain from genesis to tip, verifying that every "
                "block's hash matches its contents and that the chain of previous "
                "hashes is unbroken. Returns a verification report that is as "
                "thorough as it is unnecessary for in-memory FizzBuzz results."
            ),
            operation_id="verifyBlockchain",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/audit/events",
            method="GET",
            tag="Audit",
            summary="Query the append-only event store",
            description=(
                "Returns events from the Event Sourcing append-only log, "
                "with optional filtering by event type, sequence range, and "
                "temporal queries. Supports point-in-time state reconstruction "
                "for when you need to know what FizzBuzz thought 15 was at "
                "3:42:07.123456 PM last Tuesday."
            ),
            operation_id="queryEvents",
            parameters=(
                ParameterDefinition(
                    name="event_type",
                    location="query",
                    param_type="string",
                    description="Filter by event type.",
                    required=False,
                ),
                ParameterDefinition(
                    name="from_seq",
                    location="query",
                    param_type="integer",
                    description="Start sequence number for the query range.",
                    required=False,
                    default=0,
                ),
                ParameterDefinition(
                    name="limit",
                    location="query",
                    param_type="integer",
                    description="Maximum number of events to return.",
                    required=False,
                    default=100,
                ),
            ),
            response_schema="Event",
        ))

        # ---- ML (4 endpoints) ----
        endpoints.append(EndpointDefinition(
            path="/api/v1/ml/models",
            method="GET",
            tag="ML",
            summary="List all trained ML models",
            description=(
                "Returns metadata about the neural network models trained to "
                "predict FizzBuzz classifications. Each model covers one rule "
                "(Fizz or Buzz) and has a training accuracy, loss curve, and "
                "existential confidence score."
            ),
            operation_id="listModels",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/ml/models/{rule_name}/train",
            method="POST",
            tag="ML",
            summary="Retrain the ML model for a specific rule",
            description=(
                "Triggers a full retraining cycle for the neural network "
                "responsible for the specified rule. The model will learn "
                "modulo arithmetic from scratch using gradient descent, "
                "which is approximately 10^9 times less efficient than the "
                "modulo operator it's trying to replace."
            ),
            operation_id="trainModel",
            parameters=(
                ParameterDefinition(
                    name="rule_name",
                    location="path",
                    param_type="string",
                    description="The rule whose model should be retrained.",
                    example="FizzRule",
                ),
            ),
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/ml/predict/{number}",
            method="GET",
            tag="ML",
            summary="Get raw ML prediction for a number",
            description=(
                "Returns the raw sigmoid output from the neural network for "
                "the given number, before the Anti-Corruption Layer applies "
                "its decision thresholds. Useful for understanding why the "
                "ML engine thinks 14.999 is definitely FizzBuzz."
            ),
            operation_id="predict",
            parameters=(
                ParameterDefinition(
                    name="number",
                    location="path",
                    param_type="integer",
                    description="The number to predict.",
                    example=15,
                ),
            ),
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/ml/confidence/report",
            method="GET",
            tag="ML",
            summary="Generate ML confidence report",
            description=(
                "Generates a comprehensive report on the ML engine's confidence "
                "levels across all evaluated numbers. Includes accuracy metrics, "
                "confusion matrices (that confuse no one), and a ranking of "
                "numbers the model is least confident about."
            ),
            operation_id="getConfidenceReport",
        ))

        # ---- Compliance (5 endpoints) ----
        endpoints.append(EndpointDefinition(
            path="/api/v1/compliance/check/{number}",
            method="POST",
            tag="Compliance",
            summary="Run compliance checks on a FizzBuzz evaluation",
            description=(
                "Subjects a FizzBuzz evaluation to the full weight of SOX, "
                "GDPR, and HIPAA compliance frameworks. Returns a compliance "
                "verdict and, if applicable, THE COMPLIANCE PARADOX — the "
                "irreconcilable conflict between GDPR erasure rights and "
                "immutable data stores."
            ),
            operation_id="runComplianceCheck",
            parameters=(
                ParameterDefinition(
                    name="number",
                    location="path",
                    param_type="integer",
                    description="The number (data subject) to check.",
                    example=42,
                ),
            ),
            response_schema="ComplianceCheckResult",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/compliance/gdpr/erase/{number}",
            method="DELETE",
            tag="Compliance",
            summary="Submit a GDPR right-to-erasure request",
            description=(
                "Initiates a GDPR Article 17 right-to-erasure request for the "
                "specified number. This WILL trigger THE COMPLIANCE PARADOX, "
                "because the data exists in both an append-only event store "
                "and an immutable blockchain. The resulting DataDeletionCertificate "
                "ironically documents what was supposed to be deleted."
            ),
            operation_id="gdprErase",
            parameters=(
                ParameterDefinition(
                    name="number",
                    location="path",
                    param_type="integer",
                    description="The data subject (number) requesting erasure.",
                    example=15,
                ),
            ),
            response_schema="DataDeletionCertificate",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/compliance/sox/audit-trail",
            method="GET",
            tag="Compliance",
            summary="Retrieve the SOX segregation of duties audit trail",
            description=(
                "Returns the complete audit trail of personnel assignments "
                "for Fizz evaluation, Buzz evaluation, and output formatting. "
                "SOX Section 404 demands that no single person evaluates both "
                "Fizz AND Buzz. The virtual personnel roster ensures this "
                "sacred separation of duties is maintained."
            ),
            operation_id="getSoxAuditTrail",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/compliance/hipaa/phi-access-log",
            method="GET",
            tag="Compliance",
            summary="Retrieve the HIPAA PHI access log",
            description=(
                "Returns all access events for Protected Health Information "
                "(FizzBuzz results), including who accessed what, when, and "
                "at what HIPAA minimum necessary level. All FizzBuzz results "
                "are classified as PHI because someone in legal said they "
                "could theoretically be part of a patient's medical record."
            ),
            operation_id="getPhiAccessLog",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/compliance/officer/status",
            method="GET",
            tag="Compliance",
            summary="Check the compliance officer's availability",
            description=(
                "Returns the current status of Bob McFizzington, Chief FizzBuzz "
                "Compliance Officer. His 'available' field has never been true. "
                "His stress level only goes up. He exists in a perpetual state "
                "of compliance-induced existential dread."
            ),
            operation_id="getComplianceOfficerStatus",
            deprecated=True,  # Bob is permanently unavailable
        ))

        # ---- Operations (5 endpoints) ----
        endpoints.append(EndpointDefinition(
            path="/api/v1/ops/health/liveness",
            method="GET",
            tag="Operations",
            summary="Kubernetes-style liveness probe",
            description=(
                "Evaluates the canary number (15) and verifies it returns "
                "'FizzBuzz'. If this check fails, the platform has forgotten "
                "how to perform modulo arithmetic, which is the computational "
                "equivalent of forgetting how to breathe."
            ),
            operation_id="livenessProbe",
            response_schema="HealthReport",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/ops/health/readiness",
            method="GET",
            tag="Operations",
            summary="Kubernetes-style readiness probe",
            description=(
                "Checks all subsystem health statuses and determines if the "
                "platform is ready to accept FizzBuzz evaluation traffic. "
                "A subsystem in EXISTENTIAL_CRISIS status will fail readiness."
            ),
            operation_id="readinessProbe",
            response_schema="HealthReport",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/ops/metrics",
            method="GET",
            tag="Operations",
            summary="Prometheus-style metrics endpoint",
            description=(
                "Returns all collected metrics in the Prometheus text "
                "exposition format. This endpoint would be scraped by "
                "Prometheus every 15 seconds if we had an HTTP server. "
                "We do not. The metrics accumulate in RAM, unscraped, "
                "like unread emails in a shared inbox."
            ),
            operation_id="getMetrics",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/ops/circuit-breaker/{name}/status",
            method="GET",
            tag="Operations",
            summary="Get circuit breaker status",
            description=(
                "Returns the current state of the named circuit breaker "
                "(CLOSED, OPEN, or HALF_OPEN), along with failure counts, "
                "backoff timers, and the philosophical question of whether "
                "modulo arithmetic really needs fault tolerance."
            ),
            operation_id="getCircuitBreakerStatus",
            parameters=(
                ParameterDefinition(
                    name="name",
                    location="path",
                    param_type="string",
                    description="The circuit breaker name.",
                    example="fizzbuzz-main",
                ),
            ),
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/ops/sla/dashboard",
            method="GET",
            tag="Operations",
            summary="Get SLA monitoring dashboard data",
            description=(
                "Returns current SLO compliance percentages, error budget "
                "burn rates, and on-call status. Bob McFizzington is always "
                "the on-call engineer. Bob McFizzington is never available. "
                "This is by design."
            ),
            operation_id="getSlaDashboard",
        ))

        # ---- Pipeline (3 endpoints) ----
        endpoints.append(EndpointDefinition(
            path="/api/v1/pipeline/execute",
            method="POST",
            tag="Pipeline",
            summary="Execute the 5-stage ETL pipeline",
            description=(
                "Triggers the Extract-Validate-Transform-Enrich-Load pipeline "
                "for a batch of numbers. Each number passes through five stages "
                "of enterprise ceremony, accumulating metadata like a snowball "
                "rolling downhill through a documentation factory."
            ),
            operation_id="executePipeline",
            request_body_schema="RangeEvaluationRequest",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/pipeline/dag",
            method="GET",
            tag="Pipeline",
            summary="Get the pipeline DAG topology",
            description=(
                "Returns the Directed Acyclic Graph that defines the pipeline "
                "stage execution order. It is a straight line. It has always "
                "been a straight line. But we topologically sort it anyway, "
                "because that's what enterprise data pipelines do."
            ),
            operation_id="getPipelineDag",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/pipeline/lineage/{record_id}",
            method="GET",
            tag="Pipeline",
            summary="Get data lineage for a specific record",
            description=(
                "Returns the complete provenance chain for a processed record, "
                "from extraction through enrichment. Every transformation, "
                "every enrichment, every checkpoint — all documented with "
                "the obsessive thoroughness of a supply chain auditor tracking "
                "a single bolt through a factory."
            ),
            operation_id="getRecordLineage",
            parameters=(
                ParameterDefinition(
                    name="record_id",
                    location="path",
                    param_type="string",
                    description="The UUID of the pipeline record.",
                    example="550e8400-e29b-41d4-a716-446655440000",
                ),
            ),
        ))

        # ---- Meta (3 endpoints) ----
        endpoints.append(EndpointDefinition(
            path="/api/v1/meta/openapi.json",
            method="GET",
            tag="Meta",
            summary="Get the OpenAPI specification (JSON)",
            description=(
                "Returns this very specification in JSON format. The spec "
                "documenting the spec. If you request this endpoint from "
                "within the spec, you create a recursive reference that would "
                "make Douglas Hofstadter proud."
            ),
            operation_id="getOpenApiJson",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/meta/openapi.yaml",
            method="GET",
            tag="Meta",
            summary="Get the OpenAPI specification (YAML)",
            description=(
                "Returns the OpenAPI specification in YAML format, because "
                "JSON wasn't indented enough. The YAML version is identical "
                "in content but 30% more readable and 300% more likely to "
                "break due to whitespace issues."
            ),
            operation_id="getOpenApiYaml",
        ))

        endpoints.append(EndpointDefinition(
            path="/api/v1/meta/swagger-ui",
            method="GET",
            tag="Meta",
            summary="Render the ASCII Swagger UI",
            description=(
                "Returns an ASCII art rendering of the Swagger UI for this "
                "specification. Features include box-drawing characters, "
                "[Try It] buttons that acknowledge there is no server, and "
                "a level of terminal-based documentation that would make "
                "any DevRel engineer weep with a complex mixture of pride "
                "and confusion."
            ),
            operation_id="getSwaggerUi",
        ))

        return endpoints


# ============================================================
# Schema Generator — Converts Domain Dataclasses to JSON Schema
# ============================================================


class SchemaGenerator:
    """Converts domain model dataclasses and enums to JSON Schema dictionaries.

    Uses dataclasses.fields() and typing.get_type_hints() to introspect
    the domain models and generate OpenAPI-compatible JSON Schema definitions.
    This is the kind of reflection-heavy meta-programming that makes
    Python developers feel simultaneously powerful and guilty.

    The generator handles:
    - Frozen and mutable dataclasses
    - Enum types (converted to string enums with all member names)
    - Nested type references (converted to $ref pointers)
    - Optional fields (wrapped in nullable schemas)
    - List and dict types (converted to arrays and additionalProperties)
    - Primitive types (str, int, float, bool)
    """

    _TYPE_MAP: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        bytes: "string",
    }

    @classmethod
    def generate_all_schemas(cls) -> dict[str, dict[str, Any]]:
        """Generate JSON Schema definitions for all domain model classes.

        Introspects the models module to find all dataclasses and enums,
        then generates a JSON Schema dict for each one.

        Returns:
            A dictionary mapping schema names to their JSON Schema definitions.
        """
        schemas: dict[str, dict[str, Any]] = {}

        for name, obj in inspect.getmembers(models_module):
            if inspect.isclass(obj) and obj.__module__ == models_module.__name__:
                if dataclasses.is_dataclass(obj):
                    schemas[name] = cls._dataclass_to_schema(obj)
                elif issubclass(obj, Enum):
                    schemas[name] = cls._enum_to_schema(obj)

        # Add synthetic request/response schemas
        schemas["BatchEvaluationRequest"] = {
            "type": "object",
            "description": "Request body for batch FizzBuzz evaluation.",
            "properties": {
                "numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Array of numbers to evaluate.",
                    "example": [1, 2, 3, 5, 15, 42],
                },
                "strategy": {
                    "type": "string",
                    "enum": ["standard", "chain_of_responsibility", "machine_learning"],
                    "description": "Evaluation strategy to use.",
                    "default": "standard",
                },
            },
            "required": ["numbers"],
        }

        schemas["BatchEvaluationResponse"] = {
            "type": "object",
            "description": "Response containing batch FizzBuzz evaluation results.",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/FizzBuzzResult"},
                    "description": "Array of evaluation results, one per input number.",
                },
                "session_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "The session identifier for this batch evaluation.",
                },
                "total_processing_time_ms": {
                    "type": "number",
                    "description": "Total processing time in milliseconds.",
                },
            },
        }

        schemas["RangeEvaluationRequest"] = {
            "type": "object",
            "description": "Request body for range-based FizzBuzz evaluation.",
            "properties": {
                "start": {
                    "type": "integer",
                    "description": "Start of the range (inclusive).",
                    "example": 1,
                },
                "end": {
                    "type": "integer",
                    "description": "End of the range (inclusive).",
                    "example": 100,
                },
            },
            "required": ["start", "end"],
        }

        schemas["ErrorResponse"] = {
            "type": "object",
            "description": (
                "Standard error response for all Enterprise FizzBuzz Platform "
                "API errors. Every error includes an error code, message, and "
                "optional context — because failing without documentation is "
                "just failing without style."
            ),
            "properties": {
                "error_code": {
                    "type": "string",
                    "description": "The EFP error code (e.g., EFP-0000).",
                    "example": "EFP-RL01",
                },
                "message": {
                    "type": "string",
                    "description": "A human-readable error message with satirical commentary.",
                },
                "context": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Additional context about the error.",
                },
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "When the error occurred (UTC).",
                },
            },
            "required": ["error_code", "message"],
        }

        return schemas

    @classmethod
    def _dataclass_to_schema(cls, dc_class: type) -> dict[str, Any]:
        """Convert a dataclass to a JSON Schema object definition."""
        schema: dict[str, Any] = {
            "type": "object",
            "description": (dc_class.__doc__ or "").strip().split("\n")[0],
        }

        properties: dict[str, Any] = {}
        required: list[str] = []

        try:
            hints = get_type_hints(dc_class)
        except Exception:
            hints = {}

        for f in dataclasses.fields(dc_class):
            type_hint = hints.get(f.name, str)
            prop_schema = cls._type_to_schema(type_hint, f.name)

            # Determine if required (no default and no default_factory)
            has_default = (
                f.default is not dataclasses.MISSING
                or f.default_factory is not dataclasses.MISSING  # type: ignore[misc]
            )
            if not has_default:
                required.append(f.name)

            properties[f.name] = prop_schema

        schema["properties"] = properties
        if required:
            schema["required"] = required

        return schema

    @classmethod
    def _enum_to_schema(cls, enum_class: type) -> dict[str, Any]:
        """Convert an Enum class to a JSON Schema string enum."""
        members = [m.name for m in enum_class]  # type: ignore[var-annotated]
        return {
            "type": "string",
            "description": (enum_class.__doc__ or "").strip().split("\n")[0],
            "enum": members,
        }

    @classmethod
    def _type_to_schema(cls, type_hint: Any, field_name: str = "") -> dict[str, Any]:
        """Convert a Python type annotation to a JSON Schema property."""
        # Handle None/NoneType
        if type_hint is type(None):
            return {"type": "null"}

        # Handle basic types
        if type_hint in cls._TYPE_MAP:
            schema: dict[str, Any] = {"type": cls._TYPE_MAP[type_hint]}
            if type_hint is str and "id" in field_name.lower():
                schema["format"] = "uuid"
            if type_hint is str and "time" in field_name.lower():
                schema["format"] = "date-time"
            return schema

        # Handle datetime
        if type_hint is datetime:
            return {"type": "string", "format": "date-time"}

        # Handle Any
        origin = getattr(type_hint, "__origin__", None)
        args = getattr(type_hint, "__args__", ())

        # Handle Optional[X] which is Union[X, None]
        if origin is type(None):
            return {"type": "string"}

        # Check for Optional (Union with NoneType)
        import typing
        if origin is getattr(typing, "Union", None):
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                inner = cls._type_to_schema(non_none[0], field_name)
                inner["nullable"] = True
                return inner
            return {"type": "string", "nullable": True}

        # Handle list
        if origin is list:
            if args:
                return {
                    "type": "array",
                    "items": cls._type_to_schema(args[0], field_name),
                }
            return {"type": "array", "items": {"type": "string"}}

        # Handle tuple
        if origin is tuple:
            if args:
                return {
                    "type": "array",
                    "items": cls._type_to_schema(args[0], field_name),
                }
            return {"type": "array", "items": {"type": "string"}}

        # Handle dict
        if origin is dict:
            return {
                "type": "object",
                "additionalProperties": True,
            }

        # Handle Enum subclasses
        if inspect.isclass(type_hint) and issubclass(type_hint, Enum):
            return {"$ref": f"#/components/schemas/{type_hint.__name__}"}

        # Handle dataclass references
        if inspect.isclass(type_hint) and dataclasses.is_dataclass(type_hint):
            return {"$ref": f"#/components/schemas/{type_hint.__name__}"}

        # Fallback for Any and unknown types
        return {"type": "string"}


# ============================================================
# Exception to HTTP Status Code Mapper
# ============================================================


class ExceptionToHTTPMapper:
    """Maps ALL Enterprise FizzBuzz Platform exceptions to HTTP status codes.

    Uses inspect to introspect the exceptions module and automatically discover
    every exception class that inherits from FizzBuzzError. Each exception is
    mapped to an appropriate HTTP status code based on its error semantics.

    Key mappings that were ordained by the Architecture Review Board:
    - BudgetExceededError           -> 402 Payment Required
    - GDPRErasureParadoxError       -> 451 Unavailable For Legal Reasons
    - RateLimitExceededError        -> 429 Too Many Requests
    - CircuitOpenError              -> 503 Service Unavailable
    - InsufficientFizzPrivilegesError -> 403 Forbidden
    - TokenValidationError          -> 401 Unauthorized

    All other exceptions default to 500 Internal Server Error, because when
    a FizzBuzz platform fails, it fails with enterprise-grade HTTP semantics.
    """

    # Explicit mappings for exceptions with specific HTTP semantics
    _EXPLICIT_MAPPINGS: dict[str, int] = {
        # 400 Bad Request family
        "ConfigurationError": 400,
        "ConfigurationValidationError": 400,
        "InvalidRangeError": 400,
        "CommandValidationError": 400,
        "ChaosConfigurationError": 400,
        "SLAConfigurationError": 400,
        "ConfigValidationRejectedError": 400,
        "WebhookEndpointValidationError": 400,
        "SchemaValidationError": 400,
        "ValidationStageError": 400,
        "TrafficAllocationError": 400,

        # 401 Unauthorized
        "AuthenticationError": 401,
        "TokenValidationError": 401,

        # 402 Payment Required
        "BudgetExceededError": 402,
        "QuotaExhaustedError": 402,

        # 403 Forbidden
        "InsufficientFizzPrivilegesError": 403,
        "NumberClassificationLevelExceededError": 403,
        "VaultAccessDeniedError": 403,
        "AuthorizationError": 403,

        # 404 Not Found
        "ConfigurationFileNotFoundError": 404,
        "PluginNotFoundError": 404,
        "SpanNotFoundError": 404,
        "TraceNotFoundError": 404,
        "FlagNotFoundError": 404,
        "OnCallNotFoundError": 404,
        "MigrationNotFoundError": 404,
        "ResultNotFoundError": 404,
        "MetricNotFoundError": 404,
        "ServiceNotFoundError": 404,
        "ExperimentNotFoundError": 404,
        "TopicNotFoundError": 404,
        "BackupNotFoundError": 404,
        "VaultSecretNotFoundError": 404,

        # 408 Request Timeout
        "CircuitBreakerTimeoutError": 408,
        "MeshLatencyInjectionError": 408,

        # 409 Conflict
        "RuleConflictError": 409,
        "FlagDependencyCycleError": 409,
        "MigrationAlreadyAppliedError": 409,
        "MigrationConflictError": 409,
        "CircularDependencyError": 409,
        "DuplicateBindingError": 409,
        "DuplicateMessageError": 409,
        "ExperimentAlreadyExistsError": 409,
        "TopicAlreadyExistsError": 409,
        "VaultAlreadyInitializedError": 409,

        # 410 Gone
        "CacheEntryExpiredError": 410,
        "VaultSecretExpiredError": 410,

        # 412 Precondition Failed
        "FlagDependencyNotMetError": 412,
        "MigrationDependencyError": 412,
        "MutualExclusionError": 412,

        # 418 I'm a Teapot (because why not)
        "ChaosInducedFizzBuzzError": 418,
        "ResultCorruptionDetectedError": 418,

        # 422 Unprocessable Entity
        "ModelConvergenceError": 422,
        "EventSequenceError": 422,
        "EventVersionConflictError": 422,
        "FlagLifecycleError": 422,
        "ExperimentStateError": 422,
        "SpanLifecycleError": 422,

        # 423 Locked
        "VaultSealedError": 423,

        # 424 Failed Dependency
        "DownstreamFizzBuzzDegradationError": 424,
        "DependencyGraphCycleError": 424,

        # 429 Too Many Requests
        "RateLimitExceededError": 429,

        # 451 Unavailable For Legal Reasons
        "GDPRErasureParadoxError": 451,
        "GDPRConsentRequiredError": 451,
        "ComplianceFrameworkNotEnabledError": 451,
        "SOXSegregationViolationError": 451,
        "HIPAAPrivacyViolationError": 451,
        "HIPAAMinimumNecessaryError": 451,

        # 500 Internal Server Error (explicit)
        "FizzBuzzError": 500,
        "RuleEvaluationError": 500,
        "MiddlewareError": 500,
        "FormatterError": 500,
        "ObserverError": 500,
        "PluginLoadError": 500,

        # 502 Bad Gateway
        "WebhookDeliveryError": 502,
        "MeshPacketLossError": 502,
        "SidecarProxyError": 502,

        # 503 Service Unavailable
        "CircuitOpenError": 503,
        "MeshCircuitOpenError": 503,
        "ServiceNotInitializedError": 503,
        "ComplianceOfficerUnavailableError": 503,

        # 507 Insufficient Storage
        "CacheCapacityExceededError": 507,
        "BackupVaultFullError": 507,
        "WebhookDeadLetterQueueFullError": 507,
        "CardinalityExplosionError": 507,

        # 508 Loop Detected
        "CacheInvalidationCascadeError": 508,
    }

    @classmethod
    def get_all_mappings(cls) -> dict[str, int]:
        """Return a mapping of every exception class name to its HTTP status code.

        Introspects the exceptions module to discover ALL exception classes,
        then maps each one using explicit mappings first, base class mappings
        second, and 500 as the default.

        Returns:
            Dict mapping exception class names to HTTP status codes.
        """
        mappings: dict[str, int] = {}

        for name, obj in inspect.getmembers(exceptions_module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, FizzBuzzError)
                and obj.__module__ == exceptions_module.__name__
            ):
                mappings[name] = cls._resolve_status(name, obj)

        return mappings

    @classmethod
    def _resolve_status(cls, name: str, exc_class: type) -> int:
        """Resolve the HTTP status code for a single exception class."""
        # Check explicit mapping first
        if name in cls._EXPLICIT_MAPPINGS:
            return cls._EXPLICIT_MAPPINGS[name]

        # Walk MRO to find a mapped base class
        for base in exc_class.__mro__:
            base_name = base.__name__
            if base_name in cls._EXPLICIT_MAPPINGS:
                return cls._EXPLICIT_MAPPINGS[base_name]

        # Default to 500
        return 500

    @classmethod
    def get_status_description(cls, status_code: int) -> str:
        """Return the standard HTTP reason phrase for a status code."""
        descriptions: dict[int, str] = {
            200: "OK",
            201: "Created",
            204: "No Content",
            400: "Bad Request",
            401: "Unauthorized",
            402: "Payment Required",
            403: "Forbidden",
            404: "Not Found",
            408: "Request Timeout",
            409: "Conflict",
            410: "Gone",
            412: "Precondition Failed",
            418: "I'm a Teapot",
            422: "Unprocessable Entity",
            423: "Locked",
            424: "Failed Dependency",
            429: "Too Many Requests",
            451: "Unavailable For Legal Reasons",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
            507: "Insufficient Storage",
            508: "Loop Detected",
        }
        return descriptions.get(status_code, "Unknown")

    @classmethod
    def get_unique_status_codes(cls) -> list[int]:
        """Return sorted list of unique HTTP status codes used in mappings."""
        mappings = cls.get_all_mappings()
        return sorted(set(mappings.values()))

    @classmethod
    def get_exceptions_for_status(cls, status_code: int) -> list[str]:
        """Return all exception names mapped to a given HTTP status code."""
        mappings = cls.get_all_mappings()
        return sorted(name for name, code in mappings.items() if code == status_code)


# ============================================================
# OpenAPI Generator — Builds the Full Spec
# ============================================================


class OpenAPIGenerator:
    """Builds the complete OpenAPI 3.1 specification dictionary.

    Assembles the info block, server configuration (localhost:0),
    path definitions, component schemas, security schemes, and tags
    into a single comprehensive specification that documents an API
    server that does not exist and never will.

    The specification is fully compliant with OpenAPI 3.1.0, because
    even fictional APIs deserve standards compliance. The info block
    contains contact information for Bob McFizzington (unavailable)
    and a license that is as permissive as the platform is over-engineered.
    """

    @classmethod
    def generate(cls) -> dict[str, Any]:
        """Generate the complete OpenAPI 3.1 specification.

        Returns:
            A dictionary containing the full OpenAPI spec, ready for
            JSON or YAML serialization.
        """
        spec: dict[str, Any] = {
            "openapi": "3.1.0",
            "info": cls._build_info(),
            "servers": cls._build_servers(),
            "tags": cls._build_tags(),
            "paths": cls._build_paths(),
            "components": cls._build_components(),
            "security": [{"FizzBuzzApiKey": []}, {"BearerAuth": []}],
        }
        return spec

    @classmethod
    def to_json(cls) -> str:
        """Generate the spec and serialize it as pretty-printed JSON.

        Returns:
            The OpenAPI specification as a JSON string with indent=2.
        """
        return json.dumps(cls.generate(), indent=2, default=str)

    @classmethod
    def to_yaml(cls) -> str:
        """Generate the spec and serialize it as YAML.

        Since the platform uses stdlib only, this produces a
        simplified YAML-like output using manual formatting.
        Real YAML serialization would require PyYAML, but we
        refuse to add dependencies for a feature that documents
        a server that doesn't exist.

        Returns:
            A YAML-like string representation of the spec.
        """
        spec = cls.generate()
        lines: list[str] = [
            "# Enterprise FizzBuzz Platform - OpenAPI 3.1 Specification",
            "# This file documents an API that does not exist.",
            "# Server: http://localhost:0 (This server does not exist)",
            "#",
            "# Generated by the Enterprise FizzBuzz Platform OpenAPI Generator",
            "# because even fictional APIs deserve YAML documentation.",
            "",
        ]
        cls._dict_to_yaml(spec, lines, indent=0)
        return "\n".join(lines)

    @classmethod
    def _dict_to_yaml(cls, obj: Any, lines: list[str], indent: int = 0) -> None:
        """Recursively convert a dict/list/scalar to YAML-like lines."""
        prefix = "  " * indent
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (dict, list)) and value:
                    lines.append(f"{prefix}{key}:")
                    cls._dict_to_yaml(value, lines, indent + 1)
                elif isinstance(value, str) and "\n" in value:
                    lines.append(f"{prefix}{key}: |")
                    for line in value.split("\n"):
                        lines.append(f"{prefix}  {line}")
                else:
                    yaml_val = cls._scalar_to_yaml(value)
                    lines.append(f"{prefix}{key}: {yaml_val}")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    cls._dict_to_yaml(item, lines, indent + 1)
                else:
                    lines.append(f"{prefix}- {cls._scalar_to_yaml(item)}")

    @classmethod
    def _scalar_to_yaml(cls, value: Any) -> str:
        """Convert a scalar value to its YAML representation."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            if any(c in value for c in ":#{}[]&*!|>'\",@`"):
                return f'"{value}"'
            return value
        return str(value)

    @classmethod
    def _build_info(cls) -> dict[str, Any]:
        """Build the info section of the OpenAPI spec."""
        return {
            "title": "Enterprise FizzBuzz Platform API",
            "version": "1.0.0",
            "description": (
                "The Enterprise FizzBuzz Platform REST API provides comprehensive "
                "endpoints for FizzBuzz evaluation, blockchain audit trails, ML model "
                "management, regulatory compliance, operational monitoring, and data "
                "pipeline orchestration. This API does not exist. The server at "
                "http://localhost:0 has never accepted a connection and never will. "
                "This specification exists purely to document what COULD be, if anyone "
                "were to build an HTTP server for a program that computes n % 3."
            ),
            "contact": {
                "name": "Bob McFizzington",
                "email": "bob.mcfizzington@enterprise.example.com",
                "url": "http://localhost:0/contact",
            },
            "license": {
                "name": "Enterprise FizzBuzz Public License v1.0",
                "url": "http://localhost:0/license",
            },
            "x-compliance-regimes": ["SOX", "GDPR", "HIPAA"],
            "x-bob-stress-level": 94.7,
        }

    @classmethod
    def _build_servers(cls) -> list[dict[str, Any]]:
        """Build the servers section. Port 0: this server does not exist."""
        return [
            {
                "url": "http://localhost:0",
                "description": (
                    "This server does not exist. Port 0 was chosen because "
                    "it means 'let the OS choose,' but since we never bind "
                    "a socket, the OS never chooses, and the server remains "
                    "forever in a state of quantum superposition between "
                    "existing and not existing. It does not exist."
                ),
                "variables": {
                    "environment": {
                        "default": "production",
                        "enum": ["production", "staging", "development", "fizzbuzz"],
                        "description": (
                            "The deployment environment. All environments point "
                            "to the same non-existent server on port 0."
                        ),
                    },
                },
            },
        ]

    @classmethod
    def _build_tags(cls) -> list[dict[str, Any]]:
        """Build the tags section from EndpointRegistry tag descriptions."""
        tags = []
        for tag_name, tag_desc in EndpointRegistry.get_tag_descriptions().items():
            tags.append({
                "name": tag_name,
                "description": tag_desc,
            })
        return tags

    @classmethod
    def _build_paths(cls) -> dict[str, Any]:
        """Build the paths section from all endpoint definitions."""
        paths: dict[str, Any] = {}
        all_mappings = ExceptionToHTTPMapper.get_all_mappings()

        for endpoint in EndpointRegistry.get_all_endpoints():
            if endpoint.path not in paths:
                paths[endpoint.path] = {}

            operation: dict[str, Any] = {
                "tags": [endpoint.tag],
                "summary": endpoint.summary,
                "description": endpoint.description,
                "operationId": endpoint.operation_id,
                "responses": cls._build_responses(endpoint),
            }

            if endpoint.parameters:
                operation["parameters"] = [
                    cls._build_parameter(p) for p in endpoint.parameters
                ]

            if endpoint.request_body_schema:
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": f"#/components/schemas/{endpoint.request_body_schema}",
                            },
                        },
                    },
                }

            if endpoint.deprecated:
                operation["deprecated"] = True

            paths[endpoint.path][endpoint.method.lower()] = operation

        return paths

    @classmethod
    def _build_parameter(cls, param: ParameterDefinition) -> dict[str, Any]:
        """Build an OpenAPI parameter definition."""
        p: dict[str, Any] = {
            "name": param.name,
            "in": param.location,
            "description": param.description,
            "required": param.required,
            "schema": {"type": param.param_type},
        }
        if param.enum_values:
            p["schema"]["enum"] = list(param.enum_values)
        if param.default is not None:
            p["schema"]["default"] = param.default
        if param.example is not None:
            p["example"] = param.example
        return p

    @classmethod
    def _build_responses(cls, endpoint: EndpointDefinition) -> dict[str, Any]:
        """Build the responses section for an endpoint."""
        responses: dict[str, Any] = {}

        # 200 OK (success response)
        success_resp: dict[str, Any] = {
            "description": "Successful response. The FizzBuzz operation completed without existential crisis.",
        }
        if endpoint.response_schema:
            success_resp["content"] = {
                "application/json": {
                    "schema": {
                        "$ref": f"#/components/schemas/{endpoint.response_schema}",
                    },
                },
            }
        responses["200"] = success_resp

        # Add common error responses
        error_codes = [400, 401, 403, 429, 500, 503]
        for code in error_codes:
            desc = ExceptionToHTTPMapper.get_status_description(code)
            responses[str(code)] = {
                "description": f"{desc}. See ErrorResponse schema for details.",
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": "#/components/schemas/ErrorResponse",
                        },
                    },
                },
            }

        # Add 451 for compliance endpoints
        if endpoint.tag == "Compliance":
            responses["451"] = {
                "description": (
                    "Unavailable For Legal Reasons. THE COMPLIANCE PARADOX has been triggered. "
                    "GDPR erasure rights conflict with immutable data stores."
                ),
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": "#/components/schemas/ErrorResponse",
                        },
                    },
                },
            }

        # Add 402 for evaluation endpoints (budget exceeded)
        if endpoint.tag == "Evaluation":
            responses["402"] = {
                "description": (
                    "Payment Required. The FizzBuzz evaluation budget has been exceeded. "
                    "Please purchase additional FizzBucks."
                ),
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": "#/components/schemas/ErrorResponse",
                        },
                    },
                },
            }

        return responses

    @classmethod
    def _build_components(cls) -> dict[str, Any]:
        """Build the components section with schemas and security schemes."""
        schemas = SchemaGenerator.generate_all_schemas()

        return {
            "schemas": schemas,
            "securitySchemes": {
                "FizzBuzzApiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-FizzBuzz-API-Key",
                    "description": (
                        "Enterprise FizzBuzz Platform API Key. Contact "
                        "Bob McFizzington (unavailable) for provisioning."
                    ),
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": (
                        "JWT authentication token issued by the Enterprise "
                        "FizzBuzz Token Engine. Tokens are validated using "
                        "HMAC-SHA256, which is the most security this platform "
                        "has ever seen."
                    ),
                },
            },
        }


# ============================================================
# ASCII Swagger UI — The Punchline
# ============================================================


class ASCIISwaggerUI:
    """Renders the OpenAPI specification as an ASCII Swagger UI in the terminal.

    This is the crown jewel of the OpenAPI subsystem: a fully functional
    (in the loosest possible sense) Swagger UI rendered entirely in ASCII
    art. It features:

    - Box-drawing character borders for that enterprise dashboard feel
    - Endpoint listings with method badges (GET, POST, PUT, DELETE)
    - Expandable-looking sections for each tag group
    - [Try It] buttons that honestly acknowledge there is no server
    - Parameter tables with type information
    - Response code listings with descriptions

    The [Try It] button is the punchline. When rendered, it displays a
    message explaining that the server at http://localhost:0 does not
    exist, has never existed, and cannot accept requests. The button
    is present because Swagger UIs have [Try It] buttons, and removing
    it would violate the specification of what a Swagger UI is.
    """

    @classmethod
    def render(cls, width: int = 80) -> str:
        """Render the full ASCII Swagger UI.

        Args:
            width: The character width of the rendered output.

        Returns:
            A multi-line string containing the ASCII Swagger UI.
        """
        spec = OpenAPIGenerator.generate()
        lines: list[str] = []
        inner = width - 4  # Account for border characters

        # Header
        lines.append("")
        lines.append(cls._box_top(width))
        lines.append(cls._box_line("", width))
        lines.append(cls._box_line(
            "SWAGGER UI  --  Enterprise FizzBuzz Platform API", width, center=True
        ))
        lines.append(cls._box_line(
            f"OpenAPI {spec['openapi']}  |  v{spec['info']['version']}", width, center=True
        ))
        lines.append(cls._box_line("", width))
        lines.append(cls._box_separator(width))

        # Server info
        lines.append(cls._box_line("", width))
        lines.append(cls._box_line("  Server: http://localhost:0", width))
        lines.append(cls._box_line("  Status: This server does not exist.", width))
        lines.append(cls._box_line("", width))
        lines.append(cls._box_separator(width))

        # Security
        lines.append(cls._box_line("", width))
        lines.append(cls._box_line("  AUTHORIZATION", width))
        lines.append(cls._box_line(
            "  [X-FizzBuzz-API-Key]  [Bearer JWT]", width
        ))
        lines.append(cls._box_line("", width))
        lines.append(cls._box_separator(width))

        # Endpoints by tag
        endpoints = EndpointRegistry.get_all_endpoints()
        tag_groups: dict[str, list[EndpointDefinition]] = {}
        for ep in endpoints:
            tag_groups.setdefault(ep.tag, []).append(ep)

        for tag_name, tag_endpoints in tag_groups.items():
            lines.append(cls._box_line("", width))
            tag_header = f"  [{tag_name}]"
            desc_lines = EndpointRegistry.get_tag_descriptions().get(tag_name, "")
            lines.append(cls._box_line(tag_header, width))

            # Truncate description to fit
            desc_words = desc_lines.split()
            desc_line = "    "
            for word in desc_words:
                if len(desc_line) + len(word) + 1 > inner - 2:
                    lines.append(cls._box_line(desc_line, width))
                    desc_line = "    " + word
                else:
                    desc_line += (" " if len(desc_line) > 4 else "") + word
            if desc_line.strip():
                lines.append(cls._box_line(desc_line, width))

            lines.append(cls._box_line("", width))

            for ep in tag_endpoints:
                method_badge = cls._method_badge(ep.method)
                deprecated = " [DEPRECATED]" if ep.deprecated else ""
                path_line = f"    {method_badge}  {ep.path}{deprecated}"
                lines.append(cls._box_line(path_line, width))

                summary_line = f"         {ep.summary}"
                if len(summary_line) > inner - 2:
                    summary_line = summary_line[: inner - 5] + "..."
                lines.append(cls._box_line(summary_line, width))

                # Parameters
                if ep.parameters:
                    params_str = "         Parameters: "
                    param_names = [
                        f"{p.name} ({p.location}:{p.param_type})"
                        for p in ep.parameters
                    ]
                    params_str += ", ".join(param_names)
                    if len(params_str) > inner - 2:
                        params_str = params_str[: inner - 5] + "..."
                    lines.append(cls._box_line(params_str, width))

                # [Try It] button
                lines.append(cls._box_line(
                    "         [Try It]  (server does not exist)", width
                ))
                lines.append(cls._box_line("", width))

            lines.append(cls._box_separator(width))

        # Footer with Try It explanation
        lines.append(cls._box_line("", width))
        lines.append(cls._box_line("  NOTE ON [Try It] BUTTONS:", width))
        lines.append(cls._box_line("", width))
        lines.append(cls._box_line(
            "  The [Try It] buttons above acknowledge that there is no", width
        ))
        lines.append(cls._box_line(
            "  server running at http://localhost:0 to try anything", width
        ))
        lines.append(cls._box_line(
            "  against. This is not a bug. This is a philosophical", width
        ))
        lines.append(cls._box_line(
            "  position on the nature of API documentation for a CLI", width
        ))
        lines.append(cls._box_line(
            "  tool that has never needed, and will never need, an HTTP", width
        ))
        lines.append(cls._box_line(
            "  server. The buttons exist because Swagger UIs have", width
        ))
        lines.append(cls._box_line(
            "  buttons. Removing them would be a spec violation.", width
        ))
        lines.append(cls._box_line("", width))
        lines.append(cls._box_separator(width))

        # Stats footer
        total_endpoints = len(endpoints)
        total_schemas = len(SchemaGenerator.generate_all_schemas())
        total_exceptions = len(ExceptionToHTTPMapper.get_all_mappings())
        unique_codes = len(ExceptionToHTTPMapper.get_unique_status_codes())

        lines.append(cls._box_line("", width))
        lines.append(cls._box_line("  SPECIFICATION STATISTICS:", width))
        lines.append(cls._box_line(f"    Endpoints:        {total_endpoints}", width))
        lines.append(cls._box_line(f"    Schemas:          {total_schemas}", width))
        lines.append(cls._box_line(f"    Exceptions:       {total_exceptions}", width))
        lines.append(cls._box_line(f"    HTTP Status Codes: {unique_codes}", width))
        lines.append(cls._box_line(f"    Server Exists:    No", width))
        lines.append(cls._box_line("", width))
        lines.append(cls._box_bottom(width))
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def _method_badge(cls, method: str) -> str:
        """Return a fixed-width method badge."""
        badges: dict[str, str] = {
            "GET": " GET   ",
            "POST": " POST  ",
            "PUT": " PUT   ",
            "DELETE": "DELETE ",
            "PATCH": " PATCH ",
        }
        return badges.get(method.upper(), f" {method:<6}")

    @classmethod
    def _box_top(cls, width: int) -> str:
        return "  +" + "=" * (width - 4) + "+"

    @classmethod
    def _box_bottom(cls, width: int) -> str:
        return "  +" + "=" * (width - 4) + "+"

    @classmethod
    def _box_separator(cls, width: int) -> str:
        return "  +" + "-" * (width - 4) + "+"

    @classmethod
    def _box_line(cls, text: str, width: int, center: bool = False) -> str:
        inner = width - 4
        if center:
            padded = text.center(inner)
        else:
            padded = text.ljust(inner)
        if len(padded) > inner:
            padded = padded[:inner]
        return "  |" + padded + "|"


# ============================================================
# OpenAPI Dashboard — Stats Overview
# ============================================================


class OpenAPIDashboard:
    """ASCII dashboard displaying OpenAPI specification statistics.

    Renders a compact dashboard showing:
    - Total endpoints by tag group
    - Schema count breakdown (dataclasses vs enums vs synthetic)
    - Exception-to-HTTP mapping summary
    - Server status (spoiler: does not exist)
    - Security scheme inventory

    This dashboard is for the OpenAPI spec the same way a Grafana
    dashboard is for Prometheus metrics: a pretty visualization of
    information you could have gotten from the raw data, but with
    significantly more box-drawing characters.
    """

    @classmethod
    def render(cls, width: int = 70) -> str:
        """Render the OpenAPI statistics dashboard.

        Args:
            width: Character width of the dashboard.

        Returns:
            Multi-line string containing the ASCII dashboard.
        """
        lines: list[str] = []
        inner = width - 4

        endpoints = EndpointRegistry.get_all_endpoints()
        schemas = SchemaGenerator.generate_all_schemas()
        mappings = ExceptionToHTTPMapper.get_all_mappings()
        unique_codes = ExceptionToHTTPMapper.get_unique_status_codes()

        # Header
        lines.append("")
        lines.append("  +" + "=" * inner + "+")
        lines.append("  |" + " OPENAPI SPECIFICATION DASHBOARD ".center(inner) + "|")
        lines.append("  |" + " Enterprise FizzBuzz Platform ".center(inner) + "|")
        lines.append("  +" + "=" * inner + "+")

        # Server
        lines.append("  |" + "".center(inner) + "|")
        lines.append("  |" + "  SERVER STATUS".ljust(inner) + "|")
        lines.append("  |" + "  +-----------+-----------------------------------+".ljust(inner) + "|")
        lines.append("  |" + "  | URL       | http://localhost:0                |".ljust(inner) + "|")
        lines.append("  |" + "  | Status    | DOES NOT EXIST                    |".ljust(inner) + "|")
        lines.append("  |" + "  | Port      | 0 (OS never chose one)            |".ljust(inner) + "|")
        lines.append("  |" + "  +-----------+-----------------------------------+".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")

        # Endpoints by tag
        lines.append("  +" + "-" * inner + "+")
        lines.append("  |" + "  ENDPOINTS BY TAG GROUP".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")

        tag_counts: dict[str, int] = {}
        for ep in endpoints:
            tag_counts[ep.tag] = tag_counts.get(ep.tag, 0) + 1

        for tag, count in sorted(tag_counts.items()):
            bar_len = min(count * 3, inner - 30)
            bar = "#" * bar_len
            line = f"    {tag:<15} {count:>3} {bar}"
            lines.append("  |" + line.ljust(inner) + "|")

        total_eps = sum(tag_counts.values())
        lines.append("  |" + f"    {'TOTAL':<15} {total_eps:>3}".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")

        # Schemas
        lines.append("  +" + "-" * inner + "+")
        lines.append("  |" + "  SCHEMA INVENTORY".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")

        dc_count = 0
        enum_count = 0
        synthetic_count = 0
        for name, schema in schemas.items():
            if schema.get("enum"):
                enum_count += 1
            elif name in ("BatchEvaluationRequest", "BatchEvaluationResponse",
                          "RangeEvaluationRequest", "ErrorResponse"):
                synthetic_count += 1
            else:
                dc_count += 1

        lines.append("  |" + f"    Dataclasses:    {dc_count}".ljust(inner) + "|")
        lines.append("  |" + f"    Enums:          {enum_count}".ljust(inner) + "|")
        lines.append("  |" + f"    Synthetic:      {synthetic_count}".ljust(inner) + "|")
        lines.append("  |" + f"    Total:          {len(schemas)}".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")

        # Exception mappings
        lines.append("  +" + "-" * inner + "+")
        lines.append("  |" + "  EXCEPTION -> HTTP STATUS MAPPING".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")
        lines.append("  |" + f"    Total Exceptions Mapped: {len(mappings)}".ljust(inner) + "|")
        lines.append("  |" + f"    Unique HTTP Status Codes: {len(unique_codes)}".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")

        # Show top status codes by exception count
        code_counts: dict[int, int] = {}
        for code in mappings.values():
            code_counts[code] = code_counts.get(code, 0) + 1

        for code in sorted(code_counts.keys()):
            count = code_counts[code]
            desc = ExceptionToHTTPMapper.get_status_description(code)
            line = f"    {code} {desc:<30} {count:>3} exception(s)"
            lines.append("  |" + line.ljust(inner) + "|")

        lines.append("  |" + "".center(inner) + "|")

        # Security
        lines.append("  +" + "-" * inner + "+")
        lines.append("  |" + "  SECURITY SCHEMES".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")
        lines.append("  |" + "    [1] X-FizzBuzz-API-Key (apiKey in header)".ljust(inner) + "|")
        lines.append("  |" + "    [2] Bearer JWT (HTTP Bearer)".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")
        lines.append("  |" + "    Contact Bob McFizzington for API keys.".ljust(inner) + "|")
        lines.append("  |" + "    (He is unavailable.)".ljust(inner) + "|")
        lines.append("  |" + "".center(inner) + "|")

        # Footer
        lines.append("  +" + "=" * inner + "+")
        lines.append("")

        return "\n".join(lines)

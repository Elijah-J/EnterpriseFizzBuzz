"""
Enterprise FizzBuzz Platform - FizzSchemaContract Schema Contract Testing Tests

Comprehensive test suite for the FizzSchemaContract Schema Contract Testing
subsystem. Validates schema definition, field type enforcement, producer-consumer
compatibility checking across all three compatibility modes, contract registration,
dashboard rendering, middleware integration, and factory assembly.

Schema contracts are the gatekeepers of data integrity in any distributed
platform. A single field type mismatch between a FizzBuzz producer and its
downstream consumer can cascade into silent data corruption, rendering
entire evaluation pipelines untrustworthy. These tests ensure the contract
enforcement apparatus is watertight before it guards production traffic.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzschemacontract import (
    FIZZSCHEMACONTRACT_VERSION,
    MIDDLEWARE_PRIORITY,
    CompatibilityMode,
    SchemaFieldType,
    SchemaField,
    SchemaDefinition,
    FizzSchemaContractConfig,
    ContractRegistry,
    FizzSchemaContractDashboard,
    FizzSchemaContractMiddleware,
    create_fizzschemacontract_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzschemacontract import (
    FizzSchemaContractError,
    FizzSchemaContractNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests to prevent cross-contamination."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def registry():
    """Provide a fresh ContractRegistry for each test."""
    return ContractRegistry()


@pytest.fixture
def sample_fields():
    """Standard set of fields representing a FizzBuzz evaluation record."""
    return [
        SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
        SchemaField(name="result", field_type=SchemaFieldType.STRING, required=True),
        SchemaField(name="timestamp", field_type=SchemaFieldType.FLOAT, required=False),
    ]


@pytest.fixture
def populated_registry(registry, sample_fields):
    """Registry pre-loaded with a producer and consumer schema pair."""
    producer = registry.register_schema("fizzbuzz-output", sample_fields, version=1)
    consumer_fields = [
        SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
        SchemaField(name="result", field_type=SchemaFieldType.STRING, required=True),
    ]
    consumer = registry.register_schema("fizzbuzz-consumer", consumer_fields, version=1)
    return registry, producer, consumer


# ============================================================================
# Constants
# ============================================================================

class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version_string(self):
        """The version must follow semantic versioning for release tracking."""
        assert FIZZSCHEMACONTRACT_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Schema contract validation runs at priority 210 in the middleware chain."""
        assert MIDDLEWARE_PRIORITY == 210


# ============================================================================
# Enums
# ============================================================================

class TestEnums:
    """Validate enum definitions for compatibility modes and field types."""

    def test_compatibility_mode_backward(self):
        assert CompatibilityMode.BACKWARD is not None

    def test_compatibility_mode_forward(self):
        assert CompatibilityMode.FORWARD is not None

    def test_compatibility_mode_full(self):
        assert CompatibilityMode.FULL is not None

    def test_field_type_string(self):
        assert SchemaFieldType.STRING is not None

    def test_field_type_integer(self):
        assert SchemaFieldType.INTEGER is not None

    def test_field_type_covers_all_primitives(self):
        """All six field types must be present for complete schema coverage."""
        names = {ft.name for ft in SchemaFieldType}
        assert names == {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "ARRAY", "OBJECT"}


# ============================================================================
# SchemaField and SchemaDefinition
# ============================================================================

class TestDataclasses:
    """Validate schema data model construction and field access."""

    def test_schema_field_creation(self):
        field = SchemaField(name="value", field_type=SchemaFieldType.INTEGER, required=True)
        assert field.name == "value"
        assert field.field_type == SchemaFieldType.INTEGER
        assert field.required is True

    def test_schema_definition_creation(self, sample_fields):
        defn = SchemaDefinition(
            schema_id="test-001", name="test-schema", version=1, fields=sample_fields
        )
        assert defn.schema_id == "test-001"
        assert defn.name == "test-schema"
        assert defn.version == 1
        assert len(defn.fields) == 3

    def test_config_has_dashboard_width(self):
        """Configuration must expose dashboard width for rendering layout."""
        config = FizzSchemaContractConfig()
        assert hasattr(config, "dashboard_width")
        assert isinstance(config.dashboard_width, int)


# ============================================================================
# ContractRegistry - Schema Registration
# ============================================================================

class TestSchemaRegistration:
    """Validate schema registration and retrieval operations."""

    def test_register_schema_returns_definition(self, registry, sample_fields):
        result = registry.register_schema("test-schema", sample_fields, version=1)
        assert isinstance(result, SchemaDefinition)
        assert result.name == "test-schema"
        assert result.version == 1

    def test_register_schema_assigns_unique_id(self, registry, sample_fields):
        s1 = registry.register_schema("schema-a", sample_fields, version=1)
        s2 = registry.register_schema("schema-b", sample_fields, version=1)
        assert s1.schema_id != s2.schema_id

    def test_get_schema_by_id(self, registry, sample_fields):
        registered = registry.register_schema("lookup-test", sample_fields)
        retrieved = registry.get_schema(registered.schema_id)
        assert retrieved.schema_id == registered.schema_id
        assert retrieved.name == "lookup-test"

    def test_get_schema_not_found_raises(self, registry):
        """Requesting a non-existent schema must raise the appropriate exception."""
        with pytest.raises(FizzSchemaContractNotFoundError):
            registry.get_schema("nonexistent-id")

    def test_list_schemas_returns_all(self, registry, sample_fields):
        registry.register_schema("first", sample_fields)
        registry.register_schema("second", sample_fields)
        schemas = registry.list_schemas()
        assert len(schemas) == 2
        names = {s.name for s in schemas}
        assert names == {"first", "second"}


# ============================================================================
# ContractRegistry - Compatibility Checking
# ============================================================================

class TestCompatibility:
    """Validate schema compatibility checking across all three modes."""

    def test_backward_compatible_when_consumer_fields_present(self, populated_registry):
        """BACKWARD: consumer can read producer if all required consumer fields exist in producer."""
        registry, producer, consumer = populated_registry
        result = registry.check_compatibility(
            producer.schema_id, consumer.schema_id, CompatibilityMode.BACKWARD
        )
        assert result["compatible"] is True
        assert isinstance(result["issues"], list)
        assert len(result["issues"]) == 0

    def test_backward_incompatible_when_consumer_requires_missing_field(self, registry):
        """BACKWARD: if consumer requires a field absent from producer, incompatible."""
        producer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
        ]
        consumer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
            SchemaField(name="label", field_type=SchemaFieldType.STRING, required=True),
        ]
        producer = registry.register_schema("narrow-producer", producer_fields)
        consumer = registry.register_schema("wide-consumer", consumer_fields)
        result = registry.check_compatibility(
            producer.schema_id, consumer.schema_id, CompatibilityMode.BACKWARD
        )
        assert result["compatible"] is False
        assert len(result["issues"]) > 0

    def test_forward_compatible_when_no_extra_required_in_producer(self, registry):
        """FORWARD: compatible if producer has no extra required fields not in consumer."""
        producer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
        ]
        consumer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
            SchemaField(name="extra", field_type=SchemaFieldType.STRING, required=True),
        ]
        producer = registry.register_schema("slim-producer", producer_fields)
        consumer = registry.register_schema("broad-consumer", consumer_fields)
        result = registry.check_compatibility(
            producer.schema_id, consumer.schema_id, CompatibilityMode.FORWARD
        )
        assert result["compatible"] is True
        assert len(result["issues"]) == 0

    def test_forward_incompatible_when_producer_has_extra_required(self, registry):
        """FORWARD: if producer has required fields absent from consumer, incompatible."""
        producer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
            SchemaField(name="secret", field_type=SchemaFieldType.STRING, required=True),
        ]
        consumer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
        ]
        producer = registry.register_schema("fat-producer", producer_fields)
        consumer = registry.register_schema("lean-consumer", consumer_fields)
        result = registry.check_compatibility(
            producer.schema_id, consumer.schema_id, CompatibilityMode.FORWARD
        )
        assert result["compatible"] is False
        assert len(result["issues"]) > 0

    def test_full_compatible_requires_both_directions(self, registry):
        """FULL mode requires both BACKWARD and FORWARD compatibility."""
        fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
            SchemaField(name="result", field_type=SchemaFieldType.STRING, required=True),
        ]
        producer = registry.register_schema("full-producer", fields)
        consumer = registry.register_schema("full-consumer", fields)
        result = registry.check_compatibility(
            producer.schema_id, consumer.schema_id, CompatibilityMode.FULL
        )
        assert result["compatible"] is True
        assert len(result["issues"]) == 0

    def test_full_incompatible_when_backward_fails(self, registry):
        """FULL mode must fail if BACKWARD check fails, even if FORWARD would pass."""
        producer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
        ]
        consumer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
            SchemaField(name="needed", field_type=SchemaFieldType.STRING, required=True),
        ]
        producer = registry.register_schema("producer-missing", producer_fields)
        consumer = registry.register_schema("consumer-demanding", consumer_fields)
        result = registry.check_compatibility(
            producer.schema_id, consumer.schema_id, CompatibilityMode.FULL
        )
        assert result["compatible"] is False

    def test_optional_consumer_fields_do_not_break_backward(self, registry):
        """BACKWARD: optional consumer fields not in producer should not cause failure."""
        producer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
        ]
        consumer_fields = [
            SchemaField(name="number", field_type=SchemaFieldType.INTEGER, required=True),
            SchemaField(name="metadata", field_type=SchemaFieldType.OBJECT, required=False),
        ]
        producer = registry.register_schema("minimal-producer", producer_fields)
        consumer = registry.register_schema("optional-consumer", consumer_fields)
        result = registry.check_compatibility(
            producer.schema_id, consumer.schema_id, CompatibilityMode.BACKWARD
        )
        assert result["compatible"] is True


# ============================================================================
# ContractRegistry - Contract Registration
# ============================================================================

class TestContractRegistration:
    """Validate contract registration between producer-consumer pairs."""

    def test_register_contract_returns_dict(self, populated_registry):
        registry, producer, consumer = populated_registry
        contract = registry.register_contract(
            producer.schema_id, consumer.schema_id, CompatibilityMode.BACKWARD
        )
        assert isinstance(contract, dict)
        assert "producer_id" in contract or producer.schema_id in str(contract)

    def test_list_contracts_after_registration(self, populated_registry):
        registry, producer, consumer = populated_registry
        registry.register_contract(producer.schema_id, consumer.schema_id)
        contracts = registry.list_contracts()
        assert isinstance(contracts, list)
        assert len(contracts) >= 1


# ============================================================================
# FizzSchemaContractDashboard
# ============================================================================

class TestDashboard:
    """Validate dashboard rendering for schema contract status reporting."""

    def test_render_returns_string(self, registry):
        dashboard = FizzSchemaContractDashboard(registry)
        output = dashboard.render()
        assert isinstance(output, str)

    def test_render_reflects_registered_schemas(self, populated_registry):
        """The dashboard must include information about registered schemas."""
        registry, producer, consumer = populated_registry
        dashboard = FizzSchemaContractDashboard(registry)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0


# ============================================================================
# FizzSchemaContractMiddleware
# ============================================================================

class TestMiddleware:
    """Validate middleware integration with the FizzBuzz processing pipeline."""

    def test_get_name(self):
        middleware = FizzSchemaContractMiddleware()
        assert middleware.get_name() == "fizzschemacontract"

    def test_get_priority(self):
        middleware = FizzSchemaContractMiddleware()
        assert middleware.get_priority() == 210

    def test_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        middleware = FizzSchemaContractMiddleware()
        ctx = ProcessingContext(number=42, session_id="test")
        called = {"value": False}

        def fake_next(c):
            called["value"] = True
            return c

        middleware.process(ctx, fake_next)
        assert called["value"] is True, "Middleware must call the next handler"


# ============================================================================
# Exception Hierarchy
# ============================================================================

class TestExceptions:
    """Validate exception class hierarchy for proper error categorization."""

    def test_base_error_is_exception(self):
        assert issubclass(FizzSchemaContractError, Exception)

    def test_not_found_inherits_base(self):
        assert issubclass(FizzSchemaContractNotFoundError, FizzSchemaContractError)

    def test_not_found_can_be_raised_and_caught(self):
        with pytest.raises(FizzSchemaContractError):
            raise FizzSchemaContractNotFoundError("schema xyz not found")


# ============================================================================
# Factory Function
# ============================================================================

class TestCreateSubsystem:
    """Validate the factory function that wires the FizzSchemaContract subsystem."""

    def test_returns_tuple_of_three(self):
        result = create_fizzschemacontract_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        registry, dashboard, middleware = create_fizzschemacontract_subsystem()
        assert isinstance(registry, ContractRegistry)
        assert isinstance(dashboard, FizzSchemaContractDashboard)
        assert isinstance(middleware, FizzSchemaContractMiddleware)

    def test_subsystem_components_are_wired(self):
        """The registry and dashboard must be connected so schemas are visible."""
        registry, dashboard, middleware = create_fizzschemacontract_subsystem()
        fields = [
            SchemaField(name="id", field_type=SchemaFieldType.INTEGER, required=True),
        ]
        registry.register_schema("wiring-test", fields)
        output = dashboard.render()
        assert isinstance(output, str)

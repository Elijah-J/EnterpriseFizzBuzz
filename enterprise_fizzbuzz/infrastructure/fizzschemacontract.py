"""Enterprise FizzBuzz Platform - FizzSchemaContract: Schema Contract Testing"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzschemacontract import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzschemacontract")
EVENT_CONTRACT = EventType.register("FIZZSCHEMACONTRACT_CHECKED")
FIZZSCHEMACONTRACT_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 210


class CompatibilityMode(Enum):
    BACKWARD = "backward"
    FORWARD = "forward"
    FULL = "full"


class SchemaFieldType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class SchemaField:
    """A single field within a schema definition."""
    name: str = ""
    field_type: SchemaFieldType = SchemaFieldType.STRING
    required: bool = True


@dataclass
class SchemaDefinition:
    """A versioned schema with a set of typed fields."""
    schema_id: str = ""
    name: str = ""
    version: int = 1
    fields: List[SchemaField] = field(default_factory=list)


@dataclass
class FizzSchemaContractConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


@dataclass
class Contract:
    """A registered compatibility contract between a producer and consumer schema."""
    contract_id: str = ""
    producer_id: str = ""
    consumer_id: str = ""
    mode: CompatibilityMode = CompatibilityMode.BACKWARD


class ContractRegistry:
    """Registry for schema definitions and compatibility contracts between
    producer and consumer schemas in the Enterprise FizzBuzz data pipeline."""

    def __init__(self) -> None:
        self._schemas: OrderedDict[str, SchemaDefinition] = OrderedDict()
        self._contracts: List[Contract] = []

    def register_schema(self, name: str, fields: List[SchemaField],
                        version: int = 1) -> SchemaDefinition:
        """Register a new schema definition with typed fields."""
        schema_id = f"schema-{uuid.uuid4().hex[:8]}"
        schema = SchemaDefinition(
            schema_id=schema_id,
            name=name,
            version=version,
            fields=list(fields),
        )
        self._schemas[schema_id] = schema
        logger.debug("Registered schema %s v%d with %d fields", name, version, len(fields))
        return schema

    def get_schema(self, schema_id: str) -> SchemaDefinition:
        """Retrieve a schema by its ID."""
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise FizzSchemaContractNotFoundError(schema_id)
        return schema

    def list_schemas(self) -> List[SchemaDefinition]:
        """Return all registered schemas."""
        return list(self._schemas.values())

    def register_contract(self, producer_id: str, consumer_id: str,
                          mode: CompatibilityMode = CompatibilityMode.BACKWARD) -> dict:
        """Register a compatibility contract between producer and consumer schemas."""
        # Validate both schemas exist
        self.get_schema(producer_id)
        self.get_schema(consumer_id)
        contract = Contract(
            contract_id=f"contract-{uuid.uuid4().hex[:8]}",
            producer_id=producer_id,
            consumer_id=consumer_id,
            mode=mode,
        )
        self._contracts.append(contract)
        result = self.check_compatibility(producer_id, consumer_id, mode)
        logger.debug("Registered contract %s: %s -> %s (%s) compatible=%s",
                      contract.contract_id, producer_id, consumer_id,
                      mode.value, result["compatible"])
        return {
            "contract_id": contract.contract_id,
            "producer_id": producer_id,
            "consumer_id": consumer_id,
            "mode": mode.value,
            "compatible": result["compatible"],
            "issues": result["issues"],
        }

    def check_compatibility(self, producer_id: str, consumer_id: str,
                            mode: CompatibilityMode = CompatibilityMode.BACKWARD) -> dict:
        """Check schema compatibility between producer and consumer.

        BACKWARD: All required fields in consumer must exist in producer
        (consumer can read data produced by producer).

        FORWARD: Producer has no required fields absent from consumer
        (future consumers can read current producer data).

        FULL: Both backward and forward compatibility must hold.
        """
        producer = self.get_schema(producer_id)
        consumer = self.get_schema(consumer_id)

        producer_fields = {f.name: f for f in producer.fields}
        consumer_fields = {f.name: f for f in consumer.fields}

        issues: List[str] = []

        if mode in (CompatibilityMode.BACKWARD, CompatibilityMode.FULL):
            # All required consumer fields must exist in producer
            for cf in consumer.fields:
                if cf.required and cf.name not in producer_fields:
                    issues.append(
                        f"BACKWARD: Required consumer field '{cf.name}' missing from producer"
                    )
                elif cf.required and cf.name in producer_fields:
                    pf = producer_fields[cf.name]
                    if pf.field_type != cf.field_type:
                        issues.append(
                            f"BACKWARD: Type mismatch for '{cf.name}': "
                            f"producer={pf.field_type.value}, consumer={cf.field_type.value}"
                        )

        if mode in (CompatibilityMode.FORWARD, CompatibilityMode.FULL):
            # Producer must not have required fields absent from consumer
            for pf in producer.fields:
                if pf.required and pf.name not in consumer_fields:
                    issues.append(
                        f"FORWARD: Required producer field '{pf.name}' missing from consumer"
                    )
                elif pf.required and pf.name in consumer_fields:
                    cf = consumer_fields[pf.name]
                    if pf.field_type != cf.field_type:
                        issues.append(
                            f"FORWARD: Type mismatch for '{pf.name}': "
                            f"producer={pf.field_type.value}, consumer={cf.field_type.value}"
                        )

        return {"compatible": len(issues) == 0, "issues": issues}

    def list_contracts(self) -> List[dict]:
        """Return all registered contracts as dicts."""
        return [
            {
                "contract_id": c.contract_id,
                "producer_id": c.producer_id,
                "consumer_id": c.consumer_id,
                "mode": c.mode.value,
            }
            for c in self._contracts
        ]


class FizzSchemaContractDashboard:
    def __init__(self, registry: Optional[ContractRegistry] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._registry = registry
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzSchemaContract Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZSCHEMACONTRACT_VERSION}"]
        if self._registry:
            schemas = self._registry.list_schemas()
            contracts = self._registry.list_contracts()
            lines.append(f"  Schemas: {len(schemas)}")
            lines.append(f"  Contracts: {len(contracts)}")
            lines.append("-" * self._width)
            for s in schemas[:10]:
                lines.append(f"  {s.name:<25} v{s.version}  {len(s.fields)} fields")
        return "\n".join(lines)


class FizzSchemaContractMiddleware(IMiddleware):
    def __init__(self, registry: Optional[ContractRegistry] = None,
                 dashboard: Optional[FizzSchemaContractDashboard] = None) -> None:
        self._registry = registry
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzschemacontract"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzschemacontract_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[ContractRegistry, FizzSchemaContractDashboard, FizzSchemaContractMiddleware]:
    """Factory function that creates and wires the FizzSchemaContract subsystem."""
    registry = ContractRegistry()
    # Register representative schemas for the FizzBuzz pipeline
    producer = registry.register_schema("fizzbuzz_result", [
        SchemaField("number", SchemaFieldType.INTEGER, required=True),
        SchemaField("classification", SchemaFieldType.STRING, required=True),
        SchemaField("timestamp", SchemaFieldType.STRING, required=False),
    ])
    consumer = registry.register_schema("fizzbuzz_consumer", [
        SchemaField("number", SchemaFieldType.INTEGER, required=True),
        SchemaField("classification", SchemaFieldType.STRING, required=True),
    ])
    registry.register_contract(producer.schema_id, consumer.schema_id, CompatibilityMode.BACKWARD)

    dashboard = FizzSchemaContractDashboard(registry, dashboard_width)
    middleware = FizzSchemaContractMiddleware(registry, dashboard)
    logger.info("FizzSchemaContract initialized: %d schemas, %d contracts",
                len(registry.list_schemas()), len(registry.list_contracts()))
    return registry, dashboard, middleware

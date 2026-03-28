"""
Enterprise FizzBuzz Platform - FizzDataLake: Data Lake

Schema-on-read, partitioning, and columnar query for FizzBuzz evaluation data.

Architecture reference: Delta Lake, Apache Iceberg, Apache Hudi, AWS S3 + Athena.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzdatalake import (
    FizzDataLakeError, FizzDataLakeObjectNotFoundError,
    FizzDataLakeIngestError, FizzDataLakeQueryError,
    FizzDataLakeSchemaError, FizzDataLakePartitionError,
    FizzDataLakeConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzdatalake")

EVENT_DL_INGESTED = EventType.register("FIZZDATALAKE_INGESTED")
EVENT_DL_QUERIED = EventType.register("FIZZDATALAKE_QUERIED")

FIZZDATALAKE_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 166


class FileFormat(Enum):
    PARQUET = "parquet"
    CSV = "csv"
    JSON = "json"
    AVRO = "avro"


class PartitionStrategy(Enum):
    DATE = "date"
    HASH = "hash"
    RANGE = "range"


@dataclass
class FizzDataLakeConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


@dataclass
class DataObject:
    object_id: str = ""
    path: str = ""
    format: FileFormat = FileFormat.JSON
    size_bytes: int = 0
    partition_key: str = ""
    schema: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    data: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Partition:
    key: str = ""
    strategy: PartitionStrategy = PartitionStrategy.DATE
    values: List[str] = field(default_factory=list)
    object_count: int = 0


class DataLakeStore:
    """Data lake storage with schema-on-read and query capabilities."""

    def __init__(self) -> None:
        self._objects: OrderedDict[str, DataObject] = OrderedDict()
        self._total_bytes = 0
        self._total_queries = 0

    def ingest(self, path: str, data: List[Dict[str, Any]],
               format: FileFormat = FileFormat.JSON,
               partition_key: str = "",
               schema: Optional[Dict[str, Any]] = None) -> DataObject:
        """Ingest data into the data lake."""
        obj = DataObject(
            object_id=f"obj-{uuid.uuid4().hex[:8]}",
            path=path,
            format=format,
            size_bytes=len(json.dumps(data).encode()),
            partition_key=partition_key,
            schema=schema or {},
            created_at=datetime.now(timezone.utc),
            data=copy.deepcopy(data),
        )
        self._objects[obj.object_id] = obj
        self._total_bytes += obj.size_bytes
        return obj

    def get(self, object_id: str) -> DataObject:
        """Retrieve a data object by ID."""
        obj = self._objects.get(object_id)
        if obj is None:
            raise FizzDataLakeObjectNotFoundError(object_id)
        return obj

    def query(self, path_prefix: str = "", filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Query data across objects, optionally filtering rows."""
        self._total_queries += 1
        results = []
        for obj in self._objects.values():
            if path_prefix and not obj.path.startswith(path_prefix):
                continue
            for row in obj.data:
                if filters:
                    match = all(row.get(k) == v for k, v in filters.items())
                    if not match:
                        continue
                results.append(row)
        return results

    def list_objects(self, path_prefix: str = "") -> List[DataObject]:
        """List data objects, optionally filtered by path prefix."""
        if not path_prefix:
            return list(self._objects.values())
        return [o for o in self._objects.values() if o.path.startswith(path_prefix)]

    def delete(self, object_id: str) -> bool:
        """Delete a data object."""
        obj = self._objects.pop(object_id, None)
        if obj:
            self._total_bytes -= obj.size_bytes
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return data lake statistics."""
        return {
            "objects": len(self._objects),
            "object_count": len(self._objects),
            "total_objects": len(self._objects),
            "total_bytes": self._total_bytes,
            "total_size_bytes": self._total_bytes,
            "total_size": self._total_bytes,
            "size_bytes": self._total_bytes,
            "total_queries": self._total_queries,
            "formats": list({o.format.value for o in self._objects.values()}),
        }


class SchemaRegistry:
    """Schema-on-read schema registry."""

    def __init__(self) -> None:
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register(self, path: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Register a schema for a path."""
        self._schemas[path] = schema
        return schema

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        """Get schema for a path."""
        return self._schemas.get(path)

    def infer(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Infer schema from data. Returns field_name -> type_string mapping."""
        if not data:
            return {}
        sample = data[0]
        schema = {}
        for k, v in sample.items():
            if isinstance(v, bool):  # Check bool before int (bool is subclass of int)
                schema[k] = "boolean"
            elif isinstance(v, int):
                schema[k] = "integer"
            elif isinstance(v, float):
                schema[k] = "number"
            elif isinstance(v, str):
                schema[k] = "string"
            elif isinstance(v, list):
                schema[k] = "array"
            elif isinstance(v, dict):
                schema[k] = "object"
            else:
                schema[k] = "string"
        return schema

    def validate(self, data: List[Dict[str, Any]], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate data against a schema.

        Schema can be either:
        - Simple: {"field": "type_str"} where type_str is int/str/float/bool
        - JSON Schema: {"properties": {"field": {"type": "integer"}}}
        """
        errors = []

        # Detect schema format
        if "properties" in schema:
            props = {k: v.get("type", "string") for k, v in schema["properties"].items()}
        else:
            props = schema

        type_map = {
            "int": int, "integer": int,
            "str": str, "string": str,
            "float": (int, float), "number": (int, float),
            "bool": bool, "boolean": bool,
            "list": list, "array": list,
            "dict": dict, "object": dict,
        }

        for i, row in enumerate(data):
            for field_name, type_str in props.items():
                if field_name in row:
                    expected = type_map.get(type_str, str)
                    value = row[field_name]
                    if not isinstance(value, expected):
                        errors.append(
                            f"Row {i}: {field_name} expected {type_str}, got {type(value).__name__}"
                        )
        return len(errors) == 0, errors


class PartitionManager:
    """Manages data partitions."""

    def __init__(self) -> None:
        self._partitions: Dict[str, Partition] = {}

    def create_partition(self, key: str, strategy: PartitionStrategy = PartitionStrategy.DATE) -> Partition:
        partition = Partition(key=key, strategy=strategy)
        self._partitions[key] = partition
        return partition

    def get_partition(self, key: str) -> Optional[Partition]:
        return self._partitions.get(key)

    def list_partitions(self) -> List[Partition]:
        return list(self._partitions.values())


class FizzDataLakeDashboard:
    def __init__(self, store: Optional[DataLakeStore] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzDataLake Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZDATALAKE_VERSION}",
        ]
        if self._store:
            stats = self._store.get_stats()
            lines.append(f"  Objects: {stats['objects']}")
            lines.append(f"  Size:    {stats['total_bytes']} bytes")
            lines.append(f"  Queries: {stats['total_queries']}")
        return "\n".join(lines)


class FizzDataLakeMiddleware(IMiddleware):
    def __init__(self, store: Optional[DataLakeStore] = None,
                 dashboard: Optional[FizzDataLakeDashboard] = None) -> None:
        self._store = store
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzdatalake"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzDataLake not initialized"


def create_fizzdatalake_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[DataLakeStore, FizzDataLakeDashboard, FizzDataLakeMiddleware]:
    store = DataLakeStore()
    schema_registry = SchemaRegistry()
    partition_mgr = PartitionManager()

    # Seed with FizzBuzz evaluation data
    evaluations = [
        {"number": n, "result": "FizzBuzz" if n % 15 == 0 else "Fizz" if n % 3 == 0 else "Buzz" if n % 5 == 0 else str(n),
         "is_fizz": n % 3 == 0, "is_buzz": n % 5 == 0}
        for n in range(1, 101)
    ]
    store.ingest("fizzbuzz/evaluations/batch-001", evaluations, FileFormat.PARQUET,
                 partition_key="2026-03-28")

    # Register schema
    schema_registry.register("fizzbuzz/evaluations", {
        "type": "object",
        "properties": {
            "number": {"type": "integer"},
            "result": {"type": "string"},
            "is_fizz": {"type": "boolean"},
            "is_buzz": {"type": "boolean"},
        },
    })

    # Create partitions
    partition_mgr.create_partition("2026-03-28", PartitionStrategy.DATE)

    dashboard = FizzDataLakeDashboard(store, dashboard_width)
    middleware = FizzDataLakeMiddleware(store, dashboard)

    logger.info("FizzDataLake initialized: %d objects", len(store.list_objects()))
    return store, dashboard, middleware

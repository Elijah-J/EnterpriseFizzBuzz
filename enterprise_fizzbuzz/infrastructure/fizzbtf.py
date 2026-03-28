"""
Enterprise FizzBuzz Platform - FizzBTF: BPF Type Format for Runtime Type Introspection

A BPF Type Format (BTF) registry that provides runtime type introspection
for the Enterprise FizzBuzz Platform's kernel-bypass and observability
subsystems.  BTF encodes type information (integers, pointers, arrays,
structs, unions, enums, functions, typedefs) in a compact format that
enables tools to interpret raw memory without access to source code or
debug symbols.

The FizzBuzz evaluation pipeline operates on typed data structures at every
layer: ProcessingContext, FizzBuzzResult, CacheEntry, BlockchainBlock,
PaxosProposal, and hundreds of others.  When the FizzBPF observability
probes capture raw memory snapshots from these structures, they need type
metadata to decode the bytes into meaningful fields.  FizzBTF provides
that metadata through a centralized type registry that mirrors the kernel
BTF subsystem.

The registry supports nine BTF kinds matching the Linux kernel BTF
specification: INT, PTR, ARRAY, STRUCT, UNION, ENUM, FUNC, FUNC_PROTO,
and TYPEDEF.  Each registered type receives a unique ID and can be
resolved by name for cross-referencing.

Architecture references: Linux BTF (https://www.kernel.org/doc/html/latest/bpf/btf.html),
libbpf BTF API, pahole
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzbtf import (
    BTFDuplicateTypeError,
    BTFTypeNameNotFoundError,
    BTFTypeNotFoundError,
    BTFValidationError,
    FizzBTFError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzbtf")

EVENT_BTF = EventType.register("FIZZBTF_TYPE_REGISTERED")

# ============================================================
# Constants
# ============================================================

FIZZBTF_VERSION = "1.0.0"
"""Current version of the FizzBTF subsystem."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 236
"""Middleware pipeline priority for FizzBTF."""


# ============================================================
# Enums
# ============================================================


class BTFKind(Enum):
    """BTF type kinds matching the Linux kernel BTF specification.

    Each kind represents a distinct category of type information that
    the BTF registry can encode and resolve at runtime.
    """
    INT = "int"
    PTR = "ptr"
    ARRAY = "array"
    STRUCT = "struct"
    UNION = "union"
    ENUM = "enum"
    FUNC = "func"
    FUNC_PROTO = "func_proto"
    TYPEDEF = "typedef"


# ============================================================
# Data classes
# ============================================================


@dataclass
class BTFType:
    """A single type definition in the BTF registry.

    Each type has a unique ID, a human-readable name, a kind that
    determines how the type is interpreted, a size in bytes, and an
    optional list of field descriptors for composite types.
    """
    type_id: str = ""
    name: str = ""
    kind: BTFKind = BTFKind.INT
    size: int = 0
    fields: List[dict] = field(default_factory=list)


# ============================================================
# BTF Registry
# ============================================================


class BTFRegistry:
    """Centralized registry for BPF Type Format metadata.

    The registry stores type definitions indexed by both unique ID and
    name, enabling fast lookups from observability probes that need to
    decode raw memory snapshots.
    """

    def __init__(self) -> None:
        self._types: OrderedDict[str, BTFType] = OrderedDict()
        self._name_index: Dict[str, str] = {}  # name -> type_id

    def register_type(self, name: str, kind: BTFKind, size: int,
                      fields: Optional[List[dict]] = None) -> BTFType:
        """Register a new type in the BTF registry.

        Args:
            name: Human-readable type name.
            kind: The BTF kind category.
            size: Type size in bytes.
            fields: Optional list of field descriptors for composite types.

        Returns:
            The newly registered BTFType with a unique ID.

        Raises:
            BTFValidationError: If the type definition is invalid.
            BTFDuplicateTypeError: If a type with this name already exists.
        """
        if not name:
            raise BTFValidationError("Type name must not be empty")
        if size < 0:
            raise BTFValidationError(f"Type size must be non-negative, got {size}")
        if name in self._name_index:
            raise BTFDuplicateTypeError(name)

        type_id = f"btf-{uuid.uuid4().hex[:8]}"
        btf_type = BTFType(
            type_id=type_id,
            name=name,
            kind=kind,
            size=size,
            fields=fields or [],
        )
        self._types[type_id] = btf_type
        self._name_index[name] = type_id
        logger.debug("Registered BTF type '%s' (kind=%s, size=%d, id=%s)",
                      name, kind.value, size, type_id)
        return btf_type

    def get_type(self, type_id: str) -> BTFType:
        """Retrieve a type by its unique identifier.

        Raises:
            BTFTypeNotFoundError: If the type ID is not found.
        """
        btf_type = self._types.get(type_id)
        if btf_type is None:
            raise BTFTypeNotFoundError(type_id)
        return btf_type

    def list_types(self) -> List[BTFType]:
        """Return all registered types."""
        return list(self._types.values())

    def resolve(self, name: str) -> BTFType:
        """Resolve a type by name.

        Args:
            name: The type name to look up.

        Returns:
            The matching BTFType.

        Raises:
            BTFTypeNameNotFoundError: If no type with this name exists.
        """
        type_id = self._name_index.get(name)
        if type_id is None:
            raise BTFTypeNameNotFoundError(name)
        return self._types[type_id]

    def dump(self) -> str:
        """Dump the entire registry contents as a formatted string.

        Returns:
            A multi-line string representation of all registered types.
        """
        lines = [f"BTF Registry ({len(self._types)} types):"]
        for btf_type in self._types.values():
            field_str = ""
            if btf_type.fields:
                field_names = [f.get("name", "?") for f in btf_type.fields]
                field_str = f" fields=[{', '.join(field_names)}]"
            lines.append(
                f"  [{btf_type.type_id}] {btf_type.name} "
                f"kind={btf_type.kind.value} size={btf_type.size}{field_str}"
            )
        return "\n".join(lines)


# ============================================================
# Dashboard
# ============================================================


class FizzBTFDashboard:
    """ASCII dashboard for monitoring the BTF registry."""

    def __init__(self, registry: Optional[BTFRegistry] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._registry = registry
        self._width = width

    def render(self) -> str:
        """Render the BTF monitoring dashboard."""
        lines = [
            "=" * self._width,
            "FizzBTF Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZBTF_VERSION}",
        ]
        if self._registry:
            types = self._registry.list_types()
            lines.append(f"  Registered types: {len(types)}")
            kind_counts: Dict[str, int] = {}
            for t in types:
                kind_counts[t.kind.value] = kind_counts.get(t.kind.value, 0) + 1
            if kind_counts:
                lines.append("-" * self._width)
                lines.append("  Kind Distribution:")
                for kind, count in sorted(kind_counts.items()):
                    lines.append(f"    {kind:<12} {count}")
            lines.append("-" * self._width)
            for t in types[:10]:
                lines.append(f"  {t.name:<20} [{t.kind.value}] size={t.size}")
        lines.append("=" * self._width)
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzBTFMiddleware(IMiddleware):
    """Middleware integration for the FizzBTF subsystem."""

    def __init__(self, registry: Optional[BTFRegistry] = None,
                 dashboard: Optional[FizzBTFDashboard] = None) -> None:
        self._registry = registry
        self._dashboard = dashboard

    def get_name(self) -> str:
        return "fizzbtf"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzBTF not initialized"


# ============================================================
# Factory
# ============================================================


def create_fizzbtf_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[BTFRegistry, FizzBTFDashboard, FizzBTFMiddleware]:
    """Factory function that creates and wires the FizzBTF subsystem.

    Pre-registers the core FizzBuzz platform types so that observability
    probes can decode them immediately.

    Returns:
        A tuple of (BTFRegistry, FizzBTFDashboard, FizzBTFMiddleware).
    """
    registry = BTFRegistry()
    # Register core platform types
    registry.register_type("fizzbuzz_result", BTFKind.STRUCT, 64, [
        {"name": "number", "offset": 0, "size": 8},
        {"name": "output", "offset": 8, "size": 56},
    ])
    registry.register_type("processing_context", BTFKind.STRUCT, 128, [
        {"name": "number", "offset": 0, "size": 8},
        {"name": "session_id", "offset": 8, "size": 40},
        {"name": "results", "offset": 48, "size": 80},
    ])
    registry.register_type("cache_entry", BTFKind.STRUCT, 96, [
        {"name": "key", "offset": 0, "size": 32},
        {"name": "value", "offset": 32, "size": 56},
        {"name": "ttl", "offset": 88, "size": 8},
    ])

    dashboard = FizzBTFDashboard(registry, dashboard_width)
    middleware = FizzBTFMiddleware(registry, dashboard)
    logger.info("FizzBTF initialized: %d types registered", len(registry.list_types()))
    return registry, dashboard, middleware

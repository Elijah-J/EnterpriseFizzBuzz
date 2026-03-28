"""
Enterprise FizzBuzz Platform - FizzGraphQL: GraphQL API Server

Schema-driven GraphQL API server with SDL parsing, type system, query
parsing/validation, resolver pipeline, introspection, subscriptions,
depth/complexity limiting, DataLoader batching, and a default FizzBuzz schema.

Architecture reference: GraphQL spec (June 2018), graphql-js, Apollo Server.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzgraphql import (
    FizzGraphQLError, FizzGraphQLSchemaError, FizzGraphQLTypeError,
    FizzGraphQLParseError, FizzGraphQLValidationError,
    FizzGraphQLDepthLimitError, FizzGraphQLComplexityLimitError,
    FizzGraphQLResolverError, FizzGraphQLExecutionError,
    FizzGraphQLSubscriptionError, FizzGraphQLIntrospectionError,
    FizzGraphQLDataLoaderError, FizzGraphQLConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzgraphql")

EVENT_GQL_QUERY = EventType.register("FIZZGRAPHQL_QUERY")
EVENT_GQL_MUTATION = EventType.register("FIZZGRAPHQL_MUTATION")

FIZZGRAPHQL_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 136


class GraphQLTypeKind(Enum):
    SCALAR = "SCALAR"
    OBJECT = "OBJECT"
    ENUM = "ENUM"
    INTERFACE = "INTERFACE"
    UNION = "UNION"
    INPUT_OBJECT = "INPUT_OBJECT"
    LIST = "LIST"
    NON_NULL = "NON_NULL"

class GraphQLOperationType(Enum):
    QUERY = "query"
    MUTATION = "mutation"
    SUBSCRIPTION = "subscription"


@dataclass
class FizzGraphQLConfig:
    max_depth: int = 10
    max_complexity: int = 1000
    introspection_enabled: bool = True
    batch_enabled: bool = True
    subscription_enabled: bool = True
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class GraphQLScalarType:
    name: str = ""
    kind: GraphQLTypeKind = GraphQLTypeKind.SCALAR

@dataclass
class GraphQLField:
    name: str = ""
    type_ref: str = ""
    args: Dict[str, str] = field(default_factory=dict)
    description: str = ""

@dataclass
class GraphQLObjectType:
    name: str = ""
    fields: Dict[str, GraphQLField] = field(default_factory=dict)
    interfaces: List[str] = field(default_factory=list)
    kind: GraphQLTypeKind = GraphQLTypeKind.OBJECT

@dataclass
class GraphQLEnumType:
    name: str = ""
    values: List[str] = field(default_factory=list)
    kind: GraphQLTypeKind = GraphQLTypeKind.ENUM

@dataclass
class GraphQLInterfaceType:
    name: str = ""
    fields: Dict[str, GraphQLField] = field(default_factory=dict)
    kind: GraphQLTypeKind = GraphQLTypeKind.INTERFACE

@dataclass
class GraphQLUnionType:
    name: str = ""
    types: List[str] = field(default_factory=list)
    kind: GraphQLTypeKind = GraphQLTypeKind.UNION

@dataclass
class GraphQLInputObjectType:
    name: str = ""
    fields: Dict[str, GraphQLField] = field(default_factory=dict)
    kind: GraphQLTypeKind = GraphQLTypeKind.INPUT_OBJECT

@dataclass
class GraphQLSchema:
    types: Dict[str, Any] = field(default_factory=dict)
    query_type: str = "Query"
    mutation_type: str = ""
    subscription_type: str = ""

@dataclass
class FieldNode:
    name: str = ""
    alias: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    selection_set: List["FieldNode"] = field(default_factory=list)

@dataclass
class OperationNode:
    operation_type: GraphQLOperationType = GraphQLOperationType.QUERY
    name: str = ""
    selection_set: List[FieldNode] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecutionResult:
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================
# SDL Parser
# ============================================================

class SDLParser:
    """Parses GraphQL Schema Definition Language into a GraphQLSchema."""

    def parse(self, sdl: str) -> GraphQLSchema:
        schema = GraphQLSchema()
        # Add default scalars
        for s in ["String", "Int", "Float", "Boolean", "ID"]:
            schema.types[s] = GraphQLScalarType(name=s)

        # Parse type definitions
        blocks = re.findall(r'(type|enum|interface|union|input)\s+(\w+)(?:\s+implements\s+(\w+))?\s*\{([^}]*)\}', sdl, re.DOTALL)
        for kind, name, implements, body in blocks:
            if kind == "type":
                obj = GraphQLObjectType(name=name)
                if implements:
                    obj.interfaces.append(implements)
                obj.fields = self._parse_fields(body)
                schema.types[name] = obj
                # Detect root types
                if name == "Query":
                    schema.query_type = "Query"
                elif name == "Mutation":
                    schema.mutation_type = "Mutation"
                elif name == "Subscription":
                    schema.subscription_type = "Subscription"
            elif kind == "enum":
                values = [v.strip() for v in body.strip().split("\n") if v.strip()]
                schema.types[name] = GraphQLEnumType(name=name, values=values)
            elif kind == "interface":
                iface = GraphQLInterfaceType(name=name, fields=self._parse_fields(body))
                schema.types[name] = iface
            elif kind == "input":
                inp = GraphQLInputObjectType(name=name, fields=self._parse_fields(body))
                schema.types[name] = inp
            elif kind == "union":
                pass  # TODO: union parsing

        return schema

    def _parse_fields(self, body: str) -> Dict[str, GraphQLField]:
        fields = {}
        for line in body.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Parse: fieldName(arg: Type!, arg2: Type): ReturnType!
            match = re.match(r'(\w+)(?:\(([^)]*)\))?\s*:\s*(.+)', line)
            if match:
                fname = match.group(1)
                args_str = match.group(2) or ""
                type_ref = match.group(3).strip()
                args = {}
                if args_str:
                    for arg in args_str.split(","):
                        arg = arg.strip()
                        if ":" in arg:
                            aname, atype = arg.split(":", 1)
                            args[aname.strip()] = atype.strip()
                fields[fname] = GraphQLField(name=fname, type_ref=type_ref, args=args)
        return fields


# ============================================================
# Query Parser
# ============================================================

class QueryParser:
    """Parses GraphQL query documents into an AST."""

    def parse(self, query: str) -> OperationNode:
        query = query.strip()

        # Extract and inline fragments
        fragments: Dict[str, str] = {}
        frag_pattern = re.compile(r'fragment\s+(\w+)\s+on\s+\w+\s*\{([^}]*)\}', re.DOTALL)
        for match in frag_pattern.finditer(query):
            fragments[match.group(1)] = match.group(2).strip()
        query = frag_pattern.sub("", query).strip()

        # Determine operation type
        op_type = GraphQLOperationType.QUERY
        name = ""
        variables = {}

        # Match operation header
        header_match = re.match(r'(query|mutation|subscription)\s*(\w*)\s*(?:\(([^)]*)\))?\s*\{', query)
        if header_match:
            op_str = header_match.group(1)
            name = header_match.group(2) or ""
            var_str = header_match.group(3) or ""
            op_type = {"query": GraphQLOperationType.QUERY, "mutation": GraphQLOperationType.MUTATION,
                        "subscription": GraphQLOperationType.SUBSCRIPTION}.get(op_str, GraphQLOperationType.QUERY)
            if var_str:
                for var in var_str.split(","):
                    var = var.strip()
                    if ":" in var:
                        vname, vtype = var.split(":", 1)
                        variables[vname.strip().lstrip("$")] = vtype.strip()

        # Extract body
        brace_start = query.find("{")
        if brace_start < 0:
            return OperationNode(operation_type=op_type, name=name)

        body = query[brace_start + 1:]
        # Remove trailing brace
        last_brace = body.rfind("}")
        if last_brace >= 0:
            body = body[:last_brace]

        selection_set = self._parse_selection_set(body, fragments)
        return OperationNode(operation_type=op_type, name=name,
                             selection_set=selection_set, variables=variables)

    def _parse_arguments(self, args_str: str) -> Dict[str, Any]:
        """Parse argument string, handling object values like {key: value}."""
        args = {}
        # Simple split approach that handles nested objects
        i = 0
        while i < len(args_str):
            # Skip whitespace
            while i < len(args_str) and args_str[i] in " \t\n\r,":
                i += 1
            if i >= len(args_str):
                break
            # Find arg name
            name_match = re.match(r'(\w+)\s*:\s*', args_str[i:])
            if not name_match:
                i += 1
                continue
            aname = name_match.group(1)
            i += name_match.end()
            # Parse value
            if i < len(args_str) and args_str[i] == "{":
                # Object value
                depth = 1
                start = i + 1
                i += 1
                while i < len(args_str) and depth > 0:
                    if args_str[i] == "{": depth += 1
                    elif args_str[i] == "}": depth -= 1
                    i += 1
                obj_body = args_str[start:i - 1]
                args[aname] = self._parse_arguments(obj_body)
            elif i < len(args_str) and args_str[i] == "$":
                # Variable reference
                var_match = re.match(r'\$(\w+)', args_str[i:])
                if var_match:
                    args[aname] = f"${var_match.group(1)}"
                    i += var_match.end()
            elif i < len(args_str) and args_str[i] == '"':
                # String value
                end = args_str.index('"', i + 1)
                args[aname] = args_str[i + 1:end]
                i = end + 1
            else:
                # Numeric or identifier
                val_match = re.match(r'([^\s,}]+)', args_str[i:])
                if val_match:
                    val = val_match.group(1)
                    try:
                        args[aname] = int(val)
                    except ValueError:
                        try:
                            args[aname] = float(val)
                        except ValueError:
                            args[aname] = val
                    i += val_match.end()
        return args

    def _parse_selection_set(self, body: str, fragments: Optional[Dict[str, str]] = None) -> List[FieldNode]:
        fragments = fragments or {}
        fields = []
        body = body.strip()

        # Inline fragment spreads
        for frag_name, frag_body in fragments.items():
            body = body.replace(f"...{frag_name}", frag_body)

        i = 0
        while i < len(body):
            # Skip whitespace
            while i < len(body) and body[i] in " \t\n\r":
                i += 1
            if i >= len(body):
                break

            # Skip remaining spread syntax
            if body[i:i+3] == "...":
                while i < len(body) and body[i] not in " \t\n\r{}":
                    i += 1
                continue

            # Parse field -- handle object args like (input: {number: 3})
            field_match = re.match(r'(?:(\w+)\s*:\s*)?(\w+)(?:\(([^)]*(?:\{[^}]*\}[^)]*)*)\))?\s*', body[i:])
            if not field_match:
                i += 1
                continue

            alias = field_match.group(1) or ""
            fname = field_match.group(2) or ""
            args_str = field_match.group(3) or ""
            i += field_match.end()

            args = {}
            if args_str:
                args = self._parse_arguments(args_str)

            node = FieldNode(name=fname, alias=alias, arguments=args)


            # Check for nested selection set
            if i < len(body) and body[i] == "{":
                depth = 1
                start = i + 1
                i += 1
                while i < len(body) and depth > 0:
                    if body[i] == "{":
                        depth += 1
                    elif body[i] == "}":
                        depth -= 1
                    i += 1
                nested_body = body[start:i - 1]
                node.selection_set = self._parse_selection_set(nested_body)

            if fname:
                fields.append(node)

        return fields


# ============================================================
# Query Validator
# ============================================================

class QueryValidator:
    """Validates GraphQL queries against a schema."""

    def validate(self, operation: OperationNode, schema: GraphQLSchema) -> List[str]:
        errors = []
        root_type_name = schema.query_type
        if operation.operation_type == GraphQLOperationType.MUTATION:
            root_type_name = schema.mutation_type
        elif operation.operation_type == GraphQLOperationType.SUBSCRIPTION:
            root_type_name = schema.subscription_type

        root_type = schema.types.get(root_type_name)
        if root_type is None:
            errors.append(f"Root type '{root_type_name}' not found")
            return errors

        self._validate_fields(operation.selection_set, root_type, schema, errors)
        return errors

    def _validate_fields(self, fields: List[FieldNode], parent_type: Any,
                         schema: GraphQLSchema, errors: List[str]) -> None:
        if not hasattr(parent_type, "fields"):
            return
        for field_node in fields:
            if field_node.name == "__typename":
                continue
            if field_node.name not in parent_type.fields:
                errors.append(f"Field '{field_node.name}' not found on type '{parent_type.name}'")
                continue
            field_def = parent_type.fields[field_node.name]
            if field_node.selection_set:
                # Resolve the return type
                type_name = field_def.type_ref.strip("![]").strip()
                child_type = schema.types.get(type_name)
                if child_type:
                    self._validate_fields(field_node.selection_set, child_type, schema, errors)

    def check_depth(self, operation: OperationNode, max_depth: int) -> bool:
        depth = self._measure_depth(operation.selection_set)
        return depth <= max_depth

    def _measure_depth(self, fields: List[FieldNode], current: int = 1) -> int:
        if not fields:
            return current
        max_d = current
        for f in fields:
            if f.selection_set:
                d = self._measure_depth(f.selection_set, current + 1)
                max_d = max(max_d, d)
        return max_d

    def check_complexity(self, operation: OperationNode, max_complexity: int) -> bool:
        complexity = self._measure_complexity(operation.selection_set)
        return complexity <= max_complexity

    def _measure_complexity(self, fields: List[FieldNode]) -> int:
        total = 0
        for f in fields:
            total += 1
            if f.selection_set:
                total += self._measure_complexity(f.selection_set)
        return total


# ============================================================
# Resolver Registry
# ============================================================

class ResolverRegistry:
    """Maps (type_name, field_name) to resolver functions."""

    def __init__(self) -> None:
        self._resolvers: Dict[str, Dict[str, Callable]] = defaultdict(dict)

    def register(self, type_name: str, field_name: str, resolver: Callable) -> None:
        self._resolvers[type_name][field_name] = resolver

    def resolve(self, type_name: str, field_name: str, parent: Any,
                args: Dict[str, Any], context: Any = None) -> Any:
        resolver = self._resolvers.get(type_name, {}).get(field_name)
        if resolver is not None:
            return resolver(parent, args, context)
        # Default resolver: dict key or attribute
        if isinstance(parent, dict):
            return parent.get(field_name)
        return getattr(parent, field_name, None)


# ============================================================
# Execution Engine
# ============================================================

class ExecutionEngine:
    """Executes GraphQL queries against a schema with resolvers."""

    def __init__(self, schema: GraphQLSchema, resolver_registry: Optional[ResolverRegistry] = None) -> None:
        self._schema = schema
        self._resolvers = resolver_registry or ResolverRegistry()
        self._parser = QueryParser()

    def execute(self, schema: Optional[GraphQLSchema] = None, query: str = "",
                variables: Optional[Dict[str, Any]] = None,
                context: Any = None) -> ExecutionResult:
        result = ExecutionResult()
        schema = schema or self._schema

        try:
            operation = self._parser.parse(query)
        except Exception as e:
            result.errors.append({"message": f"Parse error: {e}"})
            return result

        # Substitute variables
        if variables:
            self._substitute_variables(operation.selection_set, variables)

        root_type_name = schema.query_type
        if operation.operation_type == GraphQLOperationType.MUTATION:
            root_type_name = schema.mutation_type

        root_type = schema.types.get(root_type_name)
        if root_type is None:
            result.errors.append({"message": f"Root type '{root_type_name}' not found"})
            return result

        data = {}
        for field_node in operation.selection_set:
            key = field_node.alias or field_node.name
            if field_node.name == "__typename":
                data[key] = root_type_name
                continue
            try:
                value = self._resolve_field(field_node, root_type_name, None, schema, context)
                data[key] = value
            except Exception as e:
                result.errors.append({"message": str(e), "path": [key]})
                data[key] = None

        result.data = data
        return result

    def _resolve_field(self, field_node: FieldNode, type_name: str,
                       parent: Any, schema: GraphQLSchema, context: Any) -> Any:
        value = self._resolvers.resolve(type_name, field_node.name, parent, field_node.arguments, context)

        if value is None:
            return None

        if field_node.selection_set:
            if isinstance(value, list):
                return [self._resolve_object(item, field_node.selection_set, schema, context)
                        for item in value]
            return self._resolve_object(value, field_node.selection_set, schema, context)

        return value

    def _resolve_object(self, obj: Any, selection_set: List[FieldNode],
                        schema: GraphQLSchema, context: Any) -> Dict[str, Any]:
        result = {}
        obj_type = type(obj).__name__ if not isinstance(obj, dict) else ""

        for field_node in selection_set:
            key = field_node.alias or field_node.name
            if field_node.name == "__typename":
                result[key] = obj_type or "Object"
                continue

            if isinstance(obj, dict):
                value = obj.get(field_node.name)
            else:
                value = getattr(obj, field_node.name, None)

            if field_node.selection_set and value is not None:
                if isinstance(value, list):
                    value = [self._resolve_object(item, field_node.selection_set, schema, context)
                             for item in value]
                elif isinstance(value, dict):
                    value = self._resolve_object(value, field_node.selection_set, schema, context)

            result[key] = value

        return result

    def _substitute_variables(self, fields: List[FieldNode], variables: Dict[str, Any]) -> None:
        for f in fields:
            for key, val in list(f.arguments.items()):
                if isinstance(val, str) and val.startswith("$"):
                    var_name = val[1:]
                    if var_name in variables:
                        f.arguments[key] = variables[var_name]
            if f.selection_set:
                self._substitute_variables(f.selection_set, variables)


# ============================================================
# DataLoader
# ============================================================

class DataLoader:
    """Batches and caches data loading operations."""

    def __init__(self, batch_fn: Callable) -> None:
        self._batch_fn = batch_fn
        self._pending: List[Any] = []
        self._cache: Dict[Any, Any] = {}

    def load(self, key: Any) -> Any:
        if key in self._cache:
            return self._cache[key]
        self._pending.append(key)
        return self._cache.get(key)

    def dispatch(self) -> None:
        if not self._pending:
            return
        keys = list(self._pending)
        self._pending.clear()
        results = self._batch_fn(keys)
        if isinstance(results, dict):
            self._cache.update(results)


# ============================================================
# Introspection System
# ============================================================

class IntrospectionSystem:
    """GraphQL introspection queries."""

    def get_schema_introspection(self, schema: GraphQLSchema) -> Dict[str, Any]:
        types_list = []
        for name, type_obj in schema.types.items():
            types_list.append({"name": name, "kind": getattr(type_obj, "kind", GraphQLTypeKind.SCALAR).value})

        return {
            "queryType": {"name": schema.query_type} if schema.query_type else None,
            "mutationType": {"name": schema.mutation_type} if schema.mutation_type else None,
            "subscriptionType": {"name": schema.subscription_type} if schema.subscription_type else None,
            "types": types_list,
        }

    def get_type_introspection(self, schema: GraphQLSchema, type_name: str) -> Dict[str, Any]:
        type_obj = schema.types.get(type_name)
        if type_obj is None:
            return {}

        result = {"name": type_name, "kind": getattr(type_obj, "kind", GraphQLTypeKind.SCALAR).value}

        if hasattr(type_obj, "fields"):
            result["fields"] = [
                {"name": f.name, "type": f.type_ref, "args": [
                    {"name": aname, "type": atype} for aname, atype in f.args.items()
                ]}
                for f in type_obj.fields.values()
            ]

        if hasattr(type_obj, "values"):
            result["enumValues"] = [{"name": v} for v in type_obj.values]

        return result


# ============================================================
# Subscription Manager
# ============================================================

class SubscriptionManager:
    """Pub/sub subscription manager."""

    def __init__(self) -> None:
        self._subscriptions: Dict[str, Dict[str, Callable]] = defaultdict(dict)

    def subscribe(self, topic: str, callback: Callable) -> str:
        handle = uuid.uuid4().hex[:12]
        self._subscriptions[topic][handle] = callback
        return handle

    def publish(self, topic: str, payload: Any) -> None:
        for callback in list(self._subscriptions.get(topic, {}).values()):
            callback(payload)

    def unsubscribe(self, handle: str) -> None:
        for topic in self._subscriptions.values():
            topic.pop(handle, None)


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzGraphQLDashboard:
    def __init__(self, schema: Optional[GraphQLSchema] = None,
                 engine: Optional[ExecutionEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._schema = schema
        self._engine = engine
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzGraphQL API Server Dashboard".center(self._width),
            "=" * self._width,
            f"  Version:    {FIZZGRAPHQL_VERSION}",
        ]
        if self._schema:
            lines.append(f"  Types:      {len(self._schema.types)}")
            lines.append(f"  Query:      {self._schema.query_type}")
            if self._schema.mutation_type:
                lines.append(f"  Mutation:   {self._schema.mutation_type}")
            if self._schema.subscription_type:
                lines.append(f"  Subscr:     {self._schema.subscription_type}")
        return "\n".join(lines)


class FizzGraphQLMiddleware(IMiddleware):
    def __init__(self, schema: Optional[GraphQLSchema] = None,
                 engine: Optional[ExecutionEngine] = None,
                 dashboard: Optional[FizzGraphQLDashboard] = None,
                 config: Optional[FizzGraphQLConfig] = None) -> None:
        self._schema = schema
        self._engine = engine
        self._dashboard = dashboard
        self._config = config or FizzGraphQLConfig()

    def get_name(self) -> str: return "fizzgraphql"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzGraphQL not initialized"

    def render_schema(self) -> str:
        if not self._schema:
            return "No schema"
        lines = []
        for name, t in self._schema.types.items():
            if hasattr(t, "fields") and isinstance(t, GraphQLObjectType):
                lines.append(f"type {name} {{")
                for f in t.fields.values():
                    args = ", ".join(f"{k}: {v}" for k, v in f.args.items())
                    args_str = f"({args})" if args else ""
                    lines.append(f"  {f.name}{args_str}: {f.type_ref}")
                lines.append("}")
        return "\n".join(lines)

    def render_query(self, query: str) -> str:
        if self._engine and self._schema:
            result = self._engine.execute(self._schema, query)
            return json.dumps({"data": result.data, "errors": result.errors}, indent=2, default=str)
        return "No engine"

    def render_introspection(self) -> str:
        if self._schema:
            intro = IntrospectionSystem()
            return json.dumps(intro.get_schema_introspection(self._schema), indent=2)
        return "No schema"


# ============================================================
# Factory
# ============================================================

def create_fizzgraphql_subsystem(
    max_depth: int = 10, max_complexity: int = 1000,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[GraphQLSchema, ExecutionEngine, FizzGraphQLDashboard, FizzGraphQLMiddleware]:
    config = FizzGraphQLConfig(max_depth=max_depth, max_complexity=max_complexity,
                               dashboard_width=dashboard_width)

    sdl = """
        type FizzBuzzResult {
            input: Int!
            output: String!
            isFizz: Boolean!
            isBuzz: Boolean!
            isFizzBuzz: Boolean!
        }

        type InfrastructureStatus {
            modulesLoaded: Int!
            uptime: Float!
            version: String!
        }

        type Query {
            fizzbuzz(n: Int!): FizzBuzzResult
            fizzbuzzRange(start: Int!, end: Int!): [FizzBuzzResult!]!
            infrastructureStatus: InfrastructureStatus
            __typename: String
        }

        type Mutation {
            evaluateFizzBuzz(n: Int!): FizzBuzzResult
        }

        type Subscription {
            onFizzBuzzEvaluation: FizzBuzzResult
        }
    """

    parser = SDLParser()
    schema = parser.parse(sdl)

    registry = ResolverRegistry()

    def fizzbuzz_resolver(parent, args, ctx):
        n = args.get("n", 0)
        if n % 15 == 0: output = "FizzBuzz"
        elif n % 3 == 0: output = "Fizz"
        elif n % 5 == 0: output = "Buzz"
        else: output = str(n)
        return {"input": n, "output": output, "isFizz": n % 3 == 0,
                "isBuzz": n % 5 == 0, "isFizzBuzz": n % 15 == 0}

    registry.register("Query", "fizzbuzz", fizzbuzz_resolver)
    registry.register("Query", "infrastructureStatus", lambda p, a, c: {
        "modulesLoaded": 150, "uptime": 42.0, "version": "1.0.0"
    })
    registry.register("Mutation", "evaluateFizzBuzz", fizzbuzz_resolver)

    engine = ExecutionEngine(schema, registry)
    dashboard = FizzGraphQLDashboard(schema, engine, dashboard_width)
    middleware = FizzGraphQLMiddleware(schema, engine, dashboard, config)

    logger.info("FizzGraphQL initialized: %d types", len(schema.types))
    return schema, engine, dashboard, middleware

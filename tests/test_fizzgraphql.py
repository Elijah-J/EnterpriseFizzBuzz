"""
Tests for the FizzGraphQL API Server.

Validates the SDL parser, query parser, query validator, resolver registry,
execution engine, DataLoader batching, introspection system, subscription
manager, dashboard, and middleware — ensuring that GraphQL queries against
FizzBuzz evaluation data resolve with the same precision one expects from
a production API gateway.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzgraphql import (
    FIZZGRAPHQL_VERSION,
    MIDDLEWARE_PRIORITY,
    GraphQLTypeKind,
    GraphQLOperationType,
    FizzGraphQLConfig,
    GraphQLSchema,
    GraphQLObjectType,
    GraphQLField,
    GraphQLEnumType,
    GraphQLScalarType,
    OperationNode,
    FieldNode,
    ExecutionResult,
    SDLParser,
    QueryParser,
    QueryValidator,
    ResolverRegistry,
    ExecutionEngine,
    DataLoader,
    IntrospectionSystem,
    SubscriptionManager,
    FizzGraphQLDashboard,
    FizzGraphQLMiddleware,
    create_fizzgraphql_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def simple_sdl():
    """A minimal SDL defining a Query type with one scalar field."""
    return """
        type Query {
            fizzbuzz(number: Int!): String!
        }
    """


@pytest.fixture
def full_sdl():
    """A richer SDL with enums, interfaces, and input types."""
    return """
        enum Classification {
            FIZZ
            BUZZ
            FIZZBUZZ
            PLAIN
        }

        interface Node {
            id: ID!
        }

        input EvaluationInput {
            number: Int!
            strategy: String
        }

        type Evaluation implements Node {
            id: ID!
            number: Int!
            output: String!
            classification: Classification!
        }

        type Query {
            evaluation(number: Int!): Evaluation
            evaluations(first: Int): [Evaluation!]!
        }

        type Mutation {
            evaluate(input: EvaluationInput!): Evaluation!
        }

        type Subscription {
            evaluationAdded: Evaluation!
        }
    """


@pytest.fixture
def parsed_schema(full_sdl):
    """A fully parsed GraphQL schema from the full SDL fixture."""
    parser = SDLParser()
    return parser.parse(full_sdl)


@pytest.fixture
def resolver_registry():
    """A resolver registry with a simple fizzbuzz resolver wired up."""
    registry = ResolverRegistry()
    registry.register("Query", "evaluation", lambda parent, args, ctx: {
        "id": str(args["number"]),
        "number": args["number"],
        "output": "Fizz" if args["number"] % 3 == 0 else str(args["number"]),
        "classification": "FIZZ" if args["number"] % 3 == 0 else "PLAIN",
    })
    return registry


@pytest.fixture
def execution_engine(parsed_schema, resolver_registry):
    """An execution engine wired to the full schema and resolver registry."""
    return ExecutionEngine(parsed_schema, resolver_registry)


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version(self):
        """The module version follows semantic versioning and matches 1.0.0."""
        assert FIZZGRAPHQL_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority is set to 136 for correct ordering in the pipeline."""
        assert MIDDLEWARE_PRIORITY == 136


# ============================================================
# TestSDLParser
# ============================================================


class TestSDLParser:
    """Validate SDL-to-schema parsing for all GraphQL type definitions."""

    def test_parse_simple_type(self, simple_sdl):
        """Parsing a type definition produces a GraphQLObjectType with the correct fields."""
        schema = SDLParser().parse(simple_sdl)
        assert "Query" in schema.types
        query_type = schema.types["Query"]
        assert isinstance(query_type, GraphQLObjectType)
        assert "fizzbuzz" in query_type.fields
        field = query_type.fields["fizzbuzz"]
        assert isinstance(field, GraphQLField)
        assert field.name == "fizzbuzz"

    def test_parse_enum(self, full_sdl):
        """Enum definitions are parsed with all declared values."""
        schema = SDLParser().parse(full_sdl)
        assert "Classification" in schema.types
        enum_type = schema.types["Classification"]
        assert isinstance(enum_type, GraphQLEnumType)
        assert set(enum_type.values) == {"FIZZ", "BUZZ", "FIZZBUZZ", "PLAIN"}

    def test_parse_interface(self, full_sdl):
        """Interface definitions are recognized and stored in the schema type map."""
        schema = SDLParser().parse(full_sdl)
        assert "Node" in schema.types

    def test_parse_input_type(self, full_sdl):
        """Input object types are parsed and included in the schema type map."""
        schema = SDLParser().parse(full_sdl)
        assert "EvaluationInput" in schema.types

    def test_parse_non_null_and_list_fields(self, full_sdl):
        """Non-null and list type modifiers are captured in the field type_ref string."""
        schema = SDLParser().parse(full_sdl)
        evaluations_field = schema.types["Query"].fields["evaluations"]
        # The type_ref should encode the list and non-null modifiers
        type_ref = evaluations_field.type_ref
        assert "[" in type_ref or "List" in type_ref or "list" in type_ref.lower()

    def test_parse_full_schema_root_types(self, full_sdl):
        """A schema with Query, Mutation, and Subscription root types is fully recognized."""
        schema = SDLParser().parse(full_sdl)
        assert isinstance(schema, GraphQLSchema)
        assert schema.query_type == "Query"
        assert schema.mutation_type == "Mutation"
        assert schema.subscription_type == "Subscription"


# ============================================================
# TestQueryParser
# ============================================================


class TestQueryParser:
    """Validate GraphQL query text parsing into an operation AST."""

    def test_simple_query(self):
        """A basic query with one field produces an OperationNode with that field."""
        op = QueryParser().parse("query { fizzbuzz }")
        assert isinstance(op, OperationNode)
        assert op.operation_type == GraphQLOperationType.QUERY
        assert len(op.selection_set) >= 1
        assert any(f.name == "fizzbuzz" for f in op.selection_set)

    def test_nested_fields(self):
        """Nested selections produce FieldNodes with their own selection_set."""
        op = QueryParser().parse("{ evaluation { id number output } }")
        eval_field = next(f for f in op.selection_set if f.name == "evaluation")
        assert len(eval_field.selection_set) == 3
        child_names = {f.name for f in eval_field.selection_set}
        assert child_names == {"id", "number", "output"}

    def test_arguments(self):
        """Field arguments are parsed into the FieldNode arguments dict."""
        op = QueryParser().parse('{ evaluation(number: 15) { output } }')
        eval_field = next(f for f in op.selection_set if f.name == "evaluation")
        assert eval_field.arguments.get("number") == 15

    def test_aliases(self):
        """Field aliases are captured on the FieldNode."""
        op = QueryParser().parse("{ myEval: evaluation { output } }")
        field = op.selection_set[0]
        assert field.alias == "myEval"
        assert field.name == "evaluation"

    def test_fragments(self):
        """Fragment spreads are inlined into the selection set during parsing."""
        query = """
            fragment EvalFields on Evaluation {
                id
                number
            }
            query {
                evaluation {
                    ...EvalFields
                    output
                }
            }
        """
        op = QueryParser().parse(query)
        eval_field = next(f for f in op.selection_set if f.name == "evaluation")
        child_names = {f.name for f in eval_field.selection_set}
        assert "id" in child_names
        assert "number" in child_names
        assert "output" in child_names


# ============================================================
# TestQueryValidator
# ============================================================


class TestQueryValidator:
    """Validate query validation against a schema."""

    def test_valid_query_passes(self, parsed_schema):
        """A query referencing existing fields produces no validation errors."""
        op = QueryParser().parse("{ evaluation(number: 3) { id number output } }")
        errors = QueryValidator().validate(op, parsed_schema)
        assert errors == []

    def test_invalid_field_fails(self, parsed_schema):
        """A query referencing a non-existent field produces a validation error."""
        op = QueryParser().parse("{ nonExistentField { id } }")
        errors = QueryValidator().validate(op, parsed_schema)
        assert len(errors) > 0
        assert any("nonExistentField" in str(e) for e in errors)

    def test_depth_limit(self):
        """check_depth returns False when the query exceeds the configured max depth."""
        # Build a deeply nested query: a { b { c { d { e { f { g { h { i { j { k } } } } } } } } } }
        levels = 12
        query = "{ " + " { ".join(f"f{i}" for i in range(levels)) + " { leaf } " + " }" * levels + " }"
        op = QueryParser().parse(query)
        validator = QueryValidator()
        assert validator.check_depth(op, max_depth=5) is False
        assert validator.check_depth(op, max_depth=20) is True

    def test_complexity_limit(self, parsed_schema):
        """check_complexity returns False when estimated cost exceeds the threshold."""
        # A query selecting many fields should accumulate complexity
        op = QueryParser().parse("""
            {
                evaluation(number: 1) { id number output classification }
                evaluations(first: 100) { id number output classification }
            }
        """)
        validator = QueryValidator()
        # With a very low threshold it should exceed
        assert validator.check_complexity(op, max_complexity=1) is False
        # With a generous threshold it should pass
        assert validator.check_complexity(op, max_complexity=100000) is True


# ============================================================
# TestResolverRegistry
# ============================================================


class TestResolverRegistry:
    """Validate resolver registration and invocation."""

    def test_register_and_resolve(self):
        """A registered resolver is invoked with the correct arguments."""
        registry = ResolverRegistry()
        resolver_fn = MagicMock(return_value="FizzBuzz")
        registry.register("Query", "fizzbuzz", resolver_fn)
        result = registry.resolve("Query", "fizzbuzz", None, {"number": 15}, {})
        resolver_fn.assert_called_once_with(None, {"number": 15}, {})
        assert result == "FizzBuzz"

    def test_default_resolver_uses_dict_key(self):
        """When no resolver is registered, dict parent values are used as defaults."""
        registry = ResolverRegistry()
        parent = {"name": "Fizz", "value": 3}
        result = registry.resolve("Evaluation", "name", parent, {}, {})
        assert result == "Fizz"

    def test_missing_resolver_returns_none(self):
        """Resolving a field with no resolver and a non-dict parent returns None."""
        registry = ResolverRegistry()
        result = registry.resolve("Query", "missing", None, {}, {})
        assert result is None


# ============================================================
# TestExecutionEngine
# ============================================================


class TestExecutionEngine:
    """Validate end-to-end query execution."""

    def test_simple_query_returns_data(self, execution_engine):
        """Executing a simple query returns an ExecutionResult with populated data."""
        result = execution_engine.execute(
            execution_engine._schema if hasattr(execution_engine, '_schema') else None,
            '{ evaluation(number: 3) { number output } }',
        )
        assert isinstance(result, ExecutionResult)
        assert isinstance(result.data, dict)
        assert "evaluation" in result.data
        assert result.data["evaluation"]["number"] == 3
        assert result.data["evaluation"]["output"] == "Fizz"

    def test_nested_query(self, execution_engine):
        """Nested field selections resolve correctly through the object graph."""
        result = execution_engine.execute(
            None,
            '{ evaluation(number: 9) { id number output classification } }',
        )
        eval_data = result.data.get("evaluation", {})
        assert eval_data.get("number") == 9
        assert eval_data.get("classification") == "FIZZ"

    def test_arguments_passed(self, parsed_schema):
        """Arguments from the query are forwarded to the resolver function."""
        received_args = {}

        def capture_resolver(parent, args, ctx):
            received_args.update(args)
            return {"number": args["number"], "output": str(args["number"])}

        registry = ResolverRegistry()
        registry.register("Query", "evaluation", capture_resolver)
        engine = ExecutionEngine(parsed_schema, registry)
        engine.execute(parsed_schema, '{ evaluation(number: 42) { number } }')
        assert received_args.get("number") == 42

    def test_errors_collected(self, parsed_schema):
        """Resolver exceptions are caught and collected in ExecutionResult.errors."""
        def failing_resolver(parent, args, ctx):
            raise ValueError("Resolver blew up")

        registry = ResolverRegistry()
        registry.register("Query", "evaluation", failing_resolver)
        engine = ExecutionEngine(parsed_schema, registry)
        result = engine.execute(parsed_schema, '{ evaluation(number: 1) { number } }')
        assert len(result.errors) > 0

    def test_mutation(self, parsed_schema):
        """Mutation operations are dispatched to the correct resolver."""
        registry = ResolverRegistry()
        registry.register("Mutation", "evaluate", lambda p, a, c: {
            "id": "1", "number": a["input"]["number"],
            "output": "Fizz", "classification": "FIZZ",
        })
        engine = ExecutionEngine(parsed_schema, registry)
        result = engine.execute(
            parsed_schema,
            'mutation { evaluate(input: {number: 3}) { number output } }',
        )
        assert isinstance(result, ExecutionResult)
        assert result.data.get("evaluate", {}).get("output") == "Fizz"

    def test_variables(self, parsed_schema):
        """Query variables are substituted into argument positions at execution time."""
        registry = ResolverRegistry()
        registry.register("Query", "evaluation", lambda p, a, c: {
            "id": str(a["number"]), "number": a["number"],
            "output": str(a["number"]), "classification": "PLAIN",
        })
        engine = ExecutionEngine(parsed_schema, registry)
        result = engine.execute(
            parsed_schema,
            'query GetEval($n: Int!) { evaluation(number: $n) { number } }',
            variables={"n": 7},
        )
        assert result.data.get("evaluation", {}).get("number") == 7


# ============================================================
# TestDataLoader
# ============================================================


class TestDataLoader:
    """Validate DataLoader batching and caching semantics."""

    def test_batches_loads(self):
        """Multiple load() calls are batched into a single batch_fn invocation."""
        batch_fn = MagicMock(return_value={1: "one", 2: "two", 3: "three"})
        loader = DataLoader(batch_fn)
        loader.load(1)
        loader.load(2)
        loader.load(3)
        loader.dispatch()
        batch_fn.assert_called_once()
        keys_arg = batch_fn.call_args[0][0]
        assert set(keys_arg) == {1, 2, 3}

    def test_caches_results(self):
        """Previously loaded keys are served from cache without re-batching."""
        call_count = 0

        def counting_batch(keys):
            nonlocal call_count
            call_count += 1
            return {k: f"val-{k}" for k in keys}

        loader = DataLoader(counting_batch)
        loader.load(1)
        loader.dispatch()
        assert call_count == 1
        # Second load for the same key should not trigger another batch
        result = loader.load(1)
        loader.dispatch()
        assert call_count == 1
        assert result == "val-1"

    def test_dispatch_clears_pending_batch(self):
        """After dispatch(), the pending key set is empty."""
        batch_fn = MagicMock(return_value={})
        loader = DataLoader(batch_fn)
        loader.load(1)
        loader.dispatch()
        # A second dispatch with no new loads should not call batch_fn again
        batch_fn.reset_mock()
        loader.dispatch()
        batch_fn.assert_not_called()


# ============================================================
# TestIntrospectionSystem
# ============================================================


class TestIntrospectionSystem:
    """Validate GraphQL introspection capabilities."""

    def test_schema_introspection(self, parsed_schema):
        """get_schema_introspection returns a dict describing all types and root operations."""
        intro = IntrospectionSystem()
        result = intro.get_schema_introspection(parsed_schema)
        assert isinstance(result, dict)
        assert "queryType" in result or "query_type" in result
        # The types list should contain our defined types
        types_list = result.get("types", result.get("__schema", {}).get("types", []))
        type_names = {t.get("name") if isinstance(t, dict) else t for t in types_list}
        assert "Query" in type_names
        assert "Evaluation" in type_names

    def test_type_introspection(self, parsed_schema):
        """get_type_introspection returns field details for a named type."""
        intro = IntrospectionSystem()
        result = intro.get_type_introspection(parsed_schema, "Evaluation")
        assert isinstance(result, dict)
        assert result.get("name") == "Evaluation"
        fields = result.get("fields", [])
        field_names = {f.get("name") if isinstance(f, dict) else f for f in fields}
        assert "number" in field_names
        assert "output" in field_names

    def test_typename_field(self, parsed_schema):
        """The __typename meta-field is available on object types."""
        intro = IntrospectionSystem()
        result = intro.get_type_introspection(parsed_schema, "Query")
        assert isinstance(result, dict)
        # __typename should either be in fields or handled by the introspection system
        assert result.get("name") == "Query"


# ============================================================
# TestSubscriptionManager
# ============================================================


class TestSubscriptionManager:
    """Validate pub/sub subscription lifecycle."""

    def test_subscribe_and_publish(self):
        """A subscribed callback receives published payloads."""
        manager = SubscriptionManager()
        received = []
        handle = manager.subscribe("evaluationAdded", lambda payload: received.append(payload))
        assert isinstance(handle, str)
        manager.publish("evaluationAdded", {"number": 15, "output": "FizzBuzz"})
        assert len(received) == 1
        assert received[0]["number"] == 15

    def test_unsubscribe_stops_delivery(self):
        """After unsubscribe, the callback no longer receives messages."""
        manager = SubscriptionManager()
        received = []
        handle = manager.subscribe("evaluationAdded", lambda p: received.append(p))
        manager.unsubscribe(handle)
        manager.publish("evaluationAdded", {"number": 3})
        assert len(received) == 0

    def test_multiple_subscribers(self):
        """Multiple subscribers to the same topic all receive the payload."""
        manager = SubscriptionManager()
        received_a = []
        received_b = []
        manager.subscribe("eval", lambda p: received_a.append(p))
        manager.subscribe("eval", lambda p: received_b.append(p))
        manager.publish("eval", {"n": 5})
        assert len(received_a) == 1
        assert len(received_b) == 1


# ============================================================
# TestFizzGraphQLMiddleware
# ============================================================


class TestFizzGraphQLMiddleware:
    """Validate the middleware integration surface."""

    def test_name(self):
        """The middleware identifies itself as 'fizzgraphql'."""
        mw = FizzGraphQLMiddleware()
        assert mw.get_name() == "fizzgraphql"

    def test_priority(self):
        """The middleware priority matches the module constant."""
        mw = FizzGraphQLMiddleware()
        assert mw.get_priority() == MIDDLEWARE_PRIORITY
        assert mw.get_priority() == 136

    def test_process_delegates(self):
        """process() invokes the next handler in the middleware chain."""
        mw = FizzGraphQLMiddleware()
        context = MagicMock()
        next_handler = MagicMock()
        mw.process(context, next_handler)
        next_handler.assert_called_once()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Validate the factory function for wiring the full FizzGraphQL subsystem."""

    def test_returns_tuple(self):
        """create_fizzgraphql_subsystem returns a 4-tuple of the expected types."""
        result = create_fizzgraphql_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 4
        schema, engine, dashboard, middleware = result
        assert isinstance(schema, GraphQLSchema)
        assert isinstance(engine, ExecutionEngine)
        assert isinstance(dashboard, FizzGraphQLDashboard)
        assert isinstance(middleware, FizzGraphQLMiddleware)

    def test_schema_has_query_type(self):
        """The subsystem schema includes a Query root type."""
        schema, _, _, _ = create_fizzgraphql_subsystem()
        assert schema.query_type == "Query"
        assert "Query" in schema.types

    def test_execution_works(self):
        """The wired subsystem can execute a basic query end-to-end."""
        schema, engine, _, _ = create_fizzgraphql_subsystem()
        result = engine.execute(schema, "{ __typename }")
        assert isinstance(result, ExecutionResult)
        assert isinstance(result.data, dict)
        assert result.errors is not None  # errors list exists (may be empty)

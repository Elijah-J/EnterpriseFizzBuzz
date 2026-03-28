# PLAN.md -- FizzGraphQL: GraphQL API Server

## Overview
Schema-driven GraphQL API server. SDL parsing, type system, query parsing/validation, resolver pipeline, introspection, subscriptions, depth/complexity limiting, DataLoader batching, default FizzBuzz schema.

## TDD: Tests written FIRST.

## Phases
1. Exceptions, constants, enums, dataclasses
2. SDL parser, query parser, validator (depth/complexity)
3. Resolver pipeline, execution engine, DataLoader, introspection
4. Subscriptions, default schema, middleware, factory

## ~800-1000 lines, ~40 tests, 10 CLI flags

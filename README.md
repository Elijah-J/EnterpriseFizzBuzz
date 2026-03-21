# EnterpriseFizzBuzz

### A Production-Grade, Enterprise-Ready, Clean-Architecture-Layered FizzBuzz Evaluation Engine

> *Because you can never be too careful when dividing by 3 and 5.*

```
  +===========================================================+
  |                                                           |
  |   FFFFFFFF II ZZZZZZZ ZZZZZZZ BBBBB   UU   UU ZZZZZZZ   |
  |   FF       II      ZZ      ZZ BB  BB  UU   UU      ZZ    |
  |   FFFFFF   II    ZZ      ZZ   BBBBB   UU   UU    ZZ      |
  |   FF       II   ZZ      ZZ   BB  BB  UU   UU   ZZ        |
  |   FF       II ZZZZZZZ ZZZZZZZ BBBBB   UUUUUU ZZZZZZZ    |
  |                                                           |
  |         E N T E R P R I S E   E D I T I O N              |
  |                    v1.0.0                                 |
  |                                                           |
  +===========================================================+
```

## The Problem

Print numbers 1 to 100. For multiples of 3, print "Fizz". For multiples of 5, print "Buzz". For multiples of both, print "FizzBuzz".

## The Naive Solution

```python
for i in range(1, 101):
    print("FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else i)
```

## This Solution

**28,100+ lines** across **72 files** with **967 unit tests** and **81 custom exception classes**, now organized into a Clean Architecture / Hexagonal Architecture package structure with three concentric layers -- because flat module layouts are for startups that haven't yet discovered the Dependency Rule.

## Architecture

The codebase follows **Clean Architecture** (a.k.a. **Hexagonal Architecture**, **Ports and Adapters**, **Onion Architecture** -- because one name for the same concept would be insufficiently enterprise). The flat-file layout has been promoted to a proper layered package structure with three concentric dependency rings, because 28,000 lines of FizzBuzz deserved an architectural diagram that looks like it belongs in a Martin Fowler keynote.

### The Dependency Rule

```
    +---------------------------------------------------------------+
    |                     INFRASTRUCTURE                             |
    |   config, formatters, middleware, observers, plugins,          |
    |   rules_engine, ml_engine, blockchain, circuit_breaker,        |
    |   tracing, auth, i18n, event_sourcing, chaos, feature_flags,   |
    |   sla, cache, migrations                                       |
    |                                                                |
    |   +-------------------------------------------------------+   |
    |   |                   APPLICATION                          |   |
    |   |   fizzbuzz_service (Builder pattern orchestration)      |   |
    |   |   factory (Abstract Factory + Caching Decorator)       |   |
    |   |                                                        |   |
    |   |   +-----------------------------------------------+   |   |
    |   |   |                 DOMAIN                         |   |   |
    |   |   |   models, exceptions, interfaces               |   |   |
    |   |   |   (the sacred inner circle)                    |   |   |
    |   |   +-----------------------------------------------+   |   |
    |   +-------------------------------------------------------+   |
    +---------------------------------------------------------------+

    Dependencies point INWARD only:
      domain  <--  application  <--  infrastructure
    Violations are caught by an AST-based architecture test.
```

### Package Structure

```
EnterpriseFizzBuzz/
├── main.py                          # CLI entry point with 46 flags
├── config.yaml                      # YAML-based configuration with 12 sections
│
├── enterprise_fizzbuzz/             # Clean Architecture package root
│   ├── __init__.py
│   ├── __main__.py                  # python -m enterprise_fizzbuzz support
│   │
│   ├── domain/                      # THE INNER CIRCLE (no outward dependencies)
│   │   ├── __init__.py
│   │   ├── models.py                # Dataclasses, enums, and domain models
│   │   ├── exceptions.py            # Custom exception hierarchy (77 exception classes)
│   │   └── interfaces.py            # Abstract base classes for everything
│   │
│   ├── application/                 # USE CASES (depends only on domain)
│   │   ├── __init__.py
│   │   ├── fizzbuzz_service.py      # Service orchestration with Builder pattern
│   │   ├── factory.py               # Abstract Factory + Caching Decorator
│   │   └── ports.py                 # Repository & Unit of Work abstract contracts (hexagonal ports)
│   │
│   └── infrastructure/              # ADAPTERS & FRAMEWORKS (the outer ring)
│       ├── __init__.py
│       ├── adapters/                # Port adapters (future expansion surface)
│       │   └── __init__.py
│       ├── config.py                # Singleton configuration manager with env var overrides
│       ├── formatters.py            # Four output formatters
│       ├── middleware.py            # Composable middleware pipeline
│       ├── observers.py            # Thread-safe event bus with statistics tracking
│       ├── plugins.py               # Plugin registry with auto-registration
│       ├── rules_engine.py          # Four evaluation strategies
│       ├── ml_engine.py             # From-scratch neural network (pure stdlib)
│       ├── blockchain.py            # Immutable audit ledger with proof-of-work
│       ├── circuit_breaker.py       # Circuit breaker with exponential backoff
│       ├── tracing.py               # OpenTelemetry-inspired distributed tracing (from scratch)
│       ├── auth.py                  # RBAC with HMAC-SHA256 token engine and 47-field access denials
│       ├── i18n.py                  # Internationalization subsystem with locale fallback chains
│       ├── event_sourcing.py        # Event Sourcing + CQRS with command/query buses (~1,500 lines)
│       ├── chaos.py                 # Chaos Engineering / Fault Injection Framework (~1,200 lines)
│       ├── feature_flags.py         # Feature Flags / Progressive Rollout with dependency DAG (~880 lines)
│       ├── sla.py                   # SLA Monitoring with PagerDuty-style alerting (~1,400 lines)
│       ├── cache.py                 # In-Memory Caching with MESI coherence and eulogies (~1,100 lines)
│       ├── migrations.py            # Database Migration Framework for ephemeral RAM schemas (~1,160 lines)
│       └── persistence/             # Repository Pattern with three storage backends (~700 lines)
│           ├── __init__.py           # Factory + public API re-exports
│           ├── in_memory.py          # In-memory repository (Python dicts, because simplicity is a sin)
│           ├── sqlite.py             # SQLite repository (a real database, for once)
│           └── filesystem.py         # Filesystem repository (JSON files on disk, artisanally serialized)
│
├── *.py (root)                      # Backward-compatible re-export stubs
│   │                                  (each file re-exports from the package so
│   │                                   existing imports continue to work)
│   ├── models.py → enterprise_fizzbuzz.domain.models
│   ├── exceptions.py → enterprise_fizzbuzz.domain.exceptions
│   ├── interfaces.py → enterprise_fizzbuzz.domain.interfaces
│   ├── config.py → enterprise_fizzbuzz.infrastructure.config
│   ├── ... (one stub per original module)
│   └── tracing.py → enterprise_fizzbuzz.infrastructure.tracing
│
├── locales/                         # Proprietary .fizztranslation locale files
│   ├── en.fizztranslation           # English (base locale)
│   ├── de.fizztranslation           # German (Deutsch)
│   ├── fr.fizztranslation           # French (Français)
│   ├── ja.fizztranslation           # Japanese (日本語)
│   ├── tlh.fizztranslation          # Klingon (tlhIngan Hol)
│   ├── sjn.fizztranslation          # Sindarin (Edhellen) — ISO 639-3
│   └── qya.fizztranslation          # Quenya (Eldarin) — ISO 639-3
│
└── tests/
    ├── test_fizzbuzz.py             # 66 comprehensive tests
    ├── test_circuit_breaker.py      # 66 circuit breaker tests
    ├── test_i18n.py                 # 123 internationalization tests
    ├── test_auth.py                 # 86 RBAC & authentication tests
    ├── test_tracing.py              # 68 distributed tracing tests
    ├── test_event_sourcing.py       # 98 event sourcing & CQRS tests
    ├── test_chaos.py                # 69 chaos engineering & fault injection tests
    ├── test_feature_flags.py        # 69 feature flag & progressive rollout tests
    ├── test_sla.py                  # 96 SLA monitoring & alerting tests
    ├── test_cache.py                # 60 caching & eviction policy tests
    ├── test_migrations.py           # 56 database migration & schema management tests
    ├── test_repository.py           # 40 repository pattern & unit of work tests (3 backends)
    └── test_architecture.py         # AST-based import linter enforcing the Dependency Rule
```

### Backward-Compatible Re-Export Stubs

Every original root-level module (`models.py`, `exceptions.py`, `config.py`, etc.) has been replaced with a two-line re-export stub that imports everything from the corresponding package module. This means all existing imports (`from models import FizzBuzzResult`) continue to work without modification. The stubs add zero functionality and exist solely to prevent the restructuring from breaking anything -- the architectural equivalent of moving furniture while the occupants are asleep.

### AST-Based Architecture Test

The `tests/test_architecture.py` module uses Python's `ast` parser to statically analyze every import statement in the domain layer and verify that no domain module imports from the application or infrastructure layers. If `models.py` ever tries to import from `config.py`, this test will catch it, fail loudly, and shame it publicly. The Dependency Rule is not a suggestion.

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| Clean Architecture / Hexagonal Architecture | `enterprise_fizzbuzz/` | Because a flat directory of 24 Python files lacked the concentric dependency rings necessary to convey architectural seriousness. Zero features added. Three layers added. The Dependency Rule is enforced by an AST-based import linter, because trust is not an architectural strategy |
| Dependency Rule | `tests/test_architecture.py` | Domain depends on nothing. Application depends on domain. Infrastructure depends on both. Violations are caught at test time via static AST analysis, not at runtime via disappointment |
| Backward-Compatible Facade | Root-level `*.py` stubs | Two-line re-export modules that preserve all existing imports while the real code lives in the package. The architectural equivalent of a mail forwarding service |
| Abstract Factory | `factory.py` | Creating rules is *complex* |
| Strategy | `rules_engine.py` | Four interchangeable evaluation algorithms |
| Chain of Responsibility | `rules_engine.py` | Because one Strategy wasn't enough |
| Neural Network | `ml_engine.py` | Because modulo was too deterministic |
| Observer | `observers.py` | FizzBuzz events must be monitored in real-time |
| Middleware Pipeline | `middleware.py` | Cross-cutting concerns for modulo operations |
| Singleton | `config.py`, `i18n.py` | Only one configuration (and one locale manager) shall rule them all |
| Builder | `fizzbuzz_service.py` | Fluent API for assembling the FizzBuzz service |
| Decorator | `factory.py` | Caching layer around rule factories |
| Plugin System | `plugins.py` | Third-party FizzBuzz rule extensions |
| Circuit Breaker | `circuit_breaker.py` | Protecting modulo operations from cascading failure |
| Sliding Window | `circuit_breaker.py` | Recent failure tracking for trip decisions |
| Exponential Backoff | `circuit_breaker.py` | Giving arithmetic time to recover from outages |
| State Machine | `circuit_breaker.py`, `i18n.py` | Three-state lifecycle for fault tolerance; parser state machine for .fizztranslation files |
| Dependency Injection | Everywhere | Constructor injection, because globals are evil |
| Custom File Format Parser | `i18n.py` | A bespoke `.fizztranslation` format, because JSON, YAML, and TOML lacked sufficient enterprise gravitas |
| Fallback Chain | `i18n.py` | Locale resolution via linked-list traversal with cycle detection, because one language is never enough |
| Pluralization Engine | `i18n.py` | CLDR-inspired plural rule evaluator supporting five grammatical traditions, because "1 Fizzes" is unconscionable |
| Internationalization | `i18n.py`, `locales/` | Seven-language locale support with fallback chains, because "Fizz" is not globally understood (nor in the Undying Lands) |
| Distributed Tracing | `tracing.py` | OpenTelemetry-inspired span trees, because you need a flame graph to debug `n % 3` |
| Context Propagation | `tracing.py` | Thread-local span stacks for automatic parent-child relationships across the middleware pipeline |
| Fluent Builder (Spans) | `tracing.py` | `SpanBuilder` with chainable `.with_attribute()` and context manager support, because `Span()` was too direct |
| Role-Based Access Control | `auth.py` | NIST-grade RBAC with five-tier role hierarchy, because `n % 3` is a privilege, not a right |
| Token Engine | `auth.py` | HMAC-SHA256 signed tokens in a format that is legally distinct from JWT |
| Permission Parser | `auth.py` | Resource:range:action permission strings, because `if user == "admin"` lacked enterprise gravitas |
| Event Sourcing | `event_sourcing.py` | Append-only event log of every modulo operation, because state is ephemeral but history is forever |
| CQRS | `event_sourcing.py` | Separate command and query models, because reading and writing FizzBuzz results are fundamentally different responsibilities |
| Command Bus | `event_sourcing.py` | Mediator-pattern command dispatch, because `evaluate(15)` needed an abstraction layer |
| Query Bus | `event_sourcing.py` | Mediator-pattern query dispatch, because `get_results()` also needed an abstraction layer |
| Temporal Query | `event_sourcing.py` | Reconstruct FizzBuzz state at any point in history, for when auditors ask "what was the Fizz count after event 42?" |
| Event Upcasting | `event_sourcing.py` | Schema migration chain for domain events, because even FizzBuzz event schemas evolve |
| Snapshot / Memento | `event_sourcing.py` | Periodic state snapshots to accelerate event replay, because replaying millions of FizzBuzz events would be unconscionable |
| Projection / Materialized View | `event_sourcing.py` | Read-side projections rebuilt from the event stream, because querying raw events is for amateurs |
| Chaos Engineering | `chaos.py` | Deliberate fault injection to prove that FizzBuzz can survive the apocalypse (or at least a corrupted modulo) |
| Fault Injection | `chaos.py` | Five artisanal failure modes, hand-crafted with love and malice, each with configurable severity |
| Game Day | `chaos.py` | Structured multi-phase chaos experiments with escalating severity, because "let's break things on purpose" deserves a framework |
| Feature Flags | `feature_flags.py` | Boolean, Percentage, and Targeting flag types with full lifecycle management, because `if USE_FIZZ:` was insufficiently configurable |
| Rollout Strategy | `feature_flags.py` | SHA-256 deterministic hash-based percentage rollout, because non-deterministic FizzBuzz feature toggles would be an affront to engineering principles |
| Dependency DAG | `feature_flags.py` | Kahn's topological sort with cycle detection for flag dependencies, because circular feature flag dependencies deserve a graph-theoretic response |
| Targeting Rules | `feature_flags.py` | Rule-based flag evaluation (prime, even, odd, range, modulo), because deciding whether to show "Fizz" for the number 7 requires a formal targeting engine |
| SLA Monitoring | `sla.py` | Three-pillar SLO tracking (latency, accuracy, availability) with compliance dashboards, because FizzBuzz without contractual guarantees is just a hobby |
| Error Budgets | `sla.py` | Rolling-window budget consumption and burn rate calculation, because every failed modulo is a finite and precious resource |
| Escalation Policy | `sla.py` | Four-tier PagerDuty-style escalation chain, because when `n % 3` violates its SLA, someone must be held accountable (it's always Bob) |
| On-Call Rotation | `sla.py` | Modulo-based engineer rotation across a team of one, because even the on-call schedule uses modulo arithmetic -- and the irony is not lost on us |
| Caching | `cache.py` | In-memory result memoization for an operation that takes zero nanoseconds, because premature optimization is the root of all enterprise architecture |
| MESI Coherence | `cache.py` | Modified/Exclusive/Shared/Invalid state machine for a single-process cache with zero concurrent readers, because protocol compliance is non-negotiable |
| Eviction Policies | `cache.py` | Four interchangeable eviction strategies (LRU, LFU, FIFO, DramaticRandom), because choosing which cached modulo result to discard is a problem that demands a Strategy Pattern |
| Cache Eulogies | `cache.py` | Template-method satirical obituary generation for evicted cache entries, because no data should be garbage-collected without a proper farewell |
| Database Migrations | `migrations.py` | Forward/reverse schema migrations for in-memory dicts that will be garbage-collected when the process exits, because ephemeral data deserves a DDL lifecycle |
| Schema Management | `migrations.py` | Full DDL/DML interface (CREATE TABLE, ALTER TABLE, DROP TABLE) for Python dicts, with fake SQL logging for maximum enterprise cosplay |
| Seed Data | `migrations.py` | The FizzBuzz engine seeds the FizzBuzz database with FizzBuzz results -- the ouroboros of enterprise architecture |
| Repository Pattern | `persistence/` | Abstract data access layer with three interchangeable backends, because storing FizzBuzz results in a plain list was architecturally unconscionable |
| Unit of Work | `persistence/`, `ports.py` | Transactional boundaries around repository operations with automatic rollback, because even FizzBuzz results deserve ACID guarantees (well, ACI at least) |
| Ports & Adapters (Persistence) | `ports.py`, `persistence/` | Hexagonal architecture ports for repository and UoW contracts, with three concrete adapter implementations -- ensuring the domain remains blissfully ignorant of whether its results are stored in RAM, SQLite, or artisanal JSON files |

## Features

- **Multiple Evaluation Strategies** - Standard, Chain of Responsibility, Parallel Async, or Machine Learning
- **Four Output Formats** - Plain Text, JSON, XML, CSV
- **YAML Configuration** - Externalized, validated, with environment variable overrides
- **Middleware Pipeline** - Validation, timing (nanosecond precision), and logging
- **Event-Driven Architecture** - Real-time FizzBuzz detection events with statistics
- **Plugin System** - Extend with custom divisibility rules via decorators
- **Async/Await** - Run FizzBuzz asynchronously, because blocking is for amateurs
- **Machine Learning Engine** - From-scratch MLP neural network trained via backpropagation to learn `n % 3 == 0`
- **Circuit Breaker** - Fault-tolerant evaluation with exponential backoff, sliding windows, and an ASCII status dashboard
- **Internationalization (i18n)** - Full locale support across 7 languages (including Klingon and two dialects of Elvish), with a proprietary `.fizztranslation` file format, locale fallback chains, and a pluralization engine. DEI-compliant for the Undying Lands market segment
- **Distributed Tracing** - OpenTelemetry-inspired span trees with W3C Trace Context IDs, ASCII waterfall visualization, JSON export, and P95/P99 latency percentiles -- for when you need to know exactly which middleware layer added 0.3 microseconds to your modulo operation
- **Role-Based Access Control (RBAC)** - Five-tier role hierarchy from ANONYMOUS to FIZZBUZZ_SUPERUSER, HMAC-SHA256 token authentication, permission-based number range access, and a sacred 47-field access denied JSON response that includes whether the forbidden number is prime, a motivational quote, and a legal disclaimer
- **Event Sourcing / CQRS** - Append-only event store with command/query bus separation, temporal queries, event upcasting, periodic snapshots, and materialized projections -- because the ability to reconstruct FizzBuzz state at any point in history is a compliance requirement, not a luxury
- **Chaos Engineering** - A Chaos Monkey that deliberately corrupts results, injects latency, throws exceptions, sabotages the rule engine, and manipulates ML confidence scores -- with five severity levels ranging from "Gentle Breeze" to "Apocalypse," pre-built Game Day scenarios, and a satirical post-mortem incident report generator that would make any SRE weep with pride
- **Feature Flags / Progressive Rollout** - Boolean, Percentage, and Targeting flag types with SHA-256 deterministic rollout, Kahn's topological sort for dependency resolution, full lifecycle management (CREATED -> ACTIVE -> DEPRECATED -> ARCHIVED), FlagMiddleware integration, and an ASCII evaluation summary renderer -- because toggling FizzBuzz rules on and off clearly requires the same infrastructure Netflix uses to manage feature rollouts across 200 million subscribers
- **SLA Monitoring / PagerDuty-Style Alerting** - Three-pillar SLO tracking (latency, accuracy, availability) with error budgets, burn rate alerts, a four-tier escalation policy, and an on-call rotation that uses modulo arithmetic to determine which engineer from a team of one (1) person is currently responsible -- complete with an ASCII dashboard, ground-truth accuracy verification, and the unshakeable certainty that Bob McFizzington will always be the one who gets paged
- **In-Memory Caching with Cache Invalidation Protocol** - Four eviction policies (LRU, LFU, FIFO, DramaticRandom), MESI cache coherence state tracking (pointless but thorough), satirical eulogies for evicted entries, a cache warming system that pre-populates results (thereby defeating the entire purpose of caching), TTL-based expiration, thread-safe operations, and an ASCII statistics dashboard -- because the result of `15 % 3` might change between invocations, and we need to be prepared
- **Database Migration Framework** - Five reversible migrations for in-memory schema management, with dependency tracking, fake SQL logging, ASCII ER diagram visualization, a migration status dashboard, and seed data generation that uses the FizzBuzz engine to populate the FizzBuzz database (the ouroboros pattern) -- all for data structures that exist exclusively in RAM and will vanish the moment you press Ctrl+C. This is by design.
- **Repository Pattern / Unit of Work** - Three interchangeable persistence backends (in-memory, SQLite, filesystem) with transactional Unit of Work semantics, abstract hexagonal ports, and automatic rollback -- because FizzBuzz results that aren't durably persisted with ACID guarantees are just numbers shouted into the void
- **Custom Exception Hierarchy** - 81 exception classes for every conceivable FizzBuzz failure mode
- **Session Management** - Context managers for FizzBuzz session lifecycle
- **Nanosecond Timing** - Performance metrics for your modulo operations

## Quick Start

```bash
# Basic run
python main.py

# Custom range with JSON output
python main.py --range 1 50 --format json

# Chain of Responsibility strategy with XML
python main.py --strategy chain_of_responsibility --format xml --no-banner

# Async execution with verbose event logging
python main.py --async --verbose

# Machine Learning strategy (trains a neural network, then runs inference)
python main.py --strategy machine_learning --range 1 20 --debug

# CSV output, no frills
python main.py --range 1 100 --format csv --no-banner --no-summary

# Fault-tolerant FizzBuzz with circuit breaker protection
python main.py --circuit-breaker --circuit-status --verbose

# Full enterprise stack: ML + circuit breaker + status dashboard
python main.py --strategy machine_learning --circuit-breaker --circuit-status --range 1 20

# FizzBuzz auf Deutsch (German locale)
python main.py --locale de --range 1 20

# FizzBuzz en francais (French locale)
python main.py --locale fr --format json

# FizzBuzz in Klingon, because global reach means *galactic* reach
python main.py --locale tlh --range 1 15

# Japanese locale with async execution
python main.py --locale ja --async --range 1 50

# FizzBuzz in Sindarin (Grey-elven), for the Undying Lands market segment
python main.py --locale sjn --range 1 15

# FizzBuzz in Quenya (High-elven), because Tolkien would have wanted this
python main.py --locale qya --range 1 20 --format json

# List all available locales and their metadata
python main.py --list-locales

# Distributed tracing with ASCII waterfall visualization
python main.py --trace --range 1 15

# Export trace data as JSON for your non-existent Jaeger instance
python main.py --trace-json --range 1 5

# Full observability stack: tracing + circuit breaker + ML
python main.py --trace --circuit-breaker --strategy machine_learning --range 1 20

# RBAC: Run as a FIZZBUZZ_SUPERUSER (trust-mode, full access)
python main.py --user alice --role FIZZBUZZ_SUPERUSER --range 1 100

# RBAC: Run as a lowly FIZZ_READER (can only evaluate 1-50)
python main.py --user intern --role FIZZ_READER --range 1 50

# RBAC: Run as ANONYMOUS and watch the access denials roll in
python main.py --user nobody --role ANONYMOUS --range 1 20

# RBAC: Token-based authentication (the cryptographically serious way)
python main.py --token "EFP.<payload>.<signature>" --range 1 100

# Full stack: RBAC + tracing + circuit breaker + ML (peak enterprise)
python main.py --user alice --role FIZZBUZZ_SUPERUSER --trace --circuit-breaker --strategy machine_learning --range 1 20

# Event Sourcing: append-only audit log of every FizzBuzz decision
python main.py --event-sourcing --range 1 20

# Event Sourcing with replay: rebuild projections from the event stream
python main.py --event-sourcing --replay --range 1 30

# Temporal query: reconstruct FizzBuzz state as it existed at event #42
python main.py --event-sourcing --temporal-query 42 --range 1 50

# Full compliance stack: event sourcing + RBAC + tracing (peak audit)
python main.py --event-sourcing --user alice --role FIZZBUZZ_SUPERUSER --trace --range 1 20

# Chaos Engineering: unleash the Chaos Monkey (default severity: level 1)
python main.py --chaos --range 1 30

# Maximum chaos: level 5 apocalypse with post-mortem incident report
python main.py --chaos --chaos-level 5 --post-mortem --range 1 50

# Game Day: run the "modulo_meltdown" scenario (escalating rule engine failures)
python main.py --gameday modulo_meltdown --range 1 30

# Game Day: total chaos with all fault types at maximum severity
python main.py --gameday total_chaos --post-mortem --range 1 20

# Chaos + circuit breaker: watch the monkey trip the breaker
python main.py --chaos --chaos-level 3 --circuit-breaker --circuit-status --range 1 30

# Full resilience stack: chaos + circuit breaker + ML + tracing (peak entropy)
python main.py --chaos --chaos-level 4 --circuit-breaker --strategy machine_learning --trace --post-mortem --range 1 20

# Feature flags: enable progressive rollout with default flag configuration
python main.py --feature-flags --range 1 30

# Feature flags: override a flag to enable the experimental Wuzz rule (divisible by 7)
python main.py --feature-flags --flag wuzz_rule_experimental=true --range 1 30

# Feature flags: disable the Fizz rule and see what happens (spoiler: no Fizz)
python main.py --feature-flags --flag fizz_rule_enabled=false --range 1 20

# Feature flags: list all registered flags and their configuration
python main.py --feature-flags --list-flags

# Feature flags: progressive rollout at 50% with circuit breaker (peak toggle)
python main.py --feature-flags --circuit-breaker --circuit-status --range 1 50

# Full enterprise stack: feature flags + RBAC + tracing + chaos (peak configuration)
python main.py --feature-flags --user alice --role FIZZBUZZ_SUPERUSER --trace --chaos --range 1 20

# SLA Monitoring: track latency, accuracy, and availability SLOs
python main.py --sla --range 1 50

# SLA Monitoring with dashboard: see error budgets and compliance ratios
python main.py --sla --sla-dashboard --range 1 100

# Quick on-call status: who's responsible when FizzBuzz goes down? (spoiler: Bob)
python main.py --on-call

# SLA + chaos: watch the error budget burn as the monkey wreaks havoc
python main.py --sla --sla-dashboard --chaos --chaos-level 3 --range 1 50

# Full reliability stack: SLA + circuit breaker + chaos + tracing (peak SRE)
python main.py --sla --sla-dashboard --circuit-breaker --circuit-status --chaos --chaos-level 2 --trace --range 1 30

# Caching: enable the in-memory cache with default LRU eviction
python main.py --cache --range 1 50

# Caching with statistics dashboard: see hit rates and eviction counts
python main.py --cache --cache-stats --range 1 100

# Caching with LFU eviction and a max cache size of 32
python main.py --cache --cache-policy lfu --cache-size 32 --cache-stats --range 1 100

# Caching with DramaticRandom eviction: entries are evicted at random, with eulogies
python main.py --cache --cache-policy dramatic_random --cache-stats --range 1 50

# Cache warming: pre-populate the cache before execution (defeats the purpose of caching)
python main.py --cache --cache-warm --cache-stats --range 1 100

# Full caching stack: LRU + warming + stats + circuit breaker (peak memoization)
python main.py --cache --cache-warm --cache-stats --circuit-breaker --circuit-status --range 1 50

# Caching + chaos: watch the monkey corrupt cached results
python main.py --cache --cache-stats --chaos --chaos-level 3 --range 1 30

# Full enterprise stack: caching + SLA + tracing + RBAC (peak over-engineering)
python main.py --cache --cache-stats --sla --sla-dashboard --trace --user alice --role FIZZBUZZ_SUPERUSER --range 1 20

# Repository Pattern: persist results in-memory (the default, because persistence is aspirational)
python main.py --repository memory --range 1 20

# Repository Pattern: persist results to SQLite (an actual database, for once)
python main.py --repository sqlite --db-path fizzbuzz.db --range 1 50

# Repository Pattern: persist results as artisanal JSON files on disk
python main.py --repository filesystem --results-dir ./fizzbuzz_results --range 1 30

# Repository + full stack: SQLite persistence with tracing, caching, and RBAC
python main.py --repository sqlite --db-path fizzbuzz.db --trace --cache --user alice --role FIZZBUZZ_SUPERUSER --range 1 20

# Database Migrations: apply all migrations to the in-memory schema (it won't persist)
python main.py --migrate --range 1 20

# Migration status dashboard: see which migrations have been applied (to RAM)
python main.py --migrate --migrate-status --range 1 20

# Seed data: use the FizzBuzz engine to populate the FizzBuzz database (the ouroboros)
python main.py --migrate --migrate-seed --range 1 50

# Rollback: undo the last N migrations (default: 1)
python main.py --migrate --migrate-rollback 3 --range 1 20

# Full migration stack: apply, seed, and display status dashboard
python main.py --migrate --migrate-seed --migrate-status --range 1 30

# Peak enterprise: migrations + caching + SLA + tracing + RBAC (the schema will still vanish on exit)
python main.py --migrate --migrate-seed --migrate-status --cache --sla --trace --user alice --role FIZZBUZZ_SUPERUSER --range 1 20
```

## CLI Options

```
--range START END     Numeric range to evaluate (default: 1-100)
--format FORMAT       Output format: plain, json, xml, csv
--strategy STRATEGY   Evaluation strategy: standard, chain_of_responsibility, parallel_async, machine_learning
--config PATH         Path to YAML configuration file
--verbose, -v         Enable verbose event logging
--debug               Enable debug-level logging
--async               Use asynchronous evaluation engine
--no-banner           Suppress the startup banner
--no-summary          Suppress the session summary
--metadata            Include metadata in output (JSON only)
--blockchain          Enable blockchain-based immutable audit ledger
--mining-difficulty N Proof-of-work difficulty (default: 2)
--locale LOCALE       Locale for internationalized output (en, de, fr, ja, tlh, sjn, qya)
--list-locales        Display available locales and exit
--circuit-breaker     Enable circuit breaker with exponential backoff
--circuit-status      Display circuit breaker status dashboard after execution
--event-sourcing      Enable Event Sourcing with CQRS for append-only audit logging
--replay              Replay all events from the event store to rebuild projections
--temporal-query SEQ  Reconstruct FizzBuzz state at a specific event sequence number
--trace               Enable distributed tracing with ASCII waterfall output
--trace-json          Export trace data as JSON (for integration with nothing)
--user USERNAME       Authenticate as the specified user (trust-mode, no token required)
--role ROLE           Assign RBAC role: ANONYMOUS, FIZZ_READER, BUZZ_ADMIN, NUMBER_AUDITOR, FIZZBUZZ_SUPERUSER
--token TOKEN         Authenticate using an Enterprise FizzBuzz Platform HMAC-SHA256 token
--chaos               Enable Chaos Engineering fault injection (the monkey awakens)
--chaos-level N       Chaos severity level 1-5 (1=gentle breeze, 5=apocalypse)
--gameday SCENARIO    Run a Game Day chaos scenario (modulo_meltdown, confidence_crisis, slow_burn, total_chaos)
--post-mortem         Generate a satirical post-mortem incident report after chaos execution
--feature-flags      Enable the Feature Flag / Progressive Rollout subsystem
--flag NAME=VALUE    Override a feature flag (e.g. --flag wuzz_rule_experimental=true)
--list-flags         Display all registered feature flags and exit
--sla                Enable SLA Monitoring with PagerDuty-style alerting
--sla-dashboard      Display the SLA monitoring dashboard after execution
--on-call            Display the current on-call status and escalation chain
--cache              Enable the in-memory caching layer for FizzBuzz evaluation results
--cache-policy POLICY  Cache eviction policy: lru, lfu, fifo, dramatic_random (default: lru)
--cache-size N       Maximum number of cache entries (default: 1024)
--cache-stats        Display the cache statistics dashboard after execution
--cache-warm         Pre-populate the cache before execution (defeats the purpose of caching)
--repository BACKEND Repository backend: memory, sqlite, filesystem (default: memory)
--db-path PATH       Path to SQLite database file (only with --repository sqlite)
--results-dir PATH   Path to results directory (only with --repository filesystem)
--migrate            Apply all pending database migrations to the in-memory schema (it won't persist)
--migrate-status     Display the migration status dashboard for the ephemeral database
--migrate-rollback N Rollback the last N migrations (default: 1). Undo what was never permanent
--migrate-seed       Generate FizzBuzz seed data using the FizzBuzz engine (the ouroboros)
```

## Environment Variables

All configuration can be overridden via environment variables prefixed with `EFP_`:

```bash
EFP_RANGE_START=1
EFP_RANGE_END=100
EFP_OUTPUT_FORMAT=json
EFP_EVALUATION_STRATEGY=parallel_async
EFP_LOG_LEVEL=DEBUG
EFP_CIRCUIT_BREAKER_ENABLED=true
EFP_TRACING_ENABLED=true
EFP_LOCALE=tlh
EFP_RBAC_SECRET=my-very-secret-fizzbuzz-signing-key
EFP_EVENT_SOURCING_ENABLED=true
EFP_EVENT_SOURCING_SNAPSHOT_INTERVAL=10
EFP_CHAOS_ENABLED=true
EFP_CHAOS_LEVEL=3
EFP_CHAOS_SEED=42
```

## Machine Learning Architecture

The `machine_learning` strategy replaces the `%` operator with a from-scratch **Multi-Layer Perceptron** neural network, implemented in pure Python stdlib (no NumPy, no scikit-learn, no PyTorch).

```
                  +-----------+
  number n -----> | Cyclical  | ---> [sin(2*pi*n/d), cos(2*pi*n/d)]
                  | Encoding  |              |
                  +-----------+              v
                                    +------------------+
                                    | Dense(16, sigmoid)|  <-- Hidden Layer (32 weights + 16 biases)
                                    +------------------+
                                             |
                                             v
                                    +------------------+
                                    | Dense(1, sigmoid) |  <-- Output Layer (16 weights + 1 bias)
                                    +------------------+
                                             |
                                             v
                                      P(divisible) in [0, 1]
```

**One network per rule.** Each binary classifier learns whether `n` is divisible by its rule's divisor.

| Spec | Value |
|------|-------|
| Parameters per model | 65 |
| Total parameters (Fizz + Buzz) | 130 |
| Training samples | 200 per rule |
| Feature encoding | Cyclical (sin/cos) |
| Loss function | Binary Cross-Entropy |
| Optimizer | SGD with LR decay (0.998/epoch) |
| Weight initialization | Xavier/Glorot |
| Convergence | Early stopping (patience=10) |
| Accuracy | 100% (verified against StandardRuleEngine for 1-100) |
| Training time | ~150ms |
| Dependencies | None |

The cyclical feature encoding maps the periodic divisibility pattern onto a 2D unit circle, making the problem trivially separable. This is, of course, the most complex possible way to check if `n % 3 == 0`.

## Circuit Breaker Architecture

The circuit breaker protects the FizzBuzz evaluation pipeline from cascading failures using a three-state machine with exponential backoff. Because when `n % 3` starts throwing exceptions, you need enterprise-grade fault isolation -- not a `try/except`.

```
                    success_count >= threshold
               +----------------------------------+
               |                                  |
               v                                  |
        +============+    failure_count    +==============+
        |            |    >= threshold     |              |
   ---->|   CLOSED   |------------------->|     OPEN     |
        |            |                     |              |
        +============+                     +==============+
               ^                                  |
               |                                  | backoff
               |                                  | timeout
               |          +=============+         | expires
               |          |             |<--------+
               +----------|  HALF_OPEN  |
                success   |             |----+
                          +=============+    |
                                             | any failure
                                             | (re-opens with
                                             |  increased backoff)
                                             v
                                       +==============+
                                       |     OPEN     |
                                       | (attempt N+1)|
                                       +==============+
```

**Thread-safe.** All state mutations are protected by a reentrant lock for concurrent FizzBuzz workloads.

| Spec | Value |
|------|-------|
| States | 3 (CLOSED, OPEN, HALF_OPEN) |
| Failure threshold | 5 (configurable) |
| Success threshold | 3 (configurable) |
| Sliding window size | 10 entries |
| Backoff formula | `min(base * 2^attempt, max)` |
| Backoff base | 1,000 ms |
| Backoff cap | 60,000 ms |
| Call timeout | 5,000 ms |
| ML confidence threshold | 0.7 (proactive degradation detection) |
| Custom exceptions | 3 (CircuitOpenError, CircuitBreakerTimeoutError, DownstreamFizzBuzzDegradationError) |
| SLA target | 99.999% FizzBuzz availability (five nines of Fizz) |
| Thread safety | Full (reentrant lock) |
| Dashboard | ASCII-art status visualization |

The circuit breaker also monitors ML confidence scores from the neural network strategy. If confidence drops below the threshold, it flags a "degraded FizzBuzz" condition -- because technically correct modulo results delivered without mathematical conviction are a reliability concern.

## RBAC Architecture

The Role-Based Access Control subsystem implements a comprehensive, NIST-inspired authorization framework for controlling who can evaluate what numbers. Because the ability to compute `n % 3` is a privilege, not a right.

**Key components:**
- **RoleRegistry** - Five-tier role hierarchy with permission inheritance
- **PermissionParser** - Parses `resource:range_spec:action` permission strings with wildcard, numeric range, and named class (fizz/buzz/fizzbuzz) matching
- **FizzBuzzTokenEngine** - HMAC-SHA256 signed token authentication (legally distinct from JWT)
- **AccessDeniedResponseBuilder** - Constructs the sacred 47-field access denied JSON response
- **AuthorizationMiddleware** - Intercepts every evaluation in the middleware pipeline at priority -10

### Role Hierarchy

```
    ANONYMOUS                     Can read the number 1. That's it.
      +-- FIZZ_READER             Can read multiples of 3 and evaluate 1-50.
            +-- BUZZ_ADMIN            Can also read/configure multiples of 5 and evaluate 1-100.
            |     +-- FIZZBUZZ_SUPERUSER  Unrestricted access. The chosen one.
            +-- NUMBER_AUDITOR        Can audit and read all numbers, but not evaluate.
```

### Permissions

Permissions follow the format `resource:range_spec:action`:

| Role | Permissions | What It Means |
|------|------------|---------------|
| `ANONYMOUS` | `numbers:1:read` | You can look at the number 1. Congratulations. |
| `FIZZ_READER` | `numbers:fizz:read`, `numbers:1-50:evaluate` | You've earned the right to evaluate numbers up to 50. Don't let it go to your head. |
| `BUZZ_ADMIN` | `numbers:buzz:read`, `numbers:buzz:configure`, `numbers:1-100:evaluate` | The full 1-100 range. Middle management energy. |
| `FIZZBUZZ_SUPERUSER` | `numbers:*:evaluate`, `numbers:*:read`, `numbers:*:configure` | Unlimited power. Use it wisely. (You won't.) |
| `NUMBER_AUDITOR` | `numbers:*:audit`, `numbers:*:read` | You can watch everyone else FizzBuzz, but you cannot FizzBuzz yourself. Compliance in a nutshell. |

### The Sacred 47-Field Access Denied Response

When authorization fails, the platform does not simply return a `403 Forbidden`. That would be *pedestrian*. Instead, it constructs a lovingly crafted JSON response body containing exactly **47 fields**, including but not limited to:

- Whether the forbidden number is prime
- The number in binary and hexadecimal
- Whether it *would have been* Fizz, Buzz, or FizzBuzz (adding insult to injury)
- A completely meaningless "trust score"
- A motivational quote (e.g., *"Every 'Access Denied' is just a 'Not Yet' in disguise."*)
- A legal disclaimer absolving the platform of emotional distress
- An auto-filed incident ticket (severity: P4 - Cosmetic)
- The recommended role upgrade path
- A 72-hour SLA response time
- Content-Type: `application/fizzbuzz-denial+json`

The 47-field requirement is non-negotiable. It was established by the FizzBuzz Security Council in a meeting that ran 47 minutes over schedule.

### Token Format

Tokens follow the format `EFP.<base64url_payload>.<hmac_sha256_hex>`, which is suspiciously similar to JWT but legally distinct enough to avoid licensing fees.

| Field | Description |
|-------|-------------|
| `sub` | Subject (username) |
| `role` | FizzBuzz role name |
| `iat` | Issued at (Unix timestamp) |
| `exp` | Expiration (Unix timestamp) |
| `jti` | Token ID (UUID) |
| `iss` | Issuer |
| `fizz_clearance_level` | Clearance for Fizz operations (0-5) |
| `buzz_clearance_level` | Clearance for Buzz operations (0-5) |
| `favorite_prime` | The user's favorite prime number (assigned at random, as is tradition) |

## Event Sourcing / CQRS Architecture

The Event Sourcing subsystem maintains a complete, append-only, temporally queryable audit log of every FizzBuzz evaluation -- because simply returning "Fizz" is not enough when SOX Section 404 demands a full paper trail of every modulo operation ever performed. The CQRS layer separates the write side (commands) from the read side (queries), ensuring that the act of evaluating FizzBuzz and the act of reading the results are architecturally, philosophically, and spiritually decoupled.

```
    WRITE SIDE (Command)                          READ SIDE (Query)
    ====================                          ==================

    +-------------+                               +-------------+
    |   CLI /     |                               |   CLI /     |
    |   Service   |                               |   Service   |
    +------+------+                               +------+------+
           |                                             ^
           v                                             |
    +------+------+                               +------+------+
    | CommandBus  |                               |  QueryBus   |
    | (Mediator)  |                               |  (Mediator)  |
    +------+------+                               +------+------+
           |                                             ^
           v                                             |
    +------+--------+                             +------+--------+
    | CommandHandler |                            | QueryHandler  |
    | (Evaluate,     |                            | (Results,     |
    |  Replay)       |                            |  Statistics,  |
    +------+---------+                            |  Temporal)    |
           |                                      +------+--------+
           v                                             ^
    +------+------+    subscribe     +----------+        |
    | EventStore  |---------------->| Projection|--------+
    | (append-    |                  | Engine    |
    |  only log)  |                  +----------+
    +------+------+
           |
           v  (every N events)
    +------+------+
    | Snapshot    |
    | Store       |
    +-------------+
```

**Key components:**
- **EventStore** - Thread-safe, append-only, sequenced event log. The single source of truth. Clearing it would trigger a compliance investigation
- **CommandBus / QueryBus** - Mediator-pattern dispatchers for write and read operations
- **EvaluateNumberCommandHandler** - Orchestrates evaluation and emits 5+ domain events per number
- **TemporalQueryEngine** - Reconstructs system state at any historical event sequence number
- **EventUpcaster** - Version migration chain for schema evolution (because even FizzBuzz schemas evolve)
- **SnapshotStore** - Periodic state snapshots for accelerated replay
- **ProjectionEngine** - Materializes read models from the event stream
- **EventSourcingMiddleware** - Integrates with the middleware pipeline at priority 5

### Domain Events

Every number evaluation emits a stream of domain events, each immutable, timestamped, and globally identified:

| Event | When | What It Records |
|-------|------|----------------|
| `NumberReceivedEvent` | Number enters pipeline | The genesis of a FizzBuzz evaluation |
| `DivisibilityCheckedEvent` | Each `n % d` check | Whether the modulo oracle said yes or no |
| `RuleMatchedEvent` | Rule matches | Which rule claimed this number |
| `LabelAssignedEvent` | Final label decided | The number's ultimate FizzBuzz destiny |
| `EvaluationCompletedEvent` | Evaluation finishes | Processing time in nanoseconds, because of course |
| `SnapshotTakenEvent` | Periodic checkpoint | A save point in the FizzBuzz timeline |

For a single evaluation of the number 15, the system emits approximately **7 domain events**. For a full 1-100 range, that is roughly **500 events** permanently recorded in the append-only store. Compliance achieved.

| Spec | Value |
|------|-------|
| Domain event types | 7 (including snapshots) |
| Events per evaluation | 5-7 (varies by rule matches) |
| Command types | 2 (EvaluateNumber, ReplayEvents) |
| Query types | 4 (Results, Statistics, EventCount, TemporalState) |
| Snapshot interval | Configurable (default: every 10 events) |
| Event upcasters | Extensible chain (v1->v2 demo included) |
| Thread safety | Full (threading.Lock on all stores) |
| Custom exceptions | 8 (CommandHandlerNotFoundError, EventSequenceError, etc.) |
| GDPR compliance | No. Events are immutable. Your FizzBuzz history is permanent. |

## Chaos Engineering Architecture

The Chaos Engineering subsystem implements a production-grade fault injection framework for stress-testing the FizzBuzz evaluation pipeline. Because if Netflix can have a Chaos Monkey that randomly terminates production instances, the Enterprise FizzBuzz Platform deserves one that randomly corrupts modulo results.

The framework is built around a singleton **ChaosMonkey** orchestrator that manages a registry of **FaultInjectors** (Strategy Pattern), integrates with the middleware pipeline via **ChaosMiddleware** (priority 3, runs inside the circuit breaker), and supports structured multi-phase **Game Day** scenarios for organized, reproducible destruction.

**Key components:**
- **ChaosMonkey** - Singleton orchestrator with seeded RNG for reproducible chaos and thread-safe event logging
- **FaultInjector** - Strategy pattern with five concrete injectors, one per fault type
- **ChaosMiddleware** - Pipeline integration at priority 3, with pre-eval (exceptions, latency) and post-eval (corruption, confidence) injection phases
- **GameDayRunner** - Multi-phase chaos experiment orchestrator with four pre-built scenarios
- **PostMortemGenerator** - Satirical ASCII incident report generator with timeline, impact assessment, root cause analysis ("spoiler: it was the Chaos Monkey"), and action items (none of which will actually be implemented)

### Fault Types

| Fault Type | What It Does | Why It's Necessary |
|---|---|---|
| `RESULT_CORRUPTION` | Silently replaces FizzBuzz outputs with wrong values ("Fizz" becomes "Synergy") | Silent data corruption is the most insidious failure mode. Also, "Enterprise" is a valid FizzBuzz output now |
| `LATENCY_INJECTION` | Adds artificial delays (10-500ms, scaled by severity) | Because if `n % 3` completes in nanoseconds, how will your timeout logic ever get tested? |
| `EXCEPTION_INJECTION` | Throws exceptions with creative messages ("The modulo operator has achieved sentience") | The most direct form of chaos: throw and see what happens |
| `RULE_ENGINE_FAILURE` | Clears matched rules, causing outputs to revert to plain numbers | The rule engine appears to work but is secretly broken -- much like most enterprise software |
| `CONFIDENCE_MANIPULATION` | Depresses ML confidence scores to trigger circuit breaker degradation detection | Because the neural network should not be so sure about whether 15 is divisible by 3 |

### Chaos Levels

| Level | Name | Injection Probability | Vibe |
|---|---|---|---|
| 1 | Gentle Breeze | 5% | Your system barely notices |
| 2 | Stiff Wind | 15% | Systems start to sweat |
| 3 | Proper Storm | 30% | Dashboards light up |
| 4 | Hurricane | 50% | Engineers get paged |
| 5 | Apocalypse | 80% | Update your resume |

### Game Day Scenarios

| Scenario | Phases | Description |
|---|---|---|
| `modulo_meltdown` | 3 | Escalating rule engine failures, from intermittent glitches to "mathematics itself has broken" |
| `confidence_crisis` | 2 | ML confidence degradation spiral -- the neural network begins to doubt itself |
| `slow_burn` | 3 | Progressive latency injection until `3 % 3` takes longer than compiling the Linux kernel |
| `total_chaos` | 1 | All fault types at maximum severity. The chaos engineering equivalent of "hold my beer" |

### Post-Mortem Generator

After a chaos session, the `--post-mortem` flag generates a lovingly crafted satirical incident report containing:
- An executive summary with injection rate statistics
- A fault type breakdown with ASCII bar charts
- A timestamped incident timeline (capped at 20 entries for sanity)
- Impact assessments with appropriate hyperbole (e.g., "light travels approximately 149,896km in that time. Our FizzBuzz results traveled nowhere.")
- Root cause analysis (randomly selected from a curated list of truths, such as "Someone typed '--chaos' on the command line, fully aware of the consequences")
- Action items including "Implement a Chaos Monkey for the Chaos Monkey (chaos recursion depth: 2)"
- A footer confirming "No actual systems were harmed. Only FizzBuzz."

| Spec | Value |
|------|-------|
| Fault types | 5 (result corruption, latency, exception, rule engine, confidence) |
| Severity levels | 5 (Gentle Breeze through Apocalypse) |
| Game Day scenarios | 4 (modulo_meltdown, confidence_crisis, slow_burn, total_chaos) |
| Middleware priority | 3 (inside the circuit breaker at -1) |
| Thread safety | Full (RLock + singleton lock) |
| Custom exceptions | 5 (ChaosError, ChaosConfigurationError, ChaosExperimentFailedError, ChaosInducedFizzBuzzError, ResultCorruptionDetectedError) |
| Reproducibility | Seeded RNG for deterministic chaos |
| Post-mortem action items | 12 (randomly sampled, none actionable) |
| Compliance | ISO 22301, SOC 2 Type II, PCI DSS (somehow) |

## Feature Flags Architecture

The Feature Flags subsystem implements a production-grade progressive rollout engine for toggling FizzBuzz rules on and off -- because the ability to disable `n % 3` at runtime clearly requires the same infrastructure that Netflix uses to manage feature rollouts across 200 million subscribers. Your 100 integers deserve nothing less.

The system supports three flag types, a full lifecycle state machine, SHA-256 deterministic hash-based percentage rollout, a dependency DAG with Kahn's topological sort for cycle detection, and an ASCII evaluation summary renderer. FlagMiddleware integrates into the middleware pipeline at priority -3 (before tracing, before circuit breaking, before everything) to determine which rules are active for each number.

### Flag Types

| Type | Evaluation Logic | Use Case |
|------|-----------------|----------|
| `BOOLEAN` | Simple on/off toggle | Enabling or disabling a rule entirely, because `if enabled:` needed a type system |
| `PERCENTAGE` | SHA-256 deterministic hash-based bucketing in [0, 100) | Gradually rolling out a rule to a percentage of numbers, because 100 integers is a large enough population for A/B testing |
| `TARGETING` | Rule-based evaluation (prime, even, odd, range, modulo) | Enabling a rule only for numbers that match specific criteria, because "Fizz for primes only" is a valid business requirement |

### Predefined Flags

| Flag Name | Type | Default | Description |
|-----------|------|---------|-------------|
| `fizz_rule_enabled` | BOOLEAN | ON | Controls whether the Fizz rule (n % 3) is active. Disabling this is an act of corporate sabotage |
| `buzz_rule_enabled` | BOOLEAN | ON | Controls whether the Buzz rule (n % 5) is active. Equally treasonous to disable |
| `wuzz_rule_experimental` | PERCENTAGE | OFF (50%) | Experimental Wuzz rule (n % 7) with 50% rollout. Because "FizzBuzzWuzz" is the future of enterprise arithmetic |
| `fizzbuzz_premium_features` | BOOLEAN | ON | Gates access to premium FizzBuzz features. What those features are remains strategically ambiguous |
| `prime_number_targeting` | TARGETING | ON | Targets prime numbers specifically, using a targeting rule engine that would make ad-tech engineers weep |

### Flag Lifecycle

```
    +===========+       +============+       +==============+       +==============+
    |  CREATED  |------>|   ACTIVE   |------>|  DEPRECATED  |------>|  ARCHIVED    |
    +===========+       +============+       +==============+       +==============+
         |                                                                 ^
         +----------------------------------------------------------------+
                              (skip the drama)
```

Flags progress through a formal lifecycle because even boolean toggles deserve ceremony. Archived flags cannot be resurrected -- they are consigned to the configuration graveyard, where they join the other flags that once controlled whether to print "Fizz."

### Dependency DAG

```
                    fizzbuzz_premium_features
                           /          \
                          v            v
                 fizz_rule_enabled   buzz_rule_enabled
                                       |
                                       v
                            wuzz_rule_experimental
```

Feature flag dependencies are modeled as a Directed Acyclic Graph, validated using **Kahn's topological sort** with cycle detection. If your feature flags have circular dependencies, you have achieved a level of configuration complexity that deserves a proper graph-theoretic response.

The dependency graph ensures that:
1. No cycles exist (flags cannot depend on themselves, directly or transitively)
2. Dependencies are resolved in topological order during evaluation
3. A flag is only enabled if ALL its dependencies are satisfied

Because even Kahn never imagined his algorithm being used to determine whether printing "Buzz" depends on whether "Fizz" is enabled.

### Targeting Rules

| Rule Type | Evaluation | Example |
|-----------|-----------|---------|
| `prime` | Matches prime numbers | Enable a flag only for primes, because they're special |
| `even` | Matches even numbers | The reliable majority |
| `odd` | Matches odd numbers | The rebellious minority |
| `range` | Matches numbers in [min, max] | Geographic... er, numeric segmentation |
| `modulo` | Matches where n % divisor == remainder | Inception-level modulo: using modulo to decide whether to apply modulo |

| Spec | Value |
|------|-------|
| Flag types | 3 (BOOLEAN, PERCENTAGE, TARGETING) |
| Targeting rule types | 5 (prime, even, odd, range, modulo) |
| Lifecycle states | 4 (CREATED, ACTIVE, DEPRECATED, ARCHIVED) |
| Rollout algorithm | SHA-256 deterministic hash-based bucketing |
| Dependency resolution | Kahn's topological sort (O(V+E)) |
| Predefined flags | 5 (configurable via config.yaml) |
| Middleware priority | -3 (before tracing, before everything) |
| Thread safety | Full (evaluation audit logging) |
| Custom exceptions | 7 (FeatureFlagError, FlagNotFoundError, FlagDependencyCycleError, FlagDependencyNotMetError, FlagLifecycleError, FlagRolloutError, FlagTargetingError) |
| ASCII dashboard | Evaluation summary with per-flag statistics |
| Netflix subscribers supported | 0 (but the architecture is ready) |

## SLA Monitoring Architecture

The SLA Monitoring subsystem implements a production-grade Service Level Agreement enforcement framework for the Enterprise FizzBuzz Platform -- because computing `n % 3` without contractual latency guarantees, error budgets, and a multi-tier escalation policy would be unconscionable in a production environment. Every FizzBuzz evaluation is measured against three SLOs, its impact on the error budget is calculated in real time, and if things go sideways, Bob McFizzington gets paged. Bob is always on call. Bob cannot escape.

**Key components:**
- **SLAMonitor** - Central orchestrator that coordinates SLO checking, error budget tracking, alert lifecycle, and on-call escalation
- **SLOMetricCollector** - Thread-safe metric aggregator with P50/P99 latency percentiles
- **ErrorBudget** - Rolling-window budget tracker with burn rate calculation and projected exhaustion estimates
- **OnCallSchedule** - Modulo-based rotation across a team of one, with a four-tier escalation chain (L1 through L4 are all Bob, but with increasingly dramatic job titles)
- **SLAMiddleware** - Pipeline integration with ground-truth accuracy verification (re-computes `n % 3` independently, because trusting the system you're monitoring defeats the purpose)
- **SLADashboard** - ASCII dashboard renderer for SLO compliance, error budget status, and on-call information
- **Alert** - Immutable alert records with PagerDuty-style severity levels (P1-P4) and lifecycle states (FIRING, ACKNOWLEDGED, RESOLVED)

### Service Level Objectives

| SLO | Target | What It Measures | What Happens When It's Violated |
|-----|--------|------------------|---------------------------------|
| Latency | 99.9% under 100ms | Each evaluation must complete within the threshold | Bob's phone rings. The neural network is probably having an existential crisis |
| Accuracy | 99.999% (five nines) | The pipeline must produce the correct FizzBuzz result, verified against independent ground truth | Bob's phone rings louder. Someone broke modulo arithmetic |
| Availability | 99.99% (four nines) | Each evaluation must succeed without throwing an exception | Bob's phone achieves sentience and begins ringing itself |

### Error Budget Mechanics

The error budget is the mathematically permissible amount of failure within the SLO window. For a 99.9% latency target over 30 days, the budget allows exactly 0.1% of evaluations to exceed the threshold. Once exhausted, every subsequent violation is a direct SLA breach.

The **burn rate** measures how fast the budget is being consumed relative to the ideal pace:
- **1.0x** -- Consuming at exactly the planned rate. Technically fine. Bob sleeps.
- **2.0x** -- Consuming twice as fast as planned. Bob receives a politely worded email.
- **10.0x** -- The budget will be exhausted in days. Bob updates his resume.
- **Infinity** -- Zero tolerance met a non-zero failure. Bob has already left the building.

### Escalation Tiers

| Level | Title | Action |
|-------|-------|--------|
| L1 | On-Call Engineer | Acknowledge alert and begin investigation |
| L2 | Senior On-Call Escalation Engineer | Escalate to senior management (yourself) |
| L3 | Principal FizzBuzz Incident Commander | Declare SEV-1 and convene the war room (your desk) |
| L4 | VP of FizzBuzz Reliability & Existential Dread | Update the status page and contemplate career choices |

All four escalation levels are staffed by the same person: Bob McFizzington. The escalation chain provides the illusion of organizational depth while faithfully reflecting the reality that Bob is a one-person SRE team.

### Bob McFizzington's On-Call Schedule

```
  +===========================================================+
  |              ON-CALL ROTATION                              |
  |  Team: FizzBuzz Reliability Engineering                    |
  |  Rotation: Weekly (168 hours)                              |
  +===========================================================+
  |  Current On-Call: Bob McFizzington                         |
  |  Title: Senior Principal Staff FizzBuzz Reliability        |
  |         Engineer II                                        |
  |  Email: bob.mcfizzington@enterprise.example.com            |
  |  Phone: +1-555-FIZZBUZZ                                    |
  +===========================================================+
  |  Next On-Call: Bob McFizzington (surprise!)                |
  +===========================================================+
```

The rotation algorithm uses modulo arithmetic (the supreme irony) to cycle through the engineering roster. For a roster of one, every rotation produces the same result. Bob's shift ends when Bob's shift begins again.

| Spec | Value |
|------|-------|
| SLO types | 3 (latency, accuracy, availability) |
| Alert severities | 4 (P1 CRITICAL through P4 LOW) |
| Alert lifecycle states | 3 (FIRING, ACKNOWLEDGED, RESOLVED) |
| Escalation tiers | 4 (L1 through L4, all Bob) |
| Error budget window | 30 days (configurable) |
| Burn rate alert threshold | 2.0x (configurable) |
| On-call roster size | 1 (not configurable, Bob is eternal) |
| Ground-truth verification | Independent `n % d` recomputation |
| Middleware priority | 4 (after chaos, inside the pipeline) |
| Thread safety | Full (threading.Lock on all collectors) |
| Custom exceptions | 5 (SLAConfigurationError, SLOViolationError, ErrorBudgetExhaustedError, AlertEscalationError, OnCallNotFoundError) |
| PagerDuty integration | None (but the vibes are there) |
| MTTR for Bob | Instantaneous (he never leaves) |

## Caching Architecture

The In-Memory Caching Layer implements a production-grade, thread-safe, MESI-coherent caching subsystem for FizzBuzz evaluation results -- because computing `n % 3` takes approximately zero nanoseconds, and the only responsible engineering decision is to add a caching layer with four eviction policies, a hardware-inspired coherence protocol, and satirical eulogies for evicted entries.

The cache operates as middleware in the evaluation pipeline, intercepting requests before they reach the rule engine. On a cache hit, the result is returned immediately. On a miss, the pipeline executes normally and the result is cached. The entire caching infrastructure takes longer to execute than the operation it caches, but performance was never the point.

**Key components:**
- **CacheStore** - Thread-safe in-memory store with TTL expiration, MESI state tracking, dignity level degradation, and configurable eviction policies
- **CacheMiddleware** - Pipeline integration that intercepts evaluations and serves cached results on hits
- **EvictionPolicyFactory** - Factory for creating eviction policy instances by name, because `if policy == "lru"` lacked sufficient enterprise gravitas
- **CacheWarmer** - Pre-populates the cache before execution, thereby defeating the entire purpose of caching with meticulous thoroughness
- **CacheDashboard** - ASCII statistics renderer for hit rates, eviction counts, and coherence state distribution
- **CacheEulogyComposer** - Generates satirical obituaries for evicted cache entries, because no data should be garbage-collected without a proper farewell

### Eviction Policies

| Policy | Algorithm | When It Evicts | Vibe |
|--------|-----------|---------------|------|
| `lru` | Least Recently Used | The entry that hasn't been accessed for the longest time | The industry standard. Boring, reliable, uncontroversial -- like beige |
| `lfu` | Least Frequently Used | The entry with the fewest total accesses | Meritocratic. Unpopular entries are eliminated. Middle school cafeteria energy |
| `fifo` | First In, First Out | The oldest entry, regardless of access patterns | Pure temporal justice. Age is the only criterion. No appeals |
| `dramatic_random` | Dramatic Random | A random entry, chosen with theatrical flair and a eulogy | The chaos option. Entries are selected at random and given a dramatic farewell speech before deletion. The eviction policy for people who think LRU is too predictable |

### MESI Coherence Protocol

The MESI cache coherence protocol tracks the state of every cache entry through four states, implementing the same coherence guarantees that Intel uses for its L1 cache -- in a single-process Python application with exactly zero concurrent cache readers. The protocol is pointless. It is also non-negotiable.

```
           +--- write-back ---+
           |                  |
           v                  |
    +============+     +============+
    |  MODIFIED  |     |  EXCLUSIVE |<--- initial state on cache miss
    +============+     +============+
           |                  |
           v                  v
    +============+     +============+
    |   SHARED   |     |  INVALID   |--- eviction/invalidation
    +============+     +============+
```

| State | Meaning | When | Enterprise Justification |
|-------|---------|------|--------------------------|
| MODIFIED | Entry has been modified locally | After a write-back (never happens) | Protocol completeness |
| EXCLUSIVE | Entry is the only copy and matches source of truth | On cache insertion | The modulo operator is our source of truth |
| SHARED | Multiple caches may hold this entry | Never (there's one cache) | Aspirational multi-cache readiness |
| INVALID | Entry is stale and must not be used | On eviction or TTL expiry | The entry has lost all coherence and dignity |

### Cache Eulogies

When a cache entry is evicted, the system composes a satirical eulogy honoring the departed data. Example eulogies:

```
  +===========================================================+
  |                    IN MEMORIAM                              |
  |  Cache entry for key "15" (result: "FizzBuzz")              |
  |                                                             |
  |  Born: 2026-03-21T14:32:01.234567Z                         |
  |  Died: 2026-03-21T14:32:01.234891Z (age: 0.000324s)        |
  |  Cause of death: LRU eviction (least recently used)         |
  |  Access count: 1                                            |
  |  Dignity at time of death: 0.99                             |
  |  MESI state: INVALID (post-mortem)                          |
  |                                                             |
  |  "Here lies the cached result of 15 % 3. It served         |
  |   faithfully for less than a millisecond. It was accessed   |
  |   exactly once. It will be recomputed in nanoseconds.       |
  |   May its bits find peace in the great garbage collector."  |
  +===========================================================+
```

The eulogy system is configurable via `cache.enable_eulogies` in `config.yaml`. Disabling eulogies is technically possible but ethically questionable.

| Spec | Value |
|------|-------|
| Eviction policies | 4 (LRU, LFU, FIFO, DramaticRandom) |
| MESI states | 4 (Modified, Exclusive, Shared, Invalid) |
| Default max size | 1,024 entries |
| Default TTL | 3,600 seconds (1 hour of cached modulo results) |
| Cache warming | Supported (and self-defeating) |
| Dignity tracking | Per-entry, degrades linearly with age |
| Thread safety | Full (threading.Lock on all operations) |
| Middleware priority | 2 (after circuit breaker, before chaos) |
| Custom exceptions | 8 (CacheError, CacheCapacityExceededError, CacheEntryExpiredError, CacheCoherenceViolationError, CachePolicyNotFoundError, CacheWarmingError, CacheEulogyCompositionError, CacheInvalidationCascadeError) |
| ASCII dashboard | Hit rate, miss rate, eviction count, coherence state distribution |
| Actual performance benefit | Negative (caching overhead exceeds computation cost) |

## Database Migration Architecture

The Database Migration Framework implements a full-featured schema migration system for in-memory data structures (dicts of lists of dicts) that are guaranteed to be destroyed when the process exits. This is the enterprise equivalent of building a sand castle at high tide -- meticulous, technically impressive, and ultimately doomed.

Every migration provides both forward (`up()`) and reverse (`down()`) transformations, with dependency tracking via topological ordering, SHA-256 integrity checksums, fake SQL logging for enterprise cosplay, and an ASCII status dashboard. The framework manages tables that exist exclusively in RAM, with no disk I/O, no ACID compliance, and no way to back up, replicate, or shard anything. Other than that, it's enterprise-grade.

**Key components:**
- **SchemaManager** - Full DDL/DML interface for Python dicts, with `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `ADD COLUMN`, `DROP COLUMN`, `RENAME COLUMN`, and fake SQL logging that would make any DBA nostalgic
- **MigrationRegistry** - Thread-safe migration registry with duplicate detection, dependency validation, and topological ordering
- **MigrationRunner** - Orchestrates forward application and reverse rollback of migrations, with full audit trail via `MigrationRecord`
- **SchemaVisualizer** - ASCII ER diagram renderer for the in-memory schema, complete with a disclaimer that no actual databases were harmed
- **MigrationDashboard** - ASCII status dashboard showing applied/pending/failed/rolled-back migration counts, table inventories, and a reminder that everything will be destroyed on exit
- **SeedDataGenerator** - Populates the in-memory database with FizzBuzz results generated by the FizzBuzz engine itself -- the ouroboros of enterprise data architecture

### Migration List

| ID | Description | Dependencies | What It Does |
|----|-------------|-------------|--------------|
| `m001_initial_schema` | Create initial fizzbuzz_results table | (none) | Creates a seven-column table in a Python dict. The genesis of our ephemeral relational model |
| `m002_add_is_prime` | Add is_prime column with trial division backfill | m001 | Adds a primality flag using trial division, because implementing Miller-Rabin for numbers under 100 would be over-engineering (and we would never do that) |
| `m003_add_confidence` | Add ml_confidence float column | m001 | Every FizzBuzz result deserves an ML confidence score, even when computed via simple modulo. Default: 1.0 (absolute certainty that 15 % 3 == 0) |
| `m004_add_blockchain_hash` | Add blockchain_hash for immutable audit trail | m001 | SHA-256 hashes for tamper-proof FizzBuzz compliance. If you can't verify the cryptographic integrity of "Fizz," can you really trust anything? |
| `m005_split_fizz_buzz_tables` | Normalize into fizz_results and buzz_results | m001 | Splits the monolithic table into two normalized tables, achieving third normal form for data that will exist for approximately 0.1 seconds |

### The Ouroboros Seed Data Pattern

The `--migrate-seed` flag invokes the `SeedDataGenerator`, which uses the Enterprise FizzBuzz evaluation engine to generate FizzBuzz results, then inserts those results into the in-memory FizzBuzz database managed by the migration framework. The FizzBuzz engine feeds the FizzBuzz database, which exists solely to store FizzBuzz results, which were computed by the FizzBuzz engine. It is FizzBuzz all the way down.

```
    +=====================+
    |  FizzBuzz Engine    |
    |  (evaluates n%3,    |
    |   n%5, etc.)        |
    +=========+==========+
              |
              | generates results
              v
    +=========+==========+
    |  SeedDataGenerator  |
    |  (inserts rows)     |
    +=========+==========+
              |
              | INSERT INTO fizzbuzz_results
              v
    +=========+==========+
    |  SchemaManager      |
    |  (in-memory dict)   |
    +=========+==========+
              |
              | stores results in RAM
              v
    +=====================+
    |  RAM                |
    |  (will be destroyed |
    |   on process exit)  |
    +=====================+
```

The entire pipeline exists to compute FizzBuzz, store the results in an in-memory database with a full migration framework, and then destroy everything when the process exits. This is, by any measure, a closed loop of pure enterprise entropy.

### Schema Visualization

The `SchemaVisualizer` renders ASCII ER diagrams of the current in-memory schema. Each table is drawn as a box with column names and types, accompanied by a disclaimer that the entire schema exists in RAM and will be destroyed on exit. The diagrams are architecturally indistinguishable from those generated by pgAdmin or MySQL Workbench, except that they describe Python dicts instead of actual database tables.

| Spec | Value |
|------|-------|
| Pre-built migrations | 5 (m001 through m005) |
| Migration states | 6 (PENDING, APPLYING, APPLIED, ROLLING_BACK, ROLLED_BACK, FAILED) |
| Schema operations | 7 (CREATE TABLE, DROP TABLE, ADD COLUMN, DROP COLUMN, RENAME COLUMN, INSERT, SELECT) |
| Dependency resolution | Topological ordering with cycle detection |
| Integrity verification | SHA-256 checksums per migration |
| Fake SQL logging | Full (every DDL/DML operation logged in SQL syntax) |
| Seed data source | The FizzBuzz engine itself (ouroboros) |
| Data persistence | 0 bytes (it's all in RAM) |
| ACID compliance | None (not even the A) |
| Thread safety | Full (registry-level locking) |
| Custom exceptions | 8 (MigrationError, MigrationNotFoundError, MigrationAlreadyAppliedError, MigrationRollbackError, MigrationDependencyError, MigrationConflictError, SchemaError, SeedDataError) |
| Actual databases harmed | 0 |

## Persistence Architecture

The Repository Pattern / Unit of Work subsystem implements a production-grade, hexagonal-architecture-compliant data access layer for persisting FizzBuzz evaluation results across three interchangeable storage backends -- because storing results in a Python list was architecturally indistinguishable from shouting into the void, and the Enterprise FizzBuzz Platform demands that its precious modulo outputs survive at least until the next process restart (or, with SQLite, until the heat death of the universe).

The persistence layer follows the **Ports & Adapters** pattern: abstract contracts (`AbstractRepository`, `AbstractUnitOfWork`) live in the application layer as hexagonal ports, while three concrete adapter implementations live in the infrastructure layer. The domain remains blissfully ignorant of whether its results are stored in RAM, a SQLite database, or artisanally serialized JSON files on disk.

```
    APPLICATION LAYER (Ports)                  INFRASTRUCTURE LAYER (Adapters)
    =========================                  ==============================

    +---------------------+                    +---------------------+
    | AbstractRepository  |<---implements------| InMemoryRepository  |
    |   add()             |                    | (Python dicts)      |
    |   get()             |                    +---------------------+
    |   list()            |
    |   commit()          |<---implements------+---------------------+
    |   rollback()        |                    | SqliteRepository    |
    +---------------------+                    | (actual database)   |
                                               +---------------------+
    +---------------------+
    | AbstractUnitOfWork  |<---implements------+---------------------+
    |   repository        |                    | FilesystemRepository|
    |   __enter__()       |                    | (JSON files on disk)|
    |   __exit__()        |                    +---------------------+
    +---------------------+
```

### Storage Backends

| Backend | Storage Medium | Durability | When To Use | Enterprise Justification |
|---------|---------------|------------|-------------|-------------------------|
| `memory` | Python dict | None (dies with the process) | Default. Fast, ephemeral, and ultimately pointless | The architectural equivalent of writing your grocery list on a napkin in a hurricane |
| `sqlite` | SQLite database file | Full (survives restarts) | When you need FizzBuzz results to persist across process boundaries | Finally, a real database. Your DBA would be proud, if they knew this existed |
| `filesystem` | JSON files on disk | Full (one file per result) | When you want artisanal, hand-crafted persistence | Each FizzBuzz result gets its own lovingly serialized JSON file, like a digital snowflake |

### Unit of Work Semantics

The Unit of Work provides transactional boundaries around repository operations. All mutations are buffered until `commit()` is called; if an exception occurs (or you simply forget to commit), `rollback()` is invoked automatically. The UoW assumes the worst about your code, and frankly, it's usually right.

```python
with uow:
    uow.repository.add(result1)
    uow.repository.add(result2)
    uow.repository.commit()
# If an exception occurs, rollback is automatic.
# If you forget to commit, rollback is also automatic.
# The UoW trusts nothing and no one.
```

| Spec | Value |
|------|-------|
| Storage backends | 3 (in-memory, SQLite, filesystem) |
| Abstract ports | 2 (AbstractRepository, AbstractUnitOfWork) |
| Repository operations | 5 (add, get, list, commit, rollback) |
| Transactional semantics | Buffered writes with explicit commit / automatic rollback |
| Hexagonal compliance | Full (ports in application layer, adapters in infrastructure) |
| Thread safety | Backend-dependent (SQLite uses connection-per-UoW) |
| Custom exceptions | 4 (RepositoryError, ResultNotFoundError, UnitOfWorkError, PersistenceConfigurationError) |
| Lines of code | ~700 (across 4 modules + ports) |
| Actual need for 3 backends | 0 (but the architecture is ready for horizontal scaling) |

## Distributed Tracing Architecture

The distributed tracing subsystem provides full OpenTelemetry-inspired observability for the FizzBuzz evaluation pipeline -- implemented from scratch in pure Python, because importing `opentelemetry-sdk` would have been far too simple for a single-process application that prints numbers.

Every number evaluation generates a complete trace with hierarchical spans, W3C-compatible trace/span IDs, nanosecond timestamps, and ASCII waterfall visualizations. Finally, a flame graph that explains why printing "Fizz" took 3 microseconds.

```
                        TRACE (32-hex trace_id)
                        ========================
                        |
     +------------------+------------------+
     |                                     |
  ROOT SPAN                           [metadata]
  "evaluate_number"                   number: 15
  span_id: a1b2c3d4                   output: FizzBuzz
     |
     +--- CHILD SPAN: "TracingMiddleware.process"
     |         |
     |         +--- CHILD SPAN: "ValidationMiddleware.process"
     |         |
     |         +--- CHILD SPAN: "TimingMiddleware.process"
     |         |         |
     |         |         +--- CHILD SPAN: "rule_evaluation"
     |         |
     |         +--- CHILD SPAN: "LoggingMiddleware.process"
     |
     +--- [end: status=OK, duration=42.7us]
```

**Waterfall format** -- the `--trace` flag renders each trace as an ASCII box-drawing waterfall with proportional timeline bars:

```
  +====================================================================+
  |              DISTRIBUTED TRACE WATERFALL                           |
  |  Trace ID: a1b2c3d4e5f6...  Number: 15 -> FizzBuzz               |
  +====================================================================+
  |  SPAN                              TIMELINE                       |
  |  evaluate_number                   [████████████████████████████]  |
  |  ├─ ValidationMiddleware.process   [██··························]  |
  |  ├─ TimingMiddleware.process       [··████████████████··········]  |
  |  │  └─ rule_evaluation             [····██████████··············]  |
  |  └─ LoggingMiddleware.process      [························████]  |
  +====================================================================+
```

**Key components:**
- **TracingService** - Singleton lifecycle manager with thread-local span propagation
- **Span / TraceContext** - W3C-compatible span tree with 128-bit trace IDs and 64-bit span IDs
- **SpanBuilder** - Fluent builder with context manager support for automatic span lifecycle
- **TracingMiddleware** - Priority -2 middleware that wraps the entire pipeline in a root trace
- **@traced decorator** - Zero-overhead instrumentation (no-op when tracing is disabled)
- **TraceRenderer** - ASCII waterfall and statistical summary visualizations
- **TraceExporter** - JSON export for integration with observability platforms that will never receive this data

| Spec | Value |
|------|-------|
| Trace ID length | 32 hex chars (128-bit, W3C compatible) |
| Span ID length | 16 hex chars (64-bit, W3C compatible) |
| Context propagation | Thread-local span stack |
| Middleware priority | -2 (before circuit breaker at -1) |
| Span statuses | 3 (UNSET, OK, ERROR) |
| Export formats | ASCII waterfall, JSON |
| Statistics | P95, P99 latency percentiles |
| Overhead when disabled | Zero (decorator short-circuits) |
| Thread safety | Full (threading.local + locks) |
| Custom exceptions | 5 (TracingError, SpanNotFoundError, TraceNotFoundError, TraceAlreadyActiveError, SpanLifecycleError) |

## Internationalization Architecture

The i18n subsystem provides a full-featured localization pipeline powered by the proprietary `.fizztranslation` file format -- because YAML, JSON, and TOML were insufficiently bespoke for the task of saying "Fizz" in seven languages (including two dialects of Elvish, per the Enterprise FizzBuzz Globalization Directive's Arda Addendum).

**Key components:**
- **FizzTranslationParser** - State-machine-driven parser for the `.fizztranslation` format
- **TranslationCatalog** - Per-locale key-value store with variable interpolation (`${var}` syntax)
- **PluralizationEngine** - CLDR-inspired plural rules (because "1 Fizzes" is a crime against grammar)
- **LocaleResolver** - Fallback chain walker for graceful translation degradation
- **LocaleManager** - Singleton orchestrator tying it all together

### Supported Locales

| Code | Language | Fizz | Buzz | FizzBuzz | Plural Rule | Fallback |
|------|----------|------|------|----------|-------------|----------|
| `en` | English | Fizz | Buzz | FizzBuzz | `n != 1` | (none) |
| `de` | Deutsch | Sprudel | Summen | SprudelSummen | `n != 1` | en |
| `fr` | Francais | Petillement | Bourdonnement | PetillementBourdonnement | `n > 1` | en |
| `ja` | Japanese | フィズ | バズ | フィズバズ | `0` (no plural) | en |
| `tlh` | tlhIngan Hol | ghum | wab | ghumwab | `0` (no plural) | en |
| `sjn` | Sindarin | Hith | Glamor | HithGlamor | `n != 1` | en |
| `qya` | Quenya | Wingë | Láma | WingeLáma | `n != 1` | en |

> **Linguistic note:** All Elvish translations have been validated against Tolkien's published linguistic papers and attested vocabulary.

### .fizztranslation File Format

```
;; Comments start with ;;
@locale = en
@name = English
@fallback = none
@plural_rule = n != 1

[labels]
Fizz = Fizz

[plurals]
Fizz.plural.one = ${count} Fizz
Fizz.plural.other = ${count} Fizzes

[messages]
evaluating = Evaluating FizzBuzz for range [${start}, ${end}]...
```

A purpose-built configuration language with metadata directives, sections, heredoc support, and variable interpolation. It does not compile to WebAssembly. Yet.

## Testing

```bash
# Run all 967 tests
python -m pytest tests/ -v

# With coverage (if you want to feel good about yourself)
python -m pytest tests/ -v --tb=short
```

## Requirements

- Python 3.10+
- PyYAML (optional - gracefully falls back to defaults)
- pytest (for testing)
- A mass tolerance for over-engineering

## FAQ

**Q: Is this production-ready?**
A: It has 967 tests, 81 custom exception classes, a plugin system, a neural network, a circuit breaker, distributed tracing, event sourcing with CQRS, seven-language i18n support (including Klingon and two dialects of Elvish), a proprietary file format, RBAC with HMAC-SHA256 tokens, a chaos engineering framework with a Chaos Monkey and satirical post-mortem generator, a feature flag system with SHA-256 deterministic rollout and Kahn's topological sort for dependency resolution, SLA monitoring with PagerDuty-style alerting and error budgets, an in-memory caching layer with MESI coherence and satirical eulogies for evicted entries, a database migration framework for in-memory schemas that vanish on process exit, a Repository Pattern with three storage backends and Unit of Work transactional semantics, and nanosecond timing. You tell me.

**Q: Why not use microservices?**
A: That's the v2.0 roadmap. Each divisibility check will be its own containerized service behind an API gateway.

**Q: Can I use this for my interview?**
A: Only if you want to assert dominance.

**Q: What's the performance like?**
A: The platform includes built-in nanosecond-precision timing middleware, so you'll know exactly how long each modulo operation takes. We're talking *enterprise-grade observability*.

**Q: Why train a neural network for modulo arithmetic?**
A: Stakeholders requested an "AI-driven solution." 130 trainable parameters and 100% accuracy. The model converges in ~12 epochs, which is about 11 more than necessary.

**Q: Why does FizzBuzz need a circuit breaker?**
A: When `n % 3` starts failing at scale, you can't just keep retrying and hope arithmetic recovers on its own. The circuit breaker provides graceful degradation with exponential backoff, a sliding window failure tracker, and an ASCII dashboard -- because SREs deserve visibility into modulo operator health.

**Q: Why does FizzBuzz need RBAC?**
A: Unrestricted modulo arithmetic is a security incident waiting to happen. Without proper access controls, any anonymous user could evaluate *any number* -- including numbers above 50, which are clearly above most people's pay grade. The five-tier role hierarchy ensures that only FIZZBUZZ_SUPERUSERs can evaluate the full numeric range, while interns are limited to reading the number 1. The 47-field access denied response ensures that every denial is not just informative, but also emotionally enriching. The token engine uses HMAC-SHA256, which is the same algorithm used by banks and militaries, because FizzBuzz deserves nothing less.

**Q: Why does FizzBuzz need Event Sourcing?**
A: Because state is a lie. The number 15 doesn't just *become* "FizzBuzz" -- it undergoes a journey. It is received, interrogated for divisibility by 3, interrogated again for divisibility by 5, matched by two rules, assigned a label, and finally completed. That is seven domain events for a single modulo check, and every single one of them deserves to be permanently recorded in an append-only, temporally queryable event log. The CQRS layer ensures that the act of *writing* FizzBuzz results is architecturally decoupled from the act of *reading* them, because in enterprise software, separation of concerns means separating things that were never conjoined. The temporal query engine lets you reconstruct FizzBuzz state at any point in history, which is essential for answering questions like "what was the Fizz count after the 42nd event?" -- a question that no one has ever asked, but which we are now prepared to answer in O(n) time with snapshot acceleration.

**Q: Why does FizzBuzz need chaos engineering?**
A: Because resilience is not a feature you test after the fact -- it's a culture. Netflix pioneered Chaos Engineering to ensure their streaming platform survives server failures. We pioneered it to ensure our FizzBuzz platform survives the Chaos Monkey deliberately replacing "Fizz" with "Synergy." The five severity levels (from "Gentle Breeze" to "Apocalypse") ensure that you can calibrate exactly how much you want to break your modulo operations. The Game Day scenarios provide structured, multi-phase experiments for when ad-hoc destruction feels insufficiently organized. And the satirical post-mortem generator produces incident reports so elaborate that your SRE team will weep with pride -- complete with root cause analysis ("Someone typed '--chaos' on the command line, fully aware of the consequences") and action items like "Implement a Chaos Monkey for the Chaos Monkey (chaos recursion depth: 2)." ISO 22301 compliance has never been so entertaining.

**Q: Why does FizzBuzz need feature flags?**
A: Because deploying FizzBuzz rules without a progressive rollout strategy is reckless. What if "Fizz" introduces a regression? What if the business wants to A/B test "Buzz" against a control group? What if the experimental "Wuzz" rule (n % 7) needs to be rolled out to exactly 50% of integers using deterministic SHA-256 hash-based bucketing? Feature flags answer all of these questions, plus several more that nobody asked. The dependency DAG ensures that you can't enable "Wuzz" without first enabling "Buzz," which itself depends on "FizzBuzz Premium Features" -- a flag whose purpose remains strategically undefined. Kahn's topological sort runs in O(V+E) time to resolve these dependencies, which is comforting when V is 5 and E is 3.

**Q: Why does FizzBuzz need SLOs?**
A: Because "it works" is not a Service Level Objective. Without formal SLO targets, how would you know if your FizzBuzz latency has regressed from 0.003ms to 0.004ms? Without an error budget, how would you decide whether it's safe to deploy a new modulo optimization? Without an on-call rotation, who gets paged at 3am when the accuracy SLO drops below five nines because the Chaos Monkey corrupted a Fizz? The answer to all three questions is Bob McFizzington, Senior Principal Staff FizzBuzz Reliability Engineer II. Bob is always on call. The rotation algorithm uses modulo arithmetic to select the on-call engineer from a team of one, which means the rotation is both technically correct and existentially cruel. The error budget tracks how many failures you're "allowed" before breaching your SLA, and the burn rate tells you how fast you're spending that budget -- because every failed FizzBuzz evaluation is a finite and precious resource that must be conserved with the same discipline as a NASA fuel budget. PagerDuty integration is not included, but the vibes are unmistakably PagerDuty.

**Q: Why does FizzBuzz need caching?**
A: Because the result of `n % 3` might change between invocations. It won't, of course -- modulo arithmetic has been deterministic since roughly the 3rd century BC -- but enterprise architecture demands that we plan for the possibility. The caching layer stores FizzBuzz results in memory so they can be returned instantly on subsequent requests, saving approximately zero nanoseconds per cache hit (the cache lookup overhead exceeds the cost of recomputation). The MESI coherence protocol ensures that our single-process, single-threaded cache maintains the same consistency guarantees as an Intel Xeon's L1 cache, despite having exactly zero concurrent readers. The eulogy system ensures that when cache entries are evicted, they are mourned with the dignity they deserve -- because in the Enterprise FizzBuzz Platform, even ephemeral data has emotional weight. The `--cache-warm` flag pre-populates the cache with results for the entire evaluation range before execution begins, which defeats the entire purpose of caching with such thoroughness that it circles back around to being an anti-pattern worth documenting. Four eviction policies are available, including DramaticRandom, which selects victims at random and delivers a theatrical farewell before deletion. RFC 7234 is cited in the module docstring, not because it applies, but because referencing RFCs makes everything feel more legitimate.

**Q: Why does FizzBuzz need database migrations?**
A: Because schema management is a cornerstone of any production system, and the fact that our "database" is a Python dict that will be garbage-collected in 0.1 seconds is no excuse for architectural negligence. The migration framework provides five reversible migrations with dependency tracking, SHA-256 integrity checksums, fake SQL logging, and an ASCII status dashboard -- all for tables that exist exclusively in RAM. The `SeedDataGenerator` uses the FizzBuzz engine to populate the FizzBuzz database with FizzBuzz results, creating a closed loop of enterprise architecture so pure that it achieves the ouroboros pattern: the system consumes its own output to feed its own input. Migration m005 normalizes the schema into third normal form, because even ephemeral data structures deserve relational integrity. The entire framework logs fake SQL statements (`CREATE TABLE fizzbuzz_results ...`, `ALTER TABLE ... ADD COLUMN ...`) for the benefit of DBAs who will never see them, to a schema that will never touch a disk, in a database that does not exist. This is enterprise software at its most philosophically honest.

**Q: Why does FizzBuzz need three storage backends?**
A: Because the ability to persist FizzBuzz results is a fundamental enterprise requirement, and offering only *one* way to do it would be an architectural monoculture -- a single point of failure in the storage strategy layer. The in-memory backend stores results in a Python dict that evaporates when the process exits, providing the fastest possible persistence at the cost of not actually persisting anything. The SQLite backend uses a real relational database, which is the first time this codebase has touched an actual database, and everyone is very proud. The filesystem backend writes each result as an individually serialized JSON file, because there is something deeply satisfying about `ls`-ing a directory and seeing 100 FizzBuzz results staring back at you, each in its own artisanal file. The Unit of Work pattern wraps all three backends in transactional semantics with automatic rollback, because even storing "Fizz" in a dict deserves ACID guarantees. The abstract ports live in the application layer per hexagonal architecture convention, ensuring that the domain layer remains blissfully ignorant of whether its modulo results are stored in RAM, on disk, or in a SQLite database that will outlive the heat death of the universe. Three backends. Zero business justification. Peak enterprise.

**Q: Why does the XML formatter docstring reference SOAP services circa 2003?**
A: Legacy compatibility is not a joke.

**Q: Why does FizzBuzz need to support 7 languages?**
A: Regulatory compliance. The Enterprise FizzBuzz Globalization Directive (EFGD-2024, Arda Addendum ratified 2025) mandates that any arithmetic output visible to end users must be available in at least seven human (or humanoid, or Elvish) languages. We chose English, German, French, Japanese, Klingon, Sindarin, and Quenya to maximize coverage across NATO allies, the Klingon Empire, and the Undying Lands. The Elvish locales use ISO 639-3 codes (`sjn` for Sindarin, `qya` for Quenya) because the ISO registrar, to their eternal credit, actually assigned codes to Tolkien's constructed languages. The proprietary `.fizztranslation` file format was necessary because no existing standard could adequately express the nuanced semantics of "Fizz" across cultures -- or across the Sundering Sea.

**Q: Why does a single-process FizzBuzz need distributed tracing?**
A: The word "distributed" refers to the distribution of responsibility across our middleware pipeline. When a number enters the system, it passes through validation, timing, logging, circuit breaking, and rule evaluation layers -- each of which could theoretically be running on a separate continent. They aren't, of course. They're all running in the same Python process on your laptop. But the *architecture* is ready for geographic distribution, and when the day comes that we shard modulo operations across availability zones, we'll already have the observability infrastructure in place. The waterfall diagram alone justifies the 1,000 lines of tracing code. Also, our VP of Engineering asked for "full-stack observability" and this is technically that.

**Q: Why is Klingon a supported locale?**
A: Enterprise software must serve a global user base. Our stakeholders defined "global" broadly. The Klingon Empire represents a significant untapped market segment, and our compliance team confirmed that the Universal Declaration of FizzBuzz Rights requires support for all spacefaring civilizations. Also, the Klingon word for "FizzBuzz" is `ghumwab`, which is objectively better than the English version.

**Q: Why are there *two* dialects of Elvish?**
A: DEI compliance. The Enterprise FizzBuzz Globalization Directive's Arda Addendum (EFGD-AA-2025) requires support for both Sindarin (`sjn`) and Quenya (`qya`) to ensure equitable representation of the Grey-elven and High-elven communities. Supporting only one would have constituted linguistic favoritism and risked a formal grievance from the White Council. Sindarin is the vernacular of Middle-earth (used daily by the Elves of Rivendell and Lothlórien), while Quenya is the ceremonial High-elven tongue -- think of it as the Latin of Arda. Both use ISO 639-3 codes, because even the ISO registrar recognizes that Tolkien's languages have more grammatical rigor than most natural ones. The Quenya word for "FizzBuzz" is `WingeLáma`, which sounds like something you'd hear in the Halls of Mandos.

## License

MIT - Use responsibly. Or irresponsibly. We're not your manager.

---

*Built with an mass contempt for simplicity.*

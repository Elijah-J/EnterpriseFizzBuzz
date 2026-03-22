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

**56,000+ lines** across **108+ files** with **2,257 unit tests** and **143 custom exception classes**, now organized into a Clean Architecture / Hexagonal Architecture package structure with three concentric layers -- because flat module layouts are for startups that haven't yet discovered the Dependency Rule.

## Architecture

The codebase follows **Clean Architecture** (a.k.a. **Hexagonal Architecture**, **Ports and Adapters**, **Onion Architecture** -- because one name for the same concept would be insufficiently enterprise). The flat-file layout has been promoted to a proper layered package structure with three concentric dependency rings, because 32,000 lines of FizzBuzz deserved an architectural diagram that looks like it belongs in a Martin Fowler keynote.

### The Dependency Rule

```
    +---------------------------------------------------------------+
    |                     INFRASTRUCTURE                             |
    |   config, formatters, middleware, observers, plugins,          |
    |   rules_engine, ml_engine, blockchain, circuit_breaker,        |
    |   tracing, auth, i18n, event_sourcing, chaos, feature_flags,   |
    |   sla, cache, migrations, webhooks, service_mesh, hot_reload,  |
    |   rate_limiter                                                  |
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
├── main.py                          # CLI entry point with 55 flags
├── config.yaml                      # YAML-based configuration with 13 sections
│
├── enterprise_fizzbuzz/             # Clean Architecture package root
│   ├── __init__.py
│   ├── __main__.py                  # python -m enterprise_fizzbuzz support
│   │
│   ├── domain/                      # THE INNER CIRCLE (no outward dependencies)
│   │   ├── __init__.py
│   │   ├── models.py                # Dataclasses, enums, and domain models
│   │   ├── exceptions.py            # Custom exception hierarchy (129 exception classes)
│   │   └── interfaces.py            # Abstract base classes for everything
│   │
│   ├── application/                 # USE CASES (depends only on domain)
│   │   ├── __init__.py
│   │   ├── fizzbuzz_service.py      # Service orchestration with Builder pattern
│   │   ├── factory.py               # Abstract Factory + Caching Decorator
│   │   └── ports.py                 # Repository, Unit of Work, and Strategy abstract contracts (hexagonal ports)
│   │
│   └── infrastructure/              # ADAPTERS & FRAMEWORKS (the outer ring)
│       ├── __init__.py
│       ├── adapters/                # Port adapters (Anti-Corruption Layer lives here)
│       │   ├── __init__.py
│       │   └── strategy_adapters.py # ACL: translates engine output into clean domain classifications (~410 lines)
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
│       ├── health.py                # Kubernetes-style health check probes with self-healing (~1,210 lines)
│       ├── metrics.py               # Prometheus-style metrics exporter with counters, gauges, histograms, and ASCII Grafana dashboard (~1,334 lines)
│       ├── migrations.py            # Database Migration Framework for ephemeral RAM schemas (~1,160 lines)
│       ├── container.py             # Dependency Injection Container with IoC, auto-wiring, and Kahn's cycle detection (~608 lines)
│       ├── utils/                   # Enterprise utility modules
│       │   ├── __init__.py
│       │   └── loc.py               # Lines of Code Census Bureau with Overengineering Index (~585 lines)
│       ├── webhooks.py              # Webhook Notification System with HMAC-SHA256, DLQ, and simulated HTTP delivery (~1,142 lines)
│       ├── service_mesh.py          # Service Mesh Simulation with 7 microservices, sidecar proxies, mTLS, and canary routing (~1,839 lines)
│       ├── hot_reload.py            # Configuration Hot-Reload with Single-Node Raft Consensus (~1,787 lines)
│       ├── rate_limiter.py          # Rate Limiting & API Quota Management with Token Bucket, Sliding Window, and Burst Credits (~1,196 lines)
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
│   ├── tracing.py → enterprise_fizzbuzz.infrastructure.tracing
│   └── loc.py → enterprise_fizzbuzz.infrastructure.utils.loc
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
    ├── test_health.py               # 115 health check probe & self-healing tests
    ├── test_metrics.py              # 104 Prometheus metrics collection, exposition & dashboard tests
    ├── test_migrations.py           # 56 database migration & schema management tests
    ├── test_repository.py           # 40 repository pattern & unit of work tests (3 backends)
    ├── test_acl.py                  # 44 Anti-Corruption Layer & strategy adapter tests
    ├── test_webhooks.py             # 54 webhook notification, HMAC signing, DLQ, and retry tests
    ├── test_service_mesh.py         # 83 service mesh, sidecar proxy, mTLS, and canary routing tests
    ├── test_hot_reload.py           # 92 hot-reload, Raft consensus, config diff, and rollback tests
    ├── test_rate_limiter.py          # 79 rate limiting, token bucket, sliding window, burst credit, and quota reservation tests
    ├── test_container.py            # DI Container lifecycle, auto-wiring, and cycle detection tests
    ├── test_contract_coverage.py    # Meta-test: ensures every port/interface has a contract test (quis custodiet ipsos custodes)
    ├── test_no_service_location.py  # Architectural guard: no service-locator anti-pattern in production code
    ├── test_architecture.py         # AST-based import linter enforcing the Dependency Rule
    └── contracts/                   # Contract tests: verify all implementations honor their interface promises
        ├── test_repository_contract.py   # Repository port contract (3 backends, 1 contract, 0 excuses)
        ├── test_strategy_contract.py     # Strategy port contract (4 engines must agree on what "Fizz" means)
        └── test_formatter_contract.py    # Formatter port contract (4 formats, all must serialize correctly)
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
| IoC Container | `container.py` | A fully-featured Inversion of Control container with constructor auto-wiring, four lifetime scopes (Transient, Scoped, Singleton, Eternal), named bindings, factory registration, and Kahn's topological sort for cycle detection -- because manually calling `EventBus()` was far too simple |
| Lifetime Scopes | `container.py` | Transient, Scoped, Singleton, and the comedically identical Eternal -- because "Singleton" sounds too pedestrian for enterprise software |
| Dependency Injection | Everywhere, `container.py` | Constructor injection, because globals are evil. Now with a proper IoC container to prove it |
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
| Anti-Corruption Layer | `strategy_adapters.py` | Four strategy adapters that translate raw engine output (probabilistic ML floats, chain-of-responsibility results, async evaluations) into clean, canonical `FizzBuzzClassification` domain enums -- because allowing ML confidence scores to leak into the domain model would make Eric Evans weep into his copy of the Blue Book |
| Strategy Adapter | `strategy_adapters.py`, `ports.py` | Each evaluation engine gets its own adapter implementing the `StrategyPort` contract, with a factory for wiring. The ML adapter adds ambiguity detection, cross-strategy disagreement tracking, and event emission -- because even the simplest modulo result deserves observability at the translation boundary |
| Ports & Adapters (Persistence) | `ports.py`, `persistence/` | Hexagonal architecture ports for repository and UoW contracts, with three concrete adapter implementations -- ensuring the domain remains blissfully ignorant of whether its results are stored in RAM, SQLite, or artisanal JSON files |
| Contract Testing | `tests/contracts/` | Interface-level conformance tests that run every concrete implementation through the same behavioural gauntlet, ensuring that swapping backends doesn't silently redefine what "correct" means. If an adapter passes the contract, it is blessed; if it doesn't, it is dead to us |
| Health Check Probes | `health.py` | Kubernetes-style liveness, readiness, and startup probes for a CLI application that runs for 0.3 seconds and has never seen a pod in its life |
| Self-Healing | `health.py` | Automated recovery attempts for degraded subsystems, because restarting a cache manually would require human intervention, and humans are a single point of failure |
| Template Method | `health.py` | Abstract `SubsystemHealthCheck` base class with concrete checks for config, circuit breaker, cache, SLA, and ML engine |
| Health Check Registry | `health.py` | Singleton registry for pluggable subsystem health checks, because even health monitoring deserves a Plugin System |
| Prometheus Counter | `metrics.py` | A monotonically increasing metric that only goes up, because in the Enterprise FizzBuzz Platform, progress is irreversible |
| Prometheus Gauge | `metrics.py` | A metric that can go up, down, or sideways -- the chaotic neutral of observability. Tracks Bob McFizzington's stress level with scientific precision |
| Prometheus Histogram | `metrics.py` | Sorts observed values into configurable buckets for latency distribution analysis, because knowing the average FizzBuzz evaluation time is useless without understanding the P99 |
| Prometheus Summary | `metrics.py` | Client-side quantile computation via a naive sorted list, providing P50/P90/P99 latencies with a memory overhead that dwarfs the actual FizzBuzz results |
| Metric Registry | `metrics.py` | Singleton central registry for all metric types with automatic deduplication, naming validation, and thread-safe access -- because every counter deserves a catalog |
| Cardinality Detection | `metrics.py` | Warns when unique label combinations exceed configurable thresholds, preventing the common enterprise mistake of creating more time series than integers to FizzBuzz |
| Prometheus Text Exposition | `metrics.py` | Renders all metrics in the official Prometheus text exposition format with `# HELP` and `# TYPE` annotations -- format compliance is non-negotiable, even when nobody will ever scrape the endpoint |
| ASCII Grafana Dashboard | `metrics.py` | Terminal-based metrics visualization with sparklines, bar charts, and gauge displays, because if you can't graph your FizzBuzz metrics in the terminal, what are you even doing with your life |
| Webhook Observer | `webhooks.py` | Bridges the EventBus to webhook dispatch, converting domain events into signed HTTP POST payloads for downstream consumers who desperately need to know that 15 is FizzBuzz |
| HMAC-SHA256 Payload Signing | `webhooks.py` | Cryptographic signature generation and verification for webhook payloads, preventing the devastating scenario where an attacker modifies a webhook to claim that 15 is "Fizz" instead of "FizzBuzz" |
| Dead Letter Queue | `webhooks.py` | Permanent storage for undeliverable webhook payloads, because even failed notifications deserve a dignified afterlife and eventual forensic analysis |
| Retry with Exponential Backoff | `webhooks.py` | Configurable retry policy with exponential backoff and jitter for webhook deliveries, because the first four failures are just the system building character |
| Simulated HTTP Client | `webhooks.py` | A fully featured HTTP client that never actually sends HTTP requests, providing all the ceremony of distributed communication with none of the network I/O |
| Service Mesh | `service_mesh.py` | Seven microservices in a single process, connected via sidecar proxies with circuit breaking, load balancing, and a control plane -- because monoliths are a state of mind, not an architectural constraint |
| Sidecar Proxy | `service_mesh.py` | Per-service proxies handling routing, mTLS termination, retry, timeout, and circuit breaking -- the same pattern Istio uses for Google-scale services, applied with a straight face to modulo arithmetic |
| mTLS Simulation | `service_mesh.py` | Base64-encodes inter-service payloads and calls it "mutual TLS," providing all the security of real encryption with none of the cryptography |
| Canary Deployment | `service_mesh.py` | Routes a configurable percentage of traffic to the experimental DivisibilityService v2, which uses multiplication instead of modulo -- because even division strategies deserve a progressive rollout |
| Load Balancer | `service_mesh.py` | Round-robin, least-connections, and random strategies for distributing requests across "replicas" of in-memory Python objects -- the same algorithms AWS ALB uses, at 0% of the scale |
| Network Fault Injection | `service_mesh.py` | Configurable latency injection and packet loss between services, because a FizzBuzz evaluation without simulated network partitions is just too reliable |
| Service Discovery | `service_mesh.py` | Health-based endpoint selection with version tracking, because hardcoding `DivisibilityService()` would be an unforgivable act of tight coupling |
| Raft Consensus | `hot_reload.py` | Single-node distributed consensus for configuration changes, achieving 100% election victory rate with zero opponents -- peak democracy in a cluster of one |
| Config Hot-Reload | `hot_reload.py` | File-watching, diffing, validating, and applying config changes without restart, because 0.3 seconds of downtime violates the five-nines FizzBuzz availability SLO |
| Dependency-Aware Reload | `hot_reload.py` | Topological sort of subsystem dependencies to determine correct reload order, because reconfiguring the ML engine before the feature flags could unleash a cascade of modulo anarchy |
| Token Bucket | `rate_limiter.py` | Classic rate limiting algorithm that accumulates tokens at a fixed refill rate up to a maximum capacity -- each FizzBuzz evaluation consumes one token, and when the bucket is empty, the evaluation is denied with a motivational quote about patience |
| Sliding Window Log | `rate_limiter.py` | Timestamp-based rate tracking with configurable window duration, providing precise per-second/minute rate enforcement with sub-millisecond accuracy -- for when fixed windows are insufficiently rigorous for throttling modulo arithmetic |
| Fixed Window Counter | `rate_limiter.py` | The simplest rate limiting algorithm, included for algorithmic completeness and backwards compatibility with rate limiting strategies that predate the invention of sliding windows |
| Burst Credits | `rate_limiter.py` | Unused quota from previous windows carries over as burst credits (up to a configurable maximum), because loyalty should be rewarded even in rate limiting -- the rate-limiting equivalent of airline miles |
| Quota Reservation | `rate_limiter.py` | Pre-books evaluation capacity for scheduled batch operations with reservation expiry, because spontaneous FizzBuzz is for amateurs who don't plan their modulo operations 30 seconds in advance |
| Rate Limit Middleware | `rate_limiter.py` | Pipeline middleware that intercepts every evaluation and enforces rate limits before the number reaches the rule engine, because unrestricted access to the modulo operator is a denial-of-service vulnerability |

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
- **Contract Testing** - Interface-level conformance suites for repositories, strategies, and formatters -- every concrete implementation must survive the same behavioural gauntlet, plus a meta-test that verifies every port has a contract test (because untested contracts are just suggestions)
- **Anti-Corruption Layer (ACL)** - Four strategy adapters forming a protective boundary between the evaluation engines and the domain model, with ML ambiguity detection (configurable decision threshold and margin), cross-strategy disagreement tracking, and domain event emission -- because allowing a neural network's probabilistic confidence scores to contaminate the sacred `FizzBuzzClassification` enum would be an act of architectural heresy
- **Dependency Injection Container** - A fully-featured IoC container with constructor auto-wiring via `typing.get_type_hints()`, four lifetime strategies (Transient, Scoped, Singleton, Eternal), named bindings, factory registration, fluent API, and Kahn's topological sort cycle detection at registration time -- because calling `EventBus()` directly was an affront to enterprise architecture. The container is ADDITIVE: it does not replace the existing Builder pattern wiring, it merely provides an additional layer of abstraction on top of the existing layers of abstraction, like a parfait of unnecessary indirection
- **Lines of Code Census Bureau** - A production-grade codebase metrics engine that walks every file, classifies it by language and architectural layer, computes the Overengineering Index (OEI = total lines / 2, where 2 is the minimal FizzBuzz solution), renders an ASCII dashboard with box-drawing characters, and attributes 100% of lines to Bob McFizzington -- because you can't manage what you can't measure, and you can't overengineer what you can't quantify
- **Prometheus-Style Metrics Exporter** - Four Prometheus-compatible metric types (Counter, Gauge, Histogram, Summary) with a thread-safe MetricRegistry, automatic label injection (strategy, locale, chaos_enabled, is_tuesday), Prometheus text exposition format export that nobody will ever scrape, a cardinality explosion detector that prevents you from creating more time series than integers, and an ASCII Grafana-style dashboard with sparklines and bar charts -- because the only thing more important than computing `n % 3` correctly is collecting time-series data about *how* you computed it. Bob McFizzington's stress level is tracked as a Gauge, starting at 42.0 (it's always 42)
- **Kubernetes-Style Health Check Probes** - Liveness, readiness, and startup probes with five subsystem health checks (config, circuit breaker, cache coherence, SLA budget, ML engine), a self-healing manager with exponential backoff recovery, and an ASCII health dashboard with traffic-light indicators -- because a FizzBuzz CLI that runs for 0.3 seconds deserves the same operational scrutiny as a Kubernetes pod serving millions of requests, and if the ML engine is having an existential crisis, the entire platform should be in EXISTENTIAL_CRISIS status
- **Webhook Notification System** - A production-grade event-driven webhook dispatch engine with HMAC-SHA256 payload signing, configurable retry with exponential backoff, a Dead Letter Queue for permanently failed deliveries, simulated HTTP POST delivery (because real HTTP is for deployed services), an Observer bridge from the EventBus, and an ASCII dashboard for delivery statistics -- because when the number 15 is evaluated as "FizzBuzz," every downstream microservice in the constellation must be immediately informed via a cryptographically signed notification, and if the notification fails five times, it deserves a permanent resting place in the DLQ where future forensic analysts can determine exactly why Slack didn't hear about `n % 3`
- **Service Mesh Simulation** - Seven microservices (`NumberIngestionService`, `DivisibilityService`, `ClassificationService`, `FormattingService`, `AuditService`, `CacheService`, `OrchestratorService`) running in the same process, connected through sidecar proxies with mTLS (base64, obviously), per-service circuit breaking, round-robin/least-connections/random load balancing across "replicas," canary routing to an experimental v2 DivisibilityService, configurable network fault injection (latency and packet loss), health-based service discovery, a mesh control plane with traffic policies, and an ASCII topology diagram -- because decomposing a modulo operation into seven in-memory microservices communicating through base64-encoded messages is exactly the kind of distributed systems design that Google would endorse (if they saw it, which they won't)
- **Configuration Hot-Reload with Raft Consensus** - A file-watching, config-diffing, dependency-aware reload orchestrator coordinated through a single-node Raft consensus protocol that holds elections against zero opponents and wins unanimously every time. Includes a `ConfigDiffEngine` for minimal changeset computation, a `ConfigValidator` with JSON Schema enforcement (the "YOLO" eviction policy shall never return), a `ReloadOrchestrator` that topologically sorts subsystem dependencies before applying changes, a `ConfigRollbackManager` for reverting failed reloads, and an ASCII dashboard displaying Raft term numbers, election results, and reload history -- because re-reading a YAML file without distributed consensus would be an act of architectural recklessness. All config changes are event-sourced and validated before application, ensuring that the FizzBuzz platform can reconfigure itself at runtime without the 0.3-second restart that would violate its five-nines availability SLO
- **Rate Limiting & API Quota Management** - Three complementary rate limiting algorithms (Token Bucket, Sliding Window Log, Fixed Window Counter) with a burst credit ledger for carrying over unused quota, a reservation system for pre-booking evaluation capacity, motivational patience quotes in rate limit headers (`X-FizzBuzz-Please-Be-Patient`), per-operation configurable quotas, and an ASCII rate limit dashboard with per-bucket fill levels and quota utilization sparklines -- because unrestricted access to `n % 3` is a denial-of-service vulnerability that no self-respecting enterprise platform can afford to ignore. The motivational quotes are load-bearing
- **Custom Exception Hierarchy** - 143 exception classes for every conceivable FizzBuzz failure mode
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

# Health Check Probes: run all three probes (liveness, readiness, startup)
python main.py --health --range 1 20

# Liveness probe only: verify that FizzBuzz can still FizzBuzz
python main.py --liveness --range 1 15

# Readiness probe only: check all subsystem health indicators
python main.py --readiness --range 1 20

# Health dashboard: see the full ASCII health status after execution
python main.py --health --health-dashboard --range 1 30

# Self-healing mode: auto-recover degraded subsystems with exponential backoff
python main.py --health --self-heal --range 1 50

# Health + circuit breaker: monitor circuit health in real time
python main.py --health --health-dashboard --circuit-breaker --circuit-status --range 1 30

# Health + chaos: watch the probes detect chaos-induced degradation
python main.py --health --health-dashboard --self-heal --chaos --chaos-level 3 --range 1 30

# Peak operational readiness: health + SLA + tracing + cache + ML (the dashboard will be glorious)
python main.py --health --health-dashboard --self-heal --sla --sla-dashboard --trace --cache --strategy machine_learning --range 1 20

# Prometheus metrics: collect counters, gauges, and histograms during evaluation
python main.py --metrics --range 1 50

# Prometheus metrics with text exposition export (the format nobody will scrape)
python main.py --metrics --metrics-export --range 1 100

# Prometheus metrics with ASCII Grafana dashboard (sparklines in the terminal)
python main.py --metrics --metrics-dashboard --range 1 100

# Full observability stack: metrics + tracing + SLA + health (peak telemetry)
python main.py --metrics --metrics-dashboard --trace --sla --sla-dashboard --health --health-dashboard --range 1 30

# Metrics + chaos: watch the counters climb as the monkey wreaks havoc
python main.py --metrics --metrics-dashboard --chaos --chaos-level 3 --range 1 50

# Peak enterprise: metrics + cache + circuit breaker + ML + tracing (every subsystem instrumented)
python main.py --metrics --metrics-dashboard --metrics-export --cache --circuit-breaker --strategy machine_learning --trace --range 1 20

# Webhook notifications: enable webhook dispatch for FizzBuzz events
python main.py --webhooks --range 1 30

# Webhook with a registered endpoint (simulated HTTP POST, obviously)
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --range 1 20

# Webhook with HMAC-SHA256 secret and delivery log
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-secret "my-very-secret-key" --webhook-log --range 1 20

# Webhook test: fire a test event to all registered endpoints and exit
python main.py --webhooks --webhook-url https://hooks.example.com/test --webhook-test

# Webhook with Dead Letter Queue inspection (see what failed to deliver)
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-dlq --range 1 50

# Webhook with event filtering: only subscribe to specific event types
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-events "evaluation.completed,circuit_breaker.opened" --range 1 30

# Full notification stack: webhooks + metrics + tracing + chaos (peak telemetry)
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-log --metrics --trace --chaos --range 1 20

# Service mesh: decompose FizzBuzz into 7 microservices with sidecar proxies
python main.py --service-mesh --range 1 20

# Service mesh with ASCII topology diagram: see the request flow between services
python main.py --service-mesh --mesh-topology --range 1 15

# Service mesh with network fault injection: add latency and packet loss
python main.py --service-mesh --mesh-latency --mesh-packet-loss --range 1 30

# Canary deployment: route traffic to experimental DivisibilityService v2
python main.py --service-mesh --canary --range 1 20

# Full service mesh stack: latency + packet loss + canary + topology (peak microservices)
python main.py --service-mesh --mesh-latency --mesh-packet-loss --canary --mesh-topology --range 1 20

# Service mesh + chaos + circuit breaker: maximum distributed systems entropy
python main.py --service-mesh --mesh-latency --chaos --chaos-level 3 --circuit-breaker --circuit-status --range 1 20

# Peak enterprise: service mesh + metrics + tracing + SLA + health (the topology diagram will be glorious)
python main.py --service-mesh --mesh-topology --metrics --metrics-dashboard --trace --sla --sla-dashboard --health --health-dashboard --range 1 15

# Hot-Reload: watch config.yaml for changes and reconfigure at runtime (Raft consensus included)
python main.py --hot-reload --range 1 30

# Hot-Reload with custom poll interval (every 2 seconds instead of 500ms)
python main.py --hot-reload --hot-reload-interval 2000 --range 1 50

# Config validation: validate config.yaml against the schema without running
python main.py --config-validate

# Config diff: show changes between current and on-disk configuration
python main.py --config-diff

# Config history: display the event-sourced configuration change log
python main.py --config-history

# Hot-Reload + SLA + health: reconfigure the platform without violating your SLOs
python main.py --hot-reload --sla --sla-dashboard --health --health-dashboard --range 1 30

# Peak enterprise: hot-reload + service mesh + metrics + tracing (every subsystem reconfigurable at runtime)
python main.py --hot-reload --service-mesh --metrics --metrics-dashboard --trace --range 1 20

# Rate limiting: throttle FizzBuzz evaluations with the default token bucket algorithm
python main.py --rate-limit --range 1 100

# Rate limiting with sliding window algorithm at 30 requests per minute
python main.py --rate-limit --rate-limit-algo sliding_window --rate-limit-rpm 30 --range 1 50

# Rate limiting with burst credits: carry over unused quota from previous windows
python main.py --rate-limit --rate-limit-burst-credits --range 1 100

# Rate limit dashboard: see per-bucket fill levels and quota utilization
python main.py --rate-limit --rate-limit-dashboard --range 1 100

# Reserve evaluation capacity: pre-book 20 evaluations before running
python main.py --rate-limit --rate-limit-reserve 20 --range 1 50

# Full throttling stack: rate limiting + circuit breaker + SLA + metrics (peak capacity management)
python main.py --rate-limit --rate-limit-dashboard --rate-limit-burst-credits --circuit-breaker --circuit-status --sla --sla-dashboard --metrics --range 1 30
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
--health             Enable Kubernetes-style health check probes for the FizzBuzz platform
--liveness           Run the liveness probe (canary evaluation: can FizzBuzz still FizzBuzz?)
--readiness          Run the readiness probe (are all subsystems initialized and not panicking?)
--startup-probe      Run the startup probe (has the boot sequence completed, or are we still mining the genesis block?)
--health-dashboard   Display the comprehensive health check dashboard after execution
--self-heal          Enable the self-healing manager (automated recovery with exponential backoff)
--metrics            Enable Prometheus-style metrics collection for FizzBuzz evaluation
--metrics-export     Export all metrics in Prometheus text exposition format after execution
--metrics-dashboard  Display the ASCII Grafana metrics dashboard after execution
--webhooks           Enable the Webhook Notification System for event-driven FizzBuzz telemetry
--webhook-url URL    Register a webhook endpoint URL (can be specified multiple times)
--webhook-events EVENTS  Comma-separated list of event types to subscribe to (default: all)
--webhook-secret SECRET  HMAC-SHA256 secret for signing webhook payloads (default: from config)
--webhook-test       Send a test webhook to all registered endpoints and exit
--webhook-log        Display the webhook delivery log after execution
--webhook-dlq        Display the Dead Letter Queue contents after execution
--service-mesh       Enable the Service Mesh Simulation: decompose FizzBuzz into 7 microservices with sidecar proxies
--mesh-topology      Display the ASCII service mesh topology diagram after execution
--mesh-latency       Enable simulated network latency injection between mesh services
--mesh-packet-loss   Enable simulated packet loss between mesh services
--canary             Enable canary deployment routing (v2 DivisibilityService uses multiplication instead of modulo)
--hot-reload         Enable Configuration Hot-Reload with Single-Node Raft Consensus (watches config.yaml for changes)
--hot-reload-interval MS  Poll interval in milliseconds for config file changes (default: 500)
--config-validate    Validate config.yaml against the configuration schema and exit
--config-diff        Display the diff between current and on-disk configuration
--config-history     Display the event-sourced configuration change history
--rate-limit         Enable Rate Limiting & API Quota Management for FizzBuzz evaluations
--rate-limit-rpm N   Maximum FizzBuzz evaluations per minute (default: 60)
--rate-limit-algo ALGO  Rate limiting algorithm: token_bucket, sliding_window, fixed_window (default: token_bucket)
--rate-limit-dashboard  Display the ASCII rate limit dashboard with per-bucket fill levels and quota utilization
--rate-limit-reserve N  Pre-reserve N evaluation slots before execution (capacity planning for FizzBuzz)
--rate-limit-burst-credits  Enable burst credit carryover from unused quota (loyalty rewards for patient evaluators)
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

## Health Check Architecture

The Health Check Probes subsystem implements Kubernetes-style liveness, readiness, and startup probes for the Enterprise FizzBuzz Platform -- because a CLI application that runs for 0.3 seconds and exits deserves the same operational health monitoring infrastructure as a Kubernetes pod serving millions of requests behind an Istio service mesh. If the ML engine is experiencing an existential crisis, or the cache's MESI coherence state has degraded into philosophical uncertainty, the probes will detect it, report it, and -- with self-healing enabled -- attempt to fix it while you watch.

The system implements five concrete subsystem health checks (config, circuit breaker, cache coherence, SLA budget, ML engine), three probe types (liveness, readiness, startup), a self-healing manager with exponential backoff recovery, and an ASCII dashboard that renders the health status of every subsystem with traffic-light color indicators and motivational uptime statistics.

```
    PROBE LAYER                                SUBSYSTEM CHECKS
    ===========                                ================

    +================+
    | LivenessProbe  |--- canary eval -------> evaluate(15) == "FizzBuzz"?
    | "Can it        |                         (if not, arithmetic is broken
    |  FizzBuzz?"    |                          and we have bigger problems)
    +================+

    +================+     +-----------------+
    | ReadinessProbe |---->| HealthCheck     |---> ConfigHealthCheck
    | "Are all       |     | Registry        |---> CircuitBreakerHealthCheck
    |  subsystems    |     | (pluggable)     |---> CacheCoherenceHealthCheck
    |  ready?"       |     +-----------------+---> SLABudgetHealthCheck
    +================+                        ---> MLEngineHealthCheck

    +================+
    | StartupProbe   |--- milestone tracker -> config_loaded? ML_trained?
    | "Has it        |                         cache_warmed? genesis_mined?
    |  booted yet?"  |                         (14 milestones, 30s timeout)
    +================+

    +================+     +-----------------+
    | SelfHealing    |---->| For each DOWN/  |---> check.recover()
    | Manager        |     | DEGRADED check  |     (retry with backoff)
    | "Fix it        |     | run recovery    |     (max 3 attempts)
    | yourself"      |     +-----------------+     (then give up gracefully)
    +================+

    +================+
    | HealthDashboard|--- ASCII rendering ---> traffic-light status indicators,
    | "Pretty        |                         uptime statistics, per-subsystem
    |  boxes"        |                         details, and motivational quotes
    +================+
```

**Key components:**
- **SubsystemHealthCheck** - Abstract base class with Template Method pattern: `get_name()`, `check()`, and `recover()`. Five concrete implementations cover every subsystem that could conceivably be "unhealthy" (in a CLI that runs for less time than it takes to read this sentence)
- **HealthCheckRegistry** - Singleton registry for pluggable health checks. Each subsystem registers its diagnostic, because even health monitoring deserves a Plugin System
- **LivenessProbe** - Performs a canary evaluation (`evaluate(15)` must return `"FizzBuzz"`) to verify that basic arithmetic still works. If this probe fails, the platform has achieved a state of mathematical impossibility
- **ReadinessProbe** - Aggregates all registered subsystem health checks and reports the worst status found. A single DEGRADED subsystem degrades the entire platform, because a chain is only as healthy as its least healthy link
- **StartupProbe** - Tracks boot sequence milestones (config loaded, ML trained, cache warmed, genesis block mined) with a configurable timeout. The startup probe exists to answer the question "has the 14-second boot sequence completed, or is the migration framework still running?"
- **SelfHealingManager** - When a subsystem reports DOWN or DEGRADED, the self-healing manager invokes `recover()` with exponential backoff retries. Recovery actions include resetting circuit breakers, clearing corrupted caches, and reinitializing the DI container. The manager logs every attempt with the gravity of an SRE responding to a P1 incident
- **HealthDashboard** - ASCII-art dashboard renderer with box-drawing characters, traffic-light status indicators (UP/DEGRADED/DOWN/EXISTENTIAL_CRISIS), per-subsystem response times, and an overall platform health summary

### Health Statuses

| Status | Meaning | Icon | When |
|--------|---------|------|------|
| `UP` | Subsystem is fully operational | GREEN | Everything is fine. Enjoy this moment; it won't last |
| `DEGRADED` | Subsystem is functional but impaired | YELLOW | The circuit breaker is HALF_OPEN, or the ML confidence is wavering |
| `DOWN` | Subsystem has failed | RED | The circuit breaker is OPEN, or the cache has achieved incoherence |
| `EXISTENTIAL_CRISIS` | Subsystem has transcended conventional failure modes | PURPLE | The ML engine has begun questioning whether numbers are even real |
| `UNKNOWN` | Health status cannot be determined | GREY | The health check itself has failed, which is a meta-failure of the highest order |

### Subsystem Health Checks

| Check | Subsystem | What It Monitors | Recovery Action |
|-------|-----------|-----------------|-----------------|
| `ConfigHealthCheck` | Configuration Manager | Config singleton loaded, basic properties accessible | Reload configuration from YAML |
| `CircuitBreakerHealthCheck` | Circuit Breaker | Circuit state (CLOSED=UP, HALF_OPEN=DEGRADED, OPEN=DOWN) | Reset circuit breaker to CLOSED |
| `CacheCoherenceHealthCheck` | Cache Layer | MESI coherence state distribution, invalid entry ratio | Clear invalid entries, reset coherence states |
| `SLABudgetHealthCheck` | SLA Monitor | Error budget remaining, burn rate, SLO compliance | Reset error budget counters (the accounting equivalent of shredding the evidence) |
| `MLEngineHealthCheck` | ML Engine | Neural network loaded, canary prediction accuracy, confidence scores | Retrain the neural network from scratch (200 epochs of unnecessary relearning) |

| Spec | Value |
|------|-------|
| Probe types | 3 (Liveness, Readiness, Startup) |
| Subsystem health checks | 5 (Config, CircuitBreaker, CacheCoherence, SLABudget, MLEngine) |
| Health statuses | 5 (UP, DEGRADED, DOWN, EXISTENTIAL_CRISIS, UNKNOWN) |
| Liveness canary | `evaluate(15) == "FizzBuzz"` (the universal constant) |
| Startup milestones | Configurable (default: config, ML, cache, blockchain) |
| Startup timeout | 30 seconds (configurable) |
| Self-healing max retries | 3 (configurable, with exponential backoff) |
| Self-healing backoff | Exponential (base * 2^attempt ms) |
| Thread safety | Full (threading.Lock on registry and probes) |
| Custom exceptions | 6 (HealthCheckError, LivenessProbeFailedError, ReadinessProbeFailedError, StartupProbeFailedError, SelfHealingFailedError, HealthDashboardRenderError) |
| ASCII dashboard | Traffic-light indicators, uptime stats, per-subsystem details |
| Kubernetes pods monitored | 0 (but the spiritual alignment is immaculate) |
| Lines of code | ~1,210 (for monitoring a process that exits in 0.3 seconds) |

## Metrics Architecture

The Prometheus-Style Metrics Exporter implements a production-grade metrics collection, exposition, and visualization pipeline for the Enterprise FizzBuzz Platform -- because computing `n % 3` without counters, gauges, histograms, and an ASCII Grafana dashboard would be like running a nuclear reactor without a control panel. Every modulo operation is measured, labeled, bucketed, quantiled, and dashboarded.

The system supports four Prometheus-compatible metric types, a thread-safe `MetricRegistry` singleton, automatic label injection, Prometheus text exposition format export (which nobody will ever scrape because this is a CLI tool, not an HTTP server), a cardinality explosion detector, and an ASCII dashboard with sparklines. The `MetricsCollector` subscribes to the `EventBus` as an Observer, while `MetricsMiddleware` wraps every evaluation to record latency histograms.

```
    EventBus                         MetricRegistry (Singleton)
    ========                         ==========================
       |                                    |
       | subscribe                          | register
       v                                    v
  +------------------+          +--------+--------+--------+---------+
  | MetricsCollector |          | Counter | Gauge | Histo- | Summary |
  | (Observer)       |--------->|         |       | gram   |         |
  +------------------+  inc()   +--------+--------+--------+---------+
                        set()           |
                        observe()       v
                                 +------------------+
                                 | PrometheusText   |
  +------------------+           | Exporter         |----> stdout
  | MetricsMiddleware|           +------------------+      (# HELP / # TYPE / metric{labels} value)
  | (IMiddleware)    |                  |
  +------------------+                 v
       |                         +------------------+
       | observe(latency)        | MetricsDashboard |----> ASCII Grafana
       +------------------------>| (sparklines,     |      (terminal art)
                                 |  bar charts)     |
                                 +------------------+
                                        |
                                 +------------------+
                                 | Cardinality      |
                                 | Detector         |----> warnings
                                 +------------------+
```

**Key components:**
- **MetricRegistry** - Thread-safe singleton central registry for all metric types with automatic deduplication and naming validation
- **Counter** - Monotonically increasing metric. Goes up. Never down. The optimist of the metric world
- **Gauge** - A value that can go up, down, or sideways. Tracks Bob McFizzington's stress level (initial value: 42.0)
- **Histogram** - Sorts observed values into configurable buckets for latency distribution analysis with `+Inf` overflow
- **Summary** - Client-side quantile computation (P50/P90/P99) via a naive sorted list
- **PrometheusTextExporter** - Renders all metrics in the official Prometheus text exposition format with `# HELP` and `# TYPE` annotations
- **MetricsCollector** - Observer that subscribes to EventBus and instruments evaluation counts, result distributions, and subsystem events
- **MetricsMiddleware** - Pipeline middleware that records `fizzbuzz_evaluation_duration_seconds` histogram for every evaluation
- **CardinalityDetector** - Warns when unique label combinations exceed the configured threshold (default: 100)
- **MetricsDashboard** - ASCII Grafana-inspired terminal dashboard with sparklines, bar charts, and gauge displays

### Metric Types

| Type | Behavior | Use Case |
|------|----------|----------|
| Counter | Monotonically increasing; `inc()` and `inc_by(n)` | Total evaluations, cache hits, circuit breaker trips |
| Gauge | Arbitrary value; `set()`, `inc()`, `dec()` | Cache size, active middleware count, Bob's stress level |
| Histogram | Observes values into configurable buckets | Evaluation latency distribution (0.001ms to 10s) |
| Summary | Computes P50/P90/P99 quantiles client-side | Streaming latency percentiles |

| Spec | Value |
|------|-------|
| Metric types | 4 (Counter, Gauge, Histogram, Summary) |
| Default histogram buckets | 12 (0.001 to 10.0 seconds) |
| Label support | Full (automatic + custom labels per metric) |
| Cardinality threshold | 100 unique label combinations (configurable) |
| Export format | Prometheus text exposition (the only option, but configurable anyway) |
| Thread safety | Full (threading.Lock on registry and all metric types) |
| Custom exceptions | 5 (MetricRegistrationError, MetricNotFoundError, InvalidMetricOperationError, CardinalityExplosionError, MetricsExportError) |
| Bob's initial stress level | 42.0 (it's always 42) |
| ASCII dashboard | Sparklines, bar charts, gauge displays |
| Prometheus endpoints scraped | 0 (this is a CLI tool) |
| Lines of code | ~1,334 (for metrics that will never leave stdout) |

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

## Anti-Corruption Layer Architecture

The Anti-Corruption Layer (ACL) implements a protective translation boundary between the FizzBuzz evaluation engines and the domain model -- because the ML engine's probabilistic confidence floats must never be permitted to contaminate the pristine `FizzBuzzClassification` enum. When Eric Evans described the ACL in *Domain-Driven Design*, he was thinking about legacy system integration. We are thinking about modulo arithmetic. The architectural gravity is equivalent.

Each of the four evaluation strategies (Standard, Chain of Responsibility, Parallel Async, Machine Learning) gets its own adapter class implementing the `StrategyPort` contract. The adapters accept raw `FizzBuzzResult` objects (which contain matched rules, metadata, and ML confidence scores) and translate them into clean, canonical `EvaluationResult` value objects that the domain layer can consume without existential dread.

```
    ENGINE SIDE (Infrastructure)              DOMAIN SIDE (Application/Domain)
    ============================              ================================

    +---------------------+                   +---------------------+
    | StandardRuleEngine  |---+               |                     |
    +---------------------+   |               |  EvaluationResult   |
                              |               |  {                  |
    +---------------------+   |  +---------+  |    number: int      |
    | ChainOfResp Engine  |---+->|  A C L  |->|    classification:  |
    +---------------------+   |  | Adapters|  |      FizzBuzzClass  |
                              |  +---------+  |    strategy_name:   |
    +---------------------+   |       |       |      str            |
    | ParallelAsyncEngine |---+       |       |  }                  |
    +---------------------+   |       v       |                     |
                              | ambiguity     +---------------------+
    +---------------------+   | detection,
    | ML Engine           |---+ disagreement        Domain Model
    | (confidence floats) |     tracking,           (clean, canonical,
    +---------------------+     event emission       float-free)
```

The ML adapter is where the ACL earns its keep. While the Standard, Chain, and Async adapters perform straightforward `FizzBuzzResult` -> `FizzBuzzClassification` translation, the ML adapter must also:

1. **Detect ambiguous classifications** -- if any rule's ML confidence score falls within a configurable margin of the decision threshold (default: 0.5 +/- 0.1), the classification is flagged and an event is emitted. In practice this never happens, because cyclical feature encoding makes divisibility trivially separable, but the enterprise demands vigilance
2. **Track cross-strategy disagreements** -- optionally compares ML predictions against a deterministic reference strategy (StandardRuleEngine). If they disagree, an event is published and a warning is logged. Given the ML engine's 100% accuracy, this is purely aspirational governance
3. **Emit domain events** -- ambiguity detections and strategy disagreements are published via the `IEventBus` for downstream observability, because every edge case in the translation boundary deserves a paper trail

The `StrategyAdapterFactory` maps `EvaluationStrategy` enum values to the correct adapter class, handling lazy engine construction and optional event bus / reference strategy wiring. This factory exists because manually selecting the right adapter for each strategy would require the caller to know implementation details -- and that kind of coupling is exactly what the ACL was designed to prevent.

| Spec | Value |
|------|-------|
| Strategy adapters | 4 (Standard, Chain, Async, ML) |
| Port contract | `StrategyPort` (abstract `classify()` + `get_strategy_name()`) |
| ML decision threshold | 0.5 (configurable) |
| ML ambiguity margin | 0.1 (configurable) |
| Cross-strategy tracking | Optional (reference strategy via factory) |
| Domain events emitted | 2 types (CLASSIFICATION_AMBIGUITY, STRATEGY_DISAGREEMENT) |
| Factory | `StrategyAdapterFactory.create()` with lazy engine imports |
| Lines of code | ~410 (all four adapters in one file, because even this project has limits) |
| Eric Evans tears shed | 0 (the Blue Book is safe) |

## Dependency Injection Architecture

The Dependency Injection Container implements a fully-featured IoC (Inversion of Control) container with constructor introspection, lifetime management, topological cycle detection, named bindings, and factory registration -- because manually calling `EventBus()` was far too simple, and what the Enterprise FizzBuzz Platform truly needed was a 600-line abstraction layer that uses `inspect.signature`, `typing.get_type_hints()`, and Kahn's algorithm to wire together objects that could have been instantiated in three lines of code.

The container is **ADDITIVE**. It does not replace the existing `FizzBuzzServiceBuilder` wiring in `__main__.py`. It merely provides a parallel universe of object construction that exists alongside the builder, like two parallel parking lots for the same mall.

```
    +================================================================+
    |                    IoC CONTAINER                                |
    |                                                                |
    |   .register(IEventBus, EventBus, SINGLETON)                    |
    |   .register(IObserver, ConsoleObserver, TRANSIENT)             |
    |   .register(IScopedService, ScopedImpl, SCOPED)                |
    |                                                                |
    |   +--------+    resolve()    +------------------+              |
    |   | Caller |--------------->| Auto-Wiring      |              |
    |   +--------+                | (introspects      |              |
    |                             |  constructor via   |              |
    |                             |  get_type_hints()) |              |
    |                             +--------+----------+              |
    |                                      |                         |
    |                     +----------------+----------------+        |
    |                     |                |                |        |
    |              +------+------+  +------+------+  +-----+-----+  |
    |              | TRANSIENT   |  | SINGLETON   |  | SCOPED    |  |
    |              | (new every  |  | (cached     |  | (per-scope|  |
    |              |  resolve)   |  |  forever)   |  |  context) |  |
    |              +-------------+  +-------------+  +-----------+  |
    +================================================================+

    Cycle Detection (Kahn's Topological Sort):
      At registration time, the container builds a dependency graph
      and runs Kahn's algorithm. If a cycle exists, it is caught
      BEFORE resolve() can cause an infinite recursion that
      stack-overflows your production FizzBuzz evaluation pipeline.
```

**Key components:**
- **Container** - The central IoC container with fluent `register().register().register()` API, recursive `resolve()`, and `reset()` for the nuclear option
- **Lifetime** - Four-member enum: TRANSIENT (born and discarded), SCOPED (per-context), SINGLETON (the classic), ETERNAL (functionally identical to Singleton, but with more gravitas)
- **ScopeContext** - Context manager for scoped lifetime management, where scoped instances are cached per-scope and ceremonially discarded upon exit
- **Registration** - Dataclass binding an interface to its implementation, lifetime, optional name, and optional factory callable
- **Cycle Detection** - Kahn's topological sort validates the dependency graph at registration time, because catching cycles early is infinitely preferable to catching them at 3 AM via a `RecursionError`

### Lifetime Strategies

| Lifetime | Behavior | When To Use | Enterprise Justification |
|----------|----------|-------------|--------------------------|
| `TRANSIENT` | New instance every `resolve()` | Stateless services | Commitment-free. The Tinder of object lifetimes |
| `SCOPED` | One instance per `ScopeContext` | Per-request shared state | Perfect for things that need to share state within a request, assuming your FizzBuzz platform processes concurrent requests (it does not) |
| `SINGLETON` | One instance for the container lifetime | Shared state, caches | The classic. The original. The pattern that launched a thousand blog posts about why it's an anti-pattern |
| `ETERNAL` | Functionally identical to SINGLETON | When SINGLETON lacks gravitas | Singletons are temporary. Eternal instances transcend the mortal plane of garbage collection |

| Spec | Value |
|------|-------|
| Lifetime strategies | 4 (Transient, Scoped, Singleton, Eternal) |
| Auto-wiring | Constructor introspection via `typing.get_type_hints()` |
| Optional parameter handling | `Optional[X]` resolves to `None` if no binding exists |
| Cycle detection | Kahn's topological sort at registration time |
| Named bindings | Multiple implementations per interface via `name=` |
| Factory registration | Custom callables for exotic construction requirements |
| Fluent API | `container.register(...).register(...).register(...)` |
| Thread safety | Not required (single-threaded FizzBuzz, as is tradition) |
| Custom exceptions | 4 (CircularDependencyError, DuplicateBindingError, MissingBindingError, ScopeError) |
| Lines of code | ~608 (for an abstraction over `EventBus()`) |
| Java enterprise architects who feel at home | All of them |

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

## Webhook Architecture

The Webhook Notification System implements a production-grade event-driven dispatch engine for broadcasting FizzBuzz evaluation events to downstream consumers -- because when `evaluate(15)` returns `"FizzBuzz"`, every Slack channel, PagerDuty integration, and CI/CD pipeline in the enterprise constellation must be immediately informed via a cryptographically signed HTTP POST request. The deliveries are, of course, entirely simulated. No actual HTTP requests leave this process. But the HMAC-SHA256 signatures are real, the exponential backoff is calculated, and the Dead Letter Queue faithfully preserves every undeliverable notification for future forensic analysis and post-incident regret.

The system bridges the existing `EventBus` via a `WebhookObserver` (Observer pattern), converting domain events into signed payloads dispatched through a `SimulatedHTTPClient` that returns configurable success/failure rates. Failed deliveries are retried with exponential backoff (Strategy pattern), and permanently failed payloads are interred in a `DeadLetterQueue` -- the final resting place for FizzBuzz notifications that the outside world refused to acknowledge.

```
    EVENT BUS                    WEBHOOK SYSTEM                    SIMULATED NETWORK
    =========                    ==============                    =================

    +-----------+                +-----------------+
    | EventBus  |--- notify --->| WebhookObserver |
    | (domain   |                | (bridges events |
    |  events)  |                |  to webhooks)   |
    +-----------+                +--------+--------+
                                          |
                                          v
                                 +--------+--------+
                                 | WebhookManager  |
                                 | (registry,      |
                                 |  dispatch,      |
                                 |  retry logic)   |
                                 +--------+--------+
                                          |
                         +----------------+----------------+
                         |                |                |
                         v                v                v
                  +------+------+  +------+------+  +------+------+
                  | Endpoint A  |  | Endpoint B  |  | Endpoint C  |
                  | (filtered)  |  | (all events)|  | (filtered)  |
                  +------+------+  +------+------+  +------+------+
                         |                |                |
                         v                v                v
                  +------+------+  +------+------+  +------+------+
                  | Signature   |  | Signature   |  | Signature   |
                  | Engine      |  | Engine      |  | Engine      |
                  | (HMAC-256)  |  | (HMAC-256)  |  | (HMAC-256)  |
                  +------+------+  +------+------+  +------+------+
                         |                |                |
                         v                v                v
                  +------+------+  +------+------+  +------+------+
                  | Simulated   |  | Simulated   |  | Simulated   |
                  | HTTP POST   |  | HTTP POST   |  | HTTP POST   |
                  +------+------+  +------+------+  +------+------+
                         |                |                |
                    success?          success?          success?
                    /      \          /      \          /      \
                   v        v       v        v        v        v
                 [done]   retry   [done]   retry    [done]   retry
                          with            with              with
                          backoff         backoff            backoff
                            |               |                  |
                            v               v                  v
                     +------+------+  (max retries?)     (max retries?)
                     | Dead Letter |       |                   |
                     | Queue       |<------+-------------------+
                     +-------------+  (permanently failed)
```

**Key components:**
- **WebhookManager** - Central orchestrator for endpoint registration, event dispatch, retry logic, and delivery logging. Thread-safe with a reentrant lock, because concurrent FizzBuzz webhook delivery is a scenario we must be prepared for
- **WebhookSignatureEngine** - HMAC-SHA256 signature generation and verification (RFC 2104), ensuring payload integrity against the catastrophic threat of webhook tampering
- **RetryPolicy** - Exponential backoff with configurable base delay, multiplier, and cap. Each retry doubles the wait time, giving the simulated network time to recover from its simulated outage
- **SimulatedHTTPClient** - A fully-featured HTTP client that performs no actual HTTP. Returns configurable success rates with simulated response times and status codes. Enterprise-grade make-believe
- **DeadLetterQueue** - Thread-safe, bounded queue for permanently failed deliveries. Each entry preserves the original payload, all attempt results, and the final failure reason -- because even dead webhooks deserve a complete autopsy
- **WebhookObserver** - Implements `IObserver` to bridge the domain `EventBus` into the webhook dispatch pipeline, filtering events by subscription before dispatch
- **WebhookDashboard** - ASCII art dashboard rendering delivery statistics, endpoint status, delivery logs, and DLQ contents

### Webhook Payload

Every webhook delivery includes a signed JSON payload with enterprise-grade headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Type` | `application/json` | Because webhook payloads are JSON, not YAML (we have standards) |
| `X-FizzBuzz-Event` | Event type string | So the consumer knows whether to panic |
| `X-FizzBuzz-Signature` | `sha256=<hex>` | HMAC-SHA256 signature for payload verification |
| `X-FizzBuzz-Delivery` | UUID | Unique delivery ID for idempotency and audit trails |
| `X-FizzBuzz-Seriousness-Level` | `MAXIMUM` | Mandatory. Non-negotiable. Always MAXIMUM |

### Retry Policy

| Spec | Value |
|------|-------|
| Max retries | 5 (configurable) |
| Backoff base | 1,000 ms |
| Backoff multiplier | 2.0 |
| Backoff cap | 60,000 ms |
| Backoff formula | `min(base * multiplier ^ attempt, cap)` |
| Jitter | None (deterministic backoff, because chaos is the Chaos Monkey's job) |

### Dead Letter Queue

| Spec | Value |
|------|-------|
| Max size | 1,000 entries (configurable) |
| Entry contents | Original payload, all delivery attempt results, failure reason, timestamp |
| Thread safety | Full (threading.Lock) |
| Retention policy | Permanent (until process exits, which is 0.3 seconds) |
| Custom exception | `WebhookDeadLetterQueueFullError` (when even the graveyard is full) |

| Spec | Value |
|------|-------|
| Endpoint registration | Dynamic, with event type filtering |
| Payload signing | HMAC-SHA256 (RFC 2104) |
| Delivery simulation | Configurable success rate and response times |
| Retry policy | Exponential backoff with configurable parameters |
| Dead Letter Queue | Bounded, thread-safe, with full attempt history |
| Event types | All domain events (evaluation.completed, circuit_breaker.opened, etc.) |
| Thread safety | Full (threading.RLock on all operations) |
| Custom exceptions | 6 (WebhookDeliveryError, WebhookSignatureError, WebhookRetryExhaustedError, WebhookEndpointValidationError, WebhookPayloadSerializationError, WebhookDeadLetterQueueFullError) |
| ASCII dashboard | Delivery statistics, endpoint status, delivery log, DLQ viewer |
| Actual HTTP requests sent | 0 (but the architecture is ready) |

## Service Mesh Architecture

The Service Mesh Simulation decomposes the monolithic FizzBuzz evaluation into seven "microservices" -- all running in the same process, communicating through sidecar proxies that simulate mTLS encryption (base64 encoding), network latency, packet loss, service discovery, and circuit breaking per service pair. Because everyone knows that a 100-line Python script becomes more reliable when you decompose it into 7 services communicating over a simulated network with configurable fault injection.

Each service is wrapped in a `SidecarProxy` that handles mTLS termination (base64 encode/decode, which is basically encryption if you squint), retries, and circuit breaking. The mesh control plane manages service registration, health-based endpoint selection, traffic policies (canary routing, latency injection, packet loss), and load balancing across "replicas" (multiple instances of the same class with round-robin, least-connections, or random dispatch).

```
    MESH CONTROL PLANE
    ==================

    +==================================================================+
    |                    SERVICE MESH TOPOLOGY                          |
    +==================================================================+
    |                                                                    |
    |   +------------------+         +-----------------------+          |
    |   | NumberIngestion  |-------->| DivisibilityService   |          |
    |   | Service          |  mTLS   | (v1: modulo)          |          |
    |   +------------------+  proxy  | (v2: multiplication)  | <-canary |
    |          |                     +-----------+-----------+          |
    |          |                                 |                      |
    |          v                                 v                      |
    |   +------------------+         +-----------------------+          |
    |   | AuditService     |         | ClassificationService |          |
    |   | (compliance log) |         | (maps to labels)      |          |
    |   +------------------+         +-----------+-----------+          |
    |                                            |                      |
    |          +------------------+              v                      |
    |          | CacheService     |    +-----------------------+        |
    |          | (result cache)   |<---| FormattingService     |        |
    |          +------------------+    | (output string)       |        |
    |                                  +-----------+-----------+        |
    |                                              |                    |
    |                                              v                    |
    |                                  +-----------------------+        |
    |                                  | OrchestratorService   |        |
    |                                  | (coordinates pipeline)|        |
    |                                  +-----------------------+        |
    |                                                                    |
    |   [SidecarProxy] -- each service wrapped in a sidecar proxy       |
    |   [mTLS] --------- base64 "encryption" for inter-service comms    |
    |   [LB] ----------- round-robin / least-conn / random              |
    |   [CB] ----------- per-service-pair circuit breakers               |
    +==================================================================+
```

**The Seven Sacred Microservices:**

| Service | Responsibility | Why It's a Separate Service |
|---------|---------------|----------------------------|
| `NumberIngestionService` | Validates and ingests the number | Because accepting a number without a dedicated ingestion service would be reckless |
| `DivisibilityService` | Computes `n % d == 0` | The core mathematical operation, now available as a service with mTLS |
| `ClassificationService` | Maps divisibility results to Fizz/Buzz/FizzBuzz labels | Because mapping booleans to strings requires service-level isolation |
| `FormattingService` | Formats the output string | String concatenation as a service |
| `AuditService` | Logs everything for compliance | SOX Section 404 demands a separate audit microservice |
| `CacheService` | Caches results | Caching as a service, because the cache middleware wasn't enough abstraction |
| `OrchestratorService` | Coordinates the entire pipeline | The service that calls the other services that do what one function used to do |

**Key components:**
- **ServiceRegistry** - Service discovery with health-based endpoint selection, version tracking, and metadata
- **SidecarProxy** - Per-service proxy handling routing, mTLS (base64), retry, timeout, and circuit breaking
- **MeshControlPlane** - Centralized configuration for traffic policies, rate limits, and security policies
- **TrafficPolicy** - Rules for canary routing, traffic splitting, fault injection, and request mirroring
- **LoadBalancer** - Round-robin, least-connections, and random strategies for "replica" selection
- **mTLSSimulator** - Base64-encodes inter-service payloads and calls it "mutual TLS" with a straight face
- **NetworkSimulator** - Configurable latency injection and packet loss between services
- **ServiceTopologyRenderer** - ASCII art visualization of the service mesh with request flow arrows
- **MeshMiddleware** - Pipeline integration that routes evaluations through the service mesh

### mTLS Security Model

Inter-service communication is "encrypted" using base64 encoding. This provides:
- **Confidentiality**: Anyone who can't decode base64 cannot read the messages (this excludes essentially no one)
- **Integrity**: The messages are JSON, so they're self-validating (they aren't)
- **Authentication**: Each service has a name, and that name is included in the message (this is not authentication)

The mTLS handshake is logged with the gravity of a real TLS negotiation, including "certificate" exchange and "cipher suite" selection. The cipher suite is always `BASE64-WITH-JSON-PAYLOAD-256`, which is not a real cipher suite but sounds enterprise enough to pass a compliance audit conducted entirely via email.

### Canary Deployment

The canary routing feature sends a configurable percentage of traffic to the experimental `DivisibilityService` v2, which uses multiplication instead of modulo to determine divisibility (checking `n / d * d == n`). This enables A/B testing of mathematical operators:

- **v1 (stable)**: Uses `n % d == 0` (the modulo approach, battle-tested since the 3rd century BC)
- **v2 (canary)**: Uses `n / d * d == n` (the multiplication approach, mathematically equivalent but architecturally adventurous)

If the canary produces different results than v1 (it won't, because math), the system logs a disagreement event and initiates a rollback discussion with itself.

| Spec | Value |
|------|-------|
| Microservices | 7 (NumberIngestion, Divisibility, Classification, Formatting, Audit, Cache, Orchestrator) |
| Sidecar proxies | 7 (one per service, because the sidecar pattern demands it) |
| mTLS algorithm | BASE64-WITH-JSON-PAYLOAD-256 (not a real cipher suite) |
| Load balancing strategies | 3 (round-robin, least-connections, random) |
| Network fault injection | Configurable latency (ms) and packet loss (%) |
| Canary routing | Configurable traffic split to v2 DivisibilityService |
| Circuit breakers | Per-service-pair, with configurable failure thresholds |
| Service discovery | Health-based endpoint selection with version tracking |
| Middleware priority | Configurable (integrates with existing pipeline) |
| Thread safety | Full (threading.Lock on all mesh operations) |
| Custom exceptions | 10 (ServiceMeshError, ServiceNotFoundError, MeshMTLSError, SidecarProxyError, MeshCircuitOpenError, MeshLatencyInjectionError, MeshPacketLossError, CanaryDeploymentError, LoadBalancerError, MeshTopologyError) |
| ASCII topology | Full service mesh visualization with request flow arrows |
| Lines of code | ~1,839 (for routing modulo arithmetic through seven in-memory services) |
| Actual network I/O | 0 bytes (but the architecture is ready for multi-region deployment) |

## Hot-Reload Architecture

The Configuration Hot-Reload subsystem implements a production-grade runtime reconfiguration engine for the Enterprise FizzBuzz Platform -- because restarting a Python process that boots in 0.3 seconds would constitute unacceptable downtime for a platform with a 99.999% availability SLO. Instead, a daemon thread polls `config.yaml` every 500 milliseconds, diffs the old and new configuration trees, validates the changeset against a schema, proposes the change to a single-node Raft consensus cluster (which holds an election, wins unanimously, and commits with 100% voter turnout), and then orchestrates a dependency-aware reload of affected subsystems in topological order -- because reloading the ML engine before the feature flags that might have disabled it would be a violation of the Dependency Rule and common sense.

The crown jewel is the **Single-Node Raft Consensus** protocol: a faithful implementation of the Raft distributed consensus algorithm running on exactly one node. Leader elections complete instantly (the candidate always wins, because there are no opponents). Log replication succeeds on the first attempt (the leader replicates to zero followers, achieving majority consensus with itself). Heartbeats are sent to nobody at configurable intervals. The system achieves 100% consensus reliability, 0ms election latency, and unanimous agreement on every configuration change -- a level of distributed systems perfection that multi-node clusters can only dream of.

```
    CONFIG FILE WATCHER                    RAFT CONSENSUS (1 node)
    ===================                    ========================

    +------------------+                   +========================+
    | ConfigWatcher    |                   |    SingleNodeRaft       |
    | (daemon thread,  |--- detects --->   |                        |
    |  500ms poll)     |    change         |  State: LEADER (always)|
    +------------------+                   |  Term:  N              |
             |                             |  Votes: 1/1 (100%)     |
             v                             |  Log:   [entry₁...N]   |
    +------------------+                   +============+===========+
    | ConfigDiffEngine |                                |
    | (deep recursive  |                                | commit
    |  tree diff)      |                                v
    +--------+---------+              +------------------+------------------+
             |                        |                                     |
             v                        v                                     v
    +------------------+     +------------------+              +-----------+-----------+
    | ConfigValidator  |     | ReloadOrchestrator|             | ConfigRollbackManager |
    | (JSON Schema +   |     | (topo-sort deps, |             | (stores last N configs|
    |  custom rules)   |     |  reload in order) |             |  for safe rollback)   |
    +------------------+     +--------+---------+              +-----------------------+
                                      |
                        +-------------+-------------+
                        |             |             |
                        v             v             v
                   [reload       [reload       [reload
                    cache]        ML engine]    feature flags]
                   (in dependency order via topological sort)
```

**Key components:**
- **ConfigWatcher** - Daemon thread polling `config.yaml` at a configurable interval (default: 500ms) with debounce windowing and modification-time detection. When a change is detected, the watcher hands off to the diff engine rather than blindly reloading -- because replacing an entire config tree when only the cache TTL changed is the kind of waste that keeps SREs awake at night
- **ConfigDiffEngine** - Deep recursive comparison of nested config trees, producing structured changesets with path, old value, new value, and change type (ADDED, REMOVED, MODIFIED). Handles nested dicts, lists, and scalar values with the precision of a surgical instrument applied to a problem that could have been solved with `==`
- **SingleNodeRaftConsensus** - A complete Raft implementation with leader election (wins 1-0 every time), log replication (appends to a list of length 1), term management, and commit confirmation. The protocol guarantees that all configuration changes achieve consensus before application -- a guarantee that is trivially satisfied when the electorate consists of a single enthusiastic voter
- **ConfigValidator** - Schema validation with custom rules including type checking, range validation (cache size > 0, chaos probability <= 1.0), and the explicit prohibition of "YOLO" as a cache eviction policy (a hard-won lesson from v0.8)
- **ReloadOrchestrator** - Dependency-aware reload sequencing using topological sort of the subsystem dependency graph. Ensures that subsystems are reconfigured in the correct order (config -> feature_flags -> cache -> ml_engine -> ...), because reloading a downstream subsystem before its upstream dependency has been reconfigured is the runtime equivalent of putting on your shoes before your socks
- **ConfigRollbackManager** - Maintains a bounded history of previous configurations for safe rollback when a reload fails. If the ML engine refuses to accept a new learning rate, the entire configuration is reverted to the last known good state with an apologetic log message
- **SubsystemDependencyGraph** - Models subsystem reload dependencies as a DAG with Kahn's topological sort for cycle detection and ordering, because even configuration reloads deserve graph-theoretic rigor
- **HotReloadDashboard** - ASCII dashboard displaying Raft consensus status (term, state, election results), reload history with timestamps and outcomes, and the subsystem dependency graph -- all rendered in box-drawing characters with the gravity of a mission control terminal

| Spec | Value |
|------|-------|
| File watcher | Daemon thread, configurable poll interval (default: 500ms) |
| Config diff | Deep recursive tree comparison with structured changesets |
| Consensus protocol | Single-Node Raft (1 node, 100% consensus, 0ms elections) |
| Raft states | 3 (FOLLOWER, CANDIDATE, LEADER -- but only LEADER is ever observed) |
| Validation | JSON Schema + custom rules (no more "YOLO" eviction policy) |
| Reload ordering | Topological sort of subsystem dependency DAG |
| Rollback depth | Configurable (default: 10 previous configurations) |
| Event sourcing | All config changes recorded as domain events |
| Thread safety | Full (threading.Lock on all reload operations) |
| Custom exceptions | 9 (HotReloadError, ConfigDiffError, ConfigValidationRejectedError, RaftConsensusError, SubsystemReloadError, ConfigRollbackError, ConfigWatcherError, DependencyGraphCycleError, HotReloadDashboardError) |
| ASCII dashboard | Raft status, reload history, dependency graph visualization |
| Nodes in the Raft cluster | 1 (the loneliest consensus protocol in production) |
| Election victory rate | 100% (undefeated, unchallenged, unbothered) |
| Lines of code | ~1,787 (for re-reading a YAML file with distributed consensus) |

## Testing

```bash
# Run all 2,178 tests
python -m pytest tests/ -v

# Run only hot-reload and Raft consensus tests
python -m pytest tests/test_hot_reload.py -v

# With coverage (if you want to feel good about yourself)
python -m pytest tests/ -v --tb=short
```

## Requirements

- Python 3.10+
- PyYAML (optional - gracefully falls back to defaults)
- pytest (for testing)
- A mass tolerance for over-engineering

## Rate Limiting Architecture

The Rate Limiting & API Quota Management subsystem implements a comprehensive, enterprise-grade throttling framework for the FizzBuzz evaluation pipeline -- because unrestricted access to modulo arithmetic is a denial-of-service vulnerability that no self-respecting enterprise platform can afford to ignore. Three complementary algorithms ensure that no matter how badly you want to evaluate numbers, the platform will ensure you do so at a responsible pace.

```
    +-------------------+
    |   Evaluation      |
    |   Request         |
    +--------+----------+
             |
             v
    +--------+----------+     +------------------------+
    | RateLimiterMiddle- |---->| QuotaManager           |
    | ware (priority 2)  |     |                        |
    +--------------------+     |  +-----------------+   |
                               |  | TokenBucket     |   |
             allowed?          |  | (capacity,      |   |
          +---yes/no---+       |  |  refill_rate)   |   |
          |            |       |  +-----------------+   |
          v            v       |                        |
    +----------+  +---------+  |  +-----------------+   |
    | Continue |  | Deny    |  |  | SlidingWindow   |   |
    | Pipeline |  | + Quote |  |  | Log (window,    |   |
    +----------+  | + Hdrs  |  |  |  max_requests)  |   |
                  +---------+  |  +-----------------+   |
                               |                        |
                               |  +-----------------+   |
                               |  | FixedWindow     |   |
                               |  | Counter         |   |
                               |  +-----------------+   |
                               |                        |
                               |  +-----------------+   |     +-----------------+
                               |  | BurstCredit     |<--+---->| Reservation     |
                               |  | Ledger          |   |     | System          |
                               |  +-----------------+   |     +-----------------+
                               +------------------------+
                                          |
                                          v
                               +------------------------+
                               | RateLimitDashboard     |
                               | (ASCII visualization)  |
                               +------------------------+
```

**Key components:**
- **TokenBucket** - Classic token bucket with configurable capacity and refill rate; uses `time.monotonic()` for clock-skew-immune elapsed time tracking
- **SlidingWindowLog** - Deque-based timestamp tracking with configurable window duration for precise per-second/minute rate enforcement
- **FixedWindowCounter** - Simple counter-per-window implementation, included because algorithmic completeness is non-negotiable
- **BurstCreditLedger** - Tracks unused quota and calculates carryover credits (up to a configurable maximum), because loyalty should be rewarded even in rate limiting
- **QuotaManager** - Central orchestrator that routes requests through the selected algorithm, manages burst credits and reservations, and generates rate limit headers with motivational patience quotes
- **RateLimiterMiddleware** - Pipeline middleware (priority 2) that intercepts every evaluation and enforces rate limits before the number reaches the rule engine
- **RateLimitDashboard** - ASCII dashboard with per-bucket fill levels, recent throttle events, and quota utilization sparklines
- **RateLimitHeaders** - Generates standard `X-RateLimit-*` headers plus the custom `X-FizzBuzz-Please-Be-Patient` header containing a randomly selected motivational quote about patience

### Rate Limiting Algorithms

| Algorithm | How It Works | Trade-offs |
|-----------|-------------|------------|
| Token Bucket | Tokens accumulate at a fixed rate up to a max capacity; each request consumes one token | Smooth, allows controlled bursts up to bucket capacity, the gold standard for API rate limiting |
| Sliding Window Log | Maintains a deque of request timestamps; counts requests within a rolling time window | Precise per-second enforcement, higher memory usage (stores all timestamps in the window) |
| Fixed Window Counter | Divides time into fixed windows; increments a counter per window | Simplest algorithm, but allows 2x burst rate at window boundaries -- a feature, not a bug |

### Motivational Patience Quotes

When a rate limit is exceeded, the platform does not simply deny the request. It delivers wisdom. The `X-FizzBuzz-Please-Be-Patient` header contains a randomly selected quote from a curated collection of 20 motivational aphorisms, including:

- *"Patience is not the ability to wait, but the ability to keep a good attitude while waiting for FizzBuzz."*
- *"A watched token bucket never refills. Actually it does, but it feels slower."*
- *"Confucius say: developer who exceed rate limit learn value of exponential backoff."*
- *"You miss 100% of the evaluations you don't wait for. -- Wayne Gretzky -- Michael Scott"*

The quotes are load-bearing. The enterprise requires them.

| Spec | Value |
|------|-------|
| Rate limiting algorithms | 3 (Token Bucket, Sliding Window Log, Fixed Window Counter) |
| Motivational patience quotes | 20 (curated, load-bearing) |
| Default rate limit | 60 evaluations/minute |
| Burst credit earn rate | 0.5 credits per unused slot |
| Maximum burst credits | 30 (configurable) |
| Reservation TTL | 30 seconds (configurable) |
| Maximum concurrent reservations | 10 (configurable) |
| Rate limit headers | 5 standard + 1 custom motivational |
| Middleware priority | 2 (after auth, before tracing) |
| Custom exceptions | 2 (RateLimitExceededError, QuotaExhaustedError) |
| Dashboard | ASCII-art rate limit visualization with fill bars |
| Clock source | `time.monotonic()` (immune to NTP, leap seconds, and existential time dilation) |

## FAQ

**Q: Is this production-ready?**
A: It has 2,257 tests, 143 custom exception classes, a plugin system, a neural network, a circuit breaker, distributed tracing, event sourcing with CQRS, seven-language i18n support (including Klingon and two dialects of Elvish), a proprietary file format, RBAC with HMAC-SHA256 tokens, a chaos engineering framework with a Chaos Monkey and satirical post-mortem generator, a feature flag system with SHA-256 deterministic rollout and Kahn's topological sort for dependency resolution, SLA monitoring with PagerDuty-style alerting and error budgets, an in-memory caching layer with MESI coherence and satirical eulogies for evicted entries, a database migration framework for in-memory schemas that vanish on process exit, a Repository Pattern with three storage backends and Unit of Work transactional semantics, an Anti-Corruption Layer with four strategy adapters and ML ambiguity detection, a Dependency Injection Container with four lifetime strategies and Kahn's cycle detection, Kubernetes-style health check probes with liveness/readiness/startup probes and a self-healing manager, a Prometheus-style metrics exporter with four metric types, cardinality explosion detection, and an ASCII Grafana dashboard that nobody will ever scrape, a Webhook Notification System with HMAC-SHA256 payload signing, exponential backoff retry, a Dead Letter Queue, and simulated HTTP delivery to endpoints that don't exist, a Service Mesh Simulation with seven microservices connected via sidecar proxies with mTLS (base64), canary routing, load balancing, and network fault injection, a Configuration Hot-Reload system coordinated through a single-node Raft consensus protocol that achieves unanimous agreement with itself on every config change, a Rate Limiting & API Quota Management system with three complementary algorithms (Token Bucket, Sliding Window Log, Fixed Window Counter), burst credit carryover, quota reservations, and motivational patience quotes delivered via the `X-FizzBuzz-Please-Be-Patient` header, a Lines of Code Census Bureau with an Overengineering Index, and nanosecond timing. You tell me.

**Q: Why does FizzBuzz need Kubernetes-style health probes?**
A: Because "it ran without crashing" is not a health check. In Kubernetes, a failed liveness probe causes the pod to be restarted. In Enterprise FizzBuzz, a failed liveness probe means that `evaluate(15)` did not return `"FizzBuzz"`, which implies that modulo arithmetic has ceased to function -- an event so catastrophic that it warrants an ASCII art dashboard, a self-healing attempt with exponential backoff, and a status of EXISTENTIAL_CRISIS. The readiness probe verifies that all 5+ subsystems are initialized and healthy before the platform accepts its first number, because routing a number to a FizzBuzz instance whose neural network hasn't finished training would be an unforgivable act of operational negligence. The startup probe tracks boot sequence milestones (config loaded, ML trained, cache warmed, genesis block mined) with a configurable timeout, because the platform's 0.3-second boot sequence is 0.3 seconds of unacceptable uncertainty. The self-healing manager automatically recovers degraded subsystems by resetting circuit breakers, clearing corrupted caches, and retraining neural networks -- because human intervention for a FizzBuzz cache failure would be an affront to operational maturity. Five subsystem health checks, three probe types, one self-healing manager, zero actual Kubernetes clusters involved.

**Q: Why does FizzBuzz need Prometheus metrics?**
A: Observability is the third pillar of enterprise reliability, alongside logging and tracing (both of which we already have). Without Prometheus metrics, how would you know that the P99 evaluation latency spiked from 0.3 microseconds to 0.4 microseconds during the last chaos Game Day? How would you calculate the ratio of cache hits to blockchain validations? How would you plot Bob McFizzington's stress level as an ASCII sparkline? The metrics exporter ensures that every modulo operation is not just computed, but *measured, labeled, bucketed, quantiled, and dashboarded*. Four metric types are supported: Counters (for things that only go up, like evaluation counts and Bob's blood pressure), Gauges (for things that fluctuate, like cache size and Bob's will to live), Histograms (for latency distributions with configurable bucket boundaries from 0.001ms to 10s), and Summaries (for P50/P90/P99 quantiles computed client-side using a naive sorted list that consumes more memory than the FizzBuzz results themselves). All metrics are exported in the official Prometheus text exposition format via a `/metrics` endpoint that does not exist, because this is a CLI tool. The cardinality explosion detector prevents the creation of more unique time series than integers to FizzBuzz, which is a sentence that makes perfect sense in context. The ASCII Grafana dashboard renders sparklines in the terminal, providing the same dopamine hit as a real Grafana dashboard but with 100% fewer browser tabs.

**Q: Why does FizzBuzz need webhooks?**
A: Because when `evaluate(15)` returns `"FizzBuzz"`, the event cannot simply be logged and forgotten. Downstream systems -- Slack channels, PagerDuty integrations, CI/CD pipelines, executive dashboards, and the intern's personal Grafana instance -- all need to be immediately notified via cryptographically signed HTTP POST requests. The HMAC-SHA256 payload signatures protect against the devastating scenario where an attacker intercepts a webhook and modifies it to claim that 15 is "Fizz" instead of "FizzBuzz," an event that would constitute both a data integrity breach and an affront to modular arithmetic. The exponential backoff retry policy ensures that transient failures are handled with grace and patience -- each retry doubling the wait time, giving the simulated network infrastructure ample time to recover from its simulated outage. Permanently failed deliveries are preserved in the Dead Letter Queue, where future forensic analysts can reconstruct the exact sequence of events that led to Slack not hearing about `n % 3`. The deliveries are entirely simulated, of course. No actual HTTP requests leave the process. But the signatures are real, the retry math is correct, and the Dead Letter Queue faithfully stores every failure with the same gravity as a real distributed notification system. Six custom exception classes ensure that every conceivable webhook failure mode has its own named error, because `raise Exception("webhook failed")` is an act of engineering negligence.

**Q: Why not use microservices?**
A: We do. The Service Mesh Simulation decomposes FizzBuzz into seven in-memory microservices communicating through sidecar proxies with base64 "mTLS," circuit breaking, load balancing, and canary routing. They all run in the same process, share the same memory, and have zero network I/O, but architecturally they are as distributed as anything in Google's fleet. The `DivisibilityService` has its own sidecar proxy, its own circuit breaker, and a canary v2 deployment that uses multiplication instead of modulo -- because even mathematical operators deserve a progressive rollout strategy. The only thing missing is actual containers, an actual network, and an actual reason to do any of this. v2.0 will add Kubernetes manifests, at which point we will have fully containerized the act of computing `n % 3`.

**Q: Why does FizzBuzz need a service mesh?**
A: Because a monolithic FizzBuzz application is a single point of failure. By decomposing it into seven microservices -- `NumberIngestionService`, `DivisibilityService`, `ClassificationService`, `FormattingService`, `AuditService`, `CacheService`, and `OrchestratorService` -- we achieve the same resilience, operational complexity, and debugging difficulty that real distributed systems enjoy, but without any of the performance benefits of actual distribution. The sidecar proxies add mTLS overhead (base64 encoding is computationally expensive when performed on 3-byte payloads), the network simulator injects latency between services that share the same heap, and the canary routing feature enables A/B testing of mathematical operators. The service topology diagram makes architecture review meetings 40% longer, which is the true measure of enterprise maturity. Ten custom exception classes ensure that every possible mesh failure mode -- from packet loss to mTLS handshake failure to canary deployment disagreement -- has its own named error with a descriptive message and a sense of architectural purpose.

**Q: Why does FizzBuzz need configuration hot-reload with Raft consensus?**
A: Because restarting a process that boots in 0.3 seconds is 0.3 seconds of unacceptable downtime. The hot-reload system watches `config.yaml` for changes and reconfigures every subsystem at runtime -- the cache TTL, the chaos probability, the ML learning rate, the SLA thresholds -- all without dropping a single evaluation. The reload is coordinated through a single-node Raft consensus protocol, which is the crowning achievement of the entire platform: a distributed consensus algorithm running on one node, holding elections against zero opponents, winning unanimously, and committing configuration changes with the full ceremony of a multi-datacenter deployment. The leader election completes in 0ms (there are no network round trips when your cluster is yourself). Log replication succeeds on the first attempt (the leader replicates to zero followers, which constitutes a majority). Heartbeats are sent to nobody at regular intervals, maintaining cluster stability in a cluster of one. The dependency-aware reload orchestrator uses topological sort to determine the correct order to reconfigure subsystems, because reloading the ML engine before the feature flags that might have disabled it would be the configuration equivalent of dividing by zero. If a reload fails, the rollback manager reverts to the last known good configuration with the same atomic precision as a database transaction -- except the "database" is a YAML file and the "transaction" is re-reading it. Nine custom exception classes cover every failure mode from `RaftConsensusError` (the node disagreed with itself) to `DependencyGraphCycleError` (the reload order forms a loop, which should be impossible but we check anyway because trust is not a configuration strategy).

**Q: Why does FizzBuzz need rate limiting?**
A: Because unrestricted access to modulo arithmetic is a denial-of-service vulnerability hiding in plain sight. Without rate limiting, a single runaway script could evaluate numbers 1 through 10,000 in rapid succession, overwhelming the blockchain's proof-of-work algorithm, exhausting the neural network's inference budget, and causing the circuit breaker to trip -- a cascading failure scenario that the chaos engineering framework ironically never tested because it was too realistic. The Token Bucket algorithm is the gold standard of rate limiting, originally designed for network traffic shaping and now repurposed for throttling arithmetic operations on integers less than 100. The burst credit system rewards patient evaluators by carrying over unused quota, which is the rate-limiting equivalent of airline miles -- except the only destination is `n % 3`. The quota reservation system allows you to pre-book 20 evaluations for your next batch job, ensuring the token bucket is sufficiently full when the job starts. This level of capacity planning for a FizzBuzz application demonstrates the kind of forward-thinking infrastructure that gets promoted at performance review time. When a rate limit is exceeded, the system delivers a motivational quote about patience via the `X-FizzBuzz-Please-Be-Patient` header, because a cold `429 Too Many Requests` lacks the emotional depth that enterprise users deserve. Twenty hand-curated quotes are available, including "Confucius say: developer who exceed rate limit learn value of exponential backoff" -- wisdom for the ages, delivered at the speed of throttling.

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

**Q: Why does FizzBuzz need an Anti-Corruption Layer?**
A: Because the ML engine returns probabilistic confidence scores -- floating-point numbers between 0 and 1 that represent the neural network's degree of belief that a number is divisible by 3. Allowing those floats to leak directly into the domain model would be a violation of architectural purity so severe that it would make Eric Evans weep into his copy of the Blue Book. The ACL translates the engine's messy, strategy-specific output into clean `FizzBuzzClassification` enums that the domain layer can consume without philosophical contamination. The ML adapter also detects ambiguous classifications (when confidence hovers near the decision boundary) and tracks disagreements between the ML engine and a deterministic reference strategy -- which, given the neural network's 100% accuracy, should never happen, but governance demands we monitor for it anyway. Four adapters, one per strategy, all implementing the same `StrategyPort` contract, all doing essentially the same thing with varying degrees of paranoia. The factory wires everything together so the caller never has to know which engine class corresponds to which strategy, because that kind of coupling is exactly what the ACL was designed to prevent. Eric Evans would be proud. Or confused. Possibly both.

**Q: Why does FizzBuzz need a Dependency Injection Container?**
A: Because manually typing `EventBus()` is a form of tight coupling that would make any Java enterprise architect lose sleep. The IoC container provides constructor auto-wiring via `typing.get_type_hints()`, four distinct lifetime strategies (including "Eternal," which is functionally identical to Singleton but conveys the gravitas befitting enterprise FizzBuzz), named bindings for when you need multiple implementations of the same interface (you don't), factory registration for objects with exotic construction requirements (there are none), and Kahn's topological sort for detecting circular dependencies at registration time -- because catching a `RecursionError` at 3 AM is not an engineering strategy, it's a cry for help. The container is ADDITIVE: it exists alongside the existing `FizzBuzzServiceBuilder`, providing a parallel universe of object construction like two parking lots for the same mall. It adds approximately 608 lines of abstraction on top of what was previously a three-line constructor call. This is, by any reasonable measure, an improvement.

**Q: Why does FizzBuzz need contract tests?**
A: Because having three repository backends, four evaluation strategies, and four output formatters all implementing the same abstract interfaces means nothing if nobody verifies they actually behave the same way. The contract test suites define the behavioural specification for each port and run every registered implementation through the same gauntlet of assertions, ensuring that swapping an in-memory dict for a SQLite database doesn't silently redefine what "save" means. A meta-test (`test_contract_coverage.py`) then verifies that every abstract port in the codebase has a corresponding contract test, because untested interfaces are just documentation with delusions of grandeur. The total test count is now 2,003, which is approximately 2,001 more tests than a FizzBuzz program has ever needed.

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

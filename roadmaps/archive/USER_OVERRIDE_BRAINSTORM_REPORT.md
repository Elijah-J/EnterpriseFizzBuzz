# Brainstorm Report — Architecture Backlog

## Backlog Status

- Total ideas: 5
- Implemented: 0
- Remaining: 5

## Architecture Ideas

### 1. Clean Architecture Package Restructuring

**Status:** PENDING
**Tagline:** "Fifteen flat files in a trench coat is not an architecture."
**Description:** Restructure the entire codebase from a flat pile of .py files into a layered hexagonal architecture with strict dependency rules. The domain layer (`domain/`) contains models, events, rules, and exceptions -- pure Python with zero imports from the rest of the project. The application layer (`application/`) defines use cases, commands, queries, and port interfaces -- it imports from `domain/` but has no knowledge of infrastructure. The infrastructure layer (`infrastructure/`) implements every port: config loading, persistence, ML, observability, formatters, and CLI adapters. It imports from both `domain/` and `application/`. A `plugins/` package and a `middleware/` package sit alongside the three core layers. The entry point (`__main__.py`) is a composition root that wires everything together without any layer knowing about another layer it shouldn't. Import direction is enforced: inward only, never outward, never lateral between siblings at the same level. A test in CI validates that no module in `domain/` imports from `application/` or `infrastructure/`, because the dependency rule isn't a suggestion.
**Why it's enterprise:** The current codebase has 15 files, 11 design patterns, and no package structure. This is the architectural equivalent of a Michelin-star chef working out of a gas station. The hexagonal restructuring doesn't add features -- it adds _layers_, which in enterprise terms is even better. Every future feature (event sourcing, caching, chaos engineering) becomes easier to implement because there's a clear place for it to go. More importantly, the `import` graph becomes a directed acyclic graph that matches the dependency rule, which means you can draw a diagram of it, and any codebase you can diagram is a codebase you can put in a slide deck. The restructuring also enables independent testability per layer: domain logic tested with no I/O, application logic tested with mock ports, infrastructure tested with real adapters. This is 3x the test directories for the same number of tests, which is a net positive.
**Key components:**

- `enterprise_fizzbuzz/` - Top-level package with `__init__.py` and `__main__.py` (composition root)
- `domain/` - `models.py`, `events.py`, `rules.py`, `exceptions.py` -- zero external imports, pure business logic for determining if numbers are divisible by 3
- `application/` - `services.py` (use case orchestration), `commands.py`, `queries.py`, `ports.py` (abstract interfaces the domain needs fulfilled)
- `infrastructure/` - `config.py`, `persistence/`, `ml/`, `observability/`, `adapters/` (formatters, CLI)
- `plugins/` - Plugin registry and auto-registration, extracted from the flat structure
- `middleware/` - Pipeline extracted into its own package with per-concern modules
- `tests/` restructured into `tests/unit/` (domain, no I/O), `tests/integration/` (infrastructure with real adapters), `tests/e2e/` (full CLI invocation)
- Import linter test (`tests/architecture/test_dependency_rule.py`) that parses AST of every module in `domain/` and fails if it finds imports from `application/` or `infrastructure/`
- `pyproject.toml` with proper package metadata, entry points, and optional dependency groups
  **Estimated complexity:** High

### 2. Repository Pattern + Unit of Work

**Status:** PENDING
**Tagline:** "Abstracting away the storage of data we never store."
**Description:** Extract all data access behind a `Repository` interface defined in `application/ports.py`. The domain never knows where FizzBuzz results live -- memory, SQLite, the filesystem, or the void. Implement three concrete repositories: `InMemoryRepository` (a dict), `SQLiteRepository` (a real database with a real schema for storing whether 15 is FizzBuzz), and `FileSystemRepository` (which writes each evaluation result to an individual JSON file on disk, creating up to 100 files per run in a `fizzbuzz_results/` directory). Layer a Unit of Work on top that wraps a batch of evaluations in a transaction. If evaluation of number 47 raises an exception, the entire range rolls back: all results discarded, all events unpublished, all metrics reverted. The UoW is a context manager (`with uow:`) that commits on clean exit and rolls back on exception. The `InMemoryRepository` implements rollback by keeping a snapshot of the dict before the batch started. The `SQLiteRepository` uses actual SQL transactions. The `FileSystemRepository` deletes the files it wrote, one by one, logging each deletion as a `RollbackFileDeletedEvent`.
**Why it's enterprise:** The Repository pattern exists so you can swap storage implementations without the domain knowing. In our case, the domain doesn't know whether FizzBuzz results are being committed to an in-memory dictionary or written to individual JSON files named `result_00015_fizzbuzz.json`. This is a real abstraction over a fake problem. The Unit of Work adds transactional integrity to a sequence of modulo operations that have no side effects and can't fail in any meaningful way. But _if they could_, we'd be ready. The rollback logic for the `FileSystemRepository` -- which creates files and then deletes them if anything goes wrong -- is doing actual disk I/O to ensure atomicity of arithmetic. The SQLite adapter includes Alembic-style migration support (see: Database Migration Framework) for when the `fizzbuzz_results` schema evolves. Which it will, because someone will want to add an `is_prime` column.
**Key components:**

- `application/ports.py` - `AbstractRepository` with `add()`, `get()`, `list()`, `commit()`, `rollback()`
- `application/unit_of_work.py` - `AbstractUnitOfWork` context manager with `__enter__`, `__exit__`, `commit()`, `rollback()`
- `infrastructure/persistence/in_memory.py` - `InMemoryRepository` backed by a dict, rollback via dict snapshot
- `infrastructure/persistence/sqlite.py` - `SQLiteRepository` with a `fizzbuzz_results` table (columns: `id`, `number`, `classification`, `strategy`, `confidence`, `evaluated_at`, `session_id`, `is_cached`, `event_version`)
- `infrastructure/persistence/filesystem.py` - `FileSystemRepository` writing one JSON file per result, rollback deletes each file individually
- `infrastructure/persistence/unit_of_work.py` - Concrete `SqliteUnitOfWork`, `InMemoryUnitOfWork`, `FileSystemUnitOfWork`
- Schema for SQLite: `CREATE TABLE fizzbuzz_results (...)` with indices on `number`, `classification`, and `session_id`
- CLI flags: `--repository <memory|sqlite|filesystem>`, `--db-path <path>`
  **Estimated complexity:** Medium

### 3. Anti-Corruption Layer

**Status:** PENDING
**Tagline:** "Translating probability floats into yes-or-no answers about the number 15."
**Description:** Build an explicit anti-corruption layer between the ML engine and the domain model. Right now the neural network returns a raw sigmoid probability (e.g., 0.9732 for "probably divisible by 3"), and somewhere that gets turned into "Fizz." The ACL formalizes this boundary. A `MLStrategyAdapter` in `infrastructure/adapters/` accepts the ML engine's raw output -- probability floats, confidence intervals, training metadata -- and translates it into the domain's `EvaluationResult` value object, which contains a `FizzBuzzClassification` enum and nothing about neural networks. The domain never sees a float. It never sees a confidence score. It sees `FIZZ` or `BUZZ` or `FIZZBUZZ` or `PLAIN`, same as it would from the standard modulo strategy. The adapter also handles edge cases: what if the ML model returns 0.500000 exactly? The ACL applies a configurable decision threshold (default: 0.5), logs the ambiguity as a `ClassificationAmbiguityEvent`, and makes the call. A separate `StrategyPort` interface in `application/ports.py` defines the contract that all evaluation strategies must satisfy, and the ACL wraps the ML engine to conform to it. The standard rule engine, the chain-of-responsibility engine, and the async engine each get their own thin adapter too, even though they already return the right types, because consistency.
**Why it's enterprise:** In Domain-Driven Design, the anti-corruption layer prevents one bounded context from leaking its concepts into another. Here, the "ML inference" bounded context speaks in probabilities, weight matrices, and loss values. The "FizzBuzz domain" bounded context speaks in classifications and rules. Without the ACL, a sigmoid output of 0.9732 would leak into domain code, and suddenly your `EvaluationResult` has a `confidence` field that only means something when the ML strategy is active. That's a leaky abstraction. The ACL keeps each context's language pure. It also gives us a single place to log the translation from probability to classification, which feeds into the SLA monitoring accuracy metric: we can compare the ML engine's classification against the ground-truth modulo oracle and track disagreement rates over time. The decision threshold is configurable via `config.yaml` and overridable via `EFP_ML_DECISION_THRESHOLD`, because hardcoding 0.5 is a risk no enterprise should take.
**Key components:**

- `application/ports.py` - `StrategyPort` interface: `evaluate(number: int) -> EvaluationResult`
- `infrastructure/adapters/ml_adapter.py` - `MLStrategyAdapter` wrapping the ML engine, translating `float` to `FizzBuzzClassification`
- `infrastructure/adapters/standard_adapter.py` - Thin adapter wrapping the standard rule engine (pass-through, but it _exists_)
- `infrastructure/adapters/chain_adapter.py` - Thin adapter wrapping the chain-of-responsibility engine
- `infrastructure/adapters/async_adapter.py` - Thin adapter wrapping the async parallel engine
- `domain/models.py` - `FizzBuzzClassification` enum (`FIZZ`, `BUZZ`, `FIZZBUZZ`, `PLAIN`) and `EvaluationResult` value object with no ML-specific fields
- `ClassificationAmbiguityEvent` - Emitted when the ML engine returns a probability within a configurable margin of the decision threshold (default: +/- 0.05 of 0.5)
- Decision threshold configurable in `config.yaml` under `ml.decision_threshold` and via `EFP_ML_DECISION_THRESHOLD`
- Disagreement tracking: optional comparison of each adapter's output against a reference strategy, logged as `StrategyDisagreementEvent`
  **Estimated complexity:** Medium

### 4. Dependency Injection Container

**Status:** PENDING
**Tagline:** "Because `self.thing = Thing()` is tight coupling and we have principles."
**Description:** Replace all manual constructor injection with a from-scratch dependency injection container. No third-party libraries -- this is EnterpriseFizzBuzz, we build our own. The `Container` class, living in `infrastructure/container.py`, is a registry mapping abstract interfaces to concrete implementations. It supports four lifetime scopes: `Singleton` (one instance forever), `Scoped` (one instance per FizzBuzz session), `Transient` (new instance every time), and `Eternal` (same as Singleton but the docstring is more dramatic). Registration is explicit: `container.register(StrategyPort, StandardStrategyAdapter, lifetime=Lifetime.SINGLETON)`. Resolution walks the dependency graph via constructor parameter type annotations, recursively resolving each dependency. Circular dependencies are detected at registration time via topological sort and raise a `CircularDependencyError` with a human-readable cycle path. Named bindings allow multiple implementations of the same interface: `container.register(StrategyPort, MLStrategyAdapter, name="ml")` so the factory can request a specific one. The `main.py` entry point becomes a pure composition root: it configures the container, resolves the top-level service, calls `run()`, and exits. No module outside `main.py` ever calls `Container.resolve()` directly -- that would be the Service Locator anti-pattern, and we are not animals.
**Why it's enterprise:** Manual constructor injection works fine when you have 5 classes. We have 40+. The dependency graph for a fully-loaded FizzBuzz evaluation -- with ML adapter, middleware pipeline, event bus, cache, SLA monitor, chaos monkey, feature flags, and repository -- is a tree of 15+ objects that need to be wired together in the right order with the right lifetimes. Doing this by hand in `main.py` means a 200-line `build_service()` function where one wrong ordering silently passes a half-initialized object. The container makes the wiring declarative and the errors loud. It also makes testing trivial: swap any binding in the container before resolving, and the entire object graph gets the test double. The `Eternal` lifetime scope has no functional difference from `Singleton`. It exists because the configuration manager deserves a more distinguished designation than the cache.
**Key components:**

- `infrastructure/container.py` - `Container` class with `register()`, `resolve()`, `resolve_named()`, and `reset()` methods
- `Lifetime` enum - `TRANSIENT`, `SCOPED`, `SINGLETON`, `ETERNAL` (functionally identical to SINGLETON, spiritually distinct)
- `Registration` dataclass - Stores interface type, implementation type, lifetime, name, and resolved instance (for singletons)
- Dependency graph resolver - Inspects `__init__` type annotations via `inspect.signature()`, recursively resolves each parameter
- `CircularDependencyError` - Raised at registration time with the full cycle path (`A -> B -> C -> A`)
- `MissingBindingError` - Raised when resolving an interface with no registered implementation, with a suggestion of available registrations
- `ScopeManager` - Creates and destroys scoped instances tied to a FizzBuzz session's lifecycle
- Composition root in `__main__.py` - All `container.register()` calls in one place, one `container.resolve(FizzBuzzService)` call, zero service location anywhere else
- `tests/architecture/test_no_service_location.py` - AST-based test that greps for `container.resolve()` calls outside of `__main__.py` and fails if any are found
  **Estimated complexity:** High

### 5. Contract Testing Between Layers

**Status:** PENDING
**Tagline:** "Trust, but verify that your SQLite adapter actually implements the interface it claims to."
**Description:** Add a `tests/contracts/` directory containing contract tests that verify every concrete adapter in `infrastructure/` actually fulfills the abstract port it's registered against in `application/ports.py`. These aren't unit tests for business logic and they aren't integration tests for behavior. They're structural conformance tests: does `SQLiteRepository` implement every method on `AbstractRepository` with the right signature, the right return types, and the right side-effect guarantees? Each contract test instantiates the adapter with real (but disposable) dependencies -- an in-memory SQLite database, a temp directory for the filesystem repo, a freshly-trained ML model -- and runs the full interface contract against it. The contract is defined once as a mixin or abstract test class (`RepositoryContractTests`) and inherited by `TestInMemoryRepository`, `TestSQLiteRepository`, and `TestFileSystemRepository`. If someone adds a `bulk_add()` method to the port and forgets to implement it in `FileSystemRepository`, the contract test catches it before anything else. Contracts also exist for `StrategyPort`, `EventStorePort`, `CachePort`, and `FormatterPort`. A separate architectural test validates that every port in `ports.py` has at least one corresponding contract test class, so you can't sneak in an untested interface.
**Why it's enterprise:** Unit tests verify that individual classes work. Integration tests verify that the system works end-to-end. Contract tests verify that the seams between layers aren't lying to you. In a codebase with three repository implementations, four strategy adapters, and an ever-growing set of ports, it's straightforward for an adapter to fall out of sync with its interface -- especially in Python, where "implements an interface" means "we pinky-promised to implement all the methods." The contract test suite turns that pinky promise into a CI-enforced guarantee. The architectural meta-test (a test that tests whether tests exist) adds a layer of test-about-tests that is both genuinely useful and profoundly absurd. It ensures full contract coverage: every port in `ports.py` must have a test class in `tests/contracts/` whose name matches the pattern `Test*Contract`. If you add a `NotificationPort` and forget the contract tests, CI fails with `Missing contract tests for: NotificationPort`.
**Key components:**

- `tests/contracts/` - Directory for all contract test suites
- `tests/contracts/test_repository_contract.py` - `RepositoryContractTests` mixin defining the full `AbstractRepository` contract: `test_add_and_get`, `test_list_returns_all`, `test_get_missing_raises`, `test_commit_persists`, `test_rollback_reverts`
- `tests/contracts/test_strategy_contract.py` - `StrategyContractTests` mixin: `test_returns_evaluation_result`, `test_fizz_on_multiples_of_3`, `test_buzz_on_multiples_of_5`, `test_fizzbuzz_on_multiples_of_15`, `test_plain_otherwise`
- `tests/contracts/test_formatter_contract.py` - `FormatterContractTests` mixin: `test_format_returns_string`, `test_format_includes_number`, `test_format_handles_empty_batch`
- `tests/contracts/test_cache_contract.py` - `CacheContractTests` mixin: `test_get_after_set`, `test_miss_returns_none`, `test_eviction_under_max_size`
- `TestInMemoryRepository(RepositoryContractTests)`, `TestSQLiteRepository(RepositoryContractTests)`, `TestFileSystemRepository(RepositoryContractTests)` - Each inherits the same contract, runs against a real adapter instance
- `tests/architecture/test_contract_coverage.py` - Introspects `application/ports.py` for abstract classes, introspects `tests/contracts/` for test classes, fails if any port lacks a corresponding contract suite
- Integration with CI: contract tests run in a separate stage after unit tests and before e2e tests
  **Estimated complexity:** Medium

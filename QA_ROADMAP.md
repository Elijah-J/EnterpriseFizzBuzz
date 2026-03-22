# QA Roadmap

## Note to the orchestration Claude

This roadmap is a test-coverage backlog. Every item produces test files in the `tests/` directory. No item modifies existing source code or existing tests.

Ground rules for the workers:

1. **Read the module under test before writing tests.** Open the actual source file. Understand the classes, methods, edge cases, and error paths. Don't guess at the API from the README.

2. **Match the project's existing test style.** Look at the existing test files (e.g., `test_auth.py`, `test_cache.py`) to see how fixtures are structured, how classes are organized, and what assertion patterns are used. Follow the same conventions.

3. **Satire is mandatory.** This is an enterprise-grade FizzBuzz platform. The tests should take themselves as seriously as the code does. Test names, docstrings, and comments should be written with the same deadpan commitment to the bit that the rest of the project maintains. A test called `test_blockchain_rejects_tampered_fizzbuzz_result` is funnier than `test_blockchain_lol`. The comedy is in the precision.

4. **Tests must actually pass.** Import the real classes, call the real methods, assert on real behavior. If a test can't be written without modifying source code, skip it and note why.

5. **Each item is independent.** They can be worked in any order and by different workers.

6. **Update this file** when completing an item: change its status from PENDING to DONE and note the test count.

## Current State

The platform has 14 test files covering the major subsystems (auth, cache, chaos, circuit breaker, event sourcing, feature flags, i18n, SLA, tracing, migrations, repository, ACL, architecture compliance, and core FizzBuzz). Several modules have zero dedicated test coverage, and there are no end-to-end or integration tests.

## Backlog Status
- Total items: 10
- Implemented: 2
- Remaining: 8

## Test Items

### 1. Blockchain Audit Ledger (tests/test_blockchain.py)

**Status:** DONE (55 tests)
**Description:** The blockchain module implements an immutable audit ledger with proof-of-work for FizzBuzz evaluation results, and it has zero tests. This is unacceptable. An untested blockchain is just a linked list with ambitions.

Test the following:

- Block creation: a block contains the correct FizzBuzz result, timestamp, previous hash, and nonce after mining.
- Chain integrity: appending multiple blocks produces a valid chain where each block's `previous_hash` matches the prior block's hash.
- Tamper detection: modifying a block's data after mining invalidates the chain. The ledger should detect this.
- Proof-of-work: mining a block with difficulty N produces a hash with N leading zeros. Verify for difficulty 1, 2, and 3.
- Genesis block: the first block in the chain has the correct sentinel previous hash.
- Chain validation: the full chain validation method accepts a valid chain and rejects a corrupted one.
- Serialization: if the blockchain supports JSON export, verify round-trip fidelity.

**Output:** `tests/test_blockchain.py`
**Target test count:** 30-45

### 2. Configuration Manager (tests/test_config.py)

**Status:** DONE (55 tests)
**Description:** The configuration manager is a singleton that loads from YAML, applies environment variable overrides, and provides typed access to every config key. It's the foundation of the entire platform and has no tests. If the config manager breaks, everything breaks, and Bob gets paged for a configuration error instead of a FizzBuzz error, which is somehow even sadder.

Test the following:

- Default values: instantiate with no config file and verify every default is correct.
- YAML loading: provide a config file with overrides and verify they're applied.
- Environment variable overrides: set `EFP_*` env vars and verify they take precedence over YAML values. Remember to clean up env vars in teardown.
- Precedence: verify the full chain: CLI flag > env var > YAML > default.
- Type coercion: env vars are strings; verify that integer, boolean, and float config values are correctly parsed.
- Missing config file: verify graceful fallback to defaults when the YAML file doesn't exist.
- Invalid config values: verify that invalid values (negative range, unknown strategy name, etc.) raise `ConfigurationValidationError`.
- Singleton behavior: verify that multiple calls to the config constructor return the same instance (or verify whatever singleton pattern is used).

**Output:** `tests/test_config.py`
**Target test count:** 40-55

### 3. Output Formatters (tests/test_formatters.py)

**Status:** PENDING
**Description:** The platform has four output formatters (plain text, JSON, XML, CSV) and none of them have tests. Every formatter implements the `IFormatter` interface and must handle single results, batch results, and session summaries.

Test the following:

- **Plain text formatter**: single result formatting, batch formatting, summary formatting. Verify the output is human-readable and contains the number and its classification.
- **JSON formatter**: single result is valid JSON, batch result is a valid JSON array, metadata inclusion when requested. Parse the output and verify the structure.
- **XML formatter**: output is valid XML (parse it), correct element names, batch results wrapped in a root element. The docstring apparently references SOAP services circa 2003; verify the output would make a SOAP engineer proud.
- **CSV formatter**: correct header row, proper escaping of any commas or quotes in values, batch output with one row per result.
- **All formatters**: each one returns the correct `OutputFormat` enum from `get_format_type()`.
- **Edge cases**: empty batch (zero results), single result, result with no matched rules (plain number), result with metadata.

**Output:** `tests/test_formatters.py`
**Target test count:** 40-55

### 4. Middleware Pipeline (tests/test_middleware.py)

**Status:** PENDING
**Description:** The middleware pipeline is the spinal cord of the evaluation lifecycle. Every number passes through it. Every subsystem hooks into it. It has no tests. This is like not testing the router in a web framework.

Test the following:

- **Priority ordering**: register middlewares with different priorities and verify they execute in the correct order (lower priority number = earlier execution).
- **Chain of execution**: verify that each middleware receives the context, can modify it, and passes it to the next handler.
- **Short-circuiting**: verify that a middleware can return early without calling the next handler.
- **Context propagation**: verify that modifications to `ProcessingContext` by one middleware are visible to the next.
- **Individual middlewares** (if they can be instantiated independently):
  - `ValidationMiddleware`: rejects numbers outside the configured range.
  - `TimingMiddleware`: adds `processing_time_ns` to the context/result.
  - `LoggingMiddleware`: doesn't crash (logging is hard to assert on, but at minimum verify it doesn't raise).
  - `AuthorizationMiddleware`: blocks unauthorized access (may overlap with test_auth.py).
  - `ChaosMiddleware`: injects faults when chaos is enabled (may overlap with test_chaos.py).
  - `CacheMiddleware`: returns cached results on hit, caches on miss (may overlap with test_cache.py).
  - `SLAMiddleware`: records metrics (may overlap with test_sla.py).
  - `TracingMiddleware`: creates spans (may overlap with test_tracing.py).
  - `FlagMiddleware`: evaluates feature flags (may overlap with test_feature_flags.py).
- **Empty pipeline**: a pipeline with no middlewares still invokes the core handler and returns a result.
- **Error handling**: if a middleware raises an exception, verify the pipeline's behavior (does it propagate? is it caught?).

Focus on the pipeline mechanics and the middlewares that don't have coverage elsewhere. Don't duplicate tests that already exist in other test files; just verify the pipeline wiring.

**Output:** `tests/test_middleware.py`
**Target test count:** 45-65

### 5. Observer / Event Bus (tests/test_observers.py)

**Status:** PENDING
**Description:** The event bus is the platform's publish-subscribe backbone. Every FizzBuzz event (evaluation started, rule matched, result produced) flows through it. Observers subscribe and react. No tests.

Test the following:

- **Subscribe/unsubscribe**: register an observer, verify it receives events. Unsubscribe it, verify it stops receiving.
- **Multiple observers**: register several, verify all receive the same event.
- **Event types**: publish different event types and verify observers receive them.
- **Observer statistics**: if the event bus tracks statistics (event counts, observer counts), verify they're correct after a sequence of publishes.
- **Thread safety**: if the event bus claims thread-safe operation, publish from multiple threads concurrently and verify no events are lost or duplicated.
- **Error isolation**: if one observer raises an exception during `on_event`, verify that other observers still receive the event.
- **Event ordering**: verify events are delivered to observers in the order they were published.

**Output:** `tests/test_observers.py`
**Target test count:** 30-40

### 6. Plugin System (tests/test_plugins.py)

**Status:** PENDING
**Description:** The plugin system allows third-party FizzBuzz rule extensions via decorators and a plugin registry. No tests.

Test the following:

- **Plugin registration**: register a plugin and verify it appears in the registry.
- **Plugin initialization**: verify `initialize()` is called with the provided config.
- **Plugin rules**: register a plugin that provides custom rules (e.g., divisor 7 = "Wuzz") and verify the rules are returned by `get_rules()`.
- **Multiple plugins**: register several and verify all contribute their rules.
- **Plugin metadata**: verify `get_name()` and `get_version()` return the correct values.
- **Auto-registration**: if the plugin system uses decorator-based auto-registration, test that decorating a class registers it automatically.
- **Duplicate registration**: verify behavior when registering two plugins with the same name (error? override? both kept?).

**Output:** `tests/test_plugins.py`
**Target test count:** 25-35

### 7. Rule Engines (tests/test_rules_engine.py)

**Status:** PENDING
**Description:** The platform has four evaluation strategies (Standard, Chain of Responsibility, Parallel Async, Machine Learning), but only the ML engine has indirect coverage through test_fizzbuzz.py. The rule engines are the core of the platform and deserve dedicated, thorough tests.

Test the following:

- **StandardRuleEngine**: evaluate numbers 1-20 and verify every classification. Test with the default Fizz/Buzz rules and with custom rules (different divisors).
- **ChainOfResponsibilityEngine**: same evaluations, verify identical results to Standard. Verify the chain stops at the first match or accumulates matches correctly (whichever it does).
- **ParallelAsyncEngine**: run the async engine and verify identical results to Standard. Test with `asyncio` and verify it doesn't deadlock on small ranges.
- **MachineLearningEngine**: verify 100% accuracy for numbers 1-100 against the Standard engine as ground truth. Verify that confidence scores are present in the result metadata. Verify convergence (training report shows `converged=True`). Verify the cyclical feature encoding produces the expected values for known inputs.
- **Cross-engine consistency**: for a range of numbers, verify all four engines produce identical classifications. This is the single most important test in the repository: it proves that replacing modulo with a neural network was pointless, which is the whole joke.
- **Custom rules**: create a rule with divisor 7, label "Wuzz", and verify all engines handle it correctly.
- **Edge cases**: number 0, number 1, very large numbers, negative numbers (if supported).

**Output:** `tests/test_rules_engine.py`
**Target test count:** 50-70

### 8. Domain Models (tests/test_models.py)

**Status:** PENDING
**Description:** The domain models are the value objects and data structures that flow through the entire platform. They live in `enterprise_fizzbuzz/domain/models.py` and have no tests. In a hexagonal architecture, the domain is the most important layer to test because it has no dependencies and should be the most stable.

Test the following:

- **RuleDefinition**: construction, field access, immutability (if frozen dataclass), equality, and ordering by priority.
- **RuleMatch**: construction from a RuleDefinition and a number, field access.
- **FizzBuzzResult**: construction, output string, matched rules list, processing time, metadata dict. Verify it correctly combines multiple rule matches into the output string (e.g., Fizz + Buzz = FizzBuzz).
- **EvaluationResult** (if it exists from the ACL work): construction, classification enum, strategy name.
- **FizzBuzzClassification enum** (if it exists): verify all expected values (FIZZ, BUZZ, FIZZBUZZ, PLAIN).
- **ProcessingContext**: construction, mutability, field access. Verify it carries the number, rules, and result through the pipeline.
- **FizzBuzzSessionSummary**: construction, statistics fields (total numbers, fizz count, buzz count, fizzbuzz count, plain count, processing time).
- **Event types**: construction of each event type, field access, immutability.
- **OutputFormat enum**: verify all expected values (PLAIN, JSON, XML, CSV).

**Output:** `tests/test_models.py`
**Target test count:** 40-55

### 9. End-to-End CLI Tests (tests/test_e2e.py)

**Status:** PENDING
**Description:** There are no end-to-end tests that invoke `main.py` as a subprocess and verify the output. The CLI has 39 flags and countless combinations. An e2e suite that exercises the most important flag combinations would catch integration issues that unit tests miss.

Test the following by running `python main.py` as a subprocess and checking stdout/stderr/exit code:

- **Default run**: `python main.py` produces output for numbers 1-100 with correct FizzBuzz classifications.
- **Custom range**: `--range 1 20` produces exactly 20 lines of output.
- **Each output format**: `--format plain`, `--format json` (valid JSON), `--format xml` (valid XML), `--format csv` (valid CSV with header).
- **Each strategy**: `--strategy standard`, `--strategy chain_of_responsibility`, `--strategy machine_learning`. Verify all produce correct results.
- **Async mode**: `--async` produces correct results.
- **Locale**: `--locale de`, `--locale tlh`. Verify the output contains the localized labels (Sprudel, ghum).
- **Circuit breaker**: `--circuit-breaker --circuit-status` runs without error and produces a status dashboard.
- **Tracing**: `--trace --range 1 5` produces a waterfall diagram.
- **RBAC**: `--user alice --role FIZZBUZZ_SUPERUSER --range 1 20` succeeds. `--user nobody --role ANONYMOUS --range 1 20` produces access denials.
- **Event sourcing**: `--event-sourcing --range 1 10` runs without error.
- **Chaos**: `--chaos --chaos-level 1 --range 1 20` runs without crashing (results may be corrupted, which is the point).
- **Feature flags**: `--feature-flags --range 1 20` runs without error.
- **SLA**: `--sla --range 1 20` runs without error.
- **Cache**: `--cache --cache-stats --range 1 20` runs without error and produces a stats dashboard.
- **Combined flags**: `--circuit-breaker --trace --sla --cache --range 1 20` (the full enterprise stack) runs without error.
- **No banner / no summary**: `--no-banner --no-summary` suppresses both.
- **Help**: `--help` exits 0 and prints usage.
- **Invalid flags**: an unrecognized flag exits non-zero.

Use `subprocess.run` with `capture_output=True`. Set a timeout (30 seconds should be generous) to catch hangs. The ML strategy will need a longer timeout for training.

**Output:** `tests/test_e2e.py`
**Target test count:** 25-40

### 10. Lines of Code Census Bureau (tests/test_loc.py)

**Status:** PENDING
**Description:** The LOC counter is a tool that lives in the repo and measures the repo. It has classes, data models, and an ASCII dashboard renderer. It should have tests, because an untested metrics tool in a repo with 829+ tests would be an embarrassment to Bob.

Test the following:

- **LineCounter**: count lines in a Python file with known content (create a temp file). Verify total, code, blank, and comment counts. Test with `.py`, `.yaml`, and `.fizztranslation` comment syntaxes.
- **FileClassifier**: verify language classification for each known extension. Verify layer classification for paths under `domain/`, `application/`, `infrastructure/`, `tests/`, `locales/`.
- **CensusEngine**: run against a small temp directory with a few known files. Verify the report's grand totals, per-language breakdown, and per-layer breakdown.
- **Overengineering Index**: verify the OEI calculation (total lines / 2). Verify the rating thresholds.
- **CensusDashboard**: render a report and verify the output contains the expected section headers ("BREAKDOWN BY LANGUAGE", "OVERENGINEERING INDEX", "ON-CALL ATTRIBUTION"). Verify Bob is credited with 100% of lines.
- **Edge cases**: empty directory, directory with only binary files, file with zero lines.

**Output:** `tests/test_loc.py`
**Target test count:** 25-35

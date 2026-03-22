# QA & End-to-End Test Roadmap

## From the user

Claude is to maintain the same protocol used for previous roadmaps: plan agent, implement agent, docs update and commit agent. Each item should be planned, implemented, verified, and committed as a discrete unit. Do not batch items or skip the planning step. The existing codebase has ~4,200 unit tests across 55+ test files with per-module coverage. What it lacks is comprehensive end-to-end and integration testing. Every CLI flag combination, every subsystem interaction, every multi-middleware pipeline path, every failure mode that only surfaces when the full stack is assembled. The unit tests prove the parts work. This roadmap proves the machine works.

These 10 items are big. Break them down into manageable cycles as you see fit. An item like "E2E: Infrastructure subsystems" with 30+ individual subsystem flags doesn't need to be one monolithic PR. Split items into sub-batches (e.g., by subsystem group, by complexity, by dependency) so each cycle is a reviewable, testable, committable unit. Use your judgment on sizing. The goal is steady forward progress, not heroic single-pass implementations that take 45 minutes and produce 800 lines of untested tests.

---

## Note to the orchestration Claude

This roadmap is a test-only backlog. No item modifies existing source code. Every item produces test files in the `tests/` directory (or `tests/e2e/`, `tests/integration/` subdirectories as specified).

Ground rules for the workers:

1. **Read the modules under test before writing tests.** Open the actual source files. Read the CLI flag definitions in `main.py` and `enterprise_fizzbuzz/__main__.py`. Read the `FizzBuzzServiceBuilder` to understand how subsystems are wired. Don't guess at behavior from the README.

2. **Match the project's existing test style.** Look at `test_e2e.py` for the subprocess invocation pattern (`run_cli` helper, `--no-banner` default, `extract_fizzbuzz_lines`). Look at unit test files for fixture patterns, class organization, and assertion style. Follow the same conventions.

3. **Satire is mandatory.** This is still the Enterprise FizzBuzz Platform. Test names and docstrings should maintain the same deadpan commitment to the bit. A test called `test_full_enterprise_stack_evaluates_fifteen_through_forty_seven_middleware_layers` is funnier than `test_integration_lol`. The comedy is in the precision and the gravity.

4. **Tests must actually pass.** Run the tests against the real codebase. If a test can't pass because of a genuine bug, note it as a known issue in a comment and mark it `@pytest.mark.skip(reason="...")`. If a test can't be written without modifying source code, skip it and note why.

5. **Each item is independent.** They can be worked in any order and by different workers.

6. **Update this file** when completing an item: change its status from PENDING to DONE and note the test count.

---

## Current State

The platform has ~4,200 unit tests across 55+ test files. Every infrastructure module has a dedicated test file. Three contract test suites verify interface conformance (formatters, repositories, strategies). There is one e2e test file (`test_e2e.py`, ~42 tests) that exercises basic CLI flag combinations via subprocess.

What's missing:

- **Deep e2e coverage**: The existing e2e tests cover ~15 of the 90+ CLI flags. Many flag combinations, especially the newer subsystems (quantum, cross-compiler, federated learning, knowledge graph, paxos, formal verification, FBaaS, time-travel, bytecode VM, query optimizer, load testing, audit dashboard, gitops, genetic algorithm, NLQ, graph DB, blue/green, secrets vault, data pipeline, message queue, A/B testing), have no e2e coverage at all.
- **Multi-subsystem integration tests**: No tests verify that subsystems interact correctly when multiple are enabled simultaneously. The compliance module and the blockchain module have a documented philosophical conflict (GDPR erasure vs. immutable chain). The SLA module monitors the output of every other module. The chaos module disrupts the output of every other module. These interactions are untested as a composed system.
- **Pipeline composition tests**: The middleware pipeline can have 20+ middlewares active simultaneously, each at a different priority. No tests verify the full ordering, context propagation, and error handling across a realistically composed pipeline.
- **Dashboard and output rendering tests**: Every subsystem has an ASCII dashboard. None of the dashboards are tested for rendering correctness after a real evaluation run (only in isolation with mock data).
- **Regression tests**: No tests specifically target known edge cases at system boundaries (e.g., what happens when the cache returns a result that the SLA module then measures as 0ns latency; what happens when chaos corrupts a result that compliance then classifies).

## Backlog Status
- Total items: 10
- Implemented: 9
- Remaining: 1

---

## Test Items

### 1. Comprehensive E2E: Evaluation Strategies (tests/e2e/test_e2e_strategies.py)

**Status:** DONE (30 tests)
**Description:** The platform has four core evaluation strategies (standard, chain_of_responsibility, parallel_async, machine_learning) plus three additional computational strategies (genetic_algorithm via `--genetic`, bytecode_vm via `--vm`, quantum via `--quantum`). The existing e2e tests cover standard, chain_of_responsibility, and machine_learning. The rest have no subprocess-level coverage.

Test the following by invoking `main.py` as a subprocess:

- **Each strategy in isolation**: `--strategy standard`, `--strategy chain_of_responsibility`, `--strategy parallel_async`, `--strategy machine_learning`. Verify all produce identical, correct FizzBuzz output for `--range 1 30`.
- **Cross-strategy consistency**: Run all four strategies on the same range and diff the outputs. They must be identical. This is the most important e2e assertion in the repo: it proves that replacing modulo with a neural network, a chain of handlers, and an async pipeline was pointless, which is the joke.
- **Async mode**: `--async --range 1 30` produces correct results. `--async --strategy machine_learning` produces correct results.
- **Bytecode VM**: `--vm --range 1 30` produces correct output. `--vm --vm-dashboard` includes a dashboard section in output. `--vm --vm-disassemble` produces disassembly output.
- **Quantum strategy**: `--strategy machine_learning --quantum --range 1 15 --no-summary` runs without error (may be slow). Verify exit code 0 and that output contains FizzBuzz classifications.
- **Genetic algorithm**: `--genetic --genetic-generations 10 --range 1 20` runs without error. Verify the genetic dashboard or summary appears in output.
- **Paxos consensus**: `--paxos --range 1 20` produces correct output agreed upon by the simulated cluster.
- **Combined computational strategies**: `--strategy machine_learning --quantum --paxos --range 1 10` (the full multi-strategy stack) exits 0.
- **Invalid strategy name**: `--strategy nonexistent_strategy` exits non-zero with an error message.

**Output:** `tests/e2e/test_e2e_strategies.py`
**Target test count:** 25-40

---

### 2. Comprehensive E2E: Output Formats and Locales (tests/e2e/test_e2e_output.py)

**Status:** DONE (55 tests)
**Description:** The platform supports four output formats (plain, json, xml, csv) and seven locales (en, de, fr, ja, tlh, sjn, qya). The existing e2e tests cover the four formats but none of the non-English locales through the full CLI path. Locales interact with formatters (a JSON-formatted Klingon FizzBuzz is a valid use case that nobody has tested).

Test the following:

- **Each format**: `--format plain`, `--format json`, `--format xml`, `--format csv` for `--range 1 20`. Verify:
  - Plain: correct line count, correct classifications for known numbers.
  - JSON: output parses as valid JSON, contains expected fields, correct classification values.
  - XML: output parses as valid XML via `xml.etree.ElementTree`, contains expected elements.
  - CSV: output parses as valid CSV via `csv.reader`, has header row, correct row count.
- **Each locale**: `--locale en`, `--locale de`, `--locale fr`, `--locale ja`, `--locale tlh`, `--locale sjn`, `--locale qya`, each with `--range 1 15 --format plain`. Verify the output contains the locale-appropriate labels (e.g., German: "Sprudel"/"Braus"/"SprudelBraus"; Klingon: "ghum"/"wab"/"ghumwab"; Quenya: "Winge"/"Lama"/"WingeLama" or similar).
- **Format + locale combinations**: `--format json --locale de`, `--format xml --locale tlh`, `--format csv --locale sjn`. Verify the structured output contains localized labels, not English ones.
- **Metadata in JSON**: `--format json --metadata --range 1 5`. Verify the JSON output includes metadata fields (processing time, strategy, etc.).
- **No-summary and no-banner**: `--no-summary --no-banner --range 1 5 --format plain` produces only the five result lines with no extra output.
- **Invalid format**: `--format yaml` exits non-zero (YAML is not a supported format, despite the config file being YAML, which is ironic but intentional).
- **Invalid locale**: `--locale xx` exits non-zero or falls back gracefully.

**Output:** `tests/e2e/test_e2e_output.py`
**Target test count:** 30-45

---

### 3. Comprehensive E2E: Infrastructure Subsystems (tests/e2e/test_e2e_subsystems.py)

**Status:** DONE (51 tests: 49 passing, 2 skipped due to known bugs)
**Description:** The platform has 30+ optional infrastructure subsystems, each activated by one or more CLI flags. The existing e2e tests cover ~8 of them (circuit breaker, tracing, SLA, cache, chaos, event sourcing, feature flags, RBAC). The remaining 20+ subsystems have never been invoked through the CLI in a test. This item covers every subsystem that has a CLI flag, invoked individually.

Test the following (each as a separate test, each verifying exit code 0 and absence of Python tracebacks in stderr):

- **Blockchain**: `--blockchain --range 1 20`
- **Compliance**: `--compliance --range 1 20`. Also: `--compliance --compliance-regime gdpr`, `--compliance --compliance-regime sox`, `--compliance --compliance-regime hipaa`.
- **FinOps**: `--cost-tracking --range 1 20`
- **Health probes**: `--health --range 1 20`
- **Metrics**: `--metrics --range 1 20`
- **Webhooks**: `--webhooks --range 1 20`
- **Service mesh**: `--service-mesh --range 1 20`
- **Hot reload**: `--hot-reload --range 1 20`
- **Rate limiting**: `--rate-limit --range 1 20`
- **Disaster recovery**: `--disaster-recovery --range 1 20`
- **A/B testing**: `--ab-testing --range 1 20`
- **Message queue**: `--message-queue --range 1 20`
- **Secrets vault**: `--vault --range 1 20`
- **Data pipeline**: `--data-pipeline --range 1 20`
- **OpenAPI**: `--openapi --range 1 20`
- **API gateway**: `--api-gateway --range 1 20`
- **Blue/green deployment**: `--blue-green --range 1 20`
- **Graph database**: `--graph-db --range 1 20`
- **NLQ**: `--nlq --range 1 20` (if applicable as a batch flag; otherwise test `--nlq-query "Is 15 FizzBuzz?"`)
- **Load testing**: `--load-test --load-test-profile smoke --range 1 20`
- **Audit dashboard**: `--audit-dashboard --range 1 20`
- **GitOps**: `--gitops --range 1 20`
- **Formal verification**: `--formal-verify --range 1 20`
- **FBaaS**: `--fbaas --range 1 10`
- **Time-travel debugger**: `--time-travel --range 1 20`
- **Query optimizer**: `--query-optimizer --range 1 20`
- **Cross-compiler**: `--compile-to c --range 1 20`, `--compile-to rust --range 1 20`, `--compile-to wasm --range 1 20`
- **Federated learning**: `--federated --fed-nodes 3 --fed-rounds 2 --range 1 15`
- **Knowledge graph**: `--knowledge-graph --range 1 20`
- **LOC census**: `--loc` (if it has a CLI flag)

Note: Some of these flags may not exist or may have different names. The worker MUST read `main.py` (or `__main__.py`) to discover the actual flag names before writing tests. If a subsystem has no CLI flag, note it as untestable via e2e and skip it.

**Output:** `tests/e2e/test_e2e_subsystems.py`
**Target test count:** 30-50

---

### 4. E2E: Multi-Subsystem Combinations (tests/e2e/test_e2e_combinations.py)

**Status:** DONE (33 tests)
**Description:** The real complexity of the platform isn't in any single subsystem; it's in what happens when you turn on five, ten, fifteen of them simultaneously. The middleware pipeline sorts by priority, subsystems publish events that other subsystems consume, and the processing context accumulates metadata from every layer it passes through. No existing test verifies that the full enterprise stack, with all reasonable subsystems enabled, produces correct output and exits cleanly.

Test the following:

- **The "full enterprise" stack**: Enable every non-destructive subsystem simultaneously. Something like: `--circuit-breaker --trace --sla --cache --blockchain --compliance --cost-tracking --health --metrics --feature-flags --event-sourcing --disaster-recovery --range 1 20 --format json`. Verify exit 0, valid JSON output, and correct FizzBuzz classifications extractable from the output.
- **Observability stack**: `--trace --sla --metrics --health --audit-dashboard --range 1 20`. Verify exit 0.
- **Security stack**: `--user alice --role FIZZBUZZ_SUPERUSER --vault --compliance --range 1 20`. Verify exit 0.
- **ML + observability**: `--strategy machine_learning --trace --sla --metrics --range 1 20`. Verify exit 0 and correct results.
- **Chaos + circuit breaker + SLA**: `--chaos --chaos-level 1 --circuit-breaker --sla --range 1 30`. Verify exit 0 (results may be corrupted, but the process should not crash).
- **Cache + SLA interaction**: `--cache --sla --range 1 20` followed by a second run. The cache should return results faster, and the SLA module should record lower latencies on the cached run.
- **FBaaS + compliance**: `--fbaas --compliance --range 1 10`. Verify that the FBaaS watermark (if Free tier) and compliance checks both apply.
- **Event sourcing + disaster recovery**: `--event-sourcing --disaster-recovery --range 1 20`. Verify both subsystems co-exist without conflict.
- **All formatters with full stack**: `--format json --circuit-breaker --trace --sla --cache --range 1 10`, then repeat with `--format xml`, `--format csv`. Verify each format produces valid, parseable output even with all the extra middleware metadata.
- **Flag count stress test**: Enable as many flags as possible without contradiction and verify the CLI still boots and exits within the timeout. This tests argument parsing, service builder wiring, and middleware pipeline assembly at scale.

**Output:** `tests/e2e/test_e2e_combinations.py`
**Target test count:** 20-30

---

### 5. Integration: Middleware Pipeline Composition (tests/integration/test_pipeline_integration.py)

**Status:** DONE (44 tests)
**Description:** The middleware pipeline is the spinal cord of the platform. Unit tests verify individual middlewares. This item tests the pipeline as a composed system, instantiated in-process (not via subprocess) with multiple real middlewares wired together in priority order. The goal is to verify ordering, context propagation, metadata accumulation, and error handling across the actual middleware stack.

Test the following by importing and composing real middleware classes:

- **Priority ordering verification**: Instantiate 5+ middlewares (e.g., AuthorizationMiddleware at -10, QuantumMiddleware at -7, ComplianceMiddleware at -5, FBaaSMiddleware at -1, ValidationMiddleware at 0, ChaosMiddleware at 3, SLAMiddleware at 55). Verify they execute in ascending priority order by checking metadata stamps or using a recording observer.
- **Context metadata accumulation**: Run a number through a pipeline with tracing, SLA, compliance, and FinOps middlewares. Verify the final `ProcessingContext.metadata` dict contains keys from each middleware (`sla_latency_ns`, `compliance_checks`, `finops_cost`, `trace_id`, etc.).
- **Error propagation**: Insert a middleware that raises an exception. Verify the pipeline's behavior: does it propagate? Does the SLA middleware record the failure? Does the circuit breaker trip?
- **Chaos + SLA interaction**: Enable chaos middleware (result corruption) and SLA middleware. Run 50 evaluations. Verify the SLA module detects accuracy violations when chaos corrupts results.
- **Cache hit path**: Run a number through a pipeline with cache middleware twice. Verify the second invocation returns the cached result and the SLA module records a faster latency.
- **RBAC denial path**: Configure an ANONYMOUS auth context and attempt to evaluate number 51 (above the range for ANONYMOUS). Verify `InsufficientFizzPrivilegesError` is raised with the 47-field denial body.
- **Full middleware chain for number 15**: Trace the evaluation of 15 through a maximally-composed pipeline and verify the final result is "FizzBuzz" despite passing through authorization, compliance, caching, tracing, SLA, FinOps, and event emission layers.

**Output:** `tests/integration/test_pipeline_integration.py`
**Target test count:** 25-40

---

### 6. Integration: Event Bus Cross-Subsystem Communication (tests/integration/test_event_integration.py)

**Status:** DONE (32 tests)
**Description:** The event bus is the nervous system of the platform. Every subsystem publishes events, and several subsystems subscribe to events from others (SLA monitors evaluation events, the audit dashboard aggregates all events, the metrics exporter counts events by type). No test verifies that events published by one real subsystem are received and correctly processed by another real subsystem.

Test the following by instantiating real subsystems with a shared event bus:

- **Evaluation events reach SLA**: Wire the rule engine and SLA monitor to the same event bus. Evaluate a number. Verify the SLA monitor's metric collector recorded the evaluation.
- **Chaos events reach audit dashboard**: Wire the chaos monkey and audit dashboard aggregator to the same event bus. Inject a fault. Verify the audit dashboard's event log contains the chaos event.
- **Compliance events reach metrics**: Wire the compliance framework and metrics exporter to the same event bus. Run a compliance check. Verify the metrics exporter has a counter for compliance events.
- **SLA alert events**: Wire the SLA monitor with a very tight latency SLO (e.g., 0.0001ms). Run an evaluation that exceeds this threshold. Verify an alert event was published and the alert manager recorded it.
- **Circuit breaker state change events**: Wire the circuit breaker to the event bus. Trip the circuit breaker (by injecting failures). Verify state transition events (CLOSED -> OPEN) were published.
- **Event ordering**: Publish 100 events of different types from different subsystems. Verify the audit dashboard's aggregator received them in the order they were published.
- **Event bus under load**: Publish 10,000 events rapidly. Verify no events are dropped and the subscriber count is correct.

**Output:** `tests/integration/test_event_integration.py`
**Target test count:** 20-35

---

### 7. Integration: The Compliance Paradox (tests/integration/test_compliance_paradox.py)

**Status:** DONE (26 tests)
**Description:** The platform's single most famous architectural conflict: GDPR's right-to-erasure vs. the append-only event store, immutable blockchain, and SOX audit retention requirements. The compliance module documents this paradox. The README devotes an entire FAQ entry to it. But no test actually triggers the full paradox path with all relevant subsystems live and verifies the resulting behavior across the event store, blockchain, cache, and compliance audit trail.

Test the following with real subsystem instances:

- **Erasure request with live event store**: Populate the event store with evaluation events for number 42. Issue a GDPR erasure request for 42. Verify the event store still contains the events (it's append-only). Verify the erasure certificate documents the refusal.
- **Erasure request with live blockchain**: Mine blocks containing evaluation results for number 42. Issue an erasure request. Verify the blockchain chain is unmodified (immutable). Verify the certificate lists the blockchain as a refused store.
- **Erasure request with live cache**: Cache a result for number 42. Issue an erasure request. Verify the cache no longer contains the result (the cache CAN be erased). Verify the certificate lists the cache as a successfully erased store.
- **Full paradox path**: Enable event sourcing, blockchain, cache, compliance (all three regimes), and SLA. Evaluate number 42. Issue a GDPR erasure request. Verify:
  - The `GDPRErasureParadoxError` path is triggered (or a `DataDeletionCertificate` with status `PARADOX_ENCOUNTERED`).
  - The certificate lists which stores were erased and which refused.
  - Bob McFizzington's stress level increased by 5.0%.
  - A compliance event was published to the event bus.
  - The SOX audit trail contains a record of the erasure attempt (itself a compliance obligation that conflicts with the erasure).
- **Multiple erasure requests**: Issue erasure requests for numbers 3, 5, 15, and 42. Verify the paradox count increments correctly and each certificate is distinct.
- **Bob's stress level trajectory**: Run 20 compliance checks followed by 3 erasure requests. Verify Bob's stress level is 94.7 + (20 * 0.3) + (3 * 5.0) = 115.7% (approximately, accounting for any non-compliant verdicts that add 1.5% each). Verify the dashboard mood indicator has progressed to "BEYOND HELP - Send chocolate."

**Output:** `tests/integration/test_compliance_paradox.py`
**Target test count:** 15-25

---

### 8. Integration: Dashboard Rendering After Real Evaluations (tests/integration/test_dashboards_live.py)

**Status:** DONE (32 tests)
**Description:** Every subsystem has an ASCII dashboard. Unit tests render dashboards with mock data. No test renders a dashboard after a real evaluation session and verifies it contains actual, non-zero metrics from the run. A dashboard full of zeros is a dashboard that proves nothing.

Test the following by running real evaluations and then rendering the corresponding dashboard:

- **SLA Dashboard**: Run 50 evaluations through the SLA-monitored pipeline. Render `SLADashboard.render()`. Verify the output contains non-zero total evaluations, non-zero P50/P99 latency values, and on-call status showing Bob McFizzington.
- **Compliance Dashboard**: Run 20 evaluations through the compliance pipeline. Render `ComplianceDashboard.render()`. Verify the output contains non-zero compliance rate, Bob's stress level above 94.7%, and data classification counts.
- **FinOps Invoice**: Run 30 evaluations through the FinOps pipeline. Render `InvoiceGenerator.generate()`. Verify the invoice contains non-zero subtotal, tax breakdown (Fizz at 3%, Buzz at 5%, FizzBuzz at 15%), and a budget utilization bar.
- **Cache Statistics**: Run 50 evaluations through a cached pipeline (some numbers repeated). Render the cache stats. Verify non-zero hit count and a hit rate above 0%.
- **Circuit Breaker Dashboard**: Trip the circuit breaker (inject failures), then render its dashboard. Verify it shows OPEN state with non-zero failure count.
- **Chaos Post-Mortem**: Run a chaos experiment (severity level 2, 20 evaluations). Render `PostMortemGenerator.generate()`. Verify the report contains a non-empty incident timeline, fault type breakdown, and at least one action item.
- **DR Dashboard**: Run evaluations through the DR middleware (which writes WAL entries and auto-snapshots). Render `RecoveryDashboard.render()`. Verify non-zero WAL entries, at least one backup in the vault, and the storage medium listed as "RAM (volatile)."
- **Health Dashboard**: Register health checks, run evaluations, render the health report. Verify subsystem statuses are populated (not all UNKNOWN).
- **Quantum Dashboard**: Run 10 evaluations through the quantum engine. Render `QuantumDashboard.render()`. Verify the Quantum Advantage ratio is negative and the disclaimer about no actual quantum hardware is present.
- **FBaaS Dashboard**: Create a tenant, run evaluations through FBaaS middleware, render the dashboard. Verify non-zero MRR (for paid tiers) or non-zero evaluation count (for free tier).

**Output:** `tests/integration/test_dashboards_live.py`
**Target test count:** 20-30

---

### 9. Regression: Cross-Subsystem Edge Cases (tests/integration/test_cross_subsystem_regression.py)

**Status:** DONE (30 tests)
**Description:** This item covers specific edge cases and known interaction patterns between subsystems that could produce surprising behavior. These are the tests that a QA engineer writes after reading the source code and thinking "wait, what happens when..."

Test the following:

- **Cache + chaos**: Enable cache and chaos (result corruption). Evaluate number 15 (gets cached as "FizzBuzz"). Enable chaos corruption. Evaluate number 15 again. Verify the cached result is returned, NOT a chaos-corrupted one (cache should bypass chaos on hit).
- **SLA accuracy with ML strategy**: Use the ML strategy. Verify the SLA module's accuracy check (which recomputes ground truth via modulo) reports 100% accuracy. This tests that the SLA module doesn't just trust the pipeline -- it independently verifies.
- **Feature flag disabling ML mid-run**: Enable ML strategy and a feature flag for ML. Disable the feature flag programmatically. Verify the system falls back gracefully (either to standard strategy or to an error, but not to a crash).
- **Rate limiter + FBaaS quota interaction**: Enable both rate limiting and FBaaS with a Free tier (10 evaluations/day). Verify the more restrictive limit applies.
- **Hot reload + SLA**: Change a config value (e.g., SLO threshold) via hot reload. Verify subsequent SLA checks use the new threshold.
- **Paxos with chaos**: Enable Paxos consensus and chaos (with Byzantine fault injection if supported). Verify the honest majority still produces correct results.
- **Zero-length range**: `--range 1 1` evaluates exactly one number. Verify all subsystems handle a single evaluation gracefully (no division by zero in statistics, no empty-list errors in dashboards).
- **Range starting at 0**: `--range 0 5` -- verify behavior for number 0. Does `0 % 3 == 0` make 0 a "Fizz"? Verify the platform's answer is consistent across all strategies.
- **Large range with all subsystems**: `--range 1 1000` with cache, SLA, and FinOps enabled. Verify it completes within the timeout and produces 1,000 results.
- **Duplicate evaluation**: Evaluate the same number twice through the event sourcing pipeline. Verify two separate events are recorded (no deduplication -- each evaluation is its own event).

**Output:** `tests/integration/test_cross_subsystem_regression.py`
**Target test count:** 20-30

---

### 10. Contract Tests: Newer Interfaces (tests/contracts/test_middleware_contract.py, tests/contracts/test_engine_contract.py)

**Status:** PENDING
**Description:** The existing contract test suite covers formatters, repositories, and strategies. But the `IMiddleware` interface (implemented by 20+ middleware classes) and the various engine interfaces have no contract tests. Every class that implements `IMiddleware` should honor the same behavioral contract: `process()` receives a context and a next_handler, calls next_handler at some point (or doesn't, if short-circuiting), and returns a `ProcessingContext`. Every class that implements `IRuleEngine` should accept a number and return a result with the correct classification.

Test the following:

- **IMiddleware contract** (`tests/contracts/test_middleware_contract.py`): For every class that implements `IMiddleware`:
  - `get_name()` returns a non-empty string.
  - `get_priority()` returns an integer.
  - `process()` accepts a `ProcessingContext` and a callable `next_handler`.
  - `process()` returns a `ProcessingContext` (not None, not something else).
  - If the middleware is non-blocking, `process()` calls `next_handler` at least once.
  - Two different middleware instances of the same class return the same priority (priority is a class property, not instance-dependent).
  - Discover all IMiddleware implementations dynamically by scanning the infrastructure package, so new middlewares added in the future are automatically covered.

- **IRuleEngine contract** (`tests/contracts/test_engine_contract.py`): For every class that implements `IRuleEngine` (StandardRuleEngine, ChainOfResponsibilityEngine, ParallelAsyncEngine, MLRuleEngine, etc.):
  - `evaluate(15)` returns a result whose output is "FizzBuzz".
  - `evaluate(3)` returns "Fizz".
  - `evaluate(5)` returns "Buzz".
  - `evaluate(7)` returns "7".
  - All engines produce identical results for numbers 1-100.
  - Discover all IRuleEngine implementations dynamically.

- **Update `test_contract_coverage.py`**: After adding the new contract suites, verify that the meta-test still passes (every abstract port has a corresponding contract test).

**Output:** `tests/contracts/test_middleware_contract.py`, `tests/contracts/test_engine_contract.py`, updates to `tests/test_contract_coverage.py`
**Target test count:** 40-60

---

## Summary

| # | Item | Type | Target Tests | Focus |
|---|------|------|:---:|-------|
| 1 | E2E: Evaluation strategies | E2E (subprocess) | 25-40 | Every strategy through the CLI |
| 2 | E2E: Output formats and locales | E2E (subprocess) | 30-45 | Every format x locale combination |
| 3 | E2E: Infrastructure subsystems | E2E (subprocess) | 30-50 | Every subsystem's CLI flag, individually |
| 4 | E2E: Multi-subsystem combinations | E2E (subprocess) | 20-30 | The full enterprise stack, composed |
| 5 | Integration: Middleware pipeline | Integration (in-process) | 25-40 | Priority ordering, context propagation, error paths |
| 6 | Integration: Event bus cross-subsystem | Integration (in-process) | 20-35 | Events published by one, consumed by another |
| 7 | Integration: The Compliance Paradox | Integration (in-process) | 15-25 | GDPR vs. blockchain vs. SOX, end to end |
| 8 | Integration: Dashboard rendering | Integration (in-process) | 20-30 | Dashboards with real data, not mocks |
| 9 | Regression: Cross-subsystem edge cases | Integration (in-process) | 20-30 | The "wait, what happens when..." tests |
| 10 | Contract: Newer interfaces | Contract | 40-60 | IMiddleware and IRuleEngine conformance |

**Total target: 245-385 new tests**
**Projected platform test count after completion: ~4,500-4,600 tests**

---

> *"Unit tests prove the parts work. Integration tests prove the parts work together. End-to-end tests prove the machine works. This roadmap covers the latter two, because 4,200 unit tests and zero integration tests is just 4,200 proofs that individual modulo operations are correct, arranged in a trench coat pretending to be a test suite."*

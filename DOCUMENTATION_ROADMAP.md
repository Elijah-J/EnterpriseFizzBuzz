# Documentation Roadmap

## Note to the orchestration Claude

This roadmap is a documentation-only backlog. None of these items add features, change behavior, or modify existing code. Every item produces markdown files in a `docs/` directory (create it if it doesn't exist).

A few ground rules for the workers:

1. **Read the source code, not just the README.** The README is entertaining but imprecise. The docs should be generated from what the code actually does, not from what the README says it does. Workers should read the relevant modules before writing about them. If the README says there are 47 fields in the access denied response, the worker should open `auth.py` and count.

2. **This is a satirical project. The docs should be too.** The Enterprise FizzBuzz Platform is a comedy project disguised as enterprise software. The documentation should be enterprise documentation disguised as comedy. Write everything with complete sincerity, as if this is a real platform that genuinely requires architecture decision records, a runbook, and an exception catalog. The humor comes from treating absurd things seriously, not from breaking character to wink at the reader. Study the tone of the README, the existing docstrings, and the brainstorm reports. The codebase already has a voice: deadpan, committed to the bit, and willing to follow an absurd premise to its logical conclusion. The docs should match. A few specific notes on how this plays out per document type:
    - **Reference docs** (architecture, configuration, exceptions): these should read like real reference docs for a real platform. The comedy is that the platform computes `n % 3`. You don't need to point that out; the reader knows. Just document the MESI cache coherence protocol with the same care you'd document a real one. If the absurdity of a subsystem is self-evident from a factual description, a factual description is funnier than a joke.
    - **ADRs**: use the standard format (Title, Status, Context, Decision, Consequences). Write them as a real engineering team would, but for decisions like "staff all four escalation tiers with one person" and "implement a proprietary file format because JSON lacked gravitas." The format's seriousness does the comedic work.
    - **Runbook**: write it as a real on-call runbook. Bob McFizzington is a real engineer. His escalation procedure is real. The decision tree for triaging a latency alert on a FizzBuzz platform should be as thorough as one for a real production service. The joke is the thoroughness, not any commentary on it.
    - **Developer guide**: this one should actually be useful. Someone (a Claude) will need to follow these instructions to add features. It can still be funny, but the walkthrough needs to be accurate and complete.

3. **Reference real file paths, class names, and method signatures.** These docs are for navigating a 24,800-line codebase. Vague descriptions are useless. If a document says "the middleware pipeline processes the request," it should say which class, which method, and at what priority number.

4. **Don't update the README.** The README is its own thing. These docs supplement it, not replace it.

5. **Each item is independent.** They can be worked in any order and by different workers. No item depends on another item being completed first. However, items 1 (architecture overview) and 2 (configuration reference) are the highest value and should be prioritized if ordering matters.

6. **Update this file** when completing an item: change its status from PENDING to DONE and note the output path.

## Current State

The platform's documentation consists of a single README.md (approximately 1,200 lines, mostly CLI examples and ASCII diagrams) and a linguistic validation report for the Elvish locales. The README functions as a combined marketing brochure, architecture overview, FAQ, and comedy special. It is not documentation in any operational sense.

There is no `docs/` directory, no developer guide, no architecture decision records, no configuration reference, no runbook, and no API or module reference beyond inline docstrings. A new contributor (human or Claude) must read 24,800 lines of source code to understand how the system fits together.

## Backlog Status
- Total items: 8
- Implemented: 1
- Remaining: 7

## Documentation Items

### 1. Architecture Overview (docs/architecture.md)

**Status:** DONE
**Output path:** `docs/architecture.md`
**Description:** A standalone architecture document that explains how the system is structured and why. This is not the README, but it should share the README's commitment to taking the platform seriously.

Cover the following:

- The hexagonal layer structure (`domain/`, `application/`, `infrastructure/`) and the dependency rule (inward only, never outward). Include a directory tree of `enterprise_fizzbuzz/` with one-line descriptions of each module.
- The request lifecycle: trace a single number (use 15) from CLI argument through config resolution, authentication, middleware pipeline, feature flag evaluation, rule engine dispatch, caching, event emission, SLA recording, and output formatting. Name every class and method it passes through, in order.
- The middleware pipeline: list every middleware by priority number, explain the ordering, and describe what each one does to the evaluation context on the way in and out.
- The event system: how the observer bus works, what events are emitted, and who subscribes to them.
- A dependency graph of the major components. Which subsystems depend on which. Use a Mermaid diagram.
- A table listing every subsystem, whether it's optional or always-on, and which CLI flags activate it.

This document is for someone who needs to find where something lives and how it connects to everything else. It should be thorough, navigable, and written as if the architecture warrants this level of documentation. Which, at 24,800 lines, it arguably does.

**Output:** `docs/architecture.md`
**Estimated size:** 400-600 lines

### 2. Configuration Reference (docs/configuration.md)

**Status:** PENDING
**Description:** A complete reference for every configuration surface in the platform. Currently, configuration lives in three places: `config.yaml`, environment variables (`EFP_*`), and CLI flags. The README lists CLI flags and some env vars, but there is no single document that maps all three layers together and explains the precedence rules.

Cover the following:

- Parse `config.yaml` and document every key, its type, default value, and what it controls. Group by section (evaluation, output, circuit_breaker, tracing, auth, event_sourcing, chaos, feature_flags, sla, cache, i18n, logging, middleware).
- For each config key, list the corresponding `EFP_*` environment variable override and CLI flag (if any).
- Explain the precedence order: CLI flag > environment variable > config.yaml > hardcoded default.
- Document the feature flag definitions in config.yaml separately, since they have their own schema (flag type, default state, rollout percentage, targeting rules, dependencies).
- Document the `.fizztranslation` file format: directives (`@locale`, `@name`, `@fallback`, `@plural_rule`), sections (`[labels]`, `[plurals]`, `[messages]`, `[summary]`, `[banner]`, `[status]`), variable interpolation (`${var}`), heredoc syntax, and comment syntax (`;;`). Treat it with the same seriousness as any proprietary file format specification.

This should be a reference, not a tutorial. Someone should be able to ctrl-F for a config key and find its type, default, env var, and CLI flag in one place.

**Output:** `docs/configuration.md`
**Estimated size:** 300-500 lines

### 3. Developer Guide (docs/developer-guide.md)

**Status:** PENDING
**Description:** A practical guide for someone who wants to add a new feature to the platform. Walk through the actual steps, referencing real files and classes. This document needs to be genuinely useful since future Claude workers will follow it.

Cover the following:

- **Adding a new rule** (e.g., "Wuzz" for divisor 7): where to define the rule, how to register it in the factory, how to add it to the ML training pipeline, how to create locale entries for it in all 7 `.fizztranslation` files, how to write tests for it.
- **Adding a new middleware**: how to implement the `IMiddleware` interface, how priority ordering works, where to register it so the pipeline picks it up.
- **Adding a new locale**: how to create a `.fizztranslation` file, what sections are required vs. optional, how the fallback chain works, how pluralization rules are defined, how to add tests. Note the existence of the linguistic validation report and the standard it sets.
- **Adding a new evaluation strategy**: what interface to implement, how to register it with the factory, how to wire it into the CLI.
- **Adding a new CLI flag**: where flags are defined, how they propagate through config, how to thread them into the service builder.
- **Running tests**: how to run the full suite, how to run a single test module, what the test directory structure looks like after the hexagonal restructuring.

Each section should be a concrete walkthrough with file paths and class names, not abstract advice. The tone can be conversational and wry, but the instructions must be accurate and complete.

**Output:** `docs/developer-guide.md`
**Estimated size:** 400-600 lines

### 4. RBAC & Security Reference (docs/security.md)

**Status:** PENDING
**Description:** The auth system is one of the more complex subsystems and its behavior is only partially described in the README. Document it as a proper security reference, with the gravity that HMAC-SHA256-signed FizzBuzz tokens deserve.

Cover the following:

- The role hierarchy: all five roles, their permissions, and the inheritance chain. Show which permissions each role accumulates from its ancestors.
- The permission string format (`resource:range_spec:action`): what each segment means, what wildcards are supported, what `fizz`, `buzz`, `fizzbuzz` mean as range specs, how numeric ranges (`1-50`, `1-100`) work.
- Token format: the `EFP.<base64url_payload>.<hmac_sha256_hex>` structure, every field in the payload (`sub`, `role`, `iat`, `exp`, `jti`, `iss`, `fizz_clearance_level`, `buzz_clearance_level`, `favorite_prime`), how to generate a valid token, how signature verification works.
- Trust-mode authentication: how `--user` and `--role` bypass token verification, and why this exists.
- The 47-field access denied response: list every field, its type, and where the value comes from. The README describes this with flair; this document should list the fields as a reference table while maintaining the voice.
- How `AuthorizationMiddleware` intercepts evaluations: at what priority, what it checks, what happens on failure.

**Output:** `docs/security.md`
**Estimated size:** 300-400 lines

### 5. Runbook for Bob (docs/runbook.md)

**Status:** PENDING
**Description:** An operational runbook written as if Bob McFizzington is a real on-call engineer responding to real incidents. This document is both functional documentation for the SLA/alerting/chaos subsystems and a continuation of the Bob bit.

Cover the following:

- **Alert triage**: what each alert severity (P1-P4) means, what SLO was violated, and what to do about it. Include a decision tree: latency violation -> check if chaos monkey is active -> check circuit breaker state -> check ML confidence scores -> escalate (to yourself).
- **Circuit breaker recovery**: how to interpret the circuit breaker dashboard, what the three states mean operationally, what triggers a state transition, how to manually reset if needed.
- **Chaos incident response**: how to identify that a chaos experiment is running, how to determine the severity level, how to read the post-mortem report, what "action items" to ignore.
- **SLA dashboard interpretation**: what each metric on the dashboard means, how to calculate remaining error budget manually, what the burn rate numbers imply.
- **Cache diagnostics**: how to read the cache stats dashboard, what a low hit rate means, how to identify MESI state anomalies.
- **Escalation procedure**: the four-tier escalation chain, who is on each tier (Bob), what each tier's responsibilities are, and the phone number to call (+1-555-FIZZBUZZ).

Write it as a real runbook. Bob is a real engineer. His problems are real problems. The escalation procedure is a real procedure. The comedy writes itself; the prose doesn't need to.

**Output:** `docs/runbook.md`
**Estimated size:** 300-500 lines

### 6. Architecture Decision Records (docs/adr/)

**Status:** PENDING
**Description:** Retroactively document the major design decisions as ADRs using the standard format (Title, Status, Context, Decision, Consequences). One file per decision.

Write the following ADRs:

- **ADR-001: Use a neural network for divisibility checking.** Context: stakeholders requested an AI-driven solution. Decision: implement a from-scratch MLP with cyclical feature encoding. Consequences: 100% accuracy, 150ms cold start, 130 trainable parameters, zero dependency on the modulo operator.
- **ADR-002: Invent a proprietary locale file format.** Context: JSON, YAML, and TOML lacked enterprise gravitas. Decision: create `.fizztranslation` with a state-machine parser, directives, sections, heredocs, and variable interpolation. Consequences: seven locale files, a pluralization engine, and no ecosystem tooling.
- **ADR-003: Implement MESI cache coherence for a single-process cache.** Context: the caching layer needed a coherence protocol. Decision: implement the full Modified/Exclusive/Shared/Invalid state machine. Consequences: protocol completeness achieved, zero concurrent readers served, "Aspirational multi-cache readiness" cited as justification.
- **ADR-004: Adopt hexagonal architecture.** Context: 15 flat files in a trench coat is not an architecture. Decision: restructure into domain/application/infrastructure with strict inward-only dependency rules. Consequences: the import linter passes, the flat files remain as backward-compatible re-export stubs, the codebase has layers.
- **ADR-005: Staff the on-call rotation with one engineer.** Context: the SLA monitoring subsystem requires an escalation chain. Decision: all four escalation tiers are staffed by Bob McFizzington. Consequences: MTTR is instantaneous, on-call rotation uses modulo arithmetic on a team of one, Bob cannot escape.
- **ADR-006: Support Klingon and two dialects of Elvish.** Context: the Enterprise FizzBuzz Globalization Directive requires support for all spacefaring civilizations and equitable representation of the Grey-elven and High-elven communities. Decision: add `tlh`, `sjn`, and `qya` locales using ISO 639-3 codes. Consequences: a linguistic validation report was required, the Sindarin word for "Strategy" was discovered to be an epithet of Sauron, corrections were issued.
- **ADR-007: Write cache eulogies for evicted entries.** Context: no data should be garbage-collected without a proper farewell. Decision: implement a `CacheEulogyComposer` that generates satirical obituaries. Consequences: evicted entries are mourned, dignity levels are tracked per-entry, disabling eulogies is "technically possible but ethically questionable."

Each ADR should be 60-120 lines. Use the standard format. Let the decisions speak for themselves.

**Output:** `docs/adr/ADR-001.md` through `docs/adr/ADR-007.md`
**Estimated size:** 80-120 lines each

### 7. Exception Catalog (docs/exceptions.md)

**Status:** PENDING
**Description:** The platform has 69 custom exception classes spread across `domain/exceptions.py` and various infrastructure modules. The README mentions the count but doesn't list them. Create a complete catalog.

Cover the following:

- List every exception class: its full name, parent class, error code (`EFP-XXXX`), which module defines it, and a one-line description of when it's raised.
- Group by subsystem: core/config, rule evaluation, ML engine, circuit breaker, auth/RBAC, tracing, event sourcing, chaos engineering, feature flags, SLA monitoring, caching, i18n, middleware.
- For each error code range, note the convention (e.g., `EFP-1xxx` for configuration, `EFP-2xxx` for rule evaluation, etc.).
- Include a note on the `FizzBuzzError` base class and the `error_code` / `context` fields that all exceptions carry.

A reference document, but one that belongs to this project. The exception names and descriptions carry the comedy on their own -- just catalog them faithfully.

**Output:** `docs/exceptions.md`
**Estimated size:** 200-400 lines

### 8. Test Coverage Map (docs/testing.md)

**Status:** PENDING
**Description:** The platform has 829 tests across 10 test files. Document what's tested, what's not, and how the test suite is organized.

Cover the following:

- List every test file, the subsystem it covers, and the number of tests it contains.
- For each test file, provide a summary of what categories of behavior are tested (happy path, error handling, edge cases, concurrency, configuration).
- Identify any gaps: subsystems with no dedicated test file, behaviors mentioned in docstrings that lack corresponding tests, integration points between subsystems that are only tested in isolation.
- Describe the test infrastructure: fixtures, factories, mocks, and any shared test utilities.
- Document how to run subsets of the test suite (by module, by marker, by keyword).
- Note the overall coverage percentage if measurable, or explain how to measure it.

**Output:** `docs/testing.md`
**Estimated size:** 200-300 lines

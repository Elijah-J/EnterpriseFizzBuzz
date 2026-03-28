# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests (~20,100 tests, ~5min)
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_cache.py

# Run a specific test
python -m pytest tests/test_cache.py::TestCacheMESI::test_valid_transition -v

# Run contract tests (interface conformance)
python -m pytest tests/contracts/

# Run architecture compliance tests (Dependency Rule enforcement)
python -m pytest tests/test_architecture.py

# Run the FizzBuzz engine
python -m enterprise_fizzbuzz --range 1 100 --format plain
```

No linting tools are configured.

## Architecture

Clean Architecture with three layers. The **Dependency Rule** is enforced by AST-based tests in `test_architecture.py`: dependencies point inward only (infrastructure → application → domain).

- **Domain** (`domain/`): Models, enums, exceptions (600+ custom exception classes), and abstract interfaces (`IRule`, `IRuleEngine`, `IMiddleware`, `IFormatter`, `IEventBus`). Zero outward dependencies.
- **Application** (`application/`): `FizzBuzzServiceBuilder` (fluent builder), rule factories (Standard/Configurable/Caching), and hexagonal ports (`StrategyPort`, `AbstractUnitOfWork`, `AbstractRepository`).
- **Infrastructure** (`infrastructure/`): 140 modules implementing enterprise subsystems — rule engines, formatters, middleware pipeline, observers, DI container, cache (MESI coherence), service mesh, blockchain, auth (RBAC + HMAC tokens), i18n (7 locales inc. Klingon/Sindarin/Quenya), event sourcing/CQRS, chaos engineering, feature flags, SLA monitoring, metrics, webhooks, hot-reload (Raft consensus), rate limiting, compliance (SOX/GDPR/HIPAA), three persistence backends (in-memory, SQLite, filesystem), bytecode VM, query optimizer, digital twin, archaeological recovery, ML engine, genetic algorithm, graph database, secrets vault, OS kernel, cross-compiler, FizzLang DSL, Paxos consensus, quantum simulator, federated learning, dependent type system, FizzKube container orchestrator, package manager, FizzSQL query engine, debug adapter protocol, IP office, distributed locks, CDC, billing/monetization, JIT compiler, capability security, OpenTelemetry tracing, write-ahead intent log, CRDTs, memory allocator, columnar storage, MapReduce, model checker, reverse proxy, ray tracer, protein folding, TCP/IP stack, audio synthesizer, virtual file system, version control, ELF binary generator, database replication, Z notation specs, process migration, flame graph generator, theorem prover, GPU shader compiler, smart contracts, DNS server, spreadsheet engine, regex engine, spatial database, clock sync (NTP/PTP), CPU pipeline simulator, x86 bootloader, video codec, TeX typesetter, garbage collector, microkernel IPC, operator succession planning, operator performance review, organizational hierarchy, Linux namespace isolation, cgroup resource accounting, OCI container runtime, copy-on-write union filesystem, OCI image registry, container network interface, container daemon, official container image catalog, container-native deployment pipeline, multi-container application orchestration, CRI-integrated orchestrator upgrade, container-native chaos engineering, container observability and diagnostics, SMTP/IMAP email server, continuous integration pipeline engine, SSH protocol server, windowing system and display server, block storage and volume manager, content delivery network and edge cache, OAuth 2.0/OIDC authorization server, AMQP-compatible message broker, interactive computational notebook, disaster recovery and backup system, application performance profiler.

### Wiring

`__main__.py` is the composition root — it parses 732+ CLI flags, builds `ConfigurationManager` (singleton), and manually wires all subsystems via `FizzBuzzServiceBuilder`. A separate IoC container (`container.py`) exists with auto-wiring and Kahn's cycle detection but isn't used by the main entry point.

### Configuration precedence (highest wins)

1. CLI flags
2. Environment variables (`EFP_*` prefix)
3. `config.yaml`

### Backward compatibility

Root-level `.py` files are re-export stubs (e.g., `cache.py` re-exports from `enterprise_fizzbuzz.infrastructure.cache`). Don't delete them.

## Tests

- All tests use `pytest` with per-file fixtures (no `conftest.py`)
- Singletons are reset between tests via `_SingletonMeta.reset()` fixture
- **Contract tests** (`tests/contracts/`) verify all implementations honor interface promises (Liskov Substitution)
- Locale test data lives in `locales/*.fizztranslation` (7 languages including Klingon, Sindarin, Quenya)

## Current Status (as of 2026-03-27)

| Metric | Value |
|--------|-------|
| Lines of Code | ~518,000+ |
| Python Files | 851 |
| Test Count | ~20,300+ |
| Custom Exceptions | 1,446+ |
| Infrastructure Modules | 148 |
| CLI Flags | 758+ |
| Commits | 318+ |
| Brainstorm Rounds Completed | 19 in progress (Round 18 COMPLETE — all 12 of 12 done, Round 20 IN PROGRESS — 5 of 6 done) |

### Autonomous Orchestration

Development follows a multi-agent orchestration protocol (see `roadmaps/BRAINSTORM_REPORT.md` for backlog). Each feature cycle:

1. **Brainstorm agent** — maintains a backlog of 5+ feature ideas in `BRAINSTORM_REPORT.md`
2. **Research agent** (optional) — web research for domain knowledge before planning
3. **Planning agent** — writes `PLAN.md` to disk
4. **Implementation agent** — implements the plan (code, tests, config, CLI flags)
5. **Docs/commit agent** — updates all docs (README, FEATURES.md, CLI_REFERENCE.md, SUBSYSTEMS.md, FAQ.md, etc.) and commits

Each step uses a **separate agent**. Steps are never combined. The cycle repeats indefinitely until explicitly stopped.

### Roadmaps

- `roadmaps/BRAINSTORM_REPORT.md` — feature backlog (current: Round 19, Round 20 IN PROGRESS -- 1 of 6 done)
- `roadmaps/QA_E2E_ROADMAP.md` — QA items (completed)
- `roadmaps/FORMAT_ROADMAP.md` — formatting audit (completed)
- `roadmaps/CURATION_AUDIT.md` — module curation audit (completed)

## Output notes

- **Line endings**: All CLI output uses the platform-native line endings (CRLF on Windows, LF on Unix). When piping output through Unix tools on Windows (e.g., WSL `cat -A`), expect `^M` artifacts. This is standard Python `print()` behavior and not a bug.

## Tone

This is a production-grade enterprise platform. Every subsystem is technically faithful — the MESI cache coherence matches the real protocol, the neural network trains from scratch, the blockchain actually mines blocks. Maintain this standard: implementations must be genuinely correct and follow established patterns in the codebase.

**Deadpan. No exceptions.** All code, comments, docstrings, and documentation must take themselves 100% seriously. Never acknowledge the joke. Never wink at the reader. No "satirical", "over-engineered", "absurd", "pointless", "the joke", "of course", or "because why not". Justify every subsystem sincerely. The comedy comes from the contrast between engineering rigor and problem triviality — that contrast only works if the implementation never flinches. Think mockumentary: the characters don't know they're in a comedy.

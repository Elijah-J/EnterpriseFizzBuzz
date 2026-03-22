# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests (~1,142 tests, ~0.4s)
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

- **Domain** (`domain/`): Models, enums, exceptions (151+ custom exception classes), and abstract interfaces (`IRule`, `IRuleEngine`, `IMiddleware`, `IFormatter`, `IEventBus`). Zero outward dependencies.
- **Application** (`application/`): `FizzBuzzServiceBuilder` (fluent builder), rule factories (Standard/Configurable/Caching), and hexagonal ports (`StrategyPort`, `AbstractUnitOfWork`, `AbstractRepository`).
- **Infrastructure** (`infrastructure/`): All implementations — rule engines, formatters, middleware pipeline, observers, DI container, cache (MESI coherence), service mesh, blockchain, auth (RBAC + HMAC tokens), i18n, event sourcing/CQRS, chaos engineering, feature flags, SLA monitoring, metrics, webhooks, hot-reload (Raft consensus), rate limiting, compliance (SOX/GDPR/HIPAA), and three persistence backends (in-memory, SQLite, filesystem).

### Wiring

`__main__.py` is the composition root — it parses 63+ CLI flags, builds `ConfigurationManager` (singleton), and manually wires all subsystems via `FizzBuzzServiceBuilder`. A separate IoC container (`container.py`) exists with auto-wiring and Kahn's cycle detection but isn't used by the main entry point.

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

## Output notes

- **Line endings**: All CLI output uses the platform-native line endings (CRLF on Windows, LF on Unix). When piping output through Unix tools on Windows (e.g., WSL `cat -A`), expect `^M` artifacts. This is standard Python `print()` behavior and not a bug.

## Project nature

This is a satirical over-engineering showcase. Every subsystem is intentionally absurd but technically faithful — the MESI cache coherence matches the real protocol, the neural network trains from scratch, the blockchain actually mines blocks. Maintain this standard: implementations should be genuinely correct, applied to a comically trivial problem.

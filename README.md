# EnterpriseFizzBuzz

### A Production-Grade, Enterprise-Ready FizzBuzz Evaluation Engine

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

**3,000+ lines** across **14 files** with **57 unit tests**, because this is an enterprise and we have standards.

## Architecture

```
EnterpriseFizzBuzz/
├── main.py                  # CLI entry point with 10 flags
├── config.yaml              # YAML-based configuration with 7 sections
├── config.py                # Singleton configuration manager with env var overrides
├── models.py                # Dataclasses, enums, and domain models
├── exceptions.py            # Custom exception hierarchy (11 exception classes)
├── interfaces.py            # Abstract base classes for everything
├── rules_engine.py          # Three evaluation strategies
├── factory.py               # Abstract Factory + Caching Decorator
├── observers.py             # Thread-safe event bus with statistics tracking
├── middleware.py             # Composable middleware pipeline
├── formatters.py            # Four output formatters
├── plugins.py               # Plugin registry with auto-registration
├── fizzbuzz_service.py      # Service orchestration with Builder pattern
└── tests/
    └── test_fizzbuzz.py     # 57 comprehensive tests
```

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| Abstract Factory | `factory.py` | Creating rules is *complex* |
| Strategy | `rules_engine.py` | Three interchangeable evaluation algorithms |
| Chain of Responsibility | `rules_engine.py` | Because one Strategy wasn't enough |
| Observer | `observers.py` | FizzBuzz events must be monitored in real-time |
| Middleware Pipeline | `middleware.py` | Cross-cutting concerns for modulo operations |
| Singleton | `config.py` | Only one configuration shall rule them all |
| Builder | `fizzbuzz_service.py` | Fluent API for assembling the FizzBuzz service |
| Decorator | `factory.py` | Caching layer around rule factories |
| Plugin System | `plugins.py` | Third-party FizzBuzz rule extensions |
| Dependency Injection | Everywhere | Constructor injection, because globals are evil |

## Features

- **Multiple Evaluation Strategies** - Standard iteration, Chain of Responsibility, or Parallel Async
- **Four Output Formats** - Plain Text, JSON, XML, CSV
- **YAML Configuration** - Externalized, validated, with environment variable overrides
- **Middleware Pipeline** - Validation, timing (nanosecond precision), and logging
- **Event-Driven Architecture** - Real-time FizzBuzz detection events with statistics
- **Plugin System** - Extend with custom divisibility rules via decorators
- **Async/Await** - Run FizzBuzz asynchronously, because blocking is for amateurs
- **Custom Exception Hierarchy** - 11 exception classes for every conceivable FizzBuzz failure mode
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

# CSV output, no frills
python main.py --range 1 100 --format csv --no-banner --no-summary
```

## CLI Options

```
--range START END     Numeric range to evaluate (default: 1-100)
--format FORMAT       Output format: plain, json, xml, csv
--strategy STRATEGY   Evaluation strategy: standard, chain_of_responsibility, parallel_async
--config PATH         Path to YAML configuration file
--verbose, -v         Enable verbose event logging
--debug               Enable debug-level logging
--async               Use asynchronous evaluation engine
--no-banner           Suppress the startup banner
--no-summary          Suppress the session summary
--metadata            Include metadata in output (JSON only)
```

## Environment Variables

All configuration can be overridden via environment variables prefixed with `EFP_`:

```bash
EFP_RANGE_START=1
EFP_RANGE_END=100
EFP_OUTPUT_FORMAT=json
EFP_EVALUATION_STRATEGY=parallel_async
EFP_LOG_LEVEL=DEBUG
```

## Testing

```bash
# Run all 57 tests
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
A: It has 57 tests, a plugin system, and nanosecond timing. You tell me.

**Q: Why not use microservices?**
A: That's the v2.0 roadmap. Each divisibility check will be its own containerized service behind an API gateway.

**Q: Can I use this for my interview?**
A: Only if you want to assert dominance.

**Q: What's the performance like?**
A: The platform includes built-in nanosecond-precision timing middleware, so you'll know exactly how long each modulo operation takes. We're talking *enterprise-grade observability*.

**Q: Why does the XML formatter docstring reference SOAP services circa 2003?**
A: Legacy compatibility is not a joke.

## License

MIT - Use responsibly. Or irresponsibly. We're not your manager.

---

*Built with an mass contempt for simplicity.*

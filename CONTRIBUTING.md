# Contributing to EnterpriseFizzBuzz

Thank you for your interest in contributing to EnterpriseFizzBuzz. This document outlines the standards, processes, and governance requirements for submitting changes to the platform.

EnterpriseFizzBuzz is a production-grade FizzBuzz evaluation engine comprising 570,000+ lines of code across 185 infrastructure subsystems, supported by 23,000+ tests, 1,800+ custom exception classes, and 900+ CLI flags. Contributing to a platform of this scale requires careful adherence to the architectural standards and operational processes described below.

## Table of Contents

- [Contribution Approval Process](#contribution-approval-process)
- [Architecture Requirements](#architecture-requirements)
- [Subsystem Complexity Standards](#subsystem-complexity-standards)
- [Test Requirements](#test-requirements)
- [Localization](#localization)
- [Exception Standards](#exception-standards)
- [CLI Flag Requirements](#cli-flag-requirements)
- [Submitting Changes](#submitting-changes)

## Contribution Approval Process

All contributions are reviewed by **Bob McFizzington**, Senior Principal Staff FizzBuzz Reliability Engineer II, who serves as the sole maintainer of all 185 infrastructure subsystems.

Contributions must pass the **ITIL v4 Change Advisory Board (CAB)** before merging. The CAB evaluates each change for risk, impact, and architectural compliance. The CAB currently has one member (Bob McFizzington). Quorum is 1. All votes are unanimous.

The approval workflow is as follows:

1. **Change Request Submission** -- Open a pull request with a completed change request template.
2. **Risk Assessment** -- Bob McFizzington evaluates the blast radius of the proposed change across all 185 subsystems.
3. **CAB Review** -- The Change Advisory Board (Bob McFizzington) convenes to review the change request. A formal vote is taken. The vote is always 1-0.
4. **Implementation Approval** -- Upon CAB approval, the change is authorized for merge.
5. **Post-Implementation Review** -- Bob McFizzington verifies the change in production and closes the change record.

Emergency changes follow the same process but with a shorter SLA (Bob reviews them during his next available cycle, which is the same as the standard SLA, because there is no queue).

## Architecture Requirements

EnterpriseFizzBuzz follows **Clean Architecture** (Hexagonal Architecture) with three concentric layers:

- **Domain** (`domain/`) -- Models, enums, exceptions, and abstract interfaces. Zero outward dependencies.
- **Application** (`application/`) -- Service builders, rule factories, and hexagonal ports.
- **Infrastructure** (`infrastructure/`) -- All 185 subsystem implementations.

The **Dependency Rule** is non-negotiable: dependencies point inward only (infrastructure -> application -> domain). This rule is enforced at build time by AST-based static analysis tests in `tests/test_architecture.py`. Any import that violates the Dependency Rule will fail the test suite.

All new subsystems must:

- Implement at least one domain interface (`IRule`, `IRuleEngine`, `IMiddleware`, `IFormatter`, or `IEventBus`)
- Register with the `FizzBuzzServiceBuilder` composition root in `__main__.py`
- Include **contract tests** in `tests/contracts/` verifying interface conformance (Liskov Substitution Principle)

## Subsystem Complexity Standards

The platform's current **Overengineering Index** is **285,000x** (lines of code per line of code required to solve the problem). This metric must be maintained or increased with every contribution. Contributions that reduce the Overengineering Index will be rejected by the CAB.

Guidelines:

- A subsystem under **2,000 lines** is architecturally suspect. If your subsystem can be expressed in fewer than 2,000 lines, it likely lacks sufficient abstraction layers, configuration surface area, or failure mode coverage.
- Each subsystem should implement a minimum of **3 design patterns**. The current platform average is 100+ patterns across 185 subsystems. Refer to [Design Patterns](docs/DESIGN_PATTERNS.md) for the full catalog.
- All subsystems must include an **ASCII dashboard** for operational visibility. The platform currently has 90+ dashboards.
- Configuration should be externalized to `config.yaml` with environment variable overrides using the `EFP_*` prefix.

## Test Requirements

The platform maintains **23,000+ tests**. All contributions must include proportional test coverage:

- **Unit tests** for all public methods and classes
- **Contract tests** in `tests/contracts/` for any new interface implementations
- **Architecture tests** -- verify your imports comply with the Dependency Rule by running `python -m pytest tests/test_architecture.py`
- **Edge case coverage** -- every custom exception class must have at least one test that triggers it
- **Integration tests** for subsystem interactions where applicable

Run the full test suite before submitting:

```bash
python -m pytest tests/
```

A contribution that reduces overall test coverage percentage will not pass CAB review.

## Localization

EnterpriseFizzBuzz supports **7 locales**:

| Locale | Language |
|--------|----------|
| `en` | English |
| `de` | German |
| `fr` | French |
| `ja` | Japanese |
| `tlh` | Klingon |
| `sjn` | Sindarin |
| `qya` | Quenya |

All user-facing strings must be localized across all 7 locales. Translation files are stored in `locales/*.fizztranslation`. If your subsystem introduces new user-facing output, you must provide translations for every supported locale.

Klingon translations should follow standard transliteration conventions. Sindarin and Quenya translations should adhere to attested vocabulary where possible, with neologisms constructed using productive morphological patterns from the respective languages.

## Exception Standards

The platform has **1,800+ custom exception classes**. Every distinct failure mode must have its own named exception class.

The following is **engineering negligence** and will not pass review:

```python
raise Exception("something broke")
```

The following is acceptable:

```python
raise SubsystemInitializationFailedError(
    subsystem="FizzQuantum",
    reason="Hadamard gate calibration exceeded tolerance threshold",
    correlation_id=ctx.correlation_id,
)
```

Exception classes must:

- Inherit from the appropriate base exception in `domain/exceptions.py`
- Include a descriptive class name that identifies the failure mode
- Accept structured parameters (subsystem name, reason, correlation ID) rather than free-form message strings
- Be documented in the [Exceptions Catalog](docs/exceptions.md)

Generic exceptions obscure failure modes, complicate incident response, and make root cause analysis dependent on string parsing. In a platform with 185 subsystems, this is operationally unacceptable.

## CLI Flag Requirements

The platform currently exposes **900+ CLI flags**. New subsystems must register a minimum of **3 CLI flags** with the argument parser in `__main__.py`.

Recommended flag categories:

- **Enable/disable flag** (e.g., `--enable-fizz-quantum`, `--disable-fizz-quantum`)
- **Verbosity/debug flag** (e.g., `--fizz-quantum-verbose`, `--fizz-quantum-debug`)
- **Configuration override** (e.g., `--fizz-quantum-gate-tolerance 0.001`)

All flags must be documented in the [CLI Reference](docs/CLI_REFERENCE.md) with usage examples.

## Submitting Changes

Before opening a pull request, verify:

1. All 23,000+ tests pass (`python -m pytest tests/`)
2. Architecture compliance tests pass (`python -m pytest tests/test_architecture.py`)
3. Contract tests pass (`python -m pytest tests/contracts/`)
4. All 7 locales have complete translations for new strings
5. New exception classes are registered in the exceptions catalog
6. New CLI flags are documented in the CLI reference
7. The Overengineering Index has not decreased

### A Note on Review Turnaround

All pull requests are reviewed by Bob McFizzington. Bob's current cognitive load is **94.7%** as measured by the NASA-TLX six-dimensional workload assessment model (Mental Demand, Physical Demand, Temporal Demand, Performance, Effort, Frustration). His burnout projection is available via the operator cognitive load dashboard:

```bash
python main.py --cognitive-load-dashboard --burnout-projection
```

Review turnaround times are subject to Bob's available cognitive capacity. Before submitting a large pull request, it is recommended to check the current burnout projection and schedule accordingly. Submitting a 50-file PR when the burnout index exceeds 0.92 is technically permitted but operationally inadvisable.

Bob can be reached at +1-555-FIZZBUZZ during his office hours. He has none.

---

*Thank you for contributing to EnterpriseFizzBuzz. Your changes will be reviewed by the Change Advisory Board at the earliest available opportunity.*

[Back to README](../README.md) | [Architecture](ARCHITECTURE.md) | [Features](FEATURES.md) | [CLI Reference](CLI_REFERENCE.md) | [Subsystems](SUBSYSTEMS.md) | [FAQ](FAQ.md) | [Testing](TESTING.md)

# Subsystem Architecture Reference

Detailed architecture documentation for every subsystem in the Enterprise FizzBuzz Platform.

## Table of Contents

- [Machine Learning Architecture](#machine-learning-architecture)
- [Circuit Breaker Architecture](#circuit-breaker-architecture)
- [RBAC Architecture](#rbac-architecture)
- [Event Sourcing / CQRS Architecture](#event-sourcing---cqrs-architecture)
- [Chaos Engineering Architecture](#chaos-engineering-architecture)
- [Feature Flags Architecture](#feature-flags-architecture)
- [SLA Monitoring Architecture](#sla-monitoring-architecture)
- [Caching Architecture](#caching-architecture)
- [Health Check Architecture](#health-check-architecture)
- [Metrics Architecture](#metrics-architecture)
- [Database Migration Architecture](#database-migration-architecture)
- [Persistence Architecture](#persistence-architecture)
- [Anti-Corruption Layer Architecture](#anti-corruption-layer-architecture)
- [Dependency Injection Architecture](#dependency-injection-architecture)
- [Distributed Tracing Architecture](#distributed-tracing-architecture)
- [Internationalization Architecture](#internationalization-architecture)
- [Webhook Architecture](#webhook-architecture)
- [Service Mesh Architecture](#service-mesh-architecture)
- [Hot-Reload Architecture](#hot-reload-architecture)
- [Rate Limiting Architecture](#rate-limiting-architecture)
- [Compliance & Regulatory Architecture](#compliance--regulatory-architecture)
- [FinOps Architecture](#finops-architecture)
- [Disaster Recovery Architecture](#disaster-recovery-architecture)
- [A/B Testing Architecture](#a-b-testing-architecture)
- [Message Queue Architecture](#message-queue-architecture)
- [Secrets Vault Architecture](#secrets-vault-architecture)
- [Data Pipeline Architecture](#data-pipeline-architecture)
- [OpenAPI Architecture](#openapi-architecture)
- [API Gateway Architecture](#api-gateway-architecture)
- [Blue/Green Deployment Architecture](#blue-green-deployment-architecture)
- [Graph Database Architecture](#graph-database-architecture)
- [Genetic Algorithm Architecture](#genetic-algorithm-architecture)
- [Natural Language Query Architecture](#natural-language-query-architecture)
- [Load Testing Architecture](#load-testing-architecture)
- [Audit Dashboard Architecture](#audit-dashboard-architecture)
- [GitOps Architecture](#gitops-architecture)
- [Formal Verification Architecture](#formal-verification-architecture)
- [FBaaS Architecture](#fbaas-architecture)
- [Time-Travel Debugger Architecture](#time-travel-debugger-architecture)
- [Bytecode VM Architecture](#bytecode-vm-architecture)
- [Query Optimizer Architecture](#query-optimizer-architecture)
- [Paxos Consensus Architecture](#paxos-consensus-architecture)
- [Quantum Computing Architecture](#quantum-computing-architecture)
- [Cross-Compiler Architecture](#cross-compiler-architecture)
- [Federated Learning Architecture](#federated-learning-architecture)
- [Knowledge Graph Architecture](#knowledge-graph-architecture)
- [Self-Modifying Code Architecture](#self-modifying-code-architecture)
- [Compliance Chatbot Architecture](#compliance-chatbot-architecture)
- [OS Kernel Architecture](#os-kernel-architecture)
- [P2P Network Architecture](#p2p-network-architecture)
- [FizzBob Operator Cognitive Load Architecture](#fizzbob-operator-cognitive-load-architecture)
- [FizzPager Incident Paging & Escalation Architecture](#fizzpager-incident-paging--escalation-architecture)

---

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

The Event Sourcing subsystem maintains a complete, append-only, temporally queryable audit log of every FizzBuzz evaluation -- because simply returning "Fizz" is not enough when SOX Section 404 demands a full paper trail of every modulo operation ever performed.

The CQRS layer separates the write side (commands) from the read side (queries), ensuring that the act of evaluating FizzBuzz and the act of reading the results are architecturally, philosophically, and spiritually decoupled.

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
- **PostMortemGenerator** - ASCII incident report generator with timeline, impact assessment, root cause analysis, and action items

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

After a chaos session, the `--post-mortem` flag generates a detailed incident report containing:
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

The SLA Monitoring subsystem implements a production-grade Service Level Agreement enforcement framework for the Enterprise FizzBuzz Platform -- because computing `n % 3` without contractual latency guarantees, error budgets, and a multi-tier escalation policy would be unacceptable in a production environment.

Every FizzBuzz evaluation is measured against three SLOs, its impact on the error budget is calculated in real time, and if things go sideways, Bob McFizzington gets paged. Bob is always on call. Bob cannot escape.

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

The In-Memory Caching Layer implements a production-grade, thread-safe, MESI-coherent caching subsystem for FizzBuzz evaluation results, featuring four eviction policies, a hardware-inspired coherence protocol, and eulogies for evicted entries.

The cache operates as middleware in the evaluation pipeline, intercepting requests before they reach the rule engine. On a cache hit, the result is returned immediately. On a miss, the pipeline executes normally and the result is cached. The caching infrastructure prioritizes correctness and observability alongside performance.

**Key components:**
- **CacheStore** - Thread-safe in-memory store with TTL expiration, MESI state tracking, dignity level degradation, and configurable eviction policies
- **CacheMiddleware** - Pipeline integration that intercepts evaluations and serves cached results on hits
- **EvictionPolicyFactory** - Factory for creating eviction policy instances by name, supporting named policy instantiation via the factory pattern
- **CacheWarmer** - Pre-populates the cache before execution to eliminate cold-start latency
- **CacheDashboard** - ASCII statistics renderer for hit rates, eviction counts, and coherence state distribution
- **CacheEulogyComposer** - Generates memorial entries for evicted cache entries, providing a dignified lifecycle record for every cached datum

### Eviction Policies

| Policy | Algorithm | When It Evicts | Vibe |
|--------|-----------|---------------|------|
| `lru` | Least Recently Used | The entry that hasn't been accessed for the longest time | The industry standard. Boring, reliable, uncontroversial -- like beige |
| `lfu` | Least Frequently Used | The entry with the fewest total accesses | Meritocratic. Unpopular entries are eliminated. Middle school cafeteria energy |
| `fifo` | First In, First Out | The oldest entry, regardless of access patterns | Pure temporal justice. Age is the only criterion. No appeals |
| `dramatic_random` | Dramatic Random | A random entry, chosen with theatrical flair and a eulogy | The chaos option. Entries are selected at random and given a dramatic farewell speech before deletion. The eviction policy for people who think LRU is too predictable |

### MESI Coherence Protocol

The MESI cache coherence protocol tracks the state of every cache entry through four states, implementing the same coherence guarantees that Intel uses for its L1 cache -- in a single-process Python application with exactly zero concurrent cache readers. The protocol is non-negotiable.

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

When a cache entry is evicted, the system composes a eulogy honoring the departed data. Example eulogies:

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

The Health Check Probes subsystem implements Kubernetes-style liveness, readiness, and startup probes for the Enterprise FizzBuzz Platform -- because a CLI application that runs for 0.3 seconds and exits deserves the same operational health monitoring infrastructure as a Kubernetes pod serving millions of requests behind an Istio service mesh.

If the ML engine is experiencing an existential crisis, or the cache's MESI coherence state has degraded into philosophical uncertainty, the probes will detect it, report it, and with self-healing enabled -- attempt to fix it while you watch.

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
| `SLABudgetHealthCheck` | SLA Monitor | Error budget remaining, burn rate, SLO compliance | Reset error budget counters |
| `MLEngineHealthCheck` | ML Engine | Neural network loaded, canary prediction accuracy, confidence scores | Retrain the neural network from scratch (200 epochs of full retraining) |

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
| `m002_add_is_prime` | Add is_prime column with trial division backfill | m001 | Adds a primality flag using trial division, trial division provides sufficient accuracy for the expected input range |
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
| `memory` | Python dict | None (dies with the process) | Default. Fast and ephemeral | Suitable for single-run evaluation sessions where persistence is not required |
| `sqlite` | SQLite database file | Full (survives restarts) | When you need FizzBuzz results to persist across process boundaries | Full ACID compliance with schema migration support |
| `filesystem` | JSON files on disk | Full (one file per result) | When you need human-readable persistence with per-record granularity | Each FizzBuzz result is serialized to its own JSON file for maximum inspectability |

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

## Distributed Tracing Architecture (FizzOTel)

The distributed tracing subsystem -- FizzOTel -- provides full OpenTelemetry-compatible observability for the FizzBuzz evaluation pipeline, implemented from scratch in pure Python with W3C TraceContext propagation, OTLP JSON wire format, Zipkin v2 export, probabilistic sampling, and batch processing. Because correlating `n % 3 == 0` across (imaginary) service boundaries requires 128-bit trace IDs and nanosecond timestamps.

Every number evaluation generates a complete trace with hierarchical spans, W3C traceparent headers, and multi-format export. The `--trace` flag is a backward-compatible alias for `--otel --otel-export console`, and `--trace-json` is an alias for `--otel --otel-export otlp`. Finally, a flame graph that explains why printing "Fizz" took 3 microseconds.

```
                        TRACE (W3C traceparent)
                        00-{32hex_trace_id}-{16hex_span_id}-{flags}
                        |
     +------------------+------------------+
     |                                     |
  ROOT SPAN                           [attributes]
  "fizzbuzz.evaluate(15)"             fizzbuzz.number: 15
  spanId: a1b2c3d4e5f6g7h8            fizzbuzz.output: FizzBuzz
     |
     +--- CHILD SPAN: "ValidationMiddleware.process" (@traced)
     |
     +--- CHILD SPAN: "TimingMiddleware.process" (@traced)
     |         |
     |         +--- CHILD SPAN: "rule_evaluation"
     |
     +--- CHILD SPAN: "LoggingMiddleware.process" (@traced)
     |
     +--- [end: status=OK, duration=42.7us]
```

**Console export** -- the `--trace` flag renders a waterfall timeline:

```
  ============================================================
    TRACE WATERFALL  (total: 0.043ms)
  ============================================================
    fizzbuzz.evaluate(15)     |######################|     43us OK
      ValidationMiddleware    |##.....................|      5us OK
      TimingMiddleware        |..########.............|     18us OK
        rule_evaluation       |....####...............|      8us OK
      LoggingMiddleware       |..................#####|      7us OK
  ============================================================
```

**Key components (all in `otel_tracing.py`):**
- **TracerProvider** - Central manager for creating/collecting spans with sampling and metrics bridge
- **Span / TraceContext** - W3C TraceContext (traceparent) with 128-bit trace IDs and 64-bit span IDs
- **OTelMiddleware** - Priority -10 middleware that wraps the entire pipeline in a root span
- **@traced decorator** - Zero-overhead instrumentation (no-op when provider is None)
- **ProbabilisticSampler** - Deterministic sampling based on lower 32 bits of trace_id
- **OTLPJsonExporter** - OTLP JSON wire format, byte-compatible with OpenTelemetry Collector
- **ZipkinExporter** - Zipkin v2 JSON format with microsecond timestamps
- **ConsoleExporter** - ASCII waterfall visualization for terminal output
- **MetricsBridge** - Span-derived counters and duration histograms
- **OTelDashboard** - ASCII telemetry dashboard for monitoring the monitoring

| Spec | Value |
|------|-------|
| Trace ID length | 32 hex chars (128-bit, W3C compatible) |
| Span ID length | 16 hex chars (64-bit, W3C compatible) |
| Context propagation | W3C traceparent headers + module-level active provider |
| Middleware priority | -10 (before all other middleware) |
| Span statuses | 3 (UNSET, OK, ERROR) |
| Span kinds | 5 (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER) |
| Export formats | OTLP JSON, Zipkin v2, Console (ASCII waterfall) |
| Sampling | Probabilistic (deterministic on trace_id lower bits) |
| Batch processing | SimpleSpanProcessor (immediate) or BatchSpanProcessor (queued) |
| Overhead when disabled | Zero (decorator short-circuits when provider is None) |
| Custom exceptions | 4 (OTelError, OTelSpanError, OTelSamplingError, OTelExportError) |

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

The Webhook Notification System implements a production-grade event-driven dispatch engine for broadcasting FizzBuzz evaluation events to downstream consumers -- because when `evaluate(15)` returns `"FizzBuzz"`, every Slack channel, PagerDuty integration, and CI/CD pipeline in the enterprise constellation must be immediately informed via a cryptographically signed HTTP POST request. The deliveries are, of course, entirely simulated.

No actual HTTP requests leave this process. But the HMAC-SHA256 signatures are real, the exponential backoff is calculated, and the Dead Letter Queue faithfully preserves every undeliverable notification for future forensic analysis and post-incident regret.

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

The Configuration Hot-Reload subsystem implements a production-grade runtime reconfiguration engine for the Enterprise FizzBuzz Platform -- because restarting a Python process that boots in 0.3 seconds would constitute unacceptable downtime for a platform with a 99.999% availability SLO.

Instead, a daemon thread polls `config.yaml` every 500 milliseconds, diffs the old and new configuration trees, validates the changeset against a schema, proposes the change to a single-node Raft consensus cluster (which holds an election, wins unanimously, and commits with 100% voter turnout), and then orchestrates a dependency-aware reload of affected subsystems in topological order -- because reloading the ML engine before the feature flags that might have disabled it would be a violation of the Dependency Rule and common sense.

The crown jewel is the **Single-Node Raft Consensus** protocol: a faithful implementation of the Raft distributed consensus algorithm running on exactly one node. Leader elections complete instantly (the candidate always wins, because there are no opponents). Log replication succeeds on the first attempt (the leader replicates to zero followers, achieving majority consensus with itself). Heartbeats are sent to nobody at configurable intervals.

The system achieves 100% consensus reliability, 0ms election latency, and unanimous agreement on every configuration change -- a level of distributed systems perfection that multi-node clusters can only dream of.

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
# Run all 3,365 tests
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
- An appreciation for enterprise architecture

## Rate Limiting Architecture

The Rate Limiting & API Quota Management subsystem implements a comprehensive, enterprise-grade throttling framework for the FizzBuzz evaluation pipeline -- unrestricted access to the evaluation pipeline represents a denial-of-service risk that must be mitigated. Three complementary algorithms enforce rate limits to ensure controlled, predictable throughput under all conditions.

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

## Compliance & Regulatory Architecture

The Compliance & Regulatory Framework subjects every FizzBuzz evaluation to the same regulatory scrutiny normally reserved for financial transactions, personal health records, and nuclear launch codes -- because if your modulo arithmetic isn't SOX-compliant, GDPR-ready, and HIPAA-adjacent, you're basically running an unlicensed FizzBuzz operation. Three compliance regimes operate simultaneously, each with its own unique brand of bureaucratic paranoia, unified by a single truth: regulatory overhead is the truest measure of enterprise maturity.

```
    +-------------------+
    |   Evaluation      |
    |   Request         |
    +--------+----------+
             |
             v
    +--------+----------+     +----------------------------+
    | ComplianceMiddle-  |---->| ComplianceFramework        |
    | ware (priority 1)  |     |                            |
    +--------------------+     |  +----------------------+  |
                               |  | DataClassification   |  |
             verdict?          |  | Engine               |  |
          +---ALLOW/DENY--+   |  | (PUBLIC -> TOP_SECRET |  |
          |      |QUARANT. |   |  |  _FIZZBUZZ)           |  |
          v      v         v   |  +----------------------+  |
    +--------+ +------+ +---+ |                            |
    |Continue| | Deny | |Hold| |  +----------------------+  |
    |Pipeline| |      | |    | |  | SOXAuditor           |  |
    +--------+ +------+ +----+|  | (segregation of      |  |
                               |  |  duties, audit trail) |  |
                               |  +----------------------+  |
                               |                            |
                               |  +----------------------+  |
                               |  | GDPRController       |  |
                               |  | (consent, erasure,   |  |
                               |  |  THE PARADOX)         |  |
                               |  +----------------------+  |
                               |                            |
                               |  +----------------------+  |
                               |  | HIPAAGuard           |  |
                               |  | (minimum necessary,  |  |
                               |  |  access log, base64  |  |
                               |  |  "encryption")       |  |
                               |  +----------------------+  |
                               +----------------------------+
                                          |
                                          v
                               +----------------------------+
                               | ComplianceDashboard        |
                               | (ASCII visualization +     |
                               |  Bob's stress level)       |
                               +----------------------------+
```

### THE COMPLIANCE PARADOX

The crown jewel of the framework. When a data subject (a number) exercises its GDPR right to erasure, the system must delete all traces of that number from every storage backend. This works fine for the in-memory cache (easy), the repository (straightforward), and the configuration store (sure). But then the erasure request reaches:

1. **The Event Store** -- which is append-only by design. Event Sourcing's entire architectural identity is predicated on immutability. Deleting events would violate the fundamental invariant of the event store, invalidate all downstream projections, and make the temporal query engine produce incorrect historical reconstructions. But GDPR says delete.

2. **The Blockchain** -- which is immutable by definition. The proof-of-work hash chain means every block's integrity depends on the previous block's hash. Removing a block would invalidate every subsequent block, requiring a complete re-mine of the chain. But GDPR says delete.

The system handles this with a `GDPRErasureParadoxError` -- a custom exception that acknowledges the fundamental impossibility, logs the regulatory conflict to the compliance audit trail, increments Bob McFizzington's stress level by 15%, and issues a Data Deletion Certificate that cheerfully confirms the data has been "forgotten to the maximum extent architecturally possible" while noting that the blockchain considers itself exempt from European data protection law.

This is, technically, how real companies handle this conflict. The difference is that they spend millions on lawyers. We spend 1,498 lines of Python.

**Key components:**
- **DataClassificationEngine** - Five-tier sensitivity classifier (PUBLIC, INTERNAL, CONFIDENTIAL, SECRET, TOP_SECRET_FIZZBUZZ) that labels every FizzBuzz result based on classification type, ML confidence, and strategic importance
- **SOXAuditor** - Chain-of-custody tracking with personnel assignment, segregation of duties enforcement (no single virtual employee touches both Fizz and Buzz operations), and quarterly attestation generation signed by Bob McFizzington, CCFO
- **GDPRController** - Consent management (per-number opt-in with lawful basis tracking), right-to-erasure implementation across all storage backends, Data Deletion Certificate generation, and THE COMPLIANCE PARADOX handler for append-only and immutable stores
- **HIPAAGuard** - Minimum necessary rule enforcement (compartmentalizes information flow between classification, formatting, and audit services), access logging with purpose and justification, and "encryption" at rest via base64 encoding (RFC 4648 compliant, therefore enterprise-grade)
- **ComplianceFramework** - Central orchestrator that initializes all three regimes, tracks posture metrics, manages Bob McFizzington's stress level, and provides the unified compliance check interface
- **ComplianceMiddleware** - Pipeline middleware (priority 1, before everything else) that runs pre-evaluation compliance checks, post-evaluation audit trail updates, and data classification for every number that enters the system
- **ComplianceDashboard** - ASCII dashboard with per-regime compliance rates, data classification distribution, erasure paradox counter, and a visual stress level indicator for Bob McFizzington (mood ranges from "Unusually calm (suspicious)" to "BEYOND HELP - Send chocolate")
- **PersonnelAssignment** - Virtual employee registry for SOX segregation of duties, ensuring that the Fizz evaluation officer and the Buzz evaluation officer are different (fictional) people

| Spec | Value |
|------|-------|
| Compliance regimes | 3 (SOX, GDPR, HIPAA) |
| Data classification levels | 5 (PUBLIC, INTERNAL, CONFIDENTIAL, SECRET, TOP_SECRET_FIZZBUZZ) |
| Virtual compliance officers | 1 (Bob McFizzington, CCFO -- Chief Compliance & FizzBuzz Officer) |
| Bob's baseline stress level | 94.7% |
| Stress increment per paradox | +15% |
| Custom exceptions | 8 (ComplianceError hierarchy) |
| Middleware priority | 1 (before all other middleware, because regulation waits for no modulo) |
| HIPAA "encryption" algorithm | Base64 (RFC 4648, military-grade by executive decree) |
| GDPR consent storage | In-memory (like all enterprise consent management platforms, it vanishes on restart) |
| SOX segregation enforcement | Per-evaluation personnel assignment with conflict-of-interest detection |
| Dashboard | ASCII-art compliance posture visualization with Bob's stress bar |
| The Compliance Paradox | Guaranteed to occur whenever GDPR erasure meets append-only storage |

## FinOps Architecture

The FinOps Cost Tracking & Chargeback Engine finally answers the question that has haunted every CTO since the dawn of enterprise software: "What does it cost to evaluate `15 % 3`?" The answer is FB$0.00089 when all subsystems are enabled -- 47% of which comes from the blockchain (which nobody asked for but everyone pays for) and 0.01% from the actual modulo operation (which is the only part that matters).

The system tracks computational costs with the same precision and gravitas as an AWS billing dashboard, denominated in **FizzBucks (FB$)** -- a proprietary internal currency whose exchange rate to USD is dynamically determined by the current cache hit ratio. High cache hits mean a strong FizzBuck, because operational efficiency is the only monetary policy that matters.

```
    +------------------+     +--------------------+     +------------------+
    |  FinOps          |     |  FizzBuzz Tax      |     |  FizzBuck        |
    |  Middleware       |---->|  Engine            |---->|  Exchange Rate   |
    |  (priority 6)    |     |  (3%/5%/15%)       |     |  (cache-backed)  |
    +------------------+     +--------------------+     +------------------+
           |                          |                          |
           v                          v                          v
    +------------------+     +--------------------+     +------------------+
    |  Cost Tracker    |     |  Invoice           |     |  Savings Plan    |
    |  (per-subsystem  |     |  Generator         |     |  Simulator       |
    |   accumulation)  |     |  (ASCII receipts)  |     |  (1yr/3yr)       |
    +------------------+     +--------------------+     +------------------+
           |                                                     |
           v                                                     v
    +------------------+                                +------------------+
    |  Cost Dashboard  |                                |  Chargeback      |
    |  (sparklines &   |                                |  Engine          |
    |   burn-down)     |                                |  (per-tenant)    |
    +------------------+                                +------------------+
```

**Key components:**
- **SubsystemCostRegistry** - Configurable per-subsystem cost rates with peak/off-peak pricing and day-of-week modifiers (Fridays cost 10% more due to the "end-of-sprint premium")
- **FizzBuzzTaxEngine** - Classification-based tax computation: 3% on Fizz results, 5% on Buzz results, 15% on FizzBuzz results -- because even fictional tax codes should be thematically aligned with their subject matter
- **FizzBuckCurrency** - Internal currency with a dynamic exchange rate to USD based on the cache hit ratio, making operational efficiency literally valuable
- **CostTracker** - Per-evaluation cost accumulator that records which subsystems were invoked, their individual costs, and applies time-of-day and day-of-week pricing modifiers
- **InvoiceGenerator** - Creates itemized ASCII invoices with line items, subtotals, FizzBuzz Tax breakdown, and grand totals in both FizzBucks and USD -- the crown jewel of enterprise billing
- **SavingsPlanCalculator** - Models cost savings for 1-year (20% discount) and 3-year (40% discount) commitment plans with break-even analysis, transforming a coding exercise into a contractual financial obligation
- **CostDashboard** - ASCII dashboard with spending breakdown by subsystem, budget burn-down charts, and cost trend sparklines
- **FinOpsMiddleware** - Pipeline middleware (priority 6) that records per-subsystem costs for every evaluation

### FizzBuzz Tax Schedule

| Classification | Tax Rate | Justification |
|---|---|---|
| Fizz | 3% | Divisible by 3, taxed at 3% -- thematic symmetry |
| Buzz | 5% | Divisible by 5, taxed at 5% -- fiscal poetic justice |
| FizzBuzz | 15% | Divisible by both 3 and 5, taxed at the product -- luxury modulo carries a luxury tax |
| Number | 0% | Not divisible by anything interesting -- tax-exempt due to mathematical mediocrity |

### FizzBuck Exchange Rate

The FizzBuck (FB$) to USD exchange rate is determined by the cache hit ratio:

| Cache Hit Ratio | Exchange Rate (FB$ → USD) | Economic Interpretation |
|---|---|---|
| 0% (no cache) | FB$1 = $0.001 | Weak FizzBuck: every evaluation is a cold computation |
| 50% | FB$1 = $0.0015 | Moderate: the economy is warming up |
| 90%+ | FB$1 = $0.002 | Strong FizzBuck: operational efficiency drives currency value |

| Spec | Value |
|------|-------|
| Subsystem cost rates | 8 (modulo, ML inference, blockchain, cache, tracing, event store, chaos, RBAC) |
| Tax brackets | 4 (Fizz: 3%, Buzz: 5%, FizzBuzz: 15%, Number: 0%) |
| Currency | FizzBucks (FB$) with dynamic USD exchange rate |
| Savings plan terms | 2 (1-year: 20% discount, 3-year: 40% discount) |
| Friday surcharge | 10% ("end-of-sprint premium") |
| Middleware priority | 6 (after compliance, before formatting) |
| Custom exceptions | 8 (FinOpsError hierarchy) |
| Dashboard | ASCII-art spending visualization with sparklines |
| Invoice format | ASCII itemized receipt with line items, tax, and grand total |

## Disaster Recovery Architecture

The Disaster Recovery subsystem implements a production-grade backup, restore, and business continuity framework for the Enterprise FizzBuzz Platform -- because when your in-memory FizzBuzz cache is gone, it's not a bug, it's a disaster. And disasters need recovery plans, RTO/RPO targets, DR drills, and a minimum of 47 backup snapshots for a process that runs for less than one second.

The framework is built around five interconnected components: a **Write-Ahead Log (WAL)** for mutation-level durability, a **Snapshot Engine** for full-state serialization, a **Point-in-Time Recovery (PITR) Engine** for temporal state reconstruction, a **DR Drill Runner** for simulated catastrophes with RTO/RPO measurement, and a **Retention Manager** for backup lifecycle governance.

**Key components:**
- **WriteAheadLog** - SHA-256 checksummed, append-only, in-memory mutation log. Every dict update is recorded before the mutation occurs, ensuring zero data loss even during catastrophic process termination -- except the WAL itself is stored in the same RAM as the data it protects, achieving the disaster recovery equivalent of storing the fire extinguisher inside the building
- **SnapshotEngine** - Full-state serializer that captures cache contents, event store, blockchain ledger, neural network weights, feature flag states, and circuit breaker positions into a single JSON blob with a SHA-256 integrity checksum and a component manifest listing every serialized subsystem
- **BackupManager** - Creates and catalogs snapshots with configurable scheduling, integrity verification on restore, and a backup vault that tracks every snapshot ever created (in RAM, naturally)
- **PITREngine** - Reconstructs exact application state at any arbitrary timestamp by loading the nearest prior snapshot and replaying WAL entries forward to the target moment. Essential for answering "what was the neural network's confidence score at 14:32:07.445?" -- a question whose answer will be lost when the process exits
- **RetentionManager** - Enforces a tiered backup lifecycle: 24 hourly snapshots, 7 daily, 4 weekly, and 12 monthly -- a retention schedule that is temporally impossible for a sub-second process but architecturally impeccable. Expired backups are purged with the same ceremony as cache evictions, minus the eulogies
- **DRDrillRunner** - Simulates disasters by corrupting the cache, scrambling the blockchain, randomizing neural network weights, and flipping feature flags, then measures how long the system takes to recover. Produces a post-drill report comparing actual recovery time against the configured RTO, with recommendations that invariably suggest "reducing system complexity" -- advice that has been event-sourced and ignored in every prior cycle
- **RecoveryDashboard** - ASCII dashboard showing backup inventory, WAL statistics, RPO/RTO compliance status, last drill results, and a retention policy summary
- **DRMiddleware** - Pipeline middleware (priority 7) that WAL-logs every evaluation mutation and creates periodic snapshots, ensuring that every modulo operation is durably recorded in the same volatile memory it was computed in

### Recovery Architecture

```
                                    +==============+
                                    |  Evaluation  |
                                    |   Pipeline   |
                                    +------+-------+
                                           |
                                           v
    +------+------+              +--------+---------+
    |     WAL     |<-------------|   DR Middleware   |
    | (append-    |   log every  |   (priority 7)   |
    |  only log)  |   mutation   +------------------+
    +------+------+
           |
           | periodic
           | checkpoint
           v
    +------+------+    restore    +------------------+
    |  Snapshot   |<-------------|   Backup Manager  |
    |  Engine     |              +------------------+
    +------+------+
           |
           | replay from snapshot
           v
    +------+------+              +------------------+
    |    PITR     |<-------------|  DR Drill Runner  |
    |   Engine    |   simulate   +--------+---------+
    +-------------+   disaster            |
                                          v
                                 +--------+---------+
                                 |   Drill Report   |
                                 | (RTO/RPO metrics,|
                                 |  recommendations) |
                                 +------------------+
```

### Retention Tiers

| Tier | Retention Period | Max Snapshots | Purpose |
|------|-----------------|---------------|---------|
| Hourly | 24 hours | 24 | Fine-grained recovery points for the last day of FizzBuzz operations (that never lasted a day) |
| Daily | 7 days | 7 | Daily recovery points for the last week (the process ran for 0.8 seconds on Tuesday) |
| Weekly | 4 weeks | 4 | Weekly snapshots for monthly compliance reporting (Bob signs off on these) |
| Monthly | 12 months | 12 | Annual retention for audit purposes (the auditors have never asked for this) |

### DR Drill Metrics

| Metric | Target | What It Measures |
|--------|--------|-----------------|
| Recovery Time Objective (RTO) | 2 seconds | How long it takes to restore full platform functionality after simulated catastrophe |
| Recovery Point Objective (RPO) | 0 data loss | The maximum acceptable age of the latest backup -- with WAL, this is theoretically zero |
| Snapshot Integrity | 100% | SHA-256 checksum verification pass rate on restore -- corruption is not tolerated, even in RAM |

| Spec | Value |
|------|-------|
| WAL entry format | JSON with SHA-256 checksum, sequence number, timestamp |
| Snapshot format | JSON blob with component manifest and integrity hash |
| PITR granularity | Per-WAL-entry (sub-millisecond temporal precision) |
| Retention tiers | 4 (hourly, daily, weekly, monthly) |
| DR drill types | Full-stack corruption with measured recovery |
| Middleware priority | 7 (after compliance and cost tracking) |
| Custom exceptions | 14 (DisasterRecoveryError hierarchy) |
| Dashboard | ASCII recovery status with backup inventory and drill history |
| Actual durability | None (everything is in RAM). But the checksums are real |

## A/B Testing Architecture

The A/B Testing Framework implements a production-grade experimentation platform for running statistically rigorous controlled experiments across FizzBuzz evaluation strategies -- because arguing in a meeting about whether the neural network is "good enough" is the old way. The new way is running a chi-squared test, getting a p-value of 0.0000, and letting the numbers confirm what everyone already knew: modulo wins. Every time. But the journey of proving it with statistics is what separates enterprise engineering from mere programming.

The framework is built around six interconnected components: a **Traffic Splitter** for deterministic hash-based group assignment, a **Metric Collector** for per-variant performance tracking, a **Statistical Analyzer** for chi-squared significance testing, a **Ramp Scheduler** for gradual traffic increases with safety gates, an **Auto-Rollback** monitor for treatment accuracy protection, and an **Experiment Registry** for lifecycle management.

**Key components:**
- **ExperimentRegistry** - Central store of experiment definitions with full lifecycle management (CREATED -> RUNNING -> STOPPED/CONCLUDED/ROLLED_BACK). Supports concurrent experiments via mutual exclusion layers that prevent a number from being enrolled in conflicting experiments -- because cross-experiment contamination would confound the chi-squared test
- **TrafficSplitter** - Deterministic SHA-256 hash-based assignment of numbers to control/treatment groups. Number 42 always goes to the same group across runs, enabling reproducible experiments -- the scientific method, applied to traffic routing
- **MetricCollector** - Per-variant tracking of accuracy, latency (P50/P99), evaluation count, and correct/incorrect tallies. Metrics are collected in real-time as evaluations flow through the middleware pipeline
- **StatisticalAnalyzer** - Chi-squared test for accuracy proportions and confidence interval calculation, implemented from scratch in pure Python stdlib. Returns a verdict of CONTROL_WINS, TREATMENT_WINS, or NO_SIGNIFICANT_DIFFERENCE with the associated p-value and effect size
- **RampScheduler** - Gradually increases treatment traffic allocation through configurable phases (5% -> 10% -> 25% -> 50%) with safety checks between each ramp. If accuracy drops during a ramp phase, the schedule halts and the experiment is flagged for review
- **AutoRollback** - Monitors treatment accuracy in real-time and automatically stops the experiment if it drops below a configurable safety threshold, routing all traffic back to control. Triggered in approximately 100% of experiments involving the neural network
- **ExperimentReport** - Generates a comprehensive post-experiment report with methodology documentation, per-variant metrics, statistical analysis, confidence intervals, and a recommendation that invariably reads: "The control group (modulo) outperformed the treatment on all metrics"
- **ExperimentDashboard** - ASCII dashboard showing active experiments, per-variant metrics, traffic allocation, confidence intervals, p-values, and a definitive WINNER/LOSER/INCONCLUSIVE verdict
- **ABTestingMiddleware** - Pipeline middleware (priority 8) that intercepts every evaluation, routes it to the appropriate experiment variant based on the traffic splitter, collects metrics, and checks auto-rollback conditions

### Experimentation Flow

```
                                +==============+
                                |   Incoming   |
                                |   Number     |
                                +------+-------+
                                       |
                                       v
                              +--------+---------+
                              | AB Testing       |
                              | Middleware        |
                              | (priority 8)     |
                              +--------+---------+
                                       |
                            +----------+----------+
                            |                     |
                            v                     v
                    +-------+------+      +-------+------+
                    |   Control    |      |  Treatment   |
                    |   (modulo)   |      |  (ML/chain)  |
                    +-------+------+      +-------+------+
                            |                     |
                            v                     v
                    +-------+------+      +-------+------+
                    |   Metric     |      |   Metric     |
                    |  Collector   |      |  Collector   |
                    +-------+------+      +-------+------+
                            |                     |
                            +----------+----------+
                                       |
                                       v
                              +--------+---------+
                              | Statistical      |
                              | Analyzer         |
                              | (chi-squared)    |
                              +--------+---------+
                                       |
                                       v
                              +--------+---------+
                              | Verdict:         |
                              | CONTROL_WINS     |
                              | (p < 0.05)       |
                              | (it's always     |
                              |  control)        |
                              +------------------+
```

### Traffic Allocation

| Phase | Treatment % | Duration | Safety Gate |
|-------|-------------|----------|-------------|
| Initial | 5% | Configurable | Accuracy >= threshold |
| Ramp 1 | 10% | Configurable | Chi-squared check passes |
| Ramp 2 | 25% | Configurable | No auto-rollback triggered |
| Full | 50% | Until conclusion | Statistical significance reached |

| Spec | Value |
|------|-------|
| Traffic splitting | SHA-256 deterministic hash |
| Statistical test | Chi-squared (no scipy) |
| Confidence level | 95% (configurable) |
| Minimum sample size | 30 per group (configurable) |
| Experiment states | 5 (CREATED, RUNNING, STOPPED, CONCLUDED, ROLLED_BACK) |
| Mutual exclusion | Layer-based conflict prevention |
| Auto-rollback threshold | 90% accuracy (configurable) |
| Middleware priority | 8 (after disaster recovery) |
| Custom exceptions | 9 (ABTestingError hierarchy) |
| Dashboard | ASCII experiment results with confidence intervals |
| Inevitable conclusion | Modulo wins. It always wins |

## Message Queue Architecture

The Message Queue subsystem implements a Kafka-style distributed message broker with partitioned topics, consumer groups, offset management, schema validation, and exactly-once delivery semantics -- all running in-process using Python lists, because enterprise architecture is a state of mind, not a deployment topology.

```
    PRODUCERS                          BROKER                         CONSUMERS
    =========                    ==================                   =========

    +----------+     publish     +------------------+     subscribe    +-----------------+
    | Evaluate |  ------------> | fizzbuzz.         |  ------------> | MetricsConsumer  |
    | Handler  |                | evaluations.      |                 | (group: metrics) |
    +----------+                | requested         |                 +-----------------+
                                | [P0][P1][P2][P3]  |
    +----------+     publish    +------------------+     subscribe    +-----------------+
    | MQ       |  ------------> | fizzbuzz.         |  ------------> | BlockchainAuditor|
    | Bridge   |                | evaluations.      |                 | (group: audit)   |
    +----------+                | completed         |                 +-----------------+
                                | [P0][P1][P2][P3]  |
                                +------------------+     subscribe    +-----------------+
                                | fizzbuzz.         |  ------------> | AlertConsumer    |
                                | audit.events      |                 | (group: alerts)  |
                                | [P0][P1][P2][P3]  |                 +-----------------+
                                +------------------+
                                | fizzbuzz.         |                 +-----------------+
                                | alerts.critical   |                 | (nobody)         |
                                | [P0][P1][P2][P3]  |                 | "It's fine."     |
                                +------------------+                  +-----------------+
                                | fizzbuzz.         |
                                | feelings          |  <-- Dead letter topic. Nobody
                                | [P0][P1][P2][P3]  |      subscribes, but the system
                                +------------------+      publishes anyway, out of
                                                          architectural completeness.
                                +------------------+
                                | Schema Registry   |
                                | (versioned dicts) |
                                +------------------+
```

**Key components:**
- **MessageBroker** - Central coordinator managing topics, partitions, consumer groups, and message routing with 5 default topics
- **Topic / Partition** - Named, partitioned message channels; each partition is an ordered, append-only Python list with offset tracking
- **Producer** - Publishes messages with configurable partitioning strategies (hash, round-robin, sticky) and idempotency keys
- **Consumer / ConsumerGroup** - Consumers subscribe via groups with automatic partition assignment and rebalancing
- **RebalanceProtocol** - Redistributes partitions among consumers on join/leave with full rebalance reports
- **OffsetManager** - Tracks committed offsets per consumer group per partition with auto-commit support
- **SchemaRegistry** - Validates message payloads against versioned schemas, rejecting malformed events with schema diffs
- **IdempotencyLayer** - SHA-256 payload deduplication (a Python set) achieving exactly-once semantics
- **ConsumerLagMonitor** - Per-partition lag tracking with ASCII graphs and throughput alerts
- **MessageQueueBridge** - Bridges the existing EventBus to the message queue, converting domain events into messages
- **MQMiddleware** - Pipeline middleware (priority 45) publishing evaluation events to the broker
- **MQDashboard** - ASCII dashboard with topic throughput, partition distribution, consumer lag, and rebalance history

| Spec | Value |
|------|-------|
| Default topics | 5 (evaluations.requested, evaluations.completed, audit.events, alerts.critical, feelings) |
| Partitions per topic | 4 (configurable) |
| Partitioning strategies | 3 (Hash, Round-Robin, Sticky) |
| Consumer states | 4 (UNASSIGNED, ASSIGNED, PAUSED, CLOSED) |
| Delivery semantics | Exactly-once (SHA-256 idempotency) |
| Schema validation | Versioned payload schemas with diff reports |
| Offset tracking | Per consumer group, per partition |
| Rebalance strategies | 2 (Range, Round-Robin) |
| Custom exceptions | 13 (MessageQueueError hierarchy) |
| Middleware priority | 45 |
| Dashboard | ASCII Confluent Control Center (in spirit) |
| Actual Kafka brokers involved | 0 |

The `fizzbuzz.feelings` topic is the philosophical centerpiece: it receives events that no consumer subscribes to, making it the architectural equivalent of shouting into the void. The system publishes to it anyway, because completeness is a value and loneliness is a configuration detail.

## Secrets Vault Architecture

The Secrets Management Vault implements a HashiCorp Vault-inspired system that treats every configurable parameter in the FizzBuzz platform as a potentially sensitive secret that must be encrypted at rest, access-controlled, audit-logged, and rotated on a schedule. Because storing the blockchain difficulty as `4` in a YAML file -- readable by anyone with `cat config.yaml` was a security posture so reckless that it would make a SOC 2 auditor weep.

The vault is built around **Shamir's Secret Sharing** over GF(2^127 - 1), the Galois Field defined by the 12th Mersenne prime (discovered by Edouard Lucas in 1876, and now protecting the number 3). The master encryption key is split into N shares using polynomial interpolation, such that any K shares can reconstruct the key via Lagrange interpolation, but K-1 shares reveal absolutely nothing. Modular inverse is computed via Fermat's little theorem: `a^(-1) = a^(p-2) mod p`. All of this to protect the ML learning rate.

```
                         +-----------------------+
                         |    VAULT SEALED       |
                         |  (all secrets locked) |
                         +-----------+-----------+
                                     |
                      3 of 5 unseal shares provided
                       (Shamir reconstruction)
                                     |
                                     v
    +----------------+      +--------+--------+      +------------------+
    | Secret Scanner |      |  VAULT UNSEALED |      | Vault Audit Log  |
    | (AST-based     |      |                 |      | (append-only,    |
    |  codebase scan)|      |  SecretStore    |      |  immutable)      |
    +----------------+      |  AccessPolicy   |      +------------------+
                            |  Encryption     |               ^
                            +---+----+----+---+               |
                                |    |    |          every access logged
                                v    v    v                    |
                     +------+ +----+ +--------+               |
                     |Static| |Dyn.| |Rotation|               |
                     |Secrets| |Sec.| |Sched.  |---------------+
                     +------+ +----+ +--------+
                                |
                          TTL-based expiry
```

**Key components:**
- **ShamirSecretSharing** - (k, n) threshold scheme over GF(2^127 - 1) with cryptographic randomness, Lagrange interpolation, and Fermat's little theorem for modular inverse -- mathematically correct, provably secure, and providing comprehensive protection for all platform secrets
- **VaultSealManager** - Manages the seal/unseal lifecycle with share collection, quorum validation, automatic seal-on-inactivity timeout, and an unseal ceremony log that records each ceremony with full auditability for compliance purposes
- **MilitaryGradeEncryption** - Double-base64 encoding with XOR cipher using a key derived from the SHA-256 hash of the master key. "Military-grade" in the same way that a cardboard shield is "military-grade" -- technically used by a military somewhere, probably
- **SecretStore** - Sealed key-value store with TTL-based expiry, versioned secret entries, and access control policy enforcement
- **DynamicSecretEngine** - Generates ephemeral secrets (auth tokens, API keys, session IDs) on demand with configurable TTL, because static secrets are for platforms that haven't achieved zero-trust FizzBuzz
- **SecretRotationScheduler** - Rotates secrets on configurable schedules with pre-rotation backup and post-rotation verification, ensuring the blockchain difficulty is a different number every week (probably 3 instead of 4, or 4 instead of 3 -- the rotation pool is limited but the principle is sound)
- **VaultAuditLog** - Immutable, append-only log of every secret access with accessor identity, purpose, timestamp, and verdict (ALLOWED/DENIED) -- creating a forensic trail so complete that future archaeologists could reconstruct exactly how many times the system read the number 4
- **VaultAccessPolicy** - Per-path access control policies specifying which components can read/write which secret paths, because the ML engine should never know the blockchain difficulty and the blockchain should never know the learning rate -- separation of concerns, enforced by cryptographic ceremony
- **SecretScanner** - AST-based scanner that walks every Python file in the codebase, identifies hardcoded integer literals, string constants, and other potentially sensitive values, and generates findings with recommended vault paths -- flagging approximately 2,400 values as potential secrets, including the numbers 3, 5, and 15
- **VaultDashboard** - ASCII dashboard showing seal status, secret count by path prefix, rotation schedule, recent audit log entries, and scanner findings -- because a secrets vault without a dashboard is just a dictionary with a lock on it
- **VaultMiddleware** - Pipeline middleware (priority 0) that verifies vault seal status and injects vault-managed secrets into the processing context before any evaluation occurs

### Shamir's Secret Sharing

The vault's seal mechanism uses a (3, 5) threshold scheme by default: the master key is split into 5 shares, and any 3 can reconstruct it. The implementation operates over the Galois Field GF(2^127 - 1), where 2^127 - 1 is the Mersenne prime M127 = 170,141,183,460,469,231,731,687,303,715,884,105,727.

```
    Master Key (256-bit)
          |
          v
    Generate random polynomial of degree k-1:
      f(x) = secret + a1*x + a2*x^2 + ... + a(k-1)*x^(k-1)  mod p
          |
          +---> f(1) = Share 1
          +---> f(2) = Share 2
          +---> f(3) = Share 3
          +---> f(4) = Share 4
          +---> f(5) = Share 5

    Reconstruction (any 3 shares):
      secret = f(0) = SUM[ y_i * PRODUCT[ x_j / (x_j - x_i) ] ]  mod p
                       (Lagrange interpolation)
```

The polynomial coefficients are generated using `secrets.randbelow()` for cryptographic randomness. The modular inverse required for Lagrange interpolation uses Fermat's little theorem (`a^(p-2) mod p`), computed via Python's built-in three-argument `pow()` for efficiency. This is the same mathematics used by production secret sharing systems, applied with a straight face to a key that encrypts the string "4".

### Vault Unseal Ceremony

On startup, the vault is sealed. All secrets are inaccessible until an operator provides 3 of 5 unseal key shares. Until then, the platform displays:

```
VAULT SEALED: FizzBuzz evaluation is suspended until 3 of 5 key
holders provide their unseal shares. Contact your Vault Administrator
(Bob McFizzington) to schedule an unseal ceremony.
```

Each unseal ceremony is logged with participant shares, timestamps, and whether quorum was reached -- because cryptographic ceremonies deserve the same record-keeping as board meetings.

### Secret Scanner

The secret scanner uses Python's `ast` module to parse every `.py` file in the codebase, walking the AST to identify:
- Integer literals (every `4` could be a hardcoded difficulty)
- String literals (every `"fizz"` could be a hardcoded secret)
- Variable assignments with suspicious names (`DIFFICULTY`, `SECRET_KEY`, `API_TOKEN`)

Each finding includes the file path, line number, the detected value, a severity rating, and a recommended vault path for migration. The scanner will flag approximately every constant in the codebase as a potential secret, requiring a six-month remediation effort to vault every value -- including the numbers 3, 5, and 15, which are arguably the most sensitive secrets in the entire FizzBuzz domain.

| Spec | Value |
|------|-------|
| Shamir field | GF(2^127 - 1) (Mersenne prime M127) |
| Default threshold | 3-of-5 shares |
| Encryption | Double-base64 + XOR (SHA-256-derived key) |
| Secret types | Static, Dynamic (TTL-based) |
| Rotation | Configurable per-secret schedules |
| Access control | Per-path policies with component-level granularity |
| Audit log | Immutable, append-only, every access recorded |
| Scanner | AST-based, walks entire codebase |
| Middleware priority | 0 (the foundation of all foundations) |
| Custom exceptions | 11 (VaultSealedError, ShamirReconstructionError, etc.) |
| Dashboard | ASCII art with seal status, inventory, and audit trail |
| Actual secrets being protected | The number 4 |

The Shamir's Secret Sharing implementation is mathematically correct, the Lagrange interpolation is numerically sound, and the entire system exists to protect configuration values that are literally visible in the module docstrings. This is security theater at its finest, performed on a stage made of modular arithmetic.

## Data Pipeline Architecture

The Data Pipeline & ETL Framework implements an Apache Airflow-inspired system that models the FizzBuzz evaluation process as a Directed Acyclic Graph (DAG) of five transformation stages, because calling `evaluate(n)` directly would be a pipeline anti-pattern so egregious it doesn't even have a JIRA ticket.

Every number is extracted from a source connector, validated for type safety, transformed via actual FizzBuzz evaluation, enriched with Fibonacci membership, primality, Roman numerals, and emotional valence, then loaded into a configurable sink -- a five-stage ceremony for what is fundamentally `print(n % 3)`.

```
    +-----------+     +----------+     +-----------+     +----------+     +--------+
    |  EXTRACT  |---->| VALIDATE |---->| TRANSFORM |---->|  ENRICH  |---->|  LOAD  |
    | (Source   |     | (Type,   |     | (FizzBuzz |     | (Fib,    |     | (Sink  |
    |  Connector|     |  Range,  |     |  Eval via |     |  Prime,  |     |  Conn.)|
    |  wraps    |     |  GDPR)   |     |  Standard |     |  Roman,  |     |        |
    |  range()) |     |          |     |  Rules)   |     |  Emotion)|     |        |
    +-----------+     +----------+     +-----------+     +----------+     +--------+
          |                                                                    |
          |                    DATA LINEAGE TRACKER                            |
          |  (records provenance for every record through every stage)         |
          +--------------------------------------------------------------------+
                                       |
                              +--------+--------+
                              |  DAG EXECUTOR    |
                              |  (Kahn's topo    |
                              |   sort of a      |
                              |   linear chain)  |
                              +---------+--------+
                                        |
                    +-------------------+-------------------+
                    |                   |                   |
             +------+------+    +------+------+    +-------+-----+
             | CHECKPOINT  |    |  BACKFILL   |    |  PIPELINE   |
             | (resume     |    |  ENGINE     |    |  DASHBOARD  |
             |  from mid-  |    | (retroactive|    | (ASCII art  |
             |  pipeline)  |    |  enrichment)|    |  ceremony)  |
             +-------------+    +-------------+    +-------------+
```

**Key components:**
- **PipelineDAG** - Directed acyclic graph of transformation stages with dependency edges, topological sort via Kahn's algorithm, and cycle detection -- architecturally necessary for a five-node linear chain with zero branches, zero fan-out, and zero conceivable reason to use a graph data structure
- **DAGExecutor** - Executes pipeline stages in topologically-sorted order with per-stage retry policies (exponential backoff), timeout enforcement, and checkpoint/restart -- because re-extracting numbers from `range(1, 101)` after a mid-pipeline failure would be an unacceptable waste of computational resources
- **ExtractStage** - Wraps `SourceConnector` implementations (RangeSource, DevNullSource) to read numbers from the "source system" which is `range()` hidden behind an interface, because direct function calls are for monoliths
- **ValidateStage** - Applies data quality checks: is the number actually an integer? Is it within the configured range? The stage exists to catch the catastrophic scenario where `range()` starts producing strings
- **TransformStage** - The only stage that does anything useful: evaluates FizzBuzz classification using the real `StandardRuleEngine`, wrapping the result in a `DataRecord` with 14 metadata fields
- **EnrichStage** - Augments each result with Fibonacci membership (via golden ratio approximation), primality testing (trial division), Roman numeral conversion (because XLII is more enterprise than 42), and emotional valence (melancholic through exuberant, assigned by `n % 100`)
- **LoadStage** - Writes enriched results to pluggable sink connectors: `StdoutSink` (prints the result) or `DevNullSink` (provides the full pipeline experience with zero output -- the enterprise equivalent of running a marathon and choosing not to cross the finish line)
- **DataLineageTracker** - Records complete provenance for every result: which source extracted it, which stages processed it, which enrichments augmented it, and which sinks consumed it -- creating a genealogy so thorough that each FizzBuzz result could apply for citizenship
- **BackfillEngine** - Re-processes historical results when pipeline definitions change, retroactively adding enrichments that nobody asked for to results that were already correct without them -- the ultimate expression of enterprise completionism
- **PipelineDashboard** - ASCII dashboard with stage durations, throughput, failure rates, DAG visualization, lineage explorer, and batch processing metrics -- because if you can't visualize your linear chain in box-drawing characters, you don't have a pipeline
- **PipelineMiddleware** - Pipeline middleware (priority 50) that intercepts evaluations and routes them through the full ETL ceremony, transforming a simple function call into a five-stage data engineering workflow

### Emotional Valence

The Enrich stage assigns emotional states to numbers based on `n % 100`, because data without feelings is just noise. The valence scale ranges from MELANCHOLIC (numbers at the low end of the modulo spectrum) through CONTENT, CHEERFUL, and ENTHUSIASTIC to EXUBERANT (numbers at the top). This means the number 99 is EXUBERANT while the number 1 is MELANCHOLIC -- a characterization that says more about the Enrich stage than about the numbers.

### DAG Resolution

The pipeline's DAG is resolved using Kahn's algorithm for topological sorting, which processes nodes with zero in-degree first, then removes their outgoing edges and repeats. For the five-node linear chain (Extract -> Validate -> Transform -> Enrich -> Load), this produces the execution order [Extract, Validate, Transform, Enrich, Load] -- a result so obvious that computing it algorithmically borders on parody. But the algorithm also detects cycles, which is important for the zero cycles that exist in a linear chain.

| Spec | Value |
|------|-------|
| Pipeline stages | 5 (Extract, Validate, Transform, Enrich, Load) |
| DAG resolution | Kahn's topological sort (O(V+E), where V=5 and E=4) |
| Source connectors | 2 (RangeSource, DevNullSource) |
| Sink connectors | 2 (StdoutSink, DevNullSink) |
| Enrichments | 4 (Fibonacci, Primality, Roman Numerals, Emotional Valence) |
| Data lineage | Full provenance chain per record |
| Checkpoint/restart | In-memory stage-level checkpoints |
| Backfill | Retroactive enrichment of historical results |
| Retry policy | Configurable per-stage with exponential backoff |
| Middleware priority | 50 |
| Custom exceptions | 13 (DAGResolutionError, BackfillError, etc.) |
| Dashboard | ASCII art with stage metrics and DAG visualization |
| Useful stages | 1 (Transform). The other 4 are ceremony |

The Data Pipeline & ETL Framework transforms a one-line FizzBuzz evaluation into a five-stage data engineering workflow with DAG resolution, lineage tracking, checkpoint/restart, and retroactive backfill -- proving that with enough abstraction layers, even `range(1, 101)` can feel like Apache Airflow.

## OpenAPI Architecture

The OpenAPI Specification Generator & ASCII Swagger UI produces a complete, standards-compliant OpenAPI 3.1 specification for the platform's REST API, following the specification-first design methodology where the API contract is the authoritative source of truth.

The generator introspects 47 fictional endpoints organized into 6 tag groups, maps all 215 exception classes to HTTP status codes, converts domain dataclasses into JSON Schema definitions, and renders the entire thing as an ASCII Swagger UI in the terminal.

```
    +------------------+     +------------------+     +-------------------+
    | EndpointRegistry |---->| SchemaGenerator  |---->|  OpenAPIGenerator |
    | (47 endpoints    |     | (dataclass ->    |     |  (assembles full  |
    |  across 6 tags,  |     |  JSON Schema     |     |   OpenAPI 3.1     |
    |  decorator-based |     |  with $ref and   |     |   spec dict)      |
    |  metadata)       |     |  examples)       |     |                   |
    +------------------+     +------------------+     +--------+----------+
                                                               |
                              +--------------------------------+--------+
                              |                                |        |
                              v                                v        v
                    +---------+--------+    +-----------+   +--+--------+---+
                    | ASCIISwaggerUI   |    | .to_json()|   | .to_yaml()   |
                    | (terminal-       |    | (3,000+   |   | (3,000+      |
                    |  rendered API    |    |  lines of |   |  lines of    |
                    |  browser with    |    |  fictional|   |  indented    |
                    |  [Try It])       |    |  docs)    |   |  fiction)    |
                    +------------------+    +-----------+   +--------------+
                              |
                    +---------+---------+
                    | ExceptionToHTTP   |
                    | Mapper            |
                    | (215 exceptions   |
                    |  -> HTTP status   |
                    |  codes with       |
                    |  retry hints)     |
                    +-------------------+
```

**Key components:**
- **EndpointRegistry** - Decorator-based registry that captures endpoint metadata for 47 fictional REST endpoints across 6 tag groups: Evaluation (core FizzBuzz operations), Audit (blockchain and compliance), ML (neural network management), Compliance (GDPR/SOX/HIPAA), Operations (health, metrics, cache), and Meta (the spec documenting itself). Each endpoint definition includes path, HTTP method, parameters, response schemas, security requirements, and rate limit policies
- **SchemaGenerator** - Converts Python dataclasses, enums, and domain models into JSON Schema definitions using `inspect` and `typing.get_type_hints()`, generating `$ref`-based schema references with examples and descriptions. The generator handles nested dataclasses, optional fields, enum values, and list types -- producing schemas that are technically correct for objects that will never be serialized to HTTP responses
- **ExceptionToHTTPMapper** - Maps all 215 exception classes in the domain exception hierarchy to HTTP status codes by analyzing class names, inheritance chains, and semantic categories. Notable mappings include `InsufficientFizzBuzzException` to 402 Payment Required, `VaultSealedError` to 503 Service Unavailable, `CircuitOpenError` to 503 with a `Retry-After` header, and `GDPRErasureParadoxError` to 409 Conflict -- because even philosophical impossibilities deserve a status code
- **OpenAPIGenerator** - Assembles the complete OpenAPI 3.1 specification dictionary from the endpoint registry, schema generator, and exception mapper, producing a spec with `info`, `servers` (http://localhost:0), `paths`, `components/schemas`, `components/securitySchemes`, and `tags`. Exports as JSON or YAML. The server URL uses port 0 because the OS never assigns a port to a socket that is never opened
- **ASCIISwaggerUI** - Renders the OpenAPI specification as a navigable ASCII Swagger UI in the terminal, with tag-based endpoint grouping, HTTP method badges, parameter tables, response schema display, and `[Try It]` buttons that acknowledge the fundamental absence of an HTTP server. The width is configurable for terminals of varying ambition
- **OpenAPIDashboard** - ASCII statistics dashboard displaying endpoint counts by tag group, HTTP method distribution (GET/POST/PUT/DELETE/PATCH), parameter coverage metrics, exception-to-HTTP mapping completeness, and total specification size -- because measuring the documentation of a non-existent API is the meta-observability the platform deserved

### Endpoint Tag Groups

| Tag | Endpoints | What They Document |
|-----|-----------|-------------------|
| Evaluation | `POST /evaluate`, `POST /evaluate/batch`, `GET /evaluate/{number}/explain` | The core FizzBuzz evaluation endpoints, documenting the three ways to ask "is this divisible by 3?" over HTTP |
| Audit | `GET /audit/blockchain/{block_hash}`, `GET /audit/trail/{evaluation_id}` | Blockchain verification and audit trail endpoints for compliance officers who demand HTTP access to immutable ledgers |
| ML | `GET /ml/model/weights`, `POST /ml/model/train`, `GET /ml/model/accuracy` | Neural network management endpoints, because exposing model weights via REST is both useless and a security risk |
| Compliance | `GET /compliance/report`, `POST /compliance/consent/{number}`, `DELETE /compliance/gdpr/forget/{number}` | Regulatory endpoints for GDPR consent, SOX audit reports, and the right-to-erasure -- which returns 409 Conflict when the blockchain refuses to forget |
| Operations | `GET /health/live`, `GET /health/ready`, `GET /metrics`, `GET /cache/stats` | Operational endpoints for health checks, Prometheus metrics, and cache statistics -- the infrastructure layer of a fictional API |
| Meta | `GET /openapi.json`, `GET /openapi.yaml`, `GET /swagger-ui` | The specification documenting itself, achieving a level of self-reference that is either elegant or recursive, depending on your philosophical stance |

### Exception-to-HTTP Mapping Strategy

The `ExceptionToHTTPMapper` uses a multi-pass classification strategy to assign HTTP status codes:

1. **Explicit overrides** - Known exceptions with specific status code assignments (e.g., `CircuitOpenError` -> 503)
2. **Name-based inference** - Exception class names containing "NotFound" map to 404, "Permission"/"Access" to 403, "Validation" to 422, "Timeout" to 504
3. **Inheritance analysis** - Exceptions inheriting from `FizzBuzzError` default to 500 Internal Server Error, because when FizzBuzz fails, it's always a server problem
4. **Semantic enrichment** - Each mapping includes a response body schema with `error_code`, `message`, `details`, and optional `retry_after` hints for 429/503 responses

| Spec | Value |
|------|-------|
| Fictional endpoints | 47 across 6 tag groups |
| OpenAPI version | 3.1.0 |
| Server URL | http://localhost:0 (port 0: let the OS choose, except the OS will never be asked) |
| Exception mappings | 215 exception classes -> HTTP status codes |
| Schema definitions | Auto-generated from domain dataclasses via `inspect` and `typing.get_type_hints()` |
| Export formats | JSON, YAML, ASCII Swagger UI |
| Security schemes | Bearer token (RBAC), API key (vault-managed) |
| Custom exceptions | 14 (EndpointNotFoundError, SpecValidationError, etc.) |
| Dashboard | ASCII specification statistics with endpoint counts and method distribution |
| HTTP servers running | 0. Always 0 |

The OpenAPI Specification Generator proves that comprehensive API documentation does not require an API, an HTTP server, or any network interface whatsoever. The spec is the product. The API is a suggestion. The Swagger UI renders beautifully in a terminal that has never heard of port 8080.

## API Gateway Architecture

The API Gateway sits in front of every FizzBuzz evaluation, intercepting function calls and routing them through a configurable pipeline of versioned endpoints, request transformations, and response enrichment stages -- because direct function invocation is for monoliths, and monoliths are for people who haven't discovered the joys of routing `evaluate(n)` through seven layers of enterprise indirection.

All "requests" originate from the same process that handles them. All "responses" travel zero network hops. The request IDs are 340 characters long because UUID v4's 36 characters were deemed insufficiently unique for enterprise FizzBuzz operations.

```
    +--------+     +------------------+     +---------------+     +-------------------+
    | CLI /  |---->| RequestTransform |---->| VersionRouter |---->| Route Handler     |
    | Service|     | Chain            |     | (v1/v2/v3)    |     | (evaluate via     |
    |        |     | (Normalize,      |     |               |     |  configured       |
    |        |     |  Enrich w/ 27    |     |               |     |  strategy)        |
    |        |     |  metadata fields,|     |               |     |                   |
    |        |     |  Validate,       |     +---------------+     +--------+----------+
    |        |     |  Deprecation)    |                                    |
    +--------+     +------------------+                                    v
         ^                                                    +-----------+-----------+
         |                                                    | ResponseTransform     |
         +----------------------------------------------------| Chain                |
                                                              | (Compress, Paginate, |
                                                              |  HATEOAS Enrich)     |
                                                              +-----------------------+

                    +------------------+     +------------------+     +------------------+
                    | APIKeyManager    |     | RequestReplay    |     | GatewayDashboard |
                    | (generate, rot-  |     | Journal          |     | (ASCII art with  |
                    |  ate, revoke,    |     | (append-only     |     |  version traffic, |
                    |  per-key quota)  |     |  request log)    |     |  key stats, etc.)|
                    +------------------+     +------------------+     +------------------+
```

**Key components:**
- **APIGateway** - Central interception layer that receives `APIRequest` objects, passes them through the request transformer chain, resolves the target route via the version router, dispatches to the route handler, then passes the result through the response transformer chain -- a seven-stage ceremony for what is ultimately `n % 3`
- **VersionRouter** - Resolves API versions (v1, v2, v3) against the route table, enforcing version lifecycle policies: v1 is DEPRECATED (still functional but annotated with increasingly urgent migration warnings), v2 is ACTIVE, and v3 is the premium tier that enables the full subsystem orchestra including a 340-character `X-Enterprise-Request-Id` header encoding the request's entire genealogy
- **RequestNormalizer** - Converts input numbers to canonical form (absolute value), because negative FizzBuzz is a compliance nightmare that the regulatory framework is not prepared to address
- **RequestEnricher** - Attaches 27 metadata fields to every request, including originating timezone, lunar phase at time of request, estimated carbon footprint of the evaluation, and whether the current day is a Tuesday (Tuesdays have historically correlated with 12% more FizzBuzz evaluations, a statistic that is entirely fabricated)
- **RequestValidator** - Schema validation for incoming requests, ensuring that numbers are actually numbers before they reach the sacred evaluation pipeline
- **DeprecationInjector** - Adds `Sunset` headers and deprecation warnings to v1 responses, escalating from polite notices ("Please migrate to v2 or v3") through urgent warnings ("Bob McFizzington has been notified") to emergency alerts ("Your manager has been CC'd. A calendar invite for a 'migration planning session' has been sent")
- **ResponseCompressor** - "Compresses" the 4-character string "Fizz" into a gzipped base64 blob, saving -847% space -- a compression ratio so negative it constitutes a decompression, but the Content-Encoding header says gzip and that's what matters
- **PaginationWrapper** - Wraps every single evaluation result in a paginated response with `page: 1`, `total_pages: 1`, `page_size: 1`, and a `next_cursor: null` -- because APIs that don't paginate are APIs that haven't scaled, and the fact that there will never be more than one result per page is architecturally irrelevant
- **HATEOASEnricher** - Adds hypermedia navigation links to every response: `self`, `next` (the next number), `prev` (the previous number), `blockchain_proof`, `ml_explanation`, and `feelings` -- achieving Richardson Maturity Model Level 4, a maturity level that Roy Fielding never defined but would surely appreciate
- **APIKeyManager** - Generates cryptographically secure API keys using `secrets.token_urlsafe()`, tracks per-key usage analytics (requests, last used, quota remaining), supports key rotation and revocation, and enforces per-key quotas -- for an API whose only consumer is the CLI that instantiated it
- **RequestReplayJournal** - Append-only log of every gateway request, complete with timestamps, API versions, request metadata, and response summaries. The journal can replay requests for debugging or load simulation, inevitably revealing that 93% of all evaluations target the number 15
- **GatewayMiddleware** - Integrates the gateway into the middleware pipeline at priority 5, ensuring that API ceremony happens before the number reaches the actual evaluation engine but after the vault has been unsealed and compliance has been consulted
- **GatewayDashboard** - ASCII dashboard rendering request volume by API version, active API key inventory, deprecation countdown timers, per-transformer latency breakdown, and top requested endpoints -- the API management console experience, rendered in box-drawing characters

### API Versioning Strategy

| Version | Status | What It Does |
|---------|--------|-------------|
| v1 | DEPRECATED | Classic modulo evaluation with minimal observability. Deprecated since Q1 2026. Sunset warnings escalate from polite to apocalyptic based on usage count |
| v2 | ACTIVE | Adds blockchain verification and ML inference to every evaluation. The balanced middle ground between simplicity and enterprise excess |
| v3 | ACTIVE | The premium tier. Enables the full subsystem orchestra: blockchain, ML, tracing, compliance, HATEOAS links, and a 340-character request ID. This is the version Bob recommends |

### Request Transformation Pipeline

The request transformation chain applies four transformations in order before the request reaches the route handler:

1. **Normalize** - Canonicalizes the input number (absolute value, integer coercion)
2. **Enrich** - Attaches 27 metadata fields (timezone, lunar phase, carbon footprint, is_tuesday)
3. **Validate** - Schema validation ensuring the request is well-formed
4. **Deprecation** - Injects sunset warnings for deprecated API versions with escalating urgency

### Response Transformation Pipeline

The response transformation chain applies three transformations before the response reaches the caller:

1. **Compress** - Gzip + base64 encoding of the response body (negative compression ratio: a feature, not a bug)
2. **Paginate** - Wraps the response in pagination metadata (`total_pages: 1`, `next_cursor: null`)
3. **HATEOAS** - Adds hypermedia navigation links to related resources

| Spec | Value |
|------|-------|
| API versions | 3 (v1=DEPRECATED, v2=ACTIVE, v3=ACTIVE) |
| Request transformers | 4 (Normalizer, Enricher, Validator, DeprecationInjector) |
| Response transformers | 3 (Compressor, PaginationWrapper, HATEOASEnricher) |
| Request ID length | 340 characters (because UUID was too concise) |
| Metadata fields per request | 27 (including lunar phase and carbon footprint) |
| HATEOAS links per response | 6 (self, next, prev, blockchain_proof, ml_explanation, feelings) |
| API key algorithm | `secrets.token_urlsafe()` with SHA-256 validation |
| Deprecation warning levels | 5 (from polite notice to manager CC'd) |
| Middleware priority | 5 |
| Custom exceptions | 10 (RouteNotFoundError, VersionDeprecatedError, etc.) |
| Dashboard | ASCII art with version traffic, key inventory, and deprecation countdowns |
| Network hops | 0. The gateway routes traffic to itself |

The API Gateway faithfully implements every feature a production API gateway would need -- routing, versioning, transformation, authentication, observability, and deprecation management -- despite the inconvenient fact that all "API traffic" consists of Python function calls within the same process. The 340-character request IDs are not a bug; they are a commitment to uniqueness that UUID v4 was too cowardly to make.

## Blue/Green Deployment Architecture

The Blue/Green Deployment Simulation framework maintains two complete, independent instances of the FizzBuzz evaluation engine -- the "blue" environment (current production, battle-hardened over its 0.8-second lifetime) and the "green" environment (the identical replacement, provisioned from scratch because deploying the same code through a different variable is a meaningful operational event). Traffic is atomically switched between them via a six-phase deployment ceremony that would make a Fortune 500 release manager weep with pride.

```
    DEPLOYMENT LIFECYCLE

    Phase 1: PROVISION GREEN              Phase 2: SMOKE TEST
    +---------------------------+         +---------------------------+
    | Create green slot         |         | Evaluate canary numbers   |
    | Configure strategy        |  --->   | (3, 5, 15, 42, 97)       |
    | Warm cache                |         | Validate against expected |
    | Run health checks         |         | Abort if 15 != "FizzBuzz" |
    +---------------------------+         +---------------------------+
                                                      |
                                                      v
    Phase 4: CUTOVER                      Phase 3: SHADOW TRAFFIC
    +---------------------------+         +---------------------------+
    | Atomic pointer swap       |         | Duplicate all requests    |
    | (one variable assignment) |  <---   | to blue AND green         |
    | Log 47 events             |         | Compare results           |
    | Fire 3 webhooks           |         | Flag discrepancies        |
    +---------------------------+         +---------------------------+
                |
                v
    Phase 5: BAKE PERIOD                  Phase 6: DECOMMISSION
    +---------------------------+         +---------------------------+
    | Monitor green metrics     |         | Drain blue requests       |
    | Compare against baseline  |  --->   | Archive blue state        |
    | Auto-rollback if degraded |         | gc.collect()              |
    | Configurable duration     |         | "2.4KB reclaimed"         |
    +---------------------------+         +---------------------------+

    ROLLBACK (any phase):
    +---------------------------+
    | Instant traffic revert    |
    | Restore blue state        |
    | Log rollback incident     |
    | Resume blue operations    |
    +---------------------------+
```

**Key components:**
- **DeploymentOrchestrator** - Manages the six-phase deployment lifecycle with phase gates, approval checkpoints, and rollback triggers
- **DeploymentSlot** - Complete, independent FizzBuzz evaluation environment with its own strategy, cache state, and circuit breaker
- **ShadowTrafficRunner** - Duplicates requests to both environments, compares results, and flags discrepancies with diff reports
- **SmokeTestSuite** - Evaluates canary numbers (3, 5, 15, 42, 97) in the target environment and validates results against expected values
- **BakePeriodMonitor** - Monitors the new environment during the bake period, comparing metrics against the baseline with auto-rollback
- **CutoverManager** - Atomically switches the active environment pointer with event logging and state validation
- **RollbackManager** - Instantly reverts traffic to the previous environment with state restoration and incident logging
- **DeploymentDashboard** - ASCII dashboard with environment health comparison, cutover history, shadow traffic diff, and rollback readiness
- **DeploymentMiddleware** - Integrates with the middleware pipeline at priority 55

| Spec | Value |
|------|-------|
| Deployment phases | 6 (Provision, Smoke Test, Shadow, Cutover, Bake, Decommission) |
| Canary numbers | 5 (3, 5, 15, 42, 97) |
| Environment isolation | Full (independent strategy, cache, circuit breaker per slot) |
| Shadow traffic comparison | Exact match required (FizzBuzz results must be identical) |
| Cutover mechanism | Atomic variable assignment (logged as 47 events) |
| Bake period | Configurable duration with accuracy/error-rate thresholds |
| Rollback capability | Instant, from any phase, with full state restoration |
| Decommission strategy | `gc.collect()` + ceremonial resource reclamation report |
| Middleware priority | 55 |
| Custom exceptions | 9 (DeploymentError, SlotProvisioningError, ShadowTrafficError, etc.) |
| Dashboard | ASCII art with environment health, cutover history, and shadow diffs |
| Users impacted by deployment | 0. There is 1 user |

The deployment framework faithfully implements every feature a production blue/green deployment system would need -- environment provisioning, smoke testing, shadow traffic, atomic cutover, bake monitoring, and rollback -- despite the inconvenient fact that both environments contain identical evaluation logic that will produce identical results for identical inputs.

The 73% rollback rate is not a sign of instability; it is a sign that the bake period thresholds are calibrated with the precision of a hair trigger, and the neural network's stochastic weight initialization ensures that no two green environments are exactly alike, even when they compute modulo arithmetic identically.

## Graph Database Architecture

The Graph Database subsystem implements a full in-memory property graph engine that models the hidden social network lurking within the integers 1-100. Because treating numbers as isolated atoms is a relational anti-pattern -- the number 15 doesn't exist in a vacuum, it has relationships: divisible by 3, divisible by 5, classified as FizzBuzz, adjacent to 14 and 16, and sharing a factor with 30, 45, 60, 75, and 90. These relationships have always existed in the mathematics, but nobody thought to formalize them in a graph database until now.

```
    +---+    DIVISIBLE_BY    +---+    CLASSIFIED_AS    +----------+
    | 3 |<------------------| 15 |-------------------->| FizzBuzz |
    +---+                    +---+                      +----------+
      |                        |                             ^
      | EVALUATED_BY           | DIVISIBLE_BY                |
      v                        v                             |
  +--------+               +---+    CLASSIFIED_AS     +------+
  | Rule:3 |               | 5 |-------------------->| Buzz  |
  +--------+               +---+                      +------+
      ^                      ^
      |  SHARES_FACTOR_WITH  |
      +------ (15) ----------+

    CypherLite Query:
    MATCH (n:Number) WHERE n.value > 90 RETURN n ORDER BY n.value LIMIT 5
```

**Key components:**
- **PropertyGraph** - Core graph engine with label indices, adjacency lists, and O(1) neighbor traversal via index-free adjacency
- **Node** - Labeled vertex with property dictionary and outgoing/incoming edge tracking
- **Edge** - Typed, directed relationship with source, target, label, and property dictionary
- **CypherLiteParser** - Recursive descent parser for a simplified Cypher query language supporting MATCH, WHERE, RETURN, ORDER BY, and LIMIT
- **CypherLiteExecutor** - Evaluates parsed query plans against the graph with label filtering, property comparison, and result ordering
- **GraphAnalyzer** - Computes degree centrality (in/out/total), betweenness centrality (shortest-path based), and community detection (label propagation)
- **GraphVisualizer** - Force-directed ASCII layout renderer using spring-embedding, with Unicode box-drawing characters and classification-based node styling
- **GraphDashboard** - ASCII analytics dashboard with centrality rankings, community membership, graph density, and "Most Isolated Number" / "Most Connected Number" awards
- **GraphMiddleware** - IMiddleware implementation (priority 14) that builds graph edges during evaluation, connecting numbers to their rules and classifications in real time
- **populate_graph** - Bulk graph population function that creates Number, Rule, and Classification nodes with DIVISIBLE_BY, SHARES_FACTOR_WITH, EVALUATED_BY, and CLASSIFIED_AS edges

### Node Types

| Label | Properties | What It Represents |
|-------|-----------|-------------------|
| `Number` | value, is_prime, parity, digit_sum | An integer in the evaluation range -- a first-class citizen of the graph |
| `Rule` | divisor, label | A FizzBuzz rule (e.g., divisor=3, label="Fizz") -- the authority that classifies |
| `Classification` | name | A classification outcome (Fizz, Buzz, FizzBuzz, plain) -- the final verdict |

### Edge Types

| Label | Direction | What It Connects |
|-------|----------|-----------------|
| `DIVISIBLE_BY` | Number -> Number | Numbers related by divisibility (15 -> 3, 15 -> 5) |
| `SHARES_FACTOR_WITH` | Number <-> Number | Numbers sharing at least one common factor -- the mathematical buddy system |
| `EVALUATED_BY` | Number -> Rule | Which rule(s) matched during evaluation |
| `CLASSIFIED_AS` | Number -> Classification | The number's ultimate FizzBuzz destiny in graph form |

### CypherLite Query Language

A simplified Cypher dialect, because the full Neo4j query language would require approximately 4,000 more lines and a type system:

| Clause | Support | Example |
|--------|---------|---------|
| `MATCH` | Node pattern with optional label | `MATCH (n:Number)` |
| `WHERE` | Property comparisons (=, !=, >, <, >=, <=) | `WHERE n.value > 50` |
| `RETURN` | Node variable projection | `RETURN n` |
| `ORDER BY` | Property-based sorting (ASC/DESC) | `ORDER BY n.value DESC` |
| `LIMIT` | Result count limitation | `LIMIT 10` |

### Graph Analytics

| Metric | Algorithm | What It Reveals |
|--------|-----------|----------------|
| Degree Centrality | Edge count (in/out/total) | Number 15 is the most connected node because it's divisible by both 3 and 5 |
| Betweenness Centrality | BFS shortest paths | Which numbers sit on the most paths between other numbers -- the "bridges" of the graph |
| Community Detection | Label propagation (iterative) | Confirms that Fizz, Buzz, FizzBuzz, and plain numbers form distinct communities |
| Graph Density | Edge count / possible edges | How interconnected the integer social network actually is |

| Spec | Value |
|------|-------|
| Graph engine | In-memory property graph with index-free adjacency |
| Query language | CypherLite (recursive descent parser) |
| Centrality metrics | 2 (degree, betweenness) |
| Community detection | Label propagation with configurable max iterations |
| Visualization | Force-directed ASCII layout with spring-embedding |
| Middleware priority | 14 |
| Custom exceptions | 1 (`CypherLiteParseError`) |
| Classes | 11 (Node, Edge, PropertyGraph, CypherLiteQuery, CypherLiteParser, CypherLiteExecutor, GraphAnalyzer, GraphVisualizer, GraphDashboard, GraphMiddleware, CypherLiteParseError) |
| Tests | 97 |
| Lines of code | ~1,691 |

The graph database confirms what we always suspected: number 15 is the most important number in FizzBuzz, number 97 is the loneliest prime eating lunch alone in the cafeteria, and the Fizz community and Buzz community are connected through their shared FizzBuzz members like two friend groups linked by mutual acquaintances at a party nobody asked for.

## Genetic Algorithm Architecture

The Genetic Algorithm subsystem implements a complete evolutionary computation framework that treats FizzBuzz rule definitions as organisms competing for survival in a fitness landscape. Because the rules `{3:"Fizz", 5:"Buzz"}` are merely one point in an infinite space of possible `(divisor, label)` mappings, and we owe it to science to explore the alternatives through the most computationally expensive means possible.

```
    Generation 0                    Generation N                    Generation 500
    +------------------+           +------------------+           +------------------+
    | Random rule sets |   --->    | Fitter rule sets |   --->    | {3:"Fizz",       |
    | "7->Wazz"        |  Select   | "3->Bizz"        |  Select   |  5:"Buzz"}       |
    | "11->Pizz"       |  Cross    | "5->Buzz"         |  Cross    |                  |
    | "4->Tazz"        |  Mutate   | "3->Fizz"         |  Mutate   | ...obviously.    |
    | "9->Fuzz"        |           | "7->Jazz"          |           |                  |
    +------------------+           +------------------+           +------------------+

    Fitness Function (5 objectives):
    +-------------------------------------------------------------------+
    |  Coverage    x  Distinctness  x  Phonetic    x  Elegance  x  Surprise  |
    |  (label %)      (unique #)       Harmony        (low div)    (novelty) |
    +-------------------------------------------------------------------+
                              |
                              v
                    Weighted fitness score

    Evolution Pipeline:
    +----------+    +----------+    +-----------+    +----------+    +-----------+
    | EVALUATE |    | SELECT   |    | CROSSOVER |    | MUTATE   |    | ELITISM   |
    | fitness  |--->| tourney  |--->| single-pt |--->| 5 types  |--->| top 5%    |
    | 5 axes   |    | size=5   |    | gene swap |    | shift,   |    | preserved |
    +----------+    +----------+    +-----------+    | swap,    |    +-----------+
                                                      | insert,  |
                                                      | delete,  |
                                                      | shuffle  |
                                                      +----------+

    Mass Extinction Event (when diversity < threshold):
    +------------------+         +------------------+
    | Population: 200  |  --->   | Survivors: 20    |
    | Diversity: 0.02  |  BOOM   | New random: 180  |
    | All look alike   |         | Diversity: reset  |
    +------------------+         +------------------+
```

**Key components:**
- **Gene** - Atomic FizzBuzz rule: `(divisor, label, priority)` -- the fundamental unit of FizzBuzz heredity
- **Chromosome** - Variable-length list of genes encoding a complete FizzBuzz rule set, with crossover and mutation support
- **FitnessScore** - Multi-objective fitness with five weighted criteria (coverage, distinctness, phonetic harmony, elegance, surprise)
- **MarkovLabelGenerator** - Character-level bigram Markov chain trained on seed labels for generating novel phonetically-plausible strings
- **PhoneticScorer** - Consonant-vowel alternation heuristic for label euphony, with bonus for sibilants and penalization for consonant clusters
- **FitnessEvaluator** - Evaluates chromosomes by running their rule sets against numbers 1-1000 and scoring on five axes
- **SelectionOperator** - Tournament selection with configurable tournament size (default: 5)
- **CrossoverOperator** - Single-point crossover on gene lists with offspring validation
- **MutationOperator** - Five mutation types: `divisor_shift`, `label_swap`, `rule_insertion`, `rule_deletion`, `priority_shuffle`
- **HallOfFame** - Persistent top-N tracker with fitness scores, rule sets, and the generation of discovery
- **ConvergenceMonitor** - Population diversity tracking via Hamming distance with mass extinction trigger
- **GeneticAlgorithmEngine** - Main evolutionary loop: initialize, evaluate, select, crossover, mutate, repeat
- **EvolutionDashboard** - ASCII dashboard with fitness-over-generations chart, diversity gauge, Hall of Fame, and live preview

| Spec | Value |
|------|-------|
| Default population | 200 chromosomes |
| Default generations | 500 |
| Elitism | Top 5% preserved unchanged |
| Selection | Tournament (size 5) |
| Crossover | Single-point on gene lists |
| Mutation types | 5 (divisor_shift, label_swap, rule_insertion, rule_deletion, priority_shuffle) |
| Fitness objectives | 5 (coverage, distinctness, phonetic harmony, mathematical elegance, surprise) |
| Mass extinction threshold | Configurable diversity minimum |
| Hall of Fame capacity | Top 10 all-time chromosomes |
| Label generation | Bigram Markov chain trained on {"Fizz", "Buzz", "Jazz", "Wuzz", "Pizz", "Tazz"} |
| Custom exceptions | 8 (GeneticAlgorithmError, ChromosomeValidationError, FitnessEvaluationError, SelectionPressureError, CrossoverIncompatibilityError, MutationError, ConvergenceTimeoutError, PopulationExtinctionError) |
| Classes | 13 (Gene, Chromosome, FitnessScore, MarkovLabelGenerator, PhoneticScorer, FitnessEvaluator, SelectionOperator, CrossoverOperator, MutationOperator, HallOfFame, ConvergenceMonitor, GeneticAlgorithmEngine, EvolutionDashboard) |
| Tests | 86 |
| Lines of code | ~1,358 |

The genetic algorithm faithfully implements every component of evolutionary computation -- population initialization, fitness evaluation, tournament selection, crossover, mutation, elitism, convergence monitoring, and mass extinction events and after hundreds of generations of sophisticated Darwinian competition, the algorithm inevitably converges on `{3:"Fizz", 5:"Buzz"}`: the same rules that were hardcoded in the original 5-line FizzBuzz solution.

This is evolution's greatest achievement: rediscovering the obvious through the most computationally expensive means possible. Darwin would be proud. Or confused. Probably both.

## Natural Language Query Architecture

The Natural Language Query Interface implements a five-stage NLP pipeline that allows users to interrogate the FizzBuzz platform using free-form English sentences -- because memorizing 94 CLI flags is a barrier to adoption and the enterprise user base includes stakeholders who communicate exclusively in nouns and prepositions. The system comprises Tokenization, Intent Classification, Entity Extraction, Query Execution, and Response Formatting, each stage more unnecessary than the last, all built from scratch with zero external NLP dependencies.

```
    User Query (plain English)
    "How many FizzBuzzes are there between 1 and 100?"
                    |
                    v
    +=======================================+
    |           TOKENIZER                    |
    |  Regex-based token classifier          |
    |  Token types: KEYWORD, NUMBER,         |
    |    OPERATOR, PUNCTUATION, UNKNOWN      |
    |  "lexical anomalies" are logged, not   |
    |    errors -- they're opportunities     |
    +=======================================+
                    |
                    v
    +=======================================+
    |       INTENT CLASSIFIER                |
    |  Decision-tree over token patterns     |
    |  5 intents: EVALUATE, COUNT, LIST,     |
    |    STATISTICS, EXPLAIN                 |
    |  Confidence score: 0.0 - 1.0           |
    |  Below 0.6 → ambiguity resolver        |
    +=======================================+
                    |
                    v
    +=======================================+
    |       ENTITY EXTRACTOR                 |
    |  Structured parameter extraction:      |
    |    - Numbers and ranges                |
    |    - Classification filters            |
    |    - Aggregation types                 |
    |    - Sort preferences                  |
    +=======================================+
                    |
                    v
    +=======================================+
    |       QUERY EXECUTOR                   |
    |  Translates structured queries into    |
    |  FizzBuzz service calls:               |
    |    evaluate(), count(), list(),        |
    |    statistics(), explain()             |
    +=======================================+
                    |
                    v
    +=======================================+
    |       RESPONSE FORMATTER               |
    |  Wraps results in natural-language     |
    |  English sentences with metadata:      |
    |    "There are 6 FizzBuzz numbers       |
    |     between 1 and 100."               |
    +=======================================+
                    |
                    v
    Boardroom-Ready Answer
    (with metadata, because raw answers
     lack enterprise gravitas)
```

**Key components:**
- **NLQEngine** - Orchestrates the full tokenize -> classify -> extract -> execute -> format pipeline with confidence gating and session history
- **Tokenizer** - Regex-based lexer producing typed token streams (KEYWORD, NUMBER, OPERATOR, PUNCTUATION, UNKNOWN) from free-form English input
- **IntentClassifier** - Decision-tree classifier mapping token patterns to five query intents (EVALUATE, COUNT, LIST, STATISTICS, EXPLAIN) with confidence scoring
- **EntityExtractor** - Extracts structured query parameters (numbers, ranges, classification filters, aggregation types) from classified token streams
- **QueryExecutor** - Translates structured queries into FizzBuzz service calls and formats results as natural-language responses
- **ResponseFormatter** - Wraps query results in grammatically correct English sentences with contextual phrasing
- **NLQSession** - Query history with sliding-window analytics, intent distribution tracking, and confidence metrics
- **NLQDashboard** - ASCII dashboard with query history, intent distribution, confidence metrics, and "hardest query" leaderboard

### Query Types

| Intent | Example Query | Response Format |
|--------|--------------|-----------------|
| `EVALUATE` | "Is 15 FizzBuzz?" | "Yes, 15 is FizzBuzz (divisible by both 3 and 5)." |
| `COUNT` | "How many Fizzes below 100?" | "There are 27 Fizz numbers between 1 and 100 (excluding FizzBuzz)." |
| `LIST` | "Which numbers between 1 and 30 are Buzz?" | "The Buzz numbers between 1 and 30 are: 5, 10, 20, 25." |
| `STATISTICS` | "What is the most common classification?" | "Classification distribution for 1-100: Plain: 47, Fizz: 27, Buzz: 14, FizzBuzz: 6." |
| `EXPLAIN` | "Why is 9 Fizz?" | "9 is Fizz because it is divisible by 3 (9 / 3 = 3) but not by 5." |

### Token Types

| Token Type | Examples | Purpose |
|-----------|---------|---------|
| `KEYWORD` | "fizz," "buzz," "fizzbuzz," "number," "between," "how many," "which," "is," "list," "count" | Recognized domain vocabulary |
| `NUMBER` | "15," "100," "42" | Integer literals for ranges and targets |
| `OPERATOR` | "greater than," "less than," "equal to," "below," "above" | Comparison and filtering operators |
| `PUNCTUATION` | "?" | Triggers question mode in the intent classifier |
| `UNKNOWN` | Everything else | Logged as "lexical anomalies" -- not errors, but opportunities for vocabulary expansion |

| Spec | Value |
|------|-------|
| Query intents | 5 (EVALUATE, COUNT, LIST, STATISTICS, EXPLAIN) |
| Token types | 5 (KEYWORD, NUMBER, OPERATOR, PUNCTUATION, UNKNOWN) |
| Confidence threshold | 0.6 (configurable) |
| Session history | Sliding window with analytics |
| NLP dependencies | 0 (zero, none, nada -- built from scratch) |
| Custom exceptions | 5 (NLQTokenizationError, NLQIntentClassificationError, NLQEntityExtractionError, NLQExecutionError, NLQUnsupportedQueryError) |
| Tests | 92 |
| Lines of code | ~1,341 |

The Natural Language Query Interface democratizes access to the Enterprise FizzBuzz Platform, extending its reach from the 3 developers who understand the 94 CLI flags to the 0 non-technical stakeholders who have ever wanted to ask a FizzBuzz engine a question in English.

The ambiguity resolver is particularly enterprise-appropriate: instead of guessing what the user meant (which would be helpful), it asks a clarifying question (which preserves audit trail integrity and shifts blame for incorrect results back to the user, where enterprise architects believe it belongs).

The batch mode enables integration with data pipelines, CI/CD systems, and Slack bots, ensuring that FizzBuzz queries can be automated at organizational scale -- because if one person asks "is 15 a FizzBuzz?" at 3am, the answer should be available without waking up the on-call engineer. Bob McFizzington would appreciate the sleep.

## Load Testing Architecture

> **Note:** The Load Testing Framework now lives in `chaos.py`, merged with the Chaos Engineering subsystem during the curation audit. Chaos and load testing are two sides of the same coin: one breaks things on purpose, the other breaks things through volume. Together they form a unified resilience testing capability.

The Load Testing Framework stress-tests the FizzBuzz evaluation pipeline under simulated concurrent workloads, measuring throughput, latency distribution, and identifying bottlenecks -- because you cannot call yourself production-ready if you don't know how many FizzBuzz evaluations per second your system can sustain before the overhead collapses under its own architectural ambitions. The framework spawns configurable pools of **virtual users** (VUs) using `concurrent.futures.ThreadPoolExecutor`, where each VU executes a loop of FizzBuzz evaluation requests against the platform.

```
    ┌─────────────────────────────────────────────────────────┐
    │                  LOAD TEST ENGINE                        │
    │                                                          │
    │  ┌──────────┐  ┌──────────┐       ┌──────────┐          │
    │  │  VU #1   │  │  VU #2   │  ...  │  VU #N   │          │
    │  │(Thread 1)│  │(Thread 2)│       │(Thread N)│          │
    │  └────┬─────┘  └────┬─────┘       └────┬─────┘          │
    │       │              │                  │                │
    │       v              v                  v                │
    │  ┌──────────────────────────────────────────────┐       │
    │  │           FizzBuzz Evaluation Pipeline        │       │
    │  │    (rules_engine → classify → format)         │       │
    │  └──────────────────┬───────────────────────────┘       │
    │                     │                                    │
    │                     v                                    │
    │  ┌──────────────────────────────────────────────┐       │
    │  │            METRICS COLLECTOR                  │       │
    │  │  per-request latency, correctness, errors     │       │
    │  └──────────────────┬───────────────────────────┘       │
    │                     │                                    │
    │       ┌─────────────┼─────────────┐                     │
    │       v             v             v                     │
    │  ┌─────────┐  ┌──────────┐  ┌───────────┐              │
    │  │Latency  │  │Bottleneck│  │Performance│              │
    │  │Histogram│  │Analyzer  │  │  Grader   │              │
    │  │p50-p99  │  │Top 5     │  │  A+ to F  │              │
    │  └─────────┘  └──────────┘  └───────────┘              │
    │                     │                                    │
    │                     v                                    │
    │  ┌──────────────────────────────────────────────┐       │
    │  │          LOAD TEST DASHBOARD                  │       │
    │  │  ASCII histogram, percentile table, grade     │       │
    │  └──────────────────────────────────────────────┘       │
    └─────────────────────────────────────────────────────────┘
```

**Key components:**
- **`LoadGenerator`** - Orchestrates virtual user spawning, workload profile execution, and metric collection with configurable duration and VU count
- **`VirtualUser`** - Thread-based simulated user that executes FizzBuzz evaluations in a loop with configurable think-time between requests
- **`WorkloadProfile`** - Defines VU ramp-up pattern over time: SMOKE, LOAD, STRESS, SPIKE, ENDURANCE with custom schedule support
- **`WorkloadSpec`** - Frozen dataclass specifying VU count, numbers per VU, ramp-up/down timing, and think-time parameters
- **`RequestMetric`** - Per-request measurement capturing latency, result value, correctness, and error information
- **`BottleneckAnalyzer`** - Correlates latency data with subsystem timings and produces ranked bottleneck reports with recommendations
- **`PerformanceGrade`** - A+ to F grading enum for FizzBuzz throughput and latency, because performance without a letter grade is just numbers without judgment
- **`PerformanceReport`** - Aggregates all load test metrics: throughput, latency percentiles (p50/p90/p95/p99), error rate, and grade
- **`LoadTestDashboard`** - Full-screen ASCII results dashboard with latency histogram, throughput metrics, and performance grade

### Workload Profiles

| Profile | VUs | Description |
|---------|-----|-------------|
| SMOKE | 5 | Quick sanity check -- "does it work at all?" |
| LOAD | 50 | Normal operating conditions -- "does it work under typical traffic?" |
| STRESS | 200 | Ramp up until failure -- "at what point does it break?" |
| SPIKE | 500 | Sudden burst at T=60s -- "can it handle everyone urgently needing to know if 42 is Fizz?" |
| ENDURANCE | 30 | Extended duration -- "does it leak memory, exhaust threads, or gradually lose the will to evaluate?" |

### Performance Grading

| Grade | Criteria |
|-------|----------|
| A+ | p99 latency < 1ms, zero errors, throughput exceeds target by 200% |
| A | p99 < 5ms, error rate < 0.1% |
| B | p99 < 10ms, error rate < 1% |
| C | p99 < 50ms, error rate < 5% |
| D | p99 < 100ms, error rate < 10% |
| F | Everything else -- the modulo operator has given up on you |

| Spec | Value |
|------|-------|
| Concurrency model | ThreadPoolExecutor |
| Default workload profiles | 5 (SMOKE, LOAD, STRESS, SPIKE, ENDURANCE) |
| Latency percentiles | p50, p90, p95, p99 |
| Performance grades | 6 (A+ through F) |
| Custom exceptions | 5 (LoadTestConfigurationError, LoadTestTimeoutError, VirtualUserSpawnError, BottleneckAnalysisError, PerformanceGradeError) |
| Tests | 67 |
| Lines of code | ~1,093 |

The Load Testing Framework transforms anecdotal performance impressions into quantified metrics with percentile distributions -- the lingua franca of performance engineering.

The bottleneck analyzer will confirm what everyone suspects (overhead is slow, middleware is slower, modulo takes microseconds) but present it with the gravitas of a formal analysis, complete with recommendations that nobody will follow because removing any subsystem would reduce the line count, and that's the opposite of the project's mission.

The stress test will discover the system's breaking point -- a number that will be prominently displayed on the dashboard as "Maximum Sustainable FizzBuzz Throughput," a metric that no other FizzBuzz implementation in history has ever measured, let alone optimized for.

## Audit Dashboard Architecture

The Unified Audit Dashboard aggregates events from every subsystem in the platform -- blockchain commits, compliance verdicts, SLA violations, auth token grants and denials, chaos fault injections, webhook deliveries, feature flag toggles, circuit breaker state transitions, cache hits and misses, deployment cutover events, pipeline stage completions, and message queue lag alerts -- into a single, continuously updating terminal interface that gives operators complete situational awareness of the FizzBuzz evaluation engine's operational state.

Because the only thing more important than monitoring your FizzBuzz evaluations is monitoring the monitoring of your FizzBuzz evaluations.

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                  UNIFIED AUDIT DASHBOARD                        │
    │                                                                 │
    │  ┌──────────────────────────────────────────────────────────┐   │
    │  │              EVENT STREAM AGGREGATOR                      │   │
    │  │  Subscribes to EventBus → normalizes → UnifiedAuditEvent │   │
    │  │  (timestamp, subsystem, type, severity, correlation_id)  │   │
    │  └──────────────────────┬───────────────────────────────────┘   │
    │                         │                                       │
    │       ┌─────────────────┼──────────────────┐                   │
    │       v                 v                  v                   │
    │  ┌──────────┐   ┌──────────────┐   ┌──────────────┐          │
    │  │ Anomaly  │   │  Temporal    │   │   Event      │          │
    │  │ Detector │   │ Correlator   │   │   Stream     │          │
    │  │(z-score) │   │(correlation  │   │  (NDJSON)    │          │
    │  │          │   │  mining)     │   │              │          │
    │  └────┬─────┘   └──────┬───────┘   └──────────────┘          │
    │       │                │                                       │
    │       v                v                                       │
    │  ┌──────────────────────────────────────────────────────────┐   │
    │  │              MULTI-PANE TERMINAL RENDERER                 │   │
    │  │                                                           │   │
    │  │  ┌─────────────┐ ┌────────────┐ ┌───────────────────┐    │   │
    │  │  │ Live Event  │ │ Throughput │ │  Classification   │    │   │
    │  │  │ Feed (50)   │ │ Gauge +    │ │  Distribution     │    │   │
    │  │  │ color-coded │ │ Sparkline  │ │  Bar Chart        │    │   │
    │  │  └─────────────┘ └────────────┘ └───────────────────┘    │   │
    │  │  ┌─────────────┐ ┌────────────┐ ┌───────────────────┐    │   │
    │  │  │ Subsystem   │ │ Alert      │ │  Event Rate       │    │   │
    │  │  │ Health      │ │ Ticker     │ │  Chart +          │    │   │
    │  │  │ Matrix      │ │ (SLA/Anom) │ │  Anomaly Line     │    │   │
    │  │  └─────────────┘ └────────────┘ └───────────────────┘    │   │
    │  └──────────────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────────────┘
```

**Key components:**
- **`EventAggregator`** - Subscribes to the EventBus via the IObserver interface, normalizes raw events into canonical `UnifiedAuditEvent` records with microsecond timestamps, subsystem attribution, severity classification, and correlation IDs linking the ~23 events generated by a single FizzBuzz evaluation
- **`AnomalyDetector`** - Z-score based anomaly detection over tumbling time windows, computing event rate deviations against a 10-window rolling average and firing `AnomalyAlert` records when the deviation exceeds a configurable threshold (default: 2 standard deviations)
- **`TemporalCorrelator`** - Groups events by correlation ID to discover co-occurrence patterns across subsystems, producing `CorrelationInsight` records with confidence scores -- revealing that chaos faults precede SLA breaches with statistical regularity
- **`EventStream`** - Headless NDJSON exporter that serializes `UnifiedAuditEvent` records to stdout for integration with external log aggregation tools, because structured logging to a terminal is the standard for terminal-based observability
- **`MultiPaneRenderer`** - Renders a six-pane ASCII dashboard: live event feed (50 most recent, color-coded by severity), throughput gauge with 60-second sparkline, classification distribution bar chart, subsystem health matrix (green/yellow/red/gray), alert ticker, and event rate chart with anomaly threshold line
- **`UnifiedAuditDashboard`** - Top-level controller managing event subscription, analytics computation, snapshot capture, and terminal rendering lifecycle with the gravitas of a mission control center

### Dashboard Panes

| Pane | Content |
|------|---------|
| Live Event Feed | Scrolling log of the 50 most recent events, color-coded by severity (DEBUG through CRITICAL), with timestamps and one-line summaries |
| Throughput Gauge | Current evaluations/second as a large ASCII number with a 60-second sparkline history |
| Classification Distribution | Horizontal bar chart showing running counts of Fizz/Buzz/FizzBuzz/plain evaluations in the current session |
| Subsystem Health Matrix | Grid of subsystem names with status indicators derived from per-subsystem error rates in the current 60-second window |
| Alert Ticker | Scrolling one-line banner showing active SLA violations, anomaly alerts, and correlation insights |
| Event Rate Chart | 5-minute ASCII time-series chart of events/second with anomaly threshold line |

| Spec | Value |
|------|-------|
| Event normalization | UnifiedAuditEvent (timestamp, subsystem, type, severity, actor, target, payload, correlation_id) |
| Anomaly detection | Z-score over tumbling windows at configurable granularity |
| Correlation mining | Temporal co-occurrence grouping by correlation ID |
| Dashboard panes | 6 (live feed, throughput, classification, health matrix, alert ticker, event rate) |
| Streaming format | Newline-delimited JSON (NDJSON) |
| Custom exceptions | 6 (AuditDashboardError, EventAggregationError, AnomalyDetectionError, TemporalCorrelationError, EventStreamError, DashboardRenderError) |
| Tests | 87 |
| Lines of code | ~1,160 |

The Audit Dashboard fills the observability gap that existed between individual subsystem metrics and the operator's understanding of how 14+ subsystems interact during a FizzBuzz evaluation.

The correlation detector transforms the dashboard from a passive display into an active diagnostic tool: when the SLA framework fires a breach alert, the correlator can immediately point to the root cause -- usually "chaos engineering injected a fault into the ML forward pass, which cascaded into a blockchain timeout" -- saving operators the effort of manually tracing through 23 correlated events.

The snapshot and replay features enable blameless post-mortems, a practice that enterprise organizations aspire to but rarely achieve because someone always deleted the logs. With the audit dashboard, the logs are normalized, the correlations are pre-computed, and the replay is a single CLI flag away.

## GitOps Architecture

The GitOps Configuration-as-Code Simulator implements a full infrastructure-as-code governance layer for the Enterprise FizzBuzz Platform -- because modifying `config.yaml` by hand and restarting is the operational equivalent of performing surgery without a checklist, and the hot-reload module handles the *how* of configuration delivery but not the *governance* of configuration change. Every configuration mutation passes through a version-controlled, policy-checked, dry-run-tested, approval-gated pipeline before reaching the running system.

```
    +-------------------------------------------------------------------+
    |                    GitOps Configuration Pipeline                   |
    +-------------------------------------------------------------------+
    |                                                                   |
    |  config.yaml    +================+                                |
    |  change    ---> | Change Proposal|                                |
    |                 +================+                                |
    |                        |                                          |
    |                        v                                          |
    |               +------------------+                                |
    |               | 1. Schema        |  types, ranges, required keys  |
    |               |    Validation    |                                |
    |               +--------+---------+                                |
    |                        |                                          |
    |                        v                                          |
    |               +------------------+                                |
    |               | 2. Policy        |  organizational rules          |
    |               |    Engine        |  ("chaos.enabled must be       |
    |               |                  |   false in production")        |
    |               +--------+---------+                                |
    |                        |                                          |
    |                        v                                          |
    |               +------------------+                                |
    |               | 3. Dry-Run       |  shadow evaluator comparison   |
    |               |    Simulation    |  (behavioral change detection) |
    |               +--------+---------+                                |
    |                        |                                          |
    |                        v                                          |
    |               +------------------+                                |
    |               | 4. Approval      |  quorum-based gate             |
    |               |    Gate          |  (auto-approved, team of one)  |
    |               +--------+---------+                                |
    |                        |                                          |
    |                        v                                          |
    |               +------------------+     +-------------------+      |
    |               | 5. Apply         |--->| Config Repository |      |
    |               |    & Commit      |     | (in-memory Git)   |      |
    |               +--------+---------+     +---+---------------+      |
    |                        |                   |                      |
    |                        v                   |  commit chain        |
    |               +------------------+         |  (SHA-256 linked)    |
    |               | Reconciliation   |<--------+                      |
    |               | Loop             |                                |
    |               | (ENFORCE/DETECT) |                                |
    |               +------------------+                                |
    |                        |                                          |
    |                        v                                          |
    |               +------------------+                                |
    |               | Running Platform |  hot-reload propagation        |
    |               | Configuration    |                                |
    |               +------------------+                                |
    +-------------------------------------------------------------------+
```

**Key components:**
- **GitOpsController** - Top-level orchestrator managing the config repository, reconciliation loop, proposal pipeline, and dashboard
- **ConfigRepository** - In-memory Git simulator with commit, branch, merge, diff, log, and revert operations on config trees. Commits are SHA-256 hash-chained in a Merkle-like linked list -- not because we need cryptographic integrity (the blockchain already handles that) but because implementing data structures is the project's raison d'etre
- **ConfigCommit** - Immutable snapshot of configuration state with content hash, parent reference, message, author, and timestamp
- **ConfigBranch** - Named mutable pointer to a commit, supporting branch creation, switching, and deletion
- **ChangeProposalPipeline** - Five-gate pipeline that every config mutation must pass: schema validation, policy engine, dry-run simulation, approval gate, and apply
- **PolicyEngine** - Evaluates organizational policy rules against proposed changes with PASS/FAIL/WARN verdicts. Rules like "blockchain.difficulty must not decrease between commits" ensure that making mining easier is treated as the governance risk it so clearly is
- **DryRunSimulator** - Applies proposed config to a shadow FizzBuzz evaluator, runs numbers 1-30, and flags behavioral changes with a side-by-side diff
- **ApprovalGate** - Collects approvals from operators with configurable quorum. In single-operator mode, proposals are auto-approved because the operator is also the approver, the reviewer, and the on-call engineer
- **ReconciliationLoop** - Continuous or on-demand desired-state vs. actual-state comparison with ENFORCE (auto-correct) and DETECT (alert-only) modes
- **BlastRadiusEstimator** - Analyzes which subsystems are affected by a config change and quantifies impact as a risk score. Changing `blockchain.difficulty` has a blast radius of 1; changing `strategy` has a blast radius of 14
- **GitOpsDashboard** - ASCII dashboard with current branch and commit hash, pending proposals with gate status, drift detection status, and commit history

### In-Memory Git Operations

| Operation | Description | Real Git Equivalent |
|-----------|-------------|---------------------|
| `commit` | Snapshot current config with message and SHA-256 content hash | `git commit` |
| `branch` | Create a named pointer for parallel config experiments | `git branch` |
| `merge` | Three-way merge with conflict detection | `git merge` |
| `diff` | Structural comparison producing added/removed/modified changesets | `git diff` |
| `log` | Chronological list of commits with messages, authors, and hashes | `git log` |
| `revert` | Reset to a previous commit's config state | `git revert` |

### Change Proposal Gate Verdicts

| Gate | What It Checks | Example Failure |
|------|---------------|-----------------|
| Schema Validation | Types, ranges, required keys | `blockchain.difficulty` set to "banana" (must be int in [1, 10]) |
| Policy Engine | Organizational rules | `chaos.enabled` set to true in production environment |
| Dry-Run Simulation | Behavioral impact | ML model accuracy changes because learning rate shifted |
| Approval Gate | Operator quorum | Insufficient approvals (never fails in single-operator mode) |
| Apply | Commit and reconcile | Merge conflict with concurrent config change |

### Reconciliation Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `ENFORCE` | Auto-corrects runtime drift by overwriting with committed values | Production: desired state is the single source of truth |
| `DETECT` | Alerts on drift but does not auto-correct | Staging: visibility without enforcement |

| Spec | Value |
|------|-------|
| Git operations | 6 (commit, branch, merge, diff, log, revert) |
| Proposal gates | 5 (schema, policy, dry-run, approval, apply) |
| Reconciliation modes | 2 (ENFORCE, DETECT) |
| Merge strategies | 3 (ours, theirs, manual) |
| Commit chain integrity | SHA-256 hash-chained (Merkle-like linked list) |
| Policy rule types | Equality, inequality, range, comparison between commits |
| Blast radius metrics | Subsystem count, behavioral change count, risk score |
| Dashboard panes | 5 (branch state, proposals, drift status, apply history, commit log) |
| Custom exceptions | 7 (GitOpsError, GitOpsBranchNotFoundError, GitOpsCommitNotFoundError, GitOpsDriftDetectedError, GitOpsMergeConflictError, GitOpsPolicyViolationError, GitOpsProposalRejectedError) |
| Tests | 79 |
| Lines of code | ~1,424 |

The in-memory Git simulator is the philosophical centerpiece of the GitOps module: it implements version control for configuration inside an application that is already version-controlled by actual Git, creating a recursive layer of version control that would make a category theorist smile.

The blast radius estimator is the cherry on top: quantifying the impact of changing a single YAML value from 4 to 5 as "blast radius: 1 subsystem, 0 behavioral changes, risk: LOW" transforms a trivial config tweak into a governance event with a formal risk assessment -- exactly the kind of ceremony that makes enterprise software feel important. All data structures live in RAM. All commits are lost on process exit. All merges are between branches that one person created. All approvals are self-approvals. This is GitOps at its finest.

## Formal Verification Architecture

The Formal Verification & Proof System brings mathematical rigor to FizzBuzz evaluation -- not because there was ever any doubt that `15 % 3 == 0`, but because empirical evidence is for scientists and the Enterprise FizzBuzz Platform demands proof-theoretic certainty.

### Verification Properties

| Property | What It Proves | Why It Matters |
|----------|---------------|----------------|
| **Totality** | Every integer n >= 1 produces exactly one output | FizzBuzz must never silently drop a number. Silence is a bug |
| **Determinism** | evaluate(n) always returns the same result for the same n | If 15 is FizzBuzz today but Fizz tomorrow, modulo arithmetic has ceased to function |
| **Completeness** | Every classification (Fizz, Buzz, FizzBuzz, identity) is reachable | A FizzBuzz engine that can never produce "Buzz" is just a Fizz engine with a misleading name |
| **Correctness** | Every output matches the specification exactly | The only property that actually needs proving, but the other three are load-bearing ceremony |

### Proof Architecture

```
                    FORMAL VERIFICATION ENGINE
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │   PropertyVerifier                                  │
  │   ├── verify_totality()     → ProofObligation       │
  │   ├── verify_determinism()  → ProofObligation       │
  │   ├── verify_completeness() → ProofObligation       │
  │   └── verify_correctness()  → ProofObligation       │
  │         │                                           │
  │         ▼                                           │
  │   InductionProver                                   │
  │   ├── base_case(n=1)                                │
  │   └── inductive_step(n → n+1)                       │
  │         │   case n%15==0 → FizzBuzz  ✓              │
  │         │   case n%3==0  → Fizz      ✓              │
  │         │   case n%5==0  → Buzz      ✓              │
  │         │   otherwise    → n         ✓              │
  │         ▼                                           │
  │   HoareTriple                                       │
  │   {n > 0} evaluate(n) {result ∈ {Fizz,Buzz,FB,n}}  │
  │         │                                           │
  │         ▼                                           │
  │   ProofTree (Gentzen-style natural deduction)       │
  │         │                                           │
  │         ▼                                           │
  │   VerificationReport + Dashboard                    │
  │         │                                           │
  │         ▼                                           │
  │       ∎ Q.E.D.                                      │
  └─────────────────────────────────────────────────────┘
```

### Proof Tree (Gentzen-Style Natural Deduction)

```
                        ∀n ≥ 1. P(n)
                    ──────────────────────
                   /                      \
            P(1) [base]           P(n) ⊢ P(n+1) [inductive]
               │                        │
               ▼                        ▼
        evaluate(1) = "1"      ┌──── case n%15=0 ────┐
             ✓ QED             │  evaluate(n)="FizzBuzz"
                               │        ✓ QED         │
                               ├──── case n%3=0  ─────┤
                               │  evaluate(n)="Fizz"   │
                               │        ✓ QED         │
                               ├──── case n%5=0  ─────┤
                               │  evaluate(n)="Buzz"   │
                               │        ✓ QED         │
                               └──── otherwise   ─────┘
                                  evaluate(n)=str(n)
                                       ✓ QED
```

### Hoare Logic Triples

Every FizzBuzz evaluation is annotated with Floyd-Hoare triples:

| Precondition | Program | Postcondition |
|-------------|---------|---------------|
| `{n > 0}` | `evaluate(n)` | `{result ∈ {"Fizz", "Buzz", "FizzBuzz", str(n)}}` |
| `{n > 0 ∧ n % 15 == 0}` | `evaluate(n)` | `{result == "FizzBuzz"}` |
| `{n > 0 ∧ n % 3 == 0 ∧ n % 5 ≠ 0}` | `evaluate(n)` | `{result == "Fizz"}` |
| `{n > 0 ∧ n % 5 == 0 ∧ n % 3 ≠ 0}` | `evaluate(n)` | `{result == "Buzz"}` |
| `{n > 0 ∧ n % 3 ≠ 0 ∧ n % 5 ≠ 0}` | `evaluate(n)` | `{result == str(n)}` |

| Component | Count |
|-----------|-------|
| Properties verified | 4 (totality, determinism, completeness, correctness) |
| Proof techniques | 2 (structural induction, Hoare logic) |
| CLI flags | 4 (--verify, --verify-property, --proof-tree, --verify-dashboard) |
| Tests | 76 |
| Lines of code | ~1,400 |

The formal verification engine proves FizzBuzz correct for all natural numbers up to the configurable proof depth -- or until the heat death of the universe, whichever comes first. Four properties are verified against a StandardRuleEngine ground truth oracle, each generating a proof obligation that must be discharged before the property is considered proven.

The proof tree is rendered in Gentzen-style natural deduction notation with ASCII art, because a proof without visual representation is just an assertion wearing a tuxedo. The VerificationDashboard displays QED status indicators for each property alongside the full proof tree, providing the same warm feeling of mathematical certainty that Euclid experienced -- but for modulo arithmetic, and in a terminal.

## FBaaS Architecture

FizzBuzz-as-a-Service (FBaaS) transforms the Enterprise FizzBuzz Platform from a CLI tool into a fully simulated multi-tenant SaaS platform -- complete with subscription management, usage-based billing, tenant isolation, and a simulated Stripe integration that processes payments in an in-memory ledger that vanishes when the process exits. Because offering modulo arithmetic as a cloud service is the logical next step in enterprise evolution.

```
                              +=====================+
                              |   FBaaS Platform     |
                              +=====================+
                                        |
              +-------------------------+-------------------------+
              |                         |                         |
    +================+       +==================+      +===================+
    | TenantManager  |       |   UsageMeter     |      | FizzStripeClient  |
    | CRUD lifecycle |       | Per-tenant daily  |      | Simulated Stripe  |
    | API key gen    |       | quota tracking    |      | charges, refunds, |
    | suspend/react. |       | overage detection |      | subscriptions     |
    +================+       +==================+      +===================+
              |                         |                         |
              +-------------------------+-------------------------+
                                        |
                              +==================+
                              |  BillingEngine   |
                              | Subscription     |
                              | lifecycle mgmt   |
                              | Overage billing  |
                              +==================+
                                        |
              +-------------------------+-------------------------+
              |                                                   |
    +====================+                          +=====================+
    |  FBaaSMiddleware   |                          |  OnboardingWizard   |
    | Priority: -1       |                          | ASCII welcome flow  |
    | Quota enforcement  |                          | Tier display        |
    | Feature gates      |                          | API key reveal      |
    | Free-tier watermark|                          | ToS acceptance      |
    +====================+                          +=====================+
              |
              v
    +====================+
    |  FBaaSDashboard    |
    | MRR tracking       |
    | Tenant list        |
    | Usage metrics      |
    | Billing event log  |
    +====================+

    Subscription Tiers:
    +-------------+------------+-----------+---------------------------+
    | Tier        | Quota/Day  | Price/Mo  | Features                  |
    +-------------+------------+-----------+---------------------------+
    | FREE        | 10         | $0.00     | standard only, watermark  |
    | DEVELOPER   | 500        | $9.99     | +chain, caching           |
    | PROFESSIONAL| 1,000      | $29.99    | +async, tracing, flags    |
    | ENTERPRISE  | unlimited  | $999.99   | ALL features, ML, chaos,  |
    |             |            |           |  blockchain, compliance   |
    +-------------+------------+-----------+---------------------------+
```

| Spec | Value |
|------|-------|
| Module | `enterprise_fizzbuzz/infrastructure/billing.py` (consolidated from fbaas.py) |
| Subscription tiers | 4 (Free, Developer, Professional, Enterprise) |
| Tenant lifecycle states | 3 (Active, Suspended, Deactivated) |
| Feature gates per tier | Free: 1, Developer: 3, Professional: 6, Enterprise: 10 |
| Daily quotas | Free: 10, Developer: 500, Professional: 1,000, Enterprise: unlimited |
| Simulated Stripe operations | charge, subscribe, refund |
| Custom exceptions | 7 (FBaaSError, TenantNotFoundError, FBaaSQuotaExhaustedError, TenantSuspendedError, FeatureNotAvailableError, BillingError, InvalidAPIKeyError) |
| CLI flags | 7 (--fbaas, --fbaas-tenant, --fbaas-tier, --fbaas-dashboard, --fbaas-onboard, --fbaas-billing-log, --fbaas-usage) |
| Tests | 87 |
| Lines of code | ~1,031 |

The FBaaS platform wraps every evaluation in a tenant context via `FBaaSMiddleware` at pipeline priority -1 (before even the Secrets Vault), enforcing daily evaluation quotas, subscription-tier feature gates, and the Free-tier watermark that brands every result with `[Powered by FBaaS Free Tier]` until the tenant discovers the $29.99/month path to dignity.

The `FizzStripeClient` processes charges by appending JSON to a Python list, achieving the same billing fidelity as actual Stripe with none of the PCI compliance overhead. The `OnboardingWizard` renders a ceremonial ASCII welcome flow that makes every new tenant feel like they've just signed an enterprise contract -- even though the "contract" is a function call and the "enterprise" is a modulo operation.

The `FBaaSDashboard` renders MRR tracking, per-tenant usage, and billing event logs in box-drawing characters, providing the Stripe Dashboard experience without the Stripe, the dashboard, or the revenue. No actual HTTP. No actual payments. No actual cloud infrastructure. Maximum ceremony.

## Time-Travel Debugger Architecture

The Time-Travel Debugger treats the FizzBuzz evaluation history as a navigable temporal dimension, allowing engineers to step forwards and backwards through every evaluation, set conditional breakpoints, diff arbitrary snapshots, and visualize the timeline -- because debugging modulo arithmetic without the ability to rewind time is a limitation that no enterprise platform should tolerate.

```
                    Evaluation Pipeline
                           |
                           v
              +========================+
              |  TimeTravelMiddleware  |  (priority -5)
              |  captures snapshot     |
              |  after each evaluation |
              +========================+
                           |
                           v
              +========================+
              |       Timeline         |
              |  [snap₀][snap₁]...[snapₙ]
              |   append-only, O(1)    |
              |   random access        |
              +========================+
                     |           |
                     v           v
         +================+  +================+
         | TimelineNavigator |  | BreakpointEngine |
         |  step_forward   |  |  compile(expr)   |
         |  step_back      |  |  evaluate(snap)  |
         |  goto(n)        |  |  field-path       |
         |  continue_fwd   |  |  access           |
         |  reverse_continue|  +================+
         +================+
                     |
                     v
         +================+     +================+
         |   DiffViewer   |     |   TimelineUI   |
         |  compare(a, b) |     |  render_strip() |
         |  field-by-field |     |  markers: B > ! |
         |  ASCII side-by- |     |  scrollable     |
         |  side rendering |     +================+
         +================+

    Every snapshot is sealed with SHA-256 integrity hash.
    Tampering triggers SnapshotIntegrityError.
```

**Key components:**
- **EvaluationSnapshot** - Frozen dataclass capturing the complete evaluation state (number, classification, strategy, latency, cache state, circuit breaker status, middleware effects, feature flags) sealed with a SHA-256 cryptographic integrity hash -- because trust is earned through hashing, not assumed through good intentions
- **Timeline** - Ordered, append-only collection of snapshots with O(1) random access by sequence index, configurable capacity limits, and automatic oldest-snapshot eviction when the timeline fills up -- because even immortalized modulo results cannot live forever
- **ConditionalBreakpoint** - Expression evaluator supporting field-path access (e.g., `classification == FizzBuzz`, `number > 50`, `latency > 1.0`) with compile-time validation, because stepping through 10,000 evaluations one by one is a punishment that not even enterprise software deserves
- **TimelineNavigator** - Bidirectional cursor over the timeline with step_forward, step_back, goto, continue_to_breakpoint, and reverse_continue operations -- the temporal VCR of modulo debugging
- **DiffViewer** - Field-by-field comparison of any two snapshots with ASCII side-by-side rendering and change highlighting, answering "what changed?" with forensic precision
- **TimelineUI** - ASCII timeline strip with markers for breakpoints (B), current cursor position (>), and detected anomalies (!) -- temporal debugging with visual flair
- **TimeTravelMiddleware** - IMiddleware implementation at priority -5 that captures a snapshot after every evaluation, ensuring the timeline stays current without modifying the core pipeline

| Spec | Value |
|------|-------|
| Snapshot storage | Append-only timeline with O(1) random access |
| Integrity verification | SHA-256 hash per snapshot |
| Breakpoint expressions | Field-path equality, comparison, and membership operators |
| Navigation operations | 6 (step_forward, step_back, goto, continue, reverse_continue, continue_to_breakpoint) |
| Diff output | ASCII side-by-side with field-level change detection |
| Middleware priority | -5 (before vault, before everything) |
| Custom exceptions | 5 (TimeTravelError, TimelineEmptyError, TimelineNavigationError, BreakpointSyntaxError, SnapshotIntegrityError) |
| Module size | ~1,166 lines |
| Test count | 82 |

The middleware runs at priority -5, making it the first observer of every evaluation -- before the vault ceremony, before compliance, before cost tracking. By the time the FizzBuzz result reaches the user, its snapshot has already been SHA-256-sealed and committed to the timeline, ready for temporal navigation by future debuggers who will wonder why evaluation #42 took 0.3ms longer than evaluation #41. The answer is always the blockchain. It's always the blockchain.

## Bytecode VM Architecture

The Custom Bytecode Virtual Machine (FBVM) implements a complete compilation and execution pipeline for FizzBuzz rule evaluation -- because running `n % 3 == 0` through CPython's general-purpose `BINARY_MODULO` opcode was an unacceptable waste of a general-purpose programming language. The FBVM replaces one Python opcode with approximately 1,450 lines of virtual machine infrastructure, achieving the same result slower but with significantly more architectural satisfaction.

```
    RuleDefinition[]                       result (str)
         |                                     ^
         v                                     |
    +============+                      +============+
    |   FBVM     |  BytecodeProgram     |  FizzBuzz  |
    |  Compiler  | ------------------->|     VM      |
    +============+                      +============+
         |                                     |
         v                                     v
    +============+                      +============+
    |  Peephole  |                      |  VMState   |
    | Optimizer  |                      | (registers,|
    +============+                      |  flags,    |
         |                              |  stacks)   |
         v                              +============+
    +============+     +============+
    | Disassembler|    | Serializer |
    +============+     | (.fzbc)    |
         |             +============+
         v
    Human-readable
    listing
```

### Instruction Set Architecture (ISA)

The FBVM defines 20 opcodes, each encoded as a single byte, giving a theoretical capacity of 256 instructions -- of which 236 are reserved for future enterprise requirements such as computing FizzBuzz in Roman numerals or evaluating divisibility using blockchain consensus.

| Opcode | Hex | Category | Description |
|--------|-----|----------|-------------|
| `LOAD_NUM` | `0x01` | Data Movement | Load an immediate integer into a register |
| `LOAD_N` | `0x02` | Data Movement | Load the current evaluation number (N) into a register |
| `MOV` | `0x03` | Data Movement | Copy value from one register to another |
| `MOD` | `0x04` | Arithmetic | Compute `reg_a % reg_b`, store result in `reg_a` |
| `ADD` | `0x05` | Arithmetic | Compute `reg_a + reg_b`, store result in `reg_a` |
| `SUB` | `0x06` | Arithmetic | Compute `reg_a - reg_b`, store result in `reg_a` |
| `CMP_ZERO` | `0x07` | Comparison | Set zero flag if register value == 0 |
| `CMP_EQ` | `0x08` | Comparison | Set zero flag if `reg_a == reg_b` |
| `JUMP` | `0x10` | Control Flow | Unconditional jump to address |
| `JUMP_IF_ZERO` | `0x11` | Control Flow | Jump to address if zero flag is set |
| `JUMP_IF_NOT_ZERO` | `0x12` | Control Flow | Jump to address if zero flag is NOT set |
| `PUSH_LABEL` | `0x20` | Label/Result | Push a string label onto the label stack |
| `CONCAT_LABELS` | `0x21` | Label/Result | Concatenate all labels on the label stack |
| `EMIT_RESULT` | `0x22` | Label/Result | Emit the final result (label stack or number as string) |
| `CLEAR_LABELS` | `0x23` | Label/Result | Clear the label stack |
| `PUSH` | `0x30` | Stack | Push register value onto data stack |
| `POP` | `0x31` | Stack | Pop data stack into register |
| `NOP` | `0xFD` | System | No operation (placeholder for optimized-away instructions) |
| `TRACE` | `0xFE` | System | Emit a trace event with a message |
| `HALT` | `0xFF` | System | Stop execution (every VM needs a HALT) |

### Compilation Pipeline

The compiler translates `RuleDefinition` objects into FBVM bytecode in three phases:

1. **Code Generation** -- Emits instructions for each rule: `LOAD_N` into a register, `LOAD_NUM` the divisor into another, `MOD` to compute the remainder, `CMP_ZERO` to check divisibility, `JUMP_IF_NOT_ZERO` to skip the label push, and `PUSH_LABEL` with the rule's label. After all rules, `CONCAT_LABELS` merges any accumulated labels, `EMIT_RESULT` produces the final output, and `HALT` stops execution
2. **Label Resolution** -- Resolves symbolic jump targets to concrete instruction addresses, because forward references are the universal headache of every assembler ever written
3. **Peephole Optimization** -- Eliminates redundant instructions: consecutive NOPs are collapsed, dead code after HALT is removed, and redundant register loads are eliminated. The optimizer makes the bytecode marginally smaller and zero nanoseconds faster, but it demonstrates compiler theory knowledge that would otherwise go tragically unused

### Execution Engine

The VM uses a classic fetch-decode-execute loop with:

- **8 general-purpose registers** (R0-R7) -- more than enough for modulo arithmetic, which needs approximately 2
- **A zero flag** -- set by comparison instructions, consumed by conditional jumps
- **A label stack** -- accumulates classification labels ("Fizz", "Buzz") for concatenation
- **A data stack** -- general-purpose value stack for complex computations (never actually needed for FizzBuzz, but architecturally essential)
- **A program counter** -- the only register that actually matters
- **Cycle counting** -- every instruction increments a cycle counter, with a configurable limit to prevent infinite loops caused by bad bytecode or existential indecision

### Serialization Format

Compiled programs can be saved and loaded in `.fzbc` format -- a proprietary binary format featuring:
- A `FZBC` magic header (because every self-respecting binary format starts with 4 bytes of personality)
- JSON-encoded instruction payloads (because true binary encoding would require more effort than this feature deserves)
- Base64 transport encoding for safe storage

This is the project's fourth proprietary file format, joining `.fizztranslation` (i18n), the blockchain ledger format, and the vault audit log. File format proliferation is a sign of enterprise maturity.

| Spec | Value |
|------|-------|
| Opcodes | 20 (236 reserved for future overengineering) |
| Registers | 8 general-purpose (R0-R7) |
| Compiler phases | 3 (code generation, label resolution, peephole optimization) |
| Peephole optimizations | 3 (NOP elimination, dead code removal, redundant load elimination) |
| Serialization format | `.fzbc` with `FZBC` magic header |
| Cycle limit | Configurable (default: 10,000) |
| Custom exceptions | 4 (BytecodeCompilationError, BytecodeExecutionError, BytecodeCycleLimitError, BytecodeSerializationError) |
| CLI flags | 4 (`--vm`, `--vm-disasm`, `--vm-trace`, `--vm-dashboard`) |
| Module size | ~1,450 lines |
| Test count | 90 |
| Performance vs. CPython | Slower. Guaranteed. By design. |

The FBVM achieves what no other FizzBuzz implementation has dared: replacing a single Python expression (`n % 3 == 0`) with a full compilation pipeline, instruction set, register file, execution engine, optimizer, disassembler, serializer, and dashboard. Computer scientists spent decades designing instruction sets for general computation; we spent an afternoon designing one for divisibility checks.

The result is approximately 725x more code than necessary, but every opcode is correct, every register is accounted for, and every cycle is counted. This is what peak enterprise bytecode looks like.

## Query Optimizer Architecture

The Query Optimizer is a PostgreSQL-inspired cost-based query planner that treats every FizzBuzz evaluation as a query requiring plan selection, cost estimation, and execution strategy optimization -- because computing `n % 3 == 0` without first generating alternative execution plans, estimating their costs via a statistical model, caching the winner in an LRU plan cache, and rendering a PostgreSQL-style EXPLAIN ANALYZE output is simply not enterprise-grade.

### How It Works

```
  Input: n=15
      |
      v
  +-------------------+
  | Plan Enumerator   |  Generates all valid execution plans
  |  - ModuloScan     |  (CacheLookup -> ModuloScan -> ComplianceGate -> Emit,
  |  - CacheLookup    |   MLInference -> ComplianceGate -> Emit,
  |  - MLInference    |   CacheLookup -> BlockchainVerify -> Emit, ...)
  |  - ComplianceGate |
  |  - BlockchainVerify|
  |  - ResultMerge    |
  +-------------------+
          |
          v
  +-------------------+
  | Cost Model        |  Estimates cost per plan using:
  |  - CPU weight     |   - Historical cache hit rates
  |  - Cache weight   |   - ML inference latency
  |  - ML weight      |   - Compliance overhead
  |  - Compliance wt  |   - Blockchain verification cost
  |  - Blockchain wt  |
  +-------------------+
          |
          v
  +-------------------+
  | Plan Selection    |  Picks cheapest plan, applies optimizer hints,
  |  - Branch & Bound |  checks plan cache for previously optimal plans
  |  - Hint Override  |
  |  - Plan Cache     |
  +-------------------+
          |
          v
  +-------------------+
  | EXPLAIN Output    |  FizzBuzz Evaluation Plan (n=15, cost: 0.42 FB$)
  |                   |  -> CacheLookup (cost: 0.01, hit prob: 0.73)
  |                   |     -> ModuloScan (cost: 0.02, strategy: standard)
  |                   |        -> ComplianceGate (cost: 0.15, regimes: SOX, GDPR)
  |                   |           -> EmitResult (cost: 0.00)
  +-------------------+
```

### Plan Node Types

The optimizer considers eight plan node types, each representing a stage in the FizzBuzz evaluation pipeline:

| Node Type | Description | Estimated Cost |
|-----------|-------------|----------------|
| `MODULO_SCAN` | Direct modulo evaluation via the rule engine | 0.02 FB$ |
| `CACHE_LOOKUP` | Check the in-memory cache for a pre-computed result | 0.01 FB$ |
| `ML_INFERENCE` | Invoke the neural network for classification | 0.42 FB$ |
| `COMPLIANCE_GATE` | SOX/GDPR/HIPAA compliance checks | 0.15 FB$ |
| `BLOCKCHAIN_VERIFY` | Mine a block to verify the result | 0.18 FB$ |
| `RESULT_MERGE` | Merge results from multiple strategies | 0.03 FB$ |
| `FILTER` | Filter intermediate results by predicate | 0.005 FB$ |
| `MATERIALIZE` | Materialize intermediate results for reuse | 0.01 FB$ |

### Cost Model

The cost model uses five configurable weights to estimate total plan cost:

- **CPU weight** (default 1.0) -- base computation cost
- **Cache weight** (default 0.8) -- cache lookup overhead (often negative when hits save downstream work)
- **ML weight** (default 2.0) -- neural network inference cost (always the most expensive, always the least necessary)
- **Compliance weight** (default 1.5) -- regulatory overhead per active regime
- **Blockchain weight** (default 1.8) -- proof-of-work verification cost

The StatisticsCollector feeds empirical data into the model: cache hit rates, ML accuracy, per-strategy latencies, and compliance overhead measurements. The model then selects the plan with the lowest estimated total cost -- which is invariably "just do the modulo," a conclusion that 1,215 lines of optimizer code reaches with the same confidence as a human reading the problem statement.

### Optimizer Hints

Like PostgreSQL's `pg_hint_plan` extension, optimizer hints allow the operator to override the cost model's judgment:

| Hint | Effect |
|------|--------|
| `FORCE_ML` | Require the ML inference path regardless of cost |
| `PREFER_CACHE` | Bias toward cache-first plans (optimistic caching) |
| `NO_BLOCKCHAIN` | Exclude blockchain verification from all plans |
| `NO_ML` | Exclude ML inference from all plans |

Contradictory hints (`FORCE_ML` + `NO_ML`) raise an `InvalidHintError`, because the optimizer has limits and logical consistency is one of them.

| Spec | Value |
|------|-------|
| Plan node types | 8 (ModuloScan, CacheLookup, MLInference, ComplianceGate, BlockchainVerify, ResultMerge, Filter, Materialize) |
| Optimizer hints | 4 (FORCE_ML, PREFER_CACHE, NO_BLOCKCHAIN, NO_ML) |
| Cost model weights | 5 (cpu, cache, ml, compliance, blockchain) |
| EXPLAIN modes | 2 (EXPLAIN, EXPLAIN ANALYZE) |
| Custom exceptions | 5 (QueryOptimizerError, PlanGenerationError, CostEstimationError, PlanCacheOverflowError, InvalidHintError) |
| CLI flags | 5 (`--optimize`, `--explain`, `--explain-analyze`, `--optimizer-hints`, `--optimizer-dashboard`) |
| Module size | ~1,215 lines |
| Test count | 88 |
| Performance vs. direct modulo | Slower. The optimizer spends more time selecting the optimal plan than the plan takes to execute. This is by design. |

PostgreSQL uses its query optimizer to select among hash joins, merge joins, nested loops, and index scans across billions of rows. Enterprise FizzBuzz uses its query optimizer to select among two modulo operations, a cache lookup, and a neural network inference across one number. The architecture diagrams are indistinguishable. The utility is not.

## Paxos Consensus Architecture

The Paxos module implements Leslie Lamport's Multi-Decree Paxos consensus protocol for distributed agreement on FizzBuzz classifications. Because computing `n % 3 == 0` on a single machine is a single point of truth, and single points of truth are single points of failure.

### Protocol Phases

```
Phase 1a: PREPARE
  Proposer selects a ballot number b and sends PREPARE(b) to all Acceptors.
  "I would like to propose a value. Is anyone else already proposing?"

Phase 1b: PROMISE
  If ballot b > any previously promised ballot, Acceptor responds PROMISE(b, previously_accepted_value).
  "I promise to ignore any proposal with a lower ballot number. Here's what I've accepted so far (if anything)."

Phase 2a: ACCEPT
  If Proposer receives PROMISE from a majority (quorum), it sends ACCEPT(b, value) to all Acceptors.
  The value is either the highest-numbered previously accepted value, or the Proposer's own proposal.
  "The quorum has spoken. Please accept this value."

Phase 2b: ACCEPTED
  If ballot b >= any previously promised ballot, Acceptor accepts and broadcasts ACCEPTED(b, value).
  "I have accepted this value. Let the Learners know."

Learn:
  Learner collects ACCEPTED messages. Once a majority of Acceptors have accepted the same value
  for the same decree, the value is CHOSEN -- permanently, irrevocably, consensually.
  "Consensus reached. The parliament has decreed that 15 is FizzBuzz."
```

### Cluster Topology

```
+--------------------------------------------------------------------+
|                        PAXOS CLUSTER (5 nodes)                      |
|                                                                     |
|  +------------+  +------------+  +------------+  +------------+    |
|  |  Node 0    |  |  Node 1    |  |  Node 2    |  |  Node 3    |    |
|  |  Standard  |  |  Chain     |  |  ML        |  |  Genetic   |    |
|  |            |  |            |  |  (may lie)  |  |  Algorithm |    |
|  | Proposer   |  | Proposer   |  | Proposer   |  | Proposer   |    |
|  | Acceptor   |  | Acceptor   |  | Acceptor   |  | Acceptor   |    |
|  | Learner    |  | Learner    |  | Learner    |  | Learner    |    |
|  +-----+------+  +-----+------+  +-----+------+  +-----+------+    |
|        |               |               |               |            |
|  +-----+---------------+---------------+---------------+------+     |
|  |                    PAXOS MESH                              |     |
|  |         In-memory message bus with partition sim           |     |
|  +-----+------------------------------------------------------+     |
|        |                                                            |
|  +-----+------+                                                     |
|  |  Node 4    |                                                     |
|  |  Functional|                                                     |
|  | Proposer   |                                                     |
|  | Acceptor   |                                                     |
|  | Learner    |                                                     |
|  +------------+                                                     |
+--------------------------------------------------------------------+
```

### Byzantine Fault Tolerance

In Byzantine mode, one or more nodes may produce incorrect evaluation results -- the ML engine occasionally claims 15 is "Fizz" instead of "FizzBuzz," the Genetic Algorithm mutates results, or the Chaos Engineering module corrupts messages. The ByzantineFaultInjector deliberately injects incorrect classifications to test the cluster's fault tolerance. With 3f+1 nodes, the cluster tolerates f Byzantine faults and still reaches correct consensus, because honest nodes outvote liars.

### Consensus Dashboard Example

```
+==============================================================+
|            PAXOS CONSENSUS DASHBOARD                          |
+==============================================================+
|                                                               |
| Decree #42 (n=15):  CONSENSUS REACHED -> FizzBuzz            |
| +--------+----------+----------+---------+                    |
| | Node   | Strategy | Vote     | Status  |                   |
| +--------+----------+----------+---------+                    |
| | node-0 | Standard | FizzBuzz | Learned |                   |
| | node-1 | Chain    | FizzBuzz | Learned |                   |
| | node-2 | ML       | Fizz(?)  | Outvoted|                   |
| | node-3 | Genetic  | FizzBuzz | Learned |                   |
| | node-4 | Func     | FizzBuzz | Learned |                   |
| +--------+----------+----------+---------+                    |
| Quorum: 4/5  |  Ballot: 7  |  Round-trips: 3                |
| Byzantine faults detected: 1  |  Consensus: VALID            |
+===============================================================+
```

### Specifications

| Spec | Value |
|------|-------|
| Protocol | Multi-Decree Paxos (Synod) with Byzantine Fault Tolerance extension |
| Message types | 5 (PREPARE, PROMISE, ACCEPT, ACCEPTED, NACK) |
| Paxos roles | 3 per node (Proposer, Acceptor, Learner) |
| Default cluster size | 5 nodes (configurable, minimum 3) |
| Quorum requirement | Majority (floor(n/2) + 1) |
| Byzantine tolerance | f faults with 3f+1 nodes |
| Custom exceptions | 6 (PaxosError, BallotRejectedError, QuorumNotReachedError, ConsensusTimeoutError, NetworkPartitionError, ByzantineFaultDetectedError) |
| CLI flags | 6 (`--paxos`, `--paxos-nodes`, `--paxos-byzantine`, `--paxos-partition`, `--paxos-show-votes`, `--paxos-dashboard`) |
| Module size | ~1,343 lines |
| Test count | 82 |
| Performance vs. single-node | 5x slower (one consensus round per evaluation). Leslie Lamport won a Turing Award for this. We are using it for FizzBuzz. |

The Hot-Reload module implements Raft consensus -- for a single node. The Paxos module implements Paxos consensus -- for five nodes. Together, they provide two different distributed consensus algorithms for two different non-problems, achieving the rare architectural distinction of solving zero real problems with two provably correct protocols. Variety is the spice of distributed systems.

## Quantum Computing Architecture

The Quantum module implements a full state-vector quantum computer simulator with a simplified Shor's algorithm adaptation for FizzBuzz divisibility checking. Because the modulo operator was too fast, too reliable, and too boring -- and the platform needed a way to compute `n % 3` that is approximately 10^14 times slower while producing identical results with lower confidence.

### Quantum Circuit for Divisibility

```
Classical: n % 3 == 0  →  True/False  (1 CPU cycle, deterministic)

Quantum:
q0: ──[H]──[*]────────────[QFT†]──[M]──┐
q1: ───────[X]──[H]───────[QFT†]──[M]──┤
q2: ──[H]───────[*]───────[QFT†]──[M]──├──→ Period r → Divisibility
q3: ────────────[X]───────[QFT†]──[M]──┤
q4: ──[H]──[FIZZ_ORACLE]──[QFT†]──[M]──┘
     (2^n operations, probabilistic, requires majority voting)
```

### Shor's Algorithm Adaptation

Instead of factoring large integers (which would be useful), the simulator uses Shor's period-finding algorithm to determine the period of `f(x) = a^x mod N` where N is 3, 5, or 15. The Quantum Fourier Transform extracts the period from the quantum state, and divisibility is inferred from the period.

The quantum approach provides a fundamentally different computational model for divisibility checking, leveraging quantum parallelism to explore the solution space simultaneously.

### Decoherence Model

```
+------------------------------------------------------------------+
|                    DECOHERENCE SIMULATION                         |
+------------------------------------------------------------------+
|                                                                   |
|  Noise Rate: 0.05 (5% error probability per gate)                |
|                                                                   |
|  Bit-flip errors (X noise):  ████░░░░░░  12 events               |
|  Phase-flip errors (Z noise): ███░░░░░░░   8 events              |
|  Measurement collapses:       █████████░  47 events               |
|                                                                   |
|  At noise rate 1.0, the simulator is indistinguishable from       |
|  random.choice(["Fizz", "Buzz", "FizzBuzz", n]).                  |
|  This is physically accurate.                                     |
+------------------------------------------------------------------+
```

### Quantum Dashboard Example

```
+==============================================================+
|            QUANTUM COMPUTING DASHBOARD                        |
+==============================================================+
|                                                               |
|  Register: 8 qubits  |  State vector: 256 amplitudes         |
|  Circuit depth: 47    |  Total gates: 142                     |
|                                                               |
|  Gate breakdown:                                              |
|    Hadamard (H):    32  |  CNOT:       28  |  Phase (S): 18  |
|    Pauli-X:         12  |  Toffoli:     8  |  QFT:        4  |
|    FIZZ_ORACLE:      3  |  Measurement: 24 |  Other:     13  |
|                                                               |
|  Measurement histogram (n=15, 100 shots):                     |
|    FizzBuzz: ████████████████████████████████████████  92%     |
|    Fizz:     ███                                       4%     |
|    Buzz:     ██                                        3%     |
|    15:       █                                         1%     |
|                                                               |
|  Quantum Advantage Ratio: -1.47 × 10^14                      |
|  (negative means classical is faster. it is always negative)  |
|                                                               |
|  Classical time:  0.000001 ms                                 |
|  Quantum time:    147.382 ms                                  |
|  Speedup: you are reading this correctly. it is slower.       |
+===============================================================+
```

### Specifications

| Spec | Value |
|------|-------|
| Simulation model | Full state-vector (2^n complex amplitudes) |
| Default qubits | 8 (sufficient for FizzBuzz up to 255) |
| Maximum qubits | 16 (65,536 amplitudes, Python begins to weep) |
| Gate library | 10+ gates (H, X, Y, Z, CNOT, Toffoli, S, T, controlled-U, FIZZ_ORACLE) |
| Algorithm | Simplified Shor's period-finding adapted for divisibility |
| Measurement | Born rule probabilistic sampling with majority voting |
| Decoherence | Configurable bit-flip and phase-flip noise (0.0 to 1.0) |
| Custom exceptions | 5 (QuantumError, QuantumDecoherenceError, QuantumCircuitError, QuantumMeasurementError, QuantumAdvantageMirage) |
| CLI flags | 6 (`--quantum`, `--quantum-qubits`, `--quantum-shots`, `--quantum-noise`, `--quantum-circuit`, `--quantum-dashboard`) |
| Module size | ~1,360 lines |
| Test count | 96 |
| Performance vs. classical modulo | ~10^14x slower. The Quantum Advantage Ratio is always negative. This is by design. The simulator faithfully reproduces the key property of quantum computing: it is slower than classical for trivial problems, but with much more impressive ASCII diagrams. |

Shor's algorithm was published in 1994 and threatens the security of RSA encryption. Enterprise FizzBuzz uses it to check if 15 is divisible by 3. Peter Shor did not respond to our request for comment.

## Cross-Compiler Architecture

The Cross-Compiler module transpiles FizzBuzz rule definitions into standards-compliant C, Rust, and WebAssembly Text format via a seven-opcode Intermediate Representation. Because the modulo operator was trapped inside CPython, accessible only to people who know what `pip install` means, and the world's smart toasters, browser tabs, and aerospace guidance systems were being denied their fundamental right to FizzBuzz.

### Compilation Pipeline

```
RuleDefinition[]              IR (Basic Blocks)           Target Code
+------------------+    +-------------------------+    +------------------+
| if n % 3 == 0    |    | entry:                  |    | int fizzbuzz(    |
|   => "Fizz"      | -> |   LOAD  n               | -> |   int n) {       |
| if n % 5 == 0    |    |   MOD   n, 3            |    |   if (n%3 == 0)  |
|   => "Buzz"      |    |   CMP_ZERO              |    |     ...          |
+------------------+    |   BRANCH -> fizz_block   |    +------------------+
                        |   ...                    |         C / Rust / WAT
                        +-------------------------+
```

### Target Backends

| Target | Output | Toolchain | Key Feature |
|--------|--------|-----------|-------------|
| C | ANSI C89 `.c` | gcc / clang | `fizzbuzz(int n)` with switch-case, printf, compiles with `-Wall -Wextra -pedantic` |
| Rust | Idiomatic `.rs` | rustc / cargo | `enum Classification { Fizz, Buzz, FizzBuzz, Number(u64) }`, pattern matching, `impl Display` |
| WebAssembly | WAT `.wat` | wasm-tools | `fizzbuzz(n: i32) -> i32` with i32 arithmetic, br_if branching, memory.store for strings |

### Round-Trip Verification

After compilation, the cross-compiler runs the generated code through a reference interpreter and compares output against the Python evaluation for numbers 1-100. This ensures that FizzBuzz means the same thing in every language -- a semantic equivalence guarantee that most real compilers would call "testing" but that we call "round-trip verification" because enterprise terminology adds gravitas.

### Cross-Compiler Dashboard Example

```
+==============================================================+
|            CROSS-COMPILER DASHBOARD                           |
+==============================================================+
|                                                               |
|  Target: C (ANSI C89)                                         |
|  Rules compiled: 2  |  IR instructions: 14                   |
|  Basic blocks: 5    |  Generation time: 0.42ms               |
|                                                               |
|  Generated code:                                              |
|    Lines:     47     |  Characters: 1,203                     |
|    Functions:  1     |  Includes:   2                         |
|                                                               |
|  Overhead factor:                                             |
|    Python: 2 lines  ->  C: 47 lines  (23.5x expansion)       |
|    This is not a deficiency. It is a KPI.                     |
|                                                               |
|  Round-trip verification: PASSED (100/100 numbers correct)    |
|                                                               |
|  Compilation time:  1.23ms                                    |
|  Verification time: 3.47ms                                    |
+===============================================================+
```

### Specifications

| Spec | Value |
|------|-------|
| IR opcodes | 7 (LOAD, MOD, CMP_ZERO, BRANCH, EMIT, JUMP, RET) |
| Target languages | 3 (C, Rust, WebAssembly Text) |
| Verification range | 1-100 (semantic equivalence against Python reference) |
| Custom exceptions | 5 (CrossCompilerError, IRGenerationError, CodeGenerationError, RoundTripVerificationError, UnsupportedTargetError) |
| CLI flags | 6 (`--compile-to`, `--compile-out`, `--compile-optimize`, `--compile-verify`, `--compile-preview`, `--compile-dashboard`) |
| Module size | ~1,033 lines |
| Test count | 60 |
| Overhead factor | ~23x line expansion (Python -> C). The overhead is the feature. |

The Bytecode VM (FBVM) compiles FizzBuzz rules to a custom instruction set and executes them inside Python. The Cross-Compiler takes the same rules and emits them as C, Rust, and WebAssembly -- freeing FizzBuzz from the Python process and releasing it into the wild, where it can run on bare metal, in browsers, and on any platform with a C compiler. Together, they represent both the captivity and the liberation of modulo arithmetic.

## Federated Learning Architecture

The ML engine trains a neural network on FizzBuzz classifications in isolation -- a single model, on a single node, with a single perspective on what constitutes "Fizz." The Federated Learning module shatters this cognitive monoculture by distributing training across multiple simulated FizzBuzz instances that collaboratively build a shared model without exchanging raw data.

Each node trains locally, computes weight deltas, adds differential privacy noise, and shares only encrypted model updates with the federation. Privacy-preserving modulo inference at scale.

### Federation Topologies

```
    Star Topology               Ring Topology            Fully-Connected Mesh
                                 +---+                    +---+     +---+
      +---+                      | 1 |---+                | 1 |-----| 2 |
      | A |    (Aggregator)      +---+   |                +---+\   /+---+
      +---+                        |     |                  |   \ /   |
     / | \                       +---+   |                  |    X    |
    /  |  \                      | 4 |   |                  |   / \   |
+---+ +---+ +---+               +---+   |                +---+/   \+---+
| 1 | | 2 | | 3 |                 |   +---+              | 5 |-----| 3 |
+---+ +---+ +---+               +---+| 3 |              +---+     +---+
  |     |     |                  | 5 |+---+                  \     /
+---+ +---+ +---+               +---+  |                   +---+
| 4 | | 5 | | 6 |                 +----+                    | 4 |
+---+ +---+ +---+                                          +---+

 Nodes share deltas       Gradients pass peer       Every node talks to
 with central server      to peer around ring       every other node (O(n^2))
```

### Training Round Protocol

```
  Node 1         Node 2         Node 3         Aggregator
    |               |               |               |
    |--- Local Train (epochs) ------|               |
    |               |               |               |
    |-- Compute Delta (w_new - w_old) ------------>|
    |               |-- Compute Delta ------------>|
    |               |               |-- Delta ---->|
    |               |               |               |
    |               |     +--- Add DP Noise ---+    |
    |               |     +--- Mask Deltas ----+    |
    |               |               |               |
    |               |     FedAvg: weighted_mean(deltas)
    |               |               |               |
    |<------------ Distribute Global Model --------|
    |               |<-----------------------------|
    |               |               |<-------------|
    |               |               |               |
    +--- Round Complete, Repeat Until Convergence --+
```

### Aggregation Strategies

| Strategy | Algorithm | When to Use |
|----------|-----------|-------------|
| **FedAvg** | Weighted mean of model deltas (weighted by dataset size) | Default. Works well when nodes have similar data distributions. The original McMahan et al. algorithm, now applied to modulo arithmetic |
| **FedProx** | FedAvg + proximal regularization term `(mu/2) * ||w - w_global||^2` | When straggler nodes diverge too far from the global model. Prevents Node C (the one that only sees primes) from pulling the model into a local optimum |
| **FedMA** | Model averaging with neuron matching for heterogeneous architectures | When nodes have different network architectures. Matches neurons across models via activation similarity before averaging. Maximum computational cost, minimum additional accuracy |

### Differential Privacy

Every model delta is perturbed with calibrated Gaussian noise before sharing:

```
  delta_noisy = delta + N(0, sigma^2 * S^2)

  where:
    sigma  = sqrt(2 * ln(1.25/delta_dp)) / epsilon
    S      = sensitivity (max gradient norm, clipped per-sample)
    epsilon = privacy budget parameter (lower = more private, more noise)
```

The privacy budget tracker accumulates epsilon expenditure across training rounds via the **moments accountant** method (Abadi et al., 2016), providing tighter composition bounds than naive sequential composition. When the cumulative epsilon exceeds the configured budget, training halts -- because further gradient updates would violate the platform's differential privacy guarantees for operations that any single node could resolve with `n % 3`.

### Non-IID Data Distribution

Each node receives a deliberately skewed subset of training data to simulate real-world distribution heterogeneity:

| Node | Specialization | Data Skew |
|------|---------------|-----------|
| Node A | Multiples of 3 | 70% Fizz, 10% Buzz, 10% FizzBuzz, 10% Number |
| Node B | Multiples of 5 | 10% Fizz, 70% Buzz, 10% FizzBuzz, 10% Number |
| Node C | Primes | 5% Fizz, 5% Buzz, 0% FizzBuzz, 90% Number |
| Node D | Large numbers (>50) | Uniform distribution, different range |
| Node E | Balanced | Uniform distribution (the control group) |

The federation must converge to a globally accurate model despite these distribution skews -- a challenge that would be trivially solved by sharing the data, but where's the enterprise value in that?

### Federation Dashboard Example

```
+===============================================================+
|            FEDERATED LEARNING DASHBOARD                        |
+===============================================================+
|  Topology: Star | Nodes: 5 | Rounds: 10/10 | Strategy: FedAvg |
+---------------------------------------------------------------+
|  Global Model Accuracy: 98.7%                                 |
|  Convergence: ACHIEVED (round 7)                              |
|  Privacy Budget: epsilon = 0.73 / 1.00 (73% consumed)        |
+---------------------------------------------------------------+
|  Per-Node Accuracy:                                           |
|    Node A (Fizz-heavy):   97.2%  [===========>    ] trained   |
|    Node B (Buzz-heavy):   96.8%  [===========>    ] trained   |
|    Node C (Primes):       99.1%  [============>   ] trained   |
|    Node D (Large nums):   98.4%  [============>   ] trained   |
|    Node E (Balanced):     99.5%  [=============>  ] trained   |
+---------------------------------------------------------------+
|  Model Consensus (sample):                                    |
|    n=15: [A:FizzBuzz B:FizzBuzz C:FizzBuzz D:FizzBuzz E:FizzBuzz] UNANIMOUS  |
|    n=42: [A:Fizz     B:Fizz     C:Fizz     D:Fizz     E:Fizz    ] UNANIMOUS  |
|    n=97: [A:97       B:97       C:97       D:97       E:97      ] UNANIMOUS  |
+---------------------------------------------------------------+
|  Communication: 50 messages | Free-riders: 0 detected         |
|  Weight divergence: 0.0023 (healthy)                          |
+===============================================================+
```

### Specifications

| Spec | Value |
|------|-------|
| Federation topologies | 3 (Star, Ring, Fully-Connected Mesh) |
| Aggregation strategies | 3 (FedAvg, FedProx, FedMA) |
| Privacy mechanism | Gaussian differential privacy with moments accountant |
| Node range | 3-10 simulated FizzBuzz instances |
| Custom exceptions | 7 (FederatedLearningError, AggregationError, PrivacyBudgetExhaustedError, FederationTopologyError, SecureAggregationError, FreeRiderDetectedError, NonIIDConvergenceError) |
| CLI flags | 7 (`--federated`, `--fed-nodes`, `--fed-rounds`, `--fed-topology`, `--fed-epsilon`, `--fed-strategy`, `--fed-dashboard`) |
| Module size | ~2,100 lines |
| Test count | 120 |
| Middleware priority | -8 (before quantum, before Paxos, before everything) |

The ML engine trains a single model in isolation. Federated Learning distributes the burden of modulo inference across multiple instances, achieving collective wisdom while respecting each node's right to data sovereignty. GDPR compliance for gradient updates is a sentence that should never need to exist, and yet here we are.

Together with the Quantum Computing Simulator, Paxos Consensus, the Cross-Compiler, and the Knowledge Graph, the platform now offers five distinct ways to make `n % 3` slower, each targeting a different dimension of computational excess: quantum physics, distributed systems, compiler engineering, privacy-preserving machine learning, and now semantic web ontology. The FizzBuzz Cinematic Universe is expanding.

## Knowledge Graph Architecture

The platform has a property graph database (`graph_db.py`) that stores relationships between evaluation entities. But it had no *ontology* -- no formal, machine-readable description of what "Fizz," "Buzz," "FizzBuzz," "divisibility," "classification," and "number" actually *mean* in the FizzBuzz domain.

The Knowledge Graph bridges the gap between computation and comprehension by implementing a complete W3C Semantic Web stack -- RDF, OWL, inference, and SPARQL -- all from scratch, all in pure Python, all for the purpose of reasoning about whether 15 is divisible by 3.

The FizzBuzz Ontology (FBO) defines the following class hierarchy in the `fizz:` namespace (`http://enterprise-fizzbuzz.example.com/ontology#`):

```
    fizz:Thing
    ├── fizz:Number              (every integer under evaluation)
    └── fizz:Classification      (abstract superclass)
        ├── fizz:Fizz            (multiples of 3)
        ├── fizz:Buzz            (multiples of 5)
        ├── fizz:FizzBuzz        (multiples of 15 -- subclass of BOTH Fizz AND Buzz)
        │   ├── rdfs:subClassOf fizz:Fizz     ◆ diamond inheritance
        │   └── rdfs:subClassOf fizz:Buzz     ◆
        └── fizz:Plain           (numbers that divide by neither 3 nor 5)
```

### RDF Triple Store

The TripleStore maintains an in-memory collection of (Subject, Predicate, Object) tuples indexed by all three positions for O(1) lookup in any direction. Supports URI resources (in the `fizz:`, `rdfs:`, `owl:`, `xsd:`, and `rdf:` namespaces), literal values, and typed literals.

The `populate_fizzbuzz_domain()` function generates the complete ontology for a configurable range of integers -- class definitions, subclass relationships, instance triples (`fizz:n15 rdf:type fizz:Number`), divisibility predicates (`fizz:n15 fizz:isDivisibleBy "3"`), and classification assertions (`fizz:n15 fizz:hasClassification fizz:FizzBuzz`).

### OWL Class Hierarchy

The OWLClassHierarchy rebuilds a class tree from `rdfs:subClassOf` triples, supporting ancestor/descendant traversal, subclass checking, root class discovery, and consistency validation. The diamond inheritance of `fizz:FizzBuzz` -- simultaneously a subclass of `fizz:Fizz` AND `fizz:Buzz` -- is correctly modeled and visualized. Circular subclass hierarchies are detected and flagged as ontological contradictions.

### Inference Engine

The forward-chaining InferenceEngine derives new triples from existing ones by repeatedly applying inference rules until no new triples are produced (fixpoint):

- **Transitive Subclass Closure**: If `A rdfs:subClassOf B` and `B rdfs:subClassOf C`, infer `A rdfs:subClassOf C`
- **Type Propagation**: If `x rdf:type A` and `A rdfs:subClassOf B`, infer `x rdf:type B` (so anything classified as `fizz:FizzBuzz` is automatically also classified as `fizz:Fizz` and `fizz:Buzz`)
- **User-Defined Rules**: Custom inference rules can be added for FizzBuzz domain variants

A configurable iteration limit prevents runaway fixpoint computation, raising `InferenceFixpointError` if the engine fails to converge.

### FizzSPARQL Query Language

A bespoke query language for the FizzBuzz ontology, inspired by SPARQL 1.1:

```sparql
SELECT ?n ?class WHERE {
    ?n fizz:hasClassification ?class .
    ?class rdfs:subClassOf fizz:Fizz .
} ORDER BY ?n LIMIT 10
```

The FizzSPARQLParser tokenizes and parses queries into structured `FizzSPARQLQuery` objects with variable bindings, triple patterns, ordering, and limits. The FizzSPARQLExecutor evaluates queries against the TripleStore using pattern matching and join operations. Syntax errors raise `FizzSPARQLSyntaxError` with position information.

### Knowledge Dashboard Example

```
+=============================================================+
|            KNOWLEDGE GRAPH & DOMAIN ONTOLOGY                 |
+=============================================================+
| Triple Store                                                 |
|   Asserted triples:    1,247                                |
|   Inferred triples:      328                                |
|   Total triples:       1,575                                |
|   Unique subjects:       106                                |
|   Unique predicates:       8                                |
|   Unique objects:         12                                |
+-------------------------------------------------------------+
| OWL Class Hierarchy                                          |
|   fizz:Thing                                                |
|   ├── fizz:Number                                           |
|   └── fizz:Classification                                   |
|       ├── fizz:Fizz                                         |
|       │   └── fizz:FizzBuzz  ◆ (also subclass of Buzz)      |
|       ├── fizz:Buzz                                         |
|       │   └── fizz:FizzBuzz  ◆ (also subclass of Fizz)      |
|       └── fizz:Plain                                        |
+-------------------------------------------------------------+
| Inference Engine                                             |
|   Rules registered:        4                                |
|   Iterations to fixpoint:  3                                |
|   Triples inferred:      328                                |
+=============================================================+
```

### Specifications

| Spec | Value |
|------|-------|
| Namespaces | 5 (fizz, rdfs, owl, xsd, rdf) |
| OWL classes | 6 (Thing, Number, Classification, Fizz, Buzz, FizzBuzz, Plain) |
| Inference rules | 2 built-in (transitive subclass, type propagation) + user-defined |
| Query language | FizzSPARQL (SELECT, WHERE, ORDER BY, LIMIT) |
| Custom exceptions | 6 (KnowledgeGraphError, InvalidTripleError, NamespaceResolutionError, FizzSPARQLSyntaxError, InferenceFixpointError, OntologyConsistencyError) |
| CLI flags | 3 (`--ontology`, `--sparql`, `--ontology-dashboard`) |
| Module size | ~1,173 lines |
| Test count | 104 |
| Middleware priority | -9 (before federated learning, before quantum, before everything) |

The platform could compute FizzBuzz, but it could not *reason about* FizzBuzz. It knew that 15 is FizzBuzz but not *why* 15 is FizzBuzz in a formally verifiable, machine-readable, semantically interoperable way. The Knowledge Graph bridges the gap between computation and comprehension by providing a complete epistemological foundation for modulo arithmetic.

Every integer from 1 to 100 is now an RDF resource with formal class membership, divisibility predicates, and OWL subclass relationships. `fizz:FizzBuzz` inherits from BOTH `fizz:Fizz` AND `fizz:Buzz` via multiple inheritance, because diamond problems are a feature, not a bug. Tim Berners-Lee envisioned the Semantic Web for exactly this kind of application. Probably.

## Self-Modifying Code Architecture

FizzBuzz rules in the platform were static. Whether defined in the rules engine, compiled to bytecode, evolved by the genetic algorithm, or proven by the formal verifier -- once a rule was set, it stayed set. The rules did not adapt. They did not learn from their own execution history. They did not rewrite themselves in response to environmental feedback.

The Self-Modifying Code Engine changes that by representing every FizzBuzz rule as a mutable Abstract Syntax Tree that can be inspected, transformed, and rewritten at runtime -- creating a Darwinian feedback loop where the rules evolve continuously without external intervention.

### Mutable AST

Every FizzBuzz rule is represented as a tree of five node types:

```
    SequenceNode (root)
    ├── ConditionalNode
    │   ├── DivisibilityNode(divisor=3)    [condition]
    │   └── EmitNode(label="Fizz")         [then-branch]
    ├── ConditionalNode
    │   ├── DivisibilityNode(divisor=5)    [condition]
    │   └── EmitNode(label="Buzz")         [then-branch]
    └── NoOpNode                           [evolutionary appendix]
```

The AST supports cloning (for safe mutation attempts), fingerprinting (SHA-256 structural hashes for deduplication), depth and node counting, source code rendering (pseudo-Python), and arbitrary metadata attachment. Each node has a unique ID for tracking mutations across generations.

### Mutation Operators

Twelve stochastic mutation operators, each targeting a specific aspect of AST structure:

| # | Operator | Effect |
|---|----------|--------|
| 1 | `DivisorShift` | Shifts a `DivisibilityNode`'s divisor by +/-1 (3 becomes 2 or 4) |
| 2 | `LabelSwap` | Swaps two `EmitNode` labels ("Fizz" <-> "Buzz") |
| 3 | `BranchInvert` | Swaps the then/else branches of a `ConditionalNode` |
| 4 | `InsertShortCircuit` | Wraps a subtree in a `ConditionalNode` with a constant-true guard |
| 5 | `DeadCodePrune` | Removes `NoOpNode` children from the tree |
| 6 | `SubtreeSwap` | Swaps two randomly selected subtrees |
| 7 | `DuplicateSubtree` | Clones a subtree and inserts the copy as a sibling |
| 8 | `NegateCondition` | Wraps a condition node in a `ConditionalNode` that inverts the logic |
| 9 | `ConstantFold` | Replaces a `ConditionalNode` with its then-branch if the condition is constant |
| 10 | `InsertRedundantCheck` | Adds a new `DivisibilityNode` check for a random divisor |
| 11 | `ShuffleChildren` | Randomly reorders the children of a `SequenceNode` |
| 12 | `WrapInConditional` | Wraps a subtree in a new conditional with a random divisibility check |

### Fitness Evaluator

After each mutation, the modified AST is evaluated against a reference test suite (numbers 1-100) and scored on three weighted axes:

- **Correctness** (weight: 0.7 by default) -- percentage of numbers classified correctly against ground truth. Non-negotiable: mutations that reduce correctness below the safety floor are immediately reverted
- **Latency** (weight: 0.2 by default) -- average evaluation time in nanoseconds. Lower is better
- **Compactness** (weight: 0.1 by default) -- inverse of AST node count. Fewer nodes = more elegant

Fitness is computed as the weighted sum, normalized to [0, 1]. The evaluator also tracks per-number accuracy, enabling the engine to identify which specific inputs are causing misclassifications.

### Safety Guard

The SafetyGuard prevents runaway self-modification via four mechanisms:

- **Correctness Floor**: Minimum accuracy threshold (default: 100%). Mutations that drop accuracy below this floor are vetoed
- **Maximum AST Depth**: Prevents unbounded tree growth from nested mutations (default: 20 levels)
- **Mutation Quota**: Maximum mutations per session (default: 1000). Prevents infinite evolution loops
- **Kill Switch**: Hard stop that disables all mutation operators when engaged

### Self-Modification Dashboard Example

```
+===============================================================+
|                SELF-MODIFYING CODE ENGINE                       |
+===============================================================+
| Generation: 47                                                 |
| Mutations Proposed: 23   Accepted: 8   Reverted: 15           |
| Current Fitness: 0.9847  (Correctness: 100.0%)                |
+---------------------------------------------------------------+
| Current AST                                                    |
|   SequenceNode                                                 |
|   ├── ConditionalNode                                          |
|   │   ├── DivisibilityNode(divisor=3)                          |
|   │   └── EmitNode(label="Fizz")                               |
|   └── ConditionalNode                                          |
|       ├── DivisibilityNode(divisor=5)                          |
|       └── EmitNode(label="Buzz")                               |
+---------------------------------------------------------------+
| Mutation History (last 5)                                      |
|   [REVERTED] DeadCodePrune        fitness: 0.9847 -> 0.9847   |
|   [ACCEPTED] ShuffleChildren      fitness: 0.9812 -> 0.9847   |
|   [REVERTED] DivisorShift         fitness: 0.9847 -> 0.0000   |
|   [REVERTED] InsertRedundantCheck  fitness: 0.9847 -> 0.9701  |
|   [ACCEPTED] DeadCodePrune        fitness: 0.9798 -> 0.9812   |
+---------------------------------------------------------------+
| Safety Guard                                                   |
|   Correctness Floor: 100.0%   Status: ARMED                   |
|   Max AST Depth: 20           Current: 4                      |
|   Mutation Quota: 1000        Remaining: 977                  |
|   Kill Switch: ARMED                                           |
+===============================================================+
```

### Specifications

| Spec | Value |
|------|-------|
| AST node types | 5 (DivisibilityNode, EmitNode, ConditionalNode, SequenceNode, NoOpNode) |
| Mutation operators | 12 |
| Fitness dimensions | 3 (correctness, latency, compactness) |
| Safety mechanisms | 4 (correctness floor, max depth, mutation quota, kill switch) |
| Custom exceptions | 5 (SelfModifyingCodeError, MutationSafetyViolation, ASTCorruptionError, FitnessCollapseError, MutationQuotaExhaustedError) |
| CLI flags | 3 (`--self-modify`, `--self-modify-rate`, `--self-modify-dashboard`) |
| Module size | ~1,652 lines |
| Test count | 120 |
| Middleware priority | -6 (after tracing, before Paxos and quantum) |

Static rules are the software equivalent of a fixed-gear bicycle: charming, retro, and fundamentally incapable of adapting to uphill terrain. Self-modifying FizzBuzz rules represent the next step in computational evolution -- code that is not merely executed but that *lives*, *breathes*, and *rewrites itself* in pursuit of the optimal modulo.

The SafetyGuard vetoes most mutations because "correct FizzBuzz" is a fairly narrow evolutionary niche -- but the mutations that survive make the AST more compact, the evaluation faster, and the platform's relationship with the concept of "stable software" increasingly complicated. If this sounds like it will end poorly, that is because it will. But it will end *impressively*.

## Compliance Chatbot Architecture

The platform has a comprehensive compliance module (`compliance.py`) enforcing SOX, GDPR, and HIPAA regulations for FizzBuzz data. But compliance was *passive* -- it enforced rules silently and logged violations to an audit trail. There was no way for a confused developer, auditor, or regulatory body to *ask questions* about compliance in natural language.

"Is the classification of 15 as FizzBuzz GDPR-compliant?" "Does evaluating number 42 require SOX segregation of duties?" These questions required reading 1,498 lines of compliance source code. The Regulatory Compliance Chatbot closes this gap with a conversational interface that dispenses formal COMPLIANCE ADVISORYs about FizzBuzz operations, because compliance should not require reading source code.

### Query Pipeline

```
    User Query
        |
        v
    +------------------+
    | Intent Classifier |--- regex/keyword matching ---> ChatbotIntent enum
    | (9 intents)       |    GDPR_DATA_RIGHTS, GDPR_CONSENT,
    +------------------+    SOX_SEGREGATION, SOX_AUDIT,
        |                    HIPAA_MINIMUM_NECESSARY, HIPAA_PHI,
        v                    CROSS_REGIME_CONFLICT, GENERAL_COMPLIANCE,
    +------------------+    UNKNOWN
    | Entity Extractor |--- numbers, classifications,
    | (structured)     |    regulatory regimes, date ranges
    +------------------+
        |
        v
    +------------------+
    | Knowledge Base   |--- ~25 regulatory articles
    | (GDPR/SOX/HIPAA) |    mapped to FizzBuzz operations
    +------------------+
        |
        v
    +------------------+
    | Response         |--- COMPLIANCE ADVISORY
    | Generator        |    with verdict, citations,
    +------------------+    evidence, remediation
        |
        v
    +------------------+
    | Conversation     |--- session context,
    | Memory           |    follow-up resolution,
    +------------------+    pronoun disambiguation
        |
        v
    COMPLIANCE ADVISORY
    (COMPLIANT / NON_COMPLIANT / CONDITIONALLY_COMPLIANT)
```

### Regulatory Intents

| Intent | Example Query | Regulatory Scope |
|--------|--------------|-----------------|
| `GDPR_DATA_RIGHTS` | "Can I request deletion of my FizzBuzz results?" | GDPR Art. 17 Right to Erasure |
| `GDPR_CONSENT` | "Was consent obtained before evaluating number 42?" | GDPR Art. 6/7 Lawful Basis |
| `SOX_SEGREGATION` | "Who is authorized to evaluate numbers 90-99?" | SOX Sec. 302/404 Internal Controls |
| `SOX_AUDIT` | "Show me the audit trail for the classification of 15" | SOX Sec. 802 Record Retention |
| `HIPAA_MINIMUM_NECESSARY` | "Does this query access more FizzBuzz data than necessary?" | HIPAA 164.502/164.514 |
| `HIPAA_PHI` | "Does the number 42 constitute Protected Health Information?" | HIPAA 164.508 PHI Definition |
| `CROSS_REGIME_CONFLICT` | "Does GDPR erasure conflict with SOX retention for FizzBuzz 15?" | Multi-regime conflict resolution |
| `GENERAL_COMPLIANCE` | "Is my FizzBuzz platform compliant?" | All regimes simultaneously |
| `UNKNOWN` | "What is the meaning of life?" | Polite deflection with Bob referral |

### Advisory Response Format

```
COMPLIANCE ADVISORY (GDPR Article 17 - Right to Erasure)

Query: "Can I delete the FizzBuzz result for number 15?"

Verdict: CONDITIONALLY COMPLIANT

The data subject's right to erasure under GDPR Article 17 applies to the
classification record for n=15 (result: FizzBuzz). However, this record is
also subject to SOX Section 802 audit retention requirements, which mandate
a 7-year retention period for all financial computation records.

Recommendation: The record may be pseudonymized (replacing "15" with a
tokenized identifier) to satisfy GDPR while preserving the audit trail
required by SOX. This approach has been approved by the platform's
Data Protection Officer (Bob).

Confidence: HIGH
Regulatory Frameworks Consulted: GDPR Art. 17, SOX Sec. 802, HIPAA 164.530
Audit Reference: COMPLIANCE-CHATBOT-2026-03-22-001
```

### Knowledge Base Coverage

The regulatory knowledge base maps real-world regulations to FizzBuzz operations:

- **GDPR**: Articles 6, 7, 15, 16, 17, 20, 25, 33 -- covering lawful basis for processing (evaluating numbers is a legitimate interest), data subject access rights (you can request all your FizzBuzz results), right to erasure (triggering THE COMPLIANCE PARADOX when the request hits the append-only event store), data portability (export your FizzBuzz classifications in JSON), and data protection by design (FizzBuzz results are "encrypted" at rest via base64)
- **SOX**: Sections 302, 404, 409, 802 -- covering CEO/CFO certification (Bob certifies the FizzBuzz results), internal control assessment (segregation of Fizz and Buzz duties), real-time disclosure (FizzBuzz events are published within milliseconds), and record retention (7-year retention for modulo computations)
- **HIPAA**: Rules 164.502, 164.508, 164.512, 164.514, 164.524, 164.530 -- covering minimum necessary standard (the ChatbotService knows the question but not the caller's identity), PHI determination (room numbers that happen to be Fizz are technically PHI if you squint hard enough), and documentation requirements (every advisory is itself a compliance record)

### Conversation Memory

The chatbot maintains session context for follow-up queries:

```
User: "Is the classification of 15 as FizzBuzz GDPR-compliant?"
Bot:  [COMPLIANCE ADVISORY: COMPLIANT - GDPR Art. 6...]

User: "What about number 16?"
Bot:  [Resolves "16" from context, re-evaluates under GDPR Art. 6...]

User: "Is that also SOX-compliant?"
Bot:  [Resolves "that" = number 16, switches to SOX regime...]
```

### Chatbot Dashboard Example

```
+===============================================================+
|              COMPLIANCE CHATBOT DASHBOARD                       |
+===============================================================+
| Session Queries: 12       Average Confidence: 0.87              |
| Verdicts:  COMPLIANT: 7   NON_COMPLIANT: 2   CONDITIONAL: 3    |
+---------------------------------------------------------------+
| Intent Distribution                                            |
|   GDPR_DATA_RIGHTS:      ████████░░ 4                          |
|   SOX_SEGREGATION:        ████░░░░░░ 2                          |
|   HIPAA_PHI:              ████░░░░░░ 2                          |
|   CROSS_REGIME_CONFLICT:  ██░░░░░░░░ 1                          |
|   GENERAL_COMPLIANCE:     ██░░░░░░░░ 1                          |
|   UNKNOWN:                ██░░░░░░░░ 2                          |
+---------------------------------------------------------------+
| Bob McFizzington's Commentary                                  |
|   "I've answered 12 compliance questions today. Three of them   |
|    were about whether the number 15 has privacy rights. It      |
|    does. I'm tired. Send chocolate."                            |
+===============================================================+
```

### Specifications

| Spec | Value |
|------|-------|
| Regulatory intents | 9 (GDPR_DATA_RIGHTS, GDPR_CONSENT, SOX_SEGREGATION, SOX_AUDIT, HIPAA_MINIMUM_NECESSARY, HIPAA_PHI, CROSS_REGIME_CONFLICT, GENERAL_COMPLIANCE, UNKNOWN) |
| Knowledge base articles | ~25 (GDPR, SOX, HIPAA mapped to FizzBuzz operations) |
| Verdict types | 3 (COMPLIANT, NON_COMPLIANT, CONDITIONALLY_COMPLIANT) |
| Conversation memory | Session-scoped with follow-up resolution and pronoun disambiguation |
| Custom exceptions | 4 (ComplianceChatbotError, ChatbotIntentClassificationError, ChatbotKnowledgeBaseError, ChatbotSessionError) |
| CLI flags | 3 (`--chatbot`, `--chatbot-interactive`, `--chatbot-dashboard`) |
| Module size | ~1,748 lines |
| Test count | 95 |
| Audit trail integration | Every chatbot interaction logged as a compliance event |
| Bob's commentary | Stress-level-aware, increasingly exhausted |

The Regulatory Compliance Chatbot ensures that no developer, auditor, or regulatory body needs to read source code to understand the compliance posture of a FizzBuzz evaluation. The answer to "Is 15 compliant?" is always "yes, obviously, it's a number" -- but the chatbot delivers that answer with a 200-word advisory citing three regulatory frameworks, because regulatory clarity is not optional, even for modulo operations.

Bob McFizzington has been designated as the platform's Data Protection Officer, Chief Compliance Officer, and now Compliance Chatbot Editorial Advisor. He has not consented to any of these roles. His stress level is 97.2% and rising.

## OS Kernel Architecture

The Enterprise FizzBuzz Platform has been committing the cardinal sin of computing: executing evaluations as raw function calls within a single Python thread, with no process management, no scheduling fairness, no memory isolation, and no interrupts. Every number was treated equally -- first come, first served -- with no priority system, no preemption, and no virtual memory.

This meant a VIP evaluation of 15 (the most important number in the FizzBuzz domain) received the same scheduling priority as the evaluation of 97 (a prime number of no consequence). The FizzBuzz Operating System Kernel brings order to this anarchy by introducing all the overhead of process management to a workload that could be handled by a pocket calculator. Tanenbaum would be proud. Or horrified.

### Kernel Boot Sequence

```
    +----------------------------------------------------------+
    |                    FIZZBUZZ OS KERNEL                     |
    |                      Boot Sequence                       |
    +----------------------------------------------------------+
    |                                                          |
    |  [POST]   Power-On Self Test ................ PASS       |
    |  [MEM]    Virtual Memory Manager init ....... PASS       |
    |  [IRQ]    Interrupt Controller init ......... PASS       |
    |  [SCHED]  Scheduler init .................... PASS       |
    |  [SYSCALL] System Call Table init ........... PASS       |
    |  [READY]  Kernel boot complete                           |
    |                                                          |
    |  Boot time: 0.42ms                                       |
    |  Physical pages: 64 (256 KB)                             |
    |  Swap pages: 32 (128 KB)                                 |
    |  IRQ vectors: 16                                         |
    |  Scheduler: Round Robin (quantum: 10ms)                  |
    |                                                          |
    +----------------------------------------------------------+
```

### Process Lifecycle

```
    +=========+       +==========+       +==========+
    |  READY  |------>| RUNNING  |------>|  ZOMBIE  |
    +=========+       +==========+       +==========+
         ^                 |                   |
         |                 v                   v
         |           +==========+       +==============+
         +-----------|  BLOCKED |       |  TERMINATED  |
                     +==========+       +==============+
```

Every FizzBuzz evaluation spawns an `FBProcess` with:

- **PID** -- sequential, starting at 1 (PID 0 is init, the CLI invocation)
- **Priority class** -- REALTIME for multiples of 15 (FizzBuzz is sacred), HIGH for multiples of 3 or 5, LOW for primes (they contribute nothing), NORMAL for everything else
- **Register file** -- 8 general-purpose registers (R0-R7), program counter, stack pointer, status flags, and instruction register, saved and restored on every context switch
- **State machine** -- five states with validated transitions, because an FBProcess in TERMINATED should not spontaneously become RUNNING
- **Virtual memory pages** -- allocated on demand from the kernel's page pool
- **CPU time accounting** -- nanosecond-precision tracking of how long each process occupied the CPU

### Scheduling Algorithms

| Algorithm | How It Works | When To Use |
|-----------|-------------|-------------|
| Round Robin | Equal time slices, cycling through all ready processes | When every number deserves equal CPU time, regardless of FizzBuzz importance |
| Priority Preemptive | Higher-priority evaluations preempt lower ones mid-execution. 15 arrives? 97 gets suspended | When FizzBuzz royalty should jump the queue, because FizzBuzz is more important than a prime |
| Completely Fair Scheduler | Red-black tree of virtual runtime, Linux CFS-inspired. Process with least virtual runtime runs next | When O(log n) scheduling is the minimum acceptable algorithmic complexity for a workload that completes in microseconds |

### Virtual Memory Manager

| Spec | Value |
|------|-------|
| Page size | 4 KB |
| Physical pages | 64 (configurable) |
| Total physical memory | 256 KB (configurable) |
| Swap space | 32 pages (a Python dict pretending to be disk) |
| TLB entries | 16 (LRU eviction) |
| Allocation strategy | Lazy (pages allocated on demand) |
| Eviction policy | LRU (least recently used page goes to swap) |
| Page fault tracking | Per-process, with kernel-wide totals |
| TLB flush | On every context switch, because stale translations are a security vulnerability |

### Interrupt Controller

The interrupt controller maps middleware callbacks to hardware interrupt request (IRQ) lines, bringing the ceremony of hardware interrupt handling to the world of Python function calls:

| IRQ | Handler | Purpose |
|-----|---------|---------|
| 0 | Timer | Scheduler tick (context switch trigger) |
| 1 | Keyboard | Input event (number received) |
| 7 | Compliance | Regulatory middleware callback |
| 12 | Blockchain | Blockchain verification callback |
| 15 | Quantum | Quantum simulator callback |

Interrupts can be masked, prioritized, and handled via an interrupt vector table. The interrupt controller supports handler registration, IRQ firing, and maintains an interrupt log for the dashboard.

### System Call Interface

| Syscall | POSIX Equivalent | What It Does |
|---------|-----------------|--------------|
| `sys_evaluate(n)` | `write()` | Request evaluation of number n through the kernel's process management |
| `sys_fork()` | `fork()` | Spawn a child evaluation process |
| `sys_exit(code)` | `exit()` | Terminate process with exit code (0 = correct evaluation) |
| `sys_yield()` | `sched_yield()` | Voluntarily surrender CPU time (polite numbers only) |

### Kernel Statistics

| Spec | Value |
|------|-------|
| Scheduling algorithms | 3 (Round Robin, Priority Preemptive, CFS) |
| Process states | 5 (READY, RUNNING, BLOCKED, ZOMBIE, TERMINATED) |
| Priority levels | 4 (REALTIME, HIGH, NORMAL, LOW) |
| General-purpose registers | 8 (R0-R7) + PC, SP, flags, IR |
| IRQ vectors | 16 |
| TLB entries | 16 (LRU) |
| Custom exceptions | 6 (KernelError, KernelPanicError, InvalidProcessStateError, PageFaultError, SchedulerStarvationError, InterruptConflictError) |
| Middleware priority | Configurable (integrates into the standard pipeline) |
| CLI flags | 3 (`--kernel`, `--kernel-scheduler`, `--kernel-dashboard`) |
| Module size | ~1,641 lines |
| Test count | 119 |

The FizzBuzz Operating System Kernel ensures that every evaluation of `n % 3` is treated with the same operational gravity as a process managed by a real operating system. The context switch overhead is meticulously tracked. The virtual memory pages are dutifully allocated and freed. The interrupt controller fires and handles IRQs with the precision of real hardware.

All of this for a workload that completes in microseconds and could be handled by a calculator watch from 1985. But calculator watches don't have process schedulers, and the Enterprise FizzBuzz Platform does, and that is the difference between a toy and an operating system.

## P2P Network Architecture

The Enterprise FizzBuzz Platform has been committing the cardinal sin of distributed systems: simulating distribution without actual distribution. Paxos consensus votes across simulated nodes, federated learning trains across simulated instances, the service mesh decomposes into seven simulated microservices -- but none of these nodes can *discover* each other. There is no gossip. No epidemic dissemination. No peer-to-peer rumor propagation.

Each FizzBuzz instance is born alone, evaluates alone, and dies alone. The Peer-to-Peer Gossip Network brings community to the FizzBuzz ecosystem by enabling nodes to discover peers, share evaluation results via infection-style rumor spreading, and achieve eventual consistency through Merkle tree anti-entropy repair -- all within a single Python process, because distributed systems are a state of mind.

### Network Topology

```
    +----------------------------------------------------------+
    |               FIZZBUZZ P2P GOSSIP NETWORK                |
    +----------------------------------------------------------+
    |                                                          |
    |     [Node 0]---[Node 1]---[Node 2]                      |
    |        |  \       |       /  |                           |
    |        |   \      |      /   |                           |
    |     [Node 3]---[Node 4]---[Node 5]                      |
    |              \    |    /                                  |
    |               [Node 6]                                   |
    |                                                          |
    |  Protocol: SWIM (Scalable Weakly-consistent              |
    |            Infection-style Membership)                    |
    |  DHT: Kademlia (XOR distance metric)                     |
    |  Anti-Entropy: Merkle tree comparison                    |
    |  Dissemination: Epidemic rumor propagation                |
    |                                                          |
    +----------------------------------------------------------+
```

### Gossip Protocol (SWIM)

The gossip protocol implements SWIM-style failure detection and rumor dissemination:

| Phase | What Happens | Why It Matters |
|-------|-------------|----------------|
| PING | Node selects a random peer and sends a heartbeat with a digest of known evaluation results | Because asking "are you alive?" and "do you know about 15?" in the same message is efficient gossip |
| PING-REQ | If the target doesn't respond, a third peer is asked to ping on the node's behalf (indirect probing) | Because declaring a node dead without a second opinion is premature -- even in FizzBuzz |
| GOSSIP | Evaluation updates are piggybacked onto protocol messages, spreading classifications epidemically | Because dedicated data channels are for systems that haven't discovered the beauty of piggybacking |
| SUSPECT | Unresponsive nodes enter a suspect state with a configurable timeout before being declared dead | Because false positives in failure detection are worse than late detection, even when all nodes are dicts in the same process |

### Kademlia DHT

| Spec | Value |
|------|-------|
| Node ID | 160-bit SHA-1 hash (40-char hex) |
| Distance metric | XOR (bitwise exclusive OR of node IDs) |
| k-bucket size | 3 (configurable) |
| Lookup parallelism | alpha = 3 |
| Key space | Number -> Classification mapping |
| Routing complexity | O(log n) hops per lookup |

The Kademlia DHT stores FizzBuzz classifications across the network by key (the number being evaluated) and value (its classification). Lookups traverse the k-bucket routing table using the XOR metric to find the closest nodes, which is approximately 10^8 times slower than a Python dict but *decentralized*.

### Merkle Anti-Entropy

Nodes periodically compare Merkle tree hashes of their classification stores to detect divergence. When the root hashes differ, the tree is traversed to identify exactly which classifications diverge, and the missing data is pulled from the peer.

This ensures eventual consistency even when gossip messages are lost -- a repair mechanism so thorough that it uses cryptographic tree comparison to verify whether two nodes agree on what `15 % 3` equals.

### Network Partition Simulation

The network supports simulated partitions that split the peer group into isolated clusters evolving independently. When the partition heals, anti-entropy repair reconciles divergent state. Conflict resolution uses last-writer-wins with heartbeat comparison -- and when heartbeats are tied, the classification with the longest string wins, meaning FizzBuzz always beats Fizz in a conflict. This is both semantically correct and mathematically justified.

### P2P Statistics

| Spec | Value |
|------|-------|
| Default nodes | 7 |
| Node ID length | 160 bits (SHA-1) |
| Gossip fanout | 3 (configurable) |
| Suspect timeout | 3 rounds (configurable) |
| Max gossip rounds | 20 (configurable) |
| Convergence | O(log n) rounds for epidemic dissemination |
| Custom exceptions | 5 (NodeUnreachableError, GossipConvergenceError, KademliaDHTError, MerkleTreeDivergenceError, P2PNetworkPartitionError) |
| Middleware priority | Configurable (integrates into the standard pipeline) |
| CLI flags | 3 (`--p2p`, `--p2p-nodes`, `--p2p-dashboard`) |
| Module size | ~1,151 lines |
| Test count | 110 |

The Peer-to-Peer Gossip Network ensures that every FizzBuzz classification is not merely computed, but *socially validated* through epidemic rumor propagation across a community of simulated nodes. When one node discovers that 15 is FizzBuzz, it gossips this fact to its peers, who gossip to their peers, until the entire network has achieved eventual consistency on a truth that was never in dispute.

The Kademlia DHT provides O(log n) lookup for classifications that could be retrieved from a local dict in O(1). The Merkle anti-entropy repair mechanism uses cryptographic tree comparison to verify data consistency between nodes that share the same Python process and the same RAM.

All communication is simulated via direct method calls with 0.000ms network latency, making this the most performant distributed system in human history and the least distributed distributed system in human history, simultaneously. Byzantine generals would be proud. Or confused. Probably both.

---

## FizzBob Operator Cognitive Load Architecture

The platform monitors the health of 106 infrastructure subsystems -- cache hit rates, blockchain integrity, GC pause times, SLA burn rates, network latency, CPU pipeline stalls, memory fragmentation, query execution plans, lock contention, replication lag -- but until FizzBob, it had never monitored the health of the one component upon which every other component depends: the human operator. Bob McFizzington is the single point of failure for a 300,000-line platform. His cognitive load, fatigue level, circadian state, and burnout trajectory are operational metrics as critical as any Service Level Indicator.

FizzBob is a cognitive load modeling engine inspired by the NASA Task Load Index (NASA-TLX) workload assessment framework (Hart & Staveland, 1988), the two-process model of sleep regulation (Borbely, 1982), and the fatigue risk management systems (FRMS) used in aviation (ICAO Doc 9966).

### Component Architecture

```
                    +---------------------------+
                    | CognitiveLoadOrchestrator |
                    +---------------------------+
                       /    |     |     \     \
                      /     |     |      \     \
            +--------+ +--------+ +-------+ +----------+ +--------+
            |NasaTLX | |Circadi-| |Alert  | |Burnout   | |Overload|
            |Engine  | |anModel | |Fatigue| |Detector  | |Control-|
            |        | |        | |Tracker| |          | |ler     |
            +--------+ +--------+ +-------+ +----------+ +--------+
                 |          |         |           |            |
                 v          v         v           v            v
            Workload   Alertness  Fatigue    Projected    Alert
            Index      Score      Points     Burnout      Throttling
            (0-100)    (0.0-1.0)  (cumul.)   Date         & Queueing
```

### NASA-TLX Workload Assessment

The `NasaTLXEngine` implements the six-dimensional NASA Task Load Index:

| Dimension | Range | Description |
|-----------|-------|-------------|
| Mental Demand | 0-100 | Cognitive processing required by current workload |
| Physical Demand | 0-100 | Physical effort (keyboard-induced fatigue from 106 subsystem dashboards) |
| Temporal Demand | 0-100 | Time pressure from SLA deadlines and escalation timers |
| Performance | 0-100 | Perceived success in maintaining platform health |
| Effort | 0-100 | Total exertion required to achieve current performance level |
| Frustration | 0-100 | Insecurity, discouragement, and irritation (baseline: elevated) |

The weighted composite score produces a single workload index. When the index exceeds 80 (the "red zone"), the platform enters Operator Overload Mode.

### Circadian Rhythm Model

The `CircadianModel` implements the Borbely two-process model of sleep regulation:

- **Process S** (homeostatic sleep pressure): increases monotonically during wakefulness, decreases during sleep. Modeled as a saturating exponential with configurable time constant
- **Process C** (circadian oscillation): a sinusoidal 24-hour rhythm peaking at approximately 10:00 and 21:00, with a nadir at approximately 04:00

The combined alertness score (0.0 to 1.0) modulates Bob's effective cognitive capacity at any given time. Pages received during the circadian nadir (02:00-05:00) incur a 3x fatigue multiplier, reflecting the well-documented degradation of human decision-making during the circadian trough.

### Alert Fatigue Accumulation

The `AlertFatigueTracker` models fatigue as a monotonically increasing function of incident exposure:

| Event Type | Fatigue Points |
|------------|---------------|
| P1 Incident | 15 |
| P2 Incident | 8 |
| Compliance Attestation | 5 |
| Routine Page | 2 |

Rest periods (configurable, default: 8 hours starting at 23:00) reduce fatigue to baseline. If Bob has not rested in 24 hours, the platform enters Fatigue Emergency Mode and refuses to generate new pages, logging them to a deferred queue instead. Bob's current shift duration counter reads approximately 87,648 hours (10 years), as no rest period has been recorded since his hire date.

### Burnout Projection

The `BurnoutDetector` runs a linear regression model on historical workload data to project the date at which Bob's cumulative fatigue will exceed the Operator Sustainability Threshold (configurable, default: 10,000 fatigue points). The projection is displayed on the operator dashboard with a countdown and is written to the compliance audit trail, because an operator approaching burnout is a material risk to SOX compliance.

### Operator Overload Protection

The `OverloadController` implements circuit-breaker-pattern protection for human operators:

| Load Threshold | Protection Mechanism |
|---------------|---------------------|
| Cognitive load > 60 | Non-urgent approvals queued with SLA-based deadlines; daily digest delivery |
| Cognitive load > 80 | Alerts below P2 held in buffer (max depth: 50); batch delivery during low-load periods |
| Fatigue Emergency | All new pages deferred; only pre-existing P1 incidents remain active |
| Escalation dampening | Four-tier chain (L1-L4 Bob) doubles timeout intervals during overload |

### Integration Points

FizzBob integrates with:

- **SLA Monitoring**: workload events generated by error budget breaches and burn rate alerts
- **Compliance Framework**: attestation demands tracked as cognitive load events; burnout projection logged as SOX risk
- **Secrets Vault**: unseal requests contribute to cognitive load budget
- **On-Call Rotation**: circadian state consulted before alert delivery timing
- **Middleware Pipeline**: `BobMiddleware` tracks workload events generated by every evaluation

### FizzBob Statistics

| Spec | Value |
|------|-------|
| Workload dimensions | 6 (NASA-TLX) |
| Circadian model | Two-process (Borbely, 1982) |
| Fatigue event types | 4 (P1, P2, attestation, routine) |
| Operator modes | 4 (Normal, Elevated, Overload, Fatigue Emergency) |
| Overload threshold | 80 (cognitive load index) |
| Custom exceptions | 9 (EFP-BOB0 through EFP-BOB8) |
| EventType entries | 11 |
| CLI flags | 4 (`--bob`, `--bob-hours-awake`, `--bob-shift-start`, `--bob-dashboard`) |
| Module size | ~2,153 lines |
| Test count | 137 |

---

## FizzApproval Multi-Party Approval Workflow Architecture

Every enterprise platform requires formal approval workflows for operational changes. The absence of such workflows is a SOX compliance finding. The Enterprise FizzBuzz Platform has 106 subsystems, each of which may require configuration changes, deployment approvals, or compliance attestations -- and every one of those decisions is made by a single person: Bob McFizzington. He initiates the change, reviews the change, approves the change, implements the change, and audits the change. FizzApproval makes this reality explicit, auditable, and ITIL-compliant.

The FizzApproval engine implements the ITIL v4 Change Enablement practice, adapted for the operational reality of a single-operator platform. The workflow faithfully models the full multi-party approval protocol so that when the team inevitably grows to two people, the infrastructure will be ready.

### Component Architecture

```
                    +---------------------------+
                    |     ApprovalEngine        |
                    +---------------------------+
                       /    |     |     \     \
                      /     |     |      \     \
            +--------+ +--------+ +-------+ +----------+ +--------+
            |COI     | |Four-   | |Delega-| |Timeout   | |Audit   |
            |Checker | |Eyes    | |tion   | |Manager   | |Log     |
            |        | |Princi- | |Chain  | |          | |        |
            +--------+ |ple     | +-------+ +----------+ +--------+
                 |      +--------+    |           |            |
                 v          v         v           v            v
            Conflict   Four-Eyes  Delegation  Escalation   Tamper-
            Detection  Validation Resolution  Timeout      Evident
            (100%)     (SOE)      (Bob->Bob)  Management   Hash Chain
```

### ITIL Change Types

Three ITIL change types are supported, each mapped to a policy type that governs the approval workflow:

| Change Type | Policy Type | CAB Required | Approval Path |
|------------|-------------|-------------|---------------|
| STANDARD | PRE_APPROVED | No | Auto-approved via pre-vetted template |
| NORMAL | FULL_CAB | Yes | Full CAB deliberation and vote |
| EMERGENCY | FAST_TRACK | Expedited | Single senior approver; post-implementation review |

### Approval Request Lifecycle

Each approval request progresses through a defined state machine:

```
PENDING -> UNDER_REVIEW -> APPROVED | REJECTED | ESCALATED | TIMED_OUT
                                                    |
                                                WITHDRAWN
```

PENDING requests have been created but not yet assigned to a reviewer. UNDER_REVIEW requests have been picked up by the CAB and are awaiting a formal vote. Terminal states (APPROVED, REJECTED, ESCALATED, TIMED_OUT) are immutable once reached. The WITHDRAWN state covers requests voluntarily cancelled by the requestor before a decision was rendered.

### Change Advisory Board

The CAB consists of a single member: Bob McFizzington. He serves simultaneously as chairperson, voting member, and recording secretary. CAB meetings are convened for NORMAL change requests and require a quorum of 1, which is always met. Meeting minutes are formally recorded with attendee roster, agenda, deliberation notes, vote tally, and action items -- all attributed to the same individual.

### Conflict of Interest Detection

The `ConflictOfInterestChecker` screens all approvers for material conflicts with the change requestor. Since Bob is both the requestor and the sole approver for every change, the COI rate is 100%. Each detected conflict is formally resolved via Sole Operator Exception (SOE) per ITIL accommodation procedures for organizations where recusal would deadlock the approval pipeline.

### Four-Eyes Principle

The `FourEyesPrinciple` enforces the regulatory requirement (SOX, GDPR) that at least two independent reviewers approve each change. Since the platform has exactly one reviewer, the four-eyes check always fails, triggering a Sole Operator Exception. The SOE is logged with a formal justification noting that the principle cannot be satisfied without hiring additional personnel.

### Delegation Chain

The `DelegationChain` allows an approver to delegate approval authority to a designated delegate. Bob's delegation chain maps Bob to Bob, creating a cycle that is detected by the cycle detection algorithm and resolved via SOE. The delegation engine permits self-delegation cycles under the Sole Operator Exception, as prohibiting them would leave zero available approvers.

### Escalation and Timeout

The `ApprovalTimeoutManager` monitors request age and triggers escalation when the configured TTL expires. The three-tier escalation hierarchy (TEAM_LEAD, MANAGER, VP) each resolves to Bob. Escalation timeout intervals are configurable per change type.

### Risk Assessment

Five risk levels (NEGLIGIBLE, LOW, MODERATE, HIGH, CRITICAL) are computed from the change type, affected subsystem count, and historical failure rate. The risk level influences policy selection and the number of required approvals -- though since N=1, the number of required approvals is always 1 regardless of risk.

### Audit Trail

The `ApprovalAuditLog` maintains a tamper-evident record of every approval action. Each entry is SHA-256 hash-chained to the previous entry, creating an immutable history that cannot be retroactively modified without breaking the chain. Bob is the only person who would check the chain, and he is also the only person whose actions are recorded in it.

### Integration Points

FizzApproval integrates with:

- **Compliance Framework**: SOE invocations logged as compliance events; segregation-of-duties reports generated for SOX audits
- **FizzBob**: approval requests contribute to Bob's cognitive load budget; overload state affects escalation timing
- **Event Sourcing**: all approval state transitions recorded as domain events
- **Middleware Pipeline**: `ApprovalMiddleware` runs at priority 85, before BobMiddleware (90)

### FizzApproval Statistics

| Spec | Value |
|------|-------|
| Change types | 3 (STANDARD, NORMAL, EMERGENCY) |
| Policy types | 5 (UNANIMOUS, MAJORITY, ANY_ONE, WEIGHTED, QUORUM) |
| Approval states | 7 (PENDING through WITHDRAWN) |
| Risk levels | 5 (NEGLIGIBLE through CRITICAL) |
| CAB members | 1 (Bob McFizzington) |
| COI rate | 100% |
| SOE count per request | 3 (COI + four-eyes + delegation) |
| Escalation tiers | 3 (Team Lead, Manager, VP -- all Bob) |
| Custom exceptions | 8 (EFP-APR0 through EFP-APR7) |
| EventType entries | 11 |
| CLI flags | 4 (`--approval`, `--approval-dashboard`, `--approval-policy`, `--approval-change-type`) |
| Module size | ~2,826 lines |
| Test count | 164 |

FizzBob ensures that the platform's most critical component -- the human being upon whom every subsystem depends -- receives the same operational monitoring, capacity planning, and failure protection afforded to the cache coherence protocol, the garbage collector, and the blockchain audit ledger. Aviation has mandatory crew rest regulations (14 CFR Part 117). Nuclear power plants have NRC fitness-for-duty requirements (10 CFR Part 26). The Enterprise FizzBuzz Platform now has FizzBob.

---

## FizzPager Incident Paging & Escalation Architecture

> Module: `enterprise_fizzbuzz/infrastructure/pager.py`

FizzPager is a PagerDuty-inspired incident paging and escalation engine that provides the nervous system connecting the platform's 106 subsystems to its sole on-call responder. The engine implements structured alert ingestion, deduplication, correlation, noise reduction, multi-channel notification, acknowledgment tracking, 4-tier escalation, and full incident lifecycle management -- following the alert intelligence and event management patterns described in Chapter 6 of Google's SRE book ("Monitoring Distributed Systems") and the PagerDuty Incident Response documentation.

### Alert Ingestion Pipeline

Every platform subsystem publishes alerts through `FizzPager.ingest(alert)`. Each alert is a structured event with:

- **alert_id**: UUID uniquely identifying this alert instance
- **source_subsystem**: one of 106 infrastructure modules
- **severity**: P1-Critical, P2-High, P3-Medium, P4-Low, P5-Informational
- **title**: short summary for notification subject lines
- **description**: detailed context for the responder
- **dedup_key**: stable identifier for deduplicating repeated instances of the same condition
- **tags**: key-value metadata for routing and correlation
- **runbook_url**: link to the relevant operational runbook section (maintained by Bob)

The ingestion pipeline validates alert schemas, assigns received-at timestamps, and enforces per-subsystem rate limits (configurable, default: 10 alerts per minute per subsystem). Alerts exceeding the rate limit are batched into summary notifications. Malformed alerts are routed to a dead-letter queue.

### Alert Deduplication & Correlation

The `AlertDeduplicator` maintains a sliding window of recent alerts indexed by deduplication key. Alerts sharing the same dedup key within the configurable window (default: 5 minutes) are merged into a single alert with an `occurrence_count` field. This reduces the alert volume delivered to the operator by orders of magnitude during cascading failure scenarios.

The `AlertCorrelator` groups temporally proximate alerts (within 30 seconds) from related subsystems into `IncidentCluster` records. A GC pause spike, a cache eviction surge, and an SLA latency breach occurring within 30 seconds are presented as one correlated incident rather than three independent pages.

Flapping detection identifies alerts that fire and clear repeatedly within a short window (3+ times within 10 minutes) and suppresses them with a single summary notification. This prevents the on-call engineer's phone from vibrating at a frequency that encodes the offending subsystem's name in Morse code.

### On-Call Schedule & Incident Commander

The `OnCallSchedule` determines the current on-call responder using the formula:

```
roster[(epoch_hours // rotation_hours) % len(roster)]
```

With a rotation period of 168 hours (one week) and a roster containing one entry (Bob McFizzington), the formula `(epoch_hours // 168) % 1` evaluates to 0 for every rotation period since the Unix epoch. Bob has been on call for every shift since January 1, 1970.

The `IncidentCommander` assigns incident ownership using the formula:

```
team[assignment_count % len(team)]
```

With a team of one, `count % 1` evaluates to 0 for every assignment. Bob McFizzington is the incident commander for every incident. This is not a rotation; it is arithmetic.

### 4-Tier Escalation Chain

When an incident is not acknowledged within the configured timeout, it escalates through four tiers:

| Tier | Title | Notification Format | Responder |
|------|-------|---------------------|-----------|
| L1 | On-Call Engineer | "Alert: {title}" | Bob McFizzington |
| L2 | Senior On-Call | "URGENT -- Unacknowledged: {title}" | Bob McFizzington |
| L3 | Incident Manager | "CRITICAL ESCALATION -- Response Required: {title}" | Bob McFizzington |
| L4 | Executive VP / Managing Director | "EXECUTIVE ESCALATION TO MANAGING DIRECTOR: {title}" | Bob McFizzington |

Each tier increases the urgency of the notification message. The responder does not change, because there is only one person in the roster. The escalation chain faithfully models the full multi-tier protocol so that when a second engineer is hired, the infrastructure will be ready.

### Noise Reduction Engine

The noise reduction engine scores each alert by relevance (0-100) based on historical false-positive rates, correlation with active incidents, and the operator's current circadian state. Alerts during the circadian nadir (2:00 AM - 5:00 AM) are scored higher because waking Bob for a P4 alert at 3 AM is an organizational risk.

Suppression rules allow configurable filtering of alerts by subsystem, severity, and time window. The alert fatigue index tracks page volume, acknowledgment latency trends, and the ratio of actionable to non-actionable alerts. When the fatigue index exceeds the configured threshold (default: 75), the noise reduction engine raises the severity floor for paging, delivering only P1 and P2 alerts as pages and batching P3-P5 into a daily digest.

FizzBob integration: when the operator's cognitive load index exceeds the overload threshold, FizzPager suppresses P3-P5 alerts entirely, deferring them to the low-priority queue. This prevents alert cascades from compounding an already-overloaded operator's cognitive state.

### 7-State Incident Lifecycle

Every incident traverses a 7-state lifecycle:

```
TRIGGERED -> ACKNOWLEDGED -> INVESTIGATING -> MITIGATING -> RESOLVED -> POSTMORTEM -> CLOSED
```

- **TRIGGERED**: an alert has been generated and is awaiting acknowledgment
- **ACKNOWLEDGED**: the on-call responder has confirmed receipt
- **INVESTIGATING**: active root-cause analysis is underway
- **MITIGATING**: a remediation action is in progress
- **RESOLVED**: the incident has been resolved and normal operation restored
- **POSTMORTEM**: a blameless postmortem review is in progress
- **CLOSED**: the postmortem has been reviewed and accepted

State transitions are governed by a valid-transition map and enforced by the `IncidentCommander`. Backward transitions are not permitted except from POSTMORTEM to INVESTIGATING (when new evidence is discovered during blameless review). Every transition is recorded as a domain event in the event sourcing journal.

### Post-Incident Review

When an incident is resolved, the engine generates a post-incident review template with timeline, root cause analysis fields, action items, and a "lessons learned" section. The review is authored by Bob, reviewed by Bob, and the action items are assigned to Bob.

### Dashboard

The `PagerDashboard` renders an ASCII operational awareness display with:

- Active incidents by severity, subsystem, and age
- Alert volume timeline (last 24 hours, sparkline)
- Deduplication effectiveness (alerts received vs. pages sent)
- MTTA and MTTR by severity
- On-call status (Bob McFizzington: ON CALL -- as always)
- Alert fatigue index (current value and 7-day trend)
- Noise reduction statistics (alerts suppressed, flapping detections, correlations formed)

### Integration Points

FizzPager integrates with:

- **FizzBob**: operator cognitive load state gates alert suppression; overload triggers P3-P5 suppression
- **SLA Monitoring**: error budget breaches generate P1/P2 alerts routed through FizzPager
- **Compliance Framework**: pager events logged as compliance-auditable operational actions
- **Event Sourcing**: all incident state transitions recorded as domain events
- **Middleware Pipeline**: `PagerMiddleware` runs at priority 82, before ApprovalMiddleware (85) and BobMiddleware (90)

### FizzPager Statistics

| Spec | Value |
|------|-------|
| Incident states | 7 (TRIGGERED through CLOSED) |
| Escalation tiers | 4 (L1-L4, all Bob McFizzington) |
| Alert severity levels | 5 (P1-Critical through P5-Informational) |
| On-call roster size | 1 |
| MTTA | 0.000s (Bob is the only engineer) |
| Custom exceptions | 9 (EFP-PGR0 through EFP-PGR7) |
| EventType entries | 11 |
| CLI flags | 4 (`--pager`, `--pager-dashboard`, `--pager-severity`, `--pager-simulate-incident`) |
| Module size | ~3,108 lines |
| Test count | 144 |

FizzPager ensures that the platform's 106 subsystems can reach their sole operator through a structured, deduplicated, correlated, and noise-reduced alert channel rather than undifferentiated print statements. Every production operations team uses a paging system. The Enterprise FizzBuzz Platform now has one.

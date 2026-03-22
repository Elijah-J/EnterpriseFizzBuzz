# Configuration Reference

Enterprise FizzBuzz Platform v1.0.0

This document is the authoritative reference for every configuration surface in the Enterprise FizzBuzz Platform. It covers YAML keys, environment variable overrides, CLI flags, feature flag definitions, and the `.fizztranslation` file format specification.

---

## Table of Contents

1. [Configuration Precedence](#configuration-precedence)
2. [YAML Configuration Reference](#yaml-configuration-reference)
   - [application](#application)
   - [range](#range)
   - [rules](#rules)
   - [engine](#engine)
   - [output](#output)
   - [logging](#logging)
   - [middleware](#middleware)
   - [plugins](#plugins)
   - [circuit_breaker](#circuit_breaker)
   - [i18n](#i18n)
   - [tracing](#tracing)
   - [rbac](#rbac)
   - [event_sourcing](#event_sourcing)
   - [chaos](#chaos)
   - [feature_flags](#feature_flags)
   - [sla](#sla)
   - [cache](#cache)
   - [migrations](#migrations)
   - [repository](#repository)
   - [ml](#ml)
   - [di](#di)
   - [observers](#observers)
3. [Feature Flag Schema](#feature-flag-schema)
4. [The .fizztranslation File Format](#the-fizztranslation-file-format)

---

## Configuration Precedence

Configuration values are resolved in the following order, from highest to lowest priority:

1. **CLI flag** (e.g., `--format json`)
2. **Environment variable** (e.g., `EFP_OUTPUT_FORMAT=json`)
3. **YAML file** (`config.yaml`)
4. **Hardcoded default** (in `ConfigurationManager._get_defaults()`)

A CLI flag always wins. An environment variable overrides the YAML file but yields to a CLI flag. If none of the above are set, the hardcoded default applies. This is the same precedence model used by every enterprise platform, because it was good enough for 12-factor apps and it is good enough for FizzBuzz.

The YAML configuration file path itself is resolved as: `--config` CLI flag > `EFP_CONFIG_PATH` environment variable > `config.yaml` in the project root.

**Source:** `ConfigurationManager` in `enterprise_fizzbuzz/infrastructure/config.py`.

---

## YAML Configuration Reference

All keys are documented as they appear in `config.yaml`. Types, defaults, environment variable overrides, and CLI flags are listed for each key.

### application

Application metadata. Informational only; does not affect evaluation behavior.

| Key | Type | Default | Description |
|---|---|---|---|
| `application.name` | string | `"Enterprise FizzBuzz Platform"` | Display name of the platform |
| `application.version` | string | `"1.0.0"` | Semantic version string |
| `application.environment` | string | `"production"` | Deployment environment label |

No environment variable overrides. No CLI flags.

### range

Defines the numeric range for FizzBuzz evaluation.

| Key | Type | Default | Env Var | CLI Flag |
|---|---|---|---|---|
| `range.start` | int | `1` | `EFP_RANGE_START` | `--range START END` (positional pair) |
| `range.end` | int | `100` | `EFP_RANGE_END` | `--range START END` (positional pair) |

**Validation:** `start` must be less than or equal to `end`. Both must be integers.

### rules

An ordered list of rule definitions. Each rule specifies a divisibility check to apply during evaluation.

| Field | Type | Default | Description |
|---|---|---|---|
| `rules[].name` | string | -- | Rule class name (e.g., `"FizzRule"`) |
| `rules[].divisor` | int | -- | The divisor for the modulo check |
| `rules[].label` | string | -- | Output label when the rule matches (e.g., `"Fizz"`) |
| `rules[].priority` | int | `0` | Evaluation priority (lower = higher priority) |

The default configuration ships with `FizzRule` (divisor 3, priority 1) and `BuzzRule` (divisor 5, priority 2). Rules are defined exclusively in YAML; there are no environment variable overrides or CLI flags.

### engine

Controls the evaluation engine strategy and concurrency limits.

| Key | Type | Default | Env Var | CLI Flag |
|---|---|---|---|---|
| `engine.strategy` | string | `"standard"` | `EFP_STRATEGY` | `--strategy STRATEGY` |
| `engine.max_concurrent_evaluations` | int | `10` | -- | -- |
| `engine.timeout_ms` | int | `5000` | -- | -- |

**Valid strategies:** `standard`, `chain_of_responsibility`, `parallel_async`, `machine_learning`.

The `--async` CLI flag selects the `parallel_async` strategy without requiring `--strategy`.

### output

Controls how FizzBuzz results are rendered.

| Key | Type | Default | Env Var | CLI Flag |
|---|---|---|---|---|
| `output.format` | string | `"plain"` | `EFP_OUTPUT_FORMAT` | `--format FORMAT` |
| `output.include_metadata` | bool | `false` | -- | `--metadata` |
| `output.include_summary` | bool | `true` | -- | `--no-summary` (inverts) |
| `output.colorize` | bool | `false` | -- | -- |

**Valid formats:** `plain`, `json`, `xml`, `csv`.

### logging

Controls the platform's logging subsystem.

| Key | Type | Default | Env Var | CLI Flag |
|---|---|---|---|---|
| `logging.level` | string | `"INFO"` | `EFP_LOG_LEVEL` | `--debug` (sets to `DEBUG`), `--verbose` (enables console observer) |
| `logging.include_timestamps` | bool | `true` | -- | -- |
| `logging.log_to_file` | bool | `false` | -- | -- |
| `logging.log_file_path` | string | `"fizzbuzz.log"` | -- | -- |

**Valid levels:** `SILENT`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, `TRACE`.

### middleware

Configures the middleware pipeline. Each middleware has an `enabled` flag and a `priority` number. Lower priority numbers execute first.

| Key | Type | Default | Description |
|---|---|---|---|
| `middleware.timing.enabled` | bool | `true` | Enable the `TimingMiddleware` |
| `middleware.timing.priority` | int | `1` | Execution order for timing |
| `middleware.logging.enabled` | bool | `true` | Enable the `LoggingMiddleware` |
| `middleware.logging.priority` | int | `2` | Execution order for logging |
| `middleware.validation.enabled` | bool | `true` | Enable the `ValidationMiddleware` |
| `middleware.validation.priority` | int | `0` | Execution order for validation |

No environment variable overrides. No CLI flags. Middleware configuration is YAML-only.

### plugins

Controls the plugin discovery and loading subsystem.

| Key | Type | Default | Description |
|---|---|---|---|
| `plugins.auto_discover` | bool | `true` | Automatically scan for plugins at startup |
| `plugins.plugin_directory` | string | `"./plugins"` | Directory to scan for plugin modules |
| `plugins.enabled_plugins` | list[string] | `[]` | Explicit list of plugin names to load |

No environment variable overrides. No CLI flags.

### circuit_breaker

Protects the FizzBuzz evaluation pipeline from cascading failures by monitoring error rates and temporarily rejecting requests when the system is unhealthy.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `circuit_breaker.enabled` | bool | `false` | `--circuit-breaker` |
| `circuit_breaker.failure_threshold` | int | `5` | -- |
| `circuit_breaker.success_threshold` | int | `3` | -- |
| `circuit_breaker.timeout_ms` | int | `30000` | -- |
| `circuit_breaker.sliding_window_size` | int | `10` | -- |
| `circuit_breaker.half_open_max_calls` | int | `3` | -- |
| `circuit_breaker.backoff_base_ms` | int | `1000` | -- |
| `circuit_breaker.backoff_max_ms` | int | `60000` | -- |
| `circuit_breaker.backoff_multiplier` | float | `2.0` | -- |
| `circuit_breaker.ml_confidence_threshold` | float | `0.7` | -- |
| `circuit_breaker.call_timeout_ms` | int | `5000` | -- |

The `--circuit-status` flag displays the circuit breaker dashboard after execution. No environment variable overrides.

### i18n

Controls the locale-aware translation subsystem. The platform ships with seven locales: English (`en`), German (`de`), French (`fr`), Japanese (`ja`), Klingon (`tlh`), Sindarin (`sjn`), and Quenya (`qya`).

| Key | Type | Default | Env Var | CLI Flag |
|---|---|---|---|---|
| `i18n.enabled` | bool | `true` | -- | -- |
| `i18n.locale` | string | `"en"` | `EFP_LOCALE` | `--locale LOCALE` |
| `i18n.locale_directory` | string | `"./locales"` | -- | -- |
| `i18n.strict_mode` | bool | `false` | -- | -- |
| `i18n.fallback_chain` | list[string] | `["en"]` | -- | -- |
| `i18n.log_missing_keys` | bool | `true` | -- | -- |

The `--list-locales` flag displays all available locales and exits. When `strict_mode` is `true`, missing keys raise `TranslationKeyError` instead of returning the key string. The `fallback_chain` is appended after any per-locale `@fallback` directive.

### tracing

OpenTelemetry-style distributed tracing for full pipeline observability.

| Key | Type | Default | Env Var | CLI Flag |
|---|---|---|---|---|
| `tracing.enabled` | bool | `false` | `EFP_TRACING_ENABLED` | `--trace` |
| `tracing.export_format` | string | `"waterfall"` | -- | `--trace` (waterfall) / `--trace-json` (json) |
| `tracing.waterfall_width` | int | `60` | -- | -- |
| `tracing.timing_precision` | string | `"us"` | -- | -- |

**Valid export formats:** `waterfall`, `json`.
**Valid timing precisions:** `us` (microseconds), `ns` (nanoseconds).

The `EFP_TRACING_ENABLED` environment variable accepts `true`, `1`, or `yes` (case-insensitive) to enable tracing.

### rbac

Role-Based Access Control. Controls who can FizzBuzz what.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `rbac.enabled` | bool | `false` | `--user` or `--token` (implicitly enables) |
| `rbac.default_role` | string | `"ANONYMOUS"` | `--role ROLE` |
| `rbac.token_secret` | string | `"enterprise-fizzbuzz-secret-do-not-share"` | -- |
| `rbac.token_ttl_seconds` | int | `3600` | -- |
| `rbac.token_issuer` | string | `"enterprise-fizzbuzz-platform"` | -- |
| `rbac.access_denied_contact_email` | string | `"fizzbuzz-security@enterprise.example.com"` | -- |
| `rbac.next_training_session` | string | `"2026-04-01T09:00:00Z"` | -- |

Additional CLI flags: `--user USERNAME` (trust-mode auth), `--role ROLE` (valid: `ANONYMOUS`, `VIEWER`, `EVALUATOR`, `ADMIN`, `SUPERADMIN`), `--token TOKEN` (signed EFP token auth). No environment variable overrides.

### event_sourcing

Append-only audit log with CQRS, point-in-time reconstruction, and materialized projections.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `event_sourcing.enabled` | bool | `false` | `--event-sourcing` |
| `event_sourcing.snapshot_interval` | int | `10` | -- |
| `event_sourcing.max_events_before_compaction` | int | `1000` | -- |
| `event_sourcing.enable_temporal_queries` | bool | `true` | -- |
| `event_sourcing.enable_projections` | bool | `true` | -- |
| `event_sourcing.event_version` | int | `1` | -- |

Additional CLI flags: `--replay` (rebuild projections from event log), `--temporal-query SEQ` (reconstruct state at a specific sequence number). No environment variable overrides.

### chaos

Chaos Engineering fault injection subsystem.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `chaos.enabled` | bool | `false` | `--chaos` |
| `chaos.level` | int | `1` | `--chaos-level N` |
| `chaos.fault_types` | list[string] | (see below) | -- |
| `chaos.latency.min_ms` | int | `10` | -- |
| `chaos.latency.max_ms` | int | `500` | -- |
| `chaos.seed` | int or null | `null` | -- |

**Default fault types:** `RESULT_CORRUPTION`, `LATENCY_INJECTION`, `EXCEPTION_INJECTION`, `RULE_ENGINE_FAILURE`, `CONFIDENCE_MANIPULATION`.

Additional CLI flags: `--gameday SCENARIO` (run a Game Day; valid: `modulo_meltdown`, `confidence_crisis`, `slow_burn`, `total_chaos`; defaults to `total_chaos`), `--post-mortem` (generate satirical incident report). No environment variable overrides.

### feature_flags

Progressive rollout and feature toggle subsystem. See [Feature Flag Schema](#feature-flag-schema) for the `predefined_flags` definition format.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `feature_flags.enabled` | bool | `false` | `--feature-flags` |
| `feature_flags.default_lifecycle` | string | `"ACTIVE"` | -- |
| `feature_flags.log_evaluations` | bool | `true` | -- |
| `feature_flags.strict_dependencies` | bool | `true` | -- |
| `feature_flags.predefined_flags` | object | (see below) | `--flag NAME=VALUE` (per-flag override) |

Additional CLI flags: `--flag NAME=VALUE` (repeatable; override a specific flag), `--list-flags` (display all flags and exit). No environment variable overrides.

### sla

SLA monitoring with PagerDuty-style alerting and error budget tracking.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `sla.enabled` | bool | `false` | `--sla` |
| `sla.slos.latency.target` | float | `0.999` | -- |
| `sla.slos.latency.threshold_ms` | float | `100.0` | -- |
| `sla.slos.accuracy.target` | float | `0.99999` | -- |
| `sla.slos.availability.target` | float | `0.9999` | -- |
| `sla.error_budget.window_days` | int | `30` | -- |
| `sla.error_budget.burn_rate_threshold` | float | `2.0` | -- |
| `sla.alerting.cooldown_seconds` | int | `60` | -- |
| `sla.alerting.escalation_timeout_seconds` | int | `300` | -- |
| `sla.on_call.team_name` | string | `"FizzBuzz Reliability Engineering"` | -- |
| `sla.on_call.rotation_interval_hours` | int | `168` | -- |
| `sla.on_call.engineers` | list[object] | (see below) | -- |

The default on-call roster contains one engineer: Bob McFizzington (`bob.mcfizzington@enterprise.example.com`, `+1-555-FIZZBUZZ`), Senior Principal Staff FizzBuzz Reliability Engineer II.

Additional CLI flags: `--sla-dashboard` (display SLA dashboard after execution), `--on-call` (display on-call status and escalation chain). No environment variable overrides.

### cache

In-memory caching layer with MESI coherence protocol and cache eulogies.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `cache.enabled` | bool | `false` | `--cache` |
| `cache.max_size` | int | `1024` | `--cache-size N` |
| `cache.ttl_seconds` | float | `3600.0` | -- |
| `cache.eviction_policy` | string | `"lru"` | `--cache-policy POLICY` |
| `cache.enable_coherence_protocol` | bool | `true` | -- |
| `cache.enable_eulogies` | bool | `true` | -- |
| `cache.warming.enabled` | bool | `false` | `--cache-warm` |
| `cache.warming.range_start` | int | `1` | -- |
| `cache.warming.range_end` | int | `100` | -- |

**Valid eviction policies:** `lru`, `lfu`, `fifo`, `dramatic_random`.

The `--cache-stats` flag displays the cache statistics dashboard after execution. No environment variable overrides.

### migrations

Database migration framework for in-memory data structures that vanish when the process exits.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `migrations.enabled` | bool | `false` | `--migrate` |
| `migrations.auto_apply` | bool | `false` | -- |
| `migrations.seed_range_start` | int | `1` | -- |
| `migrations.seed_range_end` | int | `50` | -- |
| `migrations.log_fake_sql` | bool | `true` | -- |
| `migrations.visualize_schema` | bool | `true` | -- |

Additional CLI flags: `--migrate-status` (display migration dashboard), `--migrate-rollback N` (roll back last N migrations, default 1), `--migrate-seed` (generate FizzBuzz seed data). No environment variable overrides.

### repository

Persistence backend selection for the Repository Pattern + Unit of Work implementation.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `repository.backend` | string | `"none"` | `--repository BACKEND` |
| `repository.db_path` | string | `"fizzbuzz_results.db"` | `--db-path PATH` |
| `repository.fs_path` | string | `"./fizzbuzz_results"` | `--results-dir PATH` |

**Valid backends:** `none`, `in_memory`, `sqlite`, `filesystem`.

No environment variable overrides.

### ml

Anti-Corruption Layer configuration for the ML evaluation strategy. These thresholds govern how raw neural network outputs are translated into domain-level classification decisions.

| Key | Type | Default | Description |
|---|---|---|---|
| `ml.decision_threshold` | float | `0.5` | Confidence above which a sigmoid output counts as a match |
| `ml.ambiguity_margin` | float | `0.1` | Margin around the threshold for ambiguity detection |
| `ml.enable_disagreement_tracking` | bool | `false` | Cross-check ML predictions against deterministic baseline |

No environment variable overrides. No CLI flags.

### di

Dependency Injection Container configuration. The container provides a parallel universe of object construction.

| Key | Type | Default | Description |
|---|---|---|---|
| `di.enabled` | bool | `false` | Master switch for the DI container |
| `di.default_lifetime` | string | `"transient"` | Default lifetime for auto-registered services |
| `di.cycle_detection` | bool | `true` | Validate dependency graph at registration time |
| `di.verbose_resolution_logging` | bool | `false` | Log every `resolve()` call |

No environment variable overrides. No CLI flags.

### observers

Controls the event bus observer subsystem.

| Key | Type | Default | CLI Flag |
|---|---|---|---|
| `observers.console_observer.enabled` | bool | `false` | `--verbose` (enables) |
| `observers.statistics_observer.enabled` | bool | `true` | -- |

No environment variable overrides.

---

## Feature Flag Schema

Feature flags are defined under `feature_flags.predefined_flags` in `config.yaml`. Each flag is a named object with the following schema:

### Common Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes | Flag type: `BOOLEAN`, `PERCENTAGE`, or `TARGETING` |
| `enabled` | bool | yes | Whether the flag is currently active |
| `description` | string | no | Human-readable description for dashboards and auditing |
| `dependencies` | list[string] | no | List of flag names that must be enabled for this flag to evaluate as true |

### Type: BOOLEAN

A simple on/off toggle. The flag evaluates to its `enabled` value for all inputs.

### Type: PERCENTAGE

Progressive rollout. The flag evaluates to `true` for a percentage of inputs, determined by hashing the input value against the configured percentage.

| Field | Type | Required | Description |
|---|---|---|---|
| `percentage` | int (0-100) | yes | Percentage of inputs for which the flag evaluates to true |

### Type: TARGETING

Conditional activation based on a targeting rule. The flag evaluates to `true` only for inputs that match the targeting criteria.

| Field | Type | Required | Description |
|---|---|---|---|
| `targeting_rule` | string | yes | Targeting rule identifier (e.g., `"prime"`) |

### Dependency Graph

When `feature_flags.strict_dependencies` is `true` (the default), the flag evaluation engine enforces dependency constraints. A flag with dependencies will only evaluate to `true` if all of its dependencies also evaluate to `true`. Circular dependencies are detected at registration time.

### Predefined Flags (Defaults)

| Flag Name | Type | Enabled | Key Parameters |
|---|---|---|---|
| `fizz_rule_enabled` | BOOLEAN | `true` | -- |
| `buzz_rule_enabled` | BOOLEAN | `true` | -- |
| `wuzz_rule_experimental` | PERCENTAGE | `true` | `percentage: 30` |
| `wuzz_prime_targeting` | TARGETING | `true` | `targeting_rule: "prime"`, depends on `wuzz_rule_experimental` |
| `ml_strategy_canary` | PERCENTAGE | `false` | `percentage: 10` |
| `blockchain_audit` | BOOLEAN | `false` | -- |
| `tracing_enabled` | BOOLEAN | `false` | -- |

### Runtime Overrides

Flags can be overridden at runtime via the `--flag` CLI argument:

```bash
python main.py --feature-flags --flag wuzz_rule_experimental=true --flag ml_strategy_canary=false
```

---

## The .fizztranslation File Format

The `.fizztranslation` format is a proprietary configuration language purpose-built for Enterprise FizzBuzz localization. It was designed because JSON lacked gravitas, YAML was too mainstream, and TOML did not support heredocs. The format is parsed by `FizzTranslationParser` in `enterprise_fizzbuzz/infrastructure/i18n.py` using a three-state state machine (`METADATA`, `SECTION`, `HEREDOC`).

Locale files are stored in the `locales/` directory and loaded by `LocaleManager.load_all()`.

### File Structure

A `.fizztranslation` file consists of three regions, in order:

1. **Metadata directives** (before any section header)
2. **Section blocks** (one or more)
3. Optionally, additional metadata directives (allowed anywhere, but conventionally placed at the top)

### Comments

Lines beginning with `;;` or `#` are comments and are ignored by the parser. Inline comments are not supported.

### Metadata Directives

Metadata directives appear at the top of the file, before any section header. They use the `@key = value` syntax.

| Directive | Required | Description |
|---|---|---|
| `@locale` | yes | ISO 639 locale code (e.g., `en`, `fr`, `tlh`, `sjn`, `qya`) |
| `@name` | yes | Human-readable locale name (e.g., `English`, `Klingon`) |
| `@fallback` | yes | Fallback locale code, or `none` for the root locale |
| `@plural_rule` | no | Plural rule expression (default: `n != 1`) |

Example: `@locale = fr`, `@name = French`, `@fallback = en`, `@plural_rule = n > 1`.

The `@plural_rule` directive accepts a boolean expression where `n` is the count. If it evaluates to `true`, the form is `"other"`; otherwise `"one"`. The special value `0` always returns `"other"` (no grammatical plural).

Built-in plural rules:

| Locale | Rule | Behavior |
|---|---|---|
| `en`, `de`, `tlh`, `sjn`, `qya` | `n != 1` | 1 = singular, everything else = plural |
| `fr` | `n > 1` | 0 and 1 = singular, 2+ = plural |
| `ja` | `0` | Always plural (no grammatical distinction) |

### Section Headers

Sections are delimited by `[section_name]` headers. All key-value pairs following a section header belong to that section until the next header or end of file.

**Standard sections:**

| Section | Purpose |
|---|---|
| `[labels]` | FizzBuzz output labels (e.g., `Fizz = Fizz`) |
| `[plurals]` | Plural form definitions |
| `[messages]` | UI messages with variable interpolation |
| `[summary]` | Session summary field labels |
| `[banner]` | Startup banner text |
| `[status]` | Status display labels |

All sections are optional. The parser does not enforce a fixed set of section names.

### Key-Value Pairs

Within a section, entries use `key = value` syntax. Keys are stored internally as `section.key` (e.g., `labels.Fizz`). Lookups via `LocaleManager.t()` use the fully-qualified dotted form.

### Plural Entries

Plural entries use the pattern `Base.plural.FORM = value` within the `[plurals]` section, where `FORM` is one of: `one`, `other`, `zero`, `few`, `many`, `two`. Example: `Fizz.plural.one = ${count} Fizz`.

### Variable Interpolation

Values may contain `${variable}` placeholders, replaced at lookup time via keyword arguments: `manager.t("messages.evaluating", start=1, end=100)`. Interpolation is simple string replacement with no expression evaluation.

### Heredoc Syntax

For multi-line values, a value beginning with `<<TERMINATOR` causes the parser to accumulate all subsequent lines until `TERMINATOR` appears on a line by itself. The terminator string is arbitrary (`EOF`, `END`, etc.). Whitespace is stripped before comparison. An unterminated heredoc raises `FizzTranslationParseError`. Example: `welcome = <<EOF` followed by content lines, terminated by a lone `EOF`.

### Legacy Format Compatibility

The parser supports two v1 formats for backward compatibility: `@@key: value` metadata and `>> dotted.key = value` entries with automatic section mapping (e.g., `fizz.label` to `labels.Fizz`, `status.*` to `messages.*`). These are supported but not recommended for new files.

**Canonical example:** `locales/en.fizztranslation`. **Parser source:** `FizzTranslationParser` in `enterprise_fizzbuzz/infrastructure/i18n.py`.

# Developer Guide

A practical guide for extending the Enterprise FizzBuzz Platform. This document assumes you have the codebase checked out, can run `python -m pytest`, and are ready to contribute to the most thoroughly engineered FizzBuzz implementation in recorded history.

Every walkthrough below references real file paths, real class names, and real method signatures. If you follow the steps and something doesn't work, the documentation is wrong -- not you. (But also check your imports.)

---

## Table of Contents

1. [Project Structure at a Glance](#1-project-structure-at-a-glance)
2. [Adding a New Rule](#2-adding-a-new-rule)
3. [Adding a New Middleware](#3-adding-a-new-middleware)
4. [Adding a New Locale](#4-adding-a-new-locale)
5. [Adding a New Evaluation Strategy](#5-adding-a-new-evaluation-strategy)
6. [Adding a New CLI Flag](#6-adding-a-new-cli-flag)
7. [Running Tests](#7-running-tests)

---

## 1. Project Structure at a Glance

The codebase follows hexagonal architecture with three layers. The dependency rule is **inward only** -- infrastructure depends on application, application depends on domain, never the reverse.

```
enterprise_fizzbuzz/
  domain/
    interfaces.py      # Abstract contracts (IRule, IRuleEngine, IMiddleware, etc.)
    models.py          # Value objects, enums, dataclasses
    exceptions.py      # All 69 custom exception classes
  application/
    factory.py         # Rule factories (StandardRuleFactory, ConfigurableRuleFactory, CachingRuleFactory)
    fizzbuzz_service.py  # FizzBuzzService + FizzBuzzServiceBuilder
    ports.py           # Abstract ports (StrategyPort, AbstractUnitOfWork)
  infrastructure/
    rules_engine.py    # ConcreteRule, StandardRuleEngine, ChainOfResponsibilityEngine, etc.
    middleware.py       # MiddlewarePipeline + built-in middleware
    config.py          # ConfigurationManager singleton
    i18n.py            # Locale system (parser, catalog, manager)
    ml_engine.py       # Neural network evaluation strategy
    auth.py            # RBAC, token engine, AuthorizationMiddleware
    ...and many more
  __main__.py          # CLI entry point, flag definitions, wiring
```

Configuration lives in three places, in precedence order (highest wins):
1. CLI flags (defined in `__main__.py` via `argparse`)
2. Environment variables (`EFP_*`, mapped in `config.py`)
3. `config.yaml` at the project root

Locale files live in `locales/*.fizztranslation`.

Tests live in `tests/`, with contract tests in `tests/contracts/`.

---

## 2. Adding a New Rule

Let's say you want to add "Wuzz" for divisor 7. (The platform already has this as a feature-flagged experimental rule, but let's walk through making it a first-class citizen.)

### Step 1: Define the rule in `config.yaml`

Open `config.yaml` and add an entry to the `rules` list:

```yaml
rules:
  - name: "FizzRule"
    divisor: 3
    label: "Fizz"
    priority: 1
  - name: "BuzzRule"
    divisor: 5
    label: "Buzz"
    priority: 2
  - name: "WuzzRule"      # <-- new
    divisor: 7
    label: "Wuzz"
    priority: 3
```

**File:** `config.yaml`, under the `rules` key.

**What the fields mean:**
- `name`: A human-readable identifier. Convention is `<Label>Rule`.
- `divisor`: The number to check divisibility against.
- `label`: The string emitted when the rule matches. This is what appears in output and what the i18n system translates.
- `priority`: Evaluation order. Lower numbers run first. When multiple rules match (e.g., a number divisible by both 3 and 7), their labels are concatenated in priority order. If FizzRule has priority 1 and WuzzRule has priority 3, the output for 21 would be "FizzWuzz".

That's it for the basic rule. The `ConfigurationManager.rules` property (in `enterprise_fizzbuzz/infrastructure/config.py`, line ~392) reads these entries and converts them into `RuleDefinition` dataclasses:

```python
@property
def rules(self) -> list[RuleDefinition]:
    return [
        RuleDefinition(
            name=r["name"],
            divisor=r["divisor"],
            label=r["label"],
            priority=r.get("priority", 0),
        )
        for r in self._raw_config.get("rules", [])
    ]
```

The `ConfigurableRuleFactory` in `enterprise_fizzbuzz/application/factory.py` then wraps each `RuleDefinition` in a `ConcreteRule` instance (from `enterprise_fizzbuzz/infrastructure/rules_engine.py`). `ConcreteRule.evaluate()` simply does `number % self._definition.divisor == 0`. No further registration is needed -- if it's in `config.yaml`, it's in the pipeline.

### Step 2: Add locale entries

Your new rule's label needs translations in all 7 `.fizztranslation` files. The locale files live in `locales/`:

```
locales/en.fizztranslation
locales/de.fizztranslation
locales/fr.fizztranslation
locales/ja.fizztranslation
locales/tlh.fizztranslation   (Klingon)
locales/sjn.fizztranslation   (Sindarin)
locales/qya.fizztranslation   (Quenya)
```

In each file, you need to add entries in two sections: `[labels]` and `[plurals]`.

**Example for `locales/en.fizztranslation`:**

```ini
[labels]
Wuzz = Wuzz

[plurals]
Wuzz.plural.one = ${count} Wuzz
Wuzz.plural.other = ${count} Wuzzes
```

The label key in `[labels]` **must match the `label` field** from your rule definition exactly. The `TranslationMiddleware` (in `enterprise_fizzbuzz/infrastructure/middleware.py`) looks up `labels.<label>` via `LocaleManager.get_label()`, so if your rule's label is `"Wuzz"`, the translation key is `labels.Wuzz`.

For plural forms, the convention is `<Label>.plural.one` and `<Label>.plural.other` in the `[plurals]` section. The `PluralizationEngine` (in `enterprise_fizzbuzz/infrastructure/i18n.py`) determines which form to use based on the locale's `@plural_rule` directive.

**Important:** You also need to add the label to `TranslationMiddleware._TRANSLATABLE_LABELS` in `enterprise_fizzbuzz/infrastructure/middleware.py`:

```python
class TranslationMiddleware(IMiddleware):
    _TRANSLATABLE_LABELS = {"Fizz", "Buzz", "FizzBuzz"}  # Add "Wuzz" and any combos
```

Without this, the translation middleware will not attempt to translate your new label -- it will pass through as-is. You'll also want to add combined labels like `"FizzWuzz"`, `"BuzzWuzz"`, `"FizzBuzzWuzz"` if you want those translated too, along with corresponding locale entries.

### Step 3: Update the ML training pipeline (if using ML strategy)

The ML engine (`enterprise_fizzbuzz/infrastructure/ml_engine.py`) trains a separate binary classifier for each rule. It does this automatically based on whatever rules are passed to `MachineLearningEngine.evaluate()`, so no code changes are needed -- the engine trains on first use. However, adding a new rule increases the training time (one more network to train) and the total parameter count.

The cyclical feature encoding (`sin(2*pi*n/d)` and `cos(2*pi*n/d)`) naturally handles any divisor, so divisor 7 will work out of the box. If you find the ML engine's accuracy unsatisfactory for your new divisor (you won't -- it achieves 100%), you can adjust the training hyperparameters in the `MachineLearningEngine` class.

### Step 4: Write tests

Add tests in `tests/test_fizzbuzz.py` or create a dedicated test file. At minimum, test:

1. **The rule itself:** Create a `ConcreteRule` with your `RuleDefinition` and verify it matches the correct numbers.
2. **Priority ordering:** Verify that when your rule and existing rules both match, labels are concatenated in priority order.
3. **Full pipeline integration:** Run the service with your rule in the config and verify end-to-end output.

```python
from enterprise_fizzbuzz.domain.models import RuleDefinition
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule

def test_wuzz_rule_matches_multiples_of_seven():
    rule = ConcreteRule(RuleDefinition(name="WuzzRule", divisor=7, label="Wuzz", priority=3))
    assert rule.evaluate(7) is True
    assert rule.evaluate(14) is True
    assert rule.evaluate(21) is True
    assert rule.evaluate(8) is False

def test_wuzz_rule_definition():
    defn = RuleDefinition(name="WuzzRule", divisor=7, label="Wuzz", priority=3)
    rule = ConcreteRule(defn)
    assert rule.get_definition() is defn
```

### Step 5: Feature flags (optional)

If you want your rule to be progressively rolled out rather than always-on, add a feature flag entry to `config.yaml` under `feature_flags.predefined_flags`:

```yaml
feature_flags:
  predefined_flags:
    wuzz_rule_experimental:
      type: "PERCENTAGE"
      enabled: true
      percentage: 30
      description: "Experimental Wuzz rule (divisor=7) -- 30% progressive rollout"
```

The `FlagMiddleware` (in `enterprise_fizzbuzz/infrastructure/feature_flags.py`) will then control whether the rule is active on a per-evaluation basis. The wiring that injects the Wuzz rule when feature flags are active is in `__main__.py` around line 1028.

---

## 3. Adding a New Middleware

Middleware components intercept every number evaluation, wrapping the core rule engine call. They can modify the `ProcessingContext` on the way in, the way out, or both. They can also short-circuit the pipeline entirely.

### Step 1: Implement the `IMiddleware` interface

The interface lives in `enterprise_fizzbuzz/domain/interfaces.py`:

```python
class IMiddleware(ABC):
    @abstractmethod
    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext: ...

    @abstractmethod
    def get_name(self) -> str: ...

    @abstractmethod
    def get_priority(self) -> int: ...
```

Three methods. No more, no less. Here's what they do:

- **`process(context, next_handler)`**: The main logic. You receive the current `ProcessingContext` and a callable that invokes the next middleware in the chain (or the final handler if you're last). You **must** call `next_handler(context)` to continue the pipeline, unless you're intentionally short-circuiting.
- **`get_name()`**: Returns a string identifier. Used for logging and the middleware name list.
- **`get_priority()`**: Returns an integer that determines execution order. **Lower numbers run first.** The pipeline sorts middleware by priority when you add them.

### Step 2: Write your middleware class

Place it in `enterprise_fizzbuzz/infrastructure/middleware.py` alongside the existing middleware, or in a new file under `infrastructure/` if it's complex enough to warrant one.

Here's a template:

```python
class AuditMiddleware(IMiddleware):
    """Middleware that logs every evaluation to an audit trail.

    Priority 5 ensures this runs after validation (0) and timing (1)
    but before translation (50).
    """

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        # --- Pre-processing (before the rule engine runs) ---
        context.metadata["audit_start"] = time.time()

        # --- Delegate to the rest of the pipeline ---
        result = next_handler(context)

        # --- Post-processing (after the rule engine runs) ---
        result.metadata["audit_end"] = time.time()
        result.metadata["audited"] = True

        return result

    def get_name(self) -> str:
        return "AuditMiddleware"

    def get_priority(self) -> int:
        return 5
```

### Step 3: Understand priority ordering

The existing middleware priorities are:

| Priority | Middleware              | What it does                                    |
|----------|-------------------------|-------------------------------------------------|
| -10      | `OTelMiddleware`        | FizzOTel distributed tracing spans               |
| -3       | `FlagMiddleware`        | Evaluates feature flags, disables rules          |
| -1       | `AuthorizationMiddleware` | Checks RBAC permissions                        |
| 0        | `ValidationMiddleware`  | Validates input range, type checks               |
| 1        | `TimingMiddleware`      | Records nanosecond-precision timing              |
| 2        | `LoggingMiddleware`     | Logs evaluation inputs and outputs               |
| 5        | `EventSourcingMiddleware` | Appends events to the event store              |
| 10       | `CircuitBreakerMiddleware` | Tracks failures, trips circuit breaker          |
| 15       | `CacheMiddleware`       | Checks/populates the result cache                |
| 20       | `ChaosMiddleware`       | Injects faults (latency, errors, corruption)     |
| 25       | `SLAMiddleware`         | Records SLA metrics (latency, accuracy)          |
| 50       | `TranslationMiddleware` | Translates labels to active locale               |

Pick a priority that makes sense for your middleware's role. If it needs to see raw, untranslated output, it should run before priority 50. If it needs timing data, it should run after priority 1.

### Step 4: Register it in the pipeline

There are two ways to get your middleware into the pipeline:

**Option A: Add it to the default middleware stack.**

In `enterprise_fizzbuzz/application/fizzbuzz_service.py`, the `FizzBuzzServiceBuilder.with_default_middleware()` method (line ~499) adds the standard trio:

```python
def with_default_middleware(self) -> FizzBuzzServiceBuilder:
    self._custom_middleware.extend([
        ValidationMiddleware(),
        TimingMiddleware(),
        LoggingMiddleware(),
    ])
    return self
```

Add your middleware here if it should always be active.

**Option B: Wire it conditionally in `__main__.py`.**

Most middleware in the platform is opt-in. The pattern in `__main__.py` is:

1. Check a CLI flag or config setting.
2. Instantiate the middleware with its dependencies.
3. Call `builder.with_middleware(your_middleware)`.

Example from `__main__.py` (around line 964):

```python
if cb_middleware is not None:
    builder.with_middleware(cb_middleware)
```

The `MiddlewarePipeline.add()` method (in `enterprise_fizzbuzz/infrastructure/middleware.py`, line ~224) handles sorting by priority automatically. You just add it; the pipeline figures out where it goes.

### Step 5: Write tests

Test your middleware in isolation by creating a mock `next_handler` and verifying:

1. It calls `next_handler` (unless it's supposed to short-circuit).
2. It modifies the `ProcessingContext` or its metadata as expected.
3. It returns the context from `next_handler` (possibly modified).
4. `get_name()` returns the expected string.
5. `get_priority()` returns the expected integer.

---

## 4. Adding a New Locale

The platform currently supports 7 locales: English (`en`), German (`de`), French (`fr`), Japanese (`ja`), Klingon (`tlh`), Sindarin (`sjn`), and Quenya (`qya`). Adding a new one requires creating a `.fizztranslation` file and nothing else -- the `LocaleManager` discovers locale files automatically.

### Step 1: Create the `.fizztranslation` file

Create a new file in `locales/` named `<code>.fizztranslation`, where `<code>` is the ISO 639-1 or ISO 639-3 language code.

**File:** `locales/es.fizztranslation` (for Spanish)

### Step 2: Add required metadata directives

Every `.fizztranslation` file must start with these `@`-prefixed directives:

```ini
;; Spanish -- Enterprise FizzBuzz Platform
;; Comments start with ;;

@locale = es
@name = Spanish
@fallback = en
@plural_rule = n != 1
```

- **`@locale`**: The locale code. Must match the filename (minus the extension).
- **`@name`**: Human-readable name, displayed in `--list-locales` output.
- **`@fallback`**: The locale to try when a key is missing. Usually `en`. Use `none` for the root locale (English itself uses `@fallback = none`).
- **`@plural_rule`**: A Python expression evaluated with `n` bound to the count. Returns truthy for "other" form, falsy for "one" form. Common rules:
  - `n != 1` -- English, German, Klingon, most languages
  - `n > 1` -- French (0 is singular in French)
  - `0` -- Japanese (always "other", no grammatical plural)

### Step 3: Add required sections

The canonical English locale (`locales/en.fizztranslation`) defines all sections that the platform uses. Your new locale should provide translations for at least `[labels]` and `[plurals]`. Other sections will fall back to the fallback locale if missing.

```ini
[labels]
Fizz = Fizz
Buzz = Buzz
FizzBuzz = FizzBuzz

[plurals]
Fizz.plural.one = ${count} Fizz
Fizz.plural.other = ${count} Fizzes
Buzz.plural.one = ${count} Buzz
Buzz.plural.other = ${count} Buzzes
FizzBuzz.plural.one = ${count} FizzBuzz
FizzBuzz.plural.other = ${count} FizzBuzzes

[messages]
evaluating = Evaluating FizzBuzz for range [${start}, ${end}]...
strategy = Strategy: ${name}
output_format = Output Format: ${name}
wall_clock = Wall clock time: ${time}ms

[summary]
title = FizzBuzz Session Summary
total_numbers = Total Numbers
processing_time = Processing
throughput = Throughput
numbers_per_second = numbers/sec
errors = Errors

[banner]
subtitle = E N T E R P R I S E   E D I T I O N

[status]
locale = Locale
```

**Variable interpolation** uses `${var}` syntax. The available variables for each key are determined by the code that calls `LocaleManager.t()` -- check the callsites if you need to know what variables are available.

**Heredoc syntax** is supported for multi-line values:

```ini
long_description = <<END
This is a multi-line value.
It continues until the terminator
appears on a line by itself.
END
```

### Step 4: Understand the fallback chain

When the `LocaleResolver` (in `enterprise_fizzbuzz/infrastructure/i18n.py`) can't find a key in the requested locale, it walks the fallback chain:

1. Try the requested locale (e.g., `es`).
2. Try the locale's `@fallback` (e.g., `en`).
3. Try the global fallback (always `en`).

The chain is built by `LocaleResolver.build_chain()` and respects cycles (it tracks visited locales to prevent infinite loops). If a key is missing from the entire chain, `LocaleManager.t()` returns the key itself as a graceful degradation -- unless strict mode is enabled, in which case it raises `TranslationKeyError`.

So you don't strictly _need_ to translate every key. Missing entries will fall back to English (or whatever your `@fallback` points to). But incomplete locales make Bob cry.

### Step 5: Test automatically

The `LocaleManager.load_all()` method (line ~644 of `i18n.py`) scans the `locales/` directory for all `*.fizztranslation` files, so your new locale will be discovered automatically on startup. No registration code needed.

To test your locale:

```bash
python -m enterprise_fizzbuzz --locale es --range 1 15
```

Or add unit tests in `tests/test_i18n.py`:

```python
def test_spanish_locale_loads():
    LocaleManager.reset()
    mgr = LocaleManager()
    mgr.load_all("./locales")
    assert "es" in mgr.get_available_locales()

def test_spanish_fizz_label():
    LocaleManager.reset()
    mgr = LocaleManager()
    mgr.load_all("./locales")
    mgr.set_locale("es")
    assert mgr.get_label("Fizz") == "Fizz"  # or your Spanish translation
```

### A note on the linguistic validation report

When the Klingon and Elvish locales were added, a formal linguistic validation report was produced (`LINGUISTIC_VALIDATION_REPORT.md`). If your new locale involves a constructed or minority language, you are encouraged (but not required) to maintain this tradition of due diligence. If your locale is for a language with more than 10 million speakers, you can probably skip the validation report and just ask a native speaker.

---

## 5. Adding a New Evaluation Strategy

The platform supports four evaluation strategies: `STANDARD`, `CHAIN_OF_RESPONSIBILITY`, `PARALLEL_ASYNC`, and `MACHINE_LEARNING`. Each implements the `IRuleEngine` interface. Adding a fifth is straightforward.

### Step 1: Add an enum value

In `enterprise_fizzbuzz/domain/models.py`, add your strategy to the `EvaluationStrategy` enum:

```python
class EvaluationStrategy(Enum):
    STANDARD = auto()
    CHAIN_OF_RESPONSIBILITY = auto()
    PARALLEL_ASYNC = auto()
    MACHINE_LEARNING = auto()
    QUANTUM = auto()  # <-- new
```

### Step 2: Implement the `IRuleEngine` interface

The interface is in `enterprise_fizzbuzz/domain/interfaces.py`:

```python
class IRuleEngine(ABC):
    @abstractmethod
    def evaluate(self, number: int, rules: list[IRule]) -> FizzBuzzResult: ...

    @abstractmethod
    async def evaluate_async(self, number: int, rules: list[IRule]) -> FizzBuzzResult: ...
```

Two methods:
- **`evaluate()`**: Synchronous evaluation. Takes a number and a list of rules, returns a `FizzBuzzResult`.
- **`evaluate_async()`**: Async variant. Most strategies just delegate to `evaluate()` in their async path (see `StandardRuleEngine` for an example).

Create your engine class in `enterprise_fizzbuzz/infrastructure/rules_engine.py` or a new file under `infrastructure/`:

```python
class QuantumEngine(IRuleEngine):
    """Evaluates FizzBuzz using quantum superposition.

    Each number exists in a superposition of Fizz and not-Fizz until
    observed, at which point the wave function collapses to a
    deterministic modulo result. Schrodinger would be proud.
    """

    def evaluate(self, number: int, rules: list[IRule]) -> FizzBuzzResult:
        start = time.perf_counter_ns()
        sorted_rules = sorted(rules, key=lambda r: r.get_definition().priority)
        matches = []

        for rule in sorted_rules:
            if rule.evaluate(number):
                matches.append(RuleMatch(rule=rule.get_definition(), number=number))

        output = "".join(m.rule.label for m in matches) or str(number)
        elapsed = time.perf_counter_ns() - start

        return FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=matches,
            processing_time_ns=elapsed,
        )

    async def evaluate_async(self, number: int, rules: list[IRule]) -> FizzBuzzResult:
        return self.evaluate(number, rules)
```

### Step 3: Register with the factory

In `enterprise_fizzbuzz/infrastructure/rules_engine.py`, add your engine to `RuleEngineFactory._engines`:

```python
class RuleEngineFactory:
    _engines: dict[EvaluationStrategy, type[IRuleEngine]] = {
        EvaluationStrategy.STANDARD: StandardRuleEngine,
        EvaluationStrategy.CHAIN_OF_RESPONSIBILITY: ChainOfResponsibilityEngine,
        EvaluationStrategy.PARALLEL_ASYNC: ParallelAsyncEngine,
        EvaluationStrategy.MACHINE_LEARNING: None,  # lazy import
        EvaluationStrategy.QUANTUM: QuantumEngine,   # <-- new
    }
```

The factory's `create()` classmethod will now handle your strategy. If your engine has heavy imports (like the ML engine), you can use the lazy-import pattern -- set the value to `None` and add a `_load_quantum_engine()` classmethod analogous to `_load_ml_engine()`.

### Step 4: Wire it into the CLI

In `enterprise_fizzbuzz/__main__.py`, two places need updating:

**4a. The `--strategy` argument choices** (around line 130):

```python
parser.add_argument(
    "--strategy",
    choices=["standard", "chain_of_responsibility", "parallel_async", "machine_learning", "quantum"],
    help="Rule evaluation strategy (default: from config)",
)
```

**4b. The strategy map in `main()`** (around line 557):

```python
strategy_map = {
    "standard": EvaluationStrategy.STANDARD,
    "chain_of_responsibility": EvaluationStrategy.CHAIN_OF_RESPONSIBILITY,
    "parallel_async": EvaluationStrategy.PARALLEL_ASYNC,
    "machine_learning": EvaluationStrategy.MACHINE_LEARNING,
    "quantum": EvaluationStrategy.QUANTUM,  # <-- new
}
```

**4c. The config validation** in `enterprise_fizzbuzz/infrastructure/config.py`, method `_validate()` (around line 360):

```python
valid_strategies = {"standard", "chain_of_responsibility", "parallel_async", "machine_learning", "quantum"}
```

### Step 5: Add an Anti-Corruption Layer adapter (optional but encouraged)

If your strategy produces results in a non-standard way (like the ML engine's confidence scores), you should add a strategy adapter in `enterprise_fizzbuzz/infrastructure/adapters/strategy_adapters.py`. The adapter translates your engine's raw output into the canonical `EvaluationResult` type, keeping the domain model clean.

Register it in `StrategyAdapterFactory.create()` in the same file. The wiring in `__main__.py` (around line 1017) will pick it up automatically.

### Step 6: Write tests

Add tests to `tests/` or `tests/contracts/test_strategy_contract.py`. The contract tests verify that all strategy implementations satisfy the same behavioral contract -- your new strategy should pass the same tests as the others.

---

## 6. Adding a New CLI Flag

CLI flags are defined in `enterprise_fizzbuzz/__main__.py` in the `build_argument_parser()` function (starting at line 106). Adding a flag involves three steps: define it, propagate it through config, and wire it into the service builder.

### Step 1: Define the argument

In `build_argument_parser()`, add your argument using the standard `argparse` API:

```python
parser.add_argument(
    "--my-feature",
    action="store_true",
    help="Enable the My Feature subsystem for enhanced FizzBuzz evaluation",
)
```

Conventions:
- Boolean flags use `action="store_true"`.
- Value flags use `type=str` or `type=int` with a `metavar`.
- Flags with a `--` prefix get their attribute name with dashes converted to underscores: `--my-feature` becomes `args.my_feature`.

### Step 2: Propagate through configuration

If your flag overrides a `config.yaml` value, add the config key and a corresponding property to `ConfigurationManager` in `enterprise_fizzbuzz/infrastructure/config.py`.

**2a. Add the default value** in `_get_defaults()` (around line 91):

```python
"my_feature": {
    "enabled": False,
    "some_setting": 42,
},
```

**2b. Add the config.yaml section:**

```yaml
my_feature:
  enabled: false
  some_setting: 42
```

**2c. Add property accessors** on `ConfigurationManager`:

```python
@property
def my_feature_enabled(self) -> bool:
    self._ensure_loaded()
    return self._raw_config.get("my_feature", {}).get("enabled", False)

@property
def my_feature_some_setting(self) -> int:
    self._ensure_loaded()
    return self._raw_config.get("my_feature", {}).get("some_setting", 42)
```

The property accessor pattern is consistent throughout the class -- every config value has a `@property` that calls `self._ensure_loaded()` first.

**2d. (Optional) Add an environment variable override** in `_apply_environment_overrides()`:

```python
env_mappings = {
    ...
    "EFP_MY_FEATURE_ENABLED": ("my_feature", "enabled", lambda v: v.lower() in ("true", "1", "yes")),
}
```

### Step 3: Wire it into the service builder

In the `main()` function of `__main__.py`, add the wiring logic. The pattern is consistent throughout the file:

1. Check the CLI flag (or config fallback).
2. Instantiate the relevant components.
3. Attach them to the builder via `builder.with_middleware()` or similar.

```python
# My Feature setup
my_feature_middleware = None
if args.my_feature:
    my_feature_middleware = MyFeatureMiddleware(
        some_setting=config.my_feature_some_setting,
    )
    print(
        "  +---------------------------------------------------------+\n"
        "  | MY FEATURE: ENABLED                                      |\n"
        "  +---------------------------------------------------------+"
    )

# ... later, when building the service ...
if my_feature_middleware is not None:
    builder.with_middleware(my_feature_middleware)
```

### The full chain

When someone types `--my-feature`, the flow is:

1. `argparse` sets `args.my_feature = True`
2. `main()` checks `args.my_feature` and instantiates the relevant components
3. Components are attached to the `FizzBuzzServiceBuilder`
4. `builder.build()` constructs the `FizzBuzzService` with all middleware in the pipeline
5. The middleware runs on every number evaluation

---

## 7. Running Tests

The test suite lives in `tests/` and uses pytest.

### Test directory structure

```
tests/
  __init__.py
  test_fizzbuzz.py         # Core service, rules, pipeline integration
  test_circuit_breaker.py  # Circuit breaker subsystem
  test_otel_tracing.py     # FizzOTel distributed tracing
  test_auth.py             # RBAC, tokens, permissions
  test_i18n.py             # Internationalization, locale parser
  test_event_sourcing.py   # Event sourcing / CQRS
  test_chaos.py            # Chaos engineering
  test_feature_flags.py    # Feature flags
  test_sla.py              # SLA monitoring
  test_cache.py            # Caching, MESI coherence, eulogies
  test_migrations.py       # Database migration framework
  test_repository.py       # Repository pattern + Unit of Work
  test_acl.py              # Anti-Corruption Layer
  test_no_service_location.py  # Architecture: no service locator
  test_architecture.py     # Architecture: dependency rules
  test_container.py        # Dependency injection container
  contracts/
    __init__.py
    test_strategy_contract.py   # Contract: all strategies behave identically
    test_formatter_contract.py  # Contract: all formatters produce valid output
    test_repository_contract.py # Contract: all repositories honor the same API
  test_contract_coverage.py     # Meta-test: all contracts have implementations
```

### Running the full suite

```bash
python -m pytest tests/ -v
```

### Running a single test module

```bash
python -m pytest tests/test_i18n.py -v
```

### Running a single test function

```bash
python -m pytest tests/test_fizzbuzz.py::test_fizzbuzz_15_returns_fizzbuzz -v
```

### Running tests by keyword

```bash
python -m pytest tests/ -k "middleware" -v
```

### Running contract tests only

```bash
python -m pytest tests/contracts/ -v
```

### Important testing conventions

1. **Reset singletons.** `ConfigurationManager` and `LocaleManager` are singletons. Call `_SingletonMeta.reset()` or `LocaleManager.reset()` in your test setup to avoid state leaking between tests. Most existing tests do this in a fixture or at the top of each test.

2. **The `ProcessingContext` dataclass** (in `enterprise_fizzbuzz/domain/models.py`) is what flows through the middleware pipeline. When testing middleware in isolation, construct one directly:

   ```python
   context = ProcessingContext(
       number=15,
       session_id="test-session-id",
   )
   ```

3. **Contract tests** verify that multiple implementations of the same interface behave identically. If you add a new strategy, formatter, or repository backend, add it to the relevant contract test parametrization so it gets the same behavioral coverage as the existing implementations.

4. **Architecture tests** in `test_architecture.py` enforce the hexagonal layer dependency rules. If your new code imports from the wrong direction (e.g., domain importing from infrastructure), these tests will catch it.

---

## Quick Reference: Key Classes and Where They Live

| Class | File | Purpose |
|-------|------|---------|
| `IRule` | `domain/interfaces.py` | Abstract rule contract |
| `IRuleEngine` | `domain/interfaces.py` | Abstract evaluation engine contract |
| `IMiddleware` | `domain/interfaces.py` | Abstract middleware contract |
| `RuleDefinition` | `domain/models.py` | Immutable rule config (name, divisor, label, priority) |
| `FizzBuzzResult` | `domain/models.py` | Single evaluation result |
| `ProcessingContext` | `domain/models.py` | Mutable state flowing through middleware |
| `EvaluationStrategy` | `domain/models.py` | Enum of available strategies |
| `ConcreteRule` | `infrastructure/rules_engine.py` | Standard rule implementation |
| `RuleEngineFactory` | `infrastructure/rules_engine.py` | Creates engine instances by strategy |
| `StandardRuleFactory` | `application/factory.py` | Creates `ConcreteRule` from `RuleDefinition` |
| `ConfigurableRuleFactory` | `application/factory.py` | Creates rules from config-defined definitions |
| `MiddlewarePipeline` | `infrastructure/middleware.py` | Chains and executes middleware in priority order |
| `ConfigurationManager` | `infrastructure/config.py` | Singleton config with typed property accessors |
| `LocaleManager` | `infrastructure/i18n.py` | Singleton locale orchestrator |
| `FizzTranslationParser` | `infrastructure/i18n.py` | Parses `.fizztranslation` files |
| `FizzBuzzServiceBuilder` | `application/fizzbuzz_service.py` | Fluent builder for assembling the service |
| `FizzBuzzService` | `application/fizzbuzz_service.py` | Core orchestration service |
| `build_argument_parser()` | `__main__.py` | Defines all CLI flags |
| `main()` | `__main__.py` | CLI entry point, wires everything together |

All file paths above are relative to `enterprise_fizzbuzz/`.

---

## Parting Wisdom

The Enterprise FizzBuzz Platform has 24,800 lines of code, 69 custom exception classes, 829 tests, a neural network, a blockchain, a cache with funeral rites, and support for three fictional languages. It computes `n % 3`.

When adding features, maintain the same engineering standards as the existing codebase. Every subsystem should be treated with full production rigor. If you're adding a feature, ensure it has proper middleware integration, an ASCII dashboard, and comprehensive test coverage. If your middleware doesn't have its own dashboard, it isn't production-ready. If your locale file doesn't include a constructed language, your globalization coverage has gaps.

Welcome aboard. Bob is on call if you need anything.

# Research Report: Real-World Python Monolith Splitting Patterns

**Researcher**: Razz (Competitive Research Specialist)
**Date**: 2026-03-24
**Focus**: How real-world Python projects split monolithic files into modular architectures

---

## 1. Django's Exception Architecture

Django distributes exceptions across multiple domain-specific modules rather than concentrating them in a single file. The pattern is **centralized core + distributed per-subsystem exceptions**.

### Structure

| Module | Exception Examples | Purpose |
|--------|-------------------|---------|
| `django.core.exceptions` | `ObjectDoesNotExist`, `ImproperlyConfigured`, `ValidationError`, `FieldError`, `AppRegistryNotReady` | Framework-wide base exceptions |
| `django.db` | `DatabaseError`, `IntegrityError`, `DataError` | Database layer (wraps PEP 249 DB-API exceptions) |
| `django.db.utils` | `NotSupportedError`, `DatabaseErrorWrapper` | DB utility layer with context managers |
| `django.db.transaction` | `TransactionManagementError` | Transaction-specific errors |
| `django.http` | `Http404`, `UnreadablePostError` | HTTP layer exceptions |
| `django.urls` | `Resolver404`, `NoReverseMatch` | URL resolution errors |

### Key Design Decisions

1. **`django.core.exceptions` is small** — roughly 10-15 exception classes, not hundreds. It contains only truly cross-cutting exceptions.
2. **Per-subsystem files own their exceptions** — `django.db` wraps standard DB-API exceptions; `django.http` defines HTTP-specific ones. Each subsystem's exceptions live where they're used.
3. **Inheritance hierarchy is shallow** — Most exceptions inherit directly from `Exception` or `django.core.exceptions.SuspiciousOperation`. No deep hierarchies.
4. **Re-export for convenience** — `django.db` re-exports database exceptions from `django.db.utils` so users can do `from django.db import DatabaseError`.
5. **Model-level dynamic exceptions** — Each model gets its own `DoesNotExist` and `MultipleObjectsReturned` exception created dynamically at class definition time, as inner classes inheriting from `django.core.exceptions.ObjectDoesNotExist`.

### Takeaway

For a project with 600+ exception classes: split by subsystem/domain, keep the core exceptions file small (only cross-cutting base classes), and let each infrastructure module own its exceptions. Django's `Model.DoesNotExist` pattern shows how to generate per-context exceptions dynamically rather than defining them all statically.

**Sources**:
- [Django Exceptions docs](https://docs.djangoproject.com/en/6.0/ref/exceptions/)
- [django/core/exceptions.py on GitHub](https://github.com/django/django/blob/main/django/core/exceptions.py)
- [django.db.utils source](https://docs.djangoproject.com/en/5.0/_modules/django/db/utils/)

---

## 2. Large Python CLI Splitting

### AWS CLI Architecture

AWS CLI (awscli) uses a **model-driven, event-based command loading** architecture:

1. **`clidriver.py`** is the entry point — it creates a `CLIDriver` that loads a session and dispatches commands.
2. **Service definitions are JSON models** — each AWS service (EC2, S3, etc.) is described by a JSON model file, not hard-coded Python. The driver reads these models to generate commands dynamically.
3. **Event system for customization** — commands are built via events like `'building-command-table.main'` and `'building-command-table.dynamodb'`. Customizations register handlers on these events.
4. **`customizations/` directory** — service-specific CLI behaviors live in `awscli/customizations/`, one file per customization (e.g., `sessionmanager.py`, `waiters.py`). These are loaded lazily.
5. **No 342-flag argparse call** — flags are generated from service models, not hard-coded.

### Azure CLI Architecture

Azure CLI uses **per-service command modules**:

1. Commands are organized in a tree: `az network vnet create` → group `network`, subgroup `vnet`, command `create`.
2. Each service has its own command module (separate Python package).
3. Command models are stored in XML configuration files organized by resource.
4. The AAZ (Atomic Azure CLI) tool generates command code from REST API specifications.

### Click's LazyGroup Pattern

For Click-based CLIs, the **LazyGroup** pattern is the standard approach for large CLIs:

```python
@click.group(
    cls=LazyGroup,
    lazy_subcommands={"foo": "foo.cli", "bar": "bar.cli"},
)
def cli():
    pass
```

- Subcommands are registered as module paths, not imported eagerly.
- `get_command()` performs dynamic import only when a subcommand is invoked.
- Production results: 30% memory reduction for large toolchains; <5ms latency for 1000+ commands.
- Click docs recommend testing `--help` on each subcommand to verify lazy-loadability.

### Ansible CLI Architecture

Ansible uses **per-tool CLI classes** with a shared base:

1. Each CLI tool (`ansible-playbook`, `ansible-vault`, etc.) has its own CLI class.
2. A common `CLI` base class handles shared argument parsing and output formatting.
3. After `parse()` completes, all parsed arguments are available globally through `context.CLIARGS`.
4. The pattern is: set up, then hand off to the next layer of the call stack.

### Takeaway

For a CLI with 342+ flags: the AWS CLI model-driven approach (generate commands from data, not code) is the gold standard. For argparse-based CLIs, the key patterns are (a) subparsers for command grouping, (b) per-command modules loaded lazily, and (c) separating flag definitions from flag handling. Click's LazyGroup is the cleanest implementation of lazy command loading.

**Sources**:
- [awscli/clidriver.py on GitHub](https://github.com/aws/aws-cli/blob/develop/awscli/clidriver.py)
- [Azure CLI on GitHub](https://github.com/Azure/azure-cli)
- [Click Complex Applications docs](https://click.palletsprojects.com/en/stable/complex/)
- [Ansible CLI architecture](https://medium.com/read-the-source/the-ansible-cli-a-study-in-function-decomposition-15020a87529d)

---

## 3. Python Config Class Decomposition

### Apache Airflow: AirflowConfigParser

Airflow uses a **single parser class with section-based organization**:

1. **`AirflowConfigParser`** extends Python's `ConfigParser` with case-preserving option names.
2. Configuration is split into **sections** (core, database, scheduler, etc.) in `airflow.cfg`.
3. **Environment variable override**: `AIRFLOW__{SECTION}__{KEY}` with double underscores. Dots in section names become underscores.
4. **Precedence chain**: env var → command env var → secret env var → airflow.cfg → command in cfg → secret in cfg → built-in defaults.
5. **Type-aware getters**: `getboolean()`, `getint()`, `getfloat()`, `getlist()`, `getjson()`, `getenum()`.
6. **Secret backends**: The parser integrates with external secret stores via `_cmd` and `_secret` suffixes.
7. **Recent refactor** (PR #57744): Airflow is currently moving the config parser to a shared library, showing that even mature projects continue restructuring.

### Celery: app.conf

Celery uses a **Settings object with multiple config sources**:

1. Configuration lives on `app.conf`, a special settings object.
2. Multiple loading methods: `app.conf.update()`, `config_from_object()`, `config_from_envvar()`.
3. Settings can come from a module, class, or dictionary — `config_from_object()` accepts all three.
4. **Namespace prefixing**: When using Django, Celery settings use a `CELERY_` prefix via `namespace='CELERY'`.
5. Built-in defaults exist for all settings (e.g., `accept_content={'json'}`, timezone="UTC").

### Home Assistant: Config Entries + Config Flows

Home Assistant uses a **decentralized config-per-integration** pattern:

1. **ConfigEntry** is the unit of configuration — each integration instance has its own entry.
2. **Config Flow Handlers** manage entry creation via UI wizards (no manual YAML editing).
3. **Config Subentries** (newer) provide hierarchy between config entries and device registries.
4. Each integration defines its own `config_flow.py` with step methods.
5. Data validation happens at config creation time, not at startup.
6. Multiple instances of the same integration are supported naturally.

### Dataclass Composition Pattern

For decomposing a single large config class:

```python
@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432

@dataclass
class CacheConfig:
    backend: str = "redis"
    ttl: int = 300

@dataclass
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
```

- Preferred over mixins for configuration (mixins are for behavior, not data).
- Each sub-config can be validated independently.
- Nested dataclasses compose cleanly and support `asdict()` serialization.

### Takeaway

The dominant patterns are: (1) Airflow-style section-based config with env var overrides and typed getters, (2) Celery-style multi-source loading with namespace prefixes, or (3) Home Assistant-style per-module config flows. For a monolithic config class, dataclass composition (nested dataclasses) is preferred over mixin inheritance.

**Sources**:
- [Airflow AirflowConfigParser source](https://airflow.apache.org/docs/apache-airflow/1.10.12/_modules/airflow/configuration.html)
- [Airflow config parser shared library PR](https://github.com/apache/airflow/pull/57744)
- [Celery Configuration and defaults](https://docs.celeryq.dev/en/main/userguide/configuration.html)
- [Home Assistant Config Flow docs](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
- [Airflow Configuration Reference](https://airflow.apache.org/docs/apache-airflow/stable/configurations-ref.html)

---

## 4. Backward-Compatible Python Module Restructuring

### The Core Technique: `module.py` → `module/`

When converting a single-file module to a package:

1. Create `module/` directory.
2. Move code into submodules (e.g., `module/core.py`, `module/utils.py`).
3. In `module/__init__.py`, re-export everything that was previously accessible:
   ```python
   from .core import ClassA, ClassB
   from .utils import helper_func
   ```

### PEP 562: Module-Level `__getattr__` (Python 3.7+)

The most powerful tool for backward-compatible restructuring. Allows modules to intercept attribute access:

```python
# old_module.py (now a shim)
import warnings

def __getattr__(name):
    if name == "OldClass":
        warnings.warn(
            "Importing OldClass from old_module is deprecated. "
            "Use new_module.OldClass instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from new_module import OldClass
        return OldClass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**Use cases**: lazy imports, deprecation warnings for moved symbols, dynamic attribute generation.

### IPython/Traitlets: Real-World Migration Example

IPython 4.x performed a major restructuring, splitting `IPython.config` → `traitlets.config` and `IPython.utils.traitlets` → `traitlets`:

1. **Shim packages** were created at old import paths that re-exported from new locations.
2. **Deprecation warnings** fired on every import from the old path.
3. Old paths continued to work for multiple major versions before removal.
4. Public API functions like path utilities were moved with shims at old locations.

### PyCharm's Automated Approach

PyCharm IDE offers built-in "Convert Module to Package" refactoring:
- Creates the package directory and `__init__.py`.
- Moves all code into `__init__.py` initially.
- Updates all imports across the project.

### Common Pitfalls

1. **Circular imports** — When `__init__.py` imports from submodules that import from the package. Solution: keep `__init__.py` minimal; use lazy imports or PEP 562 `__getattr__`.
2. **`__all__` management** — Must be maintained in `__init__.py` to control `from module import *` behavior.
3. **IDE autocomplete** — Some IDEs don't follow re-exports well. Using explicit `as` syntax helps: `from .core import Foo as Foo` (PEP 484 re-export convention).
4. **Pickle compatibility** — Pickled objects store their module path. If `module.Foo` becomes `module.core.Foo`, old pickles break unless the shim is maintained.
5. **mypy `--no-implicit-reexport`** — With strict mypy settings, imports in `__init__.py` are not treated as exports unless explicitly re-exported with `as` or listed in `__all__`.

### Re-Export Best Practices

```python
# __init__.py — explicit re-export patterns
from .core import Foo as Foo          # PEP 484 explicit re-export
from .core import Bar                  # implicit re-export (may warn with strict mypy)
from .utils import *                   # re-exports everything in utils.__all__

__all__ = ["Foo", "Bar", "helper"]     # explicit public API declaration
```

### Takeaway

The safest migration path is: (1) create the package with `__init__.py` re-exporting everything, (2) add PEP 562 `__getattr__` for deprecated paths with warnings, (3) maintain `__all__` for API surface control, (4) test pickle compatibility if relevant, and (5) use explicit `as` re-exports for mypy compatibility.

**Sources**:
- [PEP 562 — Module __getattr__ and __dir__](https://peps.python.org/pep-0562/)
- [IPython 4.x Changelog](https://ipython.readthedocs.io/en/stable/whatsnew/version4.html)
- [urllib3 __init__.py on GitHub](https://github.com/urllib3/urllib3/blob/main/src/urllib3/__init__.py)
- [requests __init__.py on GitHub](https://github.com/psf/requests/blob/main/src/requests/__init__.py)
- [PyCharm Convert to Package docs](https://www.jetbrains.com/help/pycharm/refactoring-convert.html)
- [mypy issue #10198 — __init__.py re-export behavior](https://github.com/python/mypy/issues/10198)
- [Scientific Python exports guide](https://learn.scientific-python.org/development/patterns/exports/)

---

## 5. Python Enum Extension Patterns

### The Fundamental Constraint

Standard Python `enum.Enum` **cannot be subclassed if it has members** (PEP 435). This is intentional — enum members are singletons, and subclassing would break identity guarantees.

### Pattern 1: aenum's `extend_enum()`

The [aenum](https://github.com/ethanfurman/aenum) library provides `extend_enum()` for adding members after class creation:

```python
from aenum import Enum, extend_enum

class Color(Enum):
    RED = 1
    GREEN = 2

extend_enum(Color, 'BLUE', 3)
# Color.BLUE now exists
```

- Used when plugins need to register new enum values at runtime.
- Members added this way are fully functional enum members.
- Supports unique values, multiple values, auto-numbering.

### Pattern 2: extendable-enum's `@inheritable_enum`

The [extendable-enum](https://pypi.org/project/extendable-enum/) package uses a decorator:

```python
from extendable_enum import inheritable_enum

@inheritable_enum
class BaseStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"

class ExtendedStatus(BaseStatus):
    PENDING = "pending"  # New member, plus inherits ACTIVE and INACTIVE
```

### Pattern 3: Class-Based Registry (No Enum)

When extensibility is more important than enum semantics:

```python
class StatusRegistry:
    _registry = {}

    @classmethod
    def register(cls, name, value):
        cls._registry[name] = value

    @classmethod
    def get(cls, name):
        return cls._registry[name]

# Core statuses
StatusRegistry.register("ACTIVE", "active")

# Plugin adds its own
StatusRegistry.register("REVIEW", "review")
```

### Pattern 4: Sentry SDK's Constants Approach

Sentry SDK uses **class-based constants** rather than enums for extensibility:

- `sentry_sdk/consts.py` defines `SPANDATA` as a class with string attributes (not an Enum).
- Plugin integrations define their own constants in their respective modules.
- No enum subclassing needed — just namespace organization.

### Pattern 5: Django's TextChoices/IntegerChoices

Django 3.0+ provides enum-like classes specifically designed for model field choices:

```python
class Status(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
```

- These are standard Python enums under the hood.
- `django-enum` and `django-enumfields` extend this with more features.
- For extensibility, Django apps define their own Choices classes per-app.

### Takeaway

For a project needing extensible enums: (1) if you need real enum semantics with plugins, use `aenum.extend_enum()`, (2) if you need inheritance, use `extendable-enum`, (3) if you need maximum flexibility, use a class-based registry with string constants (Sentry's approach), (4) if you want to avoid the enum constraint entirely, use simple classes with class attributes.

**Sources**:
- [aenum on GitHub](https://github.com/ethanfurman/aenum)
- [aenum documentation](https://github.com/ethanfurman/aenum/blob/master/aenum/doc/aenum.rst)
- [extendable-enum on PyPI](https://pypi.org/project/extendable-enum/)
- [Python Enum HOWTO](https://docs.python.org/3/howto/enum.html)
- [django-enum docs](https://django-enum.readthedocs.io/en/latest/)
- [LWN: Extending Python's enums](https://lwn.net/Articles/850300/)
- [Sentry SDK on GitHub](https://github.com/getsentry/sentry-python)

---

## 6. Test Suite Adaptation After Restructuring

### Strategy 1: Re-Export Shims (Most Common)

The dominant approach — keep old import paths working via `__init__.py` re-exports or shim modules:

- **IPython**: After splitting into traitlets, kept shim packages at old paths. Tests continued to work unchanged during migration period.
- **urllib3**: `__init__.py` re-exports `Retry`, `Timeout`, etc. from submodules. Tests import from `urllib3.Retry` and never need updating.
- **This project's existing pattern**: Root-level `.py` files are already re-export stubs (per CLAUDE.md).

**Advantage**: Zero test changes needed initially. Tests migrate gradually.
**Risk**: Shims can mask actual breakage if the re-export layer has bugs.

### Strategy 2: Deprecation Warnings + Test Assertions

Use the `deprecated` or `pyDeprecate` libraries with test integration:

```python
# Using the deprecation library
@deprecation.deprecated(deprecated_in="1.0", removed_in="2.0")
def old_function():
    return new_function()

# In tests — ensure deprecated code is eventually removed
@deprecation.fail_if_not_removed
def test_old_function():
    old_function()
```

The `fail_if_not_removed` decorator makes the test fail once the "removed_in" version is reached, preventing dead shims from accumulating.

### Strategy 3: Automated Import Rewriting

Tools for bulk import updates:

- **FileMover** (`plex1/filemover`): Python package + VSCode extension that moves files and auto-updates absolute imports across the project.
- **PyCharm refactoring**: Built-in "Move" and "Convert to Package" rewrites all import references.
- **rope**: Python refactoring library that can programmatically rename/move modules.
- **Manual**: `sed`/`find-replace` with careful regex for `from old_module import X` → `from new_module import X`.

### Strategy 4: PEP 562 `__getattr__` with Warning Tracking

```python
# In the old module location
import warnings
import importlib

_MOVED = {
    "OldClass": "new_package.core",
    "OldHelper": "new_package.utils",
}

def __getattr__(name):
    if name in _MOVED:
        warnings.warn(
            f"{name} has moved to {_MOVED[name]}",
            DeprecationWarning,
            stacklevel=2,
        )
        module = importlib.import_module(_MOVED[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

In tests, use `warnings.catch_warnings()` to assert no deprecation warnings fire, confirming all test imports have been updated:

```python
import warnings

def test_no_deprecated_imports():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import my_module
        deprecated = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecated) == 0, f"Deprecated imports found: {deprecated}"
```

### Strategy 5: Dual-Phase Migration

Used by large projects (IPython, scientific Python ecosystem):

1. **Phase 1**: Add new import paths, keep old paths working with deprecation warnings. Run full test suite — everything passes.
2. **Phase 2**: Update all internal imports to new paths. External consumers still use old paths.
3. **Phase 3**: Remove old paths in a major version bump. Tests that used old paths now fail, confirming cleanup is complete.

### Takeaway

The safest approach for 11,400 tests: (1) use re-export shims so all existing tests pass unchanged, (2) add PEP 562 `__getattr__` deprecation warnings at old paths, (3) gradually update test imports to new paths, (4) use `fail_if_not_removed` or warning-counting tests to track migration progress, (5) remove shims only in a major version bump.

**Sources**:
- [pyDeprecate library](https://borda.github.io/pyDeprecate/)
- [PEP 702 — Marking deprecations using the type system](https://peps.python.org/pep-0702/)
- [deprecation library on PyPI](https://pypi.org/project/deprecation/)
- [FileMover on GitHub](https://github.com/plex1/filemover)
- [pytest Good Integration Practices](https://docs.pytest.org/en/7.1.x/explanation/goodpractices.html)
- [SPEC 1 — Lazy Loading (Scientific Python)](https://scientific-python.org/specs/spec-0001/)

---

## Summary Matrix

| Area | Dominant Pattern | Best Real-World Example | Key Mechanism |
|------|-----------------|------------------------|---------------|
| Exception splitting | Per-subsystem files + small core | Django | Domain modules own their exceptions |
| CLI splitting | Model-driven or lazy-loaded commands | AWS CLI / Click LazyGroup | JSON models or `get_command()` lazy import |
| Config decomposition | Section-based parser or nested dataclasses | Airflow / Home Assistant | `SECTION__KEY` env vars, Config Flows |
| Module→Package migration | `__init__.py` re-exports + PEP 562 | IPython → traitlets | `__getattr__` with deprecation warnings |
| Enum extension | `aenum.extend_enum()` or class registry | Sentry SDK (class constants) | Runtime member addition or plain classes |
| Test adaptation | Re-export shims, then gradual migration | IPython, urllib3 | Shims first, deprecation warnings, phased removal |

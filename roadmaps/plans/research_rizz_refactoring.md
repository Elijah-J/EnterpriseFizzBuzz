# Research Report: Python Plugin/Registry Patterns for Round 17.5 Refactors

**Researcher:** Rizz
**Date:** 2026-03-24
**Scope:** Patterns for modularizing monolithic files into plugin/registry architectures

---

## 1. Python Plugin/Registry Patterns

### Pattern A: `__init_subclass__` with Auto-Import (Recommended)

The modern, zero-dependency approach. Subclasses register themselves automatically when their module is imported. Combined with directory scanning, this gives full auto-discovery.

```python
# infrastructure/rule_engines/__init__.py
import os
import importlib.util
import traceback


class RuleEngineBase:
    """Base class for all rule engines. Subclasses auto-register."""
    _registry = {}

    @classmethod
    def __init_subclass__(cls, engine_name=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if engine_name is not None:
            cls._registry[engine_name] = cls

    @classmethod
    def get(cls, name):
        return cls._registry[name]

    @classmethod
    def all(cls):
        return dict(cls._registry)


# --- Auto-import all .py files in this directory ---
_dir = os.path.dirname(os.path.abspath(__file__))
for _fname in sorted(os.listdir(_dir)):
    if _fname.endswith('.py') and not _fname.startswith('_'):
        _path = os.path.join(_dir, _fname)
        _name = _fname[:-3]
        try:
            _spec = importlib.util.spec_from_file_location(_name, _path)
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
        except Exception:
            traceback.print_exc()
```

```python
# infrastructure/rule_engines/standard.py
from . import RuleEngineBase

class StandardRuleEngine(RuleEngineBase, engine_name="standard"):
    """Standard FizzBuzz rule evaluation engine."""
    def evaluate(self, number):
        ...
```

**Advantages:**
- No metaclass complexity; `__init_subclass__` is stdlib since Python 3.6
- Each plugin is a standalone file — add a file, it auto-registers
- The `is_abstract` keyword arg pattern prevents base classes from registering
- Click uses this exact pattern (`PluginGroup` with `list_commands`/`get_command`)

**How Django does it:** Django's app registry (`django.apps.registry`) discovers apps listed in `INSTALLED_APPS`, imports their `models.py` and `admin.py` modules, and classes register via metaclasses (`ModelBase`, `MediaDefiningClass`). The pattern is: explicit config lists what to scan, metaclass/`__init_subclass__` handles registration.

**How pytest does it:** pytest uses `entry_points` for third-party plugins and `importlib` + naming conventions for conftest-based local plugins. The `pluggy` library manages hook specs and implementations via decorators.

**How Flask does it:** Flask Blueprints are explicitly registered with `app.register_blueprint(bp)`. The `Flask-Registry` extension adds auto-discovery via `BlueprintAutoDiscoveryRegistry` which scans packages for `views` modules containing blueprints.

### Pattern B: Decorator Registry

Simpler when you don't need inheritance-based polymorphism:

```python
# infrastructure/formatters/registry.py
_FORMATTERS = {}

def register_formatter(name):
    """Decorator that registers a formatter function or class."""
    def decorator(cls_or_fn):
        _FORMATTERS[name] = cls_or_fn
        return cls_or_fn
    return decorator

def get_formatter(name):
    return _FORMATTERS[name]

def all_formatters():
    return dict(_FORMATTERS)
```

```python
# infrastructure/formatters/json_formatter.py
from .registry import register_formatter

@register_formatter("json")
class JsonFormatter:
    def format(self, result):
        ...
```

**Advantages:** Works for functions and classes alike. No inheritance required. Simple to understand.

### Pattern C: `pkgutil.iter_modules` (For Namespace Packages)

When plugins may be installed as separate packages under a shared namespace:

```python
import importlib
import pkgutil
import myapp.plugins

def iter_namespace(ns_pkg):
    return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + ".")

discovered = {
    name: importlib.import_module(name)
    for finder, name, ispkg in iter_namespace(myapp.plugins)
}
```

### Pattern D: Click's `PluginGroup` (For CLI Commands)

Click's official pattern for auto-discovering subcommands from a directory:

```python
import importlib.util
import os
import click

class PluginGroup(click.Group):
    def __init__(self, name=None, plugin_folder="commands", **kwargs):
        super().__init__(name=name, **kwargs)
        self.plugin_folder = plugin_folder

    def list_commands(self, ctx):
        rv = []
        for filename in os.listdir(self.plugin_folder):
            if filename.endswith(".py") and not filename.startswith("_"):
                rv.append(filename[:-3])
        rv.sort()
        return rv

    def get_command(self, ctx, name):
        path = os.path.join(self.plugin_folder, f"{name}.py")
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.cli
```

### Recommendation for Enterprise FizzBuzz

Use **Pattern A** (`__init_subclass__` + auto-import) for class hierarchies (rule engines, middleware, formatters) and **Pattern B** (decorator registry) for simpler registrations (event handlers, feature flags). Both patterns coexist well.

---

## 2. Dynamic Enum Alternatives

### The Problem

A monolithic `EventType` enum (or similar) with hundreds of members in one file. Subsystems that add new events must edit the central enum, creating merge conflicts and tight coupling.

### Option A: Registry Class with Attribute Access (Recommended)

A custom class that supports `EventType.SOME_NAME` access, equality, and hashing — without being a stdlib Enum:

```python
# domain/events/event_type.py

class _EventValue:
    """Immutable, hashable event type value."""
    __slots__ = ('_name', '_value')

    def __init__(self, name, value):
        object.__setattr__(self, '_name', name)
        object.__setattr__(self, '_value', value)

    def __setattr__(self, *_):
        raise AttributeError("EventValue instances are immutable")

    @property
    def name(self):
        return self._name

    @property
    def value(self):
        return self._value

    def __repr__(self):
        return f"EventType.{self._name}"

    def __eq__(self, other):
        if isinstance(other, _EventValue):
            return self._value == other._value
        return NotImplemented

    def __hash__(self):
        return hash(self._value)


class _EventTypeRegistry:
    """Dynamic registry that supports EventType.SOME_NAME attribute access."""
    def __init__(self):
        self._members = {}   # name -> _EventValue
        self._by_value = {}  # value -> _EventValue

    def register(self, name, value=None):
        """Register a new event type. Returns the EventValue."""
        if value is None:
            value = name
        if name in self._members:
            return self._members[name]
        ev = _EventValue(name, value)
        self._members[name] = ev
        self._by_value[value] = ev
        return ev

    def __getattr__(self, name):
        try:
            return self._members[name]
        except KeyError:
            raise AttributeError(f"No event type '{name}'")

    def __contains__(self, item):
        if isinstance(item, _EventValue):
            return item.name in self._members
        return item in self._members

    def __iter__(self):
        return iter(self._members.values())

    def __len__(self):
        return len(self._members)


EventType = _EventTypeRegistry()
```

```python
# infrastructure/cache/events.py
from domain.events.event_type import EventType

EventType.register("CACHE_HIT")
EventType.register("CACHE_MISS")
EventType.register("CACHE_EVICTION")
```

```python
# infrastructure/blockchain/events.py
from domain.events.event_type import EventType

EventType.register("BLOCK_MINED")
EventType.register("CHAIN_VALIDATED")
```

Usage is identical to the old enum:
```python
if event.type == EventType.CACHE_HIT:
    ...

lookup = {EventType.BLOCK_MINED: handler}
```

**Advantages:**
- Supports `EventType.NAME` attribute access
- Supports `==` and `hash` for dict keys (via `_EventValue`)
- Subsystems register their own events at import time — no central file to edit
- No third-party dependency

### Option B: `aenum.extend_enum` (Third-Party)

The `aenum` library (by the stdlib Enum author) lets you add members to an existing Enum after definition:

```python
from aenum import Enum, extend_enum

class EventType(Enum):
    # Core events defined here
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"

# In infrastructure/cache/events.py:
extend_enum(EventType, 'CACHE_HIT', 'cache_hit')
extend_enum(EventType, 'CACHE_MISS', 'cache_miss')

# Works as expected:
EventType.CACHE_HIT          # <EventType.CACHE_HIT: 'cache_hit'>
EventType['CACHE_HIT']       # <EventType.CACHE_HIT: 'cache_hit'>
EventType('cache_hit')       # <EventType.CACHE_HIT: 'cache_hit'>
EventType.CACHE_HIT == EventType.CACHE_HIT  # True
{EventType.CACHE_HIT: 1}    # works as dict key
```

**Advantages:** True stdlib-compatible Enum. All Enum features (iteration, `_member_map_`, name/value).
**Disadvantages:** Third-party dependency. `extend_enum` is technically mutating a "closed" type.

### Option C: String Constants with Validation Registry

The simplest approach — event types are plain strings, validated through a registry:

```python
# domain/events/event_type.py
_REGISTERED = set()

def register_event(name: str) -> str:
    _REGISTERED.add(name)
    return name

def is_valid(name: str) -> bool:
    return name in _REGISTERED

# infrastructure/cache/events.py
CACHE_HIT = register_event("CACHE_HIT")
CACHE_MISS = register_event("CACHE_MISS")
```

**Advantages:** Zero complexity.
**Disadvantages:** No namespace (`CACHE_HIT` is just a string); typos not caught at import time.

### Recommendation

**Option A** (custom registry class) for Enterprise FizzBuzz. It preserves the `EventType.NAME` API the codebase already uses, requires no dependencies, and allows distributed registration.

---

## 3. Python Mixin Composition

### The Problem

A large class (e.g., `ConfigurationManager`) accumulates hundreds of methods organized by subsystem. Need to split into per-subsystem mixin files while keeping the same public API.

### Pattern A: Explicit Mixin Imports in `__init__.py` (Recommended)

```python
# infrastructure/config/mixins/cache_config.py
class CacheConfigMixin:
    """Configuration methods for the cache subsystem."""
    def get_cache_backend(self):
        return self._get("cache.backend", "memory")

    def get_cache_ttl(self):
        return self._get("cache.ttl", 300)
```

```python
# infrastructure/config/mixins/blockchain_config.py
class BlockchainConfigMixin:
    """Configuration methods for the blockchain subsystem."""
    def get_mining_difficulty(self):
        return self._get("blockchain.difficulty", 4)
```

```python
# infrastructure/config/manager.py
from .mixins.cache_config import CacheConfigMixin
from .mixins.blockchain_config import BlockchainConfigMixin
# ... more mixins

class ConfigurationManager(
    CacheConfigMixin,
    BlockchainConfigMixin,
    # ... more mixins
    _ConfigurationBase,
):
    """Enterprise configuration manager.

    Composed from per-subsystem mixins. Each mixin file handles
    one subsystem's configuration interface.
    """
    pass
```

**Advantages:** Explicit, readable, IDE-friendly (autocomplete works). Python MRO handles method resolution. Django uses this pattern extensively (e.g., `class BookListView(LoginRequiredMixin, PermissionRequiredMixin, ListView)`).

### Pattern B: Auto-Discovered Mixins via `type()`

For truly dynamic composition where you don't want to manually list mixins:

```python
# infrastructure/config/__init__.py
import os
import importlib
import inspect

_dir = os.path.join(os.path.dirname(__file__), 'mixins')
_mixins = []

for fname in sorted(os.listdir(_dir)):
    if fname.endswith('_config.py'):
        mod_name = fname[:-3]
        mod = importlib.import_module(f'.mixins.{mod_name}', package=__package__)
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if name.endswith('Mixin'):
                _mixins.append(obj)

# Dynamically compose the class
ConfigurationManager = type(
    'ConfigurationManager',
    tuple(_mixins) + (_ConfigurationBase,),
    {'__doc__': 'Enterprise configuration manager. Composed from auto-discovered mixins.'}
)
```

**Advantages:** Fully automatic — drop a mixin file, it's composed in.
**Disadvantages:** IDE can't resolve methods (no static class definition). Harder to debug MRO issues. `type()` doesn't run `__init_subclass__`.

### Pattern C: Protocol Classes for Interface Verification

Use `typing.Protocol` to verify mixin contracts without inheritance:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class CacheConfigProtocol(Protocol):
    def get_cache_backend(self) -> str: ...
    def get_cache_ttl(self) -> int: ...

# Verify at test time:
assert isinstance(config_manager, CacheConfigProtocol)
```

### Recommendation

**Pattern A** (explicit mixin imports) for Enterprise FizzBuzz. It preserves IDE support and is easy to audit. The class definition in `manager.py` serves as a clear manifest of all composed behaviors. Use `type()` (Pattern B) only if the mixin count becomes unmanageable (50+).

---

## 4. YAML Include/Merge Patterns

### The Problem

A monolithic `config.yaml` with sections for every subsystem. Need to split into per-subsystem files while keeping backward compatibility (existing code that loads `config.yaml` still works).

### Pattern A: Manual Glob-and-Merge with OmegaConf (Recommended)

```python
# infrastructure/config/loader.py
import glob
import os
from omegaconf import OmegaConf

def load_config(base_dir="config"):
    """Load and merge configuration from split YAML files.

    Precedence (highest wins):
    1. config.yaml (base config, always loaded first)
    2. config.d/*.yaml (per-subsystem overrides, alphabetical order)
    3. CLI overrides
    """
    base_path = os.path.join(base_dir, "config.yaml")
    base_cfg = OmegaConf.load(base_path)

    # Merge per-subsystem configs
    override_dir = os.path.join(base_dir, "config.d")
    if os.path.isdir(override_dir):
        for path in sorted(glob.glob(os.path.join(override_dir, "*.yaml"))):
            subsystem_cfg = OmegaConf.load(path)
            base_cfg = OmegaConf.merge(base_cfg, subsystem_cfg)

    return base_cfg
```

Directory layout:
```
config/
├── config.yaml          # base config (backward-compatible, always works alone)
└── config.d/
    ├── 00_cache.yaml
    ├── 10_blockchain.yaml
    ├── 20_auth.yaml
    └── 30_monitoring.yaml
```

**Advantages:**
- `config.yaml` alone still works (backward-compatible)
- Subsystem files are optional overlays
- Numeric prefixes control merge order
- OmegaConf provides variable interpolation (`${path.to.value}`), type checking, and merge semantics
- OmegaConf is already a common Python dependency (used by Hydra/Facebook)

### Pattern B: PyYAML Custom `!include` Constructor

For staying with pure PyYAML (no new dependency):

```python
import os
import yaml
import glob as glob_mod

class IncludeLoader(yaml.SafeLoader):
    """YAML loader with !include and !include_dir support."""
    pass

def _include_constructor(loader, node):
    """Handle !include tag — load a single file."""
    filepath = os.path.join(loader._base_dir, loader.construct_scalar(node))
    with open(filepath) as f:
        return yaml.load(f, IncludeLoader)

def _include_dir_constructor(loader, node):
    """Handle !include_dir tag — merge all YAML files in a directory."""
    dirpath = os.path.join(loader._base_dir, loader.construct_scalar(node))
    result = {}
    for path in sorted(glob_mod.glob(os.path.join(dirpath, "*.yaml"))):
        with open(path) as f:
            data = yaml.load(f, IncludeLoader)
            if isinstance(data, dict):
                result.update(data)
    return result

IncludeLoader.add_constructor('!include', _include_constructor)
IncludeLoader.add_constructor('!include_dir', _include_dir_constructor)

def load_config(path):
    IncludeLoader._base_dir = os.path.dirname(os.path.abspath(path))
    with open(path) as f:
        return yaml.load(f, IncludeLoader)
```

```yaml
# config.yaml
cache: !include config.d/cache.yaml
blockchain: !include config.d/blockchain.yaml
overrides: !include_dir config.d/overrides/
```

**Advantages:** No new dependency beyond PyYAML.
**Disadvantages:** No variable interpolation or type validation. Custom tags make the YAML non-standard.

### Pattern C: `pyyaml-include` Library

A drop-in library that adds `!inc` tag support to PyYAML:

```python
import yaml
import yaml_include

yaml.add_constructor("!inc", yaml_include.Constructor(base_dir="/path/to/config"))
```

```yaml
# config.yaml
cache: !inc cache.yaml
features: !inc features/*.yaml   # glob support built-in
```

**Advantages:** Well-maintained, supports globs, recursive includes, remote files.
**Disadvantages:** Additional dependency.

### Pattern D: Hydra Compose API

For full-featured config management with config groups:

```
config/
├── config.yaml
├── cache/
│   ├── memory.yaml
│   └── redis.yaml
├── auth/
│   ├── rbac.yaml
│   └── hmac.yaml
```

```yaml
# config.yaml
defaults:
  - cache: memory
  - auth: rbac

app:
  name: EnterpriseFizzBuzz
```

```python
from hydra import compose, initialize

with initialize(config_path="config"):
    cfg = compose(config_name="config", overrides=["cache=redis"])
```

**Advantages:** Full config group system, CLI overrides, variable interpolation.
**Disadvantages:** Heavyweight dependency. Opinionated about config structure. May conflict with existing CLI parsing (342+ flags).

### Recommendation

**Pattern A** (glob-and-merge with OmegaConf) or **Pattern B** (PyYAML custom constructor) for Enterprise FizzBuzz. Pattern A is cleaner but adds a dependency. Pattern B is zero-dependency. Both preserve backward compatibility — `config.yaml` remains the primary config file, with optional split files as overlays.

If the project already uses PyYAML and wants no new dependencies, use Pattern B. If adding OmegaConf is acceptable, Pattern A is more robust.

---

## 5. Python Package Splitting

### The Problem

A single large `.py` file (e.g., `events.py` at 3000+ lines) needs to become a package (`events/`) with the code split across multiple files, while all existing imports (`from enterprise_fizzbuzz.infrastructure.events import EventBus`) continue to work.

### Step-by-Step Process

#### Step 1: Create the Package Directory

```
# Before:
infrastructure/
├── events.py        # 3000 lines, everything in one file

# After:
infrastructure/
├── events/
│   ├── __init__.py  # re-exports for backward compatibility
│   ├── bus.py       # EventBus class
│   ├── store.py     # EventStore class
│   ├── handlers.py  # built-in event handlers
│   └── types.py     # event type definitions
```

#### Step 2: Write `__init__.py` with Re-Exports

```python
# infrastructure/events/__init__.py
"""Event sourcing infrastructure.

This package was split from a single module. All public names remain
importable from this path for backward compatibility.
"""
from .bus import EventBus, AsyncEventBus
from .store import EventStore, InMemoryEventStore
from .handlers import (
    LoggingHandler,
    MetricsHandler,
    WebhookHandler,
)
from .types import EventType, Event, EventMetadata

__all__ = [
    "EventBus",
    "AsyncEventBus",
    "EventStore",
    "InMemoryEventStore",
    "LoggingHandler",
    "MetricsHandler",
    "WebhookHandler",
    "EventType",
    "Event",
    "EventMetadata",
]
```

#### Step 3: Avoiding Circular Imports

When splitting, circular dependencies often emerge. Resolution strategies:

**Strategy 1: Dependency inversion** — Extract shared types into a `_types.py` or `_base.py` that other submodules import from:

```python
# events/_base.py  (no imports from sibling modules)
class Event:
    ...

class EventMetadata:
    ...

# events/bus.py
from ._base import Event, EventMetadata   # safe, no cycle

# events/store.py
from ._base import Event                  # safe, no cycle
```

**Strategy 2: Lazy imports** — Defer imports to function scope:

```python
# events/bus.py
class EventBus:
    def replay(self):
        from .store import EventStore  # deferred to break cycle
        ...
```

**Strategy 3: TYPE_CHECKING guard** — For type annotations only:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import EventStore

class EventBus:
    def replay(self, store: EventStore) -> None:
        ...
```

#### Step 4: Verify Backward Compatibility

Add a test to ensure all previously-public names remain importable:

```python
# tests/test_package_compat.py
def test_events_package_backward_compat():
    """All names importable from the old module path still work."""
    from enterprise_fizzbuzz.infrastructure.events import EventBus
    from enterprise_fizzbuzz.infrastructure.events import EventStore
    from enterprise_fizzbuzz.infrastructure.events import EventType
    # ... etc.
    assert EventBus is not None
```

#### Root-Level Re-Export Stubs

Per the project's existing convention, root-level `.py` files re-export from infrastructure. These continue to work because `__init__.py` re-exports everything:

```python
# events.py (root-level stub, unchanged)
from enterprise_fizzbuzz.infrastructure.events import *
```

### Key Pitfalls

1. **`__init__.py` import order matters** — If submodule A imports from submodule B at module level, B must be importable before A. Use `_base.py` for shared types.
2. **Wildcard re-exports** — Always define `__all__` in `__init__.py`. Without it, `from package import *` imports everything including private names.
3. **IDE refactoring tools** — PyCharm's "Convert to Python Package" automates step 1 (creates directory, moves code to `__init__.py`) but doesn't split the code.
4. **Test imports** — Tests that import internal names (`from events import _internal_helper`) will break. Decide whether to add those to `__all__` or update the tests.

### Recommendation

Follow the step-by-step process above. The critical ingredient is `__init__.py` re-exporting all public names with an explicit `__all__`. Use `_base.py` for shared types to prevent circular imports. Add backward-compatibility tests.

---

## Summary: Pattern Recommendations for Round 17.5

| Refactor Target | Recommended Pattern | Key Mechanism |
|---|---|---|
| Class registries (engines, formatters, middleware) | `__init_subclass__` + directory auto-import | Subclass keyword args, `importlib.util` scanning |
| Monolithic enums (EventType, etc.) | Custom registry class with `__getattr__` | `_EventValue` for hash/eq, distributed `register()` calls |
| Large classes (ConfigurationManager) | Explicit mixin composition | Per-subsystem mixin files, listed in class definition |
| Monolithic config.yaml | Glob-and-merge (OmegaConf or PyYAML) | `config.d/*.yaml` overlay directory |
| Large single-file modules | Package with `__init__.py` re-exports | `__all__`, `_base.py` for shared types, compat tests |

All patterns preserve backward compatibility and require zero changes to existing call sites.

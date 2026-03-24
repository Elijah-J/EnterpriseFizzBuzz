# Round 17.5: The Bottleneck Demolition Sprint

## Implementation Plan

**Architect:** Planz
**Date:** 2026-03-24
**Goal:** Refactor 5 monolithic shared files into modular architectures so that adding a new feature requires ONLY creating new files — zero edits to shared files. TeraSwarm-ready.

---

## Table of Contents

1. [Execution Order & Dependency Graph](#execution-order--dependency-graph)
2. [Refactor 1: Exception Sharding](#refactor-1-exception-sharding)
3. [Refactor 2: EventType Registry](#refactor-2-eventtype-registry)
4. [Refactor 3: Config Mixin Composition](#refactor-3-config-mixin-composition)
5. [Refactor 4: Feature Registry (Plugin Pattern)](#refactor-4-feature-registry-plugin-pattern)
6. [Refactor 5: Config YAML Split](#refactor-5-config-yaml-split)
7. [Verification Strategy](#verification-strategy)
8. [Rollback Plan](#rollback-plan)

---

## Execution Order & Dependency Graph

```
                    ┌──────────────────┐
                    │  Phase 1 (parallel) │
                    └──────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        Refactor 1    Refactor 2   Refactor 5
        Exceptions    EventType    YAML Split
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────────────────┐
                    │  Phase 2 (serial)  │
                    └──────────────────┘
                           │
                           ▼
                      Refactor 3
                      Config Mixins
                      (depends on R5:
                       YAML loader changes)
                           │
                           ▼
                      Refactor 4
                      Feature Registry
                      (depends on R1-R3:
                       imports must resolve)
```

**Phase 1** — Refactors 1, 2, and 5 are fully independent and can run in parallel. They touch different files with zero overlap.

**Phase 2** — Refactor 3 (Config Mixins) should run after Refactor 5 (YAML Split) because the config loader changes in R5 affect the base class that R3 splits into mixins. Running them sequentially avoids merge conflicts in `infrastructure/config.py`.

**Phase 3** — Refactor 4 (Feature Registry) runs last. It restructures `__main__.py`, which imports from exceptions, models, and config. All three must be stable in their new package forms before `__main__.py` is restructured.

---

## Refactor 1: Exception Sharding

### Overview

Convert `enterprise_fizzbuzz/domain/exceptions.py` (18,105 lines, 935 classes) into a package with one file per subsystem group. The `__init__.py` re-exports everything. Zero changes to the 204 files that import from it.

### Directory Structure

**Before:**
```
enterprise_fizzbuzz/domain/
├── __init__.py
├── exceptions.py          # 18,105 lines, 935 classes
├── interfaces.py
└── models.py
```

**After:**
```
enterprise_fizzbuzz/domain/
├── __init__.py
├── exceptions/
│   ├── __init__.py         # re-exports all 935 classes via __all__
│   ├── _base.py            # FizzBuzzError, ConfigurationError, RuleEvaluationError,
│   │                       # and other root/cross-cutting exceptions (~1100 lines)
│   ├── cache.py            # Cache subsystem exceptions
│   ├── circuit_breaker.py  # Circuit breaker exceptions (extracted from _base.py range)
│   ├── migrations.py       # Database migration framework exceptions
│   ├── container.py        # DI container exceptions
│   ├── health.py           # Health check probe exceptions
│   ├── repository.py       # Repository pattern + UoW exceptions
│   ├── metrics.py          # Prometheus-style metrics exceptions
│   ├── webhooks.py         # Webhook notification exceptions
│   ├── service_mesh.py     # Service mesh exceptions
│   ├── hot_reload.py       # Config hot-reload exceptions
│   ├── rate_limiter.py     # Rate limiting exceptions
│   ├── compliance.py       # Compliance & regulatory exceptions
│   ├── finops.py           # FinOps cost tracking exceptions
│   ├── disaster_recovery.py # DR & backup/restore exceptions
│   ├── ab_testing.py       # A/B testing framework exceptions
│   ├── message_queue.py    # Message queue & event bus exceptions
│   ├── secrets_vault.py    # Secrets management vault exceptions
│   ├── data_pipeline.py    # Data pipeline & ETL exceptions
│   ├── openapi.py          # OpenAPI spec generator exceptions
│   ├── blue_green.py       # Blue/green deployment exceptions
│   ├── graph_db.py         # Graph database exceptions
│   ├── genetic_algorithm.py # Genetic algorithm exceptions
│   ├── nlq.py              # Natural language query exceptions
│   ├── load_testing.py     # Load testing framework exceptions
│   ├── audit_dashboard.py  # Audit dashboard exceptions
│   ├── gitops.py           # GitOps exceptions
│   ├── formal_verification.py # Formal verification exceptions
│   ├── time_travel.py      # Time-travel debugger exceptions
│   ├── bytecode_vm.py      # Bytecode VM exceptions
│   ├── query_optimizer.py  # Query optimizer exceptions
│   ├── paxos.py            # Distributed Paxos exceptions
│   ├── cross_compiler.py   # Cross-compiler exceptions
│   ├── federated.py        # Federated learning exceptions
│   ├── knowledge_graph.py  # Knowledge graph exceptions
│   ├── self_modifying.py   # Self-modifying code exceptions
│   ├── compliance_chatbot.py # Compliance chatbot exceptions
│   ├── kernel.py           # OS kernel exceptions
│   ├── p2p_network.py      # P2P gossip network exceptions
│   ├── fizzlang.py         # FizzLang DSL exceptions
│   ├── recommendations.py  # Recommendation engine exceptions
│   ├── archaeology.py      # Archaeological recovery exceptions
│   ├── dependent_types.py  # Dependent type system exceptions
│   ├── fizzkube.py         # FizzKube orchestration exceptions
│   ├── fizzpm.py           # FizzPM package manager exceptions
│   ├── fizzsql.py          # FizzSQL query engine exceptions
│   ├── ip_office.py        # IP office exceptions
│   ├── distributed_locks.py # Distributed lock manager exceptions
│   ├── cdc.py              # Change data capture exceptions
│   ├── billing.py          # Billing & revenue exceptions
│   ├── observability.py    # Observability correlation exceptions
│   ├── capability_security.py # Capability-based security exceptions
│   ├── intent_log.py       # Write-ahead intent log exceptions
│   ├── grammar.py          # Formal grammar exceptions
│   ├── memory_allocator.py # Custom memory allocator exceptions
│   ├── columnar_storage.py # Columnar storage exceptions
│   ├── mapreduce.py        # MapReduce framework exceptions
│   ├── schema_evolution.py # Schema evolution exceptions
│   ├── model_check.py      # Model checking exceptions
│   ├── sli.py              # Service level indicator exceptions
│   ├── proxy.py            # Reverse proxy exceptions
│   ├── digital_logic.py    # Digital logic circuit exceptions
│   ├── bloom.py            # Bloom filter exceptions
│   ├── ssa_ir.py           # SSA intermediate representation exceptions
│   ├── proof_certificates.py # Proof certificate exceptions
│   ├── virtual_fs.py       # Virtual file system exceptions
│   ├── audio_synth.py      # Audio synthesis exceptions
│   ├── network_stack.py    # TCP/IP protocol stack exceptions
│   ├── protein_folding.py  # Protein folding exceptions
│   ├── fizz_vcs.py         # Version control exceptions
│   ├── elf_format.py       # ELF binary format exceptions
│   ├── replication.py      # Database replication exceptions
│   ├── z_spec.py           # Z specification exceptions
│   ├── flame_graph.py      # Flame graph generator exceptions
│   ├── regex_engine.py     # Regex engine exceptions
│   ├── spreadsheet.py      # Spreadsheet engine exceptions
│   ├── smart_contracts.py  # Smart contract exceptions
│   ├── cpu_pipeline.py     # CPU pipeline exceptions
│   ├── spatial_db.py       # Spatial database exceptions
│   ├── clock_sync.py       # Clock synchronization exceptions
│   ├── cognitive_load.py   # Operator cognitive load exceptions
│   ├── approval_workflow.py # Multi-party approval exceptions
│   ├── pager.py            # Incident paging exceptions
│   ├── succession.py       # Operator succession exceptions
│   ├── performance_review.py # Performance review exceptions
│   ├── org_hierarchy.py    # Organizational hierarchy exceptions
│   ├── namespaces.py       # Linux namespace exceptions
│   ├── cgroups.py          # Cgroup resource accounting exceptions
│   ├── oci_runtime.py      # OCI container runtime exceptions
│   ├── overlay_fs.py       # Copy-on-write union FS exceptions
│   ├── container_registry.py # OCI image registry exceptions
│   ├── cni.py              # Container network interface exceptions
│   ├── containerd.py       # Container daemon exceptions
│   ├── container_chaos.py  # Container chaos engineering exceptions
│   ├── container_ops.py    # Container observability exceptions
│   ├── deploy.py           # Deployment pipeline exceptions
│   ├── compose.py          # Multi-container orchestration exceptions
│   ├── kubev2.py           # KubeV2 orchestrator exceptions
│   ├── fizzlife.py         # Cellular automaton simulation exceptions
│   ├── dns_server.py       # DNS server exceptions
│   ├── typesetting.py      # TeX typesetting exceptions
│   ├── bootloader.py       # x86 bootloader exceptions
│   ├── garbage_collector.py # Garbage collector exceptions
│   ├── microkernel.py      # Microkernel IPC exceptions
│   ├── video_codec.py      # Video codec exceptions
│   ├── ray_tracer.py       # Ray tracer exceptions
│   ├── process_migration.py # Process migration exceptions
│   ├── shader_compiler.py  # GPU shader compiler exceptions
│   ├── jit.py              # JIT compiler exceptions
│   ├── otel_tracing.py     # OpenTelemetry tracing exceptions
│   └── fizzimage.py        # Container image catalog exceptions
├── interfaces.py
└── models.py
```

### What Code Moves Where

Each file in `exceptions/` contains the exception classes from one comment-delimited section of the original `exceptions.py`. The grouping follows the existing `# === Section Name ===` headers exactly.

**`_base.py`** contains:
- `FizzBuzzError` (the root exception)
- `ConfigurationError`, `ConfigurationFileNotFoundError`, `ConfigurationValidationError`
- `RuleEvaluationError`, `RuleConflictError`, `RuleNotFoundError`, `RulePriorityError`
- `MiddlewareError`, `MiddlewareChainError`, `MiddlewareTimeoutError`
- `FormatterError`, `UnsupportedFormatError`
- `PluginError`, `PluginLoadError`, `PluginConflictError`
- `EventBusError`, `DuplicateObserverError`
- `BuilderError`, `IncompleteBuilderError`
- All other exceptions that appear before the first subsystem section header (approximately lines 1-1100)

All subsystem files import `FizzBuzzError` (and any parent classes they inherit from) via `from ._base import FizzBuzzError`.

### Re-Export / Backward-Compatibility Shim

**`exceptions/__init__.py`:**
```python
"""Enterprise FizzBuzz Platform - Exception Hierarchy.

This package was split from a single module for parallel development.
All exception classes remain importable from this path.
"""
from enterprise_fizzbuzz.domain.exceptions._base import *  # noqa: F401,F403
from enterprise_fizzbuzz.domain.exceptions.cache import *  # noqa: F401,F403
from enterprise_fizzbuzz.domain.exceptions.circuit_breaker import *  # noqa: F401,F403
# ... one line per subsystem file ...

# Explicit __all__ listing every class for IDE support and `import *` safety.
__all__ = [
    "FizzBuzzError",
    "ConfigurationError",
    # ... all 935 class names ...
]
```

**Root-level `exceptions.py`** (unchanged):
```python
"""Backward-compatible re-export stub for exceptions."""
from enterprise_fizzbuzz.domain.exceptions import *  # noqa: F401,F403
```

This is already a wildcard re-export. Since the new `__init__.py` re-exports everything from the submodules, the root stub continues to work without modification.

### Existing Tests That Need Changes

**Zero.** All 204 importing files use `from enterprise_fizzbuzz.domain.exceptions import SomeException`. The `__init__.py` re-exports preserve this path exactly.

### New Tests to Add

**File: `tests/test_exception_sharding.py`** (~80 lines)

1. **Backward compatibility test** — Verify all 935 exception class names are importable from `enterprise_fizzbuzz.domain.exceptions`.
2. **Inheritance integrity test** — Verify every exception class is a subclass of `FizzBuzzError`.
3. **No circular import test** — Import each subsystem file individually and verify no `ImportError`.
4. **Root stub test** — Verify the root-level `exceptions.py` re-exports all classes.
5. **`__all__` completeness test** — Verify `__all__` in `__init__.py` matches the actual set of exported classes.

### Estimated Lines

| Category | Lines |
|----------|-------|
| Moved code (from exceptions.py) | ~18,105 |
| New code (__init__.py with re-exports + __all__) | ~1,050 |
| New tests | ~80 |
| Net new lines | ~1,130 |

### Risk Level: LOW

**Rationale:** No behavioral changes. Pure file reorganization with re-exports. The architecture tests validate layer purity, not import paths. Every import path is preserved.

**Mitigation:** Generate `__all__` programmatically from the original file to ensure completeness. Run the full test suite after the split.

---

## Refactor 2: EventType Registry

### Overview

Replace the monolithic `EventType(Enum)` in `domain/models.py` (822 members, lines 115-1016) with a dynamic registry class. Each infrastructure module registers its own event types at import time. The `EventType.SOME_NAME` attribute access, `==`, and `hash` APIs remain identical.

### Directory Structure

**Before:**
```
enterprise_fizzbuzz/domain/
├── models.py              # EventType enum with 822 members + 37 other classes/enums
```

**After:**
```
enterprise_fizzbuzz/domain/
├── models.py              # 37 other classes/enums (EventType import preserved via re-export)
├── events/
│   ├── __init__.py         # exports EventType registry instance
│   ├── _registry.py        # _EventValue + _EventTypeRegistry classes
│   ├── _core.py            # Core event registrations (SESSION_*, NUMBER_*, RULE_*, etc.)
│   ├── _circuit_breaker.py # CIRCUIT_BREAKER_* events
│   ├── _auth.py            # AUTHORIZATION_*, TOKEN_* events
│   ├── _event_sourcing.py  # ES_* events
│   ├── _chaos.py           # CHAOS_* events
│   ├── _feature_flags.py   # FLAG_* events
│   ├── _sla.py             # SLA_* events
│   ├── _cache.py           # CACHE_* events
│   ├── _repository.py      # REPOSITORY_*, ROLLBACK_* events
│   ├── _migrations.py      # MIGRATION_* events
│   ├── _metrics.py         # METRICS_* events
│   ├── _webhooks.py        # WEBHOOK_* events
│   ├── _service_mesh.py    # MESH_* events
│   ├── _hot_reload.py      # HOT_RELOAD_* events
│   ├── _rate_limiter.py    # RATE_LIMIT_* events
│   ├── _compliance.py      # COMPLIANCE_*, DATA_CLASS_* events
│   ├── _finops.py          # FINOPS_*, COST_* events
│   ├── _disaster_recovery.py # DR_* events
│   ├── _ab_testing.py      # AB_*, EXPERIMENT_* events
│   ├── _message_queue.py   # MQ_* events
│   ├── _secrets_vault.py   # VAULT_* events
│   ├── _data_pipeline.py   # PIPELINE_* events
│   ├── _api_gateway.py     # GATEWAY_* events
│   ├── _blue_green.py      # BLUE_GREEN_* events
│   ├── _graph_db.py        # GRAPH_* events
│   ├── _genetic.py         # GENETIC_* events
│   ├── _nlq.py             # NLQ_* events
│   ├── _load_testing.py    # LOAD_TEST_* events
│   ├── _audit.py           # AUDIT_* events
│   ├── _gitops.py          # GITOPS_* events
│   ├── _billing.py         # BILLING_*, FBAAS_* events
│   ├── _bytecode_vm.py     # VM_* events
│   ├── _query_optimizer.py # QO_* events
│   ├── _paxos.py           # PAXOS_* events
│   ├── _quantum.py         # QUANTUM_* events
│   ├── _cross_compiler.py  # COMPILER_* events
│   ├── _federated.py       # FL_* events
│   ├── _knowledge_graph.py # KG_* events
│   ├── _digital_twin.py    # TWIN_* events
│   ├── _fizzlang.py        # FIZZLANG_* events
│   ├── _archaeology.py     # ARCH_* events
│   ├── _kernel.py          # KERNEL_*, SCHEDULER_* events
│   ├── _p2p_network.py     # P2P_* events
│   ├── _fizzkube.py        # FIZZKUBE_* events
│   ├── _fizzpm.py          # FIZZPM_* events
│   ├── _fizzsql.py         # FIZZSQL_* events
│   ├── _ip_office.py       # IP_* events
│   ├── _distributed_locks.py # LOCK_* events
│   ├── _cdc.py             # CDC_* events
│   ├── _capability.py      # CAPABILITY_* events
│   ├── _otel.py            # OTEL_* events
│   ├── _network_stack.py   # NET_* events
│   ├── _containers.py      # NS_*, CG_*, OCI_*, OVERLAY_*, REGISTRY_*, CNI_*,
│   │                       # CONTAINERD_*, FIZZIMAGE_*, CONTAINER_CHAOS_*,
│   │                       # CONTAINER_OPS_*, DEPLOY_*, COMPOSE_*, KUBEV2_* events
│   ├── _misc.py            # All remaining subsystem events (intent_log, crdt,
│   │                       # columnar, mapreduce, model_check, flame_graph,
│   │                       # regex, spreadsheet, spatial, clock, audio, ray_tracer,
│   │                       # protein, vfs, vcs, elf, replication, proof, etc.)
│   └── _fizzlife.py        # FIZZLIFE_* events
```

### What Code Moves Where

**`_registry.py`** — New file containing:
- `_EventValue` class: immutable, hashable value object with `name` and `value` properties, `__eq__`, `__hash__`, and `__repr__`.
- `_EventTypeRegistry` class: supports `__getattr__` for `EventType.SOME_NAME`, `__contains__`, `__iter__`, `__len__`, and a `register(name, value=None)` method.
- `EventType = _EventTypeRegistry()` — the singleton instance.

**`_core.py`** — Registers the core events (SESSION_STARTED through TOKEN_VALIDATION_FAILED, lines 118-144 of original). Pattern:
```python
from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("SESSION_STARTED")
EventType.register("SESSION_ENDED")
# ... etc.
```

**Each `_subsystem.py` file** — Registers that subsystem's events using the same `EventType.register("NAME")` pattern. Events are grouped by the existing comment headers in `models.py`.

**`events/__init__.py`:**
```python
"""Enterprise FizzBuzz Platform - Event Type Registry.

Event types are registered by subsystem modules at import time.
Core events are loaded eagerly; subsystem events are loaded when
their infrastructure modules are imported.
"""
from enterprise_fizzbuzz.domain.events._registry import EventType, _EventValue

# Load core events eagerly (always needed)
import enterprise_fizzbuzz.domain.events._core  # noqa: F401

# Load ALL subsystem events eagerly to maintain backward compatibility.
# Every EventType member that existed before the split must be available
# after importing this package, regardless of which infrastructure modules
# have been imported.
import enterprise_fizzbuzz.domain.events._circuit_breaker  # noqa: F401
import enterprise_fizzbuzz.domain.events._auth  # noqa: F401
# ... one import per subsystem file ...

__all__ = ["EventType", "_EventValue"]
```

**Critical design decision: eager loading.** All event registration files are imported eagerly in `__init__.py`. This ensures that `EventType.CACHE_HIT` is available the moment any code does `from enterprise_fizzbuzz.domain.models import EventType`, exactly as before. Lazy loading would break code that references event types before the corresponding infrastructure module is imported.

**`models.py` changes:**
- Remove the entire `EventType(Enum)` class (lines 115-1016, ~900 lines).
- Add at the top: `from enterprise_fizzbuzz.domain.events import EventType  # noqa: F401`
- This preserves the `from enterprise_fizzbuzz.domain.models import EventType` import path.

### API Compatibility Contract

The `_EventTypeRegistry` must support these operations identically to the old `Enum`:

| Operation | Old (Enum) | New (Registry) |
|-----------|-----------|----------------|
| `EventType.CACHE_HIT` | Returns enum member | Returns `_EventValue` instance |
| `event == EventType.CACHE_HIT` | `True` if same member | `True` if same value |
| `{EventType.CACHE_HIT: handler}` | Works (enum is hashable) | Works (`_EventValue` is hashable) |
| `event.name` | `"CACHE_HIT"` | `"CACHE_HIT"` |
| `event.value` | `auto()` int | `"CACHE_HIT"` (string, unless int preserved) |
| `for e in EventType` | Iterates all members | Iterates all `_EventValue`s |
| `len(EventType)` | 822 | 822 |
| `EventType.CACHE_HIT in EventType` | `True` | `True` |
| `repr(EventType.CACHE_HIT)` | `<EventType.CACHE_HIT: N>` | `EventType.CACHE_HIT` |

**Value strategy:** Use auto-incrementing integers to match the old `auto()` behavior. The `register()` method assigns the next integer if no value is provided. This preserves `==` semantics for any code that compares `.value`.

```python
class _EventTypeRegistry:
    def __init__(self):
        self._members = {}
        self._by_value = {}
        self._next_value = 1

    def register(self, name, value=None):
        if name in self._members:
            return self._members[name]
        if value is None:
            value = self._next_value
            self._next_value += 1
        ev = _EventValue(name, value)
        self._members[name] = ev
        self._by_value[value] = ev
        return ev
```

### Existing Tests That Need Changes

**Zero** for tests that use `EventType.SOME_NAME` comparisons and attribute access.

**Potential issue:** Any test that does `isinstance(event_type, Enum)` or uses Enum-specific APIs like `EventType["CACHE_HIT"]` (bracket access) or `EventType(42)` (value lookup) will need the registry to support those. The registry class should implement:
- `__getitem__(name)` for bracket access
- `__call__(value)` for value lookup

These are added to `_EventTypeRegistry` to maintain full backward compatibility.

### New Tests to Add

**File: `tests/test_event_registry.py`** (~120 lines)

1. **Member count test** — Verify `len(EventType) == 822` (or current count).
2. **Attribute access test** — Spot-check `EventType.SESSION_STARTED`, `EventType.CACHE_HIT`, etc.
3. **Equality and hashing test** — Verify `EventType.X == EventType.X`, `EventType.X != EventType.Y`, and dict key usage.
4. **Iteration test** — Verify `list(EventType)` returns all members.
5. **Containment test** — Verify `EventType.X in EventType`.
6. **Name/value properties** — Verify `.name` and `.value` on event values.
7. **Registration idempotency** — `register("X")` twice returns the same object.
8. **Backward compat import test** — `from enterprise_fizzbuzz.domain.models import EventType` still works.
9. **Root stub test** — `from models import EventType` works via root re-export.
10. **Bracket access test** — `EventType["CACHE_HIT"]` works.

### Estimated Lines

| Category | Lines |
|----------|-------|
| Removed from models.py | ~900 |
| New _registry.py | ~100 |
| New registration files (total) | ~900 (moved member definitions) |
| New __init__.py | ~80 |
| Re-export line in models.py | ~1 |
| New tests | ~120 |
| Net new lines | ~300 |

### Risk Level: MEDIUM

**Rationale:** Replacing a stdlib `Enum` with a custom class could break code that relies on Enum-specific APIs (`isinstance`, `_member_map_`, bracket access, value-based construction). The registry must faithfully replicate these behaviors.

**Mitigation:**
1. Implement `__getitem__`, `__call__`, and `__contains__` on the registry.
2. Run the full 11,400 test suite after implementation.
3. Grep for `isinstance.*EventType` and `Enum` references to find code that assumes Enum semantics.

---

## Refactor 3: Config Mixin Composition

### Overview

Convert `enterprise_fizzbuzz/infrastructure/config.py` (7,665 lines, 965 `@property` methods) into a package with a base class and per-subsystem mixin files. The `ConfigurationManager` class is composed from mixins via explicit MRO in the class definition.

### Directory Structure

**Before:**
```
enterprise_fizzbuzz/infrastructure/
├── config.py              # 7,665 lines, one class with 965 @property methods
```

**After:**
```
enterprise_fizzbuzz/infrastructure/
├── config/
│   ├── __init__.py         # re-exports ConfigurationManager, _SingletonMeta, _DEFAULT_CONFIG_PATH
│   ├── _base.py            # _SingletonMeta, _ConfigurationBase (init, load, _ensure_loaded,
│   │                       # _get_defaults, _apply_environment_overrides, _validate, get_raw,
│   │                       # and core properties: range_start, range_end, rules, strategy, etc.)
│   ├── _mixins/
│   │   ├── __init__.py
│   │   ├── cache.py        # CacheConfigMixin — cache_* properties
│   │   ├── circuit_breaker.py # CircuitBreakerConfigMixin
│   │   ├── auth.py         # AuthConfigMixin — rbac_* properties
│   │   ├── i18n.py         # I18nConfigMixin
│   │   ├── event_sourcing.py # EventSourcingConfigMixin
│   │   ├── chaos.py        # ChaosConfigMixin
│   │   ├── feature_flags.py # FeatureFlagsConfigMixin
│   │   ├── sla.py          # SLAConfigMixin
│   │   ├── migrations.py   # MigrationsConfigMixin
│   │   ├── metrics.py      # MetricsConfigMixin
│   │   ├── webhooks.py     # WebhooksConfigMixin
│   │   ├── service_mesh.py # ServiceMeshConfigMixin
│   │   ├── hot_reload.py   # HotReloadConfigMixin
│   │   ├── rate_limiting.py # RateLimitingConfigMixin
│   │   ├── compliance.py   # ComplianceConfigMixin
│   │   ├── finops.py       # FinOpsConfigMixin
│   │   ├── disaster_recovery.py # DRConfigMixin
│   │   ├── ab_testing.py   # ABTestingConfigMixin
│   │   ├── message_queue.py # MessageQueueConfigMixin
│   │   ├── vault.py        # VaultConfigMixin
│   │   ├── data_pipeline.py # DataPipelineConfigMixin
│   │   ├── openapi.py      # OpenAPIConfigMixin
│   │   ├── api_gateway.py  # APIGatewayConfigMixin
│   │   ├── blue_green.py   # BlueGreenConfigMixin
│   │   ├── graph_db.py     # GraphDBConfigMixin
│   │   ├── genetic.py      # GeneticConfigMixin
│   │   ├── billing.py      # BillingConfigMixin
│   │   ├── bytecode_vm.py  # BytecodeVMConfigMixin
│   │   ├── query_optimizer.py # QueryOptimizerConfigMixin
│   │   ├── paxos.py        # PaxosConfigMixin
│   │   ├── quantum.py      # QuantumConfigMixin
│   │   ├── cross_compiler.py # CrossCompilerConfigMixin
│   │   ├── federated.py    # FederatedConfigMixin
│   │   ├── knowledge_graph.py # KnowledgeGraphConfigMixin
│   │   ├── digital_twin.py # DigitalTwinConfigMixin
│   │   ├── kernel.py       # KernelConfigMixin
│   │   ├── fizzlang.py     # FizzLangConfigMixin
│   │   ├── archaeology.py  # ArchaeologyConfigMixin
│   │   ├── fizzkube.py     # FizzKubeConfigMixin
│   │   ├── containers.py   # ContainersConfigMixin (NS, CG, OCI, overlay, registry, CNI,
│   │   │                   # containerd, fizzimage, container chaos/ops, deploy, compose, kubev2)
│   │   └── misc.py         # Remaining small subsystems (ip_office, locks, cdc,
│   │                       # capability, otel, network, mapreduce, etc.)
│   └── _manager.py         # ConfigurationManager class definition (composed from mixins)
```

### What Code Moves Where

**`_base.py`** (~350 lines) contains:
- `_SingletonMeta` metaclass
- `_DEFAULT_CONFIG_PATH`
- `_ConfigurationBase` class with:
  - `__init__`, `load`, `_ensure_loaded`, `_get_defaults`, `_apply_environment_overrides`, `_validate`
  - `get_raw(key, default)` utility method
  - Core properties that every subsystem depends on: `range_start`, `range_end`, `rules`, `strategy`, `output_format`, `log_level`, etc. (approximately the first 30-40 properties)

**Each mixin file** contains a single mixin class with `@property` methods for that subsystem. Every mixin method calls `self._ensure_loaded()` and `self._raw_config.get(...)` exactly as the original code does — no behavioral changes. Example:

```python
# _mixins/cache.py
class CacheConfigMixin:
    """Configuration properties for the cache subsystem."""

    @property
    def cache_enabled(self):
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("enabled", False)

    @property
    def cache_max_size(self):
        self._ensure_loaded()
        return self._raw_config.get("cache", {}).get("max_size", 1024)

    # ... all cache_* properties ...
```

**`_manager.py`** — The composed class:
```python
from enterprise_fizzbuzz.infrastructure.config._base import _ConfigurationBase, _SingletonMeta
from enterprise_fizzbuzz.infrastructure.config._mixins.cache import CacheConfigMixin
from enterprise_fizzbuzz.infrastructure.config._mixins.circuit_breaker import CircuitBreakerConfigMixin
# ... all mixin imports ...

class ConfigurationManager(
    CacheConfigMixin,
    CircuitBreakerConfigMixin,
    # ... all mixins in alphabetical order ...
    _ConfigurationBase,
    metaclass=_SingletonMeta,
):
    """Singleton configuration manager for the Enterprise FizzBuzz Platform.

    Composed from per-subsystem mixins. Each mixin file handles
    one subsystem's configuration interface. The base class provides
    YAML loading, environment variable overrides, and validation.
    """
    pass
```

**`config/__init__.py`:**
```python
"""Enterprise FizzBuzz Platform - Configuration Management.

This package was split from a single module for parallel development.
All public names remain importable from this path.
"""
from enterprise_fizzbuzz.infrastructure.config._base import _SingletonMeta, _DEFAULT_CONFIG_PATH
from enterprise_fizzbuzz.infrastructure.config._manager import ConfigurationManager

__all__ = ["ConfigurationManager", "_SingletonMeta", "_DEFAULT_CONFIG_PATH"]
```

### Re-Export / Backward-Compatibility Shim

The `config/__init__.py` re-exports `ConfigurationManager`, `_SingletonMeta`, and `_DEFAULT_CONFIG_PATH`.

**Root-level `config.py`** (unchanged):
```python
"""Backward-compatible re-export stub for config."""
from enterprise_fizzbuzz.infrastructure.config import *  # noqa: F401,F403
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta, _DEFAULT_CONFIG_PATH  # noqa: F401
```

### Existing Tests That Need Changes

**Zero.** All tests import `from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager`. The re-export preserves this path. The `_SingletonMeta.reset()` fixture pattern continues to work because `_SingletonMeta` is re-exported.

### New Tests to Add

**File: `tests/test_config_composition.py`** (~60 lines)

1. **Import compatibility test** — `from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta`.
2. **Mixin composition test** — Verify `ConfigurationManager` has all expected properties via `hasattr`.
3. **Property count test** — Verify the composed class has >= 965 properties (sanity check).
4. **Singleton behavior test** — Verify `_SingletonMeta` still works after the split.
5. **Root stub test** — `from config import ConfigurationManager` works.

### Estimated Lines

| Category | Lines |
|----------|-------|
| Moved code (from config.py) | ~7,665 |
| New __init__.py | ~15 |
| New _base.py (extracted) | ~350 |
| New _manager.py | ~60 |
| New _mixins/__init__.py | ~1 |
| New mixin files (total) | ~7,250 (moved property methods) |
| New tests | ~60 |
| Net new lines | ~135 |

### Risk Level: LOW

**Rationale:** Pure extraction of methods into mixin classes. No behavioral changes. Python MRO handles method resolution identically to a single class. The `_ensure_loaded` / `_raw_config` pattern means mixins access state from the base class seamlessly.

**Mitigation:** Verify `dir(ConfigurationManager)` has the same property set before and after the split. A simple test can diff the two.

---

## Refactor 4: Feature Registry (Plugin Pattern)

### Overview

Convert the hardcoded wiring in `enterprise_fizzbuzz/__main__.py` (12,646 lines, 128 import lines, 509 `add_argument` calls, ~96 builder calls) into a self-registering feature system. Each feature defines its CLI flags, factory function, and post-execution rendering in a feature descriptor file. `__main__.py` discovers and wires them automatically.

### Directory Structure

**Before:**
```
enterprise_fizzbuzz/
├── __main__.py            # 12,646 lines — imports, argparse, wiring, dashboards
```

**After:**
```
enterprise_fizzbuzz/
├── __main__.py            # ~500 lines — discovery, orchestration, core flags only
├── infrastructure/
│   ├── features/
│   │   ├── __init__.py     # FeatureDescriptor base class + registry + discovery
│   │   ├── _core.py        # Core flags (--range, --format, --strategy, --config, etc.)
│   │   ├── blockchain.py   # Blockchain feature descriptor
│   │   ├── cache.py        # Cache feature descriptor
│   │   ├── circuit_breaker.py # Circuit breaker feature descriptor
│   │   ├── auth.py         # RBAC/auth feature descriptor
│   │   ├── i18n.py         # i18n feature descriptor
│   │   ├── event_sourcing.py
│   │   ├── chaos.py
│   │   ├── feature_flags.py
│   │   ├── sla.py
│   │   ├── metrics.py
│   │   ├── webhooks.py
│   │   ├── service_mesh.py
│   │   ├── hot_reload.py
│   │   ├── rate_limiter.py
│   │   ├── compliance.py
│   │   ├── finops.py
│   │   ├── disaster_recovery.py
│   │   ├── ab_testing.py
│   │   ├── message_queue.py
│   │   ├── secrets_vault.py
│   │   ├── data_pipeline.py
│   │   ├── openapi.py
│   │   ├── api_gateway.py
│   │   ├── billing.py
│   │   ├── bytecode_vm.py
│   │   ├── cross_compiler.py
│   │   ├── fizzlang.py
│   │   ├── digital_twin.py
│   │   ├── fizzkube.py
│   │   ├── kernel.py
│   │   ├── dns_server.py
│   │   ├── typesetting.py
│   │   ├── bootloader.py
│   │   ├── containers.py   # NS, CG, OCI, overlay, registry, CNI, containerd,
│   │   │                   # fizzimage, container chaos/ops, deploy, compose, kubev2
│   │   └── ... (one per feature or feature group)
```

### Feature Descriptor Protocol

**`features/__init__.py`** defines the base class and registry:

```python
"""Feature descriptor registry for the Enterprise FizzBuzz Platform.

Each feature descriptor declares its CLI flags, initialization logic,
middleware factory, and post-execution rendering. The main entry point
discovers all descriptors and orchestrates them.
"""
import os
import importlib.util
from typing import Optional


class FeatureDescriptor:
    """Base class for feature descriptors. Subclasses auto-register."""

    _registry: dict[str, "FeatureDescriptor"] = {}
    name: str = ""              # Feature name (e.g., "blockchain")
    priority: int = 100         # Middleware priority (lower = earlier)

    @classmethod
    def __init_subclass__(cls, feature_name: str = "", **kwargs):
        super().__init_subclass__(**kwargs)
        if feature_name:
            cls.name = feature_name
            cls._registry[feature_name] = cls

    @classmethod
    def get_all(cls) -> dict[str, "FeatureDescriptor"]:
        return dict(cls._registry)

    def add_arguments(self, parser) -> None:
        """Add feature-specific CLI flags to the argument parser."""
        pass

    def configure(self, args, config, event_bus, builder) -> Optional[object]:
        """Initialize the feature from CLI args and config.

        Returns a context object (middleware instance, subsystem handle,
        or None) that will be passed to render_post_execution().
        """
        return None

    def handle_early_exit(self, args, config) -> Optional[int]:
        """Handle early-exit commands (e.g., --compile-to, --fizzlang-repl).

        Returns an exit code if the feature handled the command, or None
        to continue normal execution.
        """
        return None

    def render_banner(self, args, config) -> Optional[str]:
        """Return a banner string to print at startup, or None."""
        return None

    def render_post_execution(self, args, context) -> None:
        """Print post-execution dashboards, reports, etc."""
        pass

    def cleanup(self, context) -> None:
        """Perform cleanup (stop watchers, shut down subsystems)."""
        pass


# --- Auto-discover all feature descriptors in this directory ---
_dir = os.path.dirname(os.path.abspath(__file__))
for _fname in sorted(os.listdir(_dir)):
    if _fname.endswith('.py') and not _fname.startswith('_'):
        _path = os.path.join(_dir, _fname)
        _name = _fname[:-3]
        _spec = importlib.util.spec_from_file_location(
            f"enterprise_fizzbuzz.infrastructure.features.{_name}", _path
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
```

### Example Feature Descriptor

**`features/blockchain.py`:**
```python
from enterprise_fizzbuzz.infrastructure.features import FeatureDescriptor


class BlockchainFeature(FeatureDescriptor, feature_name="blockchain"):
    """Blockchain-based immutable audit ledger for tamper-proof compliance."""

    priority = 200

    def add_arguments(self, parser):
        parser.add_argument(
            "--blockchain",
            action="store_true",
            help="Enable blockchain-based immutable audit ledger",
        )
        parser.add_argument(
            "--mining-difficulty",
            type=int,
            default=2,
            metavar="N",
            help="Proof-of-work difficulty for blockchain mining (default: 2)",
        )
        parser.add_argument(
            "--blockchain-dashboard",
            action="store_true",
            help="Display blockchain ledger dashboard after evaluation",
        )

    def configure(self, args, config, event_bus, builder):
        if not args.blockchain:
            return None

        from enterprise_fizzbuzz.infrastructure.blockchain import (
            BlockchainObserver,
            FizzBuzzBlockchain,
        )

        blockchain = FizzBuzzBlockchain(
            difficulty=args.mining_difficulty,
        )
        observer = BlockchainObserver(blockchain=blockchain)
        event_bus.subscribe(observer)
        return {"blockchain": blockchain, "observer": observer}

    def render_banner(self, args, config):
        if not args.blockchain:
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | BLOCKCHAIN AUDIT LEDGER: ACTIVE                         |\n"
            "  |   Mining difficulty: {difficulty}                              |\n"
            "  |   Consensus: Proof-of-Work (SHA-256)                    |\n"
            "  +---------------------------------------------------------+"
        ).format(difficulty=args.mining_difficulty)

    def render_post_execution(self, args, context):
        if context is None:
            return
        if args.blockchain_dashboard:
            blockchain = context["blockchain"]
            # ... render dashboard ...
```

### New `__main__.py` Structure

The refactored `__main__.py` becomes an orchestrator:

```python
"""Enterprise FizzBuzz Platform - CLI Entry Point."""

import argparse
import sys
from typing import Optional

from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta
from enterprise_fizzbuzz.infrastructure.features import FeatureDescriptor


BANNER = "..."  # Kept in __main__.py


def build_argument_parser(features: dict) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(...)

    # Core flags (--range, --format, --strategy, etc.) are added by _core.py feature
    for feature in features.values():
        feat_instance = feature()
        feat_instance.add_arguments(parser)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    features = FeatureDescriptor.get_all()

    parser = build_argument_parser(features)
    args = parser.parse_args(argv)

    # Config
    _SingletonMeta.reset()
    config = ConfigurationManager(config_path=args.config)
    config.load()

    # Early exits
    for feat_cls in features.values():
        feat = feat_cls()
        exit_code = feat.handle_early_exit(args, config)
        if exit_code is not None:
            return exit_code

    # Event bus + builder setup
    from enterprise_fizzbuzz.infrastructure.observers import EventBus
    from enterprise_fizzbuzz.application.fizzbuzz_service import FizzBuzzServiceBuilder

    event_bus = EventBus()
    builder = FizzBuzzServiceBuilder()
    # ... core builder setup ...

    # Banner
    if not args.no_banner:
        print(BANNER)
        for feat_cls in sorted(features.values(), key=lambda f: f.priority):
            feat = feat_cls()
            banner = feat.render_banner(args, config)
            if banner:
                print(banner)

    # Configure all features
    contexts = {}
    for name, feat_cls in sorted(features.items(), key=lambda x: x[1].priority):
        feat = feat_cls()
        ctx = feat.configure(args, config, event_bus, builder)
        contexts[name] = (feat, ctx)

    # Build and execute
    service = builder.build()
    results = service.execute(range(config.range_start, config.range_end + 1))

    # Post-execution rendering
    for name, (feat, ctx) in contexts.items():
        feat.render_post_execution(args, ctx)

    # Cleanup
    for name, (feat, ctx) in contexts.items():
        feat.cleanup(ctx)

    return 0
```

### Re-Export / Backward-Compatibility

Nothing imports FROM `__main__.py` (confirmed by structural analysis). The module is a composition root only. No backward-compatibility shim needed.

### Existing Tests That Need Changes

**`tests/test_e2e.py`** — If it imports from `__main__` or calls `main()` directly, the function signature is preserved. The E2E tests should continue to pass since `main(argv)` still accepts the same CLI flags and produces the same output.

**Potential issue:** If any test patches internal names in `__main__` (e.g., `@mock.patch("enterprise_fizzbuzz.__main__.FizzBuzzBlockchain")`), those patches will need to target the feature descriptor modules instead. Grep for `__main__` in test files to identify these.

### New Tests to Add

**File: `tests/test_feature_registry.py`** (~100 lines)

1. **Discovery test** — Verify all expected features are discovered.
2. **Argument parser test** — Verify the parser has all expected flags.
3. **Feature descriptor protocol test** — Verify every descriptor has the required methods.
4. **Priority ordering test** — Verify features are wired in priority order.
5. **Early exit test** — Verify early-exit features return correct exit codes.

### Estimated Lines

| Category | Lines |
|----------|-------|
| Removed from __main__.py | ~12,100 (leaving ~500) |
| New features/__init__.py | ~80 |
| New feature descriptors (total) | ~10,000 (moved code, reorganized) |
| New _core.py | ~150 |
| New __main__.py orchestrator | ~500 |
| New tests | ~100 |
| Net new lines | ~730 |

### Risk Level: HIGH

**Rationale:** This is the most complex refactor. The wiring in `__main__.py` has subtle ordering dependencies, conditional logic, and cross-feature interactions (e.g., `event_bus` is shared, some features reference other features' state). Extracting each feature into an isolated descriptor requires careful dependency analysis.

**Mitigation:**
1. **Incremental approach** — Extract features one at a time, starting with the simplest (blockchain, cache) and progressing to the most complex (kernel, containers).
2. **Keep `__main__.py` as fallback** — During development, keep the old `main()` function renamed to `_main_legacy()`. If the new orchestrator fails, fall back.
3. **E2E tests are the safety net** — Run `python -m enterprise_fizzbuzz --range 1 100 --format plain` before and after, diff the output.
4. **Feature interaction map** — Before extracting, document which features reference each other's state (e.g., `event_bus`, `auth_context`, `fizzbuzz_kernel`).

### Implementation Phases for Refactor 4

Given the risk level, this refactor should be implemented in sub-phases:

**Phase 4a:** Create the `FeatureDescriptor` base class, registry, and discovery mechanism. Extract 5 simple features (blockchain, cache, i18n, circuit_breaker, chaos). Keep the rest in `__main__.py`.

**Phase 4b:** Extract the next 15 features (SLA, metrics, webhooks, service_mesh, hot_reload, rate_limiter, compliance, finops, DR, AB testing, message queue, vault, data_pipeline, openapi, API gateway).

**Phase 4c:** Extract the remaining features (billing, VM, cross-compiler, FizzLang, containers, kernel, etc.) and slim `__main__.py` to the final ~500-line orchestrator.

Each sub-phase is independently verifiable via the E2E test suite.

---

## Refactor 5: Config YAML Split

### Overview

Split `config.yaml` (2,247 lines, 103+ top-level keys) into a base file plus per-subsystem overlay files in `config.d/`. The loader merges them at startup using a glob-and-merge pattern with PyYAML (no new dependency).

### Directory Structure

**Before:**
```
config.yaml                # 2,247 lines, all subsystems in one file
```

**After:**
```
config.yaml                # ~80 lines — core settings only (application, range, rules,
│                          # engine, output, logging, middleware, plugins, observers)
config.d/
├── 00_circuit_breaker.yaml
├── 01_rbac.yaml
├── 02_event_sourcing.yaml
├── 03_chaos.yaml
├── 04_feature_flags.yaml
├── 05_sla.yaml
├── 06_cache.yaml
├── 07_migrations.yaml
├── 08_repository.yaml
├── 09_ml.yaml
├── 10_di.yaml
├── 11_health_check.yaml
├── 12_metrics.yaml
├── 13_webhooks.yaml
├── 14_service_mesh.yaml
├── 15_hot_reload.yaml
├── 16_rate_limiting.yaml
├── 17_compliance.yaml
├── 18_finops.yaml
├── 19_disaster_recovery.yaml
├── 20_ab_testing.yaml
├── 21_message_queue.yaml
├── 22_vault.yaml
├── 23_data_pipeline.yaml
├── 24_openapi.yaml
├── 25_api_gateway.yaml
├── 26_blue_green.yaml
├── 27_graph_db.yaml
├── 28_genetic_algorithm.yaml
├── 29_nlq.yaml
├── 30_load_testing.yaml
├── 31_audit_dashboard.yaml
├── 32_gitops.yaml
├── 33_formal_verification.yaml
├── 34_billing.yaml
├── 35_time_travel.yaml
├── 36_vm.yaml
├── 37_query_optimizer.yaml
├── 38_paxos.yaml
├── 39_quantum.yaml
├── 40_cross_compiler.yaml
├── 41_federated_learning.yaml
├── 42_knowledge_graph.yaml
├── 43_self_modifying.yaml
├── 44_kernel.yaml
├── 45_digital_twin.yaml
├── 46_fizzlang.yaml
├── 47_recommendation.yaml
├── 48_archaeology.yaml
├── 49_dependent_types.yaml
├── 50_fizzkube.yaml
├── 51_fizzpm.yaml
├── 52_fizzsql.yaml
├── 53_fizzdap.yaml
├── 54_ip_office.yaml
├── 55_distributed_locks.yaml
├── 56_cdc.yaml
├── 57_billing_revenue.yaml
├── 58_observability.yaml
├── 59_jit.yaml
├── 60_capability_security.yaml
├── 61_otel.yaml
├── 62_fizzwal.yaml
├── 63_crdt.yaml
├── 64_grammar.yaml
├── 65_memory_allocator.yaml
├── 66_columnar_storage.yaml
├── 67_mapreduce.yaml
├── 68_schema_evolution.yaml
├── 69_model_check.yaml
├── 70_sli.yaml
├── 71_proxy.yaml
├── 72_datalog.yaml
├── 73_ir.yaml
├── 74_proof_certificates.yaml
├── 75_synth.yaml
├── 76_containers.yaml      # NS, CG, OCI, overlay, registry, CNI, containerd,
│                           # fizzimage, container chaos/ops, deploy, compose, kubev2
├── 77_succession.yaml
├── 78_performance.yaml
├── 79_org.yaml
├── 80_pager.yaml
├── 81_approval.yaml
├── 82_cognitive_load.yaml
├── 83_fizzlife.yaml
└── 84_observers.yaml
```

### Config Loader Changes

The config loader in `_base.py` (or the original `config.py` before Refactor 3) gains a glob-and-merge step:

```python
import glob

def load(self) -> ConfigurationManager:
    """Load and validate configuration from YAML file and overlay directory."""
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed. Using built-in defaults.")
        self._raw_config = self._get_defaults()
        self._apply_environment_overrides()
        self._validate()
        self._loaded = True
        return self

    if not self._config_path.exists():
        raise ConfigurationFileNotFoundError(str(self._config_path))

    with open(self._config_path, "r") as f:
        self._raw_config = yaml.safe_load(f) or {}

    # Merge per-subsystem overlay files from config.d/
    overlay_dir = self._config_path.parent / "config.d"
    if overlay_dir.is_dir():
        for overlay_path in sorted(overlay_dir.glob("*.yaml")):
            with open(overlay_path, "r") as f:
                overlay = yaml.safe_load(f) or {}
            self._deep_merge(self._raw_config, overlay)

    self._apply_environment_overrides()
    self._validate()
    self._loaded = True
    logger.info("Configuration loaded from %s", self._config_path)
    return self

@staticmethod
def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base. Overlay values win."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            ConfigurationManager._deep_merge(base[key], value)
        else:
            base[key] = value
    return base
```

### What Code Moves Where

Each `config.d/NN_subsystem.yaml` file contains the top-level key(s) for that subsystem, extracted verbatim from `config.yaml`.

Example — `config.d/06_cache.yaml`:
```yaml
cache:
  enabled: false
  max_size: 1024
  ttl_seconds: 3600.0
  eviction_policy: "lru"
  enable_coherence_protocol: true
  enable_eulogies: true
  warming:
    enabled: false
    range_start: 1
    range_end: 100
```

The base `config.yaml` retains only the core keys: `application`, `range`, `rules`, `engine`, `output`, `logging`, `middleware`, `plugins`.

### Backward Compatibility

**`config.yaml` alone still works.** If `config.d/` does not exist, the loader skips the merge step. The `_get_defaults()` method is unchanged — it provides fallback values for every key.

**Precedence chain (unchanged):**
1. CLI flags (highest)
2. Environment variables (`EFP_*`)
3. `config.d/*.yaml` overlays (alphabetical order, later files win)
4. `config.yaml` base
5. Built-in defaults (lowest)

### Existing Tests That Need Changes

**Zero.** Tests use `ConfigurationManager` with either a custom config path or the singleton with defaults. The `config.d/` directory is optional — if tests don't create it, behavior is identical.

### New Tests to Add

**File: `tests/test_config_yaml_split.py`** (~80 lines)

1. **Base-only loading test** — Verify `config.yaml` without `config.d/` loads correctly.
2. **Overlay merge test** — Create a temp `config.d/` with one overlay, verify it merges.
3. **Deep merge test** — Verify nested dict merging (overlay updates nested key without clobbering siblings).
4. **Overlay ordering test** — Verify alphabetical ordering (00_ before 01_).
5. **Empty overlay test** — Verify empty YAML files don't break loading.
6. **Precedence test** — Verify environment variables still override overlays.

### Estimated Lines

| Category | Lines |
|----------|-------|
| Removed from config.yaml | ~2,170 |
| New config.d/ files (total) | ~2,170 (moved YAML) |
| New config.yaml (base only) | ~80 |
| New loader code (_deep_merge + overlay logic) | ~25 |
| New tests | ~80 |
| Net new lines | ~105 |

### Risk Level: LOW

**Rationale:** Additive change. The base `config.yaml` continues to work alone. The overlay directory is optional. The merge logic is straightforward. No import paths change.

**Mitigation:** After splitting, load both the old monolithic file and the new split files, compare the merged result dictionary. They must be identical.

---

## Verification Strategy

### Pre-Implementation Baseline

Before starting any refactor:

1. Run the full test suite: `python -m pytest tests/ -q`
2. Record the output of `python -m enterprise_fizzbuzz --range 1 20 --format plain`
3. Record the output of `python -m enterprise_fizzbuzz --range 1 5 --format json --metadata`
4. Save a snapshot of `dir(ConfigurationManager)` for property comparison
5. Save a snapshot of `len(EventType)` and a sample of member names

### Per-Refactor Verification

After each refactor:

1. **Full test suite** — All ~11,400 tests must pass with zero failures.
2. **E2E output diff** — The CLI output for the baseline commands must be identical.
3. **Import verification** — The new backward-compatibility tests confirm all import paths work.
4. **Architecture tests** — `python -m pytest tests/test_architecture.py` must pass (layer purity).

### Post-All-Refactors Verification

After all 5 refactors are complete:

1. Full test suite (final pass).
2. E2E output diff (final pass).
3. **New-feature simulation** — Create a minimal feature stub in the new structure to verify that adding a feature requires only new files (no edits to shared files).
4. Verify `config.yaml` alone still works (no `config.d/` required).

---

## Rollback Plan

Each refactor is independently reversible:

| Refactor | Rollback Method |
|----------|----------------|
| R1 (Exceptions) | Delete `domain/exceptions/` directory, restore `domain/exceptions.py` from git |
| R2 (EventType) | Delete `domain/events/` directory, restore `EventType` enum in `models.py` from git |
| R3 (Config Mixins) | Delete `infrastructure/config/` directory, restore `infrastructure/config.py` from git |
| R4 (Feature Registry) | Delete `infrastructure/features/` directory, restore `__main__.py` from git |
| R5 (YAML Split) | Delete `config.d/` directory, restore `config.yaml` from git |

Each refactor should be committed as a separate commit so that `git revert` can undo any single refactor without affecting the others.

**Commit order:**
1. R1 (Exceptions) — one commit
2. R2 (EventType) — one commit
3. R5 (YAML Split) — one commit
4. R3 (Config Mixins) — one commit
5. R4a (Feature Registry Phase 1) — one commit
6. R4b (Feature Registry Phase 2) — one commit
7. R4c (Feature Registry Phase 3) — one commit

---

## Summary

| Refactor | File | Before | After | Risk | Phase |
|----------|------|--------|-------|------|-------|
| R1: Exception Sharding | `domain/exceptions.py` | 18,105 lines, 1 file | ~95 files in `exceptions/` | LOW | 1 (parallel) |
| R2: EventType Registry | `domain/models.py` | 822-member Enum | Registry + ~60 registration files | MEDIUM | 1 (parallel) |
| R3: Config Mixins | `infrastructure/config.py` | 7,665 lines, 1 class | Base + ~40 mixin files | LOW | 2 (after R5) |
| R4: Feature Registry | `__main__.py` | 12,646 lines | ~500-line orchestrator + ~60 descriptors | HIGH | 3 (after R1-R3) |
| R5: YAML Split | `config.yaml` | 2,247 lines | ~80-line base + ~84 overlay files | LOW | 1 (parallel) |

**Total net new lines:** ~2,400 (mostly boilerplate: `__init__.py` re-exports, `__all__` lists, test files)
**Total moved lines:** ~40,600
**Expected test changes:** Zero (for existing tests)
**New test files:** 5 (~440 lines total)

After Round 17.5: adding a new feature requires creating new files in `domain/exceptions/`, `domain/events/`, `infrastructure/config/_mixins/`, `infrastructure/features/`, and `config.d/`. Zero edits to shared files. TeraSwarm-ready.

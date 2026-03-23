# PLAN: Configuration Management Page

## 1. Overview

The Configuration Management page (`/configuration`) provides a centralized governance interface for all tunable parameters of the Enterprise FizzBuzz Platform. Operators can inspect, modify, and stage configuration changes across every subsystem — from evaluation strategy selection to blockchain mining difficulty — through a single pane of glass with full change-tracking and diff review before any modification is applied.

The page also serves as the authoritative interface for the Feature Flag subsystem, exposing rollout percentages, lifecycle state management, and per-flag toggle controls with audit-grade visibility.

---

## 2. New Types (`frontend/src/lib/data-providers/types.ts`)

Append the following interfaces after the existing `AuditEntry` interface:

```typescript
// ---------------------------------------------------------------------------
// Configuration Management types
// ---------------------------------------------------------------------------

/** Top-level category for grouping related configuration items. */
export type ConfigCategory =
  | "evaluation"
  | "cache"
  | "compliance"
  | "chaos"
  | "blockchain"
  | "ml"
  | "feature_flags"
  | "rate_limiting"
  | "sla"
  | "service_mesh"
  | "observability"
  | "persistence";

/** The primitive type of a configuration value, determining the input widget rendered. */
export type ConfigValueType = "string" | "number" | "boolean" | "enum";

/** A single configurable parameter of the platform. */
export interface ConfigItem {
  /** Stable machine identifier (e.g., "cache.eviction_policy"). */
  id: string;
  /** Human-readable display name. */
  name: string;
  /** Current effective value (always serialized as string). */
  value: string;
  /** Data type governing the editor widget. */
  type: ConfigValueType;
  /** For enum types, the set of allowed values. */
  enumValues?: string[];
  /** For number types, optional minimum value. */
  min?: number;
  /** For number types, optional maximum value. */
  max?: number;
  /** Short description of what this parameter controls. */
  description: string;
  /** Factory default value. */
  defaultValue: string;
  /** Category this item belongs to. */
  category: ConfigCategory;
  /** Whether this parameter requires a platform restart to take effect. */
  requiresRestart: boolean;
  /** ISO 8601 timestamp of the last modification, if ever changed from default. */
  lastModifiedAt?: string;
  /** Principal who last modified this value. */
  lastModifiedBy?: string;
}

/** Lifecycle state of a feature flag. */
export type FeatureFlagLifecycle = "development" | "testing" | "canary" | "ga" | "deprecated";

/** A feature flag governing progressive rollout of platform capabilities. */
export interface FeatureFlag {
  /** Unique flag identifier (e.g., "wuzz_rule_experimental"). */
  id: string;
  /** Human-readable flag name. */
  name: string;
  /** Extended description of the capability gated by this flag. */
  description: string;
  /** Whether the flag is currently enabled. */
  enabled: boolean;
  /** Percentage of evaluations receiving the flagged behavior (0-100). */
  rolloutPercentage: number;
  /** Current lifecycle state. */
  lifecycle: FeatureFlagLifecycle;
  /** ISO 8601 timestamp of the last state change. */
  lastToggledAt: string;
  /** Principal who last toggled this flag. */
  lastToggledBy: string;
}

/** Result of a configuration update operation. */
export interface ConfigUpdateResult {
  /** Whether the update was accepted. */
  success: boolean;
  /** Reason for rejection, if applicable. */
  error?: string;
  /** The updated configuration item. */
  item?: ConfigItem;
}

/** Result of a feature flag toggle operation. */
export interface FeatureFlagToggleResult {
  /** Whether the toggle was accepted. */
  success: boolean;
  /** Reason for rejection, if applicable. */
  error?: string;
  /** The updated feature flag. */
  flag?: FeatureFlag;
}
```

---

## 3. DataProvider Extensions (`frontend/src/lib/data-providers/provider.ts`)

Add these four methods to the `IDataProvider` interface:

```typescript
/**
 * Retrieve all platform configuration items, optionally filtered by category.
 * Returns items sorted by category, then by name.
 */
getConfiguration(category?: ConfigCategory): Promise<ConfigItem[]>;

/**
 * Submit a configuration change. The change is validated server-side
 * against type constraints and business rules before acceptance.
 */
updateConfigItem(itemId: string, newValue: string): Promise<ConfigUpdateResult>;

/**
 * Retrieve all registered feature flags with current state and rollout
 * configuration. Returns flags sorted by lifecycle stage, then by name.
 */
getFeatureFlags(): Promise<FeatureFlag[]>;

/**
 * Toggle a feature flag's enabled state or update its rollout percentage.
 * Returns the updated flag state after server-side validation.
 */
toggleFeatureFlag(flagId: string, enabled: boolean, rolloutPercentage?: number): Promise<FeatureFlagToggleResult>;
```

---

## 4. SimulationProvider Implementation (`frontend/src/lib/data-providers/simulation-provider.ts`)

### 4.1 Configuration Items (~45 items)

Generate configuration items spanning all categories, derived from the actual CLI flags in `__main__.py`:

**Evaluation (5 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `evaluation.strategy` | Evaluation Strategy | enum (`standard`, `chain_of_responsibility`, `parallel_async`, `machine_learning`) | `standard` | Primary rule evaluation strategy |
| `evaluation.range_start` | Default Range Start | number | `1` | Default start of evaluation range |
| `evaluation.range_end` | Default Range End | number | `100` | Default end of evaluation range |
| `evaluation.output_format` | Output Format | enum (`plain`, `json`, `xml`, `csv`) | `plain` | Serialization format for evaluation results |
| `evaluation.locale` | Locale | enum (`en`, `de`, `fr`, `ja`, `tlh`, `sjn`, `qya`) | `en` | Internationalized output locale |

**Cache (5 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `cache.enabled` | Cache Enabled | boolean | `false` | Enable MESI-coherent caching layer |
| `cache.eviction_policy` | Eviction Policy | enum (`lru`, `lfu`, `fifo`, `dramatic_random`) | `lru` | Cache eviction algorithm |
| `cache.max_entries` | Max Cache Entries | number | `1024` | Maximum entries before eviction triggers |
| `cache.warm_on_start` | Warm on Start | boolean | `false` | Pre-populate cache during boot sequence |
| `cache.ttl_seconds` | TTL (seconds) | number | `3600` | Time-to-live for cached evaluation results |

**Compliance (5 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `compliance.enabled` | Compliance Framework Enabled | boolean | `false` | Enable SOX/GDPR/HIPAA compliance subsystem |
| `compliance.sox_audit` | SOX Audit Trail | boolean | `true` | Emit segregation-of-duties audit entries |
| `compliance.gdpr_erasure_enabled` | GDPR Right-to-Erasure | boolean | `true` | Honor GDPR Art. 17 erasure requests |
| `compliance.hipaa_encryption` | HIPAA PHI Encryption | boolean | `true` | Encrypt PHI data at rest and in transit |
| `compliance.audit_retention_days` | Audit Retention (days) | number | `2555` | Minimum retention period for compliance records |

**Chaos Engineering (5 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `chaos.enabled` | Chaos Engineering Enabled | boolean | `false` | Enable fault injection subsystem |
| `chaos.severity_level` | Severity Level | enum (`1`, `2`, `3`, `4`, `5`) | `1` | Chaos fault severity (1=gentle, 5=apocalypse) |
| `chaos.gameday_scenario` | Game Day Scenario | enum (`modulo_meltdown`, `confidence_crisis`, `slow_burn`, `total_chaos`) | `total_chaos` | Default Game Day scenario |
| `chaos.auto_postmortem` | Auto Post-Mortem | boolean | `true` | Automatically generate incident reports |
| `chaos.blast_radius_percent` | Blast Radius (%) | number | `25` | Percentage of evaluations subject to fault injection |

**Blockchain (4 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `blockchain.enabled` | Blockchain Ledger Enabled | boolean | `false` | Enable immutable audit ledger |
| `blockchain.mining_difficulty` | Mining Difficulty | number | `2` | Proof-of-work hash prefix zeros required |
| `blockchain.consensus_algorithm` | Consensus Algorithm | enum (`pow`, `pos`, `poa`) | `pow` | Block validation consensus mechanism |
| `blockchain.block_size_limit` | Block Size Limit | number | `100` | Maximum evaluation results per block |

**ML (5 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `ml.enabled` | ML Engine Enabled | boolean | `false` | Enable neural network evaluation strategy |
| `ml.learning_rate` | Learning Rate | number | `0.001` | Gradient descent step size |
| `ml.hidden_layers` | Hidden Layer Count | number | `3` | Neural network depth |
| `ml.epochs` | Training Epochs | number | `100` | Complete passes through training data |
| `ml.confidence_threshold` | Confidence Threshold | number | `0.85` | Minimum prediction confidence for acceptance |

**Rate Limiting (5 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `rate_limiting.enabled` | Rate Limiting Enabled | boolean | `false` | Enable evaluation rate governance |
| `rate_limiting.rpm` | Max Evaluations/min | number | `1000` | Requests-per-minute ceiling |
| `rate_limiting.algorithm` | Algorithm | enum (`token_bucket`, `sliding_window`, `fixed_window`) | `token_bucket` | Rate limiting algorithm |
| `rate_limiting.burst_multiplier` | Burst Multiplier | number | `2` | Allowed burst factor over sustained rate |
| `rate_limiting.quota_enabled` | Quota Tracking | boolean | `true` | Enable per-tenant quota accounting |

**SLA (5 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `sla.enabled` | SLA Monitoring Enabled | boolean | `false` | Enable SLO/SLA monitoring subsystem |
| `sla.availability_target` | Availability Target (%) | number | `99.95` | Target availability percentage |
| `sla.latency_p99_target_ms` | P99 Latency Target (ms) | number | `50` | 99th-percentile latency SLO threshold |
| `sla.error_budget_window_days` | Error Budget Window (days) | number | `30` | Rolling window for error budget calculation |
| `sla.auto_escalation` | Auto Escalation | boolean | `true` | Automatically page on-call for SLO breach |

**Service Mesh (3 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `service_mesh.enabled` | Service Mesh Enabled | boolean | `false` | Decompose FizzBuzz into 7 microservices |
| `service_mesh.latency_injection` | Latency Injection | boolean | `false` | Inject simulated network latency between services |
| `service_mesh.packet_loss` | Packet Loss Simulation | boolean | `false` | Simulate packet loss between mesh services |

**Observability (4 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `observability.tracing` | Distributed Tracing | boolean | `false` | Enable OpenTelemetry distributed tracing |
| `observability.metrics` | Prometheus Metrics | boolean | `false` | Enable Prometheus-style metrics collection |
| `observability.webhooks` | Webhook Notifications | boolean | `false` | Enable event-driven webhook telemetry |
| `observability.hot_reload` | Config Hot-Reload | boolean | `false` | Enable Raft-consensus configuration hot-reload |

**Persistence (4 items)**
| ID | Name | Type | Default | Description |
|---|---|---|---|---|
| `persistence.backend` | Storage Backend | enum (`in_memory`, `sqlite`, `filesystem`) | `in_memory` | Result persistence repository backend |
| `persistence.db_path` | SQLite Database Path | string | `fizzbuzz.db` | Path to SQLite database file |
| `persistence.results_dir` | Results Directory | string | `./results` | Filesystem persistence output directory |
| `persistence.event_sourcing` | Event Sourcing | boolean | `false` | Enable CQRS event-sourced persistence |

### 4.2 Feature Flags (10 items)

| ID | Name | Enabled | Rollout % | Lifecycle | Description |
|---|---|---|---|---|---|
| `wuzz_rule_experimental` | Wuzz Rule (Experimental) | false | 0 | development | Adds "Wuzz" output for numbers divisible by 7 |
| `quantum_strategy` | Quantum Evaluation Strategy | true | 15 | canary | Route eligible evaluations through quantum circuit simulator |
| `ml_confidence_override` | ML Confidence Override | true | 100 | ga | Allow ML strategy to override low-confidence predictions with fallback |
| `blockchain_async_mining` | Async Block Mining | false | 0 | testing | Mine blocks asynchronously to reduce evaluation latency |
| `cache_predictive_warm` | Predictive Cache Warming | true | 50 | canary | Use access pattern analysis to pre-warm cache entries |
| `gdpr_enhanced_erasure` | Enhanced GDPR Erasure | true | 100 | ga | Extended erasure covering backup and replica stores |
| `chaos_adaptive_severity` | Adaptive Chaos Severity | false | 0 | development | Dynamically adjust chaos severity based on system health |
| `federated_aggregation` | Federated Model Aggregation | true | 25 | testing | Enable FedAvg aggregation across distributed training nodes |
| `genetic_crossover_v2` | Genetic Algorithm Crossover v2 | false | 0 | deprecated | Replaced by uniform crossover in v3 engine |
| `dark_launch_fizzdap` | FizzDAP Dark Launch | true | 10 | canary | Shadow-route evaluations to FizzDAP debug adapter protocol |

---

## 5. Page Layout

### 5.1 Header

- Title: "Configuration Management"
- Subtitle: "Centralized parameter governance for all platform subsystems. Changes are staged locally, reviewed in the pending changes panel, and applied atomically."

### 5.2 Category Tabs

Horizontal tab bar across the top with one tab per `ConfigCategory` plus Feature Flags:

`Evaluation` | `Cache` | `Compliance` | `Chaos Engineering` | `Blockchain` | `ML` | `Rate Limiting` | `SLA` | `Service Mesh` | `Observability` | `Persistence` | `Feature Flags`

Active tab highlighted with `fizzbuzz-400` underline per existing design tokens.

### 5.3 Search Bar

Below the tabs, a full-width search input: "Search configuration items..." that filters visible items across all categories (or within the active category tab). Matches against `name`, `id`, and `description` fields.

### 5.4 Configuration Items Form (for non-Feature-Flag tabs)

Each config item renders as a row in a form card:

```
[Config Item Name]                    [Input Widget]  [Restart badge if applicable]
  config.item.id — Description text
  Default: <defaultValue>  |  Last modified: 3h ago by admin
```

Input widgets by type:
- `boolean` — toggle switch (panel-800 track, fizz-400 thumb when on)
- `enum` — dropdown select (same styling as compliance page selects)
- `number` — number input with min/max constraints, spinner arrows
- `string` — text input

When a value differs from its currently-saved state, the row gets a left border highlight (`amber-400`) to indicate a pending change.

### 5.5 Feature Flags Tab

Renders as a card grid (2 columns on xl, 1 on mobile), each card containing:

```
+--------------------------------------------------+
| [Flag Name]                    [Toggle Switch]    |
| flag.id                                           |
| Description text here...                          |
|                                                   |
| Rollout: [====------] 25%    [Slider]             |
| Lifecycle: [canary badge]                         |
| Last toggled: 2h ago by platform-admin            |
+--------------------------------------------------+
```

Lifecycle badges use existing Badge component:
- `development` — info (blue)
- `testing` — warning (amber)
- `canary` — warning (amber)
- `ga` — success (green)
- `deprecated` — error (red)

### 5.6 Pending Changes Panel

A sticky panel at the bottom of the page (or a collapsible drawer) that appears when any config item or feature flag has been modified from its saved state:

```
+---------------------------------------------------------------+
| Pending Changes (3)                          [Apply] [Discard] |
|---------------------------------------------------------------|
| cache.eviction_policy    lru → lfu                             |
| chaos.severity_level     1 → 3                                 |
| quantum_strategy (flag)  enabled: true → false                 |
+---------------------------------------------------------------+
```

Shows a diff table with columns: Parameter, Before, After. Values use monospace font. The "Before" column uses `red-400/red-950` styling, "After" uses `fizz-400/fizz-950` — matching the compliance page's severity color pattern.

**Apply** button: calls `updateConfigItem()` / `toggleFeatureFlag()` for each pending change sequentially, clears the pending set on success, shows toast on failure.

**Discard** button: resets all pending changes to their saved values.

### 5.7 Auto-Refresh

Configuration state refreshes every 30 seconds (longer interval than monitoring pages since config changes less frequently). Pending local changes are preserved across refreshes.

---

## 6. Files to Create/Modify

### New Files

| File | Purpose |
|---|---|
| `frontend/src/app/(dashboard)/configuration/page.tsx` | Main Configuration Management page component |

### Modified Files

| File | Change |
|---|---|
| `frontend/src/lib/data-providers/types.ts` | Add `ConfigCategory`, `ConfigValueType`, `ConfigItem`, `FeatureFlagLifecycle`, `FeatureFlag`, `ConfigUpdateResult`, `FeatureFlagToggleResult` types |
| `frontend/src/lib/data-providers/provider.ts` | Add `getConfiguration()`, `updateConfigItem()`, `getFeatureFlags()`, `toggleFeatureFlag()` to `IDataProvider` |
| `frontend/src/lib/data-providers/simulation-provider.ts` | Implement all four new methods with simulated data generation |
| `frontend/src/lib/data-providers/index.ts` | Re-export new types |
| `frontend/src/app/layout.tsx` | Wire the "Configuration" sidebar item as an `<a href="/configuration">` link |

---

## 7. Implementation Notes

- The page component follows the same `"use client"` / `useDataProvider()` / `useCallback` + `useEffect` pattern established by the Compliance Center page.
- Pending changes are tracked in React state via a `Map<string, { before: string; after: string }>` — they are not persisted to any backend staging area.
- The simulation provider's `updateConfigItem()` mutates an in-memory config array and returns success. `toggleFeatureFlag()` similarly mutates in-memory flag state.
- All form inputs use the same design tokens as existing pages: `border-panel-600 bg-panel-800 text-panel-200` for inputs, `text-panel-500` for labels.
- The search filter operates client-side against the already-fetched configuration array.
- The `requiresRestart` badge on applicable items uses the existing `Badge` component with `variant="warning"` and text "Restart Required".

# Enterprise FizzBuzz Platform: Operational Runbook

**Audience:** On-call engineers, FizzBuzz Reliability Engineering team
**Owner:** Bob McFizzington, Senior Principal Staff FizzBuzz Reliability Engineer II
**Contact:** bob.mcfizzington@enterprise.example.com | +1-555-FIZZBUZZ
**Last Updated:** 2026-03-21
**Review Cadence:** Weekly (during Bob's 1:1 with himself)

---

## Table of Contents

1. [Alert Triage](#1-alert-triage)
2. [Circuit Breaker Recovery](#2-circuit-breaker-recovery)
3. [Chaos Incident Response](#3-chaos-incident-response)
4. [SLA Dashboard Interpretation](#4-sla-dashboard-interpretation)
5. [Cache Diagnostics](#5-cache-diagnostics)
6. [Escalation Procedure](#6-escalation-procedure)

---

## 1. Alert Triage

### 1.1 Alert Severity Definitions

The platform uses PagerDuty-style alert severities defined in `AlertSeverity` (`enterprise_fizzbuzz/infrastructure/sla.py`). Each severity maps to a specific notification channel, response time expectation, and escalation action via `EscalationPolicy`.

| Severity | Label    | Description | Channel | Response Time |
|----------|----------|-------------|---------|---------------|
| **P1**   | CRITICAL | FizzBuzz pipeline is DOWN. SLA breach imminent. | Phone call + SMS + Email + Slack + Carrier pigeon | 5 minutes |
| **P2**   | HIGH     | SLO violations accumulating. Error budget burning fast. | Push notification + Email + Slack | 15 minutes |
| **P3**   | MEDIUM   | Error budget burn rate elevated. Monitor closely. | Email + Slack | 1 hour |
| **P4**   | LOW      | Minor SLO drift. Include in weekly reliability report. | Email digest | Next business day |

### 1.2 SLO Violation Alert Triggers

The `SLAMonitor._check_slo()` method determines alert severity based on the gap between the current compliance level and the SLO target:

| Compliance Gap     | Triggered Severity |
|--------------------|--------------------|
| Gap > 5.0%         | P1 (CRITICAL)      |
| Gap > 1.0%         | P2 (HIGH)          |
| Gap > 0.1%         | P3 (MEDIUM)        |
| Gap <= 0.1%        | P4 (LOW)           |

A P1 is also fired immediately when any error budget is fully exhausted (`ErrorBudget.is_exhausted()` returns `True`), regardless of the compliance gap.

A P3 is fired when the error budget burn rate exceeds the configured threshold (default: 2.0x the sustainable rate), as checked by `SLAMonitor._check_slo()`.

### 1.3 Alert Lifecycle

Alerts follow three states defined in `AlertStatus`:

1. **FIRING** -- The alert is active and demanding attention.
2. **ACKNOWLEDGED** -- Someone (you) has acknowledged the alert, promising to look at it after coffee.
3. **RESOLVED** -- The issue has been fixed, or the SLO has recovered, or everyone decided to pretend it never happened.

The `AlertManager` enforces a cooldown period (default: 60 seconds) per SLO to prevent alert storms. If you are receiving the same alert repeatedly, the cooldown has expired between firings, which means the underlying condition has persisted for at least 60 seconds.

### 1.4 Triage Decision Tree

When you receive an alert, follow this decision tree:

```
ALERT RECEIVED
    |
    v
Is this a LATENCY SLO violation?
    |
    +-- YES --> Is the Chaos Monkey active? (check --chaos flag / ChaosMonkey.get_instance())
    |               |
    |               +-- YES --> Check FaultSeverity level.
    |               |              Level 1-2: Chaos experiment running normally. Monitor.
    |               |              Level 3:   Dashboards will light up. Verify this is expected.
    |               |              Level 4-5: Verify this is a planned Game Day.
    |               |                         If not planned, disable chaos immediately.
    |               |              See Section 3: Chaos Incident Response.
    |               |
    |               +-- NO --> Check circuit breaker state.
    |                              |
    |                              +-- OPEN --> Circuit has tripped. See Section 2.
    |                              |
    |                              +-- HALF_OPEN --> Recovery probe in progress.
    |                              |                 Do not interfere. Monitor.
    |                              |
    |                              +-- CLOSED --> Check ML confidence scores.
    |                                                |
    |                                                +-- Avg confidence < 0.7 -->
    |                                                |     ML degradation detected.
    |                                                |     The circuit breaker's
    |                                                |     ml_confidence_threshold
    |                                                |     (default: 0.7) is being
    |                                                |     approached. If using ML
    |                                                |     strategy, consider fallback
    |                                                |     to StandardStrategy.
    |                                                |
    |                                                +-- Confidence >= 0.7 -->
    |                                                      Genuine latency issue.
    |                                                      Escalate to yourself.
    |                                                      See Section 6.
    |
    +-- NO --> Is this an ACCURACY SLO violation?
    |               |
    |               +-- YES --> Check if chaos is active (result corruption or
    |               |           rule engine failure injector). If yes, see Section 3.
    |               |           If no, this is a real accuracy failure. The pipeline
    |               |           produced an incorrect FizzBuzz result. The SLAMonitor
    |               |           verifies accuracy by independently computing
    |               |           n % 3 and n % 5 via _verify_accuracy().
    |               |           Escalate to yourself immediately (P1).
    |               |
    |               +-- NO --> AVAILABILITY SLO violation.
    |                           Check for unhandled exceptions in the pipeline.
    |                           Check circuit breaker rejections (CircuitOpenError).
    |                           Check for ChaosInducedFizzBuzzError in logs.
    |                           If none of the above: escalate to yourself.
```

---

## 2. Circuit Breaker Recovery

The circuit breaker is implemented in `CircuitBreaker` (`enterprise_fizzbuzz/infrastructure/circuit_breaker.py`). It protects the FizzBuzz evaluation pipeline from cascading failures.

### 2.1 Circuit Breaker States

The `CircuitState` enum defines three states:

| State       | Indicator on Dashboard             | Meaning |
|-------------|-------------------------------------|---------|
| **CLOSED**    | `[  CLOSED  ]  All systems nominal` | FizzBuzz requests flow freely. This is the desired state. |
| **OPEN**      | `[   OPEN   ]  REJECTING REQUESTS`  | Circuit has tripped. All requests are rejected immediately with `CircuitOpenError`. No FizzBuzz evaluations are being processed. |
| **HALF_OPEN** | `[HALF_OPEN ]  Probe phase active`  | Recovery in progress. A limited number of probe requests (default: 3, configured by `half_open_max_calls`) are allowed through to test if the downstream pipeline has recovered. |

### 2.2 State Transitions

```
CLOSED ----[failure_count >= failure_threshold (5)]--> OPEN
OPEN ------[backoff timeout expires]------------------> HALF_OPEN
HALF_OPEN -[success_count >= success_threshold (3)]---> CLOSED
HALF_OPEN -[any single failure]-----------------------> OPEN (backoff attempt incremented)
```

Key parameters (defaults from `CircuitBreaker.__init__`):

| Parameter                 | Default | Description |
|---------------------------|---------|-------------|
| `failure_threshold`       | 5       | Consecutive failures before the circuit trips. |
| `success_threshold`       | 3       | Consecutive successes in HALF_OPEN before closing. |
| `timeout_ms`              | 30000   | Base timeout for the circuit breaker. |
| `sliding_window_size`     | 10      | Number of recent evaluations tracked. |
| `half_open_max_calls`     | 3       | Maximum concurrent probe calls in HALF_OPEN. |
| `ml_confidence_threshold` | 0.7     | ML confidence below this triggers a degradation warning. |
| `call_timeout_ms`         | 5000    | Individual call timeout in milliseconds. |

Exponential backoff uses `ExponentialBackoffCalculator` with defaults:
- Base delay: 1000ms
- Multiplier: 2.0x per attempt
- Maximum delay: 60000ms (60 seconds)

The backoff delay for attempt N is: `min(1000 * 2^N, 60000)` ms.

### 2.3 Reading the Circuit Breaker Dashboard

The `CircuitBreakerDashboard.render()` method produces the following display. Here is how to interpret each field:

| Dashboard Field     | Source | What to Look For |
|---------------------|--------|------------------|
| **State**           | `CircuitBreaker.state` | If OPEN, all evaluations are being rejected. |
| **Total Calls**     | `metrics.total_calls` | Total evaluations attempted through this circuit. |
| **Successes**       | `metrics.total_successes` | Successful evaluations. |
| **Failures**        | `metrics.total_failures` | Failed evaluations. |
| **Rejections**      | `metrics.total_rejections` | Calls rejected because the circuit was OPEN. |
| **Trip Count**      | `metrics.trip_count` | How many times the circuit has tripped (CLOSED -> OPEN). Multiple trips indicate a recurring issue. |
| **Failure Rate**    | `window.failure_rate` | Failure rate within the sliding window (0% to 100%). |
| **Avg ML Conf**     | `window.avg_confidence` | Average ML confidence score. Below 0.7 indicates degradation. N/A if ML strategy is not in use. |
| **Backoff Attempt** | `metrics.current_backoff_attempt` | Current exponential backoff attempt. Higher values mean longer wait times before the next HALF_OPEN probe. |
| **Sliding Window**  | Visual: `+` = success, `X` = failure | A visual history of recent evaluations. A run of `X X X X X` preceding a state change to OPEN tells you the failure threshold was crossed. |

### 2.4 Manual Reset

If the circuit breaker is stuck in OPEN and you have determined the root cause is resolved, you can reset it programmatically:

```python
from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreakerRegistry

registry = CircuitBreakerRegistry.get_instance()
cb = registry.get("FizzBuzzPipelineCircuit")
if cb is not None:
    cb.reset()
```

`CircuitBreaker.reset()` transitions the circuit to CLOSED, clears all metrics and the sliding window, and resets the backoff attempt counter to zero. This should only be done when you are confident the underlying issue is resolved. Resetting a circuit while the root cause persists will result in another trip within `failure_threshold` evaluations.

### 2.5 ML Confidence Degradation

When the ML strategy is active, the circuit breaker monitors confidence scores via `CircuitBreaker._extract_ml_confidence()`. If the minimum confidence across all rules in an evaluation falls below `ml_confidence_threshold` (0.7), a warning is logged:

```
Circuit 'FizzBuzzPipelineCircuit': ML confidence 0.3200 below threshold 0.7000
```

This does not directly trip the circuit, but is a leading indicator. The `MLStrategyAdapter` also tracks ambiguity when any rule's confidence falls within the ambiguity margin (default: 0.1) of the decision threshold (default: 0.5), i.e., between 0.4 and 0.6. These events are published as `CLASSIFICATION_AMBIGUITY` on the event bus.

If you see confidence warnings in conjunction with accuracy SLO violations, the ML model may be producing incorrect results with low conviction. Consider switching to `StandardStrategy` until the model stabilizes.

---

## 3. Chaos Incident Response

The Chaos Monkey (`enterprise_fizzbuzz/infrastructure/chaos.py`) deliberately injects faults into the pipeline. This section covers how to identify, assess, and respond to chaos-related incidents.

### 3.1 Identifying Active Chaos Experiments

The Chaos Monkey is a singleton. If it was initialized (via `--chaos` flag or `ChaosMonkey.initialize()`), it is active. Check:

1. **Logs:** Look for `CHAOS MONKEY [FAULT_TYPE]` warnings in the log output.
2. **Context metadata:** Evaluations affected by chaos carry metadata keys prefixed with `chaos_` (e.g., `chaos_corrupted`, `chaos_latency_ms`, `chaos_confidence_manipulated`, `chaos_rule_engine_failed`).
3. **Summary:** Call `ChaosMonkey.get_instance().get_summary()` to see total injections, injection rate, and armed fault types.

### 3.2 Fault Types and Their Effects

The five fault types are defined in `FaultType`:

| Fault Type                  | Injector Class                    | Effect | Phase |
|-----------------------------|-----------------------------------|--------|-------|
| `RESULT_CORRUPTION`         | `ResultCorruptionInjector`        | Replaces correct outputs with wrong values ("Fizz" -> "Buzz", etc.) | Post-evaluation |
| `LATENCY_INJECTION`         | `LatencyInjector`                 | Adds artificial delays (10ms to 500ms base, scaled by severity) | Pre-evaluation |
| `EXCEPTION_INJECTION`       | `ExceptionInjector`               | Throws `ChaosInducedFizzBuzzError` with creative error messages | Pre-evaluation |
| `RULE_ENGINE_FAILURE`       | `RuleEngineFailureInjector`       | Clears matched rules, reverting output to plain number | Post-evaluation |
| `CONFIDENCE_MANIPULATION`   | `ConfidenceManipulationInjector`  | Reduces ML confidence scores to dangerously low levels | Post-evaluation |

The `ChaosMiddleware` runs at priority 3 (inside the circuit breaker at priority -1), so chaos-induced failures are detected by the circuit breaker as genuine downstream failures. This is by design.

### 3.3 Severity Levels

`FaultSeverity` maps to injection probabilities:

| Level | Label           | Injection Probability | Operational Impact |
|-------|-----------------|----------------------|-------------------|
| 1     | Gentle Breeze   | 5%                   | Barely noticeable. Most evaluations unaffected. |
| 2     | Stiff Wind      | 15%                  | Systems start to sweat. Occasional SLO violations. |
| 3     | Proper Storm    | 30%                  | Dashboards light up. Circuit breaker may trip. |
| 4     | Hurricane       | 50%                  | Engineers get paged. Error budgets burning fast. |
| 5     | Apocalypse      | 80%                  | Update your resume. Nearly every evaluation impacted. |

### 3.4 Game Day Scenarios

The `GameDayRunner` provides four pre-built multi-phase scenarios:

| Scenario             | Description | Phases |
|----------------------|-------------|--------|
| `modulo_meltdown`    | Progressive rule engine failure escalating to total arithmetic collapse. | 3 phases: L1 -> L3 -> L5 |
| `confidence_crisis`  | ML confidence scores plummet, triggering circuit breaker degradation detection. | 2 phases: L2 -> L4 |
| `slow_burn`          | Progressive latency injection simulating downstream load increase. | 3 phases: L1 -> L3 -> L5 |
| `total_chaos`        | All five fault types at Level 5 simultaneously. Not recommended for systems with feelings. | 1 phase: L5, all faults |

If you receive alerts during a Game Day, verify the scenario name and phase before escalating. Expected behavior during a `total_chaos` Game Day is not an incident.

### 3.5 Reading the Post-Mortem Report

After a chaos experiment, `PostMortemGenerator.generate()` produces an incident report with the following sections:

1. **Header:** Incident title (severity-appropriate), severity level, date, and game day name if applicable. Incident titles range from "Minor FizzBuzz Disturbance (Nobody Noticed)" at Level 1 to "Catastrophic FizzBuzz Collapse (CEO Notified)" at Level 5.

2. **Executive Summary:** Total evaluations monitored, total faults injected, injection rate, and number of armed fault types.

3. **Fault Type Breakdown:** Bar chart showing the count of each fault type injected.

4. **Incident Timeline:** Chronological list of chaos events (capped at 20 entries), including timestamp, fault type, target number, and description.

5. **Impact Assessment:** Per-fault-type narrative describing the operational impact.

6. **Root Cause Analysis:** Randomly selected root causes. These are always some variation of "the Chaos Monkey was doing exactly what it was told to do."

7. **Action Items:** Randomly selected action items. These are intentionally aspirational and should not be treated as actual work items. Do not create JIRA tickets for them.

---

## 4. SLA Dashboard Interpretation

The `SLADashboard.render()` method (`enterprise_fizzbuzz/infrastructure/sla.py`) produces the SLA Monitoring Dashboard. This section explains each panel.

### 4.1 SLO Compliance Panel

Displays each SLO's current compliance versus its target:

```
  latency        [LATENCY     ]   99.8000% / 99.9000%  [VIOLATION]
  accuracy       [ACCURACY    ]  100.0000% / 99.9990%  [OK]
  availability   [AVAILABILITY]   99.9500% / 99.9000%  [OK]
```

The three SLO types, defined in `SLOType`:

| SLO Type       | What It Measures | How It Is Verified |
|----------------|------------------|--------------------|
| **LATENCY**    | Percentage of evaluations completing within the threshold (e.g., 100ms). | `SLOMetricCollector.get_latency_compliance()` counts evaluations under `threshold_ms`. |
| **ACCURACY**   | Percentage of evaluations producing the correct FizzBuzz result. | `SLAMonitor._verify_accuracy()` independently computes `n % 3` and `n % 5` and compares against the pipeline output. |
| **AVAILABILITY** | Percentage of evaluations that completed without throwing an exception. | `SLOMetricCollector.get_availability_compliance()` tracks `success=True/False` for each evaluation. |

A status of `[VIOLATION]` means current compliance is below the SLO target.

### 4.2 Latency Percentiles

```
  Total Evaluations : 1500
  P50 Latency       : 0.0234 ms
  P99 Latency       : 1.4521 ms
```

- **P50** (median): Half of all evaluations complete in less than this time.
- **P99**: 99% of evaluations complete in less than this time. If this value approaches the SLO latency threshold, you are at risk of a latency SLO violation.

Both are computed by `SLOMetricCollector._percentile_ms()` from nanosecond-precision measurements.

### 4.3 Error Budget Panel

```
  latency        [---.................] 15.0% left  burn: 5.7x
  accuracy       [....................] 100.0% left burn: 0.0x
```

**Error budget formula:** `total_budget = (1 - target) * total_events`

For example, with a 99.9% SLO target over 1000 evaluations, the error budget is `(1 - 0.999) * 1000 = 1.0` allowed bad events.

| Budget Bar Symbol | Consumption Level |
|-------------------|-------------------|
| `.` (dots)        | Unconsumed budget |
| `-` (dashes)      | Consumed, under 50% |
| `=` (equals)      | Consumed, 50-80% |
| `#` (hashes)      | Consumed, 80-100% |
| `X` (crosses)     | Budget fully exhausted |

**Burn rate** (`ErrorBudget.get_burn_rate()`): The rate at which the error budget is being consumed relative to the ideal consumption rate.

| Burn Rate | Interpretation |
|-----------|----------------|
| 0.0x      | No budget consumption. Everything is working. |
| 1.0x      | Budget is being consumed at exactly the sustainable rate. The budget will be exhausted precisely at the end of the window. |
| 2.0x      | Consuming at 2x the sustainable rate. A P3 alert will fire (threshold default: 2.0x). |
| 5.0x+     | Budget will be exhausted well before the window ends. Investigate immediately. |
| 10.0x+    | Update your resume. |

**Projected exhaustion:** `ErrorBudget.get_projected_exhaustion_evaluations()` estimates how many more evaluations remain before the budget is fully consumed. If this number is dropping rapidly, the burn rate is accelerating.

### 4.4 Active Alerts Panel

Displays currently firing and acknowledged alerts, grouped by count:

```
  Firing: 2  Acknowledged: 1  Resolved: 5
  [CRITICAL] 14:32:07 latency: SLO 'latency' compliance...
  [MEDIUM  ] 14:32:07 latency_burn_rate: Error budget f...
```

Each alert shows severity, timestamp, SLO name, and a truncated message. If there are more than 5 active alerts, the display truncates with a count of remaining alerts.

### 4.5 On-Call Status Panel

```
  Team             : FizzBuzz Reliability Engineering
  Team Size        : 1
  Current On-Call  : Bob McFizzington
  Title            : Senior Principal Staff FizzBuzz Re
  Phone            : +1-555-FIZZBUZZ
  Email            : bob.mcfizzington@enterprise.exampl
```

The on-call rotation is computed by `OnCallSchedule.get_current_on_call()` using modulo arithmetic: `(epoch_hours // rotation_interval_hours) % team_size`. With a team size of 1 and a rotation interval of 168 hours (one week), the rotation index is always 0. The current on-call engineer is always Bob McFizzington.

---

## 5. Cache Diagnostics

The cache subsystem (`enterprise_fizzbuzz/infrastructure/cache.py`) stores FizzBuzz evaluation results using `CacheStore` with MESI coherence tracking and configurable eviction policies.

### 5.1 Reading the Cache Dashboard

`CacheDashboard.render()` produces the following display. Key fields:

| Field               | Source                          | What to Look For |
|---------------------|---------------------------------|------------------|
| **Eviction Policy** | `CacheStatistics.policy_name`   | Active eviction policy. One of: LRU, LFU, FIFO, DramaticRandom. |
| **Entries / Max**   | `total_entries / max_size`      | Current vs. maximum capacity. At 100%, every new entry triggers an eviction. |
| **Capacity Bar**    | `#` filled, `-` empty           | Visual fill level. |
| **Hit Rate Bar**    | `#` filled, `-` empty           | Visual hit rate. Higher is better. |
| **Total Hits**      | `CacheStatistics.total_hits`    | Number of cache hits (evaluation result served from cache). |
| **Total Misses**    | `CacheStatistics.total_misses`  | Number of cache misses (evaluation had to run the full pipeline). |
| **Hit Rate**        | `total_hits / (hits + misses)`  | Percentage of requests served from cache. |
| **Total Evictions** | `CacheStatistics.total_evictions` | Number of entries evicted to make room for new entries. |
| **Invalidations**   | `CacheStatistics.total_invalidations` | Number of explicit invalidations. |

### 5.2 Hit Rate Analysis

| Hit Rate   | Assessment | Action |
|------------|------------|--------|
| > 90%      | Healthy. The cache is serving most requests. | None required. |
| 70-90%     | Acceptable. Some misses are expected for new numbers. | Check if the working set exceeds `max_size`. |
| 50-70%     | Below expectations. High eviction rate or short TTL. | Review `max_size` (default: 1024) and `ttl_seconds` (default: 3600). |
| < 50%      | Cache is not effective. | Check for cache warming failures, TTL expiration, or capacity issues. Consider increasing `max_size`. |
| 0%         | Cache is not being used, or every entry expires before reuse. | Verify caching is enabled and `CacheMiddleware` is in the pipeline (priority 4). |

Note: A low hit rate is expected during the first pass through a number range, as every number will be a cold miss. Hit rate should improve on subsequent passes.

### 5.3 MESI State Distribution

The cache implements the Modified-Exclusive-Shared-Invalid coherence protocol via `CacheCoherenceProtocol`. The dashboard shows the distribution of entries across MESI states:

```
  MESI Coherence State Distribution:
    MODIFIED    : 2
    EXCLUSIVE   : 98
    SHARED      : 0
    INVALID     : 0
```

| State        | Meaning | Expected Distribution |
|--------------|---------|----------------------|
| **MODIFIED** | Entry has been updated since it was loaded. | Low count. Entries transition here when `CacheStore.put()` updates an existing entry. |
| **EXCLUSIVE** | Entry is loaded and unmodified. | High count. This is the normal state for cached entries. New entries start in EXCLUSIVE. |
| **SHARED**   | Entry is shared with another cache reader. | Always 0 in practice. This is a single-process application. If you see entries in SHARED state, congratulations: you have discovered multi-tenancy in a single-threaded FizzBuzz application. |
| **INVALID**  | Entry has been invalidated. | Should be 0 in active entries. Entries transition to INVALID on eviction before being removed from the dict. If you see a non-zero INVALID count, entries are being invalidated but not removed. |

**Valid state transitions** (from `CacheCoherenceProtocol._VALID_TRANSITIONS`):

```
INVALID   -> EXCLUSIVE           (cache miss, entry loaded)
EXCLUSIVE -> MODIFIED            (entry updated)
EXCLUSIVE -> SHARED              (hypothetical concurrent reader)
EXCLUSIVE -> INVALID             (entry invalidated/evicted)
SHARED    -> MODIFIED            (entry updated)
SHARED    -> INVALID             (entry invalidated/evicted)
MODIFIED  -> EXCLUSIVE           (write-back completed)
MODIFIED  -> SHARED              (write-back + share)
MODIFIED  -> INVALID             (entry invalidated/evicted)
```

An invalid transition raises `CacheCoherenceViolationError`. If you see this exception in logs, a code path is attempting a transition that violates the MESI protocol (e.g., `INVALID -> MODIFIED` without going through `EXCLUSIVE` first). The `CacheStore` handles this gracefully by resetting the entry to `EXCLUSIVE`, but the violation is logged.

### 5.4 Eviction Policies

Four eviction policies are available via `EvictionPolicyFactory`:

| Policy            | Class                 | Selection Strategy |
|-------------------|-----------------------|-------------------|
| `lru`             | `LRUPolicy`           | Evicts the least recently accessed entry. |
| `lfu`             | `LFUPolicy`           | Evicts the least frequently accessed entry. |
| `fifo`            | `FIFOPolicy`          | Evicts the oldest entry regardless of access patterns. |
| `dramatic_random` | `DramaticRandomPolicy` | Randomly selects a victim. Logs a WARNING-level eulogy. |

If the `DramaticRandomPolicy` is active, expect WARNING-level log messages for every eviction. These are eulogies composed by `EulogyGenerator.compose()` and are not actual warnings. Do not page yourself over cache eulogies.

### 5.5 Cache Entry Dignity

Each `CacheEntry` has a `dignity_level` float in [0.0, 1.0] that degrades linearly over its TTL. An entry at half its TTL has 50% dignity remaining. The dignity level is reported in eviction records and eulogies. It has no functional impact on eviction decisions (except as flavor text), but monitoring a fleet of zero-dignity cache entries is a good indicator that TTL values may need adjustment.

---

## 6. Escalation Procedure

The escalation chain is defined in `OnCallSchedule.get_escalation_contacts()` (`enterprise_fizzbuzz/infrastructure/sla.py`). It consists of four tiers. All tiers are staffed by the same engineer.

### 6.1 Escalation Tiers

| Tier | Title | Responsibilities | Action |
|------|-------|------------------|--------|
| **L1** | On-Call Engineer | First response. Acknowledge the alert and begin investigation. | Acknowledge alert and begin investigation. |
| **L2** | Senior On-Call Escalation Engineer | If L1 cannot resolve within the response time window. | Escalate to senior management (yourself). |
| **L3** | Principal FizzBuzz Incident Commander | If the issue is a SEV-1 or error budget is exhausted. | Declare SEV-1 and convene the war room (your desk). |
| **L4** | VP of FizzBuzz Reliability & Existential Dread | If all else fails. | Update the status page and contemplate career choices. |

### 6.2 Contact Information

All escalation tiers route to the same contact:

| Field   | Value |
|---------|-------|
| **Name**  | Bob McFizzington |
| **Title** | Senior Principal Staff FizzBuzz Reliability Engineer II |
| **Email** | bob.mcfizzington@enterprise.example.com |
| **Phone** | +1-555-FIZZBUZZ |

### 6.3 On-Call Rotation

The on-call rotation is managed by `OnCallSchedule` with the following parameters:

| Parameter                  | Value |
|----------------------------|-------|
| Team name                  | FizzBuzz Reliability Engineering |
| Team size                  | 1 |
| Rotation interval          | 168 hours (1 week) |
| Total unique engineers     | 1 |
| Diversity index            | 0.0 |

The rotation algorithm computes `(epoch_hours // 168) % 1`, which always yields 0. Bob is on call for every rotation.

### 6.4 Escalation Workflow

```
1. Alert fires (P1-P4).
     |
     v
2. L1 (Bob): Acknowledge the alert within the response time.
   - P1: 5 minutes
   - P2: 15 minutes
   - P3: 1 hour
   - P4: Next business day
     |
     v
3. L1 investigation: Follow the triage decision tree (Section 1.4).
   Identify root cause. Apply remediation.
     |
     +-- Resolved? --> Resolve the alert. Write a brief note. Done.
     |
     +-- Not resolved? --> Escalate to L2.
         |
         v
4. L2 (Bob): Review L1 findings. Apply deeper diagnostics.
   Check circuit breaker state, chaos status, cache metrics.
     |
     +-- Resolved? --> Resolve the alert. Done.
     |
     +-- Not resolved? --> Escalate to L3.
         |
         v
5. L3 (Bob): Declare SEV-1 incident.
   Convene the war room (move from your desk to a different chair at your desk).
   Begin incident timeline. Coordinate with all affected teams (yourself).
     |
     +-- Resolved? --> Conduct post-mortem (with yourself). Done.
     |
     +-- Not resolved? --> Escalate to L4.
         |
         v
6. L4 (Bob): Accept that this is your life now.
   Update the status page. Notify stakeholders (yourself).
   Consider whether computing n % 3 was worth all of this.
   Resolve the issue or wait for it to resolve itself.
```

### 6.5 Incident Severity Classification

| SEV Level | Criteria | Expected Response |
|-----------|----------|-------------------|
| SEV-1     | P1 alert firing. Error budget exhausted. Pipeline down. | Full incident response. War room. Status page update. |
| SEV-2     | P2 alert firing. SLO violations accumulating. | Active investigation. Hourly status updates to yourself. |
| SEV-3     | P3 alert firing. Burn rate elevated. | Monitor during business hours. Daily status note. |
| SEV-4     | P4 alert firing. Minor drift. | Include in weekly reliability report (which you write, review, and file). |

---

## Appendix A: Quick Reference Commands

### Check Circuit Breaker Status
```python
from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
    CircuitBreakerDashboard,
    CircuitBreakerRegistry,
)

registry = CircuitBreakerRegistry.get_instance()
print(CircuitBreakerDashboard.render_all(registry))
```

### Check Chaos Monkey Status
```python
from enterprise_fizzbuzz.infrastructure.chaos import ChaosMonkey, PostMortemGenerator

monkey = ChaosMonkey.get_instance()
if monkey is not None:
    print(monkey.get_summary())
    print(PostMortemGenerator.generate(monkey))
```

### Check SLA Status
```python
from enterprise_fizzbuzz.infrastructure.sla import SLADashboard

# Assuming sla_monitor is your SLAMonitor instance
print(SLADashboard.render(sla_monitor))
```

### Check Cache Status
```python
from enterprise_fizzbuzz.infrastructure.cache import CacheDashboard

# Assuming cache_store is your CacheStore instance
stats = cache_store.get_statistics()
print(CacheDashboard.render(stats))
```

### Manual Circuit Breaker Reset
```python
from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreakerRegistry

registry = CircuitBreakerRegistry.get_instance()
cb = registry.get("FizzBuzzPipelineCircuit")
if cb is not None:
    cb.reset()  # Transitions to CLOSED, clears all metrics
```

---

## Appendix B: Alert Cooldown Behavior

The `AlertManager` suppresses duplicate alerts for the same SLO within a configurable cooldown period (default: 60 seconds). This prevents alert storms where, for example, 10,000 consecutive latency violations each generate an individual page.

If you are not receiving alerts that you expect, check whether the cooldown is suppressing them. The cooldown is per-SLO, so a latency alert and an accuracy alert can fire simultaneously even if both SLOs violated within the same cooldown window.

---

*This runbook is maintained by the FizzBuzz Reliability Engineering team (Bob McFizzington). For questions, comments, or existential dread about being the sole on-call engineer for a FizzBuzz platform, contact +1-555-FIZZBUZZ.*

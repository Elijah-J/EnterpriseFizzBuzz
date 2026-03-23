[Back to README](../README.md) | [Architecture](ARCHITECTURE.md) | [Features](FEATURES.md) | [CLI Reference](CLI_REFERENCE.md) | [Subsystems](SUBSYSTEMS.md) | [FAQ](FAQ.md) | [Testing](TESTING.md)

# CLI Reference

All CLI flags, environment variables, and quick start examples for the Enterprise FizzBuzz Platform.

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

# Machine Learning strategy (trains a neural network, then runs inference)
python main.py --strategy machine_learning --range 1 20 --debug

# CSV output, no frills
python main.py --range 1 100 --format csv --no-banner --no-summary

# Fault-tolerant FizzBuzz with circuit breaker protection
python main.py --circuit-breaker --circuit-status --verbose

# Full enterprise stack: ML + circuit breaker + status dashboard
python main.py --strategy machine_learning --circuit-breaker --circuit-status --range 1 20

# FizzBuzz auf Deutsch (German locale)
python main.py --locale de --range 1 20

# FizzBuzz en francais (French locale)
python main.py --locale fr --format json

# FizzBuzz in Klingon, because global reach means *galactic* reach
python main.py --locale tlh --range 1 15

# Japanese locale with async execution
python main.py --locale ja --async --range 1 50

# FizzBuzz in Sindarin (Grey-elven), for the Undying Lands market segment
python main.py --locale sjn --range 1 15

# FizzBuzz in Quenya (High-elven), because Tolkien would have wanted this
python main.py --locale qya --range 1 20 --format json

# List all available locales and their metadata
python main.py --list-locales

# Distributed tracing with ASCII waterfall visualization
python main.py --trace --range 1 15

# Export trace data as JSON for your non-existent Jaeger instance
python main.py --trace-json --range 1 5

# Full observability stack: tracing + circuit breaker + ML
python main.py --trace --circuit-breaker --strategy machine_learning --range 1 20

# RBAC: Run as a FIZZBUZZ_SUPERUSER (trust-mode, full access)
python main.py --user alice --role FIZZBUZZ_SUPERUSER --range 1 100

# RBAC: Run as a lowly FIZZ_READER (can only evaluate 1-50)
python main.py --user intern --role FIZZ_READER --range 1 50

# RBAC: Run as ANONYMOUS and watch the access denials roll in
python main.py --user nobody --role ANONYMOUS --range 1 20

# RBAC: Token-based authentication (the cryptographically serious way)
python main.py --token "EFP.<payload>.<signature>" --range 1 100

# Full stack: RBAC + tracing + circuit breaker + ML (peak enterprise)
python main.py --user alice --role FIZZBUZZ_SUPERUSER --trace --circuit-breaker --strategy machine_learning --range 1 20

# Event Sourcing: append-only audit log of every FizzBuzz decision
python main.py --event-sourcing --range 1 20

# Event Sourcing with replay: rebuild projections from the event stream
python main.py --event-sourcing --replay --range 1 30

# Temporal query: reconstruct FizzBuzz state as it existed at event #42
python main.py --event-sourcing --temporal-query 42 --range 1 50

# Quantum FizzBuzz: evaluate divisibility using Shor's algorithm on simulated qubits
python main.py --quantum --range 1 20

# Quantum with noise: add decoherence to simulate real quantum hardware fragility
python main.py --quantum --quantum-noise 0.1 --quantum-shots 200 --range 1 15

# Quantum with circuit visualization: see the ASCII quantum circuit diagram
python main.py --quantum --quantum-circuit --range 1 10

# Quantum dashboard: state amplitudes, gate counts, and the Quantum Advantage Ratio (-10^14x)
python main.py --quantum --quantum-dashboard --range 1 20

# Peak quantum: quantum + Paxos consensus + tracing (5 nodes voting on quantum results)
python main.py --quantum --quantum-dashboard --paxos --paxos-dashboard --trace --range 1 15

# Cross-compile FizzBuzz rules to ANSI C (because smart toasters need FizzBuzz)
python main.py --compile-to c --compile-out fizzbuzz.c

# Cross-compile to Rust with round-trip verification (because safety-critical FizzBuzz demands Clippy compliance)
python main.py --compile-to rust --compile-out fizzbuzz.rs --compile-verify

# Cross-compile to WebAssembly Text format (because browsers deserve FizzBuzz too)
python main.py --compile-to wat --compile-out fizzbuzz.wat

# Cross-compile with IR preview: see the rule definition, IR, and generated code side by side
python main.py --compile-to c --compile-preview

# Cross-compiler dashboard: compilation stats, code size, overhead factor, verification results
python main.py --compile-to rust --compile-dashboard

# Full cross-compiler stack: compile to C with verification, preview, and dashboard
python main.py --compile-to c --compile-verify --compile-preview --compile-dashboard

# Federated Learning: train a shared model across 5 FizzBuzz nodes (star topology, FedAvg)
python main.py --strategy machine_learning --federated --fed-nodes 5 --fed-rounds 10

# Federated Learning with differential privacy (epsilon=0.5 for strong privacy guarantees)
python main.py --strategy machine_learning --federated --fed-epsilon 0.5 --fed-dashboard

# Federated Learning with mesh topology and FedProx aggregation (maximum enterprise)
python main.py --strategy machine_learning --federated --fed-topology mesh --fed-strategy fedprox --fed-dashboard

# Federated Learning with ring topology, FedMA, and 8 nodes (peer-to-peer gradient passing)
python main.py --strategy machine_learning --federated --fed-topology ring --fed-strategy fedma --fed-nodes 8

# Peak distributed ML: federated learning + quantum + Paxos consensus (5 nodes voting on federated quantum results)
python main.py --strategy machine_learning --federated --fed-dashboard --quantum --paxos --range 1 20

# Self-Modifying Code: enable runtime AST mutation (rules that rewrite themselves as they evaluate)
python main.py --self-modify --range 1 50

# Self-Modifying Code: increase mutation rate for more aggressive evolution (50% chance per evaluation)
python main.py --self-modify --self-modify-rate 0.5 --range 1 100

# Self-Modifying Code: display the ASCII self-modification dashboard with AST, fitness, and mutation history
python main.py --self-modify --self-modify-dashboard --range 1 50

# Peak self-modification: self-modifying code + tracing + metrics + compliance (every mutation is a regulated, observable event)
python main.py --self-modify --self-modify-dashboard --trace --metrics --metrics-dashboard --compliance --compliance-dashboard --range 1 30

# Compliance Chatbot: ask a regulatory question about FizzBuzz operations
python main.py --chatbot "Is the classification of 15 as FizzBuzz GDPR-compliant?"

# Compliance Chatbot: ask about SOX segregation of duties for FizzBuzz evaluation
python main.py --chatbot "Does evaluating number 42 require SOX segregation of duties?"

# Compliance Chatbot: ask about cross-regime conflicts (GDPR erasure vs SOX retention)
python main.py --chatbot "Does GDPR right to erasure conflict with SOX audit retention for FizzBuzz 15?"

# Compliance Chatbot: ask about HIPAA and Protected Health Information
python main.py --chatbot "Does the number 42 constitute Protected Health Information?"

# Compliance Chatbot: interactive REPL for ongoing regulatory consultations with follow-up context
python main.py --chatbot-interactive --range 1 50

# Compliance Chatbot: display the session dashboard with verdict distribution and intent statistics
python main.py --chatbot "Can I export FizzBuzz data under GDPR?" --chatbot-dashboard

# Peak compliance chatbot: chatbot + compliance + tracing + event sourcing (every advisory is a regulated, traceable event)
python main.py --chatbot "Is my FizzBuzz platform compliant?" --chatbot-dashboard --compliance --compliance-dashboard --trace --event-sourcing --range 1 20

# P2P Gossip Network: disseminate FizzBuzz results across 7 simulated nodes via SWIM and Kademlia
python main.py --p2p --range 1 50

# P2P Gossip Network: configure the number of peer nodes in the cluster
python main.py --p2p --p2p-nodes 10 --range 1 100

# P2P Gossip Network: display the ASCII P2P dashboard with topology, gossip stats, DHT routing, and Merkle sync
python main.py --p2p --p2p-dashboard --range 1 30

# P2P + Paxos: gossip protocol dissemination on top of Paxos consensus (distributed everything)
python main.py --p2p --p2p-dashboard --paxos --paxos-dashboard --range 1 20

# Peak distributed: P2P gossip + federated learning + quantum + Paxos + kernel (every node votes on quantum federated results managed by an OS kernel)
python main.py --p2p --p2p-dashboard --federated --fed-dashboard --quantum --paxos --kernel --range 1 15

# FizzBuzz OS Kernel: enable the operating system kernel for process-managed evaluation
python main.py --kernel --range 1 30

# FizzBuzz OS Kernel: use the Priority Preemptive scheduler (FizzBuzz evaluations jump the queue)
python main.py --kernel --kernel-scheduler priority --range 1 50

# FizzBuzz OS Kernel: use the Completely Fair Scheduler (Linux CFS-inspired, red-black tree of virtual runtime)
python main.py --kernel --kernel-scheduler cfs --range 1 100

# FizzBuzz OS Kernel: display the ASCII kernel dashboard with process table, memory map, and interrupt log
python main.py --kernel --kernel-dashboard --range 1 50

# FizzBuzz OS Kernel + tracing: observe process scheduling through the distributed tracing subsystem
python main.py --kernel --kernel-dashboard --trace --range 1 20

# FizzBuzz OS Kernel + quantum + Paxos: five consensus nodes voting on quantum results managed by an OS kernel
python main.py --kernel --kernel-dashboard --quantum --paxos --paxos-dashboard --range 1 15

# Peak kernel: OS kernel + compliance + RBAC + SLA + cost tracking (every process is a regulated, observable, billed syscall)
python main.py --kernel --kernel-dashboard --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --range 1 20

# Full compliance stack: event sourcing + RBAC + tracing (peak audit)
python main.py --event-sourcing --user alice --role FIZZBUZZ_SUPERUSER --trace --range 1 20

# Chaos Engineering: unleash the Chaos Monkey (default severity: level 1)
python main.py --chaos --range 1 30

# Maximum chaos: level 5 apocalypse with post-mortem incident report
python main.py --chaos --chaos-level 5 --post-mortem --range 1 50

# Game Day: run the "modulo_meltdown" scenario (escalating rule engine failures)
python main.py --gameday modulo_meltdown --range 1 30

# Game Day: total chaos with all fault types at maximum severity
python main.py --gameday total_chaos --post-mortem --range 1 20

# Chaos + circuit breaker: watch the monkey trip the breaker
python main.py --chaos --chaos-level 3 --circuit-breaker --circuit-status --range 1 30

# Full resilience stack: chaos + circuit breaker + ML + tracing (peak entropy)
python main.py --chaos --chaos-level 4 --circuit-breaker --strategy machine_learning --trace --post-mortem --range 1 20

# Feature flags: enable progressive rollout with default flag configuration
python main.py --feature-flags --range 1 30

# Feature flags: override a flag to enable the experimental Wuzz rule (divisible by 7)
python main.py --feature-flags --flag wuzz_rule_experimental=true --range 1 30

# Feature flags: disable the Fizz rule and see what happens (spoiler: no Fizz)
python main.py --feature-flags --flag fizz_rule_enabled=false --range 1 20

# Feature flags: list all registered flags and their configuration
python main.py --feature-flags --list-flags

# Feature flags: progressive rollout at 50% with circuit breaker (peak toggle)
python main.py --feature-flags --circuit-breaker --circuit-status --range 1 50

# Full enterprise stack: feature flags + RBAC + tracing + chaos (peak configuration)
python main.py --feature-flags --user alice --role FIZZBUZZ_SUPERUSER --trace --chaos --range 1 20

# SLA Monitoring: track latency, accuracy, and availability SLOs
python main.py --sla --range 1 50

# SLA Monitoring with dashboard: see error budgets and compliance ratios
python main.py --sla --sla-dashboard --range 1 100

# Quick on-call status: who's responsible when FizzBuzz goes down? (spoiler: Bob)
python main.py --on-call

# SLA + chaos: watch the error budget burn as the monkey wreaks havoc
python main.py --sla --sla-dashboard --chaos --chaos-level 3 --range 1 50

# Full reliability stack: SLA + circuit breaker + chaos + tracing (peak SRE)
python main.py --sla --sla-dashboard --circuit-breaker --circuit-status --chaos --chaos-level 2 --trace --range 1 30

# Caching: enable the in-memory cache with default LRU eviction
python main.py --cache --range 1 50

# Caching with statistics dashboard: see hit rates and eviction counts
python main.py --cache --cache-stats --range 1 100

# Caching with LFU eviction and a max cache size of 32
python main.py --cache --cache-policy lfu --cache-size 32 --cache-stats --range 1 100

# Caching with DramaticRandom eviction: entries are evicted at random, with eulogies
python main.py --cache --cache-policy dramatic_random --cache-stats --range 1 50

# Cache warming: pre-populate the cache before execution (defeats the purpose of caching)
python main.py --cache --cache-warm --cache-stats --range 1 100

# Full caching stack: LRU + warming + stats + circuit breaker (peak memoization)
python main.py --cache --cache-warm --cache-stats --circuit-breaker --circuit-status --range 1 50

# Caching + chaos: watch the monkey corrupt cached results
python main.py --cache --cache-stats --chaos --chaos-level 3 --range 1 30

# Full enterprise stack: caching + SLA + tracing + RBAC
python main.py --cache --cache-stats --sla --sla-dashboard --trace --user alice --role FIZZBUZZ_SUPERUSER --range 1 20

# Repository Pattern: persist results in-memory (the default backend)
python main.py --repository memory --range 1 20

# Repository Pattern: persist results to SQLite (an actual database, for once)
python main.py --repository sqlite --db-path fizzbuzz.db --range 1 50

# Repository Pattern: persist results as artisanal JSON files on disk
python main.py --repository filesystem --results-dir ./fizzbuzz_results --range 1 30

# Repository + full stack: SQLite persistence with tracing, caching, and RBAC
python main.py --repository sqlite --db-path fizzbuzz.db --trace --cache --user alice --role FIZZBUZZ_SUPERUSER --range 1 20

# Database Migrations: apply all migrations to the in-memory schema (it won't persist)
python main.py --migrate --range 1 20

# Migration status dashboard: see which migrations have been applied (to RAM)
python main.py --migrate --migrate-status --range 1 20

# Seed data: use the FizzBuzz engine to populate the FizzBuzz database (the ouroboros)
python main.py --migrate --migrate-seed --range 1 50

# Rollback: undo the last N migrations (default: 1)
python main.py --migrate --migrate-rollback 3 --range 1 20

# Full migration stack: apply, seed, and display status dashboard
python main.py --migrate --migrate-seed --migrate-status --range 1 30

# Peak enterprise: migrations + caching + SLA + tracing + RBAC (the schema will still vanish on exit)
python main.py --migrate --migrate-seed --migrate-status --cache --sla --trace --user alice --role FIZZBUZZ_SUPERUSER --range 1 20

# Health Check Probes: run all three probes (liveness, readiness, startup)
python main.py --health --range 1 20

# Liveness probe only: verify that FizzBuzz can still FizzBuzz
python main.py --liveness --range 1 15

# Readiness probe only: check all subsystem health indicators
python main.py --readiness --range 1 20

# Health dashboard: see the full ASCII health status after execution
python main.py --health --health-dashboard --range 1 30

# Self-healing mode: auto-recover degraded subsystems with exponential backoff
python main.py --health --self-heal --range 1 50

# Health + circuit breaker: monitor circuit health in real time
python main.py --health --health-dashboard --circuit-breaker --circuit-status --range 1 30

# Health + chaos: watch the probes detect chaos-induced degradation
python main.py --health --health-dashboard --self-heal --chaos --chaos-level 3 --range 1 30

# Peak operational readiness: health + SLA + tracing + cache + ML (the dashboard will be glorious)
python main.py --health --health-dashboard --self-heal --sla --sla-dashboard --trace --cache --strategy machine_learning --range 1 20

# Prometheus metrics: collect counters, gauges, and histograms during evaluation
python main.py --metrics --range 1 50

# Prometheus metrics with text exposition export (the format nobody will scrape)
python main.py --metrics --metrics-export --range 1 100

# Prometheus metrics with ASCII Grafana dashboard (sparklines in the terminal)
python main.py --metrics --metrics-dashboard --range 1 100

# Full observability stack: metrics + tracing + SLA + health (peak telemetry)
python main.py --metrics --metrics-dashboard --trace --sla --sla-dashboard --health --health-dashboard --range 1 30

# Metrics + chaos: watch the counters climb as the monkey wreaks havoc
python main.py --metrics --metrics-dashboard --chaos --chaos-level 3 --range 1 50

# Peak enterprise: metrics + cache + circuit breaker + ML + tracing (every subsystem instrumented)
python main.py --metrics --metrics-dashboard --metrics-export --cache --circuit-breaker --strategy machine_learning --trace --range 1 20

# Webhook notifications: enable webhook dispatch for FizzBuzz events
python main.py --webhooks --range 1 30

# Webhook with a registered endpoint (simulated HTTP POST, obviously)
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --range 1 20

# Webhook with HMAC-SHA256 secret and delivery log
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-secret "my-very-secret-key" --webhook-log --range 1 20

# Webhook test: fire a test event to all registered endpoints and exit
python main.py --webhooks --webhook-url https://hooks.example.com/test --webhook-test

# Webhook with Dead Letter Queue inspection (see what failed to deliver)
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-dlq --range 1 50

# Webhook with event filtering: only subscribe to specific event types
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-events "evaluation.completed,circuit_breaker.opened" --range 1 30

# Full notification stack: webhooks + metrics + tracing + chaos (peak telemetry)
python main.py --webhooks --webhook-url https://hooks.example.com/fizzbuzz --webhook-log --metrics --trace --chaos --range 1 20

# Service mesh: decompose FizzBuzz into 7 microservices with sidecar proxies
python main.py --service-mesh --range 1 20

# Service mesh with ASCII topology diagram: see the request flow between services
python main.py --service-mesh --mesh-topology --range 1 15

# Service mesh with network fault injection: add latency and packet loss
python main.py --service-mesh --mesh-latency --mesh-packet-loss --range 1 30

# Canary deployment: route traffic to experimental DivisibilityService v2
python main.py --service-mesh --canary --range 1 20

# Full service mesh stack: latency + packet loss + canary + topology (peak microservices)
python main.py --service-mesh --mesh-latency --mesh-packet-loss --canary --mesh-topology --range 1 20

# Service mesh + chaos + circuit breaker: maximum distributed systems entropy
python main.py --service-mesh --mesh-latency --chaos --chaos-level 3 --circuit-breaker --circuit-status --range 1 20

# Peak enterprise: service mesh + metrics + tracing + SLA + health (the topology diagram will be glorious)
python main.py --service-mesh --mesh-topology --metrics --metrics-dashboard --trace --sla --sla-dashboard --health --health-dashboard --range 1 15

# Message Queue: enable Kafka-style message broker with partitioned topics
python main.py --message-queue --range 1 30

# Message Queue: list all topics with partition counts and message throughput
python main.py --message-queue --mq-topics --range 1 50

# Message Queue: display consumer lag across all consumer groups and partitions
python main.py --message-queue --mq-lag --range 1 100

# Message Queue: ASCII dashboard with topic throughput, partition distribution, and consumer lag
python main.py --message-queue --mq-dashboard --range 1 50

# Message Queue: replay messages from a specific topic starting at a given offset
python main.py --message-queue --mq-replay fizzbuzz.evaluations.completed 0 --range 1 30

# Message Queue: configure partition count for topics (default: 4)
python main.py --message-queue --mq-partitions 8 --range 1 50

# Message Queue: list all consumer groups with assigned partitions and committed offsets
python main.py --message-queue --mq-consumer-groups --range 1 30

# Message Queue: display schema registry with registered schemas and version history
python main.py --message-queue --mq-schema-registry --range 1 20

# Full event-driven stack: message queue + event sourcing + webhooks + metrics (peak asynchronous architecture)
python main.py --message-queue --mq-dashboard --event-sourcing --webhooks --metrics --metrics-dashboard --range 1 20

# Secrets Vault: enable the vault and auto-unseal for evaluation
python main.py --vault --range 1 30

# Secrets Vault: check vault seal status and secret inventory
python main.py --vault --vault-status

# Secrets Vault: provide an unseal share (3 of 5 required for quorum)
python main.py --vault --vault-unseal "1:0a3f..."

# Secrets Vault: store a secret in the vault at a specific path
python main.py --vault --vault-set secret/fizzbuzz/blockchain/difficulty 4

# Secrets Vault: retrieve a secret from the vault
python main.py --vault --vault-get secret/fizzbuzz/blockchain/difficulty

# Secrets Vault: rotate all secrets on their configured schedule
python main.py --vault --vault-rotate

# Secrets Vault: scan the codebase for hardcoded values that should be in the vault
python main.py --vault --vault-scan

# Secrets Vault: display the immutable vault audit log
python main.py --vault --vault-audit-log

# Secrets Vault: ASCII dashboard with seal status, secrets, rotation schedule, and audit trail
python main.py --vault --vault-dashboard --range 1 30

# Secrets Vault: seal the vault (suspends all FizzBuzz evaluation until re-unsealed)
python main.py --vault --vault-seal

# Full security stack: vault + RBAC + compliance + tracing (peak zero-trust FizzBuzz)
python main.py --vault --vault-dashboard --user alice --role FIZZBUZZ_SUPERUSER --compliance --trace --range 1 20

# Hot-Reload: watch config.yaml for changes and reconfigure at runtime (Raft consensus included)
python main.py --hot-reload --range 1 30

# Hot-Reload with custom poll interval (every 2 seconds instead of 500ms)
python main.py --hot-reload --hot-reload-interval 2000 --range 1 50

# Config validation: validate config.yaml against the schema without running
python main.py --config-validate

# Config diff: show changes between current and on-disk configuration
python main.py --config-diff

# Config history: display the event-sourced configuration change log
python main.py --config-history

# Hot-Reload + SLA + health: reconfigure the platform without violating your SLOs
python main.py --hot-reload --sla --sla-dashboard --health --health-dashboard --range 1 30

# Peak enterprise: hot-reload + service mesh + metrics + tracing (every subsystem reconfigurable at runtime)
python main.py --hot-reload --service-mesh --metrics --metrics-dashboard --trace --range 1 20

# Rate limiting: throttle FizzBuzz evaluations with the default token bucket algorithm
python main.py --rate-limit --range 1 100

# Rate limiting with sliding window algorithm at 30 requests per minute
python main.py --rate-limit --rate-limit-algo sliding_window --rate-limit-rpm 30 --range 1 50

# Rate limiting with burst credits: carry over unused quota from previous windows
python main.py --rate-limit --rate-limit-burst-credits --range 1 100

# Rate limit dashboard: see per-bucket fill levels and quota utilization
python main.py --rate-limit --rate-limit-dashboard --range 1 100

# Reserve evaluation capacity: pre-book 20 evaluations before running
python main.py --rate-limit --rate-limit-reserve 20 --range 1 50

# Full throttling stack: rate limiting + circuit breaker + SLA + metrics (peak capacity management)
python main.py --rate-limit --rate-limit-dashboard --rate-limit-burst-credits --circuit-breaker --circuit-status --sla --sla-dashboard --metrics --range 1 30

# Compliance: enable SOX/GDPR/HIPAA compliance for all evaluations
python main.py --compliance --range 1 30

# Compliance with a specific regime (SOX only)
python main.py --compliance --compliance-regime sox --range 1 20

# GDPR: grant consent for a number before evaluating it
python main.py --compliance --compliance-regime gdpr --gdpr-consent 42 --range 1 50

# GDPR: exercise right-to-erasure and witness THE COMPLIANCE PARADOX
python main.py --compliance --gdpr-forget 15 --range 1 30

# Compliance dashboard: see Bob McFizzington's stress level and per-regime posture
python main.py --compliance --compliance-dashboard --range 1 50

# HIPAA minimum necessary: restrict information flow between services
python main.py --compliance --compliance-regime hipaa --hipaa-minimum-necessary --range 1 20

# Full compliance stack: all three regimes + event sourcing + blockchain (peak regulatory theater)
python main.py --compliance --compliance-regime all --event-sourcing --blockchain --range 1 20

# Peak enterprise: compliance + RBAC + tracing + SLA + metrics (every evaluation is a regulated financial transaction)
python main.py --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --trace --sla --sla-dashboard --metrics --range 1 15

# FinOps: track the cost of every FizzBuzz evaluation in FizzBucks
python main.py --cost-tracking --range 1 50

# FinOps: generate an itemized ASCII invoice for an evaluation
python main.py --cost-tracking --cost-invoice last --range 1 20

# FinOps: monthly cost report with spending breakdown by subsystem
python main.py --cost-tracking --cost-report --range 1 100

# FinOps: set a budget and get alerted when spending exceeds it
python main.py --cost-tracking --cost-budget 0.50 --range 1 100

# FinOps: see how much you'd save with a 3-year commitment plan
python main.py --cost-tracking --cost-savings-plan --range 1 100

# FinOps: ASCII cost dashboard with spending sparklines and budget burn-down
python main.py --cost-tracking --cost-dashboard --range 1 100

# FinOps: display costs in USD instead of FizzBucks (exchange rate fluctuates)
python main.py --cost-tracking --cost-currency usd --range 1 50

# Peak FinOps: cost tracking + compliance + SLA + metrics (the CFO's dream dashboard)
python main.py --cost-tracking --cost-dashboard --compliance --compliance-dashboard --sla --sla-dashboard --metrics --range 1 20

# Disaster Recovery: enable WAL and periodic snapshots for every evaluation
python main.py --wal-enable --range 1 50

# Backup: create a snapshot of the entire FizzBuzz application state (in RAM)
python main.py --backup-now --range 1 50

# Restore: recover from a specific snapshot (stored in the same process memory it's protecting)
python main.py --restore latest --range 1 30

# Point-in-Time Recovery: reconstruct FizzBuzz state at a specific timestamp
python main.py --restore-point-in-time "2026-03-22T14:32:07" --range 1 50

# DR drill: intentionally destroy the system and measure how long recovery takes
python main.py --dr-drill --range 1 30

# DR drill with report: see RTO/RPO compliance metrics and improvement recommendations
python main.py --dr-drill --dr-report --range 1 50

# Backup listing: show all available snapshots with integrity checksums
python main.py --backup-list --range 1 20

# Retention policy: manage backup lifecycle with tiered retention schedules
python main.py --backup-now --backup-retention standard --range 1 50

# Full DR stack: WAL + snapshots + drill + compliance + SLA (peak business continuity)
python main.py --wal-enable --backup-now --dr-drill --dr-report --compliance --sla --sla-dashboard --range 1 20

# A/B Testing: run an experiment comparing modulo vs. neural network strategies
python main.py --ab-test --experiment ml_vs_modulo --range 1 100

# A/B Testing: list all active experiments and their current state
python main.py --experiment-list

# A/B Testing: view real-time results with confidence intervals and p-values
python main.py --ab-test --experiment-results ml_vs_modulo --range 1 100

# A/B Testing: ASCII experiment dashboard with per-variant metrics
python main.py --ab-test --experiment-dashboard --range 1 100

# A/B Testing: set treatment traffic allocation to 25%
python main.py --ab-test --experiment ml_vs_modulo --experiment-traffic 25 --range 1 100

# A/B Testing: manually stop an experiment and lock in the results
python main.py --experiment-stop ml_vs_modulo

# A/B Testing: generate a post-experiment statistical analysis report
python main.py --experiment-report ml_vs_modulo

# Full experimentation stack: A/B testing + metrics + tracing + SLA (peak data-driven decision making)
python main.py --ab-test --experiment-dashboard --metrics --metrics-dashboard --trace --sla --sla-dashboard --range 1 50

# Data Pipeline: run FizzBuzz through the full ETL ceremony (Extract-Validate-Transform-Enrich-Load)
python main.py --pipeline --range 1 50

# Data Pipeline: run the pipeline and display the DAG visualization
python main.py --pipeline --pipeline-dag --range 1 30

# Data Pipeline: display stage durations, throughput, and lineage in the ASCII dashboard
python main.py --pipeline --pipeline-dashboard --range 1 50

# Data Pipeline: track full data lineage provenance for a specific result
python main.py --pipeline --pipeline-lineage 15 --range 1 20

# Data Pipeline: backfill historical results with new enrichment stages
python main.py --pipeline --pipeline-backfill --range 1 100

# Data Pipeline: enable checkpointing for pipeline resumption on failure
python main.py --pipeline --pipeline-checkpoint --range 1 50

# Data Pipeline: view all pipeline stages and their configuration
python main.py --pipeline --pipeline-stages --range 1 20

# Full data engineering stack: pipeline + metrics + tracing + compliance (peak ETL ceremony)
python main.py --pipeline --pipeline-dashboard --metrics --metrics-dashboard --trace --compliance --range 1 30

# OpenAPI: render the ASCII Swagger UI for the fictional REST API
python main.py --openapi

# OpenAPI: export the complete OpenAPI 3.1 specification as JSON
python main.py --openapi-spec

# OpenAPI: export the specification as YAML (for the YAML-pilled)
python main.py --openapi-yaml

# Swagger UI: alias for --openapi (because muscle memory from Swagger Hub dies hard)
python main.py --swagger-ui

# OpenAPI: display the specification statistics dashboard
python main.py --openapi-dashboard

# Peak documentation: OpenAPI spec + metrics + compliance (the spec is the source of truth)
python main.py --openapi-dashboard --metrics --metrics-dashboard --compliance --compliance-dashboard --range 1 20

# API Gateway: route evaluations through the versioned gateway (default: v3 premium tier)
python main.py --api-gateway --range 1 30

# API Gateway: use the v1 deprecated tier (enjoy the passive-aggressive sunset warnings)
python main.py --api-gateway --api-version v1 --range 1 20

# API Gateway: use v2 with blockchain and ML (the balanced middle ground)
python main.py --api-gateway --api-version v2 --range 1 20

# API Gateway: generate a new API key for your non-existent consumers
python main.py --api-gateway --api-key-generate

# API Gateway: rotate all API keys (all zero external consumers must update immediately)
python main.py --api-gateway --api-key-rotate

# API Gateway: enable HATEOAS links in every response (Richardson Maturity Level 4)
python main.py --api-gateway --api-hateoas --range 1 15

# API Gateway: replay recorded requests from the request journal
python main.py --api-gateway --api-replay --range 1 20

# API Gateway: ASCII dashboard with request volume, active keys, and deprecation countdowns
python main.py --api-gateway --api-gateway-dashboard --range 1 50

# Full gateway stack: v3 + HATEOAS + dashboard + metrics + tracing (peak API ceremony)
python main.py --api-gateway --api-version v3 --api-hateoas --api-gateway-dashboard --metrics --metrics-dashboard --trace --range 1 20

# Peak enterprise: gateway + compliance + RBAC + SLA + cost tracking (every evaluation is a regulated API call)
python main.py --api-gateway --api-gateway-dashboard --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --range 1 15

# Blue/Green Deployment: run the full six-phase deployment ceremony
python main.py --deploy --range 1 30

# Blue/Green Deployment: provision the green environment without cutting over
python main.py --deploy --deploy-provision-green --range 1 20

# Blue/Green Deployment: run smoke tests against canary numbers in the green environment
python main.py --deploy --deploy-smoke-test --range 1 20

# Blue/Green Deployment: enable shadow traffic to compare blue and green results
python main.py --deploy --deploy-shadow --range 1 50

# Blue/Green Deployment: atomically switch traffic from blue to green
python main.py --deploy --deploy-cutover --range 1 30

# Blue/Green Deployment: monitor the bake period for 5 seconds after cutover
python main.py --deploy --deploy-bake 5 --range 1 30

# Blue/Green Deployment: rollback to blue (the panic button)
python main.py --deploy --deploy-rollback --range 1 20

# Blue/Green Deployment: decommission the old blue environment after successful green cutover
python main.py --deploy --deploy-decommission --range 1 20

# Blue/Green Deployment: ASCII dashboard with environment health, cutover history, and shadow diffs
python main.py --deploy --deploy-dashboard --range 1 50

# Blue/Green Deployment: view deployment history with phase timestamps
python main.py --deploy --deploy-history --range 1 30

# Blue/Green Deployment: diff configuration between blue and green environments
python main.py --deploy --deploy-diff --range 1 20

# Full deployment stack: blue/green + metrics + tracing + SLA (peak release engineering)
python main.py --deploy --deploy-dashboard --metrics --metrics-dashboard --trace --sla --sla-dashboard --range 1 20

# Peak enterprise: deploy + compliance + RBAC + cost tracking (every deployment is a regulated event)
python main.py --deploy --deploy-dashboard --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --cost-tracking --cost-dashboard --range 1 15

# Graph Database: enable the property graph and map divisibility relationships
python main.py --graph-db --range 1 30

# Graph Database: run a CypherLite query against the integer relationship graph
python main.py --graph-db --graph-query "MATCH (n:Number) WHERE n.value > 90 RETURN n" --range 1 100

# Graph Database: ASCII visualization of the FizzBuzz relationship graph
python main.py --graph-db --graph-visualize --range 1 20

# Graph Database: analytics dashboard with centrality rankings and community detection
python main.py --graph-db --graph-dashboard --range 1 100

# Graph Database: full graph stack with tracing and metrics (peak relationship mapping)
python main.py --graph-db --graph-dashboard --graph-visualize --metrics --metrics-dashboard --trace --range 1 50

# Peak enterprise: graph database + compliance + RBAC + SLA + cost tracking (every integer is a regulated graph node)
python main.py --graph-db --graph-dashboard --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --range 1 30

# Genetic Algorithm: evolve optimal FizzBuzz rules through natural selection
python main.py --genetic --range 1 30

# Genetic Algorithm: run 1000 generations with a population of 300
python main.py --genetic --genetic-generations 1000 --genetic-population 300 --range 1 50

# Genetic Algorithm: display the Hall of Fame (top chromosomes ever discovered)
python main.py --genetic --genetic-hall-of-fame --range 1 30

# Genetic Algorithm: ASCII evolution dashboard with fitness charts and diversity gauges
python main.py --genetic --genetic-dashboard --range 1 50

# Genetic Algorithm: trigger a mass extinction event when diversity collapses
python main.py --genetic --genetic-extinction --range 1 30

# Genetic Algorithm: preview the fittest individual's output for numbers 1-30
python main.py --genetic --genetic-preview --range 1 30

# Full evolutionary stack: genetic algorithm + metrics + tracing + SLA (peak Darwinism)
python main.py --genetic --genetic-dashboard --genetic-hall-of-fame --metrics --metrics-dashboard --trace --sla --sla-dashboard --range 1 30

# Peak enterprise: genetic algorithm + compliance + RBAC + cost tracking (every chromosome is a regulated organism)
python main.py --genetic --genetic-dashboard --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --cost-tracking --cost-dashboard --range 1 20

# Natural Language Query: ask FizzBuzz a question in plain English
python main.py --nlq "Is 15 FizzBuzz?"

# NLQ: count query -- how many of a classification exist in a range
python main.py --nlq "How many Fizzes are there below 50?"

# NLQ: list query -- which numbers match a classification
python main.py --nlq "Which numbers between 1 and 30 are Buzz?"

# NLQ: statistics -- get classification distribution
python main.py --nlq "What is the most common classification from 1 to 100?"

# NLQ: explain -- understand why a number has its classification
python main.py --nlq "Why is 9 Fizz?"

# NLQ: interactive session with query history
python main.py --nlq-interactive

# NLQ: batch mode -- pipe a file of questions and get JSON answers
python main.py --nlq-batch questions.txt

# NLQ: display the ASCII dashboard with query history and intent distribution
python main.py --nlq-dashboard

# Full NLQ stack: natural language + metrics + tracing + compliance (peak accessibility)
python main.py --nlq "How many FizzBuzzes below 100?" --metrics --metrics-dashboard --trace --compliance --compliance-dashboard

# Peak enterprise: NLQ + RBAC + SLA + cost tracking (every question is a regulated query)
python main.py --nlq "List all Fizzes between 1 and 50" --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --cost-dashboard

# Load Testing: run a SMOKE test (5 VUs, quick validation)
python main.py --load-test --load-test-profile smoke --range 1 30

# Load Testing: run a LOAD test with 50 virtual users
python main.py --load-test --load-test-profile load --load-test-vus 50 --range 1 100

# Load Testing: STRESS test -- ramp up until something breaks
python main.py --load-test --load-test-profile stress --range 1 50

# Load Testing: SPIKE test -- sudden burst of 500 VUs at T=60s
python main.py --load-test --load-test-profile spike --range 1 100

# Load Testing: ENDURANCE test -- 30 VUs for extended duration
python main.py --load-test --load-test-profile endurance --load-test-duration 60 --range 1 50

# Load Testing: display the ASCII results dashboard with latency histogram and performance grade
python main.py --load-test --load-test-dashboard --range 1 100

# Load Testing: bottleneck analysis -- discover which subsystems are slowing things down (it's not the modulo)
python main.py --load-test --load-test-bottlenecks --range 1 50

# Load Testing: validate against SLA targets
python main.py --load-test --load-test-sla --range 1 100

# Load Testing: export results as JSON for trend analysis
python main.py --load-test --load-test-report ./load_test_results.json --range 1 50

# Full load testing stack: stress test + dashboard + bottlenecks + SLA (peak performance engineering)
python main.py --load-test --load-test-profile stress --load-test-dashboard --load-test-bottlenecks --load-test-sla --range 1 50

# Peak enterprise: load test + metrics + tracing + compliance (every virtual user is a regulated evaluator)
python main.py --load-test --load-test-dashboard --metrics --metrics-dashboard --trace --compliance --compliance-dashboard --range 1 20

# Audit Dashboard: aggregate all subsystem events into a six-pane real-time terminal view
python main.py --audit-dashboard --range 1 50

# Audit Dashboard with anomaly detection threshold tuning (lower = more alerts)
python main.py --audit-dashboard --audit-anomaly-threshold 1.5 --range 1 100

# Audit Dashboard: display temporal correlation insights across subsystems
python main.py --audit-dashboard --audit-correlations --range 1 50

# Audit Dashboard: capture a dashboard snapshot for post-incident review
python main.py --audit-dashboard --audit-snapshot --range 1 30

# Audit Dashboard: replay a saved snapshot for blameless post-mortem analysis
python main.py --audit-dashboard --audit-replay ./snapshot_20260322_143207.json

# Audit Dashboard: filter events by subsystem and severity
python main.py --audit-dashboard --audit-filter "subsystem:blockchain AND severity:>=WARNING" --range 1 50

# Headless event streaming: output unified events as NDJSON for external tool integration
python main.py --audit-stream --range 1 100

# Audit Dashboard + chaos: watch anomaly detection fire as chaos faults cascade through subsystems
python main.py --audit-dashboard --audit-correlations --chaos --chaos-level 3 --range 1 30

# Full observability stack: audit dashboard + metrics + tracing + SLA + health (the NOC experience)
python main.py --audit-dashboard --audit-correlations --audit-insights --metrics --metrics-dashboard --trace --sla --sla-dashboard --health --health-dashboard --range 1 20

# Peak enterprise: audit dashboard + compliance + RBAC + cost tracking (every event is a regulated observation)
python main.py --audit-dashboard --audit-correlations --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --cost-tracking --cost-dashboard --range 1 15

# GitOps: enable configuration-as-code with in-memory Git and reconciliation
python main.py --gitops --range 1 30

# GitOps: commit the current configuration with a descriptive message
python main.py --gitops --gitops-commit "Tune blockchain difficulty for Q2 performance targets" --range 1 20

# GitOps: create a branch for parallel configuration experiments
python main.py --gitops --gitops-branch experiment/harder-mining --range 1 20

# GitOps: merge a branch back into main (three-way merge with conflict detection)
python main.py --gitops --gitops-merge experiment/harder-mining --range 1 30

# GitOps: diff the current config against the last committed state
python main.py --gitops --gitops-diff --range 1 20

# GitOps: view the configuration commit history
python main.py --gitops --gitops-log --range 1 20

# GitOps: propose a configuration change through the five-gate pipeline
python main.py --gitops --gitops-propose "Increase ML learning rate for faster convergence" --range 1 30

# GitOps: approve a pending change proposal
python main.py --gitops --gitops-approve proposal-001 --range 1 20

# GitOps: apply an approved proposal (commits and triggers reconciliation)
python main.py --gitops --gitops-apply proposal-001 --range 1 20

# GitOps: run desired-state reconciliation (detect drift between committed and running config)
python main.py --gitops --gitops-reconcile --range 1 30

# GitOps: check for configuration drift without auto-correcting
python main.py --gitops --gitops-drift --range 1 20

# GitOps: rollback to a previous commit (revert and reconcile)
python main.py --gitops --gitops-rollback abc123 --range 1 30

# GitOps: validate proposed changes against organizational policies
python main.py --gitops --gitops-policy-check --range 1 20

# GitOps: ASCII dashboard with branch state, pending proposals, drift status, and commit history
python main.py --gitops --gitops-dashboard --range 1 50

# Full GitOps stack: config governance + metrics + tracing + compliance (peak change management)
python main.py --gitops --gitops-dashboard --metrics --metrics-dashboard --trace --compliance --compliance-dashboard --range 1 20

# Peak enterprise: GitOps + RBAC + SLA + cost tracking (every config change is a regulated governance event)
python main.py --gitops --gitops-dashboard --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --cost-dashboard --range 1 15

# Formal Verification: prove all four properties (totality, determinism, completeness, correctness)
python main.py --verify

# Formal Verification: verify a single property with proof tree
python main.py --verify-property correctness --proof-tree

# Formal Verification: full dashboard with QED status and proof obligations
python main.py --verify --verify-dashboard

# Formal Verification: verify determinism and display the Gentzen-style proof tree
python main.py --verify-property determinism --proof-tree

# Formal Verification: full stack with proof tree and dashboard (peak mathematical rigor)
python main.py --verify --proof-tree --verify-dashboard

# FBaaS: enable FizzBuzz-as-a-Service with default Free tier (10 evaluations/day, watermarked)
python main.py --fbaas --range 1 20

# FBaaS: Pro tier tenant with 1,000 daily evaluations and no watermark
python main.py --fbaas --fbaas-tenant "Acme Corp" --fbaas-tier pro --range 1 50

# FBaaS: Enterprise tier with unlimited evaluations, all features unlocked
python main.py --fbaas --fbaas-tenant "MegaCorp Industries" --fbaas-tier enterprise --range 1 100

# FBaaS: display the ASCII onboarding wizard for a new tenant
python main.py --fbaas --fbaas-tenant "Startup LLC" --fbaas-tier free --fbaas-onboard

# FBaaS: display the SaaS dashboard with MRR, tenant list, and usage metrics
python main.py --fbaas --fbaas-dashboard --range 1 30

# FBaaS: display the simulated Stripe billing event log
python main.py --fbaas --fbaas-tenant "BigSpender Inc" --fbaas-tier enterprise --fbaas-billing-log --range 1 50

# FBaaS: display per-tenant usage and remaining daily quota
python main.py --fbaas --fbaas-usage --range 1 20

# FBaaS + compliance + cost tracking: peak SaaS governance (the invoices will be glorious)
python main.py --fbaas --fbaas-tier enterprise --fbaas-dashboard --compliance --cost-tracking --cost-dashboard --range 1 30

# Peak enterprise: FBaaS + full stack (every subsystem, every tier, every dashboard)
python main.py --fbaas --fbaas-tier enterprise --fbaas-dashboard --sla --sla-dashboard --metrics --metrics-dashboard --trace --compliance --range 1 20

# Time-Travel Debugger: enable timeline capture and navigate evaluation history
python main.py --time-travel --range 1 30

# Time-Travel Debugger: set a breakpoint on FizzBuzz classifications and navigate to it
python main.py --time-travel --time-travel-break "classification == FizzBuzz" --range 1 50

# Time-Travel Debugger: step backward through evaluation history
python main.py --time-travel --time-travel-step-back --range 1 20

# Time-Travel Debugger: goto a specific evaluation by sequence number
python main.py --time-travel --time-travel-goto 15 --range 1 30

# Time-Travel Debugger: diff two snapshots side-by-side
python main.py --time-travel --time-travel-diff 5 15 --range 1 30

# Time-Travel Debugger: display the ASCII timeline strip with breakpoint markers
python main.py --time-travel --time-travel-timeline --range 1 50

# Time-Travel Debugger: reverse-continue to find the previous breakpoint hit
python main.py --time-travel --time-travel-break "number == 15" --time-travel-reverse-continue --range 1 100

# Full temporal stack: time-travel + event sourcing + tracing + metrics (peak temporal debugging)
python main.py --time-travel --time-travel-timeline --event-sourcing --trace --metrics --metrics-dashboard --range 1 30

# Peak enterprise: time-travel + compliance + RBAC + SLA + cost tracking (every evaluation is a navigable, regulated temporal event)
python main.py --time-travel --time-travel-timeline --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --range 1 20

# Bytecode VM: compile FizzBuzz rules to FBVM bytecode and execute via the custom VM
python main.py --vm --range 1 30

# Bytecode VM: display the disassembled bytecode listing (human-readable FBVM instructions)
python main.py --vm --vm-disasm --range 1 15

# Bytecode VM: enable instruction-level execution tracing (watch the fetch-decode-execute loop)
python main.py --vm --vm-trace --range 1 10

# Bytecode VM: display the ASCII VM dashboard with register file, disassembly, and execution stats
python main.py --vm --vm-dashboard --range 1 20

# Bytecode VM + tracing: observe the VM execution through the distributed tracing subsystem
python main.py --vm --vm-dashboard --trace --range 1 15

# Full VM stack: bytecode compilation + dashboard + metrics + tracing (peak instruction-level observability)
python main.py --vm --vm-dashboard --vm-trace --metrics --metrics-dashboard --trace --range 1 20

# Peak enterprise: VM + compliance + RBAC + SLA + cost tracking (every opcode is a regulated instruction)
python main.py --vm --vm-dashboard --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --range 1 15

# Query Optimizer: enable cost-based plan selection for every evaluation
python main.py --optimize --range 1 30

# Query Optimizer: EXPLAIN a specific number (show the chosen plan without executing)
python main.py --optimize --explain 15

# Query Optimizer: EXPLAIN ANALYZE (execute and compare estimated vs actual costs)
python main.py --optimize --explain-analyze 15

# Query Optimizer: override the optimizer with hints (force ML inference path)
python main.py --optimize --optimizer-hints "FORCE_ML" --range 1 20

# Query Optimizer: exclude blockchain verification from all plans
python main.py --optimize --optimizer-hints "NO_BLOCKCHAIN,PREFER_CACHE" --range 1 50

# Query Optimizer: display the ASCII optimizer dashboard after execution
python main.py --optimize --optimizer-dashboard --range 1 100

# Full optimizer stack: optimizer + dashboard + metrics + tracing (peak query planning observability)
python main.py --optimize --optimizer-dashboard --metrics --metrics-dashboard --trace --range 1 30

# Peak enterprise: optimizer + compliance + RBAC + SLA + cost tracking (every plan is a regulated decision)
python main.py --optimize --optimizer-dashboard --compliance --compliance-dashboard --user alice --role FIZZBUZZ_SUPERUSER --sla --sla-dashboard --cost-tracking --range 1 15
```

## CLI Options

```
--range START END     Numeric range to evaluate (default: 1-100)
--format FORMAT       Output format: plain, json, xml, csv
--strategy STRATEGY   Evaluation strategy: standard, chain_of_responsibility, parallel_async, machine_learning
--config PATH         Path to YAML configuration file
--verbose, -v         Enable verbose event logging
--debug               Enable debug-level logging
--async               Use asynchronous evaluation engine
--no-banner           Suppress the startup banner
--no-summary          Suppress the session summary
--metadata            Include metadata in output (JSON only)
--blockchain          Enable blockchain-based immutable audit ledger
--mining-difficulty N Proof-of-work difficulty (default: 2)
--locale LOCALE       Locale for internationalized output (en, de, fr, ja, tlh, sjn, qya)
--list-locales        Display available locales and exit
--circuit-breaker     Enable circuit breaker with exponential backoff
--circuit-status      Display circuit breaker status dashboard after execution
--event-sourcing      Enable Event Sourcing with CQRS for append-only audit logging
--replay              Replay all events from the event store to rebuild projections
--temporal-query SEQ  Reconstruct FizzBuzz state at a specific event sequence number
--trace               Enable distributed tracing with ASCII waterfall output (alias for --otel --otel-export console)
--trace-json          Enable distributed tracing with OTLP JSON export (alias for --otel --otel-export otlp)
--user USERNAME       Authenticate as the specified user (trust-mode, no token required)
--role ROLE           Assign RBAC role: ANONYMOUS, FIZZ_READER, BUZZ_ADMIN, NUMBER_AUDITOR, FIZZBUZZ_SUPERUSER
--token TOKEN         Authenticate using an Enterprise FizzBuzz Platform HMAC-SHA256 token
--chaos               Enable Chaos Engineering fault injection (the monkey awakens)
--chaos-level N       Chaos severity level 1-5 (1=gentle breeze, 5=apocalypse)
--gameday SCENARIO    Run a Game Day chaos scenario (modulo_meltdown, confidence_crisis, slow_burn, total_chaos)
--post-mortem         Generate a post-mortem incident report after chaos execution
--feature-flags      Enable the Feature Flag / Progressive Rollout subsystem
--flag NAME=VALUE    Override a feature flag (e.g. --flag wuzz_rule_experimental=true)
--list-flags         Display all registered feature flags and exit
--sla                Enable SLA Monitoring with PagerDuty-style alerting
--sla-dashboard      Display the SLA monitoring dashboard after execution
--on-call            Display the current on-call status and escalation chain
--cache              Enable the in-memory caching layer for FizzBuzz evaluation results
--cache-policy POLICY  Cache eviction policy: lru, lfu, fifo, dramatic_random (default: lru)
--cache-size N       Maximum number of cache entries (default: 1024)
--cache-stats        Display the cache statistics dashboard after execution
--cache-warm         Pre-populate the cache before execution (defeats the purpose of caching)
--repository BACKEND Repository backend: memory, sqlite, filesystem (default: memory)
--db-path PATH       Path to SQLite database file (only with --repository sqlite)
--results-dir PATH   Path to results directory (only with --repository filesystem)
--migrate            Apply all pending database migrations to the in-memory schema (it won't persist)
--migrate-status     Display the migration status dashboard for the ephemeral database
--migrate-rollback N Rollback the last N migrations (default: 1). Undo what was never permanent
--migrate-seed       Generate FizzBuzz seed data using the FizzBuzz engine (the ouroboros)
--health             Enable Kubernetes-style health check probes for the FizzBuzz platform
--liveness           Run the liveness probe (canary evaluation: can FizzBuzz still FizzBuzz?)
--readiness          Run the readiness probe (are all subsystems initialized and not panicking?)
--startup-probe      Run the startup probe (has the boot sequence completed, or are we still mining the genesis block?)
--health-dashboard   Display the comprehensive health check dashboard after execution
--self-heal          Enable the self-healing manager (automated recovery with exponential backoff)
--metrics            Enable Prometheus-style metrics collection for FizzBuzz evaluation
--metrics-export     Export all metrics in Prometheus text exposition format after execution
--metrics-dashboard  Display the ASCII Grafana metrics dashboard after execution
--webhooks           Enable the Webhook Notification System for event-driven FizzBuzz telemetry
--webhook-url URL    Register a webhook endpoint URL (can be specified multiple times)
--webhook-events EVENTS  Comma-separated list of event types to subscribe to (default: all)
--webhook-secret SECRET  HMAC-SHA256 secret for signing webhook payloads (default: from config)
--webhook-test       Send a test webhook to all registered endpoints and exit
--webhook-log        Display the webhook delivery log after execution
--webhook-dlq        Display the Dead Letter Queue contents after execution
--message-queue        Enable the Kafka-Style Message Queue & Event Bus with partitioned topics and consumer groups
--mq-topics            Display all topics with partition counts, message throughput, and retention policy
--mq-lag               Display consumer lag across all consumer groups and partitions with ASCII lag graphs
--mq-dashboard         Display the ASCII Message Queue dashboard with topic throughput, consumer lag, and rebalance history
--mq-replay TOPIC OFFSET  Replay messages from a specific topic starting at the given offset
--mq-partitions N      Configure the number of partitions per topic (default: 4)
--mq-consumer-groups   Display all consumer groups with partition assignments and committed offsets
--mq-schema-registry   Display the schema registry with registered message schemas and version history
--service-mesh       Enable the Service Mesh Simulation: decompose FizzBuzz into 7 microservices with sidecar proxies
--mesh-topology      Display the ASCII service mesh topology diagram after execution
--mesh-latency       Enable simulated network latency injection between mesh services
--mesh-packet-loss   Enable simulated packet loss between mesh services
--canary             Enable canary deployment routing (v2 DivisibilityService uses multiplication instead of modulo)
--hot-reload         Enable Configuration Hot-Reload with Single-Node Raft Consensus (watches config.yaml for changes)
--hot-reload-interval MS  Poll interval in milliseconds for config file changes (default: 500)
--config-validate    Validate config.yaml against the configuration schema and exit
--config-diff        Display the diff between current and on-disk configuration
--config-history     Display the event-sourced configuration change history
--rate-limit         Enable Rate Limiting & API Quota Management for FizzBuzz evaluations
--rate-limit-rpm N   Maximum FizzBuzz evaluations per minute (default: 60)
--rate-limit-algo ALGO  Rate limiting algorithm: token_bucket, sliding_window, fixed_window (default: token_bucket)
--rate-limit-dashboard  Display the ASCII rate limit dashboard with per-bucket fill levels and quota utilization
--rate-limit-reserve N  Pre-reserve N evaluation slots before execution (capacity planning for FizzBuzz)
--rate-limit-burst-credits  Enable burst credit carryover from unused quota (loyalty rewards for patient evaluators)
--compliance           Enable Compliance & Regulatory Framework (SOX/GDPR/HIPAA) for FizzBuzz evaluations
--compliance-regime REGIME  Compliance regime: sox, gdpr, hipaa, all (default: all)
--gdpr-consent NUMBER  Grant GDPR consent for a specific number (data subject) before evaluation
--gdpr-forget NUMBER   Exercise GDPR right-to-erasure for a number and witness THE COMPLIANCE PARADOX
--compliance-dashboard Display the ASCII compliance dashboard with Bob's stress level after execution
--compliance-report    Generate a multi-page ASCII compliance audit report
--compliance-approve ID  Manually approve a quarantined evaluation (requires Chief Compliance Officer status, which is Bob)
--hipaa-minimum-necessary  Enable HIPAA Minimum Necessary Rule: restrict information flow between services
--cost-tracking            Enable FinOps Cost Tracking & Chargeback Engine for FizzBuzz evaluations
--cost-invoice ID          Generate an itemized ASCII invoice for a specific evaluation (or "last" for the most recent)
--cost-report              Generate a monthly cost report with spending breakdown by subsystem, strategy, and day-of-week
--cost-budget AMOUNT       Set a spending budget in FizzBucks; fires alerts when spending exceeds the threshold
--cost-anomaly             Run the cost anomaly detector to flag unusual spending patterns
--cost-savings-plan        Display the Savings Plan simulator with 1-year and 3-year commitment comparisons
--cost-dashboard           Display the ASCII FinOps cost dashboard with spending sparklines and budget burn-down
--cost-currency CURRENCY   Display costs in fizzbucks or usd (default: fizzbucks). Exchange rate fluctuates with cache hit ratio
--wal-enable               Enable Write-Ahead Logging for every repository mutation (zero-loss durability, in RAM)
--backup-now               Create an immediate snapshot of the full FizzBuzz application state
--backup-list              Display all available backup snapshots with integrity checksums and component manifests
--backup-retention POLICY  Backup retention policy: standard (24h/7d/4w/12m) or minimal (default: standard)
--restore ID               Restore application state from a specific snapshot ID (or "latest")
--restore-point-in-time TS Reconstruct exact application state at a specific ISO-8601 timestamp via WAL replay
--dr-drill                 Run a Disaster Recovery drill: corrupt subsystems and measure recovery time against RTO
--dr-report                Display the post-drill analysis with RTO/RPO compliance, recovery metrics, and recommendations
--ab-test                  Enable the A/B Testing Framework for running controlled experiments across evaluation strategies
--experiment NAME          Specify the experiment name (e.g., ml_vs_modulo, chain_vs_standard)
--experiment-list          Display all registered experiments with their states, traffic allocation, and sample counts
--experiment-results NAME  Display real-time per-variant metrics with confidence intervals and statistical significance for a named experiment
--experiment-dashboard     Display the ASCII A/B testing dashboard with per-group metrics, p-values, and winner/loser verdicts
--experiment-traffic PCT   Set the treatment group traffic allocation percentage (default: 10)
--experiment-stop NAME     Manually stop a running experiment and preserve results for analysis
--experiment-report NAME   Generate a comprehensive post-experiment statistical analysis report with methodology, results, and recommendations
--vault                    Enable the Secrets Management Vault with Shamir's Secret Sharing and automatic unsealing
--vault-unseal SHARE       Provide an unseal share (hex format "index:value") to contribute toward the 3-of-5 quorum
--vault-seal               Seal the vault, suspending all FizzBuzz evaluation until re-unsealed via ceremony
--vault-status             Display vault seal status, secret count, and rotation schedule
--vault-get PATH           Retrieve a secret from the vault at the specified path (e.g., secret/fizzbuzz/blockchain/difficulty)
--vault-set PATH VALUE     Store a secret in the vault at the specified path with the given value
--vault-rotate             Trigger immediate rotation of all secrets on their configured schedule
--vault-scan               Run the AST-based secret scanner across all Python source files
--vault-audit-log          Display the immutable vault audit log with accessor identity and access verdicts
--vault-dashboard          Display the ASCII vault dashboard with seal status, secret inventory, rotation schedule, and audit trail
--pipeline                 Enable the Data Pipeline & ETL Framework (Extract-Validate-Transform-Enrich-Load)
--pipeline-run             Execute the full pipeline run with all configured stages
--pipeline-dag             Display the DAG visualization showing stage dependencies and execution order
--pipeline-schedule CRON   Schedule recurring pipeline runs with cron-like expressions (e.g., "*/5 * * * *")
--pipeline-backfill        Retroactively re-process historical results with updated pipeline definitions
--pipeline-lineage ID      Display the full data lineage provenance chain for a specific result ID
--pipeline-stages          Display all configured pipeline stages with retry policies and timeout settings
--pipeline-dashboard       Display the ASCII pipeline dashboard with stage durations, throughput, and failure rates
--pipeline-checkpoint      Enable checkpoint/restart for pipeline resumption after mid-pipeline failures
--pipeline-version N       Run a specific pipeline version (for historical comparison)
--openapi                  Display the ASCII Swagger UI for the fictional Enterprise FizzBuzz REST API (47 endpoints, 0 servers)
--openapi-spec             Export the complete OpenAPI 3.1 specification in JSON format (pipe to file for 3,000+ lines of fictional API documentation)
--openapi-yaml             Export the complete OpenAPI 3.1 specification in YAML format (for teams who believe indentation is a personality trait)
--swagger-ui               Display the ASCII Swagger UI (alias for --openapi, because nobody remembers which flag they used last time)
--openapi-dashboard        Display the OpenAPI specification statistics dashboard with endpoint counts, method distribution, and exception mapping coverage
--api-gateway              Enable the API Gateway with versioned routing, request/response transformation, and API key management
--api-version VERSION      API version to route through: v1 (deprecated), v2, v3 (default: v3, the premium tier with full subsystem orchestra)
--api-key KEY              Authenticate with the gateway using a specific API key
--api-key-generate         Generate a new cryptographically secure API key and exit
--api-key-rotate           Rotate all active API keys (all zero external consumers must update immediately)
--api-gateway-dashboard    Display the ASCII API Gateway dashboard with request volume, active keys, and deprecation countdowns
--api-replay               Replay recorded requests from the gateway's append-only request journal
--api-hateoas              Enable HATEOAS link enrichment in every response (Richardson Maturity Level 4, which doesn't exist but should)
--deploy                   Enable the Blue/Green Deployment Simulation with full six-phase ceremony
--deploy-provision-green   Provision the green environment (create slot, configure strategy, warm cache)
--deploy-smoke-test        Run smoke tests against canary numbers (3, 5, 15, 42, 97) in the green environment
--deploy-shadow            Enable shadow traffic routing: duplicate requests to both environments and compare results
--deploy-cutover           Atomically switch traffic from blue to green (a single variable assignment, logged as 47 events)
--deploy-bake SECONDS      Monitor the green environment for a configurable bake period with auto-rollback on degradation
--deploy-rollback          Instantly revert traffic from green back to blue with full state restoration
--deploy-decommission      Archive the old environment's state and deallocate resources (gc.collect() with a press release)
--deploy-dashboard         Display the ASCII deployment dashboard with environment health, cutover history, and shadow diffs
--deploy-history           Display deployment history with phase timestamps and approval signatures
--deploy-diff              Display configuration differences between the blue and green environments
--graph-db                 Enable the Graph Database: map divisibility relationships between integers as a property graph with centrality analysis and community detection
--graph-query QUERY        Execute a CypherLite query against the FizzBuzz graph (e.g. "MATCH (n:Number) WHERE n.value > 90 RETURN n")
--graph-visualize          Display an ASCII visualization of the FizzBuzz relationship graph using force-directed layout
--graph-dashboard          Display the Graph Database analytics dashboard with centrality rankings, community detection, and isolation awards
--genetic                  Enable the Genetic Algorithm for evolutionary FizzBuzz rule discovery through natural selection
--genetic-generations N    Number of evolutionary generations to run (default: 500)
--genetic-population N     Population size for the genetic algorithm (default: 200)
--genetic-fitness          Display the multi-objective fitness breakdown for the fittest chromosome
--genetic-hall-of-fame     Display the all-time top chromosomes with fitness scores and discovery generation
--genetic-dashboard        Display the ASCII evolution dashboard with fitness charts, diversity gauges, and Hall of Fame
--genetic-seed-bank PATH   Save/load population snapshots for experiment resumption and cross-run comparison
--genetic-extinction       Enable mass extinction events when population diversity drops below threshold
--genetic-preview          Display the fittest individual's FizzBuzz output for the evaluation range
--nlq QUERY                Execute a natural language query against the FizzBuzz platform (e.g., "Is 15 FizzBuzz?" or "How many Fizzes below 50?")
--nlq-interactive          Launch an interactive NLQ session with query history and autocomplete
--nlq-batch FILE           Process a file of natural-language questions in batch mode, outputting structured JSON answers
--nlq-dashboard            Display the ASCII NLQ dashboard with query history, intent distribution, confidence metrics, and "hardest query" leaderboard
--nlq-confidence FLOAT     Minimum confidence threshold for intent classification (default: 0.6). Queries below this trigger the ambiguity resolver
--nlq-history              Display the session query history with intent classifications and response times
--load-test                Enable the Load Testing Framework for stress-testing the FizzBuzz evaluation pipeline under simulated concurrent workloads
--load-test-profile PROFILE  Workload profile: smoke (5 VUs, quick check), load (50 VUs, normal conditions), stress (ramp until failure), spike (burst at T=60s), endurance (30 VUs, extended duration)
--load-test-vus N          Number of virtual users to spawn (overrides profile default)
--load-test-duration N     Load test duration in seconds (overrides profile default)
--load-test-dashboard      Display the ASCII load test results dashboard with latency histogram, percentile table, throughput metrics, and performance grade
--load-test-report PATH    Export load test results as structured JSON for trend analysis and CI/CD integration
--load-test-sla            Validate observed metrics against configured SLA targets (p99 latency, error rate, throughput)
--load-test-bottlenecks    Run the bottleneck analyzer to identify which subsystems contribute most to total evaluation latency
--audit-dashboard          Enable the Unified Audit Dashboard: aggregate events from all subsystems into a six-pane real-time ASCII terminal view
--audit-stream             Enable headless event streaming: output the unified event stream as newline-delimited JSON to stdout
--audit-filter EXPR        Filter dashboard events by expression (e.g., "subsystem:blockchain AND severity:>=WARNING")
--audit-snapshot           Capture the current dashboard state as a timestamped JSON document for post-incident review
--audit-replay SNAPSHOT    Load a saved dashboard snapshot and render it as if it were live for post-mortem analysis
--audit-anomaly-threshold FLOAT  Z-score threshold for anomaly detection (default: 2.0). Higher = fewer alerts, lower = more paranoia
--audit-correlations       Display temporal correlation insights with confidence scores across subsystem event streams
--audit-insights           Display synthesized human-readable insights with recommended actions based on detected patterns
--gitops                   Enable the GitOps Configuration-as-Code Simulator with in-memory Git, change proposals, and reconciliation
--gitops-commit MESSAGE    Commit the current configuration state with a descriptive message (SHA-256 hash-chained)
--gitops-branch NAME       Create a named branch for parallel configuration experiments
--gitops-merge BRANCH      Merge a branch into the current branch with three-way merge and conflict detection
--gitops-diff              Display a structural diff between the current config and the last committed state
--gitops-log               Display the chronological configuration commit history with messages, authors, and hashes
--gitops-propose DESC      Submit a configuration change proposal through the five-gate pipeline (schema, policy, dry-run, approval, apply)
--gitops-approve ID        Approve a pending change proposal (auto-approved in single-operator mode, because you are also the reviewer)
--gitops-apply ID          Apply an approved proposal: commit to config history and trigger reconciliation
--gitops-reconcile         Run desired-state reconciliation: compare committed config against running config and enforce or detect drift
--gitops-rollback HASH     Revert to a previous commit's configuration state and trigger immediate reconciliation
--gitops-drift             Display configuration drift report: structural diff between committed (desired) and running (actual) config
--gitops-dashboard         Display the ASCII GitOps dashboard with branch/commit state, pending proposals, drift status, and commit graph
--gitops-policy-check      Validate the current configuration against organizational policy rules with PASS/FAIL/WARN verdicts
--verify                   Run the Formal Verification engine: prove totality, determinism, completeness, and correctness via structural induction
--verify-property PROPERTY Verify a single property: totality, determinism, completeness, or correctness
--proof-tree               Display the Gentzen-style natural deduction proof tree for the induction proof
--verify-dashboard         Display the Formal Verification ASCII dashboard with QED status and proof obligations
--fbaas                    Enable FizzBuzz-as-a-Service (FBaaS): multi-tenant SaaS simulation with subscription tiers, usage metering, and billing
--fbaas-tenant NAME        Tenant organization name for FBaaS onboarding (default: "Default Tenant")
--fbaas-tier TIER          Subscription tier: free, professional, enterprise (default: free). "pro" is accepted as alias for "professional". Determines daily quota and feature access
--fbaas-dashboard          Display the ASCII FBaaS dashboard with MRR, tenant list, usage metrics, and billing log
--fbaas-onboard            Display the ASCII onboarding wizard for the current tenant
--fbaas-billing-log        Display the simulated Stripe billing event log
--fbaas-usage              Display per-tenant usage statistics and remaining daily quota
--time-travel              Enable the Time-Travel Debugger: capture evaluation snapshots and enable bidirectional timeline navigation
--time-travel-break EXPR   Set a conditional breakpoint expression (e.g., "classification == FizzBuzz", "number == 15", "latency > 1.0")
--time-travel-goto N       Navigate the timeline cursor to evaluation sequence number N
--time-travel-step-back    Step the timeline cursor backward by one evaluation
--time-travel-diff A B     Display a field-by-field diff between snapshots at positions A and B
--time-travel-timeline     Display the ASCII timeline strip with breakpoint markers (B), cursor position (>), and anomalies (!)
--time-travel-reverse-continue  Navigate backward through the timeline until a breakpoint condition is met
--time-travel-snapshot N   Inspect the complete system state snapshot at evaluation sequence number N
--vm                       Enable the Custom Bytecode VM (FBVM): compile FizzBuzz rules to bytecode and execute via the 20-opcode virtual machine
--vm-disasm                Display the disassembled bytecode listing with human-readable FBVM instructions after compilation
--vm-trace                 Enable instruction-level execution tracing: log every fetch-decode-execute cycle with register state
--vm-dashboard             Display the ASCII VM dashboard with register file snapshot, disassembly, execution statistics, and compilation metadata
--optimize                 Enable the cost-based Query Optimizer for FizzBuzz evaluation (because modulo deserves a query planner)
--explain N                Display the PostgreSQL-style EXPLAIN plan for evaluating number N (without executing)
--explain-analyze N        Display EXPLAIN ANALYZE for number N (execute and compare estimated vs actual costs)
--optimizer-hints HINTS    Comma-separated optimizer hints: FORCE_ML, PREFER_CACHE, NO_BLOCKCHAIN, NO_ML
--optimizer-dashboard      Display the Query Optimizer ASCII dashboard after execution
--paxos                    Enable Distributed Paxos Consensus: route every evaluation through a multi-node consensus round
--paxos-nodes N            Number of simulated Paxos nodes in the cluster (default: 5, minimum: 3 for quorum)
--paxos-byzantine          Enable Byzantine Fault Tolerance mode: one node lies about its result, requiring 3f+1 honest nodes
--paxos-partition          Enable network partition simulation: randomly drop messages between node groups
--paxos-show-votes         Display per-node evaluation votes and quorum breakdown for each decree
--paxos-dashboard          Display the ASCII Consensus Dashboard with voting records, ballot numbers, quorum status, and Byzantine fault tallies
--quantum                  Enable the Quantum Computing Simulator: evaluate FizzBuzz divisibility via Shor's algorithm on simulated qubits
--quantum-qubits N         Number of qubits in the quantum register (default: 8, max: 16 -- at which point the state vector has 65,536 complex entries)
--quantum-shots N          Number of measurement shots for majority voting (default: 100). More shots = higher confidence, more CPU time wasted
--quantum-noise RATE       Decoherence rate for the noise model (0.0 = perfect, 1.0 = random number generator). Default: 0.0
--quantum-circuit          Display the ASCII quantum circuit diagram after evaluation
--quantum-dashboard        Display the Quantum Computing dashboard with state amplitudes, gate counts, measurement histograms, and Quantum Advantage Ratio
--compile-to TARGET        Cross-compile FizzBuzz rules to a target language: c (ANSI C89), rust (idiomatic Rust), wat (WebAssembly Text format)
--compile-out PATH         Output path for the generated source file (default: stdout)
--compile-optimize         Enable optimization passes on the IR before code generation (constant folding, dead code elimination)
--compile-verify           Run round-trip verification: compare generated code output against Python reference for numbers 1-100
--compile-preview          Display ASCII side-by-side view of rule definition, IR, and generated target code
--compile-dashboard        Display the cross-compiler ASCII dashboard with compilation stats, code size, overhead factor, and verification results
--federated                Enable Federated Learning: collaboratively train a shared ML model across multiple simulated FizzBuzz instances
--fed-nodes N              Number of federated FizzBuzz nodes (default: 5, range: 3-10)
--fed-rounds N             Number of federation communication rounds (default: 10)
--fed-topology TOPOLOGY    Federation topology: star (central aggregator), ring (peer-to-peer gradient passing), mesh (fully-connected, quadratic messages, maximum enterprise)
--fed-epsilon FLOAT        Differential privacy epsilon (default: 1.0). Lower = more privacy, more noise, less accuracy. Higher = less privacy, less noise, more accuracy
--fed-strategy STRATEGY    Aggregation strategy: fedavg (Federated Averaging), fedprox (proximal regularization), fedma (model averaging with neuron matching)
--fed-dashboard            Display the ASCII Federated Learning dashboard with federation topology, per-node accuracy, global convergence, privacy budget, and model consensus
--ontology                 Enable the Knowledge Graph & Domain Ontology: model FizzBuzz as RDF triples with OWL class hierarchy, forward-chaining inference, and semantic reasoning
--sparql QUERY             Execute a FizzSPARQL query against the FizzBuzz ontology (e.g. --sparql "SELECT ?n WHERE { ?n fizz:hasClassification fizz:Fizz } LIMIT 10")
--ontology-dashboard       Display the Knowledge Graph & Domain Ontology ASCII dashboard with triple store statistics, class hierarchy, inference metrics, and ontology consistency status
--self-modify              Enable the Self-Modifying Code Engine: rules represented as mutable ASTs that propose, evaluate, and accept or revert stochastic mutations at runtime
--self-modify-rate FLOAT   Mutation probability per evaluation (default: 0.1). Higher = more mutations proposed, more evolutionary churn, more excitement
--self-modify-dashboard    Display the ASCII Self-Modification Dashboard with current AST visualization, mutation history, fitness trajectory, generation counter, and safety guard status
--chatbot QUESTION         Ask the regulatory compliance chatbot a GDPR/SOX/HIPAA question about FizzBuzz operations (e.g. --chatbot "Is erasing FizzBuzz results GDPR compliant?")
--chatbot-interactive      Start an interactive compliance chatbot REPL for ongoing regulatory consultations with conversation memory and follow-up context resolution
--chatbot-dashboard        Display the compliance chatbot session dashboard with query count, verdict distribution, intent statistics, and Bob McFizzington's editorial commentary
--kernel                   Enable the FizzBuzz OS Kernel: process scheduling, virtual memory management, interrupts, and system calls for modulo arithmetic
--kernel-scheduler ALGO    Kernel process scheduler algorithm: rr (Round Robin), priority (Priority Preemptive), cfs (Completely Fair Scheduler). Default: rr
--kernel-dashboard         Display the FizzBuzz OS Kernel ASCII dashboard with process table, memory map, interrupt log, and scheduler statistics
--p2p                      Enable the Peer-to-Peer Gossip Network: disseminate FizzBuzz results across simulated nodes via SWIM failure detection, Kademlia DHT, and epidemic rumor propagation
--p2p-nodes N              Number of P2P cluster nodes (default: 7). Each node gets a 160-bit SHA-1 node ID and its own classification store
--p2p-dashboard            Display the P2P Gossip Network ASCII dashboard with network topology, gossip statistics, DHT routing table, and Merkle anti-entropy sync status
--bob                      Enable the FizzBob Operator Cognitive Load Modeling Engine: model Bob McFizzington's circadian rhythm, NASA-TLX workload index, alert fatigue, and burnout trajectory as runtime-critical operational metrics
--bob-hours-awake N        Number of hours Bob has been awake (default: computed from --bob-shift-start). Affects circadian alertness score and fatigue accumulation rate
--bob-shift-start HH:MM    Bob's shift start time in 24-hour format (default: 06:00). Used by the circadian model to compute current alertness and fatigue state
--bob-dashboard            Display the FizzBob ASCII dashboard with circadian alertness sparkline, NASA-TLX radar chart, fatigue timeline, burnout countdown, and operator mode status
--approval                 Enable the FizzApproval Multi-Party Approval Workflow Engine: route every evaluation through ITIL-compliant change management with CAB review, COI detection, and Sole Operator Exception handling
--approval-dashboard       Display the FizzApproval ASCII dashboard with request queue, CAB meeting minutes, SOE statistics, policy distribution, and tamper-evident audit trail
--approval-policy TYPE     Approval policy type: unanimous, majority, any_one, weighted, quorum. All resolve to M=1, N=1 (default: unanimous)
--approval-change-type TYPE  ITIL change type classification: standard (pre-approved), normal (full CAB review), emergency (fast-track with post-implementation audit). Default: normal
```

## Environment Variables

All configuration can be overridden via environment variables prefixed with `EFP_`:

```bash
EFP_RANGE_START=1
EFP_RANGE_END=100
EFP_OUTPUT_FORMAT=json
EFP_EVALUATION_STRATEGY=parallel_async
EFP_LOG_LEVEL=DEBUG
EFP_CIRCUIT_BREAKER_ENABLED=true
EFP_LOCALE=tlh
EFP_RBAC_SECRET=my-very-secret-fizzbuzz-signing-key
EFP_EVENT_SOURCING_ENABLED=true
EFP_EVENT_SOURCING_SNAPSHOT_INTERVAL=10
EFP_CHAOS_ENABLED=true
EFP_CHAOS_LEVEL=3
EFP_CHAOS_SEED=42
```

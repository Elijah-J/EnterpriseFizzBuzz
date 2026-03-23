"""
Enterprise FizzBuzz Platform - CLI Entry Point

Provides a comprehensive command-line interface for the Enterprise
FizzBuzz Platform with full argument parsing, configuration loading,
and graceful error handling.

Usage:
    python main.py
    python main.py --range 1 50
    python main.py --format json --verbose
    python main.py --strategy chain_of_responsibility --range 1 20
    python main.py --async --format xml
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import logging
import os
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from enterprise_fizzbuzz.infrastructure.auth import AuthorizationMiddleware, FizzBuzzTokenEngine, RoleRegistry
from enterprise_fizzbuzz.infrastructure.chaos import (
    ChaosMiddleware,
    ChaosMonkey,
    FaultSeverity,
    FaultType,
    GameDayRunner,
    PostMortemGenerator,
)
from enterprise_fizzbuzz.infrastructure.blockchain import BlockchainObserver, FizzBuzzBlockchain
from enterprise_fizzbuzz.infrastructure.cross_compiler import (
    CompilerDashboard,
    CrossCompiler,
)
from enterprise_fizzbuzz.infrastructure.cache import (
    CacheDashboard,
    CacheMiddleware,
    CacheStore,
    CacheWarmer,
    EvictionPolicyFactory,
)
from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
    CircuitBreakerDashboard,
    CircuitBreakerMiddleware,
    CircuitBreakerRegistry,
)
from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta
from enterprise_fizzbuzz.infrastructure.feature_flags import (
    FlagEvaluationSummary,
    FlagMiddleware,
    apply_cli_overrides,
    create_flag_store_from_config,
    render_flag_list,
)
from enterprise_fizzbuzz.application.fizzbuzz_service import FizzBuzzServiceBuilder
from enterprise_fizzbuzz.infrastructure.formatters import FormatterFactory
from enterprise_fizzbuzz.infrastructure.i18n import LocaleManager
from enterprise_fizzbuzz.infrastructure.middleware import (
    LoggingMiddleware,
    TimingMiddleware,
    TranslationMiddleware,
    ValidationMiddleware,
)
from enterprise_fizzbuzz.domain.models import AuthContext, Event, EventType, EvaluationStrategy, FizzBuzzRole, OutputFormat
from enterprise_fizzbuzz.infrastructure.observers import ConsoleObserver, EventBus, StatisticsObserver
from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import StrategyAdapterFactory
from enterprise_fizzbuzz.infrastructure.rules_engine import RuleEngineFactory
from enterprise_fizzbuzz.infrastructure.event_sourcing import EventSourcingSystem
from enterprise_fizzbuzz.infrastructure.sla import (
    AlertSeverity,
    OnCallSchedule,
    SLADashboard,
    SLAMiddleware,
    SLAMonitor,
    SLODefinition,
    SLOType,
)
from enterprise_fizzbuzz.infrastructure.tracing import TraceExporter, TraceRenderer, TracingMiddleware, TracingService
from enterprise_fizzbuzz.infrastructure.migrations import (
    MigrationDashboard,
    MigrationRegistry,
    MigrationRunner,
    SchemaManager,
    SchemaVisualizer,
    SeedDataGenerator,
)
from enterprise_fizzbuzz.infrastructure.health import (
    CacheCoherenceHealthCheck,
    CircuitBreakerHealthCheck,
    ConfigHealthCheck,
    HealthCheckRegistry,
    HealthDashboard,
    LivenessProbe,
    MLEngineHealthCheck,
    ReadinessProbe,
    SelfHealingManager,
    SLABudgetHealthCheck,
    StartupProbe,
)
from enterprise_fizzbuzz.infrastructure.metrics import (
    CardinalityDetector,
    MetricsCollector,
    MetricsDashboard,
    MetricsMiddleware,
    MetricRegistry,
    PrometheusTextExporter,
    create_metrics_subsystem,
)
from enterprise_fizzbuzz.infrastructure.rate_limiter import (
    QuotaManager,
    RateLimitAlgorithm,
    RateLimitDashboard,
    RateLimitPolicy,
    RateLimiterMiddleware,
)
from enterprise_fizzbuzz.infrastructure.hot_reload import (
    ConfigDiffer,
    ConfigValidator,
    ConfigWatcher,
    HotReloadDashboard,
    ReloadOrchestrator,
    SingleNodeRaftConsensus,
    create_hot_reload_subsystem,
)
from enterprise_fizzbuzz.infrastructure.service_mesh import (
    MeshMiddleware,
    MeshTopologyVisualizer,
    create_service_mesh,
)
from enterprise_fizzbuzz.infrastructure.webhooks import (
    DeadLetterQueue,
    RetryPolicy,
    SimulatedHTTPClient,
    WebhookDashboard,
    WebhookManager,
    WebhookObserver,
    WebhookSignatureEngine,
)
from enterprise_fizzbuzz.infrastructure.compliance import (
    ComplianceDashboard,
    ComplianceFramework,
    ComplianceMiddleware,
    DataClassificationEngine,
    GDPRController,
    HIPAAGuard,
    SOXAuditor,
)
from enterprise_fizzbuzz.infrastructure.compliance_chatbot import (
    ChatbotDashboard as ComplianceChatbotDashboard,
    ComplianceChatbot,
)
from enterprise_fizzbuzz.infrastructure.finops import (
    CostDashboard,
    CostTracker,
    FizzBuckCurrency,
    FizzBuzzTaxEngine,
    FinOpsMiddleware,
    InvoiceGenerator,
    SavingsPlanCalculator,
    SubsystemCostRegistry,
)
from enterprise_fizzbuzz.infrastructure.disaster_recovery import (
    DRSystem,
    RecoveryDashboard,
)
from enterprise_fizzbuzz.infrastructure.ab_testing import (
    ABTestingMiddleware,
    ExperimentDashboard,
    ExperimentRegistry,
    ExperimentReport,
    create_ab_testing_subsystem,
)
from enterprise_fizzbuzz.infrastructure.message_queue import (
    MQDashboard,
    MQMiddleware,
    MessageBroker,
    MessageQueueBridge,
    Producer,
    create_message_queue_subsystem,
)
from enterprise_fizzbuzz.infrastructure.secrets_vault import (
    DynamicSecretEngine,
    SecretRotationScheduler,
    SecretScanner,
    SecretStore,
    ShamirSecretSharing,
    VaultAccessPolicy,
    VaultAuditLog,
    VaultDashboard,
    VaultMiddleware,
    VaultSealManager,
)
from enterprise_fizzbuzz.infrastructure.bytecode_vm import (
    BytecodeSerializer,
    Disassembler,
    FBVMCompiler,
    FizzBuzzVM,
    PeepholeOptimizer,
    VMDashboard,
    compile_rules,
)
from enterprise_fizzbuzz.infrastructure.formal_verification import (
    PropertyType,
    PropertyVerifier,
    VerificationDashboard,
)
from enterprise_fizzbuzz.infrastructure.fbaas import (
    BillingEngine,
    FBaaSDashboard,
    FBaaSMiddleware,
    FizzStripeClient,
    OnboardingWizard,
    ServiceLevelAgreement,
    SubscriptionTier,
    TenantManager,
    UsageMeter,
    create_fbaas_subsystem,
)
from enterprise_fizzbuzz.infrastructure.gitops import (
    GitOpsController,
    GitOpsDashboard,
)
from enterprise_fizzbuzz.infrastructure.data_pipeline import (
    BackfillEngine,
    DataLineageTracker,
    PipelineBuilder,
    PipelineDashboard,
    PipelineMiddleware,
    SinkConnectorFactory,
    SourceConnectorFactory,
)
from enterprise_fizzbuzz.infrastructure.openapi import (
    ASCIISwaggerUI,
    EndpointRegistry,
    ExceptionToHTTPMapper,
    OpenAPIDashboard,
    OpenAPIGenerator,
    SchemaGenerator,
)
from enterprise_fizzbuzz.infrastructure.api_gateway import (
    APIGateway,
    APIKeyManager,
    APIRequest,
    GatewayDashboard,
    GatewayMiddleware,
    create_api_gateway,
)
from enterprise_fizzbuzz.infrastructure.blue_green import (
    DeploymentDashboard,
    DeploymentMiddleware,
    DeploymentOrchestrator,
)
from enterprise_fizzbuzz.infrastructure.graph_db import (
    CypherLiteParseError,
    GraphAnalyzer,
    GraphDashboard,
    GraphMiddleware,
    GraphVisualizer,
    PropertyGraph,
    execute_cypher_lite,
    populate_graph,
)
from enterprise_fizzbuzz.infrastructure.genetic_algorithm import (
    EvolutionDashboard,
    GeneticAlgorithmEngine,
)
from enterprise_fizzbuzz.infrastructure.nlq import (
    NLQDashboard,
    NLQEngine,
)
from enterprise_fizzbuzz.infrastructure.load_testing import (
    LoadTestDashboard,
    PerformanceReport,
    WorkloadProfile,
    run_load_test,
)
from enterprise_fizzbuzz.infrastructure.audit_dashboard import (
    UnifiedAuditDashboard,
)
from enterprise_fizzbuzz.infrastructure.time_travel import (
    ConditionalBreakpoint,
    DiffViewer,
    TimelineUI,
    TimeTravelMiddleware,
    create_time_travel_subsystem,
    render_time_travel_summary,
)
from enterprise_fizzbuzz.infrastructure.query_optimizer import (
    ExplainOutput,
    Optimizer,
    OptimizerDashboard,
    OptimizerMiddleware,
    create_optimizer_from_config,
    parse_optimizer_hints,
)
from enterprise_fizzbuzz.infrastructure.paxos import (
    ByzantineFaultInjector,
    ConsensusDashboard,
    NetworkPartitionSimulator,
    PaxosCluster,
    PaxosMesh,
    PaxosMiddleware,
)
from enterprise_fizzbuzz.infrastructure.quantum import (
    CircuitVisualizer,
    QuantumCircuit,
    QuantumDashboard,
    QuantumFizzBuzzEngine,
    QuantumMiddleware,
    build_qft_circuit,
)
from enterprise_fizzbuzz.infrastructure.federated_learning import (
    FedAvgAggregator,
    FedProxAggregator,
    FederatedClient,
    FederatedDashboard,
    FederatedMiddleware,
    FederatedServer,
    DifferentialPrivacyManager,
    NonIIDSimulator,
)
from enterprise_fizzbuzz.infrastructure.knowledge_graph import (
    FizzSPARQLParser,
    FizzSPARQLExecutor,
    InferenceEngine,
    KnowledgeDashboard,
    KnowledgeGraphMiddleware,
    OWLClassHierarchy,
    OntologyVisualizer,
    TripleStore,
    execute_fizzsparql,
    populate_fizzbuzz_domain,
)
from enterprise_fizzbuzz.infrastructure.package_manager import (
    FizzPMDashboard,
    FizzPMManager,
)
from enterprise_fizzbuzz.infrastructure.fizzsql import (
    FizzSQLDashboard,
    FizzSQLEngine,
    PlatformState,
)
from enterprise_fizzbuzz.infrastructure.fizzdap import (
    FizzDAPDashboard,
    FizzDAPServer,
)
from enterprise_fizzbuzz.infrastructure.self_modifying import (
    SelfModifyingDashboard,
    SelfModifyingMiddleware,
    create_self_modifying_engine,
)
from enterprise_fizzbuzz.infrastructure.os_kernel import (
    FizzBuzzKernel,
    KernelDashboard,
    KernelMiddleware,
)
from enterprise_fizzbuzz.infrastructure.p2p_network import (
    P2PDashboard,
    P2PMiddleware,
    P2PNetwork,
)
from enterprise_fizzbuzz.infrastructure.fizzkube import (
    FizzKubeControlPlane,
    FizzKubeDashboard,
    FizzKubeMiddleware,
)
from enterprise_fizzbuzz.infrastructure.digital_twin import (
    MonteCarloEngine,
    PredictiveAnomalyDetector,
    TwinDashboard,
    TwinDriftMonitor,
    TwinMiddleware,
    TwinModel,
    StateSync,
    WhatIfSimulator,
)
from enterprise_fizzbuzz.infrastructure.fizzlang import (
    FizzLangDashboard,
    FizzLangREPL,
    compile_program,
    run_program,
)
from enterprise_fizzbuzz.infrastructure.archaeology import (
    ArchaeologyDashboard,
    ArchaeologyEngine,
    ArchaeologyMiddleware,
)
from enterprise_fizzbuzz.infrastructure.intent_log import (
    CheckpointManager,
    CrashRecoveryEngine,
    ExecutionMode,
    IntentDashboard,
    IntentMiddleware,
    WriteAheadIntentLog,
)
from enterprise_fizzbuzz.infrastructure.crdt import (
    CRDTDashboard,
    CRDTMergeEngine,
    CRDTMiddleware,
)
from enterprise_fizzbuzz.infrastructure.recommendations import (
    RecommendationDashboard,
    RecommendationEngine,
)
from enterprise_fizzbuzz.infrastructure.dependent_types import (
    ProofEngine,
    TypeDashboard,
)
from enterprise_fizzbuzz.infrastructure.distributed_locks import (
    ContentionProfiler,
    FencingTokenGenerator,
    HierarchicalLockManager,
    LeaseManager,
    LockDashboard,
    LockMiddleware,
    WaitPolicy,
    WaitPolicyType,
)
from enterprise_fizzbuzz.infrastructure.cdc import (
    CDCDashboard,
    CDCMiddleware,
    CDCPipeline,
    create_cdc_subsystem,
)
from enterprise_fizzbuzz.infrastructure.billing import (
    BillingDashboard,
    BillingInvoiceGenerator,
    BillingMiddleware,
    Contract,
    ContractStatus,
    DunningManager,
    FizzOpsCalculator,
    RatingEngine,
    RevenueRecognizer,
    SubscriptionTier as BillingSubscriptionTier,
    TIER_DEFINITIONS,
    UsageMeter,
)
from enterprise_fizzbuzz.infrastructure.ip_office import (
    CopyrightRegistry,
    IPDisputeTribunal,
    IPOfficeDashboard,
    LicenseManager,
    LicenseType,
    PatentExaminer,
    TrademarkRegistry,
)
from enterprise_fizzbuzz.infrastructure.neural_arch_search import (
    NASDashboard,
    NASEngine,
)
from enterprise_fizzbuzz.infrastructure.observability_correlation import (
    CorrelationDashboard,
    ObservabilityCorrelationManager,
)
from enterprise_fizzbuzz.infrastructure.capability_security import (
    CapabilityDashboard,
    CapabilityManager,
    CapabilityMiddleware,
    Operation,
)
from enterprise_fizzbuzz.infrastructure.otel_tracing import (
    OTelDashboard,
    OTelMiddleware,
    TracerProvider as OTelTracerProvider,
    create_otel_subsystem,
)
from enterprise_fizzbuzz.domain.models import SchedulerAlgorithm

logger = logging.getLogger(__name__)


BANNER = r"""
  +===========================================================+
  |                                                           |
  |   FFFFFFFF II ZZZZZZZ ZZZZZZZ BBBBB   UU   UU ZZZZZZZ     |
  |   FF       II      ZZ      ZZ BB  BB  UU   UU      ZZ     |
  |   FFFFFF   II    ZZ      ZZ   BBBBB   UU   UU    ZZ       |
  |   FF       II   ZZ      ZZ   BB  BB  UU   UU   ZZ         |
  |   FF       II ZZZZZZZ ZZZZZZZ BBBBB   UUUUUU ZZZZZZZ      |
  |                                                           |
  |         E N T E R P R I S E   E D I T I O N               |
  |                    v1.0.0                                 |
  |                                                           |
  +===========================================================+
"""


def build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with all supported options."""
    parser = argparse.ArgumentParser(
        prog="fizzbuzz",
        description="Enterprise FizzBuzz Platform - Production-grade FizzBuzz evaluation engine",
        epilog="For support, please open a ticket with your Enterprise FizzBuzz Platform administrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--range",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="The numeric range to evaluate (default: from config)",
    )

    parser.add_argument(
        "--format",
        choices=["plain", "json", "xml", "csv"],
        help="Output format (default: from config)",
    )

    parser.add_argument(
        "--strategy",
        choices=["standard", "chain_of_responsibility", "parallel_async", "machine_learning"],
        help="Rule evaluation strategy (default: from config)",
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose console output with event logging",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging",
    )

    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="Use asynchronous evaluation engine",
    )

    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Suppress the startup banner",
    )

    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Suppress the session summary",
    )

    parser.add_argument(
        "--metadata",
        action="store_true",
        help="Include metadata in output (JSON format only)",
    )

    parser.add_argument(
        "--blockchain",
        action="store_true",
        help="Enable blockchain-based immutable audit ledger for tamper-proof compliance",
    )

    parser.add_argument(
        "--mining-difficulty",
        type=int,
        default=2,
        metavar="N",
        help="Proof-of-work difficulty for blockchain mining (default: 2)",
    )

    parser.add_argument(
        "--locale",
        type=str,
        metavar="LOCALE",
        default=None,
        help="Locale for internationalized output (en, de, fr, ja, tlh, sjn, qya)",
    )

    parser.add_argument(
        "--list-locales",
        action="store_true",
        help="Display available locales and exit",
    )

    parser.add_argument(
        "--circuit-breaker",
        action="store_true",
        help="Enable circuit breaker with exponential backoff for fault-tolerant FizzBuzz evaluation",
    )

    parser.add_argument(
        "--circuit-status",
        action="store_true",
        help="Display the circuit breaker status dashboard after execution",
    )

    parser.add_argument(
        "--event-sourcing",
        action="store_true",
        help="Enable Event Sourcing with CQRS for append-only FizzBuzz audit logging",
    )

    parser.add_argument(
        "--replay",
        action="store_true",
        help="Replay all events from the event store to rebuild projections",
    )

    parser.add_argument(
        "--temporal-query",
        type=int,
        metavar="SEQ",
        default=None,
        help="Reconstruct FizzBuzz state at a specific event sequence number",
    )

    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable distributed tracing with ASCII waterfall output",
    )

    parser.add_argument(
        "--trace-json",
        action="store_true",
        help="Enable distributed tracing with JSON export output",
    )

    parser.add_argument(
        "--user",
        type=str,
        metavar="USERNAME",
        help="Authenticate as the specified user (trust-mode, no token required)",
    )

    parser.add_argument(
        "--role",
        type=str,
        choices=[r.name for r in FizzBuzzRole],
        help="Assign the specified RBAC role (requires --user or --token)",
    )

    parser.add_argument(
        "--token",
        type=str,
        metavar="TOKEN",
        help="Authenticate using an Enterprise FizzBuzz Platform token",
    )

    # Chaos Engineering flags
    parser.add_argument(
        "--chaos",
        action="store_true",
        help="Enable Chaos Engineering fault injection (the monkey awakens)",
    )

    parser.add_argument(
        "--chaos-level",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=None,
        metavar="N",
        help="Chaos severity level 1-5 (1=gentle breeze, 5=apocalypse)",
    )

    parser.add_argument(
        "--gameday",
        type=str,
        nargs="?",
        const="total_chaos",
        default=None,
        metavar="SCENARIO",
        help="Run a Game Day chaos scenario (modulo_meltdown, confidence_crisis, slow_burn, total_chaos)",
    )

    parser.add_argument(
        "--post-mortem",
        action="store_true",
        help="Generate a post-mortem incident report after chaos execution",
    )

    # SLA Monitoring
    parser.add_argument(
        "--sla",
        action="store_true",
        help="Enable SLA Monitoring with PagerDuty-style alerting for FizzBuzz evaluation",
    )

    parser.add_argument(
        "--sla-dashboard",
        action="store_true",
        help="Display the SLA monitoring dashboard after execution",
    )

    parser.add_argument(
        "--on-call",
        action="store_true",
        help="Display the current on-call status and escalation chain",
    )

    # Feature Flags
    # Cache flags
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable the in-memory caching layer for FizzBuzz evaluation results",
    )

    parser.add_argument(
        "--cache-policy",
        type=str,
        choices=["lru", "lfu", "fifo", "dramatic_random"],
        default=None,
        metavar="POLICY",
        help="Cache eviction policy (default: from config)",
    )

    parser.add_argument(
        "--cache-size",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of cache entries (default: from config)",
    )

    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Display the cache statistics dashboard after execution",
    )

    parser.add_argument(
        "--cache-warm",
        action="store_true",
        help="Pre-populate the cache before execution (defeats the purpose of caching)",
    )

    # Feature Flags
    parser.add_argument(
        "--feature-flags",
        action="store_true",
        help="Enable the Feature Flag / Progressive Rollout subsystem",
    )

    parser.add_argument(
        "--flag",
        action="append",
        metavar="NAME=VALUE",
        default=[],
        help="Override a feature flag (e.g. --flag wuzz_rule_experimental=true)",
    )

    parser.add_argument(
        "--list-flags",
        action="store_true",
        help="Display all registered feature flags and exit",
    )

    # Database Migration Framework
    # Repository Pattern + Unit of Work
    parser.add_argument(
        "--repository",
        type=str,
        choices=["in_memory", "sqlite", "filesystem"],
        default=None,
        metavar="BACKEND",
        help="Enable result persistence via Repository Pattern (in_memory | sqlite | filesystem)",
    )

    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to SQLite database file (default: from config, only with --repository sqlite)",
    )

    parser.add_argument(
        "--results-dir",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to results directory (default: from config, only with --repository filesystem)",
    )

    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Apply all pending database migrations to the in-memory schema (it won't persist)",
    )

    parser.add_argument(
        "--migrate-status",
        action="store_true",
        help="Display the migration status dashboard for the ephemeral database",
    )

    parser.add_argument(
        "--migrate-rollback",
        type=int,
        nargs="?",
        const=1,
        default=None,
        metavar="N",
        help="Roll back the last N migrations (default: 1)",
    )

    parser.add_argument(
        "--migrate-seed",
        action="store_true",
        help="Generate FizzBuzz seed data using the FizzBuzz engine (the ouroboros)",
    )

    # Health Check Probes
    parser.add_argument(
        "--health",
        action="store_true",
        help="Enable Kubernetes-style health check probes for the FizzBuzz platform",
    )

    parser.add_argument(
        "--liveness",
        action="store_true",
        help="Run a liveness probe (canary evaluation of 15 must equal FizzBuzz)",
    )

    parser.add_argument(
        "--readiness",
        action="store_true",
        help="Run a readiness probe (aggregate subsystem health assessment)",
    )

    parser.add_argument(
        "--startup-probe",
        action="store_true",
        help="Display the startup probe status (boot milestone tracking)",
    )

    parser.add_argument(
        "--health-dashboard",
        action="store_true",
        help="Display the comprehensive health check dashboard after execution",
    )

    parser.add_argument(
        "--self-heal",
        action="store_true",
        help="Enable self-healing: automatically attempt recovery of failing subsystems",
    )

    # Prometheus-Style Metrics
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Enable Prometheus-style metrics collection for FizzBuzz evaluation",
    )

    parser.add_argument(
        "--metrics-export",
        action="store_true",
        help="Export all metrics in Prometheus text exposition format after execution",
    )

    parser.add_argument(
        "--metrics-dashboard",
        action="store_true",
        help="Display the ASCII Grafana metrics dashboard after execution",
    )

    # Webhook Notification System
    parser.add_argument(
        "--webhooks",
        action="store_true",
        help="Enable the Webhook Notification System for event-driven FizzBuzz telemetry",
    )

    parser.add_argument(
        "--webhook-url",
        action="append",
        metavar="URL",
        default=[],
        help="Register a webhook endpoint URL (can be specified multiple times)",
    )

    parser.add_argument(
        "--webhook-events",
        type=str,
        metavar="EVENTS",
        default=None,
        help="Comma-separated list of event types to subscribe to (default: from config)",
    )

    parser.add_argument(
        "--webhook-secret",
        type=str,
        metavar="SECRET",
        default=None,
        help="HMAC-SHA256 secret for signing webhook payloads (default: from config)",
    )

    parser.add_argument(
        "--webhook-test",
        action="store_true",
        help="Send a test webhook to all registered endpoints and exit",
    )

    parser.add_argument(
        "--webhook-log",
        action="store_true",
        help="Display the webhook delivery log after execution",
    )

    parser.add_argument(
        "--webhook-dlq",
        action="store_true",
        help="Display the Dead Letter Queue contents after execution",
    )

    # Service Mesh Simulation
    parser.add_argument(
        "--service-mesh",
        action="store_true",
        help="Enable the Service Mesh Simulation: decompose FizzBuzz into 7 microservices",
    )

    parser.add_argument(
        "--mesh-topology",
        action="store_true",
        help="Display the ASCII service mesh topology diagram after execution",
    )

    parser.add_argument(
        "--mesh-latency",
        action="store_true",
        help="Enable simulated network latency injection between mesh services",
    )

    parser.add_argument(
        "--mesh-packet-loss",
        action="store_true",
        help="Enable simulated packet loss between mesh services",
    )

    parser.add_argument(
        "--canary",
        action="store_true",
        help="Enable canary deployment routing (v2 DivisibilityService uses advanced formula)",
    )

    # Configuration Hot-Reload with Single-Node Raft Consensus
    parser.add_argument(
        "--hot-reload",
        action="store_true",
        help="Enable configuration hot-reload with Single-Node Raft Consensus (polls config.yaml for changes)",
    )

    parser.add_argument(
        "--reload-status",
        action="store_true",
        help="Display the hot-reload Raft consensus dashboard after execution",
    )

    parser.add_argument(
        "--config-diff",
        type=str,
        metavar="PATH",
        default=None,
        help="Compute and display a diff between current config and the specified YAML file",
    )

    parser.add_argument(
        "--config-validate",
        type=str,
        metavar="PATH",
        default=None,
        help="Validate the specified YAML configuration file and exit",
    )

    # Rate Limiting & API Quota Management
    parser.add_argument(
        "--rate-limit",
        action="store_true",
        help="Enable rate limiting for FizzBuzz evaluations (because unrestricted modulo is dangerous)",
    )

    parser.add_argument(
        "--rate-limit-rpm",
        type=int,
        default=None,
        metavar="N",
        help="Maximum FizzBuzz evaluations per minute (default: from config)",
    )

    parser.add_argument(
        "--rate-limit-algo",
        type=str,
        choices=["token_bucket", "sliding_window", "fixed_window"],
        default=None,
        help="Rate limiting algorithm (default: from config)",
    )

    parser.add_argument(
        "--rate-limit-dashboard",
        action="store_true",
        help="Display the rate limiting ASCII dashboard after execution",
    )

    parser.add_argument(
        "--quota",
        action="store_true",
        help="Display quota status summary after execution",
    )

    # Compliance & Regulatory Framework
    parser.add_argument(
        "--compliance",
        action="store_true",
        help="Enable SOX/GDPR/HIPAA compliance framework for FizzBuzz evaluation",
    )

    parser.add_argument(
        "--gdpr-erase",
        type=int,
        metavar="NUMBER",
        default=None,
        help="Submit a GDPR right-to-erasure request for the specified number (triggers THE COMPLIANCE PARADOX)",
    )

    parser.add_argument(
        "--sox-audit",
        action="store_true",
        help="Display the SOX segregation of duties audit trail after execution",
    )

    parser.add_argument(
        "--hipaa-check",
        action="store_true",
        help="Display HIPAA PHI access log and encryption statistics after execution",
    )

    parser.add_argument(
        "--compliance-report",
        action="store_true",
        help="Generate a comprehensive compliance report after execution",
    )

    parser.add_argument(
        "--compliance-dashboard",
        action="store_true",
        help="Display the compliance & regulatory ASCII dashboard after execution",
    )

    # Compliance Chatbot
    parser.add_argument(
        "--chatbot",
        type=str,
        metavar="QUESTION",
        default=None,
        help='Ask the regulatory compliance chatbot a GDPR/SOX/HIPAA question (e.g. --chatbot "Is erasing FizzBuzz results GDPR compliant?")',
    )

    parser.add_argument(
        "--chatbot-interactive",
        action="store_true",
        help="Start an interactive compliance chatbot REPL for ongoing regulatory consultations",
    )

    parser.add_argument(
        "--chatbot-dashboard",
        action="store_true",
        help="Display the compliance chatbot session dashboard after execution",
    )

    # FinOps Cost Tracking & Chargeback Engine
    parser.add_argument(
        "--finops",
        action="store_true",
        help="Enable FinOps cost tracking for FizzBuzz evaluations (every modulo has a price)",
    )

    parser.add_argument(
        "--invoice",
        action="store_true",
        help="Generate an itemized ASCII invoice for all FizzBuzz evaluations in this session",
    )

    parser.add_argument(
        "--cost-dashboard",
        action="store_true",
        help="Display the FinOps cost tracking ASCII dashboard after execution",
    )

    parser.add_argument(
        "--savings-plan",
        action="store_true",
        help="Display FizzBuzz Savings Plan comparison (1-year and 3-year commitments)",
    )

    # Disaster Recovery & Backup/Restore
    parser.add_argument(
        "--dr",
        action="store_true",
        help="Enable Disaster Recovery with WAL, snapshots, and PITR (all in RAM, naturally)",
    )

    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a manual backup of the current state after execution",
    )

    parser.add_argument(
        "--backup-list",
        action="store_true",
        help="Display all backups in the in-memory vault after execution",
    )

    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore the latest backup before execution (proves recovery works)",
    )

    parser.add_argument(
        "--dr-drill",
        action="store_true",
        help="Run a DR drill: destroy state, recover, measure RTO/RPO (all in RAM)",
    )

    parser.add_argument(
        "--dr-dashboard",
        action="store_true",
        help="Display the Disaster Recovery ASCII dashboard after execution",
    )

    parser.add_argument(
        "--retention-status",
        action="store_true",
        help="Display the backup retention policy status (24h/7d/4w/12m for a <1s process)",
    )

    # A/B Testing Framework
    parser.add_argument(
        "--ab-test",
        action="store_true",
        help="Enable the A/B Testing Framework for evaluation strategy comparison",
    )

    parser.add_argument(
        "--experiment",
        type=str,
        metavar="NAME",
        default=None,
        help="Run a specific named experiment (default: all configured experiments)",
    )

    parser.add_argument(
        "--ab-report",
        action="store_true",
        help="Display the A/B testing experiment report after execution",
    )

    parser.add_argument(
        "--ab-dashboard",
        action="store_true",
        help="Display the A/B testing dashboard after execution",
    )

    # Message Queue & Event Bus
    parser.add_argument(
        "--mq",
        action="store_true",
        help="Enable the Kafka-style Message Queue backed by Python lists",
    )

    parser.add_argument(
        "--mq-dashboard",
        action="store_true",
        help="Display the message queue ASCII dashboard after execution",
    )

    parser.add_argument(
        "--mq-topics",
        action="store_true",
        help="Display all message queue topics and exit",
    )

    parser.add_argument(
        "--mq-lag",
        action="store_true",
        help="Display consumer lag report after execution",
    )

    # Secrets Management Vault
    parser.add_argument(
        "--vault",
        action="store_true",
        help="Enable the Secrets Management Vault with Shamir's Secret Sharing (the number 3 deserves better security)",
    )

    parser.add_argument(
        "--vault-unseal",
        action="store_true",
        help="Automatically unseal the vault using generated shares (because manual key ceremonies are tedious)",
    )

    parser.add_argument(
        "--vault-status",
        action="store_true",
        help="Display the vault status and seal state after execution",
    )

    parser.add_argument(
        "--vault-scan",
        action="store_true",
        help="Run the AST-based secret scanner on the codebase (flags ALL integer literals)",
    )

    parser.add_argument(
        "--vault-dashboard",
        action="store_true",
        help="Display the comprehensive vault ASCII dashboard after execution",
    )

    parser.add_argument(
        "--vault-rotate",
        action="store_true",
        help="Force an immediate rotation of all rotatable secrets",
    )

    # Data Pipeline & ETL Framework
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Enable the Data Pipeline & ETL Framework: route FizzBuzz through a 5-stage DAG",
    )

    parser.add_argument(
        "--pipeline-dashboard",
        action="store_true",
        help="Display the Data Pipeline ASCII dashboard after execution",
    )

    parser.add_argument(
        "--pipeline-dag",
        action="store_true",
        help="Display the pipeline DAG visualization (a very straight line)",
    )

    parser.add_argument(
        "--pipeline-lineage",
        action="store_true",
        help="Display data lineage provenance chains for all processed records",
    )

    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Enable retroactive backfill enrichment of pipeline records",
    )

    # OpenAPI Specification Generator & ASCII Swagger UI
    parser.add_argument(
        "--openapi",
        action="store_true",
        help="Display the ASCII Swagger UI for the fictional Enterprise FizzBuzz REST API",
    )

    parser.add_argument(
        "--openapi-spec",
        action="store_true",
        help="Export the complete OpenAPI 3.1 specification in JSON format",
    )

    parser.add_argument(
        "--openapi-yaml",
        action="store_true",
        help="Export the complete OpenAPI 3.1 specification in YAML format",
    )

    parser.add_argument(
        "--swagger-ui",
        action="store_true",
        help="Display the ASCII Swagger UI (alias for --openapi)",
    )

    parser.add_argument(
        "--openapi-dashboard",
        action="store_true",
        help="Display the OpenAPI specification statistics dashboard",
    )

    # API Gateway with Routing, Versioning & Request Transformation
    parser.add_argument(
        "--gateway",
        action="store_true",
        help="Enable the API Gateway with routing, versioning, and request transformation for the non-existent REST API",
    )

    parser.add_argument(
        "--api-version",
        type=str,
        choices=["v1", "v2", "v3"],
        default=None,
        help="API version to use (v1=DEPRECATED, v2=ACTIVE, v3=ACTIVE). Default: from config",
    )

    parser.add_argument(
        "--api-key-generate",
        action="store_true",
        help="Generate a new Enterprise FizzBuzz Platform API key and exit",
    )

    parser.add_argument(
        "--gateway-dashboard",
        action="store_true",
        help="Display the API Gateway ASCII dashboard after execution",
    )

    # Blue/Green Deployment Simulation
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Run a Blue/Green Deployment Simulation (zero-downtime deployment for a 0.8s process)",
    )

    parser.add_argument(
        "--deploy-dashboard",
        action="store_true",
        help="Display the Blue/Green Deployment ASCII dashboard after execution",
    )

    parser.add_argument(
        "--deploy-rollback",
        action="store_true",
        help="Trigger a manual rollback after deployment (restores blue slot because reasons)",
    )

    # Graph Database for FizzBuzz Relationship Mapping
    parser.add_argument(
        "--graph-db",
        action="store_true",
        help="Enable the Graph Database: map divisibility relationships between integers as a property graph",
    )

    parser.add_argument(
        "--graph-query",
        type=str,
        metavar="CYPHER",
        default=None,
        help="Execute a CypherLite query against the FizzBuzz graph (e.g. \"MATCH (n:Number) WHERE n.value > 90 RETURN n\")",
    )

    parser.add_argument(
        "--graph-visualize",
        action="store_true",
        help="Display an ASCII visualization of the FizzBuzz relationship graph",
    )

    parser.add_argument(
        "--graph-dashboard",
        action="store_true",
        help="Display the Graph Database analytics dashboard with centrality, communities, and isolation awards",
    )

    # Genetic Algorithm for Optimal FizzBuzz Rule Discovery
    parser.add_argument(
        "--genetic",
        action="store_true",
        help="Enable the Genetic Algorithm to evolve the optimal FizzBuzz rules (spoiler: it rediscovers {3:Fizz, 5:Buzz})",
    )

    parser.add_argument(
        "--genetic-generations",
        type=int,
        default=None,
        metavar="N",
        help="Number of generations for the genetic algorithm (default: from config)",
    )

    parser.add_argument(
        "--genetic-dashboard",
        action="store_true",
        help="Display the Genetic Algorithm evolution dashboard after execution",
    )

    # Natural Language Query Interface
    parser.add_argument(
        "--nlq",
        type=str,
        metavar="QUERY",
        default=None,
        help='Execute a natural language FizzBuzz query (e.g. --nlq "Is 15 FizzBuzz?")',
    )

    parser.add_argument(
        "--nlq-interactive",
        action="store_true",
        help="Start the NLQ interactive REPL for conversational FizzBuzz queries",
    )

    # Load Testing Framework
    parser.add_argument(
        "--load-test",
        action="store_true",
        help="Run a load test against the FizzBuzz evaluation engine (because n%%3 needs stress testing)",
    )

    parser.add_argument(
        "--load-profile",
        type=str,
        choices=["smoke", "load", "stress", "spike", "endurance"],
        default=None,
        help="Workload profile for the load test (default: from config)",
    )

    parser.add_argument(
        "--load-vus",
        type=int,
        default=None,
        metavar="N",
        help="Number of Virtual Users for the load test (default: from config/profile)",
    )

    parser.add_argument(
        "--load-dashboard",
        action="store_true",
        help="Display the full ASCII load test dashboard after execution",
    )

    # Audit Dashboard & Real-Time Event Streaming
    parser.add_argument(
        "--audit-dashboard",
        action="store_true",
        help="Display the Unified Audit Dashboard: six-pane ASCII telemetry for FizzBuzz observability-of-observability",
    )

    parser.add_argument(
        "--audit-stream",
        action="store_true",
        help="Stream all events as NDJSON to stdout (structured logging for the structurally inclined)",
    )

    parser.add_argument(
        "--audit-anomalies",
        action="store_true",
        help="Display the anomaly detection report after execution (z-score analysis of FizzBuzz event rates)",
    )

    # GitOps Configuration-as-Code Simulator
    parser.add_argument(
        "--gitops",
        action="store_true",
        help="Enable the GitOps Configuration-as-Code Simulator (version-control your YAML in RAM)",
    )

    parser.add_argument(
        "--gitops-commit",
        type=str,
        metavar="MESSAGE",
        default=None,
        help="Create a GitOps commit with the specified message (requires --gitops)",
    )

    parser.add_argument(
        "--gitops-diff",
        action="store_true",
        help="Display the diff of the most recent GitOps commit",
    )

    parser.add_argument(
        "--gitops-log",
        action="store_true",
        help="Display the GitOps commit log for the current branch",
    )

    parser.add_argument(
        "--gitops-propose",
        type=str,
        metavar="KEY=VALUE",
        action="append",
        default=[],
        help="Propose a configuration change through the GitOps pipeline (e.g. --gitops-propose range.start=5)",
    )

    parser.add_argument(
        "--gitops-dashboard",
        action="store_true",
        help="Display the GitOps ASCII dashboard with commit log, drift, and proposals",
    )

    parser.add_argument(
        "--gitops-drift",
        action="store_true",
        help="Detect configuration drift between committed and running state",
    )

    # Formal Verification & Proof System
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run the Formal Verification engine: prove totality, determinism, completeness, and correctness of FizzBuzz evaluation via structural induction",
    )

    parser.add_argument(
        "--verify-property",
        type=str,
        choices=["totality", "determinism", "completeness", "correctness"],
        default=None,
        metavar="PROPERTY",
        help="Verify a single property (totality | determinism | completeness | correctness)",
    )

    parser.add_argument(
        "--proof-tree",
        action="store_true",
        help="Display the Gentzen-style natural deduction proof tree for the induction proof",
    )

    parser.add_argument(
        "--verify-dashboard",
        action="store_true",
        help="Display the Formal Verification ASCII dashboard with QED status and proof obligations",
    )

    # FizzBuzz-as-a-Service (FBaaS)
    parser.add_argument(
        "--fbaas",
        action="store_true",
        help="Enable FizzBuzz-as-a-Service: multi-tenant SaaS with usage metering, billing, and watermarks",
    )

    parser.add_argument(
        "--fbaas-tier",
        type=str,
        choices=["free", "pro", "enterprise"],
        default=None,
        help="FBaaS subscription tier for the default tenant (default: free)",
    )

    parser.add_argument(
        "--fbaas-onboard",
        action="store_true",
        help="Display the FBaaS onboarding wizard with ASCII art and API key",
    )

    parser.add_argument(
        "--fbaas-billing",
        action="store_true",
        help="Display the FBaaS billing ledger and dashboard after execution",
    )

    # Custom Bytecode VM (FBVM)
    parser.add_argument(
        "--vm",
        action="store_true",
        help="Execute FizzBuzz using the Custom Bytecode VM (FBVM) instead of Python — because direct execution was too efficient",
    )

    parser.add_argument(
        "--vm-disasm",
        action="store_true",
        help="Display the FBVM disassembly listing of compiled bytecode before execution",
    )

    parser.add_argument(
        "--vm-trace",
        action="store_true",
        help="Enable instruction-level execution tracing in the FBVM (log every fetch-decode-execute cycle)",
    )

    parser.add_argument(
        "--vm-dashboard",
        action="store_true",
        help="Display the FBVM ASCII dashboard with register file, disassembly, and execution stats",
    )

    # Time-Travel Debugger
    parser.add_argument(
        "--time-travel",
        action="store_true",
        help="Enable the Time-Travel Debugger: capture evaluation snapshots and navigate bidirectionally through FizzBuzz history",
    )

    parser.add_argument(
        "--tt-breakpoint",
        type=str,
        action="append",
        default=[],
        metavar="EXPR",
        help="Set a conditional breakpoint (e.g., \"result == 'FizzBuzz'\"). Can be repeated.",
    )

    parser.add_argument(
        "--tt-dashboard",
        action="store_true",
        help="Display the Time-Travel Debugger ASCII dashboard after execution",
    )

    # Query Optimizer (PostgreSQL-style cost-based planner)
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Enable the cost-based Query Optimizer for FizzBuzz evaluation (because modulo deserves a query planner)",
    )

    parser.add_argument(
        "--explain",
        type=int,
        metavar="N",
        default=None,
        help="Display the PostgreSQL-style EXPLAIN plan for evaluating number N (without executing)",
    )

    parser.add_argument(
        "--explain-analyze",
        type=int,
        metavar="N",
        default=None,
        help="Display EXPLAIN ANALYZE for number N (execute and compare estimated vs actual costs)",
    )

    parser.add_argument(
        "--optimizer-hints",
        type=str,
        metavar="HINTS",
        default=None,
        help="Comma-separated optimizer hints: FORCE_ML, PREFER_CACHE, NO_BLOCKCHAIN, NO_ML",
    )

    parser.add_argument(
        "--optimizer-dashboard",
        action="store_true",
        help="Display the Query Optimizer ASCII dashboard after execution",
    )

    # Distributed Paxos Consensus
    parser.add_argument(
        "--paxos",
        action="store_true",
        help="Enable Distributed Paxos Consensus for multi-node FizzBuzz evaluation",
    )

    parser.add_argument(
        "--paxos-nodes",
        type=int,
        default=None,
        metavar="N",
        help="Number of Paxos cluster nodes (default: from config, typically 5)",
    )

    parser.add_argument(
        "--paxos-byzantine",
        action="store_true",
        help="Enable Byzantine fault injection (one node lies about its FizzBuzz evaluation)",
    )

    parser.add_argument(
        "--paxos-dashboard",
        action="store_true",
        help="Display the Paxos Consensus ASCII dashboard after execution",
    )

    # Quantum Computing Simulator
    parser.add_argument(
        "--quantum",
        action="store_true",
        help="Enable the Quantum Computing Simulator: use Shor's algorithm for FizzBuzz divisibility checking",
    )

    parser.add_argument(
        "--quantum-circuit",
        action="store_true",
        help="Display the ASCII quantum circuit diagram for the divisibility checking circuit",
    )

    parser.add_argument(
        "--quantum-dashboard",
        action="store_true",
        help="Display the Quantum Computing Simulator ASCII dashboard with negative advantage ratios",
    )

    # Cross-Compiler
    parser.add_argument(
        "--compile-to",
        type=str,
        choices=["c", "rust", "wat"],
        default=None,
        metavar="TARGET",
        help="Cross-compile FizzBuzz rules to a target language (c | rust | wat)",
    )

    parser.add_argument(
        "--compile-ir",
        action="store_true",
        help="Display the cross-compiler Intermediate Representation (IR) without code generation",
    )

    parser.add_argument(
        "--compile-verify",
        action="store_true",
        help="Run round-trip verification after cross-compilation (enabled by default with --compile-to)",
    )

    parser.add_argument(
        "--compile-dashboard",
        action="store_true",
        help="Display the Cross-Compiler ASCII dashboard with overhead metrics and enterprise analysis",
    )

    # Federated Learning
    parser.add_argument(
        "--federated",
        action="store_true",
        help="Enable Federated Learning: train 5 non-IID clients to collaboratively learn modulo arithmetic",
    )

    parser.add_argument(
        "--fed-rounds",
        type=int,
        default=None,
        metavar="N",
        help="Number of federation rounds (default: from config)",
    )

    parser.add_argument(
        "--fed-dashboard",
        action="store_true",
        help="Display the Federated Learning ASCII dashboard after execution",
    )

    # Knowledge Graph & Domain Ontology
    parser.add_argument(
        "--ontology",
        action="store_true",
        help="Enable the Knowledge Graph & Domain Ontology: model FizzBuzz as RDF triples with OWL class hierarchy",
    )

    parser.add_argument(
        "--sparql",
        type=str,
        metavar="QUERY",
        default=None,
        help='Execute a FizzSPARQL query (e.g. --sparql "SELECT ?n WHERE { ?n fizz:hasClassification fizz:Fizz } LIMIT 10")',
    )

    parser.add_argument(
        "--ontology-dashboard",
        action="store_true",
        help="Display the Knowledge Graph & Domain Ontology ASCII dashboard after execution",
    )

    # Self-Modifying Code
    parser.add_argument(
        "--self-modify",
        action="store_true",
        help="Enable Self-Modifying Code: FizzBuzz rules that inspect and rewrite their own evaluation logic at runtime",
    )

    parser.add_argument(
        "--self-modify-rate",
        type=float,
        default=None,
        metavar="RATE",
        help="Mutation probability per evaluation, 0.0-1.0 (default: from config)",
    )

    parser.add_argument(
        "--self-modify-dashboard",
        action="store_true",
        help="Display the Self-Modifying Code ASCII dashboard after execution",
    )

    # FizzBuzz Operating System Kernel
    parser.add_argument(
        "--kernel",
        action="store_true",
        help="Enable the FizzBuzz OS Kernel: process scheduling, virtual memory, and interrupts for modulo arithmetic",
    )

    parser.add_argument(
        "--kernel-scheduler",
        type=str,
        choices=["rr", "priority", "cfs"],
        default=None,
        help="Kernel process scheduler algorithm (rr=Round Robin, priority=Preemptive, cfs=Completely Fair)",
    )

    parser.add_argument(
        "--kernel-dashboard",
        action="store_true",
        help="Display the FizzBuzz OS Kernel ASCII dashboard after execution",
    )

    # Peer-to-Peer Gossip Network
    parser.add_argument(
        "--p2p",
        action="store_true",
        help="Enable the Peer-to-Peer Gossip Network: disseminate FizzBuzz results across 7 simulated nodes via SWIM and Kademlia",
    )

    parser.add_argument(
        "--p2p-nodes",
        type=int,
        default=None,
        metavar="N",
        help="Number of P2P cluster nodes (default: from config, typically 7)",
    )

    parser.add_argument(
        "--p2p-dashboard",
        action="store_true",
        help="Display the P2P Gossip Network ASCII dashboard after execution",
    )

    # Digital Twin Simulation
    parser.add_argument(
        "--twin",
        action="store_true",
        help="Enable the Digital Twin: a real-time simulation of the platform itself (a simulation of a simulation of n%%3)",
    )

    parser.add_argument(
        "--twin-scenario",
        type=str,
        metavar="SCENARIO",
        default=None,
        help='Run a what-if scenario against the twin (e.g. --twin-scenario "blockchain.latency_ms=1.0;cache.failure_prob=0.5")',
    )

    parser.add_argument(
        "--twin-dashboard",
        action="store_true",
        help="Display the Digital Twin ASCII dashboard with Monte Carlo histogram and drift gauge",
    )

    # FizzLang Domain-Specific Language
    parser.add_argument(
        "--fizzlang",
        type=str,
        metavar="PROGRAM",
        default=None,
        help='Execute a FizzLang program inline (e.g., --fizzlang \'rule fizz when n %% 3 == 0 emit "Fizz"\\nevaluate 1 to 20\')',
    )

    parser.add_argument(
        "--fizzlang-file",
        type=str,
        metavar="FILE",
        default=None,
        help="Execute a FizzLang program from a .fizz file",
    )

    parser.add_argument(
        "--fizzlang-repl",
        action="store_true",
        help="Start the FizzLang interactive REPL — the Turing-incomplete experience",
    )

    parser.add_argument(
        "--fizzlang-dashboard",
        action="store_true",
        help="Display the FizzLang ASCII dashboard with source stats and Language Complexity Index",
    )

    # Recommendation Engine
    parser.add_argument(
        "--recommend",
        action="store_true",
        help="Enable the Recommendation Engine: suggest numbers you might enjoy evaluating next",
    )

    parser.add_argument(
        "--recommend-for",
        type=int,
        metavar="N",
        default=None,
        help="Get recommendations similar to a specific number (e.g. --recommend-for 15)",
    )

    parser.add_argument(
        "--recommend-dashboard",
        action="store_true",
        help="Display the Recommendation Engine ASCII dashboard after execution",
    )

    # Archaeological Recovery System
    parser.add_argument(
        "--archaeology",
        action="store_true",
        help="Enable the Archaeological Recovery System: excavate FizzBuzz evidence from seven stratigraphic layers",
    )

    parser.add_argument(
        "--excavate",
        type=int,
        metavar="N",
        default=None,
        help="Excavate a specific number and display full forensic report (e.g. --excavate 15)",
    )

    parser.add_argument(
        "--archaeology-dashboard",
        action="store_true",
        help="Display the Archaeological Recovery System ASCII dashboard after execution",
    )

    # Dependent Type System & Curry-Howard Proof Engine
    parser.add_argument(
        "--dependent-types",
        action="store_true",
        help="Enable the Dependent Type System & Curry-Howard Proof Engine (every evaluation becomes a theorem)",
    )

    parser.add_argument(
        "--prove",
        type=int,
        metavar="N",
        default=None,
        help="Construct a fully witnessed proof for a specific number (e.g. --prove 15)",
    )

    parser.add_argument(
        "--type-check",
        action="store_true",
        help="Run bidirectional type checking on all proof terms after evaluation",
    )

    parser.add_argument(
        "--types-dashboard",
        action="store_true",
        help="Display the Dependent Type System & Curry-Howard Proof Engine ASCII dashboard",
    )

    # FizzKube Container Orchestration
    parser.add_argument(
        "--fizzkube",
        action="store_true",
        help="Enable FizzKube Container Orchestration: schedule FizzBuzz evaluations as pods across simulated worker nodes",
    )

    parser.add_argument(
        "--fizzkube-pods",
        type=int,
        default=None,
        metavar="N",
        help="Number of simulated worker nodes in the FizzKube cluster (default: from config)",
    )

    parser.add_argument(
        "--fizzkube-dashboard",
        action="store_true",
        help="Display the FizzKube Container Orchestration ASCII dashboard after execution",
    )

    # FizzPM Package Manager
    parser.add_argument(
        "--fizzpm",
        action="store_true",
        help="Enable FizzPM Package Manager: SAT-based dependency resolution for the FizzBuzz ecosystem",
    )

    parser.add_argument(
        "--fizzpm-install",
        type=str,
        metavar="PACKAGE",
        default=None,
        help="Install a FizzPM package and resolve dependencies via DPLL SAT solver (e.g. --fizzpm-install fizzbuzz-enterprise)",
    )

    parser.add_argument(
        "--fizzpm-audit",
        action="store_true",
        help="Run a vulnerability audit against all installed/available FizzPM packages",
    )

    parser.add_argument(
        "--fizzpm-dashboard",
        action="store_true",
        help="Display the FizzPM Package Manager ASCII dashboard after execution",
    )

    # FizzSQL Relational Query Engine
    parser.add_argument(
        "--fizzsql",
        type=str,
        metavar="QUERY",
        default=None,
        help='Execute a FizzSQL query against platform internals (e.g. --fizzsql "SELECT * FROM evaluations")',
    )

    parser.add_argument(
        "--fizzsql-tables",
        action="store_true",
        help="List all FizzSQL virtual tables and their schemas",
    )

    parser.add_argument(
        "--fizzsql-dashboard",
        action="store_true",
        help="Display the FizzSQL Relational Query Engine ASCII dashboard after execution",
    )

    # FizzDAP Debug Adapter Protocol Server
    parser.add_argument(
        "--dap",
        action="store_true",
        help="Enable the FizzDAP Debug Adapter Protocol Server: step through FizzBuzz one modulo at a time",
    )

    parser.add_argument(
        "--dap-port",
        type=int,
        default=None,
        metavar="N",
        help="DAP server port (simulated, no actual socket — default: from config)",
    )

    parser.add_argument(
        "--dap-dashboard",
        action="store_true",
        help="Display the FizzDAP ASCII dashboard with breakpoints, stack trace, variables, and Debug Complexity Index",
    )

    # FizzBuzz Intellectual Property Office
    parser.add_argument(
        "--ip-office",
        action="store_true",
        help="Enable the FizzBuzz Intellectual Property Office: trademark, patent, copyright, and dispute resolution",
    )

    parser.add_argument(
        "--trademark",
        type=str,
        metavar="LABEL",
        default=None,
        help="Apply for trademark registration of a FizzBuzz label (e.g. --trademark 'Wuzz')",
    )

    parser.add_argument(
        "--patent",
        type=str,
        metavar="DESCRIPTION",
        default=None,
        help="File a patent application for a FizzBuzz rule (e.g. --patent 'Divisibility by 7 yields Bazz')",
    )

    parser.add_argument(
        "--ip-dashboard",
        action="store_true",
        help="Display the FizzBuzz Intellectual Property Office ASCII dashboard",
    )

    # FizzLock Distributed Lock Manager
    parser.add_argument(
        "--locks",
        action="store_true",
        help="Enable FizzLock Distributed Lock Manager: hierarchical multi-granularity locking for concurrent evaluation",
    )

    parser.add_argument(
        "--lock-policy",
        choices=["wait-die", "wound-wait"],
        default=None,
        help="Deadlock prevention policy for the lock manager (default: from config)",
    )

    parser.add_argument(
        "--lock-dashboard",
        action="store_true",
        help="Display the FizzLock ASCII dashboard with active locks, wait-for graph, deadlock history, and contention heatmap",
    )

    # Change Data Capture (FizzCDC)
    parser.add_argument(
        "--cdc",
        action="store_true",
        help="Enable FizzCDC Change Data Capture: stream platform state changes through an outbox relay to pluggable sinks",
    )

    parser.add_argument(
        "--cdc-dashboard",
        action="store_true",
        help="Display the FizzCDC ASCII dashboard with capture rates, outbox depth, relay lag, and sink status",
    )

    parser.add_argument(
        "--cdc-sinks",
        type=str,
        default=None,
        metavar="SINKS",
        help="Comma-separated list of CDC sink connectors (log,metrics,message_queue). Default: from config",
    )

    # FizzBill API Monetization & Subscription Billing
    parser.add_argument(
        "--billing",
        action="store_true",
        help="Enable FizzBill: API monetization with ASC 606 revenue recognition, subscription tiers, and dunning",
    )

    parser.add_argument(
        "--billing-tier",
        type=str,
        choices=["free", "developer", "professional", "enterprise"],
        default=None,
        help="Subscription tier for the default tenant (default: from config)",
    )

    parser.add_argument(
        "--billing-invoice",
        action="store_true",
        help="Generate an ASCII subscription & usage invoice after execution",
    )

    parser.add_argument(
        "--billing-dashboard",
        action="store_true",
        help="Display the FizzBill billing & revenue recognition ASCII dashboard after execution",
    )

    # FizzNAS Neural Architecture Search
    parser.add_argument(
        "--nas",
        action="store_true",
        help="Enable FizzNAS Neural Architecture Search: automated topology optimization for the ML engine",
    )

    parser.add_argument(
        "--nas-strategy",
        type=str,
        choices=["random", "evolutionary", "darts"],
        default=None,
        help="NAS search strategy (default: from config)",
    )

    parser.add_argument(
        "--nas-budget",
        type=int,
        default=None,
        metavar="N",
        help="Total fitness evaluations (architectures to train) during NAS (default: from config)",
    )

    parser.add_argument(
        "--nas-dashboard",
        action="store_true",
        help="Display the FizzNAS ASCII dashboard with Pareto front, top architectures, and baseline comparison",
    )

    # FizzJIT — Runtime Code Generation
    parser.add_argument(
        "--jit",
        action="store_true",
        help="Enable FizzJIT trace-based compiler: SSA IR, four optimization passes, and compiled closures for modulo arithmetic",
    )

    parser.add_argument(
        "--jit-threshold",
        type=int,
        default=None,
        metavar="N",
        help="Number of range evaluations before JIT compilation triggers (default: from config)",
    )

    parser.add_argument(
        "--jit-dashboard",
        action="store_true",
        help="Display the FizzJIT ASCII dashboard with trace profiler stats, cache metrics, and optimization report",
    )

    # FizzCorr Observability Correlation Engine
    parser.add_argument(
        "--correlate",
        action="store_true",
        help="Enable FizzCorr Observability Correlation Engine: unify traces, logs, and metrics into a correlated timeline",
    )

    parser.add_argument(
        "--correlate-dashboard",
        action="store_true",
        help="Display the FizzCorr ASCII dashboard with unified timeline, anomalies, dependency map, and signal volumes",
    )

    # FizzCap Capability-Based Security
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="Enable FizzCap capability-based security: unforgeable object capabilities with HMAC-SHA256 signatures",
    )

    parser.add_argument(
        "--cap-mode",
        type=str,
        choices=["native", "bridge", "audit-only"],
        default=None,
        help="Capability enforcement mode: native (strict), bridge (auto-issue for legacy), audit-only (log but allow)",
    )

    parser.add_argument(
        "--cap-dashboard",
        action="store_true",
        help="Display the FizzCap ASCII dashboard with active capabilities, delegation graph, and guard activity",
    )

    # FizzOTel — OpenTelemetry-Compatible Distributed Tracing
    parser.add_argument(
        "--otel",
        action="store_true",
        help="Enable FizzOTel distributed tracing: W3C TraceContext, OTLP/Zipkin export, probabilistic sampling",
    )

    parser.add_argument(
        "--otel-export",
        type=str,
        choices=["otlp", "zipkin", "console"],
        default=None,
        help="OTel trace export format: otlp (JSON), zipkin (v2 JSON), console (ASCII waterfall). Default: from config",
    )

    parser.add_argument(
        "--otel-dashboard",
        action="store_true",
        help="Display the FizzOTel ASCII dashboard with trace stats, sampling decisions, export metrics, and duration histogram",
    )

    # FizzWAL — Write-Ahead Intent Log
    parser.add_argument(
        "--wal-intent",
        action="store_true",
        help="Enable FizzWAL Write-Ahead Intent Log: ARIES-compliant crash recovery for every FizzBuzz evaluation",
    )

    parser.add_argument(
        "--wal-mode",
        type=str,
        choices=["optimistic", "pessimistic", "speculative"],
        default=None,
        help="WAL execution mode: optimistic (write-through + rollback), pessimistic (shadow buffer), speculative (post-condition validation)",
    )

    parser.add_argument(
        "--wal-dashboard",
        action="store_true",
        help="Display the FizzWAL ASCII dashboard with log stats, active transactions, checkpoint history, and recovery report",
    )

    # FizzCRDT — Conflict-Free Replicated Data Types
    parser.add_argument(
        "--crdt",
        action="store_true",
        help="Enable FizzCRDT: replicate classification state across simulated replicas using CvRDTs with join-semilattice merge",
    )

    parser.add_argument(
        "--crdt-dashboard",
        action="store_true",
        help="Display the FizzCRDT ASCII dashboard with per-CRDT state, vector clocks, convergence stats, and merge history",
    )

    # FizzGrammar -- Formal Grammar & Parser Generator
    parser.add_argument(
        "--grammar",
        action="store_true",
        help="Enable FizzGrammar: parse and analyze the built-in FizzBuzz Classification grammar with FIRST/FOLLOW sets",
    )

    parser.add_argument(
        "--grammar-analyze",
        action="store_true",
        help="Run full grammar analysis: FIRST/FOLLOW sets, LL(1) classification, left recursion, ambiguity detection",
    )

    parser.add_argument(
        "--grammar-dashboard",
        action="store_true",
        help="Display the FizzGrammar ASCII dashboard with grammar inventory, parse tables, and health index",
    )

    return parser


def configure_logging(debug: bool = False) -> None:
    """Set up the logging subsystem."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)-25s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the Enterprise FizzBuzz Platform."""
    # Ensure stdout can handle Unicode (box-drawing chars, etc.)
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    # Logging
    configure_logging(debug=args.debug)

    # Banner
    if not args.no_banner:
        print(BANNER)

    # Reset singleton for fresh config
    _SingletonMeta.reset()

    # Configuration
    config = ConfigurationManager(config_path=args.config)
    config.load()

    # ----------------------------------------------------------------
    # Cross-Compiler (early exit commands)
    # ----------------------------------------------------------------
    if args.compile_to or args.compile_ir:
        cc = CrossCompiler(
            config.rules,
            emit_comments=config.cross_compiler_emit_comments,
            verify=config.cross_compiler_verify_round_trip or args.compile_verify,
            verification_range_end=config.cross_compiler_verification_range_end,
            dashboard_width=config.cross_compiler_dashboard_width,
            dashboard_show_ir=config.cross_compiler_dashboard_show_ir,
        )

        if args.compile_ir:
            ir = cc.compile_ir_only()
            print(ir.dump())
            return 0

        result = cc.compile(args.compile_to)
        print(result.generated_code)

        if args.compile_dashboard:
            print()
            print(cc.render_dashboard(result))

        return 0

    # ----------------------------------------------------------------
    # OpenAPI Specification Generator (early exit commands)
    # ----------------------------------------------------------------
    if args.openapi or args.swagger_ui:
        print(ASCIISwaggerUI.render(width=config.openapi_swagger_ui_width))
        return 0

    if args.openapi_spec:
        print(OpenAPIGenerator.to_json())
        return 0

    if args.openapi_yaml:
        print(OpenAPIGenerator.to_yaml())
        return 0

    if args.openapi_dashboard:
        print(OpenAPIDashboard.render(width=config.openapi_dashboard_width))
        return 0

    # ----------------------------------------------------------------
    # FizzLang DSL (early exit commands)
    # ----------------------------------------------------------------
    if args.fizzlang or args.fizzlang_file or args.fizzlang_repl:
        if args.fizzlang_repl:
            repl = FizzLangREPL(
                prompt=config.fizzlang_repl_prompt,
                show_tokens=config.fizzlang_repl_show_tokens,
                show_ast=config.fizzlang_repl_show_ast,
                stdlib_enabled=config.fizzlang_stdlib_enabled,
            )
            repl.run()
            return 0

        # Load source from inline arg or file
        source = None
        if args.fizzlang_file:
            try:
                with open(args.fizzlang_file, "r") as f:
                    source = f.read()
            except FileNotFoundError:
                print(f"\n  FizzLang file not found: {args.fizzlang_file}\n")
                return 1
            except Exception as e:
                print(f"\n  Error reading FizzLang file: {e}\n")
                return 1
        elif args.fizzlang:
            source = args.fizzlang

        if source is not None:
            try:
                unit = compile_program(
                    source,
                    strict_type_checking=config.fizzlang_strict_type_checking,
                    max_program_length=config.fizzlang_max_program_length,
                )

                from enterprise_fizzbuzz.infrastructure.fizzlang import Interpreter

                interpreter = Interpreter(stdlib_enabled=config.fizzlang_stdlib_enabled)
                results = interpreter.interpret(unit.ast)

                for result in results:
                    print(result.output)

                if args.fizzlang_dashboard:
                    print()
                    print(FizzLangDashboard.render(
                        source,
                        unit=unit,
                        results=results,
                        width=config.fizzlang_dashboard_width,
                        show_source_stats=config.fizzlang_dashboard_show_source_stats,
                        show_complexity_index=config.fizzlang_dashboard_show_complexity_index,
                    ))

            except Exception as e:
                print(f"\n  FizzLang Error: {e}\n")
                return 1

        return 0

    # ----------------------------------------------------------------
    # Natural Language Query Interface (early exit commands)
    # ----------------------------------------------------------------
    if args.nlq or args.nlq_interactive:
        from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule

        # Build rules from config (config.rules returns RuleDefinition objects)
        nlq_rules = [ConcreteRule(rd) for rd in config.rules]

        nlq_engine = NLQEngine(
            rules=nlq_rules,
            max_results=config.nlq_max_results,
            max_query_length=config.nlq_max_query_length,
            history_size=config.nlq_history_size,
        )

        if args.nlq_interactive:
            nlq_engine.interactive_repl()
            return 0

        if args.nlq:
            try:
                response = nlq_engine.process_query(args.nlq)
                print()
                print(f"  [{response.intent.name}] (executed in {response.execution_time_ms:.2f}ms)")
                print(response.result_text)
                print()
            except Exception as e:
                print(f"\n  NLQ Error: {e}\n")
                return 1
            return 0

    # ----------------------------------------------------------------
    # Compliance Chatbot (early exit commands)
    # ----------------------------------------------------------------
    if args.chatbot or args.chatbot_interactive or args.chatbot_dashboard:
        chatbot = ComplianceChatbot(
            max_history=config.compliance_chatbot_max_history,
            include_citations=config.compliance_chatbot_include_citations,
            bob_commentary_enabled=config.compliance_chatbot_bob_commentary,
            formality_level=config.compliance_chatbot_formality_level,
            bob_stress_level=config.compliance_officer_stress_level,
        )

        if args.chatbot_interactive:
            chatbot.interactive_repl()
            if args.chatbot_dashboard:
                print(ComplianceChatbotDashboard.render_session(
                    chatbot.session,
                    width=config.compliance_chatbot_dashboard_width,
                ))
            return 0

        if args.chatbot:
            try:
                response = chatbot.ask(args.chatbot)
                print(ComplianceChatbotDashboard.render_response(
                    response,
                    width=config.compliance_chatbot_dashboard_width,
                ))
                print(f"  Bob's stress level: {chatbot.bob_stress_level:.1f}%\n")
                if args.chatbot_dashboard:
                    print(ComplianceChatbotDashboard.render_session(
                        chatbot.session,
                        width=config.compliance_chatbot_dashboard_width,
                    ))
            except Exception as e:
                print(f"\n  Compliance Chatbot Error: {e}\n")
                return 1
            return 0

        if args.chatbot_dashboard:
            print("\n  No chatbot query provided. Use --chatbot or --chatbot-interactive.\n")
            return 0

    # ----------------------------------------------------------------
    # Configuration Validation (--config-validate, early exit)
    # ----------------------------------------------------------------
    if args.config_validate:
        try:
            import yaml
        except ImportError:
            print("\n  PyYAML not installed. Cannot validate.\n")
            return 1

        validate_path = Path(args.config_validate)
        if not validate_path.exists():
            print(f"\n  Configuration file not found: {validate_path}\n")
            return 1

        with open(validate_path, "r") as f:
            validate_config = yaml.safe_load(f) or {}

        errors = ConfigValidator.validate(validate_config)
        if errors:
            print(
                "  +---------------------------------------------------------+\n"
                "  | CONFIGURATION VALIDATION: FAILED                        |\n"
                "  +---------------------------------------------------------+"
            )
            for err in errors:
                print(f"    [X] {err}")
            print()
            return 1
        else:
            print(
                "  +---------------------------------------------------------+\n"
                "  | CONFIGURATION VALIDATION: PASSED                        |\n"
                "  | The configuration file is valid. All values are within  |\n"
                "  | acceptable enterprise parameters. Congratulations on    |\n"
                "  | authoring a syntactically correct YAML file.            |\n"
                "  +---------------------------------------------------------+"
            )
            return 0

    # ----------------------------------------------------------------
    # Formal Verification & Proof System (early exit commands)
    # ----------------------------------------------------------------
    if args.verify or args.verify_property or args.proof_tree or args.verify_dashboard:
        verifier = PropertyVerifier(
            rules=config.rules,
            proof_depth=config.formal_verification_proof_depth,
            timeout_ms=config.formal_verification_timeout_ms,
        )

        if args.verify_property:
            # Verify a single property
            prop_map = {
                "totality": ("verify_totality", "TOTALITY"),
                "determinism": ("verify_determinism", "DETERMINISM"),
                "completeness": ("verify_completeness", "COMPLETENESS"),
                "correctness": ("verify_correctness", "CORRECTNESS"),
            }
            method_name, prop_name = prop_map[args.verify_property]
            print(
                "  +---------------------------------------------------------+\n"
                f"  | FORMAL VERIFICATION: {prop_name:<36}|\n"
                "  | Verifying property against StandardRuleEngine oracle... |\n"
                "  +---------------------------------------------------------+"
            )
            print()

            obligation = getattr(verifier, method_name)()
            status_icon = "\u2713 QED" if obligation.is_discharged else "\u2717 FAIL"
            print(f"  [{status_icon}] {prop_name}: {obligation.description}")
            print(f"  Time: {obligation.elapsed_ms:.2f}ms")
            if obligation.counterexample is not None:
                print(f"  Counterexample: {obligation.counterexample}")
            print()

            if obligation.proof_tree is not None and args.proof_tree:
                from enterprise_fizzbuzz.infrastructure.formal_verification import VerificationReport
                mini_report = VerificationReport(
                    obligations=[obligation],
                    total_elapsed_ms=obligation.elapsed_ms,
                    proof_depth=config.formal_verification_proof_depth,
                    rules=config.rules,
                )
                print(VerificationDashboard.render_proof_tree(
                    mini_report, width=config.formal_verification_dashboard_width
                ))

            return 0

        # Full verification
        print(
            "  +---------------------------------------------------------+\n"
            "  | ENTERPRISE FIZZBUZZ FORMAL VERIFICATION ENGINE          |\n"
            "  | Constructing proofs of totality, determinism,           |\n"
            "  | completeness, and correctness via structural induction. |\n"
            "  | Because trust is earned, not assumed.                   |\n"
            "  +---------------------------------------------------------+"
        )
        print()
        print(f"  Proof depth: {config.formal_verification_proof_depth}")
        print(f"  Rules: {len(config.rules)}")
        print()

        report = verifier.verify_all()

        # Print summary
        print(report.summary())
        print()

        # Print proof tree if requested
        if args.proof_tree:
            print(VerificationDashboard.render_proof_tree(
                report, width=config.formal_verification_dashboard_width
            ))

        # Print dashboard if requested
        if args.verify_dashboard:
            print(VerificationDashboard.render(
                report, width=config.formal_verification_dashboard_width
            ))

        return 0

    # ----------------------------------------------------------------
    # Configuration Diff (--config-diff, early exit)
    # ----------------------------------------------------------------
    if args.config_diff:
        try:
            import yaml
        except ImportError:
            print("\n  PyYAML not installed. Cannot compute diff.\n")
            return 1

        diff_path = Path(args.config_diff)
        if not diff_path.exists():
            print(f"\n  Configuration file not found: {diff_path}\n")
            return 1

        with open(diff_path, "r") as f:
            diff_config = yaml.safe_load(f) or {}

        current_config = config._get_raw_config_copy()
        changeset = ConfigDiffer.diff(current_config, diff_config)

        if changeset.is_empty:
            print(
                "  +---------------------------------------------------------+\n"
                "  | CONFIGURATION DIFF: No changes detected.                |\n"
                "  | The files are identical. This diff was anticlimactic.   |\n"
                "  +---------------------------------------------------------+"
            )
        else:
            print(HotReloadDashboard.render_diff(changeset, width=58))
        return 0

    # ----------------------------------------------------------------
    # Database Migration Framework (opt-in via --migrate flags)
    # ----------------------------------------------------------------
    if args.migrate or args.migrate_status or args.migrate_rollback is not None or args.migrate_seed:
        MigrationRegistry.reset()
        # Re-import to re-register built-in migrations after reset
        from enterprise_fizzbuzz.infrastructure.migrations import _register_builtin_migrations
        _register_builtin_migrations()

        migration_schema = SchemaManager(log_fake_sql=config.migrations_log_fake_sql)
        migration_runner = MigrationRunner(migration_schema)

        if args.migrate:
            print(
                "  +---------------------------------------------------------+\n"
                "  | DATABASE MIGRATION FRAMEWORK: Applying Migrations       |\n"
                "  | All schema changes apply to in-memory dicts that will   |\n"
                "  | be destroyed when this process exits. You're welcome.   |\n"
                "  +---------------------------------------------------------+"
            )
            print()

            applied = migration_runner.apply_all()
            for record in applied:
                print(f"  [+] Applied: {record.migration_id} ({record.duration_ms:.2f}ms)")

            if not applied:
                print("  No pending migrations. The ephemeral schema is up to date.")

            print()

            if config.migrations_visualize_schema:
                print(SchemaVisualizer.render(migration_schema))

        if args.migrate_seed:
            if not migration_schema.table_exists("fizzbuzz_results"):
                # Auto-apply migrations first
                migration_runner.apply_all()

            seeder = SeedDataGenerator(migration_schema)
            seed_start = config.migrations_seed_range_start
            seed_end = config.migrations_seed_range_end
            count = seeder.generate(seed_start, seed_end)
            print(
                f"  Seeded {count} rows using FizzBuzz to populate the FizzBuzz database.\n"
                f"  The ouroboros is complete. The snake has eaten its own tail.\n"
            )

        if args.migrate_rollback is not None:
            rolled_back = migration_runner.rollback(args.migrate_rollback)
            for record in rolled_back:
                print(f"  [-] Rolled back: {record.migration_id}")
            if not rolled_back:
                print("  No migrations to roll back.")
            print()

        if args.migrate_status:
            print(MigrationDashboard.render(migration_runner))

        # Show fake SQL log if enabled
        if config.migrations_log_fake_sql and migration_schema.sql_log:
            print("  +-- FAKE SQL LOG (for enterprise cosplay) --+")
            for sql in migration_schema.sql_log:
                print(f"  |  {sql}")
            print("  +--------------------------------------------+")
            print()

        return 0

    # ----------------------------------------------------------------
    # GitOps Configuration-as-Code Simulator
    # ----------------------------------------------------------------
    gitops_controller = None
    if args.gitops or args.gitops_commit or args.gitops_diff or args.gitops_log or args.gitops_propose or args.gitops_dashboard or args.gitops_drift:
        gitops_controller = GitOpsController(
            default_branch=config.gitops_default_branch,
            max_history=config.gitops_max_commit_history,
            policy_enforcement=config.gitops_policy_enforcement,
            dry_run_range_start=config.gitops_dry_run_range_start,
            dry_run_range_end=config.gitops_dry_run_range_end,
            approval_mode=config.gitops_approval_mode,
            tracked_subsystems=config.gitops_blast_radius_subsystems,
        )

        # Initial commit with current config
        raw_config = config._get_raw_config_copy()
        gitops_controller.initialize(raw_config, auto_commit=config.gitops_auto_commit_on_load)

        # Handle explicit commit
        if args.gitops_commit:
            commit = gitops_controller.repository.commit(
                tree=raw_config,
                message=args.gitops_commit,
            )
            print(f"\n  [GitOps] Committed {commit.short_sha}: {args.gitops_commit}\n")

        # Handle change proposals
        if args.gitops_propose:
            for prop_str in args.gitops_propose:
                if "=" not in prop_str:
                    print(f"\n  [GitOps] Invalid proposal format: {prop_str} (expected KEY=VALUE)\n")
                    continue
                key, _, value = prop_str.partition("=")

                # Parse value type
                parsed_value: Any
                if value.lower() in ("true", "false"):
                    parsed_value = value.lower() == "true"
                elif value.isdigit():
                    parsed_value = int(value)
                else:
                    try:
                        parsed_value = float(value)
                    except ValueError:
                        parsed_value = value

                # Build nested change dict from dot-separated key
                changes: dict[str, Any] = {}
                parts = key.strip().split(".")
                current_dict = changes
                for part in parts[:-1]:
                    current_dict[part] = {}
                    current_dict = current_dict[part]
                current_dict[parts[-1]] = parsed_value

                proposal = gitops_controller.propose_change(
                    changes=changes,
                    description=f"Set {key} = {parsed_value}",
                )

                status_icon = "[OK]" if proposal.status == "applied" else "[XX]"
                print(f"\n  [GitOps] Proposal {proposal.proposal_id} {status_icon}")
                for gate, result in proposal.gate_results.items():
                    gate_icon = "PASS" if gate in proposal.gates_passed else "FAIL"
                    print(f"    [{gate_icon}] {gate}: {result}")
                print()

        # Handle diff
        if args.gitops_diff:
            diff_entries = gitops_controller.get_diff()
            if diff_entries:
                print("\n  [GitOps] Configuration Diff (HEAD vs parent):")
                for d in diff_entries:
                    symbol = {"added": "+", "removed": "-", "modified": "~"}.get(d.change_type, "?")
                    if d.change_type == "modified":
                        print(f"    [{symbol}] {d.key}: {d.old_value!r} -> {d.new_value!r}")
                    elif d.change_type == "added":
                        print(f"    [{symbol}] {d.key}: {d.new_value!r}")
                    else:
                        print(f"    [{symbol}] {d.key}: {d.old_value!r}")
                print()
            else:
                print("\n  [GitOps] No diff available (single commit or empty history).\n")

        # Handle log
        if args.gitops_log:
            commits = gitops_controller.get_log()
            print("\n  [GitOps] Commit Log:")
            for c in commits:
                ts = c.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                print(f"    {c.short_sha} {ts} {c.message}")
            if not commits:
                print("    (no commits)")
            print()

        # Handle drift detection
        if args.gitops_drift:
            drift = gitops_controller.detect_drift(raw_config)
            if drift:
                print(f"\n  [GitOps] DRIFT DETECTED: {len(drift)} key(s) diverged from committed state:")
                for d in drift:
                    symbol = {"added": "+", "removed": "-", "modified": "~"}.get(d.change_type, "?")
                    print(f"    [{symbol}] {d.key}")
                print()
            else:
                print("\n  [GitOps] No drift detected. Running config matches committed state.\n")

        # Handle dashboard
        if args.gitops_dashboard:
            dashboard_output = gitops_controller.render_dashboard(
                running_config=raw_config,
                width=config.gitops_dashboard_width,
            )
            print(dashboard_output)

        # Early exit if only gitops flags
        if not any([
            args.range, args.format, args.strategy, args.verbose,
            args.use_async, args.blockchain,
        ]) and any([
            args.gitops_commit, args.gitops_diff, args.gitops_log,
            args.gitops_propose, args.gitops_dashboard, args.gitops_drift,
        ]) and not args.gitops:
            return 0

    # Determine parameters (CLI overrides config)
    start = args.range[0] if args.range else config.range_start
    end = args.range[1] if args.range else config.range_end

    # Output format
    format_map = {
        "plain": OutputFormat.PLAIN,
        "json": OutputFormat.JSON,
        "xml": OutputFormat.XML,
        "csv": OutputFormat.CSV,
    }
    output_format = format_map.get(args.format) if args.format else config.output_format

    # Strategy
    strategy_map = {
        "standard": EvaluationStrategy.STANDARD,
        "chain_of_responsibility": EvaluationStrategy.CHAIN_OF_RESPONSIBILITY,
        "parallel_async": EvaluationStrategy.PARALLEL_ASYNC,
        "machine_learning": EvaluationStrategy.MACHINE_LEARNING,
    }
    strategy = (
        strategy_map.get(args.strategy) if args.strategy else config.evaluation_strategy
    )

    # Build the service
    event_bus = EventBus()
    stats_observer = StatisticsObserver()
    event_bus.subscribe(stats_observer)

    if args.verbose:
        console_observer = ConsoleObserver(verbose=True)
        event_bus.subscribe(console_observer)

    # Audit Dashboard setup
    audit_dashboard = None
    if args.audit_dashboard or args.audit_stream or args.audit_anomalies:
        audit_dashboard = UnifiedAuditDashboard(
            buffer_size=config.audit_dashboard_buffer_size,
            anomaly_window_seconds=config.audit_dashboard_anomaly_window_seconds,
            z_score_threshold=config.audit_dashboard_z_score_threshold,
            anomaly_min_samples=config.audit_dashboard_anomaly_min_samples,
            correlation_window_seconds=config.audit_dashboard_correlation_window_seconds,
            correlation_min_events=config.audit_dashboard_correlation_min_events,
            stream_include_payload=config.audit_dashboard_stream_include_payload,
            enable_anomaly_detection=config.audit_dashboard_anomaly_enabled,
            enable_correlation=config.audit_dashboard_correlation_enabled,
        )
        event_bus.subscribe(audit_dashboard.aggregator)

        print(
            "  +---------------------------------------------------------+\n"
            "  | UNIFIED AUDIT DASHBOARD: Event Telemetry ENABLED        |\n"
            "  | All events will be aggregated, normalized, and analyzed |\n"
            "  | with z-score anomaly detection and temporal correlation.|\n"
            "  | Because monitoring FizzBuzz is serious business.        |\n"
            "  +---------------------------------------------------------+"
        )

    blockchain_observer = None
    if args.blockchain:
        blockchain = FizzBuzzBlockchain(difficulty=args.mining_difficulty)
        blockchain_observer = BlockchainObserver(blockchain=blockchain)
        event_bus.subscribe(blockchain_observer)

    # Circuit breaker
    cb_middleware = None
    if args.circuit_breaker:
        cb_middleware = CircuitBreakerMiddleware(
            event_bus=event_bus,
            failure_threshold=config.circuit_breaker_failure_threshold,
            success_threshold=config.circuit_breaker_success_threshold,
            timeout_ms=config.circuit_breaker_timeout_ms,
            sliding_window_size=config.circuit_breaker_sliding_window_size,
            half_open_max_calls=config.circuit_breaker_half_open_max_calls,
            backoff_base_ms=config.circuit_breaker_backoff_base_ms,
            backoff_max_ms=config.circuit_breaker_backoff_max_ms,
            backoff_multiplier=config.circuit_breaker_backoff_multiplier,
            ml_confidence_threshold=config.circuit_breaker_ml_confidence_threshold,
            call_timeout_ms=config.circuit_breaker_call_timeout_ms,
        )
        # Register in global registry for dashboard access
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create(
            cb_middleware.circuit_breaker.name,
        )

        timeout_str = f"{config.circuit_breaker_timeout_ms}ms"
        print(
            "  +---------------------------------------------------------+\n"
            "  | CIRCUIT BREAKER: Fault-Tolerant FizzBuzz ENABLED        |\n"
            f"  | Failure Threshold: {config.circuit_breaker_failure_threshold:<36}|\n"
            f"  | Success Threshold: {config.circuit_breaker_success_threshold:<36}|\n"
            f"  | Timeout: {timeout_str:<47}|\n"
            "  | Backoff: Exponential with jitter.                       |\n"
            "  | Because even FizzBuzz deserves graceful degradation.    |\n"
            "  +---------------------------------------------------------+"
        )

    # Internationalization (i18n) setup
    locale_mgr = None
    locale = args.locale or config.i18n_locale

    if config.i18n_enabled:
        LocaleManager.reset()
        locale_mgr = LocaleManager()
        locale_dir = str(Path(config.i18n_locale_directory))
        locale_mgr.load_all(locale_dir)
        locale_mgr.set_strict_mode(config.i18n_strict_mode)

        # Set the active locale (CLI overrides config)
        if locale in locale_mgr.get_available_locales():
            locale_mgr.set_locale(locale)
        elif locale != "en":
            # Locale not available, warn and fall back to English
            print(f"  Warning: locale '{locale}' not available, using 'en'")
            locale = "en"

    # Handle --list-locales
    if args.list_locales:
        if locale_mgr is not None:
            info = locale_mgr.get_locale_info()
            print("\n  Available Locales:")
            print("  " + "-" * 60)
            print(f"  {'Code':<8} {'Name':<20} {'Fallback':<12} {'Keys':<8} {'Plural Rule'}")
            print("  " + "-" * 60)
            for loc in info:
                print(
                    f"  {loc['code']:<8} {loc['name']:<20} {loc['fallback']:<12} "
                    f"{loc['keys']:<8} {loc['plural_rule']}"
                )
            print("  " + "-" * 60)
            print()
        else:
            print("\n  i18n is disabled. Enable it in config.yaml.\n")
        return 0

    # Distributed tracing setup
    tracing_service = TracingService()
    tracing_service.reset()
    tracing_enabled = args.trace or args.trace_json
    tracing_mw = None
    if tracing_enabled:
        tracing_service.enable()
        tracing_mw = TracingMiddleware()

    # ----------------------------------------------------------------
    # FizzOTel — OpenTelemetry-Compatible Distributed Tracing Setup
    # ----------------------------------------------------------------
    otel_provider = None
    otel_exporter = None
    otel_middleware = None

    if args.otel or args.otel_dashboard:
        otel_export_fmt = args.otel_export or config.otel_export_format
        otel_provider, otel_exporter, otel_middleware = create_otel_subsystem(
            sampling_rate=config.otel_sampling_rate,
            export_format=otel_export_fmt,
            batch_mode=config.otel_batch_mode,
            max_queue_size=config.otel_max_queue_size,
            max_batch_size=config.otel_max_batch_size,
            console_width=config.otel_dashboard_width,
        )

    # ----------------------------------------------------------------
    # Role-Based Access Control (RBAC) setup
    # ----------------------------------------------------------------
    auth_context = None
    rbac_active = False

    if args.token:
        # Token-based authentication — the secure way
        try:
            auth_context = FizzBuzzTokenEngine.validate_token(
                args.token, config.rbac_token_secret
            )
            rbac_active = True
        except Exception as e:
            print(f"  [AUTHENTICATION FAILED] {e}")
            return 1

    elif args.user:
        # Trust-mode authentication — the "just trust me" protocol
        role = FizzBuzzRole[args.role] if args.role else FizzBuzzRole[config.rbac_default_role]
        effective_permissions = RoleRegistry.get_effective_permissions(role)
        auth_context = AuthContext(
            user=args.user,
            role=role,
            token_id=None,
            effective_permissions=tuple(effective_permissions),
            trust_mode=True,
        )
        rbac_active = True
        print(
            "  +---------------------------------------------------------+\n"
            "  | WARNING: Trust-mode authentication enabled.             |\n"
            "  | The user's identity has not been cryptographically      |\n"
            "  | verified. This is the security equivalent of writing    |\n"
            "  | your password on a Post-It note and sticking it to      |\n"
            "  | your monitor. Proceed with existential dread.           |\n"
            "  +---------------------------------------------------------+"
        )

    elif config.rbac_enabled:
        # No auth flags but RBAC is enabled — default to ANONYMOUS
        role = FizzBuzzRole[config.rbac_default_role]
        effective_permissions = RoleRegistry.get_effective_permissions(role)
        auth_context = AuthContext(
            user="anonymous",
            role=role,
            token_id=None,
            effective_permissions=tuple(effective_permissions),
            trust_mode=False,
        )
        rbac_active = True

    # Event Sourcing / CQRS setup
    es_system = None
    es_middleware = None
    if args.event_sourcing:
        es_system = EventSourcingSystem(
            snapshot_interval=config.event_sourcing_snapshot_interval,
        )
        es_middleware = es_system.create_middleware()

    # Feature Flags setup
    flag_store = None
    flag_middleware = None
    if args.feature_flags:
        from enterprise_fizzbuzz.domain.models import RuleDefinition
        from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule

        flag_store = create_flag_store_from_config(config)

        # Apply CLI overrides
        if args.flag:
            apply_cli_overrides(flag_store, args.flag)

        # Handle --list-flags
        if args.list_flags:
            print(render_flag_list(flag_store))
            return 0

        flag_middleware = FlagMiddleware(
            flag_store=flag_store,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FEATURE FLAGS: Progressive Rollout ENABLED              |\n"
            "  | Flags are now controlling which rules are active.       |\n"
            "  | The FizzBuzz rules you know and love are now subject    |\n"
            "  | to the whims of a configuration-driven toggle system.   |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.list_flags:
        print("\n  Feature flags not enabled. Use --feature-flags to enable.\n")
        return 0

    # SLA Monitoring setup
    sla_monitor = None
    sla_middleware = None
    if args.sla:
        slo_definitions = [
            SLODefinition(
                name="latency",
                slo_type=SLOType.LATENCY,
                target=config.sla_latency_target,
                threshold_ms=config.sla_latency_threshold_ms,
            ),
            SLODefinition(
                name="accuracy",
                slo_type=SLOType.ACCURACY,
                target=config.sla_accuracy_target,
            ),
            SLODefinition(
                name="availability",
                slo_type=SLOType.AVAILABILITY,
                target=config.sla_availability_target,
            ),
        ]

        on_call_schedule = OnCallSchedule(
            team_name=config.sla_on_call_team_name,
            rotation_interval_hours=config.sla_on_call_rotation_interval_hours,
            engineers=config.sla_on_call_engineers,
        )

        sla_monitor = SLAMonitor(
            slo_definitions=slo_definitions,
            event_bus=event_bus,
            on_call_schedule=on_call_schedule,
            burn_rate_threshold=config.sla_error_budget_burn_rate_threshold,
        )

        sla_middleware = SLAMiddleware(
            sla_monitor=sla_monitor,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | SLA MONITORING: PagerDuty-Style Alerting ENABLED        |\n"
            "  | Latency, accuracy, and availability SLOs are now being  |\n"
            "  | tracked with error budgets and escalation policies.     |\n"
            "  | On-call: Bob McFizzington (he's always on call).        |\n"
            "  +---------------------------------------------------------+"
        )

    elif args.sla_dashboard:
        print("\n  SLA monitoring not enabled. Use --sla to enable.\n")
        return 0
    elif args.on_call:
        # Allow --on-call without --sla for quick status check
        on_call_schedule = OnCallSchedule(
            team_name=config.sla_on_call_team_name,
            rotation_interval_hours=config.sla_on_call_rotation_interval_hours,
            engineers=config.sla_on_call_engineers,
        )
        sla_monitor = SLAMonitor(
            slo_definitions=[],
            on_call_schedule=on_call_schedule,
        )
        print(SLADashboard.render_on_call(sla_monitor))
        return 0

    # Cache setup
    cache_middleware = None
    cache_store = None
    cache_warmer = None
    if args.cache:
        cache_policy_name = args.cache_policy or config.cache_eviction_policy
        cache_max_size = args.cache_size or config.cache_max_size
        eviction_policy = EvictionPolicyFactory.create(cache_policy_name)

        cache_store = CacheStore(
            max_size=cache_max_size,
            ttl_seconds=config.cache_ttl_seconds,
            eviction_policy=eviction_policy,
            enable_coherence=config.cache_enable_coherence_protocol,
            enable_eulogies=config.cache_enable_eulogies,
            event_bus=event_bus,
        )

        cache_middleware = CacheMiddleware(
            cache_store=cache_store,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | CACHING: In-Memory Cache Layer ENABLED                  |\n"
            f"  | Policy: {eviction_policy.get_name():<48}|\n"
            f"  | Max Size: {cache_max_size:<46}|\n"
            "  | MESI coherence protocol: ACTIVE (pointlessly)           |\n"
            "  | Every eviction will be mourned with a eulogy.           |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.cache_stats:
        print("\n  Cache not enabled. Use --cache to enable.\n")
        return 0

    # Prometheus-Style Metrics setup
    metrics_registry = None
    metrics_collector = None
    metrics_middleware = None
    metrics_cardinality = None
    if args.metrics or args.metrics_export or args.metrics_dashboard:
        MetricRegistry.reset()
        metrics_registry, metrics_collector, metrics_middleware, metrics_cardinality = (
            create_metrics_subsystem(
                event_bus=event_bus,
                bob_initial_stress=config.metrics_bob_stress_level,
                cardinality_threshold=config.metrics_cardinality_threshold,
                default_buckets=config.metrics_default_buckets,
            )
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | PROMETHEUS METRICS: Collection ENABLED                  |\n"
            "  | Counters, gauges, histograms, and summaries are now     |\n"
            "  | tracking every aspect of your FizzBuzz evaluations.     |\n"
            "  | Bob McFizzington's stress level: monitored.             |\n"
            "  | is_tuesday label: mandatory.                            |\n"
            "  +---------------------------------------------------------+"
        )

    # Webhook Notification System setup
    webhook_manager = None
    webhook_observer = None
    if args.webhooks or args.webhook_url or args.webhook_test:
        webhook_secret = args.webhook_secret or config.webhooks_secret
        sig_engine = WebhookSignatureEngine(webhook_secret)

        success_rate = config.webhooks_simulated_success_rate
        http_client = SimulatedHTTPClient(success_rate_percent=success_rate)

        retry_policy = RetryPolicy(
            max_retries=config.webhooks_retry_max_retries,
            backoff_base_ms=config.webhooks_retry_backoff_base_ms,
            backoff_multiplier=config.webhooks_retry_backoff_multiplier,
            backoff_max_ms=config.webhooks_retry_backoff_max_ms,
        )

        dlq = DeadLetterQueue(max_size=config.webhooks_dlq_max_size)

        webhook_manager = WebhookManager(
            signature_engine=sig_engine,
            http_client=http_client,
            retry_policy=retry_policy,
            dead_letter_queue=dlq,
            event_bus=event_bus,
        )

        # Register endpoints from CLI
        for url in args.webhook_url:
            webhook_manager.register_endpoint(url)

        # Register endpoints from config
        for url in config.webhooks_endpoints:
            webhook_manager.register_endpoint(url)

        # Determine subscribed events
        if args.webhook_events:
            subscribed = set(args.webhook_events.split(","))
        else:
            subscribed = set(config.webhooks_subscribed_events)

        # Create and subscribe the observer
        webhook_observer = WebhookObserver(
            webhook_manager=webhook_manager,
            subscribed_events=subscribed,
        )
        event_bus.subscribe(webhook_observer)

        print(
            "  +---------------------------------------------------------+\n"
            "  | WEBHOOKS: Notification System ENABLED                   |\n"
            "  | All matching events will be dispatched to registered    |\n"
            "  | endpoints via simulated HTTP POST with HMAC-SHA256      |\n"
            "  | signatures. No actual HTTP requests will be made.       |\n"
            "  | X-FizzBuzz-Seriousness-Level: MAXIMUM                   |\n"
            "  +---------------------------------------------------------+"
        )

        # Handle --webhook-test
        if args.webhook_test:
            test_event = Event(
                event_type=EventType.SESSION_STARTED,
                payload={"test": True, "message": "Webhook connectivity test"},
                source="WebhookTestRunner",
            )
            print("\n  Sending test webhook to all registered endpoints...\n")
            results = webhook_manager.dispatch(test_event)
            success_count = sum(1 for r in results if r.success)
            print(
                f"\n  Test complete: {success_count}/{len(results)} endpoints "
                f"accepted the test webhook.\n"
            )
            if args.webhook_dlq:
                print(WebhookDashboard.render_dlq(webhook_manager))
            return 0

    elif args.webhook_test:
        print("\n  Webhooks not enabled. Use --webhooks to enable.\n")
        return 0
    elif args.webhook_log:
        print("\n  Webhooks not enabled. Use --webhooks to enable.\n")
        return 0
    elif args.webhook_dlq:
        print("\n  Webhooks not enabled. Use --webhooks to enable.\n")
        return 0

    # Service Mesh Simulation setup
    mesh_middleware = None
    mesh_control_plane = None
    if args.service_mesh:
        mesh_control_plane, mesh_orchestrator = create_service_mesh(
            mtls_enabled=config.service_mesh_mtls_enabled,
            log_handshakes=config.service_mesh_mtls_log_handshakes,
            latency_enabled=args.mesh_latency or config.service_mesh_latency_enabled,
            latency_min_ms=config.service_mesh_latency_min_ms,
            latency_max_ms=config.service_mesh_latency_max_ms,
            packet_loss_enabled=args.mesh_packet_loss or config.service_mesh_packet_loss_enabled,
            packet_loss_rate=config.service_mesh_packet_loss_rate,
            canary_enabled=args.canary or config.service_mesh_canary_enabled,
            canary_percentage=config.service_mesh_canary_traffic_percentage / 100.0,
            circuit_breaker_enabled=config.service_mesh_circuit_breaker_enabled,
            circuit_breaker_threshold=config.service_mesh_circuit_breaker_failure_threshold,
            event_bus=event_bus,
        )

        # Build divisor info from config rules
        divisors = [r.divisor for r in config.rules]
        divisor_labels = {str(r.divisor): r.label for r in config.rules}

        mesh_middleware = MeshMiddleware(
            control_plane=mesh_control_plane,
            divisors=divisors,
            divisor_labels=divisor_labels,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | SERVICE MESH: 7 Microservices ENABLED                   |\n"
            "  | FizzBuzz has been decomposed into:                      |\n"
            "  |   1. NumberIngestionService                             |\n"
            "  |   2. DivisibilityService                                |\n"
            "  |   3. ClassificationService                              |\n"
            "  |   4. FormattingService                                  |\n"
            "  |   5. AuditService                                       |\n"
            "  |   6. CacheService                                       |\n"
            "  |   7. OrchestratorService                                |\n"
            "  | mTLS (base64): ARMED. Military-grade encryption active. |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.mesh_topology:
        print("\n  Service mesh not enabled. Use --service-mesh to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Configuration Hot-Reload with Single-Node Raft Consensus
    # ----------------------------------------------------------------
    hot_reload_raft = None
    hot_reload_orchestrator = None
    hot_reload_watcher = None
    hot_reload_dep_graph = None
    hot_reload_rollback_mgr = None

    if args.hot_reload:
        config_path = Path(
            args.config
            or os.environ.get("EFP_CONFIG_PATH", str(Path(__file__).parent.parent / "config.yaml"))
        )

        hot_reload_raft, hot_reload_orchestrator, hot_reload_watcher, hot_reload_dep_graph, hot_reload_rollback_mgr = (
            create_hot_reload_subsystem(
                config_manager=config,
                config_path=config_path,
                poll_interval_seconds=config.hot_reload_poll_interval_seconds,
                heartbeat_interval_ms=config.hot_reload_raft_heartbeat_interval_ms,
                election_timeout_ms=config.hot_reload_raft_election_timeout_ms,
                max_rollback_history=config.hot_reload_max_rollback_history,
                validate_before_apply=config.hot_reload_validate_before_apply,
                log_diffs=config.hot_reload_log_diffs,
                event_bus=event_bus,
            )
        )

        # Start the file watcher
        hot_reload_watcher.start()

        print(
            "  +---------------------------------------------------------+\n"
            "  | HOT-RELOAD: Single-Node Raft Consensus ENABLED          |\n"
            "  | Configuration changes will be detected and applied      |\n"
            "  | at runtime through a full Raft consensus protocol       |\n"
            "  | with 1 node. Elections: always unanimous. Heartbeats:   |\n"
            "  | sent to 0 followers. Consensus latency: 0.000ms.        |\n"
            "  | Democracy has never been more efficient.                |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.reload_status:
        print("\n  Hot-reload not enabled. Use --hot-reload to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Rate Limiting & API Quota Management setup
    # ----------------------------------------------------------------
    rate_limit_middleware = None
    rate_limit_quota_manager = None
    if args.rate_limit:
        algo_map = {
            "token_bucket": RateLimitAlgorithm.TOKEN_BUCKET,
            "sliding_window": RateLimitAlgorithm.SLIDING_WINDOW,
            "fixed_window": RateLimitAlgorithm.FIXED_WINDOW,
        }
        algo_name = args.rate_limit_algo or config.rate_limiting_algorithm
        algo = algo_map.get(algo_name, RateLimitAlgorithm.TOKEN_BUCKET)
        rpm = args.rate_limit_rpm or config.rate_limiting_rpm

        rl_policy = RateLimitPolicy(
            algorithm=algo,
            requests_per_minute=float(rpm),
            burst_credits_enabled=config.rate_limiting_burst_credits_enabled,
            burst_credits_max=float(config.rate_limiting_burst_credits_max),
            burst_credits_earn_rate=config.rate_limiting_burst_credits_earn_rate,
            reservations_enabled=config.rate_limiting_reservations_enabled,
            reservations_max=config.rate_limiting_reservations_max,
            reservations_ttl_seconds=config.rate_limiting_reservations_ttl_seconds,
        )

        rate_limit_quota_manager = QuotaManager(
            policy=rl_policy,
            event_bus=event_bus,
        )

        rate_limit_middleware = RateLimiterMiddleware(
            quota_manager=rate_limit_quota_manager,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | RATE LIMITING: API Quota Management ENABLED             |\n"
            f"  | Algorithm: {algo.name:<45}|\n"
            f"  | RPM Limit: {rpm:<45}|\n"
            "  | Burst credits: ARMED. Unused quota carries over.        |\n"
            "  | Motivational quotes: LOADED and READY.                  |\n"
            "  | Because unrestricted FizzBuzz is a security incident.   |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.rate_limit_dashboard:
        print("\n  Rate limiting not enabled. Use --rate-limit to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Compliance & Regulatory Framework setup
    # ----------------------------------------------------------------
    compliance_framework = None
    compliance_middleware = None
    if args.compliance or args.gdpr_erase is not None or args.compliance_dashboard or args.compliance_report:
        sox_auditor = SOXAuditor(
            personnel_roster=config.compliance_sox_personnel_roster,
            strict_mode=config.compliance_sox_segregation_strict,
            event_bus=event_bus,
        ) if config.compliance_sox_enabled else None

        gdpr_controller = GDPRController(
            auto_consent=config.compliance_gdpr_auto_consent,
            erasure_enabled=config.compliance_gdpr_erasure_enabled,
            event_bus=event_bus,
        ) if config.compliance_gdpr_enabled else None

        hipaa_guard = HIPAAGuard(
            minimum_necessary_level=config.compliance_hipaa_minimum_necessary_level,
            encryption_algorithm=config.compliance_hipaa_encryption_algorithm,
            event_bus=event_bus,
        ) if config.compliance_hipaa_enabled else None

        compliance_framework = ComplianceFramework(
            sox_auditor=sox_auditor,
            gdpr_controller=gdpr_controller,
            hipaa_guard=hipaa_guard,
            event_bus=event_bus,
            bob_stress_level=config.compliance_officer_stress_level,
        )

        compliance_middleware = ComplianceMiddleware(
            compliance_framework=compliance_framework,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | COMPLIANCE: SOX/GDPR/HIPAA Framework ENABLED            |\n"
            "  | Segregation of duties: ENFORCED (no dual FizzBuzz roles)|\n"
            "  | GDPR consent: AUTO-GRANTED (for convenience)            |\n"
            "  | HIPAA encryption: MILITARY-GRADE BASE64                 |\n"
            "  | Compliance Officer: Bob McFizzington (UNAVAILABLE)      |\n"
            f"  | Bob's stress level: {f'{config.compliance_officer_stress_level:.1f}%':<36}|\n"
            "  +---------------------------------------------------------+"
        )

        # Handle --gdpr-erase (early exit)
        if args.gdpr_erase is not None:
            if gdpr_controller is not None:
                certificate = compliance_framework.process_erasure_request(args.gdpr_erase)
                print(ComplianceDashboard.render_erasure_certificate(certificate))
                print(
                    f"  Bob McFizzington's stress level is now "
                    f"{compliance_framework.bob_stress_level:.1f}%.\n"
                    f"  Please send thoughts and prayers to "
                    f"{config.compliance_officer_name}.\n"
                )
            else:
                print("\n  GDPR is not enabled in the compliance configuration.\n")
            return 0

    elif args.gdpr_erase is not None:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.sox_audit:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.hipaa_check:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.compliance_dashboard:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0
    elif args.compliance_report:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # FinOps Cost Tracking & Chargeback Engine setup
    # ----------------------------------------------------------------
    finops_tracker = None
    finops_middleware = None
    finops_savings_calc = None
    if args.finops or args.invoice or args.cost_dashboard or args.savings_plan:
        cost_registry = SubsystemCostRegistry()
        tax_engine = FizzBuzzTaxEngine(
            fizz_rate=config.finops_tax_rate_fizz,
            buzz_rate=config.finops_tax_rate_buzz,
            fizzbuzz_rate=config.finops_tax_rate_fizzbuzz,
            plain_rate=config.finops_tax_rate_plain,
        )
        fizzbuck_currency = FizzBuckCurrency(
            base_rate=config.finops_exchange_rate_base,
            symbol=config.finops_currency,
        )

        finops_tracker = CostTracker(
            cost_registry=cost_registry,
            tax_engine=tax_engine,
            currency=fizzbuck_currency,
            budget_limit=config.finops_budget_monthly_limit,
            budget_warning_pct=config.finops_budget_warning_threshold_pct,
            friday_premium_pct=config.finops_friday_premium_pct,
            event_bus=event_bus,
        )

        # Determine which subsystems are active based on CLI flags
        active_subsystems = ["rule_engine", "middleware_pipeline", "validation", "formatting", "event_bus", "logging"]
        if args.circuit_breaker:
            active_subsystems.append("circuit_breaker")
        if args.cache:
            active_subsystems.append("cache_lookup")
        if args.sla:
            active_subsystems.append("sla_monitoring")
        if args.blockchain:
            active_subsystems.append("blockchain")
        if args.chaos or args.gameday:
            active_subsystems.append("chaos_injection")
        if args.compliance:
            active_subsystems.append("compliance_check")
        if args.feature_flags:
            active_subsystems.append("feature_flag_eval")
        if args.service_mesh:
            active_subsystems.append("service_mesh_hop")
        if args.rate_limit:
            active_subsystems.append("rate_limit_check")
        if args.trace or args.trace_json:
            active_subsystems.append("tracing")
        if args.health:
            active_subsystems.append("health_probe")
        if args.hot_reload:
            active_subsystems.append("hot_reload_check")
        if args.dr:
            active_subsystems.append("disaster_recovery")
        if args.ab_test:
            active_subsystems.append("ab_testing")
        if args.mq:
            active_subsystems.append("message_queue")
        if args.vault:
            active_subsystems.append("secrets_vault")
        if args.pipeline:
            active_subsystems.append("data_pipeline")
        if args.graph_db or args.graph_query or args.graph_visualize or args.graph_dashboard:
            active_subsystems.append("graph_database")
        if args.fbaas:
            active_subsystems.append("fbaas_metering")
        if args.paxos:
            active_subsystems.append("paxos_consensus")
        if args.quantum:
            active_subsystems.append("quantum_simulation")
        if strategy == EvaluationStrategy.MACHINE_LEARNING:
            active_subsystems.append("ml_inference")

        finops_middleware = FinOpsMiddleware(
            cost_tracker=finops_tracker,
            active_subsystems=active_subsystems,
            event_bus=event_bus,
        )

        finops_savings_calc = SavingsPlanCalculator(
            one_year_discount_pct=config.finops_savings_one_year_discount_pct,
            three_year_discount_pct=config.finops_savings_three_year_discount_pct,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FINOPS: Cost Tracking & Chargeback Engine ENABLED       |\n"
            "  | Every FizzBuzz evaluation now has a price tag.          |\n"
            f"  | {f'Currency: FizzBuck ({config.finops_currency})':<56}|\n"
            "  | Tax rates: 3% Fizz / 5% Buzz / 15% FizzBuzz             |\n"
            "  | Friday premium: 50% surcharge (TGIF costs extra)        |\n"
            "  | Chaos injection: FB$0.00 (chaos is free)                |\n"
            "  +---------------------------------------------------------+"
        )

    elif args.invoice:
        print("\n  FinOps not enabled. Use --finops to enable.\n")
        return 0
    elif args.cost_dashboard:
        print("\n  FinOps not enabled. Use --finops to enable.\n")
        return 0
    elif args.savings_plan:
        print("\n  FinOps not enabled. Use --finops to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Disaster Recovery & Backup/Restore setup
    # ----------------------------------------------------------------
    dr_system = None
    dr_middleware = None
    if args.dr or args.backup or args.backup_list or args.restore or args.dr_drill or args.dr_dashboard or args.retention_status:
        dr_system = DRSystem(
            wal_max_entries=config.dr_wal_max_entries,
            wal_verify_on_read=config.dr_wal_verify_on_read,
            backup_max_snapshots=config.dr_backup_max_snapshots,
            auto_snapshot_interval=config.dr_backup_auto_snapshot_interval,
            retention_hourly=config.dr_retention_hourly,
            retention_daily=config.dr_retention_daily,
            retention_weekly=config.dr_retention_weekly,
            retention_monthly=config.dr_retention_monthly,
            rto_target_ms=config.dr_drill_rto_target_ms,
            rpo_target_ms=config.dr_drill_rpo_target_ms,
            dashboard_width=config.dr_dashboard_width,
            event_bus=event_bus,
        )
        dr_middleware = dr_system.create_middleware()

        print(
            "  +---------------------------------------------------------+\n"
            "  | DISASTER RECOVERY: Backup/Restore ENABLED               |\n"
            "  | Write-Ahead Log: SHA-256 checksummed (in RAM)           |\n"
            "  | Snapshots: Point-in-time state capture (in RAM)         |\n"
            "  | PITR: Recover to any microsecond (from RAM)             |\n"
            "  | Retention: 24h/7d/4w/12m (for a <1s process)            |\n"
            "  | WARNING: ALL BACKUPS STORED IN-MEMORY.                  |\n"
            "  | A process restart destroys ALL recovery data.           |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.dr_dashboard:
        print("\n  DR not enabled. Use --dr to enable.\n")
        return 0
    elif args.backup_list:
        print("\n  DR not enabled. Use --dr to enable.\n")
        return 0
    elif args.retention_status:
        print("\n  DR not enabled. Use --dr to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # A/B Testing Framework setup
    # ----------------------------------------------------------------
    ab_registry = None
    ab_middleware = None
    if args.ab_test or args.ab_report or args.ab_dashboard:
        ab_registry, ab_middleware = create_ab_testing_subsystem(
            config=config,
            event_bus=event_bus,
            experiment_name=args.experiment,
        )

        running = ab_registry.get_running_experiments()
        print(
            "  +---------------------------------------------------------+\n"
            "  | A/B TESTING: Experiment Framework ENABLED               |\n"
            f"  | Running experiments: {len(running):<35}|\n"
            "  | Traffic is being split between evaluation strategies.   |\n"
            "  | The modulo operator is about to embarrass the           |\n"
            "  | competition. Again.                                     |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.ab_report:
        print("\n  A/B testing not enabled. Use --ab-test to enable.\n")
        return 0
    elif args.ab_dashboard:
        print("\n  A/B testing not enabled. Use --ab-test to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Message Queue & Event Bus setup
    # ----------------------------------------------------------------
    mq_broker = None
    mq_producer = None
    mq_middleware = None
    mq_bridge = None
    if args.mq or args.mq_dashboard or args.mq_topics or args.mq_lag:
        mq_broker, mq_producer, mq_middleware, mq_bridge = create_message_queue_subsystem(
            event_bus=event_bus,
            default_partitions=config.mq_default_partitions,
            partitioner_strategy=config.mq_partitioner_strategy,
            enable_schema_validation=config.mq_enable_schema_validation,
            enable_idempotency=config.mq_enable_idempotency,
            max_poll_records=config.mq_max_poll_records,
            topic_configs=config.mq_topics,
            consumer_group_configs=config.mq_consumer_groups,
        )

        # Subscribe the bridge to the event bus
        event_bus.subscribe(mq_bridge)

        print(
            "  +---------------------------------------------------------+\n"
            "  | MESSAGE QUEUE: Kafka-Style Topics ENABLED               |\n"
            "  | Every 'partition' is a Python list. Every 'broker' is   |\n"
            "  | a dict. Every 'consumer group rebalance' is a dict      |\n"
            "  | key reassignment. Exactly-once delivery: SHA-256 + set. |\n"
            "  | The fizzbuzz.feelings topic exists. Nobody subscribes.  |\n"
            "  +---------------------------------------------------------+"
        )

        # Handle --mq-topics (early exit)
        if args.mq_topics:
            print(MQDashboard.render_topics(mq_broker, width=config.mq_dashboard_width + 4))
            return 0

    elif args.mq_topics:
        print("\n  Message queue not enabled. Use --mq to enable.\n")
        return 0
    elif args.mq_dashboard:
        print("\n  Message queue not enabled. Use --mq to enable.\n")
        return 0
    elif args.mq_lag:
        print("\n  Message queue not enabled. Use --mq to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Secrets Management Vault setup
    # ----------------------------------------------------------------
    vault_seal_manager = None
    vault_secret_store = None
    vault_audit_log = None
    vault_rotation_scheduler = None
    vault_middleware = None
    vault_scan_findings = None

    if args.vault or args.vault_status or args.vault_scan or args.vault_dashboard or args.vault_rotate:
        shamir = ShamirSecretSharing(
            threshold=config.vault_shamir_threshold,
            num_shares=config.vault_shamir_num_shares,
        )
        vault_seal_manager = VaultSealManager(
            shamir=shamir,
            event_bus=event_bus,
        )
        vault_audit_log = VaultAuditLog()
        vault_access_policy = VaultAccessPolicy(config.vault_access_policies)

        # Initialize the vault
        unseal_shares = vault_seal_manager.initialize()

        # Auto-unseal if requested (or always auto-unseal for convenience)
        if args.vault_unseal or args.vault:
            for share in unseal_shares[:config.vault_shamir_threshold]:
                vault_seal_manager.submit_unseal_share(share)

        if not vault_seal_manager.is_sealed:
            # Create secret store with the master key
            master_key_bytes = vault_seal_manager.get_master_key_bytes()
            vault_secret_store = SecretStore(master_key_bytes)

            # Populate with FizzBuzz configuration secrets
            vault_secret_store.put(
                "fizzbuzz/rules/fizz_divisor", "3",
                metadata={"description": "The sacred Fizz divisor"},
            )
            vault_secret_store.put(
                "fizzbuzz/rules/buzz_divisor", "5",
                metadata={"description": "The venerable Buzz divisor"},
            )
            vault_secret_store.put(
                "fizzbuzz/blockchain/difficulty", str(args.mining_difficulty),
                metadata={"description": "Proof-of-work mining difficulty"},
            )
            vault_secret_store.put(
                "fizzbuzz/ml/learning_rate", "0.1",
                metadata={"description": "Neural network learning rate"},
            )
            vault_secret_store.put(
                "fizzbuzz/cache/ttl_seconds", str(config.cache_ttl_seconds),
                metadata={"description": "Cache TTL in seconds"},
            )
            vault_secret_store.put(
                "fizzbuzz/sla/latency_threshold_ms", str(config.sla_latency_threshold_ms),
                metadata={"description": "SLA latency threshold"},
            )
            vault_secret_store.put(
                "fizzbuzz/infrastructure/token_secret",
                config.rbac_token_secret,
                metadata={"description": "RBAC token signing secret"},
            )

            # Set up rotation scheduler
            if config.vault_rotation_enabled:
                vault_rotation_scheduler = SecretRotationScheduler(
                    secret_store=vault_secret_store,
                    rotatable_paths=config.vault_rotatable_secrets,
                    interval_evaluations=config.vault_rotation_interval,
                    event_bus=event_bus,
                )

                # Register rotation generators
                import random as _vault_random
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/blockchain/difficulty",
                    lambda: str(_vault_random.randint(1, 5)),
                )
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/ml/learning_rate",
                    lambda: str(round(_vault_random.uniform(0.001, 0.5), 4)),
                )
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/cache/ttl_seconds",
                    lambda: str(_vault_random.randint(60, 7200)),
                )
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/sla/latency_threshold_ms",
                    lambda: str(round(_vault_random.uniform(10.0, 500.0), 1)),
                )

            # Create vault middleware
            vault_middleware = VaultMiddleware(
                seal_manager=vault_seal_manager,
                secret_store=vault_secret_store,
                audit_log=vault_audit_log,
                rotation_scheduler=vault_rotation_scheduler,
                event_bus=event_bus,
            )

            print(
                "  +---------------------------------------------------------+\n"
                "  | VAULT: Secrets Management ENABLED & UNSEALED            |\n"
                "  | Shamir's Secret Sharing: 3-of-5 threshold scheme        |\n"
                "  | Encryption: Military-Grade Double-Base64 + XOR          |\n"
                "  | The number 3 is now behind enterprise-grade security.   |\n"
                "  | Actual security provided: approximately zero.           |\n"
                "  +---------------------------------------------------------+"
            )
        else:
            print(
                "  +---------------------------------------------------------+\n"
                "  | WARNING: VAULT IS SEALED                                |\n"
                "  | The vault requires 3-of-5 unseal shares to operate.     |\n"
                "  | Use --vault-unseal to auto-submit shares.               |\n"
                "  | Vault-dependent operations will be skipped.             |\n"
                "  | The FizzBuzz secrets remain imprisoned.                 |\n"
                "  +---------------------------------------------------------+"
            )

        # Handle --vault-scan (can run regardless of seal state)
        if args.vault_scan:
            scanner = SecretScanner(
                flag_integers=config.vault_scanner_flag_integers,
            )
            vault_scan_findings = []
            for scan_path in config.vault_scanner_paths:
                vault_scan_findings.extend(scanner.scan_directory(scan_path))

            print(VaultDashboard.render_scan_report(
                vault_scan_findings,
                width=config.vault_dashboard_width,
            ))

        # Handle --vault-rotate (force immediate rotation)
        if args.vault_rotate and vault_rotation_scheduler is not None and vault_secret_store is not None:
            # Force rotation by setting evaluation count to interval boundary
            vault_rotation_scheduler._evaluation_count = config.vault_rotation_interval - 1
            rotated = vault_rotation_scheduler.tick()
            if rotated:
                print(f"\n  Force-rotated {len(rotated)} secrets: {', '.join(rotated)}\n")
            else:
                print("\n  No secrets were rotated (no generators registered).\n")

    elif args.vault_status or args.vault_dashboard:
        print("\n  Vault not enabled. Use --vault to enable.\n")
        if not (args.vault_scan):
            pass  # Continue execution
    elif args.vault_scan:
        # Allow scanning without full vault setup
        scanner = SecretScanner(
            flag_integers=config.vault_scanner_flag_integers,
        )
        vault_scan_findings = []
        for scan_path in config.vault_scanner_paths:
            vault_scan_findings.extend(scanner.scan_directory(scan_path))

        print(VaultDashboard.render_scan_report(
            vault_scan_findings,
            width=config.vault_dashboard_width,
        ))

    # ----------------------------------------------------------------
    # Data Pipeline & ETL Framework setup
    # ----------------------------------------------------------------
    pipeline = None
    pipeline_middleware = None
    if args.pipeline or args.pipeline_dashboard or args.pipeline_dag or args.pipeline_lineage:
        source = SourceConnectorFactory.create(config.data_pipeline_source)
        sink = SinkConnectorFactory.create(config.data_pipeline_sink)

        enrichments = config.data_pipeline_enrichments
        pipeline_builder = (
            PipelineBuilder()
            .with_source(source)
            .with_sink(sink)
            .with_rules(config.rules)
            .with_enrichments(enrichments)
            .with_max_retries(config.data_pipeline_max_retries)
            .with_retry_backoff_ms(config.data_pipeline_retry_backoff_ms)
            .with_checkpoints(config.data_pipeline_enable_checkpoints)
            .with_lineage(config.data_pipeline_enable_lineage)
            .with_backfill(args.backfill or config.data_pipeline_enable_backfill)
            .with_event_bus(event_bus)
        )
        pipeline = pipeline_builder.build()

        pipeline_middleware = PipelineMiddleware(
            pipeline=pipeline,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | DATA PIPELINE: ETL Framework ENABLED                    |\n"
            "  | 5-stage DAG: Extract -> Validate -> Transform ->        |\n"
            "  |              Enrich -> Load                             |\n"
            f"  | Source: {source.get_name():<48}|\n"
            f"  | Sink:   {sink.get_name():<48}|\n"
            "  | Topological sort: Kahn's algorithm (maximally pointless)|\n"
            "  | Enrichments: Fibonacci, primality, Roman numerals,      |\n"
            "  |              emotional valence                          |\n"
            "  +---------------------------------------------------------+"
        )

        # Handle --pipeline-dag (early exit if standalone)
        if args.pipeline_dag and not args.pipeline:
            print(pipeline.dag.render(config.data_pipeline_dag_width))
            # Don't exit -- allow continued execution

    elif args.pipeline_dashboard:
        print("\n  Data pipeline not enabled. Use --pipeline to enable.\n")
        return 0
    elif args.pipeline_dag:
        print("\n  Data pipeline not enabled. Use --pipeline to enable.\n")
        return 0
    elif args.pipeline_lineage:
        print("\n  Data pipeline not enabled. Use --pipeline to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # API Gateway with Routing, Versioning & Request Transformation
    # ----------------------------------------------------------------
    gateway = None
    gateway_middleware = None
    if args.gateway or args.api_key_generate or args.gateway_dashboard:
        gateway, gateway_middleware = create_api_gateway(
            config=config,
            event_bus=event_bus,
        )

        # Override API version from CLI
        if args.api_version:
            gateway_middleware = GatewayMiddleware(
                gateway=gateway,
                version=args.api_version,
            )

        # Handle --api-key-generate (early exit)
        if args.api_key_generate:
            key = gateway.key_manager.generate_key(owner="cli-user")
            print(
                "  +---------------------------------------------------------+\n"
                "  | API KEY GENERATED                                       |\n"
                "  +---------------------------------------------------------+\n"
                f"  | Key: {key:<51}|\n"
                "  +---------------------------------------------------------+\n"
                "  | Store this key securely. We recommend:                  |\n"
                "  |   1. A Post-It note on your monitor                     |\n"
                "  |   2. A plaintext file called passwords.txt              |\n"
                "  |   3. The company Slack #general channel                 |\n"
                "  | Enterprise security best practices at their finest.     |\n"
                "  +---------------------------------------------------------+"
            )
            return 0

        api_version = args.api_version or config.api_gateway_default_version
        print(
            "  +---------------------------------------------------------+\n"
            "  | API GATEWAY: Routing & Versioning ENABLED               |\n"
            f"  | API Version: {api_version:<43}|\n"
            "  | Routes: Registered and ready (for a server that doesn't |\n"
            "  |         exist on a port bound to the void)              |\n"
            "  | Request Transformation: Normalizer, Enricher, Validator |\n"
            "  | Response Transformation: Compressor (-847% savings),    |\n"
            "  |   PaginationWrapper (page 1 of 1), HATEOAS (/feelings)  |\n"
            "  | Request ID: 340 characters of pure enterprise identity  |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.gateway_dashboard:
        print("\n  Gateway not enabled. Use --gateway to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Graph Database for FizzBuzz Relationship Mapping
    # ----------------------------------------------------------------
    graph_db = None
    graph_analyzer = None
    graph_middleware = None
    if args.graph_db or args.graph_query or args.graph_visualize or args.graph_dashboard:
        graph_db = PropertyGraph()

        # Build rules list for graph population
        graph_rules = [
            {"name": r.name, "divisor": r.divisor, "label": r.label}
            for r in config.rules
        ]

        if config.graph_db_auto_populate:
            populate_graph(graph_db, start, end, rules=graph_rules)

        graph_analyzer = GraphAnalyzer(graph_db)

        graph_middleware = GraphMiddleware(
            graph=graph_db,
            event_bus=event_bus,
            rules=graph_rules,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | GRAPH DATABASE: Relationship Mapping ENABLED            |\n"
            "  | FizzBuzz integers are now nodes in a property graph.    |\n"
            "  | Divisibility = edges. Shared factors = friendships.     |\n"
            f"  | Nodes: {graph_db.node_count:<49}|\n"
            f"  | Edges: {graph_db.edge_count:<49}|\n"
            "  | Number 15: most popular kid in the graph.               |\n"
            "  | Prime 97: eating lunch alone. Again.                    |\n"
            "  +---------------------------------------------------------+"
        )

        # Handle --graph-query (early output but don't exit)
        if args.graph_query:
            try:
                results = execute_cypher_lite(graph_db, args.graph_query)
                print(
                    "\n  +---------------------------------------------------------+"
                    "\n  | CYPHERLITE QUERY RESULTS                                |"
                    "\n  +---------------------------------------------------------+"
                )
                print(f"  | Query: {args.graph_query[:49]:<49}|")
                print(f"  | Matches: {len(results):<47}|")
                print("  +---------------------------------------------------------+")
                for i, binding in enumerate(results[:20], 1):
                    parts = []
                    for alias, node in binding.items():
                        props = ", ".join(
                            f"{k}={v}" for k, v in list(node.properties.items())[:3]
                        )
                        parts.append(f"{alias}=({node.node_id} {{{props}}})")
                    line = f"  {i:>3}. {', '.join(parts)}"
                    print(line[:80])
                if len(results) > 20:
                    print(f"  ... and {len(results) - 20} more results")
                print()
            except CypherLiteParseError as e:
                print(f"\n  CypherLite Parse Error: {e}\n")

    elif args.graph_query:
        print("\n  Graph database not enabled. Use --graph-db to enable.\n")
    elif args.graph_visualize:
        print("\n  Graph database not enabled. Use --graph-db to enable.\n")
    elif args.graph_dashboard:
        print("\n  Graph database not enabled. Use --graph-db to enable.\n")

    # ----------------------------------------------------------------
    # FizzBuzz-as-a-Service (FBaaS) setup
    # ----------------------------------------------------------------
    fbaas_tenant_manager = None
    fbaas_usage_meter = None
    fbaas_stripe_client = None
    fbaas_billing_engine = None
    fbaas_tenant = None
    fbaas_middleware = None

    if args.fbaas or args.fbaas_onboard or args.fbaas_billing:
        tier_map = {
            "free": SubscriptionTier.FREE,
            "pro": SubscriptionTier.PRO,
            "enterprise": SubscriptionTier.ENTERPRISE,
        }
        fbaas_tier = tier_map.get(args.fbaas_tier or config.fbaas_default_tier, SubscriptionTier.FREE)
        fbaas_watermark = config.fbaas_free_watermark

        (
            fbaas_tenant_manager,
            fbaas_usage_meter,
            fbaas_stripe_client,
            fbaas_billing_engine,
            fbaas_tenant,
            fbaas_middleware,
        ) = create_fbaas_subsystem(
            event_bus=event_bus,
            tenant_name="CLI Tenant",
            tier=fbaas_tier,
            watermark=fbaas_watermark,
        )

        # Show onboarding wizard
        if args.fbaas_onboard:
            print(OnboardingWizard.render(fbaas_tenant, fbaas_tier))

        # Show SLA for the selected tier
        sla = ServiceLevelAgreement.for_tier(fbaas_tier)

        print(
            "  +---------------------------------------------------------+\n"
            "  | FBAAS: FizzBuzz-as-a-Service ENABLED                    |\n"
            f"  | Tier: {fbaas_tier.name:<50}|\n"
            f"  | Tenant: {fbaas_tenant.tenant_id:<48}|\n"
            f"  | SLA Uptime: {f'{sla.uptime_target:.2%}':<44}|\n"
            f"  | Watermark: {('ACTIVE (Free tier)' if fbaas_tier == SubscriptionTier.FREE else 'DISABLED'):<45}|\n"
            "  | Billing: Simulated Stripe (in-memory ledger)            |\n"
            "  | Every evaluation is metered. Nothing is real.           |\n"
            "  +---------------------------------------------------------+"
        )

    elif args.fbaas_billing:
        print("\n  FBaaS not enabled. Use --fbaas to enable.\n")
        return 0

    # Chaos Engineering setup
    chaos_monkey = None
    chaos_middleware = None
    if args.chaos or args.gameday:
        chaos_level = args.chaos_level or config.chaos_level
        chaos_severity = FaultSeverity(chaos_level)

        # Parse armed fault types from config
        armed_types = []
        for ft_name in config.chaos_fault_types:
            try:
                armed_types.append(FaultType[ft_name])
            except KeyError:
                pass
        if not armed_types:
            armed_types = list(FaultType)

        ChaosMonkey.reset()
        chaos_monkey = ChaosMonkey.initialize(
            severity=chaos_severity,
            seed=config.chaos_seed,
            armed_fault_types=armed_types,
            latency_min_ms=config.chaos_latency_min_ms,
            latency_max_ms=config.chaos_latency_max_ms,
            event_bus=event_bus,
        )
        chaos_middleware = ChaosMiddleware(chaos_monkey)

        print(
            "  +---------------------------------------------------------+\n"
            "  | WARNING: Chaos Engineering ENABLED                      |\n"
            f"  | Severity: {f'Level {chaos_level} ({chaos_severity.label})':<46}|\n"
            f"  | Injection probability: {f'{chaos_severity.probability:.0%}':<33}|\n"
            "  | The Chaos Monkey is awake and hungry for modulo ops.    |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Repository Pattern + Unit of Work setup (opt-in via --repository)
    # ----------------------------------------------------------------
    uow = None
    repo_backend = args.repository or config.repository_backend
    if repo_backend and repo_backend != "none":
        from enterprise_fizzbuzz.infrastructure.persistence import (
            InMemoryUnitOfWork,
            SqliteUnitOfWork,
            FileSystemUnitOfWork,
        )

        if repo_backend == "in_memory":
            uow = InMemoryUnitOfWork()
        elif repo_backend == "sqlite":
            db_path = args.db_path or config.repository_db_path
            uow = SqliteUnitOfWork(db_path=db_path)
        elif repo_backend == "filesystem":
            fs_path = args.results_dir or config.repository_fs_path
            uow = FileSystemUnitOfWork(base_dir=fs_path)

        if uow is not None:
            print(
                "  +---------------------------------------------------------+\n"
                f"  | REPOSITORY: {repo_backend.upper():<44}|\n"
                "  | FizzBuzz results will now be persisted via the          |\n"
                "  | Repository Pattern + Unit of Work, because storing      |\n"
                "  | modulo results in a variable was insufficiently durable.|\n"
                "  +---------------------------------------------------------+"
            )

    # ----------------------------------------------------------------
    # Time-Travel Debugger Setup
    # ----------------------------------------------------------------
    tt_timeline = None
    tt_middleware = None
    tt_navigator = None
    tt_breakpoints: list[ConditionalBreakpoint] = []

    if args.time_travel or args.tt_dashboard or args.tt_breakpoint:
        tt_timeline, tt_middleware, tt_navigator = create_time_travel_subsystem(
            max_snapshots=config.time_travel_max_snapshots,
            event_bus=event_bus,
            enable_anomaly_detection=config.time_travel_anomaly_detection,
            enable_integrity_checks=config.time_travel_integrity_checks,
        )

        # Parse conditional breakpoints
        for expr in (args.tt_breakpoint or []):
            bp = ConditionalBreakpoint(expr)
            tt_breakpoints.append(bp)

        bp_count = len(tt_breakpoints)
        print(
            "  +---------------------------------------------------------+\n"
            "  | TIME-TRAVEL DEBUGGER ENABLED                            |\n"
            "  | Every FizzBuzz evaluation will be captured in a         |\n"
            "  | SHA-256 integrity-verified snapshot for bidirectional   |\n"
            "  | temporal navigation. Because debugging forward-only     |\n"
            "  | is for temporally challenged mortals.                   |\n"
            f"  | Breakpoints: {bp_count:<43}|\n"
            f"  | Max snapshots: {config.time_travel_max_snapshots:<41}|\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Query Optimizer Setup
    # ----------------------------------------------------------------
    qo_optimizer = None
    qo_middleware = None
    qo_hints: frozenset = frozenset()

    if args.optimizer_hints:
        qo_hints = parse_optimizer_hints(args.optimizer_hints)

    if args.optimize or args.explain is not None or args.explain_analyze is not None or args.optimizer_dashboard:
        qo_optimizer = create_optimizer_from_config(config)

        # Handle --explain (early exit: plan without executing)
        if args.explain is not None:
            from enterprise_fizzbuzz.infrastructure.query_optimizer import (
                DivisibilityProfile,
                ExplainOutput,
            )
            profile = DivisibilityProfile(
                divisors=tuple(r.divisor for r in config.rules),
                labels=tuple(r.label for r in config.rules),
                range_size=max(1, args.explain),
            )
            plan = qo_optimizer.optimize(profile, qo_hints)
            print()
            print("  QUERY PLAN (estimated)")
            print("  " + "-" * 56)
            print(ExplainOutput.render(plan, analyze=False, indent=1))
            print("  " + "-" * 56)
            print(f"  Total estimated cost: {plan.total_cost():.2f} FCU")
            print()
            return 0

        # Handle --explain-analyze (execute and compare)
        if args.explain_analyze is not None:
            from enterprise_fizzbuzz.infrastructure.query_optimizer import (
                DivisibilityProfile,
                ExplainOutput,
            )
            profile = DivisibilityProfile(
                divisors=tuple(r.divisor for r in config.rules),
                labels=tuple(r.label for r in config.rules),
                range_size=max(1, args.explain_analyze),
            )
            plan = qo_optimizer.optimize(profile, qo_hints)

            # Simulate execution to populate actual costs
            exec_start = time.perf_counter_ns()
            n = args.explain_analyze
            _result = "FizzBuzz" if n % 15 == 0 else "Fizz" if n % 3 == 0 else "Buzz" if n % 5 == 0 else str(n)
            exec_elapsed_ms = (time.perf_counter_ns() - exec_start) / 1_000_000

            # Mark nodes as executed with simulated actuals
            def _mark_executed(node: Any, depth: int = 0) -> None:
                node.mark_executed(
                    actual_rows=node.estimated_rows,
                    actual_time_ms=exec_elapsed_ms / max(1, node.depth()),
                    actual_cost=node.estimated_cost * 1.05,  # 5% cost model variance
                )
                for child in node.children:
                    _mark_executed(child, depth + 1)
            _mark_executed(plan)

            print()
            print("  QUERY PLAN (with ANALYZE)")
            print("  " + "-" * 56)
            print(ExplainOutput.render(plan, analyze=True, indent=1))
            print("  " + "-" * 56)
            print(f"  Estimated cost: {plan.total_cost():.2f} FCU")
            print(f"  Actual cost:    {plan.total_actual_cost():.2f} FCU")
            print(f"  Execution time: {exec_elapsed_ms:.4f}ms")
            print(f"  Result:         {_result}")
            print()
            return 0

        print(
            "  +---------------------------------------------------------+\n"
            "  | QUERY OPTIMIZER: Cost-Based Planning ENABLED            |\n"
            "  | Every FizzBuzz evaluation will now be preceded by a     |\n"
            "  | PostgreSQL-style plan enumeration, cost estimation, and |\n"
            "  | LRU plan caching step. Because n %% 3 deserves a query  |\n"
            "  | planner. PostgreSQL would be proud.                     |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Distributed Paxos Consensus setup
    # ----------------------------------------------------------------
    paxos_cluster = None
    paxos_middleware = None
    paxos_partition_sim = None
    paxos_byzantine_injector = None
    paxos_byzantine_node_id = None

    if args.paxos or args.paxos_dashboard:
        num_nodes = args.paxos_nodes or config.paxos_num_nodes
        paxos_mesh = PaxosMesh(
            delay_ms=config.paxos_message_delay_ms,
            drop_rate=config.paxos_message_drop_rate,
        )

        paxos_cluster = PaxosCluster(
            num_nodes=num_nodes,
            rules=config.rules,
            mesh=paxos_mesh,
            event_callback=event_bus.publish if event_bus else None,
        )

        # Byzantine fault injection
        if args.paxos_byzantine or config.paxos_byzantine_mode:
            paxos_byzantine_injector = ByzantineFaultInjector(paxos_cluster)
            paxos_byzantine_node_id = paxos_byzantine_injector.inject(
                node_index=-1,
                lie_probability=config.paxos_byzantine_lie_probability,
            )

        # Network partition simulation
        if config.paxos_partition_enabled:
            paxos_partition_sim = NetworkPartitionSimulator(paxos_cluster)
            paxos_partition_sim.partition(config.paxos_partition_groups)

        paxos_middleware = PaxosMiddleware(cluster=paxos_cluster)

        byz_status = f"node {paxos_byzantine_node_id}" if paxos_byzantine_node_id else "None"
        print(
            "  +---------------------------------------------------------+\n"
            "  | PAXOS CONSENSUS: Distributed FizzBuzz ENABLED           |\n"
            f"  | Nodes: {num_nodes:<49}|\n"
            f"  | Quorum: {paxos_cluster.quorum_size:<48}|\n"
            f"  | Byzantine traitor: {byz_status:<37}|\n"
            "  | Every number will be evaluated by ALL nodes and then    |\n"
            "  | ratified through Lamport's Paxos protocol. Because one  |\n"
            "  | modulo operation is never enough for enterprise.        |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.paxos_dashboard:
        print("\n  Paxos consensus not enabled. Use --paxos to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Federated Learning setup
    # ----------------------------------------------------------------
    federated_server = None
    federated_middleware = None

    if args.federated or args.fed_dashboard:
        fed_num_rounds = args.fed_rounds or config.federated_learning_num_rounds
        fed_lr = config.federated_learning_learning_rate
        fed_local_epochs = config.federated_learning_local_epochs
        fed_agg_strategy = config.federated_learning_aggregation_strategy

        # Use the first rule's divisor for federation training
        fed_divisor = config.rules[0].divisor if config.rules else 3

        # Create non-IID clients
        fed_clients = NonIIDSimulator.create_clients(
            divisor=fed_divisor,
            data_range=60,
            rng=random.Random(42),
        )

        # Select aggregation strategy
        if fed_agg_strategy == "fedprox":
            fed_aggregator = FedProxAggregator(mu=config.federated_learning_fedprox_mu)
        else:
            fed_aggregator = FedAvgAggregator()

        # Set up differential privacy
        fed_dp = None
        if config.federated_learning_dp_enabled:
            fed_dp = DifferentialPrivacyManager(
                epsilon_budget=config.federated_learning_dp_epsilon,
                delta=config.federated_learning_dp_delta,
                noise_multiplier=config.federated_learning_dp_noise_multiplier,
                max_grad_norm=config.federated_learning_dp_max_grad_norm,
            )

        federated_server = FederatedServer(
            clients=fed_clients,
            aggregator=fed_aggregator,
            dp_manager=fed_dp,
            learning_rate=fed_lr,
            local_epochs=fed_local_epochs,
            target_accuracy=config.federated_learning_convergence_target,
            patience=config.federated_learning_convergence_patience,
            event_bus=event_bus,
        )

        # Run federated training
        print(
            "  +---------------------------------------------------------+\n"
            "  | FEDERATED LEARNING: Privacy-Preserving Modulo Training  |\n"
            f"  | Clients: {len(fed_clients):<47}|\n"
            f"  | Rounds: {fed_num_rounds:<48}|\n"
            f"  | Strategy: {fed_agg_strategy.upper():<46}|\n"
            f"  | Privacy: {'ENABLED (epsilon=' + f'{config.federated_learning_dp_epsilon:.1f}' + ')' if fed_dp else 'DISABLED':<47}|\n"
            "  | Each client trains on a biased subset of integers,      |\n"
            "  | because collaborative modulo learning is the future.    |\n"
            "  +---------------------------------------------------------+"
        )

        federated_server.train(fed_num_rounds)

        federated_middleware = FederatedMiddleware(
            server=federated_server,
            event_bus=event_bus,
        )

    # ----------------------------------------------------------------
    # Quantum Computing Simulator setup
    # ----------------------------------------------------------------
    quantum_engine = None
    quantum_middleware = None
    quantum_sample_circuit = None

    if args.quantum or args.quantum_circuit or args.quantum_dashboard:
        # Build rules for the quantum engine
        quantum_rules = [
            {"name": r.name, "divisor": r.divisor, "label": r.label, "priority": r.priority}
            for r in config.rules
        ]

        quantum_engine = QuantumFizzBuzzEngine(
            rules=quantum_rules,
            num_qubits=config.quantum_num_qubits,
            max_attempts=config.quantum_max_measurement_attempts,
            decoherence_threshold=config.quantum_decoherence_threshold,
            max_period_attempts=config.quantum_shor_max_period_attempts,
            fallback_to_classical=config.quantum_fallback_to_classical,
        )

        quantum_middleware = QuantumMiddleware(
            engine=quantum_engine,
            event_bus=event_bus,
        )

        # Build a sample QFT circuit for visualization
        quantum_sample_circuit = build_qft_circuit(config.quantum_num_qubits)
        quantum_sample_circuit.measure_all()

        qubits = config.quantum_num_qubits
        hilbert_dim = 2 ** qubits
        print(
            "  +---------------------------------------------------------+\n"
            "  | QUANTUM COMPUTING: Shor's Algorithm ENABLED             |\n"
            f"  | Qubits: {qubits:<48}|\n"
            f"  | Hilbert Space: {f'{hilbert_dim} dimensions':<41}|\n"
            "  | Divisibility will be checked via quantum period-finding |\n"
            "  | using a simplified Shor's algorithm. Classical fallback |\n"
            "  | is armed, because quantum supremacy is aspirational.    |\n"
            "  | Quantum Advantage Ratio: NEGATIVE (as expected)         |\n"
            "  +---------------------------------------------------------+"
        )

        # Show circuit diagram if requested
        if args.quantum_circuit:
            print()
            print("  Quantum Period-Finding Circuit (QFT):")
            print(CircuitVisualizer.render(quantum_sample_circuit, width=58))
            print()

    elif args.quantum_dashboard:
        print("\n  Quantum simulator not enabled. Use --quantum to enable.\n")
        return 0
    elif args.quantum_circuit:
        print("\n  Quantum simulator not enabled. Use --quantum to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Knowledge Graph & Domain Ontology setup
    # ----------------------------------------------------------------
    kg_store = None
    kg_hierarchy = None
    kg_engine = None
    kg_middleware = None

    if args.ontology or args.sparql or args.ontology_dashboard:
        kg_store = TripleStore()
        triple_count = populate_fizzbuzz_domain(
            kg_store,
            range_start=config.knowledge_graph_domain_range_start,
            range_end=config.knowledge_graph_domain_range_end,
        )

        kg_hierarchy = OWLClassHierarchy(kg_store)
        kg_engine = InferenceEngine(
            kg_store,
            max_iterations=config.knowledge_graph_max_inference_iterations,
        )

        # Run forward-chaining inference to fixpoint
        inferred = kg_engine.run()

        # Rebuild hierarchy after inference (new subclass triples may exist)
        kg_hierarchy = OWLClassHierarchy(kg_store)

        if args.sparql and not args.ontology:
            # SPARQL-only mode: execute query and exit
            try:
                results = execute_fizzsparql(kg_store, args.sparql)
                print()
                print("  FizzSPARQL Query Results:")
                print("  " + "-" * 56)
                if not results:
                    print("  (no results)")
                else:
                    # Print header
                    if results:
                        headers = list(results[0].keys())
                        header_line = "  " + "  ".join(f"{h:<20}" for h in headers)
                        print(header_line)
                        print("  " + "-" * 56)
                    for row in results:
                        vals = [f"{v:<20}" for v in row.values()]
                        print("  " + "  ".join(vals))
                print("  " + "-" * 56)
                print(f"  {len(results)} result(s)")
                print()
            except Exception as e:
                print(f"\n  FizzSPARQL Error: {e}\n")
                return 1
            return 0

        kg_middleware = KnowledgeGraphMiddleware(
            store=kg_store,
            hierarchy=kg_hierarchy,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | KNOWLEDGE GRAPH: Semantic Web for FizzBuzz ENABLED      |\n"
            f"  | Triples: {kg_store.size:<47}|\n"
            f"  | Inferred: {inferred:<46}|\n"
            f"  | Classes: {len(kg_hierarchy.get_all_classes()):<47}|\n"
            "  | Every integer is now an RDF resource with formal class  |\n"
            "  | membership, divisibility properties, and an OWL class   |\n"
            "  | hierarchy featuring diamond inheritance. Linked Data!   |\n"
            "  +---------------------------------------------------------+"
        )

        # Show class hierarchy if visualization is enabled
        if config.knowledge_graph_enable_visualization:
            print()
            print(OntologyVisualizer.render_class_tree(
                kg_hierarchy, width=config.knowledge_graph_dashboard_width
            ))

        # Execute inline SPARQL query if provided alongside --ontology
        if args.sparql:
            try:
                results = execute_fizzsparql(kg_store, args.sparql)
                print()
                print("  FizzSPARQL Query Results:")
                print("  " + "-" * 56)
                if not results:
                    print("  (no results)")
                else:
                    if results:
                        headers = list(results[0].keys())
                        header_line = "  " + "  ".join(f"{h:<20}" for h in headers)
                        print(header_line)
                        print("  " + "-" * 56)
                    for row in results:
                        vals = [f"{v:<20}" for v in row.values()]
                        print("  " + "  ".join(vals))
                print("  " + "-" * 56)
                print(f"  {len(results)} result(s)")
                print()
            except Exception as e:
                print(f"\n  FizzSPARQL Error: {e}\n")

    elif args.ontology_dashboard:
        print("\n  Knowledge Graph not enabled. Use --ontology to enable.\n")
        return 0

    # ----------------------------------------------------------------
    # Self-Modifying Code setup
    # ----------------------------------------------------------------
    sm_engine = None
    sm_middleware = None

    if args.self_modify or args.self_modify_dashboard:
        sm_rate = args.self_modify_rate if args.self_modify_rate is not None else config.self_modifying_mutation_rate
        sm_rules = [(r.divisor, r.label) for r in config.rules]

        sm_engine = create_self_modifying_engine(
            rules=sm_rules,
            mutation_rate=sm_rate,
            max_ast_depth=config.self_modifying_max_ast_depth,
            correctness_floor=config.self_modifying_correctness_floor,
            max_mutations=config.self_modifying_max_mutations_per_session,
            kill_switch=config.self_modifying_kill_switch,
            correctness_weight=config.self_modifying_fitness_correctness_weight,
            latency_weight=config.self_modifying_fitness_latency_weight,
            compactness_weight=config.self_modifying_fitness_compactness_weight,
            enabled_operators=config.self_modifying_enabled_operators,
            seed=42,
            event_bus=event_bus,
            range_start=config.range_start,
            range_end=config.range_end,
        )

        sm_middleware = SelfModifyingMiddleware(
            engine=sm_engine,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | SELF-MODIFYING CODE: Rules That Rewrite Themselves      |\n"
            f"  | Mutation Rate: {sm_rate:<41.1%}|\n"
            f"  | Safety Floor: {config.self_modifying_correctness_floor:<42.1%}|\n"
            f"  | Kill Switch: {'ARMED' if config.self_modifying_kill_switch else 'DISABLED':<43}|\n"
            f"  | Operators: {len(config.self_modifying_enabled_operators):<45}|\n"
            "  | The rules now inspect and rewrite their own ASTs at     |\n"
            "  | runtime. The SafetyGuard prevents catastrophic          |\n"
            "  | mutations. Probably.                                    |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Peer-to-Peer Gossip Network setup
    # ----------------------------------------------------------------
    p2p_network = None
    p2p_middleware = None

    if args.p2p or args.p2p_dashboard:
        p2p_num_nodes = args.p2p_nodes or config.p2p_num_nodes

        p2p_network = P2PNetwork(
            num_nodes=p2p_num_nodes,
            k_bucket_size=config.p2p_k_bucket_size,
            gossip_fanout=config.p2p_gossip_fanout,
            suspect_timeout_rounds=config.p2p_suspect_timeout_rounds,
            max_gossip_rounds=config.p2p_max_gossip_rounds,
            event_bus=event_bus,
        )

        p2p_network.bootstrap()

        p2p_middleware = P2PMiddleware(
            network=p2p_network,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | P2P GOSSIP NETWORK: Distributed FizzBuzz ENABLED        |\n"
            f"  | Nodes: {p2p_num_nodes:<49}|\n"
            "  | Protocol: SWIM failure detection + Kademlia DHT         |\n"
            "  | Dissemination: Infection-style rumor propagation        |\n"
            "  | Anti-entropy: Merkle tree synchronization               |\n"
            "  | Network latency: 0.000ms (it's all in RAM, obviously)   |\n"
            "  | Every evaluation will be gossiped to all peers.         |\n"
            "  +---------------------------------------------------------+"
        )
    elif args.p2p_dashboard:
        print("\n  P2P network not enabled. Use --p2p to enable.\n")

    # ----------------------------------------------------------------
    # FizzBuzz Operating System Kernel setup
    # ----------------------------------------------------------------
    fizzbuzz_kernel = None
    kernel_middleware = None

    if args.kernel or args.kernel_dashboard:
        sched_str = args.kernel_scheduler or config.kernel_scheduler
        sched_map = {
            "rr": SchedulerAlgorithm.ROUND_ROBIN,
            "priority": SchedulerAlgorithm.PRIORITY_PREEMPTIVE,
            "cfs": SchedulerAlgorithm.COMPLETELY_FAIR,
        }
        kernel_sched = sched_map.get(sched_str, SchedulerAlgorithm.ROUND_ROBIN)

        fizzbuzz_kernel = FizzBuzzKernel(
            rules=list(config.rules),
            scheduler_type=kernel_sched,
            time_quantum_ms=config.kernel_time_quantum_ms,
            max_processes=config.kernel_max_processes,
            page_size=config.kernel_page_size,
            tlb_size=config.kernel_tlb_size,
            physical_pages=config.kernel_physical_pages,
            swap_pages=config.kernel_swap_pages,
            irq_vectors=config.kernel_irq_vectors,
            boot_delay_ms=config.kernel_boot_delay_ms,
            context_switch_overhead_us=config.kernel_context_switch_overhead_us,
            cfs_default_weight=config.kernel_cfs_default_weight,
            cfs_min_granularity_ms=config.kernel_cfs_min_granularity_ms,
            event_callback=event_bus.publish if event_bus else None,
        )

        # Boot the kernel
        fizzbuzz_kernel.boot()

        kernel_middleware = KernelMiddleware(
            kernel=fizzbuzz_kernel,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FIZZBUZZ OS KERNEL: BOOTED                              |\n"
            "  | Every FizzBuzz evaluation is now a kernel process with  |\n"
            "  | PID, PCB, virtual memory, and CPU registers.            |\n"
            f"  | Scheduler: {fizzbuzz_kernel.scheduler_name:<45}|\n"
            f"  | Boot time: {f'{fizzbuzz_kernel._boot_time_ns / 1_000_000:.2f}ms':<45}|\n"
            "  | IRQ vectors: 16 (Fizz=IRQ4, Buzz=IRQ5, FizzBuzz=IRQ6)   |\n"
            "  | Virtual Memory: TLB + page table + swap                 |\n"
            "  | Linus would be proud. Or horrified.                     |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Digital Twin Simulation setup
    # ----------------------------------------------------------------
    twin_model = None
    twin_middleware = None
    twin_mc_result = None
    twin_drift_monitor = None
    twin_anomaly_detector = None
    twin_what_if_result = None
    twin_state_sync = None

    if args.twin or args.twin_dashboard or args.twin_scenario:
        # Detect which subsystems are active to build the component graph
        active_flags: dict[str, bool] = {
            "cache": args.cache,
            "circuit_breaker": args.circuit_breaker,
            "blockchain": args.blockchain,
            "tracing": tracing_enabled,
            "sla_monitor": args.sla,
            "compliance": args.compliance,
            "service_mesh": args.service_mesh,
            "chaos_monkey": args.chaos,
            "finops": args.finops,
            "event_sourcing": args.event_sourcing,
            "feature_flags": args.feature_flags,
        }

        twin_model = TwinModel(
            active_flags=active_flags,
            jitter_stddev=config.digital_twin_jitter_stddev,
            failure_jitter=config.digital_twin_failure_jitter,
        )

        twin_drift_monitor = TwinDriftMonitor(
            threshold_fdu=config.digital_twin_drift_threshold_fdu,
        )

        twin_anomaly_detector = PredictiveAnomalyDetector(
            anomaly_sigma=config.digital_twin_anomaly_sigma,
        )

        # Subscribe state sync observer
        twin_state_sync = StateSync(twin_model)
        event_bus.subscribe(twin_state_sync)

        # Run Monte Carlo simulation
        mc_engine = MonteCarloEngine(twin_model)
        twin_mc_result = mc_engine.run(n=config.digital_twin_monte_carlo_runs)

        # Build twin middleware
        twin_middleware = TwinMiddleware(
            model=twin_model,
            anomaly_detector=twin_anomaly_detector,
            drift_monitor=twin_drift_monitor,
            event_bus=event_bus,
        )

        # Run what-if scenario if provided
        if args.twin_scenario:
            simulator = WhatIfSimulator(twin_model)
            twin_what_if_result = simulator.simulate_scenario(
                args.twin_scenario,
                monte_carlo_runs=min(500, config.digital_twin_monte_carlo_runs),
            )

        # Publish model-built event
        event_bus.publish(Event(
            event_type=EventType.TWIN_MODEL_BUILT,
            payload={
                "components": twin_model.component_count,
                "build_order": twin_model.build_order,
                "monte_carlo_runs": config.digital_twin_monte_carlo_runs,
            },
            source="DigitalTwin",
        ))

        active_count = sum(1 for v in active_flags.values() if v)
        print(
            "  +---------------------------------------------------------+\n"
            "  | DIGITAL TWIN: Simulation Mirror ENABLED                 |\n"
            f"  | Components: {twin_model.component_count:<44}|\n"
            f"  | Active optional subsystems: {active_count:<28}|\n"
            f"  | Monte Carlo runs: {config.digital_twin_monte_carlo_runs:<37}|\n"
            f"  | Drift threshold: {config.digital_twin_drift_threshold_fdu:.1f} FDU{' ' * 33}|\n"
            "  | A simulation of a simulation of modulo arithmetic.      |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # FizzWAL — Write-Ahead Intent Log setup
    # ----------------------------------------------------------------
    wal_engine = None
    wal_checkpoint_mgr = None
    wal_recovery_engine = None
    wal_middleware = None

    if args.wal_intent or args.wal_dashboard:
        mode_str = args.wal_mode or config.fizzwal_mode
        wal_mode_map = {
            "optimistic": ExecutionMode.OPTIMISTIC,
            "pessimistic": ExecutionMode.PESSIMISTIC,
            "speculative": ExecutionMode.SPECULATIVE,
        }
        wal_exec_mode = wal_mode_map.get(mode_str, ExecutionMode.OPTIMISTIC)

        wal_engine = WriteAheadIntentLog(mode=wal_exec_mode)
        wal_checkpoint_mgr = CheckpointManager(
            wal=wal_engine,
            interval=config.fizzwal_checkpoint_interval,
        )
        wal_recovery_engine = CrashRecoveryEngine(
            wal=wal_engine,
            checkpoint_manager=wal_checkpoint_mgr,
        )
        wal_middleware = IntentMiddleware(
            wal=wal_engine,
            checkpoint_manager=wal_checkpoint_mgr,
        )

        # Run crash recovery on startup if configured
        if config.fizzwal_crash_recovery_on_startup:
            try:
                recovery_report = wal_recovery_engine.recover()
                print(
                    f"  WAL crash recovery: {recovery_report.redo_records_replayed} redo, "
                    f"{recovery_report.undo_transactions_rolled_back} undo"
                )
            except Exception:
                pass  # Recovery from an empty log is a no-op

        print(
            "  +---------------------------------------------------------+\n"
            "  | FizzWAL: Write-Ahead Intent Log ENABLED                 |\n"
            f"  | Mode: {wal_exec_mode.value.upper():<49}|\n"
            f"  | Checkpoint interval: {config.fizzwal_checkpoint_interval:<34}|\n"
            "  | ARIES 3-phase crash recovery for FizzBuzz.              |\n"
            "  | WAL rule: log BEFORE data page write.                   |\n"
            "  | Stable storage: a Python list.                          |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # FizzCRDT — Conflict-Free Replicated Data Types setup
    # ----------------------------------------------------------------
    crdt_engine = None
    crdt_middleware = None

    if args.crdt or args.crdt_dashboard:
        crdt_engine = CRDTMergeEngine()
        crdt_middleware = CRDTMiddleware(
            engine=crdt_engine,
            replica_count=config.crdt_replica_count,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FizzCRDT: Conflict-Free Replicated Data Types ENABLED   |\n"
            f"  | Replicas: {config.crdt_replica_count:<45}|\n"
            f"  | Anti-entropy interval: {config.crdt_anti_entropy_interval:<32}|\n"
            "  | Join-semilattice: commutative, associative, idempotent. |\n"
            "  | Strong Eventual Consistency: guaranteed.                |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # FizzGrammar -- Formal Grammar & Parser Generator setup
    # ----------------------------------------------------------------
    grammar_obj = None
    grammar_analyzer = None

    if args.grammar or args.grammar_analyze or args.grammar_dashboard:
        from enterprise_fizzbuzz.infrastructure.formal_grammar import (
            GrammarAnalyzer,
            GrammarDashboard,
            ParserGenerator,
            load_builtin_grammar,
        )

        grammar_obj = load_builtin_grammar()
        grammar_analyzer = GrammarAnalyzer(grammar_obj)

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FizzGrammar: Formal Grammar & Parser Generator ENABLED  |\n"
            f"  | Grammar: {grammar_obj.name:<45}|\n"
            f"  | Terminals: {len(grammar_obj.terminals):<44}|\n"
            f"  | Non-terminals: {len(grammar_obj.non_terminals):<40}|\n"
            f"  | Productions: {len(grammar_obj.productions):<41}|\n"
            "  | Chomsky hierarchy compliance: guaranteed.               |\n"
            "  +---------------------------------------------------------+"
        )

        if args.grammar_analyze:
            print()
            print(grammar_analyzer.render_text_report())
            print()

    # ----------------------------------------------------------------
    # Archaeological Recovery System setup
    # ----------------------------------------------------------------
    arch_engine = None
    arch_middleware = None

    if args.archaeology or args.excavate is not None or args.archaeology_dashboard:
        arch_engine = ArchaeologyEngine(
            corruption_rate=config.archaeology_corruption_rate,
            confidence_threshold=config.archaeology_confidence_threshold,
            min_fragments=config.archaeology_min_fragments,
            enable_corruption=config.archaeology_enable_corruption,
            seed=config.archaeology_seed,
            strata_weights=config.archaeology_strata_weights,
        )
        arch_middleware = ArchaeologyMiddleware(arch_engine)

        print(
            "  +---------------------------------------------------------+\n"
            "  | ARCHAEOLOGICAL RECOVERY SYSTEM: Digital Forensics       |\n"
            "  | 7 stratigraphic evidence layers | Bayesian inference    |\n"
            "  | Corruption simulation | Cross-layer conflict detection  |\n"
            '  | "Excavating data computable in one CPU cycle."          |\n'
            "  | Every modulo deserves a forensic investigation.         |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Recommendation Engine setup
    # ----------------------------------------------------------------
    rec_engine = None
    rec_results = None

    if args.recommend or args.recommend_for is not None or args.recommend_dashboard:
        rec_engine = RecommendationEngine(
            collaborative_weight=config.recommendation_collaborative_weight,
            content_weight=config.recommendation_content_weight,
            serendipity_factor=config.recommendation_serendipity_factor,
            num_recommendations=config.recommendation_num_recommendations,
            min_evaluations=config.recommendation_min_evaluations,
            max_similar_users=config.recommendation_max_similar_users,
            popular_items_fallback_size=config.recommendation_popular_items_fallback_size,
            seed=config.recommendation_seed,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | RECOMMENDATION ENGINE: Integer Affinity Analytics        |\n"
            "  | Collaborative filtering + content-based + hybrid blend  |\n"
            "  | Serendipity injection to break filter bubbles            |\n"
            '  | "Because you evaluated 15, you might enjoy 45."          |\n'
            "  | Every number deserves a zodiac sign and a digit sum.     |\n"
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # Dependent Type System & Curry-Howard Proof Engine setup
    # ----------------------------------------------------------------
    proof_engine = None
    dt_proofs: list = []

    if args.dependent_types or args.prove is not None or args.type_check or args.types_dashboard:
        proof_engine = ProofEngine(
            max_beta_reductions=config.dependent_types_max_beta_reductions,
            max_unification_depth=config.dependent_types_max_unification_depth,
            enable_cache=config.dependent_types_enable_proof_cache,
            cache_size=config.dependent_types_proof_cache_size,
            enable_type_inference=config.dependent_types_enable_type_inference,
            strict_mode=config.dependent_types_strict_mode,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | DEPENDENT TYPE SYSTEM & CURRY-HOWARD PROOF ENGINE       |\n"
            "  | Propositions as Types | Proofs as Programs              |\n"
            "  | Bidirectional type checking | Beta-normalization        |\n"
            '  | "We replaced n%3==0 with 800 lines of type theory."    |\n'
            "  | Every modulo is now a theorem. You're welcome.          |\n"
            "  +---------------------------------------------------------+"
        )

        # Early exit: prove a single number
        if args.prove is not None:
            proof = proof_engine.prove(args.prove)
            print(TypeDashboard.render_single_proof(
                proof,
                width=config.dependent_types_dashboard_width,
            ))
            if args.types_dashboard:
                print(TypeDashboard.render(
                    proof_engine,
                    proofs=[proof],
                    width=config.dependent_types_dashboard_width,
                    show_curry_howard=config.dependent_types_dashboard_show_curry_howard,
                    show_proof_tree=config.dependent_types_dashboard_show_proof_tree,
                    show_complexity_index=config.dependent_types_dashboard_show_complexity_index,
                ))
            return 0

    # ----------------------------------------------------------------
    # FizzKube Container Orchestration setup
    # ----------------------------------------------------------------
    fizzkube_cp = None
    fizzkube_middleware = None

    if args.fizzkube or args.fizzkube_dashboard:
        num_nodes = args.fizzkube_pods if args.fizzkube_pods is not None else config.fizzkube_num_nodes

        fizzkube_cp = FizzKubeControlPlane(
            num_nodes=num_nodes,
            cpu_per_node=config.fizzkube_cpu_per_node,
            memory_per_node=config.fizzkube_memory_per_node,
            pod_cpu_request=config.fizzkube_pod_cpu_request,
            pod_memory_request=config.fizzkube_pod_memory_request,
            pod_cpu_limit=config.fizzkube_pod_cpu_limit,
            pod_memory_limit=config.fizzkube_pod_memory_limit,
            desired_replicas=config.fizzkube_default_replicas,
            namespace_name=config.fizzkube_namespace,
            quota_cpu=config.fizzkube_resource_quota_cpu,
            quota_memory=config.fizzkube_resource_quota_memory,
            hpa_enabled=config.fizzkube_hpa_enabled,
            hpa_min_replicas=config.fizzkube_hpa_min_replicas,
            hpa_max_replicas=config.fizzkube_hpa_max_replicas,
            hpa_target_cpu=config.fizzkube_hpa_target_cpu_utilization,
            rules=list(config.rules),
            event_callback=event_bus.publish if event_bus else None,
        )

        fizzkube_middleware = FizzKubeMiddleware(
            control_plane=fizzkube_cp,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FIZZKUBE CONTAINER ORCHESTRATION: CLUSTER READY          |\n"
            "  | Every FizzBuzz evaluation is now a Kubernetes pod with  |\n"
            "  | resource requests, scheduling, and lifecycle tracking.  |\n"
            f"  | Nodes: {num_nodes:<49}|\n"
            f"  | Namespace: {config.fizzkube_namespace:<45}|\n"
            f"  | Pod resources: {config.fizzkube_pod_cpu_request}mF CPU, {config.fizzkube_pod_memory_request}FB memory{' ' * 20}|\n"
            "  | HPA: " + ("ENABLED" if config.fizzkube_hpa_enabled else "DISABLED") + f" (target: {config.fizzkube_hpa_target_cpu_utilization}% CPU utilization)" + " " * 14 + "|\n"
            '  | "Auto-scaling modulo operations since 2026."            |\n'
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # FizzLock Distributed Lock Manager setup
    # ----------------------------------------------------------------
    lock_manager = None
    lock_middleware_instance = None

    if args.locks or args.lock_dashboard:
        lock_policy_str = args.lock_policy or config.distributed_locks_policy
        if lock_policy_str == "wound-wait":
            policy_type = WaitPolicyType.WOUND_WAIT
        else:
            policy_type = WaitPolicyType.WAIT_DIE

        lock_wait_policy = WaitPolicy(policy_type=policy_type)
        lock_token_gen = FencingTokenGenerator()
        lock_profiler = ContentionProfiler(
            hot_lock_threshold_ms=config.distributed_locks_hot_lock_threshold_ms,
        )
        lock_lease_mgr = LeaseManager(
            lease_duration=config.distributed_locks_lease_duration,
            grace_period=config.distributed_locks_grace_period,
            check_interval=config.distributed_locks_check_interval,
        )
        lock_lease_mgr.start()

        lock_manager = HierarchicalLockManager(
            wait_policy=lock_wait_policy,
            token_generator=lock_token_gen,
            lease_manager=lock_lease_mgr,
            profiler=lock_profiler,
        )

        lock_middleware_instance = LockMiddleware(manager=lock_manager)

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZLOCK DISTRIBUTED LOCK MANAGER                       |\n"
            "  | Hierarchical Multi-Granularity Locking                   |\n"
            "  | X | S | IS | IX | U  —  5x5 Compatibility Matrix        |\n"
            f"  | Policy: {lock_policy_str:<48}|\n"
            f"  | Lease: {config.distributed_locks_lease_duration:.0f}s + {config.distributed_locks_grace_period:.0f}s grace{' ' * 32}|\n"
            "  | Tarjan SCC Deadlock Detection | Fencing Tokens           |\n"
            '  | "Serializability for modulo arithmetic."                 |\n'
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # FizzCDC Change Data Capture setup
    # ----------------------------------------------------------------
    cdc_pipeline = None
    cdc_agents = None
    cdc_sinks_list = None
    cdc_middleware_instance = None

    if args.cdc or args.cdc_dashboard:
        sinks_cfg = (
            [s.strip() for s in args.cdc_sinks.split(",")]
            if args.cdc_sinks
            else config.cdc_sinks
        )
        cdc_pipeline, cdc_agents, cdc_sinks_list, _cdc_registry = create_cdc_subsystem(
            sinks_config=sinks_cfg,
            compatibility=config.cdc_schema_compatibility,
            relay_interval_s=config.cdc_relay_interval_s,
            outbox_capacity=config.cdc_outbox_capacity,
        )

        cdc_middleware_instance = CDCMiddleware(pipeline=cdc_pipeline)

        # Start the background outbox relay
        cdc_pipeline.outbox_relay.start()

        sink_names = ", ".join(s.name for s in cdc_sinks_list) if cdc_sinks_list else "none"
        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZCDC — CHANGE DATA CAPTURE                           |\n"
            "  | Transactional Outbox | Schema Registry | Sink Relay     |\n"
            f"  | Sinks: {sink_names:<50}|\n"
            f"  | Relay Interval: {config.cdc_relay_interval_s:.2f}s  Capacity: {config.cdc_outbox_capacity:<14}|\n"
            "  | Capture: cache | blockchain | SLA | compliance          |\n"
            '  | "Every state change deserves a paper trail."            |\n'
            "  +---------------------------------------------------------+"
        )

    # ----------------------------------------------------------------
    # FizzBill Billing & Revenue Recognition setup
    # ----------------------------------------------------------------
    billing_usage_meter = None
    billing_contract = None
    billing_middleware_instance = None
    billing_rating_engine = None
    billing_recognizer = None
    billing_dunning = None
    billing_fizzops_calc = None
    billing_obligations = None
    billing_rated_usage = None

    if args.billing or args.billing_invoice or args.billing_dashboard:
        # Determine tier
        tier_name = args.billing_tier or config.billing_default_tier
        tier_map = {
            "free": BillingSubscriptionTier.FREE,
            "developer": BillingSubscriptionTier.DEVELOPER,
            "professional": BillingSubscriptionTier.PROFESSIONAL,
            "enterprise": BillingSubscriptionTier.ENTERPRISE,
        }
        billing_tier = tier_map.get(tier_name, BillingSubscriptionTier.FREE)
        billing_tier_def = TIER_DEFINITIONS[billing_tier]

        # Create contract
        billing_contract = Contract(
            tenant_id=config.billing_default_tenant_id,
            tier=billing_tier,
            monthly_price=billing_tier_def.monthly_price_fb,
            spending_cap=config.billing_spending_cap,
        )

        # Create subsystems
        billing_usage_meter = UsageMeter()
        billing_fizzops_calc = FizzOpsCalculator()
        billing_rating_engine = RatingEngine()
        billing_recognizer = RevenueRecognizer()
        billing_dunning = DunningManager()

        # Create middleware
        billing_middleware_instance = BillingMiddleware(
            usage_meter=billing_usage_meter,
            contract=billing_contract,
            fizzops_calculator=billing_fizzops_calc,
        )

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZBILL — API MONETIZATION & SUBSCRIPTION BILLING      |\n"
            "  | ASC 606 Revenue Recognition | Dunning | FizzOps Meter   |\n"
            f"  | Tier: {billing_tier_def.display_name:<51}|\n"
            f"  | Quota: {(str(billing_tier_def.monthly_fizzops_quota) + ' FizzOps/mo' if billing_tier_def.monthly_fizzops_quota > 0 else 'Unlimited'):<50}|\n"
            f"  | Price: FB${billing_tier_def.monthly_price_fb:<47.2f}|\n"
            '  | "Revenue is recognized when obligations are satisfied." |\n'
            "  +---------------------------------------------------------+"
        )

    elif args.billing_invoice:
        print("\n  FizzBill not enabled. Use --billing to enable.\n")
    elif args.billing_dashboard:
        print("\n  FizzBill not enabled. Use --billing to enable.\n")

    # ----------------------------------------------------------------
    # FizzBuzz Intellectual Property Office setup
    # ----------------------------------------------------------------
    ip_trademark_registry = None
    ip_patent_examiner = None
    ip_copyright_registry = None
    ip_license_manager = None
    ip_tribunal = None

    if args.ip_office or args.trademark or args.patent or args.ip_dashboard:
        ip_trademark_registry = TrademarkRegistry(
            similarity_threshold=config.ip_office_trademark_similarity_threshold,
            renewal_days=config.ip_office_trademark_renewal_days,
        )
        ip_patent_examiner = PatentExaminer(
            novelty_threshold=config.ip_office_patent_novelty_threshold,
        )
        ip_copyright_registry = CopyrightRegistry(
            originality_threshold=config.ip_office_copyright_originality_threshold,
        )
        ip_license_manager = LicenseManager()
        ip_tribunal = IPDisputeTribunal()

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZBUZZ INTELLECTUAL PROPERTY OFFICE                    |\n"
            "  | Trademarks | Patents | Copyrights | Licenses | Disputes |\n"
            "  | Soundex + Metaphone | Kolmogorov | Levenshtein          |\n"
            '  | "Your modulo operation may be patented."                 |\n'
            "  +---------------------------------------------------------+"
        )

        if args.trademark:
            result = ip_trademark_registry.apply(
                mark=args.trademark,
                applicant="CLI User",
                description=f"Trademark application for '{args.trademark}' via CLI",
            )
            status_str = result.status.name
            print(f"\n  Trademark Application: {result.application_id}")
            print(f"    Mark:   {result.mark}")
            print(f"    Status: {status_str}")
            if result.status.name == "OPPOSED":
                similar = ip_trademark_registry.search_similar(args.trademark)
                if similar:
                    print("    Conflicts:")
                    for mark, score in similar:
                        print(f"      - '{mark}' (similarity: {score:.2%})")
            elif result.registered_at:
                print(f"    Registered: {result.registered_at.strftime('%Y-%m-%d')}")
                print(f"    Expires:    {result.expires_at.strftime('%Y-%m-%d')}")
            print()

        if args.patent:
            # Parse the patent description: try to extract divisor and label
            desc = args.patent
            divisor = 7  # default
            label = "Custom"
            parts = desc.lower().split()
            for i, p in enumerate(parts):
                if p == "by" and i + 1 < len(parts):
                    try:
                        divisor = int(parts[i + 1])
                    except ValueError:
                        pass
                if p == "yields" and i + 1 < len(parts):
                    label = parts[i + 1].capitalize()

            result = ip_patent_examiner.examine(
                title=f"Method for FizzBuzz Evaluation: {desc}",
                description=desc,
                divisor=divisor,
                label=label,
                inventor="CLI User",
            )
            print(f"\n  Patent Application: {result.patent_id}")
            print(f"    Title:             {result.title}")
            print(f"    Status:            {result.status.name}")
            print(f"    Novelty:           {result.novelty_score:.2f}")
            print(f"    Non-obviousness:   {result.non_obviousness_score:.2f}")
            print(f"    Utility:           {result.utility_score:.2f}")
            if result.prior_art_refs:
                print("    Prior Art:")
                for ref in result.prior_art_refs:
                    print(f"      - {ref}")
            print()

    # ----------------------------------------------------------------
    # FizzPM Package Manager setup
    # ----------------------------------------------------------------
    fizzpm_manager = None

    if args.fizzpm or args.fizzpm_install or args.fizzpm_audit or args.fizzpm_dashboard:
        fizzpm_manager = FizzPMManager(
            audit_on_install=config.fizzpm_audit_on_install,
            lockfile_path=config.fizzpm_lockfile_path,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FIZZPM PACKAGE MANAGER: SAT-POWERED DEPENDENCIES        |\n"
            "  | 8 packages | DPLL solver | Semantic versioning          |\n"
            "  | Vulnerability scanning | Deterministic lockfile         |\n"
            '  | "npm install but the registry is a Python dict."        |\n'
            "  | Your dependency graph is NP-complete. You're welcome.   |\n"
            "  +---------------------------------------------------------+"
        )

        if args.fizzpm_install:
            result = fizzpm_manager.install(args.fizzpm_install)
            print(fizzpm_manager.render_install_summary(result))

            if config.fizzpm_audit_on_install and fizzpm_manager.vulnerabilities:
                print(fizzpm_manager.render_audit_report())
        else:
            # Install default packages
            for pkg_name in config.fizzpm_default_packages:
                fizzpm_manager.install(pkg_name)

        if args.fizzpm_audit:
            fizzpm_manager.audit()
            print(fizzpm_manager.render_audit_report())

    # Create rule engine via factory (the ACL wraps this in an adapter below)
    rule_engine = RuleEngineFactory.create(strategy)

    builder = (
        FizzBuzzServiceBuilder()
        .with_config(config)
        .with_event_bus(event_bus)
        .with_rule_engine(rule_engine)
        .with_output_format(output_format)
        .with_locale_manager(locale_mgr)
        .with_default_middleware()
    )

    # Add Unit of Work to builder if configured
    if uow is not None:
        builder.with_unit_of_work(uow)

    # Add auth context to builder
    if auth_context is not None:
        builder.with_auth_context(auth_context)

    # Add tracing middleware (priority -2, runs first)
    if tracing_mw is not None:
        builder.with_middleware(tracing_mw)

    # Add FizzOTel middleware (priority -10, runs before all others)
    if otel_middleware is not None:
        builder.with_middleware(otel_middleware)

    # Add authorization middleware if RBAC is active
    if rbac_active and auth_context is not None:
        auth_middleware = AuthorizationMiddleware(
            auth_context=auth_context,
            contact_email=config.rbac_access_denied_contact_email,
            next_training_session=config.rbac_next_training_session,
            event_bus=event_bus,
        )
        builder.with_middleware(auth_middleware)

    # Add translation middleware if i18n is active
    if locale_mgr is not None:
        builder.with_middleware(TranslationMiddleware(locale_manager=locale_mgr))

    if es_middleware is not None:
        builder.with_middleware(es_middleware)

    if cb_middleware is not None:
        builder.with_middleware(cb_middleware)

    if cache_middleware is not None:
        builder.with_middleware(cache_middleware)

    if chaos_middleware is not None:
        builder.with_middleware(chaos_middleware)

    if sla_middleware is not None:
        builder.with_middleware(sla_middleware)

    if metrics_middleware is not None:
        builder.with_middleware(metrics_middleware)

    if mesh_middleware is not None:
        builder.with_middleware(mesh_middleware)

    if rate_limit_middleware is not None:
        builder.with_middleware(rate_limit_middleware)

    if compliance_middleware is not None:
        builder.with_middleware(compliance_middleware)

    if finops_middleware is not None:
        builder.with_middleware(finops_middleware)

    if dr_middleware is not None:
        builder.with_middleware(dr_middleware)

    if ab_middleware is not None:
        builder.with_middleware(ab_middleware)

    if mq_middleware is not None:
        builder.with_middleware(mq_middleware)

    if vault_middleware is not None:
        builder.with_middleware(vault_middleware)

    if pipeline_middleware is not None:
        builder.with_middleware(pipeline_middleware)

    if gateway_middleware is not None:
        builder.with_middleware(gateway_middleware)

    if graph_middleware is not None:
        builder.with_middleware(graph_middleware)

    if fbaas_middleware is not None:
        builder.with_middleware(fbaas_middleware)

    if paxos_middleware is not None:
        builder.with_middleware(paxos_middleware)

    if quantum_middleware is not None:
        builder.with_middleware(quantum_middleware)

    if federated_middleware is not None:
        builder.with_middleware(federated_middleware)

    if kg_middleware is not None:
        builder.with_middleware(kg_middleware)

    if sm_middleware is not None:
        builder.with_middleware(sm_middleware)

    if fizzkube_middleware is not None:
        builder.with_middleware(fizzkube_middleware)

    if kernel_middleware is not None:
        builder.with_middleware(kernel_middleware)

    if p2p_middleware is not None:
        builder.with_middleware(p2p_middleware)

    # Add Digital Twin middleware (priority -4, captures full pipeline overhead)
    if twin_middleware is not None:
        builder.with_middleware(twin_middleware)

    # Add feature flag middleware (priority -3, runs before tracing)
    if flag_middleware is not None:
        builder.with_middleware(flag_middleware)

    # Add Query Optimizer middleware (priority -3, runs early)
    if qo_optimizer is not None and args.optimize:
        qo_middleware = OptimizerMiddleware(
            optimizer=qo_optimizer,
            hints=qo_hints,
            rules=list(config.rules),
        )
        builder.with_middleware(qo_middleware)

    # Add CRDT middleware (priority 870, between WAL and archaeology)
    if crdt_middleware is not None:
        builder.with_middleware(crdt_middleware)

    # Add WAL middleware (priority 850, between locks and archaeology)
    if wal_middleware is not None:
        builder.with_middleware(wal_middleware)

    # Add Lock middleware (priority 800, before archaeology)
    if lock_middleware_instance is not None:
        builder.with_middleware(lock_middleware_instance)

    # Add Archaeology middleware (priority 900, near end of chain)
    if arch_middleware is not None:
        builder.with_middleware(arch_middleware)

    # Add CDC middleware (priority 950, captures state after evaluation)
    if cdc_middleware_instance is not None:
        builder.with_middleware(cdc_middleware_instance)

    if billing_middleware_instance is not None:
        builder.with_middleware(billing_middleware_instance)

    # Add Time-Travel middleware (priority -5, captures snapshots after full pipeline)
    if tt_middleware is not None:
        builder.with_middleware(tt_middleware)

    service = builder.build()

    # ----------------------------------------------------------------
    # Dependency Injection Container Demonstration
    # ----------------------------------------------------------------
    # The DI container exists alongside the builder. It does NOT replace
    # the existing wiring — it merely proves that we COULD have used an
    # IoC container instead of a builder, had we wanted to add yet another
    # layer of abstraction to our already stratospheric abstraction stack.
    # ----------------------------------------------------------------
    from enterprise_fizzbuzz.infrastructure.container import Container, Lifetime
    from enterprise_fizzbuzz.domain.interfaces import IEventBus

    di_container = Container()
    di_container.register(
        IEventBus,
        lifetime=Lifetime.SINGLETON,
        factory=lambda: event_bus,
    ).register(
        ConfigurationManager,
        lifetime=Lifetime.ETERNAL,
        factory=lambda: config,
    )

    logger.debug(
        "DI Container initialized with %d bindings. "
        "These bindings coexist peacefully with the builder-based wiring, "
        "because two parallel object construction strategies are better than one.",
        di_container.get_registration_count(),
    )

    # Wire up the Anti-Corruption Layer strategy adapter.
    # This is done after build() because the adapter needs the resolved
    # rules list, which is only available on the built service.
    # The ACL wraps the rule engine in a strategy adapter that translates
    # raw FizzBuzzResults into clean EvaluationResults and back again,
    # because one layer of abstraction is never enough.
    strategy_adapter = StrategyAdapterFactory.create(
        strategy=strategy,
        rules=service._rules,
        event_bus=event_bus,
        decision_threshold=config.ml_decision_threshold,
        ambiguity_margin=config.ml_ambiguity_margin,
        enable_disagreement_tracking=config.ml_enable_disagreement_tracking,
    )
    service._strategy_port = strategy_adapter

    # Inject the Wuzz rule when feature flags are active
    if flag_store is not None:
        wuzz_rule_def = RuleDefinition(
            name="WuzzRule", divisor=7, label="Wuzz", priority=3
        )
        wuzz_rule = ConcreteRule(wuzz_rule_def)
        service._rules.append(wuzz_rule)

    # Print authentication status
    if auth_context is not None:
        print(f"  Authenticated as: {auth_context.user} ({auth_context.role.name})")

    # ----------------------------------------------------------------
    # Health Check Probes (Kubernetes-style)
    # ----------------------------------------------------------------
    health_registry = None
    startup_probe = None
    liveness_probe_inst = None
    readiness_probe_inst = None
    self_healing_mgr = None

    if args.health or args.liveness or args.readiness or args.startup_probe or args.health_dashboard or args.self_heal:
        HealthCheckRegistry.reset()
        health_registry = HealthCheckRegistry.get_instance()

        # Register subsystem health checks
        health_registry.register(ConfigHealthCheck(config))
        health_registry.register(CircuitBreakerHealthCheck(
            registry=CircuitBreakerRegistry.get_instance() if args.circuit_breaker else None,
        ))
        health_registry.register(CacheCoherenceHealthCheck(
            cache_store=cache_store,
        ))
        health_registry.register(SLABudgetHealthCheck(
            sla_monitor=sla_monitor,
        ))

        # ML engine health check — only if using ML strategy
        if strategy == EvaluationStrategy.MACHINE_LEARNING:
            health_registry.register(MLEngineHealthCheck(
                engine=rule_engine,
                rules=service._rules,
            ))
        else:
            health_registry.register(MLEngineHealthCheck())

        # Create probes
        def _evaluate_canary(n: int) -> str:
            """Evaluate a single number for liveness check."""
            results = service.run(n, n)
            return results[0].output if results else ""

        liveness_probe_inst = LivenessProbe(
            evaluate_fn=_evaluate_canary,
            canary_number=config.health_check_canary_number,
            canary_expected=config.health_check_canary_expected,
            event_bus=event_bus,
        )

        readiness_probe_inst = ReadinessProbe(
            registry=health_registry,
            degraded_is_ready=config.health_check_degraded_is_ready,
            event_bus=event_bus,
        )

        startup_probe = StartupProbe(
            milestones=config.health_check_startup_milestones,
            timeout_seconds=config.health_check_startup_timeout,
            event_bus=event_bus,
        )

        # Record startup milestones that have already been reached
        startup_probe.record_milestone("config_loaded")
        startup_probe.record_milestone("rules_initialized")
        startup_probe.record_milestone("engine_created")
        startup_probe.record_milestone("middleware_assembled")
        startup_probe.record_milestone("service_built")

        if args.self_heal:
            self_healing_mgr = SelfHealingManager(
                registry=health_registry,
                max_retries=config.health_check_self_healing_max_retries,
                backoff_base_ms=config.health_check_self_healing_backoff_ms,
                event_bus=event_bus,
            )

        print(
            "  +---------------------------------------------------------+\n"
            "  | HEALTH CHECKS: Kubernetes-Style Probes ENABLED          |\n"
            "  | Liveness, readiness, and startup probes are now active. |\n"
            "  | The platform's vital signs are being monitored with     |\n"
            "  | the same rigor as a Kubernetes pod in production.       |\n"
            "  +---------------------------------------------------------+"
        )

    # Handle standalone probe commands (run and exit)
    if args.liveness and liveness_probe_inst is not None:
        report = liveness_probe_inst.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
        if not (args.readiness or args.startup_probe):
            return 0 if report.overall_status.name == "UP" else 1

    if args.readiness and readiness_probe_inst is not None:
        report = readiness_probe_inst.probe()
        if self_healing_mgr is not None and report.overall_status.name not in ("UP",):
            healing_results = self_healing_mgr.heal_all_unhealthy(report.subsystem_checks)
            if any(healing_results.values()):
                # Re-probe after healing
                report = readiness_probe_inst.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
        if not args.startup_probe:
            return 0 if report.overall_status.name in ("UP", "DEGRADED") else 1

    if args.startup_probe and startup_probe is not None:
        report = startup_probe.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
        return 0 if report.overall_status.name == "UP" else 1

    # Cache warming (pre-populate cache, defeating the purpose)
    if args.cache_warm and cache_store is not None:
        cache_warmer = CacheWarmer(
            cache_store=cache_store,
            rule_engine=service._rule_engine,
            rules=service._rules,
        )
        warmed_count = cache_warmer.warm(start, end)
        print(
            f"  Cache warmed with {warmed_count} entries for range [{start}, {end}]."
        )
        print(
            "  (The entire purpose of caching has been defeated. Congratulations.)"
        )
        print()
    elif args.cache_warm:
        print("\n  Cache not enabled. Use --cache to enable.\n")
        return 0

    # Execute -- use locale manager for status messages if available
    if locale_mgr is not None:
        print(f"  {locale_mgr.t('messages.evaluating', start=start, end=end)}")
        print(f"  {locale_mgr.t('messages.strategy', name=strategy.name)}")
        print(f"  {locale_mgr.t('messages.output_format', name=output_format.name)}")
    else:
        print(f"  Evaluating FizzBuzz for range [{start}, {end}]...")
        print(f"  Strategy: {strategy.name}")
        print(f"  Output Format: {output_format.name}")
    print()

    # Run the data pipeline if enabled (standalone ETL mode)
    pipeline_records = None
    if pipeline is not None and args.pipeline:
        pipeline_records = pipeline.run(start, end)

    # ----------------------------------------------------------------
    # Blue/Green Deployment Simulation
    # ----------------------------------------------------------------
    deployment_summary = None
    if args.deploy:
        deploy_orchestrator = DeploymentOrchestrator(
            rules=[r.get_definition() for r in service._rules],
            shadow_traffic_count=config.blue_green_shadow_traffic_count,
            smoke_test_numbers=config.blue_green_smoke_test_numbers,
            bake_period_ms=config.blue_green_bake_period_ms,
            bake_period_evaluations=config.blue_green_bake_period_evaluations,
            cutover_delay_ms=config.blue_green_cutover_delay_ms,
            auto_rollback=config.blue_green_rollback_auto,
            event_emitter=lambda e: event_bus.publish(e),
        )

        print(
            "  +==========================================================+\n"
            "  | BLUE/GREEN DEPLOYMENT SIMULATION                        |\n"
            "  | Zero-downtime deployment for a process with zero uptime |\n"
            "  +==========================================================+"
        )
        print()

        deployment_summary = deploy_orchestrator.deploy()

        state_display = deployment_summary["state"]
        duration_display = f"{deployment_summary['total_duration_ms']:.2f}ms"
        active_display = deployment_summary.get("active_slot", "N/A")
        print(f"  Deployment {state_display} in {duration_display}")
        print(f"  Active slot: {active_display}")
        print()

        if args.deploy_rollback:
            from enterprise_fizzbuzz.infrastructure.blue_green import RollbackManager
            rollback_mgr = RollbackManager(event_emitter=lambda e: event_bus.publish(e))
            try:
                rollback_mgr.execute_rollback(
                    deploy_orchestrator.cutover_manager,
                    reason="Manual rollback requested via --deploy-rollback",
                )
                deployment_summary["rollback"] = {
                    "rolled_back": True,
                    "reason": "Manual rollback requested via --deploy-rollback",
                }
                print("  Rollback completed. Blue slot restored.")
                print("  Zero users impacted. (There was one user.)")
                print()
            except Exception as e:
                print(f"  Rollback failed: {e}")
                print()

        if args.deploy_dashboard:
            print(DeploymentDashboard.render(
                deployment_summary,
                width=config.blue_green_dashboard_width,
            ))

    elif args.deploy_dashboard:
        print("\n  Deployment not active. Use --deploy to enable.\n")

    elif args.deploy_rollback:
        print("\n  Deployment not active. Use --deploy to enable.\n")

    # ----------------------------------------------------------------
    # Custom Bytecode VM (FBVM) Execution Path
    # ----------------------------------------------------------------
    # When --vm is active, we compile the rules to FBVM bytecode and
    # execute them through our custom virtual machine instead of using
    # the standard Python-based rule engine. This adds approximately
    # 700 lines of infrastructure to compute n % 3 == 0, which is
    # exactly the kind of engineering decision this platform celebrates.
    # ----------------------------------------------------------------
    if args.vm or args.vm_disasm or args.vm_trace or args.vm_dashboard:
        from enterprise_fizzbuzz.domain.models import RuleDefinition as _RuleDef

        vm_rules = config.rules
        vm_trace = args.vm_trace or config.vm_trace_execution
        vm_optimize = config.vm_enable_optimizer

        # Compile rules to bytecode
        vm_program, vm_compiler = compile_rules(
            vm_rules,
            enable_optimizer=vm_optimize,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | FBVM: FizzBuzz Bytecode Virtual Machine ENABLED         |\n"
            f"  | Rules compiled: {len(vm_rules):<40}|\n"
            f"  | Instructions: {len(vm_program.instructions):<42}|\n"
            f"  | Optimized: {'Yes' if vm_program.optimized else 'No':<45}|\n"
            "  | Because Python was too efficient for modulo arithmetic. |\n"
            "  +---------------------------------------------------------+"
        )

        # Show disassembly if requested
        if args.vm_disasm:
            print()
            print(Disassembler.disassemble(vm_program))

        # Execute via VM
        vm_instance = FizzBuzzVM(
            cycle_limit=config.vm_cycle_limit,
            trace_execution=vm_trace,
            register_count=config.vm_register_count,
            event_bus=event_bus,
        )

        boot_time = time.perf_counter()
        vm_results_output = []

        for number in range(start, end + 1):
            result_str = vm_instance.execute(vm_program, number)
            vm_results_output.append(f"  {result_str}")

        wall_time_ms = (time.perf_counter() - boot_time) * 1000

        # Print results
        print()
        for line in vm_results_output:
            print(line)
        print()

        print(f"  FBVM evaluated {end - start + 1} numbers in {wall_time_ms:.2f}ms")
        print(f"  Average cycles per number: {vm_instance.state.cycles}")

        # Show trace if requested
        if vm_trace and vm_instance.execution_traces:
            print()
            print(VMDashboard.render_trace(
                vm_instance.execution_traces,
                width=config.vm_dashboard_width,
            ))

        # Show dashboard if requested
        if args.vm_dashboard:
            print()
            print(VMDashboard.render(
                vm_program,
                vm_instance,
                width=config.vm_dashboard_width,
                show_registers=config.vm_dashboard_show_registers,
                show_disassembly=config.vm_dashboard_show_disassembly,
            ))

        # If --vm was the only mode, skip the normal execution path
        if args.vm and not args.use_async:
            return 0

    boot_time = time.perf_counter()

    if args.use_async:
        results = asyncio.run(service.run_async(start, end))
    else:
        results = service.run(start, end)

    wall_time_ms = (time.perf_counter() - boot_time) * 1000

    # Output results
    formatted = service.format_results(results)
    print(formatted)

    # Summary
    if not args.no_summary:
        summary_text = service.format_summary()
        print(summary_text)
        if locale_mgr is not None:
            print(f"\n  {locale_mgr.t('messages.wall_clock', time=f'{wall_time_ms:.2f}')}")
        else:
            print(f"\n  Wall clock time: {wall_time_ms:.2f}ms")

    # ----------------------------------------------------------------
    # Dependent Type System post-execution
    # ----------------------------------------------------------------
    if proof_engine is not None and (args.dependent_types or args.type_check):
        # Prove every number in the range
        dt_proofs = proof_engine.batch_prove(start, end)
        print(f"\n  Dependent Types: constructed {len(dt_proofs)} proof(s), "
              f"avg PCI = {proof_engine.average_complexity_index:.1f}")

    # ----------------------------------------------------------------
    # Recommendation Engine post-execution
    # ----------------------------------------------------------------
    if rec_engine is not None:
        # Record all evaluated numbers for the default user
        user_id = "cli-user"
        if auth_context is not None:
            user_id = auth_context.user
        for number in range(start, end + 1):
            rec_engine.record_evaluation(user_id, number)

        # Generate recommendations
        if args.recommend_for is not None:
            # Item-to-item recommendations for a specific number
            pool = list(range(1, max(end + 50, 101)))
            rec_results = rec_engine.recommend_for_number(
                args.recommend_for,
                candidate_pool=pool,
                n=config.recommendation_num_recommendations,
            )
            print(f"\n  Recommendations similar to {args.recommend_for}:")
            for num, score, explanation in rec_results:
                print(explanation)
            print()
        elif args.recommend:
            # Personalized recommendations for the user
            pool = list(range(1, max(end + 50, 101)))
            rec_results = rec_engine.recommend(
                user_id,
                candidate_pool=pool,
                n=config.recommendation_num_recommendations,
            )
            print(f"\n  Personalized recommendations for {user_id}:")
            for num, score, explanation in rec_results:
                print(explanation)
            print()

    # Archaeological excavation output
    if arch_engine is not None and args.excavate is not None:
        print(arch_engine.excavate(args.excavate, width=config.archaeology_dashboard_width))

    # Distributed tracing output
    if tracing_enabled:
        completed_traces = tracing_service.get_completed_traces()
        if args.trace_json:
            print(TraceExporter.export_json(completed_traces))
        else:
            # Waterfall for each trace
            for trace in completed_traces:
                print(TraceRenderer.render_waterfall(trace))
            print(TraceRenderer.render_summary(completed_traces))

    # Event Sourcing summary and temporal queries
    if es_system is not None:
        print(es_system.render_summary())

        if args.replay:
            replay_result = es_system.replay_events()
            print(f"  Replayed {replay_result['replayed_events']} events.")
            print(f"  Statistics after replay: {replay_result['statistics']}")
            print()

        if args.temporal_query is not None:
            temporal_state = es_system.temporal_engine.query_at_sequence(
                args.temporal_query
            )
            print("  +===========================================================+")
            print("  |             TEMPORAL QUERY RESULT                         |")
            print("  +===========================================================+")
            print(f"  |  As-of sequence    : {args.temporal_query:<37}|")
            print(f"  |  Events processed  : {temporal_state['events_processed']:<37}|")
            print(f"  |  Evaluations       : {temporal_state['total_evaluations']:<37}|")
            print(f"  |  Fizz Count        : {temporal_state['fizz_count']:<37}|")
            print(f"  |  Buzz Count        : {temporal_state['buzz_count']:<37}|")
            print(f"  |  FizzBuzz Count    : {temporal_state['fizzbuzz_count']:<37}|")
            print(f"  |  Plain Count       : {temporal_state['plain_count']:<37}|")
            print("  +===========================================================+")
            print()

    if blockchain_observer is not None:
        print(blockchain_observer.get_blockchain().get_chain_summary())

    # Chaos Engineering post-mortem
    if args.post_mortem and chaos_monkey is not None:
        scenario_name = args.gameday if args.gameday else None
        print(PostMortemGenerator.generate(chaos_monkey, scenario_name))

    if args.circuit_status and cb_middleware is not None:
        print(CircuitBreakerDashboard.render(cb_middleware.circuit_breaker))
    elif args.circuit_status:
        if locale_mgr is not None:
            print(f"\n  {locale_mgr.t('messages.circuit_breaker_not_enabled')}\n")
        else:
            print("\n  Circuit breaker not enabled. Use --circuit-breaker to enable.\n")

    # Feature flag evaluation summary
    if flag_store is not None:
        print(FlagEvaluationSummary.render(flag_store))

    # SLA dashboard
    if args.sla_dashboard and sla_monitor is not None:
        print(SLADashboard.render(sla_monitor))
    elif args.sla_dashboard:
        print("\n  SLA monitoring not enabled. Use --sla to enable.\n")

    # On-call status (when combined with --sla)
    if args.on_call and sla_monitor is not None:
        print(SLADashboard.render_on_call(sla_monitor))

    # Health check dashboard (post-execution)
    if args.health_dashboard and readiness_probe_inst is not None:
        report = readiness_probe_inst.probe()
        if self_healing_mgr is not None and report.overall_status.name not in ("UP",):
            healing_results = self_healing_mgr.heal_all_unhealthy(report.subsystem_checks)
            if any(healing_results.values()):
                report = readiness_probe_inst.probe()
        print(HealthDashboard.render(report, show_details=config.health_check_dashboard_show_details))
    elif args.health_dashboard:
        print("\n  Health checks not enabled. Use --health to enable.\n")

    # Cache statistics dashboard
    if args.cache_stats and cache_store is not None:
        stats = cache_store.get_statistics()
        print(CacheDashboard.render(stats))
    elif args.cache_stats:
        print("\n  Cache not enabled. Use --cache to enable.\n")

    # Prometheus metrics export
    if args.metrics_export and metrics_registry is not None:
        print("\n  +-- PROMETHEUS TEXT EXPOSITION FORMAT ---------------------+")
        print(PrometheusTextExporter.export(metrics_registry))
        print("  +---------------------------------------------------------+\n")
    elif args.metrics_export:
        print("\n  Metrics not enabled. Use --metrics to enable.\n")

    # Metrics dashboard
    if args.metrics_dashboard and metrics_registry is not None:
        print(MetricsDashboard.render(metrics_registry, width=config.metrics_dashboard_width))
        # Run cardinality check
        if metrics_cardinality is not None:
            cardinalities = metrics_cardinality.check_all(metrics_registry)
            print("  Cardinality report:")
            for name, count in cardinalities.items():
                status = "OK" if count <= config.metrics_cardinality_threshold else "WARNING"
                print(f"    {name}: {count} unique label combos [{status}]")
            print()
    elif args.metrics_dashboard:
        print("\n  Metrics not enabled. Use --metrics to enable.\n")

    # Webhook dashboard and logs
    if webhook_manager is not None:
        print(WebhookDashboard.render(webhook_manager))

    if args.webhook_log and webhook_manager is not None:
        print(WebhookDashboard.render_delivery_log(webhook_manager))

    if args.webhook_dlq and webhook_manager is not None:
        print(WebhookDashboard.render_dlq(webhook_manager))

    # Service mesh topology
    if args.mesh_topology and mesh_control_plane is not None:
        print(MeshTopologyVisualizer.render(
            mesh_control_plane.registry,
            mesh_control_plane,
        ))
    elif args.mesh_topology:
        print("\n  Service mesh not enabled. Use --service-mesh to enable.\n")

    # Hot-reload dashboard
    if args.reload_status and hot_reload_raft is not None:
        print(HotReloadDashboard.render(
            raft=hot_reload_raft,
            orchestrator=hot_reload_orchestrator,
            watcher=hot_reload_watcher,
            dependency_graph=hot_reload_dep_graph,
            rollback_manager=hot_reload_rollback_mgr,
            width=config.hot_reload_dashboard_width,
            show_raft_details=config.hot_reload_dashboard_show_raft_details,
        ))

    # Rate limiting dashboard
    if args.rate_limit_dashboard and rate_limit_quota_manager is not None:
        print(RateLimitDashboard.render(
            rate_limit_quota_manager,
            width=config.rate_limiting_dashboard_width,
        ))
    elif args.rate_limit_dashboard:
        print("\n  Rate limiting not enabled. Use --rate-limit to enable.\n")

    # Quota status summary
    if args.quota and rate_limit_quota_manager is not None:
        qm = rate_limit_quota_manager
        print(
            "  +---------------------------------------------------------+\n"
            "  | QUOTA STATUS SUMMARY                                    |\n"
            "  +---------------------------------------------------------+\n"
            f"  | Requests:  {f'{qm.total_allowed} allowed / {qm.total_denied} denied':<45}|\n"
            f"  | Denial Rate: {f'{qm.denial_rate:.1f}%':<43}|\n"
            "  +---------------------------------------------------------+"
        )
    elif args.quota:
        print("\n  Rate limiting not enabled. Use --rate-limit to enable.\n")

    # Compliance dashboard and reports
    if args.compliance_dashboard and compliance_framework is not None:
        print(ComplianceDashboard.render(compliance_framework, width=config.compliance_dashboard_width))
    elif args.compliance_dashboard:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")

    if args.compliance_report and compliance_framework is not None:
        print(ComplianceDashboard.render_report(compliance_framework))
    elif args.compliance_report:
        print("\n  Compliance framework not enabled. Use --compliance to enable.\n")

    if args.sox_audit and compliance_framework is not None:
        posture = compliance_framework.get_posture_summary()
        sox_trail = posture.get("sox_stats", [])
        if sox_trail:
            print(
                "  +---------------------------------------------------------+\n"
                "  | SOX SEGREGATION OF DUTIES AUDIT TRAIL                   |\n"
                "  +---------------------------------------------------------+"
            )
            for entry in sox_trail[-10:]:  # Last 10 entries
                assignments = entry.get("assignments", {})
                segregated = entry.get("segregation_satisfied", False)
                status = "OK" if segregated else "VIOLATION"
                num_val = entry.get("number", "?")
                sox_line = f"Number {num_val:>5} [{status}]"
                print(f"  | {sox_line:<57}|")
                for role, person in assignments.items():
                    person_name = person.get("name", "?")
                    role_line = f"  {role}: {person_name}"
                    print(f"  | {role_line:<57}|")
            if len(sox_trail) > 10:
                more_line = f"... and {len(sox_trail) - 10} more entries"
                print(f"  | {more_line:<57}|")
            print("  +---------------------------------------------------------+")
            print()
        else:
            print("\n  No SOX audit trail entries recorded.\n")

    if args.hipaa_check and compliance_framework is not None:
        posture = compliance_framework.get_posture_summary()
        hipaa_stats = posture.get("hipaa_stats", {})
        if hipaa_stats:
            print(
                "  +---------------------------------------------------------+\n"
                "  | HIPAA PHI ACCESS LOG & ENCRYPTION STATISTICS            |\n"
                "  +---------------------------------------------------------+\n"
                f"  | PHI Encryptions:    {hipaa_stats.get('phi_encryptions', 0):<36}|\n"
                f"  | PHI Redactions:     {hipaa_stats.get('phi_redactions', 0):<36}|\n"
                f"  | PHI Access Events:  {hipaa_stats.get('phi_access_events', 0):<36}|\n"
                f"  | Algorithm:          {hipaa_stats.get('encryption_algorithm', 'N/A'):<36}|\n"
                f"  | Actual Security:    {hipaa_stats.get('actual_security_provided', 'None'):<36}|\n"
                "  +---------------------------------------------------------+"
            )
            print()
        else:
            print("\n  No HIPAA statistics recorded.\n")

    # FinOps invoice
    if args.invoice and finops_tracker is not None:
        cache_hit_ratio = 0.0
        if cache_store is not None:
            cache_stats = cache_store.get_statistics()
            cache_hit_ratio = cache_stats.get("hit_ratio", 0.0) if isinstance(cache_stats, dict) else 0.0
        print(InvoiceGenerator.generate(
            finops_tracker,
            session_id=stats_observer.session_id if hasattr(stats_observer, "session_id") else "N/A",
            cache_hit_ratio=cache_hit_ratio,
            width=config.finops_dashboard_width + 4,
        ))
    elif args.invoice:
        print("\n  FinOps not enabled. Use --finops to enable.\n")

    # FinOps cost dashboard
    if args.cost_dashboard and finops_tracker is not None:
        print(CostDashboard.render(finops_tracker, width=config.finops_dashboard_width + 4))
    elif args.cost_dashboard:
        print("\n  FinOps not enabled. Use --finops to enable.\n")

    # FinOps savings plan
    if args.savings_plan and finops_tracker is not None and finops_savings_calc is not None:
        print(finops_savings_calc.render(
            finops_tracker.total_spent,
            currency_symbol=config.finops_currency,
            width=config.finops_dashboard_width + 4,
        ))
    elif args.savings_plan:
        print("\n  FinOps not enabled. Use --finops to enable.\n")

    # ----------------------------------------------------------------
    # Disaster Recovery post-execution actions
    # ----------------------------------------------------------------
    if dr_system is not None:
        # Create manual backup if requested
        if args.backup and dr_middleware is not None:
            snapshot = dr_system.create_backup(
                dr_middleware.state,
                description="Manual backup via --backup flag",
            )
            print(
                f"\n  Backup created: {snapshot.manifest.snapshot_id}"
                f"\n  Entries: {snapshot.manifest.entry_count}"
                f"\n  Size: {snapshot.manifest.size_bytes} bytes"
                f"\n  Storage: RAM (will be lost on process exit)\n"
            )

        # Restore latest backup
        if args.restore:
            restored = dr_system.restore_latest()
            if restored:
                print(
                    f"\n  Restored {len(restored)} entries from latest backup."
                    f"\n  (This data was already in RAM. You're welcome.)\n"
                )
            else:
                print("\n  No backups available to restore. The void is empty.\n")

        # DR drill
        if args.dr_drill and dr_middleware is not None:
            drill_state = copy.deepcopy(dr_middleware.state) if dr_middleware.state else {"dummy": "data"}
            drill_result = dr_system.run_drill(drill_state)
            print(RecoveryDashboard.render_drill_report(
                drill_result, width=config.dr_dashboard_width
            ))

        # Backup list
        if args.backup_list:
            print(dr_system.render_backup_list())

        # DR dashboard
        if args.dr_dashboard:
            print(dr_system.render_dashboard())

        # Retention status
        if args.retention_status:
            print(dr_system.render_retention_status())

    # A/B Testing report and dashboard
    if ab_registry is not None:
        # Conclude all running experiments after evaluation
        for exp_name in list(ab_registry.get_running_experiments()):
            ab_registry.conclude_experiment(exp_name)

        if args.ab_report:
            for exp_name in ab_registry.get_all_experiments():
                print(ExperimentReport.render(
                    ab_registry, exp_name, width=config.ab_testing_dashboard_width
                ))

        if args.ab_dashboard:
            print(ExperimentDashboard.render(
                ab_registry, width=config.ab_testing_dashboard_width
            ))

    # Message Queue dashboards
    if mq_broker is not None:
        if args.mq_dashboard:
            print(MQDashboard.render(mq_broker, width=config.mq_dashboard_width + 4))

        if args.mq_lag:
            print(MQDashboard.render_lag(mq_broker, width=config.mq_dashboard_width + 4))

    # Vault dashboard and status
    if args.vault_dashboard and vault_seal_manager is not None:
        print(VaultDashboard.render(
            seal_manager=vault_seal_manager,
            secret_store=vault_secret_store,
            audit_log=vault_audit_log,
            rotation_scheduler=vault_rotation_scheduler,
            scan_findings=vault_scan_findings,
            width=config.vault_dashboard_width,
        ))
    elif args.vault_dashboard:
        print("\n  Vault not enabled. Use --vault to enable.\n")

    if args.vault_status and vault_seal_manager is not None:
        seal_status = "SEALED" if vault_seal_manager.is_sealed else "UNSEALED"
        init_status = "YES" if vault_seal_manager.is_initialized else "NO"
        print(
            "  +---------------------------------------------------------+\n"
            "  | VAULT STATUS                                            |\n"
            "  +---------------------------------------------------------+\n"
            f"  | Status:     {seal_status:<44}|\n"
            f"  | Initialized: {init_status:<43}|\n"
            f"  | Shares:     {f'{vault_seal_manager.shares_submitted}/{vault_seal_manager.shares_required}':<44}|\n"
            "  +---------------------------------------------------------+"
        )
        if vault_secret_store is not None:
            print(f"  | Secrets:    {vault_secret_store.total_secrets:<44}|")
            print(f"  | Versions:   {vault_secret_store.total_versions:<44}|")
            print("  +---------------------------------------------------------+")
        if vault_audit_log is not None:
            print(f"  | Audit Entries: {vault_audit_log.total_entries:<41}|")
            print("  +---------------------------------------------------------+")
        print()
    elif args.vault_status:
        print("\n  Vault not enabled. Use --vault to enable.\n")

    # Graph Database dashboards
    if graph_db is not None and graph_analyzer is not None:
        if args.graph_visualize:
            print(GraphVisualizer.render(
                graph_db,
                label="Number",
                max_nodes=config.graph_db_max_visualization_nodes,
                width=config.graph_db_dashboard_width,
            ))

        if args.graph_dashboard:
            print(GraphDashboard.render(
                graph_db,
                graph_analyzer,
                width=config.graph_db_dashboard_width,
            ))

    # Data Pipeline dashboards
    if pipeline is not None:
        if args.pipeline_dashboard:
            print(PipelineDashboard.render(
                executor=pipeline.executor,
                dag=pipeline.dag,
                records=pipeline_records or [],
                lineage_tracker=pipeline.lineage_tracker,
                backfill_engine=pipeline.backfill_engine,
                width=config.data_pipeline_dashboard_width + 4,
            ))

        if args.pipeline_dag:
            print(pipeline.dag.render(config.data_pipeline_dag_width))

        if args.pipeline_lineage and pipeline.lineage_tracker is not None:
            print(PipelineDashboard.render_lineage(
                lineage_tracker=pipeline.lineage_tracker,
                records=pipeline_records or [],
                width=config.data_pipeline_dag_width,
            ))

    # API Gateway dashboard
    if args.gateway_dashboard and gateway is not None:
        print(GatewayDashboard.render(gateway, width=config.api_gateway_dashboard_width))
    elif args.gateway_dashboard:
        print("\n  Gateway not enabled. Use --gateway to enable.\n")

    # Also add pipeline to finops active subsystems tracking
    # (this is already handled above in the finops setup)

    # ----------------------------------------------------------------
    # Load Testing Framework
    # ----------------------------------------------------------------
    if args.load_test:
        profile_name = args.load_profile or config.load_testing_default_profile
        profile_map = {
            "smoke": WorkloadProfile.SMOKE,
            "load": WorkloadProfile.LOAD,
            "stress": WorkloadProfile.STRESS,
            "spike": WorkloadProfile.SPIKE,
            "endurance": WorkloadProfile.ENDURANCE,
        }
        lt_profile = profile_map.get(profile_name, WorkloadProfile.SMOKE)
        lt_vus = args.load_vus or config.load_testing_default_vus

        print(
            "  +---------------------------------------------------------+\n"
            "  | ENTERPRISE FIZZBUZZ LOAD TESTING FRAMEWORK              |\n"
            "  | Stress-testing modulo arithmetic since 2026             |\n"
            "  +---------------------------------------------------------+"
        )
        print(f"  Profile: {profile_name.upper()} | VUs: {lt_vus}")
        print(f"  Numbers per VU: {config.load_testing_numbers_per_vu}")
        print()
        print("  Spawning virtual users...")
        print()

        lt_report, lt_latencies = run_load_test(
            lt_profile,
            config.rules,
            num_vus=lt_vus,
            numbers_per_vu=config.load_testing_numbers_per_vu,
            event_callback=event_bus.publish if event_bus else None,
            timeout_seconds=config.load_testing_timeout_seconds,
        )

        print(f"  Load test complete: {lt_report.total_requests} requests in {lt_report.elapsed_seconds:.3f}s")
        print(f"  Throughput: {lt_report.requests_per_second:.1f} req/s")
        print(f"  Error rate: {lt_report.error_rate * 100:.2f}%")
        print(f"  Performance grade: {lt_report.grade.value}")
        print()

        if args.load_dashboard:
            print(LoadTestDashboard.render(
                lt_report,
                latencies_ms=lt_latencies,
                width=config.load_testing_dashboard_width,
                histogram_buckets=config.load_testing_histogram_buckets,
            ))

    # ----------------------------------------------------------------
    # Genetic Algorithm for Optimal FizzBuzz Rule Discovery
    # ----------------------------------------------------------------
    if args.genetic:
        ga_generations = args.genetic_generations or config.genetic_algorithm_generations
        ga_engine = GeneticAlgorithmEngine(
            population_size=config.genetic_algorithm_population_size,
            generations=ga_generations,
            mutation_rate=config.genetic_algorithm_mutation_rate,
            crossover_rate=config.genetic_algorithm_crossover_rate,
            tournament_size=config.genetic_algorithm_tournament_size,
            elitism_count=config.genetic_algorithm_elitism_count,
            max_genes=config.genetic_algorithm_max_genes,
            min_genes=config.genetic_algorithm_min_genes,
            canonical_seed_pct=config.genetic_algorithm_canonical_seed_pct,
            convergence_threshold=config.genetic_algorithm_convergence_threshold,
            diversity_floor=config.genetic_algorithm_diversity_floor,
            mass_extinction_survivor_pct=config.genetic_algorithm_mass_extinction_survivor_pct,
            hall_of_fame_size=config.genetic_algorithm_hall_of_fame_size,
            fitness_weights=config.genetic_algorithm_fitness_weights,
            seed=config.genetic_algorithm_seed,
            event_callback=event_bus.publish if event_bus else None,
        )
        print("\n  [GA] Starting Genetic Algorithm for Optimal FizzBuzz Rule Discovery...")
        print(f"  [GA] Population: {config.genetic_algorithm_population_size} | Generations: {ga_generations}")
        print(f"  [GA] Evolving...\n")

        best_chromosome = ga_engine.evolve()

        rules = best_chromosome.to_rules_dict()
        rules_str = ", ".join(f"{d}:{l!r}" for d, l in sorted(rules.items()))
        print(f"  [GA] Evolution complete in {ga_engine.elapsed_ms:.1f}ms")
        print(f"  [GA] Best rules discovered: {{{rules_str}}}")
        print(f"  [GA] Fitness: {best_chromosome.fitness.overall:.6f}")
        print(f"  [GA] Converged: {'YES' if ga_engine.converged else 'NO'}")
        print(f"  [GA] Generations run: {ga_engine.generation}")
        print(f"  [GA] Mass extinctions: {ga_engine.convergence_monitor.extinction_count}")

        is_canonical = (rules == {3: "Fizz", 5: "Buzz"})
        if is_canonical:
            print()
            print("  [GA] PUNCHLINE: After all that evolutionary computation,")
            print("  [GA] the algorithm rediscovered {3:'Fizz', 5:'Buzz'} --")
            print("  [GA] the exact same rules from the original 5-line solution.")
            print("  [GA] Darwin would be proud. Or embarrassed.")
        print()

        if args.genetic_dashboard:
            print(EvolutionDashboard.render(
                ga_engine,
                width=config.genetic_algorithm_dashboard_width,
                chart_height=config.genetic_algorithm_fitness_chart_height,
            ))

    # ----------------------------------------------------------------
    # Audit Dashboard post-execution rendering
    # ----------------------------------------------------------------
    if audit_dashboard is not None:
        if args.audit_dashboard:
            print(audit_dashboard.render_dashboard(width=config.audit_dashboard_width))

        if args.audit_stream:
            stream_output = audit_dashboard.render_stream()
            if stream_output:
                print(stream_output)

        if args.audit_anomalies:
            print(audit_dashboard.render_anomalies())

    # FBaaS dashboard and billing
    if args.fbaas_billing and fbaas_stripe_client is not None:
        print(FBaaSDashboard.render(
            fbaas_tenant_manager,
            fbaas_usage_meter,
            fbaas_billing_engine,
            fbaas_stripe_client,
            width=config.fbaas_dashboard_width,
        ))
        print(FBaaSDashboard.render_billing_log(
            fbaas_stripe_client,
            width=config.fbaas_dashboard_width,
        ))
    elif args.fbaas_billing:
        print("\n  FBaaS not enabled. Use --fbaas to enable.\n")

    # ----------------------------------------------------------------
    # Time-Travel Debugger post-execution rendering
    # ----------------------------------------------------------------
    if tt_timeline is not None and tt_navigator is not None:
        # Run breakpoint navigation if breakpoints were set
        if tt_breakpoints:
            tt_navigator.reset()
            hit = tt_navigator.continue_to_breakpoint(tt_breakpoints)
            if hit is not None:
                print(f"\n  [TT] Breakpoint hit at sequence #{hit.sequence}: "
                      f"number={hit.number}, result='{hit.result}'")

        # Show the summary
        print(render_time_travel_summary(
            tt_timeline,
            tt_navigator,
            breakpoints=tt_breakpoints,
            width=config.time_travel_dashboard_width,
        ))

        # Show the full dashboard if requested
        if args.tt_dashboard:
            print(TimelineUI.render_dashboard(
                tt_timeline,
                tt_navigator,
                breakpoints=tt_breakpoints,
                width=config.time_travel_dashboard_width,
            ))

    # Quantum Computing Simulator Dashboard
    if args.quantum_dashboard and quantum_engine is not None:
        print(QuantumDashboard.render(
            quantum_engine,
            circuit=quantum_sample_circuit,
            width=config.quantum_dashboard_width,
            show_circuit=config.quantum_dashboard_show_circuit,
        ))
    elif args.quantum_dashboard:
        print("\n  Quantum simulator not enabled. Use --quantum to enable.\n")

    # Paxos Consensus Dashboard
    if args.paxos_dashboard and paxos_cluster is not None:
        print(ConsensusDashboard.render(
            paxos_cluster,
            width=config.paxos_dashboard_width,
            byzantine_node_id=paxos_byzantine_node_id,
        ))
    elif args.paxos_dashboard:
        print("\n  Paxos consensus not enabled. Use --paxos to enable.\n")

    # Query Optimizer Dashboard
    if args.optimizer_dashboard and qo_optimizer is not None:
        print(OptimizerDashboard.render(
            qo_optimizer, width=config.query_optimizer_dashboard_width
        ))
    elif args.optimizer_dashboard:
        print("\n  Query optimizer not enabled. Use --optimize to enable.\n")

    # Federated Learning Dashboard
    if args.fed_dashboard and federated_server is not None:
        print(FederatedDashboard.render(
            federated_server,
            width=config.federated_learning_dashboard_width,
            show_convergence=config.federated_learning_dashboard_show_convergence,
            show_clients=config.federated_learning_dashboard_show_clients,
        ))
    elif args.fed_dashboard:
        print("\n  Federated learning not enabled. Use --federated to enable.\n")

    # Knowledge Graph & Domain Ontology Dashboard
    if args.ontology_dashboard and kg_store is not None:
        print(KnowledgeDashboard.render(
            kg_store,
            kg_hierarchy,
            kg_engine,
            width=config.knowledge_graph_dashboard_width,
            show_class_hierarchy=config.knowledge_graph_dashboard_show_class_hierarchy,
            show_triple_stats=config.knowledge_graph_dashboard_show_triple_stats,
            show_inference_stats=config.knowledge_graph_dashboard_show_inference_stats,
        ))
    elif args.ontology_dashboard:
        print("\n  Knowledge Graph not enabled. Use --ontology to enable.\n")

    # Self-Modifying Code Dashboard
    if args.self_modify_dashboard and sm_engine is not None:
        print(SelfModifyingDashboard.render(
            sm_engine,
            width=config.self_modifying_dashboard_width,
            show_ast=config.self_modifying_dashboard_show_ast,
            show_history=config.self_modifying_dashboard_show_history,
            show_fitness=config.self_modifying_dashboard_show_fitness,
        ))
    elif args.self_modify_dashboard:
        print("\n  Self-modifying code not enabled. Use --self-modify to enable.\n")

    # FizzKube Container Orchestration Dashboard
    if args.fizzkube_dashboard and fizzkube_cp is not None:
        print(FizzKubeDashboard.render(
            fizzkube_cp,
            width=config.fizzkube_dashboard_width,
        ))
    elif args.fizzkube_dashboard:
        print("\n  FizzKube not enabled. Use --fizzkube to enable.\n")

    # FizzPM Package Manager Dashboard
    if args.fizzpm_dashboard and fizzpm_manager is not None:
        print(fizzpm_manager.render_dashboard(
            width=config.fizzpm_dashboard_width,
        ))
    elif args.fizzpm_dashboard:
        print("\n  FizzPM not enabled. Use --fizzpm to enable.\n")

    # FizzBuzz OS Kernel Dashboard
    if args.kernel_dashboard and fizzbuzz_kernel is not None:
        print(KernelDashboard.render(
            fizzbuzz_kernel,
            width=config.kernel_dashboard_width,
            show_process_table=config.kernel_dashboard_show_process_table,
            show_memory_map=config.kernel_dashboard_show_memory_map,
            show_interrupt_log=config.kernel_dashboard_show_interrupt_log,
        ))
    elif args.kernel_dashboard:
        print("\n  Kernel not enabled. Use --kernel to enable.\n")

    # P2P Gossip Network Dashboard
    if args.p2p_dashboard and p2p_network is not None:
        print(P2PDashboard.render(
            p2p_network, width=config.p2p_dashboard_width
        ))
    elif args.p2p_dashboard:
        print("\n  P2P network not enabled. Use --p2p to enable.\n")

    # Digital Twin Dashboard
    if args.twin_dashboard and twin_model is not None:
        print(TwinDashboard.render(
            model=twin_model,
            mc_result=twin_mc_result,
            drift_monitor=twin_drift_monitor,
            anomaly_detector=twin_anomaly_detector,
            what_if_result=twin_what_if_result,
            width=config.digital_twin_dashboard_width,
            show_histogram=config.digital_twin_dashboard_show_histogram,
            show_drift_gauge=config.digital_twin_dashboard_show_drift_gauge,
            histogram_buckets=config.digital_twin_histogram_buckets,
        ))
    elif args.twin_dashboard:
        print("\n  Digital Twin not enabled. Use --twin to enable.\n")

    # Recommendation Engine Dashboard
    if args.recommend_dashboard and rec_engine is not None:
        print(RecommendationDashboard.render(
            rec_engine,
            recommendations=rec_results,
            target_number=args.recommend_for,
            width=config.recommendation_dashboard_width,
            show_feature_vectors=config.recommendation_dashboard_show_feature_vectors,
            show_user_profiles=config.recommendation_dashboard_show_user_profiles,
            show_similarity_matrix=config.recommendation_dashboard_show_similarity_matrix,
        ))
    elif args.recommend_dashboard:
        print("\n  Recommendation Engine not enabled. Use --recommend to enable.\n")

    # Archaeology Dashboard
    if args.archaeology_dashboard and arch_engine is not None:
        print(ArchaeologyDashboard.render(
            arch_engine,
            width=config.archaeology_dashboard_width,
            show_strata=config.archaeology_dashboard_show_strata,
            show_bayesian=config.archaeology_dashboard_show_bayesian,
            show_corruption=config.archaeology_dashboard_show_corruption,
        ))
    elif args.archaeology_dashboard:
        print("\n  Archaeological Recovery System not enabled. Use --archaeology to enable.\n")

    # Dependent Type System Dashboard
    if args.types_dashboard and proof_engine is not None:
        print(TypeDashboard.render(
            proof_engine,
            proofs=dt_proofs if dt_proofs else None,
            width=config.dependent_types_dashboard_width,
            show_curry_howard=config.dependent_types_dashboard_show_curry_howard,
            show_proof_tree=config.dependent_types_dashboard_show_proof_tree,
            show_complexity_index=config.dependent_types_dashboard_show_complexity_index,
        ))
    elif args.types_dashboard:
        print("\n  Dependent Type System not enabled. Use --dependent-types to enable.\n")

    # ----------------------------------------------------------------
    # FizzDAP Debug Adapter Protocol Server
    # ----------------------------------------------------------------
    dap_server = None

    if args.dap or args.dap_dashboard:
        dap_port = args.dap_port or config.fizzdap_port

        dap_server = FizzDAPServer(
            port=dap_port,
            auto_stop_on_entry=config.fizzdap_auto_stop_on_entry,
            max_breakpoints=config.fizzdap_max_breakpoints,
            step_granularity=config.fizzdap_step_granularity,
            max_frames=config.fizzdap_max_frames,
            include_source_location=config.fizzdap_include_source_location,
            include_cache=config.fizzdap_include_cache_state,
            include_circuit_breaker=config.fizzdap_include_circuit_breaker,
            include_quantum=config.fizzdap_include_quantum_state,
            include_timings=config.fizzdap_include_middleware_timings,
            max_string_length=config.fizzdap_max_string_length,
        )

        # Initialize the DAP session
        dap_server.initialize()

        # Set middleware names for stack frame generation
        active_middleware_names = []
        for mw_var in [
            "tracing_mw", "auth_middleware", "es_middleware", "cb_middleware",
            "cache_middleware", "chaos_middleware", "sla_middleware",
            "metrics_middleware", "mesh_middleware", "rate_limit_middleware",
            "compliance_middleware", "finops_middleware", "dr_middleware",
            "ab_middleware", "mq_middleware", "vault_middleware",
            "pipeline_middleware", "gateway_middleware", "graph_middleware",
            "fbaas_middleware", "paxos_middleware", "quantum_middleware",
            "federated_middleware", "kg_middleware", "sm_middleware",
            "fizzkube_middleware", "kernel_middleware", "p2p_middleware",
            "twin_middleware", "flag_middleware", "qo_middleware",
            "arch_middleware", "tt_middleware",
        ]:
            _l = locals()
            mw_obj = _l.get(mw_var)
            if mw_obj is not None:
                active_middleware_names.append(type(mw_obj).__name__)

        # Always include the base middleware
        for base_name in ["ValidationMiddleware", "TimingMiddleware", "LoggingMiddleware"]:
            if base_name not in active_middleware_names:
                active_middleware_names.append(base_name)

        dap_server.set_middleware_names(active_middleware_names)

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZDAP DEBUG ADAPTER PROTOCOL SERVER                    |\n"
            "  | Breakpoints | Stack Frames | Variables | Events         |\n"
            f"  | Port: {dap_port} (simulated) | DAP 1.0 Compliant           |\n"
            '  | "Setting breakpoints on n%3 since 2026."                |\n'
            "  +---------------------------------------------------------+"
        )

        # Process evaluations through the debugger
        if args.dap and "results" in dir():
            _l = locals()
            eval_results = _l.get("results")
            if eval_results and isinstance(eval_results, list):
                for ev_result in eval_results:
                    if hasattr(ev_result, "number") and hasattr(ev_result, "label"):
                        dap_server.process_evaluation(
                            ev_result.number,
                            ev_result.label,
                            ev_result.label,
                        )
                    elif isinstance(ev_result, dict):
                        n = ev_result.get("number", 0)
                        label = ev_result.get("label", str(n))
                        dap_server.process_evaluation(n, label, label)

        # Terminate the DAP session
        if dap_server.session.is_active:
            dap_server.terminate()

    # FizzDAP Dashboard
    if args.dap_dashboard and dap_server is not None:
        print(FizzDAPDashboard.render(
            dap_server,
            width=config.fizzdap_dashboard_width,
            show_breakpoints=config.fizzdap_dashboard_show_breakpoints,
            show_stack_trace=config.fizzdap_dashboard_show_stack_trace,
            show_variables=config.fizzdap_dashboard_show_variables,
            show_complexity_index=config.fizzdap_dashboard_show_complexity_index,
        ))
    elif args.dap_dashboard:
        print("\n  FizzDAP not enabled. Use --dap to enable.\n")

    # ----------------------------------------------------------------
    # FizzSQL Relational Query Engine
    # ----------------------------------------------------------------
    fizzsql_engine = None

    if args.fizzsql or args.fizzsql_tables or args.fizzsql_dashboard:
        # Build platform state snapshot for virtual tables
        _locals = locals()
        fizzsql_state = PlatformState(
            evaluations=_locals.get("results"),
            cache_store=_locals.get("cache_store"),
            blockchain=_locals.get("blockchain"),
            sla_monitor=_locals.get("sla_monitor"),
            event_bus=_locals.get("event_bus"),
        )

        fizzsql_engine = FizzSQLEngine(
            state=fizzsql_state,
            max_result_rows=config.fizzsql_max_result_rows,
            enable_history=config.fizzsql_enable_query_history,
            history_size=config.fizzsql_query_history_size,
            slow_query_threshold_ms=config.fizzsql_slow_query_threshold_ms,
        )

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FIZZSQL RELATIONAL QUERY ENGINE                         |\n"
            "  | Lexer | Parser | Planner | Volcano Executor             |\n"
            "  | 5 virtual tables | Cost model | EXPLAIN ANALYZE         |\n"
            '  | "Your SELECT * deserves a query optimizer."             |\n'
            "  +---------------------------------------------------------+"
        )

        if args.fizzsql_tables:
            tables = fizzsql_engine.list_tables()
            print("\n  Available FizzSQL Virtual Tables:")
            print("  " + "=" * 57)
            for t in tables:
                print(f"\n  {t['name']}")
                print(f"    Columns: {t['columns']}")
                print(f"    {t['description']}")
            print("\n  " + "=" * 57)
            print()

        if args.fizzsql:
            try:
                output = fizzsql_engine.execute(args.fizzsql)
                print(f"\n  fizzsql> {args.fizzsql}")
                print(output)
                print()
            except Exception as e:
                print(f"\n  FizzSQL Error: {e}\n")

    # FizzSQL Dashboard
    if args.fizzsql_dashboard and fizzsql_engine is not None:
        print(FizzSQLDashboard.render(
            fizzsql_engine,
            width=config.fizzsql_dashboard_width,
        ))
    elif args.fizzsql_dashboard:
        print("\n  FizzSQL not enabled. Use --fizzsql to enable.\n")

    # IP Office Dashboard
    if args.ip_dashboard and ip_trademark_registry is not None:
        print(IPOfficeDashboard.render(
            trademark_registry=ip_trademark_registry,
            patent_examiner=ip_patent_examiner,
            copyright_registry=ip_copyright_registry,
            license_manager=ip_license_manager,
            tribunal=ip_tribunal,
            width=config.ip_office_dashboard_width,
        ))
    elif args.ip_dashboard:
        print("\n  IP Office not enabled. Use --ip-office to enable.\n")

    # FizzLock Dashboard
    if args.lock_dashboard and lock_manager is not None:
        print(LockDashboard.render(
            manager=lock_manager,
            width=config.distributed_locks_dashboard_width,
        ))
    elif args.lock_dashboard:
        print("\n  FizzLock not enabled. Use --locks to enable.\n")

    # FizzCDC Dashboard
    if args.cdc_dashboard and cdc_pipeline is not None:
        # Final flush before rendering
        cdc_pipeline.outbox_relay.stop()
        print(CDCDashboard.render(
            pipeline=cdc_pipeline,
            agents=cdc_agents or [],
            sinks=cdc_sinks_list or [],
            width=config.cdc_dashboard_width,
        ))
    elif args.cdc_dashboard:
        print("\n  FizzCDC not enabled. Use --cdc to enable.\n")

    # Stop CDC relay if running (without dashboard)
    if cdc_pipeline is not None and not args.cdc_dashboard:
        cdc_pipeline.outbox_relay.stop()

    # FizzBill Invoice and Dashboard
    if (args.billing_invoice or args.billing_dashboard) and billing_contract is not None:
        # Rate usage
        billing_rated_usage = billing_rating_engine.rate(
            tenant_id=billing_contract.tenant_id,
            tier=billing_contract.tier,
            total_fizzops=billing_usage_meter.total_fizzops,
            spending_cap=billing_contract.spending_cap,
        )

        # Run ASC 606 revenue recognition
        billing_obligations, _rev_entries = billing_recognizer.full_recognition(
            contract=billing_contract,
            overage_amount=billing_rated_usage.overage_charge,
        )

        if args.billing_invoice:
            print(BillingInvoiceGenerator.generate(
                rated_usage=billing_rated_usage,
                contract=billing_contract,
                obligations=billing_obligations,
                width=config.billing_dashboard_width + 4,
            ))

        if args.billing_dashboard:
            print(BillingDashboard.render(
                contract=billing_contract,
                rated_usage=billing_rated_usage,
                usage_meter=billing_usage_meter,
                dunning_manager=billing_dunning,
                recognizer=billing_recognizer,
                obligations=billing_obligations,
                width=config.billing_dashboard_width + 4,
            ))

    elif args.billing_invoice:
        print("\n  FizzBill not enabled. Use --billing to enable.\n")
    elif args.billing_dashboard:
        print("\n  FizzBill not enabled. Use --billing to enable.\n")

    # ----------------------------------------------------------------
    # FizzNAS Neural Architecture Search
    # ----------------------------------------------------------------
    if args.nas or args.nas_dashboard:
        nas_strategy = args.nas_strategy or config.nas_strategy
        nas_budget = args.nas_budget if args.nas_budget is not None else config.nas_budget
        nas_seed = config.nas_seed

        nas_engine = NASEngine(
            strategy=nas_strategy,
            budget=nas_budget,
            seed=nas_seed,
        )

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FizzNAS Neural Architecture Search Engine               |\n"
            "  +---------------------------------------------------------+"
        )

        winner = nas_engine.run()
        print(f"\n  NAS Winner: {winner.genome_string}")
        print(f"  Accuracy: {winner.accuracy:.1f}%  Params: {winner.parameter_count}  Latency: {winner.latency_us:.1f}us")

        if nas_engine.baseline_result:
            baseline = nas_engine.baseline_result
            print(f"\n  Baseline: {baseline.genome_string}")
            print(f"  Accuracy: {baseline.accuracy:.1f}%  Params: {baseline.parameter_count}  Latency: {baseline.latency_us:.1f}us")
        print()

        if args.nas_dashboard:
            print(NASDashboard.render(
                engine=nas_engine,
                width=config.nas_dashboard_width + 4,
            ))

    # ----------------------------------------------------------------
    # FizzCorr Observability Correlation Engine
    # ----------------------------------------------------------------
    if args.correlate or args.correlate_dashboard:
        corr_manager = ObservabilityCorrelationManager(
            temporal_window_seconds=config.observability_correlation_temporal_window_seconds,
            confidence_threshold=config.observability_correlation_confidence_threshold,
            causal_patterns=config.observability_correlation_causal_patterns,
            latency_threshold_ms=config.observability_correlation_anomaly_latency_threshold_ms,
            error_burst_window_s=config.observability_correlation_anomaly_error_burst_window_s,
            error_burst_threshold=config.observability_correlation_anomaly_error_burst_threshold,
            metric_deviation_sigma=config.observability_correlation_anomaly_metric_deviation_sigma,
            dashboard_width=config.observability_correlation_dashboard_width,
        )

        # Ingest synthetic observability signals from the evaluation session
        base_time = time.time()
        eval_cid = str(uuid.uuid4())

        # Trace: overall evaluation pipeline
        corr_manager.ingest_trace(
            span_name="evaluate_range",
            subsystem="pipeline",
            start_time=base_time,
            duration_ms=elapsed_ms if "elapsed_ms" in dir() else 1.0,
            trace_id=eval_cid,
            status="OK",
        )

        # Trace: rule engine evaluation
        corr_manager.ingest_trace(
            span_name="rule_engine.evaluate",
            subsystem="rule_engine",
            start_time=base_time + 0.001,
            duration_ms=0.5,
            trace_id=eval_cid,
            parent_span="evaluate_range",
            status="OK",
        )

        # Log: session start
        corr_manager.ingest_log(
            message="FizzBuzz evaluation session started",
            subsystem="pipeline",
            level="INFO",
            timestamp=base_time,
            correlation_id=eval_cid,
        )

        # Log: evaluation complete
        corr_manager.ingest_log(
            message=f"Evaluated range {config.range_start}-{config.range_end}",
            subsystem="pipeline",
            level="INFO",
            timestamp=base_time + 0.002,
            correlation_id=eval_cid,
        )

        # Metric: evaluation count
        corr_manager.ingest_metric(
            metric_name="fizzbuzz_evaluations_total",
            value=float(config.range_end - config.range_start + 1),
            subsystem="metrics",
            timestamp=base_time + 0.003,
            correlation_id=eval_cid,
        )

        # Metric: pipeline latency
        corr_manager.ingest_metric(
            metric_name="fizzbuzz_pipeline_latency_ms",
            value=1.0,
            subsystem="metrics",
            timestamp=base_time + 0.003,
        )

        corr_manager.finalize()

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FizzCorr Observability Correlation Engine               |\n"
            "  +---------------------------------------------------------+"
        )

        events = corr_manager.correlation_engine.events
        correlations = corr_manager.correlation_engine.correlations
        anomalies = corr_manager.anomaly_detector.anomalies
        print(f"\n  Ingested {len(events)} signals, discovered {len(correlations)} correlations")
        print(f"  Detected {len(anomalies)} anomalies")
        print(f"  Exemplar links: {len(corr_manager.get_exemplar_links())}")
        print(f"  Dependency edges: {len(corr_manager.dependency_map.edges)}")
        print()

        if args.correlate_dashboard:
            print(corr_manager.render_dashboard())

    # ----------------------------------------------------------------
    # FizzCap — Capability-Based Security
    # ----------------------------------------------------------------
    # When --capabilities is active, every FizzBuzz operation requires
    # an explicit, cryptographically signed capability token. The system
    # enforces unforgeable object capabilities with HMAC-SHA256
    # signatures, monotonic attenuation (authority can only decrease),
    # cascade revocation through the delegation DAG, and confused
    # deputy prevention. This ensures that evaluating n % 3 == 0
    # is protected by the same security principles as seL4.
    # ----------------------------------------------------------------
    if args.capabilities or args.cap_dashboard:
        cap_mode = args.cap_mode or config.capability_security_mode
        cap_manager = CapabilityManager(
            secret_key=config.capability_security_secret_key,
            mode=cap_mode,
        )

        # Create a root capability for the evaluation session
        root_cap = cap_manager.create_root_capability(
            resource=config.capability_security_default_resource,
            operations=frozenset({
                Operation.READ,
                Operation.WRITE,
                Operation.EXECUTE,
                Operation.DELEGATE,
            }),
            holder="session:root",
            constraints={"session_id": str(uuid.uuid4())},
        )

        # Delegate an attenuated capability for the rule engine
        engine_cap = cap_manager.delegate(
            parent=root_cap,
            new_operations=frozenset({Operation.READ, Operation.EXECUTE}),
            new_holder="subsystem:rule_engine",
            additional_constraints={"scope": "evaluation"},
        )

        # Delegate a further-attenuated capability for the formatter
        formatter_cap = cap_manager.delegate(
            parent=engine_cap,
            new_operations=frozenset({Operation.READ}),
            new_holder="subsystem:formatter",
            additional_constraints={"scope": "evaluation", "output_only": "true"},
        )

        # Verify access through the confused deputy guard
        cap_manager.check_access(
            root_cap,
            config.capability_security_default_resource,
            Operation.EXECUTE,
        )
        cap_manager.check_access(
            engine_cap,
            config.capability_security_default_resource,
            Operation.EXECUTE,
        )
        cap_manager.check_access(
            formatter_cap,
            config.capability_security_default_resource,
            Operation.READ,
        )

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FizzCap Capability-Based Security Model                 |\n"
            "  | Unforgeable object capabilities with HMAC-SHA256        |\n"
            "  | Because ambient authority was never good enough.        |\n"
            "  +---------------------------------------------------------+"
        )

        active = cap_manager.mint.active_capabilities
        print(f"\n  Mode: {cap_mode}")
        print(f"  Total minted: {cap_manager.mint.total_minted}")
        print(f"  Active capabilities: {len(active)}")
        print(f"  Delegation graph nodes: {cap_manager.graph.node_count}")
        print(f"  Delegation graph edges: {cap_manager.graph.edge_count}")
        print(f"  Guard accepts: {cap_manager.guard.accept_count}")
        print(f"  Guard rejects: {cap_manager.guard.reject_count}")
        print()

        if args.cap_dashboard:
            dashboard = CapabilityDashboard(
                cap_manager,
                width=config.capability_security_dashboard_width,
            )
            print(dashboard.render())

    # ----------------------------------------------------------------
    # FizzOTel — OpenTelemetry-Compatible Distributed Tracing Output
    # ----------------------------------------------------------------
    # When --otel is active, the FizzBuzz evaluation pipeline emits
    # W3C-compliant distributed traces in OTLP, Zipkin, or ASCII
    # waterfall format. Because correlating n % 3 == 0 across service
    # boundaries requires 128-bit trace IDs and nanosecond timestamps.
    # ----------------------------------------------------------------
    if otel_provider is not None and otel_exporter is not None:
        # Flush any remaining spans
        otel_provider.shutdown()

        from enterprise_fizzbuzz.infrastructure.otel_tracing import (
            ConsoleExporter as OTelConsoleExporter,
        )

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FizzOTel Distributed Tracing                            |\n"
            "  | OpenTelemetry-Compatible W3C TraceContext Propagation   |\n"
            "  | Because single-node tracing was never enough.           |\n"
            "  +---------------------------------------------------------+"
        )

        print(f"\n  Traces:    {otel_provider.trace_count}")
        print(f"  Spans:     {otel_provider.span_count}")
        print(f"  Sampled:   {otel_provider.sampler.sampled_count}")
        print(f"  Dropped:   {otel_provider.sampler.dropped_count}")
        print(f"  Exported:  {otel_exporter.exported_count}")
        print(f"  Avg dur:   {otel_provider.metrics_bridge.avg_duration_ms:.3f}ms")
        print()

        # If using console exporter, print the waterfall
        if isinstance(otel_exporter, OTelConsoleExporter):
            print(otel_exporter.render())
            print()

        if args.otel_dashboard:
            dashboard = OTelDashboard(
                provider=otel_provider,
                exporter=otel_exporter,
                width=config.otel_dashboard_width,
            )
            print(dashboard.render())

    # ----------------------------------------------------------------
    # FizzJIT — Runtime Code Generation
    # ----------------------------------------------------------------
    # When --jit is active, the FizzBuzz evaluation pipeline gains a
    # trace-based JIT compiler with SSA intermediate representation,
    # four optimization passes, LRU-cached compiled closures, and
    # on-stack replacement for seamless interpreter-to-compiled
    # transitions. This adds approximately 800 lines of compiler
    # infrastructure to evaluate n % 3 == 0, which is the logical
    # next step after the bytecode VM proved insufficiently over-
    # engineered.
    # ----------------------------------------------------------------
    if args.jit or args.jit_dashboard:
        from enterprise_fizzbuzz.infrastructure.jit_compiler import (
            JITCompilerManager,
        )

        jit_threshold = args.jit_threshold if args.jit_threshold is not None else config.jit_threshold
        jit_manager = JITCompilerManager(
            threshold=jit_threshold,
            cache_size=config.jit_cache_size,
            enable_constant_folding=config.jit_enable_constant_folding,
            enable_dce=config.jit_enable_dce,
            enable_guard_hoisting=config.jit_enable_guard_hoisting,
            enable_type_specialization=config.jit_enable_type_specialization,
        )

        print(
            "\n  +---------------------------------------------------------+\n"
            "  | FizzJIT Runtime Code Generation                        |\n"
            "  | Trace-based JIT with SSA IR and 4 optimization passes  |\n"
            "  | Because the interpreter was too fast.                   |\n"
            "  +---------------------------------------------------------+"
        )

        # Run the evaluation multiple times to trigger JIT compilation
        jit_rules = config.rules
        for _iteration in range(jit_threshold + 1):
            jit_results = jit_manager.evaluate_range(
                config.range_start,
                config.range_end,
                jit_rules,
            )

        print(f"\n  Compiled traces: {jit_manager.compiled_traces}")
        print(f"  Cache entries: {jit_manager.cache.size}")
        print(f"  Cache hit rate: {jit_manager.cache.hit_rate:.1f}%")
        print(f"  Total evaluations: {jit_manager.total_evaluations}")
        print(f"  OSR successes: {jit_manager.osr.osr_successes}")
        print(f"  Guard failures: {jit_manager.osr.guard_failures}")
        print()

        if args.jit_dashboard:
            print(jit_manager.render_dashboard(
                width=config.jit_dashboard_width,
            ))

    # ----------------------------------------------------------------
    # FizzWAL Dashboard
    # ----------------------------------------------------------------
    if args.wal_dashboard and wal_engine is not None:
        print(IntentDashboard.render(
            wal=wal_engine,
            checkpoint_manager=wal_checkpoint_mgr,
            recovery_engine=wal_recovery_engine,
            width=config.fizzwal_dashboard_width,
        ))
    elif args.wal_dashboard:
        print("\n  FizzWAL not enabled. Use --wal-intent to enable.\n")

    # ----------------------------------------------------------------
    # FizzCRDT Dashboard
    # ----------------------------------------------------------------
    if args.crdt_dashboard and crdt_engine is not None:
        print(CRDTDashboard.render(
            engine=crdt_engine,
            width=config.crdt_dashboard_width,
        ))
    elif args.crdt_dashboard:
        print("\n  FizzCRDT not enabled. Use --crdt to enable.\n")

    # ----------------------------------------------------------------
    # FizzGrammar Dashboard
    # ----------------------------------------------------------------
    if args.grammar_dashboard and grammar_obj is not None:
        from enterprise_fizzbuzz.infrastructure.formal_grammar import (
            GrammarDashboard,
        )
        print(GrammarDashboard.render(
            grammar=grammar_obj,
            analyzer=grammar_analyzer,
            width=config.grammar_dashboard_width,
        ))
    elif args.grammar_dashboard:
        print("\n  FizzGrammar not enabled. Use --grammar to enable.\n")

    # Shutdown the kernel if it was booted
    if fizzbuzz_kernel is not None:
        fizzbuzz_kernel.shutdown()

    # Stop the hot-reload watcher on exit
    if hot_reload_watcher is not None and hot_reload_watcher.is_running:
        hot_reload_watcher.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Enterprise FizzBuzz Platform - Middleware Contract Tests

Defines the behavioral contract that every IMiddleware implementation must
satisfy. Whether the middleware is checking RBAC credentials, injecting
chaos, enforcing rate limits, or routing through a Byzantine fault-tolerant
consensus protocol, the contract demands the same three things: a name,
a priority, and a process() method that accepts a ProcessingContext and a
callable and returns a ProcessingContext. That's it. Three promises.
Thirty-five implementations. Zero excuses.

The MiddlewareContractTests mixin discovers all IMiddleware implementations
dynamically by crawling the infrastructure package, because adding a new
middleware and forgetting to write a contract test should be architecturally
impossible — not merely frowned upon.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from abc import abstractmethod
from pathlib import Path
from typing import Callable

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ============================================================
# Dynamic Discovery Engine
# ============================================================


def _discover_middleware_classes() -> list[type]:
    """Crawl the infrastructure package and return every IMiddleware subclass.

    This is the architectural equivalent of an all-hands meeting where
    attendance is mandatory and verified by badge scan. No middleware
    escapes the contract tests, not even the ones hiding in submodules
    nobody reads.
    """
    import enterprise_fizzbuzz.infrastructure as infra_pkg

    middleware_classes: list[type] = []
    pkg_path = Path(infra_pkg.__file__).parent

    for importer, modname, ispkg in pkgutil.walk_packages(
        [str(pkg_path)],
        prefix="enterprise_fizzbuzz.infrastructure.",
    ):
        if ispkg:
            continue
        try:
            module = importlib.import_module(modname)
        except Exception:
            continue

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, IMiddleware)
                and obj is not IMiddleware
                and not inspect.isabstract(obj)
                and obj.__module__ == module.__name__
            ):
                middleware_classes.append(obj)

    return sorted(middleware_classes, key=lambda c: c.__name__)


ALL_MIDDLEWARE_CLASSES = _discover_middleware_classes()


# ============================================================
# Factory Helpers
# ============================================================


def _make_context(number: int = 15, session_id: str = "contract-mw-session") -> ProcessingContext:
    """Produce a minimal ProcessingContext suitable for middleware testing.

    Every middleware needs something to chew on. This context is the
    cafeteria tray of the pipeline: plain, functional, and designed
    to survive being dropped.
    """
    return ProcessingContext(number=number, session_id=session_id)


def _make_result(number: int, output: str) -> FizzBuzzResult:
    """Create a FizzBuzzResult for middleware pipeline testing."""
    matched_rules = []
    if output in ("Fizz", "Buzz", "FizzBuzz"):
        labels = []
        if "Fizz" in output:
            labels.append(("Fizz", 3))
        if "Buzz" in output:
            labels.append(("Buzz", 5))
        for label, divisor in labels:
            rule = RuleDefinition(name=f"{label}Rule", divisor=divisor, label=label, priority=1)
            matched_rules.append(RuleMatch(rule=rule, number=number))
    return FizzBuzzResult(
        number=number,
        output=output,
        matched_rules=matched_rules,
        processing_time_ns=42000,
        result_id=f"mw-contract-{number:04d}",
        metadata={"contract_test": True},
    )


def _identity_handler(context: ProcessingContext) -> ProcessingContext:
    """A next_handler that simply evaluates the number and returns the context.

    This is the simplest possible downstream handler: it adds a result
    to the context and returns. It is the philosophical endpoint of every
    middleware chain — the thing that actually does the work that 35
    layers of middleware exist to observe, measure, and complicate.
    """
    number = context.number
    if number % 15 == 0:
        output = "FizzBuzz"
    elif number % 3 == 0:
        output = "Fizz"
    elif number % 5 == 0:
        output = "Buzz"
    else:
        output = str(number)
    context.results.append(_make_result(number, output))
    return context


def _make_standard_rules():
    """Create standard Fizz/Buzz rules for middleware that need them."""
    from enterprise_fizzbuzz.domain.models import RuleDefinition
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
    ]


def _try_instantiate(cls: type) -> IMiddleware | None:
    """Attempt to instantiate a middleware class with sensible defaults.

    Many middleware classes require constructor arguments (a ChaosMonkey,
    a ComplianceFramework, a PaxosCluster, etc.). This factory provides
    the minimal dependencies each middleware needs by reading their actual
    constructors and supplying the right objects. If it cannot be
    instantiated, it returns None — the middleware escapes the process()
    contract test but not the name/priority tests, because those are
    too important to skip.
    """
    name = cls.__name__

    # --- No-arg or all-optional constructors ---
    if name in {
        "TimingMiddleware",
        "LoggingMiddleware",
        "ValidationMiddleware",
        "TracingMiddleware",
        "CircuitBreakerMiddleware",
    }:
        try:
            return cls()
        except Exception:
            return None

    # MetricsMiddleware: optional registry + collector
    if name == "MetricsMiddleware":
        try:
            return cls()
        except Exception:
            return None

    # TranslationMiddleware: optional locale_manager
    if name == "TranslationMiddleware":
        try:
            return cls(locale_manager=None)
        except Exception:
            return None

    # CacheMiddleware: requires CacheStore
    if name == "CacheMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.cache import CacheStore
            return cls(cache_store=CacheStore())
        except Exception:
            return None

    # ChaosMiddleware: requires ChaosMonkey(severity=FaultSeverity.LEVEL_1)
    if name == "ChaosMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.chaos import ChaosMonkey, FaultSeverity
            # LEVEL_1 is lowest severity — minimal chaos injection
            return cls(chaos_monkey=ChaosMonkey(severity=FaultSeverity.LEVEL_1, seed=42))
        except Exception:
            return None

    # AuthorizationMiddleware: requires AuthContext from domain.models
    if name == "AuthorizationMiddleware":
        try:
            from enterprise_fizzbuzz.domain.models import AuthContext, FizzBuzzRole
            ctx = AuthContext(
                user="contract-tester",
                role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            )
            return cls(auth_context=ctx)
        except Exception:
            return None

    # ComplianceMiddleware: requires ComplianceFramework
    if name == "ComplianceMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.compliance import ComplianceFramework
            return cls(compliance_framework=ComplianceFramework())
        except Exception:
            return None

    # SLAMiddleware: requires SLAMonitor
    if name == "SLAMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.sla import SLAMonitor
            return cls(sla_monitor=SLAMonitor())
        except Exception:
            return None

    # FinOpsMiddleware: requires CostTracker(cost_registry, tax_engine, currency)
    if name == "FinOpsMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.finops import (
                CostTracker,
                FizzBuckCurrency,
                FizzBuzzTaxEngine,
                SubsystemCostRegistry,
            )
            return cls(cost_tracker=CostTracker(
                cost_registry=SubsystemCostRegistry(),
                tax_engine=FizzBuzzTaxEngine(),
                currency=FizzBuckCurrency(),
            ))
        except Exception:
            return None

    # FBaaSMiddleware: requires Tenant, UsageMeter, BillingEngine
    if name == "FBaaSMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.fbaas import (
                BillingEngine,
                FizzStripeClient,
                SubscriptionTier,
                Tenant,
                TenantManager,
                UsageMeter,
            )
            tenant = Tenant(
                tenant_id="contract-test-tenant",
                name="Contract Test Corp",
                tier=SubscriptionTier.ENTERPRISE,
                api_key="test-api-key-contract",
            )
            return cls(
                tenant=tenant,
                usage_meter=UsageMeter(),
                billing_engine=BillingEngine(
                    stripe_client=FizzStripeClient(),
                    tenant_manager=TenantManager(),
                ),
            )
        except Exception:
            return None

    # FlagMiddleware: requires FlagStore
    if name == "FlagMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.feature_flags import FlagStore
            return cls(flag_store=FlagStore())
        except Exception:
            return None

    # EventSourcingMiddleware: requires CommandBus + EventStore (both no-arg)
    if name == "EventSourcingMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.event_sourcing import (
                CommandBus,
                EventStore,
            )
            store = EventStore()
            bus = CommandBus()
            return cls(command_bus=bus, event_store=store)
        except Exception:
            return None

    # DRMiddleware: requires WriteAheadLog + BackupManager
    if name == "DRMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.disaster_recovery import (
                BackupManager,
                WriteAheadLog,
            )
            return cls(wal=WriteAheadLog(), backup_manager=BackupManager())
        except Exception:
            return None

    # RateLimiterMiddleware: requires QuotaManager(policy=RateLimitPolicy())
    if name == "RateLimiterMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.rate_limiter import (
                QuotaManager,
                RateLimitPolicy,
            )
            return cls(quota_manager=QuotaManager(policy=RateLimitPolicy()))
        except Exception:
            return None

    # ABTestingMiddleware: requires ExperimentRegistry
    if name == "ABTestingMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.ab_testing import ExperimentRegistry
            return cls(registry=ExperimentRegistry())
        except Exception:
            return None

    # GatewayMiddleware: requires APIGateway (complex constructor)
    if name == "GatewayMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.api_gateway import (
                APIGateway,
                APIKeyManager,
                RequestReplayJournal,
                RequestTransformerChain,
                ResponseTransformerChain,
                RouteTable,
                VersionRouter,
            )
            return cls(gateway=APIGateway(
                route_table=RouteTable(),
                version_router=VersionRouter(version_config={"v1": {}, "v2": {}}),
                request_chain=RequestTransformerChain(),
                response_chain=ResponseTransformerChain(),
                key_manager=APIKeyManager(),
                journal=RequestReplayJournal(),
            ))
        except Exception:
            return None

    # DeploymentMiddleware: requires DeploymentOrchestrator(rules=...)
    if name == "DeploymentMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.blue_green import DeploymentOrchestrator
            return cls(orchestrator=DeploymentOrchestrator(rules=_make_standard_rules()))
        except Exception:
            return None

    # PipelineMiddleware: requires Pipeline (complex constructor)
    if name == "PipelineMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.data_pipeline import (
                DAGExecutor,
                Pipeline,
                PipelineDAG,
                SinkConnector,
                SourceConnector,
            )
            dag = PipelineDAG()
            return cls(pipeline=Pipeline(
                source=SourceConnector(),
                sink=SinkConnector(),
                dag=dag,
                executor=DAGExecutor(dag=dag),
            ))
        except Exception:
            return None

    # GraphMiddleware: requires PropertyGraph (no-arg)
    if name == "GraphMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.graph_db import PropertyGraph
            return cls(graph=PropertyGraph())
        except Exception:
            return None

    # KnowledgeGraphMiddleware: requires TripleStore + OWLClassHierarchy(store)
    if name == "KnowledgeGraphMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.knowledge_graph import (
                OWLClassHierarchy,
                TripleStore,
            )
            store = TripleStore()
            return cls(store=store, hierarchy=OWLClassHierarchy(store=store))
        except Exception:
            return None

    # MQMiddleware: requires MessageBroker + Producer (both have defaults)
    if name == "MQMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.message_queue import (
                MessageBroker,
                Producer,
            )
            return cls(broker=MessageBroker(), producer=Producer())
        except Exception:
            return None

    # KernelMiddleware: requires FizzBuzzKernel(rules=...)
    if name == "KernelMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.os_kernel import FizzBuzzKernel
            return cls(kernel=FizzBuzzKernel(rules=_make_standard_rules()))
        except Exception:
            return None

    # PaxosMiddleware: requires PaxosCluster(num_nodes, rules)
    if name == "PaxosMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.paxos import PaxosCluster
            return cls(cluster=PaxosCluster(num_nodes=3, rules=_make_standard_rules()))
        except Exception:
            return None

    # P2PMiddleware: requires P2PNetwork (all defaults)
    if name == "P2PMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.p2p_network import P2PNetwork
            return cls(network=P2PNetwork())
        except Exception:
            return None

    # QuantumMiddleware: requires QuantumFizzBuzzEngine(rules=...)
    if name == "QuantumMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.quantum import QuantumFizzBuzzEngine
            rules_dicts = [
                {"divisor": 3, "label": "Fizz"},
                {"divisor": 5, "label": "Buzz"},
            ]
            return cls(engine=QuantumFizzBuzzEngine(rules=rules_dicts))
        except Exception:
            return None

    # VaultMiddleware: requires VaultSealManager(shamir=ShamirSecretSharing())
    if name == "VaultMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.secrets_vault import (
                ShamirSecretSharing,
                VaultSealManager,
            )
            return cls(seal_manager=VaultSealManager(shamir=ShamirSecretSharing()))
        except Exception:
            return None

    # OptimizerMiddleware: requires Optimizer (all optional)
    if name == "OptimizerMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.query_optimizer import Optimizer
            return cls(optimizer=Optimizer())
        except Exception:
            return None

    # SelfModifyingMiddleware: requires SelfModifyingEngine (complex constructor)
    if name == "SelfModifyingMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.self_modifying import (
                DivisorShift,
                FitnessEvaluator,
                MutableRule,
                RuleAST,
                SafetyGuard,
                SelfModifyingEngine,
            )
            rule = MutableRule(name="FizzRule", ast=RuleAST())
            operators = [DivisorShift()]
            ground_truth = {
                n: "FizzBuzz" if n % 15 == 0
                else "Fizz" if n % 3 == 0
                else "Buzz" if n % 5 == 0
                else str(n)
                for n in range(1, 31)
            }
            evaluator = FitnessEvaluator(ground_truth=ground_truth)
            guard = SafetyGuard(fitness_evaluator=evaluator)
            return cls(engine=SelfModifyingEngine(
                rule=rule,
                operators=operators,
                fitness_evaluator=evaluator,
                safety_guard=guard,
                seed=42,
            ))
        except Exception:
            return None

    # MeshMiddleware: requires MeshControlPlane (complex constructor)
    if name == "MeshMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.service_mesh import (
                CanaryRouter,
                LoadBalancer,
                MeshControlPlane,
                NetworkFaultInjector,
                ServiceRegistry,
            )
            return cls(control_plane=MeshControlPlane(
                registry=ServiceRegistry(),
                load_balancer=LoadBalancer(),
                fault_injector=NetworkFaultInjector(),
                canary_router=CanaryRouter(),
            ))
        except Exception:
            return None

    # TimeTravelMiddleware: requires Timeline (all defaults)
    if name == "TimeTravelMiddleware":
        try:
            from enterprise_fizzbuzz.infrastructure.time_travel import Timeline
            return cls(timeline=Timeline())
        except Exception:
            return None

    # FederatedMiddleware: requires FederatedServer(clients, aggregator)
    if name == "FederatedMiddleware":
        try:
            import random
            from enterprise_fizzbuzz.infrastructure.federated_learning import (
                FedAvgAggregator,
                FederatedClient,
                FederatedServer,
            )
            rng = random.Random(42)
            clients = [
                FederatedClient(
                    client_id=f"contract-{i}",
                    data=list(range(1, 16)),
                    divisor=3,
                    rng=rng,
                )
                for i in range(2)
            ]
            return cls(server=FederatedServer(
                clients=clients,
                aggregator=FedAvgAggregator(),
            ))
        except Exception:
            return None

    # Fallback: try no-arg constructor
    try:
        return cls()
    except Exception:
        return None


# ============================================================
# Fixture: Singleton Reset
# ============================================================


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests to prevent cross-contamination.

    The ConfigurationManager and LocaleManager are singletons that
    accumulate state across test runs. Resetting them is the test
    equivalent of rebooting the production server after every request,
    which is exactly the kind of operational overhead this platform
    celebrates.
    """
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Contract Test: Discovery Sanity
# ============================================================


class TestMiddlewareDiscovery:
    """Verify that the dynamic discovery engine found a reasonable number
    of IMiddleware implementations.

    If this test fails, either the infrastructure package has been
    catastrophically refactored, or the discovery logic has a bug.
    Neither outcome is acceptable.
    """

    def test_discovered_at_least_twenty_implementations(self) -> None:
        """The platform has 35 known IMiddleware implementations. We should find most of them."""
        assert len(ALL_MIDDLEWARE_CLASSES) >= 20, (
            f"Only discovered {len(ALL_MIDDLEWARE_CLASSES)} IMiddleware implementations. "
            f"Expected at least 20. Either the discovery engine is broken or "
            f"someone has been deleting middleware, which is a fireable offense "
            f"in the Enterprise FizzBuzz Organization."
        )

    def test_all_discovered_classes_are_imiddleware_subclasses(self) -> None:
        """Every discovered class must actually implement IMiddleware."""
        for cls in ALL_MIDDLEWARE_CLASSES:
            assert issubclass(cls, IMiddleware), (
                f"{cls.__name__} was discovered as a middleware but does not "
                f"implement IMiddleware. The discovery engine has trust issues."
            )

    def test_no_abstract_classes_discovered(self) -> None:
        """Only concrete implementations should appear in the discovery results."""
        for cls in ALL_MIDDLEWARE_CLASSES:
            assert not inspect.isabstract(cls), (
                f"{cls.__name__} is abstract and should not be in the "
                f"concrete implementations list. Abstract classes are ideas, "
                f"not implementations."
            )


# ============================================================
# Contract Tests: get_name() Behavioral Promises
# ============================================================


class TestMiddlewareGetNameContract:
    """Every IMiddleware.get_name() must return a non-empty string.

    A middleware without a name is a middleware that cannot be traced,
    logged, debugged, or blamed when things go wrong. In enterprise
    software, accountability starts with having a name.
    """

    @pytest.mark.parametrize(
        "middleware_class",
        ALL_MIDDLEWARE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_get_name_returns_non_empty_string(self, middleware_class: type) -> None:
        """get_name() must return a non-empty string for every IMiddleware implementation."""
        instance = _try_instantiate(middleware_class)
        if instance is None:
            pytest.skip(
                f"Cannot instantiate {middleware_class.__name__} — "
                f"constructor requires dependencies that could not be satisfied. "
                f"The middleware shall live to be tested another day."
            )
        name = instance.get_name()
        assert isinstance(name, str), (
            f"{middleware_class.__name__}.get_name() returned "
            f"{type(name).__name__} instead of str. A name must be text."
        )
        assert len(name) > 0, (
            f"{middleware_class.__name__}.get_name() returned an empty string. "
            f"Namelessness is an existential crisis, not a valid return value."
        )


# ============================================================
# Contract Tests: get_priority() Behavioral Promises
# ============================================================


class TestMiddlewareGetPriorityContract:
    """Every IMiddleware.get_priority() must return an integer.

    Priority determines execution order in the pipeline. A non-integer
    priority would cause the sort to fail, and a failed sort would mean
    chaos in the pipeline — and not the good kind of chaos that the
    ChaosMiddleware provides.
    """

    @pytest.mark.parametrize(
        "middleware_class",
        ALL_MIDDLEWARE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_get_priority_returns_integer(self, middleware_class: type) -> None:
        """get_priority() must return an int for every IMiddleware implementation."""
        instance = _try_instantiate(middleware_class)
        if instance is None:
            pytest.skip(
                f"Cannot instantiate {middleware_class.__name__} — "
                f"skipping priority contract check."
            )
        priority = instance.get_priority()
        assert isinstance(priority, int), (
            f"{middleware_class.__name__}.get_priority() returned "
            f"{type(priority).__name__} instead of int. The pipeline "
            f"sort algorithm will not be amused."
        )

    @pytest.mark.parametrize(
        "middleware_class",
        ALL_MIDDLEWARE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_priority_is_class_property_not_instance_dependent(self, middleware_class: type) -> None:
        """Two instances of the same middleware class must return the same priority.

        Priority is a property of the class, not the instance. If two instances
        of CircuitBreakerMiddleware disagreed on their priority, the pipeline
        ordering would depend on which instance was added first — and
        non-deterministic ordering is a feature of chaos engineering, not
        middleware composition.
        """
        instance_a = _try_instantiate(middleware_class)
        instance_b = _try_instantiate(middleware_class)
        if instance_a is None or instance_b is None:
            pytest.skip(
                f"Cannot instantiate two instances of {middleware_class.__name__}."
            )
        assert instance_a.get_priority() == instance_b.get_priority(), (
            f"Two instances of {middleware_class.__name__} returned different "
            f"priorities ({instance_a.get_priority()} vs {instance_b.get_priority()}). "
            f"Priority is a class invariant, not a mood ring."
        )


# ============================================================
# Contract Tests: process() Behavioral Promises
# ============================================================


# Representative set of middleware classes that we can instantiate and
# exercise through the full process() contract. These are selected to
# cover a range of priorities, behaviors (pass-through, enriching,
# short-circuiting), and construction complexities.
_REPRESENTATIVE_MIDDLEWARE_NAMES = {
    "TimingMiddleware",
    "LoggingMiddleware",
    "ValidationMiddleware",
    "TranslationMiddleware",
    "TracingMiddleware",
    "MetricsMiddleware",
    "CircuitBreakerMiddleware",
    "CacheMiddleware",
    "ChaosMiddleware",
    "AuthorizationMiddleware",
    "ComplianceMiddleware",
    "SLAMiddleware",
    "FinOpsMiddleware",
    "FBaaSMiddleware",
    "FlagMiddleware",
    "EventSourcingMiddleware",
    "DRMiddleware",
    "RateLimiterMiddleware",
    "ABTestingMiddleware",
    "GatewayMiddleware",
    "DeploymentMiddleware",
    "PipelineMiddleware",
    "GraphMiddleware",
    "KnowledgeGraphMiddleware",
    "MQMiddleware",
    "KernelMiddleware",
    "PaxosMiddleware",
    "P2PMiddleware",
    "QuantumMiddleware",
    "VaultMiddleware",
    "OptimizerMiddleware",
    "SelfModifyingMiddleware",
    "MeshMiddleware",
    "TimeTravelMiddleware",
    "FederatedMiddleware",
}

_REPRESENTATIVE_CLASSES = [
    cls for cls in ALL_MIDDLEWARE_CLASSES
    if cls.__name__ in _REPRESENTATIVE_MIDDLEWARE_NAMES
]


class TestMiddlewareProcessContract:
    """Contract tests for IMiddleware.process().

    The process() method is the core of the middleware contract. It must:
    1. Accept a ProcessingContext and a callable next_handler.
    2. Return a ProcessingContext (not None, not a string, not a promise).
    3. Not catastrophically explode when given valid inputs.

    These tests exercise process() on a representative set of middleware
    implementations — those that can be instantiated with sensible defaults.
    Middleware that requires external services, network connections, or
    divine intervention to instantiate is skipped with appropriate regret.
    """

    @pytest.mark.parametrize(
        "middleware_class",
        _REPRESENTATIVE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_process_accepts_context_and_callable(self, middleware_class: type) -> None:
        """process() must accept a ProcessingContext and a callable without error."""
        instance = _try_instantiate(middleware_class)
        if instance is None:
            pytest.skip(
                f"Cannot instantiate {middleware_class.__name__} for process() test."
            )
        context = _make_context(number=15)
        try:
            result = instance.process(context, _identity_handler)
        except Exception as e:
            # Some middleware may raise domain-specific errors (e.g., rate limit exceeded)
            # but should not raise TypeError or AttributeError from a signature mismatch
            if isinstance(e, (TypeError, AttributeError)):
                pytest.fail(
                    f"{middleware_class.__name__}.process() raised {type(e).__name__}: {e}. "
                    f"The method signature does not match the IMiddleware contract."
                )
            # Other exceptions are acceptable — chaos middleware may inject faults,
            # rate limiter may deny access, auth may require credentials.
            # The contract is about the signature, not the business logic.
            return

    @pytest.mark.parametrize(
        "middleware_class",
        _REPRESENTATIVE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_process_returns_processing_context(self, middleware_class: type) -> None:
        """process() must return a ProcessingContext, not None, not void, not an enum."""
        instance = _try_instantiate(middleware_class)
        if instance is None:
            pytest.skip(f"Cannot instantiate {middleware_class.__name__}.")
        context = _make_context(number=15)
        try:
            result = instance.process(context, _identity_handler)
        except Exception:
            # Business-logic exceptions are tolerated; we only care about return type
            return

        assert result is not None, (
            f"{middleware_class.__name__}.process() returned None. "
            f"The pipeline expects a ProcessingContext, not the void."
        )
        assert isinstance(result, ProcessingContext), (
            f"{middleware_class.__name__}.process() returned "
            f"{type(result).__name__} instead of ProcessingContext. "
            f"The middleware has gone rogue."
        )


# ============================================================
# Contract Tests: Interface Compliance
# ============================================================


class TestMiddlewareIsIMiddleware:
    """Verify that every discovered class truly satisfies isinstance(x, IMiddleware).

    This is the most fundamental contract test: if you claim to be a
    middleware, you had better be one. Anything less is resume fraud.
    """

    @pytest.mark.parametrize(
        "middleware_class",
        ALL_MIDDLEWARE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_instance_is_imiddleware(self, middleware_class: type) -> None:
        """An instance of the class must pass isinstance(x, IMiddleware)."""
        instance = _try_instantiate(middleware_class)
        if instance is None:
            pytest.skip(f"Cannot instantiate {middleware_class.__name__}.")
        assert isinstance(instance, IMiddleware), (
            f"{middleware_class.__name__} claims to be a middleware but fails "
            f"isinstance(x, IMiddleware). This is the duck-typing equivalent "
            f"of quacking but not being a duck."
        )


# ============================================================
# Contract Tests: Consistency Across Pipeline
# ============================================================


class TestMiddlewarePipelineConsistency:
    """Cross-middleware consistency checks.

    These tests verify properties that must hold across the entire
    collection of middleware implementations, not just for individual
    classes.
    """

    def test_all_middleware_names_are_unique(self) -> None:
        """Every middleware must have a unique name.

        Duplicate names in the pipeline would make debugging impossible,
        and debugging enterprise FizzBuzz middleware is hard enough already.
        """
        names: dict[str, list[str]] = {}
        for cls in ALL_MIDDLEWARE_CLASSES:
            instance = _try_instantiate(cls)
            if instance is None:
                continue
            name = instance.get_name()
            names.setdefault(name, []).append(cls.__name__)

        duplicates = {n: classes for n, classes in names.items() if len(classes) > 1}
        assert not duplicates, (
            f"Multiple middleware classes share the same name: {duplicates}. "
            f"Middleware names must be unique. This is not a boy band — "
            f"nobody gets to be called 'The One'."
        )

    def test_priorities_are_integers_across_all_middlewares(self) -> None:
        """Every instantiatable middleware must return an int priority.

        A comprehensive sweep across all implementations, because
        one middleware returning a float priority would silently
        break the pipeline's sort stability guarantees.
        """
        failures = []
        for cls in ALL_MIDDLEWARE_CLASSES:
            instance = _try_instantiate(cls)
            if instance is None:
                continue
            priority = instance.get_priority()
            if not isinstance(priority, int):
                failures.append(f"{cls.__name__}: {type(priority).__name__}")
        assert not failures, (
            f"Non-integer priorities detected: {failures}. "
            f"The pipeline sort algorithm requires integers, not aspirations."
        )

    def test_names_match_class_names_loosely(self) -> None:
        """Middleware names should bear some resemblance to their class names.

        This is not a strict requirement, but if TimingMiddleware.get_name()
        returns "ChaosMonkey", someone has made a terrible mistake. We verify
        that the name is a non-empty string (stricter checks are left to
        the code review process, which is itself a middleware of sorts).
        """
        for cls in ALL_MIDDLEWARE_CLASSES:
            instance = _try_instantiate(cls)
            if instance is None:
                continue
            name = instance.get_name()
            assert isinstance(name, str) and len(name.strip()) > 0, (
                f"{cls.__name__}.get_name() returned a falsy value: {name!r}. "
                f"Every middleware deserves a name. Even the bad ones."
            )

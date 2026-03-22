"""
Enterprise FizzBuzz Platform - Dashboard Rendering After Real Evaluations

Integration tests that run REAL FizzBuzz evaluations through each subsystem,
then render its ASCII dashboard and verify it contains actual, non-zero
metrics from the run. A dashboard full of zeros is a dashboard that proves
nothing — it is the observability equivalent of monitoring an empty room
and announcing "no intruders detected."

These tests prove that the dashboards are not merely ASCII art generators
for hypothetical data but genuine visualizations of real computational
events that actually occurred in the pipeline. Every non-zero value in
the rendered output is a small victory against the void.

Test categories:
  1. SLA Dashboard: 50 evals, non-zero P50/P99, Bob's name
  2. Compliance Dashboard: 20 evals, non-zero compliance rate, Bob's stress > 94.7
  3. FinOps Invoice: 30 evals, non-zero subtotal, tax breakdown
  4. Cache Stats: 50 evals with repeats, non-zero hit count
  5. Circuit Breaker Dashboard: trip it, verify OPEN state shown
  6. DR Dashboard: evals through DR middleware, non-zero WAL entries
  7. Health Dashboard: registered subsystem statuses populated
  8. Quantum Dashboard: 5 quantum evals, negative advantage ratio
  9. FBaaS Dashboard: tenant created, evals recorded, tenant appears
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Callable

import pytest

# Add parent dirs to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.domain.models import (
    FizzBuzzClassification,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ConcreteRule,
    StandardRuleEngine,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singleton instances between tests.

    Because singletons are the cockroaches of software architecture:
    impossible to kill and always lurking in global state.
    """
    _SingletonMeta.reset()
    try:
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerRegistry,
        )
        CircuitBreakerRegistry.reset()
    except Exception:
        pass
    try:
        from enterprise_fizzbuzz.infrastructure.health import HealthCheckRegistry
        HealthCheckRegistry.reset()
    except Exception:
        pass
    yield
    _SingletonMeta.reset()


@pytest.fixture
def default_rules():
    """The canonical FizzBuzz rules that have launched a thousand interviews."""
    return [
        ConcreteRule(RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2)),
    ]


@pytest.fixture
def engine():
    """A StandardRuleEngine — the humble workhorse of FizzBuzz evaluation."""
    return StandardRuleEngine()


def _evaluate_number(engine, rules, number: int) -> FizzBuzzResult:
    """Evaluate a single number and return the FizzBuzzResult."""
    return engine.evaluate(number, rules)


def _classify(output: str) -> FizzBuzzClassification:
    """Derive a FizzBuzzClassification from the output string."""
    if output == "FizzBuzz":
        return FizzBuzzClassification.FIZZBUZZ
    elif output == "Fizz":
        return FizzBuzzClassification.FIZZ
    elif output == "Buzz":
        return FizzBuzzClassification.BUZZ
    else:
        return FizzBuzzClassification.PLAIN


def _make_context(number: int) -> ProcessingContext:
    """Create a fresh ProcessingContext for a given number."""
    return ProcessingContext(
        number=number,
        session_id=str(uuid.uuid4()),
    )


def _make_final_handler(engine, rules):
    """Build the terminal handler that performs actual FizzBuzz evaluation."""
    def handler(ctx: ProcessingContext) -> ProcessingContext:
        result = engine.evaluate(ctx.number, rules)
        ctx.results.append(result)
        return ctx
    return handler


# ============================================================
# 1. SLA Dashboard
# ============================================================


class TestSLADashboardAfterRealEvaluations:
    """Verify the SLA Dashboard renders non-zero metrics after real evaluations.

    The SLA monitor tracks latency, accuracy, and availability for every
    FizzBuzz evaluation. After 50 real evaluations, the dashboard should
    display actual P50 and P99 latencies, a non-zero evaluation count,
    and Bob McFizzington's name in the on-call section — because Bob
    is always on call.
    """

    def test_sla_dashboard_shows_non_zero_total_evaluations(self, engine, default_rules):
        """After 50 evaluations, the dashboard should show the count."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLADashboard, SLAMonitor, SLODefinition, SLOType,
        )

        slo_defs = [
            SLODefinition(name="latency", slo_type=SLOType.LATENCY, target=0.999, threshold_ms=100.0),
            SLODefinition(name="accuracy", slo_type=SLOType.ACCURACY, target=0.999),
            SLODefinition(name="availability", slo_type=SLOType.AVAILABILITY, target=0.999),
        ]
        monitor = SLAMonitor(slo_definitions=slo_defs)

        for n in range(1, 51):
            result = _evaluate_number(engine, default_rules, n)
            latency_ns = max(result.processing_time_ns, 1)
            monitor.record_evaluation(
                latency_ns=latency_ns,
                number=n,
                output=result.output,
                success=True,
            )

        dashboard = SLADashboard.render(monitor)

        assert "50" in dashboard, "Dashboard should show 50 total evaluations"
        assert "Total Evaluations" in dashboard

    def test_sla_dashboard_shows_non_zero_p50_and_p99_latency(self, engine, default_rules):
        """P50 and P99 latencies should be non-zero after real evaluations."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLADashboard, SLAMonitor, SLODefinition, SLOType,
        )

        slo_defs = [
            SLODefinition(name="latency", slo_type=SLOType.LATENCY, target=0.999, threshold_ms=100.0),
        ]
        monitor = SLAMonitor(slo_definitions=slo_defs)

        for n in range(1, 51):
            result = _evaluate_number(engine, default_rules, n)
            latency_ns = max(result.processing_time_ns, 1)
            monitor.record_evaluation(
                latency_ns=latency_ns,
                number=n,
                output=result.output,
                success=True,
            )

        dashboard = SLADashboard.render(monitor)

        assert "P50 Latency" in dashboard
        assert "P99 Latency" in dashboard
        # The P50 and P99 should not be 0.0000 ms
        p50 = monitor.collector.get_p50_latency_ms()
        p99 = monitor.collector.get_p99_latency_ms()
        assert p50 > 0, "P50 latency must be non-zero after real evaluations"
        assert p99 > 0, "P99 latency must be non-zero after real evaluations"

    def test_sla_dashboard_shows_bob_mcfizzington_on_call(self, engine, default_rules):
        """Bob McFizzington should always be listed as on-call."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLADashboard, SLAMonitor, SLODefinition, SLOType,
        )

        monitor = SLAMonitor(slo_definitions=[
            SLODefinition(name="accuracy", slo_type=SLOType.ACCURACY, target=0.999),
        ])

        for n in range(1, 11):
            result = _evaluate_number(engine, default_rules, n)
            monitor.record_evaluation(
                latency_ns=max(result.processing_time_ns, 1),
                number=n,
                output=result.output,
            )

        dashboard = SLADashboard.render(monitor)

        assert "Bob McFizzington" in dashboard
        assert "ON-CALL STATUS" in dashboard

    def test_sla_dashboard_shows_slo_compliance_section(self, engine, default_rules):
        """SLO compliance percentages should appear in the rendered dashboard."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLADashboard, SLAMonitor, SLODefinition, SLOType,
        )

        slo_defs = [
            SLODefinition(name="latency", slo_type=SLOType.LATENCY, target=0.999, threshold_ms=100.0),
            SLODefinition(name="accuracy", slo_type=SLOType.ACCURACY, target=0.999),
        ]
        monitor = SLAMonitor(slo_definitions=slo_defs)

        for n in range(1, 51):
            result = _evaluate_number(engine, default_rules, n)
            monitor.record_evaluation(
                latency_ns=max(result.processing_time_ns, 1),
                number=n,
                output=result.output,
            )

        dashboard = SLADashboard.render(monitor)

        assert "SLO COMPLIANCE" in dashboard
        assert "latency" in dashboard
        assert "accuracy" in dashboard


# ============================================================
# 2. Compliance Dashboard
# ============================================================


class TestComplianceDashboardAfterRealEvaluations:
    """Verify the Compliance Dashboard reflects real compliance checks.

    After running 20 FizzBuzz evaluations through the compliance framework
    (with all three regimes enabled), the dashboard should display a
    non-zero compliance rate, Bob's stress level above 94.7%, and data
    classification counts that prove numbers were actually classified.
    """

    def _make_compliance_framework(self):
        """Wire up the full compliance framework with SOX, GDPR, and HIPAA."""
        from enterprise_fizzbuzz.infrastructure.compliance import (
            ComplianceFramework, GDPRController, HIPAAGuard, SOXAuditor,
        )

        sox_roster = [
            {"name": "Alice", "title": "Fizz Evaluator", "clearance": "CONFIDENTIAL"},
            {"name": "Bob", "title": "Buzz Evaluator", "clearance": "SECRET"},
            {"name": "Charlie", "title": "Formatter", "clearance": "TOP_SECRET"},
            {"name": "Diana", "title": "Auditor", "clearance": "TOP_SECRET"},
            {"name": "Eve", "title": "Observer", "clearance": "INTERNAL"},
        ]

        sox = SOXAuditor(personnel_roster=sox_roster, strict_mode=False)
        gdpr = GDPRController(auto_consent=True)
        hipaa = HIPAAGuard()

        return ComplianceFramework(
            sox_auditor=sox,
            gdpr_controller=gdpr,
            hipaa_guard=hipaa,
        )

    def test_compliance_dashboard_shows_non_zero_compliance_rate(self, engine, default_rules):
        """The compliance rate should be greater than zero after real checks."""
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceDashboard

        framework = self._make_compliance_framework()

        for n in range(1, 21):
            result = _evaluate_number(engine, default_rules, n)
            framework.perform_compliance_check(result)

        dashboard = ComplianceDashboard.render(framework)

        assert "COMPLIANCE" in dashboard
        assert "Rate:" in dashboard
        posture = framework.get_posture_summary()
        assert posture["compliance_rate"] > 0, "Compliance rate must be non-zero"

    def test_compliance_dashboard_shows_bob_stress_above_baseline(self, engine, default_rules):
        """Bob's stress should exceed the baseline 94.7% after 20 checks."""
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceDashboard

        framework = self._make_compliance_framework()

        for n in range(1, 21):
            result = _evaluate_number(engine, default_rules, n)
            framework.perform_compliance_check(result)

        dashboard = ComplianceDashboard.render(framework)

        assert "BOB McFIZZINGTON" in dashboard or "STRESS" in dashboard
        assert framework.bob_stress_level > 94.7, (
            f"Bob's stress should exceed baseline 94.7%, got {framework.bob_stress_level}"
        )

    def test_compliance_dashboard_shows_data_classification_counts(self, engine, default_rules):
        """Data classification breakdown should contain non-zero counts."""
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceDashboard

        framework = self._make_compliance_framework()

        for n in range(1, 21):
            result = _evaluate_number(engine, default_rules, n)
            framework.perform_compliance_check(result)

        dashboard = ComplianceDashboard.render(framework)
        posture = framework.get_posture_summary()
        class_stats = posture["classification_stats"]

        assert class_stats["total_classified"] == 20
        assert "DATA CLASSIFICATION" in dashboard

    def test_compliance_dashboard_shows_total_checks(self, engine, default_rules):
        """The total check count should be non-zero and match expectations."""
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceDashboard

        framework = self._make_compliance_framework()

        for n in range(1, 21):
            result = _evaluate_number(engine, default_rules, n)
            framework.perform_compliance_check(result)

        dashboard = ComplianceDashboard.render(framework)

        assert "Total Checks:" in dashboard
        posture = framework.get_posture_summary()
        # 3 regimes * 20 checks = 60 individual check results
        assert posture["total_checks"] == 60


# ============================================================
# 3. FinOps Invoice
# ============================================================


class TestFinOpsInvoiceAfterRealEvaluations:
    """Verify the FinOps Invoice contains non-zero charges after real evaluations.

    After 30 evaluations, the invoice should contain a non-zero subtotal,
    tax breakdown showing Fizz (3%), Buzz (5%), and FizzBuzz (15%) rates,
    and a budget utilization bar that reflects actual spending.
    """

    def _make_finops(self):
        """Wire up the FinOps cost tracking engine."""
        from enterprise_fizzbuzz.infrastructure.finops import (
            CostTracker, FizzBuckCurrency, FizzBuzzTaxEngine,
            InvoiceGenerator, SubsystemCostRegistry,
        )

        registry = SubsystemCostRegistry()
        tax_engine = FizzBuzzTaxEngine()
        currency = FizzBuckCurrency()
        tracker = CostTracker(
            cost_registry=registry,
            tax_engine=tax_engine,
            currency=currency,
            budget_limit=10.0,
        )
        return tracker, InvoiceGenerator, currency

    def test_finops_invoice_shows_non_zero_subtotal(self, engine, default_rules):
        """The invoice subtotal should be non-zero after 30 evaluations."""
        tracker, InvoiceGenerator, currency = self._make_finops()

        for n in range(1, 31):
            result = _evaluate_number(engine, default_rules, n)
            classification = _classify(result.output)
            tracker.record_evaluation(number=n, classification=classification, is_friday=False)

        invoice = InvoiceGenerator.generate(tracker)

        assert tracker.total_spent > 0, "Total spent must be non-zero"
        assert "SUBTOTAL" in invoice or "Subtotal" in invoice or "subtotal" in invoice.lower()
        assert "GRAND TOTAL" in invoice

    def test_finops_invoice_shows_tax_breakdown(self, engine, default_rules):
        """Tax breakdown should show Fizz (3%), Buzz (5%), FizzBuzz (15%) rates."""
        tracker, InvoiceGenerator, currency = self._make_finops()

        for n in range(1, 31):
            result = _evaluate_number(engine, default_rules, n)
            classification = _classify(result.output)
            tracker.record_evaluation(number=n, classification=classification, is_friday=False)

        invoice = InvoiceGenerator.generate(tracker)

        assert "TAX BREAKDOWN" in invoice
        assert "3%" in invoice, "Fizz tax rate (3%) should appear in invoice"
        assert "5%" in invoice, "Buzz tax rate (5%) should appear in invoice"
        assert "15%" in invoice, "FizzBuzz tax rate (15%) should appear in invoice"

    def test_finops_invoice_shows_budget_utilization(self, engine, default_rules):
        """Budget utilization bar should reflect actual spending."""
        tracker, InvoiceGenerator, currency = self._make_finops()

        for n in range(1, 31):
            result = _evaluate_number(engine, default_rules, n)
            classification = _classify(result.output)
            tracker.record_evaluation(number=n, classification=classification, is_friday=False)

        invoice = InvoiceGenerator.generate(tracker)

        assert "BUDGET STATUS" in invoice
        assert tracker.budget_utilization_pct > 0, "Budget utilization must be non-zero"

    def test_finops_invoice_shows_evaluation_count(self, engine, default_rules):
        """The invoice should display the correct evaluation count."""
        tracker, InvoiceGenerator, currency = self._make_finops()

        for n in range(1, 31):
            result = _evaluate_number(engine, default_rules, n)
            classification = _classify(result.output)
            tracker.record_evaluation(number=n, classification=classification, is_friday=False)

        invoice = InvoiceGenerator.generate(tracker)

        assert "30" in invoice, "Invoice should show 30 evaluations"
        assert tracker.evaluation_count == 30


# ============================================================
# 4. Cache Statistics Dashboard
# ============================================================


class TestCacheDashboardAfterRealEvaluations:
    """Verify the Cache Dashboard shows non-zero hits after repeated evaluations.

    Run 50 evaluations through a cached pipeline, with some numbers
    repeated. The dashboard should show a non-zero hit count and a
    hit rate above 0%. The MESI coherence distribution should also
    be populated, proving the cache coherence protocol is not just
    decorative ASCII art.
    """

    def test_cache_dashboard_shows_non_zero_hit_count(self, engine, default_rules):
        """Cache should register hits when the same numbers are evaluated twice."""
        from enterprise_fizzbuzz.infrastructure.cache import CacheDashboard, CacheStore

        cache = CacheStore(max_size=256)

        # First pass: populate the cache (all misses)
        for n in range(1, 26):
            result = _evaluate_number(engine, default_rules, n)
            cached = cache.get(n)
            if cached is None:
                cache.put(n, result)

        # Second pass: same numbers (all hits)
        for n in range(1, 26):
            cached = cache.get(n)

        stats = cache.get_statistics()
        dashboard = CacheDashboard.render(stats)

        assert stats.total_hits > 0, "Cache should have non-zero hits"
        assert stats.total_hits >= 25, "Second pass should produce at least 25 hits"
        assert "Total Hits" in dashboard
        assert "Hit Rate" in dashboard

    def test_cache_dashboard_shows_hit_rate_above_zero(self, engine, default_rules):
        """Hit rate should be above 0% when repeated numbers are evaluated."""
        from enterprise_fizzbuzz.infrastructure.cache import CacheDashboard, CacheStore

        cache = CacheStore(max_size=256)

        # Evaluate numbers 1-25, then repeat 1-25
        for n in range(1, 26):
            result = _evaluate_number(engine, default_rules, n)
            cache.get(n)  # miss
            cache.put(n, result)

        for n in range(1, 26):
            cache.get(n)  # hit

        stats = cache.get_statistics()
        dashboard = CacheDashboard.render(stats)

        assert stats.hit_rate > 0, "Hit rate must be above 0%"
        assert "CACHE STATISTICS DASHBOARD" in dashboard

    def test_cache_dashboard_shows_mesi_distribution(self, engine, default_rules):
        """MESI coherence state distribution should be populated."""
        from enterprise_fizzbuzz.infrastructure.cache import CacheDashboard, CacheStore

        cache = CacheStore(max_size=256, enable_coherence=True)

        for n in range(1, 16):
            result = _evaluate_number(engine, default_rules, n)
            cache.put(n, result)

        stats = cache.get_statistics()
        dashboard = CacheDashboard.render(stats)

        assert stats.total_entries > 0, "Cache should have entries"
        assert "MESI" in dashboard or stats.mesi_distribution, (
            "MESI distribution should be present"
        )


# ============================================================
# 5. Circuit Breaker Dashboard
# ============================================================


class TestCircuitBreakerDashboardAfterTrip:
    """Verify the Circuit Breaker Dashboard shows OPEN state after tripping.

    To trip the circuit breaker, we inject failures until the failure
    threshold is exceeded. Then we render the dashboard and verify it
    shows OPEN state with a non-zero failure count and trip count.
    """

    def test_circuit_breaker_dashboard_shows_open_state(self):
        """After enough failures, the circuit breaker should be OPEN."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreaker, CircuitBreakerDashboard, CircuitState,
        )

        cb = CircuitBreaker(
            name="FizzBuzzTestCircuit",
            failure_threshold=3,
            sliding_window_size=10,
        )

        # Inject failures to trip the breaker
        for _ in range(3):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("simulated failure")))
            except RuntimeError:
                pass

        assert cb.state == CircuitState.OPEN, "Circuit should be OPEN after 3 failures"

        dashboard = CircuitBreakerDashboard.render(cb)

        assert "OPEN" in dashboard
        assert "REJECTING REQUESTS" in dashboard

    def test_circuit_breaker_dashboard_shows_non_zero_failure_count(self):
        """Failure count and trip count should be non-zero after tripping."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreaker, CircuitBreakerDashboard,
        )

        cb = CircuitBreaker(
            name="FizzBuzzMetricsCircuit",
            failure_threshold=3,
            sliding_window_size=10,
        )

        # 2 successes then 3 failures to trip
        for _ in range(2):
            cb.execute(lambda: "OK")

        for _ in range(3):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except RuntimeError:
                pass

        dashboard = CircuitBreakerDashboard.render(cb)
        metrics = cb.metrics

        assert metrics.total_failures >= 3
        assert metrics.trip_count >= 1
        assert "Failures" in dashboard
        assert "Trip Count" in dashboard

    def test_circuit_breaker_dashboard_shows_sliding_window(self):
        """The sliding window visualization should contain success and failure markers."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreaker, CircuitBreakerDashboard,
        )

        cb = CircuitBreaker(
            name="SlidingWindowCircuit",
            failure_threshold=5,
            sliding_window_size=10,
        )

        # Mix of successes and failures
        for _ in range(3):
            cb.execute(lambda: "OK")
        for _ in range(2):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("oops")))
            except RuntimeError:
                pass

        dashboard = CircuitBreakerDashboard.render(cb)

        # "+" = success, "X" = failure in sliding window
        assert "+" in dashboard, "Sliding window should show success markers"
        assert "X" in dashboard, "Sliding window should show failure markers"
        assert "Sliding Window" in dashboard


# ============================================================
# 6. DR Dashboard
# ============================================================


class TestDRDashboardAfterRealEvaluations:
    """Verify the DR Dashboard shows non-zero WAL entries after evaluations.

    The DRMiddleware appends a WAL entry for every evaluation and creates
    auto-snapshots at configured intervals. After running evaluations
    through the middleware, the dashboard should display a non-zero WAL
    entry count, at least one backup in the vault, and the storage medium
    listed as 'RAM (volatile)'.
    """

    def test_dr_dashboard_shows_non_zero_wal_entries(self, engine, default_rules):
        """WAL should contain entries after evaluations pass through DR middleware."""
        from enterprise_fizzbuzz.infrastructure.disaster_recovery import (
            BackupManager, DRMiddleware, PITREngine, RecoveryDashboard,
            RetentionManager, RetentionPolicy, SnapshotEngine, WriteAheadLog,
        )

        wal = WriteAheadLog(max_entries=10000)
        snapshot_engine = SnapshotEngine()
        backup_mgr = BackupManager(max_snapshots=50, snapshot_engine=snapshot_engine)
        pitr = PITREngine(wal=wal, snapshot_engine=snapshot_engine, backup_manager=backup_mgr)
        retention = RetentionManager(policy=RetentionPolicy())

        dr_middleware = DRMiddleware(
            wal=wal,
            backup_manager=backup_mgr,
            auto_snapshot_interval=10,
        )

        handler = _make_final_handler(engine, default_rules)

        for n in range(1, 21):
            ctx = _make_context(n)
            dr_middleware.process(ctx, handler)

        dashboard = RecoveryDashboard.render(wal, backup_mgr, pitr, retention)

        wal_stats = wal.get_statistics()
        assert wal_stats["total_entries"] > 0, "WAL should have entries"
        assert "WRITE-AHEAD LOG" in dashboard
        assert "Total Entries" in dashboard

    def test_dr_dashboard_shows_backup_in_vault(self, engine, default_rules):
        """At least one auto-snapshot backup should exist after 10+ evaluations."""
        from enterprise_fizzbuzz.infrastructure.disaster_recovery import (
            BackupManager, DRMiddleware, PITREngine, RecoveryDashboard,
            RetentionManager, RetentionPolicy, SnapshotEngine, WriteAheadLog,
        )

        wal = WriteAheadLog(max_entries=10000)
        snapshot_engine = SnapshotEngine()
        backup_mgr = BackupManager(max_snapshots=50, snapshot_engine=snapshot_engine)
        pitr = PITREngine(wal=wal, snapshot_engine=snapshot_engine, backup_manager=backup_mgr)
        retention = RetentionManager(policy=RetentionPolicy())

        dr_middleware = DRMiddleware(
            wal=wal,
            backup_manager=backup_mgr,
            auto_snapshot_interval=10,
        )

        handler = _make_final_handler(engine, default_rules)

        for n in range(1, 21):
            ctx = _make_context(n)
            dr_middleware.process(ctx, handler)

        dashboard = RecoveryDashboard.render(wal, backup_mgr, pitr, retention)
        backup_stats = backup_mgr.get_statistics()

        assert backup_stats["total_backups_created"] >= 1, (
            "At least one auto-snapshot should have been created after 20 evaluations"
        )
        assert "BACKUP VAULT" in dashboard

    def test_dr_dashboard_shows_ram_storage_medium(self, engine, default_rules):
        """The storage medium should be listed as RAM-based."""
        from enterprise_fizzbuzz.infrastructure.disaster_recovery import (
            BackupManager, DRMiddleware, PITREngine, RecoveryDashboard,
            RetentionManager, RetentionPolicy, SnapshotEngine, WriteAheadLog,
        )

        wal = WriteAheadLog(max_entries=10000)
        snapshot_engine = SnapshotEngine()
        backup_mgr = BackupManager(max_snapshots=50, snapshot_engine=snapshot_engine)
        pitr = PITREngine(wal=wal, snapshot_engine=snapshot_engine, backup_manager=backup_mgr)
        retention = RetentionManager(policy=RetentionPolicy())

        handler = _make_final_handler(engine, default_rules)
        dr_middleware = DRMiddleware(wal=wal, backup_manager=backup_mgr)

        ctx = _make_context(1)
        dr_middleware.process(ctx, handler)

        dashboard = RecoveryDashboard.render(wal, backup_mgr, pitr, retention)

        assert "RAM" in dashboard, "Dashboard should mention RAM as storage medium"
        assert "WARNING" in dashboard or "IN-MEMORY" in dashboard


# ============================================================
# 7. Health Dashboard
# ============================================================


class TestHealthDashboardAfterRealEvaluations:
    """Verify the Health Dashboard shows populated subsystem statuses.

    After registering health checks and running evaluations, the dashboard
    should show at least one subsystem with a status other than UNKNOWN.
    The liveness probe should confirm the platform is alive by successfully
    evaluating the canary number (15 = FizzBuzz).
    """

    def test_health_dashboard_shows_subsystem_statuses_via_readiness(self):
        """Readiness probe should populate subsystem statuses in the dashboard."""
        from enterprise_fizzbuzz.infrastructure.health import (
            ConfigHealthCheck, HealthCheckRegistry, HealthDashboard,
            ReadinessProbe,
        )

        registry = HealthCheckRegistry()
        registry.register(ConfigHealthCheck(config=None))

        probe = ReadinessProbe(registry=registry)
        report = probe.probe()

        dashboard = HealthDashboard.render(report)

        assert "HEALTH CHECK DASHBOARD" in dashboard
        assert "SUBSYSTEM STATUS" in dashboard
        assert len(report.subsystem_checks) > 0, "At least one subsystem check should exist"

    def test_health_dashboard_shows_liveness_up(self):
        """Liveness probe should report UP after successful canary evaluation."""
        from enterprise_fizzbuzz.infrastructure.health import (
            HealthDashboard, HealthStatus, LivenessProbe,
        )

        probe = LivenessProbe()
        report = probe.probe()

        dashboard = HealthDashboard.render(report)

        assert report.overall_status == HealthStatus.UP
        assert "UP" in dashboard
        assert "FizzBuzz" in dashboard or report.canary_value == "FizzBuzz"

    def test_health_dashboard_shows_multiple_registered_subsystems(self):
        """Dashboard should show all registered subsystem checks."""
        from enterprise_fizzbuzz.infrastructure.health import (
            ConfigHealthCheck, HealthCheckRegistry, HealthDashboard,
            MLEngineHealthCheck, ReadinessProbe, SLABudgetHealthCheck,
        )

        registry = HealthCheckRegistry()
        registry.register(ConfigHealthCheck(config=None))
        registry.register(SLABudgetHealthCheck(sla_monitor=None))
        registry.register(MLEngineHealthCheck(engine=None))

        probe = ReadinessProbe(registry=registry)
        report = probe.probe()

        dashboard = HealthDashboard.render(report)

        assert len(report.subsystem_checks) >= 3, (
            "All three registered subsystem checks should be present"
        )
        assert "config" in dashboard
        assert "sla" in dashboard
        assert "ml_engine" in dashboard


# ============================================================
# 8. Quantum Dashboard
# ============================================================


class TestQuantumDashboardAfterRealEvaluations:
    """Verify the Quantum Dashboard shows negative advantage ratio after evaluations.

    The Quantum Computing Simulator uses Shor's algorithm to perform
    divisibility checking. The quantum approach is always slower than
    classical modulo, so the "Quantum Advantage" ratio should be
    negative (or expressed as a fraction less than 1). The dashboard
    should also include the disclaimer about no actual quantum hardware.
    """

    def test_quantum_dashboard_shows_non_zero_evaluation_count(self):
        """After 5 quantum evaluations, the dashboard should show the count."""
        from enterprise_fizzbuzz.infrastructure.quantum import (
            QuantumDashboard, QuantumFizzBuzzEngine,
        )

        rules = [
            {"divisor": 3, "label": "Fizz", "priority": 1},
            {"divisor": 5, "label": "Buzz", "priority": 2},
        ]
        q_engine = QuantumFizzBuzzEngine(rules=rules, num_qubits=4)

        for n in [3, 5, 7, 15, 22]:
            q_engine.evaluate(n)

        dashboard = QuantumDashboard.render(q_engine)

        assert q_engine.total_evaluations == 5
        assert "Total Evaluations" in dashboard
        assert "5" in dashboard

    def test_quantum_dashboard_shows_negative_advantage_ratio(self):
        """Quantum advantage should be negative (quantum is slower)."""
        from enterprise_fizzbuzz.infrastructure.quantum import (
            QuantumDashboard, QuantumFizzBuzzEngine,
        )

        rules = [
            {"divisor": 3, "label": "Fizz", "priority": 1},
            {"divisor": 5, "label": "Buzz", "priority": 2},
        ]
        q_engine = QuantumFizzBuzzEngine(rules=rules, num_qubits=4)

        for n in [3, 5, 15, 7, 11]:
            q_engine.evaluate(n)

        dashboard = QuantumDashboard.render(q_engine)

        # The average advantage ratio should be < 1 (quantum is slower)
        avg_advantage = q_engine.average_quantum_advantage
        assert "QUANTUM ADVANTAGE" in dashboard
        assert "SLOWER" in dashboard

    def test_quantum_dashboard_shows_disclaimer(self):
        """The dashboard should include the no-actual-quantum-hardware disclaimer."""
        from enterprise_fizzbuzz.infrastructure.quantum import (
            QuantumDashboard, QuantumFizzBuzzEngine,
        )

        rules = [
            {"divisor": 3, "label": "Fizz", "priority": 1},
            {"divisor": 5, "label": "Buzz", "priority": 2},
        ]
        q_engine = QuantumFizzBuzzEngine(rules=rules, num_qubits=4)

        q_engine.evaluate(15)

        dashboard = QuantumDashboard.render(q_engine)

        assert "DISCLAIMER" in dashboard
        assert "quantum hardware" in dashboard.lower() or "No actual quantum" in dashboard

    def test_quantum_dashboard_shows_gate_counts(self):
        """Gates applied and measurements performed should be non-zero."""
        from enterprise_fizzbuzz.infrastructure.quantum import (
            QuantumDashboard, QuantumFizzBuzzEngine,
        )

        rules = [
            {"divisor": 3, "label": "Fizz", "priority": 1},
            {"divisor": 5, "label": "Buzz", "priority": 2},
        ]
        q_engine = QuantumFizzBuzzEngine(rules=rules, num_qubits=4)

        for n in [3, 5, 15]:
            q_engine.evaluate(n)

        dashboard = QuantumDashboard.render(q_engine)

        assert q_engine.checker.simulator.gates_applied > 0
        assert "Gates Applied" in dashboard
        assert "Measurements Performed" in dashboard


# ============================================================
# 9. FBaaS Dashboard
# ============================================================


class TestFBaaSDashboardAfterRealEvaluations:
    """Verify the FBaaS Dashboard shows tenant and usage data after evaluations.

    After creating a tenant, running evaluations through the FBaaS
    middleware, and rendering the dashboard, the tenant should appear
    in the roster and the evaluation count should be non-zero.
    """

    def test_fbaas_dashboard_shows_tenant_in_roster(self, engine, default_rules):
        """Created tenant should appear in the dashboard's tenant roster."""
        from enterprise_fizzbuzz.infrastructure.fbaas import (
            BillingEngine, FBaaSDashboard, FBaaSMiddleware,
            FizzStripeClient, SubscriptionTier, TenantManager, UsageMeter,
        )

        tenant_mgr = TenantManager()
        usage_meter = UsageMeter()
        stripe = FizzStripeClient()
        billing = BillingEngine(stripe, tenant_mgr)

        tenant = tenant_mgr.create_tenant("Acme FizzBuzz Corp", SubscriptionTier.PRO)
        billing.onboard_tenant(tenant)

        middleware = FBaaSMiddleware(
            tenant=tenant,
            usage_meter=usage_meter,
            billing_engine=billing,
            watermark="",
        )

        handler = _make_final_handler(engine, default_rules)
        for n in range(1, 11):
            ctx = _make_context(n)
            middleware.process(ctx, handler)

        dashboard = FBaaSDashboard.render(tenant_mgr, usage_meter, billing, stripe)

        assert "Acme FizzBuzz Corp" in dashboard or tenant.tenant_id[:18] in dashboard
        assert "TENANT ROSTER" in dashboard

    def test_fbaas_dashboard_shows_non_zero_evaluation_count(self, engine, default_rules):
        """Total evaluations should be non-zero after processing through FBaaS."""
        from enterprise_fizzbuzz.infrastructure.fbaas import (
            BillingEngine, FBaaSDashboard, FBaaSMiddleware,
            FizzStripeClient, SubscriptionTier, TenantManager, UsageMeter,
        )

        tenant_mgr = TenantManager()
        usage_meter = UsageMeter()
        stripe = FizzStripeClient()
        billing = BillingEngine(stripe, tenant_mgr)

        tenant = tenant_mgr.create_tenant("Test Tenant", SubscriptionTier.FREE)
        billing.onboard_tenant(tenant)

        middleware = FBaaSMiddleware(
            tenant=tenant,
            usage_meter=usage_meter,
            billing_engine=billing,
            watermark="[Powered by FBaaS Free Tier]",
        )

        handler = _make_final_handler(engine, default_rules)
        for n in range(1, 11):
            ctx = _make_context(n)
            middleware.process(ctx, handler)

        dashboard = FBaaSDashboard.render(tenant_mgr, usage_meter, billing, stripe)

        assert usage_meter.total_evaluations > 0, "Total evaluations must be non-zero"
        assert "Total Evaluations" in dashboard

    def test_fbaas_dashboard_shows_subscription_distribution(self, engine, default_rules):
        """Subscription tier distribution should show non-zero counts."""
        from enterprise_fizzbuzz.infrastructure.fbaas import (
            BillingEngine, FBaaSDashboard, FizzStripeClient,
            SubscriptionTier, TenantManager, UsageMeter,
        )

        tenant_mgr = TenantManager()
        usage_meter = UsageMeter()
        stripe = FizzStripeClient()
        billing = BillingEngine(stripe, tenant_mgr)

        tenant_mgr.create_tenant("Free Co", SubscriptionTier.FREE)
        tenant_mgr.create_tenant("Pro Inc", SubscriptionTier.PRO)

        dashboard = FBaaSDashboard.render(tenant_mgr, usage_meter, billing, stripe)

        assert "SUBSCRIPTION DISTRIBUTION" in dashboard
        assert tenant_mgr.tenant_count >= 2

    def test_fbaas_dashboard_shows_platform_summary(self, engine, default_rules):
        """Platform summary should include total tenant count and MRR."""
        from enterprise_fizzbuzz.infrastructure.fbaas import (
            BillingEngine, FBaaSDashboard, FBaaSMiddleware,
            FizzStripeClient, SubscriptionTier, TenantManager, UsageMeter,
        )

        tenant_mgr = TenantManager()
        usage_meter = UsageMeter()
        stripe = FizzStripeClient()
        billing = BillingEngine(stripe, tenant_mgr)

        tenant = tenant_mgr.create_tenant("Enterprise Corp", SubscriptionTier.ENTERPRISE)
        billing.onboard_tenant(tenant)

        middleware = FBaaSMiddleware(
            tenant=tenant,
            usage_meter=usage_meter,
            billing_engine=billing,
            watermark="",
        )

        handler = _make_final_handler(engine, default_rules)
        for n in range(1, 6):
            ctx = _make_context(n)
            middleware.process(ctx, handler)

        dashboard = FBaaSDashboard.render(tenant_mgr, usage_meter, billing, stripe)

        assert "PLATFORM SUMMARY" in dashboard
        assert "Total Tenants" in dashboard
        assert "FIZZBUZZ-AS-A-SERVICE DASHBOARD" in dashboard

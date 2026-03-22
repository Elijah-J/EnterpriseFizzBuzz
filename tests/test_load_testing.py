"""
Tests for the Enterprise FizzBuzz Platform - Load Testing Framework

Tests the load testing subsystem including workload profiles, virtual users,
load generator, bottleneck analysis, performance reporting, and the ASCII
dashboard. All tests use SMALL workloads (SMOKE profile, 1-3 VUs, 5-10
numbers) to avoid slow test runs, because load testing the load testing
framework at scale would be a level of meta that even this project
cannot survive.
"""

from __future__ import annotations

import time
import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    BottleneckAnalysisError,
    LoadTestConfigurationError,
    LoadTestError,
    LoadTestTimeoutError,
    PerformanceGradeError,
    VirtualUserSpawnError,
)
from enterprise_fizzbuzz.domain.models import EventType, RuleDefinition
from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta
from enterprise_fizzbuzz.infrastructure.load_testing import (
    BottleneckAnalyzer,
    LoadGenerator,
    LoadTestDashboard,
    PerformanceGrade,
    PerformanceReport,
    RequestMetric,
    VirtualUser,
    WorkloadProfile,
    WorkloadSpec,
    WORKLOAD_PROFILES,
    _compute_grade,
    _render_bottleneck_ranking,
    _render_histogram,
    _render_percentile_table,
    get_workload_spec,
    run_load_test,
)


# ================================================================
# Shared fixtures
# ================================================================

STANDARD_RULES = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
]


@pytest.fixture
def rules():
    return STANDARD_RULES


@pytest.fixture
def smoke_spec():
    return get_workload_spec(WorkloadProfile.SMOKE, num_vus=1, numbers_per_vu=5)


# ================================================================
# WorkloadProfile & WorkloadSpec Tests
# ================================================================

class TestWorkloadProfile:
    def test_all_profiles_defined(self):
        """All five workload profiles should exist."""
        profiles = list(WorkloadProfile)
        assert len(profiles) == 5
        assert WorkloadProfile.SMOKE in profiles
        assert WorkloadProfile.LOAD in profiles
        assert WorkloadProfile.STRESS in profiles
        assert WorkloadProfile.SPIKE in profiles
        assert WorkloadProfile.ENDURANCE in profiles

    def test_all_profiles_have_specs(self):
        """Every profile should have a pre-defined WorkloadSpec."""
        for profile in WorkloadProfile:
            assert profile in WORKLOAD_PROFILES
            spec = WORKLOAD_PROFILES[profile]
            assert spec.profile == profile
            assert spec.num_vus > 0
            assert spec.numbers_per_vu > 0
            assert spec.description

    def test_smoke_profile_is_small(self):
        """SMOKE profile should have minimal VUs and numbers."""
        spec = WORKLOAD_PROFILES[WorkloadProfile.SMOKE]
        assert spec.num_vus <= 5
        assert spec.numbers_per_vu <= 20

    def test_spike_profile_has_zero_ramp(self):
        """SPIKE profile should have zero ramp-up (instant traffic)."""
        spec = WORKLOAD_PROFILES[WorkloadProfile.SPIKE]
        assert spec.ramp_up_seconds == 0
        assert spec.ramp_down_seconds == 0


class TestWorkloadSpec:
    def test_valid_spec_passes_validation(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=2, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        spec.validate()  # Should not raise

    def test_zero_vus_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=0, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_negative_vus_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=-1, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_zero_numbers_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=1, numbers_per_vu=0,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_negative_ramp_up_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=1, numbers_per_vu=5,
            ramp_up_seconds=-1, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_negative_think_time_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=1, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=-1, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_get_workload_spec_with_overrides(self):
        spec = get_workload_spec(
            WorkloadProfile.SMOKE, num_vus=3, numbers_per_vu=7
        )
        assert spec.num_vus == 3
        assert spec.numbers_per_vu == 7
        assert spec.profile == WorkloadProfile.SMOKE

    def test_get_workload_spec_defaults(self):
        spec = get_workload_spec(WorkloadProfile.SMOKE)
        base = WORKLOAD_PROFILES[WorkloadProfile.SMOKE]
        assert spec.num_vus == base.num_vus
        assert spec.numbers_per_vu == base.numbers_per_vu


# ================================================================
# RequestMetric Tests
# ================================================================

class TestRequestMetric:
    def test_latency_conversions(self):
        metric = RequestMetric(
            vu_id=0, request_number=0, input_number=15,
            output="FizzBuzz", latency_ns=1_000_000,
            is_correct=True,
        )
        assert metric.latency_ms == pytest.approx(1.0)
        assert metric.latency_us == pytest.approx(1000.0)

    def test_sub_millisecond_latency(self):
        metric = RequestMetric(
            vu_id=0, request_number=0, input_number=3,
            output="Fizz", latency_ns=500,
            is_correct=True,
        )
        assert metric.latency_ms < 1.0
        assert metric.latency_us == pytest.approx(0.5)


# ================================================================
# VirtualUser Tests
# ================================================================

class TestVirtualUser:
    def test_basic_evaluation(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15])
        metrics = vu.run()
        assert len(metrics) == 4
        assert vu.is_completed

    def test_correctness_checking(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[3, 5, 15, 7])
        metrics = vu.run()
        # StandardRuleEngine should produce correct results
        for m in metrics:
            assert m.is_correct

    def test_fizz_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[3])
        metrics = vu.run()
        assert metrics[0].output == "Fizz"
        assert metrics[0].is_correct

    def test_buzz_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[5])
        metrics = vu.run()
        assert metrics[0].output == "Buzz"
        assert metrics[0].is_correct

    def test_fizzbuzz_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[15])
        metrics = vu.run()
        assert metrics[0].output == "FizzBuzz"
        assert metrics[0].is_correct

    def test_plain_number_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[7])
        metrics = vu.run()
        assert metrics[0].output == "7"
        assert metrics[0].is_correct

    def test_subsystem_timings_present(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[15])
        metrics = vu.run()
        m = metrics[0]
        assert "rule_preparation" in m.subsystem_timings
        assert "core_evaluation" in m.subsystem_timings
        assert "correctness_verification" in m.subsystem_timings

    def test_latency_is_positive(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        for m in metrics:
            assert m.latency_ns > 0

    def test_vu_id_in_metrics(self, rules):
        vu = VirtualUser(vu_id=42, rules=rules, numbers=[1, 2])
        metrics = vu.run()
        for m in metrics:
            assert m.vu_id == 42

    def test_event_callback_called(self, rules):
        events = []
        def callback(event):
            events.append(event)

        vu = VirtualUser(vu_id=0, rules=rules, numbers=[3, 5],
                         event_callback=callback)
        vu.run()
        event_types = [e.event_type for e in events]
        assert EventType.LOAD_TEST_VU_SPAWNED in event_types
        assert EventType.LOAD_TEST_VU_COMPLETED in event_types
        assert EventType.LOAD_TEST_REQUEST_COMPLETED in event_types


# ================================================================
# LoadGenerator Tests
# ================================================================

class TestLoadGenerator:
    def test_basic_run(self, rules, smoke_spec):
        gen = LoadGenerator(workload=smoke_spec, rules=rules)
        metrics = gen.run()
        assert len(metrics) == smoke_spec.numbers_per_vu * smoke_spec.num_vus
        assert gen.is_completed
        assert gen.elapsed_seconds > 0

    def test_multiple_vus(self, rules):
        spec = get_workload_spec(WorkloadProfile.SMOKE, num_vus=3, numbers_per_vu=5)
        gen = LoadGenerator(workload=spec, rules=rules)
        metrics = gen.run()
        assert len(metrics) == 15  # 3 VUs * 5 numbers
        vu_ids = {m.vu_id for m in metrics}
        assert len(vu_ids) == 3

    def test_all_results_correct(self, rules, smoke_spec):
        gen = LoadGenerator(workload=smoke_spec, rules=rules)
        metrics = gen.run()
        for m in metrics:
            assert m.is_correct

    def test_event_callback(self, rules, smoke_spec):
        events = []
        def callback(event):
            events.append(event.event_type)

        gen = LoadGenerator(workload=smoke_spec, rules=rules,
                           event_callback=callback)
        gen.run()
        assert EventType.LOAD_TEST_STARTED in events
        assert EventType.LOAD_TEST_COMPLETED in events


# ================================================================
# BottleneckAnalyzer Tests
# ================================================================

class TestBottleneckAnalyzer:
    def test_basic_analysis(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        assert len(results) == 3  # rule_preparation, core_evaluation, correctness_verification

    def test_results_sorted_by_time(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=list(range(1, 11)))
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        for i in range(len(results) - 1):
            assert results[i].total_time_ns >= results[i + 1].total_time_ns

    def test_percentages_sum_to_100(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        total_pct = sum(r.pct_of_total for r in results)
        assert total_pct == pytest.approx(100.0, abs=0.1)

    def test_empty_metrics_raises(self):
        with pytest.raises(BottleneckAnalysisError):
            BottleneckAnalyzer.analyze([])

    def test_subsystem_names(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[15])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        names = {r.subsystem for r in results}
        assert "core_evaluation" in names
        assert "rule_preparation" in names
        assert "correctness_verification" in names

    def test_avg_time_properties(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        for r in results:
            assert r.avg_time_us == r.avg_time_ns / 1_000
            assert r.avg_time_ms == r.avg_time_ns / 1_000_000


# ================================================================
# Performance Grade Tests
# ================================================================

class TestPerformanceGrade:
    def test_a_plus_grade(self):
        assert _compute_grade(0.5) == PerformanceGrade.A_PLUS

    def test_a_grade(self):
        assert _compute_grade(3.0) == PerformanceGrade.A

    def test_b_grade(self):
        assert _compute_grade(25.0) == PerformanceGrade.B

    def test_c_grade(self):
        assert _compute_grade(150.0) == PerformanceGrade.C

    def test_d_grade(self):
        assert _compute_grade(500.0) == PerformanceGrade.D

    def test_f_grade(self):
        assert _compute_grade(2000.0) == PerformanceGrade.F

    def test_boundary_a_plus_a(self):
        assert _compute_grade(0.999) == PerformanceGrade.A_PLUS
        assert _compute_grade(1.0) == PerformanceGrade.A

    def test_boundary_a_b(self):
        assert _compute_grade(4.999) == PerformanceGrade.A
        assert _compute_grade(5.0) == PerformanceGrade.B

    def test_negative_raises(self):
        with pytest.raises(PerformanceGradeError):
            _compute_grade(-1.0)


# ================================================================
# PerformanceReport Tests
# ================================================================

class TestPerformanceReport:
    def test_from_metrics_basic(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15, 7])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.01, profile_name="TEST", num_vus=1
        )
        assert report.total_requests == 5
        assert report.successful_requests == 5
        assert report.failed_requests == 0
        assert report.error_rate == 0
        assert report.p50_ms >= 0
        assert report.p99_ms >= report.p50_ms
        assert report.requests_per_second > 0

    def test_from_empty_metrics(self):
        report = PerformanceReport.from_metrics(
            [], elapsed_seconds=1.0, profile_name="EMPTY", num_vus=0
        )
        assert report.total_requests == 0
        assert report.grade == PerformanceGrade.F

    def test_grade_assignment(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=list(range(1, 11)))
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.001
        )
        # Modulo arithmetic should be fast enough for A+ or A
        assert report.grade in (PerformanceGrade.A_PLUS, PerformanceGrade.A, PerformanceGrade.B)

    def test_bottlenecks_populated(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(metrics, elapsed_seconds=0.01)
        assert len(report.bottlenecks) > 0

    def test_percentile_ordering(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=list(range(1, 11)))
        metrics = vu.run()
        report = PerformanceReport.from_metrics(metrics, elapsed_seconds=0.01)
        assert report.min_ms <= report.p50_ms
        assert report.p50_ms <= report.p90_ms
        assert report.p90_ms <= report.p95_ms
        assert report.p95_ms <= report.p99_ms
        assert report.p99_ms <= report.max_ms


# ================================================================
# Dashboard Rendering Tests
# ================================================================

class TestDashboard:
    def test_histogram_renders(self):
        latencies = [0.1, 0.2, 0.3, 0.5, 1.0, 0.15, 0.25]
        output = _render_histogram(latencies, width=60, num_buckets=5)
        assert "Latency Distribution" in output
        assert "#" in output

    def test_histogram_empty(self):
        output = _render_histogram([], width=60)
        assert "no data" in output

    def test_histogram_single_value(self):
        output = _render_histogram([1.0], width=60, num_buckets=3)
        assert "#" in output

    def test_percentile_table_renders(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(metrics, elapsed_seconds=0.01)
        output = _render_percentile_table(report, width=60)
        assert "Percentile" in output
        assert "p50" in output
        assert "p99" in output

    def test_bottleneck_ranking_renders(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        bottlenecks = BottleneckAnalyzer.analyze(metrics)
        output = _render_bottleneck_ranking(bottlenecks, width=60)
        assert "Bottleneck" in output
        assert "core_evaluation" in output

    def test_bottleneck_ranking_empty(self):
        output = _render_bottleneck_ranking([], width=60)
        assert "No subsystem data" in output

    def test_full_dashboard_renders(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.01, profile_name="SMOKE", num_vus=1
        )
        latencies = [m.latency_ms for m in metrics]
        output = LoadTestDashboard.render(report, latencies_ms=latencies, width=60)
        assert "ENTERPRISE FIZZBUZZ LOAD TEST RESULTS" in output
        assert "SMOKE" in output
        assert "PERFORMANCE GRADE" in output
        assert "Percentile" in output
        assert "END OF LOAD TEST REPORT" in output

    def test_dashboard_without_latencies(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.01, profile_name="SMOKE", num_vus=1
        )
        output = LoadTestDashboard.render(report, width=60)
        assert "ENTERPRISE FIZZBUZZ LOAD TEST RESULTS" in output


# ================================================================
# Integration / Convenience Function Tests
# ================================================================

class TestRunLoadTest:
    def test_run_smoke_test(self, rules):
        report, latencies = run_load_test(
            WorkloadProfile.SMOKE, rules, num_vus=1, numbers_per_vu=5
        )
        assert report.total_requests == 5
        assert len(latencies) == 5
        assert report.error_rate == 0

    def test_run_with_multiple_vus(self, rules):
        report, latencies = run_load_test(
            WorkloadProfile.SMOKE, rules, num_vus=2, numbers_per_vu=5
        )
        assert report.total_requests == 10
        assert len(latencies) == 10

    def test_run_produces_valid_report(self, rules):
        report, _ = run_load_test(
            WorkloadProfile.SMOKE, rules, num_vus=1, numbers_per_vu=10
        )
        assert report.successful_requests == report.total_requests
        assert report.grade in list(PerformanceGrade)


# ================================================================
# Exception Tests
# ================================================================

class TestExceptions:
    def test_load_test_error_hierarchy(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = LoadTestError("test error")
        assert isinstance(err, FizzBuzzError)
        assert "EFP-LT00" in str(err)

    def test_configuration_error(self):
        err = LoadTestConfigurationError("vus", -1, "positive integer")
        assert "EFP-LT01" in str(err)
        assert "vus" in str(err)

    def test_spawn_error(self):
        err = VirtualUserSpawnError(42, "thread pool full")
        assert "EFP-LT02" in str(err)
        assert "42" in str(err)

    def test_timeout_error(self):
        err = LoadTestTimeoutError(60.0, 30.0)
        assert "EFP-LT03" in str(err)

    def test_bottleneck_analysis_error(self):
        err = BottleneckAnalysisError("no data")
        assert "EFP-LT04" in str(err)

    def test_performance_grade_error(self):
        err = PerformanceGradeError("latency", -5.0)
        assert "EFP-LT05" in str(err)


# ================================================================
# EventType Tests
# ================================================================

class TestEventTypes:
    def test_load_test_event_types_exist(self):
        assert EventType.LOAD_TEST_STARTED
        assert EventType.LOAD_TEST_COMPLETED
        assert EventType.LOAD_TEST_VU_SPAWNED
        assert EventType.LOAD_TEST_VU_COMPLETED
        assert EventType.LOAD_TEST_REQUEST_COMPLETED
        assert EventType.LOAD_TEST_BOTTLENECK_IDENTIFIED


# ================================================================
# Config Properties Tests
# ================================================================

class TestConfigProperties:
    def test_load_testing_defaults(self):
        _SingletonMeta.reset()
        config = ConfigurationManager()
        config.load()
        assert config.load_testing_enabled is False
        assert config.load_testing_default_profile == "smoke"
        assert config.load_testing_default_vus == 10
        assert config.load_testing_numbers_per_vu == 100
        assert config.load_testing_timeout_seconds == 300
        assert config.load_testing_dashboard_width == 60
        assert config.load_testing_histogram_buckets == 10
        _SingletonMeta.reset()

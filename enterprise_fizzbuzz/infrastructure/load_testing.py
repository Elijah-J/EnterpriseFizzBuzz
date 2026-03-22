"""
Enterprise FizzBuzz Platform - Load Testing Framework

Implements a comprehensive, production-grade load testing framework for
stress-testing the FizzBuzz evaluation pipeline. Because if your modulo
arithmetic can't handle 10,000 concurrent virtual users all desperately
needing to know whether 15 is FizzBuzz, is it really enterprise-ready?

Features include:
- Virtual Users (VUs) that simulate real-world FizzBuzz traffic patterns
- Five workload profiles (SMOKE, LOAD, STRESS, SPIKE, ENDURANCE)
- ThreadPoolExecutor-based concurrency (because asyncio was too easy)
- Percentile-based latency analysis (p50/p90/p95/p99)
- Bottleneck identification (spoiler: it's always the overhead, not the modulo)
- ASCII dashboard with histogram, percentile table, and performance grade
- Performance grading from A+ to F (A+ means your modulo takes < 1ms)
"""

from __future__ import annotations

import logging
import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BottleneckAnalysisError,
    LoadTestConfigurationError,
    LoadTestTimeoutError,
    PerformanceGradeError,
    VirtualUserSpawnError,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ConcreteRule,
    StandardRuleEngine,
)

logger = logging.getLogger(__name__)


# ================================================================
# Workload Profile Definitions
# ================================================================

class WorkloadProfile(Enum):
    """Workload profiles for Enterprise FizzBuzz load testing.

    Each profile represents a different traffic pattern, because
    FizzBuzz traffic comes in many shapes and sizes. SMOKE is a
    gentle whisper. STRESS is a category 5 hurricane of modulo
    operations. ENDURANCE is the marathon runner who won't stop
    asking "is this number FizzBuzz?" until the heat death of
    the universe or the test timeout, whichever comes first.
    """

    SMOKE = auto()
    LOAD = auto()
    STRESS = auto()
    SPIKE = auto()
    ENDURANCE = auto()


@dataclass(frozen=True)
class WorkloadSpec:
    """Specification for a load test workload.

    Defines the shape of the traffic pattern: how many virtual users,
    how many numbers each evaluates, ramp-up/down timing, and think
    time between requests. Think of it as a recipe for simulated
    human desperation to evaluate modulo arithmetic.
    """

    profile: WorkloadProfile
    num_vus: int
    numbers_per_vu: int
    ramp_up_seconds: float
    ramp_down_seconds: float
    think_time_ms: float
    description: str

    def validate(self) -> None:
        """Validate workload parameters. Raises LoadTestConfigurationError."""
        if self.num_vus < 1:
            raise LoadTestConfigurationError(
                "num_vus", self.num_vus, "a positive integer (at least 1)"
            )
        if self.numbers_per_vu < 1:
            raise LoadTestConfigurationError(
                "numbers_per_vu", self.numbers_per_vu, "a positive integer (at least 1)"
            )
        if self.ramp_up_seconds < 0:
            raise LoadTestConfigurationError(
                "ramp_up_seconds", self.ramp_up_seconds, "a non-negative number"
            )
        if self.ramp_down_seconds < 0:
            raise LoadTestConfigurationError(
                "ramp_down_seconds", self.ramp_down_seconds, "a non-negative number"
            )
        if self.think_time_ms < 0:
            raise LoadTestConfigurationError(
                "think_time_ms", self.think_time_ms, "a non-negative number"
            )


# Pre-defined workload profiles
WORKLOAD_PROFILES: dict[WorkloadProfile, WorkloadSpec] = {
    WorkloadProfile.SMOKE: WorkloadSpec(
        profile=WorkloadProfile.SMOKE,
        num_vus=2,
        numbers_per_vu=10,
        ramp_up_seconds=0,
        ramp_down_seconds=0,
        think_time_ms=0,
        description=(
            "Smoke Test: 2 VUs, 10 numbers each. The gentlest of load tests. "
            "If this fails, the modulo operator itself may be broken."
        ),
    ),
    WorkloadProfile.LOAD: WorkloadSpec(
        profile=WorkloadProfile.LOAD,
        num_vus=10,
        numbers_per_vu=100,
        ramp_up_seconds=2,
        ramp_down_seconds=1,
        think_time_ms=0,
        description=(
            "Load Test: 10 VUs, 100 numbers each. Standard production-level "
            "FizzBuzz traffic. The kind of load that would make a Node.js "
            "developer reach for a cluster module."
        ),
    ),
    WorkloadProfile.STRESS: WorkloadSpec(
        profile=WorkloadProfile.STRESS,
        num_vus=50,
        numbers_per_vu=200,
        ramp_up_seconds=3,
        ramp_down_seconds=2,
        think_time_ms=0,
        description=(
            "Stress Test: 50 VUs, 200 numbers each. The kind of traffic that "
            "occurs when someone posts your FizzBuzz endpoint on Hacker News "
            "and 50 people simultaneously demand to know if 15 is FizzBuzz."
        ),
    ),
    WorkloadProfile.SPIKE: WorkloadSpec(
        profile=WorkloadProfile.SPIKE,
        num_vus=100,
        numbers_per_vu=50,
        ramp_up_seconds=0,
        ramp_down_seconds=0,
        think_time_ms=0,
        description=(
            "Spike Test: 100 VUs, instant ramp. Zero warning. All virtual users "
            "arrive simultaneously, like a flash mob of mathematicians who all "
            "urgently need modulo results RIGHT NOW."
        ),
    ),
    WorkloadProfile.ENDURANCE: WorkloadSpec(
        profile=WorkloadProfile.ENDURANCE,
        num_vus=5,
        numbers_per_vu=1000,
        ramp_up_seconds=1,
        ramp_down_seconds=1,
        think_time_ms=1,
        description=(
            "Endurance Test: 5 VUs, 1000 numbers each, with think time. "
            "The marathon runner of load tests. Tests whether the modulo "
            "operator suffers from fatigue after prolonged use."
        ),
    ),
}


def get_workload_spec(
    profile: WorkloadProfile,
    *,
    num_vus: Optional[int] = None,
    numbers_per_vu: Optional[int] = None,
    ramp_up_seconds: Optional[float] = None,
    ramp_down_seconds: Optional[float] = None,
    think_time_ms: Optional[float] = None,
) -> WorkloadSpec:
    """Get a workload spec for the given profile, with optional overrides."""
    base = WORKLOAD_PROFILES[profile]
    spec = WorkloadSpec(
        profile=profile,
        num_vus=num_vus if num_vus is not None else base.num_vus,
        numbers_per_vu=numbers_per_vu if numbers_per_vu is not None else base.numbers_per_vu,
        ramp_up_seconds=ramp_up_seconds if ramp_up_seconds is not None else base.ramp_up_seconds,
        ramp_down_seconds=ramp_down_seconds if ramp_down_seconds is not None else base.ramp_down_seconds,
        think_time_ms=think_time_ms if think_time_ms is not None else base.think_time_ms,
        description=base.description,
    )
    spec.validate()
    return spec


# ================================================================
# Request Metrics
# ================================================================

@dataclass
class RequestMetric:
    """Per-request timing and correctness data.

    Every single FizzBuzz evaluation gets its own RequestMetric,
    because in the enterprise world, you don't just compute results --
    you measure, record, categorize, percentile, and dashboard
    every last microsecond of the computation.
    """

    vu_id: int
    request_number: int
    input_number: int
    output: str
    latency_ns: int
    is_correct: bool
    timestamp: float = field(default_factory=time.monotonic)
    subsystem_timings: dict[str, int] = field(default_factory=dict)

    @property
    def latency_ms(self) -> float:
        """Latency in milliseconds."""
        return self.latency_ns / 1_000_000

    @property
    def latency_us(self) -> float:
        """Latency in microseconds."""
        return self.latency_ns / 1_000


# ================================================================
# Virtual User
# ================================================================

class VirtualUser:
    """A simulated user that evaluates FizzBuzz numbers.

    Each VirtualUser represents a single thread of execution that
    sequentially evaluates a series of numbers through the
    StandardRuleEngine. It meticulously records timing data for
    every evaluation, because even simulated humans deserve
    enterprise-grade observability into their modulo arithmetic.

    The VirtualUser calls StandardRuleEngine.evaluate() directly
    for maximum throughput, bypassing all middleware, caching,
    circuit breakers, and other enterprise nonsense. This ensures
    that load tests measure the raw performance of the modulo
    operator, which is the only thing that actually does work
    in this entire codebase.
    """

    def __init__(
        self,
        vu_id: int,
        rules: list[RuleDefinition],
        numbers: list[int],
        think_time_ms: float = 0,
        event_callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._vu_id = vu_id
        self._engine = StandardRuleEngine()
        self._concrete_rules = [ConcreteRule(rd) for rd in rules]
        self._numbers = numbers
        self._think_time_ms = think_time_ms
        self._metrics: list[RequestMetric] = []
        self._event_callback = event_callback
        self._started = False
        self._completed = False

    @property
    def vu_id(self) -> int:
        return self._vu_id

    @property
    def metrics(self) -> list[RequestMetric]:
        return list(self._metrics)

    @property
    def is_completed(self) -> bool:
        return self._completed

    def _expected_output(self, number: int) -> str:
        """Compute the expected FizzBuzz output for correctness checking."""
        labels = []
        sorted_rules = sorted(self._concrete_rules, key=lambda r: r.get_definition().priority)
        for rule in sorted_rules:
            if number % rule.get_definition().divisor == 0:
                labels.append(rule.get_definition().label)
        return "".join(labels) or str(number)

    def run(self) -> list[RequestMetric]:
        """Execute all FizzBuzz evaluations and collect metrics."""
        self._started = True
        self._metrics.clear()

        if self._event_callback:
            self._event_callback(Event(
                event_type=EventType.LOAD_TEST_VU_SPAWNED,
                payload={"vu_id": self._vu_id, "num_requests": len(self._numbers)},
                source="LoadTestingFramework",
            ))

        for idx, number in enumerate(self._numbers):
            # Measure subsystem timings
            subsystem_timings: dict[str, int] = {}

            # Phase 1: Rule preparation (sorting, setup)
            prep_start = time.perf_counter_ns()
            sorted_rules = sorted(
                self._concrete_rules, key=lambda r: r.get_definition().priority
            )
            prep_elapsed = time.perf_counter_ns() - prep_start
            subsystem_timings["rule_preparation"] = prep_elapsed

            # Phase 2: Core evaluation (the actual modulo arithmetic)
            eval_start = time.perf_counter_ns()
            result: FizzBuzzResult = self._engine.evaluate(number, self._concrete_rules)
            eval_elapsed = time.perf_counter_ns() - eval_start
            subsystem_timings["core_evaluation"] = eval_elapsed

            # Phase 3: Correctness verification
            verify_start = time.perf_counter_ns()
            expected = self._expected_output(number)
            is_correct = result.output == expected
            verify_elapsed = time.perf_counter_ns() - verify_start
            subsystem_timings["correctness_verification"] = verify_elapsed

            # Total latency includes all phases
            total_latency = prep_elapsed + eval_elapsed + verify_elapsed

            metric = RequestMetric(
                vu_id=self._vu_id,
                request_number=idx,
                input_number=number,
                output=result.output,
                latency_ns=total_latency,
                is_correct=is_correct,
                subsystem_timings=subsystem_timings,
            )
            self._metrics.append(metric)

            if self._event_callback:
                self._event_callback(Event(
                    event_type=EventType.LOAD_TEST_REQUEST_COMPLETED,
                    payload={
                        "vu_id": self._vu_id,
                        "number": number,
                        "latency_ns": total_latency,
                        "is_correct": is_correct,
                    },
                    source="LoadTestingFramework",
                ))

            # Simulate think time between requests
            if self._think_time_ms > 0 and idx < len(self._numbers) - 1:
                time.sleep(self._think_time_ms / 1000)

        self._completed = True

        if self._event_callback:
            self._event_callback(Event(
                event_type=EventType.LOAD_TEST_VU_COMPLETED,
                payload={
                    "vu_id": self._vu_id,
                    "total_requests": len(self._metrics),
                    "errors": sum(1 for m in self._metrics if not m.is_correct),
                },
                source="LoadTestingFramework",
            ))

        return self._metrics


# ================================================================
# Load Generator
# ================================================================

class LoadGenerator:
    """Orchestrates virtual users using ThreadPoolExecutor.

    Manages the lifecycle of VUs including ramp-up, steady-state,
    and ramp-down phases. Uses stdlib concurrent.futures because
    importing a third-party load testing library for a satirical
    FizzBuzz project would be the only genuinely unacceptable form
    of over-engineering in this codebase.
    """

    def __init__(
        self,
        workload: WorkloadSpec,
        rules: list[RuleDefinition],
        event_callback: Optional[Callable[..., Any]] = None,
        timeout_seconds: float = 300,
    ) -> None:
        self._workload = workload
        self._rules = rules
        self._event_callback = event_callback
        self._timeout_seconds = timeout_seconds
        self._all_metrics: list[RequestMetric] = []
        self._vus: list[VirtualUser] = []
        self._start_time: float = 0
        self._end_time: float = 0
        self._completed = False

    @property
    def all_metrics(self) -> list[RequestMetric]:
        return list(self._all_metrics)

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time == 0:
            return 0
        end = self._end_time if self._completed else time.monotonic()
        return end - self._start_time

    @property
    def is_completed(self) -> bool:
        return self._completed

    def _generate_numbers(self, vu_id: int) -> list[int]:
        """Generate a list of numbers for a VU to evaluate.

        Uses a deterministic but varied range so each VU gets slightly
        different numbers, simulating the chaos of production traffic
        where no two users ask about the same number at the same time.
        (They totally do in practice. This just looks better in the metrics.)
        """
        base = (vu_id * 7 + 1) % 100  # Deterministic offset per VU
        return [
            (base + i) % 1000 + 1
            for i in range(self._workload.numbers_per_vu)
        ]

    def run(self) -> list[RequestMetric]:
        """Execute the load test.

        Spawns VUs according to the workload spec, waits for completion,
        and collects all metrics. The ramp-up phase staggers VU creation
        to simulate gradual traffic increase, because even simulated
        traffic deserves a gentle onboarding experience.
        """
        self._workload.validate()
        self._all_metrics.clear()
        self._vus.clear()
        self._start_time = time.monotonic()
        self._completed = False

        if self._event_callback:
            self._event_callback(Event(
                event_type=EventType.LOAD_TEST_STARTED,
                payload={
                    "profile": self._workload.profile.name,
                    "num_vus": self._workload.num_vus,
                    "numbers_per_vu": self._workload.numbers_per_vu,
                },
                source="LoadTestingFramework",
            ))

        # Create virtual users
        for vu_id in range(self._workload.num_vus):
            numbers = self._generate_numbers(vu_id)
            vu = VirtualUser(
                vu_id=vu_id,
                rules=self._rules,
                numbers=numbers,
                think_time_ms=self._workload.think_time_ms,
                event_callback=self._event_callback,
            )
            self._vus.append(vu)

        # Execute with ThreadPoolExecutor
        max_workers = min(self._workload.num_vus, 32)  # Cap thread count
        futures: list[Future[list[RequestMetric]]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i, vu in enumerate(self._vus):
                # Ramp-up delay
                if self._workload.ramp_up_seconds > 0 and self._workload.num_vus > 1:
                    delay = (
                        self._workload.ramp_up_seconds
                        * i
                        / (self._workload.num_vus - 1)
                    )
                    if delay > 0:
                        time.sleep(delay)

                future = executor.submit(vu.run)
                futures.append(future)

            # Collect results with timeout
            deadline = self._start_time + self._timeout_seconds
            for future in as_completed(futures, timeout=max(0, deadline - time.monotonic())):
                try:
                    metrics = future.result(timeout=max(0, deadline - time.monotonic()))
                    self._all_metrics.extend(metrics)
                except Exception as e:
                    logger.error("VU execution failed: %s", e)

        # Ramp-down (simulated)
        if self._workload.ramp_down_seconds > 0:
            time.sleep(self._workload.ramp_down_seconds)

        self._end_time = time.monotonic()
        self._completed = True

        if self._event_callback:
            self._event_callback(Event(
                event_type=EventType.LOAD_TEST_COMPLETED,
                payload={
                    "total_requests": len(self._all_metrics),
                    "elapsed_seconds": self.elapsed_seconds,
                },
                source="LoadTestingFramework",
            ))

        return self._all_metrics


# ================================================================
# Bottleneck Analyzer
# ================================================================

class BottleneckAnalyzer:
    """Identifies slowest subsystems and ranks by latency contribution.

    The bottleneck analyzer examines subsystem-level timing data from
    all requests and determines which component is responsible for the
    most latency. In a real enterprise application, this might reveal
    that the database is slow, or the network is congested, or the
    cache is cold. In FizzBuzz, it invariably reveals that the overhead
    of measuring performance is slower than the actual computation,
    which is the punchline we've all been waiting for.
    """

    @dataclass
    class BottleneckResult:
        """Result of bottleneck analysis for a single subsystem."""
        subsystem: str
        total_time_ns: int
        avg_time_ns: float
        pct_of_total: float
        sample_count: int

        @property
        def avg_time_us(self) -> float:
            return self.avg_time_ns / 1_000

        @property
        def avg_time_ms(self) -> float:
            return self.avg_time_ns / 1_000_000

    @staticmethod
    def analyze(metrics: list[RequestMetric]) -> list[BottleneckResult]:
        """Analyze metrics and return subsystems ranked by latency contribution.

        Returns a list of BottleneckResult sorted by total time (descending),
        so the biggest bottleneck comes first. In FizzBuzz, this is always
        some form of overhead, because the modulo operator itself completes
        in nanoseconds.
        """
        if not metrics:
            raise BottleneckAnalysisError(
                "No metrics to analyze. Run a load test first."
            )

        # Aggregate subsystem timings
        subsystem_totals: dict[str, int] = {}
        subsystem_counts: dict[str, int] = {}

        for metric in metrics:
            for subsystem, timing_ns in metric.subsystem_timings.items():
                subsystem_totals[subsystem] = subsystem_totals.get(subsystem, 0) + timing_ns
                subsystem_counts[subsystem] = subsystem_counts.get(subsystem, 0) + 1

        if not subsystem_totals:
            raise BottleneckAnalysisError(
                "No subsystem timing data available. The metrics exist "
                "but contain no subsystem breakdowns."
            )

        grand_total = sum(subsystem_totals.values())
        if grand_total == 0:
            grand_total = 1  # Avoid division by zero

        results: list[BottleneckAnalyzer.BottleneckResult] = []
        for subsystem, total_ns in subsystem_totals.items():
            count = subsystem_counts[subsystem]
            results.append(BottleneckAnalyzer.BottleneckResult(
                subsystem=subsystem,
                total_time_ns=total_ns,
                avg_time_ns=total_ns / count if count > 0 else 0,
                pct_of_total=(total_ns / grand_total) * 100,
                sample_count=count,
            ))

        # Sort by total time descending (biggest bottleneck first)
        results.sort(key=lambda r: r.total_time_ns, reverse=True)
        return results


# ================================================================
# Performance Report
# ================================================================

class PerformanceGrade(Enum):
    """Performance grades for FizzBuzz load test results.

    A+ means your modulo arithmetic completes in under 1 millisecond
    at the 99th percentile. F means it took over a second. In between
    lies a spectrum of mediocrity that most enterprise systems inhabit.

    The grading system is intentionally harsh because FizzBuzz should
    be fast. If computing n % 3 takes more than a millisecond, something
    has gone terribly wrong, and that something is probably all the
    enterprise infrastructure we've wrapped around it.
    """

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


def _compute_grade(p99_ms: float) -> PerformanceGrade:
    """Compute performance grade from p99 latency.

    A+: p99 < 1ms    (the modulo operator, unencumbered by enterprise)
    A:  p99 < 5ms    (acceptable, some overhead is tolerated)
    B:  p99 < 50ms   (getting suspicious, check the middleware stack)
    C:  p99 < 200ms  (something is wrong, but at least it's not Java)
    D:  p99 < 1000ms (this is a FizzBuzz program, not a database migration)
    F:  p99 >= 1000ms (the modulo operator has given up. So have we.)
    """
    if p99_ms < 0:
        raise PerformanceGradeError("p99_latency_ms", p99_ms)
    if p99_ms < 1:
        return PerformanceGrade.A_PLUS
    if p99_ms < 5:
        return PerformanceGrade.A
    if p99_ms < 50:
        return PerformanceGrade.B
    if p99_ms < 200:
        return PerformanceGrade.C
    if p99_ms < 1000:
        return PerformanceGrade.D
    return PerformanceGrade.F


@dataclass
class PerformanceReport:
    """Comprehensive performance report for a load test run.

    Contains everything a performance engineer could want: percentiles,
    throughput, error rates, bottleneck analysis, and a letter grade
    that reduces all that nuance into a single character that management
    can put on a slide.
    """

    total_requests: int
    successful_requests: int
    failed_requests: int
    elapsed_seconds: float

    # Latency percentiles (in milliseconds)
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float
    stdev_ms: float

    # Throughput
    requests_per_second: float

    # Error rate
    error_rate: float

    # Grade
    grade: PerformanceGrade

    # Bottleneck analysis
    bottlenecks: list[BottleneckAnalyzer.BottleneckResult]

    # Workload info
    profile_name: str
    num_vus: int

    @staticmethod
    def from_metrics(
        metrics: list[RequestMetric],
        elapsed_seconds: float,
        profile_name: str = "CUSTOM",
        num_vus: int = 1,
    ) -> PerformanceReport:
        """Build a performance report from collected metrics."""
        if not metrics:
            return PerformanceReport(
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                elapsed_seconds=elapsed_seconds,
                p50_ms=0, p90_ms=0, p95_ms=0, p99_ms=0,
                min_ms=0, max_ms=0, mean_ms=0, stdev_ms=0,
                requests_per_second=0,
                error_rate=0,
                grade=PerformanceGrade.F,
                bottlenecks=[],
                profile_name=profile_name,
                num_vus=num_vus,
            )

        latencies_ms = [m.latency_ms for m in metrics]
        latencies_ms.sort()

        total = len(metrics)
        successful = sum(1 for m in metrics if m.is_correct)
        failed = total - successful

        # Percentile calculation
        def percentile(data: list[float], pct: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * (pct / 100)
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return data[int(k)]
            d0 = data[int(f)] * (c - k)
            d1 = data[int(c)] * (k - f)
            return d0 + d1

        p50 = percentile(latencies_ms, 50)
        p90 = percentile(latencies_ms, 90)
        p95 = percentile(latencies_ms, 95)
        p99 = percentile(latencies_ms, 99)

        mean = statistics.mean(latencies_ms)
        stdev = statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0.0

        rps = total / elapsed_seconds if elapsed_seconds > 0 else 0
        error_rate = failed / total if total > 0 else 0

        grade = _compute_grade(p99)

        # Bottleneck analysis
        try:
            bottlenecks = BottleneckAnalyzer.analyze(metrics)
        except BottleneckAnalysisError:
            bottlenecks = []

        return PerformanceReport(
            total_requests=total,
            successful_requests=successful,
            failed_requests=failed,
            elapsed_seconds=elapsed_seconds,
            p50_ms=p50,
            p90_ms=p90,
            p95_ms=p95,
            p99_ms=p99,
            min_ms=min(latencies_ms),
            max_ms=max(latencies_ms),
            mean_ms=mean,
            stdev_ms=stdev,
            requests_per_second=rps,
            error_rate=error_rate,
            grade=grade,
            bottlenecks=bottlenecks,
            profile_name=profile_name,
            num_vus=num_vus,
        )


# ================================================================
# ASCII Dashboard
# ================================================================

def _render_histogram(
    latencies_ms: list[float],
    width: int = 60,
    num_buckets: int = 10,
) -> str:
    """Render an ASCII histogram of latency distribution.

    Produces a bar chart showing how many requests fell into each
    latency bucket. In a well-functioning FizzBuzz system, all bars
    will be in the first bucket (sub-millisecond), and the histogram
    will look like a cliff edge. This is the desired outcome.
    """
    if not latencies_ms:
        return "  (no data)\n"

    min_val = min(latencies_ms)
    max_val = max(latencies_ms)

    # Handle edge case where all values are the same
    if min_val == max_val:
        max_val = min_val + 0.001

    bucket_width = (max_val - min_val) / num_buckets
    buckets: list[int] = [0] * num_buckets

    for val in latencies_ms:
        idx = min(int((val - min_val) / bucket_width), num_buckets - 1)
        buckets[idx] += 1

    max_count = max(buckets) if buckets else 1
    bar_area = width - 28  # Space for label and count
    if bar_area < 5:
        bar_area = 5

    lines: list[str] = []
    lines.append("  Latency Distribution (ms):")
    lines.append("  " + "-" * (width - 4))

    for i, count in enumerate(buckets):
        lo = min_val + i * bucket_width
        hi = lo + bucket_width
        bar_len = int((count / max_count) * bar_area) if max_count > 0 else 0
        bar = "#" * bar_len
        label = f"  {lo:7.3f}-{hi:7.3f}"
        lines.append(f"{label} |{bar:<{bar_area}} {count:>5}")

    lines.append("  " + "-" * (width - 4))
    return "\n".join(lines) + "\n"


def _render_percentile_table(report: PerformanceReport, width: int = 60) -> str:
    """Render an ASCII table of percentile latencies."""
    lines: list[str] = []
    inner = width - 6

    lines.append(f"  +{'-' * inner}+")
    lines.append(f"  | {'Percentile Latencies':^{inner - 2}} |")
    lines.append(f"  +{'-' * inner}+")
    lines.append(f"  | {'Metric':<20} {'Value':>20} {'Unit':<10} |")
    lines.append(f"  +{'-' * inner}+")

    rows = [
        ("Min", f"{report.min_ms:.4f}", "ms"),
        ("p50 (Median)", f"{report.p50_ms:.4f}", "ms"),
        ("p90", f"{report.p90_ms:.4f}", "ms"),
        ("p95", f"{report.p95_ms:.4f}", "ms"),
        ("p99", f"{report.p99_ms:.4f}", "ms"),
        ("Max", f"{report.max_ms:.4f}", "ms"),
        ("Mean", f"{report.mean_ms:.4f}", "ms"),
        ("Std Dev", f"{report.stdev_ms:.4f}", "ms"),
    ]

    for label, value, unit in rows:
        lines.append(f"  | {label:<20} {value:>20} {unit:<10} |")

    lines.append(f"  +{'-' * inner}+")
    return "\n".join(lines) + "\n"


def _render_bottleneck_ranking(
    bottlenecks: list[BottleneckAnalyzer.BottleneckResult],
    width: int = 60,
) -> str:
    """Render an ASCII bottleneck ranking table."""
    lines: list[str] = []
    inner = width - 6

    lines.append(f"  +{'-' * inner}+")
    lines.append(f"  | {'Bottleneck Analysis':^{inner - 2}} |")
    lines.append(f"  +{'-' * inner}+")

    if not bottlenecks:
        lines.append(f"  | {'No subsystem data available':^{inner - 2}} |")
        lines.append(f"  +{'-' * inner}+")
        return "\n".join(lines) + "\n"

    header = f"  | {'#':<3} {'Subsystem':<25} {'Avg (us)':>10} {'% Total':>8} |"
    lines.append(header)
    lines.append(f"  +{'-' * inner}+")

    for i, b in enumerate(bottlenecks):
        rank = i + 1
        name = b.subsystem[:25]
        avg_us = f"{b.avg_time_us:.1f}"
        pct = f"{b.pct_of_total:.1f}%"
        lines.append(f"  | {rank:<3} {name:<25} {avg_us:>10} {pct:>8} |")

    lines.append(f"  +{'-' * inner}+")

    # The punchline
    if bottlenecks and bottlenecks[-1].subsystem == "core_evaluation":
        lines.append(
            f"  | {'NOTE: The actual modulo arithmetic is the FASTEST':^{inner - 2}} |"
        )
        lines.append(
            f"  | {'part. Everything else is overhead. As intended.':^{inner - 2}} |"
        )
        lines.append(f"  +{'-' * inner}+")
    elif bottlenecks and bottlenecks[0].subsystem == "core_evaluation":
        lines.append(
            f"  | {'NOTE: The modulo operator is somehow the SLOWEST':^{inner - 2}} |"
        )
        lines.append(
            f"  | {'component. Mathematics itself may be degraded.':^{inner - 2}} |"
        )
        lines.append(f"  +{'-' * inner}+")

    return "\n".join(lines) + "\n"


# Grade commentary mapping
_GRADE_COMMENTARY: dict[PerformanceGrade, str] = {
    PerformanceGrade.A_PLUS: (
        "Flawless. The modulo operator is performing at peak efficiency. "
        "Sub-millisecond p99 latency for an arithmetic operation. As expected."
    ),
    PerformanceGrade.A: (
        "Excellent. Slight overhead detected, but still well within "
        "the acceptable latency budget for computing n % 3."
    ),
    PerformanceGrade.B: (
        "Acceptable. Some enterprise infrastructure overhead is showing. "
        "The modulo operator is fine; it's everything around it that's slow."
    ),
    PerformanceGrade.C: (
        "Mediocre. FizzBuzz evaluation is taking longer than it should. "
        "Consider removing some of the 47 middleware layers."
    ),
    PerformanceGrade.D: (
        "Poor. Computing n % 3 should not take this long. Something is "
        "fundamentally wrong, and it's probably not the mathematics."
    ),
    PerformanceGrade.F: (
        "Catastrophic. The modulo operator has essentially given up. "
        "At this rate, you could compute FizzBuzz faster by hand. "
        "On paper. In cursive."
    ),
}


class LoadTestDashboard:
    """ASCII dashboard for load test results.

    Renders a comprehensive performance dashboard including a latency
    histogram, percentile table, bottleneck ranking, throughput metrics,
    and a performance grade with commentary. All rendered in glorious
    ASCII art, because Grafana costs money and this is a satirical
    FizzBuzz project.
    """

    @staticmethod
    def render(
        report: PerformanceReport,
        latencies_ms: Optional[list[float]] = None,
        width: int = 60,
        histogram_buckets: int = 10,
    ) -> str:
        """Render the complete load test dashboard."""
        lines: list[str] = []
        inner = width - 6

        # Header
        lines.append("")
        lines.append(f"  +{'=' * inner}+")
        lines.append(f"  | {'ENTERPRISE FIZZBUZZ LOAD TEST RESULTS':^{inner - 2}} |")
        lines.append(f"  +{'=' * inner}+")
        lines.append("")

        # Summary section
        lines.append(f"  +{'-' * inner}+")
        lines.append(f"  | {'Test Summary':^{inner - 2}} |")
        lines.append(f"  +{'-' * inner}+")
        lines.append(f"  | {'Profile:':<20} {report.profile_name:<{inner - 23}} |")
        lines.append(f"  | {'Virtual Users:':<20} {report.num_vus:<{inner - 23}} |")
        lines.append(f"  | {'Total Requests:':<20} {report.total_requests:<{inner - 23}} |")
        lines.append(f"  | {'Successful:':<20} {report.successful_requests:<{inner - 23}} |")
        lines.append(f"  | {'Failed:':<20} {report.failed_requests:<{inner - 23}} |")
        lines.append(f"  | {'Duration:':<20} {report.elapsed_seconds:.3f}s{' ' * max(0, inner - 28)} |")
        lines.append(f"  | {'Throughput:':<20} {report.requests_per_second:.1f} req/s{' ' * max(0, inner - 33)} |")
        err_pct = f"{report.error_rate * 100:.2f}%"
        lines.append(f"  | {'Error Rate:':<20} {err_pct:<{inner - 23}} |")
        lines.append(f"  +{'-' * inner}+")
        lines.append("")

        # Performance Grade
        grade_str = report.grade.value
        commentary = _GRADE_COMMENTARY.get(report.grade, "No commentary available.")

        lines.append(f"  +{'-' * inner}+")
        lines.append(f"  | {'PERFORMANCE GRADE':^{inner - 2}} |")
        lines.append(f"  +{'-' * inner}+")
        lines.append(f"  |{' ' * inner}|")

        grade_display = f"[ {grade_str} ]"
        lines.append(f"  | {grade_display:^{inner - 2}} |")
        lines.append(f"  |{' ' * inner}|")

        # Word-wrap commentary
        words = commentary.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 > inner - 6:
                lines.append(f"  |  {current_line:<{inner - 3}}|")
                current_line = word
            else:
                current_line = f"{current_line} {word}".strip()
        if current_line:
            lines.append(f"  |  {current_line:<{inner - 3}}|")

        lines.append(f"  |{' ' * inner}|")
        lines.append(f"  +{'-' * inner}+")
        lines.append("")

        # Percentile table
        lines.append(_render_percentile_table(report, width=width))

        # Histogram
        if latencies_ms:
            lines.append(
                _render_histogram(latencies_ms, width=width, num_buckets=histogram_buckets)
            )
        lines.append("")

        # Bottleneck ranking
        lines.append(_render_bottleneck_ranking(report.bottlenecks, width=width))
        lines.append("")

        # Footer
        lines.append(f"  +{'=' * inner}+")
        lines.append(f"  | {'END OF LOAD TEST REPORT':^{inner - 2}} |")
        lines.append(f"  | {'Remember: the modulo operator was never the bottleneck.':^{inner - 2}} |")
        lines.append(f"  +{'=' * inner}+")
        lines.append("")

        return "\n".join(lines)


# ================================================================
# Convenience function
# ================================================================

def run_load_test(
    profile: WorkloadProfile,
    rules: list[RuleDefinition],
    *,
    num_vus: Optional[int] = None,
    numbers_per_vu: Optional[int] = None,
    event_callback: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = 300,
) -> tuple[PerformanceReport, list[float]]:
    """Run a load test and return the performance report and raw latencies.

    This is the high-level convenience function that ties together the
    WorkloadSpec, LoadGenerator, and PerformanceReport. It's the
    enterprise equivalent of writing a for loop, but with 800 more
    lines of supporting infrastructure.
    """
    spec = get_workload_spec(
        profile,
        num_vus=num_vus,
        numbers_per_vu=numbers_per_vu,
    )

    generator = LoadGenerator(
        workload=spec,
        rules=rules,
        event_callback=event_callback,
        timeout_seconds=timeout_seconds,
    )

    metrics = generator.run()
    latencies_ms = [m.latency_ms for m in metrics]

    report = PerformanceReport.from_metrics(
        metrics,
        elapsed_seconds=generator.elapsed_seconds,
        profile_name=spec.profile.name,
        num_vus=spec.num_vus,
    )

    return report, latencies_ms

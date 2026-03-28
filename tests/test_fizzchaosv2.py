"""
Tests for FizzChaosV2: Advanced Chaos Engineering with Game Days and Steady-State Verification

Validates experiment lifecycle management, fault type coverage, steady-state
hypothesis verification against real metric thresholds, game day orchestration
with multi-experiment coordination, blast radius enforcement, dashboard
rendering, middleware pipeline integration, and factory wiring.
"""

import uuid
from unittest.mock import MagicMock, AsyncMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzchaosv2 import (
    # Constants
    FIZZCHAOSV2_VERSION,
    MIDDLEWARE_PRIORITY,
    # Enums
    ExperimentState,
    FaultType,
    # Dataclasses / Config
    FizzChaosV2Config,
    Experiment,
    GameDay,
    # Classes
    SteadyStateVerifier,
    ChaosEngine,
    FizzChaosV2Dashboard,
    FizzChaosV2Middleware,
    # Factory
    create_fizzchaosv2_subsystem,
)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are published with correct values."""

    def test_version_string(self):
        assert FIZZCHAOSV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 174


# ---------------------------------------------------------------------------
# TestChaosEngine
# ---------------------------------------------------------------------------

class TestChaosEngine:
    """Validate experiment lifecycle, game day orchestration, and statistics."""

    @pytest.fixture()
    def engine(self):
        return ChaosEngine()

    def test_create_experiment_returns_experiment(self, engine):
        """Creating an experiment returns a well-formed Experiment instance."""
        hypothesis = {"metric": "error_rate", "operator": "<", "threshold": 0.05}
        exp = engine.create_experiment(
            name="latency-spike",
            fault_type=FaultType.LATENCY,
            target="fizzbuzz-service",
            duration=30.0,
            blast_radius=0.5,
            hypothesis=hypothesis,
        )
        assert isinstance(exp, Experiment)
        assert exp.name == "latency-spike"
        assert exp.fault_type == FaultType.LATENCY
        assert exp.target == "fizzbuzz-service"
        assert exp.duration_seconds == 30.0
        assert exp.blast_radius == 0.5
        assert exp.steady_state_hypothesis == hypothesis
        assert exp.state == ExperimentState.PLANNED
        assert exp.experiment_id  # non-empty id

    def test_run_experiment_completes(self, engine):
        """Running a planned experiment transitions it to COMPLETED."""
        exp = engine.create_experiment(
            name="error-inject",
            fault_type=FaultType.ERROR,
            target="rule-engine",
            duration=1.0,
            blast_radius=0.1,
            hypothesis={"metric": "throughput", "operator": ">", "threshold": 100},
        )
        result = engine.run(exp.experiment_id)
        assert result.state == ExperimentState.COMPLETED

    def test_abort_experiment(self, engine):
        """Aborting an experiment transitions it to ABORTED state."""
        exp = engine.create_experiment(
            name="kill-test",
            fault_type=FaultType.KILL,
            target="worker-pool",
            duration=60.0,
            blast_radius=0.2,
            hypothesis={"metric": "uptime", "operator": ">", "threshold": 0.99},
        )
        engine.abort(exp.experiment_id)
        # Retrieve the experiment via listing and check state
        all_experiments = engine.list_experiments()
        aborted = [e for e in all_experiments if e.experiment_id == exp.experiment_id]
        assert len(aborted) == 1
        assert aborted[0].state == ExperimentState.ABORTED

    def test_blast_radius_respected(self, engine):
        """Blast radius is stored and enforced within the valid 0-1 range."""
        exp = engine.create_experiment(
            name="cpu-stress",
            fault_type=FaultType.CPU_STRESS,
            target="compute-node",
            duration=10.0,
            blast_radius=0.75,
            hypothesis={"metric": "cpu_utilization", "operator": "<", "threshold": 0.95},
        )
        assert 0.0 <= exp.blast_radius <= 1.0
        assert exp.blast_radius == 0.75

    def test_list_experiments(self, engine):
        """Listing experiments returns all created experiments."""
        engine.create_experiment(
            name="exp-a", fault_type=FaultType.LATENCY, target="svc-a",
            duration=5.0, blast_radius=0.1,
            hypothesis={"metric": "latency_p99", "operator": "<", "threshold": 500},
        )
        engine.create_experiment(
            name="exp-b", fault_type=FaultType.ERROR, target="svc-b",
            duration=5.0, blast_radius=0.2,
            hypothesis={"metric": "error_rate", "operator": "<", "threshold": 0.01},
        )
        experiments = engine.list_experiments()
        names = [e.name for e in experiments]
        assert "exp-a" in names
        assert "exp-b" in names
        assert len(experiments) >= 2

    def test_get_stats(self, engine):
        """Stats dict reports counts for total, completed, and aborted experiments."""
        exp1 = engine.create_experiment(
            name="stat-run", fault_type=FaultType.MEMORY_PRESSURE, target="mem-pool",
            duration=1.0, blast_radius=0.1,
            hypothesis={"metric": "memory_free", "operator": ">", "threshold": 100},
        )
        exp2 = engine.create_experiment(
            name="stat-abort", fault_type=FaultType.NETWORK_PARTITION, target="net-zone",
            duration=1.0, blast_radius=0.1,
            hypothesis={"metric": "packet_loss", "operator": "<", "threshold": 0.5},
        )
        engine.run(exp1.experiment_id)
        engine.abort(exp2.experiment_id)
        stats = engine.get_stats()
        assert isinstance(stats, dict)
        assert stats.get("total", 0) >= 2
        assert stats.get("completed", 0) >= 1
        assert stats.get("aborted", 0) >= 1

    def test_game_day_runs_all_experiments(self, engine):
        """A game day orchestrates multiple experiments and returns a GameDay record."""
        experiments = []
        for i in range(3):
            exp = engine.create_experiment(
                name=f"gd-exp-{i}",
                fault_type=FaultType.LATENCY,
                target=f"target-{i}",
                duration=1.0,
                blast_radius=0.1,
                hypothesis={"metric": "latency_ms", "operator": "<", "threshold": 1000},
            )
            experiments.append(exp.experiment_id)
        game_day = engine.run_game_day(name="quarterly-game-day", experiments=experiments)
        assert isinstance(game_day, GameDay)
        assert game_day.name == "quarterly-game-day"
        assert game_day.game_day_id  # non-empty
        assert game_day.started_at is not None
        assert game_day.completed_at is not None
        assert len(game_day.experiments) == 3

    def test_game_day_fails_if_experiment_fails(self, engine):
        """If any experiment in a game day fails, the game day is marked as not passed."""
        # Create one experiment with a hypothesis that will not be satisfied
        exp = engine.create_experiment(
            name="doomed-exp",
            fault_type=FaultType.ERROR,
            target="fragile-service",
            duration=1.0,
            blast_radius=1.0,
            hypothesis={"metric": "impossible_metric", "operator": ">", "threshold": 999999},
        )
        game_day = engine.run_game_day(name="failure-day", experiments=[exp.experiment_id])
        assert isinstance(game_day, GameDay)
        # A game day with a failing hypothesis should report passed=False
        assert game_day.passed is False


# ---------------------------------------------------------------------------
# TestSteadyStateVerifier
# ---------------------------------------------------------------------------

class TestSteadyStateVerifier:
    """Validate that the verifier actually compares metric values to thresholds."""

    @pytest.fixture()
    def verifier(self):
        return SteadyStateVerifier()

    def test_passes_when_metric_meets_threshold(self, verifier):
        """Verification succeeds when the metric satisfies the hypothesis operator."""
        hypothesis = {"metric": "error_rate", "operator": "<", "threshold": 0.05}
        metrics = {"error_rate": 0.01}
        passed, message = verifier.verify(hypothesis, metrics)
        assert passed is True
        assert isinstance(message, str)

    def test_fails_when_metric_violates_threshold(self, verifier):
        """Verification fails when the metric violates the hypothesis constraint."""
        hypothesis = {"metric": "latency_p99", "operator": "<", "threshold": 200}
        metrics = {"latency_p99": 350}
        passed, message = verifier.verify(hypothesis, metrics)
        assert passed is False
        assert isinstance(message, str)
        # The message should indicate something about the failure
        assert len(message) > 0

    def test_handles_missing_metric(self, verifier):
        """Verification fails gracefully when the requested metric is absent."""
        hypothesis = {"metric": "nonexistent_metric", "operator": ">", "threshold": 0}
        metrics = {"some_other_metric": 42}
        passed, message = verifier.verify(hypothesis, metrics)
        assert passed is False
        assert isinstance(message, str)


# ---------------------------------------------------------------------------
# TestFizzChaosV2Dashboard
# ---------------------------------------------------------------------------

class TestFizzChaosV2Dashboard:
    """Validate dashboard rendering produces meaningful output."""

    @pytest.fixture()
    def dashboard(self):
        engine = ChaosEngine()
        engine.create_experiment(
            name="dash-exp",
            fault_type=FaultType.LATENCY,
            target="dashboard-target",
            duration=5.0,
            blast_radius=0.3,
            hypothesis={"metric": "latency", "operator": "<", "threshold": 100},
        )
        return FizzChaosV2Dashboard(engine=engine)

    def test_render_returns_string(self, dashboard):
        """Dashboard render produces a non-empty string."""
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_chaos_info(self, dashboard):
        """Dashboard output includes chaos-relevant information."""
        output = dashboard.render()
        # Should reference chaos engineering concepts or experiment data
        output_lower = output.lower()
        assert any(
            term in output_lower
            for term in ["chaos", "experiment", "game day", "fault", "steady"]
        ), f"Dashboard output lacks chaos engineering terminology: {output[:200]}"


# ---------------------------------------------------------------------------
# TestFizzChaosV2Middleware
# ---------------------------------------------------------------------------

class TestFizzChaosV2Middleware:
    """Validate middleware interface conformance and pipeline integration."""

    @pytest.fixture()
    def middleware(self):
        return FizzChaosV2Middleware()

    def test_get_name(self, middleware):
        assert middleware.get_name() == "fizzchaosv2"

    def test_get_priority(self, middleware):
        assert middleware.get_priority() == 174

    def test_process_calls_next(self, middleware):
        """Middleware invokes the next handler in the pipeline."""
        ctx = MagicMock()
        next_handler = MagicMock()
        middleware.process(ctx, next_handler)
        next_handler.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Validate the factory function wires all components correctly."""

    def test_returns_tuple_of_three(self):
        result = create_fizzchaosv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_engine_works(self):
        engine, _dashboard, _middleware = create_fizzchaosv2_subsystem()
        assert isinstance(engine, ChaosEngine)
        # Engine should be functional
        exp = engine.create_experiment(
            name="factory-test",
            fault_type=FaultType.CPU_STRESS,
            target="factory-target",
            duration=1.0,
            blast_radius=0.1,
            hypothesis={"metric": "cpu", "operator": "<", "threshold": 0.9},
        )
        assert exp.state == ExperimentState.PLANNED

    def test_has_default_experiments(self):
        """Factory-created engine ships with pre-configured default experiments."""
        engine, _dashboard, _middleware = create_fizzchaosv2_subsystem()
        experiments = engine.list_experiments()
        assert len(experiments) > 0, "Factory should seed default experiments"

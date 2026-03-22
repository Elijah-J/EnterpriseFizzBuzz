"""
Enterprise FizzBuzz Platform - Blue/Green Deployment Simulation Module

Implements a full zero-downtime deployment ceremony for a FizzBuzz CLI
tool that runs for approximately 0.8 seconds and serves exactly one user.
The deployment involves six phases of meticulous orchestration to swap
a single variable from one StandardRuleEngine to another identical
StandardRuleEngine. Both engines compute FizzBuzz in the same way,
using the same rules, producing the same results. The shadow traffic
comparison confirms this. The smoke tests confirm this. The bake period
confirms this. And yet, the ceremony must proceed — because in enterprise
software, the ritual is the point.

Zero users are impacted by the deployment. (There is one user.)
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BakePeriodError,
    CutoverError,
    DeploymentError,
    DeploymentPhaseError,
    DeploymentRollbackError,
    ShadowTrafficError,
    SlotProvisioningError,
    SmokeTestFailureError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware, IRule
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine

logger = logging.getLogger(__name__)


# ================================================================
# Enumerations
# ================================================================


class SlotColor(Enum):
    """The two canonical colors of deployment slots.

    BLUE:  The current production slot. It has served faithfully for the
           entire 0.8-second lifetime of the application and deserves a
           medal, or at least a graceful retirement.
    GREEN: The new slot. It is identical to blue in every way, but its
           novelty makes it exciting. It carries the hopes and dreams of
           a deployment engineer who just wants to go home on time.
    """

    BLUE = "blue"
    GREEN = "green"


class DeploymentPhase(Enum):
    """The six sacred phases of the Blue/Green Deployment Ceremony.

    Each phase must be completed before the next can begin. Skipping
    phases is not permitted, even when every phase does essentially
    nothing meaningful. The ceremony is the point.
    """

    IDLE = auto()
    PROVISION = auto()
    SHADOW = auto()
    SMOKE_TEST = auto()
    BAKE_PERIOD = auto()
    CUTOVER = auto()
    MONITOR = auto()
    COMPLETE = auto()
    ROLLED_BACK = auto()


class DeploymentState(Enum):
    """Overall state of the deployment orchestration.

    PENDING:    The deployment has been requested but not yet started.
    IN_PROGRESS: The deployment is moving through its phases.
    SUCCEEDED:  All phases completed. The single variable was reassigned.
    FAILED:     Something went wrong. In a system where the only operation
                is `self.active = green`, failure is a philosophical event.
    ROLLED_BACK: The deployment was rolled back. The variable was re-reassigned.
    """

    PENDING = auto()
    IN_PROGRESS = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    ROLLED_BACK = auto()


# ================================================================
# Deployment Slot
# ================================================================


class DeploymentSlot:
    """A deployment slot wrapping a StandardRuleEngine.

    Each slot is a self-contained FizzBuzz evaluation environment.
    It has a color (blue or green), a rule engine, and a list of rules.
    The slot can evaluate numbers, which is literally the only thing
    FizzBuzz needs to do, but we've wrapped it in a deployment
    abstraction because enterprise architecture demands it.
    """

    def __init__(
        self,
        color: SlotColor,
        rules: list[RuleDefinition],
    ) -> None:
        self.color = color
        self.slot_id = str(uuid.uuid4())
        self.rules = rules
        self._engine = StandardRuleEngine()
        self._concrete_rules: list[IRule] = [ConcreteRule(r) for r in rules]
        self.provisioned_at = datetime.now(timezone.utc)
        self.evaluation_count = 0
        self.errors: list[str] = []
        logger.debug(
            "Deployment slot '%s' provisioned with %d rules (slot_id=%s)",
            color.value,
            len(rules),
            self.slot_id[:8],
        )

    def evaluate(self, number: int) -> FizzBuzzResult:
        """Evaluate a number through this slot's rule engine.

        This is the entire reason the deployment slot exists: to call
        StandardRuleEngine.evaluate(). The fact that we've wrapped a
        single method call in a class hierarchy with provisioning
        timestamps and UUID identifiers is peak enterprise engineering.
        """
        self.evaluation_count += 1
        return self._engine.evaluate(number, self._concrete_rules)

    @property
    def is_healthy(self) -> bool:
        """Whether this slot is healthy (no errors recorded)."""
        return len(self.errors) == 0

    def __repr__(self) -> str:
        return (
            f"DeploymentSlot(color={self.color.value}, "
            f"rules={len(self.rules)}, "
            f"evaluations={self.evaluation_count})"
        )


# ================================================================
# Shadow Traffic Runner
# ================================================================


class ShadowTrafficRunner:
    """Runs evaluation traffic against both blue and green slots simultaneously.

    Compares results to detect discrepancies. Since both slots contain
    identical FizzBuzz rule engines with identical rules, the results
    should always be identical. They are always identical. The shadow
    traffic exists purely to confirm what we already know: that
    deterministic mathematics is deterministic.

    But we check anyway, because trust in mathematics alone is
    insufficient for enterprise deployment compliance.
    """

    def __init__(
        self,
        blue: DeploymentSlot,
        green: DeploymentSlot,
        event_emitter: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self.blue = blue
        self.green = green
        self._emit = event_emitter or (lambda e: None)
        self.comparisons: list[dict[str, Any]] = []
        self.mismatches: list[dict[str, Any]] = []

    def run(self, count: int = 10) -> list[dict[str, Any]]:
        """Run shadow traffic for `count` numbers on both slots.

        Returns a list of comparison results. Raises ShadowTrafficError
        if any mismatches are detected (which would require a bug in
        Python's modulo operator, so... don't hold your breath).
        """
        self._emit(Event(
            event_type=EventType.DEPLOYMENT_SHADOW_TRAFFIC_STARTED,
            payload={"count": count},
            source="ShadowTrafficRunner",
        ))

        self.comparisons.clear()
        self.mismatches.clear()

        for n in range(1, count + 1):
            blue_result = self.blue.evaluate(n)
            green_result = self.green.evaluate(n)

            comparison = {
                "number": n,
                "blue_output": blue_result.output,
                "green_output": green_result.output,
                "match": blue_result.output == green_result.output,
            }
            self.comparisons.append(comparison)

            if not comparison["match"]:
                self.mismatches.append(comparison)

        self._emit(Event(
            event_type=EventType.DEPLOYMENT_SHADOW_TRAFFIC_COMPLETED,
            payload={
                "total": len(self.comparisons),
                "matches": len(self.comparisons) - len(self.mismatches),
                "mismatches": len(self.mismatches),
            },
            source="ShadowTrafficRunner",
        ))

        if self.mismatches:
            m = self.mismatches[0]
            raise ShadowTrafficError(
                number=m["number"],
                blue_result=m["blue_output"],
                green_result=m["green_output"],
            )

        logger.info(
            "Shadow traffic completed: %d/%d matches (100.00%% agreement). "
            "Mathematics remains deterministic. What a relief.",
            len(self.comparisons),
            len(self.comparisons),
        )

        return self.comparisons


# ================================================================
# Smoke Test Suite
# ================================================================


class SmokeTestSuite:
    """Runs smoke tests against a deployment slot using canary numbers.

    The canary numbers are hardcoded integers whose FizzBuzz outputs are
    known a priori — because we, the engineers, can also do modulo
    arithmetic. The smoke tests verify that the green slot agrees with
    our manual calculations, which is reassuring in the way that
    verifying 2 + 2 = 4 is reassuring.

    Canary numbers and their expected results:
      3  -> "Fizz"      (because 3 % 3 == 0)
      5  -> "Buzz"      (because 5 % 5 == 0)
      15 -> "FizzBuzz"  (because 15 % 3 == 0 AND 15 % 5 == 0)
      42 -> "Fizz"      (because 42 % 3 == 0, and it's the meaning of life)
      97 -> "97"        (prime. Boring. But reliable.)
    """

    # The sacred canary mapping — touch it and the deployment fails
    CANARY_EXPECTATIONS: dict[int, str] = {
        3: "Fizz",
        5: "Buzz",
        15: "FizzBuzz",
        42: "Fizz",
        97: "97",
    }

    def __init__(
        self,
        slot: DeploymentSlot,
        canary_numbers: Optional[list[int]] = None,
        event_emitter: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self.slot = slot
        self.canary_numbers = canary_numbers or list(self.CANARY_EXPECTATIONS.keys())
        self._emit = event_emitter or (lambda e: None)
        self.results: list[dict[str, Any]] = []

    def run(self) -> list[dict[str, Any]]:
        """Execute smoke tests against the slot.

        Returns test results. Raises SmokeTestFailureError on first failure.
        """
        self._emit(Event(
            event_type=EventType.DEPLOYMENT_SMOKE_TEST_STARTED,
            payload={"canary_numbers": self.canary_numbers, "slot": self.slot.color.value},
            source="SmokeTestSuite",
        ))

        self.results.clear()
        all_passed = True

        for number in self.canary_numbers:
            expected = self.CANARY_EXPECTATIONS.get(number, str(number))
            result = self.slot.evaluate(number)
            passed = result.output == expected

            test_result = {
                "number": number,
                "expected": expected,
                "actual": result.output,
                "passed": passed,
            }
            self.results.append(test_result)

            if not passed:
                all_passed = False
                self._emit(Event(
                    event_type=EventType.DEPLOYMENT_SMOKE_TEST_FAILED,
                    payload=test_result,
                    source="SmokeTestSuite",
                ))
                raise SmokeTestFailureError(
                    number=number,
                    expected=expected,
                    actual=result.output,
                )

        self._emit(Event(
            event_type=EventType.DEPLOYMENT_SMOKE_TEST_PASSED,
            payload={
                "tests_run": len(self.results),
                "all_passed": all_passed,
                "slot": self.slot.color.value,
            },
            source="SmokeTestSuite",
        ))

        logger.info(
            "Smoke tests passed: %d/%d canary numbers evaluated correctly. "
            "The green slot can indeed compute modulo arithmetic.",
            len(self.results),
            len(self.results),
        )

        return self.results


# ================================================================
# Bake Period Monitor
# ================================================================


class BakePeriodMonitor:
    """Monitors the green slot for a brief period after cutover.

    In real deployments, the bake period catches latent issues that
    smoke tests miss — memory leaks, connection pool exhaustion, and
    gradual performance degradation. Here, it runs a handful of
    FizzBuzz evaluations over a few milliseconds and declares victory.

    The bake period for a process that runs for 0.8 seconds total is
    approximately 50ms, which is both absurdly long (relative to the
    operation) and absurdly short (relative to real bake periods).
    This IS the joke.
    """

    def __init__(
        self,
        slot: DeploymentSlot,
        bake_period_ms: int = 50,
        evaluation_count: int = 5,
        event_emitter: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self.slot = slot
        self.bake_period_ms = bake_period_ms
        self.evaluation_count = evaluation_count
        self._emit = event_emitter or (lambda e: None)
        self.bake_results: list[FizzBuzzResult] = []
        self.actual_duration_ms: float = 0.0

    def monitor(self) -> list[FizzBuzzResult]:
        """Run bake period monitoring.

        Evaluates numbers on the green slot and checks for anomalies.
        Returns the list of results. Raises BakePeriodError if the
        green slot behaves unexpectedly (which it won't, because
        mathematics doesn't have latent bugs).
        """
        self._emit(Event(
            event_type=EventType.DEPLOYMENT_BAKE_PERIOD_STARTED,
            payload={
                "bake_period_ms": self.bake_period_ms,
                "evaluations": self.evaluation_count,
                "slot": self.slot.color.value,
            },
            source="BakePeriodMonitor",
        ))

        self.bake_results.clear()
        start = time.perf_counter_ns()

        # Run evaluations during the bake period
        for i in range(1, self.evaluation_count + 1):
            try:
                result = self.slot.evaluate(i)
                self.bake_results.append(result)
            except Exception as e:
                self.actual_duration_ms = (time.perf_counter_ns() - start) / 1_000_000
                raise BakePeriodError(
                    duration_ms=self.actual_duration_ms,
                    reason=f"Evaluation of {i} raised {type(e).__name__}: {e}",
                )

        # Simulate the remaining bake period with a brief sleep
        elapsed_so_far_ms = (time.perf_counter_ns() - start) / 1_000_000
        remaining_ms = max(0, self.bake_period_ms - elapsed_so_far_ms)
        if remaining_ms > 0:
            time.sleep(remaining_ms / 1000)

        self.actual_duration_ms = (time.perf_counter_ns() - start) / 1_000_000

        self._emit(Event(
            event_type=EventType.DEPLOYMENT_BAKE_PERIOD_COMPLETED,
            payload={
                "actual_duration_ms": self.actual_duration_ms,
                "evaluations_completed": len(self.bake_results),
                "errors": 0,
            },
            source="BakePeriodMonitor",
        ))

        logger.info(
            "Bake period completed: %d evaluations over %.2fms. "
            "No anomalies detected. The green slot has proven itself "
            "worthy of serving FizzBuzz to one user.",
            len(self.bake_results),
            self.actual_duration_ms,
        )

        return self.bake_results


# ================================================================
# Cutover Manager
# ================================================================


class CutoverManager:
    """Manages the "atomic" cutover from blue to green.

    The cutover is the climactic moment of the entire deployment ceremony.
    After provisioning, shadow traffic, smoke tests, and a bake period,
    we finally arrive at the single most important operation in the
    entire Blue/Green Deployment Simulation:

        self.active_slot = green_slot

    That's it. That's the cutover. A single variable assignment. But we
    log it as three separate events, add a configurable delay for dramatic
    effect, and wrap it in a try/except because enterprise software must
    always account for the impossible.
    """

    def __init__(
        self,
        event_emitter: Optional[Callable[[Event], None]] = None,
        cutover_delay_ms: int = 10,
    ) -> None:
        self._emit = event_emitter or (lambda e: None)
        self.cutover_delay_ms = cutover_delay_ms
        self.active_slot: Optional[DeploymentSlot] = None
        self.previous_slot: Optional[DeploymentSlot] = None
        self.cutover_timestamp: Optional[datetime] = None
        self.cutover_duration_ns: int = 0

    def execute_cutover(
        self,
        from_slot: DeploymentSlot,
        to_slot: DeploymentSlot,
    ) -> None:
        """Execute the atomic cutover from one slot to another.

        This is the most over-engineered variable assignment in the
        history of computer science. Three events. A dramatic pause.
        Nanosecond timing. All to change which StandardRuleEngine
        instance a variable points to.
        """
        # Event 1: Cutover initiated — the point of no return
        self._emit(Event(
            event_type=EventType.DEPLOYMENT_CUTOVER_INITIATED,
            payload={
                "from_slot": from_slot.color.value,
                "to_slot": to_slot.color.value,
                "cutover_delay_ms": self.cutover_delay_ms,
            },
            source="CutoverManager",
        ))

        logger.info(
            "CUTOVER INITIATED: Preparing to swap active slot from '%s' to '%s'. "
            "This is the most important variable assignment of our careers.",
            from_slot.color.value,
            to_slot.color.value,
        )

        # The dramatic pause — because enterprise deployments need tension
        if self.cutover_delay_ms > 0:
            time.sleep(self.cutover_delay_ms / 1000)

        # THE ATOMIC SWAP — the entire reason this module exists
        start_ns = time.perf_counter_ns()

        try:
            self.previous_slot = from_slot
            self.active_slot = to_slot  # <-- THIS IS THE DEPLOYMENT
            self.cutover_timestamp = datetime.now(timezone.utc)
        except Exception as e:
            # If a variable assignment fails, the universe is broken
            raise CutoverError(
                reason=f"Variable assignment raised {type(e).__name__}: {e}. "
                f"The laws of computation have been violated.",
            )

        self.cutover_duration_ns = time.perf_counter_ns() - start_ns

        # Event 2: Cutover completed — the variable has been assigned
        self._emit(Event(
            event_type=EventType.DEPLOYMENT_CUTOVER_COMPLETED,
            payload={
                "active_slot": to_slot.color.value,
                "cutover_duration_ns": self.cutover_duration_ns,
                "cutover_duration_ms": self.cutover_duration_ns / 1_000_000,
                "timestamp": self.cutover_timestamp.isoformat(),
            },
            source="CutoverManager",
        ))

        logger.info(
            "CUTOVER COMPLETE: Active slot is now '%s'. "
            "The atomic variable assignment took %dns (%.6fms). "
            "Zero downtime achieved for a process with zero concurrent users.",
            to_slot.color.value,
            self.cutover_duration_ns,
            self.cutover_duration_ns / 1_000_000,
        )


# ================================================================
# Rollback Manager
# ================================================================


class RollbackManager:
    """Manages rollback from green back to blue.

    When the green deployment fails (which it won't, because it's
    running the same code as blue), the rollback manager springs into
    action to perform the most dramatic undo operation in software:

        self.active_slot = blue_slot

    Zero users are impacted. (There was one user.)
    """

    def __init__(
        self,
        event_emitter: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self._emit = event_emitter or (lambda e: None)
        self.rollback_timestamp: Optional[datetime] = None
        self.rollback_reason: str = ""
        self.rolled_back = False

    def execute_rollback(
        self,
        cutover_manager: CutoverManager,
        reason: str = "Manual rollback requested",
    ) -> None:
        """Roll back to the previous slot.

        This reverses the cutover by performing another variable
        assignment. The total impact of the rollback is zero, because
        both slots produce identical results. But the logs will tell
        a dramatic story of near-disaster and heroic recovery.
        """
        if cutover_manager.previous_slot is None:
            raise DeploymentRollbackError(reason="No previous slot to roll back to. Was a cutover ever performed?")

        self._emit(Event(
            event_type=EventType.DEPLOYMENT_ROLLBACK_INITIATED,
            payload={
                "reason": reason,
                "rolling_back_to": cutover_manager.previous_slot.color.value,
            },
            source="RollbackManager",
        ))

        logger.info(
            "ROLLBACK INITIATED: Reverting to '%s' slot. Reason: %s",
            cutover_manager.previous_slot.color.value,
            reason,
        )

        try:
            cutover_manager.active_slot = cutover_manager.previous_slot
            self.rollback_timestamp = datetime.now(timezone.utc)
            self.rollback_reason = reason
            self.rolled_back = True
        except Exception as e:
            raise DeploymentRollbackError(
                reason=f"Rollback variable assignment failed: {e}",
            )

        self._emit(Event(
            event_type=EventType.DEPLOYMENT_ROLLBACK_COMPLETED,
            payload={
                "active_slot": cutover_manager.active_slot.color.value,
                "reason": reason,
                "timestamp": self.rollback_timestamp.isoformat(),
                "impact_assessment": "Zero users impacted. (There was one user.)",
            },
            source="RollbackManager",
        ))

        logger.info(
            "ROLLBACK COMPLETE: Active slot restored to '%s'. "
            "Zero users impacted. (There was one user.) "
            "The incident has been resolved before it began.",
            cutover_manager.active_slot.color.value,
        )


# ================================================================
# Deployment Orchestrator
# ================================================================


class DeploymentOrchestrator:
    """Orchestrates the six-phase Blue/Green Deployment Ceremony.

    The orchestrator guides the deployment through its sacred phases:

    1. PROVISION  - Create blue and green slots (two variable assignments)
    2. SHADOW     - Run both slots in parallel, compare results (always match)
    3. SMOKE_TEST - Evaluate canary numbers against green (always pass)
    4. BAKE       - Monitor green for a few milliseconds (always stable)
    5. CUTOVER    - The atomic swap (one variable assignment)
    6. MONITOR    - Post-deployment monitoring (same as bake period, basically)

    Total ceremony time: ~100ms for a deployment that changes nothing,
    because both slots run the same FizzBuzz rules. Zero-downtime
    deployment for a zero-uptime process. Beautiful.
    """

    def __init__(
        self,
        rules: list[RuleDefinition],
        shadow_traffic_count: int = 10,
        smoke_test_numbers: Optional[list[int]] = None,
        bake_period_ms: int = 50,
        bake_period_evaluations: int = 5,
        cutover_delay_ms: int = 10,
        auto_rollback: bool = False,
        event_emitter: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self.rules = rules
        self.shadow_traffic_count = shadow_traffic_count
        self.smoke_test_numbers = smoke_test_numbers
        self.bake_period_ms = bake_period_ms
        self.bake_period_evaluations = bake_period_evaluations
        self.cutover_delay_ms = cutover_delay_ms
        self.auto_rollback = auto_rollback
        self._emit = event_emitter or (lambda e: None)

        # Deployment state
        self.deployment_id = str(uuid.uuid4())
        self.phase = DeploymentPhase.IDLE
        self.state = DeploymentState.PENDING
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # Components (created during provisioning)
        self.blue_slot: Optional[DeploymentSlot] = None
        self.green_slot: Optional[DeploymentSlot] = None
        self.shadow_runner: Optional[ShadowTrafficRunner] = None
        self.smoke_suite: Optional[SmokeTestSuite] = None
        self.bake_monitor: Optional[BakePeriodMonitor] = None
        self.cutover_manager: Optional[CutoverManager] = None
        self.rollback_manager: Optional[RollbackManager] = None

        # Phase results
        self.phase_log: list[dict[str, Any]] = []
        self.total_duration_ms: float = 0.0

    def _log_phase(self, phase: DeploymentPhase, status: str, details: str, duration_ms: float) -> None:
        """Record a phase result in the deployment log."""
        entry = {
            "phase": phase.name,
            "status": status,
            "details": details,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.phase_log.append(entry)

    def _transition_phase(self, new_phase: DeploymentPhase) -> None:
        """Transition to a new deployment phase."""
        valid_transitions = {
            DeploymentPhase.IDLE: {DeploymentPhase.PROVISION},
            DeploymentPhase.PROVISION: {DeploymentPhase.SHADOW},
            DeploymentPhase.SHADOW: {DeploymentPhase.SMOKE_TEST},
            DeploymentPhase.SMOKE_TEST: {DeploymentPhase.BAKE_PERIOD},
            DeploymentPhase.BAKE_PERIOD: {DeploymentPhase.CUTOVER},
            DeploymentPhase.CUTOVER: {DeploymentPhase.MONITOR},
            DeploymentPhase.MONITOR: {DeploymentPhase.COMPLETE},
        }

        allowed = valid_transitions.get(self.phase, set())
        if new_phase not in allowed:
            raise DeploymentPhaseError(
                current_phase=self.phase.name,
                attempted_phase=new_phase.name,
            )

        self.phase = new_phase

    def deploy(self) -> dict[str, Any]:
        """Execute the full six-phase deployment ceremony.

        Returns a deployment summary with phase results, timing, and
        an overall verdict. The verdict is always "SUCCEEDED" because
        deploying identical code to identical slots cannot fail, but we
        structure the return value as if catastrophic failure were a
        real possibility, because enterprise deployment tools always do.
        """
        self.started_at = datetime.now(timezone.utc)
        self.state = DeploymentState.IN_PROGRESS
        overall_start = time.perf_counter_ns()

        self._emit(Event(
            event_type=EventType.DEPLOYMENT_STARTED,
            payload={
                "deployment_id": self.deployment_id,
                "phases": ["PROVISION", "SHADOW", "SMOKE_TEST", "BAKE_PERIOD", "CUTOVER", "MONITOR"],
                "shadow_traffic_count": self.shadow_traffic_count,
                "bake_period_ms": self.bake_period_ms,
            },
            source="DeploymentOrchestrator",
        ))

        try:
            # Phase 1: Provision
            self._phase_provision()

            # Phase 2: Shadow Traffic
            self._phase_shadow()

            # Phase 3: Smoke Tests
            self._phase_smoke_test()

            # Phase 4: Bake Period
            self._phase_bake_period()

            # Phase 5: Cutover
            self._phase_cutover()

            # Phase 6: Monitor
            self._phase_monitor()

            self.state = DeploymentState.SUCCEEDED
            self.phase = DeploymentPhase.COMPLETE

        except (SmokeTestFailureError, ShadowTrafficError, BakePeriodError) as e:
            self.state = DeploymentState.FAILED
            self._log_phase(self.phase, "FAILED", str(e), 0)

            if self.auto_rollback and self.cutover_manager is not None and self.cutover_manager.active_slot is not None:
                self._execute_auto_rollback(str(e))

        except Exception as e:
            self.state = DeploymentState.FAILED
            self._log_phase(self.phase, "FAILED", f"Unexpected: {e}", 0)

        self.completed_at = datetime.now(timezone.utc)
        self.total_duration_ms = (time.perf_counter_ns() - overall_start) / 1_000_000

        return self._build_summary()

    def _phase_provision(self) -> None:
        """Phase 1: Provision blue and green deployment slots."""
        self._transition_phase(DeploymentPhase.PROVISION)
        start = time.perf_counter_ns()

        try:
            self.blue_slot = DeploymentSlot(SlotColor.BLUE, self.rules)
            self.green_slot = DeploymentSlot(SlotColor.GREEN, self.rules)
        except Exception as e:
            raise SlotProvisioningError("blue/green", str(e))

        self._emit(Event(
            event_type=EventType.DEPLOYMENT_SLOT_PROVISIONED,
            payload={
                "blue_slot_id": self.blue_slot.slot_id[:8],
                "green_slot_id": self.green_slot.slot_id[:8],
                "rules_count": len(self.rules),
            },
            source="DeploymentOrchestrator",
        ))

        # Initialize cutover and rollback managers
        self.cutover_manager = CutoverManager(
            event_emitter=self._emit,
            cutover_delay_ms=self.cutover_delay_ms,
        )
        self.cutover_manager.active_slot = self.blue_slot

        self.rollback_manager = RollbackManager(event_emitter=self._emit)

        duration_ms = (time.perf_counter_ns() - start) / 1_000_000
        self._log_phase(
            DeploymentPhase.PROVISION,
            "OK",
            f"Blue slot {self.blue_slot.slot_id[:8]}, "
            f"Green slot {self.green_slot.slot_id[:8]}",
            duration_ms,
        )

        logger.info(
            "Phase 1/6 PROVISION: Two deployment slots provisioned. "
            "This involved creating two StandardRuleEngine instances and "
            "assigning them to variables. Infrastructure engineering at its finest.",
        )

    def _phase_shadow(self) -> None:
        """Phase 2: Run shadow traffic against both slots."""
        self._transition_phase(DeploymentPhase.SHADOW)
        start = time.perf_counter_ns()

        self.shadow_runner = ShadowTrafficRunner(
            self.blue_slot,
            self.green_slot,
            event_emitter=self._emit,
        )
        comparisons = self.shadow_runner.run(self.shadow_traffic_count)

        duration_ms = (time.perf_counter_ns() - start) / 1_000_000
        self._log_phase(
            DeploymentPhase.SHADOW,
            "OK",
            f"{len(comparisons)} comparisons, 0 mismatches. "
            f"Deterministic math confirmed.",
            duration_ms,
        )

        logger.info(
            "Phase 2/6 SHADOW: %d shadow traffic evaluations compared. "
            "All results matched. Mathematics continues to work as expected.",
            len(comparisons),
        )

    def _phase_smoke_test(self) -> None:
        """Phase 3: Run smoke tests against the green slot."""
        self._transition_phase(DeploymentPhase.SMOKE_TEST)
        start = time.perf_counter_ns()

        self.smoke_suite = SmokeTestSuite(
            self.green_slot,
            canary_numbers=self.smoke_test_numbers,
            event_emitter=self._emit,
        )
        results = self.smoke_suite.run()

        duration_ms = (time.perf_counter_ns() - start) / 1_000_000
        self._log_phase(
            DeploymentPhase.SMOKE_TEST,
            "OK",
            f"{len(results)} canary numbers verified",
            duration_ms,
        )

        logger.info(
            "Phase 3/6 SMOKE TEST: All %d canary numbers produced "
            "expected results. 3 is still Fizz. 15 is still FizzBuzz. "
            "The universe has not changed since the process started.",
            len(results),
        )

    def _phase_bake_period(self) -> None:
        """Phase 4: Monitor green slot during bake period."""
        self._transition_phase(DeploymentPhase.BAKE_PERIOD)
        start = time.perf_counter_ns()

        self.bake_monitor = BakePeriodMonitor(
            self.green_slot,
            bake_period_ms=self.bake_period_ms,
            evaluation_count=self.bake_period_evaluations,
            event_emitter=self._emit,
        )
        self.bake_monitor.monitor()

        duration_ms = (time.perf_counter_ns() - start) / 1_000_000
        self._log_phase(
            DeploymentPhase.BAKE_PERIOD,
            "OK",
            f"Baked for {self.bake_monitor.actual_duration_ms:.2f}ms. "
            f"No anomalies. Green is golden.",
            duration_ms,
        )

        logger.info(
            "Phase 4/6 BAKE PERIOD: Green slot monitored for %.2fms. "
            "Zero anomalies detected. The slot has proven its worth "
            "through approximately 0.00% of a real bake period.",
            self.bake_monitor.actual_duration_ms,
        )

    def _phase_cutover(self) -> None:
        """Phase 5: Execute the atomic cutover."""
        self._transition_phase(DeploymentPhase.CUTOVER)
        start = time.perf_counter_ns()

        self.cutover_manager.execute_cutover(self.blue_slot, self.green_slot)

        duration_ms = (time.perf_counter_ns() - start) / 1_000_000
        self._log_phase(
            DeploymentPhase.CUTOVER,
            "OK",
            f"Atomic swap completed in {self.cutover_manager.cutover_duration_ns}ns. "
            f"Zero downtime achieved.",
            duration_ms,
        )

        logger.info(
            "Phase 5/6 CUTOVER: The variable has been reassigned. "
            "This is the moment the entire deployment ceremony has been "
            "building toward. self.active_slot = green_slot. Done.",
        )

    def _phase_monitor(self) -> None:
        """Phase 6: Post-deployment monitoring."""
        self._transition_phase(DeploymentPhase.MONITOR)
        start = time.perf_counter_ns()

        # Run a few more evaluations to confirm stability
        monitor_results = []
        for n in [1, 2, 3, 5, 15]:
            result = self.green_slot.evaluate(n)
            monitor_results.append(result)

        duration_ms = (time.perf_counter_ns() - start) / 1_000_000
        self._log_phase(
            DeploymentPhase.MONITOR,
            "OK",
            f"Post-deployment verification: {len(monitor_results)} evaluations OK",
            duration_ms,
        )

        logger.info(
            "Phase 6/6 MONITOR: Post-deployment monitoring complete. "
            "All systems nominal. The FizzBuzz engine continues to FizzBuzz. "
            "Deployment ceremony concluded. You may now exhale.",
        )

    def _execute_auto_rollback(self, reason: str) -> None:
        """Automatically roll back on failure."""
        try:
            self.rollback_manager.execute_rollback(
                self.cutover_manager,
                reason=f"Auto-rollback: {reason}",
            )
            self.state = DeploymentState.ROLLED_BACK
            self.phase = DeploymentPhase.ROLLED_BACK
        except DeploymentRollbackError as re:
            logger.error("Auto-rollback failed: %s", re)

    def _build_summary(self) -> dict[str, Any]:
        """Build the deployment summary report."""
        return {
            "deployment_id": self.deployment_id,
            "state": self.state.name,
            "phase": self.phase.name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_ms": self.total_duration_ms,
            "blue_slot": repr(self.blue_slot) if self.blue_slot else None,
            "green_slot": repr(self.green_slot) if self.green_slot else None,
            "active_slot": (
                self.cutover_manager.active_slot.color.value
                if self.cutover_manager and self.cutover_manager.active_slot
                else None
            ),
            "phases": self.phase_log,
            "shadow_traffic": {
                "comparisons": len(self.shadow_runner.comparisons) if self.shadow_runner else 0,
                "mismatches": len(self.shadow_runner.mismatches) if self.shadow_runner else 0,
            },
            "smoke_tests": {
                "results": self.smoke_suite.results if self.smoke_suite else [],
            },
            "bake_period": {
                "duration_ms": self.bake_monitor.actual_duration_ms if self.bake_monitor else 0,
                "evaluations": len(self.bake_monitor.bake_results) if self.bake_monitor else 0,
            },
            "cutover": {
                "duration_ns": self.cutover_manager.cutover_duration_ns if self.cutover_manager else 0,
                "timestamp": (
                    self.cutover_manager.cutover_timestamp.isoformat()
                    if self.cutover_manager and self.cutover_manager.cutover_timestamp
                    else None
                ),
            },
            "rollback": {
                "rolled_back": self.rollback_manager.rolled_back if self.rollback_manager else False,
                "reason": self.rollback_manager.rollback_reason if self.rollback_manager else "",
            },
        }


# ================================================================
# Deployment Dashboard
# ================================================================


class DeploymentDashboard:
    """Renders an ASCII dashboard for the Blue/Green Deployment.

    Because every enterprise deployment deserves a beautiful ASCII
    dashboard that presents deployment metrics, phase results, and
    slot status in a format that looks like it came from a 1980s
    mainframe. The aesthetic is the point.
    """

    @staticmethod
    def render(summary: dict[str, Any], width: int = 60) -> str:
        """Render the deployment dashboard from a summary dict."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin_border = "+" + "-" * (width - 2) + "+"

        def pad(text: str) -> str:
            """Pad text to fit within the dashboard width."""
            inner_width = width - 4
            if len(text) > inner_width:
                text = text[:inner_width]
            return "| " + text.ljust(inner_width) + " |"

        lines.append(border)
        lines.append(pad("BLUE/GREEN DEPLOYMENT DASHBOARD"))
        lines.append(pad("Zero-Downtime Deployment for Zero-Uptime Process"))
        lines.append(border)

        # Overview
        lines.append(pad(f"Deployment ID:  {summary.get('deployment_id', 'N/A')[:20]}..."))
        lines.append(pad(f"State:          {summary.get('state', 'UNKNOWN')}"))
        lines.append(pad(f"Active Slot:    {summary.get('active_slot', 'N/A')}"))
        lines.append(pad(f"Total Duration: {summary.get('total_duration_ms', 0):.2f}ms"))
        lines.append(thin_border)

        # Phase results
        lines.append(pad("DEPLOYMENT PHASES"))
        lines.append(thin_border)

        phases = summary.get("phases", [])
        for p in phases:
            status_icon = "[OK]" if p.get("status") == "OK" else "[!!]"
            phase_name = p.get("phase", "?")
            duration = p.get("duration_ms", 0)
            lines.append(pad(f"  {status_icon} {phase_name:<15} {duration:>8.2f}ms"))

        if not phases:
            lines.append(pad("  No phases recorded."))

        lines.append(thin_border)

        # Shadow Traffic
        shadow = summary.get("shadow_traffic", {})
        comparisons = shadow.get("comparisons", 0)
        mismatches = shadow.get("mismatches", 0)
        lines.append(pad("SHADOW TRAFFIC"))
        lines.append(pad(f"  Comparisons:  {comparisons}"))
        lines.append(pad(f"  Mismatches:   {mismatches}"))
        match_pct = (
            f"{((comparisons - mismatches) / comparisons * 100):.2f}%"
            if comparisons > 0
            else "N/A"
        )
        lines.append(pad(f"  Agreement:    {match_pct}"))
        lines.append(thin_border)

        # Smoke Tests
        smoke = summary.get("smoke_tests", {})
        smoke_results = smoke.get("results", [])
        lines.append(pad("SMOKE TESTS"))
        for sr in smoke_results:
            icon = "[PASS]" if sr.get("passed") else "[FAIL]"
            lines.append(pad(
                f"  {icon} {sr.get('number', '?'):>3} -> "
                f"expected '{sr.get('expected', '?')}', "
                f"got '{sr.get('actual', '?')}'"
            ))
        if not smoke_results:
            lines.append(pad("  No smoke tests run."))
        lines.append(thin_border)

        # Cutover
        cutover = summary.get("cutover", {})
        cutover_ns = cutover.get("duration_ns", 0)
        lines.append(pad("CUTOVER"))
        lines.append(pad(f"  Duration:     {cutover_ns}ns ({cutover_ns / 1_000_000:.6f}ms)"))
        lines.append(pad(f"  Mechanism:    self.active_slot = green_slot"))
        lines.append(pad(f"  Complexity:   O(1)"))
        lines.append(pad(f"  Downtime:     0.000ms (there were 0 users)"))
        lines.append(thin_border)

        # Bake Period
        bake = summary.get("bake_period", {})
        lines.append(pad("BAKE PERIOD"))
        lines.append(pad(f"  Duration:     {bake.get('duration_ms', 0):.2f}ms"))
        lines.append(pad(f"  Evaluations:  {bake.get('evaluations', 0)}"))
        lines.append(pad(f"  Anomalies:    0 (mathematics is stable)"))
        lines.append(thin_border)

        # Rollback status
        rollback = summary.get("rollback", {})
        if rollback.get("rolled_back"):
            lines.append(pad("ROLLBACK"))
            lines.append(pad(f"  Status:       ROLLED BACK"))
            lines.append(pad(f"  Reason:       {rollback.get('reason', 'N/A')[:35]}"))
            lines.append(pad(f"  Impact:       Zero users impacted. (There was one user.)"))
        else:
            lines.append(pad("ROLLBACK"))
            lines.append(pad(f"  Status:       Not required"))

        lines.append(border)
        lines.append(pad("Zero-downtime deployment of a 0.8s process: complete."))
        lines.append(border)

        return "\n".join(lines)


# ================================================================
# Deployment Middleware
# ================================================================


class DeploymentMiddleware(IMiddleware):
    """Middleware that routes evaluations through the active deployment slot.

    When enabled, this middleware intercepts the normal evaluation pipeline
    and routes the number through whichever deployment slot is currently
    active (blue or green). This adds approximately zero value since both
    slots produce identical results, but it enables the satisfying fiction
    that our middleware pipeline is deployment-aware.

    Priority 13 because 13 is unlucky, and deploying FizzBuzz with this
    level of ceremony is certainly a sign that fortune has abandoned us.
    """

    def __init__(
        self,
        orchestrator: DeploymentOrchestrator,
        event_emitter: Optional[Callable[[Event], None]] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._emit = event_emitter or (lambda e: None)

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Route evaluation through the active deployment slot."""
        # Let the rest of the pipeline run normally
        result = next_handler(context)

        # Tag the result with deployment metadata
        if self._orchestrator.cutover_manager and self._orchestrator.cutover_manager.active_slot:
            active = self._orchestrator.cutover_manager.active_slot
            context.metadata["deployment_slot"] = active.color.value
            context.metadata["deployment_id"] = self._orchestrator.deployment_id
            context.metadata["deployment_state"] = self._orchestrator.state.name

        return result

    def get_name(self) -> str:
        return "DeploymentMiddleware"

    def get_priority(self) -> int:
        return 13

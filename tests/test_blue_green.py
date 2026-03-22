"""
Tests for the Blue/Green Deployment Simulation Module.

These tests verify that the most over-engineered variable assignment
in the history of computer science works correctly. Every test confirms
what we already know: FizzBuzz produces deterministic results regardless
of which deployment slot evaluates the number. But we test anyway,
because enterprise software without tests is just enterprise software
that hasn't been caught yet.
"""

from __future__ import annotations

import unittest

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
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.blue_green import (
    BakePeriodMonitor,
    CutoverManager,
    DeploymentDashboard,
    DeploymentMiddleware,
    DeploymentOrchestrator,
    DeploymentPhase,
    DeploymentSlot,
    DeploymentState,
    RollbackManager,
    ShadowTrafficRunner,
    SlotColor,
    SmokeTestSuite,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# Standard FizzBuzz rules used across all tests
FIZZBUZZ_RULES = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
]


class TestSlotColor(unittest.TestCase):
    """Tests for the SlotColor enumeration."""

    def test_blue_value(self):
        self.assertEqual(SlotColor.BLUE.value, "blue")

    def test_green_value(self):
        self.assertEqual(SlotColor.GREEN.value, "green")

    def test_two_colors_only(self):
        self.assertEqual(len(SlotColor), 2)


class TestDeploymentPhase(unittest.TestCase):
    """Tests for the DeploymentPhase enumeration."""

    def test_all_phases_exist(self):
        expected = {
            "IDLE", "PROVISION", "SHADOW", "SMOKE_TEST",
            "BAKE_PERIOD", "CUTOVER", "MONITOR", "COMPLETE", "ROLLED_BACK",
        }
        actual = {p.name for p in DeploymentPhase}
        self.assertEqual(expected, actual)


class TestDeploymentState(unittest.TestCase):
    """Tests for the DeploymentState enumeration."""

    def test_all_states_exist(self):
        expected = {"PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED", "ROLLED_BACK"}
        actual = {s.name for s in DeploymentState}
        self.assertEqual(expected, actual)


class TestDeploymentSlot(unittest.TestCase):
    """Tests for the DeploymentSlot — the most over-engineered variable wrapper."""

    def test_slot_creation_blue(self):
        slot = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        self.assertEqual(slot.color, SlotColor.BLUE)
        self.assertEqual(len(slot.rules), 2)
        self.assertTrue(slot.is_healthy)
        self.assertEqual(slot.evaluation_count, 0)

    def test_slot_creation_green(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        self.assertEqual(slot.color, SlotColor.GREEN)

    def test_slot_evaluate_fizz(self):
        slot = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        result = slot.evaluate(3)
        self.assertEqual(result.output, "Fizz")
        self.assertEqual(slot.evaluation_count, 1)

    def test_slot_evaluate_buzz(self):
        slot = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        result = slot.evaluate(5)
        self.assertEqual(result.output, "Buzz")

    def test_slot_evaluate_fizzbuzz(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        result = slot.evaluate(15)
        self.assertEqual(result.output, "FizzBuzz")

    def test_slot_evaluate_plain_number(self):
        slot = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        result = slot.evaluate(7)
        self.assertEqual(result.output, "7")

    def test_slot_evaluate_increments_count(self):
        slot = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        slot.evaluate(1)
        slot.evaluate(2)
        slot.evaluate(3)
        self.assertEqual(slot.evaluation_count, 3)

    def test_slot_has_uuid(self):
        slot = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        self.assertTrue(len(slot.slot_id) > 0)

    def test_slot_repr(self):
        slot = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        self.assertIn("blue", repr(slot))

    def test_slot_provisioned_at(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        self.assertIsNotNone(slot.provisioned_at)


class TestShadowTrafficRunner(unittest.TestCase):
    """Tests for the ShadowTrafficRunner — confirming mathematics is deterministic."""

    def test_shadow_traffic_all_match(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        runner = ShadowTrafficRunner(blue, green)
        results = runner.run(count=10)
        self.assertEqual(len(results), 10)
        self.assertTrue(all(r["match"] for r in results))
        self.assertEqual(len(runner.mismatches), 0)

    def test_shadow_traffic_emits_events(self):
        events = []
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        runner = ShadowTrafficRunner(blue, green, event_emitter=events.append)
        runner.run(count=5)
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.DEPLOYMENT_SHADOW_TRAFFIC_STARTED, event_types)
        self.assertIn(EventType.DEPLOYMENT_SHADOW_TRAFFIC_COMPLETED, event_types)

    def test_shadow_traffic_count_zero(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        runner = ShadowTrafficRunner(blue, green)
        results = runner.run(count=0)
        self.assertEqual(len(results), 0)

    def test_shadow_traffic_evaluates_both_slots(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        runner = ShadowTrafficRunner(blue, green)
        runner.run(count=5)
        self.assertEqual(blue.evaluation_count, 5)
        self.assertEqual(green.evaluation_count, 5)


class TestSmokeTestSuite(unittest.TestCase):
    """Tests for the SmokeTestSuite — because 3 is still Fizz."""

    def test_all_canaries_pass(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        suite = SmokeTestSuite(slot)
        results = suite.run()
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r["passed"] for r in results))

    def test_canary_3_is_fizz(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        suite = SmokeTestSuite(slot)
        results = suite.run()
        fizz_result = next(r for r in results if r["number"] == 3)
        self.assertEqual(fizz_result["actual"], "Fizz")
        self.assertTrue(fizz_result["passed"])

    def test_canary_15_is_fizzbuzz(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        suite = SmokeTestSuite(slot)
        results = suite.run()
        fb_result = next(r for r in results if r["number"] == 15)
        self.assertEqual(fb_result["actual"], "FizzBuzz")

    def test_canary_97_is_plain(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        suite = SmokeTestSuite(slot)
        results = suite.run()
        plain_result = next(r for r in results if r["number"] == 97)
        self.assertEqual(plain_result["actual"], "97")

    def test_custom_canary_numbers(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        suite = SmokeTestSuite(slot, canary_numbers=[3, 5])
        results = suite.run()
        self.assertEqual(len(results), 2)

    def test_emits_passed_event(self):
        events = []
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        suite = SmokeTestSuite(slot, event_emitter=events.append)
        suite.run()
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.DEPLOYMENT_SMOKE_TEST_STARTED, event_types)
        self.assertIn(EventType.DEPLOYMENT_SMOKE_TEST_PASSED, event_types)


class TestBakePeriodMonitor(unittest.TestCase):
    """Tests for the BakePeriodMonitor — milliseconds of observation."""

    def test_bake_period_completes(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        monitor = BakePeriodMonitor(slot, bake_period_ms=1, evaluation_count=3)
        results = monitor.monitor()
        self.assertEqual(len(results), 3)
        self.assertGreater(monitor.actual_duration_ms, 0)

    def test_bake_period_emits_events(self):
        events = []
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        monitor = BakePeriodMonitor(slot, bake_period_ms=1, evaluation_count=2, event_emitter=events.append)
        monitor.monitor()
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.DEPLOYMENT_BAKE_PERIOD_STARTED, event_types)
        self.assertIn(EventType.DEPLOYMENT_BAKE_PERIOD_COMPLETED, event_types)

    def test_bake_period_zero_evaluations(self):
        slot = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        monitor = BakePeriodMonitor(slot, bake_period_ms=1, evaluation_count=0)
        results = monitor.monitor()
        self.assertEqual(len(results), 0)


class TestCutoverManager(unittest.TestCase):
    """Tests for the CutoverManager — the climactic variable assignment."""

    def test_cutover_swaps_active_slot(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        mgr = CutoverManager(cutover_delay_ms=0)
        mgr.active_slot = blue
        mgr.execute_cutover(blue, green)
        self.assertEqual(mgr.active_slot.color, SlotColor.GREEN)

    def test_cutover_records_previous_slot(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        mgr = CutoverManager(cutover_delay_ms=0)
        mgr.execute_cutover(blue, green)
        self.assertEqual(mgr.previous_slot.color, SlotColor.BLUE)

    def test_cutover_records_timestamp(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        mgr = CutoverManager(cutover_delay_ms=0)
        mgr.execute_cutover(blue, green)
        self.assertIsNotNone(mgr.cutover_timestamp)

    def test_cutover_records_duration(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        mgr = CutoverManager(cutover_delay_ms=0)
        mgr.execute_cutover(blue, green)
        self.assertGreater(mgr.cutover_duration_ns, 0)

    def test_cutover_emits_events(self):
        events = []
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        mgr = CutoverManager(event_emitter=events.append, cutover_delay_ms=0)
        mgr.execute_cutover(blue, green)
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.DEPLOYMENT_CUTOVER_INITIATED, event_types)
        self.assertIn(EventType.DEPLOYMENT_CUTOVER_COMPLETED, event_types)


class TestRollbackManager(unittest.TestCase):
    """Tests for the RollbackManager — undoing a variable assignment."""

    def test_rollback_restores_blue(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        cutover = CutoverManager(cutover_delay_ms=0)
        cutover.execute_cutover(blue, green)
        self.assertEqual(cutover.active_slot.color, SlotColor.GREEN)

        rollback = RollbackManager()
        rollback.execute_rollback(cutover, reason="Testing rollback")
        self.assertEqual(cutover.active_slot.color, SlotColor.BLUE)
        self.assertTrue(rollback.rolled_back)

    def test_rollback_records_reason(self):
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        cutover = CutoverManager(cutover_delay_ms=0)
        cutover.execute_cutover(blue, green)

        rollback = RollbackManager()
        rollback.execute_rollback(cutover, reason="Green was too green")
        self.assertEqual(rollback.rollback_reason, "Green was too green")

    def test_rollback_without_cutover_raises(self):
        cutover = CutoverManager(cutover_delay_ms=0)
        rollback = RollbackManager()
        with self.assertRaises(DeploymentRollbackError):
            rollback.execute_rollback(cutover, reason="No cutover happened")

    def test_rollback_emits_events(self):
        events = []
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        cutover = CutoverManager(cutover_delay_ms=0)
        cutover.execute_cutover(blue, green)

        rollback = RollbackManager(event_emitter=events.append)
        rollback.execute_rollback(cutover, reason="Rollback test")
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.DEPLOYMENT_ROLLBACK_INITIATED, event_types)
        self.assertIn(EventType.DEPLOYMENT_ROLLBACK_COMPLETED, event_types)

    def test_rollback_completed_event_includes_impact(self):
        events = []
        blue = DeploymentSlot(SlotColor.BLUE, FIZZBUZZ_RULES)
        green = DeploymentSlot(SlotColor.GREEN, FIZZBUZZ_RULES)
        cutover = CutoverManager(cutover_delay_ms=0)
        cutover.execute_cutover(blue, green)

        rollback = RollbackManager(event_emitter=events.append)
        rollback.execute_rollback(cutover, reason="Impact check")
        completed_event = next(
            e for e in events
            if e.event_type == EventType.DEPLOYMENT_ROLLBACK_COMPLETED
        )
        self.assertIn("Zero users impacted", completed_event.payload["impact_assessment"])
        self.assertIn("There was one user", completed_event.payload["impact_assessment"])


class TestDeploymentOrchestrator(unittest.TestCase):
    """Tests for the DeploymentOrchestrator — the six-phase ceremony."""

    def test_full_deployment_succeeds(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            shadow_traffic_count=5,
            bake_period_ms=1,
            bake_period_evaluations=2,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        self.assertEqual(summary["state"], "SUCCEEDED")
        self.assertEqual(summary["active_slot"], "green")

    def test_deployment_has_six_phases(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            shadow_traffic_count=3,
            bake_period_ms=1,
            bake_period_evaluations=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        self.assertEqual(len(summary["phases"]), 6)

    def test_deployment_all_phases_ok(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            shadow_traffic_count=3,
            bake_period_ms=1,
            bake_period_evaluations=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        for phase in summary["phases"]:
            self.assertEqual(phase["status"], "OK")

    def test_deployment_records_duration(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            shadow_traffic_count=3,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        self.assertGreater(summary["total_duration_ms"], 0)

    def test_deployment_has_deployment_id(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES, cutover_delay_ms=0, bake_period_ms=1)
        summary = orch.deploy()
        self.assertTrue(len(summary["deployment_id"]) > 0)

    def test_deployment_shadow_traffic_stats(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            shadow_traffic_count=7,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        self.assertEqual(summary["shadow_traffic"]["comparisons"], 7)
        self.assertEqual(summary["shadow_traffic"]["mismatches"], 0)

    def test_deployment_smoke_test_results(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        smoke_results = summary["smoke_tests"]["results"]
        self.assertEqual(len(smoke_results), 5)
        self.assertTrue(all(r["passed"] for r in smoke_results))

    def test_deployment_cutover_recorded(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        self.assertGreater(summary["cutover"]["duration_ns"], 0)
        self.assertIsNotNone(summary["cutover"]["timestamp"])

    def test_deployment_emits_started_event(self):
        events = []
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            bake_period_ms=1,
            cutover_delay_ms=0,
            event_emitter=events.append,
        )
        orch.deploy()
        event_types = [e.event_type for e in events]
        self.assertIn(EventType.DEPLOYMENT_STARTED, event_types)

    def test_deployment_initial_state_is_pending(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES)
        self.assertEqual(orch.state, DeploymentState.PENDING)
        self.assertEqual(orch.phase, DeploymentPhase.IDLE)

    def test_deployment_custom_smoke_test_numbers(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            smoke_test_numbers=[3, 15],
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        smoke_results = summary["smoke_tests"]["results"]
        self.assertEqual(len(smoke_results), 2)


class TestDeploymentDashboard(unittest.TestCase):
    """Tests for the DeploymentDashboard — ASCII art for a variable assignment."""

    def test_dashboard_renders_string(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        dashboard = DeploymentDashboard.render(summary, width=60)
        self.assertIsInstance(dashboard, str)
        self.assertGreater(len(dashboard), 0)

    def test_dashboard_contains_key_sections(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        dashboard = DeploymentDashboard.render(summary, width=60)
        self.assertIn("BLUE/GREEN DEPLOYMENT DASHBOARD", dashboard)
        self.assertIn("SHADOW TRAFFIC", dashboard)
        self.assertIn("SMOKE TESTS", dashboard)
        self.assertIn("CUTOVER", dashboard)
        self.assertIn("BAKE PERIOD", dashboard)
        self.assertIn("ROLLBACK", dashboard)

    def test_dashboard_shows_deployment_state(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        dashboard = DeploymentDashboard.render(summary, width=60)
        self.assertIn("SUCCEEDED", dashboard)

    def test_dashboard_shows_zero_downtime(self):
        orch = DeploymentOrchestrator(
            rules=FIZZBUZZ_RULES,
            bake_period_ms=1,
            cutover_delay_ms=0,
        )
        summary = orch.deploy()
        dashboard = DeploymentDashboard.render(summary, width=60)
        self.assertIn("0 users", dashboard)

    def test_dashboard_with_rollback(self):
        summary = {
            "deployment_id": "test-123",
            "state": "ROLLED_BACK",
            "active_slot": "blue",
            "total_duration_ms": 42.0,
            "phases": [],
            "shadow_traffic": {"comparisons": 0, "mismatches": 0},
            "smoke_tests": {"results": []},
            "cutover": {"duration_ns": 0, "timestamp": None},
            "bake_period": {"duration_ms": 0, "evaluations": 0},
            "rollback": {"rolled_back": True, "reason": "Test rollback"},
        }
        dashboard = DeploymentDashboard.render(summary, width=60)
        self.assertIn("ROLLED BACK", dashboard)
        self.assertIn("Zero users impacted", dashboard)


class TestDeploymentMiddleware(unittest.TestCase):
    """Tests for the DeploymentMiddleware — priority 13, unlucky but functional."""

    def test_middleware_priority_is_13(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES, cutover_delay_ms=0, bake_period_ms=1)
        mw = DeploymentMiddleware(orch)
        self.assertEqual(mw.get_priority(), 13)

    def test_middleware_name(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES, cutover_delay_ms=0, bake_period_ms=1)
        mw = DeploymentMiddleware(orch)
        self.assertEqual(mw.get_name(), "DeploymentMiddleware")

    def test_middleware_passes_through(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES, cutover_delay_ms=0, bake_period_ms=1)
        orch.deploy()
        mw = DeploymentMiddleware(orch)

        context = ProcessingContext(number=15, session_id="test-session")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        self.assertEqual(result.number, 15)

    def test_middleware_adds_deployment_metadata(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES, cutover_delay_ms=0, bake_period_ms=1)
        orch.deploy()
        mw = DeploymentMiddleware(orch)

        context = ProcessingContext(number=3, session_id="test-session")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        self.assertIn("deployment_slot", result.metadata)
        self.assertIn("deployment_id", result.metadata)
        self.assertEqual(result.metadata["deployment_state"], "SUCCEEDED")


class TestExceptions(unittest.TestCase):
    """Tests for the Blue/Green Deployment exception hierarchy."""

    def test_deployment_error_base(self):
        err = DeploymentError("test error")
        self.assertIn("EFP-BG00", str(err))

    def test_slot_provisioning_error(self):
        err = SlotProvisioningError("green", "out of RAM (just kidding)")
        self.assertIn("EFP-BG01", str(err))
        self.assertIn("green", str(err))

    def test_shadow_traffic_error(self):
        err = ShadowTrafficError(15, "FizzBuzz", "CrashBoom")
        self.assertIn("EFP-BG02", str(err))
        self.assertIn("15", str(err))

    def test_smoke_test_failure_error(self):
        err = SmokeTestFailureError(3, "Fizz", "Buzz")
        self.assertIn("EFP-BG03", str(err))

    def test_bake_period_error(self):
        err = BakePeriodError(42.0, "anomaly detected")
        self.assertIn("EFP-BG04", str(err))

    def test_cutover_error(self):
        err = CutoverError("variable assignment failed somehow")
        self.assertIn("EFP-BG05", str(err))

    def test_rollback_error(self):
        err = DeploymentRollbackError("cannot roll back")
        self.assertIn("EFP-BG06", str(err))
        self.assertIn("Zero users impacted", str(err))

    def test_deployment_phase_error(self):
        err = DeploymentPhaseError("IDLE", "CUTOVER")
        self.assertIn("EFP-BG07", str(err))
        self.assertIn("IDLE", str(err))
        self.assertIn("CUTOVER", str(err))


class TestEventTypes(unittest.TestCase):
    """Tests for the deployment-related EventType entries."""

    def test_deployment_event_types_exist(self):
        deployment_events = [
            EventType.DEPLOYMENT_STARTED,
            EventType.DEPLOYMENT_SLOT_PROVISIONED,
            EventType.DEPLOYMENT_SHADOW_TRAFFIC_STARTED,
            EventType.DEPLOYMENT_SHADOW_TRAFFIC_COMPLETED,
            EventType.DEPLOYMENT_SMOKE_TEST_STARTED,
            EventType.DEPLOYMENT_SMOKE_TEST_PASSED,
            EventType.DEPLOYMENT_SMOKE_TEST_FAILED,
            EventType.DEPLOYMENT_BAKE_PERIOD_STARTED,
            EventType.DEPLOYMENT_BAKE_PERIOD_COMPLETED,
            EventType.DEPLOYMENT_CUTOVER_INITIATED,
            EventType.DEPLOYMENT_CUTOVER_COMPLETED,
            EventType.DEPLOYMENT_ROLLBACK_INITIATED,
            EventType.DEPLOYMENT_ROLLBACK_COMPLETED,
            EventType.DEPLOYMENT_DASHBOARD_RENDERED,
        ]
        for evt in deployment_events:
            self.assertIsNotNone(evt)


class TestDeploymentPhaseTransitions(unittest.TestCase):
    """Tests for deployment phase transition validation."""

    def test_invalid_phase_transition_raises(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES, cutover_delay_ms=0, bake_period_ms=1)
        with self.assertRaises(DeploymentPhaseError):
            orch._transition_phase(DeploymentPhase.CUTOVER)

    def test_valid_first_transition(self):
        orch = DeploymentOrchestrator(rules=FIZZBUZZ_RULES, cutover_delay_ms=0, bake_period_ms=1)
        orch._transition_phase(DeploymentPhase.PROVISION)
        self.assertEqual(orch.phase, DeploymentPhase.PROVISION)


if __name__ == "__main__":
    unittest.main()

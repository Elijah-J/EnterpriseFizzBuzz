"""
Enterprise FizzBuzz Platform - Chaos Engineering / Fault Injection Framework

Implements a production-grade chaos engineering system for stress-testing
the FizzBuzz evaluation pipeline. Because if Netflix can have a Chaos
Monkey that randomly terminates production instances, the Enterprise
FizzBuzz Platform deserves one that randomly corrupts modulo results.

The framework supports five categories of fault injection:
    - Result Corruption: Silently changes FizzBuzz outputs to wrong values
    - Latency Injection: Adds artificial delays to simulate network issues
    - Exception Injection: Throws exceptions mid-pipeline to test error handling
    - Rule Engine Failure: Causes the rule evaluation engine to malfunction
    - Confidence Manipulation: Tampers with ML confidence scores

Each fault type has configurable severity levels (1-5), where level 1 is
a gentle nudge and level 5 is the equivalent of handing a toddler the
production database credentials.

Design Patterns Employed:
    - Strategy Pattern (fault injectors)
    - Singleton (ChaosMonkey)
    - Middleware (ChaosMiddleware)
    - Observer (event publication)
    - Template Method (game day scenarios)

Compliance:
    - ISO 22301: Business Continuity through proactive failure testing
    - SOC 2 Type II: Demonstrable resilience of the FizzBuzz pipeline
    - PCI DSS: Because corrupted FizzBuzz results are a payment risk, somehow
"""

from __future__ import annotations

import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from exceptions import (
    ChaosConfigurationError,
    ChaosError,
    ChaosExperimentFailedError,
    ChaosInducedFizzBuzzError,
    ResultCorruptionDetectedError,
)
from interfaces import IMiddleware
from models import Event, EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Fault Type and Severity Enums
# ============================================================


class FaultType(Enum):
    """The five horsemen of the FizzBuzz apocalypse.

    Each fault type represents a different category of chaos that can
    be unleashed upon the unsuspecting FizzBuzz pipeline. Choose wisely,
    or don't — that's kind of the point of chaos engineering.
    """

    RESULT_CORRUPTION = auto()
    LATENCY_INJECTION = auto()
    EXCEPTION_INJECTION = auto()
    RULE_ENGINE_FAILURE = auto()
    CONFIDENCE_MANIPULATION = auto()


class FaultSeverity(Enum):
    """Severity levels for fault injection, mapped to injection probabilities.

    Level 1: A gentle breeze. 5% chance of fault per evaluation.
             Your system barely notices.
    Level 2: A stiff wind. 15% chance. Systems start to sweat.
    Level 3: A proper storm. 30% chance. Dashboards light up.
    Level 4: A hurricane. 50% chance. Engineers get paged.
    Level 5: The apocalypse. 80% chance. Update your resume.
    """

    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3
    LEVEL_4 = 4
    LEVEL_5 = 5

    @property
    def probability(self) -> float:
        """Return the fault injection probability for this severity level."""
        return {
            1: 0.05,
            2: 0.15,
            3: 0.30,
            4: 0.50,
            5: 0.80,
        }[self.value]

    @property
    def label(self) -> str:
        """Return a human-readable label for this severity level."""
        return {
            1: "Gentle Breeze",
            2: "Stiff Wind",
            3: "Proper Storm",
            4: "Hurricane",
            5: "Apocalypse",
        }[self.value]


# ============================================================
# Chaos Event (Fault Injection Record)
# ============================================================


@dataclass(frozen=True)
class ChaosEvent:
    """An immutable record of a single fault injection incident.

    Every act of chaos is meticulously documented for the post-mortem,
    because even destruction deserves an audit trail.

    Attributes:
        fault_type: The category of fault that was injected.
        severity: The severity level at the time of injection.
        number: The number being evaluated when chaos struck.
        timestamp: When the chaos occurred (UTC).
        description: A human-readable description of what happened.
        metadata: Additional context about the injected fault.
    """

    fault_type: FaultType
    severity: FaultSeverity
    number: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Fault Injector (Strategy Pattern)
# ============================================================


class FaultInjector(ABC):
    """Abstract base class for fault injection strategies.

    Each concrete injector knows how to break the FizzBuzz pipeline
    in its own unique and special way. Think of them as artisanal
    failure modes, hand-crafted with love and malice.
    """

    @abstractmethod
    def inject(
        self,
        context: ProcessingContext,
        rng: random.Random,
        severity: FaultSeverity,
        **kwargs: Any,
    ) -> ChaosEvent:
        """Inject a fault into the processing context.

        Args:
            context: The current processing context to sabotage.
            rng: Seeded random number generator for reproducibility.
            severity: How badly to break things.

        Returns:
            A ChaosEvent documenting the atrocity committed.
        """
        ...

    @abstractmethod
    def get_fault_type(self) -> FaultType:
        """Return the fault type this injector produces."""
        ...


class ResultCorruptionInjector(FaultInjector):
    """Corrupts FizzBuzz results by replacing outputs with wrong values.

    Takes a perfectly valid FizzBuzz result and replaces it with
    something incorrect. 'Fizz' becomes 'Buzz'. '7' becomes 'FizzBuzz'.
    The modulo operator weeps silently.
    """

    # The chaos monkey's dictionary of lies
    _CORRUPTION_MAP = {
        "Fizz": ["Buzz", "FizzBuzz", "Bazz", "Fuzz", "Enterprise"],
        "Buzz": ["Fizz", "FizzBuzz", "Bozz", "Jazz", "Synergy"],
        "FizzBuzz": ["Fizz", "Buzz", "BuzzFizz", "FazzBozz", "Agile"],
    }

    def inject(
        self,
        context: ProcessingContext,
        rng: random.Random,
        severity: FaultSeverity,
        **kwargs: Any,
    ) -> ChaosEvent:
        if not context.results:
            return ChaosEvent(
                fault_type=FaultType.RESULT_CORRUPTION,
                severity=severity,
                number=context.number,
                description="No results to corrupt — the monkey is disappointed.",
            )

        latest = context.results[-1]
        original_output = latest.output

        if original_output in self._CORRUPTION_MAP:
            corrupted = rng.choice(self._CORRUPTION_MAP[original_output])
        else:
            # For plain numbers, replace with a random FizzBuzz label
            corrupted = rng.choice(["Fizz", "Buzz", "FizzBuzz"])

        latest.output = corrupted
        latest.metadata["chaos_corrupted"] = True
        latest.metadata["chaos_original_output"] = original_output

        return ChaosEvent(
            fault_type=FaultType.RESULT_CORRUPTION,
            severity=severity,
            number=context.number,
            description=(
                f"Result corrupted: '{original_output}' -> '{corrupted}'. "
                f"Mathematics has been overruled by chaos."
            ),
            metadata={"original": original_output, "corrupted": corrupted},
        )

    def get_fault_type(self) -> FaultType:
        return FaultType.RESULT_CORRUPTION


class LatencyInjector(FaultInjector):
    """Injects artificial latency to simulate slow downstream services.

    Because if computing n % 3 completes in nanoseconds, how will your
    timeout and circuit breaker logic ever get tested? This injector
    adds random delays to ensure your FizzBuzz evaluation pipeline can
    handle the unbearable slowness of being.
    """

    def __init__(self, min_ms: float = 10.0, max_ms: float = 500.0) -> None:
        self._min_ms = min_ms
        self._max_ms = max_ms

    def inject(
        self,
        context: ProcessingContext,
        rng: random.Random,
        severity: FaultSeverity,
        **kwargs: Any,
    ) -> ChaosEvent:
        # Higher severity = longer delays
        severity_multiplier = severity.value
        adjusted_max = self._min_ms + (self._max_ms - self._min_ms) * (severity_multiplier / 5.0)
        delay_ms = rng.uniform(self._min_ms, adjusted_max)
        delay_seconds = delay_ms / 1000.0

        time.sleep(delay_seconds)

        context.metadata["chaos_latency_ms"] = delay_ms

        return ChaosEvent(
            fault_type=FaultType.LATENCY_INJECTION,
            severity=severity,
            number=context.number,
            description=(
                f"Injected {delay_ms:.1f}ms of artificial latency. "
                f"The modulo operator took a coffee break."
            ),
            metadata={"delay_ms": delay_ms},
        )

    def get_fault_type(self) -> FaultType:
        return FaultType.LATENCY_INJECTION


class ExceptionInjector(FaultInjector):
    """Throws random exceptions into the pipeline to test error handling.

    The most direct form of chaos: simply throw an exception and see
    what happens. If your error handling works, the system recovers
    gracefully. If not, well, you've learned something valuable about
    your FizzBuzz platform's resilience — or lack thereof.
    """

    _EXCEPTION_MESSAGES = [
        "The FizzBuzz quantum entanglement field has collapsed.",
        "Modulo operator has achieved sentience and refuses to cooperate.",
        "Division by zero detected in a universe where zero doesn't exist.",
        "The Fizz-to-Buzz ratio has exceeded thermodynamic limits.",
        "A cosmic ray flipped a bit in the modulo coprocessor.",
        "The number you are trying to evaluate is currently on vacation.",
        "FizzBuzz entropy has reached maximum — heat death of the pipeline.",
        "The rule engine encountered an opinion it disagrees with.",
    ]

    def inject(
        self,
        context: ProcessingContext,
        rng: random.Random,
        severity: FaultSeverity,
        **kwargs: Any,
    ) -> ChaosEvent:
        message = rng.choice(self._EXCEPTION_MESSAGES)

        event = ChaosEvent(
            fault_type=FaultType.EXCEPTION_INJECTION,
            severity=severity,
            number=context.number,
            description=f"Exception injected: {message}",
            metadata={"exception_message": message},
        )

        raise ChaosInducedFizzBuzzError(
            context.number,
            context.results[-1].output if context.results else "N/A",
            f"CHAOS: {message}",
        )

    def get_fault_type(self) -> FaultType:
        return FaultType.EXCEPTION_INJECTION


class RuleEngineFailureInjector(FaultInjector):
    """Simulates rule engine failures by clearing matched rules.

    Instead of outright crashing, this injector is more subtle: it
    wipes the matched rules from the result, causing the output to
    default to the plain number. Fizz 3 becomes just '3'. The rule
    engine appears to work, but it's secretly broken — much like
    most enterprise software.
    """

    def inject(
        self,
        context: ProcessingContext,
        rng: random.Random,
        severity: FaultSeverity,
        **kwargs: Any,
    ) -> ChaosEvent:
        if not context.results:
            return ChaosEvent(
                fault_type=FaultType.RULE_ENGINE_FAILURE,
                severity=severity,
                number=context.number,
                description="No results to sabotage — rule engine was already empty.",
            )

        latest = context.results[-1]
        original_output = latest.output
        original_rules_count = len(latest.matched_rules)

        # Clear matched rules and reset output to plain number
        latest.matched_rules.clear()
        latest.output = str(context.number)
        latest.metadata["chaos_rule_engine_failed"] = True
        latest.metadata["chaos_original_output"] = original_output

        return ChaosEvent(
            fault_type=FaultType.RULE_ENGINE_FAILURE,
            severity=severity,
            number=context.number,
            description=(
                f"Rule engine sabotaged: cleared {original_rules_count} matched rules. "
                f"'{original_output}' reverted to '{context.number}'. "
                f"The modulo operator has been silenced."
            ),
            metadata={
                "original_output": original_output,
                "rules_cleared": original_rules_count,
            },
        )

    def get_fault_type(self) -> FaultType:
        return FaultType.RULE_ENGINE_FAILURE


class ConfidenceManipulationInjector(FaultInjector):
    """Tampers with ML confidence scores to trigger degradation detection.

    If your FizzBuzz platform uses ML-based evaluation (and why wouldn't
    it?), this injector reduces the confidence scores to dangerously low
    levels. This can trigger the circuit breaker's degradation detection,
    causing a cascade of protective responses — all because the chaos
    monkey decided that the neural network shouldn't be so sure about
    whether 15 is divisible by 3.
    """

    def inject(
        self,
        context: ProcessingContext,
        rng: random.Random,
        severity: FaultSeverity,
        **kwargs: Any,
    ) -> ChaosEvent:
        if not context.results:
            return ChaosEvent(
                fault_type=FaultType.CONFIDENCE_MANIPULATION,
                severity=severity,
                number=context.number,
                description="No results to manipulate confidence on.",
            )

        latest = context.results[-1]

        # Set artificially low confidence scores
        max_confidence = 1.0 - (severity.value * 0.15)  # L1=0.85, L5=0.25
        manipulated_confidence = rng.uniform(0.01, max(0.02, max_confidence))

        original_confidences = latest.metadata.get("ml_confidences", {})
        latest.metadata["ml_confidences"] = {
            rule: manipulated_confidence for rule in (original_confidences or {"default": 1.0})
        }
        latest.metadata["chaos_confidence_manipulated"] = True
        latest.metadata["chaos_original_confidences"] = original_confidences

        return ChaosEvent(
            fault_type=FaultType.CONFIDENCE_MANIPULATION,
            severity=severity,
            number=context.number,
            description=(
                f"ML confidence manipulated to {manipulated_confidence:.4f}. "
                f"The neural network is now deeply uncertain about basic arithmetic."
            ),
            metadata={
                "manipulated_confidence": manipulated_confidence,
                "original_confidences": original_confidences,
            },
        )

    def get_fault_type(self) -> FaultType:
        return FaultType.CONFIDENCE_MANIPULATION


# ============================================================
# Chaos Monkey (Singleton Orchestrator)
# ============================================================


class ChaosMonkey:
    """The Chaos Monkey: orchestrator of deliberate FizzBuzz destruction.

    Manages a registry of fault injectors, decides when and how to
    inject faults based on severity configuration, and maintains a
    detailed log of all chaos events for post-mortem analysis.

    The ChaosMonkey is a singleton because there can be only one
    agent of chaos per FizzBuzz evaluation session. Multiple monkeys
    would cause chaos in the chaos system, and we're not ready for
    that level of meta-instability.

    Thread Safety:
        All operations are protected by a threading lock because
        even chaos must be thread-safe. Concurrent chaos without
        synchronization is just a race condition.
    """

    _instance: Optional[ChaosMonkey] = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        severity: FaultSeverity = FaultSeverity.LEVEL_1,
        seed: Optional[int] = None,
        armed_fault_types: Optional[list[FaultType]] = None,
        latency_min_ms: float = 10.0,
        latency_max_ms: float = 500.0,
        event_bus: Any = None,
    ) -> None:
        self._severity = severity
        self._rng = random.Random(seed)
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._events: list[ChaosEvent] = []
        self._enabled = True
        self._total_injections = 0
        self._total_evaluations = 0

        # Build injector registry
        self._injectors: dict[FaultType, FaultInjector] = {
            FaultType.RESULT_CORRUPTION: ResultCorruptionInjector(),
            FaultType.LATENCY_INJECTION: LatencyInjector(
                min_ms=latency_min_ms, max_ms=latency_max_ms
            ),
            FaultType.EXCEPTION_INJECTION: ExceptionInjector(),
            FaultType.RULE_ENGINE_FAILURE: RuleEngineFailureInjector(),
            FaultType.CONFIDENCE_MANIPULATION: ConfidenceManipulationInjector(),
        }

        # Arm only specified fault types (default: all)
        if armed_fault_types is not None:
            self._armed_types = set(armed_fault_types)
        else:
            self._armed_types = set(FaultType)

        logger.info(
            "Chaos Monkey initialized: severity=%s (p=%.2f), seed=%s, armed=%s",
            severity.label,
            severity.probability,
            seed,
            [ft.name for ft in self._armed_types],
        )

    @classmethod
    def get_instance(cls) -> Optional[ChaosMonkey]:
        """Return the singleton instance, or None if not initialized."""
        with cls._instance_lock:
            return cls._instance

    @classmethod
    def initialize(cls, **kwargs: Any) -> ChaosMonkey:
        """Initialize the singleton ChaosMonkey instance."""
        with cls._instance_lock:
            cls._instance = ChaosMonkey(**kwargs)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton instance. Used for testing."""
        with cls._instance_lock:
            cls._instance = None

    @property
    def severity(self) -> FaultSeverity:
        return self._severity

    @property
    def events(self) -> list[ChaosEvent]:
        """Return a copy of all recorded chaos events."""
        with self._lock:
            return list(self._events)

    @property
    def total_injections(self) -> int:
        with self._lock:
            return self._total_injections

    @property
    def total_evaluations(self) -> int:
        with self._lock:
            return self._total_evaluations

    @property
    def injection_rate(self) -> float:
        """Return the actual injection rate (injections / evaluations)."""
        with self._lock:
            if self._total_evaluations == 0:
                return 0.0
            return self._total_injections / self._total_evaluations

    def _record_evaluation(self) -> None:
        """Increment the evaluation counter. Used by ChaosMiddleware."""
        with self._lock:
            self._total_evaluations += 1

    def should_inject(self) -> bool:
        """Decide whether to inject a fault based on severity probability.

        Uses the seeded RNG for reproducible chaos — because random
        chaos is only useful if you can reproduce it in your test suite.
        """
        if not self._enabled:
            return False
        return self._rng.random() < self._severity.probability

    def select_fault_type(self) -> FaultType:
        """Randomly select a fault type from the armed set."""
        armed_list = list(self._armed_types)
        return self._rng.choice(armed_list)

    def inject_fault(
        self,
        context: ProcessingContext,
        fault_type: Optional[FaultType] = None,
    ) -> Optional[ChaosEvent]:
        """Inject a fault into the given processing context.

        Args:
            context: The processing context to sabotage.
            fault_type: Specific fault type to inject, or None for random.

        Returns:
            A ChaosEvent if a fault was injected, None otherwise.
        """
        with self._lock:
            self._total_evaluations += 1

        if fault_type is None:
            fault_type = self.select_fault_type()

        if fault_type not in self._armed_types:
            return None

        injector = self._injectors.get(fault_type)
        if injector is None:
            return None

        chaos_event = injector.inject(
            context, self._rng, self._severity
        )

        with self._lock:
            self._events.append(chaos_event)
            self._total_injections += 1

        # Publish to event bus
        self._publish_event(EventType.CHAOS_FAULT_INJECTED, {
            "fault_type": fault_type.name,
            "severity": self._severity.label,
            "number": context.number,
            "description": chaos_event.description,
        })

        logger.warning(
            "CHAOS MONKEY [%s] number=%d: %s",
            fault_type.name,
            context.number,
            chaos_event.description,
        )

        return chaos_event

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Publish an event to the event bus, if available."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="ChaosMonkey",
            ))

    def get_summary(self) -> dict[str, Any]:
        """Generate a summary of all chaos activities."""
        with self._lock:
            fault_counts: dict[str, int] = {}
            for event in self._events:
                key = event.fault_type.name
                fault_counts[key] = fault_counts.get(key, 0) + 1

            return {
                "total_evaluations": self._total_evaluations,
                "total_injections": self._total_injections,
                "injection_rate": self.injection_rate,
                "severity": self._severity.label,
                "severity_level": self._severity.value,
                "armed_fault_types": [ft.name for ft in self._armed_types],
                "fault_counts": fault_counts,
                "events": len(self._events),
            }


# ============================================================
# Chaos Middleware
# ============================================================


class ChaosMiddleware(IMiddleware):
    """Middleware that injects chaos into the FizzBuzz evaluation pipeline.

    Runs INSIDE the circuit breaker (priority 3, higher than CB's -1),
    so that chaos-induced failures are detected by the circuit breaker
    as real failures. This is the key integration point: when the
    Chaos Monkey throws exceptions or adds latency, the circuit breaker
    sees these as genuine downstream failures and may trip — exactly
    as it would in a real production incident.

    The middleware operates in two phases:
        PRE-EVALUATION: Exception injection and latency injection occur
                        BEFORE the next handler runs. This simulates
                        upstream failures and network delays.
        POST-EVALUATION: Result corruption and confidence manipulation
                         occur AFTER the next handler runs. This simulates
                         silent data corruption and model degradation.

    Priority: 3 (runs after circuit breaker at -1, after validation at 0,
              after timing at 1, after logging at 2)
    """

    _PRE_EVAL_FAULTS = {FaultType.EXCEPTION_INJECTION, FaultType.LATENCY_INJECTION}
    _POST_EVAL_FAULTS = {
        FaultType.RESULT_CORRUPTION,
        FaultType.RULE_ENGINE_FAILURE,
        FaultType.CONFIDENCE_MANIPULATION,
    }

    def __init__(self, chaos_monkey: ChaosMonkey) -> None:
        self._monkey = chaos_monkey

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context with potential chaos injection.

        Pre-eval faults (exceptions, latency) fire before next_handler.
        Post-eval faults (corruption, confidence) fire after next_handler.
        """
        # PRE-EVALUATION chaos: exceptions and latency
        if self._monkey.should_inject():
            fault_type = self._monkey.select_fault_type()
            if fault_type in self._PRE_EVAL_FAULTS:
                # This may raise ChaosInducedFizzBuzzError (exception injection)
                # or add latency (latency injection)
                self._monkey.inject_fault(context, fault_type)
            else:
                # Not a pre-eval fault type; we'll check post-eval instead
                # but still count the evaluation
                self._monkey._record_evaluation()
                result = next_handler(context)
                # POST-EVALUATION chaos
                self._monkey.inject_fault(result, fault_type)
                return result

        # Normal processing (no pre-eval fault triggered)
        result = next_handler(context)

        # POST-EVALUATION chaos: independent roll for post-eval faults
        if self._monkey.should_inject():
            fault_type = self._monkey.select_fault_type()
            if fault_type in self._POST_EVAL_FAULTS:
                self._monkey.inject_fault(result, fault_type)

        return result

    def get_name(self) -> str:
        return "ChaosMiddleware"

    def get_priority(self) -> int:
        # Must run INSIDE the circuit breaker (CB is -1, we are 3)
        return 3


# ============================================================
# Game Day Scenarios
# ============================================================


@dataclass
class GameDayPhase:
    """A single phase in a Game Day chaos experiment.

    Each phase defines what fault types to inject, at what severity,
    and for how long (measured in number of evaluations, not time,
    because enterprise FizzBuzz operates on its own temporal plane).

    Attributes:
        name: Human-readable phase name.
        fault_types: Which fault types to arm during this phase.
        severity: The severity level for this phase.
        duration_evals: How many evaluations this phase lasts.
        description: Satirical description of what this phase tests.
    """

    name: str
    fault_types: list[FaultType]
    severity: FaultSeverity
    duration_evals: int
    description: str = ""


@dataclass
class GameDayScenario:
    """A structured chaos experiment with multiple phases.

    Game Days are the enterprise equivalent of 'let's see what happens
    when we break things on purpose.' Each scenario defines a sequence
    of phases with escalating (or de-escalating) chaos levels.

    Attributes:
        name: Scenario identifier.
        description: What this scenario tests.
        phases: Ordered list of phases to execute.
    """

    name: str
    description: str
    phases: list[GameDayPhase]


class GameDayRunner:
    """Orchestrates multi-phase chaos experiments (Game Days).

    In real Site Reliability Engineering, a Game Day is a planned
    exercise where teams deliberately inject failures into production
    systems to test resilience. In the Enterprise FizzBuzz Platform,
    it's an excuse to watch the Chaos Monkey systematically dismantle
    modulo arithmetic while generating impressive-looking incident reports.

    Pre-built scenarios:
        - modulo_meltdown: Escalating rule engine failures
        - confidence_crisis: ML confidence degradation spiral
        - slow_burn: Progressive latency injection
        - total_chaos: All fault types at maximum severity
    """

    # Pre-built scenarios
    SCENARIOS: dict[str, GameDayScenario] = {
        "modulo_meltdown": GameDayScenario(
            name="Modulo Meltdown",
            description=(
                "Simulates a progressive failure of the modulo operator, "
                "starting with occasional rule engine glitches and escalating "
                "to complete arithmetic collapse."
            ),
            phases=[
                GameDayPhase(
                    name="Phase 1: Intermittent Glitches",
                    fault_types=[FaultType.RULE_ENGINE_FAILURE],
                    severity=FaultSeverity.LEVEL_1,
                    duration_evals=10,
                    description="Occasional modulo hiccups. Most results are correct.",
                ),
                GameDayPhase(
                    name="Phase 2: Escalating Failures",
                    fault_types=[FaultType.RULE_ENGINE_FAILURE, FaultType.RESULT_CORRUPTION],
                    severity=FaultSeverity.LEVEL_3,
                    duration_evals=10,
                    description="The modulo operator is having a bad day.",
                ),
                GameDayPhase(
                    name="Phase 3: Total Meltdown",
                    fault_types=[FaultType.RULE_ENGINE_FAILURE, FaultType.EXCEPTION_INJECTION],
                    severity=FaultSeverity.LEVEL_5,
                    duration_evals=5,
                    description="Mathematics itself has broken. God help us all.",
                ),
            ],
        ),
        "confidence_crisis": GameDayScenario(
            name="Confidence Crisis",
            description=(
                "The ML model's confidence scores plummet as it questions "
                "its fundamental understanding of divisibility. Designed to "
                "trigger circuit breaker degradation detection."
            ),
            phases=[
                GameDayPhase(
                    name="Phase 1: Wavering Confidence",
                    fault_types=[FaultType.CONFIDENCE_MANIPULATION],
                    severity=FaultSeverity.LEVEL_2,
                    duration_evals=15,
                    description="The neural network begins to doubt itself.",
                ),
                GameDayPhase(
                    name="Phase 2: Existential Doubt",
                    fault_types=[FaultType.CONFIDENCE_MANIPULATION, FaultType.RESULT_CORRUPTION],
                    severity=FaultSeverity.LEVEL_4,
                    duration_evals=10,
                    description="Is 15 divisible by 3? The model is no longer sure.",
                ),
            ],
        ),
        "slow_burn": GameDayScenario(
            name="Slow Burn",
            description=(
                "Progressive latency injection simulating a downstream "
                "service experiencing increasing load. Eventually triggers "
                "circuit breaker timeouts."
            ),
            phases=[
                GameDayPhase(
                    name="Phase 1: Slightly Sluggish",
                    fault_types=[FaultType.LATENCY_INJECTION],
                    severity=FaultSeverity.LEVEL_1,
                    duration_evals=10,
                    description="FizzBuzz evaluations take a bit longer than usual.",
                ),
                GameDayPhase(
                    name="Phase 2: Noticeably Slow",
                    fault_types=[FaultType.LATENCY_INJECTION],
                    severity=FaultSeverity.LEVEL_3,
                    duration_evals=10,
                    description="Users start to notice the delay in their FizzBuzz results.",
                ),
                GameDayPhase(
                    name="Phase 3: Glacial",
                    fault_types=[FaultType.LATENCY_INJECTION],
                    severity=FaultSeverity.LEVEL_5,
                    duration_evals=5,
                    description="Computing 3 % 3 now takes longer than compiling the Linux kernel.",
                ),
            ],
        ),
        "total_chaos": GameDayScenario(
            name="Total Chaos",
            description=(
                "All fault types activated simultaneously at maximum severity. "
                "This is the chaos engineering equivalent of 'hold my beer.' "
                "Not recommended for systems with feelings."
            ),
            phases=[
                GameDayPhase(
                    name="Phase 1: The Reckoning",
                    fault_types=list(FaultType),
                    severity=FaultSeverity.LEVEL_5,
                    duration_evals=20,
                    description=(
                        "Every fault type at maximum severity. Results corrupted, "
                        "latency injected, exceptions thrown, rules broken, "
                        "confidence shattered. It's beautiful, in a horrible way."
                    ),
                ),
            ],
        ),
    }

    def __init__(self, event_bus: Any = None) -> None:
        self._event_bus = event_bus
        self._results: list[dict[str, Any]] = []

    def run_scenario(
        self,
        scenario_name: str,
        evaluate_fn: Callable[[int], ProcessingContext],
        start_number: int = 1,
    ) -> dict[str, Any]:
        """Execute a named Game Day scenario.

        Args:
            scenario_name: Name of the pre-built scenario to run.
            evaluate_fn: Function that evaluates a single number through the pipeline.
            start_number: First number to evaluate.

        Returns:
            A summary dict with results from all phases.
        """
        if scenario_name not in self.SCENARIOS:
            raise ChaosExperimentFailedError(
                scenario_name,
                f"Unknown scenario. Available: {list(self.SCENARIOS.keys())}",
            )

        scenario = self.SCENARIOS[scenario_name]
        return self._execute_scenario(scenario, evaluate_fn, start_number)

    def _execute_scenario(
        self,
        scenario: GameDayScenario,
        evaluate_fn: Callable[[int], ProcessingContext],
        start_number: int = 1,
    ) -> dict[str, Any]:
        """Execute a Game Day scenario with all its phases."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.CHAOS_GAMEDAY_STARTED,
                payload={"scenario": scenario.name},
                source="GameDayRunner",
            ))

        current_number = start_number
        phase_results = []

        for phase in scenario.phases:
            phase_result = self._execute_phase(phase, evaluate_fn, current_number)
            phase_results.append(phase_result)
            current_number += phase.duration_evals

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.CHAOS_GAMEDAY_ENDED,
                payload={
                    "scenario": scenario.name,
                    "phases_completed": len(phase_results),
                },
                source="GameDayRunner",
            ))

        result = {
            "scenario": scenario.name,
            "description": scenario.description,
            "phases": phase_results,
            "total_evaluations": sum(p["evaluations"] for p in phase_results),
            "total_failures": sum(p["failures"] for p in phase_results),
        }
        self._results.append(result)
        return result

    def _execute_phase(
        self,
        phase: GameDayPhase,
        evaluate_fn: Callable[[int], ProcessingContext],
        start_number: int,
    ) -> dict[str, Any]:
        """Execute a single phase of a Game Day scenario."""
        failures = 0
        successes = 0

        for i in range(phase.duration_evals):
            number = start_number + i
            try:
                evaluate_fn(number)
                successes += 1
            except Exception:
                failures += 1

        return {
            "phase_name": phase.name,
            "description": phase.description,
            "severity": phase.severity.label,
            "evaluations": phase.duration_evals,
            "successes": successes,
            "failures": failures,
            "failure_rate": failures / phase.duration_evals if phase.duration_evals > 0 else 0.0,
        }


# ============================================================
# Post-Mortem Generator
# ============================================================


class PostMortemGenerator:
    """Generates satirical ASCII incident reports from chaos events.

    In real SRE practice, post-mortems are blameless documents that
    analyze incidents and propose improvements. In the Enterprise
    FizzBuzz Platform, they're an opportunity to write the most
    over-the-top incident report for what is fundamentally a program
    that checks if numbers are divisible by 3 and 5.

    The generated reports include:
        - Timeline of chaos events
        - Impact assessment (with appropriate hyperbole)
        - Root cause analysis (spoiler: it was the Chaos Monkey)
        - Action items (none of which will actually be implemented)
    """

    # Severity-appropriate incident titles
    _INCIDENT_TITLES = {
        1: "Minor FizzBuzz Disturbance (Nobody Noticed)",
        2: "Moderate FizzBuzz Degradation (Dashboard Flickered)",
        3: "Significant FizzBuzz Incident (Engineers Alerted)",
        4: "Major FizzBuzz Outage (War Room Activated)",
        5: "Catastrophic FizzBuzz Collapse (CEO Notified)",
    }

    _IMPACT_DESCRIPTIONS = {
        FaultType.RESULT_CORRUPTION: (
            "Several FizzBuzz results were silently corrupted, causing numbers "
            "that should have been 'Fizz' to identify as 'Buzz' and vice versa. "
            "The mathematical integrity of the platform was compromised. "
            "An emergency audit of all modulo operations has been initiated."
        ),
        FaultType.LATENCY_INJECTION: (
            "FizzBuzz evaluations experienced significant latency spikes, "
            "with some modulo operations taking up to {max_latency:.0f}ms. "
            "For context, light travels approximately {light_distance:.0f}km "
            "in that time. Our FizzBuzz results traveled nowhere."
        ),
        FaultType.EXCEPTION_INJECTION: (
            "Multiple unhandled exceptions disrupted the evaluation pipeline. "
            "The FizzBuzz service experienced {exception_count} unexpected failures, "
            "each accompanied by increasingly creative error messages from the "
            "Chaos Monkey's vocabulary of destruction."
        ),
        FaultType.RULE_ENGINE_FAILURE: (
            "The rule evaluation engine suffered intermittent amnesia, "
            "forgetting that 3 is divisible by 3 and that 15 is divisible "
            "by both 3 and 5. The modulo operator appeared to function normally "
            "but was secretly producing wrong results — the worst kind of failure."
        ),
        FaultType.CONFIDENCE_MANIPULATION: (
            "ML model confidence scores were artificially depressed, "
            "causing the neural network to express profound uncertainty about "
            "basic arithmetic. Peak doubt level: {min_confidence:.1%} confidence "
            "that 15 % 3 == 0. The circuit breaker may have been triggered."
        ),
    }

    _ACTION_ITEMS = [
        "Schedule a retrospective to discuss whether FizzBuzz needs this level of chaos testing.",
        "Implement a Chaos Monkey for the Chaos Monkey (chaos recursion depth: 2).",
        "Add more monitoring dashboards. We can never have too many dashboards.",
        "Conduct mandatory 'FizzBuzz Resilience Training' for all engineers.",
        "Upgrade the modulo operator to an enterprise-grade, fault-tolerant version.",
        "Consider migrating FizzBuzz to a blockchain-based evaluation engine. Oh wait.",
        "Write a 47-page incident response plan for FizzBuzz outages.",
        "Hire a dedicated FizzBuzz Site Reliability Engineer (FizzBuzz SRE).",
        "File a JIRA ticket to investigate. Assign it to 'Future Sprint'. Close in 6 months.",
        "Blame DNS. It's always DNS.",
        "Add circuit breakers to the circuit breakers. Defense in depth.",
        "Deploy a canary FizzBuzz service that only evaluates even numbers.",
    ]

    _ROOT_CAUSES = [
        "A Chaos Monkey was deliberately introduced into the FizzBuzz pipeline.",
        "The fault injection framework was functioning exactly as designed.",
        "Someone typed '--chaos' on the command line, fully aware of the consequences.",
        "The universe briefly forgot the rules of modular arithmetic.",
        "A rogue engineer decided to 'test in production' during a Game Day exercise.",
    ]

    @classmethod
    def generate(
        cls,
        chaos_monkey: ChaosMonkey,
        scenario_name: Optional[str] = None,
    ) -> str:
        """Generate a full post-mortem report from the Chaos Monkey's event log.

        Args:
            chaos_monkey: The ChaosMonkey instance with recorded events.
            scenario_name: Optional Game Day scenario name for the header.

        Returns:
            A multi-line ASCII string containing the satirical incident report.
        """
        events = chaos_monkey.events
        summary = chaos_monkey.get_summary()
        severity_level = chaos_monkey.severity.value

        title = cls._INCIDENT_TITLES.get(severity_level, "Unknown Severity Incident")

        lines: list[str] = []

        # Header
        lines.append("")
        lines.append("  " + "=" * 65)
        lines.append("  |" + " " * 63 + "|")
        lines.append("  |" + "POST-MORTEM INCIDENT REPORT".center(63) + "|")
        lines.append("  |" + "Enterprise FizzBuzz Platform".center(63) + "|")
        lines.append("  |" + " " * 63 + "|")
        lines.append("  " + "=" * 65)
        lines.append("")
        lines.append(f"  Incident Title  : {title}")
        lines.append(f"  Severity        : Level {severity_level} ({chaos_monkey.severity.label})")
        if scenario_name:
            lines.append(f"  Game Day        : {scenario_name}")
        lines.append(f"  Date            : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"  Status          : RESOLVED (the monkey was captured)")
        lines.append("")

        # Executive Summary
        lines.append("  " + "-" * 65)
        lines.append("  EXECUTIVE SUMMARY")
        lines.append("  " + "-" * 65)
        lines.append(f"  Total evaluations monitored  : {summary['total_evaluations']}")
        lines.append(f"  Total faults injected        : {summary['total_injections']}")
        lines.append(f"  Injection rate               : {summary['injection_rate']:.1%}")
        lines.append(f"  Fault types activated         : {len(summary['armed_fault_types'])}")
        lines.append("")

        # Fault Breakdown
        if summary["fault_counts"]:
            lines.append("  Fault Type Breakdown:")
            for ft_name, count in sorted(summary["fault_counts"].items()):
                bar = "#" * min(count, 30)
                lines.append(f"    {ft_name:<30s} : {count:>4d} |{bar}|")
            lines.append("")

        # Timeline
        lines.append("  " + "-" * 65)
        lines.append("  INCIDENT TIMELINE")
        lines.append("  " + "-" * 65)
        if events:
            for i, event in enumerate(events[:20]):  # Cap at 20 for readability
                ts = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
                lines.append(
                    f"  [{ts}] [{event.fault_type.name:<25s}] "
                    f"n={event.number:<5d} {event.description[:50]}"
                )
            if len(events) > 20:
                lines.append(f"  ... and {len(events) - 20} more events (truncated for sanity)")
        else:
            lines.append("  No chaos events recorded. The monkey was on vacation.")
        lines.append("")

        # Impact Assessment
        lines.append("  " + "-" * 65)
        lines.append("  IMPACT ASSESSMENT")
        lines.append("  " + "-" * 65)
        for ft_name in summary["fault_counts"]:
            ft = FaultType[ft_name]
            template = cls._IMPACT_DESCRIPTIONS.get(ft, "Unknown fault type impact.")
            # Fill in template variables with safe defaults
            impact_text = template.format(
                max_latency=500.0,
                light_distance=500.0 * 299.792,
                exception_count=summary["fault_counts"].get(ft_name, 0),
                min_confidence=0.1,
            )
            lines.append(f"  [{ft_name}]")
            # Word-wrap the impact text
            words = impact_text.split()
            current_line = "    "
            for word in words:
                if len(current_line) + len(word) + 1 > 68:
                    lines.append(current_line)
                    current_line = "    " + word
                else:
                    current_line += " " + word if current_line.strip() else "    " + word
            if current_line.strip():
                lines.append(current_line)
            lines.append("")

        # Root Cause Analysis
        lines.append("  " + "-" * 65)
        lines.append("  ROOT CAUSE ANALYSIS")
        lines.append("  " + "-" * 65)
        rng = random.Random(len(events))
        selected_causes = rng.sample(cls._ROOT_CAUSES, min(2, len(cls._ROOT_CAUSES)))
        for i, cause in enumerate(selected_causes, 1):
            lines.append(f"  {i}. {cause}")
        lines.append("")

        # Action Items
        lines.append("  " + "-" * 65)
        lines.append("  ACTION ITEMS")
        lines.append("  " + "-" * 65)
        selected_actions = rng.sample(cls._ACTION_ITEMS, min(4, len(cls._ACTION_ITEMS)))
        for i, action in enumerate(selected_actions, 1):
            lines.append(f"  [ ] {i}. {action}")
        lines.append("")

        # Footer
        lines.append("  " + "=" * 65)
        lines.append("  |" + " " * 63 + "|")
        lines.append("  |" + "This post-mortem was auto-generated by the".center(63) + "|")
        lines.append("  |" + "Enterprise FizzBuzz Chaos Engineering Framework".center(63) + "|")
        lines.append("  |" + "No actual systems were harmed. Only FizzBuzz.".center(63) + "|")
        lines.append("  |" + " " * 63 + "|")
        lines.append("  " + "=" * 65)
        lines.append("")

        return "\n".join(lines)

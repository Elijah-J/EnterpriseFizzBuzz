"""
Enterprise FizzBuzz Platform - Chaos Engineering & Load Testing Framework

Implements a production-grade chaos engineering system for stress-testing
the FizzBuzz evaluation pipeline. Following chaos engineering best
practices established by industry leaders, the platform includes a
comprehensive fault injection framework for validating the resilience
of its evaluation pipeline under adverse conditions.

The framework supports five categories of fault injection:
    - Result Corruption: Silently changes FizzBuzz outputs to wrong values
    - Latency Injection: Adds artificial delays to simulate network issues
    - Exception Injection: Throws exceptions mid-pipeline to test error handling
    - Rule Engine Failure: Causes the rule evaluation engine to malfunction
    - Confidence Manipulation: Tampers with ML confidence scores

Each fault type has configurable severity levels (1-5), where level 1 is
a gentle nudge and level 5 is the equivalent of handing a toddler the
production database credentials.

The module also includes the Load Testing Framework, merged here because
chaos engineering and load testing are two sides of the same coin: both
exist to determine how many concurrent modulo operations your enterprise
can survive before the architecture collapses under the weight of its
own abstractions. Features include:
    - Virtual Users (VUs) that simulate real-world FizzBuzz traffic patterns
    - Five workload profiles (SMOKE, LOAD, STRESS, SPIKE, ENDURANCE)
    - ThreadPoolExecutor-based concurrency (because asyncio was too easy)
    - Percentile-based latency analysis (p50/p90/p95/p99)
    - Bottleneck identification (spoiler: it's always the overhead)
    - ASCII dashboard with histogram, percentile table, and performance grade
    - Performance grading from A+ to F (A+ means your modulo takes < 1ms)

Design Patterns Employed:
    - Strategy Pattern (fault injectors)
    - Singleton (ChaosMonkey)
    - Middleware (ChaosMiddleware)
    - Observer (event publication)
    - Template Method (game day scenarios)
    - Builder (load test workload specs)

Compliance:
    - ISO 22301: Business Continuity through proactive failure testing
    - SOC 2 Type II: Demonstrable resilience of the FizzBuzz pipeline
    - PCI DSS: Because corrupted FizzBuzz results are a payment risk, somehow
"""

from __future__ import annotations

import logging
import math
import random
import statistics
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BottleneckAnalysisError,
    ChaosConfigurationError,
    ChaosError,
    ChaosExperimentFailedError,
    ChaosInducedFizzBuzzError,
    LoadTestConfigurationError,
    LoadTestTimeoutError,
    PerformanceGradeError,
    ResultCorruptionDetectedError,
    VirtualUserSpawnError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ConcreteRule,
    StandardRuleEngine,
)

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
        description: Description of what this phase tests.
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
    """Generates ASCII incident reports from chaos events.

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
            A multi-line ASCII string containing the incident report.
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


# ============================================================
# Load Testing Framework — "GameDay: Performance Edition"
# ============================================================
#
# Formerly its own module, the load testing framework has been
# absorbed into the chaos engineering system because stress-testing
# and fault injection are natural companions. One asks "can the
# system survive this?" The other asks "can the system survive
# this FAST ENOUGH?" Together, they form the complete picture
# of enterprise FizzBuzz resilience.


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
    importing a third-party load testing library would introduce
    unnecessary external dependencies when stdlib provides
    adequate concurrency primitives.
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
    ASCII art, providing zero-dependency visualization without
    requiring external dashboarding tools.
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

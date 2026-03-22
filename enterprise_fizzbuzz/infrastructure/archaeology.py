"""
Enterprise FizzBuzz Platform - Archaeological Recovery System

Digital forensics for FizzBuzz evaluations. When a FizzBuzz result is lost
to the sands of time (or, more accurately, when it was never stored because
the answer is literally computable via n % 3 == 0 or n % 5 == 0), this
module mounts a full-scale archaeological excavation across seven
stratigraphic evidence layers, simulates data corruption and degradation,
collects evidence fragments, applies Bayesian inference to reconstruct the
most probable classification, cross-references strata for conflicts,
and renders a forensic ASCII report.

This subsystem addresses the critical challenge of recovering evaluation
results from degraded or partial data sources when primary computation
paths are unavailable. The Bayesian reconstruction uses real posterior
probability computation, the corruption simulation models bit-rot
degradation curves, and the stratigraphy engine performs cross-layer
conflict detection to produce high-confidence recovery verdicts.

Strata (from most to least reliable):
    1. Blockchain Ledger        (weight=1.0) — immutable, if it exists
    2. Event Store              (weight=0.9) — append-only audit log
    3. Rule Engine Traces       (weight=0.8) — direct computation records
    4. Cache Coherence State    (weight=0.7) — MESI protocol snapshots
    5. Middleware Pipeline       (weight=0.6) — metadata breadcrumbs
    6. Metrics Counters         (weight=0.5) — statistical shadows
    7. Cache Eulogies           (weight=0.4) — obituaries of evicted entries
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzClassification,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# EvidenceStratum Enum
# ============================================================


class EvidenceStratum(Enum):
    """Stratigraphic layers from which FizzBuzz evidence can be excavated.

    Each stratum represents a different subsystem that may contain traces
    of a past FizzBuzz evaluation. The layers are ordered by reliability,
    from the immutable blockchain ledger (practically gospel) down to
    the poetic eulogies composed for evicted cache entries (practically
    fiction).

    The reliability weights reflect the trustworthiness of each data
    source, because in the enterprise FizzBuzz forensics community,
    not all evidence is created equal.
    """

    BLOCKCHAIN = "blockchain"
    EVENT_STORE = "event_store"
    RULE_ENGINE = "rule_engine"
    CACHE_COHERENCE = "cache_coherence"
    MIDDLEWARE_PIPELINE = "middleware_pipeline"
    METRICS = "metrics"
    CACHE_EULOGIES = "cache_eulogies"


# Default reliability weights per stratum
DEFAULT_STRATA_WEIGHTS: dict[str, float] = {
    EvidenceStratum.BLOCKCHAIN.value: 1.0,
    EvidenceStratum.EVENT_STORE.value: 0.9,
    EvidenceStratum.RULE_ENGINE.value: 0.8,
    EvidenceStratum.CACHE_COHERENCE.value: 0.7,
    EvidenceStratum.MIDDLEWARE_PIPELINE.value: 0.6,
    EvidenceStratum.METRICS.value: 0.5,
    EvidenceStratum.CACHE_EULOGIES.value: 0.4,
}


# ============================================================
# EvidenceFragment Dataclass
# ============================================================


@dataclass
class EvidenceFragment:
    """A single piece of evidence recovered from a stratigraphic layer.

    Each fragment represents a data point excavated from one of the
    seven evidence strata. Fragments carry a confidence score (0.0-1.0)
    that reflects both the inherent reliability of the stratum and any
    degradation introduced by the corruption simulator.

    A corrupted fragment is not necessarily useless — it still participates
    in the Bayesian reconstruction, but with reduced weight. Think of it
    as a partially-legible clay tablet: you can still make out some
    cuneiform, but you wouldn't bet your dissertation on it.

    Attributes:
        stratum: The stratigraphic layer this evidence came from.
        number: The integer being investigated.
        classification: The FizzBuzz classification suggested by this fragment.
        confidence: Confidence in this fragment (0.0 = pure noise, 1.0 = certain).
        corrupted: Whether corruption simulation has degraded this fragment.
        timestamp: When this fragment was "excavated" (simulated).
        metadata: Additional forensic metadata attached to the fragment.
    """

    stratum: EvidenceStratum
    number: int
    classification: FizzBuzzClassification
    confidence: float
    corrupted: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_confidence(self) -> float:
        """Confidence adjusted by stratum reliability weight."""
        weight = DEFAULT_STRATA_WEIGHTS.get(self.stratum.value, 0.5)
        return self.confidence * weight


# ============================================================
# CorruptionSimulator
# ============================================================


class CorruptionSimulator:
    """Simulates data degradation across stratigraphic evidence layers.

    In the real world, data degrades over time due to bit rot, cosmic rays,
    storage media decay, and the general tendency of the universe toward
    maximum entropy. In the Enterprise FizzBuzz Platform, we simulate this
    degradation because (a) our data is ephemeral in-memory structures that
    literally cannot experience bit rot, and (b) we needed another class.

    The corruption model uses a stratum-dependent degradation curve:
    more reliable strata (blockchain) resist corruption better than
    less reliable ones (cache eulogies). The corruption rate is
    configurable, and a random seed ensures reproducible forensic
    scenarios for audit compliance.
    """

    def __init__(
        self,
        corruption_rate: float = 0.15,
        seed: int | None = None,
    ) -> None:
        self._corruption_rate = max(0.0, min(1.0, corruption_rate))
        self._rng = random.Random(seed)
        self._corruption_log: list[dict[str, Any]] = []

    @property
    def corruption_log(self) -> list[dict[str, Any]]:
        """Return the log of all corruption events for forensic review."""
        return list(self._corruption_log)

    def maybe_corrupt(self, fragment: EvidenceFragment) -> EvidenceFragment:
        """Apply stochastic corruption to an evidence fragment.

        The probability of corruption is inversely proportional to the
        stratum's reliability weight. Blockchain evidence (weight=1.0)
        is nearly immune; cache eulogy evidence (weight=0.4) is fragile.

        When corruption occurs, the fragment's confidence is degraded by
        a random factor, and the classification may be flipped to a random
        alternative. The corrupted flag is set to True so downstream
        consumers know to treat this evidence with appropriate suspicion.
        """
        weight = DEFAULT_STRATA_WEIGHTS.get(fragment.stratum.value, 0.5)
        # Higher-weight strata resist corruption better
        adjusted_rate = self._corruption_rate * (1.0 - weight * 0.7)

        if self._rng.random() < adjusted_rate:
            # Corruption event!
            degradation = self._rng.uniform(0.3, 0.8)
            new_confidence = fragment.confidence * (1.0 - degradation)

            # Sometimes corruption flips the classification entirely
            if self._rng.random() < 0.3:
                classifications = list(FizzBuzzClassification)
                classifications.remove(fragment.classification)
                corrupted_class = self._rng.choice(classifications)
            else:
                corrupted_class = fragment.classification

            corruption_event = {
                "stratum": fragment.stratum.value,
                "number": fragment.number,
                "original_confidence": fragment.confidence,
                "degraded_confidence": new_confidence,
                "original_class": fragment.classification.name,
                "corrupted_class": corrupted_class.name,
                "degradation_factor": degradation,
                "classification_flipped": corrupted_class != fragment.classification,
            }
            self._corruption_log.append(corruption_event)

            return EvidenceFragment(
                stratum=fragment.stratum,
                number=fragment.number,
                classification=corrupted_class,
                confidence=new_confidence,
                corrupted=True,
                timestamp=fragment.timestamp,
                metadata={
                    **fragment.metadata,
                    "corruption_degradation": degradation,
                    "original_confidence": fragment.confidence,
                },
            )

        return fragment

    def reset(self) -> None:
        """Clear the corruption log. For testing and between excavations."""
        self._corruption_log.clear()


# ============================================================
# Helper: compute the "true" FizzBuzz classification
# ============================================================


def _true_classification(n: int) -> FizzBuzzClassification:
    """Compute the mathematically correct FizzBuzz classification.

    This function exists so that the evidence collector can generate
    realistic evidence fragments. In a real archaeological system, we
    would not have access to ground truth — but since we are excavating
    FizzBuzz results, ground truth is literally one modulo operation away.
    The irony is not lost on us; it is, in fact, load-bearing.
    """
    div3 = n % 3 == 0
    div5 = n % 5 == 0
    if div3 and div5:
        return FizzBuzzClassification.FIZZBUZZ
    elif div3:
        return FizzBuzzClassification.FIZZ
    elif div5:
        return FizzBuzzClassification.BUZZ
    else:
        return FizzBuzzClassification.PLAIN


# ============================================================
# EvidenceCollector
# ============================================================


class EvidenceCollector:
    """Collects evidence fragments from all seven stratigraphic layers.

    Each collection method simulates excavating evidence from one subsystem.
    The collector does not depend on any real subsystem instances — it
    generates synthetic evidence based on mathematical ground truth, because
    the real subsystems may not be running, may not have been configured,
    or may not exist in this particular deployment configuration.

    This design means the Archaeological Recovery System works standalone:
    you can excavate evidence for any number without needing the blockchain,
    event store, cache, or any other subsystem to be active. The evidence
    is fabricated from first principles, which is philosophically identical
    to what the real subsystems would have produced anyway.

    Each method returns a list of EvidenceFragment objects. The list may be
    empty if the stratum yields no evidence (simulating missing data).
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def collect_all(self, number: int) -> list[EvidenceFragment]:
        """Collect evidence from all seven strata for a given number."""
        collectors = [
            self.collect_blockchain,
            self.collect_event_store,
            self.collect_rule_engine,
            self.collect_cache_coherence,
            self.collect_middleware_pipeline,
            self.collect_metrics,
            self.collect_cache_eulogies,
        ]
        fragments: list[EvidenceFragment] = []
        for collector in collectors:
            try:
                fragments.extend(collector(number))
            except Exception:
                # Gracefully handle missing subsystems
                logger.debug("Stratum collection failed for %s", collector.__name__)
        return fragments

    def collect_blockchain(self, number: int) -> list[EvidenceFragment]:
        """Excavate evidence from the blockchain ledger.

        The blockchain is the most reliable stratum. If a FizzBuzz
        evaluation was recorded on-chain, the evidence is immutable
        and tamper-proof. The confidence is derived from the block's
        hash — a deterministic fingerprint that ensures reproducibility.
        """
        true_class = _true_classification(number)
        # Simulate block hash-derived confidence
        block_hash = hashlib.sha256(f"fizzbuzz-block-{number}".encode()).hexdigest()
        hash_confidence = 0.95 + (int(block_hash[:4], 16) / 65535) * 0.05

        return [
            EvidenceFragment(
                stratum=EvidenceStratum.BLOCKCHAIN,
                number=number,
                classification=true_class,
                confidence=hash_confidence,
                metadata={
                    "block_hash": block_hash[:16],
                    "mining_difficulty": 4,
                    "chain_height": number * 7 + 42,
                },
            )
        ]

    def collect_event_store(self, number: int) -> list[EvidenceFragment]:
        """Excavate evidence from the event sourcing log.

        The event store is append-only, making it the second most reliable
        stratum. Events are never deleted, only superseded. We simulate
        finding the original evaluation event and any subsequent correction
        events.
        """
        true_class = _true_classification(number)
        # Primary event
        fragments = [
            EvidenceFragment(
                stratum=EvidenceStratum.EVENT_STORE,
                number=number,
                classification=true_class,
                confidence=0.92,
                metadata={
                    "event_type": "NUMBER_EVALUATED",
                    "event_version": 1,
                    "sequence_number": number * 3,
                },
            )
        ]
        # Sometimes there's a correction event (for numbers > 50)
        if number > 50:
            fragments.append(
                EvidenceFragment(
                    stratum=EvidenceStratum.EVENT_STORE,
                    number=number,
                    classification=true_class,
                    confidence=0.95,
                    metadata={
                        "event_type": "EVALUATION_CONFIRMED",
                        "event_version": 2,
                        "sequence_number": number * 3 + 1,
                    },
                )
            )
        return fragments

    def collect_rule_engine(self, number: int) -> list[EvidenceFragment]:
        """Excavate evidence from the rule engine computation trace.

        The rule engine stratum contains direct computation records —
        the actual results of applying divisibility rules. This is
        essentially re-deriving the answer from the rules themselves,
        which raises the philosophical question of whether archaeology
        is just computation with extra steps.
        """
        true_class = _true_classification(number)
        # Generate per-rule evidence
        fragments = []
        if number % 3 == 0:
            fragments.append(
                EvidenceFragment(
                    stratum=EvidenceStratum.RULE_ENGINE,
                    number=number,
                    classification=FizzBuzzClassification.FIZZ if number % 5 != 0 else FizzBuzzClassification.FIZZBUZZ,
                    confidence=0.88,
                    metadata={"rule": "FizzRule", "divisor": 3, "matched": True},
                )
            )
        if number % 5 == 0:
            fragments.append(
                EvidenceFragment(
                    stratum=EvidenceStratum.RULE_ENGINE,
                    number=number,
                    classification=FizzBuzzClassification.BUZZ if number % 3 != 0 else FizzBuzzClassification.FIZZBUZZ,
                    confidence=0.88,
                    metadata={"rule": "BuzzRule", "divisor": 5, "matched": True},
                )
            )
        if number % 3 != 0 and number % 5 != 0:
            fragments.append(
                EvidenceFragment(
                    stratum=EvidenceStratum.RULE_ENGINE,
                    number=number,
                    classification=FizzBuzzClassification.PLAIN,
                    confidence=0.85,
                    metadata={"rule": "NoMatch", "divisor": None, "matched": False},
                )
            )
        return fragments

    def collect_cache_coherence(self, number: int) -> list[EvidenceFragment]:
        """Excavate evidence from the MESI cache coherence protocol state.

        The cache coherence stratum contains snapshots of the MESI protocol
        state machine. If a number's result was cached, the coherence state
        tells us what value was stored and in what state (Modified, Exclusive,
        Shared, or Invalid). Evidence from the Invalid state is, predictably,
        less reliable.
        """
        true_class = _true_classification(number)
        mesi_states = ["Modified", "Exclusive", "Shared", "Invalid"]
        # Deterministic MESI state based on number
        state_idx = number % 4
        mesi_state = mesi_states[state_idx]
        # Invalid state reduces confidence
        confidence = 0.78 if mesi_state != "Invalid" else 0.55

        return [
            EvidenceFragment(
                stratum=EvidenceStratum.CACHE_COHERENCE,
                number=number,
                classification=true_class,
                confidence=confidence,
                metadata={
                    "mesi_state": mesi_state,
                    "cache_line": number % 64,
                    "tag_bits": hex(number * 17),
                },
            )
        ]

    def collect_middleware_pipeline(self, number: int) -> list[EvidenceFragment]:
        """Excavate evidence from middleware pipeline metadata.

        The middleware pipeline stratum contains breadcrumbs left by
        various middleware components as they processed the number.
        These are noisy but occasionally informative — like reading
        tea leaves, except the tea leaves are JSON metadata objects.
        """
        true_class = _true_classification(number)
        # Simulate middleware adding classification hints to metadata
        confidence = 0.65 + self._rng.uniform(-0.1, 0.1)
        confidence = max(0.1, min(1.0, confidence))

        return [
            EvidenceFragment(
                stratum=EvidenceStratum.MIDDLEWARE_PIPELINE,
                number=number,
                classification=true_class,
                confidence=confidence,
                metadata={
                    "middleware_chain": [
                        "ValidationMiddleware",
                        "TimingMiddleware",
                        "LoggingMiddleware",
                    ],
                    "pipeline_depth": 3,
                    "processing_order": number,
                },
            )
        ]

    def collect_metrics(self, number: int) -> list[EvidenceFragment]:
        """Excavate evidence from Prometheus-style metrics counters.

        The metrics stratum is statistical in nature — it doesn't record
        individual evaluations but rather aggregate counters. We infer
        the classification by examining which counters were incremented.
        This is the forensic equivalent of deducing a crime from
        actuarial tables: technically possible, aesthetically displeasing.
        """
        true_class = _true_classification(number)
        # Metrics are statistical; lower confidence
        confidence = 0.55 + self._rng.uniform(-0.08, 0.08)
        confidence = max(0.1, min(1.0, confidence))

        metric_name = {
            FizzBuzzClassification.FIZZ: "fizzbuzz_fizz_total",
            FizzBuzzClassification.BUZZ: "fizzbuzz_buzz_total",
            FizzBuzzClassification.FIZZBUZZ: "fizzbuzz_fizzbuzz_total",
            FizzBuzzClassification.PLAIN: "fizzbuzz_plain_total",
        }

        return [
            EvidenceFragment(
                stratum=EvidenceStratum.METRICS,
                number=number,
                classification=true_class,
                confidence=confidence,
                metadata={
                    "metric_name": metric_name[true_class],
                    "counter_value": self._rng.randint(1, 10000),
                    "scrape_interval_ms": 15000,
                },
            )
        ]

    def collect_cache_eulogies(self, number: int) -> list[EvidenceFragment]:
        """Excavate evidence from commemorative records of evicted cache entries.

        The cache eulogies stratum is the least reliable of all. It contains
        the flowery prose composed by the cache eviction subsystem to
        memorialize entries that were removed to make room for new data.
        The classification must be inferred from literary analysis of the
        eulogy text, which is about as reliable as you'd expect.

        Example eulogy: "Here lies the result of 15 % 3, taken from us
        too soon by the LRU policy. It was a good Fizz. It will be missed."
        """
        true_class = _true_classification(number)
        # Eulogies are poetic but unreliable
        confidence = 0.45 + self._rng.uniform(-0.1, 0.1)
        confidence = max(0.1, min(1.0, confidence))

        class_labels = {
            FizzBuzzClassification.FIZZ: "Fizz",
            FizzBuzzClassification.BUZZ: "Buzz",
            FizzBuzzClassification.FIZZBUZZ: "FizzBuzz",
            FizzBuzzClassification.PLAIN: str(number),
        }
        label = class_labels[true_class]

        eulogies = [
            f"Here lies the result of {number}, taken from us too soon by LRU. It was a good {label}.",
            f"In loving memory of {number}'s classification: {label}. Gone but not forgotten.",
            f"REST IN CACHE: {number} -> {label}. Evicted at the height of its relevance.",
            f"Dearly departed: the evaluation of {number}. Its {label}-ness shall echo through eternity.",
        ]

        return [
            EvidenceFragment(
                stratum=EvidenceStratum.CACHE_EULOGIES,
                number=number,
                classification=true_class,
                confidence=confidence,
                metadata={
                    "eulogy_text": self._rng.choice(eulogies),
                    "eviction_policy": "LRU",
                    "time_of_death": datetime.now(timezone.utc).isoformat(),
                },
            )
        ]


# ============================================================
# BayesianReconstructor
# ============================================================


class BayesianReconstructor:
    """Reconstructs the most probable FizzBuzz classification via Bayes' theorem.

    Given a collection of evidence fragments from multiple strata, this
    reconstructor computes the posterior probability P(class | evidence)
    for each possible FizzBuzz classification using Bayes' theorem:

        P(class | E) = P(E | class) * P(class) / P(E)

    The prior P(class) is derived from the mathematical distribution
    of FizzBuzz classifications in the natural numbers:
        - P(FizzBuzz) = 1/15  (~6.67%)   — divisible by both 3 and 5
        - P(Fizz)     = 4/15  (~26.67%)  — divisible by 3 but not 5
        - P(Buzz)     = 2/15  (~13.33%)  — divisible by 5 but not 3
        - P(Plain)    = 8/15  (~53.33%)  — divisible by neither

    The likelihood P(E | class) is modeled as a product of per-fragment
    contributions, where each fragment's confidence and stratum weight
    determine its contribution to the likelihood of the corresponding class.

    This is real Bayesian inference applied to a problem whose answer
    requires zero inference. The posterior distribution is guaranteed to
    converge to the correct answer given enough evidence, which is
    impressive until you remember that one modulo operation also works.
    """

    # Prior probabilities based on FizzBuzz mathematical distribution
    # In the range [1, N] as N -> infinity:
    #   P(FizzBuzz) = 1/15, P(Fizz) = 4/15, P(Buzz) = 2/15, P(Plain) = 8/15
    PRIORS: dict[FizzBuzzClassification, float] = {
        FizzBuzzClassification.FIZZBUZZ: 1.0 / 15.0,
        FizzBuzzClassification.FIZZ: 4.0 / 15.0,
        FizzBuzzClassification.BUZZ: 2.0 / 15.0,
        FizzBuzzClassification.PLAIN: 8.0 / 15.0,
    }

    def __init__(self, confidence_threshold: float = 0.6) -> None:
        self._confidence_threshold = confidence_threshold

    def reconstruct(
        self, fragments: list[EvidenceFragment]
    ) -> dict[FizzBuzzClassification, float]:
        """Compute the posterior probability distribution over classifications.

        Returns a dict mapping each FizzBuzzClassification to its posterior
        probability, normalized to sum to 1.0. If no fragments are provided,
        returns the prior distribution unchanged.
        """
        if not fragments:
            return dict(self.PRIORS)

        # Start with log-priors to avoid underflow
        log_posteriors: dict[FizzBuzzClassification, float] = {}
        for cls in FizzBuzzClassification:
            log_posteriors[cls] = math.log(self.PRIORS[cls])

        # Update with evidence (product of likelihoods in log-space)
        for fragment in fragments:
            weight = DEFAULT_STRATA_WEIGHTS.get(fragment.stratum.value, 0.5)
            effective_confidence = fragment.confidence * weight

            for cls in FizzBuzzClassification:
                if cls == fragment.classification:
                    # Evidence supports this class
                    likelihood = effective_confidence
                else:
                    # Evidence contradicts this class
                    likelihood = (1.0 - effective_confidence) / 3.0

                # Clamp to avoid log(0)
                likelihood = max(likelihood, 1e-10)
                log_posteriors[cls] += math.log(likelihood)

        # Convert from log-space and normalize
        max_log = max(log_posteriors.values())
        posteriors: dict[FizzBuzzClassification, float] = {}
        for cls in FizzBuzzClassification:
            posteriors[cls] = math.exp(log_posteriors[cls] - max_log)

        total = sum(posteriors.values())
        if total > 0:
            for cls in posteriors:
                posteriors[cls] /= total

        return posteriors

    def classify(
        self, fragments: list[EvidenceFragment]
    ) -> tuple[FizzBuzzClassification, float]:
        """Return the most probable classification and its posterior probability.

        If the highest posterior probability is below the confidence threshold,
        the classification is still returned but the caller should treat it
        with appropriate skepticism.
        """
        posteriors = self.reconstruct(fragments)
        best_class = max(posteriors, key=posteriors.get)  # type: ignore[arg-type]
        best_prob = posteriors[best_class]
        return best_class, best_prob

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold


# ============================================================
# StratigraphyEngine
# ============================================================


class StratigraphyEngine:
    """Cross-references evidence across stratigraphic layers.

    The stratigraphy engine performs three critical forensic operations:

    1. **Layer Correlation**: Identifies which strata agree on the
       classification and which disagree.

    2. **Timeline Construction**: Builds a chronological sequence of
       evidence discovery, ordered by stratum reliability.

    3. **Conflict Detection**: Identifies stratigraphic conflicts where
       two or more layers produce contradictory classifications.

    In real archaeology, stratigraphy is the study of rock layers to
    understand geological history. Here, it's the study of software
    subsystem outputs to understand what 15 % 3 equals. Same science,
    different stakes.
    """

    def correlate(
        self, fragments: list[EvidenceFragment]
    ) -> dict[str, list[EvidenceFragment]]:
        """Group fragments by stratum for cross-layer analysis."""
        strata_map: dict[str, list[EvidenceFragment]] = {}
        for f in fragments:
            key = f.stratum.value
            if key not in strata_map:
                strata_map[key] = []
            strata_map[key].append(f)
        return strata_map

    def build_timeline(
        self, fragments: list[EvidenceFragment]
    ) -> list[dict[str, Any]]:
        """Build a forensic timeline ordered by stratum reliability (descending).

        Returns a list of timeline entries, each containing the stratum name,
        the evidence fragments found, and the consensus classification
        from that stratum.
        """
        strata_map = self.correlate(fragments)
        timeline: list[dict[str, Any]] = []

        # Sort strata by reliability weight (descending)
        sorted_strata = sorted(
            strata_map.keys(),
            key=lambda s: DEFAULT_STRATA_WEIGHTS.get(s, 0.0),
            reverse=True,
        )

        for stratum_name in sorted_strata:
            stratum_fragments = strata_map[stratum_name]
            # Consensus = majority classification weighted by confidence
            class_weights: dict[FizzBuzzClassification, float] = {}
            for f in stratum_fragments:
                class_weights[f.classification] = (
                    class_weights.get(f.classification, 0.0) + f.confidence
                )
            consensus = max(class_weights, key=class_weights.get)  # type: ignore[arg-type]

            timeline.append({
                "stratum": stratum_name,
                "weight": DEFAULT_STRATA_WEIGHTS.get(stratum_name, 0.0),
                "fragment_count": len(stratum_fragments),
                "consensus": consensus,
                "corrupted_count": sum(1 for f in stratum_fragments if f.corrupted),
                "avg_confidence": sum(f.confidence for f in stratum_fragments) / len(stratum_fragments),
            })

        return timeline

    def detect_conflicts(
        self, fragments: list[EvidenceFragment]
    ) -> list[dict[str, Any]]:
        """Detect classification conflicts between strata.

        A conflict occurs when the consensus classification of one stratum
        differs from the consensus of another. Returns a list of conflict
        records, each identifying the two disagreeing strata and their
        respective classifications.
        """
        timeline = self.build_timeline(fragments)
        conflicts: list[dict[str, Any]] = []

        for i in range(len(timeline)):
            for j in range(i + 1, len(timeline)):
                if timeline[i]["consensus"] != timeline[j]["consensus"]:
                    conflicts.append({
                        "stratum_a": timeline[i]["stratum"],
                        "class_a": timeline[i]["consensus"].name,
                        "stratum_b": timeline[j]["stratum"],
                        "class_b": timeline[j]["consensus"].name,
                        "weight_a": timeline[i]["weight"],
                        "weight_b": timeline[j]["weight"],
                    })

        return conflicts


# ============================================================
# ExcavationReport
# ============================================================


class ExcavationReport:
    """Renders an ASCII forensic report for a single number excavation.

    The report includes:
    - The number under investigation
    - Evidence fragments from each stratum
    - Corruption events (if any)
    - Bayesian posterior distribution
    - Final reconstructed classification
    - Stratigraphic conflict analysis
    - An ASCII art excavation site visualization

    The level of detail in this report is inversely proportional to the
    complexity of the underlying problem. Computing 15 % 3 requires
    approximately zero thought; documenting the archaeological recovery
    of that computation requires approximately 80 lines of ASCII art.
    """

    @staticmethod
    def render(
        number: int,
        fragments: list[EvidenceFragment],
        posteriors: dict[FizzBuzzClassification, float],
        best_class: FizzBuzzClassification,
        best_prob: float,
        conflicts: list[dict[str, Any]],
        timeline: list[dict[str, Any]],
        corruption_log: list[dict[str, Any]],
        width: int = 60,
    ) -> str:
        """Render the full excavation report as an ASCII string."""
        border = "=" * width
        thin = "-" * width
        lines: list[str] = []

        lines.append(border)
        title = f"ARCHAEOLOGICAL EXCAVATION REPORT: Number {number}"
        lines.append(title.center(width))
        lines.append(f"{'Digital Forensics Division'.center(width)}")
        lines.append(border)
        lines.append("")

        # Section 1: Excavation Summary
        lines.append(f"  Subject Number: {number}")
        lines.append(f"  Total Fragments Recovered: {len(fragments)}")
        lines.append(f"  Corrupted Fragments: {sum(1 for f in fragments if f.corrupted)}")
        lines.append(f"  Strata Excavated: {len(set(f.stratum for f in fragments))}/7")
        lines.append(f"  Stratigraphic Conflicts: {len(conflicts)}")
        lines.append("")

        # Section 2: Stratigraphic Timeline
        lines.append(thin)
        lines.append("  STRATIGRAPHIC TIMELINE (by reliability)")
        lines.append(thin)
        for entry in timeline:
            corruption_marker = " [!]" if entry["corrupted_count"] > 0 else ""
            bar_len = int(entry["avg_confidence"] * 20)
            bar = "#" * bar_len + "." * (20 - bar_len)
            lines.append(
                f"  {entry['stratum']:24s} "
                f"w={entry['weight']:.1f} "
                f"[{bar}] "
                f"{entry['consensus'].name:10s}{corruption_marker}"
            )
        lines.append("")

        # Section 3: Bayesian Posterior Distribution
        lines.append(thin)
        lines.append("  BAYESIAN POSTERIOR P(class | evidence)")
        lines.append(thin)
        for cls in sorted(posteriors, key=lambda c: posteriors[c], reverse=True):
            prob = posteriors[cls]
            bar_len = int(prob * 40)
            bar = "|" * bar_len
            marker = " <-- BEST" if cls == best_class else ""
            lines.append(f"  {cls.name:10s}  {prob:6.4f}  {bar}{marker}")
        lines.append("")

        # Section 4: Verdict
        lines.append(thin)
        confidence_str = f"{best_prob:.4f}"
        verdict = f"  RECONSTRUCTED CLASSIFICATION: {best_class.name}"
        lines.append(verdict)
        lines.append(f"  POSTERIOR CONFIDENCE: {confidence_str}")
        if best_prob < 0.6:
            lines.append("  WARNING: Low confidence. Consider additional excavation.")
        elif best_prob > 0.95:
            lines.append("  CERTAINTY: Forensically conclusive.")
        else:
            lines.append("  STATUS: Reasonable archaeological certainty.")
        lines.append("")

        # Section 5: Corruption Report
        if corruption_log:
            lines.append(thin)
            lines.append(f"  CORRUPTION EVENTS ({len(corruption_log)} detected)")
            lines.append(thin)
            for event in corruption_log:
                flip_str = "CLASS FLIPPED" if event["classification_flipped"] else "confidence only"
                lines.append(
                    f"  Stratum: {event['stratum']:24s} "
                    f"Degradation: {event['degradation_factor']:.2f} "
                    f"({flip_str})"
                )
            lines.append("")

        # Section 6: Conflict Analysis
        if conflicts:
            lines.append(thin)
            lines.append(f"  STRATIGRAPHIC CONFLICTS ({len(conflicts)} detected)")
            lines.append(thin)
            for conflict in conflicts:
                lines.append(
                    f"  {conflict['stratum_a']} ({conflict['class_a']}) vs "
                    f"{conflict['stratum_b']} ({conflict['class_b']})"
                )
            lines.append("")

        # Section 7: ASCII Excavation Site
        lines.append(thin)
        lines.append("  EXCAVATION SITE CROSS-SECTION")
        lines.append(thin)
        strata_order = [
            EvidenceStratum.BLOCKCHAIN,
            EvidenceStratum.EVENT_STORE,
            EvidenceStratum.RULE_ENGINE,
            EvidenceStratum.CACHE_COHERENCE,
            EvidenceStratum.MIDDLEWARE_PIPELINE,
            EvidenceStratum.METRICS,
            EvidenceStratum.CACHE_EULOGIES,
        ]
        stratum_fragments = {s: [] for s in strata_order}
        for f in fragments:
            stratum_fragments[f.stratum].append(f)

        depth = 0
        for stratum in strata_order:
            frags = stratum_fragments[stratum]
            depth += 1
            layer_char = "~" if depth <= 2 else "-" if depth <= 4 else "." if depth <= 6 else ","
            found = len(frags)
            corrupted = sum(1 for f in frags if f.corrupted)
            status = f"{found} fragment(s)" if found > 0 else "-- empty --"
            if corrupted > 0:
                status += f" ({corrupted} corrupted)"
            layer_vis = layer_char * 40
            lines.append(f"  Layer {depth}: {layer_vis}")
            lines.append(f"         {stratum.value:24s}  {status}")

        lines.append("")
        lines.append(border)
        lines.append(
            f"  NOTE: This classification could have been computed via".center(width)
        )
        lines.append(
            f"  '{number} % 3 == 0 or {number} % 5 == 0' in one CPU cycle.".center(width)
        )
        lines.append(
            f"  The archaeological approach used {len(fragments)} evidence".center(width)
        )
        lines.append(
            f"  fragments across {len(set(f.stratum for f in fragments))} strata instead.".center(width)
        )
        lines.append(border)

        return "\n".join(lines)


# ============================================================
# ArchaeologyEngine
# ============================================================


class ArchaeologyEngine:
    """Orchestrator for the Archaeological Recovery System.

    The ArchaeologyEngine coordinates the full excavation pipeline:
    1. Collect evidence from all seven strata
    2. Apply corruption simulation
    3. Run Bayesian reconstruction
    4. Build stratigraphic timeline
    5. Detect conflicts
    6. Render the forensic report

    It is the Indiana Jones of the Enterprise FizzBuzz Platform:
    dramatically excavating answers that were never buried.
    """

    def __init__(
        self,
        corruption_rate: float = 0.15,
        confidence_threshold: float = 0.6,
        min_fragments: int = 2,
        enable_corruption: bool = True,
        seed: int | None = None,
        strata_weights: dict[str, float] | None = None,
    ) -> None:
        self._collector = EvidenceCollector(seed=seed)
        self._corruption_sim = CorruptionSimulator(
            corruption_rate=corruption_rate, seed=seed
        )
        self._reconstructor = BayesianReconstructor(
            confidence_threshold=confidence_threshold
        )
        self._stratigraphy = StratigraphyEngine()
        self._min_fragments = min_fragments
        self._enable_corruption = enable_corruption
        self._excavation_history: list[dict[str, Any]] = []

        # Allow custom strata weights
        if strata_weights:
            for key, weight in strata_weights.items():
                if key in DEFAULT_STRATA_WEIGHTS:
                    DEFAULT_STRATA_WEIGHTS[key] = weight

    @property
    def excavation_history(self) -> list[dict[str, Any]]:
        """Return the history of all excavations performed."""
        return list(self._excavation_history)

    @property
    def collector(self) -> EvidenceCollector:
        return self._collector

    @property
    def corruption_simulator(self) -> CorruptionSimulator:
        return self._corruption_sim

    @property
    def reconstructor(self) -> BayesianReconstructor:
        return self._reconstructor

    @property
    def stratigraphy(self) -> StratigraphyEngine:
        return self._stratigraphy

    def excavate(self, number: int, width: int = 60) -> str:
        """Perform a full archaeological excavation for a given number.

        Returns the rendered ExcavationReport as a string.
        """
        start_time = time.monotonic()

        # Step 1: Collect evidence from all strata
        self._corruption_sim.reset()
        raw_fragments = self._collector.collect_all(number)

        # Step 2: Apply corruption simulation
        if self._enable_corruption:
            fragments = [self._corruption_sim.maybe_corrupt(f) for f in raw_fragments]
        else:
            fragments = raw_fragments

        # Step 3: Bayesian reconstruction
        posteriors = self._reconstructor.reconstruct(fragments)
        best_class, best_prob = self._reconstructor.classify(fragments)

        # Step 4: Stratigraphy
        timeline = self._stratigraphy.build_timeline(fragments)
        conflicts = self._stratigraphy.detect_conflicts(fragments)

        # Step 5: Record in history
        elapsed = (time.monotonic() - start_time) * 1000
        self._excavation_history.append({
            "number": number,
            "classification": best_class.name,
            "confidence": best_prob,
            "fragments": len(fragments),
            "corrupted": sum(1 for f in fragments if f.corrupted),
            "conflicts": len(conflicts),
            "elapsed_ms": elapsed,
        })

        # Step 6: Render report
        return ExcavationReport.render(
            number=number,
            fragments=fragments,
            posteriors=posteriors,
            best_class=best_class,
            best_prob=best_prob,
            conflicts=conflicts,
            timeline=timeline,
            corruption_log=self._corruption_sim.corruption_log,
            width=width,
        )

    def excavate_range(
        self, start: int, end: int, width: int = 60
    ) -> list[str]:
        """Excavate a range of numbers, returning a list of reports."""
        return [self.excavate(n, width=width) for n in range(start, end + 1)]

    def get_summary(self) -> dict[str, Any]:
        """Return a statistical summary of all excavations performed."""
        if not self._excavation_history:
            return {
                "total_excavations": 0,
                "avg_confidence": 0.0,
                "total_fragments": 0,
                "total_corrupted": 0,
                "total_conflicts": 0,
                "avg_elapsed_ms": 0.0,
            }

        total = len(self._excavation_history)
        return {
            "total_excavations": total,
            "avg_confidence": sum(e["confidence"] for e in self._excavation_history) / total,
            "total_fragments": sum(e["fragments"] for e in self._excavation_history),
            "total_corrupted": sum(e["corrupted"] for e in self._excavation_history),
            "total_conflicts": sum(e["conflicts"] for e in self._excavation_history),
            "avg_elapsed_ms": sum(e["elapsed_ms"] for e in self._excavation_history) / total,
            "classification_distribution": self._classification_distribution(),
        }

    def _classification_distribution(self) -> dict[str, int]:
        """Count how many times each classification was reconstructed."""
        dist: dict[str, int] = {}
        for entry in self._excavation_history:
            cls = entry["classification"]
            dist[cls] = dist.get(cls, 0) + 1
        return dist


# ============================================================
# ArchaeologyDashboard
# ============================================================


class ArchaeologyDashboard:
    """Renders an ASCII dashboard summarizing archaeological activity.

    The dashboard provides a bird's-eye view of all excavations performed
    during the current session, including classification distributions,
    confidence statistics, corruption rates, and stratigraphic conflict
    summaries. It is the mission control center for digital forensics
    operations that could have been replaced by a for loop.
    """

    @staticmethod
    def render(
        engine: ArchaeologyEngine,
        width: int = 60,
        show_strata: bool = True,
        show_bayesian: bool = True,
        show_corruption: bool = True,
    ) -> str:
        border = "=" * width
        thin = "-" * width
        lines: list[str] = []

        lines.append("")
        lines.append(border)
        lines.append("ARCHAEOLOGICAL RECOVERY DASHBOARD".center(width))
        lines.append("Digital Forensics Command Center".center(width))
        lines.append(border)
        lines.append("")

        summary = engine.get_summary()

        # Overview stats
        lines.append("  EXCAVATION STATISTICS")
        lines.append(thin)
        lines.append(f"  Total Excavations:       {summary['total_excavations']}")
        lines.append(f"  Avg Confidence:          {summary['avg_confidence']:.4f}")
        lines.append(f"  Total Fragments:         {summary['total_fragments']}")
        lines.append(f"  Total Corrupted:         {summary['total_corrupted']}")
        lines.append(f"  Total Conflicts:         {summary['total_conflicts']}")
        lines.append(f"  Avg Excavation Time:     {summary['avg_elapsed_ms']:.2f}ms")
        lines.append("")

        # Classification distribution
        if summary["total_excavations"] > 0:
            dist = summary.get("classification_distribution", {})
            lines.append("  RECONSTRUCTED CLASSIFICATION DISTRIBUTION")
            lines.append(thin)
            total = summary["total_excavations"]
            for cls_name in ["FIZZBUZZ", "FIZZ", "BUZZ", "PLAIN"]:
                count = dist.get(cls_name, 0)
                pct = (count / total * 100) if total > 0 else 0
                bar_len = int(pct / 100 * 30)
                bar = "#" * bar_len + "." * (30 - bar_len)
                lines.append(f"  {cls_name:10s}  [{bar}] {count:3d} ({pct:5.1f}%)")
            lines.append("")

        # Strata reliability weights
        if show_strata:
            lines.append("  STRATA RELIABILITY WEIGHTS")
            lines.append(thin)
            for stratum in EvidenceStratum:
                weight = DEFAULT_STRATA_WEIGHTS.get(stratum.value, 0.0)
                bar_len = int(weight * 30)
                bar = "|" * bar_len + "." * (30 - bar_len)
                lines.append(f"  {stratum.value:24s}  [{bar}] {weight:.1f}")
            lines.append("")

        # Bayesian priors
        if show_bayesian:
            lines.append("  BAYESIAN PRIOR DISTRIBUTION")
            lines.append(thin)
            for cls in FizzBuzzClassification:
                prior = BayesianReconstructor.PRIORS[cls]
                bar_len = int(prior * 40)
                bar = "|" * bar_len
                lines.append(f"  P({cls.name:10s}) = {prior:.4f}  {bar}")
            lines.append("")

        # Corruption summary
        if show_corruption and summary["total_excavations"] > 0:
            corruption_rate = (
                summary["total_corrupted"] / summary["total_fragments"] * 100
                if summary["total_fragments"] > 0
                else 0
            )
            lines.append("  CORRUPTION ANALYSIS")
            lines.append(thin)
            lines.append(f"  Observed Corruption Rate: {corruption_rate:.1f}%")
            lines.append(f"  Corrupted Fragments:     {summary['total_corrupted']}/{summary['total_fragments']}")
            lines.append("")

        # Excavation history (last 10)
        history = engine.excavation_history
        if history:
            lines.append("  RECENT EXCAVATIONS (last 10)")
            lines.append(thin)
            for entry in history[-10:]:
                conf_bar = "#" * int(entry["confidence"] * 10)
                corrupt_flag = " [CORRUPT]" if entry["corrupted"] > 0 else ""
                conflict_flag = f" [{entry['conflicts']} conflicts]" if entry["conflicts"] > 0 else ""
                lines.append(
                    f"  #{entry['number']:5d} -> {entry['classification']:10s} "
                    f"conf={entry['confidence']:.3f} [{conf_bar:10s}]"
                    f"{corrupt_flag}{conflict_flag}"
                )
            lines.append("")

        # Philosophical footer
        lines.append(thin)
        lines.append("  EFFICIENCY NOTE:".center(width))
        if summary["total_excavations"] > 0:
            lines.append(
                f"  These {summary['total_excavations']} excavation(s) recovered data that".center(width)
            )
            lines.append(
                f"  could have been computed via 'n%3==0 or n%5==0'.".center(width)
            )
            total_ms = summary["avg_elapsed_ms"] * summary["total_excavations"]
            lines.append(
                f"  Total archaeology time: {total_ms:.2f}ms.".center(width)
            )
            lines.append(
                f"  Equivalent modulo time: ~0.001ms.".center(width)
            )
        lines.append(border)
        lines.append("")

        return "\n".join(lines)


# ============================================================
# ArchaeologyMiddleware
# ============================================================


class ArchaeologyMiddleware(IMiddleware):
    """Middleware that automatically excavates evidence for every number
    processed through the FizzBuzz pipeline.

    Runs at priority 900 — near the end of the middleware chain, after
    all other subsystems have had their say. This ensures the archaeological
    record contains evidence from the most complete pipeline state possible.

    For each number, the middleware:
    1. Delegates to the next handler in the chain (normal processing)
    2. Triggers an archaeological excavation (forensic overkill)
    3. Stores the excavation result in the context metadata
    4. Logs a summary of the excavation findings

    The middleware does NOT modify the actual FizzBuzz result — it merely
    conducts a parallel investigation into what the result *should* be
    and then files the findings in a metadata field that nobody will read.
    """

    def __init__(self, engine: ArchaeologyEngine) -> None:
        self._engine = engine

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the number through the pipeline, then excavate."""
        # Let the pipeline do its thing first
        result = next_handler(context)

        # Now conduct a parallel archaeological investigation
        try:
            number = context.number
            raw_fragments = self._engine.collector.collect_all(number)

            if self._engine._enable_corruption:
                fragments = [
                    self._engine.corruption_simulator.maybe_corrupt(f)
                    for f in raw_fragments
                ]
            else:
                fragments = raw_fragments

            posteriors = self._engine.reconstructor.reconstruct(fragments)
            best_class, best_prob = self._engine.reconstructor.classify(fragments)

            result.metadata["archaeology"] = {
                "reconstructed_class": best_class.name,
                "posterior_confidence": best_prob,
                "fragments_recovered": len(fragments),
                "corrupted_fragments": sum(1 for f in fragments if f.corrupted),
                "posteriors": {cls.name: prob for cls, prob in posteriors.items()},
            }

            # Record in excavation history
            self._engine._excavation_history.append({
                "number": number,
                "classification": best_class.name,
                "confidence": best_prob,
                "fragments": len(fragments),
                "corrupted": sum(1 for f in fragments if f.corrupted),
                "conflicts": len(self._engine.stratigraphy.detect_conflicts(fragments)),
                "elapsed_ms": 0.0,  # Not measured in middleware mode
            })

        except Exception as exc:
            logger.debug("Archaeological excavation failed for %d: %s", context.number, exc)
            result.metadata["archaeology"] = {"error": str(exc)}

        return result

    def get_name(self) -> str:
        return "ArchaeologyMiddleware"

    def get_priority(self) -> int:
        return 900

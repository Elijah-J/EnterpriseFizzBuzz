"""
Enterprise FizzBuzz Platform - A/B Testing Framework Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ABTestingError(FizzBuzzError):
    """Base exception for all A/B Testing Framework errors.

    When your experiment to determine whether modulo arithmetic
    works differently through a neural network encounters an error,
    this is the exception that catches the existential irony.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-AB00"),
            context=kwargs.pop("context", {}),
        )


class ExperimentNotFoundError(ABTestingError):
    """Raised when a referenced experiment does not exist in the registry.

    You asked for an experiment that we have no record of. Either it
    was never created, it was concluded and garbage-collected, or it
    exists in a parallel universe where someone actually needed to
    A/B test FizzBuzz evaluation strategies.
    """

    def __init__(self, experiment_name: str) -> None:
        super().__init__(
            f"Experiment '{experiment_name}' not found in the registry. "
            f"It may have never existed, or it concluded that modulo always wins.",
            error_code="EFP-AB01",
            context={"experiment_name": experiment_name},
        )


class ExperimentAlreadyExistsError(ABTestingError):
    """Raised when attempting to create an experiment with a duplicate name.

    You tried to create an experiment that already exists. The scientific
    method frowns upon duplicate experiments — unless you're trying to
    replicate results, in which case, the modulo operator will give you
    identical results every time, confirming reproducibility.
    """

    def __init__(self, experiment_name: str) -> None:
        super().__init__(
            f"Experiment '{experiment_name}' already exists. "
            f"Creating duplicate experiments is a violation of the "
            f"FizzBuzz Scientific Integrity Policy.",
            error_code="EFP-AB02",
            context={"experiment_name": experiment_name},
        )


class ExperimentStateError(ABTestingError):
    """Raised when an experiment operation is invalid for the current state.

    You attempted to perform an operation that is not valid for the
    experiment's current lifecycle state. Starting a concluded experiment,
    stopping a not-yet-started experiment, or ramping a paused experiment
    are all examples of temporal violations that this exception prevents.
    """

    def __init__(self, experiment_name: str, current_state: str, attempted_action: str) -> None:
        super().__init__(
            f"Cannot {attempted_action} experiment '{experiment_name}': "
            f"experiment is in state '{current_state}'. "
            f"The experiment lifecycle is a one-way street, much like entropy.",
            error_code="EFP-AB03",
            context={
                "experiment_name": experiment_name,
                "current_state": current_state,
                "attempted_action": attempted_action,
            },
        )


class InsufficientSampleSizeError(ABTestingError):
    """Raised when statistical analysis is requested with too few samples.

    You cannot draw statistically significant conclusions from three
    data points, no matter how confidently the product manager insists
    that "the trend is clear." The central limit theorem has feelings
    too, and those feelings require at least 30 samples.
    """

    def __init__(self, experiment_name: str, current_samples: int, required_samples: int) -> None:
        super().__init__(
            f"Experiment '{experiment_name}' has only {current_samples} samples "
            f"(minimum {required_samples} required). "
            f"Statistical significance requires patience, not enthusiasm.",
            error_code="EFP-AB04",
            context={
                "experiment_name": experiment_name,
                "current_samples": current_samples,
                "required_samples": required_samples,
            },
        )


class MutualExclusionError(ABTestingError):
    """Raised when a number would be enrolled in conflicting experiments.

    The mutual exclusion layer has detected that enrolling this number
    in the requested experiment would violate the isolation guarantee.
    A number cannot simultaneously be in two experiments that test the
    same dimension of FizzBuzz evaluation, because cross-contamination
    of modulo arithmetic results is a scientific sin of the highest order.
    """

    def __init__(self, number: int, experiment_a: str, experiment_b: str) -> None:
        super().__init__(
            f"Number {number} cannot be enrolled in experiment '{experiment_a}': "
            f"it is already enrolled in conflicting experiment '{experiment_b}'. "
            f"Mutual exclusion is not a suggestion — it is the law.",
            error_code="EFP-AB05",
            context={
                "number": number,
                "experiment_a": experiment_a,
                "experiment_b": experiment_b,
            },
        )


class TrafficAllocationError(ABTestingError):
    """Raised when traffic allocation exceeds 100% or is otherwise invalid.

    The total traffic allocation across all active experiments exceeds
    the mathematically permissible maximum of 100%. While the platform
    appreciates your ambition in wanting to test more hypotheses than
    you have traffic for, the laws of arithmetic are non-negotiable.
    """

    def __init__(self, total_allocation: float, experiment_name: str) -> None:
        super().__init__(
            f"Cannot allocate traffic for experiment '{experiment_name}': "
            f"total allocation would be {total_allocation:.1f}%, which exceeds 100%. "
            f"Even enterprise FizzBuzz cannot evaluate more numbers than exist.",
            error_code="EFP-AB06",
            context={
                "total_allocation": total_allocation,
                "experiment_name": experiment_name,
            },
        )


class AutoRollbackTriggeredError(ABTestingError):
    """Raised when an experiment is automatically rolled back due to safety violations.

    The treatment variant's accuracy has dropped below the safety threshold,
    triggering an automatic rollback to the control variant. This is the
    A/B testing equivalent of the circuit breaker pattern: when the new
    thing is demonstrably worse than the old thing, we stop the new thing.
    In FizzBuzz terms: the ML engine couldn't outperform modulo arithmetic.
    Shocking absolutely no one.
    """

    def __init__(self, experiment_name: str, treatment_accuracy: float, threshold: float) -> None:
        super().__init__(
            f"Auto-rollback triggered for experiment '{experiment_name}': "
            f"treatment accuracy {treatment_accuracy:.2%} fell below "
            f"safety threshold {threshold:.2%}. Modulo wins again.",
            error_code="EFP-AB07",
            context={
                "experiment_name": experiment_name,
                "treatment_accuracy": treatment_accuracy,
                "threshold": threshold,
            },
        )


class StatisticalAnalysisError(ABTestingError):
    """Raised when statistical analysis encounters a computational error.

    The chi-squared test, implemented from scratch because importing
    scipy for a FizzBuzz project would be too sensible, has encountered
    a mathematical impossibility. This could be a division by zero, an
    overflow, or the universe informing us that some hypotheses are
    not meant to be tested.
    """

    def __init__(self, experiment_name: str, reason: str) -> None:
        super().__init__(
            f"Statistical analysis failed for experiment '{experiment_name}': {reason}. "
            f"The chi-squared distribution is disappointed in you.",
            error_code="EFP-AB08",
            context={"experiment_name": experiment_name, "reason": reason},
        )


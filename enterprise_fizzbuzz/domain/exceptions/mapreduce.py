"""
Enterprise FizzBuzz Platform - MapReduce Framework Exceptions (EFP-MR00 through EFP-MR03)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class MapReduceError(FizzBuzzError):
    """Base exception for all FizzReduce MapReduce framework errors.

    The MapReduce pipeline involves input splitting, parallel mapping,
    shuffle-and-sort, and reduction. Any failure in any of these
    phases warrants an exception that carries enough diagnostic
    context to reconstruct the failure scenario in a post-mortem.
    This is the root of the MapReduce exception hierarchy.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-MR00"),
            context=kwargs.pop("context", {}),
        )


class MapperError(MapReduceError):
    """Raised when a mapper task fails during FizzBuzz evaluation.

    A mapper is responsible for evaluating a split of the input range
    through the StandardRuleEngine and emitting (classification_key, 1)
    pairs. When a mapper fails — whether due to an invalid input split,
    a rule engine malfunction, or a cosmic ray flipping a bit in the
    modulo ALU — this exception captures the split ID, the offending
    number range, and the root cause. The JobTracker uses this to
    decide whether to retry, launch a speculative duplicate, or
    escalate to the FizzBuzz Incident Response Team.
    """

    def __init__(self, split_id: str, detail: str) -> None:
        self.split_id = split_id
        self.detail = detail
        super().__init__(
            f"Mapper failed on split '{split_id}': {detail}. "
            f"The mapper task has been marked as FAILED. The JobTracker "
            f"may launch a speculative replacement if straggler detection "
            f"thresholds have been exceeded.",
            error_code="EFP-MR01",
            context={"split_id": split_id, "detail": detail},
        )


class ReducerError(MapReduceError):
    """Raised when a reducer task fails during value aggregation.

    Reducers aggregate shuffled (key, [values]) groups into final
    classification counts. A reducer failure means the world will
    never know exactly how many numbers in the input range were
    classified as 'Fizz'. This is an unacceptable outcome for any
    enterprise with regulatory obligations around FizzBuzz accuracy.
    """

    def __init__(self, reducer_id: int, detail: str) -> None:
        self.reducer_id = reducer_id
        self.detail = detail
        super().__init__(
            f"Reducer {reducer_id} failed: {detail}. "
            f"Partial aggregation results have been discarded. "
            f"The job cannot produce a complete classification distribution.",
            error_code="EFP-MR02",
            context={"reducer_id": reducer_id, "detail": detail},
        )


class ShuffleError(MapReduceError):
    """Raised when the shuffle-and-sort phase encounters a failure.

    The shuffle phase is responsible for hash-partitioning mapper
    output by classification key across reducer slots. A shuffle
    failure could result in misrouted key-value pairs, meaning
    'Fizz' counts end up in the 'Buzz' reducer's partition. The
    implications for data integrity are catastrophic. In a real
    Hadoop cluster, this would trigger a full job restart. Here,
    it triggers this exception and a strongly-worded log message.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(
            f"Shuffle-and-sort phase failed: {detail}. "
            f"Key-value partition integrity cannot be guaranteed. "
            f"All mapper outputs must be re-shuffled from scratch.",
            error_code="EFP-MR03",
            context={"detail": detail},
        )


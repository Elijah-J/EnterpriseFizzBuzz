"""
Enterprise FizzBuzz Platform - FizzBloom Probabilistic Data Structures Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ProbabilisticError(FizzBuzzError):
    """Raised when a probabilistic data structure encounters an error.

    The Enterprise FizzBuzz Platform employs four probabilistic data
    structures for approximate analytics over evaluation streams.
    When any of these structures encounters an invalid configuration,
    capacity overflow, or numerical instability, this exception
    hierarchy provides precise diagnostics.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-PROB0",
            context={"subsystem": "fizzbloom"},
        )


class BloomFilterCapacityError(ProbabilisticError):
    """Raised when a Bloom filter exceeds its designed capacity.

    A Bloom filter sized for n elements with target false positive
    rate p will experience degraded accuracy once the number of
    inserted elements exceeds n. This exception signals that the
    actual false positive rate has exceeded the configured threshold
    and the filter should be rebuilt with larger parameters.
    """

    def __init__(self, current_count: int, capacity: int, fpr: float) -> None:
        self.current_count = current_count
        self.capacity = capacity
        self.fpr = fpr
        super().__init__(
            f"Bloom filter capacity exceeded: {current_count}/{capacity} elements, "
            f"actual FPR {fpr:.6f} exceeds design threshold",
        )
        self.error_code = "EFP-PROB1"


class CountMinSketchOverflowError(ProbabilisticError):
    """Raised when a Count-Min Sketch counter exceeds its maximum value.

    Each cell in the Count-Min Sketch is a bounded integer counter.
    If the evaluation stream is sufficiently long, a counter may
    overflow. This exception indicates the sketch should be reset
    or widened.
    """

    def __init__(self, row: int, col: int, value: int) -> None:
        self.row = row
        self.col = col
        self.value = value
        super().__init__(
            f"Count-Min Sketch counter overflow at row={row}, col={col}: "
            f"value {value} exceeds 64-bit signed integer range",
        )
        self.error_code = "EFP-PROB2"


class HyperLogLogPrecisionError(ProbabilisticError):
    """Raised when a HyperLogLog estimator is configured with invalid precision.

    The precision parameter p must be in the range [4, 18]. Values
    outside this range either produce unacceptably high estimation
    error (p < 4) or consume excessive memory for negligible accuracy
    improvement (p > 18). The standard error of a HyperLogLog
    estimator is approximately 1.04 / sqrt(2^p).
    """

    def __init__(self, precision: int) -> None:
        self.precision = precision
        super().__init__(
            f"HyperLogLog precision {precision} is out of valid range [4, 18]. "
            f"Standard error at p={precision} would be "
            f"{'unacceptably high' if precision < 4 else 'memory-wasteful'}.",
        )
        self.error_code = "EFP-PROB3"


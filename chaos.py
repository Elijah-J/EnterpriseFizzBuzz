"""Backward-compatible re-export stub for chaos."""
from enterprise_fizzbuzz.infrastructure.chaos import *  # noqa: F401,F403
from enterprise_fizzbuzz.infrastructure.chaos import (  # noqa: F401
    _compute_grade,
    _render_histogram,
    _render_percentile_table,
    _render_bottleneck_ranking,
    _GRADE_COMMENTARY,
)

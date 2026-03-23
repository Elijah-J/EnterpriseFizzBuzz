"""
Enterprise FizzBuzz Platform - FizzReduce MapReduce Framework

Implements a complete MapReduce pipeline for distributed FizzBuzz
computation. Because evaluating whether numbers are divisible by 3
and 5 is a problem that clearly demands the same computational
framework Google invented to index the entire World Wide Web.

The pipeline follows the canonical MapReduce data flow:

    Input Range -> InputSplitter -> [InputSplit, ...]
                                        |
                                    [Mapper, ...]  (parallel via ThreadPoolExecutor)
                                        |
                                    [MapperOutput, ...]  (key-value pairs)
                                        |
                                    ShuffleSorter  (group by key, hash-partition)
                                        |
                                    [Reducer, ...]  (sum values per key)
                                        |
                                    {classification: count}

Speculative execution detects straggler mappers running >1.5x the
average completion time and launches duplicate tasks, because no
enterprise can tolerate a slow modulo operation holding up the
entire FizzBuzz job.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    MapperError,
    MapReduceError,
    ReducerError,
    ShuffleError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class TaskStatus(Enum):
    """Lifecycle states for mapper and reducer tasks.

    Every task in the FizzReduce framework traverses this state
    machine. PENDING tasks are waiting for a thread. RUNNING tasks
    are actively computing modulo arithmetic (the most computationally
    intensive operation known to enterprise software). COMPLETED
    tasks have finished successfully. FAILED tasks encountered an
    error. SPECULATIVE tasks are duplicate copies launched to
    race against a suspected straggler.
    """

    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    SPECULATIVE = auto()


class JobState(Enum):
    """State machine for a MapReduce job.

    SUBMITTED -> SPLITTING -> MAPPING -> SHUFFLING -> REDUCING -> COMPLETED

    Each transition is logged, timed, and auditable. A job that
    reaches COMPLETED has successfully distributed the evaluation
    of FizzBuzz across multiple threads, achieved the exact same
    result as a simple for loop, and consumed approximately 100x
    the CPU cycles. This is what enterprise readiness looks like.
    """

    SUBMITTED = auto()
    SPLITTING = auto()
    MAPPING = auto()
    SHUFFLING = auto()
    REDUCING = auto()
    COMPLETED = auto()
    FAILED = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class InputSplit:
    """A chunk of the input range assigned to a single mapper.

    In a real Hadoop cluster, an InputSplit corresponds to an HDFS
    block (typically 128MB). Here, it corresponds to a range of
    integers that need to be checked for divisibility by 3 and 5.
    The scale may differ, but the abstraction is identical.
    """

    start: int
    end: int
    split_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    @property
    def size(self) -> int:
        """Number of integers in this split."""
        return max(0, self.end - self.start + 1)

    def __repr__(self) -> str:
        return f"InputSplit(id={self.split_id}, range=[{self.start}, {self.end}], size={self.size})"


@dataclass(frozen=True)
class MapperOutput:
    """A single (classification_key, count) pair emitted by a mapper.

    Following the canonical MapReduce model, mappers emit intermediate
    key-value pairs. The key is the FizzBuzz classification (e.g.,
    'Fizz', 'Buzz', 'FizzBuzz', or a plain number string), and the
    value is always 1. The reducer will sum these values to produce
    final counts. Yes, we could just use a Counter. But that would
    not be MapReduce.
    """

    key: str
    value: int = 1
    source_split_id: str = ""


@dataclass
class TaskTracker:
    """Wraps a task with status tracking, timing, and heartbeat.

    Every mapper and reducer task is wrapped in a TaskTracker that
    monitors its lifecycle. The heartbeat mechanism allows the
    JobTracker to detect straggler tasks that may need speculative
    replacement. In production Hadoop, heartbeats are sent over RPC
    every 3 seconds. Here, we check elapsed wall-clock time, which
    is arguably more reliable than network-based heartbeats.
    """

    task_id: str
    task_type: str  # "mapper" or "reducer"
    status: TaskStatus = TaskStatus.PENDING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    heartbeat_time: Optional[float] = None
    error: Optional[str] = None
    result: Any = None
    is_speculative: bool = False

    @property
    def elapsed_seconds(self) -> float:
        """Time elapsed since task start, or total duration if completed."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.monotonic()
        return end - self.start_time

    def start(self) -> None:
        """Mark the task as running."""
        self.status = TaskStatus.RUNNING
        self.start_time = time.monotonic()
        self.heartbeat_time = self.start_time

    def complete(self, result: Any = None) -> None:
        """Mark the task as completed."""
        self.status = TaskStatus.COMPLETED
        self.end_time = time.monotonic()
        self.result = result

    def fail(self, error: str) -> None:
        """Mark the task as failed."""
        self.status = TaskStatus.FAILED
        self.end_time = time.monotonic()
        self.error = error

    def heartbeat(self) -> None:
        """Update the heartbeat timestamp."""
        self.heartbeat_time = time.monotonic()


# ============================================================
# Mapper
# ============================================================


class Mapper:
    """Evaluates numbers in an InputSplit via StandardRuleEngine.

    Each mapper receives a split of the input range and evaluates
    every number through the rule engine. For each evaluation, the
    mapper emits a (classification_key, 1) pair. The classification
    key is the concatenated label of all matched rules, or the string
    representation of the number if no rules match.

    This is functionally equivalent to a for loop with an if statement,
    but with the dignity and gravitas of a distributed computation node.
    """

    def __init__(
        self,
        rules: list[RuleDefinition],
        engine: Optional[StandardRuleEngine] = None,
    ) -> None:
        self._rules = [ConcreteRule(rd) for rd in rules]
        self._engine = engine or StandardRuleEngine()

    def map(self, split: InputSplit) -> list[MapperOutput]:
        """Process an InputSplit and emit key-value pairs.

        Each number in the split is evaluated by the rule engine.
        The output classification becomes the key, and the value
        is always 1 (the atomic unit of FizzBuzz counting).
        """
        outputs: list[MapperOutput] = []

        for number in range(split.start, split.end + 1):
            result = self._engine.evaluate(number, self._rules)
            classification = result.output
            outputs.append(
                MapperOutput(
                    key=classification,
                    value=1,
                    source_split_id=split.split_id,
                )
            )

        logger.debug(
            "Mapper processed split %s: %d numbers -> %d key-value pairs",
            split.split_id,
            split.size,
            len(outputs),
        )
        return outputs


# ============================================================
# ShuffleSorter
# ============================================================


class ShuffleSorter:
    """Groups mapper output by key and hash-partitions across reducers.

    The shuffle-and-sort phase is the beating heart of MapReduce.
    It takes the flat list of (key, value) pairs from all mappers,
    groups them by key, sorts the keys, and hash-partitions the
    groups across reducer slots.

    The hash function uses SHA-256 because MD5 is considered
    cryptographically weak, and we take FizzBuzz classification
    partitioning very seriously from a security standpoint.
    """

    def __init__(self, num_reducers: int) -> None:
        if num_reducers < 1:
            raise ShuffleError(
                f"Cannot shuffle into {num_reducers} reducer partitions. "
                f"At least one reducer is required to aggregate results."
            )
        self._num_reducers = num_reducers

    def _hash_partition(self, key: str) -> int:
        """Determine which reducer partition a key belongs to.

        Uses the hash of the key modulo the number of reducers.
        The irony of using modulo to partition FizzBuzz modulo
        results is not lost on the engineering team.
        """
        key_hash = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
        return key_hash % self._num_reducers

    def shuffle(
        self, mapper_outputs: list[MapperOutput]
    ) -> dict[int, dict[str, list[int]]]:
        """Group and partition mapper outputs for reducers.

        Returns a dict mapping reducer_id -> {key: [values]}.
        Each reducer receives only the keys assigned to its partition
        by the hash function.
        """
        if not mapper_outputs:
            return {i: {} for i in range(self._num_reducers)}

        # Group by key
        grouped: dict[str, list[int]] = defaultdict(list)
        for output in mapper_outputs:
            grouped[output.key].append(output.value)

        # Partition across reducers
        partitions: dict[int, dict[str, list[int]]] = {
            i: {} for i in range(self._num_reducers)
        }

        for key in sorted(grouped.keys()):
            reducer_id = self._hash_partition(key)
            partitions[reducer_id][key] = grouped[key]

        total_keys = len(grouped)
        total_values = sum(len(v) for v in grouped.values())
        logger.debug(
            "Shuffle complete: %d unique keys, %d total values -> %d partitions",
            total_keys,
            total_values,
            self._num_reducers,
        )

        return partitions

    def get_partition_stats(
        self, partitions: dict[int, dict[str, list[int]]]
    ) -> dict[str, Any]:
        """Compute statistics about the shuffle partition distribution."""
        partition_sizes = {
            rid: sum(len(v) for v in keys.values())
            for rid, keys in partitions.items()
        }
        total = sum(partition_sizes.values())
        return {
            "num_partitions": len(partitions),
            "total_records": total,
            "partition_sizes": partition_sizes,
            "max_skew": (
                max(partition_sizes.values()) / max(total / len(partitions), 1)
                if partition_sizes and total > 0
                else 0.0
            ),
        }


# ============================================================
# Reducer
# ============================================================


class Reducer:
    """Sums values per key to produce classification counts.

    Each reducer receives a partition of (key, [values]) groups
    from the shuffle phase and sums the values for each key.
    The result is a dictionary mapping classification keys to
    their total counts.

    This is functionally equivalent to sum(). But in MapReduce,
    we call it a Reducer, capitalize it, and give it its own class.
    """

    def __init__(self, reducer_id: int) -> None:
        self._reducer_id = reducer_id

    @property
    def reducer_id(self) -> int:
        return self._reducer_id

    def reduce(self, partition: dict[str, list[int]]) -> dict[str, int]:
        """Reduce a partition by summing values per key.

        For FizzBuzz, each value is 1, so summing gives the count
        of numbers with that classification. Revolutionary.
        """
        result: dict[str, int] = {}

        for key in sorted(partition.keys()):
            values = partition[key]
            result[key] = sum(values)

        logger.debug(
            "Reducer %d processed %d keys -> %s",
            self._reducer_id,
            len(partition),
            result,
        )
        return result


# ============================================================
# SpeculativeExecutor
# ============================================================


class SpeculativeExecutor:
    """Detects straggler tasks and launches speculative duplicates.

    In Google's original MapReduce paper, speculative execution
    (called "backup tasks") was responsible for a 44% reduction
    in job completion time. Here, it detects mapper tasks that
    take more than 1.5x the average completion time and launches
    duplicate copies. For FizzBuzz evaluation, where each mapper
    completes in microseconds, straggler detection is unlikely
    to trigger. But we implement it anyway, because enterprise
    readiness demands preparedness for edge cases that will
    never occur.
    """

    def __init__(self, threshold: float = 1.5) -> None:
        self._threshold = threshold
        self._speculative_launches: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def speculative_launches(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._speculative_launches)

    def detect_stragglers(
        self, trackers: list[TaskTracker]
    ) -> list[TaskTracker]:
        """Identify tasks running longer than threshold * avg completed time.

        Returns a list of TaskTracker objects that are suspected stragglers.
        A straggler is a running task whose elapsed time exceeds the
        speculative threshold multiplied by the average completion time
        of already-completed tasks.
        """
        completed = [
            t for t in trackers if t.status == TaskStatus.COMPLETED
        ]
        if not completed:
            return []

        avg_time = sum(t.elapsed_seconds for t in completed) / len(completed)
        straggler_threshold = self._threshold * avg_time

        running = [
            t
            for t in trackers
            if t.status == TaskStatus.RUNNING and not t.is_speculative
        ]

        stragglers = [
            t for t in running if t.elapsed_seconds > straggler_threshold
        ]

        if stragglers:
            logger.info(
                "Speculative executor detected %d straggler(s) "
                "(threshold=%.3fs, avg_completed=%.3fs)",
                len(stragglers),
                straggler_threshold,
                avg_time,
            )

        return stragglers

    def record_launch(
        self, original_task_id: str, speculative_task_id: str
    ) -> None:
        """Record a speculative task launch for audit purposes."""
        with self._lock:
            self._speculative_launches.append(
                {
                    "original_task_id": original_task_id,
                    "speculative_task_id": speculative_task_id,
                    "launch_time": time.monotonic(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )


# ============================================================
# JobTracker
# ============================================================


class JobTracker:
    """Splits input, assigns tasks, and monitors progress.

    The JobTracker is the master coordinator of the MapReduce job.
    It splits the input range into InputSplits, assigns mapper
    tasks to threads, monitors task progress, and coordinates
    the shuffle-and-sort phase. In Hadoop, the JobTracker runs
    on a dedicated master node. Here, it runs in the same process
    as everything else, because our FizzBuzz cluster is a single
    Python interpreter.
    """

    def __init__(
        self,
        num_mappers: int = 4,
        num_reducers: int = 2,
        speculative_threshold: float = 1.5,
    ) -> None:
        self._num_mappers = max(1, num_mappers)
        self._num_reducers = max(1, num_reducers)
        self._speculative_executor = SpeculativeExecutor(speculative_threshold)
        self._task_trackers: list[TaskTracker] = []
        self._lock = threading.Lock()

    @property
    def num_mappers(self) -> int:
        return self._num_mappers

    @property
    def num_reducers(self) -> int:
        return self._num_reducers

    @property
    def task_trackers(self) -> list[TaskTracker]:
        with self._lock:
            return list(self._task_trackers)

    @property
    def speculative_executor(self) -> SpeculativeExecutor:
        return self._speculative_executor

    def create_splits(self, start: int, end: int) -> list[InputSplit]:
        """Divide the input range into splits for mappers.

        The range is divided as evenly as possible across mappers.
        If the range doesn't divide evenly, the last split absorbs
        the remainder. This mirrors HDFS block splitting, except
        instead of 128MB blocks of web crawl data, we're splitting
        ranges of integers that need modulo arithmetic applied to them.
        """
        total = end - start + 1
        if total <= 0:
            return []

        num_splits = min(self._num_mappers, total)
        base_size = total // num_splits
        remainder = total % num_splits

        splits: list[InputSplit] = []
        current = start

        for i in range(num_splits):
            split_size = base_size + (1 if i < remainder else 0)
            split_end = current + split_size - 1
            splits.append(InputSplit(start=current, end=split_end))
            current = split_end + 1

        logger.debug(
            "Created %d splits for range [%d, %d]: %s",
            len(splits),
            start,
            end,
            [f"[{s.start},{s.end}]" for s in splits],
        )
        return splits

    def register_task(self, task_type: str, is_speculative: bool = False) -> TaskTracker:
        """Register a new task with the JobTracker."""
        tracker = TaskTracker(
            task_id=str(uuid.uuid4())[:8],
            task_type=task_type,
            is_speculative=is_speculative,
        )
        with self._lock:
            self._task_trackers.append(tracker)
        return tracker

    def get_progress(self) -> dict[str, Any]:
        """Get current job progress statistics."""
        with self._lock:
            trackers = list(self._task_trackers)

        mapper_trackers = [t for t in trackers if t.task_type == "mapper"]
        reducer_trackers = [t for t in trackers if t.task_type == "reducer"]

        def _stats(task_list: list[TaskTracker]) -> dict[str, int]:
            return {
                "total": len(task_list),
                "pending": sum(1 for t in task_list if t.status == TaskStatus.PENDING),
                "running": sum(1 for t in task_list if t.status == TaskStatus.RUNNING),
                "completed": sum(1 for t in task_list if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in task_list if t.status == TaskStatus.FAILED),
                "speculative": sum(1 for t in task_list if t.is_speculative),
            }

        return {
            "mappers": _stats(mapper_trackers),
            "reducers": _stats(reducer_trackers),
            "speculative_launches": len(self._speculative_executor.speculative_launches),
        }


# ============================================================
# MapReduceJob
# ============================================================


class MapReduceJob:
    """Top-level MapReduce job orchestrator.

    Manages the complete lifecycle of a FizzReduce job through the
    state machine: SUBMITTED -> SPLITTING -> MAPPING -> SHUFFLING ->
    REDUCING -> COMPLETED.

    The job coordinates all components: it splits input, launches
    mappers via ThreadPoolExecutor, monitors for stragglers, runs
    the shuffle-and-sort, launches reducers, and merges final results.

    For a range of 1-15, the expected output is:
        Fizz: 4, Buzz: 2, FizzBuzz: 1, plain numbers: 8

    This distribution is immutable mathematical truth, regardless
    of whether you compute it with a for loop or a full MapReduce
    framework. The framework exists not because it's necessary,
    but because it's architecturally inevitable.
    """

    def __init__(
        self,
        rules: list[RuleDefinition],
        num_mappers: int = 4,
        num_reducers: int = 2,
        speculative_threshold: float = 1.5,
    ) -> None:
        self._rules = rules
        self._job_id = str(uuid.uuid4())[:12]
        self._state = JobState.SUBMITTED
        self._state_history: list[tuple[JobState, float]] = [
            (JobState.SUBMITTED, time.monotonic())
        ]
        self._job_tracker = JobTracker(
            num_mappers=num_mappers,
            num_reducers=num_reducers,
            speculative_threshold=speculative_threshold,
        )
        self._splits: list[InputSplit] = []
        self._mapper_outputs: list[MapperOutput] = []
        self._shuffle_partitions: dict[int, dict[str, list[int]]] = {}
        self._shuffle_stats: dict[str, Any] = {}
        self._final_results: dict[str, int] = {}
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def state(self) -> JobState:
        return self._state

    @property
    def state_history(self) -> list[tuple[JobState, float]]:
        return list(self._state_history)

    @property
    def job_tracker(self) -> JobTracker:
        return self._job_tracker

    @property
    def splits(self) -> list[InputSplit]:
        return list(self._splits)

    @property
    def final_results(self) -> dict[str, int]:
        return dict(self._final_results)

    @property
    def shuffle_stats(self) -> dict[str, Any]:
        return dict(self._shuffle_stats)

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        end = self._end_time or time.monotonic()
        return end - self._start_time

    def _transition(self, new_state: JobState) -> None:
        """Transition the job to a new state."""
        old_state = self._state
        self._state = new_state
        self._state_history.append((new_state, time.monotonic()))
        logger.info(
            "Job %s: %s -> %s",
            self._job_id,
            old_state.name,
            new_state.name,
        )

    def execute(self, start: int, end: int) -> dict[str, int]:
        """Execute the complete MapReduce pipeline.

        This is the main entry point. It orchestrates all phases
        of the MapReduce job and returns the final classification
        distribution.
        """
        self._start_time = time.monotonic()

        try:
            # Phase 1: Splitting
            self._transition(JobState.SPLITTING)
            self._splits = self._job_tracker.create_splits(start, end)

            if not self._splits:
                self._transition(JobState.COMPLETED)
                self._end_time = time.monotonic()
                return {}

            # Phase 2: Mapping (parallel)
            self._transition(JobState.MAPPING)
            self._mapper_outputs = self._run_mappers()

            # Phase 3: Shuffle and Sort
            self._transition(JobState.SHUFFLING)
            sorter = ShuffleSorter(self._job_tracker.num_reducers)
            self._shuffle_partitions = sorter.shuffle(self._mapper_outputs)
            self._shuffle_stats = sorter.get_partition_stats(
                self._shuffle_partitions
            )

            # Phase 4: Reducing
            self._transition(JobState.REDUCING)
            self._final_results = self._run_reducers()

            # Phase 5: Done
            self._transition(JobState.COMPLETED)
            self._end_time = time.monotonic()

            logger.info(
                "Job %s completed in %.3fs: %s",
                self._job_id,
                self.elapsed_seconds,
                self._final_results,
            )

            return self._final_results

        except Exception as e:
            self._transition(JobState.FAILED)
            self._end_time = time.monotonic()
            raise MapReduceError(
                f"Job {self._job_id} failed: {e}",
                error_code="EFP-MR00",
                context={"job_id": self._job_id, "state": self._state.name},
            ) from e

    def _run_mappers(self) -> list[MapperOutput]:
        """Run mapper tasks in parallel using ThreadPoolExecutor."""
        all_outputs: list[MapperOutput] = []
        mapper = Mapper(self._rules)

        # Track completed task times for speculative execution
        completed_trackers: list[TaskTracker] = []

        def _map_split(split: InputSplit, tracker: TaskTracker) -> list[MapperOutput]:
            tracker.start()
            try:
                result = mapper.map(split)
                tracker.complete(result)
                return result
            except Exception as e:
                tracker.fail(str(e))
                raise MapperError(split.split_id, str(e)) from e

        with ThreadPoolExecutor(
            max_workers=self._job_tracker.num_mappers,
            thread_name_prefix="fizz-mapper",
        ) as executor:
            futures: dict[Future, tuple[InputSplit, TaskTracker]] = {}

            for split in self._splits:
                tracker = self._job_tracker.register_task("mapper")
                future = executor.submit(_map_split, split, tracker)
                futures[future] = (split, tracker)

            for future in as_completed(futures):
                split, tracker = futures[future]
                try:
                    outputs = future.result()
                    all_outputs.extend(outputs)
                    completed_trackers.append(tracker)

                    # Check for stragglers after each completion
                    all_trackers = self._job_tracker.task_trackers
                    stragglers = self._job_tracker.speculative_executor.detect_stragglers(
                        all_trackers
                    )
                    for straggler in stragglers:
                        # Find the split for the straggling task
                        for f, (s, t) in futures.items():
                            if t.task_id == straggler.task_id and not f.done():
                                spec_tracker = self._job_tracker.register_task(
                                    "mapper", is_speculative=True
                                )
                                self._job_tracker.speculative_executor.record_launch(
                                    straggler.task_id, spec_tracker.task_id
                                )
                                # Launch speculative duplicate
                                spec_future = executor.submit(
                                    _map_split, s, spec_tracker
                                )
                                futures[spec_future] = (s, spec_tracker)
                                break

                except Exception as e:
                    logger.warning(
                        "Mapper task for split %s failed: %s",
                        split.split_id,
                        e,
                    )
                    if not tracker.is_speculative:
                        raise

        return all_outputs

    def _run_reducers(self) -> dict[str, int]:
        """Run reducer tasks and merge results."""
        merged: dict[str, int] = {}

        for reducer_id, partition in self._shuffle_partitions.items():
            tracker = self._job_tracker.register_task("reducer")
            tracker.start()
            try:
                reducer = Reducer(reducer_id)
                result = reducer.reduce(partition)
                tracker.complete(result)

                # Merge into final results
                for key, count in result.items():
                    merged[key] = merged.get(key, 0) + count

            except Exception as e:
                tracker.fail(str(e))
                raise ReducerError(reducer_id, str(e)) from e

        return merged


# ============================================================
# MapReduceDashboard
# ============================================================


class MapReduceDashboard:
    """ASCII dashboard for MapReduce job monitoring.

    Renders a comprehensive view of job status, task progress,
    shuffle statistics, and speculative execution events. Because
    a MapReduce framework without a dashboard is like a monitoring
    system without monitors — technically functional but
    operationally invisible.
    """

    @staticmethod
    def render(job: MapReduceJob, width: int = 60) -> str:
        """Render the FizzReduce dashboard."""
        lines: list[str] = []
        inner = width - 4  # Account for "| " and " |"

        def _box_top() -> str:
            return "  +" + "-" * (width - 2) + "+"

        def _box_bottom() -> str:
            return "  +" + "-" * (width - 2) + "+"

        def _box_line(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def _box_center(text: str) -> str:
            return f"  | {text:^{inner}} |"

        def _box_separator() -> str:
            return "  |" + "-" * (width - 2) + "|"

        # Header
        lines.append("")
        lines.append(_box_top())
        lines.append(_box_center("FizzReduce MapReduce Dashboard"))
        lines.append(_box_center(f"Job ID: {job.job_id}"))
        lines.append(_box_separator())

        # Job State
        lines.append(_box_line(f"State: {job.state.name}"))
        lines.append(_box_line(f"Elapsed: {job.elapsed_seconds:.3f}s"))
        lines.append(_box_separator())

        # State History
        lines.append(_box_center("State Transitions"))
        lines.append(_box_separator())
        base_time = job.state_history[0][1] if job.state_history else 0
        for state, ts in job.state_history:
            elapsed = ts - base_time
            lines.append(_box_line(f"  {elapsed:8.3f}s  {state.name}"))
        lines.append(_box_separator())

        # Input Splits
        lines.append(_box_center("Input Splits"))
        lines.append(_box_separator())
        for split in job.splits:
            lines.append(
                _box_line(
                    f"  [{split.split_id}] range=[{split.start},{split.end}] "
                    f"size={split.size}"
                )
            )
        if not job.splits:
            lines.append(_box_line("  (no splits)"))
        lines.append(_box_separator())

        # Task Progress
        progress = job.job_tracker.get_progress()
        lines.append(_box_center("Task Progress"))
        lines.append(_box_separator())

        for task_type in ["mappers", "reducers"]:
            stats = progress[task_type]
            total = stats["total"]
            completed = stats["completed"]
            pct = (completed / total * 100) if total > 0 else 0
            bar_len = inner - 30
            filled = int(bar_len * pct / 100) if bar_len > 0 else 0
            bar = "#" * filled + "." * (bar_len - filled)
            lines.append(
                _box_line(f"  {task_type.capitalize()}: [{bar}] {pct:.0f}%")
            )
            lines.append(
                _box_line(
                    f"    total={total} done={completed} "
                    f"fail={stats['failed']} spec={stats['speculative']}"
                )
            )

        lines.append(_box_separator())

        # Shuffle Stats
        lines.append(_box_center("Shuffle Statistics"))
        lines.append(_box_separator())
        ss = job.shuffle_stats
        if ss:
            lines.append(
                _box_line(f"  Partitions: {ss.get('num_partitions', 0)}")
            )
            lines.append(
                _box_line(f"  Total records: {ss.get('total_records', 0)}")
            )
            lines.append(
                _box_line(f"  Max skew: {ss.get('max_skew', 0):.2f}x")
            )
            partition_sizes = ss.get("partition_sizes", {})
            for rid, size in sorted(partition_sizes.items()):
                lines.append(
                    _box_line(f"    Reducer {rid}: {size} records")
                )
        else:
            lines.append(_box_line("  (no shuffle data)"))
        lines.append(_box_separator())

        # Speculative Execution
        spec_launches = job.job_tracker.speculative_executor.speculative_launches
        lines.append(_box_center("Speculative Execution"))
        lines.append(_box_separator())
        lines.append(
            _box_line(f"  Threshold: {job.job_tracker.speculative_executor.threshold:.1f}x avg")
        )
        lines.append(_box_line(f"  Launches: {len(spec_launches)}"))
        for launch in spec_launches[:5]:  # Show first 5
            lines.append(
                _box_line(
                    f"    {launch['original_task_id']} -> "
                    f"{launch['speculative_task_id']}"
                )
            )
        if len(spec_launches) > 5:
            lines.append(
                _box_line(f"    ... and {len(spec_launches) - 5} more")
            )
        lines.append(_box_separator())

        # Final Results
        lines.append(_box_center("Classification Distribution"))
        lines.append(_box_separator())
        results = job.final_results
        if results:
            total = sum(results.values())
            for key in sorted(results.keys()):
                count = results[key]
                pct = count / total * 100 if total > 0 else 0
                bar_len = inner - 30
                filled = int(bar_len * pct / 100) if bar_len > 0 else 0
                bar = "#" * filled + "." * (bar_len - filled)
                lines.append(
                    _box_line(f"  {key:>12}: {count:4d} [{bar}]")
                )
            lines.append(_box_separator())
            lines.append(_box_line(f"  Total: {total}"))
        else:
            lines.append(_box_line("  (no results)"))

        lines.append(_box_bottom())
        lines.append("")

        return "\n".join(lines)


# ============================================================
# MapReduceMiddleware
# ============================================================


class MapReduceMiddleware(IMiddleware):
    """Routes FizzBuzz evaluation through the MapReduce pipeline.

    When installed in the middleware pipeline, this middleware
    intercepts evaluations and records them for MapReduce processing.
    The actual MapReduce job is executed separately via the
    MapReduceJob class; this middleware captures per-number
    evaluations and stores the MapReduce context metadata.

    This middleware exists primarily to integrate MapReduce into the
    existing middleware pipeline architecture. The actual distributed
    computation happens in MapReduceJob.execute(), not here —
    because middleware processes one number at a time, while MapReduce
    processes ranges. The middleware adds MapReduce metadata to each
    evaluation context for observability purposes.
    """

    def __init__(self, job: Optional[MapReduceJob] = None) -> None:
        self._job = job
        self._evaluation_count = 0
        self._lock = threading.Lock()

    @property
    def job(self) -> Optional[MapReduceJob]:
        return self._job

    @job.setter
    def job(self, value: MapReduceJob) -> None:
        self._job = value

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Add MapReduce metadata to the processing context."""
        with self._lock:
            self._evaluation_count += 1

        # Add MapReduce metadata to context
        context.metadata["mapreduce_enabled"] = True
        if self._job is not None:
            context.metadata["mapreduce_job_id"] = self._job.job_id
            context.metadata["mapreduce_state"] = self._job.state.name

        return next_handler(context)

    def get_name(self) -> str:
        return "MapReduceMiddleware"

    def get_priority(self) -> int:
        return 920

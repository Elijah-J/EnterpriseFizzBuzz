"""
Tests for the FizzReduce MapReduce Framework.

Validates input splitting, mapper evaluation, shuffle-and-sort
partitioning, reducer aggregation, speculative execution detection,
job lifecycle state machine, dashboard rendering, middleware
integration, and end-to-end correctness for the canonical
range 1-15 (Fizz:4, Buzz:2, FizzBuzz:1, plain:8).
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    MapperError,
    MapReduceError,
    ReducerError,
    ShuffleError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.mapreduce import (
    InputSplit,
    JobState,
    JobTracker,
    Mapper,
    MapperOutput,
    MapReduceDashboard,
    MapReduceJob,
    MapReduceMiddleware,
    Reducer,
    ShuffleSorter,
    SpeculativeExecutor,
    TaskStatus,
    TaskTracker,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# Standard FizzBuzz rules for testing
FIZZ_RULE = RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)
BUZZ_RULE = RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)
STANDARD_RULES = [FIZZ_RULE, BUZZ_RULE]


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestExceptions:
    """Verify the MapReduce exception hierarchy."""

    def test_mapreduce_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = MapReduceError("test")
        assert isinstance(err, FizzBuzzError)

    def test_mapreduce_error_code(self):
        err = MapReduceError("test")
        assert "EFP-MR00" in str(err)

    def test_mapper_error_inherits_mapreduce_error(self):
        err = MapperError("split-1", "evaluation failed")
        assert isinstance(err, MapReduceError)
        assert err.split_id == "split-1"
        assert "EFP-MR01" in str(err)

    def test_reducer_error_inherits_mapreduce_error(self):
        err = ReducerError(0, "aggregation failed")
        assert isinstance(err, MapReduceError)
        assert err.reducer_id == 0
        assert "EFP-MR02" in str(err)

    def test_shuffle_error_inherits_mapreduce_error(self):
        err = ShuffleError("partition failure")
        assert isinstance(err, MapReduceError)
        assert err.detail == "partition failure"
        assert "EFP-MR03" in str(err)

    def test_mapper_error_context(self):
        err = MapperError("split-abc", "bad number")
        assert err.context["split_id"] == "split-abc"
        assert err.context["detail"] == "bad number"

    def test_reducer_error_context(self):
        err = ReducerError(3, "overflow")
        assert err.context["reducer_id"] == 3

    def test_shuffle_error_context(self):
        err = ShuffleError("hash collision")
        assert err.context["detail"] == "hash collision"


# ============================================================
# InputSplit Tests
# ============================================================


class TestInputSplit:
    """Verify InputSplit data class."""

    def test_basic_split(self):
        split = InputSplit(start=1, end=10)
        assert split.start == 1
        assert split.end == 10
        assert split.size == 10

    def test_single_element_split(self):
        split = InputSplit(start=5, end=5)
        assert split.size == 1

    def test_split_id_generated(self):
        s1 = InputSplit(start=1, end=10)
        s2 = InputSplit(start=1, end=10)
        assert s1.split_id != s2.split_id

    def test_split_repr(self):
        split = InputSplit(start=1, end=10, split_id="test-id")
        r = repr(split)
        assert "test-id" in r
        assert "1" in r
        assert "10" in r

    def test_empty_split(self):
        split = InputSplit(start=10, end=5)
        assert split.size == 0

    def test_split_is_frozen(self):
        split = InputSplit(start=1, end=10)
        with pytest.raises(AttributeError):
            split.start = 2


# ============================================================
# MapperOutput Tests
# ============================================================


class TestMapperOutput:
    """Verify MapperOutput data class."""

    def test_basic_output(self):
        out = MapperOutput(key="Fizz", value=1)
        assert out.key == "Fizz"
        assert out.value == 1

    def test_default_value(self):
        out = MapperOutput(key="Buzz")
        assert out.value == 1

    def test_source_split_id(self):
        out = MapperOutput(key="FizzBuzz", source_split_id="s1")
        assert out.source_split_id == "s1"

    def test_output_is_frozen(self):
        out = MapperOutput(key="Fizz")
        with pytest.raises(AttributeError):
            out.key = "Buzz"


# ============================================================
# TaskTracker Tests
# ============================================================


class TestTaskTracker:
    """Verify TaskTracker lifecycle management."""

    def test_initial_state(self):
        tracker = TaskTracker(task_id="t1", task_type="mapper")
        assert tracker.status == TaskStatus.PENDING
        assert tracker.elapsed_seconds == 0.0

    def test_start(self):
        tracker = TaskTracker(task_id="t1", task_type="mapper")
        tracker.start()
        assert tracker.status == TaskStatus.RUNNING
        assert tracker.start_time is not None

    def test_complete(self):
        tracker = TaskTracker(task_id="t1", task_type="mapper")
        tracker.start()
        tracker.complete(result={"Fizz": 3})
        assert tracker.status == TaskStatus.COMPLETED
        assert tracker.result == {"Fizz": 3}
        assert tracker.elapsed_seconds >= 0

    def test_fail(self):
        tracker = TaskTracker(task_id="t1", task_type="reducer")
        tracker.start()
        tracker.fail("something broke")
        assert tracker.status == TaskStatus.FAILED
        assert tracker.error == "something broke"

    def test_heartbeat(self):
        tracker = TaskTracker(task_id="t1", task_type="mapper")
        tracker.start()
        first_hb = tracker.heartbeat_time
        tracker.heartbeat()
        assert tracker.heartbeat_time >= first_hb

    def test_elapsed_while_running(self):
        tracker = TaskTracker(task_id="t1", task_type="mapper")
        tracker.start()
        assert tracker.elapsed_seconds >= 0.0


# ============================================================
# Mapper Tests
# ============================================================


class TestMapper:
    """Verify mapper evaluation through StandardRuleEngine."""

    def test_mapper_fizz(self):
        mapper = Mapper(STANDARD_RULES)
        split = InputSplit(start=3, end=3, split_id="s1")
        outputs = mapper.map(split)
        assert len(outputs) == 1
        assert outputs[0].key == "Fizz"
        assert outputs[0].value == 1

    def test_mapper_buzz(self):
        mapper = Mapper(STANDARD_RULES)
        split = InputSplit(start=5, end=5, split_id="s1")
        outputs = mapper.map(split)
        assert len(outputs) == 1
        assert outputs[0].key == "Buzz"

    def test_mapper_fizzbuzz(self):
        mapper = Mapper(STANDARD_RULES)
        split = InputSplit(start=15, end=15, split_id="s1")
        outputs = mapper.map(split)
        assert len(outputs) == 1
        assert outputs[0].key == "FizzBuzz"

    def test_mapper_plain_number(self):
        mapper = Mapper(STANDARD_RULES)
        split = InputSplit(start=7, end=7, split_id="s1")
        outputs = mapper.map(split)
        assert len(outputs) == 1
        assert outputs[0].key == "7"

    def test_mapper_range(self):
        mapper = Mapper(STANDARD_RULES)
        split = InputSplit(start=1, end=5, split_id="s1")
        outputs = mapper.map(split)
        assert len(outputs) == 5
        keys = [o.key for o in outputs]
        assert keys == ["1", "2", "Fizz", "4", "Buzz"]

    def test_mapper_source_split_id(self):
        mapper = Mapper(STANDARD_RULES)
        split = InputSplit(start=1, end=1, split_id="my-split")
        outputs = mapper.map(split)
        assert outputs[0].source_split_id == "my-split"

    def test_mapper_empty_rules(self):
        mapper = Mapper([])
        split = InputSplit(start=1, end=3, split_id="s1")
        outputs = mapper.map(split)
        assert [o.key for o in outputs] == ["1", "2", "3"]


# ============================================================
# ShuffleSorter Tests
# ============================================================


class TestShuffleSorter:
    """Verify shuffle-and-sort with hash partitioning."""

    def test_basic_shuffle(self):
        sorter = ShuffleSorter(num_reducers=2)
        outputs = [
            MapperOutput(key="Fizz", value=1),
            MapperOutput(key="Buzz", value=1),
            MapperOutput(key="Fizz", value=1),
        ]
        partitions = sorter.shuffle(outputs)
        assert len(partitions) == 2

        # All Fizz values should be in one partition
        fizz_values = []
        for rid, keys in partitions.items():
            if "Fizz" in keys:
                fizz_values.extend(keys["Fizz"])
        assert fizz_values == [1, 1]

    def test_shuffle_empty_input(self):
        sorter = ShuffleSorter(num_reducers=3)
        partitions = sorter.shuffle([])
        assert len(partitions) == 3
        for rid, keys in partitions.items():
            assert keys == {}

    def test_shuffle_single_reducer(self):
        sorter = ShuffleSorter(num_reducers=1)
        outputs = [
            MapperOutput(key="Fizz", value=1),
            MapperOutput(key="Buzz", value=1),
        ]
        partitions = sorter.shuffle(outputs)
        assert len(partitions) == 1
        assert "Fizz" in partitions[0]
        assert "Buzz" in partitions[0]

    def test_shuffle_hash_deterministic(self):
        sorter = ShuffleSorter(num_reducers=4)
        outputs = [MapperOutput(key="Fizz")]
        p1 = sorter.shuffle(outputs)
        p2 = sorter.shuffle(outputs)
        # Same key should go to same partition
        for rid in range(4):
            assert ("Fizz" in p1[rid]) == ("Fizz" in p2[rid])

    def test_shuffle_invalid_num_reducers(self):
        with pytest.raises(ShuffleError):
            ShuffleSorter(num_reducers=0)

    def test_shuffle_negative_num_reducers(self):
        with pytest.raises(ShuffleError):
            ShuffleSorter(num_reducers=-1)

    def test_partition_stats(self):
        sorter = ShuffleSorter(num_reducers=2)
        outputs = [
            MapperOutput(key="Fizz"),
            MapperOutput(key="Fizz"),
            MapperOutput(key="Buzz"),
        ]
        partitions = sorter.shuffle(outputs)
        stats = sorter.get_partition_stats(partitions)
        assert stats["num_partitions"] == 2
        assert stats["total_records"] == 3

    def test_hash_partition_method(self):
        sorter = ShuffleSorter(num_reducers=4)
        # Should return a valid partition index
        pid = sorter._hash_partition("Fizz")
        assert 0 <= pid < 4

    def test_all_keys_grouped(self):
        sorter = ShuffleSorter(num_reducers=2)
        outputs = [
            MapperOutput(key="A"), MapperOutput(key="B"),
            MapperOutput(key="A"), MapperOutput(key="C"),
        ]
        partitions = sorter.shuffle(outputs)
        # Verify each key appears in exactly one partition
        seen_keys = set()
        for rid, keys in partitions.items():
            for key in keys:
                assert key not in seen_keys
                seen_keys.add(key)
        assert seen_keys == {"A", "B", "C"}


# ============================================================
# Reducer Tests
# ============================================================


class TestReducer:
    """Verify reducer aggregation logic."""

    def test_basic_reduce(self):
        reducer = Reducer(reducer_id=0)
        partition = {"Fizz": [1, 1, 1], "Buzz": [1, 1]}
        result = reducer.reduce(partition)
        assert result == {"Fizz": 3, "Buzz": 2}

    def test_reduce_empty_partition(self):
        reducer = Reducer(reducer_id=0)
        result = reducer.reduce({})
        assert result == {}

    def test_reduce_single_key(self):
        reducer = Reducer(reducer_id=1)
        result = reducer.reduce({"FizzBuzz": [1]})
        assert result == {"FizzBuzz": 1}

    def test_reducer_id(self):
        reducer = Reducer(reducer_id=42)
        assert reducer.reducer_id == 42

    def test_reduce_preserves_sorted_order(self):
        reducer = Reducer(reducer_id=0)
        partition = {"Buzz": [1, 1], "Fizz": [1, 1, 1]}
        result = reducer.reduce(partition)
        keys = list(result.keys())
        assert keys == sorted(keys)


# ============================================================
# SpeculativeExecutor Tests
# ============================================================


class TestSpeculativeExecutor:
    """Verify straggler detection and speculative launch tracking."""

    def test_no_stragglers_when_no_completed(self):
        executor = SpeculativeExecutor(threshold=1.5)
        tracker = TaskTracker(task_id="t1", task_type="mapper")
        tracker.start()
        stragglers = executor.detect_stragglers([tracker])
        assert stragglers == []

    def test_detect_straggler(self):
        executor = SpeculativeExecutor(threshold=1.5)

        # Create a completed task with 0.01s elapsed
        completed = TaskTracker(task_id="t1", task_type="mapper")
        completed.start_time = time.monotonic() - 0.01
        completed.end_time = time.monotonic()
        completed.status = TaskStatus.COMPLETED

        # Create a running task with 1.0s elapsed (way over 1.5x * 0.01)
        running = TaskTracker(task_id="t2", task_type="mapper")
        running.start_time = time.monotonic() - 1.0
        running.status = TaskStatus.RUNNING

        stragglers = executor.detect_stragglers([completed, running])
        assert len(stragglers) == 1
        assert stragglers[0].task_id == "t2"

    def test_no_straggler_within_threshold(self):
        executor = SpeculativeExecutor(threshold=1.5)

        completed = TaskTracker(task_id="t1", task_type="mapper")
        completed.start_time = time.monotonic() - 1.0
        completed.end_time = time.monotonic()
        completed.status = TaskStatus.COMPLETED

        # Running for 1.2s when avg is 1.0s and threshold is 1.5x
        running = TaskTracker(task_id="t2", task_type="mapper")
        running.start_time = time.monotonic() - 1.2
        running.status = TaskStatus.RUNNING

        stragglers = executor.detect_stragglers([completed, running])
        assert len(stragglers) == 0

    def test_speculative_tasks_excluded(self):
        executor = SpeculativeExecutor(threshold=1.5)

        completed = TaskTracker(task_id="t1", task_type="mapper")
        completed.start_time = time.monotonic() - 0.01
        completed.end_time = time.monotonic()
        completed.status = TaskStatus.COMPLETED

        # This running task is speculative, should not be detected
        running = TaskTracker(task_id="t2", task_type="mapper", is_speculative=True)
        running.start_time = time.monotonic() - 10.0
        running.status = TaskStatus.RUNNING

        stragglers = executor.detect_stragglers([completed, running])
        assert len(stragglers) == 0

    def test_record_launch(self):
        executor = SpeculativeExecutor()
        executor.record_launch("t1", "t2")
        launches = executor.speculative_launches
        assert len(launches) == 1
        assert launches[0]["original_task_id"] == "t1"
        assert launches[0]["speculative_task_id"] == "t2"

    def test_threshold_property(self):
        executor = SpeculativeExecutor(threshold=2.0)
        assert executor.threshold == 2.0

    def test_default_threshold(self):
        executor = SpeculativeExecutor()
        assert executor.threshold == 1.5


# ============================================================
# JobTracker Tests
# ============================================================


class TestJobTracker:
    """Verify JobTracker split creation and task management."""

    def test_create_splits_even(self):
        tracker = JobTracker(num_mappers=4)
        splits = tracker.create_splits(1, 20)
        assert len(splits) == 4
        total_size = sum(s.size for s in splits)
        assert total_size == 20

    def test_create_splits_uneven(self):
        tracker = JobTracker(num_mappers=3)
        splits = tracker.create_splits(1, 10)
        assert len(splits) == 3
        total_size = sum(s.size for s in splits)
        assert total_size == 10

    def test_create_splits_more_mappers_than_numbers(self):
        tracker = JobTracker(num_mappers=10)
        splits = tracker.create_splits(1, 3)
        assert len(splits) == 3
        assert all(s.size == 1 for s in splits)

    def test_create_splits_single_number(self):
        tracker = JobTracker(num_mappers=4)
        splits = tracker.create_splits(5, 5)
        assert len(splits) == 1
        assert splits[0].start == 5
        assert splits[0].end == 5

    def test_create_splits_empty_range(self):
        tracker = JobTracker(num_mappers=4)
        splits = tracker.create_splits(10, 5)
        assert len(splits) == 0

    def test_create_splits_no_gaps(self):
        tracker = JobTracker(num_mappers=4)
        splits = tracker.create_splits(1, 15)
        # Verify no gaps between splits
        for i in range(len(splits) - 1):
            assert splits[i].end + 1 == splits[i + 1].start
        assert splits[0].start == 1
        assert splits[-1].end == 15

    def test_register_task(self):
        tracker = JobTracker()
        task = tracker.register_task("mapper")
        assert task.task_type == "mapper"
        assert task.status == TaskStatus.PENDING

    def test_register_speculative_task(self):
        tracker = JobTracker()
        task = tracker.register_task("mapper", is_speculative=True)
        assert task.is_speculative is True

    def test_get_progress(self):
        tracker = JobTracker()
        t1 = tracker.register_task("mapper")
        t2 = tracker.register_task("mapper")
        t1.start()
        t1.complete()
        progress = tracker.get_progress()
        assert progress["mappers"]["total"] == 2
        assert progress["mappers"]["completed"] == 1
        assert progress["mappers"]["pending"] == 1

    def test_num_mappers_minimum(self):
        tracker = JobTracker(num_mappers=0)
        assert tracker.num_mappers == 1

    def test_num_reducers_minimum(self):
        tracker = JobTracker(num_reducers=-1)
        assert tracker.num_reducers == 1


# ============================================================
# MapReduceJob Tests
# ============================================================


class TestMapReduceJob:
    """Verify the end-to-end MapReduce pipeline."""

    def test_initial_state(self):
        job = MapReduceJob(rules=STANDARD_RULES)
        assert job.state == JobState.SUBMITTED

    def test_execute_range_1_to_15(self):
        """The canonical FizzBuzz test: range 1-15 must produce
        Fizz:4, Buzz:2, FizzBuzz:1, plain numbers:8."""
        job = MapReduceJob(
            rules=STANDARD_RULES,
            num_mappers=2,
            num_reducers=2,
        )
        results = job.execute(1, 15)

        assert results.get("Fizz", 0) == 4
        assert results.get("Buzz", 0) == 2
        assert results.get("FizzBuzz", 0) == 1

        # Plain numbers: 1, 2, 4, 7, 8, 11, 13, 14 = 8 total
        plain_count = sum(
            v for k, v in results.items()
            if k not in ("Fizz", "Buzz", "FizzBuzz")
        )
        assert plain_count == 8

    def test_execute_single_number_fizz(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        results = job.execute(3, 3)
        assert results == {"Fizz": 1}

    def test_execute_single_number_plain(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        results = job.execute(7, 7)
        assert results == {"7": 1}

    def test_state_transitions(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        job.execute(1, 5)

        states = [s for s, _ in job.state_history]
        assert states == [
            JobState.SUBMITTED,
            JobState.SPLITTING,
            JobState.MAPPING,
            JobState.SHUFFLING,
            JobState.REDUCING,
            JobState.COMPLETED,
        ]

    def test_job_id_unique(self):
        j1 = MapReduceJob(rules=STANDARD_RULES)
        j2 = MapReduceJob(rules=STANDARD_RULES)
        assert j1.job_id != j2.job_id

    def test_elapsed_seconds(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        job.execute(1, 10)
        assert job.elapsed_seconds > 0

    def test_splits_property(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=3, num_reducers=1)
        job.execute(1, 15)
        assert len(job.splits) == 3

    def test_shuffle_stats(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        stats = job.shuffle_stats
        assert stats["num_partitions"] == 2
        assert stats["total_records"] == 15

    def test_final_results_property(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        results = job.execute(1, 5)
        assert job.final_results == results

    def test_execute_empty_range(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        results = job.execute(10, 5)
        assert results == {}
        assert job.state == JobState.COMPLETED

    def test_multiple_mappers_same_result(self):
        """Result should be identical regardless of mapper count."""
        results_1 = MapReduceJob(
            rules=STANDARD_RULES, num_mappers=1, num_reducers=1
        ).execute(1, 30)
        results_4 = MapReduceJob(
            rules=STANDARD_RULES, num_mappers=4, num_reducers=1
        ).execute(1, 30)
        assert results_1 == results_4

    def test_multiple_reducers_same_result(self):
        """Result should be identical regardless of reducer count."""
        results_1 = MapReduceJob(
            rules=STANDARD_RULES, num_mappers=2, num_reducers=1
        ).execute(1, 30)
        results_4 = MapReduceJob(
            rules=STANDARD_RULES, num_mappers=2, num_reducers=4
        ).execute(1, 30)
        assert results_1 == results_4

    def test_range_1_to_100(self):
        """Larger range correctness check."""
        job = MapReduceJob(
            rules=STANDARD_RULES, num_mappers=4, num_reducers=2
        )
        results = job.execute(1, 100)

        # Verify total
        total = sum(results.values())
        assert total == 100

        # Known distribution for 1-100
        assert results.get("FizzBuzz", 0) == 6  # 15, 30, 45, 60, 75, 90
        assert results.get("Fizz", 0) == 27     # div by 3 but not 5
        assert results.get("Buzz", 0) == 14     # div by 5 but not 3


# ============================================================
# MapReduceDashboard Tests
# ============================================================


class TestMapReduceDashboard:
    """Verify the ASCII dashboard rendering."""

    def test_render_completed_job(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        output = MapReduceDashboard.render(job, width=60)

        assert "FizzReduce MapReduce Dashboard" in output
        assert job.job_id in output
        assert "COMPLETED" in output

    def test_render_contains_splits(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        output = MapReduceDashboard.render(job)

        assert "Input Splits" in output

    def test_render_contains_task_progress(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        output = MapReduceDashboard.render(job)

        assert "Task Progress" in output
        assert "Mappers" in output
        assert "Reducers" in output

    def test_render_contains_shuffle_stats(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        output = MapReduceDashboard.render(job)

        assert "Shuffle Statistics" in output

    def test_render_contains_speculative(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        output = MapReduceDashboard.render(job)

        assert "Speculative Execution" in output

    def test_render_contains_results(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        output = MapReduceDashboard.render(job)

        assert "Classification Distribution" in output

    def test_render_empty_job(self):
        job = MapReduceJob(rules=STANDARD_RULES)
        output = MapReduceDashboard.render(job)
        assert "SUBMITTED" in output

    def test_render_custom_width(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        job.execute(1, 5)
        output_narrow = MapReduceDashboard.render(job, width=50)
        output_wide = MapReduceDashboard.render(job, width=80)
        # Wider dashboard should have longer lines
        narrow_max = max(len(line) for line in output_narrow.split("\n") if line.strip())
        wide_max = max(len(line) for line in output_wide.split("\n") if line.strip())
        assert wide_max > narrow_max

    def test_render_state_transitions(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        job.execute(1, 5)
        output = MapReduceDashboard.render(job)
        assert "State Transitions" in output
        assert "SUBMITTED" in output
        assert "SPLITTING" in output
        assert "MAPPING" in output


# ============================================================
# MapReduceMiddleware Tests
# ============================================================


class TestMapReduceMiddleware:
    """Verify the middleware integration."""

    def test_middleware_name(self):
        mw = MapReduceMiddleware()
        assert mw.get_name() == "MapReduceMiddleware"

    def test_middleware_adds_metadata(self):
        mw = MapReduceMiddleware()
        context = ProcessingContext(number=3, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata["mapreduce_enabled"] is True

    def test_middleware_with_job(self):
        job = MapReduceJob(rules=STANDARD_RULES)
        mw = MapReduceMiddleware(job=job)
        context = ProcessingContext(number=3, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata["mapreduce_job_id"] == job.job_id

    def test_middleware_evaluation_count(self):
        mw = MapReduceMiddleware()

        def next_handler(ctx):
            return ctx

        for i in range(5):
            mw.process(ProcessingContext(number=i, session_id="test"), next_handler)

        assert mw.evaluation_count == 5

    def test_middleware_calls_next(self):
        mw = MapReduceMiddleware()
        called = [False]

        def next_handler(ctx):
            called[0] = True
            return ctx

        mw.process(ProcessingContext(number=1, session_id="test"), next_handler)
        assert called[0] is True

    def test_middleware_job_setter(self):
        mw = MapReduceMiddleware()
        assert mw.job is None
        job = MapReduceJob(rules=STANDARD_RULES)
        mw.job = job
        assert mw.job is job


# ============================================================
# TaskStatus and JobState Enum Tests
# ============================================================


class TestEnums:
    """Verify enum definitions."""

    def test_task_status_values(self):
        assert TaskStatus.PENDING is not None
        assert TaskStatus.RUNNING is not None
        assert TaskStatus.COMPLETED is not None
        assert TaskStatus.FAILED is not None
        assert TaskStatus.SPECULATIVE is not None

    def test_job_state_values(self):
        assert JobState.SUBMITTED is not None
        assert JobState.SPLITTING is not None
        assert JobState.MAPPING is not None
        assert JobState.SHUFFLING is not None
        assert JobState.REDUCING is not None
        assert JobState.COMPLETED is not None
        assert JobState.FAILED is not None


# ============================================================
# Integration / Edge Case Tests
# ============================================================


class TestIntegration:
    """End-to-end and edge case tests."""

    def test_large_range_correctness(self):
        """Verify total count matches range size for a larger input."""
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=8, num_reducers=4)
        results = job.execute(1, 1000)
        total = sum(results.values())
        assert total == 1000

    def test_single_mapper_single_reducer(self):
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=1, num_reducers=1)
        results = job.execute(1, 15)
        assert results.get("Fizz", 0) == 4
        assert results.get("Buzz", 0) == 2
        assert results.get("FizzBuzz", 0) == 1

    def test_custom_rules(self):
        """MapReduce with a custom Wuzz rule (divisor=7)."""
        rules = [
            RuleDefinition(name="Wuzz", divisor=7, label="Wuzz", priority=1),
        ]
        job = MapReduceJob(rules=rules, num_mappers=2, num_reducers=1)
        results = job.execute(1, 14)
        assert results.get("Wuzz", 0) == 2  # 7 and 14

    def test_concurrent_safety(self):
        """Multiple jobs can run concurrently without interference."""
        results_list = [None, None]
        errors = []

        def run_job(idx, start, end):
            try:
                job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
                results_list[idx] = job.execute(start, end)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=run_job, args=(0, 1, 15))
        t2 = threading.Thread(target=run_job, args=(1, 1, 15))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        assert results_list[0] == results_list[1]

    def test_job_tracker_speculative_executor_accessible(self):
        job = MapReduceJob(rules=STANDARD_RULES, speculative_threshold=2.0)
        assert job.job_tracker.speculative_executor.threshold == 2.0

    def test_shuffle_stats_max_skew(self):
        """Verify max_skew is computed."""
        job = MapReduceJob(rules=STANDARD_RULES, num_mappers=2, num_reducers=2)
        job.execute(1, 15)
        stats = job.shuffle_stats
        assert "max_skew" in stats
        assert stats["max_skew"] >= 0

"""
Tests for enterprise_fizzbuzz.infrastructure.fizzci

Comprehensive test suite for the FizzCI continuous integration pipeline
engine covering pipeline parsing, DAG construction, matrix expansion,
conditional evaluation, artifact management, build caching, secret
injection, log streaming, step/job/stage/pipeline execution, webhook
triggers, status reporting, pipeline history, template engine, pipeline
visualization, and middleware integration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzci import (
    FIZZCI_VERSION,
    MIDDLEWARE_PRIORITY,
    DEFAULT_MAX_PARALLEL_JOBS,
    DEFAULT_JOB_TIMEOUT,
    DEFAULT_CONTAINER_IMAGE,
    WEBHOOK_EVENTS,
    PipelineStatus,
    StageStatus,
    JobStatus,
    StepStatus,
    RetryStrategy,
    TriggerType,
    ConditionType,
    FizzCIConfig,
    StepDefinition,
    RetryPolicy,
    ArtifactSpec,
    MatrixConfig,
    ConditionSpec,
    JobDefinition,
    StageDefinition,
    PipelineDefinition,
    StepResult,
    JobResult,
    StageResult,
    PipelineRun,
    Artifact,
    CacheEntry,
    WebhookPayload,
    EngineMetrics,
    PipelineParser,
    DAGBuilder,
    MatrixExpander,
    ConditionalEvaluator,
    ArtifactManager,
    BuildCache,
    SecretInjector,
    LogStreamer,
    StepExecutor,
    JobRunner,
    PipelineExecutor,
    WebhookTriggerHandler,
    StatusReporter,
    PipelineHistory,
    PipelineTemplateEngine,
    PipelineVisualizer,
    PipelineEngine,
    FizzCIDashboard,
    FizzCIMiddleware,
    create_fizzci_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def config():
    return FizzCIConfig()


@pytest.fixture
def subsystem():
    return create_fizzci_subsystem()


@pytest.fixture
def parser():
    return PipelineParser()


@pytest.fixture
def dag_builder():
    return DAGBuilder()


@pytest.fixture
def matrix_expander():
    return MatrixExpander()


@pytest.fixture
def artifact_manager(config):
    return ArtifactManager(config)


@pytest.fixture
def build_cache(config):
    return BuildCache(config)


@pytest.fixture
def log_streamer(config):
    return LogStreamer(config)


def _simple_pipeline_def():
    return {
        "name": "test-pipeline",
        "on": ["push"],
        "stages": [
            {
                "name": "build",
                "jobs": [{
                    "name": "compile",
                    "steps": [
                        {"name": "checkout", "run": "checkout"},
                        {"name": "build", "run": "build dist/"},
                    ],
                }],
            },
            {
                "name": "test",
                "depends_on": ["build"],
                "jobs": [{
                    "name": "unit-tests",
                    "steps": [{"name": "test", "run": "pytest tests/"}],
                }],
            },
        ],
    }


# ============================================================
# TestPipelineParser
# ============================================================


class TestPipelineParser:

    def test_parse_simple(self, parser):
        pipeline = parser.parse(_simple_pipeline_def())
        assert pipeline.name == "test-pipeline"
        assert len(pipeline.stages) == 2

    def test_parse_triggers(self, parser):
        pipeline = parser.parse({"name": "t", "on": ["push", "pull_request"], "stages": [{"name": "s", "jobs": []}]})
        assert TriggerType.PUSH in pipeline.triggers
        assert TriggerType.PULL_REQUEST in pipeline.triggers

    def test_parse_variables(self, parser):
        pipeline = parser.parse({"name": "t", "variables": {"FOO": "bar"}, "stages": [{"name": "s", "jobs": []}]})
        assert pipeline.variables["FOO"] == "bar"

    def test_parse_job_steps(self, parser):
        pipeline = parser.parse(_simple_pipeline_def())
        job = pipeline.stages[0].jobs[0]
        assert len(job.steps) == 2
        assert job.steps[0].name == "checkout"

    def test_parse_job_retry(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [{"name": "j", "steps": [], "retry": 3}]}]}
        pipeline = parser.parse(defn)
        assert pipeline.stages[0].jobs[0].retry.max_attempts == 3

    def test_parse_job_retry_dict(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [{"name": "j", "steps": [],
                "retry": {"max_attempts": 5, "strategy": "exponential"}}]}]}
        pipeline = parser.parse(defn)
        assert pipeline.stages[0].jobs[0].retry.max_attempts == 5
        assert pipeline.stages[0].jobs[0].retry.strategy == RetryStrategy.EXPONENTIAL

    def test_parse_job_artifacts(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [{"name": "j", "steps": [],
                "artifacts": {"name": "dist", "paths": ["dist/"]}}]}]}
        pipeline = parser.parse(defn)
        assert pipeline.stages[0].jobs[0].artifacts.name == "dist"

    def test_parse_job_matrix(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [{"name": "j", "steps": [],
                "matrix": {"parameters": {"py": ["3.11", "3.12"]}}}]}]}
        pipeline = parser.parse(defn)
        assert "py" in pipeline.stages[0].jobs[0].matrix.parameters

    def test_parse_stage_depends_on(self, parser):
        pipeline = parser.parse(_simple_pipeline_def())
        assert pipeline.stages[1].depends_on == ["build"]

    def test_parse_condition_branch(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [],
                "condition": {"branches": ["main", "release/*"]}}]}
        pipeline = parser.parse(defn)
        assert pipeline.stages[0].condition.condition_type == ConditionType.BRANCH

    def test_parse_condition_string(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [], "condition": "always"}]}
        pipeline = parser.parse(defn)
        assert pipeline.stages[0].condition.condition_type == ConditionType.ALWAYS

    def test_parse_no_stages_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse({"name": "t", "stages": []})

    def test_parse_string_steps(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [{"name": "j",
                "steps": ["echo hello", "echo world"]}]}]}
        pipeline = parser.parse(defn)
        assert len(pipeline.stages[0].jobs[0].steps) == 2

    def test_parse_job_secrets(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [{"name": "j", "steps": [],
                "secrets": ["TOKEN_A", "TOKEN_B"]}]}]}
        pipeline = parser.parse(defn)
        assert "TOKEN_A" in pipeline.stages[0].jobs[0].secrets

    def test_parse_step_continue_on_error(self, parser):
        defn = {"name": "t", "stages": [{"name": "s", "jobs": [{"name": "j",
                "steps": [{"name": "s1", "run": "test", "continue_on_error": True}]}]}]}
        pipeline = parser.parse(defn)
        assert pipeline.stages[0].jobs[0].steps[0].continue_on_error is True


# ============================================================
# TestDAGBuilder
# ============================================================


class TestDAGBuilder:

    def test_linear_dag(self, dag_builder):
        stages = [
            StageDefinition(name="a"),
            StageDefinition(name="b", depends_on=["a"]),
            StageDefinition(name="c", depends_on=["b"]),
        ]
        levels = dag_builder.build(stages)
        assert len(levels) == 3
        assert levels[0][0].name == "a"
        assert levels[1][0].name == "b"
        assert levels[2][0].name == "c"

    def test_parallel_dag(self, dag_builder):
        stages = [
            StageDefinition(name="a"),
            StageDefinition(name="b"),
            StageDefinition(name="c", depends_on=["a", "b"]),
        ]
        levels = dag_builder.build(stages)
        assert len(levels) == 2
        level0_names = {s.name for s in levels[0]}
        assert level0_names == {"a", "b"}

    def test_cycle_detection(self, dag_builder):
        stages = [
            StageDefinition(name="a", depends_on=["b"]),
            StageDefinition(name="b", depends_on=["a"]),
        ]
        with pytest.raises(Exception):
            dag_builder.build(stages)

    def test_unknown_dependency(self, dag_builder):
        stages = [StageDefinition(name="a", depends_on=["nonexistent"])]
        with pytest.raises(Exception):
            dag_builder.build(stages)

    def test_single_stage(self, dag_builder):
        stages = [StageDefinition(name="only")]
        levels = dag_builder.build(stages)
        assert len(levels) == 1

    def test_validate_valid(self, dag_builder):
        pipeline = PipelineDefinition(stages=[
            StageDefinition(name="a"),
            StageDefinition(name="b", depends_on=["a"]),
        ])
        assert dag_builder.validate(pipeline) is True

    def test_validate_cycle(self, dag_builder):
        pipeline = PipelineDefinition(stages=[
            StageDefinition(name="a", depends_on=["b"]),
            StageDefinition(name="b", depends_on=["a"]),
        ])
        assert dag_builder.validate(pipeline) is False

    def test_diamond_dag(self, dag_builder):
        stages = [
            StageDefinition(name="a"),
            StageDefinition(name="b", depends_on=["a"]),
            StageDefinition(name="c", depends_on=["a"]),
            StageDefinition(name="d", depends_on=["b", "c"]),
        ]
        levels = dag_builder.build(stages)
        assert len(levels) == 3


# ============================================================
# TestMatrixExpander
# ============================================================


class TestMatrixExpander:

    def test_expand_single_param(self, matrix_expander):
        job = JobDefinition(name="test", matrix=MatrixConfig(parameters={"py": ["3.11", "3.12"]}))
        expanded = matrix_expander.expand(job)
        assert len(expanded) == 2
        assert "3.11" in expanded[0].name
        assert "3.12" in expanded[1].name

    def test_expand_multiple_params(self, matrix_expander):
        job = JobDefinition(name="test", matrix=MatrixConfig(
            parameters={"py": ["3.11", "3.12"], "os": ["linux", "macos"]}
        ))
        expanded = matrix_expander.expand(job)
        assert len(expanded) == 4

    def test_expand_with_exclude(self, matrix_expander):
        job = JobDefinition(name="test", matrix=MatrixConfig(
            parameters={"py": ["3.11", "3.12"], "os": ["linux", "macos"]},
            exclude=[{"py": "3.11", "os": "macos"}],
        ))
        expanded = matrix_expander.expand(job)
        assert len(expanded) == 3

    def test_expand_with_include(self, matrix_expander):
        job = JobDefinition(name="test", matrix=MatrixConfig(
            parameters={"py": ["3.11"]},
            include=[{"py": "3.10"}],
        ))
        expanded = matrix_expander.expand(job)
        assert len(expanded) == 2

    def test_no_matrix(self, matrix_expander):
        job = JobDefinition(name="test")
        expanded = matrix_expander.expand(job)
        assert len(expanded) == 1

    def test_empty_matrix_raises(self, matrix_expander):
        job = JobDefinition(name="test", matrix=MatrixConfig(
            parameters={"py": ["3.11"]},
            exclude=[{"py": "3.11"}],
        ))
        with pytest.raises(Exception):
            matrix_expander.expand(job)

    def test_expanded_jobs_have_env(self, matrix_expander):
        job = JobDefinition(name="test", matrix=MatrixConfig(parameters={"ver": ["1", "2"]}))
        expanded = matrix_expander.expand(job)
        assert "MATRIX_VER" in expanded[0].environment

    def test_preview(self, matrix_expander):
        job = JobDefinition(name="test", matrix=MatrixConfig(parameters={"a": ["1", "2"], "b": ["x", "y"]}))
        combos = matrix_expander.preview(job)
        assert len(combos) == 4


# ============================================================
# TestConditionalEvaluator
# ============================================================


class TestConditionalEvaluator:

    def test_always(self):
        ev = ConditionalEvaluator()
        assert ev.evaluate(ConditionSpec(condition_type=ConditionType.ALWAYS), {}) is True

    def test_never(self):
        ev = ConditionalEvaluator()
        assert ev.evaluate(ConditionSpec(condition_type=ConditionType.NEVER), {}) is False

    def test_none_condition(self):
        ev = ConditionalEvaluator()
        assert ev.evaluate(None, {}) is True

    def test_branch_match(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.BRANCH, branches=["main", "release/*"])
        assert ev.evaluate(cond, {"branch": "main"}) is True

    def test_branch_wildcard(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.BRANCH, branches=["feature/*"])
        assert ev.evaluate(cond, {"branch": "feature/add-ci"}) is True

    def test_branch_no_match(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.BRANCH, branches=["main"])
        assert ev.evaluate(cond, {"branch": "develop"}) is False

    def test_path_match(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.PATH, paths=["src/**"])
        assert ev.evaluate(cond, {"paths_changed": ["src/main.py"]}) is True

    def test_path_no_match(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.PATH, paths=["docs/**"])
        assert ev.evaluate(cond, {"paths_changed": ["src/main.py"]}) is False

    def test_manual_approved(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.MANUAL)
        assert ev.evaluate(cond, {"manual_approval": True}) is True

    def test_manual_not_approved(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.MANUAL)
        assert ev.evaluate(cond, {}) is False

    def test_expression_true(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.EXPRESSION, expression="true")
        assert ev.evaluate(cond, {}) is True

    def test_expression_false(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.EXPRESSION, expression="false")
        assert ev.evaluate(cond, {}) is False

    def test_expression_equality(self):
        ev = ConditionalEvaluator()
        cond = ConditionSpec(condition_type=ConditionType.EXPRESSION, expression="$branch == 'main'")
        assert ev.evaluate(cond, {"branch": "main"}) is True
        assert ev.evaluate(cond, {"branch": "dev"}) is False


# ============================================================
# TestArtifactManager
# ============================================================


class TestArtifactManager:

    def test_store_and_retrieve(self, artifact_manager):
        art = artifact_manager.store("test-art", b"data", "pipeline", "run1", "job1")
        assert art.name == "test-art"
        assert art.size == 4
        retrieved = artifact_manager.retrieve("test-art", "run1", "job1")
        assert retrieved is not None
        assert retrieved.data == b"data"

    def test_retrieve_by_name(self, artifact_manager):
        artifact_manager.store("my-art", b"data", "p", "r", "j")
        retrieved = artifact_manager.retrieve("my-art")
        assert retrieved is not None

    def test_retrieve_not_found(self, artifact_manager):
        assert artifact_manager.retrieve("nonexistent") is None

    def test_list_all(self, artifact_manager):
        artifact_manager.store("a", b"1", "p", "r", "j1")
        artifact_manager.store("b", b"2", "p", "r", "j2")
        assert len(artifact_manager.list_all()) == 2

    def test_delete(self, artifact_manager):
        artifact_manager.store("a", b"1", "p", "r", "j")
        assert artifact_manager.delete("r/j/a") is True
        assert artifact_manager.count == 0

    def test_delete_nonexistent(self, artifact_manager):
        assert artifact_manager.delete("nope") is False

    def test_size_limit(self, config):
        config.artifact_max_size = 10
        am = ArtifactManager(config)
        with pytest.raises(Exception):
            am.store("big", b"x" * 20, "p", "r", "j")

    def test_total_size(self, artifact_manager):
        artifact_manager.store("a", b"hello", "p", "r", "j")
        assert artifact_manager.total_size == 5

    def test_content_hash(self, artifact_manager):
        art = artifact_manager.store("a", b"test", "p", "r", "j")
        expected = hashlib.sha256(b"test").hexdigest()
        assert art.content_hash == expected


# ============================================================
# TestBuildCache
# ============================================================


class TestBuildCache:

    def test_put_and_get(self, build_cache):
        build_cache.put("key1", b"value1")
        assert build_cache.get("key1") == b"value1"

    def test_miss(self, build_cache):
        assert build_cache.get("nonexistent") is None

    def test_invalidate(self, build_cache):
        build_cache.put("key1", b"value1")
        assert build_cache.invalidate("key1") is True
        assert build_cache.get("key1") is None

    def test_clear(self, build_cache):
        build_cache.put("a", b"1")
        build_cache.put("b", b"2")
        count = build_cache.clear()
        assert count == 2
        assert build_cache.get("a") is None

    def test_lru_eviction(self, config):
        config.cache_max_size = 10
        cache = BuildCache(config)
        cache.put("a", b"12345")
        cache.put("b", b"67890")
        # Adding more should evict oldest
        cache.put("c", b"abcde")
        assert cache.get("a") is None  # Evicted
        assert cache.get("c") == b"abcde"

    def test_hit_rate(self, build_cache):
        build_cache.put("a", b"1")
        build_cache.get("a")  # hit
        build_cache.get("b")  # miss
        assert build_cache.hit_rate == 50.0

    def test_get_stats(self, build_cache):
        build_cache.put("a", b"test")
        stats = build_cache.get_stats()
        assert stats["entries"] == 1
        assert stats["total_size"] == 4

    def test_ttl_expiry(self, config):
        config.cache_ttl = 0.0  # Instant expiry
        cache = BuildCache(config)
        cache.put("a", b"1")
        assert cache.get("a") is None  # Expired


# ============================================================
# TestSecretInjector
# ============================================================


class TestSecretInjector:

    def test_inject_secrets(self):
        injector = SecretInjector()
        job = JobDefinition(name="j", secrets=["DEPLOY_TOKEN"])
        env = injector.inject(job)
        assert "DEPLOY_TOKEN" in env
        assert env["DEPLOY_TOKEN"] == "fzbz-deploy-xxxxxxxx"

    def test_inject_nonexistent_raises(self):
        injector = SecretInjector()
        job = JobDefinition(name="j", secrets=["NONEXISTENT_SECRET"])
        with pytest.raises(Exception):
            injector.inject(job)

    def test_inject_preserves_env(self):
        injector = SecretInjector()
        job = JobDefinition(name="j", environment={"FOO": "bar"}, secrets=["DEPLOY_TOKEN"])
        env = injector.inject(job)
        assert env["FOO"] == "bar"
        assert "DEPLOY_TOKEN" in env

    def test_mask_secrets(self):
        injector = SecretInjector()
        text = "Token is fzbz-deploy-xxxxxxxx"
        masked = injector.mask_secrets(text, ["DEPLOY_TOKEN"])
        assert "fzbz-deploy" not in masked
        assert "***DEPLOY_TOKEN***" in masked

    def test_list_available(self):
        injector = SecretInjector()
        available = injector.list_available()
        assert "DEPLOY_TOKEN" in available
        assert "REGISTRY_PASSWORD" in available


# ============================================================
# TestLogStreamer
# ============================================================


class TestLogStreamer:

    def test_create_and_append(self, log_streamer):
        log_streamer.create_buffer("job1")
        log_streamer.append("job1", "Hello")
        lines = log_streamer.get_lines("job1")
        assert len(lines) == 1
        assert "Hello" in lines[0]

    def test_get_lines_empty(self, log_streamer):
        assert log_streamer.get_lines("nonexistent") == []

    def test_get_lines_last_n(self, log_streamer):
        log_streamer.create_buffer("job1")
        for i in range(10):
            log_streamer.append("job1", f"Line {i}")
        lines = log_streamer.get_lines("job1", last_n=3)
        assert len(lines) == 3

    def test_clear(self, log_streamer):
        log_streamer.create_buffer("job1")
        log_streamer.append("job1", "data")
        log_streamer.clear("job1")
        assert log_streamer.get_lines("job1") == []

    def test_timestamp_in_lines(self, log_streamer):
        log_streamer.create_buffer("job1")
        log_streamer.append("job1", "test")
        line = log_streamer.get_lines("job1")[0]
        assert "[" in line  # Timestamp prefix


# ============================================================
# TestWebhookTriggerHandler
# ============================================================


class TestWebhookTriggerHandler:

    def test_validate_valid(self, config):
        handler = WebhookTriggerHandler(config)
        payload = WebhookPayload(event="push", ref="refs/heads/main")
        assert handler.validate_payload(payload) is True

    def test_validate_missing_event(self, config):
        handler = WebhookTriggerHandler(config)
        payload = WebhookPayload(event="")
        with pytest.raises(Exception):
            handler.validate_payload(payload)

    def test_validate_unknown_event(self, config):
        handler = WebhookTriggerHandler(config)
        payload = WebhookPayload(event="unknown_event")
        with pytest.raises(Exception):
            handler.validate_payload(payload)

    def test_should_trigger(self, config):
        handler = WebhookTriggerHandler(config)
        pipeline = PipelineDefinition(triggers=[TriggerType.PUSH])
        payload = WebhookPayload(event="push")
        assert handler.should_trigger(pipeline, payload) is True

    def test_should_not_trigger(self, config):
        handler = WebhookTriggerHandler(config)
        pipeline = PipelineDefinition(triggers=[TriggerType.TAG])
        payload = WebhookPayload(event="push")
        assert handler.should_trigger(pipeline, payload) is False

    def test_build_context(self, config):
        handler = WebhookTriggerHandler(config)
        payload = WebhookPayload(event="push", branch="main", commit_sha="abc123")
        ctx = handler.build_context(payload)
        assert ctx["branch"] == "main"
        assert ctx["commit_sha"] == "abc123"


# ============================================================
# TestStatusReporter
# ============================================================


class TestStatusReporter:

    def test_format_run_status(self):
        reporter = StatusReporter()
        run = PipelineRun(
            run_id="abc", pipeline_name="test", status=PipelineStatus.SUCCESS,
            trigger=TriggerType.PUSH, branch="main", commit_sha="1234",
            duration_ms=5000.0, started_at=datetime.now(timezone.utc),
        )
        output = reporter.format_run_status(run)
        assert "test" in output
        assert "PASS" in output

    def test_format_summary(self):
        reporter = StatusReporter()
        runs = [
            PipelineRun(run_id="1", pipeline_name="p", status=PipelineStatus.SUCCESS,
                        trigger=TriggerType.PUSH, duration_ms=1000, branch="main"),
            PipelineRun(run_id="2", pipeline_name="p", status=PipelineStatus.FAILED,
                        trigger=TriggerType.PUSH, duration_ms=2000, branch="main"),
        ]
        output = reporter.format_summary(runs)
        assert "2 runs" in output
        assert "1 passed" in output


# ============================================================
# TestPipelineHistory
# ============================================================


class TestPipelineHistory:

    def test_record_and_get(self, config):
        history = PipelineHistory(config)
        run = PipelineRun(run_id="abc", pipeline_name="test")
        history.record(run)
        assert history.get_run("abc") is not None

    def test_get_nonexistent(self, config):
        history = PipelineHistory(config)
        assert history.get_run("nope") is None

    def test_get_all(self, config):
        history = PipelineHistory(config)
        history.record(PipelineRun(run_id="1", pipeline_name="a"))
        history.record(PipelineRun(run_id="2", pipeline_name="b"))
        assert len(history.get_all()) == 2

    def test_get_by_pipeline(self, config):
        history = PipelineHistory(config)
        history.record(PipelineRun(run_id="1", pipeline_name="a"))
        history.record(PipelineRun(run_id="2", pipeline_name="b"))
        history.record(PipelineRun(run_id="3", pipeline_name="a"))
        assert len(history.get_by_pipeline("a")) == 2

    def test_get_latest(self, config):
        history = PipelineHistory(config)
        history.record(PipelineRun(run_id="1", pipeline_name="a"))
        history.record(PipelineRun(run_id="2", pipeline_name="a"))
        assert history.get_latest("a").run_id == "2"

    def test_max_runs_trimming(self):
        config = FizzCIConfig(history_max_runs=3)
        history = PipelineHistory(config)
        for i in range(5):
            history.record(PipelineRun(run_id=str(i), pipeline_name="p"))
        assert history.count == 3


# ============================================================
# TestPipelineTemplateEngine
# ============================================================


class TestPipelineTemplateEngine:

    def test_list_templates(self):
        engine = PipelineTemplateEngine()
        templates = engine.list_templates()
        assert "python-ci" in templates
        assert "docker-build" in templates
        assert "deploy" in templates

    def test_get_template(self):
        engine = PipelineTemplateEngine()
        t = engine.get_template("python-ci")
        assert t is not None
        assert "stages" in t

    def test_get_nonexistent(self):
        engine = PipelineTemplateEngine()
        assert engine.get_template("nonexistent") is None

    def test_apply_template(self):
        engine = PipelineTemplateEngine()
        defn = engine.apply_template("python-ci")
        assert "stages" in defn

    def test_apply_nonexistent_raises(self):
        engine = PipelineTemplateEngine()
        with pytest.raises(Exception):
            engine.apply_template("nonexistent")

    def test_apply_with_overrides(self):
        engine = PipelineTemplateEngine()
        defn = engine.apply_template("python-ci", {"name": "custom-pipeline"})
        assert defn["name"] == "custom-pipeline"


# ============================================================
# TestPipelineVisualizer
# ============================================================


class TestPipelineVisualizer:

    def test_render_dag(self):
        viz = PipelineVisualizer()
        pipeline = PipelineDefinition(name="test", stages=[
            StageDefinition(name="build"),
            StageDefinition(name="test", depends_on=["build"]),
        ])
        output = viz.render_dag(pipeline)
        assert "build" in output
        assert "test" in output

    def test_render_empty(self):
        viz = PipelineVisualizer()
        pipeline = PipelineDefinition(name="empty", stages=[])
        # DAG builder will raise on empty, but visualizer handles it
        output = viz.render_dag(pipeline)
        assert "empty" in output

    def test_render_run_dag(self):
        viz = PipelineVisualizer()
        run = PipelineRun(run_id="abc", status=PipelineStatus.SUCCESS,
                          stage_results=[
                              StageResult(name="build", status=StageStatus.SUCCESS,
                                          job_results=[JobResult(name="compile", status=JobStatus.SUCCESS)]),
                          ])
        output = viz.render_run_dag(run)
        assert "build" in output
        assert "PASS" in output


# ============================================================
# TestPipelineEngine
# ============================================================


class TestPipelineEngine:

    def test_run_pipeline(self, subsystem):
        engine, _, _ = subsystem
        run = engine.run_pipeline("fizzbuzz-ci")
        assert run.status in (PipelineStatus.SUCCESS, PipelineStatus.FAILED)
        assert run.pipeline_name == "fizzbuzz-ci"
        # At least lint stage runs; test/build may be skipped on random step failure
        assert len(run.stage_results) >= 1

    def test_run_nonexistent(self, subsystem):
        engine, _, _ = subsystem
        with pytest.raises(Exception):
            engine.run_pipeline("nonexistent")

    def test_list_pipelines(self, subsystem):
        engine, _, _ = subsystem
        names = engine.list_pipelines()
        assert "fizzbuzz-ci" in names
        assert "fizzbuzz-deploy" in names
        assert "fizzbuzz-nightly" in names

    def test_get_pipeline(self, subsystem):
        engine, _, _ = subsystem
        p = engine.get_pipeline("fizzbuzz-ci")
        assert p is not None
        assert p.name == "fizzbuzz-ci"

    def test_metrics_updated(self, subsystem):
        engine, _, _ = subsystem
        engine.run_pipeline("fizzbuzz-ci")
        m = engine.get_metrics()
        assert m.total_runs >= 1
        assert m.total_jobs >= 1

    def test_trigger_webhook(self, subsystem):
        engine, _, _ = subsystem
        payload = WebhookPayload(event="push", branch="main", commit_sha="abc123")
        runs = engine.trigger_webhook(payload)
        assert len(runs) >= 1  # fizzbuzz-ci triggers on push

    def test_uptime(self, subsystem):
        engine, _, _ = subsystem
        assert engine.uptime > 0
        assert engine.is_running

    def test_register_pipeline(self, subsystem):
        engine, _, _ = subsystem
        engine.register_pipeline({
            "name": "custom", "stages": [{"name": "s", "jobs": [{"name": "j", "steps": []}]}]
        })
        assert "custom" in engine.list_pipelines()

    def test_matrix_expansion_in_run(self, subsystem):
        engine, _, _ = subsystem
        run = engine.run_pipeline("fizzbuzz-ci")
        test_stages = [sr for sr in run.stage_results if sr.name == "test"]
        if test_stages:
            # Matrix should produce 3 jobs (3.11, 3.12, 3.13)
            assert len(test_stages[0].job_results) == 3

    def test_dag_execution_order(self, subsystem):
        engine, _, _ = subsystem
        run = engine.run_pipeline("fizzbuzz-ci")
        stage_names = [sr.name for sr in run.stage_results]
        # lint always runs first; test and build follow if lint passes
        assert stage_names[0] == "lint"
        if "test" in stage_names and "build" in stage_names:
            assert stage_names.index("test") < stage_names.index("build")


# ============================================================
# TestFizzCIMiddleware
# ============================================================


class TestFizzCIMiddleware:

    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzci"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock()
        ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzci_version"] == FIZZCI_VERSION

    def test_process_delegates(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock()
        ctx.metadata = {}
        handler = MagicMock(return_value=ctx)
        mw.process(ctx, handler)
        handler.assert_called_once()

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_dashboard()
        assert "FizzCI" in output
        assert "Engine" in output

    def test_render_status(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_status()
        assert "FizzCI" in output
        assert "UP" in output

    def test_render_pipelines(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_pipelines()
        assert "fizzbuzz-ci" in output

    def test_render_run_result(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_run_result("fizzbuzz-ci")
        assert "Pipeline:" in output
        assert "fizzbuzz-ci" in output

    def test_render_run_result_nonexistent(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_run_result("nonexistent")
        assert "Error" in output

    def test_render_history(self, subsystem):
        _, _, mw = subsystem
        engine, _, _ = subsystem
        engine.run_pipeline("fizzbuzz-ci")
        output = mw.render_history()
        assert "runs" in output.lower() or "Pipeline" in output

    def test_render_cache_clear(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_cache_clear()
        assert "cleared" in output.lower()

    def test_render_dry_run(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_dry_run("fizzbuzz-ci")
        assert "Stages:" in output
        assert "Jobs:" in output

    def test_render_template(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_template("python-ci")
        assert "Python CI" in output

    def test_render_template_nonexistent(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_template("nonexistent")
        assert "not found" in output.lower()

    def test_render_artifacts(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_artifacts()
        assert "Artifacts" in output

    def test_render_trigger_result(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_trigger_result("push")
        assert "Pipeline:" in output or "matched" in output.lower()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:

    def test_returns_tuple(self):
        result = create_fizzci_subsystem()
        assert len(result) == 3
        engine, dashboard, mw = result
        assert isinstance(engine, PipelineEngine)
        assert isinstance(dashboard, FizzCIDashboard)
        assert isinstance(mw, FizzCIMiddleware)

    def test_engine_started(self):
        engine, _, _ = create_fizzci_subsystem()
        assert engine.is_running

    def test_default_pipelines_registered(self):
        engine, _, _ = create_fizzci_subsystem()
        names = engine.list_pipelines()
        assert "fizzbuzz-ci" in names
        assert "fizzbuzz-deploy" in names
        assert "fizzbuzz-nightly" in names

    def test_custom_config(self):
        engine, _, _ = create_fizzci_subsystem(max_parallel_jobs=16, history_max_runs=50)
        assert engine._config.max_parallel_jobs == 16

    def test_templates_available(self):
        engine, _, _ = create_fizzci_subsystem()
        templates = engine._templates.list_templates()
        assert len(templates) >= 3


# ============================================================
# TestConstants
# ============================================================


class TestConstants:

    def test_version(self):
        assert FIZZCI_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 122

    def test_webhook_events(self):
        assert "push" in WEBHOOK_EVENTS
        assert "pull_request" in WEBHOOK_EVENTS

    def test_pipeline_statuses(self):
        assert PipelineStatus.SUCCESS.name == "SUCCESS"
        assert PipelineStatus.FAILED.name == "FAILED"

    def test_job_statuses(self):
        assert JobStatus.RUNNING.name == "RUNNING"

    def test_trigger_types(self):
        assert TriggerType.PUSH.value == "push"

    def test_retry_strategies(self):
        assert RetryStrategy.FIXED.value == "fixed"
        assert RetryStrategy.EXPONENTIAL.value == "exponential"

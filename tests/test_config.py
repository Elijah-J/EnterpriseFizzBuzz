"""
Enterprise FizzBuzz Platform - Configuration Manager Test Suite

Comprehensive tests for the ConfigurationManager singleton, because
the foundation of the entire platform is a YAML parser wrapped in a
metaclass, and if THAT breaks, Bob gets paged for a configuration
error instead of a FizzBuzz error, which is somehow even sadder.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    ConfigurationError,
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)
from models import EvaluationStrategy, LogLevel, OutputFormat


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before every test.

    The ConfigurationManager is a singleton, and singletons are the
    herpes of software architecture: once you have one, you can never
    fully get rid of it. This fixture does its best.
    """
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def env_cleanup() -> Generator[dict[str, str], None, None]:
    """Provide a dict that tracks env vars to clean up after the test.

    Set env vars via os.environ as usual, and add the key to this dict
    so they're removed in teardown. Because leaking environment variables
    between tests is a violation of the Twelve-Factor App methodology,
    and we take that very seriously for our FizzBuzz platform.
    """
    set_vars: dict[str, str] = {}
    yield set_vars
    for key in set_vars:
        os.environ.pop(key, None)


def _set_env(cleanup: dict[str, str], key: str, value: str) -> None:
    """Helper to set an env var and register it for cleanup."""
    os.environ[key] = value
    cleanup[key] = value


def _make_defaults_config() -> ConfigurationManager:
    """Create a ConfigurationManager loaded from built-in defaults only."""
    cfg = ConfigurationManager(config_path="/nonexistent/path/defaults.yaml")
    cfg._raw_config = cfg._get_defaults()
    cfg._apply_environment_overrides()
    cfg._validate()
    cfg._loaded = True
    return cfg


@pytest.fixture
def defaults_config() -> ConfigurationManager:
    """A ConfigurationManager loaded from built-in defaults.

    No YAML, no env vars, just raw defaults -- the configuration
    equivalent of showing up to work in your underwear.
    """
    return _make_defaults_config()


@pytest.fixture
def minimal_yaml(tmp_path: Path) -> Path:
    """Create a valid YAML config file with values that differ from defaults.

    The bare minimum required to convince the ConfigurationManager that
    the universe is in order, but with different values so we can verify
    overrides actually work.
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
application:
  name: "Test FizzBuzz Platform"
  version: "0.0.1-test"
  environment: "testing"
range:
  start: 1
  end: 20
rules:
  - name: "FizzRule"
    divisor: 3
    label: "Fizz"
    priority: 1
  - name: "BuzzRule"
    divisor: 5
    label: "Buzz"
    priority: 2
engine:
  strategy: "standard"
  max_concurrent_evaluations: 5
  timeout_ms: 1000
output:
  format: "json"
  include_metadata: true
  include_summary: false
  colorize: true
logging:
  level: "DEBUG"
  include_timestamps: false
  log_to_file: true
  log_file_path: "test.log"
circuit_breaker:
  enabled: true
  failure_threshold: 10
  success_threshold: 5
  timeout_ms: 60000
i18n:
  enabled: false
  locale: "de"
  strict_mode: true
tracing:
  enabled: true
  export_format: "json"
  waterfall_width: 80
  timing_precision: "ns"
cache:
  enabled: true
  max_size: 512
  ttl_seconds: 1800.0
  eviction_policy: "fifo"
ml:
  decision_threshold: 0.7
  ambiguity_margin: 0.05
  enable_disagreement_tracking: true
"""
    )
    return config_file


# ============================================================
# Default Values Tests
# ============================================================


class TestDefaultValues:
    """Verify every built-in default is correct.

    These tests ensure that if someone accidentally deletes config.yaml,
    the platform will still compute FizzBuzz with exactly the same
    over-engineered defaults it always has.
    """

    def test_default_application_metadata(self, defaults_config):
        """The platform's identity should resolve correctly from defaults."""
        assert defaults_config.app_name == "Enterprise FizzBuzz Platform"
        assert defaults_config.app_version == "1.0.0"

    def test_default_range(self, defaults_config):
        """FizzBuzz range 1-100: the canonical bounds. Not negotiable."""
        assert defaults_config.range_start == 1
        assert defaults_config.range_end == 100

    def test_default_rules(self, defaults_config):
        """Two rules: Fizz for 3, Buzz for 5. The pillars of civilization."""
        rules = defaults_config.rules
        assert len(rules) == 2
        assert rules[0].name == "FizzRule"
        assert rules[0].divisor == 3
        assert rules[0].label == "Fizz"
        assert rules[1].name == "BuzzRule"
        assert rules[1].divisor == 5
        assert rules[1].label == "Buzz"

    def test_default_strategy_and_output(self, defaults_config):
        """Standard strategy, plain text output. The sensible defaults."""
        assert defaults_config.evaluation_strategy == EvaluationStrategy.STANDARD
        assert defaults_config.output_format == OutputFormat.PLAIN
        assert defaults_config.log_level == LogLevel.INFO

    def test_default_output_flags(self, defaults_config):
        """Summary on, metadata off. Because stakeholders want dashboards, not details."""
        assert defaults_config.include_summary is True
        assert defaults_config.include_metadata is False

    def test_default_circuit_breaker(self, defaults_config):
        """Circuit breaker: disabled, but fully configured for when things go wrong."""
        assert defaults_config.circuit_breaker_enabled is False
        assert defaults_config.circuit_breaker_failure_threshold == 5
        assert defaults_config.circuit_breaker_success_threshold == 3
        assert defaults_config.circuit_breaker_timeout_ms == 30000
        assert defaults_config.circuit_breaker_backoff_multiplier == 2.0
        assert defaults_config.circuit_breaker_ml_confidence_threshold == 0.7

    def test_default_tracing(self, defaults_config):
        """Tracing off by default. The flame graph of 15 % 3 can wait."""
        assert defaults_config.tracing_enabled is False
        assert defaults_config.tracing_waterfall_width == 60
        assert defaults_config.tracing_timing_precision == "us"
        assert defaults_config.tracing_export_format == "waterfall"

    def test_default_i18n(self, defaults_config):
        """i18n on, English locale. Klingon requires opt-in."""
        assert defaults_config.i18n_enabled is True
        assert defaults_config.i18n_locale == "en"
        assert defaults_config.i18n_strict_mode is False
        assert defaults_config.i18n_fallback_chain == ["en"]
        assert defaults_config.i18n_log_missing_keys is True

    def test_default_cache(self, defaults_config):
        """Cache disabled by default. 15 % 3 is always 0, but you never know."""
        assert defaults_config.cache_enabled is False
        assert defaults_config.cache_max_size == 1024
        assert defaults_config.cache_ttl_seconds == 3600.0
        assert defaults_config.cache_eviction_policy == "lru"

    def test_default_ml(self, defaults_config):
        """ML defaults: the most obvious possible settings, made configurable."""
        assert defaults_config.ml_decision_threshold == 0.5
        assert defaults_config.ml_ambiguity_margin == 0.1
        assert defaults_config.ml_enable_disagreement_tracking is False

    def test_default_sla(self, defaults_config):
        """SLA monitoring off. Bob sleeps soundly. For now."""
        assert defaults_config.sla_enabled is False
        assert defaults_config.sla_latency_target == 0.999
        assert defaults_config.sla_accuracy_target == 0.99999
        assert defaults_config.sla_availability_target == 0.9999

    def test_default_subsystem_switches(self, defaults_config):
        """All optional subsystems disabled by default. Modulo needs no help."""
        assert defaults_config.chaos_enabled is False
        assert defaults_config.feature_flags_enabled is False
        assert defaults_config.event_sourcing_enabled is False
        assert defaults_config.migrations_enabled is False

    def test_default_repository(self, defaults_config):
        """No persistence backend. FizzBuzz results vanish like tears in rain."""
        assert defaults_config.repository_backend == "none"
        assert defaults_config.repository_db_path == "fizzbuzz_results.db"
        assert defaults_config.repository_fs_path == "./fizzbuzz_results"

    def test_default_rbac_and_chaos_and_event_sourcing(self, defaults_config):
        """RBAC, chaos, and event sourcing: disabled but fully configured."""
        assert defaults_config.rbac_enabled is False
        assert defaults_config.rbac_default_role == "ANONYMOUS"
        assert defaults_config.rbac_token_ttl_seconds == 3600
        assert defaults_config.rbac_token_issuer == "enterprise-fizzbuzz-platform"
        assert defaults_config.chaos_level == 1
        assert "RESULT_CORRUPTION" in defaults_config.chaos_fault_types
        assert defaults_config.chaos_seed is None
        assert defaults_config.event_sourcing_snapshot_interval == 10
        assert defaults_config.event_sourcing_enable_projections is True


# ============================================================
# YAML Loading Tests
# ============================================================


class TestYamlLoading:
    """Verify that YAML config values override built-in defaults.

    If you go to the trouble of writing a 297-line YAML file, the least
    the platform can do is read it.
    """

    def test_yaml_overrides_application(self, minimal_yaml):
        """Application metadata from YAML should replace defaults."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.app_name == "Test FizzBuzz Platform"
        assert cfg.app_version == "0.0.1-test"

    def test_yaml_overrides_range(self, minimal_yaml):
        """Custom range from YAML should apply."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.range_start == 1
        assert cfg.range_end == 20

    def test_yaml_overrides_output(self, minimal_yaml):
        """Output config from YAML should override all defaults."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.output_format == OutputFormat.JSON
        assert cfg.include_metadata is True
        assert cfg.include_summary is False

    def test_yaml_overrides_circuit_breaker(self, minimal_yaml):
        """Circuit breaker from YAML: enabled with custom thresholds."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.circuit_breaker_enabled is True
        assert cfg.circuit_breaker_failure_threshold == 10

    def test_yaml_overrides_i18n(self, minimal_yaml):
        """i18n from YAML: disabled, German locale, strict mode."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.i18n_enabled is False
        assert cfg.i18n_locale == "de"
        assert cfg.i18n_strict_mode is True

    def test_yaml_overrides_tracing(self, minimal_yaml):
        """Tracing from YAML: enabled, JSON export, 80-wide waterfall."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.tracing_enabled is True
        assert cfg.tracing_export_format == "json"
        assert cfg.tracing_waterfall_width == 80
        assert cfg.tracing_timing_precision == "ns"

    def test_yaml_overrides_cache(self, minimal_yaml):
        """Cache from YAML: enabled, FIFO, smaller capacity."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.cache_enabled is True
        assert cfg.cache_max_size == 512
        assert cfg.cache_ttl_seconds == 1800.0
        assert cfg.cache_eviction_policy == "fifo"

    def test_yaml_overrides_ml(self, minimal_yaml):
        """ML thresholds from YAML: higher confidence, tighter margin."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.ml_decision_threshold == 0.7
        assert cfg.ml_ambiguity_margin == 0.05
        assert cfg.ml_enable_disagreement_tracking is True

    def test_yaml_load_returns_self(self, minimal_yaml):
        """load() returns self for fluent chaining, because enterprise APIs demand it."""
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        result = cfg.load()
        assert result is cfg


# ============================================================
# Environment Variable Override Tests
# ============================================================


class TestEnvironmentVariableOverrides:
    """Verify that EFP_* environment variables override YAML and defaults.

    Environment variables are the runtime escape hatch for when someone
    deploys to production and realizes the YAML says range 1-100 but the
    SLA says 1-10. Twelve-Factor App compliance demands it.
    """

    def test_env_overrides_range(self, env_cleanup):
        """EFP_RANGE_START and EFP_RANGE_END should override defaults."""
        _set_env(env_cleanup, "EFP_RANGE_START", "42")
        _set_env(env_cleanup, "EFP_RANGE_END", "200")
        cfg = _make_defaults_config()
        assert cfg.range_start == 42
        assert cfg.range_end == 200

    def test_env_overrides_output_format(self, env_cleanup):
        """EFP_OUTPUT_FORMAT should override the configured output format."""
        _set_env(env_cleanup, "EFP_OUTPUT_FORMAT", "xml")
        cfg = _make_defaults_config()
        assert cfg.output_format == OutputFormat.XML

    def test_env_overrides_log_level(self, env_cleanup):
        """EFP_LOG_LEVEL should override the configured log level."""
        _set_env(env_cleanup, "EFP_LOG_LEVEL", "DEBUG")
        cfg = _make_defaults_config()
        assert cfg.log_level == LogLevel.DEBUG

    def test_env_overrides_strategy(self, env_cleanup):
        """EFP_STRATEGY should override the evaluation strategy."""
        _set_env(env_cleanup, "EFP_STRATEGY", "chain_of_responsibility")
        cfg = _make_defaults_config()
        assert cfg.evaluation_strategy == EvaluationStrategy.CHAIN_OF_RESPONSIBILITY

    def test_env_overrides_locale(self, env_cleanup):
        """EFP_LOCALE should override the i18n locale. qapla'!"""
        _set_env(env_cleanup, "EFP_LOCALE", "tlh")
        cfg = _make_defaults_config()
        assert cfg.i18n_locale == "tlh"

    def test_env_overrides_tracing_enabled(self, env_cleanup):
        """EFP_TRACING_ENABLED accepts 'true', 'yes', and '1' as truthy values."""
        for truthy in ("true", "yes", "1"):
            _SingletonMeta.reset()
            _set_env(env_cleanup, "EFP_TRACING_ENABLED", truthy)
            cfg = _make_defaults_config()
            assert cfg.tracing_enabled is True, f"Failed for truthy value: {truthy}"

    def test_env_tracing_false_values(self, env_cleanup):
        """EFP_TRACING_ENABLED with 'false', 'no', '0' should disable tracing."""
        for falsy in ("false", "no", "0"):
            _SingletonMeta.reset()
            _set_env(env_cleanup, "EFP_TRACING_ENABLED", falsy)
            cfg = _make_defaults_config()
            assert cfg.tracing_enabled is False, f"Failed for falsy value: {falsy}"

    def test_env_overrides_yaml_values(self, minimal_yaml, env_cleanup):
        """Environment variables take precedence over YAML values.

        YAML says json, env says csv. csv wins. Hierarchy is everything.
        """
        _set_env(env_cleanup, "EFP_OUTPUT_FORMAT", "csv")
        cfg = ConfigurationManager(config_path=str(minimal_yaml))
        cfg.load()
        assert cfg.output_format == OutputFormat.CSV


# ============================================================
# Type Coercion Tests
# ============================================================


class TestTypeCoercion:
    """Verify that string environment variables are correctly cast to typed values.

    Environment variables are always strings, because the Unix designers
    in the 1970s didn't anticipate that someone would need to pass a
    boolean to a FizzBuzz configuration manager 50 years later.
    """

    def test_int_coercion(self, env_cleanup):
        """String env vars for integer fields should be cast to int."""
        _set_env(env_cleanup, "EFP_RANGE_START", "42")
        _set_env(env_cleanup, "EFP_RANGE_END", "999")
        cfg = _make_defaults_config()
        assert cfg.range_start == 42
        assert isinstance(cfg.range_start, int)
        assert cfg.range_end == 999
        assert isinstance(cfg.range_end, int)

    def test_bool_coercion(self, env_cleanup):
        """String env vars for boolean fields should be cast to bool."""
        _set_env(env_cleanup, "EFP_TRACING_ENABLED", "true")
        cfg = _make_defaults_config()
        assert cfg.tracing_enabled is True
        assert isinstance(cfg.tracing_enabled, bool)

    def test_invalid_int_coercion_raises(self, env_cleanup):
        """Non-numeric string for an int field should raise ConfigurationValidationError.

        Because 'banana' is not a valid range start, no matter how much
        you believe in dynamic typing.
        """
        _set_env(env_cleanup, "EFP_RANGE_START", "banana")
        cfg = ConfigurationManager(config_path="/nonexistent.yaml")
        cfg._raw_config = cfg._get_defaults()
        with pytest.raises(ConfigurationValidationError):
            cfg._apply_environment_overrides()

    def test_float_string_for_int_raises(self, env_cleanup):
        """A float string for an integer field should raise ConfigurationValidationError."""
        _set_env(env_cleanup, "EFP_RANGE_START", "3.14")
        cfg = ConfigurationManager(config_path="/nonexistent.yaml")
        cfg._raw_config = cfg._get_defaults()
        with pytest.raises(ConfigurationValidationError):
            cfg._apply_environment_overrides()

    def test_string_coercion_preserves_type(self, env_cleanup):
        """String env vars for string fields should remain strings."""
        _set_env(env_cleanup, "EFP_OUTPUT_FORMAT", "csv")
        cfg = _make_defaults_config()
        raw_value = cfg.get_raw("output.format")
        assert isinstance(raw_value, str)
        assert raw_value == "csv"


# ============================================================
# Missing Config File Tests
# ============================================================


class TestMissingConfigFile:
    """Verify graceful behavior when the YAML file doesn't exist.

    In production, someone will inevitably delete config.yaml and then
    wonder why things stopped working. These tests verify the platform
    fails with dignity.
    """

    def test_missing_yaml_raises_file_not_found(self):
        """Loading a nonexistent YAML file should raise ConfigurationFileNotFoundError."""
        cfg = ConfigurationManager(config_path="/this/file/does/not/exist.yaml")
        with pytest.raises(ConfigurationFileNotFoundError):
            cfg.load()

    def test_missing_yaml_error_contains_path(self):
        """The error should include the path to the missing file for debugging."""
        cfg = ConfigurationManager(config_path="/tmp/missing_fizzbuzz_config_12345.yaml")
        with pytest.raises(ConfigurationFileNotFoundError) as exc_info:
            cfg.load()
        # Path may be normalized with backslashes on Windows
        assert "missing_fizzbuzz_config_12345.yaml" in str(exc_info.value)


# ============================================================
# Singleton Behavior Tests
# ============================================================


class TestSingletonBehavior:
    """Verify the _SingletonMeta metaclass ensures only one instance exists.

    The Singleton pattern: because if one ConfigurationManager is good,
    two would be an existential crisis. There can be only one source of
    truth for whether FizzBuzz starts at 1 or 42.
    """

    def test_same_instance_returned(self):
        """Multiple constructor calls should return the exact same instance."""
        cfg1 = ConfigurationManager()
        cfg2 = ConfigurationManager()
        assert cfg1 is cfg2

    def test_singleton_survives_different_args(self):
        """The singleton ignores arguments after first instantiation.

        The first caller wins. Democracy is overrated in configuration.
        """
        cfg1 = ConfigurationManager(config_path="/first/path.yaml")
        cfg2 = ConfigurationManager(config_path="/second/path.yaml")
        assert cfg1 is cfg2

    def test_reset_clears_singleton(self):
        """_SingletonMeta.reset() should allow a fresh instance to be created."""
        cfg1 = ConfigurationManager()
        _SingletonMeta.reset()
        cfg2 = ConfigurationManager()
        assert cfg1 is not cfg2

    def test_singleton_preserves_state(self, minimal_yaml):
        """Loading config on one reference should be visible on the other.

        If two references to the same object see different state,
        we have bigger problems than FizzBuzz.
        """
        cfg1 = ConfigurationManager(config_path=str(minimal_yaml))
        cfg1.load()
        cfg2 = ConfigurationManager()
        assert cfg2.app_name == "Test FizzBuzz Platform"


# ============================================================
# Invalid Config Values Tests
# ============================================================


class TestInvalidConfigValues:
    """Verify that invalid configuration values raise appropriate errors.

    The validation layer catches misconfigurations before they propagate
    through 15 middleware layers and manifest as a corrupted FizzBuzz
    result, which would be a compliance incident.
    """

    def test_range_start_greater_than_end(self, tmp_path):
        """Range where start > end should raise ConfigurationValidationError.

        FizzBuzz from 100 to 1 is not a thing. Not yet.
        """
        config_file = tmp_path / "bad_range.yaml"
        config_file.write_text(
            "range:\n  start: 100\n  end: 1\n"
            "engine:\n  strategy: standard\n"
            "output:\n  format: plain\n"
        )
        cfg = ConfigurationManager(config_path=str(config_file))
        with pytest.raises(ConfigurationValidationError):
            cfg.load()

    def test_invalid_output_format(self, tmp_path):
        """An unknown output format should raise ConfigurationValidationError.

        'hologram' is not a supported output format. Yet.
        """
        config_file = tmp_path / "bad_format.yaml"
        config_file.write_text(
            "range:\n  start: 1\n  end: 10\n"
            "engine:\n  strategy: standard\n"
            "output:\n  format: hologram\n"
        )
        cfg = ConfigurationManager(config_path=str(config_file))
        with pytest.raises(ConfigurationValidationError):
            cfg.load()

    def test_invalid_strategy(self, tmp_path):
        """An unknown strategy should raise ConfigurationValidationError.

        'quantum_computing' is not a supported strategy, though it would
        certainly be on-brand for this platform.
        """
        config_file = tmp_path / "bad_strategy.yaml"
        config_file.write_text(
            "range:\n  start: 1\n  end: 10\n"
            "engine:\n  strategy: quantum_computing\n"
            "output:\n  format: plain\n"
        )
        cfg = ConfigurationManager(config_path=str(config_file))
        with pytest.raises(ConfigurationValidationError):
            cfg.load()

    def test_invalid_format_via_env(self, env_cleanup):
        """EFP_OUTPUT_FORMAT set to a nonsense format should fail validation."""
        _set_env(env_cleanup, "EFP_OUTPUT_FORMAT", "interpretive_dance")
        cfg = ConfigurationManager(config_path="/nonexistent.yaml")
        cfg._raw_config = cfg._get_defaults()
        cfg._apply_environment_overrides()
        with pytest.raises(ConfigurationValidationError):
            cfg._validate()

    def test_invalid_strategy_via_env(self, env_cleanup):
        """EFP_STRATEGY set to an unknown strategy should fail validation."""
        _set_env(env_cleanup, "EFP_STRATEGY", "blockchain_consensus")
        cfg = ConfigurationManager(config_path="/nonexistent.yaml")
        cfg._raw_config = cfg._get_defaults()
        cfg._apply_environment_overrides()
        with pytest.raises(ConfigurationValidationError):
            cfg._validate()

    def test_equal_range_is_valid(self, tmp_path):
        """Range where start == end should be accepted (one-element FizzBuzz)."""
        config_file = tmp_path / "one_element.yaml"
        config_file.write_text(
            "range:\n  start: 42\n  end: 42\n"
            "engine:\n  strategy: standard\n"
            "output:\n  format: plain\n"
        )
        cfg = ConfigurationManager(config_path=str(config_file))
        cfg.load()
        assert cfg.range_start == 42
        assert cfg.range_end == 42


# ============================================================
# Ensure Loaded Guard Tests
# ============================================================


class TestEnsureLoadedGuard:
    """Verify that accessing properties before load() raises ConfigurationError.

    The _ensure_loaded() guard exists because someone will inevitably
    forget to call load() and then wonder why app_name is None. This is
    the guard rail at the edge of the cliff.
    """

    def test_property_access_before_load_raises(self):
        """Accessing any property before load() should raise ConfigurationError."""
        cfg = ConfigurationManager()
        with pytest.raises(ConfigurationError):
            _ = cfg.app_name

    def test_multiple_properties_before_load_raise(self):
        """Several different properties should all raise before load()."""
        cfg = ConfigurationManager()
        for prop in ("range_start", "rules", "evaluation_strategy", "cache_enabled"):
            with pytest.raises(ConfigurationError):
                getattr(cfg, prop)

    def test_get_raw_before_load_raises(self):
        """get_raw() before load() should also raise ConfigurationError."""
        cfg = ConfigurationManager()
        with pytest.raises(ConfigurationError):
            cfg.get_raw("application.name")


# ============================================================
# get_raw() Tests
# ============================================================


class TestGetRaw:
    """Verify the dot-separated key path accessor.

    get_raw() is the escape hatch for when the 70+ typed properties
    aren't enough and someone needs to spelunk into the raw config dict
    with a flashlight and a prayer.
    """

    def test_get_raw_top_level_section(self, defaults_config):
        """Accessing a top-level section returns the full dict."""
        app = defaults_config.get_raw("application")
        assert isinstance(app, dict)
        assert app["name"] == "Enterprise FizzBuzz Platform"

    def test_get_raw_nested_key(self, defaults_config):
        """Accessing a nested key via dot notation returns the leaf value."""
        assert defaults_config.get_raw("range.start") == 1
        assert defaults_config.get_raw("range.end") == 100

    def test_get_raw_deeply_nested(self, defaults_config):
        """Accessing a deeply nested key works correctly."""
        assert defaults_config.get_raw("cache.warming.enabled") is False
        assert defaults_config.get_raw("sla.slos.latency.target") == 0.999

    def test_get_raw_missing_key(self, defaults_config):
        """Missing keys return the provided default (or None)."""
        assert defaults_config.get_raw("nonexistent.key", "fallback") == "fallback"
        assert defaults_config.get_raw("does.not.exist") is None

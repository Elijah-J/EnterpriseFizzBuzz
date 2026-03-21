"""
Enterprise FizzBuzz Platform - Configuration Management Module

Implements a Singleton-based configuration manager with YAML loading,
environment variable overrides, and runtime validation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from exceptions import (
    ConfigurationError,
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)
from models import EvaluationStrategy, LogLevel, OutputFormat, RuleDefinition

logger = logging.getLogger(__name__)

# Default config path, overridable via environment variable
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _SingletonMeta(type):
    """Metaclass implementing the Singleton pattern.

    Ensures that only one instance of the ConfigurationManager exists
    across the entire application lifecycle.
    """

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset all singleton instances. Used for testing."""
        mcs._instances.clear()


class ConfigurationManager(metaclass=_SingletonMeta):
    """Singleton configuration manager for the Enterprise FizzBuzz Platform.

    Loads configuration from YAML, applies environment variable overrides,
    and provides validated, typed access to all configuration values.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._config_path = Path(
            config_path
            or os.environ.get("EFP_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH))
        )
        self._raw_config: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> ConfigurationManager:
        """Load and validate configuration from YAML file."""
        try:
            import yaml
        except ImportError:
            # Fallback to built-in defaults if PyYAML is not installed
            logger.warning(
                "PyYAML not installed. Using built-in default configuration."
            )
            self._raw_config = self._get_defaults()
            self._apply_environment_overrides()
            self._validate()
            self._loaded = True
            return self

        if not self._config_path.exists():
            raise ConfigurationFileNotFoundError(str(self._config_path))

        with open(self._config_path, "r") as f:
            self._raw_config = yaml.safe_load(f) or {}

        self._apply_environment_overrides()
        self._validate()
        self._loaded = True
        logger.info("Configuration loaded from %s", self._config_path)
        return self

    def _get_defaults(self) -> dict[str, Any]:
        """Return built-in default configuration."""
        return {
            "application": {
                "name": "Enterprise FizzBuzz Platform",
                "version": "1.0.0",
                "environment": "production",
            },
            "range": {"start": 1, "end": 100},
            "rules": [
                {"name": "FizzRule", "divisor": 3, "label": "Fizz", "priority": 1},
                {"name": "BuzzRule", "divisor": 5, "label": "Buzz", "priority": 2},
            ],
            "engine": {
                "strategy": "standard",
                "max_concurrent_evaluations": 10,
                "timeout_ms": 5000,
            },
            "output": {
                "format": "plain",
                "include_metadata": False,
                "include_summary": True,
                "colorize": False,
            },
            "logging": {
                "level": "INFO",
                "include_timestamps": True,
                "log_to_file": False,
                "log_file_path": "fizzbuzz.log",
            },
            "middleware": {
                "timing": {"enabled": True, "priority": 1},
                "logging": {"enabled": True, "priority": 2},
                "validation": {"enabled": True, "priority": 0},
            },
            "plugins": {
                "auto_discover": True,
                "plugin_directory": "./plugins",
                "enabled_plugins": [],
            },
            "circuit_breaker": {
                "enabled": False,
                "failure_threshold": 5,
                "success_threshold": 3,
                "timeout_ms": 30000,
                "sliding_window_size": 10,
                "half_open_max_calls": 3,
                "backoff_base_ms": 1000,
                "backoff_max_ms": 60000,
                "backoff_multiplier": 2.0,
                "ml_confidence_threshold": 0.7,
                "call_timeout_ms": 5000,
            },
            "i18n": {
                "enabled": True,
                "locale": "en",
                "locale_directory": "./locales",
                "strict_mode": False,
                "fallback_chain": ["en"],
                "log_missing_keys": True,
            },
            "observers": {
                "console_observer": {"enabled": False},
                "statistics_observer": {"enabled": True},
            },
        }

    def _apply_environment_overrides(self) -> None:
        """Apply environment variable overrides to configuration.

        Environment variables follow the pattern EFP_<SECTION>_<KEY>.
        Example: EFP_RANGE_START=1, EFP_OUTPUT_FORMAT=json
        """
        env_mappings = {
            "EFP_RANGE_START": ("range", "start", int),
            "EFP_RANGE_END": ("range", "end", int),
            "EFP_OUTPUT_FORMAT": ("output", "format", str),
            "EFP_LOG_LEVEL": ("logging", "level", str),
            "EFP_STRATEGY": ("engine", "strategy", str),
            "EFP_LOCALE": ("i18n", "locale", str),
        }

        for env_var, (section, key, cast) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                try:
                    self._raw_config.setdefault(section, {})[key] = cast(value)
                    logger.debug(
                        "Environment override: %s=%s", env_var, value
                    )
                except (ValueError, TypeError) as e:
                    raise ConfigurationValidationError(
                        env_var, value, cast.__name__
                    ) from e

    def _validate(self) -> None:
        """Validate all configuration values."""
        range_cfg = self._raw_config.get("range", {})
        start = range_cfg.get("start", 1)
        end = range_cfg.get("end", 100)
        if not isinstance(start, int) or not isinstance(end, int):
            raise ConfigurationValidationError(
                "range.start/end", f"{start}/{end}", "int"
            )
        if start > end:
            raise ConfigurationValidationError(
                "range", f"start={start} > end={end}", "start <= end"
            )

        output_format = self._raw_config.get("output", {}).get("format", "plain")
        valid_formats = {"plain", "json", "xml", "csv"}
        if output_format not in valid_formats:
            raise ConfigurationValidationError(
                "output.format", output_format, f"one of {valid_formats}"
            )

        strategy = self._raw_config.get("engine", {}).get("strategy", "standard")
        valid_strategies = {"standard", "chain_of_responsibility", "parallel_async", "machine_learning"}
        if strategy not in valid_strategies:
            raise ConfigurationValidationError(
                "engine.strategy", strategy, f"one of {valid_strategies}"
            )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise ConfigurationError("Configuration not loaded. Call load() first.")

    @property
    def app_name(self) -> str:
        self._ensure_loaded()
        return self._raw_config["application"]["name"]

    @property
    def app_version(self) -> str:
        self._ensure_loaded()
        return self._raw_config["application"]["version"]

    @property
    def range_start(self) -> int:
        self._ensure_loaded()
        return self._raw_config["range"]["start"]

    @property
    def range_end(self) -> int:
        self._ensure_loaded()
        return self._raw_config["range"]["end"]

    @property
    def rules(self) -> list[RuleDefinition]:
        self._ensure_loaded()
        return [
            RuleDefinition(
                name=r["name"],
                divisor=r["divisor"],
                label=r["label"],
                priority=r.get("priority", 0),
            )
            for r in self._raw_config.get("rules", [])
        ]

    @property
    def evaluation_strategy(self) -> EvaluationStrategy:
        self._ensure_loaded()
        strategy_map = {
            "standard": EvaluationStrategy.STANDARD,
            "chain_of_responsibility": EvaluationStrategy.CHAIN_OF_RESPONSIBILITY,
            "parallel_async": EvaluationStrategy.PARALLEL_ASYNC,
            "machine_learning": EvaluationStrategy.MACHINE_LEARNING,
        }
        return strategy_map[self._raw_config["engine"]["strategy"]]

    @property
    def output_format(self) -> OutputFormat:
        self._ensure_loaded()
        format_map = {
            "plain": OutputFormat.PLAIN,
            "json": OutputFormat.JSON,
            "xml": OutputFormat.XML,
            "csv": OutputFormat.CSV,
        }
        return format_map[self._raw_config["output"]["format"]]

    @property
    def log_level(self) -> LogLevel:
        self._ensure_loaded()
        level_map = {
            "SILENT": LogLevel.SILENT,
            "ERROR": LogLevel.ERROR,
            "WARNING": LogLevel.WARNING,
            "INFO": LogLevel.INFO,
            "DEBUG": LogLevel.DEBUG,
            "TRACE": LogLevel.TRACE,
        }
        return level_map.get(
            self._raw_config.get("logging", {}).get("level", "INFO"),
            LogLevel.INFO,
        )

    @property
    def include_summary(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("output", {}).get("include_summary", True)

    @property
    def include_metadata(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("output", {}).get("include_metadata", False)

    @property
    def circuit_breaker_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("enabled", False)

    @property
    def circuit_breaker_failure_threshold(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("failure_threshold", 5)

    @property
    def circuit_breaker_success_threshold(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("success_threshold", 3)

    @property
    def circuit_breaker_timeout_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("timeout_ms", 30000)

    @property
    def circuit_breaker_sliding_window_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("sliding_window_size", 10)

    @property
    def circuit_breaker_half_open_max_calls(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("half_open_max_calls", 3)

    @property
    def circuit_breaker_backoff_base_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_base_ms", 1000)

    @property
    def circuit_breaker_backoff_max_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_max_ms", 60000)

    @property
    def circuit_breaker_backoff_multiplier(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_multiplier", 2.0)

    @property
    def circuit_breaker_ml_confidence_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("ml_confidence_threshold", 0.7)

    @property
    def circuit_breaker_call_timeout_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("call_timeout_ms", 5000)

    @property
    def i18n_enabled(self) -> bool:
        """Whether the internationalization subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("enabled", True)

    @property
    def i18n_locale(self) -> str:
        """The active locale code (e.g. 'en', 'fr', 'tlh')."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("locale", "en")

    @property
    def i18n_locale_directory(self) -> str:
        """Path to the directory containing .fizztranslation files."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("locale_directory", "./locales")

    @property
    def i18n_strict_mode(self) -> bool:
        """Whether missing translation keys should raise errors."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("strict_mode", False)

    @property
    def i18n_fallback_chain(self) -> list[str]:
        """Global fallback chain for locale resolution."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("fallback_chain", ["en"])

    @property
    def i18n_log_missing_keys(self) -> bool:
        """Whether to log warnings for missing translation keys."""
        self._ensure_loaded()
        return self._raw_config.get("i18n", {}).get("log_missing_keys", True)

    def get_raw(self, key: str, default: Any = None) -> Any:
        """Get a raw configuration value by dot-separated key path."""
        self._ensure_loaded()
        keys = key.split(".")
        value: Any = self._raw_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

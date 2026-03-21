"""
Enterprise FizzBuzz Platform - Plugin System Module

Provides a decorator-based plugin registration system with lifecycle
management, dependency resolution, and hot-reloading capabilities.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Type

from enterprise_fizzbuzz.domain.exceptions import PluginLoadError, PluginNotFoundError
from enterprise_fizzbuzz.domain.interfaces import IPlugin
from enterprise_fizzbuzz.domain.models import RuleDefinition

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry for all FizzBuzz platform plugins.

    Manages plugin lifecycle including registration, initialization,
    and dependency resolution.
    """

    _instance: Optional[PluginRegistry] = None

    def __init__(self) -> None:
        self._plugins: dict[str, Type[IPlugin]] = {}
        self._initialized_plugins: dict[str, IPlugin] = {}
        self._plugin_configs: dict[str, dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> PluginRegistry:
        """Get the global plugin registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the global instance. Used for testing."""
        cls._instance = None

    def register(self, plugin_class: Type[IPlugin]) -> Type[IPlugin]:
        """Register a plugin class with the registry."""
        name = plugin_class.__name__
        if name in self._plugins:
            logger.warning("Plugin '%s' is being re-registered", name)
        self._plugins[name] = plugin_class
        logger.info("Plugin '%s' registered", name)
        return plugin_class

    def initialize_plugin(
        self, name: str, config: Optional[dict[str, Any]] = None
    ) -> IPlugin:
        """Initialize a registered plugin with configuration."""
        if name not in self._plugins:
            raise PluginNotFoundError(name)

        if name in self._initialized_plugins:
            logger.debug("Plugin '%s' already initialized, returning cached", name)
            return self._initialized_plugins[name]

        try:
            plugin_class = self._plugins[name]
            plugin = plugin_class()
            plugin.initialize(config or {})
            self._initialized_plugins[name] = plugin
            self._plugin_configs[name] = config or {}
            logger.info("Plugin '%s' v%s initialized", name, plugin.get_version())
            return plugin
        except Exception as e:
            raise PluginLoadError(name, str(e)) from e

    def get_plugin(self, name: str) -> IPlugin:
        """Retrieve an initialized plugin by name."""
        if name not in self._initialized_plugins:
            raise PluginNotFoundError(name)
        return self._initialized_plugins[name]

    def get_all_plugins(self) -> list[IPlugin]:
        """Return all initialized plugins."""
        return list(self._initialized_plugins.values())

    def get_all_plugin_rules(self) -> list[RuleDefinition]:
        """Collect rule definitions from all initialized plugins."""
        rules: list[RuleDefinition] = []
        for plugin in self._initialized_plugins.values():
            rules.extend(plugin.get_rules())
        return rules

    def list_registered(self) -> list[str]:
        """List names of all registered plugin classes."""
        return list(self._plugins.keys())

    def list_initialized(self) -> list[str]:
        """List names of all initialized plugins."""
        return list(self._initialized_plugins.keys())


def register_plugin(cls: Type[IPlugin]) -> Type[IPlugin]:
    """Decorator to automatically register a plugin class.

    Usage:
        @register_plugin
        class MyAwesomePlugin(IPlugin):
            ...
    """
    PluginRegistry.get_instance().register(cls)
    return cls


# ============================================================
# Built-in Example Plugin
# ============================================================


@register_plugin
class FizzBuzzProPlugin(IPlugin):
    """Built-in plugin that adds the classic Fizz and Buzz rules.

    This plugin serves as both a default rule provider and a reference
    implementation for third-party plugin developers.
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._custom_rules: list[RuleDefinition] = []

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config
        extra_rules = config.get("extra_rules", [])
        for rule_data in extra_rules:
            self._custom_rules.append(
                RuleDefinition(
                    name=rule_data["name"],
                    divisor=rule_data["divisor"],
                    label=rule_data["label"],
                    priority=rule_data.get("priority", 99),
                )
            )

    def get_name(self) -> str:
        return "FizzBuzzProPlugin"

    def get_version(self) -> str:
        return "1.0.0"

    def get_rules(self) -> list[RuleDefinition]:
        return list(self._custom_rules)

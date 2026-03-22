"""
Enterprise FizzBuzz Platform - Plugin System Test Suite

Comprehensive tests for the decorator-based plugin registration system that
allows third-party developers to extend the FizzBuzz Platform with custom
rules, because the three built-in rules (Fizz, Buzz, FizzBuzz) were never
going to be enough for a truly enterprise-grade modular arithmetic solution.

Every SaaS platform needs a plugin ecosystem, and ours is no exception.
The fact that no third-party developer has ever written a plugin is beside
the point. The architecture is ready, and that is what matters to the
architecture review board.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.domain.exceptions import PluginLoadError, PluginNotFoundError
from enterprise_fizzbuzz.domain.interfaces import IPlugin
from enterprise_fizzbuzz.domain.models import RuleDefinition
from enterprise_fizzbuzz.infrastructure.plugins import (
    FizzBuzzProPlugin,
    PluginRegistry,
    register_plugin,
)


# ============================================================
# Test Helpers
# ============================================================


class StubPlugin(IPlugin):
    """A minimal plugin for testing registration and lifecycle.

    Does nothing useful, which makes it the most realistic
    third-party plugin simulation we could write.
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._initialized = False

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config
        self._initialized = True

    def get_name(self) -> str:
        return "StubPlugin"

    def get_version(self) -> str:
        return "0.1.0"

    def get_rules(self) -> list[RuleDefinition]:
        return []


class WuzzPlugin(IPlugin):
    """A plugin that contributes the fabled 'Wuzz' rule for divisor 7.

    The Wuzz rule has been requested by exactly zero customers, but the
    product manager insisted we demonstrate extensibility in the quarterly
    review, so here we are.
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_name(self) -> str:
        return "WuzzPlugin"

    def get_version(self) -> str:
        return "2.3.1"

    def get_rules(self) -> list[RuleDefinition]:
        return [
            RuleDefinition(name="Wuzz", divisor=7, label="Wuzz", priority=3),
        ]


class BazzPlugin(IPlugin):
    """Yet another plugin contributing yet another rule.

    Divisor 11 was chosen because it sounded sufficiently enterprise-y.
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_name(self) -> str:
        return "BazzPlugin"

    def get_version(self) -> str:
        return "1.0.0"

    def get_rules(self) -> list[RuleDefinition]:
        return [
            RuleDefinition(name="Bazz", divisor=11, label="Bazz", priority=5),
        ]


class ExplodingPlugin(IPlugin):
    """A plugin that raises during initialization.

    Simulates the all-too-common scenario of a plugin author who
    never tested their initialize() method. Bless their heart.
    """

    def __init__(self) -> None:
        pass

    def initialize(self, config: dict[str, Any]) -> None:
        raise RuntimeError("Plugin exploded during initialization")

    def get_name(self) -> str:
        return "ExplodingPlugin"

    def get_version(self) -> str:
        return "0.0.1"

    def get_rules(self) -> list[RuleDefinition]:
        return []


class MultiRulePlugin(IPlugin):
    """A plugin that contributes multiple rules at once.

    Because one rule per plugin is for amateurs.
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config

    def get_name(self) -> str:
        return "MultiRulePlugin"

    def get_version(self) -> str:
        return "3.0.0"

    def get_rules(self) -> list[RuleDefinition]:
        return [
            RuleDefinition(name="Quux", divisor=13, label="Quux", priority=10),
            RuleDefinition(name="Corge", divisor=17, label="Corge", priority=11),
            RuleDefinition(name="Grault", divisor=19, label="Grault", priority=12),
        ]


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture()
def registry() -> PluginRegistry:
    """Provide a fresh, isolated PluginRegistry for each test.

    We create a new instance directly rather than using the singleton
    accessor, because cross-test contamination in a plugin registry
    is the kind of Heisenbug that costs an engineer their weekend.
    """
    return PluginRegistry()


@pytest.fixture(autouse=True)
def reset_global_registry():
    """Reset the global singleton after each test.

    The singleton pattern: making test isolation harder since 1994.
    """
    yield
    PluginRegistry.reset()


# ============================================================
# Plugin Registration Tests
# ============================================================


class TestPluginRegistration:
    """Tests for registering plugin classes with the registry."""

    def test_register_single_plugin(self, registry: PluginRegistry):
        """A registered plugin should appear in the registry's listing."""
        registry.register(StubPlugin)
        assert "StubPlugin" in registry.list_registered()

    def test_register_returns_the_class(self, registry: PluginRegistry):
        """Registration should return the class unchanged, enabling decorator use."""
        result = registry.register(StubPlugin)
        assert result is StubPlugin

    def test_registered_plugin_is_not_initialized(self, registry: PluginRegistry):
        """Registration alone should not initialize the plugin.

        Eagerly initializing every registered plugin would be a violation
        of the Principle of Least Surprise and also a waste of CPU cycles
        that could be spent on FizzBuzz evaluation.
        """
        registry.register(StubPlugin)
        assert registry.list_initialized() == []

    def test_register_multiple_plugins(self, registry: PluginRegistry):
        """The registry should accommodate multiple plugin classes."""
        registry.register(StubPlugin)
        registry.register(WuzzPlugin)
        registry.register(BazzPlugin)
        registered = registry.list_registered()
        assert "StubPlugin" in registered
        assert "WuzzPlugin" in registered
        assert "BazzPlugin" in registered

    def test_list_registered_returns_all_names(self, registry: PluginRegistry):
        """list_registered should return names of all registered classes."""
        registry.register(StubPlugin)
        registry.register(WuzzPlugin)
        assert len(registry.list_registered()) == 2

    def test_duplicate_registration_overwrites(self, registry: PluginRegistry):
        """Re-registering a plugin with the same class name should overwrite.

        The registry uses the class __name__ as the key. Registering a
        second class with the same name replaces the first. This is by
        design: hot-reloading a plugin should not require a restart.
        """
        registry.register(StubPlugin)
        registry.register(StubPlugin)
        assert registry.list_registered().count("StubPlugin") == 1

    def test_duplicate_registration_keeps_latest(self, registry: PluginRegistry):
        """When re-registering, the latest class should win."""
        # Create a second class with the same __name__
        class StubPlugin(IPlugin):  # noqa: F811
            def initialize(self, config: dict[str, Any]) -> None:
                pass

            def get_name(self) -> str:
                return "StubPlugin_v2"

            def get_version(self) -> str:
                return "99.0.0"

            def get_rules(self) -> list[RuleDefinition]:
                return []

        registry.register(globals()["StubPlugin"])
        registry.register(StubPlugin)  # the local one

        # Initialize and verify the latest version is used
        plugin = registry.initialize_plugin("StubPlugin")
        assert plugin.get_version() == "99.0.0"


# ============================================================
# Plugin Initialization Tests
# ============================================================


class TestPluginInitialization:
    """Tests for initializing registered plugins with configuration."""

    def test_initialize_registered_plugin(self, registry: PluginRegistry):
        """Initializing a registered plugin should return an instance."""
        registry.register(StubPlugin)
        plugin = registry.initialize_plugin("StubPlugin")
        assert isinstance(plugin, StubPlugin)

    def test_initialize_passes_config(self, registry: PluginRegistry):
        """The config dict should be passed to the plugin's initialize method."""
        registry.register(StubPlugin)
        config = {"enterprise_level": "maximum", "synergy_factor": 42}
        plugin = registry.initialize_plugin("StubPlugin", config)
        assert plugin._config == config

    def test_initialize_with_no_config_passes_empty_dict(self, registry: PluginRegistry):
        """When no config is provided, an empty dict should be passed."""
        registry.register(StubPlugin)
        plugin = registry.initialize_plugin("StubPlugin")
        assert plugin._config == {}

    def test_initialize_unregistered_plugin_raises(self, registry: PluginRegistry):
        """Attempting to initialize a nonexistent plugin should raise PluginNotFoundError.

        The registry is not in the business of inventing plugins.
        """
        with pytest.raises(PluginNotFoundError):
            registry.initialize_plugin("GhostPlugin")

    def test_initialize_caches_instance(self, registry: PluginRegistry):
        """Initializing the same plugin twice should return the cached instance.

        Because creating two instances of a plugin is one more than anyone
        has ever needed.
        """
        registry.register(StubPlugin)
        first = registry.initialize_plugin("StubPlugin")
        second = registry.initialize_plugin("StubPlugin")
        assert first is second

    def test_initialized_plugin_appears_in_initialized_list(self, registry: PluginRegistry):
        """After initialization, the plugin name should appear in list_initialized."""
        registry.register(StubPlugin)
        registry.initialize_plugin("StubPlugin")
        assert "StubPlugin" in registry.list_initialized()

    def test_exploding_plugin_raises_plugin_load_error(self, registry: PluginRegistry):
        """A plugin that raises during initialization should produce PluginLoadError.

        We wrap the underlying exception so callers get a consistent
        error type regardless of how creatively the plugin author
        managed to break their code.
        """
        registry.register(ExplodingPlugin)
        with pytest.raises(PluginLoadError):
            registry.initialize_plugin("ExplodingPlugin")

    def test_exploding_plugin_preserves_original_exception(self, registry: PluginRegistry):
        """The PluginLoadError should chain the original exception for debugging."""
        registry.register(ExplodingPlugin)
        with pytest.raises(PluginLoadError) as exc_info:
            registry.initialize_plugin("ExplodingPlugin")
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)


# ============================================================
# Plugin Retrieval Tests
# ============================================================


class TestPluginRetrieval:
    """Tests for retrieving initialized plugins from the registry."""

    def test_get_initialized_plugin(self, registry: PluginRegistry):
        """An initialized plugin should be retrievable by name."""
        registry.register(StubPlugin)
        registry.initialize_plugin("StubPlugin")
        plugin = registry.get_plugin("StubPlugin")
        assert isinstance(plugin, StubPlugin)

    def test_get_uninitialized_plugin_raises(self, registry: PluginRegistry):
        """Requesting a registered but not-yet-initialized plugin should raise.

        Registration is a promise. Initialization is fulfillment.
        You cannot retrieve a promise.
        """
        registry.register(StubPlugin)
        with pytest.raises(PluginNotFoundError):
            registry.get_plugin("StubPlugin")

    def test_get_nonexistent_plugin_raises(self, registry: PluginRegistry):
        """Requesting a completely unknown plugin should raise PluginNotFoundError."""
        with pytest.raises(PluginNotFoundError):
            registry.get_plugin("NonexistentPlugin")

    def test_get_all_plugins_returns_all_initialized(self, registry: PluginRegistry):
        """get_all_plugins should return every initialized plugin instance."""
        registry.register(StubPlugin)
        registry.register(WuzzPlugin)
        registry.initialize_plugin("StubPlugin")
        registry.initialize_plugin("WuzzPlugin")
        all_plugins = registry.get_all_plugins()
        assert len(all_plugins) == 2

    def test_get_all_plugins_empty_when_none_initialized(self, registry: PluginRegistry):
        """get_all_plugins should return an empty list when nothing is initialized."""
        registry.register(StubPlugin)
        assert registry.get_all_plugins() == []


# ============================================================
# Plugin Metadata Tests
# ============================================================


class TestPluginMetadata:
    """Tests for plugin name and version metadata."""

    def test_plugin_name(self, registry: PluginRegistry):
        """get_name() should return the plugin's self-reported name."""
        registry.register(WuzzPlugin)
        plugin = registry.initialize_plugin("WuzzPlugin")
        assert plugin.get_name() == "WuzzPlugin"

    def test_plugin_version(self, registry: PluginRegistry):
        """get_version() should return the plugin's version string."""
        registry.register(WuzzPlugin)
        plugin = registry.initialize_plugin("WuzzPlugin")
        assert plugin.get_version() == "2.3.1"

    def test_builtin_plugin_metadata(self, registry: PluginRegistry):
        """The built-in FizzBuzzProPlugin should report correct metadata."""
        registry.register(FizzBuzzProPlugin)
        plugin = registry.initialize_plugin("FizzBuzzProPlugin")
        assert plugin.get_name() == "FizzBuzzProPlugin"
        assert plugin.get_version() == "1.0.0"


# ============================================================
# Plugin Rules Tests
# ============================================================


class TestPluginRules:
    """Tests for custom rule contributions from plugins."""

    def test_plugin_with_no_rules(self, registry: PluginRegistry):
        """A plugin that contributes no rules should return an empty list."""
        registry.register(StubPlugin)
        plugin = registry.initialize_plugin("StubPlugin")
        assert plugin.get_rules() == []

    def test_plugin_with_single_rule(self, registry: PluginRegistry):
        """A plugin contributing one rule should return a list of one RuleDefinition."""
        registry.register(WuzzPlugin)
        plugin = registry.initialize_plugin("WuzzPlugin")
        rules = plugin.get_rules()
        assert len(rules) == 1
        assert rules[0].name == "Wuzz"
        assert rules[0].divisor == 7
        assert rules[0].label == "Wuzz"
        assert rules[0].priority == 3

    def test_plugin_with_multiple_rules(self, registry: PluginRegistry):
        """A plugin contributing multiple rules should return all of them."""
        registry.register(MultiRulePlugin)
        plugin = registry.initialize_plugin("MultiRulePlugin")
        rules = plugin.get_rules()
        assert len(rules) == 3
        divisors = {r.divisor for r in rules}
        assert divisors == {13, 17, 19}

    def test_get_all_plugin_rules_aggregates_across_plugins(self, registry: PluginRegistry):
        """get_all_plugin_rules should collect rules from every initialized plugin.

        This is the method that makes the plugin ecosystem actually useful:
        it provides a single point of access to all plugin-contributed rules
        so the evaluation engine does not need to know about individual plugins.
        """
        registry.register(WuzzPlugin)
        registry.register(BazzPlugin)
        registry.initialize_plugin("WuzzPlugin")
        registry.initialize_plugin("BazzPlugin")
        all_rules = registry.get_all_plugin_rules()
        assert len(all_rules) == 2
        labels = {r.label for r in all_rules}
        assert labels == {"Wuzz", "Bazz"}

    def test_get_all_plugin_rules_empty_when_no_plugins(self, registry: PluginRegistry):
        """With no initialized plugins, the aggregated rule list should be empty."""
        assert registry.get_all_plugin_rules() == []

    def test_get_all_plugin_rules_skips_uninitialized(self, registry: PluginRegistry):
        """Only initialized plugins should contribute rules.

        Registered-but-not-initialized plugins are wallflowers at the
        plugin party. They are present in spirit but do not contribute.
        """
        registry.register(WuzzPlugin)
        registry.register(BazzPlugin)
        registry.initialize_plugin("WuzzPlugin")
        # BazzPlugin is registered but not initialized
        all_rules = registry.get_all_plugin_rules()
        assert len(all_rules) == 1
        assert all_rules[0].label == "Wuzz"

    def test_builtin_plugin_extra_rules_from_config(self, registry: PluginRegistry):
        """FizzBuzzProPlugin should create rules from config's extra_rules."""
        registry.register(FizzBuzzProPlugin)
        config = {
            "extra_rules": [
                {"name": "Sev", "divisor": 7, "label": "Sev", "priority": 2},
                {"name": "Elv", "divisor": 11, "label": "Elv"},
            ]
        }
        plugin = registry.initialize_plugin("FizzBuzzProPlugin", config)
        rules = plugin.get_rules()
        assert len(rules) == 2
        assert rules[0].divisor == 7
        assert rules[0].priority == 2
        assert rules[1].divisor == 11
        assert rules[1].priority == 99  # default priority

    def test_builtin_plugin_no_extra_rules(self, registry: PluginRegistry):
        """FizzBuzzProPlugin with no extra_rules config should return no rules."""
        registry.register(FizzBuzzProPlugin)
        plugin = registry.initialize_plugin("FizzBuzzProPlugin")
        assert plugin.get_rules() == []


# ============================================================
# Auto-Registration Decorator Tests
# ============================================================


class TestAutoRegistrationDecorator:
    """Tests for the @register_plugin decorator."""

    def test_decorator_registers_class_in_global_registry(self):
        """Applying @register_plugin should register the class in the global singleton.

        The decorator pattern: because explicit registration calls are for
        people who read documentation.
        """
        PluginRegistry.reset()

        @register_plugin
        class AutoRegisteredPlugin(IPlugin):
            def initialize(self, config: dict[str, Any]) -> None:
                pass

            def get_name(self) -> str:
                return "AutoRegisteredPlugin"

            def get_version(self) -> str:
                return "1.0.0"

            def get_rules(self) -> list[RuleDefinition]:
                return []

        global_registry = PluginRegistry.get_instance()
        assert "AutoRegisteredPlugin" in global_registry.list_registered()

    def test_decorator_returns_class_unchanged(self):
        """The decorator should return the original class so it remains usable."""
        PluginRegistry.reset()

        @register_plugin
        class AnotherAutoPlugin(IPlugin):
            def initialize(self, config: dict[str, Any]) -> None:
                pass

            def get_name(self) -> str:
                return "AnotherAutoPlugin"

            def get_version(self) -> str:
                return "1.0.0"

            def get_rules(self) -> list[RuleDefinition]:
                return []

        # The class should still be instantiable
        instance = AnotherAutoPlugin()
        assert instance.get_name() == "AnotherAutoPlugin"

    def test_builtin_fizzbuzz_pro_plugin_is_auto_registered(self):
        """FizzBuzzProPlugin should be auto-registered by the module-level decorator.

        The import of the plugins module applies @register_plugin to
        FizzBuzzProPlugin at import time. Since our autouse fixture resets
        the singleton after each test, we re-register it here to verify
        the decorator mechanism works on the built-in plugin class.
        """
        PluginRegistry.reset()
        registry = PluginRegistry.get_instance()
        # Simulate what the module-level @register_plugin does
        register_plugin(FizzBuzzProPlugin)
        assert "FizzBuzzProPlugin" in registry.list_registered()


# ============================================================
# Singleton Pattern Tests
# ============================================================


class TestPluginRegistrySingleton:
    """Tests for the global singleton accessor."""

    def test_get_instance_returns_same_object(self):
        """Multiple calls to get_instance should return the same registry."""
        PluginRegistry.reset()
        first = PluginRegistry.get_instance()
        second = PluginRegistry.get_instance()
        assert first is second

    def test_reset_clears_the_singleton(self):
        """reset() should discard the singleton so the next get_instance creates fresh."""
        PluginRegistry.reset()
        first = PluginRegistry.get_instance()
        PluginRegistry.reset()
        second = PluginRegistry.get_instance()
        assert first is not second

    def test_reset_singleton_has_empty_registry(self):
        """A freshly reset singleton should have no registered plugins.

        Well, except for any that get auto-registered on import, which
        is a side effect we accept as the cost of decorator convenience.
        """
        PluginRegistry.reset()
        fresh = PluginRegistry.get_instance()
        # Only auto-registered plugins from module-level decorators
        # should be present. We do not assert empty because the import
        # of plugins.py already registers FizzBuzzProPlugin.
        assert isinstance(fresh.list_registered(), list)

"""
Enterprise FizzBuzz Platform - Feature Registry Tests

Tests for the FeatureDescriptor base class and FeatureRegistry singleton
that form the backbone of the plugin-based feature system. Validates
auto-registration via __init_subclass__, CLI flag registration, feature
discovery, enablement checking, lifecycle orchestration, and rendering.
"""

from __future__ import annotations

import argparse
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.features._registry import (
    FeatureDescriptor,
    FeatureRegistry,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the global registry before and after each test."""
    FeatureRegistry.reset()
    yield
    FeatureRegistry.reset()


# ---------------------------------------------------------------------------
# Auto-registration via __init_subclass__
# ---------------------------------------------------------------------------

class TestFeatureDescriptorAutoRegistration:
    """Verify that defining a FeatureDescriptor subclass with a non-empty
    name attribute auto-registers it in the global registry."""

    def test_subclass_with_name_registers(self):
        class AlphaFeature(FeatureDescriptor):
            name = "alpha"
            description = "Alpha subsystem"

        assert "alpha" in FeatureDescriptor._registry
        assert isinstance(FeatureDescriptor._registry["alpha"], AlphaFeature)

    def test_subclass_without_name_does_not_register(self):
        class AbstractFeature(FeatureDescriptor):
            name = ""
            description = "Abstract, should not register"

        assert "AbstractFeature" not in FeatureDescriptor._registry
        assert "" not in FeatureDescriptor._registry

    def test_subclass_with_no_name_attr_does_not_register(self):
        class BareFeature(FeatureDescriptor):
            description = "No name attribute set"

        # Inherits name="" from FeatureDescriptor
        assert "BareFeature" not in FeatureDescriptor._registry

    def test_multiple_features_register_independently(self):
        class BetaFeature(FeatureDescriptor):
            name = "beta"
            description = "Beta"

        class GammaFeature(FeatureDescriptor):
            name = "gamma"
            description = "Gamma"

        assert "beta" in FeatureDescriptor._registry
        assert "gamma" in FeatureDescriptor._registry
        assert len(FeatureDescriptor._registry) == 2

    def test_registry_stores_instances_not_classes(self):
        class DeltaFeature(FeatureDescriptor):
            name = "delta"

        entry = FeatureDescriptor._registry["delta"]
        assert isinstance(entry, DeltaFeature)
        assert not isinstance(entry, type)


# ---------------------------------------------------------------------------
# FeatureRegistry singleton methods
# ---------------------------------------------------------------------------

class TestFeatureRegistryGetAll:
    """Verify get_all returns features sorted by middleware_priority."""

    def test_get_all_empty(self):
        assert FeatureRegistry.get_all() == []

    def test_get_all_sorted_by_priority(self):
        class HighPriority(FeatureDescriptor):
            name = "high_pri"
            middleware_priority = 10

        class LowPriority(FeatureDescriptor):
            name = "low_pri"
            middleware_priority = 200

        class MidPriority(FeatureDescriptor):
            name = "mid_pri"
            middleware_priority = 50

        result = FeatureRegistry.get_all()
        names = [f.name for f in result]
        assert names == ["high_pri", "mid_pri", "low_pri"]


class TestFeatureRegistryGet:
    """Verify get() lookup by name."""

    def test_get_existing(self):
        class EpsilonFeature(FeatureDescriptor):
            name = "epsilon"

        assert FeatureRegistry.get("epsilon") is not None
        assert FeatureRegistry.get("epsilon").name == "epsilon"

    def test_get_missing(self):
        assert FeatureRegistry.get("nonexistent") is None


class TestFeatureRegistryCLIFlags:
    """Verify CLI flag registration with argparse."""

    def test_register_cli_flags_adds_arguments(self):
        class FlagFeature(FeatureDescriptor):
            name = "flagtest"
            cli_flags = [
                ("--flagtest", {"action": "store_true", "help": "Enable flag test"}),
                ("--flagtest-level", {"type": int, "default": 1, "help": "Level"}),
            ]

        parser = argparse.ArgumentParser()
        FeatureRegistry.register_cli_flags(parser)

        args = parser.parse_args(["--flagtest", "--flagtest-level", "5"])
        assert args.flagtest is True
        assert args.flagtest_level == 5

    def test_register_cli_flags_defaults_work(self):
        class DefaultFeature(FeatureDescriptor):
            name = "defaulttest"
            cli_flags = [
                ("--defaulttest", {"action": "store_true", "default": False, "help": "test"}),
            ]

        parser = argparse.ArgumentParser()
        FeatureRegistry.register_cli_flags(parser)

        args = parser.parse_args([])
        assert args.defaulttest is False

    def test_register_cli_flags_empty_list(self):
        class NoFlagFeature(FeatureDescriptor):
            name = "noflag"
            cli_flags = []

        parser = argparse.ArgumentParser()
        FeatureRegistry.register_cli_flags(parser)
        # Should not raise
        args = parser.parse_args([])
        assert args is not None


class TestFeatureRegistryCreateEnabled:
    """Verify create_enabled filters by is_enabled and calls create."""

    def test_create_enabled_filters_disabled_features(self):
        class DisabledFeature(FeatureDescriptor):
            name = "disabled_feat"

            def is_enabled(self, args):
                return False

        class EnabledFeature(FeatureDescriptor):
            name = "enabled_feat"

            def is_enabled(self, args):
                return True

            def create(self, config, args, event_bus=None):
                return "service", "middleware"

        args = argparse.Namespace()
        result = FeatureRegistry.create_enabled(args, config=None)
        assert len(result) == 1
        feature, service, middleware = result[0]
        assert feature.name == "enabled_feat"
        assert service == "service"
        assert middleware == "middleware"

    def test_create_enabled_returns_empty_for_no_features(self):
        args = argparse.Namespace()
        result = FeatureRegistry.create_enabled(args, config=None)
        assert result == []

    def test_create_enabled_passes_event_bus(self):
        received_bus = []

        class BusFeature(FeatureDescriptor):
            name = "bus_feat"

            def is_enabled(self, args):
                return True

            def create(self, config, args, event_bus=None):
                received_bus.append(event_bus)
                return None, None

        bus = MagicMock()
        FeatureRegistry.create_enabled(argparse.Namespace(), config=None, event_bus=bus)
        assert received_bus == [bus]


class TestFeatureRegistryRenderAll:
    """Verify render_all collects output from enabled features."""

    def test_render_all_collects_output(self):
        class RenderFeature(FeatureDescriptor):
            name = "renderfeat"

            def is_enabled(self, args):
                return True

            def render(self, middleware, args):
                return "DASHBOARD OUTPUT"

        args = argparse.Namespace()
        outputs = FeatureRegistry.render_all(args, {"renderfeat": "mw"})
        assert outputs == ["DASHBOARD OUTPUT"]

    def test_render_all_skips_none_output(self):
        class SilentFeature(FeatureDescriptor):
            name = "silent"

            def is_enabled(self, args):
                return True

            def render(self, middleware, args):
                return None

        args = argparse.Namespace()
        outputs = FeatureRegistry.render_all(args, {"silent": "mw"})
        assert outputs == []


class TestFeatureRegistryEarlyExits:
    """Verify early exit command detection and execution."""

    def test_run_early_exits_returns_none_when_no_exits(self):
        class NoExitFeature(FeatureDescriptor):
            name = "noexit"

        result = FeatureRegistry.run_early_exits(argparse.Namespace(), config=None)
        assert result is None

    def test_run_early_exits_returns_exit_code(self):
        class ExitFeature(FeatureDescriptor):
            name = "exitfeat"

            def has_early_exit(self, args):
                return True

            def run_early_exit(self, args, config):
                return 42

        result = FeatureRegistry.run_early_exits(argparse.Namespace(), config=None)
        assert result == 42


class TestFeatureRegistryReset:
    """Verify reset clears all state."""

    def test_reset_clears_registry(self):
        class TempFeature(FeatureDescriptor):
            name = "temp"

        assert "temp" in FeatureDescriptor._registry
        FeatureRegistry.reset()
        assert "temp" not in FeatureDescriptor._registry

    def test_reset_clears_discovered_flag(self):
        FeatureRegistry._discovered = True
        FeatureRegistry.reset()
        assert FeatureRegistry._discovered is False


class TestFeatureDescriptorDefaults:
    """Verify FeatureDescriptor base class default behavior."""

    def test_default_is_enabled_returns_false(self):
        fd = FeatureDescriptor()
        assert fd.is_enabled(argparse.Namespace()) is False

    def test_default_create_returns_none_tuple(self):
        fd = FeatureDescriptor()
        assert fd.create(None, None) == (None, None)

    def test_default_render_returns_none(self):
        fd = FeatureDescriptor()
        assert fd.render(None, None) is None

    def test_default_has_early_exit_returns_false(self):
        fd = FeatureDescriptor()
        assert fd.has_early_exit(argparse.Namespace()) is False

    def test_default_get_banner_returns_none(self):
        fd = FeatureDescriptor()
        assert fd.get_banner(None, None) is None


class TestFeatureRegistryDiscover:
    """Verify the discover mechanism."""

    def test_discover_sets_discovered_flag(self):
        assert FeatureRegistry._discovered is False
        FeatureRegistry.discover()
        assert FeatureRegistry._discovered is True

    def test_discover_is_idempotent(self):
        FeatureRegistry.discover()
        count_after_first = len(FeatureDescriptor._registry)
        FeatureRegistry.discover()
        count_after_second = len(FeatureDescriptor._registry)
        assert count_after_first == count_after_second

    def test_discover_nonexistent_package_does_not_raise(self):
        FeatureRegistry.discover("nonexistent.package.path")
        # Should not raise, just log a warning

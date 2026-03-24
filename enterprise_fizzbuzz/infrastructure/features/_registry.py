"""
Enterprise FizzBuzz Platform - Feature Registry

Provides the FeatureDescriptor base class and FeatureRegistry singleton for
self-registering feature plugins. Each subsystem declares its CLI flags,
initialization logic, and rendering in a FeatureDescriptor subclass. When
the subclass is defined, it auto-registers via __init_subclass__.

The FeatureRegistry discovers all descriptor modules via importlib, registers
CLI flags with argparse, creates enabled features at runtime, and orchestrates
post-execution rendering. This converts __main__.py from a 12,000-line
monolith into a slim orchestrator that delegates to self-describing plugins.
"""

from __future__ import annotations

import importlib
import logging
import os
import traceback
from typing import Any, Optional

logger = logging.getLogger(__name__)


class FeatureDescriptor:
    """Base class for self-registering feature descriptors.

    Subclasses auto-register via __init_subclass__ when they define a
    non-empty ``name`` class attribute. Each descriptor encapsulates
    everything needed to wire a feature into the platform:

    - CLI flag definitions
    - Enablement check (which flags activate this feature)
    - Service/middleware factory
    - Post-execution rendering (dashboards, reports)
    - Early-exit command handling
    """

    _registry: dict[str, FeatureDescriptor] = {}

    # Subclasses must set these
    name: str = ""
    description: str = ""
    cli_flags: list[tuple[str, dict[str, Any]]] = []
    middleware_priority: int = 100

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "name") and cls.name:
            FeatureDescriptor._registry[cls.name] = cls()

    def is_enabled(self, args: Any) -> bool:
        """Check if this feature is activated by the parsed CLI arguments.

        Override in subclasses to check specific flags.
        """
        return False

    def has_early_exit(self, args: Any) -> bool:
        """Check if this feature has early-exit commands that should run
        before the main evaluation pipeline.

        Override in subclasses that handle early-exit commands.
        """
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        """Execute early-exit commands and return an exit code.

        Only called if has_early_exit() returns True.
        """
        return 0

    def create(
        self,
        config: Any,
        args: Any,
        event_bus: Any = None,
    ) -> tuple[Any, Any]:
        """Factory: create and return (service, middleware) tuple.

        The service is the subsystem's primary object (e.g., a CacheStore,
        a BlockchainObserver). The middleware is the pipeline middleware
        instance, or None if the feature doesn't inject middleware.

        Override in subclasses.
        """
        return None, None

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        """Return a banner string to print when the feature is enabled.

        Return None to suppress banner output.
        """
        return None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        """Post-execution rendering (dashboards, reports).

        Called after the main evaluation pipeline completes. Return a
        string to print, or None for no output.
        """
        return None


class FeatureRegistry:
    """Singleton registry that manages feature discovery, CLI flag
    registration, and lifecycle orchestration for all feature descriptors.
    """

    _discovered = False

    @classmethod
    def discover(cls, package_path: str = "enterprise_fizzbuzz.infrastructure.features"):
        """Auto-import all feature descriptor modules to trigger registration.

        Scans the features package directory for .py files that don't start
        with an underscore, and imports each one. The act of importing triggers
        __init_subclass__ on any FeatureDescriptor subclasses defined in the
        module, which registers them in the global _registry.
        """
        if cls._discovered:
            return

        # Find the directory of the features package
        try:
            pkg = importlib.import_module(package_path)
        except ImportError:
            logger.warning("Could not import features package: %s", package_path)
            return

        pkg_dir = os.path.dirname(os.path.abspath(pkg.__file__))

        for fname in sorted(os.listdir(pkg_dir)):
            if fname.endswith(".py") and not fname.startswith("_"):
                module_name = f"{package_path}.{fname[:-3]}"
                try:
                    importlib.import_module(module_name)
                except Exception:
                    logger.error(
                        "Failed to import feature module %s:\n%s",
                        module_name,
                        traceback.format_exc(),
                    )

        cls._discovered = True

    @classmethod
    def get_all(cls) -> list[FeatureDescriptor]:
        """Return all registered feature descriptors, sorted by middleware priority."""
        return sorted(
            FeatureDescriptor._registry.values(),
            key=lambda f: f.middleware_priority,
        )

    @classmethod
    def get(cls, name: str) -> Optional[FeatureDescriptor]:
        """Look up a feature descriptor by name."""
        return FeatureDescriptor._registry.get(name)

    @classmethod
    def register_cli_flags(cls, parser):
        """Register all features' CLI flags with the argparse parser.

        Each feature descriptor declares its CLI flags as a list of
        (flag_name, flag_kwargs) tuples. This method iterates over all
        registered features and adds each flag to the parser.
        """
        for feature in cls.get_all():
            for flag_spec in feature.cli_flags:
                if isinstance(flag_spec, tuple) and len(flag_spec) == 2:
                    flag_name, flag_kwargs = flag_spec
                    try:
                        parser.add_argument(flag_name, **flag_kwargs)
                    except Exception:
                        logger.error(
                            "Failed to register CLI flag %s for feature %s:\n%s",
                            flag_name,
                            feature.name,
                            traceback.format_exc(),
                        )

    @classmethod
    def run_early_exits(cls, args, config) -> Optional[int]:
        """Check all features for early-exit commands and run the first match.

        Returns an exit code if an early-exit command was executed, or None
        if no early exits were triggered.
        """
        for feature in cls.get_all():
            if feature.has_early_exit(args):
                return feature.run_early_exit(args, config)
        return None

    @classmethod
    def create_enabled(
        cls,
        args: Any,
        config: Any,
        event_bus: Any = None,
    ) -> list[tuple[FeatureDescriptor, Any, Any]]:
        """Create all enabled features and return (feature, service, middleware) tuples.

        Iterates over all registered features, checks if each is enabled
        via its is_enabled() method, and calls create() for enabled ones.
        Also prints banners for each enabled feature.
        """
        enabled = []
        for feature in cls.get_all():
            if feature.is_enabled(args):
                try:
                    banner = feature.get_banner(config, args)
                    if banner:
                        print(banner)
                    service, middleware = feature.create(config, args, event_bus)
                    enabled.append((feature, service, middleware))
                except Exception:
                    logger.error(
                        "Failed to create feature %s:\n%s",
                        feature.name,
                        traceback.format_exc(),
                    )
        return enabled

    @classmethod
    def render_all(
        cls,
        args: Any,
        middlewares: dict[str, Any],
    ) -> list[str]:
        """Run post-execution rendering for all enabled features.

        Returns a list of rendered output strings (non-None results).
        """
        outputs = []
        for feature in cls.get_all():
            mw = middlewares.get(feature.name)
            if mw is not None or feature.is_enabled(args):
                try:
                    output = feature.render(mw, args)
                    if output:
                        outputs.append(output)
                except Exception:
                    logger.error(
                        "Failed to render feature %s:\n%s",
                        feature.name,
                        traceback.format_exc(),
                    )
        return outputs

    @classmethod
    def reset(cls):
        """Reset the registry state. Used for testing."""
        FeatureDescriptor._registry.clear()
        cls._discovered = False

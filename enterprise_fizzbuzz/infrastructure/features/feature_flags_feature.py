"""Feature descriptor for the Feature Flag / Progressive Rollout subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FeatureFlagsFeature(FeatureDescriptor):
    name = "feature_flags"
    description = "Feature Flag progressive rollout with CLI overrides and flag listing"
    middleware_priority = 91
    cli_flags = [
        ("--feature-flags", {"action": "store_true",
                             "help": "Enable the Feature Flag / Progressive Rollout subsystem"}),
        ("--flag", {"action": "append", "metavar": "NAME=VALUE", "default": [],
                    "help": "Override a feature flag (e.g. --flag wuzz_rule_experimental=true)"}),
        ("--list-flags", {"action": "store_true",
                          "help": "Display all registered feature flags and exit"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "feature_flags", False)

    def has_early_exit(self, args: Any) -> bool:
        return getattr(args, "list_flags", False) and getattr(args, "feature_flags", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.feature_flags import (
            FlagMiddleware,
            apply_cli_overrides,
            create_flag_store_from_config,
        )

        flag_store = create_flag_store_from_config(config)

        if getattr(args, "flag", None):
            apply_cli_overrides(flag_store, args.flag)

        flag_middleware = FlagMiddleware(
            flag_store=flag_store,
            event_bus=event_bus,
        )

        return flag_store, flag_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FEATURE FLAGS: Progressive Rollout ENABLED              |\n"
            "  | Flags are now controlling which rules are active.       |\n"
            "  | The FizzBuzz rules you know and love are now subject    |\n"
            "  | to the whims of a configuration-driven toggle system.   |\n"
            "  +---------------------------------------------------------+"
        )

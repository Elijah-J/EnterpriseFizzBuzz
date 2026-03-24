"""Feature descriptor for the FizzLambda serverless function runtime."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzLambdaFeature(FeatureDescriptor):
    name = "fizzlambda"
    description = "Serverless function runtime with auto-scaling, warm pools, event triggers, and scale-to-zero"
    middleware_priority = 118
    cli_flags = [
        ("--fizzlambda", {"action": "store_true", "default": False,
                          "help": "Enable FizzLambda serverless function runtime"}),
        ("--fizzlambda-mode", {"type": str,
                               "choices": ["container", "serverless", "hybrid"],
                               "default": None,
                               "help": "Evaluation routing: container, serverless, hybrid"}),
        ("--fizzlambda-create", {"type": str, "default": "",
                                 "help": "Create a new function (name)"}),
        ("--fizzlambda-update", {"type": str, "default": "",
                                 "help": "Update function configuration (name)"}),
        ("--fizzlambda-delete", {"type": str, "default": "",
                                 "help": "Delete a function and all versions (name)"}),
        ("--fizzlambda-publish", {"type": str, "default": "",
                                  "help": "Publish a new version of a function (name)"}),
        ("--fizzlambda-list", {"action": "store_true", "default": False,
                               "help": "List all functions with versions and triggers"}),
        ("--fizzlambda-invoke", {"type": str, "default": "",
                                 "help": "Synchronously invoke a function (name)"}),
        ("--fizzlambda-invoke-async", {"type": str, "default": "",
                                       "help": "Asynchronously invoke a function (name)"}),
        ("--fizzlambda-logs", {"type": str, "default": "",
                               "help": "Stream invocation logs for a function (name)"}),
        ("--fizzlambda-metrics", {"type": str, "default": "",
                                  "help": "Display invocation metrics for a function (name)"}),
        ("--fizzlambda-alias-create", {"type": str, "default": "",
                                       "help": "Create alias: function:alias:version"}),
        ("--fizzlambda-alias-update", {"type": str, "default": "",
                                       "help": "Update alias routing: function:alias:version[:weight]"}),
        ("--fizzlambda-alias-list", {"type": str, "default": "",
                                     "help": "List aliases for a function (name)"}),
        ("--fizzlambda-trigger-create", {"type": str, "default": "",
                                         "help": "Create trigger: function:type:config_json"}),
        ("--fizzlambda-trigger-list", {"type": str, "default": "",
                                       "help": "List triggers for a function (name)"}),
        ("--fizzlambda-trigger-enable", {"type": str, "default": "",
                                         "help": "Enable a trigger (trigger_id)"}),
        ("--fizzlambda-trigger-disable", {"type": str, "default": "",
                                          "help": "Disable a trigger (trigger_id)"}),
        ("--fizzlambda-layer-create", {"type": str, "default": "",
                                       "help": "Create a new layer (name)"}),
        ("--fizzlambda-layer-list", {"action": "store_true", "default": False,
                                     "help": "List all layers with versions and runtimes"}),
        ("--fizzlambda-layer-publish", {"type": str, "default": "",
                                        "help": "Publish a new layer version (name)"}),
        ("--fizzlambda-queue-list", {"action": "store_true", "default": False,
                                     "help": "List all queues with message counts"}),
        ("--fizzlambda-queue-receive", {"type": str, "default": "",
                                        "help": "Receive messages from a queue (name)"}),
        ("--fizzlambda-queue-replay", {"type": str, "default": "",
                                       "help": "Replay a DLQ message: queue:message_id"}),
        ("--fizzlambda-queue-purge", {"type": str, "default": "",
                                      "help": "Purge all messages from a queue (name)"}),
        ("--fizzlambda-warm-pool", {"action": "store_true", "default": False,
                                    "help": "Display warm pool status"}),
        ("--fizzlambda-concurrency", {"action": "store_true", "default": False,
                                      "help": "Display concurrency utilization"}),
        ("--fizzlambda-cold-starts", {"action": "store_true", "default": False,
                                      "help": "Display cold start metrics"}),
        ("--fizzlambda-emergency-deploy", {"action": "store_true", "default": False,
                                           "help": "Bypass cognitive load gating for emergency deployments"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzlambda", False),
            getattr(args, "fizzlambda_list", False),
            getattr(args, "fizzlambda_warm_pool", False),
            getattr(args, "fizzlambda_concurrency", False),
            getattr(args, "fizzlambda_cold_starts", False),
            getattr(args, "fizzlambda_layer_list", False),
            getattr(args, "fizzlambda_queue_list", False),
            bool(getattr(args, "fizzlambda_create", "")),
            bool(getattr(args, "fizzlambda_update", "")),
            bool(getattr(args, "fizzlambda_delete", "")),
            bool(getattr(args, "fizzlambda_publish", "")),
            bool(getattr(args, "fizzlambda_invoke", "")),
            bool(getattr(args, "fizzlambda_invoke_async", "")),
            bool(getattr(args, "fizzlambda_logs", "")),
            bool(getattr(args, "fizzlambda_metrics", "")),
            bool(getattr(args, "fizzlambda_alias_create", "")),
            bool(getattr(args, "fizzlambda_alias_update", "")),
            bool(getattr(args, "fizzlambda_alias_list", "")),
            bool(getattr(args, "fizzlambda_trigger_create", "")),
            bool(getattr(args, "fizzlambda_trigger_list", "")),
            bool(getattr(args, "fizzlambda_trigger_enable", "")),
            bool(getattr(args, "fizzlambda_trigger_disable", "")),
            bool(getattr(args, "fizzlambda_layer_create", "")),
            bool(getattr(args, "fizzlambda_layer_publish", "")),
            bool(getattr(args, "fizzlambda_queue_receive", "")),
            bool(getattr(args, "fizzlambda_queue_replay", "")),
            bool(getattr(args, "fizzlambda_queue_purge", "")),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzlambda import (
            create_fizzlambda_subsystem,
        )

        mode = getattr(args, "fizzlambda_mode", None) or config.fizzlambda_mode
        runtime, dashboard, middleware = create_fizzlambda_subsystem(
            max_total_environments=config.fizzlambda_max_total_environments,
            max_per_function=config.fizzlambda_max_environments_per_function,
            idle_timeout=config.fizzlambda_idle_timeout,
            max_burst=config.fizzlambda_max_burst_concurrency,
            account_limit=config.fizzlambda_account_concurrency_limit,
            snapshot_enabled=config.fizzlambda_snapshot_enabled,
            predictive_enabled=config.fizzlambda_predictive_prewarming,
            layer_cache_size_mb=config.fizzlambda_layer_cache_size_mb,
            mode=mode,
            dashboard_width=config.fizzlambda_dashboard_width,
            event_bus=event_bus,
        )

        return runtime, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzlambda_list", False):
            parts.append(middleware.render_functions())
        if getattr(args, "fizzlambda_warm_pool", False):
            parts.append(middleware.render_warm_pool())
        if getattr(args, "fizzlambda_concurrency", False):
            parts.append(middleware.render_concurrency())
        if getattr(args, "fizzlambda_cold_starts", False):
            parts.append(middleware.render_cold_starts())
        if getattr(args, "fizzlambda_layer_list", False):
            parts.append(middleware.render_layers())
        if getattr(args, "fizzlambda_queue_list", False):
            parts.append(middleware.render_queues())
        fn = getattr(args, "fizzlambda_metrics", "")
        if fn:
            parts.append(middleware.render_metrics(fn))
        fn = getattr(args, "fizzlambda_logs", "")
        if fn:
            parts.append(middleware.render_logs(fn))
        fn = getattr(args, "fizzlambda_alias_list", "")
        if fn:
            parts.append(middleware.render_aliases(fn))
        fn = getattr(args, "fizzlambda_trigger_list", "")
        if fn:
            parts.append(middleware.render_triggers(fn))
        if getattr(args, "fizzlambda", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

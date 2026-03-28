"""Feature descriptor for the FizzBlock block storage & volume manager."""

from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzBlockFeature(FeatureDescriptor):
    name = "fizzblock"
    description = "Block storage with volume manager, RAID, thin provisioning, encryption, and QoS"
    middleware_priority = 128
    cli_flags = [
        ("--fizzblock", {"action": "store_true", "default": False,
                         "help": "Enable FizzBlock: block storage & volume manager"}),
        ("--fizzblock-create", {"type": str, "default": None,
                                "help": "Create a logical volume (format: vg/name:size)"}),
        ("--fizzblock-delete", {"type": str, "default": None,
                                "help": "Delete a logical volume by name"}),
        ("--fizzblock-list", {"action": "store_true", "default": False,
                              "help": "List all volumes and volume groups"}),
        ("--fizzblock-snapshot", {"type": str, "default": None,
                                  "help": "Create a COW snapshot of a volume"}),
        ("--fizzblock-raid", {"type": str, "default": None,
                              "help": "Create a RAID array (format: level:dev1,dev2,...)"}),
        ("--fizzblock-encrypt", {"action": "store_true", "default": False,
                                 "help": "Enable AES-256-XTS block encryption"}),
        ("--fizzblock-dedup", {"action": "store_true", "default": False,
                               "help": "Enable SHA-256 block deduplication"}),
        ("--fizzblock-compress", {"type": str, "default": "none",
                                  "help": "Compression algorithm: none, lz4, zstd"}),
        ("--fizzblock-scheduler", {"type": str, "default": "deadline",
                                   "help": "I/O scheduler: fifo, deadline, cfq"}),
        ("--fizzblock-qos", {"type": str, "default": None,
                             "help": "QoS limits (format: iops:bandwidth_mbps)"}),
        ("--fizzblock-stats", {"action": "store_true", "default": False,
                               "help": "Display block storage statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzblock", False),
            getattr(args, "fizzblock_create", None),
            getattr(args, "fizzblock_list", False),
            getattr(args, "fizzblock_snapshot", None),
            getattr(args, "fizzblock_raid", None),
            getattr(args, "fizzblock_stats", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzblock import (
            FizzBlockMiddleware, create_fizzblock_subsystem,
        )
        engine, dashboard, middleware = create_fizzblock_subsystem(
            sector_size=config.fizzblock_sector_size,
            scheduler=config.fizzblock_scheduler,
            dashboard_width=config.fizzblock_dashboard_width,
        )
        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzblock_list", False):
            parts.append(middleware.render_volumes())
        if getattr(args, "fizzblock_stats", False):
            parts.append(middleware.render_stats())
        if getattr(args, "fizzblock", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None

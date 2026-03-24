"""Feature descriptor for the FizzS3 object storage subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzS3Feature(FeatureDescriptor):
    name = "fizzs3"
    description = "S3-compatible object storage with erasure coding, deduplication, versioning, and lifecycle management"
    middleware_priority = 118
    cli_flags = [
        ("--fizzs3", {"action": "store_true",
                      "help": "Enable FizzS3: S3-compatible object storage with erasure coding and deduplication"}),
        ("--fizzs3-list-buckets", {"action": "store_true",
                                    "help": "List all FizzS3 buckets"}),
        ("--fizzs3-create-bucket", {"type": str, "default": None, "metavar": "NAME",
                                     "help": "Create a new bucket"}),
        ("--fizzs3-delete-bucket", {"type": str, "default": None, "metavar": "NAME",
                                     "help": "Delete an empty bucket"}),
        ("--fizzs3-put", {"nargs": 3, "default": None, "metavar": ("BUCKET", "KEY", "FILE"),
                           "help": "Upload a file as an object"}),
        ("--fizzs3-get", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                           "help": "Retrieve an object"}),
        ("--fizzs3-head", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                            "help": "Retrieve object metadata"}),
        ("--fizzs3-delete", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                              "help": "Delete an object"}),
        ("--fizzs3-list", {"type": str, "default": None, "metavar": "BUCKET",
                            "help": "List objects in a bucket"}),
        ("--fizzs3-list-versions", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                                     "help": "List all versions of an object"}),
        ("--fizzs3-presign", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                               "help": "Generate a presigned URL"}),
        ("--fizzs3-presign-expires", {"type": int, "default": 3600, "metavar": "SECONDS",
                                       "help": "Presigned URL validity duration (default: 3600)"}),
        ("--fizzs3-multipart-create", {"nargs": 2, "default": None, "metavar": ("BUCKET", "KEY"),
                                        "help": "Initiate a multipart upload"}),
        ("--fizzs3-multipart-complete", {"nargs": 3, "default": None, "metavar": ("BUCKET", "KEY", "UPLOAD_ID"),
                                          "help": "Complete a multipart upload"}),
        ("--fizzs3-multipart-abort", {"nargs": 3, "default": None, "metavar": ("BUCKET", "KEY", "UPLOAD_ID"),
                                       "help": "Abort a multipart upload"}),
        ("--fizzs3-multipart-list", {"type": str, "default": None, "metavar": "BUCKET",
                                      "help": "List in-progress multipart uploads"}),
        ("--fizzs3-storage-class", {"type": str, "default": "STANDARD",
                                     "choices": ["STANDARD", "STANDARD_IA", "ARCHIVE", "DEEP_ARCHIVE"],
                                     "help": "Storage class for PUT operations"}),
        ("--fizzs3-versioning", {"nargs": 2, "default": None, "metavar": ("BUCKET", "ACTION"),
                                  "help": "Enable or suspend versioning (enable|suspend)"}),
        ("--fizzs3-encryption", {"nargs": 2, "default": None, "metavar": ("BUCKET", "MODE"),
                                  "help": "Set default encryption (sse-s3, sse-kms, sse-c)"}),
        ("--fizzs3-dedup-stats", {"type": str, "default": None, "metavar": "BUCKET",
                                   "help": "Show deduplication statistics"}),
        ("--fizzs3-scrub", {"type": str, "default": None, "metavar": "BUCKET",
                             "help": "Run erasure coding integrity scrub"}),
        ("--fizzs3-metrics", {"action": "store_true",
                               "help": "Show storage metrics summary"}),
        ("--fizzs3-prefix", {"type": str, "default": None, "metavar": "PREFIX",
                              "help": "Prefix filter for list operations"}),
        ("--fizzs3-delimiter", {"type": str, "default": None, "metavar": "DELIMITER",
                                 "help": "Delimiter for hierarchy simulation (default: /)"}),
        ("--fizzs3-region", {"type": str, "default": None, "metavar": "REGION",
                              "help": "Region for bucket operations (default: fizz-east-1)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzs3", False),
            getattr(args, "fizzs3_list_buckets", False),
            getattr(args, "fizzs3_create_bucket", None) is not None,
            getattr(args, "fizzs3_delete_bucket", None) is not None,
            getattr(args, "fizzs3_put", None) is not None,
            getattr(args, "fizzs3_get", None) is not None,
            getattr(args, "fizzs3_head", None) is not None,
            getattr(args, "fizzs3_delete", None) is not None,
            getattr(args, "fizzs3_list", None) is not None,
            getattr(args, "fizzs3_list_versions", None) is not None,
            getattr(args, "fizzs3_presign", None) is not None,
            getattr(args, "fizzs3_dedup_stats", None) is not None,
            getattr(args, "fizzs3_scrub", None) is not None,
            getattr(args, "fizzs3_metrics", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzs3 import (
            FizzS3Middleware,
            create_fizzs3_subsystem,
        )

        service, middleware = create_fizzs3_subsystem(
            default_region=config.fizzs3_default_region,
            max_buckets=config.fizzs3_max_buckets,
            default_encryption=config.fizzs3_default_encryption,
            chunk_size=config.fizzs3_chunk_size,
            gc_interval=config.fizzs3_gc_interval,
            gc_safety_delay=config.fizzs3_gc_safety_delay,
            lifecycle_interval=config.fizzs3_lifecycle_interval,
            compaction_threshold=config.fizzs3_compaction_threshold,
            segment_max_size=config.fizzs3_segment_max_size,
            presign_default_expiry=config.fizzs3_presign_default_expiry,
            dashboard_width=config.fizzs3_dashboard_width,
            event_bus=event_bus,
        )

        return service, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzs3_list_buckets", False):
            parts.append(middleware.render_buckets())
        if getattr(args, "fizzs3_dedup_stats", None):
            parts.append(middleware.render_dedup(args.fizzs3_dedup_stats))
        if getattr(args, "fizzs3_metrics", False):
            parts.append(middleware.render_metrics())
        if getattr(args, "fizzs3_scrub", None):
            parts.append(middleware.render_scrub(args.fizzs3_scrub))
        if getattr(args, "fizzs3", False) and not parts:
            parts.append(middleware.render_overview())
        return "\n".join(parts) if parts else None

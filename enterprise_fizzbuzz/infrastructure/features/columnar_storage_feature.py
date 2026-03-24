"""Feature descriptor for FizzColumn columnar storage engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ColumnarStorageFeature(FeatureDescriptor):
    name = "columnar_storage"
    description = "Parquet-style columnar storage with dictionary, RLE, and delta encoding"
    middleware_priority = 870
    cli_flags = [
        ("--columnar", {"action": "store_true",
                        "help": "Enable FizzColumn: Parquet-style columnar storage with dictionary, RLE, and delta encoding"}),
        ("--columnar-export", {"type": str, "metavar": "PATH", "default": None,
                               "help": "Export columnar data to a Parquet-style binary file at the specified path"}),
        ("--columnar-dashboard", {"action": "store_true",
                                  "help": "Display the FizzColumn ASCII dashboard with column inventory, compression ratios, and zone maps"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "columnar", False),
            getattr(args, "columnar_export", None) is not None,
            getattr(args, "columnar_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.columnar_storage import (
            ColumnMiddleware,
            ColumnStore,
        )

        store = ColumnStore(
            row_group_size=config.columnar_row_group_size,
            encoding_sample_size=config.columnar_encoding_sample_size,
            dictionary_cardinality_limit=config.columnar_dictionary_cardinality_limit,
        )
        middleware = ColumnMiddleware(store)

        return store, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.columnar_storage import (
            ColumnDashboard,
            ParquetExporter,
        )
        store = middleware._store
        parts = []

        store.flush()

        if getattr(args, "columnar_export", None):
            try:
                bytes_written = ParquetExporter.export(store, args.columnar_export)
                parts.append(
                    f"\n  FizzColumn: Exported {store.total_rows} rows to "
                    f"{args.columnar_export} ({bytes_written} bytes)"
                )
            except Exception as e:
                parts.append(f"\n  FizzColumn export error: {e}")

        if getattr(args, "columnar_dashboard", False):
            parts.append(ColumnDashboard.render(
                store=store,
                width=60,
            ))

        return "\n".join(parts) if parts else None

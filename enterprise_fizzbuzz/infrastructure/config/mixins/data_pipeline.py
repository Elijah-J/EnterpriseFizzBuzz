"""Data Pipeline & ETL Framework properties"""

from __future__ import annotations

from typing import Any


class DataPipelineConfigMixin:
    """Configuration properties for the data pipeline subsystem."""

    # ----------------------------------------------------------------
    # Data Pipeline & ETL Framework properties
    # ----------------------------------------------------------------

    @property
    def data_pipeline_enabled(self) -> bool:
        """Whether the Data Pipeline & ETL Framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enabled", False)

    @property
    def data_pipeline_source(self) -> str:
        """Source connector type: 'range' or 'devnull'."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("source", "range")

    @property
    def data_pipeline_sink(self) -> str:
        """Sink connector type: 'stdout' or 'devnull'."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("sink", "stdout")

    @property
    def data_pipeline_batch_size(self) -> int:
        """Records per batch in the pipeline."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("batch_size", 10)

    @property
    def data_pipeline_max_retries(self) -> int:
        """Maximum retry attempts per stage on failure."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("max_retries", 3)

    @property
    def data_pipeline_retry_backoff_ms(self) -> int:
        """Base backoff between retries in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("retry_backoff_ms", 100)

    @property
    def data_pipeline_enable_checkpoints(self) -> bool:
        """Whether to save pipeline state after each stage."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enable_checkpoints", True)

    @property
    def data_pipeline_enable_lineage(self) -> bool:
        """Whether to track full data provenance chain per record."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enable_lineage", True)

    @property
    def data_pipeline_enable_backfill(self) -> bool:
        """Whether to allow retroactive enrichment of processed records."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enable_backfill", False)

    @property
    def data_pipeline_enrichments(self) -> dict[str, bool]:
        """Which enrichments are enabled: fibonacci, primality, roman_numerals, emotional_valence."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("enrichments", {
            "fibonacci": True,
            "primality": True,
            "roman_numerals": True,
            "emotional_valence": True,
        })

    @property
    def data_pipeline_dag_width(self) -> int:
        """ASCII DAG visualization width."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("dag", {}).get("visualization_width", 60)

    @property
    def data_pipeline_dashboard_width(self) -> int:
        """ASCII dashboard width for the data pipeline dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("data_pipeline", {}).get("dashboard", {}).get("width", 60)


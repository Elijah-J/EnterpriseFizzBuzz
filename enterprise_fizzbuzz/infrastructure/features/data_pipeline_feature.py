"""Feature descriptor for the Data Pipeline & ETL Framework."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class DataPipelineFeature(FeatureDescriptor):
    name = "data_pipeline"
    description = "5-stage ETL pipeline DAG with source/sink connectors, lineage tracking, and backfill"
    middleware_priority = 120
    cli_flags = [
        ("--pipeline", {"action": "store_true", "default": False,
                        "help": "Enable the Data Pipeline & ETL Framework: route FizzBuzz through a 5-stage DAG"}),
        ("--pipeline-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the Data Pipeline ASCII dashboard after execution"}),
        ("--pipeline-dag", {"action": "store_true", "default": False,
                            "help": "Display the pipeline DAG visualization (a very straight line)"}),
        ("--pipeline-lineage", {"action": "store_true", "default": False,
                                "help": "Display data lineage provenance chains for all processed records"}),
        ("--backfill", {"action": "store_true", "default": False,
                        "help": "Enable retroactive backfill enrichment of pipeline records"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "pipeline", False),
            getattr(args, "pipeline_dashboard", False),
            getattr(args, "pipeline_dag", False),
            getattr(args, "pipeline_lineage", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.data_pipeline import (
            PipelineBuilder,
            PipelineMiddleware,
            SinkConnectorFactory,
            SourceConnectorFactory,
        )

        source = SourceConnectorFactory.create(config.data_pipeline_source)
        sink = SinkConnectorFactory.create(config.data_pipeline_sink)

        enrichments = config.data_pipeline_enrichments
        pipeline_builder = (
            PipelineBuilder()
            .with_source(source)
            .with_sink(sink)
            .with_rules(config.rules)
            .with_enrichments(enrichments)
            .with_max_retries(config.data_pipeline_max_retries)
            .with_retry_backoff_ms(config.data_pipeline_retry_backoff_ms)
            .with_checkpoints(config.data_pipeline_enable_checkpoints)
            .with_lineage(config.data_pipeline_enable_lineage)
            .with_backfill(getattr(args, "backfill", False) or config.data_pipeline_enable_backfill)
            .with_event_bus(event_bus)
        )
        pipeline = pipeline_builder.build()

        pipeline_middleware = PipelineMiddleware(
            pipeline=pipeline,
            event_bus=event_bus,
        )

        return pipeline, pipeline_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.data_pipeline import PipelineDashboard

        parts = []
        pipeline = middleware.pipeline if hasattr(middleware, "pipeline") else None
        if pipeline is None:
            return None

        if getattr(args, "pipeline_dashboard", False):
            parts.append(PipelineDashboard.render(
                executor=pipeline.executor,
                dag=pipeline.dag,
                records=getattr(pipeline, "_last_records", []),
                lineage_tracker=pipeline.lineage_tracker,
                backfill_engine=pipeline.backfill_engine,
                width=80,
            ))

        if getattr(args, "pipeline_dag", False):
            parts.append(pipeline.dag.render(60))

        if getattr(args, "pipeline_lineage", False) and pipeline.lineage_tracker is not None:
            parts.append(PipelineDashboard.render_lineage(
                lineage_tracker=pipeline.lineage_tracker,
                records=getattr(pipeline, "_last_records", []),
                width=60,
            ))

        return "\n".join(parts) if parts else None

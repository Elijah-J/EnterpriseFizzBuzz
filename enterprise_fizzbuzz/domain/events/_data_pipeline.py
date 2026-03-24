"""Data Pipeline and ETL Framework events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("PIPELINE_STARTED")
EventType.register("PIPELINE_COMPLETED")
EventType.register("PIPELINE_STAGE_ENTERED")
EventType.register("PIPELINE_STAGE_COMPLETED")
EventType.register("PIPELINE_RECORD_EXTRACTED")
EventType.register("PIPELINE_RECORD_VALIDATED")
EventType.register("PIPELINE_RECORD_TRANSFORMED")
EventType.register("PIPELINE_RECORD_ENRICHED")
EventType.register("PIPELINE_RECORD_LOADED")
EventType.register("PIPELINE_DAG_RESOLVED")
EventType.register("PIPELINE_CHECKPOINT_SAVED")
EventType.register("PIPELINE_BACKFILL_STARTED")
EventType.register("PIPELINE_BACKFILL_COMPLETED")
EventType.register("PIPELINE_DASHBOARD_RENDERED")

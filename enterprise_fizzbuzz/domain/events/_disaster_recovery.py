"""Disaster Recovery and Backup/Restore events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("DR_WAL_ENTRY_APPENDED")
EventType.register("DR_WAL_CHECKSUM_VERIFIED")
EventType.register("DR_WAL_CHECKSUM_FAILED")
EventType.register("DR_SNAPSHOT_CREATED")
EventType.register("DR_SNAPSHOT_RESTORED")
EventType.register("DR_SNAPSHOT_CORRUPTED")
EventType.register("DR_BACKUP_CREATED")
EventType.register("DR_BACKUP_DELETED")
EventType.register("DR_BACKUP_VAULT_FULL")
EventType.register("DR_PITR_STARTED")
EventType.register("DR_PITR_COMPLETED")
EventType.register("DR_PITR_FAILED")
EventType.register("DR_RETENTION_POLICY_APPLIED")
EventType.register("DR_DRILL_STARTED")
EventType.register("DR_DRILL_COMPLETED")
EventType.register("DR_DRILL_FAILED")
EventType.register("DR_DASHBOARD_RENDERED")

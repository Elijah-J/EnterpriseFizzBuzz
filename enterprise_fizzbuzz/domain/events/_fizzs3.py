"""FizzS3 object storage events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

# Bucket lifecycle
EventType.register("S3_BUCKET_CREATED")
EventType.register("S3_BUCKET_DELETED")
EventType.register("S3_BUCKET_VERSIONING_CHANGED")

# Object lifecycle
EventType.register("S3_OBJECT_CREATED_PUT")
EventType.register("S3_OBJECT_CREATED_COPY")
EventType.register("S3_OBJECT_CREATED_MPU")
EventType.register("S3_OBJECT_DELETED")
EventType.register("S3_OBJECT_DELETE_MARKER_CREATED")

# Storage class transitions
EventType.register("S3_OBJECT_TRANSITIONED")
EventType.register("S3_OBJECT_RESTORE_INITIATED")
EventType.register("S3_OBJECT_RESTORE_COMPLETED")
EventType.register("S3_OBJECT_RESTORE_EXPIRED")

# Replication
EventType.register("S3_REPLICATION_COMPLETED")
EventType.register("S3_REPLICATION_FAILED")

# Lifecycle
EventType.register("S3_LIFECYCLE_EXPIRATION")
EventType.register("S3_LIFECYCLE_TRANSITION")

# Maintenance
EventType.register("S3_GC_COMPLETED")
EventType.register("S3_SCRUB_COMPLETED")
EventType.register("S3_COMPACTION_COMPLETED")
EventType.register("S3_KEY_ROTATION_COMPLETED")

# Middleware
EventType.register("S3_EVALUATION_STORED")
EventType.register("S3_DASHBOARD_RENDERED")

"""FizzLambda serverless function runtime events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

# Function lifecycle
EventType.register("LAM_FUNCTION_CREATED")
EventType.register("LAM_FUNCTION_UPDATED")
EventType.register("LAM_FUNCTION_DELETED")
EventType.register("LAM_VERSION_PUBLISHED")
EventType.register("LAM_VERSION_GARBAGE_COLLECTED")

# Alias lifecycle
EventType.register("LAM_ALIAS_CREATED")
EventType.register("LAM_ALIAS_UPDATED")
EventType.register("LAM_ALIAS_DELETED")
EventType.register("LAM_TRAFFIC_SHIFT_STARTED")
EventType.register("LAM_TRAFFIC_SHIFT_COMPLETED")
EventType.register("LAM_TRAFFIC_SHIFT_ROLLED_BACK")

# Invocation lifecycle
EventType.register("LAM_INVOCATION_STARTED")
EventType.register("LAM_INVOCATION_COMPLETED")
EventType.register("LAM_INVOCATION_FAILED")
EventType.register("LAM_INVOCATION_THROTTLED")
EventType.register("LAM_INVOCATION_TIMED_OUT")
EventType.register("LAM_INVOCATION_OOM_KILLED")

# Execution environment lifecycle
EventType.register("LAM_ENVIRONMENT_CREATING")
EventType.register("LAM_ENVIRONMENT_READY")
EventType.register("LAM_ENVIRONMENT_BUSY")
EventType.register("LAM_ENVIRONMENT_FROZEN")
EventType.register("LAM_ENVIRONMENT_DESTROYING")
EventType.register("LAM_ENVIRONMENT_DESTROYED")
EventType.register("LAM_ENVIRONMENT_RECYCLED")

# Warm pool events
EventType.register("LAM_WARM_POOL_HIT")
EventType.register("LAM_WARM_POOL_MISS")
EventType.register("LAM_WARM_POOL_EVICTION")
EventType.register("LAM_WARM_POOL_PROVISIONED")

# Cold start events
EventType.register("LAM_COLD_START_INITIATED")
EventType.register("LAM_COLD_START_COMPLETED")
EventType.register("LAM_SNAPSHOT_CAPTURED")
EventType.register("LAM_SNAPSHOT_RESTORED")
EventType.register("LAM_PRE_WARM_TRIGGERED")

# Trigger events
EventType.register("LAM_TRIGGER_CREATED")
EventType.register("LAM_TRIGGER_ENABLED")
EventType.register("LAM_TRIGGER_DISABLED")
EventType.register("LAM_TRIGGER_FIRED")

# DLQ events
EventType.register("LAM_DLQ_MESSAGE_SENT")
EventType.register("LAM_DLQ_MESSAGE_RECEIVED")
EventType.register("LAM_DLQ_MESSAGE_REPLAYED")
EventType.register("LAM_DLQ_PURGED")

# Retry events
EventType.register("LAM_RETRY_ATTEMPTED")
EventType.register("LAM_RETRY_SUCCEEDED")
EventType.register("LAM_RETRY_EXHAUSTED")

# Layer events
EventType.register("LAM_LAYER_CREATED")
EventType.register("LAM_LAYER_PUBLISHED")

# Auto-scaler events
EventType.register("LAM_SCALE_UP")
EventType.register("LAM_SCALE_DOWN")

# Middleware / dashboard
EventType.register("LAM_EVALUATION_PROCESSED")
EventType.register("LAM_DASHBOARD_RENDERED")

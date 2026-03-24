"""Configuration Hot-Reload events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("HOT_RELOAD_FILE_CHANGED")
EventType.register("HOT_RELOAD_DIFF_COMPUTED")
EventType.register("HOT_RELOAD_VALIDATION_PASSED")
EventType.register("HOT_RELOAD_VALIDATION_FAILED")
EventType.register("HOT_RELOAD_RAFT_ELECTION_WON")
EventType.register("HOT_RELOAD_RAFT_HEARTBEAT")
EventType.register("HOT_RELOAD_RAFT_CONSENSUS_REACHED")
EventType.register("HOT_RELOAD_SUBSYSTEM_RELOADED")
EventType.register("HOT_RELOAD_ROLLBACK_INITIATED")
EventType.register("HOT_RELOAD_ROLLBACK_COMPLETED")
EventType.register("HOT_RELOAD_COMPLETED")
EventType.register("HOT_RELOAD_FAILED")
EventType.register("HOT_RELOAD_WATCHER_STARTED")
EventType.register("HOT_RELOAD_WATCHER_STOPPED")

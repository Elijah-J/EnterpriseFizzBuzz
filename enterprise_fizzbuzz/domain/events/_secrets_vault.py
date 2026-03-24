"""Secrets Management Vault events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("VAULT_INITIALIZED")
EventType.register("VAULT_SEALED")
EventType.register("VAULT_UNSEALED")
EventType.register("VAULT_UNSEAL_SHARE_SUBMITTED")
EventType.register("VAULT_SECRET_STORED")
EventType.register("VAULT_SECRET_RETRIEVED")
EventType.register("VAULT_SECRET_DELETED")
EventType.register("VAULT_SECRET_ROTATED")
EventType.register("VAULT_ACCESS_DENIED")
EventType.register("VAULT_ACCESS_GRANTED")
EventType.register("VAULT_AUDIT_ENTRY")
EventType.register("VAULT_SCAN_STARTED")
EventType.register("VAULT_SCAN_COMPLETED")
EventType.register("VAULT_SCAN_SECRET_FOUND")
EventType.register("VAULT_DASHBOARD_RENDERED")

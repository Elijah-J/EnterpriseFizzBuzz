"""Enterprise FizzBuzz Platform - FizzEtcd: Distributed Key-Value Store"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzetcd import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzetcd")
EVENT_ETCD = EventType.register("FIZZETCD_PUT")
FIZZETCD_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 220


@dataclass
class KeyValue:
    """A versioned key-value pair with MVCC revision tracking."""
    key: str = ""
    value: str = ""
    version: int = 1
    create_revision: int = 0
    mod_revision: int = 0


@dataclass
class Lease:
    """A time-to-live lease that can be attached to keys."""
    lease_id: str = ""
    ttl_seconds: int = 0
    granted_at: str = ""
    keys: List[str] = field(default_factory=list)


@dataclass
class WatchEvent:
    """An event generated when a watched key changes."""
    event_type: str = "PUT"
    key: str = ""
    value: Optional[str] = None
    revision: int = 0


@dataclass
class FizzEtcdConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class EtcdStore:
    """A distributed key-value store implementing etcd-compatible semantics
    with MVCC versioning, watches, and lease-based key expiration."""

    def __init__(self) -> None:
        self._store: OrderedDict[str, KeyValue] = OrderedDict()
        self._revision = 0
        self._leases: Dict[str, Lease] = {}
        self._key_leases: Dict[str, str] = {}  # key -> lease_id
        self._watches: Dict[str, tuple] = {}  # watch_id -> (prefix, callback)
        self._history: List[WatchEvent] = []

    @property
    def current_revision(self) -> int:
        return self._revision

    def put(self, key: str, value: str) -> KeyValue:
        """Put a key-value pair, creating or updating as needed."""
        self._revision += 1
        existing = self._store.get(key)
        if existing:
            existing.value = value
            existing.version += 1
            existing.mod_revision = self._revision
            kv = KeyValue(key=existing.key, value=existing.value,
                          version=existing.version,
                          create_revision=existing.create_revision,
                          mod_revision=existing.mod_revision)
        else:
            stored = KeyValue(
                key=key, value=value, version=1,
                create_revision=self._revision,
                mod_revision=self._revision,
            )
            self._store[key] = stored
            kv = KeyValue(key=stored.key, value=stored.value,
                          version=stored.version,
                          create_revision=stored.create_revision,
                          mod_revision=stored.mod_revision)

        event = WatchEvent("PUT", key, value, self._revision)
        self._history.append(event)
        self._notify_watchers(event)
        return kv

    def get(self, key: str) -> Optional[KeyValue]:
        """Get a key-value pair, or None if not found."""
        return self._store.get(key)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if the key existed."""
        if key not in self._store:
            return False
        self._revision += 1
        del self._store[key]
        if key in self._key_leases:
            lease_id = self._key_leases.pop(key)
            if lease_id in self._leases:
                lease = self._leases[lease_id]
                if key in lease.keys:
                    lease.keys.remove(key)
        event = WatchEvent("DELETE", key, None, self._revision)
        self._history.append(event)
        self._notify_watchers(event)
        return True

    def get_range(self, prefix: str) -> List[KeyValue]:
        """Get all keys starting with the given prefix."""
        return [kv for key, kv in self._store.items() if key.startswith(prefix)]

    def grant_lease(self, ttl_seconds: int) -> Lease:
        """Grant a new lease with the specified TTL."""
        lease_id = f"lease-{uuid.uuid4().hex[:8]}"
        lease = Lease(
            lease_id=lease_id,
            ttl_seconds=ttl_seconds,
            granted_at=datetime.utcnow().isoformat(),
        )
        self._leases[lease_id] = lease
        return lease

    def attach_lease(self, key: str, lease_id: str) -> KeyValue:
        """Attach a lease to a key. When the lease is revoked, the key is deleted."""
        if lease_id not in self._leases:
            raise FizzEtcdLeaseError(f"Lease not found: {lease_id}")
        kv = self._store.get(key)
        if kv is None:
            raise FizzEtcdNotFoundError(key)
        self._key_leases[key] = lease_id
        self._leases[lease_id].keys.append(key)
        return kv

    def revoke_lease(self, lease_id: str) -> List[str]:
        """Revoke a lease, deleting all attached keys."""
        if lease_id not in self._leases:
            raise FizzEtcdLeaseError(f"Lease not found: {lease_id}")
        lease = self._leases.pop(lease_id)
        deleted_keys = []
        for key in list(lease.keys):
            if key in self._store:
                self.delete(key)
                deleted_keys.append(key)
            if key in self._key_leases:
                del self._key_leases[key]
        return deleted_keys

    def watch(self, prefix: str, callback: Callable) -> str:
        """Watch for changes to keys matching the prefix."""
        watch_id = f"watch-{uuid.uuid4().hex[:8]}"
        self._watches[watch_id] = (prefix, callback)
        return watch_id

    def cancel_watch(self, watch_id: str) -> None:
        """Cancel a watch."""
        if watch_id in self._watches:
            del self._watches[watch_id]

    def compact(self, revision: int) -> None:
        """Remove history entries before the given revision."""
        self._history = [e for e in self._history if e.revision >= revision]

    def _notify_watchers(self, event: WatchEvent) -> None:
        """Notify all watches matching the event key."""
        for watch_id, (prefix, callback) in self._watches.items():
            if event.key.startswith(prefix):
                try:
                    callback(event)
                except Exception as e:
                    logger.warning("Watch callback error for %s: %s", watch_id, e)


class FizzEtcdDashboard:
    def __init__(self, store: Optional[EtcdStore] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzEtcd Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZETCD_VERSION}"]
        if self._store:
            lines.append(f"  Revision: {self._store.current_revision}")
            lines.append(f"  Keys: {len(self._store._store)}")
            lines.append(f"  Leases: {len(self._store._leases)}")
            lines.append(f"  Watches: {len(self._store._watches)}")
        return "\n".join(lines)


class FizzEtcdMiddleware(IMiddleware):
    def __init__(self, store: Optional[EtcdStore] = None,
                 dashboard: Optional[FizzEtcdDashboard] = None) -> None:
        self._store = store
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzetcd"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzetcd_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[EtcdStore, FizzEtcdDashboard, FizzEtcdMiddleware]:
    """Factory function that creates and wires the FizzEtcd subsystem."""
    store = EtcdStore()
    store.put("/fizzbuzz/config/rules/standard", "3,5")
    store.put("/fizzbuzz/config/format", "plain")
    store.put("/fizzbuzz/status/healthy", "true")

    dashboard = FizzEtcdDashboard(store, dashboard_width)
    middleware = FizzEtcdMiddleware(store, dashboard)
    logger.info("FizzEtcd initialized: %d keys, revision %d",
                len(store._store), store.current_revision)
    return store, dashboard, middleware

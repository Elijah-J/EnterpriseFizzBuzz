"""
Enterprise FizzBuzz Platform - FizzConfig2: Distributed Configuration Server

Centralized configuration with versioning, rollback, validation, and watchers.

Architecture reference: Consul KV, etcd, Spring Cloud Config, HashiCorp Vault.
"""

from __future__ import annotations

import copy
import logging
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzconfig2 import (
    FizzConfig2Error, FizzConfig2KeyNotFoundError, FizzConfig2NamespaceError,
    FizzConfig2ValidationError, FizzConfig2VersionError, FizzConfig2WatchError,
    FizzConfig2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzconfig2")

EVENT_CONFIG_CHANGED = EventType.register("FIZZCONFIG2_CHANGED")

FIZZCONFIG2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 150


@dataclass
class FizzConfig2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class ConfigEntry:
    key: str = ""
    value: Any = None
    version: int = 1
    updated_at: Optional[datetime] = None
    updated_by: str = ""
    previous_value: Any = None

@dataclass
class ConfigNamespace:
    name: str = ""
    entries: Dict[str, ConfigEntry] = field(default_factory=dict)


# ============================================================
# Config Store
# ============================================================

class ConfigStore:
    """Versioned configuration store with rollback and history."""

    def __init__(self) -> None:
        self._namespaces: Dict[str, ConfigNamespace] = {}
        self._history: Dict[str, List[ConfigEntry]] = defaultdict(list)  # ns/key -> history
        self._watchers = ConfigWatcher()

    def set(self, namespace: str, key: str, value: Any, updated_by: str = "system") -> ConfigEntry:
        if namespace not in self._namespaces:
            self._namespaces[namespace] = ConfigNamespace(name=namespace)

        ns = self._namespaces[namespace]
        existing = ns.entries.get(key)
        old_value = existing.value if existing else None
        version = (existing.version + 1) if existing else 1

        entry = ConfigEntry(
            key=key, value=value, version=version,
            updated_at=datetime.utcnow(),
            updated_by=updated_by, previous_value=old_value,
        )
        ns.entries[key] = entry

        # Record history
        history_key = f"{namespace}/{key}"
        self._history[history_key].append(copy.deepcopy(entry))

        # Notify watchers
        self._watchers.notify(namespace, key, old_value, value)

        return entry

    def get(self, namespace: str, key: str) -> Any:
        entry = self.get_entry(namespace, key)
        return entry.value

    def get_entry(self, namespace: str, key: str) -> ConfigEntry:
        ns = self._namespaces.get(namespace)
        if ns is None:
            raise FizzConfig2KeyNotFoundError(namespace, key)
        entry = ns.entries.get(key)
        if entry is None:
            raise FizzConfig2KeyNotFoundError(namespace, key)
        return entry

    def list_keys(self, namespace: str) -> List[str]:
        ns = self._namespaces.get(namespace)
        if ns is None:
            return []
        return list(ns.entries.keys())

    def list_namespaces(self) -> List[str]:
        return sorted(self._namespaces.keys())

    def delete(self, namespace: str, key: str) -> None:
        ns = self._namespaces.get(namespace)
        if ns and key in ns.entries:
            del ns.entries[key]

    def get_version(self, namespace: str, key: str) -> int:
        entry = self.get_entry(namespace, key)
        return entry.version

    def rollback(self, namespace: str, key: str, version: int) -> ConfigEntry:
        history_key = f"{namespace}/{key}"
        history = self._history.get(history_key, [])
        for entry in history:
            if entry.version == version:
                # Create a new entry with the old value at a new version
                return self.set(namespace, key, entry.value, f"rollback-to-v{version}")
        raise FizzConfig2VersionError(f"Version {version} not found for {namespace}/{key}")

    def get_history(self, namespace: str, key: str) -> List[ConfigEntry]:
        history_key = f"{namespace}/{key}"
        return list(self._history.get(history_key, []))

    @property
    def watcher(self) -> "ConfigWatcher":
        return self._watchers


# ============================================================
# Config Validator
# ============================================================

class ConfigValidator:
    """Validates configuration values against registered schemas."""

    def __init__(self) -> None:
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register_schema(self, key: str, schema: Dict[str, Any]) -> None:
        self._schemas[key] = schema

    def validate(self, key: str, value: Any, schema: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str]]:
        s = schema or self._schemas.get(key, {})
        errors = []

        if "type" in s:
            expected_type = s["type"]
            type_map = {"string": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}
            if expected_type in type_map and not isinstance(value, type_map[expected_type]):
                errors.append(f"Expected type {expected_type}, got {type(value).__name__}")

        if "min" in s and isinstance(value, (int, float)) and value < s["min"]:
            errors.append(f"Value {value} below minimum {s['min']}")

        if "max" in s and isinstance(value, (int, float)) and value > s["max"]:
            errors.append(f"Value {value} above maximum {s['max']}")

        if "enum" in s and value not in s["enum"]:
            errors.append(f"Value {value} not in allowed values {s['enum']}")

        if "required" in s and s["required"] and value is None:
            errors.append("Value is required")

        return len(errors) == 0, errors


# ============================================================
# Config Watcher
# ============================================================

class ConfigWatcher:
    """Watches for configuration changes and notifies callbacks."""

    def __init__(self) -> None:
        self._watches: Dict[str, Dict[str, Callable]] = defaultdict(dict)  # ns/key -> watch_id -> callback

    def watch(self, namespace: str, key: str, callback: Callable) -> str:
        watch_id = f"w-{uuid.uuid4().hex[:8]}"
        watch_key = f"{namespace}/{key}"
        self._watches[watch_key][watch_id] = callback
        return watch_id

    def unwatch(self, watch_id: str) -> None:
        for watch_key in list(self._watches.keys()):
            self._watches[watch_key].pop(watch_id, None)

    def notify(self, namespace: str, key: str, old_value: Any, new_value: Any) -> None:
        watch_key = f"{namespace}/{key}"
        for callback in list(self._watches.get(watch_key, {}).values()):
            try:
                callback(namespace, key, old_value, new_value)
            except Exception:
                pass


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzConfig2Dashboard:
    def __init__(self, store: Optional[ConfigStore] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzConfig2 Configuration Server".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZCONFIG2_VERSION}",
        ]
        if self._store:
            nss = self._store.list_namespaces()
            lines.append(f"  Namespaces: {len(nss)}")
            for ns in nss:
                keys = self._store.list_keys(ns)
                lines.append(f"  {ns}: {len(keys)} keys")
                for key in keys[:5]:
                    entry = self._store.get_entry(ns, key)
                    lines.append(f"    {key} = {entry.value} (v{entry.version})")
        return "\n".join(lines)


class FizzConfig2Middleware(IMiddleware):
    def __init__(self, store: Optional[ConfigStore] = None,
                 dashboard: Optional[FizzConfig2Dashboard] = None) -> None:
        self._store = store
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzconfig2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzConfig2 not initialized"

    def render_list(self) -> str:
        if not self._store: return "No store"
        lines = ["FizzConfig2 Keys:"]
        for ns in self._store.list_namespaces():
            for key in self._store.list_keys(ns):
                entry = self._store.get_entry(ns, key)
                lines.append(f"  {ns}/{key} = {entry.value} (v{entry.version})")
        return "\n".join(lines)


def create_fizzconfig2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[ConfigStore, FizzConfig2Dashboard, FizzConfig2Middleware]:
    store = ConfigStore()

    # Default platform configuration
    store.set("platform", "version", "1.0.0", "system")
    store.set("platform", "modules", 156, "system")
    store.set("platform", "operator", "bob.mcfizzington", "system")
    store.set("fizzbuzz", "range_start", 1, "system")
    store.set("fizzbuzz", "range_end", 100, "system")
    store.set("fizzbuzz", "strategy", "standard", "system")

    dashboard = FizzConfig2Dashboard(store, dashboard_width)
    middleware = FizzConfig2Middleware(store, dashboard)

    logger.info("FizzConfig2 initialized: %d namespaces", len(store.list_namespaces()))
    return store, dashboard, middleware

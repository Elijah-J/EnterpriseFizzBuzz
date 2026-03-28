"""Enterprise FizzBuzz Platform - FizzLSM: Log-Structured Merge Tree"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzlsm import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzlsm")
EVENT_LSM = EventType.register("FIZZLSM_FLUSH")
FIZZLSM_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 232
TOMBSTONE = "__TOMBSTONE__"
DEFAULT_MEMTABLE_MAX = 100


@dataclass
class MemTable:
    entries: OrderedDict = field(default_factory=OrderedDict)
    size: int = 0
    max_size: int = DEFAULT_MEMTABLE_MAX

@dataclass
class SSTable:
    table_id: str = ""; level: int = 0
    entries: OrderedDict = field(default_factory=OrderedDict)
    min_key: str = ""; max_key: str = ""

@dataclass
class FizzLSMConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class LSMTree:
    """Log-Structured Merge Tree providing write-optimized storage with
    tiered compaction for the Enterprise FizzBuzz data pipeline."""

    def __init__(self, memtable_max: int = DEFAULT_MEMTABLE_MAX,
                 memtable_max_size: int = 0) -> None:
        effective_max = memtable_max_size or memtable_max
        self._memtable = MemTable(max_size=effective_max)
        self._sstables: List[SSTable] = []  # newest first

    def put(self, key: str, value: str) -> None:
        self._memtable.entries[key] = value
        self._memtable.size = len(self._memtable.entries)
        if self._memtable.size >= self._memtable.max_size:
            self.flush()

    def get(self, key: str) -> Optional[str]:
        # Check memtable first
        if key in self._memtable.entries:
            val = self._memtable.entries[key]
            return None if val == TOMBSTONE else val
        # Check SSTables newest to oldest
        for sst in self._sstables:
            if key in sst.entries:
                val = sst.entries[key]
                return None if val == TOMBSTONE else val
        return None

    def delete(self, key: str) -> bool:
        existed = self.get(key) is not None
        self._memtable.entries[key] = TOMBSTONE
        self._memtable.size = len(self._memtable.entries)
        return existed

    def flush(self) -> SSTable:
        if not self._memtable.entries:
            return SSTable()
        entries = OrderedDict(sorted(self._memtable.entries.items()))
        keys = list(entries.keys())
        sst = SSTable(
            table_id=f"sst-{uuid.uuid4().hex[:8]}",
            level=0,
            entries=entries,
            min_key=keys[0],
            max_key=keys[-1],
        )
        self._sstables.insert(0, sst)
        self._memtable = MemTable(max_size=self._memtable.max_size)
        logger.debug("Flushed memtable to SSTable %s (%d entries)", sst.table_id, len(entries))
        return sst

    def compact(self, level: int = 0) -> None:
        """Merge SSTables at the given level into the next level."""
        tables_at_level = [s for s in self._sstables if s.level == level]
        if len(tables_at_level) < 2:
            return
        merged = OrderedDict()
        for sst in reversed(tables_at_level):
            merged.update(sst.entries)
        # Remove tombstones during compaction
        merged = OrderedDict((k, v) for k, v in sorted(merged.items()) if v != TOMBSTONE)
        keys = list(merged.keys())
        new_sst = SSTable(
            table_id=f"sst-{uuid.uuid4().hex[:8]}",
            level=level + 1,
            entries=merged,
            min_key=keys[0] if keys else "",
            max_key=keys[-1] if keys else "",
        )
        self._sstables = [s for s in self._sstables if s.level != level]
        self._sstables.insert(0, new_sst)

    def get_stats(self) -> dict:
        total = self._memtable.size + sum(len(s.entries) for s in self._sstables)
        return {
            "memtable_size": self._memtable.size,
            "sstable_count": len(self._sstables),
            "total_entries": total,
        }

    def list_sstables(self) -> List[SSTable]:
        return list(self._sstables)


class FizzLSMDashboard:
    def __init__(self, tree: Optional[LSMTree] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._tree = tree; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzLSM Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZLSM_VERSION}"]
        if self._tree:
            stats = self._tree.get_stats()
            lines.append(f"  MemTable: {stats['memtable_size']} entries")
            lines.append(f"  SSTables: {stats['sstable_count']}")
            lines.append(f"  Total: {stats['total_entries']} entries")
        return "\n".join(lines)


class FizzLSMMiddleware(IMiddleware):
    def __init__(self, tree: Optional[LSMTree] = None, dashboard: Optional[FizzLSMDashboard] = None) -> None:
        self._tree = tree; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzlsm"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzlsm_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[LSMTree, FizzLSMDashboard, FizzLSMMiddleware]:
    tree = LSMTree()
    for i in range(1, 16):
        result = "FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else str(i)
        tree.put(f"fizzbuzz/{i}", result)
    dashboard = FizzLSMDashboard(tree, dashboard_width)
    middleware = FizzLSMMiddleware(tree, dashboard)
    logger.info("FizzLSM initialized: %d entries", tree.get_stats()["total_entries"])
    return tree, dashboard, middleware

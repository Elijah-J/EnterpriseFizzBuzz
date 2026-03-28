"""
Enterprise FizzBuzz Platform - FizzEBPFMap eBPF Map Data Structures

Implements kernel-style eBPF map data structures for high-performance FizzBuzz
classification data storage. The Linux eBPF subsystem provides a set of
generic key-value data structures that programs running in the kernel can use
to share state with userspace and with each other. These maps are optimized
for concurrent access patterns found in packet processing, tracing, and
security enforcement.

The FizzEBPFMap subsystem faithfully models five core map types:

    MapRegistry
        ├── HashMap          (O(1) key-value with configurable capacity)
        ├── ArrayMap          (index-addressed fixed-size array)
        ├── RingBuffer        (lock-free SPSC circular buffer)
        ├── LPMTrie           (longest-prefix-match trie for range queries)
        └── PerCPUHash        (per-CPU hash map for contention-free updates)

FizzBuzz classification results are stored in eBPF maps keyed by input
number, enabling O(1) lookup of cached results across the processing
pipeline. The per-CPU variant eliminates lock contention in multi-threaded
evaluation contexts by maintaining independent hash tables per logical CPU.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Iterator, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZEBPFMAP_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 240

DEFAULT_MAX_ENTRIES = 65536
DEFAULT_KEY_SIZE = 4
DEFAULT_VALUE_SIZE = 8
DEFAULT_RING_BUFFER_SIZE = 4096
DEFAULT_CPU_COUNT = 4
MAX_PREFIX_LEN = 128


# ============================================================================
# Enums
# ============================================================================

class MapType(Enum):
    """Supported eBPF map types."""
    HASH = "BPF_MAP_TYPE_HASH"
    ARRAY = "BPF_MAP_TYPE_ARRAY"
    RING_BUFFER = "BPF_MAP_TYPE_RINGBUF"
    LPM_TRIE = "BPF_MAP_TYPE_LPM_TRIE"
    PERCPU_HASH = "BPF_MAP_TYPE_PERCPU_HASH"


# ============================================================================
# Abstract Base
# ============================================================================

class EBPFMap(ABC):
    """Abstract base class for all eBPF map types."""

    def __init__(self, name: str, map_type: MapType, max_entries: int,
                 key_size: int = DEFAULT_KEY_SIZE,
                 value_size: int = DEFAULT_VALUE_SIZE) -> None:
        self.name = name
        self.map_type = map_type
        self.max_entries = max_entries
        self.key_size = key_size
        self.value_size = value_size
        self.create_time = time.monotonic()

    @abstractmethod
    def lookup(self, key: Any) -> Optional[Any]:
        """Look up a value by key."""
        ...

    @abstractmethod
    def update(self, key: Any, value: Any) -> None:
        """Insert or update a key-value pair."""
        ...

    @abstractmethod
    def delete(self, key: Any) -> None:
        """Delete a key-value pair."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return the number of entries in the map."""
        ...

    def get_stats(self) -> dict:
        """Return map statistics."""
        return {
            "name": self.name,
            "type": self.map_type.value,
            "max_entries": self.max_entries,
            "current_entries": self.count(),
            "key_size": self.key_size,
            "value_size": self.value_size,
        }


# ============================================================================
# HashMap
# ============================================================================

class HashMap(EBPFMap):
    """eBPF hash map with O(1) average-case lookup.

    Implements BPF_MAP_TYPE_HASH semantics: a general-purpose hash table
    with configurable maximum entries, key size, and value size. Insertions
    beyond max_entries are rejected to prevent unbounded memory growth.
    """

    def __init__(self, name: str, max_entries: int = DEFAULT_MAX_ENTRIES,
                 key_size: int = DEFAULT_KEY_SIZE,
                 value_size: int = DEFAULT_VALUE_SIZE) -> None:
        super().__init__(name, MapType.HASH, max_entries, key_size, value_size)
        self._data: dict[Any, Any] = {}

    def lookup(self, key: Any) -> Optional[Any]:
        return self._data.get(key)

    def update(self, key: Any, value: Any) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapFullError

        if key not in self._data and len(self._data) >= self.max_entries:
            raise EBPFMapFullError(self.name, self.max_entries)
        self._data[key] = value

    def delete(self, key: Any) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapKeyError

        if key not in self._data:
            raise EBPFMapKeyError(self.name, key)
        del self._data[key]

    def count(self) -> int:
        return len(self._data)

    def keys(self) -> list:
        return list(self._data.keys())

    def items(self) -> list[tuple]:
        return list(self._data.items())


# ============================================================================
# ArrayMap
# ============================================================================

class ArrayMap(EBPFMap):
    """eBPF array map with O(1) index-addressed access.

    Implements BPF_MAP_TYPE_ARRAY semantics: a fixed-size array where
    keys are integer indices from 0 to max_entries-1. Unlike hash maps,
    array maps cannot delete entries — they can only be zeroed.
    """

    def __init__(self, name: str, max_entries: int = DEFAULT_MAX_ENTRIES,
                 value_size: int = DEFAULT_VALUE_SIZE) -> None:
        super().__init__(name, MapType.ARRAY, max_entries, key_size=4, value_size=value_size)
        self._data: list[Any] = [None] * max_entries

    def lookup(self, key: int) -> Optional[Any]:
        if not isinstance(key, int) or key < 0 or key >= self.max_entries:
            return None
        return self._data[key]

    def update(self, key: int, value: Any) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapKeyError

        if not isinstance(key, int) or key < 0 or key >= self.max_entries:
            raise EBPFMapKeyError(self.name, key)
        self._data[key] = value

    def delete(self, key: int) -> None:
        """Array maps do not support deletion; reset to None instead."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapKeyError

        if not isinstance(key, int) or key < 0 or key >= self.max_entries:
            raise EBPFMapKeyError(self.name, key)
        self._data[key] = None

    def count(self) -> int:
        return sum(1 for v in self._data if v is not None)


# ============================================================================
# RingBuffer
# ============================================================================

class RingBuffer(EBPFMap):
    """eBPF ring buffer for lock-free event streaming.

    Implements BPF_MAP_TYPE_RINGBUF semantics: a single-producer
    single-consumer circular buffer. Events are appended to the tail
    and consumed from the head. When the buffer is full, the oldest
    events are overwritten (overwrite mode) or new events are rejected
    (strict mode).
    """

    def __init__(self, name: str, capacity: int = DEFAULT_RING_BUFFER_SIZE,
                 overwrite: bool = False) -> None:
        super().__init__(name, MapType.RING_BUFFER, capacity)
        self.capacity = capacity
        self.overwrite = overwrite
        self._buffer: list[Any] = []
        self._total_produced = 0
        self._total_consumed = 0

    def submit(self, event: Any) -> None:
        """Submit an event to the ring buffer."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import (
            EBPFRingBufferError,
        )

        if len(self._buffer) >= self.capacity:
            if self.overwrite:
                self._buffer.pop(0)
            else:
                raise EBPFRingBufferError(self.name, "buffer full")
        self._buffer.append(event)
        self._total_produced += 1

    def drain(self, max_events: int = 0) -> list[Any]:
        """Drain events from the ring buffer.

        Args:
            max_events: Maximum events to drain. 0 means drain all.

        Returns:
            List of drained events.
        """
        if max_events <= 0:
            events = list(self._buffer)
            self._buffer.clear()
        else:
            events = self._buffer[:max_events]
            self._buffer = self._buffer[max_events:]
        self._total_consumed += len(events)
        return events

    def peek(self) -> Optional[Any]:
        """Peek at the next event without consuming it."""
        if not self._buffer:
            return None
        return self._buffer[0]

    def lookup(self, key: Any) -> Optional[Any]:
        """Ring buffers do not support keyed lookup."""
        return None

    def update(self, key: Any, value: Any) -> None:
        """Use submit() for ring buffers."""
        self.submit(value)

    def delete(self, key: Any) -> None:
        """Ring buffers do not support keyed deletion."""
        pass

    def count(self) -> int:
        return len(self._buffer)

    @property
    def total_produced(self) -> int:
        return self._total_produced

    @property
    def total_consumed(self) -> int:
        return self._total_consumed

    def get_stats(self) -> dict:
        base = super().get_stats()
        base.update({
            "capacity": self.capacity,
            "buffered": len(self._buffer),
            "total_produced": self._total_produced,
            "total_consumed": self._total_consumed,
            "overwrite": self.overwrite,
        })
        return base


# ============================================================================
# LPMTrie
# ============================================================================

@dataclass
class _LPMTrieNode:
    """Internal node for the longest-prefix-match trie."""
    children: dict[int, "_LPMTrieNode"] = field(default_factory=dict)
    value: Any = None
    prefix_len: int = 0
    has_value: bool = False


class LPMTrie(EBPFMap):
    """eBPF longest-prefix-match trie for range-based lookups.

    Implements BPF_MAP_TYPE_LPM_TRIE semantics: keys are (prefix_len, data)
    tuples representing network-style prefixes. Lookups return the value
    associated with the longest matching prefix.

    In FizzBuzz context, this enables range-based classification rules:
    numbers matching a prefix pattern are classified according to the
    longest matching rule.
    """

    def __init__(self, name: str, max_entries: int = DEFAULT_MAX_ENTRIES,
                 max_prefix_len: int = MAX_PREFIX_LEN) -> None:
        super().__init__(name, MapType.LPM_TRIE, max_entries)
        self.max_prefix_len = max_prefix_len
        self._root = _LPMTrieNode()
        self._count = 0

    def _key_to_bits(self, key: int, prefix_len: int) -> list[int]:
        """Convert an integer key to a list of bits up to prefix_len."""
        bits = []
        for i in range(prefix_len):
            bits.append((key >> (self.max_prefix_len - 1 - i)) & 1)
        return bits

    def update(self, key: tuple[int, int], value: Any) -> None:
        """Insert a prefix. Key is (prefix_len, data)."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import (
            EBPFLPMTrieError,
            EBPFMapFullError,
        )

        prefix_len, data = key
        if prefix_len < 0 or prefix_len > self.max_prefix_len:
            raise EBPFLPMTrieError(prefix_len, self.max_prefix_len)
        if self._count >= self.max_entries:
            raise EBPFMapFullError(self.name, self.max_entries)

        bits = self._key_to_bits(data, prefix_len)
        node = self._root
        for bit in bits:
            if bit not in node.children:
                node.children[bit] = _LPMTrieNode()
            node = node.children[bit]
        if not node.has_value:
            self._count += 1
        node.value = value
        node.prefix_len = prefix_len
        node.has_value = True

    def lookup(self, key: Any) -> Optional[Any]:
        """Look up the longest matching prefix for a given key (integer)."""
        bits = self._key_to_bits(key, self.max_prefix_len)
        node = self._root
        best = None
        for bit in bits:
            if node.has_value:
                best = node.value
            if bit not in node.children:
                break
            node = node.children[bit]
        else:
            if node.has_value:
                best = node.value
        return best

    def delete(self, key: tuple[int, int]) -> None:
        """Delete a prefix entry."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapKeyError

        prefix_len, data = key
        bits = self._key_to_bits(data, prefix_len)
        node = self._root
        for bit in bits:
            if bit not in node.children:
                raise EBPFMapKeyError(self.name, key)
            node = node.children[bit]
        if not node.has_value:
            raise EBPFMapKeyError(self.name, key)
        node.has_value = False
        node.value = None
        self._count -= 1

    def count(self) -> int:
        return self._count


# ============================================================================
# PerCPUHash
# ============================================================================

class PerCPUHash(EBPFMap):
    """eBPF per-CPU hash map for contention-free updates.

    Implements BPF_MAP_TYPE_PERCPU_HASH semantics: maintains an
    independent hash table per logical CPU. Updates on different CPUs
    never contend, making this map type ideal for counters and statistics
    in multi-threaded FizzBuzz evaluation contexts.
    """

    def __init__(self, name: str, max_entries: int = DEFAULT_MAX_ENTRIES,
                 num_cpus: int = DEFAULT_CPU_COUNT,
                 key_size: int = DEFAULT_KEY_SIZE,
                 value_size: int = DEFAULT_VALUE_SIZE) -> None:
        super().__init__(name, MapType.PERCPU_HASH, max_entries, key_size, value_size)
        self.num_cpus = num_cpus
        self._per_cpu: list[dict[Any, Any]] = [{} for _ in range(num_cpus)]

    def update(self, key: Any, value: Any, cpu: int = 0) -> None:
        """Update a value on a specific CPU's hash table."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapFullError

        cpu = cpu % self.num_cpus
        table = self._per_cpu[cpu]
        if key not in table and len(table) >= self.max_entries:
            raise EBPFMapFullError(self.name, self.max_entries)
        table[key] = value

    def lookup(self, key: Any, cpu: int = 0) -> Optional[Any]:
        """Look up a value from a specific CPU's hash table."""
        cpu = cpu % self.num_cpus
        return self._per_cpu[cpu].get(key)

    def lookup_all_cpus(self, key: Any) -> list[Optional[Any]]:
        """Look up a value across all CPUs."""
        return [table.get(key) for table in self._per_cpu]

    def delete(self, key: Any, cpu: int = 0) -> None:
        """Delete a key from a specific CPU's hash table."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapKeyError

        cpu = cpu % self.num_cpus
        if key not in self._per_cpu[cpu]:
            raise EBPFMapKeyError(self.name, key)
        del self._per_cpu[cpu][key]

    def count(self) -> int:
        """Return total entries across all CPUs."""
        return sum(len(t) for t in self._per_cpu)

    def count_per_cpu(self) -> list[int]:
        """Return entry counts per CPU."""
        return [len(t) for t in self._per_cpu]

    def get_stats(self) -> dict:
        base = super().get_stats()
        base.update({
            "num_cpus": self.num_cpus,
            "per_cpu_counts": self.count_per_cpu(),
        })
        return base


# ============================================================================
# MapRegistry
# ============================================================================

class MapRegistry:
    """Registry for creating and managing eBPF maps by type.

    Provides a centralized registry for all eBPF maps in the system.
    Maps are created through the registry to enforce naming uniqueness
    and enable discovery by name or type.
    """

    def __init__(self) -> None:
        self._maps: dict[str, EBPFMap] = {}

    @property
    def map_count(self) -> int:
        return len(self._maps)

    def create_map(self, name: str, map_type: MapType,
                   max_entries: int = DEFAULT_MAX_ENTRIES,
                   **kwargs: Any) -> EBPFMap:
        """Create a new map and register it."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import EBPFMapError

        if name in self._maps:
            raise EBPFMapError(
                f"Map '{name}' already exists in registry",
                error_code="EFP-EBPF0",
            )

        if map_type == MapType.HASH:
            m = HashMap(name, max_entries, **kwargs)
        elif map_type == MapType.ARRAY:
            m = ArrayMap(name, max_entries, **kwargs)
        elif map_type == MapType.RING_BUFFER:
            m = RingBuffer(name, capacity=max_entries, **kwargs)
        elif map_type == MapType.LPM_TRIE:
            m = LPMTrie(name, max_entries, **kwargs)
        elif map_type == MapType.PERCPU_HASH:
            m = PerCPUHash(name, max_entries, **kwargs)
        else:
            raise EBPFMapError(
                f"Unsupported map type: {map_type}",
                error_code="EFP-EBPF0",
            )

        self._maps[name] = m
        logger.info("eBPF map '%s' created (type: %s, max: %d)",
                     name, map_type.value, max_entries)
        return m

    def get_map(self, name: str) -> EBPFMap:
        """Retrieve a map by name."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import (
            EBPFMapNotFoundError,
        )

        if name not in self._maps:
            raise EBPFMapNotFoundError(name)
        return self._maps[name]

    def delete_map(self, name: str) -> None:
        """Remove a map from the registry."""
        from enterprise_fizzbuzz.domain.exceptions.fizzebpfmap import (
            EBPFMapNotFoundError,
        )

        if name not in self._maps:
            raise EBPFMapNotFoundError(name)
        del self._maps[name]
        logger.info("eBPF map '%s' deleted", name)

    def list_maps(self) -> list[str]:
        """List all registered map names."""
        return list(self._maps.keys())

    def get_stats(self) -> dict:
        """Return registry-level statistics."""
        return {
            "map_count": self.map_count,
            "maps": {name: m.get_stats() for name, m in self._maps.items()},
        }


# ============================================================================
# Dashboard
# ============================================================================

class EBPFMapDashboard:
    """ASCII dashboard for eBPF map registry visualization."""

    @staticmethod
    def render(registry: MapRegistry, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzEBPFMap Data Structures Dashboard".center(width))
        lines.append(border)
        lines.append(f"  Version: {FIZZEBPFMAP_VERSION}")
        lines.append(f"  Registered maps: {registry.map_count}")
        lines.append("")

        for name in registry.list_maps():
            m = registry.get_map(name)
            stats = m.get_stats()
            lines.append(f"  {name} ({stats['type']})")
            lines.append(f"    Entries: {stats['current_entries']}/{stats['max_entries']}")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class EBPFMapMiddleware(IMiddleware):
    """Middleware that stores FizzBuzz classification results in eBPF maps.

    Maintains a HashMap of classification results keyed by input number,
    and a RingBuffer of classification events for downstream consumers.
    """

    def __init__(self, registry: MapRegistry) -> None:
        self.registry = registry
        self.evaluations = 0

        # Create maps for classification storage
        self._results_map = registry.create_map(
            "fizzbuzz_results", MapType.HASH, max_entries=DEFAULT_MAX_ENTRIES,
        )
        self._events_ring = registry.create_map(
            "fizzbuzz_events", MapType.RING_BUFFER, max_entries=DEFAULT_RING_BUFFER_SIZE,
        )

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation and store results in eBPF maps."""
        number = context.number
        self.evaluations += 1

        # Check cache
        cached = self._results_map.lookup(number)
        if cached is not None:
            context.metadata["ebpf_classification"] = cached
            context.metadata["ebpf_cache_hit"] = True
        else:
            # Classify and store
            if number % 15 == 0:
                label = "FizzBuzz"
            elif number % 3 == 0:
                label = "Fizz"
            elif number % 5 == 0:
                label = "Buzz"
            else:
                label = str(number)
            self._results_map.update(number, label)
            self._events_ring.submit({"number": number, "result": label})
            context.metadata["ebpf_classification"] = label
            context.metadata["ebpf_cache_hit"] = False

        context.metadata["ebpf_enabled"] = True
        return next_handler(context)

    def get_name(self) -> str:
        return "fizzebpfmap"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzebpfmap_subsystem(
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> tuple[MapRegistry, EBPFMapMiddleware]:
    """Create and configure the complete FizzEBPFMap subsystem.

    Initializes a map registry with classification storage maps and
    creates the middleware component for pipeline integration.

    Args:
        max_entries: Maximum entries for the classification hash map.

    Returns:
        Tuple of (MapRegistry, EBPFMapMiddleware).
    """
    registry = MapRegistry()
    middleware = EBPFMapMiddleware(registry)

    logger.info(
        "FizzEBPFMap subsystem initialized: registry with %d maps",
        registry.map_count,
    )

    return registry, middleware

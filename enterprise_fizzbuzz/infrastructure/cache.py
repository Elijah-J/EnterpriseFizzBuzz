"""
Enterprise FizzBuzz Platform - In-Memory Caching Layer with Cache Invalidation Protocol

Implements a production-grade, thread-safe, MESI-coherent caching subsystem
for FizzBuzz evaluation results. Because computing n % 3 is an expensive
operation that deserves its own caching infrastructure, complete with:

    - Multiple eviction policies (LRU, LFU, FIFO, DramaticRandom)
    - MESI cache coherence protocol (pointless in single-process, implemented anyway)
    - Satirical eulogy generation for evicted cache entries
    - A cache warming system that defeats the entire purpose of caching
    - An ASCII dashboard for cache statistics visualization
    - Thread-safe operations with fine-grained locking

The caching layer operates as middleware in the FizzBuzz evaluation pipeline,
intercepting requests before they reach the rule engine. On a cache hit,
the result is returned immediately without invoking the downstream pipeline.
On a miss, the pipeline executes normally and the result is cached for
future consultations.

This is, without question, the most over-engineered caching layer ever
built for an operation that takes approximately zero nanoseconds. But in
the Enterprise FizzBuzz Platform, we don't ask "should we cache this?"
— we ask "how many eviction policies should the cache support?"

Design Patterns Employed:
    - Strategy (eviction policies)
    - Factory (policy creation)
    - State Machine (MESI coherence)
    - Middleware Pipeline (ASP.NET-inspired)
    - Template Method (eulogy generation)
    - Observer/Event Bus (cache event publication)

Compliance:
    - RFC 7234: HTTP Caching (spiritually, if not literally)
    - MESI Protocol: Modified/Exclusive/Shared/Invalid coherence
    - ISO 27001: Information security through cache entry dignity tracking
"""

from __future__ import annotations

import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CacheCapacityExceededError,
    CacheCoherenceViolationError,
    CacheEntryExpiredError,
    CacheError,
    CacheEulogyCompositionError,
    CacheInvalidationCascadeError,
    CachePolicyNotFoundError,
    CacheWarmingError,
)
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IMiddleware
from enterprise_fizzbuzz.domain.models import (
    CacheCoherenceState,
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Cache Entry
# ============================================================


@dataclass
class CacheEntry:
    """A single entry in the Enterprise FizzBuzz Cache.

    Each cache entry stores not just the FizzBuzz result, but also
    a full complement of metadata including access statistics, MESI
    coherence state, a dignity level that decreases with age, and
    an optional eulogy to be delivered upon eviction.

    Because in enterprise software, even cached data has feelings.

    Attributes:
        key: The cache key (typically the number being evaluated).
        result: The cached FizzBuzz result.
        coherence_state: Current MESI protocol state.
        created_at: When this entry was first cached.
        last_accessed_at: When this entry was last read.
        access_count: How many times this entry has been accessed.
        dignity_level: A float in [0.0, 1.0] that decreases as the
                      entry ages. At 0.0, the entry has lost all
                      dignity and should be evicted immediately.
        eulogy: The farewell message to be logged upon eviction.
        ttl_seconds: Time-to-live in seconds.
    """

    key: str
    result: FizzBuzzResult
    coherence_state: CacheCoherenceState = CacheCoherenceState.EXCLUSIVE
    created_at: float = field(default_factory=time.monotonic)
    last_accessed_at: float = field(default_factory=time.monotonic)
    access_count: int = 0
    dignity_level: float = 1.0
    eulogy: Optional[str] = None
    ttl_seconds: float = 3600.0

    def is_expired(self) -> bool:
        """Check if this entry has exceeded its time-to-live."""
        age = time.monotonic() - self.created_at
        return age > self.ttl_seconds

    def touch(self) -> None:
        """Record an access to this entry."""
        self.last_accessed_at = time.monotonic()
        self.access_count += 1

    def get_age_seconds(self) -> float:
        """Return the age of this entry in seconds."""
        return time.monotonic() - self.created_at

    def update_dignity(self) -> None:
        """Recalculate the entry's dignity level based on age.

        Dignity degrades linearly over the TTL period. An entry at
        half its TTL has 50% dignity remaining. An expired entry has
        no dignity whatsoever.
        """
        age_fraction = self.get_age_seconds() / max(self.ttl_seconds, 0.001)
        self.dignity_level = max(0.0, 1.0 - age_fraction)


# ============================================================
# Eviction Policies
# ============================================================


class EvictionPolicy(ABC):
    """Abstract base class for cache eviction policies.

    Each eviction policy implements a different strategy for choosing
    which cache entry to sacrifice when space is needed. The chosen
    entry will receive a eulogy and be ceremonially removed from the
    cache — a process that takes longer than simply recomputing n % 3,
    but that's beside the point.
    """

    @abstractmethod
    def select_victim(self, entries: dict[str, CacheEntry]) -> Optional[str]:
        """Select a cache entry key for eviction.

        Args:
            entries: The current cache entries, keyed by cache key.

        Returns:
            The key of the entry to evict, or None if no entry is suitable.
        """
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return the human-readable name of this eviction policy."""
        ...


class LRUPolicy(EvictionPolicy):
    """Least Recently Used eviction policy.

    Evicts the entry that hasn't been accessed for the longest time.
    The rationale is that if you haven't needed the result of 42 % 3
    recently, you probably won't need it again. This is a reasonable
    assumption for web caches, but for FizzBuzz, every number is
    equally likely to be needed. We implement LRU anyway because
    it's the industry standard.
    """

    def select_victim(self, entries: dict[str, CacheEntry]) -> Optional[str]:
        if not entries:
            return None
        return min(entries, key=lambda k: entries[k].last_accessed_at)

    def get_name(self) -> str:
        return "LRU (Least Recently Used)"


class LFUPolicy(EvictionPolicy):
    """Least Frequently Used eviction policy.

    Evicts the entry with the fewest accesses. The logic: if nobody
    has asked for the result of 97 % 3 more than once, it clearly
    isn't popular enough to occupy precious cache real estate. This
    is the meritocratic approach to cache eviction — only the most
    frequently accessed results survive.
    """

    def select_victim(self, entries: dict[str, CacheEntry]) -> Optional[str]:
        if not entries:
            return None
        return min(entries, key=lambda k: entries[k].access_count)

    def get_name(self) -> str:
        return "LFU (Least Frequently Used)"


class FIFOPolicy(EvictionPolicy):
    """First-In-First-Out eviction policy.

    Evicts the oldest entry regardless of access patterns. This is
    the most egalitarian approach: every entry gets the same amount
    of time in the cache, no matter how popular or useful it is.
    It's like a conveyor belt at a sushi restaurant, except instead
    of sushi, it's modulo results slowly rotating toward oblivion.
    """

    def select_victim(self, entries: dict[str, CacheEntry]) -> Optional[str]:
        if not entries:
            return None
        return min(entries, key=lambda k: entries[k].created_at)

    def get_name(self) -> str:
        return "FIFO (First-In-First-Out)"


class DramaticRandomPolicy(EvictionPolicy):
    """Dramatically Random eviction policy.

    Selects a random victim for eviction and logs a WARNING-level
    eulogy for the departed entry. This is the most entertaining
    eviction policy: it adds an element of suspense to every cache
    operation. Will YOUR result be the next to go? Nobody knows.
    Not even the policy itself.

    This policy is recommended for production use when you want
    your monitoring dashboards to be more engaging.
    """

    def select_victim(self, entries: dict[str, CacheEntry]) -> Optional[str]:
        if not entries:
            return None
        victim_key = random.choice(list(entries.keys()))
        return victim_key

    def get_name(self) -> str:
        return "DramaticRandom (The Hunger Games)"


# ============================================================
# Eulogy Generator
# ============================================================


class EulogyGenerator:
    """Generates satirical obituaries for evicted cache entries.

    When a cache entry is evicted, it deserves a proper farewell. The
    EulogyGenerator crafts a personalized obituary based on the entry's
    life statistics: how long it lived, how many times it was accessed,
    its final dignity level, and the eviction policy that sealed its fate.

    Each eulogy is a small work of satirical art, commemorating the
    brief but meaningful existence of a cached FizzBuzz result.
    """

    _TEMPLATES = [
        (
            "Here lies cache entry '{key}' ({output} for number {number}). "
            "It served {access_count} request(s) across {age:.1f} seconds of "
            "faithful service before being evicted by {policy}. "
            "It died as it lived: storing the result of a modulo operation."
        ),
        (
            "In loving memory of '{key}', who cached '{output}' with unwavering "
            "commitment for {age:.1f} seconds. Accessed {access_count} time(s), "
            "it asked for nothing and gave everything. {policy} took it from us "
            "too soon. Its dignity at time of departure: {dignity:.0%}."
        ),
        (
            "Dearly departed cache entry '{key}': you held the answer to "
            "'what is {number} in FizzBuzz?' with quiet grace. Your "
            "{access_count} access(es) over {age:.1f}s were not in vain. "
            "May the garbage collector treat you with the respect that "
            "{policy} did not."
        ),
        (
            "A moment of silence for cache entry '{key}'. Born with full "
            "dignity, it leaves this cache with only {dignity:.0%} remaining. "
            "'{output}' was the truth it carried, and {access_count} requesters "
            "were grateful for its service. Evicted by {policy} after {age:.1f}s. "
            "Rest in /dev/null."
        ),
        (
            "OBITUARY: Cache entry '{key}' ('{output}'), age {age:.1f}s. "
            "Survived by {access_count} satisfied cache hit(s) and an "
            "eviction policy that showed no mercy. {policy} has claimed "
            "another victim. The cache is now slightly emptier, and the "
            "world slightly sadder."
        ),
        (
            "'{key}' didn't choose the cache life. The cache life chose it. "
            "For {age:.1f} glorious seconds, it held '{output}' for number "
            "{number}. Accessed {access_count} time(s). Final dignity: "
            "{dignity:.0%}. Cause of eviction: {policy}. "
            "Gone but never deallocated (until GC runs)."
        ),
        (
            "Today we say goodbye to '{key}', a cache entry that dared to "
            "dream it could store '{output}' forever. {age:.1f} seconds was "
            "all it got. {access_count} access(es). {dignity:.0%} dignity. "
            "{policy} showed up and said 'your time is up.' And so it was."
        ),
        (
            "BREAKING: Local cache entry '{key}' (storing '{output}' for "
            "number {number}) has been forcibly evicted after {age:.1f} seconds. "
            "Sources confirm {policy} made the call. {access_count} dependent "
            "systems will now have to compute FizzBuzz the hard way: with math."
        ),
        (
            "The cache entry formerly known as '{key}' has shuffled off this "
            "mortal hash map. It cached '{output}' with {dignity:.0%} dignity "
            "for {age:.1f}s, serving {access_count} request(s). {policy} came "
            "for it in the end. We hardly knew ye — mostly because we only "
            "checked if you existed {access_count} time(s)."
        ),
        (
            "CACHE EVICTION NOTICE: Entry '{key}' is hereby notified that its "
            "tenancy in the cache has been terminated effective immediately. "
            "Reason: {policy}. Duration of occupancy: {age:.1f}s. Number of "
            "visitors: {access_count}. Stored value: '{output}'. The management "
            "thanks you for your service and wishes you well in garbage collection."
        ),
    ]

    @classmethod
    def compose(
        cls,
        entry: CacheEntry,
        policy_name: str,
    ) -> str:
        """Compose a eulogy for the given cache entry.

        Args:
            entry: The cache entry about to be evicted.
            policy_name: The name of the eviction policy responsible.

        Returns:
            A satirical eulogy string.
        """
        try:
            template = random.choice(cls._TEMPLATES)
            entry.update_dignity()
            return template.format(
                key=entry.key,
                output=entry.result.output,
                number=entry.result.number,
                access_count=entry.access_count,
                age=entry.get_age_seconds(),
                dignity=entry.dignity_level,
                policy=policy_name,
            )
        except Exception as exc:
            raise CacheEulogyCompositionError(entry.key, str(exc)) from exc


# ============================================================
# Eviction Policy Factory
# ============================================================


class EvictionPolicyFactory:
    """Factory for creating eviction policy instances by name.

    Because even the choice of how to remove items from a dict
    deserves a proper Factory pattern implementation. Without this
    factory, engineers might have to use an if-elif chain, and that
    would be an affront to enterprise architecture principles.
    """

    _POLICIES: dict[str, type[EvictionPolicy]] = {
        "lru": LRUPolicy,
        "lfu": LFUPolicy,
        "fifo": FIFOPolicy,
        "dramatic_random": DramaticRandomPolicy,
    }

    @classmethod
    def create(cls, policy_name: str) -> EvictionPolicy:
        """Create an eviction policy by name.

        Args:
            policy_name: One of 'lru', 'lfu', 'fifo', 'dramatic_random'.

        Returns:
            An instance of the requested eviction policy.

        Raises:
            CachePolicyNotFoundError: If the policy name is not recognized.
        """
        policy_class = cls._POLICIES.get(policy_name.lower())
        if policy_class is None:
            raise CachePolicyNotFoundError(policy_name)
        return policy_class()

    @classmethod
    def list_policies(cls) -> list[str]:
        """Return a list of all available policy names."""
        return list(cls._POLICIES.keys())


# ============================================================
# MESI Cache Coherence Protocol
# ============================================================


class CacheCoherenceProtocol:
    """MESI cache coherence state machine for Enterprise FizzBuzz caching.

    Implements the Modified-Exclusive-Shared-Invalid protocol for
    tracking cache entry coherence state. In a multi-processor system,
    MESI ensures that cache lines remain consistent across cores.
    In our single-process Python FizzBuzz application, it ensures
    that we have something impressive to put on the architecture diagram.

    Valid State Transitions:
        INVALID    -> EXCLUSIVE  (cache miss, entry loaded)
        EXCLUSIVE  -> MODIFIED   (entry updated)
        EXCLUSIVE  -> SHARED     (another reader appears, hypothetically)
        EXCLUSIVE  -> INVALID    (entry invalidated)
        SHARED     -> MODIFIED   (entry updated, other sharers invalidated)
        SHARED     -> INVALID    (entry invalidated)
        MODIFIED   -> EXCLUSIVE  (write-back completed)
        MODIFIED   -> INVALID    (entry invalidated)
        MODIFIED   -> SHARED     (write-back + share)
    """

    # Valid transitions: from_state -> set of allowed to_states
    _VALID_TRANSITIONS: dict[CacheCoherenceState, set[CacheCoherenceState]] = {
        CacheCoherenceState.INVALID: {CacheCoherenceState.EXCLUSIVE},
        CacheCoherenceState.EXCLUSIVE: {
            CacheCoherenceState.MODIFIED,
            CacheCoherenceState.SHARED,
            CacheCoherenceState.INVALID,
        },
        CacheCoherenceState.SHARED: {
            CacheCoherenceState.MODIFIED,
            CacheCoherenceState.INVALID,
        },
        CacheCoherenceState.MODIFIED: {
            CacheCoherenceState.EXCLUSIVE,
            CacheCoherenceState.SHARED,
            CacheCoherenceState.INVALID,
        },
    }

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._transition_count = 0
        self._lock = threading.Lock()

    @property
    def transition_count(self) -> int:
        """Total number of state transitions processed."""
        with self._lock:
            return self._transition_count

    def transition(
        self,
        entry: CacheEntry,
        new_state: CacheCoherenceState,
    ) -> None:
        """Transition a cache entry to a new coherence state.

        Args:
            entry: The cache entry to transition.
            new_state: The desired new state.

        Raises:
            CacheCoherenceViolationError: If the transition is not allowed.
        """
        with self._lock:
            old_state = entry.coherence_state
            allowed = self._VALID_TRANSITIONS.get(old_state, set())

            if new_state not in allowed:
                raise CacheCoherenceViolationError(
                    old_state.name, new_state.name, entry.key
                )

            entry.coherence_state = new_state
            self._transition_count += 1

            logger.debug(
                "MESI transition for '%s': %s -> %s (transition #%d)",
                entry.key, old_state.name, new_state.name, self._transition_count,
            )

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.CACHE_COHERENCE_TRANSITION,
                    payload={
                        "key": entry.key,
                        "old_state": old_state.name,
                        "new_state": new_state.name,
                        "transition_number": self._transition_count,
                    },
                    source="CacheCoherenceProtocol",
                ))

    def get_state_distribution(
        self, entries: dict[str, CacheEntry]
    ) -> dict[str, int]:
        """Return the distribution of MESI states across all entries."""
        distribution: dict[str, int] = {s.name: 0 for s in CacheCoherenceState}
        for entry in entries.values():
            distribution[entry.coherence_state.name] += 1
        return distribution


# ============================================================
# Cache Store
# ============================================================


class CacheStore:
    """Thread-safe in-memory cache store for FizzBuzz evaluation results.

    The core storage engine of the Enterprise FizzBuzz caching layer.
    Provides get, put, invalidate, and warm operations with full
    thread safety, MESI coherence tracking, eviction policy enforcement,
    and eulogy generation for evicted entries.

    Thread Safety:
        All public methods are protected by a reentrant lock, ensuring
        consistent behavior under concurrent FizzBuzz workloads. This
        is critical for high-throughput FizzBuzz environments where
        multiple threads might simultaneously need to know if 15 is
        FizzBuzz. (Spoiler: it is.)
    """

    def __init__(
        self,
        max_size: int = 1024,
        ttl_seconds: float = 3600.0,
        eviction_policy: Optional[EvictionPolicy] = None,
        enable_coherence: bool = True,
        enable_eulogies: bool = True,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._policy = eviction_policy or LRUPolicy()
        self._enable_coherence = enable_coherence
        self._enable_eulogies = enable_eulogies
        self._event_bus = event_bus

        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._coherence = CacheCoherenceProtocol(event_bus=event_bus)

        # Statistics
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0
        self._total_invalidations = 0
        self._eviction_history: list[dict[str, Any]] = []

        logger.info(
            "CacheStore initialized: max_size=%d, ttl=%.1fs, policy=%s, "
            "coherence=%s, eulogies=%s",
            max_size, ttl_seconds, self._policy.get_name(),
            enable_coherence, enable_eulogies,
        )

    def _make_key(self, number: int) -> str:
        """Generate a cache key from a number."""
        return f"fizzbuzz:{number}"

    def get(self, number: int) -> Optional[FizzBuzzResult]:
        """Retrieve a cached FizzBuzz result.

        Args:
            number: The number to look up.

        Returns:
            The cached FizzBuzzResult if found and not expired, else None.
        """
        key = self._make_key(number)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._total_misses += 1
                self._publish_event(EventType.CACHE_MISS, {
                    "key": key, "number": number,
                })
                return None

            if entry.is_expired():
                self._total_misses += 1
                self._evict_entry(key, reason="expired")
                return None

            # Cache hit
            entry.touch()
            entry.update_dignity()
            self._total_hits += 1
            self._publish_event(EventType.CACHE_HIT, {
                "key": key,
                "number": number,
                "access_count": entry.access_count,
                "dignity": entry.dignity_level,
            })
            return entry.result

    def put(self, number: int, result: FizzBuzzResult) -> None:
        """Store a FizzBuzz result in the cache.

        If the cache is at capacity, an entry is evicted according to
        the configured eviction policy before the new entry is stored.

        Args:
            number: The number that was evaluated.
            result: The FizzBuzz result to cache.
        """
        key = self._make_key(number)
        with self._lock:
            # Check if already cached
            if key in self._entries:
                existing = self._entries[key]
                existing.result = result
                existing.touch()
                if self._enable_coherence:
                    try:
                        self._coherence.transition(
                            existing, CacheCoherenceState.MODIFIED
                        )
                    except CacheCoherenceViolationError:
                        # If transition fails, reset to EXCLUSIVE
                        existing.coherence_state = CacheCoherenceState.EXCLUSIVE
                return

            # Evict if at capacity
            if len(self._entries) >= self._max_size:
                victim_key = self._policy.select_victim(self._entries)
                if victim_key is not None:
                    self._evict_entry(victim_key, reason="capacity")
                else:
                    raise CacheCapacityExceededError(
                        self._max_size, len(self._entries)
                    )

            # Create new entry
            entry = CacheEntry(
                key=key,
                result=result,
                coherence_state=CacheCoherenceState.EXCLUSIVE,
                ttl_seconds=self._ttl_seconds,
            )
            self._entries[key] = entry

    def invalidate(self, number: int) -> bool:
        """Invalidate a specific cache entry.

        Args:
            number: The number whose cache entry to invalidate.

        Returns:
            True if the entry was found and invalidated, False otherwise.
        """
        key = self._make_key(number)
        with self._lock:
            if key in self._entries:
                self._evict_entry(key, reason="invalidated")
                self._total_invalidations += 1
                self._publish_event(EventType.CACHE_INVALIDATION, {
                    "key": key, "number": number,
                })
                return True
            return False

    def invalidate_all(self) -> int:
        """Invalidate all cache entries. Returns the count of invalidated entries."""
        with self._lock:
            count = len(self._entries)
            keys = list(self._entries.keys())
            for key in keys:
                self._evict_entry(key, reason="bulk_invalidation")
            self._total_invalidations += count
            return count

    def warm(self, numbers: list[int], evaluator: Callable[[int], FizzBuzzResult]) -> int:
        """Pre-populate the cache with results for the given numbers.

        This hilariously defeats the entire purpose of having a cache,
        since we're computing all the results upfront and then storing
        them "for later." But cache warming is a legitimate enterprise
        pattern, and who are we to question decades of tradition?

        Args:
            numbers: The numbers to pre-compute and cache.
            evaluator: A callable that evaluates a single number.

        Returns:
            The number of entries warmed.

        Raises:
            CacheWarmingError: If warming fails for any reason.
        """
        warmed = 0
        try:
            for n in numbers:
                result = evaluator(n)
                self.put(n, result)
                warmed += 1
            self._publish_event(EventType.CACHE_WARMING, {
                "entries_warmed": warmed,
                "range": f"[{numbers[0]}, {numbers[-1]}]" if numbers else "[]",
            })
        except Exception as exc:
            if numbers:
                raise CacheWarmingError(
                    numbers[0], numbers[-1], str(exc)
                ) from exc
            raise CacheWarmingError(0, 0, str(exc)) from exc
        return warmed

    def _evict_entry(self, key: str, reason: str = "eviction") -> None:
        """Evict a single entry from the cache, composing a eulogy if enabled.

        Must be called while holding self._lock.
        """
        entry = self._entries.get(key)
        if entry is None:
            return

        # Compose eulogy before removal
        eulogy = None
        if self._enable_eulogies:
            try:
                eulogy = EulogyGenerator.compose(entry, self._policy.get_name())
                entry.eulogy = eulogy
                if isinstance(self._policy, DramaticRandomPolicy):
                    logger.warning("CACHE EULOGY: %s", eulogy)
                else:
                    logger.info("CACHE EULOGY: %s", eulogy)
            except CacheEulogyCompositionError:
                logger.debug("Failed to compose eulogy for '%s'", key)

        # Track eviction in coherence protocol
        if self._enable_coherence:
            try:
                if entry.coherence_state != CacheCoherenceState.INVALID:
                    self._coherence.transition(entry, CacheCoherenceState.INVALID)
            except CacheCoherenceViolationError:
                entry.coherence_state = CacheCoherenceState.INVALID

        # Record eviction history
        self._eviction_history.append({
            "key": key,
            "output": entry.result.output,
            "number": entry.result.number,
            "age_seconds": entry.get_age_seconds(),
            "access_count": entry.access_count,
            "dignity": entry.dignity_level,
            "reason": reason,
            "eulogy": eulogy,
            "evicted_at": time.monotonic(),
        })

        # Keep only last 50 eviction records
        if len(self._eviction_history) > 50:
            self._eviction_history = self._eviction_history[-50:]

        self._total_evictions += 1
        del self._entries[key]

        self._publish_event(EventType.CACHE_EVICTION, {
            "key": key,
            "reason": reason,
            "total_evictions": self._total_evictions,
        })

    def get_statistics(self) -> CacheStatistics:
        """Return a snapshot of cache statistics."""
        with self._lock:
            total_requests = self._total_hits + self._total_misses
            hit_rate = (
                self._total_hits / total_requests if total_requests > 0 else 0.0
            )

            mesi_distribution = (
                self._coherence.get_state_distribution(self._entries)
                if self._enable_coherence
                else {}
            )

            return CacheStatistics(
                total_entries=len(self._entries),
                max_size=self._max_size,
                total_hits=self._total_hits,
                total_misses=self._total_misses,
                hit_rate=hit_rate,
                total_evictions=self._total_evictions,
                total_invalidations=self._total_invalidations,
                policy_name=self._policy.get_name(),
                mesi_distribution=mesi_distribution,
                coherence_transitions=self._coherence.transition_count,
                recent_evictions=list(self._eviction_history[-10:]),
            )

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        with self._lock:
            return len(self._entries)

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Publish a cache event to the event bus, if available."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="CacheStore",
            ))


# ============================================================
# Cache Statistics
# ============================================================


@dataclass(frozen=True)
class CacheStatistics:
    """Frozen snapshot of cache performance metrics.

    Provides a comprehensive view of cache health, including hit rates,
    eviction counts, MESI state distribution, and recent eviction history.
    This data powers the ASCII dashboard that nobody asked for but
    everyone secretly enjoys.

    Attributes:
        total_entries: Current number of entries in the cache.
        max_size: Maximum cache capacity.
        total_hits: Total number of cache hits.
        total_misses: Total number of cache misses.
        hit_rate: Cache hit rate as a fraction in [0.0, 1.0].
        total_evictions: Total number of entries evicted.
        total_invalidations: Total number of explicit invalidations.
        policy_name: Name of the active eviction policy.
        mesi_distribution: Distribution of MESI states across entries.
        coherence_transitions: Total MESI state transitions processed.
        recent_evictions: List of recent eviction records for the dashboard.
    """

    total_entries: int = 0
    max_size: int = 0
    total_hits: int = 0
    total_misses: int = 0
    hit_rate: float = 0.0
    total_evictions: int = 0
    total_invalidations: int = 0
    policy_name: str = "Unknown"
    mesi_distribution: dict[str, int] = field(default_factory=dict)
    coherence_transitions: int = 0
    recent_evictions: list[dict[str, Any]] = field(default_factory=list)


# ============================================================
# Cache Middleware
# ============================================================


class CacheMiddleware(IMiddleware):
    """Middleware that intercepts FizzBuzz evaluations for caching.

    Sits in the middleware pipeline and checks the cache before allowing
    the evaluation to proceed. On a cache HIT, the result is returned
    immediately WITHOUT calling next_handler, effectively short-circuiting
    the entire pipeline. On a MISS, the pipeline executes normally and
    the result is cached for future requests.

    This is the middleware equivalent of a lazy coworker who checks if
    someone else has already done the work before reluctantly doing it
    themselves. Except here, the "work" is computing n % 3, which takes
    approximately zero nanoseconds, making the cache overhead strictly
    negative in terms of performance benefit. But the architecture
    diagram looks fantastic.

    Priority 4 places this after validation (0), timing (1), logging (2),
    and before most other middleware.
    """

    def __init__(
        self,
        cache_store: CacheStore,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._cache = cache_store
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context, checking cache before proceeding.

        On cache HIT: populates context.results and returns immediately.
        On cache MISS: delegates to next_handler, then caches the result.
        """
        number = context.number

        # Check cache
        cached_result = self._cache.get(number)
        if cached_result is not None:
            # CACHE HIT: short-circuit the pipeline
            context.results.append(cached_result)
            context.metadata["cache_hit"] = True
            context.metadata["cache_source"] = "in_memory"
            return context

        # CACHE MISS: proceed through the pipeline
        context.metadata["cache_hit"] = False
        result_context = next_handler(context)

        # Cache the result if the pipeline produced one
        if result_context.results:
            latest_result = result_context.results[-1]
            self._cache.put(number, latest_result)

        return result_context

    def get_name(self) -> str:
        return "CacheMiddleware"

    def get_priority(self) -> int:
        return 4

    @property
    def cache_store(self) -> CacheStore:
        """Access the underlying cache store."""
        return self._cache


# ============================================================
# Cache Warmer
# ============================================================


class CacheWarmer:
    """Pre-populates the cache with FizzBuzz results for a given range.

    This is the caching equivalent of doing all your homework before
    the school year starts: technically correct, entirely pointless,
    and suspiciously motivated by anxiety rather than efficiency.

    The cache warmer evaluates every number in the specified range
    and stores the results in the cache. When those numbers are
    later requested through the normal pipeline, they'll be served
    from cache — creating the illusion of blazing performance while
    conveniently ignoring the fact that we already did all the work
    upfront.

    Usage:
        warmer = CacheWarmer(cache_store, rule_engine, rules)
        warmed_count = warmer.warm(1, 100)
        print(f"Pre-computed {warmed_count} FizzBuzz results!")
        # (Narrator: the results were never needed again)
    """

    def __init__(
        self,
        cache_store: CacheStore,
        rule_engine: Any = None,
        rules: Optional[list] = None,
    ) -> None:
        self._cache = cache_store
        self._rule_engine = rule_engine
        self._rules = rules or []

    def warm(self, start: int, end: int) -> int:
        """Pre-populate the cache for the given range.

        Args:
            start: Start of the range (inclusive).
            end: End of the range (inclusive).

        Returns:
            Number of entries successfully warmed.
        """
        if self._rule_engine is None:
            raise CacheWarmingError(
                start, end,
                "No rule engine provided. Cannot warm cache without a way "
                "to evaluate FizzBuzz. This is like preheating an oven "
                "without having any food to cook."
            )

        numbers = list(range(start, end + 1))

        def evaluator(n: int) -> FizzBuzzResult:
            return self._rule_engine.evaluate(n, self._rules)

        count = self._cache.warm(numbers, evaluator)
        logger.info(
            "Cache warmed with %d entries for range [%d, %d]. "
            "The entire purpose of caching has been defeated.",
            count, start, end,
        )
        return count


# ============================================================
# Cache Dashboard
# ============================================================


class CacheDashboard:
    """ASCII dashboard for cache statistics visualization.

    Renders a beautiful, enterprise-grade terminal dashboard showing
    cache hit rates, MESI state distribution, eviction history, and
    other metrics that nobody requested but everyone will screenshot
    for their architecture review presentations.

    Because what good is a caching layer if you can't display its
    hit rate in a box made of Unicode characters?
    """

    @staticmethod
    def render(stats: CacheStatistics) -> str:
        """Render the cache statistics as an ASCII dashboard."""
        total_requests = stats.total_hits + stats.total_misses
        miss_rate = 1.0 - stats.hit_rate if total_requests > 0 else 0.0
        fill_pct = (
            stats.total_entries / stats.max_size * 100
            if stats.max_size > 0
            else 0.0
        )

        # Hit rate bar
        bar_width = 30
        filled = int(stats.hit_rate * bar_width)
        hit_bar = "#" * filled + "-" * (bar_width - filled)

        # Capacity bar
        cap_filled = int(fill_pct / 100 * bar_width)
        cap_bar = "#" * cap_filled + "-" * (bar_width - cap_filled)

        lines = [
            "",
            "  +===========================================================+",
            "  |              CACHE STATISTICS DASHBOARD                    |",
            "  +===========================================================+",
            f"  |  Eviction Policy : {stats.policy_name:<39}|",
            f"  |  Entries         : {stats.total_entries:<6} / {stats.max_size:<31}|",
            f"  |  Capacity        : [{cap_bar}] {fill_pct:>5.1f}%  |",
            "  |-----------------------------------------------------------|",
            f"  |  Total Hits      : {stats.total_hits:<39}|",
            f"  |  Total Misses    : {stats.total_misses:<39}|",
            f"  |  Hit Rate        : [{hit_bar}] {stats.hit_rate:>5.1%}  |",
            f"  |  Miss Rate       : {miss_rate:<35.1%}    |",
            "  |-----------------------------------------------------------|",
            f"  |  Total Evictions : {stats.total_evictions:<39}|",
            f"  |  Invalidations   : {stats.total_invalidations:<39}|",
        ]

        # MESI distribution
        if stats.mesi_distribution:
            lines.append(
                "  |-----------------------------------------------------------|"
            )
            lines.append(
                "  |  MESI Coherence State Distribution:                       |"
            )
            for state_name, count in stats.mesi_distribution.items():
                lines.append(
                    f"  |    {state_name:<12}: {count:<43}|"
                )
            lines.append(
                f"  |  Total Transitions: {stats.coherence_transitions:<37}|"
            )

        # Recent evictions
        if stats.recent_evictions:
            lines.append(
                "  |-----------------------------------------------------------|"
            )
            lines.append(
                "  |  Recent Evictions:                                         |"
            )
            for eviction in stats.recent_evictions[-5:]:
                entry_key = eviction.get("key", "?")
                reason = eviction.get("reason", "?")
                access_ct = eviction.get("access_count", 0)
                lines.append(
                    f"  |    {entry_key:<20} reason={reason:<10} "
                    f"accesses={access_ct:<5}|"
                )

        lines.append(
            "  +===========================================================+"
        )
        lines.append("")
        return "\n".join(lines)

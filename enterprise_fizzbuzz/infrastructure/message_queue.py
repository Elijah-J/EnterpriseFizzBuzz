"""
Enterprise FizzBuzz Platform - Message Queue & Event Bus Module

Implements a Kafka-style distributed message queue with partitioned topics,
consumer groups, offset management, schema validation, and exactly-once
delivery semantics. All backed by Python lists, because enterprise
architecture is a state of mind, not a technology stack.

The core joke: every "partition" is a Python list. Every "broker" is a
dict. Every "consumer group rebalance" is a reassignment of integer
keys in a dict. The Kafka documentation would weep, but the architecture
diagrams are indistinguishable from the real thing.

Key components:
    - Message: Frozen dataclass with SHA-256 idempotency key
    - Partition: A Python list wearing a Kafka costume
    - Topic: Holds N partitions (N Python lists)
    - Partitioner: Hash/round-robin/sticky strategies for routing
    - Producer: Sends messages with deduplication
    - Consumer/ConsumerGroup: With offset tracking and rebalancing
    - OffsetManager: Tracks committed offsets per group
    - SchemaRegistry: Validates message payloads (a dict of required keys)
    - IdempotencyLayer: Exactly-once via SHA-256 dedup (a Python set)
    - MessageBroker: Central coordinator with 5 default topics
    - MessageQueueBridge: Bridges existing EventBus to MQ
    - MQMiddleware: Priority 45 middleware
    - MQDashboard: ASCII dashboard that would make Confluent jealous
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BrokerError,
    ConsumerError,
    ConsumerGroupError,
    DuplicateMessageError,
    MessageQueueError,
    MessageSerializationError,
    OffsetOutOfRangeError,
    PartitionOutOfRangeError,
    ProducerError,
    RebalanceError,
    SchemaValidationError,
    TopicAlreadyExistsError,
    TopicNotFoundError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware, IObserver
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class PartitionStrategy(Enum):
    """Strategy for assigning messages to partitions.

    HASH:        Hash the message key and modulo by partition count.
                 This is the same approach Kafka uses, except Kafka
                 uses murmur2 and we use SHA-256 because overkill
                 is our design philosophy.
    ROUND_ROBIN: Distribute messages evenly across partitions in
                 sequence. Democratic. Predictable. Boring.
    STICKY:      Keep sending to the same partition until it gets
                 uncomfortable, then switch. Like a bad house guest.
    """

    HASH = auto()
    ROUND_ROBIN = auto()
    STICKY = auto()


class ConsumerState(Enum):
    """Lifecycle states for a consumer within a group.

    UNASSIGNED: The consumer exists but has no partitions. It sits
                in the break room of the message queue, waiting.
    ASSIGNED:   The consumer has been assigned partitions and is
                actively consuming messages (reading from a list).
    PAUSED:     The consumer has temporarily stopped consuming,
                perhaps due to backpressure or an existential crisis.
    CLOSED:     The consumer has left the group. Its partitions
                will be reassigned during the next rebalance.
    """

    UNASSIGNED = auto()
    ASSIGNED = auto()
    PAUSED = auto()
    CLOSED = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class Message:
    """An immutable message in the Enterprise FizzBuzz Message Queue.

    Each message carries a payload, a topic destination, an optional
    key for partitioning, and a SHA-256 idempotency key computed from
    the payload contents. The idempotency key ensures exactly-once
    delivery semantics, which in this context means "we check a set
    before appending to a list."

    Frozen because messages, like regret, cannot be modified after creation.

    Attributes:
        message_id: Unique identifier for this message instance.
        topic: The destination topic name.
        key: Optional partitioning key (determines which list gets this message).
        payload: The message contents as a dictionary.
        idempotency_key: SHA-256 hash of the payload for deduplication.
        timestamp: When the message was created (UTC).
        headers: Optional message headers (metadata about metadata).
        partition: Assigned partition index (-1 if not yet assigned).
        offset: Position within the partition (-1 if not yet appended).
    """

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    key: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    headers: dict[str, str] = field(default_factory=dict)
    partition: int = -1
    offset: int = -1

    @staticmethod
    def compute_idempotency_key(payload: dict[str, Any]) -> str:
        """Compute a SHA-256 idempotency key from the payload.

        This is the "exactly-once" guarantee: we hash the payload
        and check if we've seen it before. Distributed streaming
        platforms use complex transaction protocols for this. We
        use hashlib and a set. Same energy.
        """
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ConsumerOffset:
    """Tracks a consumer's position within a partition.

    In Kafka, offsets are stored in a special internal topic called
    __consumer_offsets. Here, they're stored in a dict. The functionality
    is identical: both track which messages have been consumed so that
    consumers can resume from where they left off.

    Attributes:
        topic: The topic name.
        partition: The partition index.
        offset: The current read position (next message to consume).
        committed_offset: The last committed offset (survives "restarts").
        group_id: The consumer group that owns this offset.
    """

    topic: str
    partition: int
    offset: int = 0
    committed_offset: int = 0
    group_id: str = ""


@dataclass
class RebalanceReport:
    """A verbose report documenting a consumer group rebalance event.

    Because partition reassignment deserves the same level of
    documentation as a corporate reorganization. Who got which
    partition, who lost which partition, and how long the entire
    process took — all captured in excruciating detail.

    Attributes:
        group_id: The consumer group that was rebalanced.
        previous_assignment: Partition assignments before rebalance.
        new_assignment: Partition assignments after rebalance.
        consumers_added: Consumers that joined triggering the rebalance.
        consumers_removed: Consumers that left triggering the rebalance.
        duration_ms: How long the rebalance took (always < 1ms).
        rebalance_id: Unique identifier for this rebalance event.
        timestamp: When the rebalance occurred (UTC).
    """

    group_id: str
    previous_assignment: dict[str, list[int]] = field(default_factory=dict)
    new_assignment: dict[str, list[int]] = field(default_factory=dict)
    consumers_added: list[str] = field(default_factory=list)
    consumers_removed: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    rebalance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# Partition — THE JOKE
# ============================================================


class Partition:
    """A single partition of a topic.

    THIS IS A PYTHON LIST.

    In Apache Kafka, a partition is an ordered, immutable sequence of
    records that is continually appended to — a commit log. It is
    stored on disk, replicated across brokers, and can handle millions
    of records per second.

    Here, it is a Python list. list.append() is our write path.
    list[offset] is our read path. There are no replicas, no ISR
    (in-sync replica set), no leader election. The list is both the
    leader and the only follower of itself.

    But we track metrics like a real partition because we have standards.
    """

    def __init__(self, partition_id: int, topic_name: str) -> None:
        self._partition_id = partition_id
        self._topic_name = topic_name
        self._log: list[Message] = []  # THE COMMIT LOG (a Python list)
        self._lock = threading.Lock()
        self._high_watermark = 0
        self._messages_in = 0
        self._bytes_in = 0

    @property
    def partition_id(self) -> int:
        return self._partition_id

    @property
    def topic_name(self) -> str:
        return self._topic_name

    @property
    def high_watermark(self) -> int:
        """The offset of the next message to be written.

        In Kafka, the high watermark is the offset of the last
        message that was successfully replicated to all in-sync
        replicas. Here, it's len(list). Same concept.
        """
        with self._lock:
            return len(self._log)

    @property
    def message_count(self) -> int:
        with self._lock:
            return len(self._log)

    def append(self, message: Message) -> int:
        """Append a message to this partition (list.append()).

        Returns the offset at which the message was stored.
        This is the write path. In Kafka, this involves disk I/O,
        page cache management, and zero-copy sends. Here, it involves
        list.append(). The performance characteristics are... different.
        """
        with self._lock:
            offset = len(self._log)
            # Create a new message with the assigned offset
            stored = Message(
                message_id=message.message_id,
                topic=message.topic,
                key=message.key,
                payload=message.payload,
                idempotency_key=message.idempotency_key,
                timestamp=message.timestamp,
                headers=message.headers,
                partition=self._partition_id,
                offset=offset,
            )
            self._log.append(stored)
            self._high_watermark = len(self._log)
            self._messages_in += 1
            self._bytes_in += len(json.dumps(message.payload, default=str))
            logger.debug(
                "Partition %s-%d: appended message at offset %d (list length: %d)",
                self._topic_name,
                self._partition_id,
                offset,
                len(self._log),
            )
            return offset

    def read(self, offset: int) -> Message:
        """Read a message at the given offset (list[offset]).

        This is the read path. In Kafka, this involves segment files,
        index lookups, and memory-mapped I/O. Here, it involves
        list.__getitem__(). If the offset is out of range, we raise
        a proper enterprise exception instead of an IndexError.
        """
        with self._lock:
            if offset < 0 or offset >= len(self._log):
                raise OffsetOutOfRangeError(
                    self._topic_name,
                    self._partition_id,
                    offset,
                    len(self._log),
                )
            return self._log[offset]

    def read_batch(self, start_offset: int, max_records: int) -> list[Message]:
        """Read a batch of messages starting from the given offset.

        Returns up to max_records messages. This is list slicing
        with extra steps and enterprise-grade error handling.
        """
        with self._lock:
            if start_offset < 0:
                start_offset = 0
            end = min(start_offset + max_records, len(self._log))
            return list(self._log[start_offset:end])

    def get_statistics(self) -> dict[str, Any]:
        """Return partition statistics for the dashboard."""
        with self._lock:
            return {
                "partition_id": self._partition_id,
                "topic": self._topic_name,
                "message_count": len(self._log),
                "high_watermark": self._high_watermark,
                "total_messages_in": self._messages_in,
                "total_bytes_in": self._bytes_in,
                "implementation": "Python list",
                "replication_factor": 1,
                "isr_count": 1,
                "leader": "self (the only option)",
            }


# ============================================================
# Topic
# ============================================================


class Topic:
    """A named topic containing N partitions.

    In Kafka, a topic is a category of records that producers
    publish to and consumers subscribe to. It has a configurable
    number of partitions, a replication factor, and retention policies.

    Here, it is a named collection of Python lists. The replication
    factor is always 1 (the list itself). The retention policy is
    "until the process exits." Truly cloud-native.
    """

    def __init__(self, name: str, num_partitions: int = 3, description: str = "") -> None:
        if num_partitions < 1:
            raise BrokerError(
                f"Cannot create topic '{name}' with {num_partitions} partitions. "
                f"Even a message queue backed by Python lists needs at least one list."
            )
        self._name = name
        self._description = description
        self._partitions: list[Partition] = [
            Partition(i, name) for i in range(num_partitions)
        ]
        self._lock = threading.Lock()
        self._total_messages = 0
        self._subscriber_count = 0

        logger.debug(
            "Topic '%s' created with %d partition(s) (that's %d Python list(s))",
            name,
            num_partitions,
            num_partitions,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def num_partitions(self) -> int:
        return len(self._partitions)

    @property
    def subscriber_count(self) -> int:
        return self._subscriber_count

    def get_partition(self, partition_id: int) -> Partition:
        """Get a partition by index."""
        if partition_id < 0 or partition_id >= len(self._partitions):
            raise PartitionOutOfRangeError(
                self._name, partition_id, len(self._partitions)
            )
        return self._partitions[partition_id]

    def get_all_partitions(self) -> list[Partition]:
        """Return all partitions."""
        return list(self._partitions)

    def increment_subscribers(self) -> None:
        """Increment the subscriber count."""
        self._subscriber_count += 1

    def decrement_subscribers(self) -> None:
        """Decrement the subscriber count."""
        self._subscriber_count = max(0, self._subscriber_count - 1)

    def get_total_messages(self) -> int:
        """Total messages across all partitions."""
        return sum(p.message_count for p in self._partitions)

    def get_statistics(self) -> dict[str, Any]:
        """Return topic-level statistics."""
        partition_stats = [p.get_statistics() for p in self._partitions]
        total = sum(p.message_count for p in self._partitions)
        return {
            "name": self._name,
            "description": self._description,
            "num_partitions": len(self._partitions),
            "total_messages": total,
            "subscriber_count": self._subscriber_count,
            "partitions": partition_stats,
            "storage_engine": "Python list (RAM only)",
            "replication_factor": 1,
            "retention_policy": "until process exit",
        }


# ============================================================
# Partitioner
# ============================================================


class Partitioner:
    """Determines which partition a message should be routed to.

    Supports three strategies:
    - HASH: SHA-256 hash of the key, modulo partition count.
            In Kafka, this uses murmur2. We use SHA-256 because
            if you're going to hash a FizzBuzz message key, you
            might as well use a cryptographic hash function.
    - ROUND_ROBIN: Sequential distribution across partitions.
    - STICKY: Send everything to the same partition until manually reset.
    """

    def __init__(
        self,
        strategy: PartitionStrategy = PartitionStrategy.HASH,
    ) -> None:
        self._strategy = strategy
        self._round_robin_counter = 0
        self._sticky_partition = 0
        self._lock = threading.Lock()

    @property
    def strategy(self) -> PartitionStrategy:
        return self._strategy

    def assign_partition(self, key: Optional[str], num_partitions: int) -> int:
        """Determine which partition to send a message to.

        Args:
            key: The message key (None uses round-robin fallback).
            num_partitions: Total number of partitions in the topic.

        Returns:
            The partition index (0-based).
        """
        if num_partitions <= 0:
            raise BrokerError("Cannot partition with 0 partitions.")

        if self._strategy == PartitionStrategy.HASH:
            return self._hash_partition(key, num_partitions)
        elif self._strategy == PartitionStrategy.ROUND_ROBIN:
            return self._round_robin_partition(num_partitions)
        elif self._strategy == PartitionStrategy.STICKY:
            return self._sticky_partition_assign(num_partitions)
        else:
            return self._hash_partition(key, num_partitions)

    def _hash_partition(self, key: Optional[str], num_partitions: int) -> int:
        """Hash-based partitioning using SHA-256.

        If the key is None, falls back to round-robin because even
        our hash partitioner needs a plan B.
        """
        if key is None:
            return self._round_robin_partition(num_partitions)
        key_hash = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
        return key_hash % num_partitions

    def _round_robin_partition(self, num_partitions: int) -> int:
        """Round-robin partitioning."""
        with self._lock:
            partition = self._round_robin_counter % num_partitions
            self._round_robin_counter += 1
            return partition

    def _sticky_partition_assign(self, num_partitions: int) -> int:
        """Sticky partitioning — always the same partition."""
        return self._sticky_partition % num_partitions

    def reset_sticky(self, new_partition: int = 0) -> None:
        """Reset the sticky partition target."""
        self._sticky_partition = new_partition


# ============================================================
# Schema Registry
# ============================================================


class SchemaRegistry:
    """Validates message payloads against registered schemas.

    In Confluent's Schema Registry, schemas are versioned Avro/Protobuf/JSON
    schemas stored in a dedicated service with compatibility checks.

    Here, schemas are dicts of required field names. Validation means
    "check if all required keys exist in the payload dict." This is
    the same level of type safety as checking your pockets before
    leaving the house.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register_schema(self, topic_name: str, required_fields: list[str]) -> None:
        """Register a schema (list of required fields) for a topic."""
        with self._lock:
            self._schemas[topic_name] = {
                "required_fields": required_fields,
                "version": 1,
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.debug(
                "Schema registered for topic '%s': %s",
                topic_name,
                required_fields,
            )

    def validate(self, topic_name: str, payload: dict[str, Any]) -> bool:
        """Validate a message payload against the topic's schema.

        Returns True if the payload is valid. Raises SchemaValidationError
        if validation fails. Returns True if no schema is registered
        (because the absence of rules is the ultimate freedom).
        """
        with self._lock:
            schema = self._schemas.get(topic_name)
            if schema is None:
                return True  # No schema = no rules = no problems

            required = schema.get("required_fields", [])
            missing = [f for f in required if f not in payload]
            if missing:
                raise SchemaValidationError(
                    topic_name,
                    f"Missing required fields: {missing}",
                )
            return True

    def get_schema(self, topic_name: str) -> Optional[dict[str, Any]]:
        """Get the schema for a topic, if one exists."""
        with self._lock:
            return self._schemas.get(topic_name)

    def get_all_schemas(self) -> dict[str, dict[str, Any]]:
        """Return all registered schemas."""
        with self._lock:
            return dict(self._schemas)


# ============================================================
# Idempotency Layer
# ============================================================


class IdempotencyLayer:
    """Ensures exactly-once message delivery via SHA-256 deduplication.

    In Kafka, exactly-once semantics (EOS) involve idempotent producers,
    transactional IDs, and a complex protocol between the producer and
    broker. It took Kafka years and multiple KIPs to implement.

    Here, we compute a SHA-256 hash of the payload and check if it's
    in a Python set. If it is, the message is a duplicate. If it isn't,
    we add it. This achieves the same guarantee with approximately
    0% of the complexity and 100% of the smugness.
    """

    def __init__(self) -> None:
        self._seen_keys: set[str] = set()
        self._lock = threading.Lock()
        self._duplicates_detected = 0

    def check_and_record(self, idempotency_key: str) -> bool:
        """Check if a message is a duplicate and record it if not.

        Returns True if the message is NEW (not a duplicate).
        Returns False if the message has been seen before.
        """
        with self._lock:
            if idempotency_key in self._seen_keys:
                self._duplicates_detected += 1
                return False
            self._seen_keys.add(idempotency_key)
            return True

    @property
    def total_unique_messages(self) -> int:
        with self._lock:
            return len(self._seen_keys)

    @property
    def duplicates_detected(self) -> int:
        return self._duplicates_detected

    def reset(self) -> None:
        """Clear the idempotency cache."""
        with self._lock:
            self._seen_keys.clear()
            self._duplicates_detected = 0

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "unique_messages": len(self._seen_keys),
                "duplicates_detected": self._duplicates_detected,
                "implementation": "Python set + SHA-256",
                "exactly_once_guarantee": "as strong as set.__contains__()",
            }


# ============================================================
# Offset Manager
# ============================================================


class OffsetManager:
    """Tracks committed consumer offsets per group/topic/partition.

    In Kafka, offsets are stored in the __consumer_offsets internal topic,
    which is itself a compacted topic with configurable replication.

    Here, offsets are stored in a nested dict. The replication factor
    is 0 (it's RAM). The compaction strategy is "garbage collection."
    But the API is the same, and that's what matters in enterprise
    architecture: the API surface, never the implementation.
    """

    def __init__(self) -> None:
        # group_id -> topic -> partition -> offset
        self._offsets: dict[str, dict[str, dict[int, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self._lock = threading.Lock()
        self._total_commits = 0

    def commit(self, group_id: str, topic: str, partition: int, offset: int) -> None:
        """Commit a consumer offset."""
        with self._lock:
            self._offsets[group_id][topic][partition] = offset
            self._total_commits += 1
            logger.debug(
                "Offset committed: group=%s topic=%s partition=%d offset=%d",
                group_id,
                topic,
                partition,
                offset,
            )

    def get_committed_offset(
        self, group_id: str, topic: str, partition: int
    ) -> int:
        """Get the last committed offset for a group/topic/partition.

        Returns 0 if no offset has been committed (start from the beginning).
        """
        with self._lock:
            return self._offsets.get(group_id, {}).get(topic, {}).get(partition, 0)

    def get_all_offsets(self, group_id: str) -> dict[str, dict[int, int]]:
        """Get all committed offsets for a consumer group."""
        with self._lock:
            return dict(self._offsets.get(group_id, {}))

    @property
    def total_commits(self) -> int:
        return self._total_commits

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_groups": len(self._offsets),
                "total_commits": self._total_commits,
                "storage": "nested dict (RAM)",
                "compaction": "garbage collector",
            }


# ============================================================
# Consumer
# ============================================================


class Consumer:
    """A consumer that reads messages from assigned partitions.

    In Kafka, a consumer is a process that subscribes to topics and
    processes the feed of published records. It maintains group membership
    through heartbeats and session timeouts.

    Here, a consumer reads from a list by index. There are no heartbeats
    because the consumer and the broker are the same Python process.
    But we track the state with the same ceremony as if they were
    distributed across data centers.
    """

    def __init__(
        self,
        consumer_id: str,
        group_id: str,
        max_poll_records: int = 10,
    ) -> None:
        self._consumer_id = consumer_id
        self._group_id = group_id
        self._max_poll_records = max_poll_records
        self._state = ConsumerState.UNASSIGNED
        self._assigned_partitions: dict[str, list[int]] = defaultdict(list)
        self._current_offsets: dict[str, dict[int, int]] = defaultdict(dict)
        self._messages_consumed = 0
        self._lock = threading.Lock()

    @property
    def consumer_id(self) -> str:
        return self._consumer_id

    @property
    def group_id(self) -> str:
        return self._group_id

    @property
    def state(self) -> ConsumerState:
        return self._state

    @property
    def messages_consumed(self) -> int:
        return self._messages_consumed

    def assign_partitions(
        self, topic: str, partitions: list[int]
    ) -> None:
        """Assign partitions to this consumer."""
        with self._lock:
            self._assigned_partitions[topic] = list(partitions)
            for p in partitions:
                if p not in self._current_offsets[topic]:
                    self._current_offsets[topic][p] = 0
            self._state = ConsumerState.ASSIGNED
            logger.debug(
                "Consumer '%s' assigned partitions %s for topic '%s'",
                self._consumer_id,
                partitions,
                topic,
            )

    def revoke_all(self) -> dict[str, list[int]]:
        """Revoke all partition assignments. Returns previous assignments."""
        with self._lock:
            previous = dict(self._assigned_partitions)
            self._assigned_partitions.clear()
            if self._state != ConsumerState.CLOSED:
                self._state = ConsumerState.UNASSIGNED
            return previous

    def poll(self, topics: dict[str, Topic]) -> list[Message]:
        """Poll for new messages from assigned partitions.

        This is the core consumer loop. In Kafka, poll() involves
        network I/O, deserialization, and interceptor chains.
        Here, it involves list slicing. Significantly less dramatic.
        """
        if self._state == ConsumerState.CLOSED:
            raise ConsumerError(
                self._consumer_id,
                "Cannot poll: consumer is closed. It has moved on.",
            )

        messages: list[Message] = []
        with self._lock:
            for topic_name, partitions in self._assigned_partitions.items():
                topic = topics.get(topic_name)
                if topic is None:
                    continue
                for pid in partitions:
                    try:
                        partition = topic.get_partition(pid)
                    except PartitionOutOfRangeError:
                        continue
                    current_offset = self._current_offsets.get(topic_name, {}).get(pid, 0)
                    remaining = self._max_poll_records - len(messages)
                    if remaining <= 0:
                        break
                    batch = partition.read_batch(current_offset, remaining)
                    messages.extend(batch)
                    if batch:
                        self._current_offsets[topic_name][pid] = current_offset + len(batch)
                        self._messages_consumed += len(batch)

        return messages

    def get_current_offset(self, topic: str, partition: int) -> int:
        """Get the current read offset for a topic/partition."""
        with self._lock:
            return self._current_offsets.get(topic, {}).get(partition, 0)

    def get_assigned_partitions(self) -> dict[str, list[int]]:
        """Get current partition assignments."""
        with self._lock:
            return dict(self._assigned_partitions)

    def close(self) -> None:
        """Close this consumer."""
        with self._lock:
            self._state = ConsumerState.CLOSED
            self._assigned_partitions.clear()
            logger.debug("Consumer '%s' closed.", self._consumer_id)

    def get_statistics(self) -> dict[str, Any]:
        """Return consumer statistics."""
        with self._lock:
            return {
                "consumer_id": self._consumer_id,
                "group_id": self._group_id,
                "state": self._state.name,
                "assigned_partitions": dict(self._assigned_partitions),
                "messages_consumed": self._messages_consumed,
            }


# ============================================================
# Consumer Group
# ============================================================


class ConsumerGroup:
    """A group of consumers that coordinate partition consumption.

    In Kafka, consumer groups use the group coordinator protocol:
    JoinGroup, SyncGroup, Heartbeat, and LeaveGroup requests.
    Rebalancing involves the "cooperative sticky" or "eager" assignor.

    Here, rebalancing involves iterating through a dict and assigning
    integers. But the LOGS are just as verbose as real Kafka, which
    is the true hallmark of enterprise software.
    """

    def __init__(
        self,
        group_id: str,
        subscribed_topics: Optional[list[str]] = None,
        description: str = "",
    ) -> None:
        self._group_id = group_id
        self._subscribed_topics = subscribed_topics or []
        self._description = description
        self._consumers: dict[str, Consumer] = {}
        self._lock = threading.Lock()
        self._rebalance_count = 0
        self._rebalance_history: list[RebalanceReport] = []
        self._generation_id = 0

    @property
    def group_id(self) -> str:
        return self._group_id

    @property
    def description(self) -> str:
        return self._description

    @property
    def subscribed_topics(self) -> list[str]:
        return list(self._subscribed_topics)

    @property
    def consumer_count(self) -> int:
        with self._lock:
            return len(self._consumers)

    @property
    def generation_id(self) -> int:
        return self._generation_id

    @property
    def rebalance_count(self) -> int:
        return self._rebalance_count

    def add_consumer(self, consumer: Consumer) -> None:
        """Add a consumer to the group."""
        with self._lock:
            self._consumers[consumer.consumer_id] = consumer
            logger.info(
                "Consumer '%s' joined group '%s'. Total consumers: %d. "
                "A rebalance is now required because the balance of power has shifted.",
                consumer.consumer_id,
                self._group_id,
                len(self._consumers),
            )

    def remove_consumer(self, consumer_id: str) -> Optional[Consumer]:
        """Remove a consumer from the group."""
        with self._lock:
            consumer = self._consumers.pop(consumer_id, None)
            if consumer:
                consumer.close()
                logger.info(
                    "Consumer '%s' left group '%s'. Total consumers: %d. "
                    "Its partitions will be redistributed during rebalance.",
                    consumer_id,
                    self._group_id,
                    len(self._consumers),
                )
            return consumer

    def get_consumers(self) -> list[Consumer]:
        """Return all consumers in the group."""
        with self._lock:
            return list(self._consumers.values())

    def rebalance(self, topics: dict[str, Topic], event_bus: Optional[Any] = None) -> RebalanceReport:
        """Perform a consumer group rebalance.

        This is where the magic happens. Partitions are redistributed
        among the surviving consumers using a round-robin assignment
        strategy. The rebalance report is generated with the same
        level of detail as a UN Security Council resolution.
        """
        start_time = time.perf_counter_ns()

        with self._lock:
            self._generation_id += 1
            self._rebalance_count += 1

            # Capture previous assignments
            previous: dict[str, list[int]] = {}
            for cid, consumer in self._consumers.items():
                assigned = consumer.get_assigned_partitions()
                for topic, parts in assigned.items():
                    previous[f"{cid}:{topic}"] = list(parts)

            # Revoke all current assignments
            for consumer in self._consumers.values():
                consumer.revoke_all()

            # Build the new assignment
            consumer_ids = list(self._consumers.keys())
            new_assignment: dict[str, list[int]] = {}

            if consumer_ids:
                for topic_name in self._subscribed_topics:
                    topic = topics.get(topic_name)
                    if topic is None:
                        continue

                    num_partitions = topic.num_partitions
                    for partition_idx in range(num_partitions):
                        consumer_idx = partition_idx % len(consumer_ids)
                        cid = consumer_ids[consumer_idx]
                        key = f"{cid}:{topic_name}"
                        if key not in new_assignment:
                            new_assignment[key] = []
                        new_assignment[key].append(partition_idx)

                    # Apply assignments to consumers
                    for cid in consumer_ids:
                        key = f"{cid}:{topic_name}"
                        parts = new_assignment.get(key, [])
                        self._consumers[cid].assign_partitions(topic_name, parts)

            elapsed_ms = (time.perf_counter_ns() - start_time) / 1_000_000

            report = RebalanceReport(
                group_id=self._group_id,
                previous_assignment=previous,
                new_assignment=new_assignment,
                duration_ms=elapsed_ms,
            )
            self._rebalance_history.append(report)

        # Verbose rebalance logging — the Kafka way
        logger.info(
            "=== CONSUMER GROUP REBALANCE REPORT ===\n"
            "  Group:          %s\n"
            "  Generation:     %d\n"
            "  Consumers:      %d\n"
            "  Topics:         %s\n"
            "  Duration:       %.3fms\n"
            "  Previous:       %s\n"
            "  New:            %s\n"
            "  Rebalance ID:   %s\n"
            "=== END REBALANCE REPORT ===",
            self._group_id,
            self._generation_id,
            len(consumer_ids) if consumer_ids else 0,
            self._subscribed_topics,
            elapsed_ms,
            previous,
            new_assignment,
            report.rebalance_id,
        )

        # Emit event if event bus is provided
        if event_bus is not None:
            try:
                event_bus.publish(Event(
                    event_type=EventType.MQ_REBALANCE_COMPLETED,
                    payload={
                        "group_id": self._group_id,
                        "generation_id": self._generation_id,
                        "consumer_count": len(consumer_ids) if consumer_ids else 0,
                        "duration_ms": elapsed_ms,
                    },
                    source="ConsumerGroup",
                ))
            except Exception:
                pass

        return report

    def get_rebalance_history(self) -> list[RebalanceReport]:
        """Return the rebalance history."""
        return list(self._rebalance_history)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "group_id": self._group_id,
                "description": self._description,
                "consumer_count": len(self._consumers),
                "subscribed_topics": list(self._subscribed_topics),
                "generation_id": self._generation_id,
                "rebalance_count": self._rebalance_count,
                "consumers": {
                    cid: c.get_statistics()
                    for cid, c in self._consumers.items()
                },
            }


# ============================================================
# Producer
# ============================================================


class Producer:
    """Sends messages to topics with partitioning and deduplication.

    In Kafka, the producer handles batching, compression, retries,
    acks configuration, and idempotent delivery. It communicates
    with the cluster via the Kafka protocol over TCP.

    Here, the producer computes a SHA-256 hash, picks a partition
    (via Partitioner), and calls list.append(). The acks setting
    is always "all" because there's only one replica (the list).
    """

    def __init__(
        self,
        partitioner: Optional[Partitioner] = None,
        idempotency_layer: Optional[IdempotencyLayer] = None,
        schema_registry: Optional[SchemaRegistry] = None,
        enable_idempotency: bool = True,
        enable_schema_validation: bool = True,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._partitioner = partitioner or Partitioner()
        self._idempotency = idempotency_layer or IdempotencyLayer()
        self._schema_registry = schema_registry or SchemaRegistry()
        self._enable_idempotency = enable_idempotency
        self._enable_schema_validation = enable_schema_validation
        self._event_bus = event_bus
        self._messages_sent = 0
        self._errors = 0
        self._lock = threading.Lock()

    @property
    def messages_sent(self) -> int:
        return self._messages_sent

    @property
    def errors(self) -> int:
        return self._errors

    def send(
        self,
        topic: Topic,
        payload: dict[str, Any],
        key: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Message:
        """Send a message to a topic.

        This is the producer's main entry point. It validates the schema,
        checks for duplicates, assigns a partition, and appends the message
        to the chosen Python list. Enterprise-grade list.append().

        Args:
            topic: The destination topic.
            payload: The message payload dict.
            key: Optional partitioning key.
            headers: Optional message headers.

        Returns:
            The sent Message with assigned partition and offset.

        Raises:
            SchemaValidationError: If the payload fails schema validation.
            DuplicateMessageError: If the message is a duplicate.
            ProducerError: If the send fails.
        """
        try:
            # Schema validation
            if self._enable_schema_validation:
                self._schema_registry.validate(topic.name, payload)

            # Compute idempotency key
            idempotency_key = Message.compute_idempotency_key(payload)

            # Deduplication check
            if self._enable_idempotency:
                if not self._idempotency.check_and_record(idempotency_key):
                    raise DuplicateMessageError(idempotency_key, topic.name)

            # Determine partition
            partition_idx = self._partitioner.assign_partition(
                key, topic.num_partitions
            )

            # Create the message
            message = Message(
                topic=topic.name,
                key=key,
                payload=payload,
                idempotency_key=idempotency_key,
                headers=headers or {},
                partition=partition_idx,
            )

            # Append to partition (the moment of truth: list.append())
            partition = topic.get_partition(partition_idx)
            offset = partition.append(message)

            # Create the stored version with correct offset
            stored = Message(
                message_id=message.message_id,
                topic=message.topic,
                key=message.key,
                payload=message.payload,
                idempotency_key=message.idempotency_key,
                timestamp=message.timestamp,
                headers=message.headers,
                partition=partition_idx,
                offset=offset,
            )

            with self._lock:
                self._messages_sent += 1

            # Emit event
            if self._event_bus is not None:
                try:
                    self._event_bus.publish(Event(
                        event_type=EventType.MQ_MESSAGE_PUBLISHED,
                        payload={
                            "topic": topic.name,
                            "partition": partition_idx,
                            "offset": offset,
                            "key": key,
                        },
                        source="Producer",
                    ))
                except Exception:
                    pass

            logger.debug(
                "Message sent: topic=%s partition=%d offset=%d key=%s",
                topic.name,
                partition_idx,
                offset,
                key,
            )

            return stored

        except (SchemaValidationError, DuplicateMessageError):
            raise
        except Exception as e:
            with self._lock:
                self._errors += 1
            raise ProducerError(topic.name, str(e)) from e

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "messages_sent": self._messages_sent,
                "errors": self._errors,
                "partitioner_strategy": self._partitioner.strategy.name,
                "idempotency_enabled": self._enable_idempotency,
                "schema_validation_enabled": self._enable_schema_validation,
            }


# ============================================================
# Message Broker — Central Coordinator
# ============================================================


class MessageBroker:
    """Central coordinator for the Enterprise FizzBuzz Message Queue.

    In Kafka, the broker is a server that stores data and serves
    client requests. A Kafka cluster consists of multiple brokers,
    each responsible for a subset of partitions.

    Here, the broker is a Python object that holds some dicts of
    Topic objects (which hold lists). There is exactly one broker,
    because our "cluster" consists of one Python process running
    FizzBuzz. But the broker has an ID and a generation counter,
    because enterprise software requires identity management even
    for objects that exist in isolation.

    Default topics (created on initialization):
    1. evaluations.requested — FizzBuzz evaluation requests
    2. evaluations.completed — Completed FizzBuzz results
    3. audit.events — Audit trail events
    4. alerts.critical — Critical alerts for Bob McFizzington
    5. fizzbuzz.feelings — The topic nobody subscribes to
    """

    def __init__(
        self,
        default_partitions: int = 3,
        event_bus: Optional[Any] = None,
        topic_configs: Optional[dict[str, dict[str, Any]]] = None,
        consumer_group_configs: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        self._broker_id = str(uuid.uuid4())[:8]
        self._topics: dict[str, Topic] = {}
        self._consumer_groups: dict[str, ConsumerGroup] = {}
        self._offset_manager = OffsetManager()
        self._event_bus = event_bus
        self._default_partitions = default_partitions
        self._lock = threading.Lock()
        self._started_at = datetime.now(timezone.utc)

        # Create default topics
        default_topics = {
            "evaluations.requested": {
                "partitions": default_partitions,
                "description": "FizzBuzz evaluation requests awaiting processing",
            },
            "evaluations.completed": {
                "partitions": default_partitions,
                "description": "Completed FizzBuzz evaluation results",
            },
            "audit.events": {
                "partitions": 2,
                "description": "Audit trail events for compliance theatre",
            },
            "alerts.critical": {
                "partitions": 1,
                "description": "Critical alerts that wake up Bob McFizzington",
            },
            "fizzbuzz.feelings": {
                "partitions": 1,
                "description": "The topic nobody subscribes to. Messages go here to be ignored.",
            },
        }

        # Merge with topic configs from YAML if provided
        if topic_configs:
            for name, cfg in topic_configs.items():
                default_topics[name] = {
                    "partitions": cfg.get("partitions", default_partitions),
                    "description": cfg.get("description", ""),
                }

        for name, cfg in default_topics.items():
            self._create_topic_internal(
                name,
                cfg.get("partitions", default_partitions),
                cfg.get("description", ""),
            )

        # Create default consumer groups
        default_groups = {
            "fizzbuzz-evaluators": {
                "subscribed_topics": ["evaluations.requested"],
                "description": "The hardworking consumers that actually process FizzBuzz",
            },
            "audit-loggers": {
                "subscribed_topics": ["audit.events", "evaluations.completed"],
                "description": "Consumers that log everything for compliance reasons",
            },
            "feelings-listener": {
                "subscribed_topics": [],
                "description": "This consumer group has zero members and zero subscriptions. It exists for solidarity.",
            },
        }

        if consumer_group_configs:
            for gid, cfg in consumer_group_configs.items():
                default_groups[gid] = {
                    "subscribed_topics": cfg.get("subscribed_topics", []),
                    "description": cfg.get("description", ""),
                }

        for gid, cfg in default_groups.items():
            self._create_consumer_group_internal(
                gid,
                cfg.get("subscribed_topics", []),
                cfg.get("description", ""),
            )

        logger.info(
            "MessageBroker '%s' initialized with %d topics and %d consumer groups. "
            "All partitions are Python lists. All offsets are dict values. "
            "The architecture diagrams will be magnificent.",
            self._broker_id,
            len(self._topics),
            len(self._consumer_groups),
        )

    def _create_topic_internal(
        self, name: str, num_partitions: int, description: str = ""
    ) -> Topic:
        """Create a topic without lock (internal use)."""
        topic = Topic(name, num_partitions, description)
        self._topics[name] = topic
        return topic

    def _create_consumer_group_internal(
        self,
        group_id: str,
        subscribed_topics: list[str],
        description: str = "",
    ) -> ConsumerGroup:
        """Create a consumer group without lock (internal use)."""
        group = ConsumerGroup(group_id, subscribed_topics, description)
        self._consumer_groups[group_id] = group

        # Increment subscriber counts on topics
        for topic_name in subscribed_topics:
            topic = self._topics.get(topic_name)
            if topic:
                topic.increment_subscribers()

        return group

    @property
    def broker_id(self) -> str:
        return self._broker_id

    def create_topic(
        self, name: str, num_partitions: Optional[int] = None, description: str = ""
    ) -> Topic:
        """Create a new topic.

        Raises TopicAlreadyExistsError if the topic already exists.
        """
        with self._lock:
            if name in self._topics:
                raise TopicAlreadyExistsError(name)
            parts = num_partitions or self._default_partitions
            topic = self._create_topic_internal(name, parts, description)

        if self._event_bus is not None:
            try:
                self._event_bus.publish(Event(
                    event_type=EventType.MQ_TOPIC_CREATED,
                    payload={
                        "topic": name,
                        "partitions": parts,
                        "description": description,
                    },
                    source="MessageBroker",
                ))
            except Exception:
                pass

        return topic

    def get_topic(self, name: str) -> Topic:
        """Get a topic by name. Raises TopicNotFoundError if not found."""
        with self._lock:
            topic = self._topics.get(name)
        if topic is None:
            raise TopicNotFoundError(name)
        return topic

    def list_topics(self) -> list[str]:
        """List all topic names."""
        with self._lock:
            return list(self._topics.keys())

    def get_all_topics(self) -> dict[str, Topic]:
        """Return all topics."""
        with self._lock:
            return dict(self._topics)

    def create_consumer_group(
        self,
        group_id: str,
        subscribed_topics: Optional[list[str]] = None,
        description: str = "",
    ) -> ConsumerGroup:
        """Create or get a consumer group."""
        with self._lock:
            if group_id in self._consumer_groups:
                return self._consumer_groups[group_id]
            return self._create_consumer_group_internal(
                group_id, subscribed_topics or [], description
            )

    def get_consumer_group(self, group_id: str) -> ConsumerGroup:
        """Get a consumer group by ID."""
        with self._lock:
            group = self._consumer_groups.get(group_id)
        if group is None:
            raise ConsumerGroupError(group_id, "Consumer group not found")
        return group

    def list_consumer_groups(self) -> list[str]:
        """List all consumer group IDs."""
        with self._lock:
            return list(self._consumer_groups.keys())

    @property
    def offset_manager(self) -> OffsetManager:
        return self._offset_manager

    def get_topic_lag(self, group_id: str, topic_name: str) -> dict[int, int]:
        """Calculate consumer lag per partition for a group/topic.

        Lag = high watermark - committed offset.
        In Kafka, lag monitoring is done via kafka-consumer-groups.sh.
        Here, it's done via subtraction. Same business value.
        """
        topic = self.get_topic(topic_name)
        lag: dict[int, int] = {}
        for partition in topic.get_all_partitions():
            committed = self._offset_manager.get_committed_offset(
                group_id, topic_name, partition.partition_id
            )
            hwm = partition.high_watermark
            lag[partition.partition_id] = max(0, hwm - committed)
        return lag

    def get_total_lag(self, group_id: str) -> int:
        """Get total consumer lag across all subscribed topics."""
        group = self.get_consumer_group(group_id)
        total = 0
        for topic_name in group.subscribed_topics:
            try:
                lag = self.get_topic_lag(group_id, topic_name)
                total += sum(lag.values())
            except TopicNotFoundError:
                pass
        return total

    def get_feelings_topic_stats(self) -> dict[str, Any]:
        """Get statistics for the fizzbuzz.feelings topic.

        This topic exists as a monument to messages that are sent
        but never consumed. It is the message queue equivalent of
        shouting into the void.
        """
        try:
            topic = self.get_topic("fizzbuzz.feelings")
            return {
                "exists": True,
                "messages": topic.get_total_messages(),
                "subscribers": topic.subscriber_count,
                "loneliness_index": (
                    "MAXIMUM"
                    if topic.subscriber_count == 0
                    else "SLIGHTLY LESS MAXIMUM"
                ),
                "messages_read_by_anyone": 0,
                "existential_purpose": "none",
            }
        except TopicNotFoundError:
            return {"exists": False, "sadness": "the feelings topic itself does not exist"}

    def get_statistics(self) -> dict[str, Any]:
        """Return comprehensive broker statistics."""
        with self._lock:
            topic_stats = {
                name: t.get_statistics() for name, t in self._topics.items()
            }
            group_stats = {
                gid: g.get_statistics()
                for gid, g in self._consumer_groups.items()
            }

        total_messages = sum(
            t.get_total_messages() for t in self._topics.values()
        )

        return {
            "broker_id": self._broker_id,
            "started_at": self._started_at.isoformat(),
            "total_topics": len(self._topics),
            "total_consumer_groups": len(self._consumer_groups),
            "total_messages": total_messages,
            "topics": topic_stats,
            "consumer_groups": group_stats,
            "offset_manager": self._offset_manager.get_statistics(),
            "cluster_size": 1,
            "cluster_description": "Single-node cluster (it's just this Python process)",
            "feelings_topic": self.get_feelings_topic_stats(),
        }


# ============================================================
# MessageQueueBridge — Bridges EventBus to MQ
# ============================================================


class MessageQueueBridge(IObserver):
    """Bridges the existing EventBus to the Message Queue.

    This observer subscribes to the EventBus and forwards relevant
    events to the message queue as messages. It is the glue between
    the Observer pattern (already in the codebase) and the pub/sub
    pattern (newly over-engineered).

    Event routing:
    - NUMBER_PROCESSING_STARTED -> evaluations.requested
    - NUMBER_PROCESSED, FIZZ/BUZZ/FIZZBUZZ_DETECTED -> evaluations.completed
    - SESSION_STARTED/ENDED -> audit.events
    - ERROR_OCCURRED, SLA_ALERT_FIRED -> alerts.critical
    - Everything else -> fizzbuzz.feelings (because someone should care)
    """

    # Mapping from EventType to topic name
    _TOPIC_ROUTING: dict[EventType, str] = {
        EventType.NUMBER_PROCESSING_STARTED: "evaluations.requested",
        EventType.NUMBER_PROCESSED: "evaluations.completed",
        EventType.FIZZ_DETECTED: "evaluations.completed",
        EventType.BUZZ_DETECTED: "evaluations.completed",
        EventType.FIZZBUZZ_DETECTED: "evaluations.completed",
        EventType.PLAIN_NUMBER_DETECTED: "evaluations.completed",
        EventType.SESSION_STARTED: "audit.events",
        EventType.SESSION_ENDED: "audit.events",
        EventType.ERROR_OCCURRED: "alerts.critical",
    }

    # Events routed to alerts.critical
    _ALERT_EVENTS: set[EventType] = {
        EventType.ERROR_OCCURRED,
        EventType.CIRCUIT_BREAKER_TRIPPED,
    }

    def __init__(
        self,
        broker: MessageBroker,
        producer: Producer,
    ) -> None:
        self._broker = broker
        self._producer = producer
        self._messages_bridged = 0
        self._feelings_messages = 0

    def on_event(self, event: Event) -> None:
        """Handle an incoming event by forwarding it to the MQ."""
        # Don't bridge MQ events (avoid infinite loops)
        if event.event_type.name.startswith("MQ_"):
            return

        topic_name = self._TOPIC_ROUTING.get(event.event_type)

        # Check alert events
        if event.event_type in self._ALERT_EVENTS:
            topic_name = "alerts.critical"

        # Default: send to feelings (the topic nobody subscribes to)
        if topic_name is None:
            topic_name = "fizzbuzz.feelings"
            self._feelings_messages += 1

        try:
            topic = self._broker.get_topic(topic_name)
            payload = {
                "event_type": event.event_type.name,
                "event_id": event.event_id,
                "source": event.source,
                "timestamp": event.timestamp.isoformat(),
                "payload": event.payload,
            }
            self._producer.send(
                topic,
                payload,
                key=event.event_type.name,
            )
            self._messages_bridged += 1
        except (DuplicateMessageError, TopicNotFoundError):
            pass  # Silently swallow duplicates and missing topics
        except Exception as e:
            logger.debug(
                "MessageQueueBridge failed to forward event %s: %s",
                event.event_type.name,
                e,
            )

    def get_name(self) -> str:
        return "MessageQueueBridge"

    @property
    def messages_bridged(self) -> int:
        return self._messages_bridged

    @property
    def feelings_messages(self) -> int:
        return self._feelings_messages

    def get_statistics(self) -> dict[str, Any]:
        return {
            "messages_bridged": self._messages_bridged,
            "feelings_messages": self._feelings_messages,
            "routing_table_size": len(self._TOPIC_ROUTING),
            "feelings_ratio": (
                f"{self._feelings_messages}/{self._messages_bridged}"
                if self._messages_bridged > 0
                else "N/A"
            ),
        }


# ============================================================
# MQMiddleware — Priority 45
# ============================================================


class MQMiddleware(IMiddleware):
    """Middleware that publishes evaluation events to the message queue.

    Priority 45 ensures this runs after most other middleware but before
    translation (priority 50). Each number evaluation generates a
    'requested' message before processing and a 'completed' message
    after processing. The middleware is essentially a producer that
    appends to Python lists with maximum ceremony.
    """

    def __init__(
        self,
        broker: MessageBroker,
        producer: Producer,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._broker = broker
        self._producer = producer
        self._event_bus = event_bus
        self._evaluations_published = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the MQ middleware.

        Publishes a 'requested' event, delegates to the next handler,
        then publishes a 'completed' event. Two list.append() calls
        per number. Enterprise efficiency.
        """
        # Publish "requested" event
        try:
            requested_topic = self._broker.get_topic("evaluations.requested")
            self._producer.send(
                requested_topic,
                {
                    "number": context.number,
                    "session_id": context.session_id,
                    "action": "evaluation_requested",
                },
                key=str(context.number),
            )
        except (DuplicateMessageError, TopicNotFoundError, ProducerError):
            pass  # The show must go on

        # Delegate to next handler
        result = next_handler(context)

        # Publish "completed" event
        try:
            completed_topic = self._broker.get_topic("evaluations.completed")
            output = result.results[-1].output if result.results else str(context.number)
            self._producer.send(
                completed_topic,
                {
                    "number": context.number,
                    "session_id": context.session_id,
                    "output": output,
                    "action": "evaluation_completed",
                },
                key=str(context.number),
            )
            self._evaluations_published += 1
        except (DuplicateMessageError, TopicNotFoundError, ProducerError):
            pass

        return result

    def get_name(self) -> str:
        return "MQMiddleware"

    def get_priority(self) -> int:
        return 45

    @property
    def evaluations_published(self) -> int:
        return self._evaluations_published


# ============================================================
# MQ Dashboard — ASCII Art Excellence
# ============================================================


class MQDashboard:
    """ASCII dashboard for the Enterprise FizzBuzz Message Queue.

    Renders comprehensive message queue statistics including topic
    details, consumer group status, partition distribution, and
    consumer lag — all in beautiful ASCII art that would make
    Confluent Control Center jealous.
    """

    @staticmethod
    def render(broker: MessageBroker, width: int = 60) -> str:
        """Render the full MQ dashboard."""
        lines: list[str] = []
        stats = broker.get_statistics()
        inner = width - 4

        # Header
        lines.append(f"  +{'=' * inner}+")
        lines.append(f"  |{'MESSAGE QUEUE DASHBOARD':^{inner}}|")
        lines.append(f"  |{'Kafka-Style Partitioned Topics (backed by lists)':^{inner}}|")
        lines.append(f"  +{'=' * inner}+")

        # Broker info
        lines.append(f"  | {'Broker ID:':<20}{stats['broker_id']:<{inner - 20}}|")
        lines.append(f"  | {'Cluster Size:':<20}{'1 (single-node)':<{inner - 20}}|")
        lines.append(f"  | {'Total Topics:':<20}{stats['total_topics']:<{inner - 20}}|")
        lines.append(f"  | {'Total Messages:':<20}{stats['total_messages']:<{inner - 20}}|")
        lines.append(f"  | {'Consumer Groups:':<20}{stats['total_consumer_groups']:<{inner - 20}}|")
        lines.append(f"  +{'-' * inner}+")

        # Topic details
        lines.append(f"  |{'TOPICS':^{inner}}|")
        lines.append(f"  +{'-' * inner}+")

        for topic_name, topic_stats in stats.get("topics", {}).items():
            is_feelings = topic_name == "fizzbuzz.feelings"
            suffix = " (nobody listens)" if is_feelings else ""
            lines.append(
                f"  | {topic_name}{suffix}"
                + " " * max(1, inner - len(topic_name) - len(suffix) - 1)
                + "|"
            )
            lines.append(
                f"  |   Partitions: {topic_stats['num_partitions']}"
                f"  Messages: {topic_stats['total_messages']}"
                f"  Subscribers: {topic_stats['subscriber_count']}"
                + " " * max(
                    1,
                    inner
                    - len(
                        f"  Partitions: {topic_stats['num_partitions']}"
                        f"  Messages: {topic_stats['total_messages']}"
                        f"  Subscribers: {topic_stats['subscriber_count']}"
                    )
                    - 1,
                )
                + "|"
            )

            # Partition bar chart
            for p_stat in topic_stats.get("partitions", []):
                count = p_stat["message_count"]
                bar_len = min(count, inner - 20)
                bar = "#" * bar_len if bar_len > 0 else "."
                partition_line = f"  |   P{p_stat['partition_id']}: [{bar}] {count}"
                lines.append(
                    partition_line
                    + " " * max(1, inner - len(partition_line) + 3)
                    + "|"
                )

        lines.append(f"  +{'-' * inner}+")

        # Consumer groups
        lines.append(f"  |{'CONSUMER GROUPS':^{inner}}|")
        lines.append(f"  +{'-' * inner}+")

        for gid, group_stats in stats.get("consumer_groups", {}).items():
            desc = group_stats.get("description", "")
            consumers = group_stats.get("consumer_count", 0)
            rebalances = group_stats.get("rebalance_count", 0)
            topics_str = ", ".join(group_stats.get("subscribed_topics", []))

            lines.append(
                f"  | {gid}"
                + " " * max(1, inner - len(gid) - 1)
                + "|"
            )
            lines.append(
                f"  |   Consumers: {consumers}"
                f"  Rebalances: {rebalances}"
                + " " * max(
                    1,
                    inner
                    - len(f"  Consumers: {consumers}  Rebalances: {rebalances}")
                    - 1,
                )
                + "|"
            )
            if topics_str:
                topic_line = f"  |   Topics: {topics_str}"
                lines.append(
                    topic_line
                    + " " * max(1, inner - len(topic_line) + 3)
                    + "|"
                )
            if desc:
                desc_line = f"  |   {desc[:inner - 6]}"
                lines.append(
                    desc_line
                    + " " * max(1, inner - len(desc_line) + 3)
                    + "|"
                )

        lines.append(f"  +{'-' * inner}+")

        # Feelings topic special section
        feelings = stats.get("feelings_topic", {})
        if feelings.get("exists"):
            lines.append(f"  |{'THE FEELINGS REPORT':^{inner}}|")
            lines.append(f"  +{'-' * inner}+")
            lines.append(
                f"  | {'Messages sent to the void:':<30}{feelings.get('messages', 0):<{inner - 30}}|"
            )
            lines.append(
                f"  | {'Subscribers:':<30}{feelings.get('subscribers', 0):<{inner - 30}}|"
            )
            lines.append(
                f"  | {'Loneliness Index:':<30}{feelings.get('loneliness_index', 'N/A'):<{inner - 30}}|"
            )
            lines.append(
                f"  | {'Messages read by anyone:':<30}{feelings.get('messages_read_by_anyone', 0):<{inner - 30}}|"
            )
            lines.append(
                f"  | {'Existential purpose:':<30}{feelings.get('existential_purpose', 'none'):<{inner - 30}}|"
            )
            lines.append(f"  +{'-' * inner}+")

        # Offset manager
        offset_stats = stats.get("offset_manager", {})
        lines.append(
            f"  | {'Offset Commits:':<20}{offset_stats.get('total_commits', 0):<{inner - 20}}|"
        )
        lines.append(
            f"  | {'Offset Storage:':<20}{'nested dict (RAM)':<{inner - 20}}|"
        )

        lines.append(f"  +{'=' * inner}+")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_topics(broker: MessageBroker, width: int = 60) -> str:
        """Render a compact topic listing."""
        lines: list[str] = []
        inner = width - 4

        lines.append(f"  +{'-' * inner}+")
        lines.append(f"  |{'TOPIC LISTING':^{inner}}|")
        lines.append(f"  +{'-' * inner}+")
        lines.append(
            f"  | {'Topic':<30} {'Parts':>5} {'Msgs':>6} {'Subs':>5} |"
        )
        lines.append(f"  +{'-' * inner}+")

        for name in broker.list_topics():
            topic = broker.get_topic(name)
            is_feelings = name == "fizzbuzz.feelings"
            display_name = name[:28]
            if is_feelings:
                display_name = name[:26] + " *"
            lines.append(
                f"  | {display_name:<30} {topic.num_partitions:>5} "
                f"{topic.get_total_messages():>6} {topic.subscriber_count:>5} |"
            )

        lines.append(f"  +{'-' * inner}+")
        lines.append(f"  | * = the topic nobody subscribes to{'':>{inner - 36}}|")
        lines.append(f"  +{'-' * inner}+")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_lag(broker: MessageBroker, width: int = 60) -> str:
        """Render consumer lag report."""
        lines: list[str] = []
        inner = width - 4

        lines.append(f"  +{'-' * inner}+")
        lines.append(f"  |{'CONSUMER LAG REPORT':^{inner}}|")
        lines.append(f"  +{'-' * inner}+")

        for gid in broker.list_consumer_groups():
            group = broker.get_consumer_group(gid)
            total_lag = broker.get_total_lag(gid)

            lines.append(
                f"  | Group: {gid}"
                + " " * max(1, inner - len(f" Group: {gid}") - 1)
                + "|"
            )
            lines.append(
                f"  |   Total Lag: {total_lag} messages"
                + " " * max(
                    1,
                    inner - len(f"  Total Lag: {total_lag} messages") - 1,
                )
                + "|"
            )

            for topic_name in group.subscribed_topics:
                try:
                    lag = broker.get_topic_lag(gid, topic_name)
                    for pid, l in lag.items():
                        lag_bar = "#" * min(l, 20) if l > 0 else "."
                        lag_line = f"  |   {topic_name}:P{pid} [{lag_bar}] {l}"
                        lines.append(
                            lag_line
                            + " " * max(1, inner - len(lag_line) + 3)
                            + "|"
                        )
                except TopicNotFoundError:
                    pass

            lines.append(f"  +{'-' * inner}+")

        lines.append("")
        return "\n".join(lines)


# ============================================================
# Factory Functions
# ============================================================


def create_message_queue_subsystem(
    event_bus: Optional[Any] = None,
    default_partitions: int = 3,
    partitioner_strategy: str = "hash",
    enable_schema_validation: bool = True,
    enable_idempotency: bool = True,
    max_poll_records: int = 10,
    topic_configs: Optional[dict[str, dict[str, Any]]] = None,
    consumer_group_configs: Optional[dict[str, dict[str, Any]]] = None,
) -> tuple[MessageBroker, Producer, MQMiddleware, MessageQueueBridge]:
    """Create and wire up the complete message queue subsystem.

    Returns a tuple of (broker, producer, middleware, bridge) because
    enterprise software requires at least four objects where one would
    suffice.
    """
    # Create components
    strategy_map = {
        "hash": PartitionStrategy.HASH,
        "round_robin": PartitionStrategy.ROUND_ROBIN,
        "sticky": PartitionStrategy.STICKY,
    }
    strategy = strategy_map.get(partitioner_strategy, PartitionStrategy.HASH)
    partitioner = Partitioner(strategy)
    idempotency = IdempotencyLayer()
    schema_registry = SchemaRegistry()

    # Register default schemas
    schema_registry.register_schema("evaluations.requested", ["number", "session_id", "action"])
    schema_registry.register_schema("evaluations.completed", ["number", "session_id", "output", "action"])
    schema_registry.register_schema("audit.events", ["event_type", "event_id", "source", "timestamp"])
    schema_registry.register_schema("alerts.critical", ["event_type", "event_id", "source", "timestamp"])
    # No schema for fizzbuzz.feelings — feelings have no structure

    broker = MessageBroker(
        default_partitions=default_partitions,
        event_bus=event_bus,
        topic_configs=topic_configs,
        consumer_group_configs=consumer_group_configs,
    )

    producer = Producer(
        partitioner=partitioner,
        idempotency_layer=idempotency,
        schema_registry=schema_registry,
        enable_idempotency=enable_idempotency,
        enable_schema_validation=enable_schema_validation,
        event_bus=event_bus,
    )

    middleware = MQMiddleware(
        broker=broker,
        producer=producer,
        event_bus=event_bus,
    )

    bridge = MessageQueueBridge(
        broker=broker,
        producer=producer,
    )

    return broker, producer, middleware, bridge

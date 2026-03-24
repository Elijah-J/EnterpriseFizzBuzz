"""
Enterprise FizzBuzz Platform - Message Queue & Event Bus Exceptions (EFP-MQ00 through EFP-MQ12)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class MessageQueueError(FizzBuzzError):
    """Base exception for all Message Queue subsystem errors.

    The fact that the "message queue" is backed by Python lists
    does not diminish the severity of these exceptions. A list
    append failure is every bit as catastrophic as a Kafka broker
    going down, provided you squint hard enough and have
    sufficiently low standards for catastrophe.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-MQ00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TopicNotFoundError(MessageQueueError):
    """Raised when a message is published to a topic that does not exist.

    In Kafka, this would mean the topic was never created or was deleted.
    Here, it means someone misspelled 'evaluations.requested' and the
    dict lookup returned None. The production impact is identical.
    """

    def __init__(self, topic_name: str) -> None:
        super().__init__(
            f"Topic '{topic_name}' does not exist. Available topics can be "
            f"listed with --mq-topics. Perhaps you meant 'fizzbuzz.feelings'? "
            f"Nobody subscribes to that one either.",
            error_code="EFP-MQ01",
            context={"topic_name": topic_name},
        )


class PartitionOutOfRangeError(MessageQueueError):
    """Raised when a partition index exceeds the topic's partition count.

    The partition is a Python list. The index is out of range. This is
    an IndexError wearing a Kafka costume, and it is NOT apologizing.
    """

    def __init__(self, topic_name: str, partition: int, max_partitions: int) -> None:
        super().__init__(
            f"Partition {partition} does not exist in topic '{topic_name}' "
            f"(valid range: 0-{max_partitions - 1}). The list is shorter "
            f"than you expected. This is not a distributed systems problem.",
            error_code="EFP-MQ02",
            context={
                "topic_name": topic_name,
                "partition": partition,
                "max_partitions": max_partitions,
            },
        )


class ConsumerGroupError(MessageQueueError):
    """Raised when a consumer group operation fails.

    Consumer groups coordinate multiple consumers reading from the
    same topic without duplicating work. In Kafka, this involves
    a group coordinator, heartbeats, and session timeouts. Here,
    it involves a Python dict and some very earnest logging.
    """

    def __init__(self, group_id: str, reason: str) -> None:
        super().__init__(
            f"Consumer group '{group_id}' error: {reason}. "
            f"The group coordinator (a dict) is disappointed.",
            error_code="EFP-MQ03",
            context={"group_id": group_id},
        )


class OffsetOutOfRangeError(MessageQueueError):
    """Raised when a consumer attempts to read from an invalid offset.

    The offset is an integer index into a Python list. If the offset
    exceeds len(list), you have reached the end of the universe —
    or at least the end of the list, which in this context is the same thing.
    """

    def __init__(self, topic_name: str, partition: int, offset: int, max_offset: int) -> None:
        super().__init__(
            f"Offset {offset} is out of range for topic '{topic_name}' "
            f"partition {partition} (max: {max_offset}). You have attempted "
            f"to read beyond the end of a Python list. This is both a "
            f"technical error and a philosophical overreach.",
            error_code="EFP-MQ04",
            context={
                "topic_name": topic_name,
                "partition": partition,
                "offset": offset,
                "max_offset": max_offset,
            },
        )


class SchemaValidationError(MessageQueueError):
    """Raised when a message payload fails schema validation.

    The Schema Registry ensures that all messages conform to the
    expected structure, because publishing unvalidated JSON to a
    Python list would be anarchy. Enterprise anarchy.
    """

    def __init__(self, topic_name: str, reason: str) -> None:
        super().__init__(
            f"Schema validation failed for topic '{topic_name}': {reason}. "
            f"The Schema Registry (a dict of required keys) has spoken.",
            error_code="EFP-MQ05",
            context={"topic_name": topic_name, "reason": reason},
        )


class DuplicateMessageError(MessageQueueError):
    """Raised when a duplicate message is detected by the idempotency layer.

    Exactly-once delivery is guaranteed by computing a SHA-256 hash of
    the message payload and checking it against a Python set. If the
    hash already exists, the message is a duplicate. This is the same
    approach used by distributed streaming platforms, except they use
    distributed hash tables and we use set.__contains__().
    """

    def __init__(self, idempotency_key: str, topic_name: str) -> None:
        super().__init__(
            f"Duplicate message detected on topic '{topic_name}' "
            f"(idempotency key: {idempotency_key[:16]}...). Exactly-once "
            f"delivery has been preserved. The SHA-256 set is vigilant.",
            error_code="EFP-MQ06",
            context={"idempotency_key": idempotency_key, "topic_name": topic_name},
        )


class ProducerError(MessageQueueError):
    """Raised when the message producer fails to send a message.

    In Kafka, this could be caused by network partitions, broker
    failures, or insufficient replicas. Here, it means list.append()
    raised an exception, which would require truly extraordinary
    circumstances — like running out of memory while processing
    FizzBuzz, a scenario that demands immediate post-mortem analysis.
    """

    def __init__(self, topic_name: str, reason: str) -> None:
        super().__init__(
            f"Producer failed to send message to topic '{topic_name}': {reason}. "
            f"list.append() has betrayed us.",
            error_code="EFP-MQ07",
            context={"topic_name": topic_name},
        )


class ConsumerError(MessageQueueError):
    """Raised when a consumer fails to process a message.

    Message consumption involves reading from a list by index.
    If this fails, the consumer is in a state of existential crisis
    that no amount of offset management can resolve.
    """

    def __init__(self, consumer_id: str, reason: str) -> None:
        super().__init__(
            f"Consumer '{consumer_id}' error: {reason}. "
            f"The consumer has lost its way in the list.",
            error_code="EFP-MQ08",
            context={"consumer_id": consumer_id},
        )


class RebalanceError(MessageQueueError):
    """Raised when consumer group rebalancing fails.

    Rebalancing redistributes partitions among consumers in a group.
    In Kafka, this is a complex protocol involving the group coordinator.
    Here, it involves reassigning integers to dict keys, which can still
    fail if you try hard enough and believe in yourself.
    """

    def __init__(self, group_id: str, reason: str) -> None:
        super().__init__(
            f"Rebalance failed for consumer group '{group_id}': {reason}. "
            f"The partition assignment (a dict) could not reach consensus.",
            error_code="EFP-MQ09",
            context={"group_id": group_id},
        )


class BrokerError(MessageQueueError):
    """Raised when the message broker encounters an operational error.

    The MessageBroker is the central coordinator for all topics,
    partitions, and consumer groups. It is a Python object that
    lives in RAM for less than one second, but its operational
    integrity is paramount. Enterprise paramount.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Message broker error: {reason}. The broker (a Python object) "
            f"is experiencing difficulties. Please check its feelings.",
            error_code="EFP-MQ10",
            context={},
        )


class TopicAlreadyExistsError(MessageQueueError):
    """Raised when attempting to create a topic that already exists.

    Topic names are unique. Creating a topic that already exists
    would violate the uniqueness constraint of the message queue
    namespace, which is not permitted.
    """

    def __init__(self, topic_name: str) -> None:
        super().__init__(
            f"Topic '{topic_name}' already exists. Topic names are unique "
            f"in this enterprise message queue, just as they are in the real "
            f"Kafka clusters that inspired this abstraction layer.",
            error_code="EFP-MQ11",
            context={"topic_name": topic_name},
        )


class MessageSerializationError(MessageQueueError):
    """Raised when a message payload cannot be serialized or deserialized.

    The message queue expects dict payloads. If you try to send something
    that cannot be represented as a dict, the serialization layer will
    reject it with the same energy as a bouncer at an exclusive nightclub.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Message serialization error: {reason}. The payload could not "
            f"be converted to a format suitable for appending to a Python list.",
            error_code="EFP-MQ12",
            context={},
        )


"""Enterprise FizzBuzz Platform - FizzQueue Message Broker Errors (EFP-QUE00 .. EFP-QUE16)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzQueueError(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzQueue error: {reason}", error_code="EFP-QUE00", context={"reason": reason})

class FizzQueueExchangeError(FizzQueueError):
    def __init__(self, exchange: str, reason: str) -> None:
        super().__init__(f"Exchange {exchange}: {reason}"); self.error_code = "EFP-QUE01"

class FizzQueueExchangeNotFoundError(FizzQueueError):
    def __init__(self, exchange: str) -> None:
        super().__init__(f"Exchange not found: {exchange}"); self.error_code = "EFP-QUE02"

class FizzQueueQueueNotFoundError(FizzQueueError):
    def __init__(self, queue: str) -> None:
        super().__init__(f"Queue not found: {queue}"); self.error_code = "EFP-QUE03"

class FizzQueueBindingError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Binding: {reason}"); self.error_code = "EFP-QUE04"

class FizzQueuePublishError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Publish: {reason}"); self.error_code = "EFP-QUE05"

class FizzQueueConsumeError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Consume: {reason}"); self.error_code = "EFP-QUE06"

class FizzQueueAckError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Ack: {reason}"); self.error_code = "EFP-QUE07"

class FizzQueueDeadLetterError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Dead letter: {reason}"); self.error_code = "EFP-QUE08"

class FizzQueuePrefetchError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Prefetch: {reason}"); self.error_code = "EFP-QUE09"

class FizzQueueVHostError(FizzQueueError):
    def __init__(self, vhost: str, reason: str) -> None:
        super().__init__(f"VHost {vhost}: {reason}"); self.error_code = "EFP-QUE10"

class FizzQueueConnectionError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Connection: {reason}"); self.error_code = "EFP-QUE11"

class FizzQueueChannelError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Channel: {reason}"); self.error_code = "EFP-QUE12"

class FizzQueuePersistenceError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Persistence: {reason}"); self.error_code = "EFP-QUE13"

class FizzQueueQuorumError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Quorum: {reason}"); self.error_code = "EFP-QUE14"

class FizzQueueTTLError(FizzQueueError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"TTL: {reason}"); self.error_code = "EFP-QUE15"

class FizzQueueConfigError(FizzQueueError):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-QUE16"

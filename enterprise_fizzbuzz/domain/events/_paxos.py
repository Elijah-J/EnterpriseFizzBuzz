"""Distributed Paxos Consensus events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("PAXOS_PREPARE_SENT")
EventType.register("PAXOS_PROMISE_RECEIVED")
EventType.register("PAXOS_ACCEPT_SENT")
EventType.register("PAXOS_ACCEPTED_RECEIVED")
EventType.register("PAXOS_CONSENSUS_REACHED")
EventType.register("PAXOS_CONSENSUS_FAILED")

"""
Enterprise FizzBuzz Platform - Distributed Paxos Consensus Module

Implements a full Paxos consensus protocol for multi-node FizzBuzz
evaluation, because computing n % 3 on a single machine is a single
point of failure. What if that machine is wrong? What if the CPU
secretly disagrees with modular arithmetic? The only responsible
engineering decision is to run FIVE copies of the same deterministic
computation and have them reach distributed consensus on the result
via Lamport's Paxos protocol.

Leslie Lamport received the Turing Award for this algorithm.
We are using it for FizzBuzz. Peak enterprise engineering.

All nodes run in-memory within a single process. The "distribution"
is simulated via message passing between Python objects. Network
partitions are simulated by dropping messages between groups.
Byzantine faults are simulated by having one node lie about its
evaluation result. Despite all of this, the majority still agrees,
because modular arithmetic is stubbornly deterministic.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BallotRejectedError,
    ByzantineFaultDetectedError,
    ConsensusTimeoutError,
    NetworkPartitionError,
    PaxosError,
    QuorumNotReachedError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
)

logger = logging.getLogger(__name__)


# ============================================================
# Data Classes — The sacred scrolls of Paxos message-passing
# ============================================================


class PaxosMessageType(Enum):
    """Types of messages exchanged in the Paxos protocol.

    Each message type corresponds to a phase of the protocol.
    PREPARE and PROMISE form Phase 1 (the courtship).
    ACCEPT and ACCEPTED form Phase 2 (the commitment).
    NACK is the rejection letter nobody wants to receive.
    """

    PREPARE = auto()
    PROMISE = auto()
    ACCEPT = auto()
    ACCEPTED = auto()
    NACK = auto()


@dataclass(frozen=True)
class BallotNumber:
    """A monotonically increasing ballot number for Paxos proposals.

    Ballot numbers must be globally unique and totally ordered.
    We achieve this by combining a sequence number with the proposer's
    node ID, because two proposers might otherwise pick the same
    number, leading to a ballot collision — the distributed consensus
    equivalent of a head-on collision on a one-lane bridge.

    Attributes:
        sequence: The monotonically increasing sequence number.
        node_id: The ID of the proposing node (tiebreaker).
    """

    sequence: int
    node_id: str

    def __lt__(self, other: BallotNumber) -> bool:
        if self.sequence != other.sequence:
            return self.sequence < other.sequence
        return self.node_id < other.node_id

    def __le__(self, other: BallotNumber) -> bool:
        return self == other or self < other

    def __gt__(self, other: BallotNumber) -> bool:
        return not self <= other

    def __ge__(self, other: BallotNumber) -> bool:
        return not self < other

    def __str__(self) -> str:
        return f"B({self.sequence}:{self.node_id})"


@dataclass(frozen=True)
class DecreeValue:
    """The value being proposed for consensus — a FizzBuzz evaluation result.

    In real Paxos, this would be a log entry, a configuration change,
    or a database write. Here, it is the output of n % 3 == 0 and
    n % 5 == 0, packaged as a decree for the Paxos parliament to
    ratify. Separation of powers for modulo arithmetic.

    Attributes:
        number: The number that was evaluated.
        output: The FizzBuzz classification (e.g., "Fizz", "Buzz", "FizzBuzz", "7").
        evaluator_node_id: Which node produced this evaluation.
    """

    number: int
    output: str
    evaluator_node_id: str


@dataclass
class PaxosMessage:
    """A message exchanged between Paxos nodes.

    Every message carries a type, a ballot number, and optionally
    a decree value. Messages are the lifeblood of distributed
    consensus — without them, nodes are just lonely processes
    computing modulo arithmetic in silence.

    Attributes:
        msg_type: The type of Paxos message.
        ballot: The ballot number associated with this message.
        sender: The node ID of the sender.
        receiver: The node ID of the intended receiver.
        decree_number: The decree (slot) this message refers to.
        value: The proposed or accepted decree value (optional).
        previously_accepted_ballot: The highest ballot previously accepted (Promise messages).
        previously_accepted_value: The value previously accepted (Promise messages).
    """

    msg_type: PaxosMessageType
    ballot: BallotNumber
    sender: str
    receiver: str
    decree_number: int
    value: Optional[DecreeValue] = None
    previously_accepted_ballot: Optional[BallotNumber] = None
    previously_accepted_value: Optional[DecreeValue] = None
    timestamp: float = field(default_factory=time.monotonic)
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


# ============================================================
# PaxosMesh — In-memory message passing between nodes
# ============================================================


class PaxosMesh:
    """Simulated network mesh for inter-node message passing.

    In a real distributed system, this would be TCP, gRPC, or
    carrier pigeons. Here, it is a Python list that messages get
    appended to. The simulated network supports configurable
    message delay and random message dropping, because unreliable
    networks are the only realistic kind of networks.

    The mesh also supports network partitions via a partition map
    that specifies which nodes can communicate with which other
    nodes. Messages between partitioned groups are silently dropped,
    just like in a real datacenter when someone trips over a cable.
    """

    def __init__(
        self,
        delay_ms: float = 0.0,
        drop_rate: float = 0.0,
    ) -> None:
        self._delay_ms = delay_ms
        self._drop_rate = drop_rate
        self._mailboxes: dict[str, list[PaxosMessage]] = {}
        self._partition_map: dict[str, int] = {}  # node_id -> partition group
        self._messages_sent = 0
        self._messages_dropped = 0
        self._messages_delivered = 0
        self._partition_drops = 0

    def register_node(self, node_id: str) -> None:
        """Register a node's mailbox in the mesh."""
        self._mailboxes[node_id] = []

    def set_partitions(self, groups: list[list[str]]) -> None:
        """Configure network partitions.

        Nodes in the same group can communicate. Nodes in different
        groups cannot. Democracy is restricted to your partition.
        """
        self._partition_map.clear()
        for group_idx, group in enumerate(groups):
            for node_id in group:
                self._partition_map[node_id] = group_idx

    def clear_partitions(self) -> None:
        """Remove all network partitions. Unity restored."""
        self._partition_map.clear()

    def send(self, message: PaxosMessage) -> bool:
        """Send a message through the mesh.

        Returns True if the message was delivered, False if it was
        dropped (either by random drop or network partition).
        """
        self._messages_sent += 1

        # Check for network partition
        if self._partition_map:
            sender_group = self._partition_map.get(message.sender, -1)
            receiver_group = self._partition_map.get(message.receiver, -2)
            if sender_group != receiver_group:
                self._messages_dropped += 1
                self._partition_drops += 1
                logger.debug(
                    "Partition drop: %s -> %s (groups %d vs %d)",
                    message.sender,
                    message.receiver,
                    sender_group,
                    receiver_group,
                )
                return False

        # Random message drop
        if self._drop_rate > 0 and random.random() < self._drop_rate:
            self._messages_dropped += 1
            logger.debug(
                "Random drop: %s -> %s (%s)",
                message.sender,
                message.receiver,
                message.msg_type.name,
            )
            return False

        # Simulate delay (we just log it — actual sleep would be antisocial)
        if self._delay_ms > 0:
            logger.debug(
                "Simulated delay of %.1fms for %s -> %s",
                self._delay_ms,
                message.sender,
                message.receiver,
            )

        # Deliver to the receiver's mailbox
        if message.receiver in self._mailboxes:
            self._mailboxes[message.receiver].append(message)
            self._messages_delivered += 1
            return True

        self._messages_dropped += 1
        return False

    def receive(self, node_id: str) -> list[PaxosMessage]:
        """Receive all pending messages for a node. Clears the mailbox."""
        messages = self._mailboxes.get(node_id, [])
        self._mailboxes[node_id] = []
        return messages

    def get_stats(self) -> dict[str, int]:
        """Return message delivery statistics."""
        return {
            "sent": self._messages_sent,
            "delivered": self._messages_delivered,
            "dropped": self._messages_dropped,
            "partition_drops": self._partition_drops,
        }


# ============================================================
# Proposer — Generates ballots and drives the two-phase protocol
# ============================================================


class Proposer:
    """Paxos Proposer role.

    The Proposer initiates consensus by selecting a ballot number,
    sending Prepare messages to all Acceptors, collecting Promises,
    and then sending Accept messages with the chosen value. In a
    real system, this might propose a database write or a config
    change. Here, it proposes that 15 should be classified as
    "FizzBuzz", which is arguably more important.
    """

    def __init__(self, node_id: str, mesh: PaxosMesh) -> None:
        self._node_id = node_id
        self._mesh = mesh
        self._ballot_sequence = 0
        self._promises_received: dict[int, list[PaxosMessage]] = {}
        self._accepted_received: dict[int, list[PaxosMessage]] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    def next_ballot(self) -> BallotNumber:
        """Generate the next monotonically increasing ballot number."""
        self._ballot_sequence += 1
        return BallotNumber(sequence=self._ballot_sequence, node_id=self._node_id)

    def prepare(
        self, ballot: BallotNumber, decree_number: int, acceptor_ids: list[str]
    ) -> int:
        """Send Prepare messages to all acceptors (Phase 1a).

        Returns the number of messages successfully sent.
        """
        sent = 0
        for acceptor_id in acceptor_ids:
            msg = PaxosMessage(
                msg_type=PaxosMessageType.PREPARE,
                ballot=ballot,
                sender=self._node_id,
                receiver=acceptor_id,
                decree_number=decree_number,
            )
            if self._mesh.send(msg):
                sent += 1
        return sent

    def collect_promises(
        self, decree_number: int, messages: list[PaxosMessage]
    ) -> list[PaxosMessage]:
        """Collect Promise responses for a decree."""
        promises = [
            m
            for m in messages
            if m.msg_type == PaxosMessageType.PROMISE
            and m.decree_number == decree_number
        ]
        self._promises_received.setdefault(decree_number, []).extend(promises)
        return self._promises_received[decree_number]

    def get_highest_accepted_value(
        self, promises: list[PaxosMessage]
    ) -> Optional[DecreeValue]:
        """From collected promises, find the value with the highest accepted ballot.

        If any acceptor has already accepted a value, the proposer
        MUST propose that value (Paxos safety guarantee). This
        prevents the cluster from changing its mind, which is the
        distributed consensus equivalent of indecisiveness.
        """
        highest_ballot: Optional[BallotNumber] = None
        highest_value: Optional[DecreeValue] = None

        for promise in promises:
            if (
                promise.previously_accepted_ballot is not None
                and promise.previously_accepted_value is not None
            ):
                if highest_ballot is None or promise.previously_accepted_ballot > highest_ballot:
                    highest_ballot = promise.previously_accepted_ballot
                    highest_value = promise.previously_accepted_value

        return highest_value

    def accept(
        self,
        ballot: BallotNumber,
        decree_number: int,
        value: DecreeValue,
        acceptor_ids: list[str],
    ) -> int:
        """Send Accept messages to all acceptors (Phase 2a).

        Returns the number of messages successfully sent.
        """
        sent = 0
        for acceptor_id in acceptor_ids:
            msg = PaxosMessage(
                msg_type=PaxosMessageType.ACCEPT,
                ballot=ballot,
                sender=self._node_id,
                receiver=acceptor_id,
                decree_number=decree_number,
                value=value,
            )
            if self._mesh.send(msg):
                sent += 1
        return sent


# ============================================================
# Acceptor — Responds to Prepare and Accept messages
# ============================================================


class Acceptor:
    """Paxos Acceptor role.

    The Acceptor is the voter in the Paxos parliament. It promises
    not to accept proposals with lower ballot numbers, and accepts
    proposals when the ballot is high enough. The Acceptor is the
    bedrock of safety in Paxos — without it, the cluster would
    accept contradictory values, which for FizzBuzz would mean
    that 15 is simultaneously "Fizz" and "Buzz" and "FizzBuzz"
    and "42". Schrödinger's FizzBuzz.
    """

    def __init__(self, node_id: str, mesh: PaxosMesh) -> None:
        self._node_id = node_id
        self._mesh = mesh
        # Highest ballot promised (per decree)
        self._promised: dict[int, BallotNumber] = {}
        # Highest ballot accepted and corresponding value (per decree)
        self._accepted_ballot: dict[int, BallotNumber] = {}
        self._accepted_value: dict[int, DecreeValue] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    def handle_prepare(self, msg: PaxosMessage) -> None:
        """Handle a Prepare message (Phase 1a -> 1b).

        If the ballot is higher than any previously promised ballot,
        respond with a Promise. Otherwise, respond with a NACK.
        """
        decree = msg.decree_number
        current_promise = self._promised.get(decree)

        if current_promise is None or msg.ballot > current_promise:
            # Promise: we will not accept any ballot lower than this
            self._promised[decree] = msg.ballot

            response = PaxosMessage(
                msg_type=PaxosMessageType.PROMISE,
                ballot=msg.ballot,
                sender=self._node_id,
                receiver=msg.sender,
                decree_number=decree,
                previously_accepted_ballot=self._accepted_ballot.get(decree),
                previously_accepted_value=self._accepted_value.get(decree),
            )
            self._mesh.send(response)
        else:
            # NACK: we already promised a higher ballot
            response = PaxosMessage(
                msg_type=PaxosMessageType.NACK,
                ballot=msg.ballot,
                sender=self._node_id,
                receiver=msg.sender,
                decree_number=decree,
            )
            self._mesh.send(response)

    def handle_accept(self, msg: PaxosMessage) -> None:
        """Handle an Accept message (Phase 2a -> 2b).

        If the ballot is >= our promised ballot, accept the value
        and broadcast Accepted. Otherwise, NACK.
        """
        decree = msg.decree_number
        current_promise = self._promised.get(decree)

        if current_promise is None or msg.ballot >= current_promise:
            # Accept the value
            self._accepted_ballot[decree] = msg.ballot
            self._accepted_value[decree] = msg.value
            self._promised[decree] = msg.ballot

            response = PaxosMessage(
                msg_type=PaxosMessageType.ACCEPTED,
                ballot=msg.ballot,
                sender=self._node_id,
                receiver=msg.sender,
                decree_number=decree,
                value=msg.value,
            )
            self._mesh.send(response)
        else:
            response = PaxosMessage(
                msg_type=PaxosMessageType.NACK,
                ballot=msg.ballot,
                sender=self._node_id,
                receiver=msg.sender,
                decree_number=decree,
            )
            self._mesh.send(response)

    def get_state(self) -> dict[str, Any]:
        """Return the acceptor's current state for diagnostics."""
        return {
            "node_id": self._node_id,
            "promised": {k: str(v) for k, v in self._promised.items()},
            "accepted": {
                k: {"ballot": str(self._accepted_ballot[k]), "value": v.output}
                for k, v in self._accepted_value.items()
            },
        }


# ============================================================
# Learner — Detects quorum and marks decrees as chosen
# ============================================================


class Learner:
    """Paxos Learner role.

    The Learner observes Accepted messages and detects when a
    quorum has been reached. Once a majority of acceptors have
    accepted the same value for a decree, the Learner declares
    that decree as chosen. This is the moment of truth — the
    cluster has spoken, and the FizzBuzz result has been
    democratically ratified.
    """

    def __init__(self, node_id: str, quorum_size: int) -> None:
        self._node_id = node_id
        self._quorum_size = quorum_size
        # decree_number -> {ballot -> {node_id -> value}}
        self._accepted_log: dict[int, dict[str, list[tuple[str, DecreeValue]]]] = {}
        self._chosen: dict[int, DecreeValue] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    def record_accepted(self, msg: PaxosMessage) -> Optional[DecreeValue]:
        """Record an Accepted message and check for quorum.

        Returns the chosen value if quorum is reached, None otherwise.
        """
        decree = msg.decree_number
        ballot_key = str(msg.ballot)

        if decree in self._chosen:
            return self._chosen[decree]

        if decree not in self._accepted_log:
            self._accepted_log[decree] = {}

        if ballot_key not in self._accepted_log[decree]:
            self._accepted_log[decree][ballot_key] = []

        # Record this acceptance (avoid duplicates from same node)
        existing_nodes = {node_id for node_id, _ in self._accepted_log[decree][ballot_key]}
        if msg.sender not in existing_nodes:
            self._accepted_log[decree][ballot_key].append(
                (msg.sender, msg.value)
            )

        # Check for quorum
        acceptances = self._accepted_log[decree][ballot_key]
        if len(acceptances) >= self._quorum_size:
            # Quorum reached! The decree is chosen.
            self._chosen[decree] = msg.value
            return msg.value

        return None

    def is_chosen(self, decree_number: int) -> bool:
        """Check if a decree has been chosen."""
        return decree_number in self._chosen

    def get_chosen_value(self, decree_number: int) -> Optional[DecreeValue]:
        """Get the chosen value for a decree."""
        return self._chosen.get(decree_number)

    def get_acceptance_count(self, decree_number: int) -> int:
        """Get the total number of unique acceptances across all ballots for a decree."""
        if decree_number not in self._accepted_log:
            return 0
        total = 0
        for acceptances in self._accepted_log[decree_number].values():
            total = max(total, len(acceptances))
        return total


# ============================================================
# PaxosNode — Composite holding Proposer + Acceptor + Learner
# ============================================================


class PaxosNode:
    """A single node in the Paxos cluster.

    Each node plays all three roles simultaneously: Proposer,
    Acceptor, and Learner. It also holds a reference to the
    StandardRuleEngine for evaluating FizzBuzz locally. In a
    real distributed system, each node would be a separate
    process on a separate machine. Here, each node is a
    separate Python object in the same process, which provides
    all the fault tolerance of talking to yourself in a mirror.

    Attributes:
        node_id: Unique identifier for this node.
        proposer: The Proposer role.
        acceptor: The Acceptor role.
        learner: The Learner role.
        evaluate_fn: Function to evaluate a number using StandardRuleEngine.
    """

    def __init__(
        self,
        node_id: str,
        mesh: PaxosMesh,
        quorum_size: int,
        evaluate_fn: Callable[[int], FizzBuzzResult],
    ) -> None:
        self.node_id = node_id
        self.proposer = Proposer(node_id, mesh)
        self.acceptor = Acceptor(node_id, mesh)
        self.learner = Learner(node_id, quorum_size)
        self.evaluate_fn = evaluate_fn
        self._mesh = mesh
        self._is_byzantine = False
        self._byzantine_lie_probability = 1.0
        self._evaluations: dict[int, str] = {}

    def set_byzantine(self, lie_probability: float = 1.0) -> None:
        """Mark this node as a Byzantine traitor.

        A Byzantine node will lie about its evaluation results with
        the given probability. In the Byzantine Generals Problem,
        this represents a treacherous general. Here, it represents
        a CPU that has decided mathematics is subjective.
        """
        self._is_byzantine = True
        self._byzantine_lie_probability = lie_probability

    def evaluate(self, number: int) -> str:
        """Evaluate a number using the local rule engine.

        Byzantine nodes may lie about the result, because in
        distributed systems, trust is earned, not assumed.
        """
        result = self.evaluate_fn(number)
        output = result.output

        if self._is_byzantine and random.random() < self._byzantine_lie_probability:
            # Lie about the result — the quintessential Byzantine fault
            lies = ["Fizz", "Buzz", "FizzBuzz", str(number)]
            lies = [l for l in lies if l != output]
            if lies:
                lie = random.choice(lies)
                logger.info(
                    "Byzantine node %s lying: %s -> %s for number %d",
                    self.node_id,
                    output,
                    lie,
                    number,
                )
                output = lie

        self._evaluations[number] = output
        return output

    def process_messages(self) -> list[PaxosMessage]:
        """Process all pending messages in this node's mailbox.

        Routes each message to the appropriate handler based on
        its type. Returns any Accepted messages received for
        learner processing.
        """
        messages = self._mesh.receive(self.node_id)
        accepted_messages = []

        for msg in messages:
            if msg.msg_type == PaxosMessageType.PREPARE:
                self.acceptor.handle_prepare(msg)
            elif msg.msg_type == PaxosMessageType.ACCEPT:
                self.acceptor.handle_accept(msg)
            elif msg.msg_type == PaxosMessageType.ACCEPTED:
                accepted_messages.append(msg)
            elif msg.msg_type == PaxosMessageType.PROMISE:
                # Collected by the proposer during the prepare phase
                pass
            elif msg.msg_type == PaxosMessageType.NACK:
                # Logged but not fatal
                logger.debug(
                    "NACK received by %s from %s for decree %d",
                    self.node_id,
                    msg.sender,
                    msg.decree_number,
                )

        return accepted_messages

    @property
    def is_byzantine(self) -> bool:
        return self._is_byzantine


# ============================================================
# PaxosCluster — Orchestrates N nodes, drives the two-phase protocol
# ============================================================


class PaxosCluster:
    """Orchestrates a cluster of Paxos nodes for FizzBuzz consensus.

    The cluster manages the full lifecycle of a Paxos consensus
    round: proposing a value, collecting promises, sending accept
    messages, and detecting quorum. All within a single Python
    process, because true distribution is just a deployment detail.

    The cluster uses StandardRuleEngine on each node to evaluate
    FizzBuzz independently, then reaches consensus on the result.
    For correct (non-Byzantine) nodes, they will all agree, making
    the entire consensus protocol a magnificent waste of computation
    that produces the same result a single modulo operation would have.
    """

    def __init__(
        self,
        num_nodes: int,
        rules: list[Any],
        mesh: Optional[PaxosMesh] = None,
        event_callback: Optional[Callable[[Event], None]] = None,
    ) -> None:
        from enterprise_fizzbuzz.infrastructure.rules_engine import (
            ConcreteRule,
            StandardRuleEngine,
        )

        self._num_nodes = num_nodes
        self._quorum_size = (num_nodes // 2) + 1
        self._mesh = mesh or PaxosMesh()
        self._event_callback = event_callback
        self._decree_counter = 0

        # Build rules for each node
        concrete_rules = []
        for r in rules:
            if isinstance(r, RuleDefinition):
                concrete_rules.append(ConcreteRule(r))
            else:
                concrete_rules.append(r)

        # Create nodes — each with its own StandardRuleEngine
        self._nodes: list[PaxosNode] = []
        for i in range(num_nodes):
            node_id = f"node-{i}"
            self._mesh.register_node(node_id)
            engine = StandardRuleEngine()

            def make_eval_fn(eng: StandardRuleEngine, rls: list) -> Callable:
                def fn(number: int) -> FizzBuzzResult:
                    return eng.evaluate(number, rls)
                return fn

            node = PaxosNode(
                node_id=node_id,
                mesh=self._mesh,
                quorum_size=self._quorum_size,
                evaluate_fn=make_eval_fn(engine, concrete_rules),
            )
            self._nodes.append(node)

        # Consensus log
        self._consensus_log: list[dict[str, Any]] = []
        self._byzantine_faults_detected: list[dict[str, Any]] = []

    @property
    def nodes(self) -> list[PaxosNode]:
        return self._nodes

    @property
    def quorum_size(self) -> int:
        return self._quorum_size

    @property
    def consensus_log(self) -> list[dict[str, Any]]:
        return self._consensus_log

    @property
    def byzantine_faults_detected(self) -> list[dict[str, Any]]:
        return self._byzantine_faults_detected

    @property
    def mesh(self) -> PaxosMesh:
        return self._mesh

    def set_byzantine_node(self, node_index: int, lie_probability: float = 1.0) -> None:
        """Mark a node as Byzantine (it will lie about evaluations)."""
        if 0 <= node_index < len(self._nodes):
            self._nodes[node_index].set_byzantine(lie_probability)

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event through the event callback."""
        if self._event_callback is not None:
            event = Event(
                event_type=event_type,
                payload=payload,
                source="PaxosCluster",
            )
            self._event_callback(event)

    def reach_consensus(self, number: int) -> dict[str, Any]:
        """Run the full Paxos protocol to reach consensus on a FizzBuzz evaluation.

        Phase 1: Prepare / Promise
        Phase 2: Accept / Accepted
        Phase 3: Learn (detect quorum)

        Returns a dict with the consensus result, vote details, and
        any Byzantine faults detected.
        """
        self._decree_counter += 1
        decree_number = self._decree_counter
        start_time = time.perf_counter_ns()

        # Step 0: Each node evaluates the number independently
        node_evaluations: dict[str, str] = {}
        for node in self._nodes:
            output = node.evaluate(number)
            node_evaluations[node.node_id] = output

        # Choose a proposer (round-robin based on decree number)
        proposer_idx = (decree_number - 1) % len(self._nodes)
        proposer_node = self._nodes[proposer_idx]
        proposer = proposer_node.proposer

        # The proposed value is determined by majority vote among all
        # node evaluations. This ensures that even if the proposer is
        # Byzantine, the proposal reflects the honest majority — because
        # in FizzBuzz governance, the electorate's arithmetic must prevail
        # over any single node's treachery.
        vote_tally: dict[str, int] = {}
        for output in node_evaluations.values():
            vote_tally[output] = vote_tally.get(output, 0) + 1
        proposed_output = max(vote_tally, key=vote_tally.get)
        proposed_value = DecreeValue(
            number=number,
            output=proposed_output,
            evaluator_node_id=proposer_node.node_id,
        )

        # Phase 1a: Proposer sends Prepare to all acceptors
        ballot = proposer.next_ballot()
        all_node_ids = [n.node_id for n in self._nodes]

        self._emit_event(EventType.PAXOS_PREPARE_SENT, {
            "decree_number": decree_number,
            "ballot": str(ballot),
            "proposer": proposer_node.node_id,
            "number": number,
        })

        proposer.prepare(ballot, decree_number, all_node_ids)

        # Phase 1b: Each acceptor processes the Prepare message and sends
        # a Promise (or NACK) back to the proposer. We handle each node's
        # incoming messages directly through its acceptor rather than the
        # generic process_messages(), because the proposer node also has
        # messages in its mailbox and we don't want to consume Promises
        # prematurely. Non-PREPARE messages are put back into the mailbox.
        for node in self._nodes:
            incoming = self._mesh.receive(node.node_id)
            for msg in incoming:
                if msg.msg_type == PaxosMessageType.PREPARE:
                    node.acceptor.handle_prepare(msg)
                else:
                    # Put non-PREPARE messages back (e.g., Promises that
                    # arrived at the proposer node's mailbox from fast
                    # acceptors)
                    self._mesh._mailboxes[node.node_id].append(msg)

        # Proposer collects Promises from its mailbox
        proposer_messages = self._mesh.receive(proposer_node.node_id)
        promises = [
            m for m in proposer_messages
            if m.msg_type == PaxosMessageType.PROMISE
            and m.decree_number == decree_number
        ]
        nacks = [
            m for m in proposer_messages
            if m.msg_type == PaxosMessageType.NACK
            and m.decree_number == decree_number
        ]

        self._emit_event(EventType.PAXOS_PROMISE_RECEIVED, {
            "decree_number": decree_number,
            "promises": len(promises),
            "nacks": len(nacks),
            "quorum_required": self._quorum_size,
        })

        # Check if we have enough promises for quorum
        if len(promises) < self._quorum_size:
            elapsed_ns = time.perf_counter_ns() - start_time
            self._emit_event(EventType.PAXOS_CONSENSUS_FAILED, {
                "decree_number": decree_number,
                "reason": "insufficient_promises",
                "promises": len(promises),
                "required": self._quorum_size,
            })
            result = {
                "decree_number": decree_number,
                "number": number,
                "consensus_reached": False,
                "reason": "insufficient_promises",
                "promises": len(promises),
                "quorum_required": self._quorum_size,
                "node_evaluations": node_evaluations,
                "elapsed_ns": elapsed_ns,
            }
            self._consensus_log.append(result)
            return result

        # Check if any acceptor had a previously accepted value
        previously_accepted = proposer.get_highest_accepted_value(promises)
        if previously_accepted is not None:
            proposed_value = previously_accepted

        # Phase 2a: Proposer sends Accept to all acceptors
        self._emit_event(EventType.PAXOS_ACCEPT_SENT, {
            "decree_number": decree_number,
            "ballot": str(ballot),
            "proposed_value": proposed_value.output,
        })

        proposer.accept(ballot, decree_number, proposed_value, all_node_ids)

        # Phase 2b: Each acceptor processes the Accept message and sends
        # Accepted (or NACK) back to the proposer. Non-ACCEPT messages
        # are put back, preserving any Accepted responses that arrived
        # early at the proposer's mailbox.
        for node in self._nodes:
            incoming = self._mesh.receive(node.node_id)
            for msg in incoming:
                if msg.msg_type == PaxosMessageType.ACCEPT:
                    node.acceptor.handle_accept(msg)
                else:
                    self._mesh._mailboxes[node.node_id].append(msg)

        # Proposer collects Accepted messages
        proposer_messages = self._mesh.receive(proposer_node.node_id)
        accepted_msgs = [
            m for m in proposer_messages
            if m.msg_type == PaxosMessageType.ACCEPTED
            and m.decree_number == decree_number
        ]

        self._emit_event(EventType.PAXOS_ACCEPTED_RECEIVED, {
            "decree_number": decree_number,
            "accepted_count": len(accepted_msgs),
            "quorum_required": self._quorum_size,
        })

        # Phase 3: Learner detects quorum
        chosen_value = None
        for msg in accepted_msgs:
            result_val = proposer_node.learner.record_accepted(msg)
            if result_val is not None:
                chosen_value = result_val

        elapsed_ns = time.perf_counter_ns() - start_time

        # Detect Byzantine faults (nodes that disagree with consensus)
        byzantine_detected = []
        if chosen_value is not None:
            # Use the canonical (non-byzantine) evaluation as ground truth
            # by checking the majority vote
            vote_counts: dict[str, int] = {}
            for node_id, output in node_evaluations.items():
                vote_counts[output] = vote_counts.get(output, 0) + 1

            majority_output = max(vote_counts, key=vote_counts.get)

            for node in self._nodes:
                if node.is_byzantine:
                    node_output = node_evaluations[node.node_id]
                    if node_output != majority_output:
                        fault_info = {
                            "node_id": node.node_id,
                            "expected": majority_output,
                            "actual": node_output,
                            "number": number,
                        }
                        byzantine_detected.append(fault_info)
                        self._byzantine_faults_detected.append(fault_info)

        if chosen_value is not None:
            self._emit_event(EventType.PAXOS_CONSENSUS_REACHED, {
                "decree_number": decree_number,
                "number": number,
                "chosen_value": chosen_value.output,
                "elapsed_ns": elapsed_ns,
                "byzantine_faults": len(byzantine_detected),
            })
        else:
            self._emit_event(EventType.PAXOS_CONSENSUS_FAILED, {
                "decree_number": decree_number,
                "reason": "quorum_not_reached_in_accept",
                "accepted_count": len(accepted_msgs),
                "required": self._quorum_size,
            })

        result = {
            "decree_number": decree_number,
            "number": number,
            "consensus_reached": chosen_value is not None,
            "chosen_value": chosen_value.output if chosen_value else None,
            "proposed_value": proposed_value.output,
            "ballot": str(ballot),
            "proposer": proposer_node.node_id,
            "node_evaluations": node_evaluations,
            "promises": len(promises),
            "accepted": len(accepted_msgs),
            "quorum_required": self._quorum_size,
            "byzantine_faults": byzantine_detected,
            "elapsed_ns": elapsed_ns,
        }
        self._consensus_log.append(result)
        return result


# ============================================================
# NetworkPartitionSimulator — Drops messages between partitioned groups
# ============================================================


class NetworkPartitionSimulator:
    """Simulates network partitions in the Paxos cluster.

    In a real distributed system, network partitions are caused by
    hardware failures, misconfigured firewalls, or particularly
    aggressive squirrels chewing through fibre optic cables. Here,
    they are caused by calling a method that sets a boolean flag.
    The effect is identical: nodes on different sides of the
    partition cannot communicate, and each side must attempt to
    reach consensus independently. Only the majority partition
    can achieve quorum.
    """

    def __init__(self, cluster: PaxosCluster) -> None:
        self._cluster = cluster

    def partition(self, groups: list[list[int]]) -> None:
        """Create a network partition.

        Args:
            groups: Lists of node indices forming each partition group.
                    e.g., [[0, 1, 2], [3, 4]] creates two partitions.
        """
        node_groups: list[list[str]] = []
        for group in groups:
            node_ids = [
                self._cluster.nodes[i].node_id
                for i in group
                if 0 <= i < len(self._cluster.nodes)
            ]
            node_groups.append(node_ids)

        self._cluster.mesh.set_partitions(node_groups)
        logger.info(
            "Network partition created: %s",
            [[n.node_id for n in [self._cluster.nodes[i] for i in g if 0 <= i < len(self._cluster.nodes)]] for g in groups],
        )

    def heal(self) -> None:
        """Heal the network partition. All nodes can communicate again."""
        self._cluster.mesh.clear_partitions()
        logger.info("Network partition healed. Democracy restored.")


# ============================================================
# ByzantineFaultInjector — Makes one node lie about its evaluation
# ============================================================


class ByzantineFaultInjector:
    """Injects Byzantine faults into the Paxos cluster.

    A Byzantine node will intentionally return incorrect FizzBuzz
    evaluation results. This simulates the classic Byzantine Generals
    Problem, where traitorous generals send conflicting orders. Here,
    the traitorous general sends conflicting FizzBuzz results, which
    is arguably a greater betrayal.

    The key insight: despite one node lying, the majority of honest
    nodes will still reach correct consensus, because Paxos tolerates
    f Byzantine faults in a cluster of 2f + 1 nodes.
    """

    def __init__(self, cluster: PaxosCluster) -> None:
        self._cluster = cluster
        self._byzantine_node_idx: Optional[int] = None

    def inject(self, node_index: int = -1, lie_probability: float = 1.0) -> str:
        """Inject a Byzantine fault on the specified node.

        Args:
            node_index: Index of the node to corrupt (-1 = last node).
            lie_probability: Probability that the node lies (0.0 - 1.0).

        Returns:
            The node_id of the corrupted node.
        """
        if node_index < 0:
            node_index = len(self._cluster.nodes) + node_index

        self._byzantine_node_idx = node_index
        self._cluster.set_byzantine_node(node_index, lie_probability)
        byzantine_id = self._cluster.nodes[node_index].node_id
        logger.info(
            "Byzantine fault injected on %s (lie probability: %.0f%%)",
            byzantine_id,
            lie_probability * 100,
        )
        return byzantine_id

    @property
    def byzantine_node_id(self) -> Optional[str]:
        if self._byzantine_node_idx is not None:
            return self._cluster.nodes[self._byzantine_node_idx].node_id
        return None


# ============================================================
# ConsensusDashboard — ASCII dashboard with vote table
# ============================================================


class ConsensusDashboard:
    """ASCII dashboard for visualizing Paxos consensus results.

    Renders a table showing each node's vote, quorum status,
    partition state, and Byzantine fault detection. Because the
    only thing more satisfying than reaching consensus is watching
    a beautifully formatted table prove that you reached consensus.
    """

    @staticmethod
    def render(
        cluster: PaxosCluster,
        width: int = 60,
        partition_groups: Optional[list[list[int]]] = None,
        byzantine_node_id: Optional[str] = None,
    ) -> str:
        """Render the full consensus dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        separator = "+" + "-" * (width - 2) + "+"
        inner_w = width - 4

        lines.append(f"  {border}")
        lines.append(f"  | {'DISTRIBUTED PAXOS CONSENSUS DASHBOARD':^{inner_w}} |")
        lines.append(f"  | {'Because one modulo is never enough':^{inner_w}} |")
        lines.append(f"  {border}")

        # Cluster info
        n = len(cluster.nodes)
        q = cluster.quorum_size
        lines.append(f"  | {'Cluster Configuration':^{inner_w}} |")
        lines.append(f"  {separator}")
        lines.append(f"  | {'Nodes:':<20} {n:<{inner_w - 21}} |")
        lines.append(f"  | {'Quorum Size:':<20} {q:<{inner_w - 21}} |")

        # Byzantine status
        byzantine_ids = [node.node_id for node in cluster.nodes if node.is_byzantine]
        byz_str = ", ".join(byzantine_ids) if byzantine_ids else "None"
        lines.append(f"  | {'Byzantine Nodes:':<20} {byz_str:<{inner_w - 21}} |")

        # Partition status
        mesh_stats = cluster.mesh.get_stats()
        part_str = "ACTIVE" if mesh_stats["partition_drops"] > 0 else "None"
        lines.append(f"  | {'Partitions:':<20} {part_str:<{inner_w - 21}} |")
        lines.append(f"  {separator}")

        # Message stats
        lines.append(f"  | {'Message Statistics':^{inner_w}} |")
        lines.append(f"  {separator}")
        lines.append(f"  | {'Sent:':<20} {mesh_stats['sent']:<{inner_w - 21}} |")
        lines.append(f"  | {'Delivered:':<20} {mesh_stats['delivered']:<{inner_w - 21}} |")
        lines.append(f"  | {'Dropped:':<20} {mesh_stats['dropped']:<{inner_w - 21}} |")
        lines.append(f"  | {'Partition Drops:':<20} {mesh_stats['partition_drops']:<{inner_w - 21}} |")
        lines.append(f"  {separator}")

        # Consensus rounds
        log = cluster.consensus_log
        if log:
            lines.append(f"  | {'Consensus Rounds':^{inner_w}} |")
            lines.append(f"  {separator}")

            # Header
            hdr = f"  | {'#':<4} {'Num':<6} {'Result':<12} {'Votes':<8} {'Time':>8} {'Status':<10} |"
            if len(hdr) > width + 2:
                hdr = hdr[:width + 1] + " |"
            lines.append(hdr)
            lines.append(f"  {separator}")

            for entry in log[-20:]:  # Show last 20 rounds
                d = entry["decree_number"]
                num = entry["number"]
                chosen = entry.get("chosen_value", "N/A")
                if chosen and len(chosen) > 10:
                    chosen = chosen[:10]
                accepted = entry.get("accepted", 0)
                elapsed_us = entry.get("elapsed_ns", 0) / 1000
                status = "OK" if entry["consensus_reached"] else "FAIL"

                # Mark Byzantine-affected rounds
                byz_count = len(entry.get("byzantine_faults", []))
                if byz_count > 0:
                    status = f"BYZ({byz_count})"

                row = f"  | {d:<4} {num:<6} {chosen:<12} {accepted}/{q:<5} {elapsed_us:>6.1f}us {status:<10} |"
                if len(row) > width + 2:
                    row = row[:width + 1] + " |"
                lines.append(row)

            lines.append(f"  {separator}")

            # Vote detail for last round
            last = log[-1]
            evals = last.get("node_evaluations", {})
            if evals:
                lines.append(f"  | {'Last Round Vote Detail':^{inner_w}} |")
                lines.append(f"  {separator}")
                for node_id, output in sorted(evals.items()):
                    is_byz = node_id == byzantine_node_id
                    byz_marker = " [BYZANTINE]" if is_byz else ""
                    proposer_marker = " [PROPOSER]" if node_id == last.get("proposer") else ""
                    label = f"{node_id}{proposer_marker}{byz_marker}"
                    lines.append(f"  | {label:<{inner_w - 14}} => {output:<10} |")
                lines.append(f"  {separator}")

        # Byzantine faults summary
        byz_faults = cluster.byzantine_faults_detected
        if byz_faults:
            lines.append(f"  | {'Byzantine Faults Detected':^{inner_w}} |")
            lines.append(f"  {separator}")
            for fault in byz_faults[-5:]:
                fault_str = (
                    f"{fault['node_id']}: said '{fault['actual']}' "
                    f"(truth: '{fault['expected']}') for n={fault['number']}"
                )
                if len(fault_str) > inner_w:
                    fault_str = fault_str[:inner_w - 3] + "..."
                lines.append(f"  | {fault_str:<{inner_w}} |")
            lines.append(f"  {separator}")

        # Summary stats
        total = len(log)
        successful = sum(1 for e in log if e["consensus_reached"])
        failed = total - successful
        lines.append(f"  | {'Summary':^{inner_w}} |")
        lines.append(f"  {separator}")
        lines.append(f"  | {'Total Rounds:':<20} {total:<{inner_w - 21}} |")
        lines.append(f"  | {'Successful:':<20} {successful:<{inner_w - 21}} |")
        lines.append(f"  | {'Failed:':<20} {failed:<{inner_w - 21}} |")
        success_rate = (successful / total * 100) if total > 0 else 0
        lines.append(f"  | {'Success Rate:':<20} {success_rate:.1f}%{'':<{inner_w - 27}} |")
        lines.append(f"  {border}")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# PaxosMiddleware(IMiddleware) — priority -6
# ============================================================


class PaxosMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through Paxos consensus.

    Instead of simply evaluating a number and returning the result
    (which would take approximately 100 nanoseconds), this middleware
    spawns a full Paxos consensus round across N simulated nodes,
    each independently evaluating the number, proposing their result,
    voting, and reaching distributed consensus. The result is then
    extracted from the chosen decree and used as the evaluation output.

    This adds approximately 0 value and approximately N times the
    computation, but it does provide Byzantine fault tolerance for
    modulo arithmetic, which is exactly the kind of engineering
    over-investment that this platform celebrates.

    Priority: -6 (runs before most other middleware)
    """

    def __init__(
        self,
        cluster: PaxosCluster,
        *,
        show_votes: bool = False,
    ) -> None:
        self._cluster = cluster
        self._show_votes = show_votes

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through Paxos consensus before the normal pipeline."""
        # Run consensus
        consensus = self._cluster.reach_consensus(context.number)

        # Store consensus metadata
        context.metadata["paxos_consensus"] = consensus.get("consensus_reached", False)
        context.metadata["paxos_decree"] = consensus.get("decree_number")
        context.metadata["paxos_chosen_value"] = consensus.get("chosen_value")
        context.metadata["paxos_votes"] = consensus.get("node_evaluations", {})
        context.metadata["paxos_byzantine_faults"] = len(
            consensus.get("byzantine_faults", [])
        )

        # Continue with the normal pipeline
        result = next_handler(context)

        # Override the result output with the consensus value if consensus was reached
        if consensus["consensus_reached"] and result.results:
            latest = result.results[-1]
            original_output = latest.output
            consensus_output = consensus["chosen_value"]
            if original_output != consensus_output:
                # The single-node evaluation disagrees with consensus!
                # This can happen in Byzantine mode.
                context.metadata["paxos_override"] = True
                context.metadata["paxos_original_output"] = original_output
                latest.output = consensus_output

        return result

    def get_name(self) -> str:
        return "PaxosMiddleware"

    def get_priority(self) -> int:
        return -6

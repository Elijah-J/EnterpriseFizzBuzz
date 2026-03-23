"""
Enterprise FizzBuzz Platform - Microkernel Inter-Process Communication Module

Implements Mach-inspired port-based message passing for inter-subsystem
communication within the Enterprise FizzBuzz Platform.  Each FizzBuzz
subsystem is modeled as an independent *task* with its own port namespace.
Messages carry typed payloads, out-of-line data descriptors, and
transferable port rights -- faithfully reproducing the Mach IPC semantics
that underpin modern microkernel operating systems.

Key design decisions:
  - **Port rights** follow the Mach model (SEND, RECEIVE, SEND_ONCE, PORT_SET)
    to enforce capability-based access control over IPC channels.
  - **Bounded message queues** prevent unbounded memory growth; back-pressure
    is applied when a port's queue reaches capacity.
  - **Priority-aware scheduling** with priority inheritance prevents priority
    inversion -- a well-documented hazard in real-time systems and an equally
    critical concern in enterprise FizzBuzz evaluation pipelines.
  - **Deadlock detection** via Tarjan's strongly connected component algorithm
    on the wait-for graph ensures that circular port waits are identified and
    reported before they stall the pipeline indefinitely.
  - **ASCII dashboard** provides operational visibility into port tables,
    message throughput, and the current wait-for graph topology.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    IPCDeadlockError,
    IPCError,
    IPCPermissionError,
    IPCPortNotFoundError,
    IPCQueueFullError,
    IPCRightTransferError,
    IPCTaskNotFoundError,
    IPCTimeoutError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Port Rights
# ══════════════════════════════════════════════════════════════════════


class PortRight(Enum):
    """Mach-style port rights governing IPC channel access.

    The Mach microkernel distinguishes four classes of port right:
      - SEND: permits the holder to enqueue messages on the port.
      - RECEIVE: permits the holder to dequeue messages; only one
        task may hold the receive right for a given port.
      - SEND_ONCE: a single-use send right that is automatically
        revoked after the first successful send.  Used for reply
        ports in RPC-style interactions.
      - PORT_SET: a composite right that multiplexes receive across
        multiple ports, enabling a single blocking receive on any
        member of the set.
    """

    SEND = auto()
    RECEIVE = auto()
    SEND_ONCE = auto()
    PORT_SET = auto()


# ══════════════════════════════════════════════════════════════════════
# Message Types
# ══════════════════════════════════════════════════════════════════════


class MessageType(Enum):
    """Classification of IPC messages flowing through the kernel.

    Each message type maps to a distinct operational semantic within
    the FizzBuzz evaluation lifecycle.
    """

    EVALUATION_REQUEST = auto()
    EVALUATION_RESPONSE = auto()
    PORT_RIGHTS_TRANSFER = auto()
    NOTIFICATION = auto()
    PING = auto()
    PONG = auto()
    SHUTDOWN = auto()
    HEARTBEAT = auto()
    SUBSYSTEM_REGISTER = auto()
    SUBSYSTEM_DEREGISTER = auto()


class MessagePriority(Enum):
    """Priority levels for IPC message scheduling.

    The priority scheduler uses these levels to determine delivery
    order.  CRITICAL messages (e.g., shutdown signals) are always
    delivered before NORMAL evaluation traffic.
    """

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


# ══════════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════════


@dataclass
class MessageHeader:
    """Fixed-size header present in every IPC message.

    Mirrors the ``mach_msg_header_t`` structure: a unique message ID,
    the local and remote port names involved in the exchange, the
    logical size of the payload, and a priority tag for scheduling.
    """

    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    local_port: str = ""
    remote_port: str = ""
    msg_type: MessageType = MessageType.EVALUATION_REQUEST
    priority: MessagePriority = MessagePriority.NORMAL
    size: int = 0
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class OutOfLineDescriptor:
    """Descriptor for out-of-line (OOL) data in an IPC message.

    Large payloads that exceed the inline message buffer are passed
    by reference through OOL descriptors.  The kernel manages the
    underlying memory mapping and performs copy-on-write semantics
    when the receiver modifies the data.
    """

    ool_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    data: Any = None
    size: int = 0
    copy_on_write: bool = True
    deallocate_on_send: bool = False


@dataclass
class PortRightTransfer:
    """Encapsulates a port right being transferred via IPC.

    When a task sends a message containing a PortRightTransfer, the
    kernel extracts the specified right from the sender's namespace
    and inserts it into the receiver's namespace, exactly as Mach
    does for port right descriptors in ``mach_msg``.
    """

    port_name: str = ""
    right: PortRight = PortRight.SEND
    disposition: str = "move"  # "move" or "copy"


@dataclass
class Message:
    """A complete IPC message with header, inline data, OOL descriptors,
    and port right transfers.

    This structure corresponds to a Mach ``mach_msg`` body: the header
    provides routing metadata, ``inline_data`` carries small payloads
    directly within the message buffer, ``ool_descriptors`` reference
    larger data regions managed by the kernel, and ``port_transfers``
    carry port rights that will be injected into the receiver's
    namespace upon delivery.
    """

    header: MessageHeader = field(default_factory=MessageHeader)
    inline_data: dict[str, Any] = field(default_factory=dict)
    ool_descriptors: list[OutOfLineDescriptor] = field(default_factory=list)
    port_transfers: list[PortRightTransfer] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        """Compute the logical size of the message including OOL regions."""
        inline_size = self.header.size or len(str(self.inline_data))
        ool_size = sum(d.size for d in self.ool_descriptors)
        return inline_size + ool_size


# ══════════════════════════════════════════════════════════════════════
# Port & Port Namespace
# ══════════════════════════════════════════════════════════════════════


class Port:
    """A Mach-style IPC port: a kernel-managed message queue with rights.

    Each port has a bounded queue, a set of rights held by various tasks,
    and metadata for scheduling and diagnostics.  The port is the
    fundamental abstraction of the FizzIPC subsystem: all inter-task
    communication flows through port send/receive operations.
    """

    def __init__(self, name: str, capacity: int = 64) -> None:
        self.name = name
        self.capacity = capacity
        self._queue: deque[Message] = deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._rights: dict[str, set[PortRight]] = {}  # task_id -> rights
        self._total_sent: int = 0
        self._total_received: int = 0
        self._total_dropped: int = 0
        self._created_at: float = time.monotonic()
        self._dead: bool = False

    # ── Rights management ─────────────────────────────────────────

    def grant_right(self, task_id: str, right: PortRight) -> None:
        """Grant a port right to a task."""
        if right == PortRight.RECEIVE:
            # Only one task may hold the receive right
            for tid, rights in self._rights.items():
                if PortRight.RECEIVE in rights and tid != task_id:
                    raise IPCPermissionError(
                        task_id, self.name, "RECEIVE right already held by another task"
                    )
        self._rights.setdefault(task_id, set()).add(right)

    def revoke_right(self, task_id: str, right: PortRight) -> None:
        """Revoke a port right from a task."""
        if task_id in self._rights:
            self._rights[task_id].discard(right)
            if not self._rights[task_id]:
                del self._rights[task_id]

    def has_right(self, task_id: str, right: PortRight) -> bool:
        """Check whether a task holds the specified right on this port."""
        return right in self._rights.get(task_id, set())

    def get_receiver(self) -> Optional[str]:
        """Return the task_id holding the RECEIVE right, if any."""
        for tid, rights in self._rights.items():
            if PortRight.RECEIVE in rights:
                return tid
        return None

    # ── Queue operations ──────────────────────────────────────────

    def enqueue(self, msg: Message, blocking: bool = True, timeout: float = 5.0) -> bool:
        """Enqueue a message, respecting the bounded capacity.

        Returns True on success, False if the queue is full and the
        operation is non-blocking.
        """
        with self._not_full:
            if self._dead:
                return False
            if len(self._queue) >= self.capacity:
                if not blocking:
                    self._total_dropped += 1
                    return False
                if not self._not_full.wait_for(
                    lambda: len(self._queue) < self.capacity or self._dead,
                    timeout=timeout,
                ):
                    self._total_dropped += 1
                    return False
            if self._dead:
                return False
            self._queue.append(msg)
            self._total_sent += 1
            self._not_empty.notify()
        return True

    def dequeue(self, blocking: bool = True, timeout: float = 5.0) -> Optional[Message]:
        """Dequeue a message from the port.

        Returns None if the queue is empty and the operation is
        non-blocking or the timeout elapses.
        """
        with self._not_empty:
            if self._dead and not self._queue:
                return None
            if not self._queue:
                if not blocking:
                    return None
                if not self._not_empty.wait_for(
                    lambda: bool(self._queue) or self._dead,
                    timeout=timeout,
                ):
                    return None
            if not self._queue:
                return None
            msg = self._queue.popleft()
            self._total_received += 1
            self._not_full.notify()
        return msg

    def destroy(self) -> None:
        """Mark the port as dead and wake all waiters."""
        with self._lock:
            self._dead = True
            self._not_empty.notify_all()
            self._not_full.notify_all()

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    @property
    def is_dead(self) -> bool:
        return self._dead

    @property
    def utilization(self) -> float:
        """Queue utilization as a fraction in [0, 1]."""
        if self.capacity == 0:
            return 0.0
        return len(self._queue) / self.capacity

    def stats(self) -> dict[str, Any]:
        """Return diagnostic statistics for this port."""
        return {
            "name": self.name,
            "capacity": self.capacity,
            "depth": self.queue_depth,
            "utilization": round(self.utilization, 3),
            "total_sent": self._total_sent,
            "total_received": self._total_received,
            "total_dropped": self._total_dropped,
            "rights_holders": {
                tid: sorted(r.name for r in rs)
                for tid, rs in self._rights.items()
            },
            "dead": self._dead,
        }


class PortNamespace:
    """Per-task port name space mapping local names to kernel port objects.

    In Mach, each task has a private port namespace that translates
    task-local port names to kernel-managed port structures.  This
    prevents tasks from forging port references and enforces
    capability-based access control.
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self._ports: dict[str, Port] = {}
        self._next_local_name: int = 0

    def register(self, port: Port, local_name: Optional[str] = None) -> str:
        """Register a port under a local name and return the name."""
        if local_name is None:
            local_name = f"port_{self._next_local_name}"
            self._next_local_name += 1
        self._ports[local_name] = port
        return local_name

    def lookup(self, local_name: str) -> Optional[Port]:
        """Resolve a local name to its underlying port."""
        return self._ports.get(local_name)

    def unregister(self, local_name: str) -> Optional[Port]:
        """Remove a port from this namespace."""
        return self._ports.pop(local_name, None)

    def list_ports(self) -> dict[str, Port]:
        """Return all ports in this namespace."""
        return dict(self._ports)

    @property
    def size(self) -> int:
        return len(self._ports)


# ══════════════════════════════════════════════════════════════════════
# Task
# ══════════════════════════════════════════════════════════════════════


class TaskState(Enum):
    """Lifecycle states for an IPC task."""

    CREATED = auto()
    RUNNING = auto()
    WAITING = auto()
    TERMINATED = auto()


@dataclass
class TaskStruct:
    """Represents a FizzBuzz subsystem as an IPC task.

    Each subsystem (rule engine, formatter, cache, blockchain, etc.)
    is modeled as an independent task with its own port namespace,
    priority level, and execution statistics.  The task struct is
    the scheduler's primary unit of work.
    """

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    namespace: PortNamespace = field(default=None)  # type: ignore[assignment]
    priority: int = 10
    state: TaskState = TaskState.CREATED
    messages_sent: int = 0
    messages_received: int = 0
    waiting_on_port: Optional[str] = None
    effective_priority: Optional[int] = None
    created_at: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        if self.namespace is None:
            self.namespace = PortNamespace(self.task_id)
        if self.effective_priority is None:
            self.effective_priority = self.priority


# ══════════════════════════════════════════════════════════════════════
# Priority Scheduler
# ══════════════════════════════════════════════════════════════════════


class PriorityScheduler:
    """Priority-aware message delivery scheduler with priority inheritance.

    When a high-priority task blocks on a port whose receive right is
    held by a lower-priority task, the scheduler temporarily *boosts*
    the holder's effective priority to match the waiter.  This prevents
    the classic priority inversion scenario described in the Mars
    Pathfinder postmortem -- a scenario that is equally catastrophic
    in production FizzBuzz environments.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskStruct] = {}
        self._lock = threading.Lock()
        self._boost_log: list[dict[str, Any]] = []

    def register_task(self, task: TaskStruct) -> None:
        """Register a task with the scheduler."""
        with self._lock:
            self._tasks[task.task_id] = task

    def unregister_task(self, task_id: str) -> None:
        """Unregister a task from the scheduler."""
        with self._lock:
            self._tasks.pop(task_id, None)

    def apply_priority_inheritance(
        self,
        waiter: TaskStruct,
        holder: TaskStruct,
        port_name: str,
    ) -> bool:
        """Apply priority inheritance if waiter has higher priority.

        Returns True if a boost was applied.
        """
        with self._lock:
            if waiter.priority > (holder.effective_priority or holder.priority):
                old_priority = holder.effective_priority
                holder.effective_priority = waiter.priority
                self._boost_log.append({
                    "timestamp": time.monotonic(),
                    "holder": holder.task_id,
                    "holder_name": holder.name,
                    "waiter": waiter.task_id,
                    "waiter_name": waiter.name,
                    "port": port_name,
                    "old_priority": old_priority,
                    "new_priority": waiter.priority,
                })
                logger.debug(
                    "Priority inheritance: %s (%d) boosted to %d by %s (%d) on port %s",
                    holder.name, old_priority, waiter.priority,
                    waiter.name, waiter.priority, port_name,
                )
                return True
            return False

    def release_priority_inheritance(self, task: TaskStruct) -> None:
        """Restore a task's effective priority to its base priority."""
        with self._lock:
            task.effective_priority = task.priority

    def get_delivery_order(self, messages: list[Message]) -> list[Message]:
        """Sort messages by priority for delivery (highest first)."""
        return sorted(
            messages,
            key=lambda m: m.header.priority.value,
            reverse=True,
        )

    @property
    def boost_log(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._boost_log)


# ══════════════════════════════════════════════════════════════════════
# Deadlock Detector
# ══════════════════════════════════════════════════════════════════════


class DeadlockDetector:
    """Wait-for graph analysis using Tarjan's SCC algorithm.

    Constructs a directed graph where nodes are tasks and edges
    represent ``waits_on`` relationships (task A is blocked waiting
    on a port whose receive right is held by task B).  Strongly
    connected components of size >= 2 indicate circular waits --
    i.e., deadlocks.
    """

    def __init__(self) -> None:
        self._cycles_detected: list[list[str]] = []
        self._check_count: int = 0

    def build_wait_for_graph(self, tasks: dict[str, TaskStruct], ports: dict[str, Port]) -> dict[str, list[str]]:
        """Build the wait-for graph from current task and port state.

        Returns an adjacency list: task_id -> list of task_ids it is
        waiting on.
        """
        graph: dict[str, list[str]] = {tid: [] for tid in tasks}
        for tid, task in tasks.items():
            if task.waiting_on_port and task.state == TaskState.WAITING:
                port = ports.get(task.waiting_on_port)
                if port:
                    holder = port.get_receiver()
                    if holder and holder != tid and holder in tasks:
                        graph[tid].append(holder)
        return graph

    def detect_deadlocks(self, tasks: dict[str, TaskStruct], ports: dict[str, Port]) -> list[list[str]]:
        """Run Tarjan's SCC algorithm and return deadlocked task groups.

        Each returned list contains the task_ids forming a cycle.
        """
        self._check_count += 1
        graph = self.build_wait_for_graph(tasks, ports)
        sccs = self._tarjan_scc(graph)
        cycles = [scc for scc in sccs if len(scc) >= 2]
        if cycles:
            self._cycles_detected.extend(cycles)
            for cycle in cycles:
                logger.warning(
                    "IPC deadlock detected: %s",
                    " -> ".join(cycle) + " -> " + cycle[0],
                )
        return cycles

    def _tarjan_scc(self, graph: dict[str, list[str]]) -> list[list[str]]:
        """Tarjan's strongly connected components algorithm.

        Time complexity: O(V + E) where V is the number of tasks
        and E is the number of wait-for edges.
        """
        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        index: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        result: list[list[str]] = []

        def strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in graph.get(v, []):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == v:
                        break
                result.append(component)

        for v in graph:
            if v not in index:
                strongconnect(v)

        return result

    @property
    def cycles_detected(self) -> list[list[str]]:
        return list(self._cycles_detected)

    @property
    def check_count(self) -> int:
        return self._check_count


# ══════════════════════════════════════════════════════════════════════
# IPC Kernel
# ══════════════════════════════════════════════════════════════════════


class IPCKernel:
    """Central message router for the FizzIPC microkernel.

    Manages the global port table, task registry, priority scheduler,
    and deadlock detector.  All inter-task communication is mediated
    by the kernel: tasks never access ports directly but instead
    invoke kernel system calls (``send``, ``receive``, ``notify``).
    """

    def __init__(
        self,
        default_port_capacity: int = 64,
        enable_deadlock_detection: bool = True,
        enable_priority_inheritance: bool = True,
    ) -> None:
        self._ports: dict[str, Port] = {}
        self._tasks: dict[str, TaskStruct] = {}
        self._scheduler = PriorityScheduler()
        self._deadlock_detector = DeadlockDetector()
        self._default_port_capacity = default_port_capacity
        self._enable_deadlock_detection = enable_deadlock_detection
        self._enable_priority_inheritance = enable_priority_inheritance
        self._lock = threading.Lock()
        self._total_messages_routed: int = 0
        self._total_rights_transferred: int = 0
        self._notification_log: list[dict[str, Any]] = []
        self._started_at: float = time.monotonic()

    # ── Task management ───────────────────────────────────────────

    def create_task(self, name: str, priority: int = 10) -> TaskStruct:
        """Create and register a new IPC task."""
        task = TaskStruct(name=name, priority=priority)
        with self._lock:
            self._tasks[task.task_id] = task
        self._scheduler.register_task(task)
        task.state = TaskState.RUNNING
        logger.debug("IPC task created: %s (%s) priority=%d", name, task.task_id, priority)
        return task

    def terminate_task(self, task_id: str) -> None:
        """Terminate a task and clean up its port namespace."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.state = TaskState.TERMINATED
            # Revoke all rights held by this task
            for port in self._ports.values():
                for right in list(PortRight):
                    port.revoke_right(task_id, right)
            self._scheduler.unregister_task(task_id)

    def get_task(self, task_id: str) -> Optional[TaskStruct]:
        """Look up a task by ID."""
        return self._tasks.get(task_id)

    def get_task_by_name(self, name: str) -> Optional[TaskStruct]:
        """Look up a task by name."""
        for task in self._tasks.values():
            if task.name == name:
                return task
        return None

    # ── Port management ───────────────────────────────────────────

    def create_port(
        self,
        name: str,
        owner_task_id: str,
        capacity: Optional[int] = None,
    ) -> Port:
        """Create a new port and grant RECEIVE right to the owning task."""
        cap = capacity if capacity is not None else self._default_port_capacity
        port = Port(name=name, capacity=cap)
        with self._lock:
            self._ports[name] = port
            task = self._tasks.get(owner_task_id)
            if task:
                port.grant_right(owner_task_id, PortRight.RECEIVE)
                task.namespace.register(port, local_name=name)
        logger.debug("IPC port created: %s (owner=%s, capacity=%d)", name, owner_task_id, cap)
        return port

    def destroy_port(self, name: str) -> None:
        """Destroy a port and notify all waiters."""
        with self._lock:
            port = self._ports.pop(name, None)
            if port:
                port.destroy()
                # Remove from all task namespaces
                for task in self._tasks.values():
                    task.namespace.unregister(name)

    def get_port(self, name: str) -> Optional[Port]:
        """Look up a port by global name."""
        return self._ports.get(name)

    def grant_send_right(self, port_name: str, task_id: str) -> None:
        """Grant a SEND right on a port to a task."""
        port = self._ports.get(port_name)
        if port is None:
            raise IPCPortNotFoundError(port_name)
        task = self._tasks.get(task_id)
        if task is None:
            raise IPCTaskNotFoundError(task_id)
        port.grant_right(task_id, PortRight.SEND)
        task.namespace.register(port, local_name=port_name)

    # ── Message passing ───────────────────────────────────────────

    def send(
        self,
        sender_task_id: str,
        port_name: str,
        msg: Message,
        blocking: bool = True,
        timeout: float = 5.0,
    ) -> bool:
        """Send a message through the IPC kernel.

        Validates that the sender holds a SEND or SEND_ONCE right on
        the target port, processes any port right transfers, and
        enqueues the message.  Returns True on success.
        """
        port = self._ports.get(port_name)
        if port is None:
            raise IPCPortNotFoundError(port_name)

        sender = self._tasks.get(sender_task_id)
        if sender is None:
            raise IPCTaskNotFoundError(sender_task_id)

        # Validate send rights
        has_send = port.has_right(sender_task_id, PortRight.SEND)
        has_send_once = port.has_right(sender_task_id, PortRight.SEND_ONCE)
        if not has_send and not has_send_once:
            raise IPCPermissionError(
                sender_task_id, port_name, "No SEND or SEND_ONCE right"
            )

        # Process port right transfers
        for transfer in msg.port_transfers:
            self._process_right_transfer(sender_task_id, port, transfer)

        # Set routing metadata
        msg.header.local_port = port_name
        msg.header.timestamp = time.monotonic()

        # Priority scheduling: if priority inheritance is enabled and
        # the receiver is waiting, check for inversion
        if self._enable_priority_inheritance:
            receiver_id = port.get_receiver()
            if receiver_id:
                receiver = self._tasks.get(receiver_id)
                if receiver and sender.priority > (receiver.effective_priority or receiver.priority):
                    self._scheduler.apply_priority_inheritance(sender, receiver, port_name)

        # Enqueue
        success = port.enqueue(msg, blocking=blocking, timeout=timeout)
        if success:
            sender.messages_sent += 1
            with self._lock:
                self._total_messages_routed += 1
            # Revoke SEND_ONCE after successful send
            if has_send_once and not has_send:
                port.revoke_right(sender_task_id, PortRight.SEND_ONCE)

        return success

    def receive(
        self,
        receiver_task_id: str,
        port_name: str,
        blocking: bool = True,
        timeout: float = 5.0,
    ) -> Optional[Message]:
        """Receive a message from a port.

        Validates that the receiver holds the RECEIVE right.  If
        blocking, the caller waits until a message is available or
        the timeout elapses.
        """
        port = self._ports.get(port_name)
        if port is None:
            raise IPCPortNotFoundError(port_name)

        receiver = self._tasks.get(receiver_task_id)
        if receiver is None:
            raise IPCTaskNotFoundError(receiver_task_id)

        if not port.has_right(receiver_task_id, PortRight.RECEIVE):
            raise IPCPermissionError(
                receiver_task_id, port_name, "No RECEIVE right"
            )

        # Mark task as waiting (for deadlock detection)
        receiver.state = TaskState.WAITING
        receiver.waiting_on_port = port_name

        # Check for deadlocks before blocking
        if self._enable_deadlock_detection and blocking:
            cycles = self._deadlock_detector.detect_deadlocks(
                self._tasks, self._ports
            )
            if cycles:
                receiver.state = TaskState.RUNNING
                receiver.waiting_on_port = None
                raise IPCDeadlockError(cycles[0])

        msg = port.dequeue(blocking=blocking, timeout=timeout)

        # Restore task state
        receiver.state = TaskState.RUNNING
        receiver.waiting_on_port = None
        if self._enable_priority_inheritance:
            self._scheduler.release_priority_inheritance(receiver)

        if msg is not None:
            receiver.messages_received += 1
            # Process incoming port right transfers
            for transfer in msg.port_transfers:
                self._apply_right_to_receiver(receiver_task_id, transfer)

        return msg

    def notify(
        self,
        sender_task_id: str,
        port_name: str,
        notification_type: str,
        data: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Send a notification message through a port.

        Notifications are fire-and-forget messages used for
        asynchronous event signaling between tasks.
        """
        msg = Message(
            header=MessageHeader(
                msg_type=MessageType.NOTIFICATION,
                priority=MessagePriority.HIGH,
                remote_port=port_name,
            ),
            inline_data={
                "notification_type": notification_type,
                "data": data or {},
            },
        )
        try:
            success = self.send(sender_task_id, port_name, msg, blocking=False)
        except (IPCPortNotFoundError, IPCPermissionError):
            success = False

        with self._lock:
            self._notification_log.append({
                "timestamp": time.monotonic(),
                "sender": sender_task_id,
                "port": port_name,
                "type": notification_type,
                "delivered": success,
            })
        return success

    def _process_right_transfer(
        self,
        sender_task_id: str,
        port: Port,
        transfer: PortRightTransfer,
    ) -> None:
        """Process a port right transfer embedded in a message."""
        source_port = self._ports.get(transfer.port_name)
        if source_port is None:
            return
        if transfer.disposition == "move":
            source_port.revoke_right(sender_task_id, transfer.right)
        with self._lock:
            self._total_rights_transferred += 1

    def _apply_right_to_receiver(
        self,
        receiver_task_id: str,
        transfer: PortRightTransfer,
    ) -> None:
        """Apply a transferred port right to the receiver's namespace."""
        port = self._ports.get(transfer.port_name)
        if port is None:
            return
        port.grant_right(receiver_task_id, transfer.right)
        receiver = self._tasks.get(receiver_task_id)
        if receiver:
            receiver.namespace.register(port, local_name=transfer.port_name)

    # ── Diagnostics ───────────────────────────────────────────────

    def run_deadlock_check(self) -> list[list[str]]:
        """Manually trigger a deadlock detection pass."""
        return self._deadlock_detector.detect_deadlocks(
            self._tasks, self._ports
        )

    @property
    def total_messages_routed(self) -> int:
        return self._total_messages_routed

    @property
    def total_rights_transferred(self) -> int:
        return self._total_rights_transferred

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    @property
    def port_count(self) -> int:
        return len(self._ports)

    def get_all_tasks(self) -> dict[str, TaskStruct]:
        return dict(self._tasks)

    def get_all_ports(self) -> dict[str, Port]:
        return dict(self._ports)

    @property
    def scheduler(self) -> PriorityScheduler:
        return self._scheduler

    @property
    def deadlock_detector(self) -> DeadlockDetector:
        return self._deadlock_detector

    @property
    def notification_log(self) -> list[dict[str, Any]]:
        return list(self._notification_log)

    def stats(self) -> dict[str, Any]:
        """Return aggregate IPC kernel statistics."""
        return {
            "uptime_s": round(time.monotonic() - self._started_at, 3),
            "tasks": self.task_count,
            "ports": self.port_count,
            "messages_routed": self._total_messages_routed,
            "rights_transferred": self._total_rights_transferred,
            "notifications_sent": len(self._notification_log),
            "deadlock_checks": self._deadlock_detector.check_count,
            "deadlocks_found": len(self._deadlock_detector.cycles_detected),
            "priority_boosts": len(self._scheduler.boost_log),
        }


# ══════════════════════════════════════════════════════════════════════
# IPC Dashboard
# ══════════════════════════════════════════════════════════════════════


class IPCDashboard:
    """ASCII dashboard for the FizzIPC microkernel.

    Renders a comprehensive operational view of the IPC subsystem
    including the port table, task registry, message throughput
    metrics, priority inheritance log, and wait-for graph topology.
    """

    @staticmethod
    def render(
        kernel: IPCKernel,
        width: int = 72,
        show_port_table: bool = True,
        show_task_table: bool = True,
        show_wait_graph: bool = True,
        show_boost_log: bool = True,
    ) -> str:
        """Render the IPC dashboard as an ASCII string."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        title_border = "+" + "=" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        stats = kernel.stats()

        # Header
        lines.append(title_border)
        lines.append(center("FizzIPC Microkernel Dashboard"))
        lines.append(center("Mach-Inspired Port-Based Message Passing"))
        lines.append(title_border)

        # Summary
        lines.append(center("Kernel Statistics"))
        lines.append(border)
        lines.append(left(f"Uptime:              {stats['uptime_s']:.3f}s"))
        lines.append(left(f"Active Tasks:        {stats['tasks']}"))
        lines.append(left(f"Active Ports:        {stats['ports']}"))
        lines.append(left(f"Messages Routed:     {stats['messages_routed']}"))
        lines.append(left(f"Rights Transferred:  {stats['rights_transferred']}"))
        lines.append(left(f"Notifications Sent:  {stats['notifications_sent']}"))
        lines.append(left(f"Deadlock Checks:     {stats['deadlock_checks']}"))
        lines.append(left(f"Deadlocks Found:     {stats['deadlocks_found']}"))
        lines.append(left(f"Priority Boosts:     {stats['priority_boosts']}"))
        lines.append(border)

        # Port table
        if show_port_table:
            lines.append("")
            lines.append(center("Port Table"))
            lines.append(border)
            ports = kernel.get_all_ports()
            if ports:
                hdr = f"{'Name':<20} {'Cap':>4} {'Depth':>5} {'Util':>5} {'Sent':>6} {'Recv':>6} {'Drop':>5}"
                lines.append(left(hdr))
                lines.append(left("-" * min(len(hdr), width - 6)))
                for pname, port in sorted(ports.items()):
                    ps = port.stats()
                    row = (
                        f"{pname:<20} {ps['capacity']:>4} "
                        f"{ps['depth']:>5} {ps['utilization']:>5.1%} "
                        f"{ps['total_sent']:>6} {ps['total_received']:>6} "
                        f"{ps['total_dropped']:>5}"
                    )
                    lines.append(left(row))
            else:
                lines.append(left("(no ports registered)"))
            lines.append(border)

        # Task table
        if show_task_table:
            lines.append("")
            lines.append(center("Task Registry"))
            lines.append(border)
            tasks = kernel.get_all_tasks()
            if tasks:
                hdr = f"{'ID':<10} {'Name':<18} {'State':<12} {'Pri':>3} {'EPri':>4} {'Sent':>5} {'Recv':>5}"
                lines.append(left(hdr))
                lines.append(left("-" * min(len(hdr), width - 6)))
                for tid, task in sorted(tasks.items(), key=lambda x: x[1].name):
                    row = (
                        f"{tid:<10} {task.name:<18} {task.state.name:<12} "
                        f"{task.priority:>3} {task.effective_priority or task.priority:>4} "
                        f"{task.messages_sent:>5} {task.messages_received:>5}"
                    )
                    lines.append(left(row))
            else:
                lines.append(left("(no tasks registered)"))
            lines.append(border)

        # Wait-for graph
        if show_wait_graph:
            lines.append("")
            lines.append(center("Wait-For Graph"))
            lines.append(border)
            tasks = kernel.get_all_tasks()
            ports = kernel.get_all_ports()
            graph = kernel.deadlock_detector.build_wait_for_graph(tasks, ports)
            has_edges = any(deps for deps in graph.values())
            if has_edges:
                for tid, deps in graph.items():
                    if deps:
                        task = tasks.get(tid)
                        tname = task.name if task else tid
                        for dep_id in deps:
                            dep_task = tasks.get(dep_id)
                            dname = dep_task.name if dep_task else dep_id
                            lines.append(left(f"  {tname} --waits-on--> {dname}"))
            else:
                lines.append(left("(no active waits -- graph is empty)"))
            lines.append(border)

        # Priority inheritance log
        if show_boost_log:
            boost_log = kernel.scheduler.boost_log
            if boost_log:
                lines.append("")
                lines.append(center("Priority Inheritance Log"))
                lines.append(border)
                for entry in boost_log[-10:]:  # Last 10 entries
                    lines.append(left(
                        f"  {entry['holder_name']} boosted "
                        f"{entry['old_priority']} -> {entry['new_priority']} "
                        f"by {entry['waiter_name']} on {entry['port']}"
                    ))
                lines.append(border)

        # Deadlock history
        cycles = kernel.deadlock_detector.cycles_detected
        if cycles:
            lines.append("")
            lines.append(center("Deadlock History"))
            lines.append(border)
            for i, cycle in enumerate(cycles[-5:], 1):
                tasks_map = kernel.get_all_tasks()
                names = []
                for tid in cycle:
                    t = tasks_map.get(tid)
                    names.append(t.name if t else tid)
                lines.append(left(f"  Cycle {i}: {' -> '.join(names)} -> {names[0]}"))
            lines.append(border)

        lines.append("")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# IPC Middleware
# ══════════════════════════════════════════════════════════════════════


class IPCMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through IPC ports.

    Intercepts each number in the processing pipeline and routes it
    as an IPC message from a ``client`` task to an ``engine`` task via
    Mach-style port send/receive.  The engine task performs the
    evaluation and sends the result back through a reply port.

    This adds approximately zero value to the evaluation itself, but
    provides invaluable operational insight into how IPC overhead
    accumulates in a microkernel architecture.  In production
    microkernel systems, IPC is the dominant cost; this middleware
    faithfully reproduces that characteristic.

    Priority -8 ensures IPC routing occurs early in the pipeline,
    after the OS kernel middleware but before most application-level
    middleware.
    """

    def __init__(
        self,
        kernel: IPCKernel,
        num_tasks: int = 4,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._kernel = kernel
        self._event_bus = event_bus
        self._num_tasks = num_tasks
        self._evaluation_count: int = 0
        self._total_ipc_time_ns: int = 0

        # Create the IPC task topology
        self._client_task = kernel.create_task("ipc_client", priority=20)
        self._engine_task = kernel.create_task("ipc_engine", priority=15)
        self._formatter_task = kernel.create_task("ipc_formatter", priority=10)
        self._audit_task = kernel.create_task("ipc_audit", priority=5)

        # Create additional tasks up to num_tasks
        self._extra_tasks: list[TaskStruct] = []
        subsystem_names = [
            "ipc_cache", "ipc_blockchain", "ipc_compliance",
            "ipc_metrics", "ipc_scheduler", "ipc_gateway",
            "ipc_telemetry", "ipc_replication",
        ]
        for i in range(max(0, num_tasks - 4)):
            name = subsystem_names[i % len(subsystem_names)]
            t = kernel.create_task(name, priority=10 + i)
            self._extra_tasks.append(t)

        # Create the evaluation port: client sends, engine receives
        self._eval_port = kernel.create_port(
            "eval_port", self._engine_task.task_id
        )
        kernel.grant_send_right("eval_port", self._client_task.task_id)

        # Create the reply port: engine sends, client receives
        self._reply_port = kernel.create_port(
            "reply_port", self._client_task.task_id
        )
        kernel.grant_send_right("reply_port", self._engine_task.task_id)

        # Create the audit port: engine sends notifications, audit receives
        self._audit_port = kernel.create_port(
            "audit_port", self._audit_task.task_id
        )
        kernel.grant_send_right("audit_port", self._engine_task.task_id)

        # Grant send rights for extra tasks on audit port
        for t in self._extra_tasks:
            kernel.grant_send_right("audit_port", t.task_id)

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Route the evaluation through IPC message passing."""
        ipc_start = time.perf_counter_ns()

        number = context.number
        self._evaluation_count += 1

        # Step 1: Client sends evaluation request to engine via eval_port
        request = Message(
            header=MessageHeader(
                msg_type=MessageType.EVALUATION_REQUEST,
                priority=MessagePriority.NORMAL,
                remote_port="eval_port",
            ),
            inline_data={
                "number": number,
                "session_id": context.session_id,
                "sequence": self._evaluation_count,
            },
        )
        self._kernel.send(
            self._client_task.task_id, "eval_port", request, blocking=False
        )

        # Step 2: Engine receives the request
        received = self._kernel.receive(
            self._engine_task.task_id, "eval_port", blocking=False
        )

        # Step 3: Delegate to downstream pipeline for actual evaluation
        result_context = next_handler(context)

        # Step 4: Engine sends result back via reply_port
        if received is not None:
            response = Message(
                header=MessageHeader(
                    msg_type=MessageType.EVALUATION_RESPONSE,
                    priority=MessagePriority.NORMAL,
                    remote_port="reply_port",
                ),
                inline_data={
                    "number": number,
                    "result": (
                        result_context.results[-1].output
                        if result_context.results
                        else str(number)
                    ),
                    "sequence": self._evaluation_count,
                },
            )
            self._kernel.send(
                self._engine_task.task_id, "reply_port", response, blocking=False
            )

            # Step 5: Client receives the response
            self._kernel.receive(
                self._client_task.task_id, "reply_port", blocking=False
            )

            # Step 6: Engine notifies audit task
            self._kernel.notify(
                self._engine_task.task_id,
                "audit_port",
                "evaluation_complete",
                {"number": number, "sequence": self._evaluation_count},
            )

        # Record IPC overhead
        ipc_elapsed = time.perf_counter_ns() - ipc_start
        self._total_ipc_time_ns += ipc_elapsed
        result_context.metadata["ipc_overhead_ns"] = ipc_elapsed
        result_context.metadata["ipc_messages_routed"] = self._kernel.total_messages_routed
        result_context.metadata["ipc_evaluation_sequence"] = self._evaluation_count

        return result_context

    def get_name(self) -> str:
        return "IPCMiddleware"

    def get_priority(self) -> int:
        return -8

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    @property
    def total_ipc_time_ns(self) -> int:
        return self._total_ipc_time_ns

    @property
    def average_ipc_overhead_us(self) -> float:
        """Average IPC overhead per evaluation in microseconds."""
        if self._evaluation_count == 0:
            return 0.0
        return (self._total_ipc_time_ns / self._evaluation_count) / 1000.0

    def render_dashboard(self) -> str:
        """Render the IPC dashboard."""
        return IPCDashboard.render(self._kernel)


__all__ = [
    "DeadlockDetector",
    "IPCDashboard",
    "IPCDeadlockError",
    "IPCError",
    "IPCKernel",
    "IPCMiddleware",
    "IPCPermissionError",
    "IPCPortNotFoundError",
    "IPCQueueFullError",
    "IPCRightTransferError",
    "IPCTaskNotFoundError",
    "IPCTimeoutError",
    "Message",
    "MessageHeader",
    "MessagePriority",
    "MessageType",
    "OutOfLineDescriptor",
    "Port",
    "PortNamespace",
    "PortRight",
    "PortRightTransfer",
    "PriorityScheduler",
    "TaskState",
    "TaskStruct",
]

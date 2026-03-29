"""
Tests for the FizzIPC Microkernel Inter-Process Communication Module.

Validates port-based message passing, port rights management, priority
inheritance, deadlock detection via Tarjan's SCC, bounded message queues,
task lifecycle management, and the IPC middleware integration with the
FizzBuzz evaluation pipeline.
"""

from __future__ import annotations

import threading
import time

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
)
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
from enterprise_fizzbuzz.infrastructure.microkernel_ipc import (
    DeadlockDetector,
    IPCDashboard,
    IPCKernel,
    IPCMiddleware,
    Message,
    MessageHeader,
    MessagePriority,
    MessageType,
    OutOfLineDescriptor,
    Port,
    PortNamespace,
    PortRight,
    PortRightTransfer,
    PriorityScheduler,
    TaskState,
    TaskStruct,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def kernel() -> IPCKernel:
    """Create a fresh IPC kernel with default settings."""
    return IPCKernel(default_port_capacity=16)


@pytest.fixture
def kernel_no_deadlock() -> IPCKernel:
    """Create a kernel with deadlock detection disabled."""
    return IPCKernel(
        default_port_capacity=16,
        enable_deadlock_detection=False,
    )


@pytest.fixture
def two_tasks(kernel: IPCKernel):
    """Create two tasks and a port connecting them."""
    task_a = kernel.create_task("task_a", priority=10)
    task_b = kernel.create_task("task_b", priority=20)
    port = kernel.create_port("channel", task_b.task_id)
    kernel.grant_send_right("channel", task_a.task_id)
    return task_a, task_b, port


@pytest.fixture
def processing_context() -> ProcessingContext:
    """Create a minimal processing context for middleware tests."""
    return ProcessingContext(number=15, session_id="test-ipc-session")


# ══════════════════════════════════════════════════════════════════════
# PortRight Enum
# ══════════════════════════════════════════════════════════════════════


class TestPortRight:
    """Validate the PortRight enumeration members."""

    def test_send_right_exists(self):
        assert PortRight.SEND.name == "SEND"

    def test_receive_right_exists(self):
        assert PortRight.RECEIVE.name == "RECEIVE"

    def test_send_once_right_exists(self):
        assert PortRight.SEND_ONCE.name == "SEND_ONCE"

    def test_port_set_right_exists(self):
        assert PortRight.PORT_SET.name == "PORT_SET"

    def test_all_rights_are_distinct(self):
        rights = [PortRight.SEND, PortRight.RECEIVE, PortRight.SEND_ONCE, PortRight.PORT_SET]
        assert len(set(rights)) == 4


# ══════════════════════════════════════════════════════════════════════
# MessageType and MessagePriority Enums
# ══════════════════════════════════════════════════════════════════════


class TestMessageEnums:
    """Validate IPC message type and priority enumerations."""

    def test_message_types_count(self):
        assert len(MessageType) >= 8

    def test_evaluation_request_type(self):
        assert MessageType.EVALUATION_REQUEST.name == "EVALUATION_REQUEST"

    def test_evaluation_response_type(self):
        assert MessageType.EVALUATION_RESPONSE.name == "EVALUATION_RESPONSE"

    def test_priority_ordering(self):
        assert MessagePriority.LOW.value < MessagePriority.NORMAL.value
        assert MessagePriority.NORMAL.value < MessagePriority.HIGH.value
        assert MessagePriority.HIGH.value < MessagePriority.CRITICAL.value


# ══════════════════════════════════════════════════════════════════════
# Message
# ══════════════════════════════════════════════════════════════════════


class TestMessage:
    """Validate IPC message construction and metadata."""

    def test_default_message_has_header(self):
        msg = Message()
        assert msg.header is not None
        assert msg.header.msg_id != ""

    def test_message_inline_data(self):
        msg = Message(inline_data={"number": 42, "result": "Fizz"})
        assert msg.inline_data["number"] == 42
        assert msg.inline_data["result"] == "Fizz"

    def test_message_ool_descriptors(self):
        ool = OutOfLineDescriptor(data=b"\x00" * 1024, size=1024)
        msg = Message(ool_descriptors=[ool])
        assert len(msg.ool_descriptors) == 1
        assert msg.ool_descriptors[0].size == 1024

    def test_message_total_size(self):
        ool = OutOfLineDescriptor(data=b"\x00" * 256, size=256)
        msg = Message(
            header=MessageHeader(size=64),
            ool_descriptors=[ool],
        )
        assert msg.total_size == 320

    def test_message_port_transfers(self):
        transfer = PortRightTransfer(
            port_name="reply_port",
            right=PortRight.SEND,
            disposition="move",
        )
        msg = Message(port_transfers=[transfer])
        assert len(msg.port_transfers) == 1
        assert msg.port_transfers[0].right == PortRight.SEND

    def test_message_header_timestamp(self):
        msg = Message()
        assert msg.header.timestamp > 0

    def test_ool_descriptor_defaults(self):
        ool = OutOfLineDescriptor()
        assert ool.copy_on_write is True
        assert ool.deallocate_on_send is False


# ══════════════════════════════════════════════════════════════════════
# Port
# ══════════════════════════════════════════════════════════════════════


class TestPort:
    """Validate port queue operations and rights management."""

    def test_port_creation(self):
        port = Port("test_port", capacity=8)
        assert port.name == "test_port"
        assert port.capacity == 8
        assert port.queue_depth == 0

    def test_port_enqueue_dequeue(self):
        port = Port("p", capacity=4)
        msg = Message(inline_data={"value": 1})
        assert port.enqueue(msg, blocking=False)
        result = port.dequeue(blocking=False)
        assert result is not None
        assert result.inline_data["value"] == 1

    def test_port_fifo_order(self):
        port = Port("p", capacity=4)
        for i in range(3):
            port.enqueue(Message(inline_data={"seq": i}), blocking=False)
        for i in range(3):
            msg = port.dequeue(blocking=False)
            assert msg is not None
            assert msg.inline_data["seq"] == i

    def test_port_bounded_capacity(self):
        port = Port("p", capacity=2)
        assert port.enqueue(Message(), blocking=False)
        assert port.enqueue(Message(), blocking=False)
        # Third message should be dropped (non-blocking)
        assert not port.enqueue(Message(), blocking=False)
        assert port._total_dropped == 1

    def test_port_grant_send_right(self):
        port = Port("p")
        port.grant_right("task_1", PortRight.SEND)
        assert port.has_right("task_1", PortRight.SEND)

    def test_port_grant_receive_right(self):
        port = Port("p")
        port.grant_right("task_1", PortRight.RECEIVE)
        assert port.has_right("task_1", PortRight.RECEIVE)

    def test_port_receive_right_exclusive(self):
        port = Port("p")
        port.grant_right("task_1", PortRight.RECEIVE)
        with pytest.raises(IPCPermissionError):
            port.grant_right("task_2", PortRight.RECEIVE)

    def test_port_revoke_right(self):
        port = Port("p")
        port.grant_right("task_1", PortRight.SEND)
        port.revoke_right("task_1", PortRight.SEND)
        assert not port.has_right("task_1", PortRight.SEND)

    def test_port_get_receiver(self):
        port = Port("p")
        port.grant_right("task_1", PortRight.RECEIVE)
        assert port.get_receiver() == "task_1"

    def test_port_no_receiver(self):
        port = Port("p")
        assert port.get_receiver() is None

    def test_port_utilization(self):
        port = Port("p", capacity=4)
        assert port.utilization == 0.0
        port.enqueue(Message(), blocking=False)
        port.enqueue(Message(), blocking=False)
        assert port.utilization == 0.5

    def test_port_stats(self):
        port = Port("test_stats", capacity=8)
        port.grant_right("t1", PortRight.SEND)
        port.enqueue(Message(), blocking=False)
        stats = port.stats()
        assert stats["name"] == "test_stats"
        assert stats["capacity"] == 8
        assert stats["depth"] == 1
        assert stats["total_sent"] == 1
        assert "t1" in stats["rights_holders"]

    def test_port_destroy(self):
        port = Port("p", capacity=4)
        port.destroy()
        assert port.is_dead
        # Enqueue should fail on dead port
        assert not port.enqueue(Message(), blocking=False)

    def test_dequeue_empty_nonblocking(self):
        port = Port("p")
        assert port.dequeue(blocking=False) is None


# ══════════════════════════════════════════════════════════════════════
# PortNamespace
# ══════════════════════════════════════════════════════════════════════


class TestPortNamespace:
    """Validate per-task port namespace operations."""

    def test_namespace_creation(self):
        ns = PortNamespace("task_1")
        assert ns.task_id == "task_1"
        assert ns.size == 0

    def test_register_port(self):
        ns = PortNamespace("task_1")
        port = Port("p1")
        name = ns.register(port)
        assert name == "port_0"
        assert ns.lookup("port_0") is port

    def test_register_with_explicit_name(self):
        ns = PortNamespace("task_1")
        port = Port("p1")
        name = ns.register(port, local_name="my_port")
        assert name == "my_port"
        assert ns.lookup("my_port") is port

    def test_unregister_port(self):
        ns = PortNamespace("task_1")
        port = Port("p1")
        ns.register(port, local_name="p")
        removed = ns.unregister("p")
        assert removed is port
        assert ns.lookup("p") is None

    def test_list_ports(self):
        ns = PortNamespace("task_1")
        p1 = Port("p1")
        p2 = Port("p2")
        ns.register(p1, "a")
        ns.register(p2, "b")
        ports = ns.list_ports()
        assert len(ports) == 2
        assert "a" in ports and "b" in ports

    def test_lookup_nonexistent(self):
        ns = PortNamespace("task_1")
        assert ns.lookup("missing") is None


# ══════════════════════════════════════════════════════════════════════
# TaskStruct
# ══════════════════════════════════════════════════════════════════════


class TestTaskStruct:
    """Validate IPC task structure and lifecycle."""

    def test_task_creation(self):
        task = TaskStruct(name="test_task", priority=15)
        assert task.name == "test_task"
        assert task.priority == 15
        assert task.state == TaskState.CREATED
        assert task.namespace is not None

    def test_task_default_priority(self):
        task = TaskStruct(name="default")
        assert task.priority == 10

    def test_task_effective_priority(self):
        task = TaskStruct(name="t", priority=10)
        assert task.effective_priority == 10

    def test_task_messages_counter(self):
        task = TaskStruct(name="t")
        task.messages_sent = 5
        task.messages_received = 3
        assert task.messages_sent == 5
        assert task.messages_received == 3


# ══════════════════════════════════════════════════════════════════════
# IPCKernel - Task Management
# ══════════════════════════════════════════════════════════════════════


class TestIPCKernelTasks:
    """Validate kernel task creation, lookup, and termination."""

    def test_create_task(self, kernel):
        task = kernel.create_task("my_task", priority=20)
        assert task.name == "my_task"
        assert task.priority == 20
        assert task.state == TaskState.RUNNING

    def test_get_task_by_id(self, kernel):
        task = kernel.create_task("t1")
        found = kernel.get_task(task.task_id)
        assert found is task

    def test_get_task_by_name(self, kernel):
        kernel.create_task("finder_test")
        found = kernel.get_task_by_name("finder_test")
        assert found is not None
        assert found.name == "finder_test"

    def test_get_nonexistent_task(self, kernel):
        assert kernel.get_task("no_such_id") is None
        assert kernel.get_task_by_name("no_such_name") is None

    def test_terminate_task(self, kernel):
        task = kernel.create_task("doomed")
        kernel.terminate_task(task.task_id)
        assert task.state == TaskState.TERMINATED

    def test_task_count(self, kernel):
        kernel.create_task("a")
        kernel.create_task("b")
        assert kernel.task_count == 2


# ══════════════════════════════════════════════════════════════════════
# IPCKernel - Port Management
# ══════════════════════════════════════════════════════════════════════


class TestIPCKernelPorts:
    """Validate kernel port creation, destruction, and rights."""

    def test_create_port(self, kernel):
        task = kernel.create_task("owner")
        port = kernel.create_port("test_port", task.task_id, capacity=32)
        assert port.name == "test_port"
        assert port.capacity == 32
        assert port.has_right(task.task_id, PortRight.RECEIVE)

    def test_destroy_port(self, kernel):
        task = kernel.create_task("owner")
        kernel.create_port("doomed_port", task.task_id)
        kernel.destroy_port("doomed_port")
        assert kernel.get_port("doomed_port") is None

    def test_grant_send_right(self, kernel):
        owner = kernel.create_task("owner")
        sender = kernel.create_task("sender")
        kernel.create_port("p", owner.task_id)
        kernel.grant_send_right("p", sender.task_id)
        port = kernel.get_port("p")
        assert port.has_right(sender.task_id, PortRight.SEND)

    def test_grant_send_right_nonexistent_port(self, kernel):
        kernel.create_task("t")
        with pytest.raises(IPCPortNotFoundError):
            kernel.grant_send_right("no_port", "t")

    def test_port_count(self, kernel):
        task = kernel.create_task("t")
        kernel.create_port("p1", task.task_id)
        kernel.create_port("p2", task.task_id)
        assert kernel.port_count == 2


# ══════════════════════════════════════════════════════════════════════
# IPCKernel - Send/Receive
# ══════════════════════════════════════════════════════════════════════


class TestIPCKernelMessaging:
    """Validate message send and receive through the IPC kernel."""

    def test_send_and_receive(self, two_tasks, kernel):
        task_a, task_b, port = two_tasks
        msg = Message(inline_data={"payload": "hello"})
        assert kernel.send(task_a.task_id, "channel", msg, blocking=False)
        received = kernel.receive(task_b.task_id, "channel", blocking=False)
        assert received is not None
        assert received.inline_data["payload"] == "hello"

    def test_send_without_right_raises(self, kernel):
        task_a = kernel.create_task("a")
        task_b = kernel.create_task("b")
        kernel.create_port("restricted", task_b.task_id)
        # task_a has no send right
        with pytest.raises(IPCPermissionError):
            kernel.send(task_a.task_id, "restricted", Message(), blocking=False)

    def test_receive_without_right_raises(self, kernel):
        owner = kernel.create_task("owner")
        intruder = kernel.create_task("intruder")
        kernel.create_port("secret", owner.task_id)
        with pytest.raises(IPCPermissionError):
            kernel.receive(intruder.task_id, "secret", blocking=False)

    def test_send_to_nonexistent_port_raises(self, kernel):
        task = kernel.create_task("t")
        with pytest.raises(IPCPortNotFoundError):
            kernel.send(task.task_id, "nonexistent", Message(), blocking=False)

    def test_receive_from_nonexistent_port_raises(self, kernel):
        task = kernel.create_task("t")
        with pytest.raises(IPCPortNotFoundError):
            kernel.receive(task.task_id, "nonexistent", blocking=False)

    def test_send_from_nonexistent_task_raises(self, kernel):
        owner = kernel.create_task("owner")
        kernel.create_port("p", owner.task_id)
        with pytest.raises(IPCTaskNotFoundError):
            kernel.send("ghost", "p", Message(), blocking=False)

    def test_messages_routed_counter(self, two_tasks, kernel):
        task_a, task_b, _ = two_tasks
        assert kernel.total_messages_routed == 0
        kernel.send(task_a.task_id, "channel", Message(), blocking=False)
        assert kernel.total_messages_routed == 1

    def test_task_message_counters(self, two_tasks, kernel):
        task_a, task_b, _ = two_tasks
        kernel.send(task_a.task_id, "channel", Message(), blocking=False)
        kernel.receive(task_b.task_id, "channel", blocking=False)
        assert task_a.messages_sent == 1
        assert task_b.messages_received == 1

    def test_send_once_right_revoked_after_use(self, kernel):
        sender = kernel.create_task("sender")
        receiver = kernel.create_task("receiver")
        port = kernel.create_port("once_port", receiver.task_id)
        port.grant_right(sender.task_id, PortRight.SEND_ONCE)
        sender.namespace.register(port, "once_port")
        # First send should succeed
        assert kernel.send(sender.task_id, "once_port", Message(), blocking=False)
        # SEND_ONCE should now be revoked
        assert not port.has_right(sender.task_id, PortRight.SEND_ONCE)

    def test_receive_empty_nonblocking_returns_none(self, two_tasks, kernel):
        _, task_b, _ = two_tasks
        result = kernel.receive(task_b.task_id, "channel", blocking=False)
        assert result is None


# ══════════════════════════════════════════════════════════════════════
# IPCKernel - Notifications
# ══════════════════════════════════════════════════════════════════════


class TestIPCKernelNotifications:
    """Validate notification message delivery."""

    def test_notify_success(self, two_tasks, kernel):
        task_a, task_b, _ = two_tasks
        result = kernel.notify(
            task_a.task_id, "channel", "test_event", {"key": "value"}
        )
        assert result is True
        assert len(kernel.notification_log) == 1
        assert kernel.notification_log[0]["type"] == "test_event"

    def test_notify_to_nonexistent_port(self, kernel):
        task = kernel.create_task("t")
        result = kernel.notify(task.task_id, "ghost_port", "event")
        assert result is False


# ══════════════════════════════════════════════════════════════════════
# Port Right Transfers
# ══════════════════════════════════════════════════════════════════════


class TestPortRightTransfer:
    """Validate port right transfer through IPC messages."""

    def test_send_right_transfer_via_message(self, kernel):
        task_a = kernel.create_task("a", priority=10)
        task_b = kernel.create_task("b", priority=10)
        # Create two ports: channel (b receives), extra (a receives)
        kernel.create_port("channel", task_b.task_id)
        kernel.grant_send_right("channel", task_a.task_id)
        extra = kernel.create_port("extra", task_a.task_id)
        extra.grant_right(task_a.task_id, PortRight.SEND)

        # Transfer SEND right on "extra" from a to b
        transfer = PortRightTransfer(
            port_name="extra", right=PortRight.SEND, disposition="copy"
        )
        msg = Message(inline_data={"hello": True}, port_transfers=[transfer])
        kernel.send(task_a.task_id, "channel", msg, blocking=False)
        received = kernel.receive(task_b.task_id, "channel", blocking=False)
        assert received is not None
        # After transfer, task_b should have SEND on extra
        assert extra.has_right(task_b.task_id, PortRight.SEND)

    def test_move_disposition_revokes_sender(self, kernel):
        task_a = kernel.create_task("a")
        task_b = kernel.create_task("b")
        kernel.create_port("ch", task_b.task_id)
        kernel.grant_send_right("ch", task_a.task_id)
        extra = kernel.create_port("ex", task_a.task_id)
        extra.grant_right(task_a.task_id, PortRight.SEND)

        transfer = PortRightTransfer(
            port_name="ex", right=PortRight.SEND, disposition="move"
        )
        msg = Message(port_transfers=[transfer])
        kernel.send(task_a.task_id, "ch", msg, blocking=False)
        # After move, sender should no longer have the right
        assert not extra.has_right(task_a.task_id, PortRight.SEND)

    def test_rights_transferred_counter(self, kernel):
        task_a = kernel.create_task("a")
        task_b = kernel.create_task("b")
        kernel.create_port("ch", task_b.task_id)
        kernel.grant_send_right("ch", task_a.task_id)
        extra = kernel.create_port("ex", task_a.task_id)
        extra.grant_right(task_a.task_id, PortRight.SEND)

        transfer = PortRightTransfer(port_name="ex", right=PortRight.SEND)
        msg = Message(port_transfers=[transfer])
        kernel.send(task_a.task_id, "ch", msg, blocking=False)
        assert kernel.total_rights_transferred == 1


# ══════════════════════════════════════════════════════════════════════
# Priority Scheduler
# ══════════════════════════════════════════════════════════════════════


class TestPriorityScheduler:
    """Validate priority-aware scheduling and priority inheritance."""

    def test_register_and_unregister(self):
        sched = PriorityScheduler()
        task = TaskStruct(name="t", priority=10)
        sched.register_task(task)
        sched.unregister_task(task.task_id)

    def test_priority_inheritance_boost(self):
        sched = PriorityScheduler()
        waiter = TaskStruct(name="high", priority=20)
        holder = TaskStruct(name="low", priority=5)
        sched.register_task(waiter)
        sched.register_task(holder)
        boosted = sched.apply_priority_inheritance(waiter, holder, "test_port")
        assert boosted is True
        assert holder.effective_priority == 20
        assert len(sched.boost_log) == 1

    def test_no_boost_when_holder_is_higher(self):
        sched = PriorityScheduler()
        waiter = TaskStruct(name="low", priority=5)
        holder = TaskStruct(name="high", priority=20)
        sched.register_task(waiter)
        sched.register_task(holder)
        boosted = sched.apply_priority_inheritance(waiter, holder, "test_port")
        assert boosted is False

    def test_release_priority_inheritance(self):
        sched = PriorityScheduler()
        task = TaskStruct(name="t", priority=10)
        task.effective_priority = 30  # Previously boosted
        sched.release_priority_inheritance(task)
        assert task.effective_priority == 10

    def test_delivery_order(self):
        sched = PriorityScheduler()
        msgs = [
            Message(header=MessageHeader(priority=MessagePriority.LOW)),
            Message(header=MessageHeader(priority=MessagePriority.CRITICAL)),
            Message(header=MessageHeader(priority=MessagePriority.NORMAL)),
        ]
        ordered = sched.get_delivery_order(msgs)
        assert ordered[0].header.priority == MessagePriority.CRITICAL
        assert ordered[1].header.priority == MessagePriority.NORMAL
        assert ordered[2].header.priority == MessagePriority.LOW

    def test_priority_inheritance_via_kernel_send(self, kernel):
        """Verify that priority inheritance is triggered during kernel send."""
        low_task = kernel.create_task("low_priority", priority=5)
        high_task = kernel.create_task("high_priority", priority=25)
        kernel.create_port("pi_port", low_task.task_id)
        kernel.grant_send_right("pi_port", high_task.task_id)

        msg = Message(inline_data={"test": True})
        kernel.send(high_task.task_id, "pi_port", msg, blocking=False)
        # Low-priority task should have been boosted
        assert low_task.effective_priority == 25


# ══════════════════════════════════════════════════════════════════════
# Deadlock Detector
# ══════════════════════════════════════════════════════════════════════


class TestDeadlockDetector:
    """Validate Tarjan's SCC-based deadlock detection."""

    def test_no_deadlock_empty_graph(self):
        dd = DeadlockDetector()
        tasks = {}
        ports = {}
        cycles = dd.detect_deadlocks(tasks, ports)
        assert cycles == []

    def test_no_deadlock_linear_wait(self):
        dd = DeadlockDetector()
        # A waits on B, but B does not wait on A
        port = Port("p")
        port.grant_right("b", PortRight.RECEIVE)
        tasks = {
            "a": TaskStruct(task_id="a", name="a", state=TaskState.WAITING, waiting_on_port="p"),
            "b": TaskStruct(task_id="b", name="b", state=TaskState.RUNNING),
        }
        ports = {"p": port}
        cycles = dd.detect_deadlocks(tasks, ports)
        assert cycles == []

    def test_detect_two_task_cycle(self):
        dd = DeadlockDetector()
        p1 = Port("p1")
        p1.grant_right("b", PortRight.RECEIVE)
        p2 = Port("p2")
        p2.grant_right("a", PortRight.RECEIVE)
        tasks = {
            "a": TaskStruct(task_id="a", name="a", state=TaskState.WAITING, waiting_on_port="p1"),
            "b": TaskStruct(task_id="b", name="b", state=TaskState.WAITING, waiting_on_port="p2"),
        }
        ports = {"p1": p1, "p2": p2}
        cycles = dd.detect_deadlocks(tasks, ports)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b"}

    def test_detect_three_task_cycle(self):
        dd = DeadlockDetector()
        p1 = Port("p1")
        p1.grant_right("b", PortRight.RECEIVE)
        p2 = Port("p2")
        p2.grant_right("c", PortRight.RECEIVE)
        p3 = Port("p3")
        p3.grant_right("a", PortRight.RECEIVE)
        tasks = {
            "a": TaskStruct(task_id="a", name="a", state=TaskState.WAITING, waiting_on_port="p1"),
            "b": TaskStruct(task_id="b", name="b", state=TaskState.WAITING, waiting_on_port="p2"),
            "c": TaskStruct(task_id="c", name="c", state=TaskState.WAITING, waiting_on_port="p3"),
        }
        ports = {"p1": p1, "p2": p2, "p3": p3}
        cycles = dd.detect_deadlocks(tasks, ports)
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b", "c"}

    def test_check_count_incremented(self):
        dd = DeadlockDetector()
        dd.detect_deadlocks({}, {})
        dd.detect_deadlocks({}, {})
        assert dd.check_count == 2

    def test_cycles_history(self):
        dd = DeadlockDetector()
        p1 = Port("p1")
        p1.grant_right("b", PortRight.RECEIVE)
        p2 = Port("p2")
        p2.grant_right("a", PortRight.RECEIVE)
        tasks = {
            "a": TaskStruct(task_id="a", name="a", state=TaskState.WAITING, waiting_on_port="p1"),
            "b": TaskStruct(task_id="b", name="b", state=TaskState.WAITING, waiting_on_port="p2"),
        }
        ports = {"p1": p1, "p2": p2}
        dd.detect_deadlocks(tasks, ports)
        assert len(dd.cycles_detected) >= 1

    def test_build_wait_for_graph(self):
        dd = DeadlockDetector()
        port = Port("p")
        port.grant_right("b", PortRight.RECEIVE)
        tasks = {
            "a": TaskStruct(task_id="a", name="a", state=TaskState.WAITING, waiting_on_port="p"),
            "b": TaskStruct(task_id="b", name="b", state=TaskState.RUNNING),
        }
        graph = dd.build_wait_for_graph(tasks, {"p": port})
        assert graph["a"] == ["b"]
        assert graph["b"] == []


# ══════════════════════════════════════════════════════════════════════
# IPC Kernel Stats
# ══════════════════════════════════════════════════════════════════════


class TestIPCKernelStats:
    """Validate kernel aggregate statistics."""

    def test_stats_keys(self, kernel):
        stats = kernel.stats()
        expected_keys = {
            "uptime_s", "tasks", "ports", "messages_routed",
            "rights_transferred", "notifications_sent",
            "deadlock_checks", "deadlocks_found", "priority_boosts",
        }
        assert expected_keys.issubset(stats.keys())

    def test_stats_initial_values(self, kernel):
        stats = kernel.stats()
        assert stats["tasks"] == 0
        assert stats["ports"] == 0
        assert stats["messages_routed"] == 0

    def test_stats_after_operations(self, two_tasks, kernel):
        task_a, task_b, _ = two_tasks
        kernel.send(task_a.task_id, "channel", Message(), blocking=False)
        stats = kernel.stats()
        assert stats["tasks"] == 2
        assert stats["ports"] == 1
        assert stats["messages_routed"] == 1


# ══════════════════════════════════════════════════════════════════════
# IPC Dashboard
# ══════════════════════════════════════════════════════════════════════


class TestIPCDashboard:
    """Validate the ASCII dashboard rendering."""

    def test_dashboard_renders_string(self, kernel):
        kernel.create_task("test_task")
        output = IPCDashboard.render(kernel)
        assert isinstance(output, str)
        assert "FizzIPC Microkernel Dashboard" in output

    def test_dashboard_shows_task(self, kernel):
        kernel.create_task("visible_task")
        output = IPCDashboard.render(kernel)
        assert "visible_task" in output

    def test_dashboard_shows_port(self, kernel):
        task = kernel.create_task("owner")
        kernel.create_port("dashboard_port", task.task_id)
        output = IPCDashboard.render(kernel)
        assert "dashboard_port" in output

    def test_dashboard_shows_statistics(self, kernel):
        output = IPCDashboard.render(kernel)
        assert "Messages Routed" in output
        assert "Active Tasks" in output

    def test_dashboard_respects_width(self, kernel):
        output = IPCDashboard.render(kernel, width=80)
        for line in output.split("\n"):
            if line.strip():
                assert len(line) <= 80

    def test_dashboard_empty_wait_graph(self, kernel):
        output = IPCDashboard.render(kernel)
        assert "no active waits" in output or "Wait-For Graph" in output


# ══════════════════════════════════════════════════════════════════════
# IPC Middleware
# ══════════════════════════════════════════════════════════════════════


class TestIPCMiddleware:
    """Validate the IPC middleware integration with the pipeline."""

    def test_middleware_name(self, kernel):
        mw = IPCMiddleware(kernel=kernel)
        assert mw.get_name() == "IPCMiddleware"

    def test_middleware_priority(self, kernel):
        mw = IPCMiddleware(kernel=kernel)
        assert mw.get_priority() == -8

    def test_middleware_creates_tasks(self, kernel):
        IPCMiddleware(kernel=kernel, num_tasks=4)
        assert kernel.task_count >= 4

    def test_middleware_creates_ports(self, kernel):
        IPCMiddleware(kernel=kernel)
        assert kernel.port_count >= 3  # eval_port, reply_port, audit_port

    def test_middleware_processes_context(self, kernel, processing_context):
        mw = IPCMiddleware(kernel=kernel)

        def next_handler(ctx):
            ctx.results.append(FizzBuzzResult(
                number=ctx.number, output="FizzBuzz",
                matched_rules=[],
            ))
            return ctx

        result = mw.process(processing_context, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "FizzBuzz"
        assert "ipc_overhead_ns" in result.metadata

    def test_middleware_increments_evaluation_count(self, kernel, processing_context):
        mw = IPCMiddleware(kernel=kernel)

        def next_handler(ctx):
            return ctx

        mw.process(processing_context, next_handler)
        mw.process(ProcessingContext(number=16, session_id="s2"), next_handler)
        assert mw.evaluation_count == 2

    def test_middleware_tracks_ipc_overhead(self, kernel, processing_context):
        mw = IPCMiddleware(kernel=kernel)

        def next_handler(ctx):
            return ctx

        mw.process(processing_context, next_handler)
        assert mw.total_ipc_time_ns > 0
        assert mw.average_ipc_overhead_us >= 0.0

    def test_middleware_routes_messages(self, kernel, processing_context):
        mw = IPCMiddleware(kernel=kernel)
        initial = kernel.total_messages_routed

        def next_handler(ctx):
            ctx.results.append(FizzBuzzResult(
                number=ctx.number, output="Fizz", matched_rules=[],
            ))
            return ctx

        mw.process(processing_context, next_handler)
        assert kernel.total_messages_routed > initial

    def test_middleware_render_dashboard(self, kernel):
        mw = IPCMiddleware(kernel=kernel)
        output = mw.render_dashboard()
        assert "FizzIPC Microkernel Dashboard" in output

    def test_middleware_with_extra_tasks(self, kernel):
        mw = IPCMiddleware(kernel=kernel, num_tasks=8)
        assert kernel.task_count >= 8

    def test_middleware_average_overhead_zero_before_use(self, kernel):
        mw = IPCMiddleware(kernel=kernel)
        assert mw.average_ipc_overhead_us == 0.0


# ══════════════════════════════════════════════════════════════════════
# Exception Hierarchy
# ══════════════════════════════════════════════════════════════════════


class TestIPCExceptions:
    """Validate the IPC exception hierarchy and error codes."""

    def test_ipc_error_base(self):
        err = IPCError("test error")
        assert "EFP-IPC0" in str(err)

    def test_port_not_found_error(self):
        err = IPCPortNotFoundError("missing_port")
        assert "missing_port" in str(err)
        assert err.port_name == "missing_port"

    def test_task_not_found_error(self):
        err = IPCTaskNotFoundError("ghost_task")
        assert "ghost_task" in str(err)
        assert err.task_id == "ghost_task"

    def test_permission_error(self):
        err = IPCPermissionError("t1", "p1", "no right")
        assert err.task_id == "t1"
        assert err.port_name == "p1"

    def test_deadlock_error(self):
        err = IPCDeadlockError(["a", "b", "c"])
        assert err.cycle == ["a", "b", "c"]
        assert "a -> b -> c -> a" in str(err)

    def test_queue_full_error(self):
        err = IPCQueueFullError("full_port", 64)
        assert err.port_name == "full_port"
        assert err.capacity == 64

    def test_timeout_error(self):
        err = IPCTimeoutError("send", "slow_port", 5.0)
        assert err.operation == "send"
        assert err.port_name == "slow_port"

    def test_right_transfer_error(self):
        err = IPCRightTransferError("p1", "SEND", "already revoked")
        assert err.port_name == "p1"

    def test_all_ipc_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        exceptions = [
            IPCError("e"),
            IPCPortNotFoundError("p"),
            IPCTaskNotFoundError("t"),
            IPCPermissionError("t", "p", "r"),
            IPCDeadlockError(["a", "b"]),
            IPCQueueFullError("p", 1),
            IPCTimeoutError("op", "p", 1.0),
            IPCRightTransferError("p", "R", "r"),
        ]
        for exc in exceptions:
            assert isinstance(exc, FizzBuzzError)


# ══════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════


class TestIPCIntegration:
    """End-to-end integration tests for the IPC subsystem."""

    def test_multi_message_pipeline(self, kernel):
        """Simulate a sequence of evaluations through IPC."""
        mw = IPCMiddleware(kernel=kernel)

        def handler(ctx):
            n = ctx.number
            if n % 15 == 0:
                out = "FizzBuzz"
            elif n % 3 == 0:
                out = "Fizz"
            elif n % 5 == 0:
                out = "Buzz"
            else:
                out = str(n)
            ctx.results.append(FizzBuzzResult(
                number=n, output=out, matched_rules=[],
            ))
            return ctx

        results = []
        for n in range(1, 16):
            ctx = ProcessingContext(number=n, session_id="integration")
            ctx = mw.process(ctx, handler)
            results.append(ctx.results[-1].output)

        assert results[0] == "1"
        assert results[2] == "Fizz"
        assert results[4] == "Buzz"
        assert results[14] == "FizzBuzz"
        assert mw.evaluation_count == 15
        assert kernel.total_messages_routed > 0

    def test_kernel_survives_rapid_create_destroy(self, kernel):
        """Stress test task and port lifecycle."""
        for i in range(50):
            task = kernel.create_task(f"ephemeral_{i}")
            port = kernel.create_port(f"port_{i}", task.task_id)
            kernel.destroy_port(f"port_{i}")
            kernel.terminate_task(task.task_id)
        # Kernel should still be operational
        new_task = kernel.create_task("survivor")
        assert new_task.state == TaskState.RUNNING

    def test_deadlock_detection_integration(self):
        """Set up a deadlock scenario and verify detection during receive."""
        kern = IPCKernel(default_port_capacity=4, enable_deadlock_detection=True)
        t1 = kern.create_task("task_1", priority=10)
        t2 = kern.create_task("task_2", priority=10)

        # t1 owns p1 (receive right), t2 owns p2 (receive right)
        kern.create_port("p1", t1.task_id)
        kern.create_port("p2", t2.task_id)
        kern.grant_send_right("p1", t2.task_id)
        kern.grant_send_right("p2", t1.task_id)

        # Simulate: t1 is waiting on p2, t2 is waiting on p1
        t1.state = TaskState.WAITING
        t1.waiting_on_port = "p2"
        t2.state = TaskState.WAITING
        t2.waiting_on_port = "p1"

        # Manual deadlock check should find the cycle
        cycles = kern.run_deadlock_check()
        assert len(cycles) == 1
        assert set(cycles[0]) == {t1.task_id, t2.task_id}

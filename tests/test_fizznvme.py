"""Tests for the FizzNVMe NVM Express Storage Protocol subsystem.

Validates all components of the FizzNVMe controller including namespace
management, command queue lifecycle, I/O command submission, LBA range
validation, queue depth enforcement, block read/write operations, flush
semantics, controller statistics, dashboard rendering, and middleware
integration.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizznvme import (
    FIZZNVME_VERSION,
    MIDDLEWARE_PRIORITY,
    DEFAULT_BLOCK_SIZE,
    DEFAULT_QUEUE_DEPTH,
    DEFAULT_DASHBOARD_WIDTH,
    MAX_NAMESPACES,
    MAX_QUEUES,
    NVMeCommand,
    NVMeNamespace,
    CommandQueue,
    IOCommand,
    NVMeController,
    FizzNVMeDashboard,
    FizzNVMeMiddleware,
    create_fizznvme_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzNVMeError,
    FizzNVMeNamespaceError,
    FizzNVMeNamespaceNotFoundError,
    FizzNVMeQueueError,
    FizzNVMeQueueNotFoundError,
    FizzNVMeQueueFullError,
    FizzNVMeInvalidLBAError,
    FizzNVMeDataSizeMismatchError,
    FizzNVMeDuplicateNamespaceError,
    FizzNVMeDuplicateQueueError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def controller():
    """Fresh NVMeController instance."""
    return NVMeController()


@pytest.fixture
def ns(controller):
    """Controller with one namespace created."""
    namespace = controller.create_namespace("fizz-data", size_blocks=1024)
    return controller, namespace


@pytest.fixture
def ns_and_queue(ns):
    """Controller with one namespace and one command queue."""
    controller, namespace = ns
    queue = controller.create_queue("io-queue-0")
    return controller, namespace, queue


# ============================================================
# Constants
# ============================================================


class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version(self):
        assert FIZZNVME_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 234

    def test_default_block_size(self):
        assert DEFAULT_BLOCK_SIZE == 4096

    def test_default_queue_depth(self):
        assert DEFAULT_QUEUE_DEPTH == 64

    def test_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72


# ============================================================
# NVMeCommand Enum
# ============================================================


class TestNVMeCommand:
    """Verify the NVMeCommand enum covers all required opcodes."""

    def test_read(self):
        assert NVMeCommand.READ.value == "read"

    def test_write(self):
        assert NVMeCommand.WRITE.value == "write"

    def test_flush(self):
        assert NVMeCommand.FLUSH.value == "flush"

    def test_identify(self):
        assert NVMeCommand.IDENTIFY.value == "identify"

    def test_create_queue(self):
        assert NVMeCommand.CREATE_QUEUE.value == "create_queue"

    def test_delete_queue(self):
        assert NVMeCommand.DELETE_QUEUE.value == "delete_queue"


# ============================================================
# Namespace Management
# ============================================================


class TestNamespaceManagement:
    """Verify namespace creation and retrieval."""

    def test_create_namespace(self, controller):
        ns = controller.create_namespace("test-ns", size_blocks=512)
        assert ns.name == "test-ns"
        assert ns.size_blocks == 512
        assert ns.block_size == DEFAULT_BLOCK_SIZE

    def test_create_namespace_custom_block_size(self, controller):
        ns = controller.create_namespace("test-ns", size_blocks=256, block_size=8192)
        assert ns.block_size == 8192
        assert ns.capacity_bytes == 256 * 8192

    def test_namespace_has_uuid(self, controller):
        ns = controller.create_namespace("test-ns", size_blocks=100)
        uuid.UUID(ns.ns_id)  # Should not raise

    def test_get_namespace(self, ns):
        controller, namespace = ns
        retrieved = controller.get_namespace(namespace.ns_id)
        assert retrieved.ns_id == namespace.ns_id

    def test_get_namespace_not_found(self, controller):
        with pytest.raises(FizzNVMeNamespaceNotFoundError):
            controller.get_namespace("nonexistent-id")

    def test_list_namespaces(self, controller):
        controller.create_namespace("ns-1", size_blocks=100)
        controller.create_namespace("ns-2", size_blocks=200)
        namespaces = controller.list_namespaces()
        assert len(namespaces) == 2
        assert namespaces[0].name == "ns-1"
        assert namespaces[1].name == "ns-2"

    def test_duplicate_namespace_name_raises(self, controller):
        controller.create_namespace("fizz-data", size_blocks=100)
        with pytest.raises(FizzNVMeDuplicateNamespaceError):
            controller.create_namespace("fizz-data", size_blocks=200)

    def test_namespace_capacity(self, controller):
        ns = controller.create_namespace("test", size_blocks=1000, block_size=4096)
        assert ns.capacity_bytes == 1000 * 4096


# ============================================================
# Queue Management
# ============================================================


class TestQueueManagement:
    """Verify command queue creation and listing."""

    def test_create_queue(self, controller):
        queue = controller.create_queue("submit-q")
        assert queue.name == "submit-q"
        assert queue.depth == DEFAULT_QUEUE_DEPTH
        assert queue.commands_processed == 0

    def test_create_queue_custom_depth(self, controller):
        queue = controller.create_queue("deep-q", depth=128)
        assert queue.depth == 128

    def test_queue_has_uuid(self, controller):
        queue = controller.create_queue("test-q")
        uuid.UUID(queue.queue_id)  # Should not raise

    def test_list_queues(self, controller):
        controller.create_queue("q-1")
        controller.create_queue("q-2")
        queues = controller.list_queues()
        assert len(queues) == 2

    def test_duplicate_queue_name_raises(self, controller):
        controller.create_queue("io-queue")
        with pytest.raises(FizzNVMeDuplicateQueueError):
            controller.create_queue("io-queue")


# ============================================================
# I/O Command Submission - Write
# ============================================================


class TestWriteCommands:
    """Verify write command submission and block storage."""

    def test_write_single_block(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        data = b"\xAB" * namespace.block_size
        cmd = controller.submit(
            queue.queue_id, NVMeCommand.WRITE, namespace.ns_id,
            lba=0, num_blocks=1, data=data,
        )
        assert cmd.opcode == NVMeCommand.WRITE
        assert cmd.num_blocks == 1

    def test_write_multiple_blocks(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        data = b"\xCD" * (namespace.block_size * 4)
        cmd = controller.submit(
            queue.queue_id, NVMeCommand.WRITE, namespace.ns_id,
            lba=10, num_blocks=4, data=data,
        )
        assert cmd.num_blocks == 4

    def test_write_data_size_mismatch_raises(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        with pytest.raises(FizzNVMeDataSizeMismatchError):
            controller.submit(
                queue.queue_id, NVMeCommand.WRITE, namespace.ns_id,
                lba=0, num_blocks=1, data=b"\x00" * 100,
            )

    def test_write_beyond_namespace_raises(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        data = b"\x00" * namespace.block_size
        with pytest.raises(FizzNVMeInvalidLBAError):
            controller.submit(
                queue.queue_id, NVMeCommand.WRITE, namespace.ns_id,
                lba=namespace.size_blocks, num_blocks=1, data=data,
            )


# ============================================================
# I/O Command Submission - Read
# ============================================================


class TestReadCommands:
    """Verify read command submission and data retrieval."""

    def test_read_written_data(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        write_data = b"\xEF" * namespace.block_size
        controller.submit(
            queue.queue_id, NVMeCommand.WRITE, namespace.ns_id,
            lba=5, num_blocks=1, data=write_data,
        )
        read_cmd = controller.submit(
            queue.queue_id, NVMeCommand.READ, namespace.ns_id,
            lba=5, num_blocks=1,
        )
        assert read_cmd.data == write_data

    def test_read_unwritten_returns_zeros(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        read_cmd = controller.submit(
            queue.queue_id, NVMeCommand.READ, namespace.ns_id,
            lba=0, num_blocks=1,
        )
        assert read_cmd.data == b"\x00" * namespace.block_size

    def test_read_beyond_namespace_raises(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        with pytest.raises(FizzNVMeInvalidLBAError):
            controller.submit(
                queue.queue_id, NVMeCommand.READ, namespace.ns_id,
                lba=namespace.size_blocks, num_blocks=1,
            )


# ============================================================
# Queue Validation
# ============================================================


class TestQueueValidation:
    """Verify queue-level validation on command submission."""

    def test_submit_to_nonexistent_queue_raises(self, ns):
        controller, namespace = ns
        with pytest.raises(FizzNVMeQueueNotFoundError):
            controller.submit(
                "nonexistent-queue", NVMeCommand.READ, namespace.ns_id,
                lba=0, num_blocks=1,
            )

    def test_submit_to_nonexistent_namespace_raises(self, controller):
        queue = controller.create_queue("test-q")
        with pytest.raises(FizzNVMeNamespaceNotFoundError):
            controller.submit(
                queue.queue_id, NVMeCommand.READ, "nonexistent-ns",
                lba=0, num_blocks=1,
            )


# ============================================================
# Flush and Identify
# ============================================================


class TestFlushAndIdentify:
    """Verify flush and identify commands."""

    def test_flush_command(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        cmd = controller.submit(
            queue.queue_id, NVMeCommand.FLUSH, namespace.ns_id,
            lba=0, num_blocks=0,
        )
        assert cmd.opcode == NVMeCommand.FLUSH

    def test_identify_command(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        cmd = controller.submit(
            queue.queue_id, NVMeCommand.IDENTIFY, namespace.ns_id,
            lba=0, num_blocks=0,
        )
        assert cmd.opcode == NVMeCommand.IDENTIFY


# ============================================================
# Statistics
# ============================================================


class TestStats:
    """Verify controller statistics tracking."""

    def test_stats_initial(self, controller):
        stats = controller.get_stats()
        assert stats["reads"] == 0
        assert stats["writes"] == 0
        assert stats["total_commands"] == 0

    def test_stats_after_write_and_read(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        data = b"\x01" * namespace.block_size
        controller.submit(
            queue.queue_id, NVMeCommand.WRITE, namespace.ns_id,
            lba=0, num_blocks=1, data=data,
        )
        controller.submit(
            queue.queue_id, NVMeCommand.READ, namespace.ns_id,
            lba=0, num_blocks=1,
        )
        stats = controller.get_stats()
        assert stats["writes"] == 1
        assert stats["reads"] == 1
        assert stats["bytes_written"] == namespace.block_size
        assert stats["bytes_read"] == namespace.block_size
        assert stats["total_commands"] == 2

    def test_queue_commands_processed(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        controller.submit(
            queue.queue_id, NVMeCommand.FLUSH, namespace.ns_id,
            lba=0, num_blocks=0,
        )
        updated_queues = controller.list_queues()
        assert updated_queues[0].commands_processed == 1


# ============================================================
# Dashboard
# ============================================================


class TestFizzNVMeDashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_overview(self, ns_and_queue):
        controller, namespace, queue = ns_and_queue
        dashboard = FizzNVMeDashboard(width=72)
        output = dashboard.render_overview(controller)
        assert "FizzNVMe NVM Express Storage Controller" in output
        assert FIZZNVME_VERSION in output
        assert "Namespaces" in output
        assert "Command Queues" in output

    def test_render_namespace(self, ns):
        controller, namespace = ns
        dashboard = FizzNVMeDashboard(width=72)
        output = dashboard.render_namespace(namespace)
        assert namespace.ns_id in output
        assert namespace.name in output

    def test_render_queue(self, controller):
        queue = controller.create_queue("render-test-q")
        dashboard = FizzNVMeDashboard(width=72)
        output = dashboard.render_queue(queue)
        assert queue.queue_id in output
        assert "render-test-q" in output


# ============================================================
# Middleware
# ============================================================


class TestFizzNVMeMiddleware:
    """Verify middleware integration with the FizzBuzz pipeline."""

    def test_get_name(self):
        controller, middleware = create_fizznvme_subsystem()
        assert middleware.get_name() == "fizznvme"

    def test_get_priority(self):
        controller, middleware = create_fizznvme_subsystem()
        assert middleware.get_priority() == 234

    def test_process_annotates_context(self):
        controller, middleware = create_fizznvme_subsystem()
        context = ProcessingContext(number=42, session_id="test-session")
        called = False

        def next_handler(ctx):
            nonlocal called
            called = True
            return ctx

        result = middleware.process(context, next_handler)
        assert called
        assert result.metadata["fizznvme_enabled"] is True
        assert result.metadata["fizznvme_version"] == FIZZNVME_VERSION


# ============================================================
# Factory
# ============================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_returns_tuple(self):
        controller, middleware = create_fizznvme_subsystem()
        assert isinstance(controller, NVMeController)
        assert isinstance(middleware, FizzNVMeMiddleware)

    def test_custom_dashboard_width(self):
        controller, middleware = create_fizznvme_subsystem(dashboard_width=100)
        assert middleware._dashboard._width == 100

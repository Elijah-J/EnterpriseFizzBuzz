"""
Enterprise FizzBuzz Platform - FizzNVMe: NVM Express Storage Protocol

A complete NVM Express (NVMe) storage controller implementation providing
high-performance block I/O for the Enterprise FizzBuzz Platform.  FizzNVMe
implements the core NVMe command set including read, write, flush, identify,
and queue management operations over a namespace-based storage model with
configurable block sizes and queue depths.

The FizzBuzz evaluation pipeline generates persistent artifacts that demand
low-latency, high-throughput block storage access: FizzWAL write-ahead log
segments, FizzVCS packfiles, FizzSQL database pages, FizzLSM sorted-string
tables, and FizzS3 erasure-coded object fragments.  These workloads share
common characteristics -- sequential writes with random reads, power-of-two
block alignment, and queue-depth-sensitive throughput scaling -- that map
directly to the NVMe command model.

The controller manages multiple namespaces (logical storage volumes), each
with an independent LBA (Logical Block Address) space and configurable block
size.  I/O commands are submitted through named command queues with bounded
depth, providing admission control and fair scheduling across concurrent
subsystem workloads.  The in-memory block store uses a dictionary-keyed
address scheme that provides O(1) read and write latency per block,
simulating the flat-latency profile of real NVMe solid-state storage.

Architecture references: NVM Express Base Specification 2.0
(https://nvmexpress.org/specifications/),
Linux NVMe Driver (https://github.com/linux-nvme/nvme-cli),
SPDK (https://spdk.io/)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    FizzNVMeError,
    FizzNVMeNamespaceError,
    FizzNVMeNamespaceNotFoundError,
    FizzNVMeQueueError,
    FizzNVMeQueueNotFoundError,
    FizzNVMeQueueFullError,
    FizzNVMeCommandError,
    FizzNVMeInvalidLBAError,
    FizzNVMeDataSizeMismatchError,
    FizzNVMeControllerError,
    FizzNVMeReadUnwrittenError,
    FizzNVMeDuplicateNamespaceError,
    FizzNVMeDuplicateQueueError,
    FizzNVMeMiddlewareError,
    FizzNVMeDashboardError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizznvme")


# ============================================================
# Constants
# ============================================================

FIZZNVME_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 234
DEFAULT_BLOCK_SIZE = 4096
DEFAULT_QUEUE_DEPTH = 64
DEFAULT_DASHBOARD_WIDTH = 72
MAX_NAMESPACES = 128
MAX_QUEUES = 64


# ============================================================
# Enums
# ============================================================


class NVMeCommand(Enum):
    """NVMe I/O and admin command opcodes.

    READ and WRITE are the primary data transfer commands.  FLUSH forces
    all pending writes to stable storage.  IDENTIFY returns controller
    and namespace metadata.  CREATE_QUEUE and DELETE_QUEUE manage
    submission and completion queue lifecycle.
    """

    READ = "read"
    WRITE = "write"
    FLUSH = "flush"
    IDENTIFY = "identify"
    CREATE_QUEUE = "create_queue"
    DELETE_QUEUE = "delete_queue"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class NVMeNamespace:
    """A logical storage volume within the NVMe controller.

    Each namespace provides an independent LBA address space with
    configurable block size.  The namespace is identified by a unique
    ns_id and a human-readable name.
    """

    ns_id: str
    name: str
    size_blocks: int
    block_size: int = DEFAULT_BLOCK_SIZE

    @property
    def capacity_bytes(self) -> int:
        """Return total capacity in bytes."""
        return self.size_blocks * self.block_size


@dataclass
class CommandQueue:
    """An NVMe submission/completion queue pair.

    Each queue has a bounded depth controlling the maximum number of
    outstanding commands.  The commands_processed counter tracks
    lifetime throughput for monitoring and capacity planning.
    """

    queue_id: str
    name: str
    depth: int = DEFAULT_QUEUE_DEPTH
    commands_processed: int = 0
    _pending: int = field(default=0, repr=False)


@dataclass
class IOCommand:
    """A single I/O command submitted to the NVMe controller.

    Encapsulates the command opcode, target namespace, LBA range,
    block count, and optional data payload for write operations.
    """

    cmd_id: str
    opcode: NVMeCommand
    ns_id: str
    lba: int
    num_blocks: int
    data: bytes = b""


# ============================================================
# NVMeController - Core Storage Engine
# ============================================================


class NVMeController:
    """NVM Express controller managing namespaces, queues, and I/O commands.

    Provides namespace lifecycle management, command queue creation and
    deletion, and I/O command submission with LBA range validation and
    queue depth enforcement.  The in-memory block store uses a
    (ns_id, lba) -> bytes mapping for O(1) per-block access.
    """

    def __init__(self) -> None:
        self._namespaces: OrderedDict[str, NVMeNamespace] = OrderedDict()
        self._queues: OrderedDict[str, CommandQueue] = OrderedDict()
        self._blocks: Dict[Tuple[str, int], bytes] = {}
        self._commands: List[IOCommand] = []
        self._stats = {
            "namespaces_created": 0,
            "queues_created": 0,
            "reads": 0,
            "writes": 0,
            "flushes": 0,
            "identifies": 0,
            "bytes_read": 0,
            "bytes_written": 0,
            "total_commands": 0,
        }
        logger.info("FizzNVMe controller initialized (v%s)", FIZZNVME_VERSION)

    def create_namespace(
        self,
        name: str,
        size_blocks: int,
        block_size: int = DEFAULT_BLOCK_SIZE,
    ) -> NVMeNamespace:
        """Create a new storage namespace.

        Args:
            name: Human-readable namespace name.
            size_blocks: Number of logical blocks in the namespace.
            block_size: Size of each block in bytes (default: 4096).

        Returns:
            The newly created NVMeNamespace.

        Raises:
            FizzNVMeNamespaceError: If max namespace limit is reached.
            FizzNVMeDuplicateNamespaceError: If name already exists.
        """
        if len(self._namespaces) >= MAX_NAMESPACES:
            raise FizzNVMeNamespaceError(
                f"Maximum namespace limit reached ({MAX_NAMESPACES})"
            )

        # Check for duplicate names
        for ns in self._namespaces.values():
            if ns.name == name:
                raise FizzNVMeDuplicateNamespaceError(name)

        ns_id = str(uuid.uuid4())
        namespace = NVMeNamespace(
            ns_id=ns_id,
            name=name,
            size_blocks=size_blocks,
            block_size=block_size,
        )
        self._namespaces[ns_id] = namespace
        self._stats["namespaces_created"] += 1
        logger.debug(
            "Created namespace %s (%s): %d blocks x %d bytes",
            ns_id, name, size_blocks, block_size,
        )
        return namespace

    def create_queue(
        self,
        name: str,
        depth: int = DEFAULT_QUEUE_DEPTH,
    ) -> CommandQueue:
        """Create a new command queue.

        Args:
            name: Human-readable queue name.
            depth: Maximum outstanding commands (default: 64).

        Returns:
            The newly created CommandQueue.

        Raises:
            FizzNVMeQueueError: If max queue limit is reached.
            FizzNVMeDuplicateQueueError: If name already exists.
        """
        if len(self._queues) >= MAX_QUEUES:
            raise FizzNVMeQueueError(
                f"Maximum queue limit reached ({MAX_QUEUES})"
            )

        for q in self._queues.values():
            if q.name == name:
                raise FizzNVMeDuplicateQueueError(name)

        queue_id = str(uuid.uuid4())
        queue = CommandQueue(
            queue_id=queue_id,
            name=name,
            depth=depth,
        )
        self._queues[queue_id] = queue
        self._stats["queues_created"] += 1
        logger.debug("Created queue %s (%s): depth=%d", queue_id, name, depth)
        return queue

    def submit(
        self,
        queue_id: str,
        opcode: NVMeCommand,
        ns_id: str,
        lba: int,
        num_blocks: int,
        data: bytes = b"",
    ) -> IOCommand:
        """Submit an I/O command to a queue for execution.

        The command is validated against the target namespace's LBA range
        and the queue's depth limit, then executed immediately (synchronous
        command completion model).

        Args:
            queue_id: The queue to submit to.
            opcode: The command opcode.
            ns_id: The target namespace.
            lba: Starting logical block address.
            num_blocks: Number of blocks to transfer.
            data: Write payload (required for WRITE commands).

        Returns:
            The completed IOCommand.

        Raises:
            FizzNVMeQueueNotFoundError: If the queue does not exist.
            FizzNVMeNamespaceNotFoundError: If the namespace does not exist.
            FizzNVMeInvalidLBAError: If the LBA range exceeds namespace capacity.
            FizzNVMeQueueFullError: If the queue depth is exceeded.
            FizzNVMeDataSizeMismatchError: If write data size is incorrect.
        """
        # Validate queue
        if queue_id not in self._queues:
            raise FizzNVMeQueueNotFoundError(queue_id)
        queue = self._queues[queue_id]

        if queue._pending >= queue.depth:
            raise FizzNVMeQueueFullError(queue_id, queue.depth)

        # Validate namespace
        if ns_id not in self._namespaces:
            raise FizzNVMeNamespaceNotFoundError(ns_id)
        namespace = self._namespaces[ns_id]

        # Validate LBA range for read/write
        if opcode in (NVMeCommand.READ, NVMeCommand.WRITE):
            if lba + num_blocks > namespace.size_blocks:
                raise FizzNVMeInvalidLBAError(
                    ns_id, lba, num_blocks, namespace.size_blocks,
                )

        # Create command
        cmd_id = str(uuid.uuid4())
        cmd = IOCommand(
            cmd_id=cmd_id,
            opcode=opcode,
            ns_id=ns_id,
            lba=lba,
            num_blocks=num_blocks,
            data=data,
        )

        # Execute command
        queue._pending += 1
        try:
            self._execute(cmd, namespace)
        finally:
            queue._pending -= 1
            queue.commands_processed += 1

        self._commands.append(cmd)
        self._stats["total_commands"] += 1
        return cmd

    def _execute(self, cmd: IOCommand, namespace: NVMeNamespace) -> None:
        """Execute a single I/O command against the block store."""
        if cmd.opcode == NVMeCommand.WRITE:
            expected_bytes = cmd.num_blocks * namespace.block_size
            if len(cmd.data) != expected_bytes:
                raise FizzNVMeDataSizeMismatchError(expected_bytes, len(cmd.data))
            # Write blocks
            for i in range(cmd.num_blocks):
                offset = i * namespace.block_size
                block_data = cmd.data[offset:offset + namespace.block_size]
                self._blocks[(cmd.ns_id, cmd.lba + i)] = block_data
            self._stats["writes"] += 1
            self._stats["bytes_written"] += len(cmd.data)

        elif cmd.opcode == NVMeCommand.READ:
            # Read blocks
            read_data = bytearray()
            for i in range(cmd.num_blocks):
                key = (cmd.ns_id, cmd.lba + i)
                if key not in self._blocks:
                    # Return zero-filled blocks for unwritten LBAs (NVMe spec behavior)
                    read_data.extend(b"\x00" * namespace.block_size)
                else:
                    read_data.extend(self._blocks[key])
            cmd.data = bytes(read_data)
            self._stats["reads"] += 1
            self._stats["bytes_read"] += len(cmd.data)

        elif cmd.opcode == NVMeCommand.FLUSH:
            # Flush is a no-op for in-memory storage but tracked for metrics
            self._stats["flushes"] += 1

        elif cmd.opcode == NVMeCommand.IDENTIFY:
            self._stats["identifies"] += 1

    def get_namespace(self, ns_id: str) -> NVMeNamespace:
        """Retrieve a namespace by its identifier.

        Raises:
            FizzNVMeNamespaceNotFoundError: If the namespace does not exist.
        """
        if ns_id not in self._namespaces:
            raise FizzNVMeNamespaceNotFoundError(ns_id)
        return self._namespaces[ns_id]

    def list_namespaces(self) -> List[NVMeNamespace]:
        """Return all namespaces in creation order."""
        return list(self._namespaces.values())

    def list_queues(self) -> List[CommandQueue]:
        """Return all command queues in creation order."""
        return list(self._queues.values())

    def get_stats(self) -> dict:
        """Return controller statistics."""
        return dict(self._stats)


# ============================================================
# Dashboard
# ============================================================


class FizzNVMeDashboard:
    """ASCII dashboard renderer for the FizzNVMe storage controller."""

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._width = width

    def render_overview(self, controller: NVMeController) -> str:
        """Render a summary of the NVMe controller state."""
        lines = []
        lines.append("=" * self._width)
        lines.append("FizzNVMe NVM Express Storage Controller".center(self._width))
        lines.append(f"Version {FIZZNVME_VERSION}".center(self._width))
        lines.append("=" * self._width)

        namespaces = controller.list_namespaces()
        queues = controller.list_queues()
        stats = controller.get_stats()

        lines.append(f"  Namespaces       : {len(namespaces)}")
        lines.append(f"  Command Queues   : {len(queues)}")
        lines.append(f"  Total Commands   : {stats['total_commands']}")
        lines.append(f"  Reads            : {stats['reads']}")
        lines.append(f"  Writes           : {stats['writes']}")
        lines.append(f"  Flushes          : {stats['flushes']}")
        lines.append(f"  Bytes Read       : {stats['bytes_read']}")
        lines.append(f"  Bytes Written    : {stats['bytes_written']}")
        lines.append("=" * self._width)
        return "\n".join(lines)

    def render_namespace(self, namespace: NVMeNamespace) -> str:
        """Render details of a single namespace."""
        lines = []
        lines.append("-" * self._width)
        lines.append(f"  Namespace ID     : {namespace.ns_id}")
        lines.append(f"  Name             : {namespace.name}")
        lines.append(f"  Size (blocks)    : {namespace.size_blocks}")
        lines.append(f"  Block Size       : {namespace.block_size}")
        lines.append(f"  Capacity (bytes) : {namespace.capacity_bytes}")
        lines.append("-" * self._width)
        return "\n".join(lines)

    def render_queue(self, queue: CommandQueue) -> str:
        """Render details of a single command queue."""
        lines = []
        lines.append("-" * self._width)
        lines.append(f"  Queue ID         : {queue.queue_id}")
        lines.append(f"  Name             : {queue.name}")
        lines.append(f"  Depth            : {queue.depth}")
        lines.append(f"  Commands Done    : {queue.commands_processed}")
        lines.append("-" * self._width)
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzNVMeMiddleware(IMiddleware):
    """Middleware integrating FizzNVMe block storage with the FizzBuzz pipeline.

    Priority: 234 (positioned after FizzArrow at 233).
    On each evaluation pass, the middleware annotates the processing context
    with NVMe controller metadata including namespace count, queue count,
    total commands processed, and engine version.
    """

    def __init__(
        self,
        controller: NVMeController,
        dashboard: FizzNVMeDashboard,
    ) -> None:
        self._controller = controller
        self._dashboard = dashboard

    def get_name(self) -> str:
        """Return 'fizznvme'."""
        return "fizznvme"

    def get_priority(self) -> int:
        """Return MIDDLEWARE_PRIORITY (234)."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        return "fizznvme"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process evaluation, annotating with FizzNVMe controller status."""
        context.metadata["fizznvme_enabled"] = True
        context.metadata["fizznvme_namespace_count"] = len(self._controller.list_namespaces())
        context.metadata["fizznvme_queue_count"] = len(self._controller.list_queues())
        context.metadata["fizznvme_version"] = FIZZNVME_VERSION
        return next_handler(context)

    def render_overview(self) -> str:
        """Render the FizzNVMe dashboard overview."""
        return self._dashboard.render_overview(self._controller)

    def render_namespace(self, ns_id: str) -> str:
        """Render details for a specific namespace."""
        ns = self._controller.get_namespace(ns_id)
        return self._dashboard.render_namespace(ns)

    def render_queue(self, queue_id: str) -> str:
        """Render details for a specific queue."""
        queues = self._controller.list_queues()
        for q in queues:
            if q.queue_id == queue_id:
                return self._dashboard.render_queue(q)
        raise FizzNVMeQueueNotFoundError(queue_id)


# ============================================================
# Factory
# ============================================================


def create_fizznvme_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    event_bus: Optional[Any] = None,
) -> Tuple[NVMeController, FizzNVMeMiddleware]:
    """Create and wire the complete FizzNVMe subsystem.

    Factory function that instantiates the NVMe controller, dashboard
    renderer, and middleware, ready for integration into the FizzBuzz
    evaluation pipeline.

    Returns:
        Tuple of (NVMeController, FizzNVMeMiddleware).
    """
    controller = NVMeController()
    dashboard = FizzNVMeDashboard(width=dashboard_width)
    middleware = FizzNVMeMiddleware(controller=controller, dashboard=dashboard)
    logger.info("FizzNVMe subsystem initialized")
    return controller, middleware

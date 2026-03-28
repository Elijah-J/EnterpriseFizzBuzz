"""
Enterprise FizzBuzz Platform - FizzXDP: Express Data Path for Kernel-Bypass Packet Processing

An XDP (Express Data Path) subsystem that processes FizzBuzz evaluation
packets at the earliest possible point in the network receive path, before
the kernel allocates socket buffers.  FizzXDP attaches eBPF-style programs
to virtual network interfaces, enabling per-packet classification and
action decisions with zero-copy forwarding.

The XDP processing model executes a single attached program per interface.
Each program inspects packet metadata (source, destination, protocol, size)
and returns one of five actions: PASS (deliver to the kernel stack), DROP
(discard silently), TX (transmit back on the same interface), REDIRECT
(forward to a different interface), or ABORTED (signal an error).

The FizzBuzz evaluation pipeline generates a continuous stream of
classification requests that, in a distributed deployment, arrive as
network packets.  Processing these packets in the kernel incurs per-packet
allocation, SKB construction, and protocol demultiplexing overhead that is
entirely unnecessary for the platform's fixed-format evaluation protocol.
FizzXDP eliminates this overhead by making action decisions before the
kernel touches the packet.

Architecture references: Linux XDP (https://www.kernel.org/doc/html/latest/networking/af_xdp.html),
Memory, Networks, and FizzBuzz: The Trifecta (internal whitepaper)
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzxdp import (
    FizzXDPError,
    XDPAttachError,
    XDPDetachError,
    XDPPacketProcessingError,
    XDPProgramNotFoundError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzxdp")

EVENT_XDP = EventType.register("FIZZXDP_PACKET_PROCESSED")

# ============================================================
# Constants
# ============================================================

FIZZXDP_VERSION = "1.0.0"
"""Current version of the FizzXDP subsystem."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 235
"""Middleware pipeline priority for FizzXDP."""


# ============================================================
# Enums
# ============================================================


class XDPAction(Enum):
    """XDP program return actions.

    Each action determines the fate of a processed packet at the
    earliest point in the receive path, before any kernel allocation.
    """
    PASS = "pass"
    DROP = "drop"
    TX = "tx"
    REDIRECT = "redirect"
    ABORTED = "aborted"


# ============================================================
# Data classes
# ============================================================


@dataclass
class XDPProgram:
    """An XDP program attached to a virtual network interface.

    Each program is bound to exactly one interface and applies a
    default action to all packets unless overridden by per-packet
    classification logic.
    """
    prog_id: str = ""
    name: str = ""
    interface: str = ""
    action: XDPAction = XDPAction.PASS
    packets_processed: int = 0


@dataclass
class PacketInfo:
    """Metadata for a single processed packet.

    Records the packet's source, destination, protocol, size, and
    the action taken by the XDP program after classification.
    """
    pkt_id: str = ""
    src: str = ""
    dst: str = ""
    protocol: str = ""
    size: int = 0
    action_taken: XDPAction = XDPAction.PASS


# ============================================================
# XDP Engine
# ============================================================


class XDPEngine:
    """Manages XDP programs and processes packets through the express data path.

    The engine maintains a registry of attached programs, each bound to a
    virtual network interface.  Packets are processed by looking up the
    program by ID and applying its classification logic.
    """

    def __init__(self) -> None:
        self._programs: OrderedDict[str, XDPProgram] = OrderedDict()
        self._packets: List[PacketInfo] = []

    def attach(self, name: str, interface: str,
               default_action: XDPAction = XDPAction.PASS) -> XDPProgram:
        """Attach a new XDP program to a virtual network interface.

        Args:
            name: Human-readable program name.
            interface: Virtual network interface to attach to.
            default_action: Action to apply to packets by default.

        Returns:
            The newly created XDPProgram with a unique ID.
        """
        prog_id = f"xdp-{uuid.uuid4().hex[:8]}"
        program = XDPProgram(
            prog_id=prog_id,
            name=name,
            interface=interface,
            action=default_action,
            packets_processed=0,
        )
        self._programs[prog_id] = program
        logger.debug("Attached XDP program '%s' to interface '%s' (action=%s)",
                      name, interface, default_action.value)
        return program

    def detach(self, prog_id: str) -> XDPProgram:
        """Detach an XDP program from its interface.

        Args:
            prog_id: The unique program identifier.

        Returns:
            The detached XDPProgram.

        Raises:
            XDPProgramNotFoundError: If the program ID is not found.
        """
        program = self.get_program(prog_id)
        del self._programs[prog_id]
        logger.debug("Detached XDP program '%s' from interface '%s'",
                      program.name, program.interface)
        return program

    def process_packet(self, prog_id: str, src: str, dst: str,
                       protocol: str, size: int) -> PacketInfo:
        """Process a packet through the specified XDP program.

        The program's default action is applied to the packet, and the
        program's packet counter is incremented.

        Args:
            prog_id: The XDP program to process through.
            src: Source address.
            dst: Destination address.
            protocol: Protocol identifier (e.g. "TCP", "UDP", "FIZZ").
            size: Packet size in bytes.

        Returns:
            PacketInfo describing the processed packet and action taken.

        Raises:
            XDPProgramNotFoundError: If the program ID is not found.
        """
        program = self.get_program(prog_id)
        pkt_id = f"pkt-{uuid.uuid4().hex[:8]}"
        packet = PacketInfo(
            pkt_id=pkt_id,
            src=src,
            dst=dst,
            protocol=protocol,
            size=size,
            action_taken=program.action,
        )
        program.packets_processed += 1
        self._packets.append(packet)
        logger.debug("Processed packet %s through program '%s': action=%s",
                      pkt_id, program.name, program.action.value)
        return packet

    def get_program(self, prog_id: str) -> XDPProgram:
        """Retrieve a program by its unique identifier.

        Raises:
            XDPProgramNotFoundError: If the program ID is not found.
        """
        program = self._programs.get(prog_id)
        if program is None:
            raise XDPProgramNotFoundError(prog_id)
        return program

    def list_programs(self) -> List[XDPProgram]:
        """Return all attached XDP programs."""
        return list(self._programs.values())

    def get_stats(self) -> dict:
        """Aggregate statistics across all programs and packets."""
        total_packets = sum(p.packets_processed for p in self._programs.values())
        action_counts: Dict[str, int] = {}
        for pkt in self._packets:
            key = pkt.action_taken.value
            action_counts[key] = action_counts.get(key, 0) + 1
        return {
            "total_programs": len(self._programs),
            "total_packets_processed": total_packets,
            "action_counts": action_counts,
        }


# ============================================================
# Dashboard
# ============================================================


class FizzXDPDashboard:
    """ASCII dashboard for monitoring the XDP subsystem."""

    def __init__(self, engine: Optional[XDPEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        """Render the XDP monitoring dashboard."""
        lines = [
            "=" * self._width,
            "FizzXDP Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZXDP_VERSION}",
        ]
        if self._engine:
            stats = self._engine.get_stats()
            lines.append(f"  Programs: {stats['total_programs']}")
            lines.append(f"  Packets processed: {stats['total_packets_processed']}")
            if stats["action_counts"]:
                lines.append("-" * self._width)
                lines.append("  Action Distribution:")
                for action, count in stats["action_counts"].items():
                    lines.append(f"    {action:<12} {count}")
            lines.append("-" * self._width)
            for prog in self._engine.list_programs()[:10]:
                lines.append(
                    f"  {prog.name:<20} [{prog.interface}] "
                    f"action={prog.action.value} pkts={prog.packets_processed}"
                )
        lines.append("=" * self._width)
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzXDPMiddleware(IMiddleware):
    """Middleware integration for the FizzXDP subsystem."""

    def __init__(self, engine: Optional[XDPEngine] = None,
                 dashboard: Optional[FizzXDPDashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str:
        return "fizzxdp"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzXDP not initialized"


# ============================================================
# Factory
# ============================================================


def create_fizzxdp_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[XDPEngine, FizzXDPDashboard, FizzXDPMiddleware]:
    """Factory function that creates and wires the FizzXDP subsystem.

    Returns:
        A tuple of (XDPEngine, FizzXDPDashboard, FizzXDPMiddleware).
    """
    engine = XDPEngine()
    # Attach default XDP programs for the standard FizzBuzz interfaces
    engine.attach("fizz_classifier", "fizz0", XDPAction.PASS)
    engine.attach("buzz_filter", "buzz0", XDPAction.PASS)
    engine.attach("fizzbuzz_redirect", "fb0", XDPAction.REDIRECT)

    dashboard = FizzXDPDashboard(engine, dashboard_width)
    middleware = FizzXDPMiddleware(engine, dashboard)
    logger.info("FizzXDP initialized: %d programs attached", len(engine.list_programs()))
    return engine, dashboard, middleware

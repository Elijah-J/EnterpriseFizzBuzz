"""
Enterprise FizzBuzz Platform - FizzNet TCP/IP Protocol Stack Module

Implements a complete, standards-compliant TCP/IP protocol stack for
reliable delivery of FizzBuzz classification results between application
components. The stack includes:

- Layer 2 (Data Link): Ethernet II frames with CRC32 integrity checks
- Layer 2.5 (Resolution): ARP table with configurable aging for IP-to-MAC
  mapping, because even in-memory function calls deserve proper addressing
- Layer 3 (Network): IPv4 packets with header checksum verification,
  TTL decrement, and ICMP echo request/reply (ping) support
- Layer 4 (Transport): TCP segments with full three-way handshake,
  Reno congestion control (slow start, congestion avoidance, fast
  retransmit on triple duplicate ACK), send/receive buffering
- Layer 5-7 (Application): FizzBuzz Protocol (FBZP) for structured
  request/response classification queries over reliable TCP streams
- Network management: ASCII dashboard, packet counters, interface
  simulation with TX/RX queues

All communication is simulated entirely in-memory via Python lists.
No actual sockets are opened. No bytes traverse any physical medium.
The entire OSI model collapses into a series of method calls within
a single Python process, achieving sub-microsecond latency that would
make any real network engineer weep with envy — or confusion.

The architectural justification is straightforward: FizzBuzz results
are mission-critical data, and mission-critical data demands reliable,
ordered, flow-controlled delivery. TCP provides exactly these guarantees.
That the sender and receiver happen to share an address space is an
implementation detail.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
import zlib
from dataclasses import dataclass, field
from enum import Enum, IntFlag, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FizzNetError,
    FizzNetChecksumError,
    FizzNetConnectionRefusedError,
    FizzNetConnectionResetError,
    FizzNetTimeoutError,
    FizzNetARPResolutionError,
    FizzNetTTLExpiredError,
    FizzNetProtocolError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ETHERNET_MTU = 1500
IPV4_HEADER_MIN_SIZE = 20
TCP_HEADER_MIN_SIZE = 20
MAX_TCP_PAYLOAD = ETHERNET_MTU - IPV4_HEADER_MIN_SIZE - TCP_HEADER_MIN_SIZE
ARP_AGING_SECONDS = 300.0
DEFAULT_TTL = 64
TCP_MAX_WINDOW = 65535
TCP_INITIAL_SSTHRESH = 65535
TCP_MSS = 1460
ICMP_ECHO_REQUEST = 8
ICMP_ECHO_REPLY = 0


# ---------------------------------------------------------------------------
# Ethernet Layer (Layer 2)
# ---------------------------------------------------------------------------

@dataclass
class EthernetFrame:
    """IEEE 802.3 Ethernet II frame.

    Each frame carries a destination MAC, source MAC, EtherType field,
    payload, and a CRC32 frame check sequence computed over the entire
    header and payload. Frames exceeding the MTU are silently dropped,
    as is the custom in enterprise networking.
    """

    dst_mac: str
    src_mac: str
    ethertype: int  # 0x0800 = IPv4, 0x0806 = ARP
    payload: bytes
    crc: int = 0

    def compute_crc(self) -> int:
        """Compute CRC32 over header fields and payload."""
        header = (
            bytes.fromhex(self.dst_mac.replace(":", ""))
            + bytes.fromhex(self.src_mac.replace(":", ""))
            + struct.pack("!H", self.ethertype)
            + self.payload
        )
        return zlib.crc32(header) & 0xFFFFFFFF

    def validate(self) -> bool:
        """Verify frame CRC matches the payload."""
        return self.crc == self.compute_crc()

    def finalize(self) -> EthernetFrame:
        """Compute and set the CRC, returning self for chaining."""
        self.crc = self.compute_crc()
        return self

    def __len__(self) -> int:
        return 14 + len(self.payload) + 4  # header + payload + FCS


# ---------------------------------------------------------------------------
# ARP Table (Layer 2.5)
# ---------------------------------------------------------------------------

@dataclass
class ARPEntry:
    """A single entry in the ARP cache."""

    ip_address: str
    mac_address: str
    timestamp: float = field(default_factory=time.monotonic)


class ARPTable:
    """Address Resolution Protocol table for IP-to-MAC mapping.

    Maintains a cache of IP-to-MAC bindings with configurable aging.
    Entries older than the aging threshold are considered stale and
    will be refreshed on next lookup. In a real network, this would
    involve broadcasting an ARP request. Here, we simply consult the
    network interface registry, which is considerably more efficient
    and considerably less interesting.
    """

    def __init__(self, aging_seconds: float = ARP_AGING_SECONDS) -> None:
        self._entries: dict[str, ARPEntry] = {}
        self._aging_seconds = aging_seconds
        self._stats = {"lookups": 0, "hits": 0, "misses": 0, "expirations": 0}

    def add(self, ip_address: str, mac_address: str) -> None:
        """Add or update an ARP entry."""
        self._entries[ip_address] = ARPEntry(
            ip_address=ip_address,
            mac_address=mac_address,
        )

    def resolve(self, ip_address: str) -> Optional[str]:
        """Resolve an IP address to a MAC address.

        Returns None if the entry is not found or has expired.
        """
        self._stats["lookups"] += 1
        entry = self._entries.get(ip_address)
        if entry is None:
            self._stats["misses"] += 1
            return None
        age = time.monotonic() - entry.timestamp
        if age > self._aging_seconds:
            self._stats["expirations"] += 1
            del self._entries[ip_address]
            return None
        self._stats["hits"] += 1
        return entry.mac_address

    def remove(self, ip_address: str) -> bool:
        """Remove an ARP entry. Returns True if it existed."""
        if ip_address in self._entries:
            del self._entries[ip_address]
            return True
        return False

    def flush(self) -> int:
        """Remove all entries. Returns the count of removed entries."""
        count = len(self._entries)
        self._entries.clear()
        return count

    @property
    def entries(self) -> dict[str, ARPEntry]:
        return dict(self._entries)

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# IPv4 Packet (Layer 3)
# ---------------------------------------------------------------------------

@dataclass
class IPv4Packet:
    """Internet Protocol version 4 packet.

    Implements the IPv4 header with version, IHL, TTL, protocol number,
    source/destination addresses, and the standard one's complement
    checksum algorithm. The header checksum is computed over the 20-byte
    minimum header using the one's complement of the one's complement
    sum, as specified in RFC 791.
    """

    version: int = 4
    ihl: int = 5  # 5 x 32-bit words = 20 bytes
    dscp: int = 0
    ecn: int = 0
    total_length: int = 0
    identification: int = 0
    flags: int = 0
    fragment_offset: int = 0
    ttl: int = DEFAULT_TTL
    protocol: int = 6  # 6 = TCP, 1 = ICMP, 17 = UDP
    header_checksum: int = 0
    src_ip: str = "0.0.0.0"
    dst_ip: str = "0.0.0.0"
    payload: bytes = b""

    def __post_init__(self) -> None:
        if self.total_length == 0:
            self.total_length = self.ihl * 4 + len(self.payload)

    @staticmethod
    def _ip_to_int(ip: str) -> int:
        """Convert dotted-quad IP string to 32-bit integer."""
        parts = ip.split(".")
        return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])

    def _build_header_bytes(self, checksum: int = 0) -> bytes:
        """Build the 20-byte IPv4 header for checksum computation."""
        ver_ihl = (self.version << 4) | self.ihl
        dscp_ecn = (self.dscp << 2) | self.ecn
        flags_frag = (self.flags << 13) | self.fragment_offset
        src = self._ip_to_int(self.src_ip)
        dst = self._ip_to_int(self.dst_ip)
        return struct.pack(
            "!BBHHHBBHII",
            ver_ihl,
            dscp_ecn,
            self.total_length,
            self.identification,
            flags_frag,
            self.ttl,
            self.protocol,
            checksum,
            src,
            dst,
        )

    @staticmethod
    def _ones_complement_sum(data: bytes) -> int:
        """Compute the one's complement sum over 16-bit words.

        This is the standard Internet checksum algorithm: sum all
        16-bit words using one's complement arithmetic, fold any
        carry bits back into the sum, then return the one's
        complement of the result.
        """
        if len(data) % 2 != 0:
            data = data + b"\x00"
        total = 0
        for i in range(0, len(data), 2):
            word = (data[i] << 8) | data[i + 1]
            total += word
        # Fold 32-bit sum to 16 bits
        while total > 0xFFFF:
            total = (total & 0xFFFF) + (total >> 16)
        return total

    def compute_checksum(self) -> int:
        """Compute the IPv4 header checksum.

        The checksum field is set to zero for computation, then the
        one's complement of the one's complement sum of all 16-bit
        words in the header is taken.
        """
        header_bytes = self._build_header_bytes(checksum=0)
        return ~self._ones_complement_sum(header_bytes) & 0xFFFF

    def finalize(self) -> IPv4Packet:
        """Compute total_length and header checksum, returning self."""
        self.total_length = self.ihl * 4 + len(self.payload)
        self.header_checksum = self.compute_checksum()
        return self

    def validate_checksum(self) -> bool:
        """Verify the header checksum is valid.

        A valid checksum will produce a one's complement sum of 0xFFFF
        when the checksum field is included in the computation.
        """
        header_bytes = self._build_header_bytes(checksum=self.header_checksum)
        return self._ones_complement_sum(header_bytes) == 0xFFFF

    def decrement_ttl(self) -> int:
        """Decrement TTL and recompute checksum. Returns new TTL."""
        self.ttl -= 1
        self.header_checksum = self.compute_checksum()
        return self.ttl

    def to_bytes(self) -> bytes:
        """Serialize the packet to bytes (header + payload)."""
        return self._build_header_bytes(checksum=self.header_checksum) + self.payload


# ---------------------------------------------------------------------------
# ICMP Message (Layer 3)
# ---------------------------------------------------------------------------

@dataclass
class ICMPMessage:
    """Internet Control Message Protocol message.

    Supports echo request (type 8) and echo reply (type 0) for
    diagnostic ping operations within the FizzNet stack. Because
    even a simulated in-memory network needs a way to verify that
    the simulated in-memory endpoints are reachable.
    """

    type: int = ICMP_ECHO_REQUEST
    code: int = 0
    checksum: int = 0
    identifier: int = 0
    sequence_number: int = 0
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        """Serialize the ICMP message to bytes."""
        header = struct.pack(
            "!BBHHH",
            self.type,
            self.code,
            0,  # checksum placeholder
            self.identifier,
            self.sequence_number,
        )
        data = header + self.payload
        # Compute checksum over the entire ICMP message
        checksum = ~IPv4Packet._ones_complement_sum(data) & 0xFFFF
        self.checksum = checksum
        return struct.pack(
            "!BBHHH",
            self.type,
            self.code,
            self.checksum,
            self.identifier,
            self.sequence_number,
        ) + self.payload

    @classmethod
    def from_bytes(cls, data: bytes) -> ICMPMessage:
        """Deserialize an ICMP message from bytes."""
        if len(data) < 8:
            raise FizzNetProtocolError("ICMP message too short", protocol="ICMP")
        type_, code, checksum, identifier, seq = struct.unpack("!BBHHH", data[:8])
        return cls(
            type=type_,
            code=code,
            checksum=checksum,
            identifier=identifier,
            sequence_number=seq,
            payload=data[8:],
        )

    def make_reply(self) -> ICMPMessage:
        """Create an echo reply from this echo request."""
        return ICMPMessage(
            type=ICMP_ECHO_REPLY,
            code=0,
            identifier=self.identifier,
            sequence_number=self.sequence_number,
            payload=self.payload,
        )


# ---------------------------------------------------------------------------
# TCP Segment (Layer 4)
# ---------------------------------------------------------------------------

class TCPFlags(IntFlag):
    """TCP control flags as per RFC 793."""

    FIN = 0x01
    SYN = 0x02
    RST = 0x04
    PSH = 0x08
    ACK = 0x10
    URG = 0x20


@dataclass
class TCPSegment:
    """Transmission Control Protocol segment.

    Implements the TCP header with source/destination ports, sequence
    and acknowledgment numbers, data offset, flags, window size, and
    checksum. The checksum covers a pseudo-header (source IP, dest IP,
    protocol, TCP length) plus the TCP header and payload, as specified
    in RFC 793.
    """

    src_port: int = 0
    dst_port: int = 0
    seq_number: int = 0
    ack_number: int = 0
    data_offset: int = 5  # 5 x 32-bit words = 20 bytes
    flags: TCPFlags = TCPFlags(0)
    window: int = TCP_MAX_WINDOW
    checksum: int = 0
    urgent_pointer: int = 0
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        """Serialize the TCP segment to bytes (header + payload)."""
        offset_flags = (self.data_offset << 12) | int(self.flags)
        header = struct.pack(
            "!HHIIHHH",
            self.src_port,
            self.dst_port,
            self.seq_number & 0xFFFFFFFF,
            self.ack_number & 0xFFFFFFFF,
            offset_flags,
            self.window,
            0,  # checksum placeholder
        )
        # Urgent pointer is the last 2 bytes
        header += struct.pack("!H", self.urgent_pointer)
        return header + self.payload

    def compute_checksum(self, src_ip: str, dst_ip: str) -> int:
        """Compute TCP checksum including pseudo-header."""
        pseudo_header = struct.pack(
            "!IIBBh",
            IPv4Packet._ip_to_int(src_ip),
            IPv4Packet._ip_to_int(dst_ip),
            0,  # reserved
            6,  # TCP protocol number
            self.data_offset * 4 + len(self.payload),
        )
        segment_bytes = self.to_bytes()
        data = pseudo_header + segment_bytes
        return ~IPv4Packet._ones_complement_sum(data) & 0xFFFF

    def finalize(self, src_ip: str, dst_ip: str) -> TCPSegment:
        """Compute checksum and return self."""
        self.checksum = self.compute_checksum(src_ip, dst_ip)
        return self

    @property
    def is_syn(self) -> bool:
        return bool(self.flags & TCPFlags.SYN) and not bool(self.flags & TCPFlags.ACK)

    @property
    def is_syn_ack(self) -> bool:
        return bool(self.flags & TCPFlags.SYN) and bool(self.flags & TCPFlags.ACK)

    @property
    def is_ack(self) -> bool:
        return bool(self.flags & TCPFlags.ACK) and not bool(self.flags & (TCPFlags.SYN | TCPFlags.FIN))

    @property
    def is_fin(self) -> bool:
        return bool(self.flags & TCPFlags.FIN)

    @property
    def is_rst(self) -> bool:
        return bool(self.flags & TCPFlags.RST)

    @property
    def is_psh(self) -> bool:
        return bool(self.flags & TCPFlags.PSH)

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    def __repr__(self) -> str:
        flag_names = []
        for f in TCPFlags:
            if self.flags & f:
                flag_names.append(f.name)
        flags_str = "|".join(flag_names) or "NONE"
        return (
            f"TCPSegment(src={self.src_port}, dst={self.dst_port}, "
            f"seq={self.seq_number}, ack={self.ack_number}, "
            f"flags={flags_str}, win={self.window}, "
            f"payload={len(self.payload)}B)"
        )


# ---------------------------------------------------------------------------
# TCP State Machine
# ---------------------------------------------------------------------------

class TCPState(Enum):
    """TCP connection states as defined in RFC 793.

    The TCP state machine governs the lifecycle of every connection
    in the FizzNet stack. Transitions are triggered by segment
    arrivals and application-level operations (connect, accept, close).
    """

    CLOSED = "CLOSED"
    LISTEN = "LISTEN"
    SYN_SENT = "SYN_SENT"
    SYN_RECEIVED = "SYN_RECEIVED"
    ESTABLISHED = "ESTABLISHED"
    FIN_WAIT_1 = "FIN_WAIT_1"
    FIN_WAIT_2 = "FIN_WAIT_2"
    CLOSE_WAIT = "CLOSE_WAIT"
    LAST_ACK = "LAST_ACK"
    TIME_WAIT = "TIME_WAIT"
    CLOSING = "CLOSING"


# ---------------------------------------------------------------------------
# TCP Connection (with Reno Congestion Control)
# ---------------------------------------------------------------------------

class TCPConnection:
    """A single TCP connection with full state machine and Reno congestion control.

    Implements the complete TCP connection lifecycle: three-way handshake
    for connection establishment, reliable data transfer with sequence
    numbering, and four-way termination. Congestion control follows
    the TCP Reno algorithm:

    - Slow Start: cwnd doubles each RTT until ssthresh is reached
    - Congestion Avoidance: cwnd increases by ~1 MSS per RTT
    - Fast Retransmit: on receiving 3 duplicate ACKs, retransmit the
      lost segment immediately, set ssthresh = cwnd/2, cwnd = ssthresh + 3
    - Fast Recovery: inflate cwnd for each additional dup ACK, deflate
      on new ACK

    All of this machinery operates over Python lists instead of network
    buffers. The congestion window governs how many FizzBuzz classifications
    can be in flight at once, which is critical for preventing the
    evaluation pipeline from overwhelming itself — a real risk when the
    sender and receiver share the same CPU and the RTT is effectively zero.
    """

    _next_isn = 1000  # Class-level ISN counter for deterministic testing

    def __init__(
        self,
        local_ip: str,
        local_port: int,
        remote_ip: str,
        remote_port: int,
    ) -> None:
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.state = TCPState.CLOSED

        # Sequence numbers
        self.snd_una = 0  # Oldest unacknowledged sequence number
        self.snd_nxt = 0  # Next sequence number to send
        self.snd_iss = 0  # Initial send sequence number
        self.rcv_nxt = 0  # Next expected receive sequence number
        self.rcv_irs = 0  # Initial receive sequence number

        # Buffers
        self.send_buffer: list[bytes] = []
        self.recv_buffer: list[bytes] = []
        self._outgoing_segments: list[TCPSegment] = []
        self._retransmit_queue: list[tuple[int, bytes]] = []

        # Reno congestion control
        self.cwnd: float = TCP_MSS  # Congestion window (bytes)
        self.ssthresh: float = TCP_INITIAL_SSTHRESH  # Slow start threshold
        self.dup_ack_count: int = 0  # Duplicate ACK counter
        self._in_fast_recovery: bool = False

        # Statistics
        self.stats = {
            "segments_sent": 0,
            "segments_received": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "retransmissions": 0,
            "dup_acks_received": 0,
            "fast_retransmits": 0,
            "timeouts": 0,
            "cwnd_history": [],
        }

    @classmethod
    def _generate_isn(cls) -> int:
        """Generate an initial sequence number.

        In production TCP, ISNs are randomized to prevent sequence
        prediction attacks. Here, we use a deterministic counter
        for testability, because FizzBuzz classification data does
        not typically face sequence prediction threats.
        """
        isn = cls._next_isn
        cls._next_isn += 1000
        return isn

    @classmethod
    def reset_isn_counter(cls) -> None:
        """Reset the ISN counter. Used for testing."""
        cls._next_isn = 1000

    def _record_cwnd(self) -> None:
        """Record current cwnd for congestion window history."""
        self.stats["cwnd_history"].append(self.cwnd)

    # ------------------------------------------------------------------
    # Three-way handshake (active open)
    # ------------------------------------------------------------------

    def initiate_handshake(self) -> TCPSegment:
        """Send SYN to begin the three-way handshake (client side).

        Transitions: CLOSED -> SYN_SENT
        """
        if self.state != TCPState.CLOSED:
            raise FizzNetProtocolError(
                f"Cannot initiate handshake from state {self.state.value}",
                protocol="TCP",
            )
        self.snd_iss = self._generate_isn()
        self.snd_nxt = self.snd_iss + 1
        self.snd_una = self.snd_iss

        syn = TCPSegment(
            src_port=self.local_port,
            dst_port=self.remote_port,
            seq_number=self.snd_iss,
            ack_number=0,
            flags=TCPFlags.SYN,
            window=TCP_MAX_WINDOW,
        )
        self.state = TCPState.SYN_SENT
        self.stats["segments_sent"] += 1
        self._record_cwnd()
        logger.debug(
            "TCP %s:%d -> %s:%d [SYN] seq=%d (SYN_SENT)",
            self.local_ip, self.local_port,
            self.remote_ip, self.remote_port,
            self.snd_iss,
        )
        return syn

    def receive_syn(self, segment: TCPSegment) -> TCPSegment:
        """Receive SYN and respond with SYN-ACK (server side).

        Transitions: LISTEN -> SYN_RECEIVED
        """
        if self.state != TCPState.LISTEN:
            raise FizzNetProtocolError(
                f"Cannot receive SYN in state {self.state.value}",
                protocol="TCP",
            )
        self.rcv_irs = segment.seq_number
        self.rcv_nxt = segment.seq_number + 1
        self.snd_iss = self._generate_isn()
        self.snd_nxt = self.snd_iss + 1
        self.snd_una = self.snd_iss

        syn_ack = TCPSegment(
            src_port=self.local_port,
            dst_port=self.remote_port,
            seq_number=self.snd_iss,
            ack_number=self.rcv_nxt,
            flags=TCPFlags.SYN | TCPFlags.ACK,
            window=TCP_MAX_WINDOW,
        )
        self.state = TCPState.SYN_RECEIVED
        self.stats["segments_sent"] += 1
        self.stats["segments_received"] += 1
        logger.debug(
            "TCP %s:%d -> %s:%d [SYN-ACK] seq=%d ack=%d (SYN_RECEIVED)",
            self.local_ip, self.local_port,
            self.remote_ip, self.remote_port,
            self.snd_iss, self.rcv_nxt,
        )
        return syn_ack

    def receive_syn_ack(self, segment: TCPSegment) -> TCPSegment:
        """Receive SYN-ACK and respond with ACK (client side).

        Transitions: SYN_SENT -> ESTABLISHED
        """
        if self.state != TCPState.SYN_SENT:
            raise FizzNetProtocolError(
                f"Cannot receive SYN-ACK in state {self.state.value}",
                protocol="TCP",
            )
        self.rcv_irs = segment.seq_number
        self.rcv_nxt = segment.seq_number + 1
        self.snd_una = segment.ack_number

        ack = TCPSegment(
            src_port=self.local_port,
            dst_port=self.remote_port,
            seq_number=self.snd_nxt,
            ack_number=self.rcv_nxt,
            flags=TCPFlags.ACK,
            window=TCP_MAX_WINDOW,
        )
        self.state = TCPState.ESTABLISHED
        self.stats["segments_sent"] += 1
        self.stats["segments_received"] += 1
        self._record_cwnd()
        logger.debug(
            "TCP %s:%d -> %s:%d [ACK] seq=%d ack=%d (ESTABLISHED)",
            self.local_ip, self.local_port,
            self.remote_ip, self.remote_port,
            self.snd_nxt, self.rcv_nxt,
        )
        return ack

    def complete_handshake(self, segment: TCPSegment) -> None:
        """Receive final ACK to complete the handshake (server side).

        Transitions: SYN_RECEIVED -> ESTABLISHED
        """
        if self.state != TCPState.SYN_RECEIVED:
            raise FizzNetProtocolError(
                f"Cannot complete handshake in state {self.state.value}",
                protocol="TCP",
            )
        self.snd_una = segment.ack_number
        self.rcv_nxt = segment.seq_number  # ACK doesn't consume seq space
        self.state = TCPState.ESTABLISHED
        self.stats["segments_received"] += 1
        self._record_cwnd()
        logger.debug(
            "TCP %s:%d (ESTABLISHED) — handshake complete",
            self.local_ip, self.local_port,
        )

    # ------------------------------------------------------------------
    # Data transfer
    # ------------------------------------------------------------------

    def send(self, data: bytes) -> list[TCPSegment]:
        """Send data over the connection.

        Segments the data according to MSS and the current congestion
        window, queuing segments for transmission.
        """
        if self.state != TCPState.ESTABLISHED:
            raise FizzNetProtocolError(
                f"Cannot send data in state {self.state.value}",
                protocol="TCP",
            )
        self.send_buffer.append(data)
        segments: list[TCPSegment] = []

        # Determine how many bytes we can send based on cwnd
        bytes_in_flight = self.snd_nxt - self.snd_una
        available_window = max(0, int(self.cwnd) - bytes_in_flight)

        offset = 0
        remaining = len(data)

        while remaining > 0 and available_window > 0:
            chunk_size = min(remaining, TCP_MSS, available_window)
            chunk = data[offset:offset + chunk_size]

            segment = TCPSegment(
                src_port=self.local_port,
                dst_port=self.remote_port,
                seq_number=self.snd_nxt,
                ack_number=self.rcv_nxt,
                flags=TCPFlags.ACK | TCPFlags.PSH,
                window=TCP_MAX_WINDOW,
                payload=chunk,
            )
            segments.append(segment)
            self._retransmit_queue.append((self.snd_nxt, chunk))
            self.snd_nxt += len(chunk)
            self.stats["segments_sent"] += 1
            self.stats["bytes_sent"] += len(chunk)

            offset += chunk_size
            remaining -= chunk_size
            available_window -= chunk_size

        self._record_cwnd()
        return segments

    def receive_data(self, segment: TCPSegment) -> Optional[TCPSegment]:
        """Process a received data segment and generate an ACK.

        Buffers the received data and advances the receive window.
        Returns an ACK segment, or None if the segment was out of order.
        """
        if self.state not in (TCPState.ESTABLISHED, TCPState.FIN_WAIT_1, TCPState.FIN_WAIT_2):
            return None

        self.stats["segments_received"] += 1

        if segment.seq_number == self.rcv_nxt:
            # In-order delivery
            if segment.payload:
                self.recv_buffer.append(segment.payload)
                self.rcv_nxt += len(segment.payload)
                self.stats["bytes_received"] += len(segment.payload)

            ack = TCPSegment(
                src_port=self.local_port,
                dst_port=self.remote_port,
                seq_number=self.snd_nxt,
                ack_number=self.rcv_nxt,
                flags=TCPFlags.ACK,
                window=TCP_MAX_WINDOW,
            )
            self.stats["segments_sent"] += 1
            return ack
        else:
            # Out of order: send duplicate ACK
            dup_ack = TCPSegment(
                src_port=self.local_port,
                dst_port=self.remote_port,
                seq_number=self.snd_nxt,
                ack_number=self.rcv_nxt,
                flags=TCPFlags.ACK,
                window=TCP_MAX_WINDOW,
            )
            self.stats["segments_sent"] += 1
            return dup_ack

    def process_ack(self, segment: TCPSegment) -> None:
        """Process an incoming ACK and update congestion control.

        Implements TCP Reno:
        - New ACK in slow start: cwnd += MSS (doubles per RTT)
        - New ACK in congestion avoidance: cwnd += MSS * MSS / cwnd
        - Duplicate ACK: increment dup_ack_count
        - 3 duplicate ACKs: fast retransmit + fast recovery
        """
        self.stats["segments_received"] += 1
        ack_num = segment.ack_number

        if ack_num > self.snd_una:
            # New ACK — advances the window
            self.snd_una = ack_num
            self.dup_ack_count = 0

            # Remove acknowledged data from retransmit queue
            self._retransmit_queue = [
                (seq, data) for seq, data in self._retransmit_queue
                if seq + len(data) > ack_num
            ]

            if self._in_fast_recovery:
                # Exit fast recovery
                self.cwnd = self.ssthresh
                self._in_fast_recovery = False
            elif self.cwnd < self.ssthresh:
                # Slow start: exponential growth
                self.cwnd += TCP_MSS
            else:
                # Congestion avoidance: linear growth
                self.cwnd += (TCP_MSS * TCP_MSS) / self.cwnd

            self._record_cwnd()

        elif ack_num == self.snd_una:
            # Duplicate ACK
            self.dup_ack_count += 1
            self.stats["dup_acks_received"] += 1

            if self.dup_ack_count == 3 and not self._in_fast_recovery:
                # Fast retransmit triggered
                self.stats["fast_retransmits"] += 1
                self.ssthresh = max(self.cwnd / 2, 2 * TCP_MSS)
                self.cwnd = self.ssthresh + 3 * TCP_MSS
                self._in_fast_recovery = True
                self._record_cwnd()
                logger.debug(
                    "TCP %s:%d fast retransmit triggered — ssthresh=%.0f cwnd=%.0f",
                    self.local_ip, self.local_port,
                    self.ssthresh, self.cwnd,
                )
            elif self._in_fast_recovery:
                # Inflate cwnd for each additional dup ACK
                self.cwnd += TCP_MSS
                self._record_cwnd()

    def get_retransmit_segment(self) -> Optional[TCPSegment]:
        """Get the oldest unacknowledged segment for retransmission."""
        if not self._retransmit_queue:
            return None
        seq, data = self._retransmit_queue[0]
        self.stats["retransmissions"] += 1
        return TCPSegment(
            src_port=self.local_port,
            dst_port=self.remote_port,
            seq_number=seq,
            ack_number=self.rcv_nxt,
            flags=TCPFlags.ACK | TCPFlags.PSH,
            window=TCP_MAX_WINDOW,
            payload=data,
        )

    # ------------------------------------------------------------------
    # Connection teardown (four-way close)
    # ------------------------------------------------------------------

    def initiate_close(self) -> TCPSegment:
        """Send FIN to begin connection teardown.

        Transitions: ESTABLISHED -> FIN_WAIT_1
        """
        if self.state not in (TCPState.ESTABLISHED, TCPState.CLOSE_WAIT):
            raise FizzNetProtocolError(
                f"Cannot initiate close from state {self.state.value}",
                protocol="TCP",
            )
        fin = TCPSegment(
            src_port=self.local_port,
            dst_port=self.remote_port,
            seq_number=self.snd_nxt,
            ack_number=self.rcv_nxt,
            flags=TCPFlags.FIN | TCPFlags.ACK,
            window=TCP_MAX_WINDOW,
        )
        self.snd_nxt += 1  # FIN consumes one sequence number

        if self.state == TCPState.ESTABLISHED:
            self.state = TCPState.FIN_WAIT_1
        else:  # CLOSE_WAIT
            self.state = TCPState.LAST_ACK

        self.stats["segments_sent"] += 1
        logger.debug(
            "TCP %s:%d -> %s:%d [FIN|ACK] (-> %s)",
            self.local_ip, self.local_port,
            self.remote_ip, self.remote_port,
            self.state.value,
        )
        return fin

    def receive_fin(self, segment: TCPSegment) -> TCPSegment:
        """Receive FIN and send ACK.

        Transitions depend on current state:
        - ESTABLISHED -> CLOSE_WAIT
        - FIN_WAIT_1 -> CLOSING (simultaneous close)
        - FIN_WAIT_2 -> TIME_WAIT
        """
        self.rcv_nxt = segment.seq_number + 1
        self.stats["segments_received"] += 1

        ack = TCPSegment(
            src_port=self.local_port,
            dst_port=self.remote_port,
            seq_number=self.snd_nxt,
            ack_number=self.rcv_nxt,
            flags=TCPFlags.ACK,
            window=TCP_MAX_WINDOW,
        )
        self.stats["segments_sent"] += 1

        if self.state == TCPState.ESTABLISHED:
            self.state = TCPState.CLOSE_WAIT
        elif self.state == TCPState.FIN_WAIT_1:
            self.state = TCPState.CLOSING
        elif self.state == TCPState.FIN_WAIT_2:
            self.state = TCPState.TIME_WAIT

        logger.debug(
            "TCP %s:%d received FIN (-> %s)",
            self.local_ip, self.local_port, self.state.value,
        )
        return ack

    def receive_fin_ack(self, segment: TCPSegment) -> None:
        """Receive ACK for our FIN.

        Transitions:
        - FIN_WAIT_1 -> FIN_WAIT_2
        - LAST_ACK -> CLOSED
        - CLOSING -> TIME_WAIT
        """
        self.snd_una = segment.ack_number
        self.stats["segments_received"] += 1

        if self.state == TCPState.FIN_WAIT_1:
            self.state = TCPState.FIN_WAIT_2
        elif self.state == TCPState.LAST_ACK:
            self.state = TCPState.CLOSED
        elif self.state == TCPState.CLOSING:
            self.state = TCPState.TIME_WAIT

        logger.debug(
            "TCP %s:%d received FIN-ACK (-> %s)",
            self.local_ip, self.local_port, self.state.value,
        )

    def time_wait_expire(self) -> None:
        """Expire TIME_WAIT state.

        Transitions: TIME_WAIT -> CLOSED

        In real TCP, TIME_WAIT lasts 2*MSL (typically 60 seconds).
        In FizzNet, it lasts exactly as long as it takes to call this
        method, which is considerably less.
        """
        if self.state == TCPState.TIME_WAIT:
            self.state = TCPState.CLOSED

    def reset(self) -> TCPSegment:
        """Send RST to immediately tear down the connection."""
        rst = TCPSegment(
            src_port=self.local_port,
            dst_port=self.remote_port,
            seq_number=self.snd_nxt,
            ack_number=0,
            flags=TCPFlags.RST,
            window=0,
        )
        self.state = TCPState.CLOSED
        self.stats["segments_sent"] += 1
        return rst

    @property
    def is_established(self) -> bool:
        return self.state == TCPState.ESTABLISHED

    @property
    def is_closed(self) -> bool:
        return self.state == TCPState.CLOSED

    @property
    def received_data(self) -> bytes:
        """Return all data received so far."""
        return b"".join(self.recv_buffer)

    @property
    def connection_tuple(self) -> tuple[str, int, str, int]:
        return (self.local_ip, self.local_port, self.remote_ip, self.remote_port)


# ---------------------------------------------------------------------------
# Socket API
# ---------------------------------------------------------------------------

class Socket:
    """BSD-style socket abstraction for the FizzNet stack.

    Provides the familiar bind/listen/accept/connect/send/recv/close
    interface that applications expect. Under the hood, each Socket
    manages a TCPConnection and interacts with the NetworkStack for
    packet delivery.

    This is the interface that the FizzBuzz Protocol layer uses to
    establish connections and exchange classification data.
    """

    _next_ephemeral_port = 49152

    def __init__(self, stack: NetworkStack) -> None:
        self._stack = stack
        self._connection: Optional[TCPConnection] = None
        self._local_ip: Optional[str] = None
        self._local_port: Optional[int] = None
        self._bound = False
        self._listening = False
        self._backlog: list[TCPConnection] = []

    @classmethod
    def _allocate_ephemeral_port(cls) -> int:
        """Allocate an ephemeral port from the dynamic range."""
        port = cls._next_ephemeral_port
        cls._next_ephemeral_port += 1
        if cls._next_ephemeral_port > 65535:
            cls._next_ephemeral_port = 49152
        return port

    @classmethod
    def reset_ephemeral_ports(cls) -> None:
        """Reset ephemeral port counter. Used for testing."""
        cls._next_ephemeral_port = 49152

    def bind(self, ip: str, port: int) -> None:
        """Bind the socket to a local address and port."""
        self._local_ip = ip
        self._local_port = port
        self._bound = True
        self._stack.register_socket(ip, port, self)

    def listen(self, backlog: int = 5) -> None:
        """Put the socket in listening state for incoming connections."""
        if not self._bound:
            raise FizzNetProtocolError("Socket must be bound before listening", protocol="TCP")
        self._listening = True

    def accept(self) -> tuple[Socket, tuple[str, int]]:
        """Accept a pending connection from the backlog.

        Returns a new Socket for the accepted connection and the
        remote address tuple.
        """
        if not self._listening:
            raise FizzNetProtocolError("Socket is not listening", protocol="TCP")
        if not self._backlog:
            raise FizzNetProtocolError("No pending connections", protocol="TCP")

        conn = self._backlog.pop(0)
        new_socket = Socket(self._stack)
        new_socket._local_ip = self._local_ip
        new_socket._local_port = self._local_port
        new_socket._connection = conn
        new_socket._bound = True
        return new_socket, (conn.remote_ip, conn.remote_port)

    def connect(self, remote_ip: str, remote_port: int) -> None:
        """Initiate a TCP connection to a remote endpoint.

        Performs the full three-way handshake synchronously.
        """
        if self._local_ip is None:
            # Auto-bind to the stack's primary interface
            iface = self._stack.primary_interface
            if iface is None:
                raise FizzNetProtocolError("No network interface available", protocol="TCP")
            self._local_ip = iface.ip_address
            self._local_port = self._allocate_ephemeral_port()
            self._bound = True

        self._connection = TCPConnection(
            local_ip=self._local_ip,
            local_port=self._local_port,
            remote_ip=remote_ip,
            remote_port=remote_port,
        )

        # Step 1: SYN
        syn = self._connection.initiate_handshake()
        syn_ack = self._stack.deliver_segment(
            syn, self._local_ip, remote_ip,
        )

        if syn_ack is None:
            raise FizzNetConnectionRefusedError(remote_ip, remote_port)

        if syn_ack.is_rst:
            self._connection.state = TCPState.CLOSED
            raise FizzNetConnectionRefusedError(remote_ip, remote_port)

        # Step 2: receive SYN-ACK, send ACK
        ack = self._connection.receive_syn_ack(syn_ack)
        self._stack.deliver_segment(ack, self._local_ip, remote_ip)

    def send(self, data: bytes) -> int:
        """Send data over the connection. Returns bytes sent."""
        if self._connection is None or not self._connection.is_established:
            raise FizzNetProtocolError("Connection not established", protocol="TCP")

        segments = self._connection.send(data)
        for seg in segments:
            response = self._stack.deliver_segment(
                seg, self._local_ip, self._connection.remote_ip,
            )
            if response is not None:
                self._connection.process_ack(response)

        return len(data)

    def recv(self, bufsize: int = 65535) -> bytes:
        """Receive data from the connection."""
        if self._connection is None:
            raise FizzNetProtocolError("Connection not established", protocol="TCP")

        data = self._connection.received_data
        if data:
            self._connection.recv_buffer.clear()
            return data[:bufsize]
        return b""

    def close(self) -> None:
        """Close the connection gracefully with FIN exchange."""
        if self._connection is None:
            return

        if self._connection.state == TCPState.ESTABLISHED:
            fin = self._connection.initiate_close()
            response = self._stack.deliver_segment(
                fin, self._local_ip, self._connection.remote_ip,
            )
            if response is not None:
                if response.is_fin:
                    ack = self._connection.receive_fin(response)
                    self._stack.deliver_segment(
                        ack, self._local_ip, self._connection.remote_ip,
                    )
                else:
                    self._connection.receive_fin_ack(response)

            self._connection.time_wait_expire()

        elif self._connection.state in (TCPState.CLOSE_WAIT,):
            fin = self._connection.initiate_close()
            response = self._stack.deliver_segment(
                fin, self._local_ip, self._connection.remote_ip,
            )
            if response is not None:
                self._connection.receive_fin_ack(response)

        self._connection = None

    def enqueue_connection(self, conn: TCPConnection) -> None:
        """Add a connection to the accept backlog (used by the stack)."""
        self._backlog.append(conn)

    @property
    def connection(self) -> Optional[TCPConnection]:
        return self._connection

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_established

    @property
    def pending_connections(self) -> int:
        return len(self._backlog)


# ---------------------------------------------------------------------------
# Network Interface (Simulated NIC)
# ---------------------------------------------------------------------------

class NetworkInterface:
    """Simulated network interface card (NIC).

    Each interface has a MAC address, IP address, and separate transmit
    and receive queues for Ethernet frames. The interface participates
    in the ARP resolution process and maintains per-interface packet
    counters.

    In a real system, this would represent a physical or virtual NIC
    bound to a specific network segment. Here, it represents a Python
    object bound to a specific position in a list, which is arguably
    the same thing at a sufficient level of abstraction.
    """

    def __init__(
        self,
        name: str,
        mac_address: str,
        ip_address: str,
        netmask: str = "255.255.255.0",
    ) -> None:
        self.name = name
        self.mac_address = mac_address
        self.ip_address = ip_address
        self.netmask = netmask
        self.tx_queue: list[EthernetFrame] = []
        self.rx_queue: list[EthernetFrame] = []
        self.is_up = True
        self.stats = {
            "tx_packets": 0,
            "rx_packets": 0,
            "tx_bytes": 0,
            "rx_bytes": 0,
            "tx_errors": 0,
            "rx_errors": 0,
            "tx_dropped": 0,
            "rx_dropped": 0,
        }

    def transmit(self, frame: EthernetFrame) -> bool:
        """Enqueue a frame for transmission."""
        if not self.is_up:
            self.stats["tx_dropped"] += 1
            return False
        self.tx_queue.append(frame)
        self.stats["tx_packets"] += 1
        self.stats["tx_bytes"] += len(frame)
        return True

    def receive(self, frame: EthernetFrame) -> bool:
        """Enqueue a received frame."""
        if not self.is_up:
            self.stats["rx_dropped"] += 1
            return False
        if not frame.validate():
            self.stats["rx_errors"] += 1
            return False
        self.rx_queue.append(frame)
        self.stats["rx_packets"] += 1
        self.stats["rx_bytes"] += len(frame)
        return True

    def drain_tx(self) -> list[EthernetFrame]:
        """Drain and return all frames from the TX queue."""
        frames = list(self.tx_queue)
        self.tx_queue.clear()
        return frames

    def drain_rx(self) -> list[EthernetFrame]:
        """Drain and return all frames from the RX queue."""
        frames = list(self.rx_queue)
        self.rx_queue.clear()
        return frames


# ---------------------------------------------------------------------------
# Network Stack
# ---------------------------------------------------------------------------

class NetworkStack:
    """Complete TCP/IP network stack tying all layers together.

    The NetworkStack manages network interfaces, the ARP table, IP
    routing, and TCP connection dispatch. It serves as the central
    coordination point for all network operations within the FizzNet
    subsystem.

    Packets are routed between interfaces based on destination IP.
    Since all interfaces exist within the same process, routing is
    implemented as a dictionary lookup — the most efficient routing
    algorithm known to computer science, with O(1) complexity and
    zero packet loss (barring CRC failures or TTL expiration).
    """

    def __init__(self) -> None:
        self._interfaces: dict[str, NetworkInterface] = {}
        self._arp_table = ARPTable()
        self._listening_sockets: dict[tuple[str, int], Socket] = {}
        self._connections: dict[tuple[str, int, str, int], TCPConnection] = {}
        self._ip_to_interface: dict[str, NetworkInterface] = {}
        self.stats = {
            "packets_routed": 0,
            "packets_dropped": 0,
            "icmp_sent": 0,
            "icmp_received": 0,
            "arp_requests": 0,
            "arp_replies": 0,
        }

    def add_interface(self, iface: NetworkInterface) -> None:
        """Register a network interface with the stack."""
        self._interfaces[iface.name] = iface
        self._ip_to_interface[iface.ip_address] = iface
        self._arp_table.add(iface.ip_address, iface.mac_address)

    def remove_interface(self, name: str) -> Optional[NetworkInterface]:
        """Remove a network interface."""
        iface = self._interfaces.pop(name, None)
        if iface:
            self._ip_to_interface.pop(iface.ip_address, None)
            self._arp_table.remove(iface.ip_address)
        return iface

    @property
    def primary_interface(self) -> Optional[NetworkInterface]:
        """Return the first registered interface, or None."""
        if self._interfaces:
            return next(iter(self._interfaces.values()))
        return None

    @property
    def arp_table(self) -> ARPTable:
        return self._arp_table

    @property
    def interfaces(self) -> dict[str, NetworkInterface]:
        return dict(self._interfaces)

    def register_socket(self, ip: str, port: int, sock: Socket) -> None:
        """Register a socket for incoming connections."""
        self._listening_sockets[(ip, port)] = sock

    def unregister_socket(self, ip: str, port: int) -> None:
        """Unregister a listening socket."""
        self._listening_sockets.pop((ip, port), None)

    def resolve_mac(self, ip: str) -> Optional[str]:
        """Resolve an IP to a MAC address via ARP."""
        mac = self._arp_table.resolve(ip)
        if mac is None:
            # Check if we have the interface directly
            iface = self._ip_to_interface.get(ip)
            if iface:
                self._arp_table.add(ip, iface.mac_address)
                self.stats["arp_requests"] += 1
                self.stats["arp_replies"] += 1
                return iface.mac_address
        return mac

    def ping(self, src_ip: str, dst_ip: str, sequence: int = 1) -> Optional[ICMPMessage]:
        """Send an ICMP echo request and return the reply, or None.

        This is the FizzNet equivalent of the ping utility. The request
        traverses the full stack: ICMP message is encapsulated in an
        IPv4 packet, which is encapsulated in an Ethernet frame, which
        is delivered to the destination interface, unwrapped, and an
        echo reply is generated and returned through the same layers.
        """
        request = ICMPMessage(
            type=ICMP_ECHO_REQUEST,
            code=0,
            identifier=0xFB22,
            sequence_number=sequence,
            payload=b"FizzBuzzPing",
        )

        icmp_bytes = request.to_bytes()
        packet = IPv4Packet(
            ttl=DEFAULT_TTL,
            protocol=1,  # ICMP
            src_ip=src_ip,
            dst_ip=dst_ip,
            payload=icmp_bytes,
        ).finalize()

        self.stats["icmp_sent"] += 1

        # Route to destination
        dst_iface = self._ip_to_interface.get(dst_ip)
        if dst_iface is None:
            return None

        if not dst_iface.is_up:
            return None

        # Validate checksum
        if not packet.validate_checksum():
            return None

        # TTL check
        if packet.ttl <= 0:
            return None

        # Parse ICMP and generate reply
        received_icmp = ICMPMessage.from_bytes(packet.payload)
        self.stats["icmp_received"] += 1

        if received_icmp.type == ICMP_ECHO_REQUEST:
            reply = received_icmp.make_reply()
            return reply

        return None

    def deliver_segment(
        self,
        segment: TCPSegment,
        src_ip: str,
        dst_ip: str,
    ) -> Optional[TCPSegment]:
        """Deliver a TCP segment from src_ip to dst_ip.

        Encapsulates the segment in an IPv4 packet (optionally in an
        Ethernet frame), routes it to the destination, and dispatches
        it to the appropriate TCP connection or listening socket.

        Returns a response segment if one is generated (e.g., SYN-ACK,
        ACK, FIN-ACK), or None.
        """
        self.stats["packets_routed"] += 1

        # Check destination is reachable
        dst_iface = self._ip_to_interface.get(dst_ip)
        if dst_iface is None or not dst_iface.is_up:
            self.stats["packets_dropped"] += 1
            return None

        # Wrap in IPv4 for stats tracking
        ip_packet = IPv4Packet(
            ttl=DEFAULT_TTL,
            protocol=6,  # TCP
            src_ip=src_ip,
            dst_ip=dst_ip,
            payload=segment.to_bytes(),
        ).finalize()

        # Wrap in Ethernet frame
        src_mac = self.resolve_mac(src_ip) or "00:00:00:00:00:00"
        dst_mac = self.resolve_mac(dst_ip) or "ff:ff:ff:ff:ff:ff"
        frame = EthernetFrame(
            dst_mac=dst_mac,
            src_mac=src_mac,
            ethertype=0x0800,
            payload=ip_packet.to_bytes(),
        ).finalize()

        src_iface = self._ip_to_interface.get(src_ip)
        if src_iface:
            src_iface.transmit(frame)
        dst_iface.receive(frame)

        # Dispatch to connection or listening socket
        conn_key = (dst_ip, segment.dst_port, src_ip, segment.src_port)
        conn = self._connections.get(conn_key)

        if conn is not None:
            # Existing connection
            if segment.is_syn_ack:
                return segment  # Pass back to caller (handshake step 2)
            elif segment.is_fin:
                return conn.receive_fin(segment)
            elif segment.payload:
                return conn.receive_data(segment)
            elif segment.is_ack:
                conn.process_ack(segment)
                if conn.state == TCPState.SYN_RECEIVED:
                    conn.complete_handshake(segment)
                return None
            return None

        # Check listening sockets
        listen_key = (dst_ip, segment.dst_port)
        listener = self._listening_sockets.get(listen_key)

        if listener is not None and segment.is_syn:
            # Create server-side connection
            server_conn = TCPConnection(
                local_ip=dst_ip,
                local_port=segment.dst_port,
                remote_ip=src_ip,
                remote_port=segment.src_port,
            )
            server_conn.state = TCPState.LISTEN

            # Register the connection
            self._connections[conn_key] = server_conn

            # Process SYN and get SYN-ACK
            syn_ack = server_conn.receive_syn(segment)
            listener.enqueue_connection(server_conn)
            return syn_ack

        # No connection, no listener — send RST
        if not segment.is_rst:
            self.stats["packets_dropped"] += 1
            return TCPSegment(
                src_port=segment.dst_port,
                dst_port=segment.src_port,
                seq_number=0,
                ack_number=segment.seq_number + 1,
                flags=TCPFlags.RST | TCPFlags.ACK,
                window=0,
            )

        return None

    def register_connection(self, conn: TCPConnection) -> None:
        """Register a TCP connection for segment dispatch."""
        key = conn.connection_tuple
        self._connections[key] = conn

    def unregister_connection(self, conn: TCPConnection) -> None:
        """Remove a TCP connection from the dispatch table."""
        key = conn.connection_tuple
        self._connections.pop(key, None)


# ---------------------------------------------------------------------------
# FizzBuzz Protocol (Application Layer)
# ---------------------------------------------------------------------------

class FizzBuzzProtocolMessageType(Enum):
    """FizzBuzz Protocol (FBZP) message types.

    The FBZP is a simple request-response protocol layered on top of
    TCP for reliable FizzBuzz classification delivery. Each message
    carries a type byte, a 4-byte payload length, and the payload itself.
    """

    FIZZ_REQUEST = 0x01
    FIZZ_RESPONSE = 0x02
    FIZZ_ERROR = 0x03
    FIZZ_HEARTBEAT = 0x04


@dataclass
class FizzBuzzProtocolMessage:
    """A single FBZP message."""

    msg_type: FizzBuzzProtocolMessageType
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        """Serialize the FBZP message."""
        return struct.pack("!BI", self.msg_type.value, len(self.payload)) + self.payload

    @classmethod
    def from_bytes(cls, data: bytes) -> FizzBuzzProtocolMessage:
        """Deserialize an FBZP message."""
        if len(data) < 5:
            raise FizzNetProtocolError("FBZP message too short", protocol="FBZP")
        type_byte, length = struct.unpack("!BI", data[:5])
        msg_type = FizzBuzzProtocolMessageType(type_byte)
        payload = data[5:5 + length]
        return cls(msg_type=msg_type, payload=payload)


class FizzBuzzProtocol:
    """Application-layer protocol for FizzBuzz classification over TCP.

    Implements a request-response protocol where clients send a number
    and servers respond with the FizzBuzz classification. Each exchange
    traverses the full TCP/IP stack: application data is segmented by
    TCP, encapsulated in IPv4 packets, wrapped in Ethernet frames, and
    delivered through the simulated network infrastructure.

    This ensures that every FizzBuzz classification benefits from
    reliable, ordered, flow-controlled delivery — guarantees that are
    absolutely essential when the alternative is a direct function call.
    """

    def __init__(self, stack: NetworkStack) -> None:
        self._stack = stack
        self._server_socket: Optional[Socket] = None
        self._client_sockets: list[Socket] = []
        self.stats = {
            "requests_sent": 0,
            "responses_sent": 0,
            "requests_received": 0,
            "responses_received": 0,
            "errors": 0,
        }

    def start_server(self, ip: str, port: int = 5353) -> None:
        """Start the FBZP server on the given address."""
        self._server_socket = Socket(self._stack)
        self._server_socket.bind(ip, port)
        self._server_socket.listen(backlog=10)
        logger.info("FBZP server listening on %s:%d", ip, port)

    def stop_server(self) -> None:
        """Stop the FBZP server."""
        if self._server_socket:
            self._stack.unregister_socket(
                self._server_socket._local_ip,
                self._server_socket._local_port,
            )
            self._server_socket = None

    def send_request(self, client_ip: str, server_ip: str, server_port: int, number: int) -> Optional[str]:
        """Send a FIZZ_REQUEST and return the classification string.

        Establishes a TCP connection to the server, sends the number,
        receives the classification, and returns it.
        """
        sock = Socket(self._stack)
        try:
            sock.connect(server_ip, server_port)
        except (FizzNetConnectionRefusedError, FizzNetProtocolError):
            self.stats["errors"] += 1
            return None

        # Send request
        request = FizzBuzzProtocolMessage(
            msg_type=FizzBuzzProtocolMessageType.FIZZ_REQUEST,
            payload=str(number).encode("utf-8"),
        )
        sock.send(request.to_bytes())
        self.stats["requests_sent"] += 1

        # The server processes in deliver_segment callbacks, so we need
        # to handle the server side explicitly for in-memory operation
        self._process_server_request(number)

        # Receive response
        response_data = sock.recv()
        sock.close()

        if response_data:
            try:
                msg = FizzBuzzProtocolMessage.from_bytes(response_data)
                if msg.msg_type == FizzBuzzProtocolMessageType.FIZZ_RESPONSE:
                    self.stats["responses_received"] += 1
                    return msg.payload.decode("utf-8")
            except (FizzNetProtocolError, ValueError):
                self.stats["errors"] += 1

        return None

    def _process_server_request(self, number: int) -> None:
        """Process an incoming request on the server side.

        Accepts the connection, reads the request, classifies the
        number, and sends the response.
        """
        if self._server_socket is None:
            return

        if self._server_socket.pending_connections == 0:
            return

        conn_socket, (remote_ip, remote_port) = self._server_socket.accept()
        self.stats["requests_received"] += 1

        # Classify the number using standard FizzBuzz logic
        classification = self._classify(number)

        # Send response
        response = FizzBuzzProtocolMessage(
            msg_type=FizzBuzzProtocolMessageType.FIZZ_RESPONSE,
            payload=classification.encode("utf-8"),
        )

        if conn_socket.connection is not None:
            segments = conn_socket.connection.send(response.to_bytes())
            # Deliver response segments back to client
            for seg in segments:
                self._stack.deliver_segment(
                    seg,
                    conn_socket._local_ip,
                    remote_ip,
                )
        self.stats["responses_sent"] += 1

    @staticmethod
    def _classify(number: int) -> str:
        """Classify a number using the canonical FizzBuzz algorithm.

        This classification is performed at the application protocol
        layer, independent of the main evaluation engine. It serves
        as a reference implementation for protocol-level validation.
        """
        if number % 15 == 0:
            return "FizzBuzz"
        elif number % 3 == 0:
            return "Fizz"
        elif number % 5 == 0:
            return "Buzz"
        return str(number)


# ---------------------------------------------------------------------------
# Network Dashboard
# ---------------------------------------------------------------------------

class NetworkDashboard:
    """ASCII dashboard for FizzNet network stack monitoring.

    Displays packet counters, TCP connection state, congestion window
    history, ARP table contents, and interface statistics in a
    professional, enterprise-grade ASCII art format.
    """

    @staticmethod
    def render(
        stack: NetworkStack,
        protocol: Optional[FizzBuzzProtocol] = None,
        connections: Optional[list[TCPConnection]] = None,
        width: int = 60,
    ) -> str:
        """Render the complete network dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        spacer = "|" + " " * (width - 2) + "|"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        lines.append(border)
        lines.append(center("FIZZNET TCP/IP PROTOCOL STACK"))
        lines.append(center("Network Operations Dashboard"))
        lines.append(border)

        # Interface summary
        lines.append(center("[ Network Interfaces ]"))
        lines.append(border)
        for name, iface in stack.interfaces.items():
            status = "UP" if iface.is_up else "DOWN"
            lines.append(left(f"{name}: {iface.ip_address} ({iface.mac_address}) [{status}]"))
            lines.append(left(f"  TX: {iface.stats['tx_packets']} pkts / {iface.stats['tx_bytes']} bytes"))
            lines.append(left(f"  RX: {iface.stats['rx_packets']} pkts / {iface.stats['rx_bytes']} bytes"))
        lines.append(border)

        # ARP table
        lines.append(center("[ ARP Table ]"))
        lines.append(border)
        arp_entries = stack.arp_table.entries
        if arp_entries:
            for ip, entry in arp_entries.items():
                lines.append(left(f"{ip} -> {entry.mac_address}"))
        else:
            lines.append(left("(empty)"))
        lines.append(border)

        # Stack statistics
        lines.append(center("[ Stack Statistics ]"))
        lines.append(border)
        lines.append(left(f"Packets routed:    {stack.stats['packets_routed']}"))
        lines.append(left(f"Packets dropped:   {stack.stats['packets_dropped']}"))
        lines.append(left(f"ICMP sent:         {stack.stats['icmp_sent']}"))
        lines.append(left(f"ICMP received:     {stack.stats['icmp_received']}"))
        lines.append(left(f"ARP requests:      {stack.stats['arp_requests']}"))
        lines.append(left(f"ARP replies:       {stack.stats['arp_replies']}"))
        lines.append(border)

        # TCP connections
        if connections:
            lines.append(center("[ TCP Connections ]"))
            lines.append(border)
            for conn in connections:
                lines.append(left(
                    f"{conn.local_ip}:{conn.local_port} -> "
                    f"{conn.remote_ip}:{conn.remote_port} "
                    f"[{conn.state.value}]"
                ))
                lines.append(left(f"  cwnd: {conn.cwnd:.0f}  ssthresh: {conn.ssthresh:.0f}"))
                lines.append(left(
                    f"  sent: {conn.stats['segments_sent']} segs / "
                    f"{conn.stats['bytes_sent']} bytes"
                ))
                lines.append(left(
                    f"  recv: {conn.stats['segments_received']} segs / "
                    f"{conn.stats['bytes_received']} bytes"
                ))
                lines.append(left(f"  retransmits: {conn.stats['retransmissions']}  "
                                  f"fast-retransmits: {conn.stats['fast_retransmits']}"))

                # Congestion window sparkline
                cwnd_hist = conn.stats.get("cwnd_history", [])
                if cwnd_hist:
                    sparkline = NetworkDashboard._render_sparkline(cwnd_hist, width - 6)
                    lines.append(left(f"  cwnd: {sparkline}"))
            lines.append(border)

        # Protocol stats
        if protocol:
            lines.append(center("[ FBZP Protocol ]"))
            lines.append(border)
            lines.append(left(f"Requests sent:     {protocol.stats['requests_sent']}"))
            lines.append(left(f"Requests received: {protocol.stats['requests_received']}"))
            lines.append(left(f"Responses sent:    {protocol.stats['responses_sent']}"))
            lines.append(left(f"Responses received:{protocol.stats['responses_received']}"))
            lines.append(left(f"Errors:            {protocol.stats['errors']}"))
            lines.append(border)

        return "\n".join(lines)

    @staticmethod
    def _render_sparkline(values: list[float], width: int) -> str:
        """Render a sparkline using Unicode block characters."""
        if not values:
            return ""
        blocks = " ▁▂▃▄▅▆▇█"
        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val if max_val != min_val else 1.0

        # Sample to fit width
        if len(values) > width:
            step = len(values) / width
            sampled = [values[int(i * step)] for i in range(width)]
        else:
            sampled = values

        chars = []
        for v in sampled:
            idx = int((v - min_val) / val_range * (len(blocks) - 1))
            chars.append(blocks[idx])
        return "".join(chars)


# ---------------------------------------------------------------------------
# Network Middleware (IMiddleware)
# ---------------------------------------------------------------------------

class NetworkMiddleware(IMiddleware):
    """Middleware that wraps every FizzBuzz evaluation in a TCP connection.

    For each number processed by the evaluation pipeline, this middleware
    establishes a full TCP connection (three-way handshake), sends a
    FIZZ_REQUEST message containing the number, receives the classification
    via FIZZ_RESPONSE, and tears down the connection (four-way close).

    This ensures that every single FizzBuzz result benefits from TCP's
    reliability guarantees: ordered delivery, flow control, congestion
    management, and checksum verification. The overhead of establishing
    and tearing down a TCP connection for each integer is a small price
    to pay for the assurance that no FizzBuzz classification is ever
    lost in transit between two Python objects in the same process.

    Priority 940 places this middleware late in the pipeline, after
    most processing has completed but before final recording middleware.
    """

    def __init__(
        self,
        stack: Optional[NetworkStack] = None,
        server_ip: str = "10.0.0.1",
        client_ip: str = "10.0.0.2",
        server_port: int = 5353,
        enable_dashboard: bool = False,
    ) -> None:
        self._stack = stack or self._create_default_stack(server_ip, client_ip)
        self._server_ip = server_ip
        self._client_ip = client_ip
        self._server_port = server_port
        self._enable_dashboard = enable_dashboard
        self._protocol = FizzBuzzProtocol(self._stack)
        self._connections: list[TCPConnection] = []

        # Start the FBZP server
        self._protocol.start_server(server_ip, server_port)

    @staticmethod
    def _create_default_stack(server_ip: str, client_ip: str) -> NetworkStack:
        """Create a default two-interface network stack."""
        stack = NetworkStack()
        server_iface = NetworkInterface(
            name="eth0",
            mac_address="02:fb:00:00:00:01",
            ip_address=server_ip,
        )
        client_iface = NetworkInterface(
            name="eth1",
            mac_address="02:fb:00:00:00:02",
            ip_address=client_ip,
        )
        stack.add_interface(server_iface)
        stack.add_interface(client_iface)
        return stack

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the evaluation through the FizzNet TCP/IP stack."""
        result = next_handler(context)

        # Send the number through the network stack for classification
        # verification via the FizzBuzz Protocol
        number = context.number
        classification = self._protocol.send_request(
            client_ip=self._client_ip,
            server_ip=self._server_ip,
            server_port=self._server_port,
            number=number,
        )

        result.metadata["fizznet_classification"] = classification
        result.metadata["fizznet_packets_routed"] = self._stack.stats["packets_routed"]

        return result

    def get_name(self) -> str:
        return "NetworkMiddleware"

    def get_priority(self) -> int:
        return 940

    @property
    def stack(self) -> NetworkStack:
        return self._stack

    @property
    def protocol(self) -> FizzBuzzProtocol:
        return self._protocol

    @property
    def connections(self) -> list[TCPConnection]:
        return self._connections

    def render_dashboard(self, width: int = 60) -> str:
        """Render the FizzNet dashboard."""
        return NetworkDashboard.render(
            stack=self._stack,
            protocol=self._protocol,
            connections=self._connections,
            width=width,
        )

"""
Enterprise FizzBuzz Platform - NTP/PTP Clock Synchronization Module

Provides distributed clock synchronization infrastructure for the Enterprise
FizzBuzz Platform. In production distributed systems, clock skew between
nodes leads to causal ordering violations, stale reads, and split-brain
scenarios. The FizzBuzz evaluation pipeline requires sub-microsecond
timestamp coherence to ensure that evaluation results across simulated
cluster nodes carry monotonically increasing, causally consistent timestamps.

This module implements the NTP v4 clock discipline algorithm (RFC 5905) with
a PI controller for frequency steering, Allan deviation analysis for clock
stability characterization, and a stratum hierarchy for hierarchical time
distribution. A full ASCII dashboard provides real-time visibility into clock
offset, delay, jitter, and frequency drift across all simulated nodes.

Key components:
  - VirtualClock: Simulated clock with configurable drift rate and jitter
  - NTPPacket: NTP v4 message format with all standard header fields
  - NTPClient/NTPServer: Request-response NTP protocol implementation
  - PIController: Proportional-integral clock discipline algorithm
  - StratumHierarchy: Multi-stratum time distribution topology
  - AllanDeviationAnalyzer: Frequency stability measurement (sigma_y(tau))
  - ClockDashboard: ASCII dashboard with offset graph and stratum tree
  - ClockMiddleware: Pipeline integration for synchronized timestamps
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ClockSyncError,
    ClockDriftExceededError,
    StratumError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

NTP_VERSION = 4
NTP_EPOCH_OFFSET = 2208988800  # Seconds between 1900-01-01 and 1970-01-01
MAX_STRATUM = 16  # RFC 5905: stratum 16 means unsynchronized
DEFAULT_POLL_INTERVAL = 6  # log2 seconds (64s)
DEFAULT_PRECISION = -20  # log2 seconds (~1 microsecond)
PPM_TO_RATIO = 1e-6  # 1 ppm = 1e-6 frequency offset


class LeapIndicator(IntEnum):
    """NTP Leap Indicator field values per RFC 5905."""
    NO_WARNING = 0
    LAST_MINUTE_61 = 1
    LAST_MINUTE_59 = 2
    ALARM = 3


class NTPMode(IntEnum):
    """NTP association mode values per RFC 5905."""
    RESERVED = 0
    SYMMETRIC_ACTIVE = 1
    SYMMETRIC_PASSIVE = 2
    CLIENT = 3
    SERVER = 4
    BROADCAST = 5
    CONTROL = 6
    PRIVATE = 7


# ============================================================
# VirtualClock
# ============================================================


class VirtualClock:
    """Simulated clock with configurable drift rate and random jitter.

    Models a real-world oscillator with a fixed frequency offset (drift)
    and Gaussian phase jitter. The drift rate is specified in parts per
    million (ppm), where 1 ppm corresponds to 1 microsecond of accumulated
    error per second of real time.

    In production NTP deployments, commodity oscillators exhibit drift
    rates of 1-100 ppm. This clock faithfully reproduces that behavior
    for the FizzBuzz evaluation pipeline.
    """

    def __init__(
        self,
        name: str = "clock-0",
        drift_ppm: float = 0.0,
        jitter_ns: float = 0.0,
        initial_offset_ns: float = 0.0,
    ) -> None:
        self._name = name
        self._drift_ppm = drift_ppm
        self._jitter_ns = jitter_ns
        self._base_time = time.monotonic()
        self._offset_ns = initial_offset_ns
        self._frequency_adjustment_ppm: float = 0.0
        self._step_corrections: list[float] = []
        self._total_adjustments: int = 0

    @property
    def name(self) -> str:
        """Clock identifier."""
        return self._name

    @property
    def drift_ppm(self) -> float:
        """Current effective drift rate in parts per million."""
        return self._drift_ppm + self._frequency_adjustment_ppm

    @property
    def nominal_drift_ppm(self) -> float:
        """Nominal (uncorrected) drift rate in parts per million."""
        return self._drift_ppm

    @property
    def frequency_adjustment_ppm(self) -> float:
        """Current PI controller frequency adjustment in ppm."""
        return self._frequency_adjustment_ppm

    def now_ns(self) -> float:
        """Return the current time in nanoseconds according to this clock.

        The returned value includes the accumulated drift, any PI controller
        frequency adjustments, and optional Gaussian jitter.
        """
        elapsed = time.monotonic() - self._base_time
        drift_ns = elapsed * self.drift_ppm * PPM_TO_RATIO * 1e9
        jitter = self._generate_jitter()
        return time.time() * 1e9 + self._offset_ns + drift_ns + jitter

    def now_seconds(self) -> float:
        """Return the current time in seconds according to this clock."""
        return self.now_ns() / 1e9

    def step(self, offset_ns: float) -> None:
        """Apply a step correction to the clock offset.

        Step corrections are used when the offset exceeds the PI controller's
        slew range (typically > 128ms). The clock is immediately adjusted
        by the specified amount.
        """
        self._offset_ns += offset_ns
        self._step_corrections.append(offset_ns)
        self._total_adjustments += 1
        logger.debug(
            "Clock '%s' step correction: %.3f us",
            self._name,
            offset_ns / 1000,
        )

    def adjust_frequency(self, ppm: float) -> None:
        """Apply a frequency adjustment from the PI controller.

        The adjustment modifies the effective drift rate, steering the
        clock frequency toward the reference.
        """
        self._frequency_adjustment_ppm = ppm
        self._total_adjustments += 1
        logger.debug(
            "Clock '%s' frequency adjustment: %.6f ppm (effective drift: %.6f ppm)",
            self._name,
            ppm,
            self.drift_ppm,
        )

    def _generate_jitter(self) -> float:
        """Generate Gaussian phase jitter using the Box-Muller transform.

        Uses a deterministic-ish approach based on the current time to avoid
        requiring an external random state, while still producing
        sufficiently random-looking jitter for clock simulation purposes.
        """
        if self._jitter_ns == 0.0:
            return 0.0
        # Use time-based seed for pseudo-random jitter
        t = time.monotonic() * 1e9
        # Simple hash-based pseudo-random
        x = math.sin(t * 0.0000001 + hash(self._name)) * 43758.5453
        u = x - math.floor(x)
        # Map uniform to approximate Gaussian via central limit theorem approx
        return (u - 0.5) * 2.0 * self._jitter_ns

    def get_statistics(self) -> dict[str, Any]:
        """Return clock statistics for dashboard rendering."""
        return {
            "name": self._name,
            "drift_ppm": self._drift_ppm,
            "frequency_adjustment_ppm": self._frequency_adjustment_ppm,
            "effective_drift_ppm": self.drift_ppm,
            "jitter_ns": self._jitter_ns,
            "offset_ns": self._offset_ns,
            "total_adjustments": self._total_adjustments,
            "step_corrections": len(self._step_corrections),
        }


# ============================================================
# NTPPacket
# ============================================================


@dataclass
class NTPPacket:
    """NTP v4 message format per RFC 5905.

    Encodes all standard NTP header fields including Leap Indicator,
    Version Number, Mode, Stratum, Poll Interval, Precision, Root Delay,
    Root Dispersion, Reference Identifier, and the four NTP timestamps
    (Reference, Originate, Receive, Transmit).

    In a real NTP implementation, this would be serialized to a 48-byte
    UDP payload. Here, we use a Python dataclass because the FizzBuzz
    evaluation pipeline communicates via in-process method calls rather
    than actual UDP datagrams, which is arguably more reliable.
    """

    leap_indicator: int = LeapIndicator.NO_WARNING
    version: int = NTP_VERSION
    mode: int = NTPMode.CLIENT
    stratum: int = 0
    poll: int = DEFAULT_POLL_INTERVAL
    precision: int = DEFAULT_PRECISION
    root_delay: float = 0.0
    root_dispersion: float = 0.0
    reference_id: str = "LOCL"
    reference_timestamp: float = 0.0
    originate_timestamp: float = 0.0
    receive_timestamp: float = 0.0
    transmit_timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the packet to a dictionary for logging and diagnostics."""
        return {
            "li": self.leap_indicator,
            "vn": self.version,
            "mode": self.mode,
            "stratum": self.stratum,
            "poll": self.poll,
            "precision": self.precision,
            "root_delay": self.root_delay,
            "root_dispersion": self.root_dispersion,
            "reference_id": self.reference_id,
            "reference_ts": self.reference_timestamp,
            "originate_ts": self.originate_timestamp,
            "receive_ts": self.receive_timestamp,
            "transmit_ts": self.transmit_timestamp,
        }


# ============================================================
# NTPServer
# ============================================================


class NTPServer:
    """NTP server that responds to client requests with reference timestamps.

    Acts as a time source at a specific stratum level. Stratum 0 represents
    an atomic reference clock (GPS, cesium, rubidium). Stratum 1 servers
    are directly synchronized to stratum 0 sources. Each additional stratum
    level adds one hop of synchronization distance.

    For the FizzBuzz platform, the stratum 0 reference is the host system's
    monotonic clock, which is arguably as authoritative as cesium for
    determining whether 15 is divisible by both 3 and 5.
    """

    def __init__(
        self,
        clock: VirtualClock,
        stratum: int = 1,
        reference_id: str = "LOCL",
    ) -> None:
        if stratum < 0 or stratum > MAX_STRATUM:
            raise StratumError(stratum, f"Stratum must be 0-{MAX_STRATUM}")
        self._clock = clock
        self._stratum = stratum
        self._reference_id = reference_id
        self._requests_served: int = 0
        self._last_reference_update: float = 0.0

    @property
    def stratum(self) -> int:
        """Server stratum level."""
        return self._stratum

    @property
    def reference_id(self) -> str:
        """Reference identifier (e.g., GPS, PPS, LOCL)."""
        return self._reference_id

    @property
    def requests_served(self) -> int:
        """Total number of NTP requests served."""
        return self._requests_served

    def handle_request(self, request: NTPPacket) -> NTPPacket:
        """Process an incoming NTP client request and generate a response.

        Implements the NTP server-side timestamp exchange:
        - T1 (originate): copied from the client's transmit timestamp
        - T2 (receive): server's clock at request arrival
        - T3 (transmit): server's clock at response departure
        """
        t2 = self._clock.now_seconds()

        response = NTPPacket(
            leap_indicator=LeapIndicator.NO_WARNING,
            version=NTP_VERSION,
            mode=NTPMode.SERVER,
            stratum=self._stratum,
            poll=request.poll,
            precision=DEFAULT_PRECISION,
            root_delay=0.0,
            root_dispersion=0.0,
            reference_id=self._reference_id,
            reference_timestamp=self._last_reference_update or t2,
            originate_timestamp=request.transmit_timestamp,
            receive_timestamp=t2,
            transmit_timestamp=self._clock.now_seconds(),
        )

        self._requests_served += 1
        self._last_reference_update = t2

        logger.debug(
            "NTP server (stratum %d) served request #%d: T2=%.9f T3=%.9f",
            self._stratum,
            self._requests_served,
            t2,
            response.transmit_timestamp,
        )

        return response


# ============================================================
# NTPClient
# ============================================================


@dataclass
class NTPMeasurement:
    """Result of a single NTP request-response exchange."""
    offset: float  # Clock offset in seconds
    delay: float  # Round-trip delay in seconds
    t1: float  # Originate timestamp
    t2: float  # Receive timestamp
    t3: float  # Transmit timestamp (server)
    t4: float  # Destination timestamp
    stratum: int  # Server stratum


class NTPClient:
    """NTP client that queries servers and computes clock offset and delay.

    Implements the standard NTP on-wire protocol:
      offset = ((T2 - T1) + (T3 - T4)) / 2
      delay  = (T4 - T1) - (T3 - T2)

    Where:
      T1 = originate timestamp (client send time)
      T2 = receive timestamp (server receive time)
      T3 = transmit timestamp (server send time)
      T4 = destination timestamp (client receive time)

    The offset represents the clock difference between client and server.
    The delay represents the total network round-trip time. In the FizzBuzz
    platform, the "network" is an in-process function call, so delays are
    dominated by Python method dispatch overhead rather than fiber optic
    propagation, but the algorithm remains mathematically correct.
    """

    def __init__(self, clock: VirtualClock) -> None:
        self._clock = clock
        self._measurements: list[NTPMeasurement] = []
        self._best_offset: Optional[float] = None
        self._best_delay: Optional[float] = None

    @property
    def measurements(self) -> list[NTPMeasurement]:
        """All recorded NTP measurements."""
        return list(self._measurements)

    @property
    def best_offset(self) -> Optional[float]:
        """Best (lowest delay) offset measurement in seconds."""
        return self._best_offset

    @property
    def best_delay(self) -> Optional[float]:
        """Best (lowest) round-trip delay in seconds."""
        return self._best_delay

    @property
    def measurement_count(self) -> int:
        """Total number of NTP exchanges performed."""
        return len(self._measurements)

    def query(self, server: NTPServer) -> NTPMeasurement:
        """Perform a single NTP request-response exchange with the server.

        Records T1 before sending, receives T2 and T3 from the server
        response, and records T4 upon receipt. Then computes offset and
        delay using the standard NTP formulas.
        """
        # T1: client originate timestamp
        t1 = self._clock.now_seconds()

        request = NTPPacket(
            mode=NTPMode.CLIENT,
            version=NTP_VERSION,
            transmit_timestamp=t1,
        )

        # Server processes the request (T2, T3 inside)
        response = server.handle_request(request)

        # T4: client destination timestamp
        t4 = self._clock.now_seconds()

        t2 = response.receive_timestamp
        t3 = response.transmit_timestamp

        # NTP offset formula: ((T2 - T1) + (T3 - T4)) / 2
        offset = ((t2 - t1) + (t3 - t4)) / 2.0

        # NTP delay formula: (T4 - T1) - (T3 - T2)
        delay = (t4 - t1) - (t3 - t2)

        measurement = NTPMeasurement(
            offset=offset,
            delay=delay,
            t1=t1,
            t2=t2,
            t3=t3,
            t4=t4,
            stratum=response.stratum,
        )

        self._measurements.append(measurement)

        # Track best measurement (lowest delay = most accurate offset)
        if self._best_delay is None or delay < self._best_delay:
            self._best_delay = delay
            self._best_offset = offset

        logger.debug(
            "NTP measurement: offset=%.9fs delay=%.9fs stratum=%d",
            offset,
            delay,
            response.stratum,
        )

        return measurement

    def poll_burst(self, server: NTPServer, count: int = 8) -> list[NTPMeasurement]:
        """Perform a burst of NTP queries and return all measurements.

        NTP implementations typically send a burst of 8 packets and select
        the measurement with the lowest delay as the most accurate estimate
        of the true offset. This mirrors that behavior.
        """
        results = []
        for _ in range(count):
            results.append(self.query(server))
        return results

    def get_filtered_offset(self) -> Optional[float]:
        """Return the median-filtered offset from recent measurements.

        Uses the median of the last 8 measurements to reject outliers
        caused by asymmetric delay variations. The median filter is
        standard practice in NTP implementations.
        """
        if not self._measurements:
            return None
        recent = self._measurements[-8:]
        offsets = sorted(m.offset for m in recent)
        n = len(offsets)
        if n % 2 == 0:
            return (offsets[n // 2 - 1] + offsets[n // 2]) / 2.0
        return offsets[n // 2]

    def get_statistics(self) -> dict[str, Any]:
        """Return client statistics for dashboard rendering."""
        if not self._measurements:
            return {
                "measurement_count": 0,
                "best_offset_us": None,
                "best_delay_us": None,
                "mean_offset_us": None,
                "stddev_offset_us": None,
            }

        offsets = [m.offset * 1e6 for m in self._measurements]
        mean_offset = sum(offsets) / len(offsets)
        variance = sum((o - mean_offset) ** 2 for o in offsets) / len(offsets)

        return {
            "measurement_count": len(self._measurements),
            "best_offset_us": self._best_offset * 1e6 if self._best_offset is not None else None,
            "best_delay_us": self._best_delay * 1e6 if self._best_delay is not None else None,
            "mean_offset_us": mean_offset,
            "stddev_offset_us": math.sqrt(variance),
        }


# ============================================================
# PIController
# ============================================================


class PIController:
    """Proportional-Integral clock discipline controller.

    Implements the PI feedback loop used by NTP to steer clock frequency
    toward zero offset. The controller computes a frequency adjustment
    (in ppm) based on the measured offset:

      adjustment = Kp * offset + Ki * integral(offset)

    The proportional term (Kp) provides immediate correction proportional
    to the current error. The integral term (Ki) eliminates steady-state
    error by accumulating past offsets.

    Typical NTP implementations use:
      Kp = 0.7 (aggressive initial correction)
      Ki = 0.3 (gradual steady-state elimination)

    The step threshold determines when the controller switches from
    frequency slewing to step correction. Per RFC 5905, the default
    step threshold is 128 milliseconds.
    """

    def __init__(
        self,
        kp: float = 0.7,
        ki: float = 0.3,
        step_threshold_s: float = 0.128,
        max_adjustment_ppm: float = 500.0,
    ) -> None:
        self._kp = kp
        self._ki = ki
        self._step_threshold_s = step_threshold_s
        self._max_adjustment_ppm = max_adjustment_ppm
        self._integral: float = 0.0
        self._last_offset: Optional[float] = None
        self._corrections: list[dict[str, Any]] = []

    @property
    def kp(self) -> float:
        """Proportional gain."""
        return self._kp

    @property
    def ki(self) -> float:
        """Integral gain."""
        return self._ki

    @property
    def integral(self) -> float:
        """Accumulated integral term."""
        return self._integral

    @property
    def corrections(self) -> list[dict[str, Any]]:
        """History of all correction actions."""
        return list(self._corrections)

    def discipline(
        self,
        clock: VirtualClock,
        offset_s: float,
    ) -> dict[str, Any]:
        """Apply clock discipline based on the measured offset.

        If the offset exceeds the step threshold, a step correction is
        applied immediately. Otherwise, a frequency adjustment is computed
        using the PI algorithm and applied to the clock's frequency trim.

        Returns a dictionary describing the correction action taken.
        """
        action: dict[str, Any]

        if abs(offset_s) > self._step_threshold_s:
            # Step correction: offset too large for frequency slewing
            clock.step(offset_s * 1e9)
            action = {
                "type": "step",
                "offset_s": offset_s,
                "correction_ns": offset_s * 1e9,
            }
            # Reset integral after step to avoid windup
            self._integral = 0.0
            logger.info(
                "PI controller: step correction of %.3f ms applied to '%s'",
                offset_s * 1000,
                clock.name,
            )
        else:
            # PI frequency adjustment
            self._integral += offset_s

            # Compute adjustment in ppm
            p_term = self._kp * offset_s * 1e6  # Convert to ppm scale
            i_term = self._ki * self._integral * 1e6
            adjustment_ppm = p_term + i_term

            # Clamp to maximum adjustment
            adjustment_ppm = max(
                -self._max_adjustment_ppm,
                min(self._max_adjustment_ppm, adjustment_ppm),
            )

            clock.adjust_frequency(-adjustment_ppm)

            action = {
                "type": "slew",
                "offset_s": offset_s,
                "p_term_ppm": p_term,
                "i_term_ppm": i_term,
                "adjustment_ppm": -adjustment_ppm,
                "integral": self._integral,
            }
            logger.debug(
                "PI controller: slew adjustment of %.6f ppm "
                "(P=%.6f, I=%.6f) applied to '%s'",
                -adjustment_ppm,
                p_term,
                i_term,
                clock.name,
            )

        self._last_offset = offset_s
        self._corrections.append(action)
        return action


# ============================================================
# StratumHierarchy
# ============================================================


@dataclass
class StratumNode:
    """A node in the stratum hierarchy tree."""
    name: str
    stratum: int
    clock: VirtualClock
    server: NTPServer
    client: Optional[NTPClient] = None
    parent: Optional[str] = None
    children: list[str] = field(default_factory=list)
    pi_controller: Optional[PIController] = None


class StratumHierarchy:
    """Hierarchical stratum topology for NTP time distribution.

    Models the standard NTP stratum hierarchy:
      - Stratum 0: Reference clocks (atomic, GPS, PPS)
      - Stratum 1: Primary servers directly synchronized to stratum 0
      - Stratum 2+: Secondary servers synchronized to higher-stratum sources

    Each stratum level adds synchronization distance and reduces accuracy.
    The FizzBuzz platform's hierarchy ensures that all evaluation nodes
    derive their time from a common reference, preventing causal ordering
    violations in the FizzBuzz result stream.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, StratumNode] = {}
        self._root: Optional[str] = None

    @property
    def nodes(self) -> dict[str, StratumNode]:
        """All nodes in the hierarchy."""
        return dict(self._nodes)

    @property
    def root(self) -> Optional[str]:
        """Name of the root (stratum 0/1) node."""
        return self._root

    def add_reference(
        self,
        name: str,
        drift_ppm: float = 0.0,
        reference_id: str = "GPS",
    ) -> StratumNode:
        """Add a stratum 1 primary server with a stratum 0 reference clock.

        The reference clock is modeled as a VirtualClock with near-zero
        drift (atomic clocks achieve < 0.01 ppm). The primary server
        serves as the root of the stratum tree.
        """
        clock = VirtualClock(name=f"{name}-clock", drift_ppm=drift_ppm)
        server = NTPServer(clock=clock, stratum=1, reference_id=reference_id)
        node = StratumNode(
            name=name,
            stratum=1,
            clock=clock,
            server=server,
        )
        self._nodes[name] = node
        if self._root is None:
            self._root = name
        return node

    def add_secondary(
        self,
        name: str,
        parent_name: str,
        drift_ppm: float = 10.0,
        jitter_ns: float = 100.0,
        kp: float = 0.7,
        ki: float = 0.3,
    ) -> StratumNode:
        """Add a secondary server synchronized to a parent node.

        The secondary server's stratum is one level below its parent.
        A PI controller is attached to discipline the local clock
        against the parent's time source.
        """
        if parent_name not in self._nodes:
            raise StratumError(
                0,
                f"Parent node '{parent_name}' not found in hierarchy",
            )

        parent = self._nodes[parent_name]
        stratum = parent.stratum + 1

        if stratum > MAX_STRATUM:
            raise StratumError(
                stratum,
                f"Maximum stratum depth ({MAX_STRATUM}) exceeded",
            )

        clock = VirtualClock(
            name=f"{name}-clock",
            drift_ppm=drift_ppm,
            jitter_ns=jitter_ns,
        )
        server = NTPServer(
            clock=clock,
            stratum=stratum,
            reference_id=parent_name[:4].upper(),
        )
        client = NTPClient(clock=clock)
        pi = PIController(kp=kp, ki=ki)

        node = StratumNode(
            name=name,
            stratum=stratum,
            clock=clock,
            server=server,
            client=client,
            parent=parent_name,
            pi_controller=pi,
        )

        self._nodes[name] = node
        parent.children.append(name)
        return node

    def synchronize(self, node_name: str, burst_count: int = 4) -> Optional[dict[str, Any]]:
        """Synchronize a secondary node against its parent.

        Performs a burst of NTP queries, selects the best measurement,
        and applies PI discipline to the local clock.

        Returns the discipline action taken, or None if the node has
        no parent (i.e., it is the reference).
        """
        if node_name not in self._nodes:
            raise ClockSyncError(
                f"Node '{node_name}' not found in stratum hierarchy"
            )

        node = self._nodes[node_name]
        if node.parent is None or node.client is None or node.pi_controller is None:
            return None  # Reference clock, nothing to synchronize

        parent = self._nodes[node.parent]
        measurements = node.client.poll_burst(parent.server, count=burst_count)

        # Select the measurement with the lowest delay
        best = min(measurements, key=lambda m: m.delay)

        # Apply PI discipline
        action = node.pi_controller.discipline(node.clock, best.offset)
        action["node"] = node_name
        action["parent"] = node.parent
        action["stratum"] = node.stratum

        return action

    def synchronize_all(self, burst_count: int = 4) -> list[dict[str, Any]]:
        """Synchronize all secondary nodes in the hierarchy.

        Traverses the stratum tree breadth-first, synchronizing each
        node against its parent. This ensures that higher-stratum nodes
        are synchronized before their children.
        """
        if self._root is None:
            return []

        actions: list[dict[str, Any]] = []
        queue = [self._root]
        visited: set[str] = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            action = self.synchronize(current, burst_count=burst_count)
            if action is not None:
                actions.append(action)

            node = self._nodes[current]
            for child in node.children:
                queue.append(child)

        return actions

    def get_tree_lines(self, node_name: Optional[str] = None, prefix: str = "", is_last: bool = True) -> list[str]:
        """Render the stratum hierarchy as an ASCII tree."""
        if node_name is None:
            node_name = self._root
        if node_name is None:
            return ["(empty hierarchy)"]

        node = self._nodes[node_name]
        connector = "`-- " if is_last else "|-- "
        line = f"{prefix}{connector}[S{node.stratum}] {node.name} ({node.clock.drift_ppm:+.2f} ppm)"

        lines = [line]
        child_prefix = prefix + ("    " if is_last else "|   ")
        for i, child_name in enumerate(node.children):
            is_last_child = (i == len(node.children) - 1)
            lines.extend(
                self.get_tree_lines(child_name, child_prefix, is_last_child)
            )

        return lines


# ============================================================
# AllanDeviationAnalyzer
# ============================================================


class AllanDeviationAnalyzer:
    """Measures clock frequency stability using Allan deviation (ADEV).

    Allan deviation (sigma_y(tau)) is the standard metric for characterizing
    oscillator stability. It quantifies frequency fluctuations over a
    specified averaging interval tau. Lower Allan deviation indicates a
    more stable oscillator.

    The overlapping Allan deviation is computed as:

      sigma_y^2(tau) = (1 / (2 * (N - 2m + 1))) * sum(
          (x[i+2m] - 2*x[i+m] + x[i])^2
          for i in range(N - 2m + 1)
      ) / tau^2

    where x[i] are phase samples, m is the averaging factor, and
    tau = m * tau_0 (base sampling interval).
    """

    def __init__(self, base_interval_s: float = 1.0) -> None:
        self._base_interval = base_interval_s
        self._phase_samples: list[float] = []
        self._frequency_samples: list[float] = []

    @property
    def sample_count(self) -> int:
        """Number of recorded phase samples."""
        return len(self._phase_samples)

    def record_phase(self, phase_offset_s: float) -> None:
        """Record a phase offset measurement (in seconds).

        Phase samples should be collected at uniform intervals equal to
        the base_interval_s specified at construction time.
        """
        self._phase_samples.append(phase_offset_s)

    def record_frequency(self, frequency_offset_ppm: float) -> None:
        """Record a frequency offset measurement (in ppm).

        Used for computing modified Allan deviation and supplementary
        stability metrics.
        """
        self._frequency_samples.append(frequency_offset_ppm)

    def compute_adev(self, tau_factor: int = 1) -> Optional[float]:
        """Compute the overlapping Allan deviation for a given tau factor.

        tau_factor: averaging factor (m). The actual averaging time is
        tau = tau_factor * base_interval_s.

        Returns sigma_y(tau) in seconds, or None if insufficient samples.
        """
        m = tau_factor
        n = len(self._phase_samples)

        if n < 2 * m + 1:
            return None  # Insufficient data

        tau = m * self._base_interval

        total = 0.0
        count = n - 2 * m
        for i in range(count):
            diff = self._phase_samples[i + 2 * m] - 2 * self._phase_samples[i + m] + self._phase_samples[i]
            total += diff * diff

        if count <= 0 or tau == 0:
            return None

        allan_variance = total / (2.0 * count * tau * tau)
        return math.sqrt(allan_variance)

    def compute_adev_spectrum(self, max_tau_factor: Optional[int] = None) -> list[tuple[float, float]]:
        """Compute Allan deviation across multiple tau values.

        Returns a list of (tau, sigma_y) pairs for plotting the ADEV
        spectrum. The spectrum reveals the dominant noise processes
        affecting clock stability:
          - tau^(-1) slope: white phase noise
          - tau^(-1/2) slope: white frequency noise (typical for quartz)
          - tau^0 (flat): flicker frequency noise
          - tau^(+1/2) slope: random walk frequency noise
        """
        n = len(self._phase_samples)
        if max_tau_factor is None:
            max_tau_factor = max(1, n // 4)

        spectrum: list[tuple[float, float]] = []
        tau_factor = 1
        while tau_factor <= max_tau_factor:
            adev = self.compute_adev(tau_factor)
            if adev is not None:
                tau = tau_factor * self._base_interval
                spectrum.append((tau, adev))
            tau_factor *= 2  # Octave spacing per convention

        return spectrum

    def get_statistics(self) -> dict[str, Any]:
        """Return ADEV statistics for dashboard rendering."""
        spectrum = self.compute_adev_spectrum()
        return {
            "sample_count": len(self._phase_samples),
            "base_interval_s": self._base_interval,
            "spectrum": spectrum,
            "adev_at_tau1": self.compute_adev(1),
        }


# ============================================================
# ClockDashboard
# ============================================================


class ClockDashboard:
    """ASCII dashboard for NTP clock synchronization telemetry.

    Renders a comprehensive view of clock synchronization state including:
      - Offset history sparkline graph
      - Stratum hierarchy tree
      - Allan deviation spectrum plot
      - PI controller state
      - Per-node synchronization statistics
    """

    @staticmethod
    def render(
        hierarchy: StratumHierarchy,
        analyzer: Optional[AllanDeviationAnalyzer] = None,
        offset_history: Optional[list[float]] = None,
        width: int = 72,
    ) -> str:
        """Render the complete clock synchronization dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"

        lines.append(border)
        lines.append(_center("FIZZCLOCK: NTP CLOCK SYNCHRONIZATION DASHBOARD", width))
        lines.append(border)

        # Stratum hierarchy tree
        lines.append(_center("STRATUM HIERARCHY", width))
        lines.append("+" + "-" * (width - 2) + "+")
        tree_lines = hierarchy.get_tree_lines()
        for tl in tree_lines:
            lines.append(f"| {tl:<{width - 4}} |")
        lines.append("+" + "-" * (width - 2) + "+")

        # Per-node statistics
        lines.append("")
        lines.append(_center("NODE SYNCHRONIZATION STATUS", width))
        lines.append("+" + "-" * (width - 2) + "+")

        for name, node in hierarchy.nodes.items():
            stats = node.clock.get_statistics()
            drift_str = f"{stats['effective_drift_ppm']:+.4f} ppm"
            adj_str = f"{stats['frequency_adjustment_ppm']:+.4f} ppm"
            line = f"  {name:<20} S{node.stratum}  drift={drift_str}  adj={adj_str}"
            lines.append(f"| {line:<{width - 4}} |")

            if node.client is not None:
                client_stats = node.client.get_statistics()
                if client_stats["measurement_count"] > 0:
                    off_str = f"{client_stats['best_offset_us']:.3f}" if client_stats['best_offset_us'] is not None else "N/A"
                    del_str = f"{client_stats['best_delay_us']:.3f}" if client_stats['best_delay_us'] is not None else "N/A"
                    detail = f"    queries={client_stats['measurement_count']}  offset={off_str}us  delay={del_str}us"
                    lines.append(f"| {detail:<{width - 4}} |")

        lines.append("+" + "-" * (width - 2) + "+")

        # Offset history graph
        if offset_history and len(offset_history) > 1:
            lines.append("")
            lines.append(_center("CLOCK OFFSET HISTORY (us)", width))
            lines.append("+" + "-" * (width - 2) + "+")
            graph_lines = _render_sparkline(offset_history, width=width - 4, height=8)
            for gl in graph_lines:
                lines.append(f"| {gl:<{width - 4}} |")
            lines.append("+" + "-" * (width - 2) + "+")

        # Allan deviation spectrum
        if analyzer is not None:
            stats = analyzer.get_statistics()
            spectrum = stats["spectrum"]
            if spectrum:
                lines.append("")
                lines.append(_center("ALLAN DEVIATION SPECTRUM", width))
                lines.append("+" + "-" * (width - 2) + "+")
                adev_lines = _render_adev_plot(spectrum, width=width - 4, height=6)
                for al in adev_lines:
                    lines.append(f"| {al:<{width - 4}} |")
                lines.append("+" + "-" * (width - 2) + "+")

        lines.append(border)
        return "\n".join(lines)


def _center(text: str, width: int) -> str:
    """Center text within a bordered line."""
    inner = width - 4
    return f"| {text:^{inner}} |"


def _render_sparkline(
    values: list[float],
    width: int = 68,
    height: int = 8,
) -> list[str]:
    """Render a simple ASCII sparkline graph of offset values."""
    if not values:
        return ["(no data)"]

    # Downsample if necessary
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values

    min_val = min(sampled)
    max_val = max(sampled)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = 1.0

    blocks = " _.-~*#@"
    lines: list[str] = []

    # Header with scale
    lines.append(f"  max: {max_val:+.3f} us")

    # Build character grid
    grid: list[list[str]] = [[" " for _ in range(len(sampled))] for _ in range(height)]

    for col, val in enumerate(sampled):
        normalized = (val - min_val) / val_range
        row = int(normalized * (height - 1))
        row = min(row, height - 1)
        grid[height - 1 - row][col] = blocks[min(col % len(blocks), len(blocks) - 1)] if col < len(blocks) else "#"
        # Use a consistent marker
        grid[height - 1 - row][col] = "*"

    for row in grid:
        lines.append("  " + "".join(row))

    lines.append(f"  min: {min_val:+.3f} us")
    lines.append(f"  samples: {len(values)}")

    return lines


def _render_adev_plot(
    spectrum: list[tuple[float, float]],
    width: int = 68,
    height: int = 6,
) -> list[str]:
    """Render an ASCII log-log plot of Allan deviation vs tau."""
    if not spectrum:
        return ["(no data)"]

    lines: list[str] = []
    lines.append("  tau (s)    | sigma_y (s)")
    lines.append("  -----------+-----------")

    for tau, adev in spectrum:
        # Simple bar chart representation
        bar_len = max(1, int(min(adev * 1e9, width - 30)))
        bar = "#" * min(bar_len, width - 30)
        lines.append(f"  {tau:>8.2f}  | {adev:.3e}  {bar}")

    return lines


# ============================================================
# ClockMiddleware
# ============================================================


class ClockMiddleware(IMiddleware):
    """Middleware that synchronizes evaluation timestamps across simulated nodes.

    Before each FizzBuzz evaluation, the middleware synchronizes all nodes
    in the stratum hierarchy and stamps the processing context with the
    synchronized timestamp, clock offset, and stratum level.

    This ensures that evaluation results carry causally consistent
    timestamps regardless of which simulated cluster node performed the
    evaluation. Without this middleware, clock skew between nodes could
    cause evaluation #42 to appear to have occurred before evaluation #41,
    which would be a violation of the FizzBuzz causal ordering invariant.
    """

    def __init__(
        self,
        hierarchy: StratumHierarchy,
        analyzer: Optional[AllanDeviationAnalyzer] = None,
        sync_every_n: int = 1,
        enable_dashboard: bool = False,
    ) -> None:
        self._hierarchy = hierarchy
        self._analyzer = analyzer
        self._sync_every_n = max(1, sync_every_n)
        self._enable_dashboard = enable_dashboard
        self._eval_count: int = 0
        self._offset_history: list[float] = []
        self._sync_actions: list[dict[str, Any]] = []

    @property
    def hierarchy(self) -> StratumHierarchy:
        """The stratum hierarchy being managed."""
        return self._hierarchy

    @property
    def analyzer(self) -> Optional[AllanDeviationAnalyzer]:
        """The Allan deviation analyzer, if configured."""
        return self._analyzer

    @property
    def offset_history(self) -> list[float]:
        """History of measured clock offsets in microseconds."""
        return list(self._offset_history)

    @property
    def sync_actions(self) -> list[dict[str, Any]]:
        """History of all synchronization actions."""
        return list(self._sync_actions)

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Synchronize clocks and stamp the context before evaluation."""
        self._eval_count += 1

        # Synchronize at the configured interval
        if self._eval_count % self._sync_every_n == 0:
            actions = self._hierarchy.synchronize_all(burst_count=4)
            self._sync_actions.extend(actions)

            # Record offset for history and ADEV analysis
            for action in actions:
                offset_us = action.get("offset_s", 0.0) * 1e6
                self._offset_history.append(offset_us)
                if self._analyzer is not None:
                    self._analyzer.record_phase(action.get("offset_s", 0.0))

        # Stamp context with clock sync metadata
        root_name = self._hierarchy.root
        if root_name is not None:
            root_node = self._hierarchy.nodes[root_name]
            context.metadata["clock_sync"] = {
                "reference_time": root_node.clock.now_seconds(),
                "stratum": root_node.stratum,
                "sync_count": self._eval_count,
                "node_count": len(self._hierarchy.nodes),
            }

        result = next_handler(context)
        return result

    def get_name(self) -> str:
        return "ClockMiddleware"

    def get_priority(self) -> int:
        return 3  # Early in the pipeline, before timing middleware

    def render_dashboard(self) -> str:
        """Render the clock synchronization dashboard."""
        return ClockDashboard.render(
            hierarchy=self._hierarchy,
            analyzer=self._analyzer,
            offset_history=self._offset_history,
        )


# ============================================================
# Factory function
# ============================================================


def create_clock_sync_subsystem(
    drift_ppm: float = 10.0,
    num_secondary_nodes: int = 3,
    enable_adev: bool = True,
) -> tuple[StratumHierarchy, Optional[AllanDeviationAnalyzer], ClockMiddleware]:
    """Create a complete clock synchronization subsystem.

    Builds a stratum hierarchy with one reference server and the specified
    number of secondary nodes, each with progressively increasing drift
    rates to simulate a realistic heterogeneous cluster.

    Returns:
        A tuple of (hierarchy, analyzer, middleware).
    """
    hierarchy = StratumHierarchy()

    # Stratum 1 reference server (near-zero drift)
    hierarchy.add_reference("ntp-primary", drift_ppm=0.001, reference_id="GPS")

    # Secondary nodes with varying drift rates
    for i in range(num_secondary_nodes):
        node_drift = drift_ppm * (1.0 + i * 0.5)
        hierarchy.add_secondary(
            name=f"fizz-node-{i}",
            parent_name="ntp-primary",
            drift_ppm=node_drift,
            jitter_ns=50.0 * (1 + i),
        )

    analyzer = AllanDeviationAnalyzer(base_interval_s=1.0) if enable_adev else None

    middleware = ClockMiddleware(
        hierarchy=hierarchy,
        analyzer=analyzer,
        sync_every_n=1,
        enable_dashboard=True,
    )

    # Perform initial synchronization
    hierarchy.synchronize_all(burst_count=4)

    return hierarchy, analyzer, middleware

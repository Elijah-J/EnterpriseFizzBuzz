"""
Enterprise FizzBuzz Platform - FizzFPGA Synthesis Engine

Implements a complete FPGA synthesis flow for hardware-accelerated FizzBuzz
evaluation. Rather than relying on software modulo operations that execute
sequentially on a general-purpose CPU, this module synthesizes the FizzBuzz
divisibility logic directly into configurable hardware primitives: lookup
tables (LUTs), flip-flops, and programmable routing fabric.

The synthesis pipeline mirrors real FPGA design flows:

1. **Logic synthesis**: Map Boolean divisibility functions to LUT primitives
2. **Placement**: Assign LUTs and flip-flops to physical fabric locations
3. **Routing**: Connect placed elements through the switch matrix fabric
4. **Timing analysis**: Verify setup/hold constraints across clock domains
5. **Bitstream generation**: Produce the binary configuration for the device
6. **Partial reconfiguration**: Update regions without full device reprogramming

The FizzBuzz-by-3 circuit uses a 2-bit state machine tracking (number mod 3),
while the FizzBuzz-by-5 circuit tracks (number mod 5) with a 3-bit state
machine. Both are mapped to 4-input LUTs with registered outputs, placed
within a simulated island-style FPGA architecture, and connected through
a hierarchical routing fabric with configurable switch matrices.

All synthesis, placement, and routing algorithms are implemented in pure
Python using only the standard library.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FPGASynthesisError,
    LUTConfigurationError,
    FlipFlopTimingError,
    RoutingCongestionError,
    BitstreamGenerationError,
    ClockDomainCrossingError,
    PartialReconfigurationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enums
# ============================================================


class LUTSize(Enum):
    """Lookup table input widths available in the fabric."""
    LUT4 = 4
    LUT6 = 6


class FlipFlopType(Enum):
    """Flip-flop types available in the configurable logic block."""
    D_FF = auto()
    T_FF = auto()
    JK_FF = auto()


class RoutingResourceType(Enum):
    """Types of routing resources in the interconnect fabric."""
    LOCAL = auto()
    SINGLE = auto()
    DOUBLE = auto()
    LONG = auto()


class ClockDomainID(Enum):
    """Named clock domains in the FizzBuzz FPGA design."""
    SYSTEM = auto()
    FIZZ = auto()
    BUZZ = auto()
    IO = auto()


class SynthesisPhase(Enum):
    """Phases of the FPGA synthesis pipeline."""
    ELABORATION = auto()
    MAPPING = auto()
    PLACEMENT = auto()
    ROUTING = auto()
    TIMING = auto()
    BITSTREAM = auto()


# ============================================================
# LUT (Lookup Table)
# ============================================================


@dataclass
class TruthTableEntry:
    """A single row in a LUT truth table."""
    inputs: tuple[bool, ...]
    output: bool


class LookupTable:
    """Configurable k-input lookup table.

    A LUT is the fundamental combinational logic primitive in an FPGA.
    It implements an arbitrary Boolean function of k inputs by storing
    the complete truth table in SRAM cells. During operation, the input
    signals select a single SRAM cell whose stored value drives the
    output. This is equivalent to a 2^k-to-1 multiplexer.
    """

    def __init__(self, lut_id: str, num_inputs: int = 4) -> None:
        if num_inputs not in (4, 6):
            raise LUTConfigurationError(lut_id, num_inputs, 6)
        self.lut_id = lut_id
        self.num_inputs = num_inputs
        self._truth_table: dict[tuple[bool, ...], bool] = {}
        self._init_mask: int = 0
        self._configured = False

    def configure(self, init_mask: int) -> None:
        """Configure the LUT with a truth table encoded as an integer bitmask.

        The init_mask is a 2^num_inputs-bit integer where bit i corresponds
        to the output for input pattern i (interpreted as binary).
        """
        max_mask = (1 << (1 << self.num_inputs)) - 1
        if init_mask < 0 or init_mask > max_mask:
            raise LUTConfigurationError(
                self.lut_id, self.num_inputs, self.num_inputs
            )
        self._init_mask = init_mask
        self._truth_table.clear()
        for i in range(1 << self.num_inputs):
            bits = tuple(bool((i >> b) & 1) for b in range(self.num_inputs))
            output = bool((init_mask >> i) & 1)
            self._truth_table[bits] = output
        self._configured = True
        logger.debug("LUT %s configured with INIT=0x%x", self.lut_id, init_mask)

    def evaluate(self, inputs: tuple[bool, ...]) -> bool:
        """Evaluate the LUT for the given input pattern."""
        if not self._configured:
            raise FPGASynthesisError(
                f"LUT '{self.lut_id}' has not been configured.",
                error_code="EFP-FG00",
            )
        if len(inputs) != self.num_inputs:
            raise LUTConfigurationError(self.lut_id, len(inputs), self.num_inputs)
        return self._truth_table[inputs]

    @property
    def utilization(self) -> float:
        """Fraction of truth table entries that output True."""
        if not self._configured:
            return 0.0
        ones = bin(self._init_mask).count("1")
        return ones / (1 << self.num_inputs)


# ============================================================
# Flip-Flop
# ============================================================


@dataclass
class TimingConstraint:
    """Setup and hold time constraints for a flip-flop."""
    setup_ns: float = 0.5
    hold_ns: float = 0.2
    clock_to_q_ns: float = 0.3


class FlipFlop:
    """Configurable flip-flop with timing constraint verification.

    Each flip-flop captures its data input on the active clock edge and
    holds the value until the next clock edge. The timing analysis engine
    verifies that setup and hold constraints are met across all paths.
    """

    def __init__(
        self,
        ff_id: str,
        ff_type: FlipFlopType = FlipFlopType.D_FF,
        clock_domain: ClockDomainID = ClockDomainID.SYSTEM,
        timing: Optional[TimingConstraint] = None,
    ) -> None:
        self.ff_id = ff_id
        self.ff_type = ff_type
        self.clock_domain = clock_domain
        self.timing = timing or TimingConstraint()
        self._state: bool = False
        self._next_state: bool = False

    def set_input(self, value: bool) -> None:
        """Set the D input for the next clock edge."""
        self._next_state = value

    def clock_edge(self) -> bool:
        """Apply the active clock edge, latching the input value."""
        self._state = self._next_state
        return self._state

    @property
    def q(self) -> bool:
        """Current output value."""
        return self._state

    def check_timing(self, data_arrival_ns: float, clock_period_ns: float) -> float:
        """Verify setup time constraint and return slack in nanoseconds.

        Positive slack means the constraint is met. Negative slack indicates
        a timing violation that must be resolved by the place-and-route
        engine through retiming or placement optimization.
        """
        setup_slack = clock_period_ns - data_arrival_ns - self.timing.setup_ns
        if setup_slack < 0:
            raise FlipFlopTimingError(self.ff_id, "setup", abs(setup_slack))
        return setup_slack


# ============================================================
# Routing Fabric
# ============================================================


@dataclass
class RoutingSegment:
    """A single segment in the FPGA routing fabric."""
    segment_id: str
    resource_type: RoutingResourceType
    source: str
    destination: str
    delay_ns: float = 0.5
    occupied: bool = False


class RoutingFabric:
    """Hierarchical interconnect fabric with configurable switch matrices.

    The routing fabric connects LUT outputs to flip-flop inputs and to
    other LUT inputs through a network of programmable switch points.
    The fabric provides multiple routing resource types (local, single,
    double, long) to balance delay and congestion.
    """

    def __init__(self, grid_width: int = 8, grid_height: int = 8) -> None:
        self.grid_width = grid_width
        self.grid_height = grid_height
        self._segments: dict[str, RoutingSegment] = {}
        self._connections: dict[str, list[str]] = defaultdict(list)
        self._utilization: dict[RoutingResourceType, int] = defaultdict(int)
        self._capacity: dict[RoutingResourceType, int] = {
            RoutingResourceType.LOCAL: grid_width * grid_height * 8,
            RoutingResourceType.SINGLE: grid_width * grid_height * 4,
            RoutingResourceType.DOUBLE: grid_width * grid_height * 2,
            RoutingResourceType.LONG: grid_width + grid_height,
        }
        self._initialize_fabric()

    def _initialize_fabric(self) -> None:
        """Create the base routing resource segments."""
        seg_id = 0
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                for rt in RoutingResourceType:
                    name = f"seg_{rt.name}_{x}_{y}_{seg_id}"
                    delay = {
                        RoutingResourceType.LOCAL: 0.2,
                        RoutingResourceType.SINGLE: 0.5,
                        RoutingResourceType.DOUBLE: 0.8,
                        RoutingResourceType.LONG: 1.5,
                    }[rt]
                    self._segments[name] = RoutingSegment(
                        segment_id=name,
                        resource_type=rt,
                        source=f"clb_{x}_{y}",
                        destination="",
                        delay_ns=delay,
                    )
                    seg_id += 1

    def route(self, source: str, destination: str, resource_type: RoutingResourceType = RoutingResourceType.SINGLE) -> RoutingSegment:
        """Route a connection between two elements using the specified resource type."""
        cap = self._capacity.get(resource_type, 0)
        used = self._utilization.get(resource_type, 0)
        if cap > 0 and used >= cap:
            pct = (used / cap) * 100
            raise RoutingCongestionError(resource_type.name, pct)

        seg_id = f"route_{source}_to_{destination}_{uuid.uuid4().hex[:8]}"
        seg = RoutingSegment(
            segment_id=seg_id,
            resource_type=resource_type,
            source=source,
            destination=destination,
            occupied=True,
        )
        self._segments[seg_id] = seg
        self._connections[source].append(destination)
        self._utilization[resource_type] += 1
        return seg

    def get_utilization(self, resource_type: RoutingResourceType) -> float:
        """Return the utilization percentage for the given resource type."""
        cap = self._capacity.get(resource_type, 1)
        used = self._utilization.get(resource_type, 0)
        return (used / cap) * 100.0 if cap > 0 else 0.0

    @property
    def total_utilization(self) -> float:
        """Return the overall routing utilization percentage."""
        total_cap = sum(self._capacity.values())
        total_used = sum(self._utilization.values())
        return (total_used / total_cap) * 100.0 if total_cap > 0 else 0.0


# ============================================================
# Clock Domain Manager
# ============================================================


@dataclass
class ClockDomain:
    """A clock domain with frequency and phase information."""
    domain_id: ClockDomainID
    frequency_mhz: float
    phase_deg: float = 0.0

    @property
    def period_ns(self) -> float:
        return 1000.0 / self.frequency_mhz


class ClockDomainManager:
    """Manages clock domains and verifies domain crossing safety.

    Every signal path that crosses from one clock domain to another must
    be explicitly synchronized to avoid metastability. The manager
    maintains a registry of all clock domains and validates CDC paths.
    """

    def __init__(self) -> None:
        self._domains: dict[ClockDomainID, ClockDomain] = {}
        self._crossings: list[tuple[ClockDomainID, ClockDomainID, str]] = []
        self._synchronized: set[tuple[ClockDomainID, ClockDomainID, str]] = set()

    def add_domain(self, domain_id: ClockDomainID, frequency_mhz: float, phase_deg: float = 0.0) -> ClockDomain:
        """Register a new clock domain."""
        domain = ClockDomain(domain_id=domain_id, frequency_mhz=frequency_mhz, phase_deg=phase_deg)
        self._domains[domain_id] = domain
        return domain

    def register_crossing(self, source: ClockDomainID, target: ClockDomainID, signal: str) -> None:
        """Register a clock domain crossing path."""
        self._crossings.append((source, target, signal))

    def synchronize_crossing(self, source: ClockDomainID, target: ClockDomainID, signal: str) -> None:
        """Mark a CDC path as properly synchronized."""
        self._synchronized.add((source, target, signal))

    def verify_all_crossings(self) -> list[tuple[ClockDomainID, ClockDomainID, str]]:
        """Return all unsynchronized CDC paths."""
        violations = []
        for src, tgt, sig in self._crossings:
            if src != tgt and (src, tgt, sig) not in self._synchronized:
                violations.append((src, tgt, sig))
        return violations

    def get_domain(self, domain_id: ClockDomainID) -> ClockDomain:
        """Retrieve a clock domain by ID."""
        if domain_id not in self._domains:
            raise FPGASynthesisError(
                f"Clock domain '{domain_id.name}' is not registered.",
                error_code="EFP-FG00",
            )
        return self._domains[domain_id]


# ============================================================
# Configurable Logic Block (CLB)
# ============================================================


@dataclass
class CLB:
    """Configurable Logic Block containing LUTs and flip-flops.

    A CLB is the fundamental tile in an island-style FPGA architecture.
    Each CLB contains a pair of LUTs and associated flip-flops, providing
    both combinational and sequential logic within a single placement site.
    """
    clb_id: str
    x: int
    y: int
    luts: list[LookupTable] = field(default_factory=list)
    flip_flops: list[FlipFlop] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.luts:
            self.luts = [
                LookupTable(f"{self.clb_id}_lut0"),
                LookupTable(f"{self.clb_id}_lut1"),
            ]
        if not self.flip_flops:
            self.flip_flops = [
                FlipFlop(f"{self.clb_id}_ff0"),
                FlipFlop(f"{self.clb_id}_ff1"),
            ]


# ============================================================
# Bitstream Generator
# ============================================================


class BitstreamGenerator:
    """Generates the binary configuration bitstream for the FPGA.

    The bitstream encodes the complete device configuration: LUT truth
    tables, flip-flop initialization values, routing switch states, and
    clock management settings. It is the final artifact of the synthesis
    flow, ready to be loaded into the physical FPGA device.
    """

    def __init__(self) -> None:
        self._frames: list[bytes] = []
        self._header: bytes = b""

    def generate(
        self,
        clbs: list[CLB],
        routes: dict[str, RoutingSegment],
        clock_domains: dict[ClockDomainID, ClockDomain],
    ) -> bytes:
        """Generate the complete bitstream from the placed and routed design."""
        if not clbs:
            raise BitstreamGenerationError("No CLBs in the design.")

        self._frames.clear()

        # Header frame: magic number + device info
        header = b"FIZZ" + len(clbs).to_bytes(4, "little")
        header += len(routes).to_bytes(4, "little")
        header += len(clock_domains).to_bytes(4, "little")
        self._frames.append(header)

        # CLB configuration frames
        for clb in clbs:
            frame = clb.clb_id.encode("utf-8")[:16].ljust(16, b"\x00")
            for lut in clb.luts:
                frame += lut._init_mask.to_bytes(4, "little")
            for ff in clb.flip_flops:
                frame += (1 if ff.q else 0).to_bytes(1, "little")
            self._frames.append(frame)

        # Routing configuration frames
        for seg_id, seg in routes.items():
            frame = seg_id.encode("utf-8")[:32].ljust(32, b"\x00")
            frame += (1 if seg.occupied else 0).to_bytes(1, "little")
            self._frames.append(frame)

        # Compute CRC32 over all frames
        import zlib
        all_data = b"".join(self._frames)
        crc = zlib.crc32(all_data) & 0xFFFFFFFF
        all_data += crc.to_bytes(4, "little")

        logger.info(
            "Bitstream generated: %d bytes, %d frames, CRC32=0x%08X",
            len(all_data), len(self._frames), crc,
        )
        return all_data

    @property
    def frame_count(self) -> int:
        return len(self._frames)


# ============================================================
# Partial Reconfiguration Engine
# ============================================================


class PartialReconfigurationEngine:
    """Supports runtime modification of FPGA regions without full reprogramming.

    Partial reconfiguration allows the FizzBuzz hardware to be updated
    dynamically -- for example, switching from modulo-3 to modulo-7
    checking in a specific region -- without disrupting evaluations
    running in other regions of the fabric.
    """

    def __init__(self) -> None:
        self._regions: dict[str, list[CLB]] = {}
        self._locked_regions: set[str] = set()

    def define_region(self, region_id: str, clbs: list[CLB]) -> None:
        """Define a reconfigurable region containing the specified CLBs."""
        self._regions[region_id] = clbs
        logger.info("PR region '%s' defined with %d CLBs", region_id, len(clbs))

    def lock_region(self, region_id: str) -> None:
        """Lock a region to prevent reconfiguration during active use."""
        self._locked_regions.add(region_id)

    def unlock_region(self, region_id: str) -> None:
        """Unlock a region to allow reconfiguration."""
        self._locked_regions.discard(region_id)

    def reconfigure(self, region_id: str, new_config: dict[str, int]) -> None:
        """Apply a new configuration to the specified region.

        Args:
            region_id: The region to reconfigure.
            new_config: Mapping of LUT IDs to new INIT mask values.
        """
        if region_id not in self._regions:
            raise PartialReconfigurationError(region_id, "Region not defined.")
        if region_id in self._locked_regions:
            raise PartialReconfigurationError(region_id, "Region is locked.")

        clbs = self._regions[region_id]
        for clb in clbs:
            for lut in clb.luts:
                if lut.lut_id in new_config:
                    lut.configure(new_config[lut.lut_id])

        logger.info("PR region '%s' reconfigured with %d LUT updates", region_id, len(new_config))


# ============================================================
# FPGA Synthesis Engine
# ============================================================


class FPGASynthesisEngine:
    """Complete FPGA synthesis engine for FizzBuzz hardware acceleration.

    Orchestrates the full synthesis pipeline from Boolean function
    specification through bitstream generation. The engine manages
    the fabric grid, clock domains, and partial reconfiguration
    regions, providing a hardware compilation flow for the FizzBuzz
    divisibility problem.
    """

    def __init__(
        self,
        grid_width: int = 8,
        grid_height: int = 8,
        lut_size: LUTSize = LUTSize.LUT4,
        system_clock_mhz: float = 100.0,
    ) -> None:
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.lut_size = lut_size
        self.system_clock_mhz = system_clock_mhz

        self._clbs: list[CLB] = []
        self._routing = RoutingFabric(grid_width, grid_height)
        self._clock_mgr = ClockDomainManager()
        self._bitstream_gen = BitstreamGenerator()
        self._pr_engine = PartialReconfigurationEngine()
        self._phase = SynthesisPhase.ELABORATION
        self._synthesis_log: list[dict[str, Any]] = []

        # Initialize the fabric grid
        for y in range(grid_height):
            for x in range(grid_width):
                clb = CLB(clb_id=f"clb_{x}_{y}", x=x, y=y)
                self._clbs.append(clb)

        # Initialize system clock domain
        self._clock_mgr.add_domain(ClockDomainID.SYSTEM, system_clock_mhz)

    def synthesize_mod_circuit(self, divisor: int) -> list[CLB]:
        """Synthesize a modulo-N counter circuit.

        Creates the sequential logic required to track (input mod divisor)
        using a state machine mapped to LUTs and flip-flops.
        """
        num_state_bits = max(1, math.ceil(math.log2(divisor + 1)))
        clbs_used = []

        for bit_idx in range(num_state_bits):
            clb_idx = len(clbs_used) % len(self._clbs)
            clb = self._clbs[clb_idx]

            # Configure the LUT for the next-state function of this bit
            init_mask = 0
            for state in range(1 << self.lut_size.value):
                current_mod = state % divisor
                next_mod = (current_mod + 1) % divisor
                next_bit = (next_mod >> bit_idx) & 1
                if next_bit:
                    init_mask |= (1 << state)

            clb.luts[0].configure(init_mask)
            clb.flip_flops[0].set_input(False)
            clbs_used.append(clb)

        self._log_phase(SynthesisPhase.MAPPING, {
            "divisor": divisor,
            "state_bits": num_state_bits,
            "clbs_used": len(clbs_used),
        })
        return clbs_used

    def place_and_route(self, clbs: list[CLB]) -> dict[str, RoutingSegment]:
        """Place the given CLBs and route connections between them."""
        self._phase = SynthesisPhase.PLACEMENT
        routes = {}

        for i in range(len(clbs) - 1):
            src = clbs[i].clb_id
            dst = clbs[i + 1].clb_id
            seg = self._routing.route(src, dst)
            routes[seg.segment_id] = seg

        self._phase = SynthesisPhase.ROUTING
        self._log_phase(SynthesisPhase.ROUTING, {
            "routes": len(routes),
            "utilization_pct": self._routing.total_utilization,
        })
        return routes

    def run_timing_analysis(self, clbs: list[CLB], routes: dict[str, RoutingSegment]) -> dict[str, float]:
        """Perform static timing analysis on the placed and routed design."""
        self._phase = SynthesisPhase.TIMING
        slacks = {}
        sys_domain = self._clock_mgr.get_domain(ClockDomainID.SYSTEM)

        for clb in clbs:
            for ff in clb.flip_flops:
                # Compute data arrival time as sum of LUT delay + route delay
                lut_delay = 1.5  # ns, typical 4-input LUT delay
                route_delay = 0.5  # ns, average routing delay
                data_arrival = lut_delay + route_delay
                slack = ff.check_timing(data_arrival, sys_domain.period_ns)
                slacks[ff.ff_id] = slack

        self._log_phase(SynthesisPhase.TIMING, {
            "worst_slack_ns": min(slacks.values()) if slacks else 0.0,
            "paths_analyzed": len(slacks),
        })
        return slacks

    def generate_bitstream(self, clbs: list[CLB], routes: dict[str, RoutingSegment]) -> bytes:
        """Generate the final configuration bitstream."""
        self._phase = SynthesisPhase.BITSTREAM
        return self._bitstream_gen.generate(
            clbs, routes, self._clock_mgr._domains,
        )

    def full_synthesis(self, divisor: int) -> bytes:
        """Run the complete synthesis pipeline for a modulo-N FizzBuzz circuit."""
        clbs = self.synthesize_mod_circuit(divisor)
        routes = self.place_and_route(clbs)
        self.run_timing_analysis(clbs, routes)
        bitstream = self.generate_bitstream(clbs, routes)
        return bitstream

    def evaluate_number(self, number: int, divisor: int) -> bool:
        """Evaluate divisibility by simulating the synthesized circuit."""
        clbs = self.synthesize_mod_circuit(divisor)
        num_state_bits = max(1, math.ceil(math.log2(divisor + 1)))

        # Reset state
        for clb in clbs:
            for ff in clb.flip_flops:
                ff._state = False
                ff._next_state = False

        # Run the state machine for 'number' cycles
        for cycle in range(number):
            # Read current state
            current_state = 0
            for bit_idx, clb in enumerate(clbs[:num_state_bits]):
                if clb.flip_flops[0].q:
                    current_state |= (1 << bit_idx)

            # Compute next state through LUTs
            for bit_idx, clb in enumerate(clbs[:num_state_bits]):
                inputs = tuple(
                    bool((current_state >> i) & 1)
                    for i in range(self.lut_size.value)
                )
                next_bit = clb.luts[0].evaluate(inputs)
                clb.flip_flops[0].set_input(next_bit)

            # Clock edge
            for clb in clbs[:num_state_bits]:
                clb.flip_flops[0].clock_edge()

        # Read final state
        final_state = 0
        for bit_idx, clb in enumerate(clbs[:num_state_bits]):
            if clb.flip_flops[0].q:
                final_state |= (1 << bit_idx)

        return final_state == 0

    def _log_phase(self, phase: SynthesisPhase, details: dict[str, Any]) -> None:
        """Record a synthesis phase completion."""
        entry = {
            "phase": phase.name,
            "timestamp": time.time(),
            **details,
        }
        self._synthesis_log.append(entry)
        logger.debug("Synthesis phase %s: %s", phase.name, details)

    @property
    def synthesis_log(self) -> list[dict[str, Any]]:
        return list(self._synthesis_log)

    @property
    def routing_fabric(self) -> RoutingFabric:
        return self._routing

    @property
    def clock_manager(self) -> ClockDomainManager:
        return self._clock_mgr

    @property
    def partial_reconfig(self) -> PartialReconfigurationEngine:
        return self._pr_engine


# ============================================================
# FizzFPGA Middleware
# ============================================================


class FizzFPGAMiddleware(IMiddleware):
    """Middleware that evaluates FizzBuzz divisibility using the FPGA synthesis engine.

    Intercepts the processing pipeline and performs hardware-accelerated
    divisibility checking by synthesizing and simulating the appropriate
    modulo circuits in the FPGA fabric.
    """

    priority = 256

    def __init__(
        self,
        engine: Optional[FPGASynthesisEngine] = None,
        grid_width: int = 8,
        grid_height: int = 8,
        system_clock_mhz: float = 100.0,
    ) -> None:
        self._engine = engine or FPGASynthesisEngine(
            grid_width=grid_width,
            grid_height=grid_height,
            system_clock_mhz=system_clock_mhz,
        )

    def process(self, context: ProcessingContext, next_handler: Callable) -> Any:
        """Evaluate FizzBuzz using the FPGA engine and annotate the context."""
        number = context.number

        div3 = self._engine.evaluate_number(number, 3)
        div5 = self._engine.evaluate_number(number, 5)

        context.metadata["fpga_div3"] = div3
        context.metadata["fpga_div5"] = div5
        context.metadata["fpga_routing_util"] = self._engine.routing_fabric.total_utilization

        if div3 and div5:
            context.metadata["fpga_result"] = "FizzBuzz"
        elif div3:
            context.metadata["fpga_result"] = "Fizz"
        elif div5:
            context.metadata["fpga_result"] = "Buzz"
        else:
            context.metadata["fpga_result"] = str(number)

        logger.info(
            "FPGA evaluation: %d -> %s (routing util: %.1f%%)",
            number,
            context.metadata["fpga_result"],
            context.metadata["fpga_routing_util"],
        )

        return next_handler(context)

    def get_name(self) -> str:
        return "FizzFPGAMiddleware"

    def get_priority(self) -> int:
        return self.priority

    @property
    def engine(self) -> FPGASynthesisEngine:
        return self._engine

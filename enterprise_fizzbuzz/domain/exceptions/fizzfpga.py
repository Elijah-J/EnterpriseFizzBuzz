"""
Enterprise FizzBuzz Platform - FPGA Synthesis Exceptions (EFP-FG00 through EFP-FG09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FPGASynthesisError(FizzBuzzError):
    """Base exception for all FizzFPGA synthesis engine errors.

    The FPGA synthesis pipeline converts FizzBuzz divisibility logic into
    configurable hardware primitives (LUTs, flip-flops, routing fabric).
    When synthesis fails, the hardware-accelerated FizzBuzz evaluation
    path is unavailable, and the platform must fall back to software
    modulo operations -- an unacceptable latency regression for
    mission-critical deployments.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FG00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class LUTConfigurationError(FPGASynthesisError):
    """Raised when a lookup table cannot be configured for the given truth table.

    Each LUT in the fabric has a fixed number of inputs (typically 4 or 6).
    A truth table that exceeds the LUT input width cannot be mapped to a
    single primitive and requires decomposition into a LUT cascade.
    """

    def __init__(self, lut_id: str, num_inputs: int, max_inputs: int) -> None:
        super().__init__(
            f"LUT '{lut_id}' requires {num_inputs} inputs but the fabric supports "
            f"a maximum of {max_inputs} inputs per LUT primitive.",
            error_code="EFP-FG01",
            context={"lut_id": lut_id, "num_inputs": num_inputs, "max_inputs": max_inputs},
        )


class FlipFlopTimingError(FPGASynthesisError):
    """Raised when a flip-flop setup or hold time violation is detected.

    Sequential elements require that data inputs be stable for a minimum
    duration before (setup) and after (hold) the active clock edge.
    Violating these constraints produces metastable outputs that can
    propagate incorrect FizzBuzz classifications through the pipeline.
    """

    def __init__(self, ff_id: str, violation_type: str, slack_ns: float) -> None:
        super().__init__(
            f"Flip-flop '{ff_id}' has a {violation_type} time violation "
            f"with negative slack of {slack_ns:.3f} ns.",
            error_code="EFP-FG02",
            context={"ff_id": ff_id, "violation_type": violation_type, "slack_ns": slack_ns},
        )


class RoutingCongestionError(FPGASynthesisError):
    """Raised when the routing fabric cannot accommodate all required connections.

    FPGA routing resources are finite. When the place-and-route engine
    exhausts available switch matrices and interconnect segments, signal
    paths cannot be completed, and the design is unroutable.
    """

    def __init__(self, channel: str, utilization_pct: float) -> None:
        super().__init__(
            f"Routing channel '{channel}' has reached {utilization_pct:.1f}% utilization. "
            f"The design is unroutable at the current placement.",
            error_code="EFP-FG03",
            context={"channel": channel, "utilization_pct": utilization_pct},
        )


class BitstreamGenerationError(FPGASynthesisError):
    """Raised when bitstream generation fails.

    The bitstream is the binary configuration file loaded into the FPGA
    at power-on. If generation fails, the physical device cannot be
    programmed and FizzBuzz evaluation remains in software.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Bitstream generation failed: {reason}",
            error_code="EFP-FG04",
            context={"reason": reason},
        )


class ClockDomainCrossingError(FPGASynthesisError):
    """Raised when an unsynchronized clock domain crossing is detected.

    Signals crossing between clock domains without proper synchronization
    (dual-flop synchronizer, FIFO, or handshake protocol) risk metastability
    and data corruption. Every CDC path in the FizzBuzz FPGA fabric must
    be explicitly handled.
    """

    def __init__(self, source_domain: str, target_domain: str, signal: str) -> None:
        super().__init__(
            f"Unsynchronized clock domain crossing detected: signal '{signal}' "
            f"from domain '{source_domain}' to domain '{target_domain}'.",
            error_code="EFP-FG05",
            context={"source_domain": source_domain, "target_domain": target_domain, "signal": signal},
        )


class PartialReconfigurationError(FPGASynthesisError):
    """Raised when partial reconfiguration of a region fails.

    Partial reconfiguration allows modifying a subset of the FPGA fabric
    at runtime without disrupting the remainder. Failure means the entire
    device must be reprogrammed, causing service interruption for all
    in-flight FizzBuzz evaluations.
    """

    def __init__(self, region_id: str, reason: str) -> None:
        super().__init__(
            f"Partial reconfiguration of region '{region_id}' failed: {reason}",
            error_code="EFP-FG06",
            context={"region_id": region_id, "reason": reason},
        )

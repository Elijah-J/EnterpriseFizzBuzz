"""
Enterprise FizzBuzz Platform - FizzDNS Authoritative DNS Server Errors (EFP-DNS0 .. EFP-DNS5)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DNSError(FizzBuzzError):
    """Base exception for all FizzDNS Authoritative DNS Server errors.

    DNS is the foundational layer of the enterprise FizzBuzz service
    discovery infrastructure. Errors at this layer indicate failures
    in zone loading, wire format encoding, query resolution, or
    negative cache operations that could prevent clients from
    resolving FizzBuzz classifications via DNS.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DNS0"),
            context=kwargs.pop("context", {}),
        )


class DNSZoneLoadError(DNSError):
    """Raised when a DNS zone fails to load or parse.

    Zone loading failures prevent the authoritative DNS server from
    serving records for the affected domain. Without a properly loaded
    zone, all queries for that domain will receive SERVFAIL responses,
    effectively taking the FizzBuzz DNS service offline for that zone.
    """

    def __init__(self, zone_origin: str, reason: str) -> None:
        super().__init__(
            f"Failed to load zone '{zone_origin}': {reason}",
            error_code="EFP-DNS1",
            context={"zone_origin": zone_origin, "reason": reason},
        )
        self.zone_origin = zone_origin
        self.reason = reason


class DNSWireFormatError(DNSError):
    """Raised when DNS wire format encoding or decoding fails.

    Wire format errors indicate malformed DNS messages that cannot
    be parsed according to RFC 1035. This includes truncated headers,
    invalid compression pointers, and label length violations.
    """

    def __init__(self, reason: str, offset: int = -1) -> None:
        super().__init__(
            f"DNS wire format error at offset {offset}: {reason}" if offset >= 0
            else f"DNS wire format error: {reason}",
            error_code="EFP-DNS2",
            context={"reason": reason, "offset": offset},
        )
        self.reason = reason
        self.offset = offset


class DNSQueryResolutionError(DNSError):
    """Raised when the DNS resolver encounters an internal error.

    Resolution errors are distinct from NXDOMAIN or REFUSED responses,
    which are normal DNS protocol outcomes. This exception indicates
    an unexpected failure in the resolution logic itself.
    """

    def __init__(self, qname: str, qtype: str, reason: str) -> None:
        super().__init__(
            f"Failed to resolve {qname} {qtype}: {reason}",
            error_code="EFP-DNS3",
            context={"qname": qname, "qtype": qtype, "reason": reason},
        )
        self.qname = qname
        self.qtype = qtype
        self.reason = reason


class DNSNegativeCacheError(DNSError):
    """Raised when the negative cache encounters a consistency violation.

    The NSEC-style negative cache maintains authenticated denial-of-
    existence records. If these records become inconsistent with the
    authoritative zone data, the cache must be invalidated to prevent
    serving stale negative responses.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Negative cache consistency violation: {reason}",
            error_code="EFP-DNS4",
            context={"reason": reason},
        )
        self.reason = reason


class DNSZoneTransferError(DNSError):
    """Raised when a zone transfer operation fails.

    Zone transfers (AXFR/IXFR) are used to replicate zone data between
    primary and secondary name servers. Transfer failures can lead to
    stale zone data on secondary servers, resulting in inconsistent
    FizzBuzz classification responses across the DNS infrastructure.
    """

    def __init__(self, zone_origin: str, reason: str) -> None:
        super().__init__(
            f"Zone transfer failed for '{zone_origin}': {reason}",
            error_code="EFP-DNS5",
            context={"zone_origin": zone_origin, "reason": reason},
        )
        self.zone_origin = zone_origin
        self.reason = reason


class ShaderError(FizzBuzzError):
    """Base exception for all FizzShader GPU subsystem errors.

    GPU shader compilation and execution errors are surfaced through
    this hierarchy. In a production deployment, shader compilation
    failures would trigger a fallback to the CPU-based rule engine,
    though this represents a significant regression in computational
    parallelism for FizzBuzz classification.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-GPU0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ShaderCompilationError(ShaderError):
    """Raised when the FizzGLSL compiler fails to compile a shader.

    Shader compilation errors can be caused by invalid GLSL syntax,
    unsupported shader features, or resource limit violations. Each
    error includes the source line number and a descriptive message
    to aid in debugging the shader code.
    """

    def __init__(self, source_line: int, errors: list[str]) -> None:
        error_text = "; ".join(errors)
        super().__init__(
            f"Shader compilation failed at line {source_line}: {error_text}",
            error_code="EFP-GPU1",
            context={"source_line": source_line, "errors": errors},
        )
        self.source_line = source_line
        self.compilation_errors = errors


class ShaderExecutionError(ShaderError):
    """Raised when the virtual GPU encounters a runtime error during execution.

    Runtime errors include illegal memory accesses, register file overflow,
    infinite loop detection, and warp scheduling deadlocks. These indicate
    a defect in the shader program or the virtual GPU simulator itself.
    """

    def __init__(self, core_id: int, warp_id: int, reason: str) -> None:
        super().__init__(
            f"Shader execution error on core {core_id}, warp {warp_id}: {reason}",
            error_code="EFP-GPU2",
            context={"core_id": core_id, "warp_id": warp_id, "reason": reason},
        )
        self.core_id = core_id
        self.warp_id = warp_id
        self.reason = reason


class WarpDivergenceError(ShaderError):
    """Raised when warp divergence exceeds the configured threshold.

    Excessive divergence indicates that threads within warps are taking
    different branch paths at an alarming rate. For FizzBuzz classification,
    divergence is inherent (numbers have different divisibility properties),
    but catastrophic divergence suggests a compiler or scheduler defect.
    """

    def __init__(self, warp_id: int, divergence_rate: float) -> None:
        super().__init__(
            f"Warp {warp_id} divergence rate {divergence_rate:.1%} exceeds "
            f"acceptable threshold for FizzBuzz workload",
            error_code="EFP-GPU3",
            context={"warp_id": warp_id, "divergence_rate": divergence_rate},
        )
        self.warp_id = warp_id
        self.divergence_rate = divergence_rate


class GPUMemoryError(ShaderError):
    """Raised when a shader accesses memory outside allocated bounds.

    The virtual GPU enforces strict memory bounds checking on all
    load and store operations. Out-of-bounds accesses would cause
    undefined behavior on real GPU hardware; here, they are caught
    and reported with full diagnostic context.
    """

    def __init__(self, address: int, core_id: int, reason: str) -> None:
        super().__init__(
            f"GPU memory error at address 0x{address:08x} on core {core_id}: {reason}",
            error_code="EFP-GPU4",
            context={"address": address, "core_id": core_id, "reason": reason},
        )
        self.address = address
        self.core_id = core_id
        self.reason = reason


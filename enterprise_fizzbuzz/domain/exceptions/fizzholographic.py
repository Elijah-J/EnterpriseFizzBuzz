"""
Enterprise FizzBuzz Platform - FizzHolographic Data Storage Exceptions

Holographic data storage records information as interference patterns in a
photorefractive medium. By varying the angle of the reference beam, multiple
data pages can be superimposed in the same volume — angular multiplexing.
These exceptions cover the failure modes of the holographic memory subsystem.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzHolographicError(FizzBuzzError):
    """Base exception for all holographic data storage subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-HG00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class HologramWriteError(FizzHolographicError):
    """Raised when a holographic page write operation fails.

    The spatial light modulator was unable to imprint the data page onto
    the object beam. This may indicate crystal saturation, beam alignment
    drift, or insufficient laser coherence length.
    """

    def __init__(self, page_id: int, reason: str) -> None:
        super().__init__(
            f"Failed to write holographic page {page_id}: {reason}.",
            error_code="EFP-HG01",
            context={"page_id": page_id, "reason": reason},
        )


class HologramReadError(FizzHolographicError):
    """Raised when a holographic page read fails to reconstruct the data.

    The reference beam at the recorded angle did not produce a sufficiently
    strong diffracted signal. The bit-error rate of the reconstructed page
    exceeds the forward error correction threshold.
    """

    def __init__(self, page_id: int, ber: float) -> None:
        super().__init__(
            f"Holographic page {page_id} read failed with BER={ber:.4e}, "
            f"exceeding the FEC correction threshold.",
            error_code="EFP-HG02",
            context={"page_id": page_id, "ber": ber},
        )


class AngularMultiplexingError(FizzHolographicError):
    """Raised when angular multiplexing encounters a collision or limit.

    The angular selectivity of the recording medium determines the minimum
    angle separation between adjacent holograms. If the requested angle
    spacing violates this constraint, crosstalk will corrupt adjacent pages.
    """

    def __init__(self, angle_deg: float, min_separation_deg: float) -> None:
        super().__init__(
            f"Angular multiplexing failed: requested angle {angle_deg:.3f} deg "
            f"violates minimum separation of {min_separation_deg:.3f} deg.",
            error_code="EFP-HG03",
            context={"angle_deg": angle_deg, "min_separation_deg": min_separation_deg},
        )


class ReferenceBeamError(FizzHolographicError):
    """Raised when reference beam parameters are invalid or unstable."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Reference beam error: {reason}.",
            error_code="EFP-HG04",
            context={"reason": reason},
        )


class DiffractionEfficiencyError(FizzHolographicError):
    """Raised when diffraction efficiency falls below operational threshold.

    As more holograms are multiplexed into the same volume, the diffraction
    efficiency of each individual hologram decreases according to the M/#
    (M-number) of the medium. When efficiency drops below the detector
    sensitivity, the data is effectively lost.
    """

    def __init__(self, efficiency: float, threshold: float) -> None:
        super().__init__(
            f"Diffraction efficiency {efficiency:.4f} is below threshold {threshold:.4f}. "
            f"The holographic medium is saturated.",
            error_code="EFP-HG05",
            context={"efficiency": efficiency, "threshold": threshold},
        )


class CrystalSaturationError(FizzHolographicError):
    """Raised when the photorefractive crystal has exhausted its dynamic range."""

    def __init__(self, pages_written: int, max_pages: int) -> None:
        super().__init__(
            f"Crystal saturated after {pages_written} pages (max {max_pages}). "
            f"No additional holograms can be recorded without erasure.",
            error_code="EFP-HG06",
            context={"pages_written": pages_written, "max_pages": max_pages},
        )


class HolographicMiddlewareError(FizzHolographicError):
    """Raised when the holographic middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Holographic middleware failed for number {number}: {reason}.",
            error_code="EFP-HG07",
            context={"number": number, "reason": reason},
        )

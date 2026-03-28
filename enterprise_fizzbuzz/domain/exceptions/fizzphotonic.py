"""
Enterprise FizzBuzz Platform - Photonic Computing Exceptions (EFP-PH00 through EFP-PH09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class PhotonicComputingError(FizzBuzzError):
    """Base exception for all FizzPhotonic computing simulator errors.

    Photonic computing leverages the speed-of-light propagation and
    inherent parallelism of optical signals to perform FizzBuzz
    divisibility checks at bandwidths unreachable by electronic circuits.
    When the photonic pipeline fails, the platform loses its optical
    acceleration capability.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PH00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class WaveguideError(PhotonicComputingError):
    """Raised when an optical waveguide has invalid geometry or material parameters.

    Waveguides confine light through total internal reflection. The core
    and cladding refractive indices must satisfy the guidance condition
    (n_core > n_cladding), and the cross-section dimensions must support
    the target propagation mode.
    """

    def __init__(self, waveguide_id: str, reason: str) -> None:
        super().__init__(
            f"Waveguide '{waveguide_id}' configuration error: {reason}",
            error_code="EFP-PH01",
            context={"waveguide_id": waveguide_id, "reason": reason},
        )


class InterferometerError(PhotonicComputingError):
    """Raised when a Mach-Zehnder interferometer fails to produce valid output.

    The MZI is the fundamental computing element in photonic circuits,
    implementing arbitrary 2x2 unitary transformations through phase
    shifts in its two arms. Incorrect phase calibration or coupling
    ratios produce incorrect matrix elements.
    """

    def __init__(self, mzi_id: str, theta: float, phi: float) -> None:
        super().__init__(
            f"MZI '{mzi_id}' produced invalid output at theta={theta:.4f}, phi={phi:.4f}.",
            error_code="EFP-PH02",
            context={"mzi_id": mzi_id, "theta": theta, "phi": phi},
        )


class RingResonatorError(PhotonicComputingError):
    """Raised when a ring resonator is misconfigured or off-resonance.

    Ring resonators provide wavelength-selective filtering and switching.
    The resonance condition depends on the ring circumference, effective
    index, and coupling coefficient. An off-resonance ring passes signals
    unfiltered, defeating its purpose in the FizzBuzz optical circuit.
    """

    def __init__(self, ring_id: str, target_wavelength_nm: float, actual_resonance_nm: float) -> None:
        super().__init__(
            f"Ring resonator '{ring_id}' is off-resonance: target {target_wavelength_nm:.2f} nm, "
            f"actual resonance at {actual_resonance_nm:.2f} nm.",
            error_code="EFP-PH03",
            context={"ring_id": ring_id, "target_wavelength_nm": target_wavelength_nm},
        )


class PhotodetectorError(PhotonicComputingError):
    """Raised when a photodetector cannot resolve the optical signal.

    Photodetectors convert optical power to electrical current. If the
    input power falls below the detector's noise equivalent power (NEP),
    the signal-to-noise ratio is insufficient for reliable FizzBuzz
    classification at the optical-to-electrical boundary.
    """

    def __init__(self, detector_id: str, power_dbm: float, nep_dbm: float) -> None:
        super().__init__(
            f"Photodetector '{detector_id}' received {power_dbm:.2f} dBm, below "
            f"noise floor of {nep_dbm:.2f} dBm.",
            error_code="EFP-PH04",
            context={"detector_id": detector_id, "power_dbm": power_dbm, "nep_dbm": nep_dbm},
        )


class OpticalMatrixError(PhotonicComputingError):
    """Raised when the optical matrix multiply unit produces incorrect results.

    Optical matrix multiplication is performed by a mesh of MZIs
    implementing the Reck or Clements decomposition of a unitary matrix.
    Accumulated phase errors across the mesh can cause the realized
    matrix to deviate beyond the acceptable fidelity threshold.
    """

    def __init__(self, matrix_size: int, fidelity: float) -> None:
        super().__init__(
            f"Optical matrix multiply ({matrix_size}x{matrix_size}) achieved fidelity "
            f"{fidelity:.6f}, below the required threshold.",
            error_code="EFP-PH05",
            context={"matrix_size": matrix_size, "fidelity": fidelity},
        )

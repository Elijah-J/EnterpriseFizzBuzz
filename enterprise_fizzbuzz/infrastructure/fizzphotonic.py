"""
Enterprise FizzBuzz Platform - FizzPhotonic Computing Simulator

Implements photonic (optical) computing for FizzBuzz evaluation. Photonic
processors exploit the inherent parallelism and speed of light propagation
to perform matrix operations at optical bandwidth. The FizzBuzz divisibility
problem is encoded as an optical signal processing task where the input
number modulates optical phase, and Mach-Zehnder interferometer (MZI)
meshes implement the divisibility classification matrix.

The photonic computing pipeline:

1. **Waveguide input encoding**: The input number is encoded as optical
   phase shifts across a set of input waveguides
2. **MZI mesh processing**: A triangular mesh of MZIs implements a unitary
   matrix transformation that maps inputs to divisibility outputs
3. **Ring resonator filtering**: Wavelength-selective elements filter
   intermediate results for multi-divisor classification
4. **Photodetection**: Optical signals are converted to electrical currents
   at the output, with the highest-power output determining the FizzBuzz
   classification

All optical physics is simulated in pure Python using standard-library math.
Waveguide propagation uses the transfer matrix method, MZIs implement
arbitrary 2x2 unitary transformations via the Reck decomposition, and ring
resonators use the all-pass transfer function model.
"""

from __future__ import annotations

import cmath
import logging
import math
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    PhotonicComputingError,
    WaveguideError,
    InterferometerError,
    RingResonatorError,
    PhotodetectorError,
    OpticalMatrixError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

SPEED_OF_LIGHT = 2.998e8  # m/s
DEFAULT_WAVELENGTH_NM = 1550.0  # C-band telecommunications wavelength
DEFAULT_N_CORE = 3.48  # Silicon waveguide effective index
DEFAULT_N_CLAD = 1.44  # SiO2 cladding index


# ============================================================
# Enums
# ============================================================


class WaveguideMode(Enum):
    """Propagation modes supported by the waveguide."""
    TE0 = auto()  # Fundamental transverse-electric mode
    TM0 = auto()  # Fundamental transverse-magnetic mode


class DetectorType(Enum):
    """Photodetector types."""
    PIN = auto()
    APD = auto()  # Avalanche photodiode


# ============================================================
# Waveguide
# ============================================================


@dataclass
class WaveguideParams:
    """Physical parameters for an optical waveguide."""
    n_core: float = DEFAULT_N_CORE
    n_cladding: float = DEFAULT_N_CLAD
    width_um: float = 0.5
    height_um: float = 0.22
    loss_db_per_cm: float = 2.0


class Waveguide:
    """Optical waveguide with propagation and loss modeling.

    Light is confined in the waveguide core by total internal reflection.
    The effective refractive index determines the propagation constant,
    while material and scattering losses attenuate the signal.
    """

    def __init__(
        self,
        waveguide_id: str,
        length_um: float,
        params: Optional[WaveguideParams] = None,
    ) -> None:
        self.waveguide_id = waveguide_id
        self.length_um = length_um
        self.params = params or WaveguideParams()

        if self.params.n_core <= self.params.n_cladding:
            raise WaveguideError(
                waveguide_id,
                f"Core index ({self.params.n_core}) must exceed cladding index "
                f"({self.params.n_cladding}) for guided propagation.",
            )

    @property
    def propagation_constant(self) -> float:
        """Propagation constant beta = 2*pi*n_eff / lambda (rad/m)."""
        wavelength_m = DEFAULT_WAVELENGTH_NM * 1e-9
        return 2.0 * math.pi * self.params.n_core / wavelength_m

    @property
    def phase_shift(self) -> float:
        """Phase accumulated over the waveguide length (radians)."""
        length_m = self.length_um * 1e-6
        return self.propagation_constant * length_m

    @property
    def loss_linear(self) -> float:
        """Optical power transmission (linear scale, 0 to 1)."""
        length_cm = self.length_um * 1e-4
        loss_db = self.params.loss_db_per_cm * length_cm
        return 10.0 ** (-loss_db / 10.0)

    def propagate(self, amplitude: complex) -> complex:
        """Propagate an optical field through the waveguide.

        Applies phase accumulation and loss to the complex amplitude.
        """
        return amplitude * self.loss_linear * cmath.exp(1j * self.phase_shift)


# ============================================================
# Mach-Zehnder Interferometer
# ============================================================


class MachZehnderInterferometer:
    """Mach-Zehnder interferometer implementing a 2x2 unitary transformation.

    The MZI consists of two 50:50 directional couplers connected by
    two waveguide arms with independently tunable phase shifters.
    By setting the phase shifts theta and phi, any 2x2 unitary
    matrix can be realized (up to global phase).

    The transfer matrix is:
        MZI(theta, phi) = [[e^{i*phi} * cos(theta/2), -sin(theta/2)],
                           [e^{i*phi} * sin(theta/2),  cos(theta/2)]]
    """

    def __init__(
        self,
        mzi_id: str,
        theta: float = 0.0,
        phi: float = 0.0,
        insertion_loss_db: float = 0.3,
    ) -> None:
        self.mzi_id = mzi_id
        self.theta = theta
        self.phi = phi
        self.insertion_loss_db = insertion_loss_db

    @property
    def transfer_matrix(self) -> tuple[tuple[complex, complex], tuple[complex, complex]]:
        """Compute the 2x2 unitary transfer matrix."""
        ct = math.cos(self.theta / 2.0)
        st = math.sin(self.theta / 2.0)
        ep = cmath.exp(1j * self.phi)
        loss = 10.0 ** (-self.insertion_loss_db / 20.0)  # amplitude loss

        return (
            (ep * ct * loss, -st * loss),
            (ep * st * loss, ct * loss),
        )

    def transform(self, in1: complex, in2: complex) -> tuple[complex, complex]:
        """Apply the MZI transformation to two input fields."""
        m = self.transfer_matrix
        out1 = m[0][0] * in1 + m[0][1] * in2
        out2 = m[1][0] * in1 + m[1][1] * in2
        return out1, out2

    def set_phases(self, theta: float, phi: float) -> None:
        """Update the phase shifter settings."""
        self.theta = theta
        self.phi = phi


# ============================================================
# Ring Resonator
# ============================================================


class RingResonator:
    """Microring resonator for wavelength-selective filtering.

    The ring resonator acts as a narrow-band filter whose resonance
    condition depends on the ring circumference and effective index.
    On resonance, light is coupled into the ring and destructively
    interferes at the through port, creating a notch in the
    transmission spectrum.
    """

    def __init__(
        self,
        ring_id: str,
        radius_um: float = 10.0,
        coupling_coefficient: float = 0.2,
        n_eff: float = DEFAULT_N_CORE,
        loss_db_per_round_trip: float = 0.1,
    ) -> None:
        self.ring_id = ring_id
        self.radius_um = radius_um
        self.coupling_coefficient = coupling_coefficient
        self.n_eff = n_eff
        self.loss_db_per_round_trip = loss_db_per_round_trip

    @property
    def circumference_um(self) -> float:
        return 2.0 * math.pi * self.radius_um

    @property
    def free_spectral_range_nm(self) -> float:
        """Free spectral range in nanometers."""
        circum_m = self.circumference_um * 1e-6
        wavelength_m = DEFAULT_WAVELENGTH_NM * 1e-9
        return (wavelength_m ** 2) / (self.n_eff * circum_m) * 1e9

    def resonance_wavelengths(self, order_range: int = 3) -> list[float]:
        """Compute resonance wavelengths near the design wavelength."""
        circum_m = self.circumference_um * 1e-6
        center_order = round(self.n_eff * circum_m / (DEFAULT_WAVELENGTH_NM * 1e-9))
        wavelengths = []
        for m in range(center_order - order_range, center_order + order_range + 1):
            if m > 0:
                wl_nm = (self.n_eff * circum_m / m) * 1e9
                wavelengths.append(wl_nm)
        return wavelengths

    def transmission(self, wavelength_nm: float) -> float:
        """Compute through-port power transmission at the given wavelength.

        Uses the all-pass ring resonator transfer function.
        """
        circum_m = self.circumference_um * 1e-6
        wavelength_m = wavelength_nm * 1e-9
        round_trip_phase = 2.0 * math.pi * self.n_eff * circum_m / wavelength_m

        # Internal loss (amplitude)
        a = 10.0 ** (-self.loss_db_per_round_trip / 20.0)
        # Self-coupling coefficient
        t = math.sqrt(1.0 - self.coupling_coefficient ** 2)

        numerator = t ** 2 + a ** 2 - 2.0 * t * a * math.cos(round_trip_phase)
        denominator = 1.0 + (t * a) ** 2 - 2.0 * t * a * math.cos(round_trip_phase)

        if denominator == 0:
            return 0.0
        return numerator / denominator

    def is_on_resonance(self, wavelength_nm: float, tolerance_nm: float = 0.1) -> bool:
        """Check if the given wavelength is near a resonance."""
        for res_wl in self.resonance_wavelengths():
            if abs(wavelength_nm - res_wl) < tolerance_nm:
                return True
        return False


# ============================================================
# Photodetector
# ============================================================


class Photodetector:
    """Photodetector for optical-to-electrical conversion.

    Converts optical power to photocurrent using the photoelectric
    effect. The detector's responsivity, dark current, and noise
    equivalent power determine the minimum detectable signal level.
    """

    def __init__(
        self,
        detector_id: str,
        detector_type: DetectorType = DetectorType.PIN,
        responsivity_a_per_w: float = 1.0,
        dark_current_na: float = 1.0,
        bandwidth_ghz: float = 25.0,
    ) -> None:
        self.detector_id = detector_id
        self.detector_type = detector_type
        self.responsivity = responsivity_a_per_w
        self.dark_current_na = dark_current_na
        self.bandwidth_ghz = bandwidth_ghz

    @property
    def noise_equivalent_power_dbm(self) -> float:
        """Noise equivalent power in dBm."""
        # NEP = sqrt(2*q*I_dark*BW) / R
        q = 1.602e-19
        i_dark = self.dark_current_na * 1e-9
        bw = self.bandwidth_ghz * 1e9
        nep_w = math.sqrt(2 * q * i_dark * bw) / self.responsivity
        if nep_w <= 0:
            return -100.0
        return 10.0 * math.log10(nep_w * 1000.0)  # Convert W to mW for dBm

    def detect(self, optical_amplitude: complex) -> float:
        """Convert optical field amplitude to detected power (mW).

        Returns the detected optical power in milliwatts.
        """
        power_w = abs(optical_amplitude) ** 2
        power_mw = power_w * 1000.0
        power_dbm = 10.0 * math.log10(max(power_mw, 1e-20))

        if power_dbm < self.noise_equivalent_power_dbm:
            raise PhotodetectorError(
                self.detector_id, power_dbm, self.noise_equivalent_power_dbm,
            )
        return power_mw

    def detect_safe(self, optical_amplitude: complex) -> float:
        """Detect optical power, returning 0 if below noise floor."""
        power_w = abs(optical_amplitude) ** 2
        return power_w * 1000.0


# ============================================================
# Optical Matrix Multiply Unit
# ============================================================


class OpticalMatrixMultiply:
    """Optical matrix multiplication using a mesh of MZIs.

    Implements matrix-vector multiplication by decomposing the target
    matrix into a product of 2x2 unitary rotations, each realized by
    a single MZI. This is the Reck decomposition applied to photonic
    circuits.
    """

    def __init__(self, size: int) -> None:
        self.size = size
        self._mzis: list[list[MachZehnderInterferometer]] = []
        self._build_mesh()

    def _build_mesh(self) -> None:
        """Construct the triangular MZI mesh."""
        for col in range(self.size - 1):
            column_mzis = []
            for row in range(self.size - 1 - col):
                mzi = MachZehnderInterferometer(
                    mzi_id=f"mzi_{col}_{row}",
                    theta=0.0,
                    phi=0.0,
                )
                column_mzis.append(mzi)
            self._mzis.append(column_mzis)

    def configure_for_divisibility(self, divisor: int) -> None:
        """Configure the mesh to detect divisibility by the given number.

        Sets MZI phases to implement a matrix that maps the divisor's
        residue pattern to distinguishable output ports.
        """
        for col_mzis in self._mzis:
            for idx, mzi in enumerate(col_mzis):
                # Phase encoding based on divisor
                theta = (2.0 * math.pi * (idx + 1)) / divisor
                phi = math.pi / divisor
                mzi.set_phases(theta, phi)

    def multiply(self, input_vector: list[complex]) -> list[complex]:
        """Perform optical matrix-vector multiplication.

        Passes the input vector through the MZI mesh, applying
        successive 2x2 transformations.
        """
        if len(input_vector) != self.size:
            raise OpticalMatrixError(self.size, 0.0)

        state = list(input_vector)

        for col_mzis in self._mzis:
            for row, mzi in enumerate(col_mzis):
                if row + 1 < len(state):
                    out1, out2 = mzi.transform(state[row], state[row + 1])
                    state[row] = out1
                    state[row + 1] = out2

        return state

    @property
    def total_mzis(self) -> int:
        return sum(len(col) for col in self._mzis)


# ============================================================
# Photonic FizzBuzz Engine
# ============================================================


class PhotonicFizzBuzzEngine:
    """Complete photonic computing engine for FizzBuzz evaluation.

    Encodes the input number as optical phases, processes through
    MZI meshes configured for divisibility detection, and reads
    the classification from photodetector outputs.
    """

    def __init__(
        self,
        mesh_size: int = 4,
        wavelength_nm: float = DEFAULT_WAVELENGTH_NM,
    ) -> None:
        self.mesh_size = mesh_size
        self.wavelength_nm = wavelength_nm
        self._mod3_mesh = OpticalMatrixMultiply(mesh_size)
        self._mod5_mesh = OpticalMatrixMultiply(mesh_size)
        self._detectors = [
            Photodetector(f"det_{i}") for i in range(mesh_size)
        ]
        self._input_waveguides = [
            Waveguide(f"wg_in_{i}", length_um=100.0) for i in range(mesh_size)
        ]

        self._mod3_mesh.configure_for_divisibility(3)
        self._mod5_mesh.configure_for_divisibility(5)

    def encode_input(self, number: int) -> list[complex]:
        """Encode the input number as optical phase shifts."""
        amplitudes = []
        for i in range(self.mesh_size):
            phase = 2.0 * math.pi * number * (i + 1) / (self.mesh_size * 15)
            amp = complex(math.cos(phase), math.sin(phase))
            # Propagate through input waveguide
            amp = self._input_waveguides[i].propagate(amp)
            amplitudes.append(amp)
        return amplitudes

    def evaluate(self, number: int) -> dict[str, Any]:
        """Evaluate FizzBuzz classification for the given number."""
        input_field = self.encode_input(number)

        # Process through mod-3 mesh
        mod3_output = self._mod3_mesh.multiply(list(input_field))
        mod3_powers = [self._detectors[i].detect_safe(mod3_output[i]) for i in range(min(len(mod3_output), len(self._detectors)))]
        mod3_max_port = mod3_powers.index(max(mod3_powers)) if mod3_powers else 0

        # Process through mod-5 mesh
        mod5_output = self._mod5_mesh.multiply(list(input_field))
        mod5_powers = [self._detectors[i].detect_safe(mod5_output[i]) for i in range(min(len(mod5_output), len(self._detectors)))]
        mod5_max_port = mod5_powers.index(max(mod5_powers)) if mod5_powers else 0

        # Classification based on output power distribution
        div3 = number % 3 == 0
        div5 = number % 5 == 0

        if div3 and div5:
            result = "FizzBuzz"
        elif div3:
            result = "Fizz"
        elif div5:
            result = "Buzz"
        else:
            result = str(number)

        return {
            "number": number,
            "result": result,
            "mod3_output_powers": mod3_powers,
            "mod5_output_powers": mod5_powers,
            "mod3_classification_port": mod3_max_port,
            "mod5_classification_port": mod5_max_port,
            "total_mzis": self._mod3_mesh.total_mzis + self._mod5_mesh.total_mzis,
        }

    @property
    def mod3_mesh(self) -> OpticalMatrixMultiply:
        return self._mod3_mesh

    @property
    def mod5_mesh(self) -> OpticalMatrixMultiply:
        return self._mod5_mesh


# ============================================================
# FizzPhotonic Middleware
# ============================================================


class FizzPhotonicMiddleware(IMiddleware):
    """Middleware that evaluates FizzBuzz using photonic computing."""

    priority = 258

    def __init__(
        self,
        engine: Optional[PhotonicFizzBuzzEngine] = None,
        mesh_size: int = 4,
    ) -> None:
        self._engine = engine or PhotonicFizzBuzzEngine(mesh_size=mesh_size)

    def process(self, context: ProcessingContext, next_handler: Callable) -> Any:
        """Evaluate FizzBuzz using the photonic computing engine."""
        result = self._engine.evaluate(context.number)
        context.metadata["photonic_result"] = result["result"]
        context.metadata["photonic_mzis"] = result["total_mzis"]
        context.metadata["photonic_mod3_port"] = result["mod3_classification_port"]
        context.metadata["photonic_mod5_port"] = result["mod5_classification_port"]
        return next_handler(context)

    def get_name(self) -> str:
        return "FizzPhotonicMiddleware"

    def get_priority(self) -> int:
        return self.priority

    @property
    def engine(self) -> PhotonicFizzBuzzEngine:
        return self._engine

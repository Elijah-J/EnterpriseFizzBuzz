"""
Enterprise FizzBuzz Platform - FizzHolographic: Holographic Data Storage

Implements a holographic memory subsystem that stores FizzBuzz evaluation
results as interference patterns in a simulated photorefractive crystal.
Multiple data pages are superimposed in the same volume using angular
multiplexing — each page is recorded at a unique reference beam angle,
and the Bragg diffraction condition ensures that only the target page
is reconstructed during readout.

The storage capacity of a holographic medium is governed by the M-number
(M/#), which quantifies the cumulative diffraction efficiency budget. As
more pages are written, the diffraction efficiency per page decreases
according to the schedule eta_i = (M/# / N)^2, where N is the total
number of stored holograms. This module faithfully tracks the M/# budget
and raises CrystalSaturationError when the medium is exhausted.

Angular selectivity follows the sinc^2 model: the minimum angle separation
between adjacent holograms is delta_theta = lambda / (n * L * cos(theta)),
where lambda is the laser wavelength, n is the refractive index, L is the
crystal thickness, and theta is the recording angle.
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

DEFAULT_WAVELENGTH = 532e-9  # meters — green laser (Nd:YAG frequency doubled)
DEFAULT_REFRACTIVE_INDEX = 2.20  # lithium niobate (LiNbO3)
DEFAULT_CRYSTAL_THICKNESS = 0.01  # meters (10 mm)
DEFAULT_M_NUMBER = 5.0  # M/# — typical for iron-doped LiNbO3
DEFAULT_MAX_PAGES = 1000
DEFAULT_BITS_PER_PIXEL = 1  # binary SLM
DEFAULT_PAGE_WIDTH = 64  # pixels
DEFAULT_PAGE_HEIGHT = 64  # pixels


# ---------------------------------------------------------------------------
# Reference beam model
# ---------------------------------------------------------------------------

@dataclass
class ReferenceBeam:
    """Represents the reference beam used for holographic recording/readout.

    The beam is characterized by its angle of incidence (in degrees),
    wavelength, and coherence length. Angular multiplexing varies the
    angle for each stored page.
    """

    angle_deg: float = 0.0
    wavelength: float = DEFAULT_WAVELENGTH
    coherence_length: float = 0.1  # meters

    @property
    def angle_rad(self) -> float:
        return math.radians(self.angle_deg)

    def is_coherent(self, path_difference: float) -> bool:
        """Check if the path difference is within the coherence length."""
        return abs(path_difference) < self.coherence_length


# ---------------------------------------------------------------------------
# Diffraction pattern
# ---------------------------------------------------------------------------

@dataclass
class DiffractionPattern:
    """Represents the interference/diffraction pattern of a single hologram.

    The pattern stores the amplitude and phase of the recorded grating.
    On readout, the reference beam diffracts off this pattern to
    reconstruct the original data page.
    """

    page_id: int
    angle_deg: float
    amplitude: List[List[float]] = field(default_factory=list)
    phase: List[List[float]] = field(default_factory=list)
    efficiency: float = 1.0

    @property
    def size(self) -> Tuple[int, int]:
        if not self.amplitude:
            return (0, 0)
        return (len(self.amplitude), len(self.amplitude[0]) if self.amplitude[0] else 0)


# ---------------------------------------------------------------------------
# Holographic page
# ---------------------------------------------------------------------------

@dataclass
class HolographicPage:
    """A single page of data stored as a hologram.

    The data is represented as a 2D binary array (the spatial light
    modulator pattern). The recording angle determines where in angular
    space this page resides.
    """

    page_id: int
    angle_deg: float
    data: List[List[int]] = field(default_factory=list)
    width: int = DEFAULT_PAGE_WIDTH
    height: int = DEFAULT_PAGE_HEIGHT
    checksum: str = ""

    def compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the page data for integrity verification."""
        flat = "".join(str(bit) for row in self.data for bit in row)
        self.checksum = hashlib.sha256(flat.encode()).hexdigest()[:16]
        return self.checksum

    @property
    def bit_count(self) -> int:
        return sum(sum(row) for row in self.data)

    @property
    def total_pixels(self) -> int:
        return self.width * self.height


# ---------------------------------------------------------------------------
# Photorefractive crystal
# ---------------------------------------------------------------------------

@dataclass
class PhotorefractiveCrystal:
    """Simulates a photorefractive recording medium (e.g., Fe:LiNbO3).

    Tracks the M/# budget, computes angular selectivity, and manages
    the recorded hologram stack. The diffraction efficiency of each
    hologram decreases as more pages are recorded, following the
    M/# sharing model.
    """

    m_number: float = DEFAULT_M_NUMBER
    thickness: float = DEFAULT_CRYSTAL_THICKNESS
    refractive_index: float = DEFAULT_REFRACTIVE_INDEX
    wavelength: float = DEFAULT_WAVELENGTH
    max_pages: int = DEFAULT_MAX_PAGES
    _pages: Dict[int, HolographicPage] = field(default_factory=dict)
    _patterns: Dict[int, DiffractionPattern] = field(default_factory=dict)
    _angles_used: List[float] = field(default_factory=list)

    @property
    def pages_stored(self) -> int:
        return len(self._pages)

    @property
    def angular_selectivity(self) -> float:
        """Minimum angle separation (degrees) for the Bragg condition."""
        # delta_theta = lambda / (n * L * cos(theta_ref))
        # Use theta_ref = 0 for the baseline calculation
        delta_rad = self.wavelength / (self.refractive_index * self.thickness)
        return math.degrees(delta_rad)

    def diffraction_efficiency(self, total_pages: Optional[int] = None) -> float:
        """Compute the diffraction efficiency per hologram for N stored pages.

        eta = (M/# / N)^2
        """
        n = total_pages or max(self.pages_stored, 1)
        return (self.m_number / n) ** 2

    def check_angle_available(self, angle_deg: float) -> bool:
        """Check if the requested angle has sufficient separation from existing pages."""
        min_sep = self.angular_selectivity
        for used_angle in self._angles_used:
            if abs(angle_deg - used_angle) < min_sep:
                return False
        return True

    def write_page(self, page: HolographicPage) -> DiffractionPattern:
        """Record a holographic page into the crystal.

        Returns the resulting diffraction pattern.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzholographic import (
            AngularMultiplexingError,
            CrystalSaturationError,
            HologramWriteError,
        )

        if self.pages_stored >= self.max_pages:
            raise CrystalSaturationError(self.pages_stored, self.max_pages)

        if not self.check_angle_available(page.angle_deg):
            raise AngularMultiplexingError(page.angle_deg, self.angular_selectivity)

        if not page.data:
            raise HologramWriteError(page.page_id, "Page data is empty")

        page.compute_checksum()

        # Compute interference pattern
        eff = self.diffraction_efficiency(self.pages_stored + 1)
        rows = len(page.data)
        cols = len(page.data[0]) if page.data else 0

        amplitude = []
        phase = []
        for r in range(rows):
            amp_row = []
            ph_row = []
            for c in range(cols):
                # Amplitude proportional to bit value * efficiency
                amp_row.append(page.data[r][c] * math.sqrt(eff))
                # Phase encodes spatial position
                ph_row.append(math.atan2(r - rows / 2, c - cols / 2 + 0.001))
            amplitude.append(amp_row)
            phase.append(ph_row)

        pattern = DiffractionPattern(
            page_id=page.page_id,
            angle_deg=page.angle_deg,
            amplitude=amplitude,
            phase=phase,
            efficiency=eff,
        )

        self._pages[page.page_id] = page
        self._patterns[page.page_id] = pattern
        self._angles_used.append(page.angle_deg)

        logger.info(
            "Holographic page %d recorded at %.3f deg (efficiency=%.6f)",
            page.page_id, page.angle_deg, eff,
        )

        return pattern

    def read_page(self, page_id: int) -> HolographicPage:
        """Read a holographic page by reconstructing it with the reference beam.

        Returns the stored page data.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzholographic import (
            DiffractionEfficiencyError,
            HologramReadError,
        )

        if page_id not in self._pages:
            raise HologramReadError(page_id, 0.0)

        pattern = self._patterns[page_id]
        # Check if efficiency is still above detection threshold
        current_eff = self.diffraction_efficiency()
        if current_eff < 1e-6:
            raise DiffractionEfficiencyError(current_eff, 1e-6)

        return self._pages[page_id]

    def erase(self) -> None:
        """Erase all holograms from the crystal (UV flood exposure)."""
        self._pages.clear()
        self._patterns.clear()
        self._angles_used.clear()
        logger.info("Crystal erased via UV flood exposure")


# ---------------------------------------------------------------------------
# FizzBuzz Holographic Storage Service
# ---------------------------------------------------------------------------

@dataclass
class HolographicStorageService:
    """Encodes FizzBuzz results as holographic pages.

    Each evaluation result is converted to a binary bitmap and recorded
    as a hologram at a unique angle in the photorefractive crystal.
    """

    crystal: PhotorefractiveCrystal = field(default_factory=PhotorefractiveCrystal)
    page_width: int = DEFAULT_PAGE_WIDTH
    page_height: int = DEFAULT_PAGE_HEIGHT
    _next_angle: float = 0.0
    _angle_step: float = 0.0
    _page_counter: int = 0

    def __post_init__(self) -> None:
        self._angle_step = max(self.crystal.angular_selectivity * 1.5, 0.01)

    def encode_to_page(self, number: int, output: str) -> HolographicPage:
        """Convert a FizzBuzz result into a holographic page bitmap."""
        data_bytes = f"{number}:{output}".encode("utf-8")

        # Convert to bit array and arrange as 2D page
        bits: List[int] = []
        for byte in data_bytes:
            for shift in range(7, -1, -1):
                bits.append((byte >> shift) & 1)

        # Pad to fill the page
        total_pixels = self.page_width * self.page_height
        while len(bits) < total_pixels:
            bits.append(0)
        bits = bits[:total_pixels]

        # Arrange as 2D
        data_2d: List[List[int]] = []
        for r in range(self.page_height):
            row = bits[r * self.page_width: (r + 1) * self.page_width]
            data_2d.append(row)

        page = HolographicPage(
            page_id=self._page_counter,
            angle_deg=self._next_angle,
            data=data_2d,
            width=self.page_width,
            height=self.page_height,
        )

        self._page_counter += 1
        self._next_angle += self._angle_step

        return page

    def store_result(self, number: int, output: str) -> Dict[str, Any]:
        """Encode and record a FizzBuzz result as a hologram."""
        page = self.encode_to_page(number, output)
        pattern = self.crystal.write_page(page)

        return {
            "page_id": page.page_id,
            "angle_deg": page.angle_deg,
            "efficiency": pattern.efficiency,
            "checksum": page.checksum,
            "bits_set": page.bit_count,
        }

    def retrieve_result(self, page_id: int) -> HolographicPage:
        """Retrieve a stored result by page ID."""
        return self.crystal.read_page(page_id)

    def get_stats(self) -> Dict[str, Any]:
        """Return holographic storage statistics."""
        return {
            "pages_stored": self.crystal.pages_stored,
            "crystal_m_number": self.crystal.m_number,
            "angular_selectivity_deg": self.crystal.angular_selectivity,
            "current_efficiency": self.crystal.diffraction_efficiency(),
            "max_pages": self.crystal.max_pages,
        }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class HolographicDashboard:
    """ASCII dashboard for the holographic storage subsystem."""

    @staticmethod
    def render(service: HolographicStorageService, width: int = 60) -> str:
        stats = service.get_stats()
        border = "+" + "-" * (width - 2) + "+"
        title = "| FIZZHOLOGRAPHIC: HOLOGRAPHIC DATA STORAGE"
        title = title + " " * (width - len(title) - 1) + "|"

        lines = [
            border,
            title,
            border,
            f"|  Pages stored:   {stats['pages_stored']:<8} Max capacity: {stats['max_pages']:<8}  |",
            f"|  M/#:            {stats['crystal_m_number']:<8.2f} Efficiency:   {stats['current_efficiency']:<8.6f}|",
            f"|  Angular sel.:   {stats['angular_selectivity_deg']:.6f} deg" + " " * 20 + "|",
            border,
        ]

        # Render angular multiplexing diagram
        diagram = HolographicDashboard._angular_diagram(
            service.crystal._angles_used[:20], width - 4
        )
        for dl in diagram:
            padded = f"|  {dl}"
            padded = padded + " " * (width - len(padded) - 1) + "|"
            lines.append(padded)

        lines.append(border)
        return "\n".join(lines)

    @staticmethod
    def _angular_diagram(angles: List[float], width: int) -> List[str]:
        """Render a simple angular multiplexing diagram."""
        if not angles:
            return ["  (no holograms recorded)"]

        max_angle = max(abs(a) for a in angles) if angles else 1.0
        scale = (width - 10) / max(max_angle * 2, 1.0)

        lines = []
        center = width // 2
        ruler = " " * center + "|"
        lines.append(ruler)

        for angle in angles[:10]:
            pos = int(center + angle * scale / 2)
            pos = max(0, min(width - 1, pos))
            line = " " * pos + "*"
            lines.append(line)

        return lines


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class HolographicMiddleware(IMiddleware):
    """Pipeline middleware that stores each FizzBuzz result holographically."""

    def __init__(
        self,
        service: HolographicStorageService,
        enable_dashboard: bool = False,
    ) -> None:
        self._service = service
        self._enable_dashboard = enable_dashboard

    @property
    def service(self) -> HolographicStorageService:
        return self._service

    def get_name(self) -> str:
        return "HolographicMiddleware"

    def get_priority(self) -> int:
        return 263

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzholographic import HolographicMiddlewareError

        context = next_handler(context)

        try:
            if context.results:
                result = context.results[-1]
                output = result.output if hasattr(result, "output") else str(context.number)
                info = self._service.store_result(context.number, output)
                context.metadata["holographic_page_id"] = info["page_id"]
                context.metadata["holographic_efficiency"] = info["efficiency"]
        except HolographicMiddlewareError:
            raise
        except Exception as exc:
            raise HolographicMiddlewareError(context.number, str(exc)) from exc

        return context

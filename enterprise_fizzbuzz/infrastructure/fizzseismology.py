"""
Enterprise FizzBuzz Platform - FizzSeismology: Seismic Wave Propagator

Simulates the propagation of seismic waves through a layered velocity
model of the Earth's interior. Each FizzBuzz evaluation generates a
synthetic seismic event whose magnitude is determined by the classification:
Fizz events produce shallow crustal earthquakes (magnitude 3-4), Buzz
events produce intermediate-depth events (magnitude 4-5), and FizzBuzz
events produce great earthquakes (magnitude 6+).

The propagation engine supports P-waves (compressional), S-waves (shear),
and surface waves (Rayleigh/Love). Ray tracing through the layered model
uses Snell's law at each interface to compute incidence angles, refraction,
and total internal reflection. Travel time tables are pre-computed for
standard distance ranges using the tau-p method.

Magnitude is computed on both the Richter (local magnitude, ML) and
moment magnitude (Mw) scales. The focal mechanism is represented as a
beach ball (lower-hemisphere stereographic projection of first-motion
polarities), with strike, dip, and rake angles derived from the
FizzBuzz classification pattern.

Physical justification: The FizzBuzz sequence's 3-against-5 pattern
produces a stress accumulation cycle analogous to tectonic plate
coupling. Monitoring seismic output provides a ground-truth validation
of the evaluation pipeline's energy release budget.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

EARTH_RADIUS = 6371.0  # km
P_WAVE_SURFACE = 5.8  # km/s (crustal P-wave velocity)
S_WAVE_SURFACE = 3.4  # km/s (crustal S-wave velocity)
RAYLEIGH_FACTOR = 0.92  # Rayleigh wave velocity ~= 0.92 * Vs
VP_VS_RATIO = 1.732  # sqrt(3) for Poisson solid
RICHTER_LOG_A0 = -1.0  # reference amplitude (log10, mm)
MOMENT_CONSTANT = 2.0 / 3.0  # Mw = (2/3) * log10(M0) - 10.7
MIN_MAGNITUDE = -2.0
MAX_MAGNITUDE = 10.0


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class WaveType(Enum):
    """Seismic wave type classification."""
    P_WAVE = auto()
    S_WAVE = auto()
    RAYLEIGH = auto()
    LOVE = auto()


class MagnitudeScale(Enum):
    """Earthquake magnitude scale."""
    RICHTER = auto()
    MOMENT = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class VelocityLayer:
    """A single layer in the 1D velocity model.

    Each layer has a top depth, P-wave velocity, S-wave velocity,
    and density. These parameters control ray refraction at interfaces
    and waveform amplitude attenuation.
    """
    top_depth: float  # km
    vp: float  # km/s (P-wave velocity)
    vs: float  # km/s (S-wave velocity)
    density: float  # g/cm^3
    name: str = ""

    def validate(self) -> bool:
        """Check that velocities are within physical bounds."""
        return self.vp > 0.0 and self.vs >= 0.0 and self.density > 0.0


@dataclass
class RaySegment:
    """A segment of a seismic ray path through one velocity layer."""
    layer_index: int
    entry_angle: float  # radians (angle from vertical)
    exit_angle: float  # radians
    path_length: float  # km
    travel_time: float  # seconds
    wave_type: WaveType = WaveType.P_WAVE


@dataclass
class TravelTimeEntry:
    """Pre-computed travel time for a specific phase and distance."""
    phase: str  # e.g., "P", "S", "PcP"
    distance_deg: float  # epicentral distance in degrees
    travel_time: float  # seconds
    ray_parameter: float  # s/km


@dataclass
class FocalMechanism:
    """Double-couple focal mechanism (beach ball representation).

    The focal mechanism is parameterized by strike, dip, and rake angles
    following the Aki & Richards convention:
      - Strike: azimuth of the fault plane (0-360 degrees)
      - Dip: angle of the fault plane from horizontal (0-90 degrees)
      - Rake: slip direction on the fault plane (-180 to 180 degrees)
    """
    strike: float  # degrees
    dip: float  # degrees
    rake: float  # degrees

    @property
    def mechanism_type(self) -> str:
        """Classify the mechanism as normal, reverse, or strike-slip."""
        if -135.0 <= self.rake <= -45.0:
            return "normal"
        elif 45.0 <= self.rake <= 135.0:
            return "reverse"
        else:
            return "strike-slip"


@dataclass
class SeismicEvent:
    """A complete seismic event with source parameters and computed fields."""
    latitude: float = 0.0
    longitude: float = 0.0
    depth: float = 10.0  # km
    magnitude_ml: float = 0.0  # Richter (local)
    magnitude_mw: float = 0.0  # moment magnitude
    focal_mechanism: Optional[FocalMechanism] = None
    origin_number: int = 0  # the FizzBuzz number that triggered this event
    ray_paths: list[RaySegment] = field(default_factory=list)
    travel_times: list[TravelTimeEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Velocity model
# ---------------------------------------------------------------------------

def build_iasp91_model() -> list[VelocityLayer]:
    """Build a simplified IASP91 velocity model.

    The IASP91 model is a standard reference model for global seismology.
    This simplified version uses 8 layers capturing the major velocity
    discontinuities: surface, Conrad, Moho, lithosphere-asthenosphere
    boundary, 410 km discontinuity, 660 km discontinuity, CMB, and ICB.
    """
    return [
        VelocityLayer(0.0, 5.8, 3.36, 2.72, "Upper Crust"),
        VelocityLayer(20.0, 6.5, 3.75, 2.92, "Lower Crust"),
        VelocityLayer(35.0, 8.04, 4.47, 3.32, "Upper Mantle"),
        VelocityLayer(210.0, 8.30, 4.52, 3.43, "Asthenosphere"),
        VelocityLayer(410.0, 9.03, 4.87, 3.54, "Transition Zone Upper"),
        VelocityLayer(660.0, 10.75, 5.95, 3.99, "Lower Mantle"),
        VelocityLayer(2891.0, 13.72, 7.26, 5.57, "Outer Core (P only)"),
        VelocityLayer(5150.0, 11.26, 3.67, 12.76, "Inner Core"),
    ]


# ---------------------------------------------------------------------------
# Ray tracing
# ---------------------------------------------------------------------------

class SeismicRayTracer:
    """Traces seismic rays through a 1D velocity model using Snell's law.

    At each layer interface, the incidence angle is updated according to
    Snell's law: sin(theta_1)/v_1 = sin(theta_2)/v_2 = ray parameter p.
    Total internal reflection occurs when sin(theta_2) > 1, creating
    a shadow zone beyond the critical distance.
    """

    def __init__(self, model: Optional[list[VelocityLayer]] = None) -> None:
        self.model = model or build_iasp91_model()
        self._validate_model()

    def _validate_model(self) -> None:
        """Validate all layers in the velocity model."""
        from enterprise_fizzbuzz.domain.exceptions.fizzseismology import VelocityModelError

        for idx, layer in enumerate(self.model):
            if not layer.validate():
                raise VelocityModelError(idx, layer.vp)

    def _get_velocity(self, depth: float, wave_type: WaveType) -> float:
        """Return the wave velocity at a given depth."""
        layer = self.model[0]
        for l in self.model:
            if l.top_depth <= depth:
                layer = l
        return layer.vp if wave_type in (WaveType.P_WAVE,) else layer.vs

    def trace_ray(
        self,
        source_depth: float,
        takeoff_angle: float,
        wave_type: WaveType = WaveType.P_WAVE,
        max_distance: float = 180.0,
    ) -> list[RaySegment]:
        """Trace a single ray from source through the velocity model.

        Args:
            source_depth: Source depth in km.
            takeoff_angle: Initial angle from vertical in radians.
            wave_type: Type of seismic wave.
            max_distance: Maximum epicentral distance in degrees.

        Returns:
            List of RaySegment objects describing the ray path.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzseismology import RayTracingError

        segments = []
        v0 = self._get_velocity(source_depth, wave_type)
        ray_param = math.sin(takeoff_angle) / v0 if v0 > 0 else 0.0

        current_depth = source_depth
        current_angle = takeoff_angle
        total_distance = 0.0
        going_down = True

        for layer_idx in range(len(self.model)):
            if layer_idx >= len(self.model) - 1:
                break

            v = self._get_velocity(current_depth, wave_type)
            if v <= 0:
                raise RayTracingError(source_depth, total_distance, "zero velocity layer")

            next_layer = self.model[layer_idx + 1] if layer_idx + 1 < len(self.model) else None
            if next_layer is None:
                break

            layer_thickness = next_layer.top_depth - self.model[layer_idx].top_depth
            if layer_thickness <= 0:
                continue

            # Path length through this layer
            if abs(math.cos(current_angle)) < 1e-10:
                path_length = layer_thickness
            else:
                path_length = layer_thickness / max(abs(math.cos(current_angle)), 1e-10)

            travel_time = path_length / v
            horizontal_dist = path_length * math.sin(abs(current_angle))
            total_distance += horizontal_dist / (EARTH_RADIUS * math.pi / 180.0)

            # Snell's law at interface
            v_next = self._get_velocity(next_layer.top_depth, wave_type)
            sin_exit = ray_param * v_next

            if abs(sin_exit) > 1.0:
                # Total internal reflection
                going_down = False
                exit_angle = math.pi / 2.0
            else:
                exit_angle = math.asin(min(abs(sin_exit), 1.0))

            segments.append(RaySegment(
                layer_index=layer_idx,
                entry_angle=current_angle,
                exit_angle=exit_angle,
                path_length=path_length,
                travel_time=travel_time,
                wave_type=wave_type,
            ))

            current_angle = exit_angle
            current_depth = next_layer.top_depth

            if total_distance > max_distance:
                break

        if not segments:
            raise RayTracingError(source_depth, max_distance, "no valid ray segments")

        return segments


# ---------------------------------------------------------------------------
# Travel time table
# ---------------------------------------------------------------------------

class TravelTimeTable:
    """Pre-computed travel times for standard phases and distances.

    Computes P and S travel times at 1-degree intervals using ray tracing
    through the velocity model.
    """

    def __init__(self, ray_tracer: Optional[SeismicRayTracer] = None) -> None:
        self.ray_tracer = ray_tracer or SeismicRayTracer()
        self._table: dict[str, list[TravelTimeEntry]] = {"P": [], "S": []}

    def compute_table(
        self,
        source_depth: float = 10.0,
        max_distance: float = 90.0,
        step: float = 5.0,
    ) -> None:
        """Compute travel time entries for P and S phases."""
        for dist in range(0, int(max_distance), int(step)):
            for phase, wt in [("P", WaveType.P_WAVE), ("S", WaveType.S_WAVE)]:
                # Approximate takeoff angle from distance
                takeoff = math.radians(max(1.0, dist * 0.5))
                try:
                    segments = self.ray_tracer.trace_ray(
                        source_depth, takeoff, wt, max_distance=dist + step
                    )
                    total_time = sum(s.travel_time for s in segments)
                    ray_param = math.sin(takeoff) / self.ray_tracer._get_velocity(
                        source_depth, wt
                    )
                    self._table[phase].append(TravelTimeEntry(
                        phase=phase,
                        distance_deg=float(dist),
                        travel_time=total_time,
                        ray_parameter=ray_param,
                    ))
                except Exception:
                    pass

    def lookup(self, phase: str, distance_deg: float) -> Optional[TravelTimeEntry]:
        """Look up the closest travel time entry for a phase and distance."""
        entries = self._table.get(phase, [])
        if not entries:
            return None
        closest = min(entries, key=lambda e: abs(e.distance_deg - distance_deg))
        return closest

    @property
    def phases(self) -> list[str]:
        return list(self._table.keys())


# ---------------------------------------------------------------------------
# Magnitude computation
# ---------------------------------------------------------------------------

def richter_magnitude(amplitude_mm: float, distance_km: float) -> float:
    """Compute local (Richter) magnitude ML.

    ML = log10(A) - log10(A0)

    where A is the maximum trace amplitude in mm and A0 is a
    distance-dependent correction.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzseismology import MagnitudeError

    if amplitude_mm <= 0:
        raise MagnitudeError("Richter", f"non-positive amplitude {amplitude_mm}")

    log_a0 = RICHTER_LOG_A0 + 1.11 * math.log10(max(distance_km, 1.0))
    ml = math.log10(amplitude_mm) - log_a0
    return max(MIN_MAGNITUDE, min(MAX_MAGNITUDE, ml))


def moment_magnitude(seismic_moment_nm: float) -> float:
    """Compute moment magnitude Mw from seismic moment M0.

    Mw = (2/3) * log10(M0) - 10.7

    where M0 is the seismic moment in Newton-meters.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzseismology import MagnitudeError

    if seismic_moment_nm <= 0:
        raise MagnitudeError("Moment", f"non-positive seismic moment {seismic_moment_nm}")

    mw = MOMENT_CONSTANT * math.log10(seismic_moment_nm) - 10.7
    return max(MIN_MAGNITUDE, min(MAX_MAGNITUDE, mw))


# ---------------------------------------------------------------------------
# Focal mechanism generator
# ---------------------------------------------------------------------------

def generate_focal_mechanism(number: int, is_fizz: bool, is_buzz: bool) -> FocalMechanism:
    """Generate a focal mechanism from the FizzBuzz classification.

    Fizz events produce normal faulting (extensional stress).
    Buzz events produce reverse faulting (compressional stress).
    FizzBuzz events produce strike-slip faulting.
    Plain numbers produce random mechanisms.
    """
    if is_fizz and is_buzz:
        # Strike-slip
        strike = (number * 17) % 360
        dip = 85.0
        rake = 0.0 if number % 2 == 0 else 180.0
    elif is_fizz:
        # Normal fault
        strike = (number * 23) % 360
        dip = 60.0
        rake = -90.0
    elif is_buzz:
        # Reverse fault
        strike = (number * 31) % 360
        dip = 30.0
        rake = 90.0
    else:
        # Random mechanism
        strike = (number * 47) % 360
        dip = 10.0 + (number * 13) % 80
        rake = -180.0 + (number * 7) % 360

    return FocalMechanism(strike=strike, dip=dip, rake=rake)


# ---------------------------------------------------------------------------
# Seismic event generator
# ---------------------------------------------------------------------------

class SeismicEventGenerator:
    """Generates synthetic seismic events from FizzBuzz evaluations.

    Combines ray tracing, magnitude computation, and focal mechanism
    determination into a complete synthetic event catalog.
    """

    def __init__(
        self,
        model: Optional[list[VelocityLayer]] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.ray_tracer = SeismicRayTracer(model)
        self.travel_times = TravelTimeTable(self.ray_tracer)
        self.travel_times.compute_table()
        self._events: list[SeismicEvent] = []

    def generate_event(
        self,
        number: int,
        is_fizz: bool,
        is_buzz: bool,
    ) -> SeismicEvent:
        """Generate a seismic event from a FizzBuzz evaluation.

        Magnitude scales with the classification:
        - Plain number: ML 1-2 (microseismic)
        - Fizz: ML 3-4 (minor)
        - Buzz: ML 4-5 (moderate)
        - FizzBuzz: ML 6-7 (strong)
        """
        if is_fizz and is_buzz:
            base_magnitude = 6.0 + (number % 20) * 0.05
            depth = 15.0
        elif is_fizz:
            base_magnitude = 3.0 + (number % 10) * 0.1
            depth = 5.0 + (number % 20)
        elif is_buzz:
            base_magnitude = 4.0 + (number % 10) * 0.1
            depth = 30.0 + (number % 50)
        else:
            base_magnitude = 1.0 + (number % 10) * 0.1
            depth = 10.0

        # Synthetic seismic moment from magnitude
        seismic_moment = 10.0 ** (1.5 * (base_magnitude + 10.7))

        focal = generate_focal_mechanism(number, is_fizz, is_buzz)

        # Trace P-wave ray
        takeoff_angle = math.radians(30.0)
        try:
            ray_paths = self.ray_tracer.trace_ray(
                depth, takeoff_angle, WaveType.P_WAVE, max_distance=90.0
            )
        except Exception:
            ray_paths = []

        # Compute travel times at a few standard distances
        travel_time_entries = []
        for dist in [10.0, 30.0, 60.0, 90.0]:
            entry = self.travel_times.lookup("P", dist)
            if entry:
                travel_time_entries.append(entry)

        event = SeismicEvent(
            latitude=(number * 7.3) % 180.0 - 90.0,
            longitude=(number * 13.1) % 360.0 - 180.0,
            depth=depth,
            magnitude_ml=base_magnitude,
            magnitude_mw=base_magnitude - 0.2,
            focal_mechanism=focal,
            origin_number=number,
            ray_paths=ray_paths,
            travel_times=travel_time_entries,
        )

        self._events.append(event)
        return event

    @property
    def event_catalog(self) -> list[SeismicEvent]:
        return list(self._events)

    @property
    def total_events(self) -> int:
        return len(self._events)

    def max_magnitude(self) -> float:
        """Return the maximum magnitude in the catalog."""
        if not self._events:
            return 0.0
        return max(e.magnitude_ml for e in self._events)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SeismologyMiddleware(IMiddleware):
    """Middleware that generates seismic events for each FizzBuzz evaluation.

    Each number passing through the pipeline triggers a synthetic
    earthquake whose parameters are derived from the FizzBuzz
    classification. Seismic metadata is attached to the processing
    context for downstream consumers.

    Priority 287 positions this in the geophysical simulation tier.
    """

    def __init__(
        self,
        model: Optional[list[VelocityLayer]] = None,
        seed: Optional[int] = None,
    ) -> None:
        self._generator = SeismicEventGenerator(model, seed)
        self._evaluations = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        try:
            event = self._generator.generate_event(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["seismo_magnitude_ml"] = event.magnitude_ml
            result.metadata["seismo_magnitude_mw"] = event.magnitude_mw
            result.metadata["seismo_depth_km"] = event.depth
            result.metadata["seismo_mechanism"] = (
                event.focal_mechanism.mechanism_type
                if event.focal_mechanism else "unknown"
            )
            result.metadata["seismo_ray_segments"] = len(event.ray_paths)
        except Exception as e:
            logger.warning("Seismology simulation failed for number %d: %s", number, e)
            result.metadata["seismo_error"] = str(e)

        return result

    def get_name(self) -> str:
        return "SeismologyMiddleware"

    def get_priority(self) -> int:
        return 287

    @property
    def generator(self) -> SeismicEventGenerator:
        return self._generator

    @property
    def evaluations(self) -> int:
        return self._evaluations

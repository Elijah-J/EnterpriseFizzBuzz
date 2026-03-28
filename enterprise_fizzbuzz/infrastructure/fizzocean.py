"""
Enterprise FizzBuzz Platform - FizzOcean: Ocean Current Simulator

Models thermohaline circulation, surface and deep currents, salinity
gradients, Ekman transport, upwelling zones, and ENSO oscillation for
a discretized ocean basin. The FizzBuzz evaluation sequence defines the
surface forcing pattern: numbers divisible by 3 generate easterly wind
stress (Fizz trades), numbers divisible by 5 generate freshwater flux
(Buzz precipitation), and FizzBuzz events trigger El Nino-like
thermocline perturbations.

The ocean basin is discretized into a latitude-longitude grid with
configurable resolution. Each cell carries temperature, salinity, and
velocity (u, v, w) fields. The thermohaline circulation is driven by
density differences computed from a simplified equation of state
(linearized UNESCO formula). Surface wind forcing generates Ekman
transport, which feeds coastal upwelling diagnostics.

The ENSO oscillation model uses a delayed-oscillator formulation where
thermocline depth anomalies in the eastern Pacific feed back through
a Kelvin-wave delay to the western Pacific. The oscillation period
is typically 2-7 years depending on coupling coefficients.

Physical justification: FizzBuzz evaluation sequences exhibit a
15-element superperiod that maps naturally to oceanic forcing cycles.
Monitoring the simulated ocean state provides a geophysically grounded
health metric for the evaluation pipeline.
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

EARTH_ROTATION_RATE = 7.2921e-5  # rad/s
GRAVITY = 9.81  # m/s^2
WATER_DENSITY_REF = 1025.0  # kg/m^3
THERMAL_EXPANSION = 2.0e-4  # 1/K
HALINE_CONTRACTION = 7.6e-4  # 1/PSU
DRAG_COEFFICIENT = 1.2e-3  # dimensionless
AIR_DENSITY = 1.225  # kg/m^3
WIND_SPEED_REF = 10.0  # m/s
FRESHWATER_FLUX_REF = 1.0e-8  # m/s (equivalent to ~0.86 mm/day)
EKMAN_DEPTH_SCALE = 50.0  # meters
MAX_PHYSICAL_VELOCITY = 2.5  # m/s
MAX_PHYSICAL_SALINITY = 40.0  # PSU
MIN_PHYSICAL_SALINITY = 0.0  # PSU

# ENSO delayed oscillator parameters
ENSO_COUPLING = 0.5
ENSO_DELAY_STEPS = 6
ENSO_DAMPING = 0.1
ENSO_MAX_ANOMALY = 150.0  # meters

# Default grid
DEFAULT_NX = 20
DEFAULT_NY = 10
DEFAULT_NZ = 5
DEFAULT_DX = 100000.0  # meters (~1 degree at equator)
DEFAULT_DT = 3600.0  # seconds (1 hour)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class CurrentType(Enum):
    """Classification of ocean current types."""
    SURFACE = auto()
    DEEP = auto()
    WESTERN_BOUNDARY = auto()
    EASTERN_BOUNDARY = auto()
    EQUATORIAL = auto()
    THERMOHALINE = auto()


@dataclass
class OceanCell:
    """A single cell in the ocean grid.

    Carries the full state vector: temperature (degrees C), salinity
    (PSU), and three-dimensional velocity (m/s). Density is computed
    from temperature and salinity using a linearized equation of state.
    """
    temperature: float = 15.0  # degrees Celsius
    salinity: float = 35.0  # PSU
    u: float = 0.0  # east-west velocity (m/s)
    v: float = 0.0  # north-south velocity (m/s)
    w: float = 0.0  # vertical velocity (m/s, positive upward)
    depth: float = 0.0  # meters below surface

    @property
    def density(self) -> float:
        """Compute seawater density using the linearized UNESCO equation.

        rho = rho_ref * (1 - alpha * (T - T_ref) + beta * (S - S_ref))

        where alpha is the thermal expansion coefficient and beta is the
        haline contraction coefficient.
        """
        return WATER_DENSITY_REF * (
            1.0
            - THERMAL_EXPANSION * (self.temperature - 15.0)
            + HALINE_CONTRACTION * (self.salinity - 35.0)
        )

    @property
    def speed(self) -> float:
        """Horizontal current speed in m/s."""
        return math.sqrt(self.u ** 2 + self.v ** 2)


@dataclass
class WindForcing:
    """Surface wind stress vector components.

    Wind stress is computed from wind speed using a bulk formula:
    tau = rho_air * C_D * |U| * U

    where C_D is the drag coefficient and U is the 10-meter wind vector.
    """
    tau_x: float = 0.0  # east-west stress (Pa)
    tau_y: float = 0.0  # north-south stress (Pa)

    @property
    def magnitude(self) -> float:
        return math.sqrt(self.tau_x ** 2 + self.tau_y ** 2)


@dataclass
class ENSOState:
    """State of the El Nino-Southern Oscillation delayed oscillator.

    The thermocline depth anomaly in the eastern Pacific is the primary
    state variable. The delay buffer stores past anomalies for the
    Kelvin-wave feedback term.
    """
    thermocline_anomaly: float = 0.0  # meters
    delay_buffer: list = field(default_factory=lambda: [0.0] * ENSO_DELAY_STEPS)
    sst_anomaly: float = 0.0  # degrees Celsius
    phase: str = "neutral"  # "el_nino", "la_nina", "neutral"
    step: int = 0


# ---------------------------------------------------------------------------
# Coriolis and Ekman computation
# ---------------------------------------------------------------------------

def coriolis_parameter(latitude_deg: float) -> float:
    """Compute the Coriolis parameter f = 2 * Omega * sin(latitude).

    Args:
        latitude_deg: Latitude in degrees (-90 to 90).

    Returns:
        Coriolis parameter in rad/s.
    """
    return 2.0 * EARTH_ROTATION_RATE * math.sin(math.radians(latitude_deg))


def ekman_transport(wind_stress: WindForcing, latitude_deg: float) -> Tuple[float, float]:
    """Compute Ekman transport components from wind stress and latitude.

    The Ekman transport is perpendicular to the wind stress and inversely
    proportional to the Coriolis parameter:

        M_x = tau_y / f
        M_y = -tau_x / f

    At the equator (f -> 0), the Ekman transport becomes singular.
    A minimum Coriolis parameter threshold is applied.

    Returns:
        Tuple of (M_x, M_y) in kg/(m*s).
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzocean import EkmanTransportError

    f = coriolis_parameter(latitude_deg)
    if abs(f) < 1.0e-8:
        raise EkmanTransportError(
            latitude_deg,
            "Coriolis parameter too close to zero (equatorial singularity)",
        )

    mx = wind_stress.tau_y / f
    my = -wind_stress.tau_x / f
    return mx, my


def compute_wind_stress(wind_u: float, wind_v: float) -> WindForcing:
    """Compute wind stress from 10-meter wind components using bulk formula."""
    speed = math.sqrt(wind_u ** 2 + wind_v ** 2)
    tau_x = AIR_DENSITY * DRAG_COEFFICIENT * speed * wind_u
    tau_y = AIR_DENSITY * DRAG_COEFFICIENT * speed * wind_v
    return WindForcing(tau_x=tau_x, tau_y=tau_y)


# ---------------------------------------------------------------------------
# Equation of state utilities
# ---------------------------------------------------------------------------

def density_from_ts(temperature: float, salinity: float) -> float:
    """Compute seawater density from temperature and salinity."""
    return WATER_DENSITY_REF * (
        1.0
        - THERMAL_EXPANSION * (temperature - 15.0)
        + HALINE_CONTRACTION * (salinity - 35.0)
    )


def buoyancy_frequency(
    rho_upper: float, rho_lower: float, dz: float
) -> float:
    """Compute the Brunt-Vaisala (buoyancy) frequency N.

    N^2 = -(g / rho_ref) * (drho / dz)

    Returns N in rad/s (or 0.0 if the water column is unstably stratified).
    """
    # dz is a positive depth interval; z increases upward, so drho/dz
    # (with z upward) = (rho_upper - rho_lower) / dz for stable stratification.
    drho_dz = (rho_upper - rho_lower) / max(dz, 1.0)
    n_squared = -(GRAVITY / WATER_DENSITY_REF) * drho_dz
    if n_squared < 0:
        return 0.0
    return math.sqrt(n_squared)


# ---------------------------------------------------------------------------
# Ocean grid
# ---------------------------------------------------------------------------

class OceanGrid:
    """Discretized ocean basin with temperature, salinity, and velocity fields.

    The grid is organized as [depth_layer][latitude_row][longitude_col].
    Latitude ranges from -45 to +45 degrees and longitude spans the
    basin width. Depth layers represent ocean levels from surface to
    the abyssal plain.
    """

    def __init__(
        self,
        nx: int = DEFAULT_NX,
        ny: int = DEFAULT_NY,
        nz: int = DEFAULT_NZ,
        dx: float = DEFAULT_DX,
        lat_min: float = -45.0,
        lat_max: float = 45.0,
    ) -> None:
        self.nx = nx
        self.ny = ny
        self.nz = nz
        self.dx = dx
        self.lat_min = lat_min
        self.lat_max = lat_max
        self.dlat = (lat_max - lat_min) / max(ny - 1, 1)

        # Depth levels (meters below surface)
        self.depth_levels = [
            50.0 * (2 ** k) for k in range(nz)
        ]

        # Initialize the 3D grid
        self.cells: list[list[list[OceanCell]]] = []
        for k in range(nz):
            layer = []
            for j in range(ny):
                row = []
                for i in range(nx):
                    cell = OceanCell(
                        temperature=20.0 - 0.5 * k - 0.1 * abs(j - ny // 2),
                        salinity=35.0 + 0.02 * (j - ny // 2),
                        depth=self.depth_levels[k],
                    )
                    row.append(cell)
                layer.append(row)
            self.cells.append(layer)

    def latitude_at(self, j: int) -> float:
        """Return the latitude in degrees for grid row j."""
        return self.lat_min + j * self.dlat

    def get_surface_cell(self, i: int, j: int) -> OceanCell:
        """Return the surface-layer cell at grid position (i, j)."""
        return self.cells[0][j][i]

    def total_cells(self) -> int:
        return self.nx * self.ny * self.nz

    def mean_surface_temperature(self) -> float:
        """Compute the area-averaged sea surface temperature."""
        total = 0.0
        count = 0
        for j in range(self.ny):
            for i in range(self.nx):
                total += self.cells[0][j][i].temperature
                count += 1
        return total / max(count, 1)

    def mean_surface_salinity(self) -> float:
        """Compute the area-averaged sea surface salinity."""
        total = 0.0
        count = 0
        for j in range(self.ny):
            for i in range(self.nx):
                total += self.cells[0][j][i].salinity
                count += 1
        return total / max(count, 1)

    def max_surface_speed(self) -> float:
        """Return the maximum horizontal current speed at the surface."""
        max_spd = 0.0
        for j in range(self.ny):
            for i in range(self.nx):
                spd = self.cells[0][j][i].speed
                if spd > max_spd:
                    max_spd = spd
        return max_spd


# ---------------------------------------------------------------------------
# Thermohaline circulation solver
# ---------------------------------------------------------------------------

class ThermohalineSolver:
    """Iterative solver for thermohaline-driven overturning circulation.

    Computes the density-driven velocity field by solving a simplified
    momentum balance where the pressure gradient force balances friction.
    The density field is derived from the temperature and salinity
    distributions via the linearized equation of state.

    The solver iterates until the velocity residual falls below a
    convergence threshold or the maximum iteration count is reached.
    """

    def __init__(
        self,
        max_iterations: int = 100,
        tolerance: float = 1.0e-6,
        diffusivity: float = 1.0e-4,
    ) -> None:
        self.max_iterations = max_iterations
        self.tolerance = tolerance
        self.diffusivity = diffusivity

    def solve(self, grid: OceanGrid, dt: float = DEFAULT_DT) -> int:
        """Update the velocity field based on density gradients.

        Returns the number of iterations required for convergence.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzocean import ThermohalineError

        for iteration in range(1, self.max_iterations + 1):
            max_residual = 0.0

            for k in range(grid.nz):
                for j in range(1, grid.ny - 1):
                    for i in range(1, grid.nx - 1):
                        cell = grid.cells[k][j][i]
                        cell_east = grid.cells[k][j][i + 1] if i + 1 < grid.nx else cell
                        cell_west = grid.cells[k][j][i - 1] if i > 0 else cell
                        cell_north = grid.cells[k][j + 1][i] if j + 1 < grid.ny else cell
                        cell_south = grid.cells[k][j - 1][i] if j > 0 else cell

                        # Pressure gradient from density differences
                        dp_dx = (cell_east.density - cell_west.density) / (2.0 * grid.dx)
                        dp_dy = (cell_north.density - cell_south.density) / (2.0 * grid.dx)

                        # Geostrophic balance: f * v = (1/rho) * dp/dx
                        lat = grid.latitude_at(j)
                        f = coriolis_parameter(lat)

                        if abs(f) > 1.0e-8:
                            new_v = (GRAVITY / (f * WATER_DENSITY_REF)) * dp_dx
                            new_u = -(GRAVITY / (f * WATER_DENSITY_REF)) * dp_dy
                        else:
                            new_u = cell.u
                            new_v = cell.v

                        # Diffusion damping
                        new_u = cell.u + dt * (
                            self.diffusivity * (
                                cell_east.u + cell_west.u - 2.0 * cell.u
                            ) / (grid.dx ** 2)
                            + 0.01 * (new_u - cell.u)
                        )
                        new_v = cell.v + dt * (
                            self.diffusivity * (
                                cell_north.v + cell_south.v - 2.0 * cell.v
                            ) / (grid.dx ** 2)
                            + 0.01 * (new_v - cell.v)
                        )

                        residual = math.sqrt(
                            (new_u - cell.u) ** 2 + (new_v - cell.v) ** 2
                        )
                        max_residual = max(max_residual, residual)

                        cell.u = new_u
                        cell.v = new_v

            if max_residual < self.tolerance:
                logger.debug(
                    "Thermohaline solver converged in %d iterations (residual: %.2e)",
                    iteration,
                    max_residual,
                )
                return iteration

        raise ThermohalineError(self.max_iterations, max_residual)


# ---------------------------------------------------------------------------
# Upwelling detector
# ---------------------------------------------------------------------------

class UpwellingDetector:
    """Identifies coastal upwelling zones from vertical velocity patterns.

    Upwelling is diagnosed where vertical velocity at the base of the
    surface layer exceeds a threshold value. Coastal upwelling is
    enhanced by offshore Ekman transport driven by along-shore winds.
    """

    def __init__(self, threshold: float = 1.0e-5) -> None:
        self.threshold = threshold

    def detect(self, grid: OceanGrid) -> list[tuple[int, int, float]]:
        """Return a list of (i, j, w) tuples identifying upwelling cells.

        Only surface-layer cells with upward vertical velocity exceeding
        the threshold are included.
        """
        upwelling_zones = []
        for j in range(grid.ny):
            for i in range(grid.nx):
                w = grid.cells[0][j][i].w
                if w > self.threshold:
                    upwelling_zones.append((i, j, w))
        return upwelling_zones


# ---------------------------------------------------------------------------
# ENSO oscillator
# ---------------------------------------------------------------------------

class ENSOOscillator:
    """Delayed-oscillator model for the El Nino-Southern Oscillation.

    The model evolves a thermocline depth anomaly H using:

        dH/dt = coupling * H - damping * H_delayed + forcing

    where H_delayed is the anomaly from ENSO_DELAY_STEPS time steps ago,
    representing the Kelvin-wave feedback from the western Pacific.
    """

    def __init__(
        self,
        coupling: float = ENSO_COUPLING,
        damping: float = ENSO_DAMPING,
        delay_steps: int = ENSO_DELAY_STEPS,
        seed: Optional[int] = None,
    ) -> None:
        self.coupling = coupling
        self.damping = damping
        self.delay_steps = delay_steps
        self.state = ENSOState()
        self._rng_seed = seed

    def step(self, external_forcing: float = 0.0) -> ENSOState:
        """Advance the ENSO oscillator by one time step.

        Args:
            external_forcing: External thermocline perturbation (meters).

        Returns:
            Updated ENSO state.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzocean import ENSOError

        h = self.state.thermocline_anomaly
        h_delayed = self.state.delay_buffer[0]

        # Delayed oscillator equation
        dh = self.coupling * h - self.damping * h_delayed + external_forcing
        new_h = h + dh

        if abs(new_h) > ENSO_MAX_ANOMALY:
            raise ENSOError(new_h, self.state.step)

        # Update delay buffer (shift)
        self.state.delay_buffer = self.state.delay_buffer[1:] + [new_h]
        self.state.thermocline_anomaly = new_h
        self.state.step += 1

        # SST anomaly proportional to thermocline anomaly
        self.state.sst_anomaly = new_h * 0.05

        # Phase classification
        if new_h > 20.0:
            self.state.phase = "el_nino"
        elif new_h < -20.0:
            self.state.phase = "la_nina"
        else:
            self.state.phase = "neutral"

        return self.state


# ---------------------------------------------------------------------------
# Salinity advection
# ---------------------------------------------------------------------------

def advect_salinity(
    grid: OceanGrid, dt: float, freshwater_cells: list[tuple[int, int]]
) -> None:
    """Apply freshwater forcing and advect salinity across the grid.

    Freshwater flux reduces surface salinity at specified cells. Simple
    upstream advection then transports the salinity field with the
    current velocity.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzocean import SalinityError

    # Apply freshwater flux
    for (i, j) in freshwater_cells:
        if 0 <= i < grid.nx and 0 <= j < grid.ny:
            grid.cells[0][j][i].salinity -= FRESHWATER_FLUX_REF * dt * 1000.0

    # Upstream advection for surface layer
    for j in range(1, grid.ny - 1):
        for i in range(1, grid.nx - 1):
            cell = grid.cells[0][j][i]
            # Upstream differencing
            if cell.u > 0:
                ds_dx = (cell.salinity - grid.cells[0][j][i - 1].salinity) / grid.dx
            else:
                ds_dx = (grid.cells[0][j][i + 1].salinity - cell.salinity) / grid.dx

            if cell.v > 0:
                ds_dy = (cell.salinity - grid.cells[0][j - 1][i].salinity) / grid.dx
            else:
                ds_dy = (grid.cells[0][j + 1][i].salinity - cell.salinity) / grid.dx

            new_s = cell.salinity - dt * (cell.u * ds_dx + cell.v * ds_dy)

            if new_s < MIN_PHYSICAL_SALINITY or new_s > MAX_PHYSICAL_SALINITY:
                raise SalinityError(new_s, j * grid.nx + i)

            cell.salinity = new_s


# ---------------------------------------------------------------------------
# Current classifier
# ---------------------------------------------------------------------------

def classify_current(
    cell: OceanCell, latitude: float, i: int, nx: int
) -> CurrentType:
    """Classify the current at a grid cell based on its position and depth."""
    if cell.depth > 200.0:
        return CurrentType.DEEP
    if abs(latitude) < 5.0:
        return CurrentType.EQUATORIAL
    if i < nx * 0.1:
        return CurrentType.WESTERN_BOUNDARY
    if i > nx * 0.9:
        return CurrentType.EASTERN_BOUNDARY
    if cell.depth <= 50.0:
        return CurrentType.SURFACE
    return CurrentType.THERMOHALINE


# ---------------------------------------------------------------------------
# Ocean simulator (composition root)
# ---------------------------------------------------------------------------

class OceanSimulator:
    """Integrates all ocean simulation components into a unified engine.

    Coordinates the thermohaline solver, Ekman transport, upwelling
    detection, ENSO oscillation, and salinity advection across the
    discretized ocean basin. Each FizzBuzz evaluation provides external
    forcing: Fizz events generate wind stress, Buzz events inject
    freshwater, and FizzBuzz events perturb the ENSO thermocline.
    """

    def __init__(
        self,
        nx: int = DEFAULT_NX,
        ny: int = DEFAULT_NY,
        nz: int = DEFAULT_NZ,
        dt: float = DEFAULT_DT,
        seed: Optional[int] = None,
    ) -> None:
        self.grid = OceanGrid(nx=nx, ny=ny, nz=nz)
        self.thermohaline = ThermohalineSolver()
        self.upwelling = UpwellingDetector()
        self.enso = ENSOOscillator(seed=seed)
        self.dt = dt
        self._step_count = 0
        self._total_fizz_forcing = 0
        self._total_buzz_forcing = 0
        self._total_fizzbuzz_forcing = 0

    def apply_fizz_forcing(self, number: int) -> None:
        """Apply easterly wind stress (trade wind enhancement) for Fizz events.

        Fizz events represent trade wind intensification along the equatorial
        belt, which enhances Ekman transport and drives coastal upwelling.
        """
        wind_u = -WIND_SPEED_REF * (1.0 + 0.1 * (number % 10))
        wind_v = 0.0
        stress = compute_wind_stress(wind_u, wind_v)

        # Apply to equatorial cells
        for j in range(self.grid.ny):
            lat = self.grid.latitude_at(j)
            if abs(lat) < 15.0:
                for i in range(self.grid.nx):
                    f = coriolis_parameter(lat)
                    if abs(f) > 1.0e-8:
                        self.grid.cells[0][j][i].u += stress.tau_x / (
                            WATER_DENSITY_REF * EKMAN_DEPTH_SCALE * abs(f)
                        ) * self.dt * 0.001

        self._total_fizz_forcing += 1

    def apply_buzz_forcing(self, number: int) -> None:
        """Apply freshwater flux (precipitation event) for Buzz events.

        Buzz events represent tropical precipitation events that reduce
        surface salinity, altering the density field and influencing
        the thermohaline circulation.
        """
        # Select cells for freshwater injection based on number
        cells = []
        for j in range(self.grid.ny):
            for i in range(self.grid.nx):
                if (i + j + number) % 5 == 0:
                    cells.append((i, j))

        advect_salinity(self.grid, self.dt * 0.01, cells)
        self._total_buzz_forcing += 1

    def apply_fizzbuzz_forcing(self, number: int) -> None:
        """Perturb the ENSO thermocline for FizzBuzz events.

        FizzBuzz events inject a positive thermocline anomaly, simulating
        the kind of external forcing that can trigger an El Nino event.
        """
        perturbation = 5.0 * math.sin(number * 0.2)
        self.enso.step(external_forcing=perturbation)
        self._total_fizzbuzz_forcing += 1

    def step(self, number: int, is_fizz: bool, is_buzz: bool) -> dict:
        """Advance the simulation by one time step with FizzBuzz forcing.

        Returns a diagnostic dictionary with key ocean state metrics.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzocean import CurrentVelocityError

        if is_fizz and is_buzz:
            self.apply_fizzbuzz_forcing(number)
        elif is_fizz:
            self.apply_fizz_forcing(number)
        elif is_buzz:
            self.apply_buzz_forcing(number)

        # Run thermohaline solver (with relaxed tolerance for real-time use)
        try:
            iterations = self.thermohaline.solve(self.grid, self.dt)
        except Exception:
            iterations = self.thermohaline.max_iterations

        # Detect upwelling zones
        upwelling_zones = self.upwelling.detect(self.grid)

        # Velocity check
        max_speed = self.grid.max_surface_speed()
        if max_speed > MAX_PHYSICAL_VELOCITY:
            # Apply velocity clamping instead of raising
            for j in range(self.grid.ny):
                for i in range(self.grid.nx):
                    cell = self.grid.cells[0][j][i]
                    spd = cell.speed
                    if spd > MAX_PHYSICAL_VELOCITY:
                        scale = MAX_PHYSICAL_VELOCITY / spd
                        cell.u *= scale
                        cell.v *= scale

        self._step_count += 1

        return {
            "step": self._step_count,
            "mean_sst": self.grid.mean_surface_temperature(),
            "mean_sss": self.grid.mean_surface_salinity(),
            "max_speed": self.grid.max_surface_speed(),
            "upwelling_count": len(upwelling_zones),
            "enso_phase": self.enso.state.phase,
            "enso_anomaly": self.enso.state.thermocline_anomaly,
            "thermohaline_iterations": iterations,
        }

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def enso_state(self) -> ENSOState:
        return self.enso.state


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class OceanMiddleware(IMiddleware):
    """Middleware that runs the FizzOcean simulation for each evaluation.

    Each number passing through the pipeline generates ocean forcing
    based on its FizzBuzz classification. The resulting ocean state
    diagnostics are attached to the processing context metadata.

    Priority 286 positions this in the geophysical simulation tier.
    """

    def __init__(
        self,
        nx: int = DEFAULT_NX,
        ny: int = DEFAULT_NY,
        nz: int = DEFAULT_NZ,
        seed: Optional[int] = None,
    ) -> None:
        self._simulator = OceanSimulator(nx=nx, ny=ny, nz=nz, seed=seed)
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
            diagnostics = self._simulator.step(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["ocean_sst"] = diagnostics["mean_sst"]
            result.metadata["ocean_salinity"] = diagnostics["mean_sss"]
            result.metadata["ocean_max_speed"] = diagnostics["max_speed"]
            result.metadata["ocean_upwelling_count"] = diagnostics["upwelling_count"]
            result.metadata["ocean_enso_phase"] = diagnostics["enso_phase"]
        except Exception as e:
            logger.warning("Ocean simulation failed for number %d: %s", number, e)
            result.metadata["ocean_error"] = str(e)

        return result

    def get_name(self) -> str:
        return "OceanMiddleware"

    def get_priority(self) -> int:
        return 286

    @property
    def simulator(self) -> OceanSimulator:
        return self._simulator

    @property
    def evaluations(self) -> int:
        return self._evaluations

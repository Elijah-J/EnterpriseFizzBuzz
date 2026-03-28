"""
Enterprise FizzBuzz Platform - FizzWeather Weather Simulation Engine

Simulates atmospheric dynamics to determine the meteorological conditions
under which each FizzBuzz evaluation occurs. The engine models simplified
Navier-Stokes fluid dynamics on a 2D atmospheric grid, tracks pressure
systems, computes temperature gradients, and predicts precipitation.

The Coriolis effect — arising from Earth's rotation — produces the
cyclonic and anticyclonic circulation patterns that directly influence
FizzBuzz output confidence. In the Northern Hemisphere, low-pressure
systems rotate counterclockwise, which by convention increases the
probability of "Fizz" classifications. The Southern Hemisphere reverses
this, favoring "Buzz".

The atmospheric model operates on a staggered Arakawa C-grid with
forward Euler time stepping and centered spatial differences. The CFL
condition is enforced to ensure numerical stability.

All fluid dynamics computations use pure Python math. No external
meteorology or CFD libraries are required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzweather import (
    CoriolisError,
    GridResolutionError,
    NavierStokesError,
    PrecipitationError,
    PressureSystemError,
    TemperatureGradientError,
    WeatherMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Physical constants
EARTH_OMEGA = 7.2921e-5  # Earth angular velocity (rad/s)
GAS_CONSTANT_DRY = 287.058  # J/(kg*K) for dry air
GRAVITY = 9.80665  # m/s^2
LAPSE_RATE_DRY = 9.8  # K/km dry adiabatic
STEFAN_BOLTZMANN = 5.670374419e-8  # W/(m^2*K^4)
REFERENCE_PRESSURE = 1013.25  # hPa standard sea level
MIN_GRID_SIZE = 4


# ============================================================
# Enums
# ============================================================


class PressureType(Enum):
    """Type of atmospheric pressure system."""

    HIGH = auto()
    LOW = auto()


class PrecipitationType(Enum):
    """Classification of precipitation."""

    NONE = auto()
    RAIN = auto()
    SNOW = auto()
    SLEET = auto()
    HAIL = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass
class GridCell:
    """A single cell in the atmospheric grid."""

    pressure: float = REFERENCE_PRESSURE  # hPa
    temperature: float = 288.15  # K (15 C)
    humidity: float = 0.5  # relative humidity [0, 1]
    u_wind: float = 0.0  # east-west wind component (m/s)
    v_wind: float = 0.0  # north-south wind component (m/s)


@dataclass
class PressureSystem:
    """A synoptic-scale pressure system on the atmospheric grid."""

    system_type: PressureType
    center_x: int
    center_y: int
    central_pressure: float  # hPa
    radius: int  # grid cells

    def validate(self) -> None:
        """Validate that pressure values are physical."""
        if self.central_pressure <= 0:
            raise PressureSystemError(self.system_type.name, self.central_pressure)
        if self.central_pressure < 870 or self.central_pressure > 1084:
            raise PressureSystemError(
                self.system_type.name, self.central_pressure
            )


@dataclass
class WeatherState:
    """Complete atmospheric state at a given time step."""

    grid: list[list[GridCell]]
    time_step: int = 0
    total_precipitation_mm: float = 0.0
    mean_pressure: float = REFERENCE_PRESSURE
    mean_temperature: float = 288.15
    dominant_wind_direction: str = "calm"


@dataclass
class Forecast:
    """Weather forecast for a FizzBuzz evaluation point."""

    temperature_c: float
    pressure_hpa: float
    humidity: float
    wind_speed_ms: float
    wind_direction: str
    precipitation_type: PrecipitationType
    precipitation_rate_mm_hr: float
    coriolis_parameter: float


# ============================================================
# Atmospheric Grid
# ============================================================


class AtmosphericGrid:
    """2D atmospheric simulation grid with Arakawa C-grid staggering.

    The grid represents a horizontal slice of the atmosphere at a
    single pressure level. State variables (pressure, temperature,
    humidity) are defined at cell centers. Wind components u and v
    are staggered to cell faces for numerical accuracy.
    """

    def __init__(self, nx: int, ny: int, dx_km: float = 10.0) -> None:
        if nx < MIN_GRID_SIZE or ny < MIN_GRID_SIZE:
            raise GridResolutionError(nx, ny, MIN_GRID_SIZE)

        self.nx = nx
        self.ny = ny
        self.dx = dx_km * 1000.0  # convert to meters
        self.grid: list[list[GridCell]] = [
            [GridCell() for _ in range(ny)] for _ in range(nx)
        ]

    def apply_pressure_system(self, system: PressureSystem) -> None:
        """Impose a pressure system onto the grid.

        The pressure perturbation follows a Gaussian profile centered
        at the system location with width proportional to the radius.
        """
        system.validate()
        delta_p = system.central_pressure - REFERENCE_PRESSURE

        for i in range(self.nx):
            for j in range(self.ny):
                dist_sq = (i - system.center_x) ** 2 + (j - system.center_y) ** 2
                sigma = max(system.radius / 2.0, 1.0)
                gaussian = math.exp(-dist_sq / (2.0 * sigma * sigma))
                self.grid[i][j].pressure = REFERENCE_PRESSURE + delta_p * gaussian

    def set_temperature_gradient(
        self, base_temp_k: float, gradient_k_per_km: float
    ) -> None:
        """Apply a north-south temperature gradient across the grid.

        The gradient represents the meridional temperature contrast
        that drives midlatitude weather systems.
        """
        if abs(gradient_k_per_km) > LAPSE_RATE_DRY * 1.5:
            raise TemperatureGradientError(gradient_k_per_km, LAPSE_RATE_DRY * 1.5)

        for i in range(self.nx):
            for j in range(self.ny):
                y_km = j * self.dx / 1000.0
                self.grid[i][j].temperature = base_temp_k + gradient_k_per_km * y_km


# ============================================================
# Coriolis Computation
# ============================================================


class CoriolisComputer:
    """Computes the Coriolis parameter for a given latitude.

    The Coriolis parameter f = 2 * Omega * sin(phi) determines the
    strength of the Coriolis effect at latitude phi. This is the
    fundamental connection between Earth's rotation and atmospheric
    circulation, and thus between planetary physics and FizzBuzz
    classification bias.
    """

    @staticmethod
    def coriolis_parameter(latitude_deg: float) -> float:
        """Compute the Coriolis parameter f at the given latitude."""
        if abs(latitude_deg) > 90.0:
            raise CoriolisError(latitude_deg, "Latitude must be in [-90, 90]")
        return 2.0 * EARTH_OMEGA * math.sin(math.radians(latitude_deg))

    @staticmethod
    def geostrophic_wind(
        dp_dx: float, dp_dy: float, density: float, f: float
    ) -> tuple[float, float]:
        """Compute geostrophic wind components from pressure gradients.

        In geostrophic balance, the pressure gradient force equals
        the Coriolis force: u_g = -(1/rho*f) * dp/dy,
        v_g = (1/rho*f) * dp/dx.
        """
        if abs(f) < 1e-10:
            raise CoriolisError(0.0, "Coriolis parameter too small for geostrophic balance")
        u_g = -(1.0 / (density * f)) * dp_dy
        v_g = (1.0 / (density * f)) * dp_dx
        return u_g, v_g


# ============================================================
# Navier-Stokes Solver (Simplified)
# ============================================================


class NavierStokesSolver:
    """Simplified 2D Navier-Stokes solver for atmospheric flow.

    Uses forward Euler time stepping with centered spatial differences
    on the atmospheric grid. Includes pressure gradient force, Coriolis
    force, and simple viscous diffusion. The CFL condition is checked
    before each timestep to ensure numerical stability.
    """

    def __init__(
        self,
        grid: AtmosphericGrid,
        latitude: float = 45.0,
        viscosity: float = 1e4,
    ) -> None:
        self._grid = grid
        self._f = CoriolisComputer.coriolis_parameter(latitude)
        self._viscosity = viscosity
        self._density = 1.225  # kg/m^3 at sea level

    def _check_cfl(self, dt: float) -> float:
        """Check the CFL condition and return the CFL number."""
        max_vel = 0.0
        for i in range(self._grid.nx):
            for j in range(self._grid.ny):
                cell = self._grid.grid[i][j]
                speed = math.sqrt(cell.u_wind ** 2 + cell.v_wind ** 2)
                max_vel = max(max_vel, speed)

        cfl = dt * max_vel / self._grid.dx if self._grid.dx > 0 else 0.0
        return cfl

    def step(self, dt: float) -> None:
        """Advance the atmospheric state by dt seconds."""
        cfl = self._check_cfl(dt)
        if cfl > 1.0:
            raise NavierStokesError(cfl, dt)

        g = self._grid
        nx, ny = g.nx, g.ny
        dx = g.dx

        # Compute new wind fields
        new_u = [[0.0] * ny for _ in range(nx)]
        new_v = [[0.0] * ny for _ in range(nx)]

        for i in range(1, nx - 1):
            for j in range(1, ny - 1):
                cell = g.grid[i][j]

                # Pressure gradients (finite difference)
                dp_dx = (g.grid[i + 1][j].pressure - g.grid[i - 1][j].pressure) * 100.0 / (2.0 * dx)
                dp_dy = (g.grid[i][j + 1].pressure - g.grid[i][j - 1].pressure) * 100.0 / (2.0 * dx)

                # Coriolis force
                f_coriolis_u = self._f * cell.v_wind
                f_coriolis_v = -self._f * cell.u_wind

                # Viscous diffusion (Laplacian)
                laplacian_u = (
                    g.grid[i + 1][j].u_wind + g.grid[i - 1][j].u_wind +
                    g.grid[i][j + 1].u_wind + g.grid[i][j - 1].u_wind -
                    4.0 * cell.u_wind
                ) / (dx * dx)

                laplacian_v = (
                    g.grid[i + 1][j].v_wind + g.grid[i - 1][j].v_wind +
                    g.grid[i][j + 1].v_wind + g.grid[i][j - 1].v_wind -
                    4.0 * cell.v_wind
                ) / (dx * dx)

                # Update momentum equations
                new_u[i][j] = cell.u_wind + dt * (
                    -dp_dx / self._density + f_coriolis_u + self._viscosity * laplacian_u
                )
                new_v[i][j] = cell.v_wind + dt * (
                    -dp_dy / self._density + f_coriolis_v + self._viscosity * laplacian_v
                )

        # Apply updated winds
        for i in range(1, nx - 1):
            for j in range(1, ny - 1):
                g.grid[i][j].u_wind = new_u[i][j]
                g.grid[i][j].v_wind = new_v[i][j]

    def simulate(self, total_seconds: float, dt: float) -> list[WeatherState]:
        """Run the simulation and return state snapshots."""
        steps = max(1, int(total_seconds / dt))
        states: list[WeatherState] = []

        for step_num in range(steps):
            self.step(dt)
            state = self._capture_state(step_num)
            states.append(state)

        return states

    def _capture_state(self, step_num: int) -> WeatherState:
        """Capture the current atmospheric state as a WeatherState."""
        g = self._grid
        total_p = 0.0
        total_t = 0.0
        count = 0
        max_speed = 0.0
        max_dir = "calm"

        for i in range(g.nx):
            for j in range(g.ny):
                cell = g.grid[i][j]
                total_p += cell.pressure
                total_t += cell.temperature
                count += 1
                speed = math.sqrt(cell.u_wind ** 2 + cell.v_wind ** 2)
                if speed > max_speed:
                    max_speed = speed
                    angle = math.degrees(math.atan2(cell.v_wind, cell.u_wind))
                    max_dir = _wind_direction(angle)

        return WeatherState(
            grid=[[GridCell(
                pressure=g.grid[i][j].pressure,
                temperature=g.grid[i][j].temperature,
                humidity=g.grid[i][j].humidity,
                u_wind=g.grid[i][j].u_wind,
                v_wind=g.grid[i][j].v_wind,
            ) for j in range(g.ny)] for i in range(g.nx)],
            time_step=step_num,
            mean_pressure=total_p / max(count, 1),
            mean_temperature=total_t / max(count, 1),
            dominant_wind_direction=max_dir,
        )


# ============================================================
# Precipitation Predictor
# ============================================================


class PrecipitationPredictor:
    """Predicts precipitation type and rate from atmospheric state.

    Uses the Clausius-Clapeyron relation to determine the saturation
    vapor pressure at the given temperature. When relative humidity
    exceeds 100% of the saturation value, excess moisture condenses
    and precipitates. Temperature at the surface determines the
    precipitation type.
    """

    @staticmethod
    def saturation_vapor_pressure(temperature_k: float) -> float:
        """Compute saturation vapor pressure using the Buck equation (hPa)."""
        t_c = temperature_k - 273.15
        return 6.1121 * math.exp((18.678 - t_c / 234.5) * (t_c / (257.14 + t_c)))

    @staticmethod
    def predict(cell: GridCell) -> tuple[PrecipitationType, float]:
        """Predict precipitation type and rate for a grid cell."""
        e_sat = PrecipitationPredictor.saturation_vapor_pressure(cell.temperature)
        e_actual = cell.humidity * e_sat

        if e_actual < e_sat * 0.95:
            return PrecipitationType.NONE, 0.0

        # Excess moisture -> precipitation rate (simplified)
        excess = max(0.0, (e_actual - e_sat) / e_sat)
        rate_mm_hr = excess * 20.0  # Empirical scaling

        if rate_mm_hr < 0:
            raise PrecipitationError(rate_mm_hr, "Negative precipitation rate")

        # Determine type based on temperature
        t_c = cell.temperature - 273.15
        if t_c > 2.0:
            precip_type = PrecipitationType.RAIN
        elif t_c > -2.0:
            precip_type = PrecipitationType.SLEET
        else:
            precip_type = PrecipitationType.SNOW

        return precip_type, rate_mm_hr


# ============================================================
# Helpers
# ============================================================


def _wind_direction(angle_deg: float) -> str:
    """Convert wind angle to cardinal direction string."""
    directions = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
    idx = int(((angle_deg + 22.5) % 360) / 45.0)
    return directions[idx % 8]


# ============================================================
# FizzWeather Middleware
# ============================================================


class WeatherMiddleware(IMiddleware):
    """Injects weather simulation data into the FizzBuzz pipeline.

    For each number evaluated, the middleware samples the atmospheric
    grid at a position derived from the number and injects temperature,
    pressure, wind, and precipitation data into the processing context.
    """

    def __init__(
        self,
        grid: AtmosphericGrid,
        latitude: float = 45.0,
    ) -> None:
        self._grid = grid
        self._latitude = latitude
        self._coriolis = CoriolisComputer.coriolis_parameter(latitude)
        self._precip_predictor = PrecipitationPredictor()

    def get_name(self) -> str:
        return "fizzweather"

    def get_priority(self) -> int:
        return 276

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Inject weather context and delegate to next handler."""
        try:
            # Map number to grid position
            i = context.number % self._grid.nx
            j = (context.number // self._grid.nx) % self._grid.ny
            cell = self._grid.grid[i][j]

            wind_speed = math.sqrt(cell.u_wind ** 2 + cell.v_wind ** 2)
            wind_dir = _wind_direction(
                math.degrees(math.atan2(cell.v_wind, cell.u_wind))
            )
            precip_type, precip_rate = self._precip_predictor.predict(cell)

            forecast = Forecast(
                temperature_c=cell.temperature - 273.15,
                pressure_hpa=cell.pressure,
                humidity=cell.humidity,
                wind_speed_ms=wind_speed,
                wind_direction=wind_dir,
                precipitation_type=precip_type,
                precipitation_rate_mm_hr=precip_rate,
                coriolis_parameter=self._coriolis,
            )

            context.metadata["weather_temperature_c"] = forecast.temperature_c
            context.metadata["weather_pressure_hpa"] = forecast.pressure_hpa
            context.metadata["weather_wind_speed_ms"] = forecast.wind_speed_ms
            context.metadata["weather_wind_direction"] = forecast.wind_direction
            context.metadata["weather_precipitation"] = forecast.precipitation_type.name
            context.metadata["weather_coriolis"] = forecast.coriolis_parameter

            logger.debug(
                "FizzWeather: number=%d temp=%.1fC pressure=%.1fhPa wind=%s@%.1fm/s",
                context.number, forecast.temperature_c, forecast.pressure_hpa,
                forecast.wind_direction, forecast.wind_speed_ms,
            )
        except Exception as exc:
            logger.error("FizzWeather middleware error: %s", exc)
            context.metadata["weather_error"] = str(exc)

        return next_handler(context)

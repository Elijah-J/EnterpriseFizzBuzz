"""
Enterprise FizzBuzz Platform - FizzAstronomy Celestial Mechanics Engine

Computes orbital mechanics, n-body gravitational simulations, and ephemeris
data to establish the celestial context of each FizzBuzz evaluation. The
position of planets along their Keplerian orbits determines gravitational
weighting factors applied to divisibility checks.

The FizzBuzz sequence exhibits a 15-number periodicity (LCM of 3 and 5).
This period maps naturally to the synodic periods of inner planets: the
ratio of Earth's orbital period to Mercury's (~87.97 days) produces a
beat frequency that aligns with FizzBuzz cycles when sampled at the
correct epoch cadence.

Coordinate transforms between ecliptic, equatorial, and galactic frames
ensure that FizzBuzz evaluations are referenced to the appropriate
celestial coordinate system for the operator's observatory location.

All computations use double-precision floating-point arithmetic with
the standard library math module. No external astronomy libraries
are required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzastronomy import (
    AstronomyMiddlewareError,
    CelestialBodyNotFoundError,
    CoordinateTransformError,
    EphemerisComputationError,
    InvalidOrbitalElementsError,
    KeplerEquationError,
    NBodyIntegrationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Gravitational constant in AU^3 / (solar_mass * day^2)
G_AU = 2.959122082855911e-4
# Earth obliquity (J2000 epoch) in radians
OBLIQUITY_J2000 = math.radians(23.43928)
# Galactic north pole in equatorial coordinates (radians)
GALACTIC_NORTH_RA = math.radians(192.85948)
GALACTIC_NORTH_DEC = math.radians(27.12825)
GALACTIC_CENTER_L = math.radians(32.93192)
# Maximum Kepler equation iterations
KEPLER_MAX_ITER = 100
KEPLER_TOLERANCE = 1e-12
# N-body softening parameter (AU)
SOFTENING_EPSILON = 1e-6


# ============================================================
# Coordinate Frame Enum
# ============================================================


class CoordinateFrame(Enum):
    """Celestial coordinate reference frames supported by FizzAstronomy."""

    ECLIPTIC = auto()
    EQUATORIAL = auto()
    GALACTIC = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass
class Vec3:
    """Three-dimensional vector for positions and velocities."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return self.__mul__(scalar)

    def magnitude(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> Vec3:
        mag = self.magnitude()
        if mag < 1e-15:
            return Vec3(0.0, 0.0, 0.0)
        return Vec3(self.x / mag, self.y / mag, self.z / mag)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z


@dataclass
class OrbitalElements:
    """Keplerian orbital elements for a celestial body.

    These six parameters fully describe a two-body orbit:
    - semi_major_axis: semi-major axis in AU
    - eccentricity: orbital eccentricity [0, 1) for bound orbits
    - inclination: orbital inclination in radians
    - longitude_ascending: longitude of the ascending node in radians
    - argument_periapsis: argument of periapsis in radians
    - mean_anomaly_epoch: mean anomaly at epoch in radians
    """

    semi_major_axis: float
    eccentricity: float
    inclination: float
    longitude_ascending: float
    argument_periapsis: float
    mean_anomaly_epoch: float

    def validate(self) -> None:
        """Validate that orbital elements are physically realizable."""
        if self.semi_major_axis <= 0:
            raise InvalidOrbitalElementsError(
                "semi_major_axis", self.semi_major_axis,
                "Semi-major axis must be positive for a bound orbit"
            )
        if not (0.0 <= self.eccentricity < 1.0):
            raise InvalidOrbitalElementsError(
                "eccentricity", self.eccentricity,
                "Eccentricity must be in [0, 1) for a bound orbit"
            )
        if not (0.0 <= self.inclination <= math.pi):
            raise InvalidOrbitalElementsError(
                "inclination", self.inclination,
                "Inclination must be in [0, pi] radians"
            )


@dataclass
class CelestialBody:
    """A body in the n-body simulation with mass, position, and velocity."""

    name: str
    mass: float  # solar masses
    position: Vec3 = field(default_factory=Vec3)
    velocity: Vec3 = field(default_factory=Vec3)
    elements: Optional[OrbitalElements] = None


@dataclass
class EphemerisRecord:
    """Position and velocity of a body at a specific epoch."""

    body_name: str
    epoch_jd: float
    position: Vec3
    velocity: Vec3
    true_anomaly: float
    distance_au: float


# ============================================================
# Kepler Equation Solver
# ============================================================


class KeplerSolver:
    """Solves Kepler's equation M = E - e*sin(E) via Newton-Raphson.

    The eccentric anomaly E relates the mean anomaly M (which advances
    linearly with time) to the true anomaly (which determines the
    actual angular position on the ellipse). This is the fundamental
    connection between time and orbital position.
    """

    @staticmethod
    def solve(mean_anomaly: float, eccentricity: float) -> float:
        """Solve for eccentric anomaly given mean anomaly and eccentricity.

        Uses Newton-Raphson iteration with Danby's initial guess for
        faster convergence at high eccentricities.
        """
        if eccentricity < 0 or eccentricity >= 1.0:
            raise KeplerEquationError(mean_anomaly, eccentricity)

        # Normalize mean anomaly to [0, 2*pi)
        M = mean_anomaly % (2.0 * math.pi)
        e = eccentricity

        # Danby's initial guess
        E = M + e * math.sin(M) + 0.5 * e * e * math.sin(2.0 * M)

        for _ in range(KEPLER_MAX_ITER):
            f = E - e * math.sin(E) - M
            fp = 1.0 - e * math.cos(E)
            if abs(fp) < 1e-15:
                raise KeplerEquationError(mean_anomaly, eccentricity)
            delta = f / fp
            E -= delta
            if abs(delta) < KEPLER_TOLERANCE:
                return E

        raise EphemerisComputationError(
            "kepler_solver", mean_anomaly, KEPLER_MAX_ITER
        )

    @staticmethod
    def eccentric_to_true_anomaly(E: float, eccentricity: float) -> float:
        """Convert eccentric anomaly to true anomaly."""
        e = eccentricity
        cos_E = math.cos(E)
        sin_E = math.sin(E)
        true_anomaly = math.atan2(
            math.sqrt(1.0 - e * e) * sin_E,
            cos_E - e,
        )
        return true_anomaly % (2.0 * math.pi)


# ============================================================
# Orbital Mechanics
# ============================================================


class OrbitalMechanics:
    """Computes positions and velocities from Keplerian elements.

    Given a set of orbital elements and a time offset from epoch,
    this class propagates the orbit using the two-body solution:
    advance mean anomaly linearly, solve Kepler's equation for
    eccentric anomaly, then convert to Cartesian coordinates.
    """

    @staticmethod
    def orbital_period(semi_major_axis: float, central_mass: float = 1.0) -> float:
        """Compute orbital period in days using Kepler's third law.

        T^2 = (4*pi^2 / G*M) * a^3
        """
        return 2.0 * math.pi * math.sqrt(
            semi_major_axis ** 3 / (G_AU * central_mass)
        )

    @staticmethod
    def position_at_epoch(
        elements: OrbitalElements,
        dt_days: float,
        central_mass: float = 1.0,
    ) -> tuple[Vec3, Vec3]:
        """Compute position and velocity at time dt_days from epoch.

        Returns (position, velocity) in the ecliptic reference frame.
        """
        elements.validate()

        a = elements.semi_major_axis
        e = elements.eccentricity
        i = elements.inclination
        Omega = elements.longitude_ascending
        omega = elements.argument_periapsis

        # Mean motion (radians per day)
        n = math.sqrt(G_AU * central_mass / (a ** 3))

        # Mean anomaly at time t
        M = elements.mean_anomaly_epoch + n * dt_days

        # Solve Kepler's equation
        E = KeplerSolver.solve(M, e)
        nu = KeplerSolver.eccentric_to_true_anomaly(E, e)

        # Distance from central body
        r = a * (1.0 - e * math.cos(E))

        # Position in orbital plane
        x_orb = r * math.cos(nu)
        y_orb = r * math.sin(nu)

        # Velocity in orbital plane
        h = math.sqrt(G_AU * central_mass * a * (1.0 - e * e))
        vx_orb = -h / r * math.sin(nu)
        vy_orb = h / r * (e + math.cos(nu))

        # Rotation matrix elements
        cos_O = math.cos(Omega)
        sin_O = math.sin(Omega)
        cos_w = math.cos(omega)
        sin_w = math.sin(omega)
        cos_i = math.cos(i)
        sin_i = math.sin(i)

        # Transform to ecliptic frame
        px = (cos_O * cos_w - sin_O * sin_w * cos_i) * x_orb + \
             (-cos_O * sin_w - sin_O * cos_w * cos_i) * y_orb
        py = (sin_O * cos_w + cos_O * sin_w * cos_i) * x_orb + \
             (-sin_O * sin_w + cos_O * cos_w * cos_i) * y_orb
        pz = (sin_w * sin_i) * x_orb + (cos_w * sin_i) * y_orb

        vx = (cos_O * cos_w - sin_O * sin_w * cos_i) * vx_orb + \
             (-cos_O * sin_w - sin_O * cos_w * cos_i) * vy_orb
        vy = (sin_O * cos_w + cos_O * sin_w * cos_i) * vx_orb + \
             (-sin_O * sin_w + cos_O * cos_w * cos_i) * vy_orb
        vz = (sin_w * sin_i) * vx_orb + (cos_w * sin_i) * vy_orb

        return Vec3(px, py, pz), Vec3(vx, vy, vz)


# ============================================================
# N-Body Simulator
# ============================================================


class NBodySimulator:
    """Velocity Verlet n-body gravitational integrator.

    Simulates the gravitational interaction of multiple celestial
    bodies using the velocity Verlet method, which is symplectic
    (energy-conserving over long integrations) and second-order
    accurate. A softening parameter prevents singularities at
    close approaches.
    """

    def __init__(self, bodies: list[CelestialBody], softening: float = SOFTENING_EPSILON):
        self.bodies = list(bodies)
        self.softening = softening
        self.time = 0.0

    def _compute_accelerations(self) -> list[Vec3]:
        """Compute gravitational acceleration on each body from all others."""
        n = len(self.bodies)
        accels = [Vec3() for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                dr = self.bodies[j].position - self.bodies[i].position
                dist_sq = dr.dot(dr) + self.softening ** 2
                dist = math.sqrt(dist_sq)

                if dist < self.softening:
                    raise NBodyIntegrationError(
                        self.bodies[i].name,
                        self.bodies[j].name,
                        dist,
                    )

                # F = G * m_i * m_j / r^2, acceleration = F / m
                factor = G_AU / (dist_sq * dist)
                accels[i] = accels[i] + dr * (factor * self.bodies[j].mass)
                accels[j] = accels[j] - dr * (factor * self.bodies[i].mass)

        return accels

    def step(self, dt: float) -> None:
        """Advance the simulation by dt days using velocity Verlet."""
        accels = self._compute_accelerations()

        # Half-kick
        for i, body in enumerate(self.bodies):
            body.velocity = body.velocity + accels[i] * (0.5 * dt)

        # Drift
        for body in self.bodies:
            body.position = body.position + body.velocity * dt

        # Compute new accelerations
        new_accels = self._compute_accelerations()

        # Half-kick
        for i, body in enumerate(self.bodies):
            body.velocity = body.velocity + new_accels[i] * (0.5 * dt)

        self.time += dt

    def total_energy(self) -> float:
        """Compute total mechanical energy (kinetic + potential)."""
        ke = 0.0
        pe = 0.0
        n = len(self.bodies)

        for i in range(n):
            v = self.bodies[i].velocity
            ke += 0.5 * self.bodies[i].mass * v.dot(v)
            for j in range(i + 1, n):
                dr = self.bodies[j].position - self.bodies[i].position
                dist = math.sqrt(dr.dot(dr) + self.softening ** 2)
                pe -= G_AU * self.bodies[i].mass * self.bodies[j].mass / dist

        return ke + pe

    def simulate(self, total_time: float, dt: float) -> list[list[Vec3]]:
        """Run simulation for total_time days, returning position history."""
        steps = max(1, int(total_time / dt))
        history: list[list[Vec3]] = []

        for _ in range(steps):
            self.step(dt)
            snapshot = [Vec3(b.position.x, b.position.y, b.position.z)
                        for b in self.bodies]
            history.append(snapshot)

        return history


# ============================================================
# Ephemeris Catalog
# ============================================================


# Default solar system bodies (simplified J2000 elements)
_DEFAULT_BODIES = {
    "Mercury": OrbitalElements(0.387098, 0.205630, math.radians(7.005), math.radians(48.331), math.radians(29.124), math.radians(174.796)),
    "Venus": OrbitalElements(0.723332, 0.006772, math.radians(3.394), math.radians(76.680), math.radians(54.884), math.radians(50.115)),
    "Earth": OrbitalElements(1.000001, 0.016709, math.radians(0.000), math.radians(0.0), math.radians(102.937), math.radians(357.517)),
    "Mars": OrbitalElements(1.523679, 0.093401, math.radians(1.850), math.radians(49.558), math.radians(286.502), math.radians(19.373)),
    "Jupiter": OrbitalElements(5.202887, 0.048498, math.radians(1.303), math.radians(100.464), math.radians(273.867), math.radians(20.020)),
    "Saturn": OrbitalElements(9.536675, 0.054151, math.radians(2.485), math.radians(113.665), math.radians(339.392), math.radians(317.020)),
}


class EphemerisCatalog:
    """Catalog of celestial bodies with ephemeris computation.

    Maintains Keplerian orbital elements for known bodies and computes
    their positions at arbitrary epochs. The catalog is pre-loaded with
    simplified J2000 elements for the inner and outer planets.
    """

    def __init__(self) -> None:
        self._bodies: dict[str, OrbitalElements] = dict(_DEFAULT_BODIES)

    def register_body(self, name: str, elements: OrbitalElements) -> None:
        """Register a new celestial body or update existing elements."""
        elements.validate()
        self._bodies[name] = elements
        logger.info("Registered celestial body '%s' in ephemeris catalog", name)

    def get_elements(self, name: str) -> OrbitalElements:
        """Retrieve orbital elements for a named body."""
        if name not in self._bodies:
            raise CelestialBodyNotFoundError(name)
        return self._bodies[name]

    def compute_ephemeris(
        self, body_name: str, epoch_jd: float, reference_epoch_jd: float = 2451545.0
    ) -> EphemerisRecord:
        """Compute position and velocity of a body at a Julian date.

        The reference epoch defaults to J2000.0 (JD 2451545.0).
        """
        elements = self.get_elements(body_name)
        dt_days = epoch_jd - reference_epoch_jd

        position, velocity = OrbitalMechanics.position_at_epoch(elements, dt_days)

        E = KeplerSolver.solve(
            elements.mean_anomaly_epoch + math.sqrt(G_AU / elements.semi_major_axis ** 3) * dt_days,
            elements.eccentricity,
        )
        nu = KeplerSolver.eccentric_to_true_anomaly(E, elements.eccentricity)
        distance = position.magnitude()

        return EphemerisRecord(
            body_name=body_name,
            epoch_jd=epoch_jd,
            position=position,
            velocity=velocity,
            true_anomaly=nu,
            distance_au=distance,
        )

    @property
    def body_names(self) -> list[str]:
        """List all registered body names."""
        return list(self._bodies.keys())


# ============================================================
# Coordinate Transforms
# ============================================================


class CoordinateTransformer:
    """Transforms positions between ecliptic, equatorial, and galactic frames.

    The ecliptic frame is the fundamental plane of the solar system.
    The equatorial frame is tilted by the obliquity of the ecliptic
    (~23.44 degrees). The galactic frame is defined by the plane of
    the Milky Way.
    """

    @staticmethod
    def ecliptic_to_equatorial(pos: Vec3, obliquity: float = OBLIQUITY_J2000) -> Vec3:
        """Rotate from ecliptic to equatorial coordinates."""
        cos_e = math.cos(obliquity)
        sin_e = math.sin(obliquity)
        return Vec3(
            pos.x,
            pos.y * cos_e - pos.z * sin_e,
            pos.y * sin_e + pos.z * cos_e,
        )

    @staticmethod
    def equatorial_to_ecliptic(pos: Vec3, obliquity: float = OBLIQUITY_J2000) -> Vec3:
        """Rotate from equatorial to ecliptic coordinates."""
        cos_e = math.cos(obliquity)
        sin_e = math.sin(obliquity)
        return Vec3(
            pos.x,
            pos.y * cos_e + pos.z * sin_e,
            -pos.y * sin_e + pos.z * cos_e,
        )

    @staticmethod
    def equatorial_to_galactic(pos: Vec3) -> Vec3:
        """Transform from equatorial to galactic coordinates.

        Uses the standard IAU rotation defined by the galactic north
        pole direction and the galactic center longitude.
        """
        # Simplified rotation using the standard Euler angles
        alpha_gp = GALACTIC_NORTH_RA
        delta_gp = GALACTIC_NORTH_DEC
        l_omega = GALACTIC_CENTER_L

        cos_a = math.cos(alpha_gp)
        sin_a = math.sin(alpha_gp)
        cos_d = math.cos(delta_gp)
        sin_d = math.sin(delta_gp)
        cos_l = math.cos(l_omega)
        sin_l = math.sin(l_omega)

        # Rotation matrix R = R_z(l_omega) * R_x(pi/2 - delta_gp) * R_z(alpha_gp)
        x1 = cos_a * pos.x + sin_a * pos.y
        y1 = -sin_a * pos.x + cos_a * pos.y
        z1 = pos.z

        x2 = x1
        y2 = sin_d * y1 + cos_d * z1
        z2 = -cos_d * y1 + sin_d * z1

        xg = cos_l * x2 + sin_l * y2
        yg = -sin_l * x2 + cos_l * y2
        zg = z2

        return Vec3(xg, yg, zg)

    @staticmethod
    def transform(
        pos: Vec3,
        source: CoordinateFrame,
        target: CoordinateFrame,
    ) -> Vec3:
        """Transform position between any two supported coordinate frames."""
        if source == target:
            return pos

        # Convert to equatorial as intermediate
        if source == CoordinateFrame.ECLIPTIC:
            eq = CoordinateTransformer.ecliptic_to_equatorial(pos)
        elif source == CoordinateFrame.EQUATORIAL:
            eq = pos
        elif source == CoordinateFrame.GALACTIC:
            raise CoordinateTransformError(
                source.name, target.name,
                "Galactic-to-equatorial inverse transform not yet implemented"
            )
        else:
            raise CoordinateTransformError(source.name, target.name, "Unknown source frame")

        # Convert from equatorial to target
        if target == CoordinateFrame.EQUATORIAL:
            return eq
        elif target == CoordinateFrame.ECLIPTIC:
            return CoordinateTransformer.equatorial_to_ecliptic(eq)
        elif target == CoordinateFrame.GALACTIC:
            return CoordinateTransformer.equatorial_to_galactic(eq)
        else:
            raise CoordinateTransformError(source.name, target.name, "Unknown target frame")


# ============================================================
# Gravitational Context
# ============================================================


class GravitationalContext:
    """Computes the gravitational influence on a FizzBuzz evaluation.

    The combined gravitational tidal force from all cataloged bodies
    at a given epoch produces a dimensionless weighting factor that
    modulates the confidence of divisibility determinations. Stronger
    tidal forces increase classification uncertainty.
    """

    def __init__(self, catalog: EphemerisCatalog) -> None:
        self._catalog = catalog

    def tidal_factor(self, epoch_jd: float) -> float:
        """Compute the aggregate tidal factor at the given Julian date.

        The tidal factor is the sum of (mass / distance^3) for all
        bodies, normalized to produce a value in [0, 1].
        """
        total = 0.0
        for name in self._catalog.body_names:
            try:
                record = self._catalog.compute_ephemeris(name, epoch_jd)
                if record.distance_au > 0:
                    total += 1.0 / (record.distance_au ** 3)
            except Exception:
                logger.warning("Skipping body '%s' in tidal computation", name)

        # Normalize using a reference tidal sum
        reference = 1000.0  # Empirical normalization constant
        return min(1.0, total / reference)

    def dominant_body(self, epoch_jd: float) -> str:
        """Determine which body exerts the strongest tidal influence."""
        best_name = ""
        best_influence = -1.0

        for name in self._catalog.body_names:
            try:
                record = self._catalog.compute_ephemeris(name, epoch_jd)
                if record.distance_au > 0:
                    influence = 1.0 / (record.distance_au ** 3)
                    if influence > best_influence:
                        best_influence = influence
                        best_name = name
            except Exception:
                continue

        return best_name


# ============================================================
# FizzAstronomy Middleware
# ============================================================


class AstronomyMiddleware(IMiddleware):
    """Injects celestial mechanics context into the FizzBuzz pipeline.

    For each number evaluated, the middleware computes the current
    gravitational tidal factor and dominant celestial body, injecting
    this data into the processing context metadata. Downstream
    middleware and formatters can use this information for
    gravitationally-aware output formatting.
    """

    def __init__(
        self,
        catalog: EphemerisCatalog,
        base_epoch_jd: float = 2451545.0,
        epoch_step_days: float = 1.0,
        coordinate_frame: CoordinateFrame = CoordinateFrame.ECLIPTIC,
    ) -> None:
        self._catalog = catalog
        self._grav_ctx = GravitationalContext(catalog)
        self._base_epoch = base_epoch_jd
        self._epoch_step = epoch_step_days
        self._frame = coordinate_frame

    def get_name(self) -> str:
        return "fizzastronomy"

    def get_priority(self) -> int:
        return 274

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Inject celestial context and delegate to next handler."""
        try:
            epoch = self._base_epoch + context.number * self._epoch_step
            tidal = self._grav_ctx.tidal_factor(epoch)
            dominant = self._grav_ctx.dominant_body(epoch)

            context.metadata["astronomy_epoch_jd"] = epoch
            context.metadata["astronomy_tidal_factor"] = tidal
            context.metadata["astronomy_dominant_body"] = dominant
            context.metadata["astronomy_coordinate_frame"] = self._frame.name

            logger.debug(
                "FizzAstronomy: number=%d epoch=%.2f tidal=%.6f dominant=%s",
                context.number, epoch, tidal, dominant,
            )
        except Exception as exc:
            logger.error("FizzAstronomy middleware error: %s", exc)
            context.metadata["astronomy_error"] = str(exc)

        return next_handler(context)

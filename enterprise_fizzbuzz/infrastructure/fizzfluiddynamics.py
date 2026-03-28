"""
Enterprise FizzBuzz Platform - FizzFluidDynamics: Computational Fluid Dynamics Engine

Implements a Navier-Stokes solver, Reynolds number classification,
k-epsilon turbulence modeling, boundary layer analysis, and drag/lift
coefficient computation for FizzBuzz evaluation sequences.

The integers flowing through the FizzBuzz pipeline constitute a
one-dimensional compressible flow. Each number carries momentum
proportional to its magnitude, and the classification rules act as
flow obstructions that impose boundary conditions. Numbers divisible
by 3 create vortex structures (Fizz vortices), numbers divisible by 5
generate pressure waves (Buzz shocks), and FizzBuzz numbers produce
turbulent wakes that require full Reynolds-averaged Navier-Stokes
treatment.

Without proper CFD analysis, the platform cannot guarantee that the
evaluation pipeline operates within acceptable pressure drop limits
or that flow separation does not occur at the Fizz-Buzz interface.
These are fundamental fluid-mechanical concerns that directly impact
the throughput and reliability of the classification system.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Kinematic viscosity of air at STP (m^2/s)
NU_AIR = 1.516e-5

# Density of air at STP (kg/m^3)
RHO_AIR = 1.225

# Dynamic viscosity of air at STP (Pa*s)
MU_AIR = RHO_AIR * NU_AIR

# Turbulence model constants (standard k-epsilon)
C_MU = 0.09
C_EPSILON_1 = 1.44
C_EPSILON_2 = 1.92
SIGMA_K = 1.0
SIGMA_EPSILON = 1.3
KAPPA = 0.41  # von Karman constant

# Reynolds number thresholds
RE_LAMINAR_MAX = 2300.0
RE_TURBULENT_MIN = 4000.0

# Default solver settings
DEFAULT_MAX_ITERATIONS = 500
DEFAULT_TOLERANCE = 1.0e-6
DEFAULT_CFL_MAX = 1.0


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FlowRegime(Enum):
    """Classification of flow regime by Reynolds number."""
    LAMINAR = auto()
    TRANSITIONAL = auto()
    TURBULENT = auto()


class BoundaryCondition(Enum):
    """Types of boundary conditions."""
    NO_SLIP = auto()
    FREE_SLIP = auto()
    INLET_VELOCITY = auto()
    OUTLET_PRESSURE = auto()
    SYMMETRY = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class FlowState:
    """State of the flow field at a single point."""
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    pressure: float = 101325.0  # Pa (atmospheric)
    density: float = RHO_AIR
    temperature: float = 293.15  # K
    turbulent_ke: float = 0.0  # k (m^2/s^2)
    dissipation_rate: float = 0.0  # epsilon (m^2/s^3)

    @property
    def velocity_magnitude(self) -> float:
        return math.sqrt(self.velocity_x ** 2 + self.velocity_y ** 2)

    @property
    def mach_number(self) -> float:
        speed_of_sound = 343.0  # m/s at STP
        vel = self.velocity_magnitude
        return vel / speed_of_sound if speed_of_sound > 0 else 0.0

    @property
    def turbulence_intensity(self) -> float:
        if self.velocity_magnitude < 1e-10:
            return 0.0
        return math.sqrt(2.0 * self.turbulent_ke / 3.0) / self.velocity_magnitude


@dataclass
class ReynoldsAnalysis:
    """Reynolds number analysis results."""
    reynolds_number: float = 0.0
    flow_regime: FlowRegime = FlowRegime.LAMINAR
    characteristic_length: float = 1.0
    velocity: float = 0.0
    viscosity: float = NU_AIR


@dataclass
class BoundaryLayerResult:
    """Boundary layer analysis at a single station."""
    x_position: float = 0.0
    thickness_99: float = 0.0  # delta_99
    displacement_thickness: float = 0.0  # delta*
    momentum_thickness: float = 0.0  # theta
    wall_shear_stress: float = 0.0  # tau_w (Pa)
    shape_factor: float = 0.0  # H = delta*/theta
    cf: float = 0.0  # Skin friction coefficient


@dataclass
class DragLiftResult:
    """Aerodynamic force coefficients."""
    cd: float = 0.0  # Drag coefficient
    cl: float = 0.0  # Lift coefficient
    cd_pressure: float = 0.0
    cd_friction: float = 0.0
    reynolds: float = 0.0
    reference_area: float = 1.0


@dataclass
class KEpsilonState:
    """State of the k-epsilon turbulence model."""
    k: float = 0.0
    epsilon: float = 0.0
    mu_t: float = 0.0  # Turbulent viscosity
    production: float = 0.0
    dissipation: float = 0.0

    @property
    def is_physical(self) -> bool:
        return self.k >= 0 and self.epsilon > 0


@dataclass
class CFDResult:
    """Complete CFD analysis result for a single number."""
    reynolds: ReynoldsAnalysis = field(default_factory=ReynoldsAnalysis)
    flow_state: FlowState = field(default_factory=FlowState)
    boundary_layer: BoundaryLayerResult = field(default_factory=BoundaryLayerResult)
    drag_lift: DragLiftResult = field(default_factory=DragLiftResult)
    turbulence: KEpsilonState = field(default_factory=KEpsilonState)
    converged: bool = False
    iterations: int = 0
    residual: float = 0.0


# ---------------------------------------------------------------------------
# Reynolds Number Analyzer
# ---------------------------------------------------------------------------


class ReynoldsAnalyzer:
    """Computes Reynolds number and classifies flow regime.

    The characteristic velocity is derived from the number magnitude,
    and the characteristic length is the string length of the FizzBuzz
    output. This ensures that larger numbers and longer output strings
    push the flow into the turbulent regime, which is physically
    correct since they carry more momentum.
    """

    def analyze(
        self,
        velocity: float,
        length: float,
        viscosity: float = NU_AIR,
    ) -> ReynoldsAnalysis:
        """Compute Reynolds number and classify flow regime."""
        if viscosity <= 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzfluiddynamics import (
                ReynoldsNumberError,
            )
            raise ReynoldsNumberError(0.0, "zero viscosity")

        re = velocity * length / viscosity

        if re < RE_LAMINAR_MAX:
            regime = FlowRegime.LAMINAR
        elif re < RE_TURBULENT_MIN:
            regime = FlowRegime.TRANSITIONAL
        else:
            regime = FlowRegime.TURBULENT

        return ReynoldsAnalysis(
            reynolds_number=re,
            flow_regime=regime,
            characteristic_length=length,
            velocity=velocity,
            viscosity=viscosity,
        )


# ---------------------------------------------------------------------------
# k-epsilon Turbulence Model
# ---------------------------------------------------------------------------


class KEpsilonModel:
    """Standard k-epsilon turbulence model.

    Solves the transport equations for turbulent kinetic energy (k) and
    its dissipation rate (epsilon). The eddy viscosity is computed as
    mu_t = C_mu * rho * k^2 / epsilon.
    """

    def compute(
        self,
        velocity: float,
        length: float,
        turbulence_intensity: float = 0.05,
    ) -> KEpsilonState:
        """Compute turbulence state for given flow conditions."""
        k = 1.5 * (velocity * turbulence_intensity) ** 2
        k = max(k, 1e-10)

        mixing_length = 0.07 * length
        epsilon = C_MU ** 0.75 * k ** 1.5 / mixing_length if mixing_length > 0 else 1e-10
        epsilon = max(epsilon, 1e-10)

        mu_t = C_MU * RHO_AIR * k ** 2 / epsilon

        production = mu_t * (velocity / length) ** 2 if length > 0 else 0.0

        state = KEpsilonState(
            k=k,
            epsilon=epsilon,
            mu_t=mu_t,
            production=production,
            dissipation=RHO_AIR * epsilon,
        )

        if not state.is_physical:
            from enterprise_fizzbuzz.domain.exceptions.fizzfluiddynamics import (
                TurbulenceModelError,
            )
            if k < 0:
                raise TurbulenceModelError("k-epsilon", "k", k)
            if epsilon <= 0:
                raise TurbulenceModelError("k-epsilon", "epsilon", epsilon)

        return state


# ---------------------------------------------------------------------------
# Boundary Layer Solver
# ---------------------------------------------------------------------------


class BoundaryLayerSolver:
    """Computes boundary layer properties using the Blasius solution.

    For laminar flow over a flat plate, the Blasius solution gives
    exact values for boundary layer thickness, skin friction, and
    displacement thickness. For turbulent flow, the 1/7th power law
    profile is used.
    """

    def solve(
        self,
        x_position: float,
        freestream_velocity: float,
        reynolds_x: float,
    ) -> BoundaryLayerResult:
        """Compute boundary layer properties at position x."""
        if reynolds_x <= 0 or x_position <= 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzfluiddynamics import (
                BoundaryLayerError,
            )
            raise BoundaryLayerError(
                x_position, "non-positive Reynolds number or position"
            )

        if reynolds_x < 5e5:
            # Laminar (Blasius)
            delta_99 = 5.0 * x_position / math.sqrt(reynolds_x)
            delta_star = 1.7208 * x_position / math.sqrt(reynolds_x)
            theta = 0.664 * x_position / math.sqrt(reynolds_x)
            cf = 0.664 / math.sqrt(reynolds_x)
        else:
            # Turbulent (1/7th power law)
            delta_99 = 0.37 * x_position * reynolds_x ** (-0.2)
            delta_star = delta_99 / 8.0
            theta = 7.0 * delta_99 / 72.0
            cf = 0.0592 * reynolds_x ** (-0.2)

        shape_factor = delta_star / theta if theta > 0 else 0.0
        tau_w = 0.5 * RHO_AIR * freestream_velocity ** 2 * cf

        return BoundaryLayerResult(
            x_position=x_position,
            thickness_99=delta_99,
            displacement_thickness=delta_star,
            momentum_thickness=theta,
            wall_shear_stress=tau_w,
            shape_factor=shape_factor,
            cf=cf,
        )


# ---------------------------------------------------------------------------
# Drag/Lift Calculator
# ---------------------------------------------------------------------------


class DragLiftCalculator:
    """Computes drag and lift coefficients for FizzBuzz numbers.

    Each number is modeled as a bluff body in cross-flow. The shape
    is determined by the FizzBuzz classification: Fizz numbers are
    streamlined (low Cd), Buzz numbers are blunt (high Cd), and
    FizzBuzz numbers exhibit vortex-induced oscillations.
    """

    def compute(
        self,
        reynolds: float,
        is_fizz: bool,
        is_buzz: bool,
    ) -> DragLiftResult:
        """Compute drag and lift coefficients."""
        if reynolds <= 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzfluiddynamics import (
                DragLiftError,
            )
            raise DragLiftError("drag", "non-positive Reynolds number")

        # Base Cd from Morrison correlation for sphere
        if reynolds < 1.0:
            cd_base = 24.0 / reynolds  # Stokes drag
        elif reynolds < 1000.0:
            cd_base = 24.0 / reynolds * (1.0 + 0.15 * reynolds ** 0.687)
        elif reynolds < 2e5:
            cd_base = 0.44  # Newton regime
        else:
            cd_base = 0.1  # Drag crisis

        # Modify based on classification
        if is_fizz and is_buzz:
            cd = cd_base * 1.5  # FizzBuzz creates turbulent wake
            cl = 0.3 * math.sin(reynolds / 1000.0)  # Vortex shedding
        elif is_fizz:
            cd = cd_base * 0.7  # Streamlined
            cl = 0.1
        elif is_buzz:
            cd = cd_base * 1.3  # Blunt
            cl = 0.05
        else:
            cd = cd_base
            cl = 0.0

        cd_friction = 1.328 / math.sqrt(reynolds) if reynolds > 0 else 0.0
        cd_pressure = max(0.0, cd - cd_friction)

        return DragLiftResult(
            cd=cd,
            cl=cl,
            cd_pressure=cd_pressure,
            cd_friction=cd_friction,
            reynolds=reynolds,
        )


# ---------------------------------------------------------------------------
# Navier-Stokes Solver (Simplified SIMPLE Algorithm)
# ---------------------------------------------------------------------------


class NavierStokesSolver:
    """Simplified Navier-Stokes solver using the SIMPLE algorithm.

    Solves the steady incompressible Navier-Stokes equations in a
    1D channel representing the FizzBuzz evaluation pipeline. The
    pressure-velocity coupling is handled by the SIMPLE (Semi-Implicit
    Method for Pressure Linked Equations) algorithm.
    """

    def __init__(
        self,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        self._max_iter = max_iterations
        self._tolerance = tolerance

    def solve(
        self,
        inlet_velocity: float,
        channel_length: float,
        viscosity: float = NU_AIR,
    ) -> tuple[FlowState, int, float]:
        """Solve for the flow state in the channel."""
        u = inlet_velocity
        p = 101325.0
        residual = float("inf")

        for iteration in range(1, self._max_iter + 1):
            re_local = abs(u) * channel_length / viscosity if viscosity > 0 else 0.0

            # Pressure drop (Hagen-Poiseuille for laminar, Darcy-Weisbach for turbulent)
            if re_local < RE_LAMINAR_MAX and re_local > 0:
                f = 64.0 / re_local
            elif re_local > 0:
                f = 0.316 * re_local ** (-0.25)  # Blasius
            else:
                f = 0.0

            dp = f * channel_length * RHO_AIR * u ** 2 / (2.0 * channel_length) if channel_length > 0 else 0.0

            p_new = 101325.0 - dp
            u_new = inlet_velocity * (1.0 - 0.01 * f)

            residual = abs(u_new - u) + abs(p_new - p) / 101325.0
            u = u_new
            p = p_new

            if residual < self._tolerance:
                return (
                    FlowState(velocity_x=u, pressure=p),
                    iteration,
                    residual,
                )

        from enterprise_fizzbuzz.domain.exceptions.fizzfluiddynamics import (
            NavierStokesConvergenceError,
        )
        raise NavierStokesConvergenceError(residual, self._tolerance, self._max_iter)


# ---------------------------------------------------------------------------
# CFD Engine
# ---------------------------------------------------------------------------


class CFDEngine:
    """Integrates all CFD analysis components.

    Performs Reynolds number analysis, turbulence modeling, boundary
    layer computation, drag/lift estimation, and Navier-Stokes solution
    for each FizzBuzz evaluation number.
    """

    def __init__(self) -> None:
        self.reynolds_analyzer = ReynoldsAnalyzer()
        self.ke_model = KEpsilonModel()
        self.bl_solver = BoundaryLayerSolver()
        self.drag_lift_calc = DragLiftCalculator()
        self.ns_solver = NavierStokesSolver()
        self._analysis_count = 0

    def analyze_number(
        self, number: int, is_fizz: bool, is_buzz: bool
    ) -> CFDResult:
        """Perform complete CFD analysis for a FizzBuzz number."""
        self._analysis_count += 1

        # Characteristic velocity proportional to number magnitude
        velocity = float(abs(number)) * 0.1 + 1.0
        length = 0.1  # Characteristic length (m)

        reynolds = self.reynolds_analyzer.analyze(velocity, length)

        # Turbulence model
        turbulence = KEpsilonState()
        if reynolds.flow_regime == FlowRegime.TURBULENT:
            turbulence = self.ke_model.compute(velocity, length)

        # Boundary layer
        re_x = velocity * length / NU_AIR
        boundary_layer = self.bl_solver.solve(length, velocity, re_x)

        # Drag and lift
        drag_lift = self.drag_lift_calc.compute(
            reynolds.reynolds_number, is_fizz, is_buzz
        )

        # Navier-Stokes
        try:
            flow_state, iterations, residual = self.ns_solver.solve(
                velocity, length
            )
            converged = True
        except Exception:
            flow_state = FlowState(velocity_x=velocity)
            iterations = 0
            residual = float("inf")
            converged = False

        return CFDResult(
            reynolds=reynolds,
            flow_state=flow_state,
            boundary_layer=boundary_layer,
            drag_lift=drag_lift,
            turbulence=turbulence,
            converged=converged,
            iterations=iterations,
            residual=residual,
        )

    @property
    def analysis_count(self) -> int:
        return self._analysis_count


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class FluidDynamicsMiddleware(IMiddleware):
    """Middleware that performs CFD analysis for each FizzBuzz evaluation.

    Each number is treated as a flow obstruction in the evaluation
    pipeline. The resulting pressure field, velocity distribution,
    and turbulence state are attached to the processing context.

    Priority 293 positions this in the physical sciences tier.
    """

    def __init__(self) -> None:
        self._engine = CFDEngine()
        self._evaluations = 0

    def get_name(self) -> str:
        return "fizzfluiddynamics"

    def get_priority(self) -> int:
        return 293

    @property
    def engine(self) -> CFDEngine:
        return self._engine

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
            cfd = self._engine.analyze_number(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["fluid_dynamics"] = {
                "reynolds_number": round(cfd.reynolds.reynolds_number, 2),
                "flow_regime": cfd.reynolds.flow_regime.name,
                "velocity_m_s": round(cfd.flow_state.velocity_x, 4),
                "pressure_pa": round(cfd.flow_state.pressure, 2),
                "mach_number": round(cfd.flow_state.mach_number, 6),
                "bl_thickness_m": round(cfd.boundary_layer.thickness_99, 6),
                "cd": round(cfd.drag_lift.cd, 4),
                "cl": round(cfd.drag_lift.cl, 4),
                "converged": cfd.converged,
                "turbulent_ke": round(cfd.turbulence.k, 6),
            }

            logger.debug(
                "FizzFluidDynamics: number=%d Re=%.1f regime=%s Cd=%.4f",
                number,
                cfd.reynolds.reynolds_number,
                cfd.reynolds.flow_regime.name,
                cfd.drag_lift.cd,
            )

        except Exception:
            logger.exception(
                "FizzFluidDynamics: analysis failed for number %d", number
            )

        return result

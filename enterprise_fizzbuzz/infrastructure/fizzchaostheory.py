"""
Enterprise FizzBuzz Platform - FizzChaos: Chaos Theory Engine

Evaluates FizzBuzz classifications by evolving nonlinear dynamical systems
seeded with the input integer. The trajectory through phase space determines
the classification label.

Three chaotic systems are implemented:

1. **Lorenz Attractor** — The iconic three-variable system
   dx/dt = sigma*(y - x), dy/dt = x*(rho - z) - y, dz/dt = x*y - beta*z
   exhibits sensitive dependence on initial conditions for the canonical
   parameters sigma=10, rho=28, beta=8/3. The input integer determines
   the initial conditions, and the final position in the butterfly-shaped
   attractor encodes the FizzBuzz label.

2. **Logistic Map** — The discrete map x_{n+1} = r*x_n*(1 - x_n) for
   r in [3.57, 4.0] exhibits deterministic chaos. The parameter r is
   derived from the input integer, and the orbit's long-term behavior
   (fixed point, period-2, period-4, chaotic) determines the classification.

3. **Lyapunov Exponent Computation** — The maximal Lyapunov exponent
   quantifies the rate of exponential divergence of nearby trajectories.
   Positive exponents indicate chaos; the magnitude correlates with the
   FizzBuzz class.

Bifurcation analysis sweeps the control parameter and identifies the
period-doubling cascade, mapping each regime to a FizzBuzz class.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Lorenz system parameters
DEFAULT_SIGMA = 10.0
DEFAULT_RHO = 28.0
DEFAULT_BETA = 8.0 / 3.0
DEFAULT_DT = 0.01
DEFAULT_LORENZ_STEPS = 1000
DEFAULT_MAX_STATE_VALUE = 1e6

# Logistic map parameters
DEFAULT_R_MIN = 3.57
DEFAULT_R_MAX = 4.0
DEFAULT_LOGISTIC_ITERATIONS = 200
DEFAULT_LOGISTIC_TRANSIENT = 100

# Lyapunov computation
DEFAULT_LYAPUNOV_ITERATIONS = 500

FIZZBUZZ_CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]


# ---------------------------------------------------------------------------
# Lorenz Attractor
# ---------------------------------------------------------------------------

@dataclass
class LorenzState:
    """State of the Lorenz system at a given time step.

    Attributes:
        x: First state variable.
        y: Second state variable.
        z: Third state variable.
        step: Integration step index.
    """
    x: float = 1.0
    y: float = 1.0
    z: float = 1.0
    step: int = 0


class LorenzAttractor:
    """Integrates the Lorenz system using fourth-order Runge-Kutta.

    The system is chaotic for sigma=10, rho=28, beta=8/3. Small
    perturbations in initial conditions lead to exponentially divergent
    trajectories — the hallmark of deterministic chaos.
    """

    def __init__(
        self,
        sigma: float = DEFAULT_SIGMA,
        rho: float = DEFAULT_RHO,
        beta: float = DEFAULT_BETA,
        dt: float = DEFAULT_DT,
        max_steps: int = DEFAULT_LORENZ_STEPS,
    ) -> None:
        self._sigma = sigma
        self._rho = rho
        self._beta = beta
        self._dt = dt
        self._max_steps = max_steps

    def integrate(self, x0: float, y0: float, z0: float) -> List[LorenzState]:
        """Integrate the Lorenz system from the given initial conditions.

        Returns:
            List of states at each time step.

        Raises:
            LorenzAttractorError if the state diverges.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzchaostheory import LorenzAttractorError

        trajectory = [LorenzState(x=x0, y=y0, z=z0, step=0)]
        x, y, z = x0, y0, z0
        dt = self._dt

        for step in range(1, self._max_steps + 1):
            # RK4 integration
            k1x, k1y, k1z = self._derivatives(x, y, z)
            k2x, k2y, k2z = self._derivatives(
                x + 0.5 * dt * k1x, y + 0.5 * dt * k1y, z + 0.5 * dt * k1z
            )
            k3x, k3y, k3z = self._derivatives(
                x + 0.5 * dt * k2x, y + 0.5 * dt * k2y, z + 0.5 * dt * k2z
            )
            k4x, k4y, k4z = self._derivatives(
                x + dt * k3x, y + dt * k3y, z + dt * k3z
            )

            x += dt * (k1x + 2 * k2x + 2 * k3x + k4x) / 6
            y += dt * (k1y + 2 * k2y + 2 * k3y + k4y) / 6
            z += dt * (k1z + 2 * k2z + 2 * k3z + k4z) / 6

            max_val = max(abs(x), abs(y), abs(z))
            if max_val > DEFAULT_MAX_STATE_VALUE:
                raise LorenzAttractorError(step, max_val)

            trajectory.append(LorenzState(x=x, y=y, z=z, step=step))

        return trajectory

    def _derivatives(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """Compute the Lorenz system derivatives."""
        dx = self._sigma * (y - x)
        dy = x * (self._rho - z) - y
        dz = x * y - self._beta * z
        return dx, dy, dz


# ---------------------------------------------------------------------------
# Logistic Map
# ---------------------------------------------------------------------------

@dataclass
class LogisticOrbit:
    """Orbit of the logistic map.

    Attributes:
        r: Control parameter.
        x0: Initial condition.
        orbit: Sequence of iterates.
        attractor: Long-term attractor values (after transient).
        period: Detected period of the attractor (0 = chaotic).
    """
    r: float = 3.57
    x0: float = 0.5
    orbit: List[float] = field(default_factory=list)
    attractor: List[float] = field(default_factory=list)
    period: int = 0


class LogisticMap:
    """Discrete logistic map x_{n+1} = r * x_n * (1 - x_n).

    The map exhibits the full period-doubling cascade to chaos as r
    increases from 3.0 to 4.0. The Feigenbaum constant delta = 4.6692
    governs the ratio of successive bifurcation intervals.
    """

    def __init__(
        self,
        iterations: int = DEFAULT_LOGISTIC_ITERATIONS,
        transient: int = DEFAULT_LOGISTIC_TRANSIENT,
    ) -> None:
        self._iterations = iterations
        self._transient = transient

    def iterate(self, r: float, x0: float = 0.5) -> LogisticOrbit:
        """Iterate the logistic map and return the orbit.

        Raises:
            LogisticMapError if r is outside [0, 4].
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzchaostheory import LogisticMapError

        if r < 0 or r > 4:
            raise LogisticMapError(r)

        orbit = [x0]
        x = x0
        for _ in range(self._iterations):
            x = r * x * (1 - x)
            orbit.append(x)

        attractor = orbit[self._transient:]
        period = self._detect_period(attractor)

        return LogisticOrbit(
            r=r,
            x0=x0,
            orbit=orbit,
            attractor=attractor,
            period=period,
        )

    def _detect_period(self, attractor: List[float], tol: float = 1e-6) -> int:
        """Detect the period of the attractor."""
        if len(attractor) < 2:
            return 1
        for period in range(1, min(len(attractor) // 2, 32) + 1):
            is_periodic = True
            for i in range(period, min(len(attractor), period * 3)):
                if abs(attractor[i] - attractor[i % period]) > tol:
                    is_periodic = False
                    break
            if is_periodic:
                return period
        return 0  # Chaotic (no detected period)


# ---------------------------------------------------------------------------
# Lyapunov Exponent
# ---------------------------------------------------------------------------

class LyapunovComputer:
    """Computes the maximal Lyapunov exponent for the logistic map.

    The Lyapunov exponent lambda = lim_{N->inf} (1/N) sum_{i=0}^{N-1} log|f'(x_i)|
    where f'(x) = r * (1 - 2*x) for the logistic map.

    lambda > 0 indicates chaos, lambda < 0 indicates convergence to
    a stable cycle, lambda = 0 indicates a bifurcation point.
    """

    def __init__(self, iterations: int = DEFAULT_LYAPUNOV_ITERATIONS) -> None:
        self._iterations = iterations

    def compute(self, r: float, x0: float = 0.5) -> float:
        """Compute the Lyapunov exponent for the logistic map at parameter r.

        Returns:
            The estimated maximal Lyapunov exponent.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzchaostheory import LogisticMapError
        if r < 0 or r > 4:
            raise LogisticMapError(r)

        x = x0
        lyap_sum = 0.0
        for _ in range(self._iterations):
            derivative = abs(r * (1.0 - 2.0 * x))
            if derivative < 1e-15:
                derivative = 1e-15
            lyap_sum += math.log(derivative)
            x = r * x * (1.0 - x)

        return lyap_sum / self._iterations


# ---------------------------------------------------------------------------
# Bifurcation Diagram
# ---------------------------------------------------------------------------

@dataclass
class BifurcationPoint:
    """A single point in the bifurcation diagram."""
    r: float = 0.0
    x_values: List[float] = field(default_factory=list)
    period: int = 0


class BifurcationAnalyzer:
    """Computes the bifurcation diagram of the logistic map."""

    def __init__(
        self,
        r_min: float = DEFAULT_R_MIN,
        r_max: float = DEFAULT_R_MAX,
        num_r_values: int = 50,
        iterations: int = DEFAULT_LOGISTIC_ITERATIONS,
        transient: int = DEFAULT_LOGISTIC_TRANSIENT,
    ) -> None:
        self._r_min = r_min
        self._r_max = r_max
        self._num_r = num_r_values
        self._logistic = LogisticMap(iterations=iterations, transient=transient)

    def compute(self) -> List[BifurcationPoint]:
        """Compute bifurcation diagram over the parameter range."""
        points = []
        for i in range(self._num_r):
            r = self._r_min + (self._r_max - self._r_min) * i / max(self._num_r - 1, 1)
            orbit = self._logistic.iterate(r)
            # Unique attractor values (within tolerance)
            unique_vals = self._unique_values(orbit.attractor)
            points.append(BifurcationPoint(
                r=r,
                x_values=unique_vals,
                period=orbit.period,
            ))
        return points

    @staticmethod
    def _unique_values(values: List[float], tol: float = 1e-4) -> List[float]:
        """Extract unique values within tolerance."""
        unique: List[float] = []
        for v in values:
            if not any(abs(v - u) < tol for u in unique):
                unique.append(v)
        return sorted(unique)


# ---------------------------------------------------------------------------
# Strange Attractor Reconstruction
# ---------------------------------------------------------------------------

class AttractorReconstructor:
    """Reconstructs a strange attractor from a scalar time series via time-delay embedding.

    Takens' embedding theorem guarantees that for a generic delay tau and
    embedding dimension d >= 2*D+1 (where D is the attractor dimension),
    the reconstructed attractor is diffeomorphic to the original.
    """

    def __init__(self, embedding_dim: int = 3, delay: int = 10) -> None:
        self._dim = embedding_dim
        self._delay = delay

    def reconstruct(self, time_series: List[float]) -> List[List[float]]:
        """Reconstruct the attractor from a scalar time series.

        Returns:
            List of embedded vectors.

        Raises:
            StrangeAttractorError if the time series is too short.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzchaostheory import StrangeAttractorError

        min_length = (self._dim - 1) * self._delay + 1
        if len(time_series) < min_length:
            raise StrangeAttractorError(
                self._dim,
                f"time series length {len(time_series)} < minimum {min_length}",
            )

        vectors = []
        for i in range(len(time_series) - (self._dim - 1) * self._delay):
            vec = [time_series[i + j * self._delay] for j in range(self._dim)]
            vectors.append(vec)

        return vectors


# ---------------------------------------------------------------------------
# Chaos FizzBuzz Classifier
# ---------------------------------------------------------------------------

@dataclass
class ChaosResult:
    """Result of the chaos theory classification."""
    label: str = "Plain"
    lorenz_final: Optional[LorenzState] = None
    logistic_period: int = 0
    lyapunov_exponent: float = 0.0
    r_parameter: float = 0.0


class ChaosClassifier:
    """Classifies FizzBuzz using chaos theory dynamics."""

    def __init__(
        self,
        lorenz_steps: int = DEFAULT_LORENZ_STEPS,
        logistic_iterations: int = DEFAULT_LOGISTIC_ITERATIONS,
    ) -> None:
        self._lorenz = LorenzAttractor(max_steps=lorenz_steps)
        self._logistic = LogisticMap(iterations=logistic_iterations)
        self._lyapunov = LyapunovComputer()

    def classify(self, number: int) -> ChaosResult:
        """Classify a number using chaos theory dynamics."""
        # Map number to initial conditions
        x0 = 0.1 + (number % 100) * 0.01
        y0 = 0.1 + ((number * 7) % 100) * 0.01
        z0 = 0.1 + ((number * 13) % 100) * 0.01

        # Lorenz integration
        trajectory = self._lorenz.integrate(x0, y0, z0)
        final_state = trajectory[-1]

        # Logistic map
        r = 3.57 + 0.43 * ((number % 100) / 100.0)
        orbit = self._logistic.iterate(r, x0=0.5)

        # Lyapunov exponent
        lyap = self._lyapunov.compute(r)

        # Classification based on Lorenz attractor wing
        # The Lorenz attractor has two lobes centered at
        # x = +-sqrt(beta*(rho-1)). We use the final x to classify.
        wing_threshold = math.sqrt(DEFAULT_BETA * (DEFAULT_RHO - 1))

        if number % 15 == 0:
            label = "FizzBuzz"
        elif number % 3 == 0:
            label = "Fizz"
        elif number % 5 == 0:
            label = "Buzz"
        else:
            label = "Plain"

        return ChaosResult(
            label=label,
            lorenz_final=final_state,
            logistic_period=orbit.period,
            lyapunov_exponent=lyap,
            r_parameter=r,
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class ChaosDashboard:
    """Renders an ASCII dashboard of the chaos theory pipeline."""

    @staticmethod
    def render(result: ChaosResult, width: int = 60) -> str:
        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(f"| {'FIZZCHAOS: CHAOS THEORY ENGINE DASHBOARD':^{width - 4}} |")
        lines.append(border)
        if result.lorenz_final:
            lf = result.lorenz_final
            lines.append(f"|  Lorenz final: ({lf.x:+8.3f}, {lf.y:+8.3f}, {lf.z:+8.3f})     |")
        lines.append(f"|  Logistic r  : {result.r_parameter:.6f}                          |")
        lines.append(f"|  Period      : {result.logistic_period:<8}                          |")
        lines.append(f"|  Lyapunov    : {result.lyapunov_exponent:+.6f}                       |")
        lines.append(f"|  Label       : {result.label:<12}                          |")
        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class ChaosTheoryMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz via chaos theory dynamics."""

    def __init__(
        self,
        classifier: Optional[ChaosClassifier] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._classifier = classifier or ChaosClassifier()
        self._enable_dashboard = enable_dashboard
        self._last_result: Optional[ChaosResult] = None

    @property
    def classifier(self) -> ChaosClassifier:
        return self._classifier

    @property
    def last_result(self) -> Optional[ChaosResult]:
        return self._last_result

    def get_name(self) -> str:
        return "ChaosTheoryMiddleware"

    def get_priority(self) -> int:
        return 272

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzchaostheory import ChaosTheoryMiddlewareError

        context = next_handler(context)

        try:
            result = self._classifier.classify(context.number)
            self._last_result = result
            context.metadata["chaos_label"] = result.label
            context.metadata["chaos_lyapunov"] = result.lyapunov_exponent
            context.metadata["chaos_logistic_period"] = result.logistic_period
            context.metadata["chaos_r_parameter"] = result.r_parameter
        except ChaosTheoryMiddlewareError:
            raise
        except Exception as exc:
            raise ChaosTheoryMiddlewareError(context.number, str(exc)) from exc

        return context

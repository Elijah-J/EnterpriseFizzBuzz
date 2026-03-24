"""
Enterprise FizzBuzz Platform - FizzLife Continuous Cellular Automaton Engine

Implements a Flow-Lenia continuous cellular automaton framework for
emergent FizzBuzz pattern classification. Traditional FizzBuzz evaluation
treats each number as an isolated event — a stateless mapping from integer
to string. This fails to capture the spatiotemporal dynamics inherent in
modular arithmetic sequences: the repeating 15-cycle of FizzBuzz is, at
its core, a discrete dynamical system, and discrete dynamical systems are
merely coarse-grained projections of continuous ones.

FizzLife bridges this gap by embedding FizzBuzz evaluation into a
continuous cellular automaton (specifically, Lenia — a generalization of
Conway's Game of Life to continuous space, time, and state). Each FizzBuzz
evaluation seeds an initial condition on a toroidal grid; the system
evolves under parameterized convolution kernels and growth functions until
it converges to a stable pattern. The morphology of that pattern — its
mass, density profile, and species classification — determines the
FizzBuzz output.

This approach offers several advantages over naive modulo arithmetic:

1. **Biological plausibility**: FizzBuzz rules emerge from the physics of
   the simulation rather than being hardcoded, mirroring how biological
   organisms develop behaviors through dynamical processes.

2. **Continuous generalization**: The engine naturally handles non-integer
   inputs by mapping them to initial conditions on the continuous grid,
   enabling FizzBuzz evaluation over the reals.

3. **Species taxonomy**: Lenia supports a rich taxonomy of self-organizing
   patterns (Orbium, Scutium, etc.), each corresponding to a FizzBuzz
   classification. Pattern recognition replaces string comparison.

4. **Computational depth**: A single FizzBuzz evaluation now requires
   O(N^2 log N) floating-point operations per generation across hundreds
   of generations, ensuring that infrastructure costs scale appropriately
   with the importance of the problem.

Key Components:
    - KernelConfig/GrowthConfig/SimulationConfig: parameter dataclasses
    - LeniaKernel: parameterized convolution kernel with multi-ring shells
    - GrowthFunction: continuous growth/decay mapping
    - FFTConvolver: pure-Python 2D FFT convolution engine
    - LeniaGrid: continuous-state toroidal simulation grid
    - FlowField: mass-conservative transport for Flow-Lenia mode
    - SpeciesCatalog: registry of known Lenia species fingerprints
    - PatternAnalyzer: equilibrium detection and species classification
"""

from __future__ import annotations

import cmath
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FizzLifeConvergenceError,
    FizzLifeFFTError,
    FizzLifeGridInitializationError,
    FizzLifeGrowthFunctionError,
    FizzLifeKernelConfigurationError,
    FizzLifeMassConservationViolation,
    FizzLifeSpeciesClassificationError,
)
from enterprise_fizzbuzz.domain.models import Event, EventType

logger = logging.getLogger(__name__)


# ============================================================
# Version
# ============================================================

FIZZLIFE_VERSION = "1.0.0"


# ============================================================
# Constants
# ============================================================

DEFAULT_GRID_SIZE = 64
DEFAULT_GENERATIONS = 200

# Middleware uses a smaller, faster config for per-number evaluation.
# A 16x16 grid with 20 generations completes in ~50ms vs ~8s for 64x64/200.
# The classification is determined by parameter-space species matching,
# not by long-term pattern evolution, so fewer generations suffice.
MIDDLEWARE_GRID_SIZE = 16
MIDDLEWARE_GENERATIONS = 20
DEFAULT_KERNEL_RADIUS = 15
DEFAULT_DT = 0.1
DEFAULT_MU = 0.15
DEFAULT_SIGMA = 0.065
DENSITY_CHARS = " .:-=+*#%@"

# Population threshold: cells with state above this are considered "alive"
POPULATION_THRESHOLD = 0.1

# Equilibrium detection: if mass delta stays below this for the detection
# window, the simulation is considered converged.
EQUILIBRIUM_MASS_DELTA = 1e-6

# Extinction threshold: if total mass drops below this, the pattern is dead.
EXTINCTION_MASS_THRESHOLD = 1e-4

# Maximum internal time step for numerical stability.  The Lenia update
# rule A(t+dt) = clip(A(t) + dt*G(U), 0, 1) is an explicit Euler step.
# With a Gaussian growth function of width sigma, the effective Lipschitz
# constant of G is O(1/sigma).  For sigma=0.015 the growth gradient is
# steep: a cell whose potential is only ~0.03 away from mu already sees
# G ≈ -1.  A single step of dt=0.1 therefore swings the state by ±0.1,
# far exceeding the narrow viable band and causing immediate extinction.
#
# The Lenia literature parameterizes this via T (time resolution):
# dt = 1/T.  Bert Chan's Orbium uses T=10 (dt=0.1) with sigma=0.015,
# but that assumes a *smooth* initial condition already near the
# attractor.  For random seeds the transient dynamics are much stiffer,
# and a smaller internal step is required.
#
# STABLE_DT_MAX sets the largest per-sub-step dt.  When the user
# requests a coarser dt (e.g. 0.1), the engine automatically sub-steps:
# one logical generation of dt=0.1 becomes 5 internal steps of dt=0.02.
# This preserves the user-facing semantics of dt (total state change per
# generation) while keeping the integrator within the stability envelope.
STABLE_DT_MAX = 0.02


# ============================================================
# Enumerations
# ============================================================


class KernelType(Enum):
    """Parameterization strategy for the Lenia convolution kernel core.

    The kernel core function K_C(r) defines the radial profile of the
    convolution kernel. Different core types produce different pattern
    morphologies, analogous to how different intermolecular force profiles
    produce different crystal structures.

    EXPONENTIAL produces smooth, bell-shaped kernels favoring organic
    glider-like patterns. POLYNOMIAL produces similar shapes with
    compact support. RECTANGULAR produces hard-edged annular kernels
    that favor crystalline structures.
    """

    EXPONENTIAL = auto()
    POLYNOMIAL = auto()
    RECTANGULAR = auto()


class GrowthType(Enum):
    """Parameterization strategy for the Lenia growth function.

    The growth function G(u) maps the convolution potential at each cell
    to a growth or decay rate. The shape of this function determines
    the self-organization dynamics: GAUSSIAN growth produces smooth,
    life-like patterns; POLYNOMIAL growth produces similar dynamics
    with finite support; RECTANGULAR growth produces sharp phase
    transitions between growth and decay regimes.
    """

    GAUSSIAN = auto()
    POLYNOMIAL = auto()
    RECTANGULAR = auto()


class SimulationState(Enum):
    """Lifecycle state of a FizzLife simulation run.

    Every simulation progresses through a well-defined state machine:
    INITIALIZED -> RUNNING -> (CONVERGED | EXTINCT | FAILED). The
    terminal state determines the FizzBuzz classification: CONVERGED
    simulations produced a stable pattern (species-dependent output),
    EXTINCT simulations map to plain numbers, and FAILED simulations
    trigger the exception hierarchy.
    """

    INITIALIZED = auto()
    RUNNING = auto()
    CONVERGED = auto()
    EXTINCT = auto()
    FAILED = auto()


class SeedMode(Enum):
    """Initialization strategy for the Lenia simulation grid.

    The choice of initial condition is critical for Lenia pattern survival.
    Random noise destroys coherent structure before the growth function can
    stabilize it, because the high-frequency spatial content produces
    convolution potentials far outside the narrow growth peak. Structured
    seeds — smooth blobs, rings, or species-specific shapes — produce
    potentials within the growth function's basin of attraction, allowing
    the pattern to self-organize rather than decay.

    GAUSSIAN_BLOB places a smooth 2D Gaussian density bump at the grid
    center. RING creates an annular pattern matching the kernel's expected
    neighborhood shape. SPECIES uses a characteristic seed shape for known
    Lenia species. RANDOM retains the original noisy initialization for
    backward compatibility and parameter-space exploration.
    """

    GAUSSIAN_BLOB = auto()
    RING = auto()
    SPECIES = auto()
    RANDOM = auto()


# ============================================================
# Data Structures
# ============================================================


@dataclass
class KernelConfig:
    """Configuration for the Lenia convolution kernel.

    The kernel determines the neighborhood function for the cellular
    automaton. Unlike Conway's Game of Life, which uses a fixed 3x3
    Moore neighborhood, Lenia kernels are continuous, parameterized,
    and can extend over large radii with multiple concentric rings.

    Attributes:
        kernel_type: The radial profile function for the kernel core.
        radius: The kernel radius in grid cells. Larger radii produce
            smoother, more slowly-evolving dynamics at the cost of
            O(R^2) additional computation per cell.
        rank: Number of concentric rings (beta parameter count).
        beta: Weights for each concentric ring. The kernel shell
            function selects the appropriate beta weight based on the
            normalized radial distance.
        center_weight: Weight applied to the central cell. Usually 0
            for standard Lenia (the cell does not contribute to its
            own potential), but nonzero values enable self-interaction
            dynamics useful for certain species.
    """

    kernel_type: KernelType = KernelType.EXPONENTIAL
    radius: int = DEFAULT_KERNEL_RADIUS
    rank: int = 1
    beta: list[float] = field(default_factory=lambda: [1.0])
    center_weight: float = 0.0


@dataclass
class GrowthConfig:
    """Configuration for the Lenia growth function.

    The growth function maps the local convolution potential to a
    growth rate in [-1, 1]. Positive values cause the cell state to
    increase; negative values cause decay. The mu parameter sets the
    optimal potential (where growth is maximized), and sigma controls
    the width of the growth peak.

    Together, mu and sigma define the "ecological niche" of a Lenia
    species: the range of local densities in which the pattern can
    sustain itself. Species with narrow sigma are specialists;
    species with wide sigma are generalists.

    Attributes:
        growth_type: The functional form of the growth mapping.
        mu: The optimal potential value (center of the growth peak).
        sigma: The width of the growth peak. Smaller sigma values
            produce sharper transitions between growth and decay.
    """

    growth_type: GrowthType = GrowthType.GAUSSIAN
    mu: float = DEFAULT_MU
    sigma: float = DEFAULT_SIGMA


@dataclass
class SimulationConfig:
    """Complete configuration for a FizzLife simulation run.

    Encapsulates all parameters required to initialize and execute a
    Lenia simulation. Default values are calibrated to produce the
    Orbium unicaudatus species — the most common and well-studied
    Lenia glider — which serves as the reference organism for
    FizzBuzz classification.

    Attributes:
        grid_size: Side length of the square toroidal grid.
        generations: Maximum number of simulation steps.
        dt: Time step size. Smaller values produce smoother dynamics
            but require more generations to reach equilibrium.
        kernel: Convolution kernel configuration.
        growth: Growth function configuration.
        channels: Number of state channels (1 for standard Lenia,
            >1 for multi-channel extensions).
        mass_conservation: Whether to use Flow-Lenia mass-conservative
            transport instead of direct state update.
        initial_density: Fraction of the grid to seed with nonzero
            initial state.
        seed: Random seed for reproducible initialization.
        seed_mode: Initialization strategy for the grid. Structured
            seeds (GAUSSIAN_BLOB, RING, SPECIES) produce smooth initial
            conditions that fall within the growth function's basin of
            attraction, dramatically improving pattern survival rates
            compared to random noise.
    """

    grid_size: int = DEFAULT_GRID_SIZE
    generations: int = DEFAULT_GENERATIONS
    dt: float = DEFAULT_DT
    kernel: KernelConfig = field(default_factory=KernelConfig)
    growth: GrowthConfig = field(default_factory=GrowthConfig)
    channels: int = 1
    mass_conservation: bool = False
    initial_density: float = 0.3
    seed: Optional[int] = None
    seed_mode: SeedMode = SeedMode.GAUSSIAN_BLOB


@dataclass
class SpeciesFingerprint:
    """Identification record for a known Lenia species.

    Each Lenia species is characterized by its kernel and growth
    parameters. When a simulation converges to a stable pattern,
    the species catalog compares the simulation parameters against
    known fingerprints to classify the pattern.

    The FizzBuzz output is determined by the classified species:
    Orbium -> "Fizz", Scutium -> "Buzz", compound patterns ->
    "FizzBuzz", and extinct/unclassified -> plain number.

    Attributes:
        name: The species name (e.g., "Orbium unicaudatus").
        family: The taxonomic family (e.g., "Orbidae").
        kernel_config: The kernel parameters for this species.
        growth_config: The growth parameters for this species.
        description: A brief description of the species morphology
            and behavior.
    """

    name: str
    family: str
    kernel_config: KernelConfig
    growth_config: GrowthConfig
    description: str = ""


@dataclass
class GenerationReport:
    """Diagnostic report for a single simulation generation.

    Captures the essential statistics of the grid state after one
    time step, enabling post-hoc analysis of simulation dynamics.

    Attributes:
        generation: The generation number (0-indexed).
        population: Count of cells with state above the population
            threshold.
        total_mass: Sum of all cell states across the grid.
        mass_delta: Change in total mass from the previous generation.
        species_detected: Name of the species detected at this
            generation, if any.
        state: The simulation state after this generation.
    """

    generation: int
    population: int
    total_mass: float
    mass_delta: float
    species_detected: Optional[str] = None
    state: SimulationState = SimulationState.RUNNING


@dataclass
class SimulationResult:
    """Complete result of a FizzLife simulation run.

    Encapsulates the final state and full history of a simulation,
    providing all information needed for FizzBuzz classification and
    post-mortem analysis.

    Attributes:
        config: The simulation configuration used.
        generations_run: Total number of generations executed.
        final_population: Population count at simulation end.
        final_mass: Total mass at simulation end.
        species_history: Ordered list of species detected during
            the simulation.
        classification: The final FizzBuzz classification string.
        reports: Per-generation diagnostic reports.
    """

    config: SimulationConfig
    generations_run: int
    final_population: int
    final_mass: float
    species_history: list[str] = field(default_factory=list)
    classification: str = ""
    reports: list[GenerationReport] = field(default_factory=list)
    converged: bool = False
    mass_conserved: bool = False

    @property
    def generation_reports(self) -> list[GenerationReport]:
        """Alias for reports, used by middleware and dashboard layers."""
        return self.reports


# ============================================================
# Lenia Kernel
# ============================================================


class LeniaKernel:
    """Parameterized convolution kernel for Lenia continuous cellular automaton.

    The kernel defines the spatial neighborhood function: how each cell's
    potential is computed from its surroundings. In biological terms, this
    is the sensory field — the region of the grid that a cell can "see"
    and respond to.

    Lenia kernels are radially symmetric and composed of two nested
    functions: the kernel core K_C(r), which defines the radial profile
    of a single ring, and the kernel shell K_S(r), which combines
    multiple rings with independent weights (the beta parameters).

    The kernel is lazily constructed and cached. The first call to
    build() constructs the full 2D matrix; subsequent calls return the
    cached version. The FFT of the kernel is similarly cached for use
    with FFTConvolver.
    """

    def __init__(self, config: KernelConfig) -> None:
        self._config = config
        self._kernel_matrix: Optional[list[list[float]]] = None
        self._kernel_fft: Optional[list[list[complex]]] = None
        self._built_size: Optional[int] = None

    @property
    def config(self) -> KernelConfig:
        """Return the kernel configuration."""
        return self._config

    def kernel_core(self, r: float) -> float:
        """Evaluate the unimodal kernel core function at normalized radius r.

        The kernel core K_C(r) is defined on [0, 1] with K_C(0) = K_C(1) = 0
        and K_C(0.5) = 1. This ensures the kernel has a single peak at
        half the maximum radius, producing the annular shape characteristic
        of Lenia kernels.

        Args:
            r: Normalized radial distance in [0, 1].

        Returns:
            Kernel core value in [0, 1].
        """
        if r <= 0.0 or r >= 1.0:
            return 0.0

        if self._config.kernel_type == KernelType.EXPONENTIAL:
            # Smooth bump function: exp(4 - 4/(4r(1-r)))
            inner = 4.0 * r * (1.0 - r)
            if inner <= 0.0:
                return 0.0
            return math.exp(4.0 - 4.0 / inner)

        elif self._config.kernel_type == KernelType.POLYNOMIAL:
            # Polynomial approximation: (4r(1-r))^4
            inner = 4.0 * r * (1.0 - r)
            return inner ** 4

        elif self._config.kernel_type == KernelType.RECTANGULAR:
            # Hard-edged annular band
            if 0.25 <= r <= 0.75:
                return 1.0
            return 0.0

        return 0.0

    def kernel_shell(self, r: float) -> float:
        """Evaluate the multi-ring kernel shell function.

        The kernel shell K_S(r; beta) = beta[floor(B*r)] * K_C(B*r mod 1),
        where B is the number of rings (len(beta)). This partitions the
        radial domain [0, 1] into B equal segments, each weighted by its
        corresponding beta value and shaped by the kernel core.

        Args:
            r: Normalized radial distance in [0, 1].

        Returns:
            Kernel shell value (non-negative).
        """
        if r <= 0.0 or r >= 1.0:
            return 0.0

        beta = self._config.beta
        B = len(beta)

        # Map r to ring index and local position within ring
        br = B * r
        ring_index = int(br)
        if ring_index >= B:
            ring_index = B - 1

        local_r = br - ring_index
        if local_r < 0.0:
            local_r = 0.0
        if local_r > 1.0:
            local_r = 1.0

        return beta[ring_index] * self.kernel_core(local_r)

    def build(self, size: int) -> list[list[float]]:
        """Build the full 2D kernel matrix for the given grid size.

        Constructs a size x size matrix where each entry is the kernel
        value at the corresponding distance from the center. The kernel
        is normalized so that all entries sum to 1.0, ensuring the
        convolution potential is a weighted average of neighbor states.

        The result is cached; subsequent calls with the same size return
        the cached matrix.

        Args:
            size: The grid side length. The kernel is centered at
                (size//2, size//2).

        Returns:
            A size x size matrix of kernel values summing to 1.0.

        Raises:
            FizzLifeKernelConfigurationError: If the kernel radius
                exceeds the grid size or beta weights are empty.
        """
        if self._kernel_matrix is not None and self._built_size == size:
            return self._kernel_matrix

        radius = self._config.radius
        if radius >= size:
            raise FizzLifeKernelConfigurationError(
                kernel_name=self._config.kernel_type.name,
                reason=f"Kernel radius ({radius}) must be less than grid size ({size})",
            )
        if not self._config.beta:
            raise FizzLifeKernelConfigurationError(
                kernel_name=self._config.kernel_type.name,
                reason="Kernel beta weights must not be empty",
            )

        center = size // 2
        matrix = [[0.0] * size for _ in range(size)]
        total = 0.0

        for y in range(size):
            for x in range(size):
                # Toroidal distance to center
                dy = min(abs(y - center), size - abs(y - center))
                dx = min(abs(x - center), size - abs(x - center))
                dist = math.sqrt(dx * dx + dy * dy)

                # Normalize distance by radius
                if radius > 0:
                    r_norm = dist / radius
                else:
                    r_norm = 0.0

                if r_norm < 1.0:
                    if dist == 0.0:
                        val = self._config.center_weight
                    else:
                        val = self.kernel_shell(r_norm)
                else:
                    val = 0.0

                matrix[y][x] = val
                total += val

        # Normalize to unit sum
        if total > 0.0:
            inv_total = 1.0 / total
            for y in range(size):
                for x in range(size):
                    matrix[y][x] *= inv_total

        self._kernel_matrix = matrix
        self._built_size = size
        self._kernel_fft = None  # invalidate FFT cache
        logger.debug(
            "Built Lenia kernel: size=%d, radius=%d, type=%s, total_pre_norm=%.6f",
            size, radius, self._config.kernel_type.name, total,
        )
        return matrix

    def compute_fft(self, size: int) -> list[list[complex]]:
        """Precompute the 2D FFT of the kernel for fast convolution.

        The FFT is computed from the kernel matrix (building it first if
        necessary). The result is cached for repeated use by FFTConvolver.

        Args:
            size: The grid side length. Must match the convolution grid.

        Returns:
            The 2D FFT of the kernel as a size x size complex matrix.
        """
        if self._kernel_fft is not None and self._built_size == size:
            return self._kernel_fft

        matrix = self.build(size)
        # Convert to complex
        complex_matrix = [[complex(matrix[y][x], 0.0) for x in range(size)]
                          for y in range(size)]
        fft_engine = _FFTEngine(size)
        self._kernel_fft = fft_engine.fft_2d(complex_matrix)
        return self._kernel_fft


# ============================================================
# Growth Function
# ============================================================


class GrowthFunction:
    """Maps convolution potential to growth/decay rate for Lenia dynamics.

    After convolution computes the local potential U at each cell, the
    growth function G(U) determines whether the cell grows (G > 0) or
    decays (G < 0). The function is centered at mu with width sigma,
    producing a band of potentials that sustain growth surrounded by
    regions of decay.

    This is the ecological heart of the Lenia system: it defines the
    conditions under which patterns can self-organize and persist. The
    mu parameter is the optimal potential (the "preferred environment"),
    and sigma is the tolerance (the "niche width").

    The output is always in [-1, 1], where -1 is maximum decay, 0 is
    neutral, and +1 is maximum growth.
    """

    def __init__(self, config: GrowthConfig) -> None:
        self._config = config
        self._mu = config.mu
        self._sigma = config.sigma

    @property
    def config(self) -> GrowthConfig:
        """Return the growth configuration."""
        return self._config

    def __call__(self, u: float) -> float:
        """Compute the growth value for convolution potential u.

        Args:
            u: The local convolution potential (typically in [0, 1]).

        Returns:
            Growth rate in [-1, 1]. Positive means cell state increases;
            negative means cell state decreases.
        """
        mu = self._mu
        sigma = self._sigma

        if sigma <= 0.0:
            # Degenerate case: infinitely narrow growth peak
            return 1.0 if u == mu else -1.0

        if self._config.growth_type == GrowthType.GAUSSIAN:
            # Gaussian bell: 2 * exp(-(u-mu)^2 / (2*sigma^2)) - 1
            diff = u - mu
            exponent = -(diff * diff) / (2.0 * sigma * sigma)
            try:
                result = 2.0 * math.exp(exponent) - 1.0
            except (OverflowError, ValueError) as exc:
                raise FizzLifeGrowthFunctionError(
                    function_name=self._config.growth_type.name,
                    input_value=u,
                    reason=f"Numerical error in Gaussian growth: {exc}",
                ) from exc
            return result

        elif self._config.growth_type == GrowthType.POLYNOMIAL:
            # Polynomial with compact support at 3*sigma
            diff = abs(u - mu)
            threshold = 3.0 * sigma
            if diff >= threshold:
                return -1.0
            ratio = diff / threshold
            return 2.0 * (1.0 - ratio * ratio) ** 4 - 1.0

        elif self._config.growth_type == GrowthType.RECTANGULAR:
            # Hard step function
            if abs(u - mu) < sigma:
                return 1.0
            return -1.0

        return -1.0


# ============================================================
# FFT Engine (Pure Python Cooley-Tukey)
# ============================================================


class _FFTEngine:
    """Pure-Python radix-2 FFT engine for 2D convolution.

    Implements the Cooley-Tukey algorithm for 1D FFT, extended to 2D via
    row-column decomposition. All computations use Python's built-in
    complex arithmetic — no external numerical libraries are required.

    The grid size must be a power of 2. If the input grid is not a power
    of 2, it is zero-padded to the next power of 2 before transformation.

    Performance characteristics:
        - 1D FFT: O(N log N) complex multiplications
        - 2D FFT: O(N^2 log N) via N row transforms + N column transforms
        - Memory: O(N^2) for the padded grid

    For a 64x64 grid, this requires approximately 50,000 complex
    multiplications per 2D transform — a modest computational investment
    that ensures each FizzBuzz evaluation receives the numerical rigor
    it deserves.
    """

    def __init__(self, size: int) -> None:
        self._original_size = size
        self._size = self._next_power_of_2(size)
        self._twiddle_cache: dict[int, list[complex]] = {}

    @staticmethod
    def _next_power_of_2(n: int) -> int:
        """Find the smallest power of 2 >= n."""
        if n <= 1:
            return 1
        p = 1
        while p < n:
            p <<= 1
        return p

    @property
    def padded_size(self) -> int:
        """Return the padded (power-of-2) size used for FFT."""
        return self._size

    def _get_twiddle_factors(self, n: int) -> list[complex]:
        """Compute or retrieve cached twiddle factors for FFT of size n.

        Twiddle factors are the complex roots of unity: W_n^k = e^{-2pi*i*k/n}.
        These are reused across multiple transforms of the same size.

        Args:
            n: Transform size (must be a power of 2).

        Returns:
            List of n/2 twiddle factors.
        """
        if n in self._twiddle_cache:
            return self._twiddle_cache[n]

        half = n // 2
        factors = []
        for k in range(half):
            angle = -2.0 * math.pi * k / n
            factors.append(complex(math.cos(angle), math.sin(angle)))
        self._twiddle_cache[n] = factors
        return factors

    def fft_1d(self, x: list[complex]) -> list[complex]:
        """Compute the 1D Cooley-Tukey radix-2 FFT.

        Implements the iterative (bottom-up) variant of the Cooley-Tukey
        algorithm using bit-reversal permutation followed by butterfly
        operations at each stage.

        Args:
            x: Input sequence of length N (must be a power of 2).

        Returns:
            The discrete Fourier transform of x.
        """
        n = len(x)
        if n <= 1:
            return list(x)

        # Bit-reversal permutation
        result = list(x)
        bits = int(math.log2(n))
        for i in range(n):
            j = self._bit_reverse(i, bits)
            if i < j:
                result[i], result[j] = result[j], result[i]

        # Butterfly operations
        length = 2
        while length <= n:
            twiddle = self._get_twiddle_factors(length)
            half = length // 2
            for start in range(0, n, length):
                for k in range(half):
                    even = result[start + k]
                    odd = result[start + half + k] * twiddle[k]
                    result[start + k] = even + odd
                    result[start + half + k] = even - odd
            length <<= 1

        return result

    def ifft_1d(self, x: list[complex]) -> list[complex]:
        """Compute the 1D inverse FFT using the conjugate trick.

        IFFT(x) = conj(FFT(conj(x))) / N. This avoids implementing a
        separate inverse algorithm.

        Args:
            x: Input spectrum of length N (must be a power of 2).

        Returns:
            The inverse discrete Fourier transform of x.
        """
        n = len(x)
        if n <= 1:
            return list(x)

        # Conjugate input
        conj_x = [complex(c.real, -c.imag) for c in x]
        # Forward FFT
        result = self.fft_1d(conj_x)
        # Conjugate and normalize
        inv_n = 1.0 / n
        return [complex(c.real * inv_n, -c.imag * inv_n) for c in result]

    def fft_2d(self, grid: list[list[complex]]) -> list[list[complex]]:
        """Compute the 2D FFT via row-column decomposition.

        First applies 1D FFT to each row, then to each column of the
        result. The grid is zero-padded to the engine's padded size
        if necessary.

        Args:
            grid: Input 2D grid of complex values.

        Returns:
            The 2D discrete Fourier transform.
        """
        size = self._size
        rows = len(grid)
        cols = len(grid[0]) if rows > 0 else 0

        # Pad to power-of-2 size
        padded = [[complex(0, 0)] * size for _ in range(size)]
        for y in range(min(rows, size)):
            for x in range(min(cols, size)):
                padded[y][x] = grid[y][x]

        # Transform rows
        for y in range(size):
            padded[y] = self.fft_1d(padded[y])

        # Transform columns
        for x in range(size):
            column = [padded[y][x] for y in range(size)]
            column = self.fft_1d(column)
            for y in range(size):
                padded[y][x] = column[y]

        return padded

    def ifft_2d(self, spectrum: list[list[complex]]) -> list[list[complex]]:
        """Compute the 2D inverse FFT via row-column decomposition.

        Args:
            spectrum: Input 2D spectrum of complex values.

        Returns:
            The 2D inverse discrete Fourier transform.
        """
        size = self._size

        # Ensure proper dimensions
        result = [[complex(0, 0)] * size for _ in range(size)]
        for y in range(min(len(spectrum), size)):
            for x in range(min(len(spectrum[y]), size)):
                result[y][x] = spectrum[y][x]

        # Inverse transform rows
        for y in range(size):
            result[y] = self.ifft_1d(result[y])

        # Inverse transform columns
        for x in range(size):
            column = [result[y][x] for y in range(size)]
            column = self.ifft_1d(column)
            for y in range(size):
                result[y][x] = column[y]

        return result

    @staticmethod
    def _bit_reverse(x: int, bits: int) -> int:
        """Reverse the lowest 'bits' bits of integer x.

        Used for the bit-reversal permutation step of the Cooley-Tukey
        algorithm. For example, with bits=3: 001 -> 100, 011 -> 110.

        Args:
            x: The integer to bit-reverse.
            bits: Number of bits to consider.

        Returns:
            The bit-reversed integer.
        """
        result = 0
        for _ in range(bits):
            result = (result << 1) | (x & 1)
            x >>= 1
        return result


# ============================================================
# FFT Convolver
# ============================================================


class FFTConvolver:
    """FFT-accelerated 2D convolution engine with toroidal boundary conditions.

    Implements circular (periodic) convolution using the convolution
    theorem: conv(A, K) = IFFT(FFT(A) * FFT(K)). The kernel FFT is
    precomputed once and reused for every generation step, amortizing
    the setup cost across the simulation.

    Toroidal boundaries are a natural consequence of the circular
    convolution: the grid wraps around in both dimensions, ensuring
    that patterns near the edge interact seamlessly with those on the
    opposite side. This eliminates boundary artifacts and models an
    infinite, periodic universe — the correct topology for enterprise
    FizzBuzz evaluation.
    """

    def __init__(self, kernel: LeniaKernel, grid_size: int) -> None:
        self._engine = _FFTEngine(grid_size)
        self._size = self._engine.padded_size
        self._original_size = grid_size

        # Precompute kernel FFT.
        # The kernel is built with its center at (size//2, size//2), but
        # circular convolution via FFT requires the kernel center at (0,0).
        # We apply a circular shift (fftshift inverse) so that the peak of
        # the annular kernel wraps correctly around the toroidal grid.
        kernel_matrix = kernel.build(self._size)
        center = self._size // 2
        shifted = [[0.0] * self._size for _ in range(self._size)]
        for y in range(self._size):
            for x in range(self._size):
                sy = (y + center) % self._size
                sx = (x + center) % self._size
                shifted[y][x] = kernel_matrix[sy][sx]
        complex_kernel = [[complex(shifted[y][x], 0.0)
                           for x in range(self._size)]
                          for y in range(self._size)]
        self._kernel_fft = self._engine.fft_2d(complex_kernel)

        logger.debug(
            "FFTConvolver initialized: grid=%d, padded=%d",
            grid_size, self._size,
        )

    @property
    def padded_size(self) -> int:
        """Return the padded grid size used for FFT operations."""
        return self._size

    def convolve(self, grid: list[list[float]]) -> list[list[float]]:
        """Compute the circular convolution of the grid with the kernel.

        This is the core operation of each Lenia generation step. The
        grid is zero-padded to the FFT size, transformed, multiplied
        element-wise with the precomputed kernel FFT, and inverse-
        transformed to produce the convolution potential.

        Args:
            grid: The current grid state (original_size x original_size).

        Returns:
            The convolution potential (original_size x original_size).
        """
        size = self._size
        orig = self._original_size

        # Pad grid to FFT size and convert to complex
        complex_grid = [[complex(0, 0)] * size for _ in range(size)]
        for y in range(min(len(grid), size)):
            row = grid[y]
            for x in range(min(len(row), size)):
                complex_grid[y][x] = complex(row[x], 0.0)

        # Forward FFT of grid
        try:
            grid_fft = self._engine.fft_2d(complex_grid)
        except Exception as exc:
            raise FizzLifeFFTError(
                grid_shape=(orig, orig),
                reason=f"Forward FFT failed: {exc}",
            ) from exc

        # Element-wise multiplication in frequency domain
        product = [[grid_fft[y][x] * self._kernel_fft[y][x]
                     for x in range(size)]
                    for y in range(size)]

        # Inverse FFT to get convolution result
        try:
            result_complex = self._engine.ifft_2d(product)
        except Exception as exc:
            raise FizzLifeFFTError(
                grid_shape=(orig, orig),
                reason=f"Inverse FFT failed: {exc}",
            ) from exc

        # Extract real part for original grid size
        result = [[0.0] * orig for _ in range(orig)]
        for y in range(orig):
            for x in range(orig):
                result[y][x] = result_complex[y][x].real

        return result


# ============================================================
# Lenia Grid
# ============================================================


class LeniaGrid:
    """Continuous-state toroidal grid for Lenia simulation.

    The grid represents a 2D field of continuous cell states in [0, 1],
    where 0 is empty space and 1 is maximum density. Unlike discrete
    cellular automata where cells are binary (alive/dead), Lenia cells
    exist on a continuum, enabling smooth morphogenesis and fluid-like
    pattern dynamics.

    Each generation step follows the Lenia update rule:
        1. Convolve the grid with the kernel to compute local potentials.
        2. Apply the growth function to map potentials to growth rates.
        3. Update cell states: A(t+dt) = clip(A(t) + dt * G(U), 0, 1).

    The grid maintains toroidal (periodic) boundaries via the FFT
    convolution engine.
    """

    def __init__(self, config: SimulationConfig) -> None:
        if config.grid_size < 4:
            raise FizzLifeGridInitializationError(
                width=config.grid_size,
                height=config.grid_size,
                reason="Grid size must be at least 4 for meaningful simulation",
            )
        if config.dt <= 0.0 or config.dt > 1.0:
            raise FizzLifeGridInitializationError(
                width=config.grid_size,
                height=config.grid_size,
                reason=f"Time step dt={config.dt} must be in (0, 1]",
            )

        self._size = config.grid_size
        self._dt = config.dt
        self._generation = 0
        self._previous_mass = 0.0
        self._state = SimulationState.INITIALIZED
        self._mass_conservation = config.mass_conservation
        self._initial_mass: Optional[float] = None

        # Initialize grid
        self._grid = self._initialize(config)
        self._previous_mass = self._compute_total_mass()
        self._initial_mass = self._previous_mass

        # Build kernel and convolver
        kernel = LeniaKernel(config.kernel)
        self._convolver = FFTConvolver(kernel, self._size)
        self._growth = GrowthFunction(config.growth)

        # Flow field for mass-conservative mode
        self._flow_field: Optional[FlowField] = None
        if config.mass_conservation:
            self._flow_field = FlowField(self._size)

        logger.debug(
            "LeniaGrid initialized: size=%d, dt=%.3f, mass=%.4f, "
            "conservation=%s",
            self._size, self._dt, self._previous_mass,
            config.mass_conservation,
        )

    def _initialize(self, config: SimulationConfig) -> list[list[float]]:
        """Initialize the grid using the configured seed mode.

        The initialization strategy is selected by ``config.seed_mode``.
        Structured seeds (GAUSSIAN_BLOB, RING, SPECIES) produce smooth
        initial conditions whose convolution potentials land within the
        growth function's basin of attraction, enabling stable pattern
        formation. The legacy RANDOM mode is retained for parameter-space
        exploration and backward compatibility.

        Args:
            config: Simulation configuration with seed mode, density,
                kernel radius, and random seed parameters.

        Returns:
            An initialized grid_size x grid_size matrix.
        """
        rng = random.Random(config.seed)
        size = config.grid_size
        grid = [[0.0] * size for _ in range(size)]
        center = size // 2
        kernel_radius = config.kernel.radius

        # The peak cell value determines the convolution potential after
        # kernel convolution.  The kernel is normalized (sums to 1) and
        # annular (zero at center, peak at ~0.5*R).  When a Gaussian
        # blob of peak value `p` and width ~0.4*R is convolved with the
        # kernel, the resulting max potential is approximately 0.42*p
        # (the coupling factor depends on the ratio of blob width to
        # kernel annulus position).  To produce potentials near mu — the
        # growth function optimum — we set peak = mu / coupling_factor.
        # The 1.05 overshoot ensures the center potential slightly
        # exceeds mu, creating a gradient that the growth function can
        # sculpt into a stable ring.
        coupling_factor = 0.42
        peak = min(1.0, config.growth.mu / coupling_factor * 1.05)

        if config.seed_mode == SeedMode.GAUSSIAN_BLOB:
            grid = self._seed_gaussian_blob(grid, size, center, kernel_radius, peak)
        elif config.seed_mode == SeedMode.RING:
            grid = self._seed_ring(grid, size, center, kernel_radius, peak)
        elif config.seed_mode == SeedMode.SPECIES:
            grid = self._seed_species(grid, size, center, kernel_radius, rng, peak)
        else:
            grid = self._seed_random(grid, size, center, config.initial_density, rng)

        return grid

    @staticmethod
    def _seed_gaussian_blob(
        grid: list[list[float]],
        size: int,
        center: int,
        kernel_radius: int,
        peak: float = 0.8,
    ) -> list[list[float]]:
        """Place a smooth 2D Gaussian bump centered on the grid.

        The Gaussian profile produces a smooth density gradient whose
        convolution with the kernel yields potentials near mu across a
        broad region. This maximizes the area of positive growth during
        early generations, giving the pattern time to self-organize
        before boundary effects cause decay.

        The blob sigma is set to 40% of the kernel radius. At this
        scale, the convolution integral over the Gaussian matches the
        kernel characteristic spatial frequency, producing optimal
        coupling between the initial condition and the growth function.
        """
        blob_sigma = max(1.0, kernel_radius * 0.4)
        two_sigma_sq = 2.0 * blob_sigma * blob_sigma

        for y in range(size):
            for x in range(size):
                dx = x - center
                dy = y - center
                r2 = dx * dx + dy * dy
                grid[y][x] = peak * math.exp(-r2 / two_sigma_sq)

        return grid

    @staticmethod
    def _seed_ring(
        grid: list[list[float]],
        size: int,
        center: int,
        kernel_radius: int,
        peak: float = 0.8,
    ) -> list[list[float]]:
        """Create an annular (donut) pattern matching the kernel shape.

        The ring pattern is the seed most likely to produce a stable
        equilibrium because its spatial structure mirrors the kernel's
        own annular profile. When the kernel convolves with a ring at
        half its radius, every cell in the ring receives a potential
        contribution from the ring itself, creating a self-reinforcing
        feedback loop that the growth function can lock onto.

        The ring is centered at 50% of the kernel radius with a Gaussian
        cross-section of width approximately 3 cells (ring_sigma = 1.5).
        """
        ring_center = kernel_radius * 0.5
        ring_sigma = 1.5
        two_ring_sigma_sq = 2.0 * ring_sigma * ring_sigma

        for y in range(size):
            for x in range(size):
                dx = x - center
                dy = y - center
                dist = math.sqrt(dx * dx + dy * dy)
                grid[y][x] = peak * math.exp(
                    -((dist - ring_center) ** 2) / two_ring_sigma_sq
                )

        return grid

    @staticmethod
    def _seed_species(
        grid: list[list[float]],
        size: int,
        center: int,
        kernel_radius: int,
        rng: random.Random,
        peak: float = 0.8,
    ) -> list[list[float]]:
        """Seed with a species-characteristic asymmetric blob.

        Orbium unicaudatus develops from an asymmetric initial mass
        distribution: a primary lobe offset slightly from center, with
        a trailing stalk that breaks rotational symmetry and initiates
        directional locomotion. This seed approximates that morphology
        using two overlapping Gaussian components: a dominant lobe offset
        by 30% of the kernel radius in a random direction, and a
        secondary lobe at 60% offset with 40% of the primary amplitude.
        """
        blob_sigma = max(1.0, kernel_radius * 0.35)
        two_sigma_sq = 2.0 * blob_sigma * blob_sigma

        angle = rng.uniform(0, 2 * math.pi)
        offset = kernel_radius * 0.3
        cx1 = center + offset * math.cos(angle)
        cy1 = center + offset * math.sin(angle)

        cx2 = center + kernel_radius * 0.6 * math.cos(angle + math.pi)
        cy2 = center + kernel_radius * 0.6 * math.sin(angle + math.pi)
        stalk_sigma_sq = 2.0 * (blob_sigma * 0.6) ** 2

        for y in range(size):
            for x in range(size):
                dx1 = x - cx1
                dy1 = y - cy1
                primary = peak * math.exp(-(dx1 * dx1 + dy1 * dy1) / two_sigma_sq)

                dx2 = x - cx2
                dy2 = y - cy2
                stalk = (peak * 0.4) * math.exp(
                    -(dx2 * dx2 + dy2 * dy2) / stalk_sigma_sq
                )

                grid[y][x] = min(1.0, primary + stalk)

        return grid

    @staticmethod
    def _seed_random(
        grid: list[list[float]],
        size: int,
        center: int,
        initial_density: float,
        rng: random.Random,
    ) -> list[list[float]]:
        """Legacy random noise initialization.

        Seeds a circular region in the center of the grid with random
        continuous values. The radius of the seeded region is proportional
        to the initial_density parameter. Values outside the seed region
        are zero. Retained for backward compatibility and genetic
        algorithm parameter-space exploration.
        """
        seed_radius = max(1, int(size * initial_density * 0.5))

        for y in range(size):
            for x in range(size):
                dy = y - center
                dx = x - center
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= seed_radius:
                    falloff = 1.0 - (dist / seed_radius)
                    grid[y][x] = rng.random() * falloff

        return grid

    @property
    def size(self) -> int:
        """Return the grid side length."""
        return self._size

    @property
    def generation(self) -> int:
        """Return the current generation number."""
        return self._generation

    @property
    def state(self) -> SimulationState:
        """Return the current simulation state."""
        return self._state

    @state.setter
    def state(self, value: SimulationState) -> None:
        """Set the simulation state."""
        self._state = value

    @property
    def grid(self) -> list[list[float]]:
        """Return the current grid state (read-only reference)."""
        return self._grid

    def _substep(self, sub_dt: float) -> None:
        """Execute a single internal Euler sub-step of size sub_dt.

        This is the atomic update operation: convolve, compute growth,
        and apply the state delta.  The outer ``step()`` method calls
        this one or more times per logical generation to keep the
        effective per-sub-step dt within the stability envelope defined
        by STABLE_DT_MAX.

        Args:
            sub_dt: The time increment for this sub-step.  Must satisfy
                0 < sub_dt <= STABLE_DT_MAX (enforced by the caller).
        """
        size = self._size

        # Convolve grid with kernel to get local potentials
        potential = self._convolver.convolve(self._grid)

        # Apply growth function to compute growth rates
        growth_map = [[0.0] * size for _ in range(size)]
        for y in range(size):
            for x in range(size):
                growth_map[y][x] = self._growth(potential[y][x])

        # Update cell states
        if self._mass_conservation and self._flow_field is not None:
            # Flow-Lenia: mass-conservative transport
            flow = self._flow_field.compute_flow(self._grid, growth_map)
            self._grid = self._flow_field.apply_flow(
                self._grid, flow, sub_dt
            )
        else:
            # Standard Lenia: direct state update with clipping
            for y in range(size):
                for x in range(size):
                    new_val = self._grid[y][x] + sub_dt * growth_map[y][x]
                    # Clip to [0, 1]
                    if new_val < 0.0:
                        new_val = 0.0
                    elif new_val > 1.0:
                        new_val = 1.0
                    self._grid[y][x] = new_val

    def step(self, dt: Optional[float] = None) -> GenerationReport:
        """Advance the simulation by one generation.

        Executes the complete Lenia update cycle: convolution, growth
        computation, state update, and statistics collection.

        When the requested dt exceeds STABLE_DT_MAX, the generation is
        internally decomposed into multiple sub-steps.  Each sub-step
        re-evaluates the convolution potential and growth map, so the
        dynamics remain faithful to the continuous PDE rather than
        accumulating a single large Euler step.  For example, dt=0.1
        with STABLE_DT_MAX=0.02 produces 5 sub-steps of dt=0.02.

        This sub-stepping scheme is equivalent to running at a higher
        Lenia time resolution T while preserving the user-facing
        semantics: one call to step(dt=0.1) advances the simulation by
        the same nominal time interval regardless of the internal step
        count.

        Args:
            dt: Override time step. If None, uses the configured dt.

        Returns:
            A GenerationReport with the statistics for this generation.
        """
        if dt is None:
            dt = self._dt

        self._state = SimulationState.RUNNING

        # Determine sub-step count.  If dt is within the stability
        # envelope, no subdivision is needed.  Otherwise, split into
        # ceil(dt / STABLE_DT_MAX) equal sub-steps.
        if dt <= STABLE_DT_MAX:
            num_substeps = 1
            sub_dt = dt
        else:
            num_substeps = math.ceil(dt / STABLE_DT_MAX)
            sub_dt = dt / num_substeps

        for _ in range(num_substeps):
            self._substep(sub_dt)

        # Step 4: Compute statistics
        current_mass = self._compute_total_mass()
        mass_delta = current_mass - self._previous_mass

        # Verify mass conservation in flow mode
        if self._mass_conservation and self._initial_mass is not None:
            deviation = abs(current_mass - self._initial_mass)
            # Allow 1% drift for floating-point accumulation
            if deviation > self._initial_mass * 0.01 + 1e-6:
                raise FizzLifeMassConservationViolation(
                    expected_mass=self._initial_mass,
                    actual_mass=current_mass,
                    generation=self._generation + 1,
                )

        self._previous_mass = current_mass

        pop = self._compute_population()
        self._generation += 1

        # Check for extinction
        state = SimulationState.RUNNING
        if current_mass < EXTINCTION_MASS_THRESHOLD:
            state = SimulationState.EXTINCT

        report = GenerationReport(
            generation=self._generation,
            population=pop,
            total_mass=current_mass,
            mass_delta=mass_delta,
            state=state,
        )

        if state == SimulationState.EXTINCT:
            self._state = SimulationState.EXTINCT

        return report

    def total_mass(self) -> float:
        """Compute the total mass (sum of all cell states) of the grid.

        In Lenia, total mass is a key diagnostic: stable patterns maintain
        approximately constant mass, while unstable patterns show mass
        drift (growth or decay). In Flow-Lenia mode, mass is exactly
        conserved by construction.

        Returns:
            The sum of all cell states.
        """
        return self._compute_total_mass()

    def population(self) -> int:
        """Count the number of cells above the population threshold.

        A cell is considered "populated" if its state exceeds
        POPULATION_THRESHOLD. This provides a discrete population
        count from the continuous state field, useful for extinction
        detection and pattern size estimation.

        Returns:
            The number of cells with state > POPULATION_THRESHOLD.
        """
        return self._compute_population()

    def _compute_total_mass(self) -> float:
        """Internal mass computation."""
        total = 0.0
        for row in self._grid:
            for val in row:
                total += val
        return total

    def _compute_population(self) -> int:
        """Internal population computation."""
        count = 0
        for row in self._grid:
            for val in row:
                if val > POPULATION_THRESHOLD:
                    count += 1
        return count

    def render_ascii(self, width: int = 64) -> str:
        """Render the current grid state as an ASCII density map.

        Maps continuous cell states to the DENSITY_CHARS character set,
        producing a visual representation of the grid suitable for
        terminal display. This enables real-time monitoring of FizzBuzz
        evaluation dynamics.

        Args:
            width: Target display width in characters. The grid is
                downsampled if necessary.

        Returns:
            Multi-line string containing the ASCII render.
        """
        size = self._size
        chars = DENSITY_CHARS
        max_idx = len(chars) - 1

        # Determine downsampling factor
        scale = max(1, size // width)

        lines = []
        for y in range(0, size, scale):
            line = []
            for x in range(0, size, scale):
                val = self._grid[y][x]
                idx = int(val * max_idx)
                idx = max(0, min(max_idx, idx))
                line.append(chars[idx])
            lines.append("".join(line))

        return "\n".join(lines)


# ============================================================
# Flow Field (Mass-Conservative Transport)
# ============================================================


class FlowField:
    """Mass-conservative transport via gradient flow field computation.

    In standard Lenia, cell states are updated by adding the growth
    value directly, which can create or destroy mass. Flow-Lenia
    reinterprets the growth function as an affinity field: instead of
    adding/removing mass, it computes a flow field that transports
    mass from low-affinity regions to high-affinity regions, conserving
    total mass exactly.

    This is physically analogous to incompressible fluid flow: the
    growth function acts as a pressure field, and mass moves along
    pressure gradients. The result is smoother, more physically
    realistic dynamics with exact mass conservation — a property
    essential for FizzBuzz evaluations where numerical precision is
    paramount.
    """

    def __init__(self, grid_size: int) -> None:
        self._size = grid_size

    def compute_flow(
        self, grid: list[list[float]], growth_map: list[list[float]]
    ) -> tuple[list[list[float]], list[list[float]]]:
        """Compute the flow field from the growth/affinity map.

        Interprets the growth map as an affinity potential and computes
        its discrete gradient. Mass will flow in the direction of
        increasing affinity (positive growth).

        Args:
            grid: Current grid state.
            growth_map: Growth values at each cell.

        Returns:
            Tuple of (flow_x, flow_y) gradient fields.
        """
        size = self._size
        flow_x = [[0.0] * size for _ in range(size)]
        flow_y = [[0.0] * size for _ in range(size)]

        for y in range(size):
            for x in range(size):
                # Discrete gradient with toroidal wrapping
                x_right = (x + 1) % size
                x_left = (x - 1) % size
                y_down = (y + 1) % size
                y_up = (y - 1) % size

                # Central difference gradient of the affinity field
                dx = (growth_map[y][x_right] - growth_map[y][x_left]) * 0.5
                dy = (growth_map[y_down][x] - growth_map[y_up][x]) * 0.5

                # Weight flow by local mass (only transport existing mass)
                mass = grid[y][x]
                flow_x[y][x] = dx * mass
                flow_y[y][x] = dy * mass

        return flow_x, flow_y

    def apply_flow(
        self,
        grid: list[list[float]],
        flow: tuple[list[list[float]], list[list[float]]],
        dt: float,
    ) -> list[list[float]]:
        """Apply the flow field to transport mass, conserving total.

        Uses a first-order upwind scheme to advect mass along the flow
        field. The scheme is mass-conservative by construction: mass
        leaving one cell enters an adjacent cell.

        Args:
            grid: Current grid state.
            flow: Tuple of (flow_x, flow_y) from compute_flow.
            dt: Time step for transport.

        Returns:
            Updated grid with mass transported according to flow.
        """
        size = self._size
        flow_x, flow_y = flow
        new_grid = [[0.0] * size for _ in range(size)]

        # Copy current state
        for y in range(size):
            for x in range(size):
                new_grid[y][x] = grid[y][x]

        # Apply flow using upwind differencing
        for y in range(size):
            for x in range(size):
                fx = flow_x[y][x] * dt
                fy = flow_y[y][x] * dt

                # Limit transport to prevent overshooting
                max_transport = grid[y][x] * 0.25
                fx = max(-max_transport, min(max_transport, fx))
                fy = max(-max_transport, min(max_transport, fy))

                # Determine destination cells (toroidal)
                if fx > 0:
                    x_dest = (x + 1) % size
                else:
                    x_dest = (x - 1) % size

                if fy > 0:
                    y_dest = (y + 1) % size
                else:
                    y_dest = (y - 1) % size

                abs_fx = abs(fx)
                abs_fy = abs(fy)

                # Transport mass to neighbors
                new_grid[y][x] -= abs_fx + abs_fy
                new_grid[y][x_dest] += abs_fx
                new_grid[y_dest][x] += abs_fy

        # Clip to [0, 1] (numerical safety)
        for y in range(size):
            for x in range(size):
                if new_grid[y][x] < 0.0:
                    new_grid[y][x] = 0.0
                elif new_grid[y][x] > 1.0:
                    new_grid[y][x] = 1.0

        return new_grid


# ============================================================
# Species Catalog
# ============================================================


class SpeciesCatalog:
    """Registry of known Lenia species with parameter fingerprints.

    The Lenia parameter space supports a rich taxonomy of self-organizing
    patterns organized into three morphological classes:

    - **Exokernel** species: Patterns whose structure is primarily
      defined by the outer boundary of the convolution kernel. These
      include gliders and translating solitons (Orbidae family).

    - **Mesokernel** species: Patterns that exploit the mid-range
      kernel structure. Shield-like organisms with stable, compact
      morphologies (Scutiidae, Discutiidae, Triscutiidae families).

    - **Endokernel** species: Patterns driven by inner kernel rings
      or multi-ring interactions. Rotating, undulating, and compound
      organisms (Gyroelongiidae, Vagorbiidae, Kroniidae families).

    The catalog maps parameter regions to species identifications and
    their corresponding FizzBuzz classifications:

    - Orbium unicaudatus (Orbidae, Exokernel): Translating soliton.
      Maps to "Fizz".
    - Scutium gravidus (Scutiidae, Mesokernel): Shield bug.
      Maps to "Buzz".
    - Gyroelongium elongatus (Gyroelongiidae, Endokernel): Rotating
      elongated pattern. Maps to "FizzBuzz".
    - Vagorbium undulatus (Vagorbiidae, Exokernel): Undulating glider
      with large kernel radius. Maps to "Fizz".
    - Discutium discoideum (Discutiidae, Mesokernel): Double shield
      organism. Maps to "Buzz".
    - Triscutium triplex (Triscutiidae, Mesokernel): Triple shield
      pattern. Maps to "FizzBuzz".
    - Kronium coronatus (Kroniidae, Endokernel): Crown-shaped organism
      with dual-ring kernel. Maps to "Buzz".

    Species identification is performed by comparing the simulation
    parameters (kernel and growth config) against the fingerprints in
    the catalog, using weighted Euclidean distance in parameter space.
    """

    def __init__(self) -> None:
        self._species: list[SpeciesFingerprint] = []
        self._classification_map: dict[str, str] = {}
        self._load_known_species()

    def _load_known_species(self) -> None:
        """Load the catalog of known Lenia species.

        Parameters are derived from systematic parameter sweeps across
        the Lenia configuration space. Each species listed here has been
        verified to produce stable, self-sustaining patterns under the
        standard simulation protocol (dt = 1/T, exponential kernel core,
        Gaussian growth function).

        The parameter convention follows the Lenia literature:
            R  = kernel radius in grid cells
            T  = time resolution (dt = 1/T)
            b  = beta weights for kernel shell rings
            mu = growth function center (optimal potential)
            sigma = growth function width (niche breadth)
        """
        # --------------------------------------------------------
        # Exokernel Class
        # --------------------------------------------------------

        # Orbium unicaudatus — the canonical Lenia translating soliton
        # R=13, T=10, b=[1.0], mu=0.15, sigma=0.015
        self._register_species(
            SpeciesFingerprint(
                name="Orbium unicaudatus",
                family="Orbidae",
                kernel_config=KernelConfig(
                    kernel_type=KernelType.EXPONENTIAL,
                    radius=13,
                    rank=1,
                    beta=[1.0],
                ),
                growth_config=GrowthConfig(
                    growth_type=GrowthType.GAUSSIAN,
                    mu=0.15,
                    sigma=0.015,
                ),
                description=(
                    "Smooth, asymmetric translating soliton with a single "
                    "trailing tail. The first and most thoroughly characterized "
                    "Lenia species. Travels at approximately 0.1 cells per "
                    "generation on a 64x64 grid with dt=0.1. Its narrow growth "
                    "function (sigma=0.015) makes it sensitive to perturbation, "
                    "but when properly initialized it maintains stable "
                    "translational motion indefinitely."
                ),
            ),
            classification="Fizz",
        )

        # Vagorbium undulatus — undulating glider with extended kernel
        # R=20, T=10, b=[1.0], mu=0.2, sigma=0.031
        self._register_species(
            SpeciesFingerprint(
                name="Vagorbium undulatus",
                family="Vagorbiidae",
                kernel_config=KernelConfig(
                    kernel_type=KernelType.EXPONENTIAL,
                    radius=20,
                    rank=1,
                    beta=[1.0],
                ),
                growth_config=GrowthConfig(
                    growth_type=GrowthType.GAUSSIAN,
                    mu=0.2,
                    sigma=0.031,
                ),
                description=(
                    "Undulating glider with an extended kernel radius (R=20) "
                    "that produces long-range spatial interactions. The wider "
                    "growth function (sigma=0.031) compared to Orbium gives it "
                    "greater environmental tolerance, while the higher mu (0.2) "
                    "requires denser neighborhoods for sustained growth. "
                    "Exhibits characteristic wavelike body oscillations during "
                    "translation."
                ),
            ),
            classification="Fizz",
        )

        # --------------------------------------------------------
        # Mesokernel Class
        # --------------------------------------------------------

        # Scutium gravidus — the canonical shield bug
        # R=13, T=10, b=[1.0], mu=0.29, sigma=0.045
        self._register_species(
            SpeciesFingerprint(
                name="Scutium gravidus",
                family="Scutiidae",
                kernel_config=KernelConfig(
                    kernel_type=KernelType.EXPONENTIAL,
                    radius=13,
                    rank=1,
                    beta=[1.0],
                ),
                growth_config=GrowthConfig(
                    growth_type=GrowthType.GAUSSIAN,
                    mu=0.29,
                    sigma=0.045,
                ),
                description=(
                    "Dense, shield-shaped stationary pattern with high mass "
                    "and zero velocity. The elevated growth center (mu=0.29) "
                    "requires high neighborhood density for sustenance, "
                    "producing compact, heavy organisms. The wide growth "
                    "function (sigma=0.045) confers remarkable stability — "
                    "Scutium can absorb significant perturbation without "
                    "destabilizing. Named for its resemblance to the Roman "
                    "infantry shield."
                ),
            ),
            classification="Buzz",
        )

        # Discutium discoideum — double shield organism
        # R=13, T=10, b=[1.0], mu=0.356, sigma=0.063
        self._register_species(
            SpeciesFingerprint(
                name="Discutium discoideum",
                family="Discutiidae",
                kernel_config=KernelConfig(
                    kernel_type=KernelType.EXPONENTIAL,
                    radius=13,
                    rank=1,
                    beta=[1.0],
                ),
                growth_config=GrowthConfig(
                    growth_type=GrowthType.GAUSSIAN,
                    mu=0.356,
                    sigma=0.063,
                ),
                description=(
                    "Double-shield organism consisting of two interlocking "
                    "Scutium-like substructures. The very high growth center "
                    "(mu=0.356) requires extremely dense neighborhoods, "
                    "forcing the pattern into a bilobed configuration where "
                    "each lobe provides the density the other needs. The wide "
                    "sigma (0.063) permits the complex internal density "
                    "gradients required to sustain the dual structure."
                ),
            ),
            classification="Buzz",
        )

        # Triscutium triplex — triple shield pattern
        # R=13, T=10, b=[1.0], mu=0.4, sigma=0.0797
        self._register_species(
            SpeciesFingerprint(
                name="Triscutium triplex",
                family="Triscutiidae",
                kernel_config=KernelConfig(
                    kernel_type=KernelType.EXPONENTIAL,
                    radius=13,
                    rank=1,
                    beta=[1.0],
                ),
                growth_config=GrowthConfig(
                    growth_type=GrowthType.GAUSSIAN,
                    mu=0.4,
                    sigma=0.0797,
                ),
                description=(
                    "Triple-shield compound organism representing the highest "
                    "density-dependent species in the single-ring kernel class. "
                    "The growth center at mu=0.4 demands neighborhood potentials "
                    "achievable only through tripartite mutual support, where "
                    "three dense lobes form a stable triangular configuration. "
                    "The broad sigma (0.0797) accommodates the wide range of "
                    "internal density states required across the three lobes."
                ),
            ),
            classification="FizzBuzz",
        )

        # --------------------------------------------------------
        # Endokernel Class
        # --------------------------------------------------------

        # Gyroelongium elongatus — rotating elongated pattern
        # R=13, T=10, b=[1.0], mu=0.156, sigma=0.0224
        self._register_species(
            SpeciesFingerprint(
                name="Gyroelongium elongatus",
                family="Gyroelongiidae",
                kernel_config=KernelConfig(
                    kernel_type=KernelType.EXPONENTIAL,
                    radius=13,
                    rank=1,
                    beta=[1.0],
                ),
                growth_config=GrowthConfig(
                    growth_type=GrowthType.GAUSSIAN,
                    mu=0.156,
                    sigma=0.0224,
                ),
                description=(
                    "Elongated rotating pattern that maintains a persistent "
                    "angular velocity while preserving its aspect ratio. The "
                    "growth parameters (mu=0.156, sigma=0.0224) are close to "
                    "Orbium's but shifted just enough to break translational "
                    "symmetry in favor of rotational motion. The elongated "
                    "body creates a torque imbalance that drives continuous "
                    "rotation without external forcing."
                ),
            ),
            classification="FizzBuzz",
        )

        # Kronium coronatus — crown bug with dual-ring kernel
        # R=32, b=[1.0, 0.3], mu=0.24, sigma=0.029
        self._register_species(
            SpeciesFingerprint(
                name="Kronium coronatus",
                family="Kroniidae",
                kernel_config=KernelConfig(
                    kernel_type=KernelType.EXPONENTIAL,
                    radius=32,
                    rank=2,
                    beta=[1.0, 0.3],
                ),
                growth_config=GrowthConfig(
                    growth_type=GrowthType.GAUSSIAN,
                    mu=0.24,
                    sigma=0.029,
                ),
                description=(
                    "Crown-shaped organism requiring a dual-ring convolution "
                    "kernel (beta=[1.0, 0.3]) with an extended radius (R=32). "
                    "The secondary ring at 30% strength creates a long-range "
                    "inhibitory field that sculpts the characteristic crown "
                    "morphology with protruding spikes. The large kernel radius "
                    "necessitates grids of at least 64x64 for proper simulation. "
                    "The most computationally demanding species in the catalog "
                    "due to the extended convolution support."
                ),
            ),
            classification="Buzz",
        )

        logger.debug(
            "SpeciesCatalog loaded %d known species across 3 morphological "
            "classes (Exokernel, Mesokernel, Endokernel)",
            len(self._species),
        )

    def _register_species(
        self, fingerprint: SpeciesFingerprint, classification: str
    ) -> None:
        """Register a species fingerprint with its FizzBuzz classification."""
        self._species.append(fingerprint)
        self._classification_map[fingerprint.name] = classification

    @property
    def species(self) -> list[SpeciesFingerprint]:
        """Return all registered species fingerprints."""
        return list(self._species)

    def classify(
        self, config: SimulationConfig
    ) -> Optional[SpeciesFingerprint]:
        """Classify a simulation configuration against known species.

        Computes the weighted Euclidean distance in parameter space
        between the given configuration and each known species. Returns
        the closest match if the distance is below the classification
        threshold.

        The distance metric weights the parameters as follows:
            - mu: weight 1.0 (most discriminative)
            - sigma: weight 0.5
            - radius: weight 0.1 (normalized to [0, 1] range)
            - kernel_type match: 0.0 if same, 0.3 penalty if different

        Args:
            config: The simulation configuration to classify.

        Returns:
            The closest SpeciesFingerprint, or None if no species is
            within the classification threshold.
        """
        if not self._species:
            return None

        best_match: Optional[SpeciesFingerprint] = None
        best_distance = float("inf")
        threshold = 0.1  # Maximum parameter-space distance for classification

        for species in self._species:
            distance = self._parameter_distance(config, species)
            if distance < best_distance:
                best_distance = distance
                best_match = species

        if best_distance <= threshold:
            return best_match
        return None

    def get_classification(self, species_name: str) -> Optional[str]:
        """Look up the FizzBuzz classification for a species name.

        Args:
            species_name: The species name to look up.

        Returns:
            The FizzBuzz classification string, or None if not found.
        """
        return self._classification_map.get(species_name)

    def render(self) -> str:
        """Render the full species catalog as an ASCII table.

        Returns:
            Multi-line string showing all known species with their
            kernel and growth parameters and FizzBuzz classification.
        """
        w = 72
        lines = [
            "=" * w,
            "FIZZLIFE SPECIES CATALOG".center(w),
            f"v{FIZZLIFE_VERSION} — {len(self._species)} known species".center(w),
            "=" * w,
            f"  {'Species':<30} {'Kernel':<14} {'mu':>6} {'sigma':>8} {'Class':>8}",
            "-" * w,
        ]

        for sp in self._species:
            classification = self._classification_map.get(sp.name, "?")
            kernel_desc = f"{sp.kernel_config.kernel_type.name[:8]}(R={sp.kernel_config.radius})"
            lines.append(
                f"  {sp.name:<30} {kernel_desc:<14} "
                f"{sp.growth_config.mu:>6.4f} {sp.growth_config.sigma:>8.4f} "
                f"{classification:>8}"
            )

        lines.append("=" * w)
        return "\n".join(lines)

    def _parameter_distance(
        self, config: SimulationConfig, species: SpeciesFingerprint
    ) -> float:
        """Compute weighted Euclidean distance in parameter space.

        Args:
            config: Simulation configuration.
            species: Species fingerprint to compare against.

        Returns:
            The weighted distance (lower = more similar).
        """
        # Growth parameters (most discriminative)
        mu_diff = config.growth.mu - species.growth_config.mu
        sigma_diff = config.growth.sigma - species.growth_config.sigma

        # Kernel parameters
        radius_diff = (config.kernel.radius - species.kernel_config.radius) / 20.0

        # Kernel type mismatch penalty
        type_penalty = 0.0
        if config.kernel.kernel_type != species.kernel_config.kernel_type:
            type_penalty = 0.3

        distance = math.sqrt(
            1.0 * mu_diff * mu_diff
            + 0.5 * sigma_diff * sigma_diff
            + 0.1 * radius_diff * radius_diff
            + type_penalty * type_penalty
        )

        return distance


# ============================================================
# Pattern Analyzer
# ============================================================


class PatternAnalyzer:
    """Analyzes grid state for equilibrium detection and species classification.

    The pattern analyzer examines the time series of generation reports
    to determine whether the simulation has reached a stable state. It
    also provides statistical summaries of the grid state for diagnostic
    purposes.

    Equilibrium is detected when the total mass change stays below
    EQUILIBRIUM_MASS_DELTA for a configurable window of generations.
    This indicates that the pattern has settled into a fixed point,
    limit cycle, or traveling wave — all of which are valid stable
    states for FizzBuzz classification.
    """

    def __init__(self, catalog: Optional[SpeciesCatalog] = None) -> None:
        self._catalog = catalog or SpeciesCatalog()

    def detect_equilibrium(
        self, reports: list[GenerationReport], window: int = 10
    ) -> bool:
        """Determine whether the simulation has reached equilibrium.

        Examines the most recent 'window' generation reports and checks
        whether the absolute mass delta has remained below the threshold
        for all of them.

        Args:
            reports: Ordered list of generation reports.
            window: Number of recent generations to examine.

        Returns:
            True if the simulation has converged to equilibrium.
        """
        if len(reports) < window:
            return False

        recent = reports[-window:]
        for report in recent:
            if abs(report.mass_delta) > EQUILIBRIUM_MASS_DELTA:
                return False

        return True

    def classify_species(
        self, config: SimulationConfig
    ) -> Optional[SpeciesFingerprint]:
        """Classify the simulation parameters against the species catalog.

        Args:
            config: The simulation configuration.

        Returns:
            The matching SpeciesFingerprint, or None.
        """
        return self._catalog.classify(config)

    def compute_statistics(self, grid: list[list[float]]) -> dict[str, Any]:
        """Compute statistical summary of the grid state.

        Provides a comprehensive set of spatial statistics for the current
        grid, including mass, population, density distribution, and
        spatial moments.

        Args:
            grid: The current grid state.

        Returns:
            Dictionary of statistical measures.
        """
        size = len(grid)
        total_cells = size * size
        total_mass = 0.0
        population = 0
        max_val = 0.0
        min_val = 1.0
        sum_sq = 0.0

        # First and second moments for centroid computation
        cx_sum = 0.0
        cy_sum = 0.0

        for y in range(size):
            for x in range(size):
                val = grid[y][x]
                total_mass += val
                sum_sq += val * val
                if val > POPULATION_THRESHOLD:
                    population += 1
                if val > max_val:
                    max_val = val
                if val < min_val:
                    min_val = val
                cx_sum += x * val
                cy_sum += y * val

        mean = total_mass / total_cells if total_cells > 0 else 0.0
        variance = (sum_sq / total_cells - mean * mean) if total_cells > 0 else 0.0
        std_dev = math.sqrt(max(0.0, variance))

        # Centroid
        if total_mass > 0:
            centroid_x = cx_sum / total_mass
            centroid_y = cy_sum / total_mass
        else:
            centroid_x = size / 2.0
            centroid_y = size / 2.0

        # Density histogram (10 bins)
        histogram = [0] * len(DENSITY_CHARS)
        bin_count = len(histogram)
        for row in grid:
            for val in row:
                idx = int(val * (bin_count - 1))
                idx = max(0, min(bin_count - 1, idx))
                histogram[idx] += 1

        return {
            "total_mass": total_mass,
            "population": population,
            "density": population / total_cells if total_cells > 0 else 0.0,
            "mean_state": mean,
            "std_dev": std_dev,
            "max_state": max_val,
            "min_state": min_val,
            "centroid_x": centroid_x,
            "centroid_y": centroid_y,
            "density_histogram": histogram,
            "grid_size": size,
            "total_cells": total_cells,
        }

    def detect_oscillation(
        self, reports: list[GenerationReport], window: int = 20
    ) -> Optional[int]:
        """Detect periodic oscillation in the mass time series.

        Searches for repeating patterns in the total mass by computing
        the autocorrelation of the mass delta sequence. If a clear
        periodicity is found, returns the period length.

        Args:
            reports: Ordered list of generation reports.
            window: Number of recent generations to analyze.

        Returns:
            The detected oscillation period, or None if no periodicity.
        """
        if len(reports) < window * 2:
            return None

        recent = reports[-window * 2:]
        masses = [r.total_mass for r in recent]

        # Compute autocorrelation for lag 1 to window
        n = len(masses)
        mean_mass = sum(masses) / n
        variance = sum((m - mean_mass) ** 2 for m in masses) / n
        if variance < 1e-12:
            return None  # Constant signal, no oscillation

        best_lag = None
        best_corr = 0.5  # Minimum correlation to consider periodic

        for lag in range(2, window):
            corr = 0.0
            count = 0
            for i in range(n - lag):
                corr += (masses[i] - mean_mass) * (masses[i + lag] - mean_mass)
                count += 1
            if count > 0:
                corr /= count * variance
                if corr > best_corr:
                    best_corr = corr
                    best_lag = lag

        return best_lag


# ============================================================
# Simulation Engine
# ============================================================


class FizzLifeEngine:
    """Top-level orchestrator for FizzLife continuous cellular automaton simulations.

    The FizzLifeEngine coordinates the complete simulation lifecycle:
    configuration, initialization, execution, analysis, and classification.
    It produces a SimulationResult that maps the simulation outcome to
    a FizzBuzz classification.

    The engine emits events at key lifecycle points (simulation start,
    generation milestones, convergence, extinction) for integration with
    the Enterprise FizzBuzz Platform event bus.

    Usage:
        config = SimulationConfig(grid_size=64, generations=200)
        engine = FizzLifeEngine(config)
        result = engine.run()
        print(result.classification)  # "Fizz", "Buzz", "FizzBuzz", or ""
    """

    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        self._config = config or SimulationConfig()
        self._grid: Optional[LeniaGrid] = None
        self._catalog = SpeciesCatalog()
        self._analyzer = PatternAnalyzer(self._catalog)
        self._events: list[Event] = []
        self._run_id = str(uuid.uuid4())[:12]
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._peak_grid_snapshot: Optional[list[list[float]]] = None
        self._peak_mass: float = 0.0

        logger.info(
            "FizzLifeEngine created: run_id=%s, grid=%d, gens=%d",
            self._run_id,
            self._config.grid_size,
            self._config.generations,
        )

    @property
    def config(self) -> SimulationConfig:
        """Return the simulation configuration."""
        return self._config

    @property
    def grid(self) -> Optional[LeniaGrid]:
        """Return the simulation grid, if initialized."""
        return self._grid

    @property
    def catalog(self) -> SpeciesCatalog:
        """Return the species catalog."""
        return self._catalog

    @property
    def analyzer(self) -> PatternAnalyzer:
        """Return the pattern analyzer."""
        return self._analyzer

    @property
    def run_id(self) -> str:
        """Return the unique run identifier."""
        return self._run_id

    @property
    def events(self) -> list[Event]:
        """Return all events emitted during the simulation."""
        return list(self._events)

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event into the event log.

        Args:
            event_type: The event category.
            payload: Event-specific data.
        """
        event = Event(
            event_type=event_type,
            payload={**payload, "run_id": self._run_id},
            source="FizzLifeEngine",
        )
        self._events.append(event)

    def initialize(self) -> None:
        """Initialize the simulation grid and subsystems.

        Creates the LeniaGrid with the configured parameters, building
        the convolution kernel and FFT structures. This is separated from
        __init__ to allow configuration inspection before committing to
        the computationally expensive initialization.
        """
        self._grid = LeniaGrid(self._config)
        self._emit_event(EventType.FIZZLIFE_SIMULATION_STARTED, {
            "grid_size": self._config.grid_size,
            "generations": self._config.generations,
            "kernel_type": self._config.kernel.kernel_type.name,
            "growth_type": self._config.growth.growth_type.name,
            "mu": self._config.growth.mu,
            "sigma": self._config.growth.sigma,
            "dt": self._config.dt,
            "mass_conservation": self._config.mass_conservation,
        })
        logger.info(
            "FizzLifeEngine initialized: run_id=%s, initial_mass=%.4f",
            self._run_id, self._grid.total_mass(),
        )

    def run(self) -> SimulationResult:
        """Execute the complete simulation and return results.

        Runs the simulation for the configured number of generations
        (or until convergence/extinction is detected), then classifies
        the outcome and returns a SimulationResult.

        Returns:
            The complete simulation result with classification.
        """
        if self._grid is None:
            self.initialize()

        assert self._grid is not None

        self._start_time = time.monotonic()
        reports: list[GenerationReport] = []
        species_history: list[str] = []
        converged = False

        logger.info(
            "FizzLifeEngine simulation started: run_id=%s", self._run_id
        )

        for gen in range(self._config.generations):
            report = self._grid.step()
            reports.append(report)

            # Snapshot grid at peak mass for dashboard visualization
            if report.total_mass > self._peak_mass:
                self._peak_mass = report.total_mass
                self._peak_grid_snapshot = [
                    row[:] for row in self._grid.grid
                ]

            # Check for extinction
            if report.state == SimulationState.EXTINCT:
                logger.info(
                    "Simulation extinct at generation %d: run_id=%s",
                    gen + 1, self._run_id,
                )
                self._emit_event(EventType.FIZZLIFE_SPECIES_EXTINCT, {
                    "reason": "extinction",
                    "generation": gen + 1,
                    "final_mass": report.total_mass,
                })
                break

            # Check for equilibrium
            if self._analyzer.detect_equilibrium(reports):
                converged = True
                self._grid.state = SimulationState.CONVERGED

                # Classify species
                species = self._analyzer.classify_species(self._config)
                if species:
                    report.species_detected = species.name
                    if species.name not in species_history:
                        species_history.append(species.name)

                logger.info(
                    "Simulation converged at generation %d: run_id=%s, "
                    "species=%s",
                    gen + 1, self._run_id,
                    species.name if species else "Unknown",
                )
                self._emit_event(EventType.FIZZLIFE_EQUILIBRIUM_REACHED, {
                    "reason": "convergence",
                    "generation": gen + 1,
                    "final_mass": report.total_mass,
                    "species": species.name if species else None,
                })
                if species:
                    self._emit_event(EventType.FIZZLIFE_SPECIES_DETECTED, {
                        "species": species.name,
                        "family": species.family,
                        "generation": gen + 1,
                    })
                break

            # Emit mass flow event when mass conservation is active
            if self._config.mass_conservation and gen > 0:
                self._emit_event(EventType.FIZZLIFE_MASS_FLOW_COMPUTED, {
                    "generation": gen + 1,
                    "total_mass": report.total_mass,
                    "mass_delta": report.mass_delta,
                })

            # Periodic logging at 10% intervals
            if (gen + 1) % max(1, self._config.generations // 10) == 0:
                self._emit_event(EventType.FIZZLIFE_GENERATION_ADVANCED, {
                    "generation": gen + 1,
                    "total_generations": self._config.generations,
                    "total_mass": report.total_mass,
                    "population": report.population,
                    "mass_delta": report.mass_delta,
                })
                logger.debug(
                    "Generation %d/%d: mass=%.4f, pop=%d, delta=%.6f",
                    gen + 1, self._config.generations,
                    report.total_mass, report.population, report.mass_delta,
                )

        self._end_time = time.monotonic()
        elapsed = self._end_time - self._start_time

        # Determine final state
        if not reports:
            final_state = SimulationState.FAILED
        elif reports[-1].state == SimulationState.EXTINCT:
            final_state = SimulationState.EXTINCT
        elif converged:
            final_state = SimulationState.CONVERGED
        else:
            final_state = SimulationState.RUNNING  # Hit max generations

        # If the simulation survived to max generations without formal
        # convergence, attempt species classification on the final state.
        # Many viable Lenia patterns oscillate indefinitely without
        # meeting the strict equilibrium criterion (mass delta below
        # threshold for the detection window), yet they exhibit stable
        # morphology suitable for classification.
        if final_state == SimulationState.RUNNING and not species_history:
            species = self._analyzer.classify_species(self._config)
            if species:
                if reports:
                    reports[-1].species_detected = species.name
                if species.name not in species_history:
                    species_history.append(species.name)
                logger.info(
                    "Post-simulation classification: run_id=%s, species=%s",
                    self._run_id, species.name,
                )

        # Determine classification
        classification = self._classify_result(
            final_state, species_history, reports
        )

        self._emit_event(EventType.FIZZLIFE_PATTERN_CLASSIFIED, {
            "classification": classification,
            "final_state": final_state.name,
            "generations_run": len(reports),
            "species_history": species_history,
        })

        # Determine mass conservation: check if total mass remained within
        # 1% of initial mass throughout the simulation (Flow-Lenia guarantee)
        mass_conserved = False
        if reports and self._config.mass_conservation:
            initial_mass = reports[0].total_mass
            if initial_mass > 0:
                mass_conserved = all(
                    abs(r.total_mass - initial_mass) / initial_mass < 0.01
                    for r in reports
                )

        result = SimulationResult(
            config=self._config,
            generations_run=len(reports),
            final_population=reports[-1].population if reports else 0,
            final_mass=reports[-1].total_mass if reports else 0.0,
            species_history=species_history,
            classification=classification,
            reports=reports,
            converged=converged,
            mass_conserved=mass_conserved,
        )

        logger.info(
            "FizzLifeEngine simulation complete: run_id=%s, gens=%d, "
            "classification=%r, elapsed=%.3fs",
            self._run_id, len(reports), classification, elapsed,
        )

        return result

    def _classify_result(
        self,
        state: SimulationState,
        species_history: list[str],
        reports: list[GenerationReport],
    ) -> str:
        """Map simulation outcome to FizzBuzz classification.

        The classification logic follows the species catalog mapping:
        - Converged with known Fizz-species -> "Fizz"
        - Converged with known Buzz-species -> "Buzz"
        - Converged with known FizzBuzz-species -> "FizzBuzz"
        - Extinct or unclassified -> "" (plain number)

        Args:
            state: Final simulation state.
            species_history: Species detected during simulation.
            reports: Generation reports for additional heuristics.

        Returns:
            The FizzBuzz classification string.
        """
        if state == SimulationState.EXTINCT:
            return ""

        # Use species classification if available
        for species_name in species_history:
            classification = self._catalog.get_classification(species_name)
            if classification:
                return classification

        # Fallback: classify based on final-state characteristics.
        # When the simulation reaches CONVERGED or RUNNING (max generations
        # without equilibrium detection), the growth parameters determine
        # which species basin the simulation occupied. The mass/population
        # ratio provides a proxy for the emergent pattern class.
        if state in (SimulationState.CONVERGED, SimulationState.RUNNING) and reports:
            final_mass = reports[-1].total_mass
            final_pop = reports[-1].population

            # Heuristic classification based on mass/population ratio
            if final_pop > 0:
                density = final_mass / final_pop
                if density > 0.7:
                    return "Buzz"  # Dense pattern -> Buzz
                elif density > 0.4:
                    return "Fizz"  # Medium density -> Fizz
                else:
                    return "FizzBuzz"  # Sparse pattern -> FizzBuzz

        return ""

    def render_current_state(self, width: int = 64) -> str:
        """Render the current grid as ASCII art.

        Args:
            width: Target display width.

        Returns:
            ASCII representation of the grid state.
        """
        if self._grid is None:
            return "(not initialized)"

        # If the live grid is extinct, render the peak-mass snapshot
        # to show the most interesting state rather than a blank grid.
        current_mass = self._grid.total_mass()
        if current_mass < 1e-10 and self._peak_grid_snapshot is not None:
            return self._render_snapshot(self._peak_grid_snapshot, width)

        return self._grid.render_ascii(width)

    def _render_snapshot(
        self, snapshot: list[list[float]], width: int
    ) -> str:
        """Render a saved grid snapshot as ASCII art.

        Uses the same density character mapping as LeniaGrid.render_ascii
        to produce a consistent visual representation from a raw grid
        snapshot captured during simulation.

        Args:
            snapshot: 2D list of cell states in [0, 1].
            width: Target display width in characters.

        Returns:
            Multi-line ASCII density map.
        """
        size = len(snapshot)
        chars = DENSITY_CHARS
        max_idx = len(chars) - 1
        scale = max(1, size // width)

        lines = []
        for y in range(0, size, scale):
            line = []
            for x in range(0, size, scale):
                val = snapshot[y][x]
                idx = int(val * max_idx)
                idx = max(0, min(max_idx, idx))
                line.append(chars[idx])
            lines.append("".join(line))

        return "\n".join(lines)

    def get_elapsed_time(self) -> Optional[float]:
        """Return elapsed simulation time in seconds, if completed."""
        if self._start_time is not None and self._end_time is not None:
            return self._end_time - self._start_time
        return None


# ============================================================
# Simulation Dashboard
# ============================================================


class FizzLifeDashboard:
    """ASCII dashboard for monitoring FizzLife simulation progress.

    Renders a comprehensive terminal dashboard showing simulation
    statistics, mass evolution, population dynamics, and the current
    grid state. Designed for enterprise-grade observability of the
    FizzBuzz cellular automaton pipeline.
    """

    DASHBOARD_WIDTH = 72

    def __init__(self) -> None:
        self._mass_history: list[float] = []
        self._pop_history: list[int] = []
        self._events: list[Event] = []

    @property
    def events(self) -> list[Event]:
        """Return all events emitted during dashboard rendering."""
        return list(self._events)

    def render(
        self,
        engine: FizzLifeEngine,
        reports: list[GenerationReport],
    ) -> str:
        """Render the full simulation dashboard.

        Args:
            engine: The FizzLife engine instance.
            reports: Generation reports collected so far.

        Returns:
            Multi-line dashboard string for terminal display.
        """
        w = self.DASHBOARD_WIDTH
        lines: list[str] = []

        def border(ch: str = "=") -> str:
            return ch * w

        def center(text: str) -> str:
            return text.center(w)

        def row(text: str) -> str:
            return f"| {text:<{w - 4}} |"

        # Header
        lines.append(border())
        lines.append(center("FIZZLIFE CONTINUOUS CELLULAR AUTOMATON"))
        lines.append(center(f"Engine v{FIZZLIFE_VERSION}"))
        lines.append(border())

        # Configuration summary
        config = engine.config
        lines.append(row(f"Run ID:       {engine.run_id}"))
        lines.append(row(f"Grid:         {config.grid_size}x{config.grid_size}"))
        lines.append(row(f"Kernel:       {config.kernel.kernel_type.name} "
                        f"(R={config.kernel.radius})"))
        lines.append(row(f"Growth:       {config.growth.growth_type.name} "
                        f"(mu={config.growth.mu}, sigma={config.growth.sigma})"))
        lines.append(row(f"dt:           {config.dt}"))
        lines.append(row(f"Flow mode:    {'ON' if config.mass_conservation else 'OFF'}"))
        lines.append(border("-"))

        if reports:
            latest = reports[-1]
            lines.append(row(f"Generation:   {latest.generation}/{config.generations}"))
            lines.append(row(f"Population:   {latest.population}"))
            lines.append(row(f"Total Mass:   {latest.total_mass:.6f}"))
            lines.append(row(f"Mass Delta:   {latest.mass_delta:+.8f}"))
            lines.append(row(f"State:        {latest.state.name}"))

            if latest.species_detected:
                lines.append(row(f"Species:      {latest.species_detected}"))

            # Build full mass and population history from all reports.
            # Previous implementation only appended the latest report,
            # yielding a single data point when rendered post-simulation.
            self._mass_history = [r.total_mass for r in reports]
            self._pop_history = [r.population for r in reports]

            lines.append(border("-"))
            lines.append(center("MASS EVOLUTION"))
            lines.append(border("-"))
            sparkline = self._render_sparkline(
                self._mass_history[-60:], w - 4
            )
            lines.append(row(sparkline))

            lines.append(border("-"))
            lines.append(center("POPULATION"))
            lines.append(border("-"))
            pop_floats = [float(p) for p in self._pop_history[-60:]]
            pop_spark = self._render_sparkline(pop_floats, w - 4)
            lines.append(row(pop_spark))
        else:
            lines.append(row("(awaiting first generation)"))

        # Grid visualization — show peak-mass snapshot when grid is extinct
        is_peak_snapshot = (
            engine.grid is not None
            and engine.grid.total_mass() < 1e-10
            and engine._peak_grid_snapshot is not None
        )
        grid_label = "GRID STATE (PEAK MASS)" if is_peak_snapshot else "GRID STATE"
        lines.append(border("-"))
        lines.append(center(grid_label))
        lines.append(border("-"))
        grid_str = engine.render_current_state(width=w - 4)
        for grid_line in grid_str.split("\n")[:20]:  # Limit height
            lines.append(row(grid_line))

        # Elapsed time
        elapsed = engine.get_elapsed_time()
        if elapsed is not None:
            lines.append(border("-"))
            lines.append(row(f"Elapsed:      {elapsed:.3f}s"))

        lines.append(border())

        self._events.append(Event(
            event_type=EventType.FIZZLIFE_DASHBOARD_RENDERED,
            payload={
                "run_id": engine.run_id,
                "generations_displayed": len(reports),
                "dashboard_width": self.DASHBOARD_WIDTH,
            },
            source="FizzLifeDashboard",
        ))

        return "\n".join(lines)

    @staticmethod
    def _render_sparkline(values: list[float], width: int) -> str:
        """Render a sparkline chart using Unicode block characters.

        Args:
            values: Data points to visualize.
            width: Target width in characters.

        Returns:
            Single-line sparkline string.
        """
        if not values:
            return " " * width

        blocks = " _.,:-=!#"
        max_val = max(values) if values else 1.0
        min_val = min(values) if values else 0.0
        val_range = max_val - min_val

        # Downsample or pad to fit width
        if len(values) > width:
            step = len(values) / width
            sampled = []
            for i in range(width):
                idx = int(i * step)
                sampled.append(values[min(idx, len(values) - 1)])
            values = sampled

        result = []
        for val in values:
            if val_range > 0:
                normalized = (val - min_val) / val_range
            else:
                normalized = 0.5
            idx = int(normalized * (len(blocks) - 1))
            idx = max(0, min(len(blocks) - 1, idx))
            result.append(blocks[idx])

        line = "".join(result)
        # Pad to width
        if len(line) < width:
            line = line + " " * (width - len(line))
        return line[:width]


# ============================================================
# Convenience Functions
# ============================================================


def run_animated(
    config: Optional[SimulationConfig] = None,
    fps: int = 10,
) -> None:
    """Run a live animated FizzLife simulation in the terminal.

    Renders each generation of the cellular automaton in real time,
    clearing the screen between frames to produce a fluid animation
    of emergent Lenia dynamics. The display includes the grid state
    as an ASCII density map, generation counter, population statistics,
    and mass trajectory.

    This is the FizzLife showcase mode: a full-size simulation rendered
    at the specified frame rate so the operator can observe the
    spatiotemporal patterns that underpin FizzBuzz classification.

    Args:
        config: Simulation configuration. Defaults to a 64x64 grid
            with 500 generations and default Lenia parameters.
        fps: Target frames per second for the animation.
    """
    import sys

    if config is None:
        config = SimulationConfig(
            grid_size=64,
            generations=500,
            seed=42,
        )

    engine = FizzLifeEngine(config)
    engine.initialize()

    grid = engine._grid
    assert grid is not None

    frame_delay = 1.0 / fps
    chars = DENSITY_CHARS
    max_idx = len(chars) - 1
    size = config.grid_size
    scale = max(1, size // 64)

    mass_history: list[float] = []
    pop_history: list[int] = []

    for gen in range(config.generations):
        start = time.monotonic()

        report = grid.step()
        mass_history.append(report.total_mass)
        pop_history.append(report.population)

        if report.state == SimulationState.EXTINCT:
            # Show final frame before exiting
            pass

        # Build the frame
        lines: list[str] = []
        lines.append("\033[2J\033[H")  # Clear screen, cursor to top
        lines.append("=" * 68)
        lines.append(
            f"  FIZZLIFE LIVE  |  Gen {gen + 1:>4d}/{config.generations}  "
            f"|  Pop: {report.population:>5d}  |  Mass: {report.total_mass:>8.1f}"
        )
        lines.append("=" * 68)

        # Render grid
        for y in range(0, size, scale):
            row_chars: list[str] = []
            for x in range(0, size, scale):
                val = grid._grid[y][x]
                idx = int(val * max_idx)
                idx = max(0, min(max_idx, idx))
                row_chars.append(chars[idx])
            lines.append("  " + "".join(row_chars))

        # Mass sparkline (last 60 values)
        lines.append("-" * 68)
        recent_mass = mass_history[-60:]
        if recent_mass:
            max_m = max(recent_mass) or 1.0
            spark_chars = " _.,:-=!#"
            spark = []
            for m in recent_mass:
                si = int(m / max_m * (len(spark_chars) - 1))
                si = max(0, min(len(spark_chars) - 1, si))
                spark.append(spark_chars[si])
            lines.append(f"  Mass: {''.join(spark)}")

        # State info
        state_name = report.state.name if hasattr(report, 'state') else "RUNNING"
        lines.append(f"  State: {state_name}  |  dt={config.dt}  |  R={config.kernel.radius}")
        lines.append("=" * 68)

        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()

        if report.state == SimulationState.EXTINCT:
            sys.stdout.write(f"\n\n  ** EXTINCT at generation {gen + 1} **\n")
            break

        # Frame timing
        elapsed = time.monotonic() - start
        sleep_time = frame_delay - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Final summary
    species = engine._analyzer.classify_species(config)
    species_name = species.name if species else "Unknown"
    classification = engine._classify_result(
        grid.state, [species_name] if species else [], []
    )
    sys.stdout.write(
        f"\n  Species: {species_name}"
        f"\n  Classification: {classification or '(plain number)'}"
        f"\n  Final mass: {report.total_mass:.2f}"
        f"\n  Generations: {gen + 1}\n"
    )


def create_default_config() -> SimulationConfig:
    """Create a SimulationConfig with default parameters.

    The defaults are calibrated for the Orbium unicaudatus species,
    providing a reliable baseline for FizzBuzz evaluation.

    Returns:
        A SimulationConfig with standard Lenia parameters.
    """
    return SimulationConfig()


def create_species_config(species_name: str) -> Optional[SimulationConfig]:
    """Create a SimulationConfig tuned for a specific Lenia species.

    Looks up the species in the catalog and returns a configuration
    with the species' characteristic kernel and growth parameters.

    Args:
        species_name: The species to configure for (e.g., "Orbium unicaudatus").

    Returns:
        A SimulationConfig for the species, or None if not found.
    """
    catalog = SpeciesCatalog()
    for species in catalog.species:
        if species.name == species_name:
            return SimulationConfig(
                kernel=KernelConfig(
                    kernel_type=species.kernel_config.kernel_type,
                    radius=species.kernel_config.radius,
                    rank=species.kernel_config.rank,
                    beta=list(species.kernel_config.beta),
                    center_weight=species.kernel_config.center_weight,
                ),
                growth=GrowthConfig(
                    growth_type=species.growth_config.growth_type,
                    mu=species.growth_config.mu,
                    sigma=species.growth_config.sigma,
                ),
            )
    return None


def run_simulation(
    config: Optional[SimulationConfig] = None,
) -> SimulationResult:
    """Run a complete FizzLife simulation with the given configuration.

    Convenience function that creates an engine, initializes it, runs
    the simulation, and returns the result.

    Args:
        config: Simulation configuration. Uses defaults if None.

    Returns:
        The complete SimulationResult.
    """
    engine = FizzLifeEngine(config)
    return engine.run()


def _growth_config_for_number(n: int) -> GrowthConfig:
    """Map an integer to a point in Lenia growth-function parameter space.

    The FizzBuzz classification of a number is ultimately determined by
    which Lenia species emerges from the simulation. Different species
    occupy distinct regions of (mu, sigma) parameter space, so by
    selecting growth parameters based on the number's modular arithmetic
    properties, we ensure that the cellular automaton naturally evolves
    toward the species whose FizzBuzz classification matches the input.

    The mapping targets well-characterized species in the catalog:
        - n divisible by 15: Triscutium triplex region   -> "FizzBuzz"
        - n divisible by 3:  Orbium unicaudatus region   -> "Fizz"
        - n divisible by 5:  Scutium gravidus region     -> "Buzz"
        - otherwise:         Sub-threshold neutral zone  -> "" (number)

    A deterministic perturbation derived from the input number shifts
    each configuration slightly within its species basin, producing
    morphological variation across evaluations without crossing species
    boundaries. This ensures that while all multiples of 3 converge to
    Orbium-family patterns, no two simulations are byte-identical.

    Args:
        n: The integer to map into parameter space.

    Returns:
        A GrowthConfig positioned in the appropriate species basin.
    """
    # Deterministic hash for per-number perturbation within the species
    # basin. The Knuth multiplicative hash provides good dispersion
    # across the 32-bit range without cryptographic overhead.
    h = (abs(n) * 2654435761) & 0xFFFFFFFF
    # Signed perturbation centered at zero: range [-0.002, +0.002).
    # This keeps each number's parameters firmly within its target
    # species basin while still producing per-number variation in the
    # simulation dynamics.
    perturbation = ((h % 1000) - 500) / 250000.0

    if n % 15 == 0:
        # Triscutium triplex -- triple shield compound organism
        # Catalog parameters: mu=0.4, sigma=0.0797
        return GrowthConfig(
            growth_type=GrowthType.GAUSSIAN,
            mu=0.4 + perturbation,
            sigma=0.0797 + perturbation * 0.5,
        )
    elif n % 3 == 0:
        # Orbium unicaudatus -- translating soliton
        # Catalog parameters: mu=0.15, sigma=0.015
        return GrowthConfig(
            growth_type=GrowthType.GAUSSIAN,
            mu=0.15 + perturbation,
            sigma=0.015 + perturbation * 0.5,
        )
    elif n % 5 == 0:
        # Scutium gravidus -- dense shield pattern
        # Catalog parameters: mu=0.29, sigma=0.045
        return GrowthConfig(
            growth_type=GrowthType.GAUSSIAN,
            mu=0.29 + perturbation,
            sigma=0.045 + perturbation * 0.5,
        )
    else:
        # Neutral zone: parameters far from any cataloged species.
        # The growth center at mu=0.55 with narrow sigma=0.01 places
        # the configuration well outside the attraction basin of every
        # known species (nearest is Triscutium at mu=0.4, distance >0.15).
        # Simulations in this region consistently fail to sustain viable
        # patterns, leading to extinction and a plain-number classification.
        return GrowthConfig(
            growth_type=GrowthType.GAUSSIAN,
            mu=0.55 + perturbation,
            sigma=0.01 + abs(perturbation) * 0.5,
        )


def classify_number(n: int, config: Optional[SimulationConfig] = None) -> str:
    """Classify a single number using FizzLife simulation.

    Seeds the simulation with a deterministic initial condition derived
    from the input number, runs the simulation, and returns the
    FizzBuzz classification.

    This is the primary integration point between FizzLife and the
    broader Enterprise FizzBuzz Platform: each number evaluation
    triggers a complete cellular automaton simulation, ensuring that
    every FizzBuzz result is grounded in emergent self-organization
    rather than mere arithmetic.

    Args:
        n: The number to classify.
        config: Optional simulation configuration override.

    Returns:
        "Fizz", "Buzz", "FizzBuzz", or "" (plain number).
    """
    if config is None:
        config = SimulationConfig(
            grid_size=MIDDLEWARE_GRID_SIZE,
            generations=MIDDLEWARE_GENERATIONS,
        )

    # Map the input number to species-specific growth parameters.
    # Each number's divisibility properties select a distinct region
    # of Lenia parameter space, ensuring that the emergent pattern
    # classification naturally corresponds to the correct FizzBuzz output.
    growth = _growth_config_for_number(n)

    seeded_config = SimulationConfig(
        grid_size=MIDDLEWARE_GRID_SIZE,
        generations=MIDDLEWARE_GENERATIONS,
        dt=config.dt,
        kernel=config.kernel,
        growth=growth,
        channels=config.channels,
        mass_conservation=config.mass_conservation,
        initial_density=config.initial_density,
        seed=n,
        seed_mode=config.seed_mode,
    )

    result = run_simulation(seeded_config)
    return result.classification


# ============================================================
# FizzLife Middleware
# ============================================================


class FizzLifeMiddleware:
    """Pipeline middleware that routes each FizzBuzz evaluation through a
    Flow-Lenia continuous cellular automaton simulation.

    For every number in the processing pipeline, the middleware seeds an
    initial condition on a toroidal grid, evolves the system under the
    configured kernel and growth functions, and annotates the processing
    context with the simulation result. This ensures that every FizzBuzz
    classification is grounded in emergent spatiotemporal dynamics rather
    than mere arithmetic.

    The middleware stores per-evaluation generation reports and the final
    simulation result in the context metadata under the ``fizzlife``
    namespace, enabling downstream middleware and dashboards to inspect
    simulation telemetry.
    """

    PRIORITY = 930

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        event_bus: Optional[object] = None,
        verbose: bool = False,
    ) -> None:
        self._config = config or SimulationConfig()
        self._event_bus = event_bus
        self._verbose = verbose
        self._engine: Optional[FizzLifeEngine] = None
        self._reports: list[GenerationReport] = []
        self._total_simulations: int = 0
        self._total_mass_conserved: int = 0

    def process(self, context: object, next_handler: object) -> object:
        """Run a FizzLife simulation for the current number and annotate
        the processing context before delegating to the next handler.

        Args:
            context: The ProcessingContext carrying the current number.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processed context with fizzlife metadata attached.
        """
        number = getattr(context, "number", 0)

        # Map the number to species-specific growth parameters so
        # that the simulation targets the correct Lenia species basin.
        growth = _growth_config_for_number(number)

        # Build a per-number config using the fast middleware defaults.
        # Classification is determined by species parameter matching, not
        # by long-term pattern evolution, so a small grid and few
        # generations are sufficient for accurate results.
        seeded_config = SimulationConfig(
            grid_size=MIDDLEWARE_GRID_SIZE,
            generations=MIDDLEWARE_GENERATIONS,
            dt=self._config.dt,
            kernel=self._config.kernel,
            growth=growth,
            channels=self._config.channels,
            mass_conservation=self._config.mass_conservation,
            initial_density=self._config.initial_density,
            seed=number,
            seed_mode=self._config.seed_mode,
        )

        engine = FizzLifeEngine(seeded_config)
        result = engine.run()
        self._total_simulations += 1

        # Progress indicator: print inline status to stderr.
        # The carriage return overwrites the previous line, producing
        # a live-updating counter without scrolling the output.
        import sys
        label = result.classification or str(number)
        sys.stderr.write(
            f"\r  FizzLife: simulating n={number:<6d} -> {label:<8s} "
            f"[{self._total_simulations} done, {result.final_mass:.1f} mass]"
        )
        sys.stderr.flush()

        # Track mass conservation fidelity
        if result.mass_conserved:
            self._total_mass_conserved += 1

        # Store engine for dashboard rendering
        self._engine = engine
        self._reports = result.generation_reports

        # Annotate context metadata
        metadata = getattr(context, "metadata", {})
        metadata["fizzlife"] = {
            "classification": result.classification,
            "final_mass": result.final_mass,
            "final_population": result.final_population,
            "generations_run": result.generations_run,
            "converged": result.converged,
            "mass_conserved": result.mass_conserved,
            "run_id": engine.run_id,
        }

        if self._verbose:
            metadata["fizzlife"]["generation_reports"] = [
                {
                    "generation": r.generation,
                    "total_mass": r.total_mass,
                    "population": r.population,
                    "mass_delta": r.mass_delta,
                    "state": r.state.name,
                }
                for r in result.generation_reports
            ]

        return next_handler(context)

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "FizzLifeMiddleware"

    def get_priority(self) -> int:
        """Return the middleware execution priority."""
        return self.PRIORITY

    @property
    def engine(self) -> Optional[FizzLifeEngine]:
        """Return the most recently used engine instance."""
        return self._engine

    @property
    def reports(self) -> list[GenerationReport]:
        """Return generation reports from the most recent simulation."""
        return self._reports

    @property
    def total_simulations(self) -> int:
        """Return the total number of simulations executed."""
        return self._total_simulations

    def render_stats(self) -> str:
        """Render a summary of all simulations run through this middleware."""
        # Clear the progress line from stderr
        import sys
        sys.stderr.write("\r" + " " * 80 + "\r")
        sys.stderr.flush()
        lines = [
            "FizzLife Middleware Statistics",
            f"  Total Simulations:    {self._total_simulations}",
            f"  Mass Conserved:       {self._total_mass_conserved}/{self._total_simulations}",
        ]
        if self._engine is not None:
            elapsed = self._engine.get_elapsed_time()
            if elapsed is not None:
                lines.append(f"  Last Elapsed:         {elapsed:.4f}s")
        return "\n".join(lines)


# ============================================================
# FizzLife Species Evolver (Genetic Algorithm)
# ============================================================


class FizzLifeEvolver:
    """Genetic algorithm for discovering novel Lenia species that produce
    interesting FizzBuzz classification patterns.

    The evolver maintains a population of SimulationConfig individuals,
    each encoding a unique combination of kernel parameters, growth
    functions, and initial conditions. Fitness is evaluated by running
    each configuration through the FizzLifeEngine and measuring:

    - **Pattern complexity**: Higher mass and population indicate richer
      emergent behavior.
    - **Classification diversity**: Configurations that produce varied
      FizzBuzz outputs across multiple seeds score higher.
    - **Stability**: Configurations that converge reliably without
      extinction are preferred.

    Selection uses tournament selection, crossover blends kernel and
    growth parameters from two parents, and mutation perturbs parameters
    within biologically plausible ranges.
    """

    def __init__(
        self,
        population_size: int = 20,
        generations: int = 50,
        mutation_rate: float = 0.2,
        crossover_rate: float = 0.7,
        seed: Optional[int] = None,
    ) -> None:
        self._population_size = population_size
        self._generations = generations
        self._mutation_rate = mutation_rate
        self._crossover_rate = crossover_rate
        self._rng = random.Random(seed)
        self._best_configs: list[tuple[float, SimulationConfig]] = []
        self._events: list[Event] = []

    @property
    def events(self) -> list[Event]:
        """Return all events emitted during evolution."""
        return list(self._events)

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event into the event log."""
        self._events.append(Event(
            event_type=event_type,
            payload=payload,
            source="FizzLifeEvolver",
        ))

    def evolve(self) -> list[tuple[float, SimulationConfig]]:
        """Run the evolutionary search and return the top configurations.

        Returns:
            A list of (fitness, config) tuples sorted by descending fitness.
        """
        # Initialize population with random configurations
        population = [self._random_config() for _ in range(self._population_size)]

        self._emit_event(EventType.FIZZLIFE_EVOLUTION_STARTED, {
            "population_size": self._population_size,
            "generations": self._generations,
            "mutation_rate": self._mutation_rate,
            "crossover_rate": self._crossover_rate,
        })

        for gen in range(self._generations):
            # Evaluate fitness
            scored = [(self._evaluate_fitness(cfg), cfg) for cfg in population]
            scored.sort(key=lambda x: x[0], reverse=True)

            # Elitism: keep top 10%
            elite_count = max(2, self._population_size // 10)
            next_gen = [cfg for _, cfg in scored[:elite_count]]

            # Fill remaining slots with crossover and mutation
            while len(next_gen) < self._population_size:
                parent_a = self._tournament_select(scored)
                parent_b = self._tournament_select(scored)

                if self._rng.random() < self._crossover_rate:
                    child = self._crossover(parent_a, parent_b)
                else:
                    child = self._clone_config(parent_a)

                if self._rng.random() < self._mutation_rate:
                    child = self._mutate(child)

                next_gen.append(child)

            population = next_gen

            self._emit_event(EventType.FIZZLIFE_EVOLUTION_GENERATION, {
                "generation": gen + 1,
                "total_generations": self._generations,
                "best_fitness": scored[0][0] if scored else 0.0,
                "elite_count": elite_count,
            })

        # Final evaluation
        final_scored = [(self._evaluate_fitness(cfg), cfg) for cfg in population]
        final_scored.sort(key=lambda x: x[0], reverse=True)
        self._best_configs = final_scored[:10]
        return self._best_configs

    def render_results(self) -> str:
        """Render evolution results as an ASCII report."""
        if not self._best_configs:
            return "(no evolution results — run evolve() first)"

        lines = [
            "=" * 60,
            "FIZZLIFE SPECIES EVOLVER RESULTS".center(60),
            "=" * 60,
            f"  Population: {self._population_size}  Generations: {self._generations}",
            f"  Mutation Rate: {self._mutation_rate}  Crossover Rate: {self._crossover_rate}",
            "-" * 60,
        ]

        for rank, (fitness, cfg) in enumerate(self._best_configs, 1):
            lines.append(
                f"  #{rank:>2}  Fitness: {fitness:.4f}  "
                f"Kernel: {cfg.kernel.kernel_type.name}(R={cfg.kernel.radius})  "
                f"Growth: mu={cfg.growth.mu:.4f} sigma={cfg.growth.sigma:.4f}"
            )

        lines.append("=" * 60)
        return "\n".join(lines)

    def _random_config(self) -> SimulationConfig:
        """Generate a random SimulationConfig within plausible ranges."""
        kernel_type = self._rng.choice(list(KernelType))
        radius = self._rng.randint(5, 25)
        mu = self._rng.uniform(0.05, 0.35)
        sigma = self._rng.uniform(0.005, 0.05)
        dt = self._rng.uniform(0.05, 0.2)

        return SimulationConfig(
            grid_size=32,  # Smaller grid for faster evolution
            generations=50,  # Fewer generations for fitness evaluation
            dt=dt,
            kernel=KernelConfig(kernel_type=kernel_type, radius=radius),
            growth=GrowthConfig(mu=mu, sigma=sigma),
            seed=self._rng.randint(0, 2**31),
        )

    def _evaluate_fitness(self, config: SimulationConfig) -> float:
        """Evaluate fitness of a configuration by running simulations."""
        total_fitness = 0.0
        test_numbers = [3, 5, 7, 15, 17, 30]

        for n in test_numbers:
            seeded = SimulationConfig(
                grid_size=config.grid_size,
                generations=config.generations,
                dt=config.dt,
                kernel=config.kernel,
                growth=config.growth,
                channels=config.channels,
                mass_conservation=config.mass_conservation,
                initial_density=config.initial_density,
                seed=n,
                seed_mode=config.seed_mode,
            )
            try:
                engine = FizzLifeEngine(seeded)
                result = engine.run()

                # Reward pattern complexity
                total_fitness += min(result.final_mass, 10.0) * 0.3
                total_fitness += min(result.final_population, 500) / 500.0 * 0.3

                # Reward convergence (not extinction)
                if result.converged and result.final_population > 0:
                    total_fitness += 0.2

                # Reward classification diversity
                if result.classification:
                    total_fitness += 0.2
            except Exception:
                pass  # Configurations that crash get zero fitness

        return total_fitness / len(test_numbers)

    def _tournament_select(
        self, scored: list[tuple[float, SimulationConfig]], k: int = 3
    ) -> SimulationConfig:
        """Select a configuration via tournament selection."""
        tournament = self._rng.sample(scored, min(k, len(scored)))
        return max(tournament, key=lambda x: x[0])[1]

    def _crossover(
        self, a: SimulationConfig, b: SimulationConfig
    ) -> SimulationConfig:
        """Blend two parent configurations."""
        alpha = self._rng.random()
        mu = a.growth.mu * alpha + b.growth.mu * (1 - alpha)
        sigma = a.growth.sigma * alpha + b.growth.sigma * (1 - alpha)
        dt = a.dt * alpha + b.dt * (1 - alpha)
        radius = int(a.kernel.radius * alpha + b.kernel.radius * (1 - alpha))
        kernel_type = self._rng.choice([a.kernel.kernel_type, b.kernel.kernel_type])

        return SimulationConfig(
            grid_size=a.grid_size,
            generations=a.generations,
            dt=dt,
            kernel=KernelConfig(kernel_type=kernel_type, radius=max(3, radius)),
            growth=GrowthConfig(mu=mu, sigma=sigma),
            seed=self._rng.randint(0, 2**31),
        )

    def _mutate(self, config: SimulationConfig) -> SimulationConfig:
        """Perturb a configuration's parameters."""
        mu = config.growth.mu + self._rng.gauss(0, 0.02)
        sigma = config.growth.sigma + self._rng.gauss(0, 0.005)
        dt = config.dt + self._rng.gauss(0, 0.01)
        radius = config.kernel.radius + self._rng.choice([-1, 0, 1])

        return SimulationConfig(
            grid_size=config.grid_size,
            generations=config.generations,
            dt=max(0.01, dt),
            kernel=KernelConfig(
                kernel_type=config.kernel.kernel_type,
                radius=max(3, min(30, radius)),
            ),
            growth=GrowthConfig(
                mu=max(0.01, min(0.5, mu)),
                sigma=max(0.001, min(0.1, sigma)),
            ),
            seed=self._rng.randint(0, 2**31),
        )

    def _clone_config(self, config: SimulationConfig) -> SimulationConfig:
        """Create an independent copy of a configuration."""
        return SimulationConfig(
            grid_size=config.grid_size,
            generations=config.generations,
            dt=config.dt,
            kernel=KernelConfig(
                kernel_type=config.kernel.kernel_type,
                radius=config.kernel.radius,
                rank=config.kernel.rank,
                beta=list(config.kernel.beta),
                center_weight=config.kernel.center_weight,
            ),
            growth=GrowthConfig(
                growth_type=config.growth.growth_type,
                mu=config.growth.mu,
                sigma=config.growth.sigma,
            ),
            channels=config.channels,
            mass_conservation=config.mass_conservation,
            initial_density=config.initial_density,
            seed=config.seed,
            seed_mode=config.seed_mode,
        )


# ============================================================
# Subsystem Factory
# ============================================================


def create_fizzlife_subsystem(
    grid_size: int = DEFAULT_GRID_SIZE,
    generations: int = DEFAULT_GENERATIONS,
    kernel_type: str = "exponential",
    kernel_radius: int = DEFAULT_KERNEL_RADIUS,
    kernel_rank: int = 1,
    growth_mu: float = DEFAULT_MU,
    growth_sigma: float = DEFAULT_SIGMA,
    dt: float = DEFAULT_DT,
    channels: int = 1,
    mass_conservation: bool = False,
    seed: Optional[int] = None,
    seed_mode: SeedMode = SeedMode.GAUSSIAN_BLOB,
    verbose: bool = False,
    event_bus: Optional[object] = None,
) -> tuple:
    """Create and wire the FizzLife subsystem components.

    Instantiates the simulation configuration, middleware, dashboard, and
    species catalog according to the provided parameters. Returns all
    components as a tuple for integration with the platform's composition
    root.

    Args:
        grid_size: Grid dimensions NxN.
        generations: Number of simulation generations.
        kernel_type: Kernel core function type.
        kernel_radius: Convolution kernel radius R.
        kernel_rank: Number of concentric kernel rings.
        growth_mu: Growth function center parameter.
        growth_sigma: Growth function width parameter.
        dt: Simulation time step.
        channels: Number of state channels.
        mass_conservation: Whether to enforce mass conservation.
        seed: Random seed for reproducibility.
        seed_mode: Grid initialization strategy.
        verbose: Enable verbose metadata logging.
        event_bus: Optional event bus for subsystem events.

    Returns:
        Tuple of (middleware, dashboard, catalog, config).
    """
    # Map kernel type string to enum
    kernel_type_map = {kt.value: kt for kt in KernelType}
    resolved_kernel = kernel_type_map.get(kernel_type, KernelType.EXPONENTIAL)

    config = SimulationConfig(
        grid_size=grid_size,
        generations=generations,
        dt=dt,
        kernel=KernelConfig(
            kernel_type=resolved_kernel,
            radius=kernel_radius,
            rank=kernel_rank,
        ),
        growth=GrowthConfig(
            mu=growth_mu,
            sigma=growth_sigma,
        ),
        channels=channels,
        mass_conservation=mass_conservation,
        seed=seed,
        seed_mode=seed_mode,
    )

    middleware = FizzLifeMiddleware(
        config=config,
        event_bus=event_bus,
        verbose=verbose,
    )
    dashboard = FizzLifeDashboard()
    catalog = SpeciesCatalog()

    return middleware, dashboard, catalog, config

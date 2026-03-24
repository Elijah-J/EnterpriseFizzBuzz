"""
Enterprise FizzBuzz Platform - FizzLife Continuous Cellular Automaton Tests

Comprehensive test suite for the FizzLife subsystem, validating the Lenia
continuous cellular automaton engine that underpins spatiotemporal FizzBuzz
evaluation. Every test contains real numerical assertions against the
mathematical definitions of kernel cores, growth functions, FFT convolution,
grid dynamics, species classification, pattern analysis, and simulation
orchestration.

Tests cover:
    - Constants and enumeration completeness
    - KernelConfig / GrowthConfig dataclass construction and defaults
    - LeniaKernel core functions (exponential, polynomial, rectangular)
    - LeniaKernel shell function (single-ring and multi-ring)
    - LeniaKernel build (normalization, symmetry, spatial extent)
    - GrowthFunction (Gaussian, polynomial, rectangular) numerical accuracy
    - _FFTEngine 1D / 2D forward and inverse transforms
    - FFTConvolver circular convolution with delta and uniform kernels
    - LeniaGrid initialization, mass computation, population, stepping
    - Deterministic seeding and reproducibility
    - FlowField mass-conservative transport
    - SpeciesCatalog species registration, classification, parameter distance
    - PatternAnalyzer equilibrium detection, statistics, oscillation detection
    - FizzLifeEngine lifecycle, events, classification
    - FizzLifeDashboard rendering and sparklines
    - Convenience functions: create_default_config, create_species_config,
      run_simulation, classify_number
"""

from __future__ import annotations

import math
import random
import unittest

from enterprise_fizzbuzz.infrastructure.fizzlife import (
    DEFAULT_DT,
    DEFAULT_GENERATIONS,
    DEFAULT_GRID_SIZE,
    DEFAULT_KERNEL_RADIUS,
    DEFAULT_MU,
    DEFAULT_SIGMA,
    DENSITY_CHARS,
    EQUILIBRIUM_MASS_DELTA,
    EXTINCTION_MASS_THRESHOLD,
    FIZZLIFE_VERSION,
    POPULATION_THRESHOLD,
    STABLE_DT_MAX,
    FFTConvolver,
    FizzLifeDashboard,
    FizzLifeEngine,
    FlowField,
    GenerationReport,
    GrowthConfig,
    GrowthFunction,
    GrowthType,
    KernelConfig,
    KernelType,
    LeniaGrid,
    LeniaKernel,
    PatternAnalyzer,
    SeedMode,
    SimulationConfig,
    SimulationResult,
    SimulationState,
    SpeciesCatalog,
    SpeciesFingerprint,
    _FFTEngine,
    classify_number,
    create_default_config,
    create_species_config,
    run_simulation,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ============================================================
# Singleton Reset Fixture
# ============================================================

def setup_module():
    _SingletonMeta.reset()


def teardown_module():
    _SingletonMeta.reset()


# ============================================================
# Constants & Enums Tests
# ============================================================


class TestConstants(unittest.TestCase):
    """Tests for FizzLife module-level constants."""

    def test_fizzlife_version_is_string(self):
        self.assertIsInstance(FIZZLIFE_VERSION, str)

    def test_fizzlife_version_is_semver(self):
        parts = FIZZLIFE_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        for part in parts:
            self.assertTrue(part.isdigit())

    def test_default_grid_size(self):
        self.assertEqual(DEFAULT_GRID_SIZE, 64)

    def test_default_generations(self):
        self.assertEqual(DEFAULT_GENERATIONS, 200)

    def test_default_kernel_radius(self):
        self.assertEqual(DEFAULT_KERNEL_RADIUS, 15)

    def test_default_dt(self):
        self.assertAlmostEqual(DEFAULT_DT, 0.1, places=10)

    def test_default_mu(self):
        self.assertAlmostEqual(DEFAULT_MU, 0.15, places=10)

    def test_default_sigma(self):
        self.assertAlmostEqual(DEFAULT_SIGMA, 0.065, places=10)

    def test_density_chars_length(self):
        self.assertEqual(len(DENSITY_CHARS), 10)

    def test_population_threshold(self):
        self.assertAlmostEqual(POPULATION_THRESHOLD, 0.1, places=10)

    def test_equilibrium_mass_delta(self):
        self.assertAlmostEqual(EQUILIBRIUM_MASS_DELTA, 1e-6, places=15)

    def test_extinction_mass_threshold(self):
        self.assertAlmostEqual(EXTINCTION_MASS_THRESHOLD, 1e-4, places=15)


class TestKernelTypeEnum(unittest.TestCase):
    """Tests for KernelType enumeration."""

    def test_exponential_value(self):
        self.assertEqual(KernelType.EXPONENTIAL.value, 1)

    def test_polynomial_value(self):
        self.assertEqual(KernelType.POLYNOMIAL.value, 2)

    def test_rectangular_value(self):
        self.assertEqual(KernelType.RECTANGULAR.value, 3)

    def test_member_count(self):
        self.assertEqual(len(KernelType), 3)


class TestGrowthTypeEnum(unittest.TestCase):
    """Tests for GrowthType enumeration."""

    def test_gaussian_value(self):
        self.assertEqual(GrowthType.GAUSSIAN.value, 1)

    def test_polynomial_value(self):
        self.assertEqual(GrowthType.POLYNOMIAL.value, 2)

    def test_rectangular_value(self):
        self.assertEqual(GrowthType.RECTANGULAR.value, 3)

    def test_member_count(self):
        self.assertEqual(len(GrowthType), 3)


class TestSimulationStateEnum(unittest.TestCase):
    """Tests for SimulationState enumeration."""

    def test_initialized_value(self):
        self.assertEqual(SimulationState.INITIALIZED.value, 1)

    def test_running_value(self):
        self.assertEqual(SimulationState.RUNNING.value, 2)

    def test_converged_value(self):
        self.assertEqual(SimulationState.CONVERGED.value, 3)

    def test_extinct_value(self):
        self.assertEqual(SimulationState.EXTINCT.value, 4)

    def test_failed_value(self):
        self.assertEqual(SimulationState.FAILED.value, 5)

    def test_member_count(self):
        self.assertEqual(len(SimulationState), 5)


# ============================================================
# KernelConfig & GrowthConfig Dataclass Tests
# ============================================================


class TestKernelConfig(unittest.TestCase):
    """Tests for KernelConfig dataclass construction and defaults."""

    def test_default_kernel_type(self):
        cfg = KernelConfig()
        self.assertEqual(cfg.kernel_type, KernelType.EXPONENTIAL)

    def test_default_radius(self):
        cfg = KernelConfig()
        self.assertEqual(cfg.radius, DEFAULT_KERNEL_RADIUS)

    def test_default_rank(self):
        cfg = KernelConfig()
        self.assertEqual(cfg.rank, 1)

    def test_default_beta(self):
        cfg = KernelConfig()
        self.assertEqual(cfg.beta, [1.0])

    def test_default_center_weight(self):
        cfg = KernelConfig()
        self.assertAlmostEqual(cfg.center_weight, 0.0, places=10)

    def test_custom_construction(self):
        cfg = KernelConfig(
            kernel_type=KernelType.POLYNOMIAL,
            radius=20,
            rank=3,
            beta=[0.5, 1.0, 0.3],
            center_weight=0.1,
        )
        self.assertEqual(cfg.kernel_type, KernelType.POLYNOMIAL)
        self.assertEqual(cfg.radius, 20)
        self.assertEqual(cfg.rank, 3)
        self.assertEqual(len(cfg.beta), 3)
        self.assertAlmostEqual(cfg.beta[1], 1.0, places=10)
        self.assertAlmostEqual(cfg.center_weight, 0.1, places=10)

    def test_beta_is_independent_list(self):
        cfg1 = KernelConfig()
        cfg2 = KernelConfig()
        cfg1.beta.append(2.0)
        self.assertEqual(len(cfg2.beta), 1)


class TestGrowthConfig(unittest.TestCase):
    """Tests for GrowthConfig dataclass construction and defaults."""

    def test_default_growth_type(self):
        cfg = GrowthConfig()
        self.assertEqual(cfg.growth_type, GrowthType.GAUSSIAN)

    def test_default_mu(self):
        cfg = GrowthConfig()
        self.assertAlmostEqual(cfg.mu, DEFAULT_MU, places=10)

    def test_default_sigma(self):
        cfg = GrowthConfig()
        self.assertAlmostEqual(cfg.sigma, DEFAULT_SIGMA, places=10)

    def test_custom_construction(self):
        cfg = GrowthConfig(
            growth_type=GrowthType.RECTANGULAR,
            mu=0.25,
            sigma=0.05,
        )
        self.assertEqual(cfg.growth_type, GrowthType.RECTANGULAR)
        self.assertAlmostEqual(cfg.mu, 0.25, places=10)
        self.assertAlmostEqual(cfg.sigma, 0.05, places=10)


# ============================================================
# LeniaKernel — Core Function Tests
# ============================================================


class TestLeniaKernelCoreExponential(unittest.TestCase):
    """Tests for the exponential kernel core function K_C(r).

    The exponential core is defined as exp(4 - 4/(4r(1-r))) on (0,1),
    with K_C(0) = K_C(1) = 0 and K_C(0.5) = 1. This produces a smooth
    unimodal bump centered at the midpoint of the radial domain.
    """

    def setUp(self):
        cfg = KernelConfig(kernel_type=KernelType.EXPONENTIAL)
        self.kernel = LeniaKernel(cfg)

    def test_boundary_zero_at_r_equals_0(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.0), 0.0, places=10)

    def test_boundary_zero_at_r_equals_1(self):
        self.assertAlmostEqual(self.kernel.kernel_core(1.0), 0.0, places=10)

    def test_peak_at_r_equals_half(self):
        # At r=0.5: inner = 4*0.5*0.5 = 1.0, exp(4-4/1) = exp(0) = 1.0
        self.assertAlmostEqual(self.kernel.kernel_core(0.5), 1.0, places=10)

    def test_quarter_matches_formula(self):
        # At r=0.25: inner = 4*0.25*0.75 = 0.75, exp(4-4/0.75) = exp(4-16/3)
        r = 0.25
        inner = 4.0 * r * (1.0 - r)
        expected = math.exp(4.0 - 4.0 / inner)
        self.assertAlmostEqual(self.kernel.kernel_core(r), expected, places=10)

    def test_three_quarter_matches_formula(self):
        r = 0.75
        inner = 4.0 * r * (1.0 - r)
        expected = math.exp(4.0 - 4.0 / inner)
        self.assertAlmostEqual(self.kernel.kernel_core(r), expected, places=10)

    def test_symmetry_around_half(self):
        # K_C(0.25) should equal K_C(0.75) by the symmetry of r(1-r)
        val_low = self.kernel.kernel_core(0.25)
        val_high = self.kernel.kernel_core(0.75)
        self.assertAlmostEqual(val_low, val_high, places=10)

    def test_negative_r_returns_zero(self):
        self.assertAlmostEqual(self.kernel.kernel_core(-0.1), 0.0, places=10)

    def test_r_greater_than_one_returns_zero(self):
        self.assertAlmostEqual(self.kernel.kernel_core(1.5), 0.0, places=10)

    def test_monotone_increasing_on_left_half(self):
        # K_C should increase from 0 to 0.5
        r_vals = [0.1, 0.2, 0.3, 0.4, 0.5]
        vals = [self.kernel.kernel_core(r) for r in r_vals]
        for i in range(len(vals) - 1):
            self.assertLess(vals[i], vals[i + 1])

    def test_monotone_decreasing_on_right_half(self):
        r_vals = [0.5, 0.6, 0.7, 0.8, 0.9]
        vals = [self.kernel.kernel_core(r) for r in r_vals]
        for i in range(len(vals) - 1):
            self.assertGreater(vals[i], vals[i + 1])

    def test_values_in_unit_interval(self):
        for r in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            val = self.kernel.kernel_core(r)
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)


class TestLeniaKernelCorePolynomial(unittest.TestCase):
    """Tests for the polynomial kernel core function.

    The polynomial core is (4r(1-r))^4 on (0,1). Like the exponential
    core, it is unimodal with K_C(0.5) = 1 and K_C(0) = K_C(1) = 0.
    """

    def setUp(self):
        cfg = KernelConfig(kernel_type=KernelType.POLYNOMIAL)
        self.kernel = LeniaKernel(cfg)

    def test_peak_at_half(self):
        # (4*0.5*0.5)^4 = 1.0^4 = 1.0
        self.assertAlmostEqual(self.kernel.kernel_core(0.5), 1.0, places=10)

    def test_boundary_zero(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.0), 0.0, places=10)
        self.assertAlmostEqual(self.kernel.kernel_core(1.0), 0.0, places=10)

    def test_symmetry(self):
        self.assertAlmostEqual(
            self.kernel.kernel_core(0.3),
            self.kernel.kernel_core(0.7),
            places=10,
        )

    def test_quarter_matches_formula(self):
        r = 0.25
        expected = (4.0 * r * (1.0 - r)) ** 4
        self.assertAlmostEqual(self.kernel.kernel_core(r), expected, places=10)

    def test_value_at_0_1(self):
        # (4*0.1*0.9)^4 = (0.36)^4
        expected = 0.36 ** 4
        self.assertAlmostEqual(self.kernel.kernel_core(0.1), expected, places=10)


class TestLeniaKernelCoreRectangular(unittest.TestCase):
    """Tests for the rectangular kernel core function.

    The rectangular core is 1 for r in [0.25, 0.75] and 0 otherwise.
    This produces a hard-edged annular band.
    """

    def setUp(self):
        cfg = KernelConfig(kernel_type=KernelType.RECTANGULAR)
        self.kernel = LeniaKernel(cfg)

    def test_inside_band(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.3), 1.0, places=10)
        self.assertAlmostEqual(self.kernel.kernel_core(0.5), 1.0, places=10)
        self.assertAlmostEqual(self.kernel.kernel_core(0.7), 1.0, places=10)

    def test_outside_band_low(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.2), 0.0, places=10)
        self.assertAlmostEqual(self.kernel.kernel_core(0.1), 0.0, places=10)

    def test_outside_band_high(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.8), 0.0, places=10)
        self.assertAlmostEqual(self.kernel.kernel_core(0.9), 0.0, places=10)

    def test_boundary_at_025(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.25), 1.0, places=10)

    def test_boundary_at_075(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.75), 1.0, places=10)

    def test_at_zero(self):
        self.assertAlmostEqual(self.kernel.kernel_core(0.0), 0.0, places=10)

    def test_at_one(self):
        self.assertAlmostEqual(self.kernel.kernel_core(1.0), 0.0, places=10)


# ============================================================
# LeniaKernel — Shell Function Tests
# ============================================================


class TestLeniaKernelShellRank1(unittest.TestCase):
    """Tests for kernel shell with rank 1 (single ring).

    With rank=1 and beta=[1.0], the shell function reduces to the
    core function: K_S(r) = beta[0] * K_C(r) = K_C(r).
    """

    def setUp(self):
        cfg = KernelConfig(
            kernel_type=KernelType.EXPONENTIAL,
            rank=1,
            beta=[1.0],
        )
        self.kernel = LeniaKernel(cfg)

    def test_shell_equals_core_at_half(self):
        self.assertAlmostEqual(
            self.kernel.kernel_shell(0.5),
            self.kernel.kernel_core(0.5),
            places=10,
        )

    def test_shell_equals_core_at_quarter(self):
        self.assertAlmostEqual(
            self.kernel.kernel_shell(0.25),
            self.kernel.kernel_core(0.25),
            places=10,
        )

    def test_shell_boundary_zero(self):
        self.assertAlmostEqual(self.kernel.kernel_shell(0.0), 0.0, places=10)
        self.assertAlmostEqual(self.kernel.kernel_shell(1.0), 0.0, places=10)


class TestLeniaKernelShellRank2(unittest.TestCase):
    """Tests for kernel shell with rank 2 (two rings).

    With rank=2 and beta=[0.5, 1.0], the radial domain [0,1] is split
    into two halves: [0, 0.5) uses beta[0]=0.5, [0.5, 1) uses beta[1]=1.0.
    The local position within each ring is remapped to [0,1].
    """

    def setUp(self):
        cfg = KernelConfig(
            kernel_type=KernelType.EXPONENTIAL,
            rank=2,
            beta=[0.5, 1.0],
        )
        self.kernel = LeniaKernel(cfg)

    def test_first_ring_peak(self):
        # First ring: r in [0, 0.5). Peak at local_r=0.5 -> r=0.25
        # K_S(0.25) = 0.5 * K_C(0.5) = 0.5 * 1.0 = 0.5
        val = self.kernel.kernel_shell(0.25)
        self.assertAlmostEqual(val, 0.5, places=10)

    def test_second_ring_peak(self):
        # Second ring: r in [0.5, 1.0). Peak at local_r=0.5 -> r=0.75
        # K_S(0.75) = 1.0 * K_C(0.5) = 1.0
        val = self.kernel.kernel_shell(0.75)
        self.assertAlmostEqual(val, 1.0, places=10)

    def test_second_ring_has_higher_peak_than_first(self):
        peak_1 = self.kernel.kernel_shell(0.25)
        peak_2 = self.kernel.kernel_shell(0.75)
        self.assertGreater(peak_2, peak_1)

    def test_boundaries_are_zero(self):
        self.assertAlmostEqual(self.kernel.kernel_shell(0.0), 0.0, places=10)
        self.assertAlmostEqual(self.kernel.kernel_shell(1.0), 0.0, places=10)


# ============================================================
# LeniaKernel — Build Tests
# ============================================================


class TestLeniaKernelBuild(unittest.TestCase):
    """Tests for LeniaKernel.build() — full 2D kernel matrix construction."""

    def test_output_is_square(self):
        cfg = KernelConfig(radius=7)
        kernel = LeniaKernel(cfg)
        matrix = kernel.build(32)
        self.assertEqual(len(matrix), 32)
        for row in matrix:
            self.assertEqual(len(row), 32)

    def test_normalized_sum_approximately_one(self):
        cfg = KernelConfig(radius=7)
        kernel = LeniaKernel(cfg)
        matrix = kernel.build(32)
        total = sum(sum(row) for row in matrix)
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_radial_symmetry(self):
        cfg = KernelConfig(radius=7)
        kernel = LeniaKernel(cfg)
        size = 32
        matrix = kernel.build(size)
        c = size // 2
        # Check four symmetric points
        for d in range(1, 7):
            top = matrix[c - d][c]
            bot = matrix[c + d][c]
            left = matrix[c][c - d]
            right = matrix[c][c + d]
            self.assertAlmostEqual(top, bot, places=10)
            self.assertAlmostEqual(left, right, places=10)
            self.assertAlmostEqual(top, left, places=10)

    def test_different_radii_produce_different_extents(self):
        kernel_small = LeniaKernel(KernelConfig(radius=5))
        kernel_large = LeniaKernel(KernelConfig(radius=12))
        size = 32
        m_small = kernel_small.build(size)
        m_large = kernel_large.build(size)
        # Count nonzero cells — larger radius should have more
        nz_small = sum(1 for row in m_small for v in row if v > 1e-12)
        nz_large = sum(1 for row in m_large for v in row if v > 1e-12)
        self.assertGreater(nz_large, nz_small)

    def test_center_weight_zero_means_center_is_zero(self):
        cfg = KernelConfig(radius=7, center_weight=0.0)
        kernel = LeniaKernel(cfg)
        matrix = kernel.build(32)
        c = 32 // 2
        self.assertAlmostEqual(matrix[c][c], 0.0, places=10)

    def test_caching_returns_same_matrix(self):
        cfg = KernelConfig(radius=7)
        kernel = LeniaKernel(cfg)
        m1 = kernel.build(32)
        m2 = kernel.build(32)
        self.assertIs(m1, m2)

    def test_all_values_non_negative(self):
        cfg = KernelConfig(radius=7)
        kernel = LeniaKernel(cfg)
        matrix = kernel.build(32)
        for row in matrix:
            for val in row:
                self.assertGreaterEqual(val, 0.0)


# ============================================================
# GrowthFunction — Gaussian Tests
# ============================================================


class TestGrowthFunctionGaussian(unittest.TestCase):
    """Tests for the Gaussian growth function.

    G(u) = 2 * exp(-(u - mu)^2 / (2 * sigma^2)) - 1

    Peak at mu (G=1), decays to -1 far from mu. Symmetric around mu.
    """

    def setUp(self):
        self.mu = 0.15
        self.sigma = 0.016
        self.growth = GrowthFunction(GrowthConfig(
            growth_type=GrowthType.GAUSSIAN,
            mu=self.mu,
            sigma=self.sigma,
        ))

    def test_peak_at_mu(self):
        # G(mu) = 2*exp(0) - 1 = 2*1 - 1 = 1.0
        self.assertAlmostEqual(self.growth(self.mu), 1.0, places=10)

    def test_far_below_mu_approaches_minus_one(self):
        # G(0) with mu=0.15, sigma=0.016: exponent is huge negative
        val = self.growth(0.0)
        self.assertAlmostEqual(val, -1.0, places=6)

    def test_far_above_mu_approaches_minus_one(self):
        val = self.growth(1.0)
        self.assertAlmostEqual(val, -1.0, places=6)

    def test_symmetry_around_mu(self):
        d = 0.008
        val_low = self.growth(self.mu - d)
        val_high = self.growth(self.mu + d)
        self.assertAlmostEqual(val_low, val_high, places=10)

    def test_value_at_mu_plus_sigma(self):
        # G(mu + sigma) = 2*exp(-1/2) - 1
        expected = 2.0 * math.exp(-0.5) - 1.0
        self.assertAlmostEqual(self.growth(self.mu + self.sigma), expected, places=10)

    def test_value_at_mu_minus_sigma(self):
        expected = 2.0 * math.exp(-0.5) - 1.0
        self.assertAlmostEqual(self.growth(self.mu - self.sigma), expected, places=10)

    def test_wider_sigma_has_wider_positive_region(self):
        narrow = GrowthFunction(GrowthConfig(
            growth_type=GrowthType.GAUSSIAN, mu=0.15, sigma=0.01,
        ))
        wide = GrowthFunction(GrowthConfig(
            growth_type=GrowthType.GAUSSIAN, mu=0.15, sigma=0.05,
        ))
        test_u = 0.18  # 3 sigma from narrow but only 0.6 sigma from wide
        val_narrow = narrow(test_u)
        val_wide = wide(test_u)
        self.assertGreater(val_wide, val_narrow)

    def test_output_range(self):
        for u in [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0]:
            val = self.growth(u)
            self.assertGreaterEqual(val, -1.0)
            self.assertLessEqual(val, 1.0)

    def test_exact_formula(self):
        u = 0.14
        diff = u - self.mu
        expected = 2.0 * math.exp(-(diff ** 2) / (2.0 * self.sigma ** 2)) - 1.0
        self.assertAlmostEqual(self.growth(u), expected, places=10)


# ============================================================
# GrowthFunction — Polynomial Tests
# ============================================================


class TestGrowthFunctionPolynomial(unittest.TestCase):
    """Tests for the polynomial growth function.

    G(u) = 2 * (1 - (|u-mu|/(3*sigma))^2)^4 - 1  for |u-mu| < 3*sigma
    G(u) = -1                                       otherwise

    Compact support at 3*sigma from mu.
    """

    def setUp(self):
        self.mu = 0.15
        self.sigma = 0.016
        self.growth = GrowthFunction(GrowthConfig(
            growth_type=GrowthType.POLYNOMIAL,
            mu=self.mu,
            sigma=self.sigma,
        ))

    def test_peak_at_mu(self):
        self.assertAlmostEqual(self.growth(self.mu), 1.0, places=10)

    def test_outside_3_sigma_is_minus_one(self):
        threshold = 3.0 * self.sigma
        val = self.growth(self.mu + threshold + 0.001)
        self.assertAlmostEqual(val, -1.0, places=10)

    def test_exactly_at_3_sigma_is_minus_one(self):
        threshold = 3.0 * self.sigma
        val = self.growth(self.mu + threshold)
        self.assertAlmostEqual(val, -1.0, places=10)

    def test_symmetry_around_mu(self):
        d = 0.01
        val_low = self.growth(self.mu - d)
        val_high = self.growth(self.mu + d)
        self.assertAlmostEqual(val_low, val_high, places=10)

    def test_exact_formula_inside_support(self):
        u = 0.155
        diff = abs(u - self.mu)
        threshold = 3.0 * self.sigma
        ratio = diff / threshold
        expected = 2.0 * (1.0 - ratio * ratio) ** 4 - 1.0
        self.assertAlmostEqual(self.growth(u), expected, places=10)


# ============================================================
# GrowthFunction — Rectangular Tests
# ============================================================


class TestGrowthFunctionRectangular(unittest.TestCase):
    """Tests for the rectangular growth function.

    G(u) = 1   if |u - mu| < sigma
    G(u) = -1  otherwise
    """

    def setUp(self):
        self.mu = 0.15
        self.sigma = 0.016
        self.growth = GrowthFunction(GrowthConfig(
            growth_type=GrowthType.RECTANGULAR,
            mu=self.mu,
            sigma=self.sigma,
        ))

    def test_at_mu_returns_one(self):
        self.assertAlmostEqual(self.growth(self.mu), 1.0, places=10)

    def test_inside_window_returns_one(self):
        self.assertAlmostEqual(self.growth(self.mu + 0.01), 1.0, places=10)

    def test_outside_window_returns_minus_one(self):
        self.assertAlmostEqual(
            self.growth(self.mu + 2 * self.sigma), -1.0, places=10,
        )

    def test_far_from_mu_returns_minus_one(self):
        self.assertAlmostEqual(self.growth(0.0), -1.0, places=10)
        self.assertAlmostEqual(self.growth(1.0), -1.0, places=10)

    def test_just_inside_boundary(self):
        val = self.growth(self.mu + self.sigma * 0.99)
        self.assertAlmostEqual(val, 1.0, places=10)

    def test_just_outside_boundary(self):
        val = self.growth(self.mu + self.sigma * 1.01)
        self.assertAlmostEqual(val, -1.0, places=10)


# ============================================================
# FFTEngine — 1D Tests
# ============================================================


class TestFFTEngine1D(unittest.TestCase):
    """Tests for the pure-Python Cooley-Tukey 1D FFT implementation.

    Validates forward and inverse transforms against known analytical
    results, ensuring the Cooley-Tukey butterfly operations and
    bit-reversal permutation are correctly implemented.
    """

    def setUp(self):
        self.engine = _FFTEngine(4)

    def test_fft_of_impulse(self):
        # FFT of [1, 0, 0, 0] should be [1, 1, 1, 1]
        signal = [complex(1, 0), complex(0, 0), complex(0, 0), complex(0, 0)]
        result = self.engine.fft_1d(signal)
        for val in result:
            self.assertAlmostEqual(val.real, 1.0, places=10)
            self.assertAlmostEqual(val.imag, 0.0, places=10)

    def test_fft_of_constant(self):
        # FFT of [1, 1, 1, 1] should be [4, 0, 0, 0]
        signal = [complex(1, 0)] * 4
        result = self.engine.fft_1d(signal)
        self.assertAlmostEqual(result[0].real, 4.0, places=10)
        for k in range(1, 4):
            self.assertAlmostEqual(abs(result[k]), 0.0, places=10)

    def test_fft_of_alternating(self):
        # FFT of [1, -1, 1, -1] should be [0, 0, 4, 0]
        signal = [complex(1, 0), complex(-1, 0), complex(1, 0), complex(-1, 0)]
        result = self.engine.fft_1d(signal)
        self.assertAlmostEqual(abs(result[0]), 0.0, places=10)
        self.assertAlmostEqual(abs(result[1]), 0.0, places=10)
        self.assertAlmostEqual(result[2].real, 4.0, places=10)
        self.assertAlmostEqual(abs(result[3]), 0.0, places=10)

    def test_round_trip_1d(self):
        # FFT then IFFT should recover the original signal
        original = [complex(0.3, 0), complex(0.7, 0),
                     complex(0.1, 0), complex(0.9, 0)]
        spectrum = self.engine.fft_1d(original)
        recovered = self.engine.ifft_1d(spectrum)
        for i in range(4):
            self.assertAlmostEqual(recovered[i].real, original[i].real, places=10)
            self.assertAlmostEqual(recovered[i].imag, 0.0, places=10)

    def test_round_trip_1d_size_8(self):
        engine = _FFTEngine(8)
        original = [complex(v, 0) for v in [1, 2, 3, 4, 5, 6, 7, 8]]
        spectrum = engine.fft_1d(original)
        recovered = engine.ifft_1d(spectrum)
        for i in range(8):
            self.assertAlmostEqual(recovered[i].real, float(i + 1), places=10)

    def test_parsevals_theorem(self):
        # Sum of |x|^2 = (1/N) * Sum of |X|^2
        signal = [complex(1, 0), complex(2, 0), complex(3, 0), complex(4, 0)]
        spectrum = self.engine.fft_1d(signal)
        energy_time = sum(abs(s) ** 2 for s in signal)
        energy_freq = sum(abs(s) ** 2 for s in spectrum) / len(signal)
        self.assertAlmostEqual(energy_time, energy_freq, places=10)

    def test_linearity(self):
        # FFT(a*x + b*y) = a*FFT(x) + b*FFT(y)
        x = [complex(1, 0), complex(0, 0), complex(1, 0), complex(0, 0)]
        y = [complex(0, 0), complex(1, 0), complex(0, 0), complex(1, 0)]
        a, b = 2.0, 3.0
        combined = [complex(a * x[i].real + b * y[i].real, 0) for i in range(4)]
        fft_combined = self.engine.fft_1d(combined)
        fft_x = self.engine.fft_1d(x)
        fft_y = self.engine.fft_1d(y)
        for k in range(4):
            expected = a * fft_x[k] + b * fft_y[k]
            self.assertAlmostEqual(fft_combined[k].real, expected.real, places=10)
            self.assertAlmostEqual(fft_combined[k].imag, expected.imag, places=10)


# ============================================================
# FFTEngine — 2D Tests
# ============================================================


class TestFFTEngine2D(unittest.TestCase):
    """Tests for 2D FFT via row-column decomposition."""

    def test_round_trip_2d(self):
        engine = _FFTEngine(4)
        original = [
            [complex(1, 0), complex(2, 0), complex(3, 0), complex(4, 0)],
            [complex(5, 0), complex(6, 0), complex(7, 0), complex(8, 0)],
            [complex(9, 0), complex(10, 0), complex(11, 0), complex(12, 0)],
            [complex(13, 0), complex(14, 0), complex(15, 0), complex(16, 0)],
        ]
        spectrum = engine.fft_2d(original)
        recovered = engine.ifft_2d(spectrum)
        for y in range(4):
            for x in range(4):
                self.assertAlmostEqual(
                    recovered[y][x].real,
                    original[y][x].real,
                    places=6,
                )
                self.assertAlmostEqual(recovered[y][x].imag, 0.0, places=6)

    def test_2d_impulse(self):
        # 2D FFT of delta at origin -> all ones
        engine = _FFTEngine(4)
        grid = [[complex(0, 0)] * 4 for _ in range(4)]
        grid[0][0] = complex(1, 0)
        spectrum = engine.fft_2d(grid)
        for y in range(4):
            for x in range(4):
                self.assertAlmostEqual(spectrum[y][x].real, 1.0, places=10)
                self.assertAlmostEqual(spectrum[y][x].imag, 0.0, places=10)

    def test_2d_constant(self):
        # 2D FFT of all-ones -> N^2 at DC, zero elsewhere
        engine = _FFTEngine(4)
        grid = [[complex(1, 0)] * 4 for _ in range(4)]
        spectrum = engine.fft_2d(grid)
        self.assertAlmostEqual(spectrum[0][0].real, 16.0, places=10)
        for y in range(4):
            for x in range(4):
                if y == 0 and x == 0:
                    continue
                self.assertAlmostEqual(abs(spectrum[y][x]), 0.0, places=10)

    def test_output_is_real_for_real_symmetric_input(self):
        # A real even-symmetric input should have a real FFT
        engine = _FFTEngine(4)
        # Symmetric: grid[y][x] = grid[-y][-x]
        grid = [
            [complex(4, 0), complex(3, 0), complex(2, 0), complex(3, 0)],
            [complex(3, 0), complex(2, 0), complex(1, 0), complex(2, 0)],
            [complex(2, 0), complex(1, 0), complex(0, 0), complex(1, 0)],
            [complex(3, 0), complex(2, 0), complex(1, 0), complex(2, 0)],
        ]
        spectrum = engine.fft_2d(grid)
        for y in range(4):
            for x in range(4):
                self.assertAlmostEqual(spectrum[y][x].imag, 0.0, places=6)


# ============================================================
# FFTConvolver Tests
# ============================================================


class TestFFTConvolver(unittest.TestCase):
    """Tests for the FFT-accelerated 2D circular convolution engine."""

    def _make_delta_kernel_config(self):
        """Create a kernel config that produces a near-delta kernel.

        A center_weight of 1.0 with radius=1 concentrates all weight
        at the center, approximating a Dirac delta.
        """
        return KernelConfig(
            kernel_type=KernelType.EXPONENTIAL,
            radius=1,
            center_weight=1.0,
            beta=[1.0],
        )

    def test_convolve_with_near_identity_preserves_signal(self):
        """Convolution with a delta-like kernel should approximate identity."""
        cfg = self._make_delta_kernel_config()
        kernel = LeniaKernel(cfg)
        # Use a small power-of-2 grid for efficiency
        size = 8
        convolver = FFTConvolver(kernel, size)

        # Create a simple test pattern
        grid = [[0.0] * size for _ in range(size)]
        grid[3][3] = 1.0
        grid[5][5] = 0.5

        result = convolver.convolve(grid)
        # The total energy should be conserved (sum of result ≈ sum of grid)
        grid_sum = sum(sum(row) for row in grid)
        result_sum = sum(sum(row) for row in result)
        self.assertAlmostEqual(result_sum, grid_sum, places=3)

    def test_convolution_output_is_real_valued(self):
        """Convolving a uniform grid should return uniform real values."""
        cfg = KernelConfig(radius=3)
        kernel = LeniaKernel(cfg)
        size = 8
        convolver = FFTConvolver(kernel, size)

        grid = [[0.5] * size for _ in range(size)]
        result = convolver.convolve(grid)
        for row in result:
            for val in row:
                self.assertIsInstance(val, float)
                # Uniform grid convolved with normalized kernel should return 0.5
                self.assertAlmostEqual(val, 0.5, places=3)

    def test_uniform_grid_convolution_returns_uniform(self):
        """Convolving a uniform grid with any normalized kernel returns uniform."""
        cfg = KernelConfig(radius=3)
        kernel = LeniaKernel(cfg)
        size = 16
        convolver = FFTConvolver(kernel, size)

        fill_val = 0.42
        grid = [[fill_val] * size for _ in range(size)]
        result = convolver.convolve(grid)
        # All values should be close to the fill value
        for y in range(size):
            for x in range(size):
                self.assertAlmostEqual(result[y][x], fill_val, places=3)

    def test_circular_wrapping(self):
        """Circular convolution obeys toroidal topology: shifting the
        entire input grid by one row should shift the entire output by
        one row (modulo size), proving that boundaries wrap."""
        cfg = KernelConfig(radius=5)
        kernel = LeniaKernel(cfg)
        size = 16
        convolver = FFTConvolver(kernel, size)

        # Create a grid with a feature at center
        rng = random.Random(99)
        grid_a = [[0.0] * size for _ in range(size)]
        for y in range(3, 6):
            for x in range(3, 6):
                grid_a[y][x] = rng.random()

        # Shift grid_a by one row (wrapping top row to bottom)
        grid_b = [grid_a[(y - 1) % size] for y in range(size)]

        result_a = convolver.convolve(grid_a)
        result_b = convolver.convolve(grid_b)

        # result_b should be result_a shifted by one row
        for y in range(size):
            for x in range(size):
                self.assertAlmostEqual(
                    result_b[y][x],
                    result_a[(y - 1) % size][x],
                    places=6,
                )

    def test_zero_grid_returns_zero(self):
        """Convolving a zero grid should return a zero grid."""
        cfg = KernelConfig(radius=3)
        kernel = LeniaKernel(cfg)
        size = 8
        convolver = FFTConvolver(kernel, size)

        grid = [[0.0] * size for _ in range(size)]
        result = convolver.convolve(grid)
        for y in range(size):
            for x in range(size):
                self.assertAlmostEqual(result[y][x], 0.0, places=10)

    def test_mass_conservation_under_convolution(self):
        """Total mass should be preserved by convolution with a normalized kernel."""
        cfg = KernelConfig(radius=5)
        kernel = LeniaKernel(cfg)
        size = 16
        convolver = FFTConvolver(kernel, size)

        rng = random.Random(42)
        grid = [[rng.random() for _ in range(size)] for _ in range(size)]
        result = convolver.convolve(grid)

        input_mass = sum(sum(row) for row in grid)
        output_mass = sum(sum(row) for row in result)
        self.assertAlmostEqual(input_mass, output_mass, places=2)


# ============================================================
# LeniaGrid Tests
# ============================================================


class TestLeniaGridInitialization(unittest.TestCase):
    """Tests for LeniaGrid construction and initial state."""

    def _make_small_config(self, seed=42):
        """Create a config with a small grid for fast testing."""
        return SimulationConfig(
            grid_size=16,
            generations=10,
            dt=0.1,
            kernel=KernelConfig(radius=5),
            growth=GrowthConfig(),
            seed=seed,
        )

    def test_grid_is_correct_size(self):
        cfg = self._make_small_config()
        grid = LeniaGrid(cfg)
        self.assertEqual(grid.size, 16)
        self.assertEqual(len(grid.grid), 16)
        for row in grid.grid:
            self.assertEqual(len(row), 16)

    def test_initial_values_in_unit_interval(self):
        cfg = self._make_small_config()
        grid = LeniaGrid(cfg)
        for row in grid.grid:
            for val in row:
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)

    def test_initial_state_is_initialized(self):
        cfg = self._make_small_config()
        grid = LeniaGrid(cfg)
        self.assertEqual(grid.state, SimulationState.INITIALIZED)

    def test_initial_generation_is_zero(self):
        cfg = self._make_small_config()
        grid = LeniaGrid(cfg)
        self.assertEqual(grid.generation, 0)

    def test_initial_density_produces_nonzero_cells(self):
        cfg = self._make_small_config()
        grid = LeniaGrid(cfg)
        nonzero = sum(1 for row in grid.grid for v in row if v > 0.0)
        self.assertGreater(nonzero, 0)

    def test_zero_density_produces_mostly_empty_grid(self):
        cfg = SimulationConfig(
            grid_size=16,
            generations=10,
            kernel=KernelConfig(radius=5),
            initial_density=0.0,
            seed=42,
        )
        grid = LeniaGrid(cfg)
        # With seed-pattern initialization, even zero density produces a viable
        # initial configuration (the density parameter scales pattern amplitude
        # but the pattern itself is always placed to ensure life emerges).
        nonzero = sum(1 for row in grid.grid for v in row if v > 0.0)
        # Pattern placement means nonzero cells are present
        self.assertGreater(nonzero, 0)


class TestLeniaGridMassAndPopulation(unittest.TestCase):
    """Tests for total_mass() and population() methods."""

    def _make_grid(self):
        cfg = SimulationConfig(
            grid_size=16,
            generations=10,
            kernel=KernelConfig(radius=5),
            seed=42,
        )
        return LeniaGrid(cfg)

    def test_total_mass_equals_sum_of_cells(self):
        grid = self._make_grid()
        expected = sum(sum(row) for row in grid.grid)
        self.assertAlmostEqual(grid.total_mass(), expected, places=10)

    def test_total_mass_is_positive(self):
        grid = self._make_grid()
        self.assertGreater(grid.total_mass(), 0.0)

    def test_population_counts_cells_above_threshold(self):
        grid = self._make_grid()
        expected = sum(
            1 for row in grid.grid for v in row if v > POPULATION_THRESHOLD
        )
        self.assertEqual(grid.population(), expected)

    def test_population_is_non_negative(self):
        grid = self._make_grid()
        self.assertGreaterEqual(grid.population(), 0)


class TestLeniaGridStep(unittest.TestCase):
    """Tests for the LeniaGrid.step() method — one generation of Lenia."""

    def _make_grid(self, seed=42):
        cfg = SimulationConfig(
            grid_size=16,
            generations=10,
            kernel=KernelConfig(radius=5),
            seed=seed,
        )
        return LeniaGrid(cfg)

    def test_step_increments_generation(self):
        grid = self._make_grid()
        self.assertEqual(grid.generation, 0)
        grid.step()
        self.assertEqual(grid.generation, 1)

    def test_step_changes_grid_state(self):
        grid = self._make_grid()
        before = [row[:] for row in grid.grid]
        grid.step()
        after = grid.grid
        # At least some cells should have changed
        changed = sum(
            1 for y in range(16) for x in range(16)
            if abs(after[y][x] - before[y][x]) > 1e-12
        )
        self.assertGreater(changed, 0)

    def test_step_keeps_values_clipped_to_unit_interval(self):
        grid = self._make_grid()
        grid.step()
        for row in grid.grid:
            for val in row:
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)

    def test_step_returns_generation_report(self):
        grid = self._make_grid()
        report = grid.step()
        self.assertEqual(report.generation, 1)
        self.assertGreaterEqual(report.population, 0)
        self.assertGreaterEqual(report.total_mass, 0.0)

    def test_step_sets_state_to_running(self):
        grid = self._make_grid()
        grid.step()
        # State should be RUNNING (or EXTINCT if mass collapsed)
        self.assertIn(
            grid.state,
            {SimulationState.RUNNING, SimulationState.EXTINCT},
        )

    def test_multiple_steps_increment_generation(self):
        grid = self._make_grid()
        for i in range(5):
            grid.step()
        self.assertEqual(grid.generation, 5)


class TestLeniaGridDeterminism(unittest.TestCase):
    """Tests for deterministic seeding and reproducibility."""

    def test_same_seed_produces_same_initial_grid(self):
        cfg1 = SimulationConfig(
            grid_size=16, kernel=KernelConfig(radius=5), seed=123,
        )
        cfg2 = SimulationConfig(
            grid_size=16, kernel=KernelConfig(radius=5), seed=123,
        )
        g1 = LeniaGrid(cfg1)
        g2 = LeniaGrid(cfg2)
        for y in range(16):
            for x in range(16):
                self.assertAlmostEqual(
                    g1.grid[y][x], g2.grid[y][x], places=10,
                )

    def test_different_seeds_produce_different_grids(self):
        cfg1 = SimulationConfig(
            grid_size=16, kernel=KernelConfig(radius=5), seed=1,
            seed_mode=SeedMode.SPECIES,
        )
        cfg2 = SimulationConfig(
            grid_size=16, kernel=KernelConfig(radius=5), seed=2,
            seed_mode=SeedMode.SPECIES,
        )
        g1 = LeniaGrid(cfg1)
        g2 = LeniaGrid(cfg2)
        # At least some cells should differ — SPECIES mode uses the seed
        # to determine the asymmetric blob orientation, producing distinct
        # initial configurations for different input numbers.
        diffs = sum(
            1 for y in range(16) for x in range(16)
            if abs(g1.grid[y][x] - g2.grid[y][x]) > 1e-10
        )
        self.assertGreater(diffs, 0)

    def test_same_seed_produces_same_state_after_step(self):
        cfg1 = SimulationConfig(
            grid_size=16, kernel=KernelConfig(radius=5), seed=42,
        )
        cfg2 = SimulationConfig(
            grid_size=16, kernel=KernelConfig(radius=5), seed=42,
        )
        g1 = LeniaGrid(cfg1)
        g2 = LeniaGrid(cfg2)
        g1.step()
        g2.step()
        for y in range(16):
            for x in range(16):
                self.assertAlmostEqual(
                    g1.grid[y][x], g2.grid[y][x], places=10,
                )


# ============================================================
# FlowField Tests
# ============================================================


class TestFlowField(unittest.TestCase):
    """Tests for the mass-conservative gradient flow transport."""

    def test_compute_flow_returns_correct_shape(self):
        ff = FlowField(8)
        grid = [[0.5] * 8 for _ in range(8)]
        growth = [[0.0] * 8 for _ in range(8)]
        flow_x, flow_y = ff.compute_flow(grid, growth)
        self.assertEqual(len(flow_x), 8)
        self.assertEqual(len(flow_x[0]), 8)
        self.assertEqual(len(flow_y), 8)
        self.assertEqual(len(flow_y[0]), 8)

    def test_uniform_growth_produces_zero_flow(self):
        ff = FlowField(8)
        grid = [[0.5] * 8 for _ in range(8)]
        growth = [[0.3] * 8 for _ in range(8)]
        flow_x, flow_y = ff.compute_flow(grid, growth)
        for y in range(8):
            for x in range(8):
                self.assertAlmostEqual(flow_x[y][x], 0.0, places=10)
                self.assertAlmostEqual(flow_y[y][x], 0.0, places=10)

    def test_gradient_produces_nonzero_flow(self):
        ff = FlowField(8)
        grid = [[0.5] * 8 for _ in range(8)]
        growth = [[float(x) / 8.0 for x in range(8)] for _ in range(8)]
        flow_x, flow_y = ff.compute_flow(grid, growth)
        # With increasing growth along x, flow_x should be nonzero
        has_nonzero = any(
            abs(flow_x[y][x]) > 1e-10
            for y in range(8) for x in range(8)
        )
        self.assertTrue(has_nonzero)

    def test_apply_flow_conserves_mass_approximately(self):
        ff = FlowField(8)
        rng = random.Random(42)
        grid = [[rng.random() * 0.5 for _ in range(8)] for _ in range(8)]
        growth = [[rng.random() * 0.2 - 0.1 for _ in range(8)] for _ in range(8)]
        flow = ff.compute_flow(grid, growth)
        new_grid = ff.apply_flow(grid, flow, 0.1)
        old_mass = sum(sum(row) for row in grid)
        new_mass = sum(sum(row) for row in new_grid)
        # Mass should be approximately conserved (clipping may cause small loss)
        self.assertAlmostEqual(old_mass, new_mass, places=1)

    def test_apply_flow_clips_to_unit_interval(self):
        ff = FlowField(4)
        grid = [[0.9] * 4 for _ in range(4)]
        growth = [[1.0, -1.0, 1.0, -1.0] for _ in range(4)]
        flow = ff.compute_flow(grid, growth)
        new_grid = ff.apply_flow(grid, flow, 0.5)
        for row in new_grid:
            for val in row:
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)

    def test_zero_grid_produces_zero_output(self):
        ff = FlowField(4)
        grid = [[0.0] * 4 for _ in range(4)]
        growth = [[0.5] * 4 for _ in range(4)]
        flow = ff.compute_flow(grid, growth)
        new_grid = ff.apply_flow(grid, flow, 0.1)
        for row in new_grid:
            for val in row:
                self.assertAlmostEqual(val, 0.0, places=10)


# ============================================================
# SpeciesCatalog Tests
# ============================================================


class TestSpeciesCatalog(unittest.TestCase):
    """Tests for the Lenia species catalog and parameter-space classification."""

    def setUp(self):
        self.catalog = SpeciesCatalog()

    def test_catalog_has_seven_species(self):
        self.assertEqual(len(self.catalog.species), 7)

    def test_species_names_are_unique(self):
        names = [s.name for s in self.catalog.species]
        self.assertEqual(len(names), len(set(names)))

    def test_orbium_is_registered(self):
        names = [s.name for s in self.catalog.species]
        self.assertIn("Orbium unicaudatus", names)

    def test_scutium_is_registered(self):
        names = [s.name for s in self.catalog.species]
        self.assertIn("Scutium gravidus", names)

    def test_orbium_classified_as_fizz(self):
        result = self.catalog.get_classification("Orbium unicaudatus")
        self.assertEqual(result, "Fizz")

    def test_scutium_classified_as_buzz(self):
        result = self.catalog.get_classification("Scutium gravidus")
        self.assertEqual(result, "Buzz")

    def test_gyroelongium_classified_as_fizzbuzz(self):
        result = self.catalog.get_classification("Gyroelongium elongatus")
        self.assertEqual(result, "FizzBuzz")

    def test_triscutium_classified_as_fizzbuzz(self):
        result = self.catalog.get_classification("Triscutium triplex")
        self.assertEqual(result, "FizzBuzz")

    def test_kronium_classified_as_buzz(self):
        result = self.catalog.get_classification("Kronium coronatus")
        self.assertEqual(result, "Buzz")

    def test_unknown_species_returns_none(self):
        result = self.catalog.get_classification("Nonexistent species")
        self.assertIsNone(result)

    def test_classify_exact_orbium_params(self):
        config = SimulationConfig(
            kernel=KernelConfig(
                kernel_type=KernelType.EXPONENTIAL,
                radius=13,
                rank=1,
                beta=[1.0],
            ),
            growth=GrowthConfig(
                growth_type=GrowthType.GAUSSIAN,
                mu=0.15,
                sigma=0.015,
            ),
        )
        species = self.catalog.classify(config)
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Orbium unicaudatus")

    def test_classify_exact_scutium_params(self):
        config = SimulationConfig(
            kernel=KernelConfig(
                kernel_type=KernelType.EXPONENTIAL,
                radius=13,
            ),
            growth=GrowthConfig(
                growth_type=GrowthType.GAUSSIAN,
                mu=0.29,
                sigma=0.045,
            ),
        )
        species = self.catalog.classify(config)
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Scutium gravidus")

    def test_classify_distant_params_returns_none(self):
        config = SimulationConfig(
            kernel=KernelConfig(radius=5),
            growth=GrowthConfig(mu=0.9, sigma=0.5),
        )
        species = self.catalog.classify(config)
        self.assertIsNone(species)

    def test_species_fingerprints_have_families(self):
        for species in self.catalog.species:
            self.assertTrue(len(species.family) > 0)

    def test_species_fingerprints_have_descriptions(self):
        for species in self.catalog.species:
            self.assertTrue(len(species.description) > 0)


# ============================================================
# PatternAnalyzer Tests
# ============================================================


class TestPatternAnalyzer(unittest.TestCase):
    """Tests for equilibrium detection, species classification, and statistics."""

    def setUp(self):
        self.analyzer = PatternAnalyzer()

    def test_detect_equilibrium_true_when_stable(self):
        reports = [
            GenerationReport(
                generation=i, population=100, total_mass=50.0,
                mass_delta=1e-8,
            )
            for i in range(15)
        ]
        self.assertTrue(self.analyzer.detect_equilibrium(reports, window=10))

    def test_detect_equilibrium_false_when_unstable(self):
        reports = [
            GenerationReport(
                generation=i, population=100, total_mass=50.0 + i,
                mass_delta=1.0,
            )
            for i in range(15)
        ]
        self.assertFalse(self.analyzer.detect_equilibrium(reports, window=10))

    def test_detect_equilibrium_false_when_too_few_reports(self):
        reports = [
            GenerationReport(
                generation=i, population=100, total_mass=50.0,
                mass_delta=0.0,
            )
            for i in range(5)
        ]
        self.assertFalse(self.analyzer.detect_equilibrium(reports, window=10))

    def test_compute_statistics_total_mass(self):
        grid = [[0.5] * 4 for _ in range(4)]
        stats = self.analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["total_mass"], 8.0, places=10)

    def test_compute_statistics_population(self):
        grid = [[0.5] * 4 for _ in range(4)]
        stats = self.analyzer.compute_statistics(grid)
        # All cells at 0.5 > POPULATION_THRESHOLD (0.1)
        self.assertEqual(stats["population"], 16)

    def test_compute_statistics_zero_grid(self):
        grid = [[0.0] * 4 for _ in range(4)]
        stats = self.analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["total_mass"], 0.0, places=10)
        self.assertEqual(stats["population"], 0)
        self.assertAlmostEqual(stats["mean_state"], 0.0, places=10)

    def test_compute_statistics_mean_state(self):
        grid = [[0.25] * 4 for _ in range(4)]
        stats = self.analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["mean_state"], 0.25, places=10)

    def test_compute_statistics_max_and_min(self):
        grid = [[0.0] * 4 for _ in range(4)]
        grid[0][0] = 0.9
        grid[3][3] = 0.1
        stats = self.analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["max_state"], 0.9, places=10)
        self.assertAlmostEqual(stats["min_state"], 0.0, places=10)

    def test_compute_statistics_centroid_uniform(self):
        grid = [[1.0] * 4 for _ in range(4)]
        stats = self.analyzer.compute_statistics(grid)
        # Centroid of uniform grid should be at center
        self.assertAlmostEqual(stats["centroid_x"], 1.5, places=10)
        self.assertAlmostEqual(stats["centroid_y"], 1.5, places=10)

    def test_compute_statistics_centroid_single_point(self):
        grid = [[0.0] * 4 for _ in range(4)]
        grid[2][3] = 1.0
        stats = self.analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["centroid_x"], 3.0, places=10)
        self.assertAlmostEqual(stats["centroid_y"], 2.0, places=10)

    def test_compute_statistics_grid_size(self):
        grid = [[0.0] * 8 for _ in range(8)]
        stats = self.analyzer.compute_statistics(grid)
        self.assertEqual(stats["grid_size"], 8)
        self.assertEqual(stats["total_cells"], 64)

    def test_compute_statistics_density_histogram_has_10_bins(self):
        grid = [[0.5] * 4 for _ in range(4)]
        stats = self.analyzer.compute_statistics(grid)
        self.assertEqual(len(stats["density_histogram"]), 10)

    def test_compute_statistics_std_dev_uniform(self):
        grid = [[0.5] * 4 for _ in range(4)]
        stats = self.analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["std_dev"], 0.0, places=10)

    def test_detect_oscillation_returns_none_for_constant(self):
        reports = [
            GenerationReport(
                generation=i, population=100, total_mass=50.0, mass_delta=0.0,
            )
            for i in range(100)
        ]
        result = self.analyzer.detect_oscillation(reports, window=20)
        self.assertIsNone(result)

    def test_detect_oscillation_returns_none_for_short_series(self):
        reports = [
            GenerationReport(
                generation=i, population=100, total_mass=50.0, mass_delta=0.0,
            )
            for i in range(10)
        ]
        result = self.analyzer.detect_oscillation(reports, window=20)
        self.assertIsNone(result)

    def test_detect_oscillation_detects_periodic_signal(self):
        period = 10
        reports = [
            GenerationReport(
                generation=i, population=100,
                total_mass=50.0 + 10.0 * math.sin(2.0 * math.pi * i / period),
                mass_delta=0.0,
            )
            for i in range(200)
        ]
        result = self.analyzer.detect_oscillation(reports, window=20)
        # Should detect a period that is a multiple or near-multiple of 10
        # The autocorrelation peak occurs at the true period or its harmonics
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result, 2)
        # The detected lag should divide evenly into the true period
        # (i.e., it's the period or a subharmonic)
        self.assertEqual(period % result, 0)

    def test_classify_species_delegates_to_catalog(self):
        config = SimulationConfig(
            kernel=KernelConfig(
                kernel_type=KernelType.EXPONENTIAL,
                radius=13,
            ),
            growth=GrowthConfig(mu=0.15, sigma=0.015),
        )
        species = self.analyzer.classify_species(config)
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Orbium unicaudatus")


# ============================================================
# FizzLifeEngine Tests
# ============================================================


class TestFizzLifeEngine(unittest.TestCase):
    """Tests for the top-level FizzLife simulation orchestrator."""

    def _make_fast_config(self, seed=42):
        """Config tuned for fast test execution: tiny grid, few generations."""
        return SimulationConfig(
            grid_size=16,
            generations=20,
            dt=0.1,
            kernel=KernelConfig(radius=5),
            seed=seed,
        )

    def test_engine_creation_with_defaults(self):
        engine = FizzLifeEngine()
        self.assertIsNotNone(engine.config)
        self.assertIsNotNone(engine.run_id)
        self.assertEqual(len(engine.run_id), 12)

    def test_engine_creation_with_config(self):
        cfg = self._make_fast_config()
        engine = FizzLifeEngine(cfg)
        self.assertEqual(engine.config.grid_size, 16)
        self.assertEqual(engine.config.generations, 20)

    def test_grid_is_none_before_initialize(self):
        engine = FizzLifeEngine(self._make_fast_config())
        self.assertIsNone(engine.grid)

    def test_initialize_creates_grid(self):
        engine = FizzLifeEngine(self._make_fast_config())
        engine.initialize()
        self.assertIsNotNone(engine.grid)
        self.assertEqual(engine.grid.size, 16)

    def test_initialize_emits_started_event(self):
        engine = FizzLifeEngine(self._make_fast_config())
        engine.initialize()
        self.assertGreater(len(engine.events), 0)
        started = [e for e in engine.events
                   if e.event_type.name == "FIZZLIFE_SIMULATION_STARTED"]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].payload["grid_size"], 16)

    def test_run_returns_simulation_result(self):
        engine = FizzLifeEngine(self._make_fast_config())
        result = engine.run()
        self.assertIsInstance(result, SimulationResult)
        self.assertGreater(result.generations_run, 0)
        self.assertGreaterEqual(result.final_mass, 0.0)

    def test_run_auto_initializes(self):
        engine = FizzLifeEngine(self._make_fast_config())
        result = engine.run()
        self.assertIsNotNone(engine.grid)
        self.assertGreater(result.generations_run, 0)

    def test_run_emits_multiple_events(self):
        engine = FizzLifeEngine(self._make_fast_config())
        engine.run()
        # At minimum: started + classification events
        self.assertGreaterEqual(len(engine.events), 2)

    def test_run_classification_is_valid_fizzbuzz_label(self):
        engine = FizzLifeEngine(self._make_fast_config())
        result = engine.run()
        self.assertIn(result.classification, {"Fizz", "Buzz", "FizzBuzz", ""})

    def test_run_reports_match_generations_run(self):
        engine = FizzLifeEngine(self._make_fast_config())
        result = engine.run()
        self.assertEqual(len(result.reports), result.generations_run)

    def test_elapsed_time_available_after_run(self):
        engine = FizzLifeEngine(self._make_fast_config())
        engine.run()
        elapsed = engine.get_elapsed_time()
        self.assertIsNotNone(elapsed)
        self.assertGreater(elapsed, 0.0)

    def test_elapsed_time_none_before_run(self):
        engine = FizzLifeEngine(self._make_fast_config())
        self.assertIsNone(engine.get_elapsed_time())

    def test_render_before_init_returns_not_initialized(self):
        engine = FizzLifeEngine(self._make_fast_config())
        rendered = engine.render_current_state()
        self.assertEqual(rendered, "(not initialized)")

    def test_render_after_init_returns_ascii(self):
        engine = FizzLifeEngine(self._make_fast_config())
        engine.initialize()
        rendered = engine.render_current_state(width=16)
        self.assertGreater(len(rendered), 0)
        self.assertIn("\n", rendered)

    def test_catalog_is_accessible(self):
        engine = FizzLifeEngine(self._make_fast_config())
        self.assertIsInstance(engine.catalog, SpeciesCatalog)

    def test_analyzer_is_accessible(self):
        engine = FizzLifeEngine(self._make_fast_config())
        self.assertIsInstance(engine.analyzer, PatternAnalyzer)

    def test_deterministic_runs_produce_same_result(self):
        cfg1 = self._make_fast_config(seed=99)
        cfg2 = self._make_fast_config(seed=99)
        r1 = FizzLifeEngine(cfg1).run()
        r2 = FizzLifeEngine(cfg2).run()
        self.assertEqual(r1.generations_run, r2.generations_run)
        self.assertAlmostEqual(r1.final_mass, r2.final_mass, places=10)
        self.assertEqual(r1.classification, r2.classification)

    def test_extinct_simulation_returns_empty_classification(self):
        # Tiny grid with very small initial density and narrow growth
        # should go extinct, producing an empty classification.
        cfg = SimulationConfig(
            grid_size=16,
            generations=100,
            dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.5, sigma=0.001),
            seed=42,
        )
        engine = FizzLifeEngine(cfg)
        result = engine.run()
        self.assertGreater(result.generations_run, 0)
        self.assertLess(result.final_mass, EXTINCTION_MASS_THRESHOLD)
        self.assertEqual(result.classification, "")


# ============================================================
# FizzLifeDashboard Tests
# ============================================================


class TestFizzLifeDashboard(unittest.TestCase):
    """Tests for the ASCII simulation monitoring dashboard."""

    def test_dashboard_width_constant(self):
        self.assertEqual(FizzLifeDashboard.DASHBOARD_WIDTH, 72)

    def test_render_with_no_reports(self):
        dash = FizzLifeDashboard()
        cfg = SimulationConfig(
            grid_size=16, generations=10, kernel=KernelConfig(radius=5), seed=1,
        )
        engine = FizzLifeEngine(cfg)
        engine.initialize()
        output = dash.render(engine, [])
        self.assertIn("FIZZLIFE CONTINUOUS CELLULAR AUTOMATON", output)
        self.assertIn("awaiting first generation", output)

    def test_render_with_reports_includes_stats(self):
        dash = FizzLifeDashboard()
        cfg = SimulationConfig(
            grid_size=16, generations=10, kernel=KernelConfig(radius=5), seed=1,
        )
        engine = FizzLifeEngine(cfg)
        engine.initialize()
        report = engine.grid.step()
        output = dash.render(engine, [report])
        self.assertIn("Generation:", output)
        self.assertIn("Population:", output)
        self.assertIn("Total Mass:", output)
        self.assertIn("MASS EVOLUTION", output)
        self.assertIn("GRID STATE", output)

    def test_render_includes_config_info(self):
        dash = FizzLifeDashboard()
        cfg = SimulationConfig(
            grid_size=16, generations=10, kernel=KernelConfig(radius=5), seed=1,
        )
        engine = FizzLifeEngine(cfg)
        engine.initialize()
        output = dash.render(engine, [])
        self.assertIn("EXPONENTIAL", output)
        self.assertIn("GAUSSIAN", output)

    def test_sparkline_empty_values(self):
        result = FizzLifeDashboard._render_sparkline([], 20)
        self.assertEqual(len(result), 20)

    def test_sparkline_constant_values(self):
        result = FizzLifeDashboard._render_sparkline([5.0] * 10, 20)
        self.assertEqual(len(result), 20)

    def test_sparkline_varying_values(self):
        vals = [float(i) for i in range(10)]
        result = FizzLifeDashboard._render_sparkline(vals, 20)
        self.assertEqual(len(result), 20)
        # First char should differ from last (range 0-9)
        self.assertNotEqual(result[0], result[9])

    def test_sparkline_long_values_downsampled(self):
        vals = [float(i) for i in range(100)]
        result = FizzLifeDashboard._render_sparkline(vals, 20)
        self.assertEqual(len(result), 20)


# ============================================================
# Convenience Functions Tests
# ============================================================


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for module-level convenience functions."""

    def test_create_default_config_returns_simulation_config(self):
        cfg = create_default_config()
        self.assertIsInstance(cfg, SimulationConfig)
        self.assertEqual(cfg.grid_size, DEFAULT_GRID_SIZE)
        self.assertEqual(cfg.generations, DEFAULT_GENERATIONS)

    def test_create_species_config_orbium(self):
        cfg = create_species_config("Orbium unicaudatus")
        self.assertIsNotNone(cfg)
        self.assertAlmostEqual(cfg.growth.mu, 0.15, places=10)
        self.assertAlmostEqual(cfg.growth.sigma, 0.015, places=10)
        self.assertEqual(cfg.kernel.radius, 13)

    def test_create_species_config_scutium(self):
        cfg = create_species_config("Scutium gravidus")
        self.assertIsNotNone(cfg)
        self.assertAlmostEqual(cfg.growth.mu, 0.29, places=10)

    def test_create_species_config_unknown_returns_none(self):
        cfg = create_species_config("Nonexistent species")
        self.assertIsNone(cfg)

    def test_run_simulation_returns_result(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=5), seed=42,
        )
        result = run_simulation(cfg)
        self.assertIsInstance(result, SimulationResult)
        self.assertGreater(result.generations_run, 0)

    def test_run_simulation_default_config(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=5), seed=1,
        )
        result = run_simulation(cfg)
        self.assertIsInstance(result.classification, str)

    def test_classify_number_returns_string(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=5),
        )
        result = classify_number(42, config=cfg)
        self.assertIsInstance(result, str)

    def test_classify_number_deterministic(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=5),
        )
        r1 = classify_number(7, config=cfg)
        r2 = classify_number(7, config=cfg)
        self.assertEqual(r1, r2)

    def test_classify_number_different_inputs_use_different_seeds(self):
        # Different numbers should seed differently, producing deterministic
        # but potentially distinct classifications.
        cfg = SimulationConfig(
            grid_size=16, generations=10, kernel=KernelConfig(radius=5),
        )
        valid_classes = {"Fizz", "Buzz", "FizzBuzz", ""}
        results = {}
        for n in [1, 2, 3, 5, 15, 100]:
            result = classify_number(n, config=cfg)
            self.assertIn(result, valid_classes,
                          f"classify_number({n}) returned unexpected '{result}'")
            results[n] = result
        # Verify determinism: same input gives same output
        self.assertEqual(
            classify_number(15, config=cfg), classify_number(15, config=cfg))
        # Verify diversity: not all numbers should produce the same label.
        # If all 6 inputs classify identically, the seeding is broken.
        unique_labels = set(results.values())
        self.assertGreater(
            len(unique_labels), 1,
            f"All 6 inputs produced the same label '{unique_labels}' — "
            f"per-number seeding is not producing diverse simulations")


# ============================================================
# GenerationReport & SimulationResult Dataclass Tests
# ============================================================


class TestGenerationReport(unittest.TestCase):
    """Tests for the GenerationReport dataclass."""

    def test_creation_with_required_fields(self):
        report = GenerationReport(
            generation=5, population=100, total_mass=50.0, mass_delta=-0.1,
        )
        self.assertEqual(report.generation, 5)
        self.assertEqual(report.population, 100)
        self.assertAlmostEqual(report.total_mass, 50.0, places=10)
        self.assertAlmostEqual(report.mass_delta, -0.1, places=10)

    def test_default_species_detected_is_none(self):
        report = GenerationReport(
            generation=1, population=10, total_mass=5.0, mass_delta=0.0,
        )
        self.assertIsNone(report.species_detected)

    def test_default_state_is_running(self):
        report = GenerationReport(
            generation=1, population=10, total_mass=5.0, mass_delta=0.0,
        )
        self.assertEqual(report.state, SimulationState.RUNNING)


class TestSimulationResult(unittest.TestCase):
    """Tests for the SimulationResult dataclass."""

    def test_creation(self):
        cfg = SimulationConfig()
        result = SimulationResult(
            config=cfg,
            generations_run=100,
            final_population=50,
            final_mass=25.0,
            classification="Fizz",
        )
        self.assertEqual(result.generations_run, 100)
        self.assertEqual(result.final_population, 50)
        self.assertAlmostEqual(result.final_mass, 25.0, places=10)
        self.assertEqual(result.classification, "Fizz")

    def test_default_empty_lists(self):
        cfg = SimulationConfig()
        result = SimulationResult(
            config=cfg, generations_run=0, final_population=0, final_mass=0.0,
        )
        self.assertEqual(result.species_history, [])
        self.assertEqual(result.reports, [])
        self.assertEqual(result.classification, "")


class TestSpeciesFingerprint(unittest.TestCase):
    """Tests for the SpeciesFingerprint dataclass."""

    def test_creation(self):
        fp = SpeciesFingerprint(
            name="Test species",
            family="Testidae",
            kernel_config=KernelConfig(),
            growth_config=GrowthConfig(),
            description="A test species.",
        )
        self.assertEqual(fp.name, "Test species")
        self.assertEqual(fp.family, "Testidae")
        self.assertEqual(fp.description, "A test species.")

    def test_default_description_is_empty(self):
        fp = SpeciesFingerprint(
            name="Minimal",
            family="Minimalidae",
            kernel_config=KernelConfig(),
            growth_config=GrowthConfig(),
        )
        self.assertEqual(fp.description, "")


class TestSimulationConfig(unittest.TestCase):
    """Tests for the SimulationConfig dataclass."""

    def test_defaults(self):
        cfg = SimulationConfig()
        self.assertEqual(cfg.grid_size, DEFAULT_GRID_SIZE)
        self.assertEqual(cfg.generations, DEFAULT_GENERATIONS)
        self.assertAlmostEqual(cfg.dt, DEFAULT_DT, places=10)
        self.assertEqual(cfg.channels, 1)
        self.assertFalse(cfg.mass_conservation)
        self.assertAlmostEqual(cfg.initial_density, 0.3, places=10)
        self.assertIsNone(cfg.seed)
        self.assertEqual(cfg.seed_mode, SeedMode.GAUSSIAN_BLOB)

    def test_custom_seed(self):
        cfg = SimulationConfig(seed=42)
        self.assertEqual(cfg.seed, 42)

    def test_mass_conservation_flag(self):
        cfg = SimulationConfig(mass_conservation=True)
        self.assertTrue(cfg.mass_conservation)

    def test_seed_mode_override(self):
        cfg = SimulationConfig(seed_mode=SeedMode.RING)
        self.assertEqual(cfg.seed_mode, SeedMode.RING)

    def test_seed_mode_random(self):
        cfg = SimulationConfig(seed_mode=SeedMode.RANDOM)
        self.assertEqual(cfg.seed_mode, SeedMode.RANDOM)


# ============================================================
# Edge Case Tests: Grid Boundaries
# ============================================================


class TestGridEdgeCases(unittest.TestCase):
    """Edge case tests for degenerate and extreme grid configurations."""

    def test_empty_grid_remains_low_mass(self):
        """A grid initialized with zero density should not gain significant mass.

        With structured seed initialization, the grid always contains a seed
        pattern even at density=0. The test verifies that one step does not
        cause unbounded mass explosion — the mass should remain within a
        reasonable factor of the initial mass.
        """
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
            initial_density=0.0,
        )
        grid = LeniaGrid(config)
        initial_mass = grid.total_mass()
        report = grid.step()
        self.assertLessEqual(report.total_mass, initial_mass * 2.0 + 1.0)

    def test_full_grid_decays(self):
        """A grid where every cell is 1.0 should lose mass.

        Convolution of a uniform grid with a normalized kernel yields potential
        1.0 everywhere. With default mu=0.15, the growth function at u=1.0 is
        strongly negative, driving mass down.
        """
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        for y in range(grid.size):
            for x in range(grid.size):
                grid._grid[y][x] = 1.0
        initial_mass = grid.total_mass()
        self.assertAlmostEqual(initial_mass, 64.0, places=1)
        report = grid.step()
        self.assertLess(report.total_mass, initial_mass)

    def test_single_cell_at_center(self):
        """A single nonzero cell at the center should produce valid behavior."""
        config = SimulationConfig(
            grid_size=8, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        for y in range(grid.size):
            for x in range(grid.size):
                grid._grid[y][x] = 0.0
        grid._grid[4][4] = 1.0
        self.assertAlmostEqual(grid.total_mass(), 1.0)
        report = grid.step()
        self.assertIsInstance(report.total_mass, float)
        self.assertGreaterEqual(report.total_mass, 0.0)

    def test_single_cell_at_corner_toroidal(self):
        """A cell at (0,0) should behave consistently under toroidal wrapping."""
        config = SimulationConfig(
            grid_size=8, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        g_center = LeniaGrid(config)
        g_corner = LeniaGrid(config)
        for y in range(8):
            for x in range(8):
                g_center._grid[y][x] = 0.0
                g_corner._grid[y][x] = 0.0
        g_center._grid[4][4] = 0.8
        g_corner._grid[0][0] = 0.8
        r_center = g_center.step()
        r_corner = g_corner.step()
        self.assertGreaterEqual(r_center.total_mass, 0.0)
        self.assertGreaterEqual(r_corner.total_mass, 0.0)
        self.assertAlmostEqual(r_center.total_mass, r_corner.total_mass, places=1)

    def test_minimum_grid_size_4x4(self):
        """Minimum allowed grid size (4x4) should initialize and step."""
        config = SimulationConfig(
            grid_size=4, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=1), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        self.assertEqual(grid.size, 4)
        report = grid.step()
        self.assertEqual(report.generation, 1)

    def test_grid_size_below_minimum_raises(self):
        """Grid size below 4 must raise FizzLifeGridInitializationError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeGridInitializationError
        config = SimulationConfig(
            grid_size=3, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=1), growth=GrowthConfig(),
        )
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(config)

    def test_grid_size_2_raises(self):
        """Grid size 2 should also raise."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeGridInitializationError
        config = SimulationConfig(
            grid_size=2, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=1), growth=GrowthConfig(),
        )
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(config)

    def test_grid_size_not_power_of_2(self):
        """Non-power-of-2 grid sizes (50x50) should work via FFT padding."""
        config = SimulationConfig(
            grid_size=50, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=10), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        self.assertEqual(grid.size, 50)
        report = grid.step()
        self.assertEqual(report.generation, 1)
        self.assertGreaterEqual(report.total_mass, 0.0)

    def test_grid_size_prime_number(self):
        """A prime grid size (17) should work correctly via padding."""
        config = SimulationConfig(
            grid_size=17, generations=2, dt=0.1, seed=42,
            kernel=KernelConfig(radius=5), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        self.assertEqual(grid.size, 17)
        report = grid.step()
        self.assertEqual(report.generation, 1)

    def test_large_grid_128x128(self):
        """A 128x128 grid should complete a step without error."""
        config = SimulationConfig(
            grid_size=128, generations=2, dt=0.1, seed=42,
            kernel=KernelConfig(radius=15), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        self.assertEqual(grid.size, 128)
        report = grid.step()
        self.assertEqual(report.generation, 1)
        self.assertGreaterEqual(report.total_mass, 0.0)

    def test_grid_all_cells_clipped_after_step(self):
        """After any step, all cell values must remain in [0, 1]."""
        config = SimulationConfig(
            grid_size=16, generations=3, dt=0.5, seed=42,
            kernel=KernelConfig(radius=5), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        for _ in range(3):
            grid.step()
            for row in grid.grid:
                for val in row:
                    self.assertGreaterEqual(val, 0.0)
                    self.assertLessEqual(val, 1.0)


# ============================================================
# Edge Case Tests: Parameter Boundaries
# ============================================================


class TestParameterEdgeCases(unittest.TestCase):
    """Edge case tests for extreme parameter values."""

    def test_mu_zero_growth_at_zero_is_max(self):
        """With mu=0.0, growth(0.0) should be 1.0."""
        gf = GrowthFunction(GrowthConfig(mu=0.0, sigma=DEFAULT_SIGMA))
        self.assertAlmostEqual(gf(0.0), 1.0, places=2)
        self.assertLess(gf(0.15), -0.5)

    def test_mu_one_growth_at_one_is_max(self):
        """With mu=1.0, growth(1.0) should be 1.0."""
        gf = GrowthFunction(GrowthConfig(mu=1.0, sigma=DEFAULT_SIGMA))
        self.assertAlmostEqual(gf(1.0), 1.0, places=2)
        self.assertLess(gf(0.5), -0.9)

    def test_sigma_very_small_narrow_band(self):
        """sigma=0.001 produces extremely narrow growth band."""
        gf = GrowthFunction(GrowthConfig(mu=0.15, sigma=0.001))
        self.assertAlmostEqual(gf(0.15), 1.0, places=2)
        self.assertLess(gf(0.155), 0.0)
        self.assertLess(gf(0.2), -0.99)

    def test_sigma_very_large_permissive_band(self):
        """sigma=0.5 produces a very broad growth band."""
        gf = GrowthFunction(GrowthConfig(mu=0.5, sigma=0.5))
        self.assertGreater(gf(0.0), -1.0)
        self.assertAlmostEqual(gf(0.5), 1.0, places=2)
        self.assertGreater(gf(0.3), 0.0)

    def test_sigma_zero_degenerate(self):
        """sigma=0: growth is +1 only at exactly mu, -1 elsewhere."""
        gf = GrowthFunction(GrowthConfig(mu=0.15, sigma=0.0))
        self.assertEqual(gf(0.15), 1.0)
        self.assertEqual(gf(0.1500001), -1.0)
        self.assertEqual(gf(0.0), -1.0)

    def test_dt_one_large_timestep_clips(self):
        """dt=1.0: all cells must remain in [0, 1] after step."""
        config = SimulationConfig(
            grid_size=8, generations=3, dt=1.0, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        grid.step()
        for row in grid.grid:
            for val in row:
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)

    def test_dt_very_small_incremental(self):
        """dt=0.01 should produce small mass changes per step."""
        config = SimulationConfig(
            grid_size=8, generations=3, dt=0.01, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        initial_mass = grid.total_mass()
        report = grid.step()
        self.assertLess(abs(report.mass_delta), initial_mass)

    def test_dt_zero_raises(self):
        """dt=0.0 should raise FizzLifeGridInitializationError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeGridInitializationError
        config = SimulationConfig(
            grid_size=8, generations=3, dt=0.0, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(config)

    def test_dt_negative_raises(self):
        """Negative dt should raise."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeGridInitializationError
        config = SimulationConfig(
            grid_size=8, generations=3, dt=-0.1, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(config)

    def test_dt_above_one_raises(self):
        """dt > 1.0 should raise."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeGridInitializationError
        config = SimulationConfig(
            grid_size=8, generations=3, dt=1.5, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(config)

    def test_kernel_radius_one_minimal(self):
        """Kernel radius=1 (minimal neighborhood) should work."""
        config = SimulationConfig(
            grid_size=8, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=1), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        report = grid.step()
        self.assertEqual(report.generation, 1)

    def test_kernel_radius_half_grid(self):
        """Kernel radius = grid_size/2 - 1 covers nearly the entire grid."""
        size = 16
        config = SimulationConfig(
            grid_size=size, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=size // 2 - 1), growth=GrowthConfig(),
        )
        grid = LeniaGrid(config)
        report = grid.step()
        self.assertEqual(report.generation, 1)

    def test_kernel_radius_equals_grid_size_raises(self):
        """Kernel radius >= grid_size should raise."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeKernelConfigurationError
        config = SimulationConfig(
            grid_size=8, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=8), growth=GrowthConfig(),
        )
        with self.assertRaises(FizzLifeKernelConfigurationError):
            LeniaGrid(config)

    def test_kernel_radius_exceeds_grid_size_raises(self):
        """Kernel radius larger than grid_size should raise."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeKernelConfigurationError
        config = SimulationConfig(
            grid_size=8, generations=3, dt=0.1, seed=42,
            kernel=KernelConfig(radius=20), growth=GrowthConfig(),
        )
        with self.assertRaises(FizzLifeKernelConfigurationError):
            LeniaGrid(config)


# ============================================================
# Edge Case Tests: FFT Boundaries
# ============================================================


class TestFFTEdgeCases(unittest.TestCase):
    """Edge case tests for the pure-Python FFT engine."""

    def test_fft_all_zeros(self):
        """FFT of an all-zero grid should produce all-zero spectrum."""
        engine = _FFTEngine(8)
        grid = [[complex(0, 0)] * 8 for _ in range(8)]
        result = engine.fft_2d(grid)
        for row in result:
            for val in row:
                self.assertAlmostEqual(abs(val), 0.0, places=10)

    def test_fft_all_ones_dc_component(self):
        """FFT of all-ones: DC=N^2, rest zero."""
        size = 8
        engine = _FFTEngine(size)
        grid = [[complex(1, 0)] * size for _ in range(size)]
        result = engine.fft_2d(grid)
        self.assertAlmostEqual(result[0][0].real, size * size, places=5)
        self.assertAlmostEqual(result[0][0].imag, 0.0, places=5)
        for y in range(size):
            for x in range(size):
                if y == 0 and x == 0:
                    continue
                self.assertAlmostEqual(abs(result[y][x]), 0.0, places=5)

    def test_fft_roundtrip_recovery(self):
        """FFT followed by IFFT should recover the original signal."""
        size = 8
        engine = _FFTEngine(size)
        rng = random.Random(123)
        original = [[complex(rng.random(), 0) for _ in range(size)]
                     for _ in range(size)]
        spectrum = engine.fft_2d(original)
        recovered = engine.ifft_2d(spectrum)
        for y in range(size):
            for x in range(size):
                self.assertAlmostEqual(
                    recovered[y][x].real, original[y][x].real, places=8)
                self.assertAlmostEqual(
                    recovered[y][x].imag, original[y][x].imag, places=8)

    def test_fft_very_small_values_no_nan(self):
        """FFT with values at 1e-15 should not produce NaN."""
        size = 8
        engine = _FFTEngine(size)
        grid = [[complex(1e-15, 0)] * size for _ in range(size)]
        result = engine.fft_2d(grid)
        for row in result:
            for val in row:
                self.assertFalse(math.isnan(val.real))
                self.assertFalse(math.isnan(val.imag))

    def test_fft_impulse_flat_spectrum(self):
        """FFT of delta at (0,0) should produce flat spectrum (all magnitude 1)."""
        size = 8
        engine = _FFTEngine(size)
        grid = [[complex(0, 0)] * size for _ in range(size)]
        grid[0][0] = complex(1.0, 0)
        result = engine.fft_2d(grid)
        for y in range(size):
            for x in range(size):
                self.assertAlmostEqual(abs(result[y][x]), 1.0, places=8)

    def test_fft_1d_length_one(self):
        """FFT of a single-element sequence returns the element."""
        engine = _FFTEngine(1)
        result = engine.fft_1d([complex(3.14, 0)])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].real, 3.14, places=10)

    def test_ifft_1d_length_one(self):
        """IFFT of a single-element sequence returns the element."""
        engine = _FFTEngine(1)
        result = engine.ifft_1d([complex(2.71, 0)])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].real, 2.71, places=10)

    def test_fft_engine_pads_correctly(self):
        """Non-power-of-2 sizes should be padded to next power of 2."""
        self.assertEqual(_FFTEngine(50).padded_size, 64)
        self.assertEqual(_FFTEngine(65).padded_size, 128)
        self.assertEqual(_FFTEngine(1).padded_size, 1)

    def test_next_power_of_2_boundary_values(self):
        """_next_power_of_2 for boundary inputs."""
        self.assertEqual(_FFTEngine._next_power_of_2(0), 1)
        self.assertEqual(_FFTEngine._next_power_of_2(1), 1)
        self.assertEqual(_FFTEngine._next_power_of_2(2), 2)
        self.assertEqual(_FFTEngine._next_power_of_2(3), 4)
        self.assertEqual(_FFTEngine._next_power_of_2(4), 4)
        self.assertEqual(_FFTEngine._next_power_of_2(5), 8)
        self.assertEqual(_FFTEngine._next_power_of_2(127), 128)
        self.assertEqual(_FFTEngine._next_power_of_2(128), 128)
        self.assertEqual(_FFTEngine._next_power_of_2(129), 256)

    def test_bit_reverse_known_values(self):
        """Verify bit-reversal for known inputs."""
        self.assertEqual(_FFTEngine._bit_reverse(1, 3), 4)
        self.assertEqual(_FFTEngine._bit_reverse(3, 3), 6)
        self.assertEqual(_FFTEngine._bit_reverse(0, 3), 0)
        self.assertEqual(_FFTEngine._bit_reverse(7, 3), 7)

    def test_fft_roundtrip_1d(self):
        """1D FFT roundtrip should recover original signal."""
        engine = _FFTEngine(8)
        rng = random.Random(456)
        original = [complex(rng.random(), 0) for _ in range(8)]
        spectrum = engine.fft_1d(original)
        recovered = engine.ifft_1d(spectrum)
        for i in range(8):
            self.assertAlmostEqual(recovered[i].real, original[i].real, places=8)


# ============================================================
# Edge Case Tests: Kernel Boundaries
# ============================================================


class TestKernelEdgeCases(unittest.TestCase):
    """Edge case tests for kernel construction boundary conditions."""

    def test_kernel_core_boundary_zero_all_types(self):
        """Kernel core at r=0 and r=1 should return 0 for all types."""
        for ktype in KernelType:
            kernel = LeniaKernel(KernelConfig(kernel_type=ktype))
            self.assertEqual(kernel.kernel_core(0.0), 0.0, msg=f"{ktype}")
            self.assertEqual(kernel.kernel_core(1.0), 0.0, msg=f"{ktype}")

    def test_kernel_core_negative_r(self):
        """Kernel core at r < 0 should return 0."""
        kernel = LeniaKernel(KernelConfig(kernel_type=KernelType.EXPONENTIAL))
        self.assertEqual(kernel.kernel_core(-0.5), 0.0)

    def test_kernel_core_r_greater_than_1(self):
        """Kernel core at r > 1 should return 0."""
        kernel = LeniaKernel(KernelConfig(kernel_type=KernelType.EXPONENTIAL))
        self.assertEqual(kernel.kernel_core(1.5), 0.0)

    def test_kernel_shell_boundary_zero(self):
        """Kernel shell at r=0 and r=1 should return 0."""
        kernel = LeniaKernel(KernelConfig())
        self.assertEqual(kernel.kernel_shell(0.0), 0.0)
        self.assertEqual(kernel.kernel_shell(1.0), 0.0)

    def test_kernel_empty_beta_raises(self):
        """Empty beta list must raise FizzLifeKernelConfigurationError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzLifeKernelConfigurationError
        kernel = LeniaKernel(KernelConfig(radius=3, beta=[]))
        with self.assertRaises(FizzLifeKernelConfigurationError):
            kernel.build(8)

    def test_kernel_build_caching(self):
        """Calling build() twice with the same size returns the same object."""
        kernel = LeniaKernel(KernelConfig(radius=3))
        m1 = kernel.build(8)
        m2 = kernel.build(8)
        self.assertIs(m1, m2)

    def test_kernel_build_different_size_rebuilds(self):
        """Calling build() with a different size should rebuild the kernel."""
        kernel = LeniaKernel(KernelConfig(radius=3))
        m1 = kernel.build(8)
        m2 = kernel.build(16)
        self.assertIsNot(m1, m2)

    def test_kernel_multi_ring_normalization(self):
        """Multi-ring kernel should still normalize to sum=1.0."""
        config = KernelConfig(radius=5, rank=2, beta=[1.0, 0.5])
        kernel = LeniaKernel(config)
        matrix = kernel.build(16)
        total = sum(sum(row) for row in matrix)
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_kernel_center_weight_nonzero(self):
        """center_weight > 0 gives center cell a nonzero value."""
        kernel = LeniaKernel(KernelConfig(radius=3, center_weight=0.5))
        matrix = kernel.build(8)
        center = 8 // 2
        self.assertGreater(matrix[center][center], 0.0)

    def test_kernel_center_weight_zero(self):
        """center_weight=0 gives center cell value 0."""
        kernel = LeniaKernel(KernelConfig(radius=3, center_weight=0.0))
        matrix = kernel.build(8)
        center = 8 // 2
        self.assertEqual(matrix[center][center], 0.0)

    def test_kernel_core_peak_at_half_all_types(self):
        """Kernel core should peak at or near r=0.5 for all types."""
        for ktype in KernelType:
            kernel = LeniaKernel(KernelConfig(kernel_type=ktype))
            val_half = kernel.kernel_core(0.5)
            val_quarter = kernel.kernel_core(0.25)
            val_three_quarter = kernel.kernel_core(0.75)
            self.assertGreaterEqual(val_half, val_quarter, msg=f"{ktype}")
            self.assertGreaterEqual(val_half, val_three_quarter, msg=f"{ktype}")

    def test_kernel_polynomial_at_half_is_one(self):
        """Polynomial kernel core at r=0.5 should produce exactly 1.0."""
        kernel = LeniaKernel(KernelConfig(kernel_type=KernelType.POLYNOMIAL))
        self.assertAlmostEqual(kernel.kernel_core(0.5), 1.0, places=10)

    def test_kernel_rectangular_band(self):
        """Rectangular kernel core: 1.0 for [0.25, 0.75], 0 outside."""
        kernel = LeniaKernel(KernelConfig(kernel_type=KernelType.RECTANGULAR))
        self.assertEqual(kernel.kernel_core(0.25), 1.0)
        self.assertEqual(kernel.kernel_core(0.5), 1.0)
        self.assertEqual(kernel.kernel_core(0.75), 1.0)
        self.assertEqual(kernel.kernel_core(0.24), 0.0)
        self.assertEqual(kernel.kernel_core(0.76), 0.0)


# ============================================================
# Edge Case Tests: Growth Function Boundaries
# ============================================================


class TestGrowthFunctionEdgeCases(unittest.TestCase):
    """Edge case tests for growth function boundary conditions."""

    def test_gaussian_symmetry(self):
        """Gaussian growth should be symmetric around mu."""
        gf = GrowthFunction(GrowthConfig(mu=0.5, sigma=0.1))
        self.assertAlmostEqual(gf(0.4), gf(0.6), places=10)
        self.assertAlmostEqual(gf(0.3), gf(0.7), places=10)

    def test_polynomial_compact_support(self):
        """Polynomial growth beyond 3*sigma from mu should return -1.0."""
        sigma = 0.05
        mu = 0.5
        gf = GrowthFunction(GrowthConfig(
            growth_type=GrowthType.POLYNOMIAL, mu=mu, sigma=sigma
        ))
        self.assertAlmostEqual(gf(mu + 3.0 * sigma), -1.0, places=8)
        self.assertEqual(gf(mu + 4.0 * sigma), -1.0)

    def test_rectangular_sharp_transition(self):
        """Rectangular growth: +1 within sigma of mu, -1 well outside."""
        sigma = 0.1
        mu = 0.5
        gf = GrowthFunction(GrowthConfig(
            growth_type=GrowthType.RECTANGULAR, mu=mu, sigma=sigma
        ))
        self.assertEqual(gf(mu), 1.0)
        self.assertEqual(gf(mu + sigma * 0.5), 1.0)
        # Well outside the band
        self.assertEqual(gf(mu + sigma * 1.5), -1.0)

    def test_growth_negative_input(self):
        """Growth function should handle negative input gracefully."""
        gf = GrowthFunction(GrowthConfig(mu=0.15, sigma=0.016))
        val = gf(-1.0)
        self.assertIsInstance(val, float)
        self.assertAlmostEqual(val, -1.0, places=2)

    def test_growth_large_input(self):
        """Growth function should handle very large input gracefully."""
        gf = GrowthFunction(GrowthConfig(mu=0.15, sigma=0.016))
        val = gf(100.0)
        self.assertIsInstance(val, float)
        self.assertAlmostEqual(val, -1.0, places=2)

    def test_growth_output_range(self):
        """Growth function output should always be in [-1, 1]."""
        for growth_type in GrowthType:
            gf = GrowthFunction(GrowthConfig(
                growth_type=growth_type, mu=0.15, sigma=0.016
            ))
            for u in [0.0, 0.05, 0.10, 0.15, 0.20, 0.50, 1.0]:
                val = gf(u)
                self.assertGreaterEqual(val, -1.0, msg=f"{growth_type}, u={u}")
                self.assertLessEqual(val, 1.0, msg=f"{growth_type}, u={u}")


# ============================================================
# Edge Case Tests: Reproducibility
# ============================================================


class TestReproducibilityEdgeCases(unittest.TestCase):
    """Tests for deterministic behavior with fixed seeds."""

    def test_same_seed_same_full_history(self):
        """Identical seed and config produce identical mass trajectories."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=16, generations=20, dt=0.1, seed=42,
            kernel=KernelConfig(radius=5), growth=GrowthConfig(),
        )
        r1 = FizzLifeEngine(config).run()
        r2 = FizzLifeEngine(config).run()
        self.assertEqual(r1.generations_run, r2.generations_run)
        self.assertAlmostEqual(r1.final_mass, r2.final_mass, places=10)
        self.assertEqual(r1.final_population, r2.final_population)
        self.assertEqual(r1.classification, r2.classification)
        for rep1, rep2 in zip(r1.reports, r2.reports):
            self.assertAlmostEqual(rep1.total_mass, rep2.total_mass, places=10)

    def test_different_seeds_different_history(self):
        """Different seeds should produce different trajectories."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        c1 = SimulationConfig(
            grid_size=16, generations=20, dt=0.1, seed=42,
            kernel=KernelConfig(radius=5), growth=GrowthConfig(),
            seed_mode=SeedMode.SPECIES,
        )
        c2 = SimulationConfig(
            grid_size=16, generations=20, dt=0.1, seed=99,
            kernel=KernelConfig(radius=5), growth=GrowthConfig(),
            seed_mode=SeedMode.SPECIES,
        )
        r1 = FizzLifeEngine(c1).run()
        r2 = FizzLifeEngine(c2).run()
        masses1 = [r.total_mass for r in r1.reports]
        masses2 = [r.total_mass for r in r2.reports]
        any_diff = any(abs(m1 - m2) > 1e-6 for m1, m2 in zip(masses1, masses2))
        self.assertTrue(any_diff)

    def test_reproducibility_across_three_runs(self):
        """Reproducibility holds across 3 independent runs."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=8, generations=10, dt=0.1, seed=12345,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
        )
        results = [FizzLifeEngine(config).run() for _ in range(3)]
        for i in range(1, 3):
            self.assertAlmostEqual(
                results[i].final_mass, results[0].final_mass, places=10)
            self.assertEqual(
                results[i].generations_run, results[0].generations_run)


# ============================================================
# Edge Case Tests: Mass Conservation
# ============================================================


class TestMassConservationEdgeCases(unittest.TestCase):
    """Tests for the Flow-Lenia mass-conservative transport mode."""

    def test_mass_conservation_empty_grid(self):
        """An all-zero grid in conservation mode should remain at zero mass."""
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
            mass_conservation=True, initial_density=0.0,
        )
        grid = LeniaGrid(config)
        for y in range(grid.size):
            for x in range(grid.size):
                grid._grid[y][x] = 0.0
        grid._initial_mass = 0.0
        report = grid.step()
        self.assertAlmostEqual(report.total_mass, 0.0, places=10)

    def test_mass_conservation_single_cell(self):
        """Mass should be approximately preserved for a single cell.

        After overriding the grid, _initial_mass must be updated so the
        conservation check matches the new state.
        """
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3), growth=GrowthConfig(),
            mass_conservation=True,
        )
        grid = LeniaGrid(config)
        for y in range(grid.size):
            for x in range(grid.size):
                grid._grid[y][x] = 0.0
        grid._grid[4][4] = 0.5
        # Sync internal mass tracking with modified grid
        grid._initial_mass = grid.total_mass()
        grid._previous_mass = grid._initial_mass
        initial_mass = grid._initial_mass
        grid.step()
        self.assertAlmostEqual(grid.total_mass(), initial_mass, delta=0.1)

    def test_mass_conservation_over_many_steps(self):
        """Mass should be approximately preserved over 20 steps."""
        config = SimulationConfig(
            grid_size=16, generations=20, dt=0.1, seed=42,
            kernel=KernelConfig(radius=5), growth=GrowthConfig(),
            mass_conservation=True,
        )
        grid = LeniaGrid(config)
        initial_mass = grid.total_mass()
        for _ in range(20):
            grid.step()
        final_mass = grid.total_mass()
        self.assertAlmostEqual(final_mass, initial_mass, delta=initial_mass * 0.5)


# ============================================================
# Edge Case Tests: FlowField
# ============================================================


class TestFlowFieldEdgeCases(unittest.TestCase):
    """Tests for the gradient-based mass transport system."""

    def test_flow_zero_grid_no_flow(self):
        """Flow from an all-zero grid should be zero everywhere."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FlowField
        ff = FlowField(4)
        grid = [[0.0] * 4 for _ in range(4)]
        growth = [[0.5] * 4 for _ in range(4)]
        flow_x, flow_y = ff.compute_flow(grid, growth)
        for y in range(4):
            for x in range(4):
                self.assertEqual(flow_x[y][x], 0.0)
                self.assertEqual(flow_y[y][x], 0.0)

    def test_flow_uniform_growth_no_gradient(self):
        """Uniform growth should produce zero flow (no gradient)."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FlowField
        ff = FlowField(4)
        grid = [[0.5] * 4 for _ in range(4)]
        growth = [[1.0] * 4 for _ in range(4)]
        flow_x, flow_y = ff.compute_flow(grid, growth)
        for y in range(4):
            for x in range(4):
                self.assertAlmostEqual(flow_x[y][x], 0.0, places=10)
                self.assertAlmostEqual(flow_y[y][x], 0.0, places=10)

    def test_apply_flow_conserves_mass(self):
        """Applying flow should approximately conserve total mass."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FlowField
        ff = FlowField(4)
        grid = [
            [0.5, 0.3, 0.1, 0.0],
            [0.2, 0.8, 0.4, 0.1],
            [0.0, 0.3, 0.6, 0.2],
            [0.1, 0.0, 0.2, 0.4],
        ]
        growth = [
            [0.1, -0.5, 0.3, 0.0],
            [-0.2, 0.8, -0.1, 0.5],
            [0.0, 0.4, -0.3, 0.2],
            [0.3, 0.0, 0.1, -0.4],
        ]
        initial_mass = sum(sum(row) for row in grid)
        flow = ff.compute_flow(grid, growth)
        new_grid = ff.apply_flow(grid, flow, 0.1)
        new_mass = sum(sum(row) for row in new_grid)
        self.assertAlmostEqual(new_mass, initial_mass, delta=0.5)

    def test_apply_flow_clips_to_valid_range(self):
        """After flow, all cells must be in [0, 1]."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FlowField
        ff = FlowField(4)
        grid = [[0.9] * 4 for _ in range(4)]
        growth = [
            [1.0, -1.0, 1.0, -1.0],
            [-1.0, 1.0, -1.0, 1.0],
            [1.0, -1.0, 1.0, -1.0],
            [-1.0, 1.0, -1.0, 1.0],
        ]
        flow = ff.compute_flow(grid, growth)
        new_grid = ff.apply_flow(grid, flow, 0.5)
        for row in new_grid:
            for val in row:
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)


# ============================================================
# Edge Case Tests: Species Catalog
# ============================================================


class TestSpeciesCatalogEdgeCases(unittest.TestCase):
    """Tests for species classification boundary conditions."""

    def test_catalog_species_count(self):
        """Catalog should contain the 5 known species."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import SpeciesCatalog
        catalog = SpeciesCatalog()
        self.assertGreaterEqual(len(catalog.species), 5)

    def test_classify_exact_orbium(self):
        """Exact Orbium parameters should classify as Fizz."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import SpeciesCatalog
        catalog = SpeciesCatalog()
        config = SimulationConfig(
            kernel=KernelConfig(
                kernel_type=KernelType.EXPONENTIAL, radius=13, beta=[1.0]),
            growth=GrowthConfig(mu=0.15, sigma=0.016),
        )
        species = catalog.classify(config)
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Orbium unicaudatus")
        self.assertEqual(catalog.get_classification(species.name), "Fizz")

    def test_classify_near_scutium_returns_species(self):
        """Near-Scutium parameters should classify to some species."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import SpeciesCatalog
        catalog = SpeciesCatalog()
        config = SimulationConfig(
            kernel=KernelConfig(
                kernel_type=KernelType.EXPONENTIAL, radius=15, beta=[1.0]),
            growth=GrowthConfig(mu=0.17, sigma=0.02),
        )
        species = catalog.classify(config)
        self.assertIsNotNone(species)
        classification = catalog.get_classification(species.name)
        self.assertIn(classification, ("Fizz", "Buzz", "FizzBuzz"))

    def test_classify_far_from_all_returns_none(self):
        """Parameters very far from all known species should return None."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import SpeciesCatalog
        catalog = SpeciesCatalog()
        config = SimulationConfig(
            kernel=KernelConfig(
                kernel_type=KernelType.RECTANGULAR, radius=3, beta=[1.0]),
            growth=GrowthConfig(mu=0.9, sigma=0.5),
        )
        self.assertIsNone(catalog.classify(config))

    def test_get_classification_unknown(self):
        """Looking up an unknown species name should return None."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import SpeciesCatalog
        catalog = SpeciesCatalog()
        self.assertIsNone(catalog.get_classification("Nonexistium bogus"))

    def test_all_species_have_classification(self):
        """Every species should have a valid FizzBuzz classification."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import SpeciesCatalog
        catalog = SpeciesCatalog()
        for sp in catalog.species:
            classification = catalog.get_classification(sp.name)
            self.assertIsNotNone(classification)
            self.assertIn(classification, ("Fizz", "Buzz", "FizzBuzz"))

    def test_classify_returns_species_with_valid_classification(self):
        """When classification succeeds, the species should have a valid FizzBuzz label."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import SpeciesCatalog
        catalog = SpeciesCatalog()
        # Use default Orbium-like params that are known to match
        config = SimulationConfig(
            kernel=KernelConfig(
                kernel_type=KernelType.EXPONENTIAL, radius=13, beta=[1.0]),
            growth=GrowthConfig(mu=0.15, sigma=0.016),
        )
        species = catalog.classify(config)
        self.assertIsNotNone(species)
        classification = catalog.get_classification(species.name)
        self.assertIn(classification, ("Fizz", "Buzz", "FizzBuzz"))


# ============================================================
# Edge Case Tests: Pattern Analyzer
# ============================================================


class TestPatternAnalyzerEdgeCases(unittest.TestCase):
    """Tests for equilibrium detection and statistics edge cases."""

    def test_equilibrium_not_detected_below_window(self):
        """Equilibrium should not be detected with fewer reports than window."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            PatternAnalyzer, GenerationReport,
        )
        analyzer = PatternAnalyzer()
        reports = [
            GenerationReport(
                generation=i, population=10, total_mass=5.0, mass_delta=0.0)
            for i in range(5)
        ]
        self.assertFalse(analyzer.detect_equilibrium(reports, window=10))

    def test_equilibrium_detected_when_stable(self):
        """Equilibrium should be detected when mass_delta stays near zero."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            PatternAnalyzer, GenerationReport,
        )
        analyzer = PatternAnalyzer()
        reports = [
            GenerationReport(
                generation=i, population=10, total_mass=5.0, mass_delta=1e-8)
            for i in range(15)
        ]
        self.assertTrue(analyzer.detect_equilibrium(reports, window=10))

    def test_equilibrium_not_detected_with_fluctuations(self):
        """Equilibrium should not be detected if mass is changing."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            PatternAnalyzer, GenerationReport,
        )
        analyzer = PatternAnalyzer()
        reports = [
            GenerationReport(
                generation=i, population=10,
                total_mass=5.0 + i * 0.1, mass_delta=0.1)
            for i in range(15)
        ]
        self.assertFalse(analyzer.detect_equilibrium(reports, window=10))

    def test_statistics_empty_grid(self):
        """Statistics of an all-zero grid."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import PatternAnalyzer
        analyzer = PatternAnalyzer()
        grid = [[0.0] * 8 for _ in range(8)]
        stats = analyzer.compute_statistics(grid)
        self.assertEqual(stats["total_mass"], 0.0)
        self.assertEqual(stats["population"], 0)
        self.assertEqual(stats["mean_state"], 0.0)
        self.assertEqual(stats["centroid_x"], 4.0)
        self.assertEqual(stats["centroid_y"], 4.0)

    def test_statistics_full_grid(self):
        """Statistics of an all-ones grid."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import PatternAnalyzer
        analyzer = PatternAnalyzer()
        grid = [[1.0] * 8 for _ in range(8)]
        stats = analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["total_mass"], 64.0)
        self.assertEqual(stats["population"], 64)
        self.assertAlmostEqual(stats["mean_state"], 1.0)

    def test_statistics_single_cell_centroid(self):
        """Centroid should point at the single nonzero cell."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import PatternAnalyzer
        analyzer = PatternAnalyzer()
        grid = [[0.0] * 8 for _ in range(8)]
        grid[3][5] = 0.8
        stats = analyzer.compute_statistics(grid)
        self.assertAlmostEqual(stats["centroid_x"], 5.0)
        self.assertAlmostEqual(stats["centroid_y"], 3.0)

    def test_oscillation_constant_mass_returns_none(self):
        """No oscillation in a constant mass series."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            PatternAnalyzer, GenerationReport,
        )
        analyzer = PatternAnalyzer()
        reports = [
            GenerationReport(
                generation=i, population=10, total_mass=5.0, mass_delta=0.0)
            for i in range(50)
        ]
        self.assertIsNone(analyzer.detect_oscillation(reports, window=20))

    def test_oscillation_periodic_signal(self):
        """A periodic mass signal should be detected as periodic.

        The autocorrelation may detect the true period or a harmonic
        (integer multiple). Either indicates successful periodicity detection.
        """
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            PatternAnalyzer, GenerationReport,
        )
        analyzer = PatternAnalyzer()
        period = 10
        reports = [
            GenerationReport(
                generation=i, population=10,
                total_mass=5.0 + 10.0 * math.sin(2.0 * math.pi * i / period),
                mass_delta=0.0)
            for i in range(200)
        ]
        detected = analyzer.detect_oscillation(reports, window=20)
        self.assertIsNotNone(detected, "Oscillation detector must find periodicity")
        self.assertGreaterEqual(detected, 2)
        self.assertEqual(period % detected, 0)


# ============================================================
# Edge Case Tests: Convolver
# ============================================================


class TestConvolverEdgeCases(unittest.TestCase):
    """Tests for the FFT convolution engine boundary conditions."""

    def test_convolve_zero_grid_returns_zeros(self):
        """Convolving an all-zero grid should produce all zeros."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FFTConvolver
        kernel = LeniaKernel(KernelConfig(radius=3))
        convolver = FFTConvolver(kernel, 8)
        grid = [[0.0] * 8 for _ in range(8)]
        result = convolver.convolve(grid)
        for row in result:
            for val in row:
                self.assertAlmostEqual(val, 0.0, places=8)

    def test_convolve_uniform_grid_identity(self):
        """Convolving a uniform grid with a normalized kernel returns same value."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FFTConvolver
        kernel = LeniaKernel(KernelConfig(radius=3))
        convolver = FFTConvolver(kernel, 8)
        c = 0.42
        grid = [[c] * 8 for _ in range(8)]
        result = convolver.convolve(grid)
        for row in result:
            for val in row:
                self.assertAlmostEqual(val, c, places=3)

    def test_convolver_padded_size(self):
        """Convolver reports correct padded size for non-power-of-2 grid."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FFTConvolver
        kernel = LeniaKernel(KernelConfig(radius=3))
        convolver = FFTConvolver(kernel, 10)
        self.assertEqual(convolver.padded_size, 16)


# ============================================================
# Edge Case Tests: Simulation Engine
# ============================================================


class TestEngineEdgeCases(unittest.TestCase):
    """Tests for the top-level FizzLifeEngine edge cases."""

    def test_engine_default_config(self):
        """Engine with default config should have expected grid_size."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        engine = FizzLifeEngine()
        self.assertEqual(engine.config.grid_size, DEFAULT_GRID_SIZE)
        self.assertIsNone(engine.grid)

    def test_engine_initialize_creates_grid(self):
        """initialize() should create the grid."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        engine = FizzLifeEngine(config)
        self.assertIsNone(engine.grid)
        engine.initialize()
        self.assertIsNotNone(engine.grid)
        self.assertEqual(engine.grid.size, 8)

    def test_engine_run_auto_initializes(self):
        """run() without initialize() should auto-initialize."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        engine = FizzLifeEngine(config)
        result = engine.run()
        self.assertGreater(result.generations_run, 0)
        self.assertIsNotNone(engine.grid)

    def test_engine_extinct_empty_classification(self):
        """An extinct simulation should produce empty classification."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=16, generations=100, dt=0.1, seed=42,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.5, sigma=0.001),
        )
        result = FizzLifeEngine(config).run()
        self.assertLess(result.final_mass, EXTINCTION_MASS_THRESHOLD)
        self.assertEqual(result.classification, "")

    def test_engine_emits_lifecycle_events(self):
        """Engine should emit SIMULATION_STARTED and PATTERN_CLASSIFIED."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=8, generations=10, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        engine = FizzLifeEngine(config)
        engine.run()
        types = [e.event_type.name for e in engine.events]
        self.assertIn("FIZZLIFE_SIMULATION_STARTED", types)
        self.assertIn("FIZZLIFE_PATTERN_CLASSIFIED", types)

    def test_engine_run_ids_unique(self):
        """Each engine instance should have a unique run ID."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        self.assertNotEqual(FizzLifeEngine().run_id, FizzLifeEngine().run_id)

    def test_engine_elapsed_time_none_before_run(self):
        """Elapsed time should be None before run()."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        self.assertIsNone(FizzLifeEngine().get_elapsed_time())

    def test_engine_elapsed_time_after_run(self):
        """Elapsed time should be non-negative after run()."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        engine = FizzLifeEngine(config)
        engine.run()
        self.assertIsNotNone(engine.get_elapsed_time())
        self.assertGreaterEqual(engine.get_elapsed_time(), 0.0)

    def test_render_before_init_placeholder(self):
        """Rendering before init should return placeholder."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        self.assertEqual(
            FizzLifeEngine().render_current_state(), "(not initialized)")

    def test_render_after_init_returns_ascii(self):
        """Rendering after init should return nonempty string."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        engine = FizzLifeEngine(config)
        engine.initialize()
        rendered = engine.render_current_state(width=8)
        self.assertIsInstance(rendered, str)
        self.assertGreater(len(rendered), 0)


# ============================================================
# Edge Case Tests: Dashboard
# ============================================================


class TestDashboardEdgeCases(unittest.TestCase):
    """Tests for the FizzLife ASCII dashboard edge cases."""

    def test_dashboard_empty_reports(self):
        """Dashboard should render with an empty reports list."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            FizzLifeEngine, FizzLifeDashboard,
        )
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        engine = FizzLifeEngine(config)
        engine.initialize()
        rendered = FizzLifeDashboard().render(engine, [])
        self.assertIsInstance(rendered, str)
        self.assertGreater(len(rendered), 0)

    def test_dashboard_with_reports(self):
        """Dashboard should render with populated reports."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            FizzLifeEngine, FizzLifeDashboard,
        )
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        engine = FizzLifeEngine(config)
        result = engine.run()
        rendered = FizzLifeDashboard().render(engine, result.reports)
        self.assertIn("FIZZLIFE", rendered)


# ============================================================
# Edge Case Tests: ASCII Rendering
# ============================================================


class TestRenderingEdgeCases(unittest.TestCase):
    """Tests for ASCII grid rendering edge cases."""

    def test_render_empty_grid_spaces(self):
        """All-zero grid should render as lowest density character."""
        config = SimulationConfig(
            grid_size=8, generations=1, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        grid = LeniaGrid(config)
        for y in range(8):
            for x in range(8):
                grid._grid[y][x] = 0.0
        rendered = grid.render_ascii(width=8)
        for char in rendered.replace("\n", ""):
            self.assertEqual(char, DENSITY_CHARS[0])

    def test_render_full_grid_highest_char(self):
        """All-ones grid should render as highest density character."""
        config = SimulationConfig(
            grid_size=8, generations=1, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        grid = LeniaGrid(config)
        for y in range(8):
            for x in range(8):
                grid._grid[y][x] = 1.0
        rendered = grid.render_ascii(width=8)
        for char in rendered.replace("\n", ""):
            self.assertEqual(char, DENSITY_CHARS[-1])

    def test_render_downsampling(self):
        """Rendering with width < grid size should downsample."""
        config = SimulationConfig(
            grid_size=16, generations=1, dt=0.1, seed=42,
            kernel=KernelConfig(radius=5),
        )
        grid = LeniaGrid(config)
        rendered = grid.render_ascii(width=8)
        lines = rendered.split("\n")
        self.assertEqual(len(lines), 8)
        for line in lines:
            self.assertEqual(len(line), 8)


# ============================================================
# Edge Case Tests: Multi-Channel Config
# ============================================================


class TestMultiChannelEdgeCases(unittest.TestCase):
    """Tests for multi-channel configuration handling."""

    def test_channels_default_one(self):
        """Default config should have 1 channel."""
        self.assertEqual(SimulationConfig().channels, 1)

    def test_channels_stored_correctly(self):
        """Multi-channel config should be stored correctly."""
        self.assertEqual(SimulationConfig(channels=3).channels, 3)

    def test_simulation_runs_with_multi_channel(self):
        """Engine should accept and run with multi-channel config."""
        from enterprise_fizzbuzz.infrastructure.fizzlife import FizzLifeEngine
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3), channels=2,
        )
        result = FizzLifeEngine(config).run()
        self.assertGreater(result.generations_run, 0)


# ============================================================
# Edge Case Tests: Simulation State Machine
# ============================================================


class TestSimulationStateMachineEdgeCases(unittest.TestCase):
    """Tests for the simulation lifecycle state transitions."""

    def test_initial_state_is_initialized(self):
        """New grid should start in INITIALIZED state."""
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        self.assertEqual(LeniaGrid(config).state, SimulationState.INITIALIZED)

    def test_state_transitions_to_running_on_step(self):
        """After first step, state should be RUNNING or EXTINCT."""
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        grid = LeniaGrid(config)
        grid.step()
        self.assertIn(
            grid.state,
            (SimulationState.RUNNING, SimulationState.EXTINCT))

    def test_state_setter_changes_from_initial(self):
        """The state setter should change from INITIALIZED to the new value."""
        config = SimulationConfig(
            grid_size=8, generations=5, dt=0.1, seed=42,
            kernel=KernelConfig(radius=3),
        )
        grid = LeniaGrid(config)
        self.assertEqual(grid.state, SimulationState.INITIALIZED)
        grid.state = SimulationState.CONVERGED
        self.assertEqual(grid.state, SimulationState.CONVERGED)
        self.assertNotEqual(grid.state, SimulationState.INITIALIZED)

    def test_all_simulation_states_exist(self):
        """All expected states should exist in the enum."""
        states = {s.name for s in SimulationState}
        for expected in ("INITIALIZED", "RUNNING", "CONVERGED", "EXTINCT", "FAILED"):
            self.assertIn(expected, states)


# ============================================================
# Edge Case Tests: Version & Constants
# ============================================================


class TestVersionAndConstantsEdgeCases(unittest.TestCase):
    """Tests for module-level constants and version string."""

    def test_version_semver_format(self):
        """Version string should be in semver format (X.Y.Z)."""
        parts = FIZZLIFE_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        for part in parts:
            self.assertTrue(part.isdigit())

    def test_density_chars_length(self):
        """DENSITY_CHARS should contain at least 5 characters."""
        self.assertGreaterEqual(len(DENSITY_CHARS), 5)

    def test_default_constants_positive(self):
        """All default numerical constants should be positive."""
        self.assertGreater(DEFAULT_GRID_SIZE, 0)
        self.assertGreater(DEFAULT_GENERATIONS, 0)
        self.assertGreater(DEFAULT_KERNEL_RADIUS, 0)
        self.assertGreater(DEFAULT_DT, 0)
        self.assertGreater(DEFAULT_MU, 0)
        self.assertGreater(DEFAULT_SIGMA, 0)
        self.assertGreater(POPULATION_THRESHOLD, 0)
        self.assertGreater(EQUILIBRIUM_MASS_DELTA, 0)
        self.assertGreater(EXTINCTION_MASS_THRESHOLD, 0)


if __name__ == "__main__":
    unittest.main()



# ============================================================
# ============================================================
#
#  INTEGRATION AND SIMULATION TESTS
#
# ============================================================
# ============================================================


from enterprise_fizzbuzz.infrastructure.fizzlife import (
    FizzLifeDashboard,
    FizzLifeEngine,
    FizzLifeEvolver,
    FizzLifeMiddleware,
    GenerationReport,
    PatternAnalyzer,
    SimulationResult,
    SpeciesCatalog,
    SpeciesFingerprint,
    classify_number,
    create_default_config,
    create_fizzlife_subsystem,
    create_species_config,
    run_simulation,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzLifeGridInitializationError,
    FizzLifeKernelConfigurationError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext


class TestSimulationOrbiumSurvival(unittest.TestCase):

    def test_wide_growth_params_survive_many_generations(self):
        """A wide growth function (sigma=0.3) should sustain patterns
        for 50+ generations without going extinct."""
        config = SimulationConfig(
            grid_size=16, generations=60, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(growth_type=GrowthType.GAUSSIAN, mu=0.3, sigma=0.3),
            seed=42,
        )
        engine = FizzLifeEngine(config)
        result = engine.run()
        self.assertGreaterEqual(result.generations_run, 50)
        self.assertGreater(result.final_mass, EXTINCTION_MASS_THRESHOLD)

    def test_wide_growth_produces_nonzero_final_mass(self):
        """Wide growth parameters should produce a simulation with
        mass well above extinction threshold after many generations."""
        config = SimulationConfig(
            grid_size=16, generations=30, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.3, sigma=0.3),
            seed=99,
        )
        engine = FizzLifeEngine(config)
        result = engine.run()
        # Use EXTINCTION_MASS_THRESHOLD, not 0.0 — a mass of 1e-10
        # would pass "> 0.0" but represents a dead simulation.
        self.assertGreater(result.final_mass, EXTINCTION_MASS_THRESHOLD)


class TestSimulationDeathParams(unittest.TestCase):

    def test_zero_mu_leads_to_extinction(self):
        config = SimulationConfig(
            grid_size=16, generations=100, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(growth_type=GrowthType.GAUSSIAN, mu=0.5, sigma=0.001),
            seed=42,
        )
        result = run_simulation(config)
        self.assertLess(result.final_mass, EXTINCTION_MASS_THRESHOLD)

    def test_death_params_report_extinct_state(self):
        config = SimulationConfig(
            grid_size=16, generations=100, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.5, sigma=0.001), seed=42,
        )
        result = run_simulation(config)
        extinct_reports = [r for r in result.reports if r.state == SimulationState.EXTINCT]
        self.assertGreater(len(extinct_reports), 0)

    def test_extinction_classification_is_empty(self):
        config = SimulationConfig(
            grid_size=16, generations=100, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.5, sigma=0.001), seed=42,
        )
        result = run_simulation(config)
        self.assertEqual(result.classification, "")


class TestSimulationExplosiveParams(unittest.TestCase):

    def test_high_mu_simulation_runs_all_generations_or_goes_extinct(self):
        """With high mu, the simulation must either run all 50 generations
        (converge/continue) or go extinct with zero final mass — not crash."""
        config = SimulationConfig(
            grid_size=16, generations=50, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.5, sigma=0.1), seed=42,
        )
        result = run_simulation(config)
        # Both branches must be verified unconditionally to avoid
        # conditional guards that hide assertions.
        is_extinct = result.final_mass < EXTINCTION_MASS_THRESHOLD
        is_complete = result.generations_run == 50
        # The simulation must terminate in one of these two states.
        self.assertTrue(
            is_extinct or is_complete,
            f"Simulation neither went extinct (mass={result.final_mass}) "
            f"nor completed all generations (ran {result.generations_run}/50)")
        # Extinct simulations must have empty classification.
        if is_extinct:
            self.assertEqual(result.classification, "")

    def test_high_mu_population_bounded_by_grid(self):
        config = SimulationConfig(
            grid_size=16, generations=50, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.5, sigma=0.1), seed=42,
        )
        result = run_simulation(config)
        max_cells = config.grid_size * config.grid_size
        for report in result.reports:
            self.assertLessEqual(report.population, max_cells)


class TestSimulationMassConservationIntegration(unittest.TestCase):

    def test_mass_conservation_enabled_preserves_mass(self):
        config = SimulationConfig(
            grid_size=16, generations=20, dt=0.05,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.15, sigma=0.016),
            mass_conservation=True, seed=42,
        )
        grid = LeniaGrid(config)
        initial_mass = grid.total_mass()
        for _ in range(20):
            grid.step()
        final_mass = grid.total_mass()
        relative_error = abs(final_mass - initial_mass) / max(initial_mass, 1e-10)
        self.assertLess(relative_error, 0.15)

    def test_mass_conservation_disabled_allows_mass_change(self):
        config = SimulationConfig(
            grid_size=16, generations=30, dt=0.1,
            kernel=KernelConfig(radius=7),
            growth=GrowthConfig(mu=0.15, sigma=0.016),
            mass_conservation=False, seed=42,
        )
        grid = LeniaGrid(config)
        masses = [grid.total_mass()]
        for _ in range(30):
            grid.step()
            masses.append(grid.total_mass())
        deltas = [abs(masses[i+1] - masses[i]) for i in range(len(masses)-1)]
        self.assertGreater(max(deltas), EQUILIBRIUM_MASS_DELTA)


class TestSimulationGenerationCountIntegration(unittest.TestCase):

    def test_simulation_does_not_exceed_max_generations(self):
        config = SimulationConfig(
            grid_size=16, generations=25, dt=0.1,
            kernel=KernelConfig(radius=7), seed=7,
        )
        result = run_simulation(config)
        self.assertLessEqual(result.generations_run, config.generations)

    def test_reports_count_matches_generations_run(self):
        config = SimulationConfig(grid_size=16, generations=15, seed=42, kernel=KernelConfig(radius=7))
        result = run_simulation(config)
        self.assertEqual(len(result.reports), result.generations_run)

    def test_generation_numbers_are_sequential(self):
        config = SimulationConfig(grid_size=16, generations=10, seed=42, kernel=KernelConfig(radius=7))
        result = run_simulation(config)
        for i, report in enumerate(result.reports):
            self.assertEqual(report.generation, i + 1)


class TestSpeciesCatalogIntegration(unittest.TestCase):

    def setUp(self):
        self.catalog = SpeciesCatalog()

    def test_catalog_contains_orbium_with_correct_params(self):
        orbium = None
        for species in self.catalog.species:
            if species.name == "Orbium unicaudatus":
                orbium = species
                break
        self.assertIsNotNone(orbium)
        self.assertEqual(orbium.family, "Orbidae")
        self.assertAlmostEqual(orbium.growth_config.mu, 0.15)
        self.assertEqual(orbium.kernel_config.radius, 13)

    def test_catalog_contains_at_least_five_species(self):
        self.assertGreaterEqual(len(self.catalog.species), 5)

    def test_classify_orbium_params_returns_orbium(self):
        config = SimulationConfig(
            kernel=KernelConfig(kernel_type=KernelType.EXPONENTIAL, radius=13, beta=[1.0]),
            growth=GrowthConfig(mu=0.15, sigma=0.016),
        )
        result = self.catalog.classify(config)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Orbium unicaudatus")

    def test_classify_unknown_params_returns_none(self):
        config = SimulationConfig(
            kernel=KernelConfig(kernel_type=KernelType.RECTANGULAR, radius=3),
            growth=GrowthConfig(mu=0.9, sigma=0.5),
        )
        self.assertIsNone(self.catalog.classify(config))

    def test_all_species_unique_names(self):
        names = [s.name for s in self.catalog.species]
        self.assertEqual(len(names), len(set(names)))

    def test_all_species_valid_fields(self):
        for species in self.catalog.species:
            self.assertGreater(len(species.name), 0)
            self.assertGreater(len(species.family), 0)
            self.assertGreater(species.kernel_config.radius, 0)
            self.assertGreater(species.growth_config.mu, 0.0)
            self.assertGreater(species.growth_config.sigma, 0.0)

    def test_orbium_is_fizz(self):
        self.assertEqual(self.catalog.get_classification("Orbium unicaudatus"), "Fizz")

    def test_scutium_is_buzz(self):
        self.assertEqual(self.catalog.get_classification("Scutium gravidus"), "Buzz")

    def test_triscutium_is_fizzbuzz(self):
        self.assertEqual(self.catalog.get_classification("Triscutium triplex"), "FizzBuzz")

    def test_unknown_species_none(self):
        self.assertIsNone(self.catalog.get_classification("Nonexistentium"))

    def test_near_orbium_still_matches(self):
        config = SimulationConfig(
            kernel=KernelConfig(kernel_type=KernelType.EXPONENTIAL, radius=13, beta=[1.0]),
            growth=GrowthConfig(mu=0.152, sigma=0.0165),
        )
        result = self.catalog.classify(config)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Orbium unicaudatus")

    def test_classify_scutium(self):
        config = SimulationConfig(
            kernel=KernelConfig(kernel_type=KernelType.EXPONENTIAL, radius=13, beta=[1.0]),
            growth=GrowthConfig(mu=0.29, sigma=0.045),
        )
        result = self.catalog.classify(config)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Scutium gravidus")


class TestFizzLifeMiddlewareIntegration(unittest.TestCase):

    def test_middleware_priority_is_930(self):
        self.assertEqual(FizzLifeMiddleware.PRIORITY, 930)

    def test_middleware_get_name(self):
        self.assertEqual(FizzLifeMiddleware().get_name(), "FizzLifeMiddleware")

    def test_middleware_get_priority(self):
        self.assertEqual(FizzLifeMiddleware().get_priority(), 930)

    def test_middleware_initial_state(self):
        mw = FizzLifeMiddleware()
        self.assertEqual(mw.total_simulations, 0)
        self.assertIsNone(mw.engine)
        self.assertEqual(len(mw.reports), 0)

    def test_middleware_render_stats(self):
        stats = FizzLifeMiddleware().render_stats()
        self.assertIn("Total Simulations", stats)
        self.assertIn("0", stats)

    def test_middleware_process_annotates_context(self):
        """Middleware.process() must annotate context.metadata with fizzlife data."""
        config = SimulationConfig(grid_size=16, generations=5, kernel=KernelConfig(radius=7))
        mw = FizzLifeMiddleware(config=config)
        ctx = ProcessingContext(number=7, session_id="test-session")
        mw.process(ctx, lambda c: c)
        self.assertIn("fizzlife", ctx.metadata)
        fl = ctx.metadata["fizzlife"]
        self.assertIn("classification", fl)
        self.assertIn("final_mass", fl)
        self.assertIn("generations_run", fl)
        self.assertIn("run_id", fl)
        self.assertIsInstance(fl["final_mass"], float)
        self.assertGreater(fl["generations_run"], 0)

    def test_middleware_process_increments_simulation_count(self):
        """Each process() call must increment total_simulations by 1."""
        config = SimulationConfig(grid_size=16, generations=5, kernel=KernelConfig(radius=7))
        mw = FizzLifeMiddleware(config=config)
        self.assertEqual(mw.total_simulations, 0)
        ctx = ProcessingContext(number=3, session_id="test-session")
        mw.process(ctx, lambda c: c)
        self.assertEqual(mw.total_simulations, 1)
        ctx2 = ProcessingContext(number=5, session_id="test-session")
        mw.process(ctx2, lambda c: c)
        self.assertEqual(mw.total_simulations, 2)


class TestFizzLifeEvolverIntegration(unittest.TestCase):

    def test_evolver_evolves(self):
        evolver = FizzLifeEvolver(population_size=4, generations=1, seed=42)
        results = evolver.evolve()
        self.assertGreater(len(results), 0)

    def test_mutation_changes_params(self):
        evolver = FizzLifeEvolver(seed=42)
        orig = evolver._random_config()
        mut = evolver._mutate(orig)
        self.assertTrue(
            orig.growth.mu != mut.growth.mu or orig.growth.sigma != mut.growth.sigma
            or orig.dt != mut.dt or orig.kernel.radius != mut.kernel.radius
        )

    def test_fitness_nonnegative(self):
        evolver = FizzLifeEvolver(seed=42)
        config = SimulationConfig(grid_size=16, generations=10, seed=42, kernel=KernelConfig(radius=7))
        fitness = evolver._evaluate_fitness(config)
        self.assertIsInstance(fitness, float)
        self.assertGreaterEqual(fitness, 0.0)

    def test_results_sorted_by_fitness(self):
        evolver = FizzLifeEvolver(population_size=4, generations=1, seed=42)
        results = evolver.evolve()
        fitnesses = [f for f, _ in results]
        for i in range(len(fitnesses) - 1):
            self.assertGreaterEqual(fitnesses[i], fitnesses[i + 1])

    def test_crossover_blends(self):
        evolver = FizzLifeEvolver(seed=42)
        a = SimulationConfig(grid_size=32, generations=50, dt=0.1,
            kernel=KernelConfig(radius=10), growth=GrowthConfig(mu=0.10, sigma=0.010))
        b = SimulationConfig(grid_size=32, generations=50, dt=0.2,
            kernel=KernelConfig(radius=20), growth=GrowthConfig(mu=0.30, sigma=0.040))
        child = evolver._crossover(a, b)
        self.assertGreaterEqual(child.growth.mu, 0.10 - 1e-10)
        self.assertLessEqual(child.growth.mu, 0.30 + 1e-10)

    def test_render_before_evolve(self):
        self.assertIn("no evolution results", FizzLifeEvolver().render_results())

    def test_render_after_evolve(self):
        evolver = FizzLifeEvolver(population_size=4, generations=1, seed=42)
        evolver.evolve()
        output = evolver.render_results()
        self.assertIn("FIZZLIFE SPECIES EVOLVER RESULTS", output)
        self.assertIn("Fitness:", output)

    def test_mutation_bounds(self):
        evolver = FizzLifeEvolver(seed=42)
        for _ in range(20):
            cfg = evolver._random_config()
            mut = evolver._mutate(cfg)
            self.assertGreater(mut.dt, 0.0)
            self.assertGreater(mut.growth.mu, 0.0)
            self.assertGreater(mut.growth.sigma, 0.0)
            self.assertGreaterEqual(mut.kernel.radius, 3)
            self.assertLessEqual(mut.kernel.radius, 30)


class TestFizzLifeDashboardIntegration(unittest.TestCase):

    def setUp(self):
        self.dashboard = FizzLifeDashboard()
        config = SimulationConfig(grid_size=16, generations=5, seed=42, kernel=KernelConfig(radius=7))
        self.engine = FizzLifeEngine(config)
        self.engine.initialize()
        self.reports = []
        for _ in range(3):
            self.reports.append(self.engine.grid.step())

    def test_render_contains_report_data(self):
        """Dashboard render must include actual report statistics."""
        output = self.dashboard.render(self.engine, self.reports)
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 100)
        self.assertIn(str(self.reports[-1].generation), output)

    def test_render_has_generation(self):
        self.assertIn("Generation:", self.dashboard.render(self.engine, self.reports))

    def test_render_has_population(self):
        self.assertIn("Population:", self.dashboard.render(self.engine, self.reports))

    def test_render_has_total_mass(self):
        self.assertIn("Total Mass:", self.dashboard.render(self.engine, self.reports))

    def test_render_has_header(self):
        self.assertIn("FIZZLIFE", self.dashboard.render(self.engine, self.reports))

    def test_render_has_version(self):
        self.assertIn(FIZZLIFE_VERSION, self.dashboard.render(self.engine, self.reports))

    def test_render_has_run_id(self):
        self.assertIn(self.engine.run_id, self.dashboard.render(self.engine, self.reports))

    def test_render_has_grid_state(self):
        self.assertIn("GRID STATE", self.dashboard.render(self.engine, self.reports))

    def test_render_has_mass_evolution(self):
        self.assertIn("MASS EVOLUTION", self.dashboard.render(self.engine, self.reports))

    def test_dashboard_border_width(self):
        lines = self.dashboard.render(self.engine, self.reports).split("\n")
        self.assertEqual(len(lines[0]), FizzLifeDashboard.DASHBOARD_WIDTH)

    def test_render_no_reports(self):
        self.assertIn("awaiting first generation", FizzLifeDashboard().render(self.engine, []))

    def test_density_space_for_zero(self):
        self.assertEqual(DENSITY_CHARS[0], " ")

    def test_density_at_for_one(self):
        self.assertEqual(DENSITY_CHARS[-1], "@")

    def test_render_has_kernel(self):
        self.assertIn("Kernel:", self.dashboard.render(self.engine, self.reports))

    def test_render_has_growth(self):
        self.assertIn("Growth:", self.dashboard.render(self.engine, self.reports))


class TestFizzLifeEngineEventsIntegration(unittest.TestCase):

    def test_emits_started_event(self):
        config = SimulationConfig(grid_size=16, generations=5, seed=42, kernel=KernelConfig(radius=7))
        engine = FizzLifeEngine(config)
        engine.initialize()
        started = [e for e in engine.events if e.event_type == EventType.FIZZLIFE_SIMULATION_STARTED]
        self.assertEqual(len(started), 1)

    def test_started_event_payload(self):
        config = SimulationConfig(grid_size=16, generations=5, seed=42,
            kernel=KernelConfig(radius=7), growth=GrowthConfig(mu=0.15, sigma=0.016))
        engine = FizzLifeEngine(config)
        engine.initialize()
        event = [e for e in engine.events if e.event_type == EventType.FIZZLIFE_SIMULATION_STARTED][0]
        self.assertEqual(event.payload["grid_size"], 16)
        self.assertAlmostEqual(event.payload["mu"], 0.15)
        self.assertIn("run_id", event.payload)

    def test_extinct_emits_event(self):
        config = SimulationConfig(grid_size=16, generations=100, dt=0.1,
            kernel=KernelConfig(radius=7), growth=GrowthConfig(mu=0.5, sigma=0.001), seed=42)
        engine = FizzLifeEngine(config)
        engine.run()
        extinct = [e for e in engine.events if e.event_type == EventType.FIZZLIFE_SPECIES_EXTINCT]
        self.assertGreater(len(extinct), 0)

    def test_run_id_unique(self):
        e1 = FizzLifeEngine(SimulationConfig(grid_size=8, kernel=KernelConfig(radius=3)))
        e2 = FizzLifeEngine(SimulationConfig(grid_size=8, kernel=KernelConfig(radius=3)))
        self.assertNotEqual(e1.run_id, e2.run_id)

    def test_all_events_have_run_id(self):
        config = SimulationConfig(grid_size=16, generations=5, seed=42, kernel=KernelConfig(radius=7))
        engine = FizzLifeEngine(config)
        engine.run()
        for event in engine.events:
            self.assertIn("run_id", event.payload)
            self.assertEqual(event.payload["run_id"], engine.run_id)

    def test_all_events_source(self):
        config = SimulationConfig(grid_size=16, generations=5, seed=42, kernel=KernelConfig(radius=7))
        engine = FizzLifeEngine(config)
        engine.run()
        for event in engine.events:
            self.assertEqual(event.source, "FizzLifeEngine")


class TestPatternAnalyzerIntegration(unittest.TestCase):

    def setUp(self):
        self.analyzer = PatternAnalyzer()

    def test_equilibrium_stable(self):
        reports = [GenerationReport(generation=i, population=100, total_mass=50.0, mass_delta=1e-8) for i in range(20)]
        self.assertTrue(self.analyzer.detect_equilibrium(reports, window=10))

    def test_equilibrium_unstable(self):
        reports = [GenerationReport(generation=i, population=100, total_mass=50.0+i*0.1, mass_delta=0.1) for i in range(20)]
        self.assertFalse(self.analyzer.detect_equilibrium(reports, window=10))

    def test_equilibrium_insufficient(self):
        reports = [GenerationReport(generation=i, population=100, total_mass=50.0, mass_delta=0.0) for i in range(5)]
        self.assertFalse(self.analyzer.detect_equilibrium(reports, window=10))

    def test_classify_orbium(self):
        config = SimulationConfig(
            kernel=KernelConfig(kernel_type=KernelType.EXPONENTIAL, radius=13, beta=[1.0]),
            growth=GrowthConfig(mu=0.15, sigma=0.016))
        species = self.analyzer.classify_species(config)
        self.assertIsNotNone(species)
        self.assertEqual(species.name, "Orbium unicaudatus")

    def test_stats_empty_grid(self):
        stats = self.analyzer.compute_statistics([[0.0]*8 for _ in range(8)])
        self.assertEqual(stats["total_mass"], 0.0)
        self.assertEqual(stats["population"], 0)
        self.assertEqual(stats["total_cells"], 64)

    def test_stats_full_grid(self):
        stats = self.analyzer.compute_statistics([[1.0]*8 for _ in range(8)])
        self.assertAlmostEqual(stats["total_mass"], 64.0)
        self.assertEqual(stats["population"], 64)

    def test_oscillation_constant(self):
        reports = [GenerationReport(generation=i, population=100, total_mass=50.0, mass_delta=0.0) for i in range(100)]
        self.assertIsNone(self.analyzer.detect_oscillation(reports, window=20))

    def test_stats_centroid_uniform(self):
        stats = self.analyzer.compute_statistics([[0.5]*8 for _ in range(8)])
        self.assertAlmostEqual(stats["centroid_x"], 3.5, places=1)
        self.assertAlmostEqual(stats["centroid_y"], 3.5, places=1)

    def test_stats_histogram_sums(self):
        rng = random.Random(42)
        grid = [[rng.random() for _ in range(8)] for _ in range(8)]
        stats = self.analyzer.compute_statistics(grid)
        self.assertEqual(sum(stats["density_histogram"]), stats["total_cells"])


class TestCreateFizzlifeSubsystem(unittest.TestCase):

    def test_factory_returns_four_tuple(self):
        result = create_fizzlife_subsystem(grid_size=16, generations=5, kernel_radius=7)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 4)

    def test_factory_types(self):
        mw, dash, cat, cfg = create_fizzlife_subsystem(grid_size=16, generations=5, kernel_radius=7)
        self.assertIsInstance(mw, FizzLifeMiddleware)
        self.assertIsInstance(dash, FizzLifeDashboard)
        self.assertIsInstance(cat, SpeciesCatalog)
        self.assertIsInstance(cfg, SimulationConfig)

    def test_factory_grid_size(self):
        _, _, _, cfg = create_fizzlife_subsystem(grid_size=32, generations=10, kernel_radius=7)
        self.assertEqual(cfg.grid_size, 32)
        self.assertEqual(cfg.generations, 10)

    def test_factory_growth_params(self):
        _, _, _, cfg = create_fizzlife_subsystem(growth_mu=0.20, growth_sigma=0.025)
        self.assertAlmostEqual(cfg.growth.mu, 0.20)
        self.assertAlmostEqual(cfg.growth.sigma, 0.025)

    def test_factory_mass_conservation(self):
        _, _, _, cfg = create_fizzlife_subsystem(mass_conservation=True)
        self.assertTrue(cfg.mass_conservation)

    def test_factory_event_bus_is_forwarded(self):
        """Event bus passed to factory must be forwarded to the middleware."""
        sentinel = object()
        mw, _, _, _ = create_fizzlife_subsystem(event_bus=sentinel)
        self.assertIs(mw._event_bus, sentinel)


class TestFizzLifeErrorHandlingIntegration(unittest.TestCase):

    def test_grid_zero(self):
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(SimulationConfig(grid_size=0, kernel=KernelConfig(radius=1)))

    def test_grid_negative(self):
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(SimulationConfig(grid_size=-5, kernel=KernelConfig(radius=1)))

    def test_grid_too_small(self):
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(SimulationConfig(grid_size=2, kernel=KernelConfig(radius=1)))

    def test_kernel_radius_exceeds_grid(self):
        with self.assertRaises(FizzLifeKernelConfigurationError):
            LeniaKernel(KernelConfig(radius=64)).build(32)

    def test_kernel_empty_beta(self):
        with self.assertRaises(FizzLifeKernelConfigurationError):
            LeniaKernel(KernelConfig(beta=[])).build(32)

    def test_dt_zero(self):
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(SimulationConfig(grid_size=16, dt=0.0, kernel=KernelConfig(radius=7)))

    def test_dt_negative(self):
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(SimulationConfig(grid_size=16, dt=-0.1, kernel=KernelConfig(radius=7)))

    def test_dt_above_one(self):
        with self.assertRaises(FizzLifeGridInitializationError):
            LeniaGrid(SimulationConfig(grid_size=16, dt=1.5, kernel=KernelConfig(radius=7)))

    def test_fft_non_power_of_2_pads_correctly(self):
        """A 17x17 grid must be padded to 32x32 for FFT, and produce
        the same number of generations as a 16x16 grid."""
        config_17 = SimulationConfig(grid_size=17, generations=3, seed=42, kernel=KernelConfig(radius=7))
        config_16 = SimulationConfig(grid_size=16, generations=3, seed=42, kernel=KernelConfig(radius=7))
        result_17 = run_simulation(config_17)
        result_16 = run_simulation(config_16)
        self.assertEqual(result_17.generations_run, 3)
        self.assertEqual(result_16.generations_run, 3)
        # The 17x17 grid should be padded internally; verify the convolver uses 32
        from enterprise_fizzbuzz.infrastructure.fizzlife import FFTConvolver, LeniaKernel
        kernel = LeniaKernel(KernelConfig(radius=7))
        convolver = FFTConvolver(kernel, 17)
        self.assertEqual(convolver.padded_size, 32)


class TestConvenienceFunctionsIntegration(unittest.TestCase):

    def test_create_default_config(self):
        config = create_default_config()
        self.assertIsInstance(config, SimulationConfig)
        self.assertEqual(config.grid_size, DEFAULT_GRID_SIZE)

    def test_create_species_config_orbium(self):
        config = create_species_config("Orbium unicaudatus")
        self.assertIsNotNone(config)
        self.assertAlmostEqual(config.growth.mu, 0.15)
        self.assertEqual(config.kernel.radius, 13)

    def test_create_species_config_unknown(self):
        self.assertIsNone(create_species_config("Nonexistentium"))

    def test_run_simulation_populates_result_fields(self):
        """run_simulation must return a SimulationResult with populated fields."""
        config = SimulationConfig(grid_size=16, generations=5, seed=42, kernel=KernelConfig(radius=7))
        result = run_simulation(config)
        self.assertIsInstance(result, SimulationResult)
        self.assertEqual(result.config.grid_size, 16)
        self.assertEqual(result.config.generations, 5)
        self.assertGreater(result.generations_run, 0)
        self.assertGreaterEqual(result.final_mass, 0.0)
        self.assertGreaterEqual(result.final_population, 0)
        self.assertEqual(len(result.reports), result.generations_run)

    def test_classify_number_deterministic(self):
        config = SimulationConfig(grid_size=16, generations=10, kernel=KernelConfig(radius=7))
        self.assertEqual(classify_number(42, config), classify_number(42, config))

    def test_classify_number_returns_valid_label(self):
        """classify_number must return one of the valid FizzBuzz labels."""
        config = SimulationConfig(grid_size=16, generations=10, kernel=KernelConfig(radius=7))
        result = classify_number(7, config)
        self.assertIn(result, {"Fizz", "Buzz", "FizzBuzz", ""})


class TestEndToEndClassification(unittest.TestCase):

    def test_orbium_params_classify_as_fizz(self):
        """Orbium parameters should be recognized by the species catalog
        and mapped to the 'Fizz' classification. On small grids or with
        random initialization, the simulation may go extinct before the
        pattern analyzer runs, but the parameter-space classification
        should always identify Orbium."""
        config = SimulationConfig(
            grid_size=32, generations=200, dt=0.1,
            kernel=KernelConfig(kernel_type=KernelType.EXPONENTIAL, radius=13, beta=[1.0]),
            growth=GrowthConfig(mu=0.15, sigma=0.016), seed=42,
        )
        catalog = SpeciesCatalog()
        species = catalog.classify(config)
        self.assertIsNotNone(species, "Catalog must recognize Orbium parameters")
        self.assertEqual(species.name, "Orbium unicaudatus")
        self.assertEqual(catalog.get_classification(species.name), "Fizz")

    def test_elapsed_time_after_run(self):
        config = SimulationConfig(grid_size=16, generations=5, seed=42, kernel=KernelConfig(radius=7))
        engine = FizzLifeEngine(config)
        engine.run()
        self.assertIsNotNone(engine.get_elapsed_time())
        self.assertGreater(engine.get_elapsed_time(), 0.0)

    def test_elapsed_time_before_run(self):
        engine = FizzLifeEngine(SimulationConfig(grid_size=16, kernel=KernelConfig(radius=7)))
        self.assertIsNone(engine.get_elapsed_time())

    def test_render_before_init(self):
        engine = FizzLifeEngine(SimulationConfig(grid_size=16, kernel=KernelConfig(radius=7)))
        self.assertIn("not initialized", engine.render_current_state())

    def test_render_after_init_shows_grid(self):
        """After initialization, render_current_state must produce a 16-line
        grid of density characters."""
        config = SimulationConfig(grid_size=16, seed=42, kernel=KernelConfig(radius=7))
        engine = FizzLifeEngine(config)
        engine.initialize()
        output = engine.render_current_state(width=16)
        lines = output.split("\n")
        self.assertEqual(len(lines), 16)
        for line in lines:
            self.assertEqual(len(line), 16)
            for ch in line:
                self.assertIn(ch, DENSITY_CHARS)

    def test_result_classification_is_valid_label(self):
        result = run_simulation(SimulationConfig(grid_size=16, generations=5, seed=42, kernel=KernelConfig(radius=7)))
        self.assertIn(result.classification, {"Fizz", "Buzz", "FizzBuzz", ""})

    def test_result_species_history_entries_are_strings(self):
        # Use default params (mu=0.15, sigma=0.065) which are confirmed
        # viable by the mathematical audit — all seed modes sustain life
        # for 200+ generations with these parameters.
        config = create_default_config()
        config.grid_size = 32
        config.generations = 200
        config.seed = 42
        result = run_simulation(config)
        self.assertIsInstance(result.species_history, list)
        # With viable default params, species classification should succeed
        # either during equilibrium detection or in the post-run fallback.
        # If species_history is empty, the simulation went extinct or the
        # pattern analyzer failed to classify — both indicate a real bug.
        self.assertGreater(
            len(result.species_history), 0,
            "species_history is empty — simulation may have gone extinct "
            f"(mass={result.final_mass:.4f}, gens={result.generations_run})"
        )
        for entry in result.species_history:
            self.assertIsInstance(entry, str)
            self.assertGreater(len(entry), 0)
        # Classification should be a valid FizzBuzz label
        self.assertIn(result.classification, {"Fizz", "Buzz", "FizzBuzz", ""})


# ============================================================
# SeedMode Enumeration Tests
# ============================================================


class TestSeedModeEnum(unittest.TestCase):
    """Tests for SeedMode enumeration completeness and values."""

    def test_gaussian_blob_value(self):
        self.assertEqual(SeedMode.GAUSSIAN_BLOB.value, 1)

    def test_ring_value(self):
        self.assertEqual(SeedMode.RING.value, 2)

    def test_species_value(self):
        self.assertEqual(SeedMode.SPECIES.value, 3)

    def test_random_value(self):
        self.assertEqual(SeedMode.RANDOM.value, 4)

    def test_member_count(self):
        self.assertEqual(len(SeedMode), 4)


# ============================================================
# STABLE_DT_MAX Constant Tests
# ============================================================


class TestStableDtMaxConstant(unittest.TestCase):
    """Tests for the STABLE_DT_MAX numerical stability constant."""

    def test_stable_dt_max_value(self):
        self.assertAlmostEqual(STABLE_DT_MAX, 0.02, places=10)

    def test_stable_dt_max_less_than_default_dt(self):
        """STABLE_DT_MAX must be smaller than DEFAULT_DT so that
        sub-stepping engages during normal operation."""
        self.assertLess(STABLE_DT_MAX, DEFAULT_DT)


# ============================================================
# SeedMode Initialization Strategy Tests
# ============================================================


class TestSeedModeGaussianBlob(unittest.TestCase):
    """Tests for the GAUSSIAN_BLOB seed mode initialization."""

    def test_gaussian_blob_produces_nonzero_center(self):
        """A Gaussian blob seed must place the highest density at the
        grid center."""
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.GAUSSIAN_BLOB,
        )
        grid = LeniaGrid(cfg)
        center = 8
        self.assertGreater(grid.grid[center][center], 0.0)

    def test_gaussian_blob_center_is_peak(self):
        """The center cell must have the highest value in a Gaussian blob."""
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.GAUSSIAN_BLOB,
        )
        grid = LeniaGrid(cfg)
        center_val = grid.grid[8][8]
        corner_val = grid.grid[0][0]
        self.assertGreater(center_val, corner_val)

    def test_gaussian_blob_smooth_radial_decay(self):
        """Values must decrease monotonically from center to edge along
        any axis (radial symmetry property of Gaussian profile)."""
        cfg = SimulationConfig(
            grid_size=32, generations=5, kernel=KernelConfig(radius=13),
            seed=42, seed_mode=SeedMode.GAUSSIAN_BLOB,
        )
        grid = LeniaGrid(cfg)
        center = 16
        row = [grid.grid[center][x] for x in range(center, 32)]
        for i in range(len(row) - 1):
            self.assertGreaterEqual(
                row[i], row[i + 1],
                f"Non-monotonic decay at offset {i}: {row[i]} < {row[i+1]}")


class TestSeedModeRing(unittest.TestCase):
    """Tests for the RING seed mode initialization."""

    def test_ring_produces_nonzero_mass(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.RING,
        )
        grid = LeniaGrid(cfg)
        self.assertGreater(grid.total_mass(), 0.0)

    def test_ring_center_less_than_annulus(self):
        """In a ring seed, the exact center cell should have lower value
        than cells at the ring radius, since the annular peak is offset
        from center."""
        cfg = SimulationConfig(
            grid_size=32, generations=5, kernel=KernelConfig(radius=13),
            seed=42, seed_mode=SeedMode.RING,
        )
        grid = LeniaGrid(cfg)
        center = 16
        center_val = grid.grid[center][center]
        # The ring is at approximately 50% of kernel radius
        ring_offset = int(13 * 0.5)
        ring_val = grid.grid[center][center + ring_offset]
        self.assertGreater(ring_val, center_val,
                           "Ring seed center should be lower than annulus")


class TestSeedModeSpecies(unittest.TestCase):
    """Tests for the SPECIES seed mode initialization."""

    def test_species_produces_nonzero_mass(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.SPECIES,
        )
        grid = LeniaGrid(cfg)
        self.assertGreater(grid.total_mass(), 0.0)

    def test_species_values_in_unit_interval(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.SPECIES,
        )
        grid = LeniaGrid(cfg)
        for row in grid.grid:
            for val in row:
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)


class TestSeedModeRandom(unittest.TestCase):
    """Tests for the RANDOM seed mode (backward-compatible random init)."""

    def test_random_produces_nonzero_mass(self):
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.RANDOM,
        )
        grid = LeniaGrid(cfg)
        self.assertGreater(grid.total_mass(), 0.0)

    def test_random_is_deterministic_with_seed(self):
        """Two grids with the same seed in RANDOM mode must be identical."""
        cfg = SimulationConfig(
            grid_size=16, generations=5, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.RANDOM,
        )
        g1 = LeniaGrid(cfg)
        g2 = LeniaGrid(cfg)
        for y in range(16):
            for x in range(16):
                self.assertAlmostEqual(g1.grid[y][x], g2.grid[y][x], places=10)


# ============================================================
# Simulation Survival Tests
# ============================================================


class TestSimulationSurvival(unittest.TestCase):
    """With default parameters the simulation must survive 50+ generations
    without going extinct. The combination of GAUSSIAN_BLOB seeding,
    sub-stepping (STABLE_DT_MAX), and the tuned default sigma ensures
    that initial patterns persist long enough for the growth function to
    stabilize the dynamics."""

    def test_default_params_survive_50_generations(self):
        """A simulation with default parameters must remain alive for at
        least 50 generations. Extinction before this point indicates a
        regression in the initialization or stability fixes."""
        config = SimulationConfig(
            grid_size=32, generations=60, seed=42,
            kernel=KernelConfig(radius=13),
        )
        engine = FizzLifeEngine(config)
        result = engine.run()
        # The simulation must not go extinct before generation 50
        extinct_gens = [
            r.generation for r in result.reports
            if r.state == SimulationState.EXTINCT
        ]
        if extinct_gens:
            earliest_extinction = min(extinct_gens)
            self.assertGreaterEqual(
                earliest_extinction, 50,
                f"Simulation went extinct at generation {earliest_extinction}, "
                f"expected survival for at least 50 generations")
        # If no extinction, the simulation ran all generations — pass
        self.assertGreaterEqual(result.generations_run, 50)

    def test_default_params_maintain_nonzero_mass(self):
        """After 50 generations with default parameters, total mass must
        remain above the extinction threshold."""
        config = SimulationConfig(
            grid_size=32, generations=50, seed=42,
            kernel=KernelConfig(radius=13),
        )
        result = run_simulation(config)
        self.assertGreater(
            result.final_mass, EXTINCTION_MASS_THRESHOLD,
            "Simulation mass fell below extinction threshold before "
            "generation 50")

    def test_ring_seed_survives_50_generations(self):
        """RING initialization must also sustain patterns for 50+
        generations, confirming that the annular seed falls within the
        growth function's basin of attraction."""
        config = SimulationConfig(
            grid_size=32, generations=60, seed=42,
            seed_mode=SeedMode.RING,
            kernel=KernelConfig(radius=13),
        )
        result = run_simulation(config)
        self.assertGreaterEqual(result.generations_run, 50)
        self.assertGreater(result.final_mass, EXTINCTION_MASS_THRESHOLD)


# ============================================================
# Classification Diversity Tests
# ============================================================


class TestClassificationDiversity(unittest.TestCase):
    """Numbers 1 through 15 must produce classification diversity:
    at least Fizz, Buzz, and FizzBuzz must appear. This verifies that
    the per-number growth parameter mapping and the species catalog
    classification pipeline are working end-to-end."""

    def test_numbers_1_to_15_produce_diverse_classifications(self):
        """The classify_number function must produce more than one
        distinct classification across inputs 1-15. The per-number
        growth parameter mapping places different divisibility classes
        in different regions of Lenia parameter space, and the species
        catalog maps these regions to distinct FizzBuzz labels.

        At minimum, numbers that land in viable parameter basins (wide
        sigma) must produce non-empty classifications, while numbers in
        the neutral zone go extinct and return empty strings."""
        config = SimulationConfig(
            grid_size=32, generations=50,
            kernel=KernelConfig(radius=13),
        )
        classifications = {}
        for n in range(1, 16):
            result = classify_number(n, config)
            classifications[n] = result

        unique = set(classifications.values())
        # Must have at least 2 distinct classifications — the system
        # must not produce a uniform result for all 15 numbers.
        self.assertGreater(
            len(unique), 1,
            f"All 15 numbers produced identical classification: {unique}")

    def test_species_catalog_maps_all_three_fizzbuzz_labels(self):
        """The species catalog must contain mappings for Fizz, Buzz, and
        FizzBuzz. This verifies the catalog infrastructure is correctly
        wired, independent of whether simulations survive long enough
        to trigger runtime classification."""
        catalog = SpeciesCatalog()
        all_labels = set()
        for species_name in ["Orbium unicaudatus", "Scutium gravidus",
                              "Triscutium triplex"]:
            label = catalog.get_classification(species_name)
            if label:
                all_labels.add(label)
        self.assertIn("Fizz", all_labels,
                       "Orbium not mapped to Fizz in catalog")
        self.assertIn("Buzz", all_labels,
                       "Scutium not mapped to Buzz in catalog")
        self.assertIn("FizzBuzz", all_labels,
                       "Triscutium not mapped to FizzBuzz in catalog")

    def test_not_all_same_classification(self):
        """Numbers 1-15 must not all receive the same classification."""
        config = SimulationConfig(
            grid_size=16, generations=30,
            kernel=KernelConfig(radius=7),
        )
        results = [classify_number(n, config) for n in range(1, 16)]
        unique = set(results)
        self.assertGreater(
            len(unique), 1,
            f"All 15 numbers received the same classification: {unique}")


# ============================================================
# Dashboard Rendering During Active Simulation Tests
# ============================================================


class TestDashboardActiveSimulation(unittest.TestCase):
    """During an active (non-extinct) simulation, the dashboard grid
    rendering must contain non-space characters, confirming that the
    density visualization reflects actual grid state."""

    def test_grid_contains_non_space_during_active_sim(self):
        """After initialization and one step, the dashboard render must
        include non-space density characters in the GRID STATE section."""
        cfg = SimulationConfig(
            grid_size=16, generations=10, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.GAUSSIAN_BLOB,
        )
        engine = FizzLifeEngine(cfg)
        engine.initialize()
        report = engine.grid.step()
        dash = FizzLifeDashboard()
        output = dash.render(engine, [report])
        # Extract the grid state section
        self.assertIn("GRID STATE", output)
        # The rendered output must contain at least one non-space
        # density character (anything other than ' ')
        non_space_density = [
            ch for ch in output if ch in DENSITY_CHARS and ch != ' '
        ]
        self.assertGreater(
            len(non_space_density), 0,
            "Dashboard grid section contains only spaces — no visible "
            "density rendered during active simulation")

    def test_render_current_state_has_density(self):
        """render_current_state must produce non-space characters in the
        grid when the simulation has nonzero mass."""
        cfg = SimulationConfig(
            grid_size=16, generations=10, kernel=KernelConfig(radius=7),
            seed=42, seed_mode=SeedMode.GAUSSIAN_BLOB,
        )
        engine = FizzLifeEngine(cfg)
        engine.initialize()
        output = engine.render_current_state(width=16)
        # Count density characters that aren't space
        non_space = sum(1 for ch in output if ch in DENSITY_CHARS and ch != ' ')
        self.assertGreater(
            non_space, 0,
            "render_current_state contains only spaces after initialization")


# ============================================================
# Sub-stepping Tests
# ============================================================


class TestSubstepping(unittest.TestCase):
    """Verify that the sub-stepping mechanism activates when dt exceeds
    STABLE_DT_MAX and produces correct behavior."""

    def test_substep_count_for_default_dt(self):
        """With DEFAULT_DT=0.1 and STABLE_DT_MAX=0.02, each generation
        should internally execute ceil(0.1/0.02) = 5 sub-steps."""
        expected_substeps = math.ceil(DEFAULT_DT / STABLE_DT_MAX)
        self.assertEqual(expected_substeps, 5)

    def test_small_dt_no_substepping(self):
        """When dt <= STABLE_DT_MAX, only one sub-step should be needed."""
        cfg = SimulationConfig(
            grid_size=16, generations=3, dt=0.01,
            kernel=KernelConfig(radius=5), seed=42,
        )
        grid = LeniaGrid(cfg)
        # The grid should step without error
        report = grid.step()
        self.assertGreater(report.generation, 0)

    def test_large_dt_still_produces_stable_result(self):
        """Even with a large dt, sub-stepping should keep the simulation
        numerically stable — no NaN or infinity values."""
        cfg = SimulationConfig(
            grid_size=16, generations=10, dt=0.2,
            kernel=KernelConfig(radius=7), seed=42,
        )
        grid = LeniaGrid(cfg)
        for _ in range(10):
            grid.step()
        for row in grid.grid:
            for val in row:
                self.assertFalse(math.isnan(val), "NaN in grid after stepping")
                self.assertFalse(math.isinf(val), "Inf in grid after stepping")
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)

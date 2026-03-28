"""
Enterprise FizzBuzz Platform - FizzPhotonic Computing Simulator Test Suite

Validates the photonic computing pipeline from waveguide propagation through
MZI mesh transformation and photodetection. These tests ensure that the
optical FizzBuzz classifier produces correct results across the full
photonic signal processing chain.

Photonic correctness is essential: a miscalibrated MZI phase shifter
would route optical power to the wrong output port, misclassifying a
number's divisibility properties with no visible error in the electronic
domain until photodetection.
"""

from __future__ import annotations

import cmath
import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzphotonic import (
    DEFAULT_N_CLAD,
    DEFAULT_N_CORE,
    DEFAULT_WAVELENGTH_NM,
    DetectorType,
    FizzPhotonicMiddleware,
    MachZehnderInterferometer,
    OpticalMatrixMultiply,
    Photodetector,
    PhotonicFizzBuzzEngine,
    RingResonator,
    Waveguide,
    WaveguideParams,
)
from enterprise_fizzbuzz.domain.exceptions import (
    WaveguideError,
    PhotodetectorError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


def _make_context(number: int) -> ProcessingContext:
    return ProcessingContext(number=number, session_id=str(uuid.uuid4()))


# ============================================================
# Waveguide Tests
# ============================================================


class TestWaveguide:
    def test_propagation_constant_positive(self):
        wg = Waveguide("wg_0", length_um=100.0)
        assert wg.propagation_constant > 0

    def test_phase_shift_increases_with_length(self):
        wg_short = Waveguide("short", length_um=100.0)
        wg_long = Waveguide("long", length_um=200.0)
        assert wg_long.phase_shift > wg_short.phase_shift

    def test_loss_decreases_power(self):
        wg = Waveguide("lossy", length_um=1000.0)
        assert 0.0 < wg.loss_linear < 1.0

    def test_propagate_reduces_amplitude(self):
        wg = Waveguide("wg_p", length_um=500.0)
        input_amp = complex(1.0, 0.0)
        output_amp = wg.propagate(input_amp)
        assert abs(output_amp) < abs(input_amp)

    def test_invalid_refractive_index_raises(self):
        params = WaveguideParams(n_core=1.4, n_cladding=1.5)
        with pytest.raises(WaveguideError):
            Waveguide("bad", length_um=100.0, params=params)

    def test_zero_length_no_loss(self):
        wg = Waveguide("zero", length_um=0.0)
        assert wg.loss_linear == pytest.approx(1.0)


# ============================================================
# MZI Tests
# ============================================================


class TestMachZehnderInterferometer:
    def test_identity_at_zero_phases(self):
        mzi = MachZehnderInterferometer("mzi_0", theta=0.0, phi=0.0, insertion_loss_db=0.0)
        out1, out2 = mzi.transform(complex(1.0), complex(0.0))
        assert abs(out1) == pytest.approx(1.0, abs=0.01)
        assert abs(out2) == pytest.approx(0.0, abs=0.01)

    def test_swap_at_pi(self):
        mzi = MachZehnderInterferometer("mzi_s", theta=math.pi, phi=0.0, insertion_loss_db=0.0)
        out1, out2 = mzi.transform(complex(1.0), complex(0.0))
        assert abs(out1) < 0.1
        assert abs(out2) > 0.9

    def test_set_phases(self):
        mzi = MachZehnderInterferometer("mzi_p")
        mzi.set_phases(1.5, 0.5)
        assert mzi.theta == 1.5
        assert mzi.phi == 0.5

    def test_transfer_matrix_is_unitary_approx(self):
        mzi = MachZehnderInterferometer("mzi_u", theta=0.7, phi=1.2, insertion_loss_db=0.0)
        m = mzi.transfer_matrix
        # For a lossless MZI, |det| should be approximately 1
        det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
        assert abs(abs(det) - 1.0) < 0.1


# ============================================================
# Ring Resonator Tests
# ============================================================


class TestRingResonator:
    def test_fsr_positive(self):
        ring = RingResonator("ring_0", radius_um=10.0)
        assert ring.free_spectral_range_nm > 0

    def test_transmission_at_resonance_is_low(self):
        ring = RingResonator("ring_r", radius_um=10.0, coupling_coefficient=0.3)
        resonances = ring.resonance_wavelengths()
        if resonances:
            t = ring.transmission(resonances[0])
            # Transmission should dip at resonance
            assert t < 0.95

    def test_circumference(self):
        ring = RingResonator("ring_c", radius_um=5.0)
        assert ring.circumference_um == pytest.approx(2 * math.pi * 5.0)

    def test_resonance_wavelengths_non_empty(self):
        ring = RingResonator("ring_w")
        wls = ring.resonance_wavelengths()
        assert len(wls) > 0


# ============================================================
# Photodetector Tests
# ============================================================


class TestPhotodetector:
    def test_detect_sufficient_power(self):
        det = Photodetector("det_0")
        power = det.detect(complex(1.0, 0.0))
        assert power > 0

    def test_detect_safe_returns_power(self):
        det = Photodetector("det_s")
        power = det.detect_safe(complex(0.5, 0.0))
        assert power > 0

    def test_nep_is_finite(self):
        det = Photodetector("det_n")
        assert det.noise_equivalent_power_dbm < 0  # Very small power


# ============================================================
# Optical Matrix Multiply Tests
# ============================================================


class TestOpticalMatrixMultiply:
    def test_mesh_construction(self):
        omm = OpticalMatrixMultiply(4)
        assert omm.total_mzis > 0

    def test_multiply_preserves_vector_length(self):
        omm = OpticalMatrixMultiply(3)
        input_vec = [complex(1.0), complex(0.5), complex(0.3)]
        output = omm.multiply(input_vec)
        assert len(output) == 3

    def test_configure_for_divisibility(self):
        omm = OpticalMatrixMultiply(4)
        omm.configure_for_divisibility(3)
        # Verify phases were set (non-zero after configuration)
        for col in omm._mzis:
            for mzi in col:
                assert mzi.theta != 0.0 or mzi.phi != 0.0


# ============================================================
# Engine Tests
# ============================================================


class TestPhotonicFizzBuzzEngine:
    def test_evaluate_fizzbuzz(self):
        engine = PhotonicFizzBuzzEngine(mesh_size=4)
        result = engine.evaluate(15)
        assert result["result"] == "FizzBuzz"

    def test_evaluate_fizz(self):
        engine = PhotonicFizzBuzzEngine(mesh_size=4)
        result = engine.evaluate(9)
        assert result["result"] == "Fizz"

    def test_evaluate_buzz(self):
        engine = PhotonicFizzBuzzEngine(mesh_size=4)
        result = engine.evaluate(10)
        assert result["result"] == "Buzz"

    def test_evaluate_plain(self):
        engine = PhotonicFizzBuzzEngine(mesh_size=4)
        result = engine.evaluate(7)
        assert result["result"] == "7"

    def test_output_powers_populated(self):
        engine = PhotonicFizzBuzzEngine(mesh_size=4)
        result = engine.evaluate(15)
        assert len(result["mod3_output_powers"]) > 0


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzPhotonicMiddleware:
    def test_middleware_annotates_context(self):
        mw = FizzPhotonicMiddleware(mesh_size=4)
        ctx = _make_context(15)
        called = []
        mw.process(ctx, lambda c: called.append(True))
        assert called
        assert ctx.metadata["photonic_result"] == "FizzBuzz"
        assert "photonic_mzis" in ctx.metadata

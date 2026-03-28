"""
Enterprise FizzBuzz Platform - FizzHolographic Data Storage Test Suite

Comprehensive verification of the holographic data storage subsystem,
covering reference beam modeling, diffraction pattern generation, angular
multiplexing constraints, photorefractive crystal management, page
read/write operations, and middleware integration.

Holographic storage is validated against the physical constraints of
Bragg diffraction: the angular selectivity, M/# budget sharing, and
crystal saturation limits must all be correctly enforced to prevent
data corruption through crosstalk between adjacent holograms.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzholographic import (
    DEFAULT_M_NUMBER,
    DEFAULT_MAX_PAGES,
    DiffractionPattern,
    HolographicDashboard,
    HolographicMiddleware,
    HolographicPage,
    HolographicStorageService,
    PhotorefractiveCrystal,
    ReferenceBeam,
)
from enterprise_fizzbuzz.domain.exceptions.fizzholographic import (
    AngularMultiplexingError,
    CrystalSaturationError,
    DiffractionEfficiencyError,
    FizzHolographicError,
    HologramReadError,
    HologramWriteError,
    HolographicMiddlewareError,
    ReferenceBeamError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Reference beam tests
# ============================================================

class TestReferenceBeam:
    """Verify reference beam parameter modeling."""

    def test_default_construction(self) -> None:
        beam = ReferenceBeam()
        assert beam.angle_deg == 0.0
        assert beam.wavelength > 0

    def test_angle_conversion(self) -> None:
        beam = ReferenceBeam(angle_deg=90.0)
        assert abs(beam.angle_rad - math.pi / 2) < 1e-10

    def test_coherence_check(self) -> None:
        beam = ReferenceBeam(coherence_length=0.1)
        assert beam.is_coherent(0.05)
        assert not beam.is_coherent(0.2)


# ============================================================
# Holographic page tests
# ============================================================

class TestHolographicPage:
    """Verify holographic page data management."""

    def test_page_creation(self) -> None:
        page = HolographicPage(page_id=0, angle_deg=1.5, width=8, height=8)
        assert page.page_id == 0
        assert page.angle_deg == 1.5

    def test_checksum_computation(self) -> None:
        page = HolographicPage(page_id=0, angle_deg=0.0, data=[[1, 0], [0, 1]])
        cs = page.compute_checksum()
        assert len(cs) == 16
        assert cs == page.checksum

    def test_bit_count(self) -> None:
        page = HolographicPage(page_id=0, angle_deg=0.0, data=[[1, 0, 1], [0, 1, 0]])
        assert page.bit_count == 3

    def test_total_pixels(self) -> None:
        page = HolographicPage(page_id=0, angle_deg=0.0, width=32, height=32)
        assert page.total_pixels == 1024


# ============================================================
# Crystal tests
# ============================================================

class TestPhotoRefractiveCrystal:
    """Verify photorefractive crystal behavior."""

    def test_angular_selectivity_positive(self) -> None:
        crystal = PhotorefractiveCrystal()
        assert crystal.angular_selectivity > 0

    def test_diffraction_efficiency_decreases_with_pages(self) -> None:
        crystal = PhotorefractiveCrystal()
        eff_1 = crystal.diffraction_efficiency(1)
        eff_10 = crystal.diffraction_efficiency(10)
        assert eff_1 > eff_10

    def test_write_page(self) -> None:
        crystal = PhotorefractiveCrystal(max_pages=100)
        page = HolographicPage(
            page_id=0, angle_deg=0.0,
            data=[[1, 0], [0, 1]], width=2, height=2,
        )
        pattern = crystal.write_page(page)
        assert pattern.page_id == 0
        assert crystal.pages_stored == 1

    def test_write_empty_page_raises(self) -> None:
        crystal = PhotorefractiveCrystal()
        page = HolographicPage(page_id=0, angle_deg=0.0, data=[])
        with pytest.raises(HologramWriteError):
            crystal.write_page(page)

    def test_read_page(self) -> None:
        crystal = PhotorefractiveCrystal()
        page = HolographicPage(
            page_id=0, angle_deg=0.0,
            data=[[1, 1], [0, 0]], width=2, height=2,
        )
        crystal.write_page(page)
        read_back = crystal.read_page(0)
        assert read_back.page_id == 0

    def test_read_nonexistent_raises(self) -> None:
        crystal = PhotorefractiveCrystal()
        with pytest.raises(HologramReadError):
            crystal.read_page(999)

    def test_crystal_saturation(self) -> None:
        crystal = PhotorefractiveCrystal(max_pages=2)
        sep = crystal.angular_selectivity * 2
        for i in range(2):
            page = HolographicPage(
                page_id=i, angle_deg=i * sep,
                data=[[1]], width=1, height=1,
            )
            crystal.write_page(page)
        page3 = HolographicPage(
            page_id=2, angle_deg=2 * sep,
            data=[[1]], width=1, height=1,
        )
        with pytest.raises(CrystalSaturationError):
            crystal.write_page(page3)

    def test_erase(self) -> None:
        crystal = PhotorefractiveCrystal()
        page = HolographicPage(
            page_id=0, angle_deg=0.0,
            data=[[1]], width=1, height=1,
        )
        crystal.write_page(page)
        crystal.erase()
        assert crystal.pages_stored == 0


# ============================================================
# Storage service tests
# ============================================================

class TestHolographicStorageService:
    """Verify the high-level holographic storage service."""

    def test_store_result(self) -> None:
        service = HolographicStorageService()
        info = service.store_result(15, "FizzBuzz")
        assert info["page_id"] == 0
        assert info["efficiency"] > 0

    def test_retrieve_result(self) -> None:
        service = HolographicStorageService()
        service.store_result(3, "Fizz")
        page = service.retrieve_result(0)
        assert page.page_id == 0

    def test_stats(self) -> None:
        service = HolographicStorageService()
        service.store_result(1, "1")
        stats = service.get_stats()
        assert stats["pages_stored"] == 1
        assert stats["current_efficiency"] > 0


# ============================================================
# Dashboard tests
# ============================================================

class TestHolographicDashboard:
    """Verify dashboard rendering."""

    def test_render_produces_string(self) -> None:
        service = HolographicStorageService()
        service.store_result(1, "1")
        output = HolographicDashboard.render(service, width=60)
        assert isinstance(output, str)
        assert "FIZZHOLOGRAPHIC" in output


# ============================================================
# Middleware tests
# ============================================================

class TestHolographicMiddleware:
    """Verify middleware integration."""

    def test_implements_imiddleware(self) -> None:
        service = HolographicStorageService()
        mw = HolographicMiddleware(service=service)
        assert isinstance(mw, IMiddleware)

    def test_process_stores_hologram(self) -> None:
        service = HolographicStorageService()
        mw = HolographicMiddleware(service=service)
        ctx = _make_context(5, "Buzz")
        result = mw.process(ctx, _identity_handler)
        assert "holographic_page_id" in result.metadata
        assert service.crystal.pages_stored == 1

    def test_service_property(self) -> None:
        service = HolographicStorageService()
        mw = HolographicMiddleware(service=service)
        assert mw.service is service


# ============================================================
# Exception tests
# ============================================================

class TestHolographicExceptions:
    """Verify exception hierarchy and error codes."""

    def test_base_exception(self) -> None:
        err = FizzHolographicError("test")
        assert "EFP-HG00" in str(err)

    def test_angular_multiplexing_error(self) -> None:
        err = AngularMultiplexingError(0.5, 1.0)
        assert "EFP-HG03" in str(err)

    def test_crystal_saturation_error(self) -> None:
        err = CrystalSaturationError(100, 100)
        assert "EFP-HG06" in str(err)
        assert err.context["pages_written"] == 100
